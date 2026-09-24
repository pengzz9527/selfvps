---
title: "AI + VPS: Local LLM-Powered Traffic Anomaly Detection and Automated WAF Rule Generation"
description: "Use local Ollama + Qwen2.5 to analyze Nginx/Cloudflare traffic logs, automatically detect CC attacks, SQL injection, path traversal and other anomalies, and generate NGINX WAF protection rules in one click"
date: 2026-09-24T21:30:00+08:00
lastmod: 2026-09-24T21:30:00+08:00
slug: "ai-vps-llm-traffic-anomaly-waf-auto"
image: /images/posts/ai-vps-llm-traffic-anomaly-waf-auto/featured.png
tags: ["AI", "VPS", "WAF", "Traffic Analysis", "Anomaly Detection", "Ollama", "Qwen2.5", "Nginx", "Cybersecurity", "Automation"]
categories: ["AI Operations"]
aliases: [/en/post/ai-vps-llm-traffic-anomaly-waf-auto/]
---

## Introduction

Has your VPS website recently experienced a sudden traffic spike? It could be a legitimate promotional campaign driving normal traffic growth—or it could be a malicious CC attack or SQL injection slowly consuming your server resources.

Traditional security monitoring relies on manually configured rules: writing regex patterns for known attack signatures, setting threshold alerts, and manually blocking IPs. The problem is that attackers constantly evolve their techniques, making static rules obsolete quickly. Whenever a new attack pattern emerges, operations staff need to manually analyze logs, write rules, test effectiveness—a response cycle measured in hours or even days.

**Local large language models (LLMs) change this equation.** By deploying Ollama + Qwen2.5 on your VPS, you can build a fully private intelligent traffic analysis system: it parses traffic logs locally, automatically identifies anomalous patterns (CC attacks, SQL injection, path traversal, scraper abuse, etc.), and directly generates usable WAF protection rules—without sending any data to the cloud.

This article walks you through building this system from scratch, achieving a complete closed loop of **log collection → AI analysis → rule generation → automatic deployment**.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                  VPS Local Environment                       │
│                                                             │
│  ┌──────────┐   ┌──────────────┐   ┌──────────────────┐    │
│  │  Nginx   │──▶│  Log Parser  │──▶│   Ollama +       │    │
│  │  Access  │   │  (awk/Python)│   │   Qwen2.5        │    │
│  │  Log     │   │              │   │  (Local LLM)      │    │
│  └──────────┘   └──────────────┘   └────────┬─────────┘    │
│                                             │               │
│                              ┌──────────────▼─────────┐     │
│                              │   AI Analysis Engine    │     │
│                              │  • Anomaly Detection    │     │
│                              │  • Attack Classification│     │
│                              │  • Risk Scoring         │     │
│                              └──────────────┬─────────┘     │
│                                             │               │
│                    ┌────────────────────────┼────────┐      │
│                    │                        │        │      │
│           ┌────────▼────────┐   ┌──────────▼──┐ ┌────▼────┐ │
│           │ WAF Rule        │   │  IP Block   │ │Telegram │ │
│           │ Generator       │   │  Engine     │ │ Alerts  │ │
│           │ (nginx.conf)    │   │  (fail2ban) │ │         │ │
│           └─────────────────┘   └─────────────┘ └──────────┘ │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Step 1: Deploy Local LLM Service

### Install Ollama

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

### Pull Qwen2.5 Model

```bash
# 7B version — suitable for VPS with 4GB+ RAM
ollama pull qwen2.5:7b

# For tighter memory constraints, use the 3B version
# ollama pull qwen2.5:3b
```

### Verify It's Running

```bash
ollama run qwen2.5:7b "Describe in one sentence what model you are"
```

---

## Step 2: Log Collection and Preprocessing

Nginx default access log format typically looks like this:

```
192.168.1.100 - - [24/Sep/2026:14:30:00 +0800] "GET /api/users?id=1 OR 1=1 HTTP/1.1" 403 150 "-" "Mozilla/5.0"
```

We write a Python log parser to extract structured fields:

```python
#!/usr/bin/env python3
"""VPS Traffic Log Parser — extracts structured fields for LLM analysis"""

import re
import json
from datetime import datetime
from collections import defaultdict

# Nginx combined log format regex
LOG_PATTERN = re.compile(
    r'(?P<ip>[\d.:]+)\s+-\s+(?P<user>\S+)\s+'
    r'\[(?P<time>[^\]]+)\]\s+'
    r'"(?P<method>\S+)\s+(?P<path>\S+)\s+(?P<proto>[^"]+)"\s+'
    r'(?P<status>\d+)\s+(?P<size>\d+)\s+'
    r'"(?P<referer>[^"]+)"\s+'
    r'"(?P<ua>[^"]+)"'
)

def parse_log_line(line):
    m = LOG_PATTERN.match(line)
    if not m:
        return None
    d = m.groupdict()
    d['status'] = int(d['status'])
    d['size'] = int(d['size'])
    d['timestamp'] = datetime.strptime(d['time'], '%d/%b/%Y:%H:%M:%S %z')
    return d

def analyze_window(log_path, window_minutes=5):
    """Analyze logs in time windows, returning statistical summary"""
    entries = []
    with open(log_path) as f:
        for line in f:
            entry = parse_log_line(line.strip())
            if entry:
                entries.append(entry)

    if not entries:
        return None

    # Aggregate by IP
    ip_stats = defaultdict(lambda: {
        'count': 0, 'statuses': defaultdict(int),
        'paths': set(), 'uas': set()
    })
    for e in entries:
        ip = e['ip']
        ip_stats[ip]['count'] += 1
        ip_stats[ip]['statuses'][e['status']] += 1
        ip_stats[ip]['paths'].add(e['path'])
        ip_stats[ip]['uas'].add(e['ua'][:50])

    # Extract suspicious patterns
    suspicious_paths = []
    sql_keywords = ['OR 1=1', 'UNION SELECT', "' OR '", '--', ';DROP', '1=1']
    traversal_keywords = ['../', '..\\', '/etc/passwd', '/proc/']

    for e in entries:
        path_upper = e['path'].upper()
        for kw in sql_keywords:
            if kw.upper() in path_upper:
                suspicious_paths.append({
                    'type': 'sql_injection', 'ip': e['ip'],
                    'path': e['path'], 'time': str(e['timestamp'])
                })
                break
        for kw in traversal_keywords:
            if kw in e['path']:
                suspicious_paths.append({
                    'type': 'path_traversal', 'ip': e['ip'],
                    'path': e['path'], 'time': str(e['timestamp'])
                })
                break

    # High-frequency IP detection
    high_freq_ips = {ip: s for ip, s in ip_stats.items()
                     if s['count'] > 100}

    return {
        'total_requests': len(entries),
        'unique_ips': len(ip_stats),
        'high_freq_ips': high_freq_ips,
        'suspicious_paths': suspicious_paths[:20],
        'sample_entries': entries[-10:]
    }
```

---

## Step 3: Build the AI Analysis Engine

This is the core of the system—using Qwen2.5 to analyze traffic summaries, identify attack patterns, and generate WAF rules.

```python
#!/usr/bin/env python3
"""AI Traffic Analysis and WAF Rule Generator"""

import json
import subprocess
import sys

MODEL = "qwen2.5:7b"

ANALYSIS_PROMPT = """You are a professional cybersecurity analyst. Analyze the following VPS traffic data, identify potential security threats, and generate corresponding WAF protection rules.

## Traffic Summary
{traffic_summary}

## Tasks:

### 1. Threat Identification
List all detected anomalous patterns, including:
- Attack type (SQL injection / CC attack / path traversal / scraper abuse, etc.)
- Primary source IPs
- Attack severity (low / medium / high)
- Impact scope

### 2. WAF Rule Generation
Generate directly usable Nginx WAF rules for each attack type
(limit_req_zone or ngx_http_lua_module format).

### 3. Emergency Response Recommendations
If immediate IP blocking is needed, provide fail2ban jail configuration.

Output in JSON format:
{{
  "threats": [...],
  "waf_rules": [...],
  "fail2ban_config": "...",
  "summary": "One-sentence security posture summary"
}}"""


def call_ollama(prompt_text):
    """Call local Ollama API"""
    result = subprocess.run(
        ['ollama', 'run', MODEL, prompt_text],
        capture_output=True, text=True, timeout=120
    )
    if result.returncode != 0:
        raise RuntimeError(f"Ollama error: {result.stderr}")
    return result.stdout.strip()


def extract_json(text):
    """Extract JSON from LLM output"""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    import re
    match = re.search(r'```json\s*(\{.*?\})\s*```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return None
```

---

## Step 4: Scheduled Polling and Telegram Alerts

Add the analysis script to cron, running every 5 minutes:

```bash
# crontab -e
*/5 * * * * /usr/bin/python3 /opt/vps-ai-waf/analyzer.py /var/log/nginx/access.log >> /var/log/vps-ai-waf/cron.log 2>&1
```

Telegram alert integration:

```python
import urllib.request
import json

TELEGRAM_BOT_TOKEN = "YOUR_BOT_TOKEN"
CHAT_ID = "YOUR_CHAT_ID"

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = json.dumps({
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }).encode()
    req = urllib.request.Request(url, data=payload, method='POST')
    urllib.request.urlopen(req)
```

Auto-send alerts when high-severity threats are detected:

```python
high_severity = [t for t in ai_result.get('threats', [])
                 if t.get('severity') == 'high']
if high_severity:
    alert = "🚨 <b>VPS Security Alert</b>\n\n"
    alert += f"Detected {len(high_severity)} high-severity threats:\n"
    for t in high_severity:
        alert += f"• {t['type']}: {t['description'][:80]}\n"
    alert += f"\n📊 Full report: {report_path}"
    send_telegram(alert)
```

---

## Step 5: Real-World Examples

### Scenario: CC Attack Detection

```
Traffic summary shows:
- Requests from 203.0.113.50 in 10 minutes: 2,341
- All request paths: /api/search?q=*
- Status codes: all 200
- User-Agent: consistent, likely automated tool
```

**AI Analysis Result:**

```json
{
  "threats": [{
    "type": "cc_attack",
    "severity": "high",
    "description": "Suspected CC attack: single IP made 2,341 search requests in 10 minutes with highly consistent request patterns",
    "source_ips": ["203.0.113.50"],
    "evidence": ["10min_count=2341", "same_path_ratio=99.2%", "consistent_ua=true"]
  }],
  "waf_rules": [{
    "type": "rate_limiting",
    "directive": "limit_req_zone",
    "config_block": "limit_req_zone $binary_remote_addr zone=search_limit:10m rate=10r/m;\n\nlocation /api/search {\n    limit_req zone=search_limit burst=20 nodelay;\n    limit_req_status 429;\n}"
  }]
}
```

The system automatically writes the `limit_req_zone` rule to `/etc/nginx/conf.d/ai-waf.rules` and reloads Nginx—attacker traffic is rate-limited immediately.

---

### Scenario: SQL Injection Detection

```json
{
  "threats": [{
    "type": "sql_injection",
    "severity": "high",
    "description": "SQL injection attempts detected: URL parameters contain OR 1=1 and UNION SELECT patterns",
    "source_ips": ["198.51.100.23", "198.51.100.44"],
    "evidence": [
      "GET /api/users?id=1' OR '1'='1",
      "GET /api/products?cat=1 UNION SELECT username,password FROM users"
    ]
  }],
  "waf_rules": [{
    "type": "sql_injection_filter",
    "directive": "ngx_lua",
    "config_block": "location / {\n    access_by_lua_block {\n        local args = ngx.var.args\n        if string.find(args, 'OR 1=1', 1, true) then\n            ngx.exit(403)\n        end\n        if string.find(args, 'UNION SELECT', 1, true) then\n            ngx.exit(403)\n        end\n    }\n}"
  }]
}
```

---

## Complete Deployment Script

```bash
#!/bin/bash
# deploy-ai-waf.sh — One-click deployment of AI WAF system

set -e

echo "🔄 Updating system..."
apt update && apt upgrade -y

echo "📦 Installing dependencies..."
apt install -y nginx python3 python3-pip curl

echo "🤖 Installing Ollama..."
curl -fsSL https://ollama.com/install.sh | sh

echo "📥 Pulling Qwen2.5 model..."
ollama pull qwen2.5:7b

echo "📁 Creating project directories..."
mkdir -p /opt/vps-ai-waf /var/log/vps-ai-waf

echo "📝 Deploying scripts..."
cp log_parser.py /opt/vps-ai-waf/
cp ai_waf_analyzer.py /opt/vps-ai-waf/
chmod +x /opt/vps-ai-waf/*.py

echo "🔧 Configuring Nginx rule inclusion..."
echo 'include /etc/nginx/conf.d/ai-waf.rules;' >> /etc/nginx/nginx.conf

echo "⏰ Setting up scheduled task (analysis every 5 minutes)..."
(crontab -l 2>/dev/null; echo '*/5 * * * * /usr/bin/python3 /opt/vps-ai-waf/analyzer.py /var/log/nginx/access.log >> /var/log/vps-ai-waf/cron.log 2>&1') | crontab -

echo "✅ Deployment complete! First analysis will run in 5 minutes."
echo "   View logs: tail -f /var/log/vps-ai-waf/cron.log"
```

---

## Advantages and Considerations

### Core Advantages

| Feature | Traditional Approach | AI-Powered Approach |
|---------|---------------------|---------------------|
| Rule Updates | Manual writing, long cycle | AI auto-generation, minute-level response |
| Unknown Attacks | Cannot detect | Behavior-pattern based identification |
| False Positives | Requires manual tuning | AI reduces false positives using context |
| Data Privacy | May upload to cloud | Fully local, logs never leave the server |
| Cost | WAF cloud service monthly fee | Only ~2GB additional RAM needed |

### Considerations

1. **Resource Usage**: Qwen2.5:7b requires approximately 4-5GB RAM—ensure your VPS has sufficient memory
2. **Analysis Latency**: Each analysis takes about 10-30 seconds; use sliding windows to reduce call frequency
3. **Rule Review**: AI-generated rules should be manually reviewed on first deployment before going fully automatic
4. **Model Selection**: Lower-spec VPS can use `qwen2.5:3b`—slightly lower accuracy but faster response

---

## Summary

By deploying Ollama + Qwen2.5 on your VPS, we've built a fully private intelligent traffic analysis and WAF auto-protection system. It can identify CC attacks, SQL injection, path traversal, and other common threats in real time without relying on any cloud service, and automatically generate and apply Nginx WAF rules.

The core value of this system lies in **shifting security operations from reactive to proactive**—you no longer need to stare at logs worrying; instead, let AI guard your server 24/7, detecting anomalies and responding immediately, while keeping you informed via Telegram at all times.

For individual developers and small teams, this is one of the best paths to enterprise-grade security protection within a limited budget.
