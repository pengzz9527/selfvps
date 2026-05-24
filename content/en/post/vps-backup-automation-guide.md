---
title: "VPS Backup Automation Guide: Complete Protection for Databases, Files, and Docker Volumes"
description: "Comprehensive VPS backup strategy — covering PostgreSQL/MySQL/SQLite database backups, Docker volume snapshots, file archiving, and automated offsite sync to B2/S3 storage"
date: 2026-05-24T10:00:00+08:00
slug: "vps-backup-automation-guide"
image: /images/posts/vps-backup-automation-guide/featured.png
tags: ["Backup", "Automation", "VPS", "Docker", "Database", "DevOps", "B2", "S3"]
categories: ["DevOps"]
draft: false
---

## Introduction

> **"Two backups are not enough — you need a third one offsite."**

The biggest advantage of self-hosting is data sovereignty, but the biggest risk is **data loss**. Hard drive failures, accidental deletions, ransomware attacks — when disaster strikes, having no backup means game over.

This guide isn't about *whether* you should back up — it gives you a **production-ready automation setup** covering:

- ✅ Automated database backups (PostgreSQL / MySQL / SQLite)
- ✅ Docker volume cold backups and snapshots
- ✅ File archiving with version management
- ✅ Offsite sync to cloud storage (Backblaze B2 / S3-compatible)
- ✅ Backup integrity verification and automatic cleanup
- ✅ Disaster recovery testing methodology

---

## Architecture Overview

```
┌─────────────────────────────┐
│          VPS Server          │
│  ┌──────────┐ ┌──────────┐  │
│  │  Cron Job │ │  Backup  │  │
│  │ (scheduler)│→│ Scripts  │  │
│  └──────────┘ └─────┬────┘  │
│                     │       │
│          ┌──────────▼────┐  │
│          │  Local Backup  │  │
│          │  /var/backups/ │  │
│          └──────┬────────┘  │
│                 │          │
│        ┌────────▼────────┐ │
│        │ Offsite Sync    │ │
│        │ (rclone)        │ │
│        │ → B2 / S3 / GCS │ │
│        └─────────────────┘ │
└─────────────────────────────┘
```

Core principle: **3-2-1 Backup Strategy**
- **3** copies of your data
- **2** different storage media
- **1** copy stored offsite

---

## 1. Automated Database Backups

### 1.1 PostgreSQL Backup Script

```bash
#!/bin/bash
# pg_backup.sh — Scheduled PostgreSQL backup
PG_DATABASES=("myapp" "nextcloud" "matrix")
BACKUP_DIR="/var/backups/postgresql"
RETENTION_DAYS=30
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

mkdir -p "$BACKUP_DIR"

for db in "${PG_DATABASES[@]}"; do
    # Use pg_dump for compressed custom format
    pg_dump -U postgres "$db" \
      --format=custom \
      --compress=9 \
      --file="${BACKUP_DIR}/${db}_${TIMESTAMP}.dump"

    # Generate checksum
    sha256sum "${BACKUP_DIR}/${db}_${TIMESTAMP}.dump" \
      > "${BACKUP_DIR}/${db}_${TIMESTAMP}.dump.sha256"

    echo "✅ PostgreSQL backup completed: $db"
done

# Clean backups older than retention period
find "$BACKUP_DIR" -name "*.dump" -mtime +$RETENTION_DAYS -delete
find "$BACKUP_DIR" -name "*.dump.sha256" -mtime +$RETENTION_DAYS -delete
```

### 1.2 MySQL/MariaDB Backup Script

```bash
#!/bin/bash
# mysql_backup.sh — Scheduled MySQL/MariaDB backup
MYSQL_USER="backup_user"
MYSQL_PASSWORD="your_secure_password"
BACKUP_DIR="/var/backups/mysql"
RETENTION_DAYS=30
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

mkdir -p "$BACKUP_DIR"

# Get all databases, excluding system databases
databases=$(mysql -u "$MYSQL_USER" -p"$MYSQL_PASSWORD" \
  -e "SHOW DATABASES;" | grep -Ev \
  "(Database|information_schema|performance_schema|mysql|sys)")

for db in $databases; do
    mysqldump -u "$MYSQL_USER" -p"$MYSQL_PASSWORD" \
      --single-transaction \
      --routines \
      --triggers \
      --events \
      "$db" | gzip -9 \
      > "${BACKUP_DIR}/${db}_${TIMESTAMP}.sql.gz"

    sha256sum "${BACKUP_DIR}/${db}_${TIMESTAMP}.sql.gz" \
      > "${BACKUP_DIR}/${db}_${TIMESTAMP}.sql.gz.sha256"

    echo "✅ MySQL backup completed: $db"
done

# Clean old backups
find "$BACKUP_DIR" -name "*.sql.gz" -mtime +$RETENTION_DAYS -delete
find "$BACKUP_DIR" -name "*.sql.gz.sha256" -mtime +$RETENTION_DAYS -delete
```

### 1.3 SQLite Online Backup

SQLite can't be exported remotely like PG/MySQL, but you can use `sqlite3`'s online backup command:

```bash
#!/bin/bash
# sqlite_backup.sh
BACKUP_DIR="/var/backups/sqlite"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Find all SQLite databases and back them up one by one
find /var/lib -name "*.db" -o -name "*.sqlite" | while read db_path; do
    db_name=$(basename "$db_path")
    backup_file="${BACKUP_DIR}/${db_name}_${TIMESTAMP}.bak"

    sqlite3 "$db_path" ".backup '$backup_file'"
    gzip -9 "$backup_file"

    sha256sum "${backup_file}.gz" > "${backup_file}.gz.sha256"
    echo "✅ SQLite backup: $db_name"
done
```

> ⚠️ **Note**: SQLite's `.backup` command holds a read lock during backup, causing brief write blocking. Schedule it during low-traffic periods.

---

## 2. Docker Volume Backups

Docker volumes live under `/var/lib/docker/volumes/`, but copying them directly risks consistency issues. The best approach is using a temporary container for consistent snapshots.

### 2.1 Docker Volume Backup Script

```bash
#!/bin/bash
# docker_volume_backup.sh
BACKUP_DIR="/var/backups/docker-volumes"
RETENTION_DAYS=30
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

VOLUMES=$(docker volume ls --format '{{.Name}}')

for volume in $VOLUMES; do
    echo "Backing up volume: $volume"

    # Use temporary Alpine container to tar volume contents
    docker run --rm \
      -v "${volume}:/source:ro" \
      -v "${BACKUP_DIR}:/backup" \
      alpine:latest \
      tar czf "/backup/${volume}_${TIMESTAMP}.tar.gz" \
        -C /source .

    sha256sum "${BACKUP_DIR}/${volume}_${TIMESTAMP}.tar.gz" \
      > "${BACKUP_DIR}/${volume}_${TIMESTAMP}.tar.gz.sha256"

    echo "✅ Volume backup: $volume"
done

# Clean old backups
find "$BACKUP_DIR" -name "*.tar.gz" -mtime +$RETENTION_DAYS -delete
```

### 2.2 Zero-Downtime Backups for Running Services

For stateful services like databases, **always use the database's native export tools** (pg_dump/mysqldump from sections 1.1 and 1.2) rather than backing up volume files directly.

For file-storage volumes (Nextcloud data, Nginx static assets), the tar approach with read-only mounts is perfectly safe.

---

## 3. File and Configuration Backups

### 3.1 Incremental Backups with rsync

```bash
#!/bin/bash
# rsync_backup.sh — Incremental file sync
SOURCE_DIRS=(
    "/etc/nginx"
    "/etc/letsencrypt"
    "/home"
    "/var/www"
)
BACKUP_DIR="/var/backups/files"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

mkdir -p "$BACKUP_DIR"

for dir in "${SOURCE_DIRS[@]}"; do
    dir_name=$(echo "$dir" | tr '/' '_')
    # Hard-link-based incremental backups (Time Machine style)
    latest_link="${BACKUP_DIR}/latest_${dir_name}"
    target="${BACKUP_DIR}/${dir_name}_${TIMESTAMP}"

    rsync -aHAXS --link-dest="$latest_link" \
      "$dir" "$target"

    # Update latest symlink
    rm -f "$latest_link"
    ln -s "$target" "$latest_link"

    echo "✅ rsync backup: $dir → $target"
done
```

The beauty of this approach: **the first backup is full, subsequent runs only save changed files**. Unchanged files share disk space via hard links — no extra storage cost.

### 3.2 Encrypted Backups with GPG

If you're sending backups to the cloud, encryption is strongly recommended:

```bash
# Encrypt a single backup file
gpg --symmetric --cipher-algo AES256 \
  --passphrase "your-backup-passphrase" \
  -o backup.tar.gz.gpg backup.tar.gz

# Decrypt
gpg --decrypt --passphrase "your-backup-passphrase" \
  -o backup.tar.gz backup.tar.gz.gpg
```

---

## 4. Offsite Sync with rclone

### 4.1 Install and Configure rclone

```bash
# Install rclone
curl https://rclone.org/install.sh | sudo bash

# Interactive configuration
rclone config

# Choose provider: Backblaze B2 / Amazon S3 / Google Cloud Storage, etc.
```

### 4.2 Automated Sync Script

```bash
#!/bin/bash
# rclone_sync.sh — Sync local backups offsite
REMOTE="b2:my-vps-backups"  # Replace with your rclone remote name
LOCAL_BACKUP_DIR="/var/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Sync to B2 (incremental, skip existing files)
rclone sync "$LOCAL_BACKUP_DIR" "$REMOTE/${TIMESTAMP}/" \
  --progress \
  --transfers=4 \
  --checkers=8 \
  --ignore-existing

# Keep only the last 7 remote snapshots
rclone lsd "$REMOTE" | awk '{print $5}' | sort | head -n -7 \
  | while read old_snapshot; do
    rclone purge "${REMOTE}/${old_snapshot}/"
    echo "🧹 Purged old remote snapshot: $old_snapshot"
done
```

### 4.3 Cost Comparison

| Storage Target | Price (per GB/month) | Egress | Best For |
|---------------|---------------------|--------|----------|
| Backblaze B2 | ~$0.006/GB | First 10GB free, then $0.01/GB | ⭐ Best cold backup |
| AWS S3 Glacier | ~$0.004/GB | $0.09/GB | Long-term archive |
| Cloudflare R2 | $0.015/GB | Free | Frequently accessed backups |
| Hetzner Storage Box | €0.04/GB | Free (internal net) | If you use Hetzner |
| rsync.net | $0.02/GB | Free | Pure POSIX compatibility |

> 💡 **Recommendation**: For personal use, **Backblaze B2** is nearly free for backups under 10GB/month. If you already have a Hetzner VPS, Storage Box offers faster internal-network sync at lower cost.

---

## 5. Putting It All Together with Cron

### 5.1 Unified Orchestration Script

```bash
#!/bin/bash
# /usr/local/bin/backup-all.sh — Fully automated backup orchestration
set -e

NOTIFY_URL="https://hooks.slack.com/services/YOUR/WEBHOOK"
START_TIME=$(date +%s)

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# Step 1: Database backups
log "Starting database backups..."
bash /usr/local/bin/pg_backup.sh
bash /usr/local/bin/mysql_backup.sh
bash /usr/local/bin/sqlite_backup.sh

# Step 2: Docker volume backups
log "Starting Docker volume backups..."
bash /usr/local/bin/docker_volume_backup.sh

# Step 3: File backups
log "Starting file backups..."
bash /usr/local/bin/rsync_backup.sh

# Step 4: Verify integrity
log "Verifying backup integrity..."
find /var/backups -name "*.sha256" -exec sh -c '
    sha256sum -c "$1" || echo "❌ FAILED: $1"
' _ {} \;

# Step 5: Sync offsite
log "Syncing to remote storage..."
bash /usr/local/bin/rclone_sync.sh

# Done
DURATION=$(( $(date +%s) - START_TIME ))
log "✅ All backups completed in ${DURATION}s"

# Optional: Send notification
# curl -s -X POST -H "Content-Type: application/json" \
#   -d "{\"text\": \"✅ Backup completed in ${DURATION}s\"}" \
#   "$NOTIFY_URL"
```

### 5.2 Crontab Setup

```bash
# Edit crontab
sudo crontab -e

# Full backup every day at 3:00 AM
0 3 * * * /usr/local/bin/backup-all.sh >> /var/log/backup.log 2>&1

# Database-only backup every 4 hours (optional high-frequency)
0 */4 * * * /usr/local/bin/pg_backup.sh >> /var/log/backup.log 2>&1
0 */4 * * * /usr/local/bin/mysql_backup.sh >> /var/log/backup.log 2>&1
```

---

## 6. Restore Drills

> **A backup you've never tested is a backup you don't have.**

### 6.1 PostgreSQL Restore

```bash
# Restore from custom format
pg_restore -U postgres -d myapp \
  --clean --if-exists \
  /var/backups/postgresql/myapp_20260524_030000.dump

# Restore from SQL file
psql -U postgres -d myapp \
  -f /var/backups/postgresql/myapp_20260524_030000.sql
```

### 6.2 Docker Volume Restore

```bash
# Create a new volume and restore from backup
docker volume create myapp_data

docker run --rm \
  -v "myapp_data:/target" \
  -v "/var/backups/docker-volumes:/backup:ro" \
  alpine:latest \
  tar xzf "/backup/myapp_data_20260524_030000.tar.gz" \
    -C /target
```

### 6.3 Automated Restore Testing

```bash
#!/bin/bash
# test_restore.sh — Test the latest backup's restorability in a temp dir
set -e

TEST_DIR="/tmp/restore-test-$(date +%s)"
mkdir -p "$TEST_DIR"

echo "=== Testing restore of latest DB backups ==="

# Test PostgreSQL restore
latest_pg=$(ls -t /var/backups/postgresql/*.dump | head -1)
pg_restore -l "$latest_pg" > /dev/null \
  && echo "✅ PostgreSQL dump is valid: $latest_pg" \
  || echo "❌ PostgreSQL dump is CORRUPT: $latest_pg"

# Test MySQL restore
latest_mysql=$(ls -t /var/backups/mysql/*.sql.gz | head -1)
gunzip -t "$latest_mysql" \
  && echo "✅ MySQL dump is valid: $latest_mysql" \
  || echo "❌ MySQL dump is CORRUPT: $latest_mysql"

# Test tar archive integrity
find /var/backups/docker-volumes -name "*.tar.gz" -exec sh -c '
    if ! tar tzf "$1" > /dev/null 2>&1; then
        echo "❌ CORRUPT archive: $1"
    fi
' _ {} \;

rm -rf "$TEST_DIR"
echo "=== Restore test complete ==="
```

Schedule monthly restore tests via crontab:

```bash
# Run restore test on the 1st of every month at 5:00 AM
0 5 1 * * /usr/local/bin/test_restore.sh >> /var/log/backup-test.log 2>&1
```

---

## 7. Monitoring & Alerts

### 7.1 Backup Success Monitoring

Add an exit code check at the end of your backup script:

```bash
# Send alert if any step fails
if [ $? -ne 0 ]; then
    curl -s "https://api.healthchecks.io/ping/YOUR-UUID/fail"
else
    curl -s "https://api.healthchecks.io/ping/YOUR-UUID"
fi
```

[Healthchecks.io](https://healthchecks.io) is a free, open-source monitoring service that alerts you if your backup script fails to run on schedule.

### 7.2 Backup Size Trends

```bash
# Log daily backup size
du -sh /var/backups/ \
  >> /var/log/backup-size.log

# View trend
tail -30 /var/log/backup-size.log
```

---

## 8. One-Command Deployment

Deploy the entire backup suite with a single command chain:

```bash
# Download complete backup script set from GitHub
git clone https://github.com/yourname/vps-backup-scripts.git /opt/backup-scripts

# Create backup directories
sudo mkdir -p /var/backups/{postgresql,mysql,sqlite,docker-volumes,files}

# Install dependencies
sudo apt install -y postgresql-client mysql-client rclone

# Set up crontab
(crontab -l 2>/dev/null; echo "0 3 * * * /opt/backup-scripts/backup-all.sh >> /var/log/backup.log 2>&1") | crontab -

# Configure rclone
rclone config
```

---

## Summary

A reliable backup strategy doesn't require complex toolchains. This guide uses just **bash scripts + cron + rclone** — zero external dependencies, fully open-source, and infinitely flexible.

**Action checklist:**

| Step | What to Do | Time |
|------|-----------|------|
| 1 | Choose offsite storage (B2 recommended) | 10 min |
| 2 | Deploy database backup scripts | 15 min |
| 3 | Deploy Docker volume backups | 10 min |
| 4 | Configure rclone offsite sync | 15 min |
| 5 | Set up automated crontab | 5 min |
| 6 | Run a full restore drill | 30 min |

**Backups aren't "set and forget"** — regular restore testing is what makes them real. Remember: your first real restore should never happen during an actual disaster.

---

## Further Reading

- [rclone Documentation](https://rclone.org/docs/)
- [Backblaze B2 + rclone Integration](https://help.backblaze.com/hc/en-us/articles/217666928-Backblaze-B2-with-rclone)
- [Healthchecks.io — Open Source Task Monitoring](https://healthchecks.io/)
- [borgbackup — Advanced Deduplicating Backup](https://www.borgbackup.org/)
- [restic — Fast, Secure, Encrypted Backups](https://restic.net/)
