---
title: "Cloudflare Tunnel Zero-Port-Forwarding: Expose Internal Services Without a Public IP"
description: "A complete guide to exposing your internal services to the internet using Cloudflare Tunnel — no firewall ports, no public IP required. Covers Zero Trust mode, Warp client, auto-certificates, and multi-service routing."
date: 2026-06-22T10:00:00+08:00
lastmod: 2026-06-22T10:00:00+08:00
slug: "cloudflare-tunnel-zero-port-forwarding"
tags: ["Cloudflare", "Tunnel", "Zero Trust", "Reverse Proxy", "No Public IP", "Docker", "Cybersecurity", "Self-hosting"]
categories: ["Network Architecture"]
draft: false
image: /images/posts/cloudflare-tunnel-zero-port-forwarding/featured.png
aliases: [/en/post/cloudflare-tunnel-zero-port-forwarding/]
---

## Why Cloudflare Tunnel?

For self-hosting enthusiasts, a common pain point is: **how do I access my home NAS, Home Assistant, or private services from outside?**

Traditional approaches include:

- **Port Forwarding**: Open ports on your router, expose your public IP — high security risk
- **DDNS + Port Mapping**: Dynamic DNS with port forwarding, but still exposes service ports
- **FRP / Ngrok**: Requires a relay server or third-party dependency, high latency and single point of failure

**Cloudflare Tunnel** offers a completely new approach: **no ports need to be opened, no public IP required**. All traffic is tunneled through Cloudflare's secure global network.

## Core Concept

Cloudflare Tunnel works differently from traditional reverse proxies:

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   User Browser│────▶│  Cloudflare CDN  │────▶│  Cloudflared    │
│             │     │  (Global Edge)     │     │  (Your Server)  │
└─────────────┘     └──────────────────┘     └────────┬────────┘
                                                       │
                                                       ▼
                                              ┌─────────────────┐
                                              │  Internal Service│
                                              │  (Localhost)     │
                                              │  :8080 / :3000   │
                                              └─────────────────┘
```

Key differences:
- **Outbound only**: `cloudflared` initiates an encrypted connection to Cloudflare edge (outbound-only)
- **No inbound rules**: Firewall doesn't need any open ports
- **DDoS protection**: Traffic is cleaned by Cloudflare's global network first
- **Automatic HTTPS**: Free SSL certificates managed by Cloudflare

## Prerequisites

1. **A domain name**: Registered or transferred to Cloudflare (free plan works)
2. **A server**: Any device that can run Docker — VPS, Raspberry Pi, NAS, etc.
3. **Docker environment**: Docker Compose recommended for management

## Option 1: Zero Trust Dashboard (Recommended)

This is Cloudflare's official modern approach, managing all tunnels through the Zero Trust panel.

### Step 1: Create a Zero Trust Organization

1. Visit [one.cloudflare.com](https://one.cloudflare.com)
2. Log in with your Cloudflare account
3. Click **"Start free trial"** to create a Zero Trust organization (free plan is sufficient)

### Step 2: Create a Tunnel

```bash
# Install cloudflared CLI
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o cloudflared
chmod +x cloudflared
sudo mv cloudflared /usr/local/bin/

# Authenticate (opens browser for login)
cloudflared tunnel login
```

After running `cloudflared tunnel login`, a browser window opens for Cloudflare authorization. After granting permission, a `cert.pem` file is created in the current directory.

### Step 3: Create Tunnel and Get Tunnel ID

```bash
# Create a tunnel named selfvps-tunnel
cloudflared tunnel create selfvps-tunnel

# Output looks like:
# Created tunnel selfvps-tunnel with id abc12345-def6-7890-ghij-klmnopqrstuv
```

Save the Tunnel ID from the output.

### Step 4: Configure Routing Rules

Create the config file `~/.cloudflared/config.yml`:

```yaml
tunnel: abc12345-def6-7890-ghij-klmnopqrstuv
credentials-file: /root/.cloudflared/abc12345-def6-7890-ghij-klmnopqrstuv.json

# Routing rules: map domains to tunnel
ingress:
  # Home Assistant
  - hostname: ha.selfvps.net
    service: http://localhost:8123
  
  # Your blog
  - hostname: blog.selfvps.net
    service: http://localhost:1313
  
  # NAS web interface
  - hostname: nas.selfvps.net
    service: http://localhost:5000
  
  # Default rule: 404
  - service: http_status:404
```

### Step 5: Register Tunnel and Start

```bash
# Register routes to Cloudflare DNS
cloudflared tunnel route dns selfvps-tunnel ha.selfvps.net
cloudflared tunnel route dns selfvps-tunnel blog.selfvps.net
cloudflared tunnel route dns selfvps-tunnel nas.selfvps.net

# Start the tunnel
cloudflared tunnel run selfvps-tunnel
```

### Step 6: Set Up as System Service

Create `/etc/systemd/system/cloudflared.service`:

```ini
[Unit]
Description=Cloudflare Tunnel
After=network.target

[Service]
Type=exec
ExecStart=/usr/local/bin/cloudflared tunnel --config /root/.cloudflared/config.yml run selfvps-tunnel
Restart=on-failure
RestartSec=5
Environment=NO_UPDATE_NOTIFIER=1

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable cloudflared
sudo systemctl start cloudflared
sudo systemctl status cloudflared
```

## Option 2: Docker Compose One-Click Deployment

Ideal for users who don't want to manually manage systemd services.

### Basic docker-compose.yml

```yaml
version: "3.8"

services:
  cloudflared:
    image: cloudflare/cloudflared:latest
    container_name: cloudflared
    restart: unless-stopped
    volumes:
      - ./cloudflared-config:/etc/cloudflared
      - cloudflared-certs:/root/.cloudflared
    command: tunnel --config /etc/cloudflared/config.yml run
    networks:
      - tunnel-net

  homepage:
    image: ghcr.io/gethomepage/homepage:latest
    container_name: homepage
    restart: unless-stopped
    ports:
      - "3000:3000"
    volumes:
      - ./homepage/config:/app/config

networks:
  tunnel-net:
    driver: bridge
```

### Simplified Token Mode

If you've already created a tunnel via the Zero Trust Dashboard, you can use token mode — no config file needed:

```bash
# Get the token from Zero Trust Dashboard > Tunnels page
docker run -d \
  --name cloudflared \
  --restart unless-stopped \
  cloudflare/cloudflared:latest \
  tunnel --no-autoupdate run --token YOUR_TOKEN_HERE
```

The downside of token mode is that **all routing rules must be configured in the Zero Trust Dashboard web UI**, which is less flexible than a local config file.

## Option 3: Zero Trust Dashboard Web Configuration

For users who prefer not to touch the command line.

1. Log in to [one.cloudflare.com](https://one.cloudflare.com)
2. Navigate to **Networks → Tunnels**
3. Click **Create a tunnel**
4. Select **Cloudflared** as connector
5. Run the provided installation command on your server
6. Configure Public Hostname and Service URL in the web UI

Dashboard configuration fields:
- **Public Hostname**: Enter subdomain (e.g., `app.selfvps.net`)
- **Subdomain**: Choose your domain
- **Domain**: Select your registered domain
- **Service Type**: Choose `http` or `https`
- **Service URL**: Fill in internal address (e.g., `localhost:3000`)

## Advanced Configurations

### Basic Authentication (Basic Auth)

Protect your services from unauthorized access:

```yaml
ingress:
  - hostname: secure.selfvps.net
    service: http://localhost:8080
    originRequest:
      noTLSVerify: true
```

Then in the Zero Trust Dashboard:
1. Go to **Access → Applications**
2. Click **Add an application**
3. Select **Self-hosted**
4. Configure **Application domain** to your subdomain
5. Set **Policy**: choose email authentication, OAuth, etc.

### Enable WAF Rules

Cloudflare Tunnel comes with a built-in Web Application Firewall:

1. Navigate to **Security → WAF**
2. Add custom rules for your domain
3. Examples: block specific IP ranges, rate-limit requests

### Multi-Region Deployment (High Availability)

```yaml
# Run the same cloudflared on multiple servers
# Zero Trust Dashboard automatically load balances
cloudflared tunnel run selfvps-tunnel
```

When one server's cloudflared goes offline, traffic is automatically routed to other healthy connectors.

### Monitor Tunnel Status

```bash
# Check tunnel status
cloudflared tunnel info selfvps-tunnel

# View routes
cloudflared tunnel list-routes selfvps-tunnel

# View logs
journalctl -u cloudflared -f
```

## Security Best Practices

| Practice | Description |
|----------|-------------|
| **Least privilege** | Only expose necessary services, never admin panels |
| **Enable Access Policy** | Add authentication for sensitive services |
| **Rotate tokens regularly** | Update tunnel credentials every 90 days |
| **Use dedicated domains** | Don't expose internal services on your main domain |
| **Enable DDoS protection** | Included with Cloudflare free plan |
| **Monitor traffic** | Check flow logs in Zero Trust Dashboard |

## Frequently Asked Questions

### Q: What if the tunnel disconnects?

Check the cloudflared process status:
```bash
sudo systemctl status cloudflared
sudo journalctl -u cloudflared -n 50 --no-pager
```

Common causes:
- Server rebooted but service didn't auto-start
- Unstable network connection causing tunnel drops
- Credential file expired or deleted

### Q: Can I use a domain not on Cloudflare?

No. Cloudflare Tunnel requires the domain to be resolved through Cloudflare DNS. If your domain is hosted elsewhere, you need to change the Nameservers to Cloudflare's NS records.

### Q: How is the performance?

- Latency increases by approximately 10-50ms (depends on distance to Cloudflare edge)
- Throughput is limited by Cloudflare's free plan (100Gbps shared bandwidth)
- More than sufficient for most self-hosting scenarios

### Q: What are the free plan limitations?

- Unlimited tunnels
- Unlimited bandwidth (with fair usage policy)
- All security features included
- Custom SSL certificate upload not supported (uses Cloudflare-provided certificates)

## Summary

Cloudflare Tunnel is the **most elegant solution** for exposing internal services in self-hosting scenarios:

- ✅ **Zero port openings**: No firewall rules needed
- ✅ **Free**: Cloudflare free plan is more than enough
- ✅ **Secure**: Built-in DDoS protection, WAF, automatic HTTPS
- ✅ **Simple**: Deploy in minutes
- ✅ **Reliable**: Global edge network with high availability

For any self-hosting user looking to securely expose internal services, Cloudflare Tunnel is the go-to choice.

---

**Related Articles:**
- [Headscale: Self-Hosted Tailscale Control Plane](/en/post/headscale-self-hosted-tailscale/)
- [VPS Monitoring: Complete Prometheus + Grafana Deployment](/en/post/vps-monitoring-prometheus-grafana/)
- [Vaultwarden Password Manager Deployment Guide](/en/post/vaultwarden-deployment-guide/)
