---
title: "Uptime Kuma 自建服务监控：零成本 HTTPS 可用性监控与多渠道告警"
description: "告别 UptimeRobot 免费版限制，用 Uptime Kuma 在 VPS 上搭建可视化服务监控平台，支持 HTTP/HTTPS/DNS/Ping 等 15+ 监控类型，Telegram/Discord/邮件多渠道告警，全部零成本自托管。"
date: 2026-09-14T10:00:00+08:00
lastmod: 2026-09-14T10:00:00+08:00
slug: "vps-uptime-kuma-monitoring"
image: /images/posts/vps-uptime-kuma-monitoring/featured.png
tags: ["VPS", "Uptime Kuma", "监控", "告警", "Docker", "自托管", "零成本", "运维"]
categories: ["监控运维"]
aliases: [/zh/post/vps-uptime-kuma-monitoring/]
---

## 为什么需要 Uptime Kuma？

你托管了网站、API、数据库或者内部服务，但**你怎么知道它们是不是还活着？**

第三方监控服务（如 UptimeRobot 免费版）有诸多限制：
- 最多监控 50 个任务，每 5 分钟检测一次
- 告警渠道有限，高级功能收费
- 数据存在别人服务器上，隐私无从保障
- 自定义程度低，无法贴合你的工作流

**Uptime Kuma** 是这一切的终极替代方案——完全免费、自托管、界面精美、功能强大。它让你把监控基础设施掌握在自己手里，零成本运行，无限扩展。

---

## 核心优势一览

| 特性 | Uptime Kuma | UptimeRobot（免费版）| 付费监控服务 |
|------|-------------|---------------------|-------------|
| 监控数量 | **无限** | 50 个 | 按套餐 |
| 检测间隔 | **10 秒起** | 5 分钟 | 1 分钟起 |
| 部署方式 | 自托管 | 云端 SaaS | 云端 SaaS |
| 告警渠道 | **15+ 种** | 3 种 | 多种 |
| 数据归属 | **完全私有** | 第三方存储 | 第三方存储 |
| 成本 | **$0** | $0（受限） | $10-50/月 |

---

## 架构图解

```
┌──────────────────────────────────────────────────────────────┐
│                     Uptime Kuma（你的 VPS）                    │
│                                                              │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────┐  │
│  │  定时探测任务  │───▶│  状态引擎    │───▶│   告警通知       │  │
│  │  (10s/次)    │    │  (UP/DOWN)  │    │  (Telegram/     │  │
│  │              │    │             │    │   Discord/      │  │
│  │  • HTTP/S    │    │             │    │   Email/        │  │
│  │  • DNS 解析   │    │             │    │   微信/钉钉/...)  │  │
│  │  • Ping     │    │             │    │                 │  │
│  │  • TCP 端口  │    │             │    │                 │  │
│  │  • 关键词检测 │    │             │    │                 │  │
│  │  • Push     │    │             │    │                 │  │
│  └─────────────┘    └──────┬──────┘    └─────────────────┘  │
│                             │                               │
│                     ┌───────▼───────┐                       │
│                     │   PostgreSQL   │                       │
│                     │  (历史数据)     │                       │
│                     └───────────────┘                       │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              Web Dashboard :3001                     │    │
│  │         实时状态 • 历史曲线 • 故障时间线              │    │
│  └─────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────┘
```

---

## 第一步：Docker Compose 一键部署

创建一个 `docker-compose.yml` 文件：

```yaml
services:
  uptime-kuma:
    image: louislam/uptime-kuma:1
    container_name: uptime-kuma
    restart: unless-stopped
    ports:
      - "3001:3001"
    volumes:
      - ./uptime-kuma-data:/app/data
    environment:
      - TZ=Asia/Shanghai
```

启动服务：

```bash
mkdir -p ./uptime-kuma-data
docker compose up -d
```

访问 `http://your-vps-ip:3001`，你会看到一个简洁漂亮的界面。默认无需登录，首次进入会引导你创建管理员账户。

---

## 第二步：配置 Nginx 反向代理 + HTTPS

Uptime Kuma 本身不强制 HTTPS，但为了安全和移动端推送正常工作，强烈建议加上。

假设你已经有一个域名 `monitor.yourdomain.com`：

```nginx
server {
    listen 443 ssl http2;
    server_name monitor.yourdomain.com;

    ssl_certificate     /etc/letsencrypt/live/monitor.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/monitor.yourdomain.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:3001;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket 支持（Uptime Kuma 推送依赖）
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}

server {
    listen 80;
    server_name monitor.yourdomain.com;
    return 301 https://$host$request_uri;
}
```

用 Certbot 免费申请 SSL 证书：

```bash
certbot --nginx -d monitor.yourdomain.com
```

---

## 第三步：添加监控任务

Uptime Kuma 支持 **15 种以上**监控类型，覆盖几乎所有场景：

### 3.1 HTTP/HTTPS 监控

最常用的类型，检查网站是否可访问：

1. 点击 **"Add New Uptime"**
2. 类型选择 **HTTP(s)**
3. 填写 URL：`https://yourwebsite.com`
4. 告警时间间隔设为 **5 分钟**（避免频繁告警）
5. 勾选 **"Allow Sticky Status"** —— 同一故障周期只发一次告警

**进阶技巧：关键词检测**
如果你的首页包含特定文字（如站点标题），可以开启关键词检测。即使 HTTP 200 返回，只要页面内容不包含该关键词，也会触发告警——这能有效防止"假活"情况。

### 3.2 Ping 监控

检查服务器是否在线：

```
类型：Ping
目标：your-vps-ip 或 example.com
包大小：64 字节
次数：3 次
```

### 3.3 DNS 监控

确保域名解析正常：

```
类型：DNS
目标域名：yourdomain.com
DNS 服务器：8.8.8.8（可选指定）
期望记录类型：A
期望值：你的服务器 IP
```

### 3.4 Port 监控

检查某个 TCP/UDP 端口是否开放：

```
类型：Port
主机：your-service.internal
端口：6379（Redis）
协议：TCP
```

### 3.5 Push 监控（被动式）

这是 Uptime Kuma 最强大的功能之一——**无需主动轮询**，让服务自己"报平安"：

1. 创建 Push 类型监控任务
2. 获得唯一 URL：`https://monitor.yourdomain.com/api/push/xxxxx`
3. 在你的业务代码中，每次关键操作完成后调用这个 URL

```python
import urllib.request

def notify_uptime():
    urllib.request.urlopen(
        "https://monitor.yourdomain.com/api/push/your-push-key?status=up"
    )
```

这种方式特别适合**短时任务**（如定时脚本、批处理作业）——任务跑完发一条 push，如果超时没收到就判定失败。

---

## 第四步：配置多渠道告警

Uptime Kuma 内置丰富的告警渠道，以下是几种最常用的配置：

### 4.1 Telegram 告警

1. 进入 **Settings → Alert Settings**
2. 添加 **Telegram** 告警
3. 填入 Bot Token（从 @BotFather 获取）
4. 填入 Chat ID（发送 `/getids` 给 @userinfobot 获取）

Telegram 推送速度快、到达率高，是企业和个人用户的首选。

### 4.2 Discord Webhook

适合团队共用一个监控频道：

```
Webhook URL: https://discord.com/api/webhooks/xxx/xxx
消息格式支持 Markdown
```

### 4.3 企业微信 / 钉钉

Uptime Kuma 支持自定义 Webhook，通过 JSON 格式适配企业微信和钉钉：

```json
{
  "msgtype": "markdown",
  "markdown": {
    "content": "⚠️ 服务异常告警\n服务：example.com\n状态：DOWN\n时间：{{currentTime}}"
  }
}
```

### 4.4 邮件告警

SMTP 配置简单直接，适合不需要即时响应的场景：

```
SMTP 服务器：smtp.gmail.com:587
加密方式：STARTTLS
发件人：your-account@gmail.com
收件人：admin@yourdomain.com
```

---

## 第五步：配置优雅的时间窗口

不是所有时段都适合告警。比如深夜 23:00-07:00 可能是维护窗口，或者周末你不想被无关告警打扰。

Uptime Kuma 内置 **Downtime 时间窗口**功能：

```
Settings → Downtime
时间范围：00:00 - 07:00（每天）
效果：此时间段内服务中断不会触发告警
```

结合"Sticky Status"使用，可以避免凌晨误报轰炸你的通知渠道。

---

## 进阶技巧：用 Reverse Proxy 聚合多监控

如果你有多个 VPS 或多个项目，可以统一用 Nginx 反代到一个域名下：

```nginx
# 主监控面板
location / {
    proxy_pass http://127.0.0.1:3001;
}

# API 健康检查子路径（复用同一实例）
location /api/health {
    proxy_pass http://127.0.0.1:3001/api/health;
}
```

或者为每个项目独立部署一个 Kuma 实例（用不同端口），统一用 Cloudflare Tunnel 暴露到公网：

```yaml
# cloudflared tunnel 配置
tunnel: your-tunnel-id
credentials-file: /etc/cloudflared/creds.json

ingress:
  - hostname: monitor-project1.example.com
    service: http://localhost:3001
  - hostname: monitor-project2.example.com
    service: http://localhost:3002
  - service: http_error:404
```

---

## 性能与资源消耗

Uptime Kuma 非常轻量：

| 指标 | 数值 |
|------|------|
| 内存占用 | ~150MB（含 PostgreSQL）|
| CPU 占用 | < 5%（空闲时接近 0%）|
| 磁盘占用 | 约 50MB（默认数据）|
| 单个监控任务开销 | 极低 |

在一个 1GB 内存的 VPS 上，你可以同时监控 **数百个服务** 而不感到压力。

---

## 对比总结

| 需求场景 | 推荐方案 |
|----------|----------|
| 个人网站可用性监控 | Uptime Kuma（单实例）|
| 多项目团队监控 | 多实例 + Cloudflare Tunnel |
| 已有 Prometheus 栈 | Uptime Kuma（补充 HTTP 层）|
| 极简场景 | 一个 Ping + 一个 HTTP 任务 |
| 合规要求（数据不外出）| 完全自托管 Uptime Kuma |

---

## 结语

Uptime Kuma 是 VPS 运维者的**必备工具**——它用极低的资源消耗，提供了商业级监控平台的核心能力。更重要的是，你的监控数据完全掌握在自己手中，不依赖任何第三方服务。

从零部署到第一个告警，整个过程不超过 **15 分钟**。今天就开始吧，让你的服务永远"在线可见"。
