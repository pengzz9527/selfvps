---
title: "LLM 驱动的 VPS 跨服务日志关联与智能故障分析"
subtitle: "LLM-Powered VPS Cross-Service Log Correlation & Intelligent Incident Analysis"
date: 2026-09-12
draft: false
tags: ["AI", "VPS", "LLM", "日志分析", "跨服务关联", "故障诊断", "可观测性", "AIOps"]
categories: ["AI + VPS"]
image: /images/posts/ai-vps-llm-cross-service-log-correlation/featured.png
description: "当 VPS 上运行的多个服务同时出现问题时，传统方法难以快速定位根因。本文介绍如何利用大语言模型（LLM）实现跨服务日志关联分析，自动识别故障链路，生成可操作的根因报告。"
---

## 引言

你的 VPS 上同时运行着 Nginx、MySQL、Redis、Docker 容器和多个自定义应用。某天用户反馈网站访问缓慢，你登录服务器后面对的是：

- Nginx 错误日志中大量 `502 Bad Gateway`
- MySQL 慢查询日志显示连接池已满
- Redis 出现 `OOM command not allowed`
- Docker 容器日志里充斥着 `connection refused`
- 系统日志里还有 `Out of memory: Killed process`

传统排查方式是逐条日志手动关联——先查 Nginx，再查 MySQL，再查 Redis，最后看系统日志。**但问题在于：这些日志分散在不同的文件、不同的时间戳、不同的格式中，人工关联几乎不可能高效完成。**

**大语言模型（LLM）的出现彻底改变了这一局面。** LLM 具备强大的语义理解能力，可以同时阅读所有相关日志，理解它们之间的因果关系，并生成结构化的根因分析报告。

本文将带你构建一套 **LLM 驱动的 VPS 跨服务日志关联分析系统**，实现从"人工大海捞针"到"AI 自动定位"的跨越。

---

## 一、为什么跨服务日志关联如此困难？

### 1.1 传统方法的三大瓶颈

| 瓶颈 | 说明 | 影响 |
|------|------|------|
| **日志孤岛** | 不同服务的日志格式、存储位置、采集方式各不相同 | 需要手动切换多个工具查看 |
| **时间同步难题** | 分布式系统中各服务的时间戳可能存在偏差 | 难以准确重建事件时间线 |
| **上下文缺失** | 单条日志无法反映完整因果链 | 容易误判根因 |

### 1.2 典型故障场景分析

让我们看一个典型的多服务故障场景：

```
用户请求 → Nginx → PHP-FPM → MySQL
                      ↘ Redis (缓存)
```

当用户报告"页面加载慢"时，可能的原因有：

1. **MySQL 慢查询**：某条 SQL 没有索引，导致全表扫描
2. **Redis 内存溢出**：缓存失效，大量请求直接打到 MySQL
3. **PHP-FPM 进程耗尽**：并发连接数超过配置上限
4. **Nginx 上游超时**：后端服务响应超时，返回 504
5. **系统 OOM**：内存不足，内核杀死了关键进程

传统排查需要：
- 查看 Nginx access/error log → 确认 502/504 错误
- 查看 MySQL slow query log → 找慢查询
- 查看 Redis info → 检查内存使用
- 查看 PHP-FPM status → 检查进程数
- 查看 dmesg/journalctl → 检查 OOM killer

**这个过程通常需要 30 分钟到数小时，而且高度依赖运维人员的经验。**

---

## 二、系统架构设计

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                      LLM 跨服务日志关联分析系统                        │
├───────────────┬───────────────┬───────────────┬─────────────────────┤
│   日志采集层   │   预处理层     │   LLM 分析层   │    输出层            │
├───────────────┼───────────────┼───────────────┼─────────────────────┤
│ • Promtail    │ • 时间对齐     │ • 日志聚合     │ • 根因报告           │
│ • Filebeat    │ • 格式标准化   │ • 关联分析     │ • 修复建议           │
│ • Docker log  │ • 上下文提取   │ • 因果推理     │ • 自动告警           │
│   driver      │ • 去重压缩     │ • 模式识别     │ • 知识沉淀           │
└───────┬───────┴───────┬───────┴───────┬───────┴──────────┬──────────┘
        │               │               │                 │
        └───────────────┴───────────────┴─────────────────┘
                              │
                              ▼
                    ┌─────────────────────┐
                    │     目标 VPS         │
                    │  Nginx + MySQL +    │
                    │  Redis + App +      │
                    │  System Logs        │
                    └─────────────────────┘
```

### 2.2 核心组件说明

**1. 日志采集层**

采集层负责从 VPS 的各个服务收集日志：

- **Promtail**：采集系统日志（/var/log/*）和应用日志
- **Docker log driver**：采集容器日志
- **MySQL slow log**：通过 Prometheus exporter 导出
- **Redis INFO**：通过 exporter 导出关键指标

**2. 预处理层**

预处理层对原始日志进行标准化处理：

- **时间对齐**：将所有日志统一到同一时区，处理时钟漂移
- **格式标准化**：将不同格式的日志转换为统一的 JSON 结构
- **上下文提取**：从日志中提取关键信息（错误码、请求 ID、用户 ID 等）
- **去重压缩**：去除重复日志，压缩相似日志

**3. LLM 分析层**

分析层是系统的核心，利用 LLM 的能力进行智能分析：

- **日志聚合**：按时间窗口和服务关系聚合相关日志
- **关联分析**：识别不同服务日志之间的因果关系
- **因果推理**：基于日志模式和领域知识推断根因
- **模式识别**：识别已知故障模式和新出现的异常模式

**4. 输出层**

输出层将分析结果以可读的形式呈现：

- **根因报告**：用自然语言描述故障根因和影响范围
- **修复建议**：提供可操作的修复步骤
- **自动告警**：通过 Webhook 推送告警到钉钉/Slack/Telegram
- **知识沉淀**：将分析结果存储到知识库，供后续参考

---

## 三、实现细节

### 3.1 日志采集配置

#### 3.1.1 Promtail 配置

```yaml
# promtail-config.yml
server:
  http_listen_port: 9080
  grpc_listen_port: 0

positions:
  filename: /tmp/positions.yaml

clients:
  - url: http://loki:3100/loki/api/v1/push

scrape_configs:
  # 系统日志
  - job_name: system
    static_configs:
      - targets:
          - localhost
        labels:
          job: varlogs
          __path__: /var/log/*.log
          service: system

  # Nginx 日志
  - job_name: nginx
    static_configs:
      - targets:
          - localhost
        labels:
          job: nginx
          __path__: /var/log/nginx/*.log
          service: nginx

  # 应用日志
  - job_name: application
    static_configs:
      - targets:
          - localhost
        labels:
          job: application
          __path__: /app/logs/*.log
          service: application
```

#### 3.1.2 Docker 日志采集

```yaml
# docker-compose.yml - Loki + Promtail
services:
  loki:
    image: grafana/loki:3.0.0
    ports:
      - "3100:3100"
    volumes:
      - loki-data:/loki
    command: -config.file=/etc/loki/local-config.yaml

  promtail:
    image: grafana/promtail:3.0.0
    volumes:
      - /var/log:/var/log
      - /run/log:/run/log
      - ./promtail-config.yml:/etc/promtail/config.yml
    command: -config.file=/etc/promtail/config.yml

  # 采集 Docker 容器日志
  dockerd-logs:
    image: grafana/promtail:3.0.0
    volumes:
      - /var/lib/docker/containers:/var/lib/docker/containers:ro
      - /var/run/docker.sock:/var/run/docker.sock
      - ./promtail-docker.yml:/etc/promtail/config.yml
    command: -config.file=/etc/promtail/config.yml
```

### 3.2 LLM 分析管道

#### 3.2.1 日志聚合与上下文构建

```python
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any

class LogAggregator:
    """日志聚合器：将相关日志按时间窗口和服务关系聚合"""
    
    def __init__(self, window_minutes=10):
        self.window = timedelta(minutes=window_minutes)
    
    def aggregate(self, logs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """按时间窗口聚合日志"""
        if not logs:
            return []
        
        # 按时间排序
        sorted_logs = sorted(logs, key=lambda x: x.get('timestamp', ''))
        
        # 按时间窗口分组
        groups = []
        current_group = []
        group_start = None
        
        for log in sorted_logs:
            ts = datetime.fromisoformat(log.get('timestamp', '').replace('Z', '+00:00'))
            
            if group_start is None:
                group_start = ts
                current_group.append(log)
            elif ts - group_start <= self.window:
                current_group.append(log)
            else:
                if current_group:
                    groups.append(current_group)
                current_group = [log]
                group_start = ts
        
        if current_group:
            groups.append(current_group)
        
        return groups
```

#### 3.2.2 LLM 根因分析提示词

```python
ROOT_CAUSE_ANALYSIS_PROMPT = """
你是一个专业的 SRE 工程师，负责分析 VPS 上的跨服务日志关联故障。

## 任务
分析以下日志片段，找出故障的根因，并生成结构化的根因报告。

## 输入日志
{logs}

## 服务依赖关系
{dependencies}

## 分析要求
1. **时间线重建**：按时间顺序梳理关键事件
2. **因果链分析**：识别"触发因素 → 级联影响 → 最终症状"的完整链条
3. **根因定位**：找出最根本的原因（不是表象）
4. **影响评估**：评估故障对业务的影响范围和程度
5. **修复建议**：提供具体的、可操作的修复步骤

## 输出格式
请以 JSON 格式输出：
{{
  "root_cause": "根因的简洁描述",
  "confidence": 0.0-1.0,
  "timeline": [
    {{"time": "时间戳", "event": "事件描述", "service": "服务名"}}
  ],
  "causal_chain": [
    {{"step": 1, "cause": "原因", "effect": "结果"}}
  ],
  "impact": {{
    "services_affected": ["受影响服务"],
    "severity": "critical/high/medium/low",
    "description": "影响描述"
  }},
  "recommendations": [
    {{"action": "修复动作", "priority": "immediate/short-term/long-term", "details": "详细说明"}}
  ],
  "similar_incidents": ["类似历史故障的标识"]
}}
"""
```

#### 3.2.3 跨服务关联分析

```python
import ollama
from typing import List, Dict, Any

class CrossServiceAnalyzer:
    """跨服务日志关联分析器"""
    
    def __init__(self, model="qwen2.5:7b"):
        self.model = model
        self.service_deps = {
            "nginx": ["php-fpm", "node"],
            "php-fpm": ["mysql", "redis"],
            "node": ["mysql", "redis", "postgresql"],
            "api-gateway": ["auth-service", "user-service", "order-service"],
        }
    
    def analyze(self, log_groups: List[List[Dict]]) -> Dict[str, Any]:
        """执行跨服务关联分析"""
        
        # 构建上下文
        all_logs = []
        for group in log_groups:
            for log in group:
                all_logs.append({
                    "service": log.get("service", "unknown"),
                    "timestamp": log.get("timestamp", ""),
                    "level": log.get("level", "INFO"),
                    "message": log.get("message", ""),
                    "error_code": log.get("error_code", ""),
                })
        
        # 构建依赖关系文本
        deps_text = json.dumps(self.service_deps, ensure_ascii=False, indent=2)
        
        # 调用 LLM 进行分析
        prompt = ROOT_CAUSE_ANALYSIS_PROMPT.format(
            logs=json.dumps(all_logs[-100:], ensure_ascii=False, indent=2),
            dependencies=deps_text
        )
        
        response = ollama.chat(
            model=self.model,
            messages=[{"role": "user", "content": prompt}]
        )
        
        # 解析结果
        try:
            result = json.loads(response["message"]["content"])
        except json.JSONDecodeError:
            # 如果 JSON 解析失败，尝试提取 JSON 片段
            content = response["message"]["content"]
            start = content.find("{")
            end = content.rfind("}")
            if start != -1 and end != -1:
                result = json.loads(content[start:end+1])
            else:
                result = {"root_cause": content, "confidence": 0.5}
        
        return result
```

### 3.3 完整部署方案

#### 3.3.1 docker-compose.yml

```yaml
version: '3.8'

services:
  # Loki - 日志存储
  loki:
    image: grafana/loki:3.0.0
    ports:
      - "3100:3100"
    volumes:
      - loki-data:/loki
      - ./loki-config.yml:/etc/loki/local-config.yaml
    command: -config.file=/etc/loki/local-config.yaml
    restart: unless-stopped

  # Promtail - 日志采集
  promtail:
    image: grafana/promtail:3.0.0
    volumes:
      - /var/log:/var/log:ro
      - /run/log:/run/log:ro
      - ./promtail-config.yml:/etc/promtail/config.yml
    command: -config.file=/etc/promtail/config.yml
    restart: unless-stopped

  # LLM 分析服务
  llm-analyzer:
    build: ./llm-analyzer
    volumes:
      - ./config:/app/config
      - ./knowledge-base:/app/knowledge-base
    environment:
      - OLLAMA_HOST=http://ollama:11434
      - LOKI_URL=http://loki:3100
      - ALERT_WEBHOOK=https://hooks.slack.com/your-webhook
    depends_on:
      - loki
      - ollama
    restart: unless-stopped

  # Ollama - 本地 LLM
  ollama:
    image: ollama/ollama:latest
    ports:
      - "11434:11434"
    volumes:
      - ollama-data:/root/.ollama
    restart: unless-stopped

  # Grafana - 可视化
  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    volumes:
      - grafana-data:/var/lib/grafana
      - ./grafana/dashboards:/etc/grafana/provisioning/dashboards
    environment:
      - GF_AUTH_ANONYMOUS_ENABLED=false
      - GF_SECURITY_ADMIN_USER=admin
      - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_PASSWORD}
    depends_on:
      - loki
    restart: unless-stopped

volumes:
  loki-data:
  ollama-data:
  grafana-data:
```

#### 3.3.2 Loki 配置

```yaml
# loki-config.yml
auth_enabled: false

server:
  http_listen_port: 3100
  grpc_listen_port: 9095

common:
  instance_addr: 127.0.0.1
  path_prefix: /tmp/loki
  storage:
    filesystem:
      chunks_directory: /tmp/loki/chunks
      rules_directory: /tmp/loki/rules
  replication_factor: 1
  ring:
    kvstore:
      store: inmemory

query_range:
  results_cache:
    cache:
      embedded_cache:
        enabled: true
        max_size_mb: 100

schema_config:
  configs:
    - from: 2024-01-01
      store: tsdb
      object_store: filesystem
      schema: v13
      index:
        prefix: index_
        period: 24h

ruler:
  alertmanager_url: http://localhost:9093
```

### 3.4 使用示例

#### 3.4.1 手动触发分析

```bash
# 查询最近 30 分钟的日志
curl -G 'http://localhost:3100/loki/api/v1/query_range' \
  --data-urlencode 'query={service=~"nginx|mysql|redis|php-fpm"}' \
  --data-urlencode 'start=now-30m' \
  --data-urlencode 'end=now' \
  --data-urlencode 'limit=1000'

# 触发 LLM 分析
curl -X POST 'http://localhost:8080/analyze' \
  -H 'Content-Type: application/json' \
  -d '{
    "log_query": "{service=~\"nginx|mysql|redis|php-fpm\"}",
    "time_range": "30m",
    "context": "用户报告页面加载缓慢"
  }'
```

#### 3.4.2 LLM 分析结果示例

```json
{
  "root_cause": "MySQL 慢查询导致连接池耗尽，级联引发 Redis 缓存失效和 Nginx 502 错误",
  "confidence": 0.92,
  "timeline": [
    {
      "time": "2026-09-12T10:15:23Z",
      "event": "MySQL 开始出现慢查询（>2s）",
      "service": "mysql"
    },
    {
      "time": "2026-09-12T10:17:45Z",
      "event": "MySQL 连接数达到上限（max_connections=151）",
      "service": "mysql"
    },
    {
      "time": "2026-09-12T10:18:02Z",
      "event": "PHP-FPM 开始等待 MySQL 连接，进程数达到 20/20",
      "service": "php-fpm"
    },
    {
      "time": "2026-09-12T10:18:30Z",
      "event": "Redis 缓存命中率降至 15%，大量请求直接打到 MySQL",
      "service": "redis"
    },
    {
      "time": "2026-09-12T10:19:15Z",
      "event": "Nginx 开始返回 502 Bad Gateway",
      "service": "nginx"
    }
  ],
  "causal_chain": [
    {"step": 1, "cause": "某条 SQL 查询缺少索引", "effect": "MySQL 慢查询增加"},
    {"step": 2, "cause": "慢查询占用连接池", "effect": "新请求无法获取数据库连接"},
    {"step": 3, "cause": "PHP-FPM 进程等待数据库连接", "effect": "进程池耗尽"},
    {"step": 4, "cause": "缓存失效导致更多数据库查询", "effect": "MySQL 压力进一步增大"},
    {"step": 5, "cause": "后端服务无响应", "effect": "Nginx 返回 502"}
  ],
  "impact": {
    "services_affected": ["mysql", "php-fpm", "redis", "nginx"],
    "severity": "high",
    "description": "网站完全无法访问，影响所有用户"
  },
  "recommendations": [
    {
      "action": "添加缺失的数据库索引",
      "priority": "immediate",
      "details": "在 orders.created_at 字段上添加索引：CREATE INDEX idx_orders_created ON orders(created_at)"
    },
    {
      "action": "优化慢查询 SQL",
      "priority": "immediate",
      "details": "检查 EXPLAIN 输出，优化查询语句，避免 SELECT *"
    },
    {
      "action": "调整 PHP-FPM 和 MySQL 连接池配置",
      "priority": "short-term",
      "details": "增加 max_connections，调整 php-fpm pm.max_children"
    },
    {
      "action": "配置 Redis 缓存预热策略",
      "priority": "long-term",
      "details": "避免缓存击穿，使用热key预加载"
    }
  ],
  "similar_incidents": ["INC-2026-0815-001", "INC-2026-0702-003"]
}
```

---

## 四、高级功能

### 4.1 知识沉淀与复用

系统会将每次分析结果存储到知识库中，供后续参考：

```python
class KnowledgeBase:
    """故障知识库：存储历史分析结果，支持相似故障匹配"""
    
    def __init__(self, db_path="knowledge.db"):
        self.db = sqlite3.connect(db_path)
        self._init_tables()
    
    def _init_tables(self):
        self.db.execute('''
            CREATE TABLE IF NOT EXISTS incidents (
                id INTEGER PRIMARY KEY,
                root_cause TEXT,
                timeline TEXT,
                causal_chain TEXT,
                recommendations TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        self.db.execute('''
            CREATE VIRTUAL TABLE IF NOT EXISTS incidents_fts 
            USING fts5(root_cause, content='incidents', content_rowid='id')
        ''')
    
    def store(self, analysis_result: Dict):
        """存储分析结果"""
        self.db.execute('''
            INSERT INTO incidents (root_cause, timeline, causal_chain, recommendations)
            VALUES (?, ?, ?, ?)
        ''', (
            analysis_result.get('root_cause', ''),
            json.dumps(analysis_result.get('timeline', [])),
            json.dumps(analysis_result.get('causal_chain', [])),
            json.dumps(analysis_result.get('recommendations', []))
        ))
        self.db.commit()
    
    def find_similar(self, root_cause: str, limit=3) -> List[Dict]:
        """查找相似历史故障"""
        cursor = self.db.execute('''
            SELECT id, root_cause, created_at
            FROM incidents_fts
            WHERE incidents_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        ''', (root_cause, limit))
        return [{'id': row[0], 'root_cause': row[1], 'date': row[2]} for row in cursor.fetchall()]
```

### 4.2 实时告警集成

```python
import requests

class AlertNotifier:
    """告警通知器"""
    
    def __init__(self, webhook_url):
        self.webhook_url = webhook_url
    
    def notify(self, analysis_result: Dict):
        """发送告警通知"""
        severity = analysis_result.get('impact', {}).get('severity', 'medium')
        root_cause = analysis_result.get('root_cause', 'Unknown')
        
        # 构建消息
        message = f"🚨 **VPS 故障告警**\n\n"
        message += f"**根因**: {root_cause}\n"
        message += f"**严重程度**: {severity}\n"
        message += f"**影响服务**: {', '.join(analysis_result.get('impact', {}).get('services_affected', []))}\n\n"
        
        # 添加修复建议
        recs = analysis_result.get('recommendations', [])
        if recs:
            message += "**修复建议**:\n"
            for i, rec in enumerate(recs[:3], 1):
                message += f"{i}. {rec.get('action', '')}\n"
        
        # 发送到 Webhook
        payload = {
            "text": message,
            "attachments": [{
                "color": "danger" if severity in ["critical", "high"] else "warning",
                "fields": [
                    {"title": "根因", "value": root_cause, "short": False},
                    {"title": "严重程度", "value": severity, "short": True},
                    {"title": "置信度", "value": f"{analysis_result.get('confidence', 0):.1%}", "short": True},
                ]
            }]
        }
        
        requests.post(self.webhook_url, json=payload, timeout=10)
```

### 4.3 定时分析任务

```python
import schedule
import time

class ScheduledAnalyzer:
    """定时分析任务"""
    
    def __init__(self, analyzer, notifier, knowledge_base):
        self.analyzer = analyzer
        self.notifier = notifier
        self.kb = knowledge_base
    
    def run_analysis(self):
        """执行分析任务"""
        # 查询最近 10 分钟的异常日志
        logs = self.fetch_anomaly_logs(minutes=10)
        
        if not logs:
            return
        
        # 执行 LLM 分析
        result = self.analyzer.analyze([logs])
        
        # 存储到知识库
        self.kb.store(result)
        
        # 发送告警（如果严重程度高）
        severity = result.get('impact', {}).get('severity', 'low')
        if severity in ['critical', 'high']:
            self.notifier.notify(result)
    
    def fetch_anomaly_logs(self, minutes=10) -> List[Dict]:
        """从 Loki 查询异常日志"""
        # 查询 ERROR 和 CRITICAL 级别的日志
        query = '{{level=~"ERROR|CRITICAL"}}'
        # ... 调用 Loki API
        pass
```

---

## 五、性能优化建议

### 5.1 日志采样策略

对于高流量 VPS，全量日志分析可能成本过高。建议采用智能采样：

```python
class SmartSampler:
    """智能日志采样器"""
    
    def should_sample(self, log: Dict) -> bool:
        """决定是否采样此日志"""
        # 始终保留错误日志
        if log.get('level') in ['ERROR', 'CRITICAL']:
            return True
        
        # 关键字日志始终保留
        keywords = ['timeout', 'connection refused', 'out of memory', 'killed']
        message = log.get('message', '').lower()
        if any(kw in message for kw in keywords):
            return True
        
        # 正常日志按 1% 采样
        import random
        return random.random() < 0.01
```

### 5.2 增量分析

避免重复分析相同日志，使用 checkpoint 机制：

```python
class IncrementalAnalyzer:
    """增量分析器"""
    
    def __init__(self, checkpoint_file="checkpoint.json"):
        self.checkpoint = self._load_checkpoint()
    
    def _load_checkpoint(self):
        try:
            with open(self.checkpoint_file, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return {"last_analysis": 0}
    
    def get_new_logs(self, since_timestamp):
        """获取指定时间之后的新日志"""
        # 调用 Loki API 获取新日志
        pass
    
    def analyze_incremental(self):
        """增量分析"""
        since = self.checkpoint.get('last_analysis', 0)
        new_logs = self.get_new_logs(since)
        
        if new_logs:
            result = self.analyzer.analyze([new_logs])
            self.checkpoint['last_analysis'] = int(time.time() * 1000)
            self._save_checkpoint()
            return result
        return None
```

---

## 六、总结与展望

### 6.1 核心价值

通过构建 LLM 驱动的跨服务日志关联分析系统，你可以获得：

1. **快速根因定位**：从小时级缩短到分钟级
2. **降低误判率**：LLM 理解上下文，减少误报
3. **知识沉淀**：历史故障自动积累，新手也能快速排查
4. **自动化响应**：严重故障自动告警，无需人工值守

### 6.2 适用场景

- **单 VPS 多服务架构**：Nginx + PHP/Node + MySQL + Redis
- **Docker 容器化部署**：多个容器之间的日志关联
- **微服务架构**：跨服务的调用链分析
- **混合云环境**：本地 VPS + 云服务的日志统一分析

### 6.3 下一步改进方向

- **多 VPS 协同分析**：跨多台服务器的日志关联
- **实时流式分析**：基于 Kafka/Flink 的实时日志处理
- **自适应阈值**：LLM 自动学习正常模式，动态调整告警阈值
- **自动修复执行**：与 Ansible/Terraform 集成，自动执行修复

---

## 参考资源

- [Loki 官方文档](https://grafana.com/oss/loki/)
- [Promtail 配置指南](https://grafana.com/docs/loki/latest/clients/promtail/)
- [Ollama 本地 LLM](https://ollama.com/)
- [OpenTelemetry 分布式追踪](https://opentelemetry.io/)
