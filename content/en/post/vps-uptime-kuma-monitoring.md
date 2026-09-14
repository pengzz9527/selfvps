---
title: "Self-Hosted Uptime Monitoring with Uptime Kuma: Zero-Cost HTTPS & Multi-Channel Alerts"
description: "Ditch UptimeRobot's free-tier limits. Deploy Uptime Kuma on your VPS for unlimited, 10-second-interval monitoring with Telegram, Discord, email, and 15+ alert channels — all fully self-hosted and free."
date: 2026-09-14T10:00:00+08:00
lastmod: 2026-09-14T10:00:00+08:00
slug: "vps-uptime-kuma-monitoring"
image: /images/posts/vps-uptime-kuma-monitoring/featured-en.png
tags: ["VPS", "Uptime Kuma", "Monitoring", "Alerting", "Docker", "Self-Hosted", "Zero-Cost", "DevOps"]
categories: ["Monitoring & Ops"]
aliases: [/en/post/vps-uptime-kuma-monitoring/]
---

## Why You Need Uptime Kuma

You're running a website, an API, a database, or internal services — but **how do you know they're still alive?**

Third-party monitoring services like UptimeRobot (free tier) have significant limitations:
- Maximum 50 monitors, checked every 5 minutes
- Limited alert channels, advanced features are paid
- Data stored on someone else's servers — zero privacy
- Minimal customization for your workflow

**Uptime Kuma** is the ultimate alternative — completely free, self-hosted, beautifully designed, and powerfully feature-rich. It puts your monitoring infrastructure entirely in your control, at zero cost, with unlimited scalability.

---

## Feature Comparison

| Feature | Uptime Kuma | UptimeRobot (Free) | Paid Monitoring Services |
|---------|-------------|---------------------|-------------------------|
| Monitor Count | **Unlimited** | 50 | Per-plan |
| Check Interval | **Every 10 seconds** | 5 minutes | 1 minute minimum |
| Deployment | Self-hosted | Cloud SaaS | Cloud SaaS |
| Alert Channels | **15+** | 3 | Multiple |
| Data Ownership | **Fully private** | Third-party | Third-party |
| Cost | **$0** | $0 (limited) | $10-50/month |

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────┐
│                  Uptime Kuma (Your VPS)                       │
│                                                              │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────┐  │
│  │  Scheduled   │───▶│  Status     │───▶│   Alert Rules   │  │
│  │  Probes      │    │  Engine     │    │  (Telegram/     │  │
│  │  (every 10s) │    │  (UP/DOWN)  │    │   Discord/      │  │
│  │              │    │             │    │   Email/        │  │
│  │  • HTTP/S    │    │             │    │   WeChat/...   │  │
│  │  • DNS check │    │             │    │                 │  │
│  │  • Ping      │    │             │    │                 │  │
│  │  • TCP port  │    │             │    │                 │  │
│  │  • Keyword   │    │             │    │                 │  │
│  │  • Push      │    │             │    │                 │  │
│  └─────────────┘    └──────┬──────┘    └─────────────────┘  │
│                             │                               │
│                     ┌───────▼───────┐                       │
│                     │  PostgreSQL    │                       │
│                     │  (history data)│                       │
│                     └───────────────┘                       │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              Web Dashboard :3001                     │    │
│  │         Real-time Status • History Charts • Timeline │    │
│  └─────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────┘
```

---

## Step 1: One-Command Docker Deployment

Create a `docker-compose.yml`:

```yaml
services:
  uptime-kuma:
    image: louislam/uptime-kuma:1
    container_name: uptime-kuma
    restart: unless-stopped
    ports:
      - "3001:3001"
    volumes:
      - ./uptime-kuma-data:/app/data
    environment:
      - TZ=Asia/Shanghai
```

Start the service:

```bash
mkdir -p ./uptime-kuma-data
docker compose up -d
```

Visit `http://your-vps-ip:3001`. You'll see a clean, modern interface. No login required initially — the first setup will guide you through creating an admin account.

---

## Step 2: Nginx Reverse Proxy + HTTPS

While Uptime Kuma works over plain HTTP, HTTPS is strongly recommended — not just for security, but because some notification channels (like mobile push) require a secure origin.

Assuming you have a domain like `monitor.yourdomain.com`:

```nginx
server {
    listen 443 ssl http2;
    server_name monitor.yourdomain.com;

    ssl_certificate     /etc/letsencrypt/live/monitor.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/monitor.yourdomain.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:3001;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket support (required for Kuma's real-time push)
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}

server {
    listen 80;
    server_name monitor.yourdomain.com;
    return 301 https://$host$request_uri;
}
```

Get a free SSL certificate with Certbot:

```bash
certbot --nginx -d monitor.yourdomain.com
```

---

## Step 3: Add Monitor Tasks

Uptime Kuma supports **15+ monitor types** covering virtually every scenario:

### 3.1 HTTP/HTTPS Monitor

The most common type — checks if a website is reachable:

1. Click **"Add New Uptime"**
2. Type: **HTTP(s)**
3. URL: `https://yourwebsite.com`
4. Alert interval: **5 minutes** (avoid spam during a single outage)
5. Enable **"Allow Sticky Status"** — same incident sends only one alert

**Pro tip: Keyword detection**
If your homepage contains specific text (like a site title), enable keyword checking. Even if HTTP 200 is returned, if the page content doesn't include the keyword, it triggers an alert — this prevents "false alive" situations where a server responds but serves broken content.

### 3.2 Ping Monitor

Check if a server is online:

```
Type: Ping
Target: your-vps-ip or example.com
Packet size: 64 bytes
Count: 3
```

### 3.3 DNS Monitor

Ensure domain resolution is working:

```
Type: DNS
Domain: yourdomain.com
DNS Server: 8.8.8.8 (optional)
Expected Record Type: A
Expected Value: your-server-IP
```

### 3.4 Port Monitor

Check if a TCP/UDP port is open:

```
Type: Port
Host: your-service.internal
Port: 6379 (Redis)
Protocol: TCP
```

### 3.5 Push Monitor (Passive Mode)

This is Uptime Kuma's most powerful feature — **no polling required**. The service checks in on its own:

1. Create a Push-type monitor
2. Get a unique URL: `https://monitor.yourdomain.com/api/push/xxxxx`
3. Call this URL from your application code after each critical operation

```python
import urllib.request

def notify_uptime():
    urllib.request.urlopen(
        "https://monitor.yourdomain.com/api/push/your-push-key?status=up"
    )
```

This is ideal for **short-lived tasks** (cron jobs, batch processing) — the task sends a push when it completes, and if no push arrives within the timeout window, it's flagged as failed.

---

## Step 4: Configure Multi-Channel Alerts

Uptime Kuma has built-in support for numerous alert channels. Here are the most commonly used configurations:

### 4.1 Telegram Alerts

1. Go to **Settings → Alert Settings**
2. Add **Telegram** alert
3. Enter Bot Token (from @BotFather)
4. Enter Chat ID (send `/getids` to @userinfobot)

Telegram offers fast delivery and high reach — it's the top choice for both individuals and teams.

### 4.2 Discord Webhook

Perfect for team shared monitoring channels:

```
Webhook URL: https://discord.com/api/webhooks/xxx/xxx
Message format supports Markdown
```

### 4.3 WeChat Work / DingTalk

Uptime Kuma supports custom webhooks — adapt the JSON format for WeChat Work or DingTalk:

```json
{
  "msgtype": "markdown",
  "markdown": {
    "content": "⚠️ Service Alert\nService: example.com\nStatus: DOWN\nTime: {{currentTime}}"
  }
}
```

### 4.4 Email Alerts

Straightforward SMTP configuration — suitable for non-urgent scenarios:

```
SMTP Server: smtp.gmail.com:587
Encryption: STARTTLS
From: your-account@gmail.com
To: admin@yourdomain.com
```

---

## Step 5: Configure Quiet Hours

You don't need alerts at 3 AM for non-critical services. Uptime Kuma has built-in **Downtime windows**:

```
Settings → Downtime
Time range: 00:00 - 07:00 (daily)
Effect: Outages during this window won't trigger alerts
```

Combine this with "Sticky Status" to avoid late-night alert fatigue.

---

## Advanced: Aggregate Multiple Monitors

If you have multiple VPS instances or projects, use Nginx to reverse-proxy them under one domain:

```nginx
# Main monitoring dashboard
location / {
    proxy_pass http://127.0.0.1:3001;
}

# API health check sub-path (same instance)
location /api/health {
    proxy_pass http://127.0.0.1:3001/api/health;
}
```

Or deploy separate Kuma instances per project (different ports) and expose them via Cloudflare Tunnel:

```yaml
# cloudflared tunnel config
tunnel: your-tunnel-id
credentials-file: /etc/cloudflared/creds.json

ingress:
  - hostname: monitor-project1.example.com
    service: http://localhost:3001
  - hostname: monitor-project2.example.com
    service: http://localhost:3002
  - service: http_error:404
```

---

## Resource Consumption

Uptime Kuma is extremely lightweight:

| Metric | Value |
|--------|-------|
| Memory | ~150MB (with PostgreSQL) |
| CPU | < 5% (near 0% idle) |
| Disk | ~50MB (default data) |
| Per-monitor overhead | Negligible |

On a 1GB RAM VPS, you can monitor **hundreds of services** without any performance concerns.

---

## When to Use What

| Scenario | Recommended Approach |
|----------|---------------------|
| Personal website uptime | Uptime Kuma (single instance) |
| Multi-project team | Multiple instances + Cloudflare Tunnel |
| Already running Prometheus | Uptime Kuma (complements HTTP layer) |
| Minimal setup | One Ping + one HTTP monitor |
| Compliance (data stays private) | Fully self-hosted Uptime Kuma |

---

## Conclusion

Uptime Kuma is an **essential tool** for any VPS operator — it delivers core monitoring capabilities that rival commercial platforms, using minimal resources, with zero ongoing cost. Most importantly, your monitoring data never leaves your infrastructure.

From zero deployment to your first alert takes less than **15 minutes**. Start today and keep your services visibly online, always.
