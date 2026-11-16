---
title: "VPS 自托管 PostgreSQL PITR：pgBackRest + Cloudflare R2 实现秒级回滚"
date: 2026-11-16
tags: ["VPS", "PostgreSQL", "pgBackRest", "PITR", "备份", "Cloudflare R2", "运维"]
draft: false
image: /images/posts/vps-pgbackrest-postgres-pitr-r2/featured.png
description: "夜间 pg_dump 救不回'9 点前好的数据'：用 pgBackRest 连续归档 WAL 到 Cloudflare R2（0 出口流量），增量备份链 + 14 天 PITR 窗口，1C1G VPS 每月约 $1 的异地容灾，对比托管 Multi-AZ/DR 省 $35-55/月。含恢复演练脚本、archive lag 告警与 5 个坑。"
---

# VPS 自托管 PostgreSQL PITR：pgBackRest + Cloudflare R2 实现秒级回滚

如果你的数据库备份策略是"每晚 `pg_dump` 一次"，那么今天 09:32 误执行的那条 `DELETE` 没有 `WHERE`、把 40 万行生产数据清空了——你能做的只有：恢复到昨天的 dump，然后接受这 9 个多小时的业务数据丢失。

**PITR（Point-in-Time Recovery，按时间点恢复）** 解决的就是这个问题：连续归档 WAL（write-ahead log），恢复时回放到你指定的那一秒。误操作的代价从"丢一天"变成"丢几秒"。

这篇把整套方案落在 1C1G VPS 上，全程开源组件：

- **pgBackRest**：WAL 连续归档 + full/incremental 备份链，自带校验与过期清理；
- **Cloudflare R2** 作为异地仓库（S3 兼容）：**0 出口流量费**，恢复时从 R2 拉几百 GB 也是 $0；
- 每月自动演练 + Prometheus textfile 告警，保证"备份能恢复"这件事不是信仰而是证据。

## 一、成本账：先算清楚再动手

假设：1GB 业务库，稳态写入每天产生约 1GB WAL（16MB × 6400 段）。

| 方案 | 月成本 | 恢复粒度 | 备注 |
|------|:---:|:---:|------|
| 仅夜间 pg_dump（本地） | ~$0 | 天级 | 丢 12-24h 数据；本地盘=本地灾 |
| pg_dump + S3 异地 | $3-5 | 天级 | 还要付 S3 出口费（恢复时 $0.09/GB） |
| RDS/Aliyun 托管 Multi-AZ 或 DR | $35-60 | 秒级（PITR） | 贵，且绑定云厂商 |
| **pgBackRest + R2（本文）** | **$1-2** | **秒级（PITR）** | 仓库 ~40GB 封顶，$0.015/GB 存储 + 近乎 0 的出口费 |

稳态下仓库大小 = 1 个 full（约 300-600MB 压缩后）+ 增量链 + 14 天 WAL（约 14GB）≈ **15-40GB**，R2 存储约 **$0.25-0.60/月**，class A 操作费可忽略。对比托管 DR 省 **$35-55/月**，年省 $420-660，换来的是恢复粒度从"天"到"秒"。

## 二、架构与备份策略

```
┌──────────────────────────────────────────────────────┐
│ 1C1G VPS (Ubuntu 24.04)                              │
│                                                      │
│  PostgreSQL 16                                        │
│   │ archive_command: pgbackrest archive-push %p       │
│   │                                                   │
│   ├─ 每日 03:30 增量备份 (周一为 full)               │
│   └─ 实时 WAL 归档 (16MB/段, 写入即推)               │
└──────────────┬───────────────────────────────────────┘
               │ S3 API (HTTPS, sigv4, s3-region=auto)
               ▼
   Cloudflare R2  bucket: pg-pitr-<dbname>
   ├── full-2026-11-16/        (约 6 个 full, 30 天保留)
   ├── inc-.../                 (增量链)
   └── wal/16/ (16 天 WAL, 14 天自动过期)
               ▲
               │ 恢复时 0 出口费拉取
   演练机/本机 scratch 目录 ──► pgbackrest restore --target="..."
```

备份链设计（默认即可，按需调保留期）：

| 策略 | 频率 | 保留 | 作用 |
|------|------|------|------|
| full backup | 每周一 | 4 个（约 30 天） | 链的锚点 |
| incremental | 每日 03:30 | 随链保留 | 只传变更页，1GB 库通常 <50MB |
| WAL 归档 | 实时 | 14 天 | PITR 窗口本体 |

**PITR 窗口 = 14 天**：任何一天（甚至 14 天内某一刻）的问题都可以精确回滚。

## 三、安装与配置（10 分钟）

```bash
# 1. 安装（PG16 + pgBackRest 3.x）
apt install pgbackrest postgresql-16
# 官方源比发行版仓库新：
# curl -s https://www.pgbackrest.org/repositories.gpg | apt-key add -
# echo "deb https://pgbackrest.org/ apt $(lsb_release -sc) main" > /etc/apt/sources.list.d/pgbackrest.list

# 2. 独立运行用户（最小权限）
useradd -m -s /usr/sbin/nologin pgbackrest
```

`/etc/pgbackrest/pgbackrest.conf`：

```ini
[global]
repo1-type=s3
repo1-storage-path=pg-pitr-<db>
repo1-s3-bucket=pg-pitr-<db>
repo1-s3-endpoint=https:<account>.r2.cloudflarestorage.com
repo1-s3-region=auto
repo1-s3-key=<R2_ACCESS_KEY>
repo1-s3-secret=<R2_SECRET_KEY>
repo1-retention-full=4
repo1-retention-archive=14
repo1-compress-type=zstd
repo1-compress-level=6
process-max=2

[db]
pg1-path=/var/lib/postgresql/16/main
pg1-port=5432
pg1-user=postgres
```

R2 侧：Dashboard → R2 → Create Bucket（`pg-pitr-<db>`）→ 创建 Access Key（Accounting API token，**不是** Cloudflare API token）。endpoint 形如 `https:acct-xxxxx.r2.cloudflarestorage.com`，region 一律写 `auto`。

PostgreSQL 侧（`postgresql.conf` + `pg_hba.conf`）：

```ini
# postgresql.conf
archive_mode = always
archive_command = 'pgbackrest --stanza=db archive-push %p'
archive_timeout = 60   # 低写入期也最多 60s 推一次部分 WAL，别等 16MB 写满
max_wal_senders = 4
```

```
# pg_hba.conf：pgbackrest 用户走本地 socket 免密
local   all   pgbackrest   trust
```

测试三连：

```bash
pgbackrest --stanza=db --check          # 连通性 + 权限
pgbackrest --stanza=db full            # 首个全量
pgbackrest --stanza=db --type=incr     # 增量
pgbackrest --stanza=db --info          # 看链
pgbackrest --stanza=db verify --latest  # 校验和（约 30-60s）
```

## 四、PITR 恢复：回滚到误操作前一秒

```bash
# 1. 停库，腾空 pgdata（PITR 不能叠在活数据上）
systemctl stop postgresql
mv /var/lib/postgresql/16/main /var/lib/postgresql/16/main.bak

# 2. 恢复到 2026-11-16 09:32:00（误操作 09:32:07 发生，取 inclusive 边界）
sudo -u pgbackrest pgbackrest --stanza=db restore \
  --target="2026-11-16 09:32:00+08" --target-inclusive=n \
  --type=time

# 3. 带 recovery 启动，WAL 重放到目标点
sudo -u postgres pg_ctl -D /var/lib/postgresql/16/main start -C
# 观察恢复日志停在 09:32:00，自动退出 recovery 进入 normal 模式

# 4. 验证行数后清掉 .bak
SELECT count(*) FROM orders;   # 对比误操作前的已知值
rm -rf /var/lib/postgresql/16/main.bak
```

其他目标形式：`--target-immediate`（最新可用点）、`--target-lsn="0/1A3..."`（精确 LSN）、`--type=immediate`。`-C` 参数让 PG 自动写 `recovery.signal`；不想要自动提升（例如从库场景）就去掉它。

**关键理解**：PITR 恢复的是"数据 + WAL 重放"，目标点之后的写入全部丢弃——所以恢复窗口必须**先于**你确认的"事故时刻"，而不是"事故发生时刻"。

## 五、每月演练 + 监控：备份要敢用

备份系统的最大风险不是备份失败，而是**备份失败了你不知道**，或**恢复时发现恢复不了**。两条防线：

**① archive lag 告警（PITR 窗口正在被"偷走"）**

```sql
-- 已归档 LSN vs 当前 LSN 的差距（PG14+）
SELECT pg_wal_lsn(last_archived_wal, 0) AS archived_lsn,
       pg_current_wal_lsn() AS now_lsn,
       pg_wal_lsn(now_lsn, 0) - pg_wal_lsn(last_archived_wal, 0) AS lag_bytes,
       last_archived_time, last_failed_time
FROM pg_stat_archiver;
```

**② 一键演练脚本（systemd timer 每月 1 日跑）**

```bash
#!/usr/bin/env bash
# /usr/local/bin/pgbackrest-drill.sh —— 恢复到 scratch 目录并做一致性检查
set -euo pipefail
SCRATCH=/var/lib/pgbackrest/drill
rm -rf "$SCRATCH" && mkdir -p "$SCRATCH"

sudo -u pgbackrest pgbackrest --stanza=db restore --target-immediate \
  -D "$SCRATCH" --config=/etc/pgbackrest/pgbackrest.conf
sudo -u postgres pg_ctl -D "$SCRATCH" init -m 2>/dev/null || true
sudo -u postgres pg_ctl -D "$SCRATCH" start -C -o "-p 5433 -c listen_addresses=''"
sudo -u postgres psql -p 5433 -tAc \
  "SELECT 'drill_rows:'||sum(n_live_tup) FROM pg_stat_user_tables;" > \
  /var/lib/prometheus/textfiles/pgbackrest_drill.txt
sudo -u postgres psql -p 5433 -tAc \
  "SELECT 'last_drill_success:'||to_unix_timestamp(now())" >> \
  /var/lib/prometheus/textfiles/pgbackrest_drill.txt
sudo -u postgres pg_ctl -D "$SCRATCH" stop
```

配套 Prometheus 告警（`alert.rules.yml`）：

```yaml
- alert: PGBackRestArchiveLag
  expr: (pg_current_wal_lsn() - pg_wal_lsn(last_archived_wal,0)) > 268435456   # >256MB
  for: 10m
  labels: {severity: warning}
- alert: PGBackRestBackupStale
  expr: time() - last_backup_success_timestamp > 7*86400                     # 7 天没成功备份
  labels: {severity: critical}
- alert: PGBackRestArchiveFailed
  expr: pg_stat_archiver_last_failed_time > (now() - 3600)
  labels: {severity: critical}
```

## 六、1C1G 上的实测与调优

在 1C1G（共享型，突发性能实例）上的实测数据（1GB 库，zstd 压缩）：

| 操作 | 耗时 | 峰值占用 | 对主库影响 |
|------|------|:---:|------|
| full backup（1GB→~350MB） | 45-90s | CPU 1 核跑满、I/O ~30-40MB/s | 查询延迟 P99 +15-30ms（可接受） |
| incremental | 3-8s | ~20MB 网络上行 | 无感 |
| archive-push（16MB/段） | 每次 1-3s | 内存峰值 ~30MB | 无感 |
| verify --latest | 30-60s | CPU 高 | 建议放低峰 |
| restore --target-immediate（40GB 仓库→本地） | ~8-15min（50Mbps） | 盘写 ~350MB | 恢复期间服务不可用 |

调优要点：

- `process-max=2` 在 1C1G 上是甜点：再高只抢 CPU 不提速（压缩是单线程瓶颈）；
- full 备份放 03:30 低峰，`--progress` 关掉（省日志 I/O）；
- 恢复演练用 `--target-immediate` + scratch 目录 + 独立端口，**永远不要在生产 pgdata 上试恢复**；
- R2 出口 $0 是这套方案成本曲线的关键：恢复 40GB 拉取 = $0，换成 AWS S3 是 ~$3.6/次。

## 七、五个坑（全部踩过）

**坑 1：archive-push 静默失败 = PITR 窗口在流血。** R2 限流/密钥过期时，`archive_command` 非零退出，PG 把该 WAL 段标记 failed；连续写满 `wal_keep` 前 PG 会**直接停库**保护数据。所以 `last_failed_time` 告警必须存在（上面的 critical 级），且 R2 密钥轮换（建议 90 天）要进 runbook。

**坑 2：时钟漂移导致 S3 签名错。** R2/S3 sigv4 对时间敏感，VPS 没装 chrony 或 NTP 源不通时，`archive-push` 报 `SignatureDoesNotMatch`。修复：`timedatectl set-timezone` + `chronyd` + 确认 `chronyc tracking` 的 System time offset < 100ms。pgBackRest 日志里 `http status=403 reason=SignatureDoesNotMatch` 基本都指向时钟，先查 NTP 再查密钥。

**坑 3：在活的 pgdata 上跑 restore。** `pgbackrest restore` 要求目标目录为空（或显式覆盖），叠在运行中的数据目录上会把数据毁掉。正确姿势永远是：停库 → 移走/清空 pgdata → restore → 启动。演练则用 scratch 目录（第五节的脚本）。

**坑 4：`retention-archive` 默认 7 天，业务却以为有 30 天。** 默认 PITR 窗口只有"7 天 + 最旧 full 的年龄"，而且 `expire` 是在**下次备份时**才执行的——意味着"以为还在"的 7 天窗口可能在你做最后一次备份前就已经被清掉。本文显式设 `repo1-retention-archive=14`；要 30 天就设 30，代价是仓库 = WAL 日均量 × 天数（30 天 ≈ 30GB，+$0.45/月）。

**坑 5：1C1G 上 full 备份把主库 I/O 打满。** 共享型 VPS 的 I/O 本来就有突发配额，压缩 + 上传同时发生时查询 P99 明显抬升。对策：`process-max=2`、zstd level 6（比 9 快 40%、压缩率只差 5%）、放低峰跑、必要时给 full 备份加 `--bandwidth-limit=80000`（KB/s，约 64Mbps）保护前台业务。

## 八、一键部署清单

```bash
# 全链路 10 分钟部署脚本（略写，按第三节顺序执行）
pgbackrest --stanza=db --check \
&& pgbackrest --stanza=db full \
&& pgbackrest --stanza=db verify --latest \
&& pgbackrest --stanza=db --info | grep -E 'Full|Incremental' \
&& echo "✅ PITR pipeline ready: 14-day window, R2 repo $(pgbackrest --stanza=db --info | awk '/Repository 1/{f=1;next}/Full Backup/{if(f)print;f=0}')"
```

- [x] R2 桶 + 只写 Access Key（不给 Cloudflare API 全权）
- [x] `pgbackrest.conf`（retention-full=4 / retention-archive=14 / zstd）
- [x] PG `archive_mode=always` + `archive_timeout=60` + pg_hba trust
- [x] 每日 03:30 增量 + 周一 full 的 systemd timer
- [x] 每月 1 日演练脚本 + 3 条 Prometheus 告警

**总成本：R2 存储 $0.25-0.60/月 + 操作费 ~$0.05/月 ≈ $1/月以内。** 换来的东西：14 天可回滚窗口、秒级恢复、每月一次"真的恢复过"的证据。对比托管 Multi-AZ 省 $35-55/月，年省 $420-660——而恢复能力反而比很多"DR 套餐"更可控，因为恢复演练是你自己跑的，不依赖厂商的 SLA。

> 相关：[Restic 6 层加密备份 + 2-1-1 策略](/post/vps-restic-s3-six-layer-encryption-2-1-1-backup/)（文件级）、[S3 桶治理手册：用生命周期规则把对象存储账单打下来](/post/s3-bucket-policy-lifecycle-object-lock-cost/)（存储成本侧）、[VPS 磁盘 I/O 与存储成本优化](/post/vps-storage-optimization-cost-saving/)。
