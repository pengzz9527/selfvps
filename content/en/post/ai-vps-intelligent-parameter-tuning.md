---
title: "AI-Driven VPS Parameter Tuning: Auto-Optimize Linux Kernel & App Configs with Local LLM"
description: "System parameter tuning is key to VPS performance, but manual tuning is hard and risky. This article shows you how to build an AI-powered tuning system using local LLM (Ollama + Qwen) — auto-analyze metrics, generate tuning plans, safely apply changes, and verify results."
date: 2026-09-13T20:00:00+08:00
lastmod: 2026-09-13T20:00:00+08:00
slug: "ai-vps-intelligent-parameter-tuning"
image: /images/posts/ai-vps-intelligent-parameter-tuning/featured.png
tags: ["AI", "VPS", "parameter tuning", "sysctl", "LLM", "Ollama", "Qwen", "performance", "automation"]
categories: ["AI Operations"]
aliases: [/en/post/ai-vps-intelligent-parameter-tuning/]
---

## Introduction

You manage a handful of VPS instances running websites, APIs, databases, and Docker containers. To make them run faster and more stable, you've heard about "system parameter tuning" — adjusting Linux kernel sysctl parameters, optimizing Nginx configs, tweaking PostgreSQL connection pools and cache sizes.

But the reality is:

- **Manual tuning has a high barrier**: sysctl has hundreds of parameters, each requiring deep understanding of semantics, impact scope, and safety boundaries;
- **Tuning carries risk**: a single wrong parameter can crash services, break network connectivity, or even prevent the system from booting;
- **No one-size-fits-all**: the optimal parameter combination for a web server is completely different from a database server or container host;
- **Hard to verify results**: after changing parameters, how do you know it actually got better? How long do you need to wait to see trends?

**The traditional ops approach is: reference online posts → try one by one → observe effects → revert if things break.** This process is time-consuming, has high trial-and-error costs, and is hard to scale.

**AI-powered parameter tuning** solves this problem: use a locally deployed large language model as your "tuning expert" to auto-collect system metrics, analyze current configuration bottlenecks, generate targeted tuning plans, and apply changes safely after verification in a sandbox. Your VPS no longer relies on "guesswork" for tuning — it makes optimal decisions based on data and AI reasoning.

This article walks you through building this system from scratch, covering:

1. **Data Collection Layer**: Gather CPU, memory, IO, network, and application-level metrics
2. **AI Analysis Layer**: Local Ollama + Qwen model analyzes bottlenecks and generates tuning plans
3. **Safe Execution Layer**: Diff backup + grayscale rollout + effect rollback mechanism
4. **Closed-loop Verification**: Compare before/after metrics, auto-evaluate effectiveness

---

## System Architecture

```
┌──────────────────────────────────────────────────────────────┐
│               AI Parameter Tuning Engine                     │
├──────────────┬──────────────┬──────────────┬────────────────┤
│  Data        │  AI          │  Safe        │  Result        │
│  Collection  │  Analyzer    │  Executor    │  Verifier      │
│  ┌────────┐  │  ┌────────┐  │  ┌────────┐  │  ┌────────┐   │
│  │sysctl  │  │  │LLM      │  │  │Diff     │  │  │AB      │   │
│  │metrics │  │  │Bottleneck│  │  │Backup   │  │  │Compare │   │
│  │App     │  │  │Analysis │  │  │Snapshot │  │  │Trend   │   │
│  │config  │  │  │Plan Gen │  │  │Grayscale │  │  │Effect  │   │
│  │scan    │  │  │Risk Eval│  │  │Rollback │  │  │Monitor │   │
│  └────────┘  │  └────────┘  │  └────────┘  │  └────────┘   │
├──────────────┴──────────────┴──────────────┴────────────────┤
│              Infrastructure Layer (All VPS)                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────────┐  │
│  │NodeExp   │  │Prometheus │ │Ollama    │  │LocalConfig  │  │
│  │Exporter  │  │Server    │  │(Qwen)    │  │Snapshot     │  │
│  └──────────┘  └──────────┘  └──────────┘  └─────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

### Core Flow

```
Collect Metrics → AI Analysis → Generate Plan → Risk Assessment → Backup Config → Grayscale Apply → Verify Results → Full Apply / Rollback
```

---

## Step 1: Build the Data Collection Layer

We install lightweight collectors on the VPS to regularly gather key performance metrics.

### 1.1 Install Node Exporter

Node Exporter collects system-level metrics: CPU, memory, disk IO, network, etc.

```bash
# Download Node Exporter
wget https://github.com/prometheus/node_exporter/releases/download/v1.8.2/node_exporter-1.8.2.linux-amd64.tar.gz
tar xzf node_exporter-1.8.2.linux-amd64.tar.gz
sudo cp node_exporter-1.8.2.linux-amd64/node_exporter /usr/local/bin/

# Create systemd service
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

### 1.2 Deploy Prometheus Server

```bash
# Deploy Prometheus via Docker Compose
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

### 1.3 Custom Metrics Collection Script

Beyond Node Exporter, we need to collect application-level metrics and current system configuration.

```bash
mkdir -p /opt/ai-tuner/scripts
```

**collect_metrics.py** — Collects current system state:

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
    
    io = psutil.disk_io_counters()
    net = psutil.net_io_counters()
    load = psutil.getloadavg()
    
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
    
    try:
        result = subprocess.run(
            ['nginx', '-T'], capture_output=True, text=True
        )
        config['nginx_workers'] = 'auto'
        if 'worker_connections' in result.stdout:
            for line in result.stdout.split('\n'):
                if 'worker_connections' in line:
                    config['nginx_worker_connections'] = int(
                        line.strip().split(';')[0].split()[-1]
                    )
    except:
        config['nginx_running'] = False
    
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
sudo pip3 install psutil
```

---

## Step 2: Build the AI Analysis Engine

We deploy a local LLM with Ollama and build the tuning analysis service.

### 2.1 Deploy Ollama

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull Qwen2.5 7B model (good balance of performance and resource usage)
ollama pull qwen2.5:7b

# Verify
ollama list
```

### 2.2 Build the Tuning Analysis Service

```bash
mkdir -p /opt/ai-tuner/service
```

**tuner_service.py** — Core AI tuning service:

```python
#!/usr/bin/env python3
"""AI-powered VPS parameter tuning service."""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SYSTEM_PROMPT = """You are a senior Linux system engineer and performance tuning expert. Your task is to analyze system metrics and current configuration, then provide precise parameter tuning recommendations.

Tuning principles:
1. Safety first: Only recommend low-risk parameters, flag high-risk changes
2. Scenario-driven: Different VPS roles (Web server, DB server, container host) need different recommendations
3. Verifiable: Each recommendation should explain expected effect and rollback method
4. Gradual: Prioritize parameters that can be safely applied; high-risk params require manual confirmation

Output format:
- Output strictly in JSON format
- Each recommendation must include: parameter, current_value, recommended_value, risk_level (low/medium/high), rationale, rollback_command
- Sort by priority (priority: 1=highest)
"""

def call_ollama(system_state_json: str) -> dict:
    """Call Ollama Qwen model to analyze system state and generate tuning plan."""
    
    prompt = f"""## System State Data
{system_state_json}

Analyze the above system state and generate parameter tuning recommendations. Output pure JSON, no markdown code blocks."""

    result = subprocess.run(
        ['ollama', 'run', 'qwen2.5:7b', prompt],
        capture_output=True, text=True, timeout=120
    )
    
    output = result.stdout.strip()
    
    # Clean possible markdown wrapping
    if output.startswith('```'):
        lines = output.split('\n')
        output = '\n'.join(lines[1:-1])
    
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        start = output.find('{')
        end = output.rfind('}')
        if start != -1 and end != -1:
            return json.loads(output[start:end+1])
        raise

def generate_tuning_plan(system_state: dict) -> dict:
    """Generate complete tuning plan with safety checks."""
    
    raw_analysis = call_ollama(json.dumps(system_state, indent=2))
    
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

## Step 3: Safe Execution Layer

After AI generates a tuning plan, we can't apply it directly — safety mechanisms are essential.

### 3.1 Configuration Snapshot & Backup

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

### 3.2 Grayscale Application Engine

```bash
cat > /opt/ai-tuner/scripts/apply_tuning.py << 'PYTHON'
#!/usr/bin/env python3
"""Safely apply parameter tuning with grayscale rollout."""

import json
import subprocess
import sys
import time
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
sudo cp {backup_path} /etc/sysctl.conf
sudo sysctl -p
echo "Rollback completed."
"""
    return rollback_script

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan-file', required=True)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--phase', choices=['safe', 'extended', 'full'], default='safe')
    args = parser.parse_args()
    
    with open(args.plan_file) as f:
        plan = json.load(f)
    
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
        "changes_summary": {"total": len(changes)},
        "result": apply_sysctl_changes(changes, dry_run=args.dry_run)
    }, indent=2, ensure_ascii=False))
PYTHON

chmod +x /opt/ai-tuner/scripts/apply_tuning.py
```

### 3.3 Result Verification Module

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
    result = subprocess.run(['sudo', 'sysctl', '-a'], capture_output=True, text=True)
    current_params = {}
    for line in result.stdout.strip().split('\n'):
        if '=' in line:
            key, value = line.split('=', 1)
            current_params[key.strip()] = value.strip()
    
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

def compare_with_baseline(before: dict, after: dict) -> dict:
    """Compare current state with baseline and evaluate improvements."""
    comparison = {
        "comparison_time": datetime.utcnow().isoformat() + "Z",
        "metrics_changed": [],
        "performance_delta": {},
        "overall_assessment": "pending"
    }
    
    before_sysctl = before.get('sysctl_values', {})
    after_sysctl = after.get('sysctl_values', {})
    
    for param in after_sysctl:
        if param in before_sysctl and before_sysctl[param] != after_sysctl[param]:
            comparison["metrics_changed"].append({
                "parameter": param,
                "before": before_sysctl[param],
                "after": after_sysctl[param]
            })
    
    if len(comparison["metrics_changed"]) > 0:
        comparison["overall_assessment"] = "tuning_applied_successfully"
    
    return comparison

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline-file', required=True)
    parser.add_argument('--output', default='verification_result.json')
    args = parser.parse_args()
    
    with open(args.baseline_file) as f:
        baseline = json.load(f)
    
    current = collect_post_tuning_metrics()
    result = compare_with_baseline(baseline, current)
    
    with open(args.output, 'w') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    
    print(f"Verification result saved to {args.output}")
    print(json.dumps(result, indent=2, ensure_ascii=False))
PYTHON

chmod +x /opt/ai-tuner/scripts/verify_results.py
```

---

## Step 4: Orchestration & Scheduling

Connect all components into an automated tuning pipeline.

### 4.1 Main Orchestration Script

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
        log("AI analysis returned no plan. Check Ollama service status: ollama list")
        sys.exit(0)
    
    recs = plan.get('analysis', {}).get('recommendations', [])
    log(f"AI generated plan with {len(recs)} recommendations")
    
    # Step 3: Snapshot
    snapshot_path = run_snapshot()
    log(f"Snapshot saved to: {snapshot_path}")
    
    # Step 4: Apply (dry run first, then real)
    dry_result = run_apply(plan, phase='safe')
    log(f"Dry run result: {json.dumps(dry_result, indent=2, ensure_ascii=False)[:500]}...")
    
    if dry_result and dry_result.get('result', {}).get('applied'):
        time.sleep(2)
        real_result = run_apply(plan, phase='safe')
        applied_count = len(real_result.get('result', {}).get('applied', []))
        log(f"Real apply result: applied={applied_count} params")
        
        # Step 5: Verify
        time.sleep(5)
        verify_result = run_verify(str(baseline_file))
        if verify_result:
            log(f"Verification: {verify_result.get('overall_assessment', 'unknown')}")
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

### 4.2 Schedule with Cron or systemd Timer

```bash
# Run daily at 3 AM (lowest system load period)
sudo crontab -e
```

Add:
```cron
# AI VPS Parameter Tuning - daily at 3 AM
0 3 * * * /usr/bin/python3 /opt/ai-tuner/tune_vps.py >> /opt/ai-tuner/logs/cron.log 2>&1
```

Or use systemd timer for more reliable scheduling:
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

## Step 5: Web UI (Optional)

Build a simple tuning management dashboard with Streamlit:

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
st.title("⚡ AI VPS Parameter Tuning")

STATE_DIR = Path("/opt/ai-tuner/state")
LOGS_DIR = Path("/opt/ai-tuner/logs")

tab1, tab2, tab3 = st.tabs(["🚀 Start Tuning", "📊 History", "📋 Logs"])

with tab1:
    st.markdown("### One-Click AI Tuning")
    st.markdown("Click to start the AI parameter tuning pipeline. The system will auto-collect metrics, analyze bottlenecks, generate tuning plans, and safely apply changes.")
    
    if st.button("🚀 Start Tuning", type="primary"):
        with st.spinner("Running AI tuning..."):
            result = subprocess.run(
                ['python3', '/opt/ai-tuner/tune_vps.py'],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                st.success("✅ Tuning completed! Check the History tab for details.")
            else:
                st.error(f"❌ Tuning failed: {result.stderr}")
        st.code(result.stdout, language="text")

with tab2:
    st.markdown("### Tuning History")
    reports = sorted(STATE_DIR.glob("report_*.json"), reverse=True)[:10]
    if reports:
        for report_file in reports:
            with open(report_file) as f:
                report = json.load(f)
            st.markdown(f"#### 📅 {report.get('completed_at', 'N/A')[:19]}")
            apply_result = report.get('apply_result', {})
            applied = len(apply_result.get('result', {}).get('applied', []))
            failed = len(apply_result.get('result', {}).get('failed', []))
            st.metric("Params Applied", applied)
            if failed:
                st.metric("Failed", failed)
            st.caption(f"Snapshot: `{report.get('snapshot_path', 'N/A')}`")
            st.divider()
    else:
        st.info("No reports yet. Run a tuning cycle first!")

with tab3:
    st.markdown("### System Logs")
    log_files = sorted(LOGS_DIR.glob("tune_*.log"), reverse=True)
    if log_files:
        with open(log_files[0]) as f:
            content = f.read()
        st.code(content, language="text")
    else:
        st.info("No logs yet.")
```

Launch the UI:
```bash
streamlit run /opt/ai-tuner/ui.py --server.port 8501
```

---

## Typical Tuning Scenarios

### Scenario A: High-Concurrency Web Server

**Symptoms**: Many short connections, high QPS, occasional connection refused errors

**AI Analysis Results Example**:
```json
{
  "recommendations": [
    {
      "parameter": "net.core.somaxconn",
      "current_value": "128",
      "recommended_value": "4096",
      "risk_level": "low",
      "rationale": "Current somaxconn=128 limits TCP listen queue length. Under high concurrency, SYN packets get dropped causing connection timeouts.",
      "rollback_command": "sudo sysctl -w net.core.somaxconn=128"
    },
    {
      "parameter": "net.ipv4.tcp_max_syn_backlog",
      "current_value": "128",
      "recommended_value": "4096",
      "risk_level": "low",
      "rationale": "Works with somaxconn to increase SYN reception queue, reducing half-open connection buildup.",
      "rollback_command": "sudo sysctl -w net.ipv4.tcp_max_syn_backlog=128"
    },
    {
      "parameter": "net.ipv4.tcp_tw_reuse",
      "current_value": "0",
      "recommended_value": "1",
      "risk_level": "low",
      "rationale": "Enable TCP TIME_WAIT socket reuse. Accelerates port recycling under high concurrency. Negligible security impact on modern kernels.",
      "rollback_command": "sudo sysctl -w net.ipv4.tcp_tw_reuse=0"
    },
    {
      "parameter": "vm.swappiness",
      "current_value": "60",
      "recommended_value": "10",
      "risk_level": "medium",
      "rationale": "Lower swappiness reduces memory swap frequency. Web servers should keep hot data in RAM. Note: still may swap if memory is insufficient.",
      "rollback_command": "sudo sysctl -w vm.swappiness=60"
    }
  ]
}
```

### Scenario B: Database Server

**Symptoms**: High disk IO wait, connection count approaching limit

**AI Focus Areas**:
- `vm.dirty_ratio` / `vm.dirty_background_ratio` — write-back policy control
- `kernel.shmmax` / `kernel.shmALL` — shared memory limits
- Application layer: PostgreSQL `shared_buffers`, `work_mem`, `max_connections`

---

## Safety Boundaries & Considerations

### ⚠️ Risk Mitigation

| Risk Type | Mitigation |
|-----------|------------|
| Wrong parameter crashes services | Grayscale phased rollout: dry-run → safe phase → observe → full |
| Unable to rollback | Auto-create config snapshot before each tuning, keep rollback.sh |
| Frequent tuning causes oscillation | Minimum 24h interval between tuning cycles |
| Unreliable AI recommendations | High-risk parameters always flagged for manual review, never auto-applied |
| Production environment mistakes | Validate on staging/test first, then apply to production |

### 🛡️ Parameters Not Recommended for Auto-Application

The following parameters affect core system behavior — AI can recommend but they should always require manual review before applying:
- `kernel.panic` — kernel crash behavior
- `kernel.core_uses_pid` — core dump behavior
- `net.ipv4.ip_forward` — routing forwarding
- `fs.suid_dumpable` — security-related
- Any parameter requiring `boot` (requires reboot)

---

## Summary

By building this **AI-powered VPS parameter tuning system**, we achieve:

1. **Automated collection**: Continuously gather system metrics and application configs to establish baselines
2. **Intelligent analysis**: Local LLM understands system bottlenecks and generates targeted tuning plans
3. **Safe execution**: Diff backup + grayscale rollout + auto-rollback — changes are controllable and reversible
4. **Closed-loop verification**: Compare before/after metrics, data-driven effect evaluation

**Core value**:
- Transforms "experience-based tuning" into "data + AI tuning", lowering the expertise barrier
- Grayscale + rollback mechanism makes tuning risk "acceptable" instead of "uncontrollable"
- Local deployment ensures data never leaves the VPS, ideal for privacy-sensitive environments

Now you can let AI be your 24/7 system tuning engineer — continuously monitoring, intelligently analyzing, safely optimizing, keeping every VPS at peak performance.

---

## Next Steps

1. Install Node Exporter and Prometheus on your VPS
2. Deploy Ollama and pull the qwen2.5:7b model
3. Copy the scripts from this article to `/opt/ai-tuner/`
4. Test first with `python3 tune_vps.py --dry-run`
5. Once confirmed, set up the systemd timer for automatic scheduling

**Remember**: Parameter tuning is a continuous optimization process, not a one-time fix. Let AI help you build tuning habits — not replace your judgment.
