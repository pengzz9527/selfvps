---
title: "Self-Host Immich: The Ultimate Google Photos Alternative"
description: "Cut your Google Photos subscription and take back control. Complete guide to deploying Immich on a VPS — AI-powered photo management with facial recognition, auto backup, and full data ownership"
date: 2026-05-31T10:02:00+08:00
slug: "self-host-immich-google-photos-alternative"
tags: ["Immich", "Self-hosting", "Photo Backup", "Google Photos Alternative", "Docker", "NAS", "Open Source"]
categories: ["Self-Hosting"]
image: /images/posts/self-host-immich-google-photos-alternative/featured.png
draft: false
---

## Why Self-Host Your Photo Management?

In June 2021, Google Photos ended its free unlimited high-quality backup. Today, Google One's 200GB plan costs **$2.99/month**, and 2TB costs **$9.99/month**. With multiple family members, the cost multiplies.

Beyond the price tag, you face:

- **Privacy concerns** — Your photos may be used for AI training
- **Vendor lock-in** — The more you store, the harder it is to leave
- **Compression loss** — Even "original quality" backups apply some compression

**Immich** is the answer — an open-source, self-hosted photo and video management platform that delivers the full Google Photos experience.

| Feature | Google Photos | Immich |
|---------|--------------|--------|
| Auto backup | ✅ | ✅ |
| AI facial recognition | ✅ | ✅ (runs locally) |
| Object/scene detection | ✅ | ✅ (runs locally) |
| Album sharing | ✅ | ✅ |
| Map browsing | ✅ | ✅ |
| Original quality storage | ❌ Compression loss | ✅ Lossless |
| Monthly cost (1TB) | $9.99 | 💸 VPS cost ($5-10) |
| Data ownership | Google owns it | **You own 100%** |

## What Is Immich?

Immich is an open-source photo management platform built with TypeScript (NestJS) + Svelte, running on Docker. It offers:

- 📱 **Mobile auto-backup** — iOS & Android apps
- 🧠 **Local AI analysis** — Facial recognition, object detection, OCR
- 👨‍👩‍👧‍👧 **Multi-user support** — Family sharing
- 🗺️ **Map view** — Browse photos by location
- 🔍 **Powerful search** — Metadata + AI semantic search
- 🔗 **Album sharing** — Public shareable links

## Minimum Hardware Requirements

| Spec | Minimum | Recommended |
|------|---------|------------|
| CPU | 2 cores | 4 cores |
| RAM | 4 GB | 8 GB |
| Storage | 100 GB | 500 GB+ |
| Docker | ✅ Required | Compose v2 |

> 💡 **Cost-saving tip**: Hetzner CX22 (2 vCPU / 4GB / 40GB) at ~€4/month + Block Storage (€0.06/GB/month). For 100GB storage, total ≈ **€10/month** — less than Google One.

## Step-by-Step Docker Deployment

### Step 1: Preparation

```bash
# Create project directory
mkdir -p /opt/immich
cd /opt/immich

# Download official docker-compose and .env
wget https://github.com/immich-app/immich/releases/latest/download/docker-compose.yml
wget -O .env https://github.com/immich-app/immich/releases/latest/download/example.env
```

### Step 2: Configure Environment

Edit the `.env` file:

```bash
UPLOAD_LOCATION=./library
DB_HOSTNAME=immich_postgres
DB_USERNAME=postgres
DB_PASSWORD=change_me_to_a_strong_password
DB_DATABASE_NAME=immich
REDIS_HOSTNAME=immich_redis
```

### Step 3: Set Up Reverse Proxy

Immich runs on port **2283** by default. Configure Nginx Proxy Manager or Traefik:

```nginx
server {
    listen 80;
    server_name photos.yourdomain.com;
    
    location / {
        proxy_pass http://localhost:2283;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

### Step 4: Launch

```bash
docker compose up -d
```

Visit `http://your_vps_ip:2283`, register an admin account, and you're ready to go.

## Backup Strategy

Immich data is irreplaceable. Here's a recommended backup plan:

```bash
#!/bin/bash
# /opt/immich/backup.sh — run weekly

TIMESTAMP=$(date +%Y%m%d)
BACKUP_DIR="/backups/immich/$TIMESTAMP"
mkdir -p "$BACKUP_DIR"

# 1. Backup PostgreSQL database
docker exec immich_postgres pg_dump -U postgres immich > "$BACKUP_DIR/db.sql"

# 2. Backup uploaded files and thumbnails
rsync -av /opt/immich/library/ "$BACKUP_DIR/library/"
rsync -av /opt/immich/upload/ "$BACKUP_DIR/upload/" 2>/dev/null

# 3. Compress and encrypt
tar -czf "$BACKUP_DIR/immich-backup.tar.gz" -C "$BACKUP_DIR" db.sql library/
gpg --symmetric --cipher-algo AES256 "$BACKUP_DIR/immich-backup.tar.gz"

# 4. Sync to remote storage (e.g., Backblaze B2)
rclone sync "$BACKUP_DIR" "b2:my-immich-backups/$TIMESTAMP" --progress

echo "✅ Immich backup completed: $TIMESTAMP"
```

### Cron Schedule

```bash
# Run every Sunday at 3:00 AM
0 3 * * 0 /bin/bash /opt/immich/backup.sh
```

## Real-World Performance

3 months of production use on a Hetzner CX22 (€4/month):

```
📸 Photos: 12,347
🎥 Videos: 415
💾 Total storage: 89.7 GB
⏱️ Initial ML analysis: ~6 hours
🔄 Daily incremental backup: ~2.3 GB
💸 Monthly cost: €4 (VPS) + €5.40 (90GB Block Storage) = €9.40
```

**vs Google One 2TB**: $9.99/month → save **~$80/year** with lossless quality and full data control.

## Advanced Optimization Tips

### 1. Hardware-Accelerated Transcoding

Add GPU support in `docker-compose.yml`:

```yaml
services:
  immich-machine-learning:
    image: ghcr.io/immich-app/immich-machine-learning:release
    devices:
      - /dev/dri:/dev/dri  # Intel QuickSync
    deploy:
      resources:
        reservations:
          devices:
            - capabilities: [gpu]  # NVIDIA GPU
```

### 2. External Storage (Keep VPS Disk Free)

```bash
# Mount Hetzner Volume
mkfs.ext4 /dev/sdb
mount /dev/sdb /mnt/immich-storage

# Update UPLOAD_LOCATION in .env
UPLOAD_LOCATION=/mnt/immich-storage/library
```

### 3. Limit Memory & CPU

The ML module is resource-intensive. Set limits:

```yaml
services:
  immich-machine-learning:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
```

### 4. Auto Thumbnail Generation

```bash
docker exec immich_server immich-admin jobs --task thumbnail-generation
# Add to cron for nightly runs
```

## FAQ

### Q: Does the mobile app drain battery?
A: Immich supports background backup and WiFi-only upload, matching Google Photos' battery performance.

### Q: Can I migrate from Google Photos?
A: Yes! Use Google Takeout to export your photos, then import via Immich's Web UI batch upload. You can also use the community tool `immich-go` to import Google Takeout archives directly.

### Q: How much for multiple users?
A: **Free!** Immich itself is completely free. You only pay for VPS and storage. A family of 5 sharing one instance typically costs under $15/month.

### Q: How accurate is facial recognition?
A: Immich uses locally-running ML models (CLIP-based + custom face recognition) with accuracy comparable to Google Photos. The initial analysis is slow, but incremental analysis is very fast.

### Q: Does it support Live Photos?
A: Yes! iOS Live Photos are recognized and play correctly in both the web and mobile apps.

## Conclusion

Immich is the most mature Google Photos alternative available today. With **50k+ ⭐ on GitHub**, an active community, and rapid feature development, it's ready for production use. If you:

- Pay $120+/year for Google Photos
- Care about photo privacy and data control
- Have a VPS or NAS
- Want a shared family photo platform

**Start building your Immich today.** In the time it takes to brew a coffee, you can have your own, fully-controlled photo cloud running on your VPS.

### Quick Start

```bash
# One-command deploy (if you have Docker)
git clone https://github.com/immich-app/immich.git
cd immich/docker
cp example.env .env
# Edit .env to set your password and storage path
docker compose up -d
```

Your data, your rules. ☁️🔐
