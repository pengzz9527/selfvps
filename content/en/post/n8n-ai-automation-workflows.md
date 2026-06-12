---
title: "Building AI Automation Workflows with N8N: From Email Classification to Smart Reports"
description: "A step-by-step guide to deploying N8N workflow engine on your VPS, combined with Ollama local LLM for AI-powered email classification, document summarization, and automated report generation — all self-hosted for as low as €4/month."
date: 2026-06-12T10:00:00+08:00
slug: "n8n-ai-automation-workflows"
image: /images/posts/n8n-ai-automation-workflows/featured.png
tags: ["N8N", "automation", "AI Agent", "Ollama", "self-hosting", "workflow", "email classification", "Docker"]
categories: ["Automation"]
aliases: [/en/post/n8n-ai-automation-workflows/]
---

## Why Self-Host AI Automation?

Do you do these repetitive tasks every day?

- Open your inbox and manually sort spam, important emails, and promotions
- Pull data from multiple sources (Google Sheets, APIs, databases) and manually compile reports
- Read long articles and extract key points
- Aggregate notifications from different platforms to Telegram or Slack

If AI automation handled these tasks, you could save **5-10 hours per week**.

**N8N** is the best fair-code open-source workflow engine for self-hosting. Unlike Zapier (which charges per execution) or Make (which limits runtime), N8N is open-source and runs on your VPS — **unlimited executions, unlimited nodes, completely free**. You only pay for the VPS.

> **Cost comparison:** Zapier Basic $20/mo (500 executions), N8N self-hosted €3.99/mo (unlimited).

---

## What is N8N?

N8N is a **fair-code** open-source workflow automation tool. It lets you connect different services by dragging and dropping nodes:

```
 Gmail ──→ Email Classification(AI) ──→ Notion Auto-Create
  │
  ▼
Google Sheets ──→ Data Processing ──→ Telegram Notification
  │
  ▼
PostgreSQL ──→ Data Aggregation ──→ AI Weekly Report ──→ Email Send
```

Each "node" represents an action: read email, call API, execute SQL query, send message. Nodes are connected with lines, forming an automated pipeline.

**Key advantages of N8N:**

| Feature | N8N | Zapier | Make |
|---------|-----|--------|------|
| Self-hosted | ✅ | ❌ | ❌ |
| Data privacy | Fully local | Via 3rd party | Via 3rd party |
| Executions | Unlimited | Limited | Limited |
| Price | Free | $20+/mo | $9+/mo |
| AI nodes | Built-in Ollama support | Requires extra connect | Limited support |
| Custom code | Python/JS supported | JS only | JS only |

---

## Environment Requirements

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| VPS | 1 CPU / 2GB RAM | 2 CPU / 4GB RAM |
| Storage | 10GB SSD | 20GB+ SSD |
| Docker | ✅ Required | Docker Compose |
| OS | Ubuntu 22.04/24.04 | Debian 12 |

> **No GPU needed.** Email classification and report generation don't need GPU. Only LLM inference benefits from GPU, and CPU inference is perfectly fine.

---

## Step 1: Deploy N8N

### Install with Docker Compose

Create the project directory:

```bash
mkdir -p ~/n8n && cd ~/n8n
```

Create `docker-compose.yml`:

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

Generate encryption key:

```bash
echo "N8N_ENCRYPTION_KEY=$(openssl rand -hex 32)" >> .env
```

Start the service:

```bash
docker compose up -d
```

Visit `http://your-ip:5678` and set up your admin account.

### Reverse Proxy (Recommended: Nginx Proxy Manager)

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

## Step 2: Deploy Ollama Local LLM

N8N has a built-in LLM node that can call any OpenAI API-compatible service. Ollama is the simplest local option:

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

Pull a lightweight model:

```bash
# Enough for email classification + summarization
ollama pull qwen2.5:7b

# Even lighter (for 2GB RAM machines)
ollama pull qwen2.5:1.5b
```

Ollama listens on `http://localhost:11434` by default. You can use this address directly in N8N's LLM node with no extra configuration.

---

## Use Case 1: AI Email Classification

### Scenario

You receive 100+ emails daily. Manual sorting:
- **Important emails** (client inquiries, billing) → Star, sync to Notion
- **Promotional emails** → Archive
- **Spam** → Delete

### Workflow Design

```
┌─────────┐    ┌──────────────┐    ┌─────────────────┐
│ Gmail   │───→│ AI Classify  │───→│ Conditional Router│
│ (every 5│    │ Node (Ollama │    │ → Notion / Archive│
│  min)   │    │  + qwen2.5)  │    │ → Delete/Telegram │
└─────────┘    └──────────────┘    └─────────────────┘
```

### Steps

1. **Add Trigger**: Add a Gmail node in N8N, select "Watch for New Emails", set to check every 5 minutes
2. **Add AI Classification Node**: Use N8N's "AI Agent" node
   - LLM: Ollama (`http://localhost:11434`)
   - Model: `qwen2.5:7b`
   - Prompt template:

```
You are an email classification assistant. Analyze the following email and categorize it as:
- important: client inquiries, billing, contracts, important notices
- promotional: deals, discounts, marketing emails
- spam: junk mail, phishing
- newsletter: newsletters, weekly digests

Return JSON only: {"category": "important|promotional|spam|newsletter", "confidence": 0.95}

Subject: {{ $json["subject"] }}
From: {{ $json["from"] }}
Preview: {{ $json["textPreview"] }}
```

3. **Add Conditional Router Node**:
   - `important` → Call Notion API to create a page, sync to knowledge base
   - `promotional` → Call Gmail node, move to "Promotions" label
   - `spam` → Call Gmail node, mark as spam
   - Send Telegram notification: "Important email received: {{ subject }}"

### Result

After deployment, important emails are pinned and synced to your Notion todo list. Telegram notifies you. The rest are auto-sorted.

---

## Use Case 2: AI-Generated Weekly Reports

### Scenario

Every Monday you need to compile a weekly report from multiple sources:

- Google Sheets sales data
- PostgreSQL order database
- Third-party API server status

Manual compilation takes 2-3 hours.

### Workflow Design

```
┌──────────┐    ┌──────────┐    ┌──────────┐
│ Google   │    │ Post-    │    │ API     │
│ Sheets   │    │ SQL DB   │    │ Query   │
└────┬─────┘    └────┬─────┘    └────┬─────┘
     │               │               │
     └───────┬───────┴───────┬───────┘
             ▼               ▼
      ┌─────────────────────────┐
      │     Data Merge Node      │
      │  (Merge + Clean)         │
      └───────────┬─────────────┘
                  ▼
      ┌─────────────────────────┐
      │   AI Weekly Report       │
      │  (Ollama analyzes        │
      │   trends & insights)     │
      └───────────┬─────────────┘
                  ▼
      ┌─────────────────────────┐
      │   Delivery:              │
      │   • Gmail send PDF       │
      │   • Telegram summary     │
      │   • Google Drive save    │
      └─────────────────────────┘
```

### Steps

1. **Add Google Sheets Node**:
   - Operation: "Read Sheet"
   - Select worksheet and range
   - Set trigger: Every Monday at 9:00 AM

2. **Add PostgreSQL Node**:
   - Operation: "Execute Query"
   - SQL example:
   ```sql
   SELECT DATE(created_at) as day, COUNT(*) as orders, 
          SUM(amount) as revenue
   FROM orders
   WHERE created_at >= NOW() - INTERVAL '7 days'
   GROUP BY DATE(created_at)
   ORDER BY day;
   ```

3. **Data Merge Node**:
   - Use N8N's "Merge" node in "Append" mode
   - Add a "Code" node (JavaScript) for data cleaning and format normalization

4. **AI Weekly Report**:
   - Use "AI Agent" node
   - Prompt template:

```
You are a business analyst. Here is 7 days of business data:

{{ $json }}

Generate a weekly summary including:
1. Total sales and order count, with week-over-week percentage change
2. Fastest-growing category/service
3. Anomalous data that needs attention
4. Recommendations for next week

Use concise Markdown, under 500 words.
```

5. **Send Notifications**:
   - Gmail node: Compose email body and send
   - Telegram node: Push condensed summary
   - Google Drive node: Store full PDF report

---

## Use Case 3: Cross-Platform AI Content Digest

### Scenario

You follow industry trends across multiple platforms:

- Hacker News / Reddit for tech trends
- Twitter/X for industry influencer updates
- Your own RSS subscriptions

Browsing these platforms daily takes 1-2 hours.

### Workflow

```
┌──────────┐  ┌──────────┐  ┌──────────┐
│ RSS      │  │ Hacker   │  │ Twitter  │
│ Feed     │  │ News API │  │ API      │
└────┬─────┘  └────┬─────┘  └────┬─────┘
     │             │             │
     └──────┬──────┴──────┬──────┘
            ▼             ▼
     ┌─────────────────────────┐
     │   AI Summary & Dedup     │
     │  (Ollama extracts key    │
     │   points + cross-source  │
     │   deduplication)         │
     └───────────┬─────────────┘
                 ▼
     ┌─────────────────────────┐
     │   Deliver to:            │
     │   • Telegram morning     │
     │   • Obsidian knowledge   │
     │   • Email daily digest   │
     └─────────────────────────┘
```

### Key Implementation

1. **RSS Feed**: N8N has a built-in Feedparser node for RSS/Atom
2. **Hacker News**: Use N8N's HTTP Request node to call `https://hacker-news.firebaseio.com/v0/`
3. **AI Summary Node**:
   ```
   You are a tech news editor. Extract key information from these article titles and summaries:
   
   {{ $json }}
   
   Please:
   1. Deduplicate (merge similar titles)
   2. Categorize by topic (AI, Infrastructure, Security, Dev Tools)
   3. Provide under 50-word summary per item
   
   Return as JSON array.
   ```

4. **Store to Obsidian**: Create notes via Obsidian REST API with date tags and topic tags automatically

---

## Advanced: Create Your Custom N8N Nodes

If N8N doesn't have a built-in node for what you need, write custom code:

### Python Data Processing Node

```python
import pandas as pd
import json

# Receive input data
data = $input.all()

# Convert to DataFrame
df = pd.DataFrame([item.json for item in data])

# Data cleaning
df = df.dropna()
df['revenue'] = df['revenue'].astype(float)

# Aggregation
summary = {
    'total_revenue': df['revenue'].sum(),
    'avg_order': df['revenue'].mean(),
    'top_category': df['category'].value_counts().idxmax()
}

# Output
return [{
    'json': {
        'summary': json.dumps(summary, ensure_ascii=False),
        'record_count': len(df)
    }
}]
```

### Custom Telegram Notification Template

```javascript
// N8N Code Node (JavaScript)
const messages = $input.all();
const formatted = messages.map(msg => {
  return `📌 ${msg.json.title}\n${msg.json.summary}\n🔗 ${msg.json.url}`;
}).join('\n\n---\n\n');

return [{
  json: {
    chat_id: process.env.TELEGRAM_CHAT_ID,
    text: `📊 N8N AI Daily Report (${new Date().toISOString().split('T')[0]})\n\n${formatted}`,
    parse_mode: 'HTML'
  }
}];
```

---

## Scheduling: Make It Truly Automated

N8N supports Cron triggers. Once set up, everything runs automatically:

### Common Schedules

| Task | Frequency | Cron Expression |
|------|-----------|-----------------|
| Email Classification | Every 5 min | `*/5 * * * *` |
| Daily Summary | Daily 9:00 AM | `0 9 * * *` |
| Weekly Report | Mon 9:00 AM | `0 9 * * 1` |
| Data Backup | Daily 2:00 AM | `0 2 * * *` |
| Server Monitor Check | Every 15 min | `*/15 * * * *` |

---

## Security Best Practices

1. **Strong passwords**: Keep your N8N encryption key safe
2. **Force HTTPS**: Use Let's Encrypt certificates
3. **API key management**: Store secrets in environment variables
4. **Network isolation**: Only expose the Webhook port externally; don't expose database ports
5. **Regular backups**:

```bash
# Backup N8N data
docker exec n8n tar czf /tmp/n8n-backup.tar.gz /home/node/.n8n
rsync /tmp/n8n-backup.tar.gz backup-server:/backups/
```

---

## Total Cost Calculation

| Item | Cost |
|------|------|
| VPS (Hetzner CX22 / 2CPU 4GB) | €3.99/mo |
| Domain | €1/mo (amortized) |
| SSL Certificate | Free (Let's Encrypt) |
| Ollama Running Cost | Free (local inference) |
| **Total** | **~€5/mo** |

Compare with Zapier $20/mo + ChatGPT Plus $20/mo + Notion $10/mo = **$50/mo**. Self-hosted saves over 90%.

---

## Next Steps

N8N goes far beyond these use cases. You can also:

- 🤖 **AI Customer Support Bot**: Combine Ollama + knowledge base for natural language customer Q&A
- 📊 **Data Analytics Pipeline**: Pull data from multiple sources and auto-generate visual reports
- 🔒 **Security Monitoring**: Real-time server log monitoring with AI anomaly detection and auto-response
- 📝 **Content Publishing Pipeline**: Auto-publish drafts to multiple platforms (blog, Twitter, LinkedIn)

> **Core concept: N8N is your "automation brain", Ollama is your "AI brain", and your VPS is your "body". Together, you own a 24/7 digital worker — fully self-hosted, cost-efficient, and completely under your control.**

Start building your first workflow today. Begin with the simplest one — "new email notification to Telegram" — and gradually expand.
