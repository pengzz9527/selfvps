---
title: "AI + VPS：多机群智能编排与跨节点故障关联分析"
description: "一台 VPS 出问题，三台跟着挂？传统告警各管一片，看不懂跨服务器依赖。本文用本地 LLM 构建多机群智能编排系统——自动发现节点间依赖关系、跨节点故障根因关联、智能流量调度，让一台 AI 大脑管透整个 VPS 集群。"
date: 2026-09-26T21:00:00+08:00
lastmod: 2026-09-26T21:00:00+08:00
slug: "ai-vps-fleet-intelligence-cross-node-correlation"
image: /images/posts/ai-vps-fleet-intelligence-cross-node-correlation/featured.png
tags: ["AI", "VPS", "多机群", "故障关联", "LLM", "Ollama", "跨节点", "SRE", "AIOps", "弹性"]
categories: ["AI + VPS"]
aliases: [/zh/post/ai-vps-fleet-intelligence-cross-node-correlation/]
draft: false
---

## 引言

你运营着十几台甚至几十台 VPS：有的跑 Web 服务，有的做数据库，有的处理 API，还有的专门做备份和监控。每台机器都有各自的监控和告警——但问题来了：

**当一台数据库 VPS CPU 飙到 95% 时，为什么前端 API 也一起慢了下来？**

传统的告警体系是**孤岛式**的：每台机器各自为政，Prometheus 盯着自己的节点，Loki 读着自己的日志，Alertmanager 按规则发通知。你收到 20 条告警，却不知道它们之间有什么关系。人工排查时，你要 SSH 进五六台机器，翻日志、看指标、猜关联，耗时几小时。

**真正的多机群运维需要一台 AI 大脑。**

本文介绍如何用本地 Ollama + Qwen2.5 构建**多机群智能编排系统**：自动发现节点间的依赖关系、跨节点故障根因关联分析、智能流量调度决策，以及 fleet-wide 健康评分。所有数据都留在你的网络内部，不上传第三方。

---

## 多机群运维的核心挑战

### 挑战一：跨节点依赖隐式存在

你的服务架构看起来是这样：

```
用户 → Nginx(Load Balancer) → API Server(x3) → Redis → PostgreSQL
                                    ↘ Worker(x2) → RabbitMQ → Worker → DB
```

表面上看，每台 VPS 独立运行。但实际上，API Server 的健康度直接取决于 PostgreSQL 的响应时间，而 PostgreSQL 的性能又受 Redis 缓存命中率影响。**单个节点的告警可能是全局问题的症状**。

| 现象 | 传统方式 | AI 驱动方式 |
|------|---------|------------|
| 数据库慢查询 | DB 节点告警 | AI 关联 API 延迟上升，定位根因为 DB 锁等待 |
| 某节点磁盘满 | 单点告警 | AI 发现备份任务在多台机器同时运行，建议错峰调度 |
| CDN 回源飙升 | 无告警 | AI 从缓存命中率下降推断上游异常 |

### 挑战二：告警风暴淹没关键信息

10 台机器 × 每台 5 条告警 = 50 条告警同时涌入 Telegram。其中可能只有一条是根因，其余 49 条都是衍生症状。人工区分根因和症状需要经验，而 AI 可以用语义理解自动完成这件事。

### 挑战三：人工故障排查效率低下

传统故障排查流程：
1. 收到告警 → SSH 登录 → `top`/`htop` 看负载
2. `dmesg`/`journalctl` 查内核日志
3. `tail -f` 跟踪应用日志
4. `curl` 测试上下游依赖
5. 在多个终端之间切换，手动对比时间点

这个过程平均耗时 **30-60 分钟**，而 AI 可以在 **30 秒内**完成同样的分析并给出结论。

---

## 系统架构设计

### 整体架构图

```
┌─────────────────────────────────────────────────────────────┐
│                    Fleet Intelligence Layer                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ Dependency   │  │ Root Cause   │  │  Fleet Health    │  │
│  │ Auto-Discovery│  │ Correlator   │  │  Score Engine    │  │
│  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘  │
│         │                 │                    │            │
│  ┌──────▼───────┐  ┌──────▼───────┐  ┌────────▼─────────┐  │
│  │  Ollama      │  │  Qwen2.5     │  │  Decision        │  │
│  │  (Local LLM) │  │  (Reasoning) │  │  Engine          │  │
│  └──────────────┘  └──────────────┘  └────────┬─────────┘  │
└───────────────────────────────────────────────┼─────────────┘
                                                 │
          ┌──────────────────────────────────────┼──────────────────┐
          │                                      │                  │
    ┌─────▼─────┐                          ┌────▼────┐       ┌─────▼─────┐
    │ Node A    │                          │ Node B  │       │ Node C    │
    │ (API)     │◄──── gRPC/Telegram ─────►│ (DB)    │◄─────►│ (Cache)   │
    │ Prometheus│                          │ Loki    │       │ Node Exporter│
    └───────────┘                          └─────────┘       └───────────┘
```

### 核心模块

**1. 依赖自动发现引擎（Dependency Auto-Discovery）**

不是靠人工配置，而是通过以下方式自动学习节点间依赖：

- **流量追踪**：分析 Nginx access log 中的上游调用关系
- **端口扫描**：定期探测各节点开放的端口和服务
- **日志时间戳关联**：当节点 A 的异常日志先于节点 B 出现，建立因果假设
- **DNS 记录分析**：从 `/etc/hosts`、Docker Compose、K8s Service 中提取服务依赖

```bash
#!/bin/bash
# fleet-discover.sh — 自动发现节点间依赖关系
NODES="192.168.1.10 192.168.1.11 192.168.1.12 192.168.1.13"

for src in $NODES; do
    echo "=== Scanning $src ==="
    # 获取当前节点监听的所有端口及服务
    ss -tlnp 2>/dev/null | grep LISTEN | while read line; do
        port=$(echo "$line" | grep -oP ':\K[0-9]+')
        # 探测这个端口是否接受来自其他节点的连接
        for dst in $NODES; do
            [ "$dst" = "$src" ] && continue
            if nc -z -w 2 "$dst" "$port" 2>/dev/null; then
                echo "DEPEND: $src:$port ← $dst"
            fi
        done
    done
done
```

**2. 跨节点根因关联器（Cross-Node Root Cause Correlator）**

核心思路：**时间窗口内的异常共现 = 潜在因果链**。

```python
# fleet_correlator.py — 跨节点故障关联分析
import json
from datetime import datetime, timedelta

class FleetCorrelator:
    def __init__(self, nodes_config):
        self.nodes = nodes_config
        self.dependency_graph = {}  # 依赖关系图
        self.alert_history = {}     # 历史告警记录

    def correlate(self, alerts: list[dict]) -> list[dict]:
        """
        输入：各节点的告警列表
        输出：归并后的根因告警 + 关联症状
        """
        # 1. 按时间排序
        sorted_alerts = sorted(alerts, key=lambda x: x['timestamp'])

        # 2. 滑动窗口内寻找共现告警
        correlated = []
        window = timedelta(minutes=5)

        for i, alert in enumerate(sorted_alerts):
            group = [alert]
            for j in range(i + 1, len(sorted_alerts)):
                if sorted_alerts[j]['timestamp'] - alert['timestamp'] <= window:
                    # 检查是否在依赖图中有关联
                    if self._is_related(alert, sorted_alerts[j]):
                        group.append(sorted_alerts[j])
            if len(group) > 1:
                correlated.append({
                    'root_cause_candidate': group[0],
                    'symptoms': group[1:],
                    'confidence': self._calculate_confidence(group)
                })
        return correlated

    def _is_related(self, alert_a, alert_b) -> bool:
        """检查两条告警是否属于同一依赖链"""
        deps = self.dependency_graph.get(alert_a['node'], [])
        return alert_b['node'] in deps

    def _calculate_confidence(self, group) -> float:
        """基于时间先后、依赖强度和告警级别计算置信度"""
        # 简化版：时间差越小、依赖越强则置信度越高
        time_span = (group[-1]['timestamp'] - group[0]['timestamp']).total_seconds()
        base_conf = 0.9 if time_span < 60 else 0.7
        return min(base_conf, 0.95)
```

**3. Fleet 健康评分引擎（Fleet Health Score Engine）**

将多台机器的状态浓缩为一个数字：

```python
# health_score.py
import numpy as np

def fleet_health_score(node_metrics: dict) -> dict:
    """
    输入: {
        "node_a": {"cpu": 45, "mem": 60, "disk": 30, "err_rate": 0.01},
        "node_b": {"cpu": 92, "mem": 85, "disk": 90, "err_rate": 0.15},
        "node_c": {"cpu": 10, "mem": 20, "disk": 15, "err_rate": 0.001},
    }
    """
    scores = {}
    for node, m in node_metrics.items():
        # 各项指标加权评分（0-100）
        cpu_s = max(0, 100 - m['cpu'])          # CPU 越高分越低
        mem_s = max(0, 100 - m['mem'])
        disk_s = max(0, 100 - m['disk'])
        err_s = max(0, 100 - m['err_rate'] * 1000)  # 错误率扣分

        weighted = (
            cpu_s * 0.25 +
            mem_s * 0.20 +
            disk_s * 0.15 +
            err_s * 0.40   # 错误率权重最高
        )
        scores[node] = round(weighted, 1)

    # Fleet 综合得分 = 各节点加权平均（故障节点权重更高）
    total = sum(scores.values())
    avg = round(total / len(scores), 1)

    # 风险放大：如果任一节点 < 30，整体打折扣
    min_score = min(scores.values())
    if min_score < 30:
        avg = round(avg * (min_score / 50), 1)

    return {
        "fleet_score": avg,
        "node_scores": scores,
        "risk_level": "critical" if avg < 40 else ("warning" if avg < 70 else "healthy"),
        "weakest_node": min(scores, key=scores.get)
    }
```

**4. 智能流量调度决策器（Intelligent Traffic Router）**

基于 LLM 的动态调度：

```python
# traffic_router.py
"""
LLM 驱动的动态流量调度：
- 健康节点获得更多流量
- 异常节点自动降级
- 冷启动节点预热后再接入
"""

ROUTING_POLICY_TEMPLATE = """
你是一个 VPS 集群流量调度专家。当前集群状态：

{fleet_state}

请输出 JSON 格式的调度决策：
{{
  "action": "rebalance|scale_out|failover|normal",
  "reasoning": "简短说明",
  "routing_table": {{
    "node_a": {"weight": 0.4, "health_check": true},
    "node_b": {"weight": 0.1, "health_check": false},
    "node_c": {"weight": 0.5, "health_check": true}
  }},
  "estimated_latency_impact": "+5ms"
}}
"""

def get_routing_decision(fleet_state: dict, llm_client) -> dict:
    prompt = ROUTING_POLICY_TEMPLATE.format(fleet_state=json.dumps(fleet_state, indent=2))
    response = llm_client.chat(prompt)
    return json.loads(extract_json(response))
```

---

## 部署实现

### 步骤一：统一采集层（Agentless 方案）

不需要在每个节点安装 Agent，通过 SSH + 远程命令采集：

```bash
#!/bin/bash
# fleet-collector.sh — 从所有节点收集指标，无需安装 Agent
COLLECTOR_NODE="192.168.1.10"
ALL_NODES="192.168.1.10 192.168.1.11 192.168.1.12 192.168.1.13"

collect_node_metrics() {
    local node=$1
    echo "Collecting from $node ..."

    ssh -o ConnectTimeout=5 "$node" '
        echo "=== $(hostname) ==="
        echo "CPU: $(top -bn1 | grep "Cpu(s)" | awk "{print \$2}" | cut -d"." -f1)%"
        echo "MEM: $(free | awk "/^Mem:/ {printf \"%.1f%%\", \$3/\$2 * 100}")"
        echo "DISK: $(df -h / | awk "NR==2 {print \$5}")"
        echo "LOAD: $(uptime | awk -F"load average:" "{print \$2}" | cut -d"," -f1)"
        echo "ERR_LOG: $(grep -c "ERROR\|FATAL\|PANIC" /var/log/syslog 2>/dev/null || echo 0)"
        echo "ACTIVE_CONN: $(ss -tn | grep ESTAB | wc -l)"
    ' 2>/dev/null || echo "UNREACHABLE: $node"
}

for node in $ALL_NODES; do
    collect_node_metrics "$node"
done | tee /tmp/fleet_snapshot.jsonl
```

### 步骤二：依赖关系图谱构建

```python
# dependency_graph.py
"""
基于日志和连接信息自动构建服务依赖图谱
"""
import subprocess
import re
from collections import defaultdict

class DependencyGraphBuilder:
    def __init__(self, nodes):
        self.nodes = nodes
        self.graph = defaultdict(set)  # node -> set of dependent nodes
        self.edge_weights = defaultdict(float)  # (from, to) -> weight

    def build_from_logs(self, log_dir: str):
        """从各节点的 access/error log 中提取调用关系"""
        for node in self.nodes:
            # 解析 Nginx upstream_response_time
            cmd = f"ssh {node} 'grep upstream_address /var/log/nginx/access.log | \
                   awk \"{{print \\$10, \\$7}}\" | head -100'"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

            for line in result.stdout.strip().split('\n'):
                parts = line.split()
                if len(parts) >= 2:
                    upstream = parts[1]  # 上游地址
                    # 简化：假设上游 IP 对应某节点
                    target_node = self._ip_to_node(upstream)
                    if target_node and target_node != node:
                        self.graph[node].add(target_node)
                        self.edge_weights[(node, target_node)] += 1

    def build_from_connections(self):
        """从网络连接中提取依赖"""
        for node in self.nodes:
            cmd = f"ssh {node} 'ss -tn state established | grep -v {node} | \
                   awk \"{{print \\$5}}\" | cut -d: -f1 | sort -u'"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            for remote_ip in result.stdout.strip().split('\n'):
                target = self._ip_to_node(remote_ip.strip())
                if target:
                    self.graph[node].add(target)

    def _ip_to_node(self, ip: str) -> str:
        """IP 到节点名的映射（实际部署中应从 DNS 或配置表获取）"""
        node_map = {
            "192.168.1.10": "api-01",
            "192.168.1.11": "db-primary",
            "192.168.1.12": "cache-01",
            "192.168.1.13": "worker-01",
        }
        return node_map.get(ip, ip)

    def to_llm_context(self) -> str:
        """导出为 LLM 可理解的文本格式"""
        lines = ["服务依赖关系图谱："]
        for src, targets in self.graph.items():
            for tgt in targets:
                weight = self.edge_weights.get((src, tgt), 1)
                lines.append(f"  {src} → {tgt} (强度: {weight})")
        return "\n".join(lines)
```

### 步骤三：LLM 根因分析管道

```python
# llm_root_cause.py
"""
使用本地 Ollama + Qwen2.5 进行跨节点根因分析
"""
import ollama
import json
from datetime import datetime

RCA_PROMPT = """你是一个资深 SRE 专家，负责分析多机群故障。

## 集群依赖关系
{dependency_map}

## 当前告警（按时间排序）
{alerts}

## 各节点健康评分
{health_scores}

请分析：
1. **根因节点**：哪台机器最先出现异常？
2. **传播路径**：故障是如何从根因节点扩散到其他节点的？
3. **置信度**：你对这个判断有多大把握？（0-100%）
4. **建议操作**：应该优先处理哪一步？

输出 JSON：
{{
  "root_cause_node": "节点名",
  "propagation_path": ["节点A", "节点B", "节点C"],
  "confidence": 85,
  "analysis": "详细分析文字",
  "recommended_actions": [
    {{"step": 1, "action": "操作描述", "priority": "high"}}
  ]
}}
"""

def analyze_fleet_incident(
    dependency_map: str,
    alerts: list[dict],
    health_scores: dict,
    model: str = "qwen2.5:7b"
) -> dict:
    alerts_json = json.dumps(alerts, indent=2, ensure_ascii=False)
    health_json = json.dumps(health_scores, indent=2, ensure_ascii=False)

    prompt = RCA_PROMPT.format(
        dependency_map=dependency_map,
        alerts=alerts_json,
        health_scores=health_json
    )

    response = ollama.chat(model=model, messages=[
        {"role": "user", "content": prompt}
    ])

    # 提取 JSON
    text = response['message']['content']
    json_start = text.find('{')
    json_end = text.rfind('}') + 1
    return json.loads(text[json_start:json_end])
```

### 步骤四：Telegram 告警聚合通知

```python
# fleet_notifier.py
"""
将 50 条分散告警合并为 1 条 AI 分析报告，推送到 Telegram
"""
import telebot
import ollama

TELEGRAM_BOT_TOKEN = "YOUR_BOT_TOKEN"
TELEGRAM_CHAT_ID = "YOUR_CHAT_ID"

def send_fleet_alert(fleet_state: dict, rca_result: dict):
    bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

    # 构建精简报告
    report = f"""🚨 **VPS 集群异常告警**

📊 **Fleet 健康分**: {fleet_state['fleet_score']}/100 ({fleet_state['risk_level']})
💥 **根因节点**: {rca_result['root_cause_node']}
🔗 **传播路径**: {' → '.join(rca_result['propagation_path'])}
🎯 **置信度**: {rca_result['confidence']}%

**各节点状态**:
"""
    for node, score in fleet_state['node_scores'].items():
        emoji = "🟢" if score >= 70 else ("🟡" if score >= 40 else "🔴")
        report += f"{emoji} {node}: {score}\n"

    report += f"""
**建议操作**:
"""
    for action in rca_result['recommended_actions']:
        report += f"{action['step']}. [{action['priority']}] {action['action']}\n"

    report += f"\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

    bot.send_message(TELEGRAM_CHAT_ID, report, parse_mode="Markdown")
```

---

## 完整工作流示例

假设你的 4 节点集群出现异常：

```
时刻 T+0s   : db-primary 磁盘使用率达到 92%
时刻 T+30s  : db-primary 开始拒绝新连接（连接池耗尽）
时刻 T+45s  : api-01 出现大量 502 错误（上游不可达）
时刻 T+60s  : api-02 出现大量 502 错误
时刻 T+90s  : cache-01 缓存失效激增（db 响应变慢导致 TTL 过期）
时刻 T+120s : worker-01 消息积压（消费端处理变慢）
```

**传统方式**：收到 5 条告警，逐一 SSH 登录排查，30 分钟后才定位到根因是 db-primary 磁盘空间。

**AI 驱动方式**：

1. FleetCorrelator 在 T+60s 时将所有告警归并为一个事件组
2. 依赖图谱显示 api-01 → db-primary，cache-01 → db-primary
3. LLM 分析后输出：
   ```json
   {
     "root_cause_node": "db-primary",
     "propagation_path": ["db-primary", "api-01", "api-02", "cache-01", "worker-01"],
     "confidence": 92,
     "analysis": "db-primary 磁盘空间不足导致写入失败，连接池耗尽引发级联故障",
     "recommended_actions": [
       {"step": 1, "action": "清理 db-primary 旧日志和临时文件释放空间", "priority": "high"},
       {"step": 2, "action": "重启 db-primary 上的 PostgreSQL 释放连接", "priority": "high"},
       {"step": 3, "action": "检查 cache-01 缓存策略，降低 db 负载", "priority": "medium"}
     ]
   }
   ```
4. Telegram 收到一条聚合告警，30 秒内知道该做什么

---

## 与现有监控体系的集成

本系统不是要替代 Prometheus/Grafana/Loki，而是**在上层增加 AI 智能**：

```
┌─────────────────────────────────────────────────┐
│           Fleet Intelligence Layer (本方案)       │
│  • 告警聚合与根因分析                              │
│  • 跨节点依赖推理                                  │
│  • 智能调度决策                                    │
├─────────────────────────────────────────────────┤
│         标准化数据接口层 (OpenTelemetry)           │
│  • Metrics → Prometheus                          │
│  • Logs → Loki / Grafana                         │
│  • Traces → Tempo / Jaeger                       │
├─────────────────────────────────────────────────┤
│            数据采集层                              │
│  • Node Exporter (指标)                           │
│  • Promtail (日志)                                │
│  • cAdvisor (容器)                                │
└─────────────────────────────────────────────────┘
```

**关键点**：Fleet Intelligence Layer 通过读取已有的 Prometheus 指标和 Loki 日志来工作，无需改动现有监控栈。

---

## 成本估算

| 组件 | 硬件要求 | 月成本 |
|------|---------|--------|
| Ollama + Qwen2.5:7b | 8GB+ RAM, CPU-only 可运行 | $0（本地） |
| Fleet Collector 脚本 | 任意 VPS 均可 | $0 |
| Prometheus + Loki | 已有则复用 | $0 |
| Telegram Bot | 免费 | $0 |

整套系统可以在一台 **2GB RAM 的 VPS** 上运行，不依赖任何云服务。

---

## 总结

多机群运维的核心难点不在于监控每台机器，而在于**理解机器之间的关系**。AI 在这里的价值是：

1. **自动发现**：不需要人工配置依赖关系，AI 从日志和连接中自动学习
2. **语义关联**：将 50 条分散告警理解为一个连贯的故障故事
3. **推理决策**：不仅告诉你"发生了什么"，还告诉你"为什么"和"该怎么办"
4. **零成本部署**：本地 LLM + 脚本，无需订阅任何 SaaS

当你的 VPS 数量从 1 台增长到 10 台、100 台时，这套系统能让你保持同样的运维效率——因为 AI 不会疲劳，不会漏看告警，也不会忘记哪个服务依赖哪个数据库。

**下一期**我们将深入讲解如何将这套系统接入 CI/CD，实现故障自愈的闭环——AI 发现根因后自动执行修复脚本，并在完成后通知你。
