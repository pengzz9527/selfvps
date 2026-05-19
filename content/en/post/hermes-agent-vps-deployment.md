---
title: "Hermes Agent Deployment Guide: Run a Self-Improving AI Agent on Your VPS"
description: "Step-by-step guide to deploying Hermes Agent (156K+ ⭐) on a VPS — including VPS resource recommendations, one-command install, Telegram gateway setup, and production tips for 24/7 operation"
date: 2026-05-19T21:30:00+08:00
slug: "hermes-agent-vps-deployment"
tags: ["Hermes Agent", "AI Agent", "Nous Research", "VPS deployment", "self-hosting", "Telegram", "Docker", "automation"]
categories: ["AI Deployment"]
draft: false
---

## What is Hermes Agent?

[Hermes Agent](https://github.com/NousResearch/hermes-agent) (156K+ ⭐ on GitHub) is the self-improving AI agent built by [Nous Research](https://nousresearch.com). Unlike conventional AI assistants that start fresh every session, Hermes has a built-in **learning loop**:

- **Persistent memory**: Saves facts about you across sessions — preferences, environment quirks, project conventions
- **Autonomous skill creation**: After complex tasks, it creates reusable skills so next time it does it better
- **Cross-session search**: Can recall past conversations using FTS5 full-text search with LLM summarization
- **Platform-agnostic**: Use the CLI locally, or talk to it from Telegram, Discord, Slack, WhatsApp, Signal, and Email through a single gateway process
- **Any model**: Switch between 200+ models from OpenRouter, OpenAI, Nous Portal, Hugging Face, or local endpoints — `hermes model` changes providers without code changes
- **Scheduled automations**: Built-in cron scheduler for daily reports, nightly backups, automated publishing
- **Subagent delegation**: Spawn parallel workers for complex multi-step tasks

The killer feature for VPS users: **it runs on a $5 VPS** and you can chat with it from your phone via Telegram while it works on the server.

---

## VPS Resource Recommendations

Hermes Agent is lightweight compared to running LLM inference locally. Since it connects to external AI providers (OpenRouter, OpenAI, etc.), almost all the heavy lifting happens on the API side — the VPS just needs to run the agent process, tools, and optionally the messaging gateway.

### Minimum Specs
| Resource | Requirement | Notes |
|----------|-------------|-------|
| **CPU** | 1 core (x86_64 / ARM64) | ARM works fine (e.g., Oracle free tier) |
| **RAM** | 1 GB | 512 MB usable after base OS |
| **Disk** | 5 GB | Includes OS + Hermes + tools |
| **Network** | Any public IP | 1 Mbps is enough for CLI/API traffic |

### Recommended Specs
| Resource | Requirement | Notes |
|----------|-------------|-------|
| **CPU** | 2 cores | Smoother multi-tasking |
| **RAM** | 2 GB | Room for cron jobs + gateway + browser tools |
| **Disk** | 20 GB | Space for downloaded files, cloned repos, skills cache |
| **Network** | 100 Mbps | Faster git clones, API responses |

### Best VPS Providers for Hermes Agent

| Provider | Price | Specs | Best For |
|----------|-------|-------|----------|
| **Hetzner** | €3.99/mo (CX22) | 2 vCPU, 4GB RAM, 40GB | Best value — use this |
| **Oracle Cloud Free Tier** | Free | 4 ARM cores, 24GB RAM | If you can get approved |
| **DigitalOcean** | $6/mo | 1 vCPU, 1GB RAM, 25GB | Simple setup |
| **Vultr** | $6/mo | 1 vCPU, 1GB RAM, 25GB | Global datacenter options |
| **RackNerd** | $1.50/mo | 1 vCPU, 1GB RAM, 20GB | Cheapest option |
| **BuyVM** | $3.50/mo | 1 vCPU, 1GB RAM, 20GB | Good for media tools |

**Our pick:** Hetzner CX22 (€3.99/mo) or the Oracle Cloud Free Tier if you can get an account.

---

## Step-by-Step Deployment

### 1. Provision Your VPS

Choose Ubuntu 22.04 or 24.04 LTS. Once your VPS is ready, SSH in:

```bash
ssh root@your-vps-ip
```

### 2. Install System Dependencies

```bash
apt update && apt upgrade -y
apt install -y curl git ffmpeg build-essential
```

### 3. Install Hermes Agent

One command, runs in under a minute:

```bash
curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash
source ~/.bashrc
```

The installer handles:
- **uv** (Python package manager, much faster than pip)
- Python 3.11
- Node.js (for some tools)
- ripgrep (for session search)
- ffmpeg (for audio/video processing)
- All Python dependencies

### 4. Verify the Installation

```bash
hermes doctor
```

This checks everything is set up correctly. You should see green checkmarks across the board.

### 5. Configure Your Model Provider

Set up an API key and choose a provider:

```bash
hermes model
```

For a free option, you can use some OpenRouter models with their free tier. For the best experience, add a paid API key:

```bash
hermes config set provider openrouter
hermes config set openrouter_api_key sk-or-v1-xxx
hermes model openrouter/anthropic/claude-sonnet-4
```

### 6. Set Up the Telegram Gateway (Optional but Recommended)

This is the most practical way to use Hermes on a VPS — install it once, then control it from your phone:

```bash
hermes gateway setup
# Follow the prompts to create a Telegram bot via @BotFather
# Configure: gateway.providers.telegram.bot_token
hermes gateway start
```

Now you can message your bot on Telegram and Hermes will respond. The gateway process runs in the background on your VPS.

### 7. Run Hermes in the CLI

```bash
hermes
```

The TUI (terminal user interface) starts. You can now chat with Hermes, create skills, schedule cron jobs, and more.

---

## Production Tips for 24/7 Operation

### Use a Process Manager

Don't use `nohup` or `&` — use `tmux` or `screen` to keep the session alive:

```bash
tmux new -s hermes
hermes
# Ctrl+B, D to detach
tmux attach -t hermes  # Reattach later
```

### Set Up the Gateway to Auto-Start

Add to crontab:

```bash
crontab -e
# Add:
@reboot cd /root && hermes gateway start &
```

### Enable SSH Backend

If you want to run Hermes from your laptop but have it work on the VPS:

```bash
hermes config set terminal.backend ssh
hermes config set terminal.ssh_host your-vps-ip
```

This way, Hermes runs on your local machine but executes all commands on the VPS.

### Monitor Resource Usage

```bash
htop                    # Real-time CPU/RAM
df -h                   # Disk usage
hermes usage            # Token usage within Hermes
```

---

## Deploying with Docker (Alternative)

If you prefer Docker, Hermes can run in a container:

```bash
docker run -it --rm \
  -v ~/.hermes:/root/.hermes \
  ghcr.io/nousresearch/hermes-agent
```

But for a VPS, the native install is simpler and uses fewer resources.

---

## Summary

| Aspect | Detail |
|--------|--------|
| Install time | ~30 seconds |
| Disk usage after install | ~800 MB |
| RAM at idle | ~150 MB |
| RAM during conversation | ~300-500 MB |
| Best VPS | Hetzner CX22 (€3.99/mo) |
| Remote access | Telegram / Discord gateway |
| Cron jobs | Built-in scheduler |

Hermes Agent is one of the most practical AI agents to run on a VPS because of its low resource footprint, the ability to control it remotely via messaging platforms, and its built-in cron scheduler for automation. Deploy it once and you have a 24/7 AI assistant that learns and improves over time.
