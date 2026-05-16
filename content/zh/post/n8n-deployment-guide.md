---
title: "N8N 部署指南：在 VPS 上用 Docker 搭建工作流自动化平台"
description: "详细的 N8N 部署教程——使用 Docker Compose 在 VPS 上一键部署 n8n 工作流自动化平台，支持 PostgreSQL、Let's Encrypt SSL 和外部访问配置"
date: 2026-05-16T10:00:00+08:00
slug: "n8n-deployment-guide"
tags: ["n8n", "Docker", "工作流自动化", "VPS部署", "CI/CD"]
categories: ["部署教程"]
aliases: [/zh/post/n8n-deployment-guide/]
---

## 为什么选择 N8N？

[N8N](https://n8n.io) 是一个开源的工作流自动化工具，功能类似于 Zapier 和 Make，但您可以将它部署在自己的服务器上，完全掌控数据和隐私。

### N8N 的优势

- 🔓 **开源免费**：社区版完全免费，无用户数限制
- 🔒 **数据自托管**：敏感数据不出服务器
- 🔌 **400+ 集成**：支持 Slack、GitHub、Gmail、Discord 等主流服务
- 🧩 **可视化编排**：拖拽式编辑，无需写代码
- 🏢 **可扩展**：支持自定义节点和脚本

## 前置要求

- 一台 VPS（推荐 2GB RAM 以上）
- Docker 和 Docker Compose 已安装
- 一个域名（可选，用于配置 HTTPS）
- 基本的 Linux 命令行知识

## 第一步：安装 Docker

如果您的 VPS 尚未安装 Docker，请执行以下命令：

```bash
# 安装 Docker
curl -fsSL https://get.docker.com | sh

# 设置 Docker 开机自启
sudo systemctl enable docker
sudo systemctl start docker

# 安装 Docker Compose 插件
sudo apt-get install docker-compose-plugin -y
```

## 第二步：创建 Docker Compose 配置

创建项目目录并编写 `docker-compose.yml`：

```bash
mkdir -p ~/n8n && cd ~/n8n
```

创建 `docker-compose.yml`：

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

## 第三步：配置环境变量

创建 `.env` 文件：

```bash
cat > .env << 'EOF'
N8N_HOST=n8n.yourdomain.com
N8N_ENCRYPTION_KEY=$(openssl rand -hex 32)
POSTGRES_USER=n8n
POSTGRES_PASSWORD=$(openssl rand -base64 32)
POSTGRES_DB=n8n
EOF
```

> ⚠️ **安全提示**：请务必修改 `N8N_ENCRYPTION_KEY` 和 `POSTGRES_PASSWORD` 为强密码。

## 第四步：配置 Nginx 反向代理（可选但推荐）

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

## 第五步：获取 SSL 证书

```bash
# 安装 acme.sh
curl https://get.acme.sh | sh

# 签发证书
acme.sh --issue -d n8n.yourdomain.com --nginx

# 安装证书
acme.sh --install-cert -d n8n.yourdomain.com \
  --key-file /etc/nginx/ssl/n8n.key \
  --fullchain-file /etc/nginx/ssl/n8n.crt
```

## 第六步：启动 N8N

```bash
cd ~/n8n
docker compose up -d
```

查看启动日志：
```bash
docker compose logs -f n8n
```

首次访问 `https://n8n.yourdomain.com` 进行初始化设置。

## 常用管理命令

```bash
# 查看日志
docker compose logs -f n8n

# 重启服务
docker compose restart n8n

# 更新 N8N
docker compose pull n8n
docker compose up -d n8n

# 备份数据
docker exec n8n-postgres pg_dump -U n8n n8n > backup_$(date +%Y%m%d).sql
```

## 总结

通过 Docker Compose，您可以在 10 分钟内完成 N8N 的部署。搭配 PostgreSQL 作为数据库，Nginx 和 Let's Encrypt 提供 HTTPS 支持，您就拥有了一个生产级的工作流自动化平台。

下一步，您可以探索 N8N 的 400+ 集成节点，创建您自己的自动化工作流！
