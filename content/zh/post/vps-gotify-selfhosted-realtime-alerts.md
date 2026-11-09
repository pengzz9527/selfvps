---
title: "GoGetify 替代品？不——自建 GoNotify：在 VPS 上运行 7MB 的实时告警推送器，0 订阅费"
description: "Prometheus/Watchtower 告警发到 Slack/Discord 都要花钱或受限。本文教你在 1C1G VPS 上自托管 Getify 兼容的实时推送器：Webhook 一行配置、Telegram/Email/钉钉全通、Docker 镜像仅 7MB、CPU 占用 <0.5%。附 Prometheus 告警联动完整示例，月省 $5-12 订阅费，还顺便干掉一条公网出口通道。"
date: 2026-11-09T12:00:00+08:00
lastmod: 2026-11-09T12:00:00+08:00
slug: "vps-gotify-selfhosted-realtime-alerts"
image: /images/posts/vps-gotify-selfhosted-realtime-alerts/featured.png
tags: ["VPS", "告警", "自托管", "Docker", "GoNotify", "Prometheus", "Telegram", "Webhook", "省钱", "运维"]
categories: ["VPS 省钱与运维", "自托管"]
aliases: ["/zh/post/vps-gotify-selfhosted-realtime-alerts/"]
draft: false
---

## 引言：告警通道为什么总是「先花钱」

大多数人的告警链路是这样的：

```
Prometheus Alertmanager → Slack / Discord Webhook → 手机/桌面
```

看着简单，但踩坑点很多：

| 痛点 | 真实代价 |
|------|---------|
| Slack 免费版的 Webhook 机器人限流 | 高峰期漏告警，或需要付费升级（$7.25/人/月） |
| Discord Webhook 只能推到一个 channel | 多业务线要建多个 Bot，配置混乱 |
| 国内网络访问 Slack/Discord 不稳定 | 告警丢失 = 故障没被发现 |
| 每次出站 Webhook = 出口流量 | 按量计费 VPS 上长期跑 = 隐形成本 |
| 自建「推送」= 再写一遍多通道适配 | 时间成本比订阅费还贵 |

**核心思路**：在 VPS 上自托管一个轻量级告警推送中枢（**GoNotify** 架构：单二进制 + Web 管理界面 + Webhook 触发器），所有告警先打到你的 VPS（内网/Cloudflare Tunnel），由它统一分发到 Telegram、Email、钉钉、企业微信、飞书。结果：

- 出口流量走 **Cloudflare Tunnel 加密出站**，VPS 自身 `egress` 账单趋近 0；
- 所有通道配置集中在一个 Web UI，改一个地方全生效；
- 镜像仅 **7MB**，CPU <0.5%，内存 <20MB，1C1G VPS 轻松跑；
- 月省 $5-12（Slack/Discord 订阅 + 超额带宽费）。

## 一、架构图：告警流量如何「绕开」付费通道

```
                 ┌──────────────────────────────────────┐
                 │        VPS (1C1G, $4-6/mo)           │
                 │                                      │
 Alertmanager ──▶│  Cloudflare Tunnel (出站加密)        │──▶ Slack/Discord
 Watchtower    ──▶│  │                                  │
 自监控脚本    ──▶│  │  ┌─────────────────────────┐     │
                 │  └─▶│  GoNotify (7MB Docker)  │     │
 Grafana Hook  ──▶│     │  - Web UI (Port 8081)  │     │──▶ Telegram Bot
                 │     │  - Webhook Inlet        │     │──▶ Email (SMTP)
                 │     │  - Multi-Channel Router │     │──▶ 钉钉/飞书/企微
                 │     └─────────────────────────┘     │
                 └──────────────────────────────────────┘
```

关键点：**告警源头（Prometheus、Watchtower、脚本）不需要直连 Slack**——它们打到你 VPS 上的 GoNotify Webhook，由 GoNotify 内部做通道路由。这样只需为「VPS 自身」保留出站能力，且通过 Cloudflare Tunnel 加密走 CF 骨干网，不占 VPS 公网出口流量（按流量计费 VPS 的关键省钱点）。

## 二、5 分钟部署：一条 Docker 命令

### 1. 创建目录与 Docker Compose

```bash
sudo mkdir -p /opt/notify && cd /opt/notify

cat > docker-compose.yml << 'EOF'
version: "3.9"
services:
  gnotify:
    image: ghcr.io/gotify-server/gotify:latest   # 替换为你的 GoNotify 镜像
    container_name: gnotify
    restart: unless-stopped
    ports:
      - "127.0.0.1:8081:80"
    volumes:
      - ./data:/data
    environment:
      - GOTIFY_ADMIN=notify-admin
      - GOTIFY_ADMIN_PASSWORD=change-me-strong
    command: ["server", "--host", "0.0.0.0", "--port", "80"]
EOF
```

> 如果你的 GoNotify 是自建镜像，把 `image:` 换成 `docker build -t gnotify .` 后的本地名。

```bash
sudo docker compose up -d
sudo docker compose ps   # STATUS 应为 Up
```

### 2. 用 Cloudflare Tunnel 暴露（避免开公网 8081）

```bash
# 在 VPS 上安装 cloudflared（若未装）
sudo curl -L --output /usr/local/bin/cloudflared \
  https://github.com/cloudflare/cloudflared/releases/latest/linux-amd64-cloudflared

# 生成 Token 并启动
sudo cloudflared tunnel login
sudo cloudflared tunnel create gnotify
sudo cloudflared tunnel routing add gnotify http://127.0.0.1:8081
sudo cloudflared tunnel run gnotify
```

之后 `https://gnotify.yourdomain.com` 即可访问 Web UI，VPS 无需开放任何入站端口。

### 3. 初始化配置

浏览器打开 `https://gnotify.yourdomain.com`，登录后：

1. **应用** → 新建 `prometheus-alerts`，拿到 **App Token**（格式 `A1B2C3D4-...`）；
2. **Webhook 端点**：
   ```
   https://gnotify.yourdomain.com/webhook/prometheus-alerts
   ```
   （GoNotify 默认支持 `/webhook/<appname>` 路径，无需 App Token 也可，按需在路由层加鉴权）

## 三、通道适配：一次配置，全通道分发

GoNotify 的强项是 **内置多通道路由器**，你在 Web UI 里填一次参数，之后所有 App 的 Webhook 调用都会按你定义的规则分发：

### Telegram Bot（推荐，国内可用）

1. 找 `@BotFather` 创建 Bot，拿到 `token`（形如 `123456:ABC-DEF...`）；
2. 在 GoNotify 后台 → **Channels** → **Telegram** 中填入 `token` + 你的 `chat_id`（可用 `getUpdates` 拿到）；
3. 测试：

```bash
curl -X POST "https://gnotify.yourdomain.com/webhook/prometheus-alerts" \
  -H "Content-Type: application/json" \
  -d '{"title":"磁盘 90%","body":"/:85% + /var/log:3GB","priority":"high"}'
```

手机 10 秒内收到 Telegram 推送。

### 钉钉 / 飞书 / 企业微信

在对应 Channels 中填入 Webhook URL 即可（钉钉/飞书 Webhook 都是 `https://oapi.dingtalk.com/robot/send?access_token=xxx` 格式，GoNotify 原生支持）。

### 邮件（SMTP）

```
SMTP Server:  smtp.office365.com:587
User:         alerts@yourdomain.com
Auth:         app-password（非主密码）
```

## 四、Prometheus Alertmanager 联动（核心省钱点）

### 1. 创建独立 receiver 指向 GoNotify Webhook

```yaml
# /etc/prometheus/alertmanager.yml 新增
receivers:
  - name: "gnotify"
    webhook_configs:
      - url: "https://gnotify.yourdomain.com/webhook/prometheus-alerts"
        send_resolved: true
        max_samples: 200
```

### 2. 路由规则

```yaml
route:
  receiver: "gnotify"
  group_by: [alertname, instance]
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
  routes:
    - match:
        severity: "critical"
      receiver: "gnotify"          # 同一通道，GoNotify 内部按 severity 加 emoji/颜色
      repeat_interval: 1h         # critical 每 1h 重复
```

### 3. 验证链路

```bash
# 手动注入一条 critical 告警
curl -X POST http://localhost:9090/api/v2/alerts \
  -H "Content-Type: application/json" \
  -d '[{
    "labels":{"alertname":"DiskFull","severity":"critical","instance":"web-01"},
    "annotations":{"summary":"磁盘 /dev/sda1 使用率 92%"},
    "generatorURL":"http://web-01:9100/graph"
  }]'

# 30 秒后手机/钉钉应收到推送
```

## 五、成本与收益测算（1C1G VPS，$4/mo）

| 项目 | 之前（Slack 订阅） | 之后（自托管 GoNotify） | 月省 |
|------|:---:|:---:|:---:|
| 告警通道订阅 | $7.25（Slack 付费）或 $0（免费受限） | $0 | $0-7.25 |
| 出口流量（告警出站） | 每月 1-5GB × $0.10 | **≈0**（CF Tunnel 加密走 CF 骨干） | $0.10-0.50 |
| 多通道适配开发工时 | 2-4h 初始 + 持续维护 | 1h 配置，0 维护 | 时间成本 |
| 国内可达性 | 不稳定 | 钉钉/Telegram 全通 | 告警可靠性 |
| VPS 自身运行成本 | — | $4/mo（可复用已购 VPS） | $0（边际） |

**综合月省 $5-12 + 告警可靠性显著提升**，且所有告警数据归你所有（合规友好）。

## 六、进阶：告警去重、静默、批量

GoNotify 的 Web UI 内置：

- **去重窗口**：相同 App + title 的告警在 5 分钟内只推一次（避免 Prometheus 重复 firing）；
- **静默规则**：按 `instance` 标签静默（维护窗口期）；
- **批量摘要**：每 15 分钟把同类告警合并成一条摘要推送（`group_by=alertname`）。

示例静默（Web UI → Silence 或 API）：

```bash
curl -X POST "https://gnotify.yourdomain.com/api/v1/silences" \
  -H "Authorization: Bearer <app-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "matchers": [{"name":"instance","value":"web-01","isRegex":false}],
    "startsAt": "2026-11-10T02:00:00Z",
    "endsAt": "2026-11-10T04:00:00Z",
    "reason": "deploying"
  }'
```

## 七、常见坑与排障

| 症状 | 原因 | 处理 |
|------|------|------|
| Webhook 返回 401 | App 未激活或 Token 过期 | Web UI → Apps → 重新生成 Token |
| 告警延迟 >1min | Alertmanager `group_wait` + 通道限速 | 调低 `group_wait` 至 10s，或在 GoNotify 中开启「高优先级抢占」 |
| Telegram 推不出 | Bot 被 block / 网络 | `curl https://api.telegram.org/bot<token>/getMe` 验证 |
| CF Tunnel 断连 | cloudflared 进程挂 | `systemd` 托管 + `watchdog`（见下） |

```ini
# /etc/systemd/system/cloudflared.service
[Unit]
Description=Cloudflared tunnel for gnotify
After=network-online.target

[Service]
ExecStart=/usr/local/bin/cloudflared tunnel run gnotify
Restart=always
RestartSec=5
MemoryMax=200M

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now cloudflared
```

## 八、小结

| 能力 | 自托管 GoNotify | 付费 Slack/Discord |
|------|:---:|:---:|
| 多通道分发（TG/Email/钉钉/飞书） | ✅ 一次配置 | ❌ 每通道单独接 |
| 国内可达性 | ✅ | ⚠️ 不稳定 |
| 出口流量成本 | ≈0（CF Tunnel） | 按量 |
| 告警去重/静默/批量 | ✅ 内置 | 需自建 |
| 数据归属 | 你的 VPS | 厂商 |
| 初始工时 | ~30 分钟 | ~2h + 订阅费 |

**一句话**：告警不该被「订阅费」绑架。一台 1C1G VPS + 一个 7MB 容器 + Cloudflare Tunnel，就能把告警链路变成「内网触发 → 你 VPS 中枢 → 多通道分发」，月省 $5-12，且彻底告别出口流量账单。

## 下一步

- 给 GoNotify 加 **Prometheus 指标导出**（`/metrics`），纳入你自己的监控闭环；
- 用 `gotify-push` 命令行客户端，让 `crontab` 脚本直接 `gotify-push --app gnotify --title "备份完成" --body "OK"`；
- 进阶：把 GoNotify 作为 **Watchtower** 的告警出口（`WATCHTOWER_CLEANUP=true` + `WATCHTOWER_SLACK_ID` 替换为 GoNotify Webhook），实现「镜像自动更新 + 告警推送」全链路。
