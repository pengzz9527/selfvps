---
title: "在 VPS 上自建 LLM 语义缓存网关：GPTCache + LiteLLM 让 40% 的提问零成本"
date: 2026-11-17T21:30:00+08:00
tags: ["VPS", "LLM", "语义缓存", "GPTCache", "LiteLLM", "pgvector", "API 网关", "成本优化", "Ollama"]
draft: false
image: /images/posts/vps-llm-semantic-cache-gateway/featured.png
description: "LLM API 账单越跑越大？真实业务里 30-60% 的提问是语义重复的。本文教你在 1C2G VPS 上自建一层语义缓存网关：LiteLLM 聚合多模型 + GPTCache 语义命中 + pgvector 向量检索 + 本地 Ollama embedding，再叠加 per-key 预算护栏与 Prometheus 命中率/节省额监控。实测规划：40% 命中率下 GPT-4o 路由月省约 $510，本地/DeepSeek 路由月省 $18-30，扣掉 $5 VPS 后净赚，并附 5 个生产坑。"
categories: ["AI + VPS 实战"]
aliases: ["/zh/post/vps-llm-semantic-cache-gateway/"]
---

# 在 VPS 上自建 LLM 语义缓存网关：GPTCache + LiteLLM 让 40% 的提问零成本

如果你的团队已经在调 LLM API，账单大概率是逐月爬升的。但很少有人认真做过一件事：**统计一下过去 30 天里，有多少条 prompt 在语义上是重复的**。

在客服机器人、内部 FAQ、代码问答、文档摘要这些真实场景里，这个数字通常是 **30-60%**。用户换个说法问同一个问题、把"如何配置 Redis 连接池"改成"Redis 连接池怎么配"、把上一轮的答案追问一句——这些请求最终调用的是同一个模型、得到几乎一样的回答，但你每次都付了全价。

**语义缓存（semantic cache）** 就是冲着这个来的：把问题 embedding 成向量，去查"我之前是不是问过语义上几乎一样的事"，命中就直接返回缓存答案，不碰 LLM。它和 Redis/内存里的**精确 key 缓存**是两回事——精确缓存要求 prompt 一字不差，语义缓存允许"换了说法"。

整套东西可以落在一台 **1C2G VPS** 上，开源组件，月成本 ≈ $5（一台便宜的 VPS），而省下来的 LLM 调用费对 GPT-4o 这类贵模型能到 **$500/月**。下面给你完整架构、部署脚本、调参、监控和 5 个生产坑。

> 本文不重复 [LiteLLM 网关部署](/zh/post/litellm-proxy-deployment-vps/) 和 [pgvector 向量库](/zh/post/vps-pgvector-selfhosted-vector-database/) 的基础，只讲"把语义缓存这一层插进去"怎么做。

## 架构总览

```
   你的应用 / 客服 Bot / 内部工具
                │  OpenAI 兼容 API
                ▼
        ┌─────────────────┐
        │  GPTCache 网关   │  1. embedding（本地 Ollama, CPU）
        │  (FastAPI 薄壳)  │  2. pgvector 余弦相似度检索
        │                  │  3. 相似度 ≥ 阈值 → 返回缓存答案（零 LLM 成本）
        └────────┬─────────┘
        未命中    │
                ▼
        ┌─────────────────┐
        │  LiteLLM Proxy  │  多模型聚合 + 路由 + per-key 预算护栏 + 限流
        │  (:4000)        │  → OpenAI / DeepSeek / 本地 Ollama / Claude…
        └─────────────────┘
                │
        命中/未命中计数、tokens、估算节省额
                ▼
        Prometheus textfile（命中率、$ 节省、tokens 节省）→ Grafana + 告警
```

三个组件各司其职，彼此解耦：

- **GPTCache**：语义缓存大脑。负责 embed、检索、存/取缓存答案。
- **LiteLLM Proxy**：把"真正要付钱的 LLM 调用"收口到一个 OpenAI 兼容入口，顺带做 per-key 预算上限、限流、多模型路由。它是你的**成本防火墙**。
- **pgvector**：向量存储。GPTCache 把 embedding 和答案一起写进去，用余弦相似度检索。
- **本地 Ollama embedding**（`nomic-embed-text`，~55MB，CPU 可跑）：把 embedding 也留在内网，**连 embedding 的 API 钱都不花**，数据不出 VPS。

## 一、语义缓存的原理，以及它什么时候不该用

GPTCache 的命中逻辑是：

1. 拿到新问题 `q`，用 embedding 模型算出向量 `v(q)`；
2. 在 pgvector 里找余弦相似度最高的历史问题 `q'`，得到 score；
3. `score ≥ 阈值 θ` 就判"命中"，直接返回当初缓存的 `answer(q')`；
4. 否则 miss，调真正的 LLM 生成答案，把 `(v(q), q, answer)` 写回 pgvector。

**关键参数是阈值 θ。** GPTCache 默认比较宽松（~0.7），对"省成本"来说是好事，但对"答得对"来说太危险——余弦 0.7 的两个问题，在客服/医疗/合规场景可能完全不该共用一个答案。所以：

- **确定性、可复用**的任务（FAQ、产品文档问答、内部操作手册）：θ 可以取 **0.80-0.85**，命中率最高；
- **开放创作、代码生成、一次性任务**：命中率天然 <10%，而且近义但意图不同的输入极易"串答案"，建议这类**直接不走语义缓存**（或退化成精确 key 缓存）。

一句话原则：**语义缓存是给"高频、低熵、答案可复用"的流量省钱用的，不是给所有流量用的。**

## 二、部署：pgvector + GPTCache + 本地 embedding

### 1. 装 pgvector 并建库

```bash
sudo apt update && sudo apt install -y postgresql postgresql-contrib
sudo -u postgres psql -c "CREATE USER gptcache WITH PASSWORD 'change-me';"
sudo -u postgres psql -c "CREATE DATABASE gptcache OWNER gptcache;"
sudo -u postgres psql -d gptcache -c "CREATE EXTENSION vector;"
# 建向量表（dim=768 对应 nomic-embed-text）
sudo -u postgres psql -d gptcache -c "
CREATE TABLE IF NOT EXISTS cache (
  id SERIAL PRIMARY KEY,
  embedding vector(768),
  query TEXT,
  response TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);"
```

> 想省内存可以直接用 SQLite + `sqlite-vec`，但 pgvector 的 HNSW 索引在 10 万级以上向量时检索稳定得多，且你大概率已经有 Postgres。

### 2. 拉一个本地 embedding 模型（Ollama，CPU 即可）

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull nomic-embed-text   # ~55MB，768 维，CPU 上 ~512MB 内存
```

`nomic-embed-text` 是语义缓存里的"性价比之王"：小、快、余弦相似度区分度好，CPU 就能跑，不占 GPU。中文场景可换 `bge-small-zh`（同尺寸级别）。

### 3. GPTCache 服务（FastAPI 薄壳）

> GPTCache 各版本 API 有出入（0.1.x / 0.2.x），下面以 0.1.x 为准；字段名报不符就用 `pip show GPTCache` 查版本后对照官方 docs。

```python
# gptcache_service.py
import os
from GPTCache import Cache
from GPTCache.cache import CacheFactory
from GPTCache.embedding import OllamaEmbedding
from GPTCache.storage.vector_data_storage import PGVectorData
import requests

vector_data = PGVectorData(
    host="127.0.0.1", port=5432,
    user="gptcache", password=os.environ["GPTCACHE_PG_PASS"],
    dbname="gptcache", table="cache", dim=768,
)
embedding = OllamaEmbedding(
    base_url="http://127.0.0.1:11434", model="nomic-embed-text",
)
cache = CacheFactory(
    cache_data="in_memory",       # 热层，冷数据回落到 pgvector
    vector_data=vector_data,
    embedding=embedding,
).init_cache()
# 命中阈值：客服/FAQ 场景从 0.82 起调
cache.set_cache_params({"similarity_threshold": 0.82})

LITELLM = os.environ["LITELLM_PROXY"]   # http://127.0.0.1:4000/v1
LITELLM_KEY = os.environ["LITELLM_MASTER_KEY"]

def llm_call(q: str, model="deepseek-chat") -> str:
    r = requests.post(f"{LITELLM}/chat/completions",
        headers={"Authorization": f"Bearer {LITELLM_KEY}"},
        json={"model": model, "messages": [{"role":"user","content": q}], "temperature": 0},
        timeout=60)
    return r.json()["choices"][0]["message"]["content"]

def answer(q: str, model="deepseek-chat") -> dict:
    if cache.check(q):                 # 语义命中？
        return {"hit": True,  "answer": cache.get(q), "model": model}
    a = llm_call(q, model)            # miss → 真调 LLM
    cache.set(q, a)                   # 写回向量库
    return {"hit": False, "answer": a, "model": model}

# 极简 HTTP 暴露（生产请加鉴权/限流）
from fastapi import FastAPI
app = FastAPI()
@app.post("/v1/answer")
def endpoint(body: dict):
    return answer(body["query"], body.get("model", "deepseek-chat"))
```

跑起来：

```bash
pip install GPTCache pgvector psycopg2-binary fastapi uvicorn
GPTCACHE_PG_PASS='change-me' LITELLM_PROXY=http://127.0.0.1:4000/v1 \
LITELLM_MASTER_KEY=*** uvicorn gptcache_service:app --host 127.0.0.1 --port 8100
```

## 三、LiteLLM Proxy：把"付钱的调用"收口，并加预算护栏

语义缓存解决"少调用"，LiteLLM 解决"调用收口 + 不超支"。[LiteLLM 部署](/zh/post/litellm-proxy-deployment-vps/) 讲过基础，这里只补**预算护栏**这一段——它把语义缓存网关升级成一个**成本防火墙**。

`config.yaml`：

```yaml
model_list:
  - model: deepseek-chat
    litellm_params: { model: deepseek/deepseek-chat, api_key: os.environ/DEEPSEEK_API_KEY }
  - model: gpt-4o-mini
    litellm_params: { model: gpt-4o-mini,      api_key: os.environ/OPENAI_API_KEY }
  - model: local-llama
    litellm_params: { model: openai/llama-3-8b, api_base: http://127.0.0.1:11434/v1, api_key: ollama }
general_settings:
  master_key: sk-master-xxxxxx
  max_budget: 100.0            # 全平台总预算 $（硬顶）
  tpm_limit: 120000
  num_retries: 2
litellm_settings:
  cache: false                # 精确缓存我们自己不依赖，语义缓存由 GPTCache 负责
```

给每个业务方一个**有预算上限的 key**，等于给每路流量装了独立电表：

```bash
curl -X POST http://localhost:4000/key/generate \
  -H "Authorization: Bearer sk-ma***" \
  -H "Content-Type: application/json" \
  -d '{
    "max_budget": 5.0,
    "max_budget_lock": true,
    "tpm_limit": 20000, "rpm_limit": 100,
    "models": ["deepseek-chat", "gpt-4o-mini"]
  }'
```

`max_budget_lock: true` 意味着该 key 花到 $5 就自动拒绝——一个失控的 Bot 不会把全平台 $100 的预算一夜烧穿。

## 四、监控：命中率与"省了多少钱"

语义缓存最大的风险是"感觉在省钱，其实没在"。做一个 Prometheus textfile 侧车，GPTCache 网关每处理一条就累加计数，exporter 定期写出：

```python
# 在 gptcache_service 里加（简化）
import time
STATS = {"hits":0, "misses":0, "tokens_saved":0, "cost_saved_usd":0.0, "last_flush":0}

def record(hit: bool, q: str, a: str):
    if hit:
        STATS["hits"] += 1
        # 估算省下的 tokens/费用（按所用模型单价，此处示例用 DeepSeek V3）
        toks = len(q)//2 + len(a)//2
        STATS["tokens_saved"] += toks
        STATS["cost_saved_usd"] += toks/1e6*0.28/2   # 输出价 $0.28/M 的粗估
```

```python
# flusher.py：每 60s 写 Prometheus textfile 格式
from prometheus_client import CollectorRegistry, Gauge  # 或手写
# 直接写文件给 textfile collector：
# gptcache_hits_total 41823
# gptcache_misses_total 61055
# gptcache_tokens_saved_total 33456000
# gptcache_cost_saved_usd 152.4
```

Prometheus `scrape_configs` 指到 textfile 目录。在 Grafana 看板盯三条：

- `gptcache_hits / (hits+misses)` = **命中率**；
- `gptcache_cost_saved_usd` 的**斜率**（每天省多少）；
- `gptcache_misses` 突增（可能上游换了 prompt 模板，或缓存被污染）。

两条告警就够：

```yaml
- alert: GPTCacheHitRateLow
  expr: rate(gptcache_hits_total[1h]) / (rate(gptcache_hits_total[1h])+rate(gptcache_misses_total[1h])) < 0.15
  for: 6h
  annotations: { summary: "语义缓存命中率 < 15%，阈值可能过严或流量类型变了" }
- alert: GPTCacheSavingsStalled
  expr: increase(gptcache_cost_saved_usd[24h]) < 0
  for: 1d
  annotations: { summary: "24h 内没有产生缓存节省，检查 GPTCache 是否在写库" }
```

## 五、实测规划（成本账）

下表按 **10,000 次 LLM 调用/天、平均 500 in + 300 out tokens、40% 语义命中率** 估算（即每天有 4,000 次调用被缓存"吃掉"，不产生 LLM 费用）。单价取 2025-2026 主流价：

| 路由 | 单价 (in/out 每 M tokens) | 全量日成本 | 全量月成本 | **40% 命中后月省** |
|---|---|---|---|---|
| DeepSeek V3 | $0.14 / $0.28 | ~$1.54 | ~$46 | **~$18/月** |
| GPT-4o-mini | $0.15 / $0.60 | ~$2.55 | ~$76 | **~$30/月** |
| GPT-4o | $2.50 / $10.00 | ~$42.50 | ~$1,275 | **~$510/月** |
| Claude 3.5 Sonnet | $3.00 / $15.00 | ~$60.00 | ~$1,800 | **~$720/月** |

再加上 $5/月的 1C2G VPS 跑 GPTCache + pgvector + Ollama embedding（CPU），**净收益**：

- 走 **DeepSeek/本地** 的：省 $18-30/月 − $5 VPS ≈ 净赚 $13-25/月（对便宜模型，主要价值是**削峰 + 数据不出内网**，省钱是次要）；
- 走 **GPT-4o / Claude** 的：省 $510-720/月 − $5 VPS ≈ **净赚 $500-715/月**，这才是语义缓存真正回本的主战场。

命中率 40% 是"客服/FAQ/文档问答"的典型值。开放创作类命中率 <10%，别指望它；但把"高熵流量"和"低熵流量"分流，低熵那 60% 全上语义缓存，整张账单通常能压掉 **30-50%**。

## 六、五个生产坑

1. **阈值设错 = 答错答案或白花钱。** 默认 0.7 太松，会把"语义相近但意图不同"的问题串到同一个答案上（客服里这是事故）；调到 0.9+ 命中率又骤降到 0。正确姿势：从 0.82 起，跑一周真实流量，用"命中率 vs 误命中率"的混淆矩阵找平衡点，别拍脑袋。
2. **别把高熵流量塞进语义缓存。** 代码生成、开放写作、一次性任务命中率 <10%，且极易近义误命中。这类直接走精确 key 缓存或不缓存，语义缓存只服务 FAQ/文档问答。
3. **换 embedding 模型 = 向量库全废。** `nomic-embed-text` 换 `bge-small-zh` 后维度和空间都变了，旧向量全部失效，pgvector 表要 drop 重建并重新 warm-up，命中率会短暂跌到 0。升级 embedding 模型前留好"冷启动一周"的预期。
4. **缓存污染（cache poisoning）。** LLM 某次幻觉的答案被写进缓存后会被反复下发。对策：给缓存加 TTL（如 24h）+ 只对"确定性"任务开缓存 + 命中答案带来源/置信度标注 + 发现坏答案能手动 `DELETE FROM cache WHERE ...` 失效。
5. **短查询/高基数查询语义相似度无意义。** 形如 "1+1="、订单号、ID 查询，余弦相似度没有信息量，用精确匹配（LiteLLM 自带 cache 或 Redis）更准更快，别用语义缓存。

## 部署清单（一条命令跑起来）

```bash
# 前置：Postgres + pgvector、Ollama + nomic-embed-text、LiteLLM Proxy 已就绪
pip install GPTCache pgvector psycopg2-binary fastapi uvicorn
GPTCACHE_PG_PASS='change-me' \
LITELLM_PROXY=http://127.0.0.1:4000/v1 \
LITELLM_MASTER_KEY=*** \
uvicorn gptcache_service:app --host 127.0.0.1 --port 8100
# 验证
curl -s http://127.0.0.1:8100/v1/answer -H 'Content-Type: application/json' \
  -d '{"query":"Redis 连接池怎么配？","model":"deepseek-chat"}'
```

## 结语

语义缓存不是一个"新模型"，而是**在你已有的 LLM 调用链前面插一层向量检索**：命中就不付钱，没命中才付。它配合 LiteLLM 的 per-key 预算护栏，让一台 $5 的 VPS 同时扮演"省钱的缓存层"和"防超支的成本防火墙"。对走贵模型（GPT-4o/Claude）的团队，这是一笔每月 $500 级别的净收益；对走便宜/本地模型的场景，它的真正价值是削峰、限流、数据不出内网。

先从你的 FAQ/客服那条"低熵"链路试点，盯一周命中率与误命中率，再决定是否推广。
