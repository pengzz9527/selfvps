---
title: "自建 DevOps 仪表盘：CloudPanel + Uptime Kuma + Gatus"
description: "手把手教你用 CloudPanel 面板 + Uptime Kuma 监控 + Gatus 健康检查，搭建一个统一的 VPS 管理仪表盘，告别碎片化工具"
date: 2026-07-08T10:00:00+08:00
slug: "cloudpanel-devops-dashboard"
image: /images/posts/cloudpanel-devops-dashboard/featured.png
tags: ["DevOps", "VPS", "CloudPanel", "Uptime Kuma", "Gatus", "监控", "面板", "自动化"]
categories: ["DevOps 实践"]
aliases: [/zh/post/cloudpanel-devops-dashboard/]
---

## 引言

> **最好的运维，是让你不需要运维。**

当你管理多个 VPS、多个站点、多个微服务时，最大的痛点不是单个工具的缺失，而是**信息碎片化**——你要打开面板看资源、打开监控看可用性、打开日志看错误。每个工具一个界面，每次排查要切换三次浏览器标签。

本文将带你搭建一套**三合一 DevOps 仪表盘**：

- **CloudPanel** — 轻量级 VPS 面板，管理站点、数据库、SSL 证书
- **Uptime Kuma** — 开源监控，支持 HTTP/TCP/Ping/DNS 等多协议告警
- **Gatus** — 极简健康检查引擎，通过 YAML 定义一切，自带 beautiful dashboard

全部自托管在一台 VPS 上，总成本 ≈ 0 元。

---

## 一、架构概览

```
┌─────────────────────────────────────────────────┐
│                  你的 VPS (Ubuntu 24.04)          │
│                                                  │
│  ┌──────────────┐  ┌──────────────┐             │
│  │  CloudPanel   │  │ Uptime Kuma  │             │
│  │  :8080        │  │ :3001        │             │
│  │  站点管理     │  │ 监控告警     │             │
│  └──────────────┘  └──────┬───────┘             │
│                           │                      │
│                    ┌──────▼───────┐              │
│                    │   Gatus      │              │
│                    │  :8081       │              │
│                    │  健康检查     │              │
│                    └──────────────┘              │
│                                                  │
│         Nginx Reverse Proxy (端口统一)            │
│    panel.yourdomain.com / monitor.yourdomain.com  │
└─────────────────────────────────────────────────┘
```

---

## 二、CloudPanel 安装

CloudPanel 是一个专为高性能应用设计的轻量级面板，基于 Nginx + MySQL/PostgreSQL + PHP/Node.js/Python。

### 2.1 一键安装

```bash
# SSH 到你的 VPS，执行以下命令：
curl -sSf https://www.cloudpanel.io/sh/install.sh | bash
```

安装完成后，你会看到类似这样的输出：

```
CloudPanel installed successfully!
Please visit: http://YOUR_IP:8080
Username: admin
Password: xxxxxxxxxx
```

### 2.2 初始配置

1. 访问 `http://你的IP:8080`，使用默认凭据登录
2. 首次登录后强制修改密码
3. 配置 SMTP 邮件服务器（用于 SSL 证书通知和告警）
4. 添加第一个站点：

```
站点类型选择 → 站点 → 输入域名 → 创建
```

### 2.3 关键配置项

| 配置项 | 推荐值 | 说明 |
|--------|--------|------|
| PHP 版本 | 8.3 | 最新稳定版，性能最佳 |
| 数据库 | MySQL 8.0 / PostgreSQL 15 | 根据应用需求选择 |
| Nginx 缓存 | 开启 | 静态资源缓存，提升响应速度 |
| SSL 证书 | Let's Encrypt | 自动续期，免费 |
| 备份策略 | 每周全量 + 每日增量 | 保留 4 周 |

---

## 三、Uptime Kuma 部署

Uptime Kuma 是一款颜值极高的开源监控工具，支持多种监控类型和告警渠道。

### 3.1 Docker 部署

```bash
docker run -d \
  --name uptime-kuma \
  --restart unless-stopped \
  -p 3001:3001 \
  -v uptime-kuma-data:/app/data \
  louislam/uptime-kuma:1
```

### 3.2 添加监控目标

登录后，点击 **"Add New Monitor"**：

#### HTTP 监控示例（网站可用性）

```
Display Name: 我的博客
Type: HTTP(s)
URL: https://blog.yourdomain.com
Method: GET
Interval: 1 分钟
Keywords: "Welcome"
```

#### TCP 监控示例（数据库端口）

```
Display Name: MySQL 主库
Type: TCP
Host: 127.0.0.1
Port: 3306
Interval: 30 秒
```

#### Ping 监控示例（服务器存活检测）

```
Display Name: 边缘节点
Type: Ping
Host: edge.yourdomain.com
Interval: 1 分钟
```

### 3.3 告警配置

Uptime Kuma 支持丰富的告警渠道：

| 渠道 | 配置方式 |
|------|----------|
| Telegram Bot | 创建 BotFather → 获取 Token → 填入 |
| 企业微信 | Webhook URL + 消息体模板 |
| 钉钉 | Webhook + 签名验证 |
| 邮件 | SMTP 配置 |
| Bark (iOS) | Bark Server URL |
| Pushover | API Key + User Key |

**Telegram 告警配置示例：**

```
1. 打开 @BotFather，发送 /newbot
2. 获取 Bot Token: 123456789:ABCdefGHIjklMNOpqrsTUVwxyz
3. 搜索 @userinfobot，获取你的 Chat ID: 987654321
4. 在 Uptime Kuma 告警设置中填入：
   - Type: Telegram
   - Bot Token: 123456789:ABCdefGHIjklMNOpqrsTUVwxyz
   - Chat ID: 987654321
   - Message: 警报: {monitor.name} {status}
```

---

## 四、Gatus 部署

Gatus 是一个自动化的服务状态引擎，通过 YAML 配置定义健康检查规则，内置漂亮的 dashboard。

### 4.1 Docker Compose 部署

创建 `docker-compose.yml`：

```yaml
version: "3"

services:
  gatus:
    image: twinproduction/gatus:v5
    container_name: gatus
    restart: unless-stopped
    ports:
      - "8081:8080"
    volumes:
      - ./config:/config
    command: ["-config", "/config/config.yaml"]
```

### 4.2 健康检查配置

创建 `config/config.yaml`：

```yaml
storage:
  type: sqlite
  path: /config/sqlite.db
  cache: true

metrics: true

endpoints:
  # 博客网站
  - name: 博客
    url: https://blog.yourdomain.com
    interval: 1m
    conditions:
      - "[STATUS] == 200"
      - "[BODY] contains 'Hello'"
      - "[RESPONSE TIME] < 500ms"

  # CloudPanel 面板
  - name: CloudPanel
    url: http://localhost:8080
    conditions:
      - "[STATUS] == 200"

  # MySQL 数据库
  - name: MySQL
    url: tcp://localhost:3306
    conditions:
      - "[CONNECTED] == true"

  # Redis 缓存
  - name: Redis
    url: tcp://localhost:6379
    conditions:
      - "[CONNECTED] == true"

  # API 端点
  - name: 用户 API
    url: https://api.yourdomain.com/health
    interval: 30s
    conditions:
      - "[STATUS] == 200"
      - "[BODY].status == 'ok'"
      - "[RESPONSE TIME] < 200ms"

  # DNS 解析
  - name: DNS 检查
    url: dns://blog.yourdomain.com
    conditions:
      - "[IP] != null"

alerts:
  - type: telegram
    enabled: true
    bot-token: "123456789:ABCdefGHIjklMNOpqrsTUVwxyz"
    chat-id: "987654321"
    send-on-resolved: true
    failure-threshold: 3
    description: "连续失败 3 次后发送告警"
```

### 4.3 Gatus 核心优势

| 特性 | 说明 |
|------|------|
| YAML 即配置 | 所有监控规则版本可控，GitOps 友好 |
| 条件表达式 | 支持状态码、响应时间、响应体匹配 |
| 多协议 | HTTP、TCP、DNS、ICMP |
| 内建 Dashboard | `/api/v1/endpoints` 返回 JSON，`/` 返回美观页面 |
| 告警集成 | Telegram、Slack、Discord、Webhook 等 |
| 历史数据 | SQLite 存储，可查询历史趋势 |

---

## 五、Nginx 统一入口

为了让三个工具通过域名统一访问，配置 Nginx 反向代理：

```nginx
# /etc/nginx/sites-available/devops-dashboard

server {
    listen 443 ssl http2;
    server_name panel.yourdomain.com;

    ssl_certificate     /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

    # CloudPanel
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

server {
    listen 443 ssl http2;
    server_name monitor.yourdomain.com;

    ssl_certificate     /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

    # Uptime Kuma
    location / {
        proxy_pass http://127.0.0.1:3001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}

server {
    listen 443 ssl http2;
    server_name status.yourdomain.com;

    ssl_certificate     /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

    # Gatus
    location / {
        proxy_pass http://127.0.0.1:8081;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

```bash
# 启用配置并重新加载
ln -s /etc/nginx/sites-available/devops-dashboard /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
```

---

## 六、自动化与进阶

### 6.1 每日健康报告

创建一个简单的 cron 任务，每天早上 9 点汇总前一日状态：

```bash
# crontab -e
0 9 * * * curl -s http://localhost:8081/api/v1/status | \
  jq '{total: (.endpoints | length), up: ([.endpoints[] | select(.statuses[0].success)] | length)}' | \
  curl -s -X POST "https://api.telegram.org/botBOT_TOKEN/sendMessage" \
  -d "chat_id=CHAT_ID" \
  -d "text=📊 每日健康报告: 总共 \(.total) 个服务, 在线 \(.up) 个" \
  -d "parse_mode=HTML"
```

### 6.2 自动故障恢复

结合 CloudPanel 的命令行工具，可以实现常见故障的自动处理：

```bash
#!/bin/bash
# /usr/local/bin/auto-restart-service.sh

SERVICE_NAME=$1
CONTAINER_ID=$(docker ps -q -f name=$SERVICE_NAME)

if [ -z "$CONTAINER_ID" ]; then
    echo "$(date): $SERVICE_NAME 容器已停止，正在重启..." >> /var/log/service-restart.log
    docker start $SERVICE_NAME
    curl -s -X POST "https://api.telegram.org/botTOKEN/sendMessage" \
      -d "chat_id=CHAT_ID" \
      -d "text=⚠️ $SERVICE_NAME 已自动重启"
fi
```

### 6.3 安全加固

| 措施 | 命令/配置 |
|------|-----------|
| 基本认证 | Nginx `auth_basic` 保护监控入口 |
| IP 白名单 | `allow 你的IP; deny all;` |
| HTTPS 强制 | 所有入口启用 TLS |
| 定期更新 | `docker pull louislam/uptime-kuma:1 && docker restart uptime-kuma` |
| 日志审计 | `journalctl -u nginx -f` |

---

## 七、资源占用评估

| 组件 | CPU | 内存 | 磁盘 |
|------|-----|------|------|
| CloudPanel | ~5% | ~150MB | ~200MB |
| Uptime Kuma | ~2% | ~80MB | ~50MB |
| Gatus | ~1% | ~30MB | ~20MB |
| **总计** | **~8%** | **~260MB** | **~270MB** |

对于一台 2 核 2GB 的 VPS，这套组合的额外开销不到 15%，完全可以接受。

---

## 八、总结

| 工具 | 核心价值 |
|------|----------|
| **CloudPanel** | 站点管理、SSL、数据库的一站式面板 |
| **Uptime Kuma** | 直观的多协议监控 + 多渠道告警 |
| **Gatus** | YAML 驱动的健康检查 + 漂亮的状态页 |

三者配合，形成一个完整的 VPS 运维闭环：

```
CloudPanel (管理) → Uptime Kuma (监控) → Gatus (健康检查)
                                                ↓
                                          告警通知 (Telegram/钉钉)
                                                ↓
                                          自动恢复 (脚本)
```

**下一步建议：**
1. 先部署 CloudPanel，管理你的站点
2. 添加 Uptime Kuma，建立监控基线
3. 最后部署 Gatus，实现 YAML 驱动的健康检查
4. 配置告警渠道，确保异常及时通知

这套方案的魔力在于：**所有数据都在你自己的 VPS 上，不依赖任何第三方 SaaS**。真正的自托管，从掌控自己的运维仪表盘开始。
