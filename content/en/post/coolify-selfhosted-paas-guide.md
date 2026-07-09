---
title: "Self-Host Coolify: Your Open-Source Heroku/Netlify Alternative for One-Click Docker Deployments"
slug: coolify-selfhosted-paas-guide
date: 2026-07-09
categories: ["Self-Hosting", "DevOps"]
tags: ["coolify", "paas", "docker", "heroku-alternative", "continuous-deployment"]
description: "Complete guide: Self-host a Coolify PaaS platform on your VPS for one-click deployments, automatic SSL, and continuous integration — a free alternative to Heroku/Netlify."
image: "/images/posts/coolify-selfhosted-paas-guide/featured.png"
---

## Why You Need Coolify

If you've ever used Heroku, Netlify, or Vercel, you know how convenient "push code and deploy" feels. But as your applications grow in scale and traffic, so do the costs — Heroku's hobby dyno starts at $7/month, and once you need multiple services or higher performance, monthly bills easily exceed $50–$100.

**Coolify** is an open-source, self-hostable PaaS (Platform as a Service) solution developed by Coollabs.io. It gives you the same Heroku/Netlify-like experience on your own VPS, completely free and without platform restrictions.

### Core Advantages of Coolify

| Feature | Heroku | Netlify | Coolify (Self-Hosted) |
|---------|--------|---------|-----------------------|
| Base Cost | $7+/month | Limited free tier | **Completely Free** |
| Custom Domains | ✅ | ✅ | ✅ |
| Auto HTTPS/SSL | ✅ | ✅ | ✅ (Let's Encrypt) |
| Docker Support | ✅ | ❌ | ✅ |
| Database Management | Paid Add-on | ❌ | ✅ (Built-in) |
| Continuous Deployment | ✅ | ✅ | ✅ (GitHub/GitLab) |
| Data Ownership | Platform owns | Platform owns | **Fully Yours** |
| Unlimited Projects | Paid | Limited | ✅ |

## Prerequisites

### System Requirements

- **Operating System**: Ubuntu 22.04 / 24.04 (recommended) or Debian 12
- **RAM**: Minimum 2GB (4GB+ recommended)
- **Disk**: At least 20GB available
- **CPU**: 2 cores or more
- **Domain**: Pointing to your VPS IP (for HTTPS)
- **Ports**: 80, 443, 22, and Coolify's ports

### Initial Setup

```bash
# Update your system
sudo apt update && sudo apt upgrade -y

# Install essential tools
sudo apt install -y curl git jq ufw

# Configure firewall
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable
```

## Installing Coolify

### Method 1: One-Click Install Script (Recommended)

Coolify provides an official one-click installation script — the simplest way to get started:

```bash
curl -fsSL https://cdn.coollabs.io/coolify/install.sh | bash
```

The installation script automatically:
1. Checks system compatibility
2. Installs Docker and Docker Compose
3. Pulls and starts the Coolify container
4. Generates an admin password

After installation, you'll see output like:

```
✅ Coolify is installed successfully!

📧 Admin email: admin@example.com
🔑 Admin password: [randomly generated password]
🌐 URL: http://your-vps-ip:8080

Please save your admin password!
```

### Method 2: Manual Docker Installation

If you prefer manual control, use Docker Compose:

```bash
# Create Coolify directory
mkdir -p ~/coolify && cd ~/coolify

# Download docker-compose configuration
curl -fsSL https://cdn.coollabs.io/coolify/docker-compose.yml -o docker-compose.yml

# Download .env template
curl -fsSL https://cdn.coollabs.io/coolify/.env.example -o .env

# Start the services
docker compose up -d
```

## First-Time Configuration

### 1. Access the Control Panel

Open your browser and navigate to `http://your-server-ip:8080` (use the port specified during installation). Log in with the admin credentials generated during installation.

### 2. Change the Default Password

The first thing to do after logging in is change the default password:

```
Settings → Account → Change Password
```

### 3. Configure Your Server

In the Coolify dashboard, click **"Servers"** → **"Add Server"**:

- **Name**: Give your server a name (e.g., "Production VPS")
- **IP Address**: Your VPS IP
- **User**: root (or your non-root user)
- **SSH Key**: Upload your SSH private key (recommended) or use password
- **Port**: 22 (default SSH port)

Coolify connects to your server via SSH, verifies the connection, and displays a green ✅ when successful.

## Core Features Deep Dive

### 1. One-Click Web Application Deployment

#### Deploy from a GitHub Repository

This is the most common and powerful feature:

1. In the Coolify panel, click **"Applications"** → **"Deploy New Application"**
2. Select **"GitHub"** as your Git provider
3. Authorize Coolify to access your GitHub account
4. Select the target repository
5. Configure deployment parameters:

```
Build Pack: 
  - PHP (Laravel/Symfony)
  - Node.js
  - Python (Django/Flask)
  - Static HTML
  - Docker Compose

Deployment Settings:
  - Auto-deploy branch (main/master)
  - Build command
  - Publish command
  - Environment variables
```

**Example: Deploy a Node.js Application**

```json
// Assuming your repo contains package.json
{
  "name": "my-app",
  "scripts": {
    "build": "npm run build",
    "start": "node dist/main.js"
  }
}
```

Configure in Coolify:
- **Build Command**: `npm run build`
- **Start Command**: `npm start`
- **Ports Exposed**: `3000`

After deployment, Coolify automatically assigns a subdomain (like `my-app.xxx.coolify.yourdomain.com`) and configures HTTPS.

#### Deploy from Docker Compose

For more complex scenarios, deploy directly from `docker-compose.yml`:

```yaml
version: '3.8'
services:
  app:
    image: your-image:latest
    ports:
      - "3000:3000"
    environment:
      - NODE_ENV=production
    restart: always
```

### 2. Database Management

Coolify includes built-in one-click deployment and management for various databases:

**Supported Database Types:**
- PostgreSQL
- MySQL / MariaDB
- Redis
- MongoDB
- Meilisearch
- ClickHouse

**Creating a Database:**

1. Click **"Databases"** → **"Create Database"**
2. Choose the database type
3. Set version and resource limits (CPU/memory)
4. Click create

Coolify auto-generates strong passwords and provides connection details:

```
Host: db-postgres-xxx.coolify.yourdomain.com
Port: 5432
Database: your_db_name
Username: your_username
Password: [auto-generated strong password]
```

### 3. Static Website Deployment

Deploying static websites (HTML/CSS/JS) is straightforward:

1. Push your static files to a GitHub repository
2. Select **"Static"** as the build pack in Coolify
3. Specify the build output directory (e.g., `dist/` or `build/`)
4. Deploy!

Coolify automatically serves static files via Nginx and configures HTTPS.

### 4. Continuous Deployment (CI/CD)

Coolify integrates with GitHub/GitLab webhooks for true continuous deployment:

```
Code Push → GitHub Webhook → Coolify Auto-Build → Auto-Deploy
```

**Setup Steps:**

1. Enable in the application's **"Settings"** → **"Continuous Deployment"**
2. Select branches to monitor (e.g., `main`, `develop`)
3. Optional: Configure deployment rules (e.g., only deploy on tags)

**Advanced: Manual Trigger via API**

You can manually trigger a deployment via API:

```bash
curl -X POST \
  "https://coolify.yourdomain.com/api/v1/deploy?resource_id=YOUR_RESOURCE_ID" \
  -H "Authorization: Bearer YOUR_API_TOKEN"
```

### 5. Environment Variable Management

Coolify provides a visual environment variable management interface:

- Supports environment isolation (dev/staging/prod)
- Supports encrypted sensitive variables (DB passwords, API keys)
- Supports importing from external secret management services

```yaml
# Configure in Coolify's interface
DATABASE_URL: postgresql://user:***@host:5432/db
REDIS_URL: redis://redis-host:***@db:5432/myapp
      - NEXT_PUBLIC_API_URL=https://api.yourdomain.com
    depends_on:
      - db
  
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: myapp
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - pgdata:/var/lib/postgresql/data

volumes:
  pgdata:
```

In Coolify:
1. Select **"Docker Compose"** deployment method
2. Point to the GitHub repository containing the above file
3. Coolify automatically parses and deploys all services
4. Databases automatically receive internal connection addresses

## Security Best Practices

### 1. Restrict Access

```bash
# Deny direct access to Coolify panel port via firewall
sudo ufw deny 8080/tcp

# Access Coolify panel through a domain instead
# Add a custom domain in Coolify settings and enable HTTPS
```

### 2. Regular Backups

Coolify supports automated configuration backups:

```bash
# Manually backup Coolify configuration
docker exec coolify-backup-1 backup

# Schedule regular backups using cron
echo "0 2 * * * docker exec coolify-backup-1 backup" | crontab -
```

### 3. Use SSH Key Authentication

Don't store passwords in Coolify; use SSH keys instead:

```bash
# Generate key on the server
ssh-keygen -t ed25519 -C "coolify-deploy" -f ~/.ssh/coolify_deploy

# Add public key to GitHub/GitLab
cat ~/.ssh/coolify_deploy.pub

# Add private key in Coolify
# Settings → SSH Keys → Add Private Key
```

### 4. Updating Coolify

Coolify supports one-click updates:

```bash
# Click "Update" in the Coolify panel
# Or via command line:
curl -fsSL https://cdn.coollabs.io/coolify/update.sh | bash
```

## Cost Comparison

### Deploying 3 Services on Heroku

| Service | Heroku Monthly Cost |
|---------|---------------------|
| Web App (Standard-1X) | $25 |
| Redis (RedisCloud 30) | $25 |
| Additional Worker | $25 |
| **Total** | **$75/month** |

### Using Coolify Self-Hosted

| Item | Cost |
|------|------|
| VPS (2GB RAM, 2 CPU) | ~$5–10/month |
| Domain | ~$10/year |
| SSL Certificate | **Free** |
| Coolify | **Free (Open Source)** |
| **Total** | **~$6–11/month** |

**Annual Savings: $780 – $900!**

## Frequently Asked Questions

### Q: Is Coolify suitable for production environments?

A: Absolutely. Coolify has many production users, including small-to-medium businesses and individual developers. It's based on Docker, ensuring stability. For ultra-high-traffic scenarios, pair it with load balancers and CDNs.

### Q: Can I manage multiple servers?

A: Yes. Coolify supports multi-server management. You can manage multiple VPS instances from a single Coolify instance, ideal for multi-region deployments.

### Q: How about data security?

A: Coolify doesn't store your application code or data — only configuration information. All applications run on your own servers, giving you full data control. Use SSD drives and back up databases regularly.

### Q: Does Coolify support Kubernetes?

A: As of 2026, Coolify primarily uses Docker Compose. Kubernetes support is under development. For most VPS scenarios, Docker Compose is more than sufficient.

### Q: How do I migrate to Coolify?

A: Very simple. Just push your application code to a Git repository and configure the corresponding deployment settings in Coolify. Coolify handles building and deploying automatically.

## Summary

Coolify is currently one of the best open-source PaaS self-hosting solutions. It perfectly fills the gap between Heroku/Netlify and raw Docker:

- ✅ **Zero software licensing fees** — Fully open source
- ✅ **One-click deployment** — Push to GitHub, deploy automatically
- ✅ **Automatic HTTPS** — Seamless Let's Encrypt integration
- ✅ **Database management** — Built-in support for multiple databases
- ✅ **Multi-environment management** — Dev/staging/prod environment isolation
- ✅ **Visual dashboard** — No need to write complex configurations

If you have a VPS and are tired of manually managing Docker containers, Coolify is definitely worth trying. It transforms your VPS into a fully functional cloud platform instead of just a remote machine you SSH into to type commands.

---

*Found this article helpful? Feel free to open an Issue or PR on GitHub to improve the content.*
