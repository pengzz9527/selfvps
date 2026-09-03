---
title: "VPS 自动化运维日报：用 Python + Telegram 每天推送服务器状态报告"
description: "告别手动 SSH 巡检，用 Python 脚本定时收集 CPU、内存、磁盘、网络、进程等核心指标，通过 Telegram Bot 每天发送结构化运维日报。零成本、可定制、支持多 VPS 聚合。"
date: 2026-09-03T10:00:00+08:00
lastmod: 2026-09-03T10:00:00+08:00
slug: "vps-daily-ops-report-telegram"
tags: ["VPS", "运维自动化", "Python", "Telegram", "监控", "定时任务", "cron", "自托管", "报警"]
categories: ["运维自动化"]
draft: false
image: /images/posts/vps-daily-ops-report-telegram/featured.png
aliases: [/zh/post/vps-daily-ops-report-telegram/]
---

## 为什么需要运维日报？

管理多台 VPS 时，最痛苦的不是出问题——而是**不知道问题什么时候发生**。

你可能有 5 台、10 台甚至更多服务器，每台都跑着不同的服务。你不可能每天 SSH 到每台机器上检查状态。等你发现"磁盘满了"的时候，网站已经挂了 3 天了。

运维日报的核心价值在于：**把被动救火变成主动感知**。每天固定时间收到一份结构化的服务器状态汇总，异常情况一目了然，正常情况无需关心。

---

## 方案架构

整个方案由三个核心组件构成：

```
┌─────────────────────────────────────────────────────┐
│                    定时触发层                         │
│  cron / systemd timer → 每天 08:00 执行              │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│                  数据采集层                           │
│  Python 脚本读取 /proc 系统指标                       │
│  - CPU 使用率 / 负载 / 核心数                         │
│  - 内存总量 / 已用 / 缓存                            │
│  - 磁盘使用率 / inode / IO 统计                      │
│  - 网络流量 / 连接数 / 带宽                          │
│  - 关键进程状态（nginx, docker, sshd）               │
│  - 系统运行时间 / 最近重启时间                        │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│                  消息推送层                           │
│  Telegram Bot API → 加密推送至个人/群组               │
│  - Markdown 格式化排版                               │
│  - 异常项高亮标记（🔴 红色警告）                      │
│  - 支持多 VPS 聚合为一份报告                          │
└─────────────────────────────────────────────────────┘
```

这个架构的优势是**完全本地化**——所有数据采集在你自己的 VPS 上完成，只有最终的推送消息经过 Telegram 服务器。不需要部署 Prometheus、Grafana 等重量级监控栈，资源占用几乎为零。

---

## 第一步：创建 Telegram Bot

打开 Telegram，搜索 `@BotFather`，发送 `/newbot`，按提示设置 bot 名称（如 `VPS-Daily-Report`）。BotFather 会给你一个 **API Token**，格式类似 `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`。

然后获取你的 **Chat ID**：

```bash
# 发送任意消息给你的 bot，然后查询
curl -s "https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates" | python3 -m json.tool
```

找到你发送消息的 `chat.id` 字段值，记录下来。后续 Python 脚本需要用这两个值。

> **安全提示**：Bot Token 和 Chat ID 属于敏感信息，请放入 `.env` 文件或环境变量中，不要硬编码在脚本里。

---

## 第二步：安装依赖

```bash
pip3 install python-dotenv requests
```

只需要两个库：`requests` 用于调用 Telegram API，`python-dotenv` 用于管理环境变量。

---

## 第三步：编写数据采集脚本

创建 `vps_report.py`：

```python
#!/usr/bin/env python3
"""VPS Daily Ops Report — collect system metrics and send via Telegram."""

import os
import re
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
    """读取 CPU 使用率和负载。"""
    with open("/proc/loadavg") as f:
        loadavg = f.read().split()
    uptime = float(loadavg[0])
    
    # CPU 使用率（采样 1 秒）
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
    """读取内存使用情况。"""
    mem = {}
    with open("/proc/meminfo") as f:
        for line in f:
            match = re.match(r"(\w+):\s+(\d+)", line)
            if match:
                mem[match.group(1)] = int(match.group(2)) * 1024  # 转为字节
    
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
    """读取磁盘使用情况。"""
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
    """读取网络流量和连接数。"""
    # 网络接口统计
    net_dev = {}
    with open("/proc/net/dev") as f:
        lines = f.readlines()[2:]  # 跳过标题行
    for line in lines:
        parts = line.split()
        if len(parts) >= 10:
            iface = parts[0].rstrip(":")
            if iface not in ("lo",):
                net_dev[iface] = {
                    "rx_bytes": int(parts[1]),
                    "tx_bytes": int(parts[9]),
                }
    
    # 连接数统计
    result = subprocess.run(
        ["ss", "-s"], capture_output=True, text=True
    )
    conn_summary = result.stdout.strip().split("\n")[0]
    
    return {"interfaces": net_dev, "connections": conn_summary}

def get_process_status(services):
    """检查关键进程是否运行。"""
    statuses = {}
    for svc in services:
        r = subprocess.run(
            ["systemctl", "is-active", svc],
            capture_output=True, text=True
        )
        statuses[svc] = r.stdout.strip()
    return statuses

def format_report(metrics):
    """将指标格式化为 Telegram Markdown 消息。"""
    lines = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines.append(f"📊 *VPS 日报 · {HOSTNAME}*")
    lines.append(f"🕐 {now}")
    lines.append("")
    
    # CPU
    cpu = metrics["cpu"]
    cpu_status = "🟢" if cpu["load_ratio"] < 1.0 else "🟡" if cpu["load_ratio"] < 2.0 else "🔴"
    lines.append(f"🖥️ *CPU* {cpu_status}")
    lines.append(f"   使用率: {cpu['cpu_percent']}%  |  负载: {cpu['load_1m']:.2f} ({cpu['nproc']}核)")
    lines.append(f"   1m/5m/15m: {cpu['load_1m']:.2f} / {cpu['load_5m']:.2f} / {cpu['load_15m']:.2f}")
    lines.append("")
    
    # 内存
    mem = metrics["memory"]
    mem_status = "🟢" if mem["percent"] < 80 else "🟡" if mem["percent"] < 90 else "🔴"
    lines.append(f"💾 *内存* {mem_status}")
    lines.append(f"   已用: {mem['used']} / {mem['total']}  ({mem['percent']}%)")
    lines.append(f"   可用: {mem['available']}  |  Buffers+Cache: {mem['buffers_cached']}")
    lines.append("")
    
    # 磁盘
    lines.append("💿 *磁盘*")
    for d in metrics["disks"]:
        pct = int(d["percent"])
        icon = "🟢" if pct < 70 else "🟡" if pct < 85 else "🔴"
        lines.append(f"   {icon} {d['mount']}: {d['used']}/{d['size']} ({d['percent']}%)  可用: {d['avail']}")
    lines.append("")
    
    # 网络
    net = metrics["network"]
    lines.append("🌐 *网络*")
    for iface, stats in net["interfaces"].items():
        rx = stats["rx_bytes"] / (1024**3)
        tx = stats["tx_bytes"] / (1024**3)
        lines.append(f"   {iface}: 接收 {rx:.2f} GB  |  发送 {tx:.2f} GB")
    lines.append(f"   连接统计: {net['connections']}")
    lines.append("")
    
    # 关键进程
    lines.append("🔧 *关键服务*")
    for svc, status in metrics["services"].items():
        icon = "🟢" if status == "active" else "🔴"
        lines.append(f"   {icon} {svc}: {status}")
    lines.append("")
    
    # 运行时间
    with open("/proc/uptime") as f:
        uptime_sec = float(f.read().split()[0])
    days = int(uptime_sec // 86400)
    hours = int((uptime_sec % 86400) // 3600)
    lines.append(f"⏱️ *运行时间*: {days}天 {hours}小时")
    
    return "\n".join(lines)

def send_telegram(message):
    """发送 Telegram 消息。"""
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
    import socket
    main()
```

---

## 第四步：配置环境变量

创建 `.env` 文件（记得加入 `.gitignore`）：

```bash
TG_BOT_TOKEN=123456789:ABCdefGHIjklMNopqrsTUVwxyz
TG_CHAT_ID=987654321
HOSTNAME=vps-prod-01
```

---

## 第五步：设置定时任务

使用 **cron** 每天 08:00 自动执行：

```bash
crontab -e
```

添加以下行（假设 Python 路径为 `/usr/bin/python3`，脚本在 `~/scripts/vps_report.py`）：

```cron
# VPS 每日运维日报 — 每天早上 8 点
0 8 * * * /usr/bin/python3 /root/scripts/vps_report.py >> /var/log/vps_report.log 2>&1
```

> **建议**：同时配置 systemd timer 作为 cron 的替代方案，支持更精确的时间控制和失败重试。

创建 `/etc/systemd/system/vps-daily-report.timer`：

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

创建 `/etc/systemd/system/vps-daily-report.service`：

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

启用并启动：

```bash
systemctl daemon-reload
systemctl enable --now vps-daily-report.timer
systemctl status vps-daily-report.timer
```

---

## 多 VPS 聚合报告

当你管理多台 VPS 时，可以把所有机器的报告汇总到同一个 Telegram 群组。方法很简单：

1. **统一 Bot**：所有 VPS 使用同一个 Bot Token
2. **统一 Chat ID**：创建一个 Telegram 群组，把 Bot 加入群组，获取群组 Chat ID
3. **每台 VPS 独立运行脚本**：只需修改 `.env` 中的 `HOSTNAME`

这样每天你会收到一份包含所有服务器状态的聚合报告，格式如下：

```
📊 VPS 日报 · vps-web-01
🕐 2026-09-03 08:00

🖥️ CPU 🟢
   使用率: 23.5%  |  负载: 0.45 (4核)
   ...

📊 VPS 日报 · vps-db-01
🕐 2026-09-03 08:00

🖥️ CPU 🔴
   使用率: 89.2%  |  负载: 5.67 (4核)
   ...
```

---

## 异常告警增强

日报适合日常巡检，但如果你想**出现问题立即通知**，可以在此基础上添加异常检测逻辑：

```python
def check_alerts(metrics):
    """检查是否需要立即告警。"""
    alerts = []
    
    cpu = metrics["cpu"]
    if cpu["load_ratio"] > 2.0:
        alerts.append(f"🔴 CPU 负载过高: {cpu['load_ratio']:.2f}x 核心数")
    
    mem = metrics["memory"]
    if mem["percent"] > 90:
        alerts.append(f"🔴 内存使用率过高: {mem['percent']}%")
    
    for d in metrics["disks"]:
        if int(d["percent"]) > 85:
            alerts.append(f"🔴 磁盘空间不足: {d['mount']} {d['percent']}%")
    
    for svc, status in metrics["services"].items():
        if status != "active":
            alerts.append(f"🔴 服务异常: {svc} 状态={status}")
    
    return alerts
```

当检测到异常时，发送一条简短的告警消息，而不是完整的日报：

```
🚨 VPS 告警 · vps-db-01
⏰ 2026-09-03 08:00
🔴 磁盘空间不足: /data 92%
🔴 服务异常: postgresql 状态=inactive
```

---

## 进阶：周报与月度总结

在日报的基础上，你可以轻松扩展出周报和月度总结：

| 报告类型 | 频率 | 内容差异 |
|---------|------|---------|
| 日报 | 每天 | 当前状态快照 |
| 周报 | 每周 | 趋势图表 + 异常统计 |
| 月报 | 每月 | 资源使用趋势 + 成本分析 |

周报的关键是记录历史数据。只需在每次执行时追加一条记录到 CSV 或 SQLite：

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

有了历史数据，周报就可以展示趋势：

```
📈 本周趋势 (vps-web-01)
CPU 平均: 32%  |  峰值: 78% (周三 14:00)
内存平均: 65%  |  峰值: 82% (周一)
磁盘增长: +2.3 GB (本周新增备份文件)
```

---

## 完整方案总结

这套方案的核心设计理念是**轻量、可控、零依赖外部监控服务**：

| 特性 | 说明 |
|------|------|
| **零成本** | 仅需一个免费 Telegram Bot，无需付费监控服务 |
| **低资源** | Python 脚本单次运行 < 50MB 内存，< 1 秒 CPU |
| **隐私安全** | 所有数据采集在本地完成，不经第三方监控平台 |
| **易扩展** | 添加新指标只需修改一个函数 |
| **多 VPS** | 同一 Bot + 群组即可聚合多台机器报告 |
| **可告警** | 在日报基础上轻松添加异常检测 |

对于个人开发者、小团队或预算有限的自托管用户来说，这是性价比最高的日常运维方案之一。与其花重金购买 Datadog 或 New Relic，不如用 Python 和 Telegram 搭一个完全属于自己的轻量监控体系。
