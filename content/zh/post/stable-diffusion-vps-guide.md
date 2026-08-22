---
title: "VPS 上搭建私有 AI 图像生成服务：Stable Diffusion WebUI 完整部署指南"
description: "告别 Midjourney 订阅费！在 VPS 上自建 Stable Diffusion WebUI，支持txt2img/img2img/ControlNet/LoRA，一次部署永久免费使用，附完整 Docker Compose 配置与性能优化方案。"
date: 2026-08-22T10:00:00+08:00
lastmod: 2026-08-22T10:00:00+08:00
slug: "stable-diffusion-vps-guide"
image: /images/posts/stable-diffusion-vps-guide/featured.png
tags: ["Stable Diffusion", "AI图像生成", "自托管", "WebUI", "Docker", "AI绘画", "省钱", "VPS"]
categories: ["AI运维"]
aliases: [/zh/post/stable-diffusion-vps-guide/]
---

## 引言

2026 年，AI 图像生成已经从"科幻"变成了"日常"。Midjourney 订阅费每月 $10 起步，DALL-E 按次计费，Stable Diffusion 开源模型更是被各大商业产品底层采用——但你是否想过，**完全免费的 AI 图像生成其实就在你手边的 VPS 上**？

本文将带你从零开始，在 VPS 上部署一套完整的 Stable Diffusion WebUI（Automatic1111 版本），支持 **txt2img（文生图）、img2img（图生图）、ControlNet（精准控制）、LoRA 模型扩展** 等全部核心功能。部署完成后，你就可以在浏览器中自由创作，**零成本、零限制、零数据外传**。

---

## 一、方案选型：为什么选择 Stable Diffusion WebUI？

### 1.1 主流方案对比

| 方案 | 资源占用 | 功能丰富度 | 易用性 | 推荐场景 |
|------|----------|-----------|--------|----------|
| **SD WebUI (Automatic1111)** | 中 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | 全功能创作 |
| SD WebUI Forge | 高 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | GPU 显存受限 |
| ComfyUI | 低 | ⭐⭐⭐⭐ | ⭐⭐⭐ | 工作流自动化 |
| SD.Next | 低 | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | 轻量级部署 |
| Diffusers (代码级) | 自定义 | ⭐⭐⭐⭐⭐ | ⭐⭐ | 开发者集成 |

**本文选择 SD WebUI (Automatic1111)**，因为它是生态最完整、插件最丰富、社区最活跃的方案，适合大多数用户。

### 1.2 硬件需求

| 配置级别 | GPU | 显存 | 内存 | 磁盘 | 适用场景 |
|----------|-----|------|------|------|----------|
| **入门级** | 集成显卡/无GPU | 4GB+ | 8GB | 20GB | CPU 推理（慢但可用） |
| **推荐级** | NVIDIA GTX 1660 / RTX 3050 | 6GB | 16GB | 50GB | 日常创作 |
| **性能级** | NVIDIA RTX 3060 12GB / 4060 Ti 16GB | 12GB+ | 32GB | 100GB | 高速生成 + 大模型 |
| **旗舰级** | NVIDIA A100 / H100 | 40GB+ | 64GB | 200GB+ | 生产级批量生成 |

> **省钱技巧**：Vultr / Linode 的 GPU VPS 每小时约 $0.50，按需启停，月均成本可控制在 $30 以内，远低于 Midjourney 年费 $120。

---

## 二、VPS 准备与环境配置

### 2.1 选择 VPS 服务商

推荐以下支持 GPU 或高性价比的 VPS 服务商：

| 服务商 | GPU 选项 | 起步价 | 特点 |
|--------|---------|--------|------|
| **Vultr** | RTX 4090 / A100 | $0.50/小时 | 按小时计费，随时启停 |
| **Lambda Labs** | A100 / RTX 4090 | $0.50-1.50/小时 | 性价比最高的 GPU 云 |
| **RunPod** | 多种 GPU | $0.20/小时起 | 专为 AI 设计，模板丰富 |
| **Hetzner** | 无GPU | €4/月 | 纯 CPU 方案，适合轻量使用 |
| **AWS EC2** | g5/g6 | $0.50+/小时 | 生态完整，但贵 |
| **阿里云/腾讯云** | GPU 实例 | ¥2/小时起 | 国内访问快 |

### 2.2 系统初始化

以 Ubuntu 24.04 为例：

```bash
# 更新系统
sudo apt update && sudo apt upgrade -y

# 安装基础工具
sudo apt install -y git curl wget unzip rsync ca-certificates

# 安装 Docker（推荐方式）
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
newgrp docker

# 安装 NVIDIA Container Toolkit（GPU 模式必需）
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://nvidia.github.io/libnvidia-container/stable/deb/$(. /etc/os-release && echo $UBUNTU_CODENAME) main" | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt update
sudo apt install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

### 2.3 验证 GPU 识别

```bash
# 检查 NVIDIA 驱动
nvidia-smi

# 验证 Docker GPU 支持
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
```

---

## 三、部署 Stable Diffusion WebUI

### 3.1 使用 Docker Compose 部署（推荐）

创建项目目录：

```bash
mkdir -p ~/stable-diffusion/{models,outputs,data}
cd ~/stable-diffusion
```

创建 `docker-compose.yml`：

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

> **注意**：如果 VPS 没有 GPU，去掉 `devices` 和 `deploy` 部分，WebUI 会自动使用 CPU 模式（较慢但可用）。

启动服务：

```bash
docker compose up -d
```

### 3.2 首次访问与配置

浏览器访问 `http://你的VPS_IP:7860`，首次启动会：

1. 自动克隆 SD WebUI 仓库
2. 下载基础模型（可选）
3. 安装 Python 依赖

### 3.3 下载模型文件

 Stable Diffusion 的核心是模型。推荐下载以下模型到 `~/stable-diffusion/models/Stable-diffusion/`：

| 模型 | 用途 | 大小 | 下载链接 |
|------|------|------|----------|
| **SDXL Base 1.0** | 高质量通用生成 | 6.7GB | HuggingFace |
| **SD 1.5** | 快速创作/插件兼容 | 4.3GB | HuggingFace |
| **Juggernaut XL** | 写实风格 | 6.7GB | CivitAI |
| **RevAnimated** | 动漫风格 | 6.7GB | CivitAI |

```bash
# 从 HuggingFace 下载 SDXL
cd ~/stable-diffusion/models/Stable-diffusion
wget https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/sd_xl_base_1.0.safetensors
```

---

## 四、核心功能使用指南

### 4.1 txt2img（文生图）

在 WebUI 的 txt2img 标签页中：

1. **Prompt（正向提示词）**：描述你想要生成的图像
   - 示例：`a futuristic city at sunset, cyberpunk style, neon lights, highly detailed, 4k`
2. **Negative Prompt（反向提示词）**：描述你不想要的内容
   - 示例：`blurry, low quality, distorted, watermark`
3. **采样方法**：推荐 `Euler a`（快速）或 `DPM++ 2M Karras`（高质量）
4. **采样步数**：20-30 步通常足够
5. **图像尺寸**：SDXL 推荐 1024×1024，SD 1.5 推荐 512×512
6. **点击 Generate**

### 4.2 img2img（图生图）

上传图片后可以进行：

- **去噪强度（Denoosing strength）**：0.0-1.0，越高变化越大
- **图像修复（Inpainting）**：遮罩指定区域进行局部重绘
- **外补绘制（Outpainting）**：扩展图像边界

### 4.3 ControlNet（精准控制）

ControlNet 是 SD WebUI 最强大的功能之一，可以实现：

- **Canny 边缘检测**：根据线稿生成彩色图像
- **Depth 深度图**：控制画面景深和空间关系
- **OpenPose 姿态控制**：精确控制人物姿势
- **Reference 参考图**：保持风格一致性

```yaml
# 在 docker-compose.yml 中添加 ControlNet 支持
volumes:
  - ./outputs:/backend/outputs
  - ./data:/backend/data
  - ./models/ControlNet:/backend/models/ControlNet
```

### 4.4 LoRA 模型扩展

LoRA（Low-Rank Adaptation）是轻量级模型微调技术，可以：

- 添加特定艺术风格
- 生成特定角色/人物
- 调整图像色调和氛围

下载 LoRA 文件到 `~/stable-diffusion/models/LoRA/`：

```bash
cd ~/stable-diffusion/models/LoRA
wget https://civitai.com/api/download/models/XXXXX -O your-lora.safetensors
```

在 WebUI 中使用：在 prompt 中添加 `<lora:your-lora:0.8>` 即可调用。

---

## 五、性能优化与安全加固

### 5.1 性能优化配置

编辑 `~/stable-diffusion/webui-user.sh`：

```bash
#!/bin/bash
export COMMANDLINE_ARGS="--xformers --opt-split-attention --enable-unsafe-sdwebui_args"
export PYTHONFAULTHANDLER=1
export HF_HUB_ENABLE_HF_TRANSFER=1
```

关键参数说明：

| 参数 | 作用 | 适用场景 |
|------|------|----------|
| `--xformers` | 内存优化，加速推理 | 显存 ≤ 8GB |
| `--opt-split-attention` | 进一步降低显存占用 | 显存 ≤ 6GB |
| `--precision full` | 提高生成质量 | 显存充足 |
| `--no-half` | 禁用半精度，减少 artifact | 高质量需求 |
| `--api` | 启用 API 接口 | 自动化集成 |

### 5.2 安全加固

**重要**：SD WebUI 默认暴露 7860 端口，必须进行安全加固：

```nginx
# Nginx 反向代理配置
server {
    listen 80;
    server_name sd.yourdomain.com;
    
    location / {
        proxy_pass http://127.0.0.1:7860;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket 支持
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

添加 API 密钥保护：

```bash
export WEBUI_ARGS="--api --api-auth your-secret-api-key"
```

使用 Cloudflare Tunnel 暴露服务（无需公网 IP）：

```bash
# 安装 cloudflared
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
sudo dpkg -i cloudflared-linux-amd64.deb

# 启动 Tunnel
cloudflared tunnel --url http://localhost:7860
```

### 5.3 自动化管理脚本

创建 `~/stable-diffusion/manage.sh`：

```bash
#!/bin/bash
case "$1" in
  start)
    docker compose up -d
    echo "✅ SD WebUI 已启动，访问 http://$(curl -s ifconfig.me):7860"
    ;;
  stop)
    docker compose stop
    echo "⏹️ SD WebUI 已停止"
    ;;
  restart)
    docker compose restart
    echo "🔄 SD WebUI 已重启"
    ;;
  update)
    docker compose pull
    docker compose up -d
    echo "📦 SD WebUI 已更新到最新版本"
    ;;
  status)
    docker compose ps
    ;;
  logs)
    docker compose logs -f
    ;;
  *)
    echo "用法: $0 {start|stop|restart|update|status|logs}"
    exit 1
    ;;
esac
```

---

## 六、成本对比：自建 vs 云服务

### 6.1 月度成本对比

| 方案 | 月费 | 生成次数 | 额外成本 |
|------|------|----------|----------|
| **Midjourney Basic** | $10 | 约 200-400 张 | 无 |
| **DALL-E 3 (API)** | $0.04/张 | 250 张 = $10 | 按次计费 |
| **Stable Diffusion (VPS)** | $15-30 | **无限** | 一次性 VPS 费用 |
| **Stable Diffusion (GPU VPS 按需)** | $0.50/小时 | **无限** | 仅支付使用时间 |

### 6.2 回本分析

假设你每月生成 200 张图像：

- **Midjourney**：$10/月 × 12 月 = **$120/年**
- **自建 VPS**：$30/月 × 6 月 = **$180**（一次性投入），之后免费
- **GPU 按需**：每天用 2 小时 × $0.50 × 30 天 = **$30/月**

**结论**：如果你每月生成超过 100 张图像，自建 VPS 在 3-6 个月内即可回本，之后完全免费。

---

## 七、常见问题排查

### Q1：显存不足怎么办？

```bash
# 方案1：使用 --medvram 参数
export WEBUI_ARGS="--xformers --medvram"

# 方案2：切换到 SD 1.5 模型（比 SDXL 更省显存）
# 方案3：使用 SD WebUI Forge 版本（更低的显存占用）
```

### Q2：生成速度太慢？

- 确保使用了 `--xformers` 参数
- 降低采样步数从 30 降到 20
- 使用更小的图像尺寸（512×512）
- 考虑升级到更大显存的 GPU

### Q3：如何备份生成的图像？

```bash
# 自动备份脚本
#!/bin/bash
BACKUP_DIR="/backup/sd-outputs-$(date +%Y%m%d)"
mkdir -p $BACKUP_DIR
cp -r ~/stable-diffusion/outputs/* $BACKUP_DIR/
# 可选：上传到 S3/R2
aws s3 sync $BACKUP_DIR s3://your-bucket/sd-backups/
```

### Q4：如何限制他人滥用？

```bash
# 启用 Basic Auth
export WEBUI_ARGS="--api --api-auth user:password"

# 或使用 Nginx 基本认证
# 或配置 Cloudflare Access 策略
```

---

## 八、进阶：API 集成与自动化

### 8.1 使用 API 进行批量生成

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

# 保存图片
for i, img in enumerate(images):
    with open(f"output_{i}.png", "wb") as f:
        f.write(requests.get(f"data:image/png;base64,{img}").content)
```

### 8.2 定时任务自动创作

```bash
# crontab 示例：每天早上 9 点生成一张随机创意图
0 9 * * * cd ~/stable-diffusion && python3 auto_generate.py >> logs/auto.log 2>&1
```

---

## 结语

在 VPS 上搭建 Stable Diffusion WebUI 不仅是一次技术实践，更是一种**成本控制和数据自主**的选择。当你拥有自己的 AI 图像生成服务时：

- ✅ **零订阅费用**：一次性投入，长期使用
- ✅ **数据隐私**：所有生成内容存储在本地
- ✅ **无审查限制**：完全自由的内容创作
- ✅ **无限生成**：不受任何次数限制
- ✅ **可扩展**：随时添加新模型、新插件

从现在开始，把你的 VPS 变成一个真正的 AI 创作工作室吧！

---

## 附录：完整部署检查清单

- [ ] 选择并启动 VPS（推荐 GPU 实例）
- [ ] 安装 Docker + NVIDIA Container Toolkit
- [ ] 克隆并配置 SD WebUI
- [ ] 下载基础模型（SDXL 或 SD 1.5）
- [ ] 配置性能优化参数
- [ ] 设置反向代理 + SSL
- [ ] 配置 API 认证
- [ ] 创建自动化管理脚本
- [ ] 测试生成流程
- [ ] 设置监控和告警
