---
title: "VPS 智能告警关联与根因分析：本地 LLM 让告警风暴不再混乱"
description: "告别告警风暴中的盲目排查，用本地 LLM（Ollama + Qwen2.5）自动关联多条告警、提取关键信息、推断根因，并生成可执行的修复建议，让运维从被动响应转向主动治理。"
date: 2026-09-22T20:00:00+08:00
lastmod: 2026-09-22T20:00:00+08:00
slug: "vps-llm-alert-correlation-rca"
image: /images/posts/vps-llm-alert-correlation-rca/featured.png
tags: ["AI 运维", "VPS", "告警关联", "根因分析", "Ollama", "Qwen2.5", "Prometheus", "Alertmanager", "LLM", "自动化"]
categories: ["AI 运维"]
aliases: [/zh/post/vps-llm-alert-correlation-rca/]
---

## 告警风暴的困境

你部署了 Prometheus + Alertmanager 监控 VPS，配置了 CPU、内存、磁盘、网络等几十条告警规则。正常情况下，一切运行平稳。但某天深夜，手机开始疯狂震动：

```
[CRITICAL] CPU usage > 95% on web-server-01
[CRITICAL] Memory usage > 90% on web-server-01
[WARNING]  Disk I/O latency high on web-server-01
[CRITICAL] Nginx 502 errors spiking
[WARNING]  MySQL slow queries increasing
[CRITICAL] Docker container 'api-worker' OOM killed
```

六条告警几乎同时触发，你该先处理哪个？**哪条是根因，哪些是连锁反应？** 在传统的告警体系里，这些告警是平行的、孤立的——没有关联，没有上下文，没有优先级。运维人员只能在告警洪流中逐个排查，耗费大量时间，而服务已经在雪崩中。

这就是**告警风暴（Alert Storm）**问题。当基础设施复杂度上升，告警数量呈指数增长，人工关联分析的成本远超其价值。

## 为什么传统方案不够用

### 1. 告警规则无法理解因果关系

Prometheus 告警规则基于阈值判断：`cpu_usage > 95%` 触发告警。但它不知道"CPU 高是因为某个进程泄漏"还是"因为下游服务响应慢导致请求堆积"。每条告警都是独立的布尔表达式，没有跨指标的理解能力。

### 2. 告警关联依赖人工经验

高级运维会手动编写关联逻辑：如果 CPU 告警和内存告警同时出现，先查进程；如果磁盘告警和 IO 延迟告警同时出现，先查写入量。但这种规则极其脆弱——新场景来了就要加新规则，规则之间还可能冲突。

### 3. 夜间和节假日响应延迟

即使有 On-Call 轮值，告警也需要人工查看、理解、决策。深夜三点收到 20 条告警，谁能保证第一时间做出正确判断？

## 本地 LLM 告警关联架构

### 核心思路

用本地部署的 LLM（如 Ollama + Qwen2.5）作为**告警语义理解引擎**，自动完成以下任务：

1. **告警聚合**：识别时间窗口内触发的相关告警
2. **根因推断**：基于告警内容、历史数据和系统状态，推断最可能的根因
3. **修复建议**：生成可执行的修复步骤
4. **告警压缩**：将多条告警压缩为一条结构化报告，减少噪音

### 架构设计

```
┌─────────────────────────────────────────────────────┐
│                   监控数据源                         │
│  Prometheus  ──┐                                    │
│  Alertmanager  ──┤                                   │
│  Syslog        ──┤──→  告警采集器 (Python)           │
│  Node Exporter ──┤      (监听 Alertmanager webhook)   │
│  cAdvisor      ──┘                                    │
└─────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────┐
│              LLM 告警分析引擎                        │
│  ┌──────────────┐  ┌──────────────┐                │
│  │ 告警预处理    │  │ 上下文收集    │                │
│  │ (去重/归一化) │  │ (指标/日志)  │                │
│  └──────┬───────┘  └──────┬───────┘                │
│         └────────┬────────┘                         │
│                  ▼                                   │
│         ┌─────────────────┐                         │
│         │  LLM 推理        │                         │
│         │  (Qwen2.5 /     │                         │
│         │   DeepSeek-V3)  │                         │
│         └────────┬────────┘                         │
│                  ▼                                   │
│         ┌─────────────────┐                         │
│         │  根因分析报告     │                         │
│         │  + 修复建议      │                         │
│         └────────┬────────┘                         │
└──────────────────┼─────────────────────────────────┘
                   │
         ┌─────────┼─────────┐
         ▼         ▼         ▼
    ┌─────────┐ ┌───────┐ ┌────────┐
    │ Telegram│ │ Slack │ │ 邮件    │
    │ 通知    │ │ 通知  │ │ 报告   │
    └─────────┘ └───────┘ └────────┘
```

## 完整实现方案

### 第一步：部署本地 LLM

使用 Ollama 在 VPS 上部署轻量级 LLM：

```bash
# 安装 Ollama
curl -fsSL https://ollama.com/install.sh | sh

# 拉取 Qwen2.5 7B 模型（中英文理解能力强，资源占用适中）
ollama pull qwen2.5:7b-instruct

# 验证模型可用
ollama run qwen2.5:7b-instruct "你好，请用一句话介绍你自己"
```

对于内存较小的 VPS（2GB+），可以使用更轻量的模型：

```bash
# 极致轻量版（500MB 内存占用）
ollama pull qwen2.5:1.5b-instruct

# 平衡版（推荐，4GB+ 内存）
ollama pull qwen2.5:7b-instruct
```

### 第二步：告警采集器

编写 Python 脚本监听 Alertmanager 的 webhook 推送：

```python
#!/usr/bin/env python3
"""
Alert Correlation Engine — 监听 Alertmanager webhook，
调用本地 LLM 进行告警关联分析和根因推断。
"""

import json
import os
import time
import requests
from datetime import datetime, timedelta
from collections import defaultdict
from pathlib import Path

# 配置
OLLAMA_API = os.getenv("OLLAMA_API", "http://localhost:11434")
MODEL = os.getenv("LLM_MODEL", "qwen2.5:7b-instruct")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
ALERT_HISTORY_FILE = Path("/var/log/vps-alerts/history.json")
COOLDOWN_SECONDS = int(os.getenv("COOLDOWN_SECONDS", "300"))  # 5分钟去重

# 告警历史（用于跨时间窗口关联）
alert_history = defaultdict(list)


def load_history():
    if ALERT_HISTORY_FILE.exists():
        try:
            return json.loads(ALERT_HISTORY_FILE.read_text())
        except Exception:
            return {}
    return {}


def save_history(history):
    ALERT_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    # 只保留最近 24 小时的数据
    cutoff = datetime.utcnow() - timedelta(hours=24)
    cleaned = {}
    for key, alerts in history.items():
        cleaned[key] = [a for a in alerts if datetime.fromisoformat(a["time"]) > cutoff]
    ALERT_HISTORY_FILE.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2))


def fetch_context(alert):
    """收集告警相关的上下文信息（CPU、内存、磁盘、进程等）"""
    instance = alert.get("labels", {}).get("instance", "unknown")
    context = {}

    # 获取当前系统状态
    try:
        # CPU 使用率
        r = requests.get(f"http://{instance}:9100/metrics", timeout=5)
        for line in r.text.splitlines():
            if line.startswith("cpu_usage_percent"):
                context["cpu_usage"] = float(line.split()[-1])
            elif line.startswith("memory_usage_percent"):
                context["memory_usage"] = float(line.split()[-1])
            elif line.startswith("disk_io_time_seconds_total"):
                context["disk_io"] = True
    except Exception:
        pass

    # 获取最近异常的进程（top by CPU/Memory）
    try:
        import subprocess
        result = subprocess.run(
            ["top", "-bn1", "-o", "%CPU"],
            capture_output=True, text=True, timeout=5
        )
        lines = result.stdout.splitlines()[3:8]  # top 5 进程
        context["top_cpu_processes"] = lines
    except Exception:
        pass

    try:
        import subprocess
        result = subprocess.run(
            ["docker", "ps", "--format", "table {{.Names}}\t{{.CPUPerc}}\t{{.MemPerc}}"],
            capture_output=True, text=True, timeout=5
        )
        context["docker_containers"] = result.stdout.strip().splitlines()[1:]
    except Exception:
        pass

    return context


def build_prompt(alerts, context):
    """构建 LLM 提示词"""
    now = datetime.utcnow().isoformat() + "Z"

    alerts_text = []
    for i, alert in enumerate(alerts, 1):
        labels = alert.get("labels", {})
        annotations = alert.get("annotations", {})
        alerts_text.append(
            f"{i}. [{alert.get('status', 'unknown')}] {labels.get('alertname', 'Unknown')}\n"
            f"   严重度: {labels.get('severity', 'unknown')}\n"
            f"   实例: {labels.get('instance', 'unknown')}\n"
            f"   描述: {annotations.get('description', 'N/A')}\n"
            f"   摘要: {annotations.get('summary', 'N/A')}"
        )

    context_text = json.dumps(context, ensure_ascii=False, indent=2)

    prompt = f"""你是资深运维专家，擅长从多条告警中快速定位根因。

当前时间: {now}

收到的告警列表（共 {len(alerts)} 条）:
{chr(10).join(alerts_text)}

相关系统上下文:
{context_text}

请完成以下分析，以 JSON 格式返回（不要包含 markdown 代码块）:
{{
  "root_cause": "根因的简短描述（中文）",
  "root_cause_severity": "critical|high|medium|low",
  "correlated_alerts": ["受根因影响的告警名称列表"],
  "independent_alerts": ["与根因无关的独立告警列表"],
  "explanation": "分析过程的简要说明（2-3句话）",
  "action_plan": [
    {{"step": 1, "action": "具体操作命令或步骤", "priority": "high"}}
  ],
  "estimated_recovery_time": "预计恢复时间"
}}"""
    return prompt


def call_llm(prompt: str) -> dict:
    """调用本地 Ollama API"""
    response = requests.post(
        f"{OLLAMA_API}/api/generate",
        json={
            "model": MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.3, "num_predict": 1024}
        },
        timeout=60
    )
    response.raise_for_status()
    result = response.json()

    # 尝试解析 JSON 输出
    output = result.get("response", "")
    # 去除可能的 markdown 代码块
    if "```json" in output:
        output = output.split("```json")[1].split("```")[0]
    elif "```" in output:
        output = output.split("```")[1].split("```")[0]

    try:
        return json.loads(output.strip())
    except json.JSONDecodeError:
        # 解析失败时返回原始输出
        return {"raw_output": output, "error": "JSON parse failed"}


def send_telegram(message: str):
    """发送 Telegram 通知"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    requests.post(url, json={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }, timeout=10)


def format_report(report: dict, alerts: list) -> str:
    """将 LLM 分析报告格式化为可读消息"""
    lines = [
        f"🔔 **VPS 告警关联分析报告**",
        f"⏰ {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC",
        f"",
        f"📊 **告警数量**: {len(alerts)} 条",
        f"🎯 **根因**: {report.get('root_cause', 'N/A')}",
        f"⚠️ **严重度**: {report.get('root_cause_severity', 'N/A')}",
        f"💡 **分析说明**: {report.get('explanation', 'N/A')}",
        f"",
    ]

    correlated = report.get("correlated_alerts", [])
    if correlated:
        lines.append(f"🔗 **关联告警**: {', '.join(correlated)}")
    independent = report.get("independent_alerts", [])
    if independent:
        lines.append(f"➖ **独立告警**: {', '.join(independent)}")

    lines.append("")
    lines.append("📋 **修复建议**:")
    for step in report.get("action_plan", []):
        lines.append(f"  {step['step']}. [{step.get('priority', '')}] {step['action']}")

    recovery = report.get("estimated_recovery_time", "N/A")
    lines.append(f"\n⏱️ **预计恢复时间**: {recovery}")

    return "\n".join(lines)


def process_alerts(alert_payload):
    """处理一组告警，进行关联分析"""
    alerts = alert_payload.get("alerts", [])
    if not alerts:
        return

    # 检查是否在冷却期内（去重）
    now = datetime.utcnow().isoformat()
    group_key = tuple(sorted(a["labels"]["alertname"] for a in alerts))
    recent = alert_history.get(group_key, [])
    if recent:
        last_time = datetime.fromisoformat(recent[-1]["time"].replace("Z", "+00:00"))
        if (datetime.now(last_time.tzinfo) - last_time).total_seconds() < COOLDOWN_SECONDS:
            print(f"[SKIP] 告警组 {group_key} 在冷却期内，跳过")
            return
    alert_history[group_key].append({"time": now, "count": len(alerts)})

    print(f"[INFO] 收到 {len(alerts)} 条告警，开始关联分析...")

    # 收集上下文
    context = fetch_context(alerts[0])

    # 构建提示词并调用 LLM
    prompt = build_prompt(alerts, context)
    print(f"[INFO] 调用 LLM ({MODEL}) 分析...")

    try:
        report = call_llm(prompt)
    except Exception as e:
        print(f"[ERROR] LLM 调用失败: {e}")
        report = {"error": str(e), "raw_output": ""}

    # 格式化报告
    report_text = format_report(report, alerts)
    print(f"[INFO] 分析报告:\n{report_text}")

    # 发送通知
    send_telegram(report_text)

    # 保存历史
    save_history(alert_history)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        # 从文件读取（测试用）
        payload = json.loads(Path(sys.argv[1]).read_text())
        process_alerts(payload)
    else:
        # 监听模式（配合 HTTP server）
        from http.server import HTTPServer, BaseHTTPRequestHandler

        class AlertHandler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                payload = json.loads(self.rfile.read(length))
                process_alerts(payload)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"OK")

            def log_message(self, format, *args):
                pass  # 静默日志

        port = int(os.getenv("WEBHOOK_PORT", "8080"))
        print(f"[START] Alert correlation engine listening on port {port}")
        HTTPServer(("0.0.0.0", port), AlertHandler).serve_forever()
```

### 第三步：Alertmanager 路由配置

在 `alertmanager.yml` 中配置 webhook 路由，将所有告警转发给 LLM 分析引擎：

```yaml
global:
  resolve_timeout: 5m

route:
  group_by: ['alertname', 'instance']
  group_wait: 10s        # 等待 10 秒收集同一批告警
  group_interval: 5m
  repeat_interval: 4h
  receiver: 'llm-analyzer'

receivers:
  - name: 'llm-analyzer'
    webhook_configs:
      - url: 'http://localhost:8080/alerts'
        send_resolved: true

  - name: 'null-receiver'  # 原始告警静默，只通过 LLM 报告通知
```

关键配置说明：
- `group_by`: 按告警名称和实例分组，避免每条告警单独触发
- `group_wait: 10s`: 等待 10 秒让同一批告警聚合，减少碎片化通知
- `send_resolved: true`: 同时接收恢复通知，LLM 可以判断是否需要进一步处理

### 第四步：定时上下文刷新

除了 webhook 触发，还可以设置定时任务，定期收集系统状态并生成预防性报告：

```bash
# crontab -e
# 每 15 分钟收集一次系统状态，每小时生成一次健康报告
*/15 * * * * /usr/bin/docker exec ollama ollama run qwen2.5:7b-instruct \
  "请根据以下系统状态生成健康评分和建议（0-100分）: $(cat /tmp/sys-status.json)" \
  > /tmp/health-report.txt 2>&1

0 * * * * cat /tmp/health-report.txt | /usr/local/bin/send-telegram.sh
```

## 实际效果演示

假设 VPS 同时触发以下告警：

| 告警名称 | 严重度 | 描述 |
|---------|--------|------|
| HighCPU | critical | CPU 使用率 97% |
| HighMemory | critical | 内存使用率 92% |
| DiskSpaceLow | warning | 磁盘使用率 88% |
| Nginx502 | critical | Nginx 返回 502 |
| MySQLSlow | warning | 慢查询增加 |

**传统方式**：运维人员需要逐一登录服务器，查看 `top`、`df -h`、`systemctl status nginx`、`mysql slow log`，耗时 30 分钟以上。

**LLM 关联分析后**：

```
🔔 VPS 告警关联分析报告
⏰ 2026-09-22 03:15:00 UTC

📊 告警数量: 5 条
🎯 根因: MySQL 慢查询导致连接池耗尽，进而引发 Nginx 502 和内存压力
⚠️ 严重度: critical
💡 分析说明: CPU 和内存告警是 MySQL 慢查询的连锁反应。磁盘空间紧张可能是 MySQL 临时表写入导致。

🔗 关联告警: HighCPU, HighMemory, Nginx502, MySQLSlow
➖ 独立告警: DiskSpaceLow

📋 修复建议:
  1. [high] 执行 SELECT PROCESSLIST 找出卡住的查询并 KILL
  2. [high] 检查 MySQL 连接池配置 (max_connections, wait_timeout)
  3. [medium] 清理 MySQL 临时文件和慢查询日志
  4. [medium] 考虑对大表添加缺失索引

⏱️ 预计恢复时间: 10-15 分钟
```

一条报告替代了五张截图，运维人员可以直接执行修复建议，无需再逐个排查。

## 进阶优化方向

### 1. 多 VPS 协同分析

当管理多台 VPS 时，可以将所有告警汇总后统一分析：

```python
# 扩展 prompt 支持多实例
all_alerts = fetch_alerts_from_all_vps()  # 从多个节点收集告警
prompt = build_prompt(all_alerts, multi_node_context)
```

LLM 可以识别跨节点的关联性——例如"web-server-01 的磁盘满导致 replication 延迟，进而影响 db-server-01 的读性能"。

### 2. 历史模式匹配

保存每次告警分析的结论，训练 LLM 识别重复模式：

```python
# 简单的模式匹配缓存
PATTERN_DB = "/var/lib/vps-alert-patterns/patterns.json"

def find_similar_pattern(new_alerts):
    """基于关键词匹配历史告警模式"""
    # 实现 TF-IDF 或简单的关键词重叠度计算
    ...
```

### 3. 自愈执行

对于低风险操作（如清理日志、重启非关键服务），可以让 LLM 生成命令后自动执行：

```python
def execute_remediation(report: dict):
    """执行 LLM 生成的修复命令（需人工确认高风险操作）"""
    for step in report.get("action_plan", []):
        if step.get("priority") == "low" and step.get("auto_execute"):
            os.system(step["action"])
            log_action(step["action"], "auto")
        else:
            log_action(step["action"], "pending_approval")
```

### 4. 与现有工具集成

- **Grafana**: 在 Dashboard 中嵌入 LLM 分析报告面板
- **PagerDuty/Opsgenie**: 将 LLM 分析结果作为备注附加到 Incident
- **Ansible**: 将修复建议转化为 Playbook 自动执行

## 总结

| 维度 | 传统告警 | LLM 关联分析 |
|------|---------|-------------|
| 告警处理方式 | 逐条响应 | 批量关联 |
| 根因定位 | 人工排查（30min+） | LLM 自动推断（<30s） |
| 通知内容 | 原始告警文本 | 结构化分析报告 |
| 误报处理 | 无 | LLM 可识别噪声告警 |
| 跨节点关联 | 不可能 | LLM 可理解拓扑关系 |
| 修复建议 | 无 | 可执行的操作步骤 |

本地 LLM 告警关联的核心价值在于：**把告警从"通知"变成"诊断"**。运维人员不再需要成为全栈专家来理解每一条告警的含义——LLM 帮你完成了信息收集和初步分析，你只需要做最终决策。

这套方案完全运行在你的 VPS 上，数据不离开你的服务器，隐私和安全都有保障。配合 Ollama 的轻量级模型，即使是 2GB 内存的 VPS 也能流畅运行。

---

**下一步建议**：先从单台 VPS 开始，部署 Ollama + 告警采集器，观察一周的关联分析效果，再逐步扩展到多节点场景。告警规则的配置质量直接影响 LLM 的分析效果，建议先梳理清楚自己的告警体系，再开始集成。
