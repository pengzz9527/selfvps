---
title: "1Panel Self-Hosted Control Panel: Zero-CLI VPS Management Made Simple"
description: "1Panel is a modern open-source Linux control panel — deploy web apps, SSL certificates, databases, and Docker containers with a single click. Visual full-stack management that replaces paid alternatives, zero cost to control your VPS."
date: 2026-09-19T10:00:00+08:00
lastmod: 2026-09-19T10:00:00+08:00
slug: "1panel-selfhosted-vps-panel"
image: /images/posts/1panel-selfhosted-vps-panel/featured.png
tags: ["1Panel", "VPS", "Control Panel", "Docker", "Self-Hosted", "Visualization", "Zero-Cost", "DevOps"]
categories: ["Operations", "Self-Hosting"]
aliases: [/en/post/1panel-selfhosted-vps-panel/]
---

## Why Do You Need 1Panel?

You might have experienced this:

> You just bought a VPS and want to set up a website. You spend half an hour reading documentation — Nginx config, SSL certificates, Docker Compose, reverse proxies... you type a bunch of commands, and the site still returns 404.

Manually configuring every service is tedious. Most commercial panels (like aaPanel/BT Panel) limit features in their free tiers and charge for advanced functionality. **1Panel** was built to solve exactly this problem — **open-source, free, Docker-based, modern UI, full-featured without阉割**.

---

## 1Panel Core Features

| Feature | Description |
|---------|-------------|
| App Store | One-click deploy 50+ popular apps: WordPress, Nginx, MySQL, Redis, Docker, and more |
| Web Services | Visual Nginx configuration — reverse proxy, load balancing, auto HTTPS renewal |
| Database | GUI management for MySQL, PostgreSQL, Redis, MongoDB — with backup/restore |
| Docker Management | Visual operations for images, containers, networks, and volumes — no CLI needed |
| File Manager | Online file editor, archive management, permission settings |
| Monitoring & Alerts | Real-time CPU/memory/disk/network charts, alerts via Telegram/Discord/Email |
| Scheduled Tasks | Automated backups, cleanup, script execution with Cron expressions |
| Security Hardening | SSH port change, Fail2Ban integration, firewall rule management |

---

## 1Panel vs aaPanel (BT Panel) Comparison

| Feature | 1Panel | aaPanel (Free) |
|---------|--------|----------------|
| Price | **Completely free & open-source** | Basic features free, advanced features paid |
| Architecture | Docker containerized deployment | Traditional process management, relies on system env |
| Security | Container isolation, low pollution risk | Shared environment, one app crash affects all |
| UI | Modern, responsive design | Traditional interface |
| Extensibility | Native Docker Compose support | Limited |
| Community | Active, frequent updates | Stable but slower release cadence |

---

## Step 1: One-Command Installation

### System Requirements

- OS: Ubuntu 20.04+ / Debian 11+ / CentOS 8+ / Rocky Linux 9+
- Memory: ≥ 1GB (2GB+ recommended)
- Disk: ≥ 10GB available space
- Privileges: root or sudo

### Installation Command

```bash
# Use the official one-liner (recommended)
curl -sSL https://resource.fit2cloud.com/1panel/package/quick_start.sh -o quick_start.sh
sudo bash quick_start.sh install
```

During installation, you'll be prompted to set the admin username and password — write them down securely:

```
=========================================
        1Panel Installation Complete
=========================================
Panel Address: http://YOUR_VPS_IP:38080/xK9mP2vL
Username: admin
Password: [randomly generated strong password]
=========================================
```

> **Note**: On first login, change the default password immediately, and restrict port 38080 in the firewall to trusted IPs only.

---

## Step 2: Initial Setup & Security Hardening

### 1. Change the Default Port

After logging in, go to **Panel Settings** → **Security Settings**, change the access port from 38080 to an uncommon port (e.g., 28080), and enable SSL.

### 2. Bind Domain + HTTPS

```bash
# Add a site in 1Panel
# Enter your domain, e.g., panel.yourdomain.com
# 1Panel will automatically provision a Let's Encrypt certificate
```

### 3. Enable Two-Factor Authentication (2FA)

In **Panel Settings** → **Security Settings**, enable TOTP 2FA. Scan the QR code with Google Authenticator or Authy.

### 4. Configure IP Whitelist

Restrict panel access to specific IP ranges in Security Settings to prevent brute-force attacks.

---

## Step 3: Deploy Your First Web Application

Let's deploy WordPress as an example:

### Method 1: One-Click from App Store

1. Go to **App Store**, search for "WordPress"
2. Click Install, fill in the database password
3. Wait for installation to complete, click "Access" to enter the WordPress setup wizard

### Method 2: Custom Docker Compose Deployment

For highly customized scenarios, create a custom `docker-compose.yml`:

```yaml
version: '3.8'
services:
  wordpress:
    image: wordpress:latest
    ports:
      - "8080:80"
    environment:
      WORDPRESS_DB_HOST: db
      WORDPRESS_DB_USER: wp_user
      WORDPRESS_DB_PASSWORD: ${DB_PASSWORD}
      WORDPRESS_DB_NAME: wordpress
    volumes:
      - wp_data:/var/www/html
    depends_on:
      - db
  db:
    image: mysql:8.0
    environment:
      MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT}
      MYSQL_DATABASE: wordpress
      MYSQL_USER: wp_user
      MYSQL_PASSWORD: ${DB_PASSWORD}
    volumes:
      - db_data:/var/lib/mysql
volumes:
  wp_data:
  db_data:
```

Import into 1Panel's **Containers** → **Compose** to start with one click.

---

## Step 4: Reverse Proxy & HTTPS Configuration

Suppose you've deployed an internal app (e.g., Portainer on port 9000) via 1Panel, and now you want it accessible via `portainer.yourdomain.com` with HTTPS.

### Set up reverse proxy in 1Panel:

1. Go to **Websites** → **Reverse Proxy**
2. Proxy name: `portainer`
3. Domain: `portainer.yourdomain.com`
4. Target: `127.0.0.1:9000`
5. Enable HTTPS, select auto-provision certificate

### Auto-generated Nginx config:

```nginx
server {
    listen 443 ssl http2;
    server_name portainer.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/portainer.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/portainer.yourdomain.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;

    location / {
        proxy_pass http://127.0.0.1:9000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## Step 5: Database Management & Backup Strategy

### GUI Database Management

1Panel includes phpMyAdmin (MySQL) and Adminer (PostgreSQL) — manage databases directly in your browser with no extra installation.

### Automated Backup Configuration

```
Path: Database → Select DB → Backup Policy
```

Recommended backup strategy:
- **Frequency**: Daily at 3 AM automatic backup
- **Retention**: Keep last 7 backups
- **Destination**: Local + S3/B2 remote storage (via 1Panel's file backup feature)

```bash
# Or manually trigger a backup
1panel toolbox backup --db all --target s3://your-bucket/backups/
```

---

## Step 6: Monitoring & Alerting Setup

### Enable System Monitoring

1Panel collects CPU, memory, disk, and network data by default. View real-time charts in the **Monitoring** page.

### Configure Alert Rules

1. Go to **Monitoring** → **Alert Rules**
2. Add rules such as:
   - CPU usage > 90% for 5 minutes → Send Telegram alert
   - Disk usage > 85% → Send email alert
   - Memory usage > 95% → Send Discord webhook alert

### Telegram Alert Configuration

In **Alert Settings**, fill in:
- Webhook URL: `https://api.telegram.org/bot<BOT_TOKEN>/sendMessage`
- Chat ID: Your Telegram group or channel ID

---

## Cost Comparison: 1Panel vs Commercial Panels

| Solution | Monthly Cost | Feature Limits | Best For |
|----------|-------------|----------------|----------|
| 1Panel (self-hosted) | **$0** | None | Individual devs, small teams |
| aaPanel Professional | ~$28/yr | Some advanced features | Small businesses |
| cPanel | $19+/mo | None | Web hosting providers |
| Plesk | $9+/mo | Some features | WordPress hosting |

For individuals or small teams managing 1–5 VPS instances, **1Panel is the only zero-cost full-featured option**.

---

## FAQ

### Q: Is 1Panel or aaPanel better for beginners?

A: Both are beginner-friendly. However, 1Panel's Docker-based architecture provides better app isolation — a crash won't affect other services. aaPanel's interface is more familiar to Chinese users with a richer plugin ecosystem. If you're a Docker user, choose 1Panel; if you prefer traditional LAMP/LNMP, aaPanel has a faster learning curve.

### Q: Does 1Panel support Windows?

A: Currently, 1Panel only supports Linux. Windows users can consider aaPanel Windows edition or XAMPP.

### Q: How do I migrate from aaPanel to 1Panel?

A: 1Panel provides a data migration tool that supports importing websites, databases, and FTP accounts from aaPanel. Go to **Toolbox** → **Data Migration** → **aaPanel Migration**.

### Q: Is 1Panel secure?

A: 1Panel's source code is open-source and auditable. It uses Docker container isolation and doesn't expose high-risk ports by default. Still, we recommend: ① Change the default port ② Enable HTTPS ③ Configure IP whitelist ④ Keep the panel updated.

---

## Summary

1Panel turns VPS management from "CLI anxiety" into "visual operations" — one-click app deployment, graphical Nginx config, container management, real-time monitoring and alerts, all in a modern interface. **Zero cost, open-source, containerized** — it's the management panel every VPS user should have.

If your VPS is still stuck in the command-line era, it's time to try 1Panel.
