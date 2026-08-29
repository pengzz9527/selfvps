---
title: "Building an AI-Driven Automated Penetration Testing Platform on VPS"
subtitle: "AI-Powered Security Assessment with Local LLM Analysis"
date: 2026-08-29
draft: false
tags: ["AI", "Penetration Testing", "Security", "VPS", "Automation", "OWASP", "Nmap", "Docker"]
categories: ["AI + VPS"]
image: /images/posts/ai-vps-automated-penetration-testing/featured.png
description: "Build an AI-driven automated penetration testing platform on VPS, integrating OWASP TOP10 detection, intelligent vulnerability scanning, natural language report generation, and actionable remediation guidance."
aliases: [/en/post/ai-vps-automated-penetration-testing/]
---

## Introduction

Network security is a core concern for every VPS operator. Traditional penetration testing relies on manual operations, is time-consuming, and难以覆盖全部攻击面 (hard to cover the entire attack surface). With the maturation of AI technology, **integrating large language models (LLMs) into penetration testing workflows** is becoming a new paradigm — AI can understand attack vectors, generate test payloads, analyze vulnerability exploitation paths, and produce readable security reports in natural language.

Building an **AI-driven automated penetration testing platform** on your VPS gives you:
- **24/7 continuous security scanning**: Scheduled full-surface assessment of public-facing services
- **OWASP TOP10 intelligent detection**: Covers injection, authentication, sensitive data exposure, and more
- **AI-generated actionable reports**: Risk descriptions and fix recommendations in plain language
- **Fully local deployment**: All scan data stays on your server, zero information leakage

This guide walks you through building a complete AI penetration testing platform from scratch, integrating classic tools like Nmap, Nikto, and SQLMap, with local LLM-powered structured security report generation.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      Scheduling & Orchestration Layer                   │
│              (Cron + Python Orchestration Script)                       │
└──────────────────────┬──────────────────────────────────────────────────┘
                       │
       ┌───────────────┼───────────────┐
       ▼               ▼               ▼
┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│  Asset      │ │  Vuln       │ │  Web App    │
│  Discovery  │ │  Scanning   │ │  Testing    │
│  Nmap       │ │  Nikto      │ │  SQLMap     │
│  Masscan    │ │  Dirb       │ │  Nuclei     │
└──────┬──────┘ └──────┬──────┘ └──────┬──────┘
       │               │               │
       └───────────────┼───────────────┘
                       ▼
            ┌─────────────────────┐
            │  Raw Result         │
            │  Aggregation        │
            │  (JSON/Markdown)    │
            └──────────┬──────────┘
                       │
                       ▼
            ┌─────────────────────┐
            │  AI Analysis Engine │
            │  (Local Ollama LLM) │
            │  - Vuln Classification│
            │  - Risk Scoring     │
            │  - Remediation Gen  │
            └──────────┬──────────┘
                       │
                       ▼
            ┌─────────────────────┐
            │  Report & Alert     │
            │  (Markdown + Email) │
            └─────────────────────┘
```

## Environment Setup

### Base Dependencies

```bash
# Update system
apt update && apt upgrade -y

# Install base tools
apt install -y python3 python3-pip docker.io git curl wget

# Enable Docker
systemctl enable docker && systemctl start docker
```

### Install Penetration Testing Tools

We use Docker containers to avoid polluting the host environment:

```bash
# Create project directory
mkdir -p ~/ai-pentest && cd ~/ai-pentest
```

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  # ── Nmap ──
  nmap:
    image: blablab1333/slimnyao:nmap
    container_name: ai-pentest-nmap
    volumes:
      - ./results:/data/results
    network_mode: host
    restart: unless-stopped

  # ── Nikto ──
  nikto:
    image: cyberus/nikto
    container_name: ai-pentest-nikto
    volumes:
      - ./results:/data/results
    network_mode: host
    restart: unless-stopped

  # ── SQLMap ──
  sqlmap:
    image: kalilinux/kali-rolling:latest
    container_name: ai-pentest-sqlmap
    volumes:
      - ./results:/data/results
    network_mode: host
    command: sleep infinity
    restart: unless-stopped

  # ── Nuclei (fast vulnerability template scanning) ──
  nuclei:
    image: projectdiscovery/nuclei:latest
    container_name: ai-pentest-nuclei
    volumes:
      - ./results:/data/results
      - ./templates:/templates
    network_mode: host
    restart: unless-stopped

  # ── OWASP ZAP (dynamic web app scanner) ──
  zaproxy:
    image: owasp/zap2docker-weekly
    container_name: ai-pentest-zap
    volumes:
      - ./results:/home/zap/results
    network_mode: host
    command: -cmd quickurl http://localhost:80
    restart: 'no'

volumes:
  results:
```

Start all scanners:

```bash
docker compose up -d
```

### Deploy Local LLM (for AI Analysis)

```bash
# Install Ollama if not already installed
curl -fsSL https://ollama.com/install.sh | sh

# Pull a model suitable for security analysis
ollama pull qwen2.5:7b

# Verify
ollama run qwen2.5:7b "Hello, you are a cybersecurity expert"
```

## Core Scanning Scripts

### Asset Discovery Module

`scripts/discovery.py`:

```python
#!/usr/bin/env python3
"""Asset Discovery: Nmap port scanning + service identification"""
import subprocess
import json
import os
from datetime import datetime

TARGETS_FILE = os.environ.get("TARGETS_FILE", "/etc/pentest-targets.txt")
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "./results/discovery")

os.makedirs(OUTPUT_DIR, exist_ok=True)
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

results = []

with open(TARGETS_FILE) as f:
    targets = [line.strip() for line in f if line.strip() and not line.startswith("#")]

for target in targets:
    print(f"[*] Scanning {target} ...")
    out_file = f"{OUTPUT_DIR}/{timestamp}_{target.replace('/', '_')}.xml"

    # Quick port scan
    cmd = [
        "docker", "run", "--rm", "--network", "host",
        "blablab1333/slimnyao:nmap",
        "-sS", "-sV", "-O", "--top-ports", "1000",
        "-oX", out_file, target
    ]
    subprocess.run(cmd, check=False, timeout=300)

    results.append({
        "target": target,
        "scan_time": timestamp,
        "output": out_file,
        "tool": "nmap"
    })

# Save discovery result index
with open(f"{OUTPUT_DIR}/{timestamp}_index.json", "w") as f:
    json.dump(results, f, indent=2)

print(f"[+] Discovery complete. Results in {OUTPUT_DIR}")
```

### Vulnerability Scanning Module

`scripts/vuln_scan.py`:

```python
#!/usr/bin/env python3
"""Vulnerability Scanning: Nikto + Nuclei combined scan"""
import subprocess
import json
import os
from datetime import datetime

TARGETS_FILE = "/etc/pentest-targets.txt"
OUTPUT_DIR = "./results/vuln_scan"

os.makedirs(OUTPUT_DIR, exist_ok=True)
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

all_results = []

with open(TARGETS_FILE) as f:
    targets = [line.strip() for line in f if line.strip() and not line.startswith("#")]

for target in targets:
    print(f"[*] Vulnerability scan: {target}")

    # Nikto scan
    nikto_out = f"{OUTPUT_DIR}/{timestamp}_nikto_{target.replace('https://','').replace('http://','').replace(':','_')}.txt"
    cmd = [
        "docker", "run", "--rm", "--network", "host",
        "cyberus/nikto",
        "-h", target,
        "-Format", "txt",
        "-e", "html",
        "-o", nikto_out
    ]
    subprocess.run(cmd, check=False, timeout=600)
    all_results.append({"target": target, "tool": "nikto", "output": nikto_out})

    # Nuclei template scanning
    nuclei_out = f"{OUTPUT_DIR}/{timestamp}_nuclei_{target.replace('https://','').replace('http://','').replace(':','_')}.json"
    cmd = [
        "docker", "run", "--rm", "--network", "host",
        "projectdiscovery/nuclei:latest",
        "-u", target,
        "-jse", nuclei_out,
        "-severity", "info,low,medium,high,critical",
        "-rate-limit", "50",
        "-bulk-size", "25"
    ]
    subprocess.run(cmd, check=False, timeout=600)
    all_results.append({"target": target, "tool": "nuclei", "output": nuclei_out})

with open(f"{OUTPUT_DIR}/{timestamp}_index.json", "w") as f:
    json.dump(all_results, f, indent=2)

print(f"[+] Vuln scan complete. Results in {OUTPUT_DIR}")
```

### SQL Injection Detection

`scripts/sqli_check.py`:

```python
#!/usr/bin/env python3
"""SQL Injection Detection: Deep probing for web applications"""
import subprocess
import json
import os
from datetime import datetime

TARGETS_FILE = "/etc/pentest-targets.txt"
OUTPUT_DIR = "./results/sqli"

os.makedirs(OUTPUT_DIR, exist_ok=True)
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

# Read targets
with open(TARGETS_FILE) as f:
    targets = [line.strip() for line in f if line.strip() and not line.startswith("#")]

results = []
for target in targets:
    print(f"[*] SQLi check: {target}")
    out_file = f"{OUTPUT_DIR}/{timestamp}_{target.replace('https://','').replace(':','_')}.log"

    # SQLMap requires interactive input; use non-interactive mode
    cmd = [
        "docker", "run", "--rm", "--network", "host",
        "kalilinux/kali-rolling:latest",
        "bash", "-c",
        f"sqlmap -u '{target}' --batch --level=3 --risk=1 -v 0 2>&1 | tee {out_file}"
    ]
    subprocess.run(cmd, check=False, timeout=600)
    results.append({"target": target, "output": out_file})

print(f"[+] SQLi scan complete.")
```

## AI Analysis Engine

### Vulnerability Analysis Prompt

`config/prompts.py`:

```python
SECURITY_ANALYSIS_PROMPT = """\
You are a professional cybersecurity analyst. Below are penetration test scan results. \
Analyze each discovered vulnerability and provide risk assessment and remediation guidance.

Output in JSON format:
{{
  "summary": "Overall security posture overview (2-3 sentences)",
  "risk_score": 0-100,
  "vulnerabilities": [
    {{
      "id": "Vulnerability ID",
      "title": "Vulnerability Title",
      "severity": "critical|high|medium|low|info",
      "description": "Vulnerability Description",
      "impact": "Potential Impact",
      "remediation": "Remediation Recommendations",
      "cwe_id": "CWE-XXX",
      "references": ["Related Links"]
    }}
  ],
  "prioritized_actions": ["Priority remediation checklist"],
  "compliance_notes": "Compliance-related notes"
}}

Scan results:
{scan_results}
"""

REPORT_GENERATION_PROMPT = """\
You are a security engineer. Convert the following vulnerability analysis into a \
professional penetration testing report. The report should include: executive summary, \
detailed findings, risk matrix, remediation timeline, and compliance recommendations.
Language: English.

Analysis data:
{analysis_data}
"""
```

### AI Analysis Script

`scripts/ai_analyze.py`:

```python
#!/usr/bin/env python3
"""AI Vulnerability Analysis & Report Generation"""
import subprocess
import json
import os
import glob
from datetime import datetime
from config.prompts import SECURITY_ANALYSIS_PROMPT, REPORT_GENERATION_PROMPT

RESULTS_DIR = "./results"
REPORTS_DIR = "./reports"
os.makedirs(REPORTS_DIR, exist_ok=True)

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

def collect_scan_results():
    """Collect all scan results"""
    findings = []

    # Nikto results
    for f in glob.glob(f"{RESULTS_DIR}/vuln_scan/*nikto*.txt"):
        with open(f) as fh:
            content = fh.read()
            findings.append({"source": "nikto", "content": content})

    # Nuclei results
    for f in glob.glob(f"{RESULTS_DIR}/vuln_scan/*nuclei*.json"):
        try:
            with open(f) as fh:
                data = json.load(fh)
                if isinstance(data, list):
                    for item in data:
                        findings.append({
                            "source": "nuclei",
                            "template": item.get("template-id", "unknown"),
                            "severity": item.get("info", {}).get("severity", "unknown"),
                            "matched-at": item.get("matched-at", ""),
                            "description": item.get("info", {}).get("description", "")
                        })
        except:
            pass

    return findings

def call_ollama(prompt: str) -> str:
    """Call local Ollama LLM"""
    cmd = [
        "ollama", "run", "qwen2.5:7b",
        prompt
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    return result.stdout.strip()

def main():
    print("[*] Collecting scan results...")
    findings = collect_scan_results()

    if not findings:
        print("[!] No scan results found. Run discovery and vuln_scan first.")
        return

    findings_json = json.dumps(findings, indent=2, ensure_ascii=False)

    print("[*] Running AI vulnerability analysis...")
    analysis_prompt = SECURITY_ANALYSIS_PROMPT.format(scan_results=findings_json)
    analysis_result = call_ollama(analysis_prompt)

    # Save raw analysis
    with open(f"{REPORTS_DIR}/{timestamp}_analysis.json", "w") as f:
        f.write(analysis_result)

    print("[*] Generating security report...")
    report_prompt = REPORT_GENERATION_PROMPT.format(analysis_data=analysis_result)
    report = call_ollama(report_prompt)

    # Save report
    report_path = f"{REPORTS_DIR}/{timestamp}_security_report.md"
    with open(report_path, "w") as f:
        f.write("# 🔒 VPS Security Penetration Test Report\n\n")
        f.write(f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write("---\n\n")
        f.write(report)

    print(f"[+] Report saved: {report_path}")
    print(f"[+] Analysis saved: {REPORTS_DIR}/{timestamp}_analysis.json")

if __name__ == "__main__":
    main()
```

## One-Click Scan Orchestration

`scripts/run_full_scan.py`:

```python
#!/usr/bin/env python3
"""Full Penetration Testing Pipeline: Discovery → Scan → AI Analysis → Report"""
import subprocess
import sys
import os
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def run_script(name: str):
    script = os.path.join(SCRIPT_DIR, f"{name}.py")
    if not os.path.exists(script):
        print(f"[!] Script not found: {script}")
        return False
    print(f"\n{'='*50}")
    print(f"[*] Running: {name}")
    print(f"{'='*50}")
    result = subprocess.run([sys.executable, script], cwd=os.path.dirname(SCRIPT_DIR))
    return result.returncode == 0

def main():
    start = datetime.now()
    print(f"🚀 AI-Powered Pentest Platform - Full Scan")
    print(f"⏰ Started: {start.strftime('%Y-%m-%d %H:%M:%S')}")

    # 1. Asset Discovery
    if not run_script("discovery"):
        print("[!] Discovery failed, continuing anyway...")

    # 2. Vulnerability Scanning
    if not run_script("vuln_scan"):
        print("[!] Vuln scan failed, continuing anyway...")

    # 3. SQL Injection Detection
    if not run_script("sqli_check"):
        print("[!] SQLi check failed, continuing anyway...")

    # 4. AI Analysis & Report
    if not run_script("ai_analyze"):
        print("[!] AI analysis failed.")
        return

    elapsed = (datetime.now() - start).total_seconds()
    print(f"\n✅ Full scan complete in {elapsed:.1f}s")
    print(f"📄 Reports in: ./reports/")

if __name__ == "__main__":
    main()
```

## Scheduled Task Configuration

Set up crontab:

```bash
# Edit crontab
crontab -e
```

Add the following entries:

```cron
# Daily full penetration test at 2:00 AM
0 2 * * * cd /root/ai-pentest && python3 scripts/run_full_scan.py >> /var/log/pentest.log 2>&1

# Weekly deep scan (with ZAP) on Sundays at 3:00 AM
0 3 * * 0 cd /root/ai-pentest && docker compose up -d zaproxy && sleep 120 && docker compose down zaproxy >> /var/log/pentest-deep.log 2>&1
```

## Multi-Target Configuration

Create `/etc/pentest-targets.txt`:

```
# One target per line, supports HTTP/HTTPS
https://your-vps-domain.com
https://api.your-service.com
http://192.168.1.100:8080
```

## Sample Report Structure

The AI-generated report includes the following sections:

```markdown
# 🔒 VPS Security Penetration Test Report

**Generated**: 2026-08-29 02:15:33
**Scan Scope**: 3 target domains/IPs
**Tools Used**: Nmap, Nikto, Nuclei, SQLMap
**AI Engine**: Qwen2.5-7B (locally deployed)

---

## 📋 Executive Summary

This penetration test discovered **12 security findings**, including:
- 🔴 Critical: 1
- 🟠 High: 2
- 🟡 Medium: 4
- 🟢 Low: 3
- 🔵 Info: 2

**Overall Risk Score: 72/100** ⚠️

## 🔍 Detailed Findings

### CVE-2024-XXXX: Apache Log4j Remote Code Execution

- **Severity**: Critical
- **CVSS Score**: 10.0
- **Impact**: Remote code execution via JNDI injection
- **Remediation**:
  1. Upgrade Log4j to version 2.17.1+
  2. If upgrade is not possible, set `-Dlog4j2.formatMsgNoLookups=true`
  3. Deploy WAF rules at the network layer to block JNDI keywords

[... more findings ...]

## 📊 Remediation Priority Matrix

| Priority | Vulnerability | Est. Fix Time | Owner |
|----------|--------------|---------------|-------|
| P0 - Immediate | Log4j RCE | 2 hours | DevOps |
| P1 - This Week | Missing HSTS Header | 30 minutes | WebAdmin |
| P2 - This Month | Expired SSL Certificate | 1 hour | Security |

## 📜 Compliance Notes

This scan covers all OWASP TOP10 2021 categories:
- A01:2021 broken access control ✅
- A02:2021 cryptographic failures ⚠️
- A03:2021 injection ✅
- ...
```

## Deployment Checklist

| Step | Command | Description |
|------|---------|-------------|
| 1 | Clone + copy configs | Set up project |
| 2 | `docker compose up -d` | Start scanners |
| 3 | Configure `/etc/pentest-targets.txt` | Add scan targets |
| 4 | `ollama pull qwen2.5:7b` | Download analysis model |
| 5 | Run first scan | `python3 scripts/run_full_scan.py` |
| 6 | Configure cron | Set scheduled tasks |
| 7 | Review reports | `ls reports/` |

## Cost Analysis

| Component | Cost | Description |
|-----------|------|-------------|
| VPS | $5-20/month | 2C4G is sufficient |
| Docker Scanners | Free | Open-source tools |
| Ollama LLM | Free | Local inference, zero API cost |
| Time Cost | ~15 min/scan | Fully automated, unattended |

Compared to paid penetration testing services ($500-5,000 per engagement), the self-built platform has near-zero marginal cost per scan.

## Summary

By integrating classic penetration testing tools with a local AI large language model, you can build a **low-cost, high-frequency, professional-grade** automated security assessment platform on your VPS. Key advantages:

1. **Continuous monitoring**: Daily automated scans to detect new vulnerabilities promptly
2. **AI empowerment**: Natural language reports make risks understandable to non-technical stakeholders
3. **Privacy protection**: Local LLM ensures scan results never leave your server
4. **Extensibility**: Easy to add new scanning modules and AI analysis capabilities

Security is not a one-time task — it's a continuous process. Let AI be your 24/7 security operations assistant.
