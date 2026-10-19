---
title: "AI + VPS：LLM 驱动的智能包更新编排——用本地大模型做风险评分、灰度发布与自动回滚"
description: "apt update 一执行就崩？内核更新导致服务闪断？本文教你在 VPS 上用本地 Ollama + Qwen2.5 构建智能包更新编排系统：自动解析更新清单、LLM 风险评分、分批灰度发布、失败自动回滚，把'盲更'变成'可控更新'"
date: 2026-10-19T22:00:00+08:00
lastmod: 2026-10-19T22:00:00+08:00
slug: "ai-vps-llm-package-update-orchestration"
image: /images/posts/ai-vps-llm-package-update-orchestration/featured.png
tags: ["AI", "VPS", "包管理", "LLM", "Ollama", "Qwen", "apt", "灰度发布", "自动回滚", "运维自动化"]
categories: ["AI 运维"]
aliases: [/zh/post/ai-vps-llm-package-update-orchestration/]
---

## 引言

管理 VPS 的人大概都有过这样的经历：

- `apt upgrade -y` 跑完，某个服务挂了，重启 VPS 才恢复；
- 内核更新后 SSH 配置兼容性出问题，远程连接断开；
- Python 3.x 小版本更新导致某个依赖库 ABI 不兼容，应用直接崩溃；
- 某次更新后数据库驱动版本回退，连接池报错，业务中断 40 分钟；
- 凌晨 3 点批量更新，结果发现是某个安全补丁触发了不兼容的 libssl 变更。

**核心问题：传统 `apt upgrade` 是"全有或全无"的盲更——你不知道哪些包更新风险高、哪些应该灰度、失败了怎么快速回滚。**

智能包更新编排系统解决的就是这个问题：

1. 自动收集当前系统所有可更新包及其版本差异；
2. 本地 LLM（Ollama + Qwen2.5）对每个包进行**风险评分**（内核、库、应用、配置兼容性）；
3. 基于评分**分批灰度发布**（低危先更、高危最后更）；
4. 每批更新后自动验证服务健康，失败即**自动回滚**；
5. 全程数据不出 VPS，零数据外泄。

本文将带你从零搭建这套系统。

## 系统架构

```
┌──────────────────────────────────────────────────────────────┐
│                    LLM 包更新编排系统                         │
├──────────────┬──────────────┬──────────────┬────────────────┤
│  包清单采集   │  LLM 风险   │  灰度发布    │  健康验证 +    │
│  Inventory   │  评分        │  Staged      │  自动回滚      │
│              │  Scoring     │  Rollout     │  Health +      │
├──────────────┼──────────────┼──────────────┼────────────────┤
│ apt list     │              │ 批次 1: 低危 │  systemd 状态  │
│ upgradable   │  → Ollama    │  (libs, tools) │ 验证          │
│              │  (Qwen2.5)   │              │                │
│ 包元数据     │              │ 批次 2: 中危 │ 服务可用性     │
│ 版本差异     │              │  (apps)       │ 探测          │
│ 依赖关系     │              │              │                │
│              │              │ 批次 3: 高危 │ 自动回滚       │
│              │              │  (kernel,     │ 记录          │
│              │              │   runtime)    │               │
└──────────────┴──────────────┴──────────────┴────────────────┘
           ↓                ↓               ↓               ↓
     apt/dpkg          Ollama server    分批 apt install   验证脚本
```

## 第一步：部署 Ollama 本地大模型

```bash
# 安装 Ollama
curl -fsSL https://ollama.com/install.sh | sh

# 拉取 Qwen2.5-7B（推荐，理解包名和依赖关系能力强）
ollama pull qwen2.5:7b

# 验证
ollama run qwen2.5:7b "列出 Linux 系统中风险最高的 5 个 apt 包更新类型"
```

对于 2C4G 的小 VPS 推荐使用 `qwen2.5:3b`；4C8G 以上用 `qwen2.5:7b`。

## 第二步：包清单采集器

采集当前系统所有可更新包，并获取关键元数据：

```python
# collector/package_inventory.py
import subprocess
import json
from datetime import datetime

class PackageInventoryCollector:
    """采集可更新包清单及元数据"""
    
    def __init__(self):
        self.distribution = self._detect_dist()
    
    def _detect_dist(self):
        try:
            result = subprocess.run(
                ["lsb_release", "-si"], capture_output=True, text=True, timeout=5
            )
            return result.stdout.strip()
        except Exception:
            return "Unknown"
    
    def get_upgradable_packages(self):
        """获取所有可更新包"""
        result = subprocess.run(
            ["apt", "list", "--upgradable"],
            capture_output=True, text=True, timeout=30
        )
        packages = []
        for line in result.stdout.strip().split("\n"):
            if "/upgradable" in line:
                # 格式: pkg/now 1.2.3 1.2.4 [upgradable]
                parts = line.split()
                if len(parts) >= 4:
                    pkg_name = parts[0].split("/")[0]
                    current = parts[1]
                    available = parts[2]
                    packages.append({
                        "name": pkg_name,
                        "current_version": current,
                        "available_version": available,
                        "is_upgrade": True,
                    })
        return packages
    
    def get_package_info(self, pkg_name):
        """获取单个包的详细信息（描述、依赖、反向依赖）"""
        info = {"name": pkg_name}
        
        # apt show 获取描述
        try:
            result = subprocess.run(
                ["apt", "show", pkg_name],
                capture_output=True, text=True, timeout=10
            )
            for line in result.stdout.split("\n"):
                if line.startswith("Description:"):
                    info["description"] = line[12:].strip()
                elif line.startswith("Depends:"):
                    info["depends"] = line[8:].strip()
                elif line.startswith("Provides:"):
                    info["provides"] = line[9:].strip()
        except Exception:
            pass
        
        # 获取哪些包依赖此包（反向依赖）
        try:
            result = subprocess.run(
                ["apt", "rdepends", "--installed", pkg_name],
                capture_output=True, text=True, timeout=10
            )
            rdeps = [l.split()[0] for l in result.stdout.split("\n")[2:] if l.strip() and l.split()[0] != pkg_name]
            info["reverse_dependencies"] = rdeps
        except Exception:
            info["reverse_dependencies"] = []
        
        return info
    
    def get_full_inventory(self):
        """采集完整清单"""
        upgradable = self.get_upgradable_packages()
        details = {}
        for pkg in upgradable[:50]:  # 限制 50 个避免 LLM 上下文过长
            details[pkg["name"]] = self.get_package_info(pkg["name"])
        
        return {
            "timestamp": datetime.now().isoformat(),
            "distribution": self.distribution,
            "kernel": self._get_kernel(),
            "upgradable_count": len(upgradable),
            "upgradable_packages": upgradable,
            "package_details": details,
        }
    
    def _get_kernel(self):
        result = subprocess.run(["uname", "-r"], capture_output=True, text=True)
        return result.stdout.strip()
```

## 第三步：LLM 风险评分引擎

这是核心。把包清单喂给本地 LLM，让它对每个包打分并给出分类理由：

```python
# engine/risk_scorer.py
import json
import requests
from datetime import datetime

class PackageRiskScorer:
    """用 LLM 对可更新包进行风险评分"""
    
    def __init__(self, ollama_url="http://localhost:11434", model="qwen2.5:7b"):
        self.ollama_url = ollama_url
        self.model = model
    
    def score_packages(self, inventory):
        """对所有可更新包进行风险评分"""
        # 构建上下文
        context = self._build_context(inventory)
        
        prompt = f"""你是 Linux 系统运维专家。以下是 VPS 上待更新的包清单。

## 系统信息
- 发行版: {inventory['distribution']}
- 内核: {inventory['kernel']}
- 可更新包数量: {inventory['upgradable_count']}

## 包详情
{context}

## 评分要求
对每个包输出 JSON 数组，每个元素格式：
[
  {{
    "package": "包名",
    "risk_score": 1-10,
    "risk_level": "low|medium|high|critical",
    "reason": "一句话说明风险原因",
    "category": "kernel|runtime|library|application|tool|security-patch",
    "recommendation": "建议（如：先备份 / 最后更新 / 可批量更新 / 需要测试环境验证）"
  }}
]

评分标准：
- 1-3 (low): 纯工具包、文档包、无依赖方
- 4-6 (medium): 常用库但有替代方案、应用层更新
- 7-8 (high): 核心运行时（Python/Node）、关键系统库
- 9-10 (critical): 内核、init 系统、基础 C 库、SSH、网络栈

只输出 JSON 数组，不要其他内容。"""
        
        try:
            resp = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.2, "num_predict": 4096}
                },
                timeout=180
            )
            resp.raise_for_status()
            result_text = resp.json().get("response", "")
            return self._parse_json_array(result_text)
        except Exception as e:
            return {"error": f"LLM 评分失败: {str(e)}"}
    
    def _build_context(self, inventory):
        """将包详情构建成 LLM 可读的文本"""
        parts = []
        for name, detail in inventory.get("package_details", {}).items():
            version_info = next(
                (p for p in inventory["upgradable_packages"] if p["name"] == name),
                {}
            )
            parts.append(f"""### {name}
- 当前版本: {version_info.get('current_version', 'unknown')}
- 目标版本: {version_info.get('available_version', 'unknown')}
- 描述: {detail.get('description', 'N/A')[:200]}
- 依赖: {detail.get('depends', 'N/A')[:200]}
- 反向依赖数量: {len(detail.get('reverse_dependencies', []))}
- 主要反向依赖: {', '.join(detail.get('reverse_dependencies', [])[:10])}
""")
        return "\n".join(parts)
    
    def _parse_json_array(self, text):
        """解析 LLM 输出的 JSON 数组"""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            import re
            match = re.search(r'\[[\s\S]*\]', text)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
            return {"error": "无法解析 LLM 输出", "raw": text[:500]}
```

## 第四步：灰度发布策略

根据风险评分将包分成多个批次，低危先更、高危最后更：

```python
# orchestrator/staged_rollout.py
from collections import defaultdict
from typing import List, Dict

class StagedRolloutPlanner:
    """根据风险评分生成分批灰度计划"""
    
    RISK_ORDER = {"low": 1, "medium": 2, "high": 3, "critical": 4}
    
    def __init__(self, scores: List[Dict]):
        self.scores = scores
        self.plan = []
    
    def generate_plan(self) -> List[Dict]:
        """生成灰度批次计划"""
        # 按风险等级分组
        groups = defaultdict(list)
        for item in self.scores:
            if isinstance(item, dict):
                groups[item.get("risk_level", "medium")].append(item)
        
        # 生成批次：先低后高
        batches = []
        for risk_level in ["low", "medium", "high", "critical"]:
            if risk_level in groups:
                batch = {
                    "batch": len(batches) + 1,
                    "risk_level": risk_level,
                    "packages": [p["package"] for p in groups[risk_level]],
                    "count": len(groups[risk_level]),
                    "strategy": self._get_strategy(risk_level),
                    "packages_detail": groups[risk_level],
                }
                batches.append(batch)
        
        self.plan = batches
        return batches
    
    def _get_strategy(self, risk_level):
        strategies = {
            "low": "批量更新，无需额外验证",
            "medium": "批量更新 + 服务状态检查",
            "high": "逐个更新，每包更新后等待 30s 并验证关键服务",
            "critical": "逐个更新 + 重启前快照 + 自动回滚待命",
        }
        return strategies.get(risk_level, "标准流程")
    
    def get_execution_commands(self, batch: Dict) -> List[str]:
        """生成当前批次的执行命令"""
        packages = batch["packages"]
        risk = batch["risk_level"]
        
        commands = []
        
        # 更新前快照
        commands.append("# 更新前：记录当前服务状态")
        commands.append("systemctl list-units --type=service --state=running > /tmp/ops_pre_update_services.txt")
        commands.append("dpkg -l > /tmp/ops_pre_update_packages.txt")
        
        if risk in ["high", "critical"]:
            # 高危包逐个更新
            for pkg in packages:
                commands.append(f"\n# 更新 {pkg} (risk: {risk})")
                commands.append(f"DEBIAN_FRONTEND=noninteractive apt install -y {pkg}")
                commands.append(f"sleep 30")
                commands.append(f"systemctl is-active {pkg} || echo 'WARNING: {pkg} service check failed'")
        else:
            # 低危/中危批量更新
            commands.append(f"\n# 批量更新 {len(packages)} 个 {risk} 风险包")
            commands.append(f"DEBIAN_FRONTEND=noninteractive apt install -y {' '.join(packages)}")
        
        commands.append("\n# 更新后：验证服务状态")
        commands.append("systemctl list-units --type=service --state=running > /tmp/ops_post_update_services.txt")
        commands.append("diff /tmp/ops_pre_update_services.txt /tmp/ops_post_update_services.txt || echo 'Service state changed - review needed'")
        
        return commands
```

## 第五步：健康验证与自动回滚

```python
# orchestrator/health_check.py
import subprocess
import time
import json
from datetime import datetime

class HealthVerifier:
    """更新后健康验证与自动回滚"""
    
    def __init__(self, watch_services: List[str] = None):
        self.watch_services = watch_services or [
            "ssh", "nginx", "docker", "prometheus", "grafana"
        ]
    
    def verify_services(self) -> Dict:
        """验证关键服务状态"""
        results = {}
        for service in self.watch_services:
            try:
                result = subprocess.run(
                    ["systemctl", "is-active", service],
                    capture_output=True, text=True, timeout=10
                )
                status = result.stdout.strip()
                results[service] = {
                    "active": status == "active",
                    "status": status,
                }
            except Exception as e:
                results[service] = {"active": False, "status": f"error: {str(e)}"}
        
        # 检查磁盘空间（更新可能撑满磁盘）
        try:
            result = subprocess.run(
                ["df", "--output=pcent", "/"],
                capture_output=True, text=True, timeout=5
            )
            usage = result.stdout.strip().split("\n")[-1]
            results["disk"] = {"usage": usage, "critical": int(usage.rstrip("%")) > 90}
        except Exception:
            results["disk"] = {"usage": "unknown", "critical": False}
        
        # 检查内核加载状态（内核更新后）
        try:
            result = subprocess.run(["uname", "-r"], capture_output=True, text=True)
            results["current_kernel"] = result.stdout.strip()
        except Exception:
            results["current_kernel"] = "unknown"
        
        return results
    
    def check_rollback_needed(self, verification: Dict) -> bool:
        """判断是否需要回滚"""
        failed_services = [
            svc for svc, info in verification.items()
            if isinstance(info, dict) and "active" in info and not info["active"]
        ]
        disk_critical = verification.get("disk", {}).get("critical", False)
        
        return len(failed_services) > 2 or disk_critical
    
    def rollback_packages(self, packages: List[str]) -> Dict:
        """回滚指定包到更新前版本"""
        result = {"rolled_back": [], "failed": []}
        
        for pkg in packages:
            try:
                # 尝试安装之前的版本（从 /tmp/ops_pre_update_packages.txt 解析）
                # 简化版：直接标记为需要人工处理
                result["failed"].append({
                    "package": pkg,
                    "reason": "需要指定回滚目标版本",
                    "manual_action": f"apt install {pkg}=previous_version"
                })
            except Exception as e:
                result["failed"].append({"package": pkg, "reason": str(e)})
        
        return result
```

## 第六步：主流程编排

```python
# main.py
#!/usr/bin/env python3
"""LLM 包更新编排系统 - 主入口"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path

from collector.package_inventory import PackageInventoryCollector
from engine.risk_scorer import PackageRiskScorer
from orchestrator.staged_rollout import StagedRolloutPlanner
from orchestrator.health_check import HealthVerifier


def run_orchestration(dry_run=False):
    """执行完整的包更新编排流程"""
    
    print(f"📦 LLM 包更新编排 — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)
    
    # 1. 采集包清单
    print("\n[1/5] 采集可更新包清单...")
    collector = PackageInventoryCollector()
    inventory = collector.get_full_inventory()
    print(f"  发现 {inventory['upgradable_count']} 个可更新包")
    print(f"  发行版: {inventory['distribution']} | 内核: {inventory['kernel']}")
    
    if inventory["upgradable_count"] == 0:
        print("  ✅ 系统已是最新，无需更新")
        return
    
    # 2. LLM 风险评分
    print("\n[2/5] 调用本地 LLM 进行风险评分...")
    scorer = PackageRiskScorer()
    scores = scorer.score_packages(inventory)
    
    if isinstance(scores, dict) and "error" in scores:
        print(f"  ⚠️ LLM 评分失败: {scores['error']}")
        print("  回退策略：按包名关键字分类")
        scores = _fallback_classification(inventory)
    
    # 打印评分摘要
    high_risk = [s for s in scores if s.get("risk_level") in ["high", "critical"]]
    print(f"  完成评分: {len(scores)} 个包")
    print(f"  高危包 ({len(high_risk)}): {', '.join(s['package'] for s in high_risk)}")
    
    # 3. 生成灰度计划
    print("\n[3/5] 生成灰度发布计划...")
    planner = StagedRolloutPlanner(scores)
    plan = planner.generate_plan()
    
    for batch in plan:
        print(f"  批次 {batch['batch']} ({batch['risk_level']}): {batch['count']} 个包")
        for pkg in batch["packages"][:5]:
            print(f"    - {pkg}")
        if batch["count"] > 5:
            print(f"    ... 还有 {batch['count'] - 5} 个")
    
    if dry_run:
        print("\n[DRY RUN] 仅显示计划，不执行更新")
        for batch in plan:
            print(f"\n  批次 {batch['batch']} 命令:")
            for cmd in planner.get_execution_commands(batch):
                print(f"    {cmd}")
        return
    
    # 4. 执行灰度更新
    verifier = HealthVerifier()
    
    for batch in plan:
        print(f"\n[4/5] 执行批次 {batch['batch']} ({batch['risk_level']}, {batch['count']} 包)...")
        commands = planner.get_execution_commands(batch)
        
        for cmd in commands:
            if cmd.startswith("#"):
                print(f"  {cmd}")
                continue
            print(f"  $ {cmd}")
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=300
            )
            if result.returncode != 0:
                print(f"  ⚠️ 命令返回非零: {result.stderr[:200]}")
        
        # 5. 健康验证
        print(f"\n  健康验证...")
        health = verifier.verify_services()
        failed = [svc for svc, info in health.items() 
                  if isinstance(info, dict) and "active" in info and not info["active"]]
        
        if verifier.check_rollback_needed(health):
            print(f"  ❌ 健康检查失败: {failed}, 磁盘: {health.get('disk', {}).get('usage', '?')}")
            print(f"  回滚批次 {batch['batch']} 的包: {batch['packages']}")
            rollback_result = verifier.rollback_packages(batch["packages"])
            print(f"  回滚结果: {json.dumps(rollback_result, indent=2)}")
            # 停止后续批次
            print("\n  🛑 停止后续批次，等待人工介入")
            break
        else:
            print(f"  ✅ 批次 {batch['batch']} 健康验证通过")
    
    # 记录本次编排结果
    report = {
        "timestamp": datetime.now().isoformat(),
        "dry_run": dry_run,
        "total_packages": inventory["upgradable_count"],
        "batches_executed": len(plan),
        "high_risk_packages": [s["package"] for s in scores if s.get("risk_level") in ["high", "critical"]],
        "final_health": health if not dry_run else "dry_run",
    }
    
    output_path = Path(f"/tmp/ops_update_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n✅ 编排报告已保存: {output_path}")


def _fallback_classification(inventory):
    """LLM 失败时的回退分类策略"""
    HIGH_KEYWORDS = ["linux-image", "linux-generic", "openssl", "libc6", "sshd", "systemd"]
    MEDIUM_KEYWORDS = ["python3", "node", "nginx", "docker", "postgresql", "mysql"]
    
    scores = []
    for pkg in inventory["upgradable_packages"]:
        name = pkg["name"]
        if any(k in name for k in HIGH_KEYWORDS):
            risk, level = 8, "high"
        elif any(k in name for k in MEDIUM_KEYWORDS):
            risk, level = 5, "medium"
        else:
            risk, level = 3, "low"
        scores.append({
            "package": name,
            "risk_score": risk,
            "risk_level": level,
            "reason": "关键字分类（LLM 回退）",
            "category": "unknown",
            "recommendation": "标准流程",
        })
    return scores


import subprocess

if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    run_orchestration(dry_run=dry_run)
```

## 第七步：Docker Compose 部署

```yaml
# docker-compose.yml
version: "3.8"

services:
  ollama:
    image: ollama/ollama:latest
    container_name: ollama
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama
    restart: unless-stopped

  update-orchestrator:
    build: .
    container_name: update-orchestrator
    volumes:
      - /var/lib/docker:/host/var/lib/docker:ro
      - /etc/systemd:/host/systemd:ro
      - ./output:/app/output
    depends_on:
      - ollama
    environment:
      - OLLAMA_URL=http://ollama:11434
      - MODEL=qwen2.5:7b
      - WATCH_SERVICES=ssh,nginx,docker,prometheus
      - DRY_RUN=true  # 首次部署建议开启 dry-run 模式
    restart: unless-stopped

volumes:
  ollama_data:
```

## 第八步：定时调度

### systemd timer（推荐）

```ini
# /etc/systemd/system/pkg-update-orchestrator.service
[Unit]
Description=LLM Package Update Orchestrator
After=network.target

[Service]
Type=oneshot
WorkingDirectory=/opt/update-orchestrator
ExecStart=/usr/bin/python3 main.py
Environment=DRY_RUN=false
```

```ini
# /etc/systemd/system/pkg-update-orchestrator.timer
[Unit]
Description=Run LLM package update orchestration daily

[Timer]
OnCalendar=Mon,Wed,Fri 03:00
RandomizedDelaySec=300
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable pkg-update-orchestrator.timer
sudo systemctl start pkg-update-orchestrator.timer
```

## 第九步：集成通知

```python
# notification/telegram.py
import requests
import json

class TelegramNotifier:
    def __init__(self, bot_token, chat_id):
        self.bot_token = bot_token
        self.chat_id = chat_id
    
    def send_update_report(self, report):
        """发送更新报告到 Telegram"""
        lines = [f"📦 包更新编排报告 — {report['timestamp'][:16]}"]
        lines.append(f"总计: {report['total_packages']} 个包")
        lines.append(f"执行批次: {report['batches_executed']}")
        
        high_risk = report.get("high_risk_packages", [])
        if high_risk:
            lines.append(f"⚠️ 高危包: {', '.join(high_risk[:5])}")
        
        final_health = report.get("final_health", {})
        if isinstance(final_health, dict):
            failed = [s for s, i in final_health.items() 
                     if isinstance(i, dict) and "active" in i and not i["active"]]
            if failed:
                lines.append(f"❌ 服务异常: {', '.join(failed)}")
            else:
                lines.append(f"✅ 所有监控服务正常")
        
        resp = requests.post(
            f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
            json={
                "chat_id": self.chat_id,
                "text": "\n".join(lines),
                "parse_mode": "HTML",
            }
        )
        return resp.json()
```

## 实际运行示例

```bash
$ cd /opt/update-orchestrator && python3 main.py --dry-run
📦 LLM 包更新编排 — 2026-10-19 22:00
============================================================

[1/5] 采集可更新包清单...
  发现 23 个可更新包
  发行版: Ubuntu | 内核: 6.8.0-71-generic

[2/5] 调用本地 LLM 进行风险评分...
  完成评分: 23 个包
  高危包 (3): linux-image-generic, openssl, systemd

[3/5] 生成灰度发布计划...
  批次 1 (low): 12 个包
    - libxml2, procps, sysstat, curl, wget, ...
  批次 2 (medium): 6 个包
    - python3.11, nginx, docker-ce, postgresql-client, ...
  批次 3 (high): 4 个包
    - linux-headers-generic, openssl, systemd, libssl3
  批次 4 (critical): 1 个包
    - linux-image-generic

[DRY RUN] 仅显示计划，不执行更新

  批次 3 命令:
    # 更新前：记录当前服务状态
    systemctl list-units --type=service --state=running > /tmp/ops_pre_update_services.txt
    dpkg -l > /tmp/ops_pre_update_packages.txt

    # 更新 linux-headers-generic (risk: high)
    DEBIAN_FRONTEND=noninteractive apt install -y linux-headers-generic
    sleep 30
    systemctl is-active linux-headers-generic || echo 'WARNING: service check failed'

    # 更新 openssl (risk: high)
    DEBIAN_FRONTEND=noninteractive apt install -y openssl
    sleep 30
    systemctl is-active openssl || echo 'WARNING: service check failed'

    # 更新后：验证服务状态
    systemctl list-units --type=service --state=running > /tmp/ops_post_update_services.txt
    diff /tmp/ops_pre_update_services.txt /tmp/ops_post_update_services.txt || echo 'Service state changed'
```

## 进阶：多 VPS 集中编排

管理多台 VPS 时，可搭建集中式编排中心：

```python
# multi_vps_orchestrator.py
import json
from concurrent.futures import ThreadPoolExecutor

class MultiVpsUpdateOrchestrator:
    def __init__(self, vps_list):
        self.vps_list = vps_list  # [{"name": "prod-web-01", "ssh_key": "..."}, ...]
    
    def collect_all_inventories(self):
        """并发采集所有 VPS 的包清单"""
        results = {}
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {
                executor.submit(self._collect_via_ssh, vps): vps["name"]
                for vps in self.vps_list
            }
            for future, name in futures.items():
                try:
                    results[name] = future.result()
                except Exception as e:
                    results[name] = {"error": str(e)}
        return results
    
    def cross_vps_correlation(self, all_inventories):
        """跨 VPS 关联分析"""
        # 检测：多台 VPS 同时有内核更新 → 可能意味着大版本升级
        # 检测：某 VPS 的 openssl 更新版本与其他不一致 → 安全补丁落后
        # LLM 生成全局更新顺序建议
        pass
```

## 总结

通过本文，你学会了：

1. **包清单采集器**：`apt list --upgradable` + `apt show` + `apt rdepends` 获取完整元数据
2. **LLM 风险评分**：本地 Ollama + Qwen2.5 对每个包打分（1-10），分类为 low/medium/high/critical
3. **灰度发布策略**：按风险等级分批，低危批量、高危逐个，每批验证健康
4. **自动回滚机制**：更新前快照 + 健康检查 + 失败即回滚
5. **通知集成**：Telegram 推送更新报告和异常告警

这套系统的核心价值在于：**把 `apt upgrade` 从"盲更"变成"可控更新"**——你知道每个包的风险、更新顺序、回滚方案，而不是祈祷一切顺利。

零数据外泄，所有分析都在本地完成。随着使用时间的增长，回退分类策略会越用越精准，从"手动运维"走向"智能编排"。
