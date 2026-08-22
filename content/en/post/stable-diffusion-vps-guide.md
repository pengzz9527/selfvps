---
title: "Self-Hosted AI Image Generation on VPS: Complete Stable Diffusion WebUI Deployment Guide"
description: "Say goodbye to Midjourney subscriptions! Build your own Stable Diffusion WebUI on VPS with txt2img, img2img, ControlNet, and LoRA support. Full Docker Compose setup and performance optimization."
date: 2026-08-22T10:00:00+08:00
lastmod: 2026-08-22T10:00:00+08:00
slug: "stable-diffusion-vps-guide"
image: /images/posts/stable-diffusion-vps-guide/featured.png
tags: ["Stable Diffusion", "AI Image Generation", "Self-Hosted", "WebUI", "Docker", "AI Art", "Cost Saving", "VPS"]
categories: ["AI Operations"]
aliases: [/en/post/stable-diffusion-vps-guide/]
---

## Introduction

In 2026, AI image generation has evolved from a novelty into a daily tool. Midjourney subscriptions start at $10/month, DALL-E charges per generation, and open-source Stable Diffusion models power countless commercial products underneath. But have you ever considered that **completely free AI image generation is already available on your VPS**?

This guide walks you through deploying a complete Stable Diffusion WebUI (Automatic1111 version) on your VPS, supporting **txt2img, img2img, ControlNet, LoRA extensions**, and all core features. Once deployed, you can create freely in your browser — **zero cost, zero limits, zero data leakage**.

---

## Chapter 1: Why Stable Diffusion WebUI?

### 1.1 Platform Comparison

| Solution | Resource Usage | Feature Richness | Ease of Use | Best For |
|----------|---------------|------------------|-------------|----------|
| **SD WebUI (A1111)** | Medium | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | Full-featured creation |
| SD WebUI Forge | High | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | Limited GPU memory |
| ComfyUI | Low | ⭐⭐⭐⭐ | ⭐⭐⭐ | Workflow automation |
| SD.Next | Low | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | Lightweight deployment |
| Diffusers (code) | Custom | ⭐⭐⭐⭐⭐ | ⭐⭐ | Developer integration |

**We choose SD WebUI (Automatic1111)** for its complete ecosystem, richest plugins, and most active community.

### 1.2 Hardware Requirements

| Tier | GPU | VRAM | RAM | Disk | Use Case |
|------|-----|------|-----|------|----------|
| **Entry** | Integrated / No GPU | 4GB+ | 8GB | 20GB | CPU inference (slow but usable) |
| **Recommended** | NVIDIA GTX 1660 / RTX 3050 | 6GB | 16GB | 50GB | Daily creation |
| **Performance** | NVIDIA RTX 3060 12GB / 4060 Ti 16GB | 12GB+ | 32GB | 100GB | High-speed generation |
| **Flagship** | NVIDIA A100 / H100 | 40GB+ | 64GB | 200GB+ | Production batch generation |

> **Cost tip**: GPU VPS from Vultr/Linode costs ~$0.50/hour — start and stop on demand, averaging under $30/month, far below Midjourney's annual cost of $120.

---

## Chapter 2: VPS Preparation

### 2.1 Choosing a VPS Provider

| Provider | GPU Option | Starting Price | Features |
|----------|-----------|----------------|----------|
| **Vultr** | RTX 4090 / A100 | $0.50/hour | Pay-by-hour, start/stop anytime |
| **Lambda Labs** | A100 / RTX 4090 | $0.50-1.50/hour | Best GPU price-to-performance |
| **RunPod** | Various GPUs | $0.20/hour+ | AI-optimized, rich templates |
| **Hetzner** | No GPU | €4/month | Pure CPU, suitable for light use |
| **AWS EC2** | g5/g6 | $0.50+/hour | Complete ecosystem, but expensive |
| **Alibaba/Tencent Cloud** | GPU instances | ¥2/hour+ | Fast domestic access |

### 2.2 System Initialization

Using Ubuntu 24.04 as example:

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install base tools
sudo apt install -y git curl wget unzip rsync ca-certificates

# Install Docker
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
newgrp docker

# Install NVIDIA Container Toolkit (required for GPU mode)
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://nvidia.github.io/libnvidia-container/stable/deb/$(. /etc/os-release && echo $UBUNTU_CODENAME) main" | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt update
sudo apt install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

### 2.3 Verify GPU Detection

```bash
# Check NVIDIA driver
nvidia-smi

# Verify Docker GPU support
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
```

---

## Chapter 3: Deploying Stable Diffusion WebUI

### 3.1 Docker Compose Deployment (Recommended)

Create project directory:

```bash
mkdir -p ~/stable-diffusion/{models,outputs,data}
cd ~/stable-diffusion
```

Create `docker-compose.yml`:

```yaml
version: "3.8"

services:
  sd-webui:
    image: ghcr.io/fofr/stable-diffusion-webui:latest
    container_name: sd-webui
    restart: unless-stopped
    ports:
      - "7860:7860"
    environment:
      - WEBUI_PORT=7860
      - WEBUI_ARGS=--api --enable-insecure-extension-access --no-half --precision full
    volumes:
      - ./outputs:/backend/outputs
      - ./data:/backend/data
    devices:
      - /dev/null
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
```

> **Note**: If your VPS has no GPU, remove the `devices` and `deploy` sections. WebUI will automatically fall back to CPU mode (slower but functional).

Start the service:

```bash
docker compose up -d
```

### 3.2 First Access and Configuration

Browser to `http://your-vps-ip:7860`. First launch will:

1. Auto-clone the SD WebUI repository
2. Download base models (optional)
3. Install Python dependencies

### 3.3 Downloading Models

The core of Stable Diffusion is the model. Recommended downloads to `~/stable-diffusion/models/Stable-diffusion/`:

| Model | Purpose | Size | Download |
|-------|---------|------|----------|
| **SDXL Base 1.0** | High-quality general generation | 6.7GB | HuggingFace |
| **SD 1.5** | Fast creation / plugin compatibility | 4.3GB | HuggingFace |
| **Juggernaut XL** | Photorealistic style | 6.7GB | CivitAI |
| **RevAnimated** | Anime style | 6.7GB | CivitAI |

```bash
# Download SDXL from HuggingFace
cd ~/stable-diffusion/models/Stable-diffusion
wget https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/sd_xl_base_1.0.safetensors
```

---

## Chapter 4: Core Features

### 4.1 txt2img (Text to Image)

In the txt2img tab:

1. **Prompt**: Describe the image you want
   - Example: `a futuristic city at sunset, cyberpunk style, neon lights, highly detailed, 4k`
2. **Negative Prompt**: Describe what you don't want
   - Example: `blurry, low quality, distorted, watermark`
3. **Sampling Method**: Recommend `Euler a` (fast) or `DPM++ 2M Karras` (high quality)
4. **Sampling Steps**: 20-30 steps usually sufficient
5. **Image Size**: SDXL recommended 1024×1024, SD 1.5 recommended 512×512
6. **Click Generate**

### 4.2 img2img (Image to Image)

Upload an image for:

- **Denoising strength**: 0.0-1.0, higher = more change
- **Inpainting**: Mask specific areas for local redraw
- **Outpainting**: Extend image boundaries

### 4.3 ControlNet (Precise Control)

ControlNet is SD WebUI's most powerful feature:

- **Canny edge detection**: Generate color images from line drawings
- **Depth maps**: Control spatial relationships and depth of field
- **OpenPose**: Precise character pose control
- **Reference**: Maintain style consistency

### 4.4 LoRA Model Extensions

LoRA (Low-Rank Adaptation) enables:

- Adding specific art styles
- Generating specific characters/figures
- Adjusting color tone and atmosphere

Download LoRA files to `~/stable-diffusion/models/LoRA/`:

```bash
cd ~/stable-diffusion/models/LoRA
wget https://civitai.com/api/download/models/XXXXX -O your-lora.safetensors
```

Use in WebUI: Add `<lora:your-lora:0.8>` to your prompt.

---

## Chapter 5: Performance Optimization & Security

### 5.1 Performance Optimization

Edit `~/stable-diffusion/webui-user.sh`:

```bash
#!/bin/bash
export COMMANDLINE_ARGS="--xformers --opt-split-attention --enable-unsafe-sdwebui_args"
export PYTHONFAULTHANDLER=1
export HF_HUB_ENABLE_HF_TRANSFER=1
```

| Parameter | Purpose | Scenario |
|-----------|---------|----------|
| `--xformers` | Memory optimization, faster inference | VRAM ≤ 8GB |
| `--opt-split-attention` | Further reduce VRAM | VRAM ≤ 6GB |
| `--precision full` | Higher generation quality | Sufficient VRAM |
| `--no-half` | Disable half-precision, reduce artifacts | High quality needs |
| `--api` | Enable API interface | Automation integration |

### 5.2 Security Hardening

**Important**: SD WebUI exposes port 7860 by default — security hardening is essential:

```nginx
# Nginx reverse proxy configuration
server {
    listen 80;
    server_name sd.yourdomain.com;
    
    location / {
        proxy_pass http://127.0.0.1:7860;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

Add API key protection:

```bash
export WEBUI_ARGS="--api --api-auth your-secret-api-key"
```

Use Cloudflare Tunnel (no public IP needed):

```bash
# Install cloudflared
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
sudo dpkg -i cloudflared-linux-amd64.deb

# Start Tunnel
cloudflared tunnel --url http://localhost:7860
```

### 5.3 Automation Management Script

Create `~/stable-diffusion/manage.sh`:

```bash
#!/bin/bash
case "$1" in
  start)
    docker compose up -d
    echo "✅ SD WebUI started, visit http://$(curl -s ifconfig.me):7860"
    ;;
  stop)
    docker compose stop
    echo "⏹️ SD WebUI stopped"
    ;;
  restart)
    docker compose restart
    echo "🔄 SD WebUI restarted"
    ;;
  update)
    docker compose pull
    docker compose up -d
    echo "📦 SD WebUI updated to latest version"
    ;;
  status)
    docker compose ps
    ;;
  logs)
    docker compose logs -f
    ;;
  *)
    echo "Usage: $0 {start|stop|restart|update|status|logs}"
    exit 1
    ;;
esac
```

---

## Chapter 6: Cost Comparison — Self-Hosted vs Cloud Services

### 6.1 Monthly Cost Comparison

| Solution | Monthly Cost | Generations | Extra Cost |
|----------|-------------|-------------|------------|
| **Midjourney Basic** | $10 | ~200-400 images | None |
| **DALL-E 3 (API)** | $0.04/image | 250 images = $10 | Pay per use |
| **Stable Diffusion (VPS)** | $15-30 | **Unlimited** | One-time VPS cost |
| **Stable Diffusion (GPU VPS on-demand)** | $0.50/hour | **Unlimited** | Only pay usage time |

### 6.2 Break-Even Analysis

Assuming 200 images/month:

- **Midjourney**: $10/month × 12 months = **$120/year**
- **Self-hosted VPS**: $30/month × 6 months = **$180** (one-time investment), then free
- **GPU on-demand**: 2 hours/day × $0.50 × 30 days = **$30/month**

**Conclusion**: If you generate over 100 images per month, self-hosting pays for itself in 3-6 months, then becomes completely free.

---

## Chapter 7: Troubleshooting

### Q1: Insufficient VRAM?

```bash
# Option 1: Use --medvram flag
export WEBUI_ARGS="--xformers --medvram"

# Option 2: Switch to SD 1.5 model (less VRAM than SDXL)
# Option 3: Use SD WebUI Forge version (lower VRAM usage)
```

### Q2: Generation too slow?

- Ensure `--xformers` parameter is used
- Reduce sampling steps from 30 to 20
- Use smaller image dimensions (512×512)
- Consider upgrading to a larger VRAM GPU

### Q3: How to backup generated images?

```bash
# Auto-backup script
#!/bin/bash
BACKUP_DIR="/backup/sd-outputs-$(date +%Y%m%d)"
mkdir -p $BACKUP_DIR
cp -r ~/stable-diffusion/outputs/* $BACKUP_DIR/
# Optional: upload to S3/R2
aws s3 sync $BACKUP_DIR s3://your-bucket/sd-backups/
```

### Q4: How to prevent abuse?

```bash
# Enable Basic Auth
export WEBUI_ARGS="--api --api-auth user:password"

# Or use Nginx basic auth
# Or configure Cloudflare Access policies
```

---

## Chapter 8: Advanced — API Integration & Automation

### 8.1 Batch Generation via API

```python
import requests

API_URL = "http://your-vps:7860/sdapi/v1/txt2img"

payload = {
    "prompt": "a beautiful sunset over the ocean, photorealistic, 8k",
    "negative_prompt": "blurry, low quality",
    "steps": 25,
    "cfg_scale": 7,
    "width": 1024,
    "height": 1024,
    "sampler_name": "Euler a"
}

response = requests.post(API_URL, json=payload)
images = response.json()["images"]

# Save images
for i, img in enumerate(images):
    with open(f"output_{i}.png", "wb") as f:
        f.write(requests.get(f"data:image/png;base64,{img}").content)
```

### 8.2 Scheduled Automated Creation

```bash
# crontab example: Generate a random creative image every day at 9 AM
0 9 * * * cd ~/stable-diffusion && python3 auto_generate.py >> logs/auto.log 2>&1
```

---

## Conclusion

Building Stable Diffusion WebUI on your VPS is not just a technical exercise — it's a choice for **cost control and data autonomy**. When you own your own AI image generation service:

- ✅ **Zero subscription fees**: One-time investment, lifelong use
- ✅ **Data privacy**: All generated content stored locally
- ✅ **No censorship**: Completely free content creation
- ✅ **Unlimited generations**: No rate limits whatsoever
- ✅ **Extensible**: Add new models and plugins anytime

Start turning your VPS into a true AI creation studio today!

---

## Appendix: Complete Deployment Checklist

- [ ] Select and start VPS (GPU instance recommended)
- [ ] Install Docker + NVIDIA Container Toolkit
- [ ] Clone and configure SD WebUI
- [ ] Download base models (SDXL or SD 1.5)
- [ ] Configure performance optimization parameters
- [ ] Set up reverse proxy + SSL
- [ ] Configure API authentication
- [ ] Create automation management scripts
- [ ] Test generation workflow
- [ ] Set up monitoring and alerts
