---
title: "AI-Driven VPS Chaos Engineering: LLM-Orchestrated Fault Injection to Verify System Resilience"
description: "Production is too risky to test, staging is too boring? This guide shows how to use a local LLM to auto-design fault scenarios, orchestrate chaos experiments, analyze causal chains, and generate resilience reports — so your VPS services are battle-tested before the real failures arrive."
date: 2026-09-28T20:00:00+08:00
lastmod: 2026-09-28T20:00:00+08:00
slug: "ai-vps-chaos-engineering-resilience-testing"
tags: ["AI", "VPS", "Chaos Engineering", "AIOps", "LLM", "Docker", "Kubernetes", "SRE", "Fault Injection", "Resilience"]
categories: ["AI + VPS"]
image: /images/posts/ai-vps-chaos-engineering-resilience-testing/featured.png
draft: false
---

## Introduction: Does Your VPS Service Actually "Hold Up"?

Many developers maintain a Docker-containerized VPS stack: API, database, cache, message queue, cron jobs... Deployment looks smooth, dashboards look green. But there's always that nagging doubt in the back of your head:

- If the database primary/replica failover kicks in, will the API service crash? Are retry policies sufficient?
- If a node's CPU pegs at 100%, will requests degrade gracefully or cascade into a full meltdown?
- If a network partition occurs, can the service self-recover within 30 seconds?
- Are your backups actually restorable? When was the last restore drill?

**Chaos Engineering** is the methodology that answers these questions: proactively inject faults in a controlled environment, observe system behavior, find fragilities, fix them, then inject harsher faults. Netflix's Chaos Monkey and CNCF's Litmus are the flagship projects in this space.

But traditional chaos engineering has a high entry barrier: **experiment design is manual**. You need to understand the service topology, identify critical dependencies, design reasonable injection parameters, write experiment scripts, and analyze results. For small teams, this is nearly unsustainable.

This guide introduces an **AI-driven chaos engineering system** — a local LLM (Ollama + Qwen2.5) handles experiment design, parameter generation, execution orchestration, causal analysis, and resilience reporting. All data stays on your VPS; no external API calls.

---

## 1. Why Use AI for Chaos Engineering?

### Three Pain Points of Traditional Chaos Engineering

| Pain Point | Description |
|-----------|-------------|
| Experience-based design | You don't know where to inject, or how hard — it's all SRE intuition |
| High parameter-tuning cost | Combinations of timeouts, retry counts, replica counts explode combinatorially |
| Fragmented analysis | Fault logs are scattered across multiple systems; root-cause analysis requires cross-platform stitching |

### Three Capabilities AI Brings

1. **Topology awareness**: The LLM reads the service registry, Docker network config, and K8s manifests to infer dependencies
2. **Scenario generation**: Based on topology + business priority, the LLM auto-designs fault scenarios (e.g., "inject 20s pg-primary outage + 5s replica lag")
3. **Causal-chain reasoning**: After the fault, the LLM reads metrics + logs + traces, infers the causal chain, and outputs remediation advice

---

## 2. System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    VPS Host (Ubuntu 24.04)                     │
│                                                                 │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐    │
│  │ Ollama   │──▶│ Experiment│──▶│ Fault    │──▶│ Observ-  │    │
│  │ Qwen2.5  │   │Orchestrator│ │ Injector  │   │ability   │    │
│  └──────────┘   └──────────┘   └──────────┘   │ Collector │    │
│       ▲                ▲                │       └──────────┘    │
│       │                │                ▼                ▼     │
│       │           ┌──────────┐      ┌──────────┐   ┌──────────┐ │
│       │           │ Topology │      │Prometheus│   │  Loki +  │ │
│       │           │ Analyzer │      │  + Grafana│  │  Tempo   │ │
│       │           └──────────┘      └──────────┘   └──────────┘ │
│       ▼                │                                         │
│  ┌──────────┐   ┌──────────┐                                    │
│  │Resilience│   │Report    │──▶ Telegram push                   │
│  │ Scorer  │   │ Generator│                                    │
│  └──────────┘   └──────────┘                                    │
└─────────────────────────────────────────────────────────────────┘
```

Five core modules:

1. **Topology Analyzer**: scans Docker network / K8s manifests / service registry, outputs a service dependency graph
2. **Experiment Orchestrator**: calls the LLM to generate scenario JSON — target, fault type, parameters, duration, circuit breaker
3. **Fault Injection Executor**: runs the LLM-generated injection scripts (iptables, kill, CPU stress, network delay, disk fill)
4. **Observability Collector**: captures Prometheus metrics + Loki logs + Tempo traces, time-aligned
5. **Resilience Scorer**: LLM scores "SLA attainment / recovery time / blast radius" on a 0–100 scale + remediation advice

---

## 3. Key Implementations

### 3.1 Topology Analyzer

LLM input:
- `docker network ls` output
- K8s `kubectl get svc,deploy -o json`
- Service registry export (Consul / Nacos)
- Recent traffic matrix (Istio / Envoy access logs)

LLM output (JSON):

```json
{
  "services": [
    {"name": "api-gateway", "image": "nginx:1.27", "ports": [80, 443]},
    {"name": "order-api", "image": "myorg/order:2.3", "depends_on": ["user-api", "pg-primary"]},
    {"name": "pg-primary", "image": "postgres:16", "role": "primary"},
    {"name": "pg-replica", "image": "postgres:16", "role": "replica"}
  ],
  "critical_paths": [
    ["client", "api-gateway", "order-api", "user-api"],
    ["client", "api-gateway", "order-api", "pg-primary"]
  ],
  "sla_targets": {
    "order-api.p99_latency": "200ms",
    "order-api.error_rate": "0.1%"
  }
}
```

### 3.2 Scenario Generation

Prompt example:

```
You are an SRE chaos engineer. Given the following topology and SLO targets,
design 5 fault injection scenarios covering:
- DB primary/replica failover
- Network partition (api-gateway ↔ order-api)
- Node CPU saturation (simulate memory leak)
- Disk fill (trigger I/O stall)
- Cascading timeout meltdown

Each scenario outputs JSON: {scenario_id, target, fault_type,
parameters, duration, circuit_breaker, expected_behavior}
Expected behavior must be verifiable by observability metrics.
```

Sample LLM output:

```json
{
  "scenario_id": "chaos-001",
  "target": "pg-primary",
  "fault_type": "kill_process",
  "parameters": {"delay_seconds": 20, "auto_failover": true},
  "duration": "60s",
  "circuit_breaker": {"metric": "pg-replica.lag_bytes", "threshold": "10MB", "action": "abort"},
  "expected_behavior": "order-api.p99_latency < 500ms, error_rate < 1%"
}
```

### 3.3 Fault Injection Executor

Six injector types (Python scripts):

| Injector | Implementation | Typical Use |
|----------|----------------|-------------|
| Process | `kill -STOP/-KILL` container PID | Simulate process crash |
| Network | `iptables` DROP/REWRITE + `tc netem` delay | Simulate partition / latency |
| CPU | `stress-ng` or `cgroup cpu.max` limit | Simulate CPU saturation |
| Memory | `cgroup memory.max` down + OOM | Simulate memory leak |
| Disk | `truncate` fill + write loop | Simulate I/O stall |
| Time | `libfaketime` or NTP offset | Simulate cert expiry, clock skew |

All injectors run inside `docker exec` / `kubectl exec` so the host stays untouched.

### 3.4 Observability Collector

Within the fault window [t0, t0+dur]:

```bash
# Prometheus metrics
promtool query "increase(http_requests_total{job=\"order-api\"}[5m])"

# Loki logs
logcli query '{job="order-api"} |~ "error|timeout"' --time-start=t0

# Tempo traces
tempo-cli traces --service order-api --since t0
```

The three streams are time-stamped, aligned, and packaged into an observation bundle for the LLM.

### 3.5 Resilience Scoring & Reporting

LLM scoring dimensions:

| Dimension | Weight | Description |
|-----------|--------|-------------|
| SLA attainment | 40% | Was p99 / error_rate in bounds during the fault? |
| Recovery time | 30% | Time from injection to metrics normalization |
| Cascade impact | 20% | Did the fault spread to non-target services? |
| Circuit breaker | 10% | Did breakers trigger and stop the meltdown? |

Weighted 0–100 score. Report template (Markdown):

```markdown
# Chaos Report #chaos-001

## Scenario
- Target: pg-primary
- Fault: kill_process (20s delay + auto failover)
- Duration: 60s

## Results
- SLA attainment: 92% ✅
- Recovery time: 42s (target < 30s ❌)
- Cascade: order-api.p99 jumped 80ms → 620ms ⚠️
- Circuit breaker: not triggered ❌

## Score: 74 / 100

## Root Cause (LLM inference)
pg-replica sync lag 5s. After failover, read traffic did not shift
to the replica; order-api's read pool kept hitting the old primary
connection, causing timeouts.

## Remediation
1. Add primary/replica awareness to order-api datasource (watch pg_is_in_recovery)
2. Default read traffic to replica; primary is write-only
3. Lower breaker threshold from error_rate > 5% to > 2%
```

Reports push to Telegram, CC the ops channel.

---

## 4. Deployment (VPS-tested)

Full end-to-end on a 4C8G VPS (Ubuntu 24.04):

```bash
# 1. Install dependencies
sudo apt install -y docker docker-compose iptables-persistent stress-ng

# 2. Deploy Ollama
docker run -d --name ollama -v ollama:/root/.ollama -p 11434:11434 ollama/ollama
docker exec -it ollama ollama pull qwen2.5:7b

# 3. Start the chaos suite
git clone https://git.example.com/myorg/chaos-suite.git
cd chaos-suite
docker compose up -d
# Includes: topology-analyzer, experiment-orchestrator,
#          injection-executor, observability-collector,
#          resilience-scorer, report-generator

# 4. Run the first batch
curl -X POST localhost:8080/api/v1/experiments/run \
  -H "Content-Type: application/json" \
  -d '{"topology_source": "docker", "scenarios": 5}'

# 5. Inspect reports
ls /opt/chaos-suite/reports/
# chaos-001.md, chaos-002.md, ...
```

Cost estimate (Ollama Qwen2.5:7b, local inference):

- Per experiment design: ~2s
- Per resilience score: ~5s
- 7 days × 5 scenarios: < 5 min of inference, zero API cost

---

## 5. Practical Advice & Pitfalls

### Do

- **Start with low-risk scenarios**: non-critical paths first (logging, monitoring collectors), validate the toolchain before touching the database
- **Circuit breakers are mandatory**: every scenario must have one, so the experiment itself can't take down production
- **Time-window management**: schedule injections in off-peak hours (03:00–05:00)
- **Auto-rollback**: snapshot cgroup / iptables state before injection; recover automatically on failure

### Watch out for

| Pitfall | Fix |
|---------|-----|
| LLM generates aggressive parameters | Prompt constraint: "duration ≤ 60s, parameters within safe bounds" |
| Timestamp drift across observability stacks | Strict NTP sync; align with Prometheus `timestamp()` |
| Injection leaks to host | All injectors run via `docker exec` inside the target container |
| Reports nobody reads | Only push failing scenarios (score < 80); silent on pass |

---

## 6. Extensions

1. **CI integration**: run a chaos batch in Gitea Actions before every PR merge
2. **Multi-node**: extend to K3s cluster-level chaos (Litmus + LLM hybrid)
3. **Knowledge sink**: historical results into a RAG knowledge base; the LLM references them when designing the next scenario
4. **Compliance mapping**: auto-map results to SLO reports for audit

---

## Conclusion

Chaos engineering isn't "make the system break" — it's **break it once before the real breakage happens**. AI turns this from a "SRE-only skill" into an "automated daily action": your VPS services have already done a hundred dress rehearsals before the real failure arrives.

Next article: AI-driven VPS capacity planning & predictive autoscaling. Stay tuned.

---

*All code samples in this guide are available under `chaos-suite/` in the repo.*
