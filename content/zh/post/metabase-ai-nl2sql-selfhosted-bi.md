---
title: "自建 AI 数据分析与 BI 平台：Metabase + LLM 自然语言查询"
description: "手把手教你用 Metabase 搭建免费 BI 看板，结合 LLM 实现自然语言查询（NL2SQL），让非技术人员也能用中文提问获取数据洞察"
date: 2026-07-14T10:00:00+08:00
slug: "metabase-ai-nl2sql-selfhosted-bi"
tags: ["Metabase", "BI", "LLM", "NL2SQL", "数据分析", "自托管", "VPS", "自然语言查询"]
categories: ["AI + 数据分析"]
aliases: [/zh/post/metabase-ai-nl2sql-selfhosted-bi/]
image: /images/posts/metabase-ai-nl2sql-selfhosted-bi/featured.png
draft: false
---

## 引言

在数据驱动的时代，**让正确的人看到正确的数据**比数据本身更重要。但大多数团队面临一个尴尬的现实：业务人员需要数据洞察，却不会写 SQL；技术人员懂 SQL，却被无尽的"帮我查个数据"请求淹没。

**Metabase** 是一个开源的 BI 工具，提供直观的可视化查询构建器和仪表板。配合 **LLM（大语言模型）**，它可以实现 NL2SQL —— 用自然语言提问，自动生成 SQL 查询。这套组合拳让非技术人员也能像和同事聊天一样获取数据分析结果。

本文将带你在一台 VPS 上搭建完整的 **AI 驱动 BI 平台**，包含 Metabase、PostgreSQL 数据库、Ollama 本地 LLM 以及 NL2SQL 桥接层。

---

## 一、架构概览

```
┌─────────────────────────────────────────────────────┐
│                   用户浏览器                          │
│  ┌──────────────┐  ┌──────────────────────────┐     │
│  │ Metabase UI  │  │  NL2SQL 自然语言查询接口   │     │
│  │ (可视化看板)  │  │ (LLM 生成 SQL + 执行)     │     │
│  └──────┬───────┘  └──────────┬───────────────┘     │
│         │                     │                      │
│         └─────────┬───────────┘                      │
│                   ▼                                  │
│  ┌─────────────────────────────────────────┐         │
│  │           Ollama (本地 LLM)              │         │
│  │     llama3 / qwen2.5 / mistral          │         │
│  └─────────────────────────────────────────┘         │
│                   ▲                                  │
│                   │ 生成 SQL                         │
│  ┌─────────────────────────────────────────┐         │
│  │       NL2SQL Bridge (FastAPI)            │         │
│  │   接收自然语言 → 调用 LLM → 返回结果      │         │
│  └─────────────────────────────────────────┘         │
│                   ▲                                  │
│                   │ 执行查询                          │
│  ┌─────────────────────────────────────────┐         │
│  │       PostgreSQL (业务数据库)             │         │
│  │   订单表 │ 用户表 │ 产品表 │ 日志表       │         │
│  └─────────────────────────────────────────┘         │
└─────────────────────────────────────────────────────┘
```

**核心组件：**
- **Metabase** — BI 可视化、仪表板、定时报告
- **PostgreSQL** — 数据存储与查询引擎
- **Ollama** — 本地运行的 LLM，无需 API Key
- **NL2SQL Bridge** — FastAPI 编写的中间层，将自然语言转为 SQL 并执行

---

## 二、环境准备

### 2.1 系统要求

| 组件 | 最低配置 | 推荐配置 |
|------|----------|----------|
| CPU | 2 核 | 4 核+ |
| 内存 | 4 GB | 8 GB+ |
| 磁盘 | 20 GB | 50 GB+ SSD |
| 网络 | 100 Mbps | 500 Mbps+ |

### 2.2 安装 Docker & Docker Compose

```bash
# 安装 Docker
curl -fsSL https://get.docker.com | sh
sudo systemctl enable --now docker

# 安装 Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
docker compose version
```

### 2.3 创建项目目录

```bash
mkdir -p ~/metabase-ai && cd ~/metabase-ai
```

---

## 三、部署 PostgreSQL 数据库

### 3.1 创建示例业务数据

首先创建一个 `init.sql` 文件，包含示例电商数据：

```sql
-- 创建用户表
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    country VARCHAR(50),
    is_premium BOOLEAN DEFAULT FALSE
);

-- 创建产品表
CREATE TABLE IF NOT EXISTS products (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    category VARCHAR(100),
    price DECIMAL(10, 2) NOT NULL,
    stock INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 创建订单表
CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    product_id INTEGER REFERENCES products(id),
    quantity INTEGER NOT NULL,
    total_amount DECIMAL(10, 2) NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT NOW()
);

-- 插入示例用户数据
INSERT INTO users (username, email, country, is_premium) VALUES
('张三', 'zhangsan@example.com', 'CN', TRUE),
('李四', 'lisi@example.com', 'CN', FALSE),
('王五', 'wangwu@example.com', 'US', TRUE),
('赵六', 'zhaoliu@example.com', 'JP', FALSE),
('钱七', 'qianqi@example.com', 'KR', TRUE),
('孙八', 'sunba@example.com', 'CN', FALSE),
('周九', 'zhoujiu@example.com', 'DE', TRUE),
('吴十', 'wushi@example.com', 'FR', FALSE),
('郑十一', 'zheng11@example.com', 'CN', TRUE),
('陈十二', 'chen12@example.com', 'US', FALSE) ON CONFLICT DO NOTHING;

-- 插入示例产品数据
INSERT INTO products (name, category, price, stock) VALUES
('机械键盘', '电子产品', 299.00, 150),
('无线鼠标', '电子产品', 89.00, 300),
('显示器支架', '办公用品', 199.00, 80),
('USB-C 集线器', '电子产品', 149.00, 200),
('人体工学椅', '办公家具', 1299.00, 50),
('降噪耳机', '电子产品', 599.00, 120),
('桌面收纳盒', '办公用品', 49.00, 500),
('摄像头', '电子产品', 399.00, 90),
('笔记本支架', '办公用品', 79.00, 250),
('蓝牙音箱', '电子产品', 249.00, 180) ON CONFLICT DO NOTHING;

-- 插入示例订单数据
INSERT INTO orders (user_id, product_id, quantity, total_amount, status) VALUES
(1, 1, 1, 299.00, 'completed'),
(2, 2, 2, 178.00, 'completed'),
(3, 3, 1, 199.00, 'shipped'),
(1, 6, 1, 599.00, 'pending'),
(4, 5, 1, 1299.00, 'completed'),
(5, 4, 3, 447.00, 'shipped'),
(6, 7, 5, 245.00, 'completed'),
(7, 8, 1, 399.00, 'pending'),
(8, 9, 2, 158.00, 'completed'),
(9, 10, 1, 249.00, 'shipped'),
(2, 1, 1, 299.00, 'completed'),
(3, 6, 2, 1198.00, 'completed'),
(10, 2, 4, 356.00, 'pending'),
(5, 5, 1, 1299.00, 'shipped'),
(1, 9, 2, 158.00, 'completed') ON CONFLICT DO NOTHING;
```

### 3.2 启动 PostgreSQL

```yaml
# docker-compose.yml 片段
services:
  postgres:
    image: postgres:16-alpine
    container_name: mb-postgres
    environment:
      POSTGRES_DB: metabase_db
      POSTGRES_USER: mb_user
      POSTGRES_PASSWORD: mb_secure_pass_2026
    ports:
      - "5432:5432"
    volumes:
      - pg_data:/var/lib/postgresql/data
      - ./init.sql:/docker-entrypoint-initdb.d/init.sql
    restart: unless-stopped

volumes:
  pg_data:
```

```bash
# 启动数据库
docker compose up -d postgres

# 验证数据
docker exec -it mb-postgres psql -U mb_user -d metabase_db -c "SELECT count(*) FROM users;"
docker exec -it mb-postgres psql -U mb_user -d metabase_db -c "SELECT count(*) FROM orders;"
```

---

## 四、部署 Metabase

### 4.1 启动 Metabase

```yaml
  metabase:
    image: metabase/metabase:latest
    container_name: mb-metabase
    environment:
      MB_DB_TYPE: postgres
      MB_DB_DBNAME: metabase_db
      MB_DB_PORT: 5432
      MB_DB_USER: mb_user
      MB_DB_PASS: mb_secure_pass_2026
      MB_DB_HOST: postgres
      MB_SITE_URL: http://your-domain.com:3000
      MB_AUTO_SETUP: "true"
      MB_SECRET_KEY: super-secret-key-change-this
    ports:
      - "3000:3000"
    depends_on:
      - postgres
    restart: unless-stopped
```

### 4.2 首次配置

访问 `http://your-vps-ip:3000`，完成以下设置：

1. **创建管理员账户** — 设置用户名和密码
2. **连接数据库** — 选择 PostgreSQL，填入连接信息：
   - Host: `your-vps-ip`
   - Port: `5432`
   - Database: `metabase_db`
   - Username: `mb_user`
   - Password: `mb_secure_pass_2026`
3. **导入示例数据** — Metabase 会自动检测到 `users`、`products`、`orders` 表

### 4.3 创建第一个仪表板

在 Metabase 中创建以下关键视图：

- **销售概览** — 总收入、订单数、平均客单价
- **用户分析** — 新增用户趋势、活跃用户分布
- **产品排行** — 按销售额排名的 Top 10 产品
- **库存预警** — 库存低于阈值的商品列表

---

## 五、搭建 NL2SQL 桥接层

这是整个系统的核心创新点 —— 让用户可以用中文自然语言提问，系统自动转化为 SQL 并返回结果。

### 5.1 创建 NL2SQL Bridge 服务

```python
# nl2sql_bridge/app.py
"""NL2SQL Bridge — 自然语言到 SQL 查询的转换层"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import psycopg2
import json
import os
import httpx

app = FastAPI(title="NL2SQL Bridge", version="1.0.0")

# 数据库配置
DB_CONFIG = {
    "dbname": os.getenv("DB_NAME", "metabase_db"),
    "user": os.getenv("DB_USER", "mb_user"),
    "password": os.getenv("DB_PASS", "mb_secure_pass_2026"),
    "host": os.getenv("DB_HOST", "postgres"),
    "port": os.getenv("DB_PORT", "5432"),
}

# Ollama 配置
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
MODEL_NAME = os.getenv("LLM_MODEL", "llama3.2:3b")

class QueryRequest(BaseModel):
    question: str
    context: Optional[str] = None
    max_tokens: int = 1024
    temperature: float = 0.1

class QueryResponse(BaseModel):
    success: bool
    sql: Optional[str] = None
    results: Optional[List[Dict[str, Any]]] = None
    columns: Optional[List[str]] = None
    row_count: Optional[int] = None
    error: Optional[str] = None
    latency_ms: Optional[float] = None

def get_database_schema() -> str:
    """获取数据库表结构，用于 LLM 上下文"""
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute("""
        SELECT table_name, column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_schema = 'public'
        ORDER BY table_name, ordinal_position;
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    schema = "可用的数据表及字段：\n\n"
    current_table = ""
    for table, col, dtype, nullable in rows:
        if table != current_table:
            schema += f"\n📋 表: {table}\n"
            current_table = table
        nullable_str = "NULL" if nullable == "YES" else "NOT NULL"
        schema += f"  • {col} ({dtype}) [{nullable_str}]\n"
    return schema

def query_ollama(question: str, schema: str) -> str:
    """调用本地 LLM 生成 SQL"""
    prompt = f"""你是一个专业的 SQL 查询生成助手。根据以下数据库结构和用户问题，生成对应的 SQL 查询。

## 数据库结构
{schema}

## 用户问题
{question}

## 要求
1. 只生成 SQL 语句，不要包含其他解释
2. 使用标准的 PostgreSQL 语法
3. 如果问题是关于统计的，使用 COUNT/SUM/AVG 等聚合函数
4. 如果涉及日期，注意使用正确的日期格式
5. 如果问题不明确，生成一个合理的默认查询
6. SQL 必须以分号结尾
7. 只输出 SQL，不要输出 markdown 代码块标记

请生成 SQL："""

    response = httpx.post(
        f"{OLLAMA_URL}/api/generate",
        json={
            "model": MODEL_NAME,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,
                "max_tokens": 1024,
            }
        },
        timeout=30.0
    )
    response.raise_for_status()
    return response.json()["response"]

def execute_sql(sql: str) -> Dict[str, Any]:
    """执行 SQL 查询并返回结果"""
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    try:
        cur.execute(sql)
        if cur.description:
            columns = [desc[0] for desc in cur.description]
            rows = cur.fetchall()
            results = [dict(zip(columns, row)) for row in rows]
        else:
            columns = []
            results = []
            conn.commit()

        return {
            "success": True,
            "columns": columns,
            "results": results,
            "row_count": len(results),
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }
    finally:
        cur.close()
        conn.close()

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "nl2sql-bridge"}

@app.post("/query", response_model=QueryResponse)
async def query(request: QueryRequest):
    import time
    start = time.time()

    try:
        # 获取数据库结构
        schema = get_database_schema()

        # 调用 LLM 生成 SQL
        sql = query_ollama(request.question, schema)

        # 清理可能的 markdown 标记
        sql = sql.strip()
        if sql.startswith("```"):
            sql = sql.split("\n", 1)[1].rsplit("`", 1)[0] if "`" in sql.split("\n", 1)[1] else sql.split("\n", 1)[1]
        sql = sql.rstrip(";").strip()

        # 执行查询
        result = execute_sql(sql + ";")
        result["sql"] = sql

        latency = (time.time() - start) * 1000
        result["latency_ms"] = round(latency, 2)

        return QueryResponse(**result)

    except Exception as e:
        latency = (time.time() - start) * 1000
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}, 耗时: {round(latency, 2)}ms")

@app.get("/schema")
async def get_schema():
    """获取当前数据库结构（供调试）"""
    return {"schema": get_database_schema()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
```

### 5.2 NL2SQL Bridge 的 Dockerfile

```dockerfile
# nl2sql_bridge/Dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
```

```txt
# nl2sql_bridge/requirements.txt
fastapi==0.115.0
uvicorn==0.30.6
psycopg2-binary==2.9.9
httpx==0.27.2
pydantic==2.9.1
```

### 5.3 在 docker-compose.yml 中添加

```yaml
  nl2sql-bridge:
    build: ./nl2sql_bridge
    container_name: mb-nl2sql
    ports:
      - "8080:8080"
    environment:
      DB_NAME: metabase_db
      DB_USER: mb_user
      DB_PASS: mb_secure_pass_2026
      DB_HOST: postgres
      DB_PORT: "5432"
      OLLAMA_URL: http://ollama:11434
      LLM_MODEL: llama3.2:3b
    depends_on:
      - postgres
      - ollama
    restart: unless-stopped

  ollama:
    image: ollama/ollama:latest
    container_name: mb-ollama
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama
    restart: unless-stopped

volumes:
  pg_data:
  ollama_data:
```

### 5.4 拉取 LLM 模型

```bash
# 下载轻量级模型（适合 VPS）
docker exec -it mb-ollama ollama pull llama3.2:3b

# 或者使用更强大的模型（需要更多内存）
# docker exec -it mb-ollama ollama pull qwen2.5:7b
```

---

## 六、使用 NL2SQL 桥接

### 6.1 通过 API 查询

```bash
# 用中文提问
curl -X POST http://your-vps-ip:8080/query \
  -H "Content-Type: application/json" \
  -d '{
    "question": "上个月总销售额是多少？按产品类别分组"
  }'
```

**示例响应：**
```json
{
  "success": true,
  "sql": "SELECT p.category AS 类别, SUM(o.total_amount) AS 总销售额, COUNT(o.id) AS 订单数 FROM orders o JOIN products p ON o.product_id = p.id WHERE o.created_at >= CURRENT_DATE - INTERVAL '30 days' GROUP BY p.category ORDER BY 总销售额 DESC;",
  "results": [
    {"类别": "电子产品", "总销售额": 2345.00, "订单数": 8},
    {"类别": "办公用品", "总销售额": 651.00, "订单数": 4}
  ],
  "columns": ["类别", "总销售额", "订单数"],
  "row_count": 2,
  "latency_ms": 1247.5
}
```

### 6.2 常见查询示例

| 自然语言问题 | 生成的 SQL 类型 |
|-------------|----------------|
| "本月新增了多少用户？" | SELECT COUNT(*) WHERE created_at >= 本月 |
| "销售额最高的前5个产品是什么？" | SELECT ... ORDER BY total_amount DESC LIMIT 5 |
| "Premium 用户的平均订单金额是多少？" | SELECT AVG(total_amount) WHERE is_premium = true |
| "哪些产品库存低于100？" | SELECT * WHERE stock < 100 |
| "各国家的用户分布" | SELECT country, COUNT(*) GROUP BY country |
| "上周每天的订单量趋势" | SELECT DATE(created_at), COUNT(*) GROUP BY DATE |

### 6.3 集成到 Metabase

你可以在 Metabase 中使用 **JSON Endpoint** 卡片来展示 NL2SQL 的结果：

1. 新建一个问题 → 选择 "JSON API"
2. 输入 NL2SQL Bridge 的 API 地址
3. 将返回的数据可视化

或者，在 Metabase 仪表板中添加一个 **文本卡片**，嵌入简单的 curl 命令提示，让团队成员知道如何提问。

---

## 七、生产环境加固

### 7.1 添加 Nginx 反向代理

```nginx
server {
    listen 80;
    server_name bi.your-domain.com;

    # Metabase
    location / {
        proxy_pass http://localhost:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400s;
    }

    # NL2SQL API
    location /api/ {
        proxy_pass http://localhost:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### 7.2 配置 HTTPS

```bash
# 使用 Certbot 申请免费 SSL 证书
sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d bi.your-domain.com
```

### 7.3 安全防护

```yaml
# 在 docker-compose.yml 中添加
  metabase:
    environment:
      # 启用身份验证
      MB_SITE_URL: https://bi.your-domain.com
      # 限制并发会话
      MB_SESSION_DURATION_MINUTES: 480
      # 启用审计日志
      MB_AUDIT_ENABLED: "true"
```

### 7.4 定时备份

```bash
#!/bin/bash
# backup-metabase.sh
BACKUP_DIR="/opt/backups/metabase"
DATE=$(date +%Y%m%d_%H%M%S)

# 备份 PostgreSQL
docker exec mb-postgres pg_dump -U mb_user metabase_db > "$BACKUP_DIR/db_$DATE.sql"

# 备份 Metabase 应用数据
docker cp mb-metabase:/metabase.db "$BACKUP_DIR/metabase_$DATE.db"

# 保留最近 30 天的备份
find "$BACKUP_DIR" -name "*.sql" -mtime +30 -delete
find "$BACKUP_DIR" -name "*.db" -mtime +30 -delete

echo "Backup completed: $DATE"
```

添加到 crontab：
```bash
crontab -e
# 每天凌晨 3 点备份
0 3 * * * /opt/scripts/backup-metabase.sh >> /var/log/metabase-backup.log 2>&1
```

---

## 八、进阶优化

### 8.1 多模型切换

```python
# 根据查询复杂度自动选择模型
def select_model(question: str) -> str:
    """简单查询用轻量模型，复杂分析用强大模型"""
    keywords_complex = ["趋势", "对比", "预测", "关联", "回归"]
    if any(kw in question for kw in keywords_complex):
        return "qwen2.5:7b"
    return "llama3.2:3b"
```

### 8.2 查询缓存

```python
import hashlib
import redis

def cached_query(question: str, sql: str) -> Optional[List]:
    """缓存相同问题的查询结果"""
    cache_key = hashlib.md5(sql.encode()).hexdigest()
    redis_client = redis.Redis(host='cache', port=6379)
    
    cached = redis_client.get(f"nl2sql:{cache_key}")
    if cached:
        return json.loads(cached)
    
    # 执行查询并缓存（TTL 5 分钟）
    result = execute_sql(sql)
    redis_client.setex(f"nl2sql:{cache_key}", 300, json.dumps(result))
    return result
```

### 8.3 与 Metabase Embedding 集成

Metabase 支持嵌入式仪表板，可以将 BI 看板嵌入到你的内部系统中：

```html
<!-- 嵌入 Metabase 仪表板 -->
<iframe
  src="https://bi.your-domain.com/embed/dashboard/YOUR_DASHBOARD_ID"
  width="100%"
  height="600"
  frameborder="0">
</iframe>
```

---

## 九、成本分析

| 项目 | 独立购买 | 自建 VPS |
|------|----------|----------|
| BI 工具（Tableau/Power BI） | $25-50/用户/月 | **$0** |
| LLM API（OpenAI） | $5-20/月 | **$0**（本地 Ollama） |
| 数据库托管 | $15-50/月 | **包含在 VPS 中** |
| VPS 费用（4核/8GB） | — | **$20-40/月** |
| **总计** | **$45-120/月** | **$20-40/月** |

**年节省：$300-1000+**

---

## 十、总结

通过在本篇教程中搭建的系统，你拥有了：

1. ✅ **完整的 BI 平台** — Metabase 提供可视化的数据分析和仪表板
2. ✅ **AI 驱动的自然语言查询** — 用中文提问，自动获取数据洞察
3. ✅ **完全自托管** — 数据留在自己的 VPS 上，无需担心隐私泄露
4. ✅ **零许可费用** — 所有组件均为开源，无订阅费

这套方案特别适合：
- **中小团队** — 没有专职数据分析师，但需要数据驱动决策
- **个人创业者** — 控制成本的同时拥有专业级 BI 能力
- **隐私敏感组织** — 数据不出境，完全掌控

**下一步**：接入更多数据源（MySQL、MongoDB）、配置定时报告推送、添加更多 LLM 模型以支持更复杂的分析场景。

---

> 📌 **相关资源**
> - [Metabase 官方文档](https://www.metabase.com/docs/)
> - [Ollama 模型库](https://ollama.com/library)
> - [NL2SQL 研究论文](https://github.com/taoyds/nl2sql-survey)
> - [PostgreSQL 最佳实践](https://wiki.postgresql.org/wiki/Best_Practices)
