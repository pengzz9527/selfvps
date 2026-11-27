---
title: "Postgres Running Out of Connections on a VPS? Pgbouncer Pooling in 30 Minutes"
date: 2026-11-27
tags: ["VPS", "Pgbouncer", "PostgreSQL", "Connection Pooling", "Self-hosting", "Cost Savings", "DevOps"]
draft: false
image: /images/posts/vps-pgbouncer-postgres-connection-pooling/featured.png
description: "Each Postgres connection is a ~10MB process — 80 live connections on a 1C1G VPS means OOM. Pgbouncer (~30MB) serves 100+ app connections with 20 server connections: 30-minute deploy, cgroup hardening, 3 Prometheus alerts, $0-4/mo vs managed PG upgrades ($15-50/mo), saving $180-600/yr. SCRAM auth, transaction-pooling pitfalls included."
---

# Postgres Running Out of Connections on a VPS? Pgbouncer Pooling in 30 Minutes

Postgres uses a process-per-connection model: every client connection gets its own OS process with 8-12MB of resident memory (work_mem, per-query buffers, sockets) plus working memory for active queries. The default `max_connections=200` sounds generous until you run Postgres on a 1C1G VPS — after shared_buffers takes 256-384MB, **60-80 live connections push the box into OOM**, while modern stacks (Node pools of 10-20, Python pools of 5-10, plus CI jobs, monitoring, and backup scripts) easily open 100+.

The classic failure sequence: `FATAL: sorry, too many clients already` → someone cranks `max_connections` up → OOM kills a random process (usually nginx, not Postgres) → "solution": upgrade to managed Postgres at $15-50/mo.

**Pgbouncer** closes that path: one ~30MB process in front of Postgres lets 20 "server connections" serve 100-200 "client connections," collapsing total memory from 800MB-1GB back to ~250MB. Zero marginal cost on a VPS you already pay for, deployed in 30 minutes.

## 1. The cost math: do it before you touch anything

Scenario: Postgres on a 1C1G VPS, ~100 connections across app + cron + monitoring + CI, already throwing `too many clients` or OOM-kills.

| Option | Monthly | Notes |
|------|:---:|------|
| RDS db.t4g.micro (smallest) | $15-25 | 0.5GB RAM, ~$0.0208/hr on-demand, plus I/O + storage |
| DigitalOcean Managed PostgreSQL | $15-30 | 1GB entry tier |
| Supabase (Pro) | $25 | managed, still capped on connections |
| Aiven for PostgreSQL | $35-90 | smallest tier is pricey |
| Upgrade the VPS to 2C4G | +$5-15 | just to fit 80 more connections |
| **Postgres + Pgbouncer @ existing 1C1G** | **$0-4** | problem solved in place, memory goes *down* |

**You save $180-600/yr**, and Pgbouncer pays for itself beyond price: `max_connections` can be pinned to 50-100, Postgres memory becomes predictable, and OOM disappears.

**Be clear about the boundary**: Pgbouncer fixes *connection count*, not connection *quality* — slow queries, lock waits, and `idle in transaction` still eat memory and stall the pool (pitfall 4). It is not an HA component: if Postgres dies, Pgbouncer does not save you. It just stops 100 clients from hand-shaking with 100 Postgres processes simultaneously.

## 2. How it works: three pool modes — pick wrong and it's pointless

| Mode | Behavior | Use when | Memory win |
|------|----------|----------|:---:|
| `session` | client keeps one server connection until disconnect | pool-unfriendly apps (transitional default) | low (queues, no sharing) |
| `transaction` | server connection returns to the pool after each transaction | pool-friendly web apps (target state) | high (100 clients share 20) |
| `stashed` | post-transaction connection is stashed for the original client ~3s, shared if no one else wants it | short transactions + high QPS | medium |

**Transaction mode is the one that actually saves memory**: Postgres sees `pool size` (20) instead of `client count` (100). The cost is that your app must be pool-friendly:

- no session-level `SET` — use `SET LOCAL`;
- no temp tables, no session-level advisory locks (`pg_advisory_lock`; `pg_advisory_xact_lock` is transaction-scoped and fine);
- no `LISTEN`/`NOTIFY`;
- don't reuse named prepared statements (`PREPARE`/`EXECUTE`) across transactions — they're reset by `DISCARD ALL` between them.

Can't do it yet? Run `session` mode first (it still caps Postgres's effective concurrency), migrate apps service-by-service, then flip to `transaction`.

## 3. Architecture: one VPS, one topology

```
 [Web app ×100 conns] [CI/scripts ×10] [monitoring ×5]
        │                   │            │
        ▼                   ▼            ▼
 ┌────────────────────────────────────────────┐
 │  Pgbouncer (127.0.0.1:6432)  ~30MB        │
 │  pool_mode=transaction                     │
 │  max_client_conn=200 / pool=20 (+4 resv)  │
 │  SCRAM-SHA-256 auth                        │
 └──────────────────┬─────────────────────────┘
                    │ 20-24 server connections
                    ▼
        PostgreSQL (127.0.0.1:5432)
        max_connections=50 (pinned, never raised)
                    │
                    ▼
        SHOW STATS → Prometheus textfile
                    → 3 alerts (pool full / waiting / conn pileup)
```

Key points:

- **Pgbouncer listens on loopback only**; remote access goes through Tailscale/SSH tunnel (see [Tailscale zero-config remote access](/post/vps-tailscale-zero-config-remote-access/)) — 6432 never faces the public internet;
- **Postgres `max_connections` gets tightened** to 50-100; pool size = `max_connections - 10` (reserve 10 for psql debugging, backups, monitoring);
- **Monitoring via Prometheus textfile**: one `SHOW STATS` command, every 5 minutes, 3 alerts (section 5).

## 4. Deployment: 30 minutes (Debian/Ubuntu)

### 1. Install

```bash
apt update && apt install -y pgbouncer
pgbouncer --version   # Debian 12 / Ubuntu 22.04: 1.19-1.21
```

### 2. Configure `/etc/pgbouncer/pgbouncer.ini`

```ini
[pgbouncer]
listen = 127.0.0.1:6432          # loopback only
admin_users = pgbouncer         # admin console limited to pgbouncer account
auth_type = scram-sha-256        # PG14+ default
auth_file = /etc/pgbouncer/userlist.txt
pool_mode = transaction          # target for pool-friendly apps
max_client_conn = 200            # client cap (each ~48KB-1MB of buffers)
default_pool_size = 20           # server pool per db/user
reserved_pool_size = 4           # overflow slots for high-priority clients
reserved_pool_timeout = 3
client_idle_timeout = 600        # drop idle clients after 10m, stops leak pinning
log_connections = 1              # on while debugging, off at steady state
# Admin console: log into the main 6432 port as pgbouncer (SHOW POOLS/STATS),
# no separate listener needed

[databases]
appdb = host=/var/run/postgresql port=5432 dbname=appdb
```

### 3. Auth: reuse Postgres's SCRAM verifier in userlist.txt

Pgbouncer never needs plaintext passwords — export the SCRAM verifier Postgres already stores:

```sql
-- as postgres superuser
SELECT rolname, rolpassword FROM pg_authid WHERE rolname = 'app';
-- looks like: {SCRAM-SHA-256$4096:xxxxxxxx:yyyy$zzzz...}
```

Write `/etc/pgbouncer/userlist.txt` (**quotes are mandatory** — PG13+ verifiers contain `:` and `$`):

```
"app" "{SCRAM-SHA-256$4096:xxxxxxxx:yyyy$zzzz...}"
"pgbouncer" "scram-sha-256$<salt>$<StoredKey>:<ServerKey>"
```

For the `pgbouncer` admin user, generate a SCRAM verifier (or use the `pgbouncer` tool's hashing mode). Lock it down: `chmod 640 /etc/pgbouncer/userlist.txt && chown pgbouncer:pgbouncer`.

### 4. systemd + cgroup hardening

The distro ships `pgbouncer.service`; add a cgroup hard cap (Pgbouncer itself is ~30-50MB, 64M is plenty):

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

### 5. Switch clients (zero code changes)

Point the connection string from `host=127.0.0.1 port=5432` to `host=127.0.0.1 port=6432`; username and password are unchanged. If it's in an env/config center, that's a one-line change.

### 6. Verify

```bash
psql -h 127.0.0.1 -p 6432 -U pgbouncer appdb -c "SHOW POOLS;"
psql -h 127.0.0.1 -p 6432 -U pgbouncer appdb -c "SHOW CLIENTS;"
psql -h 127.0.0.1 -p 6432 -U app appdb -c "SELECT 1;"    # app user through the pool
```

`SHOW SERVERS` should show at most 24 entries (20 pool + 4 reserved) while `SHOW CLIENTS` can be 100+.

## 5. Monitoring and alerts

`SHOW STATS` is the ready-made pool metrics source (`cl_active`/`cl_waiting`/`sv_used`/`sv_max`/`wait_count`/`wait_avg`), scraped to a Prometheus textfile every 5 minutes:

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

systemd timer, every 5 minutes; Grafana/Kuma run 3 alerts:

| Alert | Condition | Severity |
|------|-----------|----------|
| Pool exhaustion | `pgbouncer_server_connections_used == pgbouncer_server_connections_max` for 2 consecutive scrapes | critical (`wait_count` climbs; find stuck connections in `SHOW SERVERS`) |
| Client queueing | `pgbouncer_clients_waiting > 5` sustained 5 min | warning (pool too small or slow queries pinning slots; check `pg_stat_activity`) |
| Client pileup | `pgbouncer_client_connections_active > 80% × max_client_conn` | warning (leak or abuse; verify `client_idle_timeout` is doing its job) |

Add a Kuma TCP probe on `127.0.0.1:6432` (from a Tailscale node) so the single point of failure reports within 30s.

## 6. What to expect on 1C1G (measured baseline)

| Metric | Value |
|------|------|
| Pgbouncer idle memory | ~8-12MB; full load (200 clients + 24 pool) ~30-50MB |
| Per-query forwarding overhead | session mode <0.1ms; transaction mode 0.1-0.5ms |
| Memory math (100-conn scenario) | unpooled: 100 × 10MB ≈ 1GB → OOM; pooled: 24 × 10MB ≈ 240MB + Pgbouncer 40MB — saves ~800MB |
| Throughput | simple CRUD sustains 10k-50k QPS with pool=20; Pgbouncer at 30-50% of one core |
| Cutover time | change the port, restart app, < 5 min; zero data migration |

## 7. Five hard-won pitfalls

1. **Transaction pooling + session-state apps fail silently**: `SET` (non-LOCAL), temp tables, session-level `pg_advisory_lock`, `LISTEN`/`NOTIFY`, and named prepared statements reused across transactions all misbehave under `transaction` mode — and the errors only appear on some requests, which makes them brutal to reproduce. Run `session` mode during the transition; verify the switch by watching `sv_used` fall back to 1-5 at idle.
2. **Pool too large = OOM by other means**: `default_pool_size=100` on a 1GB box is 100 × 10MB = 1GB of server-connection memory, exactly as dead as running Postgres bare. Pin the formula: **`pool × 10MB + shared_buffers ≤ 60% of total RAM`**. If the pool is too small, profile slow queries before adding slots.
3. **SCRAM/MD5 verifier mismatch**: PG16 defaults to `password_encryption=scram-sha-256`; an old MD5 userlist (or the reverse) causes a login death loop (`no matching sasl mechanism` / `password auth failed`). After any Postgres `password_encryption` change or password reset, **re-export the verifier from `pg_authid` and rewrite userlist.txt**, then smoke-test with `psql -p 6432 -U app`.
4. **`idle in transaction` leaks pin server connections forever**: an app bug that starts a transaction and never commits holds that server connection indefinitely under transaction mode; once `sv_active` pins the pool, every client sits in `cl_waiting`. Pgbouncer won't kill it for you — find the entry with a huge `active_for` in `SHOW SERVERS`, then terminate the matching `pg_stat_activity` row; long-term, add statement/transaction timeouts and alert on `sv_active`.
5. **Pgbouncer is a single point of failure, and its admin surface is not free**: it provides zero HA — when Postgres dies, all 100 clients hang in the pool until `server_connect_timeout`; the admin console shares the business port, so anyone with a weak Pgbouncer password can `SHOW POOLS/CLIENTS` and map the whole topology. Countermeasures: `Restart=on-failure` + Kuma TCP probe for self-survival; unique strong password for `pgbouncer`; 6432 reachable via loopback/Tailscale only.

## 8. Managed mode (if self-hosted feels risky)

- **RDS/Aurora built-in PgBouncer, $0**: on Aurora enable the "Pgbouncer" option (port 9997, `pool_mode=transaction`); on RDS add pgbouncer parameters to a custom Parameter Group. Managed DB + built-in pool = connection ceiling without a tier upgrade; keep a self-hosted Pgbouncer as the cold-standby plan;
- **Supabase/Neon**: Neon's connection ceiling scales by plan (50-250); funnel all clients through one pool (Neon's built-in pooler, or your own Pgbouncer in front) in `transaction` mode to stretch 250 to an effective 1000+;
- **Migration path**: switch apps to self-hosted Pgbouncer (`session` mode) → make each service pool-friendly → flip to `transaction` → tighten `max_connections` from 200 to 50 → watch `sv_used`/`wait_count` for 2 weeks before deleting the upgrade plan. Zero downtime throughout.

---

**Bottom line**: on a 1C1G VPS, Postgres connection exhaustion is not an if — it's a when. The fix is not "bigger database"; it's a $0, 30MB process. Pgbouncer holds 100+ app connections with 20 server connections, memory drops from ~1GB to ~300MB, and `max_connections` gets pinned at 50-100. Three pre-flight rules: loopback-only listener, the pool formula (`pool × 10MB + shared_buffers ≤ 60% RAM`), and pool-friendliness cleanup before `transaction` mode. Follow those and the managed-Postgres invoice can be cancelled.
