---
title: "AI + VPS: 基于本地大模型的智能流量异常检测与 WAF 策略自动生成"
description: "用本地 Ollama + Qwen2.5 分析 Nginx/Cloudflare 流量日志，自动识别 CC 攻击、SQL 注入、路径遍历等异常模式，并一键生成 Crowdstrike/NGINX WAF 防护规则，让安全运维从人工研判走向 AI 驱动"
date: 2026-09-24T21:30:00+08:00
lastmod: 2026-09-24T21:30:00+08:00
slug: "ai-vps-llm-traffic-anomaly-waf-auto"
image: /images/posts/ai-vps-llm-traffic-anomaly-waf-auto/featured.png
tags: ["AI", "VPS", "WAF", "流量分析", "异常检测", "Ollama", "Qwen2.5", "Nginx", "网络安全", "自动化"]
categories: ["AI 运维"]
aliases: [/zh/post/ai-vps-llm-traffic-anomaly-waf-auto/]
---

## 引言

你的 VPS 网站最近是否遭遇过突发的流量洪峰？也许是合法的推广活动带来了正常访问增长，但更可能是恶意的 CC 攻击或 SQL 注入正在侵蚀你的服务器资源。

传统的安全监控依赖人工配置规则：针对已知攻击特征写正则、设置阈值告警、手动封禁 IP。问题在于——攻击者的手段不断演变，静态规则很快过时；而每当出现新型攻击模式，运维人员需要手动分析日志、编写规则、测试效果，响应周期以小时甚至天计。

**本地大语言模型（LLM）的出现改变了这一局面。** 通过在 VPS 上部署 Ollama + Qwen2.5，你可以构建一套完全私有化的智能流量分析系统：它能在本地解析流量日志，自动识别异常模式（CC 攻击、SQL 注入、路径遍历、爬虫滥用等），并直接生成可用的 WAF 防护规则，无需将任何数据上传到云端。

本文将带你从零搭建这套系统，实现**日志采集 → AI 分析 → 规则生成 → 自动生效**的完整闭环。

---

## 架构概览

```
┌─────────────────────────────────────────────────────────────┐
│                     VPS 本地环境                              │
│                                                             │
│  ┌──────────┐   ┌──────────────┐   ┌──────────────────┐    │
│  │  Nginx   │──▶│  Log Parser  │──▶│   Ollama +       │    │
│  │  Access  │   │  (awk/Python)│   │   Qwen2.5        │    │
│  │  Log     │   │              │   │  (本地 LLM)       │    │
│  └──────────┘   └──────────────┘   └────────┬─────────┘    │
│                                             │               │
│                              ┌──────────────▼─────────┐     │
│                              │   AI 分析引擎            │     │
│                              │  • 异常模式检测          │     │
│                              │  • 攻击分类              │     │
│                              │  • 风险评分              │     │
│                              └──────────────┬─────────┘     │
│                                             │               │
│                    ┌────────────────────────┼────────┐      │
│                    │                        │        │      │
│           ┌────────▼────────┐   ┌──────────▼──┐ ┌────▼────┐ │
│           │ WAF 规则生成器   │   │  IP 封禁引擎 │ │ Telegram │ │
│           │ (nginx.conf)    │   │  (fail2ban) │ │ 告警     │ │
│           └─────────────────┘   └─────────────┘ └──────────┘ │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 第一步：部署本地 LLM 服务

### 安装 Ollama

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

### 拉取 Qwen2.5 模型

```bash
# 7B 版本 — 适合 4GB+ RAM 的 VPS
ollama pull qwen2.5:7b

# 如果内存紧张，使用 3B 版本
# ollama pull qwen2.5:3b
```

### 验证运行

```bash
ollama run qwen2.5:7b "一句话说明你是什么模型"
```

---

## 第二步：日志采集与预处理

Nginx 默认访问日志格式通常如下：

```
192.168.1.100 - - [24/Sep/2026:14:30:00 +0800] "GET /api/users?id=1 OR 1=1 HTTP/1.1" 403 150 "-" "Mozilla/5.0"
```

我们编写一个 Python 日志解析器，提取关键字段：

```python
#!/usr/bin/env python3
"""VPS 流量日志解析器 — 提取结构化字段供 LLM 分析"""

import re
import json
from datetime import datetime
from collections import defaultdict

# Nginx combined log format 正则
LOG_PATTERN = re.compile(
    r'(?P<ip>[\d.:]+)\s+-\s+(?P<user>\S+)\s+'
    r'\[(?P<time>[^\]]+)\]\s+'
    r'"(?P<method>\S+)\s+(?P<path>\S+)\s+(?P<proto>[^"]+)"\s+'
    r'(?P<status>\d+)\s+(?P<size>\d+)\s+'
    r'"(?P<referer>[^"]+)"\s+'
    r'"(?P<ua>[^"]+)"'
)

def parse_log_line(line):
    m = LOG_PATTERN.match(line)
    if not m:
        return None
    d = m.groupdict()
    d['status'] = int(d['status'])
    d['size'] = int(d['size'])
    d['timestamp'] = datetime.strptime(d['time'], '%d/%b/%Y:%H:%M:%S %z')
    return d

def analyze_window(log_path, window_minutes=5):
    """按时间窗口分析日志，返回统计摘要"""
    entries = []
    with open(log_path) as f:
        for line in f:
            entry = parse_log_line(line.strip())
            if entry:
                entries.append(entry)

    if not entries:
        return None

    # 按 IP 聚合
    ip_stats = defaultdict(lambda: {
        'count': 0, 'statuses': defaultdict(int),
        'paths': set(), 'uas': set()
    })
    for e in entries:
        ip = e['ip']
        ip_stats[ip]['count'] += 1
        ip_stats[ip]['statuses'][e['status']] += 1
        ip_stats[ip]['paths'].add(e['path'])
        ip_stats[ip]['uas'].add(e['ua'][:50])

    # 提取可疑模式
    suspicious_paths = []
    sql_keywords = ['OR 1=1', 'UNION SELECT', "' OR '", '--', ';DROP', '1=1']
    traversal_keywords = ['../', '..\\', '/etc/passwd', '/proc/']

    for e in entries:
        path_upper = e['path'].upper()
        for kw in sql_keywords:
            if kw.upper() in path_upper:
                suspicious_paths.append({
                    'type': 'sql_injection', 'ip': e['ip'],
                    'path': e['path'], 'time': str(e['timestamp'])
                })
                break
        for kw in traversal_keywords:
            if kw in e['path']:
                suspicious_paths.append({
                    'type': 'path_traversal', 'ip': e['ip'],
                    'path': e['path'], 'time': str(e['timestamp'])
                })
                break

    # 高频率 IP 检测
    high_freq_ips = {ip: s for ip, s in ip_stats.items()
                     if s['count'] > 100}

    return {
        'total_requests': len(entries),
        'unique_ips': len(ip_stats),
        'status_distribution': {k: sum(v['statuses'].values())
                                for k, v in ip_stats.items()},
        'high_freq_ips': high_freq_ips,
        'suspicious_paths': suspicious_paths[:20],
        'sample_entries': entries[-10:]  # 最近 10 条
    }

if __name__ == '__main__':
    import sys
    result = analyze_window(sys.argv[1] if len(sys.argv) > 1
                            else '/var/log/nginx/access.log')
    print(json.dumps(result, indent=2, ensure_ascii=False))
```

---

## 第三步：构建 AI 分析引擎

这是系统的核心——用 Qwen2.5 分析流量摘要，识别攻击模式并生成 WAF 规则。

```python
#!/usr/bin/env python3
"""AI 流量分析与 WAF 规则生成器"""

import json
import subprocess
import sys

OLLAMA_URL = "http://localhost:11434"
MODEL = "qwen2.5:7b"

ANALYSIS_PROMPT = """你是一个专业的网络安全分析师。请分析以下 VPS 流量数据，识别潜在的安全威胁，并生成对应的 WAF 防护规则。

## 流量摘要
{traffic_summary}

## 请完成以下任务：

### 1. 威胁识别
列出检测到的所有异常模式，包括：
- 攻击类型（SQL 注入/CC 攻击/路径遍历/爬虫滥用等）
- 涉及的主要 IP
- 攻击强度（低/中/高）
- 影响范围

### 2. WAF 规则生成
为每种攻击类型生成可直接使用的 Nginx WAF 规则（ngx_http_lua_module 或 limit_req_zone 格式）。

### 3. 紧急处置建议
如果需要立即封禁 IP，提供 fail2ban jail 配置片段。

请以 JSON 格式输出，包含以下字段：
{{
  "threats": [
    {{
      "type": "攻击类型",
      "severity": "high/medium/low",
      "description": "详细描述",
      "source_ips": ["IP列表"],
      "evidence": ["关键日志证据"]
    }}
  ],
  "waf_rules": [
    {{
      "type": "规则类型",
      "directive": "nginx 配置指令",
      "config_block": "完整的 nginx location/block 配置片段"
    }}
  ],
  "fail2ban_config": "jail 配置片段",
  "summary": "一句话总结当前安全态势"
}}"""


def call_ollama(prompt_text):
    """调用本地 Ollama API"""
    result = subprocess.run(
        ['ollama', 'run', MODEL, prompt_text],
        capture_output=True, text=True, timeout=120
    )
    if result.returncode != 0:
        raise RuntimeError(f"Ollama error: {result.stderr}")
    return result.stdout.strip()


def extract_json(text):
    """从 LLM 输出中提取 JSON"""
    # 尝试直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # 提取 ```json ... ``` 块
    import re
    match = re.search(r'```json\s*(\{.*?\})\s*```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    # 提取第一个 { ... } 块
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return None


def analyze_and_generate(log_summary_json):
    """主分析流程"""
    summary_str = json.dumps(log_summary_json, indent=2, ensure_ascii=False)
    prompt = ANALYSIS_PROMPT.format(traffic_summary=summary_str)

    print("🤖 正在调用本地 LLM 分析流量...", file=sys.stderr)
    raw_response = call_ollama(prompt)

    print("🔍 正在解析 AI 分析结果...", file=sys.stderr)
    result = extract_json(raw_response)

    if result is None:
        print("❌ 无法解析 LLM 输出，原始响应：", raw_response, file=sys.stderr)
        return None

    return result


def apply_waf_rules(ai_result):
    """将 AI 生成的规则写入 Nginx 配置"""
    rules_path = "/etc/nginx/conf.d/ai-waf.rules"
    lines = ["# Auto-generated WAF rules by AI Traffic Analyzer",
             f"# Generated: {__import__('datetime').datetime.now()}"]

    for rule in ai_result.get('waf_rules', []):
        lines.append(f"\n# === {rule['type']} ===")
        lines.append(rule['config_block'])

    with open(rules_path, 'w') as f:
        f.write('\n'.join(lines) + '\n')

    # 测试 nginx 配置
    test = subprocess.run(['nginx', '-t'], capture_output=True, text=True)
    if test.returncode == 0:
        subprocess.run(['nginx', '-s', 'reload'], check=False)
        print(f"✅ WAF 规则已应用并生效: {rules_path}")
    else:
        print(f"⚠️  nginx 配置测试失败，规则已保存但未加载:",
              test.stderr, file=sys.stderr)


def main():
    if len(sys.argv) < 2:
        print("用法: python3 ai_waf_analyzer.py <log_path>", file=sys.stderr)
        sys.exit(1)

    # 1. 解析日志
    from log_parser import analyze_window
    log_summary = analyze_window(sys.argv[1])
    if not log_summary:
        print("没有可分析的日志数据", file=sys.stderr)
        sys.exit(1)

    print(f"📊 分析了 {log_summary['total_requests']} 条请求，"
          f"{log_summary['unique_ips']} 个唯一 IP", file=sys.stderr)

    # 2. AI 分析
    ai_result = analyze_and_generate(log_summary)
    if not ai_result:
        sys.exit(1)

    # 3. 输出报告
    print("\n" + "="*60)
    print("🛡️  AI 安全分析报告")
    print("="*60)
    print(f"\n📋 态势总结: {ai_result.get('summary', 'N/A')}")

    for threat in ai_result.get('threats', []):
        severity_emoji = {'high': '🔴', 'medium': '🟡', 'low': '🟢'}
        emoji = severity_emoji.get(threat.get('severity', 'low'), '🟢')
        print(f"\n{emoji} [{threat['type'].upper()}] "
              f"严重性: {threat.get('severity', 'unknown')}")
        print(f"   描述: {threat.get('description', '')}")
        print(f"   来源 IP: {', '.join(threat.get('source_ips', [])[:5])}")

    # 4. 应用规则
    if ai_result.get('waf_rules'):
        apply_waf_rules(ai_result)

    # 5. 保存完整报告
    report_path = f"/tmp/ai-waf-report-{__import__('datetime').datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    with open(report_path, 'w') as f:
        json.dump(ai_result, f, indent=2, ensure_ascii=False)
    print(f"\n💾 完整报告已保存: {report_path}")


if __name__ == '__main__':
    main()
```

---

## 第四步：定时巡检与 Telegram 告警

将分析脚本加入 cron，每 5 分钟自动执行一次：

```bash
# crontab -e
*/5 * * * * /usr/bin/python3 /opt/vps-ai-waf/analyzer.py /var/log/nginx/access.log >> /var/log/vps-ai-waf/cron.log 2>&1
```

Telegram 告警集成：

```python
import urllib.request
import json

TELEGRAM_BOT_TOKEN = "YOUR_BOT_TOKEN"
CHAT_ID = "YOUR_CHAT_ID"

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = json.dumps({
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }).encode()
    req = urllib.request.Request(url, data=payload, method='POST')
    try:
        urllib.request.urlopen(req)
    except Exception as e:
        print(f"Telegram 发送失败: {e}")
```

在分析结果中检测到高危威胁时自动发送告警：

```python
high_severity = [t for t in ai_result.get('threats', [])
                 if t.get('severity') == 'high']
if high_severity:
    alert = "🚨 <b>VPS 安全告警</b>\n\n"
    alert += f"检测到 {len(high_severity)} 个高危威胁:\n"
    for t in high_severity:
        alert += f"• {t['type']}: {t['description'][:80]}\n"
    alert += f"\n📊 完整报告: {report_path}"
    send_telegram(alert)
```

---

## 第五步：实际效果示例

### 场景：CC 攻击检测

```
流量摘要显示：
- 10 分钟内来自 203.0.113.50 的請求數：2,341 次
- 全部請求路徑：/api/search?q=*
- 狀態碼：全部 200
- User-Agent：一致，疑似自動化工具
```

**AI 分析结果：**

```json
{
  "threats": [{
    "type": "cc_attack",
    "severity": "high",
    "description": "疑似 CC 攻击：单一 IP 在 10 分钟内发起 2341 次搜索请求，请求模式高度一致，命中率高",
    "source_ips": ["203.0.113.50"],
    "evidence": ["10min_count=2341", "same_path_ratio=99.2%", "consistent_ua=true"]
  }],
  "waf_rules": [{
    "type": "rate_limiting",
    "directive": "limit_req_zone",
    "config_block": "limit_req_zone $binary_remote_addr zone=search_limit:10m rate=10r/m;\n\nlocation /api/search {\n    limit_req zone=search_limit burst=20 nodelay;\n    limit_req_status 429;\n}"
  }]
}
```

系统自动将 `limit_req_zone` 规则写入 `/etc/nginx/conf.d/ai-waf.rules` 并 reload Nginx，攻击流量被自动限流。

---

### 场景：SQL 注入检测

```json
{
  "threats": [{
    "type": "sql_injection",
    "severity": "high",
    "description": "检测到 SQL 注入尝试：URL 参数中包含 OR 1=1 和 UNION SELECT 特征",
    "source_ips": ["198.51.100.23", "198.51.100.44"],
    "evidence": [
      "GET /api/users?id=1' OR '1'='1",
      "GET /api/products?cat=1 UNION SELECT username,password FROM users"
    ]
  }],
  "waf_rules": [{
    "type": "sql_injection_filter",
    "directive": "ngx_lua",
    "config_block": "location / {\n    access_by_lua_block {\n        local uri = ngx.var.uri\n        local args = ngx.var.args\n        if string.find(args, \"OR%s+1%s*=%s*1\", 1, true) then\n            ngx.exit(403)\n        end\n        if string.find(args, \"UNION%s+SELECT\", 1, true) then\n            ngx.exit(403)\n        end\n    }\n}"
  }]
}
```

---

## 完整部署脚本

```bash
#!/bin/bash
# deploy-ai-waf.sh — 一键部署智能 WAF 系统

set -e

echo "🔄 更新系统..."
apt update && apt upgrade -y

echo "📦 安装依赖..."
apt install -y nginx python3 python3-pip curl

echo "🤖 安装 Ollama..."
curl -fsSL https://ollama.com/install.sh | sh

echo "📥 拉取 Qwen2.5 模型..."
ollama pull qwen2.5:7b

echo "📁 创建项目目录..."
mkdir -p /opt/vps-ai-waf /var/log/vps-ai-waf

echo "📝 部署脚本..."
cp log_parser.py /opt/vps-ai-waf/
cp ai_waf_analyzer.py /opt/vps-ai-waf/
chmod +x /opt/vps-ai-waf/*.py

echo "🔧 配置 Nginx 包含规则..."
echo 'include /etc/nginx/conf.d/ai-waf.rules;' >> /etc/nginx/nginx.conf

echo "⏰ 设置定时任务（每 5 分钟分析一次）..."
(crontab -l 2>/dev/null; echo '*/5 * * * * /usr/bin/python3 /opt/vps-ai-waf/analyzer.py /var/log/nginx/access.log >> /var/log/vps-ai-waf/cron.log 2>&1') | crontab -

echo "✅ 部署完成！系统将在 5 分钟后开始首次分析。"
echo "   查看日志: tail -f /var/log/vps-ai-waf/cron.log"
```

---

## 优势与注意事项

### 核心优势

| 特性 | 传统方案 | AI 驱动方案 |
|------|---------|------------|
| 规则更新 | 人工编写，周期长 | AI 自动生成，分钟级响应 |
| 未知攻击 | 无法检测 | 基于行为模式识别 |
| 误报处理 | 需要人工调优 | AI 可结合上下文上下文降低误报 |
| 数据隐私 | 可能上传云端分析 | 完全本地运行，日志不出境 |
| 成本 | WAF 云服务月费 | 仅需 VPS 额外 2GB RAM |

### 注意事项

1. **资源消耗**：Qwen2.5:7b 需要约 4-5GB RAM，确保 VPS 内存充足
2. **分析延迟**：单次分析约 10-30 秒，建议结合滑动窗口减少调用频率
3. **规则审核**：AI 生成的规则建议首次部署时人工审核，确认无误后再全自动
4. **模型选择**：低配 VPS 可使用 `qwen2.5:3b`，精度略低但响应更快

---

## 总结

通过在本节 VPS 上部署 Ollama + Qwen2.5，我们构建了一套完全私有化的智能流量分析与 WAF 自动防护系统。它能够在不依赖任何云服务的前提下，实时识别 CC 攻击、SQL 注入、路径遍历等常见威胁，并自动生成、应用 Nginx WAF 规则。

这套系统的核心价值在于：**将安全运维从被动响应转变为主动防御**——你不再需要盯着日志发愁，而是让 AI 帮你 24 小时值守，发现异常即刻处置，同时通过 Telegram 随时掌握安全态势。

对于个人开发者和小团队来说，这是在有限预算下实现企业级安全防护的最优路径之一。
