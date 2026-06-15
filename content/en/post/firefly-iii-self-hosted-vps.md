---
title: "Self-Hosting Firefly III on VPS: Build Your Personal Finance Management System from Scratch"
description: "Say goodbye to third-party记账 apps that own your data — self-host Firefly III on your VPS, take full control of your financial data with multi-account tracking, budget management, and smart analytics."
date: 2026-06-15T10:00:00+08:00
lastmod: 2026-06-15T10:00:00+08:00
slug: "firefly-iii-self-hosted-vps"
tags: ["Firefly III", "Personal Finance", "Self-Hosting", "Docker", "Privacy", "Budgeting", "VPS"]
categories: ["Self-Hosted Apps"]
draft: false
image: /images/posts/firefly-iii-self-hosted-vps/featured.png
aliases: [/en/post/firefly-iii-self-hosted-vps/]
---

## Introduction

Have you ever used a记账 app only to realize it's uploading your spending data to the cloud? Or worse — the company goes bankrupt and years of your financial records disappear overnight?

**Your financial data belongs to you.**

Firefly III is an open-source personal finance manager that supports transaction recording, budget management, multi-currency support, and analytics reporting. Most importantly — it runs on your own VPS, keeping your data completely private.

This guide walks you through setting up Firefly III from scratch on a VPS, including Docker deployment, Nginx reverse proxy, automated backups, and day-to-day maintenance.

---

## Why Firefly III?

There are many记账 tools available — Mint, YNAB, 随手记 — but they all share one critical flaw: **your data is not under your control**.

| Feature | Firefly III | Third-Party记账 App |
|---------|-------------|---------------------|
| Data Ownership | ✅ Fully yours | ❌ Stored on provider servers |
| Privacy | ✅ End-to-end private | ❌ May be used for ad profiling |
| Cost | ✅ Free and open source | ❌ Subscription-based |
| Customizability | ✅ Fully customizable | ❌ Fixed features |
| Multi-Account | ✅ Unlimited accounts | ⚠️ Usually limited |
| API Access | ✅ RESTful API | ⚠️ Limited or none |
| Data Export | ✅ Full export | ⚠️ Format restricted |

Key features of Firefly III:

- **Transaction Management** — Record every income and expense with categories, tags, and recurring transactions
- **Budget Management** — Set monthly/weekly budgets with real-time progress tracking
- **Multi-Account Tracking** — Cash, bank accounts, credit cards, investment accounts
- **Reporting & Analytics** — Visual charts showing income and expense trends
- **Multi-Currency Support** — Built-in exchange rate updates with auto-conversion
- **API Integration** — Works with Home Assistant, Grafana, and more
- **Rule Engine** — Auto-categorize transactions to reduce manual work

---

## System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| VPS | 1 CPU / 512MB RAM | 2 CPU / 2GB RAM |
| Disk | 5GB available | 10GB+ SSD |
| OS | Ubuntu 22.04 / Debian 12 | Ubuntu 24.04 / Debian 12 |
| Domain | Optional (recommended) | Resolved domain name |

---

## Step 1: Prepare the Environment

### Install Docker and Docker Compose

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sh

# Add user to docker group
sudo usermod -aG docker $USER

# Install Docker Compose (if not pre-installed)
sudo apt install docker-compose-plugin -y

# Verify installation
docker --version
docker compose version
```

### Create Project Directory Structure

```bash
mkdir -p /opt/fireflyiii/{data,storage,uploads}
cd /opt/fireflyiii
```

---

## Step 2: Docker Compose Configuration

Create `docker-compose.yml`:

```yaml
services:
  firefly:
    image: fireflyiii/core:latest
    container_name: fireflyiii
    restart: unless-stopped
    ports:
      - "127.0.0.1:8080:8080"
    environment:
      - APP_ENV=production
      - APP_KEY=base64:YOUR_RANDOM_KEY_HERE
      - APP_URL=http://your-domain.com
      - TRUSTED_PROXIES=**
      - WEBPACK_SECURE=false
      - DB_CONNECTION=mysql
      - DB_HOST=mysql
      - DB_PORT=3306
      - DB_DATABASE=firefly
      - DB_USERNAME=firefly
      - DB_PASSWORD=YOUR_DB_PASSWORD_HERE
      - MAIL_MAILER=smtp
      - MAIL_HOST=smtp.your-mail-server.com
      - MAIL_PORT=587
      - MAIL_USERNAME=noreply@your-domain.com
      - MAIL_PASSWORD=YOUR_MAIL_PASSWORD
      - MAIL_ENCRYPTION=tls
      - MAIL_FROM_ADDRESS=noreply@your-domain.com
      - MAIL_FROM_NAME="Firefly III"
    volumes:
      - ./storage/upload:/var/www/html/storage/upload
      - ./storage/logs:/var/www/html/storage/logs
    depends_on:
      mysql:
        condition: service_healthy

  mysql:
    image: mysql:8.0
    container_name: fireflyiii-mysql
    restart: unless-stopped
    environment:
      - MYSQL_ROOT_PASSWORD=YOUR_ROOT_PASSWORD_HERE
      - MYSQL_DATABASE=firefly
      - MYSQL_USER=firefly
      - MYSQL_PASSWORD=YOUR_DB_PASSWORD_HERE
    volumes:
      - mysql_data:/var/lib/mysql
    command: >
      --default-authentication-plugin=caching_sha2_password
      --character-set-server=utf8mb4
      --collation-server=utf8mb4_unicode_ci
      --max-connections=200
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost", "-u", "firefly", "-p${MYSQL_PASSWORD}"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  mysql_data:
```

> **⚠️ Important:** Before deploying, replace all `YOUR_*_HERE` placeholders. Especially `APP_KEY`, generate one with:
> ```bash
> openssl rand -base64 32
> ```

---

## Step 3: Start the Services

```bash
cd /opt/fireflyiii
docker compose up -d

# Check logs
docker compose logs -f firefly

# Wait for initialization (first startup may take a few minutes)
```

After initialization completes, visit `http://your-domain.com` and log in with default credentials:

- Username: `firefly@fireflyiii.org`
- Password: `password`

**Change the password immediately after first login!**

---

## Step 4: Configure Nginx Reverse Proxy

Using HTTPS to protect your financial data is essential.

```nginx
server {
    listen 443 ssl http2;
    server_name your-domain.com;

    # SSL certificate (Let's Encrypt)
    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    # SSL security configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 1d;
    ssl_stapling on;
    ssl_stapling_verify on;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    client_max_body_size 50M;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
    }

    # Static asset caching
    location ~* \.(css|js|png|jpg|jpeg|gif|ico|svg|woff|woff2)$ {
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
}

# Redirect HTTP to HTTPS
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$host$request_uri;
}
```

Get SSL certificate:

```bash
sudo certbot certonly --nginx -d your-domain.com
sudo certbot renew --dry-run  # Test auto-renewal
```

---

## Step 5: Configure Email Notifications

Firefly III supports sending budget alerts and reports via email.

### SMTP Configuration

Configure `MAIL_*` environment variables in `docker-compose.yml`:

```yaml
environment:
  - MAIL_MAILER=smtp
  - MAIL_HOST=smtp.gmail.com
  - MAIL_PORT=587
  - MAIL_USERNAME=your-email@gmail.com
  - MAIL_PASSWORD=your-app-password
  - MAIL_ENCRYPTION=tls
  - MAIL_FROM_ADDRESS=your-email@gmail.com
  - MAIL_FROM_NAME="Firefly III"
```

> **Gmail users:** Use an "App Password" instead of your regular password. Enable 2FA in your Google Account first, then generate an app-specific password.

### Mailpit (Development)

If you don't want to configure a real email server, use Mailpit locally:

```yaml
services:
  mailpit:
    image: axllent/mailpit:latest
    container_name: fireflyiii-mailpit
    restart: unless-stopped
    ports:
      - "127.0.0.1:8025:8025"
    environment:
      - MP_MAX_MESSAGES=5000
      - MP_DATABASE=/data/mailpit.db
    volumes:
      - mailpit_data:/data

volumes:
  mailpit_data:
```

Set `MAIL_HOST` to `mailpit` and `MAIL_PORT` to `1025`.

---

## Step 6: Automated Backups

### Database Backup

Create backup script `/opt/fireflyiii/backup.sh`:

```bash
#!/bin/bash
set -euo pipefail

BACKUP_DIR="/opt/fireflyiii/backups"
DATE=$(date +%Y%m%d_%H%M%S)
CONTAINER="fireflyiii-mysql"
DB_USER="firefly"
DB_PASS="YOUR_DB_PASSWORD_HERE"
DB_NAME="firefly"

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Backup database
docker exec "$CONTAINER" mysqldump -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" \
  | gzip > "$BACKUP_DIR/firefly_$DATE.sql.gz"

# Remove backups older than 30 days
find "$BACKUP_DIR" -name "firefly_*.sql.gz" -mtime +30 -delete

echo "Backup completed: firefly_$DATE.sql.gz"
```

Add cron job:

```bash
chmod +x /opt/fireflyiii/backup.sh

# Daily backup at 2 AM
echo "0 2 * * * /opt/fireflyiii/backup.sh >> /opt/fireflyiii/backup.log 2>&1" | crontab -
```

### File Backup

```bash
# Backup uploaded files and config
tar czf "$BACKUP_DIR/firefly_files_$DATE.tar.gz" \
  -C /opt/fireflyiii \
  --exclude='backups' \
  --exclude='mysql_data' \
  storage upload docker-compose.yml
```

### Remote Backup (Recommended)

```bash
# Sync to remote server
rsync -avz --delete /opt/fireflyiii/backups/ user@remote-server:/backups/fireflyiii/

# Or use rclone to sync to cloud storage
rclone copy /opt/fireflyiii/backups/ remote:fireflyiii-backups/ --max-age 30d
```

---

## Step 7: Daily Usage Tips

### 1. Transaction Rules (Auto-Categorization)

Firefly III's rule engine can auto-tag transactions:

```
Rule examples:
- If description contains "Starbucks" → Category: "Dining", Tag: "Coffee"
- If description contains "salary" → Category: "Income", Tag: "Monthly Salary"
- If amount > $1000 and Category: "Shopping" → Tag: "Large Purchase"
```

### 2. Import Bank Statements

Supports CSV, OFX, and QIF formats:

```bash
# Export CSV from your bank, then import via web UI
# Set mapping rules to auto-match fields
```

### 3. Budget Alerts

- Go to the "Budgets" page
- Set category budget limits per month
- Enable email alerts at 80% and 100% spending thresholds

### 4. API Integration

Firefly III provides a full RESTful API:

```bash
# Get API Token (generate in web UI)
# Query last 7 days of transactions
curl -H "Authorization: Bearer YOUR_TOKEN" \
  "https://your-domain.com/api/v1/transactions?date_start=2026-06-08&date_end=2026-06-15"

# Integrate with Grafana using InfluxDB + Telegraf for long-term trend analysis
```

### 5. Multi-Currency Support

```
- Add supported currencies
- Set exchange rate source (ECB or custom)
- Auto-convert at daily exchange rate when creating transactions
```

---

## Step 8: Security Hardening

### 1. Enable Two-Factor Authentication

Enable TOTP 2FA in "Settings" → "Security". Use Authy or Google Authenticator.

### 2. IP Whitelisting

Add IP restriction in Nginx config:

```nginx
allow 203.0.113.0/24;  # Your IP range
deny all;
```

### 3. Regular Updates

```bash
# Weekly update check
docker compose pull && docker compose up -d

# Or use Watchtower for auto-updates
docker run -d \
  --name watchtower \
  -v /var/run/docker.sock:/var/run/docker.sock \
  containrrr/watchtower \
  --cleanup --schedule "0 3 * * 0" \
  fireflyiii
```

### 4. Firewall Configuration

```bash
# Only allow necessary ports
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

---

## FAQ

### Q: Can't modify some settings after first login?

Run the database migration command:

```bash
docker exec -it fireflyiii php artisan firefly-iii:upgrade-database
```

### Q: How to migrate to a new server?

```bash
# Export from old server
docker exec fireflyiii-mysql mysqldump -u firefly -p firefly > dump.sql
tar czf files.tar.gz storage upload

# Import on new server
docker compose up -d
docker exec -i fireflyiii-mysql mysql -u firefly -p firefly < dump.sql
tar xzf files.tar.gz -C /opt/fireflyiii/
```

### Q: Database is getting too large?

```bash
# Optimize database tables
docker exec -it fireflyiii php artisan db:optimize

# Archive old data
docker exec -it fireflyiii php artisan firefly-iii:archive-old-transactions
```

### Q: How to restore from backup?

```bash
# Stop services
docker compose down

# Restore database
gunzip < backups/firefly_20260615_020000.sql.gz | docker exec -i fireflyiii-mysql mysql -u firefly -p firefly

# Restore files
tar xzf backups/firefly_files_20260615.tar.gz -C /opt/fireflyiii/

# Restart
docker compose up -d
```

---

## Summary

Firefly III is a powerful, fully private personal finance management solution. By self-hosting, you gain:

- **Data Sovereignty** — All financial data stored locally,不受第三方限制
- **Complete Freedom** — Customize categories, tags, and rules to match your habits
- **Zero Cost** — Open source and free, only VPS costs
- **Ecosystem Integration** — Connect with Home Assistant, Grafana, and more via API

For users who value privacy and want full control over their financial data, Firefly III is one of the best self-hosted solutions available today.

---

## References

- [Firefly III Documentation](https://docs.firefly-iii.org/)
- [GitHub Repository](https://github.com/firefly-iii/firefly-iii)
- [Docker Hub](https://hub.docker.com/r/fireflyiii/core)
- [Firefly III Community Forum](https://forums.firefly-iii.org/)
