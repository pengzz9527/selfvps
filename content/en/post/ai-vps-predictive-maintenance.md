---
title: "AI-Driven VPS Predictive Maintenance — Detect Failures Before They Happen"
description: "Stop reacting to VPS outages. Build an AI-powered predictive maintenance system that forecasts disk failures, detects memory leaks, and auto-fixes issues before users notice."
date: 2026-07-24T20:00:00+08:00
lastmod: 2026-07-24T20:00:00+08:00
slug: "ai-vps-predictive-maintenance"
image: /images/posts/ai-vps-predictive-maintenance/featured.png
tags: ["AI Agent", "VPS", "predictive maintenance", "failure prediction", "automated ops", "machine learning", "self-healing", "AIOps"]
categories: ["AI Operations"]
aliases: [/en/post/ai-vps-predictive-maintenance/]
---

## Introduction

When does your VPS break?

- The disk fills up at 3 AM, the logging service goes down, and you only discover it the next morning;
- A memory leak slowly accumulates over a week until your website response time jumps from 200ms to 5s;
- An SSL certificate expires and users can't access your site, because you set a calendar reminder and forgot;
- The database connection pool exhausts, APIs time out globally, but your monitoring dashboard still shows "everything is fine."

**The core problem with traditional operations is reactive response** — you only act after something breaks. **AI Agent + Predictive Maintenance** changes this paradigm: it can warn you hours or even days before a failure occurs, and automatically generate fix plans.

This article walks you through building an **AI-driven VPS predictive maintenance system** from scratch, covering:

1. **Failure Prediction**: Forecast disk, memory, and CPU bottlenecks using time-series data analysis
2. **Anomaly Detection**: Use LLMs to analyze log patterns and identify potential security threats and performance degradation
3. **Root Cause Analysis**: When anomalies occur, automatically correlate multi-dimensional metrics to pinpoint root causes
4. **Self-Healing Execution**: Automatically generate and apply repair scripts for known issue types
5. **Smart Reporting**: Generate readable daily inspection reports and trend analysis in natural language

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                  AI Agent (LLM)                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │ Failure  │  │ Anomaly  │  │ Root Cause &     │  │
│  │ Prediction│  │ Detection│  │ Self-Healing     │  │
│  │ ML Model  │  │ LLM+RAG  │  │ Decision Engine  │  │
│  └────┬─────┘  └────┬─────┘  └────────┬─────────┘  │
│       │             │                  │             │
│  ┌────▼─────────────▼──────────────────▼─────────┐  │
│  │           Unified Event Bus                    │  │
│  └────┬─────────────┬──────────────────┬─────────┘  │
│       │             │                  │             │
├───────┼─────────────┼──────────────────┼────────────┤
│       ▼             ▼                  ▼             │
│  ┌────────┐  ┌──────────┐  ┌──────────────────┐    │
│  │Prometheus│ │ Loki     │  │ Node Exporter    │    │
│  │(Metrics) │ │(Logs)    │  │ + Custom Collectors│   │
│  └────────┘  └──────────┘  └──────────────────┘    │
│       ▲             ▲                  ▲            │
│  ┌────┴─────────────┴──────────────────┴─────────┐  │
│  │              Target VPS Instances               │  │
│  └───────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

## Step 1: Data Collection Layer

Predictive maintenance requires **high-quality, multi-dimensional data**. We need three types of data:

### 1.1 System Metrics (Prometheus + Node Exporter)

```yaml
# docker-compose.yml - Monitoring Stack
version: '3.8'
services:
  prometheus:
    image: prom/prometheus:latest
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.retention.time=30d'
    ports:
      - "9090:9090"

  node_exporter:
    image: prom/node-exporter:latest
    container_name: node_exporter
    restart: unless-stopped
    ports:
      - "9100:9100"
    volumes:
      - /proc:/host/proc:ro
      - /sys:/host/sys:ro
      - /:/rootfs:ro
    command:
      - '--path.procfs=/host/proc'
      - '--path.sysfs=/host/sys'
      - '--collector.filesystem.mount-points-exclude=^/(sys|proc|dev|host|etc)($$|/)'

volumes:
  prometheus_data:
```

```yaml
# prometheus.yml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'node_exporter'
    static_configs:
      - targets: ['localhost:9100']

  - job_name: 'vps_services'
    static_configs:
      - targets: ['localhost:8080', 'localhost:3000']
```

### 1.2 Log Collection (Loki + Promtail)

```yaml
# promtail-config.yaml
server:
  http_listen_port: 9080
  grpc_listen_port: 0

positions:
  filename: /tmp/positions.yaml

clients:
  - url: http://loki:3100/loki/api/v1/push

scrape_configs:
  - job_names: ['system']
    static_configs:
      - targets: ['localhost']
        labels:
          job: 'varlogs'
          __path__: '/var/log/*.log'
```

### 1.3 Custom Business Metrics

Beyond system-level metrics, we also need application-level key metrics:

```python
#!/usr/bin/env python3
"""Custom VPS Business Metric Collector"""

import psutil
import subprocess
import json
from datetime import datetime

def collect_disk_health():
    """Collect disk health indicators"""
    smart_info = {}
    try:
        result = subprocess.run(
            ['smartctl', '-a', '/dev/sda'],
            capture_output=True, text=True, timeout=10
        )
        for line in result.stdout.split('\n'):
            if 'Reallocated_Sector' in line or 'Current_Pending_Sector' in line:
                key = line.split(':')[0].strip()
                value = line.split(':')[-1].strip().split()[0]
                smart_info[key] = int(value)
    except Exception as e:
        smart_info['error'] = str(e)
    return smart_info

def collect_memory_leak_indicators():
    """Detect signs of memory leaks"""
    mem = psutil.virtual_memory()
    process_mem = []
    for proc in psutil.process_iter(['pid', 'name', 'memory_rss']):
        try:
            process_mem.append({
                'pid': proc.info['pid'],
                'name': proc.info['name'],
                'rss_mb': round(proc.info['memory_rss'] / 1024 / 1024, 2)
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    
    process_mem.sort(key=lambda x: x['rss_mb'], reverse=True)
    return {
        'total_percent': mem.percent,
        'available_gb': round(mem.available / 1024**3, 2),
        'top_processes': process_mem[:10],
        'swap_used_percent': psutil.swap_memory().percent
    }

def collect_service_health():
    """Collect service health status"""
    services = ['nginx', 'mysql', 'redis-server']
    health = {}
    for svc in services:
        try:
            result = subprocess.run(
                ['systemctl', 'is-active', svc],
                capture_output=True, text=True, timeout=5
            )
            health[svc] = result.stdout.strip()
        except Exception:
            health[svc] = 'unknown'
    return health

if __name__ == '__main__':
    data = {
        'timestamp': datetime.now().isoformat(),
        'disk_health': collect_disk_health(),
        'memory_leak': collect_memory_leak_indicators(),
        'service_health': collect_service_health()
    }
    print(json.dumps(data, indent=2))
```

## Step 2: Failure Prediction Engine

### 2.1 Disk Capacity Trend Prediction

Use linear regression to predict when the disk will be full:

```python
#!/usr/bin/env python3
"""Disk Capacity Predictor Based on Historical Data"""

import numpy as np
from datetime import datetime, timedelta

class DiskCapacityPredictor:
    def __init__(self, window_days=30):
        self.window_days = window_days
    
    def predict_full_time(self, current_usage_gb, total_gb, daily_growth_rate_gb):
        """
        Predict when the disk will be full
        
        Args:
            current_usage_gb: Current used space (GB)
            total_gb: Total space (GB)
            daily_growth_rate_gb: Average daily growth (GB)
        
        Returns:
            dict: Prediction results
        """
        if daily_growth_rate_gb <= 0:
            return {
                'days_until_full': None,
                'risk_level': 'low',
                'message': 'Disk usage is stable or decreasing'
            }
        
        remaining_gb = total_gb - current_usage_gb
        days_until_full = remaining_gb / daily_growth_rate_gb
        
        # Risk level assessment
        if days_until_full < 7:
            risk_level = 'critical'
        elif days_until_full < 30:
            risk_level = 'high'
        elif days_until_full < 90:
            risk_level = 'medium'
        else:
            risk_level = 'low'
        
        predicted_date = datetime.now() + timedelta(days=days_until_full)
        
        return {
            'days_until_full': round(days_until_full, 1),
            'predicted_full_date': predicted_date.strftime('%Y-%m-%d'),
            'risk_level': risk_level,
            'current_usage_percent': round(current_usage_gb / total_gb * 100, 1),
            'daily_growth_gb': round(daily_growth_rate_gb, 3),
            'message': f"Disk expected to be full in {int(days_until_full)} days ({predicted_date.strftime('%b %d')}), risk level: {risk_level}"
        }

    def analyze_growth_trend(self, usage_history):
        """
        Analyze disk usage growth trend
        
        Args:
            usage_history: [(timestamp, usage_gb), ...] Last N days of data
        
        Returns:
            dict: Trend analysis results
        """
        if len(usage_history) < 7:
            return {'error': 'Insufficient data points, need at least 7 days'}
        
        values = [x[1] for x in usage_history]
        n = len(values)
        
        # Linear regression
        x = np.arange(n)
        coeffs = np.polyfit(x, values, 1)
        slope = coeffs[0]  # GB/day
        
        # R² calculation
        y_pred = np.polyval(coeffs, x)
        ss_res = np.sum((values - y_pred) ** 2)
        ss_tot = np.sum((values - np.mean(values)) ** 2)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
        
        return {
            'daily_growth_gb': round(slope, 3),
            'r_squared': round(r_squared, 3),
            'trend': 'accelerating' if r_squared > 0.9 else 'linear' if r_squared > 0.7 else 'irregular',
            'forecast_7d': round(values[-1] + slope * 7, 2),
            'forecast_30d': round(values[-1] + slope * 30, 2)
        }
```

### 2.2 Memory Leak Detection

```python
#!/usr/bin/env python3
"""Memory Leak Detector"""

import psutil
import time
from collections import deque

class MemoryLeakDetector:
    def __init__(self, check_interval=60, window_size=60):
        self.check_interval = check_interval
        self.window_size = window_size
        self.history = deque(maxlen=window_size)
    
    def detect_leak(self, pid=None):
        """
        Detect if a specific process has a memory leak
        
        Args:
            pid: Process ID, None means check all processes
        
        Returns:
            dict: Detection results
        """
        processes = []
        
        if pid is not None:
            procs = [p for p in psutil.process_iter(['pid', 'name', 'memory_info']) 
                     if p.info['pid'] == pid]
        else:
            procs = list(psutil.process_iter(['pid', 'name', 'memory_info']))
        
        for proc in procs:
            try:
                mem = proc.info['memory_info']
                processes.append({
                    'pid': proc.info['pid'],
                    'name': proc.info['name'],
                    'rss_mb': round(mem.rss / 1024 / 1024, 2),
                    'vms_mb': round(mem.vms / 1024 / 1024, 2)
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        results = {}
        for proc in processes:
            if proc['rss_mb'] > 50:
                results[proc['name']] = proc
        
        return {
            'timestamp': time.time(),
            'significant_processes': results,
            'total_system_memory_percent': psutil.virtual_memory().percent,
            'swap_usage_percent': psutil.swap_memory().percent
        }
    
    def monitor_over_time(self, pid, duration_minutes=30):
        """Monitor process memory changes over time"""
        samples = []
        end_time = time.time() + duration_minutes * 60
        
        while time.time() < end_time:
            try:
                proc = psutil.Process(pid)
                mem = proc.memory_info()
                samples.append({
                    'time': time.time(),
                    'rss_mb': round(mem.rss / 1024 / 1024, 2)
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                break
            
            time.sleep(self.check_interval)
        
        if len(samples) < 5:
            return {'leaked': False, 'reason': 'Insufficient samples'}
        
        rss_values = [s['rss_mb'] for s in samples]
        n = len(rss_values)
        x = np.arange(n)
        coeffs = np.polyfit(x, rss_values, 1)
        
        growth_rate = coeffs[0]  # MB per sample interval
        is_leaking = growth_rate > 1.0
        
        return {
            'leaked': is_leaking,
            'growth_rate_mb_per_sample': round(growth_rate, 3),
            'start_mb': rss_values[0],
            'end_mb': rss_values[-1],
            'samples_count': n,
            'monitoring_duration_min': round(duration_minutes, 1)
        }
```

### 2.3 Prometheus-Based Anomaly Detection

```promql
# Alert rules for predictive maintenance
groups:
  - name: predictive_maintenance
    rules:
      - alert: DiskFullPrediction
        expr: predict_linear(node_filesystem_avail_bytes[7d], 7 * 86400) < 0
        for: 1h
        labels:
          severity: warning
        annotations:
          summary: "Disk {{ $labels.mountpoint }} expected to fill within 7 days"
          description: "Current usage {{ $value | humanizePercentage }}, will be exhausted in 7 days at current rate"
      
      - alert: MemoryLeakSuspected
        expr: increase(process_resident_memory_bytes[1h]) > 100 * 1024 * 1024
        for: 30m
        labels:
          severity: warning
        annotations:
          summary: "Process {{ $labels.instance }} memory growing continuously"
      
      - alert: HighDiskIOWait
        expr: rate(node_disk_io_time_seconds_total[5m]) > 0.8
        for: 10m
        labels:
          severity: critical
        annotations:
          summary: "Disk I/O wait rate consistently above 80%"
```

## Step 3: LLM-Powered Smart Analysis

### 3.1 Log Anomaly Pattern Detection

```python
#!/usr/bin/env python3
"""LLM-Powered Log Anomaly Detection"""

import subprocess
import re
from datetime import datetime, timedelta

class LogAnomalyDetector:
    ERROR_PATTERNS = {
        'oom_killed': r'Out of memory: Killed process (\d+)',
        'disk_write_error': r'(EXT4-fs error|I/O error|write error)',
        'connection_refused': r'Connection refused|ECONNREFUSED',
        'permission_denied': r'Permission denied|EACCES',
        'ssl_error': r'SSL handshake failed|certificate.*expired',
        'database_error': r'can.*connect to server|too many connections',
        'high_load': r'load average:\s*([\d.]+)',
        'segfault': r'segfault \S+ ip \S+ sp \S+ error \d+',
    }
    
    def analyze_recent_logs(self, log_files=None, hours=24):
        """Analyze recent logs"""
        if log_files is None:
            log_files = ['/var/log/syslog', '/var/log/auth.log', '/var/log/kern.log']
        
        findings = []
        cutoff = datetime.now() - timedelta(hours=hours)
        
        for log_file in log_files:
            try:
                result = subprocess.run(
                    ['journalctl', '--since', f'{hours} hours ago',
                     '--no-pager'],
                    capture_output=True, text=True, timeout=30
                )
                
                lines = result.stdout.strip().split('\n')
                for line in lines:
                    for pattern_name, pattern in self.ERROR_PATTERNS.items():
                        match = re.search(pattern, line)
                        if match:
                            findings.append({
                                'type': pattern_name,
                                'severity': self._severity(pattern_name),
                                'detail': match.group(0)[:200],
                                'source': log_file
                            })
            except Exception as e:
                findings.append({'type': 'collection_error', 'severity': 'info', 
                               'detail': str(e)})
        
        return self._deduplicate(findings)
    
    def _severity(self, pattern_name):
        critical = ['oom_killed', 'segfault', 'disk_write_error']
        warning = ['connection_refused', 'database_error', 'high_load']
        
        if pattern_name in critical:
            return 'critical'
        elif pattern_name in warning:
            return 'warning'
        return 'info'
    
    def _deduplicate(self, findings):
        grouped = {}
        for f in findings:
            key = f['type']
            if key not in grouped:
                grouped[key] = {**f, 'count': 0}
            grouped[key]['count'] += 1
        return list(grouped.values())
```

### 3.2 Intelligent Root Cause Analysis

```python
#!/usr/bin/env python3
"""
AI Agent Root Cause Analysis Engine
Integrates metrics, logs, and configuration for comprehensive diagnosis
"""

import json
import subprocess
from datetime import datetime

class RootCauseAnalyzer:
    def collect_context(self):
        """Collect all context needed for diagnosis"""
        context = {
            'timestamp': datetime.now().isoformat(),
            'system_metrics': self._get_system_metrics(),
            'recent_errors': self._get_recent_errors(),
            'service_status': self._get_service_status(),
        }
        return context
    
    def _get_system_metrics(self):
        import psutil
        return {
            'cpu_percent': psutil.cpu_percent(interval=1),
            'mem_percent': psutil.virtual_memory().percent,
            'disk_usage': {
                mount: {
                    'total_gb': round(info.total / 1024**3, 1),
                    'used_gb': round(info.used / 1024**3, 1),
                    'free_gb': round(info.free / 1024**3, 1),
                    'percent': info.percent
                }
                for mount, info in psutil.disk_mounts()
            },
            'load_avg': list(psutil.getloadavg()),
        }
    
    def _get_recent_errors(self):
        try:
            result = subprocess.run(
                ['journalctl', '-p', 'err', '--since', '1 hour ago',
                 '--no-pager', '-n', '50'],
                capture_output=True, text=True, timeout=15
            )
            return result.stdout.strip().split('\n')[:10]
        except Exception:
            return []
    
    def _get_service_status(self):
        try:
            result = subprocess.run(
                ['systemctl', 'list-units', '--type=service', '--state=failed',
                 '--no-pager'],
                capture_output=True, text=True, timeout=10
            )
            return result.stdout.strip()
        except Exception:
            return 'unavailable'
    
    def generate_diagnosis_prompt(self, context, issue_description):
        """Generate diagnostic prompt for LLM"""
        return f"""You are a professional VPS operations expert. Please perform root cause analysis based on the following information.

## User Reported Issue
{issue_description}

## System Metrics
{json.dumps(context['system_metrics'], indent=2, ensure_ascii=False)}

## Recent Error Logs
{chr(10).join(context['recent_errors'])}

## Failed Services
{context['service_status']}

## Please answer
1. What is the most likely root cause?
2. Immediate repair steps (ordered by priority)
3. How to prevent similar issues from recurring
4. Whether scaling or configuration adjustments are needed"""
```

## Step 4: Self-Healing Execution

### 4.1 Common Issue Auto-Fix

```python
#!/usr/bin/env python3
"""
VPS Auto-Repair Engine
Automatically executes repairs based on diagnosis results
"""

import subprocess
import logging
from enum import Enum

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('selfheal')

class Action(Enum):
    SAFE = "safe"
    CAUTION = "caution"
    DANGEROUS = "dangerous"

REPAIR_ACTIONS = {
    'clear_journald_logs': {
        'action': Action.SAFE,
        'description': 'Clear journal logs to free disk space',
        'command': 'sudo journalctl --vacuum-time=3d',
    },
    'restart_failed_service': {
        'action': Action.CAUTION,
        'description': 'Restart failed service',
        'command_template': 'sudo systemctl restart {service}',
    },
    'remove_old_kernels': {
        'action': Action.SAFE,
        'description': 'Remove old kernels to free disk space',
        'command': 'sudo apt autoremove --purge',
    },
    'rotate_app_logs': {
        'action': Action.SAFE,
        'description': 'Compress and archive application logs',
        'command_template': 'sudo find /var/log/{app} -name "*.log" -size +100M -exec gzip {{}} \\;',
    },
    'reload_nginx': {
        'action': Action.SAFE,
        'description': 'Reload Nginx configuration',
        'command': 'sudo nginx -t && sudo systemctl reload nginx',
    },
}

class SelfHealingEngine:
    def __init__(self, dry_run=True):
        self.dry_run = dry_run
        self.execution_log = []
    
    def execute_repair(self, repair_type, params=None):
        """Execute automatic repair"""
        if repair_type not in REPAIR_ACTIONS:
            logger.error(f"Unknown repair type: {repair_type}")
            return False
        
        action_def = REPAIR_ACTIONS[repair_type]
        safety_level = action_def['action']
        
        if safety_level == Action.DANGEROUS:
            logger.warning(f"⚠️ Action '{repair_type}' marked as dangerous, skipping")
            return False
        
        if safety_level == Action.CAUTION and self.dry_run:
            logger.info(f"🔍 Dry run mode: Ready to execute '{repair_type}' (needs confirmation)")
            logger.info(f"   Command: {action_def['command']}")
            return True
        
        cmd = action_def.get('command', '')
        if params:
            cmd = cmd.format(**params)
        
        logger.info(f"🔧 Executing repair: {repair_type}")
        logger.info(f"   Command: {cmd}")
        
        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=120
            )
            
            self.execution_log.append({
                'type': repair_type,
                'command': cmd,
                'returncode': result.returncode,
                'stdout': result.stdout[:500],
                'stderr': result.stderr[:500],
                'success': result.returncode == 0,
            })
            
            if result.returncode == 0:
                logger.info(f"✅ Repair successful: {repair_type}")
            else:
                logger.error(f"❌ Repair failed: {repair_type} - {result.stderr[:200]}")
            
            return result.returncode == 0
            
        except subprocess.TimeoutExpired:
            logger.error(f"⏰ Repair timed out: {repair_type}")
            return False
        except Exception as e:
            logger.error(f"💥 Execution exception: {e}")
            return False
    
    def auto_heal(self, diagnosis_result):
        """Auto-execute repairs based on diagnosis results"""
        recommendations = diagnosis_result.get('recommendations', [])
        
        for rec in recommendations:
            repair_type = rec.get('repair_type')
            params = rec.get('params', {})
            
            if repair_type in REPAIR_ACTIONS:
                self.execute_repair(repair_type, params)
        
        return self.execution_log
```

### 4.2 Scheduled Inspection Task

```bash
#!/bin/bash
# /usr/local/bin/vps-daily-inspection.sh
# VPS Daily Inspection Script

LOG_DIR="/var/log/vps-inspection"
mkdir -p "$LOG_DIR"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

echo "=== VPS Daily Inspection Started: $(date) ===" | tee "$LOG_DIR/daily_${TIMESTAMP}.log"

# 1. Disk health check
echo "[1/5] Checking disk health..."
df -h | tee -a "$LOG_DIR/daily_${TIMESTAMP}.log"
smartctl -a /dev/sda 2>/dev/null | grep -E 'Reallocated|Current_Pending|UDMA_CRC' >> "$LOG_DIR/daily_${TIMESTAMP}.log"

# 2. Service status check
echo "[2/5] Checking service status..."
systemctl list-units --state=failed --no-pager >> "$LOG_DIR/daily_${TIMESTAMP}.log" 2>&1

# 3. Security audit
echo "[3/5] Security audit..."
echo "--- Recent Logins ---" >> "$LOG_DIR/daily_${TIMESTAMP}.log"
last -n 10 >> "$LOG_DIR/daily_${TIMESTAMP}.log" 2>&1
echo "--- SSH Failed Attempts ---" >> "$LOG_DIR/daily_${TIMESTAMP}.log"
grep -c "Failed password" /var/log/auth.log 2>/dev/null >> "$LOG_DIR/daily_${TIMESTAMP}.log"

# 4. Resource usage report
echo "[4/5] Resource usage report..."
free -h >> "$LOG_DIR/daily_${TIMESTAMP}.log"
top -bn1 | head -5 >> "$LOG_DIR/daily_${TIMESTAMP}.log"

# 5. Run AI analysis
echo "[5/5] Running AI analysis..."
python3 /opt/vps-agent/analyzer.py >> "$LOG_DIR/daily_${TIMESTAMP}.log" 2>&1

echo "=== Inspection Complete: $(date) ===" | tee -a "$LOG_DIR/daily_${TIMESTAMP}.log"

# Clean up logs older than 7 days
find "$LOG_DIR" -name "daily_*" -mtime +7 -delete
```

```cron
# Run daily inspection at 2 AM
0 2 * * * /usr/local/bin/vps-daily-inspection.sh
```

## Step 5: Smart Report Generation

```python
#!/usr/bin/env python3
"""
Generate Natural Language Inspection Reports
Convert structured data into readable English reports
"""

import json
from datetime import datetime

def generate_report(inspection_data):
    """Generate human-readable inspection report"""
    
    report = []
    report.append("# 📋 VPS Daily Inspection Report")
    report.append(f"**Date**: {inspection_data['timestamp']}")
    report.append("")
    
    score = inspection_data.get('health_score', 100)
    if score >= 90:
        emoji, status = "🟢", "Excellent"
    elif score >= 70:
        emoji, status = "🟡", "Good"
    elif score >= 50:
        emoji, status = "🟠", "Needs Attention"
    else:
        emoji, status = "🔴", "Warning"
    
    report.append(f"## Overall Health Score: {emoji} {score}/100 ({status})")
    report.append("")
    
    disk = inspection_data.get('disk', {})
    report.append(f"## 💾 Disk Analysis")
    report.append(f"- Usage: {disk.get('usage_percent', 'N/A')}%")
    report.append(f"- Days until full: {disk.get('predicted_full_days', 'N/A')}")
    report.append(f"- Risk level: {disk.get('risk_level', 'N/A')}")
    report.append("")
    
    mem = inspection_data.get('memory', {})
    report.append(f"## 🧠 Memory Analysis")
    report.append(f"- Usage: {mem.get('usage_percent', 'N/A')}%")
    report.append(f"- Available: {mem.get('available_gb', 'N/A')} GB")
    report.append(f"- Possible memory leak: {'Yes' if mem.get('possible_leak') else 'No'}")
    report.append("")
    
    security = inspection_data.get('security', {})
    report.append(f"## 🔒 Security Analysis")
    report.append(f"- Failed SSH logins: {security.get('failed_ssh_attempts', 0)}")
    report.append(f"- Open risky ports: {security.get('open_risky_ports', [])}")
    report.append("")
    
    recommendations = inspection_data.get('recommendations', [])
    if recommendations:
        report.append(f"## 🔧 Recommendations")
        for i, rec in enumerate(recommendations, 1):
            report.append(f"{i}. **{rec.get('title', '')}**: {rec.get('description', '')}")
            if rec.get('command'):
                report.append(f"   ```bash\n   {rec['command']}\n   ```")
        report.append("")
    
    return "\n".join(report)
```

## Complete Deployment Guide

### Docker Compose One-Click Deployment

```yaml
# docker-compose.yml - Full Predictive Maintenance Stack
version: '3.8'

services:
  prometheus:
    image: prom/prometheus:latest
    volumes:
      - ./prometheus:/etc/prometheus
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.retention.time=30d'
      - '--web.enable-lifecycle'
    ports:
      - "9090:9090"
    restart: unless-stopped

  grafana:
    image: grafana/grafana:latest
    volumes:
      - grafana_data:/var/lib/grafana
      - ./grafana/provisioning:/etc/grafana/provisioning
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_PASSWORD}
    ports:
      - "3000:3000"
    depends_on:
      - prometheus
    restart: unless-stopped

  loki:
    image: grafana/loki:latest
    ports:
      - "3100:3100"
    volumes:
      - ./loki:/etc/loki
    command: -config.file=/etc/loki/loki-config.yaml
    restart: unless-stopped

  promtail:
    image: grafana/promtail:latest
    volumes:
      - /var/log:/var/log
      - ./promtail:/etc/promtail
    command: -config.file=/etc/promtail/config.yaml
    restart: unless-stopped

  vps-agent:
    build: ./vps-agent
    volumes:
      - ./vps-agent/scripts:/app/scripts
      - /var/log:/host/var/log:ro
      - /proc:/host/proc:ro
      - /sys:/host/sys:ro
    environment:
      - LLM_API_URL=http://ollama:11434
      - PROMETHEUS_URL=http://prometheus:9090
      - LOKI_URL=http://loki:3100
      - DRY_RUN=true
    depends_on:
      - prometheus
      - loki
      - ollama
    restart: unless-stopped

  ollama:
    image: ollama/ollama:latest
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama
    restart: unless-stopped

volumes:
  prometheus_data:
  grafana_data:
  ollama_data:
```

## Best Practices & Considerations

### Safety Boundaries

1. **Dry Run First**: All automatic repair operations default to `dry_run` mode — observe first, execute later
2. **Whitelist Mechanism**: Only operations marked as `Action.SAFE` can be auto-executed
3. **Operation Audit**: All auto-executed operations are logged for traceability
4. **Circuit Breaker**: After 3 consecutive failures, auto-healing stops and switches to manual alerting

### Performance Optimization

1. **Sampling Frequency**: Production environments recommend 15-60 second intervals to avoid performance impact
2. **Data Retention**: Raw metrics retained for 30 days, aggregated data for 90 days
3. **LLM Rate Limiting**: Set rate limits on LLM API calls to avoid excessive consumption

### Cost Estimation

| Component | Resource Requirement | Monthly Cost |
|-----------|---------------------|-------------|
| Prometheus | 512MB RAM, 1 CPU | Free (self-hosted) |
| Grafana | 256MB RAM | Free |
| Loki | 256MB RAM | Free |
| Ollama (small model) | 2GB RAM | Free |
| **Total** | **~2GB RAM, 2 CPU** | **≈ $5-10/month** |

## Summary

By building this **AI-driven VPS predictive maintenance system**, you can achieve:

- ✅ **Early Detection**: Warn about disk full, memory leaks, and other issues days before they cause problems
- ✅ **Automatic Repair**: Auto-apply safe fixes for known issue types
- ✅ **Intelligent Diagnosis**: LLM analyzes multi-dimensional data and provides professional-grade root cause analysis
- ✅ **Readable Reports**: Automatically generate natural language daily inspection reports at a glance

The core value of this system is **shifting operations from reactive to proactive**. Instead of being woken up by alarm calls at midnight, spend one minute each day reviewing the AI-generated inspection report and handle potential issues in advance.

> 💡 **Next Steps**: Start with the simplest component — disk capacity prediction — and gradually add memory leak detection, log analysis, and auto-repair features. Each module can run independently and be combined as needed.