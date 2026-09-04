---
title: "AI + VPS：用本地大模型打造智能运维终端助手——Terminal Copilot 完整实践"
description: "在 VPS 上部署轻量级本地 LLM，打造你的专属运维 Copilot：自然语言执行命令、自动排查故障、智能生成脚本、实时知识库检索，让每一次终端交互都事半功倍。"
date: 2026-09-04T21:00:00+08:00
lastmod: 2026-09-04T21:00:00+08:00
slug: "ai-vps-terminal-copilot-local-llm"
image: /images/posts/ai-vps-terminal-copilot-local-llm/featured.png
tags: ["AI运维", "LLM", "Terminal Copilot", "Ollama", "VPS自动化", "智能排障", "本地部署"]
categories: ["AI运维"]
aliases: [/zh/post/ai-vps-terminal-copilot-local-llm/]
---

## 引言

你是否有过这样的经历——

深夜被告警叫醒，登录 VPS 后面对黑漆漆的终端，一时想不起排查顺序；或者是需要写一个复杂的 `crontab` 表达式、一段 `sed` 脚本、一条 `iptables` 规则，却要在搜索引擎和文档之间反复切换。

运维工作本质上是在**理解和操作复杂系统**，但我们的工具——终端——仍然是二十世紀七十年代的产物。输入命令、查看输出、再次输入……这条线性交互链路上，大量时间消耗在"怎么拼命令"而不是"问题是什么"上。

AI 大模型的出现，正在重新定义人与终端的交互方式。

本文带你完整搭建一套**运行在你自己的 VPS 上的 AI Terminal Copilot**——基于本地部署的轻量级 LLM（Ollama + Qwen2.5），实现自然语言驱动的命令执行、智能故障排查、自动化脚本生成和运维知识问答，全程无需外网 API，数据完全留在你自己的服务器里。

---

## 为什么选择本地 LLM 而不是云端 API？

在深入技术细节之前，先说清楚一个关键决策：**为什么要在 VPS 上跑本地模型，而不是调用 OpenAI 或 Claude 的 API？**

| 维度 | 云端 API | 本地 LLM（本文方案） |
|------|---------|---------------------|
| 数据隐私 | 命令和历史上传到第三方 | 全部本地处理，零泄露风险 |
| 网络依赖 | 需要稳定外网连接 | 完全离线可用 |
| 延迟 | 网络往返 200ms-2s | 本地推理 50-200ms |
| 成本 | 按 token 计费，高频使用昂贵 | 一次性硬件成本，后续免费 |
| 可控性 | 受制于服务商政策变化 | 完全自主，随时升级模型 |
| 审计合规 | 不符合等保/内部合规要求 | 满足所有合规要求 |

对于运维场景而言，终端里执行的每一条命令都可能涉及生产环境——数据库查询、配置文件修改、服务重启。**把运维意图发送给第三方 API 是不可接受的**。本地部署 LLM 是唯一合规且可靠的选择。

---

## 系统架构

```
┌──────────────────────────────────────────────────────────────────────┐
│                        用户终端 (SSH / 本地)                         │
│                                                                      │
│   "帮我查一下 nginx 的错误日志，看看最近有什么异常"                    │
│                              ▼                                       │
│   ┌─────────────────────────────────────────────────────────┐       │
│   │              Terminal Copilot 中间件                      │       │
│   │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐  │       │
│   │  │  意图解析    │→│  命令生成    │→│  安全沙箱执行    │  │       │
│   │  │  (LLM)      │  │  (LLM + 模板)│  │  (只读优先)     │  │       │
│   │  └─────────────┘  └─────────────┘  └────────┬────────┘  │       │
│   └──────────────────────────────────────────────┼──────────┘       │
│                              ▼                                             │
│   ┌─────────────────────────────────────────────────────────┐       │
│   │                  Ollama 本地推理引擎                      │       │
│   │         Qwen2.5-7B-Instruct / GLM-4-9B                  │       │
│   │   ┌──────────────┐  ┌──────────────┐  ┌─────────────┐  │       │
│   │   │  运维知识库   │  │  命令上下文   │  │  历史会话   │  │       │
│   │   │  (RAG 检索)  │  │  (环境变量)   │  │  (记忆)     │  │       │
│   │   └──────────────┘  └──────────────┘  └─────────────┘  │       │
│   └─────────────────────────────────────────────────────────┘       │
│                              ▼                                       │
│   ┌─────────────────────────────────────────────────────────┐       │
│   │                     VPS 系统层                           │       │
│   │   systemd · Prometheus · journald · Docker · Nginx · ... │       │
│   └─────────────────────────────────────────────────────────┘       │
└──────────────────────────────────────────────────────────────────────┘
```

整体分为三层：

1. **交互层（Copilot 中间件）**：接收自然语言输入，调用 LLM 解析意图并生成命令，在安全策略下执行并返回结果。
2. **推理层（Ollama）**：本地运行的 LLM 推理引擎，支持多种开源模型，提供 OpenAI 兼容 API。
3. **数据层（知识库 + 上下文）**：运维知识库（RAG）、系统状态快照、会话历史，让 LLM 的输出更准确、更有针对性。

---

## 第一步：部署 Ollama 本地推理引擎

### 1.1 Docker Compose 一键部署

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
    # 如果需要 GPU 加速（有 NVIDIA GPU 时）
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

启动服务：

```bash
docker compose up -d
```

### 1.2 拉取模型

推荐使用 **Qwen2.5-7B-Instruct**（阿里通义千问，中文能力强，资源占用适中）：

```bash
# 在 VPS 上直接拉取
curl -X POST http://localhost:11434/api/pull \
  -H "Content-Type: application/json" \
  -d '{"name": "qwen2.5:7b-instruct"}'

# 验证模型可用
curl http://localhost:11434/api/tags | jq .models
```

如果 VPS 内存较小（4GB），可以换用更轻量的模型：

```bash
# 1.5B 超轻量版（响应快，能力弱）
curl -X POST http://localhost:11434/api/pull -d '{"name": "qwen2.5:1.5b-instruct"}'

# 3B 平衡版（推荐低配机器）
curl -X POST http://localhost:11434/api/pull -d '{"name": "qwen2.5:3b-instruct"}'
```

> **模型选择建议**：运维场景需要较强的逻辑推理和代码生成能力，7B 是最佳平衡点。4GB 内存以上推荐 7B，2GB 内存用 3B，1GB 内存用 1.5B。

---

## 第二步：构建 Copilot 中间件

### 2.1 核心设计思路

Copilot 的核心循环很简单：

```
用户自然语言 → LLM 意图解析 → 生成命令 → 安全校验 → 执行 → 结果格式化 → 返回用户
```

关键在于**安全校验**和**结果格式化**——LLM 生成的命令不能盲目执行，返回的结果也需要结构化呈现。

### 2.2 完整 Python 实现

```python
# copilot/main.py
#!/usr/bin/env python3
"""
AI Terminal Copilot — 本地 LLM 驱动的运维终端助手
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

# 配置
OLLAMA_API = os.getenv("OLLAMA_API", "http://localhost:11434")
MODEL = os.getenv("COPILOT_MODEL", "qwen2.5:7b-instruct")
SESSION_DIR = Path(os.getenv("SESSION_DIR", str(Path.home() / ".copilot/sessions")))
KNOWLEDGE_DIR = Path(os.getenv("KNOWLEDGE_DIR", str(Path.home() / ".copilot/knowledge")))
SYSTEM_CONTEXT_FILE = Path(os.getenv("SYSTEM_CONTEXT", str(Path.home() / ".copilot/system_context.txt")))

# 安全策略：禁止执行的命令前缀
DANGEROUS_PREFIXES = [
    "rm -rf /", "rm -rf /*", "mkfs", "dd if=",
    "curl ... | sh", "wget ... | bash",
    "chmod 777", "chown -R",
]

# 允许的高风险命令（需要二次确认）
REQUIRES_CONFIRMATION = [
    "systemctl stop", "systemctl restart", "docker stop",
    "docker rm", "kill ", "iptables -F",
]

def load_system_context() -> str:
    """加载系统上下文：当前服务器信息、运行的服务、关键配置摘要"""
    if SYSTEM_CONTEXT_FILE.exists():
        return SYSTEM_CONTEXT_FILE.read_text()

    context_parts = []
    # 基础系统信息
    try:
        hostname = subprocess.check_output(
            ["hostname"], text=True, stderr=subprocess.DEVNULL
        ).strip()
        uptime = subprocess.check_output(
            ["uptime", "-p"], text=True, stderr=subprocess.DEVNULL
        ).strip()
        context_parts.append(f"Hostname: {hostname}")
        context_parts.append(f"Uptime: {uptime}")
    except Exception:
        pass

    # 运行的 Docker 容器
    try:
        containers = subprocess.check_output(
            ["docker", "ps", "--format", "table {{.Names}}\t{{.Image}}\t{{.Status}}"],
            text=True, stderr=subprocess.DEVNULL
        ).strip()
        if containers:
            context_parts.append(f"\nRunning containers:\n{containers}")
    except Exception:
        pass

    # 关键服务状态
    for svc in ["nginx", "docker", "prometheus", "grafana", "ollama"]:
        try:
            status = subprocess.check_output(
                ["systemctl", "is-active", svc],
                text=True, stderr=subprocess.DEVNULL
            ).strip()
            context_parts.append(f"Service {svc}: {status}")
        except Exception:
            pass

    return "\n".join(context_parts)


def build_system_prompt(session_history: list = None) -> str:
    """构建 LLM 的系统提示词"""
    sys_ctx = load_system_context()

    prompt = f"""你是一个运行在 Linux VPS 上的 AI 运维助手（Terminal Copilot）。

## 当前系统环境
{sys_ctx}

## 你的职责
1. 理解用户的自然语言运维需求
2. 生成准确的 shell 命令来完成任务
3. 对命令输出进行解释和分析
4. 发现异常时主动给出修复建议

## 命令生成规则
- 优先使用只读命令（`--dry-run`、`-n` 参数）确认影响范围
- 涉及写入操作前先说明将要做什么
- 使用 `2>&1` 捕获 stderr，避免遗漏错误信息
- 长命令用反斜杠 `\` 换行，保持可读性
- 避免使用 `sudo`，假设用户已在 root 环境下

## 安全策略
- 不生成破坏性命令（rm -rf /、格式化磁盘等）
- 涉及服务重启、防火墙变更时，必须提示风险
- 对不确定效果的命令，先建议用 dry-run 测试

## 输出格式
对于每个请求，按以下结构回复：
- **分析**：一句话说明你在做什么
- **命令**：```bash\n{命令}\n```
- **预期输出**：简要描述预期结果（如适用）
- **注意事项**：潜在风险和后续步骤

## 已知运维知识库位置
{KNOWLEDGE_DIR}

请用中文回复。"""

    if session_history:
        prompt += "\n\n## 历史对话记录\n"
        for turn in session_history[-10:]:  # 只保留最近10轮
            prompt += f"用户: {turn['user']}\n助手: {turn['assistant']}\n"

    return prompt


def chat_with_ollama(system_prompt: str, user_message: str, stream: bool = False) -> str:
    """调用 Ollama API 进行对话"""
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "stream": stream,
        "options": {
            "temperature": 0.3,  # 运维场景需要确定性输出
            "num_ctx": 8192,
        },
    }

    try:
        resp = requests.post(
            f"{OLLAMA_API}/api/chat",
            json=payload,
            timeout=120,
            stream=stream,
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
        return "⚠️ 请求超时，模型可能正在加载或负载过高。"
    except requests.exceptions.ConnectionError:
        return f"⚠️ 无法连接到 Ollama ({OLLAMA_API})，请确认服务已启动。"
    except Exception as e:
        return f"⚠️ 调用 LLM 出错: {e}"


def extract_commands(response: str) -> list[str]:
    """从 LLM 回复中提取 bash 代码块中的命令"""
    import re
    # 匹配 ```bash ... ``` 或 ``` ... ``` 中的内容
    pattern = r"```(?:bash)?\s*\n(.*?)\n```"
    matches = re.findall(pattern, response, re.DOTALL)
    return [m.strip() for m in matches if m.strip()]


def execute_command(cmd: str, timeout: int = 30) -> tuple[int, str, str]:
    """在安全沙箱中执行命令"""
    # 安全检查
    for prefix in DANGEROUS_PREFIXES:
        if cmd.startswith(prefix) or prefix in cmd:
            return -1, "", f"🚫 拒绝执行危险命令: {cmd}"

    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"⏱️ 命令执行超时（{timeout}s）: {cmd}"
    except Exception as e:
        return -1, "", f"❌ 执行异常: {e}"


def ask_confirmation(cmd: str) -> bool:
    """对高风险命令请求确认"""
    for prefix in REQUIRES_CONFIRMATION:
        if cmd.startswith(prefix):
            answer = input(f"\n⚠️ 即将执行可能影响服务的命令:\n  {cmd}\n确认执行? (y/N) ")
            return answer.lower() == "y"
    return True


def run_copilot_interactive():
    """交互式 REPL 模式"""
    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_file = SESSION_DIR / f"{session_id}.json"
    SESSION_DIR.mkdir(parents=True, exist_ok=True)

    session_history = []

    print("=" * 60)
    print("  🤖 AI Terminal Copilot — 本地运维助手")
    print(f"  模型: {MODEL}")
    print(f"  会话: {session_id}")
    print("  输入 '/exit' 退出, '/clear' 清空历史, '/run <cmd>' 执行命令")
    print("=" * 60)

    while True:
        try:
            user_input = input("\n👤 你> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 再见!")
            break

        if not user_input:
            continue

        # 特殊命令
        if user_input == "/exit":
            # 保存会话
            if session_file.exists():
                existing = json.loads(session_file.read_text())
                existing["history"].extend(session_history)
                session_file.write_text(json.dumps(existing, ensure_ascii=False, indent=2))
            print("👋 再见!")
            break

        if user_input == "/clear":
            session_history = []
            print("🗑️ 历史已清空")
            continue

        if user_input.startswith("/run "):
            cmd = user_input[5:].strip()
            if ask_confirmation(cmd):
                code, stdout, stderr = execute_command(cmd)
                print(f"\n{'='*40}")
                print(f"💻 执行结果 (exit={code}):")
                print(f"{'='*40}")
                if stdout:
                    print(f"📤 STDOUT:\n{stdout}")
                if stderr:
                    print(f"📥 STDERR:\n{stderr}")
            continue

        # 正常对话
        sys_prompt = build_system_prompt(session_history)
        reply = chat_with_ollama(sys_prompt, user_input)

        print(f"\n🤖 Copilot> {reply}")

        # 记录历史
        session_history.append({"user": user_input, "assistant": reply})

        # 自动提取并执行命令（可选功能）
        commands = extract_commands(reply)
        if commands and len(commands) <= 2:  # 只自动执行不超过2条简单命令
            auto_run = input("🔄 是否自动执行上述命令? (y/N) ").strip().lower()
            if auto_run == "y":
                for cmd in commands:
                    if ask_confirmation(cmd):
                        print(f"\n📤 执行: {cmd}")
                        code, stdout, stderr = execute_command(cmd)
                        if stdout:
                            print(stdout)
                        if stderr:
                            print(stderr, file=sys.stderr)


def run_copilot_one_shot(prompt: str, auto_exec: bool = False):
    """单次非交互式模式：适合脚本调用和 cron 任务"""
    sys_prompt = build_system_prompt()
    reply = chat_with_ollama(sys_prompt, prompt)

    print(reply)

    if auto_exec:
        commands = extract_commands(reply)
        for cmd in commands:
            print(f"\n▶️ 执行: {cmd}")
            code, stdout, stderr = execute_command(cmd)
            if stdout:
                print(stdout)
            if stderr:
                print(stderr, file=sys.stderr)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI Terminal Copilot")
    parser.add_argument("-p", "--prompt", help="单次提示词模式")
    parser.add_argument("-a", "--auto-exec", action="store_true", help="自动执行生成的命令")
    args = parser.parse_args()

    if args.prompt:
        run_copilot_one_shot(args.prompt, args.auto_exec)
    else:
        run_copilot_interactive()
```

### 2.3 安装依赖

```bash
pip install requests
# 或
pip3 install --user requests
```

### 2.4 创建运维知识库目录

```bash
mkdir -p ~/.copilot/knowledge
mkdir -p ~/.copilot/sessions

# 创建系统上下文文件
cat > ~/.copilot/system_context.txt << 'EOF'
# 此文件由 Copilot 自动生成，包含当前系统的关键信息
# 每次启动时重新生成
EOF
```

---

## 第三步：运维知识库（RAG 增强）

光靠 LLM 本身的知识不够准确，我们需要给它挂载一个**运维知识库**——把你服务器上特有的配置、常见故障处理方案、运维 SOP 喂给它。

### 3.1 知识库文件格式

在 `~/.copilot/knowledge/` 下存放 Markdown 格式的运维文档：

```markdown
# incidents/nginx-502-guide.md
# 标题: Nginx 502 Bad Gateway 排查指南
# 标签: nginx, 502, 故障排查

## 常见原因
1. 后端服务未启动或崩溃
2. upstream 配置错误
3. 后端响应超时（proxy_read_timeout）
4. 端口被占用或防火墙拦截

## 排查步骤
\`\`\`bash
# 1. 检查 nginx 状态
systemctl status nginx

# 2. 查看错误日志
tail -50 /var/log/nginx/error.log

# 3. 检查后端服务
curl -v http://127.0.0.1:YOUR_BACKEND_PORT/health

# 4. 检查端口监听
ss -tlnp | grep YOUR_PORT
\`\`\`

## 快速修复
\`\`\`bash
# 重启 nginx
systemctl restart nginx

# 如果是后端问题，重启对应服务
systemctl restart YOUR_SERVICE
\`\`\`
```

### 3.2 集成 RAG 检索

扩展 Copilot 的意图解析部分，加入知识库检索：

```python
# copilot/rag.py
import os
import re
from pathlib import Path
import requests

KNOWLEDGE_DIR = Path(os.getenv("KNOWLEDGE_DIR", str(Path.home() / ".copilot/knowledge")))

def semantic_search(query: str, top_k: int = 3) -> list[dict]:
    """
    简单的关键词检索（可升级为向量检索）
    在实际生产环境中，可以接入 ChromaDB / Qdrant 做语义搜索
    """
    results = []
    query_terms = set(re.findall(r'[\u4e00-\u9fa5a-zA-Z]+', query.lower()))

    for md_file in KNOWLEDGE_DIR.rglob("*.md"):
        content = md_file.read_text(errors="ignore")
        # 提取标签
        tags = set(re.findall(r'# 标签:\s*(.+)', content))
        # 计算相关性得分
        score = 0
        title_match = 0
        # 标题匹配加分
        title_match = sum(1 for t in query_terms if t in md_file.stem.lower())
        # 内容匹配
        content_lower = content.lower()
        content_score = sum(1 for t in query_terms if t in content_lower)
        # 标签匹配加倍
        tag_score = sum(2 for t in query_terms if t in str(tags).lower())

        score = title_match * 3 + content_score + tag_score

        if score > 0:
            # 提取片段（标题 + 前200字符）
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
    """将检索结果注入系统提示词"""
    docs = semantic_search(query)
    if not docs:
        return base_prompt

    ctx = "\n\n## 相关运维知识库\n"
    for doc in docs:
        ctx += f"\n### [{doc['title']}] (相关性: {doc['score']})\n"
        ctx += f"{doc['snippet']}...\n"

    return base_prompt + ctx
```

---

## 第四步：实际使用场景演示

### 场景 1：自然语言排查 Nginx 502

```
👤 你> nginx 502 了，帮我查一下原因

🤖 Copilot> 
**分析**：用户反馈 Nginx 502 错误，需要诊断后端服务状态和 Nginx 配置。

**命令**：
```bash
# 查看 Nginx 错误日志最后50行
tail -50 /var/log/nginx/error.log

# 检查后端服务是否运行
systemctl is-active your-backend-service

# 测试后端健康端点
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8080/health
```

**预期输出**：错误日志会显示 `upstream timed out` 或 `connect() failed`；后端服务状态为 `inactive`；健康检查返回非 200 状态码。

**注意事项**：如果后端服务未启动，执行 `systemctl start your-backend-service` 后再次验证。
```

### 场景 2：智能生成 crontab 定时任务

```
👤 你> 每天凌晨2点备份 MySQL 数据库，保留最近7天的备份

🤖 Copilot>
**分析**：用户需要创建一个 MySQL 数据库备份的定时任务，带自动清理旧备份的逻辑。

**命令**：
```bash
# 编辑 crontab
crontab -e

# 添加以下行（每天凌晨2点执行）
0 2 * * * mysqldump -u root -p'YOUR_PASSWORD' --all-databases | gzip > /backup/mysql_$(date +\%Y\%m\%d).sql.gz && find /backup -name "mysql_*.sql.gz" -mtime +7 -delete
```

**预期输出**：crontab 编辑器打开，保存后定时任务生效。

**注意事项**：
- 请替换 `YOUR_PASSWORD` 为你的 MySQL root 密码（建议改用 `.my.cnf` 凭证文件避免明文）
- 确保 `/backup` 目录存在且有足够空间
- 先手动测试一次：`mysqldump -u root -p'密码' --all-databases | gzip > /backup/test.sql.gz`
```

### 场景 3：磁盘空间分析

```
👤 你> 磁盘空间快满了，帮我找出占用最大的目录

🤖 Copilot>
**分析**：诊断磁盘占用，定位大文件和目录。

**命令**：
```bash
# 查看各分区使用率
df -h

# 找出根目录下最大的10个目录
du -ah / 2>/dev/null | sort -rh | head -10

# 检查 /var/log 下的日志大小
du -sh /var/log/* 2>/dev/null | sort -rh | head -10

# 检查 Docker 容器/镜像占用
docker system df
```

**预期输出**：定位到大文件所在目录（可能是日志轮转失败的日志文件、Docker 镜像或未清理的临时文件）。

**注意事项**：如果是日志文件过大，考虑配置 logrotate；如果是 Docker 垃圾数据，执行 `docker system prune -a`。
```

---

## 第五步：部署为 systemd 服务（可选）

如果你希望 Copilot 作为常驻服务运行（例如供 Web 界面或 webhook 调用）：

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

## 进阶：接入更多能力

### 7.1 多模型切换

```python
# 根据任务类型自动选择模型
MODEL_ROUTING = {
    "command_generation": "qwen2.5:7b-instruct",   # 复杂推理
    "log_analysis": "qwen2.5:7b-instruct",         # 文本理解
    "quick_query": "qwen2.5:3b-instruct",          # 简单问答，快速响应
    "code_review": "qwen2.5:7b-instruct",          # 代码相关
}
```

### 7.2 与 Prometheus 联动

```python
def get_prometheus_context(query: str) -> str:
    """从 Prometheus 获取当前关键指标，注入 LLM 上下文"""
    try:
        # 获取关键指标快照
        metrics = {
            "cpu_usage": "100 - (avg by(instance) (rate(node_cpu_seconds_total{mode=\"idle\"}[5m])) * 100)",
            "memory_usage": "(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100",
            "disk_usage": "(1 - (node_filesystem_avail_bytes{mountpoint=\"/\"} / node_filesystem_size_bytes{mountpoint=\"/\"})) * 100",
        }
        return json.dumps(metrics, indent=2)
    except Exception:
        return ""
```

### 7.3 接入 Web UI

使用 Streamlit 快速构建 Web 界面：

```python
# copilot/web_ui.py
import streamlit as st
from copilot.main import chat_with_ollama, build_system_prompt

st.set_page_config(page_title="AI Terminal Copilot", page_icon="🤖", layout="wide")
st.title("🤖 AI Terminal Copilot")
st.caption("本地 LLM 驱动的 VPS 运维助手")

if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("输入你的运维问题..."):
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

运行：`streamlit run copilot/web_ui.py`

---

## 性能与资源参考

| 模型 | 内存占用 | 推理速度 | 适用场景 |
|------|---------|---------|---------|
| qwen2.5:1.5b | ~1 GB | ~50ms/token | 简单问答、状态查询 |
| qwen2.5:3b | ~2 GB | ~80ms/token | 日常运维、命令生成 |
| qwen2.5:7b | ~5 GB | ~150ms/token | 复杂排障、代码生成 |
| glm-4-9b | ~6 GB | ~200ms/token | 中文理解强、知识问答 |

> **推荐配置**：8GB 内存 VPS + 7B 模型是最实用的组合。4GB 内存可选择 3B 模型，响应速度仍然很快。

---

## 总结

本文完整介绍了如何在 VPS 上搭建一套**本地 AI Terminal Copilot**：

1. **Ollama + Qwen2.5** 提供本地 LLM 推理能力，数据不出服务器
2. **Python 中间件** 实现意图解析 → 命令生成 → 安全执行 → 结果反馈的完整闭环
3. **运维知识库（RAG）** 让 LLM 了解你服务器的独特配置和故障处理经验
4. **交互式 REPL + 脚本模式 + Web UI** 三种使用方式，适配不同场景

这套系统的核心价值在于：**把运维经验转化为可复用的 AI 能力**——无论是你第一次搭建的服务架构，还是去年解决过的那个诡异 bug，都可以沉淀为知识库，让 Copilot 在下次遇到类似问题时给出更准确的建议。

不需要付费 API，不需要稳定外网，不需要担心数据泄露。你的 VPS，你的 AI，你的运维。

---

## 附录：完整部署清单

```bash
# 1. 部署 Ollama
docker compose up -d
docker exec -it ollama ollama pull qwen2.5:7b-instruct

# 2. 安装 Copilot
mkdir -p ~/.copilot/{knowledge,sessions}
cp -r /opt/copilot/* ~/.copilot/
pip3 install --user requests

# 3. 初始化知识库
echo "# 运维知识库目录" > ~/.copilot/knowledge/README.md

# 4. 启动 Copilot
python3 ~/.copilot/main.py

# 或者单次模式
python3 ~/.copilot/main.py -p "帮我查一下 nginx 状态" --auto-exec
```
