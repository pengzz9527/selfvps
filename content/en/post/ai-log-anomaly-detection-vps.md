---
title: "AI-Powered Log Anomaly Detection: Building an Automated VPS Monitoring System"
description: "Stop manually sifting through logs: Build an AI-driven log anomaly detection system on your VPS using LLM + time-series databases + notification channels, achieving 24/7 automated operations where anomalies are caught before users even notice"
date: 2026-06-06T21:30:00+08:00
slug: "ai-log-anomaly-detection-vps"
tags: ["AI Operations", "Log Analysis", "Anomaly Detection", "LLM", "VPS Monitoring", "Automation", "ELK", "Time-Series DB", "Promtail", "Grafana"]
categories: ["AI Operations"]
aliases: [/en/post/ai-log-anomaly-detection-vps/]
draft: false
image: /images/posts/ai-log-anomaly-detection-vps/featured.png
---

## Why Does Your VPS Need AI Log Anomaly Detection?

Most VPS users follow a reactive approach: **only check logs when something breaks**. This passive model has several critical flaws:

- **Delayed response** — A user reports your site is down, and *only then* do you start digging through logs
- **Critical signals drowned in noise** — A busy VPS generates tens of thousands of log lines daily; manual screening is practically impossible
- **Pattern recognition is hard** — Slow resource exhaustion, progressive attacks, and intermittent failures are nearly impossible to catch with static threshold alerts
- **Root cause analysis is time-consuming** — Even after detecting an anomaly, pinpointing the real cause requires extensive troubleshooting

**AI-powered log anomaly detection** solves all of these: machine learning models automatically learn the "normal pattern" of your logs, identify deviations in real-time, and notify or even auto-remediate when anomalies are found.

This guide walks you through building a complete AI-driven log anomaly detection system on your VPS, covering the full pipeline: **log collection → storage → anomaly analysis → alerting → automated response**.

---

## System Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        VPS Server                           │
│  ┌──────────┐  ┌───────────┐  ┌──────────┐  ┌───────────┐  │
│  │ Promtail │─▶│ Loki/Time  │─▶│ AI Engine│─▶│ Notifier  │  │
│  │ (Collector) │ │ Series DB │  │ (LLM/    │  │ Email/    │  │
│  └──────────┘  └───────────┘  │ ML Model) │  │ Telegram  │  │
│                               └──────────┘  └───────────┘  │
│       ▲                            │                         │
│       │ Structured Logs            ▼                         │
│  ┌──────────┐              ┌───────────┐                     │
│  │ App Logs  │◀─────────────│ Auto-     │                     │
│  │ Sys Logs  │              │ Response  │                     │
│  │ Container │              └───────────┘                     │
│  │ Logs      │                                                │
│  └──────────┘                                                │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │  External Channels│
                    │  Slack/Telegram  │
                    │  Email/DingTalk  │
                    └─────────────────┘
```

**Core Components:**

| Component | Purpose | Recommended Tool |
|-----------|---------|-----------------|
| Log Collection | Gather logs from all sources | Promtail / Filebeat / Fluent Bit |
| Log Storage | Efficient storage & query | Loki (lightweight) or ELK (full-featured) |
| AI Anomaly Detection | Identify deviations from normal patterns | Custom Python script + LLM API |
| Time-Series DB | Store metrics and alert history | Prometheus / TimescaleDB |
| Notification Channels | Instant alerts on anomalies | Telegram Bot / Email / DingTalk |

---

## Step 1: Deploy Log Infrastructure

### Option A: Lightweight — Loki + Promtail (Recommended for 1-2 Core VPS)

Loki, from Grafana Labs, is a lightweight log system that doesn't build full-text indexes — it only uses labels. Extremely low resource footprint (works on 2C2G).

```yaml
# docker-compose.yml
version: "3.8"

services:
  loki:
    image: grafana/loki:2.9.0
    ports:
      - "3100:3100"
    volumes:
      - ./loki-data:/loki
      - ./loki-config.yaml:/etc/loki/local-config.yaml:ro
    command: -config.file=/etc/loki/local-config.yaml
    restart: unless-stopped

  promtail:
    image: grafana/promtail:2.9.0
    volumes:
      - /var/log:/var/log:ro
      - /root/selfvps/logs:/app/logs:ro
      - ./promtail-config.yaml:/etc/promtail/config.yml:ro
    command: -config.file=/etc/promtail/config.yml
    restart: unless-stopped

  # Optional: for time-series metrics
  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - ./prom-data:/prometheus
    restart: unless-stopped
```

### Option B: Full Suite — ELK Stack (Recommended for 4+ Core VPS)

```yaml
# docker-compose.yml for ELK
version: "3.8"

services:
  elasticsearch:
    image: docker.elastic.co/elasticsearch/elasticsearch:8.11.0
    environment:
      - discovery.type=single-node
      - xpack.security.enabled=false
      - "ES_JAVA_OPTS=-Xms1g -Xmx1g"
    volumes:
      - es-data:/usr/share/elasticsearch/data
    ports:
      - "9200:9200"
    restart: unless-stopped

  logstash:
    image: docker.elastic.co/logstash/logstash:8.11.0
    volumes:
      - ./logstash/pipeline/:/usr/share/logstash/pipeline/
    ports:
      - "5044:5044"
      - "5000:5000/tcp"
    restart: unless-stopped

  kibana:
    image: docker.elastic.co/kibana/kibana:8.11.0
    ports:
      - "5601:5601"
    environment:
      ELASTICSEARCH_HOSTS: http://elasticsearch:9200
    restart: unless-stopped

  filebeat:
    image: docker.elastic.co/beats/filebeat:8.11.0
    volumes:
      - /var/log:/var/log:ro
      - ./filebeat.yml:/usr/share/filebeat/filebeat.yml:ro
      - ./filebeat/modules.d/:/usr/share/filebeat/modules.d/:ro
    restart: unless-stopped

volumes:
  es-data:
```

---

## Step 2: Build the AI Anomaly Detection Engine

This is the core of the entire system. We build a detection engine in Python, deployable directly on your VPS.

### 2.1 Install Dependencies

```bash
pip install python-dotenv openai langchain tiktoken psutil
```

### 2.2 Anomaly Detection Script

```python
#!/usr/bin/env python3
"""
VPS AI Log Anomaly Detection Engine
- Periodically fetches logs from Loki/Prometheus
- Uses LLM to analyze log patterns and detect anomalies
- Sends notifications when anomalies are found
"""

import os
import json
import time
import subprocess
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

# LLM API Configuration
LLM_API_KEY = os.getenv("OPENAI_API_KEY", os.getenv("ANTHROPIC_API_KEY", ""))
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")

# Loki endpoint (if not using Loki, can read from syslog or journalctl)
LOKI_URL = os.getenv("LOKI_URL", "http://localhost:3100")

# Notification Configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
SMTP_SERVER = os.getenv("SMTP_SERVER", "")
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "")


def get_recent_logs(lines=500):
    """Fetch recent logs from Loki"""
    end_time = datetime.now().isoformat()
    start_time = (datetime.now() - timedelta(hours=1)).isoformat()
    
    query = f'{{app=~".*"}} | line_format "{{{{.Line}}}}"'
    
    cmd = [
        "curl", "-s",
        f"{LOKI_URL}/loki/api/v1/query_range",
        f"--data-urlencode", f"query={query}",
        f"--data-urlencode", f"start={int(datetime.strptime(start_time, '%Y-%m-%dT%H:%M:%S').timestamp()) * 1000000000}",
        f"--data-urlencode", f"end={int(datetime.strptime(end_time, '%Y-%m-%dT%H:%M:%S').timestamp()) * 1000000000}",
        f"--data-urlencode", "limit=1000"
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        data = json.loads(result.stdout)
        logs = []
        if data.get("data", {}).get("result"):
            for stream in data["data"]["result"]:
                for ts, msg in stream.get("values", []):
                    logs.append(msg)
        return logs[-lines:]  # Last N lines
    
    # Fallback: read from journalctl
    return get_journal_logs(lines)


def get_journal_logs(lines=500):
    """Fetch logs from systemd journal"""
    cmd = ["journalctl", "-n", str(lines), "--no-pager", "-q"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        return result.stdout.strip().split('\n')
    return []


def get_system_metrics():
    """Get system resource metrics"""
    import psutil
    
    metrics = {
        "cpu_percent": psutil.cpu_percent(interval=1),
        "memory_percent": psutil.virtual_memory().percent,
        "disk_percent": psutil.disk_usage('/').percent,
        "load_1m": os.getloadavg()[0] if hasattr(os, 'getloadavg') else 0,
        "boot_time": datetime.fromtimestamp(psutil.boot_time()).isoformat()
    }
    
    # Network I/O
    net = psutil.net_io_counters()
    metrics.update({
        "bytes_sent_mb": round(net.bytes_sent / 1024 / 1024, 2),
        "bytes_recv_mb": round(net.bytes_recv / 1024 / 1024, 2),
    })
    
    # Active connections
    try:
        connections = len(psutil.net_connections(kind='inet'))
        metrics["active_connections"] = connections
    except:
        metrics["active_connections"] = "N/A"
    
    # Process count
    metrics["process_count"] = len(psutil.pids())
    
    return metrics


def analyze_logs_with_llm(logs, metrics):
    """Use LLM to analyze logs and detect anomalies"""
    
    # Build analysis prompt
    system_prompt = """You are a senior SRE (Site Reliability Engineer) specializing in VPS and server operations.
Your task is to analyze server logs and system metrics to identify:
1. **Anomalous Events** — Errors, warnings, or suspicious activities that deviate from normal behavior
2. **Resource Bottlenecks** — Abnormal CPU, memory, disk, or network resource usage
3. **Security Threats** — Intrusion attempts, brute force attacks, unauthorized access
4. **Potential Root Causes** — Root cause analysis of anomalies

Please structure your analysis. Only report genuine anomalies, avoid false positives."""

    user_content = f"""## System Metrics (Current)
{json.dumps(metrics, ensure_ascii=False, indent=2)}

## Recent Logs (Last Hour)
{'\n'.join(logs[:200])}

## Please analyze and report:
1. List of detected anomalies (each with: severity, type, details)
2. Whether immediate action is needed
3. Recommended troubleshooting steps"""

    # Call LLM
    try:
        from openai import OpenAI
        client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)
        
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            temperature=0.1,  # Low temperature for consistency
            max_tokens=2000
        )
        
        return response.choices[0].message.content
    except Exception as e:
        return f"LLM API call failed: {str(e)}"


def classify_severity(analysis_text):
    """Classify severity level from analysis text"""
    lower = analysis_text.lower()
    if any(k in lower for k in ["critical", "severe", "urgent", "security threat", "intrusion", "紧急", "严重"]):
        return "CRITICAL"
    elif any(k in lower for k in ["warning", "alert", "needs action", "警告", "注意"]):
        return "WARNING"
    elif any(k in lower for k in ["anomaly", "deviation", "abnormal", "异常", "偏离"]):
        return "INFO"
    return "OK"


def send_telegram_alert(message, severity="INFO"):
    """Send Telegram alert"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    
    emoji = {"CRITICAL": "🚨", "WARNING": "⚠️", "INFO": "ℹ️"}.get(severity, "📋")
    
    text = f"{emoji} [{severity}] VPS Anomaly Detection\n\n{message}"
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    
    try:
        import urllib.request
        import urllib.parse
        data = urllib.parse.urlencode({"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}).encode()
        req = urllib.request.Request(url, data=data)
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"Telegram send failed: {e}")


def send_email_alert(subject, body):
    """Send email alert"""
    if not SMTP_SERVER or not ADMIN_EMAIL:
        return
    
    import smtplib
    from email.mime.text import MIMEText
    
    msg = MIMEText(body, 'html', 'utf-8')
    msg['Subject'] = subject
    msg['From'] = SMTP_USER
    msg['To'] = ADMIN_EMAIL
    
    try:
        with smtplib.SMTP_SSL(SMTP_SERVER, 465, timeout=10) as server:
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, [ADMIN_EMAIL], msg.as_string())
    except Exception as e:
        print(f"Email send failed: {e}")


def run_detection():
    """Execute a complete anomaly detection cycle"""
    print(f"[{datetime.now().isoformat()}] Starting detection...")
    
    # 1. Fetch logs
    logs = get_recent_logs(lines=300)
    print(f"  Retrieved {len(logs)} log lines")
    
    # 2. Get system metrics
    metrics = get_system_metrics()
    
    # Check hard thresholds (quick filter)
    alert_thresholds = False
    if metrics["cpu_percent"] > 90:
        print("  ⚠️ CPU usage critically high")
        alert_thresholds = True
    if metrics["memory_percent"] > 90:
        print("  ⚠️ Memory usage critically high")
        alert_thresholds = True
    if metrics["disk_percent"] > 90:
        print("  ⚠️ Disk usage critically high")
        alert_thresholds = True
    
    # 3. LLM Analysis
    print("  Analyzing with LLM...")
    analysis = analyze_logs_with_llm(logs, metrics)
    severity = classify_severity(analysis)
    
    print(f"  Analysis complete, severity: {severity}")
    
    # 4. If anomaly found, send notification
    if severity != "OK":
        summary = f"```\n{analysis[:1500]}\n```"
        send_telegram_alert(summary, severity)
        send_email_alert(f"[{severity}] VPS Anomaly Report", f"<pre>{analysis[:3000]}</pre>")
        print(f"  📤 Sent {severity} level alert")
    else:
        print("  ✅ All normal, no alert needed")
    
    # 5. Record detection result
    result = {
        "timestamp": datetime.now().isoformat(),
        "severity": severity,
        "metrics": metrics,
        "analysis": analysis[:500],  # Save summary only
        "logs_count": len(logs)
    }
    
    with open("/root/selfvps/logs/detection_results.json", "a") as f:
        f.write(json.dumps(result, ensure_ascii=False) + "\n")
    
    return severity


if __name__ == "__main__":
    run_detection()
```

### 2.3 Configure .env File

```bash
# /root/selfvps/.env
# LLM API Configuration
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxx
LLM_BASE_URL=https://api.openai.com/v1
# Or use Anthropic
# ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxxxxx
# LLM_BASE_URL=https://api.anthropic.com/v1
# LLM_MODEL=claude-sonnet-4-20250514

# Loki (optional)
LOKI_URL=http://localhost:3100

# Telegram Notification
TELEGRAM_BOT_TOKEN=1234567890:ABCDEF...
TELEGRAM_CHAT_ID=123456789

# Email Notification (optional)
SMTP_SERVER=smtp.gmail.com
SMTP_USER=you@gmail.com
SMTP_PASSWORD=app_password
ADMIN_EMAIL=admin@yourdomain.com
```

### 2.4 Set Up Cron Jobs

```bash
# Run detection every 15 minutes
crontab -e

# Add the following line
*/15 * * * * cd /root/selfvps && /usr/bin/python3 /root/selfvps/scripts/ai_log_detector.py >> /root/selfvps/logs/detector.log 2>&1

# Generate daily report at 2 AM
0 2 * * * cd /root/selfvps && /usr/bin/python3 /root/selfvps/scripts/ai_daily_report.py >> /root/selfvps/logs/daily_report.log 2>&1
```

---

## Step 3: Automated Response (Optional Advanced)

After detecting anomalies, the next step is **auto-remediation**. Here's a simple automated response framework:

```python
#!/usr/bin/env python3
"""
VPS Auto-Response Engine
Automatically executes remediation actions based on AI analysis results
"""

import subprocess
import json
from datetime import datetime

# Define auto-fix rules
AUTO_FIX_RULES = {
    "high_cpu": {
        "condition": lambda m: m.get("cpu_percent", 0) > 90,
        "actions": [
            {"type": "log", "message": "Sustained high CPU load, checking processes..."},
            {"type": "exec", "cmd": "ps aux --sort=-%cpu | head -10"},
            {"type": "alert", "message": "Top CPU processes logged"},
        ]
    },
    "high_memory": {
        "condition": lambda m: m.get("memory_percent", 0) > 90,
        "actions": [
            {"type": "log", "message": "Memory usage critically high"},
            {"type": "exec", "cmd": "free -h"},
            {"type": "exec", "cmd": "ps aux --sort=-%mem | head -10"},
        ]
    },
    "high_disk": {
        "condition": lambda m: m.get("disk_percent", 0) > 90,
        "actions": [
            {"type": "log", "message": "Low disk space, cleaning up..."},
            {"type": "exec", "cmd": "du -sh /var/log/* 2>/dev/null | sort -rh | head -5"},
            {"type": "exec", "cmd": "journalctl --vacuum-time=3d"},
            {"type": "exec", "cmd": "find /tmp -mtime +7 -delete 2>/dev/null"},
        ]
    },
    "brute_force_detected": {
        "condition": None,  # Triggered by AI detection result
        "actions": [
            {"type": "exec", "cmd": "iptables -A INPUT -p tcp --dport 22 -m recent --set"},
            {"type": "exec", "cmd": "iptables -A INPUT -p tcp --dport 22 -m recent --update --seconds 60 --hitcount 5 -j DROP"},
            {"type": "alert", "message": "Brute force detected, IP temporarily blocked"},
        ]
    },
    "service_down": {
        "condition": None,
        "actions": [
            {"type": "exec", "cmd": "systemctl restart <service_name>"},
            {"type": "alert", "message": "Service automatically restarted"},
        ]
    }
}


def execute_auto_fix(rule_name, metrics, ai_analysis):
    """Execute auto-fix based on rule"""
    rule = AUTO_FIX_RULES.get(rule_name)
    if not rule:
        return
    
    # Check condition
    if rule["condition"] and not rule["condition"](metrics):
        return
    
    log_entries = []
    for action in rule["actions"]:
        action_type = action["type"]
        
        if action_type == "log":
            msg = f"[{datetime.now().isoformat()}] {action['message']}"
            log_entries.append(msg)
            print(msg)
        
        elif action_type == "exec":
            cmd = action["cmd"]
            # Safety filter: only allow safe commands
            dangerous = ["rm -rf /", "mkfs", "dd if=", "> /dev/"]
            if any(d in cmd for d in dangerous):
                print(f"  ⛔ Dangerous command blocked: {cmd}")
                continue
            
            result = subprocess.run(cmd, capture_output=True, text=True, shell=True)
            if result.stdout:
                output = result.stdout.strip()
                log_entries.append(f"  > {cmd}\n  {output}")
                print(f"  > {cmd}\n  {output}")
            if result.stderr and "No such" not in result.stderr:
                print(f"  [stderr] {result.stderr.strip()}")
        
        elif action_type == "alert":
            print(f"  📢 {action['message']}")
            log_entries.append(f"📢 {action['message']}")
    
    # Record operation log
    if log_entries:
        with open("/root/selfvps/logs/auto_fix.log", "a") as f:
            f.write(f"=== {rule_name} ===\n")
            f.write("\n".join(log_entries) + "\n\n")
```

---

## Step 4: Visualization & Dashboard

### 4.1 Grafana Integration (for Loki Users)

Add Grafana to your docker-compose:

```yaml
services:
  grafana:
    image: grafana/grafana:10.2.0
    ports:
      - "3001:3000"
    volumes:
      - ./grafana-data:/var/lib/grafana
      - ./grafana/dashboards:/etc/grafana/provisioning/dashboards
      - ./grafana/datasources:/etc/grafana/provisioning/datasources
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=your_strong_password
    restart: unless-stopped
```

### 4.2 Recommended Dashboards

Create `grafana/datasources/loki.yml`:

```yaml
apiVersion: 1

datasources:
  - name: Loki
    type: loki
    access: proxy
    url: http://loki:3100
    isDefault: true
    
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
```

**Recommended Dashboard Panels:**
- 📊 **System Resources Overview** — Real-time CPU/Memory/Disk/Network curves
- 📋 **Log Anomaly Heatmap** — Hourly/daily anomaly density
- 🚨 **Alert History** — Historical alert trends and resolution times
- 🔍 **Quick Log Search** — Supports regex and keyword filtering

### 4.3 AI Daily Report Generator

```python
#!/usr/bin/env python3
"""
Daily AI Operations Report Generator
Generates a VPS health report every day
"""

import json
import os
from datetime import datetime, timedelta

def generate_daily_report():
    """Generate daily report from detection results"""
    log_file = "/root/selfvps/logs/detection_results.json"
    
    if not os.path.exists(log_file):
        return "No detection data today"
    
    # Read today's detection records
    today = datetime.now().strftime("%Y-%m-%d")
    entries = []
    with open(log_file) as f:
        for line in f:
            try:
                entry = json.loads(line.strip())
                if entry.get("timestamp", "").startswith(today):
                    entries.append(entry)
            except:
                continue
    
    if not entries:
        return f"No detection records on {today}"
    
    # Statistics
    severity_counts = {}
    total_anomalies = 0
    for entry in entries:
        sev = entry.get("severity", "OK")
        severity_counts[sev] = severity_counts.get(sev, 0) + 1
        if sev != "OK":
            total_anomalies += 1
    
    report = f"""
📊 VPS Daily Report — {today}
{'='*40}

🔢 Total Checks: {len(entries)}
✅ Normal: {severity_counts.get('OK', 0)}
ℹ️ Minor Anomalies: {severity_counts.get('INFO', 0)}
⚠️ Warnings: {severity_counts.get('WARNING', 0)}
🚨 Critical: {severity_counts.get('CRITICAL', 0)}

📈 Total Anomalies: {total_anomalies}
"""
    
    # Add metric summary
    if entries:
        last = entries[-1]
        metrics = last.get("metrics", {})
        report += f"""
📋 Latest Metrics:
  CPU: {metrics.get('cpu_percent', 'N/A')}%
  Memory: {metrics.get('memory_percent', 'N/A')}%
  Disk: {metrics.get('disk_percent', 'N/A')}%
  Active Connections: {metrics.get('active_connections', 'N/A')}
"""
    
    return report


if __name__ == "__main__":
    report = generate_daily_report()
    print(report)
    
    # Send Telegram
    from ai_log_detector import send_telegram_alert
    send_telegram_alert(report, "INFO")
```

---

## Cost Estimation

| Item | Option A (Loki) | Option B (ELK) |
|------|-----------------|----------------|
| VPS Spec | 1C1G~2C2G | 2C4G~4C8G |
| Monthly Cost | $2~$5 | $8~$25 |
| LLM API (monthly checks) | $0.5~$2 (GPT-4o-mini) | $0.5~$2 |
| Telegram Bot | Free | Free |
| Email | Free (Gmail) | Free |

**Lowest-cost setup:** 1C1G VPS + Loki + GPT-4o-mini ($0.15/1M tokens), total monthly cost under $5.

---

## Advanced Optimization Directions

### 1. Use Local Models to Reduce API Costs

If your VPS has GPU or ample memory (16G+), deploy a lightweight local model:

```bash
# Deploy local model with Ollama
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.2:3b

# Update LLM_BASE_URL to point locally
# LLM_BASE_URL=http://localhost:11434/v1
```

### 2. Rule-Based + AI Hybrid Detection

Use efficient rule-based filtering to eliminate most normal logs first, then send only suspicious logs to the LLM — drastically reducing API call costs:

```python
# Fast rule-based pre-filtering
def quick_filter(logs):
    suspicious = []
    for log in logs:
        # Common anomaly keywords
        if any(kw in log for kw in [
            "SEGFAULT", "OOM", "PANIC", "kernel panic",
            "permission denied", "connection refused",
            "authentication failure", "rate limit",
            "disk full", "out of memory"
        ]):
            suspicious.append(log)
    
    # Only send suspicious logs to LLM
    if suspicious:
        return analyze_with_llm(suspicious)
    return None
```

### 3. Multi-VPS Centralized Monitoring

If you have multiple VPS instances, deploy a centralized AI detection node:

```bash
# Install Promtail on each VPS
# Forward logs to a centralized Loki instance
# Single AI detection engine analyzes all VPS logs
```

### 4. Custom Anomaly Detection Models

For specific applications, train dedicated anomaly detection models:

```python
# Using simple-anomaly-detector or similar libraries
from adtk.detector import FrequencyAD, ThresholdAD

# Train normal pattern from historical data
detector = FrequencyAD(c=3.0)  # 3σ anomaly
alerts = detector.detect(log_volume_series)
```

---

## Summary

This **AI-driven VPS log anomaly detection system** delivers:

1. **Full automation** — 24/7 unattended monitoring
2. **Intelligent analysis** — LLM understands log semantics, far exceeding traditional regex matching
3. **Instant notifications** — Alerts pushed to your phone within seconds of an anomaly
4. **Auto-remediation** — Predefined rules auto-fix common issues
5. **Cost-effective** — Fully functional for under $5/month

Going from manual log-sifting to AI-powered automated monitoring is the next step in VPS operations. Start building your first AI monitoring system today!

---

*Full code examples are available in the repository under `scripts/ai_log_detector.py`. Star and Fork welcome.*
