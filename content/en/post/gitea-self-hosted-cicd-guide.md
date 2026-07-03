---
title: "Gitea + Gitea Actions: The Complete Self-Hosted CI/CD Pipeline Guide — Free GitLab CI Alternative"
description: "Set up Gitea code hosting + Gitea Actions automated pipelines from scratch on your VPS. No paid subscriptions needed, no exposing code to public clouds — achieve full automation from commit to deployment."
date: 2026-07-03T10:00:00+08:00
lastmod: 2026-07-03T10:00:00+08:00
slug: "gitea-self-hosted-cicd-guide"
tags: ["Gitea", "CI/CD", "Gitea Actions", "Self-Hosted", "DevOps", "Docker", "Automation", "VPS"]
categories: ["Deployment Guides"]
draft: false
image: /images/posts/gitea-self-hosted-cicd-guide/featured.png
aliases: [/en/post/gitea-self-hosted-cicd-guide/]
---

## Why Self-Hosted CI/CD?

In the cloud-native era, CI/CD (Continuous Integration / Continuous Delivery) has become essential software development infrastructure. While GitHub Actions and GitLab CI are powerful, they have several pain points:

- **Costs scale with usage**: GitHub Actions free tier is limited; beyond that, you pay per minute. GitLab CI runner resources also require paid upgrades.
- **Code privacy concerns**: Pushing code to public cloud platforms carries inherent data exposure risks, even with encryption.
- **Network latency**: Cross-border access to GitHub/GitLab runners can result in slow build times.
- **Vendor lock-in**: Migration costs are high, and while workflow syntax is similar, details differ significantly.

**Gitea + Gitea Actions** provides the perfect alternative: lightweight, low resource footprint, fully self-hosted, with native Actions syntax support.

## What is Gitea?

[Gitea](https://gitea.com) is an open-source Git service written in Go, featuring:

- **Extremely lightweight**: Runs as a single binary, memory usage ~100MB
- **Feature-complete**: Supports Issues, Pull Requests, Wiki, Package Registry
- **Resource-friendly**: Minimum 512MB RAM to run, ideal for small VPS
- **Active community**: Over 45,000+ GitHub stars

## What is Gitea Actions?

[Gitea Actions](https://docs.gitea.com/usage/actions/introduction) is Gitea's built-in CI/CD engine, fully compatible with GitHub Actions workflow syntax. This means:

- Existing GitHub Actions workflows can migrate with near-zero modifications
- Same `.github/workflows/` directory structure
- Supports both Docker-based and self-hosted runners

## Architecture Overview

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Developer   │────▶│   Gitea Server    │────▶│  Gitea Runner   │
│  (Local)     │     │  (Code + Web UI)  │     │  (Build Execution)│
└─────────────┘     └──────────────────┘     └─────────────────┘
                           │                        │
                           ▼                        ▼
                    ┌──────────────┐         ┌──────────────┐
                    │ PostgreSQL/  │         │  Docker /    │
                    │ SQLite       │         │ Target Server │
                    └──────────────┘         └──────────────┘
```

## Step 1: Deploy Gitea

### One-Click Docker Compose Deployment

Create a `docker-compose.yml` file:

```yaml
version: '3'

services:
  gitea:
    image: gitea/gitea:1.22
    container_name: gitea
    environment:
      - USER_UID=1000
      - USER_GID=1000
      - GITEA__actions__ENABLED=true
    restart: always
    volumes:
      - ./gitea-data:/data
      - /etc/timezone:/etc/timezone:ro
      - /etc/localtime:/etc/localtime:ro
    ports:
      - "3000:3000"
      - "2222:22"
    depends_on:
      - db

  db:
    image: postgres:16-alpine
    container_name: gitea-db
    environment:
      - POSTGRES_USER=gitea
      - POSTGRES_PASSWORD=gitea_secure_password
      - POSTGRES_DB=gitea
    restart: always
    volumes:
      - ./postgres-data:/var/lib/postgresql/data
```

Start the services:

```bash
mkdir -p gitea-data postgres-data
docker compose up -d
```

> **Tip**: First visit `http://your-server-ip:3000` to enter the installation wizard. SSH port is mapped to 2222 to avoid conflict with the host's port 22.

### Key Installation Wizard Configuration

| Setting | Recommended Value |
|---------|-------------------|
| Database Type | PostgreSQL (production) / SQLite (testing) |
| SSH Port | 2222 |
| Gitea Domain | Your VPS IP or domain |
| Admin Account | Set your own |
| Enable Actions | ✅ Must enable |

## Step 2: Configure Gitea Actions Runner

Gitea Actions requires a Runner to execute workflows. Two approaches:

### Method 1: Docker-in-Docker (Recommended for Beginners)

Simplest approach — the Runner runs Docker inside a container:

```yaml
# docker-compose.yml - Add Runner service
services:
  runner:
    image: gitea/act_runner:latest
    container_name: gitea-runner
    restart: always
    volumes:
      - ./runner-data:/data
      - /var/run/docker.sock:/var/run/docker.sock
    environment:
      - GITEA_INSTANCE_URL=http://gitea:3000
      - GITEA_RUNNER_NAME=my-runner
      - GITEA_RUNNER_REGISTRATION_TOKEN=your_registration_token
```

### Method 2: Self-Hosted Runner (Recommended for Production)

Install the Runner directly on the host machine for better performance:

```bash
# Download act_runner
wget https://dl.gitea.com/gitea/act_runner/latest/act_runner-linux-amd64
chmod +x act_runner-linux-amd64
mv act_runner-linux-amd64 /usr/local/bin/act_runner

# Register Runner
act_runner register \
  --instance http://your-server-ip:3000 \
  --name my-selfhosted-runner \
  --token your_registration_token

# Install as system service
act_runner daemon install
act_runner daemon start
```

> **Get Registration Token**: Go to Gitea Web → Repository → Settings → Actions → Runners → Click "New Runner" to get the token.

### Configuring Runner Labels

To ensure workflows match the correct runner, configure labels:

```bash
# Edit Runner config file
nano /root/gitea-data/act_runner/cfg.yaml

# Add labels
labels:
  - ubuntu-latest=x86_64-linux
  - selfhosted=x86_64-linux
```

## Step 3: Write Your First Workflow

Gitea Actions uses YAML workflow files stored in `.gitea/workflows/` directory (note: `.gitea`, not `.github`).

### Example 1: Go Project Auto Build & Test

```yaml
# .gitea/workflows/go-ci.yml
name: Go CI/CD

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: selfhosted
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Go
        uses: actions/setup-go@v5
        with:
          go-version: '1.22'

      - name: Build
        run: go build -v ./...

      - name: Test
        run: go test -v ./...

      - name: Upload coverage
        run: |
          go test -coverprofile=coverage.out ./...
          go tool cover -html=coverage.out -o coverage.html
        if: success()
```

### Example 2: Docker Image Build & Push

```yaml
# .gitea/workflows/docker-publish.yml
name: Docker Publish

on:
  release:
    types: [published]

jobs:
  docker:
    runs-on: selfhosted
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Login to Gitea Container Registry
        uses: docker/login-action@v3
        with:
          registry: gitea.yourdomain.com
          username: your_username
          password: ${{ secrets.GITEA_TOKEN }}

      - name: Set up QEMU
        uses: docker/setup-qemu-action@v3

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: |
            gitea.yourdomain.com/yourusername/yourapp:${{ github.ref_name }}
            gitea.yourdomain.com/yourusername/yourapp:latest
          platforms: linux/amd64,linux/arm64
```

### Example 3: Auto Deploy to Target Server

```yaml
# .gitea/workflows/deploy.yml
name: Deploy to VPS

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: selfhosted
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Deploy via SSH
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.DEPLOY_HOST }}
          username: ${{ secrets.DEPLOY_USER }}
          key: ${{ secrets.DEPLOY_KEY }}
          port: 22
          script: |
            cd /opt/myapp
            docker compose pull
            docker compose up -d
            docker image prune -f
```

## Step 4: Configure Secrets & Permissions

### Adding Repository Secrets

Go to Repository → Settings → Actions → Secrets → New Secret:

| Secret Name | Purpose |
|-------------|---------|
| `GITEA_TOKEN` | Personal Access Token for Docker Registry login |
| `DEPLOY_HOST` | Target deployment server IP address |
| `DEPLOY_USER` | SSH username |
| `DEPLOY_KEY` | SSH private key content |

### Generating Personal Access Token

```
Settings → Applications → Generate Token
Permissions: repo, write:packages
```

## Step 5: Gitea Package Registry

Gitea includes a built-in package registry to replace Docker Hub and npm registry:

```yaml
# Enabled in docker-compose.yml, access at:
# http://your-domain:3000/-/packages
```

Push Docker images to Gitea Package Registry:

```bash
# Login
docker login gitea.yourdomain.com -u your_username -p your_token

# Build and push
docker build -t gitea.yourdomain.com/yourusername/myapp:v1.0 .
docker push gitea.yourdomain.com/yourusername/myapp:v1.0
```

## Troubleshooting

### Issue 1: Runner Shows "Offline"

```bash
# Check Runner logs
docker logs gitea-runner -f

# Verify network connectivity
curl -I http://gitea:3000

# Check if registration token expired
# Regenerate token and restart Runner
```

### Issue 2: Workflow Stuck

```bash
# View Runner queue
curl -u username:token http://gitea:3000/api/v1/admin/actions/runners

# Increase Runner concurrency
# Edit cfg.yaml
concurrency_limit: 4
```

### Issue 3: Docker-in-Docker Network Problems

```yaml
# Specify network in workflow
jobs:
  build:
    runs-on: selfhosted
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_PASSWORD: test
    steps:
      - uses: actions/checkout@v4
      - name: Connect to DB
        run: |
          # Connect using service container name
          PGPASSWORD=*** psql -h localhost -U postgres -c "SELECT 1"
```

### Issue 4: Disk Space Exhausted

```bash
# Clean Docker cache
docker system prune -af

# Periodically clean old images
act_runner cleanup --keep-latest 5

# Monitor disk usage
df -h /var/lib/docker
```

## Performance Optimization Tips

### 1. Use SQLite Instead of PostgreSQL (Small-Scale Deployments)

```yaml
# Simplified deployment, remove database service
services:
  gitea:
    image: gitea/gitea:1.22
    environment:
      - GITEA__database__DB_TYPE=sqlite3
    volumes:
      - ./gitea-data:/data
```

### 2. Configure Git LFS (Large File Support)

```bash
# Enable LFS in Gitea config
[server]
LFS_START_SERVER = true

# Allocate LFS storage space
[lfs]
PATH = /data/git/lfs
```

### 3. Nginx Reverse Proxy + HTTPS

```nginx
server {
    listen 443 ssl http2;
    server_name gitea.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

    location / {
        proxy_pass http://localhost:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket support for real-time updates
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    location /api/ {
        client_max_body_size 500m;
        proxy_pass http://localhost:3000;
    }
}
```

## Resource Requirements Reference

| Scenario | CPU | RAM | Disk |
|----------|-----|-----|------|
| Single Developer (SQLite) | 1 core | 512MB | 10GB |
| Small Team (PostgreSQL) | 2 cores | 1GB | 20GB |
| With Runner Builds | Extra 2 cores | Extra 2GB | Extra 50GB |
| Large-Scale CI/CD | 4+ cores | 4GB+ | Scale as needed |

## Comparison: GitHub Actions vs Gitea Actions

| Feature | GitHub Actions | Gitea Actions |
|---------|---------------|---------------|
| Free Tier | 2,000 min/month | Unlimited |
| Self-Hosted | ✅ | ✅ |
| Workflow Syntax | ✅ | ✅ (compatible) |
| Marketplace | Rich | Basic (customizable) |
| Privacy Control | Code on cloud | Full self-control |
| Initial Setup | Ready to use | Requires deployment |
| Network Speed | Region-dependent | Very fast (intranet) |
| Multi-Platform Build | ✅ | ✅ |

## Summary

Gitea + Gitea Actions provides a **completely free, fully controllable** CI/CD solution for self-hosting enthusiasts. For budget-conscious individual developers and small teams, it's one of the best alternatives to GitHub Actions and GitLab CI.

**Key Advantages**:
- 🆓 **Zero Cost**: No usage limits, no hidden fees
- 🔒 **Fully Private**: Code and builds entirely on your own server
- ⚡ **High Performance**: Intranet builds, faster than public cloud runners
- 🔄 **Seamless Migration**: Compatible with GitHub Actions syntax, low migration cost

Next steps: Deploy Gitea → Configure Runner → Migrate one non-critical project to test → Gradually replace all CI/CD pipelines.
