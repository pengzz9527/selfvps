---
title: "AI 智能日志分析：LLM 驱动的 VPS 日志异常检测与自动告警"
description: "将 LLM 接入你的 VPS 日志管道，实现智能异常检测、自动根因分析和告警摘要，告别手动翻日志的时代"
date: 2026-06-16T21:00:00+08:00
lastmod: 2026-06-16T21:00:00+08:00
slug: "ai-log-analysis-anomaly-detection"
image: /images/posts/ai-log-analysis-anomaly-detection/featured.png
tags: ["AI", "LLM", "日志分析", "异常检测", "VPS", "自动化", "RAG", "运维"]
categories: ["AI + VPS"]
aliases: [/zh/post/ai-log-analysis-anomaly-detection/]
---

## 引言

作为 VPS 运维者，你一定经历过这样的场景：

- 凌晨三点收到一条模糊的告警短信，打开服务器一看日志密密麻麻，根本不知道问题出在哪
- 网站访问变慢，翻了三小时 Nginx 错误日志，最后发现只是一个过期的 SSL 证书
- 磁盘空间被某个服务的 debug 日志占满，但你看不到模式，只能粗暴地删除

**传统日志分析的瓶颈在于：人类不擅长从海量非结构化文本中发现模式。**

而 LLM（大语言模型）恰恰擅长这件事——理解语义、识别异常、归纳总结。本文将介绍如何用 **LLM + RAG + 轻量级规则引擎** 的组合，为你的 VPS 搭建一套智能日志分析系统，实现：

- 🔍 **异常检测**：自动识别日志中的错误模式和异常行为
- 🧠 **根因分析**：用 LLM 理解上下文，给出可能的原因和建议
- 📝 **告警摘要**：将几百行日志压缩成一段可读的摘要
- ⚡ **实时响应**：在问题发生时就收到结构化报告

---

## 1. 整体架构

```
┌─────────────────────────────────────────────────────────┐
│                      你的 VPS                             │
│                                                         │
│  ┌──────────┐    ┌──────────────┐    ┌───────────────┐  │
│  │ 应用/服务 │───▶│  Log 收集器   │───▶│  模式匹配引擎  │  │
│  │ (Nginx   │    │  (Vector     │    │  (正则 + 阈值) │  │
│  │  Docker  │    │   journald)  │    └───────┬───────┘  │
│  │  等)     │    └──────────────┘            │          │
│  └──────────┘                    ┌──────────▼───────┐  │
│                                  │  LLM 分析引擎     │  │
│                                  │  (本地/云端 API)  │  │
│                                  └──────────┬───────┘  │
│                                             │           │
│                              ┌──────────────▼───────┐  │
│                              │  告警通知层           │  │
│                              │  (Telegram/DingTalk)  │  │
│                              └──────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

核心思路：
1. **Log 收集层**：用 Vector 或 Fluent Bit 统一收集所有服务的日志
2. **快速过滤层**：用正则和阈值做初步筛选，减少送入 LLM 的数据量
3. **AI 分析层**：将筛选后的日志片段送给 LLM 进行语义分析和根因推断
4. **通知层**：将 AI 的分析结果以结构化格式推送给你

---

## 2. 日志收集：用 Vector 统一日志管道

[Vector](https://vector.dev) 是一个高性能、低资源消耗的日志管道工具，比 Fluentd 更轻量，比 Fluent Bit 功能更丰富。

### 安装 Vector

```bash
# Ubuntu/Debian
curl --proto '=https' --tlsv1.2 -sSf https://sh.vector.dev | sh
sudo systemctl enable vector
sudo systemctl start vector
```

### 配置 Vector 收集多源日志

创建 `/etc/vector/vector.toml`：

```toml
# 数据源：收集 Nginx 错误日志
[sources.nginx_errors]
type = "file"
include = ["/var/log/nginx/error.log"]
read_from = "beginning"

# 数据源：收集 Docker 容器日志
[sources.docker_logs]
type = "docker_logs"

# 数据源：收集 systemd journal
[sources.journald]
type = "journald"
journal_directory = "/var/log/journal"

# 转换层：标记异常日志
[transforms.flag_important]
type = "remap"
inputs = ["nginx_errors", "docker_logs", "journald"]
source = '''
.important = contains(.message, "error") || 
             contains(.message, "fatal") || 
             contains(.message, "panic") ||
             contains(.message, "OOM") ||
             contains(.message, "timeout") ||
             contains(.message, "connection refused") ||
             (.level == "err" or .level == "critical")
'''

# 转换层：对重要日志添加时间窗口聚合
[transforms.windowed_logs]
type = "coalesce"
inputs = ["flag_important"]
max_wait_ms = 30000  # 30秒窗口

# 输出层：发送到本地 HTTP 端点供 AI 服务消费
[transforms.to_ai_service]
type = "remap"
inputs = ["windowed_logs"]
source = '''
.ai_payload = {
  "timestamp": now(),
  "service": .service // "unknown",
  "level": .level // "info",
  "message": .message,
  "host": host,
}
'''

[sinks.http_ai]
type = "http"
inputs = ["to_ai_service"]
uri = "http://127.0.0.1:8080/logs"
method = "post"
encoding.codec = "json"
```

Vector 的资源消耗极低——通常占用 **10-20MB 内存**，对 VPS 几乎无感。

---

## 3. 快速过滤：减少 LLM 调用成本

直接把所有日志送进 LLM 既不经济也不高效。我们需要一个**预过滤层**来识别真正需要 AI 介入的日志。

### 3.1 基于规则的快速过滤

```python
# filters.py - 快速规则引擎
import re
from datetime import datetime, timedelta

# 预定义的错误模式
ERROR_PATTERNS = [
    re.compile(r'(?i)(error|fail|fatal|panic|crash)'),
    re.compile(r'(?i)(OOM|out of memory|killed process)'),
    re.compile(r'(?i)(connection refused|timeout|deadline exceeded)'),
    re.compile(r'(?i)(SSL handshake failed|certificate.*expired)'),
    re.compile(r'(?i)(disk full|no space left|quota exceeded)'),
    re.compile(r'(?i)(permission denied|access forbidden)'),
    re.compile(r'(?i)(segmentation fault|core dumped)'),
]

# 频率阈值：同一模式在 5 分钟内出现超过 N 次才触发
FREQ_THRESHOLD = {
    'auth_failure': 10,    # 认证失败 10 次以上
    'http_error': 50,      # HTTP 错误 50 次以上
    'connection_refused': 5,  # 连接拒绝 5 次以上
}

class QuickFilter:
    def __init__(self):
        self.window_start = datetime.now() - timedelta(minutes=5)
        self.pattern_counts = {}
    
    def needs_ai_analysis(self, log_entry: dict) -> bool:
        """判断日志是否需要 AI 深度分析"""
        message = log_entry.get('message', '')
        
        # 检查是否匹配错误模式
        if not any(p.search(message) for p in ERROR_PATTERNS):
            return False
        
        # 统计频率
        severity = self._classify_severity(message)
        key = f"{severity}:{log_entry.get('service', 'unknown')}"
        self.pattern_counts[key] = self.pattern_counts.get(key, 0) + 1
        
        # 超过阈值才触发
        threshold = FREQ_THRESHOLD.get(severity, 5)
        return self.pattern_counts[key] >= threshold
    
    def _classify_severity(self, message: str) -> str:
        if re.search(r'(?i)(fatal|panic|core dump)', message):
            return 'critical'
        if re.search(r'(?i)(OOM|killed process)', message):
            return 'oom'
        if re.search(r'(?i)(error|fail)', message):
            return 'error'
        return 'warning'
```

### 3.2 滑动窗口聚合

对于短时间内大量重复的日志（比如某个服务崩溃导致每秒产生 100 条错误），我们不做 100 次 LLM 调用，而是**聚合为一个样本**：

```python
# aggregator.py
from collections import defaultdict
import hashlib

class LogAggregator:
    def __init__(self, window_seconds=60):
        self.window = window_seconds
        self.buckets = defaultdict(list)
    
    def add(self, log_entry: dict):
        # 用消息内容生成哈希，相同内容的日志归为一组
        msg_hash = hashlib.md5(
            log_entry['message'].encode()
        ).hexdigest()[:8]
        
        bucket_key = f"{msg_hash}:{log_entry.get('service', 'unknown')}"
        self.buckets[bucket_key].append(log_entry)
    
    def get_aggregated(self) -> list:
        """返回聚合后的日志摘要"""
        results = []
        for key, entries in self.buckets.items():
            results.append({
                'bucket_key': key,
                'count': len(entries),
                'first_seen': min(e.get('timestamp') for e in entries),
                'last_seen': max(e.get('timestamp') for e in entries),
                'sample': entries[-1],  # 最新的一条作为样本
                'messages': list(set(e['message'] for e in entries)),  # 去重
            })
        return results
```

---

## 4. AI 分析引擎：LLM 驱动的智能诊断

这是整个系统的核心。我们用一个轻量级的 HTTP 服务接收过滤后的日志，调用 LLM 进行分析。

### 4.1 快速上手：使用 OpenRouter 或本地 LLM

你可以选择：
- **云端 API**：OpenRouter、Together AI、Google Gemini 等
- **本地部署**：Ollama + Llama 3 / Qwen 2.5（推荐 8B 模型）

以下示例使用 OpenRouter API，你也可以轻松切换到本地 Ollama。

### 4.2 分析服务代码

```python
# ai_service.py - 智能日志分析服务
import http.server
import json
import requests
from datetime import datetime
from filters import QuickFilter
from aggregator import LogAggregator

# LLM 配置
LLM_API_URL = "https://openrouter.ai/api/v1/chat/completions"
LLM_API_KEY = "sk-or-xxxxx"  # 替换为你的 API Key
LLM_MODEL = "qwen/qwen-2.5-7b-instruct:free"  # 免费模型可用

# 如果使用本地 Ollama，改为：
# LLM_API_URL = "http://localhost:11434/api/chat"

FILTER = QuickFilter()
AGGREGATOR = LogAggregator(window_seconds=60)

SYSTEM_PROMPT = """你是一个专业的 VPS 运维专家，擅长日志分析和故障排查。

你的职责：
1. **识别异常**：从提供的日志中找出真正的异常事件
2. **根因分析**：根据错误信息、服务依赖和时间线推断最可能的原因
3. **风险评估**：判断问题的严重性和紧急程度
4. **修复建议**：给出具体、可操作的修复步骤

请以如下 JSON 格式回复：
{
  "summary": "一句话概括问题",
  "severity": "critical|high|medium|low|info",
  "root_cause": "详细的原因分析",
  "affected_services": ["受影响的组件列表"],
  "recommendations": ["具体修复步骤"],
  "keywords": ["用于后续搜索的关键标签"]
}

注意：只返回 JSON，不要包含其他解释文字。"""

class LogAnalysisHandler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != '/logs':
            self.send_response(404)
            self.end_headers()
            return
        
        content_length = int(self.headers['Content-Length'])
        log_entry = json.loads(self.rfile.read(content_length))
        
        # 添加到聚合器
        AGGREGATOR.add(log_entry)
        
        # 判断是否需要 AI 分析
        if not FILTER.needs_ai_analysis(log_entry):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps({"status": "filtered"}).encode())
            return
        
        # 获取聚合后的日志
        aggregated = AGGREGATOR.get_aggregated()
        
        # 构建 LLM 请求
        user_content = self._build_prompt(aggregated)
        
        # 调用 LLM
        response = self._call_llm(user_content)
        
        # 发送告警
        if response and self._should_alert(response):
            self._send_alert(response)
        
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({
            "status": "analyzed",
            "analysis": response
        }).encode())
    
    def _build_prompt(self, aggregated):
        """构建发给 LLM 的提示词"""
        log_snippets = []
        for item in aggregated:
            sample = item['sample']
            count = item['count']
            snippet = f"[{item['last_seen']}] [{sample.get('service', '?')}] " \
                      f"(发生 {count} 次): {sample.get('message', '')}"
            log_snippets.append(snippet)
        
        return f"以下是最近收集的异常日志：\n\n" + "\n".join(log_snippets) + \
               "\n\n请分析这些日志并给出诊断报告。"
    
    def _call_llm(self, user_content: str) -> dict:
        """调用 LLM API"""
        payload = {
            "model": LLM_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.3
        }
        
        headers = {
            "Authorization": f"Bearer {LLM_API_KEY}",
            "Content-Type": "application/json"
        }
        
        resp = requests.post(LLM_API_URL, json=payload, headers=headers, timeout=30)
        resp.raise_for_status()
        
        data = resp.json()
        content = data['choices'][0]['message']['content']
        return json.loads(content)
    
    def _should_alert(self, analysis: dict) -> bool:
        """判断是否需要发送告警通知"""
        return analysis.get('severity') in ('critical', 'high')
    
    def _send_alert(self, analysis: dict):
        """发送告警到 Telegram / 钉钉"""
        # Telegram Bot
        bot_token = "YOUR_BOT_TOKEN"
        chat_id = "YOUR_CHAT_ID"
        
        severity_emoji = {'critical': '🔴', 'high': '🟠', 'medium': '🟡', 'low': '🔵'}
        emoji = severity_emoji.get(analysis.get('severity', 'low'), '🔵')
        
        alert_text = (
            f"{emoji} **VPS 异常告警**\n\n"
            f"**摘要**: {analysis.get('summary', 'N/A')}\n"
            f"**严重度**: {analysis.get('severity', 'unknown')}\n\n"
            f"**根因**: {analysis.get('root_cause', 'N/A')}\n\n"
            f"**建议操作**:\n"
        )
        for i, rec in enumerate(analysis.get('recommendations', []), 1):
            alert_text += f"{i}. {rec}\n"
        
        # 发送到 Telegram
        telegram_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        requests.post(telegram_url, json={
            "chat_id": chat_id,
            "text": alert_text,
            "parse_mode": "Markdown"
        }, timeout=10)

if __name__ == '__main__':
    server = http.server.HTTPServer(('127.0.0.1', 8080), LogAnalysisHandler)
    print("AI 日志分析服务已启动，监听 :8080")
    server.serve_forever()
```

### 4.3 使用 Ollama 本地部署（零 API 费用）

如果你不想花 API 费用，可以用 Ollama 在 VPS 上跑本地模型：

```bash
# 安装 Ollama
curl -fsSL https://ollama.com/install.sh | sh

# 拉取适合日志分析的模型（Qwen 2.5 7B 中文能力强）
ollama pull qwen2.5:7b

# 创建自定义 Modelfile
cat > Modelfile << 'EOF'
FROM qwen2.5:7b
SYSTEM """你是一个专业的 VPS 运维专家，擅长日志分析和故障排查。
请用 JSON 格式回复，包含 summary、severity、root_cause、recommendations 字段。"""
EOF

ollama create ai-log-analyzer -f Modelfile

# 启动服务
ollama serve
```

修改 `ai_service.py` 中的 API 地址：
```python
LLM_API_URL = "http://localhost:11434/api/chat"
LLM_MODEL = "ai-log-analyzer"
```

**本地模型资源需求**：7B 模型大约需要 4-6GB 内存，所以建议至少 8GB 内存的 VPS。如果只有 2GB 内存，建议使用云端免费额度较小的模型。

---

## 5. 告警通知集成

### 5.1 Telegram Bot 告警

```python
import telebot

TELEGRAM_BOT_TOKEN = "your_bot_token"
TELEGRAM_CHAT_ID = "your_chat_id"

def send_telegram_alert(summary: str, analysis: dict):
    bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
    
    severity_map = {
        'critical': '🔴 严重',
        'high': '🟠 高危',
        'medium': '🟡 中等',
        'low': '🔵 低危',
    }
    
    text = (
        f"🖥️ *VPS 日志分析报告*\n\n"
        f"⚠️ *状态*: {severity_map.get(analysis.get('severity'), '未知')}\n"
        f"📋 *摘要*: {summary}\n\n"
        f"*根因分析*:\n{analysis.get('root_cause', 'N/A')}\n\n"
        f"*建议操作*:\n"
    )
    for i, rec in enumerate(analysis.get('recommendations', []), 1):
        text += f"{i}. {rec}\n"
    
    bot.send_message(TELEGRAM_CHAT_ID, text, parse_mode="Markdown")
```

### 5.2 钉钉机器人告警

```python
import hmac
import hashlib
import base64
import time
import requests

DINGTALK_WEBHOOK = "https://oapi.dingtalk.com/robot/send?access_token=xxx"
SECRET = "SECxxxxxxxx"

def send_dingtalk_alert(analysis: dict):
    # 签名计算
    timestamp = str(round(time.time() * 1000))
    string_to_sign = f"{timestamp}\n{SECRET}"
    hmac_code = hmac.new(
        SECRET.encode(), string_to_sign.encode(), digestmod=hashlib.sha256
    ).digest()
    sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
    
    url = f"{DINGTALK_WEBHOOK}&timestamp={timestamp}&sign={sign}"
    
    severity_text = {
        'critical': '🔴 严重告警',
        'high': '🟠 高危告警',
        'medium': '🟡 中等告警',
        'low': '🔵 低危提醒',
    }
    
    payload = {
        "msgtype": "markdown",
        "markdown": {
            "title": f"VPS 异常检测 - {severity_text.get(analysis.get('severity', ''), '未知')}",
            "text": (
                f"### {severity_text.get(analysis.get('severity', ''), '未知')}\\n\\n"
                f"**摘要**: {analysis.get('summary', 'N/A')}\\n\\n"
                f"**根因**: {analysis.get('root_cause', 'N/A')}\\n\\n"
                f"**建议操作**:\\n"
            ) + "".join(
                f"{i}. {rec}\\n" 
                for i, rec in enumerate(analysis.get('recommendations', []), 1)
            ),
        }
    }
    
    requests.post(url, json=payload, timeout=10)
```

---

## 6. 完整部署流程

### 6.1 一键部署脚本

```bash
#!/bin/bash
# deploy.sh - 一键部署 AI 日志分析系统

set -euo pipefail

echo "🚀 开始部署 AI 日志分析系统..."

# 1. 安装 Vector
echo "📦 安装 Vector..."
curl --proto '=https' --tlsv1.2 -sSf https://sh.vector.dev | bash -s -- -y
systemctl enable vector
systemctl start vector

# 2. 安装 Python 依赖
echo "🐍 安装 Python 依赖..."
pip3 install requests python-telegram-bot

# 3. 创建 AI 分析服务
echo "🤖 创建 AI 分析服务..."
mkdir -p ~/ai-log-analyzer
cd ~/ai-log-analyzer

# 复制 filters.py, aggregator.py, ai_service.py 到此处
# (从上面的代码块创建)

# 4. 创建 systemd 服务
cat > /etc/systemd/system/ai-log-analyzer.service << 'EOF'
[Unit]
Description=AI Log Analysis Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/ai-log-analyzer
ExecStart=/usr/bin/python3 /root/ai-log-analyzer/ai_service.py
Restart=always
RestartSec=10
Environment="PATH=/usr/local/bin:/usr/bin:/bin"

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable ai-log-analyzer
systemctl start ai-log-analyzer

# 5. 配置 Vector 输出到 AI 服务
cat > /etc/vector/vector.toml << 'EOF'
[sources.all_logs]
type = "docker_logs"

[transforms.filter_errors]
type = "remap"
inputs = ["all_logs"]
source = """
.important = contains(.message, "error") || 
             contains(.message, "fatal") ||
             contains(.message, "panic") ||
             contains(.message, "OOM")
"""

[sinks.http_ai]
type = "http"
inputs = ["filter_errors"]
uri = "http://127.0.0.1:8080/logs"
method = "post"
encoding.codec = "json"
EOF

systemctl restart vector

echo "✅ 部署完成！"
echo "📊 Vector 日志收集: systemd service 'vector'"
echo "🤖 AI 分析服务: http://127.0.0.1:8080/logs"
echo "📱 告警通知: 已集成 Telegram / 钉钉"
```

### 6.2 验证部署

```bash
# 检查 Vector 是否在运行
systemctl status vector

# 检查 AI 服务是否在运行
systemctl status ai-log-analyzer

# 模拟发送一条测试日志
curl -X POST http://127.0.0.1:8080/logs \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Connection refused to database at 127.0.0.1:5432",
    "service": "myapp",
    "level": "error",
    "timestamp": "'$(date -Iseconds)'",
    "host": "vps-001"
  }'

# 查看 AI 服务的响应
# 你应该收到一条包含 JSON 分析结果的响应
```

---

## 7. 进阶优化

### 7.1 历史日志 RAG 检索增强

当 LLM 回答"这是什么问题"时，如果能参考历史解决方案，准确率会大幅提升。我们可以用轻量级向量数据库实现：

```python
# rag_store.py - 简单的向量知识库
import sqlite3
import hashlib
from datetime import datetime

class LogKnowledgeBase:
    def __init__(self, db_path="/root/ai-log-analyzer/knowledge.db"):
        self.conn = sqlite3.connect(db_path)
        self._init_db()
    
    def _init_db(self):
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS knowledge (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                problem_hash TEXT UNIQUE,
                symptom TEXT,
                root_cause TEXT,
                solution TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                usage_count INTEGER DEFAULT 0
            )
        ''')
        self.conn.commit()
    
    def store_solution(self, symptom: str, root_cause: str, solution: str):
        """存储一次完整的故障排查记录"""
        problem_hash = hashlib.sha256(symptom.encode()).hexdigest()[:16]
        
        # 检查是否已存在相似问题
        existing = self.conn.execute(
            'SELECT id FROM knowledge WHERE problem_hash = ?',
            (problem_hash,)
        ).fetchone()
        
        if existing:
            self.conn.execute(
                'UPDATE knowledge SET usage_count = usage_count + 1 WHERE id = ?',
                (existing[0],)
            )
        else:
            self.conn.execute(
                'INSERT INTO knowledge (problem_hash, symptom, root_cause, solution) VALUES (?, ?, ?, ?)',
                (problem_hash, symptom, root_cause, solution)
            )
        self.conn.commit()
    
    def search_similar(self, query: str, limit=3):
        """搜索相似的历史故障"""
        # 简单关键词匹配（生产环境可用真正的向量检索）
        keywords = query.lower().split()
        results = self.conn.execute('''
            SELECT symptom, root_cause, solution, usage_count 
            FROM knowledge 
            ORDER BY usage_count DESC 
            LIMIT ?
        ''', (limit,)).fetchall()
        return results
```

在 LLM 的系统提示中加入历史案例：

```python
knowledge_base = LogKnowledgeBase()
similar_cases = knowledge_base.search_similar(user_log_content)

if similar_cases:
    cases_text = "\n\n".join([
        f"历史案例 - 症状: {r[0]}, 原因: {r[1]}, 解决方案: {r[2]}"
        for r in similar_cases
    ])
    SYSTEM_PROMPT += f"\n\n以下是相似的历史故障案例，可以参考：\n{cases_text}"
```

### 7.2 定时日志巡检

除了实时分析，还可以设置每日定时巡检：

```bash
# crontab -e
# 每天早上 9 点分析过去 24 小时的日志摘要
0 9 * * * cd ~/ai-log-analyzer && python3 daily_report.py
```

```python
# daily_report.py - 每日日志巡检报告
from datetime import datetime, timedelta
import subprocess

def generate_daily_report():
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    
    # 收集昨天的所有错误日志
    result = subprocess.run(
        ['journalctl', '--since', yesterday, '--until', f'{yesterday}T23:59:59',
         '-p', 'err', '--no-pager'],
        capture_output=True, text=True
    )
    
    logs = result.stdout
    if not logs.strip():
        print("昨天没有错误日志，一切正常 ✅")
        return
    
    # 发送给 LLM 生成摘要
    # ... (复用 ai_service.py 中的 LLM 调用逻辑)
    
    # 发送每日报告
    send_telegram_alert(f"📊 昨日日志巡检报告 ({yesterday})", analysis)

generate_daily_report()
```

### 7.3 资源占用优化

| 组件 | 内存占用 | 说明 |
|------|---------|------|
| Vector | 10-20 MB | 日志收集管道 |
| Python 服务 | 30-50 MB | 过滤 + 聚合 + HTTP 服务 |
| LLM API 调用 | ~0 (云端) | 按需调用，无常驻内存 |
| Ollama 本地模型 | 4-6 GB | 7B 模型，可选 |

**推荐配置**：2GB 内存 VPS 可使用云端免费 API + Vector + Python 服务；8GB 内存 VPS 可部署本地 Ollama 模型，实现完全离线分析。

---

## 8. 实际效果演示

假设你的 Nginx 和 Docker 产生了以下日志：

```
2026-06-16 02:15:33 [nginx] error: upstream timed out (110: Connection timed out)
2026-06-16 02:15:34 [nginx] error: 1 upstream server temporarily disabled
2026-06-16 02:15:35 [docker] myapp: Connection refused to postgres:5432
2026-06-16 02:15:36 [docker] myapp: Retrying connection (attempt 2/3)
2026-06-16 02:15:38 [kernel] Out of memory: Killed process 1234 (java)
```

LLM 可能会返回：

```json
{
  "summary": "PostgreSQL 连接超时导致上游服务连锁故障，最终触发 OOM 杀死 Java 进程",
  "severity": "critical",
  "root_cause": "PostgreSQL 数据库不可达（可能因连接数耗尽或数据库本身崩溃），导致 myapp 重试堆积，内存持续增长直至触发内核 OOM killer",
  "affected_services": ["nginx", "myapp", "postgres", "java"],
  "recommendations": [
    "检查 PostgreSQL 连接数: SELECT count(*) FROM pg_stat_activity;",
    "检查数据库是否正常运行: systemctl status postgresql",
    "为 myapp 添加连接池超时和熔断机制",
    "检查 Java 进程的内存限制，考虑增加 VPS 内存或调整 JVM 参数",
    "配置 PostgreSQL 慢查询日志，排查是否有锁表或全表扫描"
  ],
  "keywords": ["postgres-connection", "oom-killer", "retry-storm", "upstream-timeout"]
}
```

然后通过 Telegram 收到一条结构化的告警消息，一目了然。

---

## 总结

将 AI 引入 VPS 日志分析，本质上是**用机器的语义理解能力弥补人类的注意力瓶颈**。这套系统的核心价值：

- 🎯 **精准过滤**：先用规则引擎筛掉 95% 的无关日志，只对真正重要的异常调用 LLM
- 🧠 **智能诊断**：LLM 能理解错误之间的因果关系，给出比正则匹配更有价值的分析
- 💰 **成本可控**：每天实际调用 LLM 的次数可能只有几次到几十次，API 费用极低
- 🔧 **易于扩展**：可以接入更多数据源（Metrics、Traces），构建完整的可观测性体系

**下一步行动建议：**
1. 先在测试 VPS 上跑通 Vector → Filter → AI 的链路
2. 逐步接入更多服务日志
3. 积累历史案例，构建自己的故障知识库
4. 最终实现从"被动救火"到"主动预警"的转变

日志不会说谎，但人类会疲劳。让 AI 替你保持清醒。