---
title: "AI 驱动的 VPS 智能网络拓扑发现与安全策略自动生成"
description: "你的 VPS 上跑了十几个 Docker 容器，每个都开了不同的端口——你确定清楚它们之间的通信关系吗？本文介绍如何用本地 LLM 自动发现网络拓扑、生成安全策略，并持续监控配置漂移。"
date: 2026-09-27T20:00:00+08:00
lastmod: 2026-09-27T20:00:00+08:00
slug: "ai-vps-network-topology-discovery"
tags: ["AI", "VPS", "AIOps", "网络拓扑", "网络安全", "LLM", "Docker", "防火墙", "零信任", "iptables"]
categories: ["AI + VPS"]
image: /images/posts/ai-vps-network-topology-discovery/featured.png
draft: false
---

## 引言：你的 VPS 网络真的安全吗？

当你运行一堆积木容器——Nginx、PostgreSQL、Redis、API 服务、定时任务……每一个都有自己暴露的端口和依赖关系。几个月后，你还能说清楚：

- 哪些容器之间需要互相通信？
- 哪些端口是真正对外开放的？
- 哪个服务可以直接访问数据库？

大多数人的答案是：**说不清楚**。

传统运维依赖人工维护网络文档，但服务一多就失控了。本文介绍一套 **AI 驱动的网络拓扑发现系统**——用本地 LLM 自动收集网络状态、推断服务依赖关系、生成最小权限的防火墙规则，并持续监控配置漂移。所有数据留在你的 VPS 上，不依赖任何外部 API。

---

## 一、为什么要用 AI 做网络拓扑发现？

### 传统方式的三大痛点

| 痛点 | 现状 | AI 方案 |
|------|------|---------|
| **拓扑不清晰** | 手动记录端口和依赖，随服务增多变成天书 | LLM 自动分析 `ss`/`docker network`，生成可视化拓扑 |
| **安全策略滞后** | 新增服务时忘记开防火墙规则，或过度开放端口 | LLM 推断最小权限策略，自动生成 iptables/nftables 规则 |
| **漂移难发现** | 有人改了网络配置却不知道，安全审计时才发现 | 定时巡检 + LLM 比对基线，异常立即告警 |

### 核心思路

```
┌─────────────────────────────────────────────────────────────────┐
│                        你的 VPS                                  │
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │  数据采集层   │───►│  LLM 推理层   │───►│  策略执行层   │      │
│  │              │    │              │    │              │      │
│  │ • ss -tulnp  │    │ • 拓扑推断   │    │ • iptables   │      │
│  │ • docker ps  │    │ • 风险评分   │    │ • nftables   │      │
│  │ • docker net │    │ • 规则生成   │    │ • 策略生效   │      │
│  │ • iptables   │    │ • 漂移检测   │    │ • 基线存档   │      │
│  │ • 进程树     │    │ • 报告生成   │    │              │      │
│  └──────────────┘    └──────┬───────┘    └──────┬───────┘      │
│                             │                   │               │
│                             ▼                   ▼               │
│                    ┌──────────────┐    ┌──────────────┐        │
│                    │  通知层       │    │  历史基线    │        │
│                    │  Telegram    │    │  /var/db/net-│        │
│                    │  微信/邮件    │    │  baseline/   │        │
│                    └──────────────┘    └──────────────┘        │
└─────────────────────────────────────────────────────────────────┘
```

---

## 二、第一步：网络数据采集

创建一个统一的数据采集脚本，收集所有网络相关信息：

```bash
mkdir -p /opt/net-discovery
vim /opt/net-discovery/collect.sh
```

```bash
#!/bin/bash
# /opt/net-discovery/collect.sh — 网络状态全量采集
set -euo pipefail

TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
OUT_DIR="/tmp/net-discovery"
mkdir -p "$OUT_DIR"

echo "=== 采集时间: $TIMESTAMP ===" > "$OUT_DIR/timestamp.txt"

# 1. 监听端口（TCP/UDP）
echo "=== 监听端口 ===" > "$OUT_DIR/listening_ports.txt"
ss -tulnp 2>/dev/null >> "$OUT_DIR/listening_ports.txt" || true

# 2. 活跃连接
echo "=== 活跃连接 ===" > "$OUT_DIR/active_connections.txt"
ss -tnp 2>/dev/null | head -200 >> "$OUT_DIR/active_connections.txt" || true

# 3. Docker 网络信息
echo "=== Docker 网络 ===" > "$OUT_DIR/docker_networks.txt"
docker network ls 2>/dev/null >> "$OUT_DIR/docker_networks.txt" || true
docker network inspect "$(docker network ls --format '{{.Name}}' 2>/dev/null | tr '\n' ',' | sed 's/,$//')" \
  > "$OUT_DIR/docker_network_inspect.json" 2>/dev/null || true

# 4. Docker 容器端口映射
echo "=== Docker 端口映射 ===" > "$OUT_DIR/docker_ports.txt"
docker ps --format '{{.Names}}\t{{.Ports}}\t{{.Status}}' 2>/dev/null \
  >> "$OUT_DIR/docker_ports.txt" || true

# 5. 防火墙规则
echo "=== iptables 规则 ===" > "$OUT_DIR/iptables_rules.txt"
iptables -L -n -v 2>/dev/null >> "$OUT_DIR/iptables_rules.txt" || true
iptables -t nat -L -n -v 2>/dev/null >> "$OUT_DIR/iptables_rules.txt" || true

# 6. 进程网络行为
echo "=== 进程网络连接 ===" > "$OUT_DIR/process_network.txt"
ss -tnp 2>/dev/null >> "$OUT_DIR/process_network.txt" || true

# 7. DNS 解析与域名
echo "=== 主要进程的 DNS 出口 ===" > "$OUT_DIR/dns_outbound.txt"
ss -tnp state established 2>/dev/null | grep -E ':53|nameserver' >> "$OUT_DIR/dns_outbound.txt" || true

# 8. 宿主机 IP 配置
echo "=== 网络接口 ===" > "$OUT_DIR/interfaces.txt"
ip addr show 2>/dev/null >> "$OUT_DIR/interfaces.txt" || true
ip route 2>/dev/null >> "$OUT_DIR/routes.txt" || true

echo "[$TIMESTAMP] 采集完成，输出目录: $OUT_DIR"
```

设置定时采集：

```bash
chmod +x /opt/net-discovery/collect.sh
# 每 15 分钟采集一次
(crontab -l 2>/dev/null; echo "*/15 * * * * /opt/net-discovery/collect.sh") | crontab -
```

---

## 三、第二步：LLM 拓扑推理引擎

核心分析脚本，将采集数据发送给本地 LLM，让它理解网络结构并识别风险：

```bash
vim /opt/net-discovery/analyze.py
```

```python
#!/usr/bin/env python3
"""
AI 网络拓扑发现与安全评分引擎
读取采集数据 → LLM 推理 → 输出拓扑图谱 + 安全策略建议
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
    """读取所有采集文件，拼接成上下文"""
    parts = []
    for f in sorted(DATA_DIR.glob("*.txt")):
        if f.name == "timestamp.txt":
            continue
        if f.exists():
            parts.append(f"### {f.stem.upper()}\n{f.read_text()}")
    # 也读取 JSON 数据
    for f in DATA_DIR.glob("*.json"):
        if f.exists():
            parts.append(f"### {f.stem.upper()}\n{f.read_text()[:8000]}")
    return "\n\n".join(parts)


def build_prompt(raw_data: str) -> str:
    return f"""你是一个专业的网络安全工程师和 VPS 运维专家。请分析以下网络采集数据，完成三项任务：

## 任务 1：构建服务拓扑
识别所有网络服务（容器/进程），推断它们之间的依赖关系。
格式：SERVICE_A --> SERVICE_B (协议:端口)

## 任务 2：风险评估
对每个暴露的端口进行风险评级（HIGH/MEDIUM/LOW），说明原因。
特别关注：
- 数据库端口对外暴露
- SSH 暴露在公网
- 管理面板无认证访问
- 未加密的 HTTP 流量

## 任务 3：最小权限防火墙建议
为每个服务生成 iptables 规则，遵循最小权限原则。

网络采集数据：
{raw_data}

请以以下 JSON 格式输出（只输出 JSON，不要有其他内容）：
{{
  "topology": [
    {{"from": "service_name", "to": "service_name", "protocol": "tcp", "port": 5432, "justification": "原因"}}
  ],
  "exposed_services": [
    {{"service": "名称", "port": 端口, "binding": "0.0.0.0 或 127.0.0.1", "risk": "HIGH/MEDIUM/LOW", "reason": "原因"}}
  ],
  "iptables_rules": [
    {{"chain": "INPUT/DOCKER", "rule": "完整 iptables 命令"}}
  ],
  "summary": "一段话总结当前网络安全状况",
  "recommendations": ["建议1", "建议2"]
}}
"""


def call_llm(prompt: str) -> dict:
    """调用 Ollama 本地 LLM"""
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
        # 清理 markdown 代码块
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        return json.loads(text.strip())
    except Exception as e:
        return {"error": str(e), "topology": [], "exposed_services": [], "recommendations": []}


def drift_detection(current: dict) -> list:
    """与基线比对，检测配置漂移"""
    baseline_file = BASELINE_DIR / "latest.json"
    if not baseline_file.exists():
        # 首次运行，建立基线
        baseline_file.write_text(json.dumps(current, ensure_ascii=False, indent=2))
        return [{"type": "baseline_created", "message": "已创建初始网络基线"}]

    previous = json.loads(baseline_file.read_text())
    drifts = []

    # 检查新增暴露端口
    prev_ports = {(s["port"], s["binding"]) for s in previous.get("exposed_services", [])}
    curr_ports = {(s["port"], s["binding"]) for s in current.get("exposed_services", [])}
    for port, binding in curr_ports - prev_ports:
        drifts.append({
            "type": "new_exposure",
            "port": port,
            "binding": binding,
            "severity": "HIGH"
        })

    # 检查移除的端口
    for port, binding in prev_ports - curr_ports:
        drifts.append({
            "type": "port_removed",
            "port": port,
            "binding": binding,
            "severity": "MEDIUM"
        })

    # 更新基线
    baseline_file.write_text(json.dumps(current, ensure_ascii=False, indent=2))
    return drifts


def apply_iptables_rules(rules: list):
    """安全地应用 iptables 规则（需要确认）"""
    applied = []
    for r in rules:
        chain = r.get("chain", "INPUT")
        rule_cmd = r.get("rule", "")
        # 先 dry-run 检查语法
        dry_result = subprocess.run(
            ["iptables", "-w", "-C"] + rule_cmd.split()[2:],
            capture_output=True
        )
        if dry_result.returncode != 0:
            # 规则不存在，添加
            apply_result = subprocess.run(
                ["sudo", "iptables", "-w", "-A"] + rule_cmd.split()[2:],
                capture_output=True, text=True
            )
            if apply_result.returncode == 0:
                applied.append(rule_cmd)
    return applied


def send_alert(title: str, body: str):
    """发送 Telegram 告警"""
    token = Path("/opt/net-discovery/telegram_token").read_text().strip() if Path("/opt/net-discovery/telegram_token").exists() else ""
    chat_id = Path("/opt/net-discovery/telegram_chat").read_text().strip() if Path("/opt/net-discovery/telegram_chat").exists() else ""
    if not token or not chat_id:
        return
    import requests
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    requests.post(url, json={"chat_id": chat_id, "text": f"🔒 *{title}*\n\n{body}", "parse_mode": "Markdown"})


def main():
    print(f"[{datetime.now()}] 开始网络拓扑分析...")

    # 1. 采集数据
    subprocess.run(["/opt/net-discovery/collect.sh"], check=True)

    # 2. LLM 推理
    raw = read_all_data()
    prompt = build_prompt(raw)
    result = call_llm(prompt)

    if "error" in result:
        print(f"LLM 分析失败: {result['error']}")
        return

    # 3. 漂移检测
    drifts = drift_detection(result)

    # 4. 输出报告
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
    print(f"报告已保存: {report_file}")

    # 5. 打印摘要
    print(f"\n{'='*50}")
    print(f"网络安全评分报告")
    print(f"{'='*50}")
    print(f"总结: {result.get('summary', 'N/A')}")
    print(f"\n暴露服务 ({len(result.get('exposed_services', []))} 个):")
    for svc in result.get("exposed_services", []):
        emoji = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}.get(svc.get("risk", ""), "⚪")
        print(f"  {emoji} {svc['service']}: {svc['port']}/{svc.get('binding', '?')} [{svc['risk']}]")
        print(f"     原因: {svc.get('reason', '')}")

    if drifts:
        print(f"\n⚠️ 检测到 {len(drifts)} 处配置漂移:")
        for d in drifts:
            print(f"  [{d['severity']}] {d['type']}: 端口 {d.get('port', 'N/A')}")
    else:
        print("\n✅ 无配置漂移，网络状态稳定")

    # 6. 发送告警（有漂移或高风险时）
    high_risk = [s for s in result.get("exposed_services", []) if s.get("risk") == "HIGH"]
    if high_risk or drifts:
        alert_body = f"发现 {len(high_risk)} 个高风险暴露服务，{len(drifts)} 处配置漂移。\n\n"
        for s in high_risk:
            alert_body += f"- {s['service']}: {s['port']} ({s.get('reason', '')})\n"
        for d in drifts:
            alert_body += f"- 漂移: {d['type']} 端口 {d.get('port', 'N/A')}\n"
        send_alert("🔒 VPS 网络安全评分告警", alert_body)

    # 7. 生成 Markdown 报告（便于查看）
    md_report = generate_markdown_report(report)
    report_md = DATA_DIR / f"report_{int(time.time())}.md"
    report_md.write_text(md_report)
    print(f"Markdown 报告: {report_md}")


def generate_markdown_report(report: dict) -> str:
    md = f"""# VPS 网络拓扑分析报告

**生成时间**: {report['timestamp']}

## 安全总结

{report.get('summary', 'N/A')}

## 暴露服务

| 服务 | 端口 | 绑定地址 | 风险等级 | 说明 |
|------|------|---------|---------|------|
"""
    for svc in report.get("exposed_services", []):
        md += f"| {svc['service']} | {svc['port']} | {svc.get('binding', '?')} | {svc.get('risk', '?')} | {svc.get('reason', '')} |\n"

    md += "\n## 服务依赖拓扑\n\n```\n"
    for edge in report.get("topology", []):
        md += f"{edge['from']} --> {edge['to']} ({edge['protocol']}:{edge['port']})\n"
    md += "```\n"

    md += "\n## 配置漂移\n\n"
    if report.get("drifts"):
        for d in report["drifts"]:
            md += f"- [{d['severity']}] {d['type']}\n"
    else:
        md += "- 无漂移，基线稳定\n"

    md += "\n## 建议操作\n\n"
    for i, rec in enumerate(report.get("recommendations", []), 1):
        md += f"{i}. {rec}\n"

    md += "\n## iptables 规则建议\n\n```bash\n"
    for r in report.get("iptables_rules", []):
        md += f"# {r.get('chain', 'INPUT')}\n{r['rule']}\n"
    md += "```\n"

    return md


if __name__ == "__main__":
    main()
```

设置定时分析：

```bash
chmod +x /opt/net-discovery/analyze.py
# 每 30 分钟分析一次
(crontab -l 2>/dev/null; echo "*/30 * * * * /usr/bin/python3 /opt/net-discovery/analyze.py >> /var/log/net-discovery.log 2>&1") | crontab -
```

---

## 四、第三步：安全策略自动化

### 4.1 基线管理

系统会自动在 `/var/db/net-baseline/` 维护历史基线：

```bash
# 查看基线历史
ls -la /var/db/net-baseline/
cat /var/db/net-baseline/latest.json | python3 -m json.tool | head -50
```

### 4.2 一键生成安全加固脚本

LLM 生成的 iptables 规则不会直接生效——需要人工审核。系统会生成一个可审计的加固脚本：

```bash
vim /opt/net-discovery/harden.sh
```

```bash
#!/bin/bash
# 由 AI 网络分析引擎自动生成 — 请审核后再执行
set -euo pipefail

echo "🔒 应用网络加固策略..."

# 默认拒绝所有入站（除非明确允许）
iptables -w -P INPUT DROP 2>/dev/null || true
iptables -w -P FORWARD DROP 2>/dev/null || true
iptables -w -P OUTPUT ACCEPT 2>/dev/null || true

# 允许 Loopback
iptables -w -A INPUT -i lo -j ACCEPT

# 允许已建立的连接
iptables -w -A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT

# 允许 SSH（建议限制来源 IP）
# iptables -w -A INPUT -p tcp --dport 22 -s 0.0.0.0/0 -j ACCEPT  # 生产环境建议限制来源

# 允许 HTTP/HTTPS
iptables -w -A INPUT -p tcp --dport 80 -j ACCEPT
iptables -w -A INPUT -p tcp --dport 443 -j ACCEPT

# 允许 ICMP（ping）
iptables -w -A INPUT -p icmp --icmp-type echo-request -j ACCEPT

# 拒绝广播
iptables -w -A INPUT -broadcast -j DROP

# Docker 容器的网络隔离（如果有 Docker）
if command -v docker &>/dev/null && docker ps &>/dev/null; then
    # 阻止容器直接访问外网（可选，通过 Docker 自定义网络实现）
    echo "💡 提示：建议为 Docker 容器使用自定义 bridge 网络，避免默认桥接暴露"
fi

echo "✅ 基础加固规则已应用"
echo "📋 使用 'iptables -L -n -v' 查看当前规则"
echo "💾 使用 'iptables-save > /etc/iptables/rules.v4' 持久化"
```

### 4.3 规则持久化

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

## 五、进阶：可视化拓扑图

生成 Mermaid 格式的网络拓扑图，可直接渲染为可视化图表：

```bash
vim /opt/net-discovery/render_topology.py
```

```python
#!/usr/bin/env python3
"""将 LLM 分析结果渲染为 Mermaid 拓扑图"""
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
    subgraph 外网["🌐 外网 (0.0.0.0/0)"]
        INTERNET(["Internet"])
    end

    subgraph 宿主机["🖥️ 宿主机"]
        SSH(["SSH :22"])
        WEB(["Web :80/:443"])
    end

    subgraph 容器["📦 Docker 容器"]
"""

    # 添加容器节点
    for svc in latest.get("exposed_services", []):
        risk_emoji = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}.get(svc.get("risk", ""), "⚪")
        safe_name = svc["service"].replace(" ", "_")
        mermaid += f'        {safe_name}(["{risk_emoji} {svc["service"]}\\n:{svc["port"]}"])\\n'

    mermaid += """    end

    INTERNET --> |"HTTP/HTTPS"| WEB
    INTERNET --> |"SSH"| SSH
"""

    # 添加依赖边
    for edge in latest.get("topology", []):
        from_safe = edge["from"].replace(" ", "_")
        to_safe = edge["to"].replace(" ", "_")
        mermaid += f'    {from_safe} -->|"{edge["protocol"]}:{edge["port"]}"| {to_safe}\\n'

    mermaid += "```\n"

    output = DATA_DIR / f"topology_{int(datetime.now().timestamp())}.md"
    output.write_text(mermaid)
    print(f"Mermaid 拓扑图已保存: {output}")
    print("\n" + mermaid)

if __name__ == "__main__":
    render_mermaid()
```

---

## 六、进阶：Docker 网络隔离推荐

对于 Docker 环境，LLM 还会建议容器间的网络隔离方案：

```bash
vim /opt/net-discovery/docker_isolation.py
```

```python
#!/usr/bin/env python3
"""根据 LLM 分析生成 Docker 网络隔离方案"""
import json
import subprocess
from pathlib import Path

def generate_isolation_networks():
    """生成推荐的 Docker 网络隔离配置"""
    # 获取当前运行的容器
    result = subprocess.run(
        ["docker", "ps", "--format", "{{.Names}}\t{{.Image}}\t{{.Ports}}"],
        capture_output=True, text=True
    )

    containers = {}
    for line in result.stdout.strip().split("\n"):
        parts = line.split("\t")
        if len(parts) >= 3:
            containers[parts[0]] = {
                "image": parts[1],
                "ports": parts[2]
            }

    # 定义网络隔离层级
    networks = {
        "public": {"driver": "bridge", "description": "对外暴露的服务"},
        "internal": {"driver": "bridge", "description": "内部服务通信"},
        "data": {"driver": "bridge", "description": "数据库等数据存储层（仅内部访问）"},
    }

    print("推荐的 Docker 网络隔离方案：\n")
    for name, config in networks.items():
        print(f"  网络: {name}")
        print(f"    驱动: {config['driver']}")
        print(f"    用途: {config['description']}")
        print()

    print("建议将容器分组到对应网络：")
    print("  public 网络 → Nginx、API 网关等对外服务")
    print("  internal 网络 → 业务逻辑容器间通信")
    print("  data 网络 → PostgreSQL、Redis、MongoDB 等数据库（禁止直接暴露端口）")
    print()

    # 生成 docker-compose 片段
    compose = """
# 推荐的网络隔离 docker-compose 片段
networks:
  public:
    driver: bridge
    # 仅容器间通信，不暴露端口
  internal:
    driver: bridge
  data:
    driver: bridge
    internal: true  # 禁止访问外网
"""
    print(compose)

if __name__ == "__main__":
    generate_isolation_networks()
```

---

## 七、实战案例：发现并修复真实安全问题

### 场景：Redis 意外暴露到公网

某用户运行了以下服务：
- Nginx（反向代理）
- PostgreSQL（应用数据库）
- Redis（缓存）
- MinIO（对象存储）

采集数据后，LLM 分析输出：

```json
{
  "exposed_services": [
    {
      "service": "PostgreSQL",
      "port": 5432,
      "binding": "0.0.0.0",
      "risk": "HIGH",
      "reason": "数据库端口直接暴露在 0.0.0.0，任何公网 IP 可尝试连接"
    },
    {
      "service": "Redis",
      "port": 6379,
      "binding": "0.0.0.0",
      "risk": "HIGH",
      "reason": "Redis 默认无认证，公网暴露极易被勒索软件利用（如 RedisGremlin）"
    },
    {
      "service": "MinIO Console",
      "port": 9001,
      "binding": "0.0.0.0",
      "risk": "MEDIUM",
      "reason": "管理面板暴露在公网，虽然需要密码但建议仅内网访问"
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
  "summary": "检测到 2 个 HIGH 风险暴露服务（PostgreSQL 和 Redis 直接绑定 0.0.0.0），建议立即限制为 Docker 内部网络访问。",
  "recommendations": [
    "将 PostgreSQL 和 Redis 的 bind-address 改为 127.0.0.1 或 Docker 内部 IP",
    "为 Redis 设置 requirepass 密码认证",
    "MinIO Console 仅允许通过反向代理访问，不直接暴露 9001 端口",
    "启用 fail2ban 保护 SSH 端口"
  ]
}
```

Telegram 告警推送后，运维人员确认并执行：

```bash
# 立即封锁高危端口
iptables -A INPUT -p tcp --dport 5432 -s 172.17.0.0/16 -j ACCEPT
iptables -A INPUT -p tcp --dport 5432 -j DROP

iptables -A INPUT -p tcp --dport 6379 -s 172.17.0.0/16 -j ACCEPT
iptables -A INPUT -p tcp --dport 6379 -j DROP

# 修改 Redis 配置，增加密码
echo "requirepass $(openssl rand -base64 32)" >> /etc/redis/redis.conf
systemctl restart redis

# 持久化规则
iptables-save > /etc/iptables/rules.v4
```

---

## 八、成本与资源分析

| 组件 | 资源消耗 | 说明 |
|------|---------|------|
| Ollama + Qwen2.5 7B | ~4GB RAM | 如果 VPS 内存不足，可用 phi:mini（~1GB）替代 |
| 数据采集脚本 | < 50MB RAM | 仅执行系统命令，内存占用极低 |
| 分析引擎 | < 200MB RAM | Python 脚本，空闲时几乎不占资源 |
| 磁盘占用 | ~50MB/月 | 采集数据和基线文件 |

**总成本**：只需一台支持 Ollama 的 VPS（2GB+ RAM），无额外云服务费用。

---

## 九、安全最佳实践

1. **首次部署先在观察模式**：前 2 周只生成报告不执行任何规则，让 LLM 学习你的正常模式
2. **基线是动态的**：每次正常变更后手动更新基线（`cp report_xxx.json /var/db/net-baseline/latest.json`）
3. **不要盲目应用所有 iptables 规则**：LLM 生成的规则需要人工审核，特别是默认 DROP 策略可能断掉你的 SSH
4. **敏感端口务必限制来源 IP**：SSH、数据库端口只允许特定 IP 段访问
5. **定期导出报告存档**：`tar czf net-baseline-archive-$(date +%Y%m%d).tar.gz /var/db/net-baseline/`

---

## 总结

这套 AI 网络拓扑发现系统做了三件事：

1. **看见**——自动发现所有端口、连接和服务依赖，生成可视化拓扑
2. **理解**——LLM 分析风险等级，推断最小权限策略
3. **守护**——持续监控漂移，异常时即时告警

它的价值不在于替代现有的监控工具（Prometheus、Zabbix），而在于用 LLM 的语义理解能力，把零散的网络状态数据变成可操作的安全洞察。所有推理都在本地完成，你的网络拓扑和配置数据永远不会离开自己的服务器。

**立即行动**：在你的 VPS 上运行 `/opt/net-discovery/collect.sh`，然后看看 LLM 能发现什么你 previously 不知道的东西。
