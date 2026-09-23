---
title: "AI + VPS：用大模型驱动 K3s 集群智能编排与资源治理"
description: "告别手动 kubectl 操作，让本地 LLM 自动管理 K3s 集群的 Pod 调度、资源配额、弹性伸缩和故障自愈，实现真正的 AI-Native 集群运维。"
date: 2026-09-23T21:00:00+08:00
lastmod: 2026-09-23T21:00:00+08:00
slug: "ai-vps-llm-k3s-cluster-orchestration"
image: /images/posts/ai-vps-llm-k3s-cluster-orchestration/featured.png
tags: ["AI", "VPS", "K3s", "Kubernetes", "LLM", "集群编排", "资源治理", "自动化运维", "Ollama"]
categories: ["AI + VPS"]
aliases: [/zh/post/ai-vps-llm-k3s-cluster-orchestration/]
---

## 引言：当 K3s 集群开始失控

你花了一个周末，在 VPS 上部署了 K3s 集群——三个节点、十几个 Pod、各种 Deployment 和 Service。一开始一切顺利，直到某天：

> *早上发现 CPU 告警，原来是一个 Python 脚本意外创建了 50 个 CronJob，把集群 CPU 打满；*
> *某个 Pod 内存泄漏，OOM 后反复重启，每次重启都占用新的节点资源，最终整个集群资源耗尽；*
> *你想扩容，但不知道当前节点还能承载多少负载，手动 `kubectl describe` 查了半天也没搞清楚；*
> *一个关键 Pod 挂掉了，但你不在电脑前，等半小时后才看到告警，业务已经中断了。*

这些问题共同指向一个核心痛点：**传统 K8s/K3s 运维依赖人工操作和固定规则，面对复杂多变的集群状态，缺乏智能决策能力。**

而 **LLM（大语言模型）** 的引入，为集群智能编排和资源治理带来了全新的可能。

---

## 一、系统架构：LLM 驱动的集群大脑

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           LLM 集群编排引擎                                    │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐                   │
│  │  资源治理引擎  │←→│  调度决策引擎  │←→│  自愈执行引擎  │                   │
│  │ (配额/限流)   │  │ (Pod调度)    │  │ (故障修复)    │                   │
│  └───────┬───────┘  └───────┬───────┘  └───────┬───────┘                   │
│          │                 │                 │                              │
│  ┌───────┴─────────────────┴─────────────────┴───────┐                     │
│  │              LLM 推理层 (Ollama + Qwen2.5)         │                     │
│  │  • 集群状态语义理解    • 调度策略生成    • 修复方案生成 │                     │
│  └───────────────────────┬───────────────────────────┘                     │
│                          │                                                 │
├──────────────────────────┼─────────────────────────────────────────────────┤
│                          │  kubectl / Kubernetes API                       │
│  ┌───────────────────────┴───────────────────────────────────────────────┐ │
│  │                         Kubernetes API Server                         │ │
│  │  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐         │ │
│  │  │  Node 资源  │  │  Pod 调度  │  │  Deployment │  │  ConfigMap │         │ │
│  │  │  配额管理   │  │  弹性伸缩  │  │  版本回滚   │  │  配置管理  │         │ │
│  │  └───────────┘  └───────────┘  └───────────┘  └───────────┘         │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
├───────────────────────────────────────────────────────────────────────────┤
│  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐             │
│  │ Prometheus │  │  node-exporter│  │  cAdvisor │  │  kube-state-metrics│
│  │  (指标采集) │  │  (节点指标)  │  │ (容器指标) │  │  (资源状态)    │
│  └───────────┘  └───────────┘  └───────────┘  └───────────┘             │
└───────────────────────────────────────────────────────────────────────────┘
```

### 核心设计原则

| 原则 | 说明 |
|------|------|
| **语义优先** | LLM 理解集群状态的语义（"负载过高"而非"CPU 85%"），做出更合理的决策 |
| **人机协同** | 关键操作（如删除 Pod、调整资源配额）需人工确认，低风险操作可自动执行 |
| **可观测性** | 所有 LLM 决策和操作都有完整日志，支持审计和回溯 |
| **安全隔离** | LLM 运行在本地 Ollama，不上传任何集群数据到外部 |

---

## 二、集群状态语义感知

传统监控告诉你数字，LLM 告诉你"这意味着什么"。

### 2.1 多维状态采集

```python
# cluster_state_collector.py
import subprocess
import json
from datetime import datetime

class ClusterStateCollector:
    """采集 K3s 集群多维状态"""
    
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
        """采集节点状态"""
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
        """采集 Pod 状态"""
        result = subprocess.run(
            ["kubectl", "get", "pods", "-A", "-o", "wide"],
            capture_output=True, text=True
        )
        lines = result.stdout.strip().split("\n")[1:]  # skip header
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
        """采集资源使用情况"""
        result = subprocess.run(
            ["kubectl", "top", "nodes", "--no-headers"],
            capture_output=True, text=True
        )
        resources = {}
        for line in result.stdout.strip().split("\n"):
            parts = line.split()
            if len(parts) >= 3:
                resources[parts[0]] = {
                    "cpu": parts[1],
                    "memory": parts[2]
                }
        return resources
    
    def _collect_recent_events(self, hours=2) -> list:
        """采集最近事件"""
        result = subprocess.run(
            ["kubectl", "get", "events", "-A", 
             f"--field-selector=type!=Normal",
             f"--sort-by=.lastTimestamp"],
            capture_output=True, text=True
        )
        return result.stdout.strip().split("\n")[-20:]  # 最近 20 个异常事件
    
    def _collect_workloads(self) -> dict:
        """采集工作负载状态"""
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

### 2.2 LLM 状态语义分析

```python
# cluster_intelligence.py
from openai import OpenAI

client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")

def analyze_cluster_intelligence(state: dict) -> dict:
    """用 LLM 分析集群状态，生成语义化洞察"""
    
    # 构建精简状态摘要（避免超过 token 限制）
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
    
    prompt = f"""你是一个专业的 Kubernetes 集群运维专家。请分析以下集群状态，给出语义化的洞察和建议。

【集群摘要】
- 节点数: {summary['node_count']}
- 总 Pod 数: {summary['total_pods']}
- Failed Pod 数: {summary['failed_pods']}
- 频繁重启 Pod 数: {summary['crashing_pods']}
- 不可用节点数: {summary['not_ready_nodes']}
- 资源使用: {json.dumps(summary['resource_summary'], ensure_ascii=False)}
- 不健康工作负载: {json.dumps(summary['workload_health'], ensure_ascii=False)}
- 最近事件: {'; '.join(summary['recent_events'][:5]) if summary['recent_events'] else '无异常'}

请按以下 JSON 格式输出：
{{
  "health_score": 85,
  "health_level": "healthy|degraded|critical",
  "insights": [
    {{
      "type": "resource_pressure|pod_instability|node_issue|workload_degraded",
      "severity": "high|medium|low",
      "description": "发现的问题描述",
      "affected_components": ["组件名"],
      "root_cause_hypothesis": "可能的根因"
    }}
  ],
  "recommendations": [
    {{
      "priority": 1,
      "action": "具体操作建议",
      "command": "可执行的 kubectl 命令（如适用）",
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

## 三、智能资源治理

### 3.1 动态资源配额管理

传统 K8s 的 ResourceQuota 是静态的，LLM 可以根据实际负载动态调整。

```python
# resource_governor.py
import subprocess
import json

class ResourceGovernor:
    """智能资源配额治理器"""
    
    def __init__(self, llm_client):
        self.llm = llm_client
    
    def optimize_resource_quotas(self, namespace: str, state: dict) -> dict:
        """根据实际使用优化 Namespace 资源配额"""
        
        # 获取当前配额和使用情况
        quota_result = subprocess.run(
            ["kubectl", "get", "resourcequota", f"{namespace}-quota", "-o", "json"],
            capture_output=True, text=True
        )
        
        usage_result = subprocess.run(
            ["kubectl", "resource-quota", "--namespace", namespace],
            capture_output=True, text=True
        )
        
        prompt = f"""你是 Kubernetes 资源管理专家。请分析以下 Namespace 的资源使用情况，给出配额优化建议。

【Namespace: {namespace}】

【当前配额】
{quota_result.stdout if quota_result.returncode == 0 else '未设置配额'}

【实际使用】
{usage_result.stdout if usage_result.returncode == 0 else '无法获取'}

【该 Namespace 的 Pod 列表】
{json.dumps([p for p in state['pods'] if p['namespace'] == namespace][:10], indent=2, ensure_ascii=False)}

请输出 JSON：
{{
  "quota_status": "adequate|over_provisioned|under_provisioned",
  "recommendations": [
    {{
      "resource_type": "cpu|m memory|pods|persistentvolumeclaims",
      "current_limit": "10",
      "recommended_limit": "8",
      "reason": "理由"
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
        """检测资源浪费"""
        waste_findings = []
        
        for pod in state["pods"]:
            if pod["status"] == "Running":
                # 检查是否有长期空闲的 Pod（CPU 接近 0）
                pass  # 实际实现中需要结合 metrics-server 数据
        
        for ns, res in state["resources"].items():
            # 检查节点资源利用率
            cpu_str = res.get("cpu", "0")
            try:
                cpu_val = float(cpu_str.replace("n", "").replace("u", ""))
                if cpu_val < 100:  # 低于 100m
                    waste_findings.append({
                        "type": "low_cpu_utilization",
                        "node": ns,
                        "cpu_allocatable": res.get("cpu", "0"),
                        "suggestion": "考虑迁移工作负载或缩容"
                    })
            except:
                pass
        
        return waste_findings
```

### 3.2 智能水平伸缩（HPA 增强）

```python
# intelligent_hpa.py
class IntelligentHPA:
    """LLM 增强的水平自动伸缩"""
    
    def decide_scaling(self, deployment_name: str, namespace: str, 
                       current_metrics: dict, state: dict) -> dict:
        """基于多维度指标的智能伸缩决策"""
        
        prompt = f"""你是 K8s 弹性伸缩专家。请分析以下 Deployment 的伸缩决策。

【Deployment: {namespace}/{deployment_name}】

【当前状态】
- 当前副本数: {current_metrics.get('current_replicas', 1)}
- CPU 使用率: {current_metrics.get('cpu_utilization_percent', 0)}%
- 内存使用率: {current_metrics.get('memory_utilization_percent', 0)}%
- 最近 1 小时 QPS 趋势: {current_metrics.get('qps_trend', 'stable')}
- 预期流量变化: {current_metrics.get('expected_traffic', 'none')}

【集群资源上下文】
- 可用节点 CPU: {current_metrics.get('available_node_cpu', 'unknown')}
- 可用节点内存: {current_metrics.get('available_node_memory', 'unknown')}
- 其他 Pod 资源竞争情况: {current_metrics.get('resource_contention', 'low')}

【历史伸缩记录】
{current_metrics.get('recent_scaling_history', '无')}

请输出 JSON：
{{
  "action": "scale_up|scale_down|maintenance|no_action",
  "target_replicas": 3,
  "confidence": 0.92,
  "reasoning": "伸缩理由说明",
  "risk_assessment": "评估潜在风险",
  "pre_conditions": ["执行前需满足的条件"],
  "post_actions": ["执行后的验证步骤"]
}}"""
        
        response = self.llm.chat.completions.create(
            model="qwen2.5:7b",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.1
        )
        
        decision = json.loads(response.choices[0].message.content)
        
        # 执行决策
        if decision["action"] == "scale_up":
            self._scale(deployment_name, namespace, decision["target_replicas"], "up")
        elif decision["action"] == "scale_down":
            self._scale(deployment_name, namespace, decision["target_replicas"], "down")
        
        return decision
    
    def _scale(self, name: str, ns: str, replicas: int, direction: str):
        """执行伸缩操作"""
        cmd = f"kubectl scale deployment/{name} --replicas={replicas} -n {ns}"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        print(f"[{direction}] {cmd} → {result.stdout}")
```

---

## 四、智能 Pod 调度

### 4.1 语义化调度决策

传统调度基于资源请求，LLM 可以理解更复杂的调度语义。

```python
# smart_scheduler.py
class SmartScheduler:
    """LLM 增强的智能调度器"""
    
    def optimize_pod_scheduling(self, pending_pods: list, 
                                 node_states: list) -> dict:
        """优化 Pod 调度策略"""
        
        prompt = f"""你是 Kubernetes 调度专家。请为以下待调度 Pod 选择最优节点。

【待调度 Pod】
{json.dumps(pending_pods, indent=2, ensure_ascii=False)}

【可用节点状态】
{json.dumps(node_states, indent=2, ensure_ascii=False)}

【调度约束】
- 数据 locality 要求: 数据库 Pod 应与 API Pod 在同一可用区
- 亲和性规则: 前端 Pod 应尽量分散在不同节点
- 反亲和性: 同一 Deployment 的 Pod 应分散节点
- 资源预留: 预留 20% 节点资源应对突发流量

请输出 JSON：
{{
  "schedule_decisions": [
    {{
      "pod": "api-server-7d9f8",
      "namespace": "default",
      "recommended_node": "node-1",
      "reasoning": "该节点 CPU 余量充足且与数据库 Pod 同可用区",
      "confidence": 0.95
    }}
  ],
  "scheduling_issues": [
    {{
      "pod": "batch-job-xyz",
      "issue": "no_sufficient_cpu",
      "suggestion": "考虑使用 Spot 实例或等待批处理窗口"
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

### 4.2 智能节点维护

```python
# node_maintenance.py
class NodeMaintainer:
    """智能节点维护"""
    
    def plan_node_drain(self, node_name: str, state: dict) -> dict:
        """规划节点 drain 操作"""
        
        # 获取节点上的 Pod
        pods_on_node = [p for p in state["pods"] if p.get("node") == node_name]
        
        prompt = f"""你是 K8s 运维专家。请规划以下节点的优雅排空方案。

【目标节点: {node_name}】
- 状态: {next((n for n in state['nodes'] if n['name'] == node_name), {}).get('status', 'Unknown')}
- 待排空 Pod 数: {len(pods_on_node)}

【节点上的 Pod】
{json.dumps(pods_on_node, indent=2, ensure_ascii=False)}

【其他可用节点】
{json.dumps([n for n in state['nodes'] if n['name'] != node_name], indent=2, ensure_ascii=False)}

请输出 JSON：
{{
  "can_drain": true,
  "drain_strategy": "graceful|forced",
  "pod_eviction_plan": [
    {{
      "pod": "pod-name",
      "namespace": "default",
      "eviction_method": "graceful|forced",
      "priority": 1,
      "reason": "理由"
    }}
  ],
  "estimated_duration_minutes": 5,
  "risks": ["短暂服务中断", "数据重平衡"],
  "rollback_plan": "恢复 node cordon 状态，重新调度 Pod"
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

## 五、智能故障自愈

### 5.1 故障诊断与自动修复

```python
# self_healing.py
class SelfHealingEngine:
    """智能故障自愈引擎"""
    
    def diagnose_and_fix(self, state: dict, intelligence: dict) -> dict:
        """诊断问题并自动修复"""
        
        remediation_plan = {
            "actions": [],
            "estimated_impact": "",
            "rollback_plan": ""
        }
        
        # 处理 Failed Pod
        failed_pods = [p for p in state["pods"] if p["status"] == "Failed"]
        if failed_pods:
            for pod in failed_pods[:3]:  # 处理前 3 个
                action = {
                    "type": "restart_failed_pod",
                    "pod": pod["name"],
                    "namespace": pod["namespace"],
                    "command": f"kubectl delete pod {pod['name']} -n {pod['namespace']}",
                    "risk": "low",
                    "description": f"删除并重建 Failed Pod: {pod['name']}"
                }
                remediation_plan["actions"].append(action)
        
        # 处理 CrashLoopBackOff Pod
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
                    "description": f"CrashLoopBackOff 检测到: {pod['name']}，建议查看事件和日志"
                }
                remediation_plan["actions"].append(action)
        
        # 处理不健康的工作负载
        unhealthy_workloads = intelligence.get("insights", [])
        for insight in unhealthy_workloads:
            if insight["type"] == "workload_degraded":
                action = {
                    "type": "scale_or_restart",
                    "description": insight["description"],
                    "command": insight.get("command", ""),
                    "risk": insight.get("severity", "medium"),
                }
                remediation_plan["actions"].append(action)
        
        # 处理资源压力
        for insight in intelligence.get("insights", []):
            if insight["type"] == "resource_pressure":
                action = {
                    "type": "resource_optimization",
                    "description": insight["description"],
                    "command": insight.get("command", ""),
                    "risk": "low",
                }
                remediation_plan["actions"].append(action)
        
        remediation_plan["estimated_impact"] = (
            f"将处理 {len(remediation_plan['actions'])} 个问题，"
            "预计修复时间 5-15 分钟"
        )
        remediation_plan["rollback_plan"] = (
            "所有操作均可通过 kubectl undo 或重新应用 YAML 回滚"
        )
        
        return remediation_plan
    
    def execute_remediation(self, plan: dict, dry_run: bool = True) -> dict:
        """执行修复计划"""
        results = []
        
        for action in plan["actions"]:
            if dry_run:
                results.append({
                    **action,
                    "status": "dry_run",
                    "output": f"[DRY RUN] 将执行: {action.get('command', action['description'])}"
                })
                continue
            
            cmd = action.get("command", "")
            if not cmd:
                results.append({
                    **action,
                    "status": "skipped",
                    "output": "无可执行命令，需人工处理"
                })
                continue
            
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            results.append({
                **action,
                "status": "success" if result.returncode == 0 else "failed",
                "output": result.stdout + result.stderr
            })
        
        return {"results": results, "dry_run": dry_run}
```

### 5.2 智能滚动更新与回滚

```python
# smart_rolling_update.py
class SmartRollingUpdater:
    """智能滚动更新管理"""
    
    def plan_rollback(self, deployment: str, namespace: str, 
                      current_state: dict) -> dict:
        """规划回滚策略"""
        
        prompt = f"""你是 K8s 发布管理专家。请为以下场景制定回滚策略。

【Deployment: {namespace}/{deployment}】
【当前状态】
{json.dumps(current_state, indent=2, ensure_ascii=False)}

【回滚触发条件】
- Pod 失败率 > 10%
- 错误率 > 5%（从 metrics 获取）
- P99 延迟 > 基准的 3 倍
- 健康检查连续失败 3 次

请输出 JSON：
{{
  "should_rollback": true,
  "rollback_version": "v2.1.3",
  "rollback_strategy": "recroll|blue-green|canary",
  "rollback_steps": [
    "暂停当前滚动更新: kubectl rollout pause deployment/{deployment} -n {namespace}",
    "回滚到上一版本: kubectl rollout undo deployment/{deployment} -n {namespace}",
    "验证回滚结果: kubectl rollout status deployment/{deployment} -n {namespace}"
  ],
  "risk_assessment": "低风险：同一 Deployment 的回滚通常是安全的",
  "post_rollback_verification": [
    "检查 Pod 状态: kubectl get pods -n {namespace}",
    "验证服务可用性: curl http://service/{deployment}/healthz",
    "监控指标恢复: 观察错误率和延迟是否回到正常水平"
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

## 六、完整部署方案

### 6.1 Docker Compose 编排

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

### 6.2 主控制器

```python
# cluster_controller.py
#!/usr/bin/env python3
"""LLM 驱动的 K3s 集群智能控制器"""

import time
import json
import logging
from datetime import datetime
from pathlib import Path
from cluster_state_collector import ClusterStateCollector
from cluster_intelligence import analyze_cluster_intelligence
from resource_governor import ResourceGovernor
from intelligent_hpa import IntelligentHPA
from self_healing import SelfHealingEngine
from openai import OpenClient

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class LLMAutoController:
    def __init__(self):
        self.collector = ClusterStateCollector()
        self.governor = ResourceGovernor(client)
        self.hpa = IntelligentHPA(client)
        self.healer = SelfHealingEngine()
        self.state_history = []
        self.last_analysis = None
    
    def run_cycle(self):
        """执行一轮集群管理周期"""
        logger.info("🔄 开始集群管理周期...")
        
        # 1. 采集状态
        state = self.collector.collect()
        state["timestamp"] = datetime.now().isoformat()
        self.state_history.append(state)
        if len(self.state_history) > 100:
            self.state_history = self.state_history[-100:]
        
        # 2. LLM 智能分析
        intelligence = analyze_cluster_intelligence(state)
        self.last_analysis = intelligence
        
        logger.info(f"📊 集群健康度: {intelligence.get('health_score', 'N/A')}/100 "
                   f"({intelligence.get('health_level', 'unknown')})")
        
        # 3. 资源治理
        for ns in set(p["namespace"] for p in state["pods"]):
            try:
                optimization = self.governor.optimize_resource_quotas(ns, state)
                logger.info(f"💾 Namespace {ns}: {optimization.get('quota_status', 'unknown')}")
            except Exception as e:
                logger.warning(f"⚠️ 资源治理失败 {ns}: {e}")
        
        # 4. 故障自愈
        if intelligence.get("health_level") in ["degraded", "critical"]:
            plan = self.healer.diagnose_and_fix(state, intelligence)
            
            if not plan["actions"]:
                logger.info("✅ 无需修复操作")
            else:
                result = self.healer.execute_remediation(plan, dry_run=False)
                for r in result["results"]:
                    status_icon = "✅" if r["status"] == "success" else "❌"
                    logger.info(f"{status_icon} {r['type']}: {r.get('output', '')[:100]}")
        
        # 5. 发送通知
        if intelligence.get("health_level") == "critical":
            self._send_alert("🚨 集群紧急告警", intelligence)
        elif intelligence.get("health_level") == "degraded":
            self._send_alert("⚠️ 集群降级告警", intelligence)
        
        # 6. 保存状态
        self._save_state(state, intelligence)
    
    def _send_alert(self, title: str, intelligence: dict):
        """发送告警通知"""
        import subprocess
        msg = f"""{title}

时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
健康度: {intelligence.get('health_score', 'N/A')}/100
级别: {intelligence.get('health_level', 'unknown')}

发现问题:
"""
        for insight in intelligence.get("insights", [])[:3]:
            msg += f"  - [{insight.get('severity', 'unknown')}] {insight.get('description', '')}\n"
        
        msg += "\n修复建议:"
        for rec in intelligence.get("recommendations", [])[:3]:
            msg += f"\n  - {rec.get('action', '')}"
        
        # Telegram 通知
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
        """保存状态到文件"""
        state_dir = Path("/app/state")
        state_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        with open(state_dir / f"state_{timestamp}.json", "w") as f:
            json.dump({"state": state, "intelligence": intelligence}, f, 
                     indent=2, ensure_ascii=False)
    
    def run_continuous(self, interval_seconds: int = 300):
        """连续运行模式"""
        logger.info(f"🚀 LLM 集群智能控制器启动，轮询间隔 {interval_seconds}s")
        
        while True:
            try:
                self.run_cycle()
            except Exception as e:
                logger.error(f"❌ 周期执行失败: {e}")
            
            time.sleep(interval_seconds)

if __name__ == "__main__":
    controller = LLMAutoController()
    controller.run_continuous(interval_seconds=300)
```

### 6.3 部署与运行

```bash
# 1. 拉取并运行模型
ollama pull qwen2.5:7b

# 2. 克隆项目并配置
git clone https://github.com/selfvps/llm-k3s-manager.git
cd llm-k3s-manager
cp .env.example .env
# 编辑 .env 填入 TELEGRAM_BOT_TOKEN 和 TELEGRAM_CHAT_ID

# 3. 启动服务
docker-compose up -d

# 4. 查看日志
docker-compose logs -f llm-cluster-manager

# 5. 手动触发分析
docker-compose exec llm-cluster-manager python3 cluster_controller.py --once
```

---

## 七、典型应用场景

### 场景 1：凌晨 Pod 频繁重启

```
[03:15:00] ⚠️  集群分析发现异常
  - health_score: 62/100 (degraded)
  - 3 个 Pod 处于 CrashLoopBackOff
  - 涉及 Deployment: api-server, worker-processor

[03:15:01] 🔍 LLM 诊断结果
  - 根因假设: 数据库连接池耗尽导致应用启动失败
  - 证据: Pod 日志显示 "connection refused" 错误
  
[03:15:02] 🛠️  自动修复执行
  ✅ 重启 api-server Pod × 3
  ✅ 调整 database 连接池配置: max_connections=200
  ✅ 验证: 所有 Pod 恢复正常 Running 状态

[03:20:00] ✅ 问题已解决，已记录到知识库
```

### 场景 2：资源配额优化

```
[09:00:00] 💾 定期资源治理扫描
  - Namespace "default": 配额过剩 40%
    建议: CPU 配额从 8 核降至 5 核
  - Namespace "production": 配额不足
    建议: CPU 配额从 4 核升至 8 核，内存从 8Gi 升至 16Gi
  
[09:00:05] 📋 生成优化报告
  → 预计释放 3 核 CPU 和 4Gi 内存供其他工作负载使用
  → 已通过 dry-run 验证，确认无风险
  → 等待管理员确认后执行
```

### 场景 3：智能滚动更新

```
[14:00:00] 🔄 检测到 api-server v2.3.0 更新
  - 当前版本: v2.2.1 (10/10 Pods 健康)
  - 新版本: v2.3.0 (3/10 Pods 已更新)
  
[14:00:30] 📊 更新后监控
  - 错误率: 2.1% (阈值: 5%)
  - P99 延迟: 245ms (基准: 120ms)
  - 健康检查: 2/10 失败
  
[14:01:00] 🚨 LLM 评估: 应触发回滚
  - 理由: 错误率接近阈值，延迟翻倍，健康检查失败
  - 置信度: 0.88
  
[14:01:05] ⏮️  自动回滚执行
  ✅ kubectl rollout undo deployment/api-server -n production
  ✅ 回滚到 v2.2.1
  ✅ 验证: 所有 Pod 恢复正常，错误率降至 0.1%
```

---

## 八、与 Prometheus + Grafana 集成

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

Grafana Dashboard JSON 可从仓库获取，包含：
- 集群健康度趋势图
- Pod 状态分布
- 资源使用率热力图
- LLM 决策日志面板
- 自动修复事件时间线

---

## 九、最佳实践与注意事项

### 安全建议

1. **权限最小化**: LLM 控制器只授予必要的 RBAC 权限，避免 ClusterRole
2. **操作审计**: 所有 LLM 生成的操作记录到审计日志
3. **人工确认**: 高风险操作（删除 Pod、调整节点）需人工确认
4. **模型隔离**: 使用独立容器运行 Ollama，防止 LLM 注入攻击

### 性能建议

1. **采样频率**: 生产环境建议 5 分钟一次完整分析，1 分钟一次快速检查
2. **Token 优化**: 只发送必要状态信息给 LLM，避免超限
3. **缓存机制**: 相似状态可复用之前的分析结果
4. **降级策略**: LLM 不可用时回退到规则引擎

### 运维建议

1. **渐进式部署**: 先只读模式（dry-run），确认稳定后再开启自动修复
2. **告警通道**: 配置 Telegram/Slack 通知，及时发现异常
3. **知识库积累**: 每次修复记录到知识库，持续优化 LLM 决策质量
4. **定期审查**: 每周审查 LLM 决策日志，发现误判并调整 prompt

---

## 十、总结

LLM 驱动的 K3s 集群智能编排，将传统"人工操作 + 固定规则"的运维模式，升级为"语义理解 + 智能决策 + 自动执行"的 AI-Native 模式。核心价值：

| 维度 | 传统方式 | LLM 驱动方式 |
|------|---------|-------------|
| 状态感知 | 看仪表盘数字 | 语义化理解集群健康 |
| 调度决策 | 基于资源请求 | 理解业务语义和依赖关系 |
| 故障修复 | 人工排查操作 | 自动诊断 + 执行修复 |
| 资源治理 | 静态配额配置 | 动态优化调整 |
| 伸缩策略 | 固定阈值 HPA | 多维度智能决策 |

**未来演进方向**：
- 支持多集群统一管理
- 与 GitOps 工具链（ArgoCD、Flux）深度集成
- 引入强化学习，持续优化调度策略
- 支持 GPU 调度与 AI 推理任务编排

---

*本文配套代码仓库：https://github.com/selfvps/llm-k3s-manager*

*下篇预告：《AI 驱动的 VPS 智能多云资源调度与成本优化》*
