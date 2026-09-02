---
title: "AI + VPS：用大模型给服务器做全身体检——智能健康评分系统"
description: "告别零散的监控告警，让 LLM 综合 CPU、内存、磁盘、安全、网络等多维度指标，自动生成一份像体检报告一样的服务器健康评分与修复建议。"
date: 2026-09-02T21:00:00+08:00
lastmod: 2026-09-02T21:00:00+08:00
slug: "ai-vps-llm-health-scoring"
image: /images/posts/ai-vps-llm-health-scoring/featured.png
tags: ["AI运维", "LLM", "VPS健康", "智能评分", "Prometheus", "Grafana", "运维自动化"]
categories: ["AI运维"]
aliases: [/zh/post/ai-vps-llm-health-scoring/]
---

## 引言

你管理着五台、十台甚至更多的 VPS，每台都在跑着不同的服务——网站、API、数据库、缓存、定时任务。

你的监控工具能告诉你"CPU 92%"、"磁盘剩余 3GB"、"SSH 登录失败 47 次"。但这些数据是**孤立的数字**，没有人帮你回答一个最关键的问题：

**这台服务器现在到底健不健康？**

传统运维的痛点就在这里：监控数据很多，但**缺乏统一的健康判断**。运维人员需要同时看 Prometheus 面板、查系统日志、检查安全告警，才能拼凑出一个模糊的结论。

AI 大模型的引入，彻底改变了这个局面。

---

## 核心理念：从"指标告警"到"健康体检"

可以把这套系统理解为**服务器的年度体检**：

| 体检项目 | 对应的服务器指标 |
|---------|----------------|
| 血压 | CPU 负载 + 进程队列 |
| 血常规 | 内存使用 + Swap 交换 + 进程数 |
| 肝功能 | 磁盘 I/O + 文件系统健康 |
| 心电图 | 网络延迟 + 连接数 + 带宽 |
| 肿瘤筛查 | 安全日志 + 异常进程 + 未授权访问 |
| 家族病史 | 历史故障记录 + 配置变更记录 |

LLM 的职责就是：**接收所有这些"检查数据"，综合判断，给出总分和诊断建议。**

---

## 架构设计

```
┌─────────────────────────────────────────────────────────────────┐
│                     健康评分引擎 (LLM)                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │  维度评分   │  │  关联分析   │  │  趋势预测   │             │
│  │  CPU/内存   │  │  根因定位   │  │  容量预测   │             │
│  │  磁盘/I/O   │  │  影响评估   │  │  风险预判   │             │
│  │  网络       │  │  依赖链     │  │             │             │
│  │  安全       │  │             │  │             │             │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘             │
│         └─────────────────┼─────────────────┘                   │
│                           ▼                                     │
│              ┌───────────────────────┐                          │
│              │   综合健康评分 (0-100)  │                          │
│              │   + 维度的加权得分      │                          │
│              │   + 文字诊断报告        │                          │
│              └───────────────────────┘                          │
├─────────────────────────────────────────────────────────────────┤
│                     数据采集层                                   │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐   │
│  │ Prometheus│  │ journald │  │  custom  │  │  security    │   │
│  │  metrics │  │  logs    │  │  scripts │  │  audit logs  │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 第一步：定义健康评分维度

我们不搞一个笼统的"健康分"，而是**分项打分再综合**——这样才有诊断价值。

### 6 个核心维度

```yaml
# config/health_dimensions.yaml
dimensions:
  cpu:
    weight: 0.20          # 占总分 20%
    sources:
      - prometheus:node_cpu_seconds_total
      - prometheus:process_cpu_usage
    thresholds:
      critical: 90        # 0-60分
      warning:  75        # 60-80分
      normal:   50        # 80-100分

  memory:
    weight: 0.15
    sources:
      - prometheus:node_memory_MemAvailable_bytes
      - prometheus:node_memory_SwapTotal_bytes
    thresholds:
      critical: 90        # 0-60分（可用内存低于 10%）
      warning:  75
      normal:   50

  disk:
    weight: 0.15
    sources:
      - prometheus:node_filesystem_avail_bytes
      - custom: disk_io_latency
    thresholds:
      critical: 85        # 可用空间低于 15%
      warning:  70
      normal:   50

  network:
    weight: 0.15
    sources:
      - prometheus:node_network_receive_errors_total
      - prometheus:node_network_transmit_errors_total
      - custom: tcp_connections
    thresholds:
      critical: 5         # 错误连接 > 5
      warning:  2
      normal:   0

  security:
    weight: 0.20        # 安全权重最高，出了问题直接不及格
    sources:
      - custom: failed_ssh_logins
      - custom: unexpected_processes
      - custom: open_suspicious_ports
    thresholds:
      critical: 1         # 有任何一项命中
      warning:  0         # 接近但不命中
      normal:   0

  stability:
    weight: 0.15
    sources:
      - custom: uptime_hours
      - custom: restart_count_24h
      - custom: oom_kill_events
    thresholds:
      critical: 0         # 24h内发生过OOM或重启
      warning:  1         # 有异常但可控
      normal:   0
```

### 综合评分公式

```
总分 = Σ(维度得分 × 权重)

附加规则：
- 如果 security.critical == true，总分上限 = 50（安全不达标，其他再好也不合格）
- 如果 cpu.critical AND memory.critical，总分上限 = 40（多重资源耗尽，紧急）
```

---

## 第二步：数据采集脚本

这是系统的基石——把分散的数据收集成一份结构化的"体检表"。

```python
#!/usr/bin/env python3
"""采集 VPS 健康指标，输出结构化 JSON。"""

import json
import subprocess
import psutil
import urllib.request
from datetime import datetime

def get_cpu_metrics():
    """CPU 和负载指标。"""
    load_avg = psutil.getloadavg()
    cpu_percent = psutil.cpu_percent(interval=1)
    return {
        "cpu_percent": cpu_percent,
        "load_1min": load_avg[0],
        "load_5min": load_avg[1],
        "load_15min": load_avg[2],
        "cpu_count": psutil.cpu_count()
    }

def get_memory_metrics():
    """内存和 Swap 指标。"""
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()
    return {
        "mem_total_gb": round(mem.total / 1e9, 2),
        "mem_available_gb": round(mem.available / 1e9, 2),
        "mem_used_percent": mem.percent,
        "swap_total_gb": round(swap.total / 1e9, 2),
        "swap_used_percent": swap.percent,
        "mem_free_percent": round(mem.available / mem.total * 100, 1)
    }

def get_disk_metrics():
    """磁盘使用和 I/O 指标。"""
    disk = psutil.disk_usage("/")
    io = psutil.disk_io_counters()
    return {
        "disk_total_gb": round(disk.total / 1e9, 2),
        "disk_used_gb": round(disk.used / 1e9, 2),
        "disk_free_gb": round(disk.free / 1e9, 2),
        "disk_used_percent": disk.percent,
        "read_bytes": io.read_bytes if io else 0,
        "write_bytes": io.write_bytes if io else 0
    }

def get_network_metrics():
    """网络和连接指标。"""
    net = psutil.net_io_counters()
    conn = psutil.net_connections()
    tcp_count = sum(1 for c in conn if c.type.name == "STREAM")
    error_count = sum(1 for c in conn
                      if c.status in ("TIME_WAIT", "CLOSE_WAIT")
                      and c.pid is None)
    return {
        "bytes_sent": net.bytes_sent,
        "bytes_recv": net.bytes_recv,
        "tcp_connections": tcp_count,
        "zombie_connections": error_count,
        "packets_sent": net.packets_sent,
        "packets_recv": net.packets_recv
    }

def get_security_metrics():
    """安全相关指标（本地检测）。"""
    failed_logins = 0
    try:
        result = subprocess.run(
            ["journalctl", "-u", "sshdt", "--since", "24hours",
             "--no-pager", "-q"],
            capture_output=True, text=True
        )
        failed_logins = result.stdout.count("Failed password")
    except Exception:
        pass

    # 检测异常的监听端口（非标准端口）
    suspicious_ports = []
    std_ports = {22, 80, 443, 3000, 8080, 8443, 9090, 9100}
    try:
        for conn in psutil.net_connections(kind='inet'):
            if conn.status == 'LISTEN' and conn.pid:
                if conn.laddr.port not in std_ports:
                    suspicious_ports.append(conn.laddr.port)
    except Exception:
        pass

    return {
        "failed_ssh_logins_24h": failed_logins,
        "suspicious_listening_ports": suspicious_ports,
        "root_logins_24h": _count_root_logins()
    }

def get_stability_metrics():
    """稳定性指标。"""
    uptime = psutil.boot_time()
    uptime_hours = (datetime.now().timestamp() - uptime) / 3600

    # 24小时内重启次数（通过查看进程列表推断）
    # 简单方案：检查系统是否有 oom-kill 记录
    oom_kills = 0
    try:
        result = subprocess.run(
            ["dmesg", "-T", "--level", "err,warn"],
            capture_output=True, text=True
        )
        oom_kills = result.stdout.count("Out of memory")
    except Exception:
        pass

    return {
        "uptime_hours": round(uptime_hours, 1),
        "oom_kill_events": oom_kills,
        "kernel_warnings": oom_kills  # 简化：oom kill 也属于内核警告
    }

def _count_root_logins():
    """统计 24h 内 root 登录次数。"""
    try:
        result = subprocess.run(
            ["who", "-a"], capture_output=True, text=True
        )
        return result.stdout.count("root")
    except Exception:
        return 0

def collect_all():
    """汇总所有指标。"""
    data = {
        "timestamp": datetime.now().isoformat(),
        "hostname": subprocess.check_output(
            ["hostname"], text=True
        ).strip(),
        "cpu": get_cpu_metrics(),
        "memory": get_memory_metrics(),
        "disk": get_disk_metrics(),
        "network": get_network_metrics(),
        "security": get_security_metrics(),
        "stability": get_stability_metrics()
    }
    return data

if __name__ == "__main__":
    import sys
    output = collect_all()
    print(json.dumps(output, indent=2, ensure_ascii=False))
```

运行示例：
```bash
python3 collect_health.py > /tmp/health_snapshot.json
```

---

## 第三步：用 LLM 生成健康报告

这是最关键的一步——把原始指标交给 LLM，让它输出结构化的健康评分和诊断。

### 3.1 提示词设计

```python
# scripts/health_analyzer.py

SYSTEM_PROMPT = """你是一位资深 SRE（站点可靠性工程师），擅长从多维度数据中诊断服务器健康状况。

你的输出格式必须严格遵循以下 JSON 结构：
{
  "overall_score": 0-100 的整数,
  "grade": "A/B/C/D/F",
  "dimensions": {
    "cpu": {"score": 0-100, "status": "healthy/warning/critical", "detail": "简要描述"},
    "memory": {...},
    "disk": {...},
    "network": {...},
    "security": {...},
    "stability": {...}
  },
  "risk_level": "low/medium/high/critical",
  "issues": [
    {"severity": "critical/warning/info", "dimension": "...", "description": "...", "suggestion": "..."}
  ],
  "summary": "一段 2-3 句的整体健康状态总结，口语化但专业",
  "action_items": ["优先执行的操作 1", "优先执行的操作 2"]
}

评分规则：
- 安全维度出现 critical，总分不超过 50
- 多项 critical 叠加时，总分进一步下调
- grade: A(90-100) B(80-89) C(70-79) D(60-69) F(<60)
"""

USER_PROMPT_TEMPLATE = """请分析以下 VPS 健康数据，生成体检报告：

主机名：{hostname}
采集时间：{timestamp}

=== CPU ===
使用率：{cpu_percent}%
负载（1/5/15分钟）：{load_1min}/{load_5min}/{load_15min}
CPU 核数：{cpu_count}

=== 内存 ===
已用：{mem_used_percent}%
可用：{mem_available_gb} GB / 总计 {mem_total_gb} GB
Swap 使用：{swap_used_percent}%

=== 磁盘 ===
已用：{disk_used_percent}%
可用：{disk_free_gb} GB / 总计 {disk_total_gb} GB
写入量：{write_bytes_human}

=== 网络 ===
TCP 连接数：{tcp_connections}
异常连接（CLOSE_WAIT/TIME_WAIT）：{zombie_connections}
接收/发送流量：{recv_mb:.1f}MB / {sent_mb:.1f}MB

=== 安全 ===
24h SSH 失败登录：{failed_logins} 次
可疑监听端口：{suspicious_ports}
24h root 登录次数：{root_logins}

=== 稳定性 ===
运行时间：{uptime_hours} 小时
OOM kill 事件（24h）：{oom_kills}
内核警告：{kernel_warnings}

请输出完整的 JSON 健康报告。"""
```

### 3.2 调用 LLM

```python
import openai
from dotenv import load_dotenv
import json

load_dotenv()

def analyze_health(raw_data: dict) -> dict:
    """调用 LLM 生成健康评分报告。"""

    # 格式化人可读的数值
    write_bytes = raw_data["disk"]["write_bytes"]
    write_human = f"{write_bytes / 1e9:.1f} GB" if write_bytes > 1e9 else f"{write_bytes / 1e6:.1f} MB"
    recv_mb = raw_data["network"]["bytes_recv"] / 1e6
    sent_mb = raw_data["network"]["bytes_sent"] / 1e6

    prompt = USER_PROMPT_TEMPLATE.format(
        hostname=raw_data["hostname"],
        timestamp=raw_data["timestamp"],
        **raw_data["cpu"],
        **raw_data["memory"],
        **raw_data["disk"],
        write_bytes_human=write_human,
        **raw_data["network"],
        recv_mb=recv_mb,
        sent_mb=sent_mb,
        **raw_data["security"],
        **raw_data["stability"],
        root_logins=raw_data["security"]["root_logins_24h"]
    )

    response = openai.chat.completions.create(
        model="deepseek-chat",   # 或用本地 Ollama 模型
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        temperature=0.2,
        max_tokens=1500,
        response_format={"type": "json_object"}
    )

    report = json.loads(response.choices[0].message.content)

    # 后处理：应用硬性规则
    report = apply_hard_rules(report, raw_data)

    return report

def apply_hard_rules(report: dict, raw: dict) -> dict:
    """应用硬编码规则覆盖 LLM 的判断。"""
    # 安全 critical → 总分上限 50
    if report["dimensions"]["security"]["status"] == "critical":
        report["overall_score"] = min(report["overall_score"], 50)
        if report["overall_score"] < 60:
            report["grade"] = "F"
        elif report["overall_score"] < 70:
            report["grade"] = "D"

    # CPU + 内存同时 critical → 总分上限 40
    if (report["dimensions"]["cpu"]["status"] == "critical" and
        report["dimensions"]["memory"]["status"] == "critical"):
        report["overall_score"] = min(report["overall_score"], 40)
        report["grade"] = "F"

    return report
```

### 3.3 运行示例

```bash
$ python3 collect_health.py | python3 analyze_health.py
```

**输出示例：**

```json
{
  "overall_score": 72,
  "grade": "C",
  "dimensions": {
    "cpu":     {"score": 90, "status": "healthy",  "detail": "负载正常，无瓶颈"},
    "memory":  {"score": 85, "status": "healthy",  "detail": "内存充裕，Swap 未启用"},
    "disk":    {"score": 45, "status": "warning",  "detail": "根分区使用率 87%，建议清理"},
    "network": {"score": 95, "status": "healthy",  "detail": "连接数正常，无异常"},
    "security":{"score": 10, "status": "critical", "detail": "24h 内 47 次 SSH 暴力破解尝试"},
    "stability":{"score": 80, "status": "healthy", "detail": "连续运行 15 天，无异常"}
  },
  "risk_level": "high",
  "issues": [
    {
      "severity": "critical",
      "dimension": "security",
      "description": "检测到 47 次 SSH 暴力破解尝试，源 IP 分布广泛，疑似扫描攻击",
      "suggestion": "立即部署 Fail2Ban，限制 SSH 密钥登录，禁用密码认证"
    },
    {
      "severity": "warning",
      "dimension": "disk",
      "description": "根分区使用率 87%，增长趋势约每天 1.2%",
      "suggestion": "清理 /var/log 下的旧日志，压缩旧 journal 文件"
    }
  ],
  "summary": "服务器整体运行稳定，但存在两处需关注的问题：安全维度得分为 10 分（SSH 暴力破解频繁），磁盘空间趋于紧张（87% 已用）。建议优先处理安全告警，同时安排磁盘清理。",
  "action_items": [
    "【紧急】部署 Fail2Ban 并启用 SSH 密钥认证",
    "【本周】清理旧日志释放磁盘空间，目标降至 75% 以下",
    "【观察】下周复测，确认磁盘增长速率是否持续"
  ]
}
```

---

## 第四步：调度与通知

健康评分的价值在于**定期执行**，让趋势可见。

### 4.1 定时任务

```bash
# crontab -e
# 每天凌晨 3 点执行健康检查（业务低峰期）
0 3 * * * cd /opt/vps-health && ./run_health_check.sh >> /var/log/health_check.log 2>&1

# 每周一早上执行周报汇总
0 9 * * 1 cd /opt/vps-health && ./generate_weekly_report.sh
```

### 4.2 通知推送

```python
# scripts/notify.py — 根据评分结果决定通知渠道
import smtplib
import requests
from email.mime.text import MIMEText

def send_notification(report: dict):
    score = report["overall_score"]
    summary = report["summary"]

    if score >= 80:
        # 健康：推送到 Telegram 群（每日简报）
        send_telegram(summary, channel="daily-health")
    elif score >= 60:
        # 一般：Telegram + 邮件
        send_telegram(f"⚠️ VPS 健康评分: {score}/100\n{summary}", channel="alerts")
        send_email(report, subject=f"[VPS 健康] {score}分 - 需关注")
    else:
        # 差：Telegram + 邮件 + PagerDuty
        send_telegram(f"🚨 VPS 健康评分: {score}/100 — 需要立即处理！\n{summary}",
                      channel="urgent")
        send_email(report, subject=f"🚨 [紧急] VPS 健康评分 {score}分", priority="high")
        pagerduty_trigger(report)
```

### 4.3 历史趋势存储

```python
# 每次评分结果追加到 DuckDB 用于趋势分析
import duckdb

def save_report(report: dict, raw_data: dict):
    conn = duckdb.connect("/opt/vps-health/health_history.duckdb")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS health_snapshots (
            timestamp TIMESTAMP,
            hostname VARCHAR,
            overall_score INTEGER,
            grade VARCHAR,
            risk_level VARCHAR,
            cpu_score INTEGER,
            memory_score INTEGER,
            disk_score INTEGER,
            network_score INTEGER,
            security_score INTEGER,
            stability_score INTEGER,
            raw_data JSON
        )
    """)
    conn.execute("INSERT INTO health_snapshots VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                 [
                     report.get("timestamp"),
                     raw_data["hostname"],
                     report["overall_score"],
                     report["grade"],
                     report["risk_level"],
                     report["dimensions"]["cpu"]["score"],
                     report["dimensions"]["memory"]["score"],
                     report["dimensions"]["disk"]["score"],
                     report["dimensions"]["network"]["score"],
                     report["dimensions"]["security"]["score"],
                     report["dimensions"]["stability"]["score"],
                     json.dumps(raw_data)
                 ])
    conn.close()
```

---

## 进阶：多 VPS 仪表盘

当管理多台 VPS 时，需要一个**全局健康视图**：

```
┌──────────────────────────────────────────────────────────────┐
│  VPS 健康总览          更新于 03:00  UTC                      │
├──────────┬────────┬────────┬────────┬────────┬───────────────┤
│ 主机     │ 总分   │ 等级   │ 风险   │ 安全   │ 最近问题       │
├──────────┼────────┼────────┼────────┼────────┼───────────────┤
│ web-01   │ 🟢 92  │ A      │ 低     │ 正常   │ 无             │
│ web-02   │ 🟡 74  │ C      │ 中     │ ⚠️ 弱  │ SSH 暴力破解   │
│ db-01    │ 🔴 38  │ F      │ 高     │ 正常   │ 磁盘 94% + OOM │
│ api-01   │ 🟢 88  │ B      │ 低     │ 正常   │ 无             │
│ cache-01 │ 🟡 79  │ C      │ 中     │ 正常   │ Swap 使用率偏高│
└──────────┴────────┴────────┴────────┴────────┴───────────────┘
```

查询过去 30 天的趋势：
```sql
SELECT
    hostname,
    AVG(overall_score) AS avg_score,
    MIN(overall_score) AS min_score,
    COUNT(CASE WHEN risk_level = 'critical' THEN 1 END) AS critical_count
FROM health_snapshots
WHERE timestamp > NOW() - INTERVAL '30 days'
GROUP BY hostname
ORDER BY avg_score ASC;
```

---

## 完整部署

### 依赖安装

```bash
pip install psutil openai duckdb python-dotenv
```

### 项目结构

```
/opt/vps-health/
├── config/
│   ├── dimensions.yaml        # 评分维度配置
│   └── llm_config.yaml        # LLM API 配置
├── scripts/
│   ├── collect_health.py      # 指标采集
│   ├── analyze_health.py      # LLM 分析
│   ├── notify.py              # 通知推送
│   └── dashboard.py           # 仪表盘查询
├── run_health_check.sh        # 主入口
└── health_history.duckdb      # 历史记录
```

### 主入口脚本

```bash
#!/bin/bash
# run_health_check.sh
set -e

cd /opt/vps-health

# 1. 采集指标
echo "[$(date)] 开始采集健康指标..."
python3 scripts/collect_health.py > /tmp/health_raw.json

# 2. LLM 分析
echo "[$(date)] 调用 LLM 生成健康报告..."
python3 scripts/analyze_health.py /tmp/health_raw.json > /tmp/health_report.json

# 3. 保存历史
python3 -c "
import json, sys
sys.path.insert(0, 'scripts')
from notify import save_report
with open('/tmp/health_raw.json') as f: raw = json.load(f)
with open('/tmp/health_report.json') as f: report = json.load(f)
save_report(report, raw)
"

# 4. 发送通知
python3 scripts/notify.py /tmp/health_report.json

echo "[$(date)] 健康检查完成"
```

---

## 为什么这套系统值得做？

| 传统方式 | AI 健康评分系统 |
|---------|----------------|
| 看到告警才知道有问题 | 评分趋势提前预警（连续 3 天下降则触发） |
| 靠经验判断优先级 | LLM 自动排序，告诉你先处理什么 |
| 每次排查都要重新理解系统 | 历史报告形成"服务器病历本" |
| 多 VPS 靠人脑记忆 | 仪表盘一览全局，趋势一目了然 |

**核心价值不是"多一个监控面板"，而是把散落的指标变成了可理解的诊断结论。**

---

## 延伸思考

1. **本地化部署**：使用 Ollama + llama3 替代云端 API，完全离线运行，数据不出服务器
2. **自愈联动**：评分低于 60 分时，自动触发修复脚本（如清理磁盘、重启服务）
3. **成本感知**：加入云厂商定价数据，算出"当前健康状态下的每小时成本"，引导资源优化
4. **跨服务关联**：将健康评分与 Kubernetes Pod 状态、Docker 容器健康联动，实现全栈可视

---

**下一篇预告**：《AI + VPS：用多 Agent 协作实现智能故障自愈——评分触发、根因定位、自动修复的完整闭环》

*本文配套代码：[GitHub Gist](https://gist.github.com/selfvps/health-scoring)*