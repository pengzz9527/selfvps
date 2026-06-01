---
title: "在 VPS 上运行 DeepSeek V4：开源大模型的本地化部署指南"
description: "从模型量化到 API 搭建，手把手教你在 VPS 上私有化运行 DeepSeek V4——数据不出服务器，按需调用，成本仅为云 API 的零头。覆盖 Ollama、vLLM、llama.cpp 三种部署方案。"
date: 2026-06-01T21:30:00+08:00
slug: "deploy-deepseek-v4-vps"
tags: ["DeepSeek", "LLM", "VPS部署", "Ollama", "vLLM", "开源AI", "私有部署", "API"]
categories: ["AI部署"]
image: /images/posts/deploy-deepseek-v4-vps/featured.png
draft: false
---

2026 年的大语言模型赛道，DeepSeek V4 是一匹无法忽视的黑马。它不仅在多项基准测试中追平甚至超越了 GPT-4o 和 Claude 4，更关键的是——**它是开源的**。

这意味着你可以把它部署在自己的 VPS 上，所有数据留在本地，按需调用，不必为每百万 Token 付费，也不用担心 API 供应商半夜调整定价。

本文会带你走完从选型到上线的完整流程：VPS 配置推荐、模型量化选型、三种部署方案对比（Ollama / vLLM / llama.cpp）、API 封装和前端集成。

## 为什么在 VPS 上跑 DeepSeek V4？

先算一笔账。

| 方案 | 成本 | 数据隐私 | 可用性 |
|------|------|----------|--------|
| ChatGPT / Claude API | $20-200/月 + 按量计费 | ❌ 数据经第三方 | ✅ 高 |
| DeepSeek 官方 API | 按量计费（约 $0.5/百万 Token） | ⚠️ 数据经第三方 | ✅ 高 |
| **VPS 自部署 DeepSeek V4** | **$5-30/月（固定成本）** | ✅ **完全私有** | ✅ 24/7 |

自部署的核心理念是：**固定成本换无限调用**。无论你的 AI 助手一天处理 100 条请求还是 10000 条请求，VPS 账单不变。

更重要的是数据隐私——当你在本地运行模型时，没有任何代码、文档或对话会离开你的服务器。这对处理敏感数据的开发者、创业团队和企业来说意义重大。

## DeepSeek V4 模型简介

DeepSeek V4 是 DeepSeek 于 2026 年初发布的新一代大语言模型，主要特点包括：

- **MoE 架构**：混合专家模型（Mixture of Experts），总参数约 600B，但每次推理只激活约 37B 参数
- **超长上下文**：原生支持 128K tokens，可通过扩展达到 1M tokens
- **多模态能力**：支持文本、代码、图像理解
- **量化友好**：INT4 / INT8 量化后可在消费级 GPU 上运行
- **开源协议**：MIT 许可证，可自由商用

对于 VPS 部署，我们主要关注量化版本：

| 量化级别 | 显存需求 | 推理速度 | 质量损失 |
|----------|----------|----------|----------|
| FP16 (完整) | ~120GB | 最快 | 无 |
| INT8 | ~60GB | 快 | 极小 |
| INT4 | ~30GB | 中等 | 可接受 |
| Q2_K (llama.cpp) | ~16GB | 较慢 | 轻度损失 |
| IQ1_S (极致量化) | ~8GB | 慢 | 明显损失 |

对于大多数 VPS 场景，**INT4 量化版本**是最优平衡点——单卡 24GB 显存即可运行，推理速度可观，质量损失几乎不可感知。

## VPS 规格推荐

要流畅运行 DeepSeek V4 的量化版本，以下是不同预算的配置建议：

### 最低配置（体验级）
- **GPU**：NVIDIA RTX 3090 / 4090（24GB VRAM）
- **CPU**：4 核+
- **RAM**：16GB+
- **存储**：50GB+ SSD
- **适合**：个人使用，Q4_K_M 量化，推理速度 ~5-8 tokens/s
- **月费**：约 $20-30（Hetzner / Netcup 拍卖机）

### 推荐配置（生产级）
- **GPU**：NVIDIA RTX 4090 × 2 或 A6000（48GB）
- **CPU**：8 核+
- **RAM**：32GB+
- **存储**：100GB+ NVMe
- **适合**：小团队使用，INT4 量化，推理速度 ~15-20 tokens/s
- **月费**：约 $60-100

### 无 GPU 方案（纯 CPU 推理）
- **CPU**：16 核+（AMD EPYC 或 Intel Xeon）
- **RAM**：64GB+
- **存储**：50GB+ SSD
- **适合**：非实时场景，Q2_K 量化，推理速度 ~1-3 tokens/s
- **月费**：约 $15-30

{{< figure src="/images/posts/deploy-deepseek-v4-vps/deepseek-architecture.png" alt="DeepSeek V4 部署架构图" caption="DeepSeek V4 在 VPS 上的完整部署架构" width="800" >}}

## 方案一：使用 Ollama 部署（最简单）

[Ollama](https://ollama.com) 是目前最友好的本地大模型运行工具，一条命令即可拉起 DeepSeek V4。

### 安装 Ollama

```bash
# 一键安装
curl -fsSL https://ollama.com/install.sh | sh

# 验证安装
ollama --version
```

### 下载并运行 DeepSeek V4 量化版

```bash
# 拉取 INT4 量化版（推荐，约 18GB）
ollama pull deepseek-v4:14b-int4

# 拉取更小的 Q4_K_M 版（适合 24GB 显存）
ollama pull deepseek-v4:q4_k_m

# 运行模型
ollama run deepseek-v4:q4_k_m
```

首次拉取可能需要 10-30 分钟（取决于网速）。模型下载后，后续启动只需几秒。

### 配置 Ollama 允许远程访问

默认情况下 Ollama 只监听本地。要让其他设备或应用访问，需要修改配置：

```bash
# 编辑 systemd 服务配置
sudo systemctl edit ollama.service
```

添加以下内容：

```ini
[Service]
Environment="OLLAMA_HOST=0.0.0.0"
Environment="OLLAMA_ORIGINS=*"
```

重启服务：

```bash
sudo systemctl daemon-reload
sudo systemctl restart ollama
```

现在可以通过 `http://你的VPS_IP:11434` 访问 API。

### 测试 API

```bash
curl http://localhost:11434/api/generate -d '{
  "model": "deepseek-v4:q4_k_m",
  "prompt": "用 Python 写一个快速排序",
  "stream": false
}'
```

## 方案二：使用 vLLM 部署（高吞吐）

[vLLM](https://github.com/vllm-project/vllm) 专为生产环境设计，通过 PagedAttention 和连续批处理实现高吞吐推理。适合需要同时服务多个用户的场景。

### 安装 vLLM

```bash
# 推荐使用 Python 虚拟环境
python3 -m venv vllm-env
source vllm-env/bin/activate

# 安装 vLLM（CUDA 12.1+）
pip install vllm
```

### 启动 DeepSeek V4 服务

```bash
python -m vllm.entrypoints.openai.api_server \
  --model deepseek-ai/DeepSeek-V4 \
  --dtype float16 \
  --max-model-len 32768 \
  --gpu-memory-utilization 0.90 \
  --tensor-parallel-size 1 \
  --port 8000
```

参数说明：
- `--dtype float16`：使用半精度推理
- `--max-model-len 32768`：最长 32K tokens 上下文
- `--gpu-memory-utilization 0.90`：GPU 显存利用率 90%
- `--tensor-parallel-size`：多 GPU 时设置并行度

### vLLM vs Ollama 对比

| 特性 | Ollama | vLLM |
|------|--------|------|
| 安装难度 | ⭐ 极简 | ⭐⭐⭐ 需要 Python 环境 |
| 推理吞吐 | 中等 | 高（连续批处理） |
| 并发支持 | 有限 | 优秀 |
| API 兼容 | Ollama 原生 API | OpenAI 兼容 API |
| 显存效率 | 好 | 更好（PagedAttention） |
| 适用场景 | 个人使用 / 开发测试 | 生产环境 / 多用户 |

## 方案三：使用 llama.cpp 部署（CPU + GPU 混合）

[llama.cpp](https://github.com/ggerganov/llama.cpp) 的优势在于对硬件的极致适配——可以在无 GPU 的纯 CPU 机器上运行，也可以 CPU + GPU 混合推理。

### 编译安装

```bash
git clone https://github.com/ggerganov/llama.cpp
cd llama.cpp

# GPU 加速编译（需要 CUDA）
cmake -B build -DGGML_CUDA=ON
cmake --build build --config Release -j$(nproc)

# 纯 CPU 编译
# cmake -B build
# cmake --build build --config Release -j$(nproc)
```

### 下载量化模型

```bash
# 下载 GGUF 格式的量化模型
# 使用 huggingface-cli 或直接 wget
pip install huggingface-hub
huggingface-cli download \
  unsloth/DeepSeek-V4-GGUF \
  deepseek-v4-q4_k_m.gguf \
  --local-dir ./models/
```

### 启动服务器

```bash
./build/bin/server \
  -m ./models/deepseek-v4-q4_k_m.gguf \
  --host 0.0.0.0 \
  --port 8080 \
  --n-gpu-layers 35  # 将 35 层卸载到 GPU，其余 CPU 处理
  --ctx-size 32768
```

llama.cpp 的 `--n-gpu-layers` 参数非常灵活——显存不足时可以减少 GPU 层数，让 CPU 分担部分计算。

## 前端集成：Open WebUI

有了后端 API，还需要一个好用的前端。Open WebUI（前身 Ollama WebUI）是目前最流行的选择。

### 用 Docker 部署

```bash
docker run -d \
  --name open-webui \
  -p 3000:8080 \
  -v open-webui-data:/app/backend/data \
  -e OLLAMA_BASE_URL=http://你的VPS_IP:11434 \
  --restart always \
  ghcr.io/open-webui/open-webui:main
```

访问 `http://你的VPS_IP:3000` 即可打开聊天界面。Open WebUI 支持：

- 多模型切换
- 对话历史管理
- RAG（检索增强生成）
- Markdown / 代码高亮
- 用户管理和 API Key 管理

### 用 Docker Compose 整合部署

```yaml
version: '3.8'
services:
  ollama:
    image: ollama/ollama:latest
    volumes:
      - ./ollama-data:/root/.ollama
    ports:
      - "11434:11434"
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
    restart: always

  open-webui:
    image: ghcr.io/open-webui/open-webui:main
    volumes:
      - ./webui-data:/app/backend/data
    ports:
      - "3000:8080"
    environment:
      - OLLAMA_BASE_URL=http://ollama:11434
    depends_on:
      - ollama
    restart: always

  nginx:
    image: nginx:alpine
    ports:
      - "443:443"
      - "80:80"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ./ssl:/etc/nginx/ssl
    depends_on:
      - open-webui
    restart: always
```

## API 调用示例

部署完成后，你可以用标准的 HTTP 请求调用模型。以下用 Python 演示：

```python
import requests
import json

# Ollama API
def query_ollama(prompt, model="deepseek-v4:q4_k_m"):
    response = requests.post(
        "http://localhost:11434/api/generate",
        json={"model": model, "prompt": prompt, "stream": False}
    )
    return response.json()["response"]

# vLLM (OpenAI 兼容 API)
def query_vllm(prompt, model="deepseek-ai/DeepSeek-V4"):
    from openai import OpenAI
    client = OpenAI(
        base_url="http://localhost:8000/v1",
        api_key="not-needed"  # vLLM 默认不校验 API Key
    )
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=4096
    )
    return response.choices[0].message.content

# 使用示例
print(query_ollama("解释一下 MoE 架构的工作原理"))
```

## 性能优化技巧

### 1. 模型量化选择

| 量化格式 | 推荐场景 |
|----------|----------|
| Q4_K_M | 通用推荐，质量损失极小 |
| Q5_K_M | 质量优先，需要更多显存 |
| Q2_K | 低配置机器（8-12GB 显存） |
| IQ4_NL | 最新量化格式，效率更高 |

### 2. 上下文长度管理

- 不需要长上下文时，限制 `max_model_len` 或 `ctx-size` 为 8192
- 这样能显著减少显存占用和首 Token 延迟

### 3. 批处理优化（vLLM）

```bash
# 启用连续批处理，提高吞吐
--max-num-batched-tokens 8192 \
--max-num-seqs 8
```

### 4. 系统级优化

```bash
# 设置 GPU 为性能模式
sudo nvidia-smi -pm 1
sudo nvidia-smi -pl 250  # 限制功耗，降低温度

# 禁用交换分区（避免模型被换出）
sudo swapoff -a

# 设置大页内存
echo 1024 | sudo tee /proc/sys/vm/nr_hugepages
```

### 5. 使用模型缓存

Ollama 和 vLLM 都会在首次加载后缓存模型。确保部署脚本在系统启动时预热模型：

```bash
# systemd 服务示例：开机自动加载模型
[Service]
ExecStartPre=/usr/bin/ollama pull deepseek-v4:q4_k_m
ExecStart=/usr/bin/ollama serve
```

## 成本对比：自部署 vs API

假设你每天调用模型处理 100 万 Token：

| 方案 | 月费 | 每日 100 万 Token | 年费 |
|------|------|-------------------|------|
| GPT-4o API | $20 + $10/M Tok * 30 | $320 | $3,840 |
| Claude 4 API | $20 + $15/M Tok * 30 | $470 | $5,640 |
| DeepSeek 官方 API | $0.5/M Tok * 30 | ~$15 | $180 |
| **VPS 自部署** | **$30（VPS）+ $0（推理）** | **$30** | **$360** |

自部署在年调用量超过 200 万 Token 时就开始回本。用得越多，省得越多。

## 总结

在 VPS 上部署 DeepSeek V4，是在**成本、隐私、可控性**三者之间取得的最佳平衡。

- **个人用户**：推荐 Ollama + Open WebUI，半小时内搞定
- **小团队**：推荐 vLLM + Open WebUI，享受高并发能力
- **低配机器**：推荐 llama.cpp，充分利用 CPU + GPU 混合推理

核心要点回顾：

1. **INT4 / Q4_K_M 量化**是 VPS 部署的最佳选择，质量损失极小
2. **Ollama** 是最快入门方式，适合个人使用
3. **vLLM** 提供生产级吞吐，适合多用户场景
4. **llama.cpp** 对硬件容忍度最高，无 GPU 也能跑
5. 配合 **Open WebUI** 获得媲美 ChatGPT 的使用体验
6. 自部署的**长期成本远低于 API 调用**

开源大模型的本地部署不是未来——它已经来了。你的 VPS 现在就能跑起来。
