---
title: "Build an AI-Powered Self-Hosted BI Platform: Metabase + LLM Natural Language Queries"
description: "A step-by-step guide to deploying Metabase for business intelligence on your VPS, combined with a local LLM for NL2SQL — ask questions in plain English and get instant data insights"
date: 2026-07-14T10:00:00+08:00
slug: "metabase-ai-nl2sql-selfhosted-bi"
tags: ["Metabase", "BI", "LLM", "NL2SQL", "Data Analysis", "Self-Hosted", "VPS", "Natural Language Queries"]
categories: ["AI + Data Analytics"]
aliases: [/en/post/metabase-ai-nl2sql-selfhosted-bi/]
image: /images/posts/metabase-ai-nl2sql-selfhosted-bi/featured.png
draft: false
---

## Introduction

In the data-driven era, **getting the right data to the right people** matters more than the data itself. Yet most teams face an awkward reality: business users need data insights but can't write SQL; technical staff know SQL but are overwhelmed by endless "can you just pull this number" requests.

**Metabase** is an open-source BI tool offering intuitive visual query builders and dashboards. Paired with an **LLM (Large Language Model)**, it enables NL2SQL — generating SQL queries from natural language questions. This combination lets non-technical users interact with data as naturally as chatting with a colleague.

This guide walks you through deploying a complete **AI-powered BI platform** on a single VPS, including Metabase, PostgreSQL, Ollama local LLM, and an NL2SQL bridge layer.

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                  User Browser                        │
│  ┌──────────────┐  ┌──────────────────────────┐     │
│  │ Metabase UI  │  │  NL2SQL Natural Language  │     │
│  │ (Dashboards) │  │  Query Interface          │     │
│  └──────┬───────┘  └──────────┬───────────────┘     │
│         │                     │                      │
│         └─────────┬───────────┘                      │
│                   ▼                                  │
│  ┌─────────────────────────────────────────┐         │
│  │       Ollama (Local LLM)                │         │
│  │     llama3 / qwen2.5 / mistral          │         │
│  └─────────────────────────────────────────┘         │
│                   ▲                                  │
│                   │ Generate SQL                     │
│  ┌─────────────────────────────────────────┐         │
│  │       NL2SQL Bridge (FastAPI)            │         │
│  │   Receive question → Call LLM → Return  │         │
│  └─────────────────────────────────────────┘         │
│                   ▲                                  │
│                   │ Execute Query                    │
│  ┌─────────────────────────────────────────┐         │
│  │       PostgreSQL (Business Database)     │         │
│  │   Orders │ Users │ Products │ Logs       │         │
│  └─────────────────────────────────────────┘         │
└─────────────────────────────────────────────────────┘
```

**Core Components:**
- **Metabase** — BI visualization, dashboards, scheduled reports
- **PostgreSQL** — Data storage and query engine
- **Ollama** — Locally running LLM, no API keys required
- **NL2SQL Bridge** — FastAPI middleware that converts natural language to SQL and executes queries

---

## 2. Environment Setup

### 2.1 System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| CPU | 2 cores | 4+ cores |
| RAM | 4 GB | 8+ GB |
| Disk | 20 GB | 50+ GB SSD |
| Network | 100 Mbps | 500+ Mbps |

### 2.2 Install Docker & Docker Compose

```bash
# Install Docker
curl -fsSL https://get.docker.com | sh
sudo systemctl enable --now docker

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
docker compose version
```

### 2.3 Create Project Directory

```bash
mkdir -p ~/metabase-ai && cd ~/metabase-ai
```

---

## 3. Deploy PostgreSQL Database

### 3.1 Create Sample Business Data

Create an `init.sql` file with sample e-commerce data:

```sql
-- Create users table
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    country VARCHAR(50),
    is_premium BOOLEAN DEFAULT FALSE
);

-- Create products table
CREATE TABLE IF NOT EXISTS products (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    category VARCHAR(100),
    price DECIMAL(10, 2) NOT NULL,
    stock INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Create orders table
CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    product_id INTEGER REFERENCES products(id),
    quantity INTEGER NOT NULL,
    total_amount DECIMAL(10, 2) NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT NOW()
);

-- Insert sample user data
INSERT INTO users (username, email, country, is_premium) VALUES
('zhangsan', 'zhangsan@example.com', 'CN', TRUE),
('lisi', 'lisi@example.com', 'CN', FALSE),
('wangwu', 'wangwu@example.com', 'US', TRUE),
('zhaoliu', 'zhaoliu@example.com', 'JP', FALSE),
('qianqi', 'qianqi@example.com', 'KR', TRUE),
('sunba', 'sunba@example.com', 'CN', FALSE),
('zhoujiu', 'zhoujiu@example.com', 'DE', TRUE),
('wushi', 'wushi@example.com', 'FR', FALSE),
('zheng11', 'zheng11@example.com', 'CN', TRUE),
('chen12', 'chen12@example.com', 'US', FALSE) ON CONFLICT DO NOTHING;

-- Insert sample product data
INSERT INTO products (name, category, price, stock) VALUES
('Mechanical Keyboard', 'Electronics', 299.00, 150),
('Wireless Mouse', 'Electronics', 89.00, 300),
('Monitor Stand', 'Office Supplies', 199.00, 80),
('USB-C Hub', 'Electronics', 149.00, 200),
('Ergonomic Chair', 'Office Furniture', 1299.00, 50),
('Noise Cancelling Headphones', 'Electronics', 599.00, 120),
('Desktop Organizer', 'Office Supplies', 49.00, 500),
('Webcam', 'Electronics', 399.00, 90),
('Laptop Stand', 'Office Supplies', 79.00, 250),
('Bluetooth Speaker', 'Electronics', 249.00, 180) ON CONFLICT DO NOTHING;

-- Insert sample order data
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

### 3.2 Start PostgreSQL

```yaml
# docker-compose.yml snippet
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
# Start database
docker compose up -d postgres

# Verify data
docker exec -it mb-postgres psql -U mb_user -d metabase_db -c "SELECT count(*) FROM users;"
docker exec -it mb-postgres psql -U mb_user -d metabase_db -c "SELECT count(*) FROM orders;"
```

---

## 4. Deploy Metabase

### 4.1 Start Metabase

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

### 4.2 Initial Configuration

Visit `http://your-vps-ip:3000` and complete the following:

1. **Create admin account** — Set username and password
2. **Connect database** — Select PostgreSQL, enter connection details:
   - Host: `your-vps-ip`
   - Port: `5432`
   - Database: `metabase_db`
   - Username: `mb_user`
   - Password: `mb_secure_pass_2026`
3. **Import sample data** — Metabase auto-detects `users`, `products`, and `orders` tables

### 4.3 Create Your First Dashboard

Build these key views in Metabase:

- **Sales Overview** — Total revenue, order count, average order value
- **User Analysis** — New user trends, active user distribution
- **Product Rankings** — Top 10 products by sales volume
- **Inventory Alerts** — Items below stock threshold

---

## 5. Build the NL2SQL Bridge Layer

This is the core innovation of the system — letting users ask questions in plain language and automatically receive SQL-generated results.

### 5.1 Create NL2SQL Bridge Service

```python
# nl2sql_bridge/app.py
"""NL2SQL Bridge — Natural language to SQL query conversion layer"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import psycopg2
import json
import os
import httpx
import time
import hashlib

app = FastAPI(title="NL2SQL Bridge", version="1.0.0")

# Database configuration
DB_CONFIG = {
    "dbname": os.getenv("DB_NAME", "metabase_db"),
    "user": os.getenv("DB_USER", "mb_user"),
    "password": os.getenv("DB_PASS", "mb_secure_pass_2026"),
    "host": os.getenv("DB_HOST", "postgres"),
    "port": os.getenv("DB_PORT", "5432"),
}

# Ollama configuration
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
    """Get database table structure for LLM context"""
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

    schema = "Available tables and columns:\n\n"
    current_table = ""
    for table, col, dtype, nullable in rows:
        if table != current_table:
            schema += f"\n📋 Table: {table}\n"
            current_table = table
        nullable_str = "NULL" if nullable == "YES" else "NOT NULL"
        schema += f"  • {col} ({dtype}) [{nullable_str}]\n"
    return schema

def query_ollama(question: str, schema: str) -> str:
    """Call local LLM to generate SQL"""
    prompt = f"""You are a professional SQL query generation assistant. Based on the following database schema and user question, generate the corresponding SQL query.

## Database Schema
{schema}

## User Question
{question}

## Requirements
1. Output ONLY the SQL statement, no explanations
2. Use standard PostgreSQL syntax
3. For aggregations, use COUNT/SUM/AVG functions appropriately
4. For date-related queries, use correct date formats
5. If the question is ambiguous, generate a reasonable default query
6. SQL must end with a semicolon
7. Output only SQL, no markdown code block markers

Generate SQL:"""

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
    """Execute SQL query and return results"""
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
    start = time.time()

    try:
        # Get database schema
        schema = get_database_schema()

        # Call LLM to generate SQL
        sql = query_ollama(request.question, schema)

        # Clean possible markdown markers
        sql = sql.strip()
        if sql.startswith("```"):
            parts = sql.split("\n", 1)
            if len(parts) > 1:
                sql = parts[1].rstrip("`").strip()
        sql = sql.rstrip(";").strip()

        # Execute query
        result = execute_sql(sql + ";")
        result["sql"] = sql

        latency = (time.time() - start) * 1000
        result["latency_ms"] = round(latency, 2)

        return QueryResponse(**result)

    except Exception as e:
        latency = (time.time() - start) * 1000
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}, Latency: {round(latency, 2)}ms")

@app.get("/schema")
async def get_schema():
    """Get current database schema (for debugging)"""
    return {"schema": get_database_schema()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
```

### 5.2 NL2SQL Bridge Dockerfile

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

### 5.3 Add to docker-compose.yml

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

### 5.4 Pull the LLM Model

```bash
# Download lightweight model (suitable for VPS)
docker exec -it mb-ollama ollama pull llama3.2:3b

# Or use a more powerful model (requires more RAM)
# docker exec -it mb-ollama ollama pull qwen2.5:7b
```

---

## 6. Using the NL2SQL Bridge

### 6.1 Query via API

```bash
# Ask a question in English
curl -X POST http://your-vps-ip:8080/query \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What was the total sales last month? Group by product category"
  }'
```

**Example Response:**
```json
{
  "success": true,
  "sql": "SELECT p.category AS category, SUM(o.total_amount) AS total_sales, COUNT(o.id) AS order_count FROM orders o JOIN products p ON o.product_id = p.id WHERE o.created_at >= CURRENT_DATE - INTERVAL '30 days' GROUP BY p.category ORDER BY total_sales DESC;",
  "results": [
    {"category": "Electronics", "total_sales": 2345.00, "order_count": 8},
    {"category": "Office Supplies", "total_sales": 651.00, "order_count": 4}
  ],
  "columns": ["category", "total_sales", "order_count"],
  "row_count": 2,
  "latency_ms": 1247.5
}
```

### 6.2 Common Query Examples

| Natural Language Question | SQL Pattern |
|--------------------------|-------------|
| "How many new users this month?" | SELECT COUNT(*) WHERE created_at >= this_month |
| "Top 5 products by sales?" | SELECT ... ORDER BY total_amount DESC LIMIT 5 |
| "Average order value for premium users?" | SELECT AVG(total_amount) WHERE is_premium = true |
| "Which products have low stock?" | SELECT * WHERE stock < 100 |
| "User distribution by country" | SELECT country, COUNT(*) GROUP BY country |
| "Daily order trend last week" | SELECT DATE(created_at), COUNT(*) GROUP BY DATE |

### 6.3 Integration with Metabase

You can use Metabase's **JSON Endpoint** card to display NL2SQL results:

1. Create a new question → select "JSON API"
2. Enter the NL2SQL Bridge API address
3. Visualize the returned data

Alternatively, add a **Text card** to your Metabase dashboard with example curl commands, helping team members understand how to ask questions.

---

## 7. Production Hardening

### 7.1 Nginx Reverse Proxy

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

### 7.2 Configure HTTPS

```bash
# Request free SSL certificate with Certbot
sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d bi.your-domain.com
```

### 7.3 Security Configuration

```yaml
# Add to docker-compose.yml
  metabase:
    environment:
      # Enable authentication
      MB_SITE_URL: https://bi.your-domain.com
      # Limit concurrent sessions
      MB_SESSION_DURATION_MINUTES: 480
      # Enable audit logging
      MB_AUDIT_ENABLED: "true"
```

### 7.4 Scheduled Backups

```bash
#!/bin/bash
# backup-metabase.sh
BACKUP_DIR="/opt/backups/metabase"
DATE=$(date +%Y%m%d_%H%M%S)

# Backup PostgreSQL
docker exec mb-postgres pg_dump -U mb_user metabase_db > "$BACKUP_DIR/db_$DATE.sql"

# Backup Metabase application data
docker cp mb-metabase:/metabase.db "$BACKUP_DIR/metabase_$DATE.db"

# Keep last 30 days of backups
find "$BACKUP_DIR" -name "*.sql" -mtime +30 -delete
find "$BACKUP_DIR" -name "*.db" -mtime +30 -delete

echo "Backup completed: $DATE"
```

Add to crontab:
```bash
crontab -e
# Daily backup at 3 AM
0 3 * * * /opt/scripts/backup-metabase.sh >> /var/log/metabase-backup.log 2>&1
```

---

## 8. Advanced Optimizations

### 8.1 Multi-Model Switching

```python
# Automatically select model based on query complexity
def select_model(question: str) -> str:
    """Simple queries use lightweight models, complex analysis uses powerful models"""
    keywords_complex = ["trend", "compare", "predict", "correlation", "regression"]
    if any(kw in question.lower() for kw in keywords_complex):
        return "qwen2.5:7b"
    return "llama3.2:3b"
```

### 8.2 Query Caching

```python
import hashlib
import redis

def cached_query(question: str, sql: str) -> Optional[List]:
    """Cache results for identical questions"""
    cache_key = hashlib.md5(sql.encode()).hexdigest()
    redis_client = redis.Redis(host='cache', port=6379)
    
    cached = redis_client.get(f"nl2sql:{cache_key}")
    if cached:
        return json.loads(cached)
    
    # Execute query and cache (TTL 5 minutes)
    result = execute_sql(sql)
    redis_client.setex(f"nl2sql:{cache_key}", 300, json.dumps(result))
    return result
```

### 8.3 Metabase Embedding Integration

Metabase supports embedded dashboards that you can integrate into internal systems:

```html
<!-- Embed Metabase dashboard -->
<iframe
  src="https://bi.your-domain.com/embed/dashboard/YOUR_DASHBOARD_ID"
  width="100%"
  height="600"
  frameborder="0">
</iframe>
```

---

## 9. Cost Comparison

| Item | Standalone Purchase | Self-Hosted VPS |
|------|---------------------|-----------------|
| BI Tool (Tableau/Power BI) | $25-50/user/month | **$0** |
| LLM API (OpenAI) | $5-20/month | **$0** (local Ollama) |
| Managed Database | $15-50/month | **Included in VPS** |
| VPS Cost (4-core/8GB) | — | **$20-40/month** |
| **Total** | **$45-120/month** | **$20-40/month** |

**Annual Savings: $300-1000+**

---

## 10. Summary

With the system built in this tutorial, you now have:

1. ✅ **Complete BI platform** — Metabase provides visual data analysis and dashboards
2. ✅ **AI-powered natural language queries** — Ask questions in plain language, get instant data insights
3. ✅ **Fully self-hosted** — Data stays on your VPS, no privacy concerns
4. ✅ **Zero licensing costs** — All components are open-source, no subscription fees

This solution is ideal for:
- **Small to medium teams** — No dedicated data analyst, but need data-driven decisions
- **Solo entrepreneurs** — Professional-grade BI at minimal cost
- **Privacy-conscious organizations** — Data never leaves your infrastructure

**Next Steps**: Connect additional data sources (MySQL, MongoDB), configure scheduled report pushes, add more LLM models for complex analytical scenarios.

---

> 📌 **Resources**
> - [Metabase Documentation](https://www.metabase.com/docs/)
> - [Ollama Model Library](https://ollama.com/library)
> - [NL2SQL Research Survey](https://github.com/taoyds/nl2sql-survey)
> - [PostgreSQL Best Practices](https://wiki.postgresql.org/wiki/Best_Practices)
