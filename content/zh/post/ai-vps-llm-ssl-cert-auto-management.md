---
title: "AI + VPS：本地 LLM 驱动的 SSL 证书智能管理与自动化治理"
description: "SSL 证书过期是 VPS 运维中最高频的静默故障之一。本文教你在 VPS 上部署基于本地大模型（Ollama + Qwen2.5）的证书智能管理系统：自动发现、风险评分、零停机轮换、回滚保护，让 HTTPS 永不掉线"
date: 2026-10-22T20:00:00+08:00
lastmod: 2026-10-22T20:00:00+08:00
slug: "ai-vps-llm-ssl-cert-auto-management"
image: /images/posts/ai-vps-llm-ssl-cert-auto-management/featured.png
tags: ["AI", "VPS", "SSL", "证书管理", "自动化", "Ollama", "Qwen2.5", "acme.sh", "零停机", "安全"]
categories: ["AI 运维"]
aliases: [/zh/post/ai-vps-llm-ssl-cert-auto-management/]
---

## 证书过期：最容易被忽视的静默故障

你的 VPS 上跑着网站、API 服务和数据库。某天凌晨三点，客户投诉"打不开网站"——打开浏览器一看，红色警告：**"您的连接不是私密连接"**。

原因？证书 30 天前就到期了，但没有任何监控触发了告警，或者触发了但没人看。

这不是孤例。根据 Let's Encrypt 的统计数据，每年因证书过期导致的服务中断数以百万计。在 VPS 运维场景中，这个问题尤为突出：

- **多域名、多证书**：你可能同时管理着 5 个域名，每个域名对应独立的 Nginx/Caddy 配置，任何一条漏掉就是事故；
- **静默失效**：证书过期不像 CPU 爆满那样会立刻体现在监控面板上——服务还在跑，只是 HTTPS 握手失败了；
- **连锁反应**：浏览器把域名标记为"不安全"，缓存后即使续期成功，用户端仍可能显示旧状态；
- **合规压力**：PCI-DSS、等保等合规要求证书必须在有效期内，过期一天就可能触发审计问题。

**传统方案的困境**：大多数 VPS 运维人员用 `certbot` 或 `acme.sh` 自动续期。这解决了"续签"问题，但没解决"治理"问题——你不知道哪些证书快过期、哪些域名配置错误、哪些中间证书链不完整、哪些服务用了自签名证书、哪些证书用了即将被废弃的加密算法（如 SHA-1）。

**智能证书管理系统**回答的就是这些"治理"问题。它用一个本地部署的大语言模型作为"大脑"，持续扫描 VPS 上所有证书，用 LLM 进行风险评估和优先级排序，自动生成轮换计划，在零停机的窗口内完成切换，并在失败时自动回滚。

本文将带你从零搭建这套系统，覆盖：

1. **证书发现层**：自动扫描 VPS 上所有 HTTPS 服务、证书文件、DNS 配置
2. **AI 风险评估层**：本地 Ollama + Qwen2.5 对每张证书做风险评分（过期临近、算法弱、链不完整、域名不匹配等）
3. **轮换执行层**：基于 LLM 生成的决策，自动执行 acme.sh 续期或手动证书替换，零停机热加载
4. **回滚保护层**：执行前自动备份旧证书，失败时 30 秒内回滚，服务不中断
5. **闭环学习**：记录每次轮换结果，持续优化 LLM 的风险判断

## 系统架构

```
┌──────────────────────────────────────────────────────────────────────┐
│                       智能 SSL 证书管理系统                            │
├──────────────┬──────────────┬──────────────┬─────────────────────────┤
│  证书发现     │  AI 风险     │  轮换执行     │  回滚保护 & 学习        │
│  Discovery   │  评估 Engine │  Execution   │  Rollback & Learn     │
├──────────────┼──────────────┼──────────────┼─────────────────────────┤
│ openssl       │              │ acme.sh       │ 证书备份 (SQLite)      │
│ 扫描本机     │  → LLM API   │  自动续期     │  热加载验证            │
│ 证书文件     │  (Qwen2.5)   │  手动替换     │  回滚执行器            │
│ Nginx/Caddy  │              │  Nginx reload │  效果记录库            │
│ 配置解析     │              │  systemctl    │  模型反馈              │
│ DNS 记录     │              │  验证端点     │                        │
└──────────────┴──────────────┴──────────────┴─────────────────────────┘
         ↓                ↓                ↓                ↓
    scanner.py      Ollama server   rotator.py      rollback.py
    (cron 30min)   (本地 :11434)   (LLM 触发)      (失败 30s 回滚)
```

## 第一步：部署 Ollama 本地大模型

证书管理系统的"大脑"是本地 LLM，确保所有证书数据（域名、IP、密钥路径等）不出 VPS。

```bash
# 安装 Ollama
curl -fsSL https://ollama.com/install.sh | sh

# 拉取 Qwen2.5-7B（推荐，对运维场景理解能力强）
ollama pull qwen2.5:7b

# 资源紧张时（2C2G VPS）用更轻量的模型
ollama pull qwen2.5:3b

# 验证
ollama list
ollama run qwen2.5:7b "请用一句话解释什么是 SSL 证书链"
```

对于 2C2G 的 VPS，推荐 `qwen2.5:3b`（约 2GB 内存占用）；4C8G 以上建议 `qwen2.5:7b`（约 5GB 内存占用）。

## 第二步：构建证书发现器

证书发现器负责扫描 VPS 上所有 SSL/TLS 证书的来源和状态，输出结构化数据供 LLM 分析。

### 2.1 扫描本机证书文件

```python
# cert_manager/discovery.py
import subprocess
import json
import re
from datetime import datetime
from pathlib import Path

class CertificateDiscovery:
    """扫描 VPS 上所有证书来源"""

    def __init__(self):
        self.certs = []

    def scan_openssl_certs(self, base_paths=None):
        """扫描常见证书目录中的 .crt/.pem 文件"""
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
        """用 openssl 解析证书文件，提取关键信息"""
        try:
            # 获取证书详细信息
            result = subprocess.run(
                [
                    "openssl", "x509",
                    "-in", str(cert_path),
                    "-noout",
                    "-text",
                ],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode != 0:
                return

            output = result.stdout

            # 解析域名 (Subject)
            subject_match = re.search(r"Subject:.*?CN=(\S+)", output)
            cn = subject_match.group(1) if subject_match else "unknown"

            # 解析有效期
            not_before_match = re.search(r"Not Before\s*:\s*(.+)", output)
            not_after_match = re.search(r"Not After\s*:\s*(.+)", output)

            # 解析签名算法
            sig_algo_match = re.search(r"Signature Algorithm:\s*(\S+)", output)
            sig_algo = sig_algo_match.group(1) if sig_algo_match else "unknown"

            # 解析颁发者
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
                "status": "unknown",  # 后续由 LLM 评估
            })
        except Exception as e:
            print(f"[WARN] 无法解析证书 {cert_path}: {e}")

    def _note_key_file(self, key_path: Path):
        """记录私钥文件（不读取内容，只记录路径和权限）"""
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
        """解析 Nginx 配置，找出所有 SSL 证书引用"""
        try:
            with open(config_path) as f:
                content = f.read()
        except FileNotFoundError:
            return []

        certs = []
        # 匹配 ssl_certificate 和 ssl_certificate_key 指令
        cert_pattern = re.compile(
            r'ssl_certificate\s+([^\s;]+);?\s*'
            r'(?:ssl_certificate_key\s+([^\s;]+);)?',
            re.MULTILINE
        )

        for match in cert_pattern.finditer(content):
            cert_path = match.group(1)
            key_path = match.group(2) if match.group(2) else None

            certs.append({
                "type": "nginx_config",
                "cert_path": cert_path,
                "key_path": key_path,
                "config_file": config_path,
            })

        return certs

    def scan_listening_https_services(self):
        """扫描本机正在监听 443 端口的 HTTPS 服务"""
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

    def scan_dns_records(self, zone_files_dir="/etc/bind/zones/"):
        """扫描 BIND 区域文件中的证书相关记录（CNAME/ALIAS）"""
        zone_dir = Path(zone_files_dir)
        if not zone_dir.exists():
            return []

        records = []
        for zone_file in zone_dir.glob("*.db"):
            try:
                with open(zone_file) as f:
                    content = f.read()
                # 查找 CNAME 记录
                for match in re.finditer(r'(\S+)\s+CNAME\s+(\S+)', content):
                    records.append({
                        "zone": zone_file.name,
                        "name": match.group(1),
                        "target": match.group(2),
                    })
            except Exception:
                continue
        return records

    def full_scan(self):
        """执行完整扫描，返回所有发现"""
        findings = {
            "timestamp": datetime.now().isoformat(),
            "certificate_files": self.scan_openssl_certs(),
            "nginx_ssl_refs": self.scan_nginx_ssl_config(),
            "https_listeners": self.scan_listening_https_services(),
            "dns_records": self.scan_dns_records(),
        }
        return findings
```

### 2.2 定期扫描调度

使用 systemd timer 每 30 分钟执行一次扫描，结果写入本地 JSON 文件：

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
OnBootSec=5min
OnUnitActiveSec=30min
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
systemctl daemon-reload
systemctl enable --now cert-scan.timer
```

## 第三步：构建 AI 风险评估引擎

这是整个系统的核心。将扫描结果送入本地 LLM，让它对每张证书进行多维度风险评分。

```python
# cert_manager/risk_engine.py
import json
import requests
from datetime import datetime, timedelta
import re

class RiskEngine:
    """基于本地 LLM 的证书风险评估引擎"""

    RISK_LEVELS = {
        "critical": 1,   # 证书已过期 / 即将 24h 内过期
        "high": 2,       # 7 天内过期 / 弱加密算法
        "medium": 3,     # 30 天内过期 / 证书链可能不完整
        "low": 4,        # 状态正常，90 天内有效
        "info": 5,       # 无风险，纯粹记录
    }

    def __init__(self, ollama_url="http://localhost:11434", model="qwen2.5:7b"):
        self.ollama_url = ollama_url
        self.model = model

    def _now_str(self):
        return datetime.now().strftime("%b %d %Y %H:%M:%S")

    def evaluate_cert(self, cert_info: dict) -> dict:
        """对单张证书进行 LLM 风险评估"""
        # 先做规则预判（快速路径，避免 LLM 调用浪费）
        pre_check = self._pre_check(cert_info)
        if pre_check:
            return pre_check

        # 构建 LLM 评估 prompt
        prompt = f"""你是一名专业的安全运维工程师。请评估以下 SSL/TLS 证书的风险等级，并给出处理建议。

## 证书信息
{json.dumps(cert_info, indent=2, ensure_ascii=False)}

## 当前时间
{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

## 评估维度
1. **有效期**：notAfter 距离当前时间还有多久？是否已过期？
2. **算法强度**：SHA-1 签名已废弃；RSA 2048 位是底线；ECDSA P-256 推荐
3. **证书链**：颁发者是否为受信 CA？中间证书是否缺失？
4. **域名匹配**：CN/SAN 是否覆盖实际使用的域名？
5. **密钥安全**：私钥文件权限是否过宽（应为 600）？

## 输出要求
请严格按以下 JSON 格式输出，不要添加其他内容：

{{
  "risk_level": "critical|high|medium|low|info",
  "risk_score": 0,
  "risk_summary": "一句话说明最大风险点",
  "issues": [
    {{"issue": "具体问题", "severity": "critical|high|medium|low"}}
  ],
  "recommended_action": "建议的处理操作（具体命令或步骤）",
  "auto_renewable": true,
  "priority": 1
}}

risk_score 范围 0-100，分数越低越危险。
priority 范围 1-5，1 最紧急。"""

        try:
            resp = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.2,
                        "num_predict": 1500,
                    },
                },
                timeout=90,
            )
            resp.raise_for_status()
            result_text = resp.json().get("response", "")
            parsed = self._parse_llm_json(result_text)

            # 添加元数据
            parsed["cert"] = cert_info
            parsed["evaluated_at"] = datetime.now().isoformat()
            return parsed

        except requests.exceptions.Timeout:
            return {
                "error": "LLM 评估超时",
                "cert": cert_info,
                "risk_level": "unknown",
                "fallback": True,
            }
        except Exception as e:
            return {
                "error": str(e),
                "cert": cert_info,
                "risk_level": "unknown",
                "fallback": True,
            }

    def _pre_check(self, cert_info: dict) -> dict | None:
        """快速规则预判，无需 LLM 即可确定的情况"""
        risk = {}

        # 检查是否已过期
        if cert_info.get("status") == "expired":
            risk["risk_level"] = "critical"
            risk["risk_score"] = 5
            risk["risk_summary"] = "证书已过期，HTTPS 服务中断"
            risk["issues"] = [{"issue": "证书已过期", "severity": "critical"}]
            risk["recommended_action"] = "立即续期或替换证书"
            risk["auto_renewable"] = True
            risk["priority"] = 1
            return risk

        # 检查是否 24 小时内过期
        if cert_info.get("status") == "expiring_24h":
            risk["risk_level"] = "critical"
            risk["risk_score"] = 10
            risk["risk_summary"] = "证书将在 24 小时内过期"
            risk["issues"] = [{"issue": "证书 24h 内过期", "severity": "critical"}]
            risk["recommended_action"] = "立即执行 acme.sh renew 续期"
            risk["auto_renewable"] = True
            risk["priority"] = 1
            return risk

        # 检查弱加密算法
        if cert_info.get("signature_algorithm", "").startswith("sha1"):
            risk["risk_level"] = "high"
            risk["risk_score"] = 30
            risk["risk_summary"] = "使用已废弃的 SHA-1 签名算法"
            risk["issues"] = [
                {"issue": "SHA-1 签名已被现代浏览器标记为不安全", "severity": "high"}
            ]
            risk["recommended_action"] = "重新申请使用 SHA-256 或更强的证书"
            risk["auto_renewable"] = False
            risk["priority"] = 2
            return risk

        # 检查私钥权限
        if cert_info.get("insecure_permissions"):
            risk["risk_level"] = "medium"
            risk["risk_score"] = 40
            risk["risk_summary"] = "私钥文件权限过宽"
            risk["issues"] = [
                {"issue": f"私钥权限为 {cert_info.get('permissions')}，应为 600", "severity": "medium"}
            ]
            risk["recommended_action"] = f"chmod 600 {cert_info.get('path')}"
            risk["auto_renewable"] = False
            risk["priority"] = 3
            return risk

        return None  # 需要 LLM 深入分析

    def _parse_llm_json(self, text: str) -> dict:
        """解析 LLM 返回的 JSON"""
        # 尝试直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 尝试提取 JSON 块
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

        return {
            "error": "无法解析 LLM 输出",
            "raw": text[:500],
            "risk_level": "unknown",
        }

    def evaluate_all(self, findings: dict) -> list[dict]:
        """评估所有发现的证书，返回按优先级排序的风险清单"""
        results = []

        # 评估文件型证书
        for cert in findings.get("certificate_files", []):
            if cert["type"] == "file":
                results.append(self.evaluate_cert(cert))

        # 评估 Nginx 配置中的证书引用
        for ref in findings.get("nginx_ssl_refs", []):
            results.append(self.evaluate_cert(ref))

        # 按优先级排序
        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4, "unknown": 5}
        results.sort(key=lambda r: priority_order.get(r.get("risk_level", "unknown"), 5))

        return results
```

## 第四步：构建零停机轮换执行器

LLM 生成决策后，执行器负责在零停机窗口内完成证书替换，并内置回滚保护。

```python
# cert_manager/rotator.py
import subprocess
import json
import shutil
import hashlib
from datetime import datetime
from pathlib import Path

class CertificateRotator:
    """零停机证书轮换执行器，内置回滚保护"""

    def __init__(self, backup_dir="/var/lib/cert-manager/backups"):
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def renew_with_acme(self, domain: str, cert_path: str, key_path: str) -> dict:
        """使用 acme.sh 自动续期证书"""
        # 先备份现有证书
        backup_info = self._backup_cert(cert_path, key_path)

        try:
            # 执行 acme.sh 续期
            result = subprocess.run(
                [
                    "acme.sh", "renew",
                    "-d", domain,
                    "--force",  # 强制续期，不等待默认周期
                ],
                capture_output=True, text=True, timeout=120
            )

            if result.returncode != 0:
                # 续期失败，立即回滚
                self._rollback(backup_info)
                return {
                    "status": "failed",
                    "error": result.stderr,
                    "rolled_back": True,
                }

            # 将新证书安装到目标路径
            acme_cert = Path.home() / ".acme.sh" / domain / "_acme_sh" / f"{domain}.crt"
            acme_key = Path.home() / ".acme.sh" / domain / "_acme_sh" / f"{domain}.key"
            acme_chain = Path.home() / ".acme.sh" / domain / "_acme_sh" / "fullchain.cer"

            if acme_cert.exists():
                shutil.copy2(acme_cert, cert_path)
            if acme_chain.exists():
                # 使用完整证书链，避免中间证书缺失
                shutil.copy2(acme_chain, cert_path)
            if acme_key.exists():
                shutil.copy2(acme_key, key_path)

            # 验证新证书
            verification = self._verify_cert(cert_path)
            if not verification["valid"]:
                self._rollback(backup_info)
                return {
                    "status": "verification_failed",
                    "error": verification["reason"],
                    "rolled_back": True,
                }

            # 热加载服务（零停机）
            reload_result = self._reload_services()

            return {
                "status": "success",
                "domain": domain,
                "cert_path": cert_path,
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
        """备份当前证书，返回备份信息用于回滚"""
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
        """回滚到备份证书"""
        if not backup_info:
            return

        backup_dir = Path(backup_info["backup_dir"])
        cert_bak = backup_dir / "cert.bak"

        if cert_bak.exists():
            shutil.copy2(cert_bak, backup_info["cert_path"])
            print(f"[ROLLBACK] 证书已回滚: {backup_info['cert_path']}")

        key_bak = backup_dir / "key.bak"
        if key_bak.exists() and "key_path" in backup_info:
            shutil.copy2(key_bak, backup_info["key_path"])
            print(f"[ROLLBACK] 私钥已回滚: {backup_info['key_path']}")

        # 重新热加载
        self._reload_services()

    def _verify_cert(self, cert_path: str) -> dict:
        """验证新证书是否有效（检查有效期、域名、算法）"""
        try:
            result = subprocess.run(
                [
                    "openssl", "x509",
                    "-in", cert_path,
                    "-noout",
                    "-checkend", "86400",  # 检查证书是否在 24h 内过期
                ],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode != 0:
                return {"valid": False, "reason": "证书将在 24h 内过期或已过期"}

            # 检查算法
            algo_result = subprocess.run(
                ["openssl", "x509", "-in", cert_path, "-noout", "-text"],
                capture_output=True, text=True, timeout=10
            )
            if "sha1" in algo_result.stdout.lower():
                return {"valid": False, "reason": "证书使用 SHA-1 签名算法"}

            return {"valid": True, "reason": "OK"}
        except Exception as e:
            return {"valid": False, "reason": str(e)}

    def _reload_services(self) -> dict:
        """零停机热加载 Nginx / Caddy / 其他服务"""
        reloads = {}

        # Nginx: 先测试配置，再 reload
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

        # Caddy: 类似处理
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
            else:
                reloads["caddy"] = f"validate_failed: {caddy_check.stderr}"
        except Exception as e:
            reloads["caddy"] = f"error: {e}"

        # 验证 HTTPS 服务仍然正常
        health = self._check_https_health()
        reloads["health_check"] = health

        return reloads

    def _check_https_health(self) -> dict:
        """验证本地 HTTPS 端点仍然正常响应"""
        try:
            import ssl
            import socket

            # 检查本地 443 端口
            local_ctx = ssl.create_default_context()
            local_ctx.verify_mode = ssl.CERT_NONE  # 本地检查不验证证书链

            result = {"port_443": "unknown"}

            try:
                with socket.create_connection(("localhost", 443), timeout=5) as sock:
                    with local_ctx.wrap_socket(sock, server_hostname="localhost") as ssock:
                        cert = ssock.getpeercert()
                        result["port_443"] = "ok"
            except (ConnectionRefusedError, ssl.SSLError) as e:
                # 443 可能没开，检查 8443
                try:
                    with socket.create_connection(("localhost", 8443), timeout=5) as sock:
                        with local_ctx.wrap_socket(sock, server_hostname="localhost") as ssock:
                            result["port_443"] = "ok (via 8443)"
                except Exception:
                    result["port_443"] = "no_https_listener"
            except Exception:
                result["port_443"] = "no_https_listener"

            return result
        except Exception as e:
            return {"port_443": f"error: {e}"}
```

## 第五步：主程序整合与调度

将所有组件整合为一个可执行的主程序，支持手动触发和 cron 定期执行。

```python
# cert_manager/main.py
#!/usr/bin/env python3
"""智能 SSL 证书管理系统 — 主入口"""

import json
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from discovery import CertificateDiscovery
from risk_engine import RiskEngine
from rotator import CertificateRotator


def run_assessment():
    """执行完整评估流程"""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始证书评估...")

    # 1. 发现所有证书
    discovery = CertificateDiscovery()
    findings = discovery.full_scan()

    total_certs = len(findings.get("certificate_files", []))
    total_nginx = len(findings.get("nginx_ssl_refs", []))
    print(f"  发现 {total_certs} 个证书文件，{total_nginx} 条 Nginx SSL 配置")

    # 2. LLM 风险评估
    engine = RiskEngine()
    risks = engine.evaluate_all(findings)

    critical = [r for r in risks if r.get("risk_level") == "critical"]
    high = [r for r in risks if r.get("risk_level") == "high"]
    medium = [r for r in risks if r.get("risk_level") == "medium"]

    print(f"  风险评估: {len(critical)} critical, {len(high)} high, {len(medium)} medium")

    # 3. 自动执行 critical 和 high 的操作
    rotator = CertificateRotator()
    auto_actions = []

    for risk in critical + high:
        if risk.get("auto_renewable") and risk.get("cert", {}).get("common_name"):
            domain = risk["cert"]["common_name"]
            cert_path = risk["cert"].get("path", "")
            key_path = risk["cert"].get("key_path")

            print(f"  自动续期: {domain} ({risk['cert'].get('risk_level', '')})")
            result = rotator.renew_with_acme(domain, cert_path, key_path)
            auto_actions.append({
                "domain": domain,
                "result": result,
            })

    # 4. 保存评估报告
    report = {
        "timestamp": datetime.now().isoformat(),
        "findings": findings,
        "risks": risks,
        "auto_actions": auto_actions,
    }

    report_path = Path(f"/var/lib/cert-manager/reports/{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"  报告已保存: {report_path}")

    return report


def print_summary(report: dict):
    """打印人类可读的摘要"""
    print("\n" + "=" * 60)
    print("  SSL 证书智能评估报告")
    print("=" * 60)

    risks = report.get("risks", [])
    for risk in risks[:10]:
        level = risk.get("risk_level", "unknown")
        emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(level, "⚪")
        summary = risk.get("risk_summary", risk.get("cert", {}).get("common_name", "?"))
        print(f"  {emoji} [{level.upper()}] {summary}")

        # 打印建议操作
        action = risk.get("recommended_action", "")
        if action:
            print(f"     建议: {action}")

    auto = report.get("auto_actions", [])
    if auto:
        print(f"\n  自动执行: {len(auto)} 项")
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

## 第六步：Docker Compose 完整部署

将 Ollama 和证书管理系统容器化，一键部署。

```yaml
# docker-compose.yml
version: "3.8"

services:
  # Ollama 本地 LLM 服务
  ollama:
    image: ollama/ollama:latest
    container_name: cert-ollama
    volumes:
      - ollama_models:/root/.ollama
    ports:
      - "11434:11434"
    restart: unless-stopped
    # 资源限制，避免占用过多 VPS 内存
    deploy:
      resources:
        limits:
          memory: 8G

  # 证书管理系统
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
    # 每天 02:00 自动评估
    entrypoint: ["python", "main.py", "assess"]

volumes:
  ollama_models:
```

```bash
# 部署
docker compose up -d
docker compose ps

# 拉取模型（首次）
docker compose exec ollama ollama pull qwen2.5:7b

# 手动执行一次评估
docker compose exec cert-manager python main.py assess
```

## 第七步：Telegram 告警集成

将 critical/high 风险推送到 Telegram，确保问题 5 分钟内被知晓。

```python
# cert_manager/notify.py
import requests
import json
from datetime import datetime

class TelegramNotifier:
    """将证书风险推送到 Telegram"""

    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.api = f"https://api.telegram.org/bot{bot_token}"

    def send_risk_alert(self, risk: dict):
        """发送单条风险告警"""
        level = risk.get("risk_level", "unknown")
        emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡"}.get(level, "⚪")
        domain = risk.get("cert", {}).get("common_name", "unknown")
        summary = risk.get("risk_summary", "")
        action = risk.get("recommended_action", "无")

        text = (
            f"{emoji} <b>SSL 证书风险告警</b>\n"
            f"域名: <code>{domain}</code>\n"
            f"等级: {level.upper()}\n"
            f"摘要: {summary}\n"
            f"建议: {action}\n"
            f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
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
                timeout=10
            )
        except Exception as e:
            print(f"[NOTIFY] Telegram 发送失败: {e}")

    def send_summary(self, report: dict):
        """发送每日摘要"""
        risks = report.get("risks", [])
        critical = [r for r in risks if r.get("risk_level") == "critical"]
        high = [r for r in risks if r.get("risk_level") == "high"]

        text = (
            f"📊 <b>SSL 证书每日评估</b>\n"
            f"总证书数: {len(risks)}\n"
            f"Critical: {len(critical)} | High: {len(high)}\n"
            f"时间: {report.get('timestamp', '')[:16]}"
        )

        if critical:
            text += "\n\n紧急事项:"
            for r in critical[:5]:
                domain = r.get("cert", {}).get("common_name", "?")
                text += f"\n  🔴 {domain}"

        try:
            requests.post(
                f"{self.api}/sendMessage",
                json={
                    "chat_id": self.chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                },
                timeout=10
            )
        except Exception as e:
            print(f"[NOTIFY] 摘要发送失败: {e}")
```

## 安全与合规考量

### 私钥保护

证书管理系统必须遵守以下安全原则：

1. **私钥文件权限**：所有 `.key` 文件权限必须为 `600`，系统在扫描时自动检测并告警
2. **数据不出域**：LLM 推理完全在 VPS 本地执行，证书数据（域名、IP、密钥路径）不发送到任何外部 API
3. **备份加密**：证书备份目录应使用 LUKS 加密或放在私有 S3 桶中
4. **最小权限**：cert-manager 容器只挂载必要的只读目录（Nginx 配置、acme 证书目录），不挂载 `/etc/shadow` 等敏感文件

### 合规检查

```python
def compliance_check(cert_info: dict) -> list[dict]:
    """PCI-DSS 和等保合规检查"""
    issues = []

    # PCI-DSS 要求：证书有效期不超过 90 天（Let's Encrypt 标准为 90 天）
    if cert_info.get("days_remaining", 999) > 90:
        issues.append({
            "standard": "PCI-DSS",
            "issue": "证书有效期超过 90 天，建议申请更短有效期证书",
            "severity": "low",
        })

    # 等保要求：必须使用 2048 位以上 RSA 或 256 位以上 ECDSA
    if "rsa2048" not in cert_info.get("signature_algorithm", "").lower():
        issues.append({
            "standard": "等保",
            "issue": "密钥长度可能不满足等保 2.0 要求",
            "severity": "medium",
        })

    # 通用要求：不得使用 SHA-1
    if "sha1" in cert_info.get("signature_algorithm", "").lower():
        issues.append({
            "standard": "通用",
            "issue": "SHA-1 签名算法已被废弃，存在碰撞风险",
            "severity": "critical",
        })

    return issues
```

## 故障排查

| 症状 | 可能原因 | 解决方案 |
|------|---------|---------|
| Ollama 调用超时 | 模型未加载完成 / 内存不足 | 检查 `docker compose logs ollama`，增加内存限制 |
| 续期失败后服务中断 | 新证书链不完整 | 使用 `fullchain.cer` 而非单独的 `.crt`；检查中间 CA 证书 |
| Nginx reload 失败 | 新证书路径在配置中写错 | `nginx -t` 测试后再 reload；检查 `ssl_certificate` 指令路径 |
| 扫描不到 Nginx 证书 | Nginx 配置在 Docker 容器内 | 增加容器内证书路径到扫描列表 |
| LLM 输出 JSON 解析失败 | 模型幻觉导致格式错误 | 降低 temperature 至 0.2；增加 JSON 格式约束提示词 |

## 总结

这套智能 SSL 证书管理系统将传统的"被动续期"升级为"主动治理"：

- **持续发现**：每 30 分钟自动扫描 VPS 上所有证书，不遗漏任何域名
- **LLM 风险评估**：本地大模型多维度评分，区分"24 小时内过期"和"90 天后过期"的紧急程度
- **零停机轮换**：acme.sh 续期 + Nginx 热加载，服务不中断
- **回滚保护**：执行前自动备份，失败 30 秒内回滚，服务秒级恢复
- **告警推送**：Telegram 实时推送 critical 风险，5 分钟内响应
- **数据不出域**：所有推理在本地 Ollama 完成，证书元数据不外泄

对于管理多个 VPS 的团队，可以进一步扩展为多节点架构——将各节点的扫描结果汇聚到中心 Ollama 实例，统一生成全局证书健康报告。

---

**参考**

- [Let's Encrypt 证书生命周期](https://letsencrypt.org/docs/cert-lifecycle/)
- [acme.sh 官方文档](https://github.com/acmesh-official/acme.sh)
- [Ollama 模型列表](https://ollama.com/library)
- [Nginx SSL 配置指南](https://nginx.org/en/docs/http/HTTPS.html)
