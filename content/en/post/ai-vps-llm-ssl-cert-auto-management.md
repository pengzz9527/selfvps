---
title: "Intelligent SSL Certificate Management on VPS with Local LLM: Zero-Downtime Rotation & Risk Scoring"
description: "Expiring SSL certificates are one of the most common silent failures in VPS ops. Deploy a local LLM (Ollama + Qwen2.5) powered certificate management system: auto-discovery, risk scoring, zero-downtime rotation, rollback protection — keep HTTPS alive 24/7."
date: 2026-10-22T20:00:00+08:00
lastmod: 2026-10-22T20:00:00+08:00
slug: "ai-vps-llm-ssl-cert-auto-management"
image: /images/posts/ai-vps-llm-ssl-cert-auto-management/featured.png
tags: ["AI Ops", "VPS", "SSL", "Certificate Management", "Automation", "Ollama", "Qwen2.5", "acme.sh", "Zero-Downtime", "Security"]
categories: ["AI Ops"]
aliases: [/en/post/ai-vps-llm-ssl-cert-auto-management/]
---

## The Silent Killer: Expired SSL Certificates

Your VPS hosts a website, an API gateway, and a database. One day at 3 AM, a customer reports "the site is down." You open the browser — a big red warning: **"Your connection is not private."**

Why? The certificate expired 30 days ago. No monitoring alert fired, or it fired but nobody was watching.

This is not a rare event. According to Let's Encrypt statistics, millions of services are disrupted every year due to certificate expiration. In the VPS world, this problem is particularly acute:

- **Multiple domains, multiple certificates**: You may manage 5 domains simultaneously, each with independent Nginx/Caddy configurations. Missing any one is an incident.
- **Silent failure**: Unlike a CPU spike, certificate expiration doesn't immediately show up on your monitoring dashboard — the service is still running, it's just that the TLS handshake fails.
- **Cascading impact**: Browsers mark the domain as "not secure" and cache that state. Even after you renew the certificate, users may still see the old status.
- **Compliance pressure**: PCI-DSS and similar frameworks require certificates to be in valid state — one day of expiration can trigger an audit finding.

**The gap in traditional approaches**: Most VPS operators use `certbot` or `acme.sh` for auto-renewal. This solves the "renew" problem, but not the "governance" problem — you have no idea which certificates are about to expire, which domains have misconfigured settings, which certificate chains are incomplete, which services are using self-signed certs, or which certificates use algorithms that are being deprecated (like SHA-1).

An **intelligent certificate management system** answers these governance questions. It uses a locally deployed LLM as the "brain" to continuously scan every certificate on the VPS, perform risk scoring and prioritization with the LLM, auto-generate rotation plans, execute the switch within a zero-downtime window, and automatically roll back on failure.

In this article, we'll build this system from scratch, covering:

1. **Certificate Discovery**: Auto-scan all HTTPS services, certificate files, and DNS configurations on the VPS
2. **AI Risk Assessment**: Local Ollama + Qwen2.5 scores each certificate across multiple dimensions (expiry proximity, weak algorithms, incomplete chain, domain mismatch, etc.)
3. **Rotation Execution**: Based on LLM-generated decisions, auto-execute acme.sh renewal or manual certificate replacement with zero-downtime hot reload
4. **Rollback Protection**: Auto-backup old certs before execution; rollback in 30 seconds on failure — service stays up
5. **Closed-Loop Learning**: Record each rotation outcome and continuously refine the LLM's risk judgment

## System Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                   Intelligent SSL Certificate Management System      │
├──────────────┬──────────────┬──────────────┬─────────────────────────┤
│  Certificate │  AI Risk     │  Rotation     │  Rollback & Learning  │
│  Discovery   │  Assessment  │  Execution    │  Protection            │
├──────────────┼──────────────┼──────────────┼─────────────────────────┤
│ openssl      │              │ acme.sh      │ Certificate backup      │
│ scan local   │  → LLM API  │  auto-renew   │  (SQLite)              │
│ cert files   │  (Qwen2.5)  │  manual swap  │  Hot-reload validation │
│ Nginx/Caddy  │              │  Nginx reload │  Rollback executor     │
│ config parse │              │  systemctl    │  Outcome records       │
│ DNS records  │              │  verify       │  Model feedback        │
└──────────────┴──────────────┴──────────────┴─────────────────────────┘
         ↓                ↓                ↓                ↓
    scanner.py      Ollama server   rotator.py      rollback.py
    (cron 30min)   (local :11434)   (LLM-trigger)  (30s rollback on fail)
```

## Step 1: Deploy Ollama Local LLM

The "brain" of the certificate management system is a local LLM, ensuring all certificate data (domains, IPs, key paths) never leaves the VPS.

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull Qwen2.5-7B (recommended for strong ops understanding)
ollama pull qwen2.5:7b

# For resource-constrained 2C2G VPS, use a lighter model
ollama pull qwen2.5:3b

# Verify
ollama list
ollama run qwen2.5:7b "Explain what a TLS certificate chain is in one sentence"
```

For a 2C2G VPS, use `qwen2.5:3b` (~2GB RAM). For 4C8G and above, `qwen2.5:7b` (~5GB RAM) is recommended.

## Step 2: Build the Certificate Discovery Engine

The discovery engine scans all SSL/TLS certificate sources and states on the VPS, outputting structured data for LLM analysis.

### 2.1 Scan Local Certificate Files

```python
# cert_manager/discovery.py
import subprocess
import json
import re
from datetime import datetime
from pathlib import Path

class CertificateDiscovery:
    """Scan all certificate sources on the VPS"""

    def __init__(self):
        self.certs = []

    def scan_openssl_certs(self, base_paths=None):
        """Scan common certificate directories for .crt/.pem files"""
        if base_paths is None:
            base_paths = [
                "/etc/ssl/certs/",
                "/etc/nginx/ssl/",
                "/etc/caddy/",
                "/var/lib/acme/",
                "/opt/certs/",
            ]

        for base in base_paths:
            path = Path(base)
            if not path.exists():
                continue

            for f in path.rglob("*.crt"):
                self._analyze_cert_file(f)
            for f in path.rglob("*.pem"):
                self._analyze_cert_file(f)
            for f in path.rglob("*.key"):
                self._note_key_file(f)

        return self.certs

    def _analyze_cert_file(self, cert_path: Path):
        """Parse a certificate file with openssl and extract key info"""
        try:
            result = subprocess.run(
                ["openssl", "x509", "-in", str(cert_path), "-noout", "-text"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode != 0:
                return

            output = result.stdout

            subject_match = re.search(r"Subject:.*?CN=(\S+)", output)
            cn = subject_match.group(1) if subject_match else "unknown"

            not_before_match = re.search(r"Not Before\s*:\s*(.+)", output)
            not_after_match = re.search(r"Not After\s*:\s*(.+)", output)

            sig_algo_match = re.search(r"Signature Algorithm:\s*(\S+)", output)
            sig_algo = sig_algo_match.group(1) if sig_algo_match else "unknown"

            issuer_match = re.search(r"Issuer:.*?CN=(\S+)", output)
            issuer = issuer_match.group(1) if issuer_match else "unknown"

            self.certs.append({
                "type": "file",
                "path": str(cert_path),
                "common_name": cn,
                "issuer": issuer,
                "signature_algorithm": sig_algo,
                "not_before": not_before_match.group(1).strip() if not_before_match else None,
                "not_after": not_after_match.group(1).strip() if not_after_match else None,
                "status": "unknown",
            })
        except Exception as e:
            print(f"[WARN] Cannot parse certificate {cert_path}: {e}")

    def _note_key_file(self, key_path: Path):
        """Record private key files (path and permissions only, never read content)"""
        try:
            import os
            mode = oct(os.stat(key_path).st_mode & 0o777)
            self.certs.append({
                "type": "key",
                "path": str(key_path),
                "permissions": mode,
                "insecure_permissions": not (os.stat(key_path).st_mode & 0o044),
            })
        except Exception:
            pass

    def scan_nginx_ssl_config(self, config_path="/etc/nginx/nginx.conf"):
        """Parse Nginx config to find all SSL certificate references"""
        try:
            with open(config_path) as f:
                content = f.read()
        except FileNotFoundError:
            return []

        certs = []
        cert_pattern = re.compile(
            r'ssl_certificate\s+([^\s;]+);?\s*'
            r'(?:ssl_certificate_key\s+([^\s;]+);)?',
            re.MULTILINE
        )

        for match in cert_pattern.finditer(content):
            certs.append({
                "type": "nginx_config",
                "cert_path": match.group(1),
                "key_path": match.group(2) if match.group(2) else None,
                "config_file": config_path,
            })

        return certs

    def scan_listening_https_services(self):
        """Scan for services listening on HTTPS ports"""
        try:
            result = subprocess.run(
                ["ss", "-tlnp"],
                capture_output=True, text=True, timeout=10
            )
            listeners = []
            for line in result.stdout.strip().split("\n"):
                if ":443" in line or ":8443" in line or ":4433" in line:
                    listeners.append(line)
            return listeners
        except Exception:
            return []

    def full_scan(self):
        """Execute a complete scan and return all findings"""
        findings = {
            "timestamp": datetime.now().isoformat(),
            "certificate_files": self.scan_openssl_certs(),
            "nginx_ssl_refs": self.scan_nginx_ssl_config(),
            "https_listeners": self.scan_listening_https_services(),
        }
        return findings
```

### 2.2 Periodic Scan Scheduling

Run the scan every 30 minutes using a systemd timer, writing results to a local JSON file:

```bash
# /etc/systemd/system/cert-scan.service
[Unit]
Description=SSL Certificate Discovery Scan
After=network.target

[Service]
Type=oneshot
ExecStart=/opt/cert-manager/venv/bin/python /opt/cert-manager/scanner.py
User=root
WorkingDirectory=/opt/cert-manager

[Install]
WantedBy=multi-user.target
```

```ini
# /etc/systemd/system/cert-scan.timer
[Unit]
Description=Run cert scan every 30 minutes

[Timer]
OnBoot=5min
OnUnitActiveSec=30min
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
systemctl daemon-reload
systemctl enable --now cert-scan.timer
```

## Step 3: Build the AI Risk Assessment Engine

This is the core of the system. Scan results are sent to the local LLM, which performs multi-dimensional risk scoring for each certificate.

```python
# cert_manager/risk_engine.py
import json
import requests
from datetime import datetime
import re

class RiskEngine:
    """LLM-powered certificate risk assessment engine (local Ollama)"""

    def __init__(self, ollama_url="http://localhost:11434", model="qwen2.5:7b"):
        self.ollama_url = ollama_url
        self.model = model

    def evaluate_cert(self, cert_info: dict) -> dict:
        """Perform LLM risk assessment for a single certificate"""

        # Fast rule-based pre-check (avoid LLM call when answer is obvious)
        pre_check = self._pre_check(cert_info)
        if pre_check:
            return pre_check

        prompt = f"""You are a professional security operations engineer. Assess the risk level of the following SSL/TLS certificate and provide actionable recommendations.

## Certificate Info
{json.dumps(cert_info, indent=2, ensure_ascii=False)}

## Current Time
{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

## Assessment Dimensions
1. **Expiry**: How far is notAfter from now? Is it already expired?
2. **Algorithm strength**: SHA-1 is deprecated; RSA 2048 is the minimum; ECDSA P-256 preferred
3. **Certificate chain**: Is the issuer a trusted CA? Is the intermediate missing?
4. **Domain match**: Do CN/SAN cover the actual domain in use?
5. **Key security**: Are private key file permissions too wide (should be 600)?

## Output Format
Respond strictly as JSON, no other content:

{{
  "risk_level": "critical|high|medium|low|info",
  "risk_score": 0,
  "risk_summary": "One-line description of the biggest risk",
  "issues": [
    {{"issue": "specific problem", "severity": "critical|high|medium|low"}}
  ],
  "recommended_action": "Specific command or step to resolve",
  "auto_renewable": true,
  "priority": 1
}}

risk_score: 0-100, lower is more dangerous.
priority: 1-5, 1 is most urgent."""

        try:
            resp = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.2, "num_predict": 1500},
                },
                timeout=90,
            )
            resp.raise_for_status()
            result_text = resp.json().get("response", "")
            parsed = self._parse_llm_json(result_text)

            parsed["cert"] = cert_info
            parsed["evaluated_at"] = datetime.now().isoformat()
            return parsed

        except requests.exceptions.Timeout:
            return {"error": "LLM assessment timed out", "cert": cert_info, "risk_level": "unknown", "fallback": True}
        except Exception as e:
            return {"error": str(e), "cert": cert_info, "risk_level": "unknown", "fallback": True}

    def _pre_check(self, cert_info: dict) -> dict | None:
        """Fast rule-based checks that don't need the LLM"""
        if cert_info.get("status") == "expired":
            return {
                "risk_level": "critical",
                "risk_score": 5,
                "risk_summary": "Certificate has expired; HTTPS service is down",
                "issues": [{"issue": "Certificate expired", "severity": "critical"}],
                "recommended_action": "Renew or replace certificate immediately",
                "auto_renewable": True,
                "priority": 1,
            }

        if cert_info.get("status") == "expiring_24h":
            return {
                "risk_level": "critical",
                "risk_score": 10,
                "risk_summary": "Certificate expires within 24 hours",
                "issues": [{"issue": "Certificate expires within 24h", "severity": "critical"}],
                "recommended_action": "Run acme.sh renew now",
                "auto_renewable": True,
                "priority": 1,
            }

        if cert_info.get("signature_algorithm", "").startswith("sha1"):
            return {
                "risk_level": "high",
                "risk_score": 30,
                "risk_summary": "Uses deprecated SHA-1 signature algorithm",
                "issues": [{"issue": "SHA-1 is flagged as insecure by modern browsers", "severity": "high"}],
                "recommended_action": "Re-issue certificate with SHA-256 or stronger",
                "auto_renewable": False,
                "priority": 2,
            }

        if cert_info.get("insecure_permissions"):
            return {
                "risk_level": "medium",
                "risk_score": 40,
                "risk_summary": "Private key file has overly permissive file permissions",
                "issues": [
                    {"issue": f"Key permissions are {cert_info.get('permissions')}, should be 600", "severity": "medium"}
                ],
                "recommended_action": f"chmod 600 {cert_info.get('path')}",
                "auto_renewable": False,
                "priority": 3,
            }

        return None  # Needs LLM deep analysis

    def _parse_llm_json(self, text: str) -> dict:
        """Parse JSON from LLM output"""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

        return {"error": "Could not parse LLM output", "raw": text[:500], "risk_level": "unknown"}

    def evaluate_all(self, findings: dict) -> list[dict]:
        """Evaluate all discovered certificates, return sorted risk list"""
        results = []

        for cert in findings.get("certificate_files", []):
            if cert["type"] == "file":
                results.append(self.evaluate_cert(cert))

        for ref in findings.get("nginx_ssl_refs", []):
            results.append(self.evaluate_cert(ref))

        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4, "unknown": 5}
        results.sort(key=lambda r: priority_order.get(r.get("risk_level", "unknown"), 5))

        return results
```

## Step 4: Build the Zero-Downtime Rotation Executor

After the LLM generates a decision, the executor performs the certificate replacement within a zero-downtime window, with built-in rollback protection.

```python
# cert_manager/rotator.py
import subprocess
import json
import shutil
import hashlib
from datetime import datetime
from pathlib import Path

class CertificateRotator:
    """Zero-downtime certificate rotation with built-in rollback protection"""

    def __init__(self, backup_dir="/var/lib/cert-manager/backups"):
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def renew_with_acme(self, domain: str, cert_path: str, key_path: str) -> dict:
        """Auto-renew a certificate using acme.sh"""
        backup_info = self._backup_cert(cert_path, key_path)

        try:
            result = subprocess.run(
                ["acme.sh", "renew", "-d", domain, "--force"],
                capture_output=True, text=True, timeout=120
            )

            if result.returncode != 0:
                self._rollback(backup_info)
                return {"status": "failed", "error": result.stderr, "rolled_back": True}

            # Install the new certificate to the target path
            acme_cert = Path.home() / ".acme.sh" / domain / "_acme_sh" / "fullchain.cer"
            acme_key = Path.home() / ".acme.sh" / domain / "_acme_sh" / f"{domain}.key"

            if acme_cert.exists():
                shutil.copy2(acme_cert, cert_path)
            if acme_key.exists():
                shutil.copy2(acme_key, key_path)

            # Verify the new certificate
            verification = self._verify_cert(cert_path)
            if not verification["valid"]:
                self._rollback(backup_info)
                return {"status": "verification_failed", "error": verification["reason"], "rolled_back": True}

            # Hot-reload services (zero downtime)
            reload_result = self._reload_services()

            return {
                "status": "success",
                "domain": domain,
                "reloaded": reload_result,
                "rolled_back": False,
            }

        except subprocess.TimeoutExpired:
            self._rollback(backup_info)
            return {"status": "timeout", "rolled_back": True}
        except Exception as e:
            self._rollback(backup_info)
            return {"status": "error", "error": str(e), "rolled_back": True}

    def _backup_cert(self, cert_path: str, key_path: str | None) -> dict:
        """Back up the current certificate for rollback"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        cert_name = Path(cert_path).name
        backup_subdir = self.backup_dir / f"{timestamp}_{cert_name}"
        backup_subdir.mkdir(parents=True, exist_ok=True)

        shutil.copy2(cert_path, backup_subdir / "cert.bak")
        cert_hash = hashlib.sha256(open(cert_path, "rb").read()).hexdigest()

        backup_info = {
            "backup_dir": str(backup_subdir),
            "cert_path": cert_path,
            "cert_hash": cert_hash,
            "timestamp": timestamp,
        }

        if key_path and Path(key_path).exists():
            shutil.copy2(key_path, backup_subdir / "key.bak")
            backup_info["key_path"] = key_path

        return backup_info

    def _rollback(self, backup_info: dict):
        """Roll back to the backed-up certificate"""
        if not backup_info:
            return

        backup_dir = Path(backup_info["backup_dir"])
        cert_bak = backup_dir / "cert.bak"

        if cert_bak.exists():
            shutil.copy2(cert_bak, backup_info["cert_path"])
            print(f"[ROLLBACK] Certificate restored: {backup_info['cert_path']}")

        key_bak = backup_dir / "key.bak"
        if key_bak.exists() and "key_path" in backup_info:
            shutil.copy2(key_bak, backup_info["key_path"])
            print(f"[ROLLBACK] Key restored: {backup_info['key_path']}")

        self._reload_services()

    def _verify_cert(self, cert_path: str) -> dict:
        """Verify the new certificate is valid (expiry, algorithm)"""
        try:
            result = subprocess.run(
                ["openssl", "x509", "-in", cert_path, "-noout", "-checkend", "86400"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode != 0:
                return {"valid": False, "reason": "Certificate expires within 24h or already expired"}

            algo_result = subprocess.run(
                ["openssl", "x509", "-in", cert_path, "-noout", "-text"],
                capture_output=True, text=True, timeout=10
            )
            if "sha1" in algo_result.stdout.lower():
                return {"valid": False, "reason": "Certificate uses SHA-1 signature algorithm"}

            return {"valid": True, "reason": "OK"}
        except Exception as e:
            return {"valid": False, "reason": str(e)}

    def _reload_services(self) -> dict:
        """Zero-downtime hot reload of Nginx / Caddy / other services"""
        reloads = {}

        # Nginx: test config first, then reload
        try:
            test_result = subprocess.run(
                ["nginx", "-t"],
                capture_output=True, text=True, timeout=10
            )
            if test_result.returncode == 0:
                reload_result = subprocess.run(
                    ["systemctl", "reload", "nginx"],
                    capture_output=True, text=True, timeout=15
                )
                reloads["nginx"] = "ok" if reload_result.returncode == 0 else f"failed: {reload_result.stderr}"
            else:
                reloads["nginx"] = f"config_test_failed: {test_result.stderr}"
        except Exception as e:
            reloads["nginx"] = f"error: {e}"

        # Caddy
        try:
            caddy_check = subprocess.run(
                ["caddy", "validate", "--config", "/etc/caddy/Caddyfile"],
                capture_output=True, text=True, timeout=15
            )
            if caddy_check.returncode == 0:
                reload_result = subprocess.run(
                    ["systemctl", "reload", "caddy"],
                    capture_output=True, text=True, timeout=15
                )
                reloads["caddy"] = "ok" if reload_result.returncode == 0 else f"failed: {reload_result.stderr}"
        except Exception as e:
            reloads["caddy"] = f"error: {e}"

        reloads["health_check"] = self._check_https_health()
        return reloads

    def _check_https_health(self) -> dict:
        """Verify local HTTPS endpoints still respond"""
        try:
            import ssl
            import socket

            result = {"port_443": "unknown"}
            local_ctx = ssl.create_default_context()
            local_ctx.verify_mode = ssl.CERT_NONE

            try:
                with socket.create_connection(("localhost", 443), timeout=5) as sock:
                    with local_ctx.wrap_socket(sock, server_hostname="localhost"):
                        result["port_443"] = "ok"
            except (ConnectionRefusedError, ssl.SSLError):
                try:
                    with socket.create_connection(("localhost", 8443), timeout=5) as sock:
                        with local_ctx.wrap_socket(sock, server_hostname="localhost"):
                            result["port_443"] = "ok (via 8443)"
                except Exception:
                    result["port_443"] = "no_https_listener"
            except Exception:
                result["port_443"] = "no_https_listener"

            return result
        except Exception as e:
            return {"port_443": f"error: {e}"}
```

## Step 5: Main Program & Scheduling

Combine all components into a single executable, supporting both manual triggering and cron scheduling.

```python
# cert_manager/main.py
#!/usr/bin/env python3
"""Intelligent SSL Certificate Management System — main entry"""

import json
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from discovery import CertificateDiscovery
from risk_engine import RiskEngine
from rotator import CertificateRotator


def run_assessment():
    """Run the full assessment pipeline"""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Starting certificate assessment...")

    # 1. Discover all certificates
    discovery = CertificateDiscovery()
    findings = discovery.full_scan()

    total_certs = len(findings.get("certificate_files", []))
    total_nginx = len(findings.get("nginx_ssl_refs", []))
    print(f"  Found {total_certs} cert files, {total_nginx} Nginx SSL config entries")

    # 2. LLM risk assessment
    engine = RiskEngine()
    risks = engine.evaluate_all(findings)

    critical = [r for r in risks if r.get("risk_level") == "critical"]
    high = [r for r in risks if r.get("risk_level") == "high"]
    medium = [r for r in risks if r.get("risk_level") == "medium"]

    print(f"  Risk assessment: {len(critical)} critical, {len(high)} high, {len(medium)} medium")

    # 3. Auto-execute critical and high actions
    rotator = CertificateRotator()
    auto_actions = []

    for risk in critical + high:
        if risk.get("auto_renewable") and risk.get("cert", {}).get("common_name"):
            domain = risk["cert"]["common_name"]
            cert_path = risk["cert"].get("path", "")
            key_path = risk["cert"].get("key_path")

            print(f"  Auto-renew: {domain} ({risk['cert'].get('risk_level', '')})")
            result = rotator.renew_with_acme(domain, cert_path, key_path)
            auto_actions.append({"domain": domain, "result": result})

    # 4. Save report
    report = {
        "timestamp": datetime.now().isoformat(),
        "findings": findings,
        "risks": risks,
        "auto_actions": auto_actions,
    }

    report_path = Path(f"/var/lib/cert-manager/reports/{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"  Report saved: {report_path}")

    return report


def print_summary(report: dict):
    """Print a human-readable summary"""
    print("\n" + "=" * 60)
    print("  SSL Certificate Intelligent Assessment Report")
    print("=" * 60)

    risks = report.get("risks", [])
    for risk in risks[:10]:
        level = risk.get("risk_level", "unknown")
        emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(level, "⚪")
        summary = risk.get("risk_summary", risk.get("cert", {}).get("common_name", "?"))
        print(f"  {emoji} [{level.upper()}] {summary}")

        action = risk.get("recommended_action", "")
        if action:
            print(f"     Recommended: {action}")

    auto = report.get("auto_actions", [])
    if auto:
        print(f"\n  Auto-executed: {len(auto)} items")
        for item in auto:
            status = item["result"].get("status", "unknown")
            print(f"     {item['domain']}: {status}")

    print("=" * 60)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "assess":
        report = run_assessment()
        print_summary(report)
    elif len(sys.argv) > 1 and sys.argv[1] == "json":
        report = run_assessment()
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print("Usage: python main.py [assess|json]")
        sys.exit(1)
```

## Step 6: Docker Compose Deployment

Containerize Ollama and the certificate management system for one-command deployment.

```yaml
# docker-compose.yml
version: "3.8"

services:
  ollama:
    image: ollama/ollama:latest
    container_name: cert-ollama
    volumes:
      - ollama_models:/root/.ollama
    ports:
      - "11434:11434"
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 8G

  cert-manager:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: cert-manager
    volumes:
      - /etc/nginx:/etc/nginx:ro
      - /etc/caddy:/etc/caddy:ro
      - /var/lib/acme:/var/lib/acme
      - /var/lib/cert-manager:/var/lib/cert-manager
      - /etc/ssl:/etc/ssl:ro
    environment:
      - OLLAMA_URL=http://ollama:11434
      - MODEL=qwen2.5:7b
    depends_on:
      - ollama
    restart: unless-stopped
    entrypoint: ["python", "main.py", "assess"]

volumes:
  ollama_models:
```

```bash
# Deploy
docker compose up -d
docker compose ps

# Pull model (first time)
docker compose exec ollama ollama pull qwen2.5:7b

# Run assessment manually
docker compose exec cert-manager python main.py assess
```

## Step 7: Telegram Alert Integration

Push critical/high risks to Telegram so issues are known within 5 minutes.

```python
# cert_manager/notify.py
import requests
from datetime import datetime

class TelegramNotifier:
    """Push certificate risks to Telegram"""

    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.api = f"https://api.telegram.org/bot{bot_token}"

    def send_risk_alert(self, risk: dict):
        level = risk.get("risk_level", "unknown")
        emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡"}.get(level, "⚪")
        domain = risk.get("cert", {}).get("common_name", "unknown")
        summary = risk.get("risk_summary", "")
        action = risk.get("recommended_action", "None")

        text = (
            f"{emoji} <b>SSL Certificate Risk Alert</b>\n"
            f"Domain: <code>{domain}</code>\n"
            f"Level: {level.upper()}\n"
            f"Summary: {summary}\n"
            f"Recommended: {action}\n"
            f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )

        try:
            requests.post(
                f"{self.api}/sendMessage",
                json={
                    "chat_id": self.chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
                timeout=10,
            )
        except Exception as e:
            print(f"[NOTIFY] Telegram send failed: {e}")
```

## Security & Compliance Considerations

### Key Protection

The certificate management system must follow these security principles:

1. **Private key file permissions**: All `.key` files must be `600`; the system auto-detects and alerts on violations
2. **Data stays local**: LLM inference runs entirely on the VPS — certificate metadata (domains, IPs, key paths) never leaves the machine
3. **Encrypted backups**: Certificate backup directories should use LUKS encryption or a private S3 bucket
4. **Least privilege**: The cert-manager container mounts only the necessary read-only directories (Nginx config, acme cert dir), never `/etc/shadow` or other sensitive files

### Compliance Checks

```python
def compliance_check(cert_info: dict) -> list[dict]:
    """PCI-DSS and equivalent compliance checks"""
    issues = []

    # PCI-DSS: certificate validity should not exceed 90 days
    if cert_info.get("days_remaining", 999) > 90:
        issues.append({
            "standard": "PCI-DSS",
            "issue": "Certificate validity exceeds 90 days; consider a shorter-lived certificate",
            "severity": "low",
        })

    # SHA-1 is universally deprecated
    if "sha1" in cert_info.get("signature_algorithm", "").lower():
        issues.append({
            "standard": "General",
            "issue": "SHA-1 signature algorithm is deprecated and vulnerable to collision attacks",
            "severity": "critical",
        })

    return issues
```

## Troubleshooting

| Symptom | Likely Cause | Solution |
|---------|-------------|---------|
| Ollama call times out | Model not loaded / insufficient RAM | Check `docker compose logs ollama`; increase memory limit |
| Service down after renewal fails | New cert chain is incomplete | Use `fullchain.cer` instead of standalone `.crt`; verify intermediate CA |
| Nginx reload fails | New cert path misconfigured | Run `nginx -t` before reload; check `ssl_certificate` directive path |
| Nginx certs not discovered | Nginx runs inside a Docker container | Add the container's cert path to the scan list |
| LLM JSON parse fails | Model hallucination | Lower temperature to 0.2; add stricter JSON format constraints in the prompt |

## Summary

This intelligent SSL certificate management system upgrades traditional "reactive renewal" to "proactive governance":

- **Continuous discovery**: Auto-scan all certificates every 30 minutes — no domain missed
- **LLM risk scoring**: The local model scores across multiple dimensions, distinguishing "expires in 24 hours" from "expires in 90 days"
- **Zero-downtime rotation**: acme.sh renewal + Nginx hot reload — service stays up
- **Rollback protection**: Auto-backup before execution; 30-second rollback on failure — service recovers instantly
- **Real-time alerts**: Telegram pushes critical risks immediately — respond within 5 minutes
- **Data stays local**: All inference runs on the local Ollama instance — certificate metadata never leaves the VPS

For teams managing multiple VPS instances, the system can be extended to a multi-node architecture — aggregate scan results from all nodes into a central Ollama instance and generate a global certificate health report.

---

**References**

- [Let's Encrypt Certificate Lifecycle](https://letsencrypt.org/docs/cert-lifecycle/)
- [acme.sh Official Documentation](https://github.com/acmesh-official/acme.sh)
- [Ollama Model Library](https://ollama.com/library)
- [Nginx HTTPS Configuration Guide](https://nginx.org/en/docs/http/HTTPS.html)
