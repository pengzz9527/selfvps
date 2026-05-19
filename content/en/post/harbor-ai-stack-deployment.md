---
title: "Harbor: One-Command AI Stack Deployment for Your VPS"
description: "Deploy a complete LLM stack (Ollama, Open WebUI, vLLM, llama.cpp, ComfyUI) on your VPS with a single command using Harbor — no manual configuration needed"
date: 2026-05-19T11:35:13+08:00
slug: "harbor-ai-stack-deployment"
tags: ["Harbor", "Ollama", "Open WebUI", "Docker", "VPS deployment", "LLM", "self-hosting"]
categories: ["AI Deployment"]
draft: false
---

## What is Harbor?

[Harbor](https://github.com/av/harbor) (2,900+ ⭐ on GitHub) is a CLI tool and companion app that spins up a complete local LLM stack with a single command. Think of it as Docker Compose for the AI world — it wires together backends (Ollama, llama.cpp, vLLM), frontends (Open WebUI, Lobe Chat, LibreChat), and supporting services (SearXNG for web search, Speaches for voice, ComfyUI for images) so they all work together out of the box.

```bash
# That's it. One command.
harbor up
# Open WebUI + Ollama are now running on your VPS.
```

No more stitching together Docker Compose files by hand, configuring reverse proxies, or debugging cross-service connectivity. Harbor handles all of that for you.

---

## Why Harbor on a VPS?

Running LLMs on a VPS is increasingly practical thanks to:

- **Cheap GPU cloud options**: VPS providers like Vast.ai, RunPod, and TensorDock offer $0.30–$0.80/hr GPU instances
- **Quantized models**: 7B–14B parameter models (Qwen2.5, Phi-4, Llama 3) run on 6–16GB VRAM with GGUF quantization
- **Data privacy**: Your API calls, prompts, and documents never leave your infrastructure

Harbor makes the _software configuration_ part trivial, so you can focus on actually using the models.

---

## Prerequisites

Before installing Harbor, your VPS needs:

| Requirement | Minimum | Recommended |
|---|---|---|
| Docker Engine | 24.x | 27.x+ |
| Docker Compose | 2.23.1+ | 2.30+ |
| RAM | 8 GB | 16 GB+ |
| Disk | 20 GB | 50 GB+ |
| GPU (optional) | NVIDIA with 6 GB VRAM | NVIDIA with 12 GB+ VRAM |

Verify Docker is ready:

```bash
docker --version
docker compose version
```

---

## Step 1: Install Harbor

Harbor offers a one-liner install script:

```bash
curl https://raw.githubusercontent.com/av/harbor/refs/heads/main/install.sh | bash
```

This installs the `harbor` CLI to `/usr/local/bin`. Verify it works:

```bash
harbor --version
harbor doctor   # Checks Docker, disk space, and GPU availability
```

> **No GPU?** No problem. Harbor will run models on CPU. For 7B models with 8 GB RAM, expect 3–8 tokens/sec — usable for chat and batch processing.

---

## Step 2: Deploy the Default Stack

The default stack includes **Ollama** (backend) + **Open WebUI** (frontend). Start it with:

```bash
harbor up
```

Harbor will:
1. Pull the latest Docker images
2. Start Ollama on `localhost:11434`
3. Start Open WebUI on `localhost:3000`
4. Wire them together automatically

When you see "Services started successfully", open the web UI:

```bash
harbor open
```

**First time?** Create an admin account in Open WebUI, then pull a model from the admin panel or via CLI:

```bash
# Pull a model from the VPS terminal
docker exec -it $(docker ps -q -f name=ollama) ollama pull qwen2.5:7b
# Or try a smaller model for 8 GB RAM
docker exec -it $(docker ps -q -f name=ollama) ollama pull phi-4-mini:3.8b
```

Alternatively, use Harbor's built-in model management:

```bash
harbor ollama pull qwen2.5:7b
```

---

## Step 3: Add Supporting Services

Harbor's real power is adding services on top of the base stack:

```bash
# Add web search RAG (SearXNG) + voice (Speaches)
harbor up searxng speaches
```

This enables:
- **SearXNG** → Open WebUI can search the web and feed results into LLM context (Web RAG)
- **Speaches** → OpenAI-compatible speech-to-text and text-to-speech (whisper + TTS)

Other useful services to try:

```bash
# Image generation
harbor up comfyui

# Alternative inference backends
harbor up llamacpp   # CPU-friendly GGUF inference
harbor up vllm       # High-throughput GPU inference

# Alternative frontends
harbor up lobechat   # Modern UI with multi-provider support
harbor up dify       # LLM app development platform
```

---

## Step 4: Enable GPU Acceleration (NVIDIA)

If your VPS has an NVIDIA GPU, enable GPU passthrough to Docker:

**Ubuntu/Debian:**
```bash
# Install NVIDIA Container Toolkit
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
  sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
sudo systemctl restart docker
```

**Verify GPU access:**
```bash
docker run --rm --gpus all nvidia/cuda:12.0.0-base-ubuntu22.04 nvidia-smi
```

After installing, Harbor auto-detects the `nvidia` capability and passes `--gpus all` to containers that support it.

---

## Step 5: Expose Harbor Securely

To access Harbor's web UI from outside your VPS, use Cloudflare Tunnel (built into Harbor):

```bash
# Configure tunnel for Open WebUI
harbor tunnels add webui
```

This starts `cloudflared` as a sidecar and gives you a `*.trycloudflare.com` URL. For production:

1. Set up a Cloudflare domain with a CNAME record
2. Configure `cloudflared` with your tunnel token
3. Add authentication (Open WebUI already requires login)

> ⚠️ **Security warning**: Never expose Open WebUI to the internet without authentication. Harbor's default setup requires a login, but double-check your config.

---

## Step 6: Switch Inference Backends

Harbor supports multiple LLM backends. Here's how to choose:

| Backend | Best For | GPU Required | Speed |
|---|---|---|---|
| **Ollama** | General use, easy model management | Optional | Good |
| **llama.cpp** | CPU inference, GGUF format | No | Good on CPU |
| **vLLM** | High-throughput API serving | Yes | Excellent |
| **TabbyAPI** | ExLlamaV2, large context | Yes | Very fast |
| **SGLang** | Structured outputs, VLMs | Yes | Excellent |

Example: Switch to vLLM for production API serving:

```bash
# Stop current stack, restart with vLLM
harbor down
harbor up vllm
# vLLM API is now at localhost:8000 with OpenAI-compatible endpoints
```

You can even run _multiple_ backends simultaneously — Harbor connects them all to Open WebUI.

---

## Harbor Cheatsheet

```bash
harbor up                    # Start default stack (Ollama + Open WebUI)
harbor up searxng speaches  # Add services
harbor up --no-defaults vllm # Start only vLLM (skip defaults)
harbor down                  # Stop all services
harbor open                  # Open web UI in browser
harbor logs webui            # Tail logs for a specific service
harbor ps                    # Show running services
harbor doctor                # System compatibility check
harbor update                # Update Harbor CLI
harbor config set ui.autoopen true  # Auto-open browser
harbor ollama pull qwen2.5:7b       # Pull model via Ollama
harbor tunnels add webui            # Expose via Cloudflare
```

---

## Resource Estimates by Model Size

| Model | Size | RAM/VRAM | Tokens/sec (CPU) | Tokens/sec (GPU) |
|---|---|---|---|---|
| Phi-4-mini (3.8B) Q4 | 2.5 GB | 4 GB | 15–25 | 80–120 |
| Qwen2.5-7B Q4 | 4.5 GB | 6 GB | 5–10 | 40–60 |
| Llama 3.1-8B Q4 | 5 GB | 8 GB | 4–8 | 35–55 |
| DeepSeek-R1-Distill-7B Q4 | 5 GB | 8 GB | 4–7 | 30–50 |
| Qwen2.5-14B Q4 | 9 GB | 14 GB | 2–4 | 20–35 |
| Mistral-Small-24B Q4 | 14 GB | 20 GB | 1–2 | 12–20 |

---

## Real-World VPS Configurations

**Budget setup ($10–20/mo):**
- 2 vCPU, 8 GB RAM, no GPU
- Run Phi-4-mini or Qwen2.5:7B on CPU via Ollama
- Harbor + Open WebUI + SearXNG for web RAG
- ~5–10 tokens/sec — fine for casual chat

**Mid-range ($30–50/mo):**
- 4 vCPU, 16 GB RAM, NVIDIA T4 (16 GB VRAM)
- Run Llama 3.1-8B or Qwen2.5-14B with vLLM
- Add Speaches for voice I/O, ComfyUI for images
- ~40–60 tokens/sec — production-ready

**High-end ($100–150/mo):**
- 8 vCPU, 32 GB RAM, NVIDIA L40S (48 GB VRAM)
- Run Mistral-Small-24B or Qwen2.5-32B
- Full stack: vLLM + Open WebUI + Dify + ComfyUI + SearXNG
- ~60+ tokens/sec — team usage

---

## Conclusion

Harbor eliminates the hardest part of self-hosting AI — the configuration. With one command, you get a complete, production-ready LLM stack on your VPS. The 50+ available services mean you can expand from a simple chat interface to a full AI platform (RAG, voice, images, workflows) incrementally, as your needs grow.

The AI self-hosting ecosystem has matured to the point where setting up your own ChatGPT replacement takes minutes, not days. Harbor is the tool that makes that possible.

**Next steps:**
- Browse all 50+ services: `harbor ls`
- Join the [Harbor Discord](https://discord.gg/8nDRphrhSF)
- Try deploying with a GPU-equipped VPS from Vast.ai, RunPod, or TensorDock
