---
title: "Self-Hosted Bitwarden Password Manager: Complete Docker Deployment Guide"
description: "Deploy Bitwarden on your own VPS for free, open-source password management with full data control. Ditch expensive 1Password and LastPass subscriptions while enjoying faster sync speeds and higher privacy."
date: 2026-09-17
lastmod: 2026-09-17
slug: "vps-bitwarden-self-hosted"
image: "/images/posts/vps-bitwarden-self-hosted/featured-en.png"
tags: ["Bitwarden", "Password Manager", "Self-Hosting", "Docker", "Cybersecurity", "Open Source", "VPS", "Privacy"]
categories: ["Self-Hosted Tools"]
aliases: [/en/post/vps-bitwarden-self-hosted/]
---

## Introduction

How many passwords do you have?

10? 50? Or more than 100?

Every website, every app, every service needs a password—email, banking, social media, work systems... You can't possibly remember them all, and using the same password everywhere is dangerously insecure.

So you subscribe to **1Password** or **LastPass**, paying $3-$4/month, storing your data on someone else's server. Until one day—

- LastPass gets breached, 8 million users' passwords leaked;
- 1Password raises prices to $36/year per person, family plan even more;
- You discover that so-called "secure encryption" actually keeps the keys in the provider's hands.

**Why hand over the keys to your digital identity to strangers?**

Bitwarden's open-source edition offers a completely different approach: **run your own password manager on your server, maintain full data control, zero cost, unlimited users.** This guide walks you through deploying a complete self-hosted Bitwarden solution from scratch.

---

## 1. Why Self-Host Bitwarden?

| Comparison | Paid Cloud (1Password/LastPass) | Self-Hosted Bitwarden |
|------------|--------------------------------|----------------------|
| **Cost** | $36-48/year per person | **Free** (only VPS cost) |
| **Data Privacy** | Encryption keys held by provider | **Keys entirely in your hands** |
| **User Limit** | Per-seat pricing | **Unlimited** |
| **Sync Speed** | Through overseas servers | **Local/near-end, very fast** |
| **Feature Completeness** | Some features require payment | **All features free and open** |
| **Auditability** | Cannot audit | **Full code and data audit possible** |
| **Compliance** | Relies on third party | **Meets your own compliance needs** |
| **Offline Use** | Limited | **Fully supported** |

The core advantage of self-hosted Bitwarden: **You're not "renting" a password manager—you're "owning" it.** This means:

- Your password vault exists only on your server
- No one can access your encrypted data, not even Bitwarden official
- You can export, migrate, or audit your data at any time
- Team, family, friends—use as many as you want, completely free

---

## 2. System Requirements

Bitwarden self-hosted has very low resource requirements:

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| **VPS RAM** | 512MB | 1GB+ |
| **Disk Space** | 1GB | 5GB+ (grows with data) |
| **CPU** | 1 core | 1-2 cores |
| **OS** | Ubuntu 20.04+ / Debian 11+ | Same |
| **Domain** | Required (for HTTPS) | Subdomain is fine |
| **Docker** | 20.10+ | Latest version |

Your VPS doesn't need high specs. In fact, Bitwarden's official minimum recommendation is just 512MB RAM—meaning even a $5/month lightweight VPS can run it.

> **Tip**: If you already have a running VPS, you can add Docker Compose directly—no need to buy a separate server.

---

## 3. Architecture Overview

```
┌──────────────────────────────────────────────────────┐
│              Your Domain (vault.yourdomain.com)       │
│                          │                           │
│                    ┌─────▼─────┐                     │
│                    │   Nginx   │ ← HTTPS reverse proxy│
│                    │  + Certbot│    Auto-renew Let's  │
│                    └─────┬─────┘    Encrypt certs     │
│                          │                           │
│              ┌───────────┼───────────┐               │
│              │           │           │               │
│        ┌─────▼─────┐ ┌──▼────┐ ┌───▼────┐         │
│        │ Bitwarden │ │ MySQL │ │ SSH fwd│         │
│        │  (API)    │ │/PgSQL │ │(admin) │         │
│        └─────┬─────┘ └───┬───┘ └───┬────┘         │
│              │           │           │             │
│        ┌─────▼───────────▼───────────▼─────┐       │
│        │         Docker Compose             │       │
│        │      (Three-container setup)       │       │
│        └────────────────────────────────────┘       │
└──────────────────────────────────────────────────────┘
```

Core components:
- **Bitwarden container**: Provides Web Vault, API, Identity, and Notification services
- **MySQL 8**: Stores encrypted password data (PostgreSQL also supported)
- **Nginx**: Reverse proxy + HTTPS termination
- **Certbot**: Automatic SSL certificate issuance and renewal

---

## 4. One-Click Deployment (Docker Compose)

### 4.1 Install Docker and Docker Compose

```bash
# Ubuntu/Debian
curl -fsSL https://get.docker.com | sh
docker compose plugin install  # Built-in for Docker 23+, otherwise:
# apt install docker-compose-plugin
```

### 4.2 Create Deployment Directory

```bash
mkdir -p ~/bitwarden && cd ~/bitwarden
```

### 4.3 Generate Key Environment Variables

You need two critical values: **master_password** (admin password) and **installation token**.

```bash
# Generate random install token
docker run --rm bitwardenrs/server:latest gen-install-token

# Generate random master password (or set your own strong one)
openssl rand -base64 32
```

### 4.4 Create .env Configuration

```bash
cat > .env << 'EOF'
# ===== Basic Configuration =====
BITWARDENSSL_ENABLED=true
BITWARDENSSL_CERT_FILE=/etc/ssl/vault.crt
BITWARDENSSL_KEY_FILE=/etc/ssl/vault.key

# ===== Domain =====
DOMAIN=vault.yourdomain.com

# ===== Database (MySQL) =====
MYSQL_ROOT_PASSWORD=$(openssl rand -base64 32)
MYSQL_DATABASE=bitwarden
MYSQL_USER=bitwarden
MYSQL_PASSWORD=$(openssl rand -base64 32)

# ===== Admin Password =====
ADMIN_TOKEN=$(openssl rand -base64 48)

# ===== Email (for password reset notifications) =====
SMTP_HOST=smtp.yourdomain.com
SMTP_PORT=587
SMTP_FROM=noreply@yourdomain.com
SMTP_SSL=true
SMTP_USERNAME=your_smtp_user
SMTP_PASSWORD=your_smtp_pass

# ===== Feature Flags =====
SIGNUPS_ALLOWED=false
INVITATIONS_ALLOWED=false
EOF
```

> **Security Note**: Never commit `.env` files to Git! Add `.env` to your `.gitignore`.

### 4.5 Create docker-compose.yml

```yaml
version: "3.8"

services:
  # ── Bitwarden Main Service ──
  bitwarden:
    image: bitwardenrs/server:latest
    container_name: bitwarden
    restart: unless-stopped
    ports:
      - "127.0.0.1:8089:80"
    environment:
      WEBSITE_HOSTNAME: "${DOMAIN}"
      SIGNUPS_ALLOWED: "false"
      ADMIN_TOKEN: "${ADMIN_TOKEN}"
      MYSQL_HOST: db
      MYSQL_PORT: 3306
      MYSQL_DATABASE: bitwarden
      MYSQL_USER: bitwarden
      MYSQL_PASSWORD: "${MYSQL_PASSWORD}"
      SMTP_HOST: "${SMTP_HOST}"
      SMTP_PORT: "${SMTP_PORT}"
      SMTP_FROM: "${SMTP_FROM}"
      SMTP_SSL: "${SMTP_SSL}"
      SMTP_USERNAME: "${SMTP_USERNAME}"
      SMTP_PASSWORD: "${SMTP_PASSWORD}"
    volumes:
      - ./bwdata/icons:/opt/bitwarden/web/assets/icons
    depends_on:
      - db

  # ── MySQL Database ──
  db:
    image: mysql:8.0
    container_name: bitwarden-db
    restart: unless-stopped
    command: --default-authentication-plugin=mysql_native_password
    environment:
      MYSQL_ROOT_PASSWORD: "${MYSQL_ROOT_PASSWORD}"
      MYSQL_DATABASE: bitwarden
      MYSQL_USER: bitwarden
      MYSQL_PASSWORD: "${MYSQL_PASSWORD}"
    volumes:
      - ./bwdata/db:/var/lib/mysql
    networks:
      default:
        aliases:
          - db

networks:
  default:
    driver: bridge
```

### 4.6 Start the Services

```bash
# Create data directories
mkdir -p bwdata/db bwdata/icons

# Start
docker compose up -d

# Check logs
docker compose logs -f bitwarden
```

Wait about 30-60 seconds. When ready, you'll see output like:

```
bitwarden    | [2026-09-17 10:00:00][][info]: Server listening on http://0.0.0.0:80
bitwarden    | [2026-09-17 10:00:00][][info]: Administration token: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

---

## 5. Configure Nginx Reverse Proxy and HTTPS

### 5.1 Install Nginx and Certbot

```bash
apt update && apt install -y nginx certbot python3-certbot-nginx
```

### 5.2 Create Nginx Configuration

```bash
cat > /etc/nginx/sites-available/vault.yourdomain.com << 'EOF'
server {
    listen 80;
    server_name vault.yourdomain.com;

    location / {
        return 301 https://$host$request_uri;
    }
}

server {
    listen 443 ssl http2;
    server_name vault.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/vault.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/vault.yourdomain.com/privkey.pem;
    ssl_trusted_certificate /etc/letsencrypt/live/vault.yourdomain.com/chain.pem;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers on;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_session_timeout 1d;
    ssl_session_cache shared:SSL:10m;
    ssl_session_tickets off;
    ssl_stapling on;
    ssl_stapling_verify on;

    client_max_body_size 128M;

    location / {
        proxy_pass http://127.0.0.1:8089;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded Proto $scheme;
        proxy_buffering off;
        proxy_request_buffering off;
    }

    location /notifications/hub {
        proxy_pass http://127.0.0.1:8089;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_buffering off;
    }

    location /notifications/hub/negotiate {
        proxy_pass http://127.0.0.1:8089;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_buffering off;
    }
}
EOF

ln -s /etc/nginx/sites-available/vault.yourdomain.com /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
```

### 5.3 Request SSL Certificate

```bash
# Ensure your domain's A record points to your VPS IP
# Then request the certificate
certbot --nginx -d vault.yourdomain.com --non-interactive --agree-tos --email your@email.com

# Set up auto-renewal (Certbot usually configures this automatically)
systemctl status certbot.timer
```

### 5.4 Restart Bitwarden for HTTPS

```bash
docker compose restart bitwarden
```

Now visiting `https://vault.yourdomain.com` should show the Bitwarden login page.

---

## 6. Create Admin Account and Import Passwords

### 6.1 Get the Admin Registration Token

```bash
docker exec bitwarden cat /etc/bitwarden/admin_token
# Or read from .env
grep ADMIN_TOKEN .env
```

### 6.2 Create Admin Account

```bash
# Create admin via CLI (recommended method)
docker exec -it bitwarden /usr/local/bin/bw register \
  --masterpasswordhash "$(echo -n 'your_master_password' | sha256sum | cut -d' ' -f1)" \
  --email "admin@yourdomain.com" \
  --token "$(grep ADMIN_TOKEN .env | cut -d'=' -f2)"
```

### 6.3 Login to Web Interface

1. Open `https://vault.yourdomain.com`
2. Log in with the admin account created above
3. Go to **Tools → Import Data**
4. Select source format (1Password, LastPass, KeePass, Chrome, etc.)
5. Upload the exported encrypted file and complete the migration

### 6.4 Disable Public Registration

```bash
# Confirm Signups is disabled (set in .env)
grep SIGNUPS_ALLOWED .env
# Should output: SIGNUPS_ALLOWED=false

# Restart to apply
docker compose restart bitwarden
```

---

## 7. Client Configuration

Bitwarden clients are available on all platforms:

| Platform | Download |
|----------|----------|
| **Web Interface** | `https://vault.yourdomain.com` |
| **Desktop (Windows/Mac/Linux)** | [bitwarden.com/download](https://bitwarden.com/download/) |
| **Mobile (iOS/Android)** | App Store / Google Play search "Bitwarden" |
| **Browser Extension** | Chrome / Firefox / Edge extension stores |
| **Command Line** | `brew install bitwarden-cli` or `snap install bitwarden` |

### Change Server Address (Critical Step)

By default, Bitwarden clients connect to the official server `vault.bitwarden.com`. You need to manually change this to your own VPS:

**Method 1: Via Settings (Recommended)**

Desktop client → Settings → Advanced → Server Uri:
```
https://vault.yourdomain.com
```

**Method 2: Modify hosts file (not recommended, temporary only)**

```bash
echo "123.45.67.89  vault.bitwarden.com" | sudo tee -a /etc/hosts
```

**Method 3: DNS redirection (production recommended)**

Point `vault.yourdomain.com` DNS A record to your VPS IP at your DNS provider.

**Recommended Method 1**: Change the Server Uri in client settings.

---

## 8. Security Hardening

Self-hosting gives you freedom, but also full security responsibility. Here are essential hardening measures:

### 8.1 Enable Two-Factor Authentication (2FA)

After logging in as admin, immediately enable TOTP 2FA for all accounts:

1. Go to **Settings → Security → Two-Factor Authentication**
2. Select **Authenticator App**
3. Scan the QR code with Google Authenticator / Authy
4. **Save your recovery codes!**

### 8.2 Restrict Admin Access

```bash
# Only allow specific IPs to access admin panel
# Add to Nginx config
location /admin {
    allow 1.2.3.4;  # Your management IP
    deny all;
    proxy_pass http://127.0.0.1:8089;
}
```

### 8.3 Regular Backups

```bash
# Create backup script
cat > ~/bitwarden/backup.sh << 'EOF'
#!/bin/bash
BACKUP_DIR="/backup/bitwarden"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p $BACKUP_DIR

# Backup database
docker exec bitwarden-db mysqldump -u bitwarden -p${MYSQL_PASSWORD} bitwarden > $BACKUP_DIR/db_$DATE.sql
# Backup Bitwarden data directory
tar czf $BACKUP_DIR/bwdata_$DATE.tar.gz /root/bitwarden/bwdata/
# Delete backups older than 30 days
find $BACKUP_DIR -name "*.sql" -mtime +30 -delete
find $BACKUP_DIR -name "bwdata_*.tar.gz" -mtime +30 -delete
echo "Backup completed: $DATE"
EOF

chmod +x ~/bitwarden/backup.sh

# Add to crontab (daily at 3 AM)
(crontab -l 2>/dev/null; echo "0 3 * * * /root/bitwarden/backup.sh") | crontab -
```

### 8.4 Firewall Configuration

```bash
# Only open necessary ports
ufw default deny incoming
ufw allow 80/tcp    # HTTP (redirects to HTTPS)
ufw allow 443/tcp   # HTTPS
ufw allow 22/tcp    # SSH
ufw enable
```

### 8.5 Disable Unnecessary Features

In `.env`:

```bash
# Disable registration (already set)
SIGNUPS_ALLOWED=false
# Disable invitations
INVITATIONS_ALLOWED=false
# Disable password generation history (reduce data exposure)
PASSWORD_HISTORY_ENABLED=false
```

---

## 9. Troubleshooting

### Issue 1: Cannot login, "password error"

Bitwarden uses PBKDF2 key derivation. Make sure you're using your **master password**, not your email password. If you forgot it:

```bash
# Reset admin password (requires server access)
docker exec -it bitwarden /usr/local/bin/bw reset-admin-password \
  --newpassword "YourNewMasterPassword"
```

### Issue 2: Client cannot connect to server

Check the following:
1. Server URL is correct (must start with `https://`)
2. SSL certificate is valid (`curl -I https://vault.yourdomain.com`)
3. Firewall allows port 443
4. Docker container is running (`docker compose ps`)

### Issue 3: Attachment upload fails

Bitwarden stores attachments on local filesystem by default. Ensure:
- `bwdata` directory has write permissions
- `client_max_body_size` is set large enough in Nginx config
- Sufficient disk space

For S3-compatible object storage, mount MinIO:

```yaml
# Add to docker-compose.yml
  minio:
    image: minio/minio:latest
    command: server /data --console-address ":9001"
    ports:
      - "127.0.0.1:9000:9000"
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: $(openssl rand -base64 32)
    volumes:
      - ./bwdata/minio:/data
```

Then add to Bitwarden environment variables:

```bash
ATTACHMENTS_EXTENSION__S3__BUCKET=bitwarden-attachments
ATTACHMENTS_EXTENSION__S3__REGION=us-east-1
ATTACHMENTS_EXTENSION__S3__USE_PATH_STYLE=false
ATTACHMENTS_EXTENSION__S3__URL=http://127.0.0.1:9000
ATTACHMENTS_EXTENSION__S3__KEY=minioadmin
ATTACHMENTS_EXTENSION__S3__SECRET=your_minio_secret
```

### Issue 4: Database size growing too fast

MySQL data files grow with usage. Recommendations:
- Run periodic optimization: `docker exec bitwarden-db mysql -u root -p${MYSQL_ROOT_PASSWORD} bitwarden -e "OPTIMIZE TABLE cards; OPTIMIZE TABLE send; OPTIMIZE TABLE attachment;"`
- Monitor disk usage: `docker exec bitwarden-db du -sh /var/lib/mysql/`

---

## 10. Upgrades and Maintenance

### Upgrading Bitwarden

```bash
cd ~/bitwarden
docker compose pull
docker compose up -d
```

Always backup before upgrading:

```bash
./backup.sh
```

### Monitoring Service Status

```bash
# Check container status
docker compose ps

# View live logs
docker compose logs -f

# Check resource usage
docker stats bitwarden
```

Under normal conditions, the Bitwarden container uses approximately **80-150MB RAM**—very lightweight.

---

## Summary

The core value of self-hosting Bitwarden: **you take back control of your password management from providers.**

For less than $5/month in VPS costs, you gain:
- ✅ **Complete data sovereignty** — only you can decrypt your passwords
- ✅ **Unlimited free users** — no extra charges for family or team plans
- ✅ **Faster experience** — low-latency sync on your own infrastructure
- ✅ **Zero vendor lock-in** — export data to standard formats anytime
- ✅ **100% feature-complete** — no paywalls, no feature restrictions

Migrating from LastPass or 1Password is smooth—just export your CSV/encrypted file and import it into Bitwarden. Spend 30 minutes setting up, then save hundreds of dollars in subscription fees every year.

**Your passwords. Your server. Your rules.**

---

## Related Resources

- [Bitwarden Official Documentation](https://help.bitwarden.com/article/self-hosting/)
- [Bitwarden GitHub Repository](https://github.com/dani-garcia/vaultwarden)
- [Let's Encrypt Certificate Issuance](https://letsencrypt.org/)
- [Docker Compose Best Practices](https://docs.docker.com/compose/best-practices/)
