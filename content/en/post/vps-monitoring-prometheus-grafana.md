---
title: "VPS Monitoring Dashboard: Prometheus + Grafana on a Budget VPS"
description: "Build a complete server monitoring system with Prometheus, Grafana, and Node Exporter — track CPU, memory, disk, and network metrics in real time, with email alerts — 100% free and open source"
date: 2026-05-27T10:00:00+08:00
lastmod: 2026-05-27T10:00:00+08:00
slug: "vps-monitoring-prometheus-grafana"
image: /images/posts/vps-monitoring-prometheus-grafana/featured.png
tags: ["Prometheus", "Grafana", "monitoring", "VPS", "DevOps", "alerting", "Docker", "open-source", "self-hosted"]
categories: ["Monitoring & Operations"]
---

## Introduction

You have a low-cost VPS running a few Docker containers and maybe a website. Everything seems fine — until:

- You can't SSH in because the disk is full of logs
- Your site returns 502 errors, and the third-party monitoring service just expired
- A memory leak OOM-kills your VPS, and you have no idea when it happened

**Don't leave monitoring to intuition.** Today we'll set up a complete monitoring system on your VPS using three open-source tools that cost exactly $0:

| Component | Role | Memory Usage |
|-----------|------|-------------|
| **Prometheus** | Time-series DB + metric scraper | ~100MB |
| **Node Exporter** | System metric collector | ~20MB |
| **Grafana** | Dashboard & alerting | ~80MB |

The whole stack uses just **200MB of RAM** — any 1GB VPS can handle it with room to spare.

---

## 1. Architecture Overview

```
┌─────────────────────────────────────┐
│          Your VPS                    │
│  ┌──────────┐  ┌───────────────┐    │
│  │  Node     │  │  Prometheus   │    │
│  │  Exporter │──│  (scrape)     │    │
│  │  :9100    │  │  :9090       │    │
│  └──────────┘  └───────┬───────┘    │
│                        │            │
│                 ┌──────▼───────┐    │
│                 │   Grafana    │    │
│                 │  :3000       │    │
│                 └──────┬───────┘    │
│                        │            │
│            ┌───────────▼──────┐     │
│            │  Browser / Phone │     │
│            └──────────────────┘     │
└─────────────────────────────────────┘
```

- **Node Exporter** collects CPU, memory, disk, and network metrics, exposing them on :9100
- **Prometheus** periodically scrapes Node Exporter's data and stores it in a time-series database
- **Grafana** reads from Prometheus to render dashboards and trigger alerts

---

## 2. One-Click Deploy with Docker Compose

Create a project directory:

```bash
mkdir -p ~/monitoring && cd ~/monitoring
```

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  prometheus:
    image: prom/prometheus:v2.53.0
    container_name: prometheus
    restart: unless-stopped
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    ports:
      - "9090:9090"
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--storage.tsdb.retention.time=30d'

  node_exporter:
    image: prom/node-exporter:v1.8.0
    container_name: node_exporter
    restart: unless-stopped
    volumes:
      - /proc:/host/proc:ro
      - /sys:/host/sys:ro
      - /:/rootfs:ro
    command:
      - '--path.procfs=/host/proc'
      - '--path.sysfs=/host/sys'
      - '--path.rootfs=/rootfs'
      - '--collector.filesystem.mount-points-exclude=^/(sys|proc|dev|host|etc)($$|/)'
    ports:
      - "9100:9100"

  grafana:
    image: grafana/grafana:11.1.0
    container_name: grafana
    restart: unless-stopped
    volumes:
      - grafana_data:/var/lib/grafana
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin   # ← Change this immediately after first login!
      - GF_INSTALL_PLUGINS=grafana-piechart-panel

volumes:
  prometheus_data:
  grafana_data:
```

Create the Prometheus config file `prometheus.yml`:

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

alerting:
  alertmanagers: []

rule_files: []

scrape_configs:
  - job_name: 'node'
    static_configs:
      - targets: ['node_exporter:9100']
```

Start everything:

```bash
docker compose up -d
```

Verify everything is running:

```bash
# Check Prometheus targets
curl -s http://localhost:9090/api/v1/targets | jq .

# Check Node Exporter metrics
curl -s http://localhost:9100/metrics | head -20

# Access Grafana
echo "Open http://YOUR_VPS_IP:3000  (admin / admin)"
```

---

## 3. Configure the Data Source in Grafana

1. Open `http://YOUR_VPS_IP:3000` in your browser
2. First login: username `admin`, password `admin` (you'll be prompted to change it)
3. Go to **Connections → Data Sources → Add data source**
4. Select **Prometheus**
5. Set the URL to `http://prometheus:9090`
6. Click **Save & Test** — you should see a green success message

---

## 4. Import the Classic Dashboard

Grafana dashboard ID **1860** (Node Exporter Full) gives you a beautiful, comprehensive dashboard:

```bash
# Option 1: Import via Grafana CLI
docker exec grafana grafana cli \
  plugins install grafana-piechart-panel

# Option 2: Import via Web UI
# 1. Click "+" → Import on the left sidebar
# 2. Enter ID: 1860
# 3. Select your Prometheus data source
# 4. Click Import
```

After importing, you'll see:

- 📊 **CPU Usage** — real-time load per core
- 💾 **Memory Usage** — RAM, Swap, cache distribution
- 💽 **Disk Space** — partition usage, IO read/write
- 🌐 **Network Traffic** — inbound/outbound graphs
- ⏱ **System Uptime** — and Load Average

---

## 5. Configure Email Alerts (Optional but Recommended)

### 5.1 Set up SMTP in Grafana

Add SMTP configuration to the Grafana environment variables in `docker-compose.yml`:

```yaml
environment:
  - GF_SMTP_ENABLED=true
  - GF_SMTP_HOST=smtp.gmail.com:587
  - GF_SMTP_USER=youraccount@gmail.com
  - GF_SMTP_PASSWORD=your-app-specific-password
  - GF_SMTP_FROM_ADDRESS=youraccount@gmail.com
  - GF_SMTP_FROM_NAME=VPS Alert
```

Restart Grafana:

```bash
docker compose up -d grafana
```

### 5.2 Create Alert Rules

In Grafana:

1. Go to **Alerting → Alert rules → New alert rule**
2. Set condition: `disk_usage_percent > 85`
3. Set evaluation interval: every 5 minutes
4. Add a contact point with your email
5. Save and enable

**Recommended alert rules:**

| Metric | Threshold | Description |
|--------|-----------|-------------|
| Disk usage | > 85% | Running out of disk space |
| Memory usage | > 90% | Potential OOM risk |
| CPU load (15min) | > 2.0 | CPU under high pressure |
| Root partition inodes | < 10% | Cannot create new files |

---

## 6. Security Hardening

### 6.1 Nginx Reverse Proxy with HTTPS

```nginx
# /etc/nginx/sites-available/grafana
server {
    listen 443 ssl;
    server_name grafana.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### 6.2 Restrict Port Exposure

Expose only Grafana (via reverse proxy). Keep Prometheus and Node Exporter on the internal Docker network:

```yaml
# In docker-compose.yml, remove ports: from Prometheus and Node Exporter
# Use expose: instead for internal-only communication
services:
  prometheus:
    expose:
      - "9090"    # internal network only
    # remove ports: section

  node_exporter:
    expose:
      - "9100"    # internal network only
    # remove ports: section
```

### 6.3 Set a Strong Grafana Password

```bash
# Use a strong password via environment variable
environment:
  - GF_SECURITY_ADMIN_PASSWORD=Your_Strong_P@ssw0rd!
  - GF_SECURITY_DISABLE_INIT_ADMIN_CREATION=false
```

---

## 7. Real-World Resource Usage

Tested on a **1GB RAM / 1 vCPU / 20GB disk** budget VPS:

| Component | Memory (RSS) | Disk |
|-----------|-------------|------|
| Prometheus | ~85 MB | ~300MB/day (100+ metrics) |
| Node Exporter | ~18 MB | 0 |
| Grafana | ~65 MB | ~50MB (plugins + DB) |
| **Total** | **~168 MB** | **~350MB/day** |

**Bottom line:** A 1GB VPS is more than enough. A 30-day retention period uses ~10GB of disk — plan for 15GB+ to be safe.

---

## 8. Going Further: More Exporters

This stack is easily extensible. Add whatever exporter matches your needs:

| Exporter | What It Monitors | Port |
|----------|-----------------|------|
| [cAdvisor](https://github.com/google/cadvisor) | Docker container metrics | :8080 |
| [Blackbox Exporter](https://github.com/prometheus/blackbox_exporter) | External site health checks | :9115 |
| [PostgreSQL Exporter](https://github.com/prometheus-community/postgres_exporter) | Database performance | :9187 |
| [Nginx Exporter](https://github.com/nginxinc/nginx-prometheus-exporter) | Nginx metrics | :9113 |

Just add the corresponding job to Prometheus's `scrape_configs` and they'll automatically be included.

---

## Summary

Prometheus + Grafana + Node Exporter is the **"golden trio"** of VPS monitoring — completely free, backed by massive communities, and highly extensible. Compared to paid third-party services like Datadog or New Relic, this self-hosted solution runs smoothly on a **budget 1GB VPS** and keeps your data entirely under your control.

**Key takeaways:**
- ✅ One-click deploy with Docker Compose, up in 5 minutes
- ✅ Classic dashboard ID 1860 — import and go
- ✅ Email alerts configured in minutes
- ✅ Nginx reverse proxy + HTTPS keeps access secure
- ✅ Extensible to containers, databases, and external sites

Remember: **Monitoring is not optional — it's the foundation of reliable operations.** Set this up before your next outage, not after.
