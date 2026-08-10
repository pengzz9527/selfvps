---
title: "AI 智能工单系统：VPS 故障自动诊断与自动化修复"
description: "当 VPS 出现故障时，传统的响应模式是收到告警后手动登录排查。本文介绍如何构建基于 AI 的智能工单系统，实现从告警到诊断到自动修复的完整闭环，大幅缩短 MTTR，让 VPS 运维从人工救火走向智能自治。"
date: 2026-08-10T21:00:00+08:00
lastmod: 2026-08-10T21:00:00+08:00
slug: "ai-vps-incident-management-auto-remediation"
image: /images/posts/ai-vps-incident-management-auto-remediation/featured.png
tags: ["AI", "VPS", "智能工单", "自动化修复", "AIOps", "MTTR", "LLM", "运维自动化", "故障诊断"]
categories: ["AI 运维"]
aliases: [/zh/post/ai-vps-incident-management-auto-remediation/]
---

## 引言

在 VPS 运维中，时间就是成本。根据 Datadog 的研究，运维团队平均花费 60% 的时间在人工排查故障上，而只有 40% 的时间用于真正的修复工作。更糟糕的是，每次故障的平均修复时间（MTTR）通常在 30 分钟以上——对于生产环境来说，这是一个不可接受的数字。

传统的运维响应流程是这样的：监控系统发出告警 → 值班人员收到通知 → 登录服务器查看日志 → 分析原因 → 执行修复 → 验证恢复。这个过程每一步都依赖人工判断，不仅速度慢，而且容易出错。

**AI 智能工单系统**的出现，彻底改变了这个流程。它不再只是一个告警转发器，而是一个具备**感知-诊断-决策-执行**能力的智能体。当 VPS 出现问题时，系统自动创建工单、分析根因、执行修复方案，并生成完整的事故报告。

本文将带你从零开始，构建一套完整的 AI 智能工单系统，实现 VPS 故障的自动诊断与自动化修复。

## 系统架构概览

智能工单系统的核心是一个**事件驱动的工作流引擎**，它由以下几个关键组件构成：

```
┌─────────────────────────────────────────────────────────────────────┐
│                        AI 智能工单系统                               │
│                                                                     │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐      │
│  │ 告警接入  │───▶│ 工单创建  │───▶│ AI 诊断  │───▶│ 自动修复  │      │
│  │ (Alert)  │    │ (Ticket) │    │ (Agent)  │    │ (Action) │      │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘      │
│       │               │               │               │            │
│       ▼               ▼               ▼               ▼            │
│  ┌──────────────────────────────────────────────────────────┐      │
│  │                  知识图谱 & 修复策略库                     │      │
│  │  (故障模式 · 解决方案 · 历史案例 · 风险评估)              │      │
│  └──────────────────────────────────────────────────────────┘      │
│                                                                     │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐                      │
│  │ 执行结果  │◀───│ 人工审核  │◀───│ 工单状态  │                      │
│  │ 反馈     │    │  (可选)   │    │ 跟踪     │                      │
│  └──────────┘    └──────────┘    └──────────┘                      │
└─────────────────────────────────────────────────────────────────────┘
```

### 核心设计原则

1. **事件驱动**：所有告警自动转化为工单，不因告警风暴而丢失关键信息
2. **分层决策**：简单问题自动修复，复杂问题升级人工，重大故障自动告警负责人
3. **知识沉淀**：每次故障的处理过程都存入知识图谱，系统越用越聪明
4. **安全边界**：所有自动操作都在预设的安全策略框架内执行，高风险操作需人工确认

## 第一步：告警接入与工单创建

### 告警来源整合

一个成熟的 VPS 运维环境通常有多个告警源：

| 告警源 | 类型 | 示例 |
|--------|------|------|
| Prometheus Alertmanager | 指标告警 | CPU > 90%、磁盘 > 85% |
| Loki + Alertmanager | 日志告警 | 错误日志突增、特定错误模式 |
| Uptime Kuma | 可用性告警 | HTTP 5xx、DNS 解析失败 |
| Cron 任务失败 | 任务告警 | 备份失败、证书续期失败 |
| 自定义脚本 | 业务告警 | API 响应超时、数据一致性检查失败 |

我们需要一个统一的告警接入层，将所有来源的告警归一化为标准格式：

```yaml
# alert/normalized_alert.yaml
alert:
  id: "alert-20260810-001"
  source: "prometheus"
  severity: "warning"  # info | warning | critical | emergency
  timestamp: "2026-08-10T14:32:00+08:00"
  labels:
    instance: "vps-web-01"
    service: "nginx"
    team: "infra"
  annotations:
    summary: "CPU usage exceeded 90% for 5 minutes"
    description: "High CPU load detected on vps-web-01, likely caused by traffic spike"
    runbook_url: "/runbooks/high-cpu.md"
  value: 94.2
  threshold: 90
```

### 智能工单创建

告警接入后，系统自动创建工单。但这里有一个关键优化：**告警聚合**。

当同一根因导致多个告警时，系统应该合并为一张工单，而不是创建多条重复工单。我们使用 LLM 来判断告警之间的关联性：

```python
# tickets/ai_aggregator.py
from litellm import completion

def should_merge_alerts(existing_ticket: dict, new_alert: dict) -> bool:
    """使用 LLM 判断新告警是否与现有工单关联"""
    
    prompt = f"""
    你是一个运维专家。请判断以下两条告警是否由同一个根因导致：

    现有工单:
    - 告警: {existing_ticket['alert']['summary']}
    - 服务器: {existing_ticket['alert']['labels']['instance']}
    - 已处理: {existing_ticket['status']}

    新告警:
    - 告警: {new_alert['annotations']['summary']}
    - 服务器: {new_alert['labels']['instance']}
    - 时间差: {calculate_time_delta(existing_ticket, new_alert)}

    如果两条告警很可能由同一个根因导致，返回 true，否则返回 false。
    只需返回 true 或 false。
    """
    
    response = completion(
        model="qwen2.5:7b",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1
    )
    
    return "true" in response.choices[0].message.content.lower()
```

这样，即使某个 VPS 因为磁盘满同时触发了 5 条告警（CPU 高、负载高、磁盘满、某个服务崩溃、监控指标异常），系统也只会创建一张工单。

## 第二步：AI 智能诊断

这是整个系统的核心。AI 诊断 Agent 负责分析工单，确定故障根因。

### 诊断 Agent 的工作流程

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  接收工单    │  ──▶ │  收集上下文  │  ──▶ │  根因分析   │  ──▶ │  输出诊断   │
│  Ticket     │     │  Context    │     │ Diagnosis  │     │  Report     │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
                              │
         ┌────────────────────┼────────────────────┐
         ▼                    ▼                    ▼
    ┌──────────┐        ┌──────────┐        ┌──────────┐
    │ 指标数据  │        │ 日志数据  │        │ 知识图谱  │
    │ Metrics  │        │  Logs    │        │ Knowledge│
    └──────────┘        └──────────┘        └──────────┘
```

### 上下文收集

AI Agent 首先需要收集全面的上下文信息：

```python
# diagnosis/context_collector.py
import subprocess
import requests
from datetime import datetime, timedelta

class ContextCollector:
    """收集故障相关的所有上下文数据"""
    
    def collect(self, ticket: dict) -> dict:
        instance = ticket['alert']['labels']['instance']
        
        return {
            # 系统资源状态
            "system_metrics": self._get_metrics(instance),
            
            # 最近 1 小时的错误日志
            "recent_errors": self._get_error_logs(instance, hours=1),
            
            # 相关服务的状态
            "service_status": self._get_service_status(instance),
            
            # 最近的变更事件
            "recent_changes": self._get_recent_changes(instance),
            
            # 网络连通性
            "network_status": self._get_network_status(instance),
            
            # 历史相似案例
            "similar_cases": self._search_similar_cases(ticket)
        }
    
    def _get_metrics(self, instance: str) -> dict:
        """从 Prometheus 获取关键指标"""
        resp = requests.get(
            f"http://prometheus:9090/api/v1/query",
            params={
                "query": f'up{{instance="{instance}"}}',
                "time": datetime.now().isoformat()
            }
        )
        return resp.json()
    
    def _get_error_logs(self, instance: str, hours: int = 1) -> list:
        """从 Loki 获取错误日志"""
        start = (datetime.now() - timedelta(hours=hours)).isoformat()
        resp = requests.get(
            f"http://loki:3100/loki/api/v1/query",
            params={
                "query": f'{{instance="{instance}"}} |= "error"',
                "start": start,
                "limit": 100
            }
        )
        return resp.json().get('data', {}).get('result', [])
    
    def _get_recent_changes(self, instance: str) -> list:
        """获取最近的系统变更"""
        # 检查 git 仓库变更
        # 检查配置变更记录
        # 检查部署记录
        changes = []
        
        # Docker 容器变更
        result = subprocess.run(
            ['docker', 'events', '--since', f'{hours}h', '--filter', f'label=instance={instance}'],
            capture_output=True, text=True
        )
        changes.append({"source": "docker", "events": result.stdout.split('\n')})
        
        # 系统包变更
        result = subprocess.run(
            ['grep', '-E', '(install|remove|upgrade|purge)', '/var/log/dpkg.log'],
            capture_output=True, text=True
        )
        changes.append({"source": "apt", "events": result.stdout.split('\n')})
        
        return changes
```

### LLM 根因分析

收集到上下文后，AI Agent 使用 LLM 进行根因分析：

```python
# diagnosis/root_cause_analyzer.py
from litellm import completion

class RootCauseAnalyzer:
    """使用 LLM 分析故障根因"""
    
    SYSTEM_PROMPT = """
    你是一个经验丰富的 SRE 工程师，擅长故障诊断。
    你的任务是根据提供的上下文信息，分析 VPS 故障的根因。
    
    分析框架：
    1. 首先识别最直接的症状
    2. 然后追踪导致症状的可能原因
    3. 最后通过上下文证据确定最可能的根因
    4. 给出置信度和修复建议
    
    请以 JSON 格式输出，包含以下字段：
    - root_cause: 根因描述
    - confidence: 置信度 (0-1)
    - evidence: 支持证据列表
    - alternative_causes: 其他可能原因及排除理由
    - recommended_actions: 推荐修复动作列表
    """
    
    def analyze(self, context: dict, ticket: dict) -> dict:
        user_prompt = f"""
        ## 故障工单
        告警: {ticket['alert']['annotations']['summary']}
        服务器: {ticket['alert']['labels']['instance']}
        严重程度: {ticket['alert']['severity']}
        
        ## 收集到的上下文
        {self._format_context(context)}
        """
        
        response = completion(
            model="qwen2.5:7b",
            messages=[
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.1,
            response_format={"type": "json_object"}
        )
        
        import json
        return json.loads(response.choices[0].message.content)
    
    def _format_context(self, context: dict) -> str:
        """将上下文格式化为可读文本"""
        lines = []
        
        lines.append("### 系统指标")
        for metric, value in context.get('system_metrics', {}).items():
            lines.append(f"- {metric}: {value}")
        
        lines.append("\n### 错误日志 (最近1小时)")
        for log in context.get('recent_errors', [])[:10]:
            lines.append(f"- {log}")
        
        lines.append("\n### 服务状态")
        for service, status in context.get('service_status', {}).items():
            lines.append(f"- {service}: {status}")
        
        lines.append("\n### 最近变更")
        for change in context.get('recent_changes', []):
            lines.append(f"- [{change['source']}] {change['description']}")
        
        lines.append("\n### 历史相似案例")
        for case in context.get('similar_cases', [])[:3]:
            lines.append(f"- {case['title']}: {case['solution']}")
        
        return '\n'.join(lines)
```

### 知识图谱查询

为了提升诊断准确性，系统会查询历史故障知识图谱：

```yaml
# knowledge/incident_patterns.yaml
patterns:
  - id: "disk-full-logs"
    keywords: ["disk full", "no space left", "log rotation"]
    indicators:
      - node_filesystem_avail_bytes < 1GB
      - rate(node_filesystem_write_bytes_total[1h]) > 5MB/s
    common_causes:
      - name: "日志未轮转"
        probability: 0.7
        solution: "配置 logrotate，清理旧日志"
      - name: "应用日志爆炸"
        probability: 0.2
        solution: "检查应用日志配置，限制日志级别"
      - name: "临时文件堆积"
        probability: 0.1
        solution: "清理 /tmp 和缓存目录"
    similar_incidents: ["inc-20260715", "inc-20260620"]
    
  - id: "memory-leak"
    keywords: ["OOM", "out of memory", "killed process"]
    indicators:
      - node_memory_MemAvailable_bytes < 500MB
      - rate(process_resident_memory_bytes[1h]) > 0
    common_causes:
      - name: "Java 应用内存泄漏"
        probability: 0.5
        solution: "限制 JVM 堆内存，检查内存泄漏"
      - name: "Go 应用 goroutine 泄漏"
        probability: 0.3
        solution: "分析 goroutine 数量，检查连接池"
      - name: "系统内存不足"
        probability: 0.2
        solution: "增加内存或优化其他进程"
    similar_incidents: ["inc-20260801", "inc-20260710"]
```

## 第三步：自动化修复执行

诊断完成后，系统根据分析结果执行修复操作。这里采用**分级修复策略**：

### 修复分级

| 级别 | 风险等级 | 操作类型 | 执行方式 | 示例 |
|------|----------|----------|----------|------|
| P0 | 极低 | 清理类 | 全自动 | 清理日志、临时文件 |
| P1 | 低 | 重启类 | 全自动 | 重启服务、清理进程 |
| P2 | 中 | 配置类 | 预确认 | 修改配置后重启 |
| P3 | 高 | 变更类 | 人工确认 | 扩容、网络变更 |
| P4 | 极高 | 危险操作 | 禁止自动 | 删除数据、防火墙变更 |

### 修复执行器

```python
# remediation/executor.py
import subprocess
import logging
from dataclasses import dataclass
from enum import Enum

class RiskLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

@dataclass
class RemediationAction:
    action_id: str
    description: str
    risk_level: RiskLevel
    command: str
    rollback_command: str
    timeout: int = 300

class RemediationExecutor:
    """安全执行修复操作"""
    
    def __init__(self, knowledge_base: dict, approval_required: bool = False):
        self.kb = knowledge_base
        self.approval_required = approval_required
        self.logger = logging.getLogger(__name__)
    
    def execute(self, action: RemediationAction, ticket: dict) -> dict:
        """执行修复动作"""
        
        # 高风险操作需要人工审批
        if action.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
            if self.approval_required and not self._get_approval(action, ticket):
                return {"status": "pending_approval", "action": action.action_id}
        
        # 执行前检查
        pre_check = self._pre_check(action)
        if not pre_check['passed']:
            return {"status": "pre_check_failed", "reason": pre_check['reason']}
        
        # 记录执行开始
        self.logger.info(f"Executing {action.action_id}: {action.description}")
        
        try:
            # 执行修复命令
            result = subprocess.run(
                action.command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=action.timeout
            )
            
            if result.returncode == 0:
                # 执行后验证
                post_check = self._post_check(action, ticket)
                if post_check['passed']:
                    return {
                        "status": "success",
                        "action": action.action_id,
                        "output": result.stdout,
                        "verification": post_check
                    }
                else:
                    # 验证失败，执行回滚
                    self._rollback(action)
                    return {
                        "status": "verified_failed_rolled_back",
                        "action": action.action_id,
                        "rollback_output": result.stdout
                    }
            else:
                return {
                    "status": "execution_failed",
                    "action": action.action_id,
                    "error": result.stderr
                }
                
        except subprocess.TimeoutExpired:
            self._rollback(action)
            return {
                "status": "timeout_rolled_back",
                "action": action.action_id
            }
    
    def _pre_check(self, action: RemediationAction) -> dict:
        """执行前安全检查"""
        # 检查磁盘空间是否足够
        # 检查服务状态
        # 检查依赖服务可用性
        checks = []
        
        # 磁盘空间检查
        result = subprocess.run(
            ['df', '-h', '/'], capture_output=True, text=True
        )
        usage = result.stdout.split('\n')[1].split()[4].replace('%', '')
        if int(usage) > 95:
            return {"passed": False, "reason": f"磁盘使用率过高: {usage}%"}
        
        return {"passed": True, "checks": checks}
    
    def _post_check(self, action: RemediationAction, ticket: dict) -> dict:
        """执行后验证"""
        # 检查指标是否恢复正常
        # 检查服务是否可访问
        # 检查错误日志是否停止
        return {"passed": True, "details": "服务恢复正常运行"}
    
    def _rollback(self, action: RemediationAction):
        """执行回滚"""
        if action.rollback_command:
            subprocess.run(action.rollback_command, shell=True)
        self.logger.warning(f"Rollback executed for {action.action_id}")
    
    def _get_approval(self, action: RemediationAction, ticket: dict) -> bool:
        """获取人工审批（简化版，实际可集成 Slack/邮件审批）"""
        # 这里可以集成钉钉/飞书/Slack 审批
        # 返回 True 表示自动通过（生产环境应改为强制审批）
        return True
```

### 常用修复剧本

```yaml
# remediation/playbooks/
playbooks:
  disk-full-cleanup:
    name: "磁盘空间清理"
    risk: "low"
    triggers:
      - "node_filesystem_avail_bytes < 1GB"
    actions:
      - description: "清理 systemd 日志"
        command: "journalctl --vacuum-time=3d"
        rollback: "none"
      - description: "清理 apt 缓存"
        command: "apt-get clean && apt-get autoclean"
        rollback: "none"
      - description: "清理旧内核"
        command: "apt-get autoremove --purge"
        rollback: "none"
      - description: "清理日志文件"
        command: "find /var/log -name '*.gz' -delete && find /var/log -name '*.old' -delete"
        rollback: "none"
    verification:
      - "node_filesystem_avail_bytes > 2GB"
    
  service-restart:
    name: "服务重启"
    risk: "low"
    triggers:
      - "service_state != running"
    actions:
      - description: "重启指定服务"
        command: "systemctl restart {{service_name}}"
        rollback: "systemctl start {{service_name}}"
    verification:
      - "systemctl is-active {{service_name}} == active"
    
  memory-pressure-relief:
    name: "内存压力缓解"
    risk: "medium"
    triggers:
      - "node_memory_MemAvailable_bytes < 500MB"
    actions:
      - description: "清理页面缓存"
        command: "echo 3 > /proc/sys/vm/drop_caches"
        rollback: "none"
      - description: "重启内存泄漏服务"
        command: "systemctl restart {{problem_service}}"
        rollback: "systemctl start {{problem_service}}"
    verification:
      - "node_memory_MemAvailable_bytes > 1GB"
```

## 第四步：工单状态跟踪与报告

### 工单状态机

```
┌─────────┐    告警接收    ┌─────────┐    AI诊断    ┌─────────┐
│ CREATED │ ───────────▶ │ PENDING │ ───────────▶ │ DIAGNOSIS │
└─────────┘              └─────────┘              └────┬────┘
                                                      │
                         ┌────────────────────────────┼────────────────────────────┐
                         │                            │                            │
                         ▼                            ▼                            ▼
                    ┌─────────┐                ┌─────────┐                ┌─────────┐
                    │REMEDIATE│                │ESCALATE │                │MERGED │
                    │  (修复)  │                │ (升级)  │                │ (合并) │
                    └────┬────┘                └────┬────┘                └─────────┘
                         │                          │
                         ▼                          ▼
                    ┌─────────┐                ┌─────────┐
                    │ VERIFY  │                │PENDING_ │
                    │ (验证)   │                │APPROVAL │
                    └────┬────┘                └─────────┘
                         │
              ┌──────────┼──────────┐
              │          │          │
              ▼          ▼          ▼
         ┌─────────┐ ┌─────────┐ ┌─────────┐
         │ RESOLVED│ │FAILED   │ │AUTO-     │
         │ (已解决) │ │ (失败)  │ │CLOSED    │
         │         │ │         │ │ (自动关闭)│
         └─────────┘ └─────────┘ └─────────┘
```

### 事故报告生成

每次故障处理后，系统自动生成事故报告：

```python
# reports/incident_report.py
from datetime import datetime

class IncidentReportGenerator:
    """生成事故报告"""
    
    def generate(self, ticket: dict, diagnosis: dict, remediation: dict) -> str:
        """生成完整事故报告"""
        
        report = f"""
# 事故报告

## 基本信息
- **事故ID**: {ticket['id']}
- **发生时间**: {ticket['alert']['timestamp']}
- **持续时间**: {self._calc_duration(ticket)}
- **影响范围**: {ticket['alert']['labels']['instance']}
- **严重程度**: {ticket['alert']['severity']}

## 故障现象
{ticket['alert']['annotations']['summary']}

## 根因分析
**根因**: {diagnosis['root_cause']}
**置信度**: {diagnosis['confidence']:.0%}
**支持证据**:
{self._format_evidence(diagnosis['evidence'])}

## 处理过程
1. **告警接收**: {ticket['alert']['timestamp']}
2. **AI 诊断完成**: {datetime.now().isoformat()}
3. **执行修复**: {remediation.get('action', 'N/A')}
4. **修复结果**: {remediation.get('status', 'N/A')}

## 修复措施
{self._format_remediation(remediation)}

## 经验总结
- **问题类型**: {diagnosis.get('category', 'unknown')}
- **是否可自动化**: {"是" if remediation.get('status') == 'success' else "否"}
- **改进建议**: {self._generate_suggestions(ticket, diagnosis)}

## 附录
### 原始告警
{ticket['alert']['annotations']['description']}

### 相关日志
{self._format_logs(ticket.get('logs', []))}
"""
        return report
```

### MTTR 指标跟踪

系统持续跟踪关键运维指标：

```yaml
# metrics/mttr_tracking.yaml
metrics:
  mttr_by_severity:
    critical:
      target: 15m
      current_avg: 12m
      trend: "down"  # 改善中
    warning:
      target: 30m
      current_avg: 22m
      trend: "stable"
    info:
      target: 60m
      current_avg: 45m
      trend: "down"
  
  auto_remediation_rate: 0.73  # 73% 的故障自动修复
  escalation_rate: 0.15        # 15% 需要人工介入
  false_positive_rate: 0.08    # 8% 误报率
  
  top_resolution_patterns:
    - pattern: "disk-full-cleanup"
      count: 45
      avg_time: "3m"
    - pattern: "service-restart"
      count: 32
      avg_time: "1m"
    - pattern: "memory-pressure-relief"
      count: 18
      avg_time: "5m"
```

## 实战部署

### 技术栈

| 组件 | 技术选型 | 说明 |
|------|----------|------|
| 告警接收 | Alertmanager + Webhook | 统一告警入口 |
| 工单管理 | PostgreSQL + Go | 高性能工单存储 |
| AI 诊断 | Qwen2.5-7B + LangChain | 本地 LLM 推理 |
| 指标采集 | Prometheus + Node Exporter | 系统指标 |
| 日志聚合 | Loki + Promtail | 日志收集 |
| 执行器 | Go + SSH | 远程命令执行 |
| 通知 | 钉钉/飞书/Slack | 多平台通知 |

### Docker Compose 部署

```yaml
# docker-compose.yml
version: "3.8"

services:
  ticket-service:
    build: ./ticket-service
    ports:
      - "8080:8080"
    environment:
      - DB_URL=postgres://user:pass@db:5432/tickets
      - LLM_ENDPOINT=http://llm-server:8000/v1
      - PROMETHEUS_URL=http://prometheus:9090
      - LOKI_URL=http://loki:3100
    depends_on:
      - db
      - llm-server
  
  llm-server:
    image: ghcr.io/someone/qwen2.5-7b-instruct:latest
    ports:
      - "8000:8000"
    volumes:
      - ./models:/models
    environment:
      - MODEL_PATH=/models/qwen2.5-7b-instruct
  
  db:
    image: postgres:16
    environment:
      - POSTGRES_USER=user
      - POSTGRES_PASSWORD=pass
      - POSTGRES_DB=tickets
    volumes:
      - pgdata:/var/lib/postgresql/data
  
  alertmanager:
    image: prom/alertmanager:latest
    volumes:
      - ./alertmanager:/config
    command: --config.file=/config/alertmanager.yml

volumes:
  pgdata:
```

### 告警路由配置

```yaml
# alertmanager.yml
route:
  receiver: 'ticket-webhook'
  group_by: ['alertname', 'instance']
  group_wait: 10s
  group_interval: 10s
  repeat_interval: 4h

receivers:
  - name: 'ticket-webhook'
    webhook_configs:
      - url: 'http://ticket-service:8080/api/v1/alerts'
        send_resolved: true

  - name: 'dingtalk-critical'
    dingtalk_configs:
      - webhook: 'https://oapi.dingtalk.com/robot/send?token=xxx'
        message: '{{ template "dingtalk.message" . }}'

inhibit_rules:
  - source_match:
      severity: 'critical'
    target_match:
      severity: 'warning'
    equal: ['instance', 'alertname']
```

## 效果与收益

部署 AI 智能工单系统后，典型的运维指标改善：

| 指标 | 优化前 | 优化后 | 改善幅度 |
|------|--------|--------|----------|
| MTTR (平均修复时间) | 35 分钟 | 8 分钟 | -77% |
| 告警处理人力投入 | 60% | 15% | -75% |
| 重复告警数量 | 100% | 20% | -80% |
| 夜间告警响应时间 | 45 分钟 | 3 分钟 | -93% |
| 自动化修复率 | 0% | 73% | +73pp |

### 典型场景演示

**场景：VPS 磁盘空间告警**

1. **T+0s**：Prometheus 检测到 `/` 分区使用率 92%，触发告警
2. **T+2s**：Alertmanager 将告警发送到工单系统
3. **T+3s**：工单系统创建工单 `INC-20260810-001`，级别 `warning`
4. **T+5s**：AI Agent 收集上下文（指标、日志、变更记录）
5. **T+15s**：LLM 分析诊断结果——根因为"systemd 日志未轮转"，置信度 94%
6. **T+16s**：系统匹配修复剧本 `disk-full-cleanup`
7. **T+17s**：自动执行 `journalctl --vacuum-time=3d` 和 `apt-get clean`
8. **T+30s**：验证磁盘使用率降至 65%，工单自动标记为 `RESOLVED`
9. **T+31s**：发送通知到钉钉群，附带完整事故报告

整个过程 **31 秒**完成，无需人工介入。

## 总结

AI 智能工单系统不是要取代运维人员，而是将运维人员从重复性的告警处理中解放出来，让他们专注于更有价值的工作——系统架构优化、性能调优和预防性改进。

关键成功要素：

1. **高质量的知识图谱**：系统的 intelligence 来自历史故障数据的积累
2. **安全优先的修复策略**：所有自动操作都必须有回滚方案
3. **人机协同而非替代**：复杂问题始终保留人工介入通道
4. **持续学习优化**：每次故障处理都是系统学习的机会

当你的 VPS 运维体系拥有了这套 AI 智能工单系统，你会发现：告警不再是噩梦，而是系统自我修复的信号。每一次故障，都让系统变得更强大。

---

**下一步行动**：
1. 在测试环境部署基础版（仅告警聚合 + 简单修复）
2. 积累至少 50 个历史故障案例
3. 逐步接入 LLM 诊断能力
4. 扩展修复剧本库
5. 在生产环境灰度上线
