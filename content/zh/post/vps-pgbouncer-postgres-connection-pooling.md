---
title: "VPS 上 Postgres 连接数爆炸？Pgbouncer 连接池 30 分钟落地"
date: 2026-11-27
tags: ["VPS", "Pgbouncer", "PostgreSQL", "连接池", "自托管", "云省钱", "运维"]
draft: false
image: /images/posts/vps-pgbouncer-postgres-connection-pooling/featured.png
description: "Postgres 每个连接一个 ~10MB 进程，1C1G VPS 上 80 个连接就 OOM。Pgbouncer（~30MB 内存）用 20 条服务器连接承接 100+ 应用连接，30 分钟部署 + cgroup 加固 + 3 条告警，$0-5/月替代扩容到托管 PG（$15-50/月），年省 $180-600。含 SCRAM 认证、transaction 池 5 个坑。"
---

# VPS 上 Postgres 连接数爆炸？Pgbouncer 连接池 30 分钟落地

Postgres 的连接模型是"每个连接一个操作系统进程"，每个进程固定吃 8-12MB 内存（work_mem、查询缓存、socket 缓冲）外加业务查询的临时内存。默认 `max_connections=200` 听起来很大，但在一台 1C1G 的 VPS 上，shared_buffers 占 256-384MB 之后，**60-80 个活跃连接就能把机器打进 OOM**——而现代 Web 框架（Node 连接池 10-20、Python 连接池 5-10）加上 CI 跑批、监控脚本、备份工具，100+ 连接非常常见。

典型的事故顺序：`FATAL: sorry, too many clients already` → 有人把 `max_connections` 调大 → 内存直接 OOM，内核随机杀进程（被杀的是 nginx 而不是 Postgres）→ 最终"升级"到托管 PG 每月 $15-50。

**Pgbouncer** 把这条路堵死：一个 ~30MB 内存的进程挡在应用和 Postgres 之间，20 条"服务器连接"背后可以接 100-200 个"客户端连接"，总内存从 800MB-1GB 压回 ~250MB。$0 增量成本（VPS 本来就有），30 分钟部署完。

## 一、成本账：先算清楚再动手

假设场景：1C1G VPS 上自托管 Postgres，应用 + 定时任务 + 监控 + CI 共 ~100 个连接，已经频繁出现 `too many clients` 或 OOM。

| 方案 | 月成本 | 备注 |
|------|:---:|------|
| RDS db.t4g.micro（最小档） | $15-25 | 0.5GB 内存，$0.0208/hr 起，还有 I/O 与存储费 |
| DigitalOcean Managed PostgreSQL | $15-30 | 1GB 起步档 |
| Supabase（Pro） | $25 | 含托管，连接数同样有上限 |
| Aiven for PostgreSQL | $35-90 | 最小档偏贵 |
| 把 VPS 升到 2C4G 跑 Postgres | +$5-15 | 只为多塞 80 个连接 |
| **Postgres + Pgbouncer @ 原 1C1G** | **$0-4** | 连接问题原地解决，内存反而降 |

**年省 $180-600**。而且 Pgbouncer 的价值不止省钱：Postgres 的 `max_connections` 从此可以钉死在 50-100，内存占用可预测，OOM 消失。

**边界要说清**：Pgbouncer 只解决"连接数量"，不解决"连接质量"——慢查询、锁等待、`idle in transaction` 照样吃内存和坑池子（见第七节坑 4）。它不是 HA 组件，Postgres 挂了它不兜底，只是让 100 个客户端不必同时和 100 个 Postgres 进程握手。

## 二、原理：三种池模式，选错就白搭

Pgbouncer 有三种 `pool_mode`，行为差异巨大：

| 模式 | 行为 | 适用 | 内存收益 |
|------|------|------|:---:|
| `session` | 客户端连上就独占一条服务器连接直到断开 | 有会话状态、不敢改的应用（过渡期默认） | 低（只是排队，不共享） |
| `transaction` | 事务结束就归还服务器连接，下一个事务可给别的客户端 | 池友好的 Web 应用（首选） | 高（100 客户端共享 20 连接） |
| `stashed` | 事务结束连接"暂存"给原客户端 3 秒，别人等不到才共享 | 短事务 + 高 QPS | 中 |

**transaction 模式是真正省内存的那一个**：Postgres 侧连接数 = 池大小（20）而不是客户端数（100）。代价是应用必须"池友好"：

- 不用 `SET`（会话级）——用 `SET LOCAL`；
- 不用临时表、不用会话级 advisory lock（`pg_advisory_lock`；`pg_advisory_xact_lock` 是事务级的，OK）；
- 不用 `LISTEN`/`NOTIFY`；
- 命名 prepared statement（`PREPARE`/`EXECUTE`）不要跨事务复用——每个事务结束后会被 `DISCARD ALL` 重置。

做不到就先用 `session` 模式过渡（至少把 `max_connections` 撑住），逐步改造应用再切 `transaction`。

## 三、架构：一台 VPS 上的连接拓扑

```
 [Web 应用 ×100 连接] [CI/脚本 ×10] [监控 ×5]
        │                   │            │
        ▼                   ▼            ▼
 ┌────────────────────────────────────────────┐
 │  Pgbouncer (127.0.0.1:6432)  ~30MB        │
 │  pool_mode=transaction                     │
 │  max_client_conn=200 / 池=20 (+4 reserved) │
 │  SCRAM-SHA-256 认证                        │
 └──────────────────┬─────────────────────────┘
                    │ 20-24 条服务器连接
                    ▼
        PostgreSQL (127.0.0.1:5432)
        max_connections=50（钉死，不再放大）
                    │
                    ▼
        SHOW STATS → Prometheus 文本采集
                    → 3 条告警（池满/等待/连接堆积）
```

要点：

- **Pgbouncer 只监听回环**，远程访问走 Tailscale/SSH 隧道（见 [Tailscale 零配置远程访问](/post/vps-tailscale-zero-config-remote-access/)），6432 永不裸奔公网；
- **Postgres `max_connections` 反向收紧**到 50-100，Pgbouncer 池 = `max_connections - 预留运维连接`（留 10 个给 `\m` 调试、备份、监控）；
- **监控走 Prometheus 文本文件**：`SHOW STATS` 一行命令，5 分钟一次，3 条告警（见第五节）。

## 四、部署：30 分钟落地（Debian/Ubuntu）

### 1. 安装

```bash
apt update && apt install -y pgbouncer
pgbouncer --version   # Debian 12 / Ubuntu 22.04: 1.19-1.21
```

### 2. 配置 `/etc/pgbouncer/pgbouncer.ini`

```ini
[pgbouncer]
listen = 127.0.0.1:6432          # 仅回环
admin_users = pgbouncer         # 管理面只认 pgbouncer 账号
auth_type = scram-sha-256        # PG14+ 默认
auth_file = /etc/pgbouncer/userlist.txt
pool_mode = transaction          # 池友好应用首选
max_client_conn = 200           # 客户端连接上限（每条 ~48KB-1MB 缓冲）
default_pool_size = 20          # 每个 db/user 的服务器连接池
reserved_pool_size = 4          # 池满时给高优先连接的 4 个弹性位
reserved_pool_timeout = 3
client_idle_timeout = 600       # 10 分钟闲置客户端断开，防连接泄漏占坑
log_connections = 1             # 调试期开，稳态可关
# 管理面（SHOW POOLS/STATS）：用 pgbouncer 账号登录 6432 主端口即可，无需单独监听

[databases]
appdb = host=/var/run/postgresql port=5432 dbname=appdb
```

### 3. 认证：userlist.txt 用 Postgres 的 SCRAM 校验器

Pgbouncer 不需要知道明文密码——直接从 `pg_authid` 导出 Postgres 存的 SCRAM verifier：

```sql
-- 以 postgres 超级用户
SELECT rolname, rolpassword FROM pg_authid WHERE rolname = 'app';
-- 结果形如: {SCRAM-SHA-256$4096:xxxxxxxx:yyyy$zzzz...}
```

写入 `/etc/pgbouncer/userlist.txt`（**引号必须带**，PG13+ 的 verifier 含 `:` 和 `$`）：

```
"app" "{SCRAM-SHA-256$4096:xxxxxxxx:yyyy$zzzz...}"
"pgbouncer" "scram-sha-256$<salt>$<StoredKey>:<ServerKey>"   # 或手动生成
```

pgbouncer 账号本身可用 `pgbouncer` 自带的生成方式或一条 SQL 造出 verifier（`SELECT 'scram-sha-256$' || ...`）。权限：`chmod 640 /etc/pgbouncer/userlist.txt && chown pgbouncer:pgbouncer`。

### 4. systemd + cgroup 加固

发行版自带 `pgbouncer.service`，加 cgroup 硬顶（PG 在 1G 机器上，Pgbouncer 自身 ~30-50MB，给 64M 够用）：

```ini
# /etc/systemd/system/pgbouncer.service.d/override.conf
[Service]
MemoryMax=64M
MemoryHigh=48M
CPUQuota=50%
Restart=on-failure
RestartSec=2
```

```bash
systemctl daemon-reload && systemctl enable --now pgbouncer
```

### 5. 应用侧切换（零代码改动）

把连接串从 `host=127.0.0.1 port=5432` 改成 `host=127.0.0.1 port=6432`，用户密码不变。环境变量走配置中心的话一次改完。

### 6. 验证

```bash
psql -h 127.0.0.1 -p 6432 -U pgbouncer appdb -c "SHOW POOLS;"
psql -h 127.0.0.1 -p 6432 -U pgbouncer appdb -c "SHOW CLIENTS;"
psql -h 127.0.0.1 -p 6432 -U app appdb -c "SELECT 1;"    # 业务账号走池测试
```

`SHOW SERVERS` 应看到最多 24 条（20 池 + 4 reserved），而 `SHOW CLIENTS` 可以是 100+。

## 五、监控与告警

`SHOW STATS` 是现成的池指标源（`cl_active`/`cl_waiting`/`sv_used`/`sv_max`/`wait_count`/`wait_avg`），5 分钟一条落 Prometheus 文本文件：

```bash
#!/usr/bin/env bash
# /usr/local/bin/pgbouncer-metrics.sh
OUT=/var/lib/prometheus/node_exporter_textfile/pgbouncer.prom
psql -h 127.0.0.1 -p 6432 -U pgbouncer -d appdb -At \
  -c "SELECT sv_used || '|' || sv_max || '|' || wait_count || '|' || cl_active || '|' || cl_waiting FROM SHOW STATS;" > /tmp/pgb 2>/dev/null
IFS='|' read -r used mx wait cl cwait < /tmp/pgb
cat > "$OUT" <<EOF
pgbouncer_server_connections_used $used
pgbouncer_server_connections_max $mx
pgbouncer_client_connections_active $cl
pgbouncer_clients_waiting $cwait
EOF
```

systemd timer 每 5 分钟一次；Grafana/Kuma 侧 3 条告警：

| 告警 | 条件 | 级别 |
|------|------|------|
| 池耗尽 | `pgbouncer_server_connections_used == pgbouncer_server_connections_max`（连续 2 个周期） | critical（`wait_count` 会涨，查 sv_active 里卡住的连接） |
| 客户端排队 | `pgbouncer_clients_waiting > 5` 持续 5 分钟 | warning（池偏小或慢查询占坑，查 `pg_stat_activity`） |
| 客户端连接堆积 | `pgbouncer_client_connections_active > 80% × max_client_conn` | warning（连接泄漏或被打爆，对照 `client_idle_timeout` 是否生效） |

再加一条 Kuma TCP 探测 `127.0.0.1:6432`（Tailscale 节点探测），Pgbouncer 单点挂掉 30 秒内报出来。

## 六、实测预期（1C1G VPS）

| 指标 | 数值 |
|------|------|
| Pgbouncer 空闲内存 | ~8-12MB；满载 200 客户端 + 24 池 ~30-50MB |
| 每查询转发开销 | session 模式 <0.1ms；transaction 模式 0.1-0.5ms |
| 内存账（100 连接场景） | 无池：100 × 10MB ≈ 1GB → OOM；有池：24 × 10MB ≈ 240MB + Pgbouncer 40MB，省 ~800MB |
| 吞吐 | 简单 CRUD 池 20 可撑 10k-50k QPS，Pgbouncer 单核 CPU 30-50% |
| 切换耗时 | 应用改连接串重启，< 5 分钟；零数据迁移 |

## 七、5 个坑

1. **transaction 池直接接会话型应用，静默坏掉**：`SET`（非 LOCAL）、临时表、会话级 `pg_advisory_lock`、`LISTEN`/`NOTIFY`、跨事务复用命名 prepared statement——这些在 transaction 模式下要么失效要么报错，且报错只在部分请求上出现，极难复现。过渡期一律 `session` 模式，改造完用 `SHOW SERVERS` 的 `sv_used` 回落验证（transaction 模式下空闲期应回落到 1-5）。
2. **池配太大 = 换一种方式 OOM**：`default_pool_size=100` 在 1G 机器上是 100 × 10MB = 1GB 服务器连接内存，和裸奔 Postgres 一样死。公式钉死：**`池 × 10MB + shared_buffers ≤ 总内存 × 60%`**。池小不够用先看慢查询，别无脑加池。
3. **SCRAM/MD5 校验器错配**：PG16 默认 `password_encryption=scram-sha-256`，旧 userlist 用 md5 hash（或反向）会进登录死循环（`no matching sasl mechanism` / `password auth failed`）。每次 Postgres 改 `password_encryption` 或重置密码后，**重新从 `pg_authid` 导出 verifier 重写 userlist.txt**，并用 `psql -p 6432 -U app` 冒烟一次。
4. **`idle in transaction` 泄漏占死服务器连接**：应用 bug 开着事务不提交，在 transaction 模式下这条服务器连接**无限期被占用**，`sv_active` 顶满后整个池卡死（客户端全在 `cl_waiting`）。Pgbouncer 不自动杀——查 `psql -p 6432 "SHOW SERVERS;"` 找到 `active_for` 超长的条目，对应 `pg_stat_activity` terminate 掉；长期对策是给应用加语句/事务超时 + 告警第 2 条盯着 `sv_active`。
5. **Pgbouncer 自己是单点，且管理面别裸奔**：它不做任何 HA，Postgres 挂了 100 个客户端全挂在池上等 `server_connect_timeout`；`admin_server` 和业务同端口，任何拿到 Pgbouncer 的弱密码都能 `SHOW POOLS/CLIENTS` 看全拓扑。对策：`Restart=on-failure` + Kuma TCP 探测兜住自身；`pgbouncer` 管理账号用独立强密码；6432 只回环 + Tailscale 可达。

## 八、托管模式（不放心就先用这个）

- **RDS/Aurora 内置 PgBouncer，$0**：Aurora 控制台开 "Pgbouncer" 选项（端口 9997，`pool_mode=transaction`，每 128 连接 $0.03/hr），RDS 用 Parameter Group 加 `pgbouncer` 相关参数。托管 + 自带池 = 不升档位就解决连接数，自托管 Pgbouncer 留作冷备方案；
- **Supabase/Neon 侧**：Neon 连接数随计划（50-250），客户端统一走连接池（Neon 自带池或自己加 Pgbouncer 挡在 Neon 前面），`transaction` 模式把 250 上限拉到等效 1000+；
- **迁移路径**：应用先切到自托管 Pgbouncer（session 模式）→ 逐服务改池友好 → 切 transaction → 把 `max_connections` 从 200 收紧到 50 → 观测 2 周 `sv_used`/`wait_count` 稳定后删掉扩容计划。全程不停服。

---

**总结**：Postgres 连接数问题在 1C1G VPS 上几乎必然出现，而解法从来不是"升级数据库"——是一个 $0 的 30MB 进程：Pgbouncer 用 20 条服务器连接接住 100+ 应用连接，内存从 ~1GB 压回 ~300MB，`max_connections` 钉死 50-100。三条前置纪律：回环监听 + 池公式（`池×10MB + shared_buffers ≤ 60% 内存`）+ transaction 模式前跑一遍池友好改造。做到这三条，托管 PG 的账单可以不用付了。
