---
title: "VPS Automated Backup & Disaster Recovery: From Bare Metal to Data Peace of Mind"
subtitle: "Complete automated backup system for self-hosted VPS environments"
date: 2026-07-17
description: "Build a complete automated backup system for your VPS covering databases, files, and configurations with rclone + crontab for offsite disaster recovery."
tags: ["vps", "backup", "rclone", "disaster-recovery", "automation", "self-hosted"]
categories: ["Operations Guide"]
image: /images/posts/vps-backup-disaster-recovery/featured.png
draft: false
---

## Introduction

In self-hosting and VPS operations, **data is the lifeline**. Whether it's a personal blog, home NAS, or production service — without backups, a single disk failure, provider shutdown, or ransomware attack means starting from zero.

This guide provides a **complete, automated, cost-effective** VPS backup and disaster recovery solution so you can sleep soundly.

---

## 1. Backup Strategy: The 3-2-1 Rule

The industry golden rule — **3-2-1 Backup Principle**:

| Element | Description |
|---------|-------------|
| **3** copies | Original data + at least 2 backups |
| **2** media types | Local disk + remote object storage |
| **1** offsite | At least one backup in a different geographic location |

For individual VPS users, we simplify this to: **local snapshot + cloud sync**.

---

## 2. Core Toolchain

```
┌─────────────┐    ┌──────────────┐    ┌──────────────────┐
│   Cron Job   │───▶│ Backup Script│───▶│ Rclone Sync      │
│ (Scheduled)  │    │ (Archive)    │    │ (Encrypted→S3)   │
└─────────────┘    └──────────────┘    └──────────────────┘
                                                        │
                                                        ▼
                                              ┌──────────────────┐
                                              │  AWS S3 / Backblaze│
                                              │  / Cloudflare R2   │
                                              └──────────────────┘
```

### 2.1 Installing and Configuring rclone

```bash
# Install rclone
curl https://rclone.org/install.sh | sudo bash

# Configure remote storage (using Cloudflare R2 as example)
rclone config
# Select new remote → s3 → provider: Other
# Access key: your-R2-access-key
# Secret key: your-R2-secret-key
# endpoint: https://account-id.r2.cloudflarestorage.com
```

> **Money-saving tip**: Cloudflare R2 has zero egress fees, $0.015/GB/month storage — ideal for VPS backups. Backblaze B2 is equally cheap ($0.006/GB/month).

### 2.2 Automated Backup Script

Create `/usr/local/bin/vps-backup.sh`:

```bash
#!/bin/bash
# Full VPS backup script
set -euo pipefail

DATE=$(date +%Y%m%d-%H%M%S)
BACKUP_DIR="/tmp/backups"
REMOTE_BUCKET="r2:vps-backups-$(hostname)"
RETENTION_DAYS=30

mkdir -p "$BACKUP_DIR/$DATE"

# ========== 1. Backup Databases ==========
echo "[$(date)] Starting database backup..."
for db in $(mysql -e 'SHOW DATABASES;' --skip-column-names | grep -Ev '^(information_schema|performance_schema)$'); do
    mysqldump --single-transaction --routines --triggers "$db" \
        > "$BACKUP_DIR/$DATE/${db}.sql"
done

# ========== 2. Backup Configuration Files ==========
echo "[$(date)] Backing up system configs..."
tar czf "$BACKUP_DIR/$DATE/etc-backup.tar.gz" \
    /etc/hosts /etc/crontab /etc/fstab \
    /etc/nginx/ /etc/ssl/ /etc/dovecot/ 2>/dev/null || true

# ========== 3. Backup Web Content ==========
echo "[$(date)] Backing up website files..."
tar czf "$BACKUP_DIR/$DATE/web-content.tar.gz" \
    /var/www/html/ /home/*/public_html/ 2>/dev/null || true

# ========== 4. Package and Compress ==========
echo "[$(date)] Creating final backup archive..."
cd "$BACKUP_DIR"
tar czf "${DATE}-full.tar.gz" "$DATE"
rm -rf "$DATE"

# ========== 5. Upload to Cloud ==========
echo "[$(date)] Uploading to remote storage..."
rclone copy "${DATE}-full.tar.gz" "$REMOTE_BUCKET/latest/" \
    --transfers=2 --checkers=4 \
    --s3-chunk-size=64M \
    --progress

# ========== 6. Clean Old Local Backups ==========
echo "[$(date)] Cleaning local backups older than ${RETENTION_DAYS} days..."
find "$BACKUP_DIR" -name "*.tar.gz" -mtime +${RETENTION_DAYS} -delete

# ========== 7. Remote Cleanup ==========
echo "[$(date)] Cleaning expired remote backups..."
rclone delete "$REMOTE_BUCKET/old/" --max-age 30d || true
mv "$REMOTE_BUCKET/latest/" "$REMOTE_BUCKET/old/" 2>/dev/null || true
mkdir -p "$REMOTE_BUCKET/latest/"

echo "[$(date)] Backup complete! File size: $(du -h "${DATE}-full.tar.gz" | cut -f1)"
```

### 2.3 Setting Up Cron Jobs

```bash
crontab -e

# Full backup daily at 2 AM
0 2 * * * /usr/local/bin/vps-backup.sh >> /var/log/vps-backup.log 2>&1

# Incremental backup every Sunday at 3 AM (better with restic)
0 3 * * 0 /usr/local/bin/vps-backup.sh --incremental >> /var/log/vps-backup.log 2>&1
```

---

## 3. Advanced: Encrypted Backups with Restic

For higher security requirements, use **Restic**:

```bash
# Install restic
sudo apt install restic

# Initialize repository
restic init --repo s3:s3.us-east-1.amazonaws.com/mybucket \
    --password-file ~/.restic-password

# Backup entire system
restic backup / --exclude=/proc/* --exclude=/sys/* \
    --tag daily-backup \
    -r s3:s3.us-east-1.amazonaws.com/mybucket

# View backup history
restic snapshots -r s3:s3.us-east-1.amazonaws.com/mybucket

# Restore a single file
restic restore latest -r s3:s3.us-east-1.amazonaws.com/mybucket \
    --target /tmp/recovered
```

**Why Restic?**
- 🔒 End-to-end encryption — even if cloud storage is breached, data stays safe
- 🧬 Deduplication — saves significant storage space
- ⚡ Incremental backups — only transfers changed data
- 📋 Rich restore options (by time, tag, path)

---

## 4. Disaster Recovery Drills

Backups that aren't tested are no backups at all. Schedule quarterly recovery drills:

```bash
# 1. Provision a new VPS
# 2. Install base OS
# 3. Download latest backup
rclone copy "$REMOTE_BUCKET/latest/" ./restore-latest/

# 4. Extract and verify
tar xzf restore-latest/*.tar.gz
ls restore-latest/

# 5. Step-by-step restoration
#    a. Restore configuration files
#    b. Import databases
#    c. Deploy web content
#    d. Verify services running correctly
```

---

## 5. Monitoring and Alerting

Ensure your backups are actually working:

```bash
# Add health check at the end of your backup script
if [ $? -eq 0 ]; then
    echo "$(date): ✅ Backup successful" >> /var/log/vps-backup.log
else
    echo "$(date): ❌ Backup failed!" >> /var/log/vps-backup.log
    # Send alert notification (email/Telegram/Webhook)
    curl -X POST "https://api.telegram.org/bot${TG_TOKEN}/sendMessage" \
        -d "chat_id=${CHAT_ID}" \
        -d "text=⚠️ VPS backup failed! Please check immediately."
fi
```

---

## 6. Cost Estimation

| Item | Monthly Cost |
|------|-------------|
| VPS (8GB RAM) | ~$6-20 |
| Cloudflare R2 (50GB) | ~$0.75 |
| Domain | ~$10/year |
| **Total** | **~$1-3/day** |

---

## Summary

Building a robust backup system doesn't require complex infrastructure. Key takeaways:

1. ✅ **Automate**: Use crontab + scripts for hands-free operation
2. ✅ **Offsite**: Sync to S3-compatible storage with rclone
3. ✅ **Encrypt**: Restic provides end-to-end encryption
4. ✅ **Drill Quarterly**: Test recovery at least once per quarter
5. ✅ **Monitor & Alert**: Get notified immediately on backup failure

> **"Backups aren't an optional feature — they're the foundation of infrastructure."**
