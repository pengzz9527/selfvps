---
title: "AI + VPS: Intelligent Web Security Hardening & Compliance Policy Engine"
description: "HTTP security response headers (HSTS, CSP, X-Frame-Options, etc.) are your first line of defense — but manual maintenance is error-prone. This article walks through a local-LLM + Python pipeline that auto-audits Nginx/Caddy headers, detects missing directives, generates a working CSP policy, and enforces a compliance baseline. Full copy-paste code included."
date: 2026-10-09T21:00:00+08:00
lastmod: 2026-10-09T21:00:00+08:00
slug: "ai-vps-secure-headers-hardening-policy"
image: /images/posts/ai-vps-secure-headers-hardening-policy/featured.png
tags: ["VPS", "Nginx", "Caddy", "CSP", "HSTS", "Web Security", "LLM", "Ollama", "Compliance", "Hardening"]
categories: ["AI + VPS", "Web Security"]
aliases: [/en/post/ai-vps-secure-headers-hardening-policy/]
draft: false
---

## Introduction

Most web services running on a VPS (Nginx, Caddy, Apache, Node/Python backends) ship with **zero security response headers** enabled by default.

That leaves your site exposed to a well-known set of attacks:

| Missing Header | Risk |
|---------------|------|
| `Content-Security-Policy` | Clickjacking, XSS injection |
| `Strict-Transport-Security` | SSL downgrade, man-in-the-middle |
| `X-Frame-Options` / `frame-ancestors` | Clickjacking |
| `X-Content-Type-Options: nosniff` | MIME type sniffing |
| `Referrer-Policy` | Sensitive URLs leaking to third parties |
| `Permissions-Policy` | Camera / mic / geolocation abuse |
| `Cache-Control` (on sensitive endpoints) | Session data cached in the browser |

The problem with maintaining these by hand: **every new service, every Nginx upgrade, every domain change is a chance to miss one.** And a single `unsafe-*` directive in your CSP silently disables the entire policy.

This article delivers a fully offline, LLM-powered pipeline:

1. **Auto-audit script** (Python + curl): scans all public HTTP endpoints, parses response headers, outputs a gap report
2. **LLM policy generator** (Ollama + Qwen2.5): reads your actual resource domain list and generates a working, copy-paste-ready CSP string
3. **Compliance baseline check**: continuously monitors Nginx/Caddy config drift against the OWASP Secure Headers Project baseline
4. **One-click injection script**: writes the policy into `nginx.conf` or your Caddyfile, runs a syntax check, then reloads

Everything runs locally — no traffic data ever leaves your server.

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│  Scheduled job (systemd timer / cron)                    │
│     │                                                    │
│     ▼                                                    │
│  audit_headers.py                                        │
│     │ 1. Fetches all response headers from your VPS      │
│     │ 2. Parses missing + weak directives                │
│     ▼                                                    │
│  LLM Policy Generation (Ollama + Qwen2.5)               │
│     │ Input: site resource inventory + missing headers   │
│     │ Output: runnable CSP / HSTS / Permissions-Policy  │
│     ▼                                                    │
│  Compliance Baseline (OWASP Secure Headers)              │
│     │ Output: score (0-100) + violation list             │
│     ▼                                                    │
│  One-click Apply + Verify                                │
│     │ Inject into nginx.conf / Caddyfile → syntax check  │
│     │ → reload → re-audit to confirm                     │
└─────────────────────────────────────────────────────────┘
```

---

## 2. Auto-Audit Script: Scanning All Response Headers

```python
#!/usr/bin/env python3
"""
audit_headers.py — VPS Web security header audit
Usage: python3 audit_headers.py https://your-vps.example
"""

import sys, json, urllib.request
from urllib.error import URLError

# OWASP Secure Headers Project baseline (2025)
REQUIRED_HEADERS = {
    "content-security-policy": {
        "severity": "critical",
        "weak_markers": ["'unsafe-inline'", "'unsafe-eval'", "'*'", "script-src 'none'"],
    },
    "strict-transport-security": {
        "severity": "high",
        "min_max_age": 31536000,  # ≥ 1 year
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
    """Fetch all response headers for a URL"""
    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=15) as resp:
            return {k.lower(): v for k, v in resp.headers.items()}
    except URLError as e:
        print(f"[ERROR] Cannot connect to {url}: {e}", file=sys.stderr)
        sys.exit(1)

def audit(headers: dict) -> dict:
    """Check each header, return missing/weak items"""
    results = {}
    for name, rule in REQUIRED_HEADERS.items():
        value = headers.get(name, "")
        if not value:
            results[name] = {"status": "MISSING", "severity": rule["severity"]}
        else:
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
            elif name == "content-security-policy":
                weak_found = [m for m in rule["weak_markers"] if m in value]
                if weak_found:
                    results[name] = {
                        "status": "WEAK",
                        "severity": "critical",
                        "detail": f"Weak directives found: {weak_found}",
                    }
    return results

if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "https://127.0.0.1"
    raw = fetch_headers(url)
    issues = audit(raw)

    print(f"Target: {url}")
    print(f"Checks: {len(REQUIRED_HEADERS)}, Missing/weak: {len(issues)}")
    print()
    for name, info in sorted(issues.items(),
                              key=lambda x: {"critical": 0, "high": 1, "medium": 2, "info": 3}[x[1]["severity"]]):
        icon = "❌" if info["status"] == "MISSING" else "⚠️"
        print(f" {icon} [{info['severity'].upper()}] {name}")
        if "detail" in info:
            print(f"    → {info['detail']}")

    with open("/tmp/header_audit.json", "w") as f:
        json.dump({"url": url, "issues": issues}, f, indent=2, ensure_ascii=False)
    print("\n[OK] Results saved to /tmp/header_audit.json")
```

Sample output:

```
Target: https://your-vps.example
Checks: 7, Missing/weak: 5

 ❌ [CRITICAL] content-security-policy
 ❌ [HIGH] strict-transport-security
 ❌ [HIGH] x-content-type-options
 ❌ [MEDIUM] referrer-policy
 ❌ [MEDIUM] permissions-policy
```

---

## 3. LLM-Generated CSP: More Accurate Than Hand-Written

The hardest part of a CSP is the `script-src` and `style-src` domain whitelist — write it too narrow and your assets 404; write it too wide and the policy is meaningless. An LLM can infer the whitelist from your actual traffic.

### 3.1 Collect Your Resource Domain List

```bash
# Extract resource domains from the last 7 days of Nginx access logs
awk '{print $7}' /var/log/nginx/access.log | grep -oP 'https?://[^/]+' | sort | uniq -c | sort -rn > /tmp/resource_domains.txt
head -20 /tmp/resource_domains.txt
```

### 3.2 Call Ollama to Generate the CSP

```python
#!/usr/bin/env python3
"""
generate_csp.py — LLM-powered CSP policy generator
Requires: ollama serve + qwen2.5:7b
"""

import json, urllib.request

AUDIT_FILE = "/tmp/header_audit.json"
RESOURCE_FILE = "/tmp/resource_domains.txt"
MODEL = "qwen2.5:7b"
OLLAMA = "http://127.0.0.1:11434"

def build_prompt(audit: dict, domains: list) -> str:
    issues_json = json.dumps(audit.get("issues", {}), ensure_ascii=False, indent=2)
    domain_list = "\n".join(f"  - {d}" for d in domains)

    return f"""
You are a web security engineer. Generate a complete HTTP security header configuration for this site.

Current audit results (missing/weak items):
{issues_json}

Allowed resource domains observed in traffic:
{domain_list}

Output a complete Nginx configuration snippet (inside the http block) containing:
1. content-security-policy (domain whitelist, no unsafe-inline/unsafe-eval)
2. strict-transport-security (max-age=31536000; includeSubDomains)
3. x-content-type-options: nosniff
4. referrer-policy: strict-origin-when-cross-origin
5. permissions-policy (disable unneeded camera/mic/geolocation)
6. x-frame-options: DENY

Output in a ```nginx code block only, no explanation.
"""

def call_ollama(prompt: str) -> str:
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.2},  # Low temp for stable policy output
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
    with open("/tmp/csp_generated.conf", "w") as f:
        f.write(result)
    print("\n[OK] Policy saved to /tmp/csp_generated.conf")
```

### 3.3 Typical LLM Output

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

> **The `always` parameter is critical** — without it, 301/302/404 responses won't carry these headers.

---

## 4. One-Click Nginx Injection & Verification

### 4.1 Injection Script

```python
#!/usr/bin/env python3
"""
apply_csp.py — Inject generated CSP into nginx.conf, syntax-check, reload
"""

import subprocess, sys

NGINX_CONF = "/etc/nginx/nginx.conf"
GENERATED = "/tmp/csp_generated.conf"

def apply():
    with open(GENERATED) as f:
        policy_block = f.read().strip()

    with open(NGINX_CONF) as f:
        conf = f.read()

    # Idempotent: remove old add_header lines first
    for line in [l for l in conf.splitlines() if "add_header" in l]:
        conf = conf.replace(line, "")

    # Inject at the end of the http block
    marker = "  }\n"
    idx = conf.rfind(marker)
    conf = conf[:idx] + policy_block + "\n" + conf[idx:]

    # Syntax check before reload
    result = subprocess.run(["nginx", "-t"], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[FAIL] Nginx syntax check failed, not reloading:\n{result.stderr}",
              file=sys.stderr)
        sys.exit(1)

    with open(NGINX_CONF, "w") as f:
        f.write(conf)
    subprocess.run(["nginx", "-s", "reload"], check=True)
    print("[OK] Policy injected and Nginx reloaded")

if __name__ == "__main__":
    apply()
```

### 4.2 Post-Injection Verification (Closed Loop)

```bash
# Re-audit immediately after reload to confirm
curl -sI https://your-vps.example | grep -E "^(content-security|strict-transport|x-content|x-frame|referrer|permissions)"
```

Expected output:

```
content-security-policy: default-src 'self'; script-src 'self' ...
strict-transport-security: max-age=31536000; includeSubDomains; preload
x-content-type-options: nosniff
x-frame-options: DENY
referrer-policy: strict-origin-when-cross-origin
permissions-policy: camera=(), microphone=(), geolocation=()
```

---

## 5. Continuous Compliance Monitoring (systemd timer)

Wrap the audit in a systemd service + timer, run weekly, push results to Telegram.

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

### 5.1 Compliance Scoring

```python
def compliance_score(issues: dict) -> float:
    """Weighted compliance score based on severity"""
    weights = {"critical": 0.30, "high": 0.25, "medium": 0.15, "info": 0.05}
    total = sum(weights.get(info.get("severity", "medium"), 0.1)
                for info in issues.values())
    max_possible = sum(weights.values()) * len(REQUIRED_HEADERS)
    return round(100 * (1 - total / max_possible), 1)
```

Trigger a Telegram alert when the score drops below 60.

---

## 6. Caddy Users

Caddy's security header configuration is cleaner — set it globally in the `http` block:

```caddyfile
# Caddyfile (global security headers)
{
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
        -Server   # Strip server version header
    }
}
```

Caddy's `-Server` directive removes the `Server: Caddy` header entirely; Nginx requires `server_tokens off;` for the same effect.

---

## 7. Common Pitfalls

**Q: My CSP broke the site — white screen. What now?**

A: Use `report-only` mode first. Add this and observe for 7 days without blocking any requests:

```nginx
add_header Content-Security-Policy-Report-Only "default-src 'self'" always;
```

Pair it with `report-uri https://csp-report.your-vps.example/` to collect violation logs, then switch to enforcement mode once you're confident.

**Q: LLM generated a CSP containing `unsafe-inline`. Why?**

A: `temperature` too high, or the resource domain list is incomplete. Verify `/tmp/resource_domains.txt` covers all third-party resources (CDN, fonts, analytics) and lower `temperature` to 0.2.

**Q: Will an expired HTTPS certificate affect HSTS preloading?**

A: Yes. Once your domain is submitted to [hstspreload.org](https://hstspreload.org), an expired certificate means browsers will hard-refuse to connect for up to 30 days. Set up a certificate expiry alert 14 days before expiry.

---

## Summary

| Step | Tool | Frequency |
|------|------|-----------|
| Header audit | `audit_headers.py` + curl | Weekly |
| CSP policy generation | Ollama + Qwen2.5 | When site resources change |
| Policy injection + verification | `apply_csp.py` + nginx -t | After policy generation |
| Compliance score monitoring | systemd timer + Telegram | Weekly |
| Certificate expiry alerts | cert-manager / Let's Encrypt | Continuous |

Security headers aren't set-and-forget. Every deployment, every new CDN, every domain change requires the policy to be updated. This LLM-driven pipeline turns that ongoing maintenance from a manual checklist into an automated, closed-loop system.

All scripts are in the appendix below — copy them to your VPS and run.
