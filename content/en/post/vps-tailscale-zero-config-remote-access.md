---
title: "Tailscale for VPS Zero-Config Remote Access: Reach Any Service Without Port Forwarding"
date: 2026-08-21
description: "No port forwarding, no public IP, no reverse proxy configuration needed. Tailscale lets you securely access any service on your VPS with a single command—all through an encrypted mesh network."
tags: ["VPS", "Tailscale", "VPN", "Remote Access", "Zero Trust", "WireGuard", "Networking"]
categories: ["Network Tools"]
image: "/images/posts/vps-tailscale-zero-config-remote-access/featured.png"
draft: false
---

## Introduction

Have you ever faced these scenarios?

- You set up Nextcloud on your VPS, but can't access it at home because you have no public IP;
- SSH on port 22 is exposed to the internet, and you're worried about brute-force attacks;
- You want to access phpMyAdmin on your VPS, but need to configure Nginx reverse proxy and a domain every time;
- Multiple VPS instances across different providers need to communicate, but they're scattered across different networks.

The traditional solution involves opening ports, setting up DDNS, and configuring reverse proxies—complicated and insecure. Today I'll introduce a more elegant solution: **Tailscale**.

Tailscale is a zero-config VPN mesh networking tool based on WireGuard. After installation, all devices automatically form an encrypted internal network—no public IP required, no port forwarding, no service exposure. One command, secure access to all your VPS services from anywhere.

## Why Choose Tailscale?

| Solution | Setup Difficulty | Security | Needs Public IP | Cost |
|------|---------|--------|------------|------|
| Port Forwarding + DDNS | ⭐⭐⭐⭐⭐ | ⭐⭐ | Required | Free |
| Nginx Reverse Proxy + Domain | ⭐⭐⭐⭐ | ⭐⭐⭐ | Recommended | Domain cost |
| Cloudflare Tunnel | ⭐⭐⭐ | ⭐⭐⭐⭐ | Not needed | Free |
| **Tailscale** | **⭐** | **⭐⭐⭐⭐⭐** | **Not needed** | **Free (<20 devices)** |

Core advantages of Tailscale:

1. **Zero configuration**: Install client → OAuth login → auto networking, done in 30 seconds;
2. **End-to-end encryption**: All traffic encrypted via WireGuard, doesn't pass through any middle server (except control plane);
3. **NAT traversal**: Automatically handles complex network environments, works behind home routers and mobile networks;
4. **Access control**: Supports ACL rules for precise control over who can access which devices;
5. **Free tier**: Up to 20 devices personal use is completely free.

## Step 1: Install Tailscale

### Install on VPS

```bash
# Ubuntu/Debian
curl -fsSL https://tailscale.com/install.sh | sh

# CentOS/RHEL
curl -fsSL https://tailscale.com/install.sh | sh

# Start the service
sudo tailscale up
```

After installation, Tailscale automatically creates a `tailscale0` network interface and assigns a `100.x.x.x` format Tailnet IP.

### Install on Local Devices

Install the Tailscale client on your phone, laptop, home NAS, etc.:

- **Windows/macOS**: Download from [tailscale.com/download](https://tailscale.com/download)
- **Linux**: `curl -fsSL https://tailscale.com/install.sh | sh && sudo tailscale up`
- **Android/iOS**: Search Tailscale in App Store or Google Play
- **Routers**: Supports OpenWrt, pfSense, UniFi, etc.

### Login and Authenticate

```bash
# Execute on any device
sudo tailscale up

# This outputs a URL, copy it to browser to login
# Authorize using Google/GitHub/Microsoft account via OAuth
```

After login, your VPS and all devices form an encrypted internal network.

## Step 2: Verify Network Setup

```bash
# Check your Tailnet IP
tailscale ip

# View all devices in your tailnet
tailscale status

# Sample output:
# 100.64.0.1
# vps-prod        linux    -          100.64.1.1   idle  5min ago
# macbook-pro     darwin   -          100.64.1.2   active 2min ago
# iphone          android  -          100.64.1.3   active 1min ago
# nas-home        linux    -          100.64.1.4   idle  1h ago
```

Each device gets a unique `100.x.x.x` IP, and devices in the same tailnet can ping each other.

```bash
# Access VPS from local machine
ping 100.64.1.1

# Access home NAS from VPS
ping 100.64.1.4
```

## Step 3: Access Services via Tailnet IP

### SSH Access (Most Common)

```bash
# No need to expose port 22! Connect directly via Tailnet IP
ssh user@100.64.1.1

# Configure SSH client (~/.ssh/config)
Host vps
    HostName 100.64.1.1
    User root
    Port 22
```

**Security advantage**: Your VPS port 22 is completely closed to the public internet. Only devices in the Tailnet can connect. Even if scanned, no open ports will be found.

### Web Panel Access

```bash
# Access directly in browser
# http://100.64.1.1:8080  (CasaOS)
# http://100.64.1.1:3000  (Gitea)
# http://100.64.1.1:9000  (MinIO)
# http://100.64.1.1:3001  (Grafana)
```

**Key point**: These services don't need domain configuration, Nginx reverse proxy, or SSL certificates. Since all Tailnet communication is encrypted, direct IP access works fine.

### Docker Container Access

If your services run in Docker, you don't need to map ports to the host:

```yaml
# docker-compose.yml - no ports mapping needed!
version: '3.8'
services:
  nextcloud:
    image: nextcloud:latest
    # Don't map ports to host
    # ports:
    #   - "8080:80"
    networks:
      - tailscale

networks:
  tailscale:
    external: false
```

Tailscale's IP assignment is global. Whether the service is in a container or on the host, you can access it via `100.x.x.x`.

### Remote Database Access

```bash
# Connect to MySQL on VPS from local
mysql -h 100.64.1.1 -u admin -p

# Connect to Redis on VPS from local
redis-cli -h 100.64.1.1

# Connect to PostgreSQL on VPS from local
psql -h 100.64.1.1 -U postgres
```

## Step 4: Advanced Configuration

### Configure SSH with Tailscale (Recommended)

To make SSH feel more like a direct connection, configure DNS names:

```bash
# Set machine name on VPS
sudo tailscale up --hostname=vps-prod

# Then access via domain name
ssh user@vps-prod.tail xxxx.ts.net
```

Or in local `~/.ssh/config`:

```
Host *.tail.net
    User root
    IdentityFile ~/.ssh/id_ed25519
```

### Enable MagicDNS (Optional)

Tailscale offers free MagicDNS functionality, letting you use machine names instead of IP addresses:

```bash
# Enable MagicDNS in admin console
# https://login.tailscale.com/admin/dns

# Or configure via CLI
sudo tailscale up --accept-dns=true
```

After enabling, all devices in the network can reach each other by short name:

```bash
ping vps-prod      # instead of ping 100.64.1.1
ssh nas-home       # instead of ssh 100.64.1.4
```

### Access Control (ACL)

Tailscale supports fine-grained access control. Create an `acl.json` file:

```json
{
  "groups": {
    "group:admins": ["admin@example.com"],
    "group:devs": ["dev1@example.com", "dev2@example.com"]
  },
  "aclTests": [
    { "user": "admin@example.com", "src": ["*"], "dst": ["*: *"], "accept": true }
  ],
  "ssh": [
    {
      "action": "accept",
      "src": ["group:admins"],
      "dst": ["*"],
      "users": ["root", "autogid:1000"]
    }
  ],
  "hosts": {
    "vps-prod": "100.64.1.1"
  }
}
```

Upload ACL rules through the admin panel.

### Subnet Routes (Let Other Devices Join Tailnet)

If you want all devices on your home LAN to access the VPS through Tailscale, configure subnet routes:

```bash
# On a device that can reach your home LAN (e.g., home router or always-on PC)
sudo tailscale up --advertise-routes=192.168.1.0/24

# Then approve this route in the admin panel
# https://login.tailscale.com/admin/acl
```

After configuration, services on the VPS can access any device on your `192.168.1.x` network.

## Step 5: Combine with Nginx

While Tailscale handles most access needs, if you still need public access (e.g., providing web services to external users), you can combine both:

```nginx
server {
    listen 443 ssl http2;
    server_name your-domain.com;

    # Public access
    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;
}

# Tailscale internal access
server {
    listen 80;
    server_name 100.64.1.1;

    location / {
        proxy_pass http://127.0.0.1:3000;
    }
}
```

Public users access the domain, internal users access via Tailscale IP—no conflict.

## Security Best Practices

### 1. Disable Public SSH on VPS

```bash
# After confirming Tailscale works, close public port 22
sudo ufw deny 22/tcp
# Or with iptables
sudo iptables -I INPUT -p tcp --dport 22 -j DROP
```

### 2. Self-Hosted DERP Server (Optional)

Tailscale uses their DERP relay servers by default. If you prefer not to route through third parties:

```bash
# Self-host DERP server
# https://tailscale.com/kb/1118/custom-derp-servers/
sudo tailscale up --derp-region=<your-derp-region-id>
```

### 3. Device Management

Regularly check connected devices:

```bash
# View all authenticated devices
tailscale status --json | jq '.Peers[] | {key: .DNSName, lastSeen: .LastHandshake}'

# Remotely revoke suspicious devices from admin panel
# https://login.tailscale.com/admin/machines
```

### 4. Avoid Exposing Sensitive Admin Interfaces

While Tailscale encrypts traffic, admin tools like phpMyAdmin and Adminer should still have:
- Application-layer password protection (e.g., .htaccess)
- Or accessed via Tailscale SSH tunnel

```bash
# Local SSH tunnel (backup approach)
ssh -L 8888:localhost:80 root@100.64.1.1
# Then access http://localhost:8888 locally
```

## Real-World Use Cases

### Scenario 1: Manage Multiple VPS Remotely

```bash
# ~/.ssh/config
Host vps-*
    User root
    IdentityFile ~/.ssh/id_ed25519

Host vps-prod
    HostName 100.64.1.1

Host vps-dev
    HostName 100.64.1.2

Host vps-backup
    HostName 100.64.1.3
```

One `ssh vps-prod` connects regardless of where you are or what network you're on.

### Scenario 2: Home NAS + VPS Interconnection

```bash
# Install Tailscale on home NAS and enable subnet routes
sudo tailscale up --advertise-routes=192.168.0.0/24

# VPS can now access all home devices
ping 192.168.0.100   # NAS
ping 192.168.0.50    # Smart TV
ping 192.168.0.10    # Printer
```

### Scenario 3: Remote Development Environment

```bash
# Run dev server on VPS
cd ~/project && python3 -m http.server 8000

# Access directly from local browser
# http://100.64.1.1:8000
# Feels just like accessing a local service
```

### Scenario 4: Replace TeamViewer/AnyDesk

For tech-savvy users, Tailscale is lighter and more secure than remote desktop software:

```bash
# SSH remote desktop
ssh -X user@100.64.1.1 gnome-control-center

# Or use noVNC for graphical interface
# https://github.com/novnc/noVNC
```

## FAQ

### Q: Is the 20-device free limit enough?

For personal use, usually yes: phone + laptop + home NAS + VPS = 4-5 devices. For more:
- Upgrade to Business ($2/user/month, unlimited devices)
- Or self-host the control plane (completely free, no limits)

### Q: Does Tailscale affect network speed?

Tailscale uses WireGuard encryption with minimal performance overhead (typically <5%). For SSH, web panels, and similar use cases, you'll barely notice any latency difference. Only significant data transfers might show slight impact.

### Q: Can I connect when offline?

Tailscale has P2P direct connection mode. If your VPS and local device are behind the same NAT (e.g., same home network), they'll attempt direct connection without any relay servers—the fastest option.

### Q: Can Tailscale replace Cloudflare Tunnel?

It depends on the use case:
- **Internal access** (you yourself) → Tailscale is simpler
- **Public-facing services** (users accessing) → Cloudflare Tunnel is more suitable
- **Both combined** → Best practice: Tailscale for internal management, Cloudflare Tunnel for public services

## Summary

Tailscale redefines "remote access":

1. **Install and network**: No routing configuration, no port opening, no domain purchase;
2. **Encryption is security**: All communications end-to-end encrypted, public scanning is useless;
3. **Simple is powerful**: One `tailscale up` solves all remote access problems.

For self-hosting enthusiasts, Tailscale is almost a must-have tool. It lets you focus on building services instead of tinkering with network configuration.

Install it now—in 30 seconds, your VPS becomes a securely accessible node from anywhere.

---

*Useful links:*
- *Installation guide: https://tailscale.com/kb/1017/install*
- *ACL configuration: https://tailscale.com/kb/1018/acls*
- *MagicDNS: https://tailscale.com/kb/1081/magicdns*
