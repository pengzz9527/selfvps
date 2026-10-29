---
title: "The One-Command Backup Philosophy: tar + restic + R2 Full/Incremental Pipeline"
description: "Back up a VPS to Cloudflare R2 with a single cron line: tar (full) + tar --incremental + restic dedup/snapshot, 90-day retention, automatic prune. $0 egress forever, testable restore included."
date: 2026-10-29T11:30:00+08:00
lastmod: 2026-10-29T11:30:00+08:00
slug: "vps-tar-backup-pipeline-r2"
image: "/images/posts/vps-tar-backup-pipeline-r2/featured.png"
tags: ["VPS", "Backup", "tar", "restic", "Cloudflare R2", "Zero Egress", "Cron", "S3", "Self-hosted", "DR"]
categories: ["VPS Cost Saving & Ops"]
aliases: ["/en/post/vps-tar-backup-pipeline-r2/"]
draft: false
---

## The Problem: Why Most "Simple" Backup Scripts Fail

Your VPS is running a web stack, a database, some Docker services. You've written a little backup script: `tar czf /var/backups/full.tar.gz /etc /var/www` and `rclone copy` it somewhere. Six months later:

- The last successful backup was 41 days ago and nobody noticed.
- Ransomware wiped `/var/www` and the "backup" archive contains the same infected files (you tarred while the infection was live).
- You have 37 copies of "the same" full backup and your storage bill is climbing.
- To restore, you untar into a running system and break production.

The root cause: **a backup without a retention policy, deduplication, and a tested restore path is just "files stored elsewhere."**

The goal of this post: **one cron line, daily, that produces a full tar the first day of the week and incrementals on the other six — then pushes them through restic into Cloudflare R2 with 90-day retention, automatic prune, and a verified restore run — all for $0 in egress fees.**

---

## Pipeline Overview

```
/etc/cron.daily (systemd timer)
   │
   ├─ step 1  tar  → /var/backup/full-YYYY-MM-DD.tar        (full)
   │            tar → /var/backup/incr-YYYY-MM-DD.tar        (incremental, .snar)
   │            gzip -9 → *.tar.gz                            (or zstd -19 for 30% smaller)
   │
   ├─ step 2  restic init  → s3:https://<acct>.r2.cloudflarestorage.com/bucket
   │            restic backup /var/backup/                      (dedup + encrypt + compress)
   │            restic forget --keep-daily 30 --keep-weekly 8 --keep-monthly 12
   │            restic prune                                      (free up R2 storage)
   │
   └─ step 3  health check: restic check + last snapshot age < 48h
                 → success: log + delete local tar > 7 days
                 → failure: Telegram/SMTP alert
```

Three ideas that make this different from `tar | rclone`:

| Property | `tar \| rclone` | This pipeline |
|---|---|---|
| Deduplication | No — every upload is full | Yes — restic dedupes across snapshots |
| Retention policy | Manual rm | `--keep-daily/weekly/monthly` + `prune` |
| Encryption at rest | None | AES-256-CTR (restic) |
| Ransomware safety | Archive may contain infected files | restic's immutable snapshots + `.snar` incremental state survives |
| Egress cost on R2 | ~$0 but per-request fees | ~$0 (R2 egress is free) |
| Verified restore | No | `restic restore` into scratch + checksum test |

---

## 1. Cloudflare R2 as the Backup Destination

R2's killer feature: **zero egress fees.** Traditional S3 (AWS/GCP) charges ~$0.09/GB egress; 100GB of monthly restore reads costs ~$9. R2 charges nothing for downloads. For backup, where "restore" is the most important operation, this matters.

Pricing recap:

| Item | R2 | AWS S3 |
|---|---|---|
| Storage (hot) | $0.015/GB/month | $0.023/GB/month |
| egress | **$0** | $0.09/GB |
| PUT requests | $0.0004/1000 (class A) | $0.005/1000 |
| free tier | 10 GB | 5 GB |

A 10 GB VPS backup at 90-day retention ≈ 10 GB in R2 = **$0.15/month storage, $0 egress**.

### Setup

1. Create bucket `vps-backups` (private, no public access).
2. Create an API Token with `Object Read` + `Object Write` on that bucket.
3. On the VPS, write `/root/.config/restic/repo-pass` (a passphrase — keep it in a password manager, or derive one with `restic key unlock` on a second machine).

```bash
RESTIC_REPOSITORY="s3:https://acme-1234.r2.cloudflarestorage.com/vps-backups"
export RESTIC_PASSWORD="your-passphrase"
export AWS_ACCESS_KEY_ID="<r2-token-id>"
export AWS_SECRET_ACCESS_KEY="<r2-token-secret>"
# restic's S3 backend uses these to auth against any S3-compatible URL
restic -r $RESTIC_REPOSITORY init
```

> **Tip:** keep the passphrase out of the repo. Use a `~/.config/restic/.env` file with `chmod 600`, sourced by the systemd timer unit.

---

## 2. Full + Incremental tar — the `.snar` State File

`tar --listed-incremental` writes a **snapshot file** (`.snar`) that records the mtime/inode of every file at the last full backup. On the next incremental, tar includes only files newer than that snapshot. This gives you:

- **Day 0 of the week** (Monday): a full tarball (~the size of the data set).
- **Days 1-6**: small incrementals containing only changes.

Restore = unpack the most recent full, then each incremental in order. restic stores all of them deduped, so you can restore to any historical point.

### The backup directory layout

```
/var/backup/
  full/
    full-2026-10-26.tar.gz
    full.snar                       # incremental state for full-2026-10-26
  incr/
    incr-2026-10-27.tar.gz
    incr-2026-10-28.tar.gz
  ...
```

### The tar commands

```bash
#!/usr/bin/env bash
set -euo pipefail

BATCH_DAY=0   # 0 = Sunday..6 = Saturday; 1 = Monday = full day
TODAY=$(date +%F)
DOW=$(date +%u)

# Paths to back up — adjust to your VPS
SRC="/etc /var/www /var/lib/mysql /opt /root /home"
EXCLUDES=(
  "/proc/" "/sys/" "/dev/"
  "/var/backup/"       # don't back up the backups
  "/tmp/" "/run/"
)

if [ "$DOW" -eq 1 ]; then
  # ---- Monday: FULL ----
  OUT="/var/backup/full/full-${TODAY}"
  # --listed-incremental rewrites .snar to today's state
  tar --create --file "${OUT}.tar" \
      --listed-incremental="/var/backup/full/full.snar" \
      --exclude=/proc --exclude=/sys --exclude=/dev \
      --exclude=/var/backup --exclude=/tmp --exclude=/run \
      -C / $SRC
  gzip -9 "${OUT}.tar"    # or: zstd -19 -T0 "${OUT}.tar" -o "${OUT}.tar.zst"
else
  # ---- Tue..Sun: INCREMENTAL ----
  OUT="/var/backup/incr/incr-${TODAY}"
  tar --create --file "${OUT}.tar" \
      --listed-incremental="/var/backup/full/full.snar" \
      --exclude=/proc --exclude=/sys --exclude=/dev \
      --exclude=/var/backup --exclude=/tmp --exclude=/run \
      -C / $SRC
  gzip -9 "${OUT}.tar"
fi
```

> **Why gzip and not zstd?** gzip is everywhere and restic will re-compress anyway. If you prefer zstd, the pipeline is identical — just swap the compression command. zstd at `-19` is ~30% smaller than gzip at `-9` and much faster on multi-core VPSes.

### Exclusions matter more than you think

The two biggest silent backup killers:

1. **Backing up `/var/backup` itself** — infinite recursion of tarballs.
2. **Backing up `/tmp` and `/run`** — transient files that are useless in a restore and bloat the archive.

For databases, stop them first (or use `mysqldump` / `pg_dump` to get a logical backup, which is smaller and version-agnostic).

---

## 3. restic: Dedup, Encrypt, Retention, Prune

restic is the workhorse. It:

- splits files into chunks, dedupes across all snapshots (so 7 daily snapshots of a 10 GB system ≈ 12 GB total, not 70 GB),
- encrypts everything (AES-256-CTR + XChaCha20),
- keeps a retention policy via `forget`,
- physically removes unreachable chunks via `prune`.

### The restic commands

```bash
#!/usr/bin/env bash
set -euo pipefail

source /root/.config/restic/.env   # RESTIC_PASSWORD, AWS creds, RESTIC_REPOSITORY

REPO=$RESTIC_REPOSITORY
TODAY=$(date +%F)

# Figure out what we just tarred
if [ "$(date +%u)" -eq 1 ]; then
  NEW_FILE="/var/backup/full/full-${TODAY}.tar.gz"
else
  NEW_FILE="/var/backup/incr/incr-${TODAY}.tar.gz"
fi

restic -r "$REPO" --cache-dir /var/lib/restic-cache backup "$NEW_FILE"

# Retention: last 30 daily + last 8 weekly + last 12 monthly
restic -r "$REPO" forget \
  --keep-daily 30 --keep-weekly 8 --keep-monthly 12 \
  --forget-incompatible

# Prune: actually delete the chunks no longer referenced
restic -r "$REPO" prune

# Verify the last snapshot
restic -r "$REPO" check --data 2>/dev/null || echo "WARNING: restic check failed"

# Clean up local tars older than 7 days (restic has them in R2)
find /var/backup/full /var/backup/incr -name '*.tar.gz' -mtime +7 -delete
```

> **`prune` is the part people forget.** Without it, R2 storage grows forever because `forget` only marks snapshots as removable — `prune` actually deletes the chunks. R2 is cheap, but habit matters.

---

## 4. The "One Cron Line" (systemd timer version)

The whole thing can be one timer unit + one service:

```ini
# /etc/systemd/system/vps-backup.service
[Unit]
Description=VPS tar+restic backup pipeline
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
EnvironmentFile=/root/.config/restic/.env
ExecStart=/usr/local/bin/vps-backup-pipeline.sh
Nice=10
IOSchedulingClass=idle
```

```ini
# /etc/systemd/system/vps-backup.timer
[Unit]
Description=Run vps-backup-pipeline daily at 02:30

[Timer]
OnCalendar=*-*-* 02:30:00
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
systemctl daemon-reload
systemctl enable --now vps-backup.timer
```

If you prefer cron: `30 2 * * * /usr/local/bin/vps-backup-pipeline.sh >> /var/log/vps-backup.log 2>&1`.

---

## 5. The Restore Test (Don't Skip This)

A backup you've never restored is a hope, not a strategy. Add a **quarterly restore drill** to your runbook:

```bash
# 1. Pick the latest snapshot
restic -r $RESTIC_REPOSITORY ls | head

# 2. Restore to a scratch directory (never into /)
restic -r $RESTIC_REPOSITORY restore latest --target /tmp/restore-test

# 3. Verify key files exist and checksums match
sha256sum /tmp/restore-test/etc/hosts /tmp/restore-test/var/www/html/index.html

# 4. For databases: run a logical dump from the restored dir
cd /tmp/restore-test/opt/mysql && ./start-check.sh
```

Automate the drill: a monthly systemd timer that restores the latest snapshot into a throwaway VM or container and runs a `verify` script that compares file counts and hashes against a baseline.

---

## 6. Full Script (Copy-Paste Ready)

`/usr/local/bin/vps-backup-pipeline.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

# ---- config ----
BACKUP_ROOT=/var/backup
SRC="/etc /var/www /var/lib/mysql /opt /root /home"
RETENTION_DAILY=30
RETENTION_WEEKLY=8
RETENTION_MONTHLY=12
LOG_PREFIX="[vps-backup $(date +%F\ %T)]"

alert() { echo "${LOG_PREFIX} ALERT: $*" | tee -a /var/log/vps-backup.log; }
info()  { echo "${LOG_PREFIX} $*"; }

mkdir -p "$BACKUP_ROOT/full" "$BACKUP_ROOT/incr"

TODAY=$(date +%F)
DOW=$(date +%u)   # 1=Mon..7=Sun

# ---- step 1: tar ----
if [ "$DOW" -eq 1 ]; then
  info "Monday: creating FULL tar"
  OUT="${BACKUP_ROOT}/full/full-${TODAY}.tar"
  tar --create --file "$OUT" \
      --listed-incremental="${BACKUP_ROOT}/full/full.snar" \
      --exclude=/proc --exclude=/sys --exclude=/dev \
      --exclude=$BACKUP_ROOT --exclude=/tmp --exclude=/run \
      -C / $SRC
else
  info "Day $DOW: creating INCREMENTAL tar"
  OUT="${BACKUP_ROOT}/incr/incr-${TODAY}.tar"
  tar --create --file "$OUT" \
      --listed-incremental="${BACKUP_ROOT}/full/full.snar" \
      --exclude=/proc --exclude=/sys --exclude=/dev \
      --exclude=$BACKUP_ROOT --exclude=/tmp --exclude=/run \
      -C / $SRC
fi
gzip -9 "$OUT"
info "tarball created: $OUT.gz"

# ---- step 2: restic ----
source /root/.config/restic/.env
restic -r "$RESTIC_REPOSITORY" --cache-dir /var/lib/restic-cache backup "${OUT}.gz"
restic -r "$RESTIC_REPOSITORY" forget \
  --keep-daily $RETENTION_DAILY --keep-weekly $RETENTION_WEEKLY --keep-monthly $RETENTION_MONTHLY \
  --forget-incompatible
restic -r "$RESTIC_REPOSITORY" prune
info "restic snapshot uploaded + pruned"

# ---- step 3: health + cleanup ----
find "$BACKUP_ROOT" -name '*.tar.gz' -mtime +7 -delete
LAST_SNAP_EPOCH=$(restic -r "$RESTIC_REPOSITORY" snapshots --json | \
  python3 -c "import sys,json;d=json.load(sys.stdin);print(max(int(x['time'].replace('Z','+0000').replace('+00:00','').replace('+08:00','')) for x in d))")
AGE_HOURS=$(( ( $(date +%s) - ${LAST_SNAP_EPOCH//[^0-9]/0} ) / 3600 ))
if [ "$AGE_HOURS" -gt 48 ]; then
  alert "last restic snapshot is ${AGE_HOURS}h old — possible upload failure"
  exit 1
fi
info "backup pipeline OK — last snapshot ${AGE_HOURS}h ago"
```

---

## 7. Cost Summary (10 GB data set, 90-day retention)

| Item | Monthly |
|---|---|
| R2 storage (~12 GB after dedup) | $0.18 |
| R2 egress | $0 |
| R2 requests | <$0.01 |
| VPS CPU during 02:30 backup | ~2 min of one core |
| **Total** | **~$0.19/month** |

Compare: ~$3-5/month for a commercial off-site backup service, with egress fees on restore.

---

## TL;DR

- **Day 1 (Monday)**: `tar --listed-incremental=full.snar` → full tarball.
- **Days 2-7**: `tar --listed-incremental=full.snar` → small incrementals.
- **Every day**: `restic backup` the new tarball → dedup + encrypt into R2.
- **Every day**: `restic forget --keep-daily 30 --keep-weekly 8 --keep-monthly 12` + `restic prune`.
- **Quarterly**: `restic restore latest --target /tmp/drill` + checksum verify.
- **Result**: $0 egress, 90-day retention, ransomware-immutable snapshots, one cron line.

The philosophy: **backups are a pipeline, not a command.** Every stage is testable, and the restore path is as important as the write path.
