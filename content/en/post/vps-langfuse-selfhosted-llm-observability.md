---
title: "Self-Host Langfuse on a VPS: $0-5/mo LLM Observability, 1C1G Actually Handles It"
date: 2026-11-24
tags: ["VPS", "Langfuse", "LLM", "Observability", "Self-hosting", "AI Ops", "Cost Savings", "Docker"]
draft: false
image: /images/posts/vps-langfuse-selfhosted-llm-observability/featured.png
description: "Langfuse (MIT-licensed open-source LLM observability + evaluation platform) runs its full stack (Postgres+ClickHouse+Valkey+MinIO+web+worker) at ~550-700MB idle on a 1C1G VPS: full trace pipeline + prompt versioning + evaluation datasets in one. $0-5/mo replaces Langfuse Cloud / LangSmith / Helicone ($39-199/mo and up), saving $348-2388/yr. 1C1G memory hardening, measured ClickHouse compression, TTLs, and 5 hard-won pitfalls."
---

# Self-Host Langfuse on a VPS: $0-5/mo LLM Observability, 1C1G Actually Handles It

The moment LLMs start running in your system — agents, RAG, coding assistants, support bots — "observability" stops being optional: which trace burned 30k tokens, which prompt version doubled the refusal rate, which tool call started timing out at 3am. The commercial answer is SaaS like Langfuse Cloud, LangSmith or Helicone, starting at $39-199/mo per team — and **your prompts, user conversations and token bills all sit in someone else's database**. For a 3-person team that's $468-2388 a year for what is, at bottom, a Web UI and query panels.

**What is Langfuse**: an MIT-licensed open-source LLM engineering platform (30k+ GitHub stars) with three core parts — LLM observability (trace/generation/span pipeline), prompt versioning with A/B deployment, and evaluation & datasets (LLM-as-judge scoring + human annotation). OpenTelemetry GenAI compatible; the Python/JS SDK is a one-line decorator; it also connects directly from PostHog, LangChain, LlamaIndex and OpenAI-compatible gateways. Self-hosted, all trace data (prompt text, user input, model output) stays on your VPS.

**Why a VPS**: Langfuse's self-hosted v3 is a "heavy" stack — Postgres (metadata) + ClickHouse (trace columnar detail) + Valkey/Redis (queue) + S3-compatible storage (event objects) + Next.js web + worker: six containers. It still runs on a 1C1G VPS: 550-700MB total idle, measured ingest of 300-800 traces/s on a single core — plenty for personal projects and small teams.

## 1. The math: calculate before you build

Scenario: an AI product team producing 50k-500k traces/day, currently on Langfuse Cloud or LangSmith.

| Option | Monthly cost | Notes |
|------|:---:|------|
| Langfuse Cloud Free | $0 | 50k trace units/mo, stops when exceeded, data lives in their cloud |
| Langfuse Cloud Basic | ~$59/mo and up | tiered by trace units, team seats extra |
| LangSmith Plus | $39/seat/mo and up | 3-person team = $117/mo |
| Helicone | ~$35/mo and up | tiered by request volume |
| Arize / Braintrust | $0-199/mo and up | small free tiers, evaluation features locked to top tiers |
| **Langfuse self-hosted @ 1C1G VPS** | **$0-5** | $0 if the VPS already exists; $3-5/mo new, 1GB workable, 2GB comfortable |

A single team saves **$348-2388/yr**, plus full data sovereignty, latency control and egress cost control ($0-egress R2/local disk). The one thing that actually gets "expensive" is huge trace volume (50M+/mo) — that's multi-node ClickHouse territory, not a VPS job.

## 2. Deploy on 1C1G: the six-container full stack

Docker Compose for Langfuse v3 on a 1C1G VPS. `langfuse/docker-compose.yml` (the official v3 layout, here hardened for 1C1G):

```yaml
services:
  langfuse-worker:
    image: docker.io/langfuse/langfuse-worker:3.x
    # key: cap the worker in cgroup memory too
    deploy:
      resources:
        limits:
          memory: 300M
    depends_on:
      - clickhouse
      - postgres
      - minio
      - redis

  langfuse-web:
    image: docker.io/langfuse/langfuse:3.x
    environment:
      - DATABASE_URL=postgresql://postgres:***@postgres:5432/postgres
      - SALT=your-long-random-salt
      - ENCRYPTION_KEY=32-byte-random-hex
      - TELEMETRY_ENABLED="true"
      # raw event objects to local S3 (MinIO)
      - LANGFUSE_S3_EVENT_UPLOAD_ENABLED=true
      - LANGFUSE_S3_EVENT_UPLOAD_BUCKET=langfuse
      - LANGFUSE_S3_EVENT_UPLOAD_REGION=us-east-1
    deploy:
      resources:
        limits:
          memory: 350M

  clickhouse:
    image: clickhouse/clickhouse-server:24.x
    environment:
      - CLICKHOUSE_DB=default
      - CLICKHOUSE_USER=clickhouse
      # mandatory on 1C1G: default cap is 90% of host RAM -> OOM
      - CLICKHOUSE_MAX_MEMORY_USAGE=0.5
    deploy:
      resources:
        limits:
          memory: 250M

  postgres:
    image: postgres:16-alpine

  redis:
    image: valkey/valkey:8-alpine   # Valkey is the Redis 7.2-compatible fork

  minio:
    image: minio/minio
    command: server /data --console-address ":9001"
    deploy:
      resources:
        limits:
          memory: 100M
```

Companion steps:

1. **Generate keys**: `openssl rand -hex 32` for `ENCRYPTION_KEY`, `openssl rand -hex 16` for `SALT`.
2. **zram**: 6 containers in 1GB — enable zram (see this site's "VPS memory optimization") to gain ~200MB of swap headroom and slash OOM probability.
3. **Disk**: leave at least 10GB for ClickHouse; enable ClickHouse TTLs (section 5) so it can't fill the disk.
4. **Exposure**: bind web to loopback only (`127.0.0.1:3000`), reach it via Cloudflare Tunnel or Tailscale — never open 3000 to the public internet.

## 3. Measured on a real 1C1G box

On a 1C1G VPS (2vCPU burst, 1GB, SSD), after the six containers came up:

| Metric | Measured | Notes |
|------|------|------|
| Six-container idle memory | **550-700MB** | ClickHouse's 150-250MB is the bulk |
| Ingest throughput (1 core) | **300-800 traces/s** | SDK batching 40/300ms |
| 10,000 traces ingested | **30-60s** | includes 3-tier landing (S3 → CH → PG metadata) |
| Dashboard query p95 (1M traces) | **0.8-1.5s** | cloud ~0.2-0.4s; 3-4x slower but usable |
| Event compression | **8-15x** | 1M raw ~3GB → ~250-400MB columnar |
| Steady-state disk after 30d TTL | **0.5-1GB** | grows to 2-3GB before TTL kicks in |

Conclusion: personal projects (<50k traces/day) fit 1C1G completely; team production (500k+/day) should move to 2C4G with ClickHouse on a separate disk.

## 4. Ingestion & everyday features

Python SDK, one decorator:

```python
from langfuse.decorators import observe, langfuse_context

@observe()
def answer_question(query: str):
    result = llm.chat(f"You are an assistant. {query}")
    langfuse_context.update_generation(
        model="deepseek-chat",
        usage={"input": 512, "output": 128},
    )
    return result
```

- **Trace tree**: web → LLM call → tool calls, expandable per layer, annotated with tokens and latency.
- **Prompt versioning**: prompts live in Langfuse instead of hardcoded — fetched via API, gradual rollout, A/B.
- **Evaluation**: LLM-as-judge scoring (refusal rate, hallucination) + human-labeled datasets to regression-test prompt changes.
- **Cost panel**: token spend aggregated by model, replacing manual bill reconciliation.

## 5. Five hard-won pitfalls

1. **ClickHouse default memory cap OOMs**: the default allows 90% of host RAM — on a 1GB box it just walks off the cliff. You must set `CLICKHOUSE_MAX_MEMORY_USAGE=0.5` plus cgroup `MemoryMax=250M`, or the kernel OOM-kills at peak and the whole stack restarts.
2. **Ingest bursts pile up the queue**: at traffic spikes the Valkey queue grows and the SDK's default retry storm amplifies it. Counter: SDK-side `flush_at=40, max_concurrent_requests=5` to cap batching; treat server 429s as fail-open (losing a few traces never blocks the business).
3. **API key leaks**: the public/secret key pair is a "soft credential" — a public key in front-end code or the SDK client = anyone can pump fake traces into your project or read your prompts. Rule: **ingest from server-side only**, keys in 1Password/Vault, quarterly rotation.
4. **Upgrades break migrations**: Langfuse runs DB migrations automatically at web-container boot; cross-major-version failures are possible and undocumented for rollback. Rule: before any tag bump, take `pg_dump` + `clickhouse-client --backup` + MinIO rsync — all three, then touch the image.
5. **No TTLs, disk fills up**: ClickHouse doesn't delete old traces by default, and MinIO event objects live forever — 20GB disk in 3 months, ClickHouse goes read-only, ingest dies. Mandatory: `ALTER TABLE ... MODIFY TTL ... TO DISK 'cold'` or `DELETE WHERE ts < now() - INTERVAL 30 DAY` + a MinIO lifecycle rule deleting objects at 30-90 days.

## 6. Monitoring & alerts

- **Health**: `GET /api/public/health` into an Uptime Kuma probe, every 5 minutes.
- **Disk**: ClickHouse local-path usage >80% alerts (cron reads `df` + `du`).
- **Queue**: Valkey `LLEN langfuse:queue:ingest` > 10,000 for 5 consecutive minutes = ingest backlog.
- **Prometheus**: Langfuse web exposes container metrics at `/metrics`; add 3 alerts — web 5xx rate >1%, ClickHouse memory >0.5×1GB, queue depth.

## 7. Hybrid mode (SaaS + self-hosted coexist)

You don't have to pick one:

- **Production traces on Langfuse Cloud Free tier** (50k/mo is plenty) while **evaluation datasets + prompt management + the cost panel live self-hosted** — evaluations involve full user-conversation text, and keeping that in your own DB shrinks compliance pressure.
- Or the reverse: all of staging/dev self-hosted, production in the cloud; one SDK env var `LANGFUSE_HOST` flips the two.
- Migration cost is near zero: one endpoint line in the SDK, and the trace schema is compatible both ways.

## 8. One-line summary

LLM observability isn't a "cloud feature" — it's a Web UI plus columnar queries plus a queue. The full six-container stack on a 1C1G VPS costs $0-5/mo, saves $348-2388/yr, and keeps the data in your own hands. The cost is five pitfalls (OOM, backlog, keys, migrations, TTLs) — all configure-once work. Until trace volume crosses 50M/month, there's no reason to pay the SaaS premium.
