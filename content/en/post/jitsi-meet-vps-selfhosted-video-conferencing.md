---
title: "Self-Hosted Jitsi Meet on VPS: Complete Deployment Guide to Replace Zoom for Free"
description: "Step-by-step guide to deploying Jitsi Meet video conferencing on your VPS. Support for multi-person HD calls, screen sharing, and meeting recording. Fully self-hosted with zero subscription costs and maximum privacy."
date: 2026-08-24T10:00:00+08:00
lastmod: 2026-08-24T10:00:00+08:00
slug: "jitsi-meet-vps-selfhosted-video-conferencing"
tags: ["Jitsi Meet", "Video Conferencing", "Self-Hosting", "VPS", "Open Source", "Zoom Alternative", "Docker", "Privacy"]
categories: ["Self-Hosting"]
draft: false
image: /images/posts/jitsi-meet-vps-selfhosted-video-conferencing/featured.png
aliases: [/en/post/jitsi-meet-vps-selfhosted-video-conferencing/]
---

## Introduction: Why Self-Host Jitsi Meet?

While Zoom, Google Meet, and Microsoft Teams offer powerful features, they all have significant drawbacks: **increasingly aggressive pricing models**, **privacy and compliance risks**, and **high enterprise feature thresholds**. For individuals, small teams, and SMBs, self-hosting a video conferencing solution is the optimal choice.

**Jitsi Meet** is one of the most mature open-source video conferencing solutions, with these core advantages:

- **Completely free and open-source**: No meeting duration limits, no per-participant pricing
- **Zero-configuration joining**: No account registration needed, just open a link
- **End-to-end encryption**: Optional E2E encryption to protect meeting content
- **Feature-complete**: Screen sharing, meeting recording, virtual backgrounds, chat
- **Fully private**: All data stays on your own server with no third-party access

## System Requirements and Architecture

### Minimum Configuration

| Participant Size | CPU | RAM | Bandwidth | Recommended VPS |
|-----------------|-----|------|-----------|-----------------|
| Under 10 people | 2 cores | 2GB | 10 Mbps | Entry-level VPS |
| 20-50 people | 4 cores | 4GB | 50 Mbps | Standard VPS |
| 50+ people | 8 cores | 8GB+ | 100 Mbps+ | High-performance VPS |

### Architecture Components

Jitsi Meet consists of these core components:

1. **Jitsi Videobridge (JVB)**: Media relay server handling audio/video streams
2. **Jitsi Meet (Web)**: Frontend interface, React-based web application
3. **Prosody**: XMPP server handling authentication and signaling
4. **Nginx**: Reverse proxy handling HTTPS and WebSocket
5. **Jicofo**: Conference controller managing media stream routing

## Step 1: Server Preparation

### 1.1 Choosing a VPS Provider

Recommended VPS providers (sorted by value):

| Provider | Starting Price | Features |
|----------|---------------|----------|
| **Hetzner** | €4.51/mo | Ultra-low European pricing, powerful performance |
| **RamNode** | $5/mo | Unlimited bandwidth, exceptional value |
| **CloudCone** | $4.5/mo | US nodes, stable and reliable |
| **BandwagonHost** | $29/year | China-friendly, CN2 routing |
| **DigitalOcean** | $6/mo | Rich ecosystem, excellent documentation |

### 1.2 System Installation

Debian 12 or Ubuntu 22.04 LTS recommended:

```bash
# SSH into your server
ssh root@your-vps-ip

# Update the system
apt update && apt upgrade -y

# Install basic tools
apt install -y curl wget git vim htop net-tools

# Set hostname
hostnamectl set-hostname meet.yourdomain.com
```

## Step 2: Domain and SSL Certificate

### 2.1 DNS Configuration

Add an A record in your domain management panel:

```
meet.yourdomain.com  →  Your_VPS_IP
```

### 2.2 Install Nginx and Certbot

```bash
# Install Nginx
apt install -y nginx certbot python3-certbot-nginx

# Create Nginx configuration
cat > /etc/nginx/sites-available/jitsi << 'EOF'
server {
    listen 80;
    server_name meet.yourdomain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name meet.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/meet.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/meet.yourdomain.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    # Security headers
    add_header X-Frame-Options SAMEORIGIN always;
    add_header X-Content-Type-Options nosniff always;
    add_header Strict-Transport-Security "max-age=31536000" always;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF

ln -s /etc/nginx/sites-available/jitsi /etc/nginx/sites-enabled/
nginx -t && systemctl restart nginx

# Request SSL certificate
certbot --nginx -d meet.yourdomain.com --non-interactive --agree-tos -m your@email.com
```

## Step 3: Docker Deployment of Jitsi Meet

### 3.1 Install Docker

```bash
# Install Docker
curl -fsSL https://get.docker.com | sh

# Add user to docker group
usermod -aG docker $USER

# Start Docker
systemctl enable docker && systemctl start docker
```

### 3.2 Clone Jitsi Meet Project

```bash
# Create working directory
mkdir -p /opt/jitsi && cd /opt/jitsi

# Clone jitsi/docker-jitsi-meet
git clone https://github.com/jitsi/docker-jitsi-meet.git
cd docker-jitsi-meet

# Copy environment template
cp .env.example .env
```

### 3.3 Configure Environment Variables

Edit the `.env` file:

```bash
# =============== Core Configuration ===============
# Domain
DOMAIN=meet.yourdomain.com

# Randomly generated security passwords (required)
JITSI_METEOR_INTERNAL_SECRET=MbEiVsHbcspvFgzFs
JICOFO_AUTH_PASSWORD=Kns4xJh7Qz9Km2Lp
PROSODY_AUTH_PASSWORD=Lp8Nx5Qw2Yz7Km3J

# Generate random passwords
# openssl rand -hex 16

# =============== JVB Configuration ===============
# Media bridge configuration
JVB_ADVERTISE_IPS=
JVB_STUN_SERVERS=stun.l.google.com:19302,stun1.l.google.com:19302

# =============== Recording Configuration (Optional) ===============
# ENABLE_RECORDING=1
# RECORDING_STORAGE_PATH=/opt/jitsi/recordings

# =============== Security Configuration ===============
# Enable E2E encryption (optional, increases CPU load)
# ENABLE_ENCRYPTION=1
```

### 3.4 Start Services

```bash
# First-time startup (takes 5-10 minutes)
./install.sh

# Start Jitsi Meet
docker compose up -d

# Check running status
docker compose ps
docker compose logs -f jitsi-web
```

### 3.5 Access and Test

Open `https://meet.yourdomain.com` in your browser. You should see the Jitsi Meet interface.

Create a test meeting:
1. Enter a room name (e.g., `test-meeting`)
2. Enter your name
3. Click "Join"
4. Allow browser access to camera and microphone

## Step 4: Performance Optimization

### 4.1 Tune JVB Resource Limits

Edit `config/jvb/sip-communicator.properties`:

```properties
# Maximum participants
org.jitsi.videobridge.xmpp.user.shard.MAX_PARTICIPANTS=50

# Bandwidth limits (bps)
org.jitsi.videobridge.BANDWIDTH_VOICE=128000
org.jitsi.videobridge.BANDWIDTH_AUDIO=64000
org.jitsi.videobridge.BANDWIDTH_VGA_15=600000
org.jitsi.videobridge.BANDWIDTH_HD=1500000
org.jitsi.videobridge.BANDWIDTH_FHD=3000000

# Concurrent stream limits
org.jitsi.videobridge.ENABLE_STATISTICS=true
org.jitsi.videobridge.TLS_MAX_CONCURRENT_STREAMS=200
```

### 4.2 Nginx Optimization

Edit `/etc/nginx/nginx.conf`:

```nginx
worker_processes auto;
worker_rlimit_nofile 65535;

events {
    worker_connections 4096;
    multi_accept on;
    use epoll;
}

http {
    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    types_hash_max_size 2048;

    # Gzip compression
    gzip on;
    gzip_vary on;
    gzip_proxied any;
    gzip_comp_level 6;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml;

    # Timeout optimization
    client_body_timeout 12;
    client_header_timeout 12;
    send_timeout 10;
}
```

### 4.3 System-Level Optimization

```bash
# Edit /etc/sysctl.conf
cat >> /etc/sysctl.conf << 'EOF'
# Network optimization
net.core.somaxconn = 65535
net.ipv4.tcp_max_syn_backlog = 8192
net.ipv4.tcp_tw_reuse = 1
net.ipv4.ip_local_port_range = 1024 65535

# File descriptors
fs.file-max = 65535
fs.nr_open = 65535

# Memory optimization
vm.swappiness = 10
vm.dirty_ratio = 10
vm.dirty_background_ratio = 5
EOF

sysctl -p
```

## Step 5: Security Hardening

### 5.1 Enable E2E Encryption

Enable in `.env`:

```bash
ENABLE_ENCRYPTION=1
```

Then restart:

```bash
docker compose down && docker compose up -d
```

### 5.2 Configure Password Protection

Jitsi Meet supports room password protection. Users can set passwords when creating a meeting.

### 5.3 Rate Limiting

Edit `config/jicofo/sip-communicator.properties`:

```properties
# Maximum new sessions per minute
org.jitsi.jicofo.bridge.channel-per-busy-period=10
org.jitsi.jicofo.session-per-channel-per-busy-period=5
```

### 5.4 Firewall Rules

```bash
# Install UFW
apt install -y ufw

# Configure firewall
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp       # SSH
ufw allow 80/tcp       # HTTP
ufw allow 443/tcp      # HTTPS
ufw allow 10000/udp    # JVB media port
ufw allow 5349/tcp     # JVB TCP fallback
ufw enable

# Check status
ufw status verbose
```

## Step 6: Feature Enhancement

### 6.1 Enable Meeting Recording

```bash
# Enable recording in .env
ENABLE_RECORDING=1

# Create recording directory
mkdir -p /opt/jitsi/recordings
chmod 755 /opt/jitsi/recordings
```

Recordings are saved in MP4 format to `/opt/jitsi/recordings/`.

### 6.2 LDAP/AD Integration

```bash
# Configure LDAP in .env
ENABLE_AUTH=1
ENABLE_GUESTS=1
LDAP_URL=ldap://ldap.example.com
LDAP_BASE_DC=dc=example,dc=com
LDAP_BIND_DN=cn=admin,dc=example,dc=com
LDAP_BIND_PW=your_ldap_password
LDAP_FILTER=(uid=$username)
```

Then restart the services to apply LDAP configuration.

### 6.3 Multi-Server Cluster Deployment

For large-scale usage, consider cluster deployment:

```
                    ┌─────────────┐
                    │   Nginx     │
                    │ (Load Balancer)│
                    └──────┬──────┘
                           │
           ┌───────────────┼───────────────┐
           │               │               │
    ┌──────▼──────┐ ┌─────▼──────┐ ┌─────▼─────┐
    │  JVB Node 1 │ │ JVB Node 2 │ │ JVB Node 3│
    │ (Media Relay)│ │            │ │           │
    └─────────────┘ └────────────┘ └───────────┘
           │               │               │
           └───────────────┼───────────────┘
                           │
                    ┌──────▼──────┐
                    │  Prosody    │
                    │ (Signaling)  │
                    └─────────────┘
```

## Cost Comparison: Self-Hosted vs Cloud Services

| Solution | Monthly Cost | Participants | Features |
|----------|-------------|--------------|----------|
| **Zoom Free** | $0 | 40 min/session | Basic features |
| **Zoom Pro** | $15/person/month | Unlimited | Cloud recording |
| **Google Meet** | $6/person/month | 100 people | GSuite integration |
| **Self-Hosted Jitsi** | VPS cost | Depends on config | All features |

Using Hetzner CPX31 as an example (€4.51/mo, 2 vCPU, 2GB RAM):
- Supports 10-15 simultaneous conference participants
- No duration limits
- No per-participant fees
- Fully private

## Troubleshooting

### Issue 1: Video Connection Failed

```bash
# Check JVB status
docker compose logs jitsi-videobridge

# Check firewall
ufw status

# Confirm UDP 10000 port is open
netstat -ulnp | grep jvb
```

### Issue 2: Audio Problems

```bash
# Check audio configuration
docker compose logs jitsi-jicofo | grep -i audio

# Test audio in browser
# Open https://your-domain.com/test-audio
```

### Issue 3: Server Out of Memory

```bash
# Check memory usage
free -h

# Limit per-user bandwidth
# Edit config/jvb/sip-communicator.properties
org.jitsi.videobridge.BANDWIDTH_VGA_15=300000
```

### Issue 4: SSL Certificate Expiry

```bash
# Automatic renewal
certbot renew --dry-run

# Set up cron job
echo "0 3 * * * certbot renew --quiet" | crontab -
```

## Summary

Self-hosting Jitsi Meet is a worthwhile investment. Once configured, you can:

- ✅ **Zero monthly fees**: No Zoom/Teams subscription costs
- ✅ **Data privacy**: All meeting data stays on your server
- ✅ **Unlimited duration**: No more 40-minute limits
- ✅ **Feature-complete**: Screen sharing, recording, chat, virtual backgrounds
- ✅ **Easy maintenance**: Docker deployment, one-click updates

For small teams (10-50 people), a single $5-10/month VPS can handle daily meeting needs, saving hundreds to thousands annually compared to cloud service per-seat pricing.

---

**Further Reading**:
- [Jitsi Meet Official Documentation](https://jitsi.github.io/handbook/)
- [Docker-Jitsi-Meet GitHub](https://github.com/jitsi/docker-jitsi-meet)
- [Jitsi Performance Tuning Guide](https://jitsi.github.io/handbook/docs/performance)
