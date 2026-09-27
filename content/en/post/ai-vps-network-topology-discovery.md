---
title: "AI-Powered VPS Network Topology Discovery & Security Policy Auto-Generation"
description: "Running dozens of Docker containers with exposed ports? You might not know their communication patterns. This guide shows how to use a local LLM to auto-discover network topology, generate security policies, and detect configuration drift — all on your own VPS."
date: 2026-09-27T20:00:00+08:00
lastmod: 2026-09-27T20:00:00+08:00
slug: "ai-vps-network-topology-discovery"
tags: ["AI", "VPS", "AIOps", "Network Topology", "Network Security", "LLM", "Docker", "Firewall", "Zero Trust", "iptables"]
categories: ["AI + VPS"]
image: /images/posts/ai-vps-network-topology-discovery/featured.png
draft: false
---

## Introduction: Does Your VPS Network Really Feel Safe?

When you run a pile of Docker containers — Nginx, PostgreSQL, Redis, API services, cron jobs — each with its own exposed ports and dependencies, can you really answer these questions after a few months:

- Which containers need to talk to each other?
- Which ports are truly exposed to the internet?
- Which services have direct database access they shouldn't?

Most people's answer: **no, not really.**

Traditional ops rely on manual network documentation, which falls apart as services multiply. This guide presents an **AI-driven network topology discovery system** — using a local LLM to auto-collect network state, infer service dependencies, generate least-privilege firewall rules, and continuously monitor for configuration drift. All data stays on your VPS; no external API calls required.

---

## 1. Why Use AI for Network Topology Discovery?

### Three Pain Points of Traditional Approaches

| Pain Point | Current State | AI Solution |
|-----------|--------------|-------------|
| **Unclear topology** | Manually tracking ports and dependencies becomes impossible | LLM auto-analyzes `ss`/`docker network` output, generates visual topology |
| **Stale security policies** | Forgetting firewall rules when adding services, or over-opening ports | LLM infers least-privilege policy, auto-generates iptables/nftables rules |
| **Undetected drift** | Network config changes go unnoticed until audit time | Periodic巡检 + LLM baseline comparison, immediate alerting on anomalies |

### Core Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      Your VPS                                    │
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │  Data        │    │  LLM         │    │  Policy      │      │
│  │  Collection  │───►│  Reasoning   │───►│  Enforcement │      │
│  │              │    │              │    │              │      │
│  │ • ss -tulnp  │    │ • Topology   │    │ • iptables   │      │
│  │ • docker ps  │    │   inference  │    │ • nftables   │      │
│  │ • docker net │    │ • Risk       │    │ • Apply      │      │
│  │ • iptables   │    │   scoring    │    │ • Baseline   │      │
│  │ • process    │    │ • Drift      │    │              │      │
│  │   tree       │    │   detection  │    │              │      │
│  └──────────────┘    └──────┬───────┘    └──────┬───────┘      │
│                             │                   │               │
│                             ▼                   ▼               │
│                    ┌──────────────┐    ┌──────────────┐        │
│                    │  Alert Layer  │    │  Baseline   │        │
│                    │  Telegram    │    │  /var/db/net-│        │
│                    │  Email/Webhook│   │  baseline/   │        │
│                    └──────────────┘    └──────────────┘        │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. Step 1: Network Data Collection

Create a unified collection script that gathers all network-related information:

```bash
mkdir -p /opt/net-discovery
vim /opt/net-discovery/collect.sh
```

```bash
#!/bin/bash
# /opt/net-discovery/collect.sh — Full network state collection
set -euo pipefail

TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
OUT_DIR="/tmp/net-discovery"
mkdir -p "$OUT_DIR"

echo "=== Collection Time: $TIMESTAMP ===" > "$OUT_DIR/timestamp.txt"

# 1. Listening ports (TCP/UDP)
echo "=== Listening Ports ===" > "$OUT_DIR/listening_ports.txt"
ss -tulnp 2>/dev/null >> "$OUT_DIR/listening_ports.txt" || true

# 2. Active connections
echo "=== Active Connections ===" > "$OUT_DIR/active_connections.txt"
ss -tnp 2>/dev/null | head -200 >> "$OUT_DIR/active_connections.txt" || true

# 3. Docker network info
echo "=== Docker Networks ===" > "$OUT_DIR/docker_networks.txt"
docker network ls 2>/dev/null >> "$OUT_DIR/docker_networks.txt" || true
docker network inspect "$(docker network ls --format '{{.Name}}' 2>/dev/null | tr '\n' ',' | sed 's/,$//')" \
  > "$OUT_DIR/docker_network_inspect.json" 2>/dev/null || true

# 4. Docker container port mappings
echo "=== Docker Port Mappings ===" > "$OUT_DIR/docker_ports.txt"
docker ps --format '{{.Names}}\t{{.Ports}}\t{{.Status}}' 2>/dev/null \
  >> "$OUT_DIR/docker_ports.txt" || true

# 5. Firewall rules
echo "=== iptables Rules ===" > "$OUT_DIR/iptables_rules.txt"
iptables -L -n -v 2>/dev/null >> "$OUT_DIR/iptables_rules.txt" || true
iptables -t nat -L -n -v 2>/dev/null >> "$OUT_DIR/iptables_rules.txt" || true

# 6. Process network behavior
echo "=== Process Network Connections ===" > "$OUT_DIR/process_network.txt"
ss -tnp 2>/dev/null >> "$OUT_DIR/process_network.txt" || true

# 7. Host network interfaces
echo "=== Network Interfaces ===" > "$OUT_DIR/interfaces.txt"
ip addr show 2>/dev/null >> "$OUT_DIR/interfaces.txt" || true
ip route 2>/dev/null >> "$OUT_DIR/routes.txt" || true

echo "[$TIMESTAMP] Collection complete → $OUT_DIR"
```

Schedule periodic collection:

```bash
chmod +x /opt/net-discovery/collect.sh
# Collect every 15 minutes
(crontab -l 2>/dev/null; echo "*/15 * * * * /opt/net-discovery/collect.sh") | crontab -
```

---

## 3. Step 2: LLM Topology Reasoning Engine

The core analysis script feeds collected data to a local LLM, which understands the network structure and identifies risks:

```bash
vim /opt/net-discovery/analyze.py
```

```python
#!/usr/bin/env python3
"""
AI Network Topology Discovery & Security Scoring Engine
Reads collected data → LLM reasoning → outputs topology map + security policy recommendations
"""
import json
import subprocess
import time
from pathlib import Path
from datetime import datetime

DATA_DIR = Path("/tmp/net-discovery")
OLLAMA_URL = "http://localhost:11434"
MODEL = "qwen2.5:7b"
BASELINE_DIR = Path("/var/db/net-baseline")
BASELINE_DIR.mkdir(parents=True, exist_ok=True)


def read_all_data() -> str:
    """Read all collected files into a single context"""
    parts = []
    for f in sorted(DATA_DIR.glob("*.txt")):
        if f.name == "timestamp.txt":
            continue
        if f.exists():
            parts.append(f"### {f.stem.upper()}\n{f.read_text()}")
    for f in DATA_DIR.glob("*.json"):
        if f.exists():
            parts.append(f"### {f.stem.upper()}\n{f.read_text()[:8000]}")
    return "\n\n".join(parts)


def build_prompt(raw_data: str) -> str:
    return f"""You are a professional network security engineer and VPS operations expert. Analyze the following network collection data and complete three tasks:

## Task 1: Build Service Topology
Identify all network services (containers/processes) and infer their dependency relationships.
Format: SERVICE_A --> SERVICE_B (protocol:port)

## Task 2: Risk Assessment
Rate each exposed port (HIGH/MEDIUM/LOW) with reasoning. Pay special attention to:
- Database ports exposed to public internet
- SSH exposed without IP restriction
- Unauthenticated admin panels
- Unencrypted HTTP traffic

## Task 3: Least-Privilege Firewall Recommendations
Generate iptables rules for each service following the principle of least privilege.

Network collection data:
{raw_data}

Output your analysis in the following JSON format only (no other content):
{{
  "topology": [
    {{"from": "service_name", "to": "service_name", "protocol": "tcp", "port": 5432, "justification": "reason"}}
  ],
  "exposed_services": [
    {{"service": "name", "port": port_number, "binding": "0.0.0.0 or 127.0.0.1", "risk": "HIGH/MEDIUM/LOW", "reason": "explanation"}}
  ],
  "iptables_rules": [
    {{"chain": "INPUT/DOCKER", "rule": "full iptables command"}}
  ],
  "summary": "One-paragraph summary of current network security status",
  "recommendations": ["recommendation1", "recommendation2"]
}}
"""


def call_llm(prompt: str) -> dict:
    """Call Ollama local LLM"""
    payload = json.dumps({
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.1, "num_ctx": 32768}
    })
    try:
        result = subprocess.run(
            ["curl", "-s", f"{OLLAMA_URL}/api/generate", "-d", payload],
            capture_output=True, text=True, timeout=180
        )
        response = json.loads(result.stdout)
        text = response.get("response", "{}")
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        return json.loads(text.strip())
    except Exception as e:
        return {"error": str(e), "topology": [], "exposed_services": [], "recommendations": []}


def drift_detection(current: dict) -> list:
    """Compare with baseline to detect configuration drift"""
    baseline_file = BASELINE_DIR / "latest.json"
    if not baseline_file.exists():
        baseline_file.write_text(json.dumps(current, ensure_ascii=False, indent=2))
        return [{"type": "baseline_created", "message": "Initial network baseline created"}]

    previous = json.loads(baseline_file.read_text())
    drifts = []

    prev_ports = {(s["port"], s["binding"]) for s in previous.get("exposed_services", [])}
    curr_ports = {(s["port"], s["binding"]) for s in current.get("exposed_services", [])}
    for port, binding in curr_ports - prev_ports:
        drifts.append({
            "type": "new_exposure",
            "port": port,
            "binding": binding,
            "severity": "HIGH"
        })

    for port, binding in prev_ports - curr_ports:
        drifts.append({
            "type": "port_removed",
            "port": port,
            "binding": binding,
            "severity": "MEDIUM"
        })

    baseline_file.write_text(json.dumps(current, ensure_ascii=False, indent=2))
    return drifts


def send_alert(title: str, body: str):
    """Send Telegram alert"""
    token = Path("/opt/net-discovery/telegram_token").read_text().strip() if Path("/opt/net-discovery/telegram_token").exists() else ""
    chat_id = Path("/opt/net-discovery/telegram_chat").read_text().strip() if Path("/opt/net-discovery/telegram_chat").exists() else ""
    if not token or not chat_id:
        return
    import requests
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    requests.post(url, json={"chat_id": chat_id, "text": f"🔒 *{title}*\n\n{body}", "parse_mode": "Markdown"})


def main():
    print(f"[{datetime.now()}] Starting network topology analysis...")

    # 1. Collect data
    subprocess.run(["/opt/net-discovery/collect.sh"], check=True)

    # 2. LLM reasoning
    raw = read_all_data()
    prompt = build_prompt(raw)
    result = call_llm(prompt)

    if "error" in result:
        print(f"LLM analysis failed: {result['error']}")
        return

    # 3. Drift detection
    drifts = drift_detection(result)

    # 4. Generate report
    report = {
        "timestamp": datetime.now().isoformat(),
        "topology": result.get("topology", []),
        "exposed_services": result.get("exposed_services", []),
        "summary": result.get("summary", ""),
        "recommendations": result.get("recommendations", []),
        "drifts": drifts,
        "iptables_rules": result.get("iptables_rules", [])
    }

    report_file = DATA_DIR / f"report_{int(time.time())}.json"
    report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"Report saved: {report_file}")

    # 5. Print summary
    print(f"\n{'='*50}")
    print(f"Network Security Score Report")
    print(f"{'='*50}")
    print(f"Summary: {result.get('summary', 'N/A')}")
    print(f"\nExposed Services ({len(result.get('exposed_services', []))}):")
    for svc in result.get("exposed_services", []):
        emoji = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}.get(svc.get("risk", ""), "⚪")
        print(f"  {emoji} {svc['service']}: {svc['port']}/{svc.get('binding', '?')} [{svc['risk']}]")
        print(f"     Reason: {svc.get('reason', '')}")

    if drifts:
        print(f"\n⚠️ Detected {len(drifts)} configuration drift(s):")
        for d in drifts:
            print(f"  [{d['severity']}] {d['type']}: port {d.get('port', 'N/A')}")
    else:
        print("\n✅ No configuration drift — network state is stable")

    # 6. Send alert on high risk or drift
    high_risk = [s for s in result.get("exposed_services", []) if s.get("risk") == "HIGH"]
    if high_risk or drifts:
        alert_body = f"Found {len(high_risk)} high-risk exposed services, {len(drifts)} drift(s).\n\n"
        for s in high_risk:
            alert_body += f"- {s['service']}: {s['port']} ({s.get('reason', '')})\n"
        for d in drifts:
            alert_body += f"- Drift: {d['type']} port {d.get('port', 'N/A')}\n"
        send_alert("🔒 VPS Network Security Alert", alert_body)

    # 7. Generate Markdown report
    md_report = generate_markdown_report(report)
    report_md = DATA_DIR / f"report_{int(time.time())}.md"
    report_md.write_text(md_report)
    print(f"Markdown report: {report_md}")


def generate_markdown_report(report: dict) -> str:
    md = f"""# VPS Network Topology Analysis Report

**Generated**: {report['timestamp']}

## Security Summary

{report.get('summary', 'N/A')}

## Exposed Services

| Service | Port | Binding | Risk | Notes |
|---------|------|---------|------|-------|
"""
    for svc in report.get("exposed_services", []):
        md += f"| {svc['service']} | {svc['port']} | {svc.get('binding', '?')} | {svc.get('risk', '?')} | {svc.get('reason', '')} |\n"

    md += "\n## Service Dependency Topology\n\n```\n"
    for edge in report.get("topology", []):
        md += f"{edge['from']} --> {edge['to']} ({edge['protocol']}:{edge['port']})\n"
    md += "```\n"

    md += "\n## Configuration Drift\n\n"
    if report.get("drifts"):
        for d in report["drifts"]:
            md += f"- [{d['severity']}] {d['type']}\n"
    else:
        md += "- No drift, baseline stable\n"

    md += "\n## Recommended Actions\n\n"
    for i, rec in enumerate(report.get("recommendations", []), 1):
        md += f"{i}. {rec}\n"

    md += "\n## Suggested iptables Rules\n\n```bash\n"
    for r in report.get("iptables_rules", []):
        md += f"# {r.get('chain', 'INPUT')}\n{r['rule']}\n"
    md += "```\n"

    return md


if __name__ == "__main__":
    main()
```

Schedule analysis every 30 minutes:

```bash
chmod +x /opt/net-discovery/analyze.py
# Analyze every 30 minutes
(crontab -l 2>/dev/null; echo "*/30 * * * * /usr/bin/python3 /opt/net-discovery/analyze.py >> /var/log/net-discovery.log 2>&1") | crontab -
```

---

## 4. Step 3: Automated Security Policy

### 4.1 Baseline Management

The system maintains historical baselines in `/var/db/net-baseline/`:

```bash
# View baseline history
ls -la /var/db/net-baseline/
cat /var/db/net-baseline/latest.json | python3 -m json.tool | head -50
```

### 4.2 One-Click Hardening Script

LLM-generated iptables rules need manual review before execution. The system generates an auditable hardening script:

```bash
vim /opt/net-discovery/harden.sh
```

```bash
#!/bin/bash
# Auto-generated by AI Network Analysis Engine — review before executing
set -euo pipefail

echo "🔒 Applying network hardening policies..."

# Default deny all inbound (unless explicitly allowed)
iptables -w -P INPUT DROP 2>/dev/null || true
iptables -w -P FORWARD DROP 2>/dev/null || true
iptables -w -P OUTPUT ACCEPT 2>/dev/null || true

# Allow loopback
iptables -w -A INPUT -i lo -j ACCEPT

# Allow established connections
iptables -w -A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT

# Allow SSH (consider restricting source IP in production)
# iptables -w -A INPUT -p tcp --dport 22 -s 0.0.0.0/0 -j ACCEPT

# Allow HTTP/HTTPS
iptables -w -A INPUT -p tcp --dport 80 -j ACCEPT
iptables -w -A INPUT -p tcp --dport 443 -j ACCEPT

# Allow ICMP (ping)
iptables -w -A INPUT -p icmp --icmp-type echo-request -j ACCEPT

# Drop broadcast
iptables -w -A INPUT -broadcast -j DROP

# Docker container network isolation reminder
if command -v docker &>/dev/null && docker ps &>/dev/null; then
    echo "💡 Tip: Use Docker custom bridge networks to prevent default bridge exposure"
fi

echo "✅ Basic hardening rules applied"
echo "📋 View rules: iptables -L -n -v"
echo "💾 Persist: iptables-save > /etc/iptables/rules.v4"
```

### 4.3 Rule Persistence

```bash
# Debian/Ubuntu
apt-get install -y iptables-persistent
iptables-save > /etc/iptables/rules.v4
ip6tables-save > /etc/iptables/rules.v6

# RHEL/CentOS
yum install -y iptables-services
service iptables save
```

---

## 5. Advanced: Visual Topology with Mermaid

Generate a Mermaid-format topology diagram that renders beautifully in GitHub, Obsidian, or any Markdown viewer:

```bash
vim /opt/net-discovery/render_topology.py
```

```python
#!/usr/bin/env python3
"""Render LLM analysis results as a Mermaid topology diagram"""
import json
from pathlib import Path
from datetime import datetime

DATA_DIR = Path("/tmp/net-discovery")

def render_mermaid():
    report_files = sorted(DATA_DIR.glob("report_*.json"), reverse=True)
    if not report_files:
        print("No reports found")
        return

    latest = json.loads(report_files[0].read_text())

    mermaid = """```mermaid
graph TB
    subgraph External["🌐 External Network (0.0.0.0/0)"]
        INTERNET(["Internet"])
    end

    subgraph Host["🖥️ Host Machine"]
        SSH(["SSH :22"])
        WEB(["Web :80/:443"])
    end

    subgraph Containers["📦 Docker Containers"]
"""

    for svc in latest.get("exposed_services", []):
        risk_emoji = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}.get(svc.get("risk", ""), "⚪")
        safe_name = svc["service"].replace(" ", "_")
        mermaid += f'        {safe_name}(["{risk_emoji} {svc["service"]}\\n:{svc["port"]}"])\\n'

    mermaid += """    end

    INTERNET --> |"HTTP/HTTPS"| WEB
    INTERNET --> |"SSH"| SSH
"""

    for edge in latest.get("topology", []):
        from_safe = edge["from"].replace(" ", "_")
        to_safe = edge["to"].replace(" ", "_")
        mermaid += f'    {from_safe} -->|"{edge["protocol"]}:{edge["port"]}"| {to_safe}\\n'

    mermaid += "```\n"

    output = DATA_DIR / f"topology_{int(datetime.now().timestamp())}.md"
    output.write_text(mermaid)
    print(f"Mermaid topology saved: {output}")
    print("\n" + mermaid)

if __name__ == "__main__":
    render_mermaid()
```

---

## 6. Advanced: Docker Network Isolation Recommendations

For Docker environments, the LLM also suggests container network segmentation:

```bash
vim /opt/net-discovery/docker_isolation.py
```

```python
#!/usr/bin/env python3
"""Generate Docker network isolation recommendations based on LLM analysis"""
import json
import subprocess
from pathlib import Path

def generate_isolation_networks():
    """Generate recommended Docker network isolation configuration"""
    result = subprocess.run(
        ["docker", "ps", "--format", "{{.Names}}\t{{.Image}}\t{{.Ports}}"],
        capture_output=True, text=True
    )

    containers = {}
    for line in result.stdout.strip().split("\n"):
        parts = line.split("\t")
        if len(parts) >= 3:
            containers[parts[0]] = {"image": parts[1], "ports": parts[2]}

    networks = {
        "public": {"driver": "bridge", "description": "Externally exposed services"},
        "internal": {"driver": "bridge", "description": "Internal service communication"},
        "data": {"driver": "bridge", "description": "Database layer (internal access only)"},
    }

    print("Recommended Docker Network Isolation Scheme:\n")
    for name, config in networks.items():
        print(f"  Network: {name}")
        print(f"    Driver: {config['driver']}")
        print(f"    Purpose: {config['description']}")
        print()

    print("Assign containers to networks:")
    print("  public  → Nginx, API gateways, etc.")
    print("  internal → Business logic containers")
    print("  data    → PostgreSQL, Redis, MongoDB (no direct port exposure)")
    print()

    compose = """
# Recommended network isolation in docker-compose
networks:
  public:
    driver: bridge
  internal:
    driver: bridge
  data:
    driver: bridge
    internal: true  # No external network access
"""
    print(compose)

if __name__ == "__main__":
    generate_isolation_networks()
```

---

## 7. Real-World Scenario: Redis Exposed to Public Internet

A user runs these services on their VPS:
- Nginx (reverse proxy)
- PostgreSQL (application database)
- Redis (cache)
- MinIO (object storage)

After collection, the LLM analysis outputs:

```json
{
  "exposed_services": [
    {
      "service": "PostgreSQL",
      "port": 5432,
      "binding": "0.0.0.0",
      "risk": "HIGH",
      "reason": "Database port directly bound to 0.0.0.0 — any public IP can attempt connection"
    },
    {
      "service": "Redis",
      "port": 6379,
      "binding": "0.0.0.0",
      "risk": "HIGH",
      "reason": "Redis has no default authentication; public exposure is easily exploited by ransomware (e.g., RedisGremlin)"
    },
    {
      "service": "MinIO Console",
      "port": 9001,
      "binding": "0.0.0.0",
      "risk": "MEDIUM",
      "reason": "Admin panel exposed to public internet; requires password but should be internal-only"
    }
  ],
  "iptables_rules": [
    {
      "chain": "INPUT",
      "rule": "iptables -A INPUT -p tcp --dport 5432 -s 172.17.0.0/16 -j ACCEPT"
    },
    {
      "chain": "INPUT",
      "rule": "iptables -A INPUT -p tcp --dport 6379 -s 172.17.0.0/16 -j DROP"
    },
    {
      "chain": "INPUT",
      "rule": "iptables -A INPUT -p tcp --dport 9001 -s 127.0.0.1 -j ACCEPT"
    }
  ],
  "summary": "2 HIGH-risk exposed services detected (PostgreSQL and Redis bound to 0.0.0.0). Immediate restriction to Docker internal network access is recommended.",
  "recommendations": [
    "Change bind-address for PostgreSQL and Redis to 127.0.0.1 or Docker internal IP",
    "Set requirepass on Redis",
    "Access MinIO Console only through reverse proxy, not port 9001 directly",
    "Enable fail2ban for SSH protection"
  ]
}
```

After the Telegram alert, the operator confirms and executes:

```bash
# Immediately block high-risk ports
iptables -A INPUT -p tcp --dport 5432 -s 172.17.0.0/16 -j ACCEPT
iptables -A INPUT -p tcp --dport 5432 -j DROP

iptables -A INPUT -p tcp --dport 6379 -s 172.17.0.0/16 -j ACCEPT
iptables -A INPUT -p tcp --dport 6379 -j DROP

# Add Redis password
echo "requirepass $(openssl rand -base64 32)" >> /etc/redis/redis.conf
systemctl restart redis

# Persist rules
iptables-save > /etc/iptables/rules.v4
```

---

## 8. Cost & Resource Analysis

| Component | Resource Usage | Notes |
|-----------|---------------|-------|
| Ollama + Qwen2.5 7B | ~4GB RAM | Use `phi:mini` (~1GB) if VPS memory is constrained |
| Data collection script | < 50MB RAM | Only runs system commands, minimal footprint |
| Analysis engine | < 200MB RAM | Python script, nearly idle when not running |
| Disk usage | ~50MB/month | Collected data and baseline files |

**Total cost**: A single VPS with Ollama support (2GB+ RAM), no additional cloud service fees.

---

## 9. Security Best Practices

1. **Start in observation mode** — for the first 2 weeks, only generate reports without applying any rules. Let the LLM learn your normal patterns.
2. **Baselines are dynamic** — manually update the baseline after each legitimate change (`cp report_xxx.json /var/db/net-baseline/latest.json`).
3. **Don't blindly apply all iptables rules** — LLM-generated rules need human review, especially default DROP policies that could lock you out of SSH.
4. **Always restrict sensitive ports by source IP** — SSH, database ports should only accept connections from known IP ranges.
5. **Export reports regularly for archival** — `tar czf net-baseline-archive-$(date +%Y%m%d).tar.gz /var/db/net-baseline/`

---

## Summary

This AI network topology discovery system does three things:

1. **See** — auto-discover all ports, connections, and service dependencies; generate visual topology
2. **Understand** — LLM analyzes risk levels and infers least-privilege policies
3. **Guard** — continuously monitor for drift, alert immediately on anomalies

Its value isn't replacing existing monitoring tools (Prometheus, Zabbix) — it's using the LLM's semantic understanding to turn scattered network state data into actionable security insights. All inference runs locally; your network topology and configuration data never leave your server.

**Get started**: Run `/opt/net-discovery/collect.sh` on your VPS and see what the LLM discovers that you didn't know.
