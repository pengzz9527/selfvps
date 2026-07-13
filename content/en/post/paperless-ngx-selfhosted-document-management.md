---
title: "Self-Host Paperless-ngx Document Management — Build Your Personal Digital Archive with Docker"
description: "Deploy Paperless-ngx from scratch on your VPS using Docker. Achieve paper document digitization, OCR recognition, full-text search, and tag-based classification. Say goodbye to messy file storage and build an efficient knowledge management system."
date: 2026-07-13T10:00:00+08:00
lastmod: 2026-07-13T10:00:00+08:00
slug: "paperless-ngx-selfhosted-document-management"
tags: ["Paperless-ngx", "Docker", "OCR", "Document Management", "Self-Hosting", "Knowledge Management", "VPS", "Open Source"]
categories: ["Self-Hosting"]
draft: false
image: /images/posts/paperless-ngx-selfhosted-document-management/featured.png
aliases: [/en/post/paperless-ngx-selfhosted-document-management/]
---

## What is Paperless-ngx?

**Paperless-ngx** is an open-source document management system (DMS) designed for individuals and small teams. It allows you to scan and upload paper documents, automatically performs OCR text recognition, and supports full-text search, tag-based categorization, and metadata extraction.

> **Key Advantages**: Fully self-hosted with complete data privacy; one-click Docker deployment; multi-user collaboration support; comprehensive API for automation integration.

### Why Choose Self-Hosted Document Management?

| Solution | Privacy | Cost | Flexibility | Learning Curve |
|----------|---------|------|-------------|----------------|
| Google Drive/Dropbox | ⭐⭐⭐ | High (storage fees) | ⭐⭐ | Low |
| Evernote/Notion | ⭐⭐ | Medium-High | ⭐⭐⭐ | Low |
| Paperless-ngx | ⭐⭐⭐⭐⭐ | Minimal (server cost only) | ⭐⭐⭐⭐⭐ | Medium |

## System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| CPU | 1 core | 2+ cores |
| Memory | 1 GB | 2 GB+ |
| Storage | 10 GB SSD | 50 GB+ SSD |
| OS | Ubuntu 22.04+ | Ubuntu 24.04 LTS |

## Step 1: Environment Preparation

### Install Docker and Docker Compose

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sudo sh

# Add user to docker group
sudo usermod -aG docker $USER

# Install Docker Compose plugin
sudo apt install docker-compose-plugin -y

# Verify installation
docker --version
docker compose version
```

### Create Project Directory

```bash
mkdir -p ~/paperless-ngx/{data,media,export,pgdata}
cd ~/paperless-ngx
```

## Step 2: Docker Compose Configuration

Create `docker-compose.yml`:

```yaml
services:
  broker:
    image: docker.io/library/redis:7
    restart: unless-stopped
    volumes:
      - redis_data:/data

  db:
    image: docker.io/library/postgres:16
    restart: unless-stopped
    volumes:
      - pgdata:/var/lib/postgresql/data
    environment:
      POSTGRES_DB: paperless
      POSTGRES_USER: paperless
      POSTGRES_PASSWORD: paperless_secret

  webserver:
    image: ghcr.io/paperless-ngx/paperless-ngx:latest
    restart: unless-stopped
    depends_on:
      - db
      - broker
      - gotenberg
      - tika
    ports:
      - "8000:8000"
    volumes:
      - data:/usr/src/paperless/data
      - media:/usr/src/paperless/media
      - export:/usr/src/paperless/export
      - consume:/usr/src/paperless/consume
    environment:
      PAPERLESS_REDIS: redis://broker:***@${path}${file}" \
            -F "title=$(basename ${file})" \
            -F "tags=1"
        echo "Archived: $file"
    fi
done
```

## Data Backup Strategy

### Full Backup Script

```bash
#!/bin/bash
# backup_paperless.sh

BACKUP_DIR="/backup/paperless"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p "$BACKUP_DIR/$DATE"

# Backup database
docker exec paperless-ngx-db_1 pg_dump -U paperless paperless \
    > "$BACKUP_DIR/$DATE/database.sql"

# Backup media files
docker cp paperless-ngx-webserver_1:/usr/src/paperless/media \
    "$BACKUP_DIR/$DATE/media"

# Backup configuration
docker cp paperless-ngx-webserver_1:/usr/src/paperless/data \
    "$BACKUP_DIR/$DATE/data"

# Compress
tar czf "$BACKUP_DIR/paperless_$DATE.tar.gz" \
    "$BACKUP_DIR/$DATE"

# Clean temp files
rm -rf "$BACKUP_DIR/$DATE"

# Keep last 30 days of backups
find "$BACKUP_DIR" -name "paperless_*.tar.gz" -mtime +30 -delete
```

### Automated Scheduled Backups

```bash
# Daily backup at 2 AM
echo "0 2 * * * /path/to/backup_paperless.sh" | crontab -
```

## Performance Optimization Tips

### Adjust OCR Concurrency

```yaml
environment:
  # Adjust based on CPU cores
  PAPERLESS_CONSUMER_WORKERS: 4
  PAPERLESS_TASK_WORKERS: 4
```

### Storage Optimization

- Use SSD storage for faster OCR processing
- Regularly clean raw files in the `consume` directory
- Enable document compression: `PAPERLESS_COMPRESS_IMAGES=true`

### Memory Optimization

For low-spec VPS (1GB RAM), limit Tika memory usage:

```yaml
tika:
  environment:
    JVM_OPTS: "-Xms128m -Xmx256m"
```

## Security Hardening

### Change Default Credentials

After first login:
1. Change admin password
2. Create regular user accounts
3. Disable anonymous access

### Firewall Configuration

```bash
# Allow only HTTPS
sudo ufw allow 443/tcp
sudo ufw allow 22/tcp
sudo ufw enable
```

### API Key Management

- Generate independent API tokens for each application/user
- Rotate API keys regularly
- Store sensitive information in environment variables, not hardcoded

## Troubleshooting

### Low OCR Recognition Rate

```bash
# Check logs
docker compose logs gotenberg
docker compose logs webserver

# Ensure Chinese fonts are installed
docker exec -it paperless-ngx-webserver_1 \
    apt-get update && apt-get install -y fonts-noto-cjk
```

### Large File Upload Failure

Adjust Nginx configuration:

```nginx
client_max_body_size 100M;
proxy_request_buffering off;
```

### Service Won't Start

```bash
# Check disk space
df -h

# Check memory
free -m

# Restart services
docker compose down
docker compose up -d
```

## Conclusion

Paperless-ngx is an excellent choice for self-hosted document management. It simplifies complex document processing workflows into a single upload action. With Docker deployment, even technical beginners can set it up within 30 minutes.

**Key Takeaways**:
- ✅ One-click Docker Compose deployment with automatic dependency management
- ✅ OCR supports multiple languages including Chinese and English
- ✅ REST API enables automated archiving workflows
- ✅ Complete data backup strategy ensures security
- ✅ HTTPS via Nginx guarantees secure transmission

Your data is your most valuable asset — choose self-hosting and keep control in your own hands.
