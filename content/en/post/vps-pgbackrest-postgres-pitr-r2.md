---
title: "PostgreSQL PITR on a 1C1G VPS: pgBackRest + Cloudflare R2 for Second-Level Rollback"
date: 2026-11-16
tags: ["VPS", "PostgreSQL", "pgBackRest", "PITR", "Backup", "Cloudflare R2", "DevOps"]
draft: false
image: /images/posts/vps-pgbackrest-postgres-pitr-r2/featured.png
description: "Nightly pg_dump can't save your 9am data: use pgBackRest to continuously archive WAL to Cloudflare R2 (zero egress), with incremental backup chains and a 14-day PITR window. Off-site DR on a 1C1G VPS for ~$1/mo vs $35-55/mo for managed Multi-AZ. Includes a monthly restore drill, archive-lag alerting, and 5 hard-won pitfalls."
---

# PostgreSQL PITR on a 1C1G VPS: pgBackRest + Cloudflare R2 for Second-Level Rollback

If your database backup strategy is "a `pg_dump` every night," then when the 09:32 `DELETE` without a `WHERE` wipes 400k rows of production data, all you can do is restore yesterday's dump and accept the loss of those 9+ hours of business data.

**PITR (Point-in-Time Recovery)** is the answer: continuously archive the WAL (write-ahead log) and, on recovery, replay it up to the exact second you choose. The cost of a bad statement drops from "lose a day" to "lose seconds."

This post runs the whole stack on a 1C1G VPS with open-source pieces only:

- **pgBackRest** — continuous WAL archiving plus full/incremental backup chains, with built-in verification and expiry;
- **Cloudflare R2** as the off-site repo (S3-compatible) — **$0 egress**, so pulling hundreds of GB back during a restore costs nothing;
- a monthly automated drill + Prometheus textfile alerts, so "the backup actually restores" is evidence, not faith.

## 1. Do the Cost Math First

Assume: 1GB database, steady writes producing ~1GB of WAL per day (16MB × 6,400 segments).

| Strategy | Monthly cost | Recovery granularity | Notes |
|------|:---:|:---:|------|
| Nightly pg_dump (local only) | ~$0 | Day-level | Lose 12-24h; local disk = local disaster |
| pg_dump + S3 off-site | $3-5 | Day-level | Plus S3 egress on restore ($0.09/GB) |
| RDS / managed Multi-AZ or DR | $35-60 | Second-level (PITR) | Expensive, vendor-locked |
| **pgBackRest + R2 (this post)** | **$1-2** | **Second-level (PITR)** | Repo caps at ~40GB; $0.015/GB storage, ~$0 egress |

In steady state the repo is: 1 full (~300-600MB compressed) + incremental chain + 14 days of WAL (~14GB) ≈ **15-40GB total**, which is **$0.25-0.60/mo** of R2 storage plus negligible class-A operation fees. Versus managed DR you save **$35-55/mo** ($420-660/yr) while upgrading recovery granularity from days to seconds.

## 2. Architecture & Backup Policy

```
┌──────────────────────────────────────────────────────┐
│ 1C1G VPS (Ubuntu 24.04)                              │
│                                                      │
│  PostgreSQL 16                                       │
│   │ archive_command: pgbackrest archive-push %p       │
│   │                                                   │
│   ├─ daily 03:30 incremental (full on Mondays)       │
│   └─ real-time WAL archiving (16MB/seg, pushed on   │
│      write, archive_timeout=60s)                     │
└──────────────┬───────────────────────────────────────┘
               │ S3 API (HTTPS, sigv4, s3-region=auto)
               ▼
   Cloudflare R2  bucket: pg-pitr-<dbname>
   ├── full-2026-11-16/      (~4 fulls kept, 30-day window)
   ├── inc-.../              (incremental chain)
   └── wal/16/               (14 days of WAL, auto-expired)
               ▲
               │ restore pulls at $0 egress
   drill box / local scratch dir ──► pgbackrest restore --target="..."
```

The chain (defaults, tuned for retention):

| Policy | Frequency | Retention | Job |
|------|------|------|------|
| Full backup | Mondays | 4 (~30 days) | Anchor of the chain |
| Incremental | Daily 03:30 | Rides with the chain | Transfers only changed pages; <50MB for a 1GB DB |
| WAL archiving | Real-time | 14 days | The PITR window itself |

**PITR window = 14 days**: any fault within two weeks can be rolled back to the exact moment before it.

## 3. Install & Configure (10 Minutes)

```bash
# 1. Install (PG16 + pgBackRest 3.x)
apt install pgbackrest postgresql-16
# The official repo is newer than distro packages:
# curl -s https://www.pgbackrest.org/repositories.gpg | apt-key add -
# echo "deb https://pgbackrest.org/ apt $(lsb_release -sc) main" > /etc/apt/sources.list.d/pgbackrest.list

# 2. Dedicated runtime user (least privilege)
useradd -m -s /usr/sbin/nologin pgbackrest
```

`/etc/pgbackrest/pgbackrest.conf`:

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

R2 side: Dashboard → R2 → Create Bucket (`pg-pitr-<db>`) → create an Access Key (Accounting API token, **not** a Cloudflare API token). The endpoint looks like `https:acct-xxxxx.r2.cloudflarestorage.com`; always set region to `auto`.

PostgreSQL side (`postgresql.conf` + `pg_hba.conf`):

```ini
# postgresql.conf
archive_mode = always
archive_command = 'pgbackrest --stanza=db archive-push %p'
archive_timeout = 60   # push partial WAL at most every 60s even when writes are quiet
max_wal_senders = 4
```

```
# pg_hba.conf: pgbackrest user via local socket, no password
local   all   pgbackrest   trust
```

The three-command test:

```bash
pgbackrest --stanza=db --check          # connectivity + permissions
pgbackrest --stanza=db full            # first full
pgbackrest --stanza=db --type=incr     # incremental
pgbackrest --stanza=db --info          # inspect the chain
pgbackrest --stanza=db verify --latest  # checksum verification (~30-60s)
```

## 4. PITR Restore: Roll Back One Second Before the Incident

```bash
# 1. Stop PG and clear pgdata (PITR can never run on a live data dir)
systemctl stop postgresql
mv /var/lib/postgresql/16/main /var/lib/postgresql/16/main.bak

# 2. Restore to 2026-11-16 09:32:00 (the bad statement ran at 09:32:07)
sudo -u pgbackrest pgbackrest --stanza=db restore \
  --target="2026-11-16 09:32:00+08" --target-inclusive=n \
  --type=time

# 3. Start in recovery mode; WAL replays up to the target, then auto-promotes
sudo -u postgres pg_ctl -D /var/lib/postgresql/16/main start -C
# Watch recovery stop at 09:32:00 and switch to normal mode

# 4. Verify row counts, then remove .bak
SELECT count(*) FROM orders;   # compare against the known pre-incident value
rm -rf /var/lib/postgresql/16/main.bak
```

Other target forms: `--target-immediate` (latest available point), `--target-lsn="0/1A3..."` (exact LSN). The `-C` flag makes PG write `recovery.signal` itself; drop it if you don't want automatic promotion.

**Key insight**: PITR restores "data + WAL replay" — everything written *after* the target is discarded. The target must be **before** the confirmed incident moment, not at it.

## 5. Monthly Drill + Monitoring: Backups You Dare to Use

The biggest risk in a backup system isn't backup failure — it's **finding out about the failure too late**, or discovering during the real incident that the backup won't restore. Two defenses:

**① Archive-lag alerting (the PITR window is being stolen right now)**

```sql
-- archived LSN vs current LSN (PG14+)
SELECT pg_wal_lsn(last_archived_wal, 0) AS archived_lsn,
       pg_current_wal_lsn() AS now_lsn,
       pg_wal_lsn(now_lsn, 0) - pg_wal_lsn(last_archived_wal, 0) AS lag_bytes,
       last_archived_time, last_failed_time
FROM pg_stat_archiver;
```

**② One-click drill script (systemd timer, runs on the 1st of each month)**

```bash
#!/usr/bin/env bash
# /usr/local/bin/pgbackrest-drill.sh — restore into a scratch dir, sanity-check
set -euo pipefail
SCRATCH=/var/lib/pgbackrest/drill
rm -rf "$SCRATCH" && mkdir -p "$SCRATCH"

sudo -u pgbackrest pgbackrest --stanza=db restore --target-immediate \
  -D "$SCRATCH" --config=/etc/pgbackrest/pgbackrest.conf
sudo -u postgres pg_ctl -D "$SCRATCH" start -C -o "-p 5433 -c listen_addresses=''"
sudo -u postgres psql -p 5433 -tAc \
  "SELECT 'drill_rows:'||sum(n_live_tup) FROM pg_stat_user_tables;" > \
  /var/lib/prometheus/textfiles/pgbackrest_drill.txt
sudo -u postgres psql -p 5433 -tAc \
  "SELECT 'last_drill_success:'||to_unix_timestamp(now())" >> \
  /var/lib/prometheus/textfiles/pgbackrest_drill.txt
sudo -u postgres pg_ctl -D "$SCRATCH" stop
```

Matching Prometheus alerts (`alert.rules.yml`):

```yaml
- alert: PGBackRestArchiveLag
  expr: (pg_current_wal_lsn() - pg_wal_lsn(last_archived_wal,0)) > 268435456   # >256MB
  for: 10m
  labels: {severity: warning}
- alert: PGBackRestBackupStale
  expr: time() - last_backup_success_timestamp > 7*86400                     # no success in 7 days
  labels: {severity: critical}
- alert: PGBackRestArchiveFailed
  expr: pg_stat_archiver_last_failed_time > (now() - 3600)
  labels: {severity: critical}
```

## 6. Measured on 1C1G (Shared-Burst Instance)

Real numbers on a 1C1G shared-type VPS (1GB DB, zstd compression):

| Operation | Duration | Peak usage | Impact on primary |
|------|------|:---:|------|
| Full backup (1GB→~350MB) | 45-90s | CPU 100%, I/O ~30-40MB/s | Query P99 +15-30ms (acceptable off-peak) |
| Incremental | 3-8s | ~20MB upstream | None |
| archive-push (16MB/seg) | 1-3s each | ~30MB RSS | None |
| verify --latest | 30-60s | CPU-heavy | Run off-peak |
| Restore --target-immediate (40GB repo → local) | ~8-15min @ 50Mbps | ~350MB written | Service down during restore |

Tuning notes:

- `process-max=2` is the sweet spot on 1C1G: compression is single-threaded, so more processes only steal CPU;
- Full backups at 03:30, `--progress` off (saves log I/O);
- Drills use `--target-immediate` + a scratch dir + a private port — **never test-restore on the production pgdata**;
- R2's $0 egress is the whole cost curve: pulling 40GB back = $0; the same restore from AWS S3 is ~$3.6.

## 7. Five Pitfalls (All Found the Hard Way)

**Pitfall 1: Silent archive-push failures = a bleeding PITR window.** When R2 rate-limits or the key expires, `archive_command` exits non-zero and PG marks that WAL segment failed; once WAL fills, **Postgres halts to protect data**. The `last_failed_time` critical alert is mandatory, and R2 key rotation (90 days) belongs in your runbook.

**Pitfall 2: Clock drift breaks S3 signatures.** SigV4 is time-sensitive. A VPS without chrony (or with an unreachable NTP source) gets `SignatureDoesNotMatch` on `archive-push`. Fix: set the timezone, run `chronyd`, and verify `chronyc tracking` shows a System time offset under 100ms. In pgBackRest logs, `http status=403 reason=SignatureDoesNotMatch` almost always means NTP — check the clock before the credentials.

**Pitfall 3: Running restore over a live pgdata.** `pgbackrest restore` needs an empty target directory; running it over a running data directory destroys the data. Always: stop → move/clear pgdata → restore → start. Drills use a scratch directory (section 5).

**Pitfall 4: `retention-archive` defaults to 7 days while you assume 30.** The default PITR window is only "7 days + age of the oldest full," and `expire` runs **at the next backup** — the window you think you have may already be gone before your last backup. This post sets `repo1-retention-archive=14` explicitly; for 30 days set it to 30, at a cost of WAL-per-day × 30 (≈30GB, +$0.45/mo).

**Pitfall 5: Full backups saturate I/O on a 1C1G box.** Shared-type VPSes have burst I/O quotas; compression + upload together raise query P99s visibly. Countermeasures: `process-max=2`, zstd level 6 (40% faster than level 9, only ~5% less compression), off-peak scheduling, and optionally `--bandwidth-limit=80000` (KB/s ≈ 64Mbps) to cap the impact on foreground queries.

## 8. One-Click Deployment Checklist

```bash
# 10-minute end-to-end pipeline (executed in section-3 order)
pgbackrest --stanza=db --check \
&& pgbackrest --stanza=db full \
&& pgbackrest --stanza=db verify --latest \
&& pgbackrest --stanza=db --info | grep -E 'Full|Incremental' \
&& echo "✅ PITR pipeline ready: 14-day window, R2 repo $(pgbackrest --stanza=db --info | awk '/Repository 1/{f=1;next}/Full Backup/{if(f)print;f=0}')"
```

- [x] R2 bucket + write-only Access Key (never the Cloudflare API full token)
- [x] `pgbackrest.conf` (retention-full=4 / retention-archive=14 / zstd)
- [x] PG `archive_mode=always` + `archive_timeout=60` + pg_hba trust
- [x] Daily 03:30 incremental + Monday full via systemd timer
- [x] Monthly drill script + 3 Prometheus alerts

**Total cost: R2 storage $0.25-0.60/mo + ~$0.05 operations ≈ under $1/mo.** What you get: a 14-day rollback window, second-level recovery, and monthly "we actually restored it" evidence. Compared to managed Multi-AZ you save $35-55/mo ($420-660/yr) — and your recovery is *more* controllable than most vendor DR packages, because you're the one running the drill.

> Related: [Restic 6-Layer Encrypted Backup + 2-1-1 Strategy](/post/vps-restic-s3-six-layer-encryption-2-1-1-backup/) (file-level), [S3 Bucket Governance Playbook: Lifecycle Rules That Cut Object-Storage Bills](/post/s3-bucket-policy-lifecycle-object-lock-cost/) (storage cost), [VPS Disk I/O & Storage Cost Optimization](/post/vps-storage-optimization-cost-saving/).
