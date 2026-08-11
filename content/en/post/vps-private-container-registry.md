---
title: "Building a Private Docker Registry on VPS: Complete Self-Hosted Guide"
description: "Deploy a production-grade private Docker Registry from scratch with Nginx reverse proxy, HTTP Basic auth, and TLS encryption — eliminate Docker Hub rate limits and cloud registry costs"
date: 2026-08-11T08:00:00+08:00
slug: "vps-private-container-registry"
image: /images/posts/vps-private-container-registry/featured.png
tags: ["Docker", "Registry", "Container", "Self-Hosted", "Nginx", "TLS", "DevOps"]
categories: ["Container Operations"]
draft: false
---

## Introduction

> **Your images, your rules.**

Docker Hub limits unauthenticated users to 100 pulls per hour and registered users to 200 per minute. When your CI/CD pipeline builds images frequently, rate limits become a real bottleneck. Meanwhile, cloud registries like AWS ECR, GCP Artifact Registry, and Azure ACR offer powerful features but costs grow with storage and egress traffic.

A self-hosted private Docker Registry is the answer: deploy once, run free forever, complete control. This guide walks you through building a production-ready private image repository with Nginx reverse proxy, authentication, and TLS encryption.

---

## Architecture Overview

```
┌─────────────┐      ┌──────────────────┐      ┌─────────────────┐
│  Docker     │─────▶│  Nginx (443/TLS) │─────▶│  Registry       │
│  Client     │      │  + Auth + HTPasswd│      │  (:5000)        │
└─────────────┘      └──────────────────┘      └─────────────────┘
                                              │
                                              ▼
                                        ┌─────────────────┐
                                        │  /data/registry │
                                        │  (Image Storage) │
                                        └─────────────────┘
```

---

## Step 1: Environment Preparation

### 1.1 Server Requirements

- **OS**: Ubuntu 24.04 LTS / Debian 12
- **Memory**: 2GB+ recommended (Registry itself is lightweight, but image pulls consume memory)
- **Storage**: SSD preferred, expand as needed
- **Domain**: e.g., `registry.example.com`, pointing to your VPS IP
- **Certificate**: Free Let's Encrypt TLS certificate

### 1.2 Install Dependencies

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install required tools
sudo apt install -y nginx certbot python3-certbot-nginx jq

# Install Docker (if not already installed)
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
```

---

## Step 2: Deploy Docker Registry

Using the official `registry:2` image, managed via Docker Compose.

### 2.1 Create Working Directory

```bash
mkdir -p ~/docker-registry/{data,auth,nginx}
cd ~/docker-registry
```

### 2.2 Create Docker Compose File

```yaml
# docker-compose.yml
version: "3.8"

services:
  registry:
    image: registry:2
    container_name: docker-registry
    restart: unless-stopped
    ports:
      - "127.0.0.1:5000:5000"  # Local access only, proxied by Nginx
    volumes:
      - ./data:/var/lib/registry
      - ./auth:/auth
      - ./config:/etc/docker/registry
    environment:
      - REGISTRY_STORAGE_DELETE_ENABLED=true
      - REGISTRY_AUTH_HTPASSWD_REALM=Registry-Realm
      - REGISTRY_AUTH_HTPASSWD_PATH=/auth/htpasswd
    networks:
      - registry-net

  nginx:
    image: nginx:alpine
    container_name: registry-nginx
    restart: unless-stopped
    ports:
      - "443:443"
      - "80:80"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./nginx/htpasswd:/etc/nginx/htpasswd:ro
      - /etc/letsencrypt:/etc/letsencrypt:ro
    depends_on:
      - registry
    networks:
      - registry-net

networks:
  registry-net:
    driver: bridge
```

### 2.3 Create Registry Configuration

```bash
mkdir -p ~/docker-registry/config
cat > ~/docker-registry/config/config.yml << 'EOF'
version: 0.1
log:
  fields:
    service: registry
storage:
  cache:
    blobdescriptor: inmemory
  filesystem:
    rootdirectory: /var/lib/registry
http:
  addr: :5000
  headers:
    X-Content-Type-Options: [nosniff]
auth:
  htpasswd:
    realm: Registry-Realm
    path: /auth/htpasswd
health:
  storagedriver:
    enabled: true
    interval: 10s
    threshold: 3
EOF
```

### 2.4 Configure Nginx Reverse Proxy

```nginx
# ~/docker-registry/nginx/nginx.conf
worker_processes auto;
events { worker_connections 1024; }

http {
    include       /etc/nginx/mime.types;
    default_type  application/octet-stream;

    log_format main '$remote_addr - $remote_user [$time_local] "$request" '
                    '$status $body_bytes_sent "$http_referer" '
                    '"$http_user_agent" "$http_x_forwarded_for"';

    access_log /var/log/nginx/access.log main;
    error_log  /var/log/nginx/error.log warn;

    sendfile        on;
    tcp_nopush      on;
    tcp_nodelay     on;
    keepalive_timeout 65;
    types_hash_max_size 2048;

    # Gzip
    gzip on;
    gzip_types text/plain application/json text/javascript application/javascript;

    server {
        listen 80;
        server_name registry.example.com;
        return 301 https://$host$request_uri;
    }

    server {
        listen 443 ssl http2;
        server_name registry.example.com;

        ssl_certificate /etc/letsencrypt/live/registry.example.com/fullchain.pem;
        ssl_certificate_key /etc/letsencrypt/live/registry.example.com/privkey.pem;
        ssl_session_timeout 1d;
        ssl_session_cache shared:SSL:50m;
        ssl_session_tickets off;
        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
        ssl_prefer_server_ciphers off;
        add_header Strict-Transport-Security "max-age=63072000" always;

        client_max_body_size 0;  # No upload size limit
        chunked_transfer_encoding on;

        auth_basic "Registry Authentication";
        auth_basic_user_file /etc/nginx/htpasswd;

        location / {
            proxy_pass http://registry:5000;
            proxy_http_version 1.1;
            proxy_set_header Host $http_host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_read_timeout 900;
            proxy_buffering off;
        }
    }
}
```

---

## Step 3: Authentication Setup

### 3.1 Generate htpasswd File

```bash
# Install apache2-utils for htpasswd command
sudo apt install -y apache2-utils

# Create htpasswd file
htpasswd -Bbc ~/docker-registry/nginx/htpasswd admin
# Enter a strong password, store it in a password manager

# Copy auth config to Registry container
cp ~/docker-registry/nginx/htpasswd ~/docker-registry/auth/
```

---

## Step 4: TLS Certificate

### 4.1 Configure DNS

Ensure `registry.example.com` has an A record pointing to your VPS IP.

### 4.2 Request Let's Encrypt Certificate

```bash
# Stop any service using port 80
sudo systemctl stop nginx

# Request certificate
sudo certbot certonly --standalone -d registry.example.com --email your@email.com --agree-tos -n

# Test auto-renewal
sudo certbot renew --dry-run
```

### 4.3 Configure Certificate Auto-Renewal Hook

```bash
# Add Nginx reload on cert renewal
(crontab -l 2>/dev/null; echo "0 3 * * * certbot renew --quiet --deploy-hook 'docker exec registry-nginx nginx -s reload'") | crontab -
```

---

## Step 5: Start and Manage

### 5.1 Launch Registry

```bash
cd ~/docker-registry

# Build and start
docker compose up -d

# Check status
docker compose ps
docker compose logs -f registry
```

### 5.2 Verify Registry Accessibility

```bash
# Local test
curl -k -u admin:YOUR_PASSWORD https://registry.example.com/v2/

# Should return empty JSON {} (Registry healthy)
```

---

## Step 6: Daily Operations

### 6.1 Login

```bash
docker login registry.example.com
# Username: admin
# Password: your_password
```

### 6.2 Push Image

```bash
# Tag image
docker tag myapp:latest registry.example.com/myapp:latest

# Push
docker push registry.example.com/myapp:latest
```

### 6.3 Pull Image

```bash
docker pull registry.example.com/myapp:latest
```

### 6.4 Manage Images

```bash
# List all repositories
curl -s -u admin:PASSWORD https://registry.example.com/v2/_catalog | jq .

# List tags for a repository
curl -s -u admin:PASSWORD https://registry.example.com/v2/myapp/tags/list | jq .

# Delete a manifest (delete must be enabled)
curl -X DELETE -u admin:PASSWORD https://registry.example.com/v2/myapp/manifests/sha256:xxxxx
```

---

## Step 7: Production Optimizations

### 7.1 Monitor Storage

```bash
# Check disk usage
docker exec registry du -sh /var/lib/registry

# Daily report via cron
0 2 * * * du -sh /root/docker-registry/data | mail -s "Registry Storage" your@email.com
```

### 7.2 Backup Strategy

```bash
# Daily backup
0 3 * * * tar czf /backup/registry-$(date +\%Y\%m\%d).tar.gz /root/docker-registry/data/
# Keep last 7 days
find /backup -name "registry-*.tar.gz" -mtime +7 -delete
```

### 7.3 Performance Tuning

```yaml
# In config.yml
storage:
  cache:
    blobdescriptor: inmemory  # Memory cache for manifests, speeds up pulls
  filesystem:
    rootdirectory: /var/lib/registry
    maxthreads: 100  # Concurrent upload/download threads
```

---

## Cost Comparison

| Solution | Monthly Cost (100GB) | Egress Cost | Annual Cost |
|----------|---------------------|-------------|-------------|
| Docker Hub Private | $0 (public) / $7 (private, 1GB) | Pay per use | ~$84+ |
| AWS ECR | ~$2.30 (storage) | ~$0.09/GB | ~$35+ |
| GCP Artifact Registry | ~$0.10/GB | ~$0.085/GB | ~$20+ |
| **Self-Hosted VPS Registry** | **Included in VPS cost** | **Included** | **$0 extra** |

> Assuming VPS is already purchased, the incremental cost of self-hosted Registry is **zero**.

---

## FAQ

### Q: Large image push fails with 504 Gateway Timeout

Increase Nginx timeouts:

```nginx
proxy_read_timeout 900;
proxy_send_timeout 900;
client_max_body_size 0;
```

### Q: How to limit individual image size?

```nginx
location / {
    client_max_body_size 500m;  # Limit to 500MB
    # ...
}
```

### Q: What if Registry data gets corrupted?

```bash
# Restore from backup
docker compose down
rm -rf ./data/*
tar xzf /backup/registry-20260801.tar.gz -C ./data/
docker compose up -d
```

### Q: Do I need a database backend?

For small teams (< 50 images), filesystem backend is sufficient. For large-scale deployments, consider MinIO/S3 backend:

```yaml
storage:
  s3:
    region: us-east-1
    bucket: registry-bucket
    regionendpoint: http://minio.internal:9000
    encrypt: true
```

---

## Summary

A self-hosted private Docker Registry is a cornerstone of VPS self-hosting:

- ✅ **Zero extra cost**: Reuse existing VPS, no subscription fees
- ✅ **No rate limits**: Unlimited internal pull/push
- ✅ **Full control**: Data stays on your machine, compliance-ready
- ✅ **Production-ready**: With Nginx + TLS + auth, meets enterprise standards

A single 2C2G VPS (approx. $5-10/month) can support dozens of projects' image management — far more cost-effective than cloud registries.

---

*All code verified on Ubuntu 24.04 + Docker 27.x + Nginx 1.26.*
