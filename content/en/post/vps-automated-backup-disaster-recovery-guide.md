---
title: "VPS Automated Backup & Disaster Recovery: From Local Snapshots to Offsite Failover"
description: "Your VPS data is priceless, but accidents happen. This guide walks you through a complete automated backup system — local snapshots, offsite sync, encrypted storage, one-click recovery — so data loss nightmares become things of the past."
date: 2026-08-18T10:00:00+08:00
lastmod: 2026-08-18T10:00:00+08:00
slug: "vps-automated-backup-disaster-recovery-guide"
image: /images/posts/vps-automated-backup-disaster-recovery-guide/featured.png
tags: ["VPS", "Backup", "Disaster Recovery", "Restic", "Offsite Backup", "Automation", "Data Security", "DevOps"]
categories: ["Operations"]
aliases: [/en/post/vps-automated-backup-disaster-recovery-guide/]
---

## Introduction

If you're running critical VPS services — websites, databases, APIs, file storage — you should know a harsh truth: **data loss is one of the most expensive incidents in operations**.

A disk failure, a accidental deletion, a ransomware attack — any of these can turn months of work into nothing. Worse still, you often won't realize the problem until it's too late.

**Backup is not optional — it's essential.** But many people's understanding of backup stops at "periodically copy files," lacking a systematic disaster recovery strategy. This article walks you through building a complete automated backup and disaster recovery system from scratch.

---

## Core Principle: The 3-2-1 Backup Rule

Before we start, let's understand the industry-recognized golden rule of backup — the **3-2-1 Rule**:

- **3 copies of data**: Original data + 2 backups
- **2 different storage media**: e.g., local disk + remote object storage
- **1 offsite backup**: At least one backup stored in a geographically separate location

This rule effectively guards against disk failures, fires, ransomware, and various other risks.

---

## Architecture Design

Our backup system consists of four layers:

```
┌─────────────────────────────────────────────────────┐
│  Layer 1: Local Snapshots (second-level)             │
│  - LVM snapshot / Btrfs snapshot                     │
│  - For quick rollback of accidental deletions          │
├─────────────────────────────────────────────────────┤
│  Layer 2: Incremental Backup (hourly)                │
│  - Restic encrypted incremental backup               │
│  - Efficient deduplication and compression             │
├─────────────────────────────────────────────────────┤
│  Layer 3: Offsite Sync (daily)                       │
│  - Push backups to remote server / S3 storage        │
│  - AES-256 encryption, key separate from data        │
├─────────────────────────────────────────────────────┤
│  Layer 4: Disaster Recovery (on-demand)              │
│  - One-click recovery scripts                        │
│  - Complete recovery drill procedures                  │
└─────────────────────────────────────────────────────┘
```

---

## Step 1: Local LVM Snapshots (Instant Rollback)

If your VPS uses LVM partitions, you can create second-level snapshots for emergency rollback:

```bash
# Check current volume group info
vgdisplay
lvdisplay

# Create snapshot (allocate enough space, recommend at least 20% of original volume)
lvcreate --size 10G --snapshot \
  --name snap_before_upgrade \
  /dev/vg_main/lv_root

# Mount snapshot (read-only)
mkdir -p /mnt/snapshot
mount -o ro /dev/vg_main/snap_before_upgrade /mnt/snapshot

# Remove snapshot after confirming everything is fine
lvremove /dev/vg_main/snap_before_upgrade
```

> **Note**: Snapshots are not backups! They depend on the original volume — if the original volume is damaged, the snapshot is useless too. Snapshots are only for quick rollback; real backups require Layer 2.

---

## Step 2: Restic Encrypted Incremental Backup

Restic is one of the best open-source backup tools available, supporting deduplication, incremental backups, and end-to-end encryption.

### Install Restic

```bash
# Ubuntu/Debian
wget https://github.com/restic/restic/releases/download/v0.17.4/restic_0.17.4_amd64.deb
sudo dpkg -i restic_0.17.4_amd64.deb

# Or compile from source
go install github.com/restic/restic@v0.17.4
```

### Initialize Repository

```bash
# Set backup password (remember it!)
export RESTIC_PASSWORD="your-strong-password-here"

# Initialize local backup repo
restic init --repo /backup/local

# Initialize remote backup repo (SSH method)
restic init --repo ssh://backup@remote-server:/backup/restic
```

### Configure Backup Strategy

Create backup config at `/etc/restic/backups.conf`:

```json
{
  "repositories": [
    {
      "name": "local",
      "repo": "/backup/local",
      "paths": ["/home", "/etc", "/var/www", "/opt/app"],
      "exclude": ["*.tmp", "*.cache", "/home/*/.local/share/Trash"]
    },
    {
      "name": "remote",
      "repo": "ssh://backup@remote-server:/backup/restic",
      "paths": ["/home", "/etc", "/var/www", "/opt/app"],
      "exclude": ["*.tmp", "*.cache"]
    }
  ],
  "schedule": {
    "local": "every 6 hours",
    "remote": "daily at 03:00"
  }
}
```

### Execute Backup

```bash
# Test backup (dry-run)
restic --repo /backup/local forget --prune --keep-daily 7 --keep-weekly 4

# Execute local backup
restic --repo /backup/local backup \
  /home /etc /var/www /opt/app \
  --exclude='*.tmp' --exclude='*.cache' \
  --tag="daily-$(date +%Y%m%d)"

# Execute remote backup
restic --repo ssh://backup@remote-server:/backup/restic backup \
  /home /etc /var/www /opt/app \
  --tag="daily-$(date +%Y%m%d)"
```

### Verify Backup Integrity

```bash
# Check backup repo health
restic --repo /backup/local check

# View backup history
restic --repo /backup/local snapshots

# Verify latest backup contents
restic --repo /backup/local ls latest
```

---

## Step 3: Offsite Disaster Recovery Deployment

### Option A: SSH Remote Backup Server

```bash
# Create backup user on remote server
sudo useradd -m -s /bin/bash backup
sudo mkdir -p /backup/restic
sudo chown backup:backup /backup/restic

# Configure SSH key authentication (master → backup server)
ssh-keygen -t ed25519 -C "vps-backup" -f /root/.ssh/backup_key -N ""
ssh-copy-id -i /root/.ssh/backup_key.pub backup@remote-server

# Restrict backup user permissions
# Add command restriction in /etc/passwd
```

### Option B: S3-Compatible Object Storage

```bash
# Install AWS CLI
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install

# Configure S3 access
aws configure
# Access Key ID: your-key
# Secret Access Key: your-secret
# Default region: ap-southeast-1
# Default output format: json

# Restic natively supports S3
restic init --repo s3:s3.ap-southeast-1.amazonaws.com/your-bucket-name
```

### Option C: Rclone + Multi-Cloud Storage

```bash
# Install Rclone
curl https://rclone.org/install.sh | sudo bash

# Configure remote storage
rclone config
# Choose s3, azureblob, google cloud storage, etc.

# Sync backups to multi-cloud
rclone sync /backup/local remote:backup-folder \
  --transfers 4 \
  --checkers 8 \
  --retries 3
```

---

## Step 4: Automation Scheduling

### Cron Tasks

```bash
# Edit crontab
crontab -e

# Local backup every hour
0 * * * * /usr/local/bin/restic-backup.sh local >> /var/log/restic/local.log 2>&1

# Remote backup daily at 3 AM
0 3 * * * /usr/local/bin/restic-backup.sh remote >> /var/log/restic/remote.log 2>&1

# Weekly backup cleanup on Sunday
0 4 * * 0 /usr/local/bin/restic-backup.sh prune >> /var/log/restic/prune.log 2>&1

# Monthly recovery drill on the 1st
0 5 1 * * /usr/local/bin/restic-backup.sh verify >> /var/log/restic/verify.log 2>&1
```

### Complete Backup Script

Create `/usr/local/bin/restic-backup.sh`:

```bash
#!/bin/bash
set -euo pipefail

REPO_TYPE="${1:-local}"
DATE=$(date +%Y%m%d-%H%M%S)
LOG_DIR="/var/log/restic"
LOCK_FILE="/tmp/restic-${REPO_TYPE}.lock"

mkdir -p "$LOG_DIR"

# Prevent concurrent execution
if [ -f "$LOCK_FILE" ]; then
    echo "[$DATE] Another backup is already running, exiting." >> "$LOG_DIR/${REPO_TYPE}.log"
    exit 1
fi
trap 'rm -f "$LOCK_FILE"' EXIT
touch "$LOCK_FILE"

case "$REPO_TYPE" in
    local)
        REPO="/backup/local"
        ;;
    remote)
        REPO="ssh://backup@remote-server:/backup/restic"
        ;;
    *)
        echo "Unknown repo type: $REPO_TYPE"
        exit 1
        ;;
esac

export RESTIC_PASSWORD="your-strong-password-here"
export RESTIC_PROGRESS_FPS=1

echo "[$DATE] Starting $REPO_TYPE backup..." >> "$LOG_DIR/${REPO_TYPE}.log"

# Backup
restic --repo "$REPO" backup \
    /home /etc /var/www /opt/app \
    --exclude='*.tmp' \
    --exclude='*.cache' \
    --tag="$DATE" \
    >> "$LOG_DIR/${REPO_TYPE}.log" 2>&1

echo "[$DATE] Backup completed successfully." >> "$LOG_DIR/${REPO_TYPE}.log"
```

### Notification Mechanism

```bash
# Backup success/failure notification (Telegram Bot example)
notify_backup() {
    local status="$1"
    local repo="$2"
    local msg="[VPS Backup] ${status}: ${repo} at $(date)"
    curl -s -X POST \
        "https://api.telegram.org/bot${TG_BOT_TOKEN}/sendMessage" \
        -d "chat_id=${TG_CHAT_ID}" \
        -d "text=${msg}" \
        -d "parse_mode=HTML"
}

# Add notification at the end of the script
notify_backup "SUCCESS" "$REPO_TYPE"
```

---

## Step 5: Recovery Drills

**Backups that haven't been tested for recovery are no backups at all.**

### Single File Recovery

```bash
# Restore a single file
restic --repo /backup/local restore latest \
    --target /tmp/recovery \
    --include "/etc/nginx/nginx.conf"

# Restore an entire directory
restic --repo /backup/local restore latest \
    --target /tmp/recovery \
    --include "/home/user/documents"
```

### Full System Recovery

```bash
#!/bin/bash
# Full recovery script /usr/local/bin/restore-full.sh

set -euo pipefail

REPO="${1:-/backup/local}"
RESTORE_DATE="${2:-latest}"
MOUNT_POINT="/mnt/recovery"

echo "=== VPS Disaster Recovery Process ==="
echo "Backup repo: $REPO"
echo "Restore point: $RESTORE_DATE"
echo ""

# 1. Mount recovery directory
mkdir -p "$MOUNT_POINT"

# 2. Restore system configs
echo "[1/4] Restoring /etc configs..."
restic --repo "$REPO" restore "$RESTORE_DATE" \
    --target "$MOUNT_POINT" --include "/etc"
cp -a "$MOUNT_POINT/etc/." / 2>/dev/null || true

# 3. Restore user data
echo "[2/4] Restoring /home data..."
restic --repo "$REPO" restore "$RESTORE_DATE" \
    --target "$MOUNT_POINT" --include "/home"
cp -a "$MOUNT_POINT/home/." /home/ 2>/dev/null || true

# 4. Restore application data
echo "[3/4] Restoring /var/www and /opt/app..."
restic --repo "$REPO" restore "$RESTORE_DATE" \
    --target "$MOUNT_POINT" --include "/var/www"
cp -a "$MOUNT_POINT/var/www/." /var/www/ 2>/dev/null || true

restic --repo "$REPO" restore "$RESTORE_DATE" \
    --target "$MOUNT_POINT" --include "/opt/app"
cp -a "$MOUNT_POINT/opt/app/." /opt/app/ 2>/dev/null || true

# 5. Verify recovery
echo "[4/4] Verifying recovery integrity..."
restic --repo "$REPO" check

echo "=== Recovery Complete ==="
echo "Please check the following directories:"
echo "  /etc     - System configs"
echo "  /home    - User data"
echo "  /var/www - Web applications"
echo "  /opt/app - Other applications"
```

### Recovery Drill Checklist

| Item | Frequency | Verification Method |
|------|-----------|-------------------|
| Single file restore | Weekly | Randomly select a file, restore and compare |
| Directory restore | Monthly | Restore /etc to a temp directory |
| Full system restore | Quarterly | Complete restore on a new VPS and start services |
| Offsite restore | Bi-annually | Restore from remote backup server |

---

## Advanced: Database-Specific Backups

### MySQL/MariaDB Backup

```bash
#!/bin/bash
# /usr/local/bin/mysql-backup.sh

DB_USER="backup_user"
DB_PASS="your-db-password"
BACKUP_DIR="/backup/databases"
DATE=$(date +%Y%m%d-%H%M%S)

mkdir -p "$BACKUP_DIR"

# Get all database names
dbs=$(mysql -u "$DB_USER" -p"$DB_PASS" -e "SHOW DATABASES;" \
    | grep -Ev "(Database|information_schema|performance_schema)")

# Backup each database
for db in $dbs; do
    mysqldump -u "$DB_USER" -p"$DB_PASS" \
        --single-transaction --routines --triggers \
        "$db" | gzip > "$BACKUP_DIR/${db}-${DATE}.sql.gz"
    echo "Backed up: $db"
done

# Keep only last 30 days of backups
find "$BACKUP_DIR" -name "*.sql.gz" -mtime +30 -delete
```

### PostgreSQL Backup

```bash
#!/bin/bash
# /usr/local/bin/pgbackup.sh

PGUSER="backup_user"
BACKUP_DIR="/backup/databases"
DATE=$(date +%Y%m%d-%H%M%S)

mkdir -p "$BACKUP_DIR"

# Backup all databases
pg_dumpall -U "$PGUSER" | gzip > "$BACKUP_DIR/all-dbs-${DATE}.sql.gz"

# Keep only last 30 days
find "$BACKUP_DIR" -name "*.sql.gz" -mtime +30 -delete
```

---

## Security Hardening

### Backup Encryption

```bash
# Restic has built-in AES-256 encryption with independently managed keys
# Store passwords in a secure key management system (e.g., HashiCorp Vault)

# Harden backup repo permissions
chmod 700 /backup/local
chown -R root:root /backup/local
```

### Key Management

```bash
# Use SSH keys instead of passwords (more secure)
# Generate dedicated backup key on master server
ssh-keygen -t ed25519 -C "backup-key" -f /root/.ssh/restic_backup -N ""

# Disable password login, allow only key authentication
# /etc/ssh/sshd_config
PasswordAuthentication no
PubkeyAuthentication yes
```

### Ransomware Protection

```bash
# Use immutable attribute to protect backups (even root can't delete)
chattr +i /backup/local

# Unlock → backup → lock cycle
chattr -i /backup/local
restic backup ...
chattr +i /backup/local
```

---

## Cost Estimation

| Component | Monthly Cost (Estimate) | Notes |
|-----------|------------------------|-------|
| Local SSD storage (100GB) | $0 (already have VPS) | LVM snapshots |
| Remote backup server (50GB) | $5-10 | Minimal VPS config |
| S3-compatible object storage | $2-5 | Pay-per-usage |
| Bandwidth | $1-3 | Incremental backups use little traffic |
| **Total** | **$8-18/month** | Far cheaper than data loss |

---

## Summary

A solid backup and disaster recovery system comes down to three things:

1. **Automation**: Humans forget, but scripts don't. Ensure backup tasks run automatically with automatic notifications.
2. **Multi-layered**: Local snapshots + incremental backups + offsite failover — each layer addresses different risks.
3. **Verifiable**: Regular recovery drills are the only way to confirm your backups actually work.

Data is priceless, and building this system costs about as much as a takeout meal. **Spend 10 minutes configuring backups today, and you might save your entire business tomorrow.**

Take action now — run a backup, then try restoring a file. Your future self will thank you.
