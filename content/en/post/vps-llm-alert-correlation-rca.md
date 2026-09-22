---
title: "VPS Alert Correlation & Root Cause Analysis with Local LLM"
description: "Stop drowning in alert storms. Use a local LLM (Ollama + Qwen2.5) to automatically correlate alerts, identify root causes, and generate actionable fix recommendations—turning reactive ops into proactive governance."
date: 2026-09-22T20:00:00+08:00
lastmod: 2026-09-22T20:00:00+08:00
slug: "vps-llm-alert-correlation-rca"
image: /images/posts/vps-llm-alert-correlation-rca/featured.png
tags: ["AI Ops", "VPS", "Alert Correlation", "Root Cause Analysis", "Ollama", "Qwen2.5", "Prometheus", "Alertmanager", "LLM", "Automation"]
categories: ["AI Ops"]
aliases: [/en/post/vps-llm-alert-correlation-rca/]
---

## The Alert Storm Problem

You've set up Prometheus + Alertmanager to monitor your VPS with dozens of alert rules covering CPU, memory, disk, and network. Everything runs smoothly—until one night when your phone starts vibrating relentlessly:

```
[CRITICAL] CPU usage > 95% on web-server-01
[CRITICAL] Memory usage > 90% on web-server-01
[WARNING]  Disk I/O latency high on web-server-01
[CRITICAL] Nginx 502 errors spiking
[WARNING]  MySQL slow queries increasing
[CRITICAL] Docker container 'api-worker' OOM killed
```

Six alerts fire almost simultaneously. **Which one do you tackle first? Which is the root cause, and which are cascade effects?** In a traditional alerting system, these alerts are parallel and isolated—no correlation, no context, no prioritization. Operators drown in the flood, spending hours investigating while the service crashes.

This is the **Alert Storm** problem. As infrastructure complexity grows, alert volume increases exponentially, and the cost of manual correlation analysis far exceeds its value.

## Why Traditional Solutions Fall Short

### 1. Alert Rules Can't Understand Causality

Prometheus alert rules are threshold-based: `cpu_usage > 95%` triggers an alert. But it doesn't know whether "high CPU is caused by a memory-leaking process" or "because a downstream service is slow, causing request queuing." Each alert is an independent boolean expression with no cross-metric understanding.

### 2. Alert Correlation Relies on Manual Expertise

Experienced operators manually write correlation logic: if CPU and memory alerts appear together, check processes first; if disk and I/O latency alerts coincide, check write volume. But these rules are fragile—new scenarios require new rules, and rules can conflict with each other.

### 3. Night and Holiday Response Delay

Even with On-Call rotation, alerts require human review, understanding, and decision-making. At 3 AM with 20 alerts, who can guarantee the right judgment?

## Local LLM Alert Correlation Architecture

### Core Concept

Deploy a local LLM (e.g., Ollama + Qwen2.5) as an **alert semantic understanding engine** to automatically:

1. **Alert Aggregation**: Identify related alerts within a time window
2. **Root Cause Inference**: Determine the most likely root cause based on alert content, historical data, and system state
3. **Fix Recommendations**: Generate executable remediation steps
4. **Alert Compression**: Condense multiple alerts into a single structured report, reducing noise

### Architecture Design

```
┌─────────────────────────────────────────────────────┐
│                 Monitoring Data Sources              │
│  Prometheus  ──┐                                    │
│  Alertmanager  ──┤                                   │
│  Syslog        ──┤──→  Alert Collector (Python)      │
│  Node Exporter ──┤      (listen to Alertmanager webhook)│
│  cAdvisor      ──┘                                    │
└─────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────┐
│            LLM Alert Analysis Engine                 │
│  ┌──────────────┐  ┌──────────────┐                │
│  │ Alert Preproc │  │ Context Fetch │                │
│  │ (dedup/normalize)│ (metrics/logs) │                │
│  └──────┬───────┘  └──────┬───────┘                │
│         └────────┬────────┘                         │
│                  ▼                                   │
│         ┌─────────────────┐                         │
│         │  LLM Reasoning   │                         │
│         │  (Qwen2.5 /      │                         │
│         │   DeepSeek-V3)   │                         │
│         └────────┬────────┘                         │
│                  ▼                                   │
│         ┌─────────────────┐                         │
│         │  RCA Report      │                         │
│         │  + Fix Actions   │                         │
│         └────────┬────────┘                         │
└──────────────────┼─────────────────────────────────┘
                   │
         ┌─────────┼─────────┐
         ▼         ▼         ▼
    ┌─────────┐ ┌───────┐ ┌────────┐
    │ Telegram│ │ Slack │ │ Email  │
    │ Alert   │ │ Alert │ │ Report │
    └─────────┘ └───────┘ └────────┘
```

## Complete Implementation

### Step 1: Deploy Local LLM

Deploy a lightweight LLM on your VPS using Ollama:

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull Qwen2.5 7B model (strong Chinese/English understanding, moderate resource usage)
ollama pull qwen2.5:7b-instruct

# Verify the model works
ollama run qwen2.5:7b-instruct "Hello, introduce yourself in one sentence"
```

For smaller VPS (2GB+ RAM), use lighter models:

```bash
# Ultra-lightweight (500MB RAM usage)
ollama pull qwen2.5:1.5b-instruct

# Balanced (recommended, 4GB+ RAM)
ollama pull qwen2.5:7b-instruct
```

### Step 2: Alert Collector

Write a Python script that listens for Alertmanager webhook pushes:

```python
#!/usr/bin/env python3
"""
Alert Correlation Engine — Listens to Alertmanager webhooks,
calls local LLM for alert correlation and root cause analysis.
"""

import json
import os
import time
import requests
from datetime import datetime, timedelta
from collections import defaultdict
from pathlib import Path

# Configuration
OLLAMA_API = os.getenv("OLLAMA_API", "http://localhost:11434")
MODEL = os.getenv("LLM_MODEL", "qwen2.5:7b-instruct")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
ALERT_HISTORY_FILE = Path("/var/log/vps-alerts/history.json")
COOLDOWN_SECONDS = int(os.getenv("COOLDOWN_SECONDS", "300"))  # 5-minute dedup

# Alert history (for cross-time-window correlation)
alert_history = defaultdict(list)


def load_history():
    if ALERT_HISTORY_FILE.exists():
        try:
            return json.loads(ALERT_HISTORY_FILE.read_text())
        except Exception:
            return {}
    return {}


def save_history(history):
    ALERT_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    # Keep only last 24 hours
    cutoff = datetime.utcnow() - timedelta(hours=24)
    cleaned = {}
    for key, alerts in history.items():
        cleaned[key] = [a for a in alerts if datetime.fromisoformat(a["time"]) > cutoff]
    ALERT_HISTORY_FILE.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2))


def fetch_context(alert):
    """Collect context info related to the alert (CPU, memory, disk, processes, etc.)"""
    instance = alert.get("labels", {}).get("instance", "unknown")
    context = {}

    # Get current system status
    try:
        r = requests.get(f"http://{instance}:9100/metrics", timeout=5)
        for line in r.text.splitlines():
            if line.startswith("cpu_usage_percent"):
                context["cpu_usage"] = float(line.split()[-1])
            elif line.startswith("memory_usage_percent"):
                context["memory_usage"] = float(line.split()[-1])
            elif line.startswith("disk_io_time_seconds_total"):
                context["disk_io"] = True
    except Exception:
        pass

    # Get top processes by CPU/Memory
    try:
        import subprocess
        result = subprocess.run(
            ["top", "-bn1", "-o", "%CPU"],
            capture_output=True, text=True, timeout=5
        )
        lines = result.stdout.splitlines()[3:8]  # top 5 processes
        context["top_cpu_processes"] = lines
    except Exception:
        pass

    try:
        import subprocess
        result = subprocess.run(
            ["docker", "ps", "--format", "table {{.Names}}\t{{.CPUPerc}}\t{{.MemPerc}}"],
            capture_output=True, text=True, timeout=5
        )
        context["docker_containers"] = result.stdout.strip().splitlines()[1:]
    except Exception:
        pass

    return context


def build_prompt(alerts, context):
    """Build LLM prompt"""
    now = datetime.utcnow().isoformat() + "Z"

    alerts_text = []
    for i, alert in enumerate(alerts, 1):
        labels = alert.get("labels", {})
        annotations = alert.get("annotations", {})
        alerts_text.append(
            f"{i}. [{alert.get('status', 'unknown')}] {labels.get('alertname', 'Unknown')}\n"
            f"   Severity: {labels.get('severity', 'unknown')}\n"
            f"   Instance: {labels.get('instance', 'unknown')}\n"
            f"   Description: {annotations.get('description', 'N/A')}\n"
            f"   Summary: {annotations.get('summary', 'N/A')}"
        )

    context_text = json.dumps(context, ensure_ascii=False, indent=2)

    prompt = f"""You are a senior SRE expert skilled at quickly identifying root causes from multiple alerts.

Current time: {now}

Received alerts ({len(alerts)} total):
{chr(10).join(alerts_text)}

Related system context:
{context_text}

Please complete the following analysis and return as JSON (do NOT include markdown code blocks):
{{
  "root_cause": "Brief description of root cause (English)",
  "root_cause_severity": "critical|high|medium|low",
  "correlated_alerts": ["List of alerts affected by root cause"],
  "independent_alerts": ["List of independent alerts unrelated to root cause"],
  "explanation": "Brief explanation of analysis (2-3 sentences)",
  "action_plan": [
    {{"step": 1, "action": "Specific command or step", "priority": "high"}}
  ],
  "estimated_recovery_time": "Estimated recovery time"
}}"""
    return prompt


def call_llm(prompt: str) -> dict:
    """Call local Ollama API"""
    response = requests.post(
        f"{OLLAMA_API}/api/generate",
        json={
            "model": MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.3, "num_predict": 1024}
        },
        timeout=60
    )
    response.raise_for_status()
    result = response.json()

    output = result.get("response", "")
    if "```json" in output:
        output = output.split("```json")[1].split("```")[0]
    elif "```" in output:
        output = output.split("```")[1].split("```")[0]

    try:
        return json.loads(output.strip())
    except json.JSONDecodeError:
        return {"raw_output": output, "error": "JSON parse failed"}


def send_telegram(message: str):
    """Send Telegram notification"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    requests.post(url, json={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }, timeout=10)


def format_report(report: dict, alerts: list) -> str:
    """Format LLM analysis report into readable message"""
    lines = [
        f"🔔 **VPS Alert Correlation Report**",
        f"⏰ {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC",
        f"",
        f"📊 **Alert Count**: {len(alerts)}",
        f"🎯 **Root Cause**: {report.get('root_cause', 'N/A')}",
        f"⚠️ **Severity**: {report.get('root_cause_severity', 'N/A')}",
        f"💡 **Analysis**: {report.get('explanation', 'N/A')}",
        f"",
    ]

    correlated = report.get("correlated_alerts", [])
    if correlated:
        lines.append(f"🔗 **Correlated Alerts**: {', '.join(correlated)}")
    independent = report.get("independent_alerts", [])
    if independent:
        lines.append(f"➖ **Independent Alerts**: {', '.join(independent)}")

    lines.append("")
    lines.append("📋 **Fix Recommendations**:")
    for step in report.get("action_plan", []):
        lines.append(f"  {step['step']}. [{step.get('priority', '')}] {step['action']}")

    recovery = report.get("estimated_recovery_time", "N/A")
    lines.append(f"\n⏱️ **Estimated Recovery**: {recovery}")

    return "\n".join(lines)


def process_alerts(alert_payload):
    """Process a batch of alerts for correlation analysis"""
    alerts = alert_payload.get("alerts", [])
    if not alerts:
        return

    # Check cooldown period (deduplication)
    now = datetime.utcnow().isoformat()
    group_key = tuple(sorted(a["labels"]["alertname"] for a in alerts))
    recent = alert_history.get(group_key, [])
    if recent:
        last_time = datetime.fromisoformat(recent[-1]["time"].replace("Z", "+00:00"))
        if (datetime.now(last_time.tzinfo) - last_time).total_seconds() < COOLDOWN_SECONDS:
            print(f"[SKIP] Alert group {group_key} is in cooldown period")
            return
    alert_history[group_key].append({"time": now, "count": len(alerts)})

    print(f"[INFO] Received {len(alerts)} alerts, starting correlation analysis...")

    # Fetch context
    context = fetch_context(alerts[0])

    # Build prompt and call LLM
    prompt = build_prompt(alerts, context)
    print(f"[INFO] Calling LLM ({MODEL}) for analysis...")

    try:
        report = call_llm(prompt)
    except Exception as e:
        print(f"[ERROR] LLM call failed: {e}")
        report = {"error": str(e), "raw_output": ""}

    # Format and send report
    report_text = format_report(report, alerts)
    print(f"[INFO] Analysis report:\n{report_text}")
    send_telegram(report_text)

    # Save history
    save_history(alert_history)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        payload = json.loads(Path(sys.argv[1]).read_text())
        process_alerts(payload)
    else:
        from http.server import HTTPServer, BaseHTTPRequestHandler

        class AlertHandler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                payload = json.loads(self.rfile.read(length))
                process_alerts(payload)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"OK")

            def log_message(self, format, *args):
                pass

        port = int(os.getenv("WEBHOOK_PORT", "8080"))
        print(f"[START] Alert correlation engine listening on port {port}")
        HTTPServer(("0.0.0.0", port), AlertHandler).serve_forever()
```

### Step 3: Alertmanager Route Configuration

Configure the webhook route in `alertmanager.yml` to forward all alerts to the LLM analysis engine:

```yaml
global:
  resolve_timeout: 5m

route:
  group_by: ['alertname', 'instance']
  group_wait: 10s        # Wait 10s to collect same-batch alerts
  group_interval: 5m
  repeat_interval: 4h
  receiver: 'llm-analyzer'

receivers:
  - name: 'llm-analyzer'
    webhook_configs:
      - url: 'http://localhost:8080/alerts'
        send_resolved: true

  - name: 'null-receiver'  # Silence original alerts, only notify via LLM report
```

Key configuration notes:
- `group_by`: Group by alert name and instance to avoid individual alert triggers
- `group_wait: 10s`: Wait 10 seconds to aggregate same-batch alerts, reducing fragmented notifications
- `send_resolved: true`: Also receive resolution notifications so LLM can determine if further action is needed

### Step 4: Scheduled Context Refresh

In addition to webhook triggers, set up periodic system status collection and proactive reporting:

```bash
# crontab -e
# Collect system status every 15 minutes, generate health report hourly
*/15 * * * * /usr/bin/docker exec ollama ollama run qwen2.5:7b-instruct \
  "Generate a health score and recommendations (0-100) based on: $(cat /tmp/sys-status.json)" \
  > /tmp/health-report.txt 2>&1

0 * * * * cat /tmp/health-report.txt | /usr/local/bin/send-telegram.sh
```

## Real-World Example

Assume your VPS triggers these alerts simultaneously:

| Alert Name | Severity | Description |
|-----------|----------|-------------|
| HighCPU | critical | CPU usage 97% |
| HighMemory | critical | Memory usage 92% |
| DiskSpaceLow | warning | Disk usage 88% |
| Nginx502 | critical | Nginx returning 502 |
| MySQLSlow | warning | Slow queries increasing |

**Traditional approach**: Operators log into the server one by one, check `top`, `df -h`, `systemctl status nginx`, `mysql slow log`—taking 30+ minutes.

**LLM correlation analysis**:

```
🔔 VPS Alert Correlation Report
⏰ 2026-09-22 03:15:00 UTC

📊 Alert Count: 5
🎯 Root Cause: MySQL slow queries causing connection pool exhaustion, leading to Nginx 502 and memory pressure
⚠️ Severity: critical
💡 Analysis: CPU and memory alerts are cascading effects of MySQL slow queries. Disk space pressure may be caused by MySQL temp table writes.

🔗 Correlated Alerts: HighCPU, HighMemory, Nginx502, MySQLSlow
➖ Independent Alerts: DiskSpaceLow

📋 Fix Recommendations:
  1. [high] Run SHOW PROCESSLIST to find stuck queries and KILL them
  2. [high] Check MySQL connection pool config (max_connections, wait_timeout)
  3. [medium] Clean MySQL temp files and slow query logs
  4. [medium] Consider adding missing indexes on large tables

⏱️ Estimated Recovery: 10-15 minutes
```

One report replaces five screenshots. Operators can execute fix recommendations directly without逐一排查.

## Advanced Optimization Directions

### 1. Multi-VPS Collaborative Analysis

When managing multiple VPS instances, aggregate all alerts for unified analysis:

```python
# Extend prompt to support multi-instance
all_alerts = fetch_alerts_from_all_vps()  # Collect alerts from multiple nodes
prompt = build_prompt(all_alerts, multi_node_context)
```

LLM can identify cross-node correlations—e.g., "disk full on web-server-01 caused replication delay, which affected db-server-01 read performance."

### 2. Historical Pattern Matching

Save each alert analysis conclusion to help LLM recognize repeating patterns:

```python
# Simple pattern matching cache
PATTERN_DB = "/var/lib/vps-alert-patterns/patterns.json"

def find_similar_pattern(new_alerts):
    """Match historical alert patterns based on keywords"""
    # Implement TF-IDF or simple keyword overlap calculation
    ...
```

### 3. Self-Healing Execution

For low-risk operations (e.g., log cleanup, restarting non-critical services), let LLM generate commands and execute automatically:

```python
def execute_remediation(report: dict):
    """Execute LLM-generated fix commands (requires human approval for high-risk ops)"""
    for step in report.get("action_plan", []):
        if step.get("priority") == "low" and step.get("auto_execute"):
            os.system(step["action"])
            log_action(step["action"], "auto")
        else:
            log_action(step["action"], "pending_approval")
```

### 4. Integration with Existing Tools

- **Grafana**: Embed LLM analysis reports in Dashboard panels
- **PagerDuty/Opsgenie**: Attach LLM analysis as incident notes
- **Ansible**: Convert fix recommendations into Playbooks for automatic execution

## Summary

| Dimension | Traditional Alerting | LLM Correlation |
|-----------|---------------------|-----------------|
| Alert Processing | One-by-one response | Batch correlation |
| Root Cause Identification | Manual investigation (30min+) | LLM auto-inference (<30s) |
| Notification Content | Raw alert text | Structured analysis report |
| False Positive Handling | None | LLM can identify noise alerts |
| Cross-Node Correlation | Impossible | LLM understands topology |
| Fix Recommendations | None | Executable action steps |

The core value of local LLM alert correlation is: **transforming alerts from "notifications" into "diagnoses"**. Operators no longer need to be full-stack experts to understand every alert's meaning—the LLM handles information gathering and initial analysis; you only make the final decision.

This entire solution runs on your VPS. Data never leaves your server, ensuring privacy and security. Paired with Ollama's lightweight models, even a 2GB RAM VPS can run it smoothly.

---

**Next Steps**: Start with a single VPS—deploy Ollama + the alert collector, observe the correlation analysis results for a week, then gradually expand to multi-node scenarios. The quality of your alert rules directly affects LLM analysis effectiveness, so organize your alerting system first before integrating.
