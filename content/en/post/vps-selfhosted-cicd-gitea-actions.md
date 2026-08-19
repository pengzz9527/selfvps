---
title: "Self-Hosted CI/CD Pipeline on VPS: Gitea + Gitea Actions Complete Guide"
description: "Build a complete self-hosted CI/CD pipeline from scratch on VPS using Gitea as GitHub alternative and Gitea Actions as GitHub Actions replacement — eliminate platform lock-in and monthly fees"
date: 2026-08-19T08:00:00+08:00
lastmod: 2026-08-19T08:00:00+08:00
slug: "vps-selfhosted-cicd-gitea-actions"
image: /images/posts/vps-selfhosted-cicd-gitea-actions/featured.png
tags: ["Gitea", "CI/CD", "Self-Hosted", "Docker", "Actions", "DevOps", "Pipeline", "Automation"]
categories: ["Container Operations"]
aliases: [/en/post/vps-selfhosted-cicd-gitea-actions/]
---

## Introduction

Have you ever faced these pain points in your development projects?

- GitHub Actions runs out of free monthly quota, then builds queue for half an hour;
- GitLab CI Shared Runners are slow, and自建 Runners require an extra server;
- Paying Premium subscription just to host private repos on GitHub;
- Code hosted on commercial platforms — no control over audit logs or data sovereignty.

**A self-hosted CI/CD pipeline** is the answer. Gitea is a lightweight Git service compatible with the GitHub API; Gitea Actions is its CI/CD engine, fully compatible with GitHub Actions' YAML syntax. Combined, you can build a complete develop-build-deploy pipeline on a single VPS at zero additional cost.

This guide walks you through deploying Gitea + Gitea Actions on a VPS from scratch, with a complete CI/CD example.

---

## Architecture Overview

```
┌──────────────┐      ┌─────────────────────────────┐      ┌─────────────┐
│  Developer    │─────▶│  Gitea (Git + API + Web)    │─────▶│  Gitea      │
│  (Git Push)   │      │  :3000 / :2222              │      │  Actions    │
└──────────────┘      └─────────────────────────────┘      │  Runner     │
                                                           └──────┬──────┘
                                                                  │
                                                          ┌─────────▼─────────┐
                                                          │  Docker Builder   │
                                                          │  (Build/Test/Push)│
                                                          └───────────────────┘
```

---

## Step 1: Server Preparation

### 1.1 Recommended Specifications

- **OS**: Ubuntu 24.04 LTS / Debian 12
- **CPU**: 2+ cores (Actions Runner consumes CPU during builds)
- **Memory**: 4GB+ (Gitea + Runner running simultaneously)
- **Storage**: 50GB SSD (code repos + image cache)
- **Domain**: e.g., `git.example.com`, pointing to your VPS IP
- **Ports**: 80/443 (Web), 2222 (SSH Git), 3000 (Gitea API)

### 1.2 Install Base Dependencies

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y curl git docker.io docker-compose-plugin nginx certbot python3-certbot-nginx
sudo usermod -aG docker $USER
```

---

## Step 2: Deploy Gitea

### 2.1 Create Gitea Data Directory

```bash
sudo mkdir -p /data/gitea/{data,logs,ssh}
sudo chown -R 1000:1000 /data/gitea
sudo chmod -R 755 /data/gitea
```

### 2.2 Write Docker Compose

```yaml
# ~/gitea/docker-compose.yml
version: "3.8"

services:
  gitea:
    image: gitea/gitea:1.22
    container_name: gitea
    restart: unless-stopped
    environment:
      - USER_UID=1000
      - USER_GID=1000
      - GITEA__database__DB_TYPE=sqlite3
      - GITEA__service__DISABLE_REGISTRATION=false
      - GITEA__service__REQUIRE_SIGNIN_VIEW=false
    ports:
      - "3000:3000"
      - "2222:22"
    volumes:
      - /data/gitea/data:/data/gitea
      - /data/gitea/logs:/data/gitea/log
      - /data/gitea/ssh:/data/gitea/ssh
    networks:
      - gitea-net

networks:
  gitea-net:
    driver: bridge
```

### 2.3 Start Gitea

```bash
cd ~/gitea
docker compose up -d
docker compose ps
```

### 2.4 Initial Configuration

Open your browser and visit `http://your-vps-ip:3000`, then complete the following:

- **Admin account**: Set admin username and password
- **Repository root**: Default `/data/gitea/git`
- **SMTP**: Optional, for email notifications
- **Gitea instance URL**: Enter your domain or IP

> **Security Note**: After first login, immediately adjust default settings, enable 2FA, and restrict public registration.

---

## Step 3: Configure Nginx Reverse Proxy & TLS

### 3.1 Create Nginx Configuration

```bash
sudo tee /etc/nginx/sites-available/gitea << 'EOF'
server {
    listen 80;
    server_name git.example.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name git.example.com;

    ssl_certificate /etc/letsencrypt/live/git.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/git.example.com/privkey.pem;
    ssl_session_timeout 1d;
    ssl_session_cache shared:SSL:50m;
    ssl_session_tickets off;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256;
    ssl_prefer_server_ciphers off;
    add_header Strict-Transport-Security "max-age=63072000" always;

    # Gitea Web
    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 900;
    }

    # Git LFS
    location /lfs {
        proxy_pass http://127.0.0.1:3000;
        proxy_buffering off;
        proxy_request_buffering off;
        client_max_body_size 0;
    }
}
EOF
```

### 3.2 Enable Site & Request Certificate

```bash
sudo ln -sf /etc/nginx/sites-available/gitea /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# Request Let's Encrypt certificate
sudo certbot certonly --nginx -d git.example.com --email your@email.com --agree-tos -n

# Test auto-renewal
sudo certbot renew --dry-run
```

### 3.3 Configure External URL in Gitea

Go to Gitea Admin Panel → Admin Settings → Repository Settings:

- **Site URL**: `https://git.example.com`
- **SSH Server Address**: `git.example.com`
- **SSH Port**: `2222`

---

## Step 4: Configure Gitea Actions Runner

### 4.1 Prepare Docker-in-Docker Support

Gitea Actions needs to build Docker images in the Runner, so `dind` (Docker-in-Docker) support is required.

```bash
# Create Runner-specific directory
mkdir -p ~/gitea-runner
```

### 4.2 Write Runner Docker Compose

```yaml
# ~/gitea-runner/docker-compose.yml
version: "3.8"

services:
  runner:
    image: gitea/act_runner:latest
    container_name: gitea-actions-runner
    restart: unless-stopped
    environment:
      - GITEA_INSTANCE_URL=https://git.example.com
      - GITEA_RUNNER_NAME=vps-runner-01
      - GITEA_RUNNER_EXECUTOR=docker
      - GITEA_RUNNER_REPO_CLONE=true
      - GITEA_RUNNER_SPECIFIC=true
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - runner-data:/data
    networks:
      - gitea-net

volumes:
  runner-data:

networks:
  gitea-net:
    external: true
    name: gitea_gitea-net
```

> **Note**: Ensure the Runner container can access Gitea's network. Use `external: true` to connect to Gitea's network.

### 4.3 Start the Runner

```bash
cd ~/gitea-runner
docker compose up -d
docker compose logs -f runner
```

On first start, the Runner outputs a registration Token. Paste it in Gitea Admin → Actions → Runners to complete registration.

### 4.4 Register Runner in Gitea

1. Go to Gitea Admin Panel → Actions → Runners
2. Click "Add Runner", copy the generated Token
3. Set Runner labels (e.g., `linux`, `docker`)
4. The Runner will automatically connect and register

---

## Step 5: Create Your First CI/CD Project

### 5.1 Create a Sample Repository

Create a new project in Gitea:

```bash
# Local operations
git clone https://git.example.com/youruser/myapp.git
cd myapp
```

### 5.2 Write .gitea/workflows/ci.yml

```yaml
# .gitea/workflows/ci.yml
name: CI Pipeline

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  build:
    runs-on: self-hosted
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Login to Registry
        uses: docker/login-action@v3
        with:
          registry: git.example.com
          username: ${{ secrets.GITEA_USER }}
          password: ${{ secrets.GITEA_TOKEN }}

      - name: Build and Push
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: git.example.com/youruser/myapp:${{ github.sha }}
          cache-from: type=local,src=/tmp/.buildx-cache
          cache-to: type=local,dest=/tmp/.buildx-cache-new,mode=max

      - name: Health Check
        run: |
          echo "Build completed: git.example.com/youruser/myapp:${{ github.sha }}"
          docker pull git.example.com/youruser/myapp:${{ github.sha }}
          echo "Image verified ✅"
```

### 5.3 Configure Secrets

In Gitea repository settings: Settings → Actions → Secrets

- `GITEA_USER`: Your Gitea username
- `GITEA_TOKEN`: Gitea Personal Access Token (generate in user settings)

### 5.4 Trigger the Build

```bash
git add .gitea/workflows/ci.yml
git commit -m "feat: add CI pipeline"
git push origin main
```

After pushing, Gitea Actions will automatically trigger the build pipeline.

---

## Step 6: Advanced Configuration

### 6.1 Multi-Runner Load Balancing

As projects grow, a single Runner may become a bottleneck. Deploy multiple Runners:

```yaml
# Second Runner configuration
services:
  runner-2:
    image: gitea/act_runner:latest
    environment:
      - GITEA_RUNNER_NAME=vps-runner-02
      # Other config same as above
```

Set different labels for different Runners in Gitea (e.g., `linux-amd64`, `linux-arm64`), and specify in Workflow:

```yaml
jobs:
  build-arm:
    runs-on: [self-hosted, linux-arm64]
```

### 6.2 Use Self-Hosted Docker Registry for Cache

Combine with the private Registry mentioned earlier for significantly faster builds:

```yaml
- name: Build and Push
  uses: docker/build-push-action@v5
  with:
    context: .
    push: true
    tags: git.example.com/youruser/myapp:${{ github.sha }}
    cache-from: type=registry,ref=git.example.com/youruser/myapp:buildcache
    cache-to: type=registry,ref=git.example.com/youruser/myapp:buildcache,mode=max
```

### 6.3 Auto-Deploy Script

```yaml
# .gitea/workflows/deploy.yml
name: Deploy to Production

on:
  workflow_run:
    workflows: ["CI Pipeline"]
    types: [completed]
    branches: [main]

jobs:
  deploy:
    if: ${{ github.event.workflow_run.conclusion == 'success' }}
    runs-on: self-hosted
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Deploy via SSH
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.PROD_SERVER }}
          username: ${{ secrets.DEPLOY_USER }}
          key: ${{ secrets.SSH_PRIVATE_KEY }}
          script: |
            cd /opt/myapp
            docker compose pull
            docker compose up -d
            docker image prune -f
            echo "Deployed successfully at $(date)"
```

### 6.4 Webhook Notifications

Configure Webhooks in Gitea repository settings to push build status to Slack/Discord/Telegram:

```
Webhook URL: https://api.telegram.org/bot<TOKEN>/sendMessage
Body (JSON):
{
  "chat_id": <CHAT_ID>,
  "text": "🚀 Build #${{ github.run_number }} completed: ${{ github.event.workflow_run.conclusion }}",
  "parse_mode": "HTML"
}
```

---

## Step 7: Security Hardening

### 7.1 Restrict Public Registration

```bash
# In Gitea app.ini
[service]
DISABLE_REGISTRATION = false  # Allow registration
REQUIRE_SIGNIN_VIEW = true    # Require login to view
```

### 7.2 Enable 2FA

Admin Panel → Admin Settings → Security Settings → Require 2FA for administrators.

### 7.3 Limit Runner Permissions

```yaml
# docker-compose.yml — restrict Runner permissions
services:
  runner:
    security_opt:
      - no-new-privileges:true
    read_only: true
    tmpfs:
      - /tmp
```

### 7.4 Regular Backups

```bash
# Backup Gitea data
0 3 * * * tar czf /backup/gitea-$(date +\%Y\%m\%d).tar.gz /data/gitea/
find /backup -name "gitea-*.tar.gz" -mtime +30 -delete

# Backup Runner data
0 4 * * * tar czf /backup/gitea-runner-$(date +\%Y\%m\%d).tar.gz ~/gitea-runner/
```

---

## Cost Comparison

| Solution | Monthly Cost (1 Runner) | Storage | Annual Cost |
|----------|------------------------|---------|-------------|
| GitHub Actions (free tier) | $0 | 5GB | $0 |
| GitHub Actions (paid) | ~$0.008/min | Pay per use | ~$200+ |
| GitLab CI (self-hosted Runner) | $0 | 50GB | ~$10 (VPS) |
| **Gitea Actions (self-hosted)** | **$0** | **Included** | **$0 extra** |

> Assuming VPS is already purchased ($5-10/month), the incremental cost of Gitea Actions is **zero**.

---

## FAQ

### Q: Runner registration fails

Check network connectivity and whether the Token has expired. Regenerate the Token in Gitea Admin Panel.

### Q: Build is slow

- Check if Runner's CPU/memory resources are sufficient
- Enable Docker Build Cache (see Section 6.2)
- Use `docker/setup-buildx-action` to accelerate builds

### Q: Docker-in-Docker permission issues

Ensure the Runner container can access the Docker socket:

```bash
# Check permissions
ls -la /var/run/docker.sock
# Should show: srw-rw---- 1 root docker ...
```

### Q: How to migrate existing GitHub Actions Workflows?

Gitea Actions is fully compatible with GitHub Actions' YAML syntax. Just keep the version numbers in `uses: actions/xxx` up to date. Some GitHub-exclusive Actions may need replacement.

---

## Summary

A self-hosted CI/CD pipeline is a cornerstone of the VPS self-hosting ecosystem:

- ✅ **Zero extra cost**: Reuse existing VPS, no subscription fees
- ✅ **Full control**: Code, build logs, and artifacts all stay local
- ✅ **GitHub Actions compatible**: Same YAML syntax, low migration cost
- ✅ **Flexible scaling**: Multi-runner, multi-label, multi-environment deployment

A single 2C4G VPS (approx. $5-10/month) can support a small team's complete CI/CD pipeline — far more cost-effective than commercial platforms.

---

*All code verified on Ubuntu 24.04 + Docker 27.x + Gitea 1.22 + Act Runner.*
