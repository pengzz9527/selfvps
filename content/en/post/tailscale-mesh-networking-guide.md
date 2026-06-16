---
title: "Tailscale Networking Guide: Build Secure Mesh Networks Between VPS Instances"
description: "A comprehensive guide to setting up Tailscale for cross-region VPS mesh networking, secure remote access, service exposure, and node interconnection without public IPs or port forwarding"
date: 2026-06-16T10:00:00+08:00
lastmod: 2026-06-16T10:00:00+08:00
slug: "tailscale-mesh-networking-guide"
tags: ["Tailscale", "mesh networking", "VPS", "zero trust", "remote access", "self-hosted", "network security"]
categories: ["Networking"]
draft: false
aliases: [/en/post/tailscale-mesh-networking-guide/]
image: /images/posts/tailscale-mesh-networking-guide/featured.png
---

## Why Tailscale?

In the self-hosting world, we often face the same problem: **my services run on a VPS, but I need to access them securely from home or anywhere else**. Traditional approaches include:

- **Port Forwarding**: Requires a public IP, exposes attack surface
- **SSH Tunnels**: Cumbersome to configure, not ideal for long-running multi-service setups
- **Cloudflare Tunnel**: Great for web services, limited support for non-HTTP protocols
- **OpenVPN/WireGuard**: Requires maintaining your own infrastructure

[Tailscale](https://tailscale.com/) is a zero-trust networking solution built on [WireGuard](https://www.wireguard.com/) that uses **DERP relay servers** and **NAT traversal** to create an encrypted virtual LAN between any devices running Tailscale. Log in with one account, and all your devices automatically discover each other—no complex firewall rules or port configurations needed.

### Core Advantages

| Feature | Tailscale | Traditional VPN | Cloudflare Tunnel |
|---------|-----------|-----------------|-------------------|
| Setup Complexity | ⭐ Minimal | ⭐⭐⭐ Complex | ⭐⭐ Moderate |
| Latency | Low (direct) | Medium | Medium |
| Protocol Support | Any TCP/UDP | Any TCP/UDP | HTTP/HTTPS only |
| NAT Traversal | Automatic | Manual | N/A |
| Authentication | Tailnet identity | Certificates/passwords | Domain verification |
| Cost | Free (up to 100 devices) | High (self-hosted) | Free |

- 🔒 **End-to-end encryption**: All traffic encrypted via WireGuard, zero-knowledge architecture
- 🌐 **Automatic NAT traversal**: Works without a public IP, supports virtually any network environment
- 🔍 **Service discovery**: Automatically discovers devices and services on your Tailnet
- 👥 **ACL-based control**: Fine-grained access permissions
- 🖥️ **Subnet routers**: Expose your local LAN devices to the entire Tailnet

## Environment Setup

Imagine this scenario:

- **VPS A**: Alibaba Cloud Hong Kong (running Home Assistant)
- **VPS B**: AWS Singapore (running Nextcloud)
- **Local machine**: Home macOS laptop (needs access to both services)

Goal: Connect all three devices into a secure private network without exposing any public ports.

## Step 1: Install Tailscale

### Linux (Debian/Ubuntu)

```bash
# Add and install Tailscale
curl -fsSL https://tailscale.com/install.sh | sh

# Enable and start the service
sudo systemctl enable --now tailscaled

# Log in to your Tailnet
sudo tailscale up
```

After running `tailscale up`, you'll see a URL like `https://login.tailscale.com/a/xxxxx`. Open it in your browser and complete OAuth authentication (supports Google, Microsoft, GitHub, and more).

### Docker Container

If you're already using Docker, you can run Tailscale as a container:

```yaml
version: '3'
services:
  tailscale:
    container_name: tailscale
    image: tailscale/tailscale:latest
    restart: unless-stopped
    volumes:
      - ./tailscale:/var/lib/tailscale
      - /dev/net/tun:/dev/net/tun
    cap_add:
      - NET_ADMIN
      - NET_RAW
    command: "start --advertise-tags=tag:home"
```

Then attach other services to this network namespace:

```yaml
services:
  homeassistant:
    container_name: homeassistant
    image: ghcr.io/home-assistant/home-assistant:stable
    restart: unless-stopped
    network_mode: service:tailscale
    volumes:
      - ./homeassistant:/config
```

### macOS / Windows

Download from [tailscale.com/download](https://tailscale.com/download), log in, and it auto-configures everything.

## Step 2: Verify Connectivity

After installation, check the status:

```bash
# View your Tailnet status
tailscale status

# See your assigned IP address
tailscale ip

# Test connectivity to another device
tailscale ping <another-device-ip-or-hostname>
```

Each device receives a `100.x.x.x` Tailnet IP and a resolvable DNS name (like `yourname.tail1234.ts.net`).

## Step 3: Configure ACLs (Access Control)

Tailscale's ACL system lets you precisely control which devices can communicate with each other. Create an `acl.json` file:

```json
{
  "users": {
    "alice@example.com": "alice",
    "bob@example.com": "bob"
  },
  "groups": {
    "group:admin": ["alice@example.com"],
    "group:server": ["alice@*.ts.net", "bob@*.ts.net"]
  },
  "hosts": {
    "vps-a-homeassistant": "100.1.1.1",
    "vps-b-nextcloud": "100.1.1.2",
    "macbook-pro": "100.1.1.3"
  },
  "acls": [
    {
      "action": "accept",
      "src": ["group:admin"],
      "dst": ["*:"]
    },
    {
      "action": "accept",
      "src": ["group:server"],
      "dst": ["vps-a-homeassistant:8123"]
    },
    {
      "action": "accept",
      "src": ["group:server"],
      "dst": ["vps-b-nextcloud:80"]
    },
    {
      "action": "accept",
      "src": ["macbook-pro"],
      "dst": ["vps-a-homeassistant:8123", "vps-b-nextcloud:80"]
    },
    {
      "action": "accept",
      "src": ["alice@example.com"],
      "dst": ["*:22"]
    },
    {
      "action": "accept",
      "src": ["bob@example.com"],
      "dst": ["*:22"]
    }
  ],
  "ssh": [
    {
      "action": "accept",
      "src": ["*"],
      "dst": ["*"],
      "users": ["root", "autogroup-insert"]
    }
  ]
}
```

Upload the ACL file to the Tailnet admin console: Go to [Admin Console](https://login.tailscale.com/admin/acl) → Click "Policy editor" → Paste the JSON and save.

### Understanding ACL Rules

- **`acls`**: Define which users can access which service ports
- **`ssh`**: Control Tailnet-wide SSH access permissions
- **`src`**: Source (users, groups, hosts)
- **`dst`**: Destination (host:port, `*:*` means all)

For personal use, the simplest ACL allows everything:

```json
{
  "acls": [
    { "action": "accept", "src": ["*"], "dst": ["*:*"] }
  ]
}
```

## Step 4: Exposing Local Services

### Scenario 1: Access Home LAN Devices from Tailnet (Subnet Routers)

Suppose you have a NAS at home (`192.168.1.100`) and want all Tailnet devices to reach it:

```bash
# Install Tailscale on your home router/gateway
sudo tailscale up --advertise-routes=192.168.1.0/24

# Approve subnet routes in the Admin Console
# Go to Admin Console → Nodes → Click your device → Subnets → Enable "Advertise routes"
```

Now, `100.x.x.x` Tailnet devices can reach `192.168.1.x` devices through subnet routing.

### Scenario 2: Access VPS Services from Tailnet

This is straightforward—since your VPS is on the Tailnet, all its ports are reachable. Simply access `http://100.x.x.x:port`.

For example:
- Home Assistant: `http://100.1.1.1:8123`
- Nextcloud: `http://100.1.1.2:80`
- SSH: `ssh user@100.1.1.1`

## Step 5: Advanced Configuration

### 5.1 Set Up an Exit Node

If you want a VPS to act as the exit node for your entire Tailnet:

```bash
# On the VPS, allow it to be an exit node
sudo tailscale up --advertise-exit-node

# On devices that should use the exit node
sudo tailscale up --exit-node=<exit-node-ip>
```

Combined with [AdGuard Home](https://github.com/AdguardTeam/AdGuardHome) or Pi-hole, you can achieve **network-wide DNS filtering**—all Tailnet traffic passes through your home ad filter.

### 5.2 Enable MagicDNS

MagicDNS lets you use hostnames instead of IP addresses:

```bash
# Enable on each device
sudo tailscale up --accept-dns=true

# Configure in Admin Console
# Admin Console → Settings → DNS → Enable MagicDNS
```

Once enabled, you can use `ping vps-a-homeassistant.tailnet-name.ts.net` instead of `ping 100.1.1.1`.

### 5.3 Use Tags for Flexible ACLs

Tags offer simpler access control than raw ACLs. Tag your devices:

```bash
# Tag a VPS with service labels
sudo tailscale up --advertise-tags=tag:service,tag:home,tag:media

# Reference tags in ACLs
{
  "acls": [
    { "action": "accept", "src": ["tag:home"], "dst": ["tag:service:*"] }
  ]
}
```

### 5.4 Multiple Tailnets

If you need isolated networks for different teams or projects, create multiple Tailnets. Tailscale supports [Tailnet Peering](https://tailscale.com/kb/1331/magicsock-peering) to establish secure connections between different Tailnets.

## Step 6: Security Best Practices

### 6.1 Enable Device Approval

1. Go to Admin Console → Settings → Access controls
2. Set key expiry (recommended: 90 days)
3. Enable "Require device approval"

### 6.2 Optimize DERP Regions for Lower Latency

If your devices are geographically distributed, select nearby DERP regions in the Admin Console to reduce relay latency.

### 6.3 Regular ACL Audits

```bash
# Export current ACL configuration
tailscale debug export-acl

# Check device list
tailscale status --json | jq '.Nodes[] | {Name, PrimaryIP, OS, LastSeen}'
```

### 6.4 Restrict SSH Access

Even though Tailscale provides encrypted channels:

- Use key-based authentication, not passwords
- Restrict SSH access sources in ACLs
- Enable Tailscale's built-in SSH (based on Tailnet identity)

```bash
# Enable Tailscale SSH
sudo tailscale up --ssh
```

## Real-World Use Cases

### Use Case 1: Cross-Region VPS Management

You have 5 VPS instances across different providers (Alibaba Cloud, AWS, DigitalOcean, Vultr, Hetzner):

```bash
# Install Tailscale on all VPS instances
# Then SSH to any node from a single jump host
ssh root@vps-aws.ts.net
ssh root@vps-do.ts.net
ssh root@vps-hetzner.ts.net
```

### Use Case 2: Self-Hosted Service Matrix

| Service | Location | Tailscale Address |
|---------|----------|-------------------|
| Home Assistant | Home NAS | `http://100.1.1.5:8123` |
| Nextcloud | AWS | `http://100.2.1.3:80` |
| Plex | Home NAS | `http://100.1.1.5:32400` |
| AdGuard Home | Home Router | `http://100.1.1.1:3000` |
| Gitea | Alibaba Cloud | `http://100.3.1.2:3000` |
| Uptime Kuma | DigitalOcean | `http://100.4.1.2:3000` |

No public IPs, no DNS records, no SSL certificate management—all handled automatically by Tailscale.

### Use Case 3: Secure Remote Office Access

Expose internal company services (Jenkins, GitLab, internal wikis) to remote employees via Tailscale, replacing traditional OpenVPN setups. Setup time drops from hours to minutes.

## Troubleshooting

### Issue 1: Devices Can't Ping Each Other

```bash
# Check Tailscale service status
sudo systemctl status tailscaled

# View detailed logs
sudo journalctl -u tailscaled -f

# Ensure firewall allows UDP 41641
sudo ufw allow 41641/udp
sudo iptables -L -n | grep 41641
```

### Issue 2: NAT Traversal Fails, Falling Back to DERP Relays

DERP relays add latency. If direct connection fails:

```bash
# Check connection type (direct vs derp)
tailscale status --json | jq '.Peers[].LastHandshake'

# Force hole punching
sudo tailscale up --sneak-preview

# Check if UPnP is available
tailscale up --advertise-endpoints
```

### Issue 3: ACL Not Taking Effect

```bash
# View current ACL config
tailscale debug export-acl

# Reload ACL
sudo systemctl reload tailscaled

# Verify device authorization
tailscale cert <hostname>.tailnet-name.ts.net
```

## Summary

Tailscale is one of the most elegant self-hosted networking solutions available today. It enables you to:

1. **Access any device securely** without a public IP
2. **Expose any service** without port forwarding
3. **Build a mesh network** in one command—auto-discovery included
4. **Enterprise-grade security** with end-to-end encryption and granular ACLs
5. **Free for personal use**—up to 100 devices at no cost

For self-hosting enthusiasts, Tailscale should be standard equipment on every VPS. Paired with Docker, Home Assistant, Nextcloud, and other self-hosted tools, you can easily build a cross-region secure service matrix without worrying about network security or configuration complexity.

---

**Next step**: Install Tailscale on your first VPS and experience the power of zero-configuration networking. 🚀
