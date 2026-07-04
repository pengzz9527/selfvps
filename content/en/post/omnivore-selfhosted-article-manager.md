---
title: "Self-Host Omnivore on Your VPS: Build Your Personal Article Manager & Highlighting System"
description: "Omnivore is an open-source Read-it-later tool with full-text search, highlighting, and AI summaries. Learn how to deploy it on your VPS via Docker and ditch Pocket and Instapaper subscription fees."
date: 2026-07-04T10:00:00+08:00
lastmod: 2026-07-04T10:00:00+08:00
slug: "omnivore-selfhosted-article-manager"
tags: ["Omnivore", "self-hosted", "Read-it-later", "Docker", "full-text search", "AI summaries", "note management"]
categories: ["Self-Hosted Tools"]
draft: false
image: "/images/posts/omnivore-selfhosted-article-manager/featured-en.png"
---

## 📖 Why You Need Omnivore

In this information-overloaded era, we encounter countless articles daily that we want to read but don't have time for immediately. Services like Pocket and Instapaper are handy, but they share a critical flaw: **your data doesn't belong to you**. If the service shuts down or raises prices, you lose years of saved articles and annotations.

**Omnivore** was built to solve exactly this problem. It's a fully open-source Read-it-later solution offering:

- 🔍 **Full-text search** — Quickly find content across all your saved articles
- 🎨 **Highlighting & annotations** — Mark important passages like taking notes
- 🤖 **AI summaries** — Built-in AI features for one-click article summarization
- 📱 **Multi-platform sync** — Web, iOS, Android, and Chrome extension
- 🏠 **Fully self-hosted** — Your data stays in your control

---

## 🏗 System Architecture

Omnivore consists of several core components:

```
┌─────────────────────────────────────────────┐
│              Omnivore Architecture            │
├──────────┬──────────┬───────────┬────────────┤
│  Frontend │  API     │  Worker   │  Storage   │
│  (Next.js)│ (GraphQL)│ (Queue)   │            │
├──────────┼──────────┼───────────┼────────────┤
│  Web/Mobile/App          │  PostgreSQL + S3  │
└─────────────────────────────────────────────┘
```

| Component | Role | Minimum Specs |
|-----------|------|---------------|
| **API Server** | Handles GraphQL requests | 1 vCPU, 512MB RAM |
| **Worker** | Async article processing | 1 vCPU, 512MB RAM |
| **PostgreSQL** | Stores users, highlights, tags | 1 vCPU, 512MB RAM |
| **S3-Compatible Storage** | Stores article snapshots & images | Any S3 service |

---

## 🚀 One-Click Deployment (Docker Compose)

This is the simplest deployment method, suitable for most individual users.

### Step 1: Create Project Directory

```bash
mkdir -p ~/omnivore && cd ~/omnivore
```

### Step 2: Create `.env` File

```bash
cat > .env << 'EOF'
# PostgreSQL Configuration
POSTGRES_USER=omnivore
POSTGRES_PASSWORD=CHANGE_ME_SECURE_PASSWORD
POSTGRES_DB=omnivore
POSTGRES_HOST=db
POSTGRES_PORT=5432

# S3 Storage Configuration (using MinIO locally)
S3_ENDPOINT=http://minio:9000
S3_REGION=us-east-1
S3_BUCKET=omnivore
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin

# Omnivore API Secret (for authentication)
HASH_SALT=CHANGE_ME_SECURE_HASH_SALT
API_SECRET=CHANGE_ME_SECURE_API_SECRET

# Frontend Configuration
NEXTAUTH_URL=http://localhost:3000
NEXT_PUBLIC_APP_PROTOCOL=http
NEXT_PUBLIC_APP_HOST=localhost
NEXT_PUBLIC_APP_PORT=3000

# MinIO Console (optional, for storage management)
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin
EOF
```

> ⚠️ **Important**: Replace all `CHANGE_ME_*` placeholders with random strong passwords.

### Step 3: Create `docker-compose.yml`

```yaml
version: '3.8'

services:
  # PostgreSQL database
  db:
    image: postgres:16-alpine
    container_name: omnivore-db
    restart: unless-stopped
    env_file: .env
    volumes:
      - pg_data:/var/lib/postgresql/data
    networks:
      - omnivore

  # MinIO object storage
  minio:
    image: minio/minio:latest
    container_name: omnivore-minio
    restart: unless-stopped
    command: server /data --console-address ":9001"
    env_file: .env
    volumes:
      - minio_data:/data
    networks:
      - omnivore
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/live"]
      interval: 30s
      timeout: 10s
      retries: 3

  # Omnivore API Server
  api:
    image: ghcr.io/omnivore-app/omnivore/api:latest
    container_name: omnivore-api
    restart: unless-stopped
    env_file: .env
    ports:
      - "4000:4000"
    depends_on:
      db:
        condition: service_started
      minio:
        condition: service_healthy
    networks:
      - omnivore

  # Omnivore Worker (async task processing)
  worker:
    image: ghcr.io/omnivore-app/omnivore/worker:latest
    container_name: omnivore-worker
    restart: unless-stopped
    env_file: .env
    depends_on:
      db:
        condition: service_started
      minio:
        condition: service_healthy
    networks:
      - omnivore

  # Omnivore Next.js Frontend
  frontend:
    image: ghcr.io/omnivore-app/omnivore/frontend:latest
    container_name: omnivore-frontend
    restart: unless-stopped
    env_file: .env
    ports:
      - "3000:3000"
    depends_on:
      - api
    networks:
      - omnivore

volumes:
  pg_data:
  minio_data:

networks:
  omnivore:
    driver: bridge
```

### Step 4: Start Services

```bash
docker compose up -d
```

Wait a few minutes for all services to start, then visit `http://your-vps-ip:3000` to see the Omnivore interface.

---

## 🌐 Configure Reverse Proxy (Recommended)

Accessing via raw ports is neither secure nor convenient. Use **Caddy** or **Nginx** for HTTPS reverse proxying.

### Using Caddy (Simplest)

```caddy
omnivore.yourdomain.com {
    reverse_proxy localhost:3000
    encode gzip
    
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Content-Type-Options "nosniff"
    }
}
```

### Using Nginx

```nginx
server {
    listen 443 ssl http2;
    server_name omnivore.yourdomain.com;

    ssl_certificate     /etc/letsencrypt/live/omnivore.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/omnivore.yourdomain.com/privkey.pem;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;

    # WebSocket support (Chrome extension needs this)
    map $http_upgrade $connection_upgrade {
        default upgrade;
        ''      close;
    }

    location / {
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        client_max_body_size 50m;
    }
}
```

---

## 📲 Client Configuration

After deployment, configure the API endpoints in various clients:

### Chrome Extension

1. Install [Omnivore Chrome Extension](https://chromewebstore.google.com/detail/omnivore)
2. Click the extension icon → Settings
3. Change API URL to `http://your-vps-ip:4000/api`
4. Change App URL to `http://your-vps-ip:3000`

### iOS / Android

1. Install Omnivore from App Store / Play Store
2. Select "Self-hosted" option during login
3. Enter your VPS address and API key

### API Usage

```bash
# Fetch article list
curl -X POST http://localhost:4000/api \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_SECRET" \
  -d '{"query": "{ viewer { highlights { id title } } }"}'
```

---

## 💡 Core Features Deep Dive

### 1. Full-Text Search

Omnivore uses Elasticsearch-style full-text indexing. Saved articles are automatically parsed and indexed:

```graphql
{
  search(first: 20, query: "machine learning tutorial") {
    edges {
      node {
        title
        slug
        description
      }
    }
  }
}
```

### 2. Highlighting & Annotations

Highlight text and add notes on any saved article, just like reading a PDF:

- **Yellow highlight** — Key content
- **Green highlight** — Useful references
- **Red highlight** — Action items
- **Notes** — Personal annotations

### 3. AI Summaries

Omnivore has built-in AI that generates one-click article summaries. For long articles, this helps you quickly decide if they're worth reading in full:

> 💡 **Money-saving tip**: Self-hosting means you can pair it with local Ollama for completely free AI summaries — no API costs whatsoever.

### 4. Tags & Folder Organization

Supports multi-level tags and folder organization to keep hundreds of articles neatly structured:

```
📁 Tech Articles
  ├── 🏷 AI/ML
  ├── 🏷 DevOps
  └── 🏷 Cybersecurity

📁 Design Inspiration
  ├── 🏷 UI/UX
  └── 🏷 Typography

📁 To Read
```

---

## 📊 Cost Comparison

| Solution | Monthly Cost | Data Storage | AI Features | Ads |
|----------|-------------|--------------|-------------|-----|
| **Omnivore Self-Hosted** | ~$4.15 (Hetzner) | Unlimited | Free (Ollama) | ❌ None |
| Pocket Premium | $4.99 | Limited | ❌ None | ❌ None |
| Instapaper Premium | $3.99 | Limited | ❌ None | ❌ None |
| Readwise Reader | $7.00 | Limited | ✅ Yes | ❌ None |

**Annual savings**: Compared to Readwise Reader ($84/year), self-hosting Omnivore saves **$79.80+ per year**, and your data remains entirely yours.

---

## 🔧 Advanced Configuration

### Use External PostgreSQL

If you already have PostgreSQL running on your VPS, reuse it directly:

```yaml
# Override .env
POSTGRES_HOST=your-existing-db-host
POSTGRES_PORT=5432
POSTGRES_USER=omnivore_user
POSTGRES_PASSWORD=secure_password
POSTGRES_DB=omnivore
```

### Use Remote S3 (AWS / Cloudflare R2)

Don't want to self-host MinIO? Use any S3-compatible service:

```bash
# Cloudflare R2 configuration example
S3_ENDPOINT=https://ACCOUNT_ID.r2.cloudflarestorage.com
S3_REGION=auto
S3_ACCESS_KEY=YOUR_R2_KEY
S3_SECRET_KEY=YOUR_R2_SECRET
S3_BUCKET=omnivore-articles
```

R2 advantage: **Zero egress fees**, perfect for storing article snapshots.

### Enable Email Saving

Configure SMTP to save articles by sending emails:

```bash
# Add to .env
SMTP_HOST=smtp.yourdomain.com
SMTP_PORT=587
SMTP_USER=noreply@yourdomain.com
SMTP_PASSWORD=your_smtp_password
EMAIL_SAVE_ADDRESS=saved@yourdomain.com
```

---

## 🛡️ Security Hardening

### 1. Firewall Rules

```bash
# Only expose necessary ports
ufw allow 22/tcp      # SSH
ufw allow 80/tcp      # HTTP (Let's Encrypt)
ufw allow 443/tcp     # HTTPS
ufw deny 3000/tcp     # Don't expose frontend directly
ufw deny 4000/tcp     # Don't expose API directly
ufw enable
```

### 2. Automated Backups

```bash
#!/bin/bash
# omnivore-backup.sh
BACKUP_DIR="/backups/omnivore/$(date +%Y%m%d)"
mkdir -p "$BACKUP_DIR"

# Backup PostgreSQL
docker exec omnivore-db pg_dump -U omnivore omnivore > "$BACKUP_DIR/db.sql"

# Backup MinIO data
docker run --rm -v omnivore_minio_data:/data -v "$BACKUP_DIR":/backup \
  alpine tar czf /backup/minio.tar.gz -C /data .

# Remove backups older than 30 days
find /backups/omnivore -maxdepth 1 -mtime +30 -exec rm -rf {} \;

echo "Backup completed: $BACKUP_DIR"
```

Add to crontab:

```bash
0 3 * * * /root/omnivore/omnivore-backup.sh
```

### 3. Enable OAuth (Optional)

Omnivore supports GitHub OAuth login to avoid password management:

```bash
# Add to .env
NEXTAUTH_SECRET=your-random-secret
GITHUB_ID=your-github-oauth-client-id
GITHUB_SECRET=your-github-oauth-client-secret
```

---

## ❓ FAQ

### Q: Can't save articles after deployment?

Check the Worker container logs:

```bash
docker logs omnivore-worker --tail 50
```

Common causes: S3 connection failure or MinIO not ready. Verify `S3_ENDPOINT` and credentials.

### Q: Memory usage is too high?

Omnivore needs approximately 1.5GB RAM minimum. If your VPS has limited memory:

1. Use external PostgreSQL (saves container memory)
2. Use remote S3 (like Cloudflare R2)
3. Limit Worker concurrency

### Q: Can I use only the web version without deploying the API?

No. Omnivore's frontend depends on the backend API for article saving, searching, and highlighting. The full stack is required.

### Q: How to connect mobile apps?

In the Omnivore iOS/Android app settings, select "Custom Server" and enter `https://omnivore.yourdomain.com` along with your API key.

---

## 🎯 Summary

Omnivore is one of the best self-hosted Read-it-later solutions available today. Its advantages:

1. **Fully open-source** — Transparent code, no vendor lock-in
2. **Feature-rich** — Full-text search, highlighting, AI summaries all included
3. **Low cost** — Runs on the cheapest VPS available
4. **Data ownership** — Your articles, annotations, and tags always belong to you

Instead of paying monthly subscriptions to Pocket or Readwise, spend **$4/month** on a VPS and permanently own your personal knowledge management system.

**Take action now**: Deploy Omnivore in 10 minutes and take back control of your reading life.

---

*Published on [SelfVPS Guide](https://selfvps.net). Share freely — knowledge wants to be free.*
