---
title: "Nextcloud Full Stack: Building a Complete Self-Hosted Office Suite on VPS (Docs, Video Chat & Email)"
subtitle: "搭建 Nextcloud 全家桶：在 VPS 上构建完整的自托管办公套件（文档、视频会议与邮件）"
date: 2026-07-12
draft: false
tags: ["Nextcloud", "Collabora", "Self-hosted", "Docker", "Email", "Document Collaboration", "Video Conferencing"]
categories: ["Self-hosted Apps"]
image: /images/posts/nextcloud-full-suite/featured.png
description: "Deploy a complete Nextcloud office suite from scratch — integrating Collabora online docs, Talk video conferencing, and Mail client into one private workspace."
---

## Introduction: Why You Need a Complete Personal Cloud Office Suite

As cloud services become increasingly expensive, more tech enthusiasts are choosing to migrate their data and services to self-hosted solutions. But most guides only teach you how to deploy a basic Nextcloud instance — file sync and sharing. A true productivity tool should be a **complete office suite**:

- 📄 **Online Document Editing** — Like Google Docs with real-time multi-person collaboration
- 💬 **Video Conferencing** — Private calls without third-party platforms
- 📧 **Email Client** — Unified management of all email accounts
- 🔐 **Complete Data Sovereignty** — Your data, your server

This guide walks you through deploying a full Nextcloud suite on a VPS using Docker Compose for one-command deployment and easy maintenance.

## Architecture Overview

```
┌──────────────────────────────────────────────────────┐
│              Nextcloud Full Suite                     │
├──────────────────────────────────────────────────────┤
│                                                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐          │
│  │  Nextcloud│  │ Collabora│  │  Mail    │          │
│  │  (Core)   │  │  (Docs)  │  │  (Email) │          │
│  └─────┬────┘  └────┬─────┘  └────┬─────┘          │
│        │            │             │                  │
│  ┌─────▼────────────▼─────────────▼─────┐           │
│  │         Nginx Reverse Proxy           │           │
│  │      (SSL/TLS + Domain Routing)       │           │
│  └────────────────┬─────────────────────┘           │
│                   │                                  │
│  ┌────────────────▼─────────────────────┐           │
│  │       PostgreSQL + Redis              │           │
│  │       MariaDB (Optional)              │           │
│  └────────────────┬─────────────────────┘           │
│                   │                                  │
│  ┌────────────────▼─────────────────────┐           │
│  │        Docker Storage Volume          │           │
│  │       (Persistent Data + Backups)     │           │
│  └──────────────────────────────────────┘           │
└──────────────────────────────────────────────────────┘
```

## Step 1: Server Preparation

### Recommended Specifications

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| CPU | 2 cores | 4 cores |
| RAM | 4 GB | 8 GB |
| Storage | 40 GB SSD | 100 GB+ NVMe SSD |
| Bandwidth | 5 Mbps | 10 Mbps+ |
| OS | Ubuntu 22.04/24.04 | Ubuntu 24.04 LTS |

### Initial Setup

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install base tools
sudo apt install -y curl wget git unzip htop net-tools

# Create non-root user
sudo adduser nextcloud
sudo usermod -aG sudo nextcloud
su - nextcloud
```

## Step 2: Install Docker and Docker Compose

```bash
# Remove old versions
for pkg in docker.io docker-doc docker-compose podman-docker containerd runc; do
    sudo apt remove -y $pkg 2>/dev/null || true
done

# Install Docker
sudo apt install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Verify installation
docker --version
docker compose version

# Add current user to docker group (avoid sudo every time)
sudo usermod -aG docker $USER
newgrp docker
```

## Step 3: Project Directory Structure

```bash
mkdir -p ~/nextcloud-suite
cd ~/nextcloud-suite

# Create directory structure
mkdir -p data/{nextcloud,collabora,mail,postgres,redis}
mkdir -p config/nginx
mkdir -p logs
```

## Step 4: Write Docker Compose Configuration

### Main Config `docker-compose.yml`

```yaml
version: '3.8'

services:
  # ========== Nginx Reverse Proxy ==========
  nginx:
    image: nginx:alpine
    container_name: nc-nginx
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./config/nginx:/etc/nginx/conf.d:ro
      - ./data/nextcloud/html:/var/www/html:ro
      - ./logs/nginx:/var/log/nginx
      - /etc/letsencrypt:/etc/letsencrypt:ro
    depends_on:
      - nextcloud
      - collabora
      - mailserver
    restart: unless-stopped
    networks:
      - nextcloud-net

  # ========== Nextcloud Core ==========
  nextcloud:
    image: nextcloud:30-apache
    container_name: nc-nextcloud
    volumes:
      - ./data/nextcloud/html:/var/www/html
      - ./data/nextcloud/data:/var/www/html/data
      - ./data/nextcloud/config:/var/www/html/config
      - ./data/nextcloud/custom_apps:/var/www/html/apps
      - ./data/nextcloud/themes/default:/var/www/html/themes/default
    environment:
      - MYSQL_HOST=db
      - MYSQL_DATABASE=nextcloud
      - MYSQL_USER=nc_user
      - MYSQL_PASSWORD=${NC_DB_PASS}
      - REDIS_HOST=redis
      - NEXTADMIN_TRUSTED_PROXIES=172.18.0.0/16
      - OVERWRITEPROTOCOL=https
      - DEFAULTPHONEREGION=CN
      - NEXTCLOUD_ADMIN_USER=admin
      - NEXTCLOUD_ADMIN_PASSWORD=${NC_ADMIN_PASS}
      - APACHE_DISABLE_REWRITE_IP=1
    depends_on:
      - db
      - redis
    restart: unless-stopped
    networks:
      - nextcloud-net

  # ========== Database ==========
  db:
    image: mariadb:10.11
    container_name: nc-db
    command: --transaction-isolation=READ-COMMITTED --binlog-format=ROW
    restart: unless-stopped
    volumes:
      - ./data/postgres/mariadb:/var/lib/mysql
    environment:
      - MYSQL_ROOT_PASSWORD=${DB_ROOT_PASS}
      - MYSQL_DATABASE=nextcloud
      - MYSQL_USER=nc_user
      - MYSQL_PASSWORD=${NC_DB_PASS}
    networks:
      - nextcloud-net

  # ========== Redis Cache ==========
  redis:
    image: redis:7-alpine
    container_name: nc-redis
    restart: unless-stopped
    command: redis-server --requirepass ${REDIS_PASSWORD} --maxmemory 256mb --maxmemory-policy allkeys-lru
    volumes:
      - ./data/redis:/data
    networks:
      - nextcloud-net

  # ========== Collabora Online Docs ==========
  collabora:
    image: collabora/code:latest
    container_name: nc-collabora
    restart: unless-stopped
    environment:
      - domain=${COLLABORA_DOMAIN}
      - username=admin
      - password=${COLLABORA_ADMIN_PASS}
      - DONT_GEN_SSL_CERTIFICATES=true
    cap_add:
      - MKNOD
    volumes:
      - ./data/collabora:/var/lib/collabora
    networks:
      - nextcloud-net

  # ========== Mail Server ==========
  mailserver:
    image: mailserver/docker-mailserver:latest
    container_name: nc-mail
    hostname: mail
    domainname: ${MAIL_DOMAIN}
    ports:
      - "25:25"
      - "143:143"
      - "587:587"
      - "993:993"
    volumes:
      - ./data/mail/maildata:/var/mail
      - ./data/mail/mailstate:/var/mail-state
      - ./data/mail/logs:/var/log/mail
      - ./data/mail/config:/tmp/dms/fix-mymacros
      - ./data/mail/config/sogo:/etc/sogo
      - ./data/mail/config/dovecot:/tmp/dms/dovecot-backup
    environment:
      - ENABLE_SPAMASSASSIN=1
      - SPAMASSASSIN_SPAM_TO_INBOX=1
      - ENABLE_CLAMAV=1
      - ENABLE_FAIL2BAN=1
      - ENABLE_POSTGREY=1
      - ONE_DIR=1
      - DMS_DEBUG=0
      - SSL_TYPE=manual
      - POSTMASTER_ADDRESS=postmaster@${MAIL_DOMAIN}
    restart: unless-stopped
    networks:
      - nextcloud-net

networks:
  nextcloud-net:
    driver: bridge
```

### Environment File `.env`

```bash
# Generate random passwords
openssl rand -base64 32

# Edit .env file
cat > .env << 'EOF'
# Nextcloud
NC_ADMIN_PASSWORD=your_s...n
# Database
DB_ROOT_PASSWORD=your_r...n
# Redis
REDIS_PASSWORD=your_r...n
# Collabora
COLLABORA_DOMAIN=nextcloud\.yourdomain\.com
COLLABORA_ADMIN_PASS=collab...n
# Mail
MAIL_DOMAIN=mail.yourdomain.com
EOF
```

## Step 5: Nginx Reverse Proxy Configuration

### `config/nginx/nextcloud.conf`

```nginx
# HTTP to HTTPS redirect
server {
    listen 80;
    server_name nextcloud.yourdomain.com;
    
    location /.well-known/acme-challenge/ {
        root /etc/letsencrypt/www;
    }
    
    location / {
        return 301 https://$host$request_uri;
    }
}

# Nextcloud
server {
    listen 443 ssl http2;
    server_name nextcloud.yourdomain.com;
    
    ssl_certificate /etc/letsencrypt/live/nextcloud.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/nextcloud.yourdomain.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    
    # Security headers
    add_header X-Content-Type-Options nosniff;
    add_header X-Frame-Options "SAMEORIGIN";
    add_header X-XSS-Protection "1; mode=block";
    add_header X-Robots-Tag none;
    add_header XDownloadOptions noopen;
    add_header XPermittedCrossDomainPolicies none;
    add_header Referrer-Policy no-referrer;
    
    # Max upload size
    client_max_body_size 10G;
    
    location / {
        proxy_pass http://nextcloud:80;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket support for Talk
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}

# Collabora Online
server {
    listen 443 ssl http2;
    server_name collabora.yourdomain.com;
    
    ssl_certificate /etc/letsencrypt/live/collabora.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/collabora.yourdomain.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    
    location / {
        proxy_pass http://collabora:9980;
        proxy_set_header Host $http_host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        
        # Large buffers for WOPI protocol
        proxy_buffering off;
        proxy_request_buffering off;
    }
}
```

## Step 6: Get SSL Certificates

```bash
# Install Certbot
sudo apt install -y certbot python3-certbot-nginx

# Get certificate for Nextcloud
sudo certbot certonly --standalone \
  -d nextcloud.yourdomain.com \
  --email your-email@example.com \
  --agree-tos --no-eff-email

# Get certificate for Collabora
sudo certbot certonly --standalone \
  -d collabora.yourdomain.com \
  --email your-email@example.com \
  --agree-tos --no-eff-email

# Set up auto-renewal
sudo crontab -e
# Add: 0 3 * * * certbot renew --quiet && docker restart nc-nginx
```

## Step 7: Start Services

```bash
cd ~/nextcloud-suite

# First start (may take a few minutes)
docker compose up -d

# Check logs
docker compose logs -f nextcloud

# Verify all containers
docker compose ps
```

Expected output:
```
NAME            IMAGE                    STATUS
nc-nginx        nginx:alpine             Up
nc-nextcloud    nextcloud:30-apache      Up
nc-db           mariadb:10.11            Up
nc-redis        redis:7-alpine           Up
nc-collabora    collabora/code:latest    Up
nc-mail         mailserver/docker-mailserver Up
```

## Step 8: Initial Configuration

### 1. Log in to Nextcloud

Visit `https://nextcloud.yourdomain.com` and log in with your admin credentials.

### 2. Install Essential Apps

Go to **Settings → Apps** and install:

| App Name | Function | Description |
|----------|----------|-------------|
| **Richdocuments** | Collabora Integration | Enables online document editing |
| **Mail** | Email Client | Built-in email management |
| **Talk** | Video Conferencing | Audio/video calls and chat |
| **Deck** | Project Management | Trello-style kanban boards |
| **Calendar** | Calendar | Schedule management |
| **Contacts** | Contacts | Address book |
| **News** | RSS Reader | Information aggregation |
| **Photos** | Gallery | Photo management |

### 3. Configure Collabora Integration

In Nextcloud:
1. Go to **Settings → Admin → Collabora Online**
2. Enter Collabora server address: `https://collabora.yourdomain.com`
3. Check "Use own server"
4. Save and test connection

### 4. Configure Talk (Video Conferencing)

1. Go to **Settings → Talk**
2. Enable "Allow creating rooms"
3. Configure TURN/STUN server (if NAT traversal needed):
   ```
   STUN: stun.nextcloud.com:443
   ```

### 5. Configure Mail Client

1. Go to **Settings → Mail**
2. Add your email accounts (Gmail, Outlook, or self-hosted Postfix/Dovecot)
3. If using external IMAP/SMTP, fill in the corresponding server info

## Step 9: Performance Optimization

### Nextcloud Tuning

Edit `data/nextcloud/config/config.php`:

```php
<?php
$CONFIG = array(
  // Enable OPcache
  'opcache.enable' => 1,
  'opcache.memory_consumption' => 256,
  'opcache.interned_strings_buffer' => 8,
  'opcache.max_accelerated_files' => 10000,
  
  // Redis caching
  'memcache.local' => '\\OC\\Memcache\\Redis',
  'memcache.locking' => '\\OC\\Memcache\\Redis',
  'redis' => array(
    'host' => 'redis',
    'port' => 6379,
    'password' => '${REDIS_PASSWORD}',
  ),
  
  // PHP settings
  'php_enable_filelocking' => true,
  'maintenance_window' => 3,
  
  // File scan optimization
  'filesystem_check_changes' => 1,
  
  // Log level (use 1 for production)
  'loglevel' => 1,
  'logfile' => '/var/www/html/data/nextcloud.log',
);
```

### Database Tuning (MariaDB)

Create `data/postgres/mariadb/init.sql`:

```sql
-- Adjust InnoDB buffer pool size (based on available memory)
SET GLOBAL innodb_buffer_pool_size = 1073741824;  -- 1GB

-- Adjust connections
SET GLOBAL max_connections = 200;

-- Query cache
SET GLOBAL query_cache_type = 1;
SET GLOBAL query_cache_size = 67108864;  -- 64MB
```

### Browser Caching

Add to Nginx config:

```nginx
location ~* \.(css|js|jpg|jpeg|png|gif|ico|svg|woff|woff2|ttf)$ {
    expires 30d;
    add_header Cache-Control "public, immutable";
}
```

## Step 10: Backup Strategy

### Automated Backup Script

Create `~/nextcloud-suite/scripts/backup.sh`:

```bash
#!/bin/bash
set -euo pipefail

DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/backup/nextcloud"
RETENTION_DAYS=30

# Ensure backup directory exists
mkdir -p "$BACKUP_DIR"

echo "[$(date)] Starting backup..."

# 1. Backup database
docker exec nc-db mysqldump -u nc_user -p"${NC_DB_PASSWORD}" nextcloud \
  | gzip > "$BACKUP_DIR/db_nextcloud_$DATE.sql.gz"

# 2. Backup Nextcloud data
docker exec nc-nextcloud tar czf /tmp/nc_data_$DATE.tar.gz \
  -C /var/www/html/data .
docker cp nc-nextcloud:/tmp/nc_data_$DATE.tar.gz \
  "$BACKUP_DIR/nc_data_$DATE.tar.gz"

# 3. Backup configuration files
tar czf "$BACKUP_DIR/config_$DATE.tar.gz" \
  -C "$(dirname "$BACKUP_DIR")" nextcloud-suite/docker-compose.yml \
  nextcloud-suite/.env \
  nextcloud-suite/config/

# 4. Clean expired backups
find "$BACKUP_DIR" -name "*.gz" -mtime +${RETENTION_DAYS} -delete

# 5. Upload to remote storage (optional, using rclone)
if command -v rclone &> /dev/null; then
    rclone sync "$BACKUP_DIR" remote:nextcloud-backups/
fi

echo "[$(date)] Backup completed successfully."
```

### Set Up Cron Job

```bash
crontab -e
# Run daily at 2 AM
0 2 * * * /home/nextcloud/nextcloud-suite/scripts/backup.sh >> /var/log/nextcloud-backup.log 2>&1
```

### Disaster Recovery Procedure

```bash
# 1. Stop all services
docker compose down

# 2. Restore database
zcat /backup/nextcloud/db_nextcloud_20260712_020000.sql.gz | \
  docker exec -i nc-db mysql -u root -p"${DB_ROOT_PASSWORD}" nextcloud

# 3. Restore data
docker compose up -d db redis
sleep 30
docker rm -f nc-nextcloud
docker volume rm nextcloud-suite_nextcloud-data  # if using volumes
docker cp /backup/nextcloud/nc_data_*.tar.gz nc-nextcloud:/tmp/
docker exec nc-nextcloud tar xzf /tmp/nc_data_*.tar.gz -C /var/www/html/data

# 4. Restart
docker compose up -d
```

## Troubleshooting

### Q1: Collabora Cannot Connect

**Symptoms**: Error "Cannot connect to Collabora Online" when opening documents

**Solution**:
```bash
# Check Collabora container logs
docker logs nc-collabora

# Confirm domain configuration is correct
# In .env, COLLABORA_DOMAIN uses regex format
COLLABORA_DOMAIN=nextcloud\.yourdomain\.com

# Check firewall
sudo ufw allow 9980/tcp
```

### Q2: Large File Upload Fails

**Symptoms**: Files over 2GB fail to upload

**Solution**:
```bash
# Modify php.ini
sudo docker exec -it nc-nextcloud bash
# Edit /usr/local/etc/php/conf.d/uploads.ini
upload_max_filesize = 10G
post_max_size = 10G
max_execution_time = 3600
max_input_time = 3600
memory_limit = 512M
```

### Q3: Mail Server Cannot Send/Receive

**Symptoms**: SMTP/IMAP connection fails

**Solution**:
```bash
# Check if ports are open
sudo ss -tlnp | grep -E ':(25|143|587|993)'

# Check DNS MX records
dig MX yourdomain.com

# Check mail logs
docker logs nc-mail

# Common causes:
# 1. Cloud provider blocks port 25 → Use port 587 STARTTLS
# 2. SPF/DKIM/DMARC not configured → Emails marked as spam
# 3. IPv6 issues → Disable IPv6 or configure dual-stack
```

### Q4: Performance Issues

**Symptoms**: Slow response with many files

**Solution**:
```bash
# 1. Enable file indexing
sudo docker exec -it nc-nextcloud php occ files:scan --all

# 2. Clean unused files
sudo docker exec -it nc-nextcloud php occ files:cleanup

# 3. Check database performance
sudo docker exec -it nc-db mysql -u root -p"${DB_ROOT_PASSWORD}" -e "SHOW STATUS LIKE 'Innodb_buffer_pool%';"

# 4. Monitor resource usage
docker stats --no-stream
```

## Security Hardening Checklist

| Item | Action |
|------|--------|
| **Strong Passwords** | Admin password at least 16 chars with mixed case, numbers, special chars |
| **2FA** | Enable TOTP two-factor authentication |
| **IP Whitelist** | Restrict admin panel to specific IPs |
| **Regular Updates** | Check and update Docker images monthly |
| **Backup Encryption** | Encrypt backup files with `gpg` |
| **Firewall** | Only expose ports 80/443, restrict others to internal network |
| **Fail2Ban** | Enable brute-force protection |
| **Audit Logs** | Enable Nextcloud audit logging to monitor suspicious activity |

### Enable Fail2Ban

```bash
# Install fail2ban
sudo apt install -y fail2ban

# Create Nextcloud jail
sudo cat > /etc/fail2ban/jail.local << 'EOF'
[nextcloud]
enabled = true
port = http,https
filter = nextcloud
logpath = /var/www/html/data/nextcloud.log
maxretry = 5
bantime = 3600
findtime = 600
EOF

# Create filter
sudo mkdir -p /etc/fail2ban/filter.d
sudo cat > /etc/fail2ban/filter.d/nextcloud.conf << 'EOF'
[Definition]
failregex = ^.*"message":"Login failed:.*$
ignoreregex =
EOF

sudo systemctl enable fail2ban
sudo systemctl restart fail2ban
```

## Cost Estimation

| Item | Monthly | Yearly |
|------|---------|--------|
| VPS (4-core 8GB) | $7-21 | $84-252 |
| Domain | $5-14 | $5-14 |
| SSL Certificate | Free (Let's Encrypt) | Free |
| **Total** | **$12-35/month** | **$89-266/year** |

Comparison with cloud SaaS:
- Google Workspace: $7/user/year × N users
- Microsoft 365: $9/user/year × N users
- Dropbox Business: $12/user/year × N users

For teams of **under 3 people**, self-hosting costs only **10-20%** of SaaS alternatives.

## Conclusion

Through this guide, you've successfully built a complete personal cloud office suite:

✅ **Nextcloud** — File sync, sharing, and collaboration  
✅ **Collabora** — Online document editing (Writer, Calc, Presentation)  
✅ **Talk** — Private video conferencing and instant messaging  
✅ **Mail** — Unified email management  
✅ **Automated Backups** — Daily full backup + remote storage  
✅ **Security Hardening** — SSL, Fail2Ban, 2FA  

The core philosophy of this setup is: **data sovereignty + cost control + feature completeness**. Whether you're an individual user or a small team, you can enjoy an experience comparable to commercial SaaS while protecting your privacy and reducing costs significantly.
