---
title: "VPS 自托管 Valkey：$0/月替代托管 Redis，1C1G 直接扛"
date: 2026-11-23
tags: ["VPS", "Valkey", "Redis", "缓存", "自托管", "云省钱", "运维"]
draft: false
image: /images/posts/vps-valkey-selfhosted-redis-replacement/featured.png
description: "Valkey（Linux 基金会开源 Redis 分支，Apache-2.0）在 1C1G VPS 上空闲 ~30-50MB：内存缓存 + 消息队列 + 计数器一体。maxmemory 256MB + allkeys-lru 保内存安全，RDB+AOF 夜备 restic→R2（出口费 $0），$0-4/月替代托管 Redis（$5-35/月），年省 $60-420。含 systemd cgroup 加固、内存监控告警与 5 个坑。"
---

# VPS 自托管 Valkey：$0/月替代托管 Redis，1C1G 直接扛

Redis 是"托管清单"里性价比最低的一项：90% 的用法只是会话缓存、限流计数器和短消息队列，却按 99.95% SLA 的价格付月费——托管版通常还强制最低 1GB 内存起步。把一个 1GB 起步的托管 Redis 换成自托管 Valkey，内存直接定 256MB 就跑，省下的不只是钱，还有厂商的内存阶梯定价。

**Valkey** 是什么：2024 年 Redis 6.2/7.x 之后核心转向 RSALv2/SSPL 双许可证，Linux 基金会随即把 Redis 7.2.4 的开源代码收编为 **Valkey**（Apache-2.0），IBM、AWS、Google、Ericsson 都在贡献代码。协议 100% 兼容 Redis 7.2，客户端（redis-py、ioredis、go-redis）不用改一行代码，8.x 版本多核性能比原版 Redis 7.2 显著提升（官方基准 5.4 倍于 Redis 7.2 的某些多核场景）。

**为什么现在换**：Redis 7.4 之后商用授权收紧，新项目写进代码库的"Redis"越来越多其实是 Valkey 二进制——社区默认标准在转移，现在搭自托管正好落在主流轨道上。

## 一、成本账：先算清楚再动手

假设场景：一个 Web 应用需要 ~256MB 的内存缓存 + 限流计数器，当前用托管 Redis（最低 1GB 档位）。

| 方案 | 月成本 | 内存 | 备注 |
|------|:---:|:---:|------|
| DigitalOcean Managed Redis | $15 | 1GB | 最低档 1GB，$15 起 |
| Vultr Managed Redis | ~$16 | 1GB | 同上 |
| GCP Memorystore for Redis | $17-25 | 1GB | 含 99.9% SLA |
| AWS ElastiCache (t4g.small) | $20-30 | 1GB | 最低实例 1GB，还有网络费 |
| Upstash（按量） | $0-15 | 弹性 | 免费额度后按操作量/存储计费，突发流量会烧钱 |
| Aiven for Redis | $7-20 | 1GB | 最低档偏贵 |
| **Valkey @ 1C1G VPS** | **$0-4** | **256MB 即可** | VPS 本来就有则 $0；新开机型 $3-5 |

**年省 $60-420**（取决于原来托管方案），且 256MB 够用就是 256MB——自托管的内存阶梯是 1MB 粒度，不是厂商的 1GB 起步。

**边界要说清**：自托管 ≠ 白嫖。你放弃了 99.95% SLA，换来的是：缓存节点挂了不挂全服务（应用层 fail-open），数据全在 R2（出口费 $0），没有厂商涨价/停服风险。

## 二、原理：为什么单进程能扛缓存 + 队列 + 计数器

Valkey 是单线程事件循环 + 多核 I/O 线程（8.x）的内存数据库，核心数据都在 RAM：

| 用途 | 命令 | 典型场景 |
|------|------|------|
| 会话/接口缓存 | SET/GET/EXPIRE | API 响应缓存、登录会话 |
| 限流计数器 | INCR/EXPIRE | 每秒令牌桶、每日配额 |
| 短消息队列 | LPUSH/RPOP | 异步任务缓冲（非持久队列） |
| 排行榜/热点 | ZADD/ZRANGE | 实时榜单、Top-N |

关键设计点：

- **内存就是上限**：`maxmemory` 配死 + `maxmemory-policy allkeys-lru`，写满自动逐出最久未用的键，进程内存永不越界；
- **持久化双轨**：RDB（快照）+ AOF（`aof-use-rdb-preamble`，8.x 默认开启，AOF 以 RDB 为前缀，体积减半、重建更快）；
- **REST 无感**：不需要外部数据库/注册中心，单二进制 ~30MB，空闲 ~30-50MB，1C1G 和 nginx/systemd 共存毫无压力；
- **客户端零改动**：`redis://` 协议 100% 兼容，代码里只改连接串。

## 三、架构：一台 VPS 上的三个角色

```
 [应用 / API / 定时任务]
        │  redis:// (仅内网/Tailscale，6379 不暴露公网)
        ▼
 ┌─────────────────────────┐
 │  Valkey (单进程)         │
 │  maxmemory 256MB        │
 │  allkeys-lru            │
 │  RDB + AOF (RDB 前缀)   │
 └────┬───────────────┬────┘
      │ INFO memory   │ dump.rdb + appendonlydir
      ▼               ▼
 [Prometheus 文本采集]  [restic 夜备 → R2 ($0 出口)]
 [Kuma TCP 探测]       [7 代保留，异地恢复点]
```

要点：

- **6379 永远不直接对公网**：本地应用直连 `127.0.0.1:6379`；远程访问走 Tailscale 私有网络（见 [Tailscale 零配置远程访问](/post/vps-tailscale-zero-config-remote-access/)）或 SSH 隧道，管理/调试面永远不裸奔；
- **持久化落 R2**：RDB 快照每 6 小时一次（`save 60 1000` + 每小时 dump），restic 夜备 `dump.rdb` + `appendonlydir/` 到 Cloudflare R2，出口费 $0，7 代保留；
- **监控走 Prometheus**：`INFO` 命令拉 `used_memory`、`evicted_keys`、`aof_last_write_status`，文本文件落地，3 条告警（见第五节）。

## 四、部署：systemd + cgroup 加固

### 1. 安装（Debian/Ubuntu 22.04+）

```bash
# 官方仓库
curl -fsSL https://packages.valkey.io/valkey.asc | gpg --dearmor -o /usr/share/keyrings/valkey.gpg
echo "deb [signed-by=/usr/share/keyrings/valkey.gpg] https://packages.valkey.io/1.0/$(. /etc/os-release && echo $VERSION_CODENAME) main" \
  > /etc/apt/sources.list.d/valkey.list
apt update && apt install -y valkey valkey-tools
valkey-server --version   # 8.x
```

（Alpine/裸机可下载官方二进制 `valkey-8.x-linux-amd64.tar.gz` 解压即用，无依赖。）

### 2. 配置 `/etc/valkey/valkey.conf`

```conf
# 网络：只监听回环，公网访问走 Tailscale/SSH 隧道
bind 127.0.0.1 -::*
port 6379
protected-mode yes

# 认证：本机回环也设密码（防御容器逃逸/本地提权链）
requirepass '你的强密码'

# 内存红线（1C1G 机器）
maxmemory 256mb
maxmemory-policy allkeys-lru

# 持久化
save 60 1000
save 300 100
aof-use-rdb-preamble yes
auto-aof-rewrite-percentage 100
auto-aof-rewrite-min-size 64mb
appendfsync everysec

# 其他
tcp-keepalive 60
notify-keyspace-events Ex   # 键过期事件，可选
```

### 3. systemd 单元（cgroup 硬约束）

`/etc/systemd/system/valkey.service`：

```ini
[Unit]
Description=Valkey in-memory data store
After=network.target

[Service]
User=valkey
Group=valkey
ExecStart=/usr/bin/valkey-server /etc/valkey/valkey.conf
ExecReload=/bin/kill -HUP $MAINPID
Restart=on-failure
RestartSec=2
# 内存硬顶：超限 OOM 先杀 Valkey 而不是邻居服务
MemoryMax=400M
MemoryHigh=320M
CPUQuota=90%
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
```

```bash
systemctl enable --now valkey
systemctl daemon-reload
```

`MemoryMax=400M` 的意义：Valkey 自己 `maxmemory=256mb` 是软顶（逐出策略），systemd 400M 是硬顶（cgroup 强杀）——双层保险，保证 1G 内存的 VPS 上 nginx、systemd、监控脚本永远活得下来。

### 4. 远程访问（三选一）

- **Tailscale**（推荐）：VPS 加节点，客户端 `redis://100.x.y.z:6379`，零端口暴露；
- **SSH 隧道**：`ssh -L 6380:127.0.0.1:6379 vps`，本地 `redis://localhost:6380`；
- **Cloudflare Tunnel**：仅管理面（valkey-cli / 调试），生产客户端流量不走 CF（加一跳延迟）。

## 五、监控与恢复

### Prometheus 采集（每 5 分钟一条）

```bash
#!/usr/bin/env bash
# /usr/local/bin/valkey-metrics.sh
OUT=/var/lib/prometheus/node_exporter_textfile/valkey.prom
valkey-cli -a "$PW" INFO memory > /tmp/vm 2>/dev/null
used=$(grep -oP 'used_memory_human.*\K\S+' /tmp/vm)
evict=$(grep -oP '^evicted_keys.*\K[0-9]+' /tmp/vm)
aof=$(grep -oP '^aof_last_write_status.*\K\S+' /tmp/vm)
conn=$(valkey-cli -a "$PW" INFO clients 2>/dev/null | grep -oP '^connected_clients.*\K[0-9]+')
cat > "$OUT" <<EOF
valkey_used_bytes $(grep -oP '^used_memory:\K[0-9]+' /tmp/vm)
valkey_evicted_keys_total $evict
valkey_aof_write_ok $( [ "$aof" = "ok" ] && echo 1 || echo 0 )
valkey_connected_clients $conn
EOF
```

systemd timer 每 5 分钟跑一次；Grafana/Kuma 侧 3 条告警：

| 告警 | 条件 | 级别 |
|------|------|------|
| 内存逼近红线 | `valkey_used_bytes > 90% × 256MB` | warning（逐出开始，查内存大户） |
| AOF 写失败 | `valkey_aof_write_ok == 0` | critical（磁盘满/IO 异常） |
| 客户端堆积 | `valkey_connected_clients > 100` | warning（连接泄漏或被打爆） |

### 异地恢复演练（每月一次）

```bash
# R2 → scratch 目录 → 校验 → 加载
restic -r $R2_REPO restore latest -t /tmp/valkey-restore
# 起临时实例（6399）加载校验，不碰生产 6379
valkey-server --port 6399 --daemonize yes --dir /tmp/valkey-restore --dbfilename dump.rdb
valkey-cli -p 6399 DBSIZE   # 与 INFO persistence 的 last_key... 比对
```

恢复时间预期：256MB RDB 在 50Mbps 带宽下 R2 拉取 + 加载 < 30 秒。

## 六、实测预期（1C1G VPS）

| 指标 | 数值 |
|------|------|
| 空闲内存 | ~30-50MB（+ 256MB 缓存池 = 上限 300MB 左右） |
| GET/SET 单客户端 | ~5-8 万 ops/s（管道化可翻 3-5 倍） |
| 限流计数器（INCR+EXPIRE） | 10 万+/s，单核 CPU < 15% |
| RDB 256MB 快照 | ~1-3 秒，IO 尖峰 < 5s |
| AOF 每日增量（写 1GB/天） | ~200-500MB，R2 存储 $0.01-0.02/月 |
| 256MB 缓存命中 90% | 回源 QPS 降 10 倍，上游 DB/LLM 成本直接省 90% |

## 七、5 个坑

1. **6379 裸奔公网无认证**：扫描器 10 分钟内找上门，`INFO` 直接拖库 + 写 SSH 后门。永远 `bind 127.0.0.1` + requirepass，远程走 Tailscale/隧道。
2. **不设 maxmemory/policy**：1G 机器上 Valkey 吃满内存 → 内核 OOM 随机杀邻居（nginx、你的 cron）；`allkeys-lru` + `maxmemory` 是两条红线，缺一不可。
3. **AOF rewrite 在突发型 VPS 上的 IO 尖峰**：`BGREWRITEAOF` 会占盘 IO 数分钟，小 VPS 的 IOPS 配额下会拖慢所有读。对策：`auto-aof-rewrite-min-size 64mb` 拉长重写间隔 + `aof-use-rdb-preamble` 减小重写体积，重写窗口避开业务高峰，重点是大 VPS 上别同时跑 restic 全量。
4. **把托管 SLA 当自托管预期**：Valkey 节点挂了，应用 99.95% 没了——应用层必须 fail-open（缓存 miss 直接回源 + 超时 50ms），别把 Valkey 当唯一事实来源；持久化数据进 PostgreSQL，Valkey 只是加速层。
5. **RDB 恢复后版本号漂移**：低版本 Valkey 写的 RDB 被高版本加载没问题，反过来（升级失败回滚）直接拒绝。升级前 `RESTORE` 演练 + restic 保留上一版二进制备份。

## 八、混合模式（不放心就先用这个）

- **开发/staging 全自托管，生产托管**：连接串走环境变量，同一套代码，上线期省 0 但零风险；
- **L1 自托管 + L2 托管**：本机 Valkey（256MB）做热层，miss 穿透 Upstash/托管做冷层 + 突发承接，托管费降到最低档；
- **迁移路径**：双写 1 周（新写 Valkey + 旧读托管）→ 切读 → 下线托管，全程不停服。

---

**总结**：Valkey 把"Redis 托管税"打到了 $0-4/月：单二进制 30MB、256MB 内存顶 256MB 缓存（厂商 1GB 起步的 1/4 价格 × 1/4 容量 = 实际更省），RDB+AOF 夜备 R2 出口费 $0，cgroup 硬顶保 1C1G 邻居安全。前置纪律三条：6379 不裸奔、maxmemory 必配、应用 fail-open。做到这三条，托管 Redis 的账单可以删了。
