---
title: "Self-Hosted Monitoring with Uptime Kuma: Status Pages, Alerts & More"
description: "A complete guide to self-hosting Uptime Kuma on your VPS — monitor uptime, get alerts via Telegram/Email/Webhook, and build a professional status page in minutes. 100% free and open-source."
date: 2026-05-29T10:00:00+08:00
slug: "uptime-kuma-monitoring-status-page"
tags: ["Uptime Kuma", "monitoring", "status page", "Docker", "VPS", "alerts", "self-hosted", "devops"]
categories: ["Monitoring & Ops"]
image: /images/posts/uptime-kuma-monitoring-status-page/featured.png
draft: false
---

## Introduction

The worst thing about running a VPS? Finding out your service went down — from a user.

Traditional monitoring solutions are either expensive (Pingdom, Datadog) or heavyweight (Prometheus + Grafana stack). For solo developers and small teams, what you really need is something **lightweight, free, and instantly useful**.

Enter **Uptime Kuma** — an open-source, self-hosted monitoring tool that deploys in under 5 minutes, supports 90+ notification channels, and comes with a built-in status page that looks professional out of the box.

## What is Uptime Kuma?

Uptime Kuma is a Node.js-based open-source monitoring tool built around one principle: simplicity.

- 🐳 **One-line Docker deployment**
- 🔔 **90+ notification channels** (Telegram, Email, Discord, Slack, DingTalk, WeCom…)
- 📊 **Built-in status page** — no extra setup needed
- 🔍 **Multiple monitor types**: HTTP(S), TCP, Ping, DNS, SSL certificate, keyword detection, Docker container status
- 🔐 **Multi-user support** with role-based permissions
- 🌐 **IPv6 ready**

## 1. One-Click Docker Deployment

### Basic Setup

```bash
docker run -d \
  --name uptime-kuma \
  -p 3001:3001 \
  -v /data/uptime-kuma:/app/data \
  --restart unless-stopped \
  louislam/uptime-kuma:latest
```

Visit `http://your-vps-ip:3001`, create an admin account, and you're ready to go.

### Add HTTPS with Reverse Proxy

Exposing port 3001 directly is not recommended. Use Nginx or Caddy to add HTTPS.

**Caddy** (simplest — auto TLS via Let's Encrypt):

```caddyfile
status.yourdomain.com {
    reverse_proxy localhost:3001
}
```

**Nginx**:

```nginx
server {
    listen 443 ssl;
    server_name status.yourdomain.com;

    ssl_certificate /etc/ssl/certs/yourdomain.crt;
    ssl_certificate_key /etc/ssl/private/yourdomain.key;

    location / {
        proxy_pass http://127.0.0.1:3001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Docker Compose (Production-Ready)

```yaml
version: '3.8'

services:
  uptime-kuma:
    image: louislam/uptime-kuma:latest
    container_name: uptime-kuma
    volumes:
      - ./data:/app/data
    ports:
      - "3001:3001"
    restart: unless-stopped
    environment:
      - TZ=UTC
      - UPTIME_KUMA_PORT=3001
```

## 2. Adding Monitors

After logging in, click "Add Monitor" to see the full range of monitoring types:

### Available Monitor Types

| Type | Use Case | How It Works |
|------|----------|-------------|
| HTTP(s) | Web apps, APIs | Checks status code (200/403/500), supports custom headers |
| Ping | VPS, router | ICMP connectivity check |
| TCP | Database, SSH | Port reachability check |
| DNS | DNS resolvers | Validates DNS record resolution |
| SSL Certificate | HTTPS sites | Monitors cert expiry days, sends early warnings |
| Keyword | Content validation | Checks if page contains / lacks specific text |
| Docker | Container health | Monitors Docker containers on the same host |

### Practical Configuration Tips

**For web applications**:
- Monitor the main domain HTTPS (200 status check)
- Add a dedicated `/health` or `/api/v1/health` endpoint
- Set up SSL certificate monitoring (alert 30 days before expiry)

**For VPS infrastructure**:
- Ping every 1-2 minutes for basic connectivity
- Monitor SSH (port 22) availability
- Watch critical service ports (database 3306, Redis 6379)

## 3. Configuring Notifications

Uptime Kuma supports 90+ notification methods. Here are the most practical ones:

### Telegram Bot

1. Message `@BotFather` on Telegram to create a bot and get a token
2. Settings → Notifications → Add Telegram
3. Enter your Bot Token and Chat ID

```text
Bot Token: 123456789:ABCdefGHIjklmNOPqrstUVwxyz
Chat ID:   -1001234567890 (group) or 12345678 (personal)
```

### Email Notifications

Uptime Kuma has built-in email sending. You can use:
- SMTP (Gmail, Outlook, QQ Mail)
- Transactional email APIs (Resend, SendGrid, Mailgun)

### Webhook

Great for integrating with WeCom, Feishu, DingTalk, or custom automation:

```json
{
  "text": "⚠️ **{{NAME}}** is DOWN\nTime: {{DATE}}\nStatus: {{STATUS}}"
}
```

### Alert Strategy Settings

- **Retry count**: Only alert after N consecutive failures (avoid false positives from transient blips)
- **Alert interval**: Minimum time between alerts (prevents notification spam)
- **Recovery notification**: Auto-send when service comes back online

## 4. Building a Status Page

The built-in status page is one of Uptime Kuma's standout features.

### Creating a Status Page

Settings → Status Page → Add Status Page. You can customize:
- Page title and description
- Logo and favicon
- Theme color
- Which monitors to display
- Custom domain binding

### Organize by Category

Group services for better readability:

```
📊 Core Services
  ├── Main Website
  ├── API Service
  └── Database

🌐 Network
  ├── Primary Node Ping
  ├── Backup Node Ping
  └── DNS Resolution

🔒 SSL Certificates
  ├── Main Domain
  ├── API Domain
  └── CDN Domain
```

### Domain Binding & Access Control

Bind a custom domain (e.g., `status.yourdomain.com`) and optionally set a password to restrict access.

## 5. Advanced Usage

### Monitor Docker Containers on the Same Host

Mount the Docker socket to monitor containers directly:

```yaml
volumes:
  - /var/run/docker.sock:/var/run/docker.sock
```

Then select "Docker" as the monitor type and enter the container name.

### Distributed Monitoring

If you have VPS instances in multiple regions, you can:
1. Run Uptime Kuma on your main VPS
2. Use the "Push" monitor type to receive status reports from remote agents
3. Aggregate alerts from a central dashboard

This gives you geographically diverse monitoring without running multiple Kuma instances.

### REST API Integration

Uptime Kuma exposes a REST API for integration with other tools:

```bash
# Get all monitor statuses
curl -s https://status.yourdomain.com/api/status | jq .

# Get single monitor details
curl -s https://status.yourdomain.com/api/monitor/1 | jq .
```

## 6. Uptime Kuma vs. Alternatives

| Tool | Free | Self-Hosted | Status Page | Notification Channels | Setup Difficulty |
|------|------|-------------|-------------|----------------------|-----------------|
| **Uptime Kuma** | ✅ Fully free | ✅ | ✅ Built-in | 90+ | ⭐ Trivial |
| Prometheus + Grafana | ✅ | ✅ | ❌ Extra work | Moderate | 🔴 Complex |
| Pingdom | ❌ Paid | ❌ | ✅ | Limited | ⭐ Easy |
| Better Uptime | Limited free | ❌ | ✅ | Moderate | ⭐ Easy |
| StatusPage.io | ❌ Paid | ❌ | ✅ | Limited | ⭐ Easy |
| HetrixTools | Limited free | ❌ | ✅ | Moderate | ⭐ Easy |

**Verdict**: For individual developers and small teams, Uptime Kuma offers the best value. Completely free, self-hosted (your data stays with you), built-in status page, and extensive notification support.

## 7. Best Practices & Security

### Security Recommendations

1. **Always use HTTPS** via reverse proxy — never expose the dashboard over plain HTTP
2. **Keep the image updated**: `docker pull louislam/uptime-kuma:latest && docker restart uptime-kuma`
3. **Backup the data directory** (`/app/data`) — it contains all configurations and history
4. **Use a strong password** and enable two-factor authentication (2FA)

### Performance Notes

Uptime Kuma is extremely lightweight — monitoring 20-30 services uses only ~128MB RAM. Keep in mind:
- Don't set check intervals too aggressively (recommend ≥ 60 seconds for HTTP checks)
- Monitor bandwidth usage if checking many external sites

### Recommended Alert Workflow

```
Normal → 3 consecutive failures → Send alert → 1 success → Send recovery notification
         ↓                                      ↓
      Re-alert every 30 min              Stop notifications
```

This catches real issues quickly while avoiding false alarms and notification fatigue.

## Summary

Uptime Kuma is my top recommendation for VPS monitoring:

- **Fast setup**: One Docker command, 5 minutes to production
- **Complete coverage**: HTTP, TCP, Ping, SSL, Docker — everything you need
- **Rich notifications**: Telegram, Email, Webhook, and 90+ more
- **Beautiful status page**: Professional and presentable out of the box
- **Zero cost**: 100% free and open-source, full data sovereignty

If you run any user-facing services on your VPS, spending 10 minutes to deploy Uptime Kuma is infinitely better than finding out your server is down from a user complaint.

> **Further reading**: [VPS Monitoring with Prometheus & Grafana](/en/post/vps-monitoring-prometheus-grafana/) | [Docker Security Hardening Guide](/en/post/docker-security-hardening/)
