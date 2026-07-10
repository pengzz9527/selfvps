---
title: "自建 Drone CI 轻量级持续集成部署完全指南 — Docker 原生、高效灵活"
description: "在 VPS 上从零搭建 Drone CI，实现轻量级、Docker 原生的持续集成与部署流水线，比 GitLab CI 更简洁、资源占用更低，适合中小团队和个人开发者。"
date: 2026-07-10T10:00:00+08:00
lastmod: 2026-07-10T10:00:00+08:00
slug: "drone-ci-selfhosted-guide"
tags: ["Drone CI", "CI/CD", "Docker", "DevOps", "持续集成", "自动化部署", "VPS", "开源"]
categories: ["部署教程"]
draft: false
image: /images/posts/drone-ci-selfhosted-guide/featured.png
aliases: [/zh/post/drone-ci-selfhosted-guide/]
---

## 为什么选择 Drone CI？

在自托管 CI/CD 工具的选择中，GitLab CI 和 GitHub Actions 占据了大部分市场。然而，对于资源有限的 VPS 用户和追求简洁性的团队来说，**Drone CI** 提供了独特的优势：

- **极致轻量**：核心组件仅一个二进制文件 + 数据库，内存占用 < 100MB
- **Docker 原生**：所有构建都在容器中运行，天然隔离
- **YAML 配置简洁**：`.drone.yml` 语法比 `.gitlab-ci.yml` 更直观
- **插件生态丰富**：内置 100+ 插件，支持自定义扩展
- **开源免费**：MIT 许可证，无功能限制
- **多 Git 平台支持**：GitHub、GitLab、Gitea、Bitbucket、Stash

## 架构概览

```
┌──────────────┐     ┌─────────────┐     ┌──────────────┐
│   Git Server  │────▶│  Drone      │────▶│  Build       │
│  (GitHub/     │     │  Server     │     │  Containers  │
│   Gitea/etc)  │     │  :8000      │     │  (Docker)    │
└──────────────┘     └──────┬──────┘     └──────────────┘
                           │
                    ┌──────▼──────┐
                    │  Drone      │
                    │  Agent(s)   │
                    │  :3000      │
                    └─────────────┘
```

## 第一步：环境准备

### 系统要求

| 组件 | 最低配置 | 推荐配置 |
|------|---------|---------|
| CPU | 1 核 | 2+ 核 |
| 内存 | 512MB | 1GB+ |
| 磁盘 | 10GB | 20GB+ SSD |
| 操作系统 | Ubuntu 20.04+ / Debian 11+ | Ubuntu 22.04 LTS |

### 安装 Docker

```bash
# 更新系统
sudo apt update && sudo apt upgrade -y

# 安装 Docker
curl -fsSL https://get.docker.com | sh

# 启动并设置开机自启
sudo systemctl enable --now docker

# 验证安装
docker --version
# Docker version 24.0.7, build afdd53b
```

## 第二步：使用 Docker Compose 部署 Drone Server

### 创建项目目录

```bash
mkdir -p ~/drone-ci && cd ~/drone-ci
```

### 生成密钥

```bash
# 生成 Drone 密钥（用于签名 JWT token）
DRONE_SECRET=$(openssl rand -hex 16)
echo "DRONE_SECRET=$DRONE_SECRET"

# 生成 agent 共享密钥
DRONE_RPC_SECRET=$(openssl rand -hex 16)
echo "DRONE_RPC_SECRET=$DRONE_RPC_SECRET"
```

### 编写 docker-compose.yml

```yaml
version: '3'

services:
  # Drone Server
  drone-server:
    image: drone/drone:2
    container_name: drone-server
    restart: unless-stopped
    ports:
      - "8000:8000"
    volumes:
      - drone-data:/data
      - /var/run/docker.sock:/var/run/docker.sock
    environment:
      # 数据库配置（SQLite 默认）
      - DRONE_DATABASE_DRIVER=sqlite3
      - DRONE_DATABASE_DATASET=/data/drone.sqlite
      
      # 服务器配置
      - DRONE_SERVER_HOST=${DRONE_SERVER_HOST:-http://localhost:8000}
      - DRONE_SERVER_PROTO=http
      
      # RPC 配置（server 和 agent 通信）
      - DRONE_RPC_SECRET=${DRONE_RPC_SECRET}
      - DRONE_RPC_PROTO=http
      - DRONE_RPC_HOST=drone-server
      - DRONE_RPC_PORT=8000
      
      # 认证配置（以 GitHub 为例）
      - DRONE_GITHUB_CLIENT_ID=${DRONE_GITHUB_CLIENT_ID}
      - DRONE_GITHUB_CLIENT_SECRET=${DRONE_GITHUB_CLIENT_SECRET}
      - DRONE_GITHUB=true
      
      # 其他可选配置
      - DRONE_USER_CREATE=username:your_github_username,admin:true
      - DRONE_LOGS_LEVEL=info
      - DRONE_RESULTS_ENABLE=true
      
    networks:
      - drone-net

  # Drone Agent（处理构建任务）
  drone-agent:
    image: drone/drone-runner-docker:1
    container_name: drone-agent
    restart: unless-stopped
    depends_on:
      - drone-server
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - runner-data:/data
    environment:
      - DRONE_RPC_PROTO=http
      - DRONE_RPC_HOST=drone-server
      - DRONE_RPC_PORT=8000
      - DRONE_RPC_SECRET=${DRONE_RPC_SECRET}
      - DRONE_RUNNER_NAME=${HOSTNAME:-drone-runner}
      - DRONE_RUNNER_CAPACITY=2
      - DRONE_RUNNER_THREADS=2
      
    networks:
      - drone-net

  # 可选：PostgreSQL 替代 SQLite（生产环境推荐）
  # drone-db:
  #   image: postgres:15-alpine
  #   container_name: drone-db
  #   restart: unless-stopped
  #   environment:
  #     POSTGRES_DB: drone
  #     POSTGRES_USER: drone
  #     POSTGRES_PASSWORD: ${DRONE_DB_PASSWORD}
  #   volumes:
  #     - pg-data:/var/lib/postgresql/data
  #   networks:
  #     - drone-net

volumes:
  drone-data:
  runner-data:
  # pg-data:

networks:
  drone-net:
    driver: bridge
```

### 设置环境变量

```bash
# 创建 .env 文件
cat > .env << EOF
# 服务器地址
DRONE_SERVER_HOST=http://your-vps-ip:8000

# 从第一步生成的密钥
DRONE_SECRET=${DRONE_SECRET}
DRONE_RPC_SECRET=${DRONE_RPC_SECRET}

# GitHub OAuth 配置
DRONE_GITHUB_CLIENT_ID=your_github_client_id
DRONE_GITHUB_CLIENT_SECRET=your_github_client_secret

# 管理员用户名
DRONE_ADMIN_USERNAME=your_github_username
EOF
```

### 创建 GitHub OAuth 应用

1. 访问 [GitHub Settings > Developer settings > OAuth Apps](https://github.com/settings/developers)
2. 点击 **"New OAuth App"**
3. 填写：
   - Application name: `Drone CI`
   - Homepage URL: `http://your-vps-ip:8000`
   - Authorization callback URL: `http://your-vps-ip:8000/login/oauth/callback`
4. 保存后获取 **Client ID** 和 **Client Secret**

### 启动服务

```bash
# 拉取镜像
docker compose pull

# 启动服务
docker compose up -d

# 查看日志
docker compose logs -f

# 检查服务状态
docker ps
```

预期输出：
```
CONTAINER ID   IMAGE                            STATUS
abc123         drone/drone:2                    Up 2 minutes
def456         drone/drone-runner-docker:1      Up 2 minutes
```

## 第三步：配置 Nginx 反向代理（可选但推荐）

### 安装 Nginx

```bash
sudo apt install nginx -y
```

### 创建 Nginx 配置

```nginx
server {
    listen 80;
    server_name ci.yourdomain.com;
    
    # 最大上传文件大小
    client_max_body_size 50m;
    
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
    }
}
```

```bash
# 测试配置
sudo nginx -t

# 启用站点
sudo ln -s /etc/nginx/sites-available/drone /etc/nginx/sites-enabled/

# 重启 Nginx
sudo systemctl reload nginx
```

### 配置 HTTPS（Let's Encrypt）

```bash
# 安装 Certbot
sudo apt install certbot python3-certbot-nginx -y

# 获取证书
sudo certbot --nginx -d ci.yourdomain.com

# 自动续期
sudo systemctl enable --now certbot-renew.timer
```

## 第四步：首次登录与初始化

### 访问 Drone Web UI

打开浏览器访问 `http://your-vps-ip:8000` 或 `https://ci.yourdomain.com`

1. 点击 **"Sign in with GitHub"**
2. 授权 Drone 访问你的 GitHub 账号
3. 如果配置了 `DRONE_USER_CREATE`，你将自动成为管理员

### 验证安装

```bash
# 通过 API 检查服务器状态
curl -H "Authorization: Bearer $(drone token)" \
     http://localhost:8000/api/healthz

# 返回 {"status":"ok"} 表示正常运行
```

## 第五步：配置第一个项目

### 添加仓库

1. 在 Drone Web UI 中，点击左侧 **"Repositories"**
2. 点击 **"Activate"** 按钮激活你想监控的 GitHub/Gitea 仓库
3. 或者使用 API 激活：

```bash
# 激活仓库
curl -X PUT \
  -H "Authorization: Bearer $(drone token)" \
  -H "Content-Type: application/json" \
  http://localhost:8000/api/repos/username/repo-name/activate
```

### 创建 .drone.yml

在你的项目根目录创建 `.drone.yml` 配置文件：

```yaml
# 基础构建流水线
kind: pipeline
type: docker
name: default

steps:
  # 1. 拉取代码
  - name: checkout
    image: alpine/git
    commands:
      - git fetch --all
      - git checkout $DRONE_COMMIT_BRANCH

  # 2. 安装依赖
  - name: install-dependencies
    image: node:20-alpine
    commands:
      - npm ci

  # 3. 代码检查
  - name: lint
    image: node:20-alpine
    commands:
      - npm run lint
    when:
      branch: [main, develop]

  # 4. 运行测试
  - name: test
    image: node:20-alpine
    commands:
      - npm test
    when:
      branch: [main, develop]

  # 5. 构建 Docker 镜像
  - name: build-image
    image: plugins/docker
    settings:
      registry: docker.io
      username:
        from_secret: docker_username
      password:
        from_secret: docker_password
      repo: yourusername/your-app
      tags: 
        - latest
        - $DRONE_COMMIT_SHA
    when:
      branch: main
      event: push

  # 6. 部署到服务器
  - name: deploy
    image: appleboy/drone-ssh
    settings:
      host:
        from_secret: deploy_host
      username:
        from_secret: deploy_user
      key:
        from_secret: deploy_key
      port: 22
      script:
        - cd /opt/your-app
        - docker compose pull
        - docker compose up -d
    when:
      branch: main
      event: push
```

### 配置 Secrets

在项目的 **"Settings > Secrets"** 中添加：

| 名称 | 值 | 说明 |
|------|-----|------|
| `docker_username` | 你的 Docker Hub 用户名 | 推送镜像用 |
| `docker_password` | Docker Hub 密码/Token | 推送镜像用 |
| `deploy_host` | 目标服务器 IP | 部署目标 |
| `deploy_user` | SSH 用户名 | 通常是 `root` 或 `deploy` |
| `deploy_key` | SSH 私钥 | 用于 SSH 连接 |

## 第六步：高级配置

### 使用缓存加速构建

```yaml
kind: pipeline
type: docker
name: default

steps:
  - name: restore-cache
    image: alpine:3.18
    commands:
      - mkdir -p ~/.cache/npm
      - ls -la ~/.cache/npm

  - name: install-dependencies
    image: node:20-alpine
    commands:
      - npm ci
    volumes:
      - name: cache
        path: ~/.cache

  # ... 其他步骤

volumes:
  - name: cache
    temp: {}
```

### 并行执行多个步骤

```yaml
steps:
  - name: unit-tests
    image: golang:1.21-alpine
    commands:
      - go test ./... -v
    when:
      branch: main

  - name: integration-tests
    image: golang:1.21-alpine
    commands:
      - go test ./integration/... -v
    when:
      branch: main

  - name: security-scan
    image: aquasec/trivy:latest
    commands:
      - trivy fs --severity HIGH,CRITICAL .
    when:
      branch: main
```

### 条件化执行

```yaml
steps:
  - name: build-staging
    image: plugins/docker
    settings:
      repo: myapp/staging
      auto_tag: true
    when:
      branch: develop
      event: push

  - name: build-production
    image: plugins/docker
    settings:
      repo: myapp/prod
      auto_tag: true
    when:
      branch: main
      event: push

  - name: notify-slack
    image: plugins/slack
    settings:
      webhook:
        from_secret: slack_webhook
      channel: deployments
      template: >
        {{ success "#Build {{build.number}} succeeded"}}
        {{ failure "#Build {{build.number}} failed"}}
```

### 使用全局变量

```yaml
kind: pipeline
type: docker
name: default

platform:
  os: linux
  arch: amd64

settings:
  DOCKER_REGISTRY: docker.io
  APP_NAME: myapp

steps:
  - name: build
    image: docker:dind
    environment:
      DOCKER_HOST: tcp://docker:2375
    commands:
      - docker build -t $DOCKER_REGISTRY/$APP_NAME:$DRONE_COMMIT_SHA .
      - docker push $DOCKER_REGISTRY/$APP_NAME:$DRONE_COMMIT_SHA
```

## 第七步：安全加固

### 防火墙配置

```bash
# 只允许必要端口
sudo ufw allow 22/tcp      # SSH
sudo ufw allow 80/tcp      # HTTP
sudo ufw allow 443/tcp     # HTTPS
sudo ufw deny 8000/tcp     # 隐藏 Drone 直接访问

# 启用防火墙
sudo ufw enable
```

### 限制访问

```bash
# 在 .drone.yml 中限制特定分支
when:
  branch: main

# 或使用 whitelist
whitelist:
  branches: [main, release/*]
  events: [push, tag]
```

### 定期备份

```bash
#!/bin/bash
# backup-drone.sh

BACKUP_DIR="/backup/drone"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/drone-backup-$TIMESTAMP.tar.gz"

# 创建备份目录
mkdir -p $BACKUP_DIR

# 备份数据卷
docker run --rm \
  -v drone_ci_drone-data:/data \
  -v $BACKUP_DIR:/backup \
  alpine tar czf /backup/drone-backup-$TIMESTAMP.tar.gz -C /data .

# 保留最近 7 天的备份
find $BACKUP_DIR -name "drone-backup-*.tar.gz" -mtime +7 -delete

echo "Backup completed: $BACKUP_FILE"
```

添加到 crontab：
```bash
crontab -e
# 每天凌晨 3 点备份
0 3 * * * /path/to/backup-drone.sh >> /var/log/drone-backup.log 2>&1
```

## 常见问题与解决

### 问题 1：Agent 无法连接到 Server

```bash
# 检查网络连通性
docker exec drone-agent ping drone-server

# 查看 Agent 日志
docker logs drone-agent

# 常见原因：
# 1. DRONE_RPC_SECRET 不匹配
# 2. 防火墙阻止了 8000 端口
# 3. DNS 解析问题
```

### 问题 2：构建步骤超时

```yaml
# 增加超时时间
steps:
  - name: build
    image: node:20
    commands:
      - npm run build
    timeout: 3600  # 60 分钟超时
```

### 问题 3：Docker-in-Docker 权限问题

```bash
# 确保 Docker socket 正确挂载
docker inspect drone-agent | grep -A 5 Mounts

# 如果使用 DinD，需要特权模式
environment:
  - DOCKER_TLS_CERTDIR=""
  - DOCKER_HOST=tcp://docker:2375
```

### 问题 4：Webhook 未触发

```bash
# 检查 GitHub webhook 配置
# 1. 进入仓库 Settings > Webhooks
# 2. 确认 Payload URL: http://your-domain/hook
# 3. 确认 Content type: application/json
# 4. 测试 webhook 发送

# 查看 Drone 日志
docker logs drone-server | grep webhook
```

## 性能优化建议

### 资源限制

```yaml
# drone-agent 配置
environment:
  - DRONE_RUNNER_CAPACITY=4      # 最大并发构建数
  - DRONE_RUNNER_THREADS=4       # 线程数
  - DRONE_RUNNER_KEEPALIVE_ENABLED=true
```

### 使用预构建镜像

```yaml
steps:
  - name: build
    image: node:20-alpine  # 使用精简版镜像
    commands:
      - npm run build
```

### 启用结果缓存

```yaml
# 在项目中配置缓存
steps:
  - name: cache-node-modules
    image: alpine
    commands:
      - tar xzf node_modules.tar.gz || npm ci
    when:
      status: [success, failure]
```

## 总结

Drone CI 是一个非常适合 VPS 环境的轻量级 CI/CD 解决方案：

| 特性 | Drone CI | GitLab CI | GitHub Actions |
|------|----------|-----------|----------------|
| 内存占用 | ~50MB | ~500MB+ | N/A (云端) |
| 学习曲线 | ⭐⭐ 低 | ⭐⭐⭐ 中 | ⭐⭐ 低 |
| 配置复杂度 | 简单 YAML | 复杂 YAML | 简单 YAML |
| 自托管成本 | 极低 | 高 | 无 |
| 插件数量 | 100+ | 丰富 | 丰富 |
| 社区活跃度 | 活跃 | 非常活跃 | 非常活跃 |

对于 1-4GB 内存的 VPS，Drone CI 是理想选择。配合 Docker 使用，可以轻松管理多个项目的构建流水线。

---

*本文基于 Drone CI v2.x 编写，适用于 Ubuntu 20.04+/Debian 11+ 系统。*