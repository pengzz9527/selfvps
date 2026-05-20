---
title: "Traefik + Docker: The Ultimate Reverse Proxy for Your Self-Hosted Stack"
description: "Complete guide to setting up Traefik as a reverse proxy with Docker — automatic SSL certificates, middleware chaining, rate limiting, and production-hardened configuration for your VPS"
date: 2026-05-20T10:00:00+08:00
slug: "traefik-docker-reverse-proxy"
tags: ["Traefik", "Docker", "reverse proxy", "SSL", "Let's Encrypt", "VPS", "networking"]
categories: ["DevOps", "Self-Hosted Infrastructure"]
draft: false
---

If you self-host multiple services on a single VPS — like Nextcloud, n8n, Vaultwarden, and a personal blog — you need a reverse proxy. **Traefik** is the gold standard for Docker-based deployments: it automatically discovers running containers, provisions Let's Encrypt TLS certificates, and routes traffic with zero manual config reloads.

In this guide, you'll learn how to:

- Deploy Traefik v3 with Docker Compose
- Configure automatic HTTPS via Let's Encrypt (HTTP-01 + TLS-ALPN-01)
- Use Docker labels for zero-config routing
- Chain middlewares for rate limiting, compression, and IP whitelisting
- Secure the dashboard with HTTP Basic Auth
- Production-harden your Traefik instance

## Why Traefik over Nginx or Caddy?

| Feature | Traefik | Nginx Proxy Manager | Caddy |
|---|---|---|---|
| Auto service discovery | ✅ Native Docker API | ❌ Manual | ❌ Manual |
| Auto SSL + renewal | ✅ (native) | ✅ (UI) | ✅ (native) |
| Dynamic config w/out reload | ✅ | ❌ | ✅ |
| Middleware chaining | ✅ Rich ecosystem | ⚠️ Limited | ✅ Basic |
| Kubernetes support | ✅ | ❌ | ❌ |
| Prometheus metrics | ✅ | ❌ | ⚠️ Via plugin |

For a VPS running 5+ Docker services that you add/remove frequently, Traefik's auto-detection is a massive time saver.

## Step 1: Directory Structure

Create a dedicated Traefik directory:

```bash
mkdir -p /opt/traefik
cd /opt/traefik
mkdir -p data config
touch data/acme.json
chmod 600 data/acme.json
```

`acme.json` stores your Let's Encrypt certificates — the `chmod 600` is mandatory or Traefik will refuse to start.

## Step 2: Docker Compose Configuration

Create `/opt/traefik/docker-compose.yml`:

```yaml
services:
  traefik:
    image: traefik:v3.2
    container_name: traefik
    restart: unless-stopped
    security_opt:
      - no-new-privileges:true
    networks:
      - proxy
    ports:
      - "80:80"
      - "443:443"
      # Optional: metrics endpoint
      # - "8080:8080"
    environment:
      - CF_API_EMAIL=${CF_API_EMAIL}
      - CF_DNS_API_TOKEN=${CF_DNS_API_TOKEN}
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - ./data/acme.json:/acme.json
      - ./config:/config
      - ./data/logs:/var/log/traefik
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.traefik.entrypoints=websecure"
      - "traefik.http.routers.traefik.rule=Host(`traefik.yourdomain.com`)"
      - "traefik.http.routers.traefik.tls.certresolver=letsencrypt"
      - "traefik.http.routers.traefik.service=api@internal"
      # Basic auth middleware for dashboard
      - "traefik.http.routers.traefik.middlewares=auth"
      - "traefik.http.middlewares.auth.basicauth.users=${TRAEFIK_ADMIN_USER}:${TRAEFIK_ADMIN_PASSWORD_HASH}"

networks:
  proxy:
    external: true
```

> **Important:** Create the `proxy` network first: `docker network create proxy`

## Step 3: Static Configuration (traefik.yml)

Create `config/traefik.yml`:

```yaml
api:
  dashboard: true
  debug: false

entryPoints:
  web:
    address: ":80"
    http:
      redirections:
        entryPoint:
          to: websecure
          scheme: https
          permanent: true
  websecure:
    address: ":443"

providers:
  docker:
    endpoint: "unix:///var/run/docker.sock"
    exposedByDefault: false
    watch: true
  file:
    directory: /config
    watch: true

certificatesResolvers:
  letsencrypt:
    acme:
      email: youremail@example.com
      storage: /acme.json
      # Use DNS-01 for wildcard certs (Cloudflare example)
      # dnsChallenge:
      #   provider: cloudflare
      #   resolvers:
      #     - "1.1.1.1:53"
      #     - "8.8.8.8:53"
      httpChallenge:
        entryPoint: web
      # Prefer TLS-ALPN-01 when available (only works on port 443)
      # tlsChallenge: {}

log:
  level: INFO
  filePath: /var/log/traefik/traefik.log

accessLog:
  filePath: /var/log/traefik/access.log
  bufferingSize: 100
  format: json
```

## Step 4: Environment File

Create `.env`:

```bash
CF_API_EMAIL=youremail@example.com
CF_DNS_API_TOKEN=your_cloudflare_token
TRAEFIK_ADMIN_USER=admin
# Generate with: $(htpasswd -nb admin securepassword)
TRAEFIK_ADMIN_PASSWORD_HASH=admin:$2y$05$xxx...
```

Generate the password hash:

```bash
apt install apache2-utils -y
htpasswd -nb admin "your-strong-password-here"
```

Copy the output into `.env`.

## Step 5: Dynamic File Configuration (Optional Middlewares)

Create `config/middlewares.yml` for reusable middleware chains:

```yaml
http:
  middlewares:
    # Rate limiting — 100 req/min per IP
    rate-limit:
      rateLimit:
        average: 100
        burst: 50
        period: 1m
        sourceCriterion:
          ipStrategy:
            depth: 1

    # Security headers
    sec-headers:
      headers:
        frameDeny: true
        sslRedirect: true
        browserXssFilter: true
        contentTypeNosniff: true
        forceSTSHeader: true
        stsIncludeSubdomains: true
        stsPreload: true
        stsSeconds: 31536000
        customFrameOptionsValue: "SAMEORIGIN"
        referrerPolicy: "strict-origin-when-cross-origin"
        permissionsPolicy: "camera=(), microphone=(), geolocation=()"

    # IP whitelist (admin-only services)
    whitelist:
      ipWhiteList:
        sourceRange:
          - "10.0.0.0/8"
          - "192.168.0.0/16"
          - "your-home-ip/32"
          # VPN range if you use WireGuard/Tailscale
          - "100.64.0.0/10"

    # Compression
    compress:
      compress:
        excludedContentTypes:
          - "text/event-stream"
          - "image/webp"
          - "image/png"

    # CORS (for API services like n8n)
    cors:
      headers:
        accessControlAllowMethods:
          - "GET"
          - "POST"
          - "PUT"
          - "DELETE"
          - "OPTIONS"
        accessControlAllowOriginList:
          - "*"
        accessControlMaxAge: 100
        accessControlAllowCredentials: true
        addVaryHeader: true
```

## Step 6: Launch Traefik

```bash
docker compose up -d
# Check logs
docker compose logs -f
```

If everything is configured correctly, you should see:

```
time="..." level=info msg="Configuration loaded from provider: docker"
time="..." level=info msg="Starting provider aggregator ..."
```

Visit `https://traefik.yourdomain.com` — you'll see your dashboard:

![Traefik Dashboard](https://doc.traefik.io/traefik/assets/img/dashboard-main.png)

## Step 7: Route a Service with Docker Labels

Here's how to expose any Docker service through Traefik with zero config file changes. Take n8n as an example:

```yaml
services:
  n8n:
    image: n8nio/n8n:latest
    networks:
      - proxy  # <-- same network as Traefik
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.n8n.rule=Host(`n8n.yourdomain.com`)"
      - "traefik.http.routers.n8n.entrypoints=websecure"
      - "traefik.http.routers.n8n.tls.certresolver=letsencrypt"
      - "traefik.http.services.n8n.loadbalancer.server.port=5678"
      # Middleware chain
      - "traefik.http.routers.n8n.middlewares=rate-limit,sec-headers,compress@file"
```

That's it. Run `docker compose up -d` for n8n, and Traefik automatically:

1. Detects the new container via Docker API
2. Generates the routing rule
3. Fetches an SSL certificate from Let's Encrypt
4. Applies the middleware chain
5. Starts serving HTTPS traffic — all without restarting Traefik

## Step 8: Production Hardening Checklist

Before you expose Traefik to the internet:

- [ ] **Use DNS-01 challenge** instead of HTTP-01 — supports wildcard certs (`*.yourdomain.com`) and doesn't need port 80 to be directly accessible
- [ ] **Enable fail2ban** for SSH + Traefik access logs:
  ```bash
  # /etc/fail2ban/jail.local
  [traefik]
  enabled = true
  port = http,https
  filter = traefik
  logpath = /opt/traefik/data/logs/access.log
  maxretry = 20
  findtime = 600
  bantime = 3600
  ```
- [ ] **Restrict Docker socket access** — mount it read-only (`:ro`) and never expose the socket to untrusted containers
- [ ] **Set rate limits** on all routes (the `rate-limit` middleware above)
- [ ] **Enable Prometheus metrics** for monitoring:
  ```yaml
  metrics:
    prometheus:
      addEntryPointsLabels: true
      addServicesLabels: true
      entryPoint: metrics
  ```
- [ ] **Use environment variables** for secrets (`.env` file), never hardcode
- [ ] **Keep Traefik updated**: `docker compose pull && docker compose up -d`
- [ ] **Configure log rotation** to prevent disk overflow:
  ```yaml
  log:
    filePath: /var/log/traefik/traefik.log
    format: json
    level: WARN  # Use INFO for debugging, WARN in production
  ```

## Real-World Example: Full Stack on a $10 VPS

Here's what a complete self-hosted stack looks like behind Traefik:

| Service | Domain | Docker Labels Approach |
|---|---|---|
| Nextcloud | cloud.yourdomain.com | Labels on nextcloud service |
| Vaultwarden | vault.yourdomain.com | Labels on vaultwarden service |
| n8n | n8n.yourdomain.com | Labels on n8n service |
| Grafana | grafana.yourdomain.com | Labels on grafana service |
| Traefik Dashboard | traefik.yourdomain.com | Labels on Traefik itself |

All running on a single 2 vCPU / 2 GB RAM VPS. Each service is isolated in its own container, Traefik handles SSL and routing centrally, and you can add/remove services with a single `docker compose up -d`.

## Troubleshooting

**"404 page not found"** → The container isn't on the `proxy` network. Add `networks: [proxy]` to the service.

**"Certificate is not valid for hostname"** → Your `Host()` rule doesn't match the actual domain, or DNS hasn't propagated yet.

**Traefik won't start due to acme.json permissions** → Run `chmod 600 data/acme.json`. This is the #1 gotcha.

**"dial tcp 127.0.0.1:xxxx: connect: connection refused"** → The service isn't listening on the port you specified in the label. Check the container's internal port.

**Rate limiting too aggressive** → Adjust `average` and `burst` values in the middleware. Start with 200/100 for normal web apps.

## Conclusion

Traefik transforms how you manage self-hosted services. The combination of automatic SSL certificate management, zero-config service discovery via Docker labels, and a rich middleware ecosystem makes it the best reverse proxy for anyone running multiple services on a VPS.

The initial setup takes 15 minutes. The time saved over the life of your server — every time you add, remove, or update a service — compounds rapidly. Whether you're running 3 services or 30, Traefik is the foundation that makes the stack manageable.

**Next steps:** Add Prometheus + Grafana monitoring to your Traefik metrics, set up automatic backup of `acme.json`, and explore plugins via the Traefik Pilot ecosystem for features like IP allowlisting and bot detection.
