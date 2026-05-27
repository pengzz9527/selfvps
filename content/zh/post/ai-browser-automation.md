---
title: "AI 浏览器自动化：在 VPS 上部署 Browser-Use 智能体（含完整代码）"
description: "让 AI 替你操控浏览器——自动填表、抓取数据、测试网页。用 Browser-Use + 本地 LLM 在 VPS 上搭建 AI 浏览器自动化智能体，24 小时在线执行任务。本文提供完整部署与实战代码。"
date: 2026-05-27T21:30:00+08:00
slug: "ai-browser-automation"
tags: ["Browser-Use", "AI自动化", "浏览器自动化", "Playwright", "LLM", "Web Scraping", "自托管", "Docker", "Python"]
categories: ["AI 应用"]
image: /images/posts/ai-browser-automation/featured.png
draft: false
---

## 为什么需要 AI 浏览器自动化？

你有没有这样的场景：

- 每天需要登录后台导出报表，重复点击十几次
- 想监控某个 SaaS 产品的价格变动，但对方没有 API
- 需要批量提交表单，手动填到手酸
- 想测试自己的 Web 应用，但写 E2E 测试太费时间

传统方案要么靠人肉操作，要么写脆弱的 Selenium 脚本。每次页面结构一变，代码就报废。

**AI 浏览器自动化**的思路完全不同——你只需要告诉 AI「帮我做什么」，它自己看着网页，自己点、自己填、自己判断。页面变化？AI 能自适应。

更棒的是：**Browser-Use + 本地 LLM 全部跑在你的 VPS 上**，没有第三方 API 调用费，数据不出服务器。

| 能力 | 传统 Selenium | AI Browser-Use |
|------|-------------|---------------|
| 脚本编写 | 手写 CSS/XPath 选择器 | 自然语言描述任务 |
| 页面变化 | ❌ 选择器失效 | ✅ AI 自适应 |
| 复杂交互 | 多步逻辑难维护 | 一句话搞定 |
| 验证码/弹窗 | 需要额外处理 | AI 自动识别处理 |
| 本地部署 | 可以 | 可以（全自托管） |

## 架构总览

```
┌─────────────────────────────────────────────────────────┐
│                    你的 VPS                               │
│  ┌─────────────────┐    ┌──────────────────────┐        │
│  │  Browser-Use CLI │───►│  AI 推理引擎         │       │
│  │  • Python SDK    │    │  • Ollama            │        │
│  │  • Playwright    │    │  • 本地 LLM (Qwen/   │        │
│  │  • Chromium      │    │    DeepSeek/Llama)   │        │
│  └────────┬─────────┘    └──────────┬───────────┘        │
│           │                         │                     │
│           ▼                         ▼                     │
│  ┌──────────────────────────────────────────┐            │
│  │  浏览器实例（无头/有头模式）                │           │
│  │  • 页面导航 • 点击 • 输入 • 截图 • 提取    │           │
│  └──────────────────────────────────────────┘            │
└─────────────────────────────────────────────────────────┘
```

## 第一步：安装 Ollama + 浏览器依赖

Browser-Use 可以用各种 LLM。我们先用本地模型（免费、隐私），同时它也支持 OpenAI / Anthropic API。

```bash
# 1. 安装 Ollama
curl -fsSL https://ollama.com/install.sh | sh

# 2. 拉取模型（推荐 Qwen2.5:7b 或 DeepSeek-Coder-V2）
ollama pull qwen2.5:7b

# 3. 安装 Python 依赖
pip install browser-use playwright

# 4. 安装 Playwright 浏览器
playwright install chromium
```

> **为什么选 Qwen2.5 7B？** 它对中文网页理解好，128K 上下文窗口能记住多步操作，且可以在 2GB VPS 上通过 4bit 量化运行。

验证安装：

```bash
python3 -c "from browser_use import Agent; print('✅ Browser-Use 安装成功')"
playwright --version
ollama list
```

## 第二步：第一个 AI 浏览器智能体

创建一个简单的脚本，让 AI 自动搜索并截图：

```bash
mkdir -p /opt/browser-agent
vim /opt/browser-agent/search_demo.py
```

```python
#!/usr/bin/env python3
"""
Browser-Use 入门示例：让 AI 自己搜索并截图
"""
import asyncio
from browser_use import Agent

async def main():
    agent = Agent(
        task="打开 https://www.google.com，搜索 'Browser-Use GitHub'，"
             "然后点击第一个搜索结果，等待页面加载后截图保存为 result.png",
        llm="ollama/qwen2.5:7b",  # 使用本地模型
        use_vision=True,           # AI 会"看"屏幕截图来理解页面
    )
    await agent.run()

if __name__ == "__main__":
    asyncio.run(main())
```

运行：

```bash
cd /opt/browser-agent
python3 search_demo.py
```

你会看到浏览器自动打开 → 输入搜索词 → 点击链接 → 截图。全程无需你写一行选择器代码。

## 第三步：配置无头模式（Headless）

在 VPS 上通常没有显示器，需要用无头模式运行：

```python
#!/usr/bin/env python3
"""
Browser-Use 无头模式配置
"""
import asyncio
from browser_use import Agent
from browser_use.browser.browser import Browser, BrowserConfig

async def main():
    # 配置无头浏览器
    browser = Browser(
        config=BrowserConfig(
            headless=True,                    # 无头模式
            disable_security=True,            # 避免 CORS 限制
            window_w=1280, window_h=720,      # 分辨率
        )
    )

    agent = Agent(
        task="登录 https://example.com/admin，"
             "找到 '今日数据' 面板，截取数据表格并保存为 dashboard.png",
        llm="ollama/qwen2.5:7b",
        browser=browser,
        use_vision=True,
    )
    await agent.run()

if __name__ == "__main__":
    asyncio.run(main())
```

## 第四步：实用场景 —— 自动登录 + 数据采集

下面是一个完整的实战脚本：自动登录第三方后台，抓取数据并导出为 CSV：

```python
#!/usr/bin/env python3
"""
实战：AI 自动登录后台并导出报表
"""
import asyncio
import csv
from pathlib import Path
from browser_use import Agent
from browser_use.browser.browser import Browser, BrowserConfig
from browser_use.controller.service import Controller

# 定义自定义操作
controller = Controller()

@controller.action("保存数据到 CSV")
def save_to_csv(data: str, filename: str):
    """将AI提取的数据保存到CSV文件"""
    path = Path(f"/opt/browser-agent/output/{filename}")
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = data.strip().split("\n")
    if lines:
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            for line in lines:
                writer.writerow(line.split(","))
    return f"已保存到 {path}"

async def main():
    browser = Browser(
        config=BrowserConfig(headless=True, window_w=1280, window_h=720)
    )

    agent = Agent(
        task="""
        1. 打开 https://your-saas-dashboard.com/login
        2. 输入用户名 'admin@example.com' 到用户名输入框
        3. 输入密码 'your_password' 到密码输入框
        4. 点击登录按钮
        5. 等待仪表盘加载完成
        6. 点击左侧导航的 '报表中心'
        7. 选择日期范围 '本月'
        8. 点击 '导出数据' 按钮
        9. 使用 save_to_csv 操作保存数据到 'monthly_report.csv'
        10. 截图确认操作成功
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

> **安全提醒**：请使用环境变量管理密码，不要硬编码在脚本中。示例：
> ```python
> import os
> password = os.environ.get("DASHBOARD_PASSWORD")
> ```

## 第五步：定时任务 —— 让 AI 每天自动工作

结合 cron 让 AI 浏览器智能体定时执行任务：

```bash
vim /opt/browser-agent/run_daily_report.py
```

```python
#!/usr/bin/env python3
"""每日自动报表采集"""
import asyncio
import sys
from datetime import datetime
from browser_use import Agent
from browser_use.browser.browser import Browser, BrowserConfig

async def main():
    print(f"[{datetime.now()}] 开始执行每日报表采集...")
    
    browser = Browser(
        config=BrowserConfig(headless=True)
    )

    agent = Agent(
        task="""
        1. 登录 https://analytics.example.com
        2. 导航到 '流量概览' 页面
        3. 截取过去24小时的数据概览，保存为 daily_traffic.png
        4. 查看 '来源分析' 表格，提取 Top 10 流量来源
        5. 使用 save_to_csv 保存为 traffic_sources.csv
        6. 检查是否有异常数据（如流量骤降），如有则在页面醒目备注
        7. 截图最终页面保存为 daily_report_final.png
        """,
        llm="ollama/qwen2.5:7b",
        browser=browser,
        use_vision=True,
    )
    await agent.run()
    print(f"[{datetime.now()}] 报表采集完成")

if __name__ == "__main__":
    asyncio.run(main())
```

设置定时任务：

```bash
chmod +x /opt/browser-agent/run_daily_report.py

# 每天早 8 点执行
(crontab -l 2>/dev/null; echo "0 8 * * * cd /opt/browser-agent && python3 run_daily_report.py >> /var/log/browser-agent.log 2>&1") | crontab -

# 查看日志
tail -f /var/log/browser-agent.log
```

## 第六步：使用 Cloud LLM（备选方案）

如果你的 VPS 内存有限（< 2GB），或者想要更强的推理能力，可以接入云 API。Browser-Use 原生支持：

```python
# 使用 OpenAI
Agent(
    task="...",
    llm="openai/gpt-4o",
    # 通过环境变量 OPENAI_API_KEY 传入密钥
)

# 使用 Anthropic Claude
Agent(
    task="...",
    llm="anthropic/claude-sonnet-4-20250514",
)

# 使用 DeepSeek（成本极低）
Agent(
    task="...",
    llm="deepseek/deepseek-chat",
)

# 使用本地 + 云端混合策略
# 简单任务用本地模型，复杂任务回退到云端
```

> **成本估算**：GPT-4o 每次浏览器任务约 $0.01-0.05。DeepSeek API 成本仅为 GPT 的 1/10。对于高频任务，建议用本地模型。

## 第七步：Docker 部署（生产环境）

用 Docker 封装整个环境，方便部署和迁移：

```bash
vim /opt/browser-agent/Dockerfile
```

```dockerfile
FROM python:3.11-slim

# 安装系统依赖
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

# 安装 Python 依赖
RUN pip install browser-use playwright \
    && playwright install chromium \
    && playwright install-deps

WORKDIR /app
COPY . .

CMD ["python3", "run_daily_report.py"]
```

```bash
# docker-compose.yml
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
    # 如果需要看浏览器界面，可暴露端口（调试用）
    # ports:
    #   - "6080:6080"
```

```bash
# 一键启动
cd /opt/browser-agent
docker-compose up -d
docker-compose logs -f
```

## 进阶技巧

### 1. 多步骤任务编排

将复杂任务拆分为多个 Agent 串联执行：

```python
agent_1 = Agent(task="登录系统并导航到报表页面", ...)
await agent_1.run()

# 将 agent_1 的上下文传给 agent_2
agent_2 = Agent(
    task="基于当前页面，提取所有数据表格",
    context=agent_1.context,
    ...
)
await agent_2.run()
```

### 2. 错误重试与恢复

```python
from browser_use import Agent
from tenacity import retry, stop_after_attempt

@retry(stop=stop_after_attempt(3))
async def run_agent_with_retry(task: str):
    agent = Agent(task=task, ...)
    await agent.run()
```

### 3. 多 Tab 并行操作

```python
# 打开多个标签页
agent = Agent(
    task="在新标签页中打开价格对比页面，同时在当前标签页保持登录状态",
    ...
)
```

### 4. 验证码处理

AI 可以自动识别简单验证码，对于复杂的建议接打码平台：

```python
@controller.action("填写验证码")
def fill_captcha(image_path: str):
    """AI 自动识别并填写验证码"""
    # Browser-Use Vision 模式可以自动读取验证码图片
    pass
```

## 性能与成本

| 配置 | 适用场景 | 参考月费 |
|------|---------|---------|
| 2GB RAM VPS | 简单任务（搜索、截图），使用本地 3B 模型 | $3-5/月 |
| 4GB RAM VPS | 中等任务（表单填写、数据采集），使用 7B 模型 | $6-8/月 |
| 8GB RAM VPS | 复杂任务（多步流程），使用 14B 模型或云 API | $10-15/月 |
| 云端 API | 高精度任务，无 VPS 性能限制 | $5-20/月（按量计费） |

## 安全最佳实践

1. **使用环境变量管理凭据**：永远不要在代码中硬编码密码
2. **限制浏览器权限**：在 Playwright 中禁用不必要的 API（如地理位置、摄像头）
3. **监控异常行为**：Agent 如果开始访问非预期的 URL，应设置告警
4. **沙箱运行**：在 Docker 容器中隔离运行，限制网络和文件系统访问
5. **日志审计**：记录所有 Agent 操作，便于回溯问题
6. **使用只读账号**：对目标系统使用最小权限账号

## 总结

AI 浏览器自动化正在改变我们与网页交互的方式。你不再需要写脆弱的选择器脚本——只需要用自然语言描述任务，AI 就能自己看着网页完成操作。

通过将 Browser-Use 部署在你的 VPS 上，你可以：

- ✅ 每天自动采集竞争对手的公开信息
- ✅ 定时登录后台导出报表
- ✅ 自动化 Web 应用的回归测试
- ✅ 批量处理在线表单和审批流程
- ✅ 搭建 24/7 在线的网页监控系统

所有数据保留在你的服务器上，没有第三方 API 依赖，没有隐私泄露风险。

### 下一步

- 阅读 [Browser-Use 官方文档](https://github.com/browser-use/browser-use)
- 查看 [Playwright 配置指南](https://playwright.dev/python/docs/library)
- 尝试结合 Hermes Agent 定时触发浏览器任务
- 在 selfvps.net 社区分享你的自动化脚本

---

*本文发布于 selfvps.net，转载请注明出处。*
