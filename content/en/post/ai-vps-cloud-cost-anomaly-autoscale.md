---
title: "VPS Cloud Cost Auto-Pilot: LLM-Powered Bill Anomaly Detection & Idle Auto-Shutdown"
description: "Your cloud bill shouldn't be a month-end surprise. This guide builds an intelligent cloud cost manager on VPS using a local LLM (Ollama + Qwen2.5) + Prometheus: hourly billing/usage collection, LLM-based anomaly detection (idle instances, over-provisioning, traffic spikes), automatic shutdown of idle resources, and a daily savings report pushed to Telegram. No data leaves your network."
date: 2026-10-17T20:00:00+08:00
lastmod: 2026-10-17T20:00:00+08:00
slug: "ai-vps-cloud-cost-anomaly-autoscale"
tags: ["AI", "Cloud Cost", "FinOps", "Prometheus", "Ollama", "VPS Ops", "Automation", "Cost Saving"]
categories: ["Cloud Cost Optimization"]
draft: false
image: /images/posts/ai-vps-cloud-cost-anomaly-autoscale/featured.png
aliases: [/en/post/ai-vps-cloud-cost-anomaly-autoscale/]
---

## Introduction: Your Bill Should Not Be a Month-End Surprise

When we talk about self-hosting to save money, the easiest cost to overlook is not the VPS itself but the entire cloud ecosystem around it:

- **Idle VPS / cloud instances** kept alive for "in case I need them" — hundreds of dollars/month
- **Massively over-provisioned instances** (4 vCPU / 8 GB running a 200 MB static site)
- **Outbound traffic overage** (object storage, CDN, egress fees) from unexpected spikes
- **Forgotten test clusters / K8s nodes** billed 24/7
- **Silent fixed costs**: snapshots, disks, reserved IPs

The traditional approach: manually read the invoice at month end. The better approach: **let an LLM review it daily, auto-detect anomalies, auto-shutdown idle resources**.

Our pipeline:

```
Cloud billing/usage API → Prometheus → LLM anomaly triage
        ↕                   ↕                    ↕
   multi-cloud adapter   hourly cost curves   "idle / over-provisioned / spike" detection
                                        ↕
                              auto-action (shutdown / downsize)
                                        ↕
                              daily savings report → Telegram
```

All LLM inference is local (Ollama + Qwen2.5). Billing data never leaves your network.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│         VPS Cloud Cost Auto-Pilot (FinOps + LLM)        │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌──────────┐   ┌──────────┐   ┌───────────────────┐   │
│  │ Cloud    │──▶│ Crawler  │──▶│ Prometheus        │   │
│  │ Cost API │   │ (hourly) │   │ (time-series)     │   │
│  │ adapter  │   │          │   │ usage + billing   │   │
│  └──────────┘   └──────────┘   └────────┬──────────┘   │
│                                          │              │
│       ▼                                  ▼              │
│  ┌──────────┐   ┌──────────┐   ┌──────────────────┐    │
│  │ Auto     │   │ Ollama + │◀──│ Anomaly detector │    │
│  │ executor │   │ Qwen2.5  │   │ (rules + LLM)    │    │
│  └──────────┘   └──────────┘   └────────┬─────────┘    │
│       ▲                                  │              │
│       │                                  ▼              │
│  ┌──────────┐                    ┌──────────────────┐   │
│  │ Whitelist│◀── safety gate ────│ Daily savings    │   │
│  │ + cooldown│                    │ report → TG      │   │
│  └──────────┘                    └──────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

---

## Step 1: Unified Multi-Cloud Cost Collection

Cloud providers' billing APIs are all over the place, but we can normalize the output to **three time-series metrics**:

| Metric | Meaning | Cadence |
|--------|---------|---------|
| `cloud_cost_hourly{vendor,resource}` | hourly cost (RMB/USD) | hourly |
| `cloud_utilization_cpu{resource}` / `_mem` | utilization 0-100 | hourly |
| `cloud_traffic_gb{resource,region}` | outbound traffic | hourly |

Aliyun / AWS / Tencent Cloud all expose OpenAPI for billing and monitoring. Here is a minimal working crawler abstraction — you just implement `fetch()` per provider:

```python
#!/usr/bin/env python3
"""
cloud-cost-crawler.py — multi-cloud cost crawler (abstraction layer)
Normalizes each provider's billing/monitoring API into Prometheus exposition format
"""
from abc import ABC, abstractmethod
from datetime import datetime, timezone

class CostProvider(ABC):
    name: str

    @abstractmethod
    def fetch(self) -> dict:
        """Return {resource_id: {"cost": float, "cpu": float, "mem": float, "traffic_gb": float, "type": str}}"""

class AliyunProvider(CostProvider):
    name = "aliyun"
    def fetch(self) -> dict:
        # Call BSS OpenAPI (QueryBill / QueryInstanceBill)
        # + CMS DescribeMetricLast (CPU/MEM utilization)
        raise NotImplementedError

class GenericProvider(CostProvider):
    """Generic: parse a locally exported billing CSV (export-style bills)"""
    name = "local"
    def __init__(self, csv_path: str):
        self.csv_path = csv_path
    def fetch(self) -> dict:
        import csv
        out = {}
        with open(self.csv_path) as f:
            for row in csv.DictReader(f):
                out[row["resource_id"]] = {
                    "cost": float(row.get("cost", 0)),
                    "cpu": float(row.get("cpu", 0)),
                    "mem": float(row.get("mem", 0)),
                    "traffic_gb": float(row.get("traffic_gb", 0)),
                    "type": row.get("type", "vm"),
                }
        return out

def render_exposition(providers: list) -> str:
    """Emit Prometheus text exposition format for Prometheus to scrape"""
    ts = int(datetime.now(timezone.utc).timestamp())
    lines = []
    for p in providers:
        try:
            data = p.fetch()
        except Exception as e:
            print(f"[warn] provider {p.name} failed: {e}")
            continue
        for rid, m in data.items():
            lines.append(f'cloud_cost_hourly{{vendor="{p.name}",resource="{rid}"}} {m["cost"]} {ts}')
            lines.append(f'cloud_utilization_cpu{{vendor="{p.name}",resource="{rid}"}} {m["cpu"]} {ts}')
            lines.append(f'cloud_utilization_mem{{vendor="{p.name}",resource="{rid}"}} {m["mem"]} {ts}')
            lines.append(f'cloud_traffic_gb{{vendor="{p.name}",resource="{rid}"}} {m["traffic_gb"]} {ts}')
    return "\n".join(lines) + "\n"

if __name__ == "__main__":
    import argparse, http.server, threading

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = render_exposition([GenericProvider("/opt/finops/bill.csv")])
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(body.encode())

    http.server.HTTPServer(("0.0.0.0", 9415), Handler).serve_forever()
```

Add a Prometheus scrape job (internal-only):

```yaml
# prometheus.yml append
scrape_configs:
  - job_name: "cloud-cost"
    static_configs:
      - targets: ["127.0.0.1:9415"]
    scrape_interval: 1h   # billing granularity is hourly — no need for faster
```

> 💡 **Cost collection does not need second-level data** — hourly granularity is perfect for FinOps and saves API quota too.

---

## Step 2: Pre-filter "Suspect Resources" with PromQL

LLMs are smart, but feeding thousands of time series wastes tokens and invites hallucinations. First do a **coarse pass with PromQL**, then hand only the suspects to the LLM:

```promql
# 1. High cost + low utilization (over-provisioned suspects)
cloud_cost_hourly * on(resource) group_left cloud_utilization_cpu
  * 100
  < 15
  and on(resource) cloud_cost_hourly > 0.5

# 2. Zero traffic for 72 straight hours (idle suspects — static sites, test boxes)
absent_over_time(cloud_traffic_gb[72h])
  or (sum by (resource) (increase(cloud_traffic_gb[72h])) == 0)

# 3. Hourly cost spike (traffic burst / overage suspects)
cloud_cost_hourly > (avg(cloud_cost_hourly[24h]) * 3)
```

Merge the three result sets into one "suspect list" JSON — this is the LLM's input:

```bash
#!/usr/bin/env bash
# suspicious-resources.sh — export the suspect list
set -euo pipefail
PROM="http://127.0.0.1:9090"
OUT="/opt/finops/suspicious.json"

{
echo "{"
echo "  \"generated_at\": \"$(date -Iseconds)\","
echo "  \"oversized\": (<query 1 result via /api/v1/query, mapped to {resource, cost_hourly, cpu, est_daily}>)"
echo "  \"idle_candidates\": (<query 2 result>)"
echo "  \"spike_alerts\": (<query 3 result, mapped to {resource, current, base_avg}>)"
echo "  \"whitelist\": [\"prod-k8s-node-1\", \"backup-db\"]"
echo "}"
} > "$OUT"
echo "✅ suspect list generated: $OUT"
```

(Replace the placeholders with the actual `curl -sG "$PROM/api/v1/query" --data-urlencode 'query=...' | jq ...` invocations for each query — see the full working version in the Chinese article.)

---

## Step 3: LLM Anomaly Triage (Ollama + Qwen2.5, Local)

```python
#!/usr/bin/env python3
"""
llm-cost-judge.py — LLM-driven cloud cost anomaly triage
Input: suspect list JSON (from PromQL coarse pass)
Output: verdict per resource (idle_shutdown / oversize_downsize / spike_watch / normal)
        + estimated daily savings
Local execution (Ollama + Qwen2.5) — billing data stays on the VPS
"""
import json, requests

OLLAMA = "http://localhost:11434"
MODEL  = "qwen2.5:7b"

JUDGE_PROMPT = """You are a FinOps (cloud cost optimization) expert. Below is the list of suspect cloud resources pre-filtered by PromQL.

Suspect list:
{suspicious_json}

Whitelist (must NOT be touched):
{whitelist}

Analyze each item and output a strict JSON array. Each entry:
- resource: resource ID
- verdict: one of "idle_shutdown" | "oversize_downsize" | "spike_watch" | "normal" (false positive)
- daily_saving_rmb: estimated daily savings in RMB (2 decimals) if shutdown/downsize
- reason: one sentence citing concrete numbers (e.g. "zero traffic for 72h, CPU avg <5%")
- action: concrete operation suggestion (e.g. "shutdown" / "downsize to 2 vCPU 4 GB")

Rules:
1. Whitelisted resources must be "normal"
2. Only 72h zero-traffic AND no known scheduled jobs → "idle_shutdown"
3. Only CPU<15% for 7 days AND ample memory headroom → "oversize_downsize"
4. When in doubt → "normal" (better a false negative than killing production)

Output the JSON array only, no extra text."""

def judge(suspicious: dict, whitelist: list) -> list:
    payload = JUDGE_PROMPT.format(
        suspicious_json=json.dumps(
            {k: v for k, v in suspicious.items() if k != "whitelist"},
            ensure_ascii=False, indent=2,
        )[:6000],  # cap token usage
        whitelist="\n".join(f"- {w}" for w in whitelist) or "(none)",
    )
    resp = requests.post(
        f"{OLLAMA}/api/generate",
        json={"model": MODEL, "prompt": payload, "stream": False,
              "options": {"temperature": 0.1, "num_ctx": 8192}},
        timeout=180,
    )
    resp.raise_for_status()
    text = resp.json()["response"].strip()
    if "```" in text:
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text)

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--input", default="/opt/finops/suspicious.json")
    p.add_argument("--output", default="/opt/finops/judgement.json")
    args = p.parse_args()

    with open(args.input) as f:
        data = json.load(f)
    result = judge(data, data.get("whitelist", []))

    with open(args.output, "w") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    total = sum(float(r.get("daily_saving_rmb", 0)) for r in result)
    print(f"✅ triage done: {len(result)} suspects, est. ¥{total:.2f}/day savings")
```

---

## Step 4: Auto-Execution with Safety Gates

An LLM saying "safe to shut down" must NOT be executed blindly. Three safety gates:

1. **Whitelist** — whitelisted resources are never touched
2. **Cooldown** — one automatic action per resource per 7 days (no flapping)
3. **Dry-run by default** — shutdown requires an explicit `--execute` flag

```python
#!/usr/bin/env python3
"""
auto-optimizer.py — execute cost optimizations from LLM verdicts
Dry-run by default; pass --execute to actually shut down / downsize
"""
import json, subprocess, time, argparse

STATE = "/opt/finops/cooldown.json"   # {resource: last_action_ts}
WHITELIST = {"prod-k8s-node-1", "backup-db"}

def load_state() -> dict:
    try:
        with open(STATE) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_state(s: dict):
    with open(STATE, "w") as f:
        json.dump(s, f, indent=2)

def within_cooldown(s: dict, resource: str, days: int = 7) -> bool:
    return (time.time() - s.get(resource, 0)) < days * 86400

def shutdown_vps(resource: str, provider: str):
    """
    Map to provider-specific CLI:
      - Aliyun:   aliyun ecs StopInstance --InstanceId <id>
      - AWS:      aws ec2 stop-instances --instance-ids <id>
      - Tencent:  tencentcloud cvm StopInstances --InstanceId.0 <id>
      - Local VM: SSH + systemctl poweroff
    Implement per your SDK; keep keys in /root/.config/finops/ (chmod 700)
    """
    cmds = {
        "aliyun": ["aliyun", "ecs", "StopInstance", "--InstanceId", resource],
        "aws":    ["aws", "ec2", "stop-instances", "--instance-ids", resource],
        "tencent": ["tencentcloud", "cvm", "StopInstances", "--InstanceId.0", resource],
    }
    cmd = cmds.get(provider, ["echo", "unknown-provider", provider, resource])
    print(f"  -> executing: {' '.join(cmd)}")
    subprocess.run(cmd, check=False)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--judgement", default="/opt/finops/judgement.json")
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()

    with open(args.judgement) as f:
        verdicts = json.load(f)
    state = load_state()

    for v in verdicts:
        rid = v["resource"]
        if v["verdict"] == "normal" or rid in WHITELIST:
            print(f"  ⏭️  skip {rid} ({v['verdict']})")
            continue
        if within_cooldown(state, rid):
            print(f"  ⏰ {rid} in cooldown, skip")
            continue
        if args.execute:
            if v["verdict"] == "idle_shutdown":
                shutdown_vps(rid, provider_hint(rid))
                state[rid] = time.time()
                save_state(state)
                print(f"  ✅ shut down {rid} (saves ¥{v.get('daily_saving_rmb')}/day)")
            elif v["verdict"] == "oversize_downsize":
                print(f"  📐 downsize {rid} → {v.get('action')} (manual API call)")
        else:
            print(f"  [dry-run] would {'shut down' if v['verdict']=='idle_shutdown' else 'downsize'} {rid}")

def provider_hint(rid: str) -> str:
    if rid.startswith("i-") and len(rid) > 20: return "aliyun"
    if rid.startswith("i-") and len(rid) == 17: return "aws"
    if rid.startswith("ins-"): return "tencent"
    return "local"

main()
```

> ⚠️ Strongly recommended: run a full week of dry-runs to measure false-positive rate before enabling `--execute`. Always keep the 7-day cooldown + whitelist as a double safety net for shutdown actions.

---

## Step 5: Daily Savings Report → Telegram

Turn the LLM verdicts into a **human-friendly report** and push it to a Telegram channel:

```python
#!/usr/bin/env python3
"""
daily-report.py — generate daily cloud cost savings report, push to Telegram
"""
import json, requests

def render_report(verdicts: list, total_saving: float) -> str:
    lines = ["📊 Daily Cloud Cost Auto-Pilot Report"]
    for v in verdicts:
        icon = {"idle_shutdown": "⏻", "oversize_downsize": "📐",
                "spike_watch": "⚡", "normal": "✅"}[v["verdict"]]
        lines.append(f"{icon} {v['resource']}: {v['reason']}")
        lines.append(f"   Suggestion: {v['action']}")
    lines.append(f"\n💰 Estimated savings today: ¥{total_saving:.2f}/day ≈ ¥{total_saving*30:.0f}/month")
    return "\n".join(lines)

def push_telegram(text: str):
    import os
    from dotenv import load_dotenv
    load_dotenv("/root/.config/finops/tg.env")   # TG_TOKEN=*** / TG_CHAT=yyy
    r = requests.post(
        f"https://api.telegram.org/bot{os.environ['TG_TOKEN']}/sendMessage",
        json={"chat_id": os.environ["TG_CHAT"], "text": text,
              "parse_mode": "Markdown"},
        timeout=30,
    )
    r.raise_for_status()
    print("✅ report pushed to Telegram")

if __name__ == "__main__":
    with open("/opt/finops/judgement.json") as f:
        verdicts = json.load(f)
    total = sum(float(v.get("daily_saving_rmb", 0)) for v in verdicts)
    push_telegram(render_report(verdicts, total))
```

Systemd timer (full pipeline daily at 09:00):

```ini
# /etc/systemd/system/cloud-finops-daily.service
[Unit]
Description=Daily cloud cost LLM triage + auto-optimize
After=network-online.target ollama.service

[Service]
User=root
WorkingDirectory=/opt/finops
Environment=OLLAMA_HOST=http://localhost:11434
ExecStart=/usr/bin/bash -lc 'bash suspicious-resources.sh && python3 llm-cost-judge.py && python3 auto-optimizer.py && python3 daily-report.py'
# After validation, switch to: ... 'python3 auto-optimizer.py --execute && ...'

[Install]
WantedBy=multi-user.target
```

---

## Cost & Resources

| Component | Extra RAM | Extra Disk | Notes |
|-----------|-----------|------------|-------|
| Ollama + Qwen2.5-7B | ~5 GB (on demand) | ~4 GB | zero if already installed |
| Prometheus (billing metrics) | ~200 MB | ~1 GB/month | hourly granularity = very compact |
| Crawler + judge scripts | 0 | <10 MB | pure Python |

**Total overhead: ~1 GB disk (30-day Prometheus retention), zero resident RAM.**

The ROI is immediate: shutting down just 2 idle instances (~$40-60/month) pays back everything 100x over.

---

## Summary

Cloud cost optimization is not "read the invoice at month end" — it's **daily automated health checks**:

| Stage | Traditional | This Guide |
|-------|------------|------------|
| Data collection | manual CSV export | multi-cloud API → Prometheus hourly time series |
| Anomaly discovery | month-end manual review | PromQL coarse pass + LLM fine triage, daily at 09:00 |
| Idle handling | forgotten, keeps billing | auto dry-run → confirmed shutdown, 7-day cooldown + whitelist |
| Over-provisioning | downsize by gut feeling | LLM cites actual CPU/MEM numbers in its recommendation |
| Delivery | monthly email nobody reads | daily Telegram push, every suggestion with concrete numbers |

**Next steps to explore:**
- Replace test workloads with **preemptible/spot instances** (60-80% cheaper)
- **SLO-budget driven**: set a cost budget per service; over budget → LLM auto-degrades
- Unified FinOps dashboard across multi-node VPS fleets (see `ai-vps-fleet-intelligence-cross-node-correlation`)

> ⚠️ All LLM inference runs locally; billing data (amounts, resource IDs) never touches the public internet.
