---
title: "Cloudflare Tunnels: Expose Your VPS Services Without Opening Ports"
description: "Safely expose Docker services on your VPS to the internet using Cloudflare Tunnels—no open ports, no public IP, no SSL certificates required"
date: 2026-06-06T10:00:00+08:00
lastmod: 2026-06-06T10:00:00+08:00
slug: "cloudflare-tunnels-vps"
image: /images/posts/cloudflare-tunnels-vps/featured.png
tags: ["Cloudflare", "Tunnels", "Cybersecurity", "VPS", "Docker", "Reverse Proxy", "Zero Trust", "Self-hosted"]
categories: ["Network Operations"]
aliases: [/en/post/cloudflare-tunnels-vps/]
---

## Introduction

Imagine you have a VPS running Home Assistant, Nextcloud, or a self-hosted blog. You want to access it from outside, but:

- Your ISP doesn't provide a public IPv4 address;
- You don't want to configure port forwarding on your router;
- You'd rather not deal with SSL certificates;
- Exposing SSH and web ports directly worries you.

**Cloudflare Tunnels** was built for exactly this. It installs a lightweight tunnel daemon (`cloudflared`) on your server that encrypts and forwards your services through Cloudflare's global edge network. **No inbound ports need to be opened**, and no public IP is required.

This guide walks you through setting up a complete Cloudflare Tunnels-based VPS exposure solution, working seamlessly with Docker.

---

## How It Works

```
[Browser] ←HTTPS→ [Cloudflare Edge] ←TLS→ [cloudflared Tunnel] ←HTTP→ [Your VPS Service]
```

1. You run `cloudflared` on your VPS, which proactively establishes TCP connections to Cloudflare's edge
2. Since the connection is **outbound-only**, your firewall doesn't need to allow any incoming ports
3. When a user sends an HTTPS request to Cloudflare, it's forwarded through the tunnel to your VPS
4. Both ends of the tunnel are encrypted, ensuring data security

### Key Advantages

| Feature | Traditional Approach | Cloudflare Tunnels |
|---------|---------------------|-------------------|
| Public IP required | ✅ Yes | ❌ No |
| Open inbound ports | ✅ Ports 80/443 | ❌ None |
| SSL certificates | Manual management | Automatic via Cloudflare |
| DDoS protection | Separate config | Built into Cloudflare |
| WAF / Bot protection | Separate config | Built into Cloudflare |
| Geo-based restrictions | Manual | Built-in GeoIP |

---

## Step 1: Register Cloudflare & Add Your Domain

1. Visit [cloudflare.com](https://cloudflare.com) and create an account
2. Add your domain (you can use an existing domain or sign up for a free one)
3. Point your domain's NS records to the NS servers Cloudflare provides
4. Wait for DNS to propagate (usually minutes to a few hours)

> 💡 **Cost-saving tip**: If you don't have a domain yet, Cloudflare occasionally offers free domain registration promotions. Alternatively, check out [Freenom](https://freenom.com) for free `.tk` / `.ml` domains (though paid domains offer better reliability).

---

## Step 2: Install cloudflared

### Method 1: Using Docker (Recommended)

```bash
# Create config directory
mkdir -p ~/cloudflared/config
cd ~/cloudflared

# Pull the image
docker pull cloudflare/cloudflared:latest
```

### Method 2: Install Binary Directly

```bash
# Ubuntu/Debian
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
chmod +x cloudflared-linux-amd64
sudo mv cloudflared-linux-amd64 /usr/local/bin/cloudflared

# Verify installation
cloudflared --version
```

---

## Step 3: Create Tunnel & Authenticate

### Using Access Tunnel (Simplest, for personal use)

```bash
# Run authentication command
cloudflared tunnel login
```

This opens a browser window to Cloudflare's authentication page. Select your domain account, authorize, and you're done. The certificate is saved to `~/.cloudflared/cert.pem`.

### Using Tunnel CID (For teams / production)

```bash
# Create a tunnel
cloudflared tunnel create my-vps-tunnel

# Output looks like:
# Tunnel credentials saved to /home/user/.cloudflared/<tunnel-id>.json
# Tunnel my-vps-tunnel (xxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx) created
```

Note the **Tunnel ID** for later steps.

---

## Step 4: Configure Routing Rules

### Method 1: YAML Configuration File

Create `~/cloudflared/config/config.yml`:

```yaml
tunnel: <YOUR_TUNNEL_ID>
credentials-file: /home/<your-username>/.cloudflared/<TUNNEL_ID>.json

ingress:
  # Main domain → Blog
  - hostname: blog.yourdomain.com
    service: http://localhost:8080
  
  # Nextcloud
  - hostname: files.yourdomain.com
    service: http://localhost:8081
  
  # Home Assistant
  - hostname: home.yourdomain.com
    service: http://localhost:8123
  
  # Default 404
  - service: http_status:404
```

### Method 2: Docker Compose Integration

Create `~/cloudflared/docker-compose.yml`:

```yaml
version: "3.8"

services:
  cloudflared:
    image: cloudflare/cloudflared:latest
    container_name: cloudflared
    restart: unless-stopped
    command: tunnel --no-autoupdate run
    volumes:
      - ./config:/etc/cloudflared:ro
    environment:
      - TUNNEL_TOKEN=<YOUR_TUNNEL_TOKEN>  # Omit if using login method

  # Example: Blog service
  blog:
    image: ghcr.io/go-hugo/hugo:extended
    container_name: hugo-blog
    restart: unless-stopped
    ports:
      - "8080:80"
    volumes:
      - ./blog:/src

  # Example: Nextcloud
  nextcloud:
    image: nextcloud:apache
    container_name: nextcloud
    restart: unless-stopped
    ports:
      - "8081:80"
    volumes:
      - nextcloud_data:/var/www/html
    environment:
      - MYSQL_DATABASE=nextcloud
      - MYSQL_USER=nextcloud
      - MYSQL_PASSWORD=secure_password_here
      - MYSQL_HOST=db

  db:
    image: mysql:8
    container_name: nextcloud-db
    restart: unless-stopped
    volumes:
      - mysql_data:/var/lib/mysql
    environment:
      - MYSQL_ROOT_PASSWORD=root_secure_password
      - MYSQL_DATABASE=nextcloud
      - MYSQL_USER=nextcloud
      - MYSQL_PASSWORD=secure_password_here

volumes:
  nextcloud_data:
  mysql_data:
```

---

## Step 5: Start the Tunnel

### Using systemd (Recommended for production)

```bash
# Create service file
sudo tee /etc/systemd/system/cloudflared.service > /dev/null << 'EOF'
[Unit]
Description=Cloudflare Tunnel
After=network-online.target
Wants=network-online.target

[Service]
Type=notify
ExecStart=/usr/local/bin/cloudflared tunnel --config /home/<username>/.cloudflared/config.yml run
Restart=on-failure
RestartSec=5
LimitNOFILE=infinity

[Install]
WantedBy=multi-user.target
EOF

# Start and enable on boot
sudo systemctl daemon-reload
sudo systemctl enable --now cloudflared

# Check status
sudo systemctl status cloudflared

# View tunnel logs
cloudflared tunnel route dns <tunnel-name> <subdomain>.yourdomain.com
```

### Using Docker Compose

```bash
cd ~/cloudflared
docker compose up -d
```

---

## Step 6: DNS Routing Configuration

Associate subdomains with your tunnel:

```bash
# Add DNS records (using TUNNEL_ID)
cloudflared tunnel route dns my-vps-tunnel blog.yourdomain.com
cloudflared tunnel route dns my-vps-tunnel files.yourdomain.com
cloudflared tunnel route dns my-vps-tunnel home.yourdomain.com

# Verify DNS records
cloudflared tunnel info my-vps-tunnel
```

After this, visiting `https://blog.yourdomain.com` in your browser will show your service.

---

## Step 7 (Optional): Cloudflare Access Authentication

If you want to restrict access to certain services (e.g., Home Assistant), enable **Cloudflare Access**:

```bash
# In Cloudflare Dashboard:
# 1. Go to Zero Trust → Access → Applications
# 2. Click "Add an application"
# 3. Select "Self-hosted"
# 4. Set Domain: home.yourdomain.com
# 5. Set Auth Domain: yourdomain.com
# 6. Choose verification method (Google/GitHub/Email, etc.)
```

After enabling, visiting `home.yourdomain.com` will redirect to a login page. Only authenticated users can access the service.

### Configure Access Policy via CLI

```bash
# Use Cloudflare API Token for configuration
curl -X POST "https://api.cloudflare.com/client/v4/accounts/<ACCOUNT_ID>/access/services/gateway/service_report" \
  -H "Authorization: Bearer <API_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "enabled": true
  }'
```

---

## Troubleshooting

### 1. Tunnel Connection Fails

```bash
# Check cloudflared logs
sudo journalctl -u cloudflared -f

# Common causes:
# - cert.pem expired (re-run cloudflared tunnel login)
# - Wrong TUNNEL_ID (check config file)
# - Network issues (ensure VPS can reach 200.0.0.0/4)
```

### 2. Service Returns 502 Bad Gateway

- Confirm your local service is running: `curl http://localhost:8080`
- Verify the port numbers in `config.yml` are correct
- Check that the service listens on `0.0.0.0`, not just `127.0.0.1`

### 3. SSL Certificate Issues

Cloudflare Tunnels use Cloudflare's wildcard certificates by default. If your browser shows an unsafe certificate warning:

- Ensure the domain is properly added to Cloudflare
- Set TLS mode to **Full** (Cloudflare Dashboard → DNS → SSL/TLS)
- Clear browser cache and retry

### 4. Bandwidth Limits

Free Cloudflare Tunnels have a **100 GB/month** egress limit. Usually sufficient for personal use. If exceeded:

- Monitor usage: Cloudflare Dashboard → Analytics
- Consider upgrading to Pro plan ($20/month)
- Enable cache rules for high-traffic services

---

## Comparison with Alternatives

| Solution | Cost | Complexity | Security | Best For |
|----------|------|------------|----------|----------|
| **Cloudflare Tunnels** | Free | ⭐ Low | ⭐⭐⭐⭐⭐ | Personal / small teams |
| Ngrok | Free (rate-limited) | ⭐ Low | ⭐⭐⭐ | Temporary testing |
| frp | Requires relay server | ⭐⭐⭐ | ⭐⭐⭐ | Users with existing VPS |
| Caddy reverse proxy | Free (auto-cert) | ⭐⭐ | ⭐⭐⭐⭐ | Has public IP |
| Tailscale | Free (100 devices) | ⭐ Low | ⭐⭐⭐⭐⭐ | Private access only |

> 💡 **Best practice**: Recommended combo for self-hosting—Cloudflare Tunnels (public exposure) + Tailscale (internal management). Route public services through Tunnels, SSH management through Tailscale. Each excels at what it does.

---

## Summary

Cloudflare Tunnels is currently the **best VPS exposure solution for self-hosting enthusiasts**:

- ✅ **Zero ports opened** — significantly improved security
- ✅ **Automatic HTTPS** — no manual certificate management
- ✅ **DDoS protection** — backed by Cloudflare's global network
- ✅ **Free to use** — 100GB/month egress sufficient for personal use
- ✅ **Access integration** — easily add authentication

For setting up blogs, Nextcloud, Home Assistant, and other self-hosted services, Cloudflare Tunnels is the most hassle-free option. Paired with Docker, the entire deployment takes less than 10 minutes.

Get started today and put your services on the internet safely!

---

*More VPS self-hosting guides at [selfvps.net](https://selfvps.net)*
