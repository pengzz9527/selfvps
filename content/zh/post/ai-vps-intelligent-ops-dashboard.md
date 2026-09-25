---
title: "AI + VPS：智能运维大屏——多源数据融合的VPS可视化仪表盘"
description: "Prometheus 管指标、Loki 管日志、Alertmanager 管告警，数据分散在多个系统里？本文带你用 AI 引擎聚合多维数据，打造一键透视 VPS 健康状态的智能运维大屏。"
date: 2026-09-25T21:00:00+08:00
lastmod: 2026-09-25T21:00:00+08:00
slug: "ai-vps-intelligent-ops-dashboard"
image: /images/posts/ai-vps-intelligent-ops-dashboard/featured.png
tags: ["AI", "VPS", "运维大屏", "可视化", "Prometheus", "Grafana", "Loki", "LLM", "AIOps", "数据融合"]
categories: ["AI + VPS"]
aliases: [/zh/post/ai-vps-intelligent-ops-dashboard/]
draft: false
---

## 引言

你搭建了一套完整的 VPS 监控体系：Prometheus 采集指标，Grafana 展示面板，Loki 收集日志，Alertmanager 发送告警。看起来一切井井有条——

但当你需要快速了解"现在 VPS 状态如何"时，却不得不打开三四五个页面，切换不同工具，人工拼凑信息。更糟糕的是，当真正出现故障时，你需要同时查看 CPU 曲线、排查相关日志、对比历史告警，才能还原事件全貌。

**问题不在于缺少监控数据，而在于数据之间缺乏关联。** 指标告诉你"发生了什么"，日志告诉你"为什么会发生"，告警告诉你"有多严重"，但没有任何一个工具帮你把这三者串联起来，给出一个统一的视图和结论。

本文将介绍如何用 AI 引擎打通这些孤岛，构建一个**智能运维大屏**——不仅展示数据，更理解数据，自动提炼关键信息，让你在 30 秒内掌握整台 VPS 的健康状况。

---

## 为什么需要智能运维大屏？

### 传统监控的三大痛点

| 痛点 | 现象 | 后果 |
|------|------|------|
| **数据孤岛** | 指标在 Prometheus，日志在 Loki，配置在文件，告警在 Telegram | 排查故障需要切换多个工具，信息碎片化 |
| **信息过载** | 几十张 Grafana 面板，数百条告警规则 | 真正重要的信号被淹没在噪声中 |
| **缺乏上下文** | 知道 CPU 高了，但不知道是哪个进程、哪次部署导致的 | 排查依赖个人经验，无法快速定位根因 |

### 智能大屏的核心价值

智能运维大屏不是另一个可视化工具，而是一个**数据融合 + AI 理解 + 智能呈现**的综合系统：

- **一键透视**：一个页面看完所有关键信息，无需切换工具
- **AI 提炼**：自动从海量数据中提炼出"今天最重要的一件事是什么"
- **上下文关联**：将指标异常、相关日志、历史告警自动关联展示
- **预测预警**：基于趋势分析，提前告知"接下来可能会发生什么"

---

## 系统架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         AI 智能运维大屏                                   │
│                                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                  │
│  │  数据采集层    │  │  AI 分析引擎  │  │  智能呈现层   │                  │
│  │              │  │              │  │              │                  │
│  │ • Prometheus  │  │ • 异常检测    │  │ • 健康评分    │                  │
│  │ • Loki       │  │ • 趋势预测    │  │ • 关键事件    │                  │
│  │ • 系统命令    │  │ • 根因关联    │  │ • AI 摘要     │                  │
│  │ • API 状态    │  │ • 知识检索    │  │ • 一键诊断    │                  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘                  │
│         │                 │                 │                           │
│         └─────────────────┼─────────────────┘                           │
│                           ▼                                             │
│  ┌──────────────────────────────────────────────────────────────┐       │
│  │                    本地 Ollama (Qwen2.5 / Llama)              │       │
│  │              负责语义理解、异常解读、报告生成                    │       │
│  └──────────────────────────────────────────────────────────────┘       │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────┐       │
│  │                   推送通道（可选）                             │       │
│  │         Telegram / 飞书 / 邮件 / Webhook                       │       │
│  └──────────────────────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────────────────────┘
```

### 核心组件说明

| 组件 | 职责 | 技术选型 |
|------|------|----------|
| **数据采集器** | 从各数据源拉取原始信息 | Prometheus API, Loki API, shell commands |
| **AI 分析引擎** | 理解数据、发现异常、关联上下文 | Ollama + Qwen2.5 |
| **智能呈现层** | 将分析结果转化为可读视图 | Python + HTML/Markdown |
| **推送通道** | 将大屏内容推送到终端 | Telegram Bot, Feishu Bot |

---

## 第一步：构建统一数据聚合器

### 数据采集脚本

我们编写一个 Python 聚合脚本，从多个数据源拉取数据并统一格式：

```python
#!/usr/bin/env python3
"""
VPS 智能运维大屏 - 数据采集器
聚合 Prometheus 指标、Loki 日志、系统状态、服务健康度
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
        """采集系统级指标"""
        metrics = {}
        
        # CPU 负载
        try:
            with open('/proc/loadavg') as f:
                load = f.read().split()
            metrics['load_1m'] = float(load[0])
            metrics['load_5m'] = float(load[1])
            metrics['load_15m'] = float(load[2])
        except:
            pass
        
        # 内存使用
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
        
        # 磁盘使用
        try:
            result = subprocess.run(['df', '-h', '/'], capture_output=True, text=True)
            lines = result.stdout.strip().split('\n')
            if len(lines) > 1:
                parts = lines[1].split()
                metrics['disk_used_percent'] = parts[4].replace('%', '')
        except:
            pass
        
        # 关键进程状态
        for service in ['nginx', 'docker', 'sshd', 'postgresql', 'redis']:
            try:
                result = subprocess.run(['systemctl', 'is-active', service], 
                                       capture_output=True, text=True)
                metrics[f'{service}_status'] = result.stdout.strip()
            except:
                pass
        
        return metrics
    
    def collect_prometheus_alerts(self) -> List[Dict]:
        """采集当前激活告警"""
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
        """从 Loki 采集最近的关键日志"""
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
            return lines[-20:]  # 最近20条
        except Exception:
            return []
    
    def collect_service_health(self) -> Dict[str, Dict]:
        """采集各服务健康检查"""
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
        """聚合所有数据源"""
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

## 第二步：AI 分析引擎

数据采集完成后，将结构化数据发送给本地 LLM 进行分析：

```python
#!/usr/bin/env python3
"""
VPS 智能运维大屏 - AI 分析引擎
使用本地 Ollama + Qwen2.5 分析聚合数据
"""

import json
import requests

ANALYSIS_PROMPT = """你是一位经验丰富的运维工程师，正在分析一台 VPS 的运行状态。
请根据以下数据，给出简洁专业的运维分析。

【分析要求】
1. 健康评分（0-100）：综合评估当前状态
2. 关键发现：列出最重要的 2-3 个问题或异常
3. 趋势判断：基于当前数据预测接下来可能发生什么
4. 行动建议：给出具体可执行的修复或优化建议
5. 今日一句话：用一句话概括今天最需要关注的事项

【输出格式】严格使用 JSON：
{{
  "health_score": 85,
  "key_findings": ["发现1", "发现2"],
  "trend": "趋势描述",
  "actions": ["建议1", "建议2"],
  "one_liner": "一句话总结"
}}

【输入数据】
{data}
"""

def analyze_with_ollama(system_data: dict, model: str = "qwen2.5:7b") -> dict:
    """调用本地 Ollama 进行智能分析"""
    prompt = ANALYSIS_PROMPT.format(data=json.dumps(system_data, indent=2, ensure_ascii=False))
    
    try:
        resp = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=60
        )
        result = resp.json()
        # 解析 LLM 返回的 JSON
        output = result.get('response', '')
        # 提取 JSON 部分
        start = output.find('{')
        end = output.rfind('}') + 1
        if start >= 0 and end > start:
            return json.loads(output[start:end])
        return {"error": "Failed to parse LLM response", "raw": output}
    except Exception as e:
        return {"error": str(e)}


def generate_dashboard_summary(analysis: dict, raw_data: dict) -> str:
    """生成可读的大屏摘要报告"""
    score = analysis.get('health_score', '?')
    one_liner = analysis.get('one_liner', '')
    findings = analysis.get('key_findings', [])
    actions = analysis.get('actions', [])
    trend = analysis.get('trend', '')
    
    # 健康状态 emoji
    if score >= 80:
        status_emoji = "🟢"
    elif score >= 60:
        status_emoji = "🟡"
    else:
        status_emoji = "🔴"
    
    # 构建 Markdown 报告
    report = f"""# {status_emoji} VPS 智能运维大屏

**生成时间**: {raw_data.get('timestamp', 'N/A')}  
**健康评分**: {score}/100  
**一句话总结**: {one_liner}

---

## 📊 关键发现

"""
    for i, finding in enumerate(findings, 1):
        report += f"{i}. {finding}\n"
    
    report += "\n## 📈 趋势预测\n\n"
    report += f">{trend}\n"
    
    report += "\n## 🔧 行动建议\n\n"
    for i, action in enumerate(actions, 1):
        report += f"{i}. {action}\n"
    
    # 附加原始数据摘要
    report += "\n---\n\n## 📋 系统状态速览\n\n"
    system = raw_data.get('system', {})
    report += f"- **CPU 负载(1m)**: {system.get('load_1m', 'N/A')}\n"
    report += f"- **内存使用**: {system.get('memory_used_percent', 'N/A')}%\n"
    report += f"- **磁盘使用**: {system.get('disk_used_percent', 'N/A')}%\n"
    
    alerts = raw_data.get('alerts', [])
    if alerts:
        report += f"\n## 🚨 活跃告警 ({len(alerts)} 条)\n\n"
        for alert in alerts[:5]:
            severity = alert.get('severity', 'unknown')
            icon = "🔴" if severity == 'critical' else "🟠" if severity == 'warning' else "⚪"
            report += f"- {icon} **{alert.get('name', 'Unknown')}**: {alert.get('summary', '')}\n"
    else:
        report += "\n✅ 当前无活跃告警\n"
    
    return report


if __name__ == '__main__':
    # 模拟数据
    mock_data = {
        "timestamp": "2026-09-25T21:00:00",
        "system": {
            "load_1m": 1.2,
            "memory_used_percent": 72.5,
            "disk_used_percent": "68",
            "nginx_status": "active",
            "docker_status": "active"
        },
        "alerts": [],
        "recent_logs": ["2026-09-25T20:58:00 nginx: worker process started"],
        "services": {"web": {"status": "up", "latency_ms": 12.3}}
    }
    
    analysis = analyze_with_ollama(mock_data)
    summary = generate_dashboard_summary(analysis, mock_data)
    print(summary)
```

---

## 第三步：大屏渲染与推送

### 大屏 HTML 模板

将 AI 分析结果渲染为美观的 Web 大屏：

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <title>VPS 智能运维大屏</title>
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
    .alert-critical { color: #ff5252; } .alert-warning { color: #ffb74d; }
    .status-up { color: #69f0ae; } .status-down { color: #ff5252; }
    .one-liner { font-size: 20px; font-weight: 300; color: #fff; padding: 16px; background: linear-gradient(135deg, #1a1a2e, #16213e); border-radius: 8px; border-left: 4px solid var(--accent); }
  </style>
</head>
<body>
  <div class="dashboard">
    <div class="header">
      <div>
        <h1 style="margin:0;font-size:24px;">🖥️ VPS 智能运维大屏</h1>
        <span style="color:#888;font-size:13px;" id="timestamp">加载中...</span>
      </div>
      <div style="text-align:right;">
        <div class="health-label">健康评分</div>
        <div class="health-score" id="healthScore">--</div>
      </div>
    </div>
    
    <div class="one-liner" id="oneLiner">正在分析 VPS 状态...</div>
    
    <div class="grid" style="margin-top:20px;">
      <!-- 系统指标 -->
      <div class="card">
        <div class="card-title">📊 系统资源</div>
        <div class="metric"><span>CPU 负载 (1m)</span><span id="cpuLoad">--</span></div>
        <div class="metric"><span>内存使用</span><span id="memUsage">--</span></div>
        <div class="metric"><span>磁盘使用</span><span id="diskUsage">--</span></div>
      </div>
      
      <!-- 服务状态 -->
      <div class="card">
        <div class="card-title">🔌 服务状态</div>
        <div id="serviceStatus">--</div>
      </div>
      
      <!-- 活跃告警 -->
      <div class="card">
        <div class="card-title">🚨 活跃告警</div>
        <div id="activeAlerts">暂无告警</div>
      </div>
      
      <!-- AI 建议 -->
      <div class="card">
        <div class="card-title">💡 AI 行动建议</div>
        <div id="aiActions">--</div>
      </div>
    </div>
  </div>
  
  <script>
    // 自动刷新：每60秒重新加载数据
    async function refreshDashboard() {
      try {
        const resp = await fetch('/api/dashboard');
        const data = await resp.json();
        document.getElementById('healthScore').textContent = data.health_score ?? '--';
        document.getElementById('oneLiner').textContent = data.one_liner ?? '';
        document.getElementById('cpuLoad').textContent = (data.system?.load_1m ?? '--') + ' load';
        document.getElementById('memUsage').textContent = (data.system?.memory_used_percent ?? '--') + '%';
        document.getElementById('diskUsage').textContent = (data.system?.disk_used_percent ?? '--') + '%';
        // ... 渲染其他字段
      } catch(e) { console.error('Refresh failed', e); }
    }
    refreshDashboard();
    setInterval(refreshDashboard, 60000);
  </script>
</body>
</html>
```

### 定时执行与推送

将大屏生成接入 cron，定期推送至 Telegram：

```bash
# 每天 8:00 和 20:00 生成并推送大屏
0 8,20 * * * cd /opt/vps-dashboard && python3 collect_and_analyze.py | python3 send_telegram.py
```

Telegram 推送脚本：

```python
#!/usr/bin/env python3
"""将大屏摘要推送至 Telegram"""
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
    send_to_telegram(f"🖥️ *VPS 智能运维大屏*\n\n{report[:3000]}")
```

---

## 实际运行效果

运行 `python3 collect_and_analyze.py` 后，AI 大屏输出示例：

```
# 🟢 VPS 智能运维大屏

**生成时间**: 2026-09-25T21:00:00
**健康评分**: 82/100
**一句话总结**: 磁盘空间增长较快，建议本周内清理旧日志或扩容。

---

## 📊 关键发现

1. 根分区磁盘使用率达 78%，且近7天日均增长 1.2%，按此速度 20 天后将达到 90%
2. PostgreSQL 连接数接近上限（142/150），高并发时段可能出现连接拒绝
3. 内存缓存占比正常，无 OOM 风险

## 📈 趋势预测

磁盘 I/O 等待时间在过去 24 小时内呈上升趋势，结合日志增长速率，预计下周中期需要干预。

## 🔧 行动建议

1. 执行 `journalctl --vacuum-time=7d` 清理 7 天前的系统日志
2. 调整 PostgreSQL max_connections 至 200，或引入连接池（PgBouncer）
3. 为 Loki 配置日志轮转策略，单文件不超过 500MB
```

---

## 进阶：大屏 API 服务

为了让大屏可以浏览器实时访问，可以搭建一个简单的 Flask API 服务：

```python
from flask import Flask, render_template, jsonify
import subprocess, json

app = Flask(__name__)

@app.route('/')
def dashboard():
    return render_template('dashboard.html')

@app.route('/api/dashboard')
def api_dashboard():
    # 执行数据采集 + AI 分析
    result = subprocess.run(
        ['python3', '/opt/vps-dashboard/collect_and_analyze.py'],
        capture_output=True, text=True, timeout=120
    )
    return jsonify(json.loads(result.stdout))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8888)
```

访问 `http://your-vps:8888` 即可看到实时大屏，每 60 秒自动刷新。

---

## 总结

智能运维大屏的核心价值在于**把分散的数据变成连贯的故事**：

| 传统方式 | 智能大屏 |
|---------|---------|
| 逐个查看 Prometheus / Loki / 告警 | 一个页面聚合所有信息 |
| 人工判断"哪个指标异常" | AI 自动识别关键异常并评分 |
| 看到数字不知道意味着什么 | AI 生成"一句话总结"和具体建议 |
| 故障排查靠个人经验 | AI 关联指标 + 日志 + 历史案例 |

通过这套方案，你只需要：
1. 部署 Prometheus + Loki + Ollama（本地 LLM）
2. 运行数据采集脚本
3. 每日两次接收 AI 分析的大屏报告

就能实现**从"被动救火"到"主动感知"**的转变——在你意识到问题之前，AI 已经告诉你"今天需要注意什么"。
