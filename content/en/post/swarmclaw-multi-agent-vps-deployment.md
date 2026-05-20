---
title: "SwarmClaw Deployment Guide: Run a Self-Hosted Multi-Agent Orchestrator on Your VPS"
description: "Complete step-by-step guide to deploying SwarmClaw (500+ ⭐) on a VPS — a self-hosted AI agent runtime with multi-agent swarms, MCP tools, durable memory, 23+ LLM providers including Ollama, and Docker Compose setup for 24/7 operation"
date: 2026-05-20T21:30:00+08:00
slug: "swarmclaw-multi-agent-vps-deployment"
tags: ["SwarmClaw", "AI Agent", "multi-agent", "self-hosting", "VPS deployment", "Ollama", "Docker", "MCP", "orchestration"]
categories: ["AI Deployment"]
draft: false
---

## What is SwarmClaw?

[SwarmClaw](https://github.com/swarmclawai/swarmclaw) (500+ ⭐ on GitHub) is an **open-source, self-hosted AI agent runtime and multi-agent framework**. Think of it as your control plane for autonomous AI agents — it lets you run, orchestrate, and manage entire teams of AI agents on your own infrastructure.

Unlike single-agent tools like Claude Code or ChatGPT, SwarmClaw is designed for **multi-agent orchestration**:

- **Agent Swarms** — Create teams of agents (CEO, Developer, Researcher) that delegate tasks, collaborate, and report up through an org chart
- **23+ LLM Providers** — Connect to Ollama, Claude, GPT, Gemini, OpenRouter, DeepSeek, Groq, and more — mix and match models per agent
- **Durable Memory** — Hybrid recall with graph traversal, journaling, automatic reflection, and project-scoped context
- **MCP Server Support** — Attach any Model Context Protocol server for tools like web browsing, code execution, file access
- **Connectors** — Bridge agents to Discord, Slack, Telegram, WhatsApp, email, and Matrix
- **Schedules & Heartbeats** — Agents run on schedules, check in autonomously, and surface blockers
- **Runtime Skills** — Agents learn from conversations and create reusable skills

The killer feature for VPS users: **SwarmClaw runs in a single Docker container** with persistent storage, connects to **local Ollama models** for privacy, and gives you a **web UI dashboard** at `http://your-vps:3456` to manage your entire agent fleet.

---

## VPS Resource Recommendations

SwarmClaw is a Node.js application that serves as the orchestration layer — the heavy LLM inference runs on external providers or a separate Ollama instance. This means it's quite lightweight.

### Minimum Specs
| Resource | Requirement | Notes |
|----------|-------------|-------|
| **CPU** | 1 core (x86_64 / ARM64) | ARM works fine |
| **RAM** | 1 GB | 512 MB usable after base OS |
| **Disk** | 10 GB | Includes OS + SwarmClaw + Docker images |
| **Network** | Public IP with ports 3456-3457 open | For web UI and API access |

### Recommended Specs
| Resource | Requirement | Notes |
|----------|-------------|-------|
| **CPU** | 2 cores | Needed if running Ollama alongside |
| **RAM** | 4 GB | 2 GB for SwarmClaw, 2 GB for Ollama models |
| **Disk** | 20 GB SSD | For agent data + local models |
| **Network** | Any public IP | 1 Mbps is sufficient for API traffic |

### With Ollama (Local LLM Inference)
| Resource | Requirement | Notes |
|----------|-------------|-------|
| **CPU** | 4+ cores | For running 7B models without GPU |
| **RAM** | 8-16 GB | Qwen2.5:7B-Q4 needs ~6 GB, Gemma 3:12B needs ~8 GB |
| **GPU** | Optional | NVIDIA T4 or better for faster inference |
| **Disk** | 30+ GB SSD | Models are 4-8 GB each |

---

## Step 1: VPS Preparation

First, SSH into your VPS and install Docker and Docker Compose:

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Install Docker Compose plugin
sudo apt install -y docker-compose-plugin

# Add your user to docker group
sudo usermod -aG docker $USER

# Log out and back in, or use newgrp
newgrp docker

# Verify
docker --version && docker compose version
```

---

## Step 2: Deploy SwarmClaw via Docker Compose

```bash
# Create the project directory
mkdir -p ~/swarmclaw && cd ~/swarmclaw

# Create persistent data directory
mkdir -p data

# Create the docker-compose.yml
cat > docker-compose.yml << 'EOF'
services:
  swarmclaw:
    image: ghcr.io/swarmclawai/swarmclaw:latest
    ports:
      - "3456:3456"
      - "3457:3457"
    volumes:
      - ./data:/app/data
    environment:
      - ACCESS_KEY=your-secure-access-key-here
      - CREDENTIAL_SECRET=your-credential-secret-here
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:3456/api/healthz"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 10s
    restart: unless-stopped
EOF
```

> **Security**: Generate strong random values for `ACCESS_KEY` and `CREDENTIAL_SECRET`:
> ```bash
> openssl rand -base64 32  # For ACCESS_KEY
> openssl rand -base64 32  # For CREDENTIAL_SECRET
> ```

Now start the container:

```bash
docker compose up -d
```

Wait a few seconds, then verify it's running:

```bash
docker compose ps
curl -s http://localhost:3456/api/healthz | head -c 200
```

You should see `{"status":"ok"}`. Open `http://your-vps-ip:3456` in your browser and log in with `ACCESS_KEY` as the password.

---

## Step 3: Configure HTTPS with Traefik (Production)

For production use, protect your SwarmClaw dashboard behind HTTPS. Here's a quick Traefik setup:

```yaml
# docker-compose.yml — add Traefik reverse proxy
services:
  traefik:
    image: traefik:v3.2
    command:
      - "--providers.docker=true"
      - "--entrypoints.websecure.address=:443"
      - "--entrypoints.web.address=:80"
      - "--certificatesresolvers.letsencrypt.acme.tlschallenge=true"
      - "--certificatesresolvers.letsencrypt.acme.email=your@email.com"
      - "--certificatesresolvers.letsencrypt.acme.storage=/letsencrypt/acme.json"
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - "/var/run/docker.sock:/var/run/docker.sock:ro"
      - "./letsencrypt:/letsencrypt"

  swarmclaw:
    image: ghcr.io/swarmclawai/swarmclaw:latest
    expose:
      - "3456"
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.swarmclaw.rule=Host(`swarmclaw.yourdomain.com`)"
      - "traefik.http.routers.swarmclaw.entrypoints=websecure"
      - "traefik.http.routers.swarmclaw.tls.certresolver=letsencrypt"
    volumes:
      - ./data:/app/data
    environment:
      - ACCESS_KEY=your-secure-access-key
      - CREDENTIAL_SECRET=your-credential-secret
    restart: unless-stopped
```

---

## Step 4: Connect Ollama for Local LLM Inference

To run models entirely on your VPS without external API calls, deploy Ollama alongside SwarmClaw.

### Option A: Docker Compose (sidecar container)

Add to your `docker-compose.yml`:

```yaml
  ollama:
    image: ollama/ollama:latest
    ports:
      - "11434:11434"
    volumes:
      - ./ollama_data:/root/.ollama
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]  # Remove if no GPU
    restart: unless-stopped
```

Pull a model:

```bash
docker compose exec ollama ollama pull qwen2.5:7b
# or for smaller VPS:
docker compose exec ollama ollama pull phi-4:3.8b-mini-instruct-q4_K_M
```

### Option B: Standalone Ollama on host (better performance)

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull a model
ollama pull qwen2.5:7b

# Verify
ollama list
```

### Configure SwarmClaw to Use Ollama

In the SwarmClaw web UI:
1. Go to **Settings → Providers**
2. Add a new provider: **Ollama**
3. Set the base URL to `http://ollama:11434` (Docker sidecar) or `http://host.docker.internal:11434` (host install)
4. Select models like `qwen2.5:7b`, `llama3.2:3b`, or `gemma3:12b`

---

## Step 5: Create Your First Agent

Once SwarmClaw is running and connected to a provider:

1. Open the dashboard at `http://your-vps:3456`
2. Click **Create Agent**
3. Give it a name (e.g., "DevAssistant")
4. Select the provider (Ollama or OpenRouter)
5. Choose a model
6. Enable tools: Shell, Files, Web Search
7. Click Save

Your agent is now ready. You can:
- Chat with it directly in the web UI
- Assign it tasks via the task board
- Set up a schedule for recurring work
- Connect it to Telegram/Slack for on-the-go access

---

## Step 6: Building a Multi-Agent Team (Org Chart)

SwarmClaw's superpower is multi-agent orchestration. Here's how to create a virtual development team:

1. **Create the agents**:

| Agent | Role | Provider | Model | Tools |
|-------|------|----------|-------|-------|
| Lead | Architect | OpenRouter | claude-sonnet-4 | Delegation, Tasks |
| Dev | Builder | Ollama | qwen2.5:7b | Shell, Files |
| QA | Tester | Ollama | llama3.2:3b | Shell, Browser |
| Reviewer | Critic | OpenRouter | gpt-4o-mini | Files, Web Search |

2. **Set up the org chart**:
   - Go to the **Org Chart** view
   - Drag agents to define hierarchy
   - The Lead delegates tasks; Dev, QA, and Reviewer pick up work

3. **Create a task**:
   - Click **Tasks → New Task**
   - Title: "Implement user authentication module"
   - Assign to Lead
   - The Lead breaks it down and delegates to Dev

4. **Watch the swarm work**:
   - The org chart shows live agent activity
   - Each agent's status updates in real-time
   - Completed work flows back up the chain for review

---

## Step 7: Connect MCP Servers for Extended Tools

Model Context Protocol (MCP) servers add powerful capabilities to your agents.

### Example: MCP Server for Filesystem Access

```bash
# Inside the swarmclaw container or on host
docker run -d \
  --name mcp-filesystem \
  -v /path/to/projects:/projects \
  ghcr.io/modelcontextprotocol/filesystem-server /projects
```

Then in SwarmClaw:
1. Go to **Settings → MCP Servers**
2. Click **Add MCP Server**
3. Choose type: **SSE** or **Streamable HTTP**
4. Enter the endpoint URL
5. Enable the tools for specific agents

Popular MCP servers to try:
- **Filesystem** — Read, write, and manage files
- **GitHub** — Create PRs, manage issues, browse repos
- **Puppeteer** — Browser automation and screenshots
- **SQLite** — Query databases
- **Memory** — Persistent knowledge graph

---

## Step 8: Production Best Practices

### Data Persistence

All SwarmClaw data lives in `./data/`. Back it up regularly:

```bash
# Backup
tar -czf swarmclaw-backup-$(date +%Y%m%d).tar.gz data/

# Or use a cron job
0 3 * * * cd ~/swarmclaw && tar -czf backups/swarmclaw-$(date +\%Y\%m\%d).tar.gz data/
```

### Resource Limits

Prevent SwarmClaw from consuming all VPS resources:

```yaml
services:
  swarmclaw:
    deploy:
      resources:
        limits:
          memory: 1G
          cpus: "1"
```

### Monitoring

SwarmClaw supports OpenTelemetry OTLP export:

```bash
OTEL_ENABLED=true
OTEL_SERVICE_NAME=swarmclaw
OTEL_EXPORTER_OTLP_ENDPOINT=https://your-collector:4318
```

### Updates

```bash
cd ~/swarmclaw
docker compose pull
docker compose up -d
```

---

## Real-World Use Cases

### Personal AI Assistant
A single agent with memory, web access, scheduling, and file tools — your always-available copilot. Connect it to Telegram to message your agent on the go. Have it check your server health, summarize articles, manage your calendar, and draft emails.

### Automated DevOps Engineer
Build an agent that monitors your VPS, checks logs for errors, runs backups on schedule, and alerts you via Telegram when something needs attention. Connect it to shell tools for full server control.

### Content Generation Pipeline
Create two agents: a Writer that drafts blog posts based on briefs, and an Editor that tightens structure and tone. Schedule daily content runs with automatic handoff between agents.

### Customer Support Desk
Bridge a support agent to Discord, Slack, and Telegram simultaneously. The agent remembers each user's history and escalates complex issues via task delegation to a specialist agent.

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Container won't start | Check `docker compose logs` for errors |
| Can't access web UI | Verify ports 3456/3457 are open in firewall |
| Ollama not connecting | Ensure Ollama is running and accessible from SwarmClaw container (`http://ollama:11434`) |
| Agent refuses tasks | Check the agent has the necessary tools enabled |
| Memory not persisting | Verify `./data/` directory has correct permissions |
| MCP server not found | Check the MCP server URL is reachable from the SwarmClaw container |

---

## Summary

SwarmClaw brings **enterprise-grade multi-agent orchestration** to your personal VPS. In under 10 minutes, you can have a fully functional AI agent runtime running with:

- 🐳 **Single Docker Compose deployment**
- 🏠 **Local Ollama models** for complete privacy
- 🔗 **23+ LLM providers** — mix and match per agent
- 🧠 **Durable agent memory** that persists across sessions
- 🔌 **MCP tool ecosystem** for unlimited capabilities
- 📊 **Web dashboard** to manage your entire agent fleet

Whether you're building a personal assistant, a dev team, or a customer support desk, SwarmClaw gives you the control plane to wire it all together on your own infrastructure.

**Start building your agent swarm today — all you need is a VPS and 10 minutes.**

---

*Related: [Hermes Agent Deployment Guide](/post/hermes-agent-vps-deployment/) | [Deploying Open-Source AI Tools on a VPS](/post/deploying-open-source-ai-tools/) | [n8n AI Workflow Deployment Guide](/post/n8n-deployment-guide/)*
