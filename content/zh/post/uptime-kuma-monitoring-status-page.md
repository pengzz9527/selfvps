---
title: "使用 Uptime Kuma 搭建自托管监控面板 —— VPS 状态一目了然"
description: "完全免费的 VPS 监控方案：用 Uptime Kuma 自建服务状态监控、宕机告警和公共状态页面。支持 Telegram/邮件/Webhook 推送，无需第三方付费服务。"
date: 2026-05-29T10:00:00+08:00
slug: "uptime-kuma-monitoring-status-page"
tags: ["Uptime Kuma", "监控", "状态页面", "Docker", "VPS运维", "告警", "自托管"]
categories: ["运维监控"]
image: /images/posts/uptime-kuma-monitoring-status-page/featured.png
draft: false
---

## 引言

运维 VPS 最怕什么？服务挂了却不知道。

传统的监控方案要么贵（Pingdom、Datadog），要么重（Prometheus + Grafana 全家桶）。对于个人站长和小团队来说，有没有一款**轻量、免费、开箱即用**的监控工具？

答案是 **Uptime Kuma** —— 一个开源的、自托管的服务监控工具，五分钟完成部署，支持 90+ 种通知方式，还能一键生成专业级别的状态页面。

## Uptime Kuma 是什么？

Uptime Kuma 是一个基于 Node.js 的开源监控工具。它的核心理念是「简单」：

- 🐳 **一行命令** Docker 部署
- 🔔 **90+ 种**通知渠道（Telegram、邮件、Discord、Slack、钉钉、企业微信……）
- 📊 **内置状态页面**，无需额外搭建
- 🔍 **多种监控类型**：HTTP(S)、TCP、Ping、DNS、SSL 证书、关键字检测、Docker 容器状态
- 🔐 **多用户支持**，可以给团队成员分配不同权限
- 🌐 **支持 IPv6**，双栈环境无压力

## 一、Docker 一键部署

Uptime Kuma 官方提供了 Docker 镜像，部署极其简单。

### 1. 基本部署

```bash
docker run -d \
  --name uptime-kuma \
  -p 3001:3001 \
  -v /data/uptime-kuma:/app/data \
  --restart unless-stopped \
  louislam/uptime-kuma:latest
```

部署完成后，浏览器访问 `http://你的VPS_IP:3001`，设置管理员账号密码即可使用。

### 2. 搭配反向代理（推荐）

将端口暴露到公网不安全，建议用 Nginx 或 Caddy 配置 HTTPS 反向代理。

**Caddy 配置示例**（最简单）：

```caddyfile
status.yourdomain.com {
    reverse_proxy localhost:3001
}
```

Caddy 自动申请 Let's Encrypt 证书，一行配置就解决了 HTTPS。

**Nginx 配置示例**：

```nginx
server {
    listen 443 ssl;
    server_name status.yourdomain.com;

    ssl_certificate /etc/ssl/certs/yourdomain.crt;
    ssl_certificate_key /etc/ssl/private/yourdomain.key;

    location / {
        proxy_pass http://127.0.0.1:3001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### 3. Docker Compose 部署（推荐生产环境）

```yaml
version: '3.8'

services:
  uptime-kuma:
    image: louislam/uptime-kuma:latest
    container_name: uptime-kuma
    volumes:
      - ./data:/app/data
    ports:
      - "3001:3001"
    restart: unless-stopped
    environment:
      - TZ=Asia/Shanghai
      - UPTIME_KUMA_PORT=3001
```

## 二、添加监控项

登录后台后，点击「添加监控项」，可以看到丰富的监控类型：

### 支持的监控类型

| 类型 | 适用场景 | 说明 |
|------|----------|------|
| HTTP(s) | Web 服务、API | 检查返回状态码（200/403/500），支持自定义请求头 |
| Ping | VPS、路由器 | ICMP 连通性检测 |
| TCP | 数据库、SSH | 检查端口是否开放 |
| DNS | DNS 解析服务 | 验证域名解析记录 |
| SSL 证书 | HTTPS 站点 | 监控证书到期天数，提前告警 |
| 关键字 | 内容检测 | 检查页面是否包含/不包含特定字符串 |
| Docker | 容器状态 | 直接监控同机 Docker 容器运行状态 |

### 实战配置建议

**对于 Web 应用**：
- 监控主域名 HTTPS（200 状态码检测）
- 监控关键 API 端点（如 `/health` 或 `/api/v1/health`）
- 设置 SSL 证书监控（提前 30 天告警）

**对于 VPS 主机**：
- 每 1-2 分钟 Ping 一次检测连通性
- 监控 SSH（22 端口）是否可达
- 监控关键服务端口（如数据库 3306、Redis 6379）

## 三、配置通知告警

Uptime Kuma 支持超过 90 种通知方式，这里介绍最常用的几种：

### 1. Telegram Bot 通知

1. 在 Telegram 搜索 `@BotFather`，创建新 Bot，获得 Token
2. 在 Uptime Kuma 设置 → 通知 → 添加 Telegram
3. 填入 Bot Token 和你的 Chat ID
4. 支持设置多个接收人

```text
Bot Token: 123456789:ABCdefGHIjklmNOPqrstUVwxyz
Chat ID:   -1001234567890（群组）或 12345678（个人）
```

### 2. 邮件通知（免 SMTP 方案）

Uptime Kuma 内置了邮件发送功能，也可以用第三方邮件服务：
- 用 Resend、SendGrid、Mailgun 等 API
- 或使用 SMTP（Gmail、QQ 邮箱等）

### 3. Webhook 通知

适合与企业微信、飞书、钉钉或自定义系统集成：

```json
{
  "msg_type": "interactive",
  "card": {
    "elements": [{
      "tag": "markdown",
      "content": "⚠️ **{{NAME}}** 已宕机\n时间：{{DATE}}\n状态码：{{STATUS}}"
    }]
  }
}
```

### 4. 告警策略设置

Uptime Kuma 支持灵活的告警策略：
- **重复次数**：连续失败 N 次才告警，避免瞬时抖动误报
- **告警间隔**：设置最小告警间隔，防止被通知刷屏
- **恢复通知**：服务恢复后自动发送恢复通知

## 四、搭建状态页面

Uptime Kuma 最亮眼的功能之一就是内建的状态页面。

### 1. 创建状态页面

设置 → 状态页面 → 添加状态页面，可以自定义：
- 页面标题和描述
- Logo 和 Favicon
- 主题色
- 展示哪些监控项
- 域名绑定

### 2. 分类展示

建议将服务分组展示，提高可读性：

```
📊 核心服务
  ├── Web 主站
  ├── API 服务
  └── 数据库

🌐 网络状态
  ├── 主节点 Ping
  ├── 备用节点 Ping
  └── DNS 解析

🔒 SSL 证书
  ├── 主域名证书
  ├── API 域名证书
  └── CDN 域名证书
```

### 3. 域名绑定 + 密码保护

状态页面可以绑定自定义域名（如 `status.yourdomain.com`），并且支持设置访问密码，仅对特定用户开放。

## 五、进阶用法

### 1. 监控同机 Docker 容器

如果 Uptime Kuma 和你监控的服务在同一台机器上，可以用 Docker Socket 直接监控容器状态：

```yaml
volumes:
  - /var/run/docker.sock:/var/run/docker.sock
```

然后在监控类型选择「Docker」，输入容器名称即可。

### 2. 代理监控

如果有多台 VPS，可以在一台主 Uptime Kuma 上部署，同时监控所有服务。但如果你希望**分布式监控**（从不同地理位置检测连通性），可以：

1. 在不同区域的 VPS 上各部署一个 Uptime Kuma
2. 通过 Webhook 将告警汇总到主节点
3. 或者用 Uptime Kuma 的「推送」功能，从远程节点上报状态

### 3. API 集成

Uptime Kuma 提供了 REST API，可以与其他系统集成：

```bash
# 获取所有监控项状态
curl -s https://status.yourdomain.com/api/status | jq .

# 获取单个监控项详情
curl -s https://status.yourdomain.com/api/monitor/1 | jq .
```

## 六、Uptime Kuma vs 其他方案

| 工具 | 免费 | 自托管 | 状态页面 | 通知渠道 | 部署难度 |
|------|------|--------|----------|----------|----------|
| **Uptime Kuma** | ✅ 完全免费 | ✅ | ✅ 内建 | 90+ | ⭐ 极简 |
| Prometheus + Grafana | ✅ | ✅ | ❌ 需额外配置 | 中等 | 🔴 复杂 |
| Pingdom | ❌ 收费 | ❌ | ✅ | 有限 | ⭐ 简单 |
| Better Uptime | 有限免费 | ❌ | ✅ | 中等 | ⭐ 简单 |
| StatusPage.io | ❌ 收费 | ❌ | ✅ | 有限 | ⭐ 简单 |
| HetrixTools | 有限免费 | ❌ | ✅ | 中等 | ⭐ 简单 |

**结论**：对于个人开发者和小团队，Uptime Kuma 是性价比最高的选择。完全免费、自托管数据不出境、内建状态页面、通知渠道丰富。

## 七、注意事项与最佳实践

### 安全建议

1. **反向代理必须启用 HTTPS**，避免明文传输密码
2. **定期更新镜像**：`docker pull louislam/uptime-kuma:latest && docker restart uptime-kuma`
3. **备份数据目录** `/app/data`，包含所有配置和历史记录
4. **设置强密码**，并启用双因素认证（2FA）

### 性能考虑

Uptime Kuma 本身非常轻量，监控 20-30 个服务只需 128MB 内存。但需要注意：
- 监控间隔不要设置太短（建议 HTTP 检测 ≥ 60 秒）
- 如果监控大量外部站点，注意出站流量

### 告警配置建议

```
正常 → 连续失败 3 次 → 发送告警 → 连续成功 1 次 → 发送恢复通知
         ↓                                 ↓
     每 30 分钟重发一次              停止通知
```

这样既能及时发现问题，又不会被瞬时抖动和重复通知打扰。

## 总结

Uptime Kuma 是我目前最推荐的个人 VPS 监控方案：

- **部署快**：一行 Docker 命令，5 分钟搞定
- **功能全**：HTTP、TCP、Ping、SSL、Docker 全面覆盖
- **通知强**：Telegram、邮件、Webhook 应有尽有
- **颜值高**：状态页面专业漂亮，拿得出手
- **零成本**：完全免费开源，数据完全自己掌控

如果你的 VPS 上运行着任何面向用户的服务，花 10 分钟部署一个 Uptime Kuma，远比等服务挂了由用户告诉你来得划算。

> **相关阅读**：[VPS 监控终极方案：Prometheus + Grafana 部署指南](/zh/post/vps-monitoring-prometheus-grafana/) | [Docker 安全加固：生产环境容器配置指南](/zh/post/docker-security-hardening/)
