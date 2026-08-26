---
title: "Deploy Local LLMs on VPS: Complete Ollama Guide for Llama / Codestral / Qwen"
date: 2026-08-26
description: "Skip expensive API subscriptions. Deploy Ollama on your VPS and run Llama 3.2, Codestral, Qwen and other open-source LLMs locally. Covers installation, GPU acceleration, API compatibility, multi-model management, and frontend deployment."
tags: ["VPS", "Ollama", "LLM", "AI", "Self-hosted", "Llama", "Qwen", "Codestral"]
categories: ["AI Operations"]
image: "/images/posts/vps-ollama-local-llm-deployment/featured-en.png"
draft: false
---

## Introduction

Large language models are transforming how we work and interact with software. But every API call comes at a cost — ChatGPT, Claude, and GPT-4o may seem cheap per request, but high-volume usage adds up fast.

What if you could **run AI models on your own server**? You can.

**Ollama** is the simplest and most popular framework for running local LLMs. It supports dozens of open-source models including Llama 3.2, Codestral, Qwen, and DeepSeek. A single command gets you running, and it provides an OpenAI-compatible API — meaning you can connect existing AI clients directly to your local model.

This guide walks you through deploying Ollama on a VPS from scratch, including CPU and GPU acceleration, model management, API usage, and frontend interfaces.

---

## Why Run Ollama on a VPS?

| Approach | Cost | Speed | Privacy | Flexibility |
|----------|------|-------|---------|-------------|
| Cloud API (ChatGPT/Claude) | High (per-token) | Fast | Low (data leaves your server) | Medium |
| Local PC with Ollama | Free | Depends on hardware | High | Low (limited by local hardware) |
| **VPS with Ollama** | **Low (fixed monthly)** | **Medium-fast** | **High** | **High (24/7 online)** |

Advantages of the VPS approach:
- **Fixed cost**: A $20-50/month VPS runs 24/7 — cheaper than pay-per-use for heavy users
- **Always online**: Models stay in memory, ready to call anytime
- **Data privacy**: All requests stay on your own server
- **Team sharing**: Multiple users can access without individual subscriptions
- **API compatible**: OpenAI-compatible interface, drop-in replacement for third-party services

---

## Prerequisites

### Hardware Requirements

Different models have different resource needs:

| Model | Min RAM | Recommended RAM | GPU Needed |
|-------|---------|-----------------|------------|
| Llama 3.2 1B/3B | 2 GB | 4 GB | None |
| Llama 3.2 11B/8B | 8 GB | 12 GB | Recommended |
| Llama 3.1 8B | 8 GB | 16 GB | Recommended |
| Qwen 2.5 14B | 16 GB | 24 GB | Recommended |
| DeepSeek R1 7B | 8 GB | 12 GB | Recommended |
| DeepSeek R1 32B | 32 GB | 48 GB | Required |

**Recommended VPS specs**:
- **Starter**: 2 vCPU / 8 GB RAM / 50 GB SSD (for 7B-8B models)
- **Advanced**: 4 vCPU / 16-24 GB RAM (for 14B-32B models)
- **GPU**: NVIDIA T4 / L4 instances (recommended for large model inference)

### System Requirements

- Linux (Ubuntu 20.04+ / Debian 11+ / AlmaLinux 9)
- Docker (recommended for isolation)
- Or Python 3.8+ (native installation)

---

## Method 1: Docker Deployment (Recommended)

Docker makes installation trivial, simplifies version management, and eases backup and migration.

### 1. Install Docker

```bash
# Ubuntu / Debian
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker

# Verify
docker --version
```

### 2. Start Ollama Container

```bash
docker run -d \
  --name ollama \
  -v ollama-data:/root/.ollama \
  -p 11434:11434 \
  --restart unless-stopped \
  ollama/ollama:latest
```

**Parameter explanation**:
- `-v ollama-data:/root/.ollama`: Persist model data — models survive container restarts
- `-p 11434:11434`: Expose the Ollama API port
- `--restart unless-stopped`: Auto-restart on VPS reboot

### 3. Verify Installation

```bash
# Check container status
docker ps | grep ollama

# Test API responsiveness
curl http://localhost:11434/api/version
```

---

## Method 2: Native Installation

If you prefer not to use Docker:

```bash
# One-line installer
curl -fsSL https://ollama.com/install.sh | sh

# Start the service
systemctl start ollama
systemctl enable ollama  # Auto-start on boot

# Verify
ollama --version
```

---

## Pull and Run Models

Ollama's model management is beautifully simple:

### Popular Models

```bash
# Meta Llama 3.2 (most popular open-source model)
ollama pull llama3.2

# Mistral (excellent European open-source model)
ollama pull mistral

# Qwen 2.5 (Alibaba, strong Chinese language support)
ollama pull qwen2.5

# DeepSeek R1 (Chinese reasoning model, free and open)
ollama pull deepseek-r1:7b

# Codestral (Mistral's code-specialized model)
ollama pull codestral

# Gemma 2 (Google open-source model)
ollama pull gemma2
```

### Model Size Reference

Ollama automatically downloads quantized versions:

| Model | Default Quant | Parameters | RAM Usage |
|-------|--------------|------------|-----------|
| llama3.2 | Q4_K_M | 3B | ~2 GB |
| llama3.1 | Q4_K_M | 8B | ~5 GB |
| qwen2.5 | Q4_K_M | 7B | ~4.5 GB |
| deepseek-r1 | Q4_K_M | 7B | ~4.5 GB |
| codestral | Q4_K_M | 22B | ~14 GB |

### Switch Model Sizes

```bash
# Larger parameter versions (need more RAM)
ollama pull llama3.2:latest    # 3B
ollama pull llama3.1:8b        # 8B
ollama pull qwen2.5:14b        # 14B

# Smaller quantized versions (save RAM)
ollama pull llama3.2:1b        # 1B (ultra-light)
ollama pull llama3.2:0.5b      # 0.5B (mobile-grade)
```

---

## Test Your Models

### CLI Interaction

```bash
# Interactive chat
ollama run llama3.2

# One-shot query
ollama run qwen2.5 "Write a quicksort algorithm in Python"
```

### API Calls

Ollama provides a full OpenAI-compatible API:

```bash
# List available models
curl http://localhost:11434/api/tags

# Streaming chat
curl http://localhost:11434/api/chat -d '{
  "model": "llama3.2",
  "messages": [{"role": "user", "content": "Hello, introduce yourself"}],
  "stream": true
}'

# Non-streaming
curl http://localhost:11434/api/generate -d '{
  "model": "qwen2.5",
  "prompt": "How to implement multithreading in Python?",
  "stream": false
}'
```

### Python Client

```python
from openai import OpenAI

# Point to local Ollama
client = OpenAI(
    base_url="http://your-vps-ip:11434/v1/",
    api_key="not-needed"  # Ollama doesn't require an API key
)

response = client.chat.completions.create(
    model="llama3.2",
    messages=[
        {"role": "system", "content": "You are a professional programmer assistant"},
        {"role": "user", "content": "Write a REST API with FastAPI"}
    ],
    stream=True
)

for chunk in response:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="")
```

---

## GPU Acceleration

Pure CPU inference is slow for 7B+ models (typically 3-10 tokens/s). If your VPS supports GPUs, you'll see a dramatic improvement.

### NVIDIA GPU Support

```bash
# Check GPU availability
nvidia-smi

# GPU-enabled Ollama (NVIDIA CUDA)
docker run -d \
  --name ollama \
  --gpus all \
  -v ollama-data:/root/.ollama \
  -p 11434:11434 \
  --restart unless-stopped \
  ollama/ollama:latest-gpu
```

### GPU VPS Providers

| Provider | GPU Model | Price (hourly) | Best For |
|----------|-----------|----------------|----------|
| Lambda Cloud | A100 80GB | $2-3/hr | All models |
| Vast.ai | RTX 4090 / A100 | $0.2-0.5/hr | Pay-as-you-go |
| RunPod | RTX 4090 / A6000 | $0.3-0.6/hr | Pay-as-you-go |
| Alibaba Cloud PAI | A10 / A100 | ¥1-3/hr | On-demand |
| Tencent Cloud Lighthouse | T4 | ¥2-4/hr | 7B-14B models |

### Verify GPU Acceleration

```bash
# Check if Ollama is using GPU
ollama ps

# Expected output:
# NAME            ID              SIZE      PROCESSOR           UNTIL
# llama3.2:latest  abc123...      2.0 GB    CUDA:0 (NVIDIA ...)  Now
```

---

## Multi-Model Management

### List All Models

```bash
ollama list
# or
curl http://localhost:11434/api/tags
```

### Remove Unused Models

```bash
ollama rm llama3.1        # Remove specific model
ollama rm llama3.2:3b     # Remove specific version
```

### Customize Model Parameters

Create a Modelfile to customize model behavior:

```modelfile
FROM llama3.2
PARAMETER temperature 0.7
PARAMETER num_ctx 4096
PARAMETER num_predict 2048
SYSTEM "You are a professional programmer. Only answer technical questions."
```

```bash
# Build custom model
ollama create my-llama -f ./Modelfile

# Run custom model
ollama run my-llama "Hello"
```

---

## Deploy a Frontend Interface

### Option 1: Open WebUI (Recommended)

Open WebUI is the most popular open-source Ollama frontend, offering a ChatGPT-like experience.

```bash
docker run -d \
  --name open-webui \
  -v open-webui:/app/backend/data \
  -p 8080:8080 \
  --restart unless-stopped \
  ghcr.io/open-webui/open-webui:main
```

Visit `http://your-vps-ip:8080`, and set the API endpoint to `http://localhost:11434` in settings.

### Option 2: Text Generation WebUI

```bash
docker run -d \
  --name textgen \
  -p 7860:7860 \
  -v textgen-data:/data \
  --restart unless-stopped \
  ghcr.io/oobabooga/text-generation-webui:latest
```

### Option 3: Dify Integration

If you already use Dify, you can configure Ollama as the model provider:

1. Go to Dify → Workspace Settings → Model Providers
2. Select "Ollama"
3. Enter `http://your-vps-ip:11434`
4. Choose your model

---

## Production Configuration

### Nginx Reverse Proxy with HTTPS

```nginx
server {
    listen 443 ssl;
    server_name ollama.yourdomain.com;

    ssl_certificate     /etc/nginx/ssl/cert.pem;
    ssl_certificate_key /etc/nginx/ssl/key.pem;

    location / {
        proxy_pass http://localhost:11434;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket support (required for Open WebUI)
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }
}
```

### Firewall Configuration

```bash
# Only open necessary ports
sudo ufw allow 11434/tcp   # Ollama API
sudo ufw allow 8080/tcp    # Open WebUI (optional)
sudo ufw allow 443/tcp     # HTTPS
sudo ufw enable
```

### Resource Monitoring

```bash
# Real-time monitoring
htop

# Check Ollama processes
ollama ps

# Docker resource usage
docker stats ollama

# Memory and GPU
free -h
nvidia-smi  # GPU users
```

### Automated Model Backup

```bash
# Backup all models
tar czf ollama-models-backup-$(date +%Y%m%d).tar.gz \
  -C /root/.ollama .

# Or use rsync for incremental backup
rsync -avz /root/.ollama/ backup-server:/ollama-backup/ollama/
```

---

## Troubleshooting

### 1. Slow Model Loading

```bash
# Check disk I/O
iotop

# Ensure models are stored on SSD/NVMe
# Docker volumes default to /var/lib/docker — verify it's on SSD
df -h /var/lib/docker
```

### 2. Out of Memory (OOM)

```bash
# Check available memory
free -h

# Use smaller models
ollama rm llama3.1:8b
ollama pull llama3.2:3b    # Smaller model

# Or limit container resources
docker run -d --memory="8g" --cpus="2" ...
```

### 3. API Connection Timeout

```bash
# Check Ollama service status
systemctl status ollama
# or
docker logs ollama

# Check port listening
ss -tlnp | grep 11434

# Firewall
sudo ufw status
```

### 4. GPU Not Detected

```bash
# Verify NVIDIA drivers
nvidia-smi

# Verify Docker GPU support
docker run --rm --gpus all nvidia/cuda:12.0.0-base-ubuntu22.04 nvidia-smi

# Restart Ollama container
docker restart ollama
```

---

## Cost Estimation

| VPS Config | Monthly Cost | Runnable Models | Daily Token Usage | vs Cloud API |
|------------|-------------|-----------------|-------------------|-------------|
| 2C8G Basic | $10-15 | 3B-7B models | ~1M tokens | Save ~$50/mo |
| 4C16G Advanced | $30-50 | 7B-14B models | ~5M tokens | Save ~$200/mo |
| GPU VPS (T4) | $100-200 | 14B-32B models | ~10M tokens | Save ~$500/mo |

For comparison, at ~1M tokens/day with ChatGPT 4o API:
- ChatGPT API: ~$50/month (at $0.005/1K tokens)
- VPS fixed cost: $10-50/month
- **Annual savings: $500-3,000+**

---

## Summary

Running Ollama on a VPS is one of the best balances of cost, performance, and privacy:

1. **Easy installation**: One Docker command to get started
2. **Rich model library**: Supports Llama, Qwen, DeepSeek, and dozens more
3. **API compatible**: OpenAI format — drop-in replacement for third-party services
4. **Cost predictable**: Fixed monthly fee, far cheaper than pay-per-token at scale
5. **Data secure**: All requests stay on your own server

**Next steps**:
1. Provision a VPS with 8GB+ RAM
2. Run `curl -fsSL https://ollama.com/install.sh | sh`
3. `ollama pull llama3.2` to download your first model
4. Configure reverse proxy and HTTPS
5. Deploy Open WebUI for a complete chat experience

Get your own AI assistant running on your VPS today!
