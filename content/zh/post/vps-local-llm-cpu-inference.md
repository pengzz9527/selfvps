---
title: "VPS 上跑本地大模型：llama.cpp CPU 推理 + OpenAI 兼容 API 实战"
date: 2026-11-15
slug: "vps-local-llm-cpu-inference"
tags: ["VPS", "LLM", "llama.cpp", "本地推理", "OpenAI 兼容 API", "LiteLLM", "成本优化", "运维"]
draft: false
image: /images/posts/vps-local-llm-cpu-inference/featured.png
description: "没有 GPU 也能在 1C2G 到 4C8G 的 VPS 上跑自己的大模型：llama.cpp（llama-server）Q4 量化 + CPU 线程调优 + systemd cgroup 护栏 + LiteLLM 本地/云端混合网关。实测 4B 模型 CPU 生成 5-8 tok/s，API 调用零边际成本，数据不出内网，月成本 5-6 美元封顶。"
---

# VPS 上跑本地大模型：llama.cpp CPU 推理 + OpenAI 兼容 API 实战

之前写过的 [Ollama 快速上手](/zh/post/vps-ollama-local-llm-deployment/) 解决的是"十分钟跑起来"，但它把推理引擎封装得太死：量化版本、线程数、上下文、KV 缓存类型全都默认值，低配 VPS 上经常是"能跑，但慢得没用、或者内存爆了把 nginx 拖死"。

这篇文章走另一条路：**不装 Ollama，直接用 llama.cpp 的 llama-server**，把 CPU 推理当成一个正经服务来工程化：

1. **硬件预算**：你的 VPS 到底跑得动多大的模型（有公式，不用猜）；
2. **模型与量化选择**：Q4_K_M 为什么是小 VPS 的最优解；
3. **llama-server 调优**：线程、上下文、KV 量化、jinja 模板四个关键参数；
4. **systemd + cgroup 护栏**：LLM 内存暴涨时只死自己，不拖垮全站；
5. **安全暴露**：API key + Caddy TLS，8080 永不裸露公网；
6. **LiteLLM 混合网关**：本地模型兜底简单任务，云端大模型接复杂任务，一套 OpenAI SDK 通吃；
7. **成本账与 5 个坑**。

适用对象：2C4G 左右、无 GPU 的 VPS，模型 0.6B–4B，用途是日志摘要、告警降噪、私有问答、离线 Agent 这类"准实时"场景。需要秒级交互式聊天请直接用云端 API，本文不回避这一点。

## 一、硬件预算：你的 VPS 跑得动多大的模型

先把内存账算清楚，不猜。GGUF Q4_K_M 量化下，模型权重约 **0.57 字节/参数**，再叠加 KV 缓存和运行时：

| 模型（Q4_K_M） | 权重 | + KV（4k ctx，q8_0） | + 运行时 | 建议最低内存 |
|------|:---:|:---:|:---:|:---:|
| 0.6B | ~0.4GB | ~0.1GB | ~0.3GB | 1GB（1C1G 可跑，紧） |
| 1.7B | ~1.0GB | ~0.2GB | ~0.3GB | 2GB |
| 4B | ~2.4GB | ~0.5GB | ~0.4GB | 4GB（还要给系统留 1GB） |
| 8B | ~4.9GB | ~1.0GB | ~0.5GB | 8GB |

注意内存里还要装下系统本身和 nginx/数据库等常驻服务（通常 0.5–1GB）。**4B Q4_K_M 在 2C4G 上是"能跑"，在 4C8G 上是"舒服"**。

除了内存，第二个硬指标是 CPU 指令集：

```bash
grep -o 'avx2\|avx512f' /proc/cpuinfo | sort -u
```

- 有 **AVX2**：正常，本文所有参考数字成立；
- 只有 AVX/无 AVX2（部分老 CPU、个别云厂商低价实例）：llama.cpp 回退到旧内核，**速度约为 AVX2 的 1/10**，4B 模型生成只剩 0.5 tok/s，直接降到 0.6B/1.7B；
- ARM VPS（部分厂商低价 arm 实例）：需下载 `arm64` 构建版，性能与同代 x86 接近。

## 二、模型与量化选择

小 VPS 的黄金组合是 **Qwen3 或 Gemma 3 的 Q4_K_M 版**：Q4_K_M 是精度/体积/速度三角里最均衡的量化（混合 4.5bit），比 Q5_K_M 省约 30% 内存，精度损失在日常问答/摘要场景可忽略；有内存富余再升 Q5。

```bash
# 以 Qwen3-4B 为例（约 2.5GB，HuggingFace gguf 仓库）
mkdir -p /opt/llm/models && cd /opt/llm/models
hf download Qwen/Qwen3-4B-GGUF Qwen3-4B-Q4_K_M.gguf
# 没有 huggingface CLI 的话：
# curl -L -o Qwen3-4B-Q4_K_M.gguf \
#   https://huggingface.co/Qwen/Qwen3-4B-GGUF/resolve/main/Qwen3-4B-Q4_K_M.gguf
```

选型建议：

- **1C2G**：Qwen3-1.7B Q4_K_M（约 1.0GB 权重），生成 8-12 tok/s，够用；
- **2C4G**：Qwen3-4B Q4_K_M，生成 5-8 tok/s（4 线程）；
- **4C8G**：Qwen3-4B 舒服运行（可开 8k-16k ctx），或试 8B Q4_K_M（2-3 tok/s，准离线场景可接受）。

## 三、llama-server：一个 OpenAI 兼容端点

不要自己 cmake 编译（浪费 30 分钟还可能踩坑），直接下 Release 的预编译二进制：

```bash
cd /opt/llm
# x86-64 + AVX2 构建（按官方 Release 页选对应版本）
curl -L -o llama-server \
  https://github.com/ggml-org/llama.cpp/releases/latest/download/llama-server-x64-linux-avx2
chmod +x llama-server
```

启动命令与关键参数：

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

四个必须理解的参数：

| 参数 | 含义 | 取值原则 |
|------|------|------|
| `-t N` | 推理线程数 | **= 物理核数**，绝不超发。4 vCPU 用 4；1 vCPU 就是 1（超发只会上下文切换，纯亏） |
| `-c N` | 上下文长度 | 小 VPS 用 4096；每翻倍 KV 内存近似翻倍 |
| `--cache-type-k/v q8_0` | KV 缓存量化 | 内存直接省一半，精度损失可忽略，**低配机必开** |
| `--jinja` | 启用官方 chat template | Qwen3/Gemma/Llama3 家族**必须开**，否则模型直接输出乱码 |

验证：

```bash
curl -s http://127.0.0.1:8080/v1/chat/completions \
  -H "Authorization: Bearer sk-vps-local-llm" \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen3-4b","messages":[{"role":"user","content":"用一句话解释什么是 cgroup v2"}],"max_tokens":100}'
```

返回格式与 OpenAI 完全一致——`/v1/chat/completions`、`/v1/completions`、`/v1/models` 全有，现有 OpenAI SDK 代码只改 `base_url` 和 `api_key` 即可。

**参考性能**（4 vCPU AVX2 云实例，Q4_K_M，`-t 4`、ctx 4k、KV q8_0，供对照）：

| 模型 | Prompt 处理 | 生成速度 | 进程内存 |
|------|:---:|:---:|:---:|
| Qwen3-1.7B | ~400-500 tok/s | ~10-14 tok/s | ~1.2GB |
| Qwen3-4B | ~180-260 tok/s | ~5-8 tok/s | ~2.8GB |
| Qwen3-8B | ~70-100 tok/s | ~2-3 tok/s | ~5.5GB |

1 vCPU 大约是表中值的 1/3–1/4，2 vCPU 约 1/2。单条 200 token 的摘要请求，4B 模型端到端 25-40 秒——这就是"准实时"的代价。

## 四、systemd 服务化 + cgroup 护栏

裸进程跑 LLM 最大的风险是内存：上下文一长、并发一上来，RSS 可能从 2.8GB 涨到 4GB+，没有护栏时 OOM killer 很可能挑一个 nginx 或数据库先杀。**用 cgroup v2 给 LLM 单独设天花板**（延续我们 [systemd Socket Activation 内存分层](/zh/post/vps-systemd-socket-activation-memory-budget/) 的思路，把 LLM 当作"可牺牲的边缘服务"这一档）：

`/etc/systemd/system/llama-server.service`：

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

要点：

- `MemoryMax=3G` 是硬顶：4B 权重 + 4k KV q8_0 约 2.8GB，超了直接 OOM 掉**自己**并自动重启，全站无感；
- `OomScoreAdjust=-100` 让内核 OOM 时优先牺牲 LLM，保护核心服务；
- `CPUQuota=350%` 防止推理时把其他服务的 CPU 全吃掉（vCPU 共享型实例尤其需要）；
- 系统需为 cgroup v2（Ubuntu 20.04+/Debian 12+ 默认都是，`stat -fc %T /sys/fs/cgroup/` 输出 `cgroup2fs` 即满足）。

```bash
useradd -r -m llm && chown -R llm:llm /opt/llm
systemctl daemon-reload && systemctl enable --now llama-server
journalctl -u llama-server -f   # 首启会看到 1-3 秒的模型加载日志，之后安静
```

## 五、安全暴露：8080 永不裸奔

本地推理最大的安全价值是"数据不出内网"，但 LLM 端点同时也是**全机最耗 CPU 的端点**——8080 一旦裸露公网，几分钟内就会被扫描者当作免费打点，你的 VPS 等于自建了一个 DoS 放大器。三层防护：

**1. 绑定回环 + API key**（上面 `--host 127.0.0.1` + `--api-key` 已完成，无 key 的请求直接 401）。

**2. Caddy 反代只开 443**：

```
# /etc/caddy/Caddyfile
llm.yourvps.com {
    tls yourvps.com
    reverse_proxy 127.0.0.1:8080
}
```

**3. 防火墙只放行 443**（`ufw allow 443/tcp && ufw deny 8080`，或用 nftables 同效）。

内网/远程使用更省事的方案是 [Tailscale](/zh/post/vps-tailscale-zero-config-remote-access/)：llama-server 只监听 127.0.0.1，Tailscale 主机直接 `http://100.x.x.x:8080` 访问，全程无需公网入口，Caddy 和防火墙一层都可以省掉。

## 六、LiteLLM 混合网关：本地兜底，云端升级

本地模型解决的是"便宜、私密、零边际成本"，但 4B 模型处理复杂任务（长文档分析、代码重构、多轮推理）的质量确实不如云端大模型。折中方案不是二选一，而是**一套网关两种模型**：80% 的日常请求打本地，剩下 20% 转发云端。

LiteLLM 的 proxy 模式提供 OpenAI 兼容端点 + 路由 + 限流 + 计费，pip 安装即可（Docker 版也可以，但 2C4G 上省着用，pip 版常驻约 150-250MB）：

```bash
pip install 'litellm[proxy]'
```

`/opt/llm/litellm_config.yaml`：

```yaml
model_list:
  - name: local-4b
    litellm_params:
      model: llama.cpp/qwen3-4b      # 走 OpenAI 兼容协议
      api_base: http://127.0.0.1:8080/v1
      api_key: sk-vps-local-llm
  - name: cloud-strong
    litellm_params:
      model: deepseek/deepseek-chat
      api_key: os.environ/DEEPSEEK_API_KEY

router_settings:
  fallbacks:
    - model: local-4b
      fallback: [cloud-strong]       # 本地失败/拒答才升级云端
  rate_limit_per_unit: 100           # 限流：每 key 每分钟最多 100 次请求
```

```bash
DEEPSEEK_API_KEY=sk-... litellm --config /opt/llm/litellm_config.yaml --port 4000
# 同样写 systemd unit，加 MemoryMax=512M
```

调用方统一走 `http://127.0.0.1:4000/v1`（或经 Caddy 的 443）：

```python
from openai import OpenAI
client = OpenAI(base_url="http://llm.yourvps.com:4000/v1", api_key="sk-vps-local-llm")
r = client.chat.completions.create(
    model="local-4b",
    messages=[{"role": "user", "content": "总结今天的 nginx 告警日志"}],
)
```

三个实际收益：

- **成本分层**：摘要、分类、告警降噪（token 量大、难度低）走本地 $0；复杂任务按云端计费，纯 API 方案 $20-40/月 的用量压到 $5-8/月；
- **降级可用**：云端 API 限流/欠费/网络抖动时，fallback 反过来保本地可用（把 fallback 链调换即可），站点功能不断；
- **统一入口**：调用方只认一个 OpenAI 端点，本地换模型（1.7B ↔ 4B ↔ 8B）只改网关配置，业务代码零改动。

## 七、成本账：本地 vs 纯云 API

以 2C4G VPS 月费 $5.5、重度使用 1M tokens/天（约 3000 条 300 token 摘要/天）计：

| 方案 | 月成本 | 备注 |
|------|:---:|------|
| 纯云 API（mini 级模型） | $15-30 | 随用量线性增长，无上限 |
| 纯云 API（强模型） | $60-120 | 复杂任务全打云端 |
| 本地 4B + 云端兜底（本文方案） | $5.5 + $3-6 | 80% 流量本地 $0，仅复杂/失败请求上云 |
| 纯本地（不接云端） | $5.5 | 复杂任务质量打折 |

**盈亏平衡点在日均 300-500 万 tokens**；低于这个量，本地方案的意义主要是隐私（客户数据/代码不出内网）和独立性（不被供应商 API 限流、涨价、断供挟制），而不是省钱。

## 八、一条命令部署脚本

把上面第二、三、四、五节压缩成可复跑脚本（默认 4B，`-m` 换模型路径即可）：

```bash
#!/usr/bin/env bash
set -euo pipefail
MODEL_FILE=Qwen3-4B-Q4_K_M.gguf   # 模型文件名（换 1.7B/8B 改这里）
MODEL=/opt/llm/models/${MODEL_FILE}
BIN=/opt/llm/llama-server
KEY=sk-$(openssl rand -hex 16)

grep -q avx2 /proc/cpuinfo || { echo "WARN: 无 AVX2，速度约为参考值 1/10"; }

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

# 健康检查：模型加载完 /v1/models 才返回
for i in $(seq 1 30); do
  code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:8080/v1/models" -H "Authorization: Bearer $KEY")
  [ "$code" = "200" ] && break
  journalctl -u llama-server -n 5 --no-pager; sleep 2
done
[ "$code" = "200" ] && echo "OK. API key: $KEY（写入 Caddy/调用方配置）"
```

## 九、5 个坑

1. **忘开 `--jinja`**：Qwen3/Gemma/Llama3 家族依赖 chat template，不开时模型输出乱码或复读，排查半天不如启动命令里永远带上；
2. **线程超发**：`-t` 超过物理核数后上下文切换开销反超收益，2C VPS 开 4 线程比开 2 还慢；1C 实例就老老实实 `-t 1`；
3. **模型比物理内存还大**：llama.cpp 靠 mmap 会把超出部分换到磁盘，速度从 5 tok/s 掉到 0.3 tok/s 且 page cache 抖动拖慢整机——`free -h` 先算账，不够就加 4G swap 兜底或降一档模型；
4. **8080 裸露公网**：LLM 端点是全机最贵的 CPU 端点，无鉴权开放 = 自建打点；永远 127.0.0.1 + API key + 443 反代（或 Tailscale）；
5. **上下文贪大**：`-c 32768` 在 4B 模型上 KV（fp16）要 4-5GB，q8_0 也要 2GB+，小 VPS 一开就 OOM；4096 是 2C4G 的安全区，长文档场景先切块再喂。

## 十、小结

| 决策点 | 建议 |
|------|------|
| 规格 | 2C4G 起步（4B Q4），4C8G 舒适（8k-16k ctx / 8B 试水） |
| 模型 | Qwen3 / Gemma 3 的 Q4_K_M，按"权重 ≤ 内存×0.5"选 |
| 三参数 | `-t 物理核数`、`-c 4096`、`--cache-type-k/v q8_0` + `--jinja` |
| 护栏 | systemd `MemoryMax` + `OomScoreAdjust`，让 LLM 自己 OOM |
| 暴露 | 127.0.0.1 + API key + Caddy 443（或 Tailscale 内网直连） |
| 网关 | LiteLLM fallback 链：本地 → 云端，调用方零感知 |

本地小模型不是云端 API 的替代品，而是它的**廉价兜底层**：量大、难低、私密的任务留在 VPS 里，真正复杂的问题再付云端的钱。这条 4B 模型的"准实时"管线跑通之后，下一步自然是接 [pgvector 自建向量库](/zh/post/vps-pgvector-selfhosted-vector-database/) 做 RAG——你的私有数据 + 你自己的模型，全程不出内网。
