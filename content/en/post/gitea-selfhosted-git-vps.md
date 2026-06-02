---
title: "Gitea Self-Hosted Git Service: Set Up a Lightweight Code Repository on Your VPS"
description: "Deploy Gitea on your VPS — a lightweight, self-hosted Git service that runs on just 256MB RAM. Complete guide covering Docker deployment, reverse proxy with HTTPS, PostgreSQL, CI/CD pipelines, team collaboration, and backup automation."
date: 2026-06-02T09:00:00+08:00
slug: "gitea-selfhosted-git-vps"
tags: ["Gitea", "Git", "code hosting", "Docker", "self-hosting", "VPS", "CI/CD", "DevOps", "GitHub alternative"]
categories: ["DevOps", "Version Control"]
draft: false
image: /images/posts/gitea-selfhosted-git-vps/featured.png
---

## Introduction

> **Bottom line**: Gitea is the lightest, easiest-to-deploy self-hosted Git service. A 1-core 512MB budget VPS is all you need. Docker installation takes 3 minutes, and resource usage is under 1/10 of GitLab.

GitHub is great, but storing your code on someone else's server always carries privacy, compliance, and availability risks. GitLab is powerful but bloated — the official requirement recommends 4GB RAM minimum, which your small VPS simply can't handle. **Gitea** fills this gap perfectly: written in Go, runs as a single binary, sips just 256MB of RAM, yet packs everything — repository management, Issue tracking, Pull Requests, CI/CD, WebHooks, and Wiki.

This guide walks you through deploying Gitea with Docker, configuring a reverse proxy with HTTPS, connecting PostgreSQL, and setting up CI/CD pipelines.

---

## Why Gitea?

| Feature | Gitea | GitLab CE | GitHub Free |
|---------|-------|-----------|-------------|
| Memory usage | ~150MB | ~2-4GB | N/A (hosted) |
| Setup time | 3 minutes | 30+ minutes | No setup needed |
| Code ownership | ✅ Full control | ✅ Full control | ❌ Hosted by GitHub |
| Private repos | ✅ Unlimited | ✅ Unlimited | ✅ Unlimited |
| CI/CD | ✅ Built-in (lightweight) | ✅ Built-in (heavy) | ❌ Needs GitHub Actions |
| Team collaboration | ✅ Push/Pull/Review | ✅ Full-featured | ✅ Full-featured |
| Two-factor auth | ✅ Supported | ✅ Supported | ✅ Supported |
| WebHook | ✅ Supported | ✅ Supported | ✅ Supported |

**Best for**:
- Solo developers / small teams needing private code hosting
- Compliance requirements (data must stay in-region)
- Teams wanting self-hosted CI/CD pipelines
- Budget VPS (1 vCPU / 1GB RAM) running Git services

---

## Prerequisites

Before starting, ensure your VPS meets these requirements:

| Item | Minimum | Recommended |
|------|---------|-------------|
| CPU | 1 core | 2 cores |
| RAM | 512MB | 1GB |
| Disk | 10GB | 20GB+ |
| Docker | ✅ Installed | Docker Compose |
| Domain | Optional (recommended) | e.g. `git.yourdomain.com` |

Verify Docker and Docker Compose:

```bash
docker --version && docker compose version
```

If not installed, quick Docker setup:

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
```

---

## Step 1: Deploy Gitea with Docker Compose

Create a directory and write `docker-compose.yml`:

```bash
mkdir -p ~/gitea && cd ~/gitea
```

```yaml
# docker-compose.yml
version: "3"

services:
  gitea:
    image: gitea/gitea:latest
    container_name: gitea
    environment:
      - USER_UID=1000
      - USER_GID=1000
      - GITEA__database__DB_TYPE=postgres
      - GITEA__database__HOST=db:5432
      - GITEA__database__NAME=gitea
      - GITEA__database__USER=gitea
      - GITEA__database__PASSWD=gitea_secret_password
      - GITEA__server__DOMAIN=git.yourdomain.com
      - GITEA__server__HTTP_PORT=3000
      - GITEA__server__ROOT_URL=https://git.yourdomain.com
      - GITEA__server__DISABLE_SSH=false
      - GITEA__server__SSH_PORT=2222
      - GITEA__server__SSH_LISTEN_PORT=22
    restart: always
    networks:
      - gitea
    volumes:
      - ./gitea:/data
      - /etc/timezone:/etc/timezone:ro
      - /etc/localtime:/etc/localtime:ro
    ports:
      - "127.0.0.1:3000:3000"
      - "2222:22"
    depends_on:
      - db

  db:
    image: postgres:16-alpine
    container_name: gitea-db
    restart: always
    environment:
      - POSTGRES_USER=gitea
      - POSTGRES_PASSWORD=gitea_secret_password
      - POSTGRES_DB=gitea
    networks:
      - gitea
    volumes:
      - ./postgres:/var/lib/postgresql/data

networks:
  gitea:
    driver: bridge
```

> ⚠️ **Security note**: Replace `gitea_secret_password` with a strong password. The SSH port maps to `2222:22` because port 22 on the host is usually taken by SSH.

Start the services:

```bash
docker compose up -d
```

Check status:

```bash
docker compose ps
```

Both containers should show `Up` status.

---

## Step 2: Configure Nginx Reverse Proxy with HTTPS

Gitea runs on `127.0.0.1:3000`. We'll proxy it through Nginx with SSL.

Add this Nginx config (if using Nginx Proxy Manager, add through the Web UI):

```nginx
# /etc/nginx/sites-available/gitea
server {
    listen 80;
    server_name git.yourdomain.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name git.yourdomain.com;

    ssl_certificate     /etc/letsencrypt/live/git.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/git.yourdomain.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

Enable config and get SSL:

```bash
sudo ln -s /etc/nginx/sites-available/gitea /etc/nginx/sites-enabled/
sudo certbot --nginx -d git.yourdomain.com
sudo systemctl reload nginx
```

For Nginx Proxy Manager users, add in the Web UI:
- **Domain**: `git.yourdomain.com`
- **Forward Hostname**: `127.0.0.1`
- **Forward Port**: `3000`
- **SSL**: Request Let's Encrypt certificate
- **WebSocket**: Enable ✅

---

## Step 3: Initial Setup

Visit `https://git.yourdomain.com` in your browser. You'll see the Gitea installation page.

Key configuration fields:

| Setting | Recommended Value | Notes |
|---------|-------------------|-------|
| Database Type | PostgreSQL | Pre-configured in docker-compose |
| Database Host | db:5432 | Docker internal network |
| Database User | gitea | Must match docker-compose |
| Database Password | gitea_secret_password | Your password |
| Database Name | gitea | Must match docker-compose |
| Site Title | Your Git service name | e.g. "My Code" |
| Repository Root Path | /data/git/repositories | Default is fine |
| SSH Server Domain | git.yourdomain.com | Your domain |
| SSH Port | 2222 | Mapped SSH port |
| Gitea Base URL | https://git.yourdomain.com | Final access URL |

Click "Install Gitea" and the system will complete configuration. Then create your admin account.

> 💡 **Tip**: After installation, you can modify settings in `/data/gitea/conf/app.ini` and restart the container.

---

## Step 4: Daily Usage & Team Collaboration

### Creating a Repository

1. Log in and click "+" → **New Repository**
2. Fill in repository name and description
3. Choose public or private
4. Optional: Initialize with README, .gitignore, license

### Pushing Code

```bash
# Clone an existing repo to Gitea
git clone --bare https://github.com/your/repo.git
cd repo.git
git push --mirror https://git.yourdomain.com/username/new-repo.git
cd ..
rm -rf repo.git

# Or push a new project directly
git remote add origin https://git.yourdomain.com/username/my-project.git
git push -u origin main
```

### SSH Key Setup

1. User avatar (top right) → **Settings** → **SSH/GPG Keys**
2. Add your public key (`~/.ssh/id_rsa.pub`)
3. Push using SSH protocol:

```bash
git remote add origin ssh://git@git.yourdomain.com:2222/username/repo.git
git push -u origin main
```

### Team Collaboration

| Feature | How To |
|---------|--------|
| Add collaborator | Repository → Settings → Manage → Add collaborator |
| Create organization | Top-right "+" → New Organization |
| Team management | Organization → Teams → Create team with permissions |
| Pull Request | Branch development → Submit PR → Review → Merge |
| Issue tracking | Repository → Issues → Labels/Milestones/Kanban |
| Wiki | Repository → Wiki → Write documentation |
| Code review | Inline comments on PR → Approve/Request Changes |

---

## Step 5: Set Up CI/CD Pipelines

Gitea has **Gitea Actions** (compatible with GitHub Actions syntax). You just need to enable a Runner.

### Start an Actions Runner

```bash
# Create Runner directory
mkdir -p ~/gitea-runner && cd ~/gitea-runner

# Download and register Runner
docker run --rm -it -v $PWD:/data gitea/act_runner:latest \
  /bin/sh -c "act_runner --version && act_runner register"

# Registration instructions:
# 1. In Gitea Web UI: Site Admin → Actions → Runner → Create Runner
# 2. Get the registration token
# 3. Start the Runner with docker compose
```

Write `act-runner-docker-compose.yml`:

```yaml
version: "3"

services:
  runner:
    image: gitea/act_runner:latest
    environment:
      - GITEA_INSTANCE_URL=https://git.yourdomain.com
      - GITEA_RUNNER_REGISTRATION_TOKEN=your-registration-token
      - GITEA_RUNNER_NAME=vps-runner
    volumes:
      - ./data:/data
      - /var/run/docker.sock:/var/run/docker.sock
    restart: always
```

Start the Runner:

```bash
docker compose -f act-runner-docker-compose.yml up -d
```

### Write a Workflow

Create `.gitea/workflows/deploy.yml` in your repository:

```yaml
name: Deploy
on: [push]

jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: 20

      - name: Install dependencies
        run: npm ci

      - name: Run tests
        run: npm test

      - name: Build
        run: npm run build

      - name: Deploy via SSH
        env:
          DEPLOY_KEY: ${{ secrets.DEPLOY_KEY }}
        run: |
          echo "$DEPLOY_KEY" > deploy_key
          chmod 600 deploy_key
          rsync -avz -e "ssh -i deploy_key -o StrictHostKeyChecking=no" \
            ./dist/ user@yourserver:/var/www/myapp/
```

> 💡 Add `secrets.DEPLOY_KEY` in the Gitea repository settings to securely store your SSH private key.

---

## Step 6: Backup & Restore

### Automated Backup (Recommended)

Create a backup script `~/gitea-backup.sh`:

```bash
#!/bin/bash
BACKUP_DIR="/backups/gitea"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p $BACKUP_DIR

# Backup Gitea data directory
docker exec gitea tar czf - /data > $BACKUP_DIR/gitea-data-$DATE.tar.gz

# Backup PostgreSQL database
docker exec gitea-db pg_dump -U gitea gitea > $BACKUP_DIR/gitea-db-$DATE.sql

# Compress database backup
gzip $BACKUP_DIR/gitea-db-$DATE.sql

# Keep last 30 days
find $BACKUP_DIR -name "*.tar.gz" -mtime +30 -delete
find $BACKUP_DIR -name "*.gz" -mtime +30 -delete

echo "✅ Backup completed: $DATE"
```

Add to crontab:

```bash
chmod +x ~/gitea-backup.sh
crontab -e
# Add: 0 3 * * * /root/gitea-backup.sh
```

### Restore

```bash
# Restore data directory
docker exec -i gitea tar xzf - -C / < gitea-data-20260601_030000.tar.gz

# Restore database
gunzip < gitea-db-20260601_030000.sql.gz | docker exec -i gitea-db psql -U gitea gitea

# Restart Gitea
docker compose restart gitea
```

---

## Performance Optimization Tips

1. **Use SQLite (solo/small team)**: If you're the only user, SQLite is even lighter:
   ```yaml
   environment:
     - GITEA__database__DB_TYPE=sqlite3
   ```
   Drop the PostgreSQL service and run a single container — memory usage drops to **~80MB**.

2. **Nginx cache static assets**:
   ```nginx
   location /assets/ {
       proxy_pass http://127.0.0.1:3000;
       expires 7d;
       add_header Cache-Control "public, immutable";
   }
   ```

3. **Enable Git compression** in `app.ini`:
   ```ini
   [git]
   GC_ARGS = --aggressive --auto
   ENABLE_PUSH_OPTIONS = false
   ```

4. **Set repo size limits** in admin panel to 500MB per repo — prevents disk overflow.

---

## FAQ

### Q: What's the difference between Gitea and Gogs?
Gitea is a fork of Gogs with a much more active community, faster updates, and more features. **Go with Gitea.**

### Q: How do I migrate GitHub repos to Gitea?
Use Gitea's built-in migration tool: **New Repository → Migrate Repository**, enter the GitHub repo URL and a personal access token.

### Q: Does Gitea support LDAP/OAuth login?
Yes. Admin panel → Authentication Sources → Add Source. Supports LDAP, OAuth2 (GitHub, Google, GitLab, etc.), and PAM.

### Q: Can I restrict repository visibility?
Yes. Each repository can be public, private, or internal (visible to organization members).

### Q: How do I upgrade Gitea?
```bash
cd ~/gitea
docker compose pull
docker compose up -d
```

---

## Conclusion

Gitea gives you full control over your code at minimal cost. It's fully Git-compatible, and daily usage feels nearly identical to GitHub, so the learning curve is almost zero.

**Your next steps**:
- ✅ Migrate personal projects from GitHub to Gitea
- ✅ Configure Gitea Actions for automated deployments
- ✅ Create organizations and set team permissions
- ✅ Set up Drone CI or Woodpecker CI for enhanced pipelines

> 🎯 One command, 5 minutes, 256MB of RAM — that's Gitea's extreme lightness. If you've been searching for a "self-hosted GitHub alternative" but found GitLab too heavy, Gitea is the answer you've been waiting for.

---

**Related articles**:
- [Nginx Proxy Manager Reverse Proxy Setup](/en/post/nginx-proxy-manager-guide/)
- [Docker Security Hardening Guide](/en/post/docker-security-hardening/)
- [VPS Backup Automation](/en/post/vps-backup-automation-guide/)
