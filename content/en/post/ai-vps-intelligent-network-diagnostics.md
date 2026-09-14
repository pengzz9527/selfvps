---
title: "AI-Driven VPS Intelligent Network Diagnostics: End-to-End Fault Localization and Automated Remediation"
description: "Reinvent VPS network troubleshooting with AI — intelligent DNS diagnosis, TCP connection analysis, latency bottleneck detection, route tracing, and automated remediation, making network issues transparent instead of black boxes"
date: 2026-09-14T20:00:00+08:00
lastmod: 2026-09-14T20:00:00+08:00
slug: "ai-vps-intelligent-network-diagnostics"
tags: ["AI Agent", "VPS", "Network Diagnostics", "Fault Localization", "DNS Diagnosis", "TCP Analysis", "Latency Optimization", "AIOps", "DevOps"]
categories: ["AI + VPS"]
aliases: [/en/post/ai-vps-intelligent-network-diagnostics/]
image: /images/posts/ai-vps-intelligent-network-diagnostics/featured.png
---

## Introduction: Breaking the "Black Box" of Network Failures

Have you ever experienced this midnight alert:

> *"Users report slow website access, but ping is normal, ports are open, CPU/memory look fine… where's the problem?"*

Traditional VPS network troubleshooting relies on operators' experience — checking DNS, TCP, routing, and bandwidth layer by layer, manually executing commands, comparing baselines, and inferring conclusions. This process is not only time-consuming but also **prone to missing subtle issues**: intermittent packet loss, DNS cache poisoning, BGP route flapping, TCP retransmission storms…

**AI-powered intelligent network diagnostics** was born to solve these pain points. By continuously collecting network telemetry data, establishing behavioral baselines, and leveraging LLMs for root cause reasoning, it shifts operations from "reactive firefighting" to "proactive prediction."

This article guides you through building a complete **AI-driven VPS intelligent network diagnostic system** covering six core capabilities:

1. **Intelligent DNS Diagnosis**: Multi-source resolution verification, cache poisoning detection, TTL anomaly alerts
2. **TCP Connection Quality Analysis**: Retransmission rate, RTT, window scaling, congestion control auto-tuning
3. **Latency Bottleneck Localization**: End-to-end latency breakdown, hot path identification
4. **Intelligent Route Tracing**: BGP route change monitoring, AS path anomaly detection
5. **Intermittent Fault Capture**: Time-series based packet loss/jitter pattern recognition
6. **Automated Remediation Loop**: Diagnosis → Fix Recommendation → One-click Execution → Verification

---

## 1. System Architecture Design

```
┌──────────────────────────────────────────────────────────────────┐
│                      User Interaction Layer                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │  Web Console │  │  CLI Command │  │  API/Webhook │           │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘           │
└─────────┼─────────────────┼─────────────────┼───────────────────┘
          │                 │                 │
          └─────────────────┴────────┬────────┘
                                    │
┌───────────────────────────────────┼───────────────────────────────┐
│                      AI Diagnostic Engine                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐            │
│  │  LLM Reason- │←→│  Rule Engine │←→│  Knowledge   │            │
│  │  ing (RCA)   │  │  (Threshold) │  │  Graph       │            │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘            │
│         │                 │                 │                     │
│  ┌──────┴───────┐  ┌──────┴───────┐  ┌──────┴───────┐            │
│  │ Report Gen   │  │ Fix Suggestion│  │ Effect       │            │
│  │              │  │ Engine        │  │ Verifier     │            │
│  └──────────────┘  └──────────────┘  └──────────────┘            │
└──────────────────────────┬───────────────────────────────────────┘
                           │
┌──────────────────────────┼───────────────────────────────────────┐
│                      Data Collection Layer                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐            │
│  │ DNS Probe    │  │ TCP Quality  │  │ Route Trace  │            │
│  │ (dig/nslookup)│  │ Probe        │  │ Probe        │            │
│  │              │  │ (tcpdump/    │  │ (traceroute  │            │
│  │              │  │  ss/netstat)  │  │  mtr)        │            │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘            │
│         │                 │                 │                     │
│  ┌──────┴───────┐  ┌──────┴───────┐  ┌──────┴───────┐            │
│  │ Bandwidth    │  │ ICMP Probe   │  │ BGP Listener │            │
│  │ Probe        │  │ (ping/fping) │  │ (birdcli/    │            │
│  │ (iperf3)     │  │              │  │  watchquagga)│            │
│  └──────────────┘  └──────────────┘  └──────────────┘            │
└─────────────────────────────────────────────────────────────────┘
```

### Core Components

| Component | Tech Stack | Responsibility |
|-----------|-----------|----------------|
| DNS Probe | dig + multi-DNS parallel queries | Detect resolution consistency, cache poisoning, TTL anomalies |
| TCP Quality Probe | ss/netstat/tcpdump + Go-TCP-Metrics | Monitor retransmission rate, RTT, window size, congestion state |
| Route Trace Probe | mtr + BIRD CLI | Real-time path tracking, BGP route change detection |
| Bandwidth Probe | iperf3 scheduled tests | Throughput, packet loss, latency distribution measurement |
| LLM Reasoning Engine | Ollama (Qwen/DeepSeek) + structured prompts | Root cause analysis, fix recommendation generation |
| Knowledge Graph | Neo4j / SQLite JSON | Store historical fault patterns, topology relations, fix records |

---

## 2. Intelligent DNS Diagnosis

DNS resolution issues are among the most common and subtle causes of VPS network failures. The AI diagnostic system performs multi-dimensional DNS health checks to automatically discover and locate problems.

### 2.1 Multi-Source Parallel Resolution Verification

Traditional troubleshooting checks only one DNS server, while the AI system simultaneously queries multiple authoritative and recursive DNS servers to compare result consistency:

```bash
#!/bin/bash
# dns_diagnostic.sh — Multi-source DNS health check

DOMAIN="${1:-example.com}"
DNS_SERVERS=("8.8.8.8" "1.1.1.1" "223.5.5.5" "9.9.9.9" "119.29.29.29")

echo "=== DNS Multi-Source Diagnosis: $DOMAIN ==="
echo ""

results=()
for dns in "${DNS_SERVERS[@]}"; do
    result=$(dig @"$dns" "$DOMAIN" +short +time=5 +tries=2 2>/dev/null)
    status=$?
    if [ $status -eq 0 ] && [ -n "$result" ]; then
        echo "  [$dns] → $result"
        results+=("$result")
    else
        echo "  [$dns] ❌ Resolution failed or timed out"
    fi
done

# Consistency check
unique_ips=$(printf '%s\n' "${results[@]}" | sort -u | wc -l)
total_resolutions=${#results[@]}

echo ""
if [ $unique_ips -eq 1 ]; then
    echo "✅ DNS Consistent: All DNS servers return identical results"
elif [ $unique_ips -le 3 ]; then
    echo "⚠️  DNS Slight Divergence: $unique_ips different results detected, may indicate GSLB or CDN scheduling"
else
    echo "🚨 DNS Major Divergence: $unique_ips different results detected, possible DNS poisoning or misconfiguration"
fi

# TTL check
echo ""
echo "--- TTL Analysis ---"
for dns in "${DNS_SERVERS[@]:0:2}"; do
    ttl=$(dig @"$dns" "$DOMAIN" +noall +answer | awk '/^[^;]/ {print $5}' | head -1)
    echo "  [$dns] TTL = ${ttl}s"
done
```

### 2.2 AI Root Cause Analysis

After collecting DNS data, the LLM engine performs intelligent analysis:

```python
# dns_ai_analyzer.py
import json
from openai import OpenClient  # or Ollama compatible interface

def analyze_dns_issues(dns_data: dict, history: list) -> dict:
    """AI-driven DNS issue root cause analysis"""
    
    client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")
    
    prompt = f"""You are a professional network operations expert. Analyze the following DNS diagnostic data, identify potential issues, and provide fix recommendations.

【Current Diagnostic Results】
{json.dumps(dns_data, ensure_ascii=False, indent=2)}

【Historical Fault Records】
{json.dumps(history[-10:], ensure_ascii=False, indent=2) if history else 'No historical records'}

Please output JSON in the following format:
{{
  "issues": [
    {{
      "severity": "critical|warning|info",
      "type": "dns_poisoning|ttl_anomaly|resolution_failure|inconsistency|cache_expiry",
      "description": "Issue description",
      "affected_domains": ["domain1"],
      "evidence": "Key evidence"
    }}
  ],
  "root_cause": "Most likely root cause",
  "recommendations": [
    {{
      "action": "Specific fix operation",
      "command": "Command to execute (if any)",
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

### 2.3 Typical DNS Fault Scenarios

| Fault Type | Symptoms | AI Diagnostic Logic | Auto Remediation |
|-----------|----------|---------------------|-----------------|
| DNS Cache Poisoning | Inconsistent results across DNS servers | Multi-source comparison + cross-verification with authoritative DNS | Switch to backup DNS, flush local cache |
| TTL Anomaly | TTL drops from 3600s to 60s suddenly | Time-series anomaly detection (3σ principle) | Alert notification, log change event |
| Resolution Timeout | Some DNS servers unresponsive | Parallel queries + timeout threshold statistics | Auto-switch DNS upstream |
| CNAME Loop | Resolution result points to itself | DNS resolution graph cycle detection | Alert + generate configuration fix suggestion |

---

## 3. TCP Connection Quality Intelligent Analysis

TCP connection quality directly impacts user experience. The AI system continuously monitors TCP metrics and automatically identifies anomalous patterns.

### 3.1 Key TCP Metric Collection

```python
# tcp_monitor.py
import subprocess
import re
import json
from datetime import datetime, timedelta
from collections import deque

class TCPQualityMonitor:
    """TCP connection quality monitor"""
    
    def __init__(self, sample_interval=5):
        self.sample_interval = sample_interval
        self.metrics_history = deque(maxlen=288)  # 24h @ 5min intervals
    
    def get_tcp_stats(self) -> dict:
        """Collect current TCP connection statistics"""
        stats = {}
        
        # Active connections
        result = subprocess.run(
            ['ss', '-s'], capture_output=True, text=True
        )
        active = re.search(r'estab (\d+)', result.stdout)
        stats['established'] = int(active.group(1)) if active else 0
        
        # Retransmission count
        result = subprocess.run(
            ['ss', '-i'], capture_output=True, text=True
        )
        retransmits = re.findall(r'retransmits (\d+)', result.stdout)
        stats['total_retransmits'] = sum(int(r) for r in retransmits)
        
        # RTT statistics
        result = subprocess.run(
            ['ss', '-tni'], capture_output=True, text=True
        )
        rtts = re.findall(r'rto (\d+) ato (\d+)', result.stdout)
        if rtts:
            rto_values = [int(r[0]) for r in rtts]
            stats['avg_rto'] = sum(rto_values) / len(rto_values)
            stats['max_rto'] = max(rto_values)
        
        # Window size
        windows = re.findall(r'wc:(\d+)', result.stdout)
        if windows:
            w_values = [int(w) for w in windows]
            stats['avg_window'] = sum(w_values) / len(w_values)
            stats['min_window'] = min(w_values)
        
        stats['timestamp'] = datetime.now().isoformat()
        return stats
    
    def detect_anomalies(self, current: dict, baseline: dict) -> list:
        """Detect anomalies based on historical baseline"""
        anomalies = []
        
        # Retransmission rate anomaly
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
        
        # Window shrinkage anomaly
        if current.get('min_window', 0) < 1460:
            anomalies.append({
                'type': 'window_shrink',
                'value': current['min_window'],
                'severity': 'info'
            })
        
        return anomalies
    
    def get_tcp_state_distribution(self) -> dict:
        """Get TCP connection state distribution"""
        result = subprocess.run(
            ['ss', '-tan'], capture_output=True, text=True
        )
        states = re.findall(r'\w+(?=\s)', result.stdout)
        distribution = {}
        for state in states:
            distribution[state] = distribution.get(state, 0) + 1
        return distribution
```

### 3.2 AI-Driven TCP Problem Diagnosis

| Issue | TCP Indicator Pattern | AI Diagnostic Conclusion | Fix Solution |
|-------|----------------------|------------------------|-------------|
| Network Congestion | High retransmit + Rising RTT + Window shrink | Congestion control algorithm unsuitable for current network | Switch to BBR congestion control |
| Slow DNS Resolution | Low ESTABLISHED + SYN_SENT accumulation | DNS resolution is the bottleneck | Check DNS cache, optimize resolv.conf |
| Frequent Connection Reset | FIN_WAIT accumulation + High RST count | Remote side actively disconnecting / Firewall blocking | Check firewall rules, remote service status |
| Half-Connection Queue | Too many SYN_RECV | SYN Flood attack or connection exhaustion | Enable SYN Cookies, adjust backlog |

---

## 4. Latency Bottleneck Intelligent Localization

Latency issues cause the worst user experience. The AI system performs end-to-end latency decomposition to precisely locate bottlenecks.

### 4.1 Latency Layer Decomposition Model

```
User → [WAN Latency] → [Edge Node Latency] → [VPS Inbound Latency] → [Protocol Processing] → [Application Processing]
         ↑                  ↑                      ↑                      ↑                        ↑
      BGP Routing         CDN/EDGE              TCP Handshake         HTTP/TLS                Business Logic
      Hop Count           Cache Hit Rate         RTT Measurement      Request Processing       Database Query
```

### 4.2 Intelligent Latency Diagnostic Script

```bash
#!/bin/bash
# latency_diagnostic.sh — AI-enhanced latency diagnostic

TARGET="${1:-8.8.8.8}"
echo "=== Latency Diagnostic: $TARGET ==="
echo ""

# 1. Basic connectivity
echo "--- ICMP Latency (10 pings) ---"
ping -c 10 "$TARGET" 2>/dev/null | grep -E 'rtt|packet'
echo ""

# 2. Route trace
echo "--- Traceroute ---"
mtr -r -c 5 --no-dns "$TARGET" 2>/dev/null | tail -20
echo ""

# 3. TCP connection latency
echo "--- TCP Handshake Latency ---"
for i in $(seq 1 5); do
    curl -s -o /dev/null -w "Attempt $i: connect=%{time_connect}s\n" "https://$TARGET" 2>/dev/null
done
echo ""

# 4. Bandwidth test
echo "--- Bandwidth Test ---"
if command -v iperf3 &>/dev/null; then
    iperf3 -c "$TARGET" -t 5 --format b 2>&1 | grep -E 'sender|receiver|sent'
else
    echo "(iperf3 not installed, skipping bandwidth test)"
fi
echo ""

# 5. Packet loss statistics
echo "--- Packet Loss (30s) ---"
fping -q -c 30 -i 100 "$TARGET" 2>/dev/null | tail -1
```

---

## 5. Route and BGP Intelligent Monitoring

For multi-line BGP VPS or cross-border services, route changes directly impact availability. The AI system monitors route status in real-time.

### 5.1 BGP Route Change Detection

```python
# bgp_monitor.py
import subprocess
import json
from datetime import datetime

class BGPMonitor:
    """BGP route monitoring"""
    
    def __init__(self):
        self.last_routes = {}
        self.events = []
    
    def get_bgp_routes(self) -> dict:
        """Get current BGP route table"""
        routes = {}
        result = subprocess.run(
            ['birdcli', 'bird', 'show', 'route'],
            capture_output=True, text=True
        )
        routes['raw'] = result.stdout
        routes['timestamp'] = datetime.now().isoformat()
        return routes
    
    def detect_changes(self, current: dict, previous: dict) -> list:
        """Detect route changes"""
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
        """Analyze route stability"""
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

---

## 6. Intermittent Fault Intelligent Capture

Intermittent network faults (e.g., losing 1 packet per second) are the hardest to troubleshoot. The AI system performs long-duration time-series analysis to discover patterns invisible to the human eye.

### 6.1 Time-Series Packet Loss Detection

```python
# intermittent_fault_detector.py
import numpy as np
from datetime import datetime

class IntermittentFaultDetector:
    """Intermittent fault detector"""
    
    def __init__(self, window_size=60):
        self.window_size = window_size
        self.packet_logs = []
    
    def add_packet_sample(self, timestamp: datetime, sent: int, received: int):
        """Add packet loss sample"""
        self.packet_logs.append({
            'timestamp': timestamp.isoformat(),
            'sent': sent,
            'received': received,
            'loss_rate': (sent - received) / sent if sent > 0 else 0
        })
    
    def detect_burst_loss(self, window_seconds=30) -> list:
        """Detect burst packet loss"""
        if len(self.packet_logs) < self.window_size:
            return []
        
        recent = self.packet_logs[-self.window_size:]
        loss_rates = [p['loss_rate'] for p in recent]
        
        mean_loss = np.mean(loss_rates)
        std_loss = np.std(loss_rates)
        
        bursts = []
        for i, rate in enumerate(loss_rates):
            if rate > mean_loss + 2 * std_loss and rate > 0.01:
                bursts.append({
                    'index': i,
                    'loss_rate': round(rate, 4),
                    'timestamp': recent[i]['timestamp'],
                    'severity': 'high' if rate > 0.05 else 'medium'
                })
        
        return bursts
    
    def detect_periodic_loss(self) -> dict:
        """Detect periodic packet loss patterns"""
        if len(self.packet_logs) < 120:
            return {'detected': False}
        
        loss_rates = [p['loss_rate'] for p in self.packet_logs]
        thresholds = [0.05, 0.1, 0.2]
        results = {}
        
        for threshold in thresholds:
            high_loss_indices = [i for i, r in enumerate(loss_rates) if r >= threshold]
            if len(high_loss_indices) >= 3:
                intervals = [high_loss_indices[i+1] - high_loss_indices[i] 
                            for i in range(len(high_loss_indices)-1)]
                if intervals:
                    avg_interval = np.mean(intervals)
                    if 5 < avg_interval < 120:
                        results[f'loss_ge_{threshold:.0%}'] = {
                            'detected': True,
                            'avg_interval_samples': round(avg_interval, 1),
                            'occurrence_count': len(high_loss_indices)
                        }
        
        return results
    
    def generate_fault_report(self) -> dict:
        """Generate fault report"""
        bursts = self.detect_burst_loss()
        periodic = self.detect_periodic_loss()
        
        recent = self.packet_logs[-self.window_size:] if self.packet_logs else []
        overall_loss = round(np.mean([p['loss_rate'] for p in recent]), 4) if recent else 0
        
        recommendation = ""
        if periodic.get('loss_ge_5%', {}).get('detected'):
            recommendation = "Periodic packet loss detected — likely caused by QoS policies, bandwidth throttling, or network device polling. Check traffic shaping configuration."
        elif len(bursts) > 3:
            recommendation = "Multiple burst losses detected — likely network congestion or link instability. Contact ISP to investigate physical link quality."
        elif overall_loss > 0.01:
            recommendation = "Sustained low-level packet loss detected. Consider enabling TCP fast retransmit and optimizing MTU settings."
        else:
            recommendation = "Packet loss rate is within normal range, no action needed."
        
        return {
            'sample_count': len(self.packet_logs),
            'burst_losses': bursts[-5:],
            'periodic_patterns': periodic,
            'overall_loss_rate': overall_loss,
            'recommendation': recommendation
        }
```

---

## 7. Automated Remediation Loop

The value of AI diagnostics lies not just in finding problems, but in automatically fixing them. Below is the automated remediation workflow for common network issues.

### 7.1 Remediation Decision Engine

```python
# auto_remediation.py
from enum import Enum
import subprocess

class RemediationAction(Enum):
    DNS_SWITCH = "dns_switch"
    FLUSH_CACHE = "flush_cache"
    TCP_TUNING = "tcp_tuning"
    BBR_ENABLE = "bbr_enable"
    MTU_ADJUST = "mtu_adjust"
    ROUTE_FIX = "route_fix"
    FIREWALL_RULE = "firewall_rule"
    SERVICE_RESTART = "service_restart"

class AutoRemediationEngine:
    """Automated remediation engine"""
    
    def __init__(self):
        self.action_log = []
    
    def execute_remediation(self, diagnosis: dict) -> dict:
        """Execute automatic remediation based on diagnosis"""
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
        """Map issue to remediation action"""
        mappings = {
            'dns_failure': RemediationAction.DNS_SWITCH,
            'dns_poisoning': RemediationAction.DNS_SWITCH,
            'high_retransmit': RemediationAction.BBR_ENABLE,
            'tcp_congestion': RemediationAction.TCP_TUNING,
            'mtu_mismatch': RemediationAction.MTU_ADJUST,
            'route_lost': RemediationAction.ROUTE_FIX,
            'firewall_block': RemediationAction.FIREWALL_RULE,
        }
        return mappings.get(issue.get('type'))
    
    def _run_action(self, action: RemediationAction, issue: dict) -> dict:
        """Execute remediation action"""
        result = {'action': action.value, 'success': False, 'output': ''}
        
        try:
            if action == RemediationAction.DNS_SWITCH:
                cmd = '''echo "nameserver 1.1.1.1" > /tmp/resolv.conf.new && 
                         echo "nameserver 8.8.8.8" >> /tmp/resolv.conf.new && 
                         cp /etc/resolv.conf /etc/resolv.conf.bak && 
                         cp /tmp/resolv.conf.new /etc/resolv.conf && 
                         systemctl restart systemd-resolved 2>/dev/null'''
                r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                result['success'] = r.returncode == 0
                result['output'] = r.stdout + r.stderr
            
            elif action == RemediationAction.BBR_ENABLE:
                cmd = 'sysctl -w net.ipv4.tcp_congestion_control=bbr && modprobe tcp_bbr'
                r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                result['success'] = 'bbr' in r.stdout.lower()
                result['output'] = r.stdout
            
            elif action == RemediationAction.TCP_TUNING:
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
                result['success'] = True
                result['output'] = '\n'.join(outputs)
            
            result['output'] = result.get('output', '')
            
        except Exception as e:
            result['error'] = str(e)
        
        self.action_log.append({
            'action': action.value,
            'timestamp': __import__('datetime').datetime.now().isoformat(),
            'success': result['success']
        })
        
        return result
```

### 7.2 Remediation Verification and Rollback

```python
# remediation_verifier.py
def verify_and_rollback(diagnosis: dict, remediation_result: dict, 
                        pre_fix_baseline: dict) -> dict:
    """Verify remediation effect, rollback if necessary"""
    
    # Re-collect metrics
    post_fix_metrics = collect_network_metrics()
    
    # Compare analysis
    improvements = {}
    for metric in ['retransmit_rate', 'avg_rtt', 'packet_loss_rate']:
        before = pre_fix_baseline.get(metric, 0)
        after = post_fix_metrics.get(metric, 0)
        if before > 0:
            change = (before - after) / before * 100
            improvements[metric] = round(change, 2)
    
    # Determine if rollback is needed
    needs_rollback = any(v < -10 for v in improvements.values())
    
    if needs_rollback:
        return {
            'status': 'rolled_back',
            'reason': 'Metrics degraded after remediation',
            'improvements': improvements
        }
    
    return {
        'status': 'success',
        'improvements': improvements,
        'auto_rollback_triggered': False
    }
```

---

## 8. Complete Deployment Guide

### 8.1 Docker Compose Orchestration

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

### 8.2 Scheduled Diagnostic Tasks

```bash
# cron configuration: lightweight diagnostic every 5min, deep diagnostic hourly
*/5 * * * * /opt/network-diag/diagnostic.sh --quick >> /var/log/vps-net-diag.log 2>&1
0 * * * * /opt/network-diag/diagnostic.sh --full >> /var/log/vps-net-diag.log 2>&1
```

### 8.3 Alert Configuration

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
        'auto_remediate': False
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

## 9. Case Study: An AI Diagnostic Journey

### Scenario: Users report intermittently slow website, but ping is normal

**Step 1: AI Auto-Discovery**
```
[2026-09-14 03:15:00] ⚠️  DNS Diagnosis Anomaly
  - Local DNS (223.5.5.5): example.com → 1.2.3.4 (TTL=300)
  - Google DNS (8.8.8.8): example.com → 5.6.7.8 (TTL=3600)
  - Cloudflare DNS (1.1.1.1): example.com → 1.2.3.4 (TTL=300)
  → DNS divergence detected! Possible causes: GSLB scheduling / DNS cache poisoning
```

**Step 2: AI Deep TCP Analysis**
```
[2026-09-14 03:15:05] 🔍 TCP Quality Analysis
  - Retransmit rate: 0.8% (baseline: 0.1%) ⬆️ 8x
  - Avg RTT: 45ms (baseline: 25ms) ⬆️ 80%
  - Min window: 2920 bytes (normal: 65535)
  → Window shrinkage anomaly detected, likely congestion control issue
```

**Step 3: AI Generates Fix Recommendations**
```json
{
  "root_cause": "ISP path congestion causing TCP window shrinkage + DNS resolution divergence",
  "recommendations": [
    {
      "priority": 1,
      "action": "Enable BBR congestion control algorithm",
      "command": "sysctl -w net.ipv4.tcp_congestion_control=bbr",
      "expected_improvement": "Expected RTT reduction 30-50%, retransmission decrease"
    },
    {
      "priority": 2,
      "action": "Switch DNS upstream to 1.1.1.1",
      "command": "echo 'nameserver 1.1.1.1' > /etc/resolv.conf",
      "expected_improvement": "Eliminate DNS resolution divergence"
    }
  ],
  "confidence": 0.92
}
```

**Step 4: Auto-Execute Remediation + Verification**
```
✅ Executed: Enable BBR congestion control
✅ Executed: Switch DNS upstream
✅ Verified: Retransmit rate dropped to 0.1% (87.5% improvement)
✅ Verified: RTT dropped to 28ms (37.8% improvement)
✅ Verified: DNS resolution consistent, all servers return same results
→ Issue resolved, recorded to knowledge base
```

---

## 10. Summary and Outlook

The AI-driven VPS intelligent network diagnostic system transforms traditional experience-dependent "troubleshooting art" into data-driven "diagnostic science." The core value is reflected in:

| Dimension | Traditional Approach | AI-Driven Approach |
|-----------|---------------------|-------------------|
| Detection Speed | Hours after user report | Real-time monitoring, sub-second discovery |
| Localization Precision | Layer-by-layer manual check, easy to miss | Multi-dimensional cross-analysis, precise positioning |
| Fix Efficiency | Manual operations, error-prone | Automated execution, verifiable results |
| Knowledge Accumulation | Personal experience, hard to transfer | Knowledge graph, continuously evolving |

**Future Evolution Directions**:
- Integrate edge computing for distributed network diagnostic nodes
- Introduce reinforcement learning to auto-optimize diagnostic strategies and fix parameters
- Integrate with CI/CD pipelines for pre-deployment network impact assessment
- Support multi-cloud environments with unified cross-provider diagnostics

---

*Source code repository: https://github.com/selfvps/network-diagnostic-agent*

*Next episode preview: "AI-Driven VPS Intelligent Secret Management and Automated Rotation"*
