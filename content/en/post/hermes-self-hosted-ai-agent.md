---
title: "€4/Month, Your Own Private AI Agent: Hermes Self-Hosting Guide"
description: "In a world where ChatGPT costs $200/mo, you can self-host Hermes Agent on a €3.99 VPS — your data stays on your server, it runs 24/7, and you control it from Telegram. Full deployment guide included."
date: 2026-05-22T18:00:00+08:00
slug: "hermes-self-hosted-ai-agent"
tags: ["Hermes Agent", "AI Agent", "self-hosting", "VPS deployment", "open-source", "privacy", "Telegram"]
categories: ["AI Deployment"]
draft: false
---

## Why Self-Host an AI Agent?

Pasting code into ChatGPT to debug? That code might become training data. Letting an AI operate your server remotely? You're handing over root access to a third party.

[Hermes Agent](https://github.com/NousResearch/hermes-agent) (156K+ ⭐ on GitHub) is an open-source AI agent framework by [Nous Research](https://nousresearch.com). Install it on your own VPS, and every conversation, memory, and skill file stays on your server — no third party ever touches it.

Open source + self-hosted = your data, your rules.

## Cost Breakdown

A Hetzner CX22 (€3.99/mo, 2 vCPU / 4GB RAM / 40GB SSD) is plenty. Or go cheaper with RackNerd at $1.50/mo (1 core / 1GB).

API costs depend on usage. For daily coding, DeepSeek V3 ($0.27/M input tokens) runs about $20-30/mo with heavy use. **You only pay for compute, not a subscription fee.**

For reference: ChatGPT Plus is $20/mo (no self-hosting), Claude Pro is $20/mo (no self-hosting).

## Deployment Steps

### 1. Get a VPS

Hetzner CX22 (€3.99/mo), Ubuntu 24.04. Oracle Cloud free ARM tier works too.

> For users in Asia/Pacific: RackNerd $1.50/mo or BuyVM $3.50/mo are solid alternatives.

### 2. Install Dependencies

```bash
ssh root@your-vps-ip

apt update && apt upgrade -y
apt install -y curl git ffmpeg build-essential
```

`ffmpeg` is needed if you plan to generate video/audio via cron jobs.

### 3. Install Hermes Agent

```bash
curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash
source ~/.bashrc
```

The installer handles: uv (fast Python package manager), Python 3.11, Node.js, ripgrep (session search), and all Python dependencies. Takes about 30 seconds.

### 4. Verify

```bash
hermes doctor
```

All green? Good. Red errors are usually missing system packages — just `apt install` them.

### 5. Configure a Model

```bash
hermes model
```

Interactive picker, or set directly:

```bash
hermes config set provider openrouter
hermes config set openrouter_api_key sk-or-v1-your-key
hermes model openrouter/anthropic/claude-sonnet-4
```

**Budget option:** DeepSeek V3, Qwen 2.5, or Llama 3 — capable enough for coding, much cheaper.

### 6. Set Up the Telegram Gateway (Recommended)

Install it once, then control Hermes from your phone:

```bash
hermes gateway setup
```

Follow the prompts:
1. Open Telegram, search @BotFather
2. `/newbot` to create a bot, pick a name
3. Copy the Bot Token, paste it in

```bash
hermes gateway start
```

Now message your bot — Hermes responds instantly.

## Keeping It Running 24/7

### Option A: crontab (simplest)

```bash
crontab -e
# Add:
@reboot cd /root && hermes gateway start &
```

### Option B: systemd service (more reliable)

```ini
# /etc/systemd/system/hermes-gateway.service
[Unit]
Description=Hermes Gateway
After=network.target

[Service]
ExecStart=/root/.hermes/hermes-agent/venv/bin/python -m hermes_cli.main gateway run
WorkingDirectory=/root
Restart=always
User=root

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable --now hermes-gateway
```

Go with Option B. `Restart=always` means the process auto-recovers if it crashes — crontab can't do that.

## Post-Deployment FAQ

### Gateway won't start

Check `~/.hermes/logs/gateway.log`. 90% of the time it's a bad Bot Token — re-run `hermes gateway setup`.

### Not enough RAM

On a 1GB VPS, Hermes + browser tools can OOM. Disable what you don't need:

```bash
hermes tools disable browser
hermes tools disable vision
```

With only terminal / file / web enabled, memory usage drops below 200MB.

### ARM architecture (Oracle free tier)

The installer handles ARM compatibility automatically. Some Python packages may need compilation — initial setup takes a bit longer.

### Model API timeouts

Free-tier OpenRouter models time out frequently. Switch to a paid model or bump the timeout:

```bash
hermes config set agent.max_turns 120
```

### How to update

```bash
hermes update
```

Then `/restart` or restart the gateway.

## Disk Management

Hermes saves session logs by default. Over time this can grow to several GB:

```bash
hermes sessions prune --older-than 30
```

Or set auto-cleanup in config.yaml:

```yaml
sessions:
  retention_days: 30
```

## What's Next

You now have a 24/7 AI agent that respects your privacy. What can it actually do for you?

**This is Part 1 of a series. Coming up:**

- **Part 2:** Auto-publishing blog posts with Hermes — from writing to Git push
- **Part 3:** Server monitoring with Hermes — alerts, log analysis, auto-remediation
- **Part 4:** Running a Telegram channel with Hermes — scheduled posts, trending curation, rewriting
- **Part 5:** Data ETL pipelines with Hermes — collect, clean, store

The core idea: **The most valuable use of an AI agent isn't chatting in the cloud — it's working on your own infrastructure.**

See you in Part 2.

---

*Series index: [Part 2: Auto-publishing blog posts with Hermes]() (coming soon)*
