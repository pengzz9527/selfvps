---
title: "SwarmClaw 部署指南：在 VPS 上搭建自托管多智能体编排平台"
description: "详细教程：在 VPS 上部署 SwarmClaw（500+ ⭐）—— 一款开源自托管的 AI 智能体运行时与多智能体框架，支持群集、MCP 工具、持久记忆、23+ LLM 提供商（含 Ollama），一键 Docker 部署即可 24/7 运行"
date: 2026-05-20T21:30:00+08:00
slug: "swarmclaw-multi-agent-vps-deployment"
tags: ["SwarmClaw", "AI Agent", "多智能体", "自托管", "VPS部署", "Ollama", "Docker", "MCP", "编排"]
categories: ["AI部署"]
aliases: [/zh/post/swarmclaw-multi-agent-vps-deployment/]
draft: false
---

## SwarmClaw 是什么？

[SwarmClaw](https://github.com/swarmclawai/swarmclaw)（GitHub 500+ ⭐）是一个 **开源、自托管的 AI 智能体运行时与多智能体框架**。你可以把它理解成一个 AI 智能体的控制面板——在你自己的服务器上运行、编排和管理整个 AI 智能体团队。

与 Claude Code、ChatGPT 等单智能体工具不同，SwarmClaw 专为**多智能体编排**而设计：

- **智能体群集** — 创建 CEO、开发者、研究员等不同角色的智能体团队，它们可以委派任务、协作并向上汇报
- **23+ LLM 提供商** — 接入 Ollama、Claude、GPT、Gemini、OpenRouter、DeepSeek、Groq 等，每个智能体可使用不同模型
- **持久记忆** — 混合检索、图谱遍历、自动反思记忆，支持项目级上下文
- **MCP 服务器支持** — 接入任意 Model Context Protocol 服务器，扩展网页浏览、代码执行、文件访问等工具
- **消息桥接** — 将智能体连接到 Discord、Slack、Telegram、WhatsApp、邮件等平台
- **定时任务与心跳** — 智能体可按计划运行、自动检查任务状态
- **运行时技能** — 智能体从对话中学习，自动创建可复用的技能

对 VPS 用户来说，核心亮点是：**SwarmClaw 运行在单个 Docker 容器中**，持久化存储数据，连接**本地 Ollama 模型**保障隐私，通过 **Web UI 仪表盘**（`http://你的VPS:3456`）管理整个智能体舰队。

---

## VPS 资源要求

SwarmClaw 是一个 Node.js 应用，作为编排层运行——重度 LLM 推理由外部提供商或单独的 Ollama 实例完成，因此资源消耗较低。

### 最低配置
| 资源 | 要求 | 说明 |
|------|------|------|
| **CPU** | 1 核（x86_64 / ARM64）| ARM 架构也可 |
| **内存** | 1 GB | 系统可用约 512 MB |
| **磁盘** | 10 GB | 含系统 + SwarmClaw + Docker 镜像 |
| **网络** | 公网 IP，开放 3456-3457 端口 | 用于 Web UI 和 API |

### 推荐配置
| 资源 | 要求 | 说明 |
|------|------|------|
| **CPU** | 2 核 | 如需同时运行 Ollama 则需要更多 |
| **内存** | 4 GB | SwarmClaw 占 2 GB，Ollama 占 2 GB |
| **磁盘** | 20 GB SSD | 用于智能体数据 + 本地模型 |
| **网络** | 任意公网 IP | 1 Mbps 即可满足 API 流量 |

### 搭配 Ollama（本地 LLM 推理）
| 资源 | 要求 | 说明 |
|------|------|------|
| **CPU** | 4+ 核 | 无 GPU 时运行 7B 模型需要 |
| **内存** | 8-16 GB | Qwen2.5:7B-Q4 约需 6 GB，Gemma 3:12B 约需 8 GB |
| **GPU** | 可选 | NVIDIA T4 或更高可加速推理 |
| **磁盘** | 30+ GB SSD | 每个模型约 4-8 GB |

---

## 第一步：VPS 环境准备

通过 SSH 连接 VPS，安装 Docker 和 Docker Compose：

```bash
# 更新系统
sudo apt update && sudo apt upgrade -y

# 安装 Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# 安装 Docker Compose 插件
sudo apt install -y docker-compose-plugin

# 将当前用户加入 docker 组
sudo usermod -aG docker $USER

# 重新加载组或退出重新登录
newgrp docker

# 验证安装
docker --version && docker compose version
```

---

## 第二步：通过 Docker Compose 部署 SwarmClaw

```bash
# 创建项目目录
mkdir -p ~/swarmclaw && cd ~/swarmclaw

# 创建持久化数据目录
mkdir -p data

# 创建 docker-compose.yml
cat > docker-compose.yml << 'EOF'
services:
  swarmclaw:
    image: ghcr.io/swarmclawai/swarmclaw:latest
    ports:
      - "3456:3456"
      - "3457:3457"
    volumes:
      - ./data:/app/data
    environment:
      - ACCESS_KEY=your-secure-access-key-here
      - CREDENTIAL_SECRET=your-credential-secret-here
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:3456/api/healthz"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 10s
    restart: unless-stopped
EOF
```

> **安全提示**：使用以下命令生成安全的随机值：
> ```bash
> openssl rand -base64 32  # 用于 ACCESS_KEY
> openssl rand -base64 32  # 用于 CREDENTIAL_SECRET
> ```

启动容器：

```bash
docker compose up -d
```

等待几秒后验证运行状态：

```bash
docker compose ps
curl -s http://localhost:3456/api/healthz | head -c 200
```

你应看到 `{"status":"ok"}`。在浏览器中打开 `http://你的VPS-IP:3456`，使用 `ACCESS_KEY` 作为密码登录。

---

## 第三步：配置 HTTPS（生产环境）

生产环境中，请务必使用 HTTPS 保护 SwarmClaw 面板。搭配 Traefik 反代：

```yaml
services:
  traefik:
    image: traefik:v3.2
    command:
      - "--providers.docker=true"
      - "--entrypoints.websecure.address=:443"
      - "--entrypoints.web.address=:80"
      - "--certificatesresolvers.letsencrypt.acme.tlschallenge=true"
      - "--certificatesresolvers.letsencrypt.acme.email=your@email.com"
      - "--certificatesresolvers.letsencrypt.acme.storage=/letsencrypt/acme.json"
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - "/var/run/docker.sock:/var/run/docker.sock:ro"
      - "./letsencrypt:/letsencrypt"

  swarmclaw:
    image: ghcr.io/swarmclawai/swarmclaw:latest
    expose:
      - "3456"
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.swarmclaw.rule=Host(`swarmclaw.yourdomain.com`)"
      - "traefik.http.routers.swarmclaw.entrypoints=websecure"
      - "traefik.http.routers.swarmclaw.tls.certresolver=letsencrypt"
    volumes:
      - ./data:/app/data
    environment:
      - ACCESS_KEY=your-secure-access-key
      - CREDENTIAL_SECRET=your-credential-secret
    restart: unless-stopped
```

---

## 第四步：连接 Ollama 实现本地 LLM 推理

要完全在 VPS 上运行模型，无需外部 API 调用，可以在 SwarmClaw 旁部署 Ollama。

### 方案 A：Docker Compose 边车容器

在 `docker-compose.yml` 中添加：

```yaml
  ollama:
    image: ollama/ollama:latest
    ports:
      - "11434:11434"
    volumes:
      - ./ollama_data:/root/.ollama
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]  # 无 GPU 则删除此行
    restart: unless-stopped
```

拉取模型：

```bash
docker compose exec ollama ollama pull qwen2.5:7b
# 或对于小内存 VPS：
docker compose exec ollama ollama pull phi-4:3.8b-mini-instruct-q4_K_M
```

### 方案 B：宿主机直接安装（性能更佳）

```bash
# 安装 Ollama
curl -fsSL https://ollama.com/install.sh | sh

# 拉取模型
ollama pull qwen2.5:7b

# 验证
ollama list
```

### 配置 SwarmClaw 使用 Ollama

在 SwarmClaw Web UI 中：
1. 进入 **设置 → 提供商**
2. 点击 **添加提供商**，选择 **Ollama**
3. 基础 URL 设置为 `http://ollama:11434`（Docker 边车）或 `http://host.docker.internal:11434`（宿主机安装）
4. 选择模型如 `qwen2.5:7b`、`llama3.2:3b` 或 `gemma3:12b`

---

## 第五步：创建你的第一个智能体

SwarmClaw 运行并连接提供商后：

1. 打开仪表盘 `http://你的VPS:3456`
2. 点击 **创建智能体**
3. 命名（例如 "DevAssistant"）
4. 选择提供商（Ollama 或 OpenRouter）
5. 选择模型
6. 启用工具：Shell、文件、网页搜索
7. 点击保存

你的智能体已就绪，可以：
- 在 Web UI 中直接对话
- 通过任务面板分配任务
- 设置定时任务
- 连接到 Telegram/Slack 随时随地使用

---

## 第六步：构建多智能体团队（组织架构图）

SwarmClaw 的核心能力是多智能体编排。以下是创建虚拟开发团队的方法：

1. **创建智能体**：

| 智能体 | 角色 | 提供商 | 模型 | 工具 |
|--------|------|--------|------|------|
| Lead | 架构师 | OpenRouter | claude-sonnet-4 | 委派、任务 |
| Dev | 开发者 | Ollama | qwen2.5:7b | Shell、文件 |
| QA | 测试员 | Ollama | llama3.2:3b | Shell、浏览器 |
| Reviewer | 审查员 | OpenRouter | gpt-4o-mini | 文件、网页搜索 |

2. **设置组织架构**：
   - 进入 **组织架构图** 视图
   - 拖拽智能体定义层级关系
   - Lead 委派任务，Dev、QA、Reviewer 领取执行

3. **创建任务**：
   - 点击 **任务 → 新建任务**
   - 标题："实现用户认证模块"
   - 分配给 Lead
   - Lead 会自动分解任务并委派给 Dev

4. **观察群集工作**：
   - 组织架构图实时显示各智能体状态
   - 完成的工作自动返回链路上级审查

---

## 第七步：连接 MCP 服务器扩展工具

Model Context Protocol (MCP) 服务器为智能体提供强大的扩展能力。

### 示例：文件系统 MCP 服务器

```bash
docker run -d \
  --name mcp-filesystem \
  -v /path/to/projects:/projects \
  ghcr.io/modelcontextprotocol/filesystem-server /projects
```

然后在 SwarmClaw 中：
1. 进入 **设置 → MCP 服务器**
2. 点击 **添加 MCP 服务器**
3. 选择类型：**SSE** 或 **Streamable HTTP**
4. 输入端点 URL
5. 为特定智能体启用工具

推荐的 MCP 服务器：
- **Filesystem** — 读写管理文件
- **GitHub** — 创建 PR、管理 Issue、浏览仓库
- **Puppeteer** — 浏览器自动化和截图
- **SQLite** — 查询数据库
- **Memory** — 持久知识图谱

---

## 第八步：生产环境最佳实践

### 数据备份

所有 SwarmClaw 数据保存在 `./data/` 目录下：

```bash
# 备份
tar -czf swarmclaw-backup-$(date +%Y%m%d).tar.gz data/

# 或使用定时任务
0 3 * * * cd ~/swarmclaw && tar -czf backups/swarmclaw-$(date +\%Y\%m\%d).tar.gz data/
```

### 资源限制

防止 SwarmClaw 耗尽 VPS 资源：

```yaml
services:
  swarmclaw:
    deploy:
      resources:
        limits:
          memory: 1G
          cpus: "1"
```

### 监控

SwarmClaw 支持 OpenTelemetry OTLP 导出：

```bash
OTEL_ENABLED=true
OTEL_SERVICE_NAME=swarmclaw
OTEL_EXPORTER_OTLP_ENDPOINT=https://your-collector:4318
```

### 更新

```bash
cd ~/swarmclaw
docker compose pull
docker compose up -d
```

---

## 实际应用场景

### 个人 AI 助手
一个带有记忆、网页访问、定时任务和文件工具的智能体——你的随身副驾驶。连接到 Telegram，随时随地向智能体发送消息。让它检查服务器状态、总结文章、管理日程、起草邮件。

### 自动化 DevOps 工程师
构建一个监控 VPS 的智能体：检查日志错误、定时运行备份、在需要关注时通过 Telegram 提醒你。连接 Shell 工具实现完全的服务器控制。

### 内容生成流水线
创建两个智能体：Writer 根据摘要起草博客文章，Editor 优化结构和语气。定时运行内容生成，智能体之间自动交接。

### 客户支持平台
将支持智能体同时接入 Discord、Slack 和 Telegram。智能体记住每个用户的历史记录，复杂问题通过任务委派升级给专业智能体。

---

## 常见问题排查

| 问题 | 解决方案 |
|------|----------|
| 容器无法启动 | 运行 `docker compose logs` 查看错误 |
| 无法访问 Web UI | 确认防火墙已开放 3456/3457 端口 |
| Ollama 连接失败 | 确认 Ollama 运行中且 SwarmClaw 容器可访问（`http://ollama:11434`）|
| 智能体拒绝任务 | 检查智能体是否已启用所需工具 |
| 记忆未持久保存 | 确认 `./data/` 目录权限正确 |
| MCP 服务器未找到 | 确认 MCP 服务器 URL 从 SwarmClaw 容器可达 |

---

## 总结

SwarmClaw 将**企业级多智能体编排能力**带到你的个人 VPS 上。不到十分钟，你就可以拥有一个功能完整的 AI 智能体运行时：

- 🐳 **单容器 Docker Compose 部署**
- 🏠 **本地 Ollama 模型**，完全保护隐私
- 🔗 **23+ LLM 提供商**，每个智能体可混搭不同模型
- 🧠 **持久智能体记忆**，跨会话保持上下文
- 🔌 **MCP 工具生态**，无限扩展能力
- 📊 **Web 仪表盘**，管理整个智能体舰队

无论你是构建个人助手、开发团队还是客户支持平台，SwarmClaw 都能让你在自己的基础设施上掌控全局。

**今天就开始搭建你的智能体群集——只需要一台 VPS 和 10 分钟。**

---

*相关文章：[Hermes Agent 部署指南](/zh/post/hermes-agent-vps-deployment/) | [在 VPS 上部署开源 AI 工具](/zh/post/deploying-open-source-ai-tools/) | [n8n AI 工作流部署教程](/zh/post/n8n-deployment-guide/)*
