---
title: "AI 驱动 VPS 智能密钥管理：从手工旋转 to 自动化凭证轮换"
description: "VPS 上的 API 密钥、数据库密码、SSH 密钥越来越多，手工管理既危险又低效。本文教你用 AI Agent 搭建智能密钥管理系统——自动检测泄露、智能轮换凭证、预测安全风险，让敏感信息永不出事。"
date: 2026-08-24T20:00:00+08:00
lastmod: 2026-08-24T20:00:00+08:00
slug: "ai-vps-intelligent-secret-management"
tags: ["AI Agent", "VPS运维", "密钥管理", "凭证轮换", "安全运维", "自动化", "HashiCorp Vault", "LLM", "AIOps"]
categories: ["AI运维"]
aliases: [/zh/post/ai-vps-intelligent-secret-management/]
image: /images/posts/ai-vps-intelligent-secret-management/featured.png
draft: false
---

## 引言：你的 VPS 上藏着多少秘密？

打开你的 VPS，SSH 登录进去，运行几条命令：

```bash
grep -r "password\|secret\|api_key\|token" /etc/ /home/ /opt/ 2>/dev/null | head -50
```

你可能会发现：

- 配置文件里硬编码的数据库密码
- `.env` 文件中的 AWS Access Key
- Shell 历史里的临时 token
- Docker Compose 中的明文密钥
- Cron 任务里写死的 API 地址

**每个 VPS 管理员都是秘密的保管者**——数据库密码、API Token、SSH 私钥、SSL 证书、OAuth 密钥……这些敏感信息一旦泄露，后果不堪设想。而传统的管理方式是：

1. 把密钥写在配置文件里
2. 靠人工记住哪些服务用哪些密钥
3. 定期手动轮换（如果记得的话）
4. 出事了再紧急修改

这套流程的问题一目了然：**靠人管密钥，迟早会出事**。

## 为什么 AI 能改变密钥管理？

传统密钥管理工具（如 HashiCorp Vault、AWS Secrets Manager）解决了"存储"问题，但没能解决"管理"问题：

| 痛点 | 传统方案 | AI 增强方案 |
|------|---------|------------|
| 密钥泄露检测 | 依赖人工审计 | LLM 自动扫描代码和配置，语义理解识别潜在泄露 |
| 轮换时机 | 固定周期或手动触发 | AI 分析使用频率、风险等级，智能决定轮换时机 |
| 访问控制 | 静态规则 | AI 学习访问模式，动态调整权限 |
| 故障排查 | 人工对照文档 | LLM 理解密钥依赖关系，快速定位问题 |
| 合规检查 | 手动审计 | AI 自动生成合规报告，持续监控 |

AI 的核心价值在于**理解上下文**——它不仅能找到"看起来像密钥"的字符串，还能理解这个密钥的用途、风险等级、依赖关系，从而做出更智能的管理决策。

## 系统架构：AI 驱动的密钥管理闭环

```
┌─────────────────────────────────────────────────────────────────────┐
│                        AI 密钥管理中心                               │
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │  密钥发现    │  │  风险评分    │  │  智能轮换    │              │
│  │  Scanner    │  │  Engine      │  │  Scheduler   │              │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘              │
│         │                 │                 │                       │
│  ┌──────▼───────┐  ┌──────▼───────┐  ┌──────▼───────┐              │
│  │  LLM 分析    │  │  历史数据    │  │  策略引擎    │              │
│  │  (语义理解)  │  │  (使用统计)  │  │  (合规规则)  │              │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘              │
│         │                 │                 │                       │
│  ┌──────▼─────────────────▼─────────────────▼───────┐              │
│  │              HashiCorp Vault / SOPS              │              │
│  │              (密钥存储与访问控制)                  │              │
│  └──────┬─────────────────┬─────────────────┬───────┘              │
│         │                 │                 │                       │
│  ┌──────▼───────┐  ┌──────▼───────┐  ┌──────▼───────┐              │
│  │  应用服务    │  │  运维脚本    │  │  CI/CD 管道  │              │
│  │  (按需读取)  │  │  (定时轮换)  │  │  (自动注入)  │              │
│  └──────────────┘  └──────────────┘  └──────────────┘              │
│                                                                     │
│  ┌──────────────────────────────────────────────────────┐           │
│  │              AI Agent (Hermes / CrewAI)              │           │
│  │  协调发现→分析→决策→执行→验证的完整闭环               │           │
│  └──────────────────────────────────────────────────────┘           │
└─────────────────────────────────────────────────────────────────────┘
```

## 第一步：智能密钥发现与扫描

AI 驱动密钥管理的第一步是**全面发现**——找出所有散落在你 VPS 上的敏感信息。

### 传统扫描的局限

传统工具（如 `gitleaks`、`truffleHog`）使用正则表达式匹配密钥模式：

```bash
# 传统方案：正则匹配
gitleaks detect --source . --report-format json --report-path report.json
```

这种方法的问题：

1. **误报率高**：匹配到 `password123` 但实际是示例代码
2. **漏报率高**：无法识别环境变量引用、加密存储、动态拼接的密钥
3. **无上下文**：不知道这个密钥的用途和风险等级

### AI 增强的扫描方案

我们用 LLM 增强扫描能力，让它理解密钥的上下文：

```python
import re
import subprocess
from pathlib import Path
import json

class AISecretScanner:
    def __init__(self, llm_client):
        self.llm = llm_client
        self.scan_paths = [
            "/etc/",
            "/home/",
            "/opt/",
            "/var/lib/",
            "/root/",
            ".",  # 当前项目目录
        ]
        # 已知密钥模式（用于预过滤）
        self.patterns = {
            "aws": r"AKIA[0-9A-Z]{16}",
            "github": r"ghp_[0-9a-zA-Z]{36}",
            "slack": r"xox[baprs]-[0-9a-zA-Z-]+",
            "jwt": r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+",
            "generic_key": r"(?i)(api[_-]?key|secret[_-]?key|access[_-]?token)"
                          r"\s*[=:]\s*['\"][^'\"]{8,}['\"]",
        }
    
    def scan_file(self, filepath):
        """扫描单个文件，返回潜在密钥列表"""
        findings = []
        try:
            content = Path(filepath).read_text(errors="ignore")
            lines = content.split("\n")
            
            for i, line in enumerate(lines, 1):
                for key_type, pattern in self.patterns.items():
                    if re.search(pattern, line):
                        findings.append({
                            "file": str(filepath),
                            "line": i,
                            "type": key_type,
                            "content": line.strip()[:200],
                            "context": self._extract_context(lines, i-1),
                        })
        except (PermissionError, UnicodeDecodeError):
            pass
        return findings
    
    def _extract_context(self, lines, line_idx):
        """提取上下文用于 LLM 分析"""
        start = max(0, line_idx - 3)
        end = min(len(lines), line_idx + 4)
        return "\n".join(lines[start:end])
    
    def ai_enrich(self, findings):
        """用 LLM 对发现进行 enrich，判断真实风险和用途"""
        if not findings:
            return []
        
        # 批量发送上下文给 LLM
        prompt = self._build_prompt(findings)
        response = self.llm.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
        )
        
        # 解析 LLM 返回的分析结果
        analysis = json.loads(response.choices[0].message.content)
        
        # 合并原始发现与 AI 分析
        for finding, ai_result in zip(findings, analysis["assessments"]):
            finding.update({
                "risk_level": ai_result["risk"],
                "is_real_secret": ai_result["is_real"],
                "purpose": ai_result.get("purpose", "unknown"),
                "recommended_action": ai_result.get("action", "review"),
            })
        
        return findings
    
    def _build_prompt(self, findings):
        """构建 LLM 分析提示"""
        findings_json = json.dumps(findings, ensure_ascii=False, indent=2)
        return f"""你是一个 VPS 安全专家。请分析以下文件中检测到的潜在密钥，
判断它们是否是真实密钥、风险等级、用途，以及推荐的处置动作。

潜在发现：
{findings_json}

请以 JSON 格式返回分析结果：
{{
  "assessments": [
    {{
      "file": "文件路径",
      "line": 行号,
      "is_real": true/false,
      "risk": "high/medium/low",
      "purpose": "用途描述",
      "action": "recommend/review/dismiss/rotate"
    }}
  ]
}}"""
    
    def run_scan(self):
        """执行完整扫描"""
        all_findings = []
        
        for scan_path in self.scan_paths:
            try:
                for root, dirs, files in os.walk(scan_path):
                    # 跳过系统目录和虚拟环境
                    dirs[:] = [d for d in dirs if d not in 
                              {'.git', '__pycache__', 'node_modules', '.venv'}]
                    
                    for f in files:
                        if f.endswith(('.env', '.yaml', '.yml', '.json', '.toml',
                                       '.conf', '.cfg', '.ini', '.py', '.sh',
                                       '.js', '.ts', '.xml', '.properties')):
                            filepath = Path(root) / f
                            all_findings.extend(self.scan_file(filepath))
            except PermissionError:
                continue
        
        # AI 增强分析
        enriched = self.ai_enrich(all_findings)
        
        # 过滤掉非真实密钥
        real_secrets = [f for f in enriched if f.get("is_real_secret", False)]
        
        return {
            "total_findings": len(all_findings),
            "real_secrets": len(real_secrets),
            "high_risk": len([f for f in real_secrets if f.get("risk_level") == "high"]),
            "secrets": real_secrets,
        }
```

## 第二步：AI 驱动的风险评估与优先级排序

发现密钥只是第一步，更重要的是**判断哪些需要立即处理**。AI 可以根据多个维度对密钥进行风险评分：

```python
class SecretRiskScorer:
    """基于多维度因素的密钥风险评分"""
    
    def score_secret(self, secret_info, system_context):
        """
        计算密钥风险评分 (0-100)
        
        评分维度：
        - 密钥类型敏感度 (0-25)
        - 访问范围 (0-20)
        - 存储方式安全性 (0-20)
        - 轮换历史 (0-15)
        - 最近使用情况 (0-10)
        - 合规要求 (0-10)
        """
        score = 0
        
        # 1. 密钥类型敏感度
        sensitivity_map = {
            "root_password": 25,
            "aws_master_key": 25,
            "database_root": 22,
            "api_key_production": 20,
            "ssh_private_key": 22,
            "jwt_secret": 18,
            "ssl_private_key": 20,
            "api_key_dev": 12,
            "generic_token": 15,
        }
        score += sensitivity_map.get(secret_info.get("type", "generic"), 10)
        
        # 2. 访问范围
        access_scope = secret_info.get("access_scope", "local")
        scope_scores = {
            "local": 5,
            "internal_network": 10,
            "public_facing": 15,
            "internet_exposed": 20,
        }
        score += scope_scores.get(access_scope, 10)
        
        # 3. 存储方式
        storage = secret_info.get("storage", "unknown")
        storage_scores = {
            "vault": 0,      # 已用密钥管理服务
            "encrypted_file": 5,
            "env_file": 10,
            "hardcoded": 20, # 硬编码，最高风险
            "git_commit": 25, # 提交到版本控制，极高风险
        }
        score += storage_scores.get(storage, 15)
        
        # 4. 轮换历史
        days_since_rotation = secret_info.get("days_since_rotation", 999)
        if days_since_rotation > 365:
            score += 15
        elif days_since_rotation > 180:
            score += 10
        elif days_since_rotation > 90:
            score += 5
        
        # 5. 最近使用
        last_used = secret_info.get("last_used_days_ago", 0)
        if last_used > 30:
            score += 5  # 长期未使用的密钥可能是孤儿密钥
        
        # 6. 合规要求
        if system_context.get("compliance_required"):
            score += 10  # 有合规要求的环境，所有密钥风险+10
        
        return min(score, 100)
    
    def prioritize(self, secrets, system_context):
        """对密钥列表进行优先级排序"""
        scored = []
        for secret in secrets:
            risk_score = self.score_secret(secret, system_context)
            secret["risk_score"] = risk_score
            scored.append(secret)
        
        # 按风险评分降序排列
        scored.sort(key=lambda x: x["risk_score"], reverse=True)
        return scored
```

## 第三步：智能轮换策略

传统密钥轮换往往是固定周期的——每 90 天强制轮换一次。但 AI 可以让轮换更智能：

```python
import asyncio
from datetime import datetime, timedelta
import random

class IntelligentRotationScheduler:
    """基于 AI 分析的智能轮换调度器"""
    
    def __init__(self, vault_client, llm_client):
        self.vault = vault_client
        self.llm = llm_client
    
    def determine_rotation_schedule(self, secret_info):
        """
        根据密钥特征动态决定轮换策略
        
        策略维度：
        1. 风险等级 → 高風險密钥更频繁轮换
        2. 使用频率 → 高频使用的密钥更容易被破解，需频繁轮换
        3. 访问范围 → 暴露在公网的密钥需要更短轮换周期
        4. 历史泄露 → 曾经泄露过的密钥需要更严格轮换
        """
        base_interval = 90  # 基础轮换周期（天）
        
        # 风险调整
        risk_multiplier = {
            "critical": 0.3,   # 关键密钥：30天轮换
            "high": 0.5,       # 高风险：45天
            "medium": 0.75,    # 中风险：67天
            "low": 1.0,        # 低风险：90天
        }
        interval = base_interval * risk_multiplier.get(
            secret_info.get("risk_tier", "medium"), 0.75
        )
        
        # 使用频率调整
        usage_count = secret_info.get("daily_usage_count", 0)
        if usage_count > 1000:
            interval *= 0.7  # 超高频使用，缩短 30%
        elif usage_count > 100:
            interval *= 0.85  # 高频使用，缩短 15%
        
        # 访问范围调整
        exposure = secret_info.get("exposure", "internal")
        if exposure == "public":
            interval *= 0.6  # 公网暴露，大幅缩短
        elif exposure == "semi-public":
            interval *= 0.8
        
        # 历史泄露记录调整
        if secret_info.get("past_incidents", 0) > 0:
            interval *= 0.5  # 曾经泄露，轮换频率翻倍
        
        # 加入随机抖动，避免所有密钥同时轮换导致系统压力
        jitter = random.uniform(-0.1, 0.1)
        final_interval = max(7, int(interval * (1 + jitter)))  # 最少 7 天
        
        return final_interval
    
    def generate_rotation_plan(self, secrets):
        """生成轮换计划"""
        plan = []
        today = datetime.now()
        
        for secret in secrets:
            interval = self.determine_rotation_schedule(secret)
            next_rotation = today + timedelta(days=interval)
            
            plan.append({
                "secret_id": secret["id"],
                "name": secret["name"],
                "risk_level": secret.get("risk_level", "medium"),
                "current_interval": interval,
                "next_rotation_date": next_rotation.strftime("%Y-%m-%d"),
                "days_until_rotation": (next_rotation - today).days,
                "rotation_method": self._select_method(secret),
            })
        
        # 按日期排序，优先处理即将到期的
        plan.sort(key=lambda x: x["next_rotation_date"])
        return plan
    
    def _select_method(self, secret):
        """根据密钥类型选择最佳轮换方式"""
        method_map = {
            "aws": "iam_credential_rotation",
            "database": "password_rotation",
            "api_key": "regenerate_and_update",
            "ssh_key": "key_pair_rotation",
            "jwt": "secret_rotation",
            "ssl": "certificate_renewal",
        }
        return method_map.get(secret.get("type", "generic"), "manual_rotation")
```

## 第四步：自动轮换执行与验证

发现、评估、规划之后，需要**自动执行轮换**并验证效果：

```python
import subprocess
import tempfile
import os

class SecretRotationExecutor:
    """密钥轮换执行器"""
    
    def __init__(self, vault_client, config_manager):
        self.vault = vault_client
        self.config = config_manager
    
    def rotate_secret(self, rotation_task):
        """执行密钥轮换"""
        secret_id = rotation_task["secret_id"]
        method = rotation_task["rotation_method"]
        
        # 1. 从 Vault 读取当前密钥
        current_secret = self.vault.read(secret_id)
        
        # 2. 生成新密钥
        new_secret = self._generate_new_secret(method, current_secret)
        
        # 3. 写入 Vault（新版本）
        vault_version = self.vault.write(secret_id, new_secret)
        
        # 4. 更新所有依赖该密钥的服务配置
        dependents = self._find_dependents(secret_id)
        updates = []
        for dep in dependents:
            try:
                updated = self.config.update_service(dep, secret_id, new_secret)
                updates.append({"service": dep, "status": "updated"})
            except Exception as e:
                updates.append({"service": dep, "status": "failed", "error": str(e)})
        
        # 5. 验证轮换结果
        verification = self._verify_rotation(secret_id, new_secret)
        
        return {
            "secret_id": secret_id,
            "vault_version": vault_version,
            "dependents_updated": len([u for u in updates if u["status"] == "updated"]),
            "dependents_failed": len([u for u in updates if u["status"] == "failed"]),
            "verification": verification,
            "details": updates,
        }
    
    def _generate_new_secret(self, method, current):
        """根据方法生成新密钥"""
        if method == "iam_credential_rotation":
            # AWS IAM 凭证轮换
            return self.vault.generate_iam_credential(current["service"])
        elif method == "password_rotation":
            # 数据库密码轮换
            return {
                "password": self._generate_secure_password(24),
                "username": current.get("username", "app_user"),
            }
        elif method == "regenerate_and_update":
            # API Key 重新生成
            return {
                "key": self._generate_api_key(),
                "name": current.get("name", "new_key"),
            }
        elif method == "key_pair_rotation":
            # SSH 密钥对轮换
            return self._generate_ssh_keypair()
        else:
            # 通用轮换：生成随机字符串
            return {"value": self._generate_secure_password(32)}
    
    def _generate_secure_password(self, length=32):
        """生成高强度随机密码"""
        import string
        chars = string.ascii_letters + string.digits + "!@#$%^&*()-_=+"
        return "".join(random.choice(chars) for _ in range(length))
    
    def _generate_api_key(self):
        """生成 API Key"""
        import hashlib
        import uuid
        raw = f"{uuid.uuid4().hex}{uuid.uuid4().hex}"
        return f"sk-{hashlib.sha256(raw.encode()).hexdigest()[:32]}"
    
    def _generate_ssh_keypair(self):
        """生成 SSH 密钥对"""
        with tempfile.TemporaryDirectory() as tmpdir:
            key_path = f"{tmpdir}/id_rsa"
            subprocess.run([
                "ssh-keygen", "-t", "rsa", "-b", "4096",
                "-f", key_path, "-N", "",
            ], capture_output=True, check=True)
            
            with open(f"{key_path}", "r") as f:
                private_key = f.read()
            with open(f"{key_path}.pub", "r") as f:
                public_key = f.read()
            
            return {
                "private_key": private_key,
                "public_key": public_key.strip(),
                "key_type": "rsa-4096",
            }
    
    def _find_dependents(self, secret_id):
        """使用 LLM 分析找出依赖该密钥的所有服务"""
        # 扫描配置文件，找出引用该密钥的服务
        dependents = set()
        
        # 扫描常见配置目录
        for search_path in ["/etc/", "/opt/", "/home/", "/var/lib/"]:
            try:
                for root, dirs, files in os.walk(search_path):
                    dirs[:] = [d for d in dirs if d not in {'.git', '__pycache__'}]
                    for f in files:
                        if f.endswith(('.env', '.yaml', '.yml', '.json', '.toml',
                                       '.conf', '.py', '.sh')):
                            filepath = Path(root) / f
                            try:
                                content = filepath.read_text(errors="ignore")
                                if secret_id in content or self._secret_refers_to(content, secret_id):
                                    # 提取服务名称
                                    service_name = self._extract_service_name(filepath, content)
                                    if service_name:
                                        dependents.add(service_name)
                            except (PermissionError, UnicodeDecodeError):
                                continue
            except PermissionError:
                continue
        
        return list(dependents)
    
    def _secret_refers_to(self, content, secret_id):
        """检查内容是否引用了该密钥（处理变量引用等情况）"""
        # 简单的关键词匹配，实际项目中可以用更复杂的逻辑
        return secret_id.lower() in content.lower()
    
    def _extract_service_name(self, filepath, content):
        """从文件路径和内容中提取服务名称"""
        # 尝试从 Docker Compose 中提取服务名
        if "services:" in content:
            import re
            match = re.search(r"services:\s*\n\s*(\w+):", content)
            if match:
                return match.group(1)
        
        # 从路径推断
        parts = filepath.parts
        for i, part in enumerate(parts):
            if part in {"opt", "home", "var", "etc", "srv"}:
                if i + 1 < len(parts):
                    return parts[i + 1]
        
        return filepath.name
    
    def _verify_rotation(self, secret_id, new_secret):
        """验证轮换后密钥是否正常工作"""
        results = {
            "secret_id": secret_id,
            "vault_write": True,
            "service_tests": [],
        }
        
        # 尝试用新密钥访问依赖服务
        dependents = self._find_dependents(secret_id)
        for dep in dependents[:5]:  # 最多测试 5 个服务
            test_result = self._test_service_access(dep, new_secret)
            results["service_tests"].append(test_result)
        
        results["all_passed"] = all(
            t["status"] == "ok" for t in results["service_tests"]
        )
        
        return results
    
    def _test_service_access(self, service_name, secret):
        """测试服务是否能使用新密钥正常访问"""
        try:
            # 根据服务类型执行不同的健康检查
            if "database" in service_name.lower():
                # 测试数据库连接
                result = subprocess.run(
                    ["mysql", "-u", secret.get("username"), 
                     "-p" + secret.get("password", ""), "-e", "SELECT 1"],
                    capture_output=True, timeout=10
                )
                return {"service": service_name, "status": "ok" if result.returncode == 0 else "fail"}
            elif "api" in service_name.lower():
                # 测试 API 端点
                result = subprocess.run(
                    ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                     f"https://api.{service_name}.local/health"],
                    capture_output=True, text=True, timeout=10
                )
                status = "ok" if result.stdout.strip() == "200" else "fail"
                return {"service": service_name, "status": status}
            else:
                return {"service": service_name, "status": "skipped",
                        "reason": "unknown service type"}
        except Exception as e:
            return {"service": service_name, "status": "error", "error": str(e)}
```

## 第五步：AI 驱动的泄露检测与响应

即使有最完善的轮换系统，密钥也可能通过其他途径泄露。AI 可以实时监控：

```python
class SecretLeakDetector:
    """基于 AI 的密钥泄露检测器"""
    
    def __init__(self, llm_client):
        self.llm = llm_client
    
    def monitor_public_exposure(self):
        """监控密钥在公开渠道的泄露"""
        exposures = []
        
        # 1. 检查 GitHub 提交历史
        github_exposures = self._check_github()
        exposures.extend(github_exposures)
        
        # 2. 检查 Pastebin 等粘贴平台
        pastebin_exposures = self._check_pastebin()
        exposures.extend(pastebin_exposures)
        
        # 3. 检查搜索引擎索引
        search_exposures = self._check_search_engines()
        exposures.extend(search_exposures)
        
        # 4. AI 分析泄露影响
        if exposures:
            analysis = self._analyze_leak_impact(exposures)
            return analysis
        
        return {"exposures": [], "risk_level": "none", "recommendations": []}
    
    def _check_github(self):
        """检查 GitHub 上的密钥泄露"""
        # 实际项目中应使用 GitHub API 或专门工具如 gitleaks
        import subprocess
        try:
            result = subprocess.run(
                ["gitleaks", "detect", "--source", ".", 
                 "--report-format", "json"],
                capture_output=True, text=True, timeout=60
            )
            if result.returncode == 0:
                return json.loads(result.stdout).get("Findings", [])
        except Exception:
            pass
        return []
    
    def _analyze_leak_impact(self, exposures):
        """用 LLM 分析泄露影响"""
        prompt = f"""分析以下密钥泄露事件，评估影响范围和紧急程度：

泄露发现：
{json.dumps(exposures[:10], ensure_ascii=False, indent=2)}

请评估：
1. 哪些密钥已泄露（分类）
2. 泄露渠道（GitHub/Pastebin/搜索引擎等）
3. 潜在影响范围
4. 紧急程度（critical/high/medium/low）
5. 建议的响应行动

返回 JSON 格式：
{{
  "leaked_keys": [...],
  "exposure_channels": [...],
  "impact_scope": "描述",
  "risk_level": "critical/high/medium/low",
  "response_actions": [
    {{"action": "操作", "priority": 1, "description": "描述"}}
  ]
}}"""
        
        response = self.llm.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
        )
        
        return json.loads(response.choices[0].message.content)
```

## 完整部署：Docker Compose 方案

以下是一个完整的 AI 密钥管理系统部署方案：

```yaml
# docker-compose.yml
version: '3.8'

services:
  # 密钥存储与管理
  vault:
    image: hashicorp/vault:1.15
    container_name: vault
    restart: unless-stopped
    ports:
      - "8200:8200"
    environment:
      VAULT_ADDR: "http://0.0.0.0:8200"
      VAULT_DEV_ROOT_TOKEN_ID: "your-root-token"
    cap_add:
      - IPC_LOCK
    volumes:
      - vault_data:/vault/data
      - ./vault-config:/vault/config
    profiles: ["vault"]

  # AI 密钥管理 Agent
  secret-agent:
    build: ./secret-agent
    container_name: secret-agent
    restart: unless-stopped
    environment:
      VAULT_ADDR: "http://vault:8200"
      VAULT_TOKEN: "${VAULT_TOKEN}"
      LLM_API_KEY: "${LLM_API_KEY}"
      LLM_BASE_URL: "${LLM_BASE_URL}"
      LLM_MODEL: "deepseek-chat"
      SCAN_PATHS: "/etc:/opt:/home:/root"
      ROTATION_SCHEDULE: "0 2 * * *"  # 每天凌晨 2 点执行轮换检查
      LEAK_MONITOR_INTERVAL: "3600"    # 每小时检查一次泄露
    volumes:
      - /etc:/host-etc:ro
      - /opt:/host-opt:ro
      - /home:/host-home:ro
      - /root:/host-root:ro
      - agent_data:/data
      - ./config:/config
    depends_on:
      - vault
    profiles: ["agent"]

  # 密钥轮换执行器
  rotation-executor:
    build: ./rotation-executor
    container_name: rotation-executor
    restart: unless-stopped
    environment:
      VAULT_ADDR: "http://vault:8200"
      VAULT_TOKEN: "${VAULT_TOKEN}"
      LLM_API_KEY: "${LLM_API_KEY}"
      NOTIFICATION_WEBHOOK: "${NOTIFICATION_WEBHOOK}"
    volumes:
      - agent_data:/data
      - ./scripts:/scripts
    depends_on:
      - vault
      - secret-agent
    profiles: ["executor"]

  # 泄露监控服务
  leak-monitor:
    build: ./leak-monitor
    container_name: leak-monitor
    restart: unless-stopped
    environment:
      LLM_API_KEY: "${LLM_API_KEY}"
      GITHUB_TOKEN: "${GITHUB_TOKEN}"
      MONITORED_DOMAINS: "${MONITORED_DOMAINS}"
    volumes:
      - agent_data:/data
    profiles: ["monitor"]

  # Web 管理界面（可选）
  secret-dashboard:
    image: nicolargo/glances:full
    container_name: secret-dashboard
    restart: unless-stopped
    ports:
      - "61208:61208"
    environment:
      GLANCES_OPT: "-w"
    volumes:
      - agent_data:/data/reports:ro
    profiles: ["dashboard"]

volumes:
  vault_data:
  agent_data:
```

## 效果对比：传统 vs AI 驱动

| 能力维度 | 传统密钥管理 | AI 驱动密钥管理 |
|---------|------------|----------------|
| 密钥发现 | 手动审计，易遗漏 | LLM 语义扫描，覆盖环境变量、注释、历史提交 |
| 风险评级 | 固定规则 | 多维度动态评分，考虑上下文 |
| 轮换策略 | 固定周期 | 基于风险、使用频率、历史的智能调度 |
| 依赖追踪 | 人工查找 | AI 自动分析配置文件关联 |
| 泄露检测 | 被动响应 | 主动监控 GitHub/Pastebin/搜索引擎 |
| 响应速度 | 小时级 | 分钟级（AI 自动触发轮换） |
| 误报率 | 高（正则匹配） | 低（LLM 语义理解） |
| 运维负担 | 需要专人管理 | Agent 自动运行，人工只需审查 |

## 总结

AI 驱动的 VPS 密钥管理系统的核心价值在于**将密钥管理从"被动响应"转变为"主动预防"**：

1. **智能发现**：LLM 理解上下文，减少误报和漏报
2. **动态风险评级**：不只看不"像密钥"，更看"有多危险"
3. **自适应轮换**：高风险密钥频繁轮换，低风险密钥减少干扰
4. **自动依赖追踪**：轮换时自动找到所有需要更新的服务
5. **主动泄露监控**：不等出事，主动在公开渠道搜索泄露
6. **闭环验证**：轮换后自动验证服务是否正常

就像 AI 性能调优、AI 异常检测一样，密钥管理也是 AI 赋能 VPS 运维的典型场景。当你的 VPS 上running 着十几个服务、几十个密钥时，靠人工管理已经不够了——你需要一个 7×24 小时的 AI 密钥管家。

**下一步行动**：在你的 VPS 上部署 Vault，安装 `gitleaks` 扫描现有密钥，然后用 AI Agent 建立自动化轮换流程。安全不是一劳永逸的事，而是持续的过程——让 AI 来做那个持续监控的人。
