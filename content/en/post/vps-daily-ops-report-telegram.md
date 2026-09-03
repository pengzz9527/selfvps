---
title: "VPS Automated Daily Ops Report: Python + Telegram Server Status Push"
description: "Stop manually SSH-ing into every server. Use a Python script to collect CPU, memory, disk, network, and process metrics, then deliver a structured daily ops report via Telegram Bot. Zero cost, fully customizable, multi-VPS aggregation supported."
date: 2026-09-03T10:00:00+08:00
lastmod: 2026-09-03T10:00:00+08:00
slug: "vps-daily-ops-report-telegram"
tags: ["VPS", "Ops Automation", "Python", "Telegram", "Monitoring", "Cron", "Self-hosted", "Alerting"]
categories: ["Ops Automation"]
draft: false
image: /images/posts/vps-daily-ops-report-telegram/featured.png
aliases: [/en/post/vps-daily-ops-report-telegram/]
---

## Why Do You Need a Daily Ops Report?

When managing multiple VPS instances, the biggest pain isn't dealing with outages—it's **not knowing when they happen**.

You might have 5, 10, or more servers running different services. You can't SSH into each one every day to check their status. By the time you discover "the disk is full," your website has been down for three days.

The core value of a daily ops report is simple: **turn reactive firefighting into proactive awareness**. Receive a structured summary of your server status at a fixed time each day. Anomalies become immediately visible; normal operations require no action.

---

## Architecture Overview

The solution consists of three core components:

```
┌─────────────────────────────────────────────────────┐
│                  Scheduling Layer                    │
│  cron / systemd timer → runs daily at 08:00         │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│                 Data Collection Layer                │
│  Python script reads /proc system metrics             │
│  - CPU usage / load average / core count             │
│  - Memory total / used / cached                      │
│  - Disk usage / inode / IO stats                     │
│  - Network traffic / connection count / bandwidth    │
│  - Key process status (nginx, docker, sshd)          │
│  - Uptime / last reboot time                         │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│                 Delivery Layer                       │
│  Telegram Bot API → encrypted push to personal/group │
│  - Markdown formatted layout                         │
│  - Anomaly highlighting (🔴 red alerts)              │
│  - Multi-VPS aggregation into single report          │
└─────────────────────────────────────────────────────┘
```

The key advantage: **everything is localized**. All data collection happens on your own VPS. Only the final推送 message traverses Telegram's servers. No need to deploy heavyweight monitoring stacks like Prometheus or Grafana—resource overhead is nearly zero.

---

## Step 1: Create a Telegram Bot

Open Telegram, search for `@BotFather`, send `/newbot`, and follow the prompts to set a bot name (e.g., `VPS-Daily-Report`). BotFather will give you an **API Token** in the format `123456789:ABCdefGHIjklMNopqrsTUVwxyz`.

Then retrieve your **Chat ID**:

```bash
# Send any message to your bot, then query
curl -s "https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates" | python3 -m json.tool
```

Find the `chat.id` field from your message and record it. Both values are needed by the Python script.

> **Security note**: Bot Token and Chat ID are sensitive. Store them in a `.env` file or environment variables—never hard-code them in scripts.

---

## Step 2: Install Dependencies

```bash
pip3 install python-dotenv requests
```

Only two libraries needed: `requests` for the Telegram API, `python-dotenv` for environment variable management.

---

## Step 3: Write the Data Collection Script

Create `vps_report.py`:

```python
#!/usr/bin/env python3
"""VPS Daily Ops Report — collect system metrics and send via Telegram."""

import os
import re
import socket
import subprocess
import time
from datetime import datetime
from dotenv import load_dotenv
import requests

load_dotenv()

TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")
HOSTNAME = os.getenv("HOSTNAME", socket.gethostname())

def get_cpu_info():
    """Read CPU usage and load averages."""
    with open("/proc/loadavg") as f:
        loadavg = f.read().split()
    
    with open("/proc/stat") as f:
        line1 = f.readline()
    time.sleep(1)
    with open("/proc/stat") as f:
        line2 = f.readline()
    
    def parse_stat(line):
        parts = line.split()
        values = [int(x) for x in parts[1:]]
        total = sum(values)
        idle = values[3] + values[4] if len(values) > 4 else values[3]
        return total, idle
    
    total1, idle1 = parse_stat(line1)
    total2, idle2 = parse_stat(line2)
    
    total_diff = total2 - total1
    idle_diff = idle2 - idle1
    cpu_percent = round((1 - idle_diff / total_diff) * 100, 1) if total_diff else 0
    
    nproc = os.cpu_count() or 1
    return {
        "cpu_percent": cpu_percent,
        "load_1m": float(loadavg[0]),
        "load_5m": float(loadavg[1]),
        "load_15m": float(loadavg[2]),
        "nproc": nproc,
        "load_ratio": round(float(loadavg[0]) / nproc, 2),
    }

def get_memory_info():
    """Read memory usage."""
    mem = {}
    with open("/proc/meminfo") as f:
        for line in f:
            match = re.match(r"(\w+):\s+(\d+)", line)
            if match:
                mem[match.group(1)] = int(match.group(2)) * 1024
    
    total = mem.get("MemTotal", 1)
    available = mem.get("MemAvailable", mem.get("MemFree", 0))
    used = total - available
    buffers = mem.get("Buffers", 0)
    cached = mem.get("Cached", 0)
    
    def human_size(b):
        for unit in ["B", "KB", "MB", "GB"]:
            if b < 1024:
                return f"{b:.1f}{unit}"
            b /= 1024
        return f"{b:.1f}TB"
    
    return {
        "total": human_size(total),
        "used": human_size(used),
        "available": human_size(available),
        "buffers_cached": human_size(buffers + cached),
        "percent": round(used / total * 100, 1),
    }

def get_disk_info():
    """Read disk usage."""
    result = subprocess.run(
        ["df", "-h", "--output=size,used,avail,pcent,target"],
        capture_output=True, text=True
    )
    disks = []
    for line in result.stdout.strip().split("\n")[1:]:
        parts = line.strip().split()
        if len(parts) >= 5:
            disks.append({
                "mount": parts[4],
                "size": parts[0],
                "used": parts[1],
                "avail": parts[2],
                "percent": parts[3].rstrip("%"),
            })
    return disks

def get_network_info():
    """Read network traffic and connection counts."""
    net_dev = {}
    with open("/proc/net/dev") as f:
        lines = f.readlines()[2:]
    for line in lines:
        parts = line.split()
        if len(parts) >= 10:
            iface = parts[0].rstrip(":")
            if iface not in ("lo",):
                net_dev[iface] = {
                    "rx_bytes": int(parts[1]),
                    "tx_bytes": int(parts[9]),
                }
    
    result = subprocess.run(
        ["ss", "-s"], capture_output=True, text=True
    )
    conn_summary = result.stdout.strip().split("\n")[0]
    
    return {"interfaces": net_dev, "connections": conn_summary}

def get_process_status(services):
    """Check if key processes are running."""
    statuses = {}
    for svc in services:
        r = subprocess.run(
            ["systemctl", "is-active", svc],
            capture_output=True, text=True
        )
        statuses[svc] = r.stdout.strip()
    return statuses

def format_report(metrics):
    """Format metrics into a Telegram Markdown message."""
    lines = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines.append(f"📊 *VPS Daily Report · {HOSTNAME}*")
    lines.append(f"🕐 {now}")
    lines.append("")
    
    cpu = metrics["cpu"]
    cpu_status = "🟢" if cpu["load_ratio"] < 1.0 else "🟡" if cpu["load_ratio"] < 2.0 else "🔴"
    lines.append(f"🖥️ *CPU* {cpu_status}")
    lines.append(f"   Usage: {cpu['cpu_percent']}%  |  Load: {cpu['load_1m']:.2f} ({cpu['nproc']} cores)")
    lines.append(f"   1m/5m/15m: {cpu['load_1m']:.2f} / {cpu['load_5m']:.2f} / {cpu['load_15m']:.2f}")
    lines.append("")
    
    mem = metrics["memory"]
    mem_status = "🟢" if mem["percent"] < 80 else "🟡" if mem["percent"] < 90 else "🔴"
    lines.append(f"💾 *Memory* {mem_status}")
    lines.append(f"   Used: {mem['used']} / {mem['total']}  ({mem['percent']}%)")
    lines.append(f"   Available: {mem['available']}  |  Buffers+Cache: {mem['buffers_cached']}")
    lines.append("")
    
    lines.append("💿 *Disk*")
    for d in metrics["disks"]:
        pct = int(d["percent"])
        icon = "🟢" if pct < 70 else "🟡" if pct < 85 else "🔴"
        lines.append(f"   {icon} {d['mount']}: {d['used']}/{d['size']} ({d['percent']}%)  Free: {d['avail']}")
    lines.append("")
    
    net = metrics["network"]
    lines.append("🌐 *Network*")
    for iface, stats in net["interfaces"].items():
        rx = stats["rx_bytes"] / (1024**3)
        tx = stats["tx_bytes"] / (1024**3)
        lines.append(f"   {iface}: RX {rx:.2f} GB  |  TX {tx:.2f} GB")
    lines.append(f"   Connections: {net['connections']}")
    lines.append("")
    
    lines.append("🔧 *Key Services*")
    for svc, status in metrics["services"].items():
        icon = "🟢" if status == "active" else "🔴"
        lines.append(f"   {icon} {svc}: {status}")
    lines.append("")
    
    with open("/proc/uptime") as f:
        uptime_sec = float(f.read().split()[0])
    days = int(uptime_sec // 86400)
    hours = int((uptime_sec % 86400) // 3600)
    lines.append(f"⏱️ *Uptime*: {days}d {hours}h")
    
    return "\n".join(lines)

def send_telegram(message):
    """Send Telegram message."""
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TG_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
    }
    r = requests.post(url, json=payload, timeout=10)
    return r.json()

def main():
    metrics = {
        "cpu": get_cpu_info(),
        "memory": get_memory_info(),
        "disks": get_disk_info(),
        "network": get_network_info(),
        "services": get_process_status([
            "nginx", "docker", "sshd", "postgresql",
            "redis-server", "mongodb", "node",
        ]),
    }
    
    report = format_report(metrics)
    result = send_telegram(report)
    
    if result.get("ok"):
        print("Report sent successfully.")
    else:
        print(f"Failed to send: {result}")
        raise SystemExit(1)

if __name__ == "__main__":
    main()
```

---

## Step 4: Configure Environment Variables

Create `.env` (add to `.gitignore`):

```bash
TG_BOT_TOKEN=123456789:ABCdefGHIjklMNopqrsTUVwxyz
TG_CHAT_ID=987654321
HOSTNAME=vps-prod-01
```

---

## Step 5: Set Up Scheduling

### Option A: Cron (simplest)

```bash
crontab -e
```

Add:

```cron
# VPS Daily Ops Report — 8:00 AM every day
0 8 * * * /usr/bin/python3 /root/scripts/vps_report.py >> /var/log/vps_report.log 2>&1
```

### Option B: systemd timer (recommended for production)

Create `/etc/systemd/system/vps-daily-report.timer`:

```ini
[Unit]
Description=VPS Daily Ops Report Timer

[Timer]
OnCalendar=*-*-* 08:00:00
Persistent=true
RandomizedDelaySec=60

[Install]
WantedBy=timers.target
```

Create `/etc/systemd/system/vps-daily-report.service`:

```ini
[Unit]
Description=VPS Daily Ops Report

[Service]
Type=oneshot
WorkingDirectory=/root
EnvironmentFile=/root/scripts/.env
ExecStart=/usr/bin/python3 /root/scripts/vps_report.py
StandardOutput=journal
StandardError=journal
```

Enable and start:

```bash
systemctl daemon-reload
systemctl enable --now vps-daily-report.timer
systemctl status vps-daily-report.timer
```

---

## Multi-VPS Aggregated Report

When managing multiple VPS instances, aggregate all reports into a single Telegram group:

1. **Unified Bot**: Use the same Bot Token across all VPS
2. **Unified Chat ID**: Create a Telegram group, add the Bot, get the group Chat ID
3. **Independent execution**: Each VPS runs the script separately, just change `HOSTNAME` in `.env`

You'll receive a consolidated daily report like:

```
📊 VPS Daily Report · vps-web-01
🕐 2026-09-03 08:00

🖥️ CPU 🟢
   Usage: 23.5%  |  Load: 0.45 (4 cores)
   ...

📊 VPS Daily Report · vps-db-01
🕐 2026-09-03 08:00

🖥️ CPU 🔴
   Usage: 89.2%  |  Load: 5.67 (4 cores)
   ...
```

---

## Enhanced Alerting for Anomalies

Daily reports are great for巡检, but for **immediate notification** when something breaks, add anomaly detection:

```python
def check_alerts(metrics):
    """Check if immediate alert is needed."""
    alerts = []
    
    cpu = metrics["cpu"]
    if cpu["load_ratio"] > 2.0:
        alerts.append(f"🔴 CPU overload: {cpu['load_ratio']:.2f}x cores")
    
    mem = metrics["memory"]
    if mem["percent"] > 90:
        alerts.append(f"🔴 Memory usage critical: {mem['percent']}%")
    
    for d in metrics["disks"]:
        if int(d["percent"]) > 85:
            alerts.append(f"🔴 Disk space low: {d['mount']} {d['percent']}%")
    
    for svc, status in metrics["services"].items():
        if status != "active":
            alerts.append(f"🔴 Service down: {svc} status={status}")
    
    return alerts
```

When anomalies are detected, send a concise alert instead of the full report:

```
🚨 VPS Alert · vps-db-01
⏰ 2026-09-03 08:00
🔴 Disk space low: /data 92%
🔴 Service down: postgresql status=inactive
```

---

## Advanced: Weekly and Monthly Summaries

Extend the daily report with weekly and monthly summaries:

| Report Type | Frequency | Content Differences |
|------------|-----------|-------------------|
| Daily | Every day | Current state snapshot |
| Weekly | Every week | Trend charts + anomaly stats |
| Monthly | Every month | Resource trends + cost analysis |

The key for weekly reports is historical data. Append each run to a CSV or SQLite database:

```python
import csv
from datetime import datetime

def append_metric_log(metrics, filepath="~/metrics_log.csv"):
    filepath = os.path.expanduser(filepath)
    file_exists = os.path.isfile(filepath)
    with open(filepath, "a") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "timestamp", "hostname", "cpu_percent", "load_ratio",
            "mem_percent", "disk_max_percent",
        ])
        if not file_exists:
            writer.writeheader()
        writer.writerow({
            "timestamp": datetime.now().isoformat(),
            "hostname": HOSTNAME,
            "cpu_percent": metrics["cpu"]["cpu_percent"],
            "load_ratio": metrics["cpu"]["load_ratio"],
            "mem_percent": metrics["memory"]["percent"],
            "disk_max_percent": max(int(d["percent"]) for d in metrics["disks"]),
        })
```

With historical data, weekly reports can show trends:

```
📈 Weekly Trends (vps-web-01)
CPU avg: 32%  |  Peak: 78% (Wed 14:00)
Memory avg: 65%  |  Peak: 82% (Mon)
Disk growth: +2.3 GB (weekly backup files)
```

---

## Summary

The core design philosophy of this solution is **lightweight, controllable, zero external monitoring dependencies**:

| Feature | Description |
|---------|-------------|
| **Zero cost** | Only needs a free Telegram Bot, no paid monitoring services |
| **Low resource** | Python script uses < 50MB RAM, < 1 second CPU per run |
| **Privacy** | All data collection is local, never touches third-party monitoring platforms |
| **Extensible** | Adding new metrics requires modifying only one function |
| **Multi-VPS** | Same Bot + group aggregates reports from multiple machines |
| **Alertable** | Easy to add anomaly detection on top of daily reports |

For individual developers, small teams, or budget-conscious self-hosters, this is one of the best cost-performance daily ops solutions available. Rather than spending heavily on Datadog or New Relic, build your own lightweight monitoring system with Python and Telegram.
