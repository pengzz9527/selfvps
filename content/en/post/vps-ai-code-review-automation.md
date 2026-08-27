---
title: "AI-Powered Code Review Automation: Build Intelligent PR Analysis, Security Scanning & Documentation Generation on Your VPS"
subtitle: "AI 驱动的代码审查自动化：在 VPS 上搭建智能 PR 分析、安全检查与文档生成系统"
date: 2026-08-27T10:00:00+08:00
lastmod: 2026-08-27T10:00:00+08:00
slug: "vps-ai-code-review-automation"
image: /images/posts/vps-ai-code-review-automation/featured.png
tags: ["AI", "Code Review", "CI/CD", "Self-hosted", "Security", "Docker", "LLM", "DevOps"]
categories: ["AI + VPS"]
aliases: [/en/post/vps-ai-code-review-automation/]
description: "Build a fully automated code review system on your VPS using local LLMs, featuring intelligent PR analysis, security vulnerability scanning, code quality assessment, and automated documentation generation."
---

## Introduction

In software development, code review is the first line of defense for ensuring code quality. However, traditional manual review faces numerous challenges:

- **Delayed reviews**: PRs pile up, and developers wait days for feedback
- **Inconsistent standards**: Different reviewers have different focus areas, leading to uneven quality control
- **Overlooked security vulnerabilities**: Humans难以发现所有潜在的安全风险
- **Missing documentation**: New features lack documentation, increasing maintenance costs

This article introduces how to build an **AI-powered code review automation system** on your VPS, using locally deployed large language models (LLMs) to achieve intelligent PR analysis, security vulnerability scanning, code quality assessment, and automated documentation generation.

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Git Repository                          │
│              (GitHub / Gitea / GitLab)                       │
└──────────────────────┬──────────────────────────────────────┘
                       │ PR Created / Push
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
│  │  PR Analyzer │ │  Security   │ │  Doc Generator      │   │
│  │  (LLM)      │ │  Scanner    │ │  (LLM)              │   │
│  │             │ │  (Semgrep + │ │                     │   │
│  └──────┬──────┘ │   Trivy)    │ │                     │   │
│         │         └──────┬──────┘ └─────────┬───────────┘   │
│         │                │                   │               │
│         └────────────────┴───────────────────┘               │
│                         │                                   │
│                  ┌──────▼──────┐                             │
│                  │  Report     │                             │
│                  │  Aggregator │                             │
│                  │  (Markdown) │                             │
│                  └──────┬──────┘                             │
└─────────────────────────┼───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                   Post Comments to Git Repository            │
│              (PR Comments / Issues / Markdown Files)         │
└─────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. Webhook Handler

Receives PR events from Git platforms and triggers the review process:

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
    
    # Fetch PR diff
    diff = await fetch_pr_diff(owner, repo, pr_number)
    
    # Trigger three analysis tasks in parallel
    pr_analysis = analyze_pr_content(diff)
    security_scan = run_security_scan(diff)
    doc_generation = generate_documentation(diff)
    
    # Aggregate results
    report = await asyncio.gather(pr_analysis, security_scan, doc_generation)
    
    # Post review comment
    await post_review_comment(owner, repo, pr_number, report)
```

### 2. PR Content Analyzer

Uses a local LLM (e.g., Qwen or Llama deployed via Ollama) to analyze PR content:

```python
import ollama

def analyze_pr_content(diff: str) -> dict:
    prompt = f"""You are an experienced code review expert. Please analyze the following PR changes:

Change Summary (Diff):
{diff[:8000]}

Please review from the following dimensions and return as JSON:
1. Code Quality: Does the change follow best practices?
2. Readability: Is the code clear and understandable?
3. Consistency: Does the style match the project?
4. Potential Issues: Are there logic errors or missed edge cases?
5. Improvement Suggestions: Specific optimization suggestions.

JSON Format:
{{
  "quality_score": 1-10,
  "issues": ["List of issues"],
  "suggestions": ["List of suggestions"],
  "summary": "One-sentence summary"
}}
"""
    
    response = ollama.chat(model="qwen2.5:7b", messages=[{"role": "user", "content": prompt}])
    return json.loads(response["message"]["content"])
```

### 3. Security Vulnerability Scanner

Combines Semgrep and Trivy for deep security scanning:

```python
import subprocess
import json

def run_security_scan(diff: str) -> dict:
    # Write to temp file for scanning
    with open("/tmp/pr_changes.py", "w") as f:
        f.write(extract_python_changes(diff))
    
    # Semgrep static analysis
    semgrep_result = subprocess.run(
        ["semgrep", "--json", "--config=auto", "/tmp/pr_changes.py"],
        capture_output=True, text=True
    )
    
    # Trivy dependency scan
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

### 4. Documentation Auto-Generator

Automatically generates release notes based on PR changes:

```python
def generate_documentation(diff: str) -> dict:
    prompt = f"""Based on the following code changes, generate a concise release note:

Change Content:
{diff[:6000]}

Please generate:
1. Core feature/fix of this change (English, within 50 words)
2. Technical key points (3-5 items)
3. Compatibility notes (any breaking changes?)
4. Testing recommendations (key scenarios to test)

Format:
## Release Notes
- **Core Change**: xxx
- **Technical Points**:
  - xxx
  - xxx
- **Compatibility**: xxx
- **Testing Recommendations**: xxx
"""
    
    response = ollama.chat(model="qwen2.5:7b", messages=[{"role": "user", "content": prompt}])
    return response["message"]["content"]
```

## Complete Deployment Guide

### Docker Compose Configuration

```yaml
version: '3.8'

services:
  # AI Code Review Service
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

  # Local LLM Service
  ollama:
    image: ollama/ollama:latest
    ports:
      - "11434:11434"
    volumes:
      - ollama_models:/root/.ollama
    restart: unless-stopped

  # Semgrep Security Scanner
  semgrep:
    image: returntocorp/semgrep:latest
    volumes:
      - ./semgrep-rules:/rules
    command: scan --config=/rules

  # Trivy Image Scanner
  trivy:
    image: aquasec/trivy:latest
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock

volumes:
  ollama_models:
```

### Project Directory Structure

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

# Install Semgrep
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

## Usage Workflow

```
1. Developer submits PR
         │
         ▼
2. Git platform sends Webhook to your VPS
         │
         ▼
3. Webhook Handler receives event, extracts PR info
         │
         ▼
4. Three analyses run in parallel:
   ├── PR Content Analysis (LLM)
   ├── Security Vulnerability Scan (Semgrep + Trivy)
   └── Documentation Auto-Generation (LLM)
         │
         ▼
5. Aggregate analysis report, generate Markdown comment
         │
         ▼
6. Auto-post PR comment with AI review results
```

## Actual Results Example

Suppose a developer submits the following PR:

```python
# Changed code
def get_user_data(user_id):
    # Original code
    sql = "SELECT * FROM users WHERE id = " + user_id
    return db.execute(sql)
```

AI Review Result:

```
## 🔍 AI Code Review Report

### Security Score: ⚠️ 3/10

**Critical Issues**:
- 🚨 SQL Injection Risk: Directly concatenating user input into SQL statement
- Suggestion: Use parameterized query `db.execute("SELECT * FROM users WHERE id = %s", [user_id])`

### Code Quality: 6/10

**Issues**:
1. Missing input validation, user_id may be empty or non-numeric
2. No error handling, database exceptions will cause 500 errors
3. Function name should be more specific, e.g., `fetch_user_by_id`

**Suggestions**:
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

### 📝 Release Notes
- **Core Change**: Fixed SQL injection vulnerability in user data query endpoint
- **Technical Points**:
  - Used parameterized query instead of string concatenation
  - Added input validation and error handling
- **Compatibility**: Function signature unchanged, backward compatible
- **Testing Recommendations**:
  - Test injection attack: `user_id = "1 OR 1=1"`
  - Test edge cases: negative numbers, empty values, oversized integers
```

## Performance Optimization

### 1. Incremental Scanning

Only scan files changed in the PR, avoiding full scans:

```python
def get_changed_files(diff: str) -> list[str]:
    """Extract changed file list from diff"""
    import re
    files = re.findall(r'diff --git a/(.*) b/(.*)', diff)
    return list(set(f[0] for f in files))
```

### 2. Caching Mechanism

Use caching for identical PR content to avoid duplicate analysis:

```python
from functools import lru_cache
import hashlib

@lru_cache(maxsize=1024)
def cached_analysis(pr_hash: str) -> dict:
    """Cache analysis results"""
    return analyze_pr_content(fetch_pr_by_hash(pr_hash))
```

### 3. Parallel Processing

Use asyncio to run multiple analysis tasks in parallel:

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

## Cost Analysis

| Component | Resource Usage | Monthly Cost Estimate |
|-----------|---------------|----------------------|
| Ollama (Qwen 7B) | 8GB RAM, 4 vCPU | $0 (runs locally) |
| Semgrep | 1 vCPU, 512MB RAM | $0 |
| Trivy | 1 vCPU, 512MB RAM | $0 |
| Code Review Service | 1 vCPU, 1GB RAM | $0 |
| **Total** | **6 vCPU, 10GB RAM** | **$0** |

Compared to GitHub Advanced Security ($21/user/month), the self-hosted solution is completely free.

## Extended Features

### 1. Multi-language Support

```python
LANGUAGE_PATTERNS = {
    "python": ["*.py", "requirements.txt"],
    "javascript": ["*.js", "*.ts", "package.json"],
    "go": ["*.go", "go.mod"],
    "rust": ["*.rs", "Cargo.toml"],
}
```

### 2. Custom Review Rules

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

### 3. Slack/Telegram Integration

```python
async def notify_team(report: str):
    # Slack
    await slack.post("#code-review", report)
    
    # Telegram
    await telegram.send(chat_id, report)
```

## Summary

With this guide, you can build a complete **AI-powered code review automation system** on your VPS, achieving:

- ✅ **Intelligent PR Analysis**: LLM automatically understands code changes and provides expert-level review feedback
- ✅ **Security Vulnerability Scanning**: Semgrep + Trivy dual protection, discovering potential security risks
- ✅ **Automated Documentation**: Auto-generate release notes, reducing maintenance burden
- ✅ **Fully Self-hosted**: Code and data never leave your network, secure and controllable
- ✅ **Zero Marginal Cost**: Local LLM runs without paid API calls

This system is particularly suitable for:
- Small development teams looking to reduce code review costs
- Enterprises with high code security requirements
- Compliance scenarios requiring private deployment
- Developers looking to automate daily development workflows

Deploy it on your VPS today and let AI become your 24/7 code review expert!
