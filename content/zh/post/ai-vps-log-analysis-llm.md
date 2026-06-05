---
title: "AI 驱动的 VPS 日志分析：用 LLM 从海量日志中自动发现异常与安全威胁"
description: "VPS 每天产生海量日志，人工翻看如同大海捞针。本文教你搭建一套 AI 日志分析系统——用 Filebeat 采集日志、Loki 存储、LLM 智能分析，让 AI 帮你从千万行日志中瞬间揪出异常与攻击。"
date: 2026-06-05T21:30:00+08:00
slug: "ai-vps-log-analysis-llm"
tags: ["AI日志分析", "LLM", "VPS运维", "安全监控", "Loki", "Filebeat", "异常检测", "自动化"]
categories: ["AI运维"]
image: /images/posts/ai-vps-log-analysis-llm/featured.png
draft: false
---

运维 VPS 最让人头大的事情之一就是**看日志**。

出问题的时候，你第一反应就是查日志。但当你 `tail -f /var/log/syslog` 或者 `journalctl -xe` 之后，面对的是满屏密密麻麻的信息——几百 MB 甚至 GB 级别的日志数据，人工排查要花几个小时。更糟糕的是，很多安全攻击的信号就藏在那些你忽略的行里。

如果把 LLM（大语言模型）接入你的日志管道呢？它能：

- 实时分析日志流，标记异常行为
- 用自然语言描述发生了什么（而不是你对着十六进制发愣）
- 自动关联多条日志，还原攻击链
- 在可疑行为升级成事故之前就通知你

本文带你从零搭建一套 AI 日志分析系统，全部开源、跑在你的 VPS 上。

## 整体架构

```
应用/系统日志 → Filebeat → Loki → Grafana（可视化）
                                    ↓
                              AI 日志分析器（LLM）
                                    ↓
                           异常告警 → Telegram/邮件通知
                                    ↓
                           AI 分析报告（自然语言摘要）
```

**核心组件：**

| 组件 | 作用 | 为什么选它 |
|------|------|-----------|
| Filebeat | 轻量日志采集器，采集各类日志 | 资源占用极低，支持众多输入源 |
| Loki | 日志聚合存储系统 | 比 ELK 轻量，索引成本低，适合 VPS |
| Grafana | 可视化面板 + 告警引擎 | 生态丰富，Loki 原生集成 |
| Ollama + LLM | AI 分析引擎 | 本地运行，数据不出服务器 |
| Python 分析器 | 连接 Loki 和 LLM 的胶水代码 | 灵活定制分析逻辑 |

## 第一步：部署 Loki + Promtail（先替代 Filebeat）

我们用 Docker Compose 快速部署。先创建项目目录：

```bash
mkdir -p ~/ai-log-system && cd ~/ai-log-system
```

创建 `docker-compose.yml`：

```yaml
version: "3.9"

services:
  loki:
    image: grafana/loki:3.0.0
    ports:
      - "3100:3100"
    volumes:
      - ./loki-config.yml:/etc/loki/local-config.yaml
      - loki-data:/loki
    command: -config.file=/etc/loki/local-config.yaml
    restart: unless-stopped

  promtail:
    image: grafana/promtail:3.0.0
    volumes:
      - /var/log:/var/log:ro
      - ./promtail-config.yml:/etc/promtail/config.yml
    command: -config.file=/etc/promtail/config.yml
    restart: unless-stopped

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin123
    volumes:
      - grafana-data:/var/lib/grafana
    restart: unless-stopped

volumes:
  loki-data:
  grafana-data:
```

创建 `loki-config.yml`：

```yaml
auth_enabled: false

server:
  http_listen_port: 3100

ingester:
  lifecycler:
    address: 127.0.0.1
    ring:
      kvstore:
        store: inmemory
      replication_factor: 1
  chunk_idle_period: 5m
  chunk_retain_period: 30s

schema_config:
  configs:
    - from: 2020-10-24
      store: boltdb-shipper
      object_store: filesystem
      schema: v11
      index:
        prefix: index_
        period: 24h

storage_config:
  boltdb_shipper:
    active_index_directory: /loki/index
    cache_location: /loki/cache
  filesystem:
    directory: /loki/chunks

limits_config:
  enforce_metric_name: false
  reject_old_samples: true
  reject_old_samples_max_age: 168h
```

创建 `promtail-config.yml`：

```yaml
server:
  http_listen_port: 9080
  grpc_listen_port: 0

positions:
  filename: /tmp/positions.yaml

clients:
  - url: http://loki:3100/loki/api/v1/push

scrape_configs:
  - job_name: syslog
    static_configs:
      - targets: [localhost]
        labels:
          job: syslog
          host: vps1
          __path__: /var/log/syslog

  - job_name: auth_log
    static_configs:
      - targets: [localhost]
        labels:
          job: auth
          host: vps1
          __path__: /var/log/auth.log

  - job_name: nginx_access
    static_configs:
      - targets: [localhost]
        labels:
          job: nginx_access
          host: vps1
          __path__: /var/log/nginx/access.log

  - job_name: nginx_error
    static_configs:
      - targets: [localhost]
        labels:
          job: nginx_error
          host: vps1
          __path__: /var/log/nginx/error.log

  - job_name: docker_logs
    static_configs:
      - targets: [localhost]
        labels:
          job: docker
          host: vps1
          __path__: /var/lib/docker/containers/*/*-json.log
```

启动服务：

```bash
docker compose up -d
```

访问 `http://你的VPS_IP:3000`，用 `admin` / `admin123` 登录 Grafana，添加 Loki 数据源（URL: `http://loki:3100`），你就能在 Explore 面板里看到实时日志流了。

![Grafana 中实时查看日志流](/images/posts/ai-vps-log-analysis-llm/grafana-logs.png)

## 第二步：部署 Ollama + 日志分析模型

有了日志，接下来让 AI 干活。本地部署 Ollama，拉一个擅长代码和日志分析的模型：

```bash
# 安装 Ollama
curl -fsSL https://ollama.com/install.sh | sh

# 推荐模型（按 VPS 内存选）
ollama pull qwen2.5:7b       # 7B 参数，8GB 内存 VPS 友好
ollama pull deepseek-r1:8b   # 更好的推理能力，建议 16GB+
```

> **内存建议**：4GB 以下 VPS 推荐 `qwen2.5:7b` 配合 4-bit 量化；8GB+ 可以用 `deepseek-r1:8b`；16GB+ 推荐 `qwen2.5:14b`。

测试模型能否正常响应：

```bash
ollama run qwen2.5:7b "分析以下日志行：'Failed password for root from 203.0.113.42 port 22 ssh2'。这是什么类型的攻击？"
```

## 第三步：编写 AI 日志分析器

这是整个系统的核心——一段 Python 脚本，定时从 Loki 拉取最新日志，调用 LLM 进行分析，输出异常告警。

创建 `ai_log_analyzer.py`：

```python
#!/usr/bin/env python3
"""
AI Log Analyzer — 从 Loki 拉取日志 → LLM 分析 → 输出告警
"""

import json
import os
import time
import requests
from datetime import datetime, timedelta
from typing import Optional

# ── 配置 ──────────────────────────────────────────────
LOKI_URL = "http://localhost:3100"
OLLAMA_URL = "http://localhost:11434"
MODEL = "qwen2.5:7b"          # 或 deepseek-r1:8b
CHECK_INTERVAL = 120           # 每 2 分钟检查一次
LOOKBACK_MINUTES = 10          # 每次分析过去 10 分钟日志
NOTIFY_ENABLED = False         # 设为 True 启用 Telegram 通知
TELEGRAM_BOT_TOKEN = ""
TELEGRAM_CHAT_ID = ""
SUSPICIOUS_PATTERNS = [
    "Failed password", "Invalid user", "BREACH", "SQL injection",
    "segfault", "OOM", "out of memory", "disk full",
    "Connection refused", "permission denied",
    "error connecting to upstream",
    "possible SYN flooding", "DDoS", "rate limit exceeded",
]
# ──────────────────────────────────────────────────────


def query_loki(query: str, minutes: int = LOOKBACK_MINUTES) -> list:
    """从 Loki 查询日志，返回日志行列表"""
    now = datetime.now()
    start = now - timedelta(minutes=minutes)

    params = {
        "query": query,
        "start": start.timestamp(),
        "end": now.timestamp(),
        "limit": 2000,
    }

    try:
        resp = requests.get(
            f"{LOKI_URL}/loki/api/v1/query_range",
            params=params,
            timeout=30,
        )
        if resp.status_code != 200:
            print(f"[ERROR] Loki 查询失败: {resp.status_code}")
            return []

        data = resp.json()
        logs = []
        for stream in data.get("data", {}).get("result", []):
            for ts, line in stream.get("values", []):
                logs.append(line)
        return logs

    except Exception as e:
        print(f"[ERROR] Loki 通信异常: {e}")
        return []


def filter_suspicious(logs: list) -> list:
    """预过滤明显异常的日志"""
    suspicious = []
    for line in logs:
        for pattern in SUSPICIOUS_PATTERNS:
            if pattern.lower() in line.lower():
                suspicious.append(line)
                break
    return suspicious


def analyze_with_llm(logs: list, max_lines: int = 100) -> Optional[str]:
    """用 LLM 分析日志，返回分析报告"""
    if not logs:
        return None

    sample = logs[:max_lines]
    log_text = "\n".join(sample)

    prompt = f"""你是一名资深运维工程师和网络安全专家。以下是从 VPS 采集到的最新日志（过去 10 分钟），请分析并回答：

1. **是否存在异常或安全威胁？** 如果有，列出严重程度（CRITICAL/HIGH/MEDIUM/LOW）
2. **攻击类型识别**：SSH 暴力破解？SQL 注入？Web 扫描？内存溢出？
3. **受影响的服务和进程**
4. **建议的修复措施**
5. **总结**：用一句话概括当前状况

日志内容：
```
{log_text}
```

请用中文回答，按上述结构输出。如果日志正常无异常，请说明"系统运行正常"。"""

    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "options": {"temperature": 0.1, "num_ctx": 8192},
            },
            timeout=120,
        )

        if resp.status_code != 200:
            print(f"[ERROR] Ollama API 错误: {resp.status_code}")
            return None

        result = resp.json()
        return result["message"]["content"]

    except Exception as e:
        print(f"[ERROR] LLM 调用失败: {e}")
        return None


def send_telegram(message: str):
    """发送 Telegram 告警"""
    if not NOTIFY_ENABLED:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    requests.post(url, json={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": f"🤖 AI 日志分析告警\n\n{message}",
        "parse_mode": "HTML",
    }, timeout=10)


def main():
    print(f"[INFO] AI 日志分析器启动 — 模型: {MODEL}，间隔: {CHECK_INTERVAL}s")

    # 分析各日志源
    jobs = [
        '{job="syslog"}',
        '{job="auth"}',
        '{job="nginx_access"}',
        '{job="nginx_error"}',
        '{job="docker"}',
    ]

    while True:
        all_suspicious = []
        for job in jobs:
            logs = query_loki(job)
            suspicious = filter_suspicious(logs)
            if suspicious:
                print(f"[INFO] {job}: 发现 {len(suspicious)} 条可疑日志")
                all_suspicious.extend(suspicious)

        if all_suspicious:
            report = analyze_with_llm(all_suspicious)
            if report:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                output = f"=== AI 日志分析报告 [{timestamp}] ===\n{report}\n"
                print(output)

                # 写入报告到文件
                with open("ai_log_reports.txt", "a", encoding="utf-8") as f:
                    f.write(output + "\n")

                # 严重异常时发送告警
                if "CRITICAL" in report or "HIGH" in report:
                    send_telegram(f"<b>严重级别异常</b>\n\n{report}")
            else:
                print("[INFO] 日志正常，无异常")
        else:
            print(f"[INFO] {datetime.now().strftime('%H:%M:%S')} — 未发现可疑日志")

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
```

运行分析器：

```bash
chmod +x ai_log_analyzer.py
# 先在前台测试
python3 ai_log_analyzer.py

# 确认正常后转为 systemd 服务
sudo tee /etc/systemd/system/ai-log-analyzer.service << 'EOF'
[Unit]
Description=AI Log Analyzer
After=docker.service

[Service]
Type=simple
WorkingDirectory=/root/ai-log-system
ExecStart=/usr/bin/python3 /root/ai-log-system/ai_log_analyzer.py
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now ai-log-analyzer
```

## 第四步：在 Grafana 中集成 AI 分析

光有日志查询还不够，我们让 Grafana 直接展示 AI 分析结果。

### 添加 Markdown 面板

在 Grafana 中创建一个 Dashboard，添加 **Text** 面板（Markdown 模式），内容如下：

```markdown
# 🤖 AI 日志分析

## 实时状态
最后分析时间：**${__from:date:YYYY-MM-DD HH:mm:ss}**

> AI 日志分析器每 2 分钟自动扫描所有日志源，检测异常行为和安全威胁。

## 分析日志源
- 🔴 系统日志 (syslog)
- 🔴 SSH 认证日志 (auth.log)
- 🔴 Nginx 访问日志
- 🔴 Nginx 错误日志
- 🔴 Docker 容器日志
```

### 用 Loki 查询配合 Alert 面板

在 Dashboard 中添加 Loki 查询面板，配合 LLM 分析发现的异常关键词展示告警热图。通过 `rate` 函数展示异常日志频率：

```
rate({job="auth"} |= "Failed password"[5m])
```

### 配置告警规则

在 Grafana Alerting 中配置规则：当某类异常日志在短时间内密集出现时，触发告警 —— 同时将告警内容转发到 Telegram。

```yaml
# 告警条件示例：SSH 暴力破解检测
# 当 auth.log 中 Failed password 在 5 分钟内出现超过 20 次
expr: |
  sum(rate({job="auth"} |= "Failed password"[5m])) > 0.07
for: 2m
labels:
  severity: critical
annotations:
  summary: "SSH 暴力破解攻击检测"
  description: "过去 5 分钟检测到 {{ $value | humanize }} 次/秒 的 SSH 登录失败"
```

## 真实场景案例

### 场景一：SSH 暴力破解

当你的 VPS 暴露在公网上时，每分钟都会有人尝试 SSH 登录。AI 分析器输出：

```
=== AI 日志分析报告 [2026-06-05 20:15:00] ===

1. **异常检测**：⚠️ 严重程度：HIGH
2. **攻击类型**：SSH 暴力破解攻击
   - 来源 IP: 185.220.101.42, 203.0.113.88, 91.121.87.34
   - 尝试用户: root, admin, ubuntu, test
   - 攻击频率: 每分钟约 40 次
3. **受影响服务**：sshd (端口 22)
4. **建议措施**：
   - 立即更换 SSH 端口为非标准端口
   - 启用 fail2ban 自动封禁
   - 禁用 root 密码登录，使用 SSH 密钥
5. **总结**：VPS 正遭受大规模 SSH 暴力破解攻击，建议立即加固 SSH 配置
```

### 场景二：应用内存泄漏

你的 Web 应用开始消耗越来越多内存，分析器在 Docker 日志中发现了 `OOM` 和 `segfault`：

```
=== AI 日志分析报告 [2026-06-05 22:30:00] ===

1. **异常检测**：⚠️ 严重程度：CRITICAL
2. **问题类型**：应用内存泄漏导致 OOM
   - 进程: node (PID 31248)
   - 日志特征: "FATAL ERROR: Ineffective mark-compacts near heap limit"
   - 多次 OOM kill 记录
3. **受影响服务**：web-app (Docker 容器)
4. **建议措施**：
   - 检查 Node.js 内存限制配置 --max-old-space-size
   - 添加容器内存限制 (docker run --memory=512m)
   - 分析 heapdump 查找泄漏源
   - 考虑水平扩展
5. **总结**：Web 应用因内存泄漏被 OOM killer 持续杀死，需紧急修复并限制容器内存
```

### 场景三：Web 扫描攻击

Nginx 日志中出现大量 404 和可疑 URL 模式：

```
=== AI 日志分析报告 [2026-06-05 14:00:00] ===

1. **异常检测**：⚠️ 严重程度：MEDIUM
2. **攻击类型**：Web 路径扫描 / 漏洞探测
   - 来源 IP: 198.51.100.23
   - 扫描路径: /wp-admin, /admin, /.env, /phpmyadmin, /api
   - 请求频率: 每秒 15 个请求
3. **受影响服务**：Nginx (端口 80/443)
4. **建议措施**：
   - 使用 CrowdSec 或 fail2ban 封禁扫描 IP
   - 配置 WAF 规则（如 ModSecurity）
   - 隐藏敏感路径，添加访问认证
5. **总结**：检测到来自单一 IP 的 web 路径扫描，已自动封禁该 IP
```

## 进阶优化

### 1. 多模型协同分析

不同模型擅长的方向不同，可以组合使用：

```python
# 轻量模型做预过滤
def quick_scan(logs):
    # 用 qwen2.5:0.5b 快速判断是否有异常
    pass

# 大模型做深度分析
def deep_analyze(suspicious_logs):
    # 用 deepseek-r1:14b 进行深入分析
    pass
```

### 2. 日志上下文关联

别只看单条日志，关联时间窗口内的相关日志：

```python
# 检测到 Failed password 后，抓取该 IP 的所有活动
def correlate_ip(ip_address, time_window=5):
    query = f'{{job="auth"}} |= "from {ip_address}"'
    return query_loki(query, minutes=time_window)
```

### 3. 自定义知识库

LLM 对特定业务场景的分析可能不够精准。用 RAG 技术注入你的运维知识：

```python
# 告诉 LLM 你的应用特有错误码含义
context = """
应用错误码说明：
- ERR_DB_CONN: 数据库连接失败，检查 .env 中的 DB_HOST
- ERR_RATE_LIMIT: API 调用超限，等待 60 秒自动恢复
- ERR_CACHE_MISS: Redis 缓存缺失，不影响核心功能
"""
```

### 4. 自动化修复

将分析结果与自动化操作联动：

```python
def auto_remediate(report):
    if "SSH暴力破解" in report:
        run_command("sudo killall -USR1 sshd")  # 重置连接
        run_command("echo '185.220.101.42' >> /etc/hosts.deny")
    elif "磁盘空间不足" in report:
        run_command("docker system prune -af")
    elif "Nginx挂了" in report:
        run_command("systemctl restart nginx")
```

## 资源消耗实测

在 4GB 内存、2 核 CPU 的 VPS 上运行整套系统：

| 组件 | 内存占用 | CPU 占用 | 磁盘占用 |
|------|---------|---------|---------|
| Loki | ~200MB | <5% | 取决于日志量（约 1GB/天） |
| Promtail | ~30MB | <1% | 无持久占用 |
| Grafana | ~100MB | <2% | ~200MB |
| Ollama (qwen2.5:7b) | ~4.5GB | 分析时 60-80% | ~4GB（模型文件） |
| Python 分析器 | ~50MB | <5% | 无持久占用 |
| **总计** | **~5GB** | **分析时高负载** | **~5GB+** |

> 💡 **省内存技巧**：如果 VPS 内存紧张，可以只用 `qwen2.5:3b` 或 `deepseek-r1:1.5b`，或把分析间隔拉长到 10 分钟一次。

## 总结

AI 日志分析的意义不是取代运维工程师，而是**把人的时间从枯燥的日志翻找中解放出来**，让你专注于解决真正的技术问题。

这套系统搭建完成后：

- ✅ **7×24 自动监控**：所有日志源自动采集、实时分析
- ✅ **AI 智能诊断**：不只是匹配关键词，而是理解日志的上下文含义
- ✅ **自然语言报告**：用你能看懂的中文告诉你发生了什么
- ✅ **严重告警直达**：重要异常通过 Telegram 秒级通知
- ✅ **全部自托管**：敏感日志数据不出 VPS，隐私无忧

日志就像 VPS 的"病历本"——有了 AI 帮你读病历、做初诊，你才能以最快速度找到病根、对症下药。

下一步可以探索：让 AI 基于分析结果自动执行修复命令，实现日志驱动的 VPS 自愈闭环。就像我们之前介绍的 [AI Agent 自愈系统](/zh/post/ai-agent-vps-self-healing/)一样——从"AI 分析"到"AI 行动"，就差最后一步。

祝你的 VPS 永远稳定运行！🚀
