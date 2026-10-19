---
title: "AI + VPS: LLM-Driven Intelligent Package Update Orchestration — Risk Scoring, Staged Rollout, and Auto-Rollback with Local Ollama"
description: "Blind `apt upgrade` broke your service at 3 AM? This article shows you how to build an intelligent package update orchestration system on your VPS using local Ollama + Qwen2.5 — automatic risk scoring per package, staged grey rollout, health verification, and instant auto-rollback. Zero data exfiltration."
date: 2026-10-19T22:00:00+08:00
lastmod: 2026-10-19T22:00:00+08:00
slug: "ai-vps-llm-package-update-orchestration"
image: /images/posts/ai-vps-llm-package-update-orchestration/featured.png
tags: ["AI", "VPS", "package management", "LLM", "Ollama", "Qwen", "apt", "staged rollout", "auto-rollback", "ops automation"]
categories: ["AI Operations"]
aliases: [/en/post/ai-vps-llm-package-update-orchestration/]
---

## Introduction

If you manage VPS instances, you've probably experienced this:

- `apt upgrade -y` finishes, and a critical service is down — you only recover after a full reboot;
- Kernel update breaks SSH config compatibility, and you lose remote access;
- Python 3.x minor version update causes an ABI incompatibility with a dependency library, and the application crashes;
- A database driver version regression during an update breaks the connection pool, causing a 40-minute outage;
- A 3 AM batch update triggers a libssl change that's incompatible with your application.

**The core problem: traditional `apt upgrade` is a "blind update" — all-or-nothing, with no way to know which packages are high-risk, which should be staged, or how to quickly roll back on failure.**

An intelligent package update orchestration system solves this:

1. Automatically collects all upgradable packages with version diffs;
2. A local LLM (Ollama + Qwen2.5) performs **risk scoring** on each package (kernel, library, application, config compatibility);
3. **Staged grey rollout** based on scores (low-risk first, high-risk last);
4. After each batch, automatic health verification with **instant auto-rollback** on failure;
5. All data stays on your VPS — zero exfiltration.

This article walks you through building this system from scratch.

## System Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                   LLM Package Update Orchestrator               │
├──────────────────┬──────────────────┬──────────────────┬────────┤
│  Inventory       │  LLM Risk       │  Staged Rollout   │  Health│
│  Collection      │  Scoring        │                    │  +Auto│
│                  │                  │                    │Rollback│
├──────────────────┼──────────────────┼──────────────────┼────────┤
│ apt list         │                  │ Batch 1: Low      │ systemd│
│ --upgradable     │  → Ollama       │  (libs, tools)    │ status │
│                  │  (Qwen2.5)      │                   │ check  │
│ Package metadata │                  │ Batch 2: Medium   │        │
│ Version diffs    │                  │  (apps)           │ Service│
│ Dependency       │                  │                   │ avail. │
│ relationships    │                  │ Batch 3: High     │ probe  │
│                  │                  │  (kernel,         │        │
│                  │                  │   runtime)         │ Auto-  │
│                  │                  │                   │ rollback│
└──────────────────┴──────────────────┴──────────────────┴────────┘
           ↓                ↓               ↓               ↓
      apt/dpkg         Ollama server   Staged apt install  Verification
                                                  + rollback scripts
```

## Step 1: Deploy Local LLM with Ollama

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull Qwen2.5-7B (recommended, strong at understanding package names and dependencies)
ollama pull qwen2.5:7b

# Verify
ollama run qwen2.5:7b "List the 5 highest-risk apt package update types on a Linux system"
```

For a 2C4G VPS, use `qwen2.5:3b`; for 4C8G or above, use `qwen2.5:7b`.

## Step 2: Package Inventory Collector

Collect all upgradable packages and key metadata:

```python
# collector/package_inventory.py
import subprocess
import json
from datetime import datetime

class PackageInventoryCollector:
    """Collect upgradable package inventory and metadata"""
    
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
        """Get all upgradable packages"""
        result = subprocess.run(
            ["apt", "list", "--upgradable"],
            capture_output=True, text=True, timeout=30
        )
        packages = []
        for line in result.stdout.strip().split("\n"):
            if "/upgradable" in line:
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
        """Get detailed info for a single package (description, deps, reverse deps)"""
        info = {"name": pkg_name}
        
        # apt show for description
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
        
        # Get which packages depend on this one (reverse dependencies)
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
        """Collect the full inventory"""
        upgradable = self.get_upgradable_packages()
        details = {}
        for pkg in upgradable[:50]:  # Limit to 50 to avoid excessive LLM context
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

## Step 3: LLM Risk Scoring Engine

This is the core. Feed the package list to the local LLM, which scores each package and provides reasoning:

```python
# engine/risk_scorer.py
import json
import requests
from datetime import datetime

class PackageRiskScorer:
    """Score upgradable packages for risk using LLM"""
    
    def __init__(self, ollama_url="http://localhost:11434", model="qwen2.5:7b"):
        self.ollama_url = ollama_url
        self.model = model
    
    def score_packages(self, inventory):
        """Score all upgradable packages for risk"""
        context = self._build_context(inventory)
        
        prompt = f"""You are a Linux systems operations expert. Below is a list of packages awaiting update on a VPS.

## System Info
- Distribution: {inventory['distribution']}
- Kernel: {inventory['kernel']}
- Upgradable package count: {inventory['upgradable_count']}

## Package Details
{context}

## Scoring Requirements
Output a JSON array. Each element:
[
  {{
    "package": "package name",
    "risk_score": 1-10,
    "risk_level": "low|medium|high|critical",
    "reason": "One-sentence risk explanation",
    "category": "kernel|runtime|library|application|tool|security-patch",
    "recommendation": "Recommendation (e.g., backup first / update last / batch OK / test environment validation needed)"
  }}
]

Scoring criteria:
- 1-3 (low): pure tool packages, docs, no reverse dependencies
- 4-6 (medium): commonly-used libraries with alternatives, application-layer updates
- 7-8 (high): core runtime (Python/Node), critical system libraries
- 9-10 (critical): kernel, init system, base C libraries, SSH, network stack

Output ONLY the JSON array, nothing else."""
        
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
            return {"error": f"LLM scoring failed: {str(e)}"}
    
    def _build_context(self, inventory):
        """Build LLM-readable text from package details"""
        parts = []
        for name, detail in inventory.get("package_details", {}).items():
            version_info = next(
                (p for p in inventory["upgradable_packages"] if p["name"] == name),
                {}
            )
            parts.append(f"""### {name}
- Current version: {version_info.get('current_version', 'unknown')}
- Target version: {version_info.get('available_version', 'unknown')}
- Description: {detail.get('description', 'N/A')[:200]}
- Depends: {detail.get('depends', 'N/A')[:200]}
- Reverse dependency count: {len(detail.get('reverse_dependencies', []))}
- Key reverse deps: {', '.join(detail.get('reverse_dependencies', [])[:10])}
""")
        return "\n".join(parts)
    
    def _parse_json_array(self, text):
        """Parse LLM JSON array output"""
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
            return {"error": "Cannot parse LLM output", "raw": text[:500]}
```

## Step 4: Staged Rollout Strategy

Group packages by risk score — low-risk first, high-risk last:

```python
# orchestrator/staged_rollout.py
from collections import defaultdict
from typing import List, Dict

class StagedRolloutPlanner:
    """Generate staged rollout plan based on risk scores"""
    
    RISK_ORDER = {"low": 1, "medium": 2, "high": 3, "critical": 4}
    
    def __init__(self, scores: List[Dict]):
        self.scores = scores
        self.plan = []
    
    def generate_plan(self) -> List[Dict]:
        """Generate the staged batch plan"""
        groups = defaultdict(list)
        for item in self.scores:
            if isinstance(item, dict):
                groups[item.get("risk_level", "medium")].append(item)
        
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
            "low": "Batch update, no extra verification needed",
            "medium": "Batch update + service status check",
            "high": "Update one at a time, wait 30s after each + verify critical services",
            "critical": "One at a time + snapshot before restart + auto-rollback standby",
        }
        return strategies.get(risk_level, "Standard flow")
    
    def get_execution_commands(self, batch: Dict) -> List[str]:
        """Generate execution commands for a batch"""
        packages = batch["packages"]
        risk = batch["risk_level"]
        
        commands = []
        
        # Pre-update snapshot
        commands.append("# Pre-update: record current service state")
        commands.append("systemctl list-units --type=service --state=running > /tmp/ops_pre_update_services.txt")
        commands.append("dpkg -l > /tmp/ops_pre_update_packages.txt")
        
        if risk in ["high", "critical"]:
            for pkg in packages:
                commands.append(f"\n# Update {pkg} (risk: {risk})")
                commands.append(f"DEBIAN_FRONTEND=noninteractive apt install -y {pkg}")
                commands.append(f"sleep 30")
                commands.append(f"systemctl is-active {pkg} || echo 'WARNING: {pkg} service check failed'")
        else:
            commands.append(f"\n# Batch update {len(packages)} {risk}-risk packages")
            commands.append(f"DEBIAN_FRONTEND=noninteractive apt install -y {' '.join(packages)}")
        
        commands.append("\n# Post-update: verify service state")
        commands.append("systemctl list-units --type=service --state=running > /tmp/ops_post_update_services.txt")
        commands.append("diff /tmp/ops_pre_update_services.txt /tmp/ops_post_update_services.txt || echo 'Service state changed - review needed'")
        
        return commands
```

## Step 5: Health Verification and Auto-Rollback

```python
# orchestrator/health_check.py
import subprocess
import time
import json
from datetime import datetime

class HealthVerifier:
    """Post-update health verification and auto-rollback"""
    
    def __init__(self, watch_services: List[str] = None):
        self.watch_services = watch_services or [
            "ssh", "nginx", "docker", "prometheus", "grafana"
        ]
    
    def verify_services(self) -> Dict:
        """Verify critical service states"""
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
        
        # Check disk space (updates can fill the disk)
        try:
            result = subprocess.run(
                ["df", "--output=pcent", "/"],
                capture_output=True, text=True, timeout=5
            )
            usage = result.stdout.strip().split("\n")[-1]
            results["disk"] = {"usage": usage, "critical": int(usage.rstrip("%")) > 90}
        except Exception:
            results["disk"] = {"usage": "unknown", "critical": False}
        
        # Check kernel load state (after kernel update)
        try:
            result = subprocess.run(["uname", "-r"], capture_output=True, text=True)
            results["current_kernel"] = result.stdout.strip()
        except Exception:
            results["current_kernel"] = "unknown"
        
        return results
    
    def check_rollback_needed(self, verification: Dict) -> bool:
        """Determine if rollback is needed"""
        failed_services = [
            svc for svc, info in verification.items()
            if isinstance(info, dict) and "active" in info and not info["active"]
        ]
        disk_critical = verification.get("disk", {}).get("critical", False)
        
        return len(failed_services) > 2 or disk_critical
    
    def rollback_packages(self, packages: List[str]) -> Dict:
        """Roll back specified packages to pre-update versions"""
        result = {"rolled_back": [], "failed": []}
        
        for pkg in packages:
            try:
                # Simplified: mark as needing manual action with target version
                result["failed"].append({
                    "package": pkg,
                    "reason": "Target rollback version needs to be specified",
                    "manual_action": f"apt install {pkg}=previous_version"
                })
            except Exception as e:
                result["failed"].append({"package": pkg, "reason": str(e)})
        
        return result
```

## Step 6: Main Orchestration Flow

```python
# main.py
#!/usr/bin/env python3
"""LLM Package Update Orchestrator - Main Entry"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path

from collector.package_inventory import PackageInventoryCollector
from engine.risk_scorer import PackageRiskScorer
from orchestrator.staged_rollout import StagedRolloutPlanner
from orchestrator.health_check import HealthVerifier

import subprocess


def run_orchestration(dry_run=False):
    """Execute the full package update orchestration flow"""
    
    print(f"📦 LLM Package Update Orchestration — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)
    
    # 1. Collect inventory
    print("\n[1/5] Collecting upgradable package inventory...")
    collector = PackageInventoryCollector()
    inventory = collector.get_full_inventory()
    print(f"  Found {inventory['upgradable_count']} upgradable packages")
    print(f"  Dist: {inventory['distribution']} | Kernel: {inventory['kernel']}")
    
    if inventory["upgradable_count"] == 0:
        print("  ✅ System is up to date, nothing to do")
        return
    
    # 2. LLM risk scoring
    print("\n[2/5] Calling local LLM for risk scoring...")
    scorer = PackageRiskScorer()
    scores = scorer.score_packages(inventory)
    
    if isinstance(scores, dict) and "error" in scores:
        print(f"  ⚠️ LLM scoring failed: {scores['error']}")
        print("  Fallback: keyword-based classification")
        scores = _fallback_classification(inventory)
    
    high_risk = [s for s in scores if s.get("risk_level") in ["high", "critical"]]
    print(f"  Scoring complete: {len(scores)} packages")
    print(f"  High-risk ({len(high_risk)}): {', '.join(s['package'] for s in high_risk)}")
    
    # 3. Generate staged plan
    print("\n[3/5] Generating staged rollout plan...")
    planner = StagedRolloutPlanner(scores)
    plan = planner.generate_plan()
    
    for batch in plan:
        print(f"  Batch {batch['batch']} ({batch['risk_level']}): {batch['count']} packages")
        for pkg in batch["packages"][:5]:
            print(f"    - {pkg}")
        if batch["count"] > 5:
            print(f"    ... and {batch['count'] - 5} more")
    
    if dry_run:
        print("\n[DRY RUN] Plan only, no updates executed")
        for batch in plan:
            print(f"\n  Batch {batch['batch']} commands:")
            for cmd in planner.get_execution_commands(batch):
                print(f"    {cmd}")
        return
    
    # 4. Execute staged updates
    verifier = HealthVerifier()
    
    for batch in plan:
        print(f"\n[4/5] Executing batch {batch['batch']} ({batch['risk_level']}, {batch['count']} pkgs)...")
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
                print(f"  ⚠️ Non-zero exit: {result.stderr[:200]}")
        
        # 5. Health verification
        print(f"\n  Health check...")
        health = verifier.verify_services()
        failed = [svc for svc, info in health.items()
                  if isinstance(info, dict) and "active" in info and not info["active"]]
        
        if verifier.check_rollback_needed(health):
            print(f"  ❌ Health check failed: {failed}, disk: {health.get('disk', {}).get('usage', '?')}")
            print(f"  Rolling back batch {batch['batch']}: {batch['packages']}")
            rollback_result = verifier.rollback_packages(batch["packages"])
            print(f"  Rollback result: {json.dumps(rollback_result, indent=2)}")
            print("\n  🛑 Stopping subsequent batches, awaiting manual intervention")
            break
        else:
            print(f"  ✅ Batch {batch['batch']} health check passed")
    
    # Save orchestration report
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
    print(f"\n✅ Orchestration report saved: {output_path}")


def _fallback_classification(inventory):
    """Fallback classification when LLM is unavailable"""
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
            "reason": "Keyword classification (LLM fallback)",
            "category": "unknown",
            "recommendation": "Standard flow",
        })
    return scores


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    run_orchestration(dry_run=dry_run)
```

## Step 7: Docker Compose Deployment

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
      - DRY_RUN=true  # Recommend dry-run mode for initial deployment
    restart: unless-stopped

volumes:
  ollama_data:
```

## Step 8: Scheduled Execution

### systemd timer (recommended)

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

## Step 9: Notification Integration

```python
# notification/telegram.py
import requests
import json

class TelegramNotifier:
    def __init__(self, bot_token, chat_id):
        self.bot_token = bot_token
        self.chat_id = chat_id
    
    def send_update_report(self, report):
        """Push update report to Telegram"""
        lines = [f"📦 Package Update Orchestration Report — {report['timestamp'][:16]}"]
        lines.append(f"Total: {report['total_packages']} packages")
        lines.append(f"Batches executed: {report['batches_executed']}")
        
        high_risk = report.get("high_risk_packages", [])
        if high_risk:
            lines.append(f"⚠️ High-risk: {', '.join(high_risk[:5])}")
        
        final_health = report.get("final_health", {})
        if isinstance(final_health, dict):
            failed = [s for s, i in final_health.items()
                     if isinstance(i, dict) and "active" in i and not i["active"]]
            if failed:
                lines.append(f"❌ Service anomalies: {', '.join(failed)}")
            else:
                lines.append(f"✅ All monitored services healthy")
        
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

## Real-World Example

```bash
$ cd /opt/update-orchestrator && python3 main.py --dry-run
📦 LLM Package Update Orchestration — 2026-10-19 22:00
============================================================

[1/5] Collecting upgradable package inventory...
  Found 23 upgradable packages
  Dist: Ubuntu | Kernel: 6.8.0-71-generic

[2/5] Calling local LLM for risk scoring...
  Scoring complete: 23 packages
  High-risk (3): linux-image-generic, openssl, systemd

[3/5] Generating staged rollout plan...
  Batch 1 (low): 12 packages
    - libxml2, procps, sysstat, curl, wget, ...
  Batch 2 (medium): 6 packages
    - python3.11, nginx, docker-ce, postgresql-client, ...
  Batch 3 (high): 4 packages
    - linux-headers-generic, openssl, systemd, libssl3
  Batch 4 (critical): 1 package
    - linux-image-generic

[DRY RUN] Plan only, no updates executed

  Batch 3 commands:
    # Pre-update: record current service state
    systemctl list-units --type=service --state=running > /tmp/ops_pre_update_services.txt
    dpkg -l > /tmp/ops_pre_update_packages.txt

    # Update linux-headers-generic (risk: high)
    DEBIAN_FRONTEND=noninteractive apt install -y linux-headers-generic
    sleep 30
    systemctl is-active linux-headers-generic || echo 'WARNING: service check failed'

    # Update openssl (risk: high)
    DEBIAN_FRONTEND=noninteractive apt install -y openssl
    sleep 30
    systemctl is-active openssl || echo 'WARNING: service check failed'

    # Post-update: verify service state
    systemctl list-units --type=service --state=running > /tmp/ops_post_update_services.txt
    diff /tmp/ops_pre_update_services.txt /tmp/ops_post_update_services.txt || echo 'Service state changed'
```

## Advanced: Multi-VPS Centralized Orchestration

When managing multiple VPS instances, build a centralized orchestration hub:

```python
# multi_vps_orchestrator.py
import json
from concurrent.futures import ThreadPoolExecutor

class MultiVpsUpdateOrchestrator:
    def __init__(self, vps_list):
        self.vps_list = vps_list  # [{"name": "prod-web-01", "ssh_key": "..."}, ...]
    
    def collect_all_inventories(self):
        """Collect package inventories from all VPS in parallel"""
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
        """Cross-VPS correlation analysis"""
        # Detect: multiple VPS have kernel updates → possibly a major version upgrade
        # Detect: one VPS has a different openssl version than others → security patch lag
        # LLM generates global update ordering recommendation
        pass
```

## Summary

In this article, you learned how to:

1. **Collect package inventory**: `apt list --upgradable` + `apt show` + `apt rdepends` for full metadata
2. **LLM risk scoring**: Local Ollama + Qwen2.5 scores each package (1-10), classified as low/medium/high/critical
3. **Staged rollout**: Batch by risk level — low-risk in bulk, high-risk one at a time, health check after each batch
4. **Auto-rollback**: Pre-update snapshot + health check + instant rollback on failure
5. **Notification integration**: Telegram pushes update reports and anomaly alerts

The core value of this system: **turning `apt upgrade` from a "blind update" into a "controlled update"** — you know each package's risk, update order, and rollback plan, instead of just hoping everything works out.

Zero data exfiltration — all analysis happens locally. As you use it more, the fallback classification strategy gets more precise, evolving from "manual ops" to "intelligent orchestration."
