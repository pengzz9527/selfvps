---
title: "AI-Driven Adaptive Log Rotation & Retention for VPS: From Fixed Cycles to Intelligent Lifecycle Management"
description: "Your logrotate config keeps 'rotate 7' for everything — Nginx access logs, app error logs, security audit logs, CI build logs. This guide shows how to use a local LLM (Ollama + Qwen2.5) to analyze anomaly density, growth rate, and business criticality per log directory, then generate a tailored rotation/retention strategy and executable systemd timers"
date: 2026-10-07T20:00:00+08:00
lastmod: 2026-10-07T20:00:00+08:00
slug: "ai-vps-adaptive-log-rotation-retention"
image: /images/posts/ai-vps-adaptive-log-rotation-retention/featured.png
tags: ["AI", "VPS", "Log Management", "Logrotate", "LLM", "Ollama", "Qwen2.5", "Disk Optimization", "Adaptive Strategy"]
categories: ["AI + VPS"]
aliases: [/en/post/ai-vps-adaptive-log-rotation-retention/]
---

## Introduction

VPS log management has a classic dilemma: **keep logs short enough to prevent disk exhaustion, long enough to support incident investigation.**

Most people settle on a one-size-fits-all approach:

```bash
# The classic "just rotate everything daily" config
/var/log/nginx/*.log {
    daily
    rotate 7          # fixed 7 days, no context
    compress
    missingok
}
```

It works, but it's dumb:

- **Nginx access logs** (50MB/day, mostly normal) and **app error logs** (200KB/day, but every line is a potential incident clue) share the same 7-day retention;
- **CI/CD build logs** (hundreds of MB per build, 30 days is pure waste) and **security audit logs** (30 days isn't enough, compliance demands 90+) also share the same policy;
- As you add more services, manually tuning logrotate configs becomes unsustainable.

**AI adaptive log lifecycle management** flips the model: let an LLM analyze each log directory's **value density** (anomaly ratio), **growth rate**, and **business criticality**, then compute the optimal rotation period, compression strategy, and retention days — not 7 days, not 30 days, but *exactly the right number*.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    VPS Log Directories (/var/log/)       │
│  nginx/  app-error/  build/  security-audit/  ...      │
└──────────────┬──────────────────────────────────────────┘
               │ sample (last N hours)
               ▼
┌─────────────────────────────────────────────────────────┐
│            Log Analyzer (Python script)                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐     │
│  │ Anomaly   │  │ Growth   │  │ Value Score      │     │
│  │ Density   │  │ Rate     │  │ (LLM semantic)   │     │
│  │(grep/stat)│  │(du/df)   │  │                  │     │
│  └──────┬───┘  └──────┬───┘  └────────┬─────────┘     │
└─────────┼──────────────┼───────────────┼────────────────┘
          │              │               │
          ▼              ▼               ▼
┌─────────────────────────────────────────────────────────┐
│         Ollama + Qwen2.5 (local inference)              │
│  Input: log samples + directory metadata + business tags│
│  Output: JSON rotation/retention suggestion (+ confidence)│
└────────────────────────────┬────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────┐
│         Strategy Generator (Python)                     │
│  → writes /etc/logrotate.d/* config                     │
│  → generates systemd timers (hourly precision)          │
│  → outputs Grafana data-source hints                    │
└────────────────────────────┬────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────┐
│         Alerting (Telegram Bot)                         │
│  Strategy changes / disk water-level / anomaly spike    │
└─────────────────────────────────────────────────────────┘
```

---

## Implementation

### 1. Install Ollama & Pull Qwen2.5

```bash
# Install Ollama (works on 2GB RAM VPS)
curl -fsSL https://ollama.com/install.sh | sh

# Pull Qwen2.5 7B (4GB quantized — suitable for 2GB+ VPS)
ollama pull qwen2.5:7b-q4_0
```

Verify:

```bash
curl -s http://localhost:11434/api/generate \
  -d '{"model":"qwen2.5:7b-q4_0","prompt":"Hello","stream":false}' \
  | python3 -m json.tool
```

### 2. Log Sampler: Collect Directory Metrics

```python
#!/usr/bin/env python3
"""
log_sampler.py — Sample key metrics from /var/log/ subdirectories
"""
import os, json, time, re
from pathlib import Path
from datetime import datetime, timedelta

LOG_ROOT = "/var/log"
SAMPLE_DIR = Path("/tmp/log_analysis_samples")
SAMPLE_DIR.mkdir(exist_ok=True)

# Log directories to watch (extend as needed)
TARGET_DIRS = [
    "nginx/access.log",
    "nginx/error.log",
    "app/production.log",
    "app/error.log",
    "build/ci-build.log",
    "security/audit.log",
    "security/fail2ban.log",
]

def sample_anomalies(filepath, keywords=None, max_scan_lines=20000):
    """
    Count anomaly ratio.
    keywords: service-specific anomaly patterns (extendable)
    """
    if keywords is None:
        keywords = [
            r'\b(ERROR|FATAL|CRITICAL)\b',
            r'OOMKilled', r'memory cgroup out of memory',
            r'segmentation fault', r'kernel panic',
            r'connection refused', r'timeout', r'5\d\d',
        ]

    total = 0
    anomalies = 0
    with open(filepath, 'r', errors='replace') as f:
        for line in f:
            total += 1
            if total > max_scan_lines:
                break
            for kw in keywords:
                if re.search(kw, line, re.IGNORECASE):
                    anomalies += 1
                    break
    return anomalies, total

def get_disk_usage(path):
    st = os.statvfs(path)
    return {
        "total_gb": st.f_blocks * st.f_frsize / (1024**3),
        "used_gb": (st.f_blocks - st.f_bfree) * st.f_frsize / (1024**3),
        "used_pct": round((1 - st.f_bfree / st.f_blocks) * 100, 1),
    }

def dir_daily_growth(filepath, days=7):
    """Estimate daily growth rate (MB/day) from file mtime and size."""
    try:
        stat = os.stat(filepath)
        mtime = datetime.fromtimestamp(stat.st_mtime)
        age_days = max((datetime.now() - mtime).total_seconds() / 86400, 1)
        return round(stat.st_size / 1024**2 / age_days, 3)
    except:
        return 0.0

def main():
    results = {}
    disk = get_disk_usage(LOG_ROOT)

    for rel in TARGET_DIRS:
        filepath = os.path.join(LOG_ROOT, rel)
        if not os.path.exists(filepath):
            continue

        anomalies, total = sample_anomalies(filepath)
        anomaly_density = anomalies / total if total else 0.0
        daily_mb = dir_daily_growth(filepath)

        results[rel] = {
            "size_mb": round(os.path.getsize(filepath) / 1024**2, 2),
            "total_lines_scanned": total,
            "anomaly_count": anomalies,
            "anomaly_density": round(anomaly_density, 4),
            "daily_growth_mb": daily_mb,
        }

    meta = {
        "timestamp": datetime.now().isoformat(),
        "disk": disk,
        "dirs": results,
    }

    out_file = SAMPLE_DIR / f"meta_{int(time.time())}.json"
    out_file.write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    print(f"Sampling complete → {out_file}")
    return meta

if __name__ == "__main__":
    main()
```

### 3. LLM Strategy Generator: Core Prompt

```python
#!/usr/bin/env python3
"""
llm_strategy.py — Call local Ollama to generate rotation/retention strategy per directory
"""
import json, urllib.request

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen2.5:7b-q4_0"

SYSTEM_PROMPT = """\
You are a VPS log management expert. Based on the provided log directory metrics,
generate the optimal rotation and retention strategy.

Rules:
- Anomaly density > 5%: retention ≥ 30 days (incident investigation needs history)
- Anomaly density 1~5%: retention 14~30 days
- Anomaly density < 1%: retention 7~14 days (normal logs, low value)
- Daily growth > 100MB: MUST compress, rotation period ≤ 1 day
- Daily growth 10~100MB: compress + rotation period 1~3 days
- Daily growth < 10MB: no compression needed, rotation period 7~30 days
- Security audit logs (audit/fail2ban): force retention ≥ 90 days (compliance)
- Build logs (build/ci): 3~7 days is enough (can re-trigger build)
- Output must be valid JSON, no markdown code blocks

Output format (JSON):
{
  "directory": "nginx/access.log",
  "rotation_period_days": 1,
  "compress": true,
  "retention_days": 7,
  "reasoning": "High-volume low-anomaly access logs (0.3% density), daily rotation + compress + 7-day retention",
  "confidence": 0.85
}
"""

def call_ollama(prompt: str) -> str:
    payload = json.dumps({
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "system": SYSTEM_PROMPT,
        "options": {"temperature": 0.1, "num_predict": 1024}
    }).encode()

    req = urllib.request.Request(
        OLLAMA_URL, data=payload,
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        result = json.loads(resp.read())
    return result.get("response", "")

def generate_strategy(meta: dict) -> list:
    strategies = []
    for dir_path, data in meta["dirs"].items():
        user_prompt = f"""
Log directory: /var/log/{dir_path}
Current size: {data['size_mb']} MB
Daily growth: {data['daily_growth_mb']} MB/day
Anomaly density: {data['anomaly_density']*100:.2f}% ({data['anomaly_count']} of {data['total_lines_scanned']} lines)
Disk used: {meta['disk']['used_pct']}%

Generate the rotation strategy for this directory.
"""
        try:
            raw = call_ollama(user_prompt).strip()
            # Strip ```json wrapper if LLM added one
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            strategy = json.loads(raw)
            strategy["directory"] = f"/var/log/{dir_path}"
            strategies.append(strategy)
        except Exception as e:
            print(f"[WARN] Strategy generation failed for {dir_path}: {e}")

    return strategies

if __name__ == "__main__":
    import sys
    meta_file = sys.argv[1] if len(sys.argv) > 1 else None
    if meta_file:
        meta = json.load(open(meta_file))
        s = generate_strategy(meta)
        print(json.dumps(s, indent=2, ensure_ascii=False))
```

### 4. Generate logrotate Config + systemd Timer

```python
#!/usr/bin/env python3
"""
strategy_applier.py — Apply LLM strategies to executable configs
"""
import json, os
from pathlib import Path

LOGROTATE_CONF = Path("/etc/logrotate.d/ai-adaptive")
LOGROTATE_CONF.parent.mkdir(parents=True, exist_ok=True)

def generate_logrotate_conf(strategies: list) -> str:
    lines = ["# Generated by AI adaptive log strategy — re-run llm_strategy.py to update\n"]
    for s in strategies:
        dir_path = s.get("directory", "")
        period = s.get("rotation_period_days", 1)
        compress = s.get("compress", True)
        retention = s.get("retention_days", 7)

        if period == 1:
            period_str = "daily"
        elif period == 7:
            period_str = "weekly"
        elif period == 30:
            period_str = "monthly"
        else:
            period_str = f"{period}"

        lines.append(f'{dir_path} {{')
        lines.append(f'    {period_str}')
        lines.append(f'    rotate {retention}')
        if compress:
            lines.append('    compress')
            lines.append('    delaycompress')  # keep latest uncompressed for real-time inspection
        lines.append('    missingok')
        lines.append('    notifempty')
        lines.append('}\n')

    return "\n".join(lines)

def write_logrotate(strategies: list):
    conf = generate_logrotate_conf(strategies)
    LOGROTATE_CONF.write_text(conf)
    os.chmod(LOGROTATE_CONF, 0o644)
    print(f"✅ Written to {LOGROTATE_CONF}")
    print("-----")
    print(conf)

def generate_systemd_timer():
    timer_unit = """[Unit]
Description=AI Adaptive Log Rotation (Hourly)

[Service]
Type=oneshot
ExecStart=/usr/local/bin/log_rotate_hourly.sh
User=root

[Install]
WantedBy=timers.target
"""
    timer_file = Path("/etc/systemd/system/ai-log-rotate.timer")
    timer_file.write_text(timer_unit)
    print(f"✅ systemd timer written to {timer_file}")
    print("Run: systemctl daemon-reload && systemctl enable --now ai-log-rotate.timer")

if __name__ == "__main__":
    import sys
    strategies = json.load(open(sys.argv[1]))
    write_logrotate(strategies)
    generate_systemd_timer()
```

### 5. Disk Water-Level Monitoring + Telegram Alerts

```python
#!/usr/bin/env python3
"""
disk_guard.py — Disk water-level guard (systemd timer, every 15 min)
"""
import os, json, urllib.request, urllib.parse

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")

def send_telegram(text: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"[DRY-RUN] Telegram: {text}")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown"
    }).encode()
    urllib.request.urlopen(
        urllib.request.Request(url, data=data), timeout=10
    )

def check_disk():
    st = os.statvfs("/var/log")
    used_pct = (1 - st.f_bfree / st.f_blocks) * 100

    if used_pct >= 90:
        send_telegram(
            f"🚨 VPS Log Disk Water-Level Alert\n"
            f"Used: {used_pct:.1f}%\n"
            f"Action: run `logrotate -f /etc/logrotate.conf` immediately\n"
            f"or re-run `python3 /usr/local/bin/llm_strategy.py` to regenerate strategy"
        )
    elif used_pct >= 75:
        send_telegram(
            f"⚠️ VPS log disk usage at {used_pct:.1f}%\n"
            f"Approaching alert threshold — verify AI strategy is active"
        )

if __name__ == "__main__":
    check_disk()
```

Register the systemd timer (every 15 min):

```bash
cat > /etc/systemd/system/disk-guard.timer <<'EOF'
[Unit]
Description=Disk Water Guard (15min)

[Timer]
OnBoot=15min
OnUnitActiveSec=15min

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now disk-guard.timer
```

---

## Full Execution Flow

```bash
# 1. Sample
python3 /usr/local/bin/log_sampler.py > /tmp/log_meta.json

# 2. LLM strategy generation (Ollama must be running: systemctl enable --now ollama)
python3 /usr/local/bin/llm_strategy.py /tmp/log_meta.json > /tmp/strategies.json

# 3. Apply strategy
python3 /usr/local/bin/strategy_applier.py /tmp/strategies.json

# 4. Verify
logrotate -d /etc/logrotate.conf   # dry-run, no actual rotation
systemctl list-timers              # confirm timers registered
```

**Expected output example:**

```json
[
  {
    "directory": "/var/log/nginx/access.log",
    "rotation_period_days": 1,
    "compress": true,
    "retention_days": 7,
    "reasoning": "High-volume access logs (150MB/day, 0.2% anomaly density). Daily rotation + compress + 7-day retention is cost-optimal.",
    "confidence": 0.82
  },
  {
    "directory": "/var/log/app/error.log",
    "rotation_period_days": 1,
    "compress": false,
    "retention_days": 30,
    "reasoning": "Error logs have 12.4% anomaly density. Every line is an incident clue. 30-day uncompressed retention for fast grep-based investigation.",
    "confidence": 0.91
  },
  {
    "directory": "/var/log/security/audit.log",
    "rotation_period_days": 1,
    "compress": true,
    "retention_days": 90,
    "reasoning": "Security audit logs have a hard compliance floor of 90 days. Compression reduces disk usage without losing data.",
    "confidence": 0.97
  },
  {
    "directory": "/var/log/build/ci-build.log",
    "rotation_period_days": 1,
    "compress": true,
    "retention_days": 3,
    "reasoning": "CI build logs are re-producible. 3 days is sufficient for debugging recent build failures without wasting disk.",
    "confidence": 0.79
  }
]
```

---

## Key Design Decisions

| Decision | Choice | Reason |
|----------|--------|--------|
| LLM model | Qwen2.5 7B q4_0 | Runs on 2GB VPS, ~20 tokens/s, more than enough for structured output |
| Temperature | 0.1 | Strategy generation needs determinism, not creativity |
| Rotation execution | systemd timer | More precise than cron, supports dependency ordering (Ollama starts before strategy runs) |
| Alerting channel | Telegram Bot | Lightweight, free, mobile push in real-time |
| Config landing | logrotate (not custom) | Mature ecosystem, dry-run mode, safe by default |

---

## Troubleshooting

**Q: Ollama inference times out (>180s)?**
A: On a 2GB VPS, the first model load is slow. Subsequent inferences are fast. Increase the timeout to 300s or reduce `num_predict` to 512.

**Q: LLM JSON output fails to parse?**
A: This is a known LLM quirk. `llm_strategy.py` already strips ```json wrappers. If it still fails, set `temperature: 0.0` or upgrade to Qwen2.5 14B (needs 4GB+ VPS).

**Q: Disk usage actually increased after applying strategy?**
A: Check the `delaycompress` option — the most recent log file is not compressed, causing a temporary disk spike. Remove `delaycompress` if real-time inspection isn't critical.

---

## Summary

| Dimension | Traditional logrotate | AI Adaptive Strategy |
|-----------|----------------------|---------------------|
| Retention days | Fixed 7/14/30 | Dynamically computed from anomaly density |
| Compression | All or nothing | Based on growth rate |
| Compliance logs | Easily missed | Hard-flagged 90-day minimum |
| Maintenance cost | Scales poorly as services grow | Fully automatic: re-sample + regenerate |
| Alerts | None | Telegram water-level + strategy change notifications |

**Core value: turn log retention from a static configuration problem into a dynamic decision problem — let the LLM make the judgment, let systemd timers do the execution.**

---

*This solution requires a VPS with 2GB+ RAM. Ollama is the primary dependency. If resources are tight, reduce the sampling frequency from daily to weekly to cut inference cost.*
