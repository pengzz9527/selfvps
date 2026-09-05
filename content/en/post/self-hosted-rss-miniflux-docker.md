---
title: "Self-Hosted RSS Reader: Build a Lightweight Subscription Platform with Miniflux + Docker"
description: "Take back control of your information feed. Deploy Miniflux on your VPS with Docker, subscribe to 15+ source types, access from any device, and reclaim your time from algorithm-driven content consumption."
date: 2026-09-05T08:00:00+08:00
slug: "self-hosted-rss-miniflux-docker"
tags: ["RSS", "Miniflux", "Docker", "Self-hosting", "Information Aggregation", "Privacy", "Productivity"]
categories: ["Self-hosted Apps"]
image: "/images/posts/self-hosted-rss-miniflux-docker/featured.png"
draft: false
---

## Why Self-Host an RSS Reader?

Do you ever open social media just to check a few things, only to lose half an hour to an endless scroll? Algorithms feed you content they think you'll like, but they decide what you see — not you.

**RSS (Really Simple Syndication)** is the original web syndication protocol. It lets you **actively choose** what to read, instead of being passively fed recommendations. The core value of a self-hosted RSS reader:

- **Information sovereignty**: See only what you follow — no algorithm manipulating your feed
- **Privacy protection**: No tracking of your reading habits, no selling to advertisers
- **Cross-platform sync**: Access from phone, computer, tablet — everything synced
- **Free forever**: Deploy once, use indefinitely, no subscription fees

## Solution Comparison

| Solution | Setup Difficulty | Feature Richness | Resource Usage | Best For |
|------|---------|-----------|---------|---------|
| Miniflux | ⭐⭐ Easy | ⭐⭐⭐ Moderate | ⭐ Minimal | Simplicity & efficiency |
| FreshRSS | ⭐⭐⭐ Medium | ⭐⭐⭐⭐ Rich | ⭐⭐ Moderate | Advanced features |
| Tiny Tiny RSS | ⭐⭐⭐ Medium | ⭐⭐⭐⭐ Rich | ⭐⭐ Moderate | Long-time users |
| Feedly (SaaS) | ⭐ One-click | ⭐⭐⭐⭐⭐ Full | ❌ Third-party | Avoid server maintenance |

**Miniflux** is a lightweight RSS reader written in Go. It supports PostgreSQL or SQLite, has a complete API, and works with all major clients. For individual VPS users, it's the best choice.

## Step 1: Prepare Your Server

Ensure your VPS meets these requirements:

```bash
# Check if Docker is installed
docker --version
docker-compose --version

# Install if needed
curl -fsSL https://get.docker.com | sh
```

Debian 12 or Ubuntu 22.04+ recommended. As little as 512MB RAM is sufficient.

## Step 2: Deploy Miniflux with Docker Compose

Create the project directory and configuration:

```bash
mkdir -p ~/miniflux && cd ~/miniflux
```

Create `docker-compose.yml`:

```yaml
services:
  miniflux:
    image: miniflux/miniflux:v30
    container_name: miniflux
    restart: unless-stopped
    ports:
      - "8080:8080"
    environment:
      # Database configuration (SQLite is simplest)
      DATABASE_URL: postgres://miniflux:CHANGE-ME@db:5432/miniflux?sslmode=disable
      DATABASE_DRIVER: postgres
      RUN_MIGRATIONS: 1
      CREATE_ADMIN: 1
      ADMIN_USERNAME: admin
      ADMIN_PASSWORD: YourStrongPassword123!
      # Timezone
      USER_TIMEZONE: Asia/Shanghai
      # Refresh interval (minutes)
      REFRESH_FREQUENCY: 30
      # Max requests per second (prevent bans)
      FETCHER_REQUESTS_PER_SECOND: 1
      FETCHER_BURST_SIZE: 5
    depends_on:
      db:
        condition: service_healthy
    networks:
      - miniflux-net

  db:
    image: postgres:16-alpine
    container_name: miniflux-db
    restart: unless-stopped
    volumes:
      - pgdata:/var/lib/postgresql/data
    environment:
      POSTGRES_USER: miniflux
      POSTGRES_PASSWORD: CHANGE-ME
      POSTGRES_DB: miniflux
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U miniflux -d miniflux"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - miniflux-net

volumes:
  pgdata:

networks:
  miniflux-net:
```

Start the services:

```bash
docker-compose up -d
```

After a few seconds, visit `http://YOUR_VPS_IP:8080` to see the Miniflux interface.

## Step 3: Configure Nginx Reverse Proxy (Recommended)

For production, a domain + HTTPS is strongly recommended:

```nginx
server {
    listen 80;
    server_name rss.yourdomain.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name rss.yourdomain.com;

    ssl_certificate     /etc/letsencrypt/live/rss.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/rss.yourdomain.com/privkey.pem;

    location / {
        proxy_pass         http://127.0.0.1:8080;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
    }
}
```

Use Certbot for free SSL certificates:

```bash
apt install certbot python3-certbot-nginx -y
certbot --nginx -d rss.yourdomain.com
```

## Step 4: Add Subscription Sources

Miniflux supports many source formats:

| Format | Example | Description |
|------|------|------|
| RSS 2.0 | https://example.com/feed | Most common |
| Atom | https://example.com/atom | Blog standard |
| JSON Feed | https://example.com/feed.json | Modern format |
| Twitter/X | @username | Follow specific users |
| YouTube | UCxxx (channel ID) | Video updates |
| Reddit | r/linux | Subreddit feeds |
| Hacker News | hackernews | Tech news |
| GitHub Releases | github/releases | Software update alerts |

Click **Add Feeds** in the Miniflux UI and paste URLs. You can also bulk-import OPML files.

## Step 5: Multi-User & Permissions

Miniflux supports a multi-user system, ideal for team collaboration:

```bash
# Create a regular user via API
curl -X POST http://localhost:8080/users \
  -H "Content-Type: application/json" \
  -H "X-Auth-Token: YOUR_ADMIN_TOKEN" \
  -d '{"username":"user1","password":"password123","role":"user"}'
```

Role permissions:

| Role | Permissions |
|------|------|
| admin | Manage all users and settings |
| user | Manage own subscriptions, cannot see others' data |
| restricted | Read-only, cannot add/delete sources |

## Step 6: Mobile Access

Miniflux provides a complete **JSON API**, compatible with all major RSS clients:

- **iOS**: Reeder, Unread, Feed Wrangler
- **Android**: FeedMe, Readably, Bright
- **macOS**: NetNewsWire, Feedy
- **Cross-platform**: Thunderbird

To connect Reeder, select **Miniflux** as the provider and enter your domain, username, and password.

## Step 7: Automation & Backups

### Scheduled Database Backup

```bash
# Add to crontab
0 3 * * * docker exec miniflux-db pg_dump miniflux -U miniflux | gzip > /backup/miniflux-$(date +\%Y\%m\%d).sql.gz
```

### Auto-update with Watchtower

```bash
docker run -d \
  --name watchtower \
  -v /var/run/docker.sock:/var/run/docker.sock \
  containrrr/watchtower \
  --cleanup --interval 3600 \
  miniflux
```

## Cost Analysis

Self-hosting Miniflux costs virtually nothing:

| Item | Cost |
|------|------|
| VPS (minimum spec) | $3-5/month |
| Domain | $5/year |
| SSL Certificate | Free (Let's Encrypt) |
| **Total** | **≈ $15/year** |

Compared to Feedly Premium ($10/year/device) or Unread ($18/year), the self-hosted approach has **zero marginal cost** after deployment.

## FAQ

**Q: Too many sources, refreshing is slow?**

A: Adjust `REFRESH_FREQUENCY` and `FETCHER_REQUESTS_PER_SECOND`. Limit requests per source to avoid rate limits. Set infrequent sources to refresh every 120 minutes.

**Q: How do I migrate from another RSS reader?**

A: Supports OPML import/export — migrating from any RSS reader takes one click.

**Q: How to get mobile push notifications?**

A: Miniflux doesn't include push natively. Combine with ntfy.sh or Pushover for new article notifications.

## Summary

Self-hosting an RSS reader is one of the most effective ways to combat information anxiety. Miniflux, with its minimal design, low resource usage, and complete API, is the ideal choice for individual VPS users. Spend one hour deploying it, and enjoy permanent information sovereignty.

Start today — subscribe to what truly matters, and take back control from the algorithms.
