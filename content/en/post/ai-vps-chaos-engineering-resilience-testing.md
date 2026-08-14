---
title: "AI-Driven VPS Chaos Engineering: Automated Fault Injection & Resilience Testing"
description: "Use AI Agents to drive chaos engineering — automated fault injection, system behavior monitoring, intelligent recovery. Make your VPS services resilient against real-world failures, from reactive firefighting to proactive resilience building."
date: 2026-08-14T20:00:00+08:00
lastmod: 2026-08-14T20:00:00+08:00
slug: "ai-vps-chaos-engineering-resilience-testing"
image: /images/posts/ai-vps-chaos-engineering-resilience-testing/featured.png
tags: ["AI Agent", "VPS", "Chaos Engineering", "Fault Injection", "Resilience Testing", "SRE", "Automated Operations", "High Availability"]
categories: ["AI Operations"]
aliases: [/en/post/ai-vps-chaos-engineering-resilience-testing/]
draft: false
---

## Introduction

Is your VPS service really "resilient"?

- Database slow queries spike API response times from 50ms to 5s;
- Disk space fills up with logs, taking down all services;
- A dependent microservice times out, causing cascading failures;
- Memory leaks accumulate slowly, rendering the website unreachable after a week;
- SSL certificates expire, Cron jobs fail, processes deadlock...

These failures are not a question of **if** they will happen, but **when**. Traditional ops responds reactively — you troubleshoot after problems occur. But users won't wait for your investigation. **Chaos Engineering** takes a different approach: **proactively inject failures in a controlled environment to verify system resilience and discover vulnerabilities before they cause real outages.**

In 2026, LLM and AI Agent technology makes chaos engineering前所未有地 simple. You no longer need to manually write fault scripts, manually observe results, and manually analyze root causes — **AI Agents can automate the entire chaos engineering loop.**

This article walks you through building an **AI-driven VPS chaos engineering system**, achieving full automation from fault injection, behavior monitoring, root cause analysis, to automatic recovery.

---

## 1. What is Chaos Engineering? Why Does VPS Need It?

### 1.1 Core Concepts

Chaos Engineering originated from Netflix's Chaos Monkey project, with the core philosophy:

> **Proactively inject failures in a controlled environment to verify whether the system can remain available during real failures.**

Traditional testing focuses on "can the system work correctly," while chaos engineering focuses on **"can the system remain available when things go wrong."**

| Traditional Testing | Chaos Engineering |
|-------------------|-------------------|
| Verifies normal operation | Verifies availability during failures |
| Focuses on functional correctness | Focuses on resilience |
| One-time testing | Continuous verification |
| Manual execution | Automatable |

### 1.2 Chaos Engineering Value for VPS

For VPS users, chaos engineering has unique value:

1. **High single-point-of-failure risk**: Most VPS users have only one server; any failure means total outage
2. **Resource constraints**: Limited VPS resources can cause cascading failures under overload
3. **Lack of redundancy**: No replicas, no automatic failover — one failure can mean permanent downtime
4. **Limited ops manpower**: Solo operators or small teams can't monitor 24/7

AI-driven chaos engineering helps you discover system vulnerabilities **before real failures occur** and automatically fix them.

---

## 2. System Architecture: AI-Driven Chaos Engineering Platform

```
┌─────────────────────────────────────────────────────────────┐
│                    AI Chaos Engineering Platform              │
├─────────────┬─────────────┬─────────────┬───────────────────┤
│  Chaos      │  Monitor    │  AI         │  Remediation     │
│  Engine     │  Layer      │  Analysis   │  Engine          │
│             │             │  Layer      │                  │
│  • Fault    │  • Real-time│  • Root     │  • Auto-fix      │
│    injection│    metrics  │    cause    │  • Config rollback│
│  • Scenario │  • Log      │    analysis │  • Verify restore │
│    management│   collection│  • Pattern  │                  │
│  • Experiment│  • Alert    │    detection│                  │
│    scheduling│   generation│  • Decision │                  │
└──────┬──────┴──────┬──────┴──────┬──────┴────────┬──────────┘
       │             │             │               │
       └─────────────┴─────────────┴───────────────┘
                          │
                          ▼
               ┌─────────────────────┐
               │     Target VPS      │
               │  (Production Env)   │
               └─────────────────────┘
```

### Core Components

1. **Chaos Engine**: Responsible for injecting various types of faults
2. **Monitor Layer**: Collects metrics, logs, and tracing data in real-time
3. **AI Analysis Layer**: Uses LLM to analyze fault impact, locate root causes, generate decisions
4. **Remediation Engine**: Automatically executes repair operations and verifies recovery

---

## 3. Fault Injection: AI Agent Automated Experiment Design

### 3.1 Common Fault Types

Chaos engineering requires injecting many fault types. AI Agents can automatically select the most relevant scenarios based on system architecture:

```python
# Fault type definitions
CHAOS_SCENARIOS = {
    "cpu_stress": {
        "name": "CPU Stress Test",
        "description": "Consume 80%+ CPU, simulating compute-intensive load",
        "methods": ["stress-ng --cpu 4 --timeout 60s", "yes > /dev/null &"],
        "risk_level": "low",
        "duration": "60s"
    },
    "memory_pressure": {
        "name": "Memory Pressure Test",
        "description": "Allocate大量 memory until OOM triggered, simulating memory leak",
        "methods": ["stress-ng --vm 2 --vm-bytes 80%", "dd if=/dev/zero of=/tmp/bigfile bs=1M count=2000"],
        "risk_level": "medium",
        "duration": "120s"
    },
    "disk_full": {
        "name": "Disk Space Exhaustion",
        "description": "Fill disk to 95%+, simulating write failures from full disk",
        "methods": ["dd if=/dev/zero of=/tmp/filldisk bs=1M count=10000"],
        "risk_level": "high",
        "duration": "30s"
    },
    "network_partition": {
        "name": "Network Partition",
        "description": "Block specific ports or IPs, simulating network interruption",
        "methods": ["iptables -A OUTPUT -d 10.0.0.5 -j DROP", "tc qdisc add dev eth0 root netem delay 5000ms"],
        "risk_level": "high",
        "duration": "30s"
    },
    "process_kill": {
        "name": "Process Termination",
        "description": "Randomly kill关键 service processes, simulating process crashes",
        "methods": ["pkill -f nginx", "systemctl stop postgresql"],
        "risk_level": "high",
        "duration": "immediate"
    },
    "dependency_failure": {
        "name": "Dependency Service Failure",
        "description": "Simulate Redis/MySQL dependency service unavailability",
        "methods": ["docker kill redis", "systemctl stop mysql"],
        "risk_level": "medium",
        "duration": "30s"
    },
    "clock_skew": {
        "name": "Clock Skew",
        "description": "Modify system time, simulating clock drift causing auth failures",
        "methods": ["date -s '2027-01-01 00:00:00'", "chronyd -s"],
        "risk_level": "medium",
        "duration": "10s"
    }
}
```

### 3.2 AI Agent Intelligent Scenario Selection

AI Agents don't randomly inject faults — they **select the most appropriate fault scenario based on current system state and architecture**:

```python
import asyncio
from langchain.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

class ChaosAgent:
    def __init__(self, llm):
        self.llm = llm
        self.system_state = {}
    
    async def select_chaos_scenario(self, system_info: dict) -> dict:
        """AI selects the most appropriate chaos experiment scenario based on system state"""
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a chaos engineering expert.
            Based on the current system state, select the most appropriate fault injection scenario.
            Prioritize scenarios that may expose system vulnerabilities, not obvious problems.
            Return JSON format: {scenario, reason, expected_impact, safety_check}"""),
            ("human", """Current system state:
            - Architecture: {architecture}
            - Key services: {services}
            - Current load: {load}
            - Recent incidents: {recent_incidents}
            - Backup status: {backup_status}
            - Available resources: {available_resources}
            
            Analyze and select the most appropriate chaos experiment scenario.""")
        ])
        
        chain = prompt | self.llm
        response = await chain.ainvoke({
            "architecture": system_info.get("architecture", ""),
            "services": ", ".join(system_info.get("services", [])),
            "load": system_info.get("load", ""),
            "recent_incidents": system_info.get("recent_incidents", "None"),
            "backup_status": system_info.get("backup_status", ""),
            "available_resources": system_info.get("available_resources", "")
        })
        
        return response.content
    
    async def validate_safety(self, scenario: dict, system_info: dict) -> bool:
        """AI validates whether fault injection is safe"""
        safety_checks = [
            "Confirm recent backup exists",
            "Confirm key services have restart mechanism",
            "Confirm injection time is not during business peak",
            "Confirm rollback plan exists",
            "Confirm monitoring alerts are enabled"
        ]
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a chaos engineering safety expert. Check if the following fault injection is safe."),
            ("human", """Scenario: {scenario}
            System state: {system_info}
            Safety checks: {safety_checks}
            
            Check each item, return SAFE/UNSAFE with reasons.""")
        ])
        
        chain = prompt | self.llm
        response = await chain.ainvoke({
            "scenario": scenario,
            "system_info": system_info,
            "safety_checks": "\n".join(safety_checks)
        })
        
        return "SAFE" in response.content
```

### 3.3 Automated Fault Injection Execution

```python
import subprocess
import asyncio
from dataclasses import dataclass
from enum import Enum

class RiskLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

@dataclass
class ChaosResult:
    scenario: str
    status: str  # success, failed, interrupted
    duration: float
    impact: dict
    recovery_time: float
    errors: list

class ChaosEngine:
    def __init__(self):
        self.executed_scenarios = []
        self.safety_lock = asyncio.Lock()
    
    async def execute_scenario(self, scenario_name: str, params: dict = None) -> ChaosResult:
        """Execute a chaos experiment"""
        import time
        start_time = time.time()
        
        try:
            # Get fault injection commands
            commands = self._get_commands(scenario_name)
            
            # Execute fault injection (async)
            tasks = [self._run_command(cmd) for cmd in commands]
            await asyncio.gather(*tasks, return_exceptions=True)
            
            # Wait for expected duration
            await asyncio.sleep(scenario.get("duration", 30))
            
            # Cleanup fault injection
            await self._cleanup(scenario_name)
            
            duration = time.time() - start_time
            
            return ChaosResult(
                scenario=scenario_name,
                status="success",
                duration=duration,
                impact=await self._measure_impact(),
                recovery_time=duration,
                errors=[]
            )
            
        except Exception as e:
            return ChaosResult(
                scenario=scenario_name,
                status="failed",
                duration=time.time() - start_time,
                impact={},
                recovery_time=0,
                errors=[str(e)]
            )
    
    def _get_commands(self, scenario: str) -> list:
        """Return fault injection commands based on scenario"""
        commands_map = {
            "cpu_stress": ["stress-ng --cpu 4 --timeout 60s"],
            "memory_pressure": ["stress-ng --vm 2 --vm-bytes 80% --timeout 120s"],
            "disk_full": ["dd if=/dev/zero of=/tmp/filldisk bs=1M count=10000"],
            "network_partition": ["iptables -A OUTPUT -d 10.0.0.5 -j DROP"],
            "process_kill": ["pkill -f nginx"],
            "dependency_failure": ["docker kill redis"],
            "clock_skew": ["date -s '2027-01-01 00:00:00'"]
        }
        return commands_map.get(scenario, [])
    
    async def _run_command(self, cmd: str):
        """Async command execution"""
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        return stdout, stderr
    
    async def _cleanup(self, scenario: str):
        """Cleanup fault injection, restore system"""
        cleanup_commands = {
            "cpu_stress": ["pkill stress-ng"],
            "memory_pressure": ["pkill stress-ng", "swapoff -a && swapon -a"],
            "disk_full": ["rm -f /tmp/filldisk"],
            "network_partition": ["iptables -D OUTPUT -d 10.0.0.5 -j DROP"],
            "process_kill": ["systemctl start nginx"],
            "dependency_failure": ["docker start redis"],
            "clock_skew": ["systemctl restart chronyd"]
        }
        for cmd in cleanup_commands.get(scenario, []):
            await self._run_command(cmd)
    
    async def _measure_impact(self) -> dict:
        """Measure fault injection impact"""
        return {
            "cpu_usage": await self._get_metric("cpu"),
            "memory_usage": await self._get_metric("memory"),
            "disk_usage": await self._get_metric("disk"),
            "response_time": await self._get_metric("response_time"),
            "error_rate": await self._get_metric("error_rate"),
            "service_status": await self._check_services()
        }
```

---

## 4. Monitor Layer: Real-time Data Collection & Anomaly Detection

### 4.1 Multi-dimensional Data Collection

Chaos engineering requires comprehensive data collection to assess fault impact:

```python
import psutil
import asyncio
import aiohttp
from datetime import datetime, timedelta

class MonitorLayer:
    def __init__(self):
        self.metrics_history = []
        self.baseline = {}
    
    async def collect_all_metrics(self) -> dict:
        """Collect all dimensions of monitoring data"""
        metrics = {
            "timestamp": datetime.now().isoformat(),
            "system": await self._collect_system_metrics(),
            "application": await self._collect_app_metrics(),
            "network": await self._collect_network_metrics(),
            "logs": await self._collect_recent_logs(),
            "services": await self._check_service_status()
        }
        
        self.metrics_history.append(metrics)
        return metrics
    
    async def _collect_system_metrics(self) -> dict:
        """System-level metrics"""
        return {
            "cpu_percent": psutil.cpu_percent(interval=1),
            "cpu_count": psutil.cpu_count(),
            "memory_total": psutil.virtual_memory().total,
            "memory_available": psutil.virtual_memory().available,
            "memory_percent": psutil.virtual_memory().percent,
            "disk_total": psutil.disk_usage('/').total,
            "disk_used": psutil.disk_usage('/').used,
            "disk_percent": psutil.disk_usage('/').percent,
            "load_avg": psutil.getloadavg(),
            "processes": psutil.pids()
        }
    
    async def _collect_app_metrics(self) -> dict:
        """Application-level metrics"""
        health_checks = {}
        services = ["nginx", "postgresql", "redis", "app"]
        
        for service in services:
            health_checks[service] = await self._check_service_health(service)
        
        return health_checks
    
    async def _collect_network_metrics(self) -> dict:
        """Network metrics"""
        net_io = psutil.net_io_counters()
        return {
            "bytes_sent": net_io.bytes_sent,
            "bytes_recv": net_io.bytes_recv,
            "packets_sent": net_io.packets_sent,
            "packets_recv": net_io.packets_recv,
            "connections": len(psutil.net_connections())
        }
    
    async def _collect_recent_logs(self, minutes: int = 5) -> list:
        """Collect recent logs"""
        cmd = f"journalctl -u nginx --since '{(datetime.now() - timedelta(minutes=minutes)).isoformat()}' --no-pager -n 50"
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            return stdout.decode().strip().split('\n')[:20]
        except:
            return []
    
    async def _check_service_health(self, service: str) -> dict:
        """Check service health status"""
        running = await self._is_service_running(service)
        http_status = None
        if service in ["nginx", "app"] and running:
            http_status = await self._check_http_health(service)
        
        return {
            "running": running,
            "http_status": http_status,
            "uptime": await self._get_uptime(service)
        }
    
    async def _is_service_running(self, service: str) -> bool:
        """Check if service is running"""
        proc = await asyncio.create_subprocess_shell(
            f"systemctl is-active {service}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        return stdout.decode().strip() == "active"
```

### 4.2 Baseline Comparison & Anomaly Detection

```python
class AnomalyDetector:
    def __init__(self, window_size: int = 100):
        self.window_size = window_size
        self.baselines = {}
    
    def update_baseline(self, metrics: dict):
        """Update baseline"""
        for key, value in metrics.items():
            if isinstance(value, (int, float)):
                if key not in self.baselines:
                    self.baselines[key] = []
                self.baselines[key].append(value)
                if len(self.baselines[key]) > self.window_size:
                    self.baselines[key] = self.baselines[key][-self.window_size:]
    
    def detect_anomaly(self, current_metrics: dict) -> dict:
        """Detect anomalies"""
        anomalies = {}
        
        for key, value in current_metrics.items():
            if key not in self.baselines or len(self.baselines[key]) < 10:
                continue
            
            baseline = self.baselines[key]
            mean = sum(baseline) / len(baseline)
            std = (sum((x - mean) ** 2 for x in baseline) / len(baseline)) ** 0.5
            
            if std == 0:
                std = 1
            
            # Z-score anomaly detection
            z_score = abs(value - mean) / std
            
            if z_score > 3:  # More than 3 standard deviations = anomaly
                anomalies[key] = {
                    "current": value,
                    "baseline_mean": mean,
                    "z_score": z_score,
                    "severity": "high" if z_score > 5 else "medium"
                }
        
        return anomalies
    
    def get_alert_message(self, anomalies: dict) -> str:
        """Generate alert message"""
        if not anomalies:
            return "System running normally, no anomalies detected"
        
        messages = []
        for key, info in anomalies.items():
            severity = "⚠️" if info["severity"] == "medium" else "🚨"
            messages.append(
                f"{severity} {key}: current {info['current']:.2f}, "
                f"baseline mean {info['baseline_mean']:.2f}, "
                f"Z-score {info['z_score']:.2f}"
            )
        
        return "\n".join(messages)
```

---

## 5. AI Analysis Layer: Root Cause Analysis & Intelligent Decision Making

### 5.1 LLM-Driven Root Cause Analysis

```python
from langchain.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
import json

class AIAnalysisLayer:
    def __init__(self, llm: ChatOpenAI):
        self.llm = llm
    
    async def analyze_chaos_result(self, chaos_result: ChaosResult, 
                                    metrics_before: dict, 
                                    metrics_after: dict,
                                    anomalies: dict) -> dict:
        """AI analyzes chaos experiment results"""
        
        context = f"""
        Chaos Experiment: {chaos_result.scenario}
        Result: {chaos_result.status}
        Duration: {chaos_result.duration:.1f}s
        Recovery Time: {chaos_result.recovery_time:.1f}s
        Errors Injected: {', '.join(chaos_result.errors) if chaos_result.errors else 'None'}
        
        Metrics Before: {json.dumps(metrics_before, default=str, indent=2)}
        Metrics After: {json.dumps(metrics_after, default=str, indent=2)}
        
        Detected Anomalies:
        {json.dumps(anomalies, indent=2) if anomalies else 'None'}
        """
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are an SRE expert specializing in chaos engineering and root cause analysis.
            Analyze the following chaos experiment results, answer:
            1. Did the system exhibit expected failure behavior?
            2. What is the scope and severity of the failure?
            3. What is the root cause?
            4. What resilience characteristics did the system show (auto-restart, degradation, circuit breaking)?
            5. What improvement recommendations?
            
            Return JSON format."""),
            ("human", context)
        ])
        
        chain = prompt | self.llm
        response = await chain.ainvoke({})
        
        try:
            analysis = json.loads(response.content)
        except:
            analysis = {"raw_analysis": response.content}
        
        return analysis
    
    async def generate_resilience_report(self, all_results: list) -> str:
        """Generate resilience report"""
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are an SRE expert. Generate a resilience assessment report based on chaos engineering experiment results.
            Report should include:
            1. Experiment overview
            2. Discovered vulnerabilities
            3. System resilience performance
            4. Improvement recommendations
            5. Priority ranking"""),
            ("human", """Here are the chaos engineering experiment results summary:
            {results}
            
            Please generate a complete resilience assessment report.""")
        ])
        
        chain = prompt | self.llm
        response = await chain.ainvoke({"results": all_results})
        
        return response.content
```

### 5.2 Intelligent Decision: When to Inject, When to Abort

```python
class ChaosDecisionEngine:
    def __init__(self, llm: ChatOpenAI):
        self.llm = llm
        self.experiment_log = []
    
    async def should_inject(self, system_state: dict, pending_scenarios: list) -> dict:
        """Decide whether to inject the next fault"""
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a chaos engineering scheduling expert.
            Based on current system state, decide whether to inject the next fault.
            Consider:
            1. Is current system load too high?
            2. Is a critical business operation in progress?
            3. Did previous experiments reveal unrepaired issues?
            4. Is there sufficient monitoring coverage?
            
            Return JSON: {should_inject, reason, next_scenario, priority}"""),
            ("human", """Current system state:
            - CPU: {cpu}%
            - Memory: {memory}%
            - Disk: {disk}%
            - Current time: {time}
            - Recent experiment results: {last_results}
            - Pending scenarios: {pending}""")
        ])
        
        chain = prompt | self.llm
        response = await chain.ainvoke({
            "cpu": system_state.get("cpu", 0),
            "memory": system_state.get("memory", 0),
            "disk": system_state.get("disk", 0),
            "time": system_state.get("time", ""),
            "last_results": str(self.experiment_log[-3:]) if self.experiment_log else "None",
            "pending": str(pending_scenarios)
        })
        
        try:
            decision = json.loads(response.content)
        except:
            decision = {"should_inject": False, "reason": "Parse failed", "next_scenario": "", "priority": "low"}
        
        return decision
    
    async def should_abort(self, current_metrics: dict, anomalies: dict) -> bool:
        """Decide whether to abort current experiment"""
        
        # Hard abort conditions
        hard_abort_conditions = [
            ("disk_percent", 95),
            ("memory_percent", 95),
            ("cpu_percent", 98)
        ]
        
        for metric, threshold in hard_abort_conditions:
            if metric in current_metrics and current_metrics[metric] > threshold:
                return True
        
        # AI-assisted decision
        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a chaos engineering safety expert. Determine if the current experiment should be aborted."),
            ("human", """Current metrics: {metrics}
            Anomaly detection: {anomalies}
            
            If risk is too high, return "ABORT", otherwise return "CONTINUE".
            """)
        ])
        
        chain = prompt | self.llm
        response = await chain.ainvoke({
            "metrics": current_metrics,
            "anomalies": anomalies
        })
        
        return "ABORT" in response.content
```

---

## 6. Automatic Remediation: From Fault Injection to Self-Healing Loop

### 6.1 Auto-Remediation Engine

```python
class RemediationEngine:
    def __init__(self):
        self.remediation_history = []
    
    async def auto_remediate(self, chaos_result: ChaosResult, analysis: dict) -> dict:
        """Automatically remediate faults introduced by chaos experiment"""
        
        remediation_plan = analysis.get("remediation_plan", [])
        results = {}
        
        for step in remediation_plan:
            action = step.get("action", "")
            command = step.get("command", "")
            
            try:
                # Execute remediation command
                proc = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await proc.communicate()
                
                # Verify remediation effect
                post_fix_metrics = await self._collect_metrics()
                is_fixed = self._verify_remediation(chaos_result, post_fix_metrics)
                
                results[action] = {
                    "command": command,
                    "success": proc.returncode == 0,
                    "verified": is_fixed,
                    "stdout": stdout.decode()[:500],
                    "stderr": stderr.decode()[:500]
                }
                
                self.remediation_history.append({
                    "action": action,
                    "command": command,
                    "success": proc.returncode == 0,
                    "verified": is_fixed,
                    "timestamp": datetime.now().isoformat()
                })
                
            except Exception as e:
                results[action] = {
                    "success": False,
                    "error": str(e)
                }
        
        return results
    
    def _verify_remediation(self, chaos_result: ChaosResult, metrics: dict) -> bool:
        """Verify remediation success"""
        critical_metrics = ["cpu_percent", "memory_percent", "disk_percent"]
        
        for metric in critical_metrics:
            if metric in metrics:
                if metrics[metric] > 80:  # Recovery threshold
                    return False
        
        return True
    
    async def _collect_metrics(self) -> dict:
        """Collect post-remediation metrics"""
        return {
            "cpu_percent": psutil.cpu_percent(interval=1),
            "memory_percent": psutil.virtual_memory().percent,
            "disk_percent": psutil.disk_usage('/').percent
        }
```

### 6.2 Complete Closed-Loop Flow

```python
import asyncio
from datetime import datetime

class ChaosEngineeringLoop:
    """Complete chaos engineering closed loop"""
    
    def __init__(self):
        self.chaos_agent = ChaosAgent(llm=ChatOpenAI(model="gpt-4o"))
        self.chaos_engine = ChaosEngine()
        self.monitor = MonitorLayer()
        self.anomaly_detector = AnomalyDetector()
        self.ai_analyzer = AIAnalysisLayer(llm=ChatOpenAI(model="gpt-4o"))
        self.decision_engine = ChaosDecisionEngine(llm=ChatOpenAI(model="gpt-4o"))
        self.remediation = RemediationEngine()
    
    async def run_experiment(self, scenario: str, params: dict = None) -> dict:
        """Run a complete chaos experiment"""
        
        print(f"🔬 Starting chaos experiment: {scenario}")
        
        # 1. Collect baseline metrics
        print("📊 Collecting baseline metrics...")
        baseline_metrics = await self.monitor.collect_all_metrics()
        self.anomaly_detector.update_baseline(baseline_metrics["system"])
        
        # 2. Execute fault injection
        print(f"💥 Injecting fault: {scenario}")
        chaos_result = await self.chaos_engine.execute_scenario(scenario, params)
        
        # 3. Collect during-fault metrics
        print("📈 Collecting during-fault metrics...")
        during_metrics = await self.monitor.collect_all_metrics()
        anomalies = self.anomaly_detector.detect_anomaly(during_metrics["system"])
        
        # 4. AI analysis
        print("🧠 AI analyzing...")
        analysis = await self.ai_analyzer.analyze_chaos_result(
            chaos_result, baseline_metrics["system"],
            during_metrics["system"], anomalies
        )
        
        # 5. Automatic remediation
        print("🔧 Auto-remediating...")
        remediation_results = await self.remediation.auto_remediate(chaos_result, analysis)
        
        # 6. Verify recovery
        print("✅ Verifying recovery status...")
        post_remediation = await self.monitor.collect_all_metrics()
        is_resilient = self._check_resilience(baseline_metrics, post_remediation)
        
        # 7. Generate report
        report = {
            "scenario": scenario,
            "timestamp": datetime.now().isoformat(),
            "chaos_result": chaos_result.__dict__,
            "analysis": analysis,
            "remediation": remediation_results,
            "is_resilient": is_resilient,
            "recommendations": analysis.get("recommendations", [])
        }
        
        print(f"📋 Experiment complete: {'✅ PASSED' if is_resilient else '❌ FAILED'}")
        return report
    
    def _check_resilience(self, before: dict, after: dict) -> bool:
        """Check system resilience"""
        resilience_thresholds = {
            "cpu_percent": 30,
            "memory_percent": 50,
            "disk_percent": 80
        }
        
        for metric, threshold in resilience_thresholds.items():
            before_val = before.get(metric, 0)
            after_val = after.get(metric, 0)
            
            # After recovery should not exceed 120% of baseline
            if after_val > before_val * 1.2 and after_val > threshold:
                return False
        
        return True
    
    async def run_battery_test(self, scenarios: list, interval: int = 60):
        """Run chaos experiment battery test"""
        results = []
        
        for scenario in scenarios:
            # AI decides whether to continue
            system_state = await self.monitor.collect_all_metrics()
            decision = await self.decision_engine.should_inject(
                system_state["system"], scenarios[len(results):]
            )
            
            if not decision.get("should_inject", False):
                print(f"⏸️ Skipping {scenario}: {decision.get('reason', 'unknown reason')}")
                continue
            
            # Execute experiment
            report = await self.run_experiment(scenario)
            results.append(report)
            
            # Interval wait
            if interval > 0:
                await asyncio.sleep(interval)
        
        # Generate overall report
        summary = await self.ai_analyzer.generate_resilience_report(results)
        
        return {
            "experiments": results,
            "summary": summary,
            "total": len(results),
            "passed": sum(1 for r in results if r["is_resilient"]),
            "failed": sum(1 for r in results if not r["is_resilient"])
        }
```

---

## 7. Practical Deployment: Building Chaos Engineering Platform on VPS

### 7.1 Project Structure

```
chaos-vps/
├── chaos_engine/
│   ├── __init__.py
│   ├── agent.py          # AI Agent
│   ├── engine.py         # Fault injection engine
│   ├── monitor.py        # Monitor layer
│   ├── analyzer.py       # AI analysis layer
│   ├── remediation.py    # Auto-remediation
│   └── decision.py       # Decision engine
├── scenarios/
│   ├── cpu_stress.py
│   ├── memory_pressure.py
│   ├── disk_full.py
│   ├── network_partition.py
│   └── process_kill.py
├── config.yaml           # Configuration
├── main.py               # Main entry
└── requirements.txt
```

### 7.2 Configuration File

```yaml
# config.yaml
chaos:
  # Safety settings
  safety:
    max_cpu_threshold: 90
    max_memory_threshold: 90
    max_disk_threshold: 90
    abort_on_critical: true
    require_manual_approval: false
  
  # Scheduling settings
  scheduling:
    default_interval: 300  # Experiment interval (seconds)
    max_concurrent: 1      # Max concurrent experiments
    preferred_time_range:   # Recommended execution time
      start: "02:00"
      end: "06:00"
  
  # Scenario settings
  scenarios:
    enabled:
      - cpu_stress
      - memory_pressure
      - disk_full
      - process_kill
    disabled:
      - clock_skew  # High-risk scenario, disabled by default
    
  # LLM settings
  llm:
    model: "gpt-4o"
    temperature: 0.3
    max_tokens: 2048
  
  # Monitoring settings
  monitoring:
    collection_interval: 10  # Seconds
    baseline_window: 100     # Baseline window size
    anomaly_z_threshold: 3   # Z-score anomaly threshold
  
  # Remediation settings
  remediation:
    auto_remediate: true
    verify_after_fix: true
    max_retry: 3
```

### 7.3 Main Entry

```python
# main.py
import asyncio
import yaml
from chaos_engine.agent import ChaosAgent
from chaos_engine.engine import ChaosEngine
from chaos_engine.monitor import MonitorLayer
from chaos_engine.analyzer import AIAnalysisLayer
from chaos_engine.remediation import RemediationEngine
from chaos_engine.decision import ChaosDecisionEngine

async def main():
    # Load configuration
    with open("config.yaml") as f:
        config = yaml.safe_load(f)
    
    # Initialize components
    monitor = MonitorLayer()
    anomaly_detector = AnomalyDetector()
    
    chaos_engine = ChaosEngine()
    chaos_agent = ChaosAgent(llm=None)  # Optional: LLM-assisted scenario selection
    ai_analyzer = AIAnalysisLayer(llm=None)
    decision_engine = ChaosDecisionEngine(llm=None)
    remediation = RemediationEngine()
    
    print("🚀 VPS Chaos Engineering Platform Started")
    print(f"📋 Enabled scenarios: {config['chaos']['scenarios']['enabled']}")
    print(f"⏰ Safety thresholds: CPU={config['chaos']['safety']['max_cpu_threshold']}%")
    print(f"🔒 Auto-remediation: {config['chaos']['remediation']['auto_remediate']}")
    
    # Run chaos experiment battery
    results = await chaos_engine.run_battery_test(
        scenarios=config['chaos']['scenarios']['enabled'],
        interval=config['chaos']['scheduling']['default_interval']
    )
    
    # Output report
    print("\n" + "="*50)
    print("📊 Chaos Engineering Experiment Report")
    print("="*50)
    print(f"Total experiments: {results['total']}")
    print(f"Passed: {results['passed']}")
    print(f"Failed: {results['failed']}")
    print(f"\nResilience assessment summary:\n{results['summary']}")

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 8. Practical Case: A Complete Chaos Experiment

### 8.1 Scenario: CPU Stress Test

```
🔬 Starting chaos experiment: cpu_stress
📊 Collecting baseline metrics...
   CPU: 12%, Memory: 45%, Disk: 62%
💥 Injecting fault: stress-ng --cpu 4 --timeout 60s
📈 Collecting during-fault metrics...
   CPU: 95%, Memory: 48%, Disk: 62%
   Anomaly detection: cpu_percent Z-score=8.2 (high)
🧠 AI analyzing...
   - System CPU usage spiked from 12% to 95%
   - API response time increased from 50ms to 800ms
   - No service crashes or data loss detected
   - System showed good resilience: services didn't crash, only slowed under pressure
   - Recommendation: Consider adding CPU cores or configuring CPU limits
🔧 Auto-remediating...
   - Executing: pkill stress-ng
   - Verifying: CPU back to normal (15%)
✅ Verifying recovery status...
📋 Experiment complete: ✅ PASSED
```

### 8.2 Scenario: Disk Space Exhaustion

```
🔬 Starting chaos experiment: disk_full
📊 Collecting baseline metrics...
   CPU: 15%, Memory: 48%, Disk: 62%
💥 Injecting fault: dd if=/dev/zero of=/tmp/filldisk bs=1M count=10000
📈 Collecting during-fault metrics...
   CPU: 25%, Memory: 50%, Disk: 96%
   Anomaly detection: disk_percent Z-score=12.5 (high)
   Service status: nginx write failed, PostgreSQL WAL write failed
🧠 AI analyzing...
   - Disk space exhaustion caused multiple service write failures
   - PostgreSQL entered read-only mode
   - Nginx couldn't write access logs
   - System resilience insufficient: key services failed due to full disk
   - Recommendations:
     1. Configure disk usage alerts (>80%)
     2. Implement log rotation and cleanup policies
     3. Add disk space monitoring for PostgreSQL
🔧 Auto-remediating...
   - Executing: rm -f /tmp/filldisk
   - Executing: systemctl restart postgresql
   - Executing: systemctl restart nginx
   - Verifying: All services recovered
✅ Verifying recovery status...
📋 Experiment complete: ❌ FAILED (but auto-remediated)
```

---

## 9. Best Practices & Considerations

### 9.1 Chaos Engineering Best Practices

| Practice | Description |
|----------|-------------|
| **Start with low risk** | Begin with CPU/memory pressure, then try network partition |
| **Establish baselines** | Collect normal-state metric baselines before experiments |
| **Gradually expand scope** | Single service → Multi-service → Full system |
| **Keep it reversible** | Ensure each experiment can be quickly recovered |
| **Make it continuous** | Chaos engineering is not one-time; run regularly |
| **Record all experiments** | Build experiment logs, track system resilience changes |

### 9.2 Safety Considerations

1. **Be cautious in production**: First run in test environment; production requires manual approval
2. **Backup first**: Ensure recent backups exist to prevent data loss
3. **Off-peak hours**: Choose low-traffic periods for high-risk experiments
4. **Complete monitoring**: Ensure complete monitoring and alerting to detect issues promptly
5. **Manual abort**: Keep manual abort switch; AI decisions should not completely replace human judgment

### 9.3 Integration with Existing Ops Systems

```
┌──────────────────────────────────────────────────────┐
│         Chaos Engineering Integration with Existing  │
├──────────────────────────────────────────────────────┤
│                                                      │
│  Prometheus ──▶ Chaos Engine (Data Collection)       │
│      │                                              │
│      ▼                                              │
│  Grafana ──▶ Chaos Experiment Result Visualization   │
│      │                                              │
│      ▼                                              │
│  Alertmanager ──▶ AI Agent (Intelligent Alerting)    │
│      │                                              │
│      ▼                                              │
│  PagerDuty/Opsgenie ──▶ Auto-remediation Trigger     │
│      │                                              │
│      ▼                                              │
│  Ansible/Terraform ──▶ Config Rollback & Repair      │
│      │                                              │
│      ▼                                              │
│  Git ──▶ Experiment Report Version Control           │
│                                                      │
└──────────────────────────────────────────────────────┘
```

---

## 10. Summary

AI-driven chaos engineering transforms VPS ops from "reactive firefighting" to "proactive defense":

1. **AI Agent intelligent scenario selection** — not random injection, but selecting the most valuable experiment based on system state
2. **Automated fault injection and recovery** — from injection to cleanup, fully automated, no manual intervention needed
3. **LLM root cause analysis** — understand fault impact, locate root causes, generate improvement recommendations
4. **Closed-loop self-healing** — auto-remediate immediately after fault injection, verify system resilience
5. **Continuous improvement** — each experiment accumulates data, continuously optimizing system architecture

**Core benefits**:
- Discover system vulnerabilities before real failures occur
- Reduce production environment failure rate and MTTR (Mean Time To Recovery)
- Establish quantitative understanding of system resilience
- Cultivate an ops culture of "failures are normal, resilience is key"

**Next steps**:
1. Deploy chaos engineering platform in test environment
2. Start with CPU stress tests, gradually increase scenarios
3. Incorporate experiment results into ops decisions
4. Establish regular chaos engineering experiment cadence

---

*Reference Resources*:
- [Netflix Chaos Engineering Practice](https://www.chaostoolkit.org/)
- [Google SRE Chaos Engineering Guide](https://sre.google/workbook/chaos-engineering/)
- [Chaos Toolkit Open Source](https://chaostoolkit.org/)
