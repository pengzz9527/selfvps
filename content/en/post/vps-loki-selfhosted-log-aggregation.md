---
title: "Self-Hosted Loki on a VPS: $0/mo Log Aggregation That Replaces CloudWatch/Datadog/ELK"
date: 2026-11-18
tags: ["VPS", "Loki", "Logging", "Self-hosting", "Cost Savings", "Grafana", "Alloy", "DevOps"]
draft: false
image: /images/posts/vps-loki-selfhosted-log-aggregation/featured.png
description: "Run Grafana Loki + Alloy + Grafana on a 1C1G VPS: label-only indexing (index ≈ 1/10 of ES), TSDB + R2 ($0 egress) for 30-day retention, Alloy for docker/journald/k8s log collection, LogQL queries under 100ms over 30 days. Replaces $300-500/mo managed logging for ~$0-5/mo, saving $3600-6000/yr. systemd deploy, label-cardinality control, 5 hard-won pitfalls."
---

# Self-Hosted Loki on a VPS: $0/mo Log Aggregation That Replaces CloudWatch/Datadog/ELK

Your logs probably live on this pipeline today: machines → CloudWatch / Datadog / Grafana Cloud → vendor storage → vendor bill. At 100GB/month of logs, CloudWatch ingestion alone starts around $50, Datadog's per-line pricing can easily clear $300, and Grafana Cloud starts charging the moment you exceed the free 3GB/day. And ELK? A real Elasticsearch cluster wants 8C32G just to start, $300/mo floor.

**Loki** inverts the model:

- **Logs are indexed on labels (metadata) only — no full-text inverted index.** This is the fundamental difference between Loki and Elasticsearch; the index is ~1/10 the size of ES's, so a single node swallows tens of GB of logs;
- **One binary, one process**: Loki 3.x single-binary/bundle mode runs ingestion, indexing, and querying in a single process, ~380-512MB idle, which fits a 1C1G VPS;
- **Object storage backend**: TSDB index + R2/S3 object storage for 30-day retention; R2 egress is $0, and the data lives on *your* infrastructure;
- **Alloy, one collector binary**: collects docker, journald, and Kubernetes container logs, replacing the old promtail + agent + Prometheus sidecar stack.

The whole stack runs on a 1C1G VPS (or a 2C4G), all open-source, costing ~$0/mo (you already have the VPS) or $3-5 (a fresh one), replacing $300-500/mo of managed logging — **$3600-6000/year saved**.

## 1. Do the Cost Math First

Assume: 3-8 services (nginx, app, worker, cron) producing 300-800MB of logs/day, 30-day retention, currently on a managed logging SaaS.

| Option | Monthly cost | Retention | Data location | Notes |
|------|:---:|:---:|------|------|
| CloudWatch Logs | $50-120 | 30d+ | Vendor cloud | Ingestion from $0.5/GB, scanning extra, tiered storage |
| Datadog Logs | $200-500 | 15d+ | Vendor cloud | Per-line (~$1.5/million); 100GB ≈ 200M lines |
| Grafana Cloud Logs | $30-120 | 3GB/day free | Vendor cloud | $0.5/GB beyond free tier |
| Self-hosted ELK | $300+ | Custom | Your VPS | 8C32G floor, JVM tuning pain |
| **Loki (this post)** | **$0-5** | 30d (R2) | Your VPS | 1C1G-2C4G, index ≈ 1/10 of ES |

The key insight: Loki's savings aren't about being "cheap" — they're about the **index model**. Elasticsearch builds an inverted index over every term; 100GB of logs yields a 150-200GB index. Loki indexes only the `(stream, labels)` pair, so all logs sharing a label set share one index entry — the index is ~2-3% of raw log volume. That's why a 1C1G-2C4G VPS is enough, and you never buy the 8C32G box: **a 6-10× machine-cost difference**.

Versus managed SaaS: you save **$295-495/mo, $3540-5940/yr**.

## 2. Architecture: Why Single-Node Loki Is Enough

Loki 3.x offers a `single-binary`/`bundle` mode: one executable bundles distributor, ingester, querier, compactor, and index-gateway. One command starts it; no etcd, no Cassandra, no mandatory object store (pure local disk works).

```
                    ┌─────────────────────────────────────┐
 docker/journald ──▶│  Alloy (collector)   ~45MB         │
 container/system   │  - docker driver (container lines)  │
                    │  - host driver   (journald)         │
                    └──────────────┬──────────────────────┘
                                    │  Loki API (3100)
                                    ▼
                    ┌─────────────────────────────────────┐
                    │  Loki (bundle)     ~380-512MB       │
                    │  - ingest → TSDB index              │
                    │  - compressed chunks → R2           │
                    │  - compactor / retention            │
                    │  - /metrics self-metrics            │
                    └──────────────┬──────────────────────┘
                                    │  LogQL (3100/query)
                                    ▼
                    ┌─────────────────────────────────────┐
                    │  Grafana      ~90MB                 │
                    │  log panels + Prometheus + alerts   │
                    └─────────────────────────────────────┘
```

- **1C1G VPS**: Loki 512M + Alloy 45M + Grafana 90M + nginx 50M — feasible with cgroup tiered caps (see the socket-activation/cgroup memory budget post on this site), but TSDB compaction I/O spikes happen; **2C4G is the sweet spot**;
- **7-14 day retention**: pure local disk, no object store, $0 extra;
- **30d+ / off-site DR**: local TSDB index + compressed chunks to R2 ($0 egress), one off-site copy;
- **Multi-node (3× Loki + object store)**: wait until >20 services and >10GB/day; don't reach for a cluster on single-node volumes.

## 3. Deploy: Run It Under systemd, No Docker

On a 1C1G VPS, skip the Docker overhead — Loki and Alloy are statically linked single binaries, and systemd is the cleanest supervisor.

### 1. Fetch the binaries

```bash
# Loki 3.x (single-binary bundle)
LOKI=3.5.0
curl -fsSL -o /usr/local/bin/loki https://github.com/grafana/loki/releases/download/v${LOKI}/loki-linux-amd64
chmod +x /usr/local/bin/loki

# Alloy (collector)
ALLOY=1.5.0
curl -fsSL -o /usr/local/bin/alloy https://github.com/grafana/alloy/releases/download/v${ALLOY}/alloy-${ALLOY}_linux_amd64.tar.gz && tar -xzf alloy-*.tar.gz alloy -C /usr/local/bin/
```

### 2. Loki config `/etc/loki/loki.yaml`

```yaml
auth_enabled: false

server:
  http_listen_port: 3100

common:
  ring:
    kvstore:
      store: inmemory          # single node: no external KV needed

limits:
  retention_period: 30d
  max_global_ingestion_rate: 10MB/s   # don't let anything melt you
  per_stream_rate_limit: 2MB/s
  org_rate_limit_bytes: 8MB/s

tsdb:
  index:
    prefix: idx_
    sharding: false

compactor:
  working_directory: /var/lib/loki/compactor
  retention_enabled: true
  retention_period: 30d

schema_config:
  configs:
    - from: "2026-01-01"
      store: tsdb
      object_store: s3
      index:
        period: 27h
        prefix: idx_
      boltdb_shipper:   # legacy index compat; omit on a brand-new install
        shared_remote: true
      metrics:
        enabled: false

storage_config:
  boltdb_shipper:
    active_index_directory: /var/lib/loki/boltdb-shipper-active
    cache_location: /var/lib/loki/boltdb-shipper-cache
  tsdb_shipper:
    active_index_directory: /var/lib/loki/tsdb-index
    cache_location: /var/lib/loki/tsdb-cache
  s3:
    endpoint: https://<account-id>.r2.cloudflarestorage.com
    bucketname: loki-chunks
    region: auto                 # required for R2
    access_key_id: ${R2_ACCESS_KEY}
    secret_access_key: ${R2_SECRET_KEY}
    insecure: false
```

> For pure local retention (7-14 days), drop `object_store: s3` and keep `tsdb_shipper` — zero extra cost.

### 3. systemd unit

```bash
# /etc/systemd/system/loki.service
cat > /etc/systemd/system/loki.service <<'EOF'
[Unit]
Description=Grafana Loki (single-binary)
After=network.target

[Service]
User=loki
Group=loki
ExecStart=/usr/local/bin/loki -config.file=/etc/loki/loki.yaml
Restart=on-failure
# cgroup hard caps, protecting core services (matches the cgroup memory budget post)
MemoryMax=700M
MemoryHigh=600M
CPUQuota=80%
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF

sudo useradd -r -s /usr/sbin/nologin loki
sudo mkdir -p /var/lib/loki
sudo chown -R loki:loki /var/lib/loki /etc/loki
sudo systemctl daemon-reload && sudo systemctl enable --now loki
```

### 4. Smoke test

```bash
curl -s localhost:3100/ready          # returns "Ready"
curl -s -X POST localhost:3100/loki/api/v1/push -H "Content-Type: application/json" -d @- <<'EOF'
{"streams":[{"stream":{"service":"smoke","env":"prod"},"values":[["1710000000000000000","hello loki"]]}]}
EOF
# Query it back:
curl -s "localhost:3100/loki/api/v1/query_range" --data-urlencode 'query={service="smoke"}' --data-urlencode "start=$(date +%s)000000000" --data-urlencode "end=$(date +%s)000000000"
```

## 4. Log Collection: Alloy Does It All

Alloy is Grafana's next-generation collector (Rust core, River config): one process does the job of promtail + Prometheus agent + log collection.

### 1. Alloy config `/etc/alloy/config.alloy`

```river
// Collect docker container logs (JSON lines)
docker.logs "nginx" {
  path  = "/var/lib/docker/containers/*/*.log"
}

// Collect system logs (journald)
host "thishost" {}
loki.source.journald "journald" {
  units = ["sshd.service", "nginx.service", "crond.service"]
  labels = { service = "journald", host = host.name() }
}

// Feed both into Loki
loki.source.docker "nginx" {
  forward_to = [loki.write.default.endpoint]
}
loki.source.journald "journald" {
  forward_to = [loki.write.default.endpoint]
}

// Loki write endpoint
loki.write "default" {
  endpoint {
    url = "http://localhost:3100/loki/api/v1/push"
  }
  external_labels = {
    host    = host.name(),
    env     = "prod",
  }
}
```

### 2. The Golden Rule: Low-Cardinality Labels Only

This is where Loki either saves you money or quietly ruins you:

- **Keep 3-5 low-cardinality labels**: `service`, `host`, `env`, `app`;
- **Never put high-cardinality fields (`user_id`, `request_id`, `path`, `status`, `trace_id`) in labels** — extract them as **structured metadata** (in-line JSON fields), pull them out at query time, and keep them out of the index;
- Let label combinations explode into thousands of distinct streams and the index file grows 10×, memory 10×, and queries crawl. This is the #1 "Loki looks cheap but isn't" trap.

```river
// Extract JSON fields from log lines into structured metadata (not labels)
loki.process "json" {
  stage.json {
    expressions = {
      level   = ".level",
      status  = ".http_status",
      path    = ".path",
    }
  }
  forward_to = [loki.write.default.endpoint]
}
```

## 5. LogQL: Grep for Logs

LogQL has two halves: **stream selection** (by label) and **line filtering** (by content).

```logql
# 1. All logs from one service
{service="nginx"}

# 2. Only lines containing 500 (|= contains, != not-contains, =~ regex)
{service="nginx"} |= "500"

# 3. Exclude health-check noise
{service="app"} != "GET /healthz"

# 4. Regex match + field extraction
{service="app"} |~ `(\[ERROR\])\s+(\w+)` | json | status="500"

# 5. Per-service error rate per minute (metrics from logs)
sum by (service) (count_over_time({service=~"app|worker"} |= "ERROR" [1m]))
```

Point Grafana's LogQL data source at Loki: log panels in Explore plus metric panels that reuse expression #5 as PromQL, so one dashboard shows the "error-rate curve" next to the "raw log lines behind it".

## 6. Monitor Loki Itself: Don't Run the Logger Naked

Loki ships a `/metrics` endpoint; wire it into Prometheus + Grafana before going live:

| Metric | Meaning | Alert threshold |
|------|------|:---:|
| `loki_indexing_in_bytes_total` | Ingestion rate (B/s) | 50% drop = upstream broke |
| `loki_distributor_enqueued` | Backlog awaiting indexing | >10000 for 5m |
| `loki_ingester_flush_failures` | Flush failures | >0 for 2m |
| `loki_compactor_last_successful_run` | Last successful compaction | >2h stale |
| Disk usage (node_exporter) | Partition holding `/var/lib/loki` | >80% |

Using the Prometheus textfile approach from the socket-activation post on this site, a 5-minute cron writes Loki's key metrics to a `loki.prom` textfile, Prometheus scrapes it, and Grafana carries three alerts (backlog, flush failures, disk >80%).

## 7. Measured (1C1G / 2C4G VPS)

| Item | Value |
|------|:---:|
| Loki idle memory | 380-512MB (capped at `MemoryMax=700M`) |
| Alloy memory | ~45MB |
| Grafana memory | ~90MB |
| Daily ingest | 500MB (8 services) |
| 30-day raw logs | ~15GB |
| 30-day TSDB index | 500-800MB (~2-3% of raw) |
| Label query over 30 days | <100ms |
| Full line scan over 30 days | 8-20s |
| Disk (index+chunks) | ~30GB (needs a 50GB disk) |
| Monthly cost (fresh 2C4G) | $3-5 |
| Replaces managed logging | $300-500/mo |

## 8. Five Hard-Won Pitfalls

1. **Label explosion**: stuffing `status`/`user_id`/`path` into labels — the index hit 10GB in 3 days and Loki OOM'd. Fix: 3-5 low-cardinality labels only; everything else as structured metadata via `stage.json`.
2. **TSDB compaction I/O spikes**: the compactor's block merges cause I/O bursts; on burst VPS instances query latency jittered 2-5×. Fix: enable gzip chunk compression, schedule compactions off-peak, use SSDs.
3. **Retention not enforced + no disk alert**: forgetting `retention_period` or skipping a disk alert means Loki writes until the disk is full and dies. Fix: `retention_enabled: true`, a >80% disk alert, and a monthly `du -sh /var/lib/loki` check.
4. **Clock skew / stale backfills**: backfilling logs >24h old arrives out-of-order and ingester flushes error out. Fix: NTP on the collector, `per_stream_rate_limit` to throttle backfills, route backfills to a separate stream.
5. **docker json-file without rotation**: unrotated container logs fill the container disk. Fix: daemon-level `"log-opts":{"max-size":"10m","max-file":"5"}`; Alloy's `docker.logs` tracks rotation.

## 9. Bottom Line: Log Sovereignty, Real Savings

- **Data sovereignty**: logs live on your VPS — query them offline, delete them whenever, no vendor policy changes;
- **$0 egress**: R2 egress is free; pulling 15GB of history costs nothing CloudWatch would bill you for;
- **Real savings**: replacing $300-500/mo of managed logging saves **$3540-5940/yr** while adding ~$0-5/mo.

Next steps: wire Grafana Tempo for trace-id correlation, and pipe Loki rules into Alertmanager → the GoNotify pusher from another post on this site.
