---
title: "AI-Powered VPS Operations: Log Analysis, Fault Prediction & Auto-Remediation with Local LLMs"
description: "Stop scrambling when your VPS breaks. Deploy a local LLM as your 24/7 AI ops engineer — automatically analyze system logs, predict disk/memory bottlenecks, and auto-fix common issues. Complete guide with deploy scripts, works on a 2GB VPS."
date: 2026-05-26T21:30:00+08:00
slug: "ai-driven-vps-operations"
tags: ["AI Ops", "LLM", "Log Analysis", "Automation", "VPS Operations", "Anomaly Detection", "Self-hosting", "Ollama", "Monitoring"]
categories: ["AI Operations"]
image: /images/posts/ai-driven-vps-operations/featured.png
draft: false
---

## Why AI-Powered VPS Operations?

Traditional VPS management is reactive: something breaks → SSH in → grep logs → Google the error → manually fix. It works, but what about 3 AM disk-full alerts, silent service crashes, or slow resource leaks that compound for weeks?

**AI operations flips the script**: deploy a local LLM that continuously reads your system metrics and logs, understands context, flags anomalies, and either notifies you or executes remediation scripts on the spot.

| Capability | Traditional Ops | AI Ops Assistant |
|-----------|----------------|-----------------|
| Log analysis | Manual grep | Semantic understanding with context |
| Incident response | Passive alert → manual fix | Auto-diagnose → execute remediation |
| Predictive ops | ❌ Reactive only | ✅ Trend analysis, early warnings |
| 24/7 coverage | No human works round the clock | Machines never sleep |
| Knowledge retention | Scattered in personal notes | Structured, queryable history |

The best part: **every byte of your system data stays on your VPS** — no third-party monitoring service sees your logs or metrics.

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                    Your VPS                          │
│  ┌─────────────┐    ┌──────────────┐                │
│  │ Data        │───►│ AI Analysis   │               │
│  │ Collection  │    │ Engine       │               │
│  │ • journalctl│    │ • Ollama     │               │
│  │ • df/htop   │    │ • Local LLM  │               │
│  │ • dmesg     │    │ • Semantic   │               │
│  │ • nginx logs│    │   Analysis   │               │
│  └─────────────┘    └──────┬───────┘               │
│                             │                        │
│                             ▼                        │
│  ┌─────────────┐    ┌──────────────┐                │
│  │ Alert Layer │◄───│ Auto-Remed.  │               │
│  │ • Telegram  │    │ Engine       │               │
│  │ • Email     │    │ • shell cmds │               │
│  │ • Webhook   │    │ • systemctl  │               │
│  └─────────────┘    └──────────────┘                │
└─────────────────────────────────────────────────────┘
```

## Step 1: Install Ollama + a Local LLM

Ollama is the easiest way to run LLMs locally. We'll use Qwen2.5 7B — it's small enough for a 2GB VPS (4-bit quantized) and handles both system logs and natural language analysis well.

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull a capable-but-light model
ollama pull qwen2.5:7b

# For constrained VPS (1GB RAM), use:
# ollama pull phi:mini
```

> **Why Qwen2.5 7B?** Excellent log comprehension, 128K context window (enough for full system logs), and runs on 2GB RAM with 4-bit quantization. For English-only systems, Mistral 7B or Llama 3.1 8B are great alternatives.

Verify it's running:

```bash
ollama ps
```

## Step 2: System Data Collection Script

Create a script that gathers system metrics and recent logs:

```bash
mkdir -p /opt/ai-ops
vim /opt/ai-ops/collect_data.sh
```

```bash
#!/bin/bash
# /opt/ai-ops/collect_data.sh - System data collector

TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
OUTPUT_DIR="/tmp/ai-ops-data"
mkdir -p "$OUTPUT_DIR"

echo "=== System Overview [$TIMESTAMP] ===" > "$OUTPUT_DIR/summary.txt"
echo "CPU Load:" >> "$OUTPUT_DIR/summary.txt"
uptime >> "$OUTPUT_DIR/summary.txt"

echo -e "\nMemory Usage:" >> "$OUTPUT_DIR/summary.txt"
free -h >> "$OUTPUT_DIR/summary.txt"

echo -e "\nDisk Usage:" >> "$OUTPUT_DIR/summary.txt"
df -h / /var /tmp --output=source,pcent,used,avail,target 2>/dev/null >> "$OUTPUT_DIR/summary.txt"

echo -e "\nTop 5 Memory Processes:" >> "$OUTPUT_DIR/summary.txt"
ps aux --sort=-%mem | head -6 >> "$OUTPUT_DIR/summary.txt"

echo -e "\nRecent System Logs (5 min):" >> "$OUTPUT_DIR/summary.txt"
journalctl --since "5 min ago" --no-pager -n 50 >> "$OUTPUT_DIR/summary.txt" 2>&1

echo -e "\nDocker Container Status:" >> "$OUTPUT_DIR/summary.txt"
docker ps -a 2>/dev/null >> "$OUTPUT_DIR/summary.txt"

echo "Data collected: $TIMESTAMP"
```

Schedule collection every 5 minutes:

```bash
chmod +x /opt/ai-ops/collect_data.sh
(crontab -l 2>/dev/null; echo "*/5 * * * * /opt/ai-ops/collect_data.sh") | crontab -
```

## Step 3: AI Analysis Engine

This is the core — feeding system data to a local LLM and parsing its diagnosis:

```bash
vim /opt/ai-ops/analyze.py
```

```python
#!/usr/bin/env python3
"""
AI Ops Analysis Engine
Reads collected data → queries local LLM → outputs diagnosis & remediation
"""
import json
import subprocess
import time
from pathlib import Path

DATA_DIR = Path("/tmp/ai-ops-data")
OLLAMA_URL = "http://localhost:11434"
MODEL = "qwen2.5:7b"

def read_system_data():
    """Read collected system data"""
    summary_file = DATA_DIR / "summary.txt"
    if not summary_file.exists():
        return "No data available"
    return summary_file.read_text(encoding="utf-8")

def analyze_with_llm(system_data: str) -> dict:
    """Send system data to local LLM for analysis"""
    prompt = f"""You are a senior VPS operations engineer. Analyze the following system data and identify any anomalies or potential risks.

System Data:
{system_data}

Output your analysis in the following JSON format only (no markdown, no extra text):
{{
  "status": "normal|warning|critical",
  "issues": [
    {{
      "severity": "low|medium|high",
      "type": "Issue type (e.g., disk space, memory pressure, service down)",
      "detail": "Detailed description of the problem",
      "recommendation": "Recommended fix or next step"
    }}
  ],
  "summary": "One-sentence system health summary"
}}
"""
    try:
        result = subprocess.run(
            ["curl", "-s", f"{OLLAMA_URL}/api/generate",
             "-d", json.dumps({
                 "model": MODEL,
                 "prompt": prompt,
                 "stream": False,
                 "options": {"temperature": 0.1}
             })],
            capture_output=True, text=True, timeout=120
        )
        response = json.loads(result.stdout)
        text = response.get("response", "{}")
        # Strip markdown code blocks if present
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        return json.loads(text.strip())
    except Exception as e:
        return {"status": "error", "summary": f"Analysis failed: {str(e)}"}

def execute_remediation(action: str):
    """Execute safe remediation commands"""
    safe_commands = {
        "clean_docker": "docker system prune -f --volumes",
        "restart_service": "systemctl restart docker",
        "clear_journal": "journalctl --vacuum-time=3d",
        "clean_cache": "apt-get clean && rm -rf /tmp/*",
    }
    if action in safe_commands:
        subprocess.run(safe_commands[action], shell=True)
        return f"Executed: {action}"
    return f"Skipped (requires manual approval): {action}"

def main():
    system_data = read_system_data()
    result = analyze_with_llm(system_data)

    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] AI Ops Status: {result.get('status', 'unknown')}")
    print(f"Summary: {result.get('summary', 'N/A')}")

    issues = result.get("issues", [])
    for issue in issues:
        print(f"  [{issue.get('severity', 'info').upper()}] {issue.get('type', '')}")
        print(f"    Detail: {issue.get('detail', '')}")
        print(f"    Fix: {issue.get('recommendation', '')}")

    # Save analysis result
    output = DATA_DIR / f"analysis_{int(time.time())}.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
```

Schedule analysis every 10 minutes:

```bash
chmod +x /opt/ai-ops/analyze.py
(crontab -l 2>/dev/null; echo "*/10 * * * * /usr/bin/python3 /opt/ai-ops/analyze.py >> /var/log/ai-ops.log 2>&1") | crontab -
```

## Step 4: Telegram Alert Bot

When the AI detects critical issues, get notified in real-time:

```bash
vim /opt/ai-ops/notify.py
```

```python
#!/usr/bin/env python3
"""Send AI Ops alerts to Telegram"""
import json
import os
import requests
from pathlib import Path

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "YOUR_CHAT_ID")
DATA_DIR = Path("/tmp/ai-ops-data")

def send_alert(message: str):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    })

def check_and_notify():
    analysis_files = sorted(DATA_DIR.glob("analysis_*.json"))
    if not analysis_files:
        return
    latest = json.loads(analysis_files[-1].read_text())
    status = latest.get("status", "normal")
    if status not in ("warning", "critical"):
        return  # All clear

    msg = f"🚨 *AI Ops Alert*\n"
    msg += f"Status: {'⚠️ Warning' if status == 'warning' else '🔥 Critical'}\n"
    msg += f"Summary: {latest.get('summary', 'N/A')}\n\n"

    for issue in latest.get("issues", []):
        emoji = {"low": "ℹ️", "medium": "⚡", "high": "🔴"}
        msg += f"{emoji.get(issue.get('severity',''), '•')} *{issue.get('type','')}*\n"
        msg += f"  {issue.get('detail','')}\n"
        msg += f"  💡 {issue.get('recommendation','')}\n\n"

    send_alert(msg)
    print(f"Alert sent: {status}")

if __name__ == "__main__":
    check_and_notify()
```

Setting up the Telegram bot:

```
1. Message @BotFather on Telegram, send /newbot to create a bot
2. Get your BOT_TOKEN (format: 123456:ABC-DEF1234...)
3. Find your bot on Telegram, send /start
4. Visit https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates
   to find your CHAT_ID
5. Export credentials: export TELEGRAM_BOT_TOKEN="your_token"
                        export TELEGRAM_CHAT_ID="your_chat_id"
```

## Step 5: One-Click Deploy Script

Package everything into a single deploy script:

```bash
vim /opt/ai-ops/deploy.sh
```

```bash
#!/bin/bash
# AI Ops Assistant - One-click Deploy
set -e

echo "🚀 Deploying AI Ops Assistant..."

# 1. Install Ollama
if ! command -v ollama &>/dev/null; then
    echo "📦 Installing Ollama..."
    curl -fsSL https://ollama.com/install.sh | sh
fi

# 2. Pull model
echo "🤖 Pulling AI model..."
ollama pull qwen2.5:7b

# 3. Create directories
mkdir -p /opt/ai-ops /tmp/ai-ops-data

# 4. Set up collection cron (every 5 min)
echo "⏰ Setting up data collection..."
(crontab -l 2>/dev/null | grep -v "collect_data.sh"; echo "*/5 * * * * /opt/ai-ops/collect_data.sh") | crontab -

# 5. Set up analysis cron (every 10 min)
echo "🔍 Setting up AI analysis..."
(crontab -l 2>/dev/null | grep -v "analyze.py"; echo "*/10 * * * * /usr/bin/python3 /opt/ai-ops/analyze.py >> /var/log/ai-ops.log 2>&1") | crontab -

# 6. Install Python deps
pip3 install requests -q

echo "✅ Deployment complete!"
echo "   - System data collected every 5 min"
echo "   - AI analysis runs every 10 min"
echo "   - Telegram alerts on critical issues"
echo ""
echo "📋 View logs: tail -f /var/log/ai-ops.log"
```

## Real-World Scenarios

### Scenario 1: Disk Space Critical

Collected data shows:

```
Disk Usage:
/dev/vda1    82%   4.2G   920M   /
/dev/vdb1    94%   28G    1.7G   /var
```

AI analysis output:

```json
{
  "status": "warning",
  "issues": [
    {
      "severity": "high",
      "type": "Disk Space Exhaustion",
      "detail": "/var partition at 94%. Expected to fill in 2-3 days. Primary culprits: Docker container logs and journald system logs.",
      "recommendation": "Run 'journalctl --vacuum-time=3d' to clear old logs, then 'docker system prune -f' to remove unused images and containers."
    }
  ],
  "summary": "/var partition disk space alert — immediate cleanup required."
}
```

The Telegram alert arrives. You fix it, or let the auto-remediation handle it:

```bash
# Manual fix
journalctl --vacuum-time=3d
docker system prune -f

# Prevent recurrence
echo "MaxUse=100M" >> /etc/systemd/journald.conf
systemctl restart systemd-journald
```

### Scenario 2: Container Crash (OOM Kill)

AI detects a service is down:

```json
{
  "status": "critical",
  "issues": [
    {
      "severity": "high",
      "type": "Container Service Down",
      "detail": "Nginx container (nginx-proxy) crashed 3 minutes ago with exit code 137 (OOM Kill). Current memory usage at 85%. The OOM Killer likely terminated Nginx.",
      "recommendation": "Restart container and adjust memory limits: 'docker restart nginx-proxy'. Consider setting 'mem_limit: 256m' in docker-compose.yml and reducing swappiness."
    }
  ],
  "summary": "Nginx killed by OOM — memory limits need adjustment."
}
```

## Optional: Web History Dashboard

Track AI analysis history with a lightweight Flask dashboard:

```bash
pip3 install flask
vim /opt/ai-ops/dashboard.py
```

```python
#!/usr/bin/env python3
"""AI Ops History Dashboard - Flask Web UI"""
import json
from flask import Flask, jsonify, render_template_string
from pathlib import Path

app = Flask(__name__)
DATA_DIR = Path("/tmp/ai-ops-data")

HTML = """
<!DOCTYPE html>
<html>
<head><title>AI Ops Dashboard</title>
<style>
  body { font-family: sans-serif; max-width: 800px; margin: auto; padding: 20px; background: #0f172a; color: #e2e8f0; }
  .card { background: #1e293b; border-radius: 8px; padding: 16px; margin: 12px 0; }
  .critical { border-left: 4px solid #ef4444; }
  .warning { border-left: 4px solid #f59e0b; }
  .normal { border-left: 4px solid #22c55e; }
  .high { color: #ef4444; } .medium { color: #f59e0b; } .low { color: #94a3b8; }
  pre { background: #0f172a; padding: 8px; border-radius: 4px; overflow-x: auto; }
</style></head>
<body>
  <h1>🤖 AI Ops Dashboard</h1>
  <p>Last updated: {{ time }}</p>
  {% for r in records %}
  <div class="card {{ r.status }}">
    <strong>Status: {{ r.status }}</strong>
    <p>{{ r.summary }}</p>
    {% for issue in r.issues %}
      <div>
        <span class="{{ issue.severity }}">[{{ issue.severity.upper() }}]</span>
        <strong>{{ issue.type }}</strong>
        <p>{{ issue.detail }}</p>
        <pre>{{ issue.recommendation }}</pre>
      </div>
    {% endfor %}
  </div>
  {% endfor %}
</body></html>
"""

@app.route("/")
def dashboard():
    records = []
    for f in sorted(DATA_DIR.glob("analysis_*.json"), reverse=True)[:20]:
        records.append(json.loads(f.read_text()))
    return render_template_string(
        HTML, records=records,
        time=records[0]["_time"] if records else "N/A"
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=9090)
```

```bash
python3 /opt/ai-ops/dashboard.py &
# Visit: http://your-vps-ip:9090
```

> **Security note**: This dashboard has no authentication. Use Nginx reverse proxy with basic auth, or bind to 127.0.0.1 and access via SSH tunnel.

## Cost Breakdown

| Component | Cost |
|-----------|------|
| VPS (2GB RAM) | $3-5/mo (Hetzner CX22 or similar) |
| Ollama + Local LLM | Free (open-source) |
| Telegram notifications | Free |
| **Total** | **$3-5/mo** |

Compare this to Datadog ($15/mo+), New Relic ($49/mo+), or Grafana Cloud (free tier limited). For a self-hosted setup, the marginal cost is essentially zero.

## Security Best Practices

1. **Start in read-only/alert mode** — let the AI analyze for a week before enabling auto-remediation
2. **Choose the right model** — don't use models under 3B parameters for critical diagnosis; they hallucinate more
3. **Keep data local** — system logs may contain sensitive IPs, domains, or usernames
4. **Ollama API safety** — defaults to 127.0.0.1:11434; never expose it publicly
5. **Use env vars for secrets** — never hardcode Telegram tokens or API keys in scripts

## Summary

Using a local LLM for VPS operations automation delivers real value in three areas:

1. **24/7 Intelligent Monitoring** — AI never sleeps; it continuously analyzes system health
2. **Semantic Log Understanding** — move beyond keyword grepping to genuine context-aware analysis
3. **Auto-Remediation** — common issues (disk full, service down, OOM) get handled automatically

The real beauty: **your 2GB VPS can simultaneously run the services being monitored AND the AI ops assistant monitoring them.** It won't replace a seasoned DevOps engineer, but it will ensure that when a 3 AM alert hits, you already know exactly what went wrong and how to fix it.

Next steps: integrate more data sources (database slow queries, CDN origin health, SSL certificate expiry), or use a multi-agent architecture where multiple LLMs cross-validate each other's diagnoses.

---

*Start building your own AI ops engineer today — your VPS deserves a tireless 24/7 digital watchdog.*
