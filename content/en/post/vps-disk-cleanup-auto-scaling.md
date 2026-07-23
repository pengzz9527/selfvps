---
title: "VPS Disk Space Cleanup & Auto-Scaling — The Complete Guide to Eliminating Storage Anxiety"
date: 2026-07-23
description: "From manual cleanup to automated monitoring, learn how to keep your VPS disk healthy at minimum cost."
tags: [vps, disk management, auto-scaling, operations]
category: "VPS Operations"
image: "/images/posts/vps-disk-cleanup-auto-scaling/featured.png"
---

## Why Disk Space Is the VPS's Biggest Silent Killer

Many VPS users have experienced this scenario: one day suddenly your website won't load, SSH connection fails, and you discover—**the disk is full**.

A full disk is more than just "can't store files." It causes:
- **Database write failures** (MySQL/PostgreSQL throws errors)
- **Logs can't be written** (system logs pile up, making troubleshooting impossible)
- **Web services crash** (Nginx/Apache can't generate temporary files)
- **System boot anomalies** (swap partition becomes unusable)

This guide walks you through building a complete solution from **manual cleanup → monitoring alerts → automatic scaling**.

---

## Step 1: Quickly Identify What's Eating Your Disk

### Check Overall Usage

```bash
df -h
```

Example output:
```
Filesystem      Size  Used Avail Use% Mounted on
/dev/sda1        50G   47G  3.0G  94% /
tmpfs           1.6G     0  1.6G   0% /dev/shm
```

### Find Large Files and Directories

```bash
# See directory usage (in MB)
du -sh /* | sort -rh | head -20

# Dig into a specific directory
du -sh /var/* | sort -rh | head -10
```

### Common "Dirt Hiding Spots"

| Location | Common Issue | Cleanup Method |
|----------|-------------|----------------|
| `/var/log` | Log file accumulation | `journalctl --vacuum-size=100M` |
| `/var/cache/apt` | Package cache | `apt clean` |
| `~/.local/share/Trash` | Empty trash not cleared | `rm -rf ~/.local/share/Trash/*` |
| `/tmp` | Temp files not cleaned | `sudo rm -rf /tmp/*` |
| Docker | Dangling images and build cache | `docker system prune -a` |

---

## Step 2: Automated Cleanup Script

Create an automated cleanup script at `/usr/local/bin/disk-cleanup.sh`:

```bash
#!/bin/bash

LOG_FILE="/var/log/disk-cleanup.log"
THRESHOLD=80

echo "$(date): Starting disk cleanup..." >> $LOG_FILE

# 1. Clean apt/yum cache
apt-get clean && apt-get autoremove -y >> $LOG_FILE 2>&1

# 2. Clean journal logs (keep last 7 days)
journalctl --vacuum-time=7d >> $LOG_FILE 2>&1

# 3. Clean system logs
find /var/log -name "*.gz" -delete
find /var/log -name "*.old" -delete
find /var/log -size +100M -exec truncate -s 0 {} \;

# 4. Clean Docker
docker system prune -af >> $LOG_FILE 2>&1

# 5. Clean temp files
find /tmp -type f -atime +3 -delete
find /var/tmp -type f -atime +3 -delete

# Check remaining space after cleanup
USE_PERCENT=$(df / | tail -1 | awk '{print $5}' | sed 's/%//')
echo "$(date): Disk usage after cleanup: ${USE_PERCENT}%" >> $LOG_FILE

# Alert if still above threshold
if [ "$USE_PERCENT" -ge "$THRESHOLD" ]; then
    echo "$(date): WARNING - Disk usage still above ${THRESHOLD}%!" >> $LOG_FILE
    # Add email or webhook notification here
fi
```

Set it to run automatically every week:

```bash
chmod +x /usr/local/bin/disk-cleanup.sh
crontab -e
# Add: 0 3 * * 0 /usr/local/bin/disk-cleanup.sh
```

---

## Step 3: Disk Usage Monitoring & Alerts

### Using Prometheus + Node Exporter

```yaml
# docker-compose.yml
version: '3'
services:
  prometheus:
    image: prom/prometheus
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - prom_data:/prometheus

  node_exporter:
    image: prom/node-exporter
    ports:
      - "9100:9100"
    restart: unless-stopped

volumes:
  prom_data:
```

```yaml
# prometheus.yml
global:
  scrape_interval: 30s

scrape_configs:
  - job_name: 'node'
    static_configs:
      - targets: ['localhost:9100']
```

### Simple Shell Alert Script

```bash
#!/bin/bash
THRESHOLD=85
WEBHOOK_URL="https://your-webhook-url"

USE_PERCENT=$(df / | tail -1 | awk '{print $5}' | sed 's/%//')

if [ "$USE_PERCENT" -ge "$THRESHOLD" ]; then
    curl -X POST $WEBHOOK_URL \
        -H 'Content-Type: application/json' \
        -d "{\"text\":\"⚠️ VPS disk usage has reached ${USE_PERCENT}%\"}"
fi
```

---

## Step 4: Online Disk Expansion

When cleanup isn't fast enough, what you need is **expansion**.

### Cloud Provider Online Expansion

Most cloud platforms support online expansion:
1. Go to console → Cloud Server → Disk Management
2. Click "Expand", choose new capacity
3. Log in to server and execute:

```bash
# 1. View current disk partitions
lsblk

# 2. Expand partition (using /dev/sda as example)
growpart /dev/sda 1

# 3. Expand filesystem
# ext4:
resize2fs /dev/sda1
# xfs:
xfs_growfs /

# 4. Verify
df -h
```

### Use LVM for Flexible Expansion

If your VPS uses LVM (Logical Volume Manager), expansion is straightforward:

```bash
# 1. Extend physical volume
pvresize /dev/sda1

# 2. Extend logical volume
lvextend -l +100%FREE /dev/mapper/vg0-root

# 3. Extend filesystem
resize2fs /dev/mapper/vg0-root
```

---

## Step 5: Preventive Strategies

### 1. Log Rotation Configuration

Edit `/etc/logrotate.conf`:

```
/var/log/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 0640 root adm
}
```

### 2. Limit Docker Disk Usage

```bash
# /etc/docker/daemon.json
{
    "storage-driver": "overlay2",
    "log-driver": "json-file",
    "log-opts": {
        "max-size": "10m",
        "max-file": "3"
    },
    "data-root": "/var/lib/docker"
}
```

Restart Docker: `systemctl restart docker`

### 3. Regular Disk Health Checks

```bash
# Check SMART status
smartctl -a /dev/sda

# Check filesystem errors
e2fsck -n /dev/sda1
```

---

## Summary

| Stage | Action | Frequency |
|-------|--------|-----------|
| Manual cleanup | `du` / `df` / `apt clean` | Monthly |
| Automated cleanup | Cron script | Weekly |
| Monitoring alerts | Prometheus / Shell script | Real-time |
| Online expansion | Cloud platform console | On-demand |

**Core principle: Don't wait until the disk is full to act.** Build a closed loop of "monitor → alert → cleanup → expand" to keep your VPS running stably over the long term.

---

*This guide applies to all Linux VPS providers — whether you're using Alibaba Cloud, Tencent Cloud, AWS, or DigitalOcean.*
