---
title: "Self-Host Plausible Analytics on VPS: A Privacy-Friendly Google Analytics Alternative"
description: "Step-by-step guide to deploying Plausible Analytics on VPS with Docker — an open-source, privacy-first website analytics tool that eliminates Google's data collection while saving subscription costs"
date: 2026-06-05T10:00:00+08:00
lastmod: 2026-06-05T10:00:00+08:00
slug: "selfhost-plausible-analytics-vps"
image: /images/posts/selfhost-plausible-analytics-vps/featured.png
tags: ["Plausible", "Analytics", "self-hosted", "Docker", "privacy", "VPS", "open-source", "web-development"]
categories: ["Self-Hosting"]
---

## Introduction

Website analytics are essential for understanding user behavior, but Google Analytics comes with several pain points:

- **Privacy concerns**: Google collects vast amounts of user data, often violating GDPR and other privacy regulations
- **Performance impact**: GA's bloated script (~45KB+) slows down page load times
- **Cost**: While GA4 is free for basic use, privacy-friendly SaaS analytics tools (Fathom, Simple Analytics) charge $10-30/month
- **Ad blocker blocking**: Google Analytics is widely blocked by ad blockers, skewing data accuracy

**Plausible Analytics** is an open-source, lightweight, privacy-first website analytics tool with these advantages:

| Feature | Plausible | Google Analytics |
|---------|-----------|-----------------|
| Script size | < 1KB | 45KB+ |
| GDPR compliance | ✅ Native (cookie-free) | ⚠️ Requires configuration |
| Self-hostable | ✅ Open source & free | ❌ SaaS only |
| Ad blocker blocking | ⚠️ Partially blocked | ❌ Heavily blocked |
| Data ownership | ✅ Full control | ❌ Google owns it |
| Monthly cost (self-hosted) | ~$3-5 (VPS cost) | Free / Paid |

This guide walks you through deploying Plausible on a VPS with Docker, using PostgreSQL + ClickHouse dual-database architecture, with Nginx/Caddy reverse proxy and HTTPS.

---

## Prerequisites

- A VPS (recommended minimum: 1 vCPU, 1GB RAM, 20GB SSD)
- A domain name (e.g., `analytics.yourdomain.com`)
- Docker and Docker Compose (v2+)
- Basic Linux command-line knowledge

## 1. Prepare the Environment

### Install Docker

```bash
# Install Docker (skip if already installed)
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Install Docker Compose v2
sudo apt-get update
sudo apt-get install -y docker-compose-plugin

# Verify installation
docker --version
docker compose version
```

### Set Up Directory Structure

```bash
# Create Plausible directory
mkdir -p ~/plausible && cd ~/plausible

# Directory layout
# ~/plausible/
# ├── docker-compose.yml
# ├── plausible-conf.env
# ├── clickhouse/
# │   └── (data directory, auto-created)
# └── plausible/
#     └── (data directory, auto-created)
```

## 2. Configure Docker Compose

Plausible requires three services:
1. **Plausible** — Main application (built with Elixir)
2. **PostgreSQL** — Stores metadata (users, site configurations)
3. **ClickHouse** — Stores analytics event data (column-oriented, optimized for analytics)

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  plausible:
    image: plausible/analytics:v2.1
    restart: unless-stopped
    command: sh -c "sleep 10 && /entrypoint.sh db migrate && /entrypoint.sh run"
    ports:
      - "127.0.0.1:8000:8000"
    depends_on:
      - plausible_db
      - plausible_events_db
    env_file:
      - plausible-conf.env
    volumes:
      - plausible_data:/var/lib/plausible/data
      - ./plausible/geoip:/var/lib/plausible/geoip:ro

  plausible_db:
    image: postgres:16-alpine
    restart: unless-stopped
    volumes:
      - db_data:/var/lib/postgresql/data
    environment:
      - POSTGRES_DB=plausible
      - POSTGRES_USER=plausible
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-plausible_secret_password}

  plausible_events_db:
    image: clickhouse/clickhouse-server:24.3-alpine
    restart: unless-stopped
    volumes:
      - event_data:/var/lib/clickhouse
      - ./clickhouse/clickhouse-config.xml:/etc/clickhouse-server/config.d/logging.xml:ro
    environment:
      - CLICKHOUSE_DB=plausible_events
      - CLICKHOUSE_USER=plausible
      - CLICKHOUSE_PASSWORD=${CLICKHOUSE_PASSWORD:-plausible_secret_password}

volumes:
  db_data:
  event_data:
  plausible_data:
```

### ClickHouse Logging Configuration

Create `clickhouse/clickhouse-config.xml` to reduce log verbosity:

```bash
mkdir -p clickhouse
```

```xml
<clickhouse>
  <logger>
    <level>warning</level>
    <log>/var/log/clickhouse-server/clickhouse-server.log</log>
    <errorlog>/var/log/clickhouse-server/clickhouse-server.err.log</errorlog>
    <size>10M</size>
    <count>3</count>
  </logger>
</clickhouse>
```

## 3. Configure Environment Variables

Create `plausible-conf.env`:

```bash
cat > plausible-conf.env << 'EOF'
# ── Base Configuration ──
BASE_URL=https://analytics.yourdomain.com
SECRET_KEY_BASE=$(openssl rand -base64 48)
DISABLE_REGISTRATION=true

# ── Database Configuration ──
DATABASE_URL=postgres://plausible:plausible_secret_password@plausible_db:5432/plausible
CLICKHOUSE_DATABASE_URL=http://plausible:plausible_secret_password@plausible_events_db:8123/plausible_events

# ── Performance Tuning ──
CLICKHOUSE_QUERY_TIMEOUT_MS=30000
DATABASE_POOL_SIZE=15

# ── Email (optional, for reports) ──
# MAILER_ADAPTER=Bamboo.SMTPAdapter
# SMTP_HOST_ADDR=smtp.example.com
# SMTP_HOST_PORT=587
# SMTP_USER_NAME=user@example.com
# SMTP_USER_PWD=password
# SMTP_HOST_SSL_ENABLED=true
# MAILER_EMAIL=analytics@yourdomain.com
EOF
```

> ⚠️ **Important**: Replace `BASE_URL` with your actual domain. Replace `POSTGRES_PASSWORD` and `CLICKHOUSE_PASSWORD` with strong passwords.

### Generate Keys

```bash
# Generate SECRET_KEY_BASE
openssl rand -base64 48

# Generate database passwords
openssl rand -base64 24
```

## 4. Start Plausible

```bash
# Start all services
docker compose up -d

# Check startup logs
docker compose logs -f

# Verify service status
docker compose ps

# Test that Plausible is running
curl -s http://127.0.0.1:8000 | head -5
```

After startup, visit `http://your-vps-ip:8000` — you should see the Plausible interface.

### Create Admin Account

The first visit will prompt you to register. With `DISABLE_REGISTRATION=true`, no one else can register afterward.

```bash
# Or create admin via CLI
docker compose exec plausible /entrypoint.sh db create-admin \
  --email admin@yourdomain.com \
  --name "Admin" \
  --password "your-strong-password"
```

## 5. Configure Reverse Proxy and HTTPS

### Option A: Caddy (Recommended, Auto HTTPS)

Caddy automatically provisions Let's Encrypt certificates with zero config.

```bash
# Install Caddy
sudo apt-get install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt-get update
sudo apt-get install caddy
```

Create `/etc/caddy/Caddyfile`:

```caddy
analytics.yourdomain.com {
    reverse_proxy 127.0.0.1:8000
    
    # Security headers
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"
        X-Content-Type-Options nosniff
        X-Frame-Options DENY
        X-XSS-Protection "1; mode=block"
        Referrer-Policy strict-origin-when-cross-origin
    }
    
    # Logging
    log {
        output file /var/log/caddy/analytics.log
    }
}
```

```bash
# Validate configuration
sudo caddy validate --config /etc/caddy/Caddyfile

# Reload Caddy
sudo systemctl reload caddy

# Check certificate status
sudo caddy cert-info analytics.yourdomain.com
```

### Option B: Nginx

```nginx
# /etc/nginx/sites-available/analytics.yourdomain.com
upstream plausible {
    server 127.0.0.1:8000;
}

server {
    listen 80;
    server_name analytics.yourdomain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name analytics.yourdomain.com;

    ssl_certificate     /etc/letsencrypt/live/analytics.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/analytics.yourdomain.com/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;

    location / {
        proxy_pass http://plausible;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_redirect off;
        proxy_buffering off;
        client_max_body_size 10m;
    }
}
```

```bash
# Enable site
sudo ln -s /etc/nginx/sites-available/analytics.yourdomain.com /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

## 6. Add Your Site and Deploy Tracking Script

### Add a Site in Plausible

1. Visit `https://analytics.yourdomain.com`
2. Log in with your admin account
3. Click "Add website"
4. Enter your domain (e.g., `selfvps.net`)
5. Copy the tracking script

### Deploy the Tracking Script

Add the following code to your website's `<head>` tag:

```html
<script defer data-domain="yourdomain.com" src="https://analytics.yourdomain.com/js/script.js"></script>
```

For Hugo blogs, add to `layouts/partials/head.html`:

```html
{{ if not .Site.IsServer }}
<script defer data-domain="{{ .Site.BaseURL | urlize }}" src="https://analytics.yourdomain.com/js/script.js"></script>
{{ end }}
```

### Custom Event Tracking

Plausible supports custom events and goal tracking:

```javascript
// Track button clicks
plausible('Signup', { props: { method: 'Email' }});

// Track 404 pages
plausible('404', { props: { path: document.location.pathname }});

// Track file downloads
document.querySelectorAll('a[href$=".pdf"]').forEach(link => {
    link.addEventListener('click', () => {
        plausible('Download', { props: { file: link.href }});
    });
});
```

## 7. Performance Optimization

### System-Level Tuning

```bash
# ── System-level optimizations ──

# 1. Increase file descriptor limit
echo "fs.file-max = 100000" | sudo tee -a /etc/sysctl.conf

# 2. Network optimizations
cat >> /etc/sysctl.conf << 'EOF'
net.core.somaxconn = 65535
net.ipv4.tcp_max_syn_backlog = 65535
net.ipv4.tcp_tw_reuse = 1
net.ipv4.tcp_fastopen = 3
EOF
sudo sysctl -p

# 3. Set up swap (recommended for 1GB RAM VPS)
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

### Docker Resource Limits

Set resource limits in `docker-compose.yml`:

```yaml
services:
  plausible:
    # ... other config ...
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: '0.75'
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  plausible_events_db:
    # ... other config ...
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: '0.5'
```

### ClickHouse Performance Tuning

Create `clickhouse/clickhouse-performance.xml`:

```xml
<clickhouse>
  <max_memory_usage>300000000</max_memory_usage>
  <max_server_memory_usage>400000000</max_server_memory_usage>
  <max_concurrent_queries>10</max_concurrent_queries>
  <merge_tree>
    <max_suspicious_broken_parts>5</max_suspicious_broken_parts>
    <parts_to_throw_insert>300</parts_to_throw_insert>
    <parts_to_delay_insert>150</parts_to_delay_insert>
  </merge_tree>
</clickhouse>
```

## 8. Data Backup & Recovery

### Automated Backup Script

Create `backup.sh`:

```bash
#!/bin/bash
# Plausible data backup script

BACKUP_DIR="/root/backups/plausible"
DATE=$(date +%Y%m%d_%H%M%S)
RETENTION_DAYS=30

mkdir -p $BACKUP_DIR

echo "==> Backing up PostgreSQL database..."
docker compose exec -T plausible_db pg_dumpall -U plausible | gzip > "$BACKUP_DIR/plausible_db_$DATE.sql.gz"

echo "==> Backing up ClickHouse data..."
docker compose exec -T plausible_events_db clickhouse-client --query "BACKUP TABLE plausible_events.* TO 'file:///var/lib/clickhouse/backup/backup_$DATE'" 2>/dev/null || {
    echo "⚠️ ClickHouse backup failed, falling back to data directory copy..."
    tar czf "$BACKUP_DIR/clickhouse_data_$DATE.tar.gz" -C /var/lib/docker/volumes/$(basename $(pwd))_event_data/_data .
}

echo "==> Cleaning old backups (retaining $RETENTION_DAYS days)..."
find $BACKUP_DIR -name "*.sql.gz" -mtime +$RETENTION_DAYS -delete
find $BACKUP_DIR -name "*.tar.gz" -mtime +$RETENTION_DAYS -delete

echo "✅ Backup complete! Files in: $BACKUP_DIR"
ls -lh $BACKUP_DIR
```

```bash
chmod +x backup.sh

# Schedule daily backup (3 AM)
(crontab -l 2>/dev/null; echo "0 3 * * * cd ~/plausible && ./backup.sh >> /var/log/plausible-backup.log 2>&1") | crontab -
```

### Restore from Backup

```bash
# Stop services
docker compose down

# Restore PostgreSQL
gunzip -c plausible_db_20260605_030000.sql.gz | docker compose exec -T plausible_db psql -U plausible

# Restart services
docker compose up -d
```

## 9. Monitoring & Maintenance

### Health Checks

```bash
# Health check endpoint
curl -s https://analytics.yourdomain.com/health

# Check resource usage
docker stats --no-stream plausible plausible_db plausible_events_db

# View logs
docker compose logs --tail=100 plausible

# Check database connectivity
docker compose exec plausible_db pg_isready -U plausible
```

### Upgrading Plausible

```bash
# Backup data first
./backup.sh

# Pull latest images
docker compose pull

# Restart services
docker compose up -d

# Migration runs automatically on startup
docker compose logs -f plausible | grep "migration"
```

### Integrate with Uptime Kuma

```yaml
# In Uptime Kuma, add a monitor:
# URL: https://analytics.yourdomain.com/health
# Expected status: 200
# Notification: Telegram / Email
```

## 10. Troubleshooting

### Q: Blank page or 502 error

```bash
# Check if services are running
docker compose ps

# View error logs
docker compose logs plausible | tail -50

# Check database connectivity
docker compose exec plausible_db psql -U plausible -d plausible -c "SELECT 1"

# Common cause: Plausible started before database was ready
docker compose restart plausible
```

### Q: ClickHouse out of memory

```bash
# Check ClickHouse logs
docker compose logs plausible_events_db | grep -i "memory\|OOM\|error"

# Solution: Limit ClickHouse memory usage
# Edit max_memory_usage in clickhouse-performance.xml
```

### Q: No data showing / tracking not working

```bash
# 1. Check if tracking script is deployed correctly
curl -s https://analytics.yourdomain.com/js/script.js | head -5

# 2. Check DNS resolution
dig analytics.yourdomain.com

# 3. Check if Plausible received events
docker compose logs plausible | grep "tracking\|event\|pageview"

# 4. Check for CSP restrictions
# Add to Nginx/Caddy:
# Content-Security-Policy: script-src 'self' https://analytics.yourdomain.com;
```

### Q: Database disk space low

```bash
# Check Docker volume usage
docker system df -v

# Check ClickHouse data sizes
docker compose exec plausible_events_db clickhouse-client \
  --query "SELECT table, formatReadableSize(sum(bytes)) FROM system.parts WHERE active GROUP BY table"

# Set data retention (add to plausible-conf.env)
# CLICKHOUSE_DATA_RETENTION_DAYS=90
```

## Cost Analysis

| Item | Monthly Cost |
|------|-------------|
| VPS (1C1G, e.g., RackNerd $18/year) | $1.50 |
| Domain (e.g., `analytics.yourdomain.com`) | $0 (subdomain) |
| **Total** | **~$1.50/month** |

Compared to Plausible Cloud: **$9/month** (10K page views) → Self-hosting saves **83%**!

> 💡 **Pro tip**: If you already have a VPS running other services, deploying Plausible on the same machine has near-zero marginal cost.

## Summary

You've successfully self-hosted Plausible Analytics on your VPS:

✅ Deployed Plausible + PostgreSQL + ClickHouse with Docker Compose
✅ Configured Caddy/Nginx reverse proxy with automatic HTTPS
✅ Installed the tracking script on your website
✅ Set up automated backups and monitoring

Plausible is the best self-hosted alternative to Google Analytics. It protects user privacy while giving you full control over your data — exactly what self-hosting is all about.

### Next Steps

- 📊 **Set up email reports**: Configure SMTP to receive weekly/monthly analytics reports
- 🔗 **Integrate Slack/Telegram**: Get real-time data push via webhooks
- 🎯 **Configure goal tracking**: Monitor conversions like signups, downloads, and purchases
- 🚀 **Scale to multiple sites**: Manage analytics for all your websites from a single instance

## Resources

- [Plausible Self-Hosting Docs](https://plausible.io/docs/self-hosting)
- [Plausible on GitHub](https://github.com/plausible/analytics)
- [ClickHouse Documentation](https://clickhouse.com/docs)
- [Caddy Documentation](https://caddyserver.com/docs/)
- [Docker Compose V2 Docs](https://docs.docker.com/compose/)

---

*Published on [SelfVPS Guide](https://selfvps.net). All rights reserved.*
