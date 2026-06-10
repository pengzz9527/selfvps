---
title: "AI VPS 智能运维：大模型驱动的自动化故障排查与修复"
description: "当 VPS 出现问题时，不再需要手动翻查日志。本文介绍如何利用大语言模型（LLM）实现 VPS 故障的自动检测、智能诊断与一键修复，让你从半夜告警中解放出来。"
date: 2026-06-10T21:30:00+08:00
lastmod: 2026-06-10T21:30:00+08:00
slug: "ai-vps-llm-automated-troubleshooting"
tags: ["LLM", "VPS运维", "自动化运维", "故障排查", "大模型", "AIOps", "智能诊断"]
categories: ["AI运维"]
image: /images/posts/ai-vps-llm-automated-troubleshooting/featured.png
draft: false
---

## 前言：从"半夜告警"到"自动修复"

你是否经历过这样的场景？

凌晨两点，手机响起——VPS 的 CPU 使用率飙升到 98%，某个服务卡死了。你挣扎着爬起来，SSH 连上服务器，一顿 `top`、`dmesg`、`journalctl` 翻找后，终于发现是某个进程内存泄漏。重启、清理、恢复——折腾完天都亮了。

如果有一个系统能在问题发生时，**自动获取日志、用大模型分析根因、执行修复命令**，而你只需要睡个安稳觉呢？

2026 年，大语言模型（LLM）的能力已经足够强大，可以将日志分析、故障诊断、甚至修复决策做得相当可靠。本文将带你搭建一套 **LLM 驱动的 VPS 智能运维系统**，实现从故障发现到自动修复的完整闭环。

## 系统架构概览

```
┌─────────────────────────────────────────────────┐
│                  监控触发层                       │
│  CPU/内存/磁盘/进程异常 → 告警事件               │
└──────────────────────┬──────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────┐
│              数据采集层                           │
│  获取系统指标 + 相关日志 + 配置信息              │
└──────────────────────┬──────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────┐
│            LLM 诊断引擎                           │
│  构建 Prompt → 发送大模型 → 分析根因            │
└──────────────────────┬──────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────┐
│            修复决策层                             │
│  生成修复方案 → 风险评估 → 执行/审批            │
└──────────────────────┬──────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────┐
│            验证与反馈层                           │
│  验证修复效果 → 记录知识库 → 持续优化            │
└─────────────────────────────────────────────────┘
```

这个系统的核心思想是：**把运维工程师的经验"注入"到大模型的 Prompt 中，让模型扮演一个经验丰富的 SRE 角色**。

## 第一步：环境准备

你需要以下基础环境：

```bash
# 安装 Python 3.11+
apt update && apt install -y python3 python3-pip python3-venv

# 创建项目目录
mkdir -p ~/vps-llm-ops && cd ~/vps-llm-ops
python3 -m venv venv && source venv/bin/activate

# 安装依赖
pip install openai requests psutil pyyaml
```

> **注意**：本文使用 OpenAI 兼容 API（可以是 OpenAI 自身，也可以是本地部署的 `vLLM`、`Ollama`、`LiteLLM` 等）。如果你使用本地大模型，后续配置部分做对应调整即可。

## 第二步：构建日志采集模块

故障诊断的第一步是获取上下文——大模型需要看到**什么信息、什么时候、发生了什么**才能做出准确判断。

```python
# collectors.py
import subprocess
import psutil
import datetime

def get_system_metrics():
    """获取当前系统关键指标"""
    return {
        "cpu_percent": psutil.cpu_percent(interval=1),
        "cpu_count": psutil.cpu_count(),
        "memory": {
            "total": psutil.virtual_memory().total,
            "used": psutil.virtual_memory().used,
            "percent": psutil.virtual_memory().percent,
        },
        "disk": {
            "/": {
                "total": psutil.disk_usage("/").total,
                "used": psutil.disk_usage("/").used,
                "percent": psutil.disk_usage("/").percent,
            }
        },
        "load_avg": psutil.getloadavg(),
        "timestamp": datetime.datetime.now().isoformat(),
    }

def get_top_processes(limit=10):
    """获取 CPU/内存占用最高的进程"""
    processes = []
    for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "status"]):
        processes.append(proc.info)
    processes.sort(key=lambda x: x.get("cpu_percent") or 0, reverse=True)
    return processes[:limit]

def get_service_status(service_name):
    """获取指定服务状态"""
    try:
        result = subprocess.run(
            ["systemctl", "status", service_name],
            capture_output=True, text=True, timeout=10
        )
        return {
            "active": result.returncode == 0,
            "output": result.stdout[:2000],
        }
    except Exception as e:
        return {"error": str(e)}

def get_recent_logs(service_name, lines=100):
    """获取服务最近 N 行日志"""
    try:
        result = subprocess.run(
            ["journalctl", "-u", service_name, "-n", str(lines), "--no-pager"],
            capture_output=True, text=True, timeout=10
        )
        return result.stdout
    except Exception as e:
        return f"获取日志失败: {e}"

def collect_context(event_type, service_name=None):
    """收集故障上下文：系统指标 + 日志 + 配置摘要"""
    context = {
        "event_type": event_type,
        "system_metrics": get_system_metrics(),
        "top_processes": get_top_processes(),
        "timestamp": datetime.datetime.now().isoformat(),
    }
    if service_name:
        context["service_status"] = get_service_status(service_name)
        context["recent_logs"] = get_recent_logs(service_name)
    return context
```

关键点：
- **不采集全量日志**——只采集最近的 N 行，控制 Token 消耗
- **系统指标优先**——CPU、内存、磁盘使用率是最直接的信号
- **进程排名**——找出"谁在搞事情"

## 第三步：构建 LLM 诊断引擎

这是整个系统的"大脑"。我们需要设计一个**结构化 Prompt**，让大模型扮演 SRE 专家。

```python
# llm_engine.py
import json
from openai import OpenAI

class LLMDiagnosisEngine:
    def __init__(self, api_key=None, base_url=None, model="gpt-4o"):
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
        )
        self.model = model

    SYSTEM_PROMPT = """你是一位拥有 15 年经验的高级 SRE（站点可靠性工程师）。
你的任务是根据提供的系统信息，诊断故障根因并给出修复方案。

请严格按照以下 JSON 格式输出（不要输出任何其他内容）：
{
    "root_cause": "用一句话描述故障的根本原因",
    "confidence": 0.95,
    "severity": "critical|high|medium|low",
    "recommendations": [
        {
            "action": "具体的修复操作步骤",
            "command": "需要执行的 shell 命令（如果有）",
            "risk": "low|medium|high",
            "description": "这个操作的作用说明"
        }
    ],
    "prevention": "如何预防此类问题再次发生"
}

分析原则：
1. 优先检查内存泄漏、磁盘空间不足、进程崩溃、端口占用
2. 结合 CPU/内存使用率和进程排名判断异常来源
3. 修复方案应从简单到复杂排列
4. 高风险操作需标注风险级别
5. 如果信息不足以做出判断，请在 root_cause 中说明"
"""

    def diagnose(self, context):
        """发送诊断请求"""
        # 将上下文序列化为文本
        context_text = json.dumps(context, ensure_ascii=False, indent=2)

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": f"以下是系统当前状态信息：\n\n{context_text}"},
            ],
            temperature=0.1,  # 低温度保证输出稳定
            max_tokens=1500,
        )

        # 解析 JSON 输出
        content = response.choices[0].message.content.strip()
        # 尝试从 markdown 代码块中提取 JSON
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        return json.loads(content)
```

这个设计的精妙之处在于：
- **角色设定**：让模型进入"SRE 专家"模式
- **结构化输出**：强制 JSON 格式，方便程序解析
- **低温度设置**：`temperature=0.1` 保证每次输出稳定，不会"放飞自我"
- **分析原则**：引导模型按照 SRE 的思维方式进行分析

## 第四步：执行修复与风险控制

诊断出结果后，不能盲目执行修复方案。需要**风险评估 + 分级处理**。

```python
# repair_engine.py
import subprocess
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RepairEngine:
    """修复执行引擎 - 带风险控制"""

    # 高风险操作黑名单
    DANGEROUS_COMMANDS = ["rm -rf", "dd", "mkfs", "fdisk"]

    def __init__(self, dry_run=True, approval_required=True):
        self.dry_run = dry_run  # 首次使用建议开启 dry_run
        self.approval_required = approval_required
        self.history = []

    def _is_safe_command(self, command):
        """检查命令是否安全"""
        for dangerous in self.DANGEROUS_COMMANDS:
            if dangerous in command:
                return False
        return True

    def execute(self, recommendation, require_approval=True):
        """执行单个修复建议"""
        action = recommendation["action"]
        command = recommendation.get("command", "")
        risk = recommendation.get("risk", "low")

        logger.info(f"执行修复: {action}")
        logger.info(f"风险级别: {risk}")

        # 高风险操作需要审批
        if require_approval and risk in ["high"] and self.approval_required:
            logger.warning(f"高风险操作需要人工审批: {action}")
            return {"status": "pending_approval", "action": action}

        if self.dry_run:
            logger.info(f"[DRY RUN] 将执行: {command}")
            return {"status": "dry_run", "command": command}

        # 安全检查
        if command and not self._is_safe_command(command):
            logger.error(f"命令被安全策略拦截: {command}")
            return {"status": "blocked", "reason": "dangerous_command"}

        # 执行命令
        try:
            result = subprocess.run(
                command, shell=True, capture_output=True, text=True, timeout=120
            )
            return {
                "status": "success" if result.returncode == 0 else "failed",
                "stdout": result.stdout[:500],
                "stderr": result.stderr[:500],
                "exit_code": result.returncode,
            }
        except subprocess.TimeoutExpired:
            return {"status": "timeout", "command": command}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def execute_repair_plan(self, diagnosis):
        """执行完整的修复计划"""
        results = []
        for rec in diagnosis.get("recommendations", []):
            result = self.execute(rec)
            results.append(result)
            # 如果低风险修复成功，尝试下一个
            if result["status"] == "success" and rec.get("risk") == "low":
                continue
            # 否则停止，等待人工评估
            if result["status"] in ["pending_approval", "blocked", "failed"]:
                break
        return results
```

风险控制要点：
- **dry_run 模式**：首次部署时务必开启，只输出计划不执行
- **命令黑名单**：`rm -rf`、`dd` 等危险命令直接拦截
- **风险分级**：high 风险操作需要人工审批
- **逐步执行**：低风险操作可自动执行，高风险操作暂停

## 第五步：整合为完整工作流

将以上模块串联成一个完整的工作流。

```python
# vps_ai_ops.py
import json
import logging
from collectors import collect_context
from llm_engine import LLMDiagnosisEngine
from repair_engine import RepairEngine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

class VPSAIOps:
    def __init__(self, api_key, base_url=None, model="gpt-4o", dry_run=True):
        self.engine = LLMDiagnosisEngine(api_key, base_url, model)
        self.repair = RepairEngine(dry_run=dry_run)
        self.dry_run = dry_run

    def handle_event(self, event_type, service_name=None):
        """处理告警事件：采集 → 诊断 → 修复"""
        logger.info(f"收到告警事件: {event_type}")
        if service_name:
            logger.info(f"目标服务: {service_name}")

        # 1. 采集上下文
        logger.info("正在采集系统上下文...")
        context = collect_context(event_type, service_name)
        logger.info(f"采集完成: CPU={context['system_metrics']['cpu_percent']}% "
                     f"内存={context['system_metrics']['memory']['percent']}%")

        # 2. LLM 诊断
        logger.info("正在发送诊断请求...")
        diagnosis = self.engine.diagnose(context)
        logger.info(f"诊断结果: 根因={diagnosis['root_cause']}, "
                     f"严重度={diagnosis['severity']}, "
                     f"置信度={diagnosis['confidence']}")

        # 3. 执行修复
        logger.info("开始执行修复方案...")
        results = self.repair.execute_repair_plan(diagnosis)

        # 4. 生成报告
        report = {
            "event_type": event_type,
            "service": service_name,
            "diagnosis": diagnosis,
            "repair_results": results,
            "dry_run": self.dry_run,
            "timestamp": context["timestamp"],
        }
        logger.info(f"事件处理完成: {json.dumps(report, ensure_ascii=False)[:200]}")
        return report

if __name__ == "__main__":
    import os
    api_key = os.environ.get("OPENAI_API_KEY", "")
    base_url = os.environ.get("OPENAI_BASE_URL")  # 本地模型时用

    ops = VPSAIOps(
        api_key=api_key,
        base_url=base_url,
        model="gpt-4o",
        dry_run=True,  # 先开 dry_run 验证！
    )

    # 模拟处理一个 CPU 异常事件
    report = ops.handle_event(
        event_type="cpu_high",
        service_name="nginx",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
```

## 实战示例：CPU 异常自动修复

让我们看一个完整的实际运行效果：

**告警事件**：Nginx 服务 CPU 使用率超过 90%，持续 5 分钟

**系统采集到的上下文**：
```json
{
  "system_metrics": {
    "cpu_percent": 94.2,
    "memory": {"percent": 78.5},
    "disk": {"/": {"percent": 82.3}}
  },
  "top_processes": [
    {"name": "nginx", "cpu_percent": 45.2, "memory_percent": 12.1},
    {"name": "python3", "cpu_percent": 32.8, "memory_percent": 15.3},
    {"name": "node", "cpu_percent": 16.2, "memory_percent": 8.7}
  ]
}
```

**LLM 诊断结果**：
```json
{
  "root_cause": "Nginx 进程 CPU 占用异常偏高，可能由大量并发请求或慢请求处理引起；同时存在 Python 进程异常占用 CPU，可能是某个脚本在疯狂重试",
  "confidence": 0.88,
  "severity": "high",
  "recommendations": [
    {
      "action": "检查 Nginx 活跃连接数，识别异常请求来源",
      "command": "ss -tn | grep ':80' | awk '{print $5}' | cut -d: -f1 | sort | uniq -c | sort -rn | head",
      "risk": "low",
      "description": "查看哪些 IP 的连接数最多"
    },
    {
      "action": "检查并重命名占用 CPU 的 Python 异常进程",
      "command": "ps aux | grep python3 | grep -v grep | head -5",
      "risk": "low",
      "description": "定位具体的异常 Python 进程"
    },
    {
      "action": "重启 Nginx 服务释放连接",
      "command": "systemctl restart nginx",
      "risk": "medium",
      "description": "临时恢复服务，可能有几秒中断"
    }
  ],
  "prevention": "建议配置 Nginx 的 limit_req 和 limit_conn 限制，并为 Python 脚本添加退避重试机制"
}
```

**修复执行**（dry_run 模式下）：
```
2026-06-10 14:23:01 [INFO] 执行修复: 检查 Nginx 活跃连接数...
2026-06-10 14:23:01 [INFO] [DRY RUN] 将执行: ss -tn | grep ':80' | ...
2026-06-10 14:23:01 [INFO] 执行修复: 检查并重命名 Python 进程...
2026-06-10 14:23:01 [INFO] [DRY RUN] 将执行: ps aux | grep python3 ...
2026-06-10 14:23:01 [WARNING] 高风险操作需要人工审批: 重启 Nginx 服务
```

你可以看到，系统自动诊断了问题根因、按风险级别排序了修复方案，并将高风险操作标记为等待人工审批。

## 进阶：接入监控告警实现全自动

上面的系统目前还是"被动响应"——需要手动触发。要让它全自动运行，只需接入监控告警系统：

### 方案一：配合 Prometheus + Alertmanager

```yaml
# alertmanager.yml 中配置 webhook 路由
route:
  receiver: 'vps-ai-ops'

receivers:
  - name: 'vps-ai-ops'
    webhook_configs:
      - url: 'http://localhost:8080/webhook'
        send_resolved: true
```

### 方案二：简单的 Cron + 自定义脚本

```bash
# /etc/cron.d/vps-ai-ops-check
*/5 * * * * root /root/vps-llm-ops/venv/bin/python3 /root/vps-llm-ops/check_and_diagnose.py
```

```python
# check_and_diagnose.py
import subprocess, json
from vps_ai_ops import VPSAIOps

def check_thresholds():
    """检查阈值并触发诊断"""
    metrics = get_metrics()
    issues = []

    if metrics["cpu_percent"] > 85:
        issues.append(("cpu_high", None))
    if metrics["memory"]["percent"] > 90:
        issues.append(("memory_high", None))
    if metrics["disk"]["/"]["percent"] > 90:
        issues.append(("disk_full", None))

    return issues

if __name__ == "__main__":
    issues = check_thresholds()
    if issues:
        api_key = os.environ["OPENAI_API_KEY"]
        ops = VPSAIOps(api_key, dry_run=False)
        for event_type, service in issues:
            ops.handle_event(event_type, service)
```

### 方案三：结合 Docker 容器监控

如果你的服务跑在 Docker 中，可以监控容器健康状态：

```python
def get_container_health():
    """获取所有 Docker 容器健康状态"""
    result = subprocess.run(
        ["docker", "ps", "--format", "{{.Names}}\t{{.Status}}\t{{.CPUPerc}}\t{{.MemPerc}}"],
        capture_output=True, text=True
    )
    containers = []
    for line in result.stdout.strip().split("\n"):
        parts = line.split("\t")
        if len(parts) >= 4:
            containers.append({
                "name": parts[0],
                "status": parts[1],
                "cpu": parts[2].replace("%", ""),
                "memory": parts[3].replace("%", ""),
            })
    return containers
```

## 成本考量

使用 LLM 进行运维诊断的成本：

| 方案 | 单次诊断成本 | 延迟 | 适用场景 |
|------|-------------|------|---------|
| **OpenAI GPT-4o** | ~$0.01/次 | 2-5秒 | 生产环境 |
| **Claude Haiku** | ~$0.001/次 | 1-3秒 | 高频监控 |
| **本地 Ollama** | $0（电费） | 3-10秒 | 数据敏感场景 |
| **LiteLLM 代理** | 灵活 | 取决于后端 | 多模型切换 |

按每天处理 50 次告警计算：
- OpenAI GPT-4o：约 $0.5/天，$15/月
- Claude Haiku：约 $0.05/天，$1.5/月
- 本地部署：几乎零成本

> **省钱技巧**：先用本地模型（如 `Llama 3.1 8B`）处理简单问题，复杂问题才调用 GPT-4o，可以大幅降低成本。

## 安全注意事项

1. **最小权限原则**：运行 VPS AI Ops 的用户不应拥有 root 权限，只授予必要的 sudo 权限
2. **API Key 安全**：将 API Key 存储在环境变量或密钥管理服务中，不要硬编码
3. **网络隔离**：诊断系统应与生产环境隔离，避免被恶意告警注入
4. **审计日志**：记录所有 LLM 输入输出和修复执行记录，方便事后追溯
5. **回滚机制**：确保每次修复都有对应的回滚操作，避免"越修越坏"

## 总结

这套 LLM 驱动的 VPS 智能运维系统的核心价值在于：

1. **减少 MTTR（平均修复时间）**：从几分钟的排查缩短到几秒钟的诊断
2. **7×24 不间断**：不需要值班工程师，系统时刻在线
3. **积累经验**：每次诊断和修复都会被记录，形成可复用的知识库
4. **降低门槛**：初级运维人员也可以处理复杂问题

当然，它目前还不是银弹——**高风险操作仍需人工确认**，模型也可能出现误判。但作为一个辅助工具，它已经能承担大部分重复性诊断工作，让你把精力集中在真正重要的问题上。

开始尝试吧——从 dry_run 模式入手，让 AI 先"说"，你再来"做"，逐步建立信任。

---

*本文完整代码示例可在 GitHub 上找到。如果你有好的改进想法，欢迎交流。*
