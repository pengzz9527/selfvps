---
title: "Self-Host Drone CI: The Complete Lightweight Continuous Integration & Deployment Guide — Docker-Native, Efficient & Flexible"
description: "Build a lightweight, Docker-native continuous integration and deployment pipeline from scratch on your VPS with Drone CI. More concise and resource-efficient than GitLab CI, perfect for small teams and individual developers."
date: 2026-07-10T10:00:00+08:00
lastmod: 2026-07-10T10:00:00+08:00
slug: "drone-ci-selfhosted-guide"
tags: ["Drone CI", "CI/CD", "Docker", "DevOps", "Continuous Integration", "Deployment Automation", "VPS", "Open Source"]
categories: ["Deployment Guide"]
draft: false
image: /images/posts/drone-ci-selfhosted-guide/featured.png
aliases: [/en/post/drone-ci-selfhosted-guide/]
---

## Why Choose Drone CI?

When it comes to self-hosted CI/CD tools, GitLab CI and GitHub Actions dominate the market. However, for VPS users with limited resources and teams seeking simplicity, **Drone CI** offers unique advantages:

- **Extremely Lightweight**: Core components are just one binary + database, memory usage < 100MB
- **Docker Native**: All builds run in containers, providing natural isolation
- **Simple YAML Configuration**: `.drone.yml` syntax is more intuitive than `.gitlab-ci.yml`
- **Rich Plugin Ecosystem**: 100+ built-in plugins with support for custom extensions
- **Free & Open Source**: MIT license, no feature restrictions
- **Multi-Git Platform Support**: GitHub, GitLab, Gitea, Bitbucket, Stash

## Architecture Overview

```
┌──────────────┐     ┌─────────────┐     ┌──────────────┐
│   Git Server  │────▶│  Drone      │────▶│  Build       │
│  (GitHub/     │     │  Server     │     │  Containers  │
│   Gitea/etc)  │     │  :8000      │     │  (Docker)    │
└──────────────┘     └──────┬──────┘     └──────────────┘
                           │
                    ┌──────▼──────┐
                    │  Drone      │
                    │  Agent(s)   │
                    │  :3000      │
                    └─────────────┘
```

## Step 1: Environment Preparation

### System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| CPU | 1 core | 2+ cores |
| Memory | 512MB | 1GB+ |
| Disk | 10GB | 20GB+ SSD |
| OS | Ubuntu 20.04+ / Debian 11+ | Ubuntu 22.04 LTS |

### Install Docker

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sh

# Start and enable on boot
sudo systemctl enable --now docker

# Verify installation
docker --version
# Docker version 24.0.7, build afdd53b
```

## Step 2: Deploy Drone Server with Docker Compose

### Create Project Directory

```bash
mkdir -p ~/drone-ci && cd ~/drone-ci
```

### Generate Secrets

```bash
# Generate Drone secret (for signing JWT tokens)
DRONE_SECRET=$(openssl rand -hex 16)
echo "DRONE_SECRET=$DRONE_SECRET"

# Generate agent shared secret
DRONE_RPC_SECRET=$(openssl rand -hex 16)
echo "DRONE_RPC_SECRET=$DRONE_RPC_SECRET"
```

### Write docker-compose.yml

```yaml
version: '3'

services:
  # Drone Server
  drone-server:
    image: drone/drone:2
    container_name: drone-server
    restart: unless-stopped
    ports:
      - "8000:8000"
    volumes:
      - drone-data:/data
      - /var/run/docker.sock:/var/run/docker.sock
    environment:
      # Database configuration (SQLite by default)
      - DRONE_DATABASE_DRIVER=sqlite3
      - DRONE_DATABASE_DATASET=/data/drone.sqlite
      
      # Server configuration
      - DRONE_SERVER_HOST=${DRONE_SERVER_HOST:-http://localhost:8000}
      - DRONE_SERVER_PROTO=http
      
      # RPC configuration (server-agent communication)
      - DRONE_RPC_SECRET=${DRONE_RPC_SECRET}
      - DRONE_RPC_PROTO=http
      - DRONE_RPC_HOST=drone-server
      - DRONE_RPC_PORT=8000
      
      # Authentication (GitHub example)
      - DRONE_GITHUB_CLIENT_ID=${DRONE_GITHUB_CLIENT_ID}
      - DRONE_GITHUB_CLIENT_SECRET=${DRONE_GITHUB_CLIENT_SECRET}
      - DRONE_GITHUB=true
      
      # Optional configurations
      - DRONE_USER_CREATE=username:your_github_username,admin:true
      - DRONE_LOGS_LEVEL=info
      - DRONE_RESULTS_ENABLE=true
      
    networks:
      - drone-net

  # Drone Agent (handles build tasks)
  drone-agent:
    image: drone/drone-runner-docker:1
    container_name: drone-agent
    restart: unless-stopped
    depends_on:
      - drone-server
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - runner-data:/data
    environment:
      - DRONE_RPC_PROTO=http
      - DRONE_RPC_HOST=drone-server
      - DRONE_RPC_PORT=8000
      - DRONE_RPC_SECRET=${DRONE_RPC_SECRET}
      - DRONE_RUNNER_NAME=${HOSTNAME:-drone-runner}
      - DRONE_RUNNER_CAPACITY=2
      - DRONE_RUNNER_THREADS=2
      
    networks:
      - drone-net

  # Optional: PostgreSQL instead of SQLite (recommended for production)
  # drone-db:
  #   image: postgres:15-alpine
  #   container_name: drone-db
  #   restart: unless-stopped
  #   environment:
  #     POSTGRES_DB: drone
  #     POSTGRES_USER: drone
  #     POSTGRES_PASSWORD: ${DRONE_DB_PASSWORD}
  #   volumes:
  #     - pg-data:/var/lib/postgresql/data
  #   networks:
  #     - drone-net

volumes:
  drone-data:
  runner-data:
  # pg-data:

networks:
  drone-net:
    driver: bridge
```

### Set Environment Variables

```bash
# Create .env file
cat > .env << EOF
# Server address
DRONE_SERVER_HOST=http://your-vps-ip:8000

# Secrets from step 1
DRONE_SECRET=${DRONE_SECRET}
DRONE_RPC_SECRET=${DRONE_RPC_SECRET}

# GitHub OAuth configuration
DRONE_GITHUB_CLIENT_ID=your_github_client_id
DRONE_GITHUB_CLIENT_SECRET=your_github_client_secret

# Admin username
DRONE_ADMIN_USERNAME=your_github_username
EOF
```

### Create GitHub OAuth App

1. Visit [GitHub Settings > Developer settings > OAuth Apps](https://github.com/settings/developers)
2. Click **"New OAuth App"**
3. Fill in:
   - Application name: `Drone CI`
   - Homepage URL: `http://your-vps-ip:8000`
   - Authorization callback URL: `http://your-vps-ip:8000/login/oauth/callback`
4. Save and get **Client ID** and **Client Secret**

### Start Services

```bash
# Pull images
docker compose pull

# Start services
docker compose up -d

# Check logs
docker compose logs -f

# Verify service status
docker ps
```

Expected output:
```
CONTAINER ID   IMAGE                            STATUS
abc123         drone/drone:2                    Up 2 minutes
def456         drone/drone-runner-docker:1      Up 2 minutes
```

## Step 3: Configure Nginx Reverse Proxy (Optional but Recommended)

### Install Nginx

```bash
sudo apt install nginx -y
```

### Create Nginx Configuration

```nginx
server {
    listen 80;
    server_name ci.yourdomain.com;
    
    # Maximum upload file size
    client_max_body_size 50m;
    
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
    }
}
```

```bash
# Test configuration
sudo nginx -t

# Enable site
sudo ln -s /etc/nginx/sites-available/drone /etc/nginx/sites-enabled/

# Reload Nginx
sudo systemctl reload nginx
```

### Configure HTTPS (Let's Encrypt)

```bash
# Install Certbot
sudo apt install certbot python3-certbot-nginx -y

# Get certificate
sudo certbot --nginx -d ci.yourdomain.com

# Enable auto-renewal
sudo systemctl enable --now certbot-renew.timer
```

## Step 4: First Login & Initialization

### Access Drone Web UI

Open browser and visit `http://your-vps-ip:8000` or `https://ci.yourdomain.com`

1. Click **"Sign in with GitHub"**
2. Authorize Drone to access your GitHub account
3. If you configured `DRONE_USER_CREATE`, you'll automatically become an admin

### Verify Installation

```bash
# Check server status via API
curl -H "Authorization: Bearer <your_token>" \
     http://localhost:8000/api/healthz

# Returns {"status":"ok"} if running normally
```

## Step 5: Configure Your First Project

### Add Repository

1. In Drone Web UI, click **"Repositories"** on the left sidebar
2. Click **"Activate"** button to activate repositories you want to monitor
3. Or use API to activate:

```bash
# Activate repository
curl -X PUT \
  -H "Authorization: Bearer <your_token>" \
  -H "Content-Type: application/json" \
  http://localhost:8000/api/repos/username/repo-name/activate
```

### Create .drone.yml

Create `.drone.yml` configuration file in your project root:

```yaml
# Basic build pipeline
kind: pipeline
type: docker
name: default

steps:
  # 1. Checkout code
  - name: checkout
    image: alpine/git
    commands:
      - git fetch --all
      - git checkout $DRONE_COMMIT_BRANCH

  # 2. Install dependencies
  - name: install-dependencies
    image: node:20-alpine
    commands:
      - npm ci

  # 3. Code linting
  - name: lint
    image: node:20-alpine
    commands:
      - npm run lint
    when:
      branch: [main, develop]

  # 4. Run tests
  - name: test
    image: node:20-alpine
    commands:
      - npm test
    when:
      branch: [main, develop]

  # 5. Build Docker image
  - name: build-image
    image: plugins/docker
    settings:
      registry: docker.io
      username:
        from_secret: docker_username
      password:
        from_secret: docker_password
      repo: yourusername/your-app
      tags: 
        - latest
        - $DRONE_COMMIT_SHA
    when:
      branch: main
      event: push

  # 6. Deploy to server
  - name: deploy
    image: appleboy/drone-ssh
    settings:
      host:
        from_secret: deploy_host
      username:
        from_secret: deploy_user
      key:
        from_secret: deploy_key
      port: 22
      script:
        - cd /opt/your-app
        - docker compose pull
        - docker compose up -d
    when:
      branch: main
      event: push
```

### Configure Secrets

Add secrets in the project **"Settings > Secrets"**:

| Name | Value | Description |
|------|-------|-------------|
| `docker_username` | Your Docker Hub username | For pushing images |
| `docker_password` | Docker Hub password/token | For pushing images |
| `deploy_host` | Target server IP | Deployment target |
| `deploy_user` | SSH username | Usually `root` or `deploy` |
| `deploy_key` | SSH private key | For SSH connection |

## Step 6: Advanced Configuration

### Use Cache to Speed Up Builds

```yaml
kind: pipeline
type: docker
name: default

steps:
  - name: restore-cache
    image: alpine:3.18
    commands:
      - mkdir -p ~/.cache/npm
      - ls -la ~/.cache/npm

  - name: install-dependencies
    image: node:20-alpine
    commands:
      - npm ci
    volumes:
      - name: cache
        path: ~/.cache

  # ... other steps

volumes:
  - name: cache
    temp: {}
```

### Execute Multiple Steps in Parallel

```yaml
steps:
  - name: unit-tests
    image: golang:1.21-alpine
    commands:
      - go test ./... -v
    when:
      branch: main

  - name: integration-tests
    image: golang:1.21-alpine
    commands:
      - go test ./integration/... -v
    when:
      branch: main

  - name: security-scan
    image: aquasec/trivy:latest
    commands:
      - trivy fs --severity HIGH,CRITICAL .
    when:
      branch: main
```

### Conditional Execution

```yaml
steps:
  - name: build-staging
    image: plugins/docker
    settings:
      repo: myapp/staging
      auto_tag: true
    when:
      branch: develop
      event: push

  - name: build-production
    image: plugins/docker
    settings:
      repo: myapp/prod
      auto_tag: true
    when:
      branch: main
      event: push

  - name: notify-slack
    image: plugins/slack
    settings:
      webhook:
        from_secret: slack_webhook
      channel: deployments
      template: >
        {{ success "#Build {{build.number}} succeeded"}}
        {{ failure "#Build {{build.number}} failed"}}
```

### Use Global Variables

```yaml
kind: pipeline
type: docker
name: default

platform:
  os: linux
  arch: amd64

settings:
  DOCKER_REGISTRY: docker.io
  APP_NAME: myapp

steps:
  - name: build
    image: docker:dind
    environment:
      DOCKER_HOST: tcp://docker:2375
    commands:
      - docker build -t $DOCKER_REGISTRY/$APP_NAME:$DRONE_COMMIT_SHA .
      - docker push $DOCKER_REGISTRY/$APP_NAME:$DRONE_COMMIT_SHA
```

## Step 7: Security Hardening

### Firewall Configuration

```bash
# Allow only necessary ports
sudo ufw allow 22/tcp      # SSH
sudo ufw allow 80/tcp      # HTTP
sudo ufw allow 443/tcp     # HTTPS
sudo ufw deny 8000/tcp     # Hide Drone direct access

# Enable firewall
sudo ufw enable
```

### Restrict Access

```bash
# Restrict specific branches in .drone.yml
when:
  branch: main

# Or use whitelist
whitelist:
  branches: [main, release/*]
  events: [push, tag]
```

### Regular Backups

```bash
#!/bin/bash
# backup-drone.sh

BACKUP_DIR="/backup/drone"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/drone-backup-$TIMESTAMP.tar.gz"

# Create backup directory
mkdir -p $BACKUP_DIR

# Backup data volume
docker run --rm \
  -v drone_ci_drone-data:/data \
  -v $BACKUP_DIR:/backup \
  alpine tar czf /backup/drone-backup-$TIMESTAMP.tar.gz -C /data .

# Keep only last 7 days of backups
find $BACKUP_DIR -name "drone-backup-*.tar.gz" -mtime +7 -delete

echo "Backup completed: $BACKUP_FILE"
```

Add to crontab:
```bash
crontab -e
# Backup daily at 3 AM
0 3 * * * /path/to/backup-drone.sh >> /var/log/drone-backup.log 2>&1
```

## Common Issues & Solutions

### Issue 1: Agent Cannot Connect to Server

```bash
# Check network connectivity
docker exec drone-agent ping drone-server

# View Agent logs
docker logs drone-agent

# Common causes:
# 1. DRONE_RPC_SECRET mismatch
# 2. Firewall blocking port 8000
# 3. DNS resolution issues
```

### Issue 2: Build Steps Timeout

```yaml
# Increase timeout
steps:
  - name: build
    image: node:20
    commands:
      - npm run build
    timeout: 3600  # 60 minutes timeout
```

### Issue 3: Docker-in-Docker Permission Issues

```bash
# Ensure Docker socket is mounted correctly
docker inspect drone-agent | grep -A 5 Mounts

# If using DinD, privileged mode is required
environment:
  - DOCKER_TLS_CERTDIR=""
  - DOCKER_HOST=tcp://docker:2375
```

### Issue 4: Webhooks Not Triggering

```bash
# Check GitHub webhook configuration
# 1. Go to repository Settings > Webhooks
# 2. Confirm Payload URL: http://your-domain/hook
# 3. Confirm Content type: application/json
# 4. Test webhook delivery

# Check Drone logs
docker logs drone-server | grep webhook
```

## Performance Optimization Tips

### Resource Limits

```yaml
# drone-agent configuration
environment:
  - DRONE_RUNNER_CAPACITY=4      # Max concurrent builds
  - DRONE_RUNNER_THREADS=4       # Thread count
  - DRONE_RUNNER_KEEPALIVE_ENABLED=true
```

### Use Pre-built Images

```yaml
steps:
  - name: build
    image: node:20-alpine  # Use slimmed image
    commands:
      - npm run build
```

### Enable Result Caching

```yaml
# Configure caching in your project
steps:
  - name: cache-node-modules
    image: alpine
    commands:
      - tar xzf node_modules.tar.gz || npm ci
    when:
      status: [success, failure]
```

## Summary

Drone CI is an ideal lightweight CI/CD solution for VPS environments:

| Feature | Drone CI | GitLab CI | GitHub Actions |
|---------|----------|-----------|----------------|
| Memory Usage | ~50MB | ~500MB+ | N/A (Cloud) |
| Learning Curve | ⭐⭐ Low | ⭐⭐⭐ Medium | ⭐⭐ Low |
| Config Complexity | Simple YAML | Complex YAML | Simple YAML |
| Self-host Cost | Very Low | High | None |
| Plugin Count | 100+ | Rich | Rich |
| Community Activity | Active | Very Active | Very Active |

For VPS with 1-4GB memory, Drone CI is the perfect choice. Combined with Docker, you can easily manage build pipelines for multiple projects.

---

*This guide is based on Drone CI v2.x, applicable to Ubuntu 20.04+/Debian 11+ systems.*