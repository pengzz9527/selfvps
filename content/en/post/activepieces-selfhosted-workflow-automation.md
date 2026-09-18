---
title: "Self-Hosted ActivePieces Workflow Automation: Free Alternative to Make/Zapier, Save $600+/Year"
description: "Build visual workflow automation on your VPS with ActivePieces — zero-code, 200+ app integrations, unlimited executions, replacing Make ($19/mo+) and Zapier ($20/mo+) for $0/year."
date: 2026-09-18T10:00:00+08:00
lastmod: 2026-09-18T10:00:00+08:00
slug: "activepieces-selfhosted-workflow-automation"
image: /images/posts/activepieces-selfhosted-workflow-automation/featured-en.png
tags: ["ActivePieces", "Automation", "Workflow", "Make", "Zapier", "Docker", "Self-Hosted", "Zero-Cost", "Savings"]
categories: ["Tool Reviews", "Self-Hosted"]
aliases: [/en/post/activepieces-selfhosted-workflow-automation/]
---

## Why Self-Host Workflow Automation?

Do you have scenarios like this?

> When an email with an invoice arrives → auto-save to Google Drive → sync to Notion → notify in Slack?

Or more everyday tasks:

> A user signs up on your site → auto-send welcome email → create user profile → add to Mailchimp → log in CRM?

If you use **Zapier** or **Make** (formerly Integromat) for these, the free tiers have strict execution limits — Zapier free gives 100 tasks/month, Make free gives 1,000 operations/month. Once your usage grows, paid plans quickly reach **$19~$59/month**.

**ActivePieces** is the perfect alternative — **open-source, free, self-hosted, with unlimited executions**. The same workflows, running locally, data entirely in your hands, costing **$0/month**.

---

## ActivePieces vs Make vs Zapier: Cost Comparison

| Feature | ActivePieces (Self-Hosted) | Make (Standard) | Zapier (Professional) |
|---------|---------------------------|-----------------|----------------------|
| Monthly Cost | **$0** | $9/mo ($108/yr) | $29/mo ($348/yr) |
| Task Executions | **Unlimited** | 10,000/mo | 750,000/mo |
| Multi-Step Workflows | ✅ | ✅ | ✅ |
| Conditions/Loops | ✅ | ✅ | ✅ (paid) |
| Custom Code Blocks | ✅ JavaScript | ✅ JavaScript | ✅ Python/JS |
| 200+ App Integrations | ✅ | ✅ | ✅ |
| Data Privacy | **Fully private** | Third-party servers | Third-party servers |
| Webhook Triggers | ✅ | ✅ | ✅ |
| Scheduled Triggers | ✅ | ✅ | ✅ |
| Team Access Control | ✅ | ✅ | ✅ (paid) |
| API Access | ✅ | ✅ | ✅ (paid) |

**Annual savings: $108 ~ $348+** (just software costs, not counting the value of privacy and data control)

---

## Core Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│              Your VPS / Local Server                 │
│                                                     │
│  ┌──────────┐    ┌──────────────┐    ┌──────────┐  │
│  │  Nginx   │───▶│ ActivePieces │───▶│ PostgreSQL│  │
│  │  Reverse │    │   (Node.js)  │    │ (Storage) │  │
│  │  Proxy   │    │  :3000       │    └──────────┘  │
│  └────┬─────┘    └──────┬───────┘          ▲       │
│       │                 │                  │       │
│       ▼                 ▼                  │       │
│  ┌──────────┐    ┌──────────────┐         │       │
│  │  TLS     │    │   Redis      │─────────┘       │
│  │ (Cert)   │    │  (Queue)     │                 │
│  └──────────┘    └──────────────┘                 │
│                                                    │
│  ┌──────────────────────────────────────────┐     │
│  │        External Service Triggers & Callbacks    │
│  │  Gmail · Notion · Slack · Google Drive   │     │
│  │  GitHub · Telegram · Discord · HTTP      │     │
│  │  + 200+ more integrations                │     │
│  └──────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────┘
```

---

## Step 1: One-Click Docker Compose Deployment

The easiest deployment method — from 0 to running in 10 minutes.

### 1. Create Working Directory

```bash
mkdir -p ~/activepieces && cd ~/activepieces
```

### 2. Create docker-compose.yml

```yaml
services:
  activepieces:
    image: ghcr.io/activepieces/activepieces:latest
    restart: unless-stopped
    ports:
      - "5050:80"
    environment:
      AP_ENGINE_EXECUTABLE_PATH: "dist/main"
      AP_ENCRYPTION_KEY: "your-random-32-char-key-here"
      AP_JWT_SECRET: "your-random-jwt-secret"
      AP_FRONTEND_URL: "https://flows.yourdomain.com"
      AP_BACKEND_URL: "http://localhost:5050"
      AP_EXECUTION_MODE: "FULL"
      AP_REDIS_HOST: "redis"
      AP_POSTGRES_HOST: "postgres"
      AP_POSTGRES_PORT: "5432"
      AP_POSTGRES_DATABASE: "activepieces"
      AP_POSTGRES_USER: "postgres"
      AP_POSTGRES_PASSWORD: "your-strong-password"
      AP_TELEMETRY_ENABLED: "true"
    depends_on:
      redis:
        condition: service_healthy
      postgres:
        condition: service_healthy

  redis:
    image: redis:7-alpine
    restart: unless-stopped
    command: redis-server --appendonly yes
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  postgres:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_DB: activepieces
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: "your-strong-password"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  redis_data:
  postgres_data:
```

### 3. Start Services

```bash
docker compose up -d
```

### 4. Verify Deployment

```bash
# Check container status
docker compose ps

# View logs
docker compose logs -f activepieces
```

When you see `Application is ready!`, deployment is successful.

---

## Step 2: Configure Nginx Reverse Proxy + HTTPS

ActivePieces requires HTTPS to function properly (for OAuth callbacks and webhooks).

### Create Nginx Configuration

```nginx
server {
    listen 80;
    server_name flows.yourdomain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name flows.yourdomain.com;

    ssl_certificate     /etc/nginx/ssl/flows.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/nginx/ssl/flows.yourdomain.com/privkey.pem;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # Timeout settings (long polling required)
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;
    send_timeout 3600s;

    location / {
        proxy_pass http://127.0.0.1:5050;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # WebSocket support
    location /ws {
        proxy_pass http://127.0.0.1:5050;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }
}
```

### Get Free SSL Certificate with Certbot

```bash
# Install certbot
apt install certbot python3-certbot-nginx -y

# Request certificate
certbot certonly --standalone -d flows.yourdomain.com

# Create SSL directory and copy certificates
mkdir -p /etc/nginx/ssl/flows.yourdomain.com
cp /etc/letsencrypt/live/flows.yourdomain.com/fullchain.pem \
   /etc/nginx/ssl/flows.yourdomain.com/
cp /etc/letsencrypt/live/flows.yourdomain.com/privkey.pem \
   /etc/nginx/ssl/flows.yourdomain.com/
```

### Enable Site and Reload Nginx

```bash
ln -s /etc/nginx/sites-available/activepieces \
       /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
```

---

## Step 3: Create Your First Automation Workflow

### Scenario: Auto-Save Email Attachments to Google Drive

#### 1. Create Trigger

Login to `https://flows.yourdomain.com`, click **"New Piece"** → select **"Schedule"** trigger:

- **Type**: Polling mode
- **Frequency**: Check every 5 minutes
- **App**: Gmail

#### 2. Configure Gmail Trigger

```
Trigger conditions:
- New email in inbox
- Contains attachments
- From specific sender (optional)
```

#### 3. Add Action: Save to Google Drive

```
Action: Google Drive → Upload File
- Source: Gmail attachment
- Target folder: /AutoPieces/Email-Attachments
- File naming: {date}_{sender}_{filename}
```

#### 4. Add Second Action: Send Telegram Notification

```
Action: Telegram → Send Message
- Chat ID: Your Telegram Chat ID
- Message: 📎 New email attachment saved
  Filename: {{attachments.0.name}}
  Size: {{attachments.0.size}}
  Link: {{drive_link}}
```

#### 5. Save and Enable

Click **"Save & Turn On"** in the top right corner. The workflow starts running immediately.

---

## Advanced: Build a CI/CD Notification System

### Scenario: GitHub Push → Multi-Channel Notification

```
Trigger: GitHub Webhook (Push event)
    │
    ├─→ Action 1: Parse commit info
    │         （JavaScript code snippet）
    │
    ├─→ Action 2a: Send Telegram notification
    │
    ├─→ Action 2b: Send Slack message
    │
    └─→ Action 2c: Update Google Sheets record
```

### GitHub Webhook Configuration

1. In GitHub repo Settings → Webhooks → Add webhook
2. Payload URL: `https://flows.yourdomain.com/api/v1/hook/github`
3. Content type: `application/json`
4. Secret: Set a key for verification

### JavaScript Code Snippet Example

You can write JavaScript directly in ActivePieces to process data:

```javascript
// Parse GitHub push event
const push = params.body;
const repo = push.repository.full_name;
const branch = push.ref.replace('refs/heads/', '');
const commits = push.commits;

// Format output
const commitList = commits.map(c => 
  `• ${c.message.split('\n')[0].substring(0, 50)}`
).join('\n');

return {
  repo,
  branch,
  author: push.pusher.name,
  commitCount: commits.length,
  commits: commitList
};
```

---

## Cost Calculation: Self-Hosted vs SaaS

Assuming you need monthly:
- 500 task executions
- 3 multi-step workflows
- 5 app integrations

| Plan | Monthly | Annual | Notes |
|------|---------|--------|-------|
| **ActivePieces (Self-Hosted)** | **$0** | **$0** | Only VPS cost |
| Make (Standard) | $9 | $108 | 10K ops/mo |
| Make (Premium) | $29 | $348 | 100K ops/mo |
| Zapier (Professional) | $29 | $348 | 750K ops/mo |
| Zapier (Team) | $166 | $1,992 | 2000K ops/mo |

**Conclusion**: As long as your VPS has spare capacity, ActivePieces is free. Even if you pay for a lightweight VPS separately ($5/mo), it's still 80%+ cheaper than Make/Zapier — and you get unlimited executions + complete data privacy.

---

## FAQ

### Q: What's the difference between ActivePieces and n8n?

Both are excellent self-hosted workflow automation tools. Key differences:
- **ActivePieces**: Lighter weight, faster to get started, simpler UI, great for small-to-medium workflows
- **n8n**: More feature-rich, more nodes, better for complex enterprise scenarios
- **License**: ActivePieces uses MIT license (fully open), n8n uses Sustainable Use License

### Q: Do I need a domain?

**Recommended yes**, because many app OAuth callbacks require HTTPS domains. If only used internally, you can use IP + self-signed certificate, but you'll lose some integration capabilities.

### Q: Minimum VPS requirements?

- CPU: 1 vCPU
- RAM: **1GB** (2GB recommended)
- Disk: 10GB
- Network: Outbound internet access required (for calling external APIs)

### Q: How about data security?

All data (workflow configs, execution logs, auth tokens) is stored in your own database. Compared to SaaS solutions, you avoid:
- Data breach risks on third-party servers
- Workflow interruption due to provider downtime
- Pricing strategy changes by the provider

---

## Summary

ActivePieces is one of the most recommended solutions in the self-hosted workflow automation space:

- ✅ **Completely free**, no execution limits
- ✅ **One-click Docker deployment**, online in 10 minutes
- ✅ **200+ native app integrations**, visual drag-and-drop
- ✅ **JavaScript extensions** for custom needs
- ✅ **MIT open-source license**, customizable
- ✅ **Saves $100~$2000+/year** (depending on which SaaS you replace)

For anyone already running services on a VPS, deploying ActivePieces is nearly zero additional cost — your VPS already has spare capacity. Give it a try today!

---

*Published on [SelfVPS](https://selfvps.net/en/) — Your guide to self-hosting and cloud cost savings*
