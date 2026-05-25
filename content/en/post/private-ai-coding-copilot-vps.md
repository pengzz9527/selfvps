---
title: "Build a Private AI Coding Copilot on VPS: Complete Continue.dev + Ollama Guide"
description: "GitHub Copilot raised prices, Cursor went closed-source — fight back with your own AI coding assistant on a VPS. Full guide covering Ollama setup, Continue.dev config, VS Code/JetBrains integration, all under $10/month."
date: 2026-05-25T21:30:00+08:00
slug: "private-ai-coding-copilot-vps"
tags: ["AI Coding Assistant", "Continue.dev", "Ollama", "VPS Deployment", "Open Source", "Developer Tools", "Self-hosting"]
categories: ["AI Development Tools"]
image: /images/posts/private-ai-coding-copilot-vps/featured.png
draft: false
---

## Why Build Your Own AI Coding Assistant?

The AI coding assistant landscape shifted dramatically since late 2025:

- **GitHub Copilot** raised prices to $10/mo (individual) / $19/mo (enterprise), and your code lives on Microsoft servers
- **Cursor** went partially closed-source at $20/mo, sparking controversy
- More companies are banning employees from uploading code to third-party AI services

**The solution**: Run [Ollama](https://ollama.ai) with open-source LLMs on your own VPS, paired with [Continue.dev](https://continue.dev) (open-source IDE extension) — a fully self-hosted AI coding experience.

**Your code never leaves your network. Model inference runs on your own VPS.** No third party ever sees your code.

## Architecture Overview

```
Your Machine (VS Code / JetBrains)
       │
       │ Continue.dev Extension
       │
       ▼
Your VPS (Ollama Service)
       │
       ├── deepseek-coder-v2 (code completion)
       ├── codestral (completion backup)
       ├── qwen2.5-coder:7b (lightweight option)
       └── llama3.1:8b (chat/explain)
```

## Cost Comparison

| Option | Monthly Cost | Privacy | Model Choice |
|--------|-------------|---------|-------------|
| GitHub Copilot | $10-19 | ❌ Code uploaded to Microsoft | Single model |
| Cursor Pro | $20 | ⚠️ Partially closed-source | Limited |
| **This Setup** | **$4-8** | **✅ Fully private** | **Any model** |

Minimum VPS specs:

- **Starter**: Hetzner CX22 (€3.99/mo, 2 vCPU / 4GB / 40GB) — runs 7B models
- **Recommended**: Hetzner CAX21 (€5.99/mo, 4 vCPU / 8GB / 40GB ARM) — runs 14B models
- **Advanced**: Netcup RS1000 (€5.50/mo, 4 vCPU / 8GB) or a GPU-equipped VPS

> 💡 CPU inference on 7B models (e.g., `qwen2.5-coder:7b`) takes 2-5 seconds per completion — perfectly usable for daily development. For 14B models, 8GB+ RAM is recommended.

## Step 1: Deploy Ollama on VPS

### 1. Install Ollama

```bash
# SSH into your VPS
ssh root@your-vps-ip

# One-command install
curl -fsSL https://ollama.ai/install.sh | sh

# Verify
ollama --version
```

### 2. Pull Code-Specialized Models

```bash
# DeepSeek Coder V2 (recommended, best code quality)
ollama pull deepseek-coder-v2:16b

# Qwen2.5 Coder 7B (lightweight, fast responses)
ollama pull qwen2.5-coder:7b

# Llama 3.1 8B (general chat assistance)
ollama pull llama3.1:8b

# List downloaded models
ollama list
```

> Initial model pulls take a few minutes depending on VPS bandwidth. deepseek-coder-v2:16b is ~9GB, qwen2.5-coder:7b is ~4.5GB.

### 3. Allow Remote Access to Ollama

Ollama listens on localhost by default. We need it to listen on all interfaces for your local IDE to connect.

```bash
# Edit systemd service config
systemctl edit ollama

# Add the following content:
```

```ini
[Service]
Environment="OLLAMA_HOST=0.0.0.0:11434"
```

```bash
# Restart Ollama
systemctl daemon-reload
systemctl restart ollama

# Verify it's listening
ss -tlnp | grep 11434
```

### 4. Security Hardening (Important!)

**Never expose Ollama directly to the public internet.** Use ufw to restrict access:

```bash
# Install ufw
apt install -y ufw

# Only allow your home/office IP
ufw allow from your-local-ip to any port 11434 proto tcp
ufw enable

# Or use WireGuard VPN (recommended)
# After connecting via VPN, let Ollama listen on the VPN interface only
```

> Best practice: Deploy an API-key-authenticated reverse proxy in front of Ollama (covered below).

## Step 2: Configure Continue.dev

### 1. Install the Continue Extension

- **VS Code**: Search for "Continue" in the extension marketplace and install
- **JetBrains**: Search for "Continue" in the plugin marketplace

### 2. Configure Ollama Connection

After installation, click the Continue icon in the sidebar and open the config file at `~/.continue/config.json`:

```json
{
  "models": [
    {
      "title": "DeepSeek Coder V2 (VPS)",
      "provider": "ollama",
      "model": "deepseek-coder-v2:16b",
      "apiBase": "http://your-vps-ip:11434",
      "completionOptions": {
        "temperature": 0.1,
        "topP": 0.9,
        "maxTokens": 4096
      }
    },
    {
      "title": "Qwen2.5 Coder 7B (VPS)",
      "provider": "ollama",
      "model": "qwen2.5-coder:7b",
      "apiBase": "http://your-vps-ip:11434",
      "completionOptions": {
        "temperature": 0.1,
        "topP": 0.9,
        "maxTokens": 2048
      }
    }
  ],
  "tabAutocompleteModel": {
    "title": "Qwen2.5 Coder (Tab Auto)",
    "provider": "ollama",
    "model": "qwen2.5-coder:7b",
    "apiBase": "http://your-vps-ip:11434"
  },
  "slashCommands": [
    {
      "name": "edit",
      "description": "Edit selected code"
    },
    {
      "name": "comment",
      "description": "Add comments to code"
    },
    {
      "name": "optimize",
      "description": "Optimize code performance"
    },
    {
      "name": "explain",
      "description": "Explain code logic"
    }
  ]
}
```

### 3. Tab Autocomplete Setup

Continue's inline tab autocomplete is one of its best features. In VS Code:

1. Open command palette (`Cmd+Shift+P` / `Ctrl+Shift+P`)
2. Type "Continue: Toggle Tab Autocomplete"
3. Enable it — suggestions will appear as inline gray text
4. Press `Tab` to accept suggestions

For `tabAutocompleteModel`, choose the fastest model. `qwen2.5-coder:7b` returns completions in about 2-4 seconds on a 4GB VPS — smooth enough for daily use.

## Step 3 (Advanced): API Key Auth + Reverse Proxy

Exposing port 11434 directly isn't secure enough. Use Nginx as a reverse proxy with API key authentication:

```bash
# Install Nginx
apt install -y nginx

# Create configuration
cat > /etc/nginx/sites-available/ollama-proxy << 'EOF'
server {
    listen 443 ssl;
    server_name ollama.your-domain.com;

    ssl_certificate /etc/letsencrypt/live/ollama.your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/ollama.your-domain.com/privkey.pem;

    location / {
        # API key validation
        if ($http_x_api_key != "your-secret-key") {
            return 401;
        }

        proxy_pass http://127.0.0.1:11434;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
EOF

# Enable config
ln -s /etc/nginx/sites-available/ollama-proxy /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
```

Then update your Continue config with the HTTPS URL and add `X-Api-Key` to HTTP headers.

## Model Selection Guide

| Model | Parameters | RAM Needed | Code Quality | Speed (4-core CPU) |
|-------|-----------|-----------|-------------|-------------------|
| `qwen2.5-coder:1.5b` | 1.5B | < 2GB | ⭐⭐ | ⚡ Very Fast |
| `qwen2.5-coder:7b` | 7B | ~4GB | ⭐⭐⭐⭐ | ⚡ Fast |
| `deepseek-coder-v2:16b` | 16B | ~9GB | ⭐⭐⭐⭐⭐ | 🐢 Slower |
| `codestral:22b` | 22B | ~12GB | ⭐⭐⭐⭐⭐ | 🐢 Slow |
| `starcoder2:15b` | 15B | ~8GB | ⭐⭐⭐⭐ | ⏳ Medium |

> **Beginner recommendation**: Start with `qwen2.5-coder:7b`. It's the sweet spot for 4GB VPS, offering the best balance of speed and quality.

## Advanced Optimization Tips

### GPU Acceleration (if you have a GPU VPS)

If your VPS has an NVIDIA GPU, Ollama automatically uses CUDA:

```bash
# Install NVIDIA drivers on GPU VPS
apt install -y nvidia-driver-545 nvidia-utils-545

# Verify GPU
nvidia-smi

# Ollama auto-detects GPU — no extra config needed
# GPU inference on 16B models is 5-10x faster than CPU
```

### Multi-VPS Load Balancing

With multiple VPS, use Nginx for load balancing:

```nginx
upstream ollama_backend {
    server vps1:11434 weight=3;
    server vps2:11434 weight=1;
}
```

### RAM Disk for Faster Model Loading

```bash
# Create 16GB RAM disk (requires enough RAM)
mount -t tmpfs -o size=16G tmpfs /mnt/ramdisk

# Symlink model blobs to RAM disk
ln -s /mnt/ramdisk/blobs /usr/share/ollama/.ollama/models/blobs
```

## Real-World Comparison

Testing with a Python Fibonacci generator:

**DeepSeek Coder V2 (16B)**:
```python
def fibonacci(n: int) -> list[int]:
    """Generate first n Fibonacci numbers."""
    if n <= 0:
        return []
    fib = [0, 1]
    for _ in range(2, n):
        fib.append(fib[-1] + fib[-2])
    return fib[:n]
```
- Quality: ⭐⭐⭐⭐⭐ Proper type hints, clean code
- Speed: 4-6 seconds (4-core VPS)

**Qwen2.5 Coder (7B)**:
- Quality: ⭐⭐⭐⭐ Mostly correct, occasional minor issues
- Speed: 2-3 seconds (4-core VPS)

> For daily development, 7B models are surprisingly capable. 16B models shine for complex algorithms and architecture decisions.

## FAQ

### Q: Will network latency be noticeable?

A: Depends on VPS location. If your VPS is geographically close (e.g., you're in Europe with a Hetzner VPS), latency is ~10-30ms. With streaming output (default in Continue), it's barely noticeable while typing.

### Q: Can I use multiple IDEs simultaneously?

A: Yes. Ollama handles concurrent requests. Configure each IDE instance with the same `apiBase` pointing to your VPS.

### Q: Does the VPS store my code?

A: Ollama processes inference in RAM only — input/output data is discarded immediately after processing. For maximum security, enable full-disk encryption on your VPS.

### Q: How do I switch models?

A: Just `ollama pull` the new model on the VPS, then update the `model` field in Continue config. No services need restarting.

## Summary

Building a private AI coding assistant with VPS + Ollama + Continue.dev gives you:

- ✅ **Full data privacy** — code never leaves your network
- ✅ **Free AI completions** — only pay for the VPS
- ✅ **Model freedom** — switch between any open-source models
- ✅ **Team sharing** — one VPS serves your entire team
- ✅ **Auditable** — fully open-source, no black boxes

Compared to GitHub Copilot at $10-19/mo or Cursor at $20/mo, a €3.99/mo VPS delivers comparable or better results — with the peace of mind that your code stays **yours**.

**Next steps**: SSH into your VPS right now, run `curl -fsSL https://ollama.ai/install.sh | sh`, then `ollama pull qwen2.5-coder:7b`. In ten minutes, you'll have your very own private AI coding copilot.
