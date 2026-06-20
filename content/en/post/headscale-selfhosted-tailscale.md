---
title: "Self-Hosted Headscale: Your Own Tailscale Control Plane on VPS"
description: "Deploy Headscale — an open-source Tailscale control plane alternative — on your VPS with Docker. Full control over your zero-trust network, custom DNS, ACLs, node management, and free unlimited nodes."
date: 2026-06-20T10:00:00+08:00
lastmod: 2026-06-20T10:00:00+08:00
slug: "headscale-selfhosted-tailscale"
tags: ["Headscale", "Tailscale", "Zero Trust", "VPS Deployment", "Docker", "Network Security", "Self-Hosted", "WireGuard"]
categories: ["Network Security"]
draft: false
image: "/images/posts/headscale-selfhosted-tailscale/featured.png"
aliases: [/en/post/headscale-selfhosted-tailscale/]
---

## Why Self-Host Headscale?

[Tailscale](https://tailscale.com/) is a revolutionary zero-trust networking tool that connects devices worldwide using WireGuard. But its default control plane is operated by Tailscale Inc., which means:

- Your node list, DNS configuration, and ACL rules are stored on Tailscale's servers
- Corporate compliance requirements may not allow exposing network topology to third parties
- You cannot fully control identity authentication and key management

[Headscale](https://github.com/juanfont/headscale) is an **open-source Tailscale control plane alternative** written in Go, allowing you to take complete ownership of your Zero Trust network architecture on your own VPS.

## Headscale Feature Comparison

| Feature | Tailscale Official | Self-Hosted Headscale |
|---------|-------------------|----------------------|
| Control Plane | Tailscale Inc. hosted | Your own VPS |
| Cost | Free (basic features) | Completely free |
| Data Sovereignty | Data via Tailscale servers | Fully localized |
| ACL Control | Web UI management | YAML configuration |
| DNS Service | Built-in MagicDNS | Built-in DNS resolution |
| Multi-tenancy | Team/Enterprise paid | Open-source free |
| Audit Logs | Enterprise feature | Built-in |

## Prerequisites

### System Requirements

- Ubuntu 22.04/24.04 or Debian 12+
- At least 1 CPU core, 512MB RAM
- Docker and Docker Compose installed

### Install Docker

```bash
curl -fsSL https://get.docker.com | sh
systemctl enable --now docker
```

## Deploying Headscale

### Step 1: Create Project Directory Structure

```bash
mkdir -p /opt/headscale/{config,data}
cd /opt/headscale
```

### Step 2: Generate Pre-Auth Keys

```bash
headscale preauth-key --reusable --expiration 720h
```

> 💡 This key is used to automatically authorize nodes during client registration. The validity period is customizable.

### Step 3: Create Configuration File `/opt/headscale/config/config.yaml`

```yaml
---
# Headscale listen address and port
listen_addr: 0.0.0.0:8080

# Metrics server (optional)
measurement_server_addr: 0.0.0.0:9090

# TLS configuration (strongly recommended for production)
tls_letsencrypt_cache_dir: /var/www/cache
tls_letsencrypt_hostname: ""
tls_cert_path: ""
tls_key_path: ""

# DNS configuration
dns_config:
  override_local_dns: true
  nameservers:
    - "1.1.1.1"
    - "8.8.8.8"

# Domain list
proxied: false

# Database
database:
  type: sqlite
  sqlite:
    db_path: "/var/lib/headscale/db.sqlite"

# Logging
log:
  format: json
  level: info

# Private key
private_key_path: "/var/lib/headscale/private.key"

# Unix socket (for tailcontrol API)
unix_socket: /var/run/headscale/headscale.sock
unix_socket_permission: "0770"
```

### Step 4: Deploy with Docker Compose

Create `/opt/headscale/docker-compose.yml`:

```yaml
version: "3.9"

services:
  headscale:
    image: headscale/headscale:v0.23.0
    container_name: headscale
    restart: unless-stopped
    command: serve
    volumes:
      - ./config:/etc/headscale:ro
      - headscale-data:/var/lib/headscale
    ports:
      - "8080:8080"
      - "9090:9090"
    networks:
      - headscale-net

  headscale-ui:
    image: ghcr.io/gurucomputing/headscale-ui:latest
    container_name: headscale-ui
    restart: unless-stopped
    ports:
      - "9443:443"
    networks:
      - headscale-net

networks:
  headscale-net:
    driver: bridge

volumes:
  headscale-data:
```

Start the services:

```bash
docker compose up -d
```

### Step 5: Initialize Database and Users

```bash
# Run initialization inside the container
docker exec headscale headscale users create default

# Create the first admin user
docker exec headscale headscale users create admin

# Check status
docker exec headscale headscale nodes list
```

## Configuring Tailscale Clients to Connect to Headscale

### Linux Client Configuration

```bash
# Stop the official Tailscale service
sudo systemctl stop tailscaled
sudo systemctl disable tailscaled

# Configure Tailscale to use Headscale
sudo tailscale up --login-url=http://your-vps-ip:8080/admin/users/default/s/device
```

### macOS Client Configuration

```bash
# Install Tailscale for macOS
brew install tailscale

# Configure Headscale backend
sudo tailscale configure-host
sudo tailscale up --login-url=http://your-vps-ip:8080/admin/users/default/s/device
```

### Windows Client Configuration

1. Download from [tailscale.com](https://tailscale.com/download)
2. Open PowerShell as Administrator:
```powershell
Restart-Service tailscaled
tailscale config set-control-url http://your-vps-ip:8080
tailscale up
```

## ACL Access Control Configuration

Headscale uses YAML-formatted ACL files to control inter-node communication. Create `/opt/headscale/config/acls.yaml`:

```yaml
# ACL Configuration Example
# Allow all nodes to communicate with each other
- action: accept
  sources:
    - '*'
  protocols:
    - tcp
    - udp
    - icmp

# Restrict specific subnet access
- action: accept
  sources:
    - 'user:admin'
  protocols:
    - tcp:22

# Block certain traffic
- action: drop
  sources:
    - 'group:guest'
  protocols:
    - tcp:443
```

Reference ACL in the configuration file:

```yaml
# Add to config.yaml
acl:
  auto_appends:
    - user:admin
  distributions:
    - group:admins:
      - admin
```

## Enabling HTTPS (Production Environment)

### Option 1: Let's Encrypt (Recommended)

```yaml
# config.yaml
tls_letsencrypt_hostname: "headscale.yourdomain.com"
tls_letsencrypt_cache_dir: "/var/lib/headscale/cert"
tls_letsencrypt_email: "admin@yourdomain.com"
```

With Nginx reverse proxy:

```nginx
server {
    listen 443 ssl http2;
    server_name headscale.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/headscale.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/headscale.yourdomain.com/privkey.pem;

    location / {
        proxy_pass http://localhost:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Option 2: Self-Signed Certificates

```yaml
tls_cert_path: "/etc/ssl/certs/headscale.crt"
tls_key_path: "/etc/ssl/private/headscale.key"
```

## Common Management Commands

```bash
# List all nodes
docker exec headscale headscale nodes list

# View node details
docker exec headscale headscale nodes list --json

# Rename a node
docker exec headscale headscale nodes rename old-name new-name

# Force node refresh
docker exec headscale headscale nodes expire <node-id>

# List pre-auth keys
docker exec headscale headscale keys list

# Create a new pre-auth key (7-day validity)
docker exec headscale headscale preauth-key create --user default --reusable --expiration 168h

# View logs
docker logs -f headscale

# Health check
curl -s http://localhost:8080/health
```

## Migrating from Tailscale to Headscale

If you're migrating from Tailscale to Headscale:

1. Create the same users and groups on Headscale
2. Reconfigure `--login-url` on each client
3. Re-execute `tailscale up` for authentication
4. Migrate ACL configurations
5. Keep original WireGuard keys if needed

> ⚠️ After migration, existing nodes' Machine Keys will change, but Ephemeral Keys remain the same.

## Monitoring and Alerting

### Prometheus Metrics

Headscale exposes a `/metrics` endpoint for Prometheus integration:

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'headscale'
    static_configs:
      - targets: ['headscale:9090']
```

### Grafana Dashboard

Import a [community dashboard](https://github.com/juankivz/headscale-grafana-dashboard) to visualize:
- Online node count
- API request latency
- Database size growth
- Authentication event frequency

## FAQ

### Q: Can Headscale replace all Tailscale features?

A: Most core features work: P2P direct connection, DERP relay, MagicDNS, ACL control. But Tailscale's Tailnet Lock, SaaS integrations, and enterprise audit logs require custom implementation in Headscale.

### Q: How to configure DERP relay servers?

A: Headscale includes a built-in simple DERP server, or you can configure public DERP:

```yaml
derper:
  active: true
  stun:
    active: true
    listen_addr: "0.0.0.0:3478"
```

### Q: How to backup Headscale data?

```bash
# Backup database
cp /var/lib/headscale/db.sqlite backup-headscale-$(date +%Y%m%d).sqlite

# Backup keys
cp /var/lib/headscale/private.key backup-private-key.key

# Backup configuration
tar czf headscale-config-backup.tar.gz /opt/headscale/config/
```

### Q: Does Headscale support IPv6?

A: Yes, Headscale natively supports IPv6. Simply enable it in the configuration:

```yaml
ip_prefixes:
  - fd7a:115c:a1e0::/48
  - 2a01:4f8:c2c:123f::/64
```

## Summary

Headscale provides an excellent open-source alternative for users who want complete control over their network infrastructure. After deploying Headscale on your VPS, you gain:

- ✅ Complete data sovereignty and network topology visibility
- ✅ Zero-cost unlimited node scaling
- ✅ Flexible ACL and DNS configuration
- ✅ Full audit logging capabilities
- ✅ Seamless compatibility with Tailscale clients

For privacy-conscious users and those with compliance requirements, self-hosting Headscale is one of the most worthwhile VPS projects you can undertake.

---

> 📌 **Next Steps**: Combine with [CrowdSec](/en/post/crowdsec-intrusion-prevention/) to add intrusion detection to Headscale, building a complete zero-trust security system.