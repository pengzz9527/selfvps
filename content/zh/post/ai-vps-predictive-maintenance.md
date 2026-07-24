---
title: "VPS 预测性维护：AI Agent 提前预警磁盘故障与内存泄漏"
description: "别再半夜被告警电话叫醒。用 AI Agent 构建 VPS 预测性维护系统——提前发现磁盘满载、内存泄漏和服务退化，自动生成修复方案，让运维从'救火'走向'预防'"
date: 2026-07-24T20:00:00+08:00
lastmod: 2026-07-24T20:00:00+08:00
slug: "ai-vps-predictive-maintenance"
image: /images/posts/ai-vps-predictive-maintenance/featured.png
tags: ["AI Agent", "VPS", "预测性维护", "故障预警", "自动化运维", "机器学习", "自我修复", "AIOps"]
categories: ["AI 运维"]
aliases: [/zh/post/ai-vps-predictive-maintenance/]
---

## 引言

你的 VPS 什么时候会出问题？

- 硬盘在凌晨三点突然写满，日志服务中断，第二天早上才发现问题；
- 内存泄漏缓慢累积，一周后网站响应时间从 200ms 飙升到 5s；
- SSL 证书过期导致用户无法访问，而你只在日历上设了一个提醒却忘了；
- 数据库连接池耗尽，API 全面超时，但监控面板只显示"一切正常"。

**传统运维的核心问题是被动响应**——只有在问题发生后才采取行动。而 **AI Agent + 预测性维护** 改变了这一范式：它能在故障发生前数小时甚至数天发出预警，并自动生成修复方案。

本文将带你从零构建一套 **AI 驱动的 VPS 预测性维护系统**，涵盖以下核心能力：

1. **故障预测**：基于时序数据分析磁盘、内存、CPU 趋势，提前预警容量瓶颈
2. **异常检测**：利用 LLM 分析日志模式，识别潜在的安全威胁和性能退化
3. **根因分析**：当异常发生时，自动关联多维度指标，定位根本原因
4. **自愈执行**：对已知问题类型自动生成并执行修复脚本
5. **智能报告**：用自然语言生成可读的每日巡检报告和趋势分析

## 架构概览

```
┌─────────────────────────────────────────────────────┐
│                  AI Agent (LLM)                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │ 故障预测  │  │ 异常检测  │  │   根因分析与自愈  │  │
│  │ ML模型    │  │ LLM+RAG  │  │   决策引擎        │  │
│  └────┬─────┘  └────┬─────┘  └────────┬─────────┘  │
│       │             │                  │             │
│  ┌────▼─────────────▼──────────────────▼─────────┐  │
│  │           统一事件总线 (Event Bus)              │  │
│  └────┬─────────────┬──────────────────┬─────────┘  │
│       │             │                  │             │
├───────┼─────────────┼──────────────────┼────────────┤
│       ▼             ▼                  ▼             │
│  ┌────────┐  ┌──────────┐  ┌──────────────────┐    │
│  │Prometheus│ │ Loki     │  │ Node Exporter    │    │
│  │(指标采集) │ │(日志采集) │  │ + 自定义采集器    │    │
│  └────────┘  └──────────┘  └──────────────────┘    │
│       ▲             ▲                  ▲            │
│  ┌────┴─────────────┴──────────────────┴─────────┐  │
│  │              目标 VPS 实例                      │  │
│  └───────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

## 第一步：数据采集层

预测性维护的前提是**高质量、全维度的数据**。我们需要采集三类数据：

### 1.1 系统指标采集（Prometheus + Node Exporter）

```yaml
# docker-compose.yml - 监控栈
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

### 1.2 日志采集（Loki + Promtail）

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

### 1.3 自定义业务指标

除了系统级指标，还需要采集应用层面的关键指标：

```python
#!/usr/bin/env python3
"""自定义 VPS 业务指标采集器"""

import psutil
import subprocess
import json
from datetime import datetime

def collect_disk_health():
    """采集磁盘健康度指标"""
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
    """检测内存泄漏迹象"""
    mem = psutil.virtual_memory()
    # 获取各进程内存使用排名
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
    """采集服务健康状态"""
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

## 第二步：故障预测引擎

### 2.1 磁盘容量趋势预测

使用线性回归预测磁盘何时会满：

```python
#!/usr/bin/env python3
"""基于历史数据的磁盘容量预测"""

import numpy as np
from datetime import datetime, timedelta

class DiskCapacityPredictor:
    def __init__(self, window_days=30):
        self.window_days = window_days
    
    def predict_full_time(self, current_usage_gb, total_gb, daily_growth_rate_gb):
        """
        预测磁盘何时会满
        
        Args:
            current_usage_gb: 当前已用空间 (GB)
            total_gb: 总空间 (GB)
            daily_growth_rate_gb: 日均增长量 (GB)
        
        Returns:
            dict: 预测结果
        """
        if daily_growth_rate_gb <= 0:
            return {
                'days_until_full': None,
                'risk_level': 'low',
                'message': '磁盘使用率呈下降或稳定趋势'
            }
        
        remaining_gb = total_gb - current_usage_gb
        days_until_full = remaining_gb / daily_growth_rate_gb
        
        # 风险等级评估
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
            'message': f"预计 {int(days_until_full)} 天后 ({predicted_date.strftime('%m月%d日')}) 磁盘将满，当前风险等级: {risk_level}"
        }

    def analyze_growth_trend(self, usage_history):
        """
        分析磁盘使用增长趋势
        
        Args:
            usage_history: [(timestamp, usage_gb), ...] 最近N天的数据
        
        Returns:
            dict: 趋势分析结果
        """
        if len(usage_history) < 7:
            return {'error': '数据点不足，至少需要7天'}
        
        # 提取数值
        values = [x[1] for x in usage_history]
        n = len(values)
        
        # 线性回归
        x = np.arange(n)
        coeffs = np.polyfit(x, values, 1)
        slope = coeffs[0]  # 每日增长量 (GB/day)
        
        # 计算 R² 判断拟合程度
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

# 使用示例
if __name__ == '__main__':
    predictor = DiskCapacityPredictor()
    
    # 模拟30天磁盘使用数据
    history = [(i, 45 + i * 0.8 + np.random.randn() * 0.3) 
               for i in range(30)]
    
    trend = predictor.analyze_growth_trend(history)
    prediction = predictor.predict_full_time(
        current_usage_gb=history[-1][1],
        total_gb=100,
        daily_growth_rate_gb=trend['daily_growth_gb']
    )
    
    print(json.dumps({
        'trend_analysis': trend,
        'capacity_prediction': prediction
    }, indent=2))
```

### 2.2 内存泄漏检测

```python
#!/usr/bin/env python3
"""内存泄漏检测器"""

import psutil
import time
from collections import deque

class MemoryLeakDetector:
    def __init__(self, check_interval=60, window_size=60):
        self.check_interval = check_interval  # 检查间隔(秒)
        self.window_size = window_size  # 滑动窗口大小
        self.history = deque(maxlen=window_size)
    
    def detect_leak(self, pid=None):
        """
        检测指定进程是否存在内存泄漏
        
        Args:
            pid: 进程ID，None表示检测所有进程
        
        Returns:
            dict: 检测结果
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
        
        # 分析增长趋势
        results = {}
        for proc in processes:
            if proc['rss_mb'] > 50:  # 只关注大于50MB的进程
                results[proc['name']] = proc
        
        return {
            'timestamp': time.time(),
            'significant_processes': results,
            'total_system_memory_percent': psutil.virtual_memory().percent,
            'swap_usage_percent': psutil.swap_memory().percent
        }
    
    def monitor_over_time(self, pid, duration_minutes=30):
        """
        长时间监控进程内存变化
        
        Returns:
            bool: 是否检测到内存泄漏
        """
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
            return {'leaked': False, 'reason': '采样数据不足'}
        
        # 简单的线性趋势检测
        rss_values = [s['rss_mb'] for s in samples]
        n = len(rss_values)
        x = np.arange(n)
        coeffs = np.polyfit(x, rss_values, 1)
        
        growth_rate = coeffs[0]  # MB per sample interval
        is_leaking = growth_rate > 1.0  # 每次采样增长超过1MB视为泄漏
        
        return {
            'leaked': is_leaking,
            'growth_rate_mb_per_sample': round(growth_rate, 3),
            'start_mb': rss_values[0],
            'end_mb': rss_values[-1],
            'samples_count': n,
            'monitoring_duration_min': round(duration_minutes, 1)
        }
```

### 2.3 基于 Prometheus 的异常检测

```promql
# 磁盘使用率超过85%的告警规则
groups:
  - name: predictive_maintenance
    rules:
      # 磁盘容量预测告警
      - alert: DiskFullPrediction
        expr: predict_linear(node_filesystem_avail_bytes[7d], 7 * 86400) < 0
        for: 1h
        labels:
          severity: warning
        annotations:
          summary: "磁盘 {{ $labels.mountpoint }} 预计7天内将满"
          description: "当前使用率 {{ $value | humanizePercentage }}，按当前增长速度，7天后将耗尽"
      
      # 内存持续增长告警
      - alert: MemoryLeakSuspected
        expr: increase(process_resident_memory_bytes[1h]) > 100 * 1024 * 1024
        for: 30m
        labels:
          severity: warning
        annotations:
          summary: "进程 {{ $labels.instance }} 内存持续增长"
      
      # 磁盘I/O等待过高
      - alert: HighDiskIOWait
        expr: rate(node_disk_io_time_seconds_total[5m]) > 0.8
        for: 10m
        labels:
          severity: critical
        annotations:
          summary: "磁盘I/O等待率持续高于80%"
```

## 第三步：LLM 驱动的智能分析

### 3.1 日志异常模式检测

```python
#!/usr/bin/env python3
"""LLM驱动的日志异常检测"""

import subprocess
import re
from datetime import datetime, timedelta

class LogAnomalyDetector:
    """基于日志模式的异常检测"""
    
    # 常见错误模式定义
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
        """分析最近N小时的日志"""
        if log_files is None:
            log_files = ['/var/log/syslog', '/var/log/auth.log', '/var/log/kern.log']
        
        findings = []
        cutoff = datetime.now() - timedelta(hours=hours)
        
        for log_file in log_files:
            try:
                # 使用 journalctl 获取最近日志
                result = subprocess.run(
                    ['journalctl', f'-u', '--since', f'{hours} hours ago',
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
        """根据错误类型判断严重程度"""
        critical = ['oom_killed', 'segfault', 'disk_write_error']
        warning = ['connection_refused', 'database_error', 'high_load']
        info = ['permission_denied', 'ssl_error']
        
        if pattern_name in critical:
            return 'critical'
        elif pattern_name in warning:
            return 'warning'
        return 'info'
    
    def _deduplicate(self, findings):
        """去重，相同类型的错误合并计数"""
        grouped = {}
        for f in findings:
            key = f['type']
            if key not in grouped:
                grouped[key] = {**f, 'count': 0}
            grouped[key]['count'] += 1
        return list(grouped.values())

# 使用示例
detector = LogAnomalyDetector()
results = detector.analyze_recent_logs(hours=24)
for r in results:
    print(f"[{r['severity'].upper()}] {r['type']}: {r['detail']} (×{r['count']})")
```

### 3.2 智能根因分析

```python
#!/usr/bin/env python3
"""
AI Agent 根因分析引擎
整合指标、日志、配置信息，通过 LLM 进行综合诊断
"""

import json
import subprocess
from datetime import datetime

class RootCauseAnalyzer:
    """根因分析器 — 收集上下文并提交给 LLM"""
    
    def collect_context(self):
        """收集诊断所需的全部上下文"""
        context = {
            'timestamp': datetime.now().isoformat(),
            'system_metrics': self._get_system_metrics(),
            'recent_errors': self._get_recent_errors(),
            'service_status': self._get_service_status(),
            'resource_limits': self._get_resource_limits(),
        }
        return context
    
    def _get_system_metrics(self):
        """采集系统指标"""
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
            'uptime_seconds': psutil.boot_time(),
        }
    
    def _get_recent_errors(self):
        """获取最近的错误日志"""
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
        """获取服务状态"""
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
        """生成提交给 LLM 的诊断提示"""
        return f"""你是一个专业的 VPS 运维专家。请根据以下信息进行根因分析。

## 用户报告的问题
{issue_description}

## 系统指标
{json.dumps(context['system_metrics'], indent=2, ensure_ascii=False)}

## 最近错误日志
{chr(10).join(context['recent_errors'])}

## 失败的服务
{context['service_status']}

## 请回答
1. 最可能的根本原因是什么？
2. 需要立即执行的修复步骤（按优先级排序）
3. 如何预防类似问题再次发生
4. 是否需要扩容或调整配置"""

# 使用示例
analyzer = RootCauseAnalyzer()
context = analyzer.collect_context()
prompt = analyzer.generate_diagnosis_prompt(
    context, 
    "网站响应缓慢，API 超时率升高"
)
# 将 prompt 发送给 LLM（如 Ollama 本地部署的模型）
# response = ollama.chat(model='llama3', messages=[{'role': 'user', 'content': prompt}])
```

## 第四步：自愈执行

### 4.1 常见问题自动修复

```python
#!/usr/bin/env python3
"""
VPS 自动修复引擎
根据诊断结果自动执行修复操作
"""

import subprocess
import logging
from enum import Enum

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('selfheal')

class Action(Enum):
    SAFE = "safe"      # 可自动执行
    CAUTION = "caution" # 需要确认
    DANGEROUS = "dangerous"  # 禁止自动执行

REPAIR_ACTIONS = {
    'clear_journald_logs': {
        'action': Action.SAFE,
        'description': '清理 journal 日志释放磁盘空间',
        'command': 'sudo journalctl --vacuum-time=3d',
    },
    'restart_failed_service': {
        'action': Action.CAUTION,
        'description': '重启失败的服务',
        'command_template': 'sudo systemctl restart {service}',
    },
    'remove_old_kernels': {
        'action': Action.SAFE,
        'description': '移除过时的内核释放磁盘空间',
        'command': 'sudo apt autoremove --purge',
    },
    'rotate_app_logs': {
        'action': Action.SAFE,
        'description': '压缩并归档应用日志',
        'command_template': 'sudo find /var/log/{app} -name "*.log" -size +100M -exec gzip {{}} \\;',
    },
    'fix_permissions': {
        'action': Action.CAUTION,
        'description': '修复常见的权限问题',
        'command_template': 'sudo chown -R {user}:{group} {path}',
    },
    'reload_nginx': {
        'action': Action.SAFE,
        'description': '重新加载 Nginx 配置',
        'command': 'sudo nginx -t && sudo systemctl reload nginx',
    },
}

class SelfHealingEngine:
    def __init__(self, dry_run=True):
        self.dry_run = dry_run  # 默认干跑模式
        self.execution_log = []
    
    def execute_repair(self, repair_type, params=None):
        """执行自动修复"""
        if repair_type not in REPAIR_ACTIONS:
            logger.error(f"未知修复类型: {repair_type}")
            return False
        
        action_def = REPAIR_ACTIONS[repair_type]
        safety_level = action_def['action']
        
        # 安全检查
        if safety_level == Action.DANGEROUS:
            logger.warning(f"⚠️ 操作 '{repair_type}' 标记为危险，跳过自动执行")
            return False
        
        if safety_level == Action.CAUTION and self.dry_run:
            logger.info(f"🔍 干跑模式: 准备执行 '{repair_type}' (需确认)")
            logger.info(f"   命令: {action_def['command']}")
            return True
        
        # 执行命令
        cmd = action_def.get('command', '')
        if params:
            cmd = cmd.format(**params)
        
        logger.info(f"🔧 执行修复: {repair_type}")
        logger.info(f"   命令: {cmd}")
        
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
                logger.info(f"✅ 修复成功: {repair_type}")
            else:
                logger.error(f"❌ 修复失败: {repair_type} - {result.stderr[:200]}")
            
            return result.returncode == 0
            
        except subprocess.TimeoutExpired:
            logger.error(f"⏰ 修复超时: {repair_type}")
            return False
        except Exception as e:
            logger.error(f"💥 执行异常: {e}")
            return False
    
    def auto_heal(self, diagnosis_result):
        """根据诊断结果自动执行修复"""
        recommendations = diagnosis_result.get('recommendations', [])
        
        for rec in recommendations:
            repair_type = rec.get('repair_type')
            params = rec.get('params', {})
            
            if repair_type in REPAIR_ACTIONS:
                self.execute_repair(repair_type, params)
        
        return self.execution_log

# 使用示例
engine = SelfHealingEngine(dry_run=True)

diagnosis = {
    'recommendations': [
        {'repair_type': 'clear_journald_logs', 'params': {}},
        {'repair_type': 'reload_nginx', 'params': {}},
    ]
}

engine.auto_heal(diagnosis)
```

### 4.2 定时巡检任务

```bash
#!/bin/bash
# /usr/local/bin/vps-daily-inspection.sh
# VPS 每日巡检脚本

LOG_DIR="/var/log/vps-inspection"
mkdir -p "$LOG_DIR"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

echo "=== VPS 每日巡检开始: $(date) ===" | tee "$LOG_DIR/daily_${TIMESTAMP}.log"

# 1. 磁盘健康检查
echo "[1/5] 检查磁盘健康..."
df -h | tee -a "$LOG_DIR/daily_${TIMESTAMP}.log"
smartctl -a /dev/sda 2>/dev/null | grep -E 'Reallocated|Current_Pending|UDMA_CRC' >> "$LOG_DIR/daily_${TIMESTAMP}.log"

# 2. 服务状态检查
echo "[2/5] 检查服务状态..."
systemctl list-units --state=failed --no-pager >> "$LOG_DIR/daily_${TIMESTAMP}.log" 2>&1

# 3. 安全审计
echo "[3/5] 安全审计..."
echo "--- 最近登录 ---" >> "$LOG_DIR/daily_${TIMESTAMP}.log"
last -n 10 >> "$LOG_DIR/daily_${TIMESTAMP}.log" 2>&1
echo "--- SSH 失败尝试 ---" >> "$LOG_DIR/daily_${TIMESTAMP}.log"
grep -c "Failed password" /var/log/auth.log 2>/dev/null >> "$LOG_DIR/daily_${TIMESTAMP}.log"

# 4. 资源使用报告
echo "[4/5] 资源使用报告..."
free -h >> "$LOG_DIR/daily_${TIMESTAMP}.log"
top -bn1 | head -5 >> "$LOG_DIR/daily_${TIMESTAMP}.log"

# 5. 运行 AI 分析
echo "[5/5] 运行 AI 分析..."
python3 /opt/vps-agent/analyzer.py >> "$LOG_DIR/daily_${TIMESTAMP}.log" 2>&1

echo "=== 巡检完成: $(date) ===" | tee -a "$LOG_DIR/daily_${TIMESTAMP}.log"

# 清理7天前的日志
find "$LOG_DIR" -name "daily_*" -mtime +7 -delete
```

```cron
# 每天凌晨2点执行巡检
0 2 * * * /usr/local/bin/vps-daily-inspection.sh
```

## 第五步：智能报告生成

```python
#!/usr/bin/env python3
"""
生成自然语言巡检报告
将结构化数据转化为可读的中文报告
"""

import json
from datetime import datetime

def generate_report(inspection_data):
    """生成人类可读的巡检报告"""
    
    report = []
    report.append(f"# 📋 VPS 每日巡检报告")
    report.append(f"**日期**: {inspection_data['timestamp']}")
    report.append("")
    
    # 健康评分
    score = inspection_data.get('health_score', 100)
    if score >= 90:
        emoji, status = "🟢", "优秀"
    elif score >= 70:
        emoji, status = "🟡", "良好"
    elif score >= 50:
        emoji, status = "🟠", "需注意"
    else:
        emoji, status = "🔴", "警告"
    
    report.append(f"## 整体健康评分: {emoji} {score}/100 ({status})")
    report.append("")
    
    # 磁盘分析
    disk = inspection_data.get('disk', {})
    report.append(f"## 💾 磁盘分析")
    report.append(f"- 使用率: {disk.get('usage_percent', 'N/A')}%")
    report.append(f"- 预测满盘时间: {disk.get('predicted_full_days', 'N/A')} 天")
    report.append(f"- 风险等级: {disk.get('risk_level', 'N/A')}")
    if disk.get('smart_warnings'):
        report.append(f"- ⚠️ SMART 警告: {', '.join(disk['smart_warnings'])}")
    report.append("")
    
    # 内存分析
    mem = inspection_data.get('memory', {})
    report.append(f"## 🧠 内存分析")
    report.append(f"- 使用率: {mem.get('usage_percent', 'N/A')}%")
    report.append(f"- 可用内存: {mem.get('available_gb', 'N/A')} GB")
    report.append(f"- 疑似内存泄漏: {'是' if mem.get('possible_leak') else '否'}")
    report.append("")
    
    # 安全分析
    security = inspection_data.get('security', {})
    report.append(f"## 🔒 安全分析")
    report.append(f"- 失败SSH登录: {security.get('failed_ssh_attempts', 0)} 次")
    report.append(f"- 开放高危端口: {security.get('open_risky_ports', [])}")
    report.append(f"- 异常进程: {'无' if not security.get('suspicious_processes') else '有'}")
    report.append("")
    
    # 修复建议
    recommendations = inspection_data.get('recommendations', [])
    if recommendations:
        report.append(f"## 🔧 修复建议")
        for i, rec in enumerate(recommendations, 1):
            report.append(f"{i}. **{rec.get('title', '')}**: {rec.get('description', '')}")
            if rec.get('command'):
                report.append(f"   ```bash\n   {rec['command']}\n   ```")
        report.append("")
    
    return "\n".join(report)

# 使用示例
sample_data = {
    'timestamp': '2026-07-24',
    'health_score': 78,
    'disk': {
        'usage_percent': 72.5,
        'predicted_full_days': 23,
        'risk_level': 'medium',
        'smart_warnings': []
    },
    'memory': {
        'usage_percent': 65.3,
        'available_gb': 2.1,
        'possible_leak': True
    },
    'security': {
        'failed_ssh_attempts': 47,
        'open_risky_ports': [],
        'suspicious_processes': []
    },
    'recommendations': [
        {
            'title': '清理旧日志',
            'description': 'journal 日志占用约 8GB，建议清理3天前的日志',
            'command': 'sudo journalctl --vacuum-time=3d'
        },
        {
            'title': '排查内存增长',
            'description': 'Node.js 进程 RSS 持续增长，建议检查是否有内存泄漏',
            'command': 'sudo pmap -x $(pgrep node) | tail -1'
        }
    ]
}

print(generate_report(sample_data))
```

## 完整部署方案

### Docker Compose 一键部署

```yaml
# docker-compose.yml - 预测性维护完整栈
version: '3.8'

services:
  # 监控采集
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

  # AI Agent
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

  # 本地 LLM
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

### Grafana 仪表盘模板

```json
{
  "dashboard": {
    "title": "VPS 预测性维护总览",
    "panels": [
      {
        "title": "磁盘容量趋势 & 预测",
        "type": "graph",
        "targets": [
          {
            "expr": "node_filesystem_avail_bytes / node_filesystem_size_bytes",
            "legendFormat": "{{mountpoint}}"
          },
          {
            "expr": "predict_linear(node_filesystem_avail_bytes[7d], 86400 * 30)",
            "legendFormat": "30天预测",
            "dashPattern": "dot"
          }
        ]
      },
      {
        "title": "内存增长趋势",
        "type": "timeseries",
        "targets": [
          {
            "expr": "process_resident_memory_bytes / 1024 / 1024",
            "legendFormat": "{{instance}} (MB)"
          }
        ]
      },
      {
        "title": "AI 健康评分",
        "type": "gauge",
        "targets": [
          {
            "expr": "vps_health_score",
            "legendFormat": "Health Score"
          }
        ]
      }
    ]
  }
}
```

## 最佳实践与注意事项

### 安全边界

1. **干跑优先**：所有自动修复操作默认启用 `dry_run` 模式，先观察再执行
2. **白名单机制**：只有标记为 `Action.SAFE` 的操作可以自动执行
3. **操作审计**：所有自动执行的操作记录到日志，便于追溯
4. **熔断机制**：连续失败3次后自动停止自愈，转为人工告警

### 性能优化

1. **采样频率**：生产环境建议 15-60 秒采样，避免过高频率影响性能
2. **数据保留**：原始指标保留30天，聚合数据保留90天
3. **LLM 调用限流**：对 LLM API 设置速率限制，避免过度消耗

### 成本考量

| 组件 | 资源需求 | 月成本估算 |
|------|---------|-----------|
| Prometheus | 512MB RAM, 1 CPU | 免费 (自托管) |
| Grafana | 256MB RAM | 免费 |
| Loki | 256MB RAM | 免费 |
| Ollama (小模型) | 2GB RAM | 免费 |
| **总计** | **~2GB RAM, 2 CPU** | **≈ $5-10/月** |

## 总结

通过构建这套 **AI 驱动的 VPS 预测性维护系统**，你可以实现：

- ✅ **提前发现**：在故障发生前数天预警磁盘满载、内存泄漏等问题
- ✅ **自动修复**：对已知问题类型自动执行安全修复操作
- ✅ **智能诊断**：LLM 综合分析多维度数据，给出专业级根因分析
- ✅ **可读报告**：每日自动生成自然语言巡检报告，一目了然

这套系统的核心价值在于**将运维从被动响应转变为主动预防**。与其在半夜被告警电话叫醒，不如每天花一分钟查看 AI 生成的巡检报告，提前处理潜在问题。

> 💡 **下一步**：可以从最简单的磁盘容量预测开始，逐步添加内存泄漏检测、日志分析和自动修复功能。每个模块都可以独立运行，按需组合。
