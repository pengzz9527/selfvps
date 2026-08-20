---
title: "VPS Scheduled Snapshots & Offsite Backups: Building an Automated Disaster Recovery System"
description: "From local snapshot strategies to offsite multi-replica backups, build a fully automated VPS disaster recovery system with zero manual intervention"
date: 2026-08-20T08:00:00+08:00
lastmod: 2026-08-20T08:00:00+08:00
slug: "vps-snapshot-disaster-recovery"
tags: ["VPS", "Disaster Recovery", "Snapshots", "Backup", "Restic", "Automation", "S3", "Cost Optimization"]
categories: ["Disaster Recovery"]
draft: false
image: /images/posts/vps-snapshot-disaster-recovery/featured.png
aliases: [/en/post/vps-snapshot-disaster-recovery/]
---

## Introduction

Have you ever lost critical data due to disk failure, accidental deletion, or cloud provider downtime? In self-hosting and VPS operations, **disaster recovery is not optional — it is the foundation of survival**.

Many operators only do local backups, ignoring the risk of a single point of failure — when the backup itself sits on the same disk, both data and backup are lost together upon hardware failure.

This article guides you from scratch to build a complete VPS disaster recovery system: **local snapshots + offsite backups + automated recovery**, with zero manual intervention.

## I. Core Principles of Disaster Recovery

### 1.1 The 3-2-1 Backup Rule

This is the industry standard for data protection:

- **3 copies of data**: original + 2 backups
- **2 different storage media**: local disk + cloud storage
- **1 offsite copy**: remotely located physical storage

### 1.2 RPO and RTO

| Metric | Meaning | Recommended Value |
|--------|---------|-------------------|
| RPO (Recovery Point Objective) | Max data loss tolerated | ≤ 1 hour |
| RTO (Recovery Time Objective) | Time to restore service | ≤ 30 minutes |

## II. Local Snapshot Strategy

### 2.1 Disk Snapshots (LVM/ZFS)

If your VPS uses LVM or ZFS, leverage native snapshot features:

```bash
# Create LVM snapshot
sudo lvcreate --size 1G --snapshot --name snap-$(date +%Y%m%d-%H%M) /dev/vg0/root

# Check snapshot status
sudo lvs -o +snap_percent

# Auto-clean snapshots older than 7 days
sudo lvremove -f /dev/vg0/snap-$(date -d '7 days ago' +%Y%m%d-%H%M)
```

### 2.2 System Snapshots with Timeshift

Timeshift is a Linux system-level snapshot tool, ideal for full system backups:

```bash
# Install Timeshift
sudo apt install timeshift

# Create a system snapshot
sudo timeshift --create --comments "auto-$(date +%Y%m%d)"

# Configure daily snapshots at 2 AM
sudo nano /etc/cron.d/timeshift-daily
# */0 2 * * * root /usr/bin/timeshift --create --comments "daily-$(date +\%Y\%m\%d)" --skip-lvm-restore
```

## III. Offsite Backups: Restic + S3

### 3.1 Why Choose Restic?

Restic is a next-generation backup tool with clear advantages over traditional tools:

- **Deduplication & compression**: stores identical files only once, saving 70%+ space
- **End-to-end encryption**: AES-256 encrypted transfers
- **Incremental backups**: only transfers changed data blocks
- **Cross-platform**: Linux / macOS / Windows

### 3.2 Initialize the Backup Repository

```bash
# Install Restic
curl -L https://github.com/restic/restic/releases/latest/download/restic_0.17.0_amd64.deb -o restic.deb
sudo dpkg -i restic.deb

# Initialize repository (S3-compatible storage)
export RESTIC_REPOSITORY=s3:s3.amazonaws.com/your-bucket-name
export RESTIC_PASSWORD=your-strong-password
export AWS_ACCESS_KEY_ID=xxx
export AWS_SECRET_ACCESS_KEY=xxx

# Create the repository
restic init
```

### 3.3 Backup Script

Create `~/scripts/backup.sh`:

```bash
#!/bin/bash
set -euo pipefail

export RESTIC_REPOSITORY=s3:s3.amazonaws.com/your-bucket-name
export RESTIC_PASSWORD=your-strong-password
export AWS_ACCESS_KEY_ID=xxx
export AWS_SECRET_ACCESS_KEY=xxx

BACKUP_DIRS=("/home" "/etc" "/var/www" "/opt/app")
LOG_FILE="/var/log/restic-backup.log"

echo "[$(date)] Starting backup..." | tee -a $LOG_FILE

for dir in "${BACKUP_DIRS[@]}"; do
    if [ -d "$dir" ]; then
        restic backup "$dir" --tag "$(date +%Y%m%d)" >> $LOG_FILE 2>&1
        echo "[$(date)] Backed up $dir" | tee -a $LOG_FILE
    fi
done

# Retain 30 days of snapshots, clean up expired ones
restic prune
restic forget --keep-daily 7 --keep-weekly 4 --keep-monthly 6

echo "[$(date)] Backup completed" | tee -a $LOG_FILE
```

### 3.4 Configure Scheduled Task

```bash
# Backup every 6 hours
echo "0 */6 * * * /root/scripts/backup.sh" | sudo tee /etc/cron.d/restic-backup
sudo chmod 644 /etc/cron.d/restic-backup
```

## IV. Monitoring & Alerting

### 4.1 Backup Health Check

```bash
#!/bin/bash
# ~/scripts/backup-health-check.sh

export RESTIC_REPOSITORY=s3:s3.amazonaws.com/your-bucket-name
export RESTIC_PASSWORD=your-strong-password
export AWS_ACCESS_KEY_ID=xxx
export AWS_SECRET_ACCESS_KEY=xxx

# Verify repository is accessible
if ! restic snapshots | grep -q "$(date +%Y-%m-%d)"; then
    echo "ALERT: No backup found for today!" | mail -s "Backup Alert" admin@yourdomain.com
    exit 1
fi

# Check for anomalous backup size
size=$(restic snapshots --json | jq '.[-1].stats.newBytes' 2>/dev/null || echo "0")
if [ "$size" -lt 1000 ]; then
    echo "ALERT: Backup size seems anomalously small: $size bytes" | mail -s "Backup Alert" admin@yourdomain.com
fi
```

### 4.2 Integrate with Prometheus

```yaml
# restic_exporter configuration
restic_exporter:
  repositories:
    - s3:s3.amazonaws.com/your-bucket-name
  environment:
    - RESTIC_PASSWORD=your-password
```

## V. Recovery Drills

### 5.1 Single File Recovery

```bash
# List all snapshots
restic snapshots

# Restore a single file
restic restore latest --target /tmp/recovered --include "/home/user/docs/report.pdf"

# Restore an entire directory
restic restore latest --target /tmp/recovered --include "/home/user"
```

### 5.2 Full System Recovery

```bash
# Install Restic and OS on new VPS
# Restore system data
restic restore latest --target /mnt/root

# Restore GRUB
grub-install /dev/vda
update-grub

# Reboot
reboot
```

### 5.3 Periodic Recovery Testing

```bash
# Monthly recovery drill
sudo crontab -e
# 0 3 1 * * restic restore latest --target /tmp/test-restore && echo "Recovery OK"
```

## VI. Cost Optimization

### 6.1 Choose Cost-Effective Storage

| Provider | Price (per GB/month) | Features |
|----------|---------------------|----------|
| AWS S3 Standard | $0.023 | Standard, reliable |
| AWS S3 Glacier | $0.00099 | Archive, 99.99% availability |
| Backblaze B2 | $0.005 | Cheapest object storage |
| Cloudflare R2 | $0.015 | Zero egress fees |

### 6.2 Compression & Deduplication

Restic enables deduplication and compression by default, typically reducing 100GB to 20-30GB. With `zstd`:

```bash
# Compress large files before backup
restic backup /data --compression=zstd
```

### 6.3 Lifecycle Policies

```bash
# Set S3 bucket lifecycle rules
# Transition to Glacier after 30 days, delete after 180
aws s3api put-bucket-lifecycle-configuration \
  --bucket your-bucket-name \
  --lifecycle-configuration '{
    "Rules": [
      {
        "ID": "archive-old-backups",
        "Status": "Enabled",
        "Transitions": [
          {"Days": 30, "StorageClass": "GLACIER"}
        ],
        "Expiration": {"Days": 180}
      }
    ]
  }'
```

## VII. Complete Automation

### 7.1 Daily Operations Script

```bash
#!/bin/bash
# ~/scripts/daily-ops.sh

set -euo pipefail

echo "=== Daily VPS Operations $(date) ==="

# 1. Run backup
~/scripts/backup.sh

# 2. Verify backup health
~/scripts/backup-health-check.sh

# 3. Clean old snapshots
restic forget --keep-daily 7 --keep-weekly 4 --keep-monthly 6 --prune

# 4. Check disk space
df -h | awk 'NR==1 || $5+0 > 80 {print "WARNING: "$0}'

# 5. Send daily report
~/scripts/send-daily-report.sh
```

### 7.2 Complete crontab

```bash
# Backup every 6 hours
0 */6 * * * /root/scripts/backup.sh >> /var/log/restic-backup.log 2>&1

# Daily health check
0 8 * * * /root/scripts/backup-health-check.sh

# Weekly snapshot verification (Sunday 3 AM)
0 3 * * 0 /usr/bin/restic snapshots | head -5

# Monthly recovery drill (1st of month, 4 AM)
0 4 1 * * /usr/bin/restic restore latest --target /tmp/monthly-test --dry-run
```

## Summary

Building a VPS disaster recovery system doesn't require complex infrastructure. The core principles are:

1. **Local snapshots** — fast recovery for accidental deletions
2. **Offsite backups** — prevent single-point-of-failure, survive hardware damage
3. **Automated execution** — scheduled tasks + health checks, zero manual intervention
4. **Regular drills** — untested recovery is no recovery at all

Remember: backup is not something you do "when you need it" — it's something you need "before you need it". Take 30 minutes today to set up Restic offsite backups, and tomorrow you will thank yourself.
