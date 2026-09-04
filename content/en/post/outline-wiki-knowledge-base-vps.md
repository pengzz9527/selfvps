---
title: "Self-Hosted Wiki & Knowledge Base on VPS: Complete Outline Deployment Guide"
description: "Build your team knowledge base with Outline — Markdown support, real-time collaboration, full-text search, SSO integration. Complete Docker Compose deployment guide from scratch to production, replacing Notion and Confluence."
date: 2026-09-04T10:00:00+08:00
lastmod: 2026-09-04T10:00:00+08:00
slug: "outline-wiki-knowledge-base-vps"
tags: ["Outline", "Wiki", "Knowledge Base", "Docker", "Self-Hosted", "Team Collaboration", "Documentation", "Nextcloud"]
categories: ["Deployment Guides"]
draft: false
image: /images/posts/outline-wiki-knowledge-base-vps/featured.png
aliases: [/en/post/outline-wiki-knowledge-base-vps/]
---

## Why Self-Host a Wiki?

In team collaboration-centric workflows, a knowledge base is the infrastructure for information flow. While there are mature products like Notion, Confluence, and GitBook on the market, each has significant pain points:

| Solution | Key Pain Points |
|----------|----------------|
| **Notion** | Data stored on third-party servers, difficult to self-host, slow access in China, limited free tier |
| **Confluence** | Atlassian ecosystem lock-in, expensive, complex deployment, requires Jira |
| **GitBook** | Free tier has document limits, enterprise pricing is high |
| **WordPress + Plugins** | Fragmented experience, weak collaboration features, high maintenance cost |

**Outline** is one of the most popular self-hosted Wiki solutions in recent years. Developed by a former Stack Overflow engineering team, it features a modern UI design, a smooth Markdown editing experience, powerful search capabilities, and flexible integration options. Most importantly, **all data stays entirely in your hands**.

### Outline Core Features

- **Markdown First**: Native Markdown support with an editor experience comparable to Notion
- **Real-time Collaboration**: Multiple users editing the same document simultaneously with visible cursors
- **Full-text Search**: Millisecond search powered by Typesense with Chinese tokenization support
- **Granular Permissions**: Space-based access control with team group support
- **SSO Integration**: Supports Google, GitHub, OIDC, LDAP, and other authentication methods
- **Complete API**: RESTful API + WebSocket for easy extension and customization
- **Export Options**: PDF, Markdown, HTML export formats supported
- **Custom Branding**: Support for custom brand colors and logos

## Requirements

Before starting, ensure your VPS meets these requirements:

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| **CPU** | 2 cores | 4 cores |
| **RAM** | 4GB | 8GB |
| **Disk** | 20GB SSD | 50GB+ NVMe |
| **Bandwidth** | 100Mbps | 500Mbps+ |
| **OS** | Ubuntu 22.04/24.04 LTS | Debian 12 / Ubuntu 24.04 |
| **Domain** | Recommended (for SSO callbacks) | `wiki.yourdomain.com` |

## Method 1: Docker Compose One-Click Deployment (Recommended)

### Step 1: Preparation

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker and Docker Compose
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
sudo apt install -y docker-compose-plugin

# Verify installation
docker --version
docker compose version
```

### Step 2: Create Project Directory

```bash
mkdir -p ~/outline-wiki/{data,postgres,data/redis}
cd ~/outline-wiki
```

### Step 3: Generate Secrets

```bash
# Generate SECRET_KEY_BASE (for encrypting sessions and tokens)
openssl rand -hex 64

# Generate JWT_SECRET (for signing JWT tokens)
openssl rand -hex 32

# Record the two values output above for later use
```

### Step 4: Create .env Configuration

```bash
cat > .env << 'EOF'
# ===== Outline Configuration =====
OUTLINE_URL=https://wiki.yourdomain.com
NODE_ENV=production

# ===== Database Configuration (PostgreSQL) =====
DB_HOST=postgres
DB_NAME=outline
DB_USER=outline
DB_PASS=your-strong-password-here
DB_PORT=5432

# ===== Redis Configuration =====
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASS=your-redis-password-here

# ===== Security Keys (replace with generated values) =====
SECRET_KEY_BASE=your-64-char-hex-key-here
JWT_SECRET=your-32-char-hex-key-here

# ===== File Storage Configuration =====
FILE_STORAGE=local
FILE_STORAGE_LOCAL_ROOT=/var/lib/outline/uploads

# ===== Search Configuration (Typesense) =====
SEARCH_PROVIDER=typesense
TYPESENSE_HOST=typesense
TYPESENSE_PORT=8108
TYPESENSE_PROTOCOL=http
TYPESENSE_API_KEY=your-typesense-api-key

# ===== Authentication Configuration (choose one) =====
# Google OAuth
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret

# Or GitHub OAuth
# GITHUB_CLIENT_ID=your-github-client-id
# GITHUB_CLIENT_SECRET=your-github-client-secret

# Or OIDC (universal SSO)
# OIDC_CLIENT_ID=your-oidc-client-id
# OIDC_CLIENT_SECRET=your-oidc-client-secret
# OIDC_ISSUER=https://your-identity-provider.com

# ===== Email Configuration (for password reset and notifications) =====
SMTP_HOST=smtp.yourdomain.com
SMTP_PORT=587
SMTP_SECURE=false
SMTP_USERNAME=noreply@yourdomain.com
SMTP_PASSWORD=your-smtp-password
SMTP_FROM_ADDRESS=noreply@yourdomain.com

# ===== Admin Email (used to create admin account on first launch) =====
ADMIN_EMAIL=admin@yourdomain.com
EOF
```

> **Note**: Replace `wiki.yourdomain.com` with your actual domain, and fill in real keys and authentication information.

### Step 5: Create docker-compose.yml

```bash
cat > docker-compose.yml << 'EOF'
version: '3.8'

services:
  # ===== Outline Main Application =====
  outline:
    image: outlinewiki/outline:latest
    container_name: outline
    restart: unless-stopped
    env_file:
      - .env
    environment:
      - OUTLINE_LOG_LEVEL=info
      - OUTLINE_RATE_LIMIT_WEBHOOKS=500:15m
      - OUTLINE_RATE_LIMIT_API=2000:1m
    volumes:
      - ./uploads:/var/lib/outline/uploads
    ports:
      - "3000:3000"
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_started
      typesense:
        condition: service_started
    networks:
      - outline-net

  # ===== PostgreSQL Database =====
  postgres:
    image: postgres:16-alpine
    container_name: outline-postgres
    restart: unless-stopped
    environment:
      - POSTGRES_DB=outline
      - POSTGRES_USER=outline
      - POSTGRES_PASSWORD=${DB_PASS}
    volumes:
      - postgres-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U outline -d outline"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - outline-net

  # ===== Redis Cache =====
  redis:
    image: redis:7-alpine
    container_name: outline-redis
    restart: unless-stopped
    command: redis-server --requirepass ${REDIS_PASS} --maxmemory 256mb --maxmemory-policy allkeys-lru
    volumes:
      - redis-data:/data
    networks:
      - outline-net

  # ===== Typesense Search Engine =====
  typesense:
    image: typesense/typesense:27.0.rc31
    container_name: outline-typesense
    restart: unless-stopped
    command: >
      ./typesense-server
      --data-dir /data
      --api-key=${TYPESENSE_API_KEY}
      --enable-cors
    volumes:
      - typesense-data:/data
    networks:
      - outline-net

volumes:
  postgres-data:
  redis-data:
  typesense-data:

networks:
  outline-net:
    driver: bridge
EOF
```

### Step 6: Start Services

```bash
# First launch (automatically runs database migrations)
docker compose up -d

# Watch startup logs
docker compose logs -f outline
```

On first launch, Outline will automatically create database tables and initialize configuration. You'll see output like this when ready:

```
outline    | info: Server is ready to accept connections! 🎉
```

### Step 7: Create Admin Account

Visit `http://your-VPS-IP:3000` and register the first admin account using the `ADMIN_EMAIL` configured in `.env`.

## Method 2: Nginx Reverse Proxy Configuration

For production, use Nginx as a reverse proxy with HTTPS and cache optimization.

### Step 1: Install Nginx and Certbot

```bash
sudo apt install -y nginx certbot python3-certbot-nginx
```

### Step 2: Get SSL Certificate

```bash
# Ensure your domain A record points to the VPS IP
sudo certbot certonly --nginx -d wiki.yourdomain.com
```

### Step 3: Create Nginx Configuration

```bash
sudo tee /etc/nginx/sites-available/outline << 'EOF'
server {
    listen 80;
    server_name wiki.yourdomain.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name wiki.yourdomain.com;

    # SSL Certificate
    ssl_certificate     /etc/letsencrypt/live/wiki.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/wiki.yourdomain.com/privkey.pem;
    ssl_trusted_certificate /etc/letsencrypt/live/wiki.yourdomain.com/chain.pem;

    # SSL Optimization
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 1d;
    ssl_session_tickets off;

    # Security Headers
    add_header X-Frame-Options SAMEORIGIN always;
    add_header X-Content-Type-Options nosniff always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy strict-origin-when-cross-origin always;

    # Upload file size limit
    client_max_body_size 100m;

    # WebSocket support
    map $http_upgrade $connection_upgrade {
        default upgrade;
        ''      close;
    }

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;

        # WebSocket proxy
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;

        # Real client info
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Timeout settings (WebSocket needs longer timeout)
        proxy_connect_timeout 7d;
        proxy_send_timeout 7d;
        proxy_read_timeout 7d;
    }

    # Static resource cache
    location ~* \.(jpg|jpeg|png|gif|ico|css|js|svg|woff2?)$ {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
}
EOF

# Enable site and restart Nginx
sudo ln -sf /etc/nginx/sites-available/outline /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

## Authentication Configuration

### Google OAuth Setup

1. Visit [Google Cloud Console](https://console.cloud.google.com/)
2. Create project → APIs & Services → Credentials
3. Create OAuth 2.0 Client ID
4. Add authorized redirect URL: `https://wiki.yourdomain.com/auth/google/callback`
5. Fill Client ID and Secret into `.env`

### GitHub OAuth Setup

1. Visit [GitHub Settings → Developer settings → OAuth Apps](https://github.com/settings/developers)
2. Create a new OAuth App
3. Set Authorization callback URL: `https://wiki.yourdomain.com/auth/github/callback`
4. Fill Client ID and Secret into `.env`

### OIDC (Universal SSO) Setup

Works with Keycloak, Auth0, Azure AD, and other OIDC-compatible identity providers:

```bash
# Add to .env
OIDC_CLIENT_ID=your-oidc-client-id
OIDC_CLIENT_SECRET=your-oidc-client-secret
OIDC_ISSUER=https://your-identity-provider.com/.well-known/openid-configuration
```

## Advanced Configuration

### Custom Branding and Theme

Outline supports branding customization via environment variables:

```bash
# Add to .env
BRANDING_LOGO_URL=https://wiki.yourdomain.com/assets/logo.png
BRANDING_COLOR=#6366f1
BRANDING_NAME=My Team Wiki
BRANDING_DESCRIPTION=Team internal knowledge management platform
```

### Adjust File Upload Limits

```bash
# Add to outline service environment in docker-compose.yml
- UPLOAD_MAX_FILE_SIZE=104857600  # 100MB
- ALLOWED_FILE_EXTENSIONS=jpg,png,gif,pdf,doc,docx,xls,xlsx,zip
```

### Enable LDAP Authentication

Outline supports LDAP through plugins or community versions:

```bash
# Configure in .env
LDAP_HOST=ldap://your-ldap-server
LDAP_PORT=389
LDAP_BIND_DN=cn=admin,dc=example,dc=com
LDAP_BIND_PASSWORD=your-ldap-password
LDAP_SEARCH_BASE=ou=users,dc=example,dc=com
LDAP_USER_FILTER=(uid=%{login})
```

### Configure Object Storage (S3 Compatible)

For production, use S3-compatible object storage instead of local storage:

```bash
# Modify in .env
FILE_STORAGE=s3
AWS_REGION=us-east-1
AWS_S3_BUCKET=outline-uploads
AWS_ACCESS_KEY_ID=your-aws-access-key
AWS_SECRET_ACCESS_KEY=your-aws-secret-key
AWS_S3_ENDPOINT=https://minio.yourdomain.com
```

### Scheduled Backup Strategy

```bash
# Create backup script ~/outline-wiki/backup.sh
#!/bin/bash
set -e

BACKUP_DIR="/backup/outline-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_DIR"

# Backup database
docker exec outline-postgres pg_dump -U outline outline > "$BACKUP_DIR/database.sql"

# Backup uploaded files
docker cp outline:/var/lib/outline/uploads "$BACKUP_DIR/uploads"

# Backup configuration files
cp .env "$BACKUP_DIR/env"
cp docker-compose.yml "$BACKUP_DIR/docker-compose.yml"

# Compress
tar czf "$BACKUP_DIR.tar.gz" "$BACKUP_DIR"
rm -rf "$BACKUP_DIR"

# Keep only last 7 days of backups
find /backup -name "outline-*.tar.gz" -mtime +7 -delete

echo "Backup completed: $BACKUP_DIR.tar.gz"
```

```bash
# Add to crontab (daily backup at 3 AM)
crontab -e
# Add: 0 3 * * * /root/outline-wiki/backup.sh
```

## Data Migration and Upgrades

### Upgrading Outline Version

```bash
cd ~/outline-wiki
docker compose pull
docker compose up -d
```

Outline's database migrations are automatic — no additional steps needed during upgrades.

### Migrating from Other Wiki Platforms

Outline supports importing from the following formats:

- **Markdown Files**: Batch upload `.md` files to a specified space
- **Notion Export**: Export as Markdown then batch import
- **Confluence Export**: Export as XML then convert to Markdown
- **GitBook Export**: Export ZIP then unpack and import

```bash
# Use Outline API for batch import
curl -X POST https://wiki.yourdomain.com/api/documents/import \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  -F "file=@document.md" \
  -F "parentId=DOCUMENT_ID"
```

## Troubleshooting

### Q1: Page Not Accessible After Startup

```bash
# Check container status
docker compose ps

# View Outline logs
docker compose logs outline

# Check port usage
sudo ss -tlnp | grep 3000
```

Common causes:
- PostgreSQL not ready yet (wait for healthcheck)
- Environment variable misconfiguration (check `.env`)
- Firewall blocking port 3000

### Q2: File Upload Fails

```bash
# Check uploads directory permissions
sudo chown -R 999:999 ~/outline-wiki/uploads

# Check disk space
df -h
```

### Q3: Search Function Not Working

```bash
# Check Typesense status
docker compose logs typesense

# Restart Typesense
docker compose restart typesense

# Rebuild search index
curl -X POST https://wiki.yourdomain.com/api/search/reindex \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"
```

### Q4: WebSocket Connection Unstable

Ensure the Nginx configuration includes WebSocket support (see above), and check proxy timeout settings.

### Q5: Chinese Search Accuracy Issues

Typesense doesn't support Chinese tokenization by default. Use a TypeScript configuration with Chinese support:

```bash
# Add to typesense service in docker-compose.yml
command: >
  ./typesense-server
  --data-dir /data
  --api-key=${TYPESENSE_API_KEY}
  --enable-cors
  --search-index-field-count=5000
```

## Performance Optimization

### 1. Optimize PostgreSQL Configuration

```bash
# Optimize in postgres container
# Mount custom config to /var/lib/postgresql/data/postgresql.conf
shared_buffers = 256MB          # Adjust based on available memory
effective_cache_size = 768MB
work_mem = 4MB
maintenance_work_mem = 64MB
max_connections = 100
```

### 2. Redis Memory Optimization

```bash
# maxmemory is set to 256MB, adjust as needed
# Using allkeys-lru strategy for automatic eviction of least-recently-used data
```

### 3. Enable Gzip Compression

Add to Nginx configuration:

```nginx
gzip on;
gzip_vary on;
gzip_proxied any;
gzip_comp_level 6;
gzip_types text/plain text/css text/xml application/json application/javascript application/rss+xml application/atom+xml image/svg+xml;
```

### 4. CDN for Static Resources

If your team is distributed across different regions, consider distributing uploaded attachments through a CDN.

## Summary

Outline is one of the best self-hosted Wiki solutions available today, perfectly combining modern UI design, powerful collaboration features, and complete data autonomy.

**Key Takeaways:**

1. **Simple Deployment**: Docker Compose one-click deployment, 5 services to complete setup
2. **Excellent UX**: Notion-like editing experience with smooth real-time collaboration
3. **Powerful Search**: Millisecond full-text search powered by Typesense
4. **Secure & Controllable**: All data stored on your own VPS
5. **Flexible Integration**: Supports multiple SSO authentication methods
6. **Highly Extensible**: Complete API for custom development

**Cost Estimation:**

| Item | Cost |
|------|------|
| VPS (4-core 8GB) | $20-40/month |
| Domain | $10-15/year |
| SSL Certificate | Free (Let's Encrypt) |
| **Total** | **~$30/month** |

Compared to Notion Business ($10/user/month) or Confluence ($8.75/user/month), self-hosted Outline breaks even when your team exceeds 5 people.

**Next Steps:**
- [ ] Prepare VPS and configure domain DNS
- [ ] Deploy Outline following this guide
- [ ] Configure SSO authentication
- [ ] Set up scheduled backup strategy
- [ ] Invite team members to start using
