---
title: "Gitea 自托管 Git 服务：在 VPS 上搭建轻量级代码仓库"
description: "用 Gitea 在 VPS 上搭建属于自己的 Git 代码托管平台，替代 GitHub/GitLab。仅需 256MB 内存、Docker 一键部署，支持 CI/CD、WebHook、SSH 密钥管理、团队协作，完全掌控你的代码数据。"
date: 2026-05-27T09:00:00+08:00
slug: "gitea-selfhosted-git-vps"
tags: ["Gitea", "Git", "代码托管", "Docker", "自托管", "VPS", "CI/CD", "DevOps", "GitHub 替代"]
categories: ["DevOps", "版本控制"]
aliases: [/zh/post/gitea-selfhosted-git-vps/]
draft: false
image: /images/posts/gitea-selfhosted-git-vps/featured.png
---

## 引言

> **核心观点**：Gitea 是目前最轻量、最容易部署的自托管 Git 服务。一台 1 核 512MB 的廉价 VPS 就能跑，Docker 安装只需 3 分钟，资源占用不到 GitLab 的 1/10。

GitHub 很好用，但代码放在别人服务器上始终存在隐私、合规和可用性风险。GitLab 功能强大但臃肿——官方推荐最低 4GB 内存，小 VPS 根本扛不住。**Gitea** 完美填补了这个空白：它用 Go 编写，单二进制文件运行，256MB 内存即可流畅运行，功能却一应俱全——仓库管理、Issue 跟踪、Pull Request、CI/CD、WebHook、Wiki 全都有。

本文手把手教你用 Docker 部署 Gitea，配置反向代理与 HTTPS，接入 PostgreSQL 数据库，并设置 CI/CD 自动化流水线。

---

## 为什么选择 Gitea？

| 特性 | Gitea | GitLab CE | GitHub Free |
|------|-------|-----------|-------------|
| 内存需求 | ~150MB | ~2-4GB | N/A（第三方） |
| 部署时间 | 3 分钟 | 30 分钟+ | 无需部署 |
| 代码所有权 | ✅ 完全掌控 | ✅ 完全掌控 | ❌ 托管在 GitHub |
| 私有仓库 | ✅ 无限免费 | ✅ 无限免费 | ✅ 无限免费 |
| CI/CD | ✅ 内置（轻量） | ✅ 内置（重型） | ❌ 需 GitHub Actions |
| 团队协作 | ✅ Push/Pull/Review | ✅ 完整功能 | ✅ 完整功能 |
| 双因素认证 | ✅ 支持 | ✅ 支持 | ✅ 支持 |
| WebHook | ✅ 支持 | ✅ 支持 | ✅ 支持 |

**适用场景**：
- 个人开发者/小团队需要私有代码托管
- 合规要求代码不得存放在境外平台
- 希望结合自建 CI/CD 实现自动化
- 低预算 VPS（1核/1GB）想要 Git 服务

---

## 前置准备

开始之前请确保你的 VPS 满足以下条件：

| 项目 | 最低要求 | 推荐配置 |
|------|---------|---------|
| CPU | 1 核 | 2 核 |
| 内存 | 512MB | 1GB |
| 磁盘 | 10GB | 20GB+ |
| Docker | ✅ 已安装 | Docker Compose |
| 域名 | 可选（推荐） | 如 `git.yourdomain.com` |

确认 Docker 和 Docker Compose 已安装：

```bash
docker --version && docker compose version
```

如果未安装，运行以下命令快速安装 Docker：

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
```

---

## 第一步：用 Docker Compose 部署 Gitea

创建一个目录并编写 `docker-compose.yml`：

```bash
mkdir -p ~/gitea && cd ~/gitea
```

```yaml
# docker-compose.yml
version: "3"

services:
  gitea:
    image: gitea/gitea:latest
    container_name: gitea
    environment:
      - USER_UID=1000
      - USER_GID=1000
      - GITEA__database__DB_TYPE=postgres
      - GITEA__database__HOST=db:5432
      - GITEA__database__NAME=gitea
      - GITEA__database__USER=gitea
      - GITEA__database__PASSWD=gitea_secret_password
      - GITEA__server__DOMAIN=git.yourdomain.com
      - GITEA__server__HTTP_PORT=3000
      - GITEA__server__ROOT_URL=https://git.yourdomain.com
      - GITEA__server__DISABLE_SSH=false
      - GITEA__server__SSH_PORT=2222
      - GITEA__server__SSH_LISTEN_PORT=22
    restart: always
    networks:
      - gitea
    volumes:
      - ./gitea:/data
      - /etc/timezone:/etc/timezone:ro
      - /etc/localtime:/etc/localtime:ro
    ports:
      - "127.0.0.1:3000:3000"
      - "2222:22"
    depends_on:
      - db

  db:
    image: postgres:16-alpine
    container_name: gitea-db
    restart: always
    environment:
      - POSTGRES_USER=gitea
      - POSTGRES_PASSWORD=gitea_secret_password
      - POSTGRES_DB=gitea
    networks:
      - gitea
    volumes:
      - ./postgres:/var/lib/postgresql/data

networks:
  gitea:
    driver: bridge
```

> ⚠️ **安全提醒**：请将 `gitea_secret_password` 改为一个强密码。SSH 端口映射为 `2222:22` 是因为宿主机 22 端口通常已被 SSH 占用。

启动服务：

```bash
docker compose up -d
```

检查状态：

```bash
docker compose ps
```

如果一切正常，你会看到两个容器都在运行。

---

## 第二步：配置 Nginx 反向代理与 HTTPS

Gitea 运行在 `127.0.0.1:3000`，我们需要通过 Nginx 代理并配置 SSL。

在 Nginx 中添加以下配置（如果你用了 Nginx Proxy Manager，可以通过 Web UI 添加代理主机）：

```nginx
# /etc/nginx/sites-available/gitea
server {
    listen 80;
    server_name git.yourdomain.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name git.yourdomain.com;

    ssl_certificate     /etc/letsencrypt/live/git.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/git.yourdomain.com/privkey.pem;

    # Gitea WebSocket 支持
    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket 支持
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

启用配置并申请 SSL 证书：

```bash
sudo ln -s /etc/nginx/sites-available/gitea /etc/nginx/sites-enabled/
sudo certbot --nginx -d git.yourdomain.com
sudo systemctl reload nginx
```

用 Nginx Proxy Manager 的用户，在 Web UI 中添加：
- **Domain**: `git.yourdomain.com`
- **Forward Hostname**: `127.0.0.1`
- **Forward Port**: `3000`
- **SSL**: 申请 Let's Encrypt 证书
- **WebSocket**: 开启 ✅

---

## 第三步：初始配置

打开浏览器访问 `https://git.yourdomain.com`，你会看到 Gitea 安装页面。

关键配置项：

| 配置项 | 推荐值 | 说明 |
|--------|--------|------|
| 数据库类型 | PostgreSQL | 已通过 Docker Compose 配置 |
| 数据库主机 | db:5432 | Docker 内部网络地址 |
| 数据库用户 | gitea | 与 docker-compose 一致 |
| 数据库密码 | gitea_secret_password | 你设置的密码 |
| 数据库名称 | gitea | 与 docker-compose 一致 |
| 站点名称 | 你的 Git 服务名称 | 如 "My Code" |
| 仓库根路径 | /data/git/repositories | 默认即可 |
| SSH 服务器域名 | git.yourdomain.com | 你的域名 |
| SSH 端口 | 2222 | 映射的 SSH 端口 |
| 基础 URL | https://git.yourdomain.com | 最终访问地址 |

点击"安装 Gitea"后，系统会自动完成配置。然后创建管理员账号。

> 💡 **提示**：一旦完成安装，可以在 `/data/gitea/conf/app.ini` 中修改配置，修改后重启容器即可。

---

## 第四步：日常使用与团队协作

### 创建仓库

1. 登录后点击右上角"+" → **新建仓库**
2. 填写仓库名称、描述
3. 选择公开或私有
4. 可选：初始化 README、.gitignore、许可证

### 推送代码

```bash
# 克隆已有仓库到 Gitea
git clone --bare https://github.com/your/repo.git
cd repo.git
git push --mirror https://git.yourdomain.com/username/new-repo.git
cd ..
rm -rf repo.git

# 或者直接推送新项目
git remote add origin https://git.yourdomain.com/username/my-project.git
git push -u origin main
```

### SSH 密钥配置

1. 右上角用户头像 → **设置** → **SSH/GPG 密钥**
2. 添加你的公钥（`~/.ssh/id_rsa.pub`）
3. 使用 SSH 协议推送代码：

```bash
git remote add origin ssh://git@git.yourdomain.com:2222/username/repo.git
git push -u origin main
```

### 团队协作

| 功能 | 操作方式 |
|------|---------|
| 添加协作者 | 仓库 → 设置 → 管理 → 添加合作者 |
| 创建组织 | 右上角"+" → 新建组织 |
| 团队管理 | 组织 → 团队 → 创建团队并设置权限 |
| Pull Request | 分支开发后提交 PR → 代码审查 → 合并 |
| Issue 跟踪 | 仓库 → Issues → 新建标签/里程碑/看板 |
| Wiki | 仓库 → Wiki → 编写文档 |
| 代码审查 | PR 中添加行内评论 → Approve/Request Changes |

---

## 第五步：配置 CI/CD 流水线

Gitea 内置了 **Gitea Actions**（兼容 GitHub Actions 语法），只需启用一个 Runner 即可。

### 启动 Actions Runner

```bash
# 创建 Runner 目录
mkdir -p ~/gitea-runner && cd ~/gitea-runner

# 下载 Runner
docker run --rm -it -v $PWD:/data gitea/act_runner:latest \
  /bin/sh -c "act_runner --version && act_runner register"

# 注册 Runner
# 1. 在 Gitea Web UI 中：管理站点 → Actions → Runner → 创建 Runner
# 2. 获取注册 Token
# 3. 用 docker compose 启动 Runner
```

编写 `act-runner-docker-compose.yml`：

```yaml
version: "3"

services:
  runner:
    image: gitea/act_runner:latest
    environment:
      - GITEA_INSTANCE_URL=https://git.yourdomain.com
      - GITEA_RUNNER_REGISTRATION_TOKEN=你的注册令牌
      - GITEA_RUNNER_NAME=vps-runner
    volumes:
      - ./data:/data
      - /var/run/docker.sock:/var/run/docker.sock
    restart: always
```

启动 Runner：

```bash
docker compose -f act-runner-docker-compose.yml up -d
```

### 编写工作流

在仓库中创建 `.gitea/workflows/deploy.yml`：

```yaml
name: Deploy
on: [push]

jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: 20

      - name: Install dependencies
        run: npm ci

      - name: Run tests
        run: npm test

      - name: Build
        run: npm run build

      - name: Deploy via SSH
        env:
          DEPLOY_KEY: ${{ secrets.DEPLOY_KEY }}
        run: |
          echo "$DEPLOY_KEY" > deploy_key
          chmod 600 deploy_key
          rsync -avz -e "ssh -i deploy_key -o StrictHostKeyChecking=no" \
            ./dist/ user@yourserver:/var/www/myapp/
```

> 💡 在 Gitea 仓库设置中添加 `secrets.DEPLOY_KEY` 即可安全存储 SSH 私钥。

---

## 第六步：备份与恢复

### 自动备份（推荐）

创建每日备份脚本 `~/gitea-backup.sh`：

```bash
#!/bin/bash
BACKUP_DIR="/backups/gitea"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p $BACKUP_DIR

# 备份 Gitea 数据目录
docker exec gitea tar czf - /data > $BACKUP_DIR/gitea-data-$DATE.tar.gz

# 备份 PostgreSQL 数据库
docker exec gitea-db pg_dump -U gitea gitea > $BACKUP_DIR/gitea-db-$DATE.sql

# 压缩数据库备份
gzip $BACKUP_DIR/gitea-db-$DATE.sql

# 保留最近 30 天备份
find $BACKUP_DIR -name "*.tar.gz" -mtime +30 -delete
find $BACKUP_DIR -name "*.gz" -mtime +30 -delete

echo "✅ Backup completed: $DATE"
```

添加到 crontab：

```bash
chmod +x ~/gitea-backup.sh
crontab -e
# 添加：0 3 * * * /root/gitea-backup.sh
```

### 恢复

```bash
# 恢复数据目录
docker exec -i gitea tar xzf - -C / < gitea-data-20260601_030000.tar.gz

# 恢复数据库
gunzip < gitea-db-20260601_030000.sql.gz | docker exec -i gitea-db psql -U gitea gitea

# 重启 Gitea
docker compose restart gitea
```

---

## 性能优化技巧

1. **使用 SQLite（极低负载场景）**：如果只有你一个人用，SQLite 更轻量：
   ```yaml
   environment:
     - GITEA__database__DB_TYPE=sqlite3
   ```
   去掉 PostgreSQL 服务，单容器即可运行，内存占用可低至 **80MB**。

2. **Nginx 缓存静态资源**：
   ```nginx
   location /assets/ {
       proxy_pass http://127.0.0.1:3000;
       expires 7d;
       add_header Cache-Control "public, immutable";
   }
   ```

3. **开启 Git 压缩**：在 `app.ini` 中：
   ```ini
   [git]
   GC_ARGS = --aggressive --auto
   ENABLE_PUSH_OPTIONS = false
   ```

4. **限制仓库大小**：管理面板中设置单仓库最大 500MB，防止存储爆满。

---

## 常见问题

### Q: Gitea 和 Gogs 有什么区别？
Gitea 是从 Gogs fork 而来，社区更活跃、更新更快、功能更多。**推荐直接使用 Gitea**。

### Q: 如何迁移 GitHub 仓库到 Gitea？
使用 Gitea 内置的迁移工具：**新建仓库 → 迁移仓库**，输入 GitHub 仓库 URL 和 Token 即可。

### Q: Gitea 支持 LDAP/OAuth 登录吗？
支持。管理面板 → 认证源 → 添加认证源，支持 LDAP、OAuth2（GitHub、Google、GitLab 等）、PAM。

### Q: 可以限制仓库可见性吗？
可以。每个仓库可设为公开、私有或内部（组织成员可见）。

### Q: 如何升级 Gitea？
```bash
cd ~/gitea
docker compose pull
docker compose up -d
```

---

## 总结

Gitea 让你用最小的成本掌控自己的代码。它与 Git 完全兼容，日常使用体验与 GitHub 高度一致，学习成本几乎为零。

**下一步你可以**：
- ✅ 将个人项目从 GitHub 迁移到 Gitea
- ✅ 配置 Gitea Actions 实现自动化部署
- ✅ 为团队创建组织，设置权限管理
- ✅ 搭建 Drone CI 或 Woodpecker CI 作为增强 CI/CD

> 🎯 一条命令、5 分钟、256MB 内存——这就是 Gitea 的极致轻量。如果你一直在寻找「GitHub 的自托管替代」却嫌 GitLab 太重，Gitea 就是你一直在等的那个答案。

---

**相关文章**：
- [Nginx Proxy Manager 反向代理配置](/zh/post/nginx-proxy-manager-guide/)
- [Docker 安全加固指南](/zh/post/docker-security-hardening/)
- [VPS 备份自动化](/zh/post/vps-backup-automation-guide/)
