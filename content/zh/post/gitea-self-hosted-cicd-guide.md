---
title: "Gitea + Gitea Actions: 自托管 CI/CD 流水线完全指南 — 免费替代 GitLab CI"
description: "从零开始在 VPS 上搭建 Gitea 代码托管 + Gitea Actions 自动化流水线。无需付费订阅，无需暴露代码到公有云，实现从提交到部署的全流程自动化。"
date: 2026-07-03T10:00:00+08:00
lastmod: 2026-07-03T10:00:00+08:00
slug: "gitea-self-hosted-cicd-guide"
tags: ["Gitea", "CI/CD", "Gitea Actions", "自托管", "DevOps", "Docker", "自动化", "VPS部署"]
categories: ["部署教程"]
draft: false
image: /images/posts/gitea-self-hosted-cicd-guide/featured.png
aliases: [/zh/post/gitea-self-hosted-cicd-guide/]
---

## 为什么需要自托管 CI/CD？

在云原生时代，CI/CD（持续集成/持续交付）已成为软件开发的基础设施。GitHub Actions 和 GitLab CI 虽然功能强大，但存在几个痛点：

- **费用随用量增长**：GitHub Actions 免费额度有限，超出后按分钟计费；GitLab CI 的 runner 资源也需付费升级
- **代码隐私顾虑**：将代码推送到公有云平台，即使加密也无法完全排除数据泄露风险
- **网络延迟**：跨国访问 GitHub/GitLab 的 runner 可能导致构建速度缓慢
- **供应商锁定**：迁移成本高，workflow 语法虽相似但细节差异大

**Gitea + Gitea Actions** 提供了完美的替代方案：轻量级、资源占用少、完全自托管，并且原生支持 Actions 语法。

## Gitea 是什么？

[Gitea](https://gitea.com) 是一个开源的 Git 服务，用 Go 语言编写，特点包括：

- **极致轻量**：单二进制文件运行，内存占用仅需 ~100MB
- **功能完整**：支持 Issues、Pull Request、Wiki、Package Registry
- **资源丰富**：最低 512MB 内存即可运行，适合小型 VPS
- **活跃社区**：GitHub Star 数超过 45,000+

## Gitea Actions 是什么？

[Gitea Actions](https://docs.gitea.com/usage/actions/introduction) 是 Gitea 内置的 CI/CD 引擎，完全兼容 GitHub Actions 的 workflow 语法。这意味着：

- 现有的 GitHub Actions workflow 可以几乎零修改地迁移到 Gitea
- 使用相同的 `.github/workflows/` 目录结构
- 支持 Docker-based runners 和 self-hosted runners

## 架构概览

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Developer  │────▶│   Gitea Server    │────▶│  Gitea Runner   │
│   (本地)     │     │  (代码+Web UI)    │     │  (构建执行)     │
└─────────────┘     └──────────────────┘     └─────────────────┘
                           │                        │
                           ▼                        ▼
                    ┌──────────────┐         ┌──────────────┐
                    │ PostgreSQL/  │         │  Docker /    │
                    │ SQLite       │         │  目标服务器   │
                    └──────────────┘         └──────────────┘
```

## 第一步：部署 Gitea

### 使用 Docker Compose 一键部署

创建一个 `docker-compose.yml` 文件：

```yaml
version: '3'

services:
  gitea:
    image: gitea/gitea:1.22
    container_name: gitea
    environment:
      - USER_UID=1000
      - USER_GID=1000
      - GITEA__actions__ENABLED=true
    restart: always
    volumes:
      - ./gitea-data:/data
      - /etc/timezone:/etc/timezone:ro
      - /etc/localtime:/etc/localtime:ro
    ports:
      - "3000:3000"
      - "2222:22"
    depends_on:
      - db

  db:
    image: postgres:16-alpine
    container_name: gitea-db
    environment:
      - POSTGRES_USER=gitea
      - POSTGRES_PASSWORD=gitea_password_here
      - POSTGRES_DB=gitea
    restart: always
    volumes:
      - ./postgres-data:/var/lib/postgresql/data
```

启动服务：

```bash
mkdir -p gitea-data postgres-data
docker compose up -d
```

> **提示**：首次访问 `http://your-server-ip:3000` 会进入安装向导。SSH 端口映射为 2222 以避免与宿主机的 22 端口冲突。

### 安装向导关键配置

| 配置项 | 推荐值 |
|--------|--------|
| 数据库类型 | PostgreSQL（生产）/ SQLite（测试） |
| SSH 端口 | 2222 |
| Gitea 域名 | 你的 VPS IP 或域名 |
| 管理员账户 | 自行设定 |
| 启用 Actions | ✅ 必须勾选 |

## 第二步：配置 Gitea Actions Runner

Gitea Actions 需要一个 Runner 来执行 workflow。有两种方式：

### 方式一：Docker-in-Docker（推荐新手）

这种方式最简单，Runner 在容器中运行 Docker：

```yaml
# docker-compose.yml - 添加 Runner 服务
services:
  runner:
    image: gitea/act_runner:latest
    container_name: gitea-runner
    restart: always
    volumes:
      - ./runner-data:/data
      - /var/run/docker.sock:/var/run/docker.sock
    environment:
      - GITEA_INSTANCE_URL=http://gitea:3000
      - GITEA_RUNNER_NAME=my-runner
      - GITEA_RUNNER_REGISTRATION_TOKEN=your_registration_token
```

### 方式二：Self-Hosted Runner（推荐生产环境）

在宿主机上直接安装 Runner，性能更好：

```bash
# 下载 act_runner
wget https://dl.gitea.com/gitea/act_runner/latest/act_runner-linux-amd64
chmod +x act_runner-linux-amd64
mv act_runner-linux-amd64 /usr/local/bin/act_runner

# 注册 Runner
act_runner register \
  --instance http://your-server-ip:3000 \
  --name my-selfhosted-runner \
  --token your_registration_token

# 设置为系统服务
act_runner daemon install
act_runner daemon start
```

> **获取 Registration Token**：进入 Gitea Web → 仓库 → Settings → Actions → Runners → 点击 "New Runner" 获取 token。

### 配置 Runner Labels

为了让 workflow 正确匹配 Runner，需要配置 labels：

```bash
# 编辑 Runner 配置文件
nano /root/gitea-data/act_runner/cfg.yaml

# 添加 labels
labels:
  - ubuntu-latest=x86_64-linux
  - selfhosted=x86_64-linux
```

## 第三步：编写第一个 Workflow

Gitea Actions 使用 YAML 格式的 workflow 文件，存放在 `.gitea/workflows/` 目录下（注意是 `.gitea` 而非 `.github`）。

### 示例 1：Go 项目自动构建与测试

```yaml
# .gitea/workflows/go-ci.yml
name: Go CI/CD

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: selfhosted
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Go
        uses: actions/setup-go@v5
        with:
          go-version: '1.22'

      - name: Build
        run: go build -v ./...

      - name: Test
        run: go test -v ./...

      - name: Upload coverage
        run: |
          go test -coverprofile=coverage.out ./...
          go tool cover -html=coverage.out -o coverage.html
        if: success()
```

### 示例 2：Docker 镜像构建与推送

```yaml
# .gitea/workflows/docker-publish.yml
name: Docker Publish

on:
  release:
    types: [published]

jobs:
  docker:
    runs-on: selfhosted
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Login to Gitea Container Registry
        uses: docker/login-action@v3
        with:
          registry: gitea.yourdomain.com
          username: your_username
          password: ${{ secrets.GITEA_TOKEN }}

      - name: Set up QEMU
        uses: docker/setup-qemu-action@v3

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: |
            gitea.yourdomain.com/yourusername/yourapp:${{ github.ref_name }}
            gitea.yourdomain.com/yourusername/yourapp:latest
          platforms: linux/amd64,linux/arm64
```

### 示例 3：自动部署到目标服务器

```yaml
# .gitea/workflows/deploy.yml
name: Deploy to VPS

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: selfhosted
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Deploy via SSH
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.DEPLOY_HOST }}
          username: ${{ secrets.DEPLOY_USER }}
          key: ${{ secrets.DEPLOY_KEY }}
          port: 22
          script: |
            cd /opt/myapp
            docker compose pull
            docker compose up -d
            docker image prune -f
```

## 第四步：配置 Secret 与权限

### 添加 Repository Secrets

进入仓库 → Settings → Actions → Secrets → New Secret：

| Secret 名称 | 用途 |
|------------|------|
| `GITEA_TOKEN` | 用于 Docker Registry 登录的 Personal Access Token |
| `DEPLOY_HOST` | 目标部署服务器的 IP 地址 |
| `DEPLOY_USER` | SSH 用户名 |
| `DEPLOY_KEY` | SSH 私钥内容 |

### 生成 Personal Access Token

```
Settings → Applications → Generate Token
权限选择: repo, write:packages
```

## 第五步：Gitea Package Registry

Gitea 内置了包注册中心，可以替代 Docker Hub 和 npm registry：

```yaml
# docker-compose.yml 中已启用，访问:
# http://your-domain:3000/-/packages
```

推送 Docker 镜像到 Gitea Package Registry：

```bash
# 登录
docker login gitea.yourdomain.com -u your_username -p your_token

# 构建并推送
docker build -t gitea.yourdomain.com/yourusername/myapp:v1.0 .
docker push gitea.yourdomain.com/yourusername/myapp:v1.0
```

## 常见问题排查

### 问题 1：Runner 显示 "Offline"

```bash
# 检查 Runner 日志
docker logs gitea-runner -f

# 确认网络连接
curl -I http://gitea:3000

# 检查 registration token 是否过期
# 重新生成 token 并重启 Runner
```

### 问题 2：Workflow 卡住不执行

```bash
# 查看 Runner 队列
curl -u username:token http://gitea:3000/api/v1/admin/actions/runners

# 增加 Runner 并发数
# 编辑 cfg.yaml
concurrency_limit: 4
```

### 问题 3：Docker-in-Docker 网络问题

```yaml
# 在 workflow 中指定网络
jobs:
  build:
    runs-on: selfhosted
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_PASSWORD: test
    steps:
      - uses: actions/checkout@v4
      - name: Connect to DB
        run: |
          # 使用服务容器名连接
          PGPASSWORD=test psql -h localhost -U postgres -c "SELECT 1"
```

### 问题 4：磁盘空间不足

```bash
# 清理 Docker 缓存
docker system prune -af

# 定期清理旧镜像
act_runner cleanup --keep-latest 5

# 监控磁盘使用
df -h /var/lib/docker
```

## 性能优化建议

### 1. 使用 SQLite 代替 PostgreSQL（小规模部署）

```yaml
# 简化部署，去掉数据库服务
services:
  gitea:
    image: gitea/gitea:1.22
    environment:
      - GITEA__database__DB_TYPE=sqlite3
    volumes:
      - ./gitea-data:/data
```

### 2. 配置 Git LFS（大文件支持）

```bash
# 在 Gitea 配置中启用 LFS
[server]
LFS_START_SERVER = true

# 分配 LFS 存储空间
[lfs]
PATH = /data/git/lfs
```

### 3. 使用 Nginx 反向代理 + HTTPS

```nginx
server {
    listen 443 ssl http2;
    server_name gitea.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

    location / {
        proxy_pass http://localhost:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket support for real-time updates
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    location /api/ {
        client_max_body_size 500m;
        proxy_pass http://localhost:3000;
    }
}
```

## 资源需求参考

| 场景 | CPU | 内存 | 磁盘 |
|------|-----|------|------|
| 单人开发（SQLite） | 1核 | 512MB | 10GB |
| 小团队（PostgreSQL） | 2核 | 1GB | 20GB |
| 含 Runner 构建 | 额外 2核 | 额外 2GB | 额外 50GB |
| 大规模 CI/CD | 4核+ | 4GB+ | 按需扩展 |

## 与 GitHub Actions 对比

| 特性 | GitHub Actions | Gitea Actions |
|------|---------------|---------------|
| 免费额度 | 2000 分钟/月 | 无限制 |
| 自托管支持 | ✅ | ✅ |
| Workflow 语法 | ✅ | ✅（兼容） |
| Marketplace | 丰富 | 基础（可自定义） |
| 隐私控制 | 代码在云端 | 代码完全自控 |
| 初始配置 | 开箱即用 | 需自行部署 |
| 网络速度 | 取决于地区 | 内网极快 |
| 多平台构建 | ✅ | ✅ |

## 总结

Gitea + Gitea Actions 为自托管爱好者提供了一个**完全免费、完全可控**的 CI/CD 解决方案。对于预算有限的个人开发者和小型团队来说，这是替代 GitHub Actions 和 GitLab CI 的最佳选择之一。

**核心优势**：
- 🆓 **零费用**：没有用量限制，没有隐藏收费
- 🔒 **全私有**：代码和构建过程完全在自己的服务器上
- ⚡ **高性能**：内网构建，速度远超公有云 runner
- 🔄 **无缝迁移**：兼容 GitHub Actions 语法，迁移成本低

下一步建议：部署 Gitea → 配置 Runner → 迁移一个非关键项目试用 → 逐步替换所有 CI/CD 流程。
