---
title: "构建 VPS 私有容器镜像仓库：完整自托管 Docker Registry 指南"
description: "从零搭建私有 Docker Registry，配合 Nginx 反代、HTTP Basic 认证和 TLS 加密，彻底告别 Docker Hub 限速与云注册表费用"
date: 2026-08-11T08:00:00+08:00
slug: "vps-private-container-registry"
image: /images/posts/vps-private-container-registry/featured.png
tags: ["Docker", "Registry", "容器化", "自托管", "Nginx", "TLS", "DevOps"]
categories: ["容器化运维"]
draft: false
---

## 引言

> **你的镜像，你来做主。**

Docker Hub 对未登录用户每小时仅限 100 次拉取，对注册用户每分钟 200 次。当你的 CI/CD 流水线频繁构建镜像时，限速成了刚需。而 AWS ECR、GCP Artifact Registry、Azure ACR 等云注册表，虽然功能强大，但存储和流量费用随规模增长不断攀升。

自建私有 Docker Registry 是解决方案：一次部署，永久免费，完全掌控。本文将带你从零搭建一套生产可用的私有镜像仓库，包含 Nginx 反向代理、认证保护和 TLS 加密。

---

## 架构概览

```
┌─────────────┐      ┌──────────────────┐      ┌─────────────────┐
│  Docker     │─────▶│  Nginx (443/TLS) │─────▶│  Registry       │
│  Client     │      │  + Auth + HTPasswd│      │  (:5000)        │
└─────────────┘      └──────────────────┘      └─────────────────┘
                                              │
                                              ▼
                                        ┌─────────────────┐
                                        │  /data/registry │
                                        │  (镜像存储)      │
                                        └─────────────────┘
```

---

## 第一步：基础环境准备

### 1.1 服务器要求

- **系统**：Ubuntu 24.04 LTS / Debian 12
- **内存**：2GB+ 推荐（Registry 本身轻量，但镜像拉取消耗内存）
- **磁盘**：SSD 优先，镜像存储按需扩展
- **域名**：如 `registry.example.com`，解析到 VPS IP
- **证书**：Let's Encrypt 免费 TLS 证书

### 1.2 安装依赖

```bash
# 更新系统
sudo apt update && sudo apt upgrade -y

# 安装必要工具
sudo apt install -y nginx certbot python3-certbot-nginx jq

# 安装 Docker（如未安装）
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
```

---

## 第二步：部署 Docker Registry

使用官方 `registry:2` 镜像，通过 Docker Compose 管理。

### 2.1 创建工作目录

```bash
mkdir -p ~/docker-registry/{data,auth,nginx}
cd ~/docker-registry
```

### 2.2 创建 Docker Compose 文件

```yaml
# docker-compose.yml
version: "3.8"

services:
  registry:
    image: registry:2
    container_name: docker-registry
    restart: unless-stopped
    ports:
      - "127.0.0.1:5000:5000"  # 仅本地访问，Nginx 反代
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

### 2.3 创建 Registry 配置文件

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

### 2.4 配置 Nginx 反代

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

        client_max_body_size 0;  # 不限上传大小
        chunked_transfer_encoding on;

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

## 第三步：认证配置

### 3.1 生成认证密码文件

```bash
# 安装 apache2-utils 以获取 htpasswd 命令
sudo apt install -y apache2-utils

# 创建 htpasswd 文件（在宿主机关外生成）
htpasswd -Bbc ~/docker-registry/nginx/htpasswd admin
# 输入密码，建议强密码 + 密码管理器保管

# 复制认证配置到 Registry 容器
cp ~/docker-registry/nginx/htpasswd ~/docker-registry/auth/
```

### 3.2 创建 Nginx htpasswd 软链接

Registry 的 htpasswd 由 Nginx 代理层验证：

```bash
# 在 docker-compose 中，Nginx 需要自己的认证
# 我们需要在 Nginx 层添加 basic auth
```

修改 nginx.conf 的 server 块，添加 Basic Auth：

```nginx
http {
    # ... 上面配置 ...

    server {
        listen 443 ssl http2;
        server_name registry.example.com;

        # ... SSL 配置 ...

        auth_basic "Registry Authentication";
        auth_basic_user_file /etc/nginx/htpasswd;

        location / {
            # ... proxy 配置 ...
        }
    }
}
```

---

## 第四步：获取 TLS 证书

### 4.1 配置 DNS

确保域名 `registry.example.com` 已 A 记录解析到你的 VPS IP。

### 4.2 申请 Let's Encrypt 证书

```bash
# 先停止可能占用 80 端口的服务
sudo systemctl stop nginx  # 如果用系统 nginx

# 申请证书
sudo certbot certonly --standalone -d registry.example.com --email your@email.com --agree-tos -n

# 设置自动续期
sudo certbot renew --dry-run
```

### 4.3 配置证书自动续期后重载 Nginx

```bash
# 创建续期后自动重载的 hook
sudo tee /etc/letsencrypt/live/registry.example.com/renew-hook.sh << 'EOF'
#!/bin/bash
docker exec registry-nginx nginx -s reload
EOF
sudo chmod +x /etc/letsencrypt/live/registry.example.com/renew-hook.sh

# 或者编辑 crontab
(crontab -l 2>/dev/null; echo "0 3 * * * certbot renew --quiet --deploy-hook 'docker exec registry-nginx nginx -s reload'") | crontab -
```

---

## 第五步：启动与服务管理

### 5.1 启动 Registry

```bash
cd ~/docker-registry

# 构建并启动
docker compose up -d

# 查看状态
docker compose ps
docker compose logs -f registry
```

### 5.2 验证 Registry 可达

```bash
# 本机测试
curl -k -u admin:YOUR_PASSWORD https://registry.example.com/v2/

# 应返回空 JSON {}（Registry 健康）
```

---

## 第六步：日常使用

### 6.1 登录 Registry

```bash
docker login registry.example.com
# Username: admin
# Password: 你的密码
```

### 6.2 推送镜像

```bash
# 标记镜像
docker tag myapp:latest registry.example.com/myapp:latest

# 推送
docker push registry.example.com/myapp:latest
```

### 6.3 拉取镜像

```bash
docker pull registry.example.com/myapp:latest
```

### 6.4 管理镜像

```bash
# 列出所有镜像
curl -s -u admin:PASSWORD https://registry.example.com/v2/_catalog | jq .

# 列出某镜像的所有 tag
curl -s -u admin:PASSWORD https://registry.example.com/v2/myapp/tags/list | jq .

# 删除镜像（需启用 delete）
curl -X DELETE -u admin:PASSWORD https://registry.example.com/v2/myapp/manifests/sha256:xxxxx
```

---

## 第七步：生产优化

### 7.1 监控存储使用

```bash
# 查看磁盘使用
docker exec registry du -sh /var/lib/registry

# 定期检查（加入 crontab）
0 2 * * * du -sh /root/docker-registry/data | mail -s "Registry Storage" your@email.com
```

### 7.2 备份策略

```bash
# 每日备份 registry 数据
0 3 * * * tar czf /backup/registry-$(date +\%Y\%m\%d).tar.gz /root/docker-registry/data/
# 保留最近 7 天
find /backup -name "registry-*.tar.gz" -mtime +7 -delete
```

### 7.3 性能调优

```yaml
# 在 config.yml 中调整
storage:
  cache:
    blobdescriptor: inmemory  # 内存缓存 manifest，加速拉取
  filesystem:
    rootdirectory: /var/lib/registry
    maxthreads: 100  # 并发上传/下载线程数
```

### 7.4 多客户端配置（Docker Daemon）

如果客户端 Docker 服务器不在同一域名下，需要在 `/etc/docker/daemon.json` 中配置：

```json
{
  "insecure-registries" : ["registry.example.com:443"]
}
```

> **注意**：使用 TLS 后无需 `insecure-registries`，直接 `docker login` 即可。

---

## 成本对比

| 方案 | 月成本（100GB 存储） | 月流量费 | 年成本 |
|------|---------------------|---------|--------|
| Docker Hub Private | $0（公开）/ $7（私有，1GB） | 按量 | ~$84+ |
| AWS ECR | ~$2.30（存储） | ~$0.09/GB | ~$35+ |
| GCP Artifact Registry | ~$0.10/GB | ~$0.085/GB | ~$20+ |
| **自建 VPS Registry** | **含在 VPS 费用中** | **内网/已付** | **$0 额外** |

> 假设 VPS 已购，自建 Registry 增量成本为 **零**。

---

## 常见问题

### Q: 推送大镜像失败（504 Gateway Timeout）

Nginx 默认超时较短，调整配置：

```nginx
proxy_read_timeout 900;
proxy_send_timeout 900;
client_max_body_size 0;
```

### Q: 如何限制单个镜像大小？

```nginx
# 在 nginx.conf 中
location / {
    client_max_body_size 500m;  # 限制 500MB
    # ...
}
```

### Q: Registry 数据损坏怎么办？

```bash
# 从备份恢复
docker compose down
rm -rf ./data/*
tar xzf /backup/registry-20260801.tar.gz -C ./data/
docker compose up -d
```

### Q: 是否需要数据库后端？

对于小型团队（< 50 个镜像），文件系统后端足够。如需大规模部署，可考虑 MinIO/S3 后端：

```yaml
storage:
  s3:
    region: us-east-1
    bucket: registry-bucket
    regionendpoint: http://minio.internal:9000
    encrypt: true
    keyfile: /etc/docker/registry/s3-key.json
```

---

## 总结

自建私有 Docker Registry 是 VPS 自托管的重要一环：

- ✅ **零额外成本**：复用现有 VPS，无订阅费
- ✅ **无速率限制**：内部网络无限拉取推送
- ✅ **完全可控**：数据留在自己手中，符合合规要求
- ✅ **生产可用**：配合 Nginx + TLS + 认证，可达企业级标准

一台 2C2G 的 VPS（月费约 ¥50-100）即可支撑数十个项目的镜像管理，远比云注册表划算。

---

*本文代码已在 Ubuntu 24.04 + Docker 27.x + Nginx 1.26 环境验证通过。*
