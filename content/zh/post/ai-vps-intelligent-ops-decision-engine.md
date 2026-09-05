---
title: "AI + VPS：智能运维决策引擎——用本地大模型构建从数据到行动的闭环"
description: "传统运维依赖人工分析告警、排查日志、制定方案。本文教你在 VPS 上部署基于本地大模型的智能运维决策引擎，自动关联多源数据、生成优先级行动清单、追踪修复效果，让运维从'救火'走向'自动驾驶'"
date: 2026-09-05T20:00:00+08:00
lastmod: 2026-09-05T20:00:00+08:00
slug: "ai-vps-intelligent-ops-decision-engine"
image: /images/posts/ai-vps-intelligent-ops-decision-engine/featured.png
tags: ["AI", "VPS", "运维决策", "大模型", "自动化", "Ollama", "Llama", "Qwen", "Prometheus", "Grafana"]
categories: ["AI 运维"]
aliases: [/zh/post/ai-vps-intelligent-ops-decision-engine/]
---

## 引言

你管理着几台 VPS，跑着网站、API 和数据库。每天面对的是：

- Prometheus 告警群发，不知哪个是根因；
- 磁盘空间告警，但不知道是日志暴涨还是备份堆积；
- CPU 飙升告警，但日志里找不到对应的异常请求；
- 月底账单来了，才发现某台 VPS 长期低负载却未降配。

**核心痛点是：数据分散、分析耗时、决策依赖个人经验。**

传统运维的工作流是：告警 → 人工查看 → 手动排查 → 制定方案 → 执行修复 → 验证效果。整个过程依赖运维人员的经验和时间，且难以规模化。

**智能运维决策引擎**解决的就是这个问题：用一个本地部署的大语言模型（LLM）作为"大脑"，自动收集多源运维数据，关联分析，生成优先级行动清单，并追踪执行效果。你的 VPS 不再只是被动响应告警，而是主动告诉你"现在该做什么、为什么、怎么做"。

本文将带你从零搭建这套系统，包括：

1. **数据采集层**：从 Prometheus、日志、备份、成本等多源聚合
2. **AI 分析层**：本地 Ollama + Qwen/Llama 模型进行关联推理
3. **决策输出层**：生成优先级行动清单 + 一键执行脚本
4. **反馈闭环**：记录执行效果，持续优化推荐质量

## 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                    智能运维决策引擎                          │
├─────────────┬─────────────┬─────────────┬─────────────────┤
│  数据采集    │  AI 分析    │  决策输出    │   反馈学习       │
│  Collector  │  Engine     │  Output     │   Feedback      │
├─────────────┼─────────────┼─────────────┼─────────────────┤
│ Prometheus  │             │ 优先级清单  │ 执行效果记录     │
│ 告警 + 指标 │  → LLM API  │  行动建议   │  人工确认反馈    │
│             │  (Qwen/     │  一键脚本   │  效果统计        │
│ 系统日志    │   Llama)    │  根因分析   │  模型微调        │
│             │             │  趋势预测   │                 │
│ 备份状态    │             │             │                 │
│ 成本数据    │             │             │                 │
└─────────────┴─────────────┴─────────────┴─────────────────┘
         ↓                ↓                ↓                ↓
     docker-compose    Ollama server   Telegram/邮件    SQLite 记录库
```

## 第一步：部署 Ollama 本地大模型

决策引擎的核心是本地 LLM，确保数据不出 VPS。我们使用 Ollama 运行 Qwen2.5-7B 或 Llama-3.2-3B。

```bash
# 安装 Ollama
curl -fsSL https://ollama.com/install.sh | sh

# 拉取 Qwen2.5-7B（推荐，中文理解能力强）
ollama pull qwen2.5:7b

# 或者更轻量的 Llama-3.2-3B（资源紧张时）
ollama pull llama3.2:3b

# 验证运行
ollama list
ollama run qwen2.5:7b "你好，请简单介绍一下你自己"
```

对于 2C2G 的小 VPS，推荐使用 `llama3.2:3b`；4C8G 以上建议使用 `qwen2.5:7b`。

## 第二步：构建数据采集器

### 2.1 采集 Prometheus 指标与告警

```python
# collector/prometheus_collector.py
import requests
from datetime import datetime, timedelta
import json

class PrometheusCollector:
    def __init__(self, url="http://localhost:9090"):
        self.url = url.rstrip("/")
    
    def get_firing_alerts(self):
        """获取当前触发中的告警"""
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
        """查询最近 N 分钟的指标"""
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
        """计算指标趋势"""
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
        """采集所有 Prometheus 数据"""
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

### 2.2 采集系统日志

```python
# collector/log_collector.py
import subprocess
from datetime import datetime, timedelta
import re

class LogCollector:
    def __init__(self):
        self.errors = []
    
    def collect_recent_errors(self, hours=6):
        """采集最近 N 小时的错误日志"""
        since = (datetime.now() - timedelta(hours=hours)).strftime("%b %d %H:%M")
        
        # 采集 journalctl 错误
        try:
            result = subprocess.run(
                ["journalctl", "--since", since, "-p", "err", "--no-pager", "-n", "50"],
                capture_output=True, text=True, timeout=30
            )
            errors = result.stdout.strip().split("\n")
        except Exception:
            errors = []
        
        # 采集 syslog 错误
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
        """采集内核消息中的异常"""
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

### 2.3 采集备份与成本数据

```python
# collector/backup_collector.py
import subprocess
import json
from datetime import datetime

class BackupCollector:
    def check_backup_status(self):
        """检查关键备份状态"""
        checks = []
        
        # 检查最近的备份文件
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
        
        # 检查 Docker 镜像数量
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
        """估算当前资源使用成本"""
        try:
            # CPU 平均使用率
            result = subprocess.run(
                ["awk", "{print $2/$1*100}", "/proc/stat"],
                capture_output=True, text=True
            )
            cpu_usage = float(result.stdout.strip().split()[0]) if result.stdout.strip() else 0
            
            # 内存使用率
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

## 第三步：构建 AI 分析引擎

这是整个系统的核心。我们将采集到的数据拼接成上下文，发送给本地 LLM，让它分析根因、生成行动建议。

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
        """将多源数据构建成 AI 可读的上下文"""
        context_parts = []
        
        # 告警信息
        alerts = collected_data.get("alerts", [])
        if alerts:
            context_parts.append("【当前告警】")
            for a in alerts:
                context_parts.append(f"- [{a['severity']}] {a['name']}: {a['summary']} (持续 {a.get('starts_at', '')})")
        else:
            context_parts.append("【当前告警】无")
        
        # 资源使用情况
        metrics = collected_data.get("metrics", {})
        context_parts.append("【资源使用】")
        for metric in metrics.get("cpu", []):
            context_parts.append(f"- CPU {metric['metric'].get('instance', 'local')}: {metric['latest_value']:.1f}% (趋势: {metric['trend']})")
        for metric in metrics.get("memory", []):
            context_parts.append(f"- 内存 {metric['metric'].get('instance', 'local')}: {100 - metric['latest_value']:.1f}% (趋势: {metric['trend']})")
        for metric in metrics.get("disk", []):
            context_parts.append(f"- 磁盘 {metric['metric'].get('mountpoint', 'unknown')}: {metric['latest_value']:.1f}% (趋势: {metric['trend']})")
        
        # 日志错误
        logs = collected_data.get("logs", {})
        if logs.get("total_errors", 0) > 0:
            context_parts.append(f"【日志异常】最近 6 小时共 {logs['total_errors']} 条错误")
            for err in logs.get("journalctl_errors", [])[:5]:
                context_parts.append(f"  - {err[:120]}")
        
        # 备份状态
        backup = collected_data.get("backup", {})
        for check in backup.get("checks", []):
            context_parts.append(f"【{check['type']}】状态: {check['status']}")
        
        # 成本建议
        cost = collected_data.get("cost", {})
        if "recommendation" in cost:
            context_parts.append(f"【成本评估】{cost['recommendation']} (CPU: {cost.get('cpu_usage_percent', 'N/A')}%, 内存: {cost.get('memory_usage_percent', 'N/A')}%)")
        
        return "\n".join(context_parts)
    
    def generate_decision(self, context):
        """调用 LLM 生成决策"""
        prompt = f"""你是专业的运维工程师助手。请根据以下 VPS 运行状态数据，生成运维决策建议。

## VPS 运行状态
{context}

## 输出要求
请按以下 JSON 格式输出，不要添加任何其他内容：

{{
  "priority": "critical|high|medium|low|info",
  "root_cause_summary": "一句话总结最紧急的问题及可能原因",
  "action_items": [
    {{
      "priority": 1,
      "action": "具体操作步骤（命令行或命令）",
      "reason": "为什么做这个操作",
      "estimated_impact": "预期效果",
      "risk": "低|中|高"
    }}
  ],
  "trend_forecast": "基于当前趋势，预测未来 24 小时内可能发生的问题",
  "auto_execute_commands": ["可安全自动执行的命令列表"],
  "requires_human_review": ["需要人工确认的操作"]
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
            return {"error": "LLM 请求超时，请检查 Ollama 服务"}
        except Exception as e:
            return {"error": f"LLM 调用失败: {str(e)}"}
    
    def _parse_llm_output(self, text):
        """解析 LLM 返回的 JSON"""
        try:
            # 尝试直接解析
            return json.loads(text)
        except json.JSONDecodeError:
            # 尝试提取 JSON 块
            import re
            match = re.search(r'\{[\s\S]*\}', text)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
            return {"error": "无法解析 LLM 输出", "raw": text[:500]}
    
    def run_decision_cycle(self, collected_data):
        """执行一次完整的决策周期"""
        context = self.build_context(collected_data)
        decision = self.generate_decision(context)
        
        # 记录决策历史
        self._save_history(collected_data, context, decision)
        
        return {
            "timestamp": datetime.now().isoformat(),
            "context_summary": context[:500],
            "decision": decision,
        }
    
    def _save_history(self, input_data, context, decision):
        """保存决策历史记录（简化版，实际可用 SQLite）"""
        record = {
            "timestamp": datetime.now().isoformat(),
            "input_summary": {
                "alert_count": len(input_data.get("alerts", [])),
                "error_count": input_data.get("logs", {}).get("total_errors", 0),
            },
            "decision": decision,
        }
        # 实际生产中应写入 SQLite 或 TimescaleDB
        # 这里简化为打印
        print(f"[Decision Record] {record['timestamp']}")
        print(f"  Alerts: {record['input_summary']['alert_count']}, Errors: {record['input_summary']['error_count']}")
        priority = decision.get("priority", "unknown")
        print(f"  Priority: {priority}")
        for item in decision.get("action_items", []):
            print(f"  Action #{item.get('priority', '?')}: {item.get('action', '')[:80]}")
```

## 第四步：编排与调度

使用 Python 脚本整合所有组件，通过 cron 或 systemd timer 定期执行。

```python
# main.py
#!/usr/bin/env python3
"""智能运维决策引擎 - 主入口"""

import json
import sys
from pathlib import Path
from datetime import datetime

# 添加 collector 和 engine 到路径
sys.path.insert(0, str(Path(__file__).parent))

from collector.prometheus_collector import PrometheusCollector
from collector.log_collector import LogCollector
from collector.backup_collector import BackupCollector, CostCollector
from engine.decision_engine import DecisionEngine


def collect_all_data():
    """采集所有运维数据"""
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
    
    # 日志
    try:
        log_col = LogCollector()
        data["logs"] = log_col.collect_recent_errors()
        data["dmesg"] = log_col.collect_dmesg()
    except Exception as e:
        data["logs"] = {"total_errors": 0, "journalctl_errors": [], "syslog_errors": []}
    
    # 备份 & 成本
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
    """格式化输出决策结果"""
    output = []
    output.append(f"🔍 智能运维决策报告 — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    output.append("=" * 50)
    
    priority = decision.get("decision", {}).get("priority", "unknown")
    emoji_map = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢", "info": "ℹ️"}
    output.append(f"优先级: {emoji_map.get(priority, '⚪')} {priority.upper()}")
    
    root_cause = decision.get("decision", {}).get("root_cause_summary", "")
    if root_cause:
        output.append(f"\n📋 根因摘要: {root_cause}")
    
    action_items = decision.get("decision", {}).get("action_items", [])
    if action_items:
        output.append(f"\n📝 建议行动 ({len(action_items)} 项):")
        for i, item in enumerate(action_items, 1):
            output.append(f"  {i}. [{item.get('risk', '?')}] {item.get('action', '')}")
            output.append(f"     原因: {item.get('reason', '')}")
            output.append(f"     预期: {item.get('estimated_impact', '')}")
    
    auto_cmds = decision.get("decision", {}).get("auto_execute_commands", [])
    if auto_cmds:
        output.append(f"\n🤖 可自动执行:")
        for cmd in auto_cmds[:5]:
            output.append(f"  $ {cmd}")
    
    forecast = decision.get("decision", {}).get("trend_forecast", "")
    if forecast:
        output.append(f"\n📈 趋势预测: {forecast}")
    
    return "\n".join(output)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "run"
    
    if mode == "collect":
        data = collect_all_data()
        print(json.dumps(data, indent=2, ensure_ascii=False))
    
    elif mode == "run":
        print("正在采集运维数据...")
        data = collect_all_data()
        
        print("正在调用 AI 分析...")
        engine = DecisionEngine()
        result = engine.run_decision_cycle(data)
        
        # 输出格式化结果
        print(format_output(result))
        
        # 保存完整结果
        output_path = Path(f"/tmp/ops_decision_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        with open(output_path, "w") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"\n完整结果已保存至: {output_path}")
    
    elif mode == "history":
        # 显示历史决策记录
        history_dir = Path("/var/lib/ops-decision")
        if history_dir.exists():
            files = sorted(history_dir.glob("*.json"), reverse=True)[:5]
            for f in files:
                with open(f) as fp:
                    rec = json.load(fp)
                print(f"{f.name}: priority={rec.get('decision', {}).get('priority', '?')}")
        else:
            print("暂无历史记录")


if __name__ == "__main__":
    main()
```

## 第五步：Docker Compose 完整部署

将所有组件容器化，一键部署。

```yaml
# docker-compose.yml
version: "3.8"

services:
  # Ollama 大模型服务
  ollama:
    image: ollama/ollama:latest
    container_name: ollama
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama
    restart: unless-stopped

  # 智能运维决策引擎
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
      - COLLECTION_INTERVAL=300  # 5分钟采集一次
      - NOTIFICATION_CHANNEL=telegram  # telegram/email/webhook

  # Prometheus（如已有可省略）
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

## 第六步：配置定时任务

### 使用 systemd timer（推荐）

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

### 或使用 cron

```cron
# 每 5 分钟执行一次决策分析
*/5 * * * * cd /opt/ops-decision && /usr/bin/python3 main.py run >> /var/log/ops-decision.log 2>&1

# 每天凌晨 2 点生成日报
0 2 * * * cd /opt/ops-decision && /usr/bin/python3 main.py run --daily-report >> /var/log/ops-decision-daily.log 2>&1
```

## 第七步：集成通知渠道

### Telegram 推送

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
        """发送决策报告到 Telegram"""
        # Telegram 消息长度限制 4096 字符
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
        """发送带快捷操作按钮的决策报告"""
        action_items = decision.get("decision", {}).get("action_items", [])
        
        # 构建内联按钮
        buttons = []
        for item in action_items[:3]:
            buttons.append([{"text": f"✅ {item.get('priority', '?')}: {item.get('action', '')[:20]}...", 
                            "callback_data": f"execute:{item.get('action', '')}"}])
        
        return {
            "chat_id": self.chat_id,
            "text": f"🔍 运维决策建议\n\n{decision.get('decision', {}).get('root_cause_summary', '')}",
            "reply_markup": json.dumps({"inline_keyboard": buttons}),
        }
```

### 效果追踪与反馈闭环

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
                feedback_type TEXT,  -- execute/reject/modify
                feedback_text TEXT,
                created_at TEXT
            )
        """)
        conn.commit()
        conn.close()
    
    def record_execution(self, decision_id, action_index, executed, effectiveness):
        """记录执行效果和人工反馈"""
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO feedback_logs (decision_id, action_index, feedback_type, feedback_text, created_at) VALUES (?, ?, ?, ?, ?)",
            (decision_id, action_index, executed, effectiveness, datetime.now().isoformat())
        )
        conn.commit()
        conn.close()
    
    def get_effectiveness_stats(self, days=7):
        """统计最近 N 天的决策效果"""
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

## 实际运行示例

```bash
$ cd /opt/ops-decision && python3 main.py run
正在采集运维数据...
正在调用 AI 分析...
🔍 智能运维决策报告 — 2026-09-05 20:30
==================================================
优先级: 🟠 HIGH

📋 根因摘要: 磁盘 /var/log 使用率 92% 且持续上升，疑似 syslog 日志未轮转导致

📝 建议行动 (3 项):
  1. [低] journalctl --vacuum-time=3d
     原因: 清理 3 天前的 journal 日志，释放磁盘空间
     预期: 预计释放 2-5GB 空间
  2. [低] systemctl restart rsyslog
     原因: 确保日志轮转配置生效
     预期: 日志按配置大小分割，防止单文件过大
  3. [中] 检查是否有进程持续写入大量日志
     原因: 磁盘使用率快速上升可能有应用异常
     预期: 定位日志激增的根因应用

🤖 可自动执行:
  $ journalctl --vacuum-time=3d
  $ systemctl restart rsyslog

📈 趋势预测: 如不处理，预计 12 小时内 /var/log 将达到 95%，触发严重告警
```

## 进阶：多 VPS 集中决策

当管理多台 VPS 时，可以搭建集中式决策引擎：

```python
# multi_vps_manager.py
import json
from concurrent.futures import ThreadPoolExecutor

class MultiVpsDecisionManager:
    def __init__(self, vps_list):
        self.vps_list = vps_list  # [{"name": "prod-web-01", "ip": "1.2.3.4"}, ...]
    
    def collect_all(self):
        """并发采集所有 VPS 数据"""
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
        """跨 VPS 关联分析，生成全局决策"""
        # 这里可以检测跨 VPS 的关联问题
        # 例如：多台 VPS 同时出现 DNS 解析失败 → 指向同一个 DNS 服务器问题
        context = self._build_global_context(all_data)
        # 调用 LLM 进行全局分析
        return self.engine.generate_decision(context)
```

## 总结

通过本文，你学会了：

1. **本地部署 Ollama + Qwen/Llama**，确保数据隐私
2. **构建多源数据采集器**，聚合 Prometheus、日志、备份、成本数据
3. **设计 AI 分析引擎**，将运维数据转化为结构化决策输出
4. **实现反馈闭环**，记录执行效果持续优化
5. **集成通知渠道**，通过 Telegram 等推送决策建议

这套系统的核心价值在于：**把运维人员从"看告警 → 查日志 → 想方案"的重复劳动中解放出来，让 AI 完成数据分析，人只需要做最终决策**。

随着使用时间的增长，系统会通过学习你的操作习惯和反馈，越来越精准地给出符合你实际需求的建议。从"救火队员"到"自动驾驶"，这就是 AI + VPS 运维的未来。
