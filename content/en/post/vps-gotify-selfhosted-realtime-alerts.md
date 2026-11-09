---
title: "Self-Host GoNotify: Run a 7MB Real-Time Alert Pusher on Your VPS, $0 Subscription"
description: "Slack/Discord alert webhooks cost money or have limits. This guide shows how to self-host a GoNotify-style real-time alert pusher on a 1C1G VPS: single-line Webhook config, Telegram/Email/DingTalk all wired, Docker image just 7MB, CPU under 0.5%. Includes a full Prometheus Alertmanager integration example, saves $5-12/month in subscriptions, and eliminates one public egress channel at the same time."
date: 2026-11-09T12:00:00+08:00
lastmod: 2026-11-09T12:00:00+08:00
slug: "vps-gotify-selfhosted-realtime-alerts"
image: /images/posts/vps-gotify-selfhosted-realtime-alerts/featured.png
tags: ["VPS", "Alerting", "Self-Hosted", "Docker", "GoNotify", "Prometheus", "Telegram", "Webhook", "Cost Saving", "DevOps"]
categories: ["VPS Cost & Ops", "Self-Hosting"]
aliases: ["/en/post/vps-gotify-selfhosted-realtime-alerts/"]
draft: false
---

## Introduction: Why Alerting Channels Always Start With a Bill

Most people's alert pipeline looks like this:

```
Prometheus Alertmanager → Slack / Discord Webhook → phone/desktop
```

It looks simple, but the pitfalls are numerous:

| Pain Point | Real Cost |
|------|---------|
| Slack free-tier Webhook bot is rate-limited | Missed alerts at peak, or pay for the upgrade ($7.25/user/mo) |
| Discord Webhook can only push to one channel | Multiple business lines need multiple Bots, config chaos |
| Unreliable access to Slack/Discord from China | Lost alerts = undetected incidents |
| Every outbound Webhook = egress traffic | On metered VPS, this becomes a silent ongoing cost |
| Building your own "pusher" = re-implementing multi-channel adapters | Time cost exceeds the subscription fee |

**Core idea**: self-host a lightweight alert push hub (**GoNotify** architecture: single binary + web admin UI + Webhook trigger) on your VPS. All alerts land on your VPS (via internal network / Cloudflare Tunnel), and it fans out to Telegram, Email, DingTalk, WeCom, and Feishu. The result:

- Egress goes through **Cloudflare Tunnel encrypted outbound**, your VPS `egress` bill approaches 0;
- All channel configs live in one web UI — change one place, applies everywhere;
- Image is only **7MB**, CPU <0.5%, memory <20MB — runs fine on a 1C1G VPS;
- Saves $5-12/month (Slack/Discord subscription + overage bandwidth).

## 1. Architecture: How Alert Traffic "Skips" the Paid Channels

```
                 ┌──────────────────────────────────────┐
                 │        VPS (1C1G, $4-6/mo)           │
                 │                                      │
 Alertmanager ──▶│  Cloudflare Tunnel (outbound crypto) │──▶ Slack/Discord
 Watchtower    ──▶│  │                                  │
 monitoring scr ─▶│  │  ┌─────────────────────────┐     │
                 │  └─▶│  GoNotify (7MB Docker)   │     │
 Grafana Hook   ──▶│     │  - Web UI (Port 8081)  │     │──▶ Telegram Bot
                 │     │  - Webhook Inlet         │     │──▶ Email (SMTP)
                 │     │  - Multi-Channel Router  │     │──▶ DingTalk/Feishu/WeCom
                 │     └─────────────────────────┘     │
                 └──────────────────────────────────────┘
```

The key point: **alert sources (Prometheus, Watchtower, scripts) don't connect to Slack directly** — they hit the GoNotify Webhook on your VPS, and GoNotify routes to channels internally. That way only "the VPS itself" keeps outbound capability, and via Cloudflare Tunnel over CF's backbone, it does not consume your VPS's public egress (the critical cost-saver on metered VPS).

## 2. 5-Minute Deploy: One Docker Command

### 1. Create directory and Docker Compose

```bash
sudo mkdir -p /opt/notify && cd /opt/notify

cat > docker-compose.yml << 'EOF'
version: "3.9"
services:
  gnotify:
    image: ghcr.io/gotify-server/gotify:latest   # replace with your GoNotify image
    container_name: gnotify
    restart: unless-stopped
    ports:
      - "127.0.0.1:8081:80"
    volumes:
      - ./data:/data
    environment:
      - GOTIFY_ADMIN=notify-admin
      - GOTIFY_ADMIN_PASSWORD=change...ng
    command: ["server", "--host", "0.0.0.0", "--port", "80"]
EOF
```

> If GoNotify is a self-built image, swap `image:` for the local name after `docker build -t gnotify .`.

```bash
sudo docker compose up -d
sudo docker compose ps   # STATUS should be Up
```

### 2. Expose via Cloudflare Tunnel (avoid opening public 8081)

```bash
# Install cloudflared on the VPS (if not already)
sudo curl -L --output /usr/local/bin/cloudflared \
  https://github.com/cloudflare/cloudflared/releases/latest/linux-amd64-cloudflared

# Generate token and start
sudo cloudflared tunnel login
sudo cloudflared tunnel create gnotify
sudo cloudflared tunnel routing add gnotify http://127.0.0.1:8081
sudo cloudflared tunnel run gnotify
```

Now `https://gnotify.yourdomain.com` reaches the web UI, with no inbound ports open on the VPS.

### 3. Initialize Config

Open `https://gnotify.yourdomain.com` in browser, log in, then:

1. **Apps** → create `prometheus-alerts`, get the **App Token** (format `A1B2C3D4-...`);
2. **Webhook endpoint**:
   ```
   https://gnotify.yourdomain.com/webhook/prometheus-alerts
   ```
   (GoNotify supports `/webhook/<appname>` by default; no App Token needed unless you add auth at the routing layer)

## 3. Channel Adapters: One Config, Fan-Out Everywhere

GoNotify's strength is the **built-in multi-channel router** — fill parameters once in the web UI, then every app's Webhook call fans out according to your rules:

### Telegram Bot (recommended, works in China)

1. Talk to `@BotFather`, create a bot, get the `token` (like `123456:ABC-DEF...`);
2. In GoNotify admin → **Channels** → **Telegram**, fill `token` + your `chat_id` (use `getUpdates` to obtain it);
3. Test:

```bash
curl -X POST "https://gnotify.yourdomain.com/webhook/prometheus-alerts" \
  -H "Content-Type: application/json" \
  -d '{"title":"Disk 90%","body":"/:85% + /var/log:3GB","priority":"high"}'
```

Your phone should receive a Telegram push within 10 seconds.

### DingTalk / Feishu / WeCom

Fill the Webhook URL in the corresponding Channels (DingTalk/Feishu Webhooks are `https://oapi.dingtalk.com/robot/send?access_token=xxx` style, natively supported by GoNotify).

### Email (SMTP)

```
SMTP Server:  smtp.office365.com:587
User:         alerts@yourdomain.com
Auth:         app-password (not the main password)
```

## 4. Prometheus Alertmanager Integration (the Core Cost-Saver)

### 1. Create a dedicated receiver pointing to GoNotify Webhook

```yaml
# /etc/prometheus/alertmanager.yml, add
receivers:
  - name: "gnotify"
    webhook_configs:
      - url: "https://gnotify.yourdomain.com/webhook/prometheus-alerts"
        send_resolved: true
        max_samples: 200
```

### 2. Routing Rules

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
      receiver: "gnotify"          # same channel; GoNotify adds emoji/color by severity internally
      repeat_interval: 1h         # critical repeats every 1h
```

### 3. Verify the Pipeline

```bash
# Inject a critical alert manually
curl -X POST http://localhost:9090/api/v2/alerts \
  -H "Content-Type: application/json" \
  -d '[{
    "labels":{"alertname":"DiskFull","severity":"critical","instance":"web-01"},
    "annotations":{"summary":"Disk /dev/sda1 at 92%"},
    "generatorURL":"http://web-01:9100/graph"
  }]'

# Within 30s your phone/DingTalk should receive the push
```

## 5. Cost & Benefit (1C1G VPS, $4/mo)

| Item | Before (Slack Sub) | After (Self-Hosted GoNotify) | Monthly Save |
|------|:---:|:---:|:---:|
| Alert channel subscription | $7.25 (Slack paid) or $0 (free w/ limits) | $0 | $0-7.25 |
| Egress traffic (alert outbound) | 1-5GB/mo × $0.10 | **≈0** (CF Tunnel over CF backbone) | $0.10-0.50 |
| Multi-channel adapter dev hours | 2-4h initial + ongoing | 1h config, 0 maintenance | Time cost |
| China reachability | Unstable | DingTalk/Telegram all green | Alert reliability |
| VPS itself running cost | — | $4/mo (reuse existing VPS) | $0 (marginal) |

**Net: $5-12/mo saved + significantly improved alert reliability**, and all alert data stays under your control (compliance-friendly).

## 6. Advanced: Dedup, Silence, Batch

GoNotify's web UI has built-in:

- **Dedup window**: same App + title alerts dedup within 5 minutes (avoid Prometheus re-firing);
- **Silence rules**: silence by `instance` label (maintenance windows);
- **Batch digest**: every 15 minutes merge same-kind alerts into one digest (`group_by=alertname`).

Example silence (Web UI → Silence, or API):

```bash
curl -X POST "https://gnotify.yourdomain.com/api/v1/silences" \
  -H "Authorization: Bearer *** \
  -H "Content-Type: application/json" \
  -d '{
    "matchers": [{"name":"instance","value":"web-01","isRegex":false}],
    "startsAt": "2026-11-10T02:00:00Z",
    "endsAt": "2026-11-10T04:00:00Z",
    "reason": "deploying"
  }'
```

## 7. Common Pitfalls & Troubleshooting

| Symptom | Cause | Fix |
|------|------|------|
| Webhook returns 401 | App not active or Token expired | Web UI → Apps → regenerate Token |
| Alert latency >1min | Alertmanager `group_wait` + channel rate-limit | Lower `group_wait` to 10s, or enable "high-priority preemption" in GoNotify |
| Telegram not pushing | Bot blocked / network | `curl https://api.telegram.org/bot<token>/getMe` to verify |
| CF Tunnel disconnects | cloudflared process died | `systemd` management + `watchdog` (below) |

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

## 8. Summary

| Capability | Self-Hosted GoNotify | Paid Slack/Discord |
|------|:---:|:---:|
| Multi-channel fan-out (TG/Email/DingTalk/Feishu) | ✅ one config | ❌ per-channel wiring |
| China reachability | ✅ | ⚠️ unstable |
| Egress traffic cost | ≈0 (CF Tunnel) | metered |
| Alert dedup/silence/batch | ✅ built-in | must DIY |
| Data ownership | your VPS | vendor |
| Initial effort | ~30 min | ~2h + subscription |

**One line**: alerts shouldn't be held hostage by a subscription. One 1C1G VPS + one 7MB container + Cloudflare Tunnel turns your alerting pipeline into "internal trigger → your VPS hub → multi-channel fan-out", saving $5-12/mo and killing the egress bill entirely.

## Next Steps

- Add **Prometheus metrics export** to GoNotify (`/metrics`), closing the loop into your own monitoring;
- Use the `gotify-push` CLI so `crontab` scripts can just `gotify-push --app gnotify --title "backup done" --body "OK"`;
- Advanced: point **Watchtower** at GoNotify (`WATCHTOWER_CLEANUP=true` + swap `WATCHTOWER_SLACK_ID` for the GoNotify Webhook), achieving "image auto-update + alert push" in one chain.
