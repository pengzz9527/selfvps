---
title: "Dokku Zero-Config PaaS Deployment Guide: Build Your Own Heroku on a VPS"
description: "Complete guide to deploying Dokku on a VPS — a Docker-based mini PaaS platform that lets you deploy apps with a single git push, automatic SSL, and domain management for just ~200MB RAM"
date: 2026-06-10T10:00:00+08:00
lastmod: 2026-06-10T10:00:00+08:00
slug: "dokku-vps-paas-deployment"
tags: ["Dokku", "PaaS", "Docker", "VPS Deployment", "Self-hosted", "Heroku Alternative", "CI/CD"]
categories: ["Self-Hosted Platform"]
draft: false
image: /images/posts/dokku-vps-paas-deployment/featured.png
---

## Why Dokku?

If you've ever deployed an application on [Heroku](https://www.heroku.com/), you've experienced the magic of "just `git push heroku main` to deploy." But Heroku's free tier has been discontinued, and even their cheapest paid plan starts at $5/month per app. For individual developers and small teams, this adds up quickly.

[Dokku](https://dokku.com/) is a **Docker-powered mini PaaS** that runs on any Linux VPS, giving you almost the same deployment experience as Heroku — completely free and fully under your control.

### Dokku vs Heroku vs Coolify

| Feature | Dokku | Heroku | Coolify |
|---------|-------|--------|---------|
| Deploy Method | `git push` | `git push` | Web UI / API |
| RAM Usage | ~200MB | N/A | ~1GB+ |
| Learning Curve | Moderate | Easy | Easy |
| Free | ✅ Open source | ❌ Paid | ✅ Open source |
| Plugin System | Bash plugins | Buildpacks | Pre-built templates |
| Best For | Technical users | Non-technical users | Team management |

If you have some Linux experience and want a **lightweight, fast, and fully controllable** self-hosted PaaS solution, Dokku is currently the best choice.

---

## Prerequisites

### Server Requirements

- **OS**: Ubuntu 22.04 / 24.04 (recommended) or Debian 12
- **CPU**: 1 core or more
- **RAM**: 1GB minimum (2GB recommended)
- **Storage**: 20GB SSD or more
- **Domain**: A domain pointing to your VPS IP (e.g., `app.yourdomain.com`)

> 💡 **Cost-saving tip**: If you already have a VPS, Dokku uses very little resources — the core process only consumes about 200MB of RAM. You can share it with Nginx, Cloudflare Tunnel, and other services.

### DNS Configuration

Before proceeding, make sure your domain resolves to your VPS public IP:

```bash
# Add wildcard DNS record (optional but recommended)
# Add in Cloudflare or your DNS provider:
*.yourdomain.com  →  VPS_IP  (A record)
yourdomain.com    →  VPS_IP  (A record)
```

A wildcard DNS record lets you assign a unique subdomain to each app without manually configuring DNS.

---

## Installing Dokku

### One-Click Install Script

Dokku provides an official one-line install script — the easiest way to get started:

```bash
# SSH into your VPS
ssh root@your_vps_ip

# Set the hostname (important!)
hostnamectl set-hostname dokku.yourdomain.com

# Run the official install script
curl -sSL https://dokku.com/install.sh | bash
```

The installation will automatically:

1. Install Docker (if not already installed)
2. Download and configure Dokku
3. Set up SSH keys
4. Create the initial user

After installation, you'll see output like:

```
=====> Dokku version: 0.32.13
=====> Dokku is enabled
=====> Instance dokku installed
```

### Verify the Installation

```bash
# Check Dokku status
dokku doctor

# Check Dokku version
dokku version

# List installed plugins
dokku plugins
```

---

## Configuring Nginx and SSL

### Default Nginx Configuration

Dokku comes with an Nginx container as a reverse proxy. It auto-generates Nginx configs when you first deploy an app.

```bash
# View current Nginx config
dokku nginx:show-default-config
```

### Enable HTTPS (Let's Encrypt)

Dokku has a built-in Let's Encrypt plugin for automatic SSL certificate issuance and renewal:

```bash
# Install the letsencrypt plugin
dokku plugins-install

# Set email address (for Let's Encrypt notifications)
dokku config:set --global DOKKU_LETSENCRYPT_EMAIL=admin@yourdomain.com

# Enable auto SSL
dokku letsencrypt:auto-reenable
```

When you deploy an app, Dokku will automatically request an SSL certificate for your domain.

### Configure Global Nginx Parameters

```bash
# Set max upload file size (for file upload apps)
dokku nginx:show-default-config | \
  sed 's/client_max_body_size 1m;/client_max_body_size 100m;/' | \
  dokku nginx:set-default-config

# Reload Nginx
dokku nginx:reload
```

---

## Deploying Your First App

### Method 1: Git Push Deployment (Recommended)

This is the closest experience to Heroku:

```bash
# On your local machine
git clone https://github.com/dokku/sample-app.git
cd sample-app

# Add the dokku remote
git remote add dokku dokku@your_vps_ip:myapp

# Deploy!
git push dokku main
```

That's it. Dokku will:

1. Detect the app type (Node.js, Python, Go, Ruby, etc.)
2. Build the app (using Buildpacks or Dockerfile)
3. Start the container
4. Assign a subdomain `myapp.yourdomain.com`
5. Automatically request an SSL certificate

### Method 2: Using a Dockerfile

For custom Dockerfiles:

```dockerfile
# Example Dockerfile
FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production
COPY . .
EXPOSE 3000
CMD ["node", "index.js"]
```

```bash
# Create the app on the VPS
dokku apps:create myapp

# Bind the domain
dokku domains:add myapp myapp.yourdomain.com

# Enable SSL
dokku letsencrypt myapp

# Deploy
git push dokku main
```

### Method 3: Using Docker Compose

Dokku supports multi-container apps via a `dokku.yml` file:

```yaml
# dokku.yml
release:
  cmd:
    - node dist/src/main.js

run:
  web:
    cmd:
      - node dist/src/main.js
```

```bash
# Deploy via git push
git push dokku main
```

---

## Database Management

Dokku's most powerful feature is its **plugin system**. You can manage databases as easily as Heroku:

### PostgreSQL

```bash
# Install the postgres plugin
dokku plugin:install https://github.com/dokku/dokku-postgres.git

# Create a database instance
dokku postgres:create mydb

# Link to your app
dokku postgres:link mydb myapp

# View connection info
dokku postgres:info mydb
```

After linking, Dokku automatically injects the database connection as an environment variable:

```
DATABASE_URL=postgres://dokku:random_password@dokku-postgres-mydb:5432/mydb
```

### Redis

```bash
# Install the redis plugin
dokku plugin:install https://github.com/dokku/dokku-redis.git

# Create a Redis instance
dokku redis:create mycache

# Link to your app
dokku redis:link mycache myapp
```

### MySQL / MongoDB

```bash
# MySQL
dokku plugin:install https://github.com/dokku/dokku-mysql.git
dokku mysql:create mydb
dokku mysql:link mydb myapp

# MongoDB
dokku plugin:install https://github.com/dokku/dokku-mongodb.git
dokku mongodb:create mydb
dokku mongodb:link mydb myapp
```

### Database Backups

```bash
# PostgreSQL backup
dokku postgres:backup-save mydb > backup.sql

# Restore
dokku postgres:backup-restore mydb < backup.sql
```

---

## Advanced Configuration

### Environment Variables

```bash
# Set a single environment variable
dokku config:set myapp NODE_ENV=production

# Set multiple variables
dokku config:set myapp API_KEY=xxx SECRET_KEY=yyy REDIS_URL=redis://...

# View all environment variables
dokku config myapp

# Remove an environment variable
dokku config:unset myapp API_KEY

# Bulk import from file
dokku config:import myapp .env
```

### Port Mapping

Dokku uses internal ports by default. To customize external ports:

```bash
# View current port bindings
dokku ports:show myapp

# Set port mapping
dokku ports:set myapp http:80:3000 https:443:3000
```

### Resource Limits

Prevent any single app from consuming all server resources:

```bash
# Limit CPU
dokku resource:limit myapp cpus 0.5

# Limit memory
dokku resource:limit myapp memory 512m

# View resource limits
dokku resource:info myapp
```

### Logs

```bash
# Real-time app logs
dokku logs myapp -t

# Last 100 lines
dokku logs myapp --tail=100

# Export logs to file
dokku logs myapp > app.log
```

### Health Checks

```bash
# Set HTTP health check
dokku probes:set myapp health http://localhost:3000/health

# Check health status
dokku probes:status myapp
```

---

## CI/CD Integration

### GitHub Actions Example

```yaml
# .github/workflows/deploy.yml
name: Deploy to Dokku

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Deploy to Dokku
        uses: dokku/github-action@v2
        with:
          host: your_vps_ip
          hostname: dokku.yourdomain.com
          identity: ${{ secrets.SSH_PRIVATE_KEY }}
          app: myapp
```

### GitLab CI Example

```yaml
# .gitlab-ci.yml
deploy:
  stage: deploy
  script:
    - ssh-keyscan your_vps_ip >> ~/.ssh/known_hosts
    - git push dokku@your_vps_ip:myapp HEAD:main
  only:
    - main
```

---

## Performance Optimization

### Enable Gzip Compression

```bash
# Edit global Nginx config
dokku nginx:show-default-config | \
  sed '/gzip_types/a\    gzip_comp_level 6;' | \
  dokku nginx:set-default-config

dokku nginx:reload
```

### Enable HTTP/2

```bash
# Enable HTTP/2 in Nginx config
dokku nginx:show-default-config | \
  sed 's/listen 443 ssl;/listen 443 ssl http2;/' | \
  dokku nginx:set-default-config

dokku nginx:reload
```

### Container Resource Optimization

```bash
# Set reasonable resource limits
dokku resource:limit myapp memory 1g
dokku resource:limit myapp cpus 1.0

# Set graceful shutdown
dokku config:set myapp DOKKU_APP_RESTORE=1
```

### Cache Optimization

```bash
# Enable build cache for Node.js apps
dokku buildpacks:set myapp cache true

# Set cache headers for static files
dokku nginx:show-default-config | \
  sed '/location \/static/a\    expires 30d;\n    add_header Cache-Control "public, immutable";' | \
  dokku nginx:set-default-config

dokku nginx:reload
```

---

## Backup and Migration

### Full Backup

```bash
# Backup all app configurations
dokku apps:list > apps.txt
dokku domains:list > domains.txt

# Backup each app's config
for app in $(dokku apps:list); do
  dokku config --shell $app | sed 's/^export //' > configs/$app.env
done

# Backup databases
dokku postgres:backup-save mydb > backups/mydb-$(date +%Y%m%d).sql

# Backup Dokku itself
tar czf dokku-backup-$(date +%Y%m%d).tar.gz \
  /var/lib/dokku \
  /etc/dokku \
  /home/dokku
```

### Migrate to a New Server

```bash
# Install Dokku on the new server
curl -sSL https://dokku.com/install.sh | bash

# Restore SSH keys
scp /path/to/dokku.pub root@new_server:/home/dokku/.ssh/authorized_keys

# Restore app configurations
for env_file in configs/*.env; do
  app=$(basename $env_file .env)
  dokku apps:create $app
  dokku config:import $app $env_file
done

# Restore databases
dokku postgres:restore mydb < backups/mydb-20260610.sql
```

---

## Troubleshooting

### Issue 1: Deployment Fails, Build Errors

```bash
# View detailed build logs
dokku logs myapp --tail=200

# Check Docker images
docker images | grep myapp

# Test manual build
cd /tmp
git clone your_repo
dokku build myapp .
```

### Issue 2: SSL Certificate Failed to Issue

```bash
# Check Let's Encrypt plugin status
dokku letsencrypt myapp

# Manually request certificate
dokku letsencrypt myapp

# View Let's Encrypt logs
tail -f /var/log/letsencrypt/letsencrypt.log
```

Ensure:
- Domain resolves correctly to VPS IP
- Ports 80 and 443 are not occupied by other services
- Firewall allows HTTP/HTTPS traffic

### Issue 3: App Starts and Immediately Crashes

```bash
# View crash logs
dokku logs myapp --tail=50

# Check port binding
dokku ports:show myapp

# Enter container for debugging
dokku enter myapp /bin/bash
```

### Issue 4: Disk Space Running Low

```bash
# Clean unused Docker resources
dokku docker-options:add app extra "--rm-volumes=unused"
docker system prune -a --volumes

# Clean old images
dokku ps:cleanup myapp
```

---

## Cost Analysis

### Cost Comparison with Heroku

Assuming you deploy 3 apps, each needing 512MB RAM:

| Platform | Monthly Cost | Notes |
|----------|-------------|-------|
| Heroku | ~$75 | 3 × $25/month |
| Dokku (VPS) | $5-10 | Cost of one 1GB VPS |
| **Savings** | **~$65/month** | **$780+/year saved** |

### Recommended VPS Configurations

| Scale | Configuration | Est. Monthly | Apps Deployable |
|-------|--------------|-------------|-----------------|
| Personal | 1C1G | $5-6 | 2-3 |
| Small Team | 2C2G | $10-12 | 5-8 |
| Medium | 4C4G | $20-25 | 15-20 |

---

## Summary

Dokku is an excellent choice for building your own PaaS on a VPS:

- ✅ **Minimal deployment**: A single `git push` to deploy
- ✅ **Automatic SSL**: Let's Encrypt integration, auto-renewal
- ✅ **Rich plugins**: PostgreSQL, Redis, MongoDB — one-click install
- ✅ **Resource-friendly**: Core usage only ~200MB RAM
- ✅ **Completely free**: Open source, no limits
- ✅ **Fully controllable**: Complete ownership of your data and infrastructure

For developers familiar with Docker and Linux, Dokku offers the best self-hosted PaaS experience. It's not as bloated as Coolify, and not as bare-bones as raw Docker — it sits perfectly in the middle, providing just the right level of abstraction.

---

## Resources

- [Dokku Official Documentation](https://dokku.com/getting-started/installation/)
- [Dokku Plugin Repository](https://github.com/dokku)
- [Dokku GitHub Repository](https://github.com/dokku/dokku)
- [Buildpacks Documentation](https://buildpacks.io/)
- [Let's Encrypt Documentation](https://letsencrypt.org/)
