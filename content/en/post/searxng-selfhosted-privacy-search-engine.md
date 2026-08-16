---
title: "Self-Hosted SearXNG: Your Private Search Engine, No Tracking"
description: "Deploy SearXNG on your VPS to aggregate 70+ search engines without tracking, no data storage, and full privacy control. Docker one-command deployment, HTTPS ready."
date: 2026-08-16T10:00:00+08:00
slug: "searxng-selfhosted-privacy-search-engine"
tags: ["SearXNG", "search engine", "privacy", "self-hosted", "Docker", "VPS", "meta search"]
categories: ["Search & Privacy"]
image: /images/posts/searxng-selfhosted-privacy-search-engine/featured.png
draft: false
---

## Introduction

Every search you make is being tracked.

Google records everything: your queries, click patterns, time spent, location. DuckDuckGo claims privacy, but its results still depend on third-party engines. When you need truly **no-leak search**, the only option is — **host your own search engine**.

SearXNG exists for exactly this purpose. It's an open-source, self-hosted metasearch engine that aggregates results from 70+ major search engines, doesn't record user data or store search history, supports one-click Docker deployment, and gets you running in 15 minutes.

## What is SearXNG?

SearXNG is the community continuation of the original SearX project (now discontinued). Key features:

- 🔍 **70+ search engine aggregation**: Google, Bing, DuckDuckGo, Baidu, Wikipedia, GitHub, and more
- 🔒 **Zero tracking**: No IP logging, no search history, no user profiling
- 🌐 **Multilingual support**: Friendly Chinese interface, supports multi-language search
- 📱 **Responsive design**: Works on mobile, tablet, and desktop
- 🛡️ **Anti-tracking protection**: Automatically obfuscates request headers to avoid search engine blocks
- 🔧 **Highly customizable**: Plugin system, result sorting, engine preference configuration
- 🐳 **One-click Docker deployment**: Up and running in 5 minutes

## 1. Quick Docker Deployment

SearXNG's official recommendation is Docker deployment — the simplest approach:

### Basic Deployment

```bash
docker run -d \
  --name searxng \
  -p 8080:8080 \
  -v /data/searxng:/etc/searxng \
  --restart unless-stopped \
  searxng/searxng:latest
```

After deployment, visit `http://your-vps-ip:8080` in your browser.

### Docker Compose (Production-Ready)

```yaml
# docker-compose.yml
version: '3.8'

services:
  searxng:
    image: searxng/searxng:latest
    container_name: searxng
    ports:
      - "8080:8080"
    volumes:
      - ./searxng-settings:/etc/searxng
    environment:
      - SEARXNG_BASE_URL=http://localhost:8080/
      - TZ=Asia/Shanghai
    restart: unless-stopped
    mem_limit: 512m
    cpus: 1.0
```

```bash
mkdir -p ./searxng
docker compose up -d
```

## 2. Reverse Proxy + HTTPS

Exposing SearXNG to the public internet requires HTTPS. Caddy (auto TLS) or Nginx is recommended.

### Caddy Configuration (Simplest)

```caddyfile
search.yourdomain.com {
    reverse_proxy localhost:8080
}
```

One line does it all — Caddy auto-renews Let's Encrypt certificates.

### Nginx Configuration

```nginx
server {
    listen 443 ssl http2;
    server_name search.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

    # Security headers
    add_header X-Content-Type-Options nosniff;
    add_header X-Frame-Options SAMEORIGIN;
    add_header Referrer-Policy no-referrer;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
        proxy_request_buffering off;
    }
}
```

## 3. Core Configuration

SearXNG's config file lives at `/etc/searxng/settings.yml`, mounted via Docker volume.

### 1. Basic Settings

```yaml
# settings.yml
general:
  instance_name: "My Private Search"
  contact_url: false
  debug: false

search:
  safe_search: 0        # 0=off, 1=moderate, 2=strict
  autocomplete: "google"
  default_lang: "auto"
  formats:
    - html
    - json

server:
  port: 8080
  bind_address: "0.0.0.0"
  secret_key: "your-random-secret-key-here"  # Replace with a random string
  limiter: false
  image_proxy: true   # Proxy images to protect privacy
```

### 2. Search Engine Preferences

```yaml
engines:
  - name: google
    disabled: false
    weight: 3

  - name: bing
    disabled: false
    weight: 2

  - name: baidu
    disabled: false
    weight: 1

  - name: duckduckgo
    disabled: false
    weight: 2

  - name: wikipedia
    disabled: false
    weight: 1

  # Disable engines you don't need
  - name: amazon
    disabled: true
```

### 3. Enable JSON API (for integrations)

SearXNG provides a RESTful JSON API that can be consumed by other applications:

```bash
# Test search
curl -s "https://search.yourdomain.com/search?q=VPS+recommendation&format=json" | jq .
```

### 4. Configure Plugins

SearXNG supports a rich plugin system. Useful plugins:

```yaml
plugins:
  - plugin_name: 'Hostnames plugin'
  - plugin_name: 'Tracker URL remover'    # Strip tracking params from result URLs
  - plugin_name: 'Tor check plugin'
  - plugin_name: 'Self Open Results'
  - plugin_name: 'Ahmia blacklist'        # Dark web blacklist filtering
```

The `Tracker URL remover` plugin is essential — it automatically strips UTM parameters and tracking IDs from result links, preventing target sites from tracking your referral.

## 4. Advanced Features

### 1. Search Categories

SearXNG supports multiple search categories with quick-access UI:

| Category | Description |
|----------|-------------|
| **General** | Web search (Google, Bing, etc.) |
| **Images** | Image search |
| **Videos** | Video search |
| **News** | News search |
| **Music** | Music search |
| **IT** | Tech/programming (GitHub, Stack Overflow) |
| **Science** | Academic papers |
| **Files** | File search |

### 2. Sorting and Filtering

After each search you can:
- Sort by **relevance** or **date**
- Switch **language** and **region** (e.g., zh-CN, en-US)
- Enable **Safe Search** to filter inappropriate content
- Adjust **results per page** (default: 30)

### 3. Set as Browser Default Search Engine

**Chrome/Edge**: Install the "Search by SearXNG" extension, then set it as default in browser settings.

**Firefox**: Settings → Search → Search Engines → Add SearXNG custom engine:
```
URL: https://search.yourdomain.com/search?q=%s
```

### 4. RSS Feed for Search Results

SearXNG supports RSS output — subscribe to search results in your feed reader:

```
https://search.yourdomain.com/search?q=keyword&format=rss
```

## 5. SearXNG vs Other Search Solutions

| Tool | Free | Self-Hosted | Privacy | Chinese Support | Setup Difficulty |
|------|------|-------------|---------|-----------------|------------------|
| **SearXNG** | ✅ | ✅ | ✅ Fully anonymous | ✅ | ⭐ Minimal |
| Google | ❌ | ❌ | ❌ Full tracking | ✅ | N/A |
| DuckDuckGo | ✅ | ❌ | ✅ Good | ✅ | N/A |
| Bing | ❌ | ❌ | ❌ Microsoft tracking | ✅ | N/A |
| Presearch | ✅ | ❌ | ⚠️ Token required | ✅ | N/A |
| Mojeek | ✅ | ❌ | ✅ | ⚠️ Weak | N/A |

**Verdict**: If you want **absolute search privacy** without relying on any third party, SearXNG is the only correct choice. A self-hosted instance means your search behavior belongs solely to you.

## 6. Security Hardening & Best Practices

### 1. Access Restriction

If only for home/team use, add authentication:

```nginx
auth_basic "Private Search";
auth_basic_user_file /etc/nginx/.htpasswd;
```

### 2. Performance Optimization

- Set `results_limit: 50` to cap max results per query
- Enable `cache_limit: 1 day` to cache search results and reduce redundant requests
- Reduce enabled engines for faster response times

### 3. Automated Container Updates

```bash
# Add to crontab, update weekly
0 3 * * 0 docker pull searxng/searxng:latest && docker restart searxng
```

### 4. Backup Configuration

```bash
tar czf searxng-config-backup-$(date +%Y%m%d).tar.gz ./searxng/
```

## 7. Alternative Tools

If SearXNG isn't your style, these alternatives are worth exploring:

| Tool | Features | Language |
|------|----------|----------|
| **SearXNG** | Most features, rich plugins, active community | Python |
| **Whoogle** | Minimal Google mirror, single binary | Go |
| **Lug** | Academic search focused | Python |
| **Yandex Search** | Russian engine, better privacy policy | — |

Whoogle is notably lighter (single binary file), ideal for very resource-constrained VPS instances.

## Summary

SearXNG is one of the most worthwhile privacy tools to deploy on a VPS:

- **Minimal deployment**: One Docker command, running in 15 minutes
- **Powerful search**: Aggregates 70+ engines, results rival Google
- **Total privacy**: Zero tracking, zero logging, zero profiling
- **Free & open-source**: MIT license, fully autonomous

In an era where data is currency, owning your own search engine is the most basic act of digital self-defense.

> **Related**: [Cloudflare Tunnel: Zero-Config Intranet Access Guide](/en/post/cloudflare-tunnel-zero-config-guide/) | [VPS Security Hardening: 2026 Production Configuration Manual](/en/post/vps-security-hardening-2026/)
