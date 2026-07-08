---
title: "Build a Self-Hosted DevOps Dashboard: CloudPanel + Uptime Kuma + Gatus"
description: "A step-by-step guide to building a unified VPS management dashboard with CloudPanel, Uptime Kuma, and Gatus —告别碎片化工具"
date: 2026-07-08T10:00:00+08:00
slug: "cloudpanel-devops-dashboard"
image: /images/posts/cloudpanel-devops-dashboard/featured.png
tags: ["DevOps", "VPS", "CloudPanel", "Uptime Kuma", "Gatus", "Monitoring", "Dashboard", "Self-Hosted"]
categories: ["DevOps Practices"]
aliases: [/en/post/cloudpanel-devops-dashboard/]
---

## Introduction

> **The best operations are the ones you don't have to do.**

When managing multiple VPS instances, websites, and microservices, the biggest pain point isn't the lack of individual tools — it's **information fragmentation**. You open a panel to check resources, a monitoring tool for availability, and logs for errors. Every tool has its own interface, and troubleshooting requires switching between three browser tabs.

This guide walks you through building a **three-in-one DevOps dashboard**:

- **CloudPanel** — Lightweight VPS panel for managing sites, databases, and SSL certificates
- **Uptime Kuma** — Open-source monitoring with HTTP/TCP/Ping/DNS alerting support
- **Gatus** — Minimalist health-check engine driven by YAML configs with a built-in beautiful dashboard

All self-hosted on a single VPS. Total cost: approximately $0.

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────┐
│              Your VPS (Ubuntu 24.04)             │
│                                                  │
│  ┌──────────────┐  ┌──────────────┐             │
│  │  CloudPanel   │  │ Uptime Kuma  │             │
│  │  :8080        │  │ :3001        │             │
│  │  Site Mgmt    │  │ Monitoring   │             │
│  └──────────────┘  └──────┬───────┘             │
│                           │                      │
│                    ┌──────▼───────┐              │
│                    │   Gatus      │              │
│                    │  :8081       │              │
│                    │  Health Check│              │
│                    └──────────────┘              │
│                                                  │
│         Nginx Reverse Proxy (Unified Ports)       │
│    panel.yourdomain.com / monitor.yourdomain.com  │
└─────────────────────────────────────────────────┘
```

---

## 2. Installing CloudPanel

CloudPanel is a lightweight panel designed for high-performance applications, built on Nginx + MySQL/PostgreSQL + PHP/Node.js/Python.

### 2.1 One-Click Installation

```bash
# SSH into your VPS and run:
curl -sSf https://www.cloudpanel.io/sh/install.sh | bash
```

After installation, you'll see output similar to:

```
CloudPanel installed successfully!
Please visit: http://YOUR_IP:8080
Username: admin
Password: xxxxxxxxxx
```

### 2.2 Initial Configuration

1. Visit `http://your-ip:8080`, log in with default credentials
2. Change password immediately on first login
3. Configure SMTP server (for SSL certificate notifications and alerts)
4. Add your first site:

```
Site Type → Website → Enter Domain → Create
```

### 2.3 Key Configuration

| Setting | Recommended | Notes |
|---------|-------------|-------|
| PHP Version | 8.3 | Latest stable, best performance |
| Database | MySQL 8.0 / PostgreSQL 15 | Choose based on application needs |
| Nginx Cache | Enabled | Static resource caching |
| SSL Certificate | Let's Encrypt | Auto-renewal, free |
| Backup Policy | Weekly full + Daily incremental | Keep 4 weeks |

---

## 3. Deploying Uptime Kuma

Uptime Kuma is a good-looking open-source monitoring tool supporting multiple protocols and alert channels.

### 3.1 Docker Deployment

```bash
docker run -d \
  --name uptime-kuma \
  --restart unless-stopped \
  -p 3001:3001 \
  -v uptime-kuma-data:/app/data \
  louislam/uptime-kuma:1
```

### 3.2 Adding Monitors

After logging in, click **"Add New Monitor"**:

#### HTTP Monitor Example (Website Availability)

```
Display Name: My Blog
Type: HTTP(s)
URL: https://blog.yourdomain.com
Method: GET
Interval: 1 minute
Keywords: "Welcome"
```

#### TCP Monitor Example (Database Port)

```
Display Name: MySQL Primary
Type: TCP
Host: 127.0.0.1
Port: 3306
Interval: 30 seconds
```

#### Ping Monitor Example (Server Liveness)

```
Display Name: Edge Node
Type: Ping
Host: edge.yourdomain.com
Interval: 1 minute
```

### 3.3 Alert Configuration

Uptime Kuma supports rich alert channels:

| Channel | Setup |
|---------|-------|
| Telegram Bot | Create BotFather → Get Token → Fill in |
| WeChat Work | Webhook URL + Message template |
| DingTalk | Webhook + Signature verification |
| Email | SMTP configuration |
| Bark (iOS) | Bark Server URL |
| Pushover | API Key + User Key |

**Telegram Alert Setup:**

```
1. Open @BotFather, send /newbot
2. Get Bot Token: 123456789:ABCdefGHIjklMNOpqrsTUVwxyz
3. Search @userinfobot, get your Chat ID: 987654321
4. In Uptime Kuma alert settings:
   - Type: Telegram
   - Bot Token: 123456789:ABCdefGHIjklMNOpqrsTUVwxyz
   - Chat ID: 987654321
   - Message: Alert: {monitor.name} {status}
```

---

## 4. Deploying Gatus

Gatus is an automated service status engine. Define health check rules via YAML and get a beautiful dashboard out of the box.

### 4.1 Docker Compose Deployment

Create `docker-compose.yml`:

```yaml
version: "3"

services:
  gatus:
    image: twinproduction/gatus:v5
    container_name: gatus
    restart: unless-stopped
    ports:
      - "8081:8080"
    volumes:
      - ./config:/config
    command: ["-config", "/config/config.yaml"]
```

### 4.2 Health Check Configuration

Create `config/config.yaml`:

```yaml
storage:
  type: sqlite
  path: /config/sqlite.db
  cache: true

metrics: true

endpoints:
  # Blog website
  - name: Blog
    url: https://blog.yourdomain.com
    interval: 1m
    conditions:
      - "[STATUS] == 200"
      - "[BODY] contains 'Hello'"
      - "[RESPONSE TIME] < 500ms"

  # CloudPanel dashboard
  - name: CloudPanel
    url: http://localhost:8080
    conditions:
      - "[STATUS] == 200"

  # MySQL database
  - name: MySQL
    url: tcp://localhost:3306
    conditions:
      - "[CONNECTED] == true"

  # Redis cache
  - name: Redis
    url: tcp://localhost:6379
    conditions:
      - "[CONNECTED] == true"

  # API endpoint
  - name: User API
    url: https://api.yourdomain.com/health
    interval: 30s
    conditions:
      - "[STATUS] == 200"
      - "[BODY].status == 'ok'"
      - "[RESPONSE TIME] < 200ms"

  # DNS resolution
  - name: DNS Check
    url: dns://blog.yourdomain.com
    conditions:
      - "[IP] != null"

alerts:
  - type: telegram
    enabled: true
    bot-token: "123456789:ABCdefGHIjklMNOpqrsTUVwxyz"
    chat-id: "987654321"
    send-on-resolved: true
    failure-threshold: 3
    description: "Alert after 3 consecutive failures"
```

### 4.3 Gatus Key Advantages

| Feature | Description |
|---------|-------------|
| YAML-as-Config | All rules version-controlled, GitOps-friendly |
| Condition Expressions | Support status codes, response time, body matching |
| Multi-Protocol | HTTP, TCP, DNS, ICMP |
| Built-in Dashboard | `/api/v1/endpoints` returns JSON, `/` renders beautiful page |
| Alert Integration | Telegram, Slack, Discord, Webhooks |
| Historical Data | SQLite storage, query historical trends |

---

## 5. Nginx Unified Entry

Configure Nginx reverse proxy so all three tools are accessible via domains:

```nginx
# /etc/nginx/sites-available/devops-dashboard

server {
    listen 443 ssl http2;
    server_name panel.yourdomain.com;

    ssl_certificate     /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

    # CloudPanel
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

server {
    listen 443 ssl http2;
    server_name monitor.yourdomain.com;

    ssl_certificate     /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

    # Uptime Kuma
    location / {
        proxy_pass http://127.0.0.1:3001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}

server {
    listen 443 ssl http2;
    server_name status.yourdomain.com;

    ssl_certificate     /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

    # Gatus
    location / {
        proxy_pass http://127.0.0.1:8081;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

```bash
# Enable config and reload
ln -s /etc/nginx/sites-available/devops-dashboard /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
```

---

## 6. Automation & Advanced

### 6.1 Daily Health Report

Create a cron job to summarize daily status at 9 AM:

```bash
# crontab -e
0 9 * * * curl -s http://localhost:8081/api/v1/status | \
  jq '{total: (.endpoints | length), up: ([.endpoints[] | select(.statuses[0].success)] | length)}' | \
  curl -s -X POST "https://api.telegram.org/botBOT_TOKEN/sendMessage" \
  -d "chat_id=CHAT_ID" \
  -d "text=📊 Daily Health Report: \(.total) total services, \(.up) online" \
  -d "parse_mode=HTML"
```

### 6.2 Automatic Failure Recovery

Combine with CloudPanel's CLI tools for common auto-recovery:

```bash
#!/bin/bash
# /usr/local/bin/auto-restart-service.sh

SERVICE_NAME=$1
CONTAINER_ID=$(docker ps -q -f name=$SERVICE_NAME)

if [ -z "$CONTAINER_ID" ]; then
    echo "$(date): $SERVICE_NAME container stopped, restarting..." >> /var/log/service-restart.log
    docker start $CONTAINER_ID
    curl -s -X POST "https://api.telegram.org/botTOKEN/sendMessage" \
      -d "chat_id=CHAT_ID" \
      -d "text=⚠️ $SERVICE_NAME has been auto-restarted"
fi
```

### 6.3 Security Hardening

| Measure | Command/Config |
|---------|----------------|
| Basic Auth | Nginx `auth_basic` to protect monitoring entry |
| IP Whitelist | `allow your-ip; deny all;` |
| Force HTTPS | TLS enabled on all entries |
| Regular Updates | `docker pull louislam/uptime-kuma:1 && docker restart uptime-kuma` |
| Log Audit | `journalctl -u nginx -f` |

---

## 7. Resource Usage Estimate

| Component | CPU | RAM | Disk |
|-----------|-----|-----|------|
| CloudPanel | ~5% | ~150MB | ~200MB |
| Uptime Kuma | ~2% | ~80MB | ~50MB |
| Gatus | ~1% | ~30MB | ~20MB |
| **Total** | **~8%** | **~260MB** | **~270MB** |

For a 2-core 2GB VPS, this stack adds less than 15% overhead — easily manageable.

---

## 8. Summary

| Tool | Core Value |
|------|------------|
| **CloudPanel** | One-stop panel for site management, SSL, and databases |
| **Uptime Kuma** | Intuitive multi-protocol monitoring + multi-channel alerts |
| **Gatus** | YAML-driven health checks + beautiful status page |

Together they form a complete VPS operations loop:

```
CloudPanel (Management) → Uptime Kuma (Monitoring) → Gatus (Health Checks)
                                                        ↓
                                              Alerts (Telegram/DingTalk)
                                                        ↓
                                              Auto-Recovery (Scripts)
```

**Next Steps:**
1. Deploy CloudPanel first to manage your sites
2. Add Uptime Kuma to establish a monitoring baseline
3. Deploy Gatus for YAML-driven health checks
4. Configure alert channels for timely notifications

The beauty of this setup: **all data stays on your own VPS, no third-party SaaS dependency**. True self-hosting starts with taking control of your own operations dashboard.
