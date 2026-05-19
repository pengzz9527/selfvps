---
title: "Deploy Khoj: Your AI Second Brain on a VPS"
description: "Step-by-step guide to self-hosting Khoj — the open-source AI second brain — on your VPS with Docker. Connect local LLMs via Ollama, enable web search, and build custom AI agents."
date: 2026-05-19T12:00:00+08:00
slug: "deploy-khoj-ai-second-brain-vps"
tags: ["Khoj", "AI", "self-hosting", "Ollama", "RAG", "Docker", "VPS deployment", "AI agent", "open-source"]
categories: ["AI Deployment"]
draft: false
---

## What is Khoj?

[Khoj](https://khoj.dev) is an open-source, self-hostable **AI second brain** that acts as your personal AI assistant. With over 34,000 GitHub stars, it's one of the most popular self-hosted AI platforms available today.

Khoj lets you:

- **Chat with any LLM** — local (via Ollama, llama.cpp) or cloud (GPT, Claude, Gemini, DeepSeek)
- **Search your documents** — PDF, Markdown, Notion, Word, images, and more using semantic search
- **Build custom AI agents** — with custom knowledge bases, personas, chat models, and tools
- **Automate research** — get personal newsletters and smart notifications delivered to your inbox
- **Access everywhere** — Browser, Obsidian, Emacs, Desktop, Phone, or WhatsApp
- **Generate images and speak** — built-in image generation and text-to-speech

Best of all, it's fully open-source (AGPL-3.0) and designed to be self-hosted from the start.

## Why Run Khoj on a VPS?

Running Khoj on a VPS gives you the best of both worlds:

1. **Always-on availability** — your AI second brain is accessible 24/7
2. **Full privacy** — your documents and queries never leave your server
3. **Connect local LLMs** — pair with Ollama to run models like Qwen3, Llama 3, or Phi-4 entirely on your hardware
4. **Multi-device sync** — access from any device, anywhere
5. **Custom integrations** — connect your own tools, APIs, and data sources

### Recommended VPS Specs

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| CPU | 2 cores | 4 cores |
| RAM | 4 GB | 8 GB+ |
| Storage | 20 GB | 50 GB+ SSD |
| OS | Ubuntu 22.04+ | Ubuntu 24.04 |
| Docker | Yes | Docker Compose v2 |

If you plan to run local LLMs via Ollama alongside Khoj, aim for **8 GB+ RAM** and consider a VPS with GPU support (NVIDIA T4, A10, or similar).

## Step 1: Install Docker and Docker Compose

First, set up Docker on your VPS:

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sudo sh

# Add your user to the docker group
sudo usermod -aG docker $USER

# Log out and back in, OR run:
newgrp docker

# Verify installation
docker --version
docker compose version
```

## Step 2: Deploy Khoj with Docker Compose

Create a directory for Khoj and download the official docker-compose file:

```bash
mkdir -p ~/khoj && cd ~/khoj
wget https://raw.githubusercontent.com/khoj-ai/khoj/master/docker-compose.yml
```

The `docker-compose.yml` includes four services:

- **database** — PostgreSQL with pgvector for vector storage
- **sandbox** — Terrarium code execution sandbox
- **search** — SearXNG meta-search engine for web results
- **server** — The main Khoj application

### Configuration

Before starting, edit the environment variables in `docker-compose.yml`:

```bash
nano docker-compose.yml
```

Set the following essential environment variables under the `server` service:

```yaml
environment:
  - POSTGRES_PASSWORD=your_secure_password        # Change from default
  - KHOJ_DJANGO_SECRET_KEY=your_random_secret_key  # Generate one
  - KHOJ_DEBUG=False
  - KHOJ_ADMIN_EMAIL=admin@yourdomain.com
  - KHOJ_ADMIN_PASSWORD=your_admin_password
```

Generate a Django secret key:
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(50))"
```

### Start Khoj

```bash
cd ~/khoj
docker compose up -d
```

Check the logs to verify everything is running:

```bash
docker compose logs -f server
```

Once healthy, Khoj will be available at `http://your-vps-ip:42110`.

## Step 3: Connect Ollama for Local LLMs

To run models locally, set up Ollama alongside Khoj:

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull a model (e.g., Qwen3 for Chinese/English support)
ollama pull qwen3:8b

# Or use a smaller model for limited RAM
ollama pull phi4-mini:3.8b
```

Add the following to the `server` service environment in `docker-compose.yml`:

```yaml
- OPENAI_BASE_URL=http://host.docker.internal:11434/v1/
- KHOJ_DEFAULT_CHAT_MODEL=qwen3
```

Then restart:

```bash
docker compose down && docker compose up -d
```

Khoj will now use your local Ollama model as the default chat backend.

## Step 4: Set Up a Reverse Proxy (Recommended)

To access Khoj securely with HTTPS, use Caddy or Nginx.

### Using Caddy (Simplest)

```bash
# Install Caddy
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install caddy
```

Create `/etc/caddy/Caddyfile`:

```
khoj.yourdomain.com {
    reverse_proxy localhost:42110
}
```

### Using Nginx

```bash
sudo apt install nginx
```

Create `/etc/nginx/sites-available/khoj`:

```nginx
server {
    server_name khoj.yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:42110;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400;
    }
}
```

Enable and set up HTTPS:

```bash
sudo ln -s /etc/nginx/sites-available/khoj /etc/nginx/sites-enabled/
sudo certbot --nginx -d khoj.yourdomain.com
sudo nginx -t && sudo systemctl reload nginx
```

Then update your Khoj env vars for public access:

```yaml
- KHOJ_NO_HTTPS=True
- KHOJ_DOMAIN=khoj.yourdomain.com
```

## Step 5: First Login and Configuration

1. Open `https://khoj.yourdomain.com` (or `http://your-vps-ip:42110`)
2. Log in with the admin credentials you set in `docker-compose.yml`
3. Go to **Settings → Content** to add your document sources
4. Go to **Settings → Chat** to configure your preferred LLM

### Adding Documents

Khoj supports uploading files directly or pointing to directories. Supported formats:

- PDF, Markdown, Plaintext
- Microsoft Word (`.docx`)
- Images (with OCR)
- Org-mode, Notion export
- GitHub repositories

To add content from the web interface:

1. Navigate to **Settings → Content**
2. Click **Add Content**
3. Choose a source type (file upload, directory, or URL)
4. Khoj will automatically index and make it searchable

## Step 6: Create Custom AI Agents

One of Khoj's most powerful features is custom agents. To create one:

1. Go to **Agents** in the sidebar
2. Click **Create Agent**
3. Configure:
   - **Name & Persona** — define the agent's personality and behavior
   - **Knowledge Base** — select which documents the agent can access
   - **Model** — choose which LLM powers this agent
   - **Tools** — enable web search, code execution, image generation, etc.
   - **Instructions** — give the agent specific system prompts

Example: Create a "Technical Writer" agent that only accesses your documentation folder and responds formally.

## Step 7: Enable Web Search and Advanced Features

### Web Search with SearXNG

The docker-compose.yml already includes SearXNG. To enable web results in Khoj:

1. Uncomment the `SERPER_DEV_API_KEY` line and get a free API key from [serper.dev](https://serper.dev)
2. Or use [Firecrawl](https://firecrawl.dev) for combined search + page reading
3. Restart Khoj: `docker compose down && docker compose up -d`

### Enable Khoj's Computer (Experimental)

Khoj can perform actions on a virtual computer:

```yaml
- KHOJ_OPERATOR_ENABLED=True
# Mount Docker socket to let Khoj control containers
# - /var/run/docker.sock:/var/run/docker.sock
```

## Troubleshooting

### "Connection refused" when connecting to Ollama

Ensure the `extra_hosts` line is present in your docker-compose.yml:

```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"
```

### Khoj won't start

Check the logs:
```bash
docker compose logs server
docker compose logs database
```

Most issues are caused by:
- Insufficient RAM (minimum 2 GB free)
- PostgreSQL not fully initialized (wait 30 seconds)
- Port 42110 already in use

### Slow responses with local LLMs

- Use quantized models (Q4_K_M or Q5_K_M)
- Consider a smaller model like Phi-4-mini (3.8B) instead of 7B+
- Enable GPU acceleration if available

## Managing Khoj

```bash
# Stop Khoj
cd ~/khoj && docker compose down

# Update Khoj
cd ~/khoj && docker compose pull && docker compose up -d

# View logs
cd ~/khoj && docker compose logs -f

# Backup data (volumes are at /var/lib/docker/volumes/)
docker run --rm -v khoj_khoj_db:/data -v $(pwd):/backup alpine tar czf /backup/khoj-db-backup.tar.gz -C /data .
docker run --rm -v khoj_khoj_config:/data -v $(pwd):/backup alpine tar czf /backup/khoj-config-backup.tar.gz -C /data .
```

## Performance Tips

1. **Use SSD storage** — vector searches are I/O intensive
2. **Increase swap** if RAM is tight:
   ```bash
   sudo fallocate -l 4G /swapfile
   sudo chmod 600 /swapfile
   sudo mkswap /swapfile
   sudo swapon /swapfile
   echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
   ```
3. **Limit concurrent users** — Khoj is designed for personal or small team use
4. **Use smaller embedding models** — configure in Settings for faster indexing
5. **Consider a hybrid setup** — use cloud LLMs for complex reasoning and local models for everyday queries

## Conclusion

Deploying Khoj on your VPS gives you a private, always-available AI second brain that respects your privacy and can be customized to your exact needs. With Docker Compose, the setup takes just minutes, and you can connect it to local LLMs via Ollama for a completely self-contained AI ecosystem.

Whether you're a researcher who needs to search thousands of documents, a developer who wants AI-powered code assistance, or just someone who wants a private AI assistant — Khoj on a VPS is a powerful combination.

**Next steps:**
- Explore the [Khoj documentation](https://docs.khoj.dev)
- Join the [Khoj Discord community](https://discord.gg/BDgyabRM6e)
- Try creating custom agents for your specific workflows
- Set up automated document sync from your cloud storage
