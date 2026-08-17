---
title: "Cloudflare Tunnel Complete Guide: Expose Local Services Without Public IP or Port Forwarding"
description: "Set up Cloudflare Tunnel (cloudflared) from scratch to expose local VPS services to the internet without a public IP. Supports HTTP/HTTPS, SSH, databases, and intranet penetration — more secure and free compared to Ngrok, simpler than frp."
date: 2026-08-17T10:00:00+08:00
lastmod: 2026-08-17T10:00:00+08:00
slug: "cloudflare-tunnel-zero-trust-network"
tags: ["Cloudflare", "Tunnel", "Port Forwarding", "Zero Trust", "VPS", "Self-Hosted", "Network Security", "Docker", "frp Alternative", "Intranet Penetration"]
categories: ["Deployment Guides"]
draft: false
image: /images/posts/cloudflare-tunnel-zero-trust-network/featured.png
aliases: [/en/post/cloudflare-tunnel-zero-trust-network/]
---

## Why Cloudflare Tunnel?

In self-hosting and VPS operations, we often need to expose local services to the internet: personal blogs, NAS, cameras, Home Assistant, or even SSH remote desktops. Traditional solutions fall into two categories:

1. **Port Forwarding**: Open ports on your router/firewall pointing to an internal IP. Problems: exposes your public IP, vulnerable to scanning and attacks, requires dynamic DNS.
2. **Ngrok/frp and similar tools**: Require setting up a relay server that you must maintain yourself.

**Cloudflare Tunnel (cloudflared)** is the third option — it connects your services to Cloudflare's edge network through an encrypted tunnel, **eliminating the need for a public IP, port forwarding, or a relay server**. All traffic passes through Cloudflare's DDoS protection and WAF, making it significantly more secure than traditional approaches.

---

## How Cloudflare Tunnel Works

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────┐
│  Your Service │──▶│  cloudflared      │──▶│  Cloudflare  │
│  (Local VPS)  │     │  (Tunnel Client) │     │  Edge Network│
└─────────────┘     └──────────────────┘     └──────┬──────┘
                                                     │
                                                     ▼
                                               ┌─────────────┐
                                               │  Internet Users │
                                               │  *.yourdomain.com│
                                               └─────────────┘
```

Key advantages:
- **Outbound-only connection**: cloudflared initiates connections to Cloudflare edges — inbound ports are completely closed
- **Zero-trust architecture**: No ports to open, attack surface minimized
- **Free HTTPS**: Automatic TLS certificate provisioning, no Let's Encrypt needed
- **DDoS protection**: All traffic flows through Cloudflare's global CDN

---

## Step 1: Prerequisites

### 1.1 Cloudflare Account and Domain

Sign up at [cloudflare.com](https://cloudflare.com), then delegate your domain's DNS to Cloudflare (change nameservers at your domain registrar to Cloudflare's NS records).

### 1.2 Install cloudflared

```bash
# Ubuntu/Debian
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb -o cloudflared.deb
sudo dpkg -i cloudflared.deb

# Or one-liner install
curl -s https://bin.equinox.io/c/bNyj1mQVY4c/cloudflared-stable-linux-amd64.tgz | sudo tar -xzf - -C /usr/local/bin

# Verify installation
cloudflared --version
```

---

## Step 2: Authentication and Tunnel Creation

### 2.1 Login to Cloudflare

```bash
cloudflared tunnel login
```

This generates an authentication URL. Open it in your browser, select your domain to authorize. After authorization, credentials are saved to `~/.cloudflared/*.json`.

### 2.2 Create a Tunnel

```bash
# Create a named tunnel
cloudflared tunnel create my-tunnel

# Note the Tunnel ID (needed later)
# Output: Tunnel credentials saved to /root/.cloudflared/<uuid>.json
# Tunnel ID: abcdef12-3456-7890-abcd-ef1234567890
```

### 2.3 Create DNS Records

```bash
# List your tunnels
cloudflared tunnel list

# Add CNAME in Cloudflare DNS
# For example, to point http://app.yourdomain.com to the tunnel:
# Name: app
# Type: CNAME
# Target: abcdef12-3456-7890-abcd-ef1234567890.trycloudflare.com
```

> **Tip**: You can also use `cloudflared tunnel route dns my-tunnel` to automatically add DNS records.

---

## Step 3: Configure Routes

### 3.1 Configuration File (Recommended)

Create `~/.cloudflared/config.yml`:

```yaml
tunnel: abcdef12-3456-7890-abcd-ef1234567890
credentials-file: /root/.cloudflared/<uuid>.json

ingress:
  # Rule 1: Expose local web service
  - hostname: app.yourdomain.com
    service: http://localhost:3000
  
  # Rule 2: Expose SSH (replaces traditional port forwarding)
  - hostname: ssh.yourdomain.com
    service: ssh://localhost:22
  
  # Rule 3: Expose database admin interface (with access control)
  - hostname: db.yourdomain.com
    service: http://localhost:8080
    originRequest:
      noTLSVerify: true
      http2Origin: false
  
  # Default rule: 404
  - service: http_status:404
```

### 3.2 Command Line (Simple Scenarios)

```bash
cloudflared tunnel route ip add 10.0.0.1  # Add IP route (optional)
cloudflared tunnel route dns add my-tunnel app.yourdomain.com  # Add DNS route
```

---

## Step 4: Start the Tunnel

### 4.1 Foreground Mode (Testing)

```bash
cloudflared tunnel run my-tunnel
```

Check logs to confirm tunnel is healthy:
```
$ cloudflared tunnel run my-tunnel
INFO  Connection xxx.x.xx.x:xxxxx is authenticated  via token
INFO  Certified tunnel hostname: abcdef.trycloudflare.com
INFO  Listening on https://app.yourdomain.com
```

### 4.2 Background Mode (Production)

#### Method 1: systemd Service (Recommended)

```bash
# Create systemd service
sudo tee /etc/systemd/system/cloudflared.service > /dev/null <<'EOF'
[Unit]
Description=Cloudflare Tunnel
After=network-online.target

[Service]
Type=notify
ExecStart=/usr/local/bin/cloudflared tunnel run --no-autoupdate my-tunnel
Restart=always
RestartSec=10
Environment=CF_TUNNEL_TOKEN=abcdef12-3456-7890-abcd-ef1234567890

[Install]
WantedBy=multi-user.target
EOF

# Start the service
sudo systemctl daemon-reload
sudo systemctl enable cloudflared
sudo systemctl start cloudflared

# Check status
sudo systemctl status cloudflared
journalctl -u cloudflared -f
```

#### Method 2: Docker

```bash
docker run -d \
  --name cloudflared \
  --restart unless-stopped \
  -v ~/.cloudflared:/home/user/.cloudflared \
  -e TUNNEL_TOKEN=abcdef12-3456-7890-abcd-ef1234567890 \
  cloudflare/cloudflared:latest \
  tunnel --no-autoupdate run my-tunnel
```

---

## Step 5: Security Enhancements

### 5.1 Enable Cloudflare Access (Zero Trust)

Configure in Cloudflare Dashboard → Zero Trust → Access → Applications:

- Set application rules (e.g., `*.yourdomain.com`)
- Choose authentication method: email verification, Google OAuth, GitHub OAuth, etc.
- Different subdomains can have different auth policies

```
Dashboard: Zero Trust → Networks → Tunnels
Select your tunnel → Edit → Enable "Access" policies
```

### 5.2 Configure WAF Rules

```
Dashboard → Security → WAF
Add rules for tunnel domains:
- Block common scanner User-Agents
- Restrict admin interfaces to specific IP ranges
- Enable Bot Fight Mode
```

### 5.3 Restrict Origin to Tunnel Only

In Cloudflare Dashboard → Network → Tunnel, enable **"Only allow traffic from Cloudflare Tunnels"**. This ensures that even if someone knows your server IP, they cannot access your services directly.

---

## Real-World Examples

### Example 1: Expose Home Assistant

```yaml
ingress:
  - hostname: home.yourdomain.com
    service: http://localhost:8123
  - service: http_status:404
```

### Example 2: Expose Syncthing WebUI

```yaml
ingress:
  - hostname: sync.yourdomain.com
    service: http://localhost:8384
  - service: http_status:404
```

### Example 3: Expose Database Admin (Adminer/phpMyAdmin)

```yaml
ingress:
  - hostname: dbadmin.yourdomain.com
    service: http://localhost:8080
    originRequest:
      noTLSVerify: true
  - service: http_status:404
```

> ⚠️ **Security Note**: Always enable Cloudflare Access authentication for database admin interfaces. Never expose them publicly without protection!

### Example 4: Multi-Service Routing (frp Alternative)

```yaml
ingress:
  - hostname: blog.yourdomain.com
    service: http://localhost:4000
  
  - hostname: wiki.yourdomain.com
    service: http://localhost:7777
  
  - hostname: monitor.yourdomain.com
    service: http://localhost:9090
  
  - hostname: ssh.yourdomain.com
    service: ssh://localhost:22
  
  - service: http_status:404
```

---

## Cloudflare Tunnel vs Alternatives Comparison

| Feature | Cloudflare Tunnel | frp | Ngrok | Tailscale |
|---------|-------------------|-----|-------|-----------|
| Public IP Required | **No** | Yes (relay server) | Yes (relay server) | **No** |
| Port Forwarding | **Not needed** | Required | Required | **Not needed** |
| Free Tier | **Unlimited** | Self-maintained | Limited | 64 devices |
| HTTPS | **Automatic** | Manual config | Automatic | Automatic |
| DDoS Protection | **Yes** | No | Partial | No |
| Access Control | **Zero Trust** | Self-built | Basic Auth | Self-built |
| Latency | Low (edge nodes) | Depends on relay | Medium | Low |
| Self-hosted services | ✅ | ✅ | ✅ | ❌ (P2P only) |

---

## Troubleshooting

### Problem 1: Tunnel Connection Failed

```bash
# Check credentials
ls -la ~/.cloudflared/

# Re-authenticate
cloudflared tunnel login
cloudflared tunnel route dns add my-tunnel app.yourdomain.com

# Validate configuration
cloudflared tunnel ingress validate
```

### Problem 2: DNS Resolution Incorrect

```bash
# Check CNAME record
dig app.yourdomain.com CNAME

# Should point to abcdef.trycloudflare.com
# Not directly to an IP address
```

### Problem 3: 502/503 Errors

Check if your local service is running:
```bash
# Test local access
curl http://localhost:3000

# Check tunnel logs
journalctl -u cloudflared -n 50
```

### Problem 4: Slow SSH Connection

Add timeout configuration in `~/.cloudflared/config.yml`:
```yaml
ingress:
  - hostname: ssh.yourdomain.com
    service: ssh://localhost:22
    originRequest:
      connectTimeout: 30s
      noHappyEyeballs: true
```

---

## Summary

Cloudflare Tunnel is the **most elegant solution for exposing self-hosted services**:

- ✅ **No public IP needed**: Say goodbye to port forwarding and dynamic DNS
- ✅ **Free and unlimited**: No cost, no data caps
- ✅ **Enterprise-grade security**: DDoS protection + Zero Trust access control
- ✅ **Simple to use**: One command to get started
- ✅ **Multi-protocol support**: HTTP, SSH, TCP, UDP all covered

For VPS self-hosting enthusiasts, Cloudflare Tunnel is essentially a must-have tool. Paired with Cloudflare's free CDN and SSL certificates, your self-hosted services can run securely and stably in any network environment.

Get started now: log into your Cloudflare Dashboard, create a Tunnel, and safely expose your services to the world!
