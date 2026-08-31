---
title: "Self-Hosted VPS Remote Development Environment: Code-Server + Jupyter + Git Full Setup"
description: "Say goodbye to local environment setup headaches. Deploy a unified VS Code + Jupyter + Git remote development platform on your VPS, code and run experiments from any device, anywhere, with zero local hardware dependency"
date: 2026-08-31T10:00:00+08:00
lastmod: 2026-08-31T10:00:00+08:00
slug: "vps-remote-dev-environment"
image: /images/posts/vps-remote-dev-environment/featured.png
tags: ["VPS", "Remote Development", "Code-Server", "Jupyter", "Git", "Docker", "DevOps", "Self-Hosted"]
categories: ["Developer Tools"]
aliases: [/en/post/vps-remote-dev-environment/]
draft: false
---

## Introduction

Do you experience any of these scenarios?

- Switched to a new computer and spent half a day just setting up the dev environment
- Home computer is too weak to run AI models or compile large projects
- Want to code on a tablet/iPad, but realize it's impossible
- Collaborating with teammates, but their environment differs from yours: "It works on my machine"
- Midnight emergency fix needed, but your home computer is shut down

All these problems share one solution: **move your development environment to a VPS**.

This article walks you through building a complete **VPS remote development environment**: VS Code in the browser (Code-Server) + JupyterLab + Git, behind Nginx reverse proxy with HTTPS encryption and authentication. Code, run experiments, and manage your projects from any device, any browser, seamlessly.

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    Your Any Device                              │
│   Mac / Windows / Linux / iPad / Phone  →  Browser             │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTPS
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    VPS (Ubuntu 24.04)                           │
│                                                                 │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────────┐   │
│  │   Nginx      │──▶│  Code-Server │   │  JupyterLab      │   │
│  │  :443 HTTPS  │   │  :8080       │   │  :8888           │   │
│  │  Reverse     │   │  VS Code     │   │  Notebook Env    │   │
│  │  Proxy       │   │  in Browser  │   │                  │   │
│  └──────┬───────┘   └──────┬───────┘   └────────┬─────────┘   │
│         │                  │                     │             │
│         │                  └────────┬────────────┘             │
│         │                           ▼                          │
│         │                  ┌─────────────────┐                 │
│         │                  │   Docker        │                 │
│         │                  │  Git Repos      │                 │
│         │                  │  Python/Node    │                 │
│         │                  │  Toolchains     │                 │
│         │                  └─────────────────┘                 │
│                                                                 │
│  Domain: dev.yourdomain.com → Nginx Routes                      │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. Prerequisites

### 2.1 Minimum VPS Specs

| Use Case | Minimum | Recommended |
|----------|---------|-------------|
| Code-Server basic dev | 2 CPU / 4GB RAM / 40GB Disk | 4 CPU / 8GB RAM / 100GB SSD |
| With Jupyter + AI projects | 4 CPU / 8GB RAM / 80GB Disk | 8 CPU / 16GB RAM / 200GB NVMe |
| Multi-container + GPU | 8 CPU / 32GB RAM / 500GB SSD | 16 CPU / 64GB RAM + GPU |

### 2.2 System Initialization

```bash
# Update the system
sudo apt update && sudo apt upgrade -y

# Install base tools
sudo apt install -y curl wget git unzip htop net-tools

# Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# Install Nginx
sudo apt install -y nginx certbot python3-certbot-nginx
```

### 2.3 Domain DNS

Point `dev.yourdomain.com` to your VPS IP:

```bash
# DNS A record
dev.yourdomain.com  →  Your VPS IP
```

---

## 3. Deploy Code-Server (VS Code in Browser)

### 3.1 Docker Deployment

```bash
# Create working directories
mkdir -p ~/dev-environment/code-server/{data,projects}
cd ~/dev-environment

# Pull and start Code-Server
docker run -d \
  --name code-server \
  --restart unless-stopped \
  -p 127.0.0.1:8080:8080 \
  -v ~/dev-environment/projects:/home/coder/projects \
  -v ~/dev-environment/code-server/data:/home/coder/.local/share/code-server \
  -e PASSWORD=YourStrongPassword \
  -e TZ=Asia/Shanghai \
  -e PROXY_DOMAIN=dev.yourdomain.com \
  ghcr.io/coder/code-server:latest
```

### 3.2 Verify Deployment

```bash
# Check container status
docker ps | grep code-server

# Test locally via SSH tunnel
ssh -L 8080:localhost:8080 your-vps
# Then open http://localhost:8080 in your browser
```

### 3.3 Recommended Extensions

After logging into Code-Server, install these from the marketplace:

| Extension | Purpose |
|-----------|---------|
| Chinese Language Pack | Chinese UI |
| Remote - SSH | SSH remote development |
| Python | Python language support |
| Go | Go language support |
| Prettier | Code formatting |
| ESLint | JavaScript/TypeScript linting |
| GitLens | Git enhancement |
| Project Manager | Multi-project management |
| Material Icon Theme | File icon美化 |
| Error Lens | In-line error hints |

---

## 4. Deploy JupyterLab

### 4.1 One-Command Docker Deployment

```bash
mkdir -p ~/dev-environment/jupyter/{notebooks,projects}
cd ~/dev-environment

docker run -d \
  --name jupyter \
  --restart unless-stopped \
  -p 127.0.0.1:8888:8888 \
  -v ~/dev-environment/projects:/home/jovyan/work \
  -v ~/dev-environment/jupyter/notebooks:/home/jovyan/notebooks \
  -e PASSWORD=YourJupyterPassword \
  -e TZ=Asia/Shanghai \
  jupyter/base-notebook:latest
```

### 4.2 Choose the Right Image

```bash
# Basic (minimal)
jupyter/base-notebook

# Python + Scientific computing
jupyter/scipy-notebook

# AI/ML complete stack
jupyter/pyspark-notebook

# GPU support (requires nvidia-container-toolkit)
jupyter/torch-notebook
```

### 4.3 Install Extra Python Packages

```bash
# Enter the container
docker exec -it jupyter bash

# Install common packages
pip install numpy pandas matplotlib seaborn scikit-learn
pip install torch torchvision torchaudio
pip install transformers datasets accelerate
pip install langchain langgraph llama-index

# Save as custom image
docker commit jupyter jupyter:custom
```

---

## 5. Nginx Reverse Proxy Configuration

### 5.1 Get SSL Certificate

```bash
sudo certbot --nginx -d dev.yourdomain.com --non-interactive --agree-tos -m your@email.com
```

### 5.2 Nginx Configuration

```bash
sudo tee /etc/nginx/sites-available/dev.yourdomain.com << 'EOF'
server {
    listen 443 ssl http2;
    server_name dev.yourdomain.com;

    ssl_certificate     /etc/letsencrypt/live/dev.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/dev.yourdomain.com/privkey.pem;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Strict-Transport-Security "max-age=31536000" always;

    # Code-Server
    location / {
        proxy_pass                         http://127.0.0.1:8080;
        proxy_http_version                 1.1;
        proxy_set_header Upgrade           $http_upgrade;
        proxy_set_header Connection        upgrade;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass                 $http_upgrade;
        proxy_read_timeout                  86400;
    }

    # JupyterLab
    location /jupyter/ {
        proxy_pass                         http://127.0.0.1:8888/jupyter/;
        proxy_http_version                 1.1;
        proxy_set_header Upgrade           $http_upgrade;
        proxy_set_header Connection        upgrade;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout                  86400;
        proxy_set_header X-Frame-Options   "";
    }

    # Static assets
    location ~* \.(css|js|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
        proxy_pass http://127.0.0.1:8080;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
}

# HTTP → HTTPS redirect
server {
    listen 80;
    server_name dev.yourdomain.com;
    return 301 https://$host$request_uri;
}
EOF

sudo ln -sf /etc/nginx/sites-available/dev.yourdomain.com /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

### 5.3 Auto-Renew Certificates

```bash
# Test renewal
sudo certbot renew --dry-run

# Verify timer is active
sudo systemctl status certbot.timer
```

---

## 6. Git Integration & Code Management

### 6.1 Configure Git

```bash
# Inside Code-Server terminal, set global config
git config --global user.name "Your Name"
git config --global user.email "you@email.com"
git config --global core.editor "code --wait"
git config --global init.defaultBranch main

# Generate SSH key
ssh-keygen -t ed25519 -C "your@email.com"
cat ~/.ssh/id_ed25519.pub  # Add to GitHub/GitLab
```

### 6.2 Project Directory Structure

```
~/projects/
├── web-app/              # Web project
│   ├── src/
│   ├── package.json
│   └── README.md
├── ml-experiments/       # AI/ML project
│   ├── notebooks/
│   ├── models/
│   └── requirements.txt
├── scripts/              # Utility scripts
└── personal/             # Personal notes
    └── obsidian-vault/
```

### 6.3 Code Sync Strategies

```bash
# Option 1: Git push to remote (recommended)
cd ~/projects/my-project
git init
git remote add origin git@github.com:username/my-project.git
git add .
git commit -m "Initial commit"
git push -u origin main

# Option 2: rsync sync to local machine
rsync -avz --progress coder@your-vps:~/projects/my-project/ ./my-project/

# Option 3: syncthing for bidirectional sync
# See: https://syncthing.net/
```

---

## 7. Security Hardening

### 7.1 Firewall Configuration

```bash
# Only open necessary ports
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp      # SSH
sudo ufw allow 80/tcp      # HTTP (for redirect)
sudo ufw allow 443/tcp     # HTTPS
sudo ufw enable
```

### 7.2 Fail2ban Protection

```bash
sudo apt install -y fail2ban

sudo tee /etc/fail2ban/jail.local << 'EOF'
[sshd]
enabled = true
port = ssh
filter = sshd
logpath = /var/log/auth.log
maxretry = 3
bantime = 3600

[code-server]
enabled = true
port = http,https
filter = http-auth
logpath = /home/coder/.local/share/code-server/logs
maxretry = 5
bantime = 3600
EOF

sudo systemctl enable fail2ban
sudo systemctl restart fail2ban
```

### 7.3 Backup Configuration

```bash
# Regular backup of dev environment
sudo tar czf /backup/dev-environment-$(date +%Y%m%d).tar.gz \
  ~/dev-environment/ \
  ~/.ssh/ \
  ~/.gitconfig

# Upload to object storage (optional)
aws s3 cp /backup/dev-environment-$(date +%Y%m%d).tar.gz \
  s3://your-backup-bucket/dev-environment/
```

---

## 8. Advanced: Docker Compose One-Command Start

Combine all services into one `docker-compose.yml`:

```yaml
# ~/dev-environment/docker-compose.yml
version: "3.8"

services:
  code-server:
    image: ghcr.io/coder/code-server:latest
    container_name: code-server
    restart: unless-stopped
    ports:
      - "127.0.0.1:8080:8080"
    volumes:
      - ./projects:/home/coder/projects
      - ./code-server/data:/home/coder/.local/share/code-server
    environment:
      - PASSWORD=${CS_PASSWORD}
      - TZ=Asia/Shanghai
      - PROXY_DOMAIN=dev.yourdomain.com
    networks:
      - dev-net

  jupyter:
    image: jupyter/scipy-notebook:latest
    container_name: jupyter
    restart: unless-stopped
    ports:
      - "127.0.0.1:8888:8888"
    volumes:
      - ./projects:/home/jovyan/work
      - ./jupyter/notebooks:/home/jovyan/notebooks
    environment:
      - PASSWORD=${JPY_PASSWORD}
      - TZ=Asia/Shanghai
    networks:
      - dev-net

networks:
  dev-net:
    driver: bridge
```

```bash
# Create .env file
cat > ~/dev-environment/.env << EOF
CS_PASSWORD=YourCodeServerPassword
JPY_PASSWORD=YourJupyterPassword
EOF

# Start everything
cd ~/dev-environment
docker compose up -d

# View logs
docker compose logs -f
```

---

## 9. Real-World Use Cases

### 9.1 Code on iPad

```
iPad Safari → dev.yourdomain.com → Code-Server
                ↓
         Full VS Code experience
         Keyboard + mouse (or touch)
         Code auto-saved to Git
```

### 9.2 Run AI Experiments Without Using Home Power

```bash
# Train on VPS, monitor from home computer
cd ~/projects/ml-experiments
python train.py --epochs 100  # Running on your VPS
# Monitor training curves live via Jupyter
```

### 9.3 Instant Team Collaboration

```bash
# Log in from any device → identical environment
git clone https://github.com/team/project.git
code project/  # Open directly in browser
# Code auto-saves, never lose your work
```

---

## 10. FAQ

### Q1: Code-Server feels slow, what to do?

```bash
# Check bandwidth usage
iftop -i eth0

# Disable animations in Code-Server
# Settings → Appearance → Reduce Animation
```

### Q2: How to share the dev environment with team members?

```bash
# Option 1: Each person gets their own container, shared projects directory
# Option 2: Use DevContainer standard (GitHub Codespaces-style)
# Option 3: Add Nginx basic auth to restrict access
```

### Q3: Running out of disk space?

```bash
# Clean up unused Docker resources
docker system df          # Check usage
docker system prune -a    # Clean up (use with caution)
docker volume prune       # Clean anonymous volumes

# Move projects to larger disk
mv /home/coder/projects /mnt/large-disk/projects
ln -s /mnt/large-disk/projects /home/coder/projects
```

### Q4: Forgot the password?

```bash
# Code-Server password is in the config
cat ~/dev-environment/code-server/data/User/settings.json
# Or reset directly
docker exec code-server passwd coder
```

---

## Summary

Through this article, you've learned:

| Capability | Tool |
|------------|------|
| VS Code in Browser | Code-Server |
| Interactive Programming | JupyterLab |
| Code Version Control | Git + GitHub |
| Secure Access | Nginx + HTTPS + Fail2ban |
| One-Click Deploy | Docker Compose |

**Key Benefits:**
- 🎯 **Consistent Environment**: Same setup on any device
- 💰 **Cost Savings**: Cheap VPS replaces high-end local machine
- 🔒 **Data Security**: Code stays on your server
- 🚀 **Productivity Boost**: Start coding anytime, unbound by hardware
- 🌍 **Mobile Office**: Code from phone/iPad too

Visit `https://dev.yourdomain.com` and start your cloud development journey!
