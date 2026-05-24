---
title: "搭建统一 AI API 网关：用 LiteLLM 在 VPS 上聚合多模型接口"
description: "OpenAI、Claude、DeepSeek、本地 Ollama……每次切换模型都要改代码？部署 LiteLLM Proxy 统一接口层，一套 OpenAI 兼容 API 背后路由到任意模型提供商，还能做负载均衡、限流、用量审计。"
date: 2026-05-24T21:30:00+08:00
slug: "litellm-proxy-deployment-vps"
tags: ["LiteLLM", "AI Gateway", "API Proxy", "Docker", "VPS部署", "OpenAI兼容", "模型路由"]
categories: ["AI部署"]
image: /images/posts/litellm-proxy-deployment-vps/featured.png
draft: false
---

## 为什么需要 AI API 网关？

现在的 AI 生态有多碎片？开发用 Claude 写代码、生产用 GPT-4o 做推理、本地跑 Ollama 搞 RAG、测试阶段可能同时比较三个模型的输出。

结果就是：每个工具接不同 API 格式、不同认证方式、不同计费口径。改一次模型提供商，代码里所有调用点全要改。

**LiteLLM 解决了这个问题。** 它在你的 VPS 上开一个代理服务，暴露标准的 OpenAI 兼容 `/v1/chat/completions` 接口，背后路由到任意模型提供商——OpenAI、Anthropic、DeepSeek、Google Gemini、Groq、Together AI，甚至你本地的 Ollama。

一套代码，任意模型，零改造成本。

### LiteLLM 的几大核心能力

| 功能 | 说明 |
|------|------|
| **统一接口** | 所有模型走 OpenAI 格式，Cline/OpenRouter 等工具直接可用 |
| **多模型路由** | 一个请求指定模型名，自动路由到对应 Provider |
| **负载均衡** | 同一模型配多个 API Key，自动轮转、降级 |
| **限流与预算** | 按用户/模型/时间窗口设速率限制和费用上限 |
| **用量审计** | 记录每次调用的模型、token、耗时、费用 |
| **Fallback** | 主模型不可用时自动降级到备用模型 |

## 部署方式

### 方式一：Docker Compose 一键部署（推荐）

这是最快的方式，单文件搞定。

创建项目目录：

```bash
mkdir -p ~/litellm-proxy && cd ~/litellm-proxy
```

创建 `docker-compose.yml`：

```yaml
version: "3.8"

services:
  litellm-proxy:
    image: ghcr.io/berriai/litellm:main-latest
    container_name: litellm-proxy
    ports:
      - "4000:4000"
    volumes:
      - ./config.yaml:/app/config.yaml
      - ./litellm.db:/app/litellm.db
    environment:
      - DATABASE_URL=sqlite:///app/litellm.db
      - OPENAI_API_KEY=${OPENAI_API_KEY:-}
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY:-}
      - DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY:-}
      - GEMINI_API_KEY=${GEMINI_API_KEY:-}
    restart: unless-stopped
    command: ["--config", "/app/config.yaml", "--port", "4000", "--num_workers", "4"]
```

创建 `config.yaml` 配置模型路由规则：

```yaml
model_list:
  - model_name: gpt-4o
    litellm_params:
      model: openai/gpt-4o
      api_key: os.environ/OPENAI_API_KEY

  - model_name: claude-sonnet
    litellm_params:
      model: anthropic/claude-3-5-sonnet-20241022
      api_key: os.environ/ANTHROPIC_API_KEY

  - model_name: deepseek-chat
    litellm_params:
      model: deepseek/deepseek-chat
      api_key: os.environ/DEEPSEEK_API_KEY

  - model_name: gemini-pro
    litellm_params:
      model: gemini/gemini-2.0-flash
      api_key: os.environ/GEMINI_API_KEY

  - model_name: local-llama
    litellm_params:
      model: ollama/llama3.2
      api_base: http://host.docker.internal:11434

  - model_name: gpt-4o-mini
    litellm_params:
      model: openai/gpt-4o-mini
      api_key: os.environ/OPENAI_API_KEY
    # 负载均衡：配多个 Key 自动轮转
    - model_name: deepseek-chat
      litellm_params:
        model: deepseek/deepseek-chat
        api_key: "sk-deepseek-key-1"
      - model_name: deepseek-chat
        litellm_params:
          model: deepseek/deepseek-chat
          api_key: "sk-deepseek-key-2"

litellm_settings:
  drop_params: true
  set_verbose: false
  cache: true
  cache_params:
    type: redis
    host: localhost
    port: 6379
    ttl: 600

general_settings:
  master_key: "sk-your-master-key-here"  # 代理自身的安全密钥
  database_url: "sqlite:///app/litellm.db"
```

创建 `.env` 文件存放密钥：

```bash
cat > .env << 'EOF'
OPENAI_API_KEY=sk-proj-xxxx
ANTHROPIC_API_KEY=sk-ant-xxxx
DEEPSEEK_API_KEY=sk-deepseek-xxxx
GEMINI_API_KEY=AIzaSyxxxx
EOF
```

启动服务：

```bash
docker compose up -d
```

### 方式二：直接安装（轻量）

如果你不想用 Docker，直接用 pip 安装：

```bash
pip install 'litellm[proxy]'
litellm --config ./config.yaml --port 4000
```

建议用 `systemd` 或 `screen` 保持在后台。

## 使用方式

### 1. 基础调用

部署完成后，任何 OpenAI 兼容客户端只需改 base_url 和 api_key：

```bash
curl http://你的VPS_IP:4000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-your-master-key-here" \
  -d '{
    "model": "deepseek-chat",
    "messages": [{"role": "user", "content": "你好，请用中文回复"}]
  }'
```

### 2. 配合 Cline / Cursor / Continue 使用

以 VS Code 的 Continue 插件为例，配置 `config.json`：

```json
{
  "models": [{
    "title": "LiteLLM Proxy",
    "provider": "openai",
    "model": "claude-sonnet",
    "apiBase": "http://你的VPS_IP:4000",
    "apiKey": "sk-your-master-key-here"
  }]
}
```

切换到其他模型只需改 `model` 字段，不需要改任何基础设施配置。

### 3. Python SDK 调用

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://你的VPS_IP:4000/v1",
    api_key="sk-your-master-key-here"
)

response = client.chat.completions.create(
    model="gemini-pro",  # 背后走的是 Google Gemini
    messages=[{"role": "user", "content": "解释一下量子纠缠"}]
)
```

## 安全加固

暴露在公网的 API 网关必须做好防护。

### 启用 Master Key

`general_settings.master_key` 是 LiteLLM 的全局安全密钥，所有请求必须带这个 token。建议用强随机字符串：

```bash
openssl rand -hex 32
# 输出类似: 7a9f2b3c8d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a
```

### Nginx 反代 + HTTPS

用 Caddy 或 Nginx 加一层 TLS，防止 API Key 明文传输：

```nginx
# /etc/nginx/sites-available/litellm
server {
    listen 443 ssl;
    server_name ai-gateway.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/ai-gateway.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/ai-gateway.yourdomain.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:4000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### IP 白名单

仅允许你的办公 IP 或通过 Tailscale/WireGuard 访问：

```yaml
general_settings:
  allowed_ip_ranges:
    - "10.0.0.0/8"        # WireGuard 内网
    - "你的办公公网IP/32"
```

## 限流与费用控制

这是 LiteLLM 的杀手级功能。可以给不同团队设不同预算：

```yaml
router_settings:
  routing_strategy: "usage-based"  # 也可用 "latency-based"
  enable_loadbalancing: true

general_settings:
  alerting: true
  alerting_threshold: 80  # 费用达到预算 80% 时告警

user_settings:
  - user_id: "team-a"
    max_budget: 50.0      # 每月最多花 $50
    rpm_limit: 100         # 每分钟最多 100 请求
    tpm_limit: 100000      # 每分钟最多 100K token
```

## 用量监控 API

LiteLLM 自带管理界面和监控端点：

```bash
# 查看所有模型调用统计
curl http://你的VPS_IP:4000/spend/models \
  -H "Authorization: Bearer sk-your-master-key-here"

# 查看总费用
curl http://你的VPS_IP:4000/spend/total \
  -H "Authorization: Bearer sk-your-master-key-here"
```

访问 `http://你的VPS_IP:4000/ui` 可进入图形化管理面板。

## 实用技巧

### 模型别名

给模型起好记的名字，前端不用关心底层提供商：

```yaml
model_list:
  - model_name: cheap-fast      # 前端用这个名字
    litellm_params:
      model: openai/gpt-4o-mini
  - model_name: best-coding     # 前端用这个名字
    litellm_params:
      model: anthropic/claude-3-5-sonnet-20241022
  - model_name: local           # 前端用这个名字
    litellm_params:
      model: ollama/qwen2.5:14b
```

### Failover 策略

主模型不可用时自动降级：

```yaml
router_settings:
  fallbacks:
    - gpt-4: ["claude-sonnet", "deepseek-chat"]   # GPT-4 挂了走 Claude → DeepSeek
    - claude-sonnet: ["deepseek-chat", "gpt-4o-mini"]
  num_retries: 3
  request_timeout: 30
```

### Ollama 本地模型集成

如果 VPS 上同时跑着 Ollama，LiteLLM 可以直接代理：

```yaml
model_list:
  - model_name: local-qwen
    litellm_params:
      model: ollama/qwen2.5:14b
      api_base: http://localhost:11434
```

这样外部工具通过 LiteLLM 调用 `local-qwen` 时，实际走的是本地模型，零成本推理。

## 成本估算

以一台 2 核 4GB 的 VPS（Hetzner CX22，€3.99/月）为例：

| 组件 | 成本 |
|------|------|
| VPS | €3.99/月 |
| LiteLLM 本身 | 免费开源 |
| API 调用费 | 按实际用量计（同直接调用） |
| Redis 缓存（可选） | Docker 内运行，零额外成本 |

比起直接调用各个 Provider，LiteLLM 没有任何额外开销，反而因为缓存机制可能节省重复调用。

## 总结

LiteLLM Proxy 解决了一个真实而普遍的问题：**AI 模型碎片化**。它把多模型管理从"到处改代码"变成"改一行配置文件"，同时带来限流、审计、负载均衡、故障转移等企业级能力。

如果你是：
- **独立开发者**：一个 VPS + LiteLLM = 统一接入所有模型
- **小团队**：做多模型 A/B 测试和用量管理
- **企业用户**：给不同部门设不同预算和限流策略

都可以零成本起步。开源、轻量、Docker 化部署，5 分钟就能从零跑到生产。

### 相关资源

- [LiteLLM 官方文档](https://docs.litellm.ai)
- [LiteLLM GitHub](https://github.com/BerriAI/litellm)
- [Docker 部署指南](https://docs.litellm.ai/docs/proxy/proxy_cli)
