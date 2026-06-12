---
title: "用 N8N 搭建 AI 自动化工作流：从邮件分类到智能报表"
description: "手把手教你在 VPS 上部署 N8N 工作流引擎，结合 Ollama 本地 LLM 实现智能邮件分类、文档摘要、数据报表自动生成等 AI 自动化场景——无需第三方云服务，成本低至 4 欧元/月。"
date: 2026-06-12T10:00:00+08:00
slug: "n8n-ai-automation-workflows"
image: /images/posts/n8n-ai-automation-workflows/featured.png
tags: ["N8N", "自动化", "AI Agent", "Ollama", "自托管", "工作流", "邮件分类", "Docker"]
categories: ["自动化"]
aliases: [/zh/post/n8n-ai-automation-workflows/]
---

## 为什么选择自托管 AI 自动化？

你每天是否都在重复这些操作：

- 打开邮箱，手动分类垃圾邮件、重要邮件、促销邮件
- 从多个数据源（Google Sheets、API、数据库）拉取数据，手动整理成报表
- 阅读长篇文章，提取关键信息
- 把不同平台的通知汇总到 Telegram 或 Slack

这些重复性工作，如果用 AI 自动化来做，每周能省下 5-10 小时。

而 **N8N** 是地球上最适合自托管的工作流引擎。它不像 Zapier 那样按调用次数收费，也不像 Make 那样限制执行时长。N8N 是开源的，部署在你的 VPS 上，**无限执行、无限节点、完全免费**——你只需要付 VPS 的钱。

> **成本对比：** Zapier 基础版 $20/月（500 次调用），N8N 自托管 €3.99/月（无限次）。

---

## N8N 是什么？

N8N 是一个**公平代码（fair-code）**开源的工作流自动化工具。它让你通过拖拽节点的方式，把不同的服务连接起来：

```
 Gmail ──→ 邮件分类(AI) ──→ Notion 自动入库
  │
  ▼
Google Sheets ──→ 数据处理 ──→ Telegram 通知
  │
  ▼
PostgreSQL ──→ 数据聚合 ──→ AI 生成周报 ──→ 邮件发送
```

每个「节点」代表一个动作：读取邮件、调用 API、执行 SQL 查询、发送消息。节点之间用线连接，形成一条自动化流水线。

**N8N 的核心优势：**

| 特性 | N8N | Zapier | Make |
|------|------|--------|------|
| 自托管 | ✅ | ❌ | ❌ |
| 数据隐私 | 完全本地 | 经过第三方 | 经过第三方 |
| 执行次数 | 无限 | 有限制 | 有限制 |
| 价格 | 免费 | $20+/月 | $9+/月 |
| AI 节点 | 内置 Ollama 支持 | 需要额外连接 | 有限支持 |
| 自定义代码 | 支持 Python/JS | 支持 JS | 支持 JS |

---

## 环境要求

| 资源 | 最低配置 | 推荐配置 |
|------|---------|---------|
| VPS | 1 核 / 2GB RAM | 2 核 / 4GB RAM |
| 存储 | 10GB SSD | 20GB+ SSD |
| Docker | ✅ 需要 | Docker Compose |
| 系统 | Ubuntu 22.04/24.04 | Debian 12 |

> **没有 GPU 也可以跑。** 邮件分类和报表生成不需要 GPU——只有运行 LLM 时才用得上 GPU，CPU 推理完全够用。

---

## 第一步：部署 N8N

### 使用 Docker Compose 安装

创建项目目录：

```bash
mkdir -p ~/n8n && cd ~/n8n
```

创建 `docker-compose.yml`：

```yaml
services:
  n8n:
    image: docker.n8n.io/n8nio/n8n
    container_name: n8n
    restart: unless-stopped
    ports:
      - "5678:5678"
    environment:
      - N8N_ENCRYPTION_KEY=${N8N_ENCRYPTION_KEY}
      - N8N_HOST=n8n.yourdomain.com
      - N8N_PORT=5678
      - N8N_PROTOCOL=https
      - NODE_ENV=production
      - WEBHOOK_URL=https://n8n.yourdomain.com/
      - GENERIC_TIMEZONE=Asia/Shanghai
    volumes:
      - n8n_data:/home/node/.n8n
    networks:
      - n8n

volumes:
  n8n_data:

networks:
  n8n:
    driver: bridge
```

生成加密密钥：

```bash
echo "N8N_ENCRYPTION_KEY=$(openssl rand -hex 32)" >> .env
```

启动服务：

```bash
docker compose up -d
```

访问 `http://你的IP:5678`，设置管理员账号。

### 反向代理配置（推荐 Nginx Proxy Manager）

```nginx
location / {
    proxy_pass http://127.0.0.1:5678;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Host $host;
    proxy_set_header X-Forwarded-Port $server_port;
}
```

---

## 第二步：部署 Ollama 本地 LLM

N8N 内置了 LLM 节点，可以调用任何兼容 OpenAI API 的服务。Ollama 是最简单的本地方案：

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

下载轻量模型：

```bash
# 邮件分类 + 文档摘要够用
ollama pull qwen2.5:7b

# 更轻量（适合 2GB RAM 机器）
ollama pull qwen2.5:1.5b
```

Ollama 默认监听 `http://localhost:11434`，N8N 的 LLM 节点直接填这个地址即可，无需额外配置。

---

## 实战一：AI 邮件智能分类

### 场景描述

你每天收到 100+ 封邮件，手动分类：
- **重要邮件**（客户询盘、账单通知）→ 标记星标，同步到 Notion
- **促销邮件** → 直接归档
- **垃圾邮件** → 标记删除

### 工作流设计

```
┌─────────┐    ┌──────────────┐    ┌─────────────────┐
│ Gmail   │───→│ AI 分类节点   │───→│ 条件分发节点     │
│ (每5分钟) │    │ (Ollama +    │    │ → Notion / 归档   │
└─────────┘    │  qwen2.5)     │    │ → 删除/Telegram  │
               └──────────────┘    └─────────────────┘
```

### 步骤

1. **添加触发器**：在 N8N 中添加 Gmail 节点，选择「Watch for New Emails」，设置每 5 分钟检查一次
2. **添加 AI 分类节点**：使用 N8N 的「AI Agent」节点
   - LLM 选择 Ollama（`http://localhost:11434`）
   - 模型：`qwen2.5:7b`
   - 提示词模板：

```
你是一个邮件分类助手。请分析以下邮件内容，将其分类为：
- important：客户询盘、账单、合同、重要通知
- promotional：促销、折扣、营销邮件
- spam：垃圾邮件、诈骗邮件
- newsletter：新闻通讯、订阅周报

只返回 JSON 格式：{"category": "important|promotional|spam|newsletter", "confidence": 0.95}

邮件标题：{{ $json["subject"] }}
邮件发件人：{{ $json["from"] }}
邮件内容摘要：{{ $json["textPreview"] }}
```

3. **添加条件分发节点**：
   - `important` → 调用 Notion API 创建页面，同步到知识库
   - `promotional` → 调用 Gmail 节点，移动到「Promotions」标签
   - `spam` → 调用 Gmail 节点，标记为垃圾邮件
   - 同时发送 Telegram 通知：「收到重要邮件：{{ subject }}」

### 效果

部署后，你每天打开邮箱时，重要邮件已经置顶、同步到 Notion 待办列表，其余邮件按类别归档。Telegram 还会给你推送通知。

---

## 实战二：AI 自动报表生成

### 场景描述

每周一你需要从多个数据源汇总数据，生成周报：

- Google Sheets 的销售数据
- PostgreSQL 数据库的订单数据
- 第三方 API 的服务器状态

手动整理需要 2-3 小时。

### 工作流设计

```
┌──────────┐    ┌──────────┐    ┌──────────┐
│ Google   │    │ Post-    │    │ API     │
│ Sheets   │    │ SQL DB   │    │ 查询    │
└────┬─────┘    └────┬─────┘    └────┬─────┘
     │               │               │
     └───────┬───────┴───────┬───────┘
             ▼               ▼
      ┌─────────────────────────┐
      │     数据合并节点         │
      │  (Merge + 数据清洗)      │
      └───────────┬─────────────┘
                  ▼
      ┌─────────────────────────┐
      │   AI 生成周报            │
      │  (Ollama 分析趋势       │
      │   提取关键洞察)          │
      └───────────┬─────────────┘
                  ▼
      ┌─────────────────────────┐
      │   发送方式：             │
      │   • Gmail 发送 PDF      │
      │   • Telegram 推送摘要   │
      │   • 存储到 Google Drive │
      └─────────────────────────┘
```

### 步骤

1. **添加 Google Sheets 节点**：
   - 操作：「Read Sheet」
   - 选择工作表和范围
   - 设置每周一上午 9 点触发

2. **添加 PostgreSQL 节点**：
   - 操作：「Execute Query」
   - SQL 示例：
   ```sql
   SELECT DATE(created_at) as day, COUNT(*) as orders, 
          SUM(amount) as revenue
   FROM orders
   WHERE created_at >= NOW() - INTERVAL '7 days'
   GROUP BY DATE(created_at)
   ORDER BY day;
   ```

3. **数据合并节点**：
   - 使用 N8N 的「Merge」节点，选择「Append」模式
   - 添加「Code」节点（JavaScript）进行数据清洗和格式统一

4. **AI 生成周报**：
   - 使用「AI Agent」节点
   - 提示词模板：

```
你是一个商业分析师。以下是过去 7 天的业务数据：

{{ $json }}

请生成一份周报摘要，包括：
1. 本周总销售额和订单数，与上周对比的增减百分比
2. 增长最快的品类/服务
3. 需要关注的异常数据
4. 下周建议

使用简洁的 Markdown 格式，不超过 500 字。
```

5. **发送通知**：
   - Gmail 节点：生成邮件正文并发送
   - Telegram 节点：推送精简版摘要
   - Google Drive 节点：存储完整 PDF 报表

---

## 实战三：跨平台 AI 内容摘要

### 场景描述

你在多个平台关注行业动态：

- Hacker News / Reddit 的技术趋势
- Twitter / X 上的行业 KOL 动态
- 自己的 RSS 订阅

每天浏览这些平台需要 1-2 小时。

### 工作流

```
┌──────────┐  ┌──────────┐  ┌──────────┐
│ RSS      │  │ Hacker   │  │ Twitter  │
│ 订阅     │  │ News API │  │ API     │
└────┬─────┘  └────┬─────┘  └────┬─────┘
     │             │             │
     └──────┬──────┴──────┬──────┘
            ▼             ▼
     ┌─────────────────────────┐
     │   AI 摘要 & 去重         │
     │  (Ollama 提取要点        │
     │   跨源去重)              │
     └───────────┬─────────────┘
                 ▼
     ┌─────────────────────────┐
     │   发送到：               │
     │   • Telegram 早报       │
     │   • Obsidian 知识库     │
     │   • 邮件日报            │
     └─────────────────────────┘
```

### 关键实现

1. **RSS 订阅**：N8N 内置 Feedparser 节点，支持 RSS/Atom
2. **Hacker News**：使用 N8N 的 HTTP Request 节点调用 `https://hacker-news.firebaseio.com/v0/`
3. **AI 摘要节点**：
   ```
   你是一个技术资讯编辑。请从以下文章标题和摘要中提取关键信息：
   
   {{ $json }}
   
   请：
   1. 去重（相似标题合并）
   2. 按主题分类（AI、基础设施、安全、开发工具）
   3. 每条输出 50 字以内摘要
   
   返回 JSON 数组格式。
   ```

4. **存储到 Obsidian**：通过 Obsidian REST API 创建笔记，自动带上日期标签和主题标签

---

## 进阶：创建你的自定义 N8N 节点

如果你需要 N8N 内置节点不支持的功能，可以写自定义代码：

### Python 数据处理节点

```python
import pandas as pd
import json

# 接收输入数据
data = $input.all()

# 转换为 DataFrame
df = pd.DataFrame([item.json for item in data])

# 数据清洗
df = df.dropna()
df['revenue'] = df['revenue'].astype(float)

# 聚合分析
summary = {
    'total_revenue': df['revenue'].sum(),
    'avg_order': df['revenue'].mean(),
    'top_category': df['category'].value_counts().idxmax()
}

# 输出
return [{
    'json': {
        'summary': json.dumps(summary, ensure_ascii=False),
        'record_count': len(df)
    }
}]
```

### 自定义 Telegram 通知模板

```javascript
// N8N 代码节点 (JavaScript)
const messages = $input.all();
const formatted = messages.map(msg => {
  return `📌 ${msg.json.title}\n${msg.json.summary}\n🔗 ${msg.json.url}`;
}).join('\n\n---\n\n');

return [{
  json: {
    chat_id: process.env.TELEGRAM_CHAT_ID,
    text: `📊 N8N AI 日报 (${new Date().toISOString().split('T')[0]})\n\n${formatted}`,
    parse_mode: 'HTML'
  }
}];
```

---

## 定时执行：让自动化真正自动化

N8N 支持 Cron 触发器，设置好时间后无需任何手动操作：

### 常用调度方案

| 任务 | 频率 | Cron 表达式 |
|------|------|-------------|
| 邮件分类 | 每 5 分钟 | `*/5 * * * *` |
| 日报摘要 | 每天 9:00 | `0 9 * * *` |
| 周报生成 | 每周一 9:00 | `0 9 * * 1` |
| 数据备份 | 每天 2:00 | `0 2 * * *` |
| 服务器监控检查 | 每 15 分钟 | `*/15 * * * *` |

---

## 安全最佳实践

1. **设置强密码**：N8N 面板的加密密钥妥善保管
2. **HTTPS 强制**：使用 Let's Encrypt 证书
3. **API 密钥管理**：使用环境变量存储敏感信息
4. **网络隔离**：N8N 容器只对外暴露 Webhook 端口，数据库端口不暴露
5. **定期备份**：

```bash
# 备份 N8N 数据
docker exec n8n tar czf /tmp/n8n-backup.tar.gz /home/node/.n8n
rsync /tmp/n8n-backup.tar.gz backup-server:/backups/
```

---

## 总成本计算

| 项目 | 费用 |
|------|------|
| VPS（Hetzner CX22 / 2核4G） | €3.99/月 |
| 域名 | €1/月（分摊） |
| SSL 证书 | 免费（Let's Encrypt） |
| Ollama 运行成本 | 免费（本地推理） |
| **总计** | **~€5/月** |

对比 Zapier $20/月 + ChatGPT Plus $20/月 + Notion $10/月 = **$50/月**，自托管方案节省了 90% 以上的费用。

---

## 下一步

N8N 的能力远不止这些。你还可以：

- 🤖 **AI 客服机器人**：结合 Ollama + 知识库，用自然语言回答客户问题
- 📊 **数据分析管道**：从多个数据源拉取数据，自动生成可视化报表
- 🔒 **安全监控**：实时监控服务器日志，AI 检测异常并自动响应
- 📝 **内容发布流水线**：自动将草稿发布到多个平台（博客、Twitter、LinkedIn）

> **核心思路：N8N 是你的「自动化大脑」，Ollama 是你的「AI 大脑」，VPS 是你的「身体」。三者结合，你拥有一个 24/7 在线、完全自有、成本极低的数字员工。**

开始搭建你的第一个工作流吧！从最简单的「新邮件通知到 Telegram」开始，逐步扩展。
