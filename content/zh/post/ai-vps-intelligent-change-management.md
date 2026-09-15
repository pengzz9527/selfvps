---
title: "AI + VPS：用本地大模型构建智能变更管理与发布安全系统"
description: "传统 VPS 变更依赖人工审批和经验判断，容易出错且效率低下。本文介绍如何在 VPS 上部署基于本地 LLM 的智能变更管理系统，实现变更风险自动评估、回滚方案自动生成、发布后健康验证与安全门禁，让每次变更都安全可靠。"
date: 2026-09-15T21:00:00+08:00
lastmod: 2026-09-15T21:00:00+08:00
slug: "ai-vps-intelligent-change-management"
tags: ["AI", "VPS", "变更管理", "发布安全", "LLM", "自动化", "回滚", "Ollama", "GitOps"]
categories: ["AI + VPS"]
aliases: [/zh/post/ai-vps-intelligent-change-management/]
image: /images/posts/ai-vps-intelligent-change-management/featured.png
---

## 引言：当变更成为服务器最大的恐惧

作为 VPS 运维人员，你一定经历过这样的场景：

凌晨两点，你收到一条生产环境的变更通知——某个服务需要紧急更新配置。你 hurriedly 登录服务器，手动修改 Nginx 配置，重启服务。十分钟后，监控报警：CPU 飙升到 98%，服务完全无法访问。

你开始排查问题，发现是新配置的某个参数写错了。紧急回滚配置，服务恢复。但你心里清楚：**如果有一个系统能提前识别这个风险，这一切都可以避免。**

传统 VPS 变更管理的痛点非常突出：

- **变更风险评估靠经验**：老运维一眼看出问题，新人完全不知道风险在哪
- **回滚方案临时编写**：每次变更都要现场想怎么回滚，手忙脚乱
- **发布后验证依赖人工**：改完后要手动检查各项指标，容易遗漏
- **变更记录分散**：git 提交、工单系统、聊天记录，信息碎片化
- **审批流程形式化**：紧急变更往往跳过审批，事后补单

这些问题在单体 VPS 上可能还不致命，但当你管理 10 台、50 台甚至更多服务器时，变更风险会指数级增长。

**AI 驱动的变更管理系统**正是为了解决这些问题而生。通过在本地 VPS 上部署大模型，我们可以实现：

1. **自动变更风险评估**：分析变更内容，预测潜在风险
2. **智能回滚方案生成**：根据变更类型自动生成可执行的回滚脚本
3. **发布后健康验证**：自动检测变更后的服务状态，判断是否成功
4. **变更日志智能关联**：将 git 提交、部署记录、监控告警关联在一起
5. **安全门禁自动执行**：高风险变更自动触发审批流程

让我们一步步构建这个系统。

---

## 一、系统架构设计

```
┌─────────────────────────────────────────────────────────────────────┐
│                        用户交互层                                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │  Web 控制台   │  │  Slack/飞书   │  │  CLI 命令行   │              │
│  │  (React)     │  │  Bot         │  │  (Python)    │              │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘              │
│         └──────────────────┼──────────────────┘                     │
│                            ▼                                         │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    变更管理 API 服务                          │    │
│  │              (FastAPI + PostgreSQL + Redis)                  │    │
│  └──────────────────┬──────────────────────────────────────────┘    │
│                     │                                                 │
│         ┌───────────┼───────────┬───────────┬───────────┐          │
│         ▼           ▼           ▼           ▼           ▼          │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ │
│  │ 风险评估  │ │ 回滚生成  │ │ 健康验证  │ │ 日志关联  │ │ 安全门禁  │ │
│  │ 引擎     │ │ 引擎     │ │ 引擎     │ │ 引擎     │ │ 引擎     │ │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ │
│       │            │            │            │            │        │
│  ┌────▼────────────▼────────────▼────────────▼────────────▼────┐  │
│  │                    本地 LLM 服务 (Ollama)                      │  │
│  │              Qwen2.5-7B / Llama-3.2-3B / Gemma-3             │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                       │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                    基础设施层                                  │   │
│  │  Git Repo │ Prometheus │ Docker │ Kubernetes │ 配置文件管理    │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

系统分为五层：

1. **用户交互层**：Web 控制台、IM Bot、CLI 三种入口，适配不同场景
2. **API 服务层**：基于 FastAPI 的核心服务，处理变更请求、协调各引擎
3. **引擎层**：五个核心引擎，各自负责不同的变更管理职能
4. **LLM 服务层**：本地部署的 Ollama，提供 AI 推理能力
5. **基础设施层**：Git、监控、容器等现有基础设施

---

## 二、风险评估引擎

风险评估是整个系统的核心。它的任务是：**分析变更内容，预测潜在风险等级**。

### 2.1 风险数据收集

风险评估需要收集以下维度的数据：

```python
# risk_analyzer.py - 风险数据采集
import subprocess
import json
from datetime import datetime
from typing import Dict, List, Any

class RiskDataCollector:
    """收集变更相关的风险数据"""
    
    def collect_context(self, change_id: str) -> Dict[str, Any]:
        return {
            "change_id": change_id,
            "timestamp": datetime.now().isoformat(),
            "server_info": self._collect_server_info(),
            "service_status": self._collect_service_status(),
            "recent_changes": self._collect_recent_changes(),
            "monitoring_alerts": self._collect_alerts(),
            "resource_usage": self._collect_resource_usage(),
            "dependency_map": self._collect_dependency_map(),
        }
    
    def _collect_server_info(self) -> Dict:
        """收集服务器基础信息"""
        return {
            "hostname": subprocess.getoutput("hostname"),
            "os": subprocess.getoutput("cat /etc/os-release | grep PRETTY_NAME"),
            "cpu_cores": subprocess.getoutput("nproc"),
            "memory_total": subprocess.getoutput("free -h | awk '/^Mem:/{print $2}'"),
            "disk_total": subprocess.getoutput("df -h / | awk 'NR==2{print $2}'"),
        }
    
    def _collect_service_status(self) -> List[Dict]:
        """收集服务运行状态"""
        services = {}
        # Docker 容器
        containers = subprocess.getoutput(
            "docker ps --format '{{.Names}}|{{.Status}}|{{.Ports}}'"
        ).split("\n")
        for c in containers:
            if c:
                parts = c.split("|")
                services[parts[0]] = {"status": parts[1], "ports": parts[2]}
        return services
    
    def _collect_recent_changes(self, days: int = 7) -> List[Dict]:
        """收集近期的变更记录"""
        changes = []
        # Git 变更历史
        git_log = subprocess.getoutput(
            f"cd /etc/services && git log --oneline --since={days}days"
        )
        for line in git_log.split("\n")[:20]:
            if line:
                changes.append({"type": "git", "content": line})
        
        # 配置变更（通过 auditd 或 journalctl）
        journal = subprocess.getoutput(
            f"journalctl --since '{days} days ago' "
            "-u nginx -u postgresql -u docker --no-pager"
        )
        if journal.strip():
            changes.append({"type": "journal", "content": journal[:2000]})
        return changes
    
    def _collect_alerts(self, hours: int = 24) -> List[Dict]:
        """收集近期的告警记录"""
        alerts = subprocess.getoutput(
            f"curl -s 'http://localhost:9090/api/v1/alerts?"
            f"start={int(datetime.now().timestamp()) - hours*3600}'"
        )
        try:
            return json.loads(alerts).get("data", {}).get("alerts", [])
        except:
            return []
    
    def _collect_resource_usage(self) -> Dict:
        """收集当前资源使用状况"""
        return {
            "cpu": subprocess.getoutput("top -bn1 | grep 'Cpu(s)' | awk '{print $2}'"),
            "memory": subprocess.getoutput(
                "free | awk '/^Mem:/ {printf \"%.1f%%\", $3/$2 * 100}'"
            ),
            "disk": subprocess.getoutput(
                "df -h / | awk 'NR==2{printf \"%.1f%%\", $5}'"
            ),
            "load_avg": subprocess.getoutput(
                "cat /proc/loadavg | awk '{print $1, $2, $3}'"
            ),
        }
    
    def _collect_dependency_map(self) -> Dict:
        """收集服务依赖关系"""
        deps = {}
        # 分析 docker-compose 依赖
        compose_files = subprocess.getoutput(
            "find /etc/services -name docker-compose.yml -o -name docker-compose.yaml"
        )
        for f in compose_files.strip().split("\n"):
            if f and subprocess.os.path.exists(f):
                deps[f] = "loaded"
        return deps
```

### 2.2 LLM 风险评估

收集到数据后，我们调用本地 LLM 进行风险分析：

```python
# risk_assessment.py - LLM 风险评估
import json
import requests
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum

class RiskLevel(Enum):
    LOW = "低风险"
    MEDIUM = "中风险"
    HIGH = "高风险"
    CRITICAL = "严重风险"

@dataclass
class RiskAssessment:
    risk_level: RiskLevel
    risk_score: int  # 0-100
    risk_factors: List[Dict[str, str]] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    rollback_needed: bool = True
    approval_required: bool = False
    detailed_analysis: str = ""

class RiskAssessmentEngine:
    """基于 LLM 的风险评估引擎"""
    
    def __init__(self, ollama_url: str = "http://localhost:11434"):
        self.ollama_url = ollama_url
        self.model = "qwen2.5:7b"  # 可根据资源调整
    
    def assess_risk(self, context: Dict, change_description: str) -> RiskAssessment:
        """执行风险评估"""
        
        # 构建风险评估 prompt
        prompt = self._build_risk_prompt(context, change_description)
        
        # 调用 LLM
        llm_response = self._call_llm(prompt)
        
        # 解析结果
        assessment = self._parse_assessment(llm_response, change_description)
        
        return assessment
    
    def _build_risk_prompt(self, context: Dict, change_description: str) -> str:
        """构建风险评估 prompt"""
        
        risk_indicators = self._extract_risk_indicators(context)
        
        prompt = f"""你是一位经验丰富的运维安全专家。请分析以下 VPS 变更请求的风险。

## 变更信息
{change_description}

## 当前系统状态
- 服务器: {context.get('server_info', {}).get('hostname', 'unknown')}
- CPU 核心: {context.get('server_info', {}).get('cpu_cores', 'unknown')}
- 内存总量: {context.get('server_info', {}).get('memory_total', 'unknown')}
- 磁盘总量: {context.get('server_info', {}).get('disk_total', 'unknown')}
- 当前 CPU 使用率: {context.get('resource_usage', {}).get('cpu', 'unknown')}
- 当前内存使用率: {context.get('resource_usage', {}).get('memory', 'unknown')}
- 当前磁盘使用率: {context.get('resource_usage', {}).get('disk', 'unknown')}
- 负载均值: {context.get('resource_usage', {}).get('load_avg', 'unknown')}

## 运行中的服务
{json.dumps(context.get('service_status', {}), indent=2, ensure_ascii=False)}

## 近期告警 ({len(context.get('monitoring_alerts', []))} 条)
{json.dumps(context.get('monitoring_alerts', [])[:5], indent=2, ensure_ascii=False)}

## 近期变更记录 ({len(context.get('recent_changes', []))} 条)
{json.dumps(context.get('recent_changes', [])[:5], indent=2, ensure_ascii=False)}

## 风险指标分析
{json.dumps(risk_indicators, indent=2, ensure_ascii=False)}

请按照以下 JSON 格式输出风险评估结果（不要包含其他内容）：
{{
  "risk_level": "低风险|中风险|高风险|严重风险",
  "risk_score": 0-100的整数,
  "risk_factors": [
    {{"factor": "风险因素描述", "severity": "高|中|低"}}
  ],
  "recommendations": ["建议1", "建议2"],
  "rollback_needed": true/false,
  "approval_required": true/false,
  "detailed_analysis": "详细分析说明"
}}
"""
        return prompt
    
    def _extract_risk_indicators(self, context: Dict) -> Dict:
        """提取风险指标"""
        indicators = {}
        
        # 资源压力指标
        mem_usage = context.get('resource_usage', {}).get('memory', '0%')
        if '%' in mem_usage:
            try:
                mem_pct = float(mem_usage.replace('%', ''))
                indicators['memory_pressure'] = 'high' if mem_pct > 85 else ('medium' if mem_pct > 70 else 'low')
            except:
                indicators['memory_pressure'] = 'unknown'
        
        # 告警数量指标
        alert_count = len(context.get('monitoring_alerts', []))
        indicators['active_alerts'] = alert_count
        indicators['alert_severity'] = 'high' if alert_count > 5 else ('medium' if alert_count > 2 else 'low')
        
        # 近期变更频率
        recent_changes = len(context.get('recent_changes', []))
        indicators['change_frequency'] = recent_changes
        indicators['recent_change_risk'] = 'high' if recent_changes > 10 else ('medium' if recent_changes > 5 else 'low')
        
        # 关键服务状态
        services = context.get('service_status', {})
        degraded_services = [s for s, info in services.items() 
                           if 'unhealthy' in info.get('status', '').lower() 
                           or 'starting' in info.get('status', '').lower()]
        indicators['degraded_services'] = len(degraded_services)
        
        return indicators
    
    def _call_llm(self, prompt: str) -> str:
        """调用 Ollama API"""
        try:
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json={"model": self.model, "prompt": prompt, "stream": False},
                timeout=120
            )
            return response.json().get("response", "")
        except Exception as e:
            return f"LLM调用失败: {e}"
    
    def _parse_assessment(self, response: str, change_desc: str) -> RiskAssessment:
        """解析 LLM 返回的风险评估"""
        try:
            # 提取 JSON 部分
            start = response.find('{')
            end = response.rfind('}')
            if start != -1 and end != -1:
                json_str = response[start:end+1]
                data = json.loads(json_str)
            else:
                # 解析失败，返回默认低风险
                return RiskAssessment(
                    risk_level=RiskLevel.LOW,
                    risk_score=10,
                    risk_factors=[{"factor": "LLM解析异常，采用默认低风险策略", "severity": "低"}],
                    recommendations=["请人工复核变更内容"],
                    rollback_needed=True,
                    approval_required=False,
                    detailed_analysis=f"LLM响应解析异常，原始响应: {response[:500]}"
                )
            
            # 映射风险等级
            level_map = {
                "低风险": RiskLevel.LOW,
                "中风险": RiskLevel.MEDIUM,
                "高风险": RiskLevel.HIGH,
                "严重风险": RiskLevel.CRITICAL,
            }
            
            return RiskAssessment(
                risk_level=level_map.get(data.get("risk_level", "低风险"), RiskLevel.LOW),
                risk_score=data.get("risk_score", 10),
                risk_factors=data.get("risk_factors", []),
                recommendations=data.get("recommendations", []),
                rollback_needed=data.get("rollback_needed", True),
                approval_required=data.get("approval_required", False),
                detailed_analysis=data.get("detailed_analysis", "")
            )
        except Exception as e:
            return RiskAssessment(
                risk_level=RiskLevel.MEDIUM,
                risk_score=30,
                risk_factors=[{"factor": f"解析异常: {e}", "severity": "中"}],
                recommendations=["请人工复核变更内容"],
                rollback_needed=True,
                approval_required=True,
                detailed_analysis=str(e)
            )
```

### 2.3 风险评估示例

假设我们计划进行一次 Nginx 配置更新：

```python
# 示例：评估一次 Nginx 配置变更
analyzer = RiskAssessmentEngine()

context = collector.collect_context("change-20260915-001")

assessment = analyzer.assess_risk(
    context=context,
    change_description="""
    变更类型：Nginx 配置更新
    变更内容：
    - 修改 /etc/nginx/nginx.conf
    - 将 worker_processes 从 auto 改为 4
    - 新增 upstream backend 配置
    - 重启 nginx 服务
    影响服务：nginx (端口 80/443)
    变更窗口：凌晨 2:00-3:00
    负责人：张三
    """
)

print(f"风险等级: {assessment.risk_level.value}")
print(f"风险评分: {assessment.risk_score}/100")
print(f"需要回滚方案: {'是' if assessment.rollback_needed else '否'}")
print(f"需要审批: {'是' if assessment.approval_required else '否'}")
print(f"\n风险因素:")
for f in assessment.risk_factors:
    print(f"  - [{f['severity']}] {f['factor']}")
print(f"\n建议措施:")
for r in assessment.recommendations:
    print(f"  - {r}")
```

输出示例：

```
风险等级: 中风险
风险评分: 45/100
需要回滚方案: 是
需要审批: 否

风险因素:
  - [中] worker_processes 修改可能影响现有连接
  - [中] 新增 upstream 配置需要后端服务就绪
  - [低] 当前内存使用率正常 (62%)

建议措施:
  - 建议在变更窗口期内执行
  - 变更前备份当前配置文件
  - 准备回滚脚本
  - 变更后逐步验证 HTTP 响应码和服务可用性
```

---

## 三、智能回滚方案生成

回滚是变更安全的关键保障。传统方式下，运维人员需要在变更时临时编写回滚脚本，常常因为时间紧迫而出现遗漏。

### 3.1 回滚方案生成引擎

```python
# rollback_generator.py - 智能回滚方案生成
import json
import re
from typing import Dict, List, Optional
from datetime import datetime
from dataclasses import dataclass

@dataclass
class RollbackPlan:
    plan_id: str
    change_id: str
    generated_at: str
    steps: List[Dict[str, str]]
    estimated_duration: str
    risk_notes: List[str]
    validation_commands: List[str]
    full_script: str

class RollbackGenerator:
    """基于 LLM 的智能回滚方案生成器"""
    
    def __init__(self, ollama_url: str = "http://localhost:11434"):
        self.ollama_url = ollama_url
        self.model = "qwen2.5:7b"
    
    def generate_rollback_plan(
        self, 
        change_id: str, 
        change_details: Dict,
        system_snapshot: Dict
    ) -> RollbackPlan:
        """生成回滚方案"""
        
        prompt = self._build_rollback_prompt(change_id, change_details, system_snapshot)
        llm_response = self._call_llm(prompt)
        
        plan = self._parse_rollback_plan(llm_response, change_id)
        return plan
    
    def _build_rollback_prompt(
        self, 
        change_id: str, 
        change_details: Dict,
        system_snapshot: Dict
    ) -> str:
        """构建回滚 prompt"""
        
        prompt = f"""你是一位资深运维工程师。请根据以下变更信息，生成详细的回滚方案。

## 变更信息
- 变更ID: {change_id}
- 变更类型: {change_details.get('type', 'unknown')}
- 变更内容: {change_details.get('description', 'N/A')}
- 受影响服务: {', '.join(change_details.get('services', []))}
- 执行时间: {change_details.get('executed_at', 'unknown')}

## 当前系统快照
{json.dumps(system_snapshot, indent=2, ensure_ascii=False)}

## 变更操作记录
{json.dumps(change_details.get('operations', []), indent=2, ensure_ascii=False)}

请按照以下 JSON 格式输出回滚方案：
{{
  "steps": [
    {{
      "order": 1,
      "action": "回滚动作描述",
      "command": "具体执行的命令",
      "expected_result": "期望的结果",
      "timeout_seconds": 30
    }}
  ],
  "estimated_duration": "预计回滚耗时",
  "risk_notes": ["回滚过程中的风险提示"],
  "validation_commands": ["回滚后的验证命令"],
  "full_script": "#!/bin/bash\n# 完整回滚脚本\n..."
}}
"""
        return prompt
    
    def _call_llm(self, prompt: str) -> str:
        """调用 Ollama"""
        try:
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json={"model": self.model, "prompt": prompt, "stream": False},
                timeout=120
            )
            return response.json().get("response", "")
        except Exception as e:
            return f"LLM调用失败: {e}"
    
    def _parse_rollback_plan(self, response: str, change_id: str) -> RollbackPlan:
        """解析回滚方案"""
        try:
            start = response.find('{')
            end = response.rfind('}')
            if start != -1 and end != -1:
                data = json.loads(response[start:end+1])
            else:
                # 生成默认回滚方案
                data = self._generate_fallback_plan(change_id)
            
            return RollbackPlan(
                plan_id=f"rollback-{change_id}",
                change_id=change_id,
                generated_at=datetime.now().isoformat(),
                steps=data.get("steps", []),
                estimated_duration=data.get("estimated_duration", "未知"),
                risk_notes=data.get("risk_notes", []),
                validation_commands=data.get("validation_commands", []),
                full_script=data.get("full_script", "# 请检查回滚方案")
            )
        except Exception as e:
            return RollbackPlan(
                plan_id=f"rollback-{change_id}",
                change_id=change_id,
                generated_at=datetime.now().isoformat(),
                steps=[{"order": 1, "action": "手动回滚", "command": "请手动执行回滚操作", "expected_result": "服务恢复", "timeout_seconds": 0}],
                estimated_duration="未知",
                risk_notes=["自动回滚方案生成失败，请手动执行"],
                validation_commands=["systemctl status nginx"],
                full_script="# 回滚方案生成失败，请手动执行"
            )
    
    def _generate_fallback_plan(self, change_id: str) -> Dict:
        """生成默认回滚方案"""
        return {
            "steps": [
                {
                    "order": 1,
                    "action": "恢复配置文件备份",
                    "command": "cp /backup/config/pre-change-* /etc/",
                    "expected_result": "配置文件恢复",
                    "timeout_seconds": 10
                },
                {
                    "order": 2,
                    "action": "重启受影响服务",
                    "command": "systemctl restart nginx",
                    "expected_result": "服务重启成功",
                    "timeout_seconds": 30
                },
                {
                    "order": 3,
                    "action": "验证服务状态",
                    "command": "curl -s -o /dev/null -w '%{http_code}' http://localhost/ && systemctl is-active nginx",
                    "expected_result": "HTTP 200, active",
                    "timeout_seconds": 10
                }
            ],
            "estimated_duration": "约2分钟",
            "risk_notes": ["这是默认回滚方案，请根据实际情况调整"],
            "validation_commands": ["systemctl is-active nginx", "curl -s http://localhost/ | head -5"],
            "full_script": "#!/bin/bash\nset -euo pipefail\n\necho '=== 开始回滚变更 {change_id} ==='\n\n# 1. 恢复配置\necho '步骤1: 恢复配置文件...'\ncp /backup/config/pre-change-*/etc/nginx/nginx.conf /etc/nginx/nginx.conf\n\n# 2. 重启服务\necho '步骤2: 重启Nginx...'\nsystemctl restart nginx\n\n# 3. 验证\necho '步骤3: 验证服务状态...'\nsleep 5\nhttp_code=$(curl -s -o /dev/null -w '%{http_code}' http://localhost/)\nif [ \"$http_code\" = \"200\" ]; then\n    echo \"回滚成功! HTTP状态: $http_code\"\nelse\n    echo \"回滚可能存在问题，HTTP状态: $http_code\"\nfi\n\necho '=== 回滚完成 ==='"
        }
```

### 3.2 快照机制

为了确保回滚可行，系统需要在变更前自动创建系统快照：

```python
# snapshot_manager.py - 变更快照管理
import subprocess
import shutil
import os
from datetime import datetime
from pathlib import Path

class SnapshotManager:
    """管理变更前的系统快照"""
    
    SNAPSHOT_DIR = "/var/lib/change-mgmt/snapshots"
    
    def __init__(self):
        os.makedirs(self.SNAPSHOT_DIR, exist_ok=True)
    
    def create_snapshot(self, change_id: str) -> Dict:
        """创建变更快照"""
        snapshot_time = datetime.now().strftime("%Y%m%d_%H%M%S")
        snapshot_path = f"{self.SNAPSHOT_DIR}/{change_id}_{snapshot_time}"
        os.makedirs(snapshot_path, exist_ok=True)
        
        snapshot_data = {
            "change_id": change_id,
            "created_at": datetime.now().isoformat(),
            "path": snapshot_path,
            "files_backed_up": [],
            "configs_exported": {},
            "services_stopped": [],
        }
        
        # 备份关键配置文件
        config_paths = [
            "/etc/nginx/nginx.conf",
            "/etc/nginx/conf.d/",
            "/etc/postgresql/",
            "/etc/mysql/",
            "/etc/docker/daemon.json",
            "/etc/sysctl.conf",
            "/etc/crontab",
        ]
        
        for cfg in config_paths:
            if os.path.exists(cfg):
                dest = f"{snapshot_path}/{cfg.replace('/', '_')}"
                if os.path.isdir(cfg):
                    shutil.copytree(cfg, dest)
                else:
                    shutil.copy2(cfg, dest)
                snapshot_data["files_backed_up"].append(cfg)
        
        # 导出当前服务状态
        snapshot_data["configs_exported"]["docker_ps"] = subprocess.getoutput("docker ps -a --format '{{.Names}}|{{.Status}}'")
        snapshot_data["configs_exported"]["systemd_services"] = subprocess.getoutput("systemctl list-units --type=service --state=running | head -50")
        snapshot_data["configs_exported"]["crontab"] = subprocess.getoutput("crontab -l 2>/dev/null || echo 'no crontab'")
        snapshot_data["configs_exported"]["mounts"] = subprocess.getoutput("df -h")
        
        # 保存快照元数据
        with open(f"{snapshot_path}/snapshot.json", "w") as f:
            json.dump(snapshot_data, f, indent=2, ensure_ascii=False)
        
        return snapshot_data
    
    def restore_snapshot(self, snapshot_path: str) -> Dict:
        """从快照恢复"""
        result = {"restored_files": [], "actions": []}
        
        snapshot_data = json.load(open(f"{snapshot_path}/snapshot.json"))
        
        # 恢复配置文件
        for config_file in snapshot_data.get("files_backed_up", []):
            src = f"{snapshot_path}/{config_file.replace('/', '_')}"
            if os.path.exists(src):
                dest_dir = os.path.dirname(config_file)
                os.makedirs(dest_dir, exist_ok=True)
                shutil.copy2(src, config_file)
                result["restored_files"].append(config_file)
                result["actions"].append(f"恢复: {config_file}")
        
        # 记录恢复结果
        with open(f"{snapshot_path}/restore-log.json", "w") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        return result
```

---

## 四、发布后健康验证引擎

变更执行后，需要自动验证变更是否成功。健康验证引擎负责：

1. **服务可达性检查**：确认关键端口和服务可用
2. **指标对比**：对比变更前后的关键指标
3. **错误率监控**：监测变更后的错误率变化
4. **自动判定**：综合多项指标，判定变更是否成功

```python
# health_validator.py - 发布后健康验证
import subprocess
import json
import time
from typing import Dict, List, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta

@dataclass
class HealthCheckResult:
    check_name: str
    passed: bool
    value: str
    threshold: str
    before: Optional[float] = None
    after: Optional[float] = None

class HealthValidator:
    """发布后健康验证引擎"""
    
    def __init__(self, ollama_url: str = "http://localhost:11434"):
        self.ollama_url = ollama_url
        self.model = "qwen2.5:7b"
    
    def validate_deployment(
        self, 
        change_id: str, 
        target_services: List[str],
        baseline_metrics: Dict,
        monitoring_window: int = 300  # 5分钟监控窗口
    ) -> Dict:
        """执行发布后健康验证"""
        
        results = {
            "change_id": change_id,
            "validated_at": datetime.now().isoformat(),
            "checks": [],
            "overall_status": "pending",
            "llm_analysis": "",
            "recommendation": "",
        }
        
        # 1. 即时健康检查
        immediate_checks = self._immediate_checks(target_services)
        results["checks"].extend(immediate_checks)
        
        # 2. 持续监控（等待监控窗口）
        time.sleep(min(monitoring_window, 60))  # 最多等60秒用于演示
        continued_checks = self._continued_monitoring(target_services, baseline_metrics)
        results["checks"].extend(continued_checks)
        
        # 3. LLM 综合分析
        llm_analysis = self._llm_health_analysis(results["checks"], baseline_metrics, target_services)
        results["llm_analysis"] = llm_analysis
        
        # 4. 综合判定
        passed_count = sum(1 for c in results["checks"] if c.passed)
        total_count = len(results["checks"])
        pass_rate = passed_count / total_count if total_count > 0 else 0
        
        if pass_rate >= 0.9:
            results["overall_status"] = "success"
            results["recommendation"] = "变更成功，服务运行正常"
        elif pass_rate >= 0.7:
            results["overall_status"] = "warning"
            results["recommendation"] = "部分检查未通过，建议人工复核"
        else:
            results["overall_status"] = "failure"
            results["recommendation"] = "多项检查未通过，建议立即回滚"
        
        return results
    
    def _immediate_checks(self, services: List[str]) -> List[HealthCheckResult]:
        """即时健康检查"""
        checks = []
        
        # 服务进程检查
        for svc in services:
            if svc == "nginx":
                active = subprocess.getoutput("systemctl is-active nginx")
                checks.append(HealthCheckResult(
                    check_name=f"nginx服务状态",
                    passed=active == "active",
                    value=active,
                    threshold="active"
                ))
                
                # HTTP 响应检查
                try:
                    http_code = subprocess.getoutput(
                        "curl -s -o /dev/null -w '%{http_code}' http://localhost/"
                    )
                    checks.append(HealthCheckResult(
                        check_name="Nginx HTTP响应",
                        passed=http_code == "200",
                        value=http_code,
                        threshold="200"
                    ))
                except:
                    checks.append(HealthCheckResult(
                        check_name="Nginx HTTP响应",
                        passed=False,
                        value="连接失败",
                        threshold="200"
                    ))
        
        # 端口监听检查
        ports_output = subprocess.getoutput("ss -tlnp | grep LISTEN")
        for line in ports_output.split("\n"):
            if "80" in line or "443" in line:
                checks.append(HealthCheckResult(
                    check_name=f"端口监听 ({line.split(':')[1].strip()})",
                    passed=True,
                    value="listening",
                    threshold="listening"
                ))
        
        return checks
    
    def _continued_monitoring(
        self, 
        services: List[str], 
        baseline: Dict
    ) -> List[HealthCheckResult]:
        """持续监控（对比基线）"""
        checks = []
        
        # 当前资源使用
        current_cpu = self._get_cpu_usage()
        current_mem = self._get_memory_usage()
        current_disk = self._get_disk_usage()
        
        baseline_cpu = baseline.get("cpu", 50)
        baseline_mem = baseline.get("memory", 60)
        baseline_disk = baseline.get("disk", 70)
        
        checks.append(HealthCheckResult(
            check_name="CPU使用率",
            passed=current_cpu < baseline_cpu * 1.5,
            value=f"{current_cpu}%",
            threshold=f"<{baseline_cpu * 1.5}%"
        ))
        
        checks.append(HealthCheckResult(
            check_name="内存使用率",
            passed=current_mem < baseline_mem * 1.3,
            value=f"{current_mem}%",
            threshold=f"<{baseline_mem * 1.3}%"
        ))
        
        checks.append(HealthCheckResult(
            check_name="磁盘使用率",
            passed=current_disk < 85,
            value=f"{current_disk}%",
            threshold="<85%"
        ))
        
        # Docker 容器健康
        unhealthy = subprocess.getoutput(
            "docker ps --filter 'health=unhealthy' --format '{{.Names}}'"
        )
        checks.append(HealthCheckResult(
            check_name="Docker容器健康",
            passed=not unhealthy.strip(),
            value=unhealthy.strip() or "全部健康",
            threshold="无不健康容器"
        ))
        
        return checks
    
    def _llm_health_analysis(
        self, 
        checks: List[HealthCheckResult], 
        baseline: Dict,
        services: List[str]
    ) -> str:
        """LLM 综合分析健康检查结果"""
        
        checks_summary = json.dumps([
            {"name": c.check_name, "passed": c.passed, "value": c.value}
            for c in checks
        ], indent=2, ensure_ascii=False)
        
        prompt = f"""你是一位运维专家。请分析以下部署后的健康检查结果，给出专业判断。

## 健康检查项
{checks_summary}

## 当前服务
{', '.join(services)}

## 基线指标
- CPU基线: {baseline.get('cpu', 'N/A')}%
- 内存基线: {baseline.get('memory', 'N/A')}%
- 磁盘基线: {baseline.get('disk', 'N/A')}%

请简要分析：
1. 变更是否成功？
2. 有哪些异常需要关注？
3. 下一步建议是什么？

用3-5句话回答，直接给出分析结果。
"""
        
        try:
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json={"model": self.model, "prompt": prompt, "stream": False},
                timeout=60
            )
            return response.json().get("response", "分析失败")
        except:
            return "LLM分析不可用"
    
    def _get_cpu_usage(self) -> float:
        try:
            output = subprocess.getoutput("top -bn1 | grep 'Cpu(s)'")
            match = re.search(r'(\d+\.?\d*)\s*id', output)
            if match:
                return round(100 - float(match.group(1)), 1)
        except:
            pass
        return 0.0
    
    def _get_memory_usage(self) -> float:
        try:
            output = subprocess.getoutput("free | awk '/^Mem:/ {printf \"%.1f\", $3/$2 * 100}'")
            return float(output)
        except:
            return 0.0
    
    def _get_disk_usage(self) -> float:
        try:
            output = subprocess.getoutput("df -h / | awk 'NR==2{printf \"%.1f\", $5}'")
            return float(output.replace('%', ''))
        except:
            return 0.0
```

---

## 五、变更日志智能关联

变更管理需要一个完整的审计追踪。智能日志关联引擎将分散的信息统一起来：

```python
# change_logger.py - 变更日志智能关联
import subprocess
import json
import re
from datetime import datetime, timedelta
from typing import Dict, List
from pathlib import Path

class ChangeLogger:
    """变更日志智能关联引擎"""
    
    def __init__(self, db_path: str = "/var/lib/change-mgmt/changes.db"):
        self.db_path = db_path
        self.log_dir = Path("/var/lib/change-mgmt/logs")
        self.log_dir.mkdir(parents=True, exist_ok=True)
    
    def log_change(
        self, 
        change_id: str,
        change_type: str,
        description: str,
        executor: str,
        risk_assessment: Dict,
        rollback_plan: Dict,
        health_check: Dict,
    ) -> Dict:
        """记录完整变更日志"""
        
        log_entry = {
            "change_id": change_id,
            "type": change_type,
            "description": description,
            "executor": executor,
            "created_at": datetime.now().isoformat(),
            "risk_assessment": risk_assessment,
            "rollback_plan": rollback_plan,
            "health_check": health_check,
            "status": "completed",
            "timeline": [
                {
                    "time": datetime.now().isoformat(),
                    "event": "变更完成",
                    "details": "变更已执行并通过健康验证"
                }
            ]
        }
        
        # 关联 git 提交
        git_related = self._find_related_git_commits(change_id, description)
        if git_related:
            log_entry["related_commits"] = git_related
        
        # 关联监控告警
        alert_related = self._find_related_alerts(change_id)
        if alert_related:
            log_entry["related_alerts"] = alert_related
        
        # 保存日志
        log_file = self.log_dir / f"{change_id}.json"
        with open(log_file, "w") as f:
            json.dump(log_entry, f, indent=2, ensure_ascii=False)
        
        return log_entry
    
    def _find_related_git_commits(self, change_id: str, description: str) -> List[Dict]:
        """查找相关的 git 提交"""
        commits = []
        
        # 搜索近期提交
        git_log = subprocess.getoutput(
            "cd /etc/services && git log --since='7 days ago' "
            "--pretty=format:'%H|%an|%ad|%s' --date=short"
        )
        
        for line in git_log.split("\n"):
            if not line:
                continue
            parts = line.split("|")
            if len(parts) >= 4:
                commit_hash, author, date, message = parts[0], parts[1], parts[2], "|".join(parts[3:])
                
                # 检查是否与变更描述相关
                if any(word in message.lower() for word in description.lower().split()[:3]):
                    commits.append({
                        "hash": commit_hash,
                        "author": author,
                        "date": date,
                        "message": message,
                    })
        
        return commits[:5]
    
    def _find_related_alerts(self, change_id: str) -> List[Dict]:
        """查找相关的监控告警"""
        alerts = []
        
        # 查询 Prometheus 告警
        since = (datetime.now() - timedelta(hours=24)).timestamp()
        try:
            result = subprocess.getoutput(
                f"curl -s 'http://localhost:9090/api/v1/query?query=up&start={since}'"
            )
            data = json.loads(result)
            for item in data.get("data", {}).get("result", []):
                alerts.append({
                    "metric": item.get("metric", {}),
                    "value": item.get("value", []),
                })
        except:
            pass
        
        return alerts[:5]
    
    def generate_report(self, change_id: str) -> str:
        """生成变更报告"""
        log_file = self.log_dir / f"{change_id}.json"
        if not log_file.exists():
            return f"未找到变更日志: {change_id}"
        
        log = json.load(open(log_file))
        
        report = f"""
## 变更报告: {log['change_id']}

| 项目 | 内容 |
|------|------|
| 变更类型 | {log['type']} |
| 执行人 | {log['executor']} |
| 执行时间 | {log['created_at']} |
| 状态 | {log['status']} |

### 变更描述
{log['description']}

### 风险评估
- 风险等级: {log.get('risk_assessment', {}).get('risk_level', '未知')}
- 风险评分: {log.get('risk_assessment', {}).get('risk_score', 'N/A')}/100
- 需要回滚: {'是' if log.get('rollback_plan', {}).get('rollback_needed', True) else '否'}
- 需要审批: {'是' if log.get('risk_assessment', {}).get('approval_required', False) else '否'}

### 健康验证
- 验证状态: {log.get('health_check', {}).get('overall_status', '未知')}
- 建议: {log.get('health_check', {}).get('recommendation', 'N/A')}

### LLM 分析
{log.get('health_check', {}).get('llm_analysis', 'N/A')}

### 关联 Git 提交
{json.dumps(log.get('related_commits', []), indent=2, ensure_ascii=False)}

### 关联监控告警
{json.dumps(log.get('related_alerts', []), indent=2, ensure_ascii=False)}
"""
        return report
```

---

## 六、安全门禁与审批流程

对于高风险变更，系统需要自动触发安全门禁：

```python
# security_gateway.py - 安全门禁
import json
import smtplib
from email.mime.text import MIMEText
from typing import Dict, List
from datetime import datetime

class SecurityGateway:
    """变更安全门禁引擎"""
    
    def __init__(self, config: Dict = None):
        self.config = config or {
            "high_risk_threshold": 70,
            "critical_risk_threshold": 85,
            "notification_channels": ["email", "slack"],
            "approval_required_roles": ["senior-engineer", "ops-manager"],
        }
    
    def check_gateway(self, risk_assessment: Dict, change_details: Dict) -> Dict:
        """执行安全门禁检查"""
        
        gates = {
            "risk_score_gate": self._check_risk_score(risk_assessment),
            "alert_gate": self._check_active_alerts(change_details),
            "resource_gate": self._check_resource_safety(change_details),
            "time_window_gate": self._check_time_window(change_details),
            "approval_gate": self._check_approval_required(risk_assessment),
        }
        
        all_passed = all(g["passed"] for g in gates.values())
        blocked_gates = [name for name, g in gates.items() if not g["passed"]]
        
        result = {
            "timestamp": datetime.now().isoformat(),
            "all_passed": all_passed,
            "gates": gates,
            "blocked_gates": blocked_gates,
            "action": "allow" if all_passed else "block",
        }
        
        # 如果阻断，发送通知
        if not all_passed:
            self._send_notification(result, change_details)
        
        return result
    
    def _check_risk_score(self, risk_assessment: Dict) -> Dict:
        """检查风险评分"""
        score = risk_assessment.get("risk_score", 0)
        threshold = self.config.get("high_risk_threshold", 70)
        
        if score >= threshold:
            return {
                "passed": False,
                "reason": f"风险评分 {score} 超过阈值 {threshold}",
                "severity": "critical" if score >= self.config.get("critical_risk_threshold", 85) else "high"
            }
        return {"passed": True, "reason": "风险评分在安全范围内"}
    
    def _check_active_alerts(self, change_details: Dict) -> Dict:
        """检查是否有活跃告警"""
        alerts = change_details.get("active_alerts", [])
        critical_alerts = [a for a in alerts if a.get("severity") == "critical"]
        
        if critical_alerts:
            return {
                "passed": False,
                "reason": f"存在 {len(critical_alerts)} 条严重告警，禁止变更",
                "severity": "high"
            }
        return {"passed": True, "reason": "无严重活跃告警"}
    
    def _check_resource_safety(self, change_details: Dict) -> Dict:
        """检查资源安全"""
        resources = change_details.get("resource_usage", {})
        issues = []
        
        mem_usage = float(resources.get("memory", "0").replace("%", ""))
        if mem_usage > 85:
            issues.append(f"内存使用率 {mem_usage}% 过高")
        
        disk_usage = float(resources.get("disk", "0").replace("%", ""))
        if disk_usage > 90:
            issues.append(f"磁盘使用率 {disk_usage}% 过高")
        
        if issues:
            return {
                "passed": False,
                "reason": "; ".join(issues),
                "severity": "medium"
            }
        return {"passed": True, "reason": "资源使用在安全范围内"}
    
    def _check_time_window(self, change_details: Dict) -> Dict:
        """检查变更时间窗口"""
        exec_time = change_details.get("scheduled_time", "")
        if not exec_time:
            return {"passed": True, "reason": "未指定执行时间"}
        
        try:
            hour = int(exec_time.split(" ")[1].split(":")[0]) if " " in exec_time else 0
            # 业务高峰期禁止变更 (9:00-12:00, 14:00-18:00)
            peak_hours = list(range(9, 12)) + list(range(14, 18))
            if hour in peak_hours:
                return {
                    "passed": False,
                    "reason": f"变更时间 {exec_time} 处于业务高峰期",
                    "severity": "medium"
                }
        except:
            pass
        
        return {"passed": True, "reason": "变更时间在允许窗口内"}
    
    def _check_approval_required(self, risk_assessment: Dict) -> Dict:
        """检查是否需要审批"""
        if risk_assessment.get("approval_required", False):
            return {
                "passed": False,
                "reason": "高风险变更需要审批",
                "severity": "high"
            }
        return {"passed": True, "reason": "无需额外审批"}
    
    def _send_notification(self, result: Dict, change_details: Dict):
        """发送阻断通知"""
        blocked_gates = result.get("blocked_gates", [])
        
        message = f"""
🚨 变更安全门禁阻断通知

变更ID: {change_details.get('change_id', 'N/A')}
阻断原因: {', '.join(blocked_gates)}

详细信息:
{json.dumps(result.get('gates', {}), indent=2, ensure_ascii=False)}

请立即处理相关问题后重新提交变更。
"""
        
        # 发送邮件通知
        try:
            msg = MIMEText(message)
            msg["Subject"] = "🚨 变更安全门禁阻断"
            msg["From"] = "change-mgmt@selfvps.net"
            msg["To"] = "ops-team@selfvps.net"
            
            # smtp_server.send_message(msg)  # 实际使用时配置SMTP
        except Exception as e:
            print(f"通知发送失败: {e}")
```

---

## 七、完整变更工作流集成

将所有组件集成到一个完整的变更工作流中：

```python
# change_workflow.py - 完整变更工作流
import json
import asyncio
from typing import Dict, Optional
from dataclasses import dataclass
from enum import Enum

class ChangeStatus(Enum):
    PENDING = "待执行"
    RISK_ANALYSIS = "风险评估中"
    ROLLBACK_PREPARED = "回滚方案已生成"
    GATE_CHECKED = "安全门禁已通过"
    EXECUTING = "执行中"
    HEALTH_CHECKING = "健康验证中"
    COMPLETED = "已完成"
    ROLLED_BACK = "已回滚"
    BLOCKED = "已阻断"

@dataclass
class ChangeRequest:
    change_id: str
    type: str
    description: str
    executor: str
    target_services: List[str]
    scheduled_time: str
    config_diff: str  # 变更的具体配置差异

class ChangeWorkflow:
    """完整变更管理工作流"""
    
    def __init__(self):
        self.risk_analyzer = RiskAssessmentEngine()
        self.rollback_generator = RollbackGenerator()
        self.snapshot_manager = SnapshotManager()
        self.health_validator = HealthValidator()
        self.change_logger = ChangeLogger()
        self.security_gateway = SecurityGateway()
    
    async def execute_change(self, request: ChangeRequest) -> Dict:
        """执行完整的变更工作流"""
        
        workflow_result = {
            "change_id": request.change_id,
            "status": ChangeStatus.PENDING.value,
            "stages": [],
        }
        
        # 阶段1: 变更前快照
        print(f"[{request.change_id}] 阶段1: 创建变更前快照...")
        snapshot = self.snapshot_manager.create_snapshot(request.change_id)
        workflow_result["stages"].append({
            "stage": "snapshot",
            "status": "completed",
            "result": snapshot,
        })
        
        # 阶段2: 风险评估
        print(f"[{request.change_id}] 阶段2: 执行风险评估...")
        context = RiskDataCollector().collect_context(request.change_id)
        risk_assessment = self.risk_analyzer.assess_risk(
            context=context,
            change_description=request.description
        )
        workflow_result["stages"].append({
            "stage": "risk_assessment",
            "status": "completed",
            "result": {
                "risk_level": risk_assessment.risk_level.value,
                "risk_score": risk_assessment.risk_score,
                "risk_factors": risk_assessment.risk_factors,
                "recommendations": risk_assessment.recommendations,
            }
        })
        
        # 阶段3: 安全门禁检查
        print(f"[{request.change_id}] 阶段3: 安全门禁检查...")
        gate_result = self.security_gateway.check_gateway(
            risk_assessment=vars(risk_assessment),
            change_details={
                "change_id": request.change_id,
                "active_alerts": context.get("monitoring_alerts", []),
                "resource_usage": context.get("resource_usage", {}),
                "scheduled_time": request.scheduled_time,
            }
        )
        
        if not gate_result["all_passed"]:
            workflow_result["status"] = ChangeStatus.BLOCKED.value
            workflow_result["stages"].append({
                "stage": "security_gateway",
                "status": "blocked",
                "result": gate_result,
            })
            print(f"⛔ 变更被阻断: {gate_result['blocked_gates']}")
            return workflow_result
        
        workflow_result["stages"].append({
            "stage": "security_gateway",
            "status": "passed",
            "result": gate_result,
        })
        
        # 阶段4: 生成回滚方案
        print(f"[{request.change_id}] 阶段4: 生成回滚方案...")
        rollback_plan = self.rollback_generator.generate_rollback_plan(
            change_id=request.change_id,
            change_details={
                "type": request.type,
                "description": request.description,
                "services": request.target_services,
                "operations": [{"action": "apply_config", "diff": request.config_diff}],
            },
            system_snapshot=snapshot
        )
        workflow_result["stages"].append({
            "stage": "rollback_plan",
            "status": "completed",
            "result": {
                "steps_count": len(rollback_plan.steps),
                "estimated_duration": rollback_plan.estimated_duration,
                "risk_notes": rollback_plan.risk_notes,
            }
        })
        
        # 阶段5: 执行变更（模拟）
        print(f"[{request.change_id}] 阶段5: 执行变更...")
        # 实际环境中这里会执行真实的变更操作
        workflow_result["stages"].append({
            "stage": "execution",
            "status": "completed",
            "result": {"message": "变更操作已执行"}
        })
        
        # 阶段6: 健康验证
        print(f"[{request.change_id}] 阶段6: 执行健康验证...")
        baseline = context.get("resource_usage", {})
        health_result = self.health_validator.validate_deployment(
            change_id=request.change_id,
            target_services=request.target_services,
            baseline_metrics=baseline,
        )
        workflow_result["stages"].append({
            "stage": "health_check",
            "status": "completed",
            "result": {
                "overall_status": health_result["overall_status"],
                "recommendation": health_result["recommendation"],
                "llm_analysis": health_result["llm_analysis"],
            }
        })
        
        # 阶段7: 记录变更日志
        print(f"[{request.change_id}] 阶段7: 记录变更日志...")
        self.change_logger.log_change(
            change_id=request.change_id,
            change_type=request.type,
            description=request.description,
            executor=request.executor,
            risk_assessment={
                "risk_level": risk_assessment.risk_level.value,
                "risk_score": risk_assessment.risk_score,
            },
            rollback_plan={
                "rollback_needed": rollback_plan.rollback_needed,
                "steps_count": len(rollback_plan.steps),
            },
            health_check=health_result,
        )
        
        workflow_result["status"] = ChangeStatus.COMPLETED.value
        print(f"✅ 变更完成: {request.change_id}")
        
        return workflow_result
```

---

## 八、Web 控制台实现

一个简洁的 Web 控制台，用于提交变更请求和查看结果：

```python
# web_console.py - 变更管理 Web 控制台
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import asyncio

app = FastAPI(title="VPS 智能变更管理系统", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

workflow = ChangeWorkflow()

class ChangeRequestModel(BaseModel):
    change_id: str
    type: str
    description: str
    executor: str
    target_services: List[str]
    scheduled_time: str
    config_diff: str

@app.get("/")
async def root():
    return {
        "service": "VPS 智能变更管理系统",
        "version": "1.0.0",
        "endpoints": {
            "POST /api/v1/changes": "提交变更请求",
            "GET /api/v1/changes/{change_id}": "查询变更状态",
            "GET /api/v1/changes/{change_id}/report": "生成变更报告",
            "POST /api/v1/changes/{change_id}/rollback": "执行回滚",
        }
    }

@app.post("/api/v1/changes")
async def submit_change(request: ChangeRequestModel):
    """提交变更请求"""
    try:
        result = await workflow.execute_change(request)
        return {"status": "success", "change_id": request.change_id, "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/changes/{change_id}")
async def get_change_status(change_id: str):
    """查询变更状态"""
    log_file = Path(f"/var/lib/change-mgmt/logs/{change_id}.json")
    if not log_file.exists():
        raise HTTPException(status_code=404, detail="变更不存在")
    
    log = json.load(open(log_file))
    return log

@app.get("/api/v1/changes/{change_id}/report")
async def get_change_report(change_id: str):
    """生成变更报告"""
    logger = ChangeLogger()
    report = logger.generate_report(change_id)
    return {"change_id": change_id, "report": report}

@app.post("/api/v1/changes/{change_id}/rollback")
async def trigger_rollback(change_id: str):
    """触发回滚"""
    # 查找最近的快照
    snapshot_dir = Path("/var/lib/change-mgmt/snapshots")
    snapshots = list(snapshot_dir.glob(f"{change_id}_*"))
    
    if not snapshots:
        raise HTTPException(status_code=404, detail="未找到可回滚的快照")
    
    latest_snapshot = max(snapshots, key=lambda p: p.stat().st_mtime)
    manager = SnapshotManager()
    result = manager.restore_snapshot(str(latest_snapshot))
    
    return {
        "status": "rollback_initiated",
        "change_id": change_id,
        "snapshot": str(latest_snapshot),
        "result": result,
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
```

---

## 九、部署与配置

### 9.1 系统要求

- **CPU**: 2核以上（推荐4核）
- **内存**: 8GB以上（运行 7B 模型推荐 16GB）
- **磁盘**: 50GB以上（用于存储模型和快照）
- **操作系统**: Ubuntu 22.04+ / Debian 12+

### 9.2 安装步骤

```bash
# 1. 安装 Ollama
curl -fsSL https://ollama.com/install.sh | sh

# 2. 拉取模型
ollama pull qwen2.5:7b

# 3. 安装 Python 依赖
pip install fastapi uvicorn pillow requests python-dotenv

# 4. 创建数据目录
mkdir -p /var/lib/change-mgmt/{snapshots,logs}

# 5. 部署应用
cp change_workflow.py /opt/change-mgmt/
cp web_console.py /opt/change-mgmt/
cd /opt/change-mgmt

# 6. 使用 systemd 管理
cat > /etc/systemd/system/change-mgmt.service << 'EOF'
[Unit]
Description=VPS Intelligent Change Management System
After=network.target ollama.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/change-mgmt
ExecStart=/usr/bin/python3 web_console.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

systemctl enable change-mgmt
systemctl start change-mgmt

# 7. 验证服务
curl http://localhost:8080/
```

### 9.3 Nginx 反向代理配置

```nginx
server {
    listen 443 ssl;
    server_name change.selfvps.net;

    ssl_certificate /etc/letsencrypt/live/selfvps.net/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/selfvps.net/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## 十、实际使用示例

### 10.1 提交一次 Nginx 配置变更

```bash
# 通过 API 提交变更
curl -X POST http://localhost:8080/api/v1/changes \
  -H "Content-Type: application/json" \
  -d '{
    "change_id": "change-20260915-001",
    "type": "nginx_config_update",
    "description": "更新Nginx worker_processes参数并添加新的upstream配置",
    "executor": "zhangsan",
    "target_services": ["nginx"],
    "scheduled_time": "2026-09-16 02:00",
    "config_diff": "worker_processes 4;\nupstream backend { server 10.0.0.1:8080; }"
  }'
```

### 10.2 查看变更报告

```bash
curl http://localhost:8080/api/v1/changes/change-20260915-001/report
```

### 10.3 触发紧急回滚

```bash
curl -X POST http://localhost:8080/api/v1/changes/change-20260915-001/rollback
```

---

## 十一、最佳实践与建议

### 11.1 变更管理黄金法则

1. ** Always create a snapshot before changing ** - 变更前必须创建快照
2. ** Define clear rollback criteria ** - 明确定义回滚触发条件
3. ** Test in staging first ** - 先在测试环境验证
4. ** Execute during maintenance windows ** - 在维护窗口执行
5. ** Document everything ** - 完整记录变更过程

### 11.2 系统优化建议

| 优化方向 | 具体建议 |
|---------|---------|
| 模型选择 | 资源有限时用 qwen2.5:3b，资源充足用 qwen2.5:7b |
| 快照策略 | 每周全量快照 + 变更前增量快照 |
| 监控集成 | 对接 Prometheus + Alertmanager |
| 通知渠道 | 支持 Slack/飞书/钉钉/邮件 |
| 权限控制 | 基于 RBAC 的变更审批流程 |

### 11.3 与现有工具集成

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   GitLab/Gitea  │────▶│  变更管理系统    │────▶│   Slack/飞书    │
│   (代码仓库)     │     │  (本系统)        │     │   (通知)        │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                              │
                    ┌─────────▼─────────┐
                    │   Prometheus      │
                    │   (监控告警)       │
                    └───────────────────┘
```

---

## 结语

AI 驱动的变更管理系统将传统依赖经验的变更流程，转变为由 LLM 智能辅助的自动化流程。通过风险评估、回滚方案生成、健康验证和安全门禁四个核心能力，大幅降低 VPS 变更风险。

关键收益：
- **风险前置**：变更前识别潜在问题，而不是变更后补救
- **回滚自动化**：每次变更都有预先生成的回滚方案
- **健康可验证**：变更后立即自动验证，不再依赖人工检查
- **全程可追溯**：完整的变更日志和审计报告

当你管理越来越多 VPS 时，这套系统会从"可选工具"变成"必需品"。毕竟，谁也不想再在凌晨两点因为一个配置错误而手忙脚乱地回滚了，对吧？

---

**参考资源**：
- [Ollama 官方文档](https://ollama.com/docs)
- [FastAPI 文档](https://fastapi.tiangolo.com/)
- [Prometheus 监控指南](https://prometheus.io/docs/)
- [GitOps 实践](https://www.gitops.tech/)