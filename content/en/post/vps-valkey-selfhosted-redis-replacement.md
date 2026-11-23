---
title: "Self-Host Valkey on a VPS: $0/mo Managed Redis Replacement on 1C1G"
date: 2026-11-23
tags: ["VPS", "Valkey", "Redis", "Caching", "Self-hosting", "Cost Savings", "DevOps"]
draft: false
image: /images/posts/vps-valkey-selfhosted-redis-replacement/featured.png
description: "Valkey (the Linux Foundation's open-source Redis fork, Apache-2.0) idles at ~30-50MB on a 1C1G VPS: in-memory cache + queue + counters in one process. maxmemory 256MB + allkeys-lru keeps memory safe; RDB+AOF nightly restic -> R2 ($0 egress). $0-4/mo replaces managed Redis ($5-35/mo), saving $60-420/yr. systemd cgroup hardening, memory monitoring, and 5 hard-won pitfalls."
---

# Self-Host Valkey on a VPS: $0/mo Managed Redis Replacement on 1C1G

Managed Redis is the worst-value line item on the hosting bill: 90% of workloads are session caches, rate-limit counters, and short queues, yet you pay for 99.95% SLA pricing with a minimum 1GB tier. Swap that 1GB managed instance for a self-hosted Valkey capped at 256MB and you keep the functionality while deleting the tier-based pricing.

**What is Valkey**: In 2024, after Redis's core team moved to the RSALv2/SSPL dual license, the Linux Foundation folded Redis 7.2.4's open-source codebase into **Valkey** (Apache-2.0), with code contributions from IBM, AWS, Google, and Ericsson. It's 100% protocol-compatible with Redis 7.2 — your clients (redis-py, ioredis, go-redis) need zero code changes — and 8.x shows dramatically better multi-core performance than stock Redis 7.2 in vendor benchmarks.

**Why switch now**: With Redis 7.4+ commercial licensing tightening, the "Redis" in new projects increasingly means Valkey binaries — the de facto standard is moving. Standing up a self-hosted cache today puts you on the mainline.

## 1. The math: calculate before you build

Scenario: a web app needs ~256MB of in-memory cache + rate-limit counters, currently on managed Redis (minimum 1GB tier).

| Option | Monthly | Memory | Notes |
|--------|:---:|:---:|------|
| DigitalOcean Managed Redis | $15 | 1GB | Minimum tier 1GB |
| Vultr Managed Redis | ~$16 | 1GB | Same |
| GCP Memorystore for Redis | $17-25 | 1GB | 99.9% SLA |
| AWS ElastiCache (t4g.small) | $20-30 | 1GB | Minimum instance 1GB + network fees |
| Upstash (usage-based) | $0-15 | elastic | Free tier, then per-op/per-store pricing — burst traffic burns |
| Aiven for Redis | $7-20 | 1GB | Expensive entry tier |
| **Valkey @ 1C1G VPS** | **$0-4** | **256MB is enough** | $0 if the VPS exists; $3-5 new box |

**Saves $60-420/yr** (depending on the managed plan you replace), and memory granularity is 1MB instead of the vendor's 1GB minimum — you only pay for 256MB when 256MB is enough.

**The boundary, stated upfront**: self-hosting ≠ free. You give up the 99.95% SLA in exchange for: the cache node dying without taking your app with it (fail-open), data on R2 ($0 egress), and zero vendor price-hike or sunset risk.

## 2. Why one process covers cache + queue + counters

Valkey is a single-threaded event loop with multi-core I/O threads (8.x) where everything hot lives in RAM:

| Use case | Commands | Typical scenario |
|------|------|------|
| Session/API cache | SET/GET/EXPIRE | API response cache, login sessions |
| Rate-limit counters | INCR/EXPIRE | Per-second token buckets, daily quotas |
| Short queues | LPUSH/RPOP | Async task buffering (non-durable) |
| Leaderboards / hot sets | ZADD/ZRANGE | Real-time rankings, Top-N |

Key design points:

- **Memory is the ceiling**: `maxmemory` set hard + `maxmemory-policy allkeys-lru` — when full, the least-recently-used keys are evicted automatically, and the process memory never crosses the line;
- **Dual persistence**: RDB (snapshots) + AOF (`aof-use-rdb-preamble`, default in 8.x — AOF starts from an RDB preamble, roughly halving size and speeding up rebuilds);
- **No sidecars**: no external database or service registry; one ~30MB binary, ~30-50MB idle, coexisting with nginx/systemd on 1C1G with zero pressure;
- **Zero client changes**: `redis://` protocol fully compatible — only the connection string moves.

## 3. Architecture: three roles on one VPS

```
 [App / API / cron jobs]
        │  redis:// (private: Tailscale/SSH tunnel only; 6379 never public)
        ▼
 ┌─────────────────────────┐
 │  Valkey (1 process)     │
 │  maxmemory 256MB        │
 │  allkeys-lru            │
 │  RDB + AOF (RDB prefix) │
 └────┬───────────────┬────┘
      │ INFO memory   │ dump.rdb + appendonlydir/
      ▼               ▼
 [Prometheus textfile]  [restic nightly -> R2 ($0 egress)]
 [Kuma TCP probe]      [7 generations kept, off-site restore point]
```

Key points:

- **6379 is never directly public**: local apps connect to `127.0.0.1:6379`; remote access via Tailscale private mesh (see [Tailscale zero-config remote access](/post/vps-tailscale-zero-config-remote-access/)) or SSH tunnels — the debug surface never runs naked;
- **Persistence lands on R2**: RDB snapshots every 6 hours (`save 60 1000` + hourly dumps), restic nightly backs up `dump.rdb` + `appendonlydir/` to Cloudflare R2 with $0 egress, 7 generations kept;
- **Monitoring via Prometheus**: pull `INFO` for `used_memory`, `evicted_keys`, `aof_last_write_status` into a textfile; 3 alerts (section 5).

## 4. Deployment: systemd + cgroup hardening

### 1. Install (Debian/Ubuntu 22.04+)

```bash
# Official repo
curl -fsSL https://packages.valkey.io/valkey.asc | gpg --dearmor -o /usr/share/keyrings/valkey.gpg
echo "deb [signed-by=/usr/share/keyrings/valkey.gpg] https://packages.valkey.io/1.0/$(. /etc/os-release && echo $VERSION_CODENAME) main" \
  > /etc/apt/sources.list.d/valkey.list
apt update && apt install -y valkey valkey-tools
valkey-server --version   # 8.x
```

(On Alpine / bare metal: download the official `valkey-8.x-linux-amd64.tar.gz` binary, extract, run — no dependencies.)

### 2. Config `/etc/valkey/valkey.conf`

```conf
# Network: loopback only; remote access via Tailscale/SSH tunnel
bind 127.0.0.1 -::*
port 6379
protected-mode yes

# Auth: password even on loopback (defense against container escape / local LPE chains)
requirepass 'your-strong-password'

# Memory ceiling (1C1G box)
maxmemory 256mb
maxmemory-policy allkeys-lru

# Persistence
save 60 1000
save 300 100
aof-use-rdb-preamble yes
auto-aof-rewrite-percentage 100
auto-aof-rewrite-min-size 64mb
appendfsync everysec

# Misc
tcp-keepalive 60
notify-keyspace-events Ex   # key-expired events, optional
```

### 3. systemd unit (hard cgroup limits)

`/etc/systemd/system/valkey.service`:

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
# Memory hard cap: when exceeded, OOM kills Valkey first, not its neighbors
MemoryMax=400M
MemoryHigh=320M
CPUQuota=90%
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable --now valkey
```

Why `MemoryMax=400M`: Valkey's `maxmemory=256mb` is a soft cap (eviction policy); systemd's 400M is a hard cap (cgroup kill). Two layers of insurance — on a 1GB VPS, nginx, systemd, and your monitoring scripts always survive.

### 4. Remote access (pick one)

- **Tailscale** (recommended): add the VPS as a node, clients use `redis://100.x.y.z:6379` — zero exposed ports;
- **SSH tunnel**: `ssh -L 6380:127.0.0.1:6379 vps`, local `redis://localhost:6380`;
- **Cloudflare Tunnel**: management plane only (valkey-cli / debugging); production client traffic never routes through CF (extra hop of latency).

## 5. Monitoring & recovery

### Prometheus scrape (every 5 minutes)

```bash
#!/usr/bin/env bash
# /usr/local/bin/valkey-metrics.sh
OUT=/var/lib/prometheus/node_exporter_textfile/valkey.prom
valkey-cli -a "$PW" INFO memory > /tmp/vm 2>/dev/null
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

Run via a systemd timer every 5 minutes; Grafana/Kuma side, 3 alerts:

| Alert | Condition | Severity |
|------|------|------|
| Memory near the line | `valkey_used_bytes > 90% × 256MB` | warning (evictions starting — find the memory hog) |
| AOF write failed | `valkey_aof_write_ok == 0` | critical (disk full / IO anomaly) |
| Client buildup | `valkey_connected_clients > 100` | warning (connection leak or client stampede) |

### Off-site recovery drill (monthly)

```bash
# R2 -> scratch dir -> verify -> load
restic -r $R2_REPO restore latest -t /tmp/valkey-restore
# Temporary instance on 6399 for the drill; production 6379 untouched
valkey-server --port 6399 --daemonize yes --dir /tmp/valkey-restore --dbfilename dump.rdb
valkey-cli -p 6399 DBSIZE   # cross-check against INFO persistence's last_key...
```

Expected recovery time: a 256MB RDB pulled from R2 over 50Mbps + load finishes in under 30 seconds.

## 6. Measured expectations (1C1G VPS)

| Metric | Value |
|------|------|
| Idle memory | ~30-50MB (+ 256MB cache pool ≈ 300MB ceiling) |
| GET/SET, single client | ~50-80k ops/s (3-5× more pipelined) |
| Rate-limit counters (INCR+EXPIRE) | 100k+/s, single-core CPU < 15% |
| RDB 256MB snapshot | ~1-3s, IO spike < 5s |
| AOF daily delta (1GB/day writes) | ~200-500MB; R2 storage $0.01-0.02/mo |
| 256MB cache @ 90% hit rate | Upstream QPS ÷10 → DB/LLM upstream costs drop ~90% |

## 7. Five pitfalls

1. **6379 exposed publicly with no auth**: scanners find it within 10 minutes — `INFO` drags the whole database + SSH key planting. Always `bind 127.0.0.1` + requirepass; remote access via Tailscale/tunnel only.
2. **No maxmemory/policy**: on a 1GB box Valkey fills memory → the kernel OOM-kills a random neighbor (nginx, your cron jobs). `allkeys-lru` + `maxmemory` are two red lines; neither is optional.
3. **AOF rewrite IO spikes on burst VPS**: `BGREWRITEAOF` occupies disk IO for minutes and, under small-IOPS quotas, drags every read. Mitigate with `auto-aof-rewrite-min-size 64mb` (longer rewrite intervals) + `aof-use-rdb-preamble` (smaller rewrites), and don't run a full restic upload at the same time on the same box.
4. **Expecting a managed SLA from self-hosting**: when the Valkey node dies, your 99.95% dies with it — the app layer must fail-open (cache miss → straight to origin, 50ms timeout). Never treat Valkey as the source of truth; durable data belongs in PostgreSQL, Valkey is the accelerator.
5. **RDB version drift after upgrades**: a newer Valkey loads an older RDB fine; the reverse (rolling back after a failed upgrade) is rejected outright. Before upgrading: run a `RESTORE` drill + keep the previous binary in restic.

## 8. Hybrid mode (if you're not ready to commit)

- **Dev/staging self-hosted, production managed**: one env-var connection string, same codebase, zero risk during launch;
- **L1 self-hosted + L2 managed**: local Valkey (256MB) as the hot tier, misses fall through to Upstash/managed as the cold tier + burst absorption — managed bill drops to the minimum tier;
- **Migration path**: dual-write for 1 week (new writes go to Valkey, old reads stay on managed) → cut over reads → decommission the managed instance, no downtime the whole way.

---

**Bottom line**: Valkey drives the "managed Redis tax" down to $0-4/mo: a 30MB single binary, a 256MB cache ceiling where vendors force a 1GB minimum (¼ the price × ¼ the footprint — actually cheaper), RDB+AOF nightly to R2 at $0 egress, and a cgroup hard cap that protects the 1C1G neighbors. Three pre-commitments: 6379 never public, maxmemory always set, app always fails open. Do those three and the managed Redis invoice can be deleted.
