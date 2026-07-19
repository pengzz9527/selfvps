---
title: "Nginx Reverse Proxy & SSL Auto-Renewal Complete Guide"
subtitle: "Build a Production-Grade Reverse Proxy with Free Let's Encrypt Certificates"
description: "Step-by-step guide to configuring Nginx as a reverse proxy with Certbot for automatic SSL certificate management — giving your self-hosted services professional HTTPS experience."
tags: ["nginx", "reverse-proxy", "ssl", "certbot", "lets-encrypt", "vps", "devops"]
categories: ["DevOps"]
date: "2026-07-19"
image: "/images/posts/nginx-reverse-proxy-ssl-auto-renewal-guide/featured.png"
draft: false
---

## Introduction

When self-hosting services on a VPS, a **reverse proxy** is one of the most critical pieces of infrastructure. Using Nginx as a reverse proxy enables you to:

- Host multiple services on the same IP and port (80/443)
- Centrally manage and configure HTTPS certificates
- Add a security layer (WAF, rate limiting, hide backend ports)
- Improve user experience with custom domain names

Combined with **Certbot + Let's Encrypt**, the entire process can be fully automated — no manual certificate renewal required.

---

## 1. Environment Setup

### 1.1 System Requirements

```bash
# Ubuntu/Debian
sudo apt update && sudo apt install -y nginx certbot python3-certbot-nginx

# CentOS/RHEL
sudo yum install -y epel-release
sudo yum install -y nginx certbot python3-certbot-nginx
```

### 1.2 DNS Configuration

Ensure your domain's A record points to your VPS public IP:

```
@       IN  A   YourVPSPublicIP
www     IN  A   YourVPSPublicIP
app     IN  CNAME  yourdomain.com
blog    IN  CNAME  yourdomain.com
```

### 1.3 Firewall Configuration

```bash
# Allow HTTP (80) and HTTPS (443)
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw reload
```

---

## 2. Nginx Basic Configuration

### 2.1 Default Site Setup

After installation, Nginx configuration files are located in `/etc/nginx/`:

```bash
# Check Nginx version
nginx -v

# Test configuration syntax
sudo nginx -t

# Start and enable Nginx
sudo systemctl start nginx
sudo systemctl enable nginx
```

### 2.2 Creating Your First Reverse Proxy

Assuming you want to proxy an application running on `localhost:3000`:

```nginx
# /etc/nginx/sites-available/myapp
server {
    listen 80;
    server_name app.yourdomain.com;

    # Logging
    access_log /var/log/nginx/app-access.log;
    error_log /var/log/nginx/app-error.log;

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        
        # WebSocket support
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        
        # Pass real client information
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Timeout settings
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
}
```

Enable the site and reload:

```bash
sudo ln -s /etc/nginx/sites-available/myapp /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 2.3 Multi-Site Configuration Example

A typical VPS may host multiple services simultaneously:

```nginx
# /etc/nginx/sites-available/homepage
server {
    listen 80;
    server_name homepage.yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}

# /etc/nginx/sites-available/blog
server {
    listen 80;
    server_name blog.yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:4000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}

# /etc/nginx/sites-available/api
server {
    listen 80;
    server_name api.yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

---

## 3. SSL Certificate & Auto-Renewal

### 3.1 Getting Certificates with Certbot

Certbot will automatically modify your Nginx configuration to enable HTTPS:

```bash
# Get certificate for a single domain
sudo certbot --nginx -d app.yourdomain.com

# Get certificate for multiple domains at once
sudo certbot --nginx -d app.yourdomain.com -d homepage.yourdomain.com

# First run will prompt for email and terms agreement
```

After Certbot runs, your Nginx config is updated to:

```nginx
server {
    listen 443 ssl http2;
    server_name app.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/app.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/app.yourdomain.com/privkey.pem;

    # Automatically added security headers
    add_header Strict-Transport-Security "max-age=31536000" always;

    location / {
        proxy_pass http://127.0.0.1:3000;
        # ... other config remains unchanged
    }
}

# Automatically added redirect rule
server {
    listen 80;
    server_name app.yourdomain.com;
    return 301 https://$host$request_uri;
}
```

### 3.2 Automatic Renewal

Let's Encrypt certificates are valid for **90 days**. Certbot pre-configures automatic renewal:

```bash
# Test renewal (won't actually renew, just validates the process)
sudo certbot renew --dry-run

# View current renewal schedule
systemctl list-timers | grep certbot
```

By default, Certbot checks twice daily via systemd timer and auto-renews certificates within 30 days of expiration.

### 3.3 Manual Renewal

If you need to renew immediately:

```bash
sudo certbot renew
```

### 3.4 DNS-01 Validation (Optional)

If you cannot open port 80 (e.g., cloud provider restrictions), use DNS-01 validation:

```bash
# Using Cloudflare DNS as an example
sudo apt install -y certbot python3-certbot-dns-cloudflare

# Create credentials file
cat > /etc/letsencrypt/cloudflare.ini << EOF
dns_cloudflare_email = your@email.com
dns_cloudflare_api_key = your-api-key
EOF

chmod 600 /etc/letsencrypt/cloudflare.ini

# Get certificate
sudo certbot certonly \
    --dns-cloudflare \
    --dns-cloudflare-credentials /etc/letsencrypt/cloudflare.ini \
    -d app.yourdomain.com
```

---

## 4. Advanced Security Configuration

### 4.1 Hardened SSL/TLS Settings

```nginx
# /etc/nginx/snippets/ssl-params.conf
ssl_protocols TLSv1.2 TLSv1.3;
ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
ssl_prefer_server_ciphers off;
ssl_session_cache shared:SSL:10m;
ssl_session_timeout 10m;
ssl_session_tickets off;

# OCSP Stapling
ssl_stapling on;
ssl_stapling_verify on;
resolver 8.8.8.8 8.8.4.4 valid=300s;
resolver_timeout 5s;
```

### 4.2 Rate Limiting

```nginx
# /etc/nginx/conf.d/rate-limit.conf
limit_req_zone $binary_remote_addr zone=general:10m rate=10r/s;
limit_req_zone $binary_remote_addr zone=login:10m rate=1r/s;

# Use in server block
location / {
    limit_req zone=general burst=20 nodelay;
}

location /login {
    limit_req zone=login burst=5 nodelay;
}
```

### 4.3 IP Whitelisting

```nginx
location /admin {
    allow 192.168.1.0/24;
    allow 10.0.0.0/8;
    deny all;
    
    proxy_pass http://127.0.0.1:3000/admin;
}
```

### 4.4 Hide Nginx Version

```nginx
# /etc/nginx/nginx.conf
http {
    server_tokens off;
}
```

---

## 5. Complete Example: Docker Container Reverse Proxy

### 5.1 docker-compose.yml

```yaml
version: '3.8'

services:
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/conf.d:/etc/nginx/conf.d
      - ./nginx/certs:/etc/nginx/certs
      - ./nginx/logs:/var/log/nginx
    depends_on:
      - app
      - homepage
    restart: unless-stopped

  app:
    image: your-app:latest
    ports:
      - "3000:3000"
    environment:
      - NODE_ENV=production
    restart: unless-stopped

  homepage:
    image: gethomepage/homepage:latest
    ports:
      - "3000:3000"
    restart: unless-stopped
```

### 5.2 Nginx Docker Configuration

```nginx
# /etc/nginx/conf.d/default.conf
upstream app_backend {
    server app:3000;
}

upstream homepage_backend {
    server homepage:3000;
}

server {
    listen 80;
    server_name app.yourdomain.com;
    
    location / {
        proxy_pass http://app_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

server {
    listen 80;
    server_name homepage.yourdomain.com;
    
    location / {
        proxy_pass http://homepage_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

## 6. Troubleshooting

### 6.1 Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| 502 Bad Gateway | Backend service not running | Check `systemctl status <service>` |
| 504 Gateway Timeout | Backend response too slow | Increase `proxy_read_timeout` |
| SSL Certificate Error | Certificate misconfigured | Run `certbot certificates` |
| 403 Forbidden | Permission issues | Check file permissions and SELinux |
| Redirect Loop | HTTPS config conflict | Check for conflicting server blocks |

### 6.2 Debugging Commands

```bash
# Test Nginx configuration
sudo nginx -t

# View Nginx error logs
sudo tail -f /var/log/nginx/error.log

# Check Certbot certificate status
sudo certbot certificates

# Test SSL configuration quality
curl -I https://app.yourdomain.com

# Online SSL test
# Visit https://www.ssllabs.com/ssltest/
```

---

## 7. Best Practices Summary

1. **Always use HTTPS** — even for internal services, encryption is important
2. **Keep Nginx updated** — patch security vulnerabilities promptly
3. **Enable HSTS** — prevent man-in-the-middle attacks
4. **Configure log rotation** — avoid disk space exhaustion from logs
5. **Backup configuration files** — `cp /etc/nginx/nginx.conf /etc/nginx/nginx.conf.bak`
6. **Use Fail2Ban** — protect SSH and web services from brute-force attacks
7. **Monitor disk space** — certificate files and logs need cleanup

---

## Conclusion

With Nginx reverse proxy + Certbot automatic renewal, you can easily build a **production-grade** multi-service hosting platform. This solution is cost-effective (only domain costs), easy to maintain (fully automated renewal), and highly secure (TLS 1.3 + security headers) — making it the best practice combination for VPS self-hosting.

Happy self-hosting! 🚀
