---
title: "Nginx 反向代理 + SSL 自动续期完全指南"
subtitle: "从零搭建生产级反向代理，Let's Encrypt 免费证书自动续期"
description: "手把手教你用 Nginx 配置反向代理，结合 Certbot 实现 SSL 证书自动申请和续期，让你的自托管服务拥有专业 HTTPS 体验。"
tags: ["nginx", "reverse-proxy", "ssl", "certbot", "lets-encrypt", "vps", "运维"]
categories: ["运维"]
date: "2026-07-19"
image: "/images/posts/nginx-reverse-proxy-ssl-auto-renewal-guide/featured.png"
draft: false
---

## 前言

在 VPS 上自托管各种服务时，**反向代理**是最核心的基础设施之一。通过 Nginx 作为反向代理，你可以：

- 将多个服务绑定到同一个 IP 和端口（80/443）
- 统一管理和配置 HTTPS 证书
- 提供额外的安全层（WAF、限流、隐藏后端端口）
- 改善用户体验（自定义域名访问）

配合 **Certbot + Let's Encrypt**，整个流程可以完全自动化，无需人工干预证书续期。

---

## 一、环境准备

### 1.1 系统要求

```bash
# Ubuntu/Debian 系统
sudo apt update && sudo apt install -y nginx certbot python3-certbot-nginx

# CentOS/RHEL 系统
sudo yum install -y epel-release
sudo yum install -y nginx certbot python3-certbot-nginx
```

### 1.2 域名解析

确保你的域名 A 记录指向 VPS 的公网 IP：

```
@       IN  A   你的VPS公网IP
www     IN  A   你的VPS公网IP
app     IN  CNAME  yourdomain.com
blog    IN  CNAME  yourdomain.com
```

### 1.3 防火墙配置

```bash
# 放行 HTTP (80) 和 HTTPS (443)
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw reload
```

---

## 二、Nginx 基础配置

### 2.1 默认站点配置

Nginx 安装完成后，配置文件位于 `/etc/nginx/`：

```bash
# 查看 Nginx 版本
nginx -v

# 测试配置文件语法
sudo nginx -t

# 启动 Nginx
sudo systemctl start nginx
sudo systemctl enable nginx
```

### 2.2 创建第一个反向代理

假设你要托管一个运行在 `localhost:3000` 的应用：

```nginx
# /etc/nginx/sites-available/myapp
server {
    listen 80;
    server_name app.yourdomain.com;

    # 日志配置
    access_log /var/log/nginx/app-access.log;
    error_log /var/log/nginx/app-error.log;

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        
        # WebSocket 支持
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        
        # 传递真实客户端信息
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # 超时设置
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
}
```

启用站点并重新加载：

```bash
sudo ln -s /etc/nginx/sites-available/myapp /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 2.3 多站点配置示例

一个典型的 VPS 可能同时托管多个服务：

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

## 三、SSL 证书自动续期

### 3.1 使用 Certbot 获取证书

Certbot 会自动修改 Nginx 配置以启用 HTTPS：

```bash
# 为单个域名获取证书
sudo certbot --nginx -d app.yourdomain.com

# 为多个域名一次性获取
sudo certbot --nginx -d app.yourdomain.com -d homepage.yourdomain.com

# 首次运行会提示输入邮箱和同意条款
```

Certbot 执行后，Nginx 配置会自动更新为：

```nginx
server {
    listen 443 ssl http2;
    server_name app.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/app.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/app.yourdomain.com/privkey.pem;

    # 自动添加的安全头
    add_header Strict-Transport-Security "max-age=31536000" always;

    location / {
        proxy_pass http://127.0.0.1:3000;
        # ... 其他配置保持不变
    }
}

# 自动添加的重定向规则
server {
    listen 80;
    server_name app.yourdomain.com;
    return 301 https://$host$request_uri;
}
```

### 3.2 自动续期

Let's Encrypt 证书有效期为 **90 天**，Certbot 已预配置了自动续期：

```bash
# 测试续期（不会真正续期，仅验证流程）
sudo certbot renew --dry-run

# 查看当前的续期计划
systemctl list-timers | grep certbot
```

默认情况下，Certbot 通过 systemd timer 每天检查两次，在证书到期前 30 天内自动续期。

### 3.3 手动续期

如果需要立即续期：

```bash
sudo certbot renew
```

### 3.4 配置 DNS-01 验证（可选）

如果你需要在无法开放 80 端口的情况下获取证书（例如云服务商限制），可以使用 DNS-01 验证：

```bash
# 以 Cloudflare DNS 为例
sudo apt install -y certbot python3-certbot-dns-cloudflare

# 创建认证文件
cat > /etc/letsencrypt/cloudflare.ini << EOF
dns_cloudflare_email = your@email.com
dns_cloudflare_api_key = your-api-key
EOF

chmod 600 /etc/letsencrypt/cloudflare.ini

# 获取证书
sudo certbot certonly \
    --dns-cloudflare \
    --dns-cloudflare-credentials /etc/letsencrypt/cloudflare.ini \
    -d app.yourdomain.com
```

---

## 四、高级安全配置

### 4.1 强化 SSL/TLS 配置

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

### 4.2 速率限制

```nginx
# /etc/nginx/conf.d/rate-limit.conf
limit_req_zone $binary_remote_addr zone=general:10m rate=10r/s;
limit_req_zone $binary_remote_addr zone=login:10m rate=1r/s;

# 在 server block 中使用
location / {
    limit_req zone=general burst=20 nodelay;
    # ...
}

location /login {
    limit_req zone=login burst=5 nodelay;
    # ...
}
```

### 4.3 IP 白名单

```nginx
location /admin {
    allow 192.168.1.0/24;
    allow 10.0.0.0/8;
    deny all;
    
    proxy_pass http://127.0.0.1:3000/admin;
}
```

### 4.4 隐藏 Nginx 版本信息

```nginx
# /etc/nginx/nginx.conf
http {
    server_tokens off;
    # ...
}
```

---

## 五、完整示例：Docker 容器反向代理

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

### 5.2 Nginx Docker 配置

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

## 六、故障排查

### 6.1 常见问题

| 问题 | 原因 | 解决方案 |
|------|------|----------|
| 502 Bad Gateway | 后端服务未运行 | 检查 `systemctl status <service>` |
| 504 Gateway Timeout | 后端响应过慢 | 增加 `proxy_read_timeout` |
| SSL 证书错误 | 证书未正确配置 | `certbot certificates` 查看状态 |
| 403 Forbidden | 权限问题 | 检查文件权限和 SELinux |
| 重定向循环 | HTTPS 配置冲突 | 检查是否有多个 server block 冲突 |

### 6.2 调试命令

```bash
# 测试 Nginx 配置
sudo nginx -t

# 查看 Nginx 错误日志
sudo tail -f /var/log/nginx/error.log

# 查看 Certbot 证书状态
sudo certbot certificates

# 测试 SSL 配置质量
curl -I https://app.yourdomain.com

# 在线 SSL 测试
# 访问 https://www.ssllabs.com/ssltest/
```

---

## 七、最佳实践总结

1. **始终使用 HTTPS** — 即使只是内网服务，也应启用加密
2. **定期更新 Nginx** — 修复安全漏洞
3. **启用 HSTS** — 防止中间人攻击
4. **配置日志轮转** — 避免磁盘被日志占满
5. **备份配置文件** — `cp /etc/nginx/nginx.conf /etc/nginx/nginx.conf.bak`
6. **使用 Fail2Ban** — 保护 SSH 和 Web 服务免受暴力破解
7. **监控磁盘空间** — 证书文件和日志不会自动清理

---

## 结语

通过 Nginx 反向代理 + Certbot 自动续期，你可以轻松构建一个**生产级别**的多服务托管平台。这套方案成本低廉（仅需域名费用）、维护简单（全自动续期）、安全性高（TLS 1.3 + 安全头），是 VPS 自托管的最佳实践组合。

Happy self-hosting! 🚀
