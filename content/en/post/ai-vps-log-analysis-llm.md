---
title: "AI-Powered VPS Log Analysis: Automatically Detect Anomalies and Security Threats from Massive Logs with LLMs"
description: "VPS servers generate gigabytes of logs daily — manually sifting through them is like finding a needle in a haystack. Build an AI log analysis system using Filebeat, Loki, and LLMs to instantly surface anomalies, attacks, and issues from millions of log lines."
date: 2026-06-05T21:30:00+08:00
slug: "ai-vps-log-analysis-llm"
tags: ["AI Log Analysis", "LLM", "VPS Operations", "Security Monitoring", "Loki", "Filebeat", "Anomaly Detection", "Automation"]
categories: ["AI Operations"]
image: /images/posts/ai-vps-log-analysis-llm/featured.png
draft: false
---

One of the most dreaded tasks in VPS management is **reading logs**.

When something goes wrong, your first instinct is to check the logs. But when you run `tail -f /var/log/syslog` or `journalctl -xe`, you're greeted by an endless wall of text — hundreds of megabytes or even gigabytes of log data. Manually combing through this takes hours. Worse, many security attack signals hide in the lines you'd naturally skip over.

What if you could plug an LLM (Large Language Model) into your log pipeline? It could:

- Analyze log streams in real-time, flag abnormal behavior
- Describe what happened in plain English (no more staring at hex dumps)
- Correlate multiple log entries to reconstruct attack chains
- Notify you before a suspicious event becomes a full-blown incident

This guide walks you through building an AI log analysis system from scratch — all open-source, all running on your own VPS.

## Architecture Overview

```
App/System Logs → Filebeat → Loki → Grafana (Visualization)
                                       ↓
                                 AI Log Analyzer (LLM)
                                       ↓
                             Anomaly Alert → Telegram/Email
                                       ↓
                             AI Analysis Report (Natural Language)
```

**Core Components:**

| Component | Role | Why This One |
|-----------|------|-------------|
| Filebeat | Lightweight log shipper | Minimal resource usage, supports many inputs |
| Loki | Log aggregation & storage | Lighter than ELK, low indexing cost |
| Grafana | Dashboard + Alert engine | Rich ecosystem, native Loki integration |
| Ollama + LLM | AI analysis engine | Runs locally, data never leaves your server |
| Python Analyzer | Glue code connecting Loki to LLM | Fully customizable analysis logic |

## Step 1: Deploy Loki + Promtail

Let's use Docker Compose for a quick start. Create the project directory:

```bash
mkdir -p ~/ai-log-system && cd ~/ai-log-system
```

Create `docker-compose.yml`:

```yaml
version: "3.9"

services:
  loki:
    image: grafana/loki:3.0.0
    ports:
      - "3100:3100"
    volumes:
      - ./loki-config.yml:/etc/loki/local-config.yaml
      - loki-data:/loki
    command: -config.file=/etc/loki/local-config.yaml
    restart: unless-stopped

  promtail:
    image: grafana/promtail:3.0.0
    volumes:
      - /var/log:/var/log:ro
      - ./promtail-config.yml:/etc/promtail/config.yml
    command: -config.file=/etc/promtail/config.yml
    restart: unless-stopped

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin123
    volumes:
      - grafana-data:/var/lib/grafana
    restart: unless-stopped

volumes:
  loki-data:
  grafana-data:
```

Create `loki-config.yml`:

```yaml
auth_enabled: false

server:
  http_listen_port: 3100

ingester:
  lifecycler:
    address: 127.0.0.1
    ring:
      kvstore:
        store: inmemory
      replication_factor: 1
  chunk_idle_period: 5m
  chunk_retain_period: 30s

schema_config:
  configs:
    - from: 2020-10-24
      store: boltdb-shipper
      object_store: filesystem
      schema: v11
      index:
        prefix: index_
        period: 24h

storage_config:
  boltdb_shipper:
    active_index_directory: /loki/index
    cache_location: /loki/cache
  filesystem:
    directory: /loki/chunks

limits_config:
  enforce_metric_name: false
  reject_old_samples: true
  reject_old_samples_max_age: 168h
```

Create `promtail-config.yml`:

```yaml
server:
  http_listen_port: 9080
  grpc_listen_port: 0

positions:
  filename: /tmp/positions.yaml

clients:
  - url: http://loki:3100/loki/api/v1/push

scrape_configs:
  - job_name: syslog
    static_configs:
      - targets: [localhost]
        labels:
          job: syslog
          host: vps1
          __path__: /var/log/syslog

  - job_name: auth_log
    static_configs:
      - targets: [localhost]
        labels:
          job: auth
          host: vps1
          __path__: /var/log/auth.log

  - job_name: nginx_access
    static_configs:
      - targets: [localhost]
        labels:
          job: nginx_access
          host: vps1
          __path__: /var/log/nginx/access.log

  - job_name: nginx_error
    static_configs:
      - targets: [localhost]
        labels:
          job: nginx_error
          host: vps1
          __path__: /var/log/nginx/error.log

  - job_name: docker_logs
    static_configs:
      - targets: [localhost]
        labels:
          job: docker
          host: vps1
          __path__: /var/lib/docker/containers/*/*-json.log
```

Start the services:

```bash
docker compose up -d
```

Visit `http://your-vps-ip:3000`, login with `admin` / `admin123`, add Loki as a data source (URL: `http://loki:3100`), and you'll see real-time log streams in the Explore panel.

## Step 2: Deploy Ollama + Log Analysis Model

Now let's make AI do the heavy lifting. Deploy Ollama locally and pull a model that excels at log and code analysis:

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Recommended models (choose based on your VPS RAM)
ollama pull qwen2.5:7b       # 7B params, friendly to 8GB VPS
ollama pull deepseek-r1:8b   # Better reasoning, recommend 16GB+
```

> **Memory Guide**: For VPS with 4GB or less, use `qwen2.5:3b` or 4-bit quantized models. For 8GB+, `qwen2.5:7b` or `deepseek-r1:8b` work well. For 16GB+, try `qwen2.5:14b`.

Test the model:

```bash
ollama run qwen2.5:7b "Analyze this log line: 'Failed password for root from 203.0.113.42 port 22 ssh2'. What type of attack is this?"
```

## Step 3: Build the AI Log Analyzer

This is the heart of the system — a Python script that periodically pulls fresh logs from Loki, sends them to the LLM for analysis, and outputs anomaly alerts.

Create `ai_log_analyzer.py`:

```python
#!/usr/bin/env python3
"""
AI Log Analyzer — Fetch logs from Loki → LLM analysis → Alert output
"""

import json
import os
import time
import requests
from datetime import datetime, timedelta
from typing import Optional

# ── Configuration ─────────────────────────────────────
LOKI_URL = "http://localhost:3100"
OLLAMA_URL = "http://localhost:11434"
MODEL = "qwen2.5:7b"          # or deepseek-r1:8b
CHECK_INTERVAL = 120           # Check every 2 minutes
LOOKBACK_MINUTES = 10          # Analyze last 10 minutes of logs
NOTIFY_ENABLED = False         # Set to True to enable Telegram
TELEGRAM_BOT_TOKEN = ""
TELEGRAM_CHAT_ID = ""
SUSPICIOUS_PATTERNS = [
    "Failed password", "Invalid user", "BREACH", "SQL injection",
    "segfault", "OOM", "out of memory", "disk full",
    "Connection refused", "permission denied",
    "error connecting to upstream",
    "possible SYN flooding", "DDoS", "rate limit exceeded",
]
# ──────────────────────────────────────────────────────


def query_loki(query: str, minutes: int = LOOKBACK_MINUTES) -> list:
    """Query logs from Loki, returns list of log lines"""
    now = datetime.now()
    start = now - timedelta(minutes=minutes)

    params = {
        "query": query,
        "start": start.timestamp(),
        "end": now.timestamp(),
        "limit": 2000,
    }

    try:
        resp = requests.get(
            f"{LOKI_URL}/loki/api/v1/query_range",
            params=params,
            timeout=30,
        )
        if resp.status_code != 200:
            print(f"[ERROR] Loki query failed: {resp.status_code}")
            return []

        data = resp.json()
        logs = []
        for stream in data.get("data", {}).get("result", []):
            for ts, line in stream.get("values", []):
                logs.append(line)
        return logs

    except Exception as e:
        print(f"[ERROR] Loki communication error: {e}")
        return []


def filter_suspicious(logs: list) -> list:
    """Pre-filter obviously abnormal logs"""
    suspicious = []
    for line in logs:
        for pattern in SUSPICIOUS_PATTERNS:
            if pattern.lower() in line.lower():
                suspicious.append(line)
                break
    return suspicious


def analyze_with_llm(logs: list, max_lines: int = 100) -> Optional[str]:
    """Analyze logs with LLM, returns analysis report"""
    if not logs:
        return None

    sample = logs[:max_lines]
    log_text = "\n".join(sample)

    prompt = f"""You are a senior DevOps engineer and cybersecurity expert. Below are the latest log entries from a VPS (last 10 minutes). Please analyze and answer:

1. **Are there any anomalies or security threats?** If yes, rate severity (CRITICAL/HIGH/MEDIUM/LOW)
2. **Attack type identification**: SSH brute force? SQL injection? Web scanning? Memory overflow?
3. **Affected services and processes**
4. **Recommended remediation steps**
5. **Summary**: One sentence describing the current situation

Log content:
```
{log_text}
```

Answer in English, following the structure above. If everything looks normal, state "System operating normally"."""

    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "options": {"temperature": 0.1, "num_ctx": 8192},
            },
            timeout=120,
        )

        if resp.status_code != 200:
            print(f"[ERROR] Ollama API error: {resp.status_code}")
            return None

        result = resp.json()
        return result["message"]["content"]

    except Exception as e:
        print(f"[ERROR] LLM call failed: {e}")
        return None


def send_telegram(message: str):
    """Send Telegram alert"""
    if not NOTIFY_ENABLED:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    requests.post(url, json={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": f"🤖 AI Log Analysis Alert\n\n{message}",
        "parse_mode": "HTML",
    }, timeout=10)


def main():
    print(f"[INFO] AI Log Analyzer started — Model: {MODEL}, Interval: {CHECK_INTERVAL}s")

    jobs = [
        '{job="syslog"}',
        '{job="auth"}',
        '{job="nginx_access"}',
        '{job="nginx_error"}',
        '{job="docker"}',
    ]

    while True:
        all_suspicious = []
        for job in jobs:
            logs = query_loki(job)
            suspicious = filter_suspicious(logs)
            if suspicious:
                print(f"[INFO] {job}: Found {len(suspicious)} suspicious log entries")
                all_suspicious.extend(suspicious)

        if all_suspicious:
            report = analyze_with_llm(all_suspicious)
            if report:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                output = f"=== AI Log Analysis Report [{timestamp}] ===\n{report}\n"
                print(output)

                with open("ai_log_reports.txt", "a", encoding="utf-8") as f:
                    f.write(output + "\n")

                if "CRITICAL" in report or "HIGH" in report:
                    send_telegram(f"<b>Critical Level Anomaly</b>\n\n{report}")
            else:
                print("[INFO] No anomalies detected")
        else:
            print(f"[INFO] {datetime.now().strftime('%H:%M:%S')} — No suspicious logs found")

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
```

Run the analyzer:

```bash
chmod +x ai_log_analyzer.py
# Test in foreground first
python3 ai_log_analyzer.py

# Once confirmed working, set up as a systemd service
sudo tee /etc/systemd/system/ai-log-analyzer.service << 'EOF'
[Unit]
Description=AI Log Analyzer
After=docker.service

[Service]
Type=simple
WorkingDirectory=/root/ai-log-system
ExecStart=/usr/bin/python3 /root/ai-log-system/ai_log_analyzer.py
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now ai-log-analyzer
```

## Step 4: Integrate AI Analysis in Grafana

Beyond raw log queries, let's display AI analysis results right in Grafana.

### Add a Markdown Panel

Create a dashboard in Grafana and add a **Text** panel (Markdown mode):

```markdown
# 🤖 AI Log Analysis

## Live Status
Last Analysis: **${__from:date:YYYY-MM-DD HH:mm:ss}**

> AI Log Analyzer scans all log sources every 2 minutes, detecting anomalies and threats.

## Log Sources
- 🔴 System Log (syslog)
- 🔴 SSH Auth Log (auth.log)
- 🔴 Nginx Access Log
- 🔴 Nginx Error Log
- 🔴 Docker Container Logs
```

### Loki Queries with Alert Panels

Add Loki query panels to visualize anomaly spikes via `rate`:

```
rate({job="auth"} |= "Failed password"[5m])
```

### Configure Alert Rules

In Grafana Alerting, create rules to trigger when anomaly patterns spike:

```yaml
# Example: SSH brute force detection
# Alert when Failed password appears >20 times in 5 minutes
expr: |
  sum(rate({job="auth"} |= "Failed password"[5m])) > 0.07
for: 2m
labels:
  severity: critical
annotations:
  summary: "SSH Brute Force Attack Detected"
  description: "Detected {{ $value | humanize }} failed attempts/sec in last 5 minutes"
```

## Real-World Scenarios

### Scenario 1: SSH Brute Force Attack

When your VPS is exposed to the internet, SSH login attempts happen constantly. AI analysis output:

```
=== AI Log Analysis Report [2026-06-05 20:15:00] ===

1. **Anomaly Detection**: ⚠️ Severity: HIGH
2. **Attack Type**: SSH Brute Force
   - Source IPs: 185.220.101.42, 203.0.113.88, 91.121.87.34
   - Attempted Users: root, admin, ubuntu, test
   - Frequency: ~40 attempts/minute
3. **Affected Service**: sshd (port 22)
4. **Recommended Actions**:
   - Change SSH port immediately
   - Enable fail2ban for auto-blocking
   - Disable root password login, use SSH keys only
5. **Summary**: VPS is under large-scale SSH brute force attack — recommend immediate SSH hardening
```

### Scenario 2: Application Memory Leak

Your web app starts consuming increasing memory. The analyzer finds `OOM` and `segfault` in Docker logs:

```
=== AI Log Analysis Report [2026-06-05 22:30:00] ===

1. **Anomaly Detection**: ⚠️ Severity: CRITICAL
2. **Issue Type**: Application memory leak leading to OOM
   - Process: node (PID 31248)
   - Log Pattern: "FATAL ERROR: Ineffective mark-compacts near heap limit"
   - Multiple OOM kill records
3. **Affected Service**: web-app (Docker container)
4. **Recommended Actions**:
   - Check Node.js --max-old-space-size setting
   - Add container memory limit (docker run --memory=512m)
   - Analyze heapdump to find leak source
   - Consider horizontal scaling
5. **Summary**: Web app being repeatedly killed by OOM killer due to memory leak — urgent fix needed
```

### Scenario 3: Web Vulnerability Scanner

Nginx logs showing high volumes of 404s and suspicious URL patterns:

```
=== AI Log Analysis Report [2026-06-05 14:00:00] ===

1. **Anomaly Detection**: ⚠️ Severity: MEDIUM
2. **Attack Type**: Web path scanning / vulnerability probing
   - Source IP: 198.51.100.23
   - Scanned paths: /wp-admin, /admin, /.env, /phpmyadmin, /api
   - Request rate: 15 requests/second
3. **Affected Service**: Nginx (port 80/443)
4. **Recommended Actions**:
   - Block scanner IP with CrowdSec or fail2ban
   - Configure WAF rules (e.g., ModSecurity)
   - Hide sensitive paths, add access authentication
5. **Summary**: Web path scan detected from a single IP — auto-blocked by firewall
```

## Advanced Optimizations

### 1. Multi-Model Collaborative Analysis

Different models excel at different tasks. Combine them:

```python
# Lightweight model for pre-filtering
def quick_scan(logs):
    # Use qwen2.5:0.5b to quickly check for anomalies
    pass

# Large model for deep analysis
def deep_analyze(suspicious_logs):
    # Use deepseek-r1:14b for thorough investigation
    pass
```

### 2. Log Context Correlation

Don't look at isolated log lines — correlate related entries within a time window:

```python
# After detecting Failed password, grab all activity from that IP
def correlate_ip(ip_address, time_window=5):
    query = f'{{job="auth"}} |= "from {ip_address}"'
    return query_loki(query, minutes=time_window)
```

### 3. Custom Knowledge Base

Inject your app-specific knowledge via RAG to improve LLM accuracy:

```python
# Tell the LLM your app's specific error codes
context = """
Application Error Codes:
- ERR_DB_CONN: Database connection failed, check DB_HOST in .env
- ERR_RATE_LIMIT: API call rate exceeded, wait 60s for auto-recovery
- ERR_CACHE_MISS: Redis cache missed, core functionality not affected
"""
```

### 4. Automated Remediation

Connect analysis results to automated actions:

```python
def auto_remediate(report):
    if "SSH brute force" in report:
        run_command("sudo killall -USR1 sshd")
        run_command("echo '185.220.101.42' >> /etc/hosts.deny")
    elif "disk space" in report:
        run_command("docker system prune -af")
    elif "Nginx down" in report:
        run_command("systemctl restart nginx")
```

## Resource Usage Benchmarks

On a 4GB RAM, 2-core VPS running the full stack:

| Component | Memory Usage | CPU Usage | Disk Usage |
|-----------|-------------|-----------|-----------|
| Loki | ~200MB | <5% | ~1GB/day (depends on log volume) |
| Promtail | ~30MB | <1% | None persistent |
| Grafana | ~100MB | <2% | ~200MB |
| Ollama (qwen2.5:7b) | ~4.5GB | 60-80% during analysis | ~4GB (model file) |
| Python Analyzer | ~50MB | <5% | None persistent |
| **Total** | **~5GB** | **Spiky during analysis** | **~5GB+** |

> 💡 **Memory-saving tips**: If your VPS is tight on RAM, use `qwen2.5:3b` or `deepseek-r1:1.5b`, or increase the analysis interval to 10 minutes.

## Conclusion

AI-powered log analysis isn't about replacing DevOps engineers — it's about **freeing human time from the drudgery of log spelunking** so you can focus on solving real engineering problems.

Once this system is up and running:

- ✅ **24/7 Automated Monitoring**: All log sources automatically collected and analyzed
- ✅ **AI-Powered Diagnosis**: Not just keyword matching — understanding log context and meaning
- ✅ **Natural Language Reports**: Tells you what happened in plain English
- ✅ **Instant Critical Alerts**: Severe anomalies ping you via Telegram in seconds
- ✅ **Fully Self-Hosted**: Sensitive log data never leaves your VPS

Think of logs as your VPS's medical records — with AI acting as the triage nurse that reads the chart and gives you a diagnosis summary, you can find the root cause and prescribe the fix much faster.

Next steps to explore: Connect AI analysis results to automated remediation actions, creating a true log-driven self-healing loop for your VPS. Similar to the [AI Agent Self-Healing System](/en/post/ai-agent-vps-self-healing/) — from "AI analysis" to "AI action" is just one step away.

May your VPS run stable forever! 🚀
