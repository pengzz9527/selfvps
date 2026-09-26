---
title: "AI + VPS: Multi-Node Fleet Intelligence & Cross-Node Fault Correlation"
description: "One VPS goes down and three others follow? Traditional alerts are siloed and can't see cross-server dependencies. This article builds a multi-node fleet intelligence system with local LLM — automatic dependency discovery, cross-node root cause correlation, intelligent traffic routing, and fleet-wide health scoring."
date: 2026-09-26T21:00:00+08:00
lastmod: 2026-09-26T21:00:00+08:00
slug: "ai-vps-fleet-intelligence-cross-node-correlation"
image: /images/posts/ai-vps-fleet-intelligence-cross-node-correlation/featured.png
tags: ["AI Ops", "Multi-Node", "Fault Correlation", "LLM", "Ollama", "SRE", "AIOps", "Resilience", "Self-hosted"]
categories: ["AI + VPS"]
aliases: [/en/post/ai-vps-fleet-intelligence-cross-node-correlation/]
draft: false
---

## Introduction

You're running a fleet of VPS instances: some for web services, some for databases, some for APIs, and others for backups and monitoring. Each machine has its own monitoring and alerting — but here's the problem:

**When one database VPS hits 95% CPU, why does the frontend API slow down too?**

Traditional alerting systems are **siloed**: each machine watches itself. Prometheus monitors its own nodes, Loki reads its own logs, Alertmanager fires rules in isolation. You get 20 alerts and have no idea how they're related. Manual investigation means SSH-ing into half a dozen machines, sifting through logs, comparing timestamps, and guessing connections — taking hours.

**True multi-node operations需要一个 AI brain.**

This article shows how to build a **multi-node fleet intelligence system** using local Ollama + Qwen2.5: automatic dependency discovery across nodes, cross-node fault root cause correlation, intelligent traffic routing decisions, and fleet-wide health scoring. All data stays on your network — nothing sent to third parties.

---

## Core Challenges of Multi-Node Operations

### Challenge 1: Implicit Cross-Node Dependencies

Your service architecture might look like this:

```
User → Nginx (Load Balancer) → API Server (x3) → Redis → PostgreSQL
                                 ↘ Worker (x2) → RabbitMQ → Processor → DB
```

On the surface, each VPS runs independently. But in reality, API Server health depends on PostgreSQL response time, and PostgreSQL performance is affected by Redis cache hit rate. **A single-node alert is often a symptom of a systemic issue.**

| Symptom | Traditional Approach | AI-Driven Approach |
|---------|---------------------|-------------------|
| DB slow queries | DB node alerts | AI correlates API latency spike, identifies root cause as DB lock contention |
| Disk full on one node | Single alert | AI notices backup jobs running on multiple nodes simultaneously, suggests staggered scheduling |
| CDN origin shield spike | No alert | AI infers upstream issue from cache miss rate increase |

### Challenge 2: Alert Storms Drown Critical Information

10 nodes × 5 alerts each = 50 alerts flooding Telegram at once. Only one might be the root cause; the other 49 are downstream symptoms. Distinguishing root cause from symptoms requires experience — AI does this automatically with semantic understanding.

### Challenge 3: Inefficient Manual Troubleshooting

Traditional troubleshooting flow:
1. Receive alert → SSH in → `top`/`htop` check load
2. `dmesg`/`journalctl` check kernel logs
3. `tail -f` follow application logs
4. `curl` test upstream/downstream dependencies
5. Switch between multiple terminals, manually compare timestamps

This process averages **30-60 minutes**, while AI completes the same analysis in **under 30 seconds**.

---

## System Architecture

### Overall Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    Fleet Intelligence Layer                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ Dependency   │  │ Root Cause   │  │  Fleet Health    │  │
│  │ Auto-Discovery│  │ Correlator   │  │  Score Engine    │  │
│  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘  │
│         │                 │                    │            │
│  ┌──────▼───────┐  ┌──────▼───────┐  ┌────────▼─────────┐  │
│  │  Ollama      │  │  Qwen2.5     │  │  Decision        │  │
│  │  (Local LLM) │  │  (Reasoning) │  │  Engine          │  │
│  └──────────────┘  └──────────────┘  └────────┬─────────┘  │
└───────────────────────────────────────────────┼─────────────┘
                                                 │
          ┌──────────────────────────────────────┼──────────────────┐
          │                                      │                  │
    ┌─────▼─────┐                          ┌────▼────┐       ┌─────▼─────┐
    │ Node A    │                          │ Node B  │       │ Node C    │
    │ (API)     │◄──── gRPC/Telegram ─────►│ (DB)    │◄─────►│ (Cache)   │
    │ Prometheus│                          │ Loki    │       │ Node Exp. │
    └───────────┘                          └─────────┘       └───────────┘
```

### Core Modules

**1. Dependency Auto-Discovery Engine**

Instead of manual configuration, automatically learn node dependencies through:

- **Traffic tracing**: Analyze Nginx access logs for upstream call patterns
- **Port scanning**: Periodically probe ports and services on each node
- **Log timestamp correlation**: When node A's anomaly log precedes node B's, establish causal hypothesis
- **DNS record analysis**: Extract service dependencies from `/etc/hosts`, Docker Compose, K8s Services

```bash
#!/bin/bash
# fleet-discover.sh — Automatically discover cross-node dependencies
NODES="192.168.1.10 192.168.1.11 192.168.1.12 192.168.1.13"

for src in $NODES; do
    echo "=== Scanning $src ==="
    ss -tlnp 2>/dev/null | grep LISTEN | while read line; do
        port=$(echo "$line" | grep -oP ':\K[0-9]+')
        for dst in $NODES; do
            [ "$dst" = "$src" ] && continue
            if nc -z -w 2 "$dst" "$port" 2>/dev/null; then
                echo "DEPEND: $src:$port ← $dst"
            fi
        done
    done
done
```

**2. Cross-Node Root Cause Correlator**

Core idea: **Co-occurring anomalies within a time window = potential causal chain.**

```python
# fleet_correlator.py — Cross-node fault correlation engine
import json
from datetime import datetime, timedelta

class FleetCorrelator:
    def __init__(self, nodes_config):
        self.nodes = nodes_config
        self.dependency_graph = {}
        self.alert_history = {}

    def correlate(self, alerts: list[dict]) -> list[dict]:
        """
        Input: alerts from all nodes
        Output: merged root cause alerts + associated symptoms
        """
        sorted_alerts = sorted(alerts, key=lambda x: x['timestamp'])
        correlated = []
        window = timedelta(minutes=5)

        for i, alert in enumerate(sorted_alerts):
            group = [alert]
            for j in range(i + 1, len(sorted_alerts)):
                if sorted_alerts[j]['timestamp'] - alert['timestamp'] <= window:
                    if self._is_related(alert, sorted_alerts[j]):
                        group.append(sorted_alerts[j])
            if len(group) > 1:
                correlated.append({
                    'root_cause_candidate': group[0],
                    'symptoms': group[1:],
                    'confidence': self._calculate_confidence(group)
                })
        return correlated

    def _is_related(self, alert_a, alert_b) -> bool:
        deps = self.dependency_graph.get(alert_a['node'], [])
        return alert_b['node'] in deps

    def _calculate_confidence(self, group) -> float:
        time_span = (group[-1]['timestamp'] - group[0]['timestamp']).total_seconds()
        base_conf = 0.9 if time_span < 60 else 0.7
        return min(base_conf, 0.95)
```

**3. Fleet Health Score Engine**

Condense multi-node status into a single number:

```python
# health_score.py
import numpy as np

def fleet_health_score(node_metrics: dict) -> dict:
    """
    Input: {
        "node_a": {"cpu": 45, "mem": 60, "disk": 30, "err_rate": 0.01},
        "node_b": {"cpu": 92, "mem": 85, "disk": 90, "err_rate": 0.15},
        "node_c": {"cpu": 10, "mem": 20, "disk": 15, "err_rate": 0.001},
    }
    """
    scores = {}
    for node, m in node_metrics.items():
        cpu_s = max(0, 100 - m['cpu'])
        mem_s = max(0, 100 - m['mem'])
        disk_s = max(0, 100 - m['disk'])
        err_s = max(0, 100 - m['err_rate'] * 1000)

        weighted = (
            cpu_s * 0.25 +
            mem_s * 0.20 +
            disk_s * 0.15 +
            err_s * 0.40
        )
        scores[node] = round(weighted, 1)

    total = sum(scores.values())
    avg = round(total / len(scores), 1)

    min_score = min(scores.values())
    if min_score < 30:
        avg = round(avg * (min_score / 50), 1)

    return {
        "fleet_score": avg,
        "node_scores": scores,
        "risk_level": "critical" if avg < 40 else ("warning" if avg < 70 else "healthy"),
        "weakest_node": min(scores, key=scores.get)
    }
```

**4. Intelligent Traffic Router**

LLM-driven dynamic routing:

```python
# traffic_router.py
"""
LLM-driven dynamic traffic routing:
- Healthy nodes get more traffic
- Anomalous nodes automatically degraded
- Cold-start nodes warmed before joining pool
"""

ROUTING_POLICY_TEMPLATE = """
You are a VPS fleet traffic routing expert. Current fleet state:

{fleet_state}

Output JSON routing decision:
{{
  "action": "rebalance|scale_out|failover|normal",
  "reasoning": "brief explanation",
  "routing_table": {{
    "node_a": {{"weight": 0.4, "health_check": true}},
    "node_b": {{"weight": 0.1, "health_check": false}},
    "node_c": {{"weight": 0.5, "health_check": true}}
  }},
  "estimated_latency_impact": "+5ms"
}}
"""

def get_routing_decision(fleet_state: dict, llm_client) -> dict:
    prompt = ROUTING_POLICY_TEMPLATE.format(fleet_state=json.dumps(fleet_state, indent=2))
    response = llm_client.chat(prompt)
    return json.loads(extract_json(response))
```

---

## Deployment

### Step 1: Agentless Collection Layer

No agents needed on each node — collect via SSH + remote commands:

```bash
#!/bin/bash
# fleet-collector.sh — Collect metrics from all nodes without agents
COLLECTOR_NODE="192.168.1.10"
ALL_NODES="192.168.1.10 192.168.1.11 192.168.1.12 192.168.1.13"

collect_node_metrics() {
    local node=$1
    echo "Collecting from $node ..."

    ssh -o ConnectTimeout=5 "$node" '
        echo "=== $(hostname) ==="
        echo "CPU: $(top -bn1 | grep "Cpu(s)" | awk "{print \$2}" | cut -d"." -f1)%"
        echo "MEM: $(free | awk "/^Mem:/ {printf \"%.1f%%\", \$3/\$2 * 100}")"
        echo "DISK: $(df -h / | awk "NR==2 {print \$5}")"
        echo "LOAD: $(uptime | awk -F"load average:" "{print \$2}" | cut -d"," -f1)"
        echo "ERR_LOG: $(grep -c "ERROR\|FATAL\|PANIC" /var/log/syslog 2>/dev/null || echo 0)"
        echo "ACTIVE_CONN: $(ss -tn | grep ESTAB | wc -l)"
    ' 2>/dev/null || echo "UNREACHABLE: $node"
}

for node in $ALL_NODES; do
    collect_node_metrics "$node"
done | tee /tmp/fleet_snapshot.jsonl
```

### Step 2: Dependency Graph Construction

```python
# dependency_graph.py
"""
Automatically build service dependency graph from logs and connections
"""
import subprocess
import re
from collections import defaultdict

class DependencyGraphBuilder:
    def __init__(self, nodes):
        self.nodes = nodes
        self.graph = defaultdict(set)
        self.edge_weights = defaultdict(float)

    def build_from_logs(self, log_dir: str):
        """Extract call relationships from access/error logs"""
        for node in self.nodes:
            cmd = f"ssh {node} 'grep upstream_address /var/log/nginx/access.log | \
                   awk \"{{print \\$10, \\$7}}\" | head -100'"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

            for line in result.stdout.strip().split('\n'):
                parts = line.split()
                if len(parts) >= 2:
                    upstream = parts[1]
                    target_node = self._ip_to_node(upstream)
                    if target_node and target_node != node:
                        self.graph[node].add(target_node)
                        self.edge_weights[(node, target_node)] += 1

    def build_from_connections(self):
        """Extract dependencies from network connections"""
        for node in self.nodes:
            cmd = f"ssh {node} 'ss -tn state established | grep -v {node} | \
                   awk \"{{print \\$5}}\" | cut -d: -f1 | sort -u'"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            for remote_ip in result.stdout.strip().split('\n'):
                target = self._ip_to_node(remote_ip.strip())
                if target:
                    self.graph[node].add(target)

    def to_llm_context(self) -> str:
        """Export as LLM-understandable text format"""
        lines = ["Service dependency graph:"]
        for src, targets in self.graph.items():
            for tgt in targets:
                weight = self.edge_weights.get((src, tgt), 1)
                lines.append(f"  {src} → {tgt} (strength: {weight})")
        return "\n".join(lines)
```

### Step 3: LLM Root Cause Analysis Pipeline

```python
# llm_root_cause.py
"""
Cross-node root cause analysis using local Ollama + Qwen2.5
"""
import ollama
import json
from datetime import datetime

RCA_PROMPT = """You are a senior SRE expert analyzing multi-node fleet incidents.

## Cluster Dependency Map
{dependency_map}

## Current Alerts (chronological order)
{alerts}

## Node Health Scores
{health_scores}

Please analyze:
1. **Root cause node**: Which machine showed anomaly first?
2. **Propagation path**: How did the fault spread from root cause to other nodes?
3. **Confidence**: How confident are you? (0-100%)
4. **Recommended actions**: What should be done first?

Output JSON:
{{
  "root_cause_node": "node name",
  "propagation_path": ["node_a", "node_b", "node_c"],
  "confidence": 85,
  "analysis": "detailed analysis",
  "recommended_actions": [
    {{"step": 1, "action": "action description", "priority": "high"}}
  ]
}}
"""

def analyze_fleet_incident(
    dependency_map: str,
    alerts: list[dict],
    health_scores: dict,
    model: str = "qwen2.5:7b"
) -> dict:
    alerts_json = json.dumps(alerts, indent=2, ensure_ascii=False)
    health_json = json.dumps(health_scores, indent=2, ensure_ascii=False)

    prompt = RCA_PROMPT.format(
        dependency_map=dependency_map,
        alerts=alerts_json,
        health_scores=health_json
    )

    response = ollama.chat(model=model, messages=[
        {"role": "user", "content": prompt}
    ])

    text = response['message']['content']
    json_start = text.find('{')
    json_end = text.rfind('}') + 1
    return json.loads(text[json_start:json_end])
```

### Step 4: Telegram Aggregated Alert

```python
# fleet_notifier.py
"""
Merge 50 scattered alerts into 1 AI-generated report sent to Telegram
"""
import telebot
import ollama

TELEGRAM_BOT_TOKEN = "YOUR_BOT_TOKEN"
TELEGRAM_CHAT_ID = "YOUR_CHAT_ID"

def send_fleet_alert(fleet_state: dict, rca_result: dict):
    bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

    report = f"""🚨 **Fleet Anomaly Alert**

📊 **Fleet Health Score**: {fleet_state['fleet_score']}/100 ({fleet_state['risk_level']})
💥 **Root Cause Node**: {rca_result['root_cause_node']}
🔗 **Propagation Path**: {' → '.join(rca_result['propagation_path'])}
🎯 **Confidence**: {rca_result['confidence']}%

**Node Status**:
"""
    for node, score in fleet_state['node_scores'].items():
        emoji = "🟢" if score >= 70 else ("🟡" if score >= 40 else "🔴")
        report += f"{emoji} {node}: {score}\n"

    report += f"""
**Recommended Actions**:
"""
    for action in rca_result['recommended_actions']:
        report += f"{action['step']}. [{action['priority']}] {action['action']}\n"

    report += f"\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

    bot.send_message(TELEGRAM_CHAT_ID, report, parse_mode="Markdown")
```

---

## Complete Workflow Example

Assume your 4-node fleet experiences an incident:

```
T+0s    : db-primary disk usage hits 92%
T+30s   : db-primary starts rejecting new connections (connection pool exhausted)
T+45s   : api-01 shows大量 502 errors (upstream unreachable)
T+60s   : api-02 shows大量 502 errors
T+90s   : cache-01 cache invalidation spike (db slowness causes TTL expiry)
T+120s  : worker-01 message backlog (consumer processing slowed)
```

**Traditional approach**: 5 separate alerts, SSH into each machine one by one, 30+ minutes to identify root cause as db-primary disk space.

**AI-driven approach**:

1. FleetCorrelator merges all alerts into a single incident at T+60s
2. Dependency graph shows api-01 → db-primary, cache-01 → db-primary
3. LLM analysis outputs:
   ```json
   {
     "root_cause_node": "db-primary",
     "propagation_path": ["db-primary", "api-01", "api-02", "cache-01", "worker-01"],
     "confidence": 92,
     "analysis": "db-primary disk space exhaustion caused write failures, connection pool exhaustion triggered cascading failure",
     "recommended_actions": [
       {"step": 1, "action": "Clean up old logs and temp files on db-primary to free space", "priority": "high"},
       {"step": 2, "action": "Restart PostgreSQL on db-primary to release connections", "priority": "high"},
       {"step": 3, "action": "Review cache-01 TTL strategy to reduce DB load", "priority": "medium"}
     ]
   }
   ```
4. Telegram receives one consolidated alert — you know exactly what to do in 30 seconds

---

## Integration with Existing Monitoring

This system doesn't replace Prometheus/Grafana/Loki — it **adds AI intelligence on top**:

```
┌─────────────────────────────────────────────────┐
│         Fleet Intelligence Layer (this system)   │
│  • Alert aggregation & root cause analysis       │
│  • Cross-node dependency reasoning                │
│  • Intelligent routing decisions                  │
├─────────────────────────────────────────────────┤
│         Standardized Data Interface (OpenTelemetry)│
│  • Metrics → Prometheus                          │
│  • Logs → Loki / Grafana                         │
│  • Traces → Tempo / Jaeger                       │
├─────────────────────────────────────────────────┤
│            Data Collection Layer                  │
│  • Node Exporter (metrics)                       │
│  • Promtail (logs)                               │
│  • cAdvisor (containers)                         │
└─────────────────────────────────────────────────┘
```

**Key point**: The Fleet Intelligence Layer works by reading your existing Prometheus metrics and Loki logs — no changes to your current monitoring stack required.

---

## Cost Estimate

| Component | Hardware Requirement | Monthly Cost |
|-----------|---------------------|-------------|
| Ollama + Qwen2.5:7b | 8GB+ RAM, CPU-only runs fine | $0 (local) |
| Fleet Collector script | Any VPS | $0 |
| Prometheus + Loki | Reuse existing | $0 |
| Telegram Bot | Free tier | $0 |

The entire system runs on a **2GB RAM VPS** with zero cloud service dependencies.

---

## Summary

The core challenge of multi-node operations isn't monitoring each machine — it's **understanding the relationships between them**. AI's value here is:

1. **Automatic discovery**: No manual dependency configuration needed; AI learns from logs and connections
2. **Semantic correlation**: Understand 50 scattered alerts as one coherent incident story
3. **Reasoned decisions**: Not just "what happened" but "why" and "what to do about it"
4. **Zero-cost deployment**: Local LLM + scripts, no SaaS subscriptions required

When your VPS count grows from 1 to 10 to 100, this system keeps your operational efficiency constant — because AI doesn't get tired, doesn't miss alerts, and never forgets which service depends on which database.

**Next time** we'll dive into closing the loop: connecting this system to CI/CD for autonomous incident remediation — AI detects the root cause, executes fix scripts, and notifies you when done.
