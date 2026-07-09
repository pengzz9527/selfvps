---
title: "自建 Coolify：你的开源 Heroku/Netlify 替代方案，一键部署 Docker 应用"
slug: coolify-selfhosted-paas-guide
date: 2026-07-09
categories: ["自托管", "DevOps"]
tags: ["coolify", "paas", "docker", "heroku替代", "自动化部署"]
description: "全面指南：在 VPS 上自建 Coolify PaaS 平台，实现一键部署、自动 SSL、持续集成，免费替代 Heroku/Netlify。"
image: "/images/posts/coolify-selfhosted-paas-guide/featured.png"
---

## 为什么你需要 Coolify？

如果你曾经用过 Heroku、Netlify 或 Vercel，你一定体验过它们"推送代码即部署"的便捷。但当你的应用规模扩大、流量增长时，这些平台的费用也会水涨船高——Heroku 的 hobby dyno 每月 $7，一旦需要多个服务或更高性能，月费轻松突破 $50-$100。

**Coolify** 是一个开源的、可自托管的 PaaS（平台即服务）解决方案，由 Coollabs.io 开发。它让你在自己的 VPS 上获得类似 Heroku/Netlify 的体验，但完全免费且不受平台限制。

### Coolify 的核心优势

| 特性 | Heroku | Netlify | Coolify（自建） |
|------|--------|---------|----------------|
| 基础费用 | $7/月起 | 免费额度有限 | **完全免费** |
| 自定义域名 | ✅ | ✅ | ✅ |
| 自动 HTTPS/SSL | ✅ | ✅ | ✅（Let's Encrypt） |
| Docker 支持 | ✅ | ❌ | ✅ |
| 数据库管理 | 付费扩展 | ❌ | ✅（内置） |
| 持续部署 | ✅ | ✅ | ✅（GitHub/GitLab） |
| 数据所有权 | 平台所有 | 平台所有 | **完全自有** |
| 无限项目 | 付费 | 受限 | ✅ |

## 环境准备

### 系统要求

- **操作系统**: Ubuntu 22.04 / 24.04（推荐）或 Debian 12
- **内存**: 最低 2GB RAM（推荐 4GB+）
- **磁盘**: 至少 20GB 可用空间
- **CPU**: 2 核及以上
- **域名**: 指向你的 VPS IP（用于 HTTPS）
- **端口**: 80, 443, 22, 和 Coolify 使用的端口

### 初始设置

```bash
# 更新系统
sudo apt update && sudo apt upgrade -y

# 安装必要的基础工具
sudo apt install -y curl git jq ufw

# 配置防火墙
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable
```

## 安装 Coolify

### 方法一：一键安装脚本（推荐）

Coolify 提供了官方的一键安装脚本，这是最简单的方式：

```bash
curl -fsSL https://cdn.coollabs.io/coolify/install.sh | bash
```

安装脚本会自动完成以下操作：
1. 检查系统兼容性
2. 安装 Docker 和 Docker Compose
3. 拉取并启动 Coolify 容器
4. 生成管理员密码

安装完成后，你会看到类似这样的输出：

```
✅ Coolify is installed successfully!

📧 Admin email: admin@example.com
🔑 Admin password: [随机生成的密码]
🌐 URL: http://your-vps-ip:8080

请保存你的管理员密码！
```

### 方法二：手动 Docker 安装

如果你更喜欢手动控制，可以使用 Docker Compose：

```bash
# 创建 Coolify 目录
mkdir -p ~/coolify && cd ~/coolify

# 下载 docker-compose 配置
curl -fsSL https://cdn.coollabs.io/coolify/docker-compose.yml -o docker-compose.yml

# 下载 .env 模板
curl -fsSL https://cdn.coollabs.io/coolify/.env.example -o .env

# 生成安全的密钥
openssl rand -base64 32 > .env

# 启动服务
docker compose up -d
```

## 首次配置

### 1. 访问控制面板

打开浏览器访问 `http://your-server-ip:8080`（如果安装脚本指定了其他端口，请使用对应端口）。使用安装时生成的管理员凭据登录。

### 2. 修改默认密码

登录后第一件事就是修改默认密码：

```
设置 → 账户 → 修改密码
```

### 3. 配置服务器

在 Coolify 的控制面板中，点击 **"Servers"** → **"Add Server"**：

- **Name**: 给你的服务器起个名字（如 "Production VPS"）
- **IP Address**: 你的 VPS IP
- **User**: root（或你创建的非 root 用户）
- **SSH Key**: 上传你的 SSH 私钥（推荐方式）或使用密码
- **Port**: 22（默认 SSH 端口）

Coolify 会通过 SSH 连接到你的服务器，验证连接后会显示绿色 ✅。

## 核心功能详解

### 1. 一键部署 Web 应用

#### 从 GitHub 仓库部署

这是最常用也最强大的功能：

1. 在 Coolify 面板点击 **"Applications"** → **"Deploy New Application"**
2. 选择 **"GitHub"** 作为 Git 提供者
3. 授权 Coolify 访问你的 GitHub 账户
4. 选择目标仓库
5. 配置部署参数：

```
Build Pack: 
  - PHP (Laravel/Symfony)
  - Node.js
  - Python (Django/Flask)
  - Static HTML
  - Docker Compose

Deployment Settings:
  - 自动部署分支（main/master）
  - 构建命令
  - 发布命令
  - 环境变量
```

**示例：部署一个 Node.js 应用**

```yaml
# 假设你的仓库包含 package.json
{
  "name": "my-app",
  "scripts": {
    "build": "npm run build",
    "start": "node dist/main.js"
  }
}
```

在 Coolify 中配置：
- **Build Command**: `npm run build`
- **Start Command**: `npm start`
- **Ports Exposed**: `3000`

部署后，Coolify 会自动分配一个子域名（如 `my-app.xxx.coolify.yourdomain.com`），并配置 HTTPS。

#### 从 Docker Compose 部署

对于更复杂的场景，可以直接部署 `docker-compose.yml`：

```yaml
version: '3.8'
services:
  app:
    image: your-image:latest
    ports:
      - "3000:3000"
    environment:
      - NODE_ENV=production
    restart: always
```

### 2. 数据库管理

Coolify 内置了多种数据库的一键部署和管理：

**支持的数据库类型：**
- PostgreSQL
- MySQL / MariaDB
- Redis
- MongoDB
- Meilisearch
- ClickHouse

**创建数据库：**

1. 点击 **"Databases"** → **"Create Database"**
2. 选择数据库类型
3. 设置版本、资源限制（CPU/内存）
4. 点击创建

Coolify 会为每个数据库自动生成强密码，并提供连接信息：

```
Host: db-postgres-xxx.coolify.yourdomain.com
Port: 5432
Database: your_db_name
Username: your_username
Password: [自动生成的强密码]
```

### 3. 静态网站部署

部署静态网站（HTML/CSS/JS）非常简单：

1. 将你的静态文件推送到 GitHub 仓库
2. 在 Coolify 中选择 **"Static"** 作为构建包
3. 指定构建输出目录（如 `dist/` 或 `build/`）
4. 部署！

Coolify 会自动使用 Nginx 提供静态文件服务，并配置 HTTPS。

### 4. 持续部署（CI/CD）

Coolify 集成了 GitHub/GitLab webhook，实现了真正的持续部署：

```
代码推送 → GitHub Webhook → Coolify 自动构建 → 自动部署
```

**配置步骤：**

1. 在应用的 **"Settings"** → **"Continuous Deployment"** 中启用
2. 选择监控的分支（如 `main`, `develop`）
3. 可选：配置部署规则（如只在打 tag 时部署）

**高级：手动触发部署**

你可以通过 API 手动触发部署：

```bash
curl -X POST \
  "https://coolify.yourdomain.com/api/v1/deploy?resource_id=YOUR_RESOURCE_ID" \
  -H "Authorization: Bearer YOUR_API_TOKEN"
```

### 5. 环境变量管理

Coolify 提供了可视化的环境变量管理界面：

- 支持按环境隔离（开发/预发/生产）
- 支持加密敏感变量（数据库密码、API Key 等）
- 支持从外部密钥管理服务导入

```yaml
# 在 Coolify 界面中配置
DATABASE_URL: postgresql://user:pass@host:5432/db
REDIS_URL: redis://redis-host:6379
APP_SECRET: [加密存储]
API_KEY: [加密存储]
```

### 6. SSL/TLS 证书管理

Coolify 使用 Let's Encrypt 自动为所有域名签发和续期 SSL 证书：

- **首次部署**时自动申请证书
- **自动续期**：在证书到期前自动更新
- **通配符证书**：支持 `*.yourdomain.com`（需 DNS 验证）

如果你使用自定义域名，只需在应用设置中添加域名，Coolify 会自动配置：

```
域名: app.yourdomain.com
协议: HTTPS
证书: Let's Encrypt (自动)
```

## 实际部署案例

### 案例一：部署 Laravel 应用

```bash
# 1. 确保你的 Laravel 项目包含以下文件：
# - composer.json
# - package.json (如需前端构建)
# - .dockerignore

# 2. 在 Coolify 中配置：
# Build Pack: PHP
# Base Path: / (项目根目录)
# Publish Path: public
# PHP Version: 8.3

# 3. 添加环境变量：
APP_NAME="MyApp"
APP_ENV=production
APP_DEBUG=false
DB_CONNECTION=mysql
DB_HOST=db-mysql-xxx.coolify.yourdomain.com
DB_PORT=3306
DB_DATABASE=myapp
DB_USERNAME=root
DB_PASSWORD=[Coolify生成的密码]

# 4. 点击部署
```

Laravel 应用通常还需要运行队列 worker：

```bash
# 在 Coolify 的 "Services" 中添加队列 worker
Command: php artisan queue:work
Auto-Start: enabled
```

### 案例二：部署 Next.js + PostgreSQL

```yaml
# docker-compose.yml
version: '3.8'
services:
  web:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "3000:3000"
    environment:
      - DATABASE_URL=postgresql://postgres:password@db:5432/myapp
      - NEXT_PUBLIC_API_URL=https://api.yourdomain.com
    depends_on:
      - db
  
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: myapp
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - pgdata:/var/lib/postgresql/data

volumes:
  pgdata:
```

在 Coolify 中：
1. 选择 **"Docker Compose"** 部署方式
2. 指向包含上述文件的 GitHub 仓库
3. Coolify 会自动解析并部署所有服务
4. 数据库会自动获取内部连接地址

## 安全最佳实践

### 1. 限制访问

```bash
# 在防火墙中仅允许必要的端口
sudo ufw deny 8080/tcp  # Coolify 面板端口（如果不使用域名访问）

# 通过域名访问 Coolify 面板
# 在 Coolify 设置中添加自定义域名，启用 HTTPS
```

### 2. 定期备份

Coolify 支持自动备份配置：

```bash
# 手动备份 Coolify 配置
docker exec coolify-backup-1 backup

# 配置定时备份（使用 cron）
echo "0 2 * * * docker exec coolify-backup-1 backup" | crontab -
```

### 3. 使用 SSH 密钥认证

不要在 Coolify 中存储密码，使用 SSH 密钥：

```bash
# 在服务器上生成密钥
ssh-keygen -t ed25519 -C "coolify-deploy" -f ~/.ssh/coolify_deploy

# 将公钥添加到 GitHub/GitLab
cat ~/.ssh/coolify_deploy.pub

# 在 Coolify 中添加私钥
# Settings → SSH Keys → Add Private Key
```

### 4. 更新 Coolify

Coolify 支持一键更新：

```bash
# 在 Coolify 面板中点击 "Update"
# 或通过命令行：
curl -fsSL https://cdn.coollabs.io/coolify/update.sh | bash
```

## 成本对比

### 使用 Heroku 部署 3 个服务

| 服务 | Heroku 月费 |
|------|------------|
| Web App (Standard-1X) | $25 |
| Redis (RedisCloud 30) | $25 |
| 额外 Worker | $25 |
| **总计** | **$75/月** |

### 使用 Coolify 自建

| 项目 | 费用 |
|------|------|
| VPS (2GB RAM, 2 CPU) | ~$5-10/月 |
| 域名 | ~$10/年 |
| SSL 证书 | **免费** |
| Coolify | **免费（开源）** |
| **总计** | **~$6-11/月** |

**每年节省：$780 - $900！**

## 常见问题

### Q: Coolify 适合生产环境吗？

A: 完全可以。Coolify 已经有很多生产环境用户，包括中小型企业和个人开发者。它基于 Docker，稳定性有保障。但对于超高流量场景，建议配合负载均衡和 CDN 使用。

### Q: 可以部署多个服务器吗？

A: 可以。Coolify 支持多服务器管理。你可以在一个 Coolify 实例中管理多台 VPS，适合多区域部署。

### Q: 数据安全性如何？

A: Coolify 本身不存储你的应用代码或数据，只存储配置信息。所有应用运行在你自己的服务器上，数据完全可控。建议使用 SSD 硬盘并定期备份数据库。

### Q: 支持 Kubernetes 吗？

A: 截至 2026 年，Coolify 主要基于 Docker Compose。Kubernetes 支持正在开发中。对于大多数 VPS 场景，Docker Compose 已足够。

### Q: 如何迁移到 Coolify？

A: 非常简单。只需将你的应用代码推送到 Git 仓库，然后在 Coolify 中配置对应的部署设置即可。Coolify 会自动处理构建和部署流程。

## 总结

Coolify 是目前最好的开源 PaaS 自托管方案之一。它完美填补了 Heroku/Netlify 与裸 Docker 之间的空白：

- ✅ **零软件许可费用** — 完全开源
- ✅ **一键部署** — GitHub 推送即部署
- ✅ **自动 HTTPS** — Let's Encrypt 无缝集成
- ✅ **数据库管理** — 内置多种数据库支持
- ✅ **多环境管理** — 开发/测试/生产环境隔离
- ✅ **可视化面板** — 无需编写复杂配置

如果你有一台 VPS 并且厌倦了手动管理 Docker 容器，Coolify 绝对值得尝试。它让你的 VPS 变成一个功能完整的云平台，而不再是一台需要 SSH 进去敲命令的远程机器。

---

*这篇文章对你有帮助吗？欢迎在 GitHub 上给 selfvps.net 提 Issue 或 PR 来改进内容。*
