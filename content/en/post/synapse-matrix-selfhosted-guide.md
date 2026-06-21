---
title: "Synapse Self-Hosting Guide: Build a Private Matrix Messaging & VoIP Server for Complete Communication Control"
description: "Step-by-step tutorial to deploy Matrix Synapse server on your VPS with Docker, pair it with Element client for end-to-end encrypted messaging, voice/video calls, bot integrations, and team collaboration — reclaiming your communication privacy"
date: 2026-06-21T10:00:00+08:00
lastmod: 2026-06-21T10:00:00+08:00
slug: "synapse-matrix-selfhosted-guide"
tags: ["Matrix", "Synapse", "Messaging", "End-to-End Encryption", "VoIP", "Element", "Self-Hosting", "Docker", "VPS Deployment", "Privacy"]
categories: ["Deployment Guide"]
draft: false
image: /images/posts/synapse-matrix-selfhosted-guide/featured.png
aliases: [/en/post/synapse-matrix-selfhosted-guide/]
---

## Why Self-Host Your Own Messaging Platform?

With mainstream platforms like Telegram, WhatsApp, and Signal, your messages, contacts, and call records are stored on third-party servers. Even when these platforms claim end-to-end encryption, you still need to trust their operators — and history has shown that no commercial company can protect your data forever.

[Matrix](https://matrix.org/) is an open real-time communication protocol, much like SMTP for email: it's not tied to any single provider, allowing anyone to run their own server while remaining interoperable with others. [Synapse](https://github.com/element-hq/synapse) is the reference implementation of the Matrix protocol, written in Python, and paired with the [Element](https://element.io/) client, it forms a complete private communication system.

### Core Advantages of the Matrix Ecosystem

| Feature | Description |
|---------|-------------|
| **Decentralized** | Like email, you choose your server but can communicate with anyone on any server |
| **End-to-End Encrypted** | Supports Olm/Megolm encryption by default — even the server can't read your messages |
| **Rich Media Communication** | Text, voice calls, video conferences (via Jitsi integration) |
| **Bot Integration** | Rich Bot API for CI/CD, monitoring, AI, and automation workflows |
| **Cross-Platform Clients** | Element covers Web, iOS, Android, Windows, macOS, and Linux |
| **Data Sovereignty** | All data stored entirely on your own VPS |

## Environment Preparation

### Server Requirements

| Scale | CPU | RAM | Disk | Use Case |
|-------|-----|-----|------|----------|
| Minimal | 1 core | 1GB | 10GB | 1–5 users |
| Recommended | 2 cores | 2GB | 20GB | 5–50 users |
| Production | 4 cores | 4GB+ | 50GB+ | 50+ users |

This guide uses a **2-core, 2GB VPS** as the example.

### Prerequisites

- VPS running Ubuntu 22.04/24.04 or Debian 12
- Docker and Docker Compose installed
- A domain pointing to your VPS (e.g., `matrix.yourdomain.com`)
- Optional: SSL certificate (Let's Encrypt)

## Step 1: Install Docker Environment

If you don't have Docker yet:

```bash
# Install Docker
curl -fsSL https://get.docker.com | sh

# Enable and start Docker
sudo systemctl enable docker
sudo systemctl start docker

# Add your user to the docker group
sudo usermod -aG docker $USER
newgrp docker
```

Verify the installation:

```bash
docker --version
# Docker version 27.x.x

docker compose version
# Docker Compose version v2.x.x
```

## Step 2: Create Synapse Configuration

First, create the project directory structure:

```bash
mkdir -p ~/matrix-synapse/{homeserver,data,logs,nginx,certs}
cd ~/matrix-synapse
```

Generate the initial configuration using the Docker container:

```bash
docker run --rm \
  -v ./homeserver:/data \
  matrixdotorg/synapse:latest \
  generate

# Edit the configuration file
nano homeserver/homeserver.yaml
```

Key configuration changes:

```yaml
# Server name (must match your domain's server_name)
server_name: "matrix.yourdomain.com"
pedantic_server_names: true

# Listener configuration
listeners:
  - port: 8008
    tls: false
    type: http
    x_forwarded: true
    resources:
      - names: [client, federation]
        compress: false

# Database configuration
database:
  name: sqlite3
  args:
    database: /data/homeserver.db

# Registration shared secret (used for first user registration)
registration_shared_secret: "generate-a-random-secret"

# Allow remote registration (disable in production, add users manually as admin)
enable_registration: true

# Logging
log_config: "/data/matrix.yourdomain.com.log.config"
```

Generate the registration shared secret:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Configure logging:

```yaml
# homeserver/matrix.yourdomain.com.log.config
version: 1

formatters:
  precise:
    format: "%(asctime)s %(levelname)-5s %(process)s %(name)s:%(lineno)d %(message)s"

handlers:
  file:
    class: logging.handlers.RotatingFileHandler
    formatter: precise
    filename: /data/logs/homeserver.log
    maxBytes: 104857600  # 100MB
    backupCount: 10

root:
  level: INFO
  handlers:
    - file
```

## Step 3: Start Synapse with Docker Compose

Create `docker-compose.yaml`:

```yaml
services:
  synapse:
    image: matrixdotorg/synapse:latest
    container_name: synapse
    restart: unless-stopped
    ports:
      - "8008:8008"
    volumes:
      - ./homeserver:/data
      - ./logs:/data/logs
    environment:
      - TZ=Asia/Shanghai
    depends_on:
      - db

  db:
    image: postgres:16-alpine
    container_name: synapse-db
    restart: unless-stopped
    environment:
      - POSTGRES_USER=synapse
      - POSTGRES_PASSWORD=synapse_password_here
      - POSTGRES_DB=synapse
      - TZ=Asia/Shanghai
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U synapse"]
      interval: 10s
      timeout: 5s
      retries: 5
```

> **Note**: Use PostgreSQL instead of SQLite in production. SQLite works for small deployments but performance degrades noticeably with increased concurrent connections.

Start the services:

```bash
docker compose up -d

# Check logs to confirm successful startup
docker logs -f synapse
```

## Step 4: Register the Admin Account

```bash
# Enter the container and register
docker exec -it synapse register_new_matrix_user \
  -c /data/homeserver.yaml \
  http://localhost:8008 \
  --admin \
  -u admin \
  -p 'your_secure_password_here'
```

After successful registration, you'll receive a confirmation email (if email is configured). The admin account has full permissions, including creating other users.

## Step 5: Configure Nginx Reverse Proxy and HTTPS

Synapse doesn't provide HTTPS natively, so you need Nginx or Caddy as a reverse proxy.

### Install Nginx and SSL Certificate

```bash
sudo apt install -y nginx certbot python3-certbot-nginx
```

### Obtain SSL Certificate

```bash
sudo certbot --nginx -d matrix.yourdomain.com
```

### Configure Nginx

```nginx
server {
    listen 443 ssl http2;
    server_name matrix.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/matrix.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/matrix.yourdomain.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    # Client request size limit
    client_max_body_size 50M;

    # Matrix Client API
    location /_matrix/client/ {
        proxy_pass http://127.0.0.1:8008;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_buffering off;
        chunked_transfer_encoding off;
    }

    # Matrix Federation API
    location /_matrix/federation/ {
        proxy_pass http://127.0.0.1:8008;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_buffering off;
    }

    # Matrix Media Repo
    location /_matrix/media/ {
        proxy_pass http://127.0.0.1:8008;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # Synapse Server Key
    location /_matrix/key/v2/ {
        proxy_pass http://127.0.0.1:8008;
        proxy_set_header Host $host;
    }

    # Well-known configuration
    location /.well-known/matrix/server {
        add_header Content-Type application/json;
        return 200 '{"m.server": "matrix.yourdomain.com:443"}';
    }

    location /.well-known/matrix/client {
        add_header Content-Type application/json;
        return 200 '{
            "m.home_server": "matrix.yourdomain.com",
            "m.server": "matrix.yourdomain.com:443"
        }';
    }
}

# HTTP to HTTPS redirect
server {
    listen 80;
    server_name matrix.yourdomain.com;
    return 301 https://$server_name$request_uri;
}
```

```bash
# Test and reload Nginx
sudo nginx -t
sudo systemctl reload nginx
```

## Step 6: Configure Email Service (Optional but Recommended)

Add email configuration to `homeserver.yaml`:

```yaml
email:
  smtp_host: smtp.yourdomain.com
  smtp_port: 587
  smtp_user: "noreply@yourdomain.com"
  smtp_pass: "your_smtp_password"
  require_transport_security: true
  notif_from: "Your Name <noreply@yourdomain.com>"

  app_name: "MyPrivateMatrix"

  notif_template_html: notif_mail.html
  notif_template_text: notif_mail.txt
```

## Step 7: Install the Element Client

### Web Version (Quickest Start)

Visit `https://matrix.yourdomain.com`. Element will auto-detect your server. Click "Create Account" to register a new user.

### Desktop Client

- **Linux**: `sudo apt install element-desktop` or download AppImage from [element.io](https://element.io/download)
- **Windows/macOS**: Download the installer from the official website
- **Mobile**: Search for "Element" in the iOS/Android app stores

### Logging into Element

1. Open Element, select "Custom Server"
2. Enter your domain: `https://matrix.yourdomain.com`
3. Log in with the admin account you registered earlier

## Step 8: Invite Users and Daily Management

### Creating Regular Users

```bash
# As admin, run on the server
docker exec -it synapse register_new_matrix_user \
  -c /data/homeserver.yaml \
  http://localhost:8008 \
  -u alice \
  -p 'alice_secure_password'
```

### Inviting via Link

In Element, go to Room Settings → Invite → Copy Link. The invitee can use this link to discover your server and register automatically.

### Managing Users

```bash
# List all users
docker exec -it synapse list_users -c /data/homeserver.yaml

# Deactivate a user
docker exec -it synapse deactivate_user -c /data/homeserver.yaml user@matrix.yourdomain.com

# Reset password
docker exec -it synapse update_password -c /data/homeserver.yaml user@matrix.yourdomain.com new_password_here
```

## Step 9: Configure Voice/Video Calls

Synapse doesn't handle media streams directly. You need Jitsi Meet for audio/video calling.

### Method 1: Use Public Jitsi Instance (Simplest)

In Element room settings, configure the Jitsi domain directly. However, public instances have limited reliability.

### Method 2: Self-Host Jitsi Meet (Recommended)

```bash
mkdir -p ~/jitsi-meet
cd ~/jitsi-meet

# Use the official installation script
wget -qO - https://download.jitsi.org/jitsi-key.gpg.key | gpg --dearmor > /usr/share/keyrings/jitsi-keyring.gpg
echo 'deb [signed-by=/usr/share/keyrings/jitsi-keyring.gpg] https://download.jitsi.org stable/' | tee /etc/apt/sources.list.d/jitsi-stable.list > /dev/null
apt update
apt install -y jitsi-meet
```

During installation, enter your domain (e.g., `meet.yourdomain.com`), and it will automatically configure SSL.

Set the Jitsi domain in Element room settings to `https://meet.yourdomain.com`.

## Step 10: Configure Bot Integrations

Matrix's Bot API is powerful and can integrate with various automation tools.

### Common Bot Examples

#### 1. Deploy Gatus Health Check Bot

```bash
# Clone Gatus Bot
git clone https://github.com/TwiN/gatus.git
cd gatus/docker/bot

# Edit config.yaml with your bot token
```

#### 2. Deploy Matrix IRC Bridge

Bridge Matrix rooms with IRC channels:

```yaml
# docker-compose.yaml snippet
irc-bot:
  image: matrix-org/matrix-appservice-irc:latest
  volumes:
    - ./irc-config:/config
  ports:
    - "9000:9000"
```

#### 3. Deploy Matrix CI/CD Bot

Use [matrix-bot-sdk](https://github.com/matrix-org/matrix-bot-sdk) to write custom bots:

```python
from matrix_bot_sdk import MatrixClient

client = MatrixClient("https://matrix.yourdomain.com")
home = client.join_room("!roomid:matrix.yourdomain.com")

@home.on_event("m.room.message")
def handle_message(event):
    content = event["content"]["body"]
    if content.startswith("!deploy"):
        home.send_markdown_message("Deploying...")
        # Execute deployment logic
        home.send_markdown_message("✅ Deployment complete!")

client.run()
```

## Advanced Configuration

### Configure Media Storage Limits

Prevent users from uploading excessive files that fill up disk space:

```yaml
# homeserver.yaml
max_upload_size_mb: 100
media_storage_path: /data/media_store
write_back:
  engine: ffi
  blob_store_path: /data/blob_store
  blob_store_keep_days: 90
```

### Configure Rate Limiting

```yaml
rate_limits:
  concurrent_login_limit_per_user: 5
  concurrent_login_window: 30s
  concurrent_login_reauth_window: 30s
```

### Enable Federation (Allow Other Matrix Servers to Connect)

```yaml
# homeserver.yaml
federation_domain_whitelist:
  - matrix.org
  - element.io

suppress_send_errors: false
```

> **Tip**: Once Federation is enabled, your server becomes part of the global Matrix network. Other servers' users can communicate with yours. If you only want internal use, leave it disabled.

### Regular Backups

```bash
#!/bin/bash
# backup-matrix.sh
BACKUP_DIR="/backup/matrix"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p "$BACKUP_DIR"

# Backup database
docker exec synapse-db pg_dump -U synapse synapse > "$BACKUP_DIR/synapse_$DATE.sql"

# Backup uploaded media files
tar czf "$BACKUP_DIR/media_$DATE.tar.gz" -C /root/matrix-synapse/data/media_store .

# Keep only last 30 days of backups
find "$BACKUP_DIR" -mtime +30 -delete

echo "Backup completed: $DATE"
```

Add to crontab:

```bash
crontab -e
# Daily backup at 2 AM
0 2 * * * /root/scripts/backup-matrix.sh
```

## Troubleshooting

### Issue 1: Element Cannot Connect to Server

Check if Nginx correctly forwards `/_matrix/` paths:

```bash
curl -I https://matrix.yourdomain.com/_matrix/client/versions
# Should return 200 OK with JSON response
```

### Issue 2: Federation Connection Failed

Ensure firewall allows port 443 for federation traffic:

```bash
sudo ufw allow 443/tcp
sudo ufw allow 8448/tcp  # If using non-standard port
```

### Issue 3: Insufficient Disk Space

```bash
# Check disk usage
df -h

# Clean old media files
docker exec synapse python3 -m synapse.admin purge_media_cache \
  -c /data/homeserver.yaml \
  --size 1GB \
  --min-age 30d
```

### Issue 4: PostgreSQL Connection Problems

```bash
# Check database logs
docker logs synapse-db

# Restart database
docker restart synapse-db

# Verify connectivity
docker exec synapse-db pg_isready -U synapse
```

## Security Hardening Checklist

- [x] Enable HTTPS (Let's Encrypt auto-renewal)
- [x] Disable public registration (in production)
- [x] Configure rate limiting
- [x] Limit maximum upload file size
- [x] Regularly update Synapse image
- [x] Configure firewall (only expose 80/443)
- [x] Enable database backups
- [x] Set up log rotation
- [x] Enforce strong password policy

## Summary

By following this tutorial, you've successfully deployed a complete Matrix messaging server on your VPS. Compared to commercial communication platforms, self-hosting Synapse offers:

1. **Full data control** — all messages, files, and contacts stay on your server
2. **Zero operational cost** — only VPS fees, no subscription charges
3. **Highly scalable** — from 5 users to 5,000+
4. **Rich ecosystem** — Bots, Bridges, and plugins integrate with virtually any workflow
5. **True end-to-end encryption** — even server admins cannot read messages

The Matrix protocol, like email, is an open, decentralized communication standard. When you run your own Synapse server, you own your own "email server" — except this time, it's instant, encrypted, and supports voice and video.

Get started now and take back your communication privacy!
