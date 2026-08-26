---
title: "在 VPS 上部署 Ollama：本地运行 Llama / Codestral / Qwen 等开源大模型完全指南"
date: 2026-08-26
description: "不用昂贵的 API 订阅，在你的 VPS 上部署 Ollama，本地运行 Llama 3.2、Codestral、Qwen 等主流开源大模型。本文涵盖安装配置、GPU 加速、API 兼容、多模型切换、前端界面部署等完整流程。"
tags: ["VPS", "Ollama", "大模型", "LLM", "AI", "自托管", "Llama", "Qwen", "Codestral"]
categories: ["AI 运维"]
image: "/images/posts/vps-ollama-local-llm-deployment/featured-zh.png"
draft: false
---

## 引言

大语言模型正在改变我们工作和使用软件的方式。但每调用一次 AI 模型，你都要为 API 付费——ChatGPT、Claude、GPT-4o 的调用费用虽然单次不高，但高频使用下账单会让你心疼。

有没有可能**在自己服务器上运行大模型**？答案是：**完全可以**。

**Ollama** 是目前最简单、最流行的本地大模型运行框架。它支持 Llama 3.2、Codestral、Qwen、DeepSeek 等数十个开源模型，一条命令就能启动，并且提供与 OpenAI API 完全兼容的接口——这意味着你可以直接用现有的 AI 客户端连接你的本地模型。

本文将带你从零开始在 VPS 上部署 Ollama，包括 CPU 和 GPU 加速方案、模型管理、API 调用、以及配套前端界面的搭建。

---

## 为什么在 VPS 上跑 Ollama？

| 方案 | 成本 | 速度 | 隐私 | 灵活性 |
|------|------|------|------|--------|
| 云端 API（ChatGPT/Claude） | 高（按 Token 计费） | 快 | 低（数据上传） | 中等 |
| 本地电脑跑 Ollama | 零 | 取决于硬件 | 高 | 低（受限于本地硬件） |
| **VPS 上跑 Ollama** | **低（固定月费）** | **中等偏快** | **高** | **高（7x24 在线）** |

VPS 方案的优势：
- **固定成本**：每月 20-50 美元的 VPS 可以 7x24 运行，比按量付费便宜得多
- **全天候在线**：模型常驻内存，随时调用，无需等待
- **数据隐私**：所有请求都在你自己的服务器上处理
- **多用户共享**：团队内多人都能使用，无需各自订阅
- **API 兼容**：OpenAI 兼容接口，无缝替换第三方服务

---

## 环境准备

### 硬件要求

不同模型对资源的需求差异很大：

| 模型 | 最小内存 | 推荐内存 | GPU 需求 |
|------|---------|---------|---------|
| Llama 3.2 1B/3B | 2 GB | 4 GB | 无 |
| Llama 3.2 11B/8B | 8 GB | 12 GB | 推荐 |
| Llama 3.1 8B | 8 GB | 16 GB | 推荐 |
| Qwen 2.5 14B | 16 GB | 24 GB | 推荐 |
| DeepSeek R1 7B | 8 GB | 12 GB | 推荐 |
| DeepSeek R1 32B | 32 GB | 48 GB | 需要 |

**推荐 VPS 配置**：
- 入门级：2 vCPU / 8 GB RAM / 50 GB SSD（跑 7B-8B 模型）
- 进阶级：4 vCPU / 16-24 GB RAM（跑 14B-32B 模型）
- GPU 版：NVIDIA T4 / L4 实例（推荐跑大模型加速推理）

### 系统要求

- Linux（Ubuntu 20.04+ / Debian 11+ / AlmaLinux 9）
- Docker（推荐，隔离性好）
- 或 Python 3.8+（原生安装）

---

## 方法一：Docker 部署 Ollama（推荐）

Docker 方式安装最简单，版本管理方便，且易于备份和迁移。

### 1. 安装 Docker

```bash
# Ubuntu / Debian
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker

# 验证安装
docker --version
```

### 2. 启动 Ollama 容器

```bash
docker run -d \
  --name ollama \
  -v ollama-data:/root/.ollama \
  -p 11434:11434 \
  --restart unless-stopped \
  ollama/ollama:latest
```

**参数说明**：
- `-v ollama-data:/root/.ollama`：持久化模型数据，避免删除容器后丢失
- `-p 11434:11434`：暴露 Ollama API 端口
- `--restart unless-stopped`：VPS 重启后自动恢复

### 3. 验证安装

```bash
# 检查容器状态
docker ps | grep ollama

# 测试 API 是否响应
curl http://localhost:11434/api/version
```

---

## 方法二：原生安装 Ollama

如果你不需要 Docker，可以直接安装：

```bash
# 一键安装脚本
curl -fsSL https://ollama.com/install.sh | sh

# 启动服务
systemctl start ollama
systemctl enable ollama  # 开机自启

# 验证
ollama --version
```

---

## 拉取和运行模型

Ollama 的模型管理极其简单，一条命令即可完成：

### 常用模型

```bash
# Meta Llama 3.2（最流行的开源模型）
ollama pull llama3.2

# Mistral（欧洲开源模型，性能优秀）
ollama pull mistral

# Qwen 2.5（阿里通义千问，中文能力强）
ollama pull qwen2.5

# DeepSeek R1（国产推理模型，免费开源）
ollama pull deepseek-r1:7b

# Codestral（Mistral 的代码专用模型）
ollama pull codestral

# Gemma 2（Google 开源模型）
ollama pull gemma2
```

### 模型大小对照

Ollama 自动下载对应量化版本，常见模型规格：

| 模型 | 默认量化 | 参数量 | 内存占用 |
|------|---------|--------|---------|
| llama3.2 | Q4_K_M | 3B | ~2 GB |
| llama3.1 | Q4_K_M | 8B | ~5 GB |
| qwen2.5 | Q4_K_M | 7B | ~4.5 GB |
| deepseek-r1 | Q4_K_M | 7B | ~4.5 GB |
| codestral | Q4_K_M | 22B | ~14 GB |

### 切换模型大小

```bash
# 拉取更大参数版本（需要更多内存）
ollama pull llama3.2:latest    # 3B
ollama pull llama3.1:8b        # 8B
ollama pull qwen2.5:14b        # 14B

# 拉取更小量化版本（节省内存）
ollama pull llama3.2:1b        # 1B（极简版）
ollama pull llama3.2:0.5b      # 0.5B（手机级别）
```

---

## 测试模型

### 命令行交互

```bash
# 直接对话
ollama run llama3.2

# 指定模型
ollama run qwen2.5 "用 Python 写一个快速排序算法"
```

### API 调用

Ollama 提供完整的 OpenAI 兼容 API：

```bash
# 查看 API 端点
curl http://localhost:11434/api/tags

# 流式聊天（Streaming）
curl http://localhost:11434/api/chat -d '{
  "model": "llama3.2",
  "messages": [{"role": "user", "content": "你好，介绍一下你自己"}],
  "stream": true
}'

# 非流式调用
curl http://localhost:11434/api/generate -d '{
  "model": "qwen2.5",
  "prompt": "Python 中如何实现多线程？",
  "stream": false
}'
```

### 用 Python 调用

```python
from openai import OpenAI

# 指向本地 Ollama
client = OpenAI(
    base_url="http://your-vps-ip:11434/v1/",
    api_key="not-needed"  # Ollama 不需要 API Key
)

response = client.chat.completions.create(
    model="llama3.2",
    messages=[
        {"role": "system", "content": "你是一个专业的程序员助手"},
        {"role": "user", "content": "用 FastAPI 写一个 REST API"}
    ],
    stream=True
)

for chunk in response:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="")
```

---

## GPU 加速部署

纯 CPU 推理对于 7B+ 模型来说速度较慢（通常 3-10 tokens/s）。如果你使用支持 GPU 的 VPS，可以获得质的飞跃。

### NVIDIA GPU 支持

```bash
# 检查 GPU 是否可用
nvidia-smi

# 使用 GPU 版 Ollama（NVIDIA CUDA）
docker run -d \
  --name ollama \
  --gpus all \
  -v ollama-data:/root/.ollama \
  -p 11434:11434 \
  --restart unless-stopped \
  ollama/ollama:latest-gpu
```

### 常用 GPU VPS 提供商

| 提供商 | GPU 型号 | 价格（月） | 适合模型 |
|--------|---------|-----------|---------|
| Lambda Cloud | A100 80GB | $2-3/小时 | 所有模型 |
| Vast.ai | RTX 4090 / A100 | $0.2-0.5/小时 | 按需使用 |
| RunPod | RTX 4090 / A6000 | $0.3-0.6/小时 | 按需使用 |
| 阿里云 PAI | A10 / A100 | ¥1-3/小时 | 按需使用 |
| 腾讯云 Lighthouse | T4 | ¥2-4/小时 | 7B-14B 模型 |

### 验证 GPU 加速

```bash
# 查看 Ollama 是否使用 GPU
ollama ps

# 输出示例：
# NAME            ID              SIZE      PROCESSOR           UNTIL
# llama3.2:latest  abc123...      2.0 GB    CUDA:0 (NVIDIA ...)  Now
```

---

## 多模型管理与切换

### 列出所有模型

```bash
ollama list
# 或
curl http://localhost:11434/api/tags
```

### 删除不需要的模型

```bash
ollama rm llama3.1        # 删除特定模型
ollama rm llama3.2:3b     # 删除特定版本
```

### 修改模型参数

编辑 Modelfile 来自定义模型行为：

```modelfile
FROM llama3.2
PARAMETER temperature 0.7
PARAMETER num_ctx 4096
PARAMETER num_predict 2048
SYSTEM "你是一个专业程序员，只回答技术相关问题"
```

```bash
# 构建自定义模型
ollama create my-llama -f ./Modelfile

# 运行自定义模型
ollama run my-llama "你好"
```

---

## 搭建 Ollama 前端界面

### 方案一：Open WebUI（推荐）

Open WebUI 是最流行的开源 Ollama 前端，功能媲美 ChatGPT Web 界面。

```bash
docker run -d \
  --name open-webui \
  -v open-webui:/app/backend/data \
  -p 8080:8080 \
  --restart unless-stopped \
  ghcr.io/open-webui/open-webui:main
```

访问 `http://your-vps-ip:8080`，在设置中将 API 端点改为 `http://localhost:11434`。

### 方案二：文本生成 WebUI

```bash
docker run -d \
  --name textgen \
  -p 7860:7860 \
  -v textgen-data:/data \
  --restart unless-stopped \
  ghcr.io/oobabooga/text-generation-webui:latest
```

### 方案三：Dify 集成

如果你已经有 Dify 平台，可以直接在 Dify 中配置 Ollama 作为模型提供方：

1. 进入 Dify → 工作空间设置 → 模型提供者
2. 选择 "Ollama"
3. 填入 `http://your-vps-ip:11434`
4. 选择模型名称

---

## 生产环境配置

### 配置反向代理（Nginx + HTTPS）

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

        # WebSocket 支持（Open WebUI 需要）
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }
}
```

### 配置防火墙

```bash
# 仅开放必要端口
sudo ufw allow 11434/tcp   # Ollama API
sudo ufw allow 8080/tcp    # Open WebUI（可选）
sudo ufw allow 443/tcp     # HTTPS
sudo ufw enable
```

### 监控资源使用

```bash
# 实时监控
htop

# 查看 Ollama 进程
ollama ps

# 查看 Docker 资源使用
docker stats ollama

# 内存和显存
free -h
nvidia-smi  # GPU 用户
```

### 自动备份模型

```bash
# 备份所有模型
tar czf ollama-models-backup-$(date +%Y%m%d).tar.gz \
  -C /root/.ollama .

# 或用 rsync 增量备份
rsync -avz /root/.ollama/ backup-server:/ollama-backup/ollama/
```

---

## 常见问题排查

### 1. 模型加载慢

```bash
# 检查磁盘 I/O
iotop

# 将模型存到 SSD/NVMe
# Docker 卷默认在 /var/lib/docker，确认它在 SSD 上
df -h /var/lib/docker
```

### 2. Out of Memory（OOM）

```bash
# 检查可用内存
free -h

# 减少模型参数量
ollama rm llama3.1:8b
ollama pull llama3.2:3b    # 更小的模型

# 或限制并发请求
# 在 docker run 中加 --memory 和 --cpus 限制
docker run -d --memory="8g" --cpus="2" ...
```

### 3. API 连接超时

```bash
# 检查 Ollama 服务状态
systemctl status ollama
# 或
docker logs ollama

# 检查端口监听
ss -tlnp | grep 11434

# 防火墙
sudo ufw status
```

### 4. GPU 未识别

```bash
# 确认 NVIDIA 驱动
nvidia-smi

# 确认 Docker GPU 支持
docker run --rm --gpus all nvidia/cuda:12.0.0-base-ubuntu22.04 nvidia-smi

# 重启 Ollama 容器
docker restart ollama
```

---

## 成本估算

| VPS 配置 | 月费 | 可运行模型 | 日均 Token 消耗 | 对比云端 API |
|---------|------|-----------|----------------|-------------|
| 2C8G 基础 VPS | $10-15 | 3B-7B 模型 | ~100万 Token | 节省 ~$50/月 |
| 4C16G 进阶 VPS | $30-50 | 7B-14B 模型 | ~500万 Token | 节省 ~$200/月 |
| GPU VPS (T4) | $100-200 | 14B-32B 模型 | ~1000万 Token | 节省 ~$500/月 |

以日均 100 万 Token 的 ChatGPT 4o 调用为例：
- ChatGPT API：约 $50/月（按 $0.005/1K tokens 估算）
- VPS 固定月费：$10-50/月
- **年节省：$500-3000+**

---

## 总结

在 VPS 上部署 Ollama 是平衡成本、性能和隐私的最佳方案之一：

1. **安装简单**：Docker 一条命令启动
2. **模型丰富**：支持 Llama、Qwen、DeepSeek 等数十个开源模型
3. **API 兼容**：OpenAI 格式接口，无缝替换第三方服务
4. **成本可控**：固定月费，高频使用下远优于 API 按量计费
5. **数据安全**：所有请求在自有服务器处理，不泄露数据

**下一步行动建议**：
1. 准备一台 8GB+ 内存的 VPS
2. 执行 `curl -fsSL https://ollama.com/install.sh | sh`
3. `ollama pull llama3.2` 拉取模型
4. 配置反向代理和 HTTPS
5. 部署 Open WebUI 获得完整聊天体验

现在就可以在你的 VPS 上搭建专属的 AI 助手了！
