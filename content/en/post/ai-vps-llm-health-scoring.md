---
title: "AI + VPS: Giving Your Server a Full Health Check — Intelligent Health Scoring with LLMs"
description: "Move beyond scattered alerting. Let an LLM synthesize CPU, memory, disk, security, and network metrics into a single actionable health score and diagnosis report — like a physical exam for your server."
date: 2026-09-02T21:00:00+08:00
lastmod: 2026-09-02T21:00:00+08:00
slug: "ai-vps-llm-health-scoring"
image: /images/posts/ai-vps-llm-health-scoring/featured.png
tags: ["AI Ops", "LLM", "VPS Health", "Intelligent Scoring", "Prometheus", "Grafana", "Automation"]
categories: ["AI Ops"]
aliases: [/en/post/ai-vps-llm-health-scoring/]
---

## Introduction

You manage five, ten, or more VPS instances—each running different services: websites, APIs, databases, caches, cron jobs.

Your monitoring tools tell you "CPU at 92%", "3 GB disk remaining", "47 failed SSH logins". But these are **isolated numbers**. No one is answering the most important question:

**Is this server actually healthy right now?**

The core pain point of traditional ops: monitoring data is abundant, but there's **no unified health judgment**. Operators need to check Prometheus dashboards, review system logs, examine security alerts—to piece together a vague conclusion.

AI large language models change this entirely.

---

## Core Concept: From "Alert Thresholds" to "Health Exams"

Think of this system as a **yearly physical examination** for your servers:

| Exam Item        | Server Metric Equivalent        |
|-----------------|----------------------------------|
| Blood pressure  | CPU load + process queue         |
| Blood test      | Memory usage + Swap + process count |
| Liver function  | Disk I/O + filesystem health     |
| ECG             | Network latency + connections + bandwidth |
| Cancer screening| Security logs + anomalous processes + unauthorized access |
| Family history  | Past incidents + config changes  |

The LLM's role: **ingest all these "lab results" and produce an overall score plus a diagnosis.**

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                  Health Scoring Engine (LLM)                    │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │ Dimension   │  │ Correlation │  │ Trend       │             │
│  │ Scoring     │  │ Analysis    │  │ Prediction  │             │
│  │ CPU/Memory  │  │ Root cause  │  │ Capacity    │             │
│  │ Disk/I/O    │  │ Impact      │  │ Risk        │             │
│  │ Network     │  │ Dependencies│  │             │             │
│  │ Security    │  │             │  │             │             │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘             │
│         └─────────────────┼─────────────────┘                   │
│                           ▼                                     │
│              ┌───────────────────────┐                          │
│              │  Overall Score (0-100) │                          │
│              │  + Weighted dimension  │                          │
│              │  + Narrative diagnosis │                          │
│              └───────────────────────┘                          │
├─────────────────────────────────────────────────────────────────┤
│                     Data Collection Layer                       │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐   │
│  │ Prometheus│  │ journald │  │  custom  │  │  security    │   │
│  │  metrics │  │  logs    │  │  scripts │  │  audit logs  │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Step 1: Define Health Score Dimensions

We don't use a single vague "health score"—we **score each dimension separately then aggregate**. That's what makes it actionable.

### Six Core Dimensions

```yaml
# config/health_dimensions.yaml
dimensions:
  cpu:
    weight: 0.20          # 20% of total score
    sources:
      - prometheus:node_cpu_seconds_total
      - prometheus:process_cpu_usage
    thresholds:
      critical: 90        # 0-60 points
      warning:  75        # 60-80 points
      normal:   50        # 80-100 points

  memory:
    weight: 0.15
    sources:
      - prometheus:node_memory_MemAvailable_bytes
      - prometheus:node_memory_SwapTotal_bytes
    thresholds:
      critical: 90        # Available < 10%
      warning:  75
      normal:   50

  disk:
    weight: 0.15
    sources:
      - prometheus:node_filesystem_avail_bytes
      - custom: disk_io_latency
    thresholds:
      critical: 85        # Available < 15%
      warning:  70
      normal:   50

  network:
    weight: 0.15
    sources:
      - prometheus:node_network_receive_errors_total
      - prometheus:node_network_transmit_errors_total
      - custom: tcp_connections
    thresholds:
      critical: 5         # Erroneous connections > 5
      warning:  2
      normal:   0

  security:
    weight: 0.20        # Highest weight — any critical fails the exam
    sources:
      - custom: failed_ssh_logins
      - custom: unexpected_processes
      - custom: open_suspicious_ports
    thresholds:
      critical: 1         # Any match
      warning:  0         # Borderline
      normal:   0

  stability:
    weight: 0.15
    sources:
      - custom: uptime_hours
      - custom: restart_count_24h
      - custom: oom_kill_events
    thresholds:
      critical: 0         # OOM or restart in 24h
      warning:  1         # Anomalous but manageable
      normal:   0
```

### Aggregation Formula

```
Total Score = Σ(Dimension Score × Weight)

Hard rules:
- If security.critical → max score capped at 50
- If cpu.critical AND memory.critical → max score capped at 40
```

---

## Step 2: Data Collection Script

This is the foundation—gathering scattered metrics into a structured "physical exam form".

```python
#!/usr/bin/env python3
"""Collect VPS health metrics, output structured JSON."""

import json
import subprocess
import psutil
from datetime import datetime

def get_cpu_metrics():
    load_avg = psutil.getloadavg()
    cpu_percent = psutil.cpu_percent(interval=1)
    return {
        "cpu_percent": cpu_percent,
        "load_1min": load_avg[0],
        "load_5min": load_avg[1],
        "load_15min": load_avg[2],
        "cpu_count": psutil.cpu_count()
    }

def get_memory_metrics():
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()
    return {
        "mem_total_gb": round(mem.total / 1e9, 2),
        "mem_available_gb": round(mem.available / 1e9, 2),
        "mem_used_percent": mem.percent,
        "swap_total_gb": round(swap.total / 1e9, 2),
        "swap_used_percent": swap.percent,
        "mem_free_percent": round(mem.available / mem.total * 100, 1)
    }

def get_disk_metrics():
    disk = psutil.disk_usage("/")
    io = psutil.disk_io_counters()
    return {
        "disk_total_gb": round(disk.total / 1e9, 2),
        "disk_used_gb": round(disk.used / 1e9, 2),
        "disk_free_gb": round(disk.free / 1e9, 2),
        "disk_used_percent": disk.percent,
        "read_bytes": io.read_bytes if io else 0,
        "write_bytes": io.write_bytes if io else 0
    }

def get_network_metrics():
    net = psutil.net_io_counters()
    conn = psutil.net_connections()
    tcp_count = sum(1 for c in conn if c.type.name == "STREAM")
    error_count = sum(1 for c in conn
                      if c.status in ("TIME_WAIT", "CLOSE_WAIT")
                      and c.pid is None)
    return {
        "bytes_sent": net.bytes_sent,
        "bytes_recv": net.bytes_recv,
        "tcp_connections": tcp_count,
        "zombie_connections": error_count,
        "packets_sent": net.packets_sent,
        "packets_recv": net.packets_recv
    }

def get_security_metrics():
    failed_logins = 0
    try:
        result = subprocess.run(
            ["journalctl", "-u", "ssh", "--since", "24hours",
             "--no-pager", "-q"],
            capture_output=True, text=True
        )
        failed_logins = result.stdout.count("Failed password")
    except Exception:
        pass

    suspicious_ports = []
    std_ports = {22, 80, 443, 3000, 8080, 8443, 9090, 9100}
    try:
        for conn in psutil.net_connections(kind='inet'):
            if conn.status == 'LISTEN' and conn.pid:
                if conn.laddr.port not in std_ports:
                    suspicious_ports.append(conn.laddr.port)
    except Exception:
        pass

    return {
        "failed_ssh_logins_24h": failed_logins,
        "suspicious_listening_ports": suspicious_ports
    }

def get_stability_metrics():
    uptime = psutil.boot_time()
    uptime_hours = (datetime.now().timestamp() - uptime) / 3600

    oom_kills = 0
    try:
        result = subprocess.run(
            ["dmesg", "-T", "--level", "err,warn"],
            capture_output=True, text=True
        )
        oom_kills = result.stdout.count("Out of memory")
    except Exception:
        pass

    return {
        "uptime_hours": round(uptime_hours, 1),
        "oom_kill_events": oom_kills
    }

def collect_all():
    data = {
        "timestamp": datetime.now().isoformat(),
        "hostname": subprocess.check_output(
            ["hostname"], text=True
        ).strip(),
        "cpu": get_cpu_metrics(),
        "memory": get_memory_metrics(),
        "disk": get_disk_metrics(),
        "network": get_network_metrics(),
        "security": get_security_metrics(),
        "stability": get_stability_metrics()
    }
    return data

if __name__ == "__main__":
    import sys
    output = collect_all()
    print(json.dumps(output, indent=2, ensure_ascii=False))
```

Run it:
```bash
python3 collect_health.py > /tmp/health_snapshot.json
```

---

## Step 3: LLM-Powered Health Report Generation

This is the core—handing raw metrics to an LLM and getting back a structured diagnosis.

### 3.1 Prompt Design

```python
# scripts/health_analyzer.py

SYSTEM_PROMPT = """You are a senior SRE (Site Reliability Engineer) who excels at diagnosing server health from multi-dimensional data.

Your output must strictly follow this JSON structure:
{
  "overall_score": 0-100 integer,
  "grade": "A/B/C/D/F",
  "dimensions": {
    "cpu":     {"score": 0-100, "status": "healthy/warning/critical", "detail": "..."},
    "memory":  {"score": 0-100, "status": "healthy/warning/critical", "detail": "..."},
    "disk":    {"score": 0-100, "status": "healthy/warning/critical", "detail": "..."},
    "network": {"score": 0-100, "status": "healthy/warning/critical", "detail": "..."},
    "security":{"score": 0-100, "status": "healthy/warning/critical", "detail": "..."},
    "stability":{"score": 0-100, "status": "healthy/warning/critical", "detail": "..."}
  },
  "risk_level": "low/medium/high/critical",
  "issues": [
    {"severity": "critical/warning/info", "dimension": "...", "description": "...", "suggestion": "..."}
  ],
  "summary": "A 2-3 sentence overall health summary, professional but conversational",
  "action_items": ["Priority action 1", "Priority action 2"]
}

Scoring rules:
- If security is critical, max total score = 50
- If both CPU and memory are critical, max total score = 40
- Grade: A(90-100) B(80-89) C(70-79) D(60-69) F(<60)
"""

USER_PROMPT_TEMPLATE = """Analyze the following VPS health data and generate a health report:

Hostname: {hostname}
Collection time: {timestamp}

=== CPU ===
Usage: {cpu_percent}%
Load (1/5/15 min): {load_1min}/{load_5min}/{load_15min}
CPU cores: {cpu_count}

=== Memory ===
Used: {mem_used_percent}%
Available: {mem_available_gb} GB / Total {mem_total_gb} GB
Swap usage: {swap_used_percent}%

=== Disk ===
Used: {disk_used_percent}%
Free: {disk_free_gb} GB / Total {disk_total_gb} GB
Write volume: {write_bytes_human}

=== Network ===
TCP connections: {tcp_connections}
Zombie connections (CLOSE_WAIT/TIME_WAIT): {zombie_connections}
Traffic: {recv_mb:.1f}MB received / {sent_mb:.1f}MB sent

=== Security ===
Failed SSH logins (24h): {failed_logins}
Suspicious listening ports: {suspicious_ports}

=== Stability ===
Uptime: {uptime_hours} hours
OOM kills (24h): {oom_kills}

Output a complete JSON health report."""
```

### 3.2 Calling the LLM

```python
import openai
from dotenv import load_dotenv
import json

load_dotenv()

def analyze_health(raw_data: dict) -> dict:
    """Call LLM to generate health scoring report."""

    write_bytes = raw_data["disk"]["write_bytes"]
    write_human = f"{write_bytes / 1e9:.1f} GB" if write_bytes > 1e9 else f"{write_bytes / 1e6:.1f} MB"
    recv_mb = raw_data["network"]["bytes_recv"] / 1e6
    sent_mb = raw_data["network"]["bytes_sent"] / 1e6

    prompt = USER_PROMPT_TEMPLATE.format(
        hostname=raw_data["hostname"],
        timestamp=raw_data["timestamp"],
        **raw_data["cpu"],
        **raw_data["memory"],
        **raw_data["disk"],
        write_bytes_human=write_human,
        **raw_data["network"],
        recv_mb=recv_mb,
        sent_mb=sent_mb,
        **raw_data["security"],
        **raw_data["stability"],
    )

    response = openai.chat.completions.create(
        model="deepseek-chat",   # or local Ollama model
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        temperature=0.2,
        max_tokens=1500,
        response_format={"type": "json_object"}
    )

    report = json.loads(response.choices[0].message.content)
    report = apply_hard_rules(report, raw_data)
    return report

def apply_hard_rules(report: dict, raw: dict) -> dict:
    """Apply hardcoded rules to override LLM judgment."""
    if report["dimensions"]["security"]["status"] == "critical":
        report["overall_score"] = min(report["overall_score"], 50)
        if report["overall_score"] < 60:
            report["grade"] = "F"
        elif report["overall_score"] < 70:
            report["grade"] = "D"

    if (report["dimensions"]["cpu"]["status"] == "critical" and
        report["dimensions"]["memory"]["status"] == "critical"):
        report["overall_score"] = min(report["overall_score"], 40)
        report["grade"] = "F"

    return report
```

### 3.3 Sample Output

```bash
$ python3 collect_health.py | python3 analyze_health.py
```

**Output:**

```json
{
  "overall_score": 72,
  "grade": "C",
  "dimensions": {
    "cpu":      {"score": 90, "status": "healthy",  "detail": "Load normal, no bottleneck"},
    "memory":   {"score": 85, "status": "healthy",  "detail": "Memory充裕, Swap unused"},
    "disk":     {"score": 45, "status": "warning",  "detail": "Root partition at 87%, cleanup needed"},
    "network":  {"score": 95, "status": "healthy",  "detail": "Connections normal, no anomalies"},
    "security": {"score": 10, "status": "critical", "detail": "47 SSH brute-force attempts in 24h"},
    "stability":{"score": 80, "status": "healthy", "detail": "Uptime 15 days, no incidents"}
  },
  "risk_level": "high",
  "issues": [
    {
      "severity": "critical",
      "dimension": "security",
      "description": "47 SSH brute-force attempts detected from distributed IPs — likely scanning attack",
      "suggestion": "Deploy Fail2Ban immediately, enforce SSH key-only authentication, disable password auth"
    },
    {
      "severity": "warning",
      "dimension": "disk",
      "description": "Root partition at 87%, growing at ~1.2% per day",
      "suggestion": "Clean old logs in /var/log, compress stale journal files"
    }
  ],
  "summary": "Server runs stably overall, but two issues need attention: security score is only 10 (frequent SSH brute-force), and disk space is tightening (87% used). Prioritize security hardening and schedule disk cleanup.",
  "action_items": [
    "【URGENT】Deploy Fail2Ban and enable SSH key-only auth",
    "【This week】Clean old logs to bring disk usage below 75%",
    "【Observe】Re-check next week to confirm disk growth rate"
  ]
}
```

---

## Step 4: Scheduling & Notifications

The value of health scoring lies in **regular execution**—making trends visible over time.

### 4.1 Cron Schedule

```bash
# crontab -e
# Daily health check during low-traffic window (3 AM)
0 3 * * * cd /opt/vps-health && ./run_health_check.sh >> /var/log/health_check.log 2>&1

# Weekly summary report every Monday at 9 AM
0 9 * * 1 cd /opt/vps-health && ./generate_weekly_report.sh
```

### 4.2 Notification Routing

```python
# scripts/notify.py
import smtplib
import requests
from email.mime.text import MIMEText

def send_notification(report: dict):
    score = report["overall_score"]
    summary = report["summary"]

    if score >= 80:
        # Healthy: daily digest to Telegram group
        send_telegram(summary, channel="daily-health")
    elif score >= 60:
        # Fair: Telegram + email
        send_telegram(f"⚠️ VPS Health Score: {score}/100\n{summary}", channel="alerts")
        send_email(report, subject=f"[VPS Health] Score {score} - Needs Attention")
    else:
        # Poor: Telegram + email + PagerDuty
        send_telegram(f"🚨 VPS Health Score: {score}/100 — Immediate action required!\n{summary}",
                      channel="urgent")
        send_email(report, subject=f"🚨 [URGENT] VPS Health Score {score}", priority="high")
        pagerduty_trigger(report)
```

### 4.3 Historical Trend Storage

```python
import duckdb

def save_report(report: dict, raw_data: dict):
    conn = duckdb.connect("/opt/vps-health/health_history.duckdb")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS health_snapshots (
            timestamp TIMESTAMP,
            hostname VARCHAR,
            overall_score INTEGER,
            grade VARCHAR,
            risk_level VARCHAR,
            cpu_score INTEGER,
            memory_score INTEGER,
            disk_score INTEGER,
            network_score INTEGER,
            security_score INTEGER,
            stability_score INTEGER,
            raw_data JSON
        )
    """)
    conn.execute("INSERT INTO health_snapshots VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                 [
                     report.get("timestamp"),
                     raw_data["hostname"],
                     report["overall_score"],
                     report["grade"],
                     report["risk_level"],
                     report["dimensions"]["cpu"]["score"],
                     report["dimensions"]["memory"]["score"],
                     report["dimensions"]["disk"]["score"],
                     report["dimensions"]["network"]["score"],
                     report["dimensions"]["security"]["score"],
                     report["dimensions"]["stability"]["score"],
                     json.dumps(raw_data)
                 ])
    conn.close()
```

---

## Multi-VPS Dashboard

When managing multiple servers, you need a **global health view**:

```
┌──────────────────────────────────────────────────────────────┐
│  VPS Health Overview    Updated 03:00 UTC                    │
├──────────┬────────┬────────┬────────┬────────┬───────────────┤
│ Host     │ Score  │ Grade  │ Risk   │ Secure │ Top Issue     │
├──────────┼────────┼────────┼────────┼────────┼───────────────┤
│ web-01   │ 🟢 92  │ A      │ Low    │ OK     │ None           │
│ web-02   │ 🟡 74  │ C      │ Medium │ ⚠️ Weak│ SSH brute force│
│ db-01    │ 🔴 38  │ F      │ High   │ OK     │ Disk 94% + OOM │
│ api-01   │ 🟢 88  │ B      │ Low    │ OK     │ None           │
│ cache-01 │ 🟡 79  │ C      │ Medium │ OK     │ High Swap usage│
└──────────┴────────┴────────┴────────┴────────┴───────────────┘
```

Query last 30 days trend:
```sql
SELECT
    hostname,
    AVG(overall_score) AS avg_score,
    MIN(overall_score) AS min_score,
    COUNT(CASE WHEN risk_level = 'critical' THEN 1 END) AS critical_count
FROM health_snapshots
WHERE timestamp > NOW() - INTERVAL '30 days'
GROUP BY hostname
ORDER BY avg_score ASC;
```

---

## Full Deployment

### Dependencies

```bash
pip install psutil openai duckdb python-dotenv
```

### Project Structure

```
/opt/vps-health/
├── config/
│   ├── dimensions.yaml        # Scoring dimension config
│   └── llm_config.yaml        # LLM API config
├── scripts/
│   ├── collect_health.py      # Metric collection
│   ├── analyze_health.py      # LLM analysis
│   ├── notify.py              # Notification routing
│   └── dashboard.py           # Dashboard queries
├── run_health_check.sh        # Main entry point
└── health_history.duckdb      # Historical data
```

### Main Entry Script

```bash
#!/bin/bash
# run_health_check.sh
set -e

cd /opt/vps-health

# 1. Collect metrics
echo "[$(date)] Collecting health metrics..."
python3 scripts/collect_health.py > /tmp/health_raw.json

# 2. LLM analysis
echo "[$(date)] Generating health report via LLM..."
python3 scripts/analyze_health.py /tmp/health_raw.json > /tmp/health_report.json

# 3. Save to history
python3 -c "
import json, sys
sys.path.insert(0, 'scripts')
from notify import save_report
with open('/tmp/health_raw.json') as f: raw = json.load(f)
with open('/tmp/health_report.json') as f: report = json.load(f)
save_report(report, raw)
"

# 4. Send notifications
python3 scripts/notify.py /tmp/health_report.json

echo "[$(date)] Health check complete"
```

---

## Why This System Matters

| Traditional Approach | AI Health Scoring System |
|---------------------|--------------------------|
| Alert only when threshold breached | Trend-based early warning (3-day decline triggers alert) |
| Operator prioritizes manually | LLM auto-sorts by severity and impact |
| Every incident requires fresh context | Historical reports form a "server medical record" |
| Multi-VPS status requires mental juggling | Dashboard gives at-a-glance global view |

**The core value isn't "another monitoring dashboard"—it's turning scattered metrics into an understandable diagnosis.**

---

## Next Steps & Extensions

1. **Fully offline**: Use Ollama + llama3 instead of cloud API — data never leaves your server
2. **Auto-remediation link**: Score below 60 automatically triggers fix scripts (disk cleanup, service restart)
3. **Cost awareness**: Integrate cloud pricing data to show "cost per healthy hour" and guide resource optimization
4. **Cross-service correlation**: Link health scores with Kubernetes pod status and Docker container health for full-stack visibility

---

*Next up: "AI + VPS: Multi-Agent Collaboration for Intelligent Self-Healing — The Complete Closed Loop of Scoring, Root Cause Analysis, and Auto-Fix"*

*Sample code: [GitHub Gist](https://gist.github.com/selfvps/health-scoring)*