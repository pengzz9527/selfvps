---
title: "Dokku 零配置 PaaS 部署指南：在 VPS 上自建 Heroku，一条命令部署应用"
description: "从零开始在 VPS 上部署 Dokku — 这个基于 Docker 的微型 PaaS 平台让你能用一条 git push 命令部署应用，自动 SSL、自动域名管理，资源占用仅 200MB 内存"
date: 2026-06-10T10:00:00+08:00
lastmod: 2026-06-10T10:00:00+08:00
slug: "dokku-vps-paas-deployment"
tags: ["Dokku", "PaaS", "Docker", "VPS部署", "自托管", "Heroku替代", "CI/CD"]
categories: ["自托管平台"]
draft: false
image: /images/posts/dokku-vps-paas-deployment/featured.png
---

## 为什么需要 Dokku？

如果你曾经在 [Heroku](https://www.heroku.com/) 上部署过应用，你一定体验过那种「只需 `git push heroku main` 就能发布」的快感。但 Heroku 免费套餐早已取消，免费额度也极为有限。对于个人开发者和小团队来说，每月 $25 起的费用并不便宜。

[Dokku](https://dokku.com/) 是一个基于 Docker 的**微型 PaaS**，它能在任何 Linux VPS 上运行，让你拥有和 Heroku 几乎一样的部署体验，而且完全免费、完全可控。

### Dokku vs Heroku vs Coolify

| 特性 | Dokku | Heroku | Coolify |
|------|-------|--------|---------|
| 部署方式 | `git push` | `git push` | Web UI / API |
| 内存占用 | ~200MB | N/A | ~1GB+ |
| 学习曲线 | 中等 | 简单 | 简单 |
| 免费 | ✅ 完全开源 | ❌ 付费 | ✅ 开源 |
| 插件系统 | Bash 插件 | Buildpacks | 预置模板 |
| 适合场景 | 技术用户 | 非技术用户 | 团队管理 |

如果你有一定 Linux 基础，想要一个**轻量、快速、可控**的自托管 PaaS 方案，Dokku 是目前最佳选择。

---

## 环境准备

### 服务器要求

- **操作系统**: Ubuntu 22.04 / 24.04（推荐）或 Debian 12
- **CPU**: 1 核及以上
- **内存**: 1GB 及以上（建议 2GB）
- **磁盘**: 20GB SSD 及以上
- **域名**: 一个指向 VPS IP 的域名（如 `app.yourdomain.com`）

> 💡 **省钱提示**: 如果你已经有 VPS，Dokku 的资源占用非常低——核心进程仅占用约 200MB 内存。你可以和 Nginx、Cloudflare Tunnel 等其他服务共存。

### 域名配置

在继续之前，请确保你的域名已正确解析到 VPS 的公网 IP：

```bash
# 添加通配符 DNS 记录（可选，推荐）
# 在 Cloudflare 或其他 DNS 服务商处添加：
*.yourdomain.com  →  VPS_IP  (A 记录)
yourdomain.com    →  VPS_IP  (A 记录)
```

通配符 DNS 记录让你可以为每个应用分配独立子域名，而无需手动配置 DNS。

---

## 安装 Dokku

### 一键安装脚本

Dokku 提供了官方的一键安装脚本，这是最简单的方式：

```bash
# SSH 到你的 VPS
ssh root@your_vps_ip

# 设置主机名（重要！）
hostnamectl set-hostname dokku.yourdomain.com

# 运行官方安装脚本
curl -sSL https://dokku.com/install.sh | bash
```

安装过程会自动完成以下操作：

1. 安装 Docker（如果未安装）
2. 下载并配置 Dokku
3. 设置 SSH 密钥
4. 创建初始用户

安装完成后，你会看到类似这样的输出：

```
=====> Dokku version: 0.32.13
=====> Dokku is enabled
=====> Instance dokku installed
```

### 验证安装

```bash
# 检查 Dokku 状态
dokku doctor

# 查看 Dokku 版本
dokku version

# 查看已安装的插件
dokku plugins
```

---

## 配置 Nginx 与 SSL

### 默认 Nginx 配置

Dokku 自带 Nginx 容器作为反向代理。首次部署应用时，它会自动生成 Nginx 配置。

```bash
# 查看当前 Nginx 配置
dokku nginx:show-default-config
```

### 启用 HTTPS（Let's Encrypt）

Dokku 内置了 Let's Encrypt 插件，可以自动申请和续期 SSL 证书：

```bash
# 安装 letsencrypt 插件
dokku plugins-install

# 配置邮件地址（用于 Let's Encrypt 通知）
dokku config:set --global DOKKU_LETSENCRYPT_EMAIL=admin@yourdomain.com

# 启用自动 SSL
dokku letsencrypt:auto-reenable
```

之后，当你部署应用时，Dokku 会自动为你的域名申请 SSL 证书。

### 配置全局 Nginx 参数

```bash
# 设置最大上传文件大小（适合文件上传应用）
dokku nginx:show-default-config | \
  sed 's/client_max_body_size 1m;/client_max_body_size 100m;/' | \
  dokku nginx:set-default-config

# 重载 Nginx
dokku nginx:reload
```

---

## 部署第一个应用

### 方式一：Git Push 部署（推荐）

这是最接近 Heroku 体验的方式：

```bash
# 在你的本地机器上
git clone https://github.com/dokku/sample-app.git
cd sample-app

# 添加 dokku 远程仓库
git remote add dokku dokku@your_vps_ip:myapp

# 部署！
git push dokku main
```

就这么简单。Dokku 会：

1. 检测应用类型（Node.js、Python、Go、Ruby 等）
2. 构建应用（使用 Buildpacks 或 Dockerfile）
3. 启动容器
4. 自动分配子域名 `myapp.yourdomain.com`
5. 自动申请 SSL 证书

### 方式二：使用 Dockerfile

如果你有自定义的 Dockerfile：

```dockerfile
# Dockerfile 示例
FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production
COPY . .
EXPOSE 3000
CMD ["node", "index.js"]
```

```bash
# 在 VPS 上创建应用
dokku apps:create myapp

# 绑定域名
dokku domains:add myapp myapp.yourdomain.com

# 启用 SSL
dokku letsencrypt myapp

# 部署
git push dokku main
```

### 方式三：使用 Docker Compose

Dokku 支持通过 `dokku.yml` 文件定义多容器应用：

```yaml
# dokku.yml
release:
  cmd:
    - node dist/src/main.js

run:
  web:
    cmd:
      - node dist/src/main.js
```

```bash
# 直接通过 git 推送 dokku.yml
git push dokku main
```

---

## 数据库管理

Dokku 最强大的功能之一是它的**插件系统**。你可以像 Heroku 一样轻松管理数据库：

### PostgreSQL

```bash
# 安装 postgres 插件
dokku plugin:install https://github.com/dokku/dokku-postgres.git

# 创建数据库实例
dokku postgres:create mydb

# 关联到应用
dokku postgres:link mydb myapp

# 查看连接信息
dokku postgres:info mydb
```

关联后，Dokku 会自动将数据库连接信息注入为环境变量：

```
DATABASE_URL=postgres://dokku:随机密码@dokku-postgres-mydb:5432/mydb
```

### Redis

```bash
# 安装 redis 插件
dokku plugin:install https://github.com/dokku/dokku-redis.git

# 创建 Redis 实例
dokku redis:create mycache

# 关联到应用
dokku redis:link mycache myapp
```

### MySQL / MongoDB

```bash
# MySQL
dokku plugin:install https://github.com/dokku/dokku-mysql.git
dokku mysql:create mydb
dokku mysql:link mydb myapp

# MongoDB
dokku plugin:install https://github.com/dokku/dokku-mongodb.git
dokku mongodb:create mydb
dokku mongodb:link mydb myapp
```

### 数据库备份

```bash
# PostgreSQL 备份
dokku postgres:backup-save mydb > backup.sql

# 恢复
dokku postgres:backup-restore mydb < backup.sql
```

---

## 高级配置

### 环境变量管理

```bash
# 设置单个环境变量
dokku config:set myapp NODE_ENV=production

# 设置多个环境变量
dokku config:set myapp API_KEY=xxx SECRET_KEY=yyy REDIS_URL=redis://...

# 查看所有环境变量
dokku config myapp

# 删除环境变量
dokku config:unset myapp API_KEY

# 从文件批量导入
dokku config:import myapp .env
```

### 端口映射

Dokku 默认使用内部端口。如果需要自定义外部端口：

```bash
# 查看当前端口绑定
dokku ports:show myapp

# 设置端口映射
dokku ports:set myapp http:80:3000 https:443:3000
```

### 资源限制

防止某个应用耗尽服务器资源：

```bash
# 限制 CPU
dokku resource:limit myapp cpus 0.5

# 限制内存
dokku resource:limit myapp memory 512m

# 查看资源限制
dokku resource:info myapp
```

### 日志管理

```bash
# 实时查看应用日志
dokku logs myapp -t

# 查看最近 100 行日志
dokku logs myapp --tail=100

# 导出日志到文件
dokku logs myapp > app.log
```

### 健康检查

```bash
# 设置 HTTP 健康检查
dokku probes:set myapp health http://localhost:3000/health

# 查看健康状态
dokku probes:status myapp
```

---

## CI/CD 集成

### GitHub Actions 示例

```yaml
# .github/workflows/deploy.yml
name: Deploy to Dokku

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Deploy to Dokku
        uses: dokku/github-action@v2
        with:
          host: your_vps_ip
          hostname: dokku.yourdomain.com
          identity: ${{ secrets.SSH_PRIVATE_KEY }}
          app: myapp
```

### GitLab CI 示例

```yaml
# .gitlab-ci.yml
deploy:
  stage: deploy
  script:
    - ssh-keyscan your_vps_ip >> ~/.ssh/known_hosts
    - git push dokku@your_vps_ip:myapp HEAD:main
  only:
    - main
```

---

## 性能优化

### 启用 Gzip 压缩

```bash
# 编辑全局 Nginx 配置
dokku nginx:show-default-config | \
  sed '/gzip_types/a\    gzip_comp_level 6;' | \
  dokku nginx:set-default-config

dokku nginx:reload
```

### 启用 HTTP/2

```bash
# 在 Nginx 配置中启用 HTTP/2
dokku nginx:show-default-config | \
  sed 's/listen 443 ssl;/listen 443 ssl http2;/' | \
  dokku nginx:set-default-config

dokku nginx:reload
```

### 容器资源优化

```bash
# 为应用设置合理的资源上限
dokku resource:limit myapp memory 1g
dokku resource:limit myapp cpus 1.0

# 设置优雅停机时间
dokku config:set myapp DOKKU_APP_RESTORE=1
```

### 缓存优化

```bash
# 为 Node.js 应用启用构建缓存
dokku buildpacks:set myapp cache true

# 为静态文件设置缓存头
dokku nginx:show-default-config | \
  sed '/location \/static/a\    expires 30d;\n    add_header Cache-Control "public, immutable";' | \
  dokku nginx:set-default-config

dokku nginx:reload
```

---

## 备份与迁移

### 完整备份

```bash
# 备份所有应用配置
dokku apps:list > apps.txt
dokku domains:list > domains.txt

# 备份每个应用的配置
for app in $(dokku apps:list); do
  dokku config --shell $app | sed 's/^export //' > configs/$app.env
done

# 备份数据库
dokku postgres:backup-save mydb > backups/mydb-$(date +%Y%m%d).sql

# 备份 Dokku 本身的数据
tar czf dokku-backup-$(date +%Y%m%d).tar.gz \
  /var/lib/dokku \
  /etc/dokku \
  /home/dokku
```

### 迁移到新服务器

```bash
# 在新服务器上安装 Dokku
curl -sSL https://dokku.com/install.sh | bash

# 恢复 SSH 密钥
scp /path/to/dokku.pub root@new_server:/home/dokku/.ssh/authorized_keys

# 恢复应用配置
for env_file in configs/*.env; do
  app=$(basename $env_file .env)
  dokku apps:create $app
  dokku config:import $app $env_file
done

# 恢复数据库
dokku postgres:restore mydb < backups/mydb-20260610.sql
```

---

## 常见问题排查

### 问题 1: 部署失败，构建报错

```bash
# 查看详细构建日志
dokku logs myapp --tail=200

# 检查 Docker 镜像
docker images | grep myapp

# 手动构建测试
cd /tmp
git clone your_repo
dokku build myapp .
```

### 问题 2: SSL 证书无法申请

```bash
# 检查 Let's Encrypt 插件状态
dokku letsencrypt myapp

# 手动申请证书
dokku letsencrypt myapp

# 查看 Let's Encrypt 日志
tail -f /var/log/letsencrypt/letsencrypt.log
```

确保：
- 域名已正确解析到 VPS IP
- 80 和 443 端口未被其他服务占用
- 防火墙允许 HTTP/HTTPS 流量

### 问题 3: 应用启动后立即退出

```bash
# 查看崩溃日志
dokku logs myapp --tail=50

# 检查端口绑定
dokku ports:show myapp

# 进入容器调试
dokku enter myapp /bin/bash
```

### 问题 4: 磁盘空间不足

```bash
# 清理未使用的 Docker 资源
dokku docker-options:add app extra "--rm-volumes=unused"
docker system prune -a --volumes

# 清理旧镜像
dokku ps:cleanup myapp
```

---

## 成本分析

### 对比 Heroku 的费用

假设你部署 3 个应用，每个应用需要 512MB 内存：

| 平台 | 月费 | 说明 |
|------|------|------|
| Heroku | ~$75 | 3 × $25/月 |
| Dokku (VPS) | $5-10 | 一台 1GB VPS 的费用 |
| **节省** | **~$65/月** | **年省 $780+** |

### 推荐的 VPS 配置

| 规模 | 配置 | 月费估算 | 可部署应用数 |
|------|------|----------|-------------|
| 个人项目 | 1C1G | $5-6 | 2-3 个 |
| 小型团队 | 2C2G | $10-12 | 5-8 个 |
| 中型站点 | 4C4G | $20-25 | 15-20 个 |

---

## 总结

Dokku 是在 VPS 上自建 PaaS 的绝佳选择：

- ✅ **极简部署**：一条 `git push` 即可完成部署
- ✅ **自动 SSL**：Let's Encrypt 集成，证书自动续期
- ✅ **丰富插件**：PostgreSQL、Redis、MongoDB 等一键安装
- ✅ **资源友好**：核心占用仅 ~200MB 内存
- ✅ **完全免费**：开源无限制
- ✅ **高度可控**：完全掌握自己的数据和基础设施

对于已经熟悉 Docker 和 Linux 的开发者来说，Dokku 提供了最佳的自托管 PaaS 体验。它不像 Coolify 那样臃肿，也不像纯 Docker 那样缺乏自动化——它正好站在两者之间，提供了恰到好处的抽象层。

---

## 参考资源

- [Dokku 官方文档](https://dokku.com/getting-started/installation/)
- [Dokku 插件仓库](https://github.com/dokku)
- [Dokku GitHub 仓库](https://github.com/dokku/dokku)
- [Buildpacks 文档](https://buildpacks.io/)
- [Let's Encrypt 文档](https://letsencrypt.org/zh-cn/)
