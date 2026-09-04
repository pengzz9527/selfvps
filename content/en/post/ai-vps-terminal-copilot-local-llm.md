---
title: "AI + VPS: Building an Intelligent Terminal Copilot with Local LLMs"
description: "Deploy a lightweight local LLM on your VPS to create your own ops Copilot—execute commands in natural language, auto-troubleshoot issues, generate scripts intelligently, and query your ops knowledge base, all without sending data to third-party APIs."
date: 2026-09-04T21:00:00+08:00
lastmod: 2026-09-04T21:00:00+08:00
slug: "ai-vps-terminal-copilot-local-llm"
image: /images/posts/ai-vps-terminal-copilot-local-llm/featured.png
tags: ["AI Ops", "LLM", "Terminal Copilot", "Ollama", "VPS Automation", "Troubleshooting", "Self-hosted"]
categories: ["AI Ops"]
aliases: [/en/post/ai-vps-terminal-copilot-local-llm/]
---

## Introduction

Ever had this experience—

Woken up at midnight by an alert, logging into your VPS to face a black terminal, momentarily forgetting the troubleshooting sequence; or needing to write a complex `crontab` expression, a `sed` script, or an `iptables` rule, only to jump back and forth between search engines and documentation.

Operations work is fundamentally about **understanding and controlling complex systems**, yet our primary tool—the terminal—remains a product of the 1970s. Input command, view output, input again... along this linear interaction chain, too much time is spent on "how do I type this command" instead of "what is the actual problem."

AI large language models are redefining how humans interact with terminals.

This article walks you through building a complete **AI Terminal Copilot running on your own VPS**—powered by a locally deployed lightweight LLM (Ollama + Qwen2.5)—enabling natural-language-driven command execution, intelligent troubleshooting, automated script generation, and ops knowledge Q&A. Everything runs entirely offline, with zero data leaving your server.

---

## Why Local LLM Instead of Cloud API?

Before diving into the technical details, let's address a key decision: **why run a local model on your VPS instead of calling OpenAI or Claude's API?**

| Dimension | Cloud API | Local LLM (This Guide) |
|-----------|-----------|----------------------|
| Data Privacy | Commands and history sent to third parties | All processed locally, zero leakage risk |
| Network Dependency | Requires stable external connectivity | Fully offline capable |
| Latency | 200ms–2s network round-trip | 50–200ms local inference |
| Cost | Token-based pricing, expensive at scale | One-time hardware cost, free afterward |
| Controllability | Subject to provider policy changes | Fully autonomous, upgrade anytime |
| Compliance | Fails security audit requirements | Meets all compliance standards |

For ops scenarios, every command executed in the terminal may touch production environments—database queries, configuration changes, service restarts. **Sending operational intents to a third-party API is unacceptable.** Local LLM deployment is the only compliant and reliable choice.

---

## System Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                      User Terminal (SSH / Local)                     │
│                                                                      │
│   "Check nginx error logs and tell me what's wrong recently"         │
│                              ▼                                       │
│   ┌─────────────────────────────────────────────────────────┐       │
│   │              Terminal Copilot Middleware                  │       │
│   │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐  │       │
│   │  │  Intent      │→│  Command     │→│  Security         │  │       │
│   │  │  Parsing     │  │  Generation  │  │  Sandbox Exec   │  │       │
│   │  │  (LLM)       │  │  (LLM +      │  │  (Read-first)   │  │       │
│   │  │              │  │   Templates) │  │                 │  │       │
│   │  └─────────────┘  └─────────────┘  └────────┬────────┘  │       │
│   └──────────────────────────────────────────────┼──────────┘       │
│                              ▼                                             │
│   ┌─────────────────────────────────────────────────────────┐       │
│   │                  Ollama Local Inference Engine            │       │
│   │         Qwen2.5-7B-Instruct / GLM-4-9B                  │       │
│   │   ┌──────────────┐  ┌──────────────┐  ┌─────────────┐  │       │
│   │   │  Ops KB      │  │  System       │  │  Session    │  │       │
│   │   │  (RAG)       │  │  Context      │  │  History    │  │       │
│   │   │              │  │  (Env vars)   │  │  (Memory)   │  │       │
│   │   └──────────────┘  └──────────────┘  └─────────────┘  │       │
│   └─────────────────────────────────────────────────────────┘       │
│                              ▼                                       │
│   ┌─────────────────────────────────────────────────────────┐       │
│   │                     VPS System Layer                     │       │
│   │   systemd · Prometheus · journald · Docker · Nginx · ... │       │
│   └─────────────────────────────────────────────────────────┘       │
└──────────────────────────────────────────────────────────────────────┘
```

Three layers:

1. **Interaction Layer (Copilot Middleware)**: Accepts natural language input, calls LLM to parse intent and generate commands, executes under security policies, and returns structured results.
2. **Inference Layer (Ollama)**: Local LLM inference engine supporting multiple open-source models, providing OpenAI-compatible API.
3. **Data Layer (Knowledge Base + Context)**: Ops knowledge base (RAG), system state snapshots, session history—making LLM outputs more accurate and targeted.

---

## Step 1: Deploy Ollama Local Inference Engine

### 1.1 Docker Compose One-Click Deployment

```yaml
# docker-compose.yml
version: "3.8"

services:
  ollama:
    image: ollama/ollama:latest
    container_name: ollama
    restart: unless-stopped
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama
      - /etc/timezone:/etc/timezone:ro
      - /etc/localtime:/etc/localtime:ro
    environment:
      - OLLAMA_HOST=0.0.0.0
      - OLLAMA_ORIGINS=*
    # GPU acceleration (if NVIDIA GPU available)
    # deploy:
    #   resources:
    #     reservations:
    #       devices:
    #         - driver: nvidia
    #           count: 1
    #           capabilities: [gpu]

volumes:
  ollama_data:
```

Start the service:

```bash
docker compose up -d
```

### 1.2 Pull Models

Recommended: **Qwen2.5-7B-Instruct** (Alibaba's Tongyi Qianwen, strong Chinese capability, moderate resource usage):

```bash
curl -X POST http://localhost:11434/api/pull \
  -H "Content-Type: application/json" \
  -d '{"name": "qwen2.5:7b-instruct"}'

# Verify model is available
curl http://localhost:11434/api/tags | jq .models
```

For smaller VPS memory (4GB), use a lighter model:

```bash
# 1.5B ultra-light (fast response, weaker capability)
curl -X POST http://localhost:11434/api/pull -d '{"name": "qwen2.5:1.5b-instruct"}'

# 3B balanced (recommended for low-spec machines)
curl -X POST http://localhost:11434/api/pull -d '{"name": "qwen2.5:3b-instruct"}'
```

> **Model Selection Guide**: Ops scenarios require strong logical reasoning and code generation—7B is the best balance. 4GB+ RAM: 7B; 2GB RAM: 3B; 1GB RAM: 1.5B.

---

## Step 2: Build the Copilot Middleware

### 2.1 Core Design

The core loop is simple:

```
Natural language → LLM intent parsing → Command generation → Safety check → Execution → Result formatting → Return to user
```

The key differentiators are **safety checking** and **result formatting**—commands generated by LLM shouldn't be executed blindly, and returned results need structured presentation.

### 2.2 Complete Python Implementation

```python
# copilot/main.py
#!/usr/bin/env python3
"""
AI Terminal Copilot — Local LLM-powered ops terminal assistant
"""

import os
import sys
import json
import subprocess
import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests

# Configuration
OLLAMA_API = os.getenv("OLLAMA_API", "http://localhost:11434")
MODEL = os.getenv("COPILOT_MODEL", "qwen2.5:7b-instruct")
SESSION_DIR = Path(os.getenv("SESSION_DIR", str(Path.home() / ".copilot/sessions")))
KNOWLEDGE_DIR = Path(os.getenv("KNOWLEDGE_DIR", str(Path.home() / ".copilot/knowledge")))
SYSTEM_CONTEXT_FILE = Path(os.getenv("SYSTEM_CONTEXT", str(Path.home() / ".copilot/system_context.txt")))

# Safety: prefixes of forbidden commands
DANGEROUS_PREFIXES = [
    "rm -rf /", "rm -rf /*", "mkfs", "dd if=",
    "curl ... | sh", "wget ... | bash",
    "chmod 777", "chown -R",
]

# Commands requiring confirmation
REQUIRES_CONFIRMATION = [
    "systemctl stop", "systemctl restart", "docker stop",
    "docker rm", "kill ", "iptables -F",
]

def load_system_context() -> str:
    """Load system context: current server info, running services, key config summary"""
    if SYSTEM_CONTEXT_FILE.exists():
        return SYSTEM_CONTEXT_FILE.read_text()

    context_parts = []
    try:
        hostname = subprocess.check_output(["hostname"], text=True, stderr=subprocess.DEVNULL).strip()
        uptime = subprocess.check_output(["uptime", "-p"], text=True, stderr=subprocess.DEVNULL).strip()
        context_parts.append(f"Hostname: {hostname}")
        context_parts.append(f"Uptime: {uptime}")
    except Exception:
        pass

    try:
        containers = subprocess.check_output(
            ["docker", "ps", "--format", "table {{.Names}}\t{{.Image}}\t{{.Status}}"],
            text=True, stderr=subprocess.DEVNULL
        ).strip()
        if containers:
            context_parts.append(f"\nRunning containers:\n{containers}")
    except Exception:
        pass

    for svc in ["nginx", "docker", "prometheus", "grafana", "ollama"]:
        try:
            status = subprocess.check_output(
                ["systemctl", "is-active", svc], text=True, stderr=subprocess.DEVNULL
            ).strip()
            context_parts.append(f"Service {svc}: {status}")
        except Exception:
            pass

    return "\n".join(context_parts)


def build_system_prompt(session_history: list = None) -> str:
    """Build LLM system prompt"""
    sys_ctx = load_system_context()

    prompt = f"""You are an AI ops assistant (Terminal Copilot) running on a Linux VPS.

## Current System Environment
{sys_ctx}

## Your Responsibilities
1. Understand natural language ops requests
2. Generate accurate shell commands to accomplish tasks
3. Interpret and analyze command outputs
4. Proactively suggest fixes when anomalies are detected

## Command Generation Rules
- Prefer read-only commands (--dry-run, -n flags) to confirm impact first
- Explain what you're about to do before generating write operations
- Use 2>&1 to capture stderr and avoid missing error information
- Format long commands with backslash continuation for readability
- Avoid sudo; assume user is already in a root environment

## Safety Policy
- Never generate destructive commands (rm -rf /, disk formatting, etc.)
- When involving service restarts or firewall changes, always flag the risk
- For uncertain commands, suggest dry-run testing first

## Output Format
For each request, respond with:
- **Analysis**: One-sentence explanation of what you're doing
- **Command**: ```bash\n{command}\n```
- **Expected Output**: Brief description of expected results
- **Notes**: Potential risks and follow-up steps

## Ops Knowledge Base Location
{KNOWLEDGE_DIR}

Please respond in Chinese."""

    if session_history:
        prompt += "\n\n## Conversation History\n"
        for turn in session_history[-10:]:
            prompt += f"User: {turn['user']}\nAssistant: {turn['assistant']}\n"

    return prompt


def chat_with_ollama(system_prompt: str, user_message: str, stream: bool = False) -> str:
    """Call Ollama API for conversation"""
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "stream": stream,
        "options": {"temperature": 0.3, "num_ctx": 8192},
    }

    try:
        resp = requests.post(
            f"{OLLAMA_API}/api/chat", json=payload, timeout=120, stream=stream
        )
        resp.raise_for_status()

        if stream:
            result = ""
            for line in resp.iter_lines():
                if line:
                    chunk = json.loads(line.decode())
                    if chunk.get("message", {}).get("content"):
                        result += chunk["message"]["content"]
                        print(chunk["message"]["content"], end="", flush=True)
            print()
            return result
        else:
            data = resp.json()
            return data["message"]["content"]
    except requests.exceptions.Timeout:
        return "⚠️ Request timeout—model may be loading or under heavy load."
    except requests.exceptions.ConnectionError:
        return f"⚠️ Cannot connect to Ollama ({OLLAMA_API}). Ensure the service is running."
    except Exception as e:
        return f"⚠️ LLM call error: {e}"


def extract_commands(response: str) -> list[str]:
    """Extract bash code blocks from LLM response"""
    import re
    pattern = r"```(?:bash)?\s*\n(.*?)\n```"
    matches = re.findall(pattern, response, re.DOTALL)
    return [m.strip() for m in matches if m.strip()]


def execute_command(cmd: str, timeout: int = 30) -> tuple[int, str, str]:
    """Execute command in a safety sandbox"""
    for prefix in DANGEROUS_PREFIXES:
        if cmd.startswith(prefix) or prefix in cmd:
            return -1, "", f"🚫 Refused dangerous command: {cmd}"

    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"⏱️ Command timed out ({timeout}s): {cmd}"
    except Exception as e:
        return -1, "", f"❌ Execution error: {e}"


def ask_confirmation(cmd: str) -> bool:
    """Request confirmation for high-risk commands"""
    for prefix in REQUIRES_CONFIRMATION:
        if cmd.startswith(prefix):
            answer = input(f"\n⚠️ About to execute a potentially service-affecting command:\n  {cmd}\nProceed? (y/N) ")
            return answer.lower() == "y"
    return True


def run_copilot_interactive():
    """Interactive REPL mode"""
    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_file = SESSION_DIR / f"{session_id}.json"
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    session_history = []

    print("=" * 60)
    print("  🤖 AI Terminal Copilot — Local Ops Assistant")
    print(f"  Model: {MODEL}")
    print(f"  Session: {session_id}")
    print("  Type '/exit' to quit, '/clear' to reset, '/run <cmd>' to execute")
    print("=" * 60)

    while True:
        try:
            user_input = input("\n👤 You> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 Goodbye!")
            break

        if not user_input:
            continue

        if user_input == "/exit":
            if session_file.exists():
                existing = json.loads(session_file.read_text())
                existing["history"].extend(session_history)
                session_file.write_text(json.dumps(existing, ensure_ascii=False, indent=2))
            print("👋 Goodbye!")
            break

        if user_input == "/clear":
            session_history = []
            print("🗑️ History cleared")
            continue

        if user_input.startswith("/run "):
            cmd = user_input[5:].strip()
            if ask_confirmation(cmd):
                code, stdout, stderr = execute_command(cmd)
                print(f"\n{'='*40}")
                print(f"💻 Result (exit={code}):")
                print(f"{'='*40}")
                if stdout:
                    print(f"📤 STDOUT:\n{stdout}")
                if stderr:
                    print(f"📥 STDERR:\n{stderr}")
            continue

        sys_prompt = build_system_prompt(session_history)
        reply = chat_with_ollama(sys_prompt, user_input)
        print(f"\n🤖 Copilot> {reply}")
        session_history.append({"user": user_input, "assistant": reply})

        commands = extract_commands(reply)
        if commands and len(commands) <= 2:
            auto_run = input("🔄 Auto-execute the commands above? (y/N) ").strip().lower()
            if auto_run == "y":
                for cmd in commands:
                    if ask_confirmation(cmd):
                        print(f"\n▶️ Executing: {cmd}")
                        code, stdout, stderr = execute_command(cmd)
                        if stdout:
                            print(stdout)
                        if stderr:
                            print(stderr, file=sys.stderr)


def run_copilot_one_shot(prompt: str, auto_exec: bool = False):
    """Single-shot non-interactive mode—for scripts and cron jobs"""
    sys_prompt = build_system_prompt()
    reply = chat_with_ollama(sys_prompt, prompt)
    print(reply)

    if auto_exec:
        commands = extract_commands(reply)
        for cmd in commands:
            print(f"\n▶️ Executing: {cmd}")
            code, stdout, stderr = execute_command(cmd)
            if stdout:
                print(stdout)
            if stderr:
                print(stderr, file=sys.stderr)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI Terminal Copilot")
    parser.add_argument("-p", "--prompt", help="Single-shot prompt mode")
    parser.add_argument("-a", "--auto-exec", action="store_true", help="Auto-execute generated commands")
    args = parser.parse_args()

    if args.prompt:
        run_copilot_one_shot(args.prompt, args.auto_exec)
    else:
        run_copilot_interactive()
```

### 2.3 Install Dependencies

```bash
pip install requests
```

### 2.4 Initialize Knowledge Base Directory

```bash
mkdir -p ~/.copilot/knowledge
mkdir -p ~/.copilot/sessions
```

---

## Step 3: Ops Knowledge Base (RAG Enhancement)

LLM knowledge alone isn't accurate enough—we need to mount an **ops knowledge base** that feeds your server's unique configurations, common troubleshooting procedures, and ops SOPs directly to the model.

### 3.1 Knowledge Base File Format

Store Markdown-formatted ops documents in `~/.copilot/knowledge/`:

````markdown
# incidents/nginx-502-guide.md
# Title: Nginx 502 Bad Gateway Troubleshooting Guide
# Tags: nginx, 502, troubleshooting

## Common Causes
1. Backend service down or crashed
2. Incorrect upstream configuration
3. Backend response timeout (proxy_read_timeout)
4. Port blocked or firewall interference

## Troubleshooting Steps
```bash
# 1. Check nginx status
systemctl status nginx

# 2. View error logs
tail -50 /var/log/nginx/error.log

# 3. Check backend service
curl -v http://127.0.0.1:YOUR_BACKEND_PORT/health

# 4. Check port listening
ss -tlnp | grep YOUR_PORT
```

## Quick Fix
```bash
systemctl restart nginx
systemctl restart YOUR_SERVICE
```
````

### 3.2 Integrate RAG Search

````python
# copilot/rag.py
import os
import re
from pathlib import Path
import requests

KNOWLEDGE_DIR = Path(os.getenv("KNOWLEDGE_DIR", str(Path.home() / ".copilot/knowledge")))

def semantic_search(query: str, top_k: int = 3) -> list[dict]:
    """Keyword-based search (upgrade to vector search with ChromaDB/Qdrant later)"""
    results = []
    query_terms = set(re.findall(r'[\u4e00-\u9fa5a-zA-Z]+', query.lower()))

    for md_file in KNOWLEDGE_DIR.rglob("*.md"):
        content = md_file.read_text(errors="ignore")
        tags = set(re.findall(r'# Tags:\s*(.+)', content))
        score = 0
        title_match = sum(1 for t in query_terms if t in md_file.stem.lower())
        content_score = sum(1 for t in query_terms if t in content.lower())
        tag_score = sum(2 for t in query_terms if t in str(tags).lower())
        score = title_match * 3 + content_score + tag_score

        if score > 0:
            lines = content.split('\n')
            snippet = []
            for line in lines[:5]:
                if line.strip() and not line.startswith('#'):
                    snippet.append(line.strip())
                    if len(' '.join(snippet)) > 200:
                        break
            results.append({
                "file": str(md_file.relative_to(KNOWLEDGE_DIR)),
                "score": score,
                "snippet": " ".join(snippet)[:200],
                "title": md_file.stem,
            })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]


def enrich_prompt(base_prompt: str, query: str) -> str:
    """Inject retrieved results into system prompt"""
    docs = semantic_search(query)
    if not docs:
        return base_prompt

    ctx = "\n\n## Relevant Ops Knowledge Base\n"
    for doc in docs:
        ctx += f"\n### [{doc['title']}] (relevance: {doc['score']})\n"
        ctx += f"{doc['snippet']}...\n"

    return base_prompt + ctx
````

---

## Step 4: Real-World Usage Scenarios

### Scenario 1: Natural Language Nginx 502 Troubleshooting

```
👤 You> nginx is returning 502, help me diagnose

🤖 Copilot> 
**Analysis**: User reports Nginx 502 errors—need to check backend service status and Nginx configuration.

**Command**:
```bash
tail -50 /var/log/nginx/error.log
systemctl is-active your-backend-service
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8080/health
```

**Expected Output**: Error logs show `upstream timed out` or `connect() failed`; backend service shows `inactive`; health check returns non-200.

**Notes**: If the backend is down, run `systemctl start your-backend-service` then verify again.
```

### Scenario 2: Smart crontab Generation

```
👤 You> Back up MySQL daily at 2 AM, keep 7 days of backups

🤖 Copilot>
**Analysis**: User needs a daily MySQL backup cron job with automatic cleanup of old backups.

**Command**:
```bash
crontab -e
# Add this line (runs daily at 2 AM):
0 2 * * * mysqldump -u root -p'YOUR_PASSWORD' --all-databases | gzip > /backup/mysql_$(date +\%Y\%m\%d).sql.gz && find /backup -name "mysql_*.sql.gz" -mtime +7 -delete
```

**Notes**:
- Replace `YOUR_PASSWORD` with your MySQL root password (recommend using `.my.cnf` credential file)
- Ensure `/backup` directory exists with sufficient space
- Test manually first: `mysqldump -u root -p'password' --all-databases | gzip > /backup/test.sql.gz`
```

### Scenario 3: Disk Space Analysis

```
👤 You> Disk is almost full, find what's taking the most space

🤖 Copilot>
**Analysis**: Diagnose disk usage and locate largest files and directories.

**Command**:
```bash
df -h
du -ah / 2>/dev/null | sort -rh | head -10
du -sh /var/log/* 2>/dev/null | sort -rh | head -10
docker system df
```

**Notes**: Likely culprits are unrotated log files, Docker images, or temp files. Consider `docker system prune -a` for Docker cleanup.
```

---

## Step 5: Deploy as systemd Service (Optional)

```ini
# /etc/systemd/system/copilot.service
[Unit]
Description=AI Terminal Copilot
After=network.target ollama.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/copilot
ExecStart=/usr/bin/python3 /opt/copilot/main.py --server --port 8080
Restart=always
RestartSec=10
Environment=OLLAMA_API=http://localhost:11434
Environment=COPILOT_MODEL=qwen2.5:7b-instruct
Environment=SESSION_DIR=/root/.copilot/sessions
Environment=KNOWLEDGE_DIR=/root/.copilot/knowledge

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable copilot
systemctl start copilot
```

---

## Advanced: Extending Capabilities

### 7.1 Multi-Model Routing

```python
MODEL_ROUTING = {
    "command_generation": "qwen2.5:7b-instruct",
    "log_analysis": "qwen2.5:7b-instruct",
    "quick_query": "qwen2.5:3b-instruct",
    "code_review": "qwen2.5:7b-instruct",
}
```

### 7.2 Prometheus Integration

```python
def get_prometheus_context(query: str) -> str:
    """Fetch current key metrics from Prometheus for LLM context"""
    try:
        metrics = {
            "cpu_usage": "100 - (avg by(instance) (rate(node_cpu_seconds_total{mode=\"idle\"}[5m])) * 100)",
            "memory_usage": "(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100",
            "disk_usage": "(1 - (node_filesystem_avail_bytes{mountpoint=\"/\"} / node_filesystem_size_bytes{mountpoint=\"/\"})) * 100",
        }
        return json.dumps(metrics, indent=2)
    except Exception:
        return ""
```

### 7.3 Web UI with Streamlit

```python
# copilot/web_ui.py
import streamlit as st
from copilot.main import chat_with_ollama, build_system_prompt

st.set_page_config(page_title="AI Terminal Copilot", page_icon="🤖", layout="wide")
st.title("🤖 AI Terminal Copilot")
st.caption("Local LLM-powered VPS ops assistant")

if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("Ask about your VPS..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    sys_prompt = build_system_prompt(
        [m for m in st.session_state.messages if m["role"] == "assistant"]
    )
    with st.chat_message("assistant"):
        response = chat_with_ollama(sys_prompt, prompt)
        st.markdown(response)

    st.session_state.messages.append({"role": "assistant", "content": response})
```

Run with: `streamlit run copilot/web_ui.py`

---

## Performance & Resource Reference

| Model | Memory Usage | Inference Speed | Best For |
|-------|-------------|-----------------|----------|
| qwen2.5:1.5b | ~1 GB | ~50ms/token | Simple Q&A, status checks |
| qwen2.5:3b | ~2 GB | ~80ms/token | Daily ops, command generation |
| qwen2.5:7b | ~5 GB | ~150ms/token | Complex troubleshooting, code generation |
| glm-4-9b | ~6 GB | ~200ms/token | Strong Chinese comprehension, knowledge Q&A |

> **Recommended Setup**: 8GB RAM VPS + 7B model is the most practical combination. 4GB RAM: go with 3B model for still-fast responses.

---

## Summary

This article covered the complete setup of a **local AI Terminal Copilot** on your VPS:

1. **Ollama + Qwen2.5** provides local LLM inference—data never leaves your server
2. **Python middleware** implements the full pipeline: intent parsing → command generation → safe execution → result feedback
3. **Ops knowledge base (RAG)** gives the LLM insight into your server's unique configurations and troubleshooting experience
4. **Three usage modes**—interactive REPL, script mode, and Web UI—adapt to different scenarios

The core value: **turning ops experience into reusable AI capability**. Whether it's the service architecture you built for the first time, or that weird bug you solved last year, you can codify it into the knowledge base so the Copilot gives better answers next time the same issue arises.

No paid API. No external network required. No data privacy concerns. Your VPS, your AI, your ops.

---

## Appendix: Complete Deployment Checklist

```bash
# 1. Deploy Ollama
docker compose up -d
docker exec -it ollama ollama pull qwen2.5:7b-instruct

# 2. Install Copilot
mkdir -p ~/.copilot/{knowledge,sessions}
cp -r /opt/copilot/* ~/.copilot/
pip3 install --user requests

# 3. Initialize knowledge base
echo "# Ops Knowledge Base" > ~/.copilot/knowledge/README.md

# 4. Start Copilot
python3 ~/.copilot/main.py

# Or single-shot mode
python3 ~/.copilot/main.py -p "check nginx status" --auto-exec
```
