---
title: "VPS 自建 GitHub Actions Runner：彻底解决 GitHub Actions 配额不足与费用爆炸"
description: "GitHub Actions 免费版每小时配额严重限制，私有仓库每分钟收费也不便宜。用 VPS 自建自托管 Runner，免费无限制，完全掌控 CI/CD 流水线，成本直降 90%+"
date: 2026-08-09T10:00:00+08:00
lastmod: 2026-08-09T10:00:00+08:00
slug: "self-hosted-github-actions-runner"
image: /images/posts/self-hosted-github-actions-runner/featured.png
tags: ["GitHub Actions", "CI/CD", "自托管", "Runner", "VPS", "DevOps", "自动化", "省钱"]
categories: ["CI/CD 优化"]
aliases: [/zh/post/self-hosted-github-actions-runner/]
---

## 引言

GitHub Actions 是目前最流行的 CI/CD 工具，GitHub 提供的免费额度对于个人项目和小团队来说相当慷慨：**免费账户每月 2,000 分钟（公共仓库无限），私有仓库每月 500 分钟**。

但当你开始认真对待 CI/CD 时，这些限制很快就成了瓶颈：

- **构建大型项目**（比如编译 Go、构建 React 生产包、运行全量测试套件）每次消耗 10-30 分钟，几个流水线跑完配额就见底
- **私有仓库每分钟 $0.008**，如果一天跑 100 次流水线，每月轻松超 $20
- **并发限制**：免费账户只能 2 个并发作业，复杂项目根本跑不动
- **网络限制**：GitHub 服务器在全球，拉取国内镜像速度慢如蜗牛

**自托管 Runner** 是终极解决方案——在 VPS 上部署自己的 Runner，完全免费、无限并发、无网络限制，成本直降 90% 以上。

---

## 一、为什么自建 Runner 性价比极高

### 费用对比

| 项目 | GitHub Hosted | 自建 Runner (2核4G VPS) |
|------|---------------|----------------------|
| 月成本 | $0 ~ $200+ | $5 ~ $10 |
| 并发限制 | 2 ~ 20 | 无限制 |
| 网络 | GitHub 全球 | 你的网络（国内可极快） |
| 自定义环境 | 固定镜像 | 完全可控 |
| 数据隐私 | 数据过 GitHub | 完全私有 |

**算一笔账**：如果你每月花 $50 在 GitHub Actions 上，换成 $10 的 VPS + 自建 Runner，每月省 $40，一年省 $480。

### 适用场景

- 高频构建（每天 20+ 次）
- 大型项目（编译耗时长）
- 国内项目（需要高速国内网络）
- 私有敏感项目（数据不出境）
- 需要自定义环境（Docker、特定运行时）

---

## 二、架构设计

### 核心组件

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────┐
│  GitHub      │────▶│  Self-hosted     │────▶│  VPS Runner  │
│  (Webhook)   │     │  Runner Agent    │     │  (Docker)    │
└─────────────┘     └──────────────────┘     └─────────────┘
                                              │
                                       ┌──────┴──────┐
                                       │  Docker     │
                                       │  Build      │
                                       │  Cache      │
                                       │  Artifacts  │
                                       └─────────────┘
```

### 关键设计决策

1. **Docker-in-Docker (DinD)**：Runner 在 Docker 容器中运行，每个 Job 独立容器，互不干扰
2. **自动扩缩容**：根据队列长度自动启停 Runner 实例
3. **缓存共享**：使用本地缓存或对象存储共享构建缓存
4. **安全隔离**：Runner 与宿主系统隔离，防止构建任务越权

---

## 三、环境准备

### 3.1 选择 VPS

推荐配置：
- **最低**：2 vCPU / 4GB RAM / 40GB SSD
- **推荐**：4 vCPU / 8GB RAM / 100GB SSD
- **高负载**：8 vCPU / 16GB RAM / 200GB SSD

推荐 VPS 提供商：
- **轻量应用服务器**：腾讯云/阿里云，国内访问快
- **Vultr / DigitalOcean**：海外稳定，支持按小时计费
- **Hetzner**：欧洲性价比最高（€3.5/月起）

### 3.2 安装 Docker

```bash
# Ubuntu/Debian
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# 验证
docker --version
docker run hello-world
```

### 3.3 准备 GitHub Token

在 GitHub 仓库设置中生成 Personal Access Token (PAT)：
1. 进入 `Settings → Developer settings → Personal access tokens → Tokens (classic)`
2. 点击 "Generate new token (classic)"
3. 勾选以下权限：
   - `repo` (全权限)
   - `workflow` (读写)
4. 复制 token，后续配置需要用到

---

## 四、部署自托管 Runner

### 4.1 创建 GitHub Runner 组织/仓库级别

**仓库级 Runner**（适合单个项目）：
1. 进入仓库 `Settings → Actions → Runners`
2. 点击 "New runner"
3. 下载并配置 Runner 包

**组织级 Runner**（适合多个项目共享）：
1. 进入组织 `Settings → Actions → Runners`
2. 选择 "New organization runner"

### 4.2 在 VPS 上运行 Runner

```bash
# 创建 runner 目录
mkdir -p ~/actions-runner && cd ~/actions-runner

# 下载最新 Runner（以 v2.318.0 为例）
RUNNER_VERSION="2.318.0"
curl -O -L https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz
tar xzf ./actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz

# 配置 Runner
./config.sh --url https://github.com/<your-org>/<your-repo> \
  --token <YOUR_PAT_TOKEN> \
  --name my-runner \
  --labels self-hosted,linux,x64 \
  --work /tmp/actions-runner-work

# 启动 Runner（前台运行，用于测试）
./run.sh
```

### 4.3 使用 systemd 管理（生产推荐）

```bash
sudo nano /etc/systemd/system/github-runner.service
```

```ini
[Unit]
Description=GitHub Actions Runner
After=network.target docker.service
Requires=docker.service

[Service]
Type=simple
User=root
WorkingDirectory=/root/actions-runner
ExecStart=/root/actions-runner/run.sh
ExecStop=/root/actions-runner/bin/RunnerService stop
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable github-runner
sudo systemctl start github-runner
sudo systemctl status github-runner
```

---

## 五、Docker-in-Docker 配置

### 5.1 安装 Docker Runner 代理

GitHub 官方提供了 Docker 版本的 Runner，自动处理 DinD：

```bash
# 使用 Docker Compose 部署
cat > docker-compose.yml << 'EOF'
version: '3.8'

services:
  runner:
    image: ghcr.io/actions/runner:latest
    container_name: github-runner
    environment:
      - RUNNER_URL=https://github.com/<your-org>/<your-repo>
      - RUNNER_TOKEN=<YOUR_TOKEN>
      - RUNNER_NAME=my-runner
      - RUNNER_WORKDIR=/tmp/actions-runner-work
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - runner-data:/tmp/actions-runner-work
    restart: unless-stopped

volumes:
  runner-data:
EOF

docker-compose up -d
```

### 5.2 验证 Runner 在线

在 GitHub 仓库 `Settings → Actions → Runners` 中，应该能看到你的 Runner 显示绿色在线状态。

---

## 六、CI/CD 流水线配置

### 6.1 基础流水线示例

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  build:
    runs-on: [self-hosted, linux, x64]  # 使用自托管 Runner
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'
          
      - name: Install dependencies
        run: npm ci
        
      - name: Run tests
        run: npm test
        
      - name: Build
        run: npm run build
```

### 6.2 多 Runner 标签配置

根据项目需求，可以给 Runner 打不同标签：

```bash
# 创建多个 Runner，用于不同场景
./config.sh --url https://github.com/<org>/<repo> \
  --token <token> \
  --name runner-build \
  --labels self-hosted,linux,x64,build
  
./config.sh --url https://github.com/<org>/<repo> \
  --token <token> \
  --name runner-test \
  --labels self-hosted,linux,x64,test
```

在流水线中指定：
```yaml
jobs:
  build:
    runs-on: [self-hosted, linux, x64, build]
  test:
    runs-on: [self-hosted, linux, x64, test]
```

---

## 七、性能优化

### 7.1 构建缓存

使用 `actions/cache` 加速依赖安装：

```yaml
- uses: actions/cache@v4
  with:
    path: |
      ~/.npm
      node_modules
    key: ${{ runner.os }}-node-${{ hashFiles('**/package-lock.json') }}
    restore-keys: |
      ${{ runner.os }}-node-
```

### 7.2 并行构建

使用 `matrix` 并行测试：

```yaml
jobs:
  test:
    runs-on: [self-hosted, linux, x64]
    strategy:
      matrix:
        node-version: [18, 20, 22]
        os: [ubuntu-latest]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: ${{ matrix.node-version }}
      - run: npm ci
      - run: npm test
```

### 7.3 资源限制

防止单个 Job 耗尽资源：

```bash
# 在 Runner 上配置 Docker 资源限制
docker run -d \
  --cpus=4 \
  --memory=8g \
  --name runner \
  ghcr.io/actions/runner:latest
```

---

## 八、高可用与扩展

### 8.1 多 Runner 负载均衡

```yaml
# 自动扩缩容脚本（示例）
#!/bin/bash
# auto-scaler.sh

QUEUE_SIZE=$(curl -s https://api.github.com/repos/<org>/<repo>/actions/runners | jq '.total_count')
MAX_RUNNERS=5

if [ $QUEUE_SIZE -gt 3 ] && [ $RUNNER_COUNT -lt $MAX_RUNNERS ]; then
  docker-compose up -d --scale runner=$RUNNER_COUNT
fi
```

### 8.2 灾难恢复

```bash
# 备份 Runner 配置
tar czf runner-backup-$(date +%Y%m%d).tar.gz ~/actions-runner/

# 恢复
tar xzf runner-backup-20260809.tar.gz -C /
```

---

## 九、安全加固

### 9.1 Runner 隔离

```yaml
# docker-compose.yml
services:
  runner:
    security_opt:
      - no-new-privileges:true
    read_only: true
    tmpfs:
      - /tmp
    cap_drop:
      - ALL
```

### 9.2 网络隔离

```bash
# 限制 Runner 只能访问必要的网络
docker network create runner-net
# 在网络中只允许访问构建所需的端点
```

### 9.3 Token 管理

- 使用短生命周期 Token（GitHub 支持 30 天有效期）
- 定期轮换 Token
- 不要在代码中硬编码 Token

---

## 十、成本计算与 ROI

### 10.1 月度成本对比

**场景**：每月运行 200 小时构建

| 方案 | GitHub Actions | 自建 Runner |
|------|---------------|-------------|
| 基础费用 | $100+ | $10 |
| 带宽费用 | 包含在内 | $0 |
| 维护成本 | 0 | 0.5 小时/周 |
| **总计** | **$100+** | **$10** |

### 10.2 投资回报

- **初始投入**：VPS 设置 2-4 小时
- **每月节省**：$90+
- **回本周期**：1 个月
- **年化节省**：$1,080+

---

## 十一、常见问题排查

### 11.1 Runner 无法连接 GitHub

```bash
# 检查网络
curl -I https://github.com

# 检查 Token 是否过期
# 重新获取 Token 并更新配置
```

### 11.2 构建失败，但本地正常

```bash
# 检查 Runner 日志
sudo journalctl -u github-runner -f

# 检查 Docker 版本兼容性
docker version
```

### 11.3 资源不足

```bash
# 监控资源使用
htop
docker stats

# 清理未使用的镜像和容器
docker system prune -a
```

---

## 总结

自建 GitHub Actions Runner 是 VPS 自托管的典范案例：

1. **成本骤降**：从 $100+/月降至 $10/月，节省 90%+
2. **性能提升**：无并发限制，国内网络极速
3. **完全掌控**：自定义环境、数据安全、灵活扩展
4. **易于维护**：Docker 一键部署，systemd 自动重启

对于任何频繁使用 GitHub Actions 的个人开发者或小团队，自建 Runner 都是最具性价比的投资。

**立即行动**：
1. 注册一个便宜的 VPS（$5/月起）
2. 部署 GitHub Actions Runner
3. 将 CI/CD 流水线迁移到自托管 Runner
4. 享受免费无限的构建体验！

---

## 英文版本

---

# Self-Hosted GitHub Actions Runner on VPS: Solve Quota Limits & Cut Costs by 90%+

## Introduction

GitHub Actions is the most popular CI/CD tool. GitHub offers generous free tiers: **2,000 minutes/month for free accounts (unlimited for public repos), 500 minutes/month for private repos**.

But when you take CI/CD seriously, these limits become bottlenecks quickly:

- **Building large projects** (compiling Go, building React production bundles, running full test suites) consumes 10-30 minutes per build. A few pipelines and your quota is gone
- **Private repos cost $0.008/minute** — 100 runs per day easily exceeds $20/month
- **Concurrency limits**: Free accounts only support 2 concurrent jobs, impossible for complex projects
- **Network limitations**: GitHub servers are global, pulling国内镜像 from China is painfully slow

**Self-hosted Runners** are the ultimate solution — deploy your own Runner on a VPS, completely free, unlimited concurrency, no network restrictions, cutting costs by 90%+.

---

## Why Self-Hosted Runners Are Extremely Cost-Effective

### Cost Comparison

| Item | GitHub Hosted | Self-Hosted (2C4G VPS) |
|------|---------------|----------------------|
| Monthly Cost | $0 ~ $200+ | $5 ~ $10 |
| Concurrency Limit | 2 ~ 20 | Unlimited |
| Network | GitHub Global | Your network (fast in China) |
| Custom Environment | Fixed images | Fully controllable |
| Data Privacy | Data via GitHub | Fully private |

**Do the math**: If you spend $50/month on GitHub Actions, switch to a $10 VPS with self-hosted Runner, save $40/month, $480/year.

### When to Use

- High-frequency builds (20+ per day)
- Large projects (long compile times)
- China-based projects (need fast domestic network)
- Private sensitive projects (data stays in-house)
- Custom environment needs (Docker, specific runtimes)

---

## Architecture Design

### Core Components

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────┐
│  GitHub      │────▶│  Self-hosted     │────▶│  VPS Runner  │
│  (Webhook)   │     │  Runner Agent    │     │  (Docker)    │
└─────────────┘     └──────────────────┘     └─────────────┘
                                              │
                                       ┌──────┴──────┐
                                       │  Docker     │
                                       │  Build      │
                                       │  Cache      │
                                       │  Artifacts  │
                                       └─────────────┘
```

### Key Design Decisions

1. **Docker-in-Docker (DinD)**: Runner runs in Docker container, each Job gets independent container
2. **Auto-scaling**: Automatically start/stop Runner instances based on queue length
3. **Shared cache**: Use local cache or object storage for shared build cache
4. **Security isolation**: Runner isolated from host system, preventing privilege escalation

---

## Environment Preparation

### 3.1 Choose a VPS

Recommended specs:
- **Minimum**: 2 vCPU / 4GB RAM / 40GB SSD
- **Recommended**: 4 vCPU / 8GB RAM / 100GB SSD
- **High load**: 8 vCPU / 16GB RAM / 200GB SSD

Recommended providers:
- **Lightweight App Servers**: Tencent Cloud / Alibaba Cloud, fast domestic access
- **Vultr / DigitalOcean**: Stable overseas, pay-per-hour
- **Hetzner**: Best value in Europe (from €3.5/month)

### 3.2 Install Docker

```bash
# Ubuntu/Debian
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# Verify
docker --version
docker run hello-world
```

### 3.3 Prepare GitHub Token

Generate a Personal Access Token (PAT) in GitHub repo settings:
1. Go to `Settings → Developer settings → Personal access tokens → Tokens (classic)`
2. Click "Generate new token (classic)"
3. Select these permissions:
   - `repo` (full control)
   - `workflow` (read/write)
4. Copy the token for later use

---

## Deploy Self-Hosted Runner

### 4.1 Create Organization/Repository Level Runner

**Repository-level Runner** (for single project):
1. Go to repo `Settings → Actions → Runners`
2. Click "New runner"
3. Download and configure Runner package

**Organization-level Runner** (shared across multiple projects):
1. Go to org `Settings → Actions → Runners`
2. Select "New organization runner"

### 4.2 Run Runner on VPS

```bash
# Create runner directory
mkdir -p ~/actions-runner && cd ~/actions-runner

# Download latest Runner (v2.318.0 example)
RUNNER_VERSION="2.318.0"
curl -O -L https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz
tar xzf ./actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz

# Configure Runner
./config.sh --url https://github.com/<your-org>/<your-repo> \
  --token <YOUR_PAT_TOKEN> \
  --name my-runner \
  --labels self-hosted,linux,x64 \
  --work /tmp/actions-runner-work

# Start Runner (foreground for testing)
./run.sh
```

### 4.3 Use systemd for Production

```bash
sudo nano /etc/systemd/system/github-runner.service
```

```ini
[Unit]
Description=GitHub Actions Runner
After=network.target docker.service
Requires=docker.service

[Service]
Type=simple
User=root
WorkingDirectory=/root/actions-runner
ExecStart=/root/actions-runner/run.sh
ExecStop=/root/actions-runner/bin/RunnerService stop
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable github-runner
sudo systemctl start github-runner
sudo systemctl status github-runner
```

---

## Docker-in-Docker Configuration

### 5.1 Install Docker Runner Agent

GitHub provides an official Docker version of Runner that auto-handles DinD:

```bash
# Deploy with Docker Compose
cat > docker-compose.yml << 'EOF'
version: '3.8'

services:
  runner:
    image: ghcr.io/actions/runner:latest
    container_name: github-runner
    environment:
      - RUNNER_URL=https://github.com/<your-org>/<your-repo>
      - RUNNER_TOKEN=<YOUR_TOKEN>
      - RUNNER_NAME=my-runner
      - RUNNER_WORKDIR=/tmp/actions-runner-work
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - runner-data:/tmp/actions-runner-work
    restart: unless-stopped

volumes:
  runner-data:
EOF

docker-compose up -d
```

### 5.2 Verify Runner Online

In GitHub repo `Settings → Actions → Runners`, you should see your Runner showing green online status.

---

## CI/CD Pipeline Configuration

### 6.1 Basic Pipeline Example

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  build:
    runs-on: [self-hosted, linux, x64]  # Use self-hosted Runner
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'
          
      - name: Install dependencies
        run: npm ci
        
      - name: Run tests
        run: npm test
        
      - name: Build
        run: npm run build
```

### 6.2 Multi-Runner Label Configuration

Create different runners for different scenarios:

```bash
# Create multiple runners for different use cases
./config.sh --url https://github.com/<org>/<repo> \
  --token <token> \
  --name runner-build \
  --labels self-hosted,linux,x64,build
  
./config.sh --url https://github.com/<org>/<repo> \
  --token <token> \
  --name runner-test \
  --labels self-hosted,linux,x64,test
```

Specify in pipeline:
```yaml
jobs:
  build:
    runs-on: [self-hosted, linux, x64, build]
  test:
    runs-on: [self-hosted, linux, x64, test]
```

---

## Performance Optimization

### 7.1 Build Cache

Use `actions/cache` to speed up dependency installation:

```yaml
- uses: actions/cache@v4
  with:
    path: |
      ~/.npm
      node_modules
    key: ${{ runner.os }}-node-${{ hashFiles('**/package-lock.json') }}
    restore-keys: |
      ${{ runner.os }}-node-
```

### 7.2 Parallel Builds

Use `matrix` for parallel testing:

```yaml
jobs:
  test:
    runs-on: [self-hosted, linux, x64]
    strategy:
      matrix:
        node-version: [18, 20, 22]
        os: [ubuntu-latest]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: ${{ matrix.node-version }}
      - run: npm ci
      - run: npm test
```

### 7.3 Resource Limits

Prevent single Job from consuming all resources:

```bash
# Configure Docker resource limits on Runner
docker run -d \
  --cpus=4 \
  --memory=8g \
  --name runner \
  ghcr.io/actions/runner:latest
```

---

## High Availability & Scaling

### 8.1 Multi-Runner Load Balancing

```bash
# Auto-scaling script (example)
#!/bin/bash
# auto-scaler.sh

QUEUE_SIZE=$(curl -s https://api.github.com/repos/<org>/<repo>/actions/runners | jq '.total_count')
MAX_RUNNERS=5

if [ $QUEUE_SIZE -gt 3 ] && [ $RUNNER_COUNT -lt $MAX_RUNNERS ]; then
  docker-compose up -d --scale runner=$RUNNER_COUNT
fi
```

### 8.2 Disaster Recovery

```bash
# Backup Runner configuration
tar czf runner-backup-$(date +%Y%m%d).tar.gz ~/actions-runner/

# Restore
tar xzf runner-backup-20260809.tar.gz -C /
```

---

## Security Hardening

### 9.1 Runner Isolation

```yaml
# docker-compose.yml
services:
  runner:
    security_opt:
      - no-new-privileges:true
    read_only: true
    tmpfs:
      - /tmp
    cap_drop:
      - ALL
```

### 9.2 Network Isolation

```bash
# Restrict Runner to only necessary networks
docker network create runner-net
# Only allow access to endpoints needed for builds
```

### 9.3 Token Management

- Use short-lived Tokens (GitHub supports 30-day validity)
- Rotate tokens regularly
- Don't hardcode tokens in code

---

## Cost Calculation & ROI

### 10.1 Monthly Cost Comparison

**Scenario**: 200 hours of builds per month

| Plan | GitHub Actions | Self-Hosted Runner |
|------|---------------|-------------------|
| Base Cost | $100+ | $10 |
| Bandwidth | Included | $0 |
| Maintenance | 0 | 0.5 hours/week |
| **Total** | **$100+** | **$10** |

### 10.2 Return on Investment

- **Initial investment**: 2-4 hours VPS setup
- **Monthly savings**: $90+
- **Break-even**: 1 month
- **Annual savings**: $1,080+

---

## Common Troubleshooting

### 11.1 Runner Cannot Connect to GitHub

```bash
# Check network
curl -I https://github.com

# Check if Token expired
# Re-fetch Token and update configuration
```

### 11.2 Build Fails Locally But Works on Runner

```bash
# Check Runner logs
sudo journalctl -u github-runner -f

# Check Docker version compatibility
docker version
```

### 11.3 Resource Exhaustion

```bash
# Monitor resource usage
htop
docker stats

# Clean up unused images and containers
docker system prune -a
```

---

## Summary

Self-hosted GitHub Actions Runner is a prime example of VPS self-hosting:

1. **Cost plunge**: From $100+/month to $10/month, saving 90%+
2. **Performance boost**: No concurrency limits, ultra-fast domestic network
3. **Full control**: Custom environment, data security, flexible scaling
4. **Easy maintenance**: One-click Docker deployment, systemd auto-restart

For any individual developer or small team that frequently uses GitHub Actions, self-hosted Runner is the most cost-effective investment.

**Get started now**:
1. Register a cheap VPS (from $5/month)
2. Deploy GitHub Actions Runner
3. Migrate CI/CD pipelines to self-hosted Runner
4. Enjoy free unlimited builds!
