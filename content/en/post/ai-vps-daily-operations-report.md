---
title: "AI-Generated Daily VPS Operations Reports: Build Intelligent Monitoring with Local LLMs"
description: "Stop manually SSH'ing into your server to check logs. Let a local LLM read system metrics, analyze log trends, generate daily ops reports, and even suggest or execute fixes automatically. Complete guide with scripts."
date: 2026-06-02T21:30:00+08:00
slug: "ai-vps-daily-operations-report"
tags: ["AI Ops", "LLM", "Monitoring", "Log Analysis", "Automation", "VPS Management", "Ollama", "Shell Scripting"]
categories: ["AI Operations"]
image: /images/posts/ai-vps-daily-operations-report/featured.png
draft: false
---

You bought a VPS, deployed your services, launched your site — and now what?

If you're like most solo developers, VPS maintenance is a "fix it when it breaks" game. Disk fills up before you notice. Services crash silently. Intrusion traces hide in logs you never read.

This guide solves that problem: **let a local LLM generate a daily operations report**, acting as your personal SRE engineer — checking server health, analyzing anomalies, and delivering actionable recommendations.

## Why AI Operations Reports?

Traditional monitoring tools (Prometheus + Grafana, Netdata, Uptime Kuma) tell you *what* broke, but they don't tell you *why* or *what to do about it*.

| Capability | Traditional Monitoring | AI Ops Report |
|-----------|----------------------|---------------|
| Disk usage alert | ✅ Threshold notification | ✅ Trend analysis + fill-up prediction |
| CPU anomaly | ✅ Load graph | ✅ Process correlation + root cause |
| Log analysis | ❌ Keyword matching only | ✅ Semantic understanding + unknown pattern detection |
| Auto-fix | ❌ Manual intervention | ✅ Fix commands generated, optional auto-execution |
| Trend reports | ⚠️ Manual dashboard config | ✅ Daily/weekly summaries, auto-generated |
| Cost | Multi-component maintenance | One script + local LLM |

## System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Your VPS Server                       │
│                                                         │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │  Data Collector │  LLM Analysis  │  Report Generator │
│  │  collect.sh  │→│  Ollama API  │→│  report.sh    │  │
│  │              │  │  (local model) │               │  │
│  │  • Metrics   │  │              │  │  • Formatted   │  │
│  │  • Logs      │  │  • Anomaly   │  │    reports     │  │
│  │  • Processes │  │  • Trends    │  │  • Telegram    │  │
│  │  • Disk/Net  │  │  • Suggestions│  │  • Email/Web   │  │
│  └─────────────┘  └──────────────┘  └───────────────┘  │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### Component Breakdown

1. **Data Collector**: Shell script gathering system state, log summaries, process info
2. **LLM Analysis Engine**: Local Ollama with lightweight model (Qwen2.5 7B or Llama 3.1 8B)
3. **Report Generator**: Formats LLM analysis into beautiful reports pushed to your notification channels

## Step 1: Deploy Local LLM (Ollama)

If you already have Ollama running, skip this step. If not, it takes two minutes:

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull a lightweight model (recommend Qwen2.5 7B — runs on 2GB RAM)
ollama pull qwen2.5:7b

# Verify
ollama list
```

> **Model selection guide**: For 2GB RAM VPS, use `qwen2.5:7b` or `llama3.1:8b` (quantized). For 1GB RAM VPS, use `qwen2.5:3b` or `phi3:mini`.

## Step 2: Data Collection Script

Create a system data collector to gather raw data for the ops report:

```bash
#!/bin/bash
# /usr/local/bin/collect-ops-data.sh

REPORT_DIR="/var/ops-reports/$(date +%Y%m%d)"
mkdir -p "$REPORT_DIR"

# 1. System metrics
cat > "$REPORT_DIR/system.txt" << 'EOF'
=== System Information ===
EOF
echo "Hostname: $(hostname)" >> "$REPORT_DIR/system.txt"
echo "Uptime: $(uptime -p)" >> "$REPORT_DIR/system.txt"
echo "Load Average: $(uptime | awk -F'load average:' '{print $2}')" >> "$REPORT_DIR/system.txt"
echo "CPU Usage: $(top -bn1 | grep 'Cpu(s)' | awk '{print $2 + $4}')%" >> "$REPORT_DIR/system.txt"
echo "Memory: $(free -h | awk '/^Mem:/{print $3 " / " $2}')" >> "$REPORT_DIR/system.txt"
echo "Swap: $(free -h | awk '/^Swap:/{print $3 " / " $2}')" >> "$REPORT_DIR/system.txt"
echo "Disk Usage: $(df -h / | awk 'NR==2{print $3 " / " $2 " (" $5 ")"}')" >> "$REPORT_DIR/system.txt"
echo "Disk Inodes: $(df -i / | awk 'NR==2{print $5}')" >> "$REPORT_DIR/system.txt"

# 2. Process info
ps aux --sort=-%cpu | head -15 > "$REPORT_DIR/top-processes.txt"

# 3. Docker status
if command -v docker &>/dev/null; then
  docker ps -a --format "table {{.Names}}\t{{.Status}}\t{{.Image}}\t{{.Ports}}" > "$REPORT_DIR/docker-status.txt"
  docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemPerc}}\t{{.NetIO}}" 2>/dev/null > "$REPORT_DIR/docker-stats.txt"
fi

# 4. Network
ss -tuln > "$REPORT_DIR/network-listening.txt"
ss -t state established | head -30 > "$REPORT_DIR/network-connections.txt"

# 5. Recent errors (last 24h)
journalctl --since "24 hours ago" -p err --no-pager -n 100 > "$REPORT_DIR/journal-errors.txt" 2>/dev/null
journalctl --since "24 hours ago" -p crit --no-pager -n 50 > "$REPORT_DIR/journal-critical.txt" 2>/dev/null

# 6. SSH failures
if [ -f /var/log/auth.log ]; then
  grep "Failed password" /var/log/auth.log | tail -50 > "$REPORT_DIR/ssh-failures.txt"
  echo "Total SSH failures (24h): $(grep "Failed password" /var/log/auth.log | wc -l)" >> "$REPORT_DIR/ssh-failures.txt"
elif [ -f /var/log/secure ]; then
  grep "Failed password" /var/log/secure | tail -50 > "$REPORT_DIR/ssh-failures.txt"
  echo "Total SSH failures (24h): $(grep "Failed password" /var/log/secure | wc -l)" >> "$REPORT_DIR/ssh-failures.txt"
fi

# 7. Recent file changes (suspicious)
find /var/www /etc -type f -mtime -1 2>/dev/null | head -30 > "$REPORT_DIR/recent-changes.txt"

# 8. SSL certificates
if command -v certbot &>/dev/null; then
  certbot certificates 2>/dev/null > "$REPORT_DIR/certificates.txt"
fi

echo "✅ Data collected: $REPORT_DIR"
```

Make it executable and test:

```bash
chmod +x /usr/local/bin/collect-ops-data.sh
sudo /usr/local/bin/collect-ops-data.sh
```

## Step 3: LLM Analysis Engine

Next, send collected data to your local LLM for analysis:

```bash
#!/bin/bash
# /usr/local/bin/analyze-with-llm.sh

REPORT_DIR="/var/ops-reports/$(date +%Y%m%d)"
MODEL="qwen2.5:7b"

# Build the Prompt
PROMPT="You are a professional VPS operations engineer. Analyze the following server data and generate an operations report.

Please include:
1. **Health Score** (0-100, based on load, disk, memory, error logs)
2. **Anomalies Found** (list all issues worth noting, sorted by severity)
3. **Trend Analysis** (compare with historical data if available)
4. **Actionable Suggestions** (executable commands for each issue)
5. **Security Summary** (SSH brute force attempts, suspicious file changes)

Keep it concise and professional.

=== System Data ===

$(cat "$REPORT_DIR/system.txt")

=== Top Processes ===
$(cat "$REPORT_DIR/top-processes.txt")

=== Docker Status ===
$(cat "$REPORT_DIR/docker-status.txt" 2>/dev/null || echo "No Docker")

=== Error Log Summary ===
$(head -60 "$REPORT_DIR/journal-errors.txt" 2>/dev/null || echo "No errors")

=== SSH Brute Force Stats ===
$(cat "$REPORT_DIR/ssh-failures.txt" 2>/dev/null || echo "No SSH logs")

=== Recent Changes ===
$(cat "$REPORT_DIR/recent-changes.txt" 2>/dev/null || echo "None")
"

# Send to Ollama
curl -s http://localhost:11434/api/generate \
  -d "{\"model\": \"$MODEL\", \"prompt\": \"$PROMPT\", \"stream\": false}" \
  | jq -r '.response' > "$REPORT_DIR/analysis.txt"

echo "✅ AI analysis complete: $REPORT_DIR/analysis.txt"
```

Schedule it with cron for daily execution at 8 AM:

```bash
# crontab -e
0 8 * * * /usr/local/bin/collect-ops-data.sh && /usr/local/bin/analyze-with-llm.sh
```

## Step 4: Report Delivery (Telegram / Email / Web)

Once the report is generated, push it to your daily channels.

### Telegram Bot Push

```bash
#!/bin/bash
# /usr/local/bin/send-report-telegram.sh

BOT_TOKEN="YOUR_BOT_TOKEN"
CHAT_ID="YOUR_CHAT_ID"
REPORT_DIR="/var/ops-reports/$(date +%Y%m%d)"

REPORT=$(cat "$REPORT_DIR/analysis.txt")

MSG="📊 *VPS Ops Report - $(date '+%Y-%m-%d')*
\`\`\`
$REPORT
\`\`\`
#selfvps #opsreport"

curl -s -X POST "https://api.telegram.org/bot$BOT_TOKEN/sendMessage" \
  -d "chat_id=$CHAT_ID&text=$MSG&parse_mode=Markdown&disable_web_page_preview=true"
```

### HTML Web Report

Generate an HTML page for viewing in your browser:

```bash
#!/bin/bash
# /usr/local/bin/gen-report-html.sh

REPORT_DIR="/var/ops-reports/$(date +%Y%m%d)"
ANALYSIS=$(cat "$REPORT_DIR/analysis.txt" | sed 's/$/<br>/g')
SYSTEM=$(cat "$REPORT_DIR/system.txt" | sed 's/$/<br>/g')

cat > "$REPORT_DIR/report.html" << HTML
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>VPS Ops Report - $(date '+%Y-%m-%d')</title>
  <style>
    body { font-family: 'Segoe UI', sans-serif; max-width: 800px; margin: 40px auto; padding: 20px; background: #0d1117; color: #c9d1d9; }
    h1 { color: #58a6ff; border-bottom: 1px solid #30363d; padding-bottom: 10px; }
    h2 { color: #7ee787; }
    pre { background: #161b22; padding: 16px; border-radius: 8px; overflow-x: auto; }
    .meta { color: #8b949e; font-size: 0.9em; }
    .healthy { color: #3fb950; }
    .warning { color: #d29922; }
    .danger { color: #f85149; }
  </style>
</head>
<body>
  <h1>📊 VPS Daily Operations Report</h1>
  <p class="meta">Generated: $(date '+%Y-%m-%d %H:%M:%S') | Server: $(hostname)</p>
  <div>$ANALYSIS</div>
  <hr>
  <h2>Raw System Data</h2>
  <pre>$SYSTEM</pre>
</body>
</html>
HTML

echo "✅ HTML report: $REPORT_DIR/report.html"
```

## Advanced: Auto-Healing

This is the most valuable part — when the LLM detects issues, it can **auto-execute fixes** using structured JSON output:

```bash
#!/bin/bash
# /usr/local/bin/auto-heal.sh

REPORT_DIR="/var/ops-reports/$(date +%Y%m%d)"
MODEL="qwen2.5:7b"

# Build a "diagnose + fix" prompt
PROMPT="You are a VPS auto-healing engineer. Analyze the system data below and output JSON-formatted repair instructions.

If everything is healthy, output: {\"status\": \"healthy\", \"score\": 95, \"message\": \"System running normally\"}

If issues are found, output:
{
  \"status\": \"issues_found\",
  \"score\": 60,
  \"issues\": [
    {
      \"severity\": \"high|medium|low\",
      \"problem\": \"Description\",
      \"fix_command\": \"executable fix command\",
      \"auto_fix\": true
    }
  ]
}

=== System Data ===
$(cat "$REPORT_DIR/system.txt")

=== Critical Errors ===
$(head -30 "$REPORT_DIR/journal-errors.txt" 2>/dev/null || echo "None")

=== Docker Status ===
$(cat "$REPORT_DIR/docker-status.txt" 2>/dev/null || echo "None")
"

# Get LLM response
RESPONSE=$(curl -s http://localhost:11434/api/generate \
  -d "{\"model\": \"$MODEL\", \"prompt\": \"$PROMPT\", \"stream\": false, \"format\": \"json\"}" \
  | jq -r '.response')

echo "$RESPONSE" > "$REPORT_DIR/heal-plan.json"

# Auto-execute fixes
HEAL_STATUS=$(echo "$RESPONSE" | jq -r '.status')

if [ "$HEAL_STATUS" = "issues_found" ]; then
  echo "$RESPONSE" | jq -c '.issues[] | select(.auto_fix == true and .severity != "low")' | while read issue; do
    PROBLEM=$(echo "$issue" | jq -r '.problem')
    CMD=$(echo "$issue" | jq -r '.fix_command')
    SEVERITY=$(echo "$issue" | jq -r '.severity')

    echo "🛠  [$SEVERITY] $PROBLEM"
    echo "   Executing: $CMD"
    eval "$CMD" || echo "   ⚠️ Fix command failed"
  done
fi
```

> **Security note**: Auto-executing LLM-generated commands carries risk. Start with `severity: medium` and `severity: low` fixes only. For high-severity issues, generate suggestions and execute manually after review.

## Real-World Example

Here's what a real ops report looks like:

```
📊 VPS Ops Report - 2026-06-02
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🏥 Health Score: 72/100 (Good, with room for improvement)

🔴 High Risk (1 issue):
  1. Disk usage at 87%, projected to fill in 12 days
     → Fix: sudo journalctl --vacuum-size=500M && docker system prune -af

🟡 Medium Risk (2 issues):
  2. Docker container 'postgres' using 1.8GB RAM, 40% above baseline
     → Suggestion: Review PostgreSQL config, consider container memory limits
  3. SSH brute force: 247 failed attempts in 24h (38 unique IPs)
     → Fix: fail2ban auto-banned already executed

🟢 Info:
  • Certbot certificates: All valid, next renewal 2026-08-15
  • System updates: 12 security updates pending
  • Swap usage: 0%, normal

📈 Trend (vs yesterday):
  • Disk usage: 86% → 87% (+1%) ⚠️
  • Load average: 0.8 → 1.2 (normal fluctuation)
  • Error count: 34 → 28 (improving)
```

## Complete Cron Configuration

Integrate everything into a single crontab:

```bash
# Daily ops report at 8 AM
0 8 * * * /usr/local/bin/collect-ops-data.sh && /usr/local/bin/analyze-with-llm.sh && /usr/local/bin/send-report-telegram.sh

# Auto-heal check every 4 hours
0 */4 * * * /usr/local/bin/collect-ops-data.sh && /usr/local/bin/auto-heal.sh

# Weekly detailed report on Sundays
0 9 * * 0 /usr/local/bin/gen-report-html.sh

# Monthly cleanup (keep last 90 days)
0 6 1 * * find /var/ops-reports/ -maxdepth 1 -type d -mtime +90 -exec rm -rf {} \;
```

## Resource Impact

The overhead on your VPS is minimal:

| Component | CPU | RAM | Disk |
|-----------|-----|-----|------|
| Data collection | ~2 sec/run | — | ~100KB/run |
| LLM analysis (7B) | ~30 sec | ~4GB | ~4.5GB (model) |
| LLM analysis (3B) | ~10 sec | ~2GB | ~2.2GB (model) |
| Report delivery | ~1 sec | — | — |

> On a 2GB RAM VPS, use `qwen2.5:3b` or `phi3:mini`. Each analysis takes ~10 seconds and ~2GB RAM — perfectly feasible for background operation.

## Extension Ideas

1. **Multi-server aggregation**: Collect data from multiple VPSes, analyze centrally
2. **Predictive scaling**: Forecast disk/memory growth, auto-alert on capacity timelines
3. **Webhook integration**: Connect with PagerDuty, Slack, Discord, or Teams
4. **Custom knowledge base**: Feed your architecture docs to the LLM for context-aware analysis
5. **Ansible integration**: Convert LLM-generated fix commands into Ansible playbooks

## Summary

Using a local LLM to generate daily VPS operations reports essentially hires an "AI SRE" to replace manual server checks. No more daily SSH login — AI reads, analyzes, recommends, and even fixes for you.

Core benefits:
- ✅ **Data privacy**: Everything runs on your server, nothing leaves
- ✅ **Near-zero cost**: Uses existing VPS resources, no additional cloud services
- ✅ **Continuous improvement**: As LLMs evolve, analysis quality keeps getting better
- ✅ **Fully controllable**: Tweak prompts, fix strategies, and notification channels anytime

Let AI manage your servers, starting today.
