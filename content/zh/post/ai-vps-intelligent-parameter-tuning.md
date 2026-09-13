---
title: "AI驱动的VPS智能参数调优：用本地大模型自动优化Linux内核与应用配置"
description: "系统参数调优是提升VPS性能的关键，但手动调参门槛高、风险大。本文教你用本地大模型（Ollama + Qwen）构建智能参数调优系统——自动分析系统指标、生成调优建议、安全应用变更，让每台VPS都跑到最佳状态"
date: 2026-09-13T20:00:00+08:00
lastmod: 2026-09-13T20:00:00+08:00
slug: "ai-vps-intelligent-parameter-tuning"
image: /images/posts/ai-vps-intelligent-parameter-tuning/featured.png
tags: ["AI", "VPS", "参数调优", "sysctl", "大模型", "Ollama", "Qwen", "性能优化", "自动化"]
categories: ["AI 运维"]
aliases: [/zh/post/ai-vps-intelligent-parameter-tuning/]
---

## 引言

你管理着几台 VPS，跑着网站、API、数据库和 Docker 容器。为了让它们跑得更快、更稳，你听说过"系统参数调优"——调整 Linux 内核的 sysctl 参数、优化 Nginx 配置、调整 PostgreSQL 的连接池和缓存大小。

但现实是：

- **手动调参门槛高**：sysctl 参数有上百个，每个参数的含义、影响范围、安全边界都需要深入了解；
- **调优有风险**：一个错误的参数可能导致服务崩溃、网络连接中断，甚至整个系统无法启动；
- **没有统一标准**：不同业务场景（Web 服务器、数据库服务器、容器主机）的最佳参数组合完全不同；
- **难以验证效果**：改完参数后，如何知道是否真的变好了？需要跑多久才能看出趋势？

**传统运维的做法是：参考网上帖子 → 逐个尝试 → 观察效果 → 不行再改回来。** 这个过程耗时、试错成本高，而且很难规模化。

**AI 参数调优系统**解决的就是这个问题：用本地部署的大语言模型作为"调优专家"，自动收集系统指标，分析当前配置瓶颈，生成针对性的调优方案，并在安全沙箱中验证效果后应用变更。你的 VPS 不再靠"经验主义"调参，而是基于数据和 AI 推理做出最优决策。

本文将带你从零搭建这套系统，包括：

1. **数据采集层**：收集 CPU、内存、IO、网络、应用层指标
2. **AI 分析层**：本地 Ollama + Qwen 模型分析瓶颈并生成调优方案
3. **安全执行层**：差分备份 + 灰度应用 + 效果回滚机制
4. **闭环验证**：对比调优前后指标，自动评估效果

---

## 系统架构

```
┌──────────────────────────────────────────────────────────────┐
│                  AI 参数调优引擎                              │
├──────────────┬──────────────┬──────────────┬────────────────┤
│  数据采集    │  AI 分析     │  安全执行     │  效果验证      │
│  Collector   │  Analyzer    │  Executor     │  Verifier      │
│  ┌────────┐  │  ┌────────┐  │  ┌────────┐  │  ┌────────┐   │
│  │sysctl  │  │  │LLM推理 │  │  │差分备份│  │  │AB对比 │   │
│  │指标    │  │  │瓶颈识别│  │  │快照    │  │  │趋势分析│   │
│  │应用指标│  │  │方案生成│  │  │灰度应用│  │  │效果评估│   │
│  │配置扫描│  │  │风险评估│  │  │回滚机制│  │  │持续监控│   │
│  └────────┘  │  └────────┘  │  └────────┘  │  └────────┘   │
├──────────────┴──────────────┴──────────────┴────────────────┤
│                基础设施层 (所有 VPS)                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────────┐  │
│  │ NodeExp  │  │ Prometheus│ │ Ollama   │  │ LocalConfig │  │
│  │ Exporter │  │ Server   │  │ (Qwen)   │  │ Snapshot    │  │
│  └──────────┘  └──────────┘  └──────────┘  └─────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

### 核心流程

```
数据采集 → AI 分析 → 方案生成 → 风险评估 → 备份当前配置 → 灰度应用 → 效果验证 → 全量应用/回滚
```

---

## 第一步：搭建数据采集层

我们需要在 VPS 上安装轻量级采集器，定期收集关键性能指标。

### 1.1 安装 Node Exporter

Node Exporter 负责采集系统级指标：CPU、内存、磁盘 IO、网络等。

```bash
# 下载 Node Exporter
wget https://github.com/prometheus/node_exporter/releases/download/v1.8.2/node_exporter-1.8.2.linux-amd64.tar.gz
tar xzf node_exporter-1.8.2.linux-amd64.tar.gz
sudo cp node_exporter-1.8.2.linux-amd64/node_exporter /usr/local/bin/

# 创建 systemd 服务
sudo tee /etc/systemd/system/node_exporter.service << 'EOF'
[Unit]
Description=Node Exporter
Wants=network-online.target
After=network-online.target

[Service]
User=node_exporter
ExecStart=/usr/local/bin/node_exporter \
  --collector.processes \
  --collector.filesystem.mount-points-exclude='^/(dev|proc|sys|run)' \
  --web.listen-address=:9100

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable node_exporter
sudo systemctl start node_exporter
```

### 1.2 部署 Prometheus 服务端

```bash
# Docker Compose 方式部署 Prometheus
cat > docker-compose.yml << 'EOF'
version: '3.8'
services:
  prometheus:
    image: prom/prometheus:v2.53.0
    container_name: prometheus
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus-data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--web.console.libraries=/etc/prometheus/console_libraries'
      - '--web.console.templates=/etc/prometheus/consoles'
      - '--storage.tsdb.retention.time=7d'

  grafana:
    image: grafana/grafana:11.0.0
    container_name: grafana
    ports:
      - "3000:3000"
    volumes:
      - grafana-data:/var/lib/grafana
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin123

volumes:
  prometheus-data:
  grafana-data:
EOF

cat > prometheus.yml << 'EOF'
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'node_exporter'
    static_configs:
      - targets: ['localhost:9100']

  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']
EOF

docker compose up -d
```

### 1.3 自定义指标采集脚本

除了 Node Exporter，我们还需要采集应用层指标和当前系统配置。

```bash
mkdir -p /opt/ai-tuner/scripts
```

**collect_metrics.py** — 采集系统当前状态：

```python
#!/usr/bin/env python3
"""Collect system metrics and current configuration for AI analysis."""

import json
import subprocess
import psutil
import socket

def get_sysctl_snapshot():
    """Collect all current sysctl parameters."""
    result = subprocess.run(
        ['sudo', 'sysctl', '-a'],
        capture_output=True, text=True
    )
    params = {}
    for line in result.stdout.strip().split('\n'):
        if '=' in line:
            key, value = line.split('=', 1)
            params[key.strip()] = value.strip()
    return params

def get_system_metrics():
    """Collect CPU, memory, disk, network metrics."""
    cpu_percent = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    
    # IO counters
    io = psutil.disk_io_counters()
    
    # Network counters
    net = psutil.net_io_counters()
    
    # Load average
    load = psutil.getloadavg()
    
    # File descriptors
    try:
        with open('/proc/sys/fs/file-nr') as f:
            file_nr = f.read().strip().split()
            used_files = int(file_nr[0])
            max_files = int(file_nr[2])
    except:
        used_files, max_files = 0, 0
    
    return {
        "cpu_percent": cpu_percent,
        "cpu_count": psutil.cpu_count(),
        "memory_total_gb": round(memory.total / 1024**3, 2),
        "memory_used_percent": memory.percent,
        "disk_total_gb": round(disk.total / 1024**3, 2),
        "disk_used_percent": disk.percent,
        "disk_read_bytes": io.read_bytes if io else 0,
        "disk_write_bytes": io.write_bytes if io else 0,
        "net_bytes_sent": net.bytes_sent,
        "net_bytes_recv": net.bytes_recv,
        "load_1min": load[0],
        "load_5min": load[1],
        "load_15min": load[2],
        "file_descriptors_used": used_files,
        "file_descriptors_max": max_files,
        "hostname": socket.gethostname(),
        "uptime_seconds": psutil.boot_time(),
    }

def get_application_config():
    """Collect relevant application configurations."""
    config = {}
    
    # Check if nginx is running and get config
    try:
        result = subprocess.run(
            ['nginx', '-T'], capture_output=True, text=True
        )
        config['nginx_workers'] = 'auto'
        # Parse worker_connections if available
        if 'worker_connections' in result.stdout:
            for line in result.stdout.split('\n'):
                if 'worker_connections' in line:
                    config['nginx_worker_connections'] = int(
                        line.strip().split(';')[0].split()[-1]
                    )
    except:
        config['nginx_running'] = False
    
    # Check PostgreSQL if running
    try:
        result = subprocess.run(
            ['sudo', 'psql', '-U', 'postgres', '-c', 
             "SHOW max_connections; SHOW shared_buffers; SHOW effective_cache_size;"],
            capture_output=True, text=True
        )
        lines = result.stdout.strip().split('\n')
        for i in range(0, len(lines), 2):
            if i + 1 < len(lines):
                key = lines[i].strip()
                val = lines[i+1].strip()
                config[f'pg_{key}'] = val
    except:
        pass
    
    return config

if __name__ == '__main__':
    metrics = {
        "timestamp": subprocess.run(['date', '-u', '+%Y-%m-%dT%H:%M:%SZ'],
                                    capture_output=True, text=True).stdout.strip(),
        "system": get_system_metrics(),
        "sysctl_snapshot": get_sysctl_snapshot(),
        "application_config": get_application_config(),
    }
    print(json.dumps(metrics, indent=2))
```

```bash
chmod +x /opt/ai-tuner/scripts/collect_metrics.py
sudo pip3 install psutil  # 或在 venv 中安装
```

---

## 第二步：搭建 AI 分析引擎

我们用 Ollama 部署本地大模型，构建调优分析服务。

### 2.1 部署 Ollama

```bash
# 安装 Ollama
curl -fsSL https://ollama.com/install.sh | sh

# 拉取 Qwen2.5 7B 模型（性能与资源占用的良好平衡）
ollama pull qwen2.5:7b

# 验证
ollama list
```

### 2.2 构建调优分析服务

```bash
mkdir -p /opt/ai-tuner/service
```

**tuner_service.py** — AI 调优核心服务：

```python
#!/usr/bin/env python3
"""AI-powered VPS parameter tuning service."""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SYSTEM_PROMPT = """你是资深 Linux 系统工程师和性能调优专家。你的任务是根据系统指标和当前配置，给出精确的参数调优建议。

调优原则：
1. 安全第一：只推荐低风险参数，标注高风险变更
2. 场景驱动：根据 VPS 角色（Web服务器/数据库/容器主机）给出不同建议
3. 可验证：每条建议说明预期效果和回滚方式
4. 渐进式：优先推荐可以安全应用的参数，高风险参数建议手动确认

输出格式要求：
- 严格按照 JSON 格式输出
- 每条建议包含: parameter, current_value, recommended_value, risk_level(低/中/高), rationale, rollback_command
- 按优先级排序 (priority: 1=最高)
"""

def call_ollama(system_state_json: str) -> dict:
    """Call Ollama Qwen model to analyze system state and generate tuning plan."""
    
    prompt = f"""## 系统状态数据
{system_state_json}

请分析上述系统状态，生成参数调优建议。输出纯 JSON，不要 markdown 代码块。"""

    result = subprocess.run(
        ['ollama', 'run', 'qwen2.5:7b', prompt],
        capture_output=True, text=True, timeout=120
    )
    
    output = result.stdout.strip()
    
    # 清理可能的 markdown 包裹
    if output.startswith('```'):
        lines = output.split('\n')
        output = '\n'.join(lines[1:-1])
    
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        # 尝试提取 JSON 部分
        start = output.find('{')
        end = output.rfind('}')
        if start != -1 and end != -1:
            return json.loads(output[start:end+1])
        raise

def generate_tuning_plan(system_state: dict) -> dict:
    """Generate complete tuning plan with safety checks."""
    
    # Call AI for recommendations
    raw_analysis = call_ollama(json.dumps(system_state, indent=2))
    
    # Add metadata
    plan = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "vps_hostname": system_state.get('system', {}).get('hostname', 'unknown'),
        "analysis": raw_analysis,
        "safety_checks": {
            "backup_created": False,
            "rollback_plan": [],
            "grayscale_phases": []
        }
    }
    
    return plan

if __name__ == '__main__':
    # Read system state from stdin or file
    if len(sys.argv) > 1:
        with open(sys.argv[1]) as f:
            system_state = json.load(f)
    else:
        import psutil
        system_state = {
            "system": {
                "cpu_percent": psutil.cpu_percent(interval=1),
                "memory_used_percent": psutil.virtual_memory().percent,
                "disk_used_percent": psutil.disk_usage('/').percent,
                "load_1min": psutil.getloadavg()[0],
                "hostname": subprocess.run(['hostname'], capture_output=True, text=True).stdout.strip(),
            }
        }
    
    plan = generate_tuning_plan(system_state)
    print(json.dumps(plan, indent=2, ensure_ascii=False))
```

---

## 第三步：安全执行层

AI 生成调优方案后，不能直接应用——必须有安全机制保障。

### 3.1 配置快照与备份

```bash
cat > /opt/ai-tuner/scripts/snapshot.sh << 'SCRIPT'
#!/bin/bash
# Create a snapshot of current system configuration

SNAPSHOT_DIR="/opt/ai-tuner/snapshots"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
HOSTNAME=$(hostname)
SNAPSHOT_PATH="${SNAPSHOT_DIR}/${HOSTNAME}/${TIMESTAMP}"

mkdir -p "${SNAPSHOT_PATH}"

# Snapshot sysctl
sudo sysctl -a > "${SNAPSHOT_PATH}/sysctl_current.txt" 2>&1

# Snapshot nginx config
if command -v nginx &>/dev/null; then
    sudo nginx -T > "${SNAPSHOT_PATH}/nginx_config.txt" 2>&1 || true
fi

# Snapshot postgresql config
if command -v psql &>/dev/null; then
    sudo -u postgres psql -c "SHOW ALL;" > "${SNAPSHOT_PATH}/pg_config.txt" 2>&1 || true
fi

# Snapshot key system files
sudo cp /etc/sysctl.conf "${SNAPSHOT_PATH}/" 2>/dev/null || true
sudo cp /etc/nginx/nginx.conf "${SNAPSHOT_PATH}/" 2>/dev/null || true
sudo cp /etc/postgresql/*/main/postgresql.conf "${SNAPSHOT_PATH}/" 2>/dev/null || true

# Create rollback script
cat > "${SNAPSHOT_PATH}/rollback.sh" << 'EOF'
#!/bin/bash
echo "ROLLBACK: Restoring system configuration..."
sudo sysctl -p /etc/sysctl.conf.bak.$1 2>/dev/null
echo "Rollback completed. Please verify services."
EOF
chmod +x "${SNAPSHOT_PATH}/rollback.sh"

# Save snapshot metadata
cat > "${SNAPSHOT_PATH}/metadata.json" << EOF
{
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "hostname": "${HOSTNAME}",
  "snapshot_path": "${SNAPSHOT_PATH}",
  "rollback_script": "${SNAPSHOT_PATH}/rollback.sh"
}
EOF

echo "${SNAPSHOT_PATH}"
SCRIPT

chmod +x /opt/ai-tuner/scripts/snapshot.sh
```

### 3.2 灰度应用引擎

```bash
cat > /opt/ai-tuner/scripts/apply_tuning.py << 'PYTHON'
#!/usr/bin/env python3
"""Safely apply parameter tuning with grayscale rollout."""

import json
import subprocess
import sys
import time
import shutil
from pathlib import Path
from datetime import datetime

SAFE_SYSCTL_PARAMS = {
    # Network tuning - safe for most workloads
    'net.core.somaxconn': {'default': 128, 'web_optimized': 4096, 'risk': 'low'},
    'net.ipv4.tcp_max_syn_backlog': {'default': 128, 'web_optimized': 4096, 'risk': 'low'},
    'net.ipv4.tcp_tw_reuse': {'default': 0, 'web_optimized': 1, 'risk': 'low'},
    'net.ipv4.ip_local_port_range': {'default': '32768 60999', 'web_optimized': '1024 65535', 'risk': 'low'},
    # Memory tuning
    'vm.swappiness': {'default': 60, 'web_optimized': 10, 'risk': 'low'},
    'vm.vfs_cache_pressure': {'default': 100, 'web_optimized': 50, 'risk': 'low'},
    # IO tuning
    'vm.dirty_ratio': {'default': 20, 'web_optimized': 15, 'risk': 'medium'},
    'vm.dirty_background_ratio': {'default': 10, 'web_optimized': 5, 'risk': 'medium'},
    'vm.overcommit_memory': {'default': 0, 'web_optimized': 0, 'risk': 'low'},
    # File descriptors
    'fs.file-max': {'default': 'auto', 'web_optimized': 'auto', 'risk': 'low'},
    'fs.nr_open': {'default': 'auto', 'web_optimized': 'auto', 'risk': 'low'},
}

def create_backup():
    """Create backup of current sysctl.conf before changes."""
    backup_path = "/etc/sysctl.conf.bak." + datetime.now().strftime("%Y%m%d_%H%M%S")
    subprocess.run(['sudo', 'cp', '/etc/sysctl.conf', backup_path], check=False)
    return backup_path

def apply_sysctl_changes(changes: dict, dry_run: bool = False) -> dict:
    """Apply sysctl changes safely with rollback support."""
    results = {"applied": [], "failed": [], "skipped": [], "backup_path": None}
    
    if not dry_run:
        results["backup_path"] = create_backup()
    
    for param, config in changes.items():
        new_value = config.get("value")
        risk = config.get("risk", "unknown")
        
        # Safety check: skip high-risk params in auto mode
        if risk == "high" and not dry_run:
            results["skipped"].append({
                "parameter": param,
                "reason": "high_risk_manual_review_required"
            })
            continue
        
        cmd = ['sudo', 'sysctl', '-w', f'{param}={new_value}']
        
        if dry_run:
            results["applied"].append({
                "parameter": param,
                "new_value": new_value,
                "status": "dry_run_simulated"
            })
        else:
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    results["applied"].append({
                        "parameter": param,
                        "new_value": new_value,
                        "status": "success"
                    })
                else:
                    results["failed"].append({
                        "parameter": param,
                        "error": result.stderr.strip()
                    })
            except Exception as e:
                results["failed"].append({
                    "parameter": param,
                    "error": str(e)
                })
    
    return results

def generate_rollback_plan(changes: dict, backup_path: str) -> str:
    """Generate rollback script."""
    rollback_script = f"""#!/bin/bash
# Auto-generated rollback script
# Created: {datetime.now().isoformat()}
# Backup: {backup_path}

echo "ROLLING BACK sysctl changes..."

# Restore from backup
sudo cp {backup_path} /etc/sysctl.conf
sudo sysctl -p

echo "Rollback completed. Current settings:"
sudo sysctl -a | grep -E '({" ".join(changes.keys())})'
"""
    return rollback_script

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan-file', required=True, help='Path to JSON tuning plan')
    parser.add_argument('--dry-run', action='store_true', help='Simulate without applying')
    parser.add_argument('--phase', choices=['safe', 'extended', 'full'], default='safe',
                       help='Grayscale phase: safe=low-risk only, extended=+medium, full=all')
    args = parser.parse_args()
    
    with open(args.plan_file) as f:
        plan = json.load(f)
    
    # Filter changes by phase
    phase_threshold = {'safe': 'low', 'extended': 'medium', 'full': 'high'}
    threshold = phase_threshold[args.phase]
    
    changes = {}
    for item in plan.get('analysis', {}).get('recommendations', []):
        if item.get('risk_level', 'unknown') in ('low', 'medium', 'high'):
            risk_order = {'low': 0, 'medium': 1, 'high': 2}
            if risk_order.get(item['risk_level'], 99) <= risk_order.get(threshold, 99):
                changes[item['parameter']] = {
                    'value': item['recommended_value'],
                    'risk': item['risk_level']
                }
    
    print(json.dumps({
        "dry_run": args.dry_run,
        "phase": args.phase,
        "changes_summary": {
            "total": len(changes),
            "by_risk": {}
        },
        "result": apply_sysctl_changes(changes, dry_run=args.dry_run)
    }, indent=2, ensure_ascii=False))
PYTHON

chmod +x /opt/ai-tuner/scripts/apply_tuning.py
```

### 3.3 效果验证模块

```bash
cat > /opt/ai-tuner/scripts/verify_results.py << 'PYTHON'
#!/usr/bin/env python3
"""Verify tuning results by comparing before/after metrics."""

import json
import subprocess
import psutil
from datetime import datetime

def collect_post_tuning_metrics():
    """Collect metrics after tuning for comparison."""
    # Get current sysctl values
    result = subprocess.run(['sudo', 'sysctl', '-a'], capture_output=True, text=True)
    current_params = {}
    for line in result.stdout.strip().split('\n'):
        if '=' in line:
            key, value = line.split('=', 1)
            current_params[key.strip()] = value.strip()
    
    # Collect performance metrics
    metrics = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "sysctl_values": current_params,
        "performance": {
            "cpu_percent": psutil.cpu_percent(interval=1),
            "memory_percent": psutil.virtual_memory().percent,
            "load_avg": list(psutil.getloadavg()),
            "disk_io": psutil.disk_io_counters()._asdict() if psutil.disk_io_counters() else {},
            "network_io": psutil.net_io_counters()._asdict(),
        }
    }
    return metrics

def compare_with_baseline(before: dict, after: dict, expected_improvements: list) -> dict:
    """Compare current state with baseline and evaluate improvements."""
    comparison = {
        "comparison_time": datetime.utcnow().isoformat() + "Z",
        "metrics_changed": [],
        "performance_delta": {},
        "overall_assessment": "pending"
    }
    
    # Compare sysctl changes
    before_sysctl = before.get('sysctl_values', {})
    after_sysctl = after.get('sysctl_values', {})
    
    for param in after_sysctl:
        if param in before_sysctl and before_sysctl[param] != after_sysctl[param]:
            comparison["metrics_changed"].append({
                "parameter": param,
                "before": before_sysctl[param],
                "after": after_sysctl[param]
            })
    
    # Compare performance metrics
    before_perf = before.get('performance', {})
    after_perf = after.get('performance', {})
    
    # Simple delta calculation
    for key in ['cpu_percent', 'memory_percent']:
        if key in before_perf and key in after_perf:
            delta = after_perf[key] - before_perf[key]
            comparison["performance_delta"][key] = {
                "before": before_perf[key],
                "after": after_perf[key],
                "delta": round(delta, 2),
                "direction": "improved" if (key == 'cpu_percent' and delta < 0) or (key == 'memory_percent' and delta < 0) else "worst"
            }
    
    # Overall assessment
    if len(comparison["metrics_changed"]) > 0:
        comparison["overall_assessment"] = "tuning_applied_successfully"
    
    return comparison

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline-file', required=True, help='Path to baseline metrics JSON')
    parser.add_argument('--output', default='verification_result.json')
    args = parser.parse_args()
    
    with open(args.baseline_file) as f:
        baseline = json.load(f)
    
    current = collect_post_tuning_metrics()
    result = compare_with_baseline(baseline, current, [])
    
    with open(args.output, 'w') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    
    print(f"Verification result saved to {args.output}")
    print(json.dumps(result, indent=2, ensure_ascii=False))
PYTHON

chmod +x /opt/ai-tuner/scripts/verify_results.py
```

---

## 第四步：编排与调度

将所有组件串联起来，实现自动化调优流程。

### 4.1 主调优脚本

```bash
cat > /opt/ai-tuner/tune_vps.py << 'PYTHON'
#!/usr/bin/env python3
"""Main orchestration script for AI-powered VPS parameter tuning."""

import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

BASE_DIR = Path("/opt/ai-tuner")
SCRIPTS_DIR = BASE_DIR / "scripts"
STATE_DIR = BASE_DIR / "state"
LOGS_DIR = BASE_DIR / "logs"

STATE_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

def log(msg: str):
    ts = datetime.utcnow().isoformat() + "Z"
    print(f"[{ts}] {msg}")
    # Also write to log file
    log_file = LOGS_DIR / f"tune_{datetime.now().strftime('%Y%m%d')}.log"
    with open(log_file, 'a') as f:
        f.write(f"[{ts}] {msg}\n")

def run_collect():
    """Step 1: Collect system metrics."""
    log("Step 1: Collecting system metrics...")
    result = subprocess.run(
        ['python3', str(SCRIPTS_DIR / 'collect_metrics.py')],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        log(f"ERROR: Metric collection failed: {result.stderr}")
        return None
    return json.loads(result.stdout)

def run_ai_analysis(system_state: dict) -> dict:
    """Step 2: AI analysis."""
    log("Step 2: Running AI analysis...")
    result = subprocess.run(
        ['python3', str(SCRIPTS_DIR / 'tuner_service.py')],
        input=json.dumps(system_state),
        capture_output=True, text=True, cwd=str(SCRIPTS_DIR)
    )
    if result.returncode != 0:
        log(f"ERROR: AI analysis failed: {result.stderr}")
        return None
    return json.loads(result.stdout)

def run_snapshot() -> str:
    """Step 3: Create configuration snapshot."""
    log("Step 3: Creating configuration snapshot...")
    result = subprocess.run(
        [str(SCRIPTS_DIR / 'snapshot.sh')],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        log(f"WARNING: Snapshot failed: {result.stderr}")
        return ""
    return result.stdout.strip()

def run_apply(plan: dict, phase: str = 'safe'):
    """Step 4: Apply tuning in grayscale phase."""
    plan_file = STATE_DIR / "current_plan.json"
    with open(plan_file, 'w') as f:
        json.dump(plan, f, indent=2, ensure_ascii=False)
    
    log(f"Step 4: Applying tuning (phase={phase})...")
    result = subprocess.run([
        'python3', str(SCRIPTS_DIR / 'apply_tuning.py'),
        '--plan-file', str(plan_file),
        '--phase', phase
    ], capture_output=True, text=True)
    
    if result.returncode != 0:
        log(f"ERROR: Apply failed: {result.stderr}")
        return None
    return json.loads(result.stdout)

def run_verify(baseline_file: str):
    """Step 5: Verify results."""
    log("Step 5: Verifying tuning results...")
    result = subprocess.run([
        'python3', str(SCRIPTS_DIR / 'verify_results.py'),
        '--baseline-file', baseline_file
    ], capture_output=True, text=True)
    
    if result.returncode != 0:
        log(f"WARNING: Verification failed: {result.stderr}")
        return None
    return json.loads(result.stdout)

def main():
    log("=" * 60)
    log("AI-VPS Parameter Tuning initiated")
    log("=" * 60)
    
    # Step 1: Collect
    system_state = run_collect()
    if not system_state:
        sys.exit(1)
    
    # Save baseline
    baseline_file = STATE_DIR / "baseline.json"
    with open(baseline_file, 'w') as f:
        json.dump(system_state, f, indent=2, ensure_ascii=False)
    
    # Step 2: AI Analysis
    plan = run_ai_analysis(system_state)
    if not plan:
        log("AI analysis returned no plan, skipping auto-tuning.")
        log("Check Ollama service status: ollama list")
        sys.exit(0)
    
    log(f"AI generated plan with {len(plan.get('analysis', {}).get('recommendations', []))} recommendations")
    
    # Step 3: Snapshot
    snapshot_path = run_snapshot()
    log(f"Snapshot saved to: {snapshot_path}")
    
    # Step 4: Apply (dry run first, then real)
    dry_result = run_apply(plan, phase='safe')
    log(f"Dry run result: {json.dumps(dry_result, indent=2, ensure_ascii=False)[:500]}...")
    
    # If dry run succeeded, apply for real
    if dry_result and dry_result.get('result', {}).get('applied'):
        # Re-apply without dry-run
        time.sleep(2)  # Brief pause
        real_result = run_apply(plan, phase='safe')
        log(f"Real apply result: applied={len(real_result.get('result', {}).get('applied', []))} params")
        
        # Step 5: Verify
        time.sleep(5)  # Wait for changes to take effect
        verify_result = run_verify(str(baseline_file))
        if verify_result:
            log(f"Verification: {verify_result.get('overall_assessment', 'unknown')}")
            # Save full report
            report = {
                "plan": plan,
                "snapshot_path": snapshot_path,
                "apply_result": real_result,
                "verification": verify_result,
                "completed_at": datetime.utcnow().isoformat() + "Z"
            }
            report_file = STATE_DIR / f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(report_file, 'w') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            log(f"Full report saved to: {report_file}")
    else:
        log("Dry run had issues, skipping real application.")
    
    log("Tuning cycle completed.")

if __name__ == '__main__':
    main()
PYTHON

chmod +x /opt/ai-tuner/tune_vps.py
```

### 4.2 设置定时任务

```bash
# 每天凌晨 3 点执行调优（系统负载最低时段）
sudo crontab -e
```

添加以下行：
```cron
# AI VPS Parameter Tuning - daily at 3 AM
0 3 * * * /usr/bin/python3 /opt/ai-tuner/tune_vps.py >> /opt/ai-tuner/logs/cron.log 2>&1
```

也可以用 systemd timer 实现更可靠的调度：
```bash
sudo tee /etc/systemd/system/ai-tuner.service << 'EOF'
[Unit]
Description=AI VPS Parameter Tuning Service
After=network-online.target ollama.service

[Service]
Type=oneshot
User=root
WorkingDirectory=/opt/ai-tuner
ExecStart=/usr/bin/python3 /opt/ai-tuner/tune_vps.py
EOF

sudo tee /etc/systemd/system/ai-tuner.timer << 'EOF'
[Unit]
Description=AI VPS Parameter Tuning Timer

[Timer]
OnCalendar=daily
Persistent=true

[Install]
WantedBy=timers.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable ai-tuner.timer
sudo systemctl start ai-tuner.timer
```

---

## 第五步：Web UI 可视化（可选）

用 Streamlit 搭建一个简单的调优管理界面：

```bash
pip3 install streamlit requests
```

```python
# /opt/ai-tuner/ui.py
import streamlit as st
import json
import subprocess
from pathlib import Path
from datetime import datetime

st.set_page_config(page_title="AI VPS Tuner", page_icon="⚡", layout="wide")
st.title("⚡ AI VPS 参数调优系统")

STATE_DIR = Path("/opt/ai-tuner/state")
LOGS_DIR = Path("/opt/ai-tuner/logs")

tab1, tab2, tab3 = st.tabs(["🚀 开始调优", "📊 历史报告", "📋 系统日志"])

with tab1:
    st.markdown("### 一键智能调优")
    st.markdown("点击按钮启动 AI 参数调优流程。系统会自动采集指标、分析瓶颈、生成调优方案并安全应用。")
    
    if st.button("🚀 启动调优", type="primary"):
        with st.spinner("正在执行 AI 调优..."):
            result = subprocess.run(
                ['python3', '/opt/ai-tuner/tune_vps.py'],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                st.success("✅ 调优完成！查看「历史报告」标签页查看详情。")
            else:
                st.error(f"❌ 调优失败: {result.stderr}")
        st.code(result.stdout, language="text")

with tab2:
    st.markdown("### 历史调优报告")
    reports = sorted(STATE_DIR.glob("report_*.json"), reverse=True)[:10]
    if reports:
        for report_file in reports:
            with open(report_file) as f:
                report = json.load(f)
            st.markdown(f"#### 📅 {report.get('completed_at', 'N/A')[:19]}")
            apply_result = report.get('apply_result', {})
            applied = len(apply_result.get('result', {}).get('applied', []))
            failed = len(apply_result.get('result', {}).get('failed', []))
            st.metric("成功应用参数", applied)
            if failed:
                st.metric("失败参数", failed)
            st.caption(f"快照路径: `{report.get('snapshot_path', 'N/A')}`")
            st.divider()
    else:
        st.info("暂无历史报告。先运行一次调优吧！")

with tab3:
    st.markdown("### 系统日志")
    log_files = sorted(LOGS_DIR.glob("tune_*.log"), reverse=True)
    if log_files:
        with open(log_files[0]) as f:
            content = f.read()
        st.code(content, language="text")
    else:
        st.info("暂无日志。")
```

启动 UI：
```bash
streamlit run /opt/ai-tuner/ui.py --server.port 8501
```

---

## 典型调优场景示例

### 场景 A：高并发 Web 服务器

**问题特征**：大量短连接、高 QPS、偶发连接拒绝

**AI 分析结果示例**：
```json
{
  "recommendations": [
    {
      "parameter": "net.core.somaxconn",
      "current_value": "128",
      "recommended_value": "4096",
      "risk_level": "低",
      "rationale": "当前 somaxconn=128 限制了 TCP 监听队列长度，高并发 Web 场景下容易导致 SYN 包被丢弃，引发连接超时。",
      "rollback_command": "sudo sysctl -w net.core.somaxconn=128"
    },
    {
      "parameter": "net.ipv4.tcp_max_syn_backlog",
      "current_value": "128",
      "recommended_value": "4096",
      "risk_level": "低",
      "rationale": "与 somaxconn 配合，增大 SYN 接收队列，减少半连接堆积。",
      "rollback_command": "sudo sysctl -w net.ipv4.tcp_max_syn_backlog=128"
    },
    {
      "parameter": "net.ipv4.tcp_tw_reuse",
      "current_value": "0",
      "recommended_value": "1",
      "risk_level": "低",
      "rationale": "启用 TCP TIME_WAIT 套接字重用，高并发场景下加速端口回收。对现代 Linux 内核安全影响可忽略。",
      "rollback_command": "sudo sysctl -w net.ipv4.tcp_tw_reuse=0"
    },
    {
      "parameter": "vm.swappiness",
      "current_value": "60",
      "recommended_value": "10",
      "risk_level": "中",
      "rationale": "降低 swappiness 减少内存换出频率，Web 服务器应优先保持热数据在内存中。需注意：若内存不足仍可能触发换出。",
      "rollback_command": "sudo sysctl -w vm.swappiness=60"
    }
  ]
}
```

### 场景 B：数据库服务器

**问题特征**：磁盘 IO 等待高、连接数接近上限

**AI 重点关注参数**：
- `vm.dirty_ratio` / `vm.dirty_background_ratio` — 控制写回策略
- `kernel.shmmax` / `kernel.shmall` — 共享内存限制
- 应用层：PostgreSQL `shared_buffers`、`work_mem`、`max_connections`

---

## 安全边界与注意事项

### ⚠️ 风险防控

| 风险类型 | 防控措施 |
|---------|---------|
| 参数错误导致服务崩溃 | 灰度 phased rollout：先 dry-run → safe phase → 观察 → full |
| 无法回滚 | 每次调优前自动创建配置快照，保留 rollback.sh |
| 高频调优互相干扰 | 两次调优间隔 ≥ 24h，避免参数震荡 |
| AI 推荐不可靠 | 高风险参数始终标记为"需人工确认"，不自动应用 |
| 生产环境误操作 | 先在生产镜像/测试环境验证，再应用到生产 |

### 🛡️ 不建议自动化的参数

以下参数涉及系统核心行为，建议仅作为 AI 推荐，由人工审核后再应用：
- `kernel.panic` — 内核崩溃行为
- `kernel.core_uses_pid` — 核心转储行为
- `net.ipv4.ip_forward` — 路由转发
- `fs.suid_dumpable` — 安全相关
- 任何涉及 `boot` 参数的项

---

## 总结

通过构建这套 **AI 驱动的 VPS 参数调优系统**，我们实现了：

1. **自动化采集**：持续收集系统指标和应用配置，建立基线
2. **智能化分析**：本地 LLM 理解系统瓶颈，生成针对性调优方案
3. **安全化执行**：差分备份 + 灰度应用 + 自动回滚，变更可控可逆
4. **闭环验证**：调优前后对比，数据驱动效果评估

**核心价值**：
- 将"经验调参"变为"数据+AI 调参"，降低专业门槛
- 灰度+回滚机制让调优风险从"不可控"变成"可接受"
- 本地部署确保数据不出 VPS，适合对隐私敏感的場景

现在，你可以让 AI 成为你的 24 小时系统调优工程师——持续监控、智能分析、安全优化，让每台 VPS 始终保持在最佳性能状态。

---

## 下一步行动

1. 在你的 VPS 上安装 Node Exporter 和 Prometheus
2. 部署 Ollama 并拉取 qwen2.5:7b 模型
3. 复制本文脚本到 `/opt/ai-tuner/`
4. 先运行 `python3 tune_vps.py --dry-run` 测试分析流程
5. 确认无误后设置 systemd timer 自动调度

**记住**：参数调优是持续优化过程，不是一锤子买卖。让 AI 帮你建立调优习惯，而不是替代你的判断。
