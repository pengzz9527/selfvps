---
title: "Deploy Open WebUI + Ollama on VPS: Build Your Private ChatGPT"
description: "Complete tutorial: One-click deployment of Open WebUI + Ollama on your VPS with Docker. Run offline, switch between multiple LLMs, enable RAG knowledge bases, and say goodbye to ChatGPT subscriptions forever."
date: 2026-05-21T21:30:00+08:00
slug: "open-webui-ollama-vps-deployment"
tags: ["Open WebUI", "Ollama", "AI", "Docker", "VPS deployment", "LLM", "ChatGPT alternative", "self-hosting", "RAG"]
categories: ["AI Deployment"]
aliases: [/en/post/open-webui-ollama-vps-deployment/]
draft: false
image: /images/posts/open-webui-ollama-vps-deployment/featured.png
---

## Why Open WebUI + Ollama?

If you want to run your own AI assistant without paying for ChatGPT Plus every month, **Open WebUI + Ollama** is the most mature self-hosted solution available today. This powerful combo gives you on your VPS:

- **100% Private** — Your data never leaves your server. No privacy concerns
- **Zero Subscription Costs** — Just pay for your VPS, no API fees
- **Works Offline** — No internet connection required to use
- **Multi-Model Support** — Run Llama, Qwen, DeepSeek, Mistral, Gemma and more simultaneously
- **ChatGPT-Class Experience** — OpenAI-compatible web interface with full feature parity
- **RAG Knowledge Base** — Upload documents and let AI answer based on your data
- **Multi-User Support** — Share the same server with your team

## Prerequisites

Before you begin, make sure you have:

- **A VPS** (recommended: 4 CPU cores, 8 GB RAM, 50 GB SSD)
- **Docker and Docker Compose** (installed)
- **A domain name** (optional, for HTTPS configuration)
- **Basic Linux command-line knowledge**

### Recommended VPS Specs

| Model Size | Recommended RAM | Storage Needed | Use Case |
|-----------|-----------------|----------------|----------|
| 1B-3B parameters | 4 GB | 10 GB | Light chat, translation, summarization |
| 7B-8B parameters | 8 GB | 20 GB | General QA, code assistance |
| 14B-20B parameters | 16 GB | 40 GB | Complex reasoning, professional writing |
| 70B+ parameters | 32 GB+ | 80 GB+ | Advanced reasoning, multilingual |

> **Tip**: For most use cases, an 8 GB RAM VPS running a 7B model (like Qwen2.5-7B or Llama-3.1-8B) delivers excellent results.

## Step 1: Install Docker and Docker Compose

If not already installed:

```bash
# Update system
apt update && apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | bash

# Verify installation
docker --version
docker compose version
```

## Step 2: Create Docker Compose Configuration

Create a project directory and configuration file:

```bash
mkdir -p ~/open-webui && cd ~/open-webui
nano docker-compose.yml
```

Paste the following configuration:

```yaml
version: "3.8"

services:
  ollama:
    image: ollama/ollama:latest
    container_name: ollama
    volumes:
      - ./ollama_data:/root/.ollama
    ports:
      - "11434:11434"
    restart: unless-stopped
    networks:
      - ai-net
    environment:
      - OLLAMA_KEEP_ALIVE=24h
      - OLLAMA_NUM_PARALLEL=1
      - OLLAMA_MAX_LOADED_MODELS=1

  open-webui:
    image: ghcr.io/open-webui/open-webui:main
    container_name: open-webui
    depends_on:
      - ollama
    volumes:
      - ./webui_data:/app/backend/data
    ports:
      - "3000:8080"
    restart: unless-stopped
    networks:
      - ai-net
    environment:
      - OLLAMA_BASE_URL=http://ollama:11434
      - WEBUI_SECRET_KEY=replace-with-random-secret
      - WEBUI_NAME=My AI Chat
    extra_hosts:
      - "host.docker.internal:host-gateway"

networks:
  ai-net:
    driver: bridge
```

> **Security note**: Generate a random secret with `openssl rand -base64 32` and replace `WEBUI_SECRET_KEY`.

## Step 3: Start the Services

```bash
docker compose up -d
```

Check service status:

```bash
docker compose ps
docker compose logs -f
```

You'll know it's working when you see:

```
open-webui  | INFO:     Application startup complete.
ollama      | 2026/05/21 10:30:00 server.go:89: Listening on 0.0.0.0:11434
```

## Step 4: Download AI Models

Now download and test your first model:

```bash
# Pull a model (Qwen2.5-7B is excellent for multilingual use)
docker exec ollama ollama pull qwen2.5:7b

# Other recommended models
# docker exec ollama ollama pull llama3.1:8b     # Best for English
# docker exec ollama ollama pull deepseek-r1:8b   # Strong reasoning
# docker exec ollama ollama pull gemma2:9b        # Google's offering
# docker exec ollama ollama pull mistral:7b       # Efficient and fast

# Test the model
docker exec ollama ollama run qwen2.5:7b "Hello, introduce yourself"
```

Download time depends on your VPS network speed. A 7B model requires ~4-5 GB of storage and may take 5-20 minutes to download.

### List Downloaded Models

```bash
docker exec ollama ollama list
```

## Step 5: Access Open WebUI

### Direct IP Access

If your VPS firewall allows port `3000`:

```
http://YOUR_VPS_IP:3000
```

### Nginx Reverse Proxy + HTTPS (Recommended)

Create an Nginx configuration:

```bash
sudo nano /etc/nginx/sites-available/open-webui
```

```nginx
server {
    listen 80;
    server_name chat.your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400s;
        proxy_send_timeout 86400s;
    }
}
```

Enable the site and get SSL:

```bash
sudo ln -s /etc/nginx/sites-available/open-webui /etc/nginx/sites-enabled/
sudo certbot --nginx -d chat.your-domain.com
sudo nginx -t && sudo systemctl reload nginx
```

## Advanced Configuration

### 1. Set Up RAG Knowledge Base

Open WebUI has built-in RAG (Retrieval-Augmented Generation) support:

1. Click the **"+"** button next to the chat input
2. Upload PDF, TXT, Markdown, or other documents
3. The AI automatically indexes document content
4. Future conversations will include context from your documents

### 2. Run Multiple Models Simultaneously

Modify environment variables in `docker-compose.yml`:

```yaml
environment:
  - OLLAMA_KEEP_ALIVE=-1          # Keep models in memory
  - OLLAMA_NUM_PARALLEL=4        # Allow parallel requests
  - OLLAMA_MAX_LOADED_MODELS=3   # Max 3 models loaded
```

### 3. GPU Acceleration

If your VPS has an NVIDIA GPU, add:

```yaml
services:
  ollama:
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
```

### 4. Integrate Cloud Models

Open WebUI also supports cloud API calls. Configure in the web interface:

- **OpenAI API** — Plug in your API key for GPT-4 access
- **Google Gemini** — Add your Gemini API key
- **Anthropic Claude** — Configure Claude access
- **Custom Endpoints** — Any OpenAI-compatible API

### 5. Enable Web Search

In Open WebUI's "Admin Panel → Settings → Web Search", enable search engines so the AI can fetch real-time information.

## Performance Optimization

### Memory Tuning

```bash
# Set up swap space (safety net for low memory)
fallocate -l 8G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab

# Tune swappiness (lower = use RAM more aggressively)
sysctl vm.swappiness=10
echo 'vm.swappiness=10' >> /etc/sysctl.conf
```

### Model Quantization Guide

Different quantization levels impact memory and quality:

| Quantization | Precision | Memory (7B) | Quality |
|-------------|-----------|-------------|---------|
| Q4_K_M | 4-bit | ~5 GB | Recommended balance |
| Q5_K_M | 5-bit | ~6 GB | Higher precision |
| Q8_0 | 8-bit | ~8 GB | Nearly lossless |
| fp16 | 16-bit | ~16 GB | Original precision |

For an 8 GB VPS, use `qwen2.5:7b` (default Q4_K_M) or `qwen2.5:7b-q5_k_m`.

## Frequently Asked Questions

### Q: Why is model response slow?
**A:** A 7B model on CPU generates about 5-15 tokens/second, which is normal. To speed things up: ① Use a smaller model (1.5B/3B); ② Upgrade to a higher-performance VPS CPU; ③ Add GPU acceleration.

### Q: Will I lose chat history after restarting containers?
**A:** No. The `webui_data` and `ollama_data` volumes persist on the host machine. Container restarts won't delete your data.

### Q: How do I upgrade Open WebUI?
**A:** Simply pull the latest image and restart:
```bash
docker compose pull
docker compose up -d --force-recreate
```

### Q: Ollama keeps crashing due to memory limits?
**A:** Limit CPU threads used by the model:
```bash
docker exec ollama ollama run qwen2.5:7b --num-thread 4
```
Or set `OLLAMA_NUM_THREADS=4` in the Ollama environment.

## Conclusion

With the Open WebUI + Ollama combination, you can build a fully functional private AI chat platform on any VPS. It's completely free, privacy-protecting, and supports advanced features like multi-model switching, RAG knowledge bases, and web search.

This setup is ideal for:

- **Developers** — Code assistance, technical Q&A, local document search
- **Small teams** — Shared AI assistant, reduced API costs
- **Privacy-conscious users** — Medical, legal, financial data stays on your server
- **Offline environments** — AI capabilities in air-gapped networks

Get started today! Pick a capable VPS, follow this guide, and you'll have your own private AI assistant up and running in minutes.
