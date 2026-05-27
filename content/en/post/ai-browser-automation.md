---
title: "AI Browser Automation: Deploy Browser-Use Agents on Your VPS (Full Code)"
description: "Let AI control your browser — auto-fill forms, scrape data, test web apps. Deploy Browser-Use with a local LLM on your VPS for 24/7 AI-powered web automation. Complete deployment guide with production-ready code."
date: 2026-05-27T21:30:00+08:00
slug: "ai-browser-automation"
tags: ["Browser-Use", "AI Automation", "Browser Automation", "Playwright", "LLM", "Web Scraping", "Self-hosting", "Docker", "Python"]
categories: ["AI Applications"]
image: /images/posts/ai-browser-automation/featured.png
draft: false
---

## Why AI Browser Automation?

Sound familiar?

- You log into a dashboard every morning and click through 15 pages to export a report
- You want to monitor a competitor's pricing but their site has no API
- You need to submit forms in bulk — hundreds of them
- You should write E2E tests for your web app, but it's too much effort

Traditional solutions are either manual labor or brittle Selenium scripts. One CSS class name change and your carefully crafted selectors are dead.

**AI browser automation flips the script**: just tell the AI *what* you want done, and it watches the screen, clicks the right buttons, fills in the forms, and adapts when the page changes. No more fragile XPath selectors.

The best part: **Browser-Use + a local LLM runs entirely on your VPS** — zero API costs, zero data leaving your server.

| Capability | Traditional Selenium | AI Browser-Use |
|-----------|-------------------|---------------|
| Script writing | Manual CSS/XPath selectors | Natural language |
| Page changes | ❌ Selectors break | ✅ AI adapts |
| Complex flows | Hard to maintain | One paragraph |
| CAPTCHAs/popups | Custom handling needed | AI handles visually |
| Self-hosted | Yes | Yes (fully private) |

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    Your VPS                               │
│  ┌─────────────────┐    ┌──────────────────────┐        │
│  │  Browser-Use CLI │───►│  AI Inference Engine │       │
│  │  • Python SDK    │    │  • Ollama            │        │
│  │  • Playwright    │    │  • Local LLM (Qwen/  │        │
│  │  • Chromium      │    │    DeepSeek/Llama)   │        │
│  └────────┬─────────┘    └──────────┬───────────┘        │
│           │                         │                     │
│           ▼                         ▼                     │
│  ┌──────────────────────────────────────────┐            │
│  │  Browser Instance (Headless/Headed)       │           │
│  │  • Navigate • Click • Type • Screenshot   │           │
│  └──────────────────────────────────────────┘            │
└─────────────────────────────────────────────────────────┘
```

## Step 1: Install Ollama + Browser Dependencies

Browser-Use works with many LLMs. We'll start with a local model (free, private), but it also supports OpenAI / Anthropic API out of the box.

```bash
# 1. Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# 2. Pull a capable model (Qwen2.5:7b or Llama 3.1 8B recommended)
ollama pull qwen2.5:7b

# 3. Install Python dependencies
pip install browser-use playwright

# 4. Install Playwright browsers
playwright install chromium
```

> **Why Qwen2.5 7B?** Strong Chinese AND English page comprehension, 128K context window for multi-step workflows, and runs on a 2GB VPS with 4-bit quantization. For English-only tasks, Llama 3.1 8B is a great alternative.

Verify the installation:

```bash
python3 -c "from browser_use import Agent; print('✅ Browser-Use ready')"
playwright --version
ollama list
```

## Step 2: Your First AI Browser Agent

A simple script that lets the AI search Google and take a screenshot — no selectors, no XPath:

```bash
mkdir -p /opt/browser-agent
vim /opt/browser-agent/search_demo.py
```

```python
#!/usr/bin/env python3
"""
Browser-Use Quickstart: Let AI search and screenshot
"""
import asyncio
from browser_use import Agent

async def main():
    agent = Agent(
        task="Go to https://www.google.com, search for 'Browser-Use GitHub', "
             "click the first result, wait for the page to load, "
             "and save a screenshot as result.png",
        llm="ollama/qwen2.5:7b",  # using local model
        use_vision=True,           # AI "sees" the page via screenshots
    )
    await agent.run()

if __name__ == "__main__":
    asyncio.run(main())
```

Run it:

```bash
cd /opt/browser-agent
python3 search_demo.py
```

Watch as a Chromium browser opens, types the query, clicks the link, and saves a screenshot. Zero CSS selectors needed.

## Step 3: Headless Mode Configuration

On a VPS, there's typically no display. Configure headless mode:

```python
#!/usr/bin/env python3
"""
Browser-Use Headless Mode Setup
"""
import asyncio
from browser_use import Agent
from browser_use.browser.browser import Browser, BrowserConfig

async def main():
    # Configure headless browser
    browser = Browser(
        config=BrowserConfig(
            headless=True,                    # no GUI needed
            disable_security=True,            # avoid CORS issues
            window_w=1280, window_h=720,      # viewport size
        )
    )

    agent = Agent(
        task="Log in to https://example.com/admin, "
             "find the 'Today's Data' panel, "
             "screenshot the data table and save as dashboard.png",
        llm="ollama/qwen2.5:7b",
        browser=browser,
        use_vision=True,
    )
    await agent.run()

if __name__ == "__main__":
    asyncio.run(main())
```

## Step 4: Practical Scenario — Auto Login + Data Export

A complete production script: log into a third-party dashboard, extract data, and save as CSV:

```python
#!/usr/bin/env python3
"""
Production: AI auto-login and report export to CSV
"""
import asyncio
import csv
from pathlib import Path
from browser_use import Agent
from browser_use.browser.browser import Browser, BrowserConfig
from browser_use.controller.service import Controller

# Define custom actions
controller = Controller()

@controller.action("Save data to CSV")
def save_to_csv(data: str, filename: str):
    """Save AI-extracted data to a CSV file"""
    path = Path(f"/opt/browser-agent/output/{filename}")
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = data.strip().split("\n")
    if lines:
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            for line in lines:
                writer.writerow(line.split(","))
    return f"Saved to {path}"

async def main():
    browser = Browser(
        config=BrowserConfig(headless=True, window_w=1280, window_h=720)
    )

    agent = Agent(
        task="""
        1. Open https://your-saas-dashboard.com/login
        2. Type 'admin@example.com' into the username field
        3. Type the password into the password field
        4. Click the login button
        5. Wait for the dashboard to fully load
        6. Click 'Reports' in the left navigation
        7. Select date range 'This Month'
        8. Click 'Export Data'
        9. Use save_to_csv to save the data as 'monthly_report.csv'
        10. Take a screenshot to confirm success
        """,
        llm="ollama/qwen2.5:7b",
        browser=browser,
        controller=controller,
        use_vision=True,
    )
    await agent.run()

if __name__ == "__main__":
    asyncio.run(main())
```

> **Security**: Use environment variables for credentials, never hardcode passwords:
> ```python
> import os
> password = os.environ.get("DASHBOARD_PASSWORD")
> ```

## Step 5: Cron Jobs — Let AI Work Daily

Combine with cron for scheduled browser automation:

```bash
vim /opt/browser-agent/run_daily_report.py
```

```python
#!/usr/bin/env python3
"""Daily automated report collection"""
import asyncio
from datetime import datetime
from browser_use import Agent
from browser_use.browser.browser import Browser, BrowserConfig

async def main():
    print(f"[{datetime.now()}] Starting daily report collection...")
    
    browser = Browser(
        config=BrowserConfig(headless=True)
    )

    agent = Agent(
        task="""
        1. Log in to https://analytics.example.com
        2. Navigate to 'Traffic Overview'
        3. Take a screenshot of the last 24h data, save as daily_traffic.png
        4. Find the 'Traffic Sources' table, extract Top 10 entries
        5. Save traffic sources using save_to_csv as traffic_sources.csv
        6. Check for anomalies (e.g., sudden traffic drop), note them on the page
        7. Take a final screenshot as daily_report_final.png
        """,
        llm="ollama/qwen2.5:7b",
        browser=browser,
        use_vision=True,
    )
    await agent.run()
    print(f"[{datetime.now()}] Report collection complete")

if __name__ == "__main__":
    asyncio.run(main())
```

Schedule it:

```bash
chmod +x /opt/browser-agent/run_daily_report.py

# Run daily at 8 AM
(crontab -l 2>/dev/null; echo "0 8 * * * cd /opt/browser-agent && python3 run_daily_report.py >> /var/log/browser-agent.log 2>&1") | crontab -

# Monitor logs
tail -f /var/log/browser-agent.log
```

## Step 6: Using Cloud LLMs (Alternative)

If your VPS has limited RAM (< 2GB) or you need stronger reasoning, plug in cloud APIs. Browser-Use supports them natively:

```python
# OpenAI
Agent(
    task="...",
    llm="openai/gpt-4o",
    # Set OPENAI_API_KEY environment variable
)

# Anthropic Claude
Agent(
    task="...",
    llm="anthropic/claude-sonnet-4-20250514",
)

# DeepSeek (ultra-low cost)
Agent(
    task="...",
    llm="deepseek/deepseek-chat",
)
```

> **Cost**: GPT-4o costs ~$0.01-0.05 per browser task. DeepSeek API is about 1/10th of GPT pricing. For high-frequency tasks, use a local model; for complex reasoning, fall back to cloud.

## Step 7: Docker Deployment (Production)

Package everything into Docker for reproducible deployments:

```bash
vim /opt/browser-agent/Dockerfile
```

```dockerfile
FROM python:3.11-slim

# System dependencies for Chromium
RUN apt-get update && apt-get install -y \
    curl \
    fonts-liberation \
    libappindicator3-1 \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libcups2 \
    libdbus-1-3 \
    libgdk-pixbuf2.0-0 \
    libnspr4 \
    libnss3 \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps
RUN pip install browser-use playwright \
    && playwright install chromium \
    && playwright install-deps

WORKDIR /app
COPY . .

CMD ["python3", "run_daily_report.py"]
```

```bash
vim /opt/browser-agent/docker-compose.yml
```

```yaml
version: '3.8'

services:
  browser-agent:
    build: .
    environment:
      - DASHBOARD_PASSWORD=${DASHBOARD_PASSWORD}
      - OPENAI_API_KEY=${OPENAI_API_KEY:-}
    volumes:
      - ./output:/app/output
      - ./screenshots:/app/screenshots
    restart: unless-stopped
```

```bash
# One-click start
cd /opt/browser-agent
docker-compose up -d
docker-compose logs -f
```

## Advanced Techniques

### 1. Multi-Step Task Chaining

Break complex workflows into sequential agents:

```python
agent_1 = Agent(task="Log in and navigate to the reports page", ...)
await agent_1.run()

# Pass context to next agent
agent_2 = Agent(
    task="Extract all data tables from the current page",
    context=agent_1.context,
    ...
)
await agent_2.run()
```

### 2. Retry with Recovery

```python
from tenacity import retry, stop_after_attempt

@retry(stop=stop_after_attempt(3))
async def run_agent_with_retry(task: str):
    agent = Agent(task=task, ...)
    await agent.run()
```

### 3. Multi-Tab Operations

```python
# Open multiple tabs simultaneously
agent = Agent(
    task="Open a price comparison page in a new tab "
         "while keeping the login session active in the current tab",
    ...
)
```

### 4. CAPTCHA Handling

The AI can visually identify and solve simple CAPTCHAs. For complex ones, integrate a CAPTCHA solver:

```python
@controller.action("Solve CAPTCHA")
def solve_captcha(image_path: str):
    """AI automatically reads and fills CAPTCHA"""
    # Browser-Use vision mode can read the CAPTCHA image directly
    pass
```

## Performance & Cost

| Configuration | Use Case | Monthly Cost |
|--------------|---------|-------------|
| 2GB RAM VPS | Simple tasks (search, screenshots), local 3B model | $3-5/mo |
| 4GB RAM VPS | Medium tasks (form fills, data extraction), 7B model | $6-8/mo |
| 8GB RAM VPS | Complex workflows, 14B model or cloud API | $10-15/mo |
| Cloud API only | High-precision tasks, no VPS limits | $5-20/mo (usage-based) |

## Security Best Practices

1. **Environment variables for secrets** — never hardcode passwords or API keys
2. **Restrict browser permissions** — disable geolocation, camera, and unnecessary APIs in Playwright
3. **Monitor for abnormal behavior** — alert if the agent navigates to unexpected URLs
4. **Run in a sandbox** — Docker container with restricted network and filesystem access
5. **Audit logging** — record every agent action for post-mortem analysis
6. **Use read-only accounts** — grant minimal permissions on target systems

## Summary

AI browser automation is changing how we interact with the web. Instead of writing brittle selector scripts, you describe what you want in natural language, and the AI watches the screen and executes.

By deploying Browser-Use on your VPS, you can:

- ✅ Automatically collect competitor public data every day
- ✅ Schedule dashboard report exports
- ✅ Automate regression testing for your web apps
- ✅ Process online forms and approval workflows in bulk
- ✅ Run a 24/7 web monitoring system

All data stays on your server — no third-party API costs, no privacy leaks.

### Next Steps

- Check out the [Browser-Use GitHub repo](https://github.com/browser-use/browser-use)
- Read the [Playwright Python docs](https://playwright.dev/python/docs/library)
- Combine with Hermes Agent for cron-triggered browser tasks
- Share your automation scripts on the selfvps.net community

---

*This article was originally published on selfvps.net. Please attribute if sharing.*
