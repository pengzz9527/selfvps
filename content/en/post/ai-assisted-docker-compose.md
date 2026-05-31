---
title: "AI-Assisted Docker Compose: Generate and Optimize Container Deployments with LLMs"
description: "Step-by-step guide to using LLMs to generate Docker Compose files from natural language, review existing configurations for security and performance issues, and debug deployment problems — all with AI assistance."
date: 2026-05-31T21:30:00+08:00
slug: "ai-assisted-docker-compose"
image: /images/posts/ai-assisted-docker-compose/featured.png
tags: ["AI", "LLM", "Docker", "Docker Compose", "container orchestration", "DevOps", "automation", "self-hosting"]
categories: ["AI & DevOps"]
draft: false
---

Writing Docker Compose files has a weird property: **the entry barrier is low, but the ceiling is sky-high**.

For simple scenarios — a Nginx + MySQL + Redis stack — a dozen lines of YAML will do. But once you involve multi-service orchestration, health checks, dependency ordering, network isolation, volume permission management, resource limits, and secret management, your config quickly balloons to hundreds of lines, and the chances of something going wrong skyrocket.

Here's the good news: **Large Language Models are exceptionally good at YAML generation and configuration optimization**. They've read countless open-source Compose files, they know the best practices, and they can spot the subtle issues in your configuration that you'd miss after staring at it for an hour.

This guide walks you through building an **AI-assisted Docker Compose workflow** — from describing your requirements in plain English to auto-generating configurations, reviewing for security and performance issues, and debugging deployment problems.

---

## Why AI-Assisted Orchestration?

Consider a typical scenario: You want to deploy a WordPress site with Nginx, PHP-FPM, and MariaDB. Sounds simple, right? But here's what you actually need to think about:

- How do you ensure PHP-FPM starts after MariaDB is ready?
- Should Nginx have a health check?
- How do you manage the database password — hard-coded in compose or via `.env`?
- What are the correct volume permissions for persistent data?
- How many replicas do you need for production?

A user unfamiliar with Docker's subtleties can easily write a config that "works" but isn't production-viable. An LLM can externalize all this tacit knowledge and help you write a configuration that's actually deployable in production.

## Choosing Your Approach

| Method | Best For | Difficulty |
|--------|---------|-----------|
| **Ask ChatGPT/Claude directly** | One-off needs, quick prototyping | ⭐ |
| **Local Ollama + custom prompts** | Privacy-sensitive, offline environments | ⭐⭐ |
| **AI Agent with iterative optimization** | Complex multi-service deployments | ⭐⭐⭐ |
| **IDE AI plugins** | Daily development, incremental improvement | ⭐ |

This guide focuses on the first two approaches, which are the most practical for VPS users.

## Step 1: Generate Compose Files from Scratch with LLM

### Method 1: Online LLM (Quick Prototyping)

Here's a prompt template that works well with ChatGPT, Claude, or any capable LLM:

```
Generate a Docker Compose configuration with these services:

1. Nginx (latest), as a reverse proxy
2. PHP 8.3-FPM running a Laravel application
3. MariaDB 10.11 for the database
4. Redis 7.x for caching and sessions

Requirements:
- Use .env file for sensitive variables
- Add health checks for PHP-FPM and MariaDB
- Nginx depends on PHP-FPM, which depends on MariaDB and Redis
- Use overlay network driver with an internal network for app services
- Expose ports 80 and 443 on Nginx only
- Set resource limits on all services
- Use named volumes for persistent data
```

The LLM will return a complete `docker-compose.yml` that typically includes:

- Network isolation (frontend / backend networks)
- `depends_on` with proper conditions for startup ordering
- `healthcheck` configurations for critical services
- CPU and memory `limits` with `reservations`
- Named volume declarations and mounts

### Method 2: Local Ollama (Privacy-First)

If you're privacy-conscious or already running Ollama on your VPS:

```bash
# Verify Ollama is running
curl http://localhost:11434/api/tags

# Choose a model good at code generation
ollama pull llama3.3:70b  # or deepseek-coder:33b
```

Then use a simple script to generate Compose config via the Ollama API:

```bash
#!/bin/bash
# generate-compose.sh

read -r -d '' PROMPT << 'EOF'
You are a Docker Compose expert. Generate a docker-compose.yml for:

Services: Python FastAPI app + PostgreSQL 16 + Redis 7
Requirements:
- FastAPI runs with uvicorn
- Database password from .env
- Health checks configured
- Named volumes for data persistence
- Production-grade configuration
- Comments explaining key sections

Output ONLY the YAML code, no explanations.
EOF

curl -s http://localhost:11434/api/generate \
  -d "{\"model\": \"llama3.3:70b\", \"prompt\": \"$PROMPT\", \"stream\": false}" \
  | jq -r '.response' > docker-compose.yml

echo "✅ docker-compose.yml generated"
```

> **Note**: Generation quality depends heavily on model size. 7B models can handle basic configs, but 70B+ models perform significantly better on complex scenarios.

## Step 2: Review and Optimize Existing Configs with AI

LLMs aren't just good at generation — they **excel at review**. Feed it your existing `docker-compose.yml`:

```
Review this docker-compose.yml and identify potential issues and optimizations:

- Security: secret management, network isolation, image pinning
- Performance: resource allocation, restart policies
- Reliability: health checks, dependency ordering
- Maintainability: naming conventions, comments, structure

<Paste your docker-compose.yml here>
```

Common issues an LLM review will catch:

| Category | Typical Issues AI Can Detect |
|---------|-----------------------------|
| **Security** | Hard-coded passwords, `latest` tag usage, no network isolation |
| **Performance** | Missing resource limits, suboptimal volume types |
| **Reliability** | Missing health checks, incorrect dependency ordering, no restart policy |
| **Maintainability** | No named volume declarations, scattered configuration, no comments |

## Step 3: Debug Compose Issues with AI

When `docker compose up` fails, the instinct is to stare at your YAML line by line. Don't waste time — try this instead:

```
docker compose up failed with the following error. Please analyze the cause and suggest a fix.

Error log:
<Paste the error log>

My docker-compose.yml:
<Paste your config>
```

LLMs can rapidly diagnose issues like:

- **Port conflicts**: "port is already allocated"
- **Volume permissions**: "permission denied" errors
- **Dependency timeouts**: health check timeout too short, or wrong health check command
- **Undefined variables**: missing references in `.env`
- **Network issues**: network doesn't exist or name conflicts

## Step 4: Advanced — AI Agent for Iterative Optimization

For truly complex deployments, you can set up an AI agent loop: Agent generates Compose → deploys it → reads logs → finds problems → modifies config → retries.

Here's a simplified implementation:

```python
# ai-compose-agent.py (pseudocode)
import subprocess
import json

def generate_compose(requirements):
    """Generate Compose config via LLM"""
    prompt = f"Generate docker-compose.yml for: {requirements}"
    # Call Ollama API here
    return response

def deploy_and_check(compose_content):
    """Deploy and verify service health"""
    with open('docker-compose.yml', 'w') as f:
        f.write(compose_content)
    result = subprocess.run(['docker', 'compose', 'up', '-d'], 
                          capture_output=True, text=True)
    status = subprocess.run(['docker', 'compose', 'ps', '--format', 'json'],
                          capture_output=True, text=True)
    return result.returncode, result.stderr, status.stdout

def optimize(compose_content, errors):
    """Fix issues via LLM"""
    prompt = f"The following docker-compose.yml failed to deploy. Fix it:\n\n{compose_content}\n\nError: {errors}"
    return new_compose  # from LLM

# Iterative loop
max_attempts = 5
for i in range(max_attempts):
    compose = generate_compose(requirements) if i == 0 else optimize(compose, errors)
    code, stderr, status = deploy_and_check(compose)
    if code == 0 and all_healthy(status):
        print("✅ Deployment successful!")
        break
    errors = stderr
```

## Real-World Example: Deploying a Full Web Stack

Let me walk through a real example to show the full AI-assisted workflow.

### Requirements

> Deploy a Node.js (Express) + MongoDB + Nginx TODO application.
> - Backend API proxied through Nginx
> - MongoDB with authentication and persistence
> - Production-grade configuration with security and performance in mind

### AI-Generated Initial Version

```yaml
version: '3.8'

services:
  mongodb:
    image: mongo:7.0
    container_name: todo-mongodb
    restart: unless-stopped
    environment:
      MONGO_INITDB_ROOT_USERNAME: ${MONGO_USER}
      MONGO_INITDB_ROOT_PASSWORD: ${MONGO_PASS}
      MONGO_INITDB_DATABASE: ${MONGO_DB:-todoapp}
    volumes:
      - mongo_data:/data/db
      - mongo_config:/data/configdb
    networks:
      - backend
    healthcheck:
      test: echo 'db.runCommand("ping").ok' | mongosh --quiet
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    deploy:
      resources:
        limits:
          cpus: '1.0'
          memory: 512M
        reservations:
          cpus: '0.25'
          memory: 256M

  app:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: todo-app
    restart: unless-stopped
    depends_on:
      mongodb:
        condition: service_healthy
    environment:
      NODE_ENV: production
      MONGODB_URI: mongodb://${MONGO_USER}:${MONGO_PASS}@mongodb:27017/${MONGO_DB:-todoapp}?authSource=admin
      PORT: 3000
    networks:
      - backend
    healthcheck:
      test: ["CMD", "wget", "--spider", "http://localhost:3000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 15s
    deploy:
      resources:
        limits:
          cpus: '0.5'
          memory: 256M

  nginx:
    image: nginx:1.25-alpine
    container_name: todo-nginx
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/conf.d/default.conf:ro
      - ./ssl:/etc/nginx/ssl:ro
    depends_on:
      app:
        condition: service_healthy
    networks:
      - frontend
      - backend
    healthcheck:
      test: ["CMD", "nginx", "-t"]
      interval: 60s
      timeout: 5s
      retries: 2
    deploy:
      resources:
        limits:
          cpus: '0.3'
          memory: 128M

networks:
  frontend:
    driver: bridge
  backend:
    driver: bridge
    internal: true

volumes:
  mongo_data:
  mongo_config:
```

### AI Review Suggestions

When submitted to an LLM for review, here's what it recommended:

1. **🔒 Security**: MongoDB 7.0 has auth enabled by default, but add `--auth` explicitly in the command. Consider Docker Secrets instead of environment variables for production.

2. **⚡ Performance**: Add `NODE_OPTIONS="--max-old-space-size=200"` to the Node.js service to constrain memory usage.

3. **📦 Image Pinning**: Pin Nginx to a specific patch version (e.g., `1.25.5-alpine`) instead of `1.25-alpine`.

4. **🔄 Logging**: Add a `logging` configuration to all services to prevent log files from filling up the disk:
   ```yaml
   logging:
     driver: "json-file"
     options:
       max-size: "10m"
       max-file: "3"
   ```

5. **🔍 Monitoring**: Consider adding a cAdvisor container for resource monitoring.

## Best Practices

After extensive experimentation, here are the core principles for effective AI-assisted Compose orchestration:

### 1. Be Specific in Your Prompts

**Bad**: Write a Docker Compose for me
**Good**: Write a Docker Compose with Python FastAPI + PostgreSQL 16 + Redis 7, using .env for variables, production-grade config, named volumes for database persistence

### 2. Iterate, Don't Try for Perfection in One Shot

Generate the basic structure → review it → add details → optimize. Focusing on one dimension at a time (networking, security, performance) yields better results than asking the LLM to consider everything at once.

### 3. Always Review Before Deploying to Production

AI-generated configurations should always be reviewed by a human before production deployment. Pay special attention to:

- Port mappings — are they correct and secure?
- Image sources — stick to official images
- No hard-coded secrets in environment variables
- Volume mount paths make sense
- Network isolation is properly configured

### 4. Build Your Prompt Template Library

Save your frequently-used requirements as templates for reuse:

```
Template: WordPress Production Deployment
- Services: Nginx + PHP 8.3-FPM + MariaDB 10.11 + Redis 7
- Features: LSCache support, auto SSL renewal, WAF rules
- Security: Non-root execution, minimal file permissions, fail2ban integration
```

## Further Reading

- [AI-Driven VPS Operations](/en/post/ai-vps-automated-operations/) — Monitor and fix your server with LLM agents
- [Docker Security Hardening](/en/post/docker-security-hardening/) — Deep dive into container security
- [Docker Log Management: Loki + Grafana + Promtail](/en/post/docker-log-management-loki-grafana-promtail/) — Set up a comprehensive logging pipeline

---

**Your first AI-assisted Compose exercise**: Use the methods in this guide to generate a Docker Compose configuration for a Next.js + PostgreSQL + MinIO stack. Deploy it and verify all services run correctly. You'll find that with AI assistance, writing container orchestration configs becomes at least twice as fast — and the results are often better than anything you'd write from scratch.
