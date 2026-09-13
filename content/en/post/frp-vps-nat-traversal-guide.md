---
title: "VPS NAT Traversal with FRP: Build Your Own High-Speed Reverse Proxy"
description: "Access your home services from anywhere without a public IP. FRP (Fast Reverse Proxy) lets you use a VPS as a relay to securely expose internal services—free, fast, and fully under your control."
date: 2026-09-13T10:00:00+08:00
lastmod: 2026-09-13T10:00:00+08:00
slug: "frp-vps-nat-traversal-guide"
tags: ["VPS", "FRP", "NAT Traversal", "Reverse Proxy", "Self-hosting", "Networking", "Privacy"]
categories: ["Networking Tools"]
draft: false
image: /images/posts/frp-vps-nat-traversal-guide/featured.png
aliases: [/en/post/frp-vps-nat-traversal-guide/]
---

## Why Do You Need NAT Traversal?

You've set up Plex on your home NAS, deployed Nextcloud for file sync, and run Home Assistant on a Raspberry Pi—but you can't access any of them when you're away. Your home broadband has no public IP. Port forwarding on your router feels risky. Commercial tunneling services charge monthly fees and route your traffic through third-party servers.

The common thread: **your devices are behind NAT, but you want their services accessible from the internet.**

Today's solution: **FRP** (Fast Reverse Proxy)—free, open-source, high-performance, and entirely under your control.

---

## What Is FRP?

FRP is a high-performance reverse proxy application designed to expose intranet services to the public internet. Developed by fatedier, it has over 75,000 GitHub stars and is one of the most popular open-source tunneling tools available.

The architecture is elegant in its simplicity:

```
Internet ──▶ [FRP Server] ──▶ [FRP Client] ──▶ Intranet Service
              (VPS, Public IP)  (Home/Office)   (NAS/RPi/Local Dev)
```

- **frps (server)**: Deployed on a VPS with a public IP, listens for incoming connections
- **frpc (client)**: Deployed on internal devices, connects to the server and registers services to expose
- **Supported protocols**: TCP, UDP, HTTP, HTTPS, STCP (secret TCP), XTCP (P2P), and more

---

## Prerequisites

- A VPS with a public IP (low-spec is fine, 1-5 Mbps bandwidth suffices)
- Internal devices (NAS, Raspberry Pi, home server, etc.)
- Internal devices must be able to initiate outbound connections (usually satisfied)

---

## Step 1: Deploy the FRP Server

### 1. Download and Install

Log into your VPS and download the latest FRP release:

```bash
# Check latest version
FRP_VERSION=$(curl -s https://api.github.com/repos/fatedier/frp/releases/latest | grep tag_name | cut -d'"' -f4)
echo "Latest version: $FRP_VERSION"

# Download Linux amd64
wget "https://github.com/fatedier/frp/releases/download/${FRP_VERSION}/frp_${FRP_VERSION}_linux_amd64.tar.gz"
tar -xzf "frp_${FRP_VERSION}_linux_amd64.tar.gz"
cd "frp_${FRP_VERSION}_linux_amd64"
```

### 2. Configure frps

Create `frps.toml` (newer versions use TOML format):

```toml
# frps.toml
bindPort = 7000
vhostHTTPPort = 80
vhostHTTPSPort = 443

# Web dashboard (optional, useful for monitoring connections)
webServer.addr = "0.0.0.0"
webServer.port = 7500
webServer.user = "admin"
webServer.password = "your_strong_password_here"

# Auth token — critical security setting
token = "your_secret_token_2026"

# Connection pool
maxPoolCount = 50
heartbeatTimeout = 90

# Logging
log.to = "/var/log/frps.log"
log.level = "info"
log.maxDays = 7
```

### 3. Set Up systemd Service

```bash
sudo cp frps /usr/local/bin/
sudo cp assets/frps/systemd/frps.service /etc/systemd/system/

# Adjust paths in the service file
sudo sed -i 's|/etc/frp/frps.ini|/root/frp/frps.toml|' /etc/systemd/system/frps.service
sudo sed -i 's|/usr/bin/frps|/usr/local/bin/frps|' /etc/systemd/system/frps.service

sudo systemctl daemon-reload
sudo systemctl enable frps
sudo systemctl start frps
sudo systemctl status frps
```

### 4. Configure Firewall

```bash
# Only open necessary ports
sudo ufw allow 7000/tcp   # FRP main connection
sudo ufw allow 7500/tcp   # Web dashboard (optional)
sudo ufw allow 80/tcp     # HTTP vhost (optional)
sudo ufw allow 443/tcp    # HTTPS vhost (optional)
sudo ufw reload
```

---

## Step 2: Deploy the FRP Client

### 1. Install on Your NAS / Raspberry Pi

For a Raspberry Pi (Linux ARM64):

```bash
FRP_VERSION=$(curl -s https://api.github.com/repos/fatedier/frp/releases/latest | grep tag_name | cut -d'"' -f4)
wget "https://github.com/fatedier/frp/releases/download/${FRP_VERSION}/frp_${FRP_VERSION}_linux_arm64.tar.gz"
tar -xzf "frp_${FRP_VERSION}_linux_arm64.tar.gz"
cd "frp_${FRP_VERSION}_linux_arm64"
```

### 2. Configure frpc

```toml
# frpc.toml
serverAddr = "your-vps-public-ip"
serverPort = 7000
token = "your_secret_token_2026"

# Heartbeat
heartbeatInterval = 30
heartbeatTimeout = 90

# DNS override (prevent DNS pollution)
dnsServer = "8.8.8.8"

# Expose SSH (changed port for security)
[[proxies]]
name = "ssh-home"
type = "tcp"
localIP = "127.0.0.1"
localPort = 22
remotePort = 2222

# Expose Nextcloud via HTTPS
[[proxies]]
name = "nextcloud"
type = "https"
localIP = "192.168.1.100"
localPort = 443
customDomains = ["nextcloud.yourdomain.com"]

# Expose Plex media server
[[proxies]]
name = "plex"
type = "https"
localIP = "192.168.1.100"
localPort = 32400
customDomains = ["plex.yourdomain.com"]

# STCP: Hidden service (only authorized clients can connect)
[[proxies]]
name = "homeassistant"
type = "stcp"
localIP = "127.0.0.1"
localPort = 8123
sk = "your_stcp_secret"
allowUsers = ["admin"]

# Expose system stats
[[proxies]]
name = "raspi-stats"
type = "tcp"
localIP = "127.0.0.1"
localPort = 9090
remotePort = 9090
```

### 3. Enable Auto-start

```bash
sudo cp frpc /usr/local/bin/
sudo tee /etc/systemd/system/frpc.service > /dev/null << 'EOF'
[Unit]
Description=FRPC Client
After=network.target

[Service]
Type=simple
User=root
ExecStart=/usr/local/bin/frpc -c /root/frp/frpc.toml
ExecReload=/usr/local/bin/frpc -reload -c /root/frp/frpc.toml
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable frpc
sudo systemctl start frpc
sudo systemctl status frpc
```

---

## Step 3: Domain Configuration and HTTPS

### 1. DNS Records

Add DNS records at your domain registrar:

```
nextcloud.yourdomain.com  →  VPS public IP
plex.yourdomain.com       →  VPS public IP
```

### 2. TLS Termination with Caddy (Recommended)

Install Caddy on your VPS for automatic HTTPS:

```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install caddy
```

Configure `/etc/caddy/Caddyfile`:

```
nextcloud.yourdomain.com {
    reverse_proxy localhost:8080
    encode gzip
}

plex.yourdomain.com {
    reverse_proxy localhost:8081
    encode gzip
}
```

Alternatively, configure TLS directly in frps:

```toml
# frps.toml
vhostHTTPSPort = 443

[[httpsServers]]
addr = "0.0.0.0:443"
certificate = "/path/to/fullchain.pem"
private_key = "/path/to/privkey.pem"
```

Get certificates with Certbot:

```bash
sudo certbot certonly --standalone -d nextcloud.yourdomain.com -d plex.yourdomain.com
```

---

## Advanced Usage

### STCP Secret TCP (Recommended for Sensitive Services)

STCP mode doesn't expose a remote port—only clients with the correct `sk` can connect:

```toml
# Client side (frpc.toml) — the service provider
[[proxies]]
name = "hidden-rdp"
type = "stcp"
localIP = "127.0.0.1"
localPort = 3389
sk = "super_secret_key"
allowUsers = ["viewer"]

# Visitor side (another frpc.toml) — the one connecting
[[visitors]]
name = "hidden-rdp visitor"
type = "stcp"
serverName = "hidden-rdp"
sk = "super_secret_key"
bindAddr = "127.0.0.1"
bindPort = 3390
```

Your RDP service leaves no open port on the public internet. Only devices with the secret key can connect.

### UDP Tunneling (Gaming / VoIP)

```toml
[[proxies]]
name = "minecraft"
type = "udp"
localIP = "192.168.1.200"
localPort = 25565
remotePort = 25565
```

### XTCP P2P Direct Connection (Zero Server Relay)

XTCP enables direct P2P connections between clients, bypassing the server entirely for lower latency:

```toml
# Server side
xtcpPunchholeProbe = true

# Client side (service)
[[proxies]]
name = "p2p-ssh"
type = "xtcp"
localIP = "127.0.0.1"
localPort = 22
secret = "p2p_secret_key"

# Visitor side
[[visitors]]
name = "p2p-ssh visitor"
type = "xtcp"
serverName = "p2p-ssh"
secret = "p2p_secret_key"
bindAddr = "127.0.0.1"
bindPort = 6000
```

P2P mode offers the lowest latency (direct connection), but both sides must be online and NAT types must allow it (most home routers work; carrier-grade NAT does not).

---

## Performance Tuning

### Server-side Optimization

```toml
# frps.toml performance settings
maxPoolCount = 100              # Connection pool size
heartbeatTimeout = 90           # Heartbeat timeout in seconds
startProtocols = ["tcp", "udp", "http", "https", "stcp", "xtcp"]

# Optional: bandwidth limit per connection
# bandwidthLimit = "10MB"
# bandwidthLimitMode = "server"
```

### Client-side Optimization

```toml
# frpc.toml
loginFailExit = false           # Don't exit on login failure (systemd handles restart)
runMode = "normal"              # normal / fake / random
tcpMux = true                   # TCP multiplexing, reduces connection count
tcpMuxKeepaliveInterval = 60
log.level = "warn"              # Lower log level in production
```

### Linux Kernel Parameters

```bash
# /etc/sysctl.d/99-frp.conf
net.core.somaxconn = 65535
net.ipv4.tcp_max_syn_backlog = 8192
net.ipv4.ip_local_port_range = 1024 65535
net.ipv4.tcp_fin_timeout = 30
net.ipv4.tcp_keepalive_time = 600
net.ipv4.tcp_tw_reuse = 1
fs.file-max = 100000

sudo sysctl -p /etc/sysctl.d/99-frp.conf
```

---

## Comparison with Alternatives

| Solution | Cost | Speed | Difficulty | Privacy | Best For |
|----------|------|-------|------------|---------|----------|
| **FRP (self-hosted)** | VPS cost only | ⭐⭐⭐⭐⭐ | Medium | ⭐⭐⭐⭐⭐ | Tech-savvy users, multiple services |
| Tailscale | Free tier available | ⭐⭐⭐⭐ | Low | ⭐⭐⭐⭐ | Personal device networking |
| Cloudflare Tunnel | Free | ⭐⭐⭐ | Low | ⭐⭐⭐ | Websites/APIs |
| ngrok | Free 8KB/s, $8/mo+ | ⭐⭐⭐ | Low | ⭐⭐ | Temporary debugging |
| ZeroTier | Free 50 devices | ⭐⭐⭐⭐ | Medium | ⭐⭐⭐⭐ | Multi-node networking |
| Paid services (Oray, etc.) | ¥30-200/mo | ⭐⭐ | Low | ⭐ | Non-technical users |

---

## Troubleshooting

### Client Keeps Reconnecting

```bash
# Check VPS firewall allows port 7000
sudo ufw status

# Check frps logs
sudo journalctl -u frps -f

# Test connectivity from client
curl -v telnet://your-vps-ip:7000
```

### Domain Returns 404

- Verify DNS resolves to VPS IP: `dig nextcloud.yourdomain.com`
- Confirm `vhostHTTPPort` is set correctly in frps
- Ensure client proxy `customDomains` matches DNS exactly

### HTTPS Certificate Issues

Make sure the domain resolves to your VPS before running Certbot:

```bash
# Resolve first, then request certificate
sudo certbot certonly --nginx -d yourdomain.com
```

### Bandwidth Bottleneck

FRP uses single connections by default. For high bandwidth:

```toml
# Enable TCP Mux to multiplex over fewer connections
tcpMux = true
tcpMuxKeepaliveInterval = 60

# Increase connection pool
maxPoolCount = 100
```

---

## Security Recommendations

1. **Always set a token**—an unauthenticated frps lets anyone tunnel into your network
2. **Never expose SSH directly**—use STCP mode or change the default port + key-based auth
3. **Keep FRP updated**—watch GitHub releases for security patches
4. **Use allowUsers in STCP**—explicitly specify which clients can connect
5. **Enable TLS between frps and frpc**:

```toml
# frps.toml
tls.force = true
tls.certFile = "/path/to/server.pem"
tls.keyFile = "/path/to/server.key"

# frpc.toml
tls.enable = true
tls.trustedCaFile = "/path/to/ca.pem"
```

---

## Summary

FRP is the most flexible and free option for self-hosted NAT traversal. Compared to paid tunneling services, your traffic never touches a third party. Compared to Tailscale, FRP supports more protocol types (HTTP/HTTPS/UDP/P2P) and is better suited for exposing specific ports to the internet.

Key takeaways:
- **frps** runs on your public VPS, **frpc** runs on internal devices
- Use **token authentication** to secure connections, **STCP mode** to hide sensitive services
- **XTCP P2P mode** enables zero-relay direct connections with the lowest latency
- **TCP Mux + kernel tuning** breaks through single-connection bandwidth limits
- Pair with **Caddy/Nginx + Certbot** for fully automated HTTPS

With FRP, your home NAS, Raspberry Pi, and development machines can all securely serve content via custom domains—no paid tunneling services, no exposed raw ports, complete control over your network.
