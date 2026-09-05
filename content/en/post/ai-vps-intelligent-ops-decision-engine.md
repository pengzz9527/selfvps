---
title: "AI + VPS: Building an Intelligent Ops Decision Engine with Local LLM"
description: "Traditional ops relies on manual alert analysis and troubleshooting. This article shows you how to deploy an AI-powered decision engine on your VPS using local LLM — automatically correlating multi-source data, generating prioritized action plans, and tracking fix effectiveness for truly autonomous operations"
date: 2026-09-05T20:00:00+08:00
lastmod: 2026-09-05T20:00:00+08:00
slug: "ai-vps-intelligent-ops-decision-engine"
image: /images/posts/ai-vps-intelligent-ops-decision-engine/featured.png
tags: ["AI", "VPS", "ops decision", "LLM", "automation", "Ollama", "Llama", "Qwen", "Prometheus", "Grafana"]
categories: ["AI Operations"]
aliases: [/en/post/ai-vps-intelligent-ops-decision-engine/]
---

## Introduction

You manage several VPS instances running websites, APIs, and databases. Every day you face:

- Prometheus alerts firing in bursts — which one is the root cause?
- Disk space alerts, but you can't tell if it's log bloat or accumulated backups;
- CPU spike alerts, but the logs show no corresponding anomalies;
- Monthly bills arrive, and you realize a VPS has been running at under 5% utilization for months.

**The core pain point: scattered data, time-consuming analysis, and decisions that depend on individual experience.**

Traditional ops workflow is: alert → manual investigation → manual troubleshooting → plan formulation → execution → verification. This process relies heavily on the ops engineer's experience and time, and doesn't scale.

**An intelligent ops decision engine** solves this problem: a locally deployed Large Language Model (LLM) acts as the "brain", automatically collecting multi-source operational data, correlating analyses, generating prioritized action lists, and tracking execution effectiveness. Your VPS stops just responding to alerts passively — instead, it proactively tells you "what to do now, why, and how".

This article walks you through building this system from scratch, including:

1. **Data collection layer**: Aggregating from Prometheus, logs, backups, costs
2. **AI analysis layer**: Local Ollama + Qwen/Llama for correlated reasoning
3. **Decision output layer**: Prioritized action lists + one-click execution scripts
4. **Feedback loop**: Recording execution results to continuously improve recommendations

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│              Intelligent Ops Decision Engine                 │
├─────────────┬─────────────┬─────────────┬─────────────────┤
│  Data       │  AI         │  Decision    │   Feedback      │
│  Collection │  Analysis   │  Output      │   Learning      │
│  Collector  │  Engine     │  Output      │   Feedback      │
├─────────────┼─────────────┼─────────────┼─────────────────┤
│ Prometheus  │             │  Priority    │  Execution      │
│  Alerts +   │  → LLM API  │  Action List │  Effectiveness  │
│  Metrics    │  (Qwen/     │  Recommendations │ Human Review  │
│             │   Llama)    │  Root Cause  │  Stats          │
│             │             │  Analysis    │  Model tuning   │
│ System Logs │             │  Trend Forecast │               │
│             │             │              │                 │
│ Backup      │             │              │                 │
│ Status      │             │              │                 │
│ Cost Data   │             │              │                 │
└─────────────┴─────────────┴─────────────┴─────────────────┘
         ↓                ↓                ↓                ↓
     docker-compose    Ollama server   Telegram/Email    SQLite History
```

## Step 1: Deploy Local LLM with Ollama

The core of the decision engine is a local LLM, ensuring data never leaves your VPS. We use Ollama to run Qwen2.5-7B or Llama-3.2-3B.

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull Qwen2.5-7B (recommended, strong Chinese understanding)
ollama pull qwen2.5:7b

# Or the lighter Llama-3.2-3B (for resource-constrained VPS)
ollama pull llama3.2:3b

# Verify it's running
ollama list
ollama run qwen2.5:7b "Hello, please briefly introduce yourself"
```

For a 2C2G VPS, `llama3.2:3b` is recommended; for 4C8G or above, use `qwen2.5:7b`.

## Step 2: Build the Data Collector

### 2.1 Collect Prometheus Metrics and Alerts

```python
# collector/prometheus_collector.py
import requests
from datetime import datetime, timedelta
import json

class PrometheusCollector:
    def __init__(self, url="http://localhost:9090"):
        self.url = url.rstrip("/")
    
    def get_firing_alerts(self):
        """Get currently firing alerts"""
        resp = requests.get(f"{self.url}/api/v1/alerts", timeout=10)
        data = resp.json()
        alerts = []
        if data["status"] == "success":
            for group in data["data"].get("activeAlerts", []):
                alerts.append({
                    "name": group["labels"].get("alertname", "Unknown"),
                    "severity": group["labels"].get("severity", "info"),
                    "summary": group["annotations"].get("summary", ""),
                    "starts_at": group["startsAt"],
                    "value": group.get("value", ""),
                })
        return alerts
    
    def get_metric(self, query, minutes=60):
        """Query metrics for the last N minutes"""
        end = datetime.now().isoformat()
        start = (datetime.now() - timedelta(minutes=minutes)).isoformat()
        resp = requests.get(
            f"{self.url}/api/v1/query",
            params={"query": query, "start": start, "end": end},
            timeout=10
        )
        data = resp.json()
        results = []
        if data["status"] == "success":
            for result in data["data"].get("result", []):
                values = result.get("values", [])
                if values:
                    latest = float(values[-1][1])
                    results.append({
                        "metric": result["metric"],
                        "latest_value": latest,
                        "trend": self._calc_trend(values),
                    })
        return results
    
    def _calc_trend(self, values):
        """Calculate metric trend"""
        if len(values) < 2:
            return "stable"
        first = float(values[0][1])
        last = float(values[-1][1])
        if last > first * 1.2:
            return "rising"
        elif last < first * 0.8:
            return "falling"
        return "stable"
    
    def collect_all(self):
        """Collect all Prometheus data"""
        return {
            "timestamp": datetime.now().isoformat(),
            "source": "prometheus",
            "alerts": self.get_firing_alerts(),
            "cpu": self.get_metric("100 - (avg by(instance) (rate(node_cpu_seconds_total{mode=\"idle\"}[5m])) * 100)"),
            "memory": self.get_metric("node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes * 100"),
            "disk": self.get_metric("100 - (node_filesystem_avail_bytes / node_filesystem_size_bytes * 100)"),
            "network": self.get_metric("rate(node_network_receive_bytes_total[5m])"),
        }
```

### 2.2 Collect System Logs

```python
# collector/log_collector.py
import subprocess
from datetime import datetime, timedelta
import re

class LogCollector:
    def __init__(self):
        self.errors = []
    
    def collect_recent_errors(self, hours=6):
        """Collect error logs from the last N hours"""
        since = (datetime.now() - timedelta(hours=hours)).strftime("%b %d %H:%M")
        
        # Collect journalctl errors
        try:
            result = subprocess.run(
                ["journalctl", "--since", since, "-p", "err", "--no-pager", "-n", "50"],
                capture_output=True, text=True, timeout=30
            )
            errors = result.stdout.strip().split("\n")
        except Exception:
            errors = []
        
        # Collect syslog errors
        try:
            result = subprocess.run(
                ["grep", "-E", "(error|fail|warning)", "/var/log/syslog"],
                capture_output=True, text=True, timeout=10
            )
            syslog_errors = result.stdout.strip().split("\n")[-20:]
        except Exception:
            syslog_errors = []
        
        return {
            "timestamp": datetime.now().isoformat(),
            "source": "logs",
            "journalctl_errors": errors[:20],
            "syslog_errors": [e for e in syslog_errors if e],
            "total_errors": len(errors) + len(syslog_errors),
        }
    
    def collect_dmesg(self):
        """Collect kernel messages with anomalies"""
        try:
            result = subprocess.run(
                ["dmesg", "-T", "-l", "err,warn,crit,alert,emerg"],
                capture_output=True, text=True, timeout=10
            )
            return {
                "timestamp": datetime.now().isoformat(),
                "source": "dmesg",
                "kernel_issues": result.stdout.strip().split("\n")[-10:],
            }
        except Exception:
            return {"timestamp": datetime.now().isoformat(), "source": "dmesg", "kernel_issues": []}
```

### 2.3 Collect Backup and Cost Data

```python
# collector/backup_collector.py
import subprocess
import json
from datetime import datetime

class BackupCollector:
    def check_backup_status(self):
        """Check critical backup status"""
        checks = []
        
        # Check recent backup files
        try:
            result = subprocess.run(
                ["find", "/backup", "-type", "f", "-mtime", "-7", "-printf", "%T@ %p\n"],
                capture_output=True, text=True
            )
            recent_backups = [line.split(" ", 1)[1] for line in result.stdout.strip().split("\n") if line]
            checks.append({
                "type": "backup_files",
                "status": "ok" if len(recent_backups) > 0 else "warning",
                "count": len(recent_backups),
                "latest": recent_backups[-1] if recent_backups else None,
            })
        except Exception as e:
            checks.append({"type": "backup_files", "status": "error", "detail": str(e)})
        
        # Check Docker image count
        try:
            result = subprocess.run(
                ["docker", "images", "--format", "{{.Repository}}:{{.Tag}}"],
                capture_output=True, text=True
            )
            images = [i for i in result.stdout.strip().split("\n") if i]
            checks.append({
                "type": "docker_images",
                "status": "ok",
                "count": len(images),
            })
        except Exception:
            checks.append({"type": "docker_images", "status": "unknown"})
        
        return {"timestamp": datetime.now().isoformat(), "checks": checks}


class CostCollector:
    def estimate_resource_usage(self):
        """Estimate current resource usage cost"""
        try:
            # Average CPU usage
            result = subprocess.run(
                ["awk", "{print $2/$1*100}", "/proc/stat"],
                capture_output=True, text=True
            )
            cpu_usage = float(result.stdout.strip().split()[0]) if result.stdout.strip() else 0
            
            # Memory usage
            with open("/proc/meminfo") as f:
                meminfo = f.read()
            mem_total = int(re.search(r"MemTotal:\s+(\d+)", meminfo).group(1))
            mem_avail = int(re.search(r"MemAvailable:\s+(\d+)", meminfo).group(1))
            mem_usage = (1 - mem_avail / mem_total) * 100
            
            return {
                "timestamp": datetime.now().isoformat(),
                "source": "cost",
                "cpu_usage_percent": round(cpu_usage, 1),
                "memory_usage_percent": round(mem_usage, 1),
                "recommendation": self._get_cost_recommendation(cpu_usage, mem_usage),
            }
        except Exception as e:
            return {"timestamp": datetime.now().isoformat(), "error": str(e)}
    
    def _get_cost_recommendation(self, cpu, mem):
        if cpu < 10 and mem < 20:
            return "underutilized: consider downsizing"
        elif cpu > 80 or mem > 85:
            return "overutilized: consider upgrading"
        return "normal utilization"
```

## Step 3: Build the AI Decision Engine

This is the core of the entire system. We concatenate collected data into context, send it to the local LLM, which analyzes root causes and generates action recommendations.

```python
# engine/decision_engine.py
import json
import requests
from datetime import datetime
from pathlib import Path

class DecisionEngine:
    def __init__(self, ollama_url="http://localhost:11434", model="qwen2.5:7b"):
        self.ollama_url = ollama_url
        self.model = model
        self.history_db = Path("/var/lib/ops-decision/history.db")
    
    def build_context(self, collected_data):
        """Build AI-readable context from multi-source data"""
        context_parts = []
        
        # Alert information
        alerts = collected_data.get("alerts", [])
        if alerts:
            context_parts.append("【Current Alerts】")
            for a in alerts:
                context_parts.append(f"- [{a['severity']}] {a['name']}: {a['summary']}")
        else:
            context_parts.append("【Current Alerts】None")
        
        # Resource usage
        metrics = collected_data.get("metrics", {})
        context_parts.append("【Resource Usage】")
        for metric in metrics.get("cpu", []):
            context_parts.append(f"- CPU {metric['metric'].get('instance', 'local')}: {metric['latest_value']:.1f}% (trend: {metric['trend']})")
        for metric in metrics.get("memory", []):
            context_parts.append(f"- Memory {metric['metric'].get('instance', 'local')}: {100 - metric['latest_value']:.1f}% (trend: {metric['trend']})")
        for metric in metrics.get("disk", []):
            context_parts.append(f"- Disk {metric['metric'].get('mountpoint', 'unknown')}: {metric['latest_value']:.1f}% (trend: {metric['trend']})")
        
        # Log errors
        logs = collected_data.get("logs", {})
        if logs.get("total_errors", 0) > 0:
            context_parts.append(f"【Log Anomalies】{logs['total_errors']} errors in the last 6 hours")
            for err in logs.get("journalctl_errors", [])[:5]:
                context_parts.append(f"  - {err[:120]}")
        
        # Backup status
        backup = collected_data.get("backup", {})
        for check in backup.get("checks", []):
            context_parts.append(f"【{check['type']}】Status: {check['status']}")
        
        # Cost assessment
        cost = collected_data.get("cost", {})
        if "recommendation" in cost:
            context_parts.append(f"【Cost Assessment】{cost['recommendation']} (CPU: {cost.get('cpu_usage_percent', 'N/A')}%, RAM: {cost.get('memory_usage_percent', 'N/A')}%)")
        
        return "\n".join(context_parts)
    
    def generate_decision(self, context):
        """Call LLM to generate decisions"""
        prompt = f"""You are a professional ops engineer assistant. Based on the following VPS operational status data, generate ops decision recommendations.

## VPS Operational Status
{context}

## Output Requirements
Please output in the following JSON format, do not add any other content:

{{
  "priority": "critical|high|medium|low|info",
  "root_cause_summary": "One-sentence summary of the most urgent issue and possible cause",
  "action_items": [
    {{
      "priority": 1,
      "action": "Specific steps (commands or operations)",
      "reason": "Why this operation is needed",
      "estimated_impact": "Expected effect",
      "risk": "low|medium|high"
    }}
  ],
  "trend_forecast": "Predict problems that may occur in the next 24 hours based on current trends",
  "auto_execute_commands": ["List of commands that can be safely auto-executed"],
  "requires_human_review": ["Operations that require human confirmation"]
}}"""
        
        try:
            resp = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.3, "num_predict": 2048}
                },
                timeout=120
            )
            resp.raise_for_status()
            result = resp.json()
            return self._parse_llm_output(result.get("response", ""))
        except requests.exceptions.Timeout:
            return {"error": "LLM request timeout, check Ollama service"}
        except Exception as e:
            return {"error": f"LLM call failed: {str(e)}"}
    
    def _parse_llm_output(self, text):
        """Parse LLM returned JSON"""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            import re
            match = re.search(r'\{[\s\S]*\}', text)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
            return {"error": "Cannot parse LLM output", "raw": text[:500]}
    
    def run_decision_cycle(self, collected_data):
        """Execute a complete decision cycle"""
        context = self.build_context(collected_data)
        decision = self.generate_decision(context)
        
        # Record decision history
        self._save_history(collected_data, context, decision)
        
        return {
            "timestamp": datetime.now().isoformat(),
            "context_summary": context[:500],
            "decision": decision,
        }
    
    def _save_history(self, input_data, context, decision):
        """Save decision history records (simplified version, SQLite recommended for production)"""
        record = {
            "timestamp": datetime.now().isoformat(),
            "input_summary": {
                "alert_count": len(input_data.get("alerts", [])),
                "error_count": input_data.get("logs", {}).get("total_errors", 0),
            },
            "decision": decision,
        }
        # In production, write to SQLite or TimescaleDB
        # Here simplified to printing
        print(f"[Decision Record] {record['timestamp']}")
        print(f"  Alerts: {record['input_summary']['alert_count']}, Errors: {record['input_summary']['error_count']}")
        priority = decision.get("priority", "unknown")
        print(f"  Priority: {priority}")
        for item in decision.get("action_items", []):
            print(f"  Action #{item.get('priority', '?')}: {item.get('action', '')[:80]}")
```

## Step 4: Orchestration and Scheduling

Use a Python script to integrate all components, scheduled via cron or systemd timer.

```python
# main.py
#!/usr/bin/env python3
"""Intelligent Ops Decision Engine - Main Entry"""

import json
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from collector.prometheus_collector import PrometheusCollector
from collector.log_collector import LogCollector
from collector.backup_collector import BackupCollector, CostCollector
from engine.decision_engine import DecisionEngine


def collect_all_data():
    """Collect all operational data"""
    data = {"timestamp": datetime.now().isoformat()}
    
    # Prometheus
    try:
        prom = PrometheusCollector()
        data["alerts"] = prom.get_firing_alerts()
        data["metrics"] = {
            "cpu": prom.get_metric("100 - (avg by(instance) (rate(node_cpu_seconds_total{mode=\"idle\"}[5m])) * 100)"),
            "memory": prom.get_metric("node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes * 100"),
            "disk": prom.get_metric("100 - (node_filesystem_avail_bytes / node_filesystem_size_bytes * 100)"),
        }
    except Exception as e:
        data["prometheus_error"] = str(e)
        data["alerts"] = []
        data["metrics"] = {}
    
    # Logs
    try:
        log_col = LogCollector()
        data["logs"] = log_col.collect_recent_errors()
        data["dmesg"] = log_col.collect_dmesg()
    except Exception as e:
        data["logs"] = {"total_errors": 0, "journalctl_errors": [], "syslog_errors": []}
    
    # Backup & Cost
    try:
        backup_col = BackupCollector()
        cost_col = CostCollector()
        data["backup"] = backup_col.check_backup_status()
        data["cost"] = cost_col.estimate_resource_usage()
    except Exception as e:
        data["backup"] = {"checks": []}
        data["cost"] = {}
    
    return data


def format_output(decision):
    """Format decision output"""
    output = []
    output.append(f"🔍 Ops Decision Report — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    output.append("=" * 50)
    
    priority = decision.get("decision", {}).get("priority", "unknown")
    emoji_map = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢", "info": "ℹ️"}
    output.append(f"Priority: {emoji_map.get(priority, '⚪')} {priority.upper()}")
    
    root_cause = decision.get("decision", {}).get("root_cause_summary", "")
    if root_cause:
        output.append(f"\n📋 Root Cause Summary: {root_cause}")
    
    action_items = decision.get("decision", {}).get("action_items", [])
    if action_items:
        output.append(f"\n📝 Recommended Actions ({len(action_items)}):")
        for i, item in enumerate(action_items, 1):
            output.append(f"  {i}. [{item.get('risk', '?')}] {item.get('action', '')}")
            output.append(f"     Reason: {item.get('reason', '')}")
            output.append(f"     Expected: {item.get('estimated_impact', '')}")
    
    auto_cmds = decision.get("decision", {}).get("auto_execute_commands", [])
    if auto_cmds:
        output.append(f"\n🤖 Auto-Executable:")
        for cmd in auto_cmds[:5]:
            output.append(f"  $ {cmd}")
    
    forecast = decision.get("decision", {}).get("trend_forecast", "")
    if forecast:
        output.append(f"\n📈 Trend Forecast: {forecast}")
    
    return "\n".join(output)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "run"
    
    if mode == "collect":
        data = collect_all_data()
        print(json.dumps(data, indent=2, ensure_ascii=False))
    
    elif mode == "run":
        print("Collecting operational data...")
        data = collect_all_data()
        
        print("Running AI analysis...")
        engine = DecisionEngine()
        result = engine.run_decision_cycle(data)
        
        print(format_output(result))
        
        output_path = Path(f"/tmp/ops_decision_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        with open(output_path, "w") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"\nFull result saved to: {output_path}")
    
    elif mode == "history":
        history_dir = Path("/var/lib/ops-decision")
        if history_dir.exists():
            files = sorted(history_dir.glob("*.json"), reverse=True)[:5]
            for f in files:
                with open(f) as fp:
                    rec = json.load(fp)
                print(f"{f.name}: priority={rec.get('decision', {}).get('priority', '?')}")
        else:
            print("No history records yet")


if __name__ == "__main__":
    main()
```

## Step 5: Docker Compose Full Deployment

Containerize all components for one-click deployment.

```yaml
# docker-compose.yml
version: "3.8"

services:
  # Ollama LLM service
  ollama:
    image: ollama/ollama:latest
    container_name: ollama
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama
    restart: unless-stopped

  # Intelligent ops decision engine
  ops-decision:
    build: .
    container_name: ops-decision
    volumes:
      - ./config:/app/config
      - ./output:/app/output
      - /var/lib/docker:/var/lib/docker:ro
      - /proc:/host/proc:ro
      - /sys:/host/sys:ro
    depends_on:
      - ollama
    restart: unless-stopped
    environment:
      - OLLAMA_URL=http://ollama:11434
      - MODEL=qwen2.5:7b
      - COLLECTION_INTERVAL=300  # Collect every 5 minutes
      - NOTIFICATION_CHANNEL=telegram

  # Prometheus (skip if already running)
  prometheus:
    image: prom/prometheus:latest
    container_name: prometheus
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    restart: unless-stopped

volumes:
  ollama_data:
  prometheus_data:
```

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/output /app/config

ENTRYPOINT ["python3", "main.py"]
```

```txt
# requirements.txt
requests>=2.31.0
python-dotenv>=1.0.0
```

## Step 6: Configure Scheduled Tasks

### Using systemd timer (recommended)

```ini
# /etc/systemd/system/ops-decision.service
[Unit]
Description=VPS Intelligent Ops Decision Engine
After=network.target

[Service]
Type=oneshot
WorkingDirectory=/opt/ops-decision
ExecStart=/usr/bin/python3 main.py run
User=root
```

```ini
# /etc/systemd/system/ops-decision.timer
[Unit]
Description=Run VPS ops decision every 5 minutes

[Timer]
OnBootSec=2min
OnUnitActiveSec=5min
AccuracySec=1min
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable ops-decision.timer
sudo systemctl start ops-decision.timer
```

### Or using cron

```cron
# Run decision analysis every 5 minutes
*/5 * * * * cd /opt/ops-decision && /usr/bin/python3 main.py run >> /var/log/ops-decision.log 2>&1

# Generate daily report at 2 AM
0 2 * * * cd /opt/ops-decision && /usr/bin/python3 main.py run --daily-report >> /var/log/ops-decision-daily.log 2>&1
```

## Step 7: Integrate Notification Channels

### Telegram Integration

```python
# notification/telegram_notifier.py
import requests
import json

class TelegramNotifier:
    def __init__(self, bot_token, chat_id):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
    
    def send_decision(self, decision_output):
        """Send decision report to Telegram"""
        message = decision_output[:4000]
        
        resp = requests.post(
            f"{self.base_url}/sendMessage",
            json={
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            }
        )
        return resp.json()
    
    def send_inline_buttons(self, decision):
        """Send decision report with quick-action buttons"""
        action_items = decision.get("decision", {}).get("action_items", [])
        
        buttons = []
        for item in action_items[:3]:
            buttons.append([{"text": f"✅ {item.get('priority', '?')}: {item.get('action', '')[:20]}...", 
                            "callback_data": f"execute:{item.get('action', '')}"}])
        
        return {
            "chat_id": self.chat_id,
            "text": f"🔍 Ops Decision Suggestion\n\n{decision.get('decision', {}).get('root_cause_summary', '')}",
            "reply_markup": json.dumps({"inline_keyboard": buttons}),
        }
```

### Feedback Loop and Effectiveness Tracking

```python
# feedback/tracker.py
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

class FeedbackTracker:
    def __init__(self, db_path="/var/lib/ops-decision/history.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                priority TEXT,
                root_cause TEXT,
                action_items TEXT,
                executed_commands TEXT,
                human_feedback TEXT,
                feedback_effectiveness TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS feedback_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                decision_id INTEGER,
                action_index INTEGER,
                feedback_type TEXT,
                feedback_text TEXT,
                created_at TEXT
            )
        """)
        conn.commit()
        conn.close()
    
    def record_execution(self, decision_id, action_index, executed, effectiveness):
        """Record execution effect and human feedback"""
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO feedback_logs (decision_id, action_index, feedback_type, feedback_text, created_at) VALUES (?, ?, ?, ?, ?)",
            (decision_id, action_index, executed, effectiveness, datetime.now().isoformat())
        )
        conn.commit()
        conn.close()
    
    def get_effectiveness_stats(self, days=7):
        """Stats on decision effectiveness for the last N days"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("""
            SELECT feedback_type, COUNT(*) 
            FROM feedback_logs 
            WHERE created_at > datetime('now', '-{} days')
            GROUP BY feedback_type
        """.format(days))
        stats = dict(cursor.fetchall())
        conn.close()
        return stats
```

## Real-World Example

```bash
$ cd /opt/ops-decision && python3 main.py run
Collecting operational data...
Running AI analysis...
🔍 Ops Decision Report — 2026-09-05 20:30
==================================================
Priority: 🟠 HIGH

📋 Root Cause Summary: Disk /var/log at 92% and rising, likely due to unrotated syslog entries

📝 Recommended Actions (3):
  1. [low] journalctl --vacuum-time=3d
     Reason: Clean journal logs older than 3 days to free disk space
     Expected: Free up approximately 2-5GB
  2. [low] systemctl restart rsyslog
     Reason: Ensure log rotation configuration takes effect
     Expected: Logs split by configured size limits
  3. [medium] Check for processes writing excessive logs
     Reason: Rapid disk usage increase may indicate application anomaly
     Expected: Identify the root cause application

🤖 Auto-Executable:
  $ journalctl --vacuum-time=3d
  $ systemctl restart rsyslog

📈 Trend Forecast: If unaddressed, /var/log will reach 95% within 12 hours, triggering critical alerts
```

## Advanced: Multi-VPS Centralized Decision

When managing multiple VPS instances, you can deploy a centralized decision engine:

```python
# multi_vps_manager.py
import json
from concurrent.futures import ThreadPoolExecutor

class MultiVpsDecisionManager:
    def __init__(self, vps_list):
        self.vps_list = vps_list
    
    def collect_all(self):
        """Concurrently collect data from all VPS instances"""
        results = {}
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {
                executor.submit(self._collect_single, vps): vps["name"]
                for vps in self.vps_list
            }
            for future in futures:
                name = futures[future]
                try:
                    results[name] = future.result()
                except Exception as e:
                    results[name] = {"error": str(e)}
        return results
    
    def generate_correlated_decisions(self, all_data):
        """Cross-VPS correlated analysis, generate global decisions"""
        # Detect cross-VPS correlated issues here
        # e.g., multiple VPS experiencing DNS resolution failure simultaneously → points to shared DNS server issue
        context = self._build_global_context(all_data)
        return self.engine.generate_decision(context)
```

## Summary

Through this article, you've learned:

1. **Deploy local Ollama + Qwen/Llama**, ensuring data privacy
2. **Build multi-source data collectors** aggregating Prometheus, logs, backups, and cost data
3. **Design an AI analysis engine** that transforms operational data into structured decision outputs
4. **Implement a feedback loop** recording execution effects for continuous optimization
5. **Integrate notification channels** pushing decision suggestions via Telegram, etc.

The core value of this system: **liberating ops engineers from repetitive "check alerts → search logs → formulate plans" labor**, letting AI handle data analysis while humans make final decisions.

As usage time grows, the system learns your operational habits and feedback, increasingly accurately generating recommendations that match your actual needs. From "firefighter" to "autopilot" — this is the future of AI + VPS operations.
