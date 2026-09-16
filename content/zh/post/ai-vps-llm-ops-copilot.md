---
title: "AI + VPS：用大模型构建智能运维 Copilot"
description: "传统 VPS 运维依赖人工经验和繁琐命令，效率低且易出错。本文介绍如何基于本地大模型构建一个智能运维 Copilot，支持自然语言交互、自动故障诊断、智能决策执行和持续学习，让运维从'手动操作'进化为'对话驱动'。"
date: 2026-09-16T21:00:00+08:00
lastmod: 2026-09-16T21:00:00+08:00
slug: "ai-vps-llm-ops-copilot"
tags: ["AI", "VPS", "LLM", "运维 Copilot", "ChatOps", "自动化", "Ollama", "LangChain", "工具调用"]
categories: ["AI + VPS"]
aliases: [/zh/post/ai-vps-llm-ops-copilot/]
image: /images/posts/ai-vps-llm-ops-copilot/featured.png
---

## 引言：从"命令台"到"对话台"的运维革命

作为 VPS 运维人员，你一定经历过这样的场景：

> *"服务器 CPU 飙到 95%，我要先查什么？"*
> *"这个 Nginx 报错是什么意思？怎么修？"*
> *"帮我看看有哪些进程在吃内存，然后杀掉占用最高的。"*

传统运维方式要求你：打开终端 → 记住命令 → 执行 → 分析结果 → 再决定下一步。整个过程高度依赖个人经验和记忆力，而且一旦多服务同时出现问题，排查效率急剧下降。

**AI 运维 Copilot** 的目标就是改变这一切——让你用自然语言与 VPS 对话，Copilot 理解你的意图、调用工具获取数据、给出诊断结论并执行修复操作。它不是要取代运维人员，而是成为你的**第二大脑**：记得住所有命令、24 小时在线、从不疲劳。

本文将带你从零构建一套完整的 **AI 运维 Copilot 系统**，涵盖架构设计、工具集成、安全控制和实战演示。

## 一、系统架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                        AI Ops Copilot                               │
│                                                                     │
│  ┌─────────────┐    ┌──────────────┐    ┌──────────────────────┐   │
│  │  用户交互层  │ ←→ │  LLM 推理引擎 │ ←→ │     工具执行层        │   │
│  │  (CLI/Web)  │    │  (Ollama/    │    │  (Shell/API/Script)  │   │
│  │             │    │   OpenRouter) │    │                      │   │
│  └─────────────┘    └──────┬───────┘    └──────────┬───────────┘   │
│                            │                      │                │
│                   ┌────────▼──────┐       ┌────────▼──────────┐    │
│                   │  记忆与上下文   │       │    知识库 & SOP     │    │
│                   │  (LangChain   │       │  (Markdown/向量库) │    │
│                   │   Memory)     │       │                   │    │
│                   └───────────────┘       └───────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
         │                    │                    │
         ▼                    ▼                    ▼
   ┌───────────┐        ┌───────────┐        ┌───────────┐
   │  系统监控  │        │  日志分析  │        │  服务管理  │
   │ Prometheus │        │   ELK/    │        │  Docker/  │
   │   Node    │        │  Vector   │        │  Systemd  │
   └───────────┘        └───────────┘        └───────────┘
```

### 核心组件说明

| 组件 | 技术选型 | 职责 |
|------|---------|------|
| **LLM 引擎** | Ollama (本地) / OpenRouter (云端) | 理解自然语言、生成决策 |
| **工具层** | Python subprocess + 自定义工具函数 | 执行命令、查询指标、管理容器 |
| **记忆层** | LangChain ConversationBufferMemory | 维护对话上下文 |
| **知识库** | Markdown 文档 + ChromaDB 向量库 | 存储 SOP、故障手册、配置文档 |
| **安全层** | 命令白名单 + 二次确认 + 审计日志 | 防止误操作和恶意指令 |

## 二、基础环境搭建

### 2.1 安装 Ollama 和本地模型

```bash
# 安装 Ollama
curl -fsSL https://ollama.com/install.sh | sh

# 拉取适合运维场景的模型（参数少、响应快）
ollama pull qwen2.5:7b
ollama pull nomic-embed-text  # 用于知识库向量嵌入
```

> **为什么选择 qwen2.5:7b？** 中文理解能力强，推理速度快，在 8GB 显存/内存上即可流畅运行。对于纯中文运维场景，它的效果优于同等规模的 Llama 系列模型。

### 2.2 安装依赖

```bash
pip install langchain langchain-community langchain-core \
            chromadb ollama python-dotenv \
            psutil pydantic
```

### 2.3 创建工具集

Copilot 的核心能力来自于它能调用的"工具"。我们定义一组运维工具：

```python
# tools/system_tools.py
import subprocess
import psutil
import json
from datetime import datetime

def run_command(cmd: str, timeout: int = 30) -> dict:
    """执行系统命令，返回结果和状态"""
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
        return {"success": False, "error": "命令超时", "command": cmd}
    except Exception as e:
        return {"success": False, "error": str(e), "command": cmd}

def get_system_status() -> dict:
    """获取系统整体状态"""
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
    """获取占用资源最多的进程"""
    processes = []
    for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'status']):
        try:
            processes.append(proc.info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    
    key_map = {"cpu": "cpu_percent", "memory": "memory_percent"}
    processes.sort(key=lambda x: x.get(key_map.get(sort_by, "memory_percent"), 0), reverse=True)
    return processes[:n]

def check_service(service_name: str) -> dict:
    """检查 systemd 服务状态"""
    result = run_command(f"systemctl is-active {service_name}")
    return {
        "service": service_name,
        "status": result["stdout"],
        "enabled": run_command(f"systemctl is-enabled {service_name}")["stdout"]
    }

def docker_status() -> dict:
    """获取 Docker 容器状态"""
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

## 三、构建 Copilot 核心引擎

### 3.1 定义工具列表

LangChain 通过 `@tool` 装饰器将函数注册为 LLM 可调用的工具：

```python
# copilot/core.py
from langchain_core.tools import tool
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnablePassthrough
from langchain_ollama import ChatOllama
from tools.system_tools import (
    run_command, get_system_status, get_top_processes,
    check_service, docker_status
)

# 定义运维工具
@tool
def system_info() -> str:
    """获取 VPS 系统整体状态：CPU、内存、磁盘、负载"""
    status = get_system_status()
    return json.dumps(status, ensure_ascii=False, indent=2)

@tool
def top_processes(sort_by: str = "memory", n: int = 10) -> str:
    """获取占用资源最多的进程列表，sort_by 可选 memory 或 cpu"""
    procs = get_top_processes(n=n, sort_by=sort_by)
    return json.dumps(procs, ensure_ascii=False, indent=2)

@tool
def exec_command(command: str) -> str:
    """在 VPS 上执行命令（需管理员确认）"""
    result = run_command(command)
    return json.dumps(result, ensure_ascii=False, indent=2)

@tool
def check_service_status(service: str) -> str:
    """检查指定 systemd 服务的运行状态"""
    return json.dumps(check_service(service), ensure_ascii=False)

@tool
def docker_list() -> str:
    """列出所有 Docker 容器及其状态"""
    return json.dumps(docker_status(), ensure_ascii=False)

TOOLS = [system_info, top_processes, exec_command, check_service_status, docker_list]
```

### 3.2 构建带工具调用的 Agent

```python
from langchain.agents import create_tool_calling_agent, AgentExecutor

# 初始化 LLM
llm = ChatOllama(
    model="qwen2.5:7b",
    temperature=0,
    base_url="http://localhost:11434"
)

# 构建提示词——加入安全约束
SYSTEM_PROMPT = """你是一个专业的 VPS 运维 AI 助手（Ops Copilot）。
你的职责是帮助用户诊断问题、执行操作、提供建议。

## 行为准则
1. **安全第一**：执行破坏性操作（删除文件、重启服务、停止容器）前必须向用户确认
2. **精准诊断**：先用只读工具收集信息，再决定是否需要执行修改操作
3. **解释清晰**：用中文回答，解释技术的含义和影响
4. **承认未知**：不确定时明确说明，不要编造答案
5. **拒绝危险**：拒绝执行明显有害的操作（如 rm -rf /、格式化磁盘等）

## 当前时间
{current_time}

## 可用工具
{tools}

现在，请开始帮助用户。""".strip()

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

### 3.3 添加记忆功能

```python
from langchain.memory import ConversationBufferMemory

memory = ConversationBufferMemory(
    memory_key="chat_history",
    return_messages=True,
    output_key="output"
)

# 完整的 Copilot 链路
copilot = {
    "input": lambda x: x["input"],
    "chat_history": lambda x: memory.load_memory_variables(x)["chat_history"],
    "agent_scratchpad": lambda x: format_agent_scratchpad(x["intermediate_steps"]),
} | agent_executor
```

## 四、知识库增强（RAG）

光有工具不够——Copilot 还需要了解你的**运维习惯和 SOP**。通过 RAG（检索增强生成），我们可以让 Copilot 查阅历史故障记录、配置文件和最佳实践。

### 4.1 构建知识库

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
        """从知识库目录构建向量索引"""
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
            separators=["\n\n", "\n", "。", ".", " "]
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
        """检索相关知识"""
        if not self.vectorstore:
            return []
        return self.vectorstore.similarity_search(query, k=k)
```

### 4.2 整合到 Copilot 中

```python
# 在 agent prompt 中加入知识检索
KB_PROMPT = """
## 运维知识库
以下知识来自你的历史运维记录和操作手册，请参考这些信息来回答用户问题：

{context}

如果知识库中没有相关信息，请基于你的通用知识回答，并说明这是通用建议。
"""

# 构建 RAG 增强链
from langchain.chains import create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain

kb = OpsKnowledgeBase()
kb.build()

retriever = kb.vectorstore.as_retriever(search_kwargs={"k": 3})

doc_chain = create_stuff_documents_chain(llm, KB_PROMPT)
rag_chain = create_retrieval_chain(retriever, doc_chain)
```

## 五、安全控制机制

Copilot 能执行命令——这意味着安全风险必须严格管控。

### 5.1 命令白名单与拦截

```python
# security.py
import re

DANGEROUS_PATTERNS = [
    r'\brm\s+-rf\b',          # 递归强制删除
    r'\bformat\b.*\b/',        # 格式化磁盘
    r'\bmkfs\b',               # 创建文件系统
    r'\bdd\s+if=',             # 直接写盘
    r'\bwget\s+.*\|.*sh\b',    # 远程脚本执行
    r'\bcurl\s+.*\|.*sh\b',    # 同上
    r'\bchown\s+-R\s+root\b',  # 递归改所有权
    r'\biptables\s+-F\b',      # 清空防火墙规则
    r'\bswapoff\s+-a\b',       # 关闭全部 swap
    r'\breboot\b',             # 重启系统
    r'\ ipython\b',             # 交互式 shell
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
    """检查命令是否安全"""
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, cmd, re.IGNORECASE):
            return {"safe": False, "reason": f"匹配危险模式: {pattern}"}
    
    base_cmd = cmd.strip().split()[0] if cmd.strip() else ""
    if base_cmd not in ALLOWED_COMMANDS:
        return {"safe": None, "reason": f"未在白名单中的命令: {base_cmd}，需要人工确认"}
    
    return {"safe": True, "reason": "命令在白名单中"}
```

### 5.2 二次确认流程

```python
def safe_execute(agent_executor, input_text: str, history: list = None) -> dict:
    """带安全控制的执行入口"""
    safety = is_safe_command(input_text)
    
    if safety["safe"] is False:
        return {
            "status": "blocked",
            "message": f"⛔ 操作被拦截：{safety['reason']}",
            "suggestion": "请联系管理员审核此操作"
        }
    
    if safety["safe"] is None:
        return {
            "status": "pending_confirm",
            "message": f"⚠️ 检测到未白名单命令，请确认是否执行：\n\n\`{input_text}\`\n\n回复 '确认' 执行，或 '取消' 跳过。"
        }
    
    # 正常执行
    result = agent_executor.invoke({
        "input": input_text,
        "chat_history": history or []
    })
    return {
        "status": "success",
        "output": result["output"]
    }
```

## 六、实战演示

### 场景 1：日常健康检查

```
用户: "帮我做个系统健康检查"

Copilot 执行流程:
┌─ system_info() ─────────────────────────────┐
│ CPU: 12%  内存: 4.2/8GB (52%)  磁盘: 65%   │
│ 负载: 0.85, 0.92, 0.78                     │
└────────────────────────────────────────────┘
┌─ top_processes(sort_by="cpu") ──────────────┐
│ 1. nginx (pid 1234) - CPU 8%               │
│ 2. node (pid 5678)  - CPU 3%               │
│ 3. python3 (pid 9012) - CPU 1%             │
└─────────────────────────────────────────────┘

回复: "✅ 系统健康检查完成：
  • CPU 使用率 12%，正常
  • 内存使用 52%（4.2/8GB），良好
  • 磁盘使用 65%，建议关注
  • 负载 0.85，中等偏高但不超标
  • 没有异常进程

  建议：磁盘使用率已达 65%，建议设置告警阈值在 80%。"
```

### 场景 2：故障诊断

```
用户: "网站访问很慢，帮我看看"

Copilot 执行流程:
┌─ system_info() ──┐  ┌─ docker_list() ──┐
│ CPU 89% 🔴       │  │ api-server: Up   │
│ 内存 78%         │  │ redis: Up        │
│ 负载 4.2 🔴      │  │ nginx: Up        │
└──────────────────┘  └──────────────────┘
┌─ top_processes() ─┐ ┌─ check_service("nginx") ─┐
│ 1. java - 85% CPU │ │ status: active (running) │
│ 2. python3 - 4%   │ └──────────────────────────┘
└───────────────────┘

回复: "🔍 诊断结果：
  发现异常：CPU 使用率 89%，系统负载 4.2，远超正常值。
  
  根因定位：Java 应用（pid 1234）占用 85% CPU，疑似存在死循环或全表扫描。
  
  建议操作：
  1. 检查 Java 应用日志：journalctl -u myapp -n 50
  2. 查看慢查询：mysql -e 'SHOW SLOW QUERIES'
  3. 如确认为异常进程，可执行：systemctl restart myapp
  
  是否需要我帮你执行上述排查命令？"
```

### 场景 3：批量服务管理

```
用户: "重启所有 Docker 容器"

Copilot 回复: "⚠️ 确认操作：将重启以下容器：
  • api-server（API 服务将中断 10-30 秒）
  • worker（队列任务将暂停）
  • redis（短暂连接中断）
  
  此操作会影响线上用户。是否确认？（回复'确认'继续）"
```

## 七、部署与集成

### 7.1 Docker 化部署

```dockerfile
# Dockerfile
FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    curl git tmux && \
    rm -rf /var/lib/apt/lists/*

# 安装 Ollama
RUN curl -fsSL https://ollama.com/install.sh | sh

# 复制项目
WORKDIR /app
COPY . .

RUN pip install --no-cache-dir -r requirements.txt

# 预拉取模型
RUN ollama pull qwen2.5:7b && \
    ollama pull nomic-embed-text

EXPOSE 8080
CMD ["python", "main.py"]
```

### 7.2 Telegram Bot 集成

```python
# bots/telegram_bot.py
import telebot
from copilot.core import copilot

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
bot = telebot.TeleBot(BOT_TOKEN)

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(message, 
        "🤖 Ops Copilot 已就绪！\n\n"
        "直接发送问题即可，例如：\n"
        "• '系统状态如何？'\n"
        "• '哪些进程占用 CPU 最高？'\n"
        "• '重启 nginx 服务'\n"
        "• '帮我查看今天的错误日志'"
    )

@bot.message_handler(func=lambda m: True)
def handle_message(message):
    chat_id = message.chat.id
    user_input = message.text.strip()
    
    with bot.state_privacy(chat_id, True):
        result = safe_execute(copilot, user_input)
    
    if result["status"] == "blocked":
        bot.reply_to(message, result["message"])
    elif result["status"] == "pending_confirm":
        # 存储待确认状态
        confirm_states[chat_id] = {"result": result, "input": user_input}
        bot.reply_to(message, result["message"])
    else:
        bot.reply_to(message, result["output"])
```

### 7.3 Web 控制台

```python
# main.py
from flask import Flask, request, jsonify
from copilot.core import copilot
import threading

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
        chat_states[chat_id] = history[-20:]  # 保留最近 20 条
    
    return jsonify(result)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
```

## 八、进阶：持续学习与自我改进

一个优秀的 Copilot 应该能从每次交互中学习。以下是几种实现方式：

### 8.1 故障案例沉淀

```python
def save_incident_to_kb(failure_scenario: str, solution: str):
    """将故障排查过程保存为知识"""
    doc = f"""## 故障案例
**问题**: {failure_scenario}
**解决方案**: {solution}
**时间**: {datetime.now().isoformat()}
"""
    with open(f"./knowledge/incidents/{datetime.now().strftime('%Y%m%d')}.md", "w") as f:
        f.write(doc)
```

### 8.2 提示词优化循环

```python
def refine_promptBasedOnFeedback(old_prompt: str, feedback: str) -> str:
    """用 LLM 自身优化自己的提示词"""
    optimizer_llm = ChatOllama(model="qwen2.5:7b", temperature=0.3)
    
    improvement_request = f"""
    以下是一个运维 Copilot 的系统提示词：
    ---
    {old_prompt}
    ---
    
    用户反馈：{feedback}
    
    请改进提示词，使 Copilot 能更好地处理此类问题。只输出改进后的提示词，不要其他内容。
    """
    
    return optimizer_llm.invoke(improvement_request).content
```

## 九、总结

AI 运维 Copilot 的价值不在于"替代运维"，而在于：

| 传统运维 | AI Copilot 运维 |
|---------|----------------|
| 靠记忆和笔记 | 知识库自动检索 |
| 命令逐条执行 | 自然语言一键完成 |
| 故障发现滞后 | 主动预警 + 自动诊断 |
| 经验难以传承 | 故障案例自动沉淀 |
| 7×8 人力覆盖 | 7×24 AI 守护 |

**下一步行动建议：**
1. 在测试 VPS 上部署 Ollama + qwen2.5:7b
2. 从简单的只读工具开始（system_info、top_processes）
3. 逐步添加更多工具和知识库
4. 接入 Telegram Bot 实现移动端交互
5. 在真实生产环境灰度发布，先在只读模式下验证效果

AI 正在重新定义运维的工作方式——从"命令台"到"对话台"，这一变革已经到来。你的 VPS，值得拥有一个聪明的助手。
