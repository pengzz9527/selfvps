---
title: "AI 驱动的智能日志异常检测：在 VPS 上搭建自动化运维监控体系"
description: "告别手动翻阅日志：在 VPS 上利用 LLM + 时序数据库 + 消息通知，搭建 AI 驱动的日志异常检测系统，实现 7×24 小时自动化运维，让异常在用户感知前就被发现和处理"
date: 2026-06-06T21:30:00+08:00
slug: "ai-log-anomaly-detection-vps"
tags: ["AI运维", "日志分析", "异常检测", "LLM", "VPS监控", "自动化", "ELK", "时序数据库", "Promtail", "Grafana"]
categories: ["AI运维"]
aliases: [/zh/post/ai-log-anomaly-detection-vps/]
draft: false
image: /images/posts/ai-log-anomaly-detection-vps/featured.png
---

## 为什么 VPS 需要 AI 日志异常检测？

大多数 VPS 用户的运维模式是：**出问题了才去看日志**。这种被动式运维有几个致命缺陷：

- **响应滞后** — 用户报告网站打不开，你才开始翻日志找原因
- **海量日志淹没关键信息** — 一台繁忙的 VPS 每天产生数万条日志，人工筛查几乎不可能
- **模式识别困难** — 缓慢的资源耗尽、渐进式攻击、间歇性故障，常规阈值告警很难捕获
- **根因分析耗时** — 即使发现了异常，要定位真正原因仍需大量排查时间

**AI 日志异常检测**解决了这些问题：通过机器学习模型自动学习日志的"正常模式"，实时识别偏离，并在发现异常时自动通知甚至自动修复。

本文将介绍如何在 VPS 上搭建一套完整的 AI 驱动日志异常检测系统，涵盖 **日志采集 → 存储 → 异常分析 → 告警通知 → 自动响应** 全链路。

---

## 系统架构概览

```
┌─────────────────────────────────────────────────────────────┐
│                        VPS 服务器                           │
│  ┌──────────┐  ┌───────────┐  ┌──────────┐  ┌───────────┐  │
│  │ Promtail │─▶│ Loki/时序  │─▶│ AI分析引擎│─▶│ 通知渠道  │  │
│  │ (采集)   │  │ 数据库     │  │ (LLM/     │  │ 邮件/     │  │
│  └──────────┘  └───────────┘  │  模型)    │  │ Telegram  │  │
│                               └──────────┘  └───────────┘  │
│       ▲                            │                         │
│       │  结构化日志                  ▼                         │
│  ┌──────────┐              ┌───────────┐                     │
│  │ 应用日志  │              │ 异常工单   │                     │
│  │ 系统日志  │◀─────────────│ 自动响应   │                     │
│  │ 容器日志  │              └───────────┘                     │
│  └──────────┘                                                │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │  外部通知通道    │
                    │  Slack/Telegram │
                    │  邮件/钉钉/企微  │
                    └─────────────────┘
```

**核心组件：**

| 组件 | 作用 | 推荐方案 |
|------|------|----------|
| 日志采集 | 收集各来源日志 | Promtail / Filebeat / Fluent Bit |
| 日志存储 | 高效存储和查询 | Loki（轻量）或 ELK（功能全） |
| AI 异常检测 | 识别偏离正常模式的日志 | 自定义 Python 脚本 + LLM API |
| 时序数据库 | 存储指标和告警历史 | Prometheus / TimescaleDB |
| 通知渠道 | 异常时即时通知 | Telegram Bot / 邮件 / 钉钉 |

---

## 第一步：部署日志基础设施

### 方案 A：轻量级 — Loki + Promtail（推荐 1-2C 低配 VPS）

Loki 是 Grafana 推出的轻量级日志系统，不建立全文索引，只打标签，资源占用极低（2C2G 即可运行）。

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

  # 可选：用于时序数据
  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - ./prom-data:/prometheus
    restart: unless-stopped
```

### 方案 B：完整方案 — ELK Stack（推荐 4C 以上 VPS）

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

## 第二步：构建 AI 异常检测引擎

这是整个系统的核心。我们使用 Python 构建一个可部署在 VPS 上的检测引擎。

### 2.1 安装依赖

```bash
pip install python-dotenv openai langchain tiktoken psutil
```

### 2.2 异常检测脚本

```python
#!/usr/bin/env python3
"""
VPS AI 日志异常检测引擎
- 定期从 Loki/Prometheus 拉取日志
- 使用 LLM 分析日志模式，检测异常
- 发现异常时发送通知
"""

import os
import json
import time
import subprocess
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

# LLM API 配置
LLM_API_KEY = os.getenv("OPENAI_API_KEY", os.getenv("ANTHROPIC_API_KEY", ""))
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")

# Loki 端点（如果不用 Loki，可以改从 syslog 或 journalctl 读取）
LOKI_URL = os.getenv("LOKI_URL", "http://localhost:3100")

# 通知配置
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
SMTP_SERVER = os.getenv("SMTP_SERVER", "")
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "")


def get_recent_logs(lines=500):
    """从 Loki 获取最近日志"""
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
        return logs[-lines:]  # 最近 N 条
    
    # 备用：从 journalctl 读取
    return get_journal_logs(lines)


def get_journal_logs(lines=500):
    """从 systemd journal 获取日志"""
    cmd = ["journalctl", "-n", str(lines), "--no-pager", "-q"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        return result.stdout.strip().split('\n')
    return []


def get_system_metrics():
    """获取系统资源指标"""
    import psutil
    
    metrics = {
        "cpu_percent": psutil.cpu_percent(interval=1),
        "memory_percent": psutil.virtual_memory().percent,
        "disk_percent": psutil.disk_usage('/').percent,
        "load_1m": os.getloadavg()[0] if hasattr(os, 'getloadavg') else 0,
        "boot_time": datetime.fromtimestamp(psutil.boot_time()).isoformat()
    }
    
    # 网络 I/O
    net = psutil.net_io_counters()
    metrics.update({
        "bytes_sent_mb": round(net.bytes_sent / 1024 / 1024, 2),
        "bytes_recv_mb": round(net.bytes_recv / 1024 / 1024, 2),
    })
    
    # 活跃连接数
    try:
        connections = len(psutil.net_connections(kind='inet'))
        metrics["active_connections"] = connections
    except:
        metrics["active_connections"] = "N/A"
    
    # 进程数
    metrics["process_count"] = len(psutil.pids())
    
    return metrics


def analyze_logs_with_llm(logs, metrics):
    """使用 LLM 分析日志，检测异常"""
    
    # 构建分析提示
    system_prompt = """你是一个资深 SRE（站点可靠性工程师），专门负责 VPS 和服务器运维。
你的任务是分析服务器日志和系统指标，识别：
1. **异常事件** — 偏离正常行为的错误、警告或可疑活动
2. **资源瓶颈** — CPU、内存、磁盘、网络资源的异常使用
3. **安全威胁** — 入侵尝试、暴力破解、未授权访问
4. **潜在根因** — 异常的根本原因分析

请结构化地输出分析结果。只报告真正的异常，避免误报。"""

    user_content = f"""## 系统指标（当前）
{json.dumps(metrics, ensure_ascii=False, indent=2)}

## 最近日志（最近1小时）
{'\n'.join(logs[:200])}

## 请分析并报告：
1. 发现的异常列表（每条包含：严重级别、类型、详情）
2. 是否需要立即处理
3. 建议的排查步骤"""

    # 调用 LLM
    try:
        from openai import OpenAI
        client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)
        
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            temperature=0.1,  # 低温度提高一致性
            max_tokens=2000
        )
        
        return response.choices[0].message.content
    except Exception as e:
        return f"LLM 调用失败: {str(e)}"


def classify_severity(analysis_text):
    """对分析文本进行严重级别分类"""
    lower = analysis_text.lower()
    if any(k in lower for k in ["紧急", "critical", "严重", "紧急处理", "安全威胁", "入侵"]):
        return "CRITICAL"
    elif any(k in lower for k in ["警告", "warning", "注意", "需要处理"]):
        return "WARNING"
    elif any(k in lower for k in ["异常", "anomaly", "偏离", "异常行为"]):
        return "INFO"
    return "OK"


def send_telegram_alert(message, severity="INFO"):
    """发送 Telegram 告警"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    
    emoji = {"CRITICAL": "🚨", "WARNING": "⚠️", "INFO": "ℹ️"}.get(severity, "📋")
    
    text = f"{emoji} [{severity}] VPS 异常检测\n\n{message}"
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    
    try:
        import urllib.request
        import urllib.parse
        data = urllib.parse.urlencode({"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}).encode()
        req = urllib.request.Request(url, data=data)
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"Telegram 发送失败: {e}")


def send_email_alert(subject, body):
    """发送邮件告警"""
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
        print(f"邮件发送失败: {e}")


def run_detection():
    """执行一次完整的异常检测"""
    print(f"[{datetime.now().isoformat()}] 开始检测...")
    
    # 1. 获取日志
    logs = get_recent_logs(lines=300)
    print(f"  获取到 {len(logs)} 条日志")
    
    # 2. 获取系统指标
    metrics = get_system_metrics()
    
    # 检查硬阈值（快速筛选）
    alert_thresholds = False
    if metrics["cpu_percent"] > 90:
        print("  ⚠️ CPU 使用率异常高")
        alert_thresholds = True
    if metrics["memory_percent"] > 90:
        print("  ⚠️ 内存使用率异常高")
        alert_thresholds = True
    if metrics["disk_percent"] > 90:
        print("  ⚠️ 磁盘使用率异常高")
        alert_thresholds = True
    
    # 3. LLM 分析
    print("  正在调用 LLM 分析...")
    analysis = analyze_logs_with_llm(logs, metrics)
    severity = classify_severity(analysis)
    
    print(f"  分析完成，严重级别: {severity}")
    
    # 4. 如果有异常，发送通知
    if severity != "OK":
        summary = f"```\n{analysis[:1500]}\n```"
        send_telegram_alert(summary, severity)
        send_email_alert(f"[{severity}] VPS 异常检测报告", f"<pre>{analysis[:3000]}</pre>")
        print(f"  📤 已发送 {severity} 级别告警")
    else:
        print("  ✅ 一切正常，无需告警")
    
    # 5. 记录检测结果
    result = {
        "timestamp": datetime.now().isoformat(),
        "severity": severity,
        "metrics": metrics,
        "analysis": analysis[:500],  # 只保存摘要
        "logs_count": len(logs)
    }
    
    with open("/root/selfvps/logs/detection_results.json", "a") as f:
        f.write(json.dumps(result, ensure_ascii=False) + "\n")
    
    return severity


if __name__ == "__main__":
    run_detection()
```

### 2.3 配置 .env 文件

```bash
# /root/selfvps/.env
# LLM API 配置
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxx
LLM_BASE_URL=https://api.openai.com/v1
# 或使用 Anthropic
# ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxxxxx
# LLM_BASE_URL=https://api.anthropic.com/v1
# LLM_MODEL=claude-sonnet-4-20250514

# Loki（可选）
LOKI_URL=http://localhost:3100

# Telegram 通知
TELEGRAM_BOT_TOKEN=1234567890:ABCDEF...
TELEGRAM_CHAT_ID=123456789

# 邮件通知（可选）
SMTP_SERVER=smtp.gmail.com
SMTP_USER=you@gmail.com
SMTP_PASSWORD=app_password
ADMIN_EMAIL=admin@yourdomain.com

# 系统
ADMIN_EMAIL=admin@yourdomain.com
```

### 2.4 设置定时任务

```bash
# 每 15 分钟执行一次检测
crontab -e

# 添加以下行
*/15 * * * * cd /root/selfvps && /usr/bin/python3 /root/selfvps/scripts/ai_log_detector.py >> /root/selfvps/logs/detector.log 2>&1

# 每天凌晨 2 点生成日报
0 2 * * * cd /root/selfvps && /usr/bin/python3 /root/selfvps/scripts/ai_daily_report.py >> /root/selfvps/logs/daily_report.log 2>&1
```

---

## 第三步：实现自动响应（可选进阶）

异常检测到之后，更进一步是**自动修复**。以下是一个简单的自动响应框架：

```python
#!/usr/bin/env python3
"""
VPS 自动响应引擎
根据 AI 分析结果自动执行修复操作
"""

import subprocess
import json
from datetime import datetime

# 定义自动修复规则
AUTO_FIX_RULES = {
    "high_cpu": {
        "condition": lambda m: m.get("cpu_percent", 0) > 90,
        "actions": [
            {"type": "log", "message": "CPU 持续高负载，正在检查进程..."},
            {"type": "exec", "cmd": "ps aux --sort=-%cpu | head -10"},
            {"type": "alert", "message": "CPU 高负载 TOP 进程已记录"},
        ]
    },
    "high_memory": {
        "condition": lambda m: m.get("memory_percent", 0) > 90,
        "actions": [
            {"type": "log", "message": "内存使用率过高"},
            {"type": "exec", "cmd": "free -h"},
            {"type": "exec", "cmd": "ps aux --sort=-%mem | head -10"},
        ]
    },
    "high_disk": {
        "condition": lambda m: m.get("disk_percent", 0) > 90,
        "actions": [
            {"type": "log", "message": "磁盘空间不足，正在清理..."},
            {"type": "exec", "cmd": "du -sh /var/log/* 2>/dev/null | sort -rh | head -5"},
            {"type": "exec", "cmd": "journalctl --vacuum-time=3d"},
            {"type": "exec", "cmd": "find /tmp -mtime +7 -delete 2>/dev/null"},
        ]
    },
    "brute_force_detected": {
        "condition": None,  # 由 AI 检测结果触发
        "actions": [
            {"type": "exec", "cmd": "iptables -A INPUT -p tcp --dport 22 -m recent --set"},
            {"type": "exec", "cmd": "iptables -A INPUT -p tcp --dport 22 -m recent --update --seconds 60 --hitcount 5 -j DROP"},
            {"type": "alert", "message": "检测到暴力破解，已临时封禁 IP"},
        ]
    },
    "service_down": {
        "condition": None,
        "actions": [
            {"type": "exec", "cmd": "systemctl restart <service_name>"},
            {"type": "alert", "message": "服务已自动重启"},
        ]
    }
}


def execute_auto_fix(rule_name, metrics, ai_analysis):
    """执行自动修复"""
    rule = AUTO_FIX_RULES.get(rule_name)
    if not rule:
        return
    
    # 检查条件
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
            # 安全过滤：只允许安全的命令
            dangerous = ["rm -rf /", "mkfs", "dd if=", "> /dev/"]
            if any(d in cmd for d in dangerous):
                print(f"  ⛔ 危险命令被阻止: {cmd}")
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
    
    # 记录操作日志
    if log_entries:
        with open("/root/selfvps/logs/auto_fix.log", "a") as f:
            f.write(f"=== {rule_name} ===\n")
            f.write("\n".join(log_entries) + "\n\n")
```

---

## 第四步：可视化与 Dashboard

### 4.1 Grafana 集成（Loki 用户）

在 Docker 中添加 Grafana：

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

### 4.2 推荐 Dashboard

创建 `grafana/datasources/loki.yml`:

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

**推荐的监控面板：**
- 📊 **系统资源总览** — CPU/内存/磁盘/网络实时曲线
- 📋 **日志异常热力图** — 按小时/天展示异常密度
- 🚨 **告警历史** — 历史告警趋势和恢复时间
- 🔍 **日志快速搜索** — 支持正则和关键词过滤

### 4.3 AI 检测日报生成

```python
#!/usr/bin/env python3
"""
每日 AI 运维报告生成器
每天生成一份 VPS 健康报告
"""

import json
import os
from datetime import datetime, timedelta

def generate_daily_report():
    """从检测结果生成日报"""
    log_file = "/root/selfvps/logs/detection_results.json"
    
    if not os.path.exists(log_file):
        return "今日无检测数据"
    
    # 读取今日检测记录
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
        return f"{today} 无检测记录"
    
    # 统计
    severity_counts = {}
    total_anomalies = 0
    for entry in entries:
        sev = entry.get("severity", "OK")
        severity_counts[sev] = severity_counts.get(sev, 0) + 1
        if sev != "OK":
            total_anomalies += 1
    
    report = f"""
📊 VPS 日报 — {today}
{'='*40}

🔢 检测次数: {len(entries)}
✅ 正常次数: {severity_counts.get('OK', 0)}
ℹ️ 轻度异常: {severity_counts.get('INFO', 0)}
⚠️ 警告: {severity_counts.get('WARNING', 0)}
🚨 严重: {severity_counts.get('CRITICAL', 0)}

📈 异常总计: {total_anomalies} 次
"""
    
    # 添加指标汇总
    if entries:
        last = entries[-1]
        metrics = last.get("metrics", {})
        report += f"""
📋 最新指标:
  CPU: {metrics.get('cpu_percent', 'N/A')}%
  内存: {metrics.get('memory_percent', 'N/A')}%
  磁盘: {metrics.get('disk_percent', 'N/A')}%
  活跃连接: {metrics.get('active_connections', 'N/A')}
"""
    
    return report


if __name__ == "__main__":
    report = generate_daily_report()
    print(report)
    
    # 发送 Telegram
    from ai_log_detector import send_telegram_alert
    send_telegram_alert(report, "INFO")
```

---

## 费用估算

| 项目 | 方案 A（Loki） | 方案 B（ELK） |
|------|---------------|--------------|
| VPS 配置 | 1C1G~2C2G | 2C4G~4C8G |
| 月费用 | ¥15~40 | ¥60~200 |
| LLM API（月度检测） | ¥5~20（GPT-4o-mini） | ¥5~20 |
| Telegram Bot | 免费 | 免费 |
| 邮件 | 免费（Gmail） | 免费 |

**最低成本方案：** 使用 1C1G VPS + Loki + GPT-4o-mini（$0.15/1M tokens），每月成本可控制在 ¥20 以内。

---

## 进阶优化方向

### 1. 使用本地模型降低 API 成本

如果 VPS 有 GPU 或内存充足（16G+），可以部署轻量级本地模型：

```bash
# 使用 Ollama 部署本地模型
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.2:3b

# 修改 LLM_BASE_URL 指向本地
# LLM_BASE_URL=http://localhost:11434/v1
```

### 2. 基于规则 + AI 混合检测

先用高效的规则过滤掉大部分正常日志，再把可疑日志交给 LLM，大幅降低 API 调用成本：

```python
# 快速规则过滤
def quick_filter(logs):
    suspicious = []
    for log in logs:
        # 常见异常关键词
        if any(kw in log for kw in [
            "SEGFAULT", "OOM", "PANIC", "kernel panic",
            "permission denied", "connection refused",
            "authentication failure", "rate limit",
            "disk full", "out of memory"
        ]):
            suspicious.append(log)
    
    # 只把可疑日志发给 LLM
    if suspicious:
        return analyze_with_llm(suspicious)
    return None
```

### 3. 多 VPS 统一监控

如果你有多个 VPS，可以部署一个集中式的 AI 检测节点：

```bash
# 在各 VPS 上安装 Promtail
# 将日志发送到集中的 Loki 实例
# 单个 AI 检测引擎分析所有 VPS 日志
```

### 4. 自定义异常模型

对于特定应用，可以训练专用的异常检测模型：

```python
# 使用 simple-anomaly-detector 或同类库
from adtk.detector import FrequencyAD, ThresholdAD

# 基于历史数据训练正常模式
detector = FrequencyAD(c=3.0)  # 3σ 异常
alerts = detector.detect(log_volume_series)
```

---

## 总结

这套 **AI 驱动的 VPS 日志异常检测系统** 提供了：

1. **自动化** — 7×24 小时无人值守监控
2. **智能分析** — LLM 理解日志语义，远超传统正则匹配
3. **即时通知** — 异常出现秒级通知到手机
4. **自动响应** — 预设规则自动修复常见问题
5. **成本可控** — 最低 ¥20/月即可运行完整系统

从手动翻日志到 AI 自动监控，这是 VPS 运维的必经之路。现在就开始搭建你的第一套 AI 监控体系吧！

---

*本文代码示例可在仓库的 `scripts/ai_log_detector.py` 找到完整版本。欢迎 Star 和 Fork。*
