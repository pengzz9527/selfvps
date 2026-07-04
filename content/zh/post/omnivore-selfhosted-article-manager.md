---
title: "在 VPS 上自建 Omnivore：打造你的个人文章收藏与标注系统"
description: "Omnivore 是一款开源的 Read-it-later 工具，支持全文搜索、高亮标注和 AI 摘要。本文教你如何在 VPS 上通过 Docker 一键部署 Omnivore，告别 Pocket 和 Instapaper 的订阅费用。"
date: 2026-07-04T10:00:00+08:00
lastmod: 2026-07-04T10:00:00+08:00
slug: "omnivore-selfhosted-article-manager"
tags: ["Omnivore", "自托管", "Read-it-later", "Docker", "全文搜索", "AI摘要", "笔记管理"]
categories: ["自托管工具"]
draft: false
image: "/images/posts/omnivore-selfhosted-article-manager/featured.png"
---

## 📖 为什么你需要 Omnivore？

在这个信息爆炸的时代，我们每天都会遇到大量值得阅读但没时间立即消化的文章。Pocket、Instapaper 等 Read-it-later 服务虽然好用，但它们有一个共同问题：**你的数据不属于你**。一旦服务关闭或涨价，你将失去积累多年的阅读清单和标注。

**Omnivore** 正是为了解决这个问题而生。它是一个完全开源的 Read-it-later 解决方案，提供：

- 🔍 **全文搜索** — 在你收藏的所有文章中快速查找内容
- 🎨 **高亮与标注** — 像做笔记一样标记重要段落
- 🤖 **AI 摘要** — 内置 AI 功能，一键生成文章摘要
- 📱 **多端同步** — Web、iOS、Android、Chrome 扩展全覆盖
- 🏠 **完全自托管** — 数据掌握在自己手中

---

## 🏗 系统架构

Omnivore 由以下几个核心组件构成：

```
┌─────────────────────────────────────────────┐
│              Omnivore Architecture            │
├──────────┬──────────┬───────────┬────────────┤
│  Frontend │  API     │  Worker   │  Storage   │
│  (Next.js)│ (GraphQL)│ (Queue)   │            │
├──────────┼──────────┼───────────┼────────────┤
│  Web/Mobile/App          │  PostgreSQL + S3  │
└─────────────────────────────────────────────┘
```

| 组件 | 作用 | 最低配置 |
|------|------|----------|
| **API Server** | 处理 GraphQL 请求 | 1 vCPU, 512MB RAM |
| **Worker** | 异步保存/处理文章 | 1 vCPU, 512MB RAM |
| **PostgreSQL** | 存储用户数据、标注、标签 | 1 vCPU, 512MB RAM |
| **S3 兼容存储** | 存储文章快照和图片 | 任意 S3 服务 |

---

## 🚀 一键部署（Docker Compose）

这是最简单的部署方式，适合大多数个人用户。

### 步骤 1：创建项目目录

```bash
mkdir -p ~/omnivore && cd ~/omnivore
```

### 步骤 2：创建 `.env` 文件

```bash
cat > .env << 'EOF'
# PostgreSQL 配置
POSTGRES_USER=omnivore
POSTGRES_PASSWORD=CHANGE_ME_SECURE_PASSWORD
POSTGRES_DB=omnivore
POSTGRES_HOST=db
POSTGRES_PORT=5432

# S3 存储配置（使用 MinIO 作为本地 S3）
S3_ENDPOINT=http://minio:9000
S3_REGION=us-east-1
S3_BUCKET=omnivore
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin

# Omnivore API 密钥（用于身份验证）
HASH_SALT=CHANGE_ME_SECURE_HASH_SALT
API_SECRET=CHANGE_ME_SECURE_API_SECRET

# 前端配置
NEXTAUTH_URL=http://localhost:3000
NEXT_PUBLIC_APP_PROTOCOL=http
NEXT_PUBLIC_APP_HOST=localhost
NEXT_PUBLIC_APP_PORT=3000

# MinIO 控制台（可选，用于管理存储）
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin
EOF
```

> ⚠️ **重要**：请修改所有 `CHANGE_ME_*` 占位符为随机强密码。

### 步骤 3：创建 `docker-compose.yml`

```yaml
version: '3.8'

services:
  # PostgreSQL 数据库
  db:
    image: postgres:16-alpine
    container_name: omnivore-db
    restart: unless-stopped
    env_file: .env
    volumes:
      - pg_data:/var/lib/postgresql/data
    networks:
      - omnivore

  # MinIO 对象存储
  minio:
    image: minio/minio:latest
    container_name: omnivore-minio
    restart: unless-stopped
    command: server /data --console-address ":9001"
    env_file: .env
    volumes:
      - minio_data:/data
    networks:
      - omnivore
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/live"]
      interval: 30s
      timeout: 10s
      retries: 3

  # Omnivore API Server
  api:
    image: ghcr.io/omnivore-app/omnivore/api:latest
    container_name: omnivore-api
    restart: unless-stopped
    env_file: .env
    ports:
      - "4000:4000"
    depends_on:
      db:
        condition: service_started
      minio:
        condition: service_healthy
    networks:
      - omnivore

  # Omnivore Worker（异步任务处理）
  worker:
    image: ghcr.io/omnivore-app/omnivore/worker:latest
    container_name: omnivore-worker
    restart: unless-stopped
    env_file: .env
    depends_on:
      db:
        condition: service_started
      minio:
        condition: service_healthy
    networks:
      - omnivore

  # Omnivore Next.js 前端
  frontend:
    image: ghcr.io/omnivore-app/omnivore/frontend:latest
    container_name: omnivore-frontend
    restart: unless-stopped
    env_file: .env
    ports:
      - "3000:3000"
    depends_on:
      - api
    networks:
      - omnivore

volumes:
  pg_data:
  minio_data:

networks:
  omnivore:
    driver: bridge
```

### 步骤 4：启动服务

```bash
docker compose up -d
```

等待几分钟，所有服务启动后访问 `http://your-vps-ip:3000` 即可看到 Omnivore 界面。

---

## 🌐 配置反向代理（推荐）

直接通过端口访问不安全也不方便。推荐使用 **Caddy** 或 **Nginx** 配置 HTTPS 反代。

### 使用 Caddy（最简单）

```caddy
omnivore.yourdomain.com {
    reverse_proxy localhost:3000
    encode gzip
    
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Content-Type-Options "nosniff"
    }
}
```

### 使用 Nginx

```nginx
server {
    listen 443 ssl http2;
    server_name omnivore.yourdomain.com;

    ssl_certificate     /etc/letsencrypt/live/omnivore.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/omnivore.yourdomain.com/privkey.pem;

    # 安全头
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;

    # WebSocket 支持（Chrome 扩展需要）
    map $http_upgrade $connection_upgrade {
        default upgrade;
        ''      close;
    }

    location / {
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        client_max_body_size 50m;
    }
}
```

---

## 📲 客户端配置

Omnivore 提供多种客户端，部署完成后需要配置 API 地址：

### Chrome 扩展

1. 安装 [Omnivore Chrome Extension](https://chromewebstore.google.com/detail/omnivore)
2. 点击扩展图标 → Settings
3. 将 API URL 改为 `http://your-vps-ip:4000/api`
4. 将 App URL 改为 `http://your-vps-ip:3000`

### iOS / Android

1. 从 App Store / Play Store 安装 Omnivore
2. 登录时选择 "Self-hosted" 选项
3. 输入你的 VPS 地址和 API 密钥

### API 调用

```bash
# 获取文章列表
curl -X POST http://localhost:4000/api \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_SECRET" \
  -d '{"query": "{ viewer { highlights { id title } } }"}'
```

---

## 💡 核心功能详解

### 1. 全文搜索

Omnivore 使用 Elasticsearch 风格的全文索引。收藏的文章会被自动提取正文并建立索引：

```graphql
{
  search(first: 20, query: "machine learning tutorial") {
    edges {
      node {
        title
        slug
        description
      }
    }
  }
}
```

### 2. 高亮与标注

像阅读 PDF 一样，你可以在任何收藏的文章中高亮文本并添加备注：

- **黄色高亮** — 重点内容
- **绿色高亮** — 有用参考
- **红色高亮** — 待跟进
- **备注** — 添加个人笔记

### 3. AI 摘要

Omnivore 内置 AI 功能，可以一键生成文章摘要。对于长文章，这能帮你快速判断是否值得细读：

> 💡 **省钱提示**：自托管意味着你可以搭配本地 Ollama 使用，完全免费地获得 AI 摘要功能，无需支付任何 API 费用。

### 4. 标签与文件夹管理

支持多级标签和文件夹组织，让你的数百篇文章井井有条：

```
📁 技术文章
  ├── 🏷 AI/ML
  ├── 🏷 DevOps
  └── 🏷 网络安全

📁 设计灵感
  ├── 🏷 UI/UX
  └── 🏷 排版设计

📁 待读
```

---

## 📊 成本对比

| 方案 | 月费 | 数据存储 | AI 功能 | 广告 |
|------|------|----------|---------|------|
| **Omnivore 自托管** | ~$4.15 (Hetzner) | 无限 | 免费(Ollama) | ❌ 无 |
| Pocket Premium | $4.99 | 有限 | ❌ 无 | ❌ 无 |
| Instapaper Premium | $3.99 | 有限 | ❌ 无 | ❌ 无 |
| Readwise Reader | $7.00 | 有限 | ✅ 有 | ❌ 无 |

**年度节省**：相比 Readwise Reader（$84/年），自托管 Omnivore 每年可节省 **$79.80+**，而且数据完全属于你。

---

## 🔧 高级配置

### 使用外部 PostgreSQL

如果你的 VPS 已经运行了 PostgreSQL，可以直接复用：

```yaml
# .env 覆盖
POSTGRES_HOST=your-existing-db-host
POSTGRES_PORT=5432
POSTGRES_USER=omnivore_user
POSTGRES_PASSWORD=secure_password
POSTGRES_DB=omnivore
```

### 使用远程 S3（AWS / Cloudflare R2）

不想自建 MinIO？可以使用任何 S3 兼容服务：

```bash
# Cloudflare R2 配置示例
S3_ENDPOINT=https://ACCOUNT_ID.r2.cloudflarestorage.com
S3_REGION=auto
S3_ACCESS_KEY=YOUR_R2_KEY
S3_SECRET_KEY=YOUR_R2_SECRET
S3_BUCKET=omnivore-articles
```

R2 的优势：**零出口流量费用**，非常适合存储文章快照。

### 启用邮件保存

配置 SMTP 后，可以通过发送邮件到指定地址来保存文章：

```bash
# .env 中添加
SMTP_HOST=smtp.yourdomain.com
SMTP_PORT=587
SMTP_USER=noreply@yourdomain.com
SMTP_PASSWORD=your_smtp_password
EMAIL_SAVE_ADDRESS=saved@yourdomain.com
```

---

## 🛡️ 安全加固

### 1. 防火墙限制

```bash
# 仅开放必要端口
ufw allow 22/tcp      # SSH
ufw allow 80/tcp      # HTTP (Let's Encrypt)
ufw allow 443/tcp     # HTTPS
ufw deny 3000/tcp     # 前端不直接暴露
ufw deny 4000/tcp     # API 不直接暴露
ufw enable
```

### 2. 定期备份

```bash
#!/bin/bash
# omnivore-backup.sh
BACKUP_DIR="/backups/omnivore/$(date +%Y%m%d)"
mkdir -p "$BACKUP_DIR"

# 备份 PostgreSQL
docker exec omnivore-db pg_dump -U omnivore omnivore > "$BACKUP_DIR/db.sql"

# 备份 MinIO 数据
docker run --rm -v omnivore_minio_data:/data -v "$BACKUP_DIR":/backup \
  alpine tar czf /backup/minio.tar.gz -C /data .

# 删除 30 天前的备份
find /backups/omnivore -maxdepth 1 -mtime +30 -exec rm -rf {} \;

echo "Backup completed: $BACKUP_DIR"
```

添加到 crontab：

```bash
0 3 * * * /root/omnivore/omnivore-backup.sh
```

### 3. 启用 OAuth（可选）

Omnivore 支持 GitHub OAuth 登录，避免密码管理：

```bash
# .env 中添加
NEXTAUTH_SECRET=your-random-secret
GITHUB_ID=your-github-oauth-client-id
GITHUB_SECRET=your-github-oauth-client-secret
```

---

## ❓ 常见问题

### Q: 部署后无法保存文章？

检查 Worker 容器日志：

```bash
docker logs omnivore-worker --tail 50
```

常见原因：S3 连接失败或 MinIO 未就绪。确认 `S3_ENDPOINT` 和凭证正确。

### Q: 内存占用过高？

Omnivore 最低需要约 1.5GB RAM。如果 VPS 内存不足，可以考虑：

1. 使用外部 PostgreSQL（节省容器内数据库内存）
2. 使用远程 S3（如 Cloudflare R2）
3. 限制 Worker 并发数

### Q: 能否只使用 Web 版而不部署 API？

不可以。Omnivore 的前端依赖后端 API 处理文章保存、搜索和标注。所有功能都需要完整的后端栈。

### Q: 移动端如何连接？

在 Omnivore iOS/Android 应用的设置中选择 "Custom Server"，输入 `https://omnivore.yourdomain.com` 和 API 密钥即可。

---

## 🎯 总结

Omnivore 是目前最好的自托管 Read-it-later 解决方案之一。它的优势在于：

1. **完全开源** — 代码透明，不存在供应商锁定
2. **功能丰富** — 全文搜索、高亮标注、AI 摘要一应俱全
3. **成本低廉** — 一台最便宜的 VPS 即可运行
4. **数据自主** — 你的文章、标注、标签永远属于你

与其每月支付订阅费给 Pocket 或 Readwise，不如花 **$4/月** 买一台 VPS，永久拥有自己的知识管理系统。

**立即行动**：花 10 分钟部署 Omnivore，把阅读主动权拿回自己手中。

---

*本文发布于 [SelfVPS 指南](https://selfvps.net)，转载请注明出处。*
