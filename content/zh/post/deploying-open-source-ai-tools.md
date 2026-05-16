---
title: "部署开源 AI 工具合集：在 VPS 上搭建 LocalAI、Ollama、Stable Diffusion 等"
description: "2025 年可自托管的开源 AI 工具大盘点——从 LocalAI 到 Ollama，从 Whisper 到 Stable Diffusion，教你在自己的 VPS 上搭建私有 AI 服务"
date: 2026-05-16T14:00:00+08:00
slug: "deploying-open-source-ai-tools"
tags: ["AI", "开源AI", "LocalAI", "Ollama", "Stable Diffusion", "Whisper", "Docker", "自托管"]
categories: ["AI部署"]
aliases: [/zh/post/deploying-open-source-ai-tools/]
---

## 为什么要自托管 AI 工具？

随着 AI 技术的快速发展，越来越多的开源 AI 工具可以在自己的服务器上运行。自托管 AI 的优势包括：

- 🔒 **数据隐私**：敏感数据不出服务器
- 💰 **成本可控**：按需使用，无需支付 API 订阅费
- ⚡ **低延迟**：本地推理，无需网络等待
- 🎯 **定制化**：可选模型、参数完全由你控制

## 环境要求

自托管 AI 工具对硬件有一定要求。以下是推荐的 VPS 配置：

| 用途 | 最低配置 | 推荐配置 |
|------|----------|----------|
| LLM 推理（7B 模型） | 8GB RAM, 4核 | 16GB RAM, 8核 + GPU |
| 语音转文字 | 4GB RAM, 2核 | 8GB RAM, 4核 |
| 图片生成 | 8GB RAM + 4GB VRAM | 16GB RAM + 8GB VRAM |

> ⚠️ **注意**：如果需要 GPU 加速，建议选择配备 NVIDIA GPU 的云服务器，如 Hetzner（带 GPU 的云实例）或 RunPod、Vast.ai 等 GPU 云平台。

## 工具一：Ollama — 本地运行大语言模型

[Ollama](https://ollama.com) 是目前最简单的大语言模型运行工具，支持 Llama、Mistral、Qwen 等主流模型。

### 安装与使用

```bash
# 使用 Docker 一键部署
docker run -d --name ollama -p 11434:11434 \
  -v ollama:/root/.ollama \
  ollama/ollama

# 拉取并运行模型
docker exec -it ollama ollama pull llama3.2:1b
docker exec -it ollama ollama run llama3.2:1b

# API 调用
curl http://localhost:11434/api/generate -d '{
  "model": "llama3.2:1b",
  "prompt": "What is self-hosting?",
  "stream": false
}'
```

### 推荐模型

| 模型 | 参数规模 | 内存需求 | 适用场景 |
|------|----------|----------|----------|
| llama3.2:1b | 1B | <2GB | 轻量问答 |
| llama3.2:3b | 3B | ~3GB | 通用对话 |
| qwen2.5:7b | 7B | ~8GB | 中文优化 |
| mistral:7b | 7B | ~8GB | 英文推理 |

## 工具二：LocalAI — OpenAI API 兼容方案

[LocalAI](https://localai.io) 是一个 OpenAI API 的替代品，支持 LLM、TTS、图像生成等多种功能，API 完全兼容 OpenAI。

```bash
# Docker Compose 部署
mkdir -p ~/localai && cd ~/localai

cat > docker-compose.yml << 'EOF'
version: '3.8'
services:
  localai:
    image: localai/localai:latest
    ports:
      - "8080:8080"
    volumes:
      - ./models:/build/models
    environment:
      - THREADS=4
      - CONTEXT_SIZE=2048
    command: ["/usr/bin/local-ai"]
EOF

docker compose up -d
```

### 使用示例

```bash
# 聊天补全（兼容 OpenAI Python SDK）
curl http://localhost:8080/v1/chat/completions -d '{
  "model": "llama3.2-3b",
  "messages": [{"role": "user", "content": "Hello!"}]
}'
```

## 工具三：OpenAI Whisper — 语音转文字

OpenAI 的 [Whisper](https://github.com/openai/whisper) 是一个开源语音识别模型，支持 99+ 种语言。

```bash
# Docker 部署
docker run -d --name whisper \
  -p 9000:9000 \
  -v whisper-data:/data \
  onerahmet/openai-whisper-asr-webservice:latest
```

**使用场景**：
- 会议录音转文字
- 视频字幕自动生成
- 语音输入系统

## 工具四：Stable Diffusion — 图片生成

通过 [Automatic1111 WebUI](https://github.com/AUTOMATIC1111/stable-diffusion-webui) 部署：

```bash
# Docker 部署（需要 GPU）
docker run -d --name sd-webui \
  --gpus all \
  -p 7860:7860 \
  -v models:/app/stable-diffusion-webui/models \
  abdibrokhim/stable-diffusion-webui:latest
```

## 工具五：LobeChat — AI 聊天界面

[LobeChat](https://github.com/lobehub/lobe-chat) 是一个现代 AI 聊天界面，支持接入 Ollama、LocalAI 等多种后端。

```bash
# Docker 部署
docker run -d --name lobe-chat \
  -p 3210:3210 \
  -e OLLAMA_PROXY_URL=http://localhost:11434 \
  lobehub/lobe-chat:latest
```

## 组合部署架构

推荐的自托管 AI 堆栈：

```
用户 → Nginx → LobeChat (前端界面)
                ├── Ollama (LLM 推理)
                ├── LocalAI (OpenAI 兼容 API)
                └── Whisper (语音识别)
```

## 总结

2025 年，自托管 AI 工具已经从"小众玩法"变成了"可行方案"。随着硬件成本下降和模型优化技术的进步，在个人 VPS 上运行 AI 服务已经不再是遥不可及的事情。

### 快速开始

1. 先从 **Ollama + LobeChat** 开始，体验最简部署
2. 按需添加 **Whisper** 处理语音
3. 配置 GPU 后加入 **Stable Diffusion**

> 💡 **提示**：如果 VPS 资源有限，可以从 1B-3B 参数的小模型开始，逐步探索升级。
