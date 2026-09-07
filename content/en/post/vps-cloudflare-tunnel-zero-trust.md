---
title: "VPS Port-Free Access: Complete Cloudflare Tunnel Zero-Trust Guide"
description: "Say goodbye to port forwarding and firewall exposure. Use Cloudflare Tunnel for secure, zero-trust access to your VPS services — no public IP needed, auto HTTPS, perfect for self-hosting enthusiasts"
date: 2026-09-07T10:00:00+08:00
lastmod: 2026-09-07T10:00:00+08:00
slug: "vps-cloudflare-tunnel-zero-trust"
image: /images/posts/vps-cloudflare-tunnel-zero-trust/featured.png
tags: ["Cloudflare", "Tunnel", "Zero Trust", "Secure Access", "Self-hosted", "VPS", "No Public IP", "DDNS Alternative"]
categories: ["Network Security"]
aliases: [/en/post/vps-cloudflare-tunnel-zero-trust/]
---

## Introduction

You have a VPS running various self-hosted services — Nextcloud, Home Assistant, Pi-hole, Gitea... But have you ever faced these frustrations?

- You had to expose ports to the public internet just to access your services, getting scanned and attacked daily;
- Without a public IP, you rely on DDNS + port forwarding, which is complex and unstable;
- SSL certificate management is a pain — Let's Encrypt renewals occasionally fail;
- You want to add access control to your services but find no straightforward solution.

**Cloudflare Tunnel** (formerly Argon Tunnel) solves all of these problems elegantly. It runs a lightweight client `cloudflared` on your VPS that proactively establishes an encrypted tunnel to Cloudflare's edge network. Your service ports stay closed forever. Users access via `https://your-service.your-domain.com` with automatic HTTPS encryption, plus built-in Cloudflare DDoS protection and WAF capabilities.

This guide takes you from zero to fully operational Cloudflare Tunnel, covering: basic installation, multi-service configuration, access control, Zero Trust integration, and troubleshooting.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        User Browser                            │
│                    https://app.your-domain.com                  │
└──────────────────────┬──────────────────────────────────────────┘
                       │ HTTPS (Cloudflare Edge)
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Cloudflare Edge Network                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────────┐   │
│  │  DDoS    │  │   WAF    │  │  CDN     │  │  Access/Zero  │   │
│  │ Shield   │  │ Firewall │  │  Cache   │  │   Trust       │   │
│  └──────────┘  └──────────┘  └──────────┘  └───────────────┘   │
└──────────────────────┬──────────────────────────────────────────┘
                       │ Encrypted Tunnel (QUIC/TCP)
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Your VPS Network                            │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │              cloudflared Client                          │    │
│  │  ┌───────────┐  ┌───────────┐  ┌───────────┐           │    │
│  │  │ Nextcloud │  │ HomeAssit │  │  Pi-hole  │           │    │
│  │  │ :8080     │  │ :8123     │  │ :8081     │           │    │
│  │  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘           │    │
│  │        └───────────────┴───────────────┘                │    │
│  │                      Local Routing                       │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
│  🔥 All inbound ports CLOSED! Only outbound connections needed   │
└─────────────────────────────────────────────────────────────────┘
```

Key points:
- **Outbound only**: `cloudflared` initiates connections to Cloudflare — no inbound ports required
- **Zero-trust architecture**: Access control managed entirely on Cloudflare's side
- **Automatic HTTPS**: Cloudflare provisions and manages certificates
- **Multi-service routing**: One Tunnel can route to multiple local services

---

## Prerequisites

1. **A domain name**: Registered and DNS hosted on Cloudflare (free tier works)
2. **A VPS**: Linux system (Debian 12 / Ubuntu 22.04+ recommended)
3. **Cloudflare account**: Free sign-up at https://dash.cloudflare.com
4. **Basic Linux command knowledge**

---

## Step 1: Install cloudflared

### Method 1: Official APT Repository (Recommended)

```bash
# Debian/Ubuntu
sudo apt install -y curl gnupg
curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg.key | sudo tee /usr/share/keyrings/cloudflare-main.gpg > /dev/null

echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflare-main debian main" | sudo tee /etc/apt/sources.list.d/cloudflare.list

sudo apt update && sudo apt install cloudflared
```

### Method 2: Direct Binary Download

```bash
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
sudo mv cloudflared-linux-amd64 /usr/local/bin/cloudflared
sudo chmod +x /usr/local/bin/cloudflared
```

Verify installation:

```bash
cloudflared --version
# cloudflared version 2024.x.x (built ...)
```

---

## Step 2: Create a Tunnel

### 2.1 Login to Cloudflare

```bash
cloudflared tunnel login
```

This outputs a URL. Open it in your browser, select your domain and authorize. After successful authorization, a `cert.pem` file is created in the current directory.

### 2.2 Create the Tunnel

```bash
# Create tunnel (save the generated Tunnel ID)
cloudflared tunnel create vps-primary

# Output example:
# Created tunnel vps-primary -> <TUNNEL_ID>
```

### 2.3 Configure DNS CNAME

```bash
cloudflared tunnel route dns vps-primary your-domain.com
```

This creates a CNAME record in your DNS: `your-domain.com → <TUNNEL_ID>.cfargotunnel.com`

You can also add it manually:
- Type: CNAME
- Name: `@` (root domain)
- Target: `<TUNNEL_ID>.cfargotunnel.com`

---

## Step 3: Configure Route Rules

Edit the config file `~/.cloudflared/config.yml`:

```yaml
# Basic configuration
tunnel: <TUNNEL_ID>
credentials-file: /root/.cloudflared/<TUNNEL_ID>.json

# Logging
loglevel: info
logdir: /var/log/cloudflared

# Route rules - map different subdomains to different local services
ingress:
  # Main app / Nextcloud
  - hostname: app.your-domain.com
    service: http://localhost:8080

  # Home Assistant
  - hostname: home.your-domain.com
    service: http://localhost:8123

  # Pi-hole admin interface
  - hostname: pihole.your-domain.com
    service: http://localhost:8081

  # Gitea Git service
  - hostname: git.your-domain.com
    service: http://localhost:3000

  # Default 404
  - service: http_status:404
```

Create log directory and set permissions:

```bash
sudo mkdir -p /var/log/cloudflared
sudo chown root:root /var/log/cloudflared
```

---

## Step 4: Register as System Service

### Create systemd unit

```bash
sudo tee /etc/systemd/system/cloudflared.service > /dev/null <<'EOF'
[Unit]
Description=Cloudflare Tunnel
After=network-online.target

[Service]
Type=notify
ExecStart=/usr/local/bin/cloudflared tunnel --no-autoupdate run vps-primary
Environment="CF_TUNNEL_METRICS=localhost:2000"
Restart=on-failure
RestartSec=10
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF
```

Start and enable auto-start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable cloudflared
sudo systemctl start cloudflared

# Check status
sudo systemctl status cloudflared
```

Expected output:
```
● cloudflared.service - Cloudflare Tunnel
   Active: active (running) since Mon 2026-09-07 10:00:00 +08; 5s ago
 Main PID: 1234 (cloudflared)
    Tasks: 10 (limit: 4915)
   Memory: 25.0M
```

### Check Tunnel Status

```bash
cloudflared tunnel list
cloudflared tunnel info vps-primary
```

---

## Step 5: Configure Access Control (Recommended)

### 5.1 Using Cloudflare Access (Zero Trust)

Visit https://one.dash.cloudflare.com, go to **Access → Applications**:

1. Click **Add an application**
2. Select **Self-hosted**
3. Set Application domain: `app.your-domain.com`
4. Choose a Policy, for example:
   - **Block all** (block everything)
   - **Allow email domains** (allow only specific email domains)
   - **Allow specific emails** (allow only specific email addresses)

### 5.2 Simple Password Protection (Without Cloudflare Access)

If you just need basic password protection, add a reverse proxy in front of your service:

```nginx
# Nginx reverse proxy + basic auth
server {
    listen 8080;
    server_name app.your-domain.com;

    location / {
        proxy_pass http://localhost:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;

        # Basic authentication
        auth_basic "Restricted Access";
        auth_basic_user_file /etc/nginx/.htpasswd;
    }
}
```

Generate htpasswd file:

```bash
sudo apt install apache2-utils
sudo htpasswd -c /etc/nginx/.htpasswd admin
```

### 5.3 IP Whitelist (Simplest Approach)

```bash
# Allow only your IP to access local ports
sudo iptables -A INPUT -p tcp --dport 8080 -s YOUR_IP/32 -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 8080 -j DROP
```

---

## Step 6: Health Checks & Monitoring

### 6.1 Built-in Monitoring Endpoints

Cloudflare Tunnel includes HTTP monitoring endpoints:

```bash
# Check tunnel health
curl http://localhost:2000/ready
curl http://localhost:2000/status

# View connection metrics
curl http://localhost:2000/metrics
```

### 6.2 Prometheus + Grafana Integration

If you already have Prometheus, add cloudflared metrics:

```yaml
# Add to prometheus.yml
scrape_configs:
  - job_name: 'cloudflared'
    static_configs:
      - targets: ['localhost:2000']
```

Grafana Dashboard ID: `19397` (official Cloudflare Tunnel dashboard)

### 6.3 Health Check Alerting

```bash
# Simple monitoring script
#!/bin/bash
# /usr/local/bin/check-tunnel.sh

STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:2000/ready)

if [ "$STATUS" != "200" ]; then
    echo "Cloudflare Tunnel unhealthy! Status: $STATUS"
    # Send alert (Telegram/DingTalk/Email)
    curl -X POST "https://api.telegram.org/bot<TOKEN>/sendMessage" \
         -d "chat_id=<CHAT_ID>" \
         -d "text=🚨 Cloudflare Tunnel down!"
fi
```

Add to crontab for minute-by-minute checks:

```bash
* * * * * /usr/local/bin/check-tunnel.sh
```

---

## Step 7: Multi-Tunnel High Availability

For production environments, run Tunnels on multiple VPS instances for redundancy:

```bash
# On the second VPS, install cloudflared the same way
# Run with the same Tunnel ID
cloudflared tunnel --no-autoupdate run vps-primary
```

Cloudflare automatically load-balances across multiple Tunnel endpoints. If one VPS goes down, the other takes over seamlessly.

You can also specify backup routes with the `--url` parameter:

```bash
cloudflared tunnel run vps-primary --url https://your-backup-service.com
```

---

## Troubleshooting

### Issue 1: Tunnel Connection Unstable

```bash
# Check detailed logs
sudo journalctl -u cloudflared -f

# Verify network connectivity
curl -I https://region1.tunnel.cfargotunnel.com
```

For VPS in China, you may need to use the China-region endpoint:
```bash
cloudflared tunnel --region cn run vps-primary
```

### Issue 2: DNS Resolution Failure

```bash
# Check CNAME record
dig your-domain.com CNAME
# Should return: your-domain.com. CNAME <TUNNEL_ID>.cfargotunnel.com.

# Flush local DNS cache
sudo systemd-resolve --flush-caches
```

### Issue 3: Service Returns 502/503

Check that ingress routes in `config.yml` correctly point to local services:

```bash
# Verify local services are running
curl http://localhost:8080
curl http://localhost:8123

# Check cloudflared logs
sudo journalctl -u cloudflared -n 50
```

Common causes: local service not running, wrong port configuration, firewall blocking loopback.

### Issue 4: Certificate Problems

Cloudflare Tunnel manages certificates automatically. Usually no manual intervention needed. If you encounter certificate errors:

```bash
# Re-login to refresh certificate
cloudflared tunnel login
# Restart service
sudo systemctl restart cloudflared
```

---

## Cost Analysis

| Item | Cost |
|------|------|
| Cloudflare Free Tier | $0/month (includes Tunnel) |
| Domain (if needed) | ~$8/year |
| VPS | Already have |
| **Total** | **≈ $0/month (excluding domain)** |

Compared to traditional approaches:
- No public IP needed (saves $5-20/month)
- No DDNS service required (saves $0-3/month)
- No manual SSL certificate management (saves time)
- Built-in DDoS protection (worth $10+/month)

---

## Summary

Cloudflare Tunnel is an essential tool for self-hosting enthusiasts:

1. **Zero port exposure**: All service ports stay closed, drastically reducing attack surface
2. **Automatic HTTPS**: No manual Let's Encrypt configuration needed
3. **Free to use**: Cloudflare's free tier fully supports Tunnels
4. **Enterprise-grade security**: DDoS protection + WAF + optional Zero Trust access control
5. **Simple to deploy**: One command to get running

Go configure your first Tunnel now — your VPS will thank you.

---

## References

- [Cloudflare Tunnel Documentation](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/)
- [cloudflared GitHub](https://github.com/cloudflare/cloudflared)
- [Cloudflare Zero Trust](https://one.dash.cloudflare.com)
