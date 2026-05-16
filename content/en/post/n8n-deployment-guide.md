---
title: "N8N Deployment Guide: Self-Host Workflow Automation on a VPS with Docker"
description: "A step-by-step guide to deploying n8n on your VPS using Docker Compose — self-hosted workflow automation with PostgreSQL, Let's Encrypt SSL, and Nginx reverse proxy"
date: 2026-05-16T10:00:00+08:00
slug: "n8n-deployment-guide"
tags: ["n8n", "Docker", "workflow automation", "VPS deployment", "CI/CD"]
categories: ["Deployment Guides"]
---

## Why N8N?

[N8N](https://n8n.io) is an open-source workflow automation tool, similar to Zapier and Make, but you deploy it on your own server for full data control and privacy.

### N8N Advantages

- 🔓 **Open Source & Free**: Community edition is completely free with no user limits
- 🔒 **Self-Hosted Data**: Sensitive data never leaves your server
- 🔌 **400+ Integrations**: Slack, GitHub, Gmail, Discord, and more
- 🧩 **Visual Builder**: Drag-and-drop editor, no coding required
- 🏢 **Extensible**: Custom nodes and scripts supported

## Prerequisites

- A VPS (2GB RAM recommended)
- Docker and Docker Compose installed
- A domain name (optional, for HTTPS)
- Basic Linux command line knowledge

## Step 1: Install Docker

```bash
# Install Docker
curl -fsSL https://get.docker.com | sh

# Enable Docker on boot
sudo systemctl enable docker
sudo systemctl start docker

# Install Docker Compose plugin
sudo apt-get install docker-compose-plugin -y
```

## Step 2: Create Docker Compose Configuration

```bash
mkdir -p ~/n8n && cd ~/n8n
```

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  n8n:
    image: n8nio/n8n:latest
    container_name: n8n
    restart: unless-stopped
    ports:
      - "5678:5678"
    environment:
      - N8N_HOST=${N8N_HOST}
      - N8N_PORT=5678
      - N8N_PROTOCOL=https
      - WEBHOOK_URL=https://${N8N_HOST}/
      - DB_TYPE=postgresdb
      - DB_POSTGRESDB_HOST=postgres
      - DB_POSTGRESDB_DATABASE=${POSTGRES_DB}
      - DB_POSTGRESDB_USER=${POSTGRES_USER}
      - DB_POSTGRESDB_PASSWORD=${POSTGRES_PASSWORD}
      - N8N_ENCRYPTION_KEY=${N8N_ENCRYPTION_KEY}
    volumes:
      - n8n_data:/home/node/.n8n
    depends_on:
      postgres:
        condition: service_healthy
    networks:
      - n8n_network

  postgres:
    image: postgres:15-alpine
    container_name: n8n-postgres
    restart: unless-stopped
    environment:
      - POSTGRES_USER=${POSTGRES_USER}
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
      - POSTGRES_DB=${POSTGRES_DB}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - n8n_network

volumes:
  n8n_data:
  postgres_data:

networks:
  n8n_network:
    driver: bridge
```

## Step 3: Configure Environment Variables

Create `.env` file:

```bash
cat > .env << 'EOF'
N8N_HOST=n8n.yourdomain.com
N8N_ENCRYPTION_KEY=$(openssl rand -hex 32)
POSTGRES_USER=n8n
POSTGRES_PASSWORD=$(openssl rand -base64 32)
POSTGRES_DB=n8n
EOF
```

> ⚠️ **Security Note**: Always replace `N8N_ENCRYPTION_KEY` and `POSTGRES_PASSWORD` with strong, unique values.

## Step 4: Configure Nginx Reverse Proxy

```nginx
server {
    listen 80;
    server_name n8n.yourdomain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name n8n.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/n8n.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/n8n.yourdomain.com/privkey.pem;

    location / {
        proxy_pass http://localhost:5678;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

## Step 5: Get SSL Certificate

```bash
# Install acme.sh
curl https://get.acme.sh | sh

# Issue certificate
acme.sh --issue -d n8n.yourdomain.com --nginx

# Install certificate
acme.sh --install-cert -d n8n.yourdomain.com \
  --key-file /etc/nginx/ssl/n8n.key \
  --fullchain-file /etc/nginx/ssl/n8n.crt
```

## Step 6: Launch N8N

```bash
cd ~/n8n
docker compose up -d
```

Check the logs:
```bash
docker compose logs -f n8n
```

Visit `https://n8n.yourdomain.com` to complete the initial setup.

## Management Commands

```bash
# View logs
docker compose logs -f n8n

# Restart service
docker compose restart n8n

# Update N8N
docker compose pull n8n
docker compose up -d n8n

# Backup database
docker exec n8n-postgres pg_dump -U n8n n8n > backup_$(date +%Y%m%d).sql
```

## Summary

With Docker Compose, you can deploy n8n in under 10 minutes. Combined with PostgreSQL, Nginx, and Let's Encrypt, you'll have a production-grade workflow automation platform running on your own VPS.

Next, explore n8n's 400+ integration nodes and start building your own automated workflows!
