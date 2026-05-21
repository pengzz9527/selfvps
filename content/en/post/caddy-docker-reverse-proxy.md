---
title: "Caddy v2 + Docker: The Easiest Reverse Proxy with Automatic HTTPS for Self-Hosted Services"
description: "Step-by-step guide to setting up Caddy v2 as a Docker reverse proxy with automatic Let's Encrypt TLS, wildcard certificates, and practical multi-service deployment for your self-hosted apps on a single VPS."
date: 2026-05-21T10:00:00+08:00
slug: "caddy-docker-reverse-proxy"
tags: ["Caddy", "reverse proxy", "Docker", "HTTPS", "Let's Encrypt", "self-hosting", "VPS", "wildcard certificate"]
categories: ["DevOps", "Web Server"]
draft: false
---

If you run multiple self-hosted services on a single VPS, you need a reverse proxy. Nginx is powerful but its config syntax is unforgiving. Traefik is clever but its dynamic config model has a learning curve. **Caddy v2** sits in the sweet spot: it just works, HTTPS is automatic, and the Caddyfile is readable at a glance.

In this guide, you'll learn how to:

- Set up Caddy v2 with Docker Compose
- Configure automatic TLS via Let's Encrypt (including wildcard certs via DNS challenges)
- Proxy multiple self-hosted services behind a single Caddy instance
- Enable real-time logging, security headers, and basic auth
- Use Caddy APIs for dynamic configuration

## Why Caddy?

| Feature | Caddy v2 | Traefik | Nginx |
|---|---|---|---|
| Auto HTTPS | ✅ Built-in, zero config | ✅ Automatic | ❌ Need certbot |
| Config format | Caddyfile (simple) | TOML/YAML labels | Complex `.conf` files |
| Docker labels | ✅ via `caddy-docker-proxy` | ✅ Native | ❌ Via third-party |
| Wildcard certs | ✅ One-liner DNS challenge | ✅ Supported | ❌ certbot + cron |
| Resource usage | ~15 MB RAM | ~30-50 MB | ~5-10 MB |

Caddy is ideal for small-to-medium setups where you want HTTPS "for free" and don't want to write 50-line Nginx configs.

## Step 1: Basic Caddy + Docker Compose Setup

Create a directory and `docker-compose.yml`:

```yaml
version: "3.8"

services:
  caddy:
    image: caddy:2-alpine
    container_name: caddy
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
      - caddy_config:/config
    restart: unless-stopped
    networks:
      - caddy_net

volumes:
  caddy_data:
  caddy_config:

networks:
  caddy_net:
    name: caddy_net
    external: false
```

Create a minimal `Caddyfile`:

```caddy
# Global options
{
    email your@email.com  # Let's Encrypt account email
    admin off             # Disable admin API in production
}

# Default catch-all: serve a static page
:80 {
    respond "Caddy is running!"
}
```

Start it up:

```bash
docker compose up -d
```

Caddy will automatically provision a HTTP-01 Let's Encrypt certificate for any domain you point at it.

## Step 2: Proxy a Real Service

Let's proxy a simple service — say, a **Vaultwarden** instance running on the same Docker network.

Add the service to `docker-compose.yml`:

```yaml
  vaultwarden:
    image: vaultwarden/server:latest
    container_name: vaultwarden
    volumes:
      - ./vw-data:/data
    restart: unless-stopped
    networks:
      - caddy_net
    expose:
      - "80"
```

Then update your `Caddyfile`:

```caddy
vault.yourdomain.com {
    reverse_proxy vaultwarden:80
}
```

Caddy automatically detects `vault.yourdomain.com`, provisions a Let's Encrypt certificate, and proxies traffic to the `vaultwarden` container. That's it — two lines.

## Step 3: Wildcard Certificates via DNS Challenge

If you have many subdomains — `nextcloud.yourdomain.com`, `n8n.yourdomain.com`, `grafana.yourdomain.com` — you'd normally need one cert per subdomain. With a wildcard cert, you cover `*.yourdomain.com` with a single certificate.

This requires a DNS challenge, meaning Caddy needs API access to your DNS provider. Caddy supports 40+ DNS providers out of the box.

### Example: Cloudflare

```caddy
{
    email your@email.com
}

*.yourdomain.com, yourdomain.com {
    tls {
        dns cloudflare YOUR_CLOUDFLARE_API_TOKEN
    }

    @nextcloud host nextcloud.yourdomain.com
    handle @nextcloud {
        reverse_proxy nextcloud:80
    }

    @n8n host n8n.yourdomain.com
    handle @n8n {
        reverse_proxy n8n:80
    }

    @grafana host grafana.yourdomain.com
    handle @grafana {
        reverse_proxy grafana:3000
    }

    # Default: 404
    respond 404
}
```

Key points:
- Set the `CLOUDFLARE_API_TOKEN` environment variable in the Caddy container
- The wildcard cert covers all `*.yourdomain.com` subdomains
- The `handle` directive routes by hostname — cleaner than separate site blocks

## Step 4: Security Headers & Middleware

Caddy makes it trivially easy to add security headers:

```caddy
vault.yourdomain.com {
    # Security headers
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
        Referrer-Policy "strict-origin-when-cross-origin"
        Permissions-Policy "geolocation=(), microphone=(), camera=()"
    }

    # Rate limiting (10 req/s burst to 20)
    rate_limit {
        zone dynamic {
            key {remote_host}
            events 20
            window 1s
        }
    }

    reverse_proxy vaultwarden:80
}
```

## Step 5: Basic Auth for Staging / Internal Tools

Need to lock down an internal dashboard?

```caddy
internal.yourdomain.com {
    basicauth {
        # Hash generated with: caddy hash-password --plaintext "mypassword"
        admin $2a$14$ZaPPKZPGnVPGnRCeGQGZ5u
    }
    reverse_proxy dashboard:8080
}
```

Generate a password hash:

```bash
docker exec caddy caddy hash-password --plaintext "your-password"
```

## Step 6: Real-Time Logs & Access Logging

```caddy
{
    log {
        output file /var/log/caddy/access.log {
            roll_size 50mb
            roll_keep 5
        }
        format json
    }
}

vault.yourdomain.com {
    log {
        output file /var/log/caddy/vaultwarden.log
    }
    reverse_proxy vaultwarden:80
}
```

Tail logs in real time:

```bash
docker logs -f caddy
# Or for a specific site log:
tail -f /var/log/caddy/vaultwarden.log
```

## Step 7: Production Checklist

Before you go live, run through these:

| Item | Check |
|---|---|
| **Firewall** | Ports 80/443 open; admin ports (e.g., 2019) blocked |
| **Auto-restart** | `restart: unless-stopped` in compose |
| **Resource limits** | Add `deploy.resources.limits` to Caddy container |
| **Backup Caddy data** | Back up `caddy_data` volume (contains certs) |
| **Monitoring** | Health check endpoint or prometheus metrics |
| **Updates** | `docker compose pull caddy && docker compose up -d` |

### Resource Limits Example

```yaml
services:
  caddy:
    image: caddy:2-alpine
    deploy:
      resources:
        limits:
          cpus: "0.5"
          memory: "128M"
```

## Caddy vs Traefik: When to Use Which

**Choose Caddy if:**
- You want HTTPS with minimal config
- You need a Caddyfile you can read at a glance
- You're managing fewer than ~20 services
- You want wildcard certs with a one-liner

**Choose Traefik if:**
- You're running a large microservice architecture
- You need Kubernetes-style dynamic service discovery
- You want full hot-reload without container restart
- You need built-in metrics and middleware chaining

For most self-hosters running 5-15 services on a single VPS, **Caddy is the simpler choice**.

## Next Steps

Once Caddy is up, you can:

1. **Add monitoring**: Expose Prometheus metrics via the Caddy metrics module (`caddy-metrics`)
2. **Enable fail2ban**: Parse Caddy logs to ban malicious IPs
3. **Use Caddy API**: Dynamically add/remove routes without editing the Caddyfile
4. **Set up ACME ZeroSSL**: Use ZeroSSL as an alternative to Let's Encrypt

Caddy v2 is one of the best additions you can make to your self-hosting stack. It eliminates the most painful part of running homelab services — TLS certificate management — and wraps everything in a config format that actually makes sense.

Have you tried Caddy? What's your reverse proxy setup look like? Drop a comment or tag us with your setup!
