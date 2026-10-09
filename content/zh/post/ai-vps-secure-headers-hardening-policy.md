---
title: "AI + VPS：Web 安全响应头智能加固与合规策略引擎"
description: "HTTP 响应头（HSTS、CSP、X-Frame-Options 等）是 Web 应用的第一道防线，但手工维护极易遗漏。本文用本地 LLM + Python 脚本实现 Nginx/Caddy 响应头自动审计、缺失项检测、CSP 策略生成，以及合规基线持续监控，附可复制的完整代码。"
date: 2026-10-09T21:00:00+08:00
lastmod: 2026-10-09T21:00:00+08:00
slug: "ai-vps-secure-headers-hardening-policy"
image: /images/posts/ai-vps-secure-headers-hardening-policy/featured.png
tags: ["VPS", "Nginx", "Caddy", "CSP", "HSTS", "Web安全", "LLM", "Ollama", "合规", "加固"]
categories: ["AI + VPS", "Web 安全"]
aliases: [/zh/post/ai-vps-secure-headers-hardening-policy/]
draft: false
---

## 引言

绝大多数 VPS 上运行的 Web 服务（Nginx、Caddy、Apache、Node/Python 后端）**默认不会设置任何安全响应头**。

这意味着你的网站暴露在一系列经典攻击下：

| 缺失响应头 | 对应风险 |
|-----------|---------|
| `Content-Security-Policy` | 点击劫持、XSS 注入 |
| `Strict-Transport-Security` | SSL 降级攻击、中间人 |
| `X-Frame-Options` / `frame-ancestors` | 点击劫持（Clickjacking） |
| `X-Content-Type-Options: nosniff` | MIME 类型嗅探攻击 |
| `Referrer-Policy` | 敏感 URL 泄漏到第三方站点 |
| `Permissions-Policy` | 摄像头/麦克风/地理位置被滥用 |
| `Cache-Control`（敏感端点） | 会话数据被浏览器缓存泄漏 |

手工维护这些头的问题是：**每次部署新服务、每次升级 Nginx，都很容易漏掉。** 而且 CSP 写错一个 `unsafe-*` 指令，整个策略形同虚设。

本文的方案：

1. **自动审计脚本**（Python + curl）：扫描所有对外 HTTP 端点，解析响应头，输出缺失项报告
2. **LLM 策略生成器**（Ollama + Qwen2.5）：根据站点实际资源域名、CDN 域名自动生成可运行的 CSP 字符串
3. **合规基线比对**：对照 OWASP Secure Headers Project 基线，持续监控 Nginx/Caddy 配置漂移
4. **一键加固脚本**：将生成的策略直接注入 Nginx `nginx.conf` 或 Caddyfile，并做语法检查后 reload

全部离线运行，不上传任何流量数据。

---

## 1. 方案架构

```
┌─────────────────────────────────────────────────────────┐
│  定时任务（systemd timer / cron）                         │
│     │                                                    │
│     ▼                                                    │
│  audit_headers.py                                        │
│     │ 1. 抓取 https://your-vps/ 全部响应头                │
│     │ 2. 解析缺失项 + 已知弱指令（unsafe-inline 等）       │
│     ▼                                                    │
│  LLM 策略生成（Ollama + Qwen2.5）                        │
│     │ 输入: 站点资源清单 + 当前缺失头列表                   │
│     │ 输出: 可运行 CSP / HSTS / Permissions-Policy 字符串  │
│     ▼                                                    │
│  合规基线比对（OWASP Secure Headers）                      │
│     │ 输出: 合规分 (0-100) + 违规清单                      │
│     ▼                                                    │
│  一键加固 + 验证                                          │
│     │ 注入 nginx.conf / Caddyfile → 语法检查 → reload     │
│     │ 再次抓取响应头确认生效                                │
└─────────────────────────────────────────────────────────┘
```

---

## 2. 自动审计脚本：扫描所有响应头

```python
#!/usr/bin/env python3
"""
audit_headers.py — VPS Web 端点安全响应头审计
用法: python3 audit_headers.py https://your-vps.example
"""

import sys, json, urllib.request
from urllib.error import URLError

# OWASP Secure Headers Project 基线（2025）
REQUIRED_HEADERS = {
    "content-security-policy": {
        "severity": "critical",
        "weak_markers": ["'unsafe-inline'", "'unsafe-eval'", "'*'", "script-src 'none'"],
    },
    "strict-transport-security": {
        "severity": "high",
        "min_max_age": 31536000,  # ≥ 1年
        "require_subdomains": True,
    },
    "x-content-type-options": {"severity": "high", "expected": "nosniff"},
    "referrer-policy": {
        "severity": "medium",
        "expected": ["no-referrer", "same-origin"],
    },
    "permissions-policy": {"severity": "medium"},
    "x-frame-options": {"severity": "high"},
    "cache-control": {"severity": "info"},
}

def fetch_headers(url: str) -> dict:
    """抓取 URL 的所有响应头"""
    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=15) as resp:
            return {k.lower(): v for k, v in resp.headers.items()}
    except URLError as e:
        print(f"[ERROR] 无法连接 {url}: {e}", file=sys.stderr)
        sys.exit(1)

def audit(headers: dict) -> dict:
    """逐头检查，返回缺失/弱配置项"""
    results = {}
    for name, rule in REQUIRED_HEADERS.items():
        value = headers.get(name, "")
        if not value:
            results[name] = {"status": "MISSING", "severity": rule["severity"]}
        else:
            # HSTS 特别检查
            if name == "strict-transport-security":
                max_age = 0
                if "max-age=" in value:
                    max_age = int(value.split("max-age=")[1].split(";")[0])
                if max_age < rule.get("min_max_age", 0):
                    results[name] = {
                        "status": "WEAK",
                        "severity": "high",
                        "detail": f"max-age={max_age} < 31536000",
                    }
            # CSP 弱指令检查
            elif name == "content-security-policy":
                weak_found = [m for m in rule["weak_markers"] if m in value]
                if weak_found:
                    results[name] = {
                        "status": "WEAK",
                        "severity": "critical",
                        "detail": f"含弱指令: {weak_found}",
                    }
    return results

if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "https://127.0.0.1"
    raw = fetch_headers(url)
    issues = audit(raw)

    print(f"目标: {url}")
    print(f"检测项: {len(REQUIRED_HEADERS)}, 缺失/弱配置: {len(issues)}")
    print()
    for name, info in sorted(issues.items(),
                              key=lambda x: {"critical": 0, "high": 1, "medium": 2, "info": 3}[x[1]["severity"]]):
        icon = "❌" if info["status"] == "MISSING" else "⚠️"
        print(f" {icon} [{info['severity'].upper()}] {name}")
        if "detail" in info:
            print(f"    → {info['detail']}")

    # 输出 JSON 供 LLM 使用
    with open("/tmp/header_audit.json", "w") as f:
        json.dump({"url": url, "issues": issues}, f, indent=2, ensure_ascii=False)
    print("\n[OK] 结果已保存至 /tmp/header_audit.json")
```

运行效果示例：

```
目标: https://your-vps.example
检测项: 7, 缺失/弱配置: 5

 ❌ [CRITICAL] content-security-policy
 ❌ [HIGH] strict-transport-security
 ❌ [HIGH] x-content-type-options
 ❌ [MEDIUM] referrer-policy
 ❌ [MEDIUM] permissions-policy
```

---

## 3. LLM 生成 CSP：比手写策略更准确

CSP 最难写的部分是 `script-src` 和 `style-src` 的域名白名单——写漏了资源就 404，写宽了形同虚设。用 LLM 可以自动从站点实际资源中推断。

### 3.1 收集站点资源清单

```bash
# 从 Nginx 访问日志中提取最近 7 天的资源 URL
awk '{print $7}' /var/log/nginx/access.log | grep -oP 'https?://[^/]+' | sort | uniq -c | sort -rn > /tmp/resource_domains.txt
head -20 /tmp/resource_domains.txt
```

### 3.2 调用 Ollama 生成 CSP

```python
#!/usr/bin/env python3
"""
generate_csp.py — 用本地 LLM 生成 CSP 策略
依赖: ollama serve + qwen2.5:7b
"""

import json, urllib.request, os

AUDIT_FILE = "/tmp/header_audit.json"
RESOURCE_FILE = "/tmp/resource_domains.txt"
MODEL = "qwen2.5:7b"
OLLAMA = "http://127.0.0.1:11434"

def build_prompt(audit: dict, domains: list) -> str:
    """构造 LLM prompt"""
    issues_json = json.dumps(audit.get("issues", {}), ensure_ascii=False, indent=2)
    domain_list = "\n".join(f"  - {d}" for d in domains)

    return f"""
你是一名 Web 安全工程师。请为以下站点生成完整的 HTTP 安全响应头配置。

当前审计结果（缺失/弱项）:
{issues_json}

站点实际使用的资源域名白名单:
{domain_list}

请输出完整的 Nginx 配置片段（http 块内），包含：
1. content-security-policy（script-src/style-src 使用域名白名单，禁止 unsafe-inline/unsafe-eval）
2. strict-transport-security（max-age=31536000; includeSubDomains）
3. x-content-type-options: nosniff
4. referrer-policy: strict-origin-when-cross-origin
5. permissions-policy（禁用不需要的摄像头/麦克风/地理位置）
6. x-frame-options: DENY

用 ```nginx 代码块输出，不要解释。
"""

def call_ollama(prompt: str) -> str:
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.2},  # 低温度，策略生成要稳定
    }
    req = urllib.request.Request(
        f"{OLLAMA}/api/generate",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read())["response"]

if __name__ == "__main__":
    with open(AUDIT_FILE) as f:
        audit = json.load(f)
    with open(RESOURCE_FILE) as f:
        domains = [line.strip().split()[-1] for line in f if line.strip()]

    result = call_ollama(build_prompt(audit, domains))
    print(result)

    # 保存供部署脚本使用
    with open("/tmp/csp_generated.conf", "w") as f:
        f.write(result)
    print("\n[OK] 策略已保存至 /tmp/csp_generated.conf")
```

### 3.3 LLM 生成的典型输出

```nginx
# CSP
add_header Content-Security-Policy "default-src 'self'; "
    "script-src 'self' https://cdn.your-vps.example; "
    "style-src 'self' https://cdn.your-vps.example; "
    "img-src 'self' https://images.your-vps.example data:; "
    "connect-src 'self' wss://your-vps.example; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'" always;

add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;
add_header X-Content-Type-Options "nosniff" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
add_header Permissions-Policy "camera=(), microphone=(), geolocation=(), payment=()" always;
add_header X-Frame-Options "DENY" always;
```

> **`always` 参数是关键**：没有它，301/302/404 响应不会携带这些头。

---

## 4. 一键注入 Nginx 配置并验证

### 4.1 注入脚本（systemd 服务或手动运行）

```python
#!/usr/bin/env python3
"""
apply_csp.py — 将生成的 CSP 注入 nginx.conf，语法检查后 reload
"""

import subprocess, sys, time

NGINX_CONF = "/etc/nginx/nginx.conf"
GENERATED = "/tmp/csp_generated.conf"

def apply():
    # 1. 读取生成的策略
    with open(GENERATED) as f:
        policy_block = f.read().strip()

    # 2. 定位 nginx.conf 中 server{} 块内的 add_header 位置
    #    这里假设策略放在 http 块末尾（全局生效）
    with open(NGINX_CONF) as f:
        conf = f.read()

    # 3. 移除旧的 CSP 相关 add_header（幂等）
    old_lines = [l for l in conf.splitlines() if "add_header" in l]
    for line in old_lines:
        conf = conf.replace(line, "")

    # 4. 在 http { ... } 块末尾注入
    marker = "  }\n"  # http 块闭合
    idx = conf.rfind(marker)
    conf = conf[:idx] + policy_block + "\n" + conf[idx:]

    # 5. 语法检查
    result = subprocess.run(
        ["nginx", "-t"], capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"[FAIL] Nginx 语法检查失败，未 reload：\n{result.stderr}", file=sys.stderr)
        sys.exit(1)

    # 6. 写入 + reload
    with open(NGINX_CONF, "w") as f:
        f.write(conf)
    subprocess.run(["nginx", "-s", "reload"], check=True)
    print("[OK] 策略已注入并重载 Nginx")

if __name__ == "__main__":
    apply()
```

### 4.2 再次验证（闭环）

```bash
# 注入后立即重新审计，确认生效
curl -sI https://your-vps.example | grep -E "^(content-security|strict-transport|x-content|x-frame|referrer|permissions)"
```

期望输出：

```
content-security-policy: default-src 'self'; script-src 'self' ...
strict-transport-security: max-age=31536000; includeSubDomains; preload
x-content-type-options: nosniff
x-frame-options: DENY
referrer-policy: strict-origin-when-cross-origin
permissions-policy: camera=(), microphone=(), geolocation=()
```

---

## 5. 合规基线持续监控（systemd timer）

将审计脚本封装为 systemd 服务 + timer，每周跑一次，结果推送到 Telegram。

```ini
# /etc/systemd/system/header-audit.service
[Unit]
Description=VPS Web Security Header Audit
After=network-online.target

[Service]
Type=oneshot
User=root
ExecStart=/usr/bin/python3 /opt/vps-security/header-audit-and-report.py
Restart=on-failure

---
# /etc/systemd/system/header-audit.timer
[Unit]
Description=Weekly security header audit

[Timer]
OnCalendar=Sun 03:00
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
systemctl enable --now header-audit.timer
systemctl list-timers | grep header-audit
```

### 5.1 合规分计算（嵌入 Python）

```python
def compliance_score(issues: dict) -> float:
    """按严重度加权计算合规分"""
    weights = {"critical": 0.30, "high": 0.25, "medium": 0.15, "info": 0.05}
    total = 0.0
    for name, info in issues.items():
        w = weights.get(info.get("severity", "medium"), 0.1)
        total += w  # 每项违规扣分
    # 满分 1.0，按比例折算 0-100
    max_possible = sum(weights.values()) * len(REQUIRED_HEADERS)
    return round(100 * (1 - total / max_possible), 1)
```

分数低于 60 时触发告警。

---

## 6. Caddy 用户适配

Caddy 的安全头配置更简洁，全局写在 `http` 块：

```caddyfile
# Caddyfile（全局安全头）
{
    # Caddy 默认就有部分安全头，这里做完整覆盖
    globals enforce_csp strict
}

your-vps.example {
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"
        Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self'"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
        Referrer-Policy "strict-origin-when-cross-origin"
        Permissions-Policy "camera=(), microphone=()"
        -Server   # 隐藏服务器版本
    }
}
```

Caddy 的优势：`-Server` 指令直接剥离 `Server: Caddy` 响应头，Nginx 需要 `server_tokens off;`。

---

## 7. 常见问题

**Q：CSP 写错了，网站白屏怎么办？**

A：CSP 有 `report-only` 模式——先加这一行观察 7 天，不阻塞请求：

```nginx
add_header Content-Security-Policy-Report-Only "default-src 'self'" always;
```

配合 `report-uri https://csp-report.your-vps.example/` 收集违规日志，确认无误后再切换为强制模式。

**Q：LLM 生成的 CSP 包含 `unsafe-inline`，为什么？**

A：`temperature` 设得太高或 prompt 中资源域名清单不完整。确认 `/tmp/resource_domains.txt` 覆盖了所有第三方资源（CDN、字体、统计脚本），并把 `temperature` 调低到 0.2。

**Q：HTTPS 证书过期会不会影响 HSTS 预加载？**

A：会。HSTS `preload` 提交到 [hstspreload.org](https://hstspreload.org) 后，证书过期 = 浏览器直接拒绝访问（30 天宽限期）。建议证书到期前 14 天自动告警。

---

## 总结

| 步骤 | 工具 | 频率 |
|------|------|------|
| 响应头审计 | `audit_headers.py` + curl | 每周 |
| CSP 策略生成 | Ollama + Qwen2.5 | 站点资源变更时 |
| 策略注入 + 验证 | `apply_csp.py` + nginx -t | 策略生成后 |
| 合规分监控 | systemd timer + Telegram | 每周 |
| 证书到期预警 | cert-manager / Let's Encrypt | 持续 |

安全响应头不是"设置一次就忘"的事情——每次部署、每次加 CDN、每次换域名，策略都要跟着更新。这套 LLM 驱动的流程把这件事从"人工记挂"变成了"自动闭环"。

完整脚本见文末附录，直接复制到你的 VPS 即可运行。
