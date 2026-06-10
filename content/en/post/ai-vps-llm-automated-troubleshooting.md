---
title: "AI-Powered VPS Operations: Automated Troubleshooting & Repair with LLMs"
description: "Stop manually digging through logs at 2 AM. This article shows how to use Large Language Models to automate VPS fault detection, intelligent diagnosis, and one-click repair—liberating you from midnight alert fatigue."
date: 2026-06-10T21:30:00+08:00
lastmod: 2026-06-10T21:30:00+08:00
slug: "ai-vps-llm-automated-troubleshooting"
tags: ["LLM", "VPS Operations", "AIOps", "Fault Diagnosis", "Large Language Model", "Automation", "Intelligent Diagnosis"]
categories: ["AI Operations"]
image: /images/posts/ai-vps-llm-automated-troubleshooting/featured.png
draft: false
---

## Introduction: From "Midnight Alerts" to "Automated Repair"

Have you experienced this scenario?

It's 2 AM, your phone buzzes — the VPS CPU usage has spiked to 98%, and a service has hung. You drag yourself out of bed, SSH into the server, spend ages flipping through `top`, `dmesg`, and `journalctl` before finally discovering a memory leak in a process. Restart, clean up, recover — by the time it's done, it's morning.

What if there was a system that could **automatically collect logs, use an LLM to diagnose the root cause, and execute repair commands** — while you slept soundly?

In 2026, Large Language Models (LLMs) have become powerful enough to handle log analysis, fault diagnosis, and even repair decisions with impressive reliability. This article walks you through building an **LLM-driven VPS intelligent operations system** that achieves a complete closed loop from fault detection to automatic repair.

## System Architecture Overview

```
┌─────────────────────────────────────────────────┐
│              Alert Triggering Layer              │
│  CPU/Memory/Disk/Process Anomalies → Events      │
└──────────────────────┬──────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────┐
│              Data Collection Layer               │
│  Collect system metrics + related logs + config  │
└──────────────────────┬──────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────┐
│            LLM Diagnosis Engine                   │
│  Build Prompt → Send to LLM → Analyze Root Cause │
└──────────────────────┬──────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────┐
│            Repair Decision Layer                  │
│  Generate Repair Plan → Risk Assessment → Execute │
└──────────────────────┬──────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────┐
│           Verification & Feedback Layer           │
│  Verify Repair Effect → Log Knowledge Base → Optimize │
└─────────────────────────────────────────────────┘
```

The core idea: **inject operations engineers' experience into the LLM's prompts**, letting the model play the role of a seasoned SRE.

## Step 1: Environment Setup

You need the following base environment:

```bash
# Install Python 3.11+
apt update && apt install -y python3 python3-pip python3-venv

# Create project directory
mkdir -p ~/vps-llm-ops && cd ~/vps-llm-ops
python3 -m venv venv && source venv/bin/activate

# Install dependencies
pip install openai requests psutil pyyaml
```

> **Note**: This article uses an OpenAI-compatible API (which could be OpenAI itself, or locally deployed `vLLM`, `Ollama`, `LiteLLM`, etc.). If you use a local model, adjust the configuration section accordingly.

## Step 2: Build the Log Collection Module

The first step of fault diagnosis is gathering context — the LLM needs to see **what happened, when, and under what conditions** to make accurate judgments.

```python
# collectors.py
import subprocess
import psutil
import datetime

def get_system_metrics():
    """Collect key system metrics"""
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
    """Get top processes by CPU/Memory usage"""
    processes = []
    for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "status"]):
        processes.append(proc.info)
    processes.sort(key=lambda x: x.get("cpu_percent") or 0, reverse=True)
    return processes[:limit]

def get_service_status(service_name):
    """Get specific service status"""
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
    """Get the last N lines of service logs"""
    try:
        result = subprocess.run(
            ["journalctl", "-u", service_name, "-n", str(lines), "--no-pager"],
            capture_output=True, text=True, timeout=10
        )
        return result.stdout
    except Exception as e:
        return f"Failed to get logs: {e}"

def collect_context(event_type, service_name=None):
    """Collect fault context: system metrics + logs + config summary"""
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

Key points:
- **Don't collect full logs** — only the last N lines to control token consumption
- **System metrics first** — CPU, memory, and disk usage are the most direct signals
- **Process ranking** — identify "who's causing the trouble"

## Step 3: Build the LLM Diagnosis Engine

This is the "brain" of the entire system. We need to design a **structured prompt** that makes the LLM play the role of an SRE expert.

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

    SYSTEM_PROMPT = """You are a Senior SRE (Site Reliability Engineer) with 15 years of experience.
Your task is to diagnose the root cause of a fault and provide a repair plan based on the system information provided.

Please output strictly in the following JSON format (do not output anything else):
{
    "root_cause": "A one-sentence description of the root cause",
    "confidence": 0.95,
    "severity": "critical|high|medium|low",
    "recommendations": [
        {
            "action": "Specific repair operation steps",
            "command": "Shell command to execute (if any)",
            "risk": "low|medium|high",
            "description": "Explanation of what this operation does"
        }
    ],
    "prevention": "How to prevent this type of issue from recurring"
}

Analysis principles:
1. Prioritize checking memory leaks, disk space exhaustion, process crashes, port conflicts
2. Use CPU/memory usage and process ranking to identify anomaly sources
3. Order repair plans from simple to complex
4. High-risk operations must be marked with their risk level
5. If information is insufficient to make a judgment, state so in root_cause"
"""

    def diagnose(self, context):
        """Send diagnosis request"""
        # Serialize context to text
        context_text = json.dumps(context, ensure_ascii=False, indent=2)

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": f"Here is the current system status information:\n\n{context_text}"},
            ],
            temperature=0.1,  # Low temperature ensures stable output
            max_tokens=1500,
        )

        # Parse JSON output
        content = response.choices[0].message.content.strip()
        # Try to extract JSON from markdown code blocks
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        return json.loads(content)
```

The brilliance of this design:
- **Role setting**: Puts the model in "SRE Expert" mode
- **Structured output**: Enforces JSON format for easy programmatic parsing
- **Low temperature**: `temperature=0.1` ensures stable output every time
- **Analysis principles**: Guides the model to think like an experienced SRE

## Step 4: Repair Execution & Risk Control

After diagnosis, you can't blindly execute repair plans. You need **risk assessment + tiered processing**.

```python
# repair_engine.py
import subprocess
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RepairEngine:
    """Repair execution engine with risk control"""

    # Dangerous command blacklist
    DANGEROUS_COMMANDS = ["rm -rf", "dd", "mkfs", "fdisk"]

    def __init__(self, dry_run=True, approval_required=True):
        self.dry_run = dry_run  # Start with dry_run enabled on first deployment
        self.approval_required = approval_required
        self.history = []

    def _is_safe_command(self, command):
        """Check if a command is safe"""
        for dangerous in self.DANGEROUS_COMMANDS:
            if dangerous in command:
                return False
        return True

    def execute(self, recommendation, require_approval=True):
        """Execute a single repair recommendation"""
        action = recommendation["action"]
        command = recommendation.get("command", "")
        risk = recommendation.get("risk", "low")

        logger.info(f"Executing repair: {action}")
        logger.info(f"Risk level: {risk}")

        # High-risk operations require approval
        if require_approval and risk in ["high"] and self.approval_required:
            logger.warning(f"High-risk operation needs manual approval: {action}")
            return {"status": "pending_approval", "action": action}

        if self.dry_run:
            logger.info(f"[DRY RUN] Would execute: {command}")
            return {"status": "dry_run", "command": command}

        # Security check
        if command and not self._is_safe_command(command):
            logger.error(f"Command blocked by security policy: {command}")
            return {"status": "blocked", "reason": "dangerous_command"}

        # Execute command
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
        """Execute a complete repair plan"""
        results = []
        for rec in diagnosis.get("recommendations", []):
            result = self.execute(rec)
            results.append(result)
            # If low-risk repair succeeded, try the next one
            if result["status"] == "success" and rec.get("risk") == "low":
                continue
            # Otherwise stop and wait for human evaluation
            if result["status"] in ["pending_approval", "blocked", "failed"]:
                break
        return results
```

Risk control highlights:
- **dry_run mode**: Must be enabled on first deployment — outputs the plan without executing
- **Command blacklist**: Dangerous commands like `rm -rf`, `dd` are directly blocked
- **Risk tiering**: High-risk operations require manual approval
- **Gradual execution**: Low-risk operations can execute automatically; high-risk operations pause

## Step 5: Integrate into a Complete Workflow

Connect all modules into a complete workflow.

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
        """Handle alert events: collect → diagnose → repair"""
        logger.info(f"Received alert event: {event_type}")
        if service_name:
            logger.info(f"Target service: {service_name}")

        # 1. Collect context
        logger.info("Collecting system context...")
        context = collect_context(event_type, service_name)
        logger.info(f"Collection complete: CPU={context['system_metrics']['cpu_percent']}% "
                     f"Memory={context['system_metrics']['memory']['percent']}%")

        # 2. LLM diagnosis
        logger.info("Sending diagnosis request...")
        diagnosis = self.engine.diagnose(context)
        logger.info(f"Diagnosis: Root cause={diagnosis['root_cause']}, "
                     f"Severity={diagnosis['severity']}, "
                     f"Confidence={diagnosis['confidence']}")

        # 3. Execute repair
        logger.info("Starting repair execution...")
        results = self.repair.execute_repair_plan(diagnosis)

        # 4. Generate report
        report = {
            "event_type": event_type,
            "service": service_name,
            "diagnosis": diagnosis,
            "repair_results": results,
            "dry_run": self.dry_run,
            "timestamp": context["timestamp"],
        }
        logger.info(f"Event processed: {json.dumps(report, ensure_ascii=False)[:200]}")
        return report

if __name__ == "__main__":
    import os
    api_key = os.environ.get("OPENAI_API_KEY", "")
    base_url = os.environ.get("OPENAI_BASE_URL")  # Use for local models

    ops = VPSAIOps(
        api_key=api_key,
        base_url=base_url,
        model="gpt-4o",
        dry_run=True,  # Start with dry_run enabled!
    )

    # Simulate handling a CPU anomaly event
    report = ops.handle_event(
        event_type="cpu_high",
        service_name="nginx",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
```

## Practical Example: Automatic CPU Anomaly Repair

Let's look at a complete real-world execution:

**Alert Event**: Nginx service CPU usage exceeded 90% for 5 consecutive minutes

**Collected context**:
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

**LLM Diagnosis Result**:
```json
{
  "root_cause": "Nginx processes have abnormally high CPU usage, possibly caused by excessive concurrent requests or slow request handling; a Python process is also consuming excessive CPU, likely a script repeatedly retrying",
  "confidence": 0.88,
  "severity": "high",
  "recommendations": [
    {
      "action": "Check Nginx active connections and identify anomalous request sources",
      "command": "ss -tn | grep ':80' | awk '{print $5}' | cut -d: -f1 | sort | uniq -c | sort -rn | head",
      "risk": "low",
      "description": "Check which IPs have the most connections"
    },
    {
      "action": "Inspect and address the anomalous Python process consuming CPU",
      "command": "ps aux | grep python3 | grep -v grep | head -5",
      "risk": "low",
      "description": "Locate the specific anomalous Python process"
    },
    {
      "action": "Restart Nginx service to release connections",
      "command": "systemctl restart nginx",
      "risk": "medium",
      "description": "Temporarily restore service; may have a few seconds of interruption"
    }
  ],
  "prevention": "Configure Nginx limit_req and limit_conn directives, and add exponential backoff retry mechanisms for Python scripts"
}
```

**Repair Execution** (in dry_run mode):
```
2026-06-10 14:23:01 [INFO] Executing repair: Check Nginx active connections...
2026-06-10 14:23:01 [INFO] [DRY RUN] Would execute: ss -tn | grep ':80' | ...
2026-06-10 14:23:01 [INFO] Executing repair: Inspect anomalous Python process...
2026-06-10 14:23:01 [INFO] [DRY RUN] Would execute: ps aux | grep python3 ...
2026-06-10 14:23:01 [WARNING] High-risk operation needs manual approval: Restart Nginx
```

You can see the system automatically diagnosed the root cause, ranked repair plans by risk level, and flagged high-risk operations for manual approval.

## Advanced: Integrating with Monitoring Alerts for Full Automation

The system above is currently "reactive" — it needs manual triggering. To make it fully automatic, simply integrate with a monitoring alerting system:

### Option 1: With Prometheus + Alertmanager

```yaml
# Configure webhook routing in alertmanager.yml
route:
  receiver: 'vps-ai-ops'

receivers:
  - name: 'vps-ai-ops'
    webhook_configs:
      - url: 'http://localhost:8080/webhook'
        send_resolved: true
```

### Option 2: Simple Cron + Custom Script

```bash
# /etc/cron.d/vps-ai-ops-check
*/5 * * * * root /root/vps-llm-ops/venv/bin/python3 /root/vps-llm-ops/check_and_diagnose.py
```

```python
# check_and_diagnose.py
import os
from vps_ai_ops import VPSAIOps

def check_thresholds():
    """Check thresholds and trigger diagnosis"""
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

### Option 3: Docker Container Monitoring

If your services run in Docker, you can monitor container health:

```python
def get_container_health():
    """Get health status of all Docker containers"""
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

## Cost Considerations

Cost of using LLM for operations diagnosis:

| Solution | Cost per Diagnosis | Latency | Use Case |
|----------|-------------------|---------|----------|
| **OpenAI GPT-4o** | ~$0.01/invocation | 2-5 sec | Production |
| **Claude Haiku** | ~$0.001/invocation | 1-3 sec | High-frequency monitoring |
| **Local Ollama** | $0 (electricity only) | 3-10 sec | Data-sensitive scenarios |
| **LiteLLM Proxy** | Flexible | Depends on backend | Multi-model switching |

At 50 alerts per day:
- OpenAI GPT-4o: ~$0.5/day, $15/month
- Claude Haiku: ~$0.05/day, $1.5/month
- Local deployment: Almost zero cost

> **Money-saving tip**: Start with a local model (like `Llama 3.1 8B`) for simple issues, and escalate to GPT-4o only for complex problems — this can dramatically reduce costs.

## Security Considerations

1. **Principle of least privilege**: The user running VPS AI Ops should not have root access — grant only necessary sudo permissions
2. **API Key security**: Store API keys in environment variables or a secrets manager, never hardcode
3. **Network isolation**: The diagnosis system should be isolated from production to prevent malicious alert injection
4. **Audit logging**: Record all LLM inputs/outputs and repair execution records for post-incident review
5. **Rollback mechanism**: Ensure every repair has a corresponding rollback operation to avoid "making it worse"

## Summary

The core value of this LLM-driven VPS intelligent operations system lies in:

1. **Reduced MTTR (Mean Time To Repair)**: Shrink troubleshooting from minutes to seconds
2. **24/7 availability**: No need for on-call engineers — the system is always on
3. **Experience accumulation**: Every diagnosis and repair is recorded, forming a reusable knowledge base
4. **Lowered barrier**: Junior operations staff can handle complex issues with AI assistance

Of course, it's not a silver bullet — **high-risk operations still require human confirmation**, and models can make mistakes. But as an auxiliary tool, it can already handle the bulk of repetitive diagnostic work, freeing you to focus on what truly matters.

Get started — begin with dry_run mode, let the AI "talk" first and you "act" later, and gradually build trust.

---

*Full code examples for this article are available on GitHub. Feel free to reach out if you have improvement ideas.*
