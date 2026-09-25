---
title: "AI + VPS: Intelligent Ops Dashboard — Multi-Source Data Fusion Visualization"
description: "Prometheus tracks metrics, Loki handles logs, Alertmanager fires alerts — but your data lives in silos. This article shows how to build an AI-powered ops dashboard that fuses multi-source data into a single, actionable VPS health overview."
date: 2026-09-25T21:00:00+08:00
lastmod: 2026-09-25T21:00:00+08:00
slug: "ai-vps-intelligent-ops-dashboard"
image: /images/posts/ai-vps-intelligent-ops-dashboard/featured.png
tags: ["AI", "VPS", "Ops Dashboard", "Visualization", "Prometheus", "Grafana", "Loki", "LLM", "AIOps", "Data Fusion"]
categories: ["AI + VPS"]
aliases: [/en/post/ai-vps-intelligent-ops-dashboard/]
draft: false
---

## Introduction

You've built a complete VPS monitoring stack: Prometheus for metrics, Grafana for dashboards, Loki for logs, Alertmanager for notifications. Everything looks organized —

But when you need to quickly answer "how is my VPS doing right now?", you end up opening three or four different tools, switching between pages, manually piecing together the story. And when an actual incident occurs, you need to cross-reference CPU curves, grep through relevant logs, and check historical alerts just to understand what happened.

**The problem isn't a lack of monitoring data — it's the lack of correlation between data sources.** Metrics tell you *what* happened, logs tell you *why*, and alerts tell you *how severe* — but no single tool connects these dots and gives you a unified view with actionable conclusions.

This article shows how to use an AI engine to bridge these silos and build an **Intelligent Ops Dashboard** — not just displaying data, but understanding it, automatically extracting key insights, and letting you grasp your entire VPS's health status in 30 seconds.

---

## Why Do You Need an Intelligent Ops Dashboard?

### Three Pain Points of Traditional Monitoring

| Pain Point | Symptom | Consequence |
|------------|---------|-------------|
| **Data Silos** | Metrics in Prometheus, logs in Loki, configs in files, alerts in Telegram | Troubleshooting requires switching multiple tools; information is fragmented |
| **Information Overload** | Dozens of Grafana panels, hundreds of alert rules | The signal you need is drowned in noise |
| **Lack of Context** | You know CPU spiked, but not which process or deployment caused it | Troubleshooting depends on personal experience; slow root cause identification |

### Core Value of an Intelligent Dashboard

An intelligent ops dashboard is not another visualization tool — it's a **data fusion + AI understanding + intelligent presentation** system:

- **One-glance visibility**: See all critical information on a single page, no tool-switching needed
- **AI extraction**: Automatically distills "what's the single most important thing today" from massive data
- **Contextual correlation**: Automatically links metric anomalies with related logs and historical alerts
- **Predictive warnings**: Based on trend analysis, tells you "what might happen next" before it does

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      AI Intelligent Ops Dashboard                       │
│                                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                  │
│  │  Data Layer   │  │  AI Engine   │  │ Presentation │                  │
│  │              │  │              │  │              │                  │
│  │ • Prometheus  │  │ • Anomaly    │  │ • Health     │                  │
│  │ • Loki       │  │   Detection   │  │   Scoring    │                  │
│  │ • System Cmds │  │ • Trend      │  │ • Key Events │                  │
│  │ • API Health  │  │   Prediction │  │ • AI Summary │                  │
│  │              │  │ • Root Cause │  │ • One-click  │                  │
│  │              │  │   Correlation│  │   Diagnostics│                  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘                  │
│         │                 │                 │                           │
│         └─────────────────┼─────────────────┘                           │
│                           ▼                                             │
│  ┌──────────────────────────────────────────────────────────────┐       │
│  │              Local Ollama (Qwen2.5 / Llama)                   │       │
│  │        Semantic understanding, anomaly interpretation,         │       │
│  │                 report generation                              │       │
│  └──────────────────────────────────────────────────────────────┘       │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────┐       │
│  │                  Push Channels (Optional)                     │       │
│  │         Telegram / Feishu / Email / Webhook                   │       │
│  └──────────────────────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────────────────────┘
```

### Component Breakdown

| Component | Responsibility | Technology |
|-----------|---------------|------------|
| **Data Collector** | Pulls raw info from each source | Prometheus API, Loki API, shell commands |
| **AI Analysis Engine** | Understands data, detects anomalies, correlates context | Ollama + Qwen2.5 |
| **Presentation Layer** | Transforms analysis into readable views | Python + HTML/Markdown |
| **Push Channel** | Delivers dashboard content to endpoints | Telegram Bot, Feishu Bot |

---

## Step 1: Build the Unified Data Aggregator

### Data Collection Script

We write a Python aggregation script that pulls data from multiple sources and unifies the format:

```python
#!/usr/bin/env python3
"""
VPS Intelligent Ops Dashboard — Data Aggregator
Fusion Prometheus metrics, Loki logs, system state, service health
"""

import json
import subprocess
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Any

class VPSDataAggregator:
    def __init__(self, prometheus_url="http://localhost:9090", 
                 loki_url="http://localhost:3100",
                 ollama_url="http://localhost:11434"):
        self.prom_url = prometheus_url
        self.loki_url = loki_url
        self.ollama_url = ollama_url
        self.snapshot_time = datetime.now()
    
    def collect_system_metrics(self) -> Dict[str, Any]:
        """Collect system-level metrics"""
        metrics = {}
        
        # CPU load
        try:
            with open('/proc/loadavg') as f:
                load = f.read().split()
            metrics['load_1m'] = float(load[0])
            metrics['load_5m'] = float(load[1])
            metrics['load_15m'] = float(load[2])
        except:
            pass
        
        # Memory usage
        try:
            with open('/proc/meminfo') as f:
                mem_info = f.read()
            mem_lines = {}
            for line in mem_info.splitlines():
                parts = line.split(':')
                if len(parts) == 2:
                    mem_lines[parts[0].strip()] = int(parts[1].strip().split()[0])
            total = mem_lines.get('MemTotal', 1)
            available = mem_lines.get('MemAvailable', 0)
            metrics['memory_total_gb'] = total / 1024 / 1024
            metrics['memory_used_percent'] = round((total - available) / total * 100, 1)
        except:
            pass
        
        # Disk usage
        try:
            result = subprocess.run(['df', '-h', '/'], capture_output=True, text=True)
            lines = result.stdout.strip().split('\n')
            if len(lines) > 1:
                parts = lines[1].split()
                metrics['disk_used_percent'] = parts[4].replace('%', '')
        except:
            pass
        
        # Key process status
        for service in ['nginx', 'docker', 'sshd', 'postgresql', 'redis']:
            try:
                result = subprocess.run(['systemctl', 'is-active', service], 
                                       capture_output=True, text=True)
                metrics[f'{service}_status'] = result.stdout.strip()
            except:
                pass
        
        return metrics
    
    def collect_prometheus_alerts(self) -> List[Dict]:
        """Collect currently firing alerts"""
        try:
            resp = requests.get(f"{self.prom_url}/api/v1/alerts", timeout=5)
            data = resp.json()
            alerts = []
            for item in data.get('data', {}).get('alerts', []):
                if item['state'] == 'firing':
                    alerts.append({
                        'name': item['labels'].get('alertname', 'Unknown'),
                        'severity': item['labels'].get('severity', 'unknown'),
                        'summary': item['annotations'].get('summary', ''),
                        'starts_at': item['startsAt'],
                    })
            return alerts
        except Exception as e:
            return [{'error': str(e)}]
    
    def collect_recent_logs(self, hours: int = 2) -> List[str]:
        """Collect key recent logs from Loki"""
        try:
            end = datetime.now().timestamp() * 1e9
            start = (datetime.now() - timedelta(hours=hours)).timestamp() * 1e9
            query = '{"job"=~"prometheus|node_exporter|application"}'
            url = f"{self.loki_url}/loki/api/v1/query_range"
            params = {
                'query': query,
                'start': str(int(start)),
                'end': str(int(end)),
                'limit': 50,
            }
            resp = requests.get(url, params=params, timeout=10)
            lines = []
            for entry in resp.json().get('data', {}).get('result', []):
                for vals in entry.get('values', []):
                    ts, text = vals
                    lines.append(text[:200])
            return lines[-20:]
        except Exception:
            return []
    
    def collect_service_health(self) -> Dict[str, Dict]:
        """Collect per-service health checks"""
        health = {}
        services = {
            'web': 'http://localhost:80/health',
            'api': 'http://localhost:8080/health',
            'db': 'postgres://localhost:5432',
        }
        for name, endpoint in services.items():
            try:
                if endpoint.startswith('http'):
                    resp = requests.get(endpoint, timeout=5)
                    health[name] = {'status': 'up' if resp.status_code < 400 else 'down',
                                    'latency_ms': round(resp.elapsed.total_seconds() * 1000, 1)}
                else:
                    result = subprocess.run(['pg_isready', '-h', 'localhost'], 
                                           capture_output=True, timeout=5)
                    health[name] = {'status': 'up' if result.returncode == 0 else 'down'}
            except:
                health[name] = {'status': 'unknown'}
        return health
    
    def gather_all(self) -> Dict[str, Any]:
        """Aggregate all data sources"""
        return {
            'timestamp': self.snapshot_time.isoformat(),
            'system': self.collect_system_metrics(),
            'alerts': self.collect_prometheus_alerts(),
            'recent_logs': self.collect_recent_logs(),
            'services': self.collect_service_health(),
        }


if __name__ == '__main__':
    agg = VPSDataAggregator()
    data = agg.gather_all()
    print(json.dumps(data, indent=2, ensure_ascii=False))
```

---

## Step 2: AI Analysis Engine

After data collection, send the structured data to the local LLM for analysis:

```python
#!/usr/bin/env python3
"""
VPS Intelligent Ops Dashboard — AI Analysis Engine
Uses local Ollama + Qwen2.5 to analyze aggregated data
"""

import json
import requests

ANALYSIS_PROMPT = """You are an experienced DevOps engineer analyzing a VPS's runtime status.
Based on the following data, provide a concise and professional operations analysis.

【Analysis Requirements】
1. Health Score (0-100): Comprehensive assessment of current status
2. Key Findings: List the top 2-3 issues or anomalies
3. Trend Prediction: Based on current data, predict what might happen next
4. Action Recommendations: Provide specific, actionable fix or optimization suggestions
5. One-Liner: Summarize in one sentence what needs attention today

【Output Format】Strictly use JSON:
{{
  "health_score": 85,
  "key_findings": ["Finding 1", "Finding 2"],
  "trend": "Trend description",
  "actions": ["Suggestion 1", "Suggestion 2"],
  "one_liner": "One-sentence summary"
}}

【Input Data】
{data}
"""

def analyze_with_ollama(system_data: dict, model: str = "qwen2.5:7b") -> dict:
    """Call local Ollama for intelligent analysis"""
    prompt = ANALYSIS_PROMPT.format(data=json.dumps(system_data, indent=2, ensure_ascii=False))
    
    try:
        resp = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=60
        )
        result = resp.json()
        output = result.get('response', '')
        start = output.find('{')
        end = output.rfind('}') + 1
        if start >= 0 and end > start:
            return json.loads(output[start:end])
        return {"error": "Failed to parse LLM response", "raw": output}
    except Exception as e:
        return {"error": str(e)}


def generate_dashboard_summary(analysis: dict, raw_data: dict) -> str:
    """Generate a readable dashboard summary report"""
    score = analysis.get('health_score', '?')
    one_liner = analysis.get('one_liner', '')
    findings = analysis.get('key_findings', [])
    actions = analysis.get('actions', [])
    trend = analysis.get('trend', '')
    
    if score >= 80:
        status_emoji = "🟢"
    elif score >= 60:
        status_emoji = "🟡"
    else:
        status_emoji = "🔴"
    
    report = f"""# {status_emoji} VPS Intelligent Ops Dashboard

**Generated**: {raw_data.get('timestamp', 'N/A')}  
**Health Score**: {score}/100  
**One-Liner**: {one_liner}

---

## 📊 Key Findings

"""
    for i, finding in enumerate(findings, 1):
        report += f"{i}. {finding}\n"
    
    report += "\n## 📈 Trend Prediction\n\n"
    report += f">{trend}\n"
    
    report += "\n## 🔧 Action Recommendations\n\n"
    for i, action in enumerate(actions, 1):
        report += f"{i}. {action}\n"
    
    report += "\n---\n\n## 📋 System Status Quick View\n\n"
    system = raw_data.get('system', {})
    report += f"- **CPU Load (1m)**: {system.get('load_1m', 'N/A')}\n"
    report += f"- **Memory Usage**: {system.get('memory_used_percent', 'N/A')}%\n"
    report += f"- **Disk Usage**: {system.get('disk_used_percent', 'N/A')}%\n"
    
    alerts = raw_data.get('alerts', [])
    if alerts:
        report += f"\n## 🚨 Active Alerts ({len(alerts)})\n\n"
        for alert in alerts[:5]:
            severity = alert.get('severity', 'unknown')
            icon = "🔴" if severity == 'critical' else "🟠" if severity == 'warning' else "⚪"
            report += f"- {icon} **{alert.get('name', 'Unknown')}**: {alert.get('summary', '')}\n"
    else:
        report += "\n✅ No active alerts\n"
    
    return report
```

---

## Step 3: Dashboard Rendering & Push

### Dashboard HTML Template

Render AI analysis results as a beautiful web dashboard:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>VPS Intelligent Ops Dashboard</title>
  <style>
    :root { --bg: #0f0f1a; --card: #1a1a2e; --accent: #4fc3f7; }
    body { background: var(--bg); color: #e0e0e0; font-family: 'Segoe UI', sans-serif; margin: 0; padding: 20px; }
    .dashboard { max-width: 1400px; margin: 0 auto; }
    .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
    .health-score { font-size: 72px; font-weight: 700; color: var(--accent); }
    .health-label { font-size: 14px; color: #888; text-transform: uppercase; letter-spacing: 2px; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px; }
    .card { background: var(--card); border-radius: 12px; padding: 20px; border: 1px solid #2a2a4a; }
    .card-title { font-size: 12px; color: #888; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 12px; }
    .metric { display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #2a2a4a; }
    .metric:last-child { border-bottom: none; }
    .one-liner { font-size: 20px; font-weight: 300; color: #fff; padding: 16px; background: linear-gradient(135deg, #1a1a2e, #16213e); border-radius: 8px; border-left: 4px solid var(--accent); }
  </style>
</head>
<body>
  <div class="dashboard">
    <div class="header">
      <div>
        <h1 style="margin:0;font-size:24px;">🖥️ VPS Intelligent Ops Dashboard</h1>
        <span style="color:#888;font-size:13px;" id="timestamp">Loading...</span>
      </div>
      <div style="text-align:right;">
        <div class="health-label">Health Score</div>
        <div class="health-score" id="healthScore">--</div>
      </div>
    </div>
    
    <div class="one-liner" id="oneLiner">Analyzing VPS status...</div>
    
    <div class="grid" style="margin-top:20px;">
      <div class="card">
        <div class="card-title">📊 System Resources</div>
        <div class="metric"><span>CPU Load (1m)</span><span id="cpuLoad">--</span></div>
        <div class="metric"><span>Memory Usage</span><span id="memUsage">--</span></div>
        <div class="metric"><span>Disk Usage</span><span id="diskUsage">--</span></div>
      </div>
      <div class="card">
        <div class="card-title">🔌 Service Status</div>
        <div id="serviceStatus">--</div>
      </div>
      <div class="card">
        <div class="card-title">🚨 Active Alerts</div>
        <div id="activeAlerts">No alerts</div>
      </div>
      <div class="card">
        <div class="card-title">💡 AI Recommendations</div>
        <div id="aiActions">--</div>
      </div>
    </div>
  </div>
  
  <script>
    async function refreshDashboard() {
      try {
        const resp = await fetch('/api/dashboard');
        const data = await resp.json();
        document.getElementById('healthScore').textContent = data.health_score ?? '--';
        document.getElementById('oneLiner').textContent = data.one_liner ?? '';
        document.getElementById('cpuLoad').textContent = (data.system?.load_1m ?? '--') + ' load';
        document.getElementById('memUsage').textContent = (data.system?.memory_used_percent ?? '--') + '%';
        document.getElementById('diskUsage').textContent = (data.system?.disk_used_percent ?? '--') + '%';
      } catch(e) { console.error('Refresh failed', e); }
    }
    refreshDashboard();
    setInterval(refreshDashboard, 60000);
  </script>
</body>
</html>
```

### Scheduled Execution & Push

Integrate the dashboard generation into cron for periodic push to Telegram:

```bash
# Generate and push dashboard at 8:00 and 20:00 daily
0 8,20 * * * cd /opt/vps-dashboard && python3 collect_and_analyze.py | python3 send_telegram.py
```

Telegram Push Script:

```python
#!/usr/bin/env python3
"""Push dashboard summary to Telegram"""
import os, json, requests

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_to_telegram(message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    })

if __name__ == "__main__":
    import sys
    report = sys.stdin.read()
    send_to_telegram(f"🖥️ *VPS Intelligent Ops Dashboard*\n\n{report[:3000]}")
```

---

## Real-World Output Example

After running `python3 collect_and_analyze.py`, the AI dashboard output looks like:

```
# 🟢 VPS Intelligent Ops Dashboard

**Generated**: 2026-09-25T21:00:00
**Health Score**: 82/100
**One-Liner**: Disk space is growing fast; recommend cleaning old logs or scaling this week.

---

## 📊 Key Findings

1. Root partition at 78% usage, growing ~1.2% daily over the past 7 days — will hit 90% in ~20 days
2. PostgreSQL connections near limit (142/150); connection refusals possible during high concurrency
3. Memory cache ratio is normal, no OOM risk

## 📈 Trend Prediction

Disk I/O wait time has been trending upward over the past 24 hours. Combined with log growth rates, intervention is likely needed mid-next-week.

## 🔧 Action Recommendations

1. Run `journalctl --vacuum-time=7d` to clean system logs older than 7 days
2. Adjust PostgreSQL `max_connections` to 200, or introduce a connection pool (PgBouncer)
3. Configure log rotation for Loki; cap single file size at 500MB
```

---

## Advanced: Dashboard API Service

To enable real-time browser access, set up a simple Flask API service:

```python
from flask import Flask, render_template, jsonify
import subprocess, json

app = Flask(__name__)

@app.route('/')
def dashboard():
    return render_template('dashboard.html')

@app.route('/api/dashboard')
def api_dashboard():
    result = subprocess.run(
        ['python3', '/opt/vps-dashboard/collect_and_analyze.py'],
        capture_output=True, text=True, timeout=120
    )
    return jsonify(json.loads(result.stdout))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8888)
```

Visit `http://your-vps:8888` for a live dashboard that auto-refreshes every 60 seconds.

---

## Summary

The core value of an intelligent ops dashboard is **turning scattered data into a coherent story**:

| Traditional Approach | Intelligent Dashboard |
|---------------------|----------------------|
| Check Prometheus / Loki / alerts one by one | All information aggregated on one page |
| Manually judge "which metric is anomalous" | AI automatically identifies key anomalies and scores them |
| See numbers but don't know what they mean | AI generates "one-liner summary" and specific recommendations |
| Troubleshooting relies on personal experience | AI correlates metrics + logs + historical cases |

With this approach, you only need to:
1. Deploy Prometheus + Loki + Ollama (local LLM)
2. Run the data collection script
3. Receive AI-analyzed dashboard reports twice daily

…to achieve the shift from **reactive firefighting** to **proactive awareness** — AI tells you "what to watch today" before you even realize there's a problem.
