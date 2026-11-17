---
title: "Self-Hosted LLM Semantic Cache Gateway on a VPS: GPTCache + LiteLLM to Cut 40% of Your API Bill"
date: 2026-11-17T21:30:00+08:00
tags: ["VPS", "LLM", "Semantic Cache", "GPTCache", "LiteLLM", "pgvector", "API Gateway", "Cost Optimization", "Ollama"]
draft: false
image: /images/posts/vps-llm-semantic-cache-gateway/featured.png
description: "Your LLM API bill keeps climbing, but 30-60% of real queries are semantically duplicate. Build a semantic cache gateway on a 1C2G VPS: LiteLLM multi-model aggregation + GPTCache semantic hits + pgvector retrieval + local Ollama embeddings, plus per-key budget guardrails and Prometheus hit-rate / savings monitoring. Plan: at 40% hit rate, GPT-4o routing saves ~$510/mo, local/DeepSeek ~$18-30/mo, net positive after the $5 VPS. 5 production pitfalls included."
categories: ["AI + VPS in Practice"]
aliases: ["/en/post/vps-llm-semantic-cache-gateway/"]
---

# Self-Hosted LLM Semantic Cache Gateway on a VPS: GPTCache + LiteLLM to Cut 40% of Your API Bill

If your team is already calling LLM APIs, the bill is almost certainly climbing month over month. Very few teams have actually done the one thing that would expose the waste: **measure how many of the last 30 days of prompts are semantically duplicate.**

In customer support bots, internal FAQ, code Q&A, and doc summarization, that number is typically **30-60%**. Users rephrase the same question, they tweak "how do I configure a Redis pool" into "Redis pool config?", they follow up on a previous answer — every one of these hits the same model for an almost-identical response, and you pay full price each time.

**Semantic caching** attacks exactly this: embed the question into a vector, look up "have I answered something this similar before," and if so serve the cached answer without touching the LLM. It's a different thing from a Redis/in-memory **exact-key cache** — exact cache needs byte-identical prompts; semantic cache tolerates "the same question, rephrased."

The whole thing fits on a **1C2G VPS**, all open-source, roughly **$5/mo** to run, and the LLM calls you skip can save **~$500/mo** on expensive models like GPT-4o. Below is the full architecture, deploy scripts, tuning, monitoring, and 5 hard-won production pitfalls.

> This post assumes you've read the [LiteLLM gateway deploy](/en/post/litellm-proxy-deployment-vps/) and [pgvector vector DB](/en/post/vps-pgvector-selfhosted-vector-database/). It only covers "how to slot a semantic cache layer in front."

## Architecture at a glance

```
   Your app / support bot / internal tool
                │  OpenAI-compatible API
                ▼
        ┌─────────────────┐
        │  GPTCache GW    │  1. embedding (local Ollama, CPU)
        │  (FastAPI shell)│  2. pgvector cosine similarity
        │                  │  3. similarity ≥ θ → cached answer (zero LLM cost)
        └────────┬─────────┘
        miss     │
                ▼
        ┌─────────────────┐
        │  LiteLLM Proxy  │  multi-model aggregation + routing + per-key budgets + rate limits
        │  (:4000)        │  → OpenAI / DeepSeek / local Ollama / Claude…
        └─────────────────┘
                │
        hit/miss counts, tokens, estimated savings
                ▼
        Prometheus textfile (hit rate, $ saved, tokens saved) → Grafana + alerts
```

Three decoupled components:

- **GPTCache**: the semantic-cache brain — embed, retrieve, store/retrieve cached answers.
- **LiteLLM Proxy**: funnels "the calls you actually pay for" through one OpenAI-compatible entry point, adding per-key budget caps, rate limits, and multi-model routing. It's your **cost firewall**.
- **pgvector**: the vector store. GPTCache writes embeddings + answers here and retrieves by cosine similarity.
- **Local Ollama embedding** (`nomic-embed-text`, ~55MB, CPU-friendly): keeps even the embedding step in-house, so **you don't even pay for the embedding API**, and no data leaves the VPS.

## 1. How semantic caching works — and when not to use it

GPTCache's hit logic:

1. Take the new question `q`, compute `v(q)` with the embedding model;
2. Find the most similar historical question `q'` in pgvector, get a score;
3. `score ≥ θ` → "hit," return the cached `answer(q')`;
4. Otherwise miss: call the real LLM, get the answer, write `(v(q), q, answer)` back to pgvector.

**The key knob is the threshold θ.** GPTCache defaults are loose (~0.7) — great for saving money, dangerous for correctness: two questions at cosine 0.7 can absolutely not share an answer in support/medical/compliance contexts. So:

- **Deterministic, reusable** tasks (FAQ, product-doc Q&A, internal runbooks): θ ≈ **0.80-0.85** for the highest hit rate;
- **Open-ended creative / code generation / one-shot tasks**: hit rate is naturally <10%, and near-synonym-but-different-intent inputs cause cross-answers. Route these **past semantic cache** (or fall back to exact-key cache).

The rule: **semantic cache is for saving money on "high-frequency, low-entropy, reusable-answer" traffic — not for all traffic.**

## 2. Deployment: pgvector + GPTCache + local embeddings

### 1. Install pgvector and create the DB

```bash
sudo apt update && sudo apt install -y postgresql postgresql-contrib
sudo -u postgres psql -c "CREATE USER gptcache WITH PASSWORD 'change-me';"
sudo -u postgres psql -c "CREATE DATABASE gptcache OWNER gptcache;"
sudo -u postgres psql -d gptcache -c "CREATE EXTENSION vector;"
# Vector table (dim=768 for nomic-embed-text)
sudo -u postgres psql -d gptcache -c "
CREATE TABLE IF NOT EXISTS cache (
  id SERIAL PRIMARY KEY,
  embedding vector(768),
  query TEXT,
  response TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);"
```

> Want less memory? SQLite + `sqlite-vec` works, but pgvector's HNSW index is far more stable past ~100k vectors, and you probably already run Postgres.

### 2. Pull a local embedding model (Ollama, CPU is fine)

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull nomic-embed-text   # ~55MB, 768-dim, ~512MB RAM on CPU
```

`nomic-embed-text` is the semantic-cache workhorse: small, fast, good cosine discrimination, runs on CPU, no GPU. For Chinese, swap in `bge-small-zh` (similar size class).

### 3. GPTCache service (a thin FastAPI shell)

> GPTCache's API differs across versions (0.1.x / 0.2.x); below targets 0.1.x. If a field name doesn't match, run `pip show GPTCache` and check the official docs for your version.

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
    cache_data="in_memory",       # hot layer, cold data falls back to pgvector
    vector_data=vector_data,
    embedding=embedding,
).init_cache()
# Hit threshold: start at 0.82 for support/FAQ
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
    if cache.check(q):                 # semantic hit?
        return {"hit": True,  "answer": cache.get(q), "model": model}
    a = llm_call(q, model)            # miss → real LLM call
    cache.set(q, a)                   # write back to vector store
    return {"hit": False, "answer": a, "model": model}

from fastapi import FastAPI
app = FastAPI()
@app.post("/v1/answer")
def endpoint(body: dict):
    return answer(body["query"], body.get("model", "deepseek-chat"))
```

Run it:

```bash
pip install GPTCache pgvector psycopg2-binary fastapi uvicorn
GPTCACHE_PG_PASS='change-me' LITELLM_PROXY=http://127.0.0.1:4000/v1 \
LITELLM_MASTER_KEY=*** uvicorn gptcache_service:app --host 127.0.0.1 --port 8100
```

## 3. LiteLLM Proxy: funnel paid calls, add budget guardrails

Semantic cache cuts *how often* you call; LiteLLM cuts *how much you can spend per caller*. The [LiteLLM deploy post](/en/post/litellm-proxy-deployment-vps/) covers the basics; here's the **budget guardrail** piece that turns the cache gateway into a **cost firewall**.

`config.yaml`:

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
  max_budget: 100.0            # platform-wide hard cap in $
  tpm_limit: 120000
  num_retries: 2
litellm_settings:
  cache: false                # we don't rely on exact cache; semantic cache is GPTCache's job
```

Give each service a **budget-capped key** — an independent power meter per caller:

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

`max_budget_lock: true` means that key stops at $5 — one runaway bot can't burn the platform's $100 budget overnight.

## 4. Monitoring: hit rate and "how much you actually saved"

The biggest semantic-cache risk is "feels like it's saving money, but it isn't." Add a Prometheus textfile sidecar; the GPTCache gateway increments a counter per request, and an exporter flushes periodically:

```python
# in gptcache_service (simplified)
STATS = {"hits":0, "misses":0, "tokens_saved":0, "cost_saved_usd":0.0, "last_flush":0}

def record(hit: bool, q: str, a: str):
    if hit:
        STATS["hits"] += 1
        toks = len(q)//2 + len(a)//2
        STATS["tokens_saved"] += toks
        STATS["cost_saved_usd"] += toks/1e6*0.28/2   # rough, using DeepSeek V3 $0.28/M output
```

```python
# flusher.py: every 60s, write Prometheus textfile format
# gptcache_hits_total 41823
# gptcache_misses_total 61055
# gptcache_tokens_saved_total 33456000
# gptcache_cost_saved_usd 152.4
```

Point Prometheus `scrape_configs` at the textfile dir. Track three things in Grafana:

- `gptcache_hits / (hits+misses)` = **hit rate**;
- slope of `gptcache_cost_saved_usd` (daily $ saved);
- spikes in `gptcache_misses` (upstream prompt template changed, or cache got poisoned).

Two alerts are enough:

```yaml
- alert: GPTCacheHitRateLow
  expr: rate(gptcache_hits_total[1h]) / (rate(gptcache_hits_total[1h])+rate(gptcache_misses_total[1h])) < 0.15
  for: 6h
  annotations: { summary: "Semantic cache hit rate < 15%; threshold too strict or traffic type shifted" }
- alert: GPTCacheSavingsStalled
  expr: increase(gptcache_cost_saved_usd[24h]) < 0
  for: 1d
  annotations: { summary: "No cache savings in 24h; check GPTCache is writing to the DB" }
```

## 5. Cost model (planning numbers)

Assume **10,000 LLM calls/day, avg 500 in + 300 out tokens, 40% semantic hit rate** (i.e., 4,000 calls/day absorbed by cache, zero LLM cost). Prices are mainstream 2025-2026 rates:

| Routing | Price (in/out per M tokens) | Full daily cost | Full monthly | **Saved @40% hit** |
|---|---|---|---|---|
| DeepSeek V3 | $0.14 / $0.28 | ~$1.54 | ~$46 | **~$18/mo** |
| GPT-4o-mini | $0.15 / $0.60 | ~$2.55 | ~$76 | **~$30/mo** |
| GPT-4o | $2.50 / $10.00 | ~$42.50 | ~$1,275 | **~$510/mo** |
| Claude 3.5 Sonnet | $3.00 / $15.00 | ~$60.00 | ~$1,800 | **~$720/mo** |

Add the $5/mo 1C2G VPS running GPTCache + pgvector + Ollama embedding (CPU). **Net**:

- **DeepSeek/local** routing: $18-30/mo saved − $5 VPS ≈ **net +$13-25/mo** (with cheap models the real win is peak-shaving + data staying in-house; cash savings are secondary);
- **GPT-4o / Claude** routing: $510-720/mo saved − $5 VPS ≈ **net +$500-715/mo** — this is where semantic cache actually pays off.

A 40% hit rate is typical for support/FAQ/doc-QA. Open-ended creative traffic is <10%; don't count on it. But by splitting "high-entropy" from "low-entropy" traffic and caching all of the low-entropy 60%, you usually knock **30-50%** off the whole bill.

## 6. Five production pitfalls

1. **Wrong threshold = wrong answers or wasted money.** Default 0.7 is loose — it cross-answers "similar but different intent" questions (an incident in support). At 0.9+ the hit rate collapses to 0. Do this: start at 0.82, run a week of real traffic, and find the balance on a "hit rate vs. false-hit rate" confusion matrix, don't guess.
2. **Don't pipe high-entropy traffic through semantic cache.** Code generation, open-ended writing, one-shots hit <10% and are prone to near-synonym false hits. Route those to exact-key cache or no cache; keep semantic cache for FAQ/docs.
3. **Swapping the embedding model invalidates the whole store.** Going `nomic-embed-text` → `bge-small-zh` changes dimensions and space; every old vector is dead. You must drop/rebuild the pgvector table and re-warm; expect hit rate to drop to 0 for a week. Plan for the cold-start before any embedding upgrade.
4. **Cache poisoning.** One hallucinated answer, once written, gets re-served forever. Mitigations: TTL on the cache (e.g., 24h) + only enable caching for "deterministic" tasks + tag cached answers with source/confidence + be able to `DELETE FROM cache WHERE ...` to kill a bad entry.
5. **Short / high-cardinality queries have no meaningful semantic similarity.** "1+1=", order numbers, IDs — cosine similarity is useless there. Use exact match (LiteLLM's built-in cache or Redis), which is faster and more correct.

## Deploy checklist (one command)

```bash
# Prereqs: Postgres + pgvector, Ollama + nomic-embed-text, LiteLLM Proxy already up
pip install GPTCache pgvector psycopg2-binary fastapi uvicorn
GPTCACHE_PG_PASS='change-me' \
LITELLM_PROXY=http://127.0.0.1:4000/v1 \
LITELLM_MASTER_KEY=*** \
uvicorn gptcache_service:app --host 127.0.0.1 --port 8100
# Verify
curl -s http://127.0.0.1:8100/v1/answer -H 'Content-Type: application/json' \
  -d '{"query":"How do I configure a Redis pool?","model":"deepseek-chat"}'
```

## Wrap-up

Semantic caching isn't a "new model" — it's **a vector-retrieval layer slotted in front of your existing LLM calls**: on a hit you pay nothing, on a miss you pay. Paired with LiteLLM's per-key budget guardrails, a single $5 VPS plays both "the money-saving cache layer" and "the overspend firewall." For teams on expensive models (GPT-4o/Claude) that's a **$500+/mo net win**; on cheap/local models the real value is peak-shaving, rate-limiting, and keeping data in-house.

Start with your FAQ/support "low-entropy" lane, watch hit rate vs. false-hit rate for a week, then decide whether to roll it out.
