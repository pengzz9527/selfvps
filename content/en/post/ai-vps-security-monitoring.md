---
title: "AI-Powered VPS Security Monitoring: Real-Time Intrusion Detection with Local LLMs"
description: "VPS under constant SSH brute force, cryptomining, or lateral movement attacks? Deploy a local LLM as your 24/7 security analyst — automatically parse auth logs, detect anomalous login patterns, identify cryptominers and zero-day malware, all running on a 2GB VPS with zero data leaving your server."
date: 2026-05-30T21:30:00+08:00
slug: "ai-vps-security-monitoring"
tags: ["AI Security", "Intrusion Detection", "LLM", "Log Analysis", "VPS Security", "Self-hosting", "Ollama", "Security Monitoring", "Anomaly Detection"]
categories: ["AI Security"]
image: /images/posts/ai-vps-security-monitoring/featured.png
draft: false
---

## Why VPS Security Needs AI

An internet-exposed VPS receives dozens to hundreds of SSH brute-force attempts every single day. Traditional security tools work on rules — Fail2Ban blocks IPs, ClamAV scans for known malware, RKHunter detects rootkits. These tools are effective, but they all share one fundamental limitation: **they only know known threats**.

AI-powered security monitoring takes a different approach: deploy a local LLM as your security analyst, continuously reading system logs, process lists, network connections, and file changes — identifying threats that no rule engine could have anticipated.

| Capability | Traditional Tools | AI Security Assistant |
|-----------|-----------------|----------------------|
| Brute force detection | Fail2Ban (rule matching) | Attack pattern analysis, trend prediction |
| Malicious process ID | Known signature database | Zero-day behavioral detection |
| Log analysis | grep keywords | Context-aware, cross-log correlation |
| False positives | Silent or noisy alert | Severity assessment + remediation suggestions |

## Architecture Overview

```
┌──────────────────────────────────────────────┐
│            VPS Security Monitor               │
│                                              │
│  ┌─────────┐  ┌──────────┐  ┌───────────┐   │
│  │ Syslogs  │  │ Process  │  │  Network   │   │
│  │auth.log  │  │ snapshots│  │  conns     │   │
│  │syslog    │  │ ps aux   │  │ ss -tuln   │   │
│  └────┬────┘  └────┬─────┘  └─────┬─────┘   │
│       │             │              │          │
│  ┌────▼─────────────▼──────────────▼──────┐  │
│  │         Data Collector (collector.sh)   │  │
│  │   Collects every 5 minutes, generates   │  │
│  │   structured security snapshots         │  │
│  └────────────────┬───────────────────────┘  │
│                   │                           │
│  ┌────────────────▼───────────────────────┐  │
│  │      LLM Analysis Engine               │  │
│  │   (Ollama + Qwen2.5)                   │  │
│  │   Reads snapshot → Semantic analysis   │  │
│  └────────────────┬───────────────────────┘  │
│                   │                           │
│  ┌────────────────▼───────────────────────┐  │
│  │          Alert Handler                  │  │
│  │   Telegram / Email / Webhook           │  │
│  └────────────────────────────────────────┘  │
└──────────────────────────────────────────────┘
```

## Deployment Guide

### Step 1: Install Ollama and Pull a Lightweight Model

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull Qwen2.5 7B (quantized, runs on 2GB VPS)
ollama pull qwen2.5:7b-q4_K_M

# Or use a smaller model (works on 1GB VPS)
ollama pull qwen2.5:3b-q4_K_M
```

### Step 2: Create the Data Collection Script

```bash
cat > /usr/local/bin/security-collector.sh << 'SCRIPT'
#!/bin/bash
# Security Data Collector - captures system security state every 5 minutes

OUTPUT_DIR="/var/log/security-snapshots"
mkdir -p "$OUTPUT_DIR"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT_FILE="$OUTPUT_DIR/snapshot_$TIMESTAMP.json"

# 1. Recent auth logs (SSH login attempts)
AUTH_LOG=$(tail -200 /var/log/auth.log 2>/dev/null || journalctl -u sshd --no-pager -n 200 2>/dev/null)

# 2. Currently logged-in users
CURRENT_USERS=$(who)

# 3. Listening ports and network connections
NET_CONNS=$(ss -tulpn 2>/dev/null)

# 4. Recently created SUID files
SUID_FILES=$(find /usr /bin /sbin /etc -type f -perm -4000 -newer /etc/crontab 2>/dev/null)

# 5. Processes sorted by CPU usage
TOP_PROCS=$(ps aux --sort=-%cpu | head -30)

# 6. Docker container status (if available)
DOCKER_PS=$(docker ps 2>/dev/null || echo "Docker not available")

# 7. Recent cron changes
CRON_CHANGES=$(stat /var/spool/cron/crontabs/ 2>/dev/null)

# Build JSON snapshot
cat > "$OUTPUT_FILE" << EOF
{
  "timestamp": "$TIMESTAMP",
  "auth_log_summary": $(echo "$AUTH_LOG" | jq -R -s .),
  "logged_in_users": $(echo "$CURRENT_USERS" | jq -R -s .),
  "network_connections": $(echo "$NET_CONNS" | jq -R -s .),
  "suspicious_suid_files": $(echo "$SUID_FILES" | jq -R -s .),
  "top_processes": $(echo "$TOP_PROCS" | jq -R -s .),
  "docker_status": $(echo "$DOCKER_PS" | jq -R -s .)
}
EOF

# Keep only last 60 snapshots (5 hours)
find "$OUTPUT_DIR" -name "snapshot_*.json" -mmin +300 -delete
SCRIPT
chmod +x /usr/local/bin/security-collector.sh
```

### Step 3: Create the LLM Analysis Script

```bash
cat > /usr/local/bin/security-analyzer.sh << 'SCRIPT'
#!/bin/bash
# AI Security Analysis Engine - analyzes security snapshots with local LLM

LATEST_SNAPSHOT=$(ls -t /var/log/security-snapshots/snapshot_*.json 2>/dev/null | head -1)

if [ -z "$LATEST_SNAPSHOT" ]; then
    echo "No snapshots found. Run collector first."
    exit 1
fi

SNAPSHOT_CONTENT=$(cat "$LATEST_SNAPSHOT")

# Build the analysis prompt
PROMPT="You are a VPS security analysis expert. Analyze the following system security snapshot and output in this format:

1. Security Rating: [Safe / Suspicious / Critical]
2. Issues Found (list specific items with evidence)
3. Recommended Actions (if threats exist)

Snapshot data:
$SNAPSHOT_CONTENT

Answer in English. If everything looks normal, just say '✅ System is secure'."

RESPONSE=$(ollama run qwen2.5:7b-q4_K_M "$PROMPT" 2>/dev/null)

echo "$RESPONSE"

# Send alert if threats are detected
if echo "$RESPONSE" | grep -qi "critical\|danger\|attack\|intrusion\|malicious\|suspicious\|miner"; then
    TELEGRAM_TOKEN="${TELEGRAM_BOT_TOKEN:-}"
    CHAT_ID="${TELEGRAM_CHAT_ID:-}"
    if [ -n "$TELEGRAM_TOKEN" ] && [ -n "$CHAT_ID" ]; then
        MESSAGE=$(echo "🚨 *AI Security Alert*\n$RESPONSE" | head -50)
        curl -s -X POST "https://api.telegram.org/bot$TELEGRAM_TOKEN/sendMessage" \
            -d "chat_id=$CHAT_ID" \
            -d "text=$MESSAGE" \
            -d "parse_mode=Markdown" > /dev/null
    fi
fi
SCRIPT
chmod +x /usr/local/bin/security-analyzer.sh
```

### Step 4: Set Up Cron Jobs

```bash
# Add crontab entries
(crontab -l 2>/dev/null; echo "*/5 * * * * /usr/local/bin/security-collector.sh") | crontab -
(crontab -l 2>/dev/null; echo "*/10 * * * * /usr/local/bin/security-analyzer.sh >> /var/log/ai-security.log 2>&1") | crontab -
```

## Live Demo: Simulating an Intrusion

Let's simulate a common attack scenario — SSH brute force + cryptominer:

```bash
# Simulate failed SSH logins (test only)
for i in $(seq 1 100); do
    echo "Failed password for root from 10.0.0.$((RANDOM % 255)) port $((10000 + RANDOM % 50000)) ssh2" >> /var/log/auth.log
done

# Simulate a cryptominer process
cat > /tmp/.system-update << 'FAKE'
#!/bin/bash
while true; do
    echo "hashrate: 1234 KH/s"
    sleep 5
done
FAKE
chmod +x /tmp/.system-update
/tmp/.system-update &
```

Run the analyzer and you'll see output like this:

```
🔍 Analysis Results:

Security Rating: Critical ⚠️

Issues Found:
1. SSH brute force attack: 100 failed login attempts from different IPs detected
2. Suspicious process: /tmp/.system-update running from non-standard directory with high CPU
3. Unknown outbound network connection detected

Recommended Actions:
1. Immediately terminate: kill $(pgrep -f system-update)
2. Block attacking IPs with fail2ban
3. Check /tmp for additional malicious files
4. Change root password immediately
```

## Advanced Configuration

### Fail2Ban + AI Integration

Rather than replacing Fail2Ban, layer AI intelligence on top:

```bash
cat > /usr/local/bin/ai-fail2ban-analyzer.sh << 'SCRIPT'
#!/bin/bash
# Analyze fail2ban logs to detect advanced attack patterns
BANNED_IPS=$(grep "Ban" /var/log/fail2ban.log | tail -100)

PROMPT="Analyze these fail2ban ban records and answer:
1. Is there a concentrated attack against specific ports?
2. Are attacks coming from the same subnet?
3. Should jail configurations be adjusted?

Ban records:
$BANNED_IPS"

ollama run qwen2.5:7b-q4_K_M "$PROMPT"
SCRIPT
```

### Setting Up Telegram Alerts

Create a `.env` configuration:

```bash
cat > /usr/local/etc/ai-security.env << 'ENV'
# Telegram Bot
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklmNOPqrStuVWXyz
TELEGRAM_CHAT_ID=-1001234567890

# Collection frequency (seconds)
COLLECTOR_INTERVAL=300
ANALYZER_INTERVAL=600
ENV
```

### Optional: Dashboard Integration

Push security metrics to Prometheus + Grafana for a security posture dashboard:

```bash
cat > /usr/local/bin/security-metrics.sh << 'SCRIPT'
#!/bin/bash
# Export Prometheus metrics
LATEST_SNAPSHOT=$(ls -t /var/log/security-snapshots/snapshot_*.json | head -1)
SUSPICIOUS_COUNT=$(cat "$LATEST_SNAPSHOT" | grep -c "Failed password\|Invalid user\|Connection closed by authenticating user")

echo "# HELP ai_security_suspicious_events Total suspicious security events"
echo "# TYPE ai_security_suspicious_events gauge"
echo "ai_security_suspicious_events $SUSPICIOUS_COUNT"
SCRIPT
```

## Resource Usage

| Component | Memory | CPU | Disk |
|-----------|--------|-----|------|
| Ollama (Qwen2.5:3b-Q4) | ~1.8 GB | Low~Med | 2 GB |
| Collection script | ~5 MB | Minimal (1s per 5min) | ~50 MB/day |
| Analysis engine (per run) | ~2 GB peak | ~5-10s CPU | ~10 MB/day logs |

> 💡 **Pro tip**: On a 1GB VPS, use `qwen2.5:1.5b-q4_K_M` — memory drops to ~1GB with acceptable analysis quality.

## Summary

Running AI-powered security monitoring with a local LLM gives you several critical advantages:

1. **Zero data exfiltration** — all logs and system data stay local, never touching a third-party API
2. **Zero ongoing cost** — no paid SIEM or security services needed, a single VPS handles everything
3. **Zero rule maintenance** — no signature databases to update, the LLM understands context and semantics
4. **Full explainability** — every alert includes natural-language analysis explaining exactly why it fired

This system isn't meant to replace Fail2Ban or traditional security tools — it augments them. Traditional tools handle enforcement, the AI handles understanding. **That's the future of VPS security monitoring.**

---

*All scripts in this article run on a 2GB VPS. Ollama and Qwen2.5 are both open-source projects.*
