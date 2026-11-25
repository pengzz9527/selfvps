---
title: "Self-Host Meilisearch on a VPS: Replace Algolia for $0/mo"
date: 2026-11-25
tags: ["VPS", "Meilisearch", "Algolia", "Search", "Self-Hosted", "Cloud Savings", "Ops"]
draft: false
image: /images/posts/vps-meilisearch-selfhosted-algolia-replacement/featured.png
description: "Meilisearch (Rust engine, AGPL-3.0, v1.57) is a single binary: typo-tolerant search + faceted filtering + ranking rules in one. Cap indexing memory at 256MB + a 512M cgroup hard cap on a 1C1G VPS; daily --schedule-snapshot snapshots restic'd to R2 ($0 egress) with a monthly --import-snapshot drill; ship only a read-only search key to the frontend. $0-5/mo instead of Algolia Grow ($15-126/mo on typical sites), saving $180-1,500/yr. Includes hardened systemd, monitoring, and 5 pitfalls."
---

# Self-Host Meilisearch on a VPS: Replace Algolia for $0/mo

Search is one of the fastest-growing "hidden bills" in a stack: Algolia prices by search requests + record count, so an un-throttled SaaS app hitting 180K searches a month costs $85+, and a mid-size store with 240K records and 150K searches runs $126+/mo. In 90% of cases the workload is just "site search + docs search + product search" — plain keyword retrieval. Move that to Meilisearch on a 1C1G VPS and the search volume stops being metered: the bill drops to $0-5/mo flat.

**Meilisearch** is an open-source (AGPL-3.0) search engine written in Rust: LMDB store, single binary, no external dependencies. Built-in typo-tolerance ("seach" still finds "search"), faceted filtering, configurable ranking rules, and a REST API you can wire up in five minutes. Current version is **v1.57** (released 2026-11-16), on the stable 1.x line.

**Why not Elasticsearch/OpenSearch instead**: the ES stack (JVM + cluster protocol + ILM) cannot run on 1C1G and is operationally heavy. Meilisearch is a single process, ~50-100MB idle memory, a ~350MB download that extracts and runs — for "site search" scale it is the best tool in the box. Reconsider ES or managed services only above ~1M documents.

## 1. The cost math before you start

Scenario: a SaaS/store site needs 100-500K records and 50-180K searches/month, currently on Algolia (Oct 2026 pricing).

| Option | Monthly | Searches | Records | Notes |
|------|:---:|:---:|:---:|------|
| Algolia Free | $0 | 10K | 50K | upgrade when exceeded |
| Algolia Grow (docs site: 20K records + 40K searches) | ~$15 | 10K incl. | 100K | overage $0.50/1K req, $0.40/1K rec |
| Algolia Grow (SaaS: 50K records + 180K searches, no debounce) | ~$85 | 10K incl. | 100K | un-throttled search volume burns cash |
| Algolia Grow (mid store: 240K records + 150K searches) | ~$126 | 10K incl. | 100K | records overage $0.40/1K |
| Algolia Grow Plus (AI ranking) | ~$297 | 10K incl. | 100K | overage $1.75/1K req |
| **Meilisearch @ 1C1G VPS** | **$0-5** | **unlimited** | **unlimited** | $0 if the VPS exists; $3-5 for a new machine |

**Save $180-1,500/yr** on a typical site; $1,500-4,300/yr for the mid store. Search requests no longer being metered means traffic spikes (launch campaigns, viral backlinks) no longer produce bill spikes.

**Honest boundaries**: self-hosting ≠ free. You give up the vendor's 99.99% SLA and AI ranking (NeuralSearch); you get unmetered search volume, data on R2 ($0 egress), and no vendor metering-runaway risk. Search outages don't break checkout — degrade the app layer to a `LIKE` query (fail-open).

**AGPL note**: self-hosting and not forking the engine = zero obligation. Modifying Meilisearch source and offering it as a service requires open-sourcing your modifications.

## 2. Why a single process handles site search

Core architecture: LMDB memory-mapped index + async task queue (all writes are enqueued and built in the background):

| Capability | What it does | Algolia counterpart |
|------|------|------|
| Typo tolerance | edit-distance aware (default: 1-char words 1 typo, 2-char 2) | built-in |
| Faceted filters | `facets` field counts + filtering (v1.56 adds `sampledCount` sampling for huge catalogs) | built-in |
| Ranking rules | configurable `rankingRules` (typo → words → proximity → attribute → customRank → criteria) | partly in AI plans |
| Fuzzy + exact mix | `filter` + `q` combination, facet distribution limits | built-in |
| Async writes | POST returns task id instantly; index builds in background | metered by write ops |

Key design points:

- **Memory has a red line**: `--max-indexing-memory` defaults to 2/3 of system RAM (on 1GB = 665MB) — on shared VPS you must cap it explicitly (see deployment); `--experimental-reduce-indexing-memory-usage` (LMDB WRITEMAP) lowers resident memory further;
- **Disk is the limit**: index data + task DB + snapshots all live in the data dir; 100K docs ≈ 200-400MB, trivial on a 10-20GB VPS disk;
- **Search doesn't hog indexing threads**: `--max-indexing-threads` defaults to half of available cores — but **on a single core, indexing can only steal that one core**: search latency spikes during indexing windows (documented behavior); schedule heavy indexes off-peak;
- **Key layering**: master key stays server-side; the frontend gets one read-only search key (scoped to specific indexes + the `search` action).

## 3. Architecture: four roles on one VPS

```
 [frontend JS / API / crawler indexer]
        │  HTTPS (443, read-only search key only)
        ▼
 [Caddy/Nginx reverse proxy]
        │  127.0.0.1:7700 + Authorization: Bearer ***
        ▼
 ┌─────────────────────────┐
 │  Meilisearch (1 process)│
 │  --env production        │
 │  max-indexing-memory 256M│
 │  cgroup hard cap 512M    │
 └────┬───────────────┬────┘
      │ /stats /tasks │ snapshots/ (daily 24h)
      ▼               ▼
 [Prometheus /metrics]  [restic nightly → R2 ($0 egress)]
 [3 alerts]             [7-gen retention, --import-snapshot restore]
```

Notes:

- **7700 binds to 127.0.0.1 by default** (Meilisearch ships localhost:7700): public surface via Caddy/Traefik reverse proxy + TLS; pure-internal search can go over Tailscale (see [Tailscale Zero-Config Remote Access](/post/vps-tailscale-zero-config-remote-access/));
- **Snapshots to R2**: `--schedule-snapshot` (default every 24h) + nightly restic of `snapshots/` + `data.ms/` to Cloudflare R2, $0 egress, 7-gen retention. Note: direct S3 snapshot uploads are an **Enterprise feature** — the community edition syncs via restic;
- **Monitoring**: `--experimental-enable-metrics` exposes Prometheus `/metrics` (experimental; verify the flag still exists before upgrades); fallback: 5-min cron pulling `/stats` + `/tasks` into a textfile (section 5).

## 4. Deployment: systemd + cgroup hardening

### 1. Install (Debian/Ubuntu 22.04+)

```bash
# Official .deb (v1.57)
curl -fsSL https://downloads.meilisearch.meilisearch.cn/meilisearch.deb -o /tmp/meili.deb
# Or the official static binary from GitHub Releases (~350MB, no deps):
#   meilisearch-linux-amd64 → /usr/local/bin/meilisearch
dpkg -i /tmp/meili.deb
meilisearch --version   # v1.57.x
```

(The official .deb installs a systemd unit and a `meilisearch` user; re-enable after overriding the unit.)

### 2. Keys

```bash
mkdir -p /etc/meilisearch
# Master key: >=16 bytes, mandatory in production
openssl rand -hex 32 > /etc/meilisearch/master.key
chmod 600 /etc/meilisearch/master.key

cat > /etc/meilisearch/meilisearch.env <<'EOF'
MEILI_MASTER_KEY=***
MEILI_ENV=production
MEILI_NO_ANALYTICS=1
EOF
chmod 600 /etc/meilisearch/meilisearch.env
```

After startup, mint two API keys with the master key (shown once only — store them):

```bash
curl -s -XPOST 'http://127.0.0.1:7700/keys' \
  -H "Authorization: Bearer $(cat /etc/meilisearch/master.key)" \
  -H 'Content-Type: application/json' -d '{
  "description": "public read-only search key (ship to frontend)",
  "actions": ["search", "query"],
  "indexes": ["docs", "products"],
  "expiresAt": null
}'
```

- **Public search key**: read-only, index-scoped — safe to hardcode in frontend JS; a leak exposes only search, not data;
- **Admin key** (`actions: ["*"]`): server-side + Tailscale/SSH tunnel only; all writes go through it.

### 3. systemd unit (cgroup hard caps)

`/etc/systemd/system/meilisearch.service` (overriding the [Service] section of the stock unit):

```ini
[Unit]
Description=Meilisearch search engine
After=network.target

[Service]
User=meilisearch
Group=meilisearch
EnvironmentFile=/etc/meilisearch/meilisearch.env
ExecStart=/usr/local/bin/meilisearch \
  --db-path /var/lib/meilisearch/data.ms \
  --http-addr 127.0.0.1:7700 \
  --max-indexing-memory 256mb \
  --experimental-reduce-indexing-memory-usage \
  --schedule-snapshot \
  --snapshot-dir /var/lib/meilisearch/snapshots \
  --no-analytics
Restart=on-failure
RestartSec=2
# Memory hard cap: on a 1GB box, 512M so OOM kills Meilisearch, not neighbors
MemoryMax=512M
MemoryHigh=448M
CPUQuota=150%
LimitNOFILE=65536
# Snapshot temp staging (full copy) → point at the data disk to avoid filling /tmp
Environment=TMPDIR=/var/lib/meilisearch/tmp

[Install]
WantedBy=multi-user.target
```

```bash
mkdir -p /var/lib/meilisearch/tmp
systemctl daemon-reload && systemctl enable --now meilisearch
systemctl status meilisearch
```

`--max-indexing-memory 256mb` + `MemoryMax=512M` is a two-layer guardrail: Meilisearch's cap is soft (indexing backpressures on overflow), the cgroup cap is hard (OOM-kills the process) — guarantees nginx, systemd and cron survive a full re-index on a 1C1G box. `--experimental-reduce-indexing-memory-usage` (LMDB WRITEMAP) further lowers resident memory on UNIX, trading a little write speed — a good trade on small VPS.

### 4. Public surface (Caddy reverse proxy)

```
search.example.com {
    reverse_proxy 127.0.0.1:7700
    header -Server
    request_header Authorization "Bearer meili_public_search_key_xxx"  # demo only; production uses the frontend's own key
}
```

Frontend calls `https://search.example.com/indexes/docs/search?q=...` with the read-only key; the admin surface stays unexposed.

## 5. Search API in practice

```bash
MEILI=http://127.0.0.1:7700
AUTH="Authorization: Bearer $(cat /etc/meilisearch/master.key)"

# 1. Create index
curl -s -XPOST "$MEILI/indexes" -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"uid":"docs","primaryKey":"slug"}'

# 2. Push documents (100K in batches of 1000, async tasks)
curl -s -XPOST "$MEILI/indexes/docs/documents" -H "$AUTH" -H 'Content-Type: application/json' \
  -d @docs_batch.json
# → {"taskUid": 123, ...}  GET /tasks/123 for status

# 3. Tune search behavior
curl -s -XPATCH "$MEILI/indexes/docs/settings" -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{
    "searchableAttributes": ["title","body","tags"],
    "filterableAttributes": ["tags","category"],
    "typoTolerance": {"minTwoTypos": 1, "minOneTypos": 2},
    "rankingRules": ["typo","words","proximity","attribute","criteria"]
  }'

# 4. Search (frontend uses the read-only key)
curl -s "$MEILI/indexes/docs/search?q=seach&filter=tags:backup&limit=10" \
  -H "Authorization: Bearer ***"
# "seach" typo still hits
```

**Nightly full re-index (off-peak; on a single core, search slows during the indexing window)**:

```bash
#!/usr/bin/env bash
# /usr/local/bin/meili-reindex.sh  run at 02:30
curl -s -XPOST "$MEILI/indexes/docs/documents/delete" -H "$AUTH" -d '{}'
for f in /var/lib/meili-source/docs_*.json; do
  curl -s -XPOST "$MEILI/indexes/docs/documents" -H "$AUTH" -d @"$f"
done
```

Pair with `--task-webhook-url` (NDJSON notification per task completion) to push "full re-index done" to Telegram/Gotify (see [Gotify Self-Hosted Realtime Alerts](/post/vps-gotify-selfhosted-realtime-alerts/)).

## 6. Monitoring and alerting

**Preferred**: add `--experimental-enable-metrics` to the unit; Prometheus scrapes `http://127.0.0.1:7700/metrics` directly (experimental flag — verify it still exists before major upgrades).

**Fallback** (5-min cron → textfile, same pattern as [Valkey monitoring](/post/vps-valkey-selfhosted-redis-replacement/)):

```bash
#!/usr/bin/env bash
# /usr/local/bin/meili-metrics.sh
OUT=/var/lib/prometheus/node_exporter_textfile/meilisearch.prom
AUTH="Authorization: Bearer $(cat /etc/meilisearch/master.key)"
curl -s "$MEILI/stats" -H "$AUTH" > /tmp/ms_stats
curl -s "$MEILI/tasks?limit=1&statuses=fail" -H "$AUTH" > /tmp/ms_fail
curl -s "$MEILI/tasks?limit=1" -H "$AUTH" > /tmp/ms_last
failed=$(jq -r '.total' /tmp/ms_fail)
lag=$(jq -r '.results[0].enqueuedAt // empty' /tmp/ms_last)   # last task's enqueue time
cat > "$OUT" <<EOF
meili_tasks_failed_total $failed
meili_index_size_bytes $(jq '.dbSize' /tmp/ms_stats)
meili_last_task_ts $(date -d "$lag" +%s 2>/dev/null || echo 0)
EOF
```

Three alerts:

| Alert | Condition | Severity |
|------|------|------|
| Index bloat | `meili_index_size_bytes` > 70% of disk watermark (7GB on a 10GB disk) | warning (purge stale data / grow disk / split indexes) |
| Indexing lag | last task enqueued > 10min and still not processed (queue backing up) | warning (source writes too fast / CPU stolen) |
| Task failures | `meili_tasks_failed_total` increasing | critical (payload too big / schema clash / disk full) |

Kuma's `GET /health` (200 = alive, no key needed) covers liveness.

## 7. Backup and restore

Meilisearch 1.x ships a **snapshot mechanism** (cleaner than the old dump approach):

- `--schedule-snapshot`: default every 24h into `--snapshot-dir` (value in seconds, e.g. `--schedule-snapshot 43200` = every 12h);
- `--import-snapshot /path/to/x.snapshot`: import at startup (**errors if the data dir already exists** — wipe `data.ms/` first when restoring);
- Engine upgrades: `--upgrade-db` (dumpless migration; called `--experimental-dumpless-upgrade` before v1.51; **non-atomic** — always snapshot manually first).

Offsite pipeline (restic → R2, same as [restic Automated Backup to S3](/post/vps-restic-automated-backup-s3.md)):

```bash
# Nightly: snapshots + data dir → R2 ($0 egress, 7-gen retention)
restic -r $R2_REPO backup /var/lib/meilisearch
# Monthly drill: R2 → scratch → import on a scratch instance
restic -r $R2_REPO restore latest -t /tmp/meili-restore
systemctl stop meilisearch
rm -rf /var/lib/meilisearch/data.ms
cp /tmp/meili-restore/snapshots/latest.snapshot /tmp/x.snapshot
meilisearch --import-snapshot /tmp/x.snapshot --db-path /var/lib/meilisearch/data.ms &
# After verification, hand back to systemd management
```

Restore expectation: 200-400MB of data, R2 pull + import < 2-4 min on 50Mbps.

## 8. Expected numbers (1C1G VPS, empirical)

| Metric | Value |
|------|------|
| Idle memory | ~50-100MB (+256MB transient indexing buffer) |
| Disk (100K docs + 2 snapshot gens) | ~0.5-1GB |
| Search P50 (100K docs) | ~3-15ms, single core ~500-2000 qps |
| Full index (100K docs, first run) | 1-3 min (single core; search slows during the window) |
| Incremental (1000-doc batches) | seconds, async task queue |
| Snapshot (400MB) | ~5-15s |

Capacity red lines: ≤200K docs on 1C1G; 200K-1M on 1C2G; beyond that, 2C4G or managed search.

## 9. Five pitfalls

1. **Dev mode + public exposure = an unlocked safe**: without `--env production` + a master key, every route is unauthenticated (and default port 7700). Public machines need `--env production`, a ≥16-byte master key, `127.0.0.1` binding, and `--no-analytics`.
2. **The default 2/3-RAM indexing memory is uncapped**: on a 1GB box that's 665MB — one full re-index evicts nginx into OOM. Do the three-piece set: `--max-indexing-memory 256mb` + cgroup `MemoryMax=512M` + WRITEMAP.
3. **"Indexing = lag" on a single core**: indexing and search threads fight for the one core; P99 jumps from 15ms to 200ms+. Schedule full re-indexes at 02:30, push in batches, and just buy 2 cores for big catalogs.
4. **Snapshot staging dir blows up /tmp**: snapshot/upgrade operations first copy the full database to `TMPDIR` (default `/tmp`). On small VPS, `/tmp` often shares the root partition or is tmpfs — 1GB of data can fill it (`No space left`). Set `Environment=TMPDIR=/var/lib/meilisearch/tmp` in the unit, pointing at the data disk.
5. **Dumpless upgrade is non-atomic**: a failed `--upgrade-db` mid-migration can leave a corrupt database. Iron rule: snapshot to R2 manually before bumping the binary; rollback = old binary + `--import-snapshot`.

## 10. Hybrid mode (if you're not confident yet)

- **Self-host in dev, managed in prod**: put the search URL in an env var; staging runs Meilisearch, prod stays on Algolia; switch when stable — zero code changes;
- **L1 self-hosted keyword + L2 managed AI ranking**: Meilisearch carries 95% of traffic (unmetered); route long-tail / NeuralSearch queries to Algolia Grow Plus and pay only for the AI portion;
- **Degrade switch**: if the search endpoint returns 5xx, the frontend automatically falls back to DB `LIKE` + title matching (fail-open) — search outages never block the main business;
- **Migration path**: Algolia → Meilisearch via Algolia's `export` API to JSON, convert the schema, push in; dual-read comparison for a week, then retire the Algolia index — no downtime.

---

**Bottom line**: Meilisearch turns the "search tax" from Algolia's metering into a flat $0-5/mo cost: single binary, P50 3-15ms on 100K docs, unmetered search volume (zero bill on launch-day spikes), daily snapshots + restic→R2 with $0 egress. The four non-negotiables: production mode + master key, cap indexing memory, schedule heavy indexes off-peak, point snapshot staging at the data disk. Do those four and you can delete the Algolia line item.
