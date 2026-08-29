---
title: "VPS 上构建 AI 驱动的智能渗透测试与安全评估平台"
subtitle: "Building an AI-Driven Automated Penetration Testing Platform on VPS"
date: 2026-08-29
draft: false
tags: ["AI", "渗透测试", "安全评估", "VPS", "自动化", "OWASP", "Nmap", "Docker"]
categories: ["AI + VPS"]
image: /images/posts/ai-vps-automated-penetration-testing/featured.png
description: "在 VPS 上搭建基于 AI 的自动化渗透测试平台，整合 OWASP TOP10 检测、智能漏洞扫描、自然语言报告生成与修复建议，实现持续安全评估与合规审计。"
aliases: [/zh/post/ai-vps-automated-penetration-testing/]
---

## 引言

网络安全是每个 VPS 运维者的核心关切。传统的渗透测试依赖人工操作，耗时且难以覆盖全部攻击面。随着 AI 技术的成熟，**将大语言模型（LLM）融入渗透测试流程**正在成为新的范式——AI 可以理解攻击向量、生成测试 payload、分析漏洞利用路径，并以自然语言输出可读的安全报告。

在 VPS 上构建一套 **AI 驱动的自动化渗透测试平台**，你可以：
- **7×24 持续安全扫描**：定时对公开服务进行全面暴露面评估
- **OWASP TOP10 智能检测**：覆盖注入、身份认证、敏感数据泄露等常见漏洞
- **AI 生成可操作报告**：用自然语言描述漏洞风险与修复方案
- **本地化部署**：所有扫描数据不出服务器，敏感信息零外泄

本文将带你从零搭建一个完整的 AI 渗透测试平台，整合 Nmap、Nikto、SQLMap 等经典工具，并通过本地 LLM 自动生成结构化安全报告。

## 架构全景

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         调度与编排层                                     │
│              (Cron + Python Orchestration Script)                       │
└──────────────────────┬──────────────────────────────────────────────────┘
                       │
       ┌───────────────┼───────────────┐
       ▼               ▼               ▼
┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│  资产发现    │ │  漏洞扫描    │ │  Web 检测   │
│  Nmap       │ │  Nikto      │ │  SQLMap     │
│  Masscan    │ │  Dirb       │ │  nuclei     │
└──────┬──────┘ └──────┬──────┘ └──────┬──────┘
       │               │               │
       └───────────────┼───────────────┘
                       ▼
            ┌─────────────────────┐
            │   原始结果聚合       │
            │   (JSON/Markdown)   │
            └──────────┬──────────┘
                       │
                       ▼
            ┌─────────────────────┐
            │   AI 分析引擎        │
            │  (本地 Ollama LLM)  │
            │  - 漏洞分类         │
            │  - 风险评级         │
            │  - 修复建议生成     │
            └──────────┬──────────┘
                       │
                       ▼
            ┌─────────────────────┐
            │   报告生成与通知     │
            │  (Markdown + 邮件)  │
            └─────────────────────┘
```

## 环境准备

### 基础依赖

```bash
# 更新系统
apt update && apt upgrade -y

# 安装基础工具
apt install -y python3 python3-pip docker.io git curl wget

# 启动 Docker
systemctl enable docker && systemctl start docker
```

### 安装渗透测试工具

我们使用 Docker 容器化方式安装，避免污染宿主机环境：

```bash
# 创建项目目录
mkdir -p ~/ai-pentest && cd ~/ai-pentest
```

创建 `docker-compose.yml`：

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

  # ── Nuclei (快速漏洞模板扫描) ──
  nuclei:
    image: projectdiscovery/nuclei:latest
    container_name: ai-pentest-nuclei
    volumes:
      - ./results:/data/results
      - ./templates:/templates
    network_mode: host
    restart: unless-stopped

  # ── OWASP ZAP (动态 Web 应用扫描) ──
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

启动所有扫描器：

```bash
docker compose up -d
```

### 部署本地 LLM（用于 AI 分析）

```bash
# 拉取并运行 Ollama（如果尚未安装）
curl -fsSL https://ollama.com/install.sh | sh

# 拉取适合安全分析的小模型
ollama pull qwen2.5:7b

# 验证
ollama run qwen2.5:7b "你好，你是一个网络安全专家"
```

## 核心扫描脚本

### 资产发现模块

`scripts/discovery.py`：

```python
#!/usr/bin/env python3
"""资产发现：Nmap 端口扫描 + 服务识别"""
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

    # 快速端口扫描
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

# 保存发现结果索引
with open(f"{OUTPUT_DIR}/{timestamp}_index.json", "w") as f:
    json.dump(results, f, indent=2)

print(f"[+] Discovery complete. Results in {OUTPUT_DIR}")
```

### 漏洞扫描模块

`scripts/vuln_scan.py`：

```python
#!/usr/bin/env python3
"""漏洞扫描：Nikto + Nuclei 综合扫描"""
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

    # Nikto 扫描
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

    # Nuclei 模板扫描
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

### SQL 注入检测

`scripts/sqli_check.py`：

```python
#!/usr/bin/env python3
"""SQL 注入检测：针对 Web 应用的深度探测"""
import subprocess
import json
import os
from datetime import datetime

TARGETS_FILE = "/etc/pentest-targets.txt"
OUTPUT_DIR = "./results/sqli"

os.makedirs(OUTPUT_DIR, exist_ok=True)
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

# 读取目标
with open(TARGETS_FILE) as f:
    targets = [line.strip() for line in f if line.strip() and not line.startswith("#")]

results = []
for target in targets:
    print(f"[*] SQLi check: {target}")
    out_file = f"{OUTPUT_DIR}/{timestamp}_{target.replace('https://','').replace(':','_')}.log"

    cmd = [
        "docker", "run", "--rm", "--network", "host",
        "kalilinux/kali-rolling:latest",
        "sqlmap", "-u", target,
        "--batch", "--random-agent",
        "--level=3", "--risk=1",
        "--output-dir", "/tmp/sqlmap-out",
        "-m", "/dev/null"  # placeholder
    ]
    # SQLMap 需要交互式输入，改用非批量模式
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

## AI 分析引擎

### 漏洞分析提示词

`config/prompts.py`：

```python
SECURITY_ANALYSIS_PROMPT = """\
你是一个专业的网络安全分析师。以下是一组渗透测试扫描结果，请分析每个发现的漏洞，\
给出风险评估和修复建议。

请以 JSON 格式输出：
{{
  "summary": "整体安全态势概述（2-3句话）",
  "risk_score": 0-100,
  "vulnerabilities": [
    {{
      "id": "漏洞编号",
      "title": "漏洞标题",
      "severity": "critical|high|medium|low|info",
      "description": "漏洞描述",
      "impact": "潜在影响",
      "remediation": "修复建议",
      "cwe_id": "CWE-XXX",
      "references": ["相关链接"]
    }}
  ],
  "prioritized_actions": ["优先级修复清单"],
  "compliance_notes": "合规相关说明"
}}

扫描结果：
{scan_results}
"""

REPORT_GENERATION_PROMPT = """\
你是一位安全工程师，请将以下漏洞分析结果转换为一份专业的渗透测试报告。\
报告应包含：执行摘要、详细发现、风险矩阵、修复时间线和合规建议。\
语言：中文。

分析数据：
{analysis_data}
"""
```

### AI 分析脚本

`scripts/ai_analyze.py`：

```python
#!/usr/bin/env python3
"""AI 漏洞分析与报告生成"""
import subprocess
import json
import os
import glob
from datetime import datetime
from prompts import SECURITY_ANALYSIS_PROMPT, REPORT_GENERATION_PROMPT

RESULTS_DIR = "./results"
REPORTS_DIR = "./reports"
os.makedirs(REPORTS_DIR, exist_ok=True)

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

def collect_scan_results():
    """收集所有扫描结果"""
    findings = []

    # Nikto 结果
    for f in glob.glob(f"{RESULTS_DIR}/vuln_scan/*nikto*.txt"):
        with open(f) as fh:
            content = fh.read()
            findings.append({"source": "nikto", "content": content})

    # Nuclei 结果
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
    """调用本地 Ollama LLM"""
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

    # 保存原始分析
    with open(f"{REPORTS_DIR}/{timestamp}_analysis.json", "w") as f:
        f.write(analysis_result)

    print("[*] Generating security report...")
    report_prompt = REPORT_GENERATION_PROMPT.format(analysis_data=analysis_result)
    report = call_ollama(report_prompt)

    # 保存报告
    report_path = f"{REPORTS_DIR}/{timestamp}_security_report.md"
    with open(report_path, "w") as f:
        f.write("# 🔒 VPS 安全渗透测试报告\n\n")
        f.write(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write("---\n\n")
        f.write(report)

    print(f"[+] Report saved: {report_path}")
    print(f"[+] Analysis saved: {REPORTS_DIR}/{timestamp}_analysis.json")

if __name__ == "__main__":
    main()
```

## 一键扫描编排脚本

`scripts/run_full_scan.py`：

```python
#!/usr/bin/env python3
"""完整渗透测试流水线：发现 → 扫描 → AI 分析 → 报告"""
import subprocess
import sys
import os
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.join(SCRIPT_DIR, "../.env")

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

    # 1. 资产发现
    if not run_script("discovery"):
        print("[!] Discovery failed, continuing anyway...")

    # 2. 漏洞扫描
    if not run_script("vuln_scan"):
        print("[!] Vuln scan failed, continuing anyway...")

    # 3. SQL 注入检测
    if not run_script("sqli_check"):
        print("[!] SQLi check failed, continuing anyway...")

    # 4. AI 分析 & 报告
    if not run_script("ai_analyze"):
        print("[!] AI analysis failed.")
        return

    elapsed = (datetime.now() - start).total_seconds()
    print(f"\n✅ Full scan complete in {elapsed:.1f}s")
    print(f"📄 Reports in: ./reports/")

if __name__ == "__main__":
    main()
```

## 定时调度配置

创建 crontab 定时任务：

```bash
# 编辑 crontab
crontab -e
```

添加以下条目：

```cron
# 每日凌晨 2:00 执行完整渗透测试
0 2 * * * cd /root/ai-pentest && python3 scripts/run_full_scan.py >> /var/log/pentest.log 2>&1

# 每周日凌晨 3:00 执行深度扫描（含 ZAP）
0 3 * * 0 cd /root/ai-pentest && docker compose up -d zaproxy && sleep 120 && docker compose down zaproxy >> /var/log/pentest-deep.log 2>&1
```

## 多目标配置文件

创建 `/etc/pentest-targets.txt`：

```
# 每个目标一行，支持 HTTP/HTTPS
https://your-vps-domain.com
https://api.your-service.com
http://192.168.1.100:8080
```

## 报告示例结构

AI 生成的报告包含以下章节：

```markdown
# 🔒 VPS 安全渗透测试报告

**生成时间**: 2026-08-29 02:15:33
**扫描范围**: 3 个目标域名/IP
**扫描工具**: Nmap, Nikto, Nuclei, SQLMap
**AI 引擎**: Qwen2.5-7B (本地部署)

---

## 📋 执行摘要

本次渗透测试共发现 **12 个安全发现**，其中：
- 🔴 严重 (Critical): 1 个
- 🟠 高危 (High): 2 个
- 🟡 中危 (Medium): 4 个
- 🟢 低危 (Low): 3 个
- 🔵 信息 (Info): 2 个

**综合风险评分: 72/100** ⚠️

## 🔍 详细发现

### CVE-2024-XXXX: Apache Log4j RCE 漏洞

- **严重级别**: Critical
- **CVSS 评分**: 10.0
- **影响**: 远程代码执行，攻击者可通过 JNDI 注入执行任意命令
- **修复建议**: 
  1. 升级 Log4j 至 2.17.1+ 版本
  2. 如无法升级，设置 `-Dlog4j2.formatMsgNoLookups=true`
  3. 在网络层部署 WAF 规则阻断 JNDI 关键字

[... 更多发现 ...]

## 📊 修复优先级矩阵

| 优先级 | 漏洞 | 预计修复时间 | 责任人 |
|--------|------|-------------|--------|
| P0 - 立即修复 | Log4j RCE | 2小时 | DevOps |
| P1 - 本周内 | 缺失 HSTS 头 | 30分钟 | WebAdmin |
| P2 - 本月内 | 过期的 SSL 证书 | 1小时 | Security |

## 📜 合规说明

本次扫描覆盖了 OWASP TOP10 2021 全部类别：
- A01:2021  broken access control ✅
- A02:2021 cryptographic failures ⚠️
- A03:2021 injection ✅
- ...
```

## 部署清单

| 步骤 | 命令 | 说明 |
|------|------|------|
| 1 | `git clone` + 复制配置 | 克隆项目 |
| 2 | `docker compose up -d` | 启动扫描器 |
| 3 | 配置 `/etc/pentest-targets.txt` | 添加扫描目标 |
| 4 | `ollama pull qwen2.5:7b` | 下载分析模型 |
| 5 | 执行首次扫描 | `python3 scripts/run_full_scan.py` |
| 6 | 配置 cron | 设置定时任务 |
| 7 | 查看报告 | `ls reports/` |

## 成本分析

| 组件 | 费用 | 说明 |
|------|------|------|
| VPS | ¥50-200/月 | 2C4G 即可运行 |
| Docker 扫描器 | 免费 | 开源工具 |
| Ollama LLM | 免费 | 本地推理，零 API 费用 |
| 时间成本 | ~15分钟/次 | 全自动无人值守 |

相比付费渗透测试服务（¥5,000-50,000/次），自建平台的单次扫描成本几乎为零。

## 总结

通过整合经典渗透测试工具与本地 AI 大模型，你可以在 VPS 上构建一套**低成本、高频率、专业化**的自动化安全评估平台。关键优势：

1. **持续监控**：每日自动扫描，及时发现新漏洞
2. **AI 赋能**：自然语言报告让非技术人员也能理解风险
3. **隐私保护**：本地 LLM 确保扫描结果不外传
4. **可扩展**：轻松添加新的扫描模块和 AI 分析能力

安全不是一次性的任务，而是一个持续的过程。让 AI 成为你的 7×24 安全运维助手。
