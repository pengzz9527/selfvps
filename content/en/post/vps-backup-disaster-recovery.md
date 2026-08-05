---
title: "VPS Backup & Disaster Recovery Complete Guide: From Bare Metal to Data Peace of Mind"
description: "Build a complete VPS backup system from scratch, covering database, files, and Docker volume backups, with one-click disaster recovery for ultimate data safety."
date: 2026-08-05T10:00:00+08:00
lastmod: 2026-08-05T10:00:00+08:00
slug: "vps-backup-disaster-recovery"
image: /images/posts/vps-backup-disaster-recovery/featured.png
tags: ["VPS", "backup", "disaster recovery", "Restic", "Docker", "automation", "data safety", "DevOps"]
categories: ["Operations"]
aliases: [/en/post/vps-backup-disaster-recovery/]
---

## Introduction

Data is the most valuable asset on your VPS. Whether you're running a personal blog, business website, or API service, data loss recovery costs can be dozens of times higher than building a proper backup system.

Have you experienced these nightmares?

- Disk failure destroys all data instantly
- Accidentally deleted the database with no backup
- Ransomware encrypted all your files
- Cloud provider downtime with slow recovery

**A VPS without backup is like a house without insurance** — you might be fine for years, but one incident can destroy everything.

This guide will help you build a complete VPS backup and disaster recovery system with:

1. **Automated backups**: Scheduled execution without manual intervention
2. **Multi-storage strategy**: Local + remote dual protection
3. **Fast recovery**: One-click restore to any point in time
4. **Disaster recovery**: Full system backup and rapid rebuild

---

## Backup Strategy Design

### 3-2-1 Backup Rule

The industry standard is the **3-2-1 backup rule**:

- **3 copies of data**: Original + 2 backups
- **2 storage media**: e.g., local disk + cloud storage
- **1 offsite copy**: Prevents single point of failure

```
┌─────────────────────────────────────────────────────┐
│                    VPS (Production)                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐           │
│  │  Database │  │  Website  │  │ Docker   │           │
│  │           │  │  Files    │  │ Volumes  │           │
│  └─────┬────┘  └─────┬────┘  └─────┬────┘           │
│        │             │             │                 │
│        └──────────────┼──────────────┘                 │
│                       │                               │
│              ┌────────▼────────┐                       │
│              │   Restic Backup  │                       │
│              └────────┬────────┘                       │
│                       │                               │
│          ┌────────────┼────────────┐                  │
│          │            │            │                  │
│    ┌─────▼────┐ ┌─────▼────┐ ┌─────▼────┐            │
│    │Local SSD │ │ S3 Compat│ │ AWS S3   │            │
│    │ /backup  │ │  MinIO   │ │ (Offsite) │            │
│    └─────────┘ └──────────┘ └──────────┘            │
└─────────────────────────────────────────────────────┘
```

### Backup Object Classification

| Data Type | Backup Strategy | Frequency | Retention |
|-----------|----------------|----------|-----------|
| Database | Logical backup (mysqldump/pg_dump) | Hourly | 30 days |
| Website files | Restic encrypted backup | Daily | 7 days full + 30 days incremental |
| Docker volumes | Restic backup | Daily | 7 days full + 30 days incremental |
| System config | rsync sync | Daily | 7 days |
| Full system image | Timeshift | Weekly | 4 weeks |

---

## Part 1: Database Backup

### MySQL/MariaDB Backup

#### Option 1: Logical Backup (mysqldump)

```bash
#!/bin/bash
# mysql-backup.sh

BACKUP_DIR="/backup/mysql"
DATE=$(date +%Y%m%d_%H%M%S)
RETAIN_DAYS=30

# Create backup directory
mkdir -p $BACKUP_DIR/$DATE

# Backup all databases
mysqldump --all-databases \
  --single-transaction \
  --routines \
  --triggers \
  --events \
  --quick \
  | gzip > $BACKUP_DIR/$DATE/all-databases.sql.gz

# Backup each database separately
for db in $(mysql -e 'SHOW DATABASES' -s --skip-column-names | grep -v '^information_schema$' | grep -v '^performance_schema$'); do
  mysqldump --single-transaction --routines --triggers "$db" \
    | gzip > $BACKUP_DIR/$DATE/${db}.sql.gz
done

# Delete expired backups
find $BACKUP_DIR -type d -mtime +$RETAIN_DAYS -exec rm -rf {} \; 2>/dev/null

# Upload to remote storage
restic -r s3:s3.amazonaws.com/your-bucket/backup/mysql backup $BACKUP_DIR/$DATE

echo "[$(date)] MySQL backup completed: $DATE"
```

#### Option 2: Physical Backup (Percona XtraBackup)

For large databases, physical backup is faster:

```bash
# Install Percona XtraBackup
sudo apt-get install -y percona-xtrabackup-80

# Hot backup
xtrabackup --backup \
  --target-dir=/backup/mysql/physical/$(date +%Y%m%d_%H%M%S) \
  --user=root \
  --password=your_password

# Prepare backup (make it consistent)
xtrabackup --prepare --target-dir=/backup/mysql/physical/20260805_100000
```

### PostgreSQL Backup

#### Logical Backup (pg_dump)

```bash
#!/bin/bash
# pg-backup.sh

BACKUP_DIR="/backup/postgres"
DATE=$(date +%Y%m%d_%H%M%S)
RETAIN_DAYS=30

mkdir -p $BACKUP_DIR/$DATE

# Backup all databases
pg_dumpall -h localhost | gzip > $BACKUP_DIR/$DATE/all-databases.sql.gz

# Backup each database
for db in $(psql -lqt | cut -d \| -f 1 | grep -v '^$\|^Name$' | grep -v 'template[01]'); do
  pg_dump "$db" | gzip > $BACKUP_DIR/$DATE/${db}.sql.gz
done

# Clean expired backups
find $BACKUP_DIR -type d -mtime +$RETAIN_DAYS -exec rm -rf {} \; 2>/dev/null

echo "[$(date)] PostgreSQL backup completed: $DATE"
```

#### Continuous Archival (WAL Archival)

For Point-in-Time Recovery (PITR):

```bash
# postgresql.conf configuration
wal_level = replica
archive_mode = on
archive_command = 'restic -r s3:s3.amazonaws.com/your-bucket/wal archive %p'
```

```bash
# Periodic full backup
pg_backup_schedule="0 2 * * * pg_basebackup -D /backup/postgres/base/$(date +%Y%m%d) -Ft -z"
```

---

## Part 2: File Backup

### Restic: Modern Backup Tool

[Restic](https://restic.net/) is one of the most recommended backup tools today, supporting:

- Incremental backups (only backed up changed data)
- End-to-end encryption
- Deduplication (saves space)
- Multiple backends (local, S3, SFTP, Azure, etc.)

#### Install Restic

```bash
# Ubuntu/Debian
wget https://github.com/restic/restic/releases/download/v0.16.1/restic_0.16.1_amd64.deb
sudo dpkg -i restic_0.16.1_amd64.deb

# Or compile from source
go install github.com/restic/restic@latest
```

#### Initialize Repository

```bash
# Local repository
restic -r /backup/repos/main init

# S3 compatible storage (e.g., MinIO)
export RESTIC_REPOSITORY=s3:s3.minio.local:9000/vps-backup
export AWS_ACCESS_KEY_ID=your_access_key
export AWS_SECRET_ACCESS_KEY=your_secret_key
restic init

# AWS S3
export RESTIC_REPOSITORY=s3:s3.amazonaws.com/your-bucket/vps-backup
restic init
```

#### Backup Website Files

```bash
#!/bin/bash
# file-backup.sh

export RESTIC_REPOSITORY=s3:s3.amazonaws.com/your-bucket/vps-backup
export RESTIC_PASSWORD=your_secure_password

# Backup website directory
restic backup /var/www/html --exclude='*.tmp' --exclude='cache/*'

# Backup configuration files
restic backup /etc/nginx /etc/ssl /root/.ssh

# Backup Docker configuration
restic backup /opt/docker-compose /root/docker

# Add tags to snapshots
restic tag add --tag=website /var/www/html

# Clean old snapshots (keep last 7 days)
restic forget --keep-daily=7 --keep-weekly=4 --keep-monthly=12 --prune
```

#### Backup Docker Volumes

```bash
#!/bin/bash
# docker-backup.sh

export RESTIC_REPOSITORY=s3:s3.amazonaws.com/your-bucket/vps-backup
export RESTIC_PASSWORD=your_secure_password

# Backup all Docker volumes
for vol in $(docker volume ls -q); do
  restic backup \
    --exclude='*.log' \
    /var/lib/docker/volumes/$vol/_data \
    --tag=$vol
done

# Or use standard Docker volume backup method
docker run --rm \
  -v backup-data:/data \
  -v /var/lib/docker/volumes:/backup \
  alpine tar czf /data/backup-$(date +%Y%m%d).tar.gz /backup
```

---

## Part 3: Automated Backups

### Cron Scheduled Tasks

```bash
# Edit crontab
crontab -e

# Add the following tasks
# Backup database hourly on weekdays
0 * * * * /opt/scripts/mysql-backup.sh >> /var/log/backup/mysql.log 2>&1

# Backup files daily at 2 AM
0 2 * * * /opt/scripts/file-backup.sh >> /var/log/backup/file.log 2>&1

# Backup system config weekly on Sunday at 3 AM
0 3 * * 0 /opt/scripts/config-backup.sh >> /var/log/backup/config.log 2>&1

# Full system backup monthly on 1st at 4 AM
0 4 1 * * /opt/scripts/full-backup.sh >> /var/log/backup/full.log 2>&1
```

### Complete Backup Script Example

```bash
#!/bin/bash
# full-backup.sh - Complete backup script

set -euo pipefail

# Configuration
BACKUP_ROOT="/backup/full/$(date +%Y%m%d_%H%M%S)"
RESTIC_REPO="s3:s3.amazonaws.com/your-bucket/vps-backup"
RESTIC_PASSWORD="your_secure_password"
LOG_FILE="/var/log/backup/full-$(date +%Y%m%d).log"

# Logging function
log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# Error handling
trap 'log "ERROR: Backup failed at line $LINENO"; exit 1' ERR

log "=== Starting full backup ==="

# 1. Create backup directories
mkdir -p $BACKUP_ROOT/{mysql,postgres,files,config,docker}

# 2. Database backup
log "Backing up MySQL..."
mysqldump --all-databases --single-transaction | \
  gzip > $BACKUP_ROOT/mysql/all-databases.sql.gz

log "Backing up PostgreSQL..."
pg_dumpall | gzip > $BACKUP_ROOT/postgres/all-databases.sql.gz

# 3. File backup (using Restic)
log "Backing up website files..."
export RESTIC_REPOSITORY=$RESTIC_REPO
export RESTIC_PASSWORD=$RESTIC_PASSWORD

restic backup /var/www/html --tag=website >> $LOG_FILE 2>&1
restic backup /etc --tag=config >> $LOG_FILE 2>&1
restic backup /opt/docker-compose --tag=docker >> $LOG_FILE 2>&1

# 4. System config sync
log "Syncing system configuration..."
rsync -avz --delete /etc/ $BACKUP_ROOT/config/etc/ >> $LOG_FILE 2>&1
rsync -avz /root/.ssh/ $BACKUP_ROOT/config/ssh/ >> $LOG_FILE 2>&1

# 5. Clean old backups
log "Cleaning expired backups..."
find $BACKUP_ROOT -type f -mtime +30 -delete 2>/dev/null || true

# 6. Verify backup
log "Verifying backup integrity..."
restic check >> $LOG_FILE 2>&1

# 7. Generate backup report
BACKUP_SIZE=$(du -sh $BACKUP_ROOT | cut -f1)
SNAPSHOT_COUNT=$(restic snapshots | wc -l)

log "=== Backup completed ==="
log "Backup size: $BACKUP_SIZE"
log "Snapshot count: $SNAPSHOT_COUNT"
log "Backup location: $BACKUP_ROOT"

# Send notification
curl -X POST "https://api.telegram.org/bot${TG_BOT_TOKEN}/sendMessage" \
  -d "chat_id=${TG_CHAT_ID}" \
  -d "text=✅ VPS Backup Completed\n📦 Size: $BACKUP_SIZE\n📸 Snapshots: $SNAPSHOT_COUNT"
```

---

## Part 4: Disaster Recovery

### Restore Single Database

```bash
# MySQL restore
gunzip < /backup/mysql/20260805_100000/all-databases.sql.gz | mysql

# PostgreSQL restore
gunzip < /backup/postgres/20260805_100000/all-databases.sql.gz | psql

# Restore to specific point in time (requires WAL archival)
pg_restore -d postgres -c \
  --dbname=template1 \
  /backup/postgres/base/20260805/base.tar.gz
```

### Restore with Restic

```bash
# List all snapshots
restic snapshots

# Restore entire backup
restic restore latest --target=/restore

# Restore specific directory
restic restore latest --target=/restore --include=/var/www/html

# Restore single file
restic restore snapshot-id --target=/tmp --include=/var/www/html/index.html

# Interactive restore
restic restore latest --target=/restore --interactive
```

### Full System Recovery Process

When your VPS is completely damaged, use these steps to recover quickly:

#### Step 1: Rebuild System

```bash
# 1. Reinstall operating system
# 2. Install required software
sudo apt-get update
sudo apt-get install -y docker.io nginx mysql-server postgresql restic

# 3. Configure Restic
export RESTIC_REPOSITORY=s3:s3.amazonaws.com/your-bucket/vps-backup
export RESTIC_PASSWORD=your_secure_password
```

#### Step 2: Restore Data

```bash
#!/bin/bash
# disaster-recovery.sh

# 1. Restore website files
restic restore latest \
  --target=/var/www \
  --include=/var/www/html

# 2. Restore databases
gunzip < /backup/mysql/latest/all-databases.sql.gz | mysql
gunzip < /backup/postgres/latest/all-databases.sql.gz | psql

# 3. Restore Docker configuration
docker compose -f /opt/docker-compose/docker-compose.yml up -d

# 4. Restore system configuration
rsync -avz /backup/config/etc/ /etc/
rsync -avz /backup/config/ssh/ /root/.ssh/

# 5. Restart services
systemctl restart nginx mysql postgresql docker
```

#### Step 3: Verify Recovery

```bash
# Check service status
systemctl status nginx mysql postgresql docker

# Verify backup integrity
restic check
restic snapshots

# Verify website access
curl -I https://yourdomain.com

# Verify database connection
mysql -e "SHOW DATABASES;"
psql -c "\l"
```

---

## Part 5: Monitoring & Alerting

### Backup Health Check

```bash
#!/bin/bash
# backup-monitor.sh

LOG_FILE="/var/log/backup/monitor.log"

# Check latest backups
LATEST_MYSQL=$(find /backup/mysql -type d -mtime -1 | head -1)
LATEST_FILE=$(restic snapshots --tag=website | head -1)

if [ -z "$LATEST_MYSQL" ]; then
  echo "[$(date)] ERROR: No MySQL backup in last 24 hours" | tee -a $LOG_FILE
  # Send alert
  curl -X POST "https://api.telegram.org/bot${TG_BOT_TOKEN}/sendMessage" \
    -d "chat_id=${TG_CHAT_ID}" \
    -d "text=❌ MySQL backup failed!"
fi

if [ -z "$LATEST_FILE" ]; then
  echo "[$(date)] ERROR: No file backup in last 24 hours" | tee -a $LOG_FILE
fi

# Check backup size anomaly
BACKUP_SIZE=$(du -sh /backup/full/latest 2>/dev/null | cut -f1)
if [ "$BACKUP_SIZE" = "0" ] || [ -z "$BACKUP_SIZE" ]; then
  echo "[$(date)] ERROR: Backup size is zero!" | tee -a $LOG_FILE
fi
```

### Prometheus + Grafana Monitoring

```yaml
# node_exporter collects backup metrics
# backup_metrics.yml
backup_duration_seconds:
  help: "Duration of last backup"
backup_failures_total:
  help: "Total number of backup failures"
backup_size_bytes:
  help: "Size of last backup"
```

---

## Part 6: Best Practices

### 1. Encrypt Backups

```bash
# Use Restic built-in encryption
export RESTIC_PASSWORD=$(openssl rand -base64 32)

# Or use GPG encryption
gpg --encrypt --recipient your@email.com backup.sql
```

### 2. Test Recovery

Regularly test recovery processes to ensure backups are usable:

```bash
# Execute recovery test monthly
restic restore latest \
  --target=/tmp/test-restore \
  --exclude='*/proc/*' \
  --exclude='*/sys/*'

# Verify file integrity
md5sum -c /backup/checksums.md5
```

### 3. Monitor Storage Space

```bash
#!/bin/bash
# disk-monitor.sh

THRESHOLD=80
USAGE=$(df -h /backup | awk 'NR==2 {print $5}' | sed 's/%//')

if [ "$USAGE" -gt "$THRESHOLD" ]; then
  echo "Disk usage at ${USAGE}%! Cleaning old backups..."
  restic forget --keep-daily=3 --prune
fi
```

### 4. Secure Backup Keys

```bash
# Don't hardcode passwords in scripts
# Use environment variables or key management tools
echo "RESTIC_PASSWORD=$(openssl rand -base64 32)" >> ~/.bashrc

# Or use Vault
vault write secret/backup password=$(openssl rand -base64 32)
```

---

## Conclusion

Building a comprehensive backup and disaster recovery system is a core capability of VPS operations. Through this guide, you've learned:

1. **Design backup strategy**: Follow 3-2-1 rule, layer protection for different data types
2. **Implement database backup**: mysqldump/pg_dump + WAL archival
3. **Use Restic**: Modern backup tool with encryption, deduplication, and incremental support
4. **Automate workflow**: Cron + scripts for unattended backups
5. **Disaster recovery**: Full system backup + rapid rebuild process
6. **Monitoring and alerting**: Ensure backup system stays healthy

**Remember: The value of backup is not in the backup itself, but in successful recovery.** Regularly test your recovery process to ensure you can successfully restore data when you truly need it.

---

## Reference Resources

- [Restic Documentation](https://restic.net/documentation/)
- [MySQL Backup Best Practices](https://dev.mysql.com/doc/refman/8.0/en/backup-methods.html)
- [PostgreSQL Backup and Recovery](https://www.postgresql.org/docs/current/backup.html)
- [3-2-1 Backup Strategy](https://www.backblaze.com/blog/the-3-2-1-backup-strategy/)
