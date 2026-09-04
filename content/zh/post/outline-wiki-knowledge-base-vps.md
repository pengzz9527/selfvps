---
title: "VPS 上搭建内部 Wiki 与知识库：Outline 团队协作文档平台完整部署指南"
description: "使用 Outline 自建团队知识库 —— 支持 Markdown、实时协作、全文搜索、SSO 集成。从零部署到生产环境的完整 Docker Compose 指南，替代 Notion 和 Confluence。"
date: 2026-09-04T10:00:00+08:00
lastmod: 2026-09-04T10:00:00+08:00
slug: "outline-wiki-knowledge-base-vps"
tags: ["Outline", "Wiki", "知识库", "Docker", "自托管", "团队协作", "文档管理", "Nextcloud"]
categories: ["部署教程"]
draft: false
image: /images/posts/outline-wiki-knowledge-base-vps/featured.png
aliases: [/zh/post/outline-wiki-knowledge-base-vps/]
---

## 为什么自建 Wiki？

在团队协作为核心的工作场景中，知识库是信息流转的基础设施。市面上有 Notion、Confluence、GitBook 等成熟产品，但它们各自存在明显痛点：

| 方案 | 主要痛点 |
|------|---------|
| **Notion** | 数据存储在第三方，私有化困难，国内访问慢，免费版功能受限 |
| **Confluence** | Atlassian 生态绑定，价格昂贵，部署复杂，需要 Jira 配合 |
| **GitBook** | 免费版文档数量有限制，企业版价格高 |
| **自建 WordPress + 插件** | 体验割裂，协作功能弱，维护成本高 |

**Outline** 是近年来最受欢迎的自托管 Wiki 解决方案之一。它由 Stack Overflow 前工程师团队开发，具有现代化的 UI 设计、流畅的 Markdown 编辑体验、强大的搜索能力，以及灵活的集成选项。更重要的是，**所有数据完全掌握在自己手中**。

### Outline 核心特性

- **Markdown 优先**：原生支持 Markdown 语法，编辑器体验接近 Notion
- **实时协作**：多人同时编辑同一文档，光标实时可见
- **全文搜索**：基于 Typesense 的毫秒级搜索，支持中文分词
- **权限管理**：基于空间的精细权限控制，支持团队分组
- **SSO 集成**：支持 Google、GitHub、OIDC、LDAP 等多种认证方式
- **API 完备**：RESTful API + WebSocket，便于二次开发
- **导出功能**：支持 PDF、Markdown、HTML 多种格式导出
- **主题自定义**：支持自定义品牌色和 Logo

## 环境需求

在开始之前，请确保你的 VPS 满足以下要求：

| 组件 | 最低配置 | 推荐配置 |
|------|---------|---------|
| **CPU** | 2 核 | 4 核 |
| **内存** | 4GB | 8GB |
| **磁盘** | 20GB SSD | 50GB+ NVMe |
| **带宽** | 100Mbps | 500Mbps+ |
| **操作系统** | Ubuntu 22.04/24.04 LTS | Debian 12 / Ubuntu 24.04 |
| **域名** | 建议配置（用于 SSO 回调） | `wiki.yourdomain.com` |

## 方案一：Docker Compose 一键部署（推荐）

### 第 1 步：准备工作

```bash
# 更新系统
sudo apt update && sudo apt upgrade -y

# 安装 Docker 和 Docker Compose
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
sudo apt install -y docker-compose-plugin

# 验证安装
docker --version
docker compose version
```

### 第 2 步：创建项目目录

```bash
mkdir -p ~/outline-wiki/{data,postgres,data/redis}
cd ~/outline-wiki
```

### 第 3 步：生成密钥

```bash
# 生成 SECRET_KEY_BASE（用于加密 session 和 token）
openssl rand -hex 64

# 生成 JWT_SECRET（用于签名 JWT token）
openssl rand -hex 32

# 记录上面输出的两个值，稍后使用
```

### 第 4 步：创建 .env 配置文件

```bash
cat > .env << 'EOF'
# ===== Outline 配置 =====
OUTLINE_URL=https://wiki.yourdomain.com
NODE_ENV=production

# ===== 数据库配置 (PostgreSQL) =====
DB_HOST=postgres
DB_NAME=outline
DB_USER=outline
DB_PASS=your-strong-password-here
DB_PORT=5432

# ===== Redis 配置 =====
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASS=your-redis-password-here

# ===== 安全密钥（替换为上面生成的值）=====
SECRET_KEY_BASE=your-64-char-hex-key-here
JWT_SECRET=your-32-char-hex-key-here

# ===== 文件存储配置 =====
FILE_STORAGE=local
FILE_STORAGE_LOCAL_ROOT=/var/lib/outline/uploads

# ===== 搜索配置 (Typesense) =====
SEARCH_PROVIDER=typesense
TYPESENSE_HOST=typesense
TYPESENSE_PORT=8108
TYPESENSE_PROTOCOL=http
TYPESENSE_API_KEY=your-typesense-api-key

# ===== 认证配置（选择一种）=====
# Google OAuth
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret

# 或者 GitHub OAuth
# GITHUB_CLIENT_ID=your-github-client-id
# GITHUB_CLIENT_SECRET=your-github-client-secret

# 或者 OIDC（通用 SSO）
# OIDC_CLIENT_ID=your-oidc-client-id
# OIDC_CLIENT_SECRET=your-oidc-client-secret
# OIDC_ISSUER=https://your-identity-provider.com

# ===== 邮件配置（用于密码重置和通知）=====
SMTP_HOST=smtp.yourdomain.com
SMTP_PORT=587
SMTP_SECURE=false
SMTP_USERNAME=noreply@yourdomain.com
SMTP_PASSWORD=your-smtp-password
SMTP_FROM_ADDRESS=noreply@yourdomain.com

# ===== 管理员邮箱（首次启动时用于创建管理员账号）=====
ADMIN_EMAIL=admin@yourdomain.com
EOF
```

> **注意**：将 `wiki.yourdomain.com` 替换为你的实际域名，并填入真实的密钥和认证信息。

### 第 5 步：创建 docker-compose.yml

```bash
cat > docker-compose.yml << 'EOF'
version: '3.8'

services:
  # ===== Outline 主应用 =====
  outline:
    image: outlinewiki/outline:latest
    container_name: outline
    restart: unless-stopped
    env_file:
      - .env
    environment:
      - OUTLINE_LOG_LEVEL=info
      - OUTLINE_RATE_LIMIT_WEBHOOKS=500:15m
      - OUTLINE_RATE_LIMIT_API=2000:1m
    volumes:
      - ./uploads:/var/lib/outline/uploads
    ports:
      - "3000:3000"
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_started
      typesense:
        condition: service_started
    networks:
      - outline-net

  # ===== PostgreSQL 数据库 =====
  postgres:
    image: postgres:16-alpine
    container_name: outline-postgres
    restart: unless-stopped
    environment:
      - POSTGRES_DB=outline
      - POSTGRES_USER=outline
      - POSTGRES_PASSWORD=${DB_PASS}
    volumes:
      - postgres-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U outline -d outline"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - outline-net

  # ===== Redis 缓存 =====
  redis:
    image: redis:7-alpine
    container_name: outline-redis
    restart: unless-stopped
    command: redis-server --requirepass ${REDIS_PASS} --maxmemory 256mb --maxmemory-policy allkeys-lru
    volumes:
      - redis-data:/data
    networks:
      - outline-net

  # ===== Typesense 搜索引擎 =====
  typesense:
    image: typesense/typesense:27.0.rc31
    container_name: outline-typesense
    restart: unless-stopped
    command: >
      ./typesense-server
      --data-dir /data
      --api-key=${TYPESENSE_API_KEY}
      --enable-cors
    volumes:
      - typesense-data:/data
    networks:
      - outline-net

volumes:
  postgres-data:
  redis-data:
  typesense-data:

networks:
  outline-net:
    driver: bridge
EOF
```

### 第 6 步：启动服务

```bash
# 首次启动（会自动执行数据库迁移）
docker compose up -d

# 查看启动日志
docker compose logs -f outline
```

首次启动时，Outline 会自动创建数据库表结构并初始化配置。看到类似以下的输出表示启动成功：

```
outline    | info: Server is ready to accept connections! 🎉
```

### 第 7 步：创建管理员账号

访问 `http://你的VPS-IP:3000`，使用 `.env` 中配置的 `ADMIN_EMAIL` 注册第一个管理员账号。

## 方案二：Nginx 反向代理配置

生产环境推荐使用 Nginx 作为反向代理，配置 HTTPS 和缓存优化。

### 第 1 步：安装 Nginx 和 Certbot

```bash
sudo apt install -y nginx certbot python3-certbot-nginx
```

### 第 2 步：获取 SSL 证书

```bash
# 确保域名 A 记录已指向 VPS IP
sudo certbot certonly --nginx -d wiki.yourdomain.com
```

### 第 3 步：创建 Nginx 配置

```bash
sudo tee /etc/nginx/sites-available/outline << 'EOF'
server {
    listen 80;
    server_name wiki.yourdomain.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name wiki.yourdomain.com;

    # SSL 证书
    ssl_certificate     /etc/letsencrypt/live/wiki.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/wiki.yourdomain.com/privkey.pem;
    ssl_trusted_certificate /etc/letsencrypt/live/wiki.yourdomain.com/chain.pem;

    # SSL 优化
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 1d;
    ssl_session_tickets off;

    # 安全头部
    add_header X-Frame-Options SAMEORIGIN always;
    add_header X-Content-Type-Options nosniff always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy strict-origin-when-cross-origin always;

    # 上传文件大小限制（Outline 默认支持大文件）
    client_max_body_size 100m;

    # WebSocket 支持
    map $http_upgrade $connection_upgrade {
        default upgrade;
        ''      close;
    }

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;

        # WebSocket 代理
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;

        # 真实客户端信息
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # 超时设置（WebSocket 需要较长超时）
        proxy_connect_timeout 7d;
        proxy_send_timeout 7d;
        proxy_read_timeout 7d;
    }

    # 静态资源缓存
    location ~* \.(jpg|jpeg|png|gif|ico|css|js|svg|woff2?)$ {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
}
EOF

# 启用站点并重启 Nginx
sudo ln -sf /etc/nginx/sites-available/outline /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

## 认证方式配置

### Google OAuth 配置

1. 访问 [Google Cloud Console](https://console.cloud.google.com/)
2. 创建项目 → API 与服务 → 凭据
3. 创建 OAuth 2.0 客户端 ID
4. 添加授权回调 URL：`https://wiki.yourdomain.com/auth/google/callback`
5. 将 Client ID 和 Secret 填入 `.env`

### GitHub OAuth 配置

1. 访问 [GitHub Settings → Developer settings → OAuth Apps](https://github.com/settings/developers)
2. 新建 OAuth App
3. 设置 Authorization callback URL：`https://wiki.yourdomain.com/auth/github/callback`
4. 将 Client ID 和 Secret 填入 `.env`

### OIDC（通用 SSO）配置

适用于 Keycloak、Auth0、Azure AD 等支持 OIDC 的身份提供商：

```bash
# 在 .env 中添加
OIDC_CLIENT_ID=your-oidc-client-id
OIDC_CLIENT_SECRET=your-oidc-client-secret
OIDC_ISSUER=https://your-identity-provider.com/.well-known/openid-configuration
```

## 高级配置

### 自定义品牌与主题

Outline 支持通过环境变量自定义品牌：

```bash
# .env 中添加
BRANDING_LOGO_URL=https://wiki.yourdomain.com/assets/logo.png
BRANDING_COLOR=#6366f1
BRANDING_NAME=My Team Wiki
BRANDING_DESCRIPTION=团队内部知识管理平台
```

### 调整文件上传限制

```bash
# 在 outline 服务的 environment 中添加
- UPLOAD_MAX_FILE_SIZE=104857600  # 100MB
- ALLOWED_FILE_EXTENSIONS=jpg,png,gif,pdf,doc,docx,xls,xlsx,zip
```

### 启用 LDAP 认证（企业版）

Outline 支持通过插件或社区版本集成 LDAP：

```bash
# 需要额外安装 ldap-auth 插件
# 或在 .env 中配置
LDAP_HOST=ldap://your-ldap-server
LDAP_PORT=389
LDAP_BIND_DN=cn=admin,dc=example,dc=com
LDAP_BIND_PASSWORD=your-ldap-password
LDAP_SEARCH_BASE=ou=users,dc=example,dc=com
LDAP_USER_FILTER=(uid=%{login})
```

### 配置对象存储（S3 兼容）

生产环境建议使用 S3 兼容的对象存储替代本地存储：

```bash
# .env 中修改
FILE_STORAGE=s3
AWS_REGION=us-east-1
AWS_S3_BUCKET=outline-uploads
AWS_ACCESS_KEY_ID=your-aws-access-key
AWS_SECRET_ACCESS_KEY=your-aws-secret-key
AWS_S3_ENDPOINT=https://minio.yourdomain.com
```

### 定时备份策略

```bash
# 创建备份脚本 ~/outline-wiki/backup.sh
#!/bin/bash
set -e

BACKUP_DIR="/backup/outline-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_DIR"

# 备份数据库
docker exec outline-postgres pg_dump -U outline outline > "$BACKUP_DIR/database.sql"

# 备份上传文件
docker cp outline:/var/lib/outline/uploads "$BACKUP_DIR/uploads"

# 备份配置文件
cp .env "$BACKUP_DIR/env"
cp docker-compose.yml "$BACKUP_DIR/docker-compose.yml"

# 压缩
tar czf "$BACKUP_DIR.tar.gz" "$BACKUP_DIR"
rm -rf "$BACKUP_DIR"

# 保留最近 7 天的备份
find /backup -name "outline-*.tar.gz" -mtime +7 -delete

echo "Backup completed: $BACKUP_DIR.tar.gz"
```

```bash
# 添加到 crontab（每天凌晨 3 点备份）
crontab -e
# 添加：0 3 * * * /root/outline-wiki/backup.sh
```

## 数据迁移与升级

### 升级 Outline 版本

```bash
cd ~/outline-wiki
docker compose pull
docker compose up -d
```

Outline 的数据库迁移是自动的，升级过程无需额外操作。

### 从其他 Wiki 迁移数据

Outline 支持从以下格式导入：

- **Markdown 文件**：批量上传 `.md` 文件到指定空间
- **Notion 导出**：导出为 Markdown 后批量导入
- **Confluence 导出**：导出为 XML 后转换为 Markdown
- **GitBook 导出**：导出 ZIP 后解压导入

```bash
# 使用 Outline API 批量导入
curl -X POST https://wiki.yourdomain.com/api/documents/import \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  -F "file=@document.md" \
  -F "parentId=DOCUMENT_ID"
```

## 常见问题排查

### Q1: 启动后页面无法访问

```bash
# 检查容器状态
docker compose ps

# 查看 Outline 日志
docker compose logs outline

# 检查端口占用
sudo ss -tlnp | grep 3000
```

常见原因：
- PostgreSQL 未就绪（等待 healthcheck 通过）
- 环境变量配置错误（检查 `.env` 文件）
- 防火墙阻挡了 3000 端口

### Q2: 文件上传失败

```bash
# 检查 uploads 目录权限
sudo chown -R 999:999 ~/outline-wiki/uploads

# 检查磁盘空间
df -h
```

### Q3: 搜索功能不可用

```bash
# 检查 Typesense 状态
docker compose logs typesense

# 重启 Typesense
docker compose restart typesense

# 重建搜索索引
curl -X POST https://wiki.yourdomain.com/api/search/reindex \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"
```

### Q4: WebSocket 连接不稳定

确保 Nginx 配置中包含 WebSocket 支持（见上文 Nginx 配置），并检查代理超时设置。

### Q5: 中文搜索不准确

Typesense 默认不支持中文分词。可以使用支持中文的 TypeScript 配置：

```bash
# 在 docker-compose.yml 的 typesense 服务中添加
command: >
  ./typesense-server
  --data-dir /data
  --api-key=${TYPESENSE_API_KEY}
  --enable-cors
  --search-index-field-count=5000
```

## 性能优化建议

### 1. 调整 PostgreSQL 配置

```bash
# 在 postgres 容器中优化配置
# 挂载自定义配置到 /var/lib/postgresql/data/postgresql.conf
shared_buffers = 256MB          # 根据内存调整
effective_cache_size = 768MB
work_mem = 4MB
maintenance_work_mem = 64MB
max_connections = 100
```

### 2. Redis 内存优化

```bash
# maxmemory 已设置为 256MB，可根据实际需求调整
# 使用 allkeys-lru 策略自动淘汰不常用数据
```

### 3. 启用 Gzip 压缩

在 Nginx 配置中添加：

```nginx
gzip on;
gzip_vary on;
gzip_proxied any;
gzip_comp_level 6;
gzip_types text/plain text/css text/xml application/json application/javascript application/rss+xml application/atom+xml image/svg+xml;
```

### 4. CDN 加速静态资源

如果团队分布在不同地区，可以考虑将上传的附件通过 CDN 加速分发。

## 总结

Outline 是目前最优秀的自托管 Wiki 解决方案之一，它完美结合了现代化的 UI 设计、强大的协作功能和完全的数据自主权。

**核心要点回顾：**

1. **部署简单**：Docker Compose 一键部署，5 个服务即可完成
2. **体验优秀**：类 Notion 的编辑体验，流畅的实时协作
3. **搜索强大**：基于 Typesense 的毫秒级全文搜索
4. **安全可控**：所有数据存储在自有 VPS 上
5. **集成灵活**：支持多种 SSO 认证方式
6. **扩展性强**：完善的 API 支持二次开发

**成本估算：**

| 项目 | 费用 |
|------|------|
| VPS（4核8G） | $20-40/月 |
| 域名 | $10-15/年 |
| SSL 证书 | 免费（Let's Encrypt） |
| **总计** | **~$30/月** |

相比 Notion 商业版（$10/用户/月）或 Confluence（$8.75/用户/月），自建 Outline 在团队规模超过 5 人时即可回本。

**下一步行动：**
- [ ] 准备 VPS 并配置域名 DNS
- [ ] 按照本文步骤部署 Outline
- [ ] 配置 SSO 认证方式
- [ ] 设置定时备份策略
- [ ] 邀请团队成员开始使用
