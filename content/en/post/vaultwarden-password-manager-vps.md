---
title: "Self-Host Vaultwarden Password Manager on VPS — Free, Secure, Open Source Bitwarden Alternative"
description: "Deploy Vaultwarden with Docker on your VPS — fully compatible with Bitwarden clients, supports 2FA, secure sharing, and password generation. No subscription fees, your data stays yours."
date: 2026-07-01T10:00:00+08:00
lastmod: 2026-07-01T10:00:00+08:00
slug: "vaultwarden-password-manager-vps"
tags: ["Vaultwarden", "Password Manager", "Bitwarden", "Docker", "Self-Hosting", "Data Security", "VPS Deployment", "Privacy"]
categories: ["Deployment Guides"]
draft: false
image: /images/posts/vaultwarden-password-manager-vps/featured.png
aliases: [/en/post/vaultwarden-password-manager-vps/]
---

## Why Self-Host a Password Manager?

In the digital age, the average person manages **50-150 passwords**. Using "123456" or "password" across all accounts is like hanging your house key on the front door. A password manager encrypts and stores all your credentials while generating strong, unique passwords for every site.

Commercial password managers (1Password, LastPass, Bitwarden Cloud) are convenient but come with drawbacks:

- **Ongoing subscription costs**: 1Password costs $3-5/user/month, LastPass Premium is $3/month
- **Data not in your control**: Passwords stored on third-party servers carry breach risks
- **Service interruption risk**: Commercial services may shut down or change pricing
- **Privacy concerns**: Even with zero-knowledge encryption, trusting a third party always carries some risk

**Vaultwarden** offers a perfect alternative — it's an open-source, lightweight reimplementation of the Bitwarden server written in Rust, fully compatible with all official Bitwarden clients.

## What is Vaultwarden?

Vaultwarden (formerly bitwarden_rs) is a third-party Bitwarden server implementation with these features:

| Feature | Details |
|---------|---------|
| **Language** | Rust — high performance, low memory footprint |
| **Compatibility** | Fully compatible with official Bitwarden clients (desktop, mobile, browser extensions) |
| **Database** | SQLite (lightweight) or PostgreSQL (high concurrency) |
| **Resource Requirements** | Runs on as little as 64MB RAM |
| **License** | Apache 2.0 — completely free and open source |
| **Features** | Password storage, secure sharing, two-factor authentication, password generator, TOTP authenticator |

## Prerequisites

You'll need a VPS running:

- **OS**: Ubuntu 22.04 LTS or Debian 12
- **RAM**: At least 512MB (1GB recommended)
- **Storage**: At least 5GB available
- **Domain**: Pointing to your VPS IP (for HTTPS)
- **Installed**: Docker and Docker Compose

If Docker isn't installed yet:

```bash
# Install Docker
curl -fsSL https://get.docker.com | sh

# Add your user to the docker group
sudo usermod -aG docker $USER

# Verify installation
docker --version
docker compose version
```

## Deploying Vaultwarden

### Step 1: Create Project Directory

```bash
mkdir -p ~/vaultwarden/data
cd ~/vaultwarden
```

### Step 2: Write docker-compose.yml

```yaml
services:
  vaultwarden:
    image: vaultwarden/server:latest
    container_name: vaultwarden
    restart: always
    ports:
      - "80:80"
      - "443:443"
    environment:
      # Admin email (for admin notifications)
      ADMIN_TOKEN: "$(openssl rand -base64 32)"
      # Website domain
      SIGNUPS_ALLOWED: "false"
      DOMAIN: "https://your-domain.com"
      # Database path
      DATABASE_URL: /data/db.sqlite3
      # Enable Web Vault (web-based admin interface)
      WEBSOCKET_ENABLED: "true"
      WEBSOCKET_ADDRESS: "0.0.0.0"
      WEBSOCKET_PORT: "3012"
      # Log rotation
      LOG_FILE: "/data/vaultwarden.log"
      MAX_LOG_SIZE: "10MB"
      # Backup folder
      BACKUP_FOLDER: "/data/backups"
    volumes:
      - ./data:/data
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

> **Security note**: In production, replace `ADMIN_TOKEN` with a randomly generated strong password and store it securely.

### Step 3: Start the Service

```bash
docker compose up -d
```

Wait a few seconds, then check the container status:

```bash
docker compose ps
```

You should see the `vaultwarden` container in `healthy` status.

### Step 4: Configure Reverse Proxy & HTTPS

Vaultwarden requires HTTPS to function (Bitwarden clients enforce this). Recommended options:

#### Option A: Use Caddy (Recommended — Automatic HTTPS)

Add to your `docker-compose.yml`:

```yaml
  caddy:
    image: caddy:2-alpine
    container_name: caddy
    restart: always
    ports:
      - "443:443"
      - "80:80"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile
      - caddy_data:/data
      - caddy_config:/config
    depends_on:
      - vaultwarden

volumes:
  caddy_data:
  caddy_config:
```

`Caddyfile` configuration:

```
your-domain.com {
    reverse_proxy vaultwarden:80
    
    encode gzip zstd
    
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
        Referrer-Policy "strict-origin-when-cross-origin"
    }
}
```

#### Option B: Use Nginx Proxy Manager

If you already have Nginx Proxy Manager deployed (see our [Nginx Proxy Manager guide](/en/post/nginx-proxy-manager-guide/)), just add a proxy host in the panel:

- **Domain**: Your domain
- **IP**: vaultwarden container IP or `vaultwarden` (if using Docker Compose)
- **Port**: 80
- **SSL**: Request a Let's Encrypt certificate

## Initial Configuration

### Create Admin Account

1. Visit `https://your-domain.com/admin`
2. Enter the `ADMIN_TOKEN` from your `docker-compose.yml`
3. Click "Create your admin account"
4. Set admin email and password

### Disable Public Signups

For security, disable public registration and only allow admin invitations:

```yaml
environment:
  SIGNUPS_ALLOWED: "false"
  SIGNUPS_VERIFY: "true"
  INVITATIONS_ALLOWED: "true"
```

### Enable Two-Factor Authentication

Vaultwarden supports multiple TOTP implementations:

- **WebAuthn**: Using security keys (YubiKey, etc.)
- **TOTP**: Using Google Authenticator, Authy, etc.
- **DUO**: Integrated with DUO Security

In the Bitwarden client, go to **Settings > Two-step login** and choose your preferred method.

## Client Connection

Vaultwarden's biggest advantage is **full Bitwarden client compatibility**. You can use:

- **Desktop**: Native apps for Windows, macOS, Linux
- **Browser Extensions**: Chrome, Firefox, Edge, Safari
- **Mobile**: Official iOS and Android apps
- **CLI**: The `bw` command-line tool

### Adding a Custom Server

In any Bitwarden client:

1. Open **Settings > Account > Services**
2. Click **Custom**
3. Enter your Vaultwarden instance address: `https://your-domain.com`
4. Log in with your admin account

Once connected, all features (password storage, generator, security events, sharing) work normally.

## Security Hardening

### 1. Restrict Registrations

```yaml
environment:
  SIGNUPS_ALLOWED: "false"
  ADMIN_TOKEN: "$(openssl rand -base64 48)"
```

### 2. Enable Logging & Monitoring

```yaml
environment:
  LOG_FILE: "/data/vaultwarden.log"
  MAX_LOG_SIZE: "10MB"
  LOG_FORMAT: "json"
```

### 3. Regular Backups

```bash
#!/bin/bash
# backup-vaultwarden.sh
BACKUP_DIR="$HOME/vaultwarden/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
mkdir -p "$BACKUP_DIR"

docker exec vaultwarden cp /data/db.sqlite3 "/data/backup_${TIMESTAMP}.db"
docker cp vaultwarden:/data/backup_${TIMESTAMP}.db "$BACKUP_DIR/"
docker exec vaultwarden rm -f /data/backup_${TIMESTAMP}.db

# Keep only last 30 days of backups
find "$BACKUP_DIR" -name "backup_*.db" -mtime +30 -delete

echo "Backup completed: ${BACKUP_DIR}/backup_${TIMESTAMP}.db"
```

Add to crontab for automation:

```bash
crontab -e
# Daily backup at 3 AM
0 3 * * * /path/to/backup-vaultwarden.sh >> /var/log/vaultwarden-backup.log 2>&1
```

### 4. Network Isolation

Expose only necessary ports with Docker network isolation:

```yaml
networks:
  vaultwarden-net:
    driver: bridge

services:
  vaultwarden:
    networks:
      - vaultwarden-net
  caddy:
    networks:
      - vaultwarden-net
```

### 5. Firewall Rules

```bash
# Open only necessary ports
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP (redirect to HTTPS)
sudo ufw allow 443/tcp   # HTTPS
sudo ufw enable
```

## Advanced Features

### Password Health Check

Bitwarden/Vaultwarden includes built-in **security dashboard** features:

- **Reused passwords**: Detect identical passwords used across multiple sites
- **Weak passwords**: Identify passwords vulnerable to brute-force attacks
- **Breach-checked passwords**: Cross-reference with HaveIBeenPwned database
- **Unencrypted passwords**: Flag passwords not stored with encryption

Regularly review the **Security Events** page and update insecure passwords.

### Secure Sharing

Vaultwarden supports **secure sharing** — share sensitive information (WiFi passwords, API keys, configurations) via encrypted links with trusted people, without sending plaintext.

### Organizations & Teams

For small teams or families, Vaultwarden supports **Organizations**:

- Create shared family or team workspaces
- Share password vaults
- Manage member permissions
- Audit logs for tracking

### TOTP Authenticator Management

Beyond password storage, Vaultwarden works as a **TOTP authenticator**, managing your two-factor authentication codes as a replacement for Google Authenticator.

## Migration Guide

### Migrating from Other Password Managers

#### From LastPass

1. Export your LastPass CSV file
2. Import in Bitwarden client: Settings > Export > Select CSV file
3. Verify imported data integrity

#### From 1Password

1. Export from 1Password in `.1pux` or CSV format
2. Convert using [1pass-to-bitwarden](https://github.com/dghouston/1pass-to-bitwarden)
3. Import in Bitwarden client

#### From Bitwarden Cloud

1. Export data from Bitwarden web interface
2. Import into your Vaultwarden instance
3. Verify all entries

### Migration Checklist

- **Back up your existing vault before migrating**
- **Verify all critical account passwords after migration**
- **Test with a small subset first** before full migration
- **Keep the old password manager active** for 1-2 weeks as a safety net

## Troubleshooting

### Issue 1: Client Cannot Connect

**Symptom**: Bitwarden client shows "Connection error"

**Solution**:
- Confirm domain DNS resolves correctly
- Ensure HTTPS certificate is valid (self-signed certificates may cause issues)
- Verify `DOMAIN` environment variable matches the address configured in the client
- Confirm firewall allows port 443

### Issue 2: Web Vault Unreachable

**Symptom**: Accessing `/admin` returns 404

**Solution**:
- Confirm container is running: `docker compose ps`
- Check logs: `docker compose logs vaultwarden`
- Verify reverse proxy configuration is correct

### Issue 3: Disk Space Full

**Symptom**: Vaultwarden cannot write data

**Solution**:
- Clear old logs: `docker exec vaultwarden truncate -s 0 /data/vaultwarden.log`
- Check disk usage: `df -h`
- Increase storage or clean unnecessary data

### Issue 4: Lost 2FA Device

**Symptom**: Cannot log in, 2FA device unavailable

**Solution**:
- Temporarily disable 2FA for the user via admin panel
- Or reset using `ADMIN_TOKEN`

## Summary

| Item | Details |
|------|---------|
| **Setup Difficulty** | ⭐⭐☆☆☆ (Easy — one docker compose command) |
| **Resource Usage** | 64MB-256MB RAM, < 100MB disk |
| **Security** | High (AES-256 encryption, end-to-end secure) |
| **Compatibility** | Perfect — works with all Bitwarden clients |
| **Cost** | Free (only VPS hosting cost) |
| **Maintenance** | Minimal (just update container images) |

Vaultwarden is the best choice for self-hosted password management. It combines Bitwarden's full feature set with minimal resource requirements, keeping your password security entirely in your hands.

**Take action now**: Deploy Vaultwarden on your VPS and start protecting your digital life with strong passwords and two-factor authentication.

## Resources

- [Vaultwarden GitHub Repository](https://github.com/dani-garcia/vaultwarden)
- [Bitwarden Official Documentation](https://bitwarden.com/help/)
- [Have I Been Pwned](https://haveibeenpwned.com/) — Check if your passwords have been compromised
- [Nginx Proxy Manager Deployment Guide](/en/post/nginx-proxy-manager-guide/)
