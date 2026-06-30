---
title: "自建 GitLab CI/CD 流水线：从零搭建完整的持续集成与部署平台"
description: "在 VPS 上从零部署 GitLab CI/CD 完整流水线，涵盖 Runner 配置、Docker-in-Docker 构建、自动化部署到生产环境，以及最佳实践和故障排查指南。"
date: 2026-06-30T10:00:00+08:00
lastmod: 2026-06-30T10:00:00+08:00
slug: "gitlab-cicd-selfhosted-guide"
tags: ["GitLab", "CI/CD", "DevOps", "Docker", "自动化部署", "Runner", "持续集成", "VPS"]
categories: ["部署教程"]
draft: false
image: /images/posts/gitlab-cicd-selfhosted-guide/featured.png
aliases: [/zh/post/gitlab-cicd-selfhosted-guide/]
---

## 为什么自建 GitLab CI/CD？

在自托管和 VPS 运维领域，CI/CD（持续集成/持续部署）是提升开发效率的核心基础设施。GitHub Actions 和 GitLab CI 是目前最流行的两个选择。对于重视数据主权、隐私和成本控制的团队来说，自建 GitLab CI/CD 有以下优势：

- **完全掌控**：代码、构建产物、部署流程全部在自己手中
- **成本可控**：无第三方平台按分钟计费，适合长期运行重型任务
- **灵活定制**：可自定义 Runner 资源、构建环境和部署策略
- **离线可用**：内网环境也能正常工作

## 架构概览

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   GitLab     │────▶│  GitLab CI   │────▶│  Runner     │
│   Server     │     │  (Pipeline)  │     │  (Docker)   │
│  :8080/:443  │     │              │     │             │
└─────────────┘     └──────────────┘     └──────┬──────┘
                                                │
                                        ┌───────▼────────┐
                                        │  Target Server │
                                        │  (Staging/Prod)│
                                        └────────────────┘
```

## 第一步：部署 GitLab 服务器

### 使用 Docker Compose 一键部署

推荐使用官方 GitLab Omnibus 镜像，配合 Docker Compose 管理：

```yaml
# docker-compose.yml
version: '3.8'

services:
  gitlab:
    image: gitlab/gitlab-ce:latest
    container_name: gitlab
    hostname: gitlab.example.com
    ports:
      - "80:80"
      - "443:443"
      - "2222:22"
    volumes:
      - ./config:/etc/gitlab
      - ./logs:/var/log/gitlab
      - ./data:/var/opt/gitlab
    shm_size: '256m'
    restart: unless-stopped
    mem_limit: 8g
    cpus: 4
```

### 初始配置

首次启动后，修改 `/config/gitlab.rb`：

```ruby
# 外部 URL
external_url 'https://gitlab.example.com'

# SSH 端口映射
gitlab_rails['gitlab_shell_ssh_port'] = 2222

# 内存优化（适用于 4GB VPS）
unicorn['worker_memory_min'] = 5
unicorn['worker_memory_max'] = 150

# 备份策略
gitlab_rails['manage_backup_path'] = true
gitlab_rails['backup_path'] = "/var/opt/gitlab/backups"
gitlab_rails['backup_keep_time'] = 604800  # 保留7天
```

### 重新配置并启动

```bash
docker compose up -d
# 等待 GitLab 初始化（首次启动可能需要 5-10 分钟）
docker exec -it gitlab gitlab-ctl reconfigure
```

## 第二步：配置 GitLab Runner

Runner 是实际执行 CI/CD 任务的组件。推荐使用 Docker Executor 模式。

### 注册 Runner

```bash
# 获取注册令牌（从 GitLab Web UI: Settings > CI/CD > Runners）
docker run --rm -v /srv/gitlab-runner/config:/etc/gitlab-runner \
  gitlab/gitlab-runner:latest \
  register \
  --non-interactive \
  --url "https://gitlab.example.com" \
  --registration-token "YOUR_REGISTRATION_TOKEN" \
  --executor "docker" \
  --description "Docker Runner" \
  --docker-image "docker:latest" \
  --docker-volumes /var/run/docker.sock:/var/run/docker.sock \
  --tag-list "docker,linux" \
  --locked="false" \
  --run-untagged="true"
```

### Docker-in-Docker (DinD) 模式

如果需要容器化构建（例如构建 Docker 镜像），使用 DinD：

```yaml
# gitlab-runner/config/config.toml
[[runners]]
  executor = "docker"
  [runners.docker]
    image = "docker:latest"
    privileged = true
    disable_entrypoint_overwrite = false
    oom_kill_disable = false
    disable_cache = false
    volumes = ["/cache"]
    shm_size = 0
```

### 多 Runner 策略

| Runner 类型 | 适用场景 | 标签 |
|------------|---------|------|
| 共享 Runner | 小型项目，轻量构建 | `docker`, `linux` |
| 专用 Runner | 大型项目，GPU 构建 | `gpu`, `large` |
| 环境 Runner | 仅部署到特定环境 | `staging`, `production` |

## 第三步：编写 .gitlab-ci.yml

### 基础流水线模板

```yaml
# .gitlab-ci.yml
stages:
  - build
  - test
  - deploy-staging
  - deploy-production

variables:
  DOCKER_IMAGE: $CI_REGISTRY_IMAGE:$CI_COMMIT_SHORT_SHA
  DEPLOY_SERVER: "deploy@example.com"
  DEPLOY_PATH: "/var/www/app"

# 代码检查阶段
lint:
  stage: build
  image: node:20-alpine
  script:
    - npm ci
    - npm run lint
  rules:
    - changes:
        - "src/**/*"
        - "package.json"

# 构建阶段
build:
  stage: build
  image: docker:24-dind
  services:
    - docker:24-docker
  variables:
    DOCKER_TLS_CERTDIR: ""
  script:
    - docker login -u $CI_REGISTRY_USER -p $CI_REGISTRY_PASSWORD $CI_REGISTRY
    - docker build -t $DOCKER_IMAGE .
    - docker push $DOCKER_IMAGE
  rules:
    - if: '$CI_COMMIT_BRANCH == "main"'
    - if: '$CI_COMMIT_BRANCH == "develop"'

# 测试阶段
test:
  stage: test
  image: node:20-alpine
  script:
    - npm ci
    - npm run test:coverage
  coverage: '/Lines\s*:\s*(\d+.?\d*)/'
  artifacts:
    reports:
      coverage_report:
        coverage_format: cobertura
        path: "coverage/cobertura-coverage.xml"
  rules:
    - changes:
        - "src/**/*"

# 部署到预发布环境
deploy-staging:
  stage: deploy-staging
  image: alpine:latest
  script:
    - apk add --no-cache openssh-client rsync
    - eval $(ssh-agent -s)
    - echo "$SSH_PRIVATE_KEY" | ssh-add -
    - ssh-keyscan -H $DEPLOY_SERVER >> ~/.ssh/known_hosts
    - rsync -avz --delete -e "ssh -o StrictHostKeyChecking=no" \
        ./ $DEPLOY_SERVER:$DEPLOY_PATH/staging/
    - ssh $DEPLOY_SERVER "cd $DEPLOY_PATH/staging && docker compose up -d"
  environment:
    name: staging
    url: https://staging.gitlab.example.com
  rules:
    - if: '$CI_COMMIT_BRANCH == "main"'

# 部署到生产环境（需手动触发）
deploy-production:
  stage: deploy-production
  image: alpine:latest
  script:
    - apk add --no-cache openssh-client rsync
    - eval $(ssh-agent -s)
    - echo "$SSH_PRIVATE_KEY" | ssh-add -
    - ssh-keyscan -H $DEPLOY_SERVER >> ~/.ssh/known_hosts
    - rsync -avz --delete -e "ssh -o StrictHostKeyChecking=no" \
        ./ $DEPLOY_SERVER:$DEPLOY_PATH/production/
    - ssh $DEPLOY_SERVER "cd $DEPLOY_PATH/production && docker compose up -d"
  environment:
    name: production
    url: https://gitlab.example.com
  rules:
    - if: '$CI_COMMIT_BRANCH == "main"'
      when: manual
```

### 多语言项目配置示例

#### Python 项目

```yaml
.python-test:
  image: python:3.12-slim
  variables:
    PIP_CACHE_DIR: "$CI_PROJECT_DIR/.cache/pip"
  cache:
    key: "${CI_COMMIT_REF_SLUG}-pip"
    paths:
      - .cache/pip
  before_script:
    - pip install --upgrade pip
    - pip install -r requirements.txt
    - pip install pytest pytest-cov

unit-tests:
  extends: .python-test
  stage: test
  script:
    - pytest tests/ --cov=app --cov-report=xml
  artifacts:
    reports:
      coverage_report:
        coverage_format: cobertura
        path: coverage.xml
```

#### Go 项目

```yaml
.go-build:
  image: golang:1.22-alpine
  cache:
    key: "${CI_COMMIT_REF_SLUG}-go"
    paths:
      - go.mod
      - go.sum
      - ~/go/pkg/mod/
  before_script:
    - go version
    - go mod download

build-binary:
  extends: .go-build
  stage: build
  script:
    - CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o app ./cmd/app
  artifacts:
    paths:
      - app
```

## 第四步：安全配置

### SSH 密钥管理

```bash
# 在 GitLab 中设置 CI/CD 变量
# Settings > CI/CD > Variables

# 推荐的安全做法：
# 1. 使用 Deploy Keys（只读）用于拉取代码
# 2. 使用 CI/CD Variables 存储敏感信息
# 3. 启用变量掩码（Masked）防止日志泄露
# 4. 限制 Runner 作用域（Scoped Runners）
```

### GitLab CI/CD 变量类型

| 变量类型 | 用途 | 示例 |
|---------|------|------|
| Variable | 普通环境变量 | `DEPLOY_PATH=/var/www` |
| File | 写入文件（证书/密钥） | `SSL_CERT_FILE` |
| Masked | 隐藏值（日志中显示 ****） | `SSH_PRIVATE_KEY` |
| Protected | 仅在保护分支上可用 | `PROD_DEPLOY_KEY` |
| Environment | 绑定到特定环境 | `STAGING_URL` |

### 保护分支策略

```yaml
# 在 GitLab Settings > Repository > Protected Branches 中配置：
# main 分支：
#   - 禁止直接推送
#   - 仅允许 Merge Request 合并
#   - 需要至少 1 个 Reviewer 批准
#   - CI 流水线必须全部通过

# 配置 Merge Request 模板
# .merge_request_template.md:
# ## 变更类型
# - [ ] 新功能
# - [ ] Bug 修复
# - [ ] 重构
# - [ ] 文档更新

# ## 测试验证
# - [ ] 单元测试通过
# - [ ] 集成测试通过
# - [ ] 手动测试完成
```

## 第五步：高级技巧

### 缓存优化

```yaml
cache:
  key: "${CI_COMMIT_REF_SLUG}"
  paths:
    - node_modules/
    - .npm/
  policy: pull-push  # 默认策略
  # 可选: pull / push / pull-push

# 多级缓存策略
variables:
  NPM_CACHE_DIR: ".npm"
cache:
  key:
    files:
      - package-lock.json
    prefix: ${CI_COMMIT_REF_SLUG}
  paths:
    - .npm/
```

### 并行流水线

```yaml
# 使用 parallel 并行执行测试
test:parallel:
  stage: test
  image: node:20-alpine
  script:
    - npm run test:parallel
  parallel:
    matrix:
      - SHARD: [1, 2, 3, 4]
  variables:
    TEST_SHARD: $SHARD
```

### 动态环境

```yaml
# 为每个 MR 创建临时环境
deploy-preview:
  stage: deploy-staging
  image: alpine:latest
  script:
    - echo "Deploying to preview-$CI_MERGE_REQUEST_IID"
    - ./scripts/deploy-preview.sh $CI_MERGE_REQUEST_IID
  environment:
    name: preview/$CI_MERGE_REQUEST_IID
    url: https://preview-$CI_MERGE_REQUEST_IID.gitlab.example.com
    on_stop: stop_preview
    stop_action: stop
  rules:
    - if: '$CI_PIPELINE_SOURCE == "merge_request_event"'

stop_preview:
  stage: deploy-staging
  script:
    - docker rm -f preview-$CI_ENVIRONMENT_SLUG
  environment:
    name: preview/$CI_MERGE_REQUEST_IID
    stop_action: stop
  when: manual
```

### 监控与告警

```bash
# 在 Runner 服务器上安装 Node Exporter
# docker-compose.yml for monitoring
services:
  prometheus:
    image: prom/node-exporter:latest
    ports:
      - "9100:9100"
  
  grafana:
    image: grafana/grafana:latest
    ports:
      - "3001:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
```

## 第六步：备份与灾难恢复

### GitLab 数据备份

```bash
# 创建备份
docker exec -t gitlab gitlab-rake gitlab:backup:create

# 自动备份（添加到 crontab）
0 2 * * * docker exec -t gitlab gitlab-rake gitlab:backup:create CRON=1

# 备份文件位置
/var/opt/gitlab/backups/1719705600_2026_06_30_16-4-3_gitlab_backup.tar

# 恢复备份
docker exec -t gitlab gitlab-rake gitlab:backup:restore BACKUP=1719705600_2026_06_30_16-4-3
```

### Runner 配置备份

```bash
# 备份 Runner 配置
cp /srv/gitlab-runner/config/config.toml ~/gitlab-runner-backup/

# 重新注册 Runner（如果丢失配置）
docker run --rm -v /srv/gitlab-runner/config:/etc/gitlab-runner \
  gitlab/gitlab-runner:latest \
  register \
  --token "YOUR_REGISTRATION_TOKEN" \
  --executor "docker" \
  --docker-image "docker:latest"
```

## 常见问题与解决

### 问题 1：Runner 状态一直为 "Online" 但无法执行任务

```bash
# 检查 Runner 日志
docker logs gitlab-runner

# 常见原因：
# 1. Runner 未分配标签匹配
# 2. 项目未启用 Runner
# 3. Docker 权限问题

# 解决方案：
# 确保 Runner 标签与 .gitlab-ci.yml 中的 rules/tags 匹配
# 在 GitLab 中检查：Settings > CI/CD > Runners > 确认 Runner 已关联项目
```

### 问题 2：Docker-in-Docker 构建失败

```bash
# 检查 Docker socket 挂载
docker inspect gitlab-runner | grep -A 5 "Mounts"

# 确保 privileged 模式已启用
# 在 config.toml 中确认：
# [runners.docker]
#   privileged = true

# 如果是内存不足导致，调整 Docker 限制
docker run --memory=2g --cpus=2 --rm docker:latest info
```

### 问题 3：部署到服务器时 SSH 连接超时

```bash
# 测试 SSH 连接
ssh -v -p 22 deploy@example.com

# 常见问题：
# 1. 防火墙阻止了 SSH 端口
# 2. SSH 密钥权限不正确
# 3. known_hosts 文件中存在冲突

# 解决方案：
chmod 600 ~/.ssh/id_rsa
ssh-keygen -R example.com  # 清除旧的 host key
```

## 硬件配置建议

| 规模 | CPU | 内存 | 磁盘 | 适用场景 |
|------|-----|------|------|---------|
| 微型 | 2核 | 4GB | 40GB SSD | 个人项目，1-2 个 Runner |
| 小型 | 4核 | 8GB | 100GB SSD | 小团队，3-5 个 Runner |
| 中型 | 8核 | 16GB | 200GB SSD | 中型团队，5-10 个 Runner |
| 大型 | 16核+ | 32GB+ | 500GB+ NVMe | 企业级，10+ Runner |

## 总结

自建 GitLab CI/CD 流水线是一个值得投入的项目，它能让你在数据主权、成本和灵活性之间取得完美平衡。关键步骤包括：

1. **部署 GitLab 服务器** — 使用 Docker Compose 简化安装
2. **配置 Runner** — 选择合适的 Executor 模式
3. **编写 CI/CD 配置** — 利用 stages、rules 和缓存优化流水线
4. **加强安全** — 合理管理密钥和访问控制
5. **持续优化** — 根据项目需求调整资源配置

通过合理的架构设计和最佳实践，你可以在自己的 VPS 上运行一个功能完备、安全可靠的 CI/CD 平台，完全媲美 GitHub Actions 和 GitLab.com 的功能。
