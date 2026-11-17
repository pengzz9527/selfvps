---
title: "Running a Local LLM on Your VPS: llama.cpp CPU Inference + an OpenAI-Compatible API"
date: 2026-11-15
slug: "vps-local-llm-cpu-inference"
tags: ["VPS", "LLM", "llama.cpp", "Local Inference", "OpenAI-Compatible API", "LiteLLM", "Cost Optimization", "DevOps"]
draft: false
image: /images/posts/vps-local-llm-cpu-inference/featured.png
description: "No GPU required: run your own LLM on a 1C2G–4C8G VPS with llama.cpp (llama-server) Q4 quantization, CPU thread tuning, systemd cgroup guardrails, and a LiteLLM local/cloud hybrid gateway. A 4B model generates at 5-8 tok/s on CPU at $0 marginal cost per call, with data never leaving your network and monthly cost capped at $5-6."
---

# Running a Local LLM on Your VPS: llama.cpp CPU Inference + an OpenAI-Compatible API

Our [Ollama quickstart](/en/post/vps-ollama-local-llm-deployment/) solves "get something running in ten minutes," but it wraps the inference engine so tightly that quantization, thread count, context length, and KV cache type all stay at defaults. On a low-spec VPS that usually means "it works, but it's either too slow to be useful or it OOMs and takes nginx down with it."

This post takes a different path: **skip Ollama and use llama.cpp's `llama-server` directly**, and engineer CPU inference as a proper service:

1. **Hardware budgeting** — a formula for figuring out what your VPS can actually run (no guesswork);
2. **Model and quantization choice** — why Q4_K_M is the sweet spot for small VPS;
3. **llama-server tuning** — the four parameters that matter: threads, context, KV quantization, and the jinja chat template;
4. **systemd + cgroup guardrails** — when the LLM balloons, it OOMs itself and restarts; the rest of your stack never blinks;
5. **Secure exposure** — API key + Caddy TLS, port 8080 never hits the public internet;
6. **LiteLLM hybrid gateway** — local model handles the simple 80%, cloud handles the complex 20%, one OpenAI SDK for everything;
7. **The cost math and 5 pitfalls**.

Target audience: a ~2C4G VPS without a GPU, models in the 0.6B–4B class, workloads like log summarization, alert denoising, private Q&A, or offline agents — "near-realtime" is fine, instant is not. If you need sub-second interactive chat, use a cloud API; we won't pretend otherwise.

## 1. Hardware Budget: What Model Can Your VPS Actually Run

Do the memory math first, then buy. With GGUF Q4_K_M, weights cost about **0.57 bytes/parameter**, plus KV cache and runtime overhead:

| Model (Q4_K_M) | Weights | + KV (4k ctx, q8_0) | + Runtime | Minimum RAM |
|------|:---:|:---:|:---:|:---:|
| 0.6B | ~0.4GB | ~0.1GB | ~0.3GB | 1GB (runs on 1C1G, tight) |
| 1.7B | ~1.0GB | ~0.2GB | ~0.3GB | 2GB |
| 4B | ~2.4GB | ~0.5GB | ~0.4GB | 4GB (leave 1GB for the OS) |
| 8B | ~4.9GB | ~1.0GB | ~0.5GB | 8GB |

Remember RAM also holds the OS plus your nginx/database/etc. (usually 0.5–1GB). **A 4B Q4_K_M is "survivable" on 2C4G and "comfortable" on 4C8G.**

The second hard requirement is CPU instruction set:

```bash
grep -o 'avx2\|avx512f' /proc/cpuinfo | sort -u
```

- **AVX2**: good, every reference number below holds;
- AVX-only / no AVX2 (older CPUs, some cheap cloud instances): llama.cpp falls back to slower kernels, **expect ~1/10 the speed** — a 4B model drops to ~0.5 tok/s, step down to 0.6B/1.7B;
- ARM VPS (some cheap arm instances): download the `arm64` build; performance is close to equivalent-generation x86.

## 2. Model and Quantization

The gold combo for small VPS is **Qwen3 or Gemma 3 in Q4_K_M**: Q4_K_M (mixed 4.5-bit) is the best precision/size/speed trade — it saves ~30% memory vs Q5_K_M with quality loss you won't notice for daily Q&A or summarization. Upgrade to Q5 only when you have spare RAM.

```bash
# Qwen3-4B example (~2.5GB, HuggingFace gguf repo)
mkdir -p /opt/llm/models && cd /opt/llm/models
hf download Qwen/Qwen3-4B-GGUF Qwen3-4B-Q4_K_M.gguf
# Without the huggingface CLI:
# curl -L -o Qwen3-4B-Q4_K_M.gguf \
#   https://huggingface.co/Qwen/Qwen3-4B-GGUF/resolve/main/Qwen3-4B-Q4_K_M.gguf
```

Recommendations:

- **1C2G**: Qwen3-1.7B Q4_K_M (~1.0GB weights), 8-12 tok/s — enough;
- **2C4G**: Qwen3-4B Q4_K_M, 5-8 tok/s (4 threads);
- **4C8G**: Qwen3-4B with room to spare (8k-16k ctx), or try 8B Q4_K_M (2-3 tok/s, acceptable for near-offline work).

## 3. llama-server: One OpenAI-Compatible Endpoint

Don't waste 30 minutes cmake-compiling (and maybe hitting a footgun); grab the prebuilt release binary:

```bash
cd /opt/llm
# x86-64 + AVX2 build (pick the matching one on the official releases page)
curl -L -o llama-server \
  https://github.com/ggml-org/llama.cpp/releases/latest/download/llama-server-x64-linux-avx2
chmod +x llama-server
```

Startup command and the parameters that matter:

```bash
./llama-server \
  -m /opt/llm/models/Qwen3-4B-Q4_K_M.gguf \
  --host 127.0.0.1 --port 8080 \
  -c 4096 \
  -t 4 \
  -np 2 \
  --cache-type-k q8_0 --cache-type-v q8_0 \
  --jinja \
  --api-key sk-vps-local-llm
```

The four you must understand:

| Flag | Meaning | Rule of thumb |
|------|------|------|
| `-t N` | Inference threads | **= physical cores, never more**. 4 vCPU → 4; 1 vCPU → 1 (oversubscribing only adds context switches) |
| `-c N` | Context length | 4096 on small VPS; KV memory roughly doubles per doubling |
| `--cache-type-k/v q8_0` | Quantized KV cache | Halves KV memory, negligible quality loss, **mandatory on low-spec boxes** |
| `--jinja` | Load the official chat template | **Required** for the Qwen3/Gemma/Llama3 families, or the model spits out gibberish |

Verify:

```bash
curl -s http://127.0.0.1:8080/v1/chat/completions \
  -H "Authorization: Bearer sk-vps-local-llm" \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen3-4b","messages":[{"role":"user","content":"Explain cgroup v2 in one sentence"}],"max_tokens":100}'
```

The response format is identical to OpenAI's — `/v1/chat/completions`, `/v1/completions`, and `/v1/models` all exist. Existing OpenAI SDK code only needs a new `base_url` and `api_key`.

**Reference performance** (4 vCPU AVX2 cloud instance, Q4_K_M, `-t 4`, 4k ctx, q8_0 KV — use for comparison):

| Model | Prompt processing | Generation | Process RAM |
|------|:---:|:---:|:---:|
| Qwen3-1.7B | ~400-500 tok/s | ~10-14 tok/s | ~1.2GB |
| Qwen3-4B | ~180-260 tok/s | ~5-8 tok/s | ~2.8GB |
| Qwen3-8B | ~70-100 tok/s | ~2-3 tok/s | ~5.5GB |

A 1 vCPU instance is roughly 1/3–1/4 of the table; 2 vCPU about 1/2. A single 200-token summarization request on the 4B model takes 25-40 seconds end-to-end — that's the price of "near-realtime."

## 4. systemd + cgroup Guardrails

The biggest risk of a bare LLM process is memory: long contexts plus concurrency can push RSS from 2.8GB to 4GB+, and without a guardrail the OOM killer will happily pick nginx or your database first. **Give the LLM its own cgroup v2 ceiling** (same tiering idea as our [systemd Socket Activation memory budget](/en/post/vps-systemd-socket-activation-memory-budget/) post — the LLM is an "edge service" that's fine to sacrifice):

`/etc/systemd/system/llama-server.service`:

```ini
[Unit]
Description=llama.cpp local LLM server (CPU inference)
After=network-online.target
Wants=network-online.target

[Service]
User=llm
Group=llm
WorkingDirectory=/opt/llm
ExecStart=/opt/llm/llama-server -m /opt/llm/models/Qwen3-4B-Q4_K_M.gguf \
  --host 127.0.0.1 --port 8080 -c 4096 -t 4 -np 2 \
  --cache-type-k q8_0 --cache-type-v q8_0 \
  --jinja --api-key sk-vps-local-llm
Restart=on-failure
RestartSec=5
MemoryMax=3G
MemoryHigh=2.5G
TasksMax=32
CPUQuota=350%
OomScoreAdjust=-100

[Install]
WantedBy=multi-user.target
```

Why these knobs:

- `MemoryMax=3G` is a hard cap: 4B weights + 4k q8_0 KV is ~2.8GB; past the cap the LLM **OOMs and restarts itself** — the rest of the site never notices;
- `OomScoreAdjust=-100` makes the kernel's OOM killer sacrifice the LLM first, protecting core services;
- `CPUQuota=350%` stops inference from starving other services (critical on shared-vCPU instances);
- Requires cgroup v2 (default on Ubuntu 20.04+/Debian 12+; `stat -fc %T /sys/fs/cgroup/` printing `cgroup2fs` confirms it).

```bash
useradd -r -m llm && chown -R llm:llm /opt/llm
systemctl daemon-reload && systemctl enable --now llama-server
journalctl -u llama-server -f   # 1-3s of model-loading logs on first start, then quiet
```

## 5. Secure Exposure: Never Run 8080 Naked

Local inference's main security value is "data never leaves the network," but an LLM endpoint is also **the most CPU-expensive endpoint on the box** — if 8080 faces the public internet, scanners find it within minutes and use it as a free endpoint, effectively self-DoS-ing your VPS. Three layers:

**1. Loopback bind + API key** (`--host 127.0.0.1` + `--api-key` above; requests without the key get 401).

**2. Caddy reverse proxy on 443 only**:

```
# /etc/caddy/Caddyfile
llm.yourvps.com {
    tls yourvps.com
    reverse_proxy 127.0.0.1:8080
}
```

**3. Firewall allows 443 only** (`ufw allow 443/tcp && ufw deny 8080`, or the nftables equivalent).

For internal/remote use, the easier route is [Tailscale](/en/post/vps-tailscale-zero-config-remote-access/): llama-server stays on 127.0.0.1, and Tailscale hosts hit `http://100.x.x.x:8080` directly — no public ingress at all, so you can skip Caddy and the firewall layer.

## 6. LiteLLM Hybrid Gateway: Local as Fallback, Cloud as Escalation

Local models buy you "cheap, private, zero marginal cost," but a 4B model genuinely can't match cloud frontier models on hard tasks (long-document analysis, code refactoring, multi-step reasoning). The answer isn't pick-one — it's **one gateway, two tiers**: 80% of daily traffic hits the local model, the remaining 20% escalates to the cloud.

LiteLLM's proxy mode gives you an OpenAI-compatible endpoint plus routing, rate limits, and keys. `pip install` is fine (the Docker image works too, but on 2C4G keep it lean — the pip install idles around 150-250MB):

```bash
pip install 'litellm[proxy]'
```

`/opt/llm/litellm_config.yaml`:

```yaml
model_list:
  - name: local-4b
    litellm_params:
      model: llama.cpp/qwen3-4b      # OpenAI-compatible protocol
      api_base: http://127.0.0.1:8080/v1
      api_key: sk-vps-local-llm
  - name: cloud-strong
    litellm_params:
      model: deepseek/deepseek-chat
      api_key: os.environ/DEEPSEEK_API_KEY

router_settings:
  fallbacks:
    - model: local-4b
      fallback: [cloud-strong]       # escalate to cloud only on local failure/refusal
  rate_limit_per_unit: 100           # limit: 100 requests/key/minute
```

```bash
DEEPSEEK_API_KEY=sk-... litellm --config /opt/llm/litellm_config.yaml --port 4000
# Same treatment: systemd unit with MemoryMax=512M
```

Callers use one OpenAI endpoint (`http://127.0.0.1:4000/v1`, or 443 through Caddy):

```python
from openai import OpenAI
client = OpenAI(base_url="http://llm.yourvps.com:4000/v1", api_key="sk-vps-local-llm")
r = client.chat.completions.create(
    model="local-4b",
    messages=[{"role": "user", "content": "Summarize today's nginx alert log"}],
)
```

Three practical wins:

- **Cost tiering**: summarization, classification, alert denoising (high token volume, low difficulty) run locally at $0; only complex or failed requests bill against the cloud — a pure-API setup costing $20-40/mo drops to $5-8/mo;
- **Graceful degradation**: when the cloud API rate-limits, gets delinquent, or has network hiccups, you can flip the fallback direction to keep serving from local — your site's AI features never go dark;
- **Single entry point**: callers know one OpenAI endpoint; swapping the local model (1.7B ↔ 4B ↔ 8B) is a gateway config change, zero business-code churn.

## 7. The Cost Math: Local vs. Pure Cloud API

Assume a 2C4G VPS at $5.5/mo and heavy usage at 1M tokens/day (~3,000 three-hundred-token summaries a day):

| Approach | Monthly cost | Notes |
|------|:---:|------|
| Pure cloud API (mini-class model) | $15-30 | Grows linearly with usage, unbounded |
| Pure cloud API (strong model) | $60-120 | All complex tasks on the cloud |
| Local 4B + cloud fallback (this post) | $5.5 + $3-6 | 80% of traffic local at $0, only complex/failed calls hit the cloud |
| Pure local (no cloud) | $5.5 | Complex tasks take a quality hit |

**Break-even lands around 3-5M tokens/day**; below that, the value of the local setup is privacy (customer data and code never leave the network) and independence (no vendor rate limits, price hikes, or service cuts holding your features hostage) more than raw savings.

## 8. One-Command Deploy Script

Everything from sections 2, 3, 4, and 5 compressed into an idempotent script (defaults to the 4B; swap the model filename to use 1.7B/8B):

```bash
#!/usr/bin/env bash
set -euo pipefail
MODEL_FILE=Qwen3-4B-Q4_K_M.gguf   # model filename (edit to switch 1.7B/8B)
MODEL=/opt/llm/models/${MODEL_FILE}
BIN=/opt/llm/llama-server
KEY=sk-$(openssl rand -hex 16)

grep -q avx2 /proc/cpuinfo || echo "WARN: no AVX2, expect ~1/10 of reference speeds"

useradd -r llm 2>/dev/null || true
mkdir -p /opt/llm/models
[ -f "$MODEL" ] || hf download Qwen/Qwen3-4B-GGUF "$MODEL_FILE" --local-dir /opt/llm/models
curl -sfL -o "$BIN" https://github.com/ggml-org/llama.cpp/releases/latest/download/llama-server-x64-linux-avx2
chmod +x "$BIN"; chown -R llm:llm /opt/llm

cat > /etc/systemd/system/llama-server.service <<EOF
[Unit]
Description=llama.cpp local LLM server (CPU inference)
After=network-online.target

[Service]
User=llm
WorkingDirectory=/opt/llm
ExecStart=$BIN -m $MODEL --host 127.0.0.1 --port 8080 -c 4096 \
  -t $(nproc) -np 2 --cache-type-k q8_0 --cache-type-v q8_0 --jinja --api-key $KEY
Restart=on-failure
MemoryMax=3G
CPUQuota=350%
OomScoreAdjust=-100

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now llama-server
sleep 3

# Health check: /v1/models only returns once the model is loaded
code=000
for i in $(seq 1 30); do
  code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:8080/v1/models" -H "Authorization: Bearer $KEY")
  [ "$code" = "200" ] && break
  journalctl -u llama-server -n 5 --no-pager; sleep 2
done
[ "$code" = "200" ] && echo "OK. API key: $KEY (add to Caddy/caller configs)"
```

## 9. Five Pitfalls

1. **Forgetting `--jinja`**: the Qwen3/Gemma/Llama3 families depend on chat templates — without the flag the model outputs gibberish or loops. It's a ten-second debug versus an hour of head-scratching; always keep it in the startup command;
2. **Oversubscribing threads**: past physical core count, context-switch overhead eats the gains — on a 2C VPS, 4 threads is *slower* than 2. A 1C instance gets `-t 1`, no debate;
3. **Model bigger than physical RAM**: llama.cpp mmaps, so the overflow silently spills to disk — generation drops from 5 tok/s to 0.3 tok/s and page-cache churn slows the whole box. Check `free -h` first; add a 4G swap backstop or step down a model size;
4. **8080 public**: an unauthenticated LLM endpoint is the most expensive CPU endpoint on your VPS — exposing it is building your own DDoS amp. Always 127.0.0.1 + API key + 443 reverse proxy (or Tailscale);
5. **Greedy context**: `-c 32768` needs 4-5GB of KV on a 4B model even quantized (2GB+ with q8_0) — on a small VPS that's instant OOM. 4096 is the safe zone for 2C4G; for long documents, chunk them first.

## 10. Summary

| Decision | Recommendation |
|------|------|
| Spec | Start at 2C4G (4B Q4); 4C8G is comfortable (8k-16k ctx / 8B trials) |
| Model | Qwen3 / Gemma 3 Q4_K_M, sized to "weights ≤ 50% of RAM" |
| Three flags | `-t physical-cores`, `-c 4096`, `--cache-type-k/v q8_0` + `--jinja` |
| Guardrails | systemd `MemoryMax` + `OomScoreAdjust` — let the LLM OOM itself |
| Exposure | 127.0.0.1 + API key + Caddy 443 (or Tailscale internal access) |
| Gateway | LiteLLM fallback chain: local → cloud, callers never know |

A local small model isn't a replacement for cloud APIs — it's their **cheap fallback tier**: high-volume, low-difficulty, sensitive work stays in your VPS, and genuinely hard problems still pay the cloud's price. Once this 4B "near-realtime" pipeline is running, the natural next step is a [self-hosted pgvector store](/en/post/vps-pgvector-selfhosted-vector-database/) for RAG — your private data, your own model, nothing ever leaving the network.
