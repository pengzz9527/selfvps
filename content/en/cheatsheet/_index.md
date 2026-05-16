---
title: "Self-Host Cheatsheet"
description: "A handy self-hosting cheatsheet — Docker commands, Nginx configs, and Linux ops commands all on one page"
date: 2026-05-16T10:00:00+08:00
slug: "cheatsheet"
menu:
  main:
    weight: 55
    identifier: cheatsheet
---

## Self-Host Cheatsheet

A quick reference for common DevOps and self-hosting commands.

### Docker Basics

```bash
# List running containers
docker ps

# List all containers
docker ps -a

# Start/stop a container
docker start <container>
docker stop <container>

# View container logs
docker logs -f <container>

# Enter a container shell
docker exec -it <container> /bin/bash

# Pull an image
docker pull <image>:<tag>

# Clean up unused resources
docker system prune -a
```

### Docker Compose

```bash
# Start all services
docker compose up -d

# View service logs
docker compose logs -f

# Rebuild and start
docker compose up -d --build

# Stop and remove containers
docker compose down

# List running services
docker compose ps
```

### Nginx Configuration

```nginx
# HTTP to HTTPS redirect
server {
    listen 80;
    server_name example.com;
    return 301 https://$server_name$request_uri;
}

# Reverse proxy
server {
    listen 443 ssl;
    server_name example.com;
    
    location / {
        proxy_pass http://localhost:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### Linux Ops

```bash
# Check disk usage
df -h

# Check memory usage
free -h

# Check system load
htop  # or top

# Find large files
du -sh /* 2>/dev/null | sort -rh | head -10

# Firewall management (UFW)
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable
ufw status verbose

# SSL certificates (acme.sh)
acme.sh --issue -d example.com --nginx
acme.sh --renew -d example.com --force
```
