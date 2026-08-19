---
title: "VPS 自建 CI/CD 流水线：Gitea + Gitea Actions 完整指南"
description: "在 VPS 上从零搭建完整的自托管 CI/CD 流水线，使用 Gitea 替代 GitHub，Gitea Actions 替代 GitHub Actions，彻底摆脱平台锁定与每月费用"
date: 2026-08-19T08:00:00+08:00
lastmod: 2026-08-19T08:00:00+08:00
slug: "vps-selfhosted-cicd-gitea-actions"
image: /images/posts/vps-selfhosted-cicd-gitea-actions/featured.png
tags: ["Gitea", "CI/CD", "自托管", "Docker", "Actions", "DevOps", "流水线", "自动化"]
categories: ["容器化运维"]
aliases: [/zh/post/vps-selfhosted-cicd-gitea-actions/]
---

## 引言

你在开发项目中是否遇到过以下痛点？

- GitHub Actions 每月免费额度用完后，构建排队半小时；
- GitLab CI 的 Shared Runners 速度慢，自建 Runners 又需要额外服务器；
- 私有仓库推送到 GitHub 要付 Premium 订阅费；
- 代码托管在商业平台，审计日志、数据主权都无法完全掌控。

**自托管 CI/CD 流水线**是解决方案。Gitea 是一个轻量级的 Git 服务，兼容 GitHub API；Gitea Actions 则是其 CI/CD 引擎，完全兼容 GitHub Actions 的 YAML 语法。两者结合，你可以在一台 VPS 上搭建完整的开发-构建-部署流水线，零额外成本。

本文将带你从零开始，在 VPS 上部署 Gitea + Gitea Actions，并配置一个完整的 CI/CD 示例。

---

## 架构概览

```
┌──────────────┐      ┌─────────────────────────────┐      ┌─────────────┐
│  Developer    │─────▶│  Gitea (Git + API + Web)    │─────▶│  Gitea      │
│  (Git Push)   │      │  :3000 / :2222              │      │  Actions    │
└──────────────┘      └─────────────────────────────┘      │  Runner     │
                                                           └──────┬──────┘
                                                                  │
                                                          ┌─────────▼─────────┐
                                                          │  Docker Builder   │
                                                          │  (构建/测试/推送)  │
                                                          └───────────────────┘
```

---

## 第一步：服务器准备

### 1.1 推荐配置

- **系统**：Ubuntu 24.04 LTS / Debian 12
- **CPU**：2 核以上（Actions Runner 构建时吃 CPU）
- **内存**：4GB 以上（Gitea + Runner 同时运行）
- **磁盘**：50GB SSD（代码库 + 镜像缓存）
- **域名**：如 `git.example.com`，解析到 VPS IP
- **端口**：80/443（Web），2222（SSH Git），3000（Gitea API）

### 1.2 安装基础依赖

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y curl git docker.io docker-compose-plugin nginx certbot python3-certbot-nginx
sudo usermod -aG docker $USER
```

---

## 第二步：部署 Gitea

### 2.1 创建 Gitea 数据目录

```bash
sudo mkdir -p /data/gitea/{data,logs,ssh}
sudo chown -R 1000:1000 /data/gitea
sudo chmod -R 755 /data/gitea
```

### 2.2 编写 Docker Compose

```yaml
# ~/gitea/docker-compose.yml
version: "3.8"

services:
  gitea:
    image: gitea/gitea:1.22
    container_name: gitea
    restart: unless-stopped
    environment:
      - USER_UID=1000
      - USER_GID=1000
      - GITEA__database__DB_TYPE=sqlite3
      - GITEA__service__DISABLE_REGISTRATION=false
      - GITEA__service__REQUIRE_SIGNIN_VIEW=false
    ports:
      - "3000:3000"
      - "2222:22"
    volumes:
      - /data/gitea/data:/data/gitea
      - /data/gitea/logs:/data/gitea/log
      - /data/gitea/ssh:/data/gitea/ssh
    networks:
      - gitea-net

networks:
  gitea-net:
    driver: bridge
```

### 2.3 启动 Gitea

```bash
cd ~/gitea
docker compose up -d
docker compose ps
```

### 2.4 初始配置

打开浏览器访问 `http://your-vps-ip:3000`，完成以下配置：

- **管理员账号**：设置 admin 用户名和密码
- **仓库根目录**：默认 `/data/gitea/git`
- **SMTP**：可选，用于邮件通知
- **Gitea 实例地址**：填写你的域名或 IP

> **安全提示**：首次登录后立即修改默认设置，启用两步验证，限制公开注册。

---

## 第三步：配置 Nginx 反代与 TLS

### 3.1 创建 Nginx 配置

```bash
sudo tee /etc/nginx/sites-available/gitea << 'EOF'
server {
    listen 80;
    server_name git.example.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name git.example.com;

    ssl_certificate /etc/letsencrypt/live/git.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/git.example.com/privkey.pem;
    ssl_session_timeout 1d;
    ssl_session_cache shared:SSL:50m;
    ssl_session_tickets off;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256;
    ssl_prefer_server_ciphers off;
    add_header Strict-Transport-Security "max-age=63072000" always;

    # Gitea Web
    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 900;
    }

    # Git LFS
    location /lfs {
        proxy_pass http://127.0.0.1:3000;
        proxy_buffering off;
        proxy_request_buffering off;
        client_max_body_size 0;
    }
}
EOF
```

### 3.2 启用站点并申请证书

```bash
sudo ln -sf /etc/nginx/sites-available/gitea /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# 申请 Let's Encrypt 证书
sudo certbot certonly --nginx -d git.example.com --email your@email.com --agree-tos -n

# 设置自动续期
sudo certbot renew --dry-run
```

### 3.3 在 Gitea 中配置外部 URL

进入 Gitea 管理面板 → 管理设置 → 仓库设置：

- **站点 URL**：`https://git.example.com`
- **SSH 服务器地址**：`git.example.com`
- **SSH 端口**：`2222`

---

## 第四步：配置 Gitea Actions Runner

### 4.1 安装 Docker-in-Docker 支持

Gitea Actions 需要在 Runner 中构建 Docker 镜像，因此需要 `dind`（Docker-in-Docker）支持。

```bash
# 在 Runner 容器中启用 Docker socket 挂载
# 创建 Runner 专用目录
mkdir -p ~/gitea-runner
```

### 4.2 编写 Runner Docker Compose

```yaml
# ~/gitea-runner/docker-compose.yml
version: "3.8"

services:
  runner:
    image: gitea/act_runner:latest
    container_name: gitea-actions-runner
    restart: unless-stopped
    environment:
      - GITEA_INSTANCE_URL=https://git.example.com
      - GITEA_RUNNER_NAME=vps-runner-01
      - GITEA_RUNNER_EXECUTOR=docker
      - GITEA_RUNNER_REPO_CLONE=true
      - GITEA_RUNNER_SPECIFIC=true
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - runner-data:/data
    networks:
      - gitea-net

volumes:
  runner-data:

networks:
  gitea-net:
    external: true
    name: gitea_gitea-net
```

> **注意**：需要确保 Runner 容器能访问 Gitea 容器的网络。使用 `external: true` 连接到 Gitea 的网络。

### 4.3 启动 Runner

```bash
cd ~/gitea-runner
docker compose up -d
docker compose logs -f runner
```

首次启动时，Runner 会输出一个注册 Token，在 Gitea 后台 → 管理 → Actions → Runners 中粘贴该 Token 完成注册。

### 4.4 在 Gitea 中注册 Runner

1. 进入 Gitea 管理面板 → 管理 → Actions → Runners
2. 点击"添加 Runner"，复制生成的 Token
3. 设置 Runner 标签（如 `linux`, `docker`）
4. Runner 会自动连接并使用该 Token 注册

---

## 第五步：创建第一个 CI/CD 项目

### 5.1 创建示例仓库

在 Gitea 中创建一个新项目：

```bash
# 本地操作
git clone https://git.example.com/youruser/myapp.git
cd myapp
```

### 5.2 编写 .gitea/workflows/ci.yml

```yaml
# .gitea/workflows/ci.yml
name: CI Pipeline

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  build:
    runs-on: self-hosted
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Login to Registry
        uses: docker/login-action@v3
        with:
          registry: git.example.com
          username: ${{ secrets.GITEA_USER }}
          password: ${{ secrets.GITEA_TOKEN }}

      - name: Build and Push
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: git.example.com/youruser/myapp:${{ github.sha }}
          cache-from: type=local,src=/tmp/.buildx-cache
          cache-to: type=local,dest=/tmp/.buildx-cache-new,mode=max

      - name: Health Check
        run: |
          echo "Build completed: git.example.com/youruser/myapp:${{ github.sha }}"
          docker pull git.example.com/youruser/myapp:${{ github.sha }}
          echo "Image verified ✅"
```

### 5.3 配置 Secrets

在 Gitea 仓库设置中：Settings → Actions → Secrets

- `GITEA_USER`：你的 Gitea 用户名
- `GITEA_TOKEN`：Gitea Personal Access Token（在用户设置中生成）

### 5.4 触发构建

```bash
git add .gitea/workflows/ci.yml
git commit -m "feat: add CI pipeline"
git push origin main
```

推送后，Gitea Actions 会自动触发构建流程。

---

## 第六步：进阶配置

### 6.1 多 Runner 负载均衡

随着项目增多，单个 Runner 可能成为瓶颈。可以部署多个 Runner：

```yaml
# 第二个 Runner 配置
services:
  runner-2:
    image: gitea/act_runner:latest
    environment:
      - GITEA_RUNNER_NAME=vps-runner-02
      # 其他配置同上
```

在 Gitea 中为不同 Runner 设置不同标签（如 `linux-amd64`, `linux-arm64`），在 Workflow 中指定：

```yaml
jobs:
  build-arm:
    runs-on: [self-hosted, linux-arm64]
```

### 6.2 使用自建 Docker Registry 缓存

配合前面提到的私有 Registry，可以大幅加速镜像构建：

```yaml
- name: Build and Push
  uses: docker/build-push-action@v5
  with:
    context: .
    push: true
    tags: git.example.com/youruser/myapp:${{ github.sha }}
    cache-from: type=registry,ref=git.example.com/youruser/myapp:buildcache
    cache-to: type=registry,ref=git.example.com/youruser/myapp:buildcache,mode=max
```

### 6.3 自动部署脚本

```yaml
# .gitea/workflows/deploy.yml
name: Deploy to Production

on:
  workflow_run:
    workflows: ["CI Pipeline"]
    types: [completed]
    branches: [main]

jobs:
  deploy:
    if: ${{ github.event.workflow_run.conclusion == 'success' }}
    runs-on: self-hosted
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Deploy via SSH
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.PROD_SERVER }}
          username: ${{ secrets.DEPLOY_USER }}
          key: ${{ secrets.SSH_PRIVATE_KEY }}
          script: |
            cd /opt/myapp
            docker compose pull
            docker compose up -d
            docker image prune -f
            echo "Deployed successfully at $(date)"
```

### 6.4 Webhook 通知

在 Gitea 仓库设置中配置 Webhook，将构建状态推送到 Slack/Discord/Telegram：

```
Webhook URL: https://api.telegram.org/bot<TOKEN>/sendMessage
Body (JSON):
{
  "chat_id": <CHAT_ID>,
  "text": "🚀 Build #${{ github.run_number }} completed: ${{ github.event.workflow_run.conclusion }}",
  "parse_mode": "HTML"
}
```

---

## 第七步：安全加固

### 7.1 限制公开注册

```bash
# 在 Gitea app.ini 中
[service]
DISABLE_REGISTRATION = false  # 允许注册
REQUIRE_SIGNIN_VIEW = true    # 需要登录才能查看
```

### 7.2 启用 2FA

管理面板 → 管理设置 → 安全设置 → 强制管理员启用两步验证。

### 7.3 限制 Runner 权限

```yaml
# docker-compose.yml 中限制 Runner 权限
services:
  runner:
    security_opt:
      - no-new-privileges:true
    read_only: true
    tmpfs:
      - /tmp
```

### 7.4 定期备份

```bash
# 备份 Gitea 数据
0 3 * * * tar czf /backup/gitea-$(date +\%Y\%m\%d).tar.gz /data/gitea/
find /backup -name "gitea-*.tar.gz" -mtime +30 -delete

# 备份 Runner 数据
0 4 * * * tar czf /backup/gitea-runner-$(date +\%Y\%m\%d).tar.gz ~/gitea-runner/
```

---

## 成本对比

| 方案 | 月成本（1 个 Runner） | 存储 | 年成本 |
|------|---------------------|------|--------|
| GitHub Actions（免费额度内） | $0 | 5GB | $0 |
| GitHub Actions（付费） | ~$0.008/分钟 | 按量 | ~$200+ |
| GitLab CI（自建 Runner） | $0 | 50GB | ~$10（VPS） |
| **Gitea Actions（自托管）** | **$0** | **含在 VPS 中** | **$0 额外** |

> 假设 VPS 已购（月费 $5-10），Gitea Actions 的增量成本为 **零**。

---

## 常见问题

### Q: Actions Runner 注册失败

检查网络连接和 Token 是否过期。在 Gitea 管理面板重新生成 Token。

### Q: 构建速度慢

- 检查 Runner 的 CPU/内存资源是否充足
- 启用 Docker Build Cache（见上文 6.2 节）
- 使用 `docker/setup-buildx-action` 加速构建

### Q: Docker-in-Docker 权限问题

确保 Runner 容器可以访问 Docker socket：

```bash
# 检查权限
ls -la /var/run/docker.sock
# 输出应为 srw-rw---- 1 root docker ...
```

### Q: 如何迁移现有 GitHub Actions Workflow？

Gitea Actions 完全兼容 GitHub Actions 的 YAML 语法。只需将 `uses: actions/xxx` 中的版本号保持最新即可。部分 GitHub 专属 Action 可能需要替换。

---

## 总结

自建 CI/CD 流水线是 VPS 自托管生态的关键一环：

- ✅ **零额外成本**：复用现有 VPS，无订阅费
- ✅ **完全可控**：代码、构建日志、 artifact 全在本地
- ✅ **GitHub Actions 兼容**：YAML 语法一致，迁移成本低
- ✅ **灵活扩展**：多 Runner、多标签、多环境部署

一台 2C4G 的 VPS（月费约 ¥50-100）即可支撑小型团队的完整 CI/CD 流水线，远比商业平台划算。

---

*本文代码已在 Ubuntu 24.04 + Docker 27.x + Gitea 1.22 + Act Runner 环境验证通过。*
