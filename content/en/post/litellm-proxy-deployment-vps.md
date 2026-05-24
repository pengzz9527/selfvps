---
title: "Build a Unified AI API Gateway: Deploy LiteLLM Proxy on Your VPS"
description: "Switching between OpenAI, Claude, DeepSeek, and local Ollama means rewriting code every time. Deploy LiteLLM Proxy — a single OpenAI-compatible endpoint that routes to any model provider with load balancing, rate limiting, and usage auditing built in."
date: 2026-05-24T21:30:00+08:00
slug: "litellm-proxy-deployment-vps"
tags: ["LiteLLM", "AI Gateway", "API Proxy", "Docker", "VPS Deployment", "OpenAI-compatible", "Model Routing"]
categories: ["AI Deployment"]
image: /images/posts/litellm-proxy-deployment-vps/featured.png
draft: false
---

## Why Do You Need an AI API Gateway?

The AI ecosystem is fragmented. You code with Claude, deploy with GPT-4o, run a local Ollama for RAG, and benchmark three models side-by-side during testing.

The result? Every tool speaks a different API format, uses different auth, and tracks costs differently. Changing providers means updating every integration point in your codebase.

**LiteLLM fixes this.** It runs a proxy service on your VPS that exposes a standard OpenAI-compatible `/v1/chat/completions` endpoint, routing behind the scenes to any model provider — OpenAI, Anthropic, DeepSeek, Google Gemini, Groq, Together AI, or your local Ollama instance.

One codebase, any model, zero refactoring.

### Core Capabilities

| Feature | Description |
|---------|-------------|
| **Unified Interface** | All models speak OpenAI format — tools like Cline, Continue, and OpenRouter work instantly |
| **Multi-Model Routing** | Specify a model name, LiteLLM routes to the right provider automatically |
| **Load Balancing** | Multiple API keys per model with automatic rotation and fallback |
| **Rate Limiting & Budgets** | Per-user, per-model rate limits and spending caps |
| **Usage Auditing** | Log every request: model, tokens, latency, cost |
| **Failover** | Auto-degrade to backup models when the primary is unavailable |

## Deployment Options

### Option 1: Docker Compose (Recommended)

The fastest way to get started — one file to rule them all.

Create the project directory:

```bash
mkdir -p ~/litellm-proxy && cd ~/litellm-proxy
```

Create `docker-compose.yml`:

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

Create `config.yaml` with your model routing rules:

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
    # Load balancing: multiple keys auto-rotate
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
  master_key: "sk-your-master-key-here"
  database_url: "sqlite:///app/litellm.db"
```

Create `.env` for your API keys:

```bash
cat > .env << 'EOF'
OPENAI_API_KEY=sk-proj-xxxx
ANTHROPIC_API_KEY=sk-ant-xxxx
DEEPSEEK_API_KEY=sk-deepseek-xxxx
GEMINI_API_KEY=AIzaSyxxxx
EOF
```

Launch the service:

```bash
docker compose up -d
```

### Option 2: Direct Installation (Lightweight)

If you prefer not to use Docker:

```bash
pip install 'litellm[proxy]'
litellm --config ./config.yaml --port 4000
```

Use `systemd` or `screen` to keep it running in the background.

## How to Use It

### 1. Basic API Call

Once deployed, any OpenAI-compatible client just needs a different base URL:

```bash
curl http://YOUR_VPS_IP:4000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-your-master-key-here" \
  -d '{
    "model": "deepseek-chat",
    "messages": [{"role": "user", "content": "Hello, explain quantum entanglement"}]
  }'
```

### 2. Use with Cline / Cursor / Continue

For VS Code's Continue extension, configure `config.json`:

```json
{
  "models": [{
    "title": "LiteLLM Proxy",
    "provider": "openai",
    "model": "claude-sonnet",
    "apiBase": "http://YOUR_VPS_IP:4000",
    "apiKey": "sk-your-master-key-here"
  }]
}
```

Switching models is now just a field change — no infrastructure changes needed.

### 3. Python SDK

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://YOUR_VPS_IP:4000/v1",
    api_key="sk-your-master-key-here"
)

response = client.chat.completions.create(
    model="gemini-pro",  # Actually routes to Google Gemini
    messages=[{"role": "user", "content": "Explain quantum entanglement"}]
)
```

## Security Hardening

A public-facing API gateway needs proper protection.

### Enable Master Key

The `general_settings.master_key` is LiteLLM's global security token — all requests require it. Generate a strong one:

```bash
openssl rand -hex 32
# Output: 7a9f2b3c8d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a
```

### Nginx Reverse Proxy + HTTPS

Add TLS with Caddy or Nginx to prevent API keys from being transmitted in plaintext:

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

### IP Whitelist

Restrict access to your office IP or through Tailscale/WireGuard:

```yaml
general_settings:
  allowed_ip_ranges:
    - "10.0.0.0/8"        # WireGuard internal network
    - "YOUR_OFFICE_IP/32"
```

## Rate Limiting & Cost Control

This is LiteLLM's killer feature. Set different budgets for different teams:

```yaml
router_settings:
  routing_strategy: "usage-based"
  enable_loadbalancing: true

general_settings:
  alerting: true
  alerting_threshold: 80  # Alert at 80% of budget

user_settings:
  - user_id: "team-a"
    max_budget: 50.0      # Max $50/month
    rpm_limit: 100         # Max 100 requests/minute
    tpm_limit: 100000      # Max 100K tokens/minute
```

## Usage Monitoring API

LiteLLM includes a built-in admin UI and monitoring endpoints:

```bash
# Model spend stats
curl http://YOUR_VPS_IP:4000/spend/models \
  -H "Authorization: Bearer sk-your-master-key-here"

# Total spend
curl http://YOUR_VPS_IP:4000/spend/total \
  -H "Authorization: Bearer sk-your-master-key-here"
```

Visit `http://YOUR_VPS_IP:4000/ui` for the graphical admin panel.

## Pro Tips

### Model Aliases

Give models memorable names — your frontend never needs to know the actual provider:

```yaml
model_list:
  - model_name: cheap-fast      # Frontend uses this
    litellm_params:
      model: openai/gpt-4o-mini
  - model_name: best-coding     # Frontend uses this
    litellm_params:
      model: anthropic/claude-3-5-sonnet-20241022
  - model_name: local           # Frontend uses this
    litellm_params:
      model: ollama/qwen2.5:14b
```

### Failover Strategy

Auto-fallback when a model is down:

```yaml
router_settings:
  fallbacks:
    - gpt-4: ["claude-sonnet", "deepseek-chat"]
    - claude-sonnet: ["deepseek-chat", "gpt-4o-mini"]
  num_retries: 3
  request_timeout: 30
```

### Local Ollama Integration

If you're already running Ollama on the same VPS, LiteLLM can proxy it:

```yaml
model_list:
  - model_name: local-qwen
    litellm_params:
      model: ollama/qwen2.5:14b
      api_base: http://localhost:11434
```

External tools calling `local-qwen` through LiteLLM will hit your local models — zero inference cost.

## Cost Breakdown

Using a 2-core 4GB VPS (Hetzner CX22, €3.99/mo):

| Component | Cost |
|----------|------|
| VPS | €3.99/mo |
| LiteLLM | Free & open-source |
| API usage | Pay-as-you-go (same as direct calls) |
| Redis cache (optional) | Runs in Docker, zero extra cost |

Compared to calling each provider directly, LiteLLM adds zero overhead and may save costs through response caching.

## Summary

LiteLLM Proxy solves a real and growing problem: **AI model fragmentation**. It transforms multi-model management from "rewrite every integration" to "change one config line" — while adding enterprise-grade rate limiting, auditing, load balancing, and failover.

If you're:
- **An indie developer**: One VPS + LiteLLM = unified access to every major model
- **A small team**: Multi-model A/B testing with usage management
- **An enterprise**: Per-department budgets and rate limits

You can start at zero cost. Open-source, lightweight, Docker-ready — from zero to production in 5 minutes.

### Resources

- [LiteLLM Documentation](https://docs.litellm.ai)
- [LiteLLM GitHub](https://github.com/BerriAI/litellm)
- [Docker Deployment Guide](https://docs.litellm.ai/docs/proxy/proxy_cli)
