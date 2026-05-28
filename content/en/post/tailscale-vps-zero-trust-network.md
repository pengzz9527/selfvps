---
title: "Tailscale + VPS: Build a Zero-Trust Network for Self-Hosted Services"
description: "Step-by-step guide to building a zero-trust secure network on your VPS with Tailscale — access self-hosted services without public IPs, port forwarding, or complex firewall rules."
date: 2026-05-28T10:00:00+08:00
slug: "tailscale-vps-zero-trust-network"
image: /images/posts/tailscale-vps-zero-trust-network/featured.png
tags: ["Tailscale", "VPN", "zero-trust", "WireGuard", "networking", "VPS", "self-hosting", "security"]
categories: ["Networking & Security"]
draft: false
---

## Why Tailscale?

As you deploy more and more self-hosted services on your VPS, a thorny problem emerges: **how do you securely access all of these services?**

The traditional approach — opening ports, configuring firewalls, password authentication — creates a massive attack surface. Every new service means worrying about SSL certificates, reverse proxies, and authentication. It's tedious and error-prone.

[Tailscale](https://tailscale.com) offers a radically different approach: a **zero-trust network** built on top of WireGuard. It creates secure, encrypted tunnels between all your devices — no public IP, no port forwarding, no complex firewall rules needed.

### Tailscale's Core Advantages

- 🔒 **Zero-Trust Architecture**: Authenticates based on device and user identity, not IP addresses
- 🚀 **Built on WireGuard**: Kernel-level encryption with minimal performance overhead
- 🌐 **No Public IP Required**: Uses DERP relays and NAT traversal for direct connections
- 📱 **Cross-Platform**: Linux, macOS, Windows, iOS, Android — everything supported
- 🎯 **Tailscale Funnel**: Optionally expose internal services to the public web
- 🏢 **SSO Integration**: Google, GitHub, Microsoft single sign-on
- 💰 **Generous Free Tier**: Up to 100 devices for personal use, completely free

---

## Architecture Overview

A typical Tailscale + VPS network topology looks like this:

```
┌──────────────────────────────────────────────────────────┐
│                     Tailscale Network                      │
│                    (100.x.x.x/10)                         │
│                                                           │
│   ┌──────────┐    ┌──────────┐    ┌──────────┐           │
│   │ VPS Node  │    │ Laptop   │    │ Phone    │           │
│   │(Subnet    │    │(Direct   │    │ (4G/5G)  │           │
│   │ Router)   │    │ Connect) │    │          │           │
│   └────┬─────┘    └──────────┘    └──────────┘           │
│        │                                                   │
│   ┌────┴─────┐                                            │
│   │  Docker  │                                            │
│   │  Network │                                            │
│   │ 10.0.100 │                                            │
│   └──────────┘                                            │
└──────────────────────────────────────────────────────────┘
```

The core idea: your VPS acts as a **Subnet Router**, exposing the Docker container network to all devices on your Tailscale network. You can access services directly by their container IP from your laptop — all traffic fully encrypted.

---

## Step 1: Install Tailscale

### Install on Your VPS

```bash
# One-liner installer (supports all major Linux distros)
curl -fsSL https://tailscale.com/install.sh | sh

# Enable and start the service
sudo systemctl enable --now tailscaled

# Authenticate with your Tailscale account
sudo tailscale up
```

When you run `tailscale up`, the terminal outputs a login URL. Open it in your browser and sign in with Google/GitHub/Microsoft.

### Install on Your Local Machine

- **macOS**: `brew install --cask tailscale` or download from the website
- **Windows**: Download from [tailscale.com/download](https://tailscale.com/download)
- **Linux**: Same one-liner script as above
- **iOS/Android**: Search "Tailscale" in your app store

Once all devices log into the same Tailscale account, they automatically form a secure virtual network.

### Verify the Connection

```bash
# List all devices on your Tailscale network
tailscale status

# Example output:
# 100.x.x.x    your-vps-name        your-user@ linux   -
# 100.y.y.y    your-laptop          your-user@ macOS   -
# 100.z.z.z    your-phone           your-user@ iOS    -

# Test connectivity
ping 100.x.x.x
```

If all devices can ping each other, your Tailscale network is up and running.

---

## Step 2: Configure Subnet Routing

This is the critical step — making your VPS act as a router to expose its Docker network to your Tailscale network.

### Enable IP Forwarding

```bash
# Enable kernel IP forwarding
echo 'net.ipv4.ip_forward = 1' | sudo tee -a /etc/sysctl.conf
echo 'net.ipv6.conf.all.forwarding = 1' | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
```

### Re-authenticate with Subnet Routes

```bash
# Assume your Docker network is 172.17.0.0/16
# First, disconnect current session
sudo tailscale down

# Re-authenticate with subnet routing enabled
sudo tailscale up --advertise-routes=172.17.0.0/16 --accept-routes

# For multiple subnets, separate with commas:
# sudo tailscale up --advertise-routes=172.17.0.0/16,10.0.0.0/24 --accept-routes
```

### Approve Routes in the Tailscale Admin Console

1. Open [https://login.tailscale.com/admin/machines](https://login.tailscale.com/admin/machines)
2. Find your VPS node
3. Click **"..." → "Edit route settings"**
4. Check the subnet you advertised
5. Click **"Save"**

> ⚠️ **Important**: You must manually approve subnet routes in the admin console, or clients won't accept them.

---

## Step 3: Configure Docker Networking

For Tailscale to route to your Docker containers properly, use a fixed Docker subnet.

### Create a Custom Docker Network

```bash
# Create a Docker network with a fixed subnet
docker network create --subnet=10.0.100.0/24 selfhosted-net
```

### Start Services on the Custom Network

```bash
docker run -d --name my-app \
  --network selfhosted-net \
  --ip 10.0.100.10 \
  nginx:alpine
```

Or with Docker Compose:

```yaml
# docker-compose.yml
version: '3.8'

networks:
  selfhosted-net:
    driver: bridge
    ipam:
      config:
        - subnet: 10.0.100.0/24

services:
  n8n:
    image: n8nio/n8n
    networks:
      selfhosted-net:
        ipv4_address: 10.0.100.10
    ports:
      - "5678:5678"

  postgres:
    image: postgres:15
    networks:
      selfhosted-net:
        ipv4_address: 10.0.100.20
    volumes:
      - pgdata:/var/lib/postgresql/data
```

### Update Tailscale Routes

If you previously only advertised `172.17.0.0/16`, add the new subnet:

```bash
sudo tailscale up \
  --advertise-routes=10.0.100.0/24,172.17.0.0/16 \
  --accept-routes
```

Then approve the new routes in the admin console.

---

## Step 4: Securely Access Your Services

Now you can access any container directly from any device on your Tailscale network.

### Direct Access

```bash
# From your laptop
curl http://10.0.100.10:5678  # Directly access N8N
```

### Using MagicDNS (Recommended)

Tailscale's MagicDNS lets you use hostnames instead of IPs.

```bash
# Enable MagicDNS in the admin console
# Then set the Tailscale hostname
sudo tailscale up --advertise-routes=10.0.100.0/24 --accept-routes

# Now you can use hostnames
curl http://your-vps-hostname:5678
```

### Secure SSH via Tailscale

```bash
# On your VPS, restrict SSH to Tailscale interface
# Edit /etc/ssh/sshd_config
# Change ListenAddress 0.0.0.0 to ListenAddress 100.x.x.x

# Or use firewall rules
sudo ufw allow from 100.64.0.0/10 to any port 22
sudo ufw deny 22
```

### In Your Browser

Just type in the address bar:
```
http://10.0.100.10:5678
```

You'll see your service running on the VPS — all traffic encrypted via WireGuard, with zero public exposure.

---

## Step 5: Advanced Configuration

### 5.1 Tailscale Funnel — Expose Services Safely

If someone outside your Tailscale network needs to access a service (e.g., showing a demo to a client), use **Tailscale Funnel**.

```bash
# Install serve (Tailscale's HTTP proxy tool)
sudo tailscale serve --bg --https=443 serve 10.0.100.10:80

# Enable Funnel
sudo tailscale funnel --bg 443 on
```

This exposes your internal service through Tailscale's Funnel infrastructure — connections are still encrypted and authenticated.

### 5.2 ACL Access Control

Tailscale provides granular access control lists:

```json
// Tailscale ACL configuration example
{
  "acls": [
    // Allow all devices to access port 5678 (N8N)
    {"action": "accept", "src": ["*"], "dst": ["your-vps:5678"]},
    // Only allow specific users to access the database
    {"action": "accept", "src": ["user1@", "user2@"], "dst": ["your-vps:5432"]},
    // Deny all other inbound connections
    {"action": "deny", "src": ["*"], "dst": ["*:*"]}
  ]
}
```

Edit ACLs at [https://login.tailscale.com/admin/acls](https://login.tailscale.com/admin/acls).

### 5.3 Using an Exit Node

Route all your traffic through your VPS for an extra layer of privacy:

```bash
# On the VPS
sudo tailscale up --advertise-exit-node
```

```bash
# On your client device
sudo tailscale up --exit-node=your-vps-tailscale-ip
```

This is especially useful when using public Wi-Fi.

### 5.4 Multi-VPS Interconnection

Connect VPS instances across different regions:

```bash
# Each VPS installs Tailscale and joins the same network
# Then they advertise their subnet routes

# VPS Singapore
sudo tailscale up --advertise-routes=10.0.100.0/24 --accept-routes

# VPS US
sudo tailscale up --advertise-routes=10.0.200.0/24 --accept-routes

# Now Singapore container 10.0.100.10 can directly access US container 10.0.200.20
```

---

## Performance Comparison

| Approach | Latency | Throughput | Security | Setup Complexity |
|----------|---------|------------|----------|------------------|
| Direct Public | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐⭐⭐ |
| Traditional VPN (WireGuard) | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ |
| **Tailscale** | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| Cloudflare Tunnel | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| ngrok | ⭐⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ |

Tailscale leads in security and ease of setup, while delivering performance nearly identical to raw WireGuard.

---

## FAQ

### Q: What are the limits of the free Tailscale plan?
A: The free plan supports up to **100 devices** and **3 users** — more than enough for individuals and small teams.

### Q: What if two devices behind strict NAT can't connect directly?
A: Tailscale automatically falls back to DERP relay servers. These are provided by Tailscale and support end-to-end encryption (Tailscale itself cannot decrypt your traffic).

### Q: Can I run my own DERP relay server?
A: Absolutely! You can deploy a private DERP relay server on your own VPS and configure Tailscale to use it. Useful in restricted network environments.

### Q: How is Tailscale different from plain WireGuard?
A: Tailscale is built on WireGuard but adds automatic NAT traversal, device management, ACLs, MagicDNS, and more. Think of it as "WireGuard + a control plane."

### Q: My Docker containers don't have fixed IPs. Can I still use this?
A: Yes — you can use container names or Docker's internal DNS. But subnet routing requires a fixed CIDR range. Always specify a fixed subnet for your Docker networks.

---

## Summary

Tailscale fundamentally changes how we access self-hosted services. By configuring your VPS as a subnet router, you can:

1. ✅ **Zero port exposure** — no ports need to be opened on your VPS
2. ✅ **End-to-end encryption** — all traffic encrypted via WireGuard
3. ✅ **Zero-config access** — seamlessly access VPS services from any device
4. ✅ **Granular control** — precise access rules via ACLs
5. ✅ **Global connectivity** — easily connect VPS instances across the world

Best of all, Tailscale's free tier is generous enough for individuals and small teams. Give it a try today — make your self-hosted services more secure and easier to manage.

### Quick-Start Command Reference

```bash
# Install
curl -fsSL https://tailscale.com/install.sh | sh

# Connect
sudo tailscale up

# Configure subnet routing
sudo tailscale up --advertise-routes=10.0.100.0/24 --accept-routes

# Check status
tailscale status

# Get your IP
tailscale ip -4
```

---

*Found this guide helpful? Share it with other self-hosting enthusiasts!*
