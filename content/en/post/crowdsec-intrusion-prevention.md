---
title: "CrowdSec Intrusion Prevention: Modern Server Hardening for Your VPS"
description: "Still relying on fail2ban? CrowdSec is the next-gen collaborative IPS with behavior analysis, global threat intelligence, Docker & Nginx integration. Complete installation and configuration guide for your VPS."
date: 2026-06-03T10:00:00+08:00
slug: "crowdsec-intrusion-prevention"
tags: ["CrowdSec", "Security", "Intrusion Detection", "IPS", "Docker", "Nginx", "SSH Hardening", "fail2ban alternative"]
categories: ["Security Hardening"]
image: /images/posts/crowdsec-intrusion-prevention/featured.png
draft: false
---

When was the last time you checked `/var/log/auth.log` on your VPS? How many scanners are probing your SSH port right now? How many of those 404 requests hitting your Nginx are something more sinister?

Traditional fail2ban works, but it fights **alone** — each server is an island with local-only rules, completely unaware that a neighboring server is under active attack. CrowdSec changes this fundamentally: **collaborative threat intelligence + behavioral analysis engine**.

## What is CrowdSec?

CrowdSec is an open-source, collaborative Intrusion Prevention System (IPS). Written in Go, it's lightweight and performant. While it inherits the "ban the IP" philosophy from fail2ban, its architecture is a generational leap forward:

| Feature | fail2ban | CrowdSec |
|---------|----------|----------|
| Threat Intel | Local rules only | Local + global community sharing |
| Detection Engine | Regex on logs | Behavior analysis + scenario orchestration |
| Ban Mechanism | Single-node iptables | Decoupled (detect/decide/execute) |
| Extensibility | Manual rule writing | Rich Hub plugin ecosystem |
| API & Management | None | REST API + Prometheus metrics |
| Updates | Static rules | Dynamic rules + proactive defense |

In simple terms: fail2ban is "wait to be hit, then retaliate." CrowdSec is "learn from the community and prevent attacks before they reach you."

## Core Architecture

CrowdSec uses a microservice-style component architecture:

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│  CrowdSec   │────▶│  Local API   │────▶│  Bouncers    │
│  (Detector)  │     │  (LAPI)      │     │  (Enforcers) │
└─────────────┘     └──────┬───────┘     └──────────────┘
                           │
                    ┌──────▼───────┐
                    │  CrowdSec    │
                    │   Console    │
                    │  (Cloud/Self) │
                    └──────────────┘
```

- **CrowdSec (Detector)**: Parses logs, runs scenarios, identifies attacks
- **Local API (LAPI)**: Manages ban decisions, provides query API for Bouncers
- **Bouncers (Enforcers)**: Execute bans (iptables, Nginx deny, Cloudflare API, etc.)
- **CrowdSec Console**: Central management dashboard (SaaS or self-hosted)

### Key Differences from fail2ban

1. **Detection & enforcement are decoupled**: CrowdSec detects; Bouncers enforce. One detector can drive multiple bouncer types.
2. **Global threat intelligence**: CrowdSec agents (called "signals") anonymously share attack data with the community while receiving the latest malicious IP lists. The more servers use it, the safer everyone becomes.
3. **Proactive defense**: No need to wait for your logs to show an attack pattern — if an IP is flagged anywhere in the community, its first connection to your server is blocked.

## Installation

CrowdSec supports multiple installation methods. Docker Compose is recommended for new deployments.

### Method 1: Docker Compose (Recommended)

Create `docker-compose.yml`:

```yaml
version: "3.8"

services:
  crowdsec:
    image: crowdsecurity/crowdsec:latest
    container_name: crowdsec
    environment:
      - COLLECTIONS=crowdsecurity/linux crowdsecurity/nginx crowdsecurity/http-cve
      - GID=1000
      - UID=1000
    volumes:
      - ./crowdsec/db:/var/lib/crowdsec/data
      - ./crowdsec/config:/etc/crowdsec
      - /var/log:/var/log:ro
      - /var/log/nginx:/var/log/nginx:ro
      - /var/log/auth.log:/var/log/auth.log:ro
    ports:
      - "8080:8080"
    restart: unless-stopped

  crowdsec-bouncer:
    image: crowdsecurity/firewall-bouncer:latest
    container_name: crowdsec-bouncer
    environment:
      - API_URL=http://crowdsec:8080
      - API_KEY=${BOUNCER_API_KEY}
      - DISABLE_IPV6=true
    cap_add:
      - NET_ADMIN
      - NET_RAW
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
    restart: unless-stopped
    depends_on:
      - crowdsec
```

Start the service:

```bash
# Generate API key
docker run --rm crowdsecurity/crowdsec:latest \
  cscli machines add crowdsec-bouncer --auto \
  -f /dev/stdout

# Launch CrowdSec
docker compose up -d
```

### Method 2: APT Installation (Debian/Ubuntu)

```bash
# Add repository
curl -s https://packagecloud.io/install/repositories/crowdsec/crowdsec/script.deb.sh | sudo bash

# Install CrowdSec
sudo apt install crowdsec

# Install firewall bouncer
sudo apt install crowdsec-firewall-bouncer-iptables

# Install Nginx bouncer (optional)
sudo apt install crowdsec-nginx-bouncer
```

After installation, check status with `cscli`:

```bash
# List all scenarios
cscli scenarios list

# View active bans
cscli decisions list

# View alerts
cscli alerts list
```

## Configuration Guide

### Acquisitions (Log Sources)

CrowdSec uses acquisition files to configure log sources. Edit `/etc/crowdsec/acquis.yaml`:

```yaml
# Collect Nginx access logs
filename: /var/log/nginx/access.log
labels:
  type: nginx

# Collect Nginx error logs
filename: /var/log/nginx/error.log
labels:
  type: nginx

# Collect system auth logs
filename: /var/log/auth.log
labels:
  type: syslog

# Collect Docker container logs
container_name:
  - nginx
  - postgres
  - wordpress
labels:
  type: docker
```

### Scenarios (Detection Logic)

Scenarios are CrowdSec's core detection rules. Install commonly used collections:

```bash
# Linux base protection
cscli collections install crowdsecurity/linux

# Nginx protection
cscli collections install crowdsecurity/nginx

# HTTP CVE protection
cscli collections install crowdsecurity/http-cve

# SSH brute force protection
cscli scenarios install crowdsecurity/ssh-bf
```

Each scenario is defined in YAML. For example, `ssh-bf` triggers when an IP has 5 failed SSH authentications within 10 seconds.

### Ban Policies (Profiles)

Configure response policies in `/etc/crowdsec/profiles.yaml`:

```yaml
name: default_ip_remediation
filters:
  - Alert.Remediation == true && Alert.GetScope() == "Ip"
decisions:
  - type: ban
    duration: 4h
on_success: break

---
name: http_remediation
filters:
  - Alert.Remediation == true && Alert.GetScenario() contains "http"
decisions:
  - type: ban
    duration: 24h
on_success: break
```

Customize ban durations per attack type — 4 hours for SSH brute force, 24 hours for HTTP attacks, permanent for malicious crawlers.

## Production Integrations

### Nginx Integration

The Nginx Bouncer blocks malicious requests at the reverse proxy layer, offering finer control than firewall bans:

```bash
deploy Nginx Bouncer with Docker:
docker run -d \
  --name crowdsec-nginx-bouncer \
  -e API_URL=http://crowdsec:8080 \
  -e API_KEY=${API_KEY} \
  -p 8081:8080 \
  crowdsecurity/nginx-bouncer:latest
```

Add to your Nginx config:

```nginx
location / {
    proxy_pass http://backend;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    
    crowdsec_bouncer on;
    crowdsec_bouncer_ban_code 403;
    crowdsec_bouncer_mode "live";
}
```

### Docker Container Integration

The Docker Bouncer provides container-level network isolation:

```bash
docker run -d \
  --name crowdsec-docker-bouncer \
  -e API_URL=http://crowdsec:8080 \
  -e API_KEY=${API_KEY} \
  -v /var/run/docker.sock:/var/run/docker.sock:ro \
  crowdsecurity/docker-bouncer:latest
```

Malicious IPs are automatically added to Docker's network blacklist, protecting all connected containers.

### Cloudflare Integration

If your site uses Cloudflare CDN, configure CrowdSec to ban via the Cloudflare API:

```yaml
# /etc/crowdsec/bouncers/cloudflare.yaml
type: cloudflare
api_token: YOUR_CLOUDFLARE_API_TOKEN
mode: "block"
zones:
  - yourdomain.com
```

### SSH Protection

The most classic and practical use case — protecting SSH from brute force:

```bash
# Verify SSH logs are being collected
cscli metrics

# View SSH attack events
cscli alerts list --type ssh

# Inspect a banned IP
cscli decisions inspect <IP_ADDRESS>
```

Note: even if you use SSH keys exclusively (no password auth), CrowdSec is still valuable — it protects Nginx, WordPress, databases, and every other service on your server.

## Monitoring & Management

### CLI Management (cscli)

```bash
# List all alerts
cscli alerts list

# View ban decisions
cscli decisions list

# Manually ban an IP
cscli decisions add --ip 1.2.3.4 --duration 24h

# Manually unban an IP
cscli decisions delete --ip 1.2.3.4

# View system metrics
cscli metrics

# Update Hub plugins
cscli hub update
cscli collections upgrade crowdsecurity/linux
```

### CrowdSec Console

CrowdSec Console provides a web dashboard to visualize:

- Live attack map
- Alert trends
- Per-server security status
- Global threat intelligence statistics

Sign up at: https://app.crowdsec.net/

You can also self-host the Console on a separate VPS.

### Prometheus Integration

CrowdSec natively exposes Prometheus metrics:

```yaml
# Enable in docker-compose.yml
environment:
  - PROMETHEUS_ENABLED=true
```

Grafana dashboard ID: `15097` (CrowdSec Official Dashboard)

## Performance & Resource Usage

CrowdSec is known for its lightweight footprint:

| Resource | Usage |
|----------|-------|
| CPU | Idle < 1%, Peak < 5% |
| Memory | ~80-150 MB |
| Disk | ~200 MB (including IP database) |
| Log processing latency | < 100ms |

On a 2-core 4GB VPS, CrowdSec runs with virtually no impact on existing services.

## Advanced Techniques

### Custom Scenarios

Create custom scenarios for application-specific attacks:

```yaml
# /etc/crowdsec/scenarios/myapp-bf.yaml
type: leaky
name: myapp/bruteforce
description: "Detect brute force on myapp login"
filter: "evt.Meta.log_type == 'myapp_failed_auth'"
leaky:
  capacity: 5
  leak_speed: "10s"
groupby: evt.Meta.source_ip
labels:
  service: myapp
  confidence: 3
  classification:
    - attack.bruteforce
```

### Allowlisting

Whitelist trusted IPs (monitoring servers, jump hosts):

```yaml
# /etc/crowdsec/parsers/s02-enrich/whitelist.yaml
name: crowdsecurity/whitelists
description: "Whitelist trusted IPs"
whitelist:
  reason: "Trusted IPs"
  ips:
    - 192.168.1.0/24
    - 10.0.0.0/8
  expressions:
    - "'my-company-vpn' in evt.Meta.service"
```

### Multi-Server Deployment

Multiple VPS servers can share a single LAPI:

```
VPS-A (CrowdSec + Bouncer)
    │
    ├──▶ LAPI (Master)
    │
VPS-B (CrowdSec + Bouncer)
    │
    ├──▶ LAPI (Same)
    │
VPS-C (CrowdSec + Bouncer)
    │
    └──▶ LAPI (Same)
```

All servers share ban decisions — when VPS-A detects an attacker, VPS-B and VPS-C automatically block that IP too.

## FAQ

**Q: Will CrowdSec ban legitimate users?**
A: CrowdSec's thresholds are conservatively tuned with very low false-positive rates. If false bans occur, use allowlisting or adjust scenario parameters.

**Q: Can I run CrowdSec alongside fail2ban?**
A: Technically yes, but not recommended. They'll independently manage iptables rules, causing bloat. Migrate and uninstall fail2ban.

**Q: Is registration required?**
A: Not mandatory. But registering gives you access to the cloud console and global threat intelligence. The free tier's community intelligence is sufficient for everyday use.

**Q: How much bandwidth does CrowdSec use?**
A: Signal reporting is extremely lightweight — just a few KB per day. Negligible.

## Summary

CrowdSec represents the evolution of server security: from **isolated passive defense** to **collaborative proactive protection**. It's not complex, but the security improvement is transformative.

If your VPS has no intrusion prevention system — **start today with CrowdSec instead of traditional fail2ban**. If you're already using fail2ban, migrating to CrowdSec takes about 30 minutes.

One final note: security is an ongoing practice, not a one-time setup. Regularly update rules, review alerts, and audit ban records to keep your VPS truly hardened.

---

*Next up: advanced CrowdSec usage — integrating with a WAF (Web Application Firewall) for multi-layer security. Stay tuned.*
