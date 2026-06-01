---
title: "Running DeepSeek V4 on Your VPS: Complete Local Deployment Guide"
description: "From model quantization to API setup — deploy DeepSeek V4 privately on your own VPS. Covers Ollama, vLLM, and llama.cpp deployment with cost comparison vs cloud APIs."
date: 2026-06-01T21:30:00+08:00
slug: "deploy-deepseek-v4-vps"
tags: ["DeepSeek", "LLM", "VPS deployment", "Ollama", "vLLM", "open-source AI", "self-hosting", "API"]
categories: ["AI Deployment"]
image: /images/posts/deploy-deepseek-v4-vps/featured.png
draft: false
---

In the 2026 LLM landscape, DeepSeek V4 is the dark horse nobody can ignore. It matches or even surpasses GPT-4o and Claude 4 on multiple benchmarks — and crucially, **it's open-source**.

This means you can deploy it on your own VPS. All data stays local, you pay a flat monthly rate instead of per-token fees, and you never have to worry about API providers changing their pricing overnight.

This guide covers the entire deployment journey: VPS specs, model quantization selection, three deployment methods (Ollama / vLLM / llama.cpp), API integration, and frontend setup.

## Why Run DeepSeek V4 on Your Own VPS?

Let's do the math.

| Option | Monthly Cost | Data Privacy | Availability |
|--------|-------------|--------------|--------------|
| ChatGPT / Claude API | $20-200/mo + usage fees | ❌ Data passes through third party | ✅ High |
| DeepSeek Official API | ~$0.50/1M tokens | ⚠️ Data passes through third party | ✅ High |
| **Self-hosted on VPS** | **$5-30/mo (fixed)** | ✅ **100% private** | ✅ 24/7 |

The core philosophy of self-hosting: **fixed cost for unlimited usage**. Whether your AI assistant handles 100 requests or 10,000 requests per day, your VPS bill stays the same.

More importantly: data privacy. When you run the model locally, no code, document, or conversation ever leaves your server. This is critical for developers, startups, and enterprises handling sensitive data.

## DeepSeek V4 Model Overview

DeepSeek V4 is the next-generation LLM released by DeepSeek in early 2026:

- **MoE Architecture**: Mixture of Experts — ~600B total parameters, but only ~37B activated per inference
- **Ultra-long Context**: Native 128K tokens, extendable to 1M tokens
- **Multimodal**: Supports text, code, and image understanding
- **Quantization-friendly**: INT4/INT8 quantized versions run on consumer GPUs
- **License**: MIT — free for commercial use

For VPS deployment, we focus on quantized versions:

| Quantization | VRAM Required | Speed | Quality Loss |
|-------------|---------------|-------|--------------|
| FP16 (full) | ~120GB | Fastest | None |
| INT8 | ~60GB | Fast | Minimal |
| INT4 | ~30GB | Medium | Acceptable |
| Q2_K (llama.cpp) | ~16GB | Slow | Mild |
| IQ1_S (extreme) | ~8GB | Very slow | Noticeable |

For most VPS scenarios, **INT4 quantization** hits the sweet spot — runs on a single 24GB GPU, decent inference speed, and quality loss that's nearly imperceptible.

## Recommended VPS Specs

### Minimum (Personal Use)
- **GPU**: NVIDIA RTX 3090 / 4090 (24GB VRAM)
- **CPU**: 4+ cores
- **RAM**: 16GB+
- **Storage**: 50GB+ SSD
- **Performance**: Q4_K_M quant, ~5-8 tokens/s
- **Cost**: ~$20-30/mo (Hetzner / Netcup auction)

### Recommended (Production)
- **GPU**: Dual RTX 4090 or A6000 (48GB)
- **CPU**: 8+ cores
- **RAM**: 32GB+
- **Storage**: 100GB+ NVMe
- **Performance**: INT4 quant, ~15-20 tokens/s
- **Cost**: ~$60-100/mo

### CPU-Only (Budget)
- **CPU**: 16+ cores (AMD EPYC or Intel Xeon)
- **RAM**: 64GB+
- **Storage**: 50GB+ SSD
- **Performance**: Q2_K quant, ~1-3 tokens/s
- **Cost**: ~$15-30/mo

{{< figure src="/images/posts/deploy-deepseek-v4-vps/deepseek-architecture.png" alt="DeepSeek V4 Deployment Architecture" caption="Complete DeepSeek V4 deployment architecture on VPS" width="800" >}}

## Option 1: Deploy with Ollama (Simplest)

[Ollama](https://ollama.com) is the friendliest tool for running local LLMs. One command is all it takes to get DeepSeek V4 running.

### Install Ollama

```bash
# One-click install
curl -fsSL https://ollama.com/install.sh | sh

# Verify installation
ollama --version
```

### Download and Run DeepSeek V4

```bash
# Pull INT4 quantized version (recommended, ~18GB)
ollama pull deepseek-v4:14b-int4

# Pull Q4_K_M version (fits 24GB VRAM)
ollama pull deepseek-v4:q4_k_m

# Run the model
ollama run deepseek-v4:q4_k_m
```

First pull may take 10-30 minutes depending on your connection speed. Subsequent starts take only seconds.

### Enable Remote Access

By default, Ollama only listens on localhost. To access it from other devices:

```bash
# Edit systemd service
sudo systemctl edit ollama.service
```

Add:

```ini
[Service]
Environment="OLLAMA_HOST=0.0.0.0"
Environment="OLLAMA_ORIGINS=*"
```

Restart:

```bash
sudo systemctl daemon-reload
sudo systemctl restart ollama
```

Access at `http://your-vps-ip:11434`.

### Test the API

```bash
curl http://localhost:11434/api/generate -d '{
  "model": "deepseek-v4:q4_k_m",
  "prompt": "Write a quick sort in Python",
  "stream": false
}'
```

## Option 2: Deploy with vLLM (High Throughput)

[vLLM](https://github.com/vllm-project/vllm) is designed for production environments. Its PagedAttention and continuous batching deliver high-throughput inference — ideal for multi-user scenarios.

### Install vLLM

```bash
# Use a Python virtual environment
python3 -m venv vllm-env
source vllm-env/bin/activate

# Install vLLM (CUDA 12.1+)
pip install vllm
```

### Start DeepSeek V4 API Server

```bash
python -m vllm.entrypoints.openai.api_server \
  --model deepseek-ai/DeepSeek-V4 \
  --dtype float16 \
  --max-model-len 32768 \
  --gpu-memory-utilization 0.90 \
  --tensor-parallel-size 1 \
  --port 8000
```

### vLLM vs Ollama

| Feature | Ollama | vLLM |
|---------|--------|------|
| Installation Complexity | ⭐ Minimal | ⭐⭐⭐ Python environment needed |
| Inference Throughput | Medium | High (continuous batching) |
| Concurrency | Limited | Excellent |
| API Compatibility | Ollama native | OpenAI-compatible |
| Memory Efficiency | Good | Better (PagedAttention) |
| Best For | Personal / Dev | Production / Multi-user |

## Option 3: Deploy with llama.cpp (CPU + GPU Hybrid)

[llama.cpp](https://github.com/ggerganov/llama.cpp) shines at hardware adaptability — it runs on pure CPU machines, GPU machines, or anything in between.

### Build from Source

```bash
git clone https://github.com/ggerganov/llama.cpp
cd llama.cpp

# GPU-accelerated build (with CUDA)
cmake -B build -DGGML_CUDA=ON
cmake --build build --config Release -j$(nproc)
```

### Download Quantized Model

```bash
pip install huggingface-hub
huggingface-cli download \
  unsloth/DeepSeek-V4-GGUF \
  deepseek-v4-q4_k_m.gguf \
  --local-dir ./models/
```

### Start Server

```bash
./build/bin/server \
  -m ./models/deepseek-v4-q4_k_m.gguf \
  --host 0.0.0.0 \
  --port 8080 \
  --n-gpu-layers 35 \
  --ctx-size 32768
```

The `--n-gpu-layers` parameter is flexible — reduce it if VRAM is tight, and the CPU handles the remaining layers.

## Frontend Integration: Open WebUI

[Open WebUI](https://github.com/open-webui/open-webui) (formerly Ollama WebUI) is the most popular frontend choice.

### Docker Deployment

```bash
docker run -d \
  --name open-webui \
  -p 3000:8080 \
  -v open-webui-data:/app/backend/data \
  -e OLLAMA_BASE_URL=http://your-vps-ip:11434 \
  --restart always \
  ghcr.io/open-webui/open-webui:main
```

Access `http://your-vps-ip:3000` for the chat interface.

### Docker Compose (Full Stack)

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

## API Usage Examples

Once deployed, you can call the model with standard HTTP requests:

```python
import requests

# Ollama API
def query_ollama(prompt, model="deepseek-v4:q4_k_m"):
    response = requests.post(
        "http://localhost:11434/api/generate",
        json={"model": model, "prompt": prompt, "stream": False}
    )
    return response.json()["response"]

# vLLM (OpenAI-compatible API)
def query_vllm(prompt, model="deepseek-ai/DeepSeek-V4"):
    from openai import OpenAI
    client = OpenAI(
        base_url="http://localhost:8000/v1",
        api_key="not-needed"
    )
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=4096
    )
    return response.choices[0].message.content

print(query_ollama("Explain how MoE architecture works"))
```

## Performance Optimization Tips

### 1. Choose the Right Quantization

| Format | Use Case |
|--------|----------|
| Q4_K_M | General recommendation, minimal quality loss |
| Q5_K_M | Quality-first, needs more VRAM |
| Q2_K | Low-end machines (8-12GB VRAM) |
| IQ4_NL | Newer format, better efficiency |

### 2. Manage Context Length

Limit `max_model_len` or `ctx-size` to 8192 when you don't need long context — significantly reduces VRAM usage and first-token latency.

### 3. Batch Processing (vLLM)

```bash
--max-num-batched-tokens 8192 \
--max-num-seqs 8
```

### 4. System-Level Tuning

```bash
# Set GPU to performance mode
sudo nvidia-smi -pm 1
sudo nvidia-smi -pl 250  # Limit power draw

# Disable swap
sudo swapoff -a

# Enable huge pages
echo 1024 | sudo tee /proc/sys/vm/nr_hugepages
```

### 5. Pre-warm Models

Ensure your deployment script pre-loads the model on boot:

```bash
# systemd service example
[Service]
ExecStartPre=/usr/bin/ollama pull deepseek-v4:q4_k_m
ExecStart=/usr/bin/ollama serve
```

## Cost Comparison: Self-Hosted vs API

Assuming 1M tokens processed daily:

| Option | Monthly | Per 1M Tokens | Annual |
|--------|---------|---------------|--------|
| GPT-4o API | $20 + $10/1M × 30 | $320 | $3,840 |
| Claude 4 API | $20 + $15/1M × 30 | $470 | $5,640 |
| DeepSeek Official API | $0.50/1M × 30 | ~$15 | $180 |
| **VPS Self-Hosted** | **$30 (VPS) + $0 inference** | **$30** | **$360** |

Self-hosting breaks even at ~200K tokens/month. The more you use it, the more you save.

## Conclusion

Running DeepSeek V4 on your VPS is the optimal balance between **cost, privacy, and control**.

- **Individual users**: Start with Ollama + Open WebUI — done in 30 minutes
- **Small teams**: Go with vLLM + Open WebUI for production-grade concurrency
- **Budget machines**: Use llama.cpp for flexible CPU + GPU hybrid inference

Key takeaways:

1. **INT4 / Q4_K_M quantization** is the sweet spot for VPS deployment
2. **Ollama** is the fastest way to get started
3. **vLLM** provides production-grade throughput for multi-user setups
4. **llama.cpp** works even without a GPU
5. Pair with **Open WebUI** for a ChatGPT-like experience
6. Self-hosting's **long-term cost is far below API calls**

Local deployment of open-source LLMs isn't the future — it's already here. And your VPS is ready to run it.
