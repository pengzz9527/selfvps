---
title: "AI 驱动的 VPS 智能网络诊断：从故障定位到自动修复的全链路方案"
description: "用 AI 重构 VPS 网络故障排查流程——智能 DNS 诊断、TCP 连接分析、延迟瓶颈定位、路由追踪与自动修复，让网络问题从'黑盒'走向'透明'"
date: 2026-09-14T20:00:00+08:00
lastmod: 2026-09-14T20:00:00+08:00
slug: "ai-vps-intelligent-network-diagnostics"
tags: ["AI Agent", "VPS", "网络诊断", "故障定位", "DNS 诊断", "TCP 分析", "延迟优化", "AIOps", "自动化运维"]
categories: ["AI + VPS"]
aliases: [/zh/post/ai-vps-intelligent-network-diagnostics/]
image: /images/posts/ai-vps-intelligent-network-diagnostics/featured.png
---

## 引言：网络故障的"盲区"与 AI 的破局之道

你是否经历过这样的深夜报警：

> *"用户反馈网站访问缓慢，但 ping 正常、端口通畅、CPU/内存也无异常……问题到底出在哪？"*

传统 VPS 网络排查依赖运维人员的经验——逐层检查 DNS、TCP、路由、带宽，每一步都要手动执行命令、对比基线、推断结论。这个过程不仅耗时，而且**极易遗漏隐性问题**：间歇性丢包、DNS 缓存污染、BGP 路由抖动、TCP 重传风暴……

**AI 智能网络诊断系统**正是为了解决这些痛点而生。它通过持续采集网络遥测数据、建立行为基线、运用 LLM 进行根因推理，实现从"被动救火"到"主动预测"的转变。

本文将带你构建一套完整的 **AI 驱动的 VPS 智能网络诊断系统**，涵盖六大核心能力：

1. **智能 DNS 诊断**：多源解析验证、缓存污染检测、TTL 异常告警
2. **TCP 连接质量分析**：重传率、RTT、窗口缩放、拥塞控制自动调优
3. **延迟瓶颈定位**：端到端延迟分解、热点路径识别
4. **智能路由追踪**：BGP 路由变化监测、AS 路径异常检测
5. **间歇性故障捕捉**：基于时间序列的丢包/抖动模式识别
6. **自动修复闭环**：诊断结果 → 修复建议 → 一键执行 → 效果验证

---

## 一、系统架构设计

```
┌──────────────────────────────────────────────────────────────────┐
│                        用户交互层                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │  Web 控制台   │  │  CLI 命令行   │  │  API/Webhook │           │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘           │
└─────────┼─────────────────┼─────────────────┼───────────────────┘
          │                 │                 │
          └─────────────────┴────────┬────────┘
                                    │
┌───────────────────────────────────┼───────────────────────────────┐
│                      AI 诊断引擎                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐            │
│  │  LLM 推理    │←→│  规则引擎    │←→│  知识图谱    │            │
│  │  (根因分析)   │  │  (阈值告警)  │  │  (历史模式)  │            │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘            │
│         │                 │                 │                     │
│  ┌──────┴───────┐  ┌──────┴───────┐  ┌──────┴───────┐            │
│  │  诊断报告生成 │  │  修复建议引擎 │  │  效果验证器   │            │
│  └──────────────┘  └──────────────┘  └──────────────┘            │
└──────────────────────────┬───────────────────────────────────────┘
                           │
┌──────────────────────────┼───────────────────────────────────────┐
│                      数据采集层                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐            │
│  │ DNS 探针     │  │ TCP 质量探针  │  │ 路由追踪探针  │            │
│  │ (dig/nslookup)│  │ (tcpdump/    │  │ (traceroute  │            │
│  │              │  │  ss/netstat)  │  │  mtr)        │            │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘            │
│         │                 │                 │                     │
│  ┌──────┴───────┐  ┌──────┴───────┐  ┌──────┴───────┐            │
│  │  带宽探针    │  │  ICMP 探针   │  │ BGP 监听器   │            │
│  │ (iperf3)     │  │ (ping/fping) │  │ (birdcli/   │            │
│  │              │  │              │  │  watchquagga)│            │
│  └──────────────┘  └──────────────┘  └──────────────┘            │
└─────────────────────────────────────────────────────────────────┘
```

### 核心组件说明

| 组件 | 技术选型 | 职责 |
|------|---------|------|
| DNS 探针 | dig + 多 DNS 服务器并行查询 | 检测解析一致性、缓存污染、TTL 异常 |
| TCP 质量探针 | ss/netstat/tcpdump + Go-TCP-Metrics | 监控重传率、RTT、窗口大小、拥塞状态 |
| 路由追踪探针 | mtr + BIRD CLI | 实时路径跟踪、BGP 路由变化检测 |
| 带宽探针 | iperf3 定时压测 | 吞吐量、丢包率、延迟分布测量 |
| LLM 推理引擎 | Ollama (Qwen/DeepSeek) + 结构化 prompt | 根因分析、修复建议生成 |
| 知识图谱 | Neo4j / SQLite JSON | 存储历史故障模式、拓扑关系、修复记录 |

---

## 二、智能 DNS 诊断

DNS 解析问题是 VPS 网络故障中最常见也最隐蔽的原因之一。AI 诊断系统通过多维度 DNS 健康检测，自动发现并定位问题。

### 2.1 多源并行解析验证

传统排查只检查一个 DNS 服务器，而 AI 系统会同时向多个权威 DNS 和递归 DNS 发起查询，对比结果一致性：

```bash
#!/bin/bash
# dns_diagnostic.sh — 多源 DNS 健康检测

DOMAIN="${1:-example.com}"
DNS_SERVERS=("8.8.8.8" "1.1.1.1" "223.5.5.5" "9.9.9.9" "119.29.29.29")

echo "=== DNS 多源解析诊断: $DOMAIN ==="
echo ""

results=()
for dns in "${DNS_SERVERS[@]}"; do
    result=$(dig @"$dns" "$DOMAIN" +short +time=5 +tries=2 2>/dev/null)
    status=$?
    if [ $status -eq 0 ] && [ -n "$result" ]; then
        echo "  [$dns] → $result"
        results+=("$result")
    else
        echo "  [$dns] ❌ 解析失败或超时"
    fi
done

# 一致性检查
unique_ips=$(printf '%s\n' "${results[@]}" | sort -u | wc -l)
total_resolutions=${#results[@]}

echo ""
if [ $unique_ips -eq 1 ]; then
    echo "✅ DNS 一致性: 所有 DNS 服务器返回相同结果"
elif [ $unique_ips -le 3 ]; then
    echo "⚠️  DNS 轻微分歧: 检测到 $unique_ips 种不同解析结果，可能存在 GSLB 或 CDN 调度"
else
    echo "🚨 DNS 严重分歧: 检测到 $unique_ips 种不同结果，可能存在 DNS 污染或配置错误"
fi

# TTL 检查
echo ""
echo "--- TTL 分析 ---"
for dns in "${DNS_SERVERS[@]:0:2}"; do
    ttl=$(dig @"$dns" "$DOMAIN" +noall +answer | awk '/^[^;]/ {print $5}' | head -1)
    echo "  [$dns] TTL = ${ttl}s"
done
```

### 2.2 AI 根因分析

采集到 DNS 数据后，LLM 引擎进行智能分析：

```python
# dns_ai_analyzer.py
import json
from openai import OpenAI  # 或 ollama 兼容接口

def analyze_dns_issues(dns_data: dict, history: list) -> dict:
    """AI 驱动的 DNS 问题根因分析"""
    
    client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")
    
    prompt = f"""你是一个专业的网络运维专家。请分析以下 DNS 诊断数据，找出潜在问题并给出修复建议。

【当前诊断结果】
{json.dumps(dns_data, ensure_ascii=False, indent=2)}

【历史故障记录】
{json.dumps(history[-10:], ensure_ascii=False, indent=2) if history else '无历史记录'}

请按以下格式输出 JSON：
{{
  "issues": [
    {{
      "severity": "critical|warning|info",
      "type": "dns_poisoning|ttl_anomaly|resolution_failure|inconsistency|cache_expiry",
      "description": "问题描述",
      "affected_domains": ["domain1"],
      "evidence": "关键证据"
    }}
  ],
  "root_cause": "最可能的根因",
  "recommendations": [
    {{
      "action": "具体修复操作",
      "command": "执行的命令（如有）",
      "priority": 1
    }}
  ],
  "confidence": 0.95
}}"""

    response = client.chat.completions.create(
        model="qwen2.5:7b",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.1
    )
    
    return json.loads(response.choices[0].message.content)
```

### 2.3 典型 DNS 故障场景

| 故障类型 | 现象 | AI 诊断逻辑 | 自动修复 |
|---------|------|------------|---------|
| DNS 缓存污染 | 不同 DNS 服务器返回不一致结果 | 多源对比 + 与权威 DNS 交叉验证 | 切换至备用 DNS，清空本地缓存 |
| TTL 异常突变 | TTL 从 3600s 骤降至 60s | 时间序列异常检测 (3σ 原则) | 告警通知，记录变更事件 |
| 解析超时 | 部分 DNS 服务器无响应 | 并行查询 + 超时阈值统计 | 自动切换 DNS 上游 |
| CNAME 环路 | 解析结果指向自身 | DNS 解析图遍历检测环 | 告警 + 生成配置修正建议 |

---

## 三、TCP 连接质量智能分析

TCP 连接质量直接影响用户体验。AI 系统持续监控 TCP 指标，自动识别异常模式。

### 3.1 关键 TCP 指标采集

```python
# tcp_monitor.py
import subprocess
import re
import json
from datetime import datetime, timedelta
from collections import deque

class TCPQualityMonitor:
    """TCP 连接质量监控"""
    
    def __init__(self, sample_interval=5):
        self.sample_interval = sample_interval
        self.metrics_history = deque(maxlen=288)  # 24小时 @ 5分钟间隔
    
    def get_tcp_stats(self) -> dict:
        """采集当前 TCP 连接统计"""
        stats = {}
        
        # 活跃连接数
        result = subprocess.run(
            ['ss', '-s'], capture_output=True, text=True
        )
        active = re.search(r'estab (\d+)', result.stdout)
        stats['established'] = int(active.group(1)) if active else 0
        
        # 重传率
        result = subprocess.run(
            ['ss', '-i'], capture_output=True, text=True
        )
        retransmits = re.findall(r'retransmits (\d+)', result.stdout)
        stats['total_retransmits'] = sum(int(r) for r in retransmits)
        
        # RTT 统计
        result = subprocess.run(
            ['ss', '-tni'], capture_output=True, text=True
        )
        rtts = re.findall(r'rto (\d+) ato (\d+)', result.stdout)
        if rtts:
            rto_values = [int(r[0]) for r in rtts]
            stats['avg_rto'] = sum(rto_values) / len(rto_values)
            stats['max_rto'] = max(rto_values)
        
        # 窗口大小
        windows = re.findall(r'wc:(\d+)', result.stdout)
        if windows:
            w_values = [int(w) for w in windows]
            stats['avg_window'] = sum(w_values) / len(w_values)
            stats['min_window'] = min(w_values)
        
        stats['timestamp'] = datetime.now().isoformat()
        return stats
    
    def detect_anomalies(self, current: dict, baseline: dict) -> list:
        """基于历史基线检测异常"""
        anomalies = []
        
        # 重传率异常
        if baseline.get('retransmit_rate', 0) > 0:
            current_retransmit = current.get('total_retransmits', 0) / max(current['established'], 1)
            baseline_rate = baseline.get('retransmit_rate', 0)
            if current_retransmit > baseline_rate * 3:
                anomalies.append({
                    'type': 'high_retransmit',
                    'current': round(current_retransmit, 4),
                    'baseline': round(baseline_rate, 4),
                    'severity': 'warning'
                })
        
        # 窗口收缩异常
        if current.get('min_window', 0) < 1460:
            anomalies.append({
                'type': 'window_shrink',
                'value': current['min_window'],
                'severity': 'info'
            })
        
        return anomalies
    
    def get_tcp_state_distribution(self) -> dict:
        """获取 TCP 连接状态分布"""
        result = subprocess.run(
            ['ss', '-tan'], capture_output=True, text=True
        )
        states = re.findall(r'\w+(?=\s)', result.stdout)
        distribution = {}
        for state in states:
            distribution[state] = distribution.get(state, 0) + 1
        return distribution
```

### 3.2 AI 驱动的 TCP 问题诊断

```python
# tcp_ai_analyzer.py
def analyze_tcp_issues(tcp_metrics: dict, tcp_history: list) -> dict:
    """AI 分析 TCP 质量问题"""
    
    prompt = f"""你是网络专家。分析以下 TCP 质量数据，诊断潜在问题。

【当前 TCP 指标】
- 活跃连接数: {tcp_metrics.get('established', 0)}
- 平均 RTT: {tcp_metrics.get('avg_rtt_ms', 'N/A')}ms
- 最大 RTO: {tcp_metrics.get('max_rto', 0)}ms
- 最小窗口: {tcp_metrics.get('min_window', 0)} bytes
- 重传次数: {tcp_metrics.get('total_retransmits', 0)}
- 连接状态分布: {json.dumps(tcp_metrics.get('state_distribution', {}))}

【近期趋势】
{json.dumps(tcp_history[-20:], ensure_ascii=False) if tcp_history else '数据不足'}

请输出 JSON 格式的分析和修复建议。"""

    # 调用 LLM 进行分析...
    # (同 DNS 分析的 LLM 调用模式)
    pass
```

### 3.3 常见 TCP 问题与 AI 诊断

| 问题 | TCP 指标特征 | AI 诊断结论 | 修复方案 |
|------|-------------|------------|---------|
| 网络拥塞 | 重传率高 + RTT 上升 + 窗口收缩 | 拥塞控制算法不适应当前网络 | 切换 BBR 拥塞控制 |
| DNS 解析慢 | ESTABLISHED 低 + SYN_SENT 堆积 | DNS 解析成为瓶颈 | 检查 DNS 缓存、优化 resolv.conf |
| 连接重置频繁 | FIN_WAIT 堆积 + RST 数量高 | 对端主动断开/防火墙拦截 | 检查防火墙规则、对端服务状态 |
| 半连接积压 | SYN_RECV 过多 | SYN Flood 攻击或连接耗尽 | 启用 SYN Cookies、调整 backlog |

---

## 四、延迟瓶颈智能定位

延迟问题是用户感知最差的网络问题。AI 系统通过端到端延迟分解，精准定位瓶颈所在。

### 4.1 延迟分层分解模型

```
用户 → [WAN 延迟] → [边缘节点延迟] → [VPS 入站延迟] → [协议处理延迟] → [应用处理延迟]
         ↑                ↑                  ↑                  ↑                ↑
      BGP 路由         CDN/EDGE          TCP握手           HTTP/TLS         业务逻辑
      跳数统计         缓存命中率         RTT 测量          请求处理          数据库查询
```

### 4.2 智能延迟诊断脚本

```bash
#!/bin/bash
# latency_diagnostic.sh — AI 增强延迟诊断

TARGET="${1:-8.8.8.8}"
echo "=== 延迟诊断: $TARGET ==="
echo ""

# 1. 基础连通性
echo "--- ICMP 延迟 (10次) ---"
ping -c 10 "$TARGET" 2>/dev/null | grep -E 'rtt|packet'
echo ""

# 2. 路由追踪
echo "--- 路由追踪 ---"
mtr -r -c 5 --no-dns "$TARGET" 2>/dev/null | tail -20
echo ""

# 3. TCP 连接延迟
echo "--- TCP 握手延迟 ---"
for i in $(seq 1 5); do
    start=$(date +%s%N)
    curl -s -o /dev/null -w "%{time_connect}" "https://$TARGET" 2>/dev/null
    end=$(date +%s%N)
done
echo ""

# 4. 带宽测试
echo "--- 带宽测试 ---"
if command -v iperf3 &>/dev/null; then
    iperf3 -c "$TARGET" -t 5 --format b 2>&1 | grep -E 'sender|receiver|sent'
else
    echo "(iperf3 未安装，跳过带宽测试)"
fi
echo ""

# 5. 丢包率统计
echo "--- 丢包率 (30秒) ---"
fping -q -c 30 -i 100 "$TARGET" 2>/dev/null | tail -1
```

### 4.3 AI 延迟分析报告生成

```python
# latency_ai_report.py
import subprocess
import json

def generate_latency_report(diagnostic_output: str) -> dict:
    """AI 生成延迟分析报告"""
    
    prompt = f"""你是网络性能专家。根据以下延迟诊断结果，生成详细的分析报告。

【诊断原始输出】
{diagnostic_output}

请输出 JSON:
{{
  "bottleneck_location": "wan|edge|vps_inbound|protocol|application",
  "bottleneck_description": "瓶颈描述",
  "latency_breakdown": {{
    "dns_resolution_ms": 15,
    "tcp_handshake_ms": 25,
    "tls_negotiation_ms": 30,
    "server_processing_ms": 50,
    "total_ms": 120
  }},
  "recommendations": [
    {{
      "category": "network|protocol|application",
      "action": "具体措施",
      "expected_improvement": "预期改善"
    }}
  ],
  "priority": "high|medium|low"
}}"""
    
    # 调用 LLM 生成报告...
    pass
```

---

## 五、路由与 BGP 智能监测

对于多线 BGP VPS 或跨境业务，路由变化直接影响可用性。AI 系统实时监控路由状态。

### 5.1 BGP 路由变化检测

```python
# bgp_monitor.py
import subprocess
import json
from datetime import datetime

class BGPMonitor:
    """BGP 路由监控"""
    
    def __init__(self):
        self.last_routes = {}
        self.events = []
    
    def get_bgp_routes(self) -> dict:
        """获取当前 BGP 路由表"""
        routes = {}
        
        # 通过 birdcli 获取 BGP 路由
        result = subprocess.run(
            ['birdcli', 'bird', 'show', 'route'],
            capture_output=True, text=True
        )
        
        # 解析路由输出...
        # 简化版：直接保存原始输出
        routes['raw'] = result.stdout
        routes['timestamp'] = datetime.now().isoformat()
        
        return routes
    
    def detect_changes(self, current: dict, previous: dict) -> list:
        """检测路由变化"""
        changes = []
        
        current_routes = set(current.get('raw', '').split())
        previous_routes = set(previous.get('raw', '').split())
        
        new_routes = current_routes - previous_routes
        lost_routes = previous_routes - current_routes
        
        if new_routes:
            changes.append({
                'type': 'route_added',
                'routes': list(new_routes)[:10],
                'timestamp': datetime.now().isoformat()
            })
        
        if lost_routes:
            changes.append({
                'type': 'route_lost',
                'routes': list(lost_routes)[:10],
                'timestamp': datetime.now().isoformat(),
                'severity': 'critical'
            })
        
        return changes
    
    def check_route_stability(self, history: list) -> dict:
        """分析路由稳定性"""
        if len(history) < 2:
            return {'status': 'insufficient_data'}
        
        total_changes = 0
        critical_events = 0
        
        for entry in history:
            if 'changes' in entry:
                for change in entry['changes']:
                    total_changes += 1
                    if change.get('severity') == 'critical':
                        critical_events += 1
        
        return {
            'total_route_changes': total_changes,
            'critical_events': critical_events,
            'stability_score': max(0, 100 - total_changes * 5 - critical_events * 20),
            'status': 'stable' if critical_events == 0 else 'unstable'
        }
```

### 5.2 AI 路由异常诊断

```python
# bgp_ai_analyzer.py
def analyze_bgp_anomalies(route_changes: list, stability: dict) -> dict:
    """AI 分析 BGP 路由异常"""
    
    prompt = f"""你是 BGP 路由专家。分析以下路由变化事件。

【路由变化事件】
{json.dumps(route_changes, ensure_ascii=False, indent=2)}

【稳定性评分】
{json.dumps(stability, ensure_ascii=False)}

请输出 JSON 分析结果，包括：
- 异常类型判定
- 可能的根因（路由泄漏/黑洞/AS 路径变化）
- 影响评估
- 修复建议"""
    
    # 调用 LLM...
    pass
```

---

## 六、间歇性故障智能捕捉

间歇性网络故障（如每秒丢 1 个包）最难以排查。AI 系统通过长时间序列分析，发现人类肉眼难以察觉的模式。

### 6.1 时间序列丢包检测

```python
# intermittent_fault_detector.py
import numpy as np
from datetime import datetime, timedelta

class IntermittentFaultDetector:
    """间歇性故障检测器"""
    
    def __init__(self, window_size=60):
        self.window_size = window_size  # 滑动窗口大小（秒）
        self.packet_logs = []
    
    def add_packet_sample(self, timestamp: datetime, sent: int, received: int):
        """添加丢包样本"""
        self.packet_logs.append({
            'timestamp': timestamp.isoformat(),
            'sent': sent,
            'received': received,
            'loss_rate': (sent - received) / sent if sent > 0 else 0
        })
    
    def detect_burst_loss(self, window_seconds=30) -> list:
        """检测突发丢包"""
        if len(self.packet_logs) < self.window_size:
            return []
        
        recent = self.packet_logs[-self.window_size:]
        loss_rates = [p['loss_rate'] for p in recent]
        
        # 计算基线和异常
        mean_loss = np.mean(loss_rates)
        std_loss = np.std(loss_rates)
        
        bursts = []
        for i, rate in enumerate(loss_rates):
            if rate > mean_loss + 2 * std_loss and rate > 0.01:  # 超过 2σ 且丢包率 > 1%
                bursts.append({
                    'index': i,
                    'loss_rate': round(rate, 4),
                    'timestamp': recent[i]['timestamp'],
                    'severity': 'high' if rate > 0.05 else 'medium'
                })
        
        return bursts
    
    def detect_periodic_loss(self) -> dict:
        """检测周期性丢包模式"""
        if len(self.packet_logs) < 120:  # 需要至少 10 分钟数据
            return {'detected': False}
        
        loss_rates = [p['loss_rate'] for p in self.packet_logs]
        
        # 简单的周期性检测：检查是否存在固定间隔的高丢包
        thresholds = [0.05, 0.1, 0.2]
        results = {}
        
        for threshold in thresholds:
            high_loss_indices = [i for i, r in enumerate(loss_rates) if r >= threshold]
            if len(high_loss_indices) >= 3:
                intervals = [high_loss_indices[i+1] - high_loss_indices[i] 
                            for i in range(len(high_loss_indices)-1)]
                if intervals:
                    avg_interval = np.mean(intervals)
                    if 5 < avg_interval < 120:  # 合理的周期范围
                        results[f'loss_ge_{threshold:.0%}'] = {
                            'detected': True,
                            'avg_interval_samples': round(avg_interval, 1),
                            'occurrence_count': len(high_loss_indices)
                        }
        
        return results
    
    def generate_fault_report(self) -> dict:
        """生成故障报告"""
        bursts = self.detect_burst_loss()
        periodic = self.detect_periodic_loss()
        
        return {
            'sample_count': len(self.packet_logs),
            'burst_losses': bursts[-5:],  # 最近 5 次
            'periodic_patterns': periodic,
            'overall_loss_rate': round(
                np.mean([p['loss_rate'] for p in self.packet_logs[-self.window_size:]]), 4
            ) if self.packet_logs else 0,
            'recommendation': self._get_recommendation(bursts, periodic)
        }
    
    def _get_recommendation(self, bursts, periodic) -> str:
        if periodic.get('loss_ge_5%', {}).get('detected'):
            return "检测到周期性丢包，可能是 QoS 策略、带宽限速或网络设备轮询导致。建议检查流量整形配置。"
        elif len(bursts) > 3:
            return "检测到多次突发丢包，可能是网络拥塞或链路不稳定。建议联系 ISP 排查物理链路质量。"
        elif self.overall_loss_rate > 0.01:
            return "存在持续低级别丢包，建议启用 TCP 快速重传和优化 MTU 设置。"
        return "丢包率在正常范围内，无需干预。"
```

### 6.2 AI 增强模式识别

```python
# fault_pattern_recognition.py
def recognize_fault_pattern(fault_data: dict) -> dict:
    """AI 识别故障模式"""
    
    prompt = f"""你是网络故障诊断专家。根据以下故障数据，识别故障模式并给出诊断。

【丢包统计】
- 总体丢包率: {fault_data.get('overall_loss_rate', 0):.2%}
- 突发丢包次数: {len(fault_data.get('burst_losses', []))}
- 周期性模式: {json.dumps(fault_data.get('periodic_patterns', {}))}

【网络上下文】
- 最近变更: ["DNS 服务器切换", "内核升级", "安全组规则更新"]
- 关联告警: ["CPU 使用率升高", "内存压力"]

请输出 JSON:
{{
  "pattern_type": "qos_throttling|congestion|link_instability|dns_pollution|firewall_intervention",
  "confidence": 0.85,
  "analysis": "详细分析",
  "next_steps": ["步骤1", "步骤2"]
}}"""
    
    # 调用 LLM...
    pass
```

---

## 七、自动修复闭环

AI 诊断的价值不仅在于发现问题，更在于自动修复。以下是常见网络问题的自动修复流程。

### 7.1 修复决策引擎

```python
# auto_remediation.py
from enum import Enum
import subprocess
import json

class RemediationAction(Enum):
    DNS_SWITCH = "dns_switch"           # 切换 DNS
    FLUSH_CACHE = "flush_cache"         # 清空缓存
    TCP_TUNING = "tcp_tuning"           # TCP 参数调优
    BBR_ENABLE = "bbr_enable"           # 启用 BBR 拥塞控制
    MTU_ADJUST = "mtu_adjust"           # MTU 调整
    ROUTE_FIX = "route_fix"             # 路由修复
    FIREWALL_RULE = "firewall_rule"     # 防火墙规则修正
    SERVICE_RESTART = "service_restart" # 重启服务

class AutoRemediationEngine:
    """自动修复引擎"""
    
    def __init__(self):
        self.action_log = []
    
    def execute_remediation(self, diagnosis: dict) -> dict:
        """根据诊断结果执行自动修复"""
        results = []
        
        for issue in diagnosis.get('issues', []):
            action = self._match_action(issue)
            if action:
                result = self._run_action(action, issue)
                results.append(result)
        
        return {
            'remediation_results': results,
            'success_count': sum(1 for r in results if r['success']),
            'failed_count': sum(1 for r in results if not r['success'])
        }
    
    def _match_action(self, issue: dict) -> RemediationAction | None:
        """将问题映射到修复动作"""
        issue_type = issue.get('type', '')
        
        mappings = {
            'dns_failure': RemediationAction.DNS_SWITCH,
            'dns_poisoning': RemediationAction.DNS_SWITCH,
            'high_retransmit': RemediationAction.BBR_ENABLE,
            'tcp_congestion': RemediationAction.TCP_TUNING,
            'mtu_mismatch': RemediationAction.MTU_ADJUST,
            'route_lost': RemediationAction.ROUTE_FIX,
            'firewall_block': RemediationAction.FIREWALL_RULE,
        }
        
        return mappings.get(issue_type)
    
    def _run_action(self, action: RemediationAction, issue: dict) -> dict:
        """执行修复动作"""
        result = {'action': action.value, 'success': False, 'output': ''}
        
        try:
            if action == RemediationAction.DNS_SWITCH:
                output = self._switch_dns(issue)
                result['success'] = 'nameserver' in output.lower() or 'success' in output.lower()
            
            elif action == RemediationAction.BBR_ENABLE:
                output = self._enable_bbr()
                result['success'] = 'bbr' in output
            
            elif action == RemediationAction.TCP_TUNING:
                output = self._tune_tcp()
                result['success'] = True
            
            elif action == RemediationAction.MTU_ADJUST:
                output = self._adjust_mtu(issue)
                result['success'] = True
            
            result['output'] = output
            
        except Exception as e:
            result['error'] = str(e)
        
        self.action_log.append({
            'action': action.value,
            'timestamp': __import__('datetime').datetime.now().isoformat(),
            'success': result['success']
        })
        
        return result
    
    def _switch_dns(self, issue: dict) -> str:
        """切换到备用 DNS"""
        # 实际场景中应读取配置的 DNS 备选列表
        commands = [
            'echo "nameserver 1.1.1.1" > /tmp/resolv.conf.new',
            'echo "nameserver 8.8.8.8" >> /tmp/resolv.conf.new',
            'cp /etc/resolv.conf /etc/resolv.conf.bak',
            'cp /tmp/resolv.conf.new /etc/resolv.conf',
            'systemctl restart systemd-resolved 2>/dev/null || systemctl restart networking 2>/dev/null'
        ]
        outputs = []
        for cmd in commands:
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            outputs.append(r.stdout + r.stderr)
        return '\n'.join(outputs)
    
    def _enable_bbr(self) -> str:
        """启用 BBR 拥塞控制"""
        cmd = 'sysctl -w net.ipv4.tcp_congestion_control=bbr && modprobe tcp_bbr'
        return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout
    
    def _tune_tcp(self) -> str:
        """TCP 参数调优"""
        cmds = [
            'sysctl -w net.ipv4.tcp_tw_reuse=1',
            'sysctl -w net.ipv4.tcp_max_syn_backlog=4096',
            'sysctl -w net.core.somaxconn=4096',
            'sysctl -w net.ipv4.tcp_rmem="4096 87380 16777216"',
            'sysctl -w net.ipv4.tcp_wmem="4096 65536 16777216"'
        ]
        outputs = []
        for cmd in cmds:
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            outputs.append(r.stdout.strip())
        return '\n'.join(outputs)
    
    def _adjust_mtu(self, issue: dict) -> str:
        """MTU 调整"""
        # 智能 MTU 探测
        target = issue.get('mtu_target', 1460)
        cmd = f'ip link set dev eth0 mtu {target}'
        return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout
    
    def verify_remediation(self, original_diagnosis: dict) -> dict:
        """验证修复效果"""
        # 重新采集指标，对比修复前后
        # 简化示例：
        return {
            'verified': True,
            'before': original_diagnosis.get('metrics', {}),
            'after': {},  # 重新采集的结果
            'improvement': '指标已恢复正常'
        }
```

### 7.2 修复效果验证与回滚

```python
# remediation_verifier.py
def verify_and_rollback(diagnosis: dict, remediation_result: dict, 
                        pre_fix_baseline: dict) -> dict:
    """验证修复效果，必要时回滚"""
    
    # 重新采集指标
    post_fix_metrics = collect_network_metrics()
    
    # 对比分析
    improvements = {}
    for metric in ['retransmit_rate', 'avg_rtt', 'packet_loss_rate']:
        before = pre_fix_baseline.get(metric, 0)
        after = post_fix_metrics.get(metric, 0)
        if before > 0:
            change = (before - after) / before * 100
            improvements[metric] = round(change, 2)
    
    # 判断是否需要回滚
    needs_rollback = any(v < -10 for v in improvements.values())  # 任何指标恶化超过 10%
    
    if needs_rollback:
        rollback_result = execute_rollback(diagnosis)
        return {
            'status': 'rolled_back',
            'reason': '修复后指标恶化',
            'rollback_output': rollback_result
        }
    
    return {
        'status': 'success',
        'improvements': improvements,
        'auto_rollback_triggered': False
    }
```

---

## 八、完整部署方案

### 8.1 Docker Compose 编排

```yaml
# docker-compose.yml
version: '3.8'

services:
  network-diagnostic-agent:
    image: selfvps/network-diag:latest
    container_name: vps-network-diag
    privileged: true
    volumes:
      - ./config:/app/config
      - ./logs:/app/logs
      - ./data:/app/data
    environment:
      - LLM_ENDPOINT=http://ollama:11434
      - LLM_MODEL=qwen2.5:7b
      - ALERT_CHANNEL=telegram
      - TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
      - TELEGRAM_CHAT_ID=${TELEGRAM_CHAT_ID}
    restart: unless-stopped
    networks:
      - diag-network

  ollama:
    image: ollama/ollama:latest
    container_name: vps-ollama
    volumes:
      - ollama_data:/root/.ollama
    ports:
      - "11434:11434"
    restart: unless-stopped
    networks:
      - diag-network

  # 可选：时序数据库用于长期存储
  timescaledb:
    image: timescale/timescaledb:latest-pg15
    container_name: vps-timescaledb
    environment:
      - POSTGRES_PASSWORD=${DB_PASSWORD}
    volumes:
      - tsdata:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    restart: unless-stopped
    networks:
      - diag-network

volumes:
  ollama_data:
  tsdata:

networks:
  diag-network:
    driver: bridge
```

### 8.2 定时诊断任务

```bash
# cron 配置：每 5 分钟执行一次轻量诊断，每小时执行一次深度诊断
*/5 * * * * /opt/network-diag/diagnostic.sh --quick >> /var/log/vps-net-diag.log 2>&1
0 * * * * /opt/network-diag/diagnostic.sh --full >> /var/log/vps-net-diag.log 2>&1
```

### 8.3 报警配置

```python
# alert_config.py
ALERT_RULES = {
    'dns_failure': {
        'condition': 'dns_resolution_failures > 3 in 5min',
        'severity': 'critical',
        'channels': ['telegram', 'email'],
        'auto_remediate': True
    },
    'high_retransmit': {
        'condition': 'tcp_retransmit_rate > 5% for 10min',
        'severity': 'warning',
        'channels': ['telegram'],
        'auto_remediate': True
    },
    'route_instability': {
        'condition': 'bgp_route_changes > 5 in 10min',
        'severity': 'critical',
        'channels': ['telegram', 'sms'],
        'auto_remediate': False  # BGP 变更需人工确认
    },
    'intermittent_loss': {
        'condition': 'packet_loss_rate > 1% with periodic pattern',
        'severity': 'warning',
        'channels': ['telegram'],
        'auto_remediate': True
    }
}
```

---

## 九、实战案例：一次 AI 诊断的发现之旅

### 场景：用户反馈网站 intermittently 慢，但 ping 正常

**第一步：AI 自动发现异常**
```
[2026-09-14 03:15:00] ⚠️  DNS 诊断异常
  - 本地 DNS (223.5.5.5): example.com → 1.2.3.4 (TTL=300)
  - Google DNS (8.8.8.8): example.com → 5.6.7.8 (TTL=3600)
  - Cloudflare DNS (1.1.1.1): example.com → 1.2.3.4 (TTL=300)
  → 检测到 DNS 分歧！可能原因：GSLB 调度 / DNS 缓存污染
```

**第二步：AI 深入分析 TCP 质量**
```
[2026-09-14 03:15:05] 🔍 TCP 质量分析
  - 重传率: 0.8% (基线: 0.1%) ⬆️ 8x
  - 平均 RTT: 45ms (基线: 25ms) ⬆️ 80%
  - 最小窗口: 2920 bytes (正常: 65535)
  → 检测到窗口收缩异常，疑似拥塞控制问题
```

**第三步：AI 生成修复建议**
```json
{
  "root_cause": "ISP 路径拥塞导致 TCP 窗口收缩 + DNS 解析分歧",
  "recommendations": [
    {
      "priority": 1,
      "action": "启用 BBR 拥塞控制算法",
      "command": "sysctl -w net.ipv4.tcp_congestion_control=bbr",
      "expected_improvement": "预计降低 RTT 30-50%, 减少重传"
    },
    {
      "priority": 2,
      "action": "切换 DNS 上游至 1.1.1.1",
      "command": "echo 'nameserver 1.1.1.1' > /etc/resolv.conf",
      "expected_improvement": "消除 DNS 解析分歧"
    }
  ],
  "confidence": 0.92
}
```

**第四步：自动执行修复 + 验证**
```
✅ 执行: 启用 BBR 拥塞控制
✅ 执行: 切换 DNS 上游
✅ 验证: 重传率降至 0.1% (改善 87.5%)
✅ 验证: RTT 降至 28ms (改善 37.8%)
✅ 验证: DNS 解析一致，所有服务器返回相同结果
→ 问题已解决，已记录到知识库
```

---

## 十、总结与展望

AI 驱动的 VPS 智能网络诊断系统，将传统依赖经验的"排障艺术"转变为数据驱动的"诊断科学"。核心价值体现在：

| 维度 | 传统方式 | AI 驱动方式 |
|------|---------|------------|
| 发现速度 | 用户报障后数小时 | 实时监测，秒级发现 |
| 定位精度 | 逐层排查，容易遗漏 | 多维度交叉分析，精准定位 |
| 修复效率 | 人工操作，容易出错 | 自动执行，效果可验证 |
| 知识积累 | 个人经验，难以传承 | 知识图谱，持续进化 |

**未来演进方向**：
- 融合边缘计算，实现分布式网络诊断节点
- 引入强化学习，自动优化诊断策略和修复参数
- 与 CI/CD 系统集成，实现变更前的网络影响预评估
- 支持多云环境，跨 provider 统一诊断

---

*本文配套代码仓库：https://github.com/selfvps/network-diagnostic-agent*

*下篇预告：《AI 驱动的 VPS 智能密钥管理与自动化轮转》*
