---
title: "Cloudflare Tunnel + VPS: Free Public Internet Access for Internal Services"
description: "No public IP needed — securely expose your self-hosted services to the internet via Cloudflare Tunnel, with a complete Docker Compose deployment guide"
date: 2026-06-25T08:00:00+08:00
slug: "cloudflare-tunnel-vps-guide"
tags: ["Cloudflare", "Tunnel", "Reverse Proxy", "No Public IP", "Self-Hosting", "Docker", "Network Security"]
categories: ["Networking"]
aliases: [/en/post/cloudflare-tunnel-vps-guide/]
image: /images/posts/cloudflare-tunnel-vps-guide/featured.png
---

## Why Cloudflare Tunnel?

Most home users and low-tier VPS users face a common problem: **no public IP**. Even if you have a VPS, if your provider assigns an internal IP (like CGNAT), you cannot access your services directly from the internet.

Traditional solutions involve port forwarding, which requires:
- Router port forwarding support
- A public IPv4/IPv6 address
- Exposing ports, which introduces security risks

**Cloudflare Tunnel** (formerly Argo Tunnel) provides a completely different approach — it runs a lightweight proxy process on your server that proactively establishes encrypted connections outward, allowing Cloudflare's edge network to securely forward traffic to your internal services. **No ports need to be opened, no public IP required.**

## How It Works

```
Internet User → Cloudflare CDN Edge Node → cloudflared Tunnel → Your VPS Local Service
     (DNS)           (HTTPS/TLS)               (Outbound TCP)       (localhost:port)
```

1. **cloudflared** runs on your VPS and proactively establishes outbound TCP connections to Cloudflare's edge nodes
2. When users visit your domain, DNS resolves to Cloudflare's edge IP
3. Cloudflare forwards requests through the established tunnel to your VPS
4. All transmissions are TLS-encrypted

**Key advantage**: Outbound connections don't require firewall rules because the connection is initiated from the inside out.

## Prerequisites

### What You Need

- A VPS (any spec works, even 512MB RAM)
- A domain registered with Cloudflare
- Docker and Docker Compose (containerized deployment recommended for cloudflared)

### Creating a Cloudflare Tunnel

1. Log in to the [Cloudflare Dashboard](https://dash.cloudflare.com)
2. Select your domain → **Zero Trust** → **Networks** → **Tunnels**
3. Click **Create a tunnel**, select **Cloudflared** as the connector
4. Copy the generated installation token

## Deploying cloudflared on Your VPS

### Method 1: Docker Compose (Recommended)

Create a `docker-compose.yml` file:

```yaml
version: '3.8'

services:
  cloudflared:
    image: cloudflare/cloudflared:latest
    container_name: cloudflared
    restart: unless-stopped
    command: tunnel --no-autoupdate run --token ${TUNNEL_TOKEN}
    environment:
      - TUNNEL_TOKEN=your_token_here
    networks:
      - web

networks:
  web:
    driver: bridge
```

Start the service:

```bash
export TUNNEL_TOKEN="eyJhIjoiYWNjb3VudC1pZCIsInQiOiJ0dW5uZWwtdG9rZW4iLCJzIjoic2VjcmV0In0="
docker compose up -d
```

### Method 2: Direct Installation

```bash
# Debian/Ubuntu
curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg \
  | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null

echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] \
  https://pkg.cloudflare.com/cloudflared $(lsb_release -cs) main" \
  | sudo tee /etc/apt/sources.list.d/cloudflared.list

sudo apt update && sudo apt install -y cloudflared

# Configure the tunnel
sudo cloudflared tunnel setup my-tunnel \
  --token "your_token_here"

sudo systemctl enable cloudflared-my-tunnel
sudo systemctl start cloudflared-my-tunnel
```

## Configuring Route Rules

### Via CLI (Docker method)

First, add route rules for the tunnel in the Cloudflare Dashboard. Or use CLI:

```bash
# List all tunnels
cloudflared tunnel list

# View tunnel details
cloudflared tunnel info my-tunnel

# Add route rule: map HTTP service to tunnel
cloudflared tunnel route dns my-tunnel demo.yourdomain.com
```

### Via Dashboard

1. Return to Zero Trust → Tunnels → select your tunnel
2. Go to the **Public Hostnames** tab
3. Click **Add a public hostname**
4. Fill in the configuration:
   - **Subdomain**: `demo`
   - **Domain**: `yourdomain.com`
   - **Service Type**: `HTTP`
   - **URL**: `localhost:8080` (or your service port)
5. Click **Save tunnel**

### Multiple Services Example

You can configure multiple routes for one tunnel, mapping different subdomains to different local services:

| Subdomain | Service Type | Target Address | Corresponding Service |
|-----------|--------------|----------------|----------------------|
| `home.yourdomain.com` | HTTP | `localhost:8080` | Home Assistant |
| `docs.yourdomain.com` | HTTP | `localhost:3000` | Wiki.js |
| `files.yourdomain.com` | HTTP | `localhost:80` | Nextcloud |
| `monitor.yourdomain.com` | HTTP | `localhost:3001` | Uptime Kuma |
| `chat.yourdomain.com` | HTTPS | `localhost:8443` | ChatGPT-Next-Web |

## Complete Self-Hosted Service Example

Here is a complete Docker Compose configuration that runs cloudflared alongside your own services:

```yaml
version: '3.8'

services:
  # Your self-hosted service
  nextcloud:
    image: nextcloud:apache
    container_name: nextcloud
    restart: unless-stopped
    volumes:
      - nextcloud_data:/var/www/html
      - nextcloud_config:/var/www/html/config
    environment:
      - MYSQL_HOST=db
      - MYSQL_PASSWORD=nextcloud
      - MYSQL_DATABASE=nextcloud
      - MYSQL_USER=nextcloud
    networks:
      - apps

  # Database
  db:
    image: mariadb:10.11
    container_name: nextcloud-db
    restart: unless-stopped
    command: --transaction-isolation=READ-COMMITTED --binlog-format=ROW
    volumes:
      - db_data:/var/lib/mysql
    environment:
      - MYSQL_ROOT_PASSWORD=rootpass
      - MYSQL_PASSWORD=nextcloud
      - MYSQL_DATABASE=nextcloud
      - MYSQL_USER=nextcloud
    networks:
      - apps

  # cloudflared tunnel
  cloudflared:
    image: cloudflare/cloudflared:latest
    container_name: cloudflared
    restart: unless-stopped
    command: tunnel --no-autoupdate run --token ${TUNNEL_TOKEN}
    environment:
      - TUNNEL_TOKEN=${TUNNEL_TOKEN}
    networks:
      - apps
    depends_on:
      - nextcloud

volumes:
  nextcloud_data:
  nextcloud_config:
  db_data:

networks:
  apps:
    driver: bridge
```

Environment variable configuration:

```bash
# .env file
TUNNEL_TOKEN=eyJhIjoiYWNjb3VudC1pZCIsInQiOiJ0dW5uZWwtdG9rZW4iLCJzIjoic2VjcmV0In0=
```

Route configuration (in Dashboard):
- `nextcloud.yourdomain.com` → `http://nextcloud:80`

## Security Enhancements

### Enable Cloudflare Access (Zero Trust Access Control)

Cloudflare Tunnel can integrate with Cloudflare Access to add an extra authentication layer to your services:

1. Create an **Access Policy** in the Zero Trust Dashboard
2. Set rules such as:
   - Allow access only from specific email domains
   - Require OAuth 2.0 authentication (Google, GitHub, etc.)
   - Device compliance checks
3. Apply the policy to your tunnel subdomains

### Additional Security Recommendations

- **Use HTTPS**: Cloudflare provides free Let's Encrypt SSL certificates by default
- **Enable WAF Rules**: Configure Web Application Firewall in the Cloudflare Dashboard
- **Restrict Source IPs**: If your service has IP whitelisting, pair it with Cloudflare Proxy IPs
- **Rotate Tokens Regularly**: Rebuild the tunnel quickly if a Tunnel Token is compromised

## Troubleshooting

### Service Not Accessible

```bash
# Check cloudflared container status
docker logs cloudflared

# View tunnel connection status
cloudflared tunnel info my-tunnel

# Test if local service is running properly
curl http://localhost:8080
```

### DNS Resolution Issues

```bash
# Confirm DNS record has been created
dig demo.yourdomain.com CNAME
# Should return something like: demo.yourdomain.com CNAME xxxxxxxx.cfargotunnel.com

# Check DNS settings in Cloudflare Dashboard
```

### Performance Optimization

- Enable Cloudflare **Auto Minify** (HTML/CSS/JS)
- Turn on **Brotli compression**
- Configure **Cache Rules** to set longer cache times for static assets
- For high-traffic services, consider upgrading Cloudflare plans for better edge performance

## Cloudflare Tunnel vs Nginx Proxy Manager

| Feature | Cloudflare Tunnel | Nginx Proxy Manager |
|---------|-------------------|---------------------|
| Requires Public IP | ❌ No | ✅ Yes |
| Requires Port Open | ❌ No | ✅ Yes |
| SSL Certificate | ✅ Automatic | Manual/Automatic |
| CDN Acceleration | ✅ Built-in | ❌ None |
| DDoS Protection | ✅ Built-in | ❌ None |
| Access Control | ✅ Access Integration | ✅ Basic Auth |
| Global Access | ✅ 200+ Edges | ❌ Single Point |
| Free Tier | ✅ Unlimited Bandwidth* | ✅ Completely Free |

*\*Cloudflare free plan has no bandwidth limit, but advanced features require payment*

## Summary

Cloudflare Tunnel is an ideal choice for self-hosting enthusiasts and small teams:

1. **Zero cost**: No public IP needed, no additional hardware
2. **High security**: Outbound connections, ports not exposed, TLS encrypted
3. **Easy maintenance**: One-click Docker deployment, visual Dashboard configuration
4. **Scalable**: Supports any number of services and subdomains
5. **Global acceleration**: Leverages Cloudflare's 200+ edge nodes

For users without a public IP, Cloudflare Tunnel is practically the only option. For those with a public IP, it's also an excellent security supplement — placing your services under Cloudflare's protection umbrella is far safer than exposing them directly to the internet.

Get started! In just minutes, you can safely expose any self-hosted service to the internet.
