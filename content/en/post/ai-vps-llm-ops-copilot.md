---
title: "AI + VPS: Building an Intelligent Ops Copilot with LLMs"
description: "Traditional VPS operations rely on manual commands and operator experience, which is inefficient and error-prone. This article shows how to build an AI-powered Ops Copilot using local LLMs that supports natural language interaction, automatic fault diagnosis, intelligent decision-making, and continuous learning."
date: 2026-09-16T21:00:00+08:00
lastmod: 2026-09-16T21:00:00+08:00
slug: "ai-vps-llm-ops-copilot"
tags: ["AI", "VPS", "LLM", "Ops Copilot", "ChatOps", "Automation", "Ollama", "LangChain", "Function Calling"]
categories: ["AI + VPS"]
aliases: [/en/post/ai-vps-llm-ops-copilot/]
image: /images/posts/ai-vps-llm-ops-copilot/featured.png
---

## Introduction: From Terminal to Conversational Operations

As a VPS operator, you've likely experienced these scenarios:

> *"CPU spiked to 95%, what should I check first?"*
> *"What does this Nginx error mean and how do I fix it?"*
> *"Check which processes are consuming memory and kill the top one."*

Traditional operations require you to: open terminal → remember commands → execute → analyze results → decide next steps. This process heavily relies on personal experience and memory, and troubleshooting efficiency drops sharply when multiple services have issues simultaneously.

An **AI Ops Copilot** changes this — you interact with your VPS using natural language. The Copilot understands your intent, calls tools to gather data, provides diagnostic conclusions, and executes remediation actions. It doesn't replace operators; it becomes your **second brain**: remembers every command, online 24/7, never gets tired.

This article walks you through building a complete **AI Ops Copilot system** from scratch, covering architecture design, tool integration, safety controls, and real-world demos.

## 1. System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        AI Ops Copilot                               │
│                                                                     │
│  ┌─────────────┐    ┌──────────────┐    ┌──────────────────────┐   │
│  │  User Layer │ ←→ │  LLM Engine  │ ←→ │    Tool Execution    │   │
│  │ (CLI/Web)   │    │ (Ollama/     │    │    (Shell/API/Script)│   │
│  │             │    │  OpenRouter)  │    │                      │   │
│  └─────────────┘    └──────┬───────┘    └──────────┬───────────┘   │
│                            │                      │                │
│                   ┌────────▼──────┐       ┌────────▼──────────┐    │
│                   │  Memory &     │       │  Knowledge Base   │    │
│                   │  Context      │       │  (Markdown/Vector)│    │
│                   │ (LangChain    │       │                   │    │
│                   │  Memory)      │       │                   │    │
│                   └───────────────┘       └───────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
         │                    │                    │
         ▼                    ▼                    ▼
   ┌───────────┐        ┌───────────┐        ┌───────────┐
   │ Monitoring │        │ Log Analysis│       │ Service Mgmt│
   │ Prometheus │        │  ELK/      │       │  Docker/   │
   │   Node    │        │  Vector    │       │  Systemd   │
   └───────────┘        └───────────┘        └───────────┘
```

### Core Components

| Component | Technology | Responsibility |
|-----------|-----------|----------------|
| **LLM Engine** | Ollama (local) / OpenRouter (cloud) | Understand natural language, generate decisions |
| **Tool Layer** | Python subprocess + custom tool functions | Execute commands, query metrics, manage containers |
| **Memory Layer** | LangChain ConversationBufferMemory | Maintain conversation context |
| **Knowledge Base** | Markdown docs + ChromaDB vector store | Store SOPs, incident manuals, config docs |
| **Safety Layer** | Command whitelist + confirmation + audit logs | Prevent misoperations and malicious commands |

## 2. Foundation Setup

### 2.1 Install Ollama and Local Models

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull models suitable for ops scenarios (lightweight, fast)
ollama pull qwen2.5:7b
ollama pull nomic-embed-text  # for knowledge base embeddings
```

> **Why qwen2.5:7b?** Strong Chinese understanding, fast inference, runs smoothly on 8GB VRAM/RAM. For Chinese-only ops scenarios, it outperforms similarly-sized Llama models.

### 2.2 Install Dependencies

```bash
pip install langchain langchain-community langchain-core \
            chromadb ollama python-dotenv \
            psutil pydantic
```

### 2.3 Create Tool Set

The core capability of a Copilot comes from the "tools" it can call:

```python
# tools/system_tools.py
import subprocess
import psutil
import json
from datetime import datetime

def run_command(cmd: str, timeout: int = 30) -> dict:
    """Execute system command, return result and status"""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "return_code": result.returncode,
            "timestamp": datetime.now().isoformat()
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Command timeout", "command": cmd}
    except Exception as e:
        return {"success": False, "error": str(e), "command": cmd}

def get_system_status() -> dict:
    """Get overall system status"""
    return {
        "cpu_percent": psutil.cpu_percent(interval=1),
        "memory": {
            "total_gb": round(psutil.virtual_memory().total / 1024**3, 2),
            "available_gb": round(psutil.virtual_memory().available / 1024**3, 2),
            "used_percent": psutil.virtual_memory().percent
        },
        "disk": {
            "/": {
                "total_gb": round(psutil.disk_usage('/').total / 1024**3, 2),
                "used_gb": round(psutil.disk_usage('/').used / 1024**3, 2),
                "used_percent": psutil.disk_usage('/').percent
            }
        },
        "load_avg": psutil.getloadavg(),
        "uptime_seconds": psutil.boot_time()
    }

def get_top_processes(n: int = 10, sort_by: str = "memory") -> list:
    """Get top resource-consuming processes"""
    processes = []
    for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'status']):
        try:
            processes.append(proc.info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    
    key_map = {"cpu": "cpu_percent", "memory": "memory_percent"}
    processes.sort(
        key=lambda x: x.get(key_map.get(sort_by, "memory_percent"), 0), 
        reverse=True
    )
    return processes[:n]

def check_service(service_name: str) -> dict:
    """Check systemd service status"""
    result = run_command(f"systemctl is-active {service_name}")
    return {
        "service": service_name,
        "status": result["stdout"],
        "enabled": run_command(f"systemctl is-enabled {service_name}")["stdout"]
    }

def docker_status() -> dict:
    """Get Docker container status"""
    result = run_command("docker ps --format '{{.Names}}\t{{.Status}}\t{{.Ports}}'")
    containers = []
    for line in result["stdout"].split("\n"):
        if line.strip():
            parts = line.strip().split("\t")
            containers.append({
                "name": parts[0] if len(parts) > 0 else "",
                "status": parts[1] if len(parts) > 1 else "",
                "ports": parts[2] if len(parts) > 2 else ""
            })
    return {"containers": containers, "count": len(containers)}
```

## 3. Building the Copilot Core Engine

### 3.1 Define Tool List

LangChain registers functions as LLM-callable tools via the `@tool` decorator:

```python
# copilot/core.py
from langchain_core.tools import tool
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_ollama import ChatOllama
from tools.system_tools import (
    run_command, get_system_status, get_top_processes,
    check_service, docker_status
)
import json

@tool
def system_info() -> str:
    """Get VPS system overall status: CPU, memory, disk, load"""
    status = get_system_status()
    return json.dumps(status, indent=2)

@tool
def top_processes(sort_by: str = "memory", n: int = 10) -> str:
    """Get top resource-consuming process list, sort_by: memory or cpu"""
    procs = get_top_processes(n=n, sort_by=sort_by)
    return json.dumps(procs, indent=2)

@tool
def exec_command(command: str) -> str:
    """Execute command on VPS (requires admin confirmation)"""
    result = run_command(command)
    return json.dumps(result, indent=2)

@tool
def check_service_status(service: str) -> str:
    """Check specified systemd service status"""
    return json.dumps(check_service(service))

@tool
def docker_list() -> str:
    """List all Docker containers and their status"""
    return json.dumps(docker_status())

TOOLS = [system_info, top_processes, exec_command, check_service_status, docker_list]
```

### 3.2 Build Tool-Calling Agent

```python
from langchain.agents import create_tool_calling_agent, AgentExecutor

# Initialize LLM
llm = ChatOllama(
    model="qwen2.5:7b",
    temperature=0,
    base_url="http://localhost:11434"
)

# Build prompt with safety constraints
SYSTEM_PROMPT = """You are a professional VPS operations AI assistant (Ops Copilot).
Your duty is to help users diagnose issues, execute operations, and provide recommendations.

## Rules
1. **Safety first**: Always confirm with the user before executing destructive operations 
   (delete files, restart services, stop containers)
2. **Precise diagnosis**: Use read-only tools to gather info first, then decide if 
   modification is needed
3. **Clear explanation**: Explain technical meaning and impact in clear language
4. **Admit uncertainty**: Clearly state when you're unsure, don't fabricate answers
5. **Refuse dangerous requests**: Reject obviously harmful operations (rm -rf /, 
   disk formatting, etc.)

## Available Tools
{tools}

Now, help the user. """.strip()

prompt = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    MessagesPlaceholder("chat_history", optional=True),
    ("human", "{input}"),
    MessagesPlaceholder("agent_scratchpad"),
])

agent = create_tool_calling_agent(llm, TOOLS, prompt)
agent_executor = AgentExecutor(
    agent=agent,
    tools=TOOLS,
    verbose=True,
    handle_parsing_errors=True,
    max_iterations=15,
    return_intermediate_steps=True
)
```

### 3.3 Add Memory

```python
from langchain.memory import ConversationBufferMemory

memory = ConversationBufferMemory(
    memory_key="chat_history",
    return_messages=True,
    output_key="output"
)
```

## 4. Knowledge Base Enhancement (RAG)

Tools alone aren't enough — the Copilot also needs to understand your **ops habits and SOPs**. With RAG (Retrieval-Augmented Generation), the Copilot can reference historical incident records, configuration files, and best practices.

### 4.1 Build the Knowledge Base

```python
# knowledge_base.py
import chromadb
from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_community.embeddings import OllamaEmbeddings
from langchain_community.vectorstores import Chroma
from langchain.text_splitter import RecursiveCharacterTextSplitter

class OpsKnowledgeBase:
    def __init__(self, docs_dir: str = "./knowledge"):
        self.embeddings = OllamaEmbeddings(model="nomic-embed-text")
        self.client = chromadb.PersistentClient(path="./chroma_ops_db")
        self.docs_dir = docs_dir
        self.vectorstore = None
    
    def build(self):
        """Build vector index from knowledge base directory"""
        loader = DirectoryLoader(
            self.docs_dir,
            glob="**/*.md",
            loader_cls=TextLoader,
            loader_kwargs={"encoding": "utf-8"}
        )
        documents = loader.load()
        
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=500,
            chunk_overlap=50,
            separators=["\n\n", "\n", ".", " "]
        )
        chunks = splitter.split_documents(documents)
        
        self.vectorstore = Chroma.from_documents(
            documents=chunks,
            embedding=self.embeddings,
            client=self.client,
            collection_name="ops_knowledge"
        )
        return len(chunks)
    
    def search(self, query: str, k: int = 3) -> list:
        """Search relevant knowledge"""
        if not self.vectorstore:
            return []
        return self.vectorstore.similarity_search(query, k=k)
```

### 4.2 Integrate into Copilot

```python
KB_PROMPT = """
## Ops Knowledge Base
The following knowledge comes from your historical ops records and operation manuals.
Please reference this information when answering user questions:

{context}

If the knowledge base doesn't have relevant info, answer based on your general 
knowledge and note that this is a general recommendation.
"""
```

## 5. Safety Controls

The Copilot can execute commands — this means security risks must be strictly controlled.

### 5.1 Command Whitelist and Blocking

```python
# security.py
import re

DANGEROUS_PATTERNS = [
    r'\brm\s+-rf\b',
    r'\bformat\b.*\b/',
    r'\bmkfs\b',
    r'\bdd\s+if=',
    r'\bwget\s+.*\|.*sh\b',
    r'\bcurl\s+.*\|.*sh\b',
    r'\bchown\s+-R\s+root\b',
    r'\biptables\s+-F\b',
    r'\breboot\b',
]

ALLOWED_COMMANDS = [
    'ls', 'cat', 'head', 'tail', 'grep', 'find', 'du', 'df',
    'top', 'htop', 'ps', 'free', 'uptime', 'who', 'uname',
    'docker', 'systemctl', 'journalctl', 'ss', 'netstat',
    'curl', 'wget', 'ping', 'dig', 'nslookup', 'traceroute',
    'apt', 'apt-get', 'yum', 'dnf', 'pip', 'npm',
    'git', 'tar', 'gzip', 'zip', 'unzip',
]

def is_safe_command(cmd: str) -> dict:
    """Check if command is safe"""
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, cmd, re.IGNORECASE):
            return {"safe": False, "reason": f"Matched danger pattern: {pattern}"}
    
    base_cmd = cmd.strip().split()[0] if cmd.strip() else ""
    if base_cmd not in ALLOWED_COMMANDS:
        return {"safe": None, "reason": f"Command not in whitelist: {base_cmd}, needs human confirmation"}
    
    return {"safe": True, "reason": "Command is in whitelist"}
```

### 5.2 Two-Step Confirmation Flow

```python
def safe_execute(agent_executor, input_text: str, history: list = None) -> dict:
    """Execution entry with safety controls"""
    safety = is_safe_command(input_text)
    
    if safety["safe"] is False:
        return {
            "status": "blocked",
            "message": f"⛔ Operation blocked: {safety['reason']}",
            "suggestion": "Please contact administrator for review"
        }
    
    if safety["safe"] is None:
        return {
            "status": "pending_confirm",
            "message": f"⚠️ Non-whitelisted command detected. Confirm execution?\n\n`{input_text}`\n\nReply 'confirm' to proceed or 'cancel' to skip."
        }
    
    result = agent_executor.invoke({
        "input": input_text,
        "chat_history": history or []
    })
    return {"status": "success", "output": result["output"]}
```

## 6. Real-World Demos

### Scenario 1: Daily Health Check

```
User: "Run a system health check"

Copilot execution flow:
┌─ system_info() ─────────────────────────────┐
│ CPU: 12%  Memory: 4.2/8GB (52%)  Disk: 65% │
│ Load: 0.85, 0.92, 0.78                     │
└────────────────────────────────────────────┘
┌─ top_processes(sort_by="cpu") ──────────────┐
│ 1. nginx (pid 1234) - CPU 8%               │
│ 2. node (pid 5678)  - CPU 3%               │
│ 3. python3 (pid 9012) - CPU 1%             │
└─────────────────────────────────────────────┘

Response: "✅ System health check complete:
  • CPU usage 12%, normal
  • Memory usage 52% (4.2/8GB), good
  • Disk usage 65%, worth monitoring
  • Load 0.85, moderate but not exceeding threshold
  • No abnormal processes detected

  Recommendation: Disk at 65%, consider setting alert threshold at 80%."
```

### Scenario 2: Fault Diagnosis

```
User: "Website is very slow, check it out"

Copilot execution flow:
┌─ system_info() ──┐  ┌─ docker_list() ──┐
│ CPU 89% 🔴       │  │ api-server: Up   │
│ Memory 78%       │  │ redis: Up        │
│ Load 4.2 🔴      │  │ nginx: Up        │
└──────────────────┘  └──────────────────┘
┌─ top_processes() ─┐ ┌─ check_service("nginx") ─┐
│ 1. java - 85% CPU │ │ status: active (running) │
│ 2. python3 - 4%   │ └──────────────────────────┘
└───────────────────┘

Response: "🔍 Diagnosis:
  Issue found: CPU at 89%, system load 4.2, well above normal.
  
  Root cause: Java app (pid 1234) consuming 85% CPU, 
  likely an infinite loop or full table scan.
  
  Recommended actions:
  1. Check Java app logs: journalctl -u myapp -n 50
  2. Check slow queries: mysql -e 'SHOW SLOW QUERIES'
  3. If confirmed abnormal: systemctl restart myapp
  
  Should I help execute these diagnostic commands?"
```

### Scenario 3: Batch Service Management

```
User: "Restart all Docker containers"

Copilot response: "⚠️ Confirm operation: The following containers will be restarted:
  • api-server (API service will be down 10-30 seconds)
  • worker (queue tasks will pause)
  • redis (brief connection interruption)
  
  This will affect live users. Confirm? (Reply 'confirm' to proceed)"
```

## 7. Deployment and Integration

### 7.1 Docker Deployment

```dockerfile
# Dockerfile
FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    curl git tmux && \
    rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://ollama.com/install.sh | sh

WORKDIR /app
COPY . .

RUN pip install --no-cache-dir -r requirements.txt

RUN ollama pull qwen2.5:7b && \
    ollama pull nomic-embed-text

EXPOSE 8080
CMD ["python", "main.py"]
```

### 7.2 Telegram Bot Integration

```python
# bots/telegram_bot.py
import telebot
from copilot.core import copilot

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
bot = telebot.TeleBot(BOT_TOKEN)

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(message, 
        "🤖 Ops Copilot is ready!\n\n"
        "Send questions directly, e.g.:\n"
        "• 'How is system status?'\n"
        "• 'Which processes use the most CPU?'\n"
        "• 'Restart nginx service'\n"
        "• 'Show me today's error logs'"
    )

@bot.message_handler(func=lambda m: True)
def handle_message(message):
    chat_id = message.chat.id
    user_input = message.text.strip()
    
    result = safe_execute(copilot, user_input)
    
    if result["status"] == "blocked":
        bot.reply_to(message, result["message"])
    elif result["status"] == "pending_confirm":
        confirm_states[chat_id] = {"result": result, "input": user_input}
        bot.reply_to(message, result["message"])
    else:
        bot.reply_to(message, result["output"])
```

### 7.3 Web Console

```python
# main.py
from flask import Flask, request, jsonify
from copilot.core import copilot

app = Flask(__name__)
chat_states = {}

@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    chat_id = data.get('chat_id', 'default')
    message = data.get('message', '')
    
    history = chat_states.get(chat_id, [])
    result = safe_execute(copilot, message, history)
    
    if result["status"] == "success":
        history.append({"role": "user", "content": message})
        history.append({"role": "assistant", "content": result["output"]})
        chat_states[chat_id] = history[-20:]
    
    return jsonify(result)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
```

## 8. Advanced: Continuous Learning

An excellent Copilot should learn from every interaction.

### 8.1 Incident Case Preservation

```python
def save_incident_to_kb(failure_scenario: str, solution: str):
    """Save troubleshooting process as knowledge"""
    doc = f"""## Incident Case
**Issue**: {failure_scenario}
**Solution**: {solution}
**Time**: {datetime.now().isoformat()}
"""
    import os
    os.makedirs(f"./knowledge/incidents/", exist_ok=True)
    with open(f"./knowledge/incidents/{datetime.now().strftime('%Y%m%d')}.md", "w") as f:
        f.write(doc)
```

### 8.2 Prompt Optimization Loop

```python
def refine_prompt_based_on_feedback(old_prompt: str, feedback: str) -> str:
    """Use LLM to optimize its own prompt"""
    optimizer_llm = ChatOllama(model="qwen2.5:7b", temperature=0.3)
    
    improvement_request = f"""
    Current system prompt:
    ---
    {old_prompt}
    ---
    
    User feedback: {feedback}
    
    Improve the prompt so the Copilot handles such issues better. 
    Output only the improved prompt, nothing else.
    """
    
    return optimizer_llm.invoke(improvement_request).content
```

## 9. Summary

The value of an AI Ops Copilot isn't about "replacing operators" — it's about:

| Traditional Ops | AI Copilot Ops |
|----------------|----------------|
| Relies on memory and notes | Auto-retrieves from knowledge base |
| Commands executed one by one | Natural language, one-click completion |
| Reactive fault discovery | Proactive alerts + automatic diagnosis |
| Experience hard to transfer | Incident cases auto-preserved |
| 7×8 human coverage | 7×24 AI guard |

**Next Steps:**
1. Deploy Ollama + qwen2.5:7b on a test VPS
2. Start with read-only tools (system_info, top_processes)
3. Gradually add more tools and knowledge base
4. Integrate Telegram Bot for mobile interaction
5. Pilot in production under read-only mode first

AI is redefining how operations work — from "terminal" to "conversation". The change has already arrived. Your VPS deserves a smart assistant.
