---
title: "Harbor：一行命令在 VPS 上部署完整的 AI 大模型栈"
description: "使用 Harbor 一行命令在 VPS 上部署 Ollama、Open WebUI、vLLM、llama.cpp、ComfyUI 等全套 AI 服务——无需手动配置 Docker Compose 和反向代理"
date: 2026-05-19T11:35:13+08:00
slug: "harbor-ai-stack-deployment"
tags: ["Harbor", "Ollama", "Open WebUI", "Docker", "VPS部署", "大模型", "自托管"]
categories: ["AI部署"]
aliases: [/zh/post/harbor-ai-stack-deployment/]
draft: false
---

## 什么是 Harbor？

[Harbor](https://github.com/av/harbor)（GitHub 2900+ ⭐）是一个 CLI 工具，能够用一条命令启动完整的本地大模型技术栈。你可以把它理解为 AI 界的 Docker Compose——它自动将后端（Ollama、llama.cpp、vLLM）、前端（Open WebUI、Lobe Chat、LibreChat）和支持服务（SearXNG 网络搜索、Speaches 语音、ComfyUI 图像生成）串联在一起，开箱即用。

```bash
# 只需这一条命令
harbor up
# Open WebUI + Ollama 已在你 VPS 上运行
```

无需再手动编写 Docker Compose 文件、配置 Nginx 反向代理或调试跨服务网络连接——Harbor 自动处理这一切。

---

## 为什么在 VPS 上用 Harbor？

在 VPS 上运行大模型正变得越来越实用：

- **廉价 GPU 云**：Vast.ai、RunPod、TensorDock 等平台提供 $0.30–$0.80/小时的 GPU 实例
- **量化模型成熟**：7B–14B 参数模型（Qwen2.5、Phi-4、Llama 3）通过 GGUF 量化后仅需 6–16GB 显存
- **数据隐私**：你的 API 调用、提示词和文档永不离开你的基础设施

Harbor 将最繁琐的**软件配置**部分化繁为简，让你专注于模型的实际使用。

---

## 前置条件

安装 Harbor 前，VPS 需满足以下条件：

| 要求 | 最低配置 | 推荐配置 |
|---|---|---|
| Docker Engine | 24.x | 27.x+ |
| Docker Compose | 2.23.1+ | 2.30+ |
| 内存 | 8 GB | 16 GB+ |
| 磁盘 | 20 GB | 50 GB+ |
| GPU（可选） | NVIDIA 6 GB 显存 | NVIDIA 12 GB+ 显存 |

验证 Docker 环境：

```bash
docker --version
docker compose version
```

---

## 第一步：安装 Harbor

Harbor 提供一行命令安装：

```bash
curl https://raw.githubusercontent.com/av/harbor/refs/heads/main/install.sh | bash
```

该命令将 `harbor` CLI 安装到 `/usr/local/bin`。验证安装：

```bash
harbor --version
harbor doctor   # 检查 Docker、磁盘空间和 GPU 可用性
```

> **没有 GPU？** 没关系。Harbor 可以在 CPU 上运行模型。对于 7B 模型搭配 8GB 内存，预计 3–8 tokens/秒——聊天和批量处理完全可用。

---

## 第二步：部署默认栈

默认栈包括 **Ollama**（后端）+ **Open WebUI**（前端）。启动它：

```bash
harbor up
```

Harbor 会自动：
1. 拉取最新的 Docker 镜像
2. 在 `localhost:11434` 启动 Ollama
3. 在 `localhost:3000` 启动 Open WebUI
4. 将它们自动连通

当看到 "Services started successfully" 时，在浏览器打开：

```bash
harbor open
```

**首次使用？** 在 Open WebUI 中创建管理员账户，然后在管理面板或通过 CLI 拉取模型：

```bash
# 从 VPS 终端拉取模型
docker exec -it $(docker ps -q -f name=ollama) ollama pull qwen2.5:7b
# 或者试试适合 8GB 内存的小模型
docker exec -it $(docker ps -q -f name=ollama) ollama pull phi-4-mini:3.8b
```

也可以使用 Harbor 内置的模型管理命令：

```bash
harbor ollama pull qwen2.5:7b
```

---

## 第三步：添加支持服务

Harbor 的真正威力在于可以在基础栈上叠加服务：

```bash
# 添加网络搜索 RAG（SearXNG）+ 语音服务（Speaches）
harbor up searxng speaches
```

启用后：
- **SearXNG** → Open WebUI 可以搜索网络并将结果输入 LLM 上下文（Web RAG）
- **Speaches** → 兼容 OpenAI API 的语音转文字和文字转语音（whisper + TTS）

其他有用的服务：

```bash
# 图像生成
harbor up comfyui

# 替代推理后端
harbor up llamacpp   # CPU 友好的 GGUF 推理
harbor up vllm       # 高吞吐 GPU 推理

# 替代前端
harbor up lobechat   # 支持多提供商的新式 UI
harbor up dify       # LLM 应用开发平台
```

---

## 第四步：启用 GPU 加速（NVIDIA）

如果 VPS 配备 NVIDIA GPU，启用 Docker GPU 直通：

**Ubuntu/Debian：**
```bash
# 安装 NVIDIA Container Toolkit
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
  sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
sudo systemctl restart docker
```

**验证 GPU 访问：**
```bash
docker run --rm --gpus all nvidia/cuda:12.0.0-base-ubuntu22.04 nvidia-smi
```

安装后，Harbor 会自动检测 `nvidia` 能力（capability），并向支持的容器传递 `--gpus all` 参数。

---

## 第五步：安全暴露 Harbor 服务

要从 VPS 外部访问 Harbor 的 Web UI，请使用 Harbor 内置的 Cloudflare Tunnel：

```bash
# 为 Open WebUI 配置隧道
harbor tunnels add webui
```

这会启动 `cloudflared` 作为 sidecar 容器，并生成一个 `*.trycloudflare.com` 的 URL。生产环境建议：

1. 设置 Cloudflare 域名并添加 CNAME 记录
2. 用你的隧道令牌配置 `cloudflared`
3. 确保认证已启用（Open WebUI 默认需要登录）

> ⚠️ **安全警告**：切勿在没有认证的情况下将 Open WebUI 暴露到互联网。Harbor 默认要求登录，但请务必检查配置。

---

## 第六步：切换推理后端

Harbor 支持多种 LLM 推理后端，以下是选择指南：

| 后端 | 最适合 | 需要 GPU | 速度 |
|---|---|---|---|
| **Ollama** | 通用，模型管理简单 | 可选 | 良好 |
| **llama.cpp** | CPU 推理，GGUF 格式 | 不需要 | CPU 上表现佳 |
| **vLLM** | 生产环境高吞吐 API 服务 | 需要 | 优秀 |
| **TabbyAPI** | ExLlamaV2，超长上下文 | 需要 | 很快 |
| **SGLang** | 结构化输出，视觉语言模型 | 需要 | 优秀 |

示例：切换到 vLLM 用于生产环境 API 服务：

```bash
# 停止当前栈，用 vLLM 重启
harbor down
harbor up vllm
# vLLM API 现在位于 localhost:8000，兼容 OpenAI 接口
```

你甚至可以同时运行**多个后端**——Harbor 会将它们全部连接到 Open WebUI。

---

## Harbor 命令速查

```bash
harbor up                    # 启动默认栈（Ollama + Open WebUI）
harbor up searxng speaches  # 添加服务
harbor up --no-defaults vllm # 仅启动 vLLM（跳过默认服务）
harbor down                  # 停止所有服务
harbor open                  # 在浏览器中打开 Web UI
harbor logs webui            # 查看特定服务的日志
harbor ps                    # 查看运行中的服务
harbor doctor                # 系统兼容性检查
harbor update                # 更新 Harbor CLI
harbor config set ui.autoopen true  # 自动打开浏览器
harbor ollama pull qwen2.5:7b       # 通过 Ollama 拉取模型
harbor tunnels add webui            # 通过 Cloudflare 暴露服务
```

---

## 模型资源估算

| 模型 | 大小 | RAM/显存 | CPU 推理速度 | GPU 推理速度 |
|---|---|---|---|---|
| Phi-4-mini (3.8B) Q4 | 2.5 GB | 4 GB | 15–25 tok/s | 80–120 tok/s |
| Qwen2.5-7B Q4 | 4.5 GB | 6 GB | 5–10 tok/s | 40–60 tok/s |
| Llama 3.1-8B Q4 | 5 GB | 8 GB | 4–8 tok/s | 35–55 tok/s |
| DeepSeek-R1-Distill-7B Q4 | 5 GB | 8 GB | 4–7 tok/s | 30–50 tok/s |
| Qwen2.5-14B Q4 | 9 GB | 14 GB | 2–4 tok/s | 20–35 tok/s |
| Mistral-Small-24B Q4 | 14 GB | 20 GB | 1–2 tok/s | 12–20 tok/s |

---

## 实际 VPS 配置推荐

**入门配置（$10–20/月）：**
- 2 vCPU，8 GB 内存，无 GPU
- CPU 运行 Phi-4-mini 或 Qwen2.5:7B（通过 Ollama）
- Harbor + Open WebUI + SearXNG（Web RAG）
- ~5–10 tokens/秒——日常聊天够用

**中配（$30–50/月）：**
- 4 vCPU，16 GB 内存，NVIDIA T4（16 GB 显存）
- vLLM 运行 Llama 3.1-8B 或 Qwen2.5-14B
- 添加 Speaches 语音交互、ComfyUI 图像生成
- ~40–60 tokens/秒——生产可用

**高配（$100–150/月）：**
- 8 vCPU，32 GB 内存，NVIDIA L40S（48 GB 显存）
- 运行 Mistral-Small-24B 或 Qwen2.5-32B
- 全栈：vLLM + Open WebUI + Dify + ComfyUI + SearXNG
- ~60+ tokens/秒——团队使用

---

## 总结

Harbor 消除了自托管 AI 最困难的配置环节。一条命令就能在 VPS 上获得完整的、可投入生产使用的大模型技术栈。50+ 可用服务意味着你可以从简单的聊天界面逐步扩展到完整的 AI 平台（RAG、语音、图像、工作流）。

AI 自托管生态已经成熟到搭建你自己的 ChatGPT 只需几分钟而非几天的程度。Harbor 就是让这成为可能的工具。

**下一步：**
- 浏览所有 50+ 服务：`harbor ls`
- 加入 [Harbor Discord](https://discord.gg/8nDRphrhSF) 社区
- 尝试在 Vast.ai、RunPod 或 TensorDock 等有 GPU 的 VPS 上部署
