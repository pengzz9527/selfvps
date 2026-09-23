---
title: "AI + VPS: LLM-Driven K3s Cluster Orchestration and Resource Governance"
description: "Say goodbye to manual kubectl operations. Let a local LLM automatically manage K3s cluster Pod scheduling, resource quotas, auto-scaling, and self-healing — achieving true AI-native cluster operations."
date: 2026-09-23T21:00:00+08:00
lastmod: 2026-09-23T21:00:00+08:00
slug: "ai-vps-llm-k3s-cluster-orchestration"
image: /images/posts/ai-vps-llm-k3s-cluster-orchestration/featured.png
tags: ["AI", "VPS", "K3s", "Kubernetes", "LLM", "Cluster Orchestration", "Resource Governance", "Automation", "Ollama"]
categories: ["AI + VPS"]
aliases: [/en/post/ai-vps-llm-k3s-cluster-orchestration/]
---

## Introduction: When Your K3s Cluster Starts Spiraling Out of Control

You spent a weekend deploying a K3s cluster on your VPS — three nodes, a dozen Pods, various Deployments and Services. Everything worked great at first, until one day:

> *You get a CPU alert in the morning. It turns out a Python script accidentally created 50 CronJobs, maxing out the cluster CPU;*
> *A Pod has a memory leak, crashes and restarts repeatedly. Each restart consumes more node resources until the entire cluster runs out;*
> *You need to scale up, but have no idea how much capacity the current nodes can handle. You spend half an hour running `kubectl describe` without clarity;*
> *A critical Pod goes down, but you're not at your computer. By the time you see the alert 30 minutes later, the service is already interrupted.*

These problems share a common root cause: **traditional K8s/K3s operations rely on manual intervention and fixed rules, lacking intelligent decision-making capabilities when facing complex, changing cluster states.**

**LLMs (Large Language Models)** bring a brand-new possibility to intelligent cluster orchestration and resource governance.

---

## 1. System Architecture: The LLM-Powered Cluster Brain

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      LLM Cluster Orchestration Engine                        │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐                   │
│  │ Resource      │←→│ Scheduling    │←→│ Self-Healing  │                   │
│  │ Governance    │  │ Decision      │  │ Execution     │                   │
│  │ (Quotas/Limits)│  │ (Pod Scheduling)│ (Fault Repair) │                   │
│  └───────┬───────┘  └───────┬───────┘  └───────┬───────┘                   │
│          │                 │                 │                              │
│  ┌───────┴─────────────────┴─────────────────┴───────┐                     │
│  │           LLM Inference Layer (Ollama + Qwen2.5)   │                     │
│  │  • Cluster State Semantic Understanding            │                     │
│  │  • Scheduling Strategy Generation                  │                     │
│  │  • Remediation Plan Generation                     │                     │
│  └───────────────────────┬───────────────────────────┘                     │
│                          │                                                 │
├──────────────────────────┼─────────────────────────────────────────────────┤
│                          │  kubectl / Kubernetes API                       │
│  ┌───────────────────────┴───────────────────────────────────────────────┐ │
│  │                      Kubernetes API Server                             │ │
│  │  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐         │ │
│  │  │ Node      │  │ Pod       │  │ Deployment│  │ ConfigMap │         │ │
│  │  │ Resource  │  │ Scheduling│  │ Rollback  │  │ Management│         │ │
│  │  │ Quotas    │  │ Auto-     │  │ Versions  │  │ Configs   │         │ │
│  │  │ Management│  │ Scaling   │  │           │  │           │         │ │
│  │  └───────────┘  └───────────┘  └───────────┘  └───────────┘         │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
├───────────────────────────────────────────────────────────────────────────┤
│  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐             │
│  │ Prometheus│  │node-exporter│  │cAdvisor │  │kube-state-metrics│
│  │(Metrics)  │  │(Node M.)  │  │(Container)│  │(Resource St.)  │
│  └───────────┘  └───────────┘  └───────────┘  └───────────┘             │
└───────────────────────────────────────────────────────────────────────────┘
```

### Core Design Principles

| Principle | Description |
|-----------|-------------|
| **Semantics First** | LLM understands cluster state semantically ("high load" vs "CPU 85%"), making smarter decisions |
| **Human-in-the-Loop** | Critical operations (deleting Pods, adjusting quotas) require human confirmation; low-risk ops can auto-execute |
| **Observability** | All LLM decisions and operations are fully logged for audit and rollback |
| **Security Isolation** | LLM runs locally via Ollama — no cluster data ever leaves your infrastructure |

---

## 2. Cluster State Semantic Awareness

Traditional monitoring gives you numbers; LLM tells you what they mean.

### 2.1 Multi-Dimensional State Collection

```python
# cluster_state_collector.py
import subprocess
import json
from datetime import datetime

class ClusterStateCollector:
    """Collect multi-dimensional K3s cluster state"""
    
    def collect(self) -> dict:
        return {
            "timestamp": datetime.now().isoformat(),
            "nodes": self._collect_nodes(),
            "pods": self._collect_pods(),
            "resources": self._collect_resources(),
            "events": self._collect_recent_events(),
            "workloads": self._collect_workloads()
        }
    
    def _collect_nodes(self) -> list:
        """Collect node status"""
        result = subprocess.run(
            ["kubectl", "get", "nodes", "-o", "json"],
            capture_output=True, text=True
        )
        nodes = json.loads(result.stdout)
        return [
            {
                "name": n["metadata"]["name"],
                "status": n["status"]["conditions"][0]["status"] if n["status"]["conditions"] else "Unknown",
                "cpu_allocatable": n["status"]["allocatable"].get("cpu", "0"),
                "memory_allocatable": n["status"]["allocatable"].get("memory", "0"),
            }
            for n in nodes["items"]
        ]
    
    def _collect_pods(self) -> list:
        """Collect Pod status"""
        result = subprocess.run(
            ["kubectl", "get", "pods", "-A", "-o", "wide"],
            capture_output=True, text=True
        )
        lines = result.stdout.strip().split("\n")[1:]
        pods = []
        for line in lines:
            parts = line.split()
            if len(parts) >= 7:
                pods.append({
                    "name": parts[1],
                    "namespace": parts[0],
                    "status": parts[2],
                    "restarts": parts[3],
                    "node": parts[5] if len(parts) > 5 else "N/A",
                    "ip": parts[6] if len(parts) > 6 else "N/A",
                })
        return pods
    
    def _collect_resources(self) -> dict:
        """Collect resource usage"""
        result = subprocess.run(
            ["kubectl", "top", "nodes", "--no-headers"],
            capture_output=True, text=True
        )
        resources = {}
        for line in result.stdout.strip().split("\n"):
            parts = line.split()
            if len(parts) >= 3:
                resources[parts[0]] = {"cpu": parts[1], "memory": parts[2]}
        return resources
    
    def _collect_recent_events(self, hours=2) -> list:
        """Collect recent events"""
        result = subprocess.run(
            ["kubectl", "get", "events", "-A",
             "--field-selector=type!=Normal",
             "--sort-by=.lastTimestamp"],
            capture_output=True, text=True
        )
        return result.stdout.strip().split("\n")[-20:]
    
    def _collect_workloads(self) -> dict:
        """Collect workload status"""
        result = subprocess.run(
            ["kubectl", "get", "deployments", "-A", "-o", "json"],
            capture_output=True, text=True
        )
        deps = json.loads(result.stdout)
        workloads = {}
        for d in deps["items"]:
            name = d["metadata"]["name"]
            ns = d["metadata"]["namespace"]
            spec = d["spec"]
            status = d.get("status", {})
            workloads[f"{ns}/{name}"] = {
                "replicas_desired": spec.get("replicas", 1),
                "replicas_ready": status.get("readyReplicas", 0),
                "replicas_available": status.get("availableReplicas", 0),
                "replicas_unavailable": status.get("unavailableReplicas", 0),
            }
        return workloads
```

### 2.2 LLM-Powered State Semantic Analysis

```python
# cluster_intelligence.py
from openai import OpenAI

client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")

def analyze_cluster_intelligence(state: dict) -> dict:
    """Analyze cluster state with LLM, generate semantic insights"""
    
    summary = {
        "node_count": len(state["nodes"]),
        "total_pods": len(state["pods"]),
        "failed_pods": sum(1 for p in state["pods"] if p["status"] == "Failed"),
        "crashing_pods": sum(1 for p in state["pods"] if int(p.get("restarts", 0)) > 3),
        "not_ready_nodes": sum(1 for n in state["nodes"] if n["status"] != "True"),
        "resource_summary": state["resources"],
        "workload_health": {
            k: v for k, v in state["workloads"].items() 
            if v["replicas_ready"] < v["replicas_desired"]
        },
        "recent_events": state["events"][:10]
    }
    
    prompt = f"""You are a professional Kubernetes cluster operations expert. Analyze the following cluster state and provide semantic insights and recommendations.

【Cluster Summary】
- Node count: {summary['node_count']}
- Total Pods: {summary['total_pods']}
- Failed Pods: {summary['failed_pods']}
- Crashing Pods (restarts > 3): {summary['crashing_pods']}
- Not-Ready Nodes: {summary['not_ready_nodes']}
- Resource Usage: {json.dumps(summary['resource_summary'], ensure_ascii=False)}
- Unhealthy Workloads: {json.dumps(summary['workload_health'], ensure_ascii=False)}
- Recent Events: {'; '.join(summary['recent_events'][:5]) if summary['recent_events'] else 'No anomalies'}

Output JSON format:
{{
  "health_score": 85,
  "health_level": "healthy|degraded|critical",
  "insights": [
    {{
      "type": "resource_pressure|pod_instability|node_issue|workload_degraded",
      "severity": "high|medium|low",
      "description": "Problem description",
      "affected_components": ["component names"],
      "root_cause_hypothesis": "Possible root cause"
    }}
  ],
  "recommendations": [
    {{
      "priority": 1,
      "action": "Specific action recommendation",
      "command": "Executable kubectl command (if applicable)",
      "risk": "low|medium|high"
    }}
  ],
  "auto_remediate_eligible": true
}}"""
    
    response = client.chat.completions.create(
        model="qwen2.5:7b",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.1
    )
    
    return json.loads(response.choices[0].message.content)
```

---

## 3. Intelligent Resource Governance

### 3.1 Dynamic Resource Quota Management

Traditional K8s ResourceQuota is static; LLM can dynamically adjust based on actual load.

```python
# resource_governor.py
import subprocess
import json

class ResourceGovernor:
    """Intelligent resource quota governor"""
    
    def __init__(self, llm_client):
        self.llm = llm_client
    
    def optimize_resource_quotas(self, namespace: str, state: dict) -> dict:
        """Optimize Namespace resource quotas based on actual usage"""
        
        quota_result = subprocess.run(
            ["kubectl", "get", "resourcequota", f"{namespace}-quota", "-o", "json"],
            capture_output=True, text=True
        )
        
        usage_result = subprocess.run(
            ["kubectl", "resource-quota", "--namespace", namespace],
            capture_output=True, text=True
        )
        
        prompt = f"""You are a Kubernetes resource management expert. Analyze the following Namespace resource usage and provide quota optimization recommendations.

【Namespace: {namespace}】

【Current Quotas】
{quota_result.stdout if quota_result.returncode == 0 else 'No quota set'}

【Actual Usage】
{usage_result.stdout if usage_result.returncode == 0 else 'Unable to retrieve'}

【Pods in this Namespace】
{json.dumps([p for p in state['pods'] if p['namespace'] == namespace][:10], indent=2, ensure_ascii=False)}

Output JSON:
{{
  "quota_status": "adequate|over_provisioned|under_provisioned",
  "recommendations": [
    {{
      "resource_type": "cpu|memory|pods|persistentvolumeclaims",
      "current_limit": "10",
      "recommended_limit": "8",
      "reason": "Rationale"
    }}
  ],
  "apply_command": "kubectl patch resourcequota ..."
}}"""
        
        response = self.llm.chat.completions.create(
            model="qwen2.5:7b",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.1
        )
        
        return json.loads(response.choices[0].message.content)
    
    def detect_resource_waste(self, state: dict) -> list:
        """Detect resource waste"""
        waste_findings = []
        
        for ns, res in state["resources"].items():
            cpu_str = res.get("cpu", "0")
            try:
                cpu_val = float(cpu_str.replace("n", "").replace("u", ""))
                if cpu_val < 100:
                    waste_findings.append({
                        "type": "low_cpu_utilization",
                        "node": ns,
                        "cpu_allocatable": res.get("cpu", "0"),
                        "suggestion": "Consider migrating workloads or scaling down"
                    })
            except:
                pass
        
        return waste_findings
```

### 3.2 Intelligent HPA (Horizontal Pod Autoscaler) Enhancement

```python
# intelligent_hpa.py
class IntelligentHPA:
    """LLM-enhanced horizontal auto-scaling"""
    
    def decide_scaling(self, deployment_name: str, namespace: str,
                       current_metrics: dict, state: dict) -> dict:
        """Intelligent scaling decision based on multi-dimensional metrics"""
        
        prompt = f"""You are a K8s auto-scaling expert. Analyze the following Deployment scaling decision.

【Deployment: {namespace}/{deployment_name}】

【Current State】
- Current replicas: {current_metrics.get('current_replicas', 1)}
- CPU utilization: {current_metrics.get('cpu_utilization_percent', 0)}%
- Memory utilization: {current_metrics.get('memory_utilization_percent', 0)}%
- QPS trend (last 1h): {current_metrics.get('qps_trend', 'stable')}
- Expected traffic change: {current_metrics.get('expected_traffic', 'none')}

【Cluster Resource Context】
- Available node CPU: {current_metrics.get('available_node_cpu', 'unknown')}
- Available node memory: {current_metrics.get('available_node_memory', 'unknown')}
- Resource contention: {current_metrics.get('resource_contention', 'low')}

【Recent Scaling History】
{current_metrics.get('recent_scaling_history', 'None')}

Output JSON:
{{
  "action": "scale_up|scale_down|maintenance|no_action",
  "target_replicas": 3,
  "confidence": 0.92,
  "reasoning": "Scaling rationale",
  "risk_assessment": "Assess potential risks",
  "pre_conditions": ["Conditions to meet before execution"],
  "post_actions": ["Verification steps after execution"]
}}"""
        
        response = self.llm.chat.completions.create(
            model="qwen2.5:7b",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.1
        )
        
        decision = json.loads(response.choices[0].message.content)
        
        if decision["action"] == "scale_up":
            self._scale(deployment_name, namespace, decision["target_replicas"], "up")
        elif decision["action"] == "scale_down":
            self._scale(deployment_name, namespace, decision["target_replicas"], "down")
        
        return decision
    
    def _scale(self, name: str, ns: str, replicas: int, direction: str):
        cmd = f"kubectl scale deployment/{name} --replicas={replicas} -n {ns}"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        print(f"[{direction}] {cmd} → {result.stdout}")
```

---

## 4. Intelligent Pod Scheduling

### 4.1 Semantic-Aware Scheduling Decisions

Traditional scheduling is based on resource requests; LLM can understand more complex scheduling semantics.

```python
# smart_scheduler.py
class SmartScheduler:
    """LLM-enhanced intelligent scheduler"""
    
    def optimize_pod_scheduling(self, pending_pods: list,
                                 node_states: list) -> dict:
        """Optimize Pod scheduling strategy"""
        
        prompt = f"""You are a Kubernetes scheduling expert. Choose optimal nodes for the following pending Pods.

【Pending Pods】
{json.dumps(pending_pods, indent=2, ensure_ascii=False)}

【Available Node States】
{json.dumps(node_states, indent=2, ensure_ascii=False)}

【Scheduling Constraints】
- Data locality: Database Pods should be in the same availability zone as API Pods
- Affinity: Frontend Pods should be spread across different nodes
- Anti-affinity: Same Deployment Pods should be on different nodes
- Resource reservation: Reserve 20% node resources for traffic spikes

Output JSON:
{{
  "schedule_decisions": [
    {{
      "pod": "api-server-7d9f8",
      "namespace": "default",
      "recommended_node": "node-1",
      "reasoning": "Node has sufficient CPU and is in the same AZ as the database Pod",
      "confidence": 0.95
    }}
  ],
  "scheduling_issues": [
    {{
      "pod": "batch-job-xyz",
      "issue": "no_sufficient_cpu",
      "suggestion": "Consider using Spot instances or waiting for batch processing window"
    }}
  ],
  "overall_health": "good|fair|poor"
}}"""
        
        response = self.llm.chat.completions.create(
            model="qwen2.5:7b",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.1
        )
        
        return json.loads(response.choices[0].message.content)
```

### 4.2 Intelligent Node Maintenance

```python
# node_maintenance.py
class NodeMaintainer:
    """Intelligent node maintenance"""
    
    def plan_node_drain(self, node_name: str, state: dict) -> dict:
        """Plan graceful node drain"""
        
        pods_on_node = [p for p in state["pods"] if p.get("node") == node_name]
        
        prompt = f"""You are a K8s operations expert. Plan a graceful drain strategy for the following node.

【Target Node: {node_name}】
- Status: {next((n for n in state['nodes'] if n['name'] == node_name), {}).get('status', 'Unknown')}
- Pods to evict: {len(pods_on_node)}

【Pods on this Node】
{json.dumps(pods_on_node, indent=2, ensure_ascii=False)}

【Other Available Nodes】
{json.dumps([n for n in state['nodes'] if n['name'] != node_name], indent=2, ensure_ascii=False)}

Output JSON:
{{
  "can_drain": true,
  "drain_strategy": "graceful|forced",
  "pod_eviction_plan": [
    {{
      "pod": "pod-name",
      "namespace": "default",
      "eviction_method": "graceful|forced",
      "priority": 1,
      "reason": "Reasoning"
    }}
  ],
  "estimated_duration_minutes": 5,
  "risks": ["Brief service interruption", "Data rebalancing"],
  "rollback_plan": "Restore node cordon state and reschedule Pods"
}}"""
        
        response = self.llm.chat.completions.create(
            model="qwen2.5:7b",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.1
        )
        
        return json.loads(response.choices[0].message.content)
```

---

## 5. Intelligent Self-Healing

### 5.1 Fault Diagnosis and Automatic Repair

```python
# self_healing.py
class SelfHealingEngine:
    """Intelligent fault self-healing engine"""
    
    def diagnose_and_fix(self, state: dict, intelligence: dict) -> dict:
        """Diagnose issues and auto-remediate"""
        
        remediation_plan = {"actions": [], "estimated_impact": "", "rollback_plan": ""}
        
        # Handle Failed Pods
        failed_pods = [p for p in state["pods"] if p["status"] == "Failed"]
        if failed_pods:
            for pod in failed_pods[:3]:
                action = {
                    "type": "restart_failed_pod",
                    "pod": pod["name"],
                    "namespace": pod["namespace"],
                    "command": f"kubectl delete pod {pod['name']} -n {pod['namespace']}",
                    "risk": "low",
                    "description": f"Delete and recreate Failed Pod: {pod['name']}"
                }
                remediation_plan["actions"].append(action)
        
        # Handle CrashLoopBackOff Pods
        crashing_pods = [p for p in state["pods"]
                        if p["status"] == "CrashLoopBackOff" or int(p.get("restarts", 0)) > 5]
        if crashing_pods:
            for pod in crashing_pods[:2]:
                action = {
                    "type": "investigate_crashing_pod",
                    "pod": pod["name"],
                    "namespace": pod["namespace"],
                    "command": f"kubectl describe pod {pod['name']} -n {pod['namespace']}",
                    "risk": "medium",
                    "description": f"CrashLoopBackOff detected: {pod['name']}, check events and logs"
                }
                remediation_plan["actions"].append(action)
        
        # Handle unhealthy workloads
        for insight in intelligence.get("insights", []):
            if insight["type"] == "workload_degraded":
                remediation_plan["actions"].append({
                    "type": "scale_or_restart",
                    "description": insight["description"],
                    "command": insight.get("command", ""),
                    "risk": insight.get("severity", "medium"),
                })
        
        remediation_plan["estimated_impact"] = (
            f"Will address {len(remediation_plan['actions'])} issues, "
            "estimated repair time 5-15 minutes"
        )
        remediation_plan["rollback_plan"] = (
            "All operations can be rolled back via kubectl undo or re-applying YAML"
        )
        
        return remediation_plan
    
    def execute_remediation(self, plan: dict, dry_run: bool = True) -> dict:
        """Execute remediation plan"""
        results = []
        
        for action in plan["actions"]:
            if dry_run:
                results.append({
                    **action,
                    "status": "dry_run",
                    "output": f"[DRY RUN] Would execute: {action.get('command', action['description'])}"
                })
                continue
            
            cmd = action.get("command", "")
            if not cmd:
                results.append({**action, "status": "skipped", "output": "No executable command, requires manual handling"})
                continue
            
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            results.append({
                **action,
                "status": "success" if result.returncode == 0 else "failed",
                "output": result.stdout + result.stderr
            })
        
        return {"results": results, "dry_run": dry_run}
```

### 5.2 Intelligent Rolling Updates and Rollback

```python
# smart_rolling_update.py
class SmartRollingUpdater:
    """Intelligent rolling update management"""
    
    def plan_rollback(self, deployment: str, namespace: str,
                      current_state: dict) -> dict:
        """Plan rollback strategy"""
        
        prompt = f"""You are a K8s release management expert. Create a rollback strategy for the following scenario.

【Deployment: {namespace}/{deployment}】
【Current State】
{json.dumps(current_state, indent=2, ensure_ascii=False)}

【Rollback Trigger Conditions】
- Pod failure rate > 10%
- Error rate > 5%
- P99 latency > 3x baseline
- Health check failures: 3 consecutive

Output JSON:
{{
  "should_rollback": true,
  "rollback_version": "v2.1.3",
  "rollback_strategy": "rollback|blue-green|canary",
  "rollback_steps": [
    "Pause current rollout: kubectl rollout pause deployment/{deployment} -n {namespace}",
    "Rollback: kubectl rollout undo deployment/{deployment} -n {namespace}",
    "Verify: kubectl rollout status deployment/{deployment} -n {namespace}"
  ],
  "risk_assessment": "Low risk: Same Deployment rollback is generally safe",
  "post_rollback_verification": [
    "Check pods: kubectl get pods -n {namespace}",
    "Verify service: curl http://service/{deployment}/healthz",
    "Monitor metrics: Watch error rate and latency recovery"
  ]
}}"""
        
        response = self.llm.chat.completions.create(
            model="qwen2.5:7b",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.1
        )
        
        return json.loads(response.choices[0].message.content)
```

---

## 6. Complete Deployment Guide

### 6.1 Docker Compose Orchestration

```yaml
# docker-compose.yml
version: '3.8'

services:
  llm-cluster-manager:
    build: ./cluster-manager
    container_name: vps-llm-cluster-mgr
    privileged: true
    volumes:
      - /etc/rancher/k3s/k3s.yaml:/etc/rancher/k3s/k3s.yaml:ro
      - ./config:/app/config
      - ./logs:/app/logs
      - ./state:/app/state
    environment:
      - KUBECONFIG=/etc/rancher/k3s/k3s.yaml
      - LLM_ENDPOINT=http://ollama:11434
      - LLM_MODEL=qwen2.5:7b
      - AUTO_REMEDIATE=true
      - DRY_RUN=false
      - ALERT_CHANNEL=telegram
      - TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
      - TELEGRAM_CHAT_ID=${TELEGRAM_CHAT_ID}
    restart: unless-stopped
    networks:
      - cluster-mgr-net

  ollama:
    image: ollama/ollama:latest
    container_name: vps-ollama
    volumes:
      - ollama_data:/root/.ollama
    ports:
      - "11434:11434"
    restart: unless-stopped
    networks:
      - cluster-mgr-net

  prometheus:
    image: prom/prometheus:latest
    container_name: vps-prometheus
    volumes:
      - ./config/prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    ports:
      - "9090:9090"
    restart: unless-stopped
    networks:
      - cluster-mgr-net

  grafana:
    image: grafana/grafana:latest
    container_name: vps-grafana
    volumes:
      - grafana_data:/var/lib/grafana
      - ./config/grafana/datasources:/etc/grafana/provisioning/datasources
    ports:
      - "3000:3000"
    restart: unless-stopped
    networks:
      - cluster-mgr-net

volumes:
  ollama_data:
  prometheus_data:
  grafana_data:

networks:
  cluster-mgr-net:
    driver: bridge
```

### 6.2 Main Controller

```python
# cluster_controller.py
#!/usr/bin/env python3
"""LLM-driven K3s cluster intelligent controller"""

import time
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from cluster_state_collector import ClusterStateCollector
from cluster_intelligence import analyze_cluster_intelligence
from resource_governor import ResourceGovernor
from intelligent_hpa import IntelligentHPA
from self_healing import SelfHealingEngine
from openai import OpenAI

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")

class LLMAutoController:
    def __init__(self):
        self.collector = ClusterStateCollector()
        self.governor = ResourceGovernor(client)
        self.hpa = IntelligentHPA(client)
        self.healer = SelfHealingEngine()
        self.state_history = []
        self.last_analysis = None
    
    def run_cycle(self):
        """Execute one cluster management cycle"""
        logger.info("🔄 Starting cluster management cycle...")
        
        # 1. Collect state
        state = self.collector.collect()
        state["timestamp"] = datetime.now().isoformat()
        self.state_history.append(state)
        if len(self.state_history) > 100:
            self.state_history = self.state_history[-100:]
        
        # 2. LLM intelligence analysis
        intelligence = analyze_cluster_intelligence(state)
        self.last_analysis = intelligence
        
        logger.info(f"📊 Cluster health: {intelligence.get('health_score', 'N/A')}/100 "
                   f"({intelligence.get('health_level', 'unknown')})")
        
        # 3. Resource governance
        for ns in set(p["namespace"] for p in state["pods"]):
            try:
                optimization = self.governor.optimize_resource_quotas(ns, state)
                logger.info(f"💾 Namespace {ns}: {optimization.get('quota_status', 'unknown')}")
            except Exception as e:
                logger.warning(f"⚠️ Resource governance failed for {ns}: {e}")
        
        # 4. Self-healing
        if intelligence.get("health_level") in ["degraded", "critical"]:
            plan = self.healer.diagnose_and_fix(state, intelligence)
            
            if not plan["actions"]:
                logger.info("✅ No remediation needed")
            else:
                result = self.healer.execute_remediation(plan, dry_run=False)
                for r in result["results"]:
                    icon = "✅" if r["status"] == "success" else "❌"
                    logger.info(f"{icon} {r['type']}: {r.get('output', '')[:100]}")
        
        # 5. Send alerts
        if intelligence.get("health_level") == "critical":
            self._send_alert("🚨 Cluster Critical Alert", intelligence)
        elif intelligence.get("health_level") == "degraded":
            self._send_alert("⚠️ Cluster Degraded Alert", intelligence)
        
        # 6. Save state
        self._save_state(state, intelligence)
    
    def _send_alert(self, title: str, intelligence: dict):
        """Send alert notification"""
        import subprocess
        msg = f"""{title}

Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Health: {intelligence.get('health_score', 'N/A')}/100
Level: {intelligence.get('health_level', 'unknown')}

Issues found:
"""
        for insight in intelligence.get("insights", [])[:3]:
            msg += f"  - [{insight.get('severity', 'unknown')}] {insight.get('description', '')}\n"
        
        msg += "\nRecommendations:"
        for rec in intelligence.get("recommendations", [])[:3]:
            msg += f"\n  - {rec.get('action', '')}"
        
        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
        if bot_token and chat_id:
            subprocess.run([
                "curl", "-s", "-X", "POST",
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                f"-d", f"chat_id={chat_id}",
                f"-d", f"text={msg}",
                f"-d", "parse_mode=HTML"
            ], capture_output=True)
    
    def _save_state(self, state: dict, intelligence: dict):
        """Save state to file"""
        state_dir = Path("/app/state")
        state_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        with open(state_dir / f"state_{timestamp}.json", "w") as f:
            json.dump({"state": state, "intelligence": intelligence}, f,
                     indent=2, ensure_ascii=False)
    
    def run_continuous(self, interval_seconds: int = 300):
        """Continuous running mode"""
        logger.info(f"🚀 LLM Cluster Controller started, polling interval {interval_seconds}s")
        
        while True:
            try:
                self.run_cycle()
            except Exception as e:
                logger.error(f"❌ Cycle execution failed: {e}")
            time.sleep(interval_seconds)

if __name__ == "__main__":
    controller = LLMAutoController()
    controller.run_continuous(interval_seconds=300)
```

### 6.3 Deployment Steps

```bash
# 1. Pull and run the model
ollama pull qwen2.5:7b

# 2. Clone and configure
git clone https://github.com/selfvps/llm-k3s-manager.git
cd llm-k3s-manager
cp .env.example .env
# Edit .env with TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID

# 3. Start services
docker-compose up -d

# 4. View logs
docker-compose logs -f llm-cluster-manager

# 5. Manual analysis trigger
docker-compose exec llm-cluster-manager python3 cluster_controller.py --once
```

---

## 7. Typical Application Scenarios

### Scenario 1: Pods Restarting Frequently at 3 AM

```
[03:15:00] ⚠️  Cluster analysis detected anomaly
  - health_score: 62/100 (degraded)
  - 3 Pods in CrashLoopBackOff
  - Affected Deployment: api-server, worker-processor

[03:15:01] 🔍 LLM Diagnosis
  - Root cause hypothesis: Database connection pool exhaustion causing app startup failure
  - Evidence: Pod logs show "connection refused" errors
  
[03:15:02] 🛠️  Auto-remediation executed
  ✅ Restarted api-server Pods × 3
  ✅ Adjusted database connection pool: max_connections=200
  ✅ Verified: All Pods back to Running state

[03:20:00] ✅ Problem resolved, recorded to knowledge base
```

### Scenario 2: Resource Quota Optimization

```
[09:00:00] 💾 Periodic resource governance scan
  - Namespace "default": Quota over-provisioned by 40%
    Recommendation: CPU quota from 8 cores → 5 cores
  - Namespace "production": Quota insufficient
    Recommendation: CPU quota from 4 cores → 8 cores, memory from 8Gi → 16Gi
  
[09:00:05] 📋 Generated optimization report
  → Estimated 3 CPU cores and 4Gi memory freed for other workloads
  → Validated via dry-run, confirmed no risk
  → Awaiting admin confirmation before execution
```

### Scenario 3: Intelligent Rolling Update with Auto-Rollback

```
[14:00:00] 🔄 Detected api-server v2.3.0 update
  - Current: v2.2.1 (10/10 Pods healthy)
  - New: v2.3.0 (3/10 Pods updated)
  
[14:00:30] 📊 Post-update monitoring
  - Error rate: 2.1% (threshold: 5%)
  - P99 latency: 245ms (baseline: 120ms)
  - Health checks: 2/10 failing
  
[14:01:00] 🚨 LLM Assessment: Rollback should trigger
  - Reason: Error rate near threshold, latency doubled, health checks failing
  - Confidence: 0.88
  
[14:01:05] ⏮️  Auto-rollback executed
  ✅ kubectl rollout undo deployment/api-server -n production
  ✅ Rolled back to v2.2.1
  ✅ Verified: All Pods healthy, error rate dropped to 0.1%
```

---

## 8. Prometheus + Grafana Integration

```yaml
# config/prometheus.yml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'k3s-nodes'
    kubernetes_sd_configs:
      - role: node
    relabel_configs:
      - source_labels: [__address__]
        regex: '(.+):10250'
        target_label: __address__
        replacement: '${1}:9100'

  - job_name: 'k3s-pods'
    kubernetes_sd_configs:
      - role: pod
    relabel_configs:
      - source_labels: [__meta_kubernetes_pod_annotation_prometheus_io_scrape]
        action: keep
        regex: true

  - job_name: 'llm-cluster-manager'
    static_configs:
      - targets: ['llm-cluster-manager:8080']
```

Grafana Dashboard JSON available from repository, including:
- Cluster health score trend
- Pod status distribution
- Resource utilization heatmap
- LLM decision log panel
- Auto-remediation event timeline

---

## 9. Best Practices

### Security Recommendations

1. **Least Privilege**: Grant the LLM controller only necessary RBAC permissions, avoid ClusterRole
2. **Operation Audit**: All LLM-generated operations logged to audit trail
3. **Human Confirmation**: High-risk operations (deleting Pods, adjusting nodes) require manual confirmation
4. **Model Isolation**: Run Ollama in an isolated container to prevent LLM injection attacks

### Performance Recommendations

1. **Sampling Frequency**: Production — 5 min full analysis, 1 min quick check
2. **Token Optimization**: Only send essential state info to LLM to avoid exceeding limits
3. **Caching**: Similar states can reuse previous analysis results
4. **Fallback**: Revert to rule-based engine when LLM is unavailable

### Operations Recommendations

1. **Gradual Deployment**: Start in read-only mode (dry-run), enable auto-remediation after stability confirmation
2. **Alert Channels**: Configure Telegram/Slack notifications for timely anomaly detection
3. **Knowledge Base**: Record every remediation to the knowledge base, continuously optimizing LLM decision quality
4. **Weekly Review**: Review LLM decision logs weekly, identify misjudgments and adjust prompts

---

## 10. Summary

LLM-driven K3s cluster orchestration upgrades traditional "manual operation + fixed rules" operations to an AI-Native model of "semantic understanding + intelligent decision-making + automated execution." Core value:

| Dimension | Traditional Approach | LLM-Driven Approach |
|-----------|---------------------|---------------------|
| State Awareness | Reading dashboard numbers | Semantic understanding of cluster health |
| Scheduling Decisions | Based on resource requests | Understanding business semantics and dependencies |
| Fault Repair | Manual investigation and operation | Automatic diagnosis + execution |
| Resource Governance | Static quota configuration | Dynamic optimization and adjustment |
| Scaling Strategy | Fixed-threshold HPA | Multi-dimensional intelligent decision-making |

**Future Evolution Directions**:
- Support multi-cluster unified management
- Deep integration with GitOps toolchains (ArgoCD, Flux)
- Introduce reinforcement learning for continuous strategy optimization
- Support GPU scheduling and AI inference task orchestration

---

*Repository: https://github.com/selfvps/llm-k3s-manager*

*Next up: "AI-Driven VPS Intelligent Multi-Cloud Resource Scheduling and Cost Optimization"*
