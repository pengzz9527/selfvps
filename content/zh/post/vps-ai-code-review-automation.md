---
title: "AI 驱动的代码审查自动化：在 VPS 上搭建智能 PR 分析、安全检查与文档生成系统"
subtitle: "AI-Powered Code Review Automation: Build Intelligent PR Analysis, Security Scanning & Documentation Generation on Your VPS"
date: 2026-08-27T10:00:00+08:00
lastmod: 2026-08-27T10:00:00+08:00
slug: "vps-ai-code-review-automation"
image: /images/posts/vps-ai-code-review-automation/featured.png
tags: ["AI", "代码审查", "CI/CD", "自托管", "安全扫描", "Docker", "LLM", "DevOps"]
categories: ["AI + VPS"]
aliases: [/zh/post/vps-ai-code-review-automation/]
description: "利用本地 LLM 在 VPS 上搭建全自动代码审查系统，实现 PR 智能分析、安全漏洞扫描、代码质量评估与文档自动生成，让每次代码提交都经过 AI 专家级审查。"
---

## 引言

在软件开发中，代码审查（Code Review）是保障代码质量的第一道防线。然而，传统的人工审查方式面临诸多挑战：

- **审查不及时**：PR 堆积如山，开发者等待数天才能得到反馈
- **标准不统一**：不同审查者的关注点各异，质量把控参差不齐
- **安全漏洞遗漏**：人工难以发现所有潜在的安全风险
- **文档缺失**：新功能缺乏文档说明，维护成本高

本文将介绍如何在 VPS 上搭建一套 **AI 驱动的代码审查自动化系统**，利用本地部署的大语言模型（LLM）实现智能 PR 分析、安全漏洞扫描、代码质量评估与文档自动生成。

## 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                     Git Repository                          │
│              (GitHub / Gitea / GitLab)                       │
└──────────────────────┬──────────────────────────────────────┘
                       │ PR 创建 / Push
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                   Webhook Handler                            │
│              (Python Flask / FastAPI)                        │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                  AI Code Review Engine                       │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────────────┐   │
│  │  PR 分析器   │ │ 安全检查器  │ │   文档生成器        │   │
│  │  (LLM)      │ │  (Semgrep + │ │  (LLM)              │   │
│  │             │ │   Trivy)    │ │                     │   │
│  └──────┬──────┘ └──────┬──────┘ └─────────┬───────────┘   │
│         │               │                   │               │
│         └───────────────┴───────────────────┘               │
│                         │                                   │
│                  ┌──────▼──────┐                             │
│                  │  报告聚合器  │                             │
│                  │  (Markdown) │                             │
│                  └──────┬──────┘                             │
└─────────────────────────┼───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                   评论回写 Git Repository                    │
│              (PR 评论 / Issue / Markdown 文件)                │
└─────────────────────────────────────────────────────────────┘
```

## 核心组件

### 1. Webhook 处理器

接收 Git 平台的 PR 事件，触发审查流程：

```python
from fastapi import FastAPI, Request
import httpx
import json

app = FastAPI()

@app.post("/webhook/pr-opened")
async def handle_pr_opened(request: Request):
    payload = await request.json()
    
    repo = payload.get("repository", {}).get("full_name")
    pr_number = payload.get("pull_request", {}).get("number")
    owner = payload.get("repository", {}).get("owner", {}).get("login")
    
    # 获取 PR diff
    diff = await fetch_pr_diff(owner, repo, pr_number)
    
    # 并行触发三个分析任务
    pr_analysis = analyze_pr_content(diff)
    security_scan = run_security_scan(diff)
    doc_generation = generate_documentation(diff)
    
    # 聚合结果
    report = await asyncio.gather(pr_analysis, security_scan, doc_generation)
    
    # 回写评论
    await post_review_comment(owner, repo, pr_number, report)
```

### 2. PR 内容分析器

使用本地 LLM（如 Ollama 部署的 Qwen 或 Llama）分析 PR 内容：

```python
import ollama

def analyze_pr_content(diff: str) -> dict:
    prompt = f"""你是一个经验丰富的代码审查专家。请分析以下 PR 的变更内容：

变更摘要（Diff）：
{diff[:8000]}

请从以下维度进行审查，并以 JSON 格式返回：
1. 代码质量：变更是否符合最佳实践？
2. 可读性：代码是否清晰易懂？
3. 一致性：风格是否与项目保持一致？
4. 潜在问题：是否存在逻辑错误或边界情况遗漏？
5. 改进建议：具体的优化建议。

JSON 格式：
{{
  "quality_score": 1-10,
  "issues": ["问题列表"],
  "suggestions": ["建议列表"],
  "summary": "一句话总结"
}}
"""
    
    response = ollama.chat(model="qwen2.5:7b", messages=[{"role": "user", "content": prompt}])
    return json.loads(response["message"]["content"])
```

### 3. 安全漏洞扫描器

结合 Semgrep 和 Trivy 进行深度安全扫描：

```python
import subprocess
import json

def run_security_scan(diff: str) -> dict:
    # 写入临时文件进行扫描
    with open("/tmp/pr_changes.py", "w") as f:
        f.write(extract_python_changes(diff))
    
    # Semgrep 静态分析
    semgrep_result = subprocess.run(
        ["semgrep", "--json", "--config=auto", "/tmp/pr_changes.py"],
        capture_output=True, text=True
    )
    
    # Trivy 依赖扫描
    trivy_result = subprocess.run(
        ["trivy", "fs", "--security-checks=vuln,config", "--format=json", "/tmp/"],
        capture_output=True, text=True
    )
    
    return {
        "semgrep_findings": json.loads(semgrep_result.stdout).get("results", []),
        "trivy_findings": json.loads(trivy_result.stdout).get("Results", []),
        "severity_summary": count_severities(semgrep_result.stdout)
    }
```

### 4. 文档自动生成器

基于 PR 变更自动生成更新说明：

```python
def generate_documentation(diff: str) -> dict:
    prompt = f"""根据以下代码变更，生成一份简洁的更新说明：

变更内容：
{diff[:6000]}

请生成：
1. 本次变更的核心功能/修复（中文，50字以内）
2. 技术要点（3-5条）
3. 兼容性说明（是否有 breaking change）
4. 测试建议（需要重点测试的场景）

格式：
## 更新说明
- **核心变更**：xxx
- **技术要点**：
  - xxx
  - xxx
- **兼容性**：xxx
- **测试建议**：xxx
"""
    
    response = ollama.chat(model="qwen2.5:7b", messages=[{"role": "user", "content": prompt}])
    return response["message"]["content"]
```

## 完整部署方案

### Docker Compose 配置

```yaml
version: '3.8'

services:
  # AI 代码审查服务
  code-review:
    build: ./code-review-service
    ports:
      - "8080:8080"
    environment:
      - OLLAMA_HOST=http://ollama:11434
      - GITHUB_TOKEN=${GITHUB_TOKEN}
      - WEBHOOK_SECRET=${WEBHOOK_SECRET}
    volumes:
      - ./config:/app/config
      - ./logs:/app/logs
    depends_on:
      - ollama

  # 本地 LLM 服务
  ollama:
    image: ollama/ollama:latest
    ports:
      - "11434:11434"
    volumes:
      - ollama_models:/root/.ollama
    restart: unless-stopped

  # Semgrep 安全扫描
  semgrep:
    image: returntocorp/semgrep:latest
    volumes:
      - ./semgrep-rules:/rules
    command: scan --config=/rules

  # Trivy 镜像扫描
  trivy:
    image: aquasec/trivy:latest
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock

volumes:
  ollama_models:
```

### 项目目录结构

```
vps-ai-code-review/
├── docker-compose.yml
├── code-review-service/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py
│   ├── reviewers/
│   │   ├── pr_analyzer.py
│   │   ├── security_scanner.py
│   │   └── doc_generator.py
│   └── config/
│       └── review-prompt.yaml
├── semgrep-rules/
│   ├── security.yaml
│   └── quality.yaml
└── README.md
```

### Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 安装 Semgrep
RUN curl -Ls https://install.semgrep.dev | bash

COPY . .

EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
```

### requirements.txt

```
fastapi==0.111.0
uvicorn==0.30.1
ollama==0.2.0
httpx==0.27.0
pyyaml==6.0.1
semgrep==1.70.0
```

## 使用流程

```
1. 开发者提交 PR
         │
         ▼
2. Git 平台发送 Webhook 到你的 VPS
         │
         ▼
3. Webhook Handler 接收事件，提取 PR 信息
         │
         ▼
4. 并行执行三个分析：
   ├── PR 内容分析（LLM）
   ├── 安全漏洞扫描（Semgrep + Trivy）
   └── 文档自动生成（LLM）
         │
         ▼
5. 聚合分析报告，生成 Markdown 格式评论
         │
         ▼
6. 自动回写 PR 评论，开发者即可查看 AI 审查结果
```

## 实际效果示例

假设一个开发者提交了以下 PR：

```python
# 变更内容
def get_user_data(user_id):
    # 原来的代码
    sql = "SELECT * FROM users WHERE id = " + user_id
    return db.execute(sql)
```

AI 审查结果：

```
## 🔍 AI 代码审查报告

### 安全评分: ⚠️ 3/10

**严重问题**:
- 🚨 SQL 注入风险：直接拼接用户输入到 SQL 语句中
- 建议：使用参数化查询 `db.execute("SELECT * FROM users WHERE id = %s", [user_id])`

### 代码质量: 6/10

**问题**:
1. 缺少输入验证，user_id 可能为空或非数字
2. 没有错误处理，数据库异常会导致 500 错误
3. 函数名应该更具体，如 `fetch_user_by_id`

**建议**:
```python
def fetch_user_by_id(user_id: int) -> dict:
    if not isinstance(user_id, int) or user_id <= 0:
        raise ValueError("Invalid user ID")
    
    try:
        sql = "SELECT * FROM users WHERE id = %s"
        result = db.execute(sql, [user_id])
        return result.fetchone()
    except DatabaseError as e:
        logger.error(f"Database error: {e}")
        raise
```

### 📝 更新说明
- **核心变更**：修复用户数据查询接口的 SQL 注入漏洞
- **技术要点**：
  - 使用参数化查询替代字符串拼接
  - 添加输入验证和错误处理
- **兼容性**：函数签名保持不变，向后兼容
- **测试建议**：
  - 测试注入攻击：`user_id = "1 OR 1=1"`
  - 测试边界值：负数、空值、超大整数
```

## 性能优化

### 1. 增量扫描

只扫描 PR 变更的文件，避免全量扫描：

```python
def get_changed_files(diff: str) -> list[str]:
    """从 diff 中提取变更的文件列表"""
    import re
    files = re.findall(r'diff --git a/(.*) b/(.*)', diff)
    return list(set(f[0] for f in files))
```

### 2. 缓存机制

对相同的 PR 内容使用缓存，避免重复分析：

```python
from functools import lru_cache
import hashlib

@lru_cache(maxsize=1024)
def cached_analysis(pr_hash: str) -> dict:
    """缓存分析结果"""
    return analyze_pr_content(fetch_pr_by_hash(pr_hash))
```

### 3. 并行处理

使用 asyncio 并行执行多个分析任务：

```python
async def run_all_reviews(diff: str):
    results = await asyncio.gather(
        analyze_pr_content(diff),
        run_security_scan(diff),
        generate_documentation(diff),
        check_code_style(diff)
    )
    return merge_reports(results)
```

## 成本分析

| 组件 | 资源消耗 | 月成本估算 |
|------|---------|-----------|
| Ollama (Qwen 7B) | 8GB RAM, 4 vCPU | ¥0 (本地运行) |
| Semgrep | 1 vCPU, 512MB RAM | ¥0 |
| Trivy | 1 vCPU, 512MB RAM | ¥0 |
| Code Review Service | 1 vCPU, 1GB RAM | ¥0 |
| **合计** | **6 vCPU, 10GB RAM** | **¥0** |

相比 GitHub Advanced Security（$21/用户/月），自建方案完全免费。

## 扩展功能

### 1. 支持多语言

```python
LANGUAGE_PATTERNS = {
    "python": ["*.py", "requirements.txt"],
    "javascript": ["*.js", "*.ts", "package.json"],
    "go": ["*.go", "go.mod"],
    "rust": ["*.rs", "Cargo.toml"],
}
```

### 2. 自定义审查规则

```yaml
# config/review-prompt.yaml
reviewer:
  role: "Senior Software Engineer with 10+ years experience"
  focus_areas:
    - security
    - performance
    - maintainability
    - testing
  tone: "constructive and encouraging"
```

### 3. 与 Slack/Telegram 集成

```python
async def notify_team(report: str):
    # Slack
    await slack.post("#code-review", report)
    
    # Telegram
    await telegram.send(chat_id, report)
```

## 总结

通过本文的指南，你可以在 VPS 上搭建一套完整的 **AI 驱动代码审查自动化系统**，实现：

- ✅ **智能 PR 分析**：LLM 自动理解代码变更，提供专业级审查意见
- ✅ **安全漏洞扫描**：Semgrep + Trivy 双重保障，发现潜在安全风险
- ✅ **文档自动生成**：自动产出更新说明，减少维护负担
- ✅ **完全自托管**：代码和数据不出域，安全可控
- ✅ **零边际成本**：本地 LLM 运行，无需付费 API

这套系统特别适合以下场景：
- 小型开发团队，希望降低代码审查成本
- 对代码安全有高要求的企业
- 需要私有化部署的合规场景
- 希望自动化日常开发流程的开发者

立即在 VPS 上部署，让 AI 成为你的 7×24 代码审查专家！
