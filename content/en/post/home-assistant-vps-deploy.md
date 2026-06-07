---
title: "Home Assistant Self-Hosting Guide: Deploy an Open-Source Smart Home Hub on Your VPS"
description: "Ditch cloud services and vendor lock-in. Deploy Home Assistant on a VPS with Docker to unify all your smart home devices, automate routines, and keep your data private."
date: 2026-06-07T10:00:00+08:00
slug: "home-assistant-vps-deploy"
tags: ["Home Assistant", "Smart Home", "IoT", "Docker", "Self-Hosting", "Automation", "VPS", "Open Source"]
categories: ["Self-Hosting", "Smart Home"]
aliases: [/en/post/home-assistant-vps-deploy/]
draft: false
image: /images/posts/home-assistant-vps-deploy/featured.png
---

## Why Run Home Assistant on a VPS?

The smart home market is filled with cloud-dependent services — Mi Home, HomeKit, Google Home, Alexa — each requiring you to upload device data to their servers. **Privacy leaks, service outages, and vendor lock-in** are the long-standing pain points of self-hosting users.

**Home Assistant (HA)** is an open-source smart home automation platform with a core philosophy: **all data processing happens locally, with zero cloud dependency**. Deploying HA on a VPS gives you:

- **Unified multi-brand device control** — 3000+ integrations for Xiaomi, Apple, Samsung, Tuya, and more — all in one platform
- **Complete privacy control** — all sensor data and automation logic run on your own server
- **Immune to cloud outages** — no cloud service downtime means your automations always work
- **Low-latency responses** — local device automation has millisecond response times
- **Remote access** — paired with a Let's Encrypt certificate + reverse proxy, access your hub from anywhere via your phone

---

## System Architecture

```
┌─────────────────────────────────────────────────────┐
│                 Your Phone / Tablet                   │
│              📱 Home Assistant App                    │
└──────────────┬──────────────────────────────────────┘
               │ HTTPS (wss://your-domain.com)
               ▼
┌─────────────────────────────────────────────────────┐
│            Reverse Proxy (Caddy / Nginx)              │
│         Let's Encrypt TLS + WebSocket Proxy          │
└──────────────┬──────────────────────────────────────┘
               │ localhost:8123
               ▼
┌─────────────────────────────────────────────────────┐
│           VPS / Cloud Server (Debian 12+)             │
│                                                     │
│  ┌───────────────────────────────────────────────┐  │
│  │        Docker Container: Home Assistant       │  │
│  │                                               │  │
│  │  ┌───────────┐  ┌──────────┐  ┌───────────┐  │  │
│  │  │ Core Engine│  │ 3000+    │  │Automation  │  │  │
│  │  │ (Python)   │  │ Integrations│ Engine     │  │  │
│  │  └───────────┘  └──────────┘  └───────────┘  │  │
│  │         │                    │                │  │
│  │  ┌──────▼────┐    ┌─────────▼──────────┐     │  │
│  │  │ SQLite /  │    │  Automation Rules  │     │  │
│  │  │ InfluxDB  │    │  If…Then Triggers  │     │  │
│  │  └───────────┘    └────────────────────┘     │  │
│  └───────────────────────────────────────────────┘  │
│                                                     │
│  ┌───────────────────────────────────────────────┐  │
│  │              Device Integration Layer           │  │
│  │  WiFi: Xiaomi · Apple · Tuya · Philips Hue     │  │
│  │  Zigbee: Zigbee2MQTT / ZHA                    │  │
│  │  MQTT: Massive open-source IoT ecosystem       │  │
│  │  HTTP: Any device with a public API            │  │
│  └───────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

---

## Step 1: Environment Preparation

### Recommended Specs

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| CPU | 1 core | 2 cores |
| RAM | 1 GB | 2 GB+ |
| Storage | 16 GB SSD | 32 GB+ SSD |
| Network | Standard | 10 Mbps+ |
| OS | Debian 12 / Ubuntu 22.04 | Debian 12 |

> **Note:** Home Assistant itself doesn't require heavy resources. If your VPS has ≥4 GB RAM, you can run additional services like a MQTT broker (Mosquitto) or InfluxDB for enhanced functionality.

### Install Docker

```bash
# Update the system
apt update && apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sh

# Add your user to the docker group (avoid sudo each time)
usermod -aG docker $USER
newgrp docker

# Verify the installation
docker --version
docker compose version
```

---

## Step 2: Deploy Home Assistant

### Method 1: Docker Compose (Recommended)

Create a dedicated directory and write `docker-compose.yml`:

```bash
mkdir -p ~/home-assistant
cd ~/home-assistant
```

Create `docker-compose.yml`:

```yaml
version: "3.8"

services:
  homeassistant:
    container_name: homeassistant
    image: ghcr.io/home-assistant/home-assistant:stable
    volumes:
      - ./config:/config
      - /etc/localtime:/etc/localtime:ro
      - /run/dbus:/run/dbus:ro
    restart: unless-stopped
    network_mode: host  # Home Assistant recommends host mode
    # If using bridge mode, you need to map ports:
    # ports:
    #   - "8123:8123"
```

Start the container:

```bash
docker compose up -d
```

### Method 2: Docker run directly

```bash
docker run -d \
  --name homeassistant \
  --restart=unless-stopped \
  -v /root/home-assistant/config:/config \
  -v /etc/localtime:/etc/localtime:ro \
  --network=host \
  ghcr.io/home-assistant/home-assistant:stable
```

### Verify the Deployment

```bash
# Check logs
docker logs -f homeassistant

# Wait a few seconds, then access via browser
# Open http://your-vps-ip:8123
```

On first startup, Home Assistant will walk you through initial configuration, including creating an admin account and selecting your region.

---

## Step 3: HTTPS and Remote Access Setup

Accessing HA directly via IP is inconvenient and insecure. We'll use Caddy as a reverse proxy to enable HTTPS access.

### Install Caddy

```bash
# Docker installation method
mkdir -p ~/caddy-data
cat > ~/caddy/Caddyfile << 'EOF'
your-domain.com {
    reverse_proxy localhost:8123
    
    # Security headers
    header {
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
    }
}
EOF
```

### Proxy Home Assistant with Caddy

```yaml
# ~/caddy/docker-compose.yml
version: "3.8"

services:
  caddy:
    image: caddy:2.8
    container_name: caddy
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile
      - caddy-data:/data
      - caddy-config:/config
    network_mode: host

volumes:
  caddy-data:
  caddy-config:
```

Start Caddy:

```bash
cd ~/caddy && docker compose up -d
```

You can now securely access Home Assistant at `https://your-domain.com`, with Let's Encrypt automatically issuing your certificate.

### Configure Home Assistant Internal Settings

In the HA interface, go to **Settings → System → Network**:

1. Set **Home Assistant URL** to `https://your-domain.com`
2. Enable the **SSL** option
3. Disable **Allow X-Forwarded-For headers** (if proxying through Caddy)

---

## Step 4: Connect Smart Devices

Home Assistant's strength lies in its ability to connect virtually any brand of device. Here are the most common integration methods:

### Method 1: Integrate Existing Brand Devices

HA has 3000+ built-in integrations. Search in **Settings → Devices & Services → Add Integration**:

- **Xiaomi Mi Home** — Connects to Xiaomi ecosystem devices (Mi sensors, ACs, bulbs, etc.)
- **Tuya** — Connects all Tuya platform devices
- **Aqara** — Connects Aqara devices in the Apple HomeKit ecosystem
- **Philips Hue** — Philips smart lighting
- **TP-Link/Kasa** — TP-Link smart plugs and switches
- **Sonoff** — eWeLink ecosystem devices

### Method 2: Zigbee Devices (Zigbee2MQTT Recommended)

If you have Zigbee devices (like Aqara sensors, Xiaomi door/window sensors), this is the best approach:

```yaml
# ~/zigbee2mqtt/docker-compose.yml
version: "3.8"

services:
  zigbee2mqtt:
    container_name: zigbee2mqtt
    image: ghcr.io/koenkk/zigbee2mqtt:latest
    restart: unless-stopped
    volumes:
      - ./data:/app/data
      - /run/udev:/run/udev:ro
    ports:
      - "8099:8099"
    environment:
      - TZ=Asia/Shanghai
    devices:
      - /dev/ttyACM0:/dev/ttyACM0  # Zigbee USB adapter
    network_mode: host
```

You'll need a Zigbee USB adapter (such as CC2652P) plugged into the VPS's USB port or bridged via USB-over-IP.

### Method 3: MQTT Protocol for Open-Source Devices

A large number of open-source hardware devices (ESPHome, etc.) use the MQTT protocol.

```yaml
# ~/mosquitto/docker-compose.yml
version: "3.8"

services:
  mosquitto:
    container_name: mosquitto
    image: eclipse-mosquitto:2
    restart: unless-stopped
    ports:
      - "1883:1883"
      - "9001:9001"
    volumes:
      - ./config/mosquitto.conf:/mosquitto/config/mosquitto.conf
      - ./data:/mosquitto/data
      - ./log:/mosquitto/log
```

In Home Assistant, the MQTT integration only needs the broker address to auto-discover all devices publishing MQTT messages.

---

## Step 5: Create Automation Scenes

Home Assistant's automation engine is the core of the entire system. You can create automation logic using the graphical interface or YAML configuration.

### Scene 1: Away Mode

```yaml
# Automation example in configuration.yaml
automation:
  - alias: "Away Mode"
    trigger:
      - platform: state
        entity_id: person.your_phone
        to: "not_home"
    condition:
      - condition: time
        after: "08:00:00"
        before: "23:00:00"
    action:
      - service: light.turn_off
        target:
          entity_id: group.all_lights
      - service: climate.set_hvac_mode
        target:
          entity_id: climate.ac_living_room
        data:
          hvac_mode: "off"
      - service: notify.telegram
        data:
          message: "🏠 Away mode activated, all lights turned off"
```

### Scene 2: Lights On When People Enter, Off When They Leave

```yaml
  - alias: "Lights On When Occupied"
    trigger:
      - platform: state
        entity_id: sensor.presence_hallway
        to: "occupied"
    condition:
      - condition: state
        entity_id: light.hallway
        state: "off"
      - condition: time
        after: "18:00:00"
    action:
      - service: light.turn_on
        target:
          entity_id: light.hallway
        data:
          brightness: 200
          color_temp: 370

  - alias: "Lights Off When Empty"
    trigger:
      - platform: state
        entity_id: sensor.presence_hallway
        to: "not_home"
        for: "00:02:00"
    action:
      - service: light.turn_off
        target:
          entity_id: light.hallway
```

### Scene 3: Temperature-Adaptive AC

```yaml
  - alias: "Temperature Adaptive AC"
    trigger:
      - platform: time_pattern
        minutes: "/5"
    condition:
      - condition: state
        entity_id: input_boolean.summer_mode
        state: "on"
    action:
      - service: climate.set_temperature
        target:
          entity_id: climate.ac_bedroom
        data:
          temperature: >
            {{ states('sensor.bedroom_temp') | float + 0.5 }}
```

---

## Step 6: Enhanced Features

### Install InfluxDB + Grafana for Visualization

```yaml
version: "3.8"

services:
  homeassistant:
    image: ghcr.io/home-assistant/home-assistant:stable
    volumes:
      - ./ha-config:/config
    network_mode: host
    restart: unless-stopped

  influxdb:
    image: influxdb:2
    container_name: influxdb
    restart: unless-stopped
    ports:
      - "8086:8086"
    volumes:
      - ./influxdb-data:/var/lib/influxdb2
    environment:
      - DOCKER_INFLUXDB_INIT_MODE=setup
      - DOCKER_INFLUXDB_INIT_USERNAME=admin
      - DOCKER_INFLUXDB_INIT_PASSWORD=your_secure_password
      - DOCKER_INFLUXDB_INIT_ORG=homeassistant
      - DOCKER_INFLUXDB_INIT_BUCKET=ha

  grafana:
    image: grafana/grafana:latest
    container_name: grafana
    restart: unless-stopped
    ports:
      - "3000:3000"
    volumes:
      - ./grafana-data:/var/lib/grafana
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin_password
```

Install the **InfluxDB** integration in Home Assistant, configure it to export historical data, and connect Grafana to InfluxDB to create visualization dashboards.

### Voice Assistant Integration

```yaml
# After installing the voice-assistant integration, add to configuration.yaml:
conversation:
  language: "en"

tts:
  - platform: edge_tts
    service_name: edge_tts_say
    language: en-US
    voice: en-US-JennyNeural
```

### Backup Strategy

```bash
#!/bin/bash
# ~/home-assistant/backup.sh

DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/backup/home-assistant"
CONFIG_DIR="/root/home-assistant/config"

# Create backup
mkdir -p "$BACKUP_DIR"
tar czf "$BACKUP_DIR/ha-backup-$DATE.tar.gz" \
  -C /root/home-assistant config/

# Delete backups older than 30 days
find "$BACKUP_DIR" -name "ha-backup-*.tar.gz" -mtime +30 -delete

# Optional: Upload to cloud storage
# rclone copy "$BACKUP_DIR/ha-backup-$DATE.tar.gz" remote:ha-backups/
```

Add to crontab:

```bash
crontab -e
# Daily backup at 3 AM
0 3 * * * /root/home-assistant/backup.sh
```

---

## Step 7: Security Hardening

### 1. Enable Two-Factor Authentication (2FA)

Enable the **Google Authenticator** integration in HA and configure two-factor authentication for all user accounts.

### 2. Network Isolation

```yaml
# Use Docker network isolation for HA container
version: "3.8"

services:
  homeassistant:
    networks:
      - ha-net
    # Do not expose any ports to the host

  reverse-proxy:
    ports:
      - "443:443"
    networks:
      - ha-net
      - proxy-net

networks:
  ha-net:
    driver: bridge
  proxy-net:
    driver: bridge
```

### 3. Keep Updated

```bash
# Check for updates daily
docker compose pull && docker compose up -d

# Or use Watchtower for auto-updates
docker run -d \
  --name watchtower \
  --volume /var/run/docker.sock:/var/run/docker.sock \
  containrrr/watchtower \
  --cleanup --interval 21600 --label-enable
```

### 4. Restrict API Access

In `configuration.yaml`:

```yaml
http:
  ssl_certificate: /config/ssl/fullchain.pem
  ssl_key: /config/ssl/privkey.pem
  trusted_proxies:
    - 172.18.0.0/16  # Docker internal network
    - ::1              # localhost IPv6
```

---

## Troubleshooting FAQ

### Issue 1: WebSockets Connection Dropping

Home Assistant uses WebSockets for real-time updates. If connections drop frequently:

```bash
# Check if firewall blocks WebSocket traffic
# Ensure reverse proxy config includes WebSocket support
# Caddy supports WebSocket automatically — no extra config needed

# In Caddyfile:
# reverse_proxy localhost:8123
# No additional websocket configuration required
```

### Issue 2: Device Scan Can't Find Devices

- Ensure all devices are on the same local network
- If using bridge network mode, HA cannot discover LAN devices
- Use `network_mode: host` or configure mDNS/Bonjour

### Issue 3: High Automation Latency

- Check if InfluxDB or SQLite is a disk I/O bottleneck
- Reduce unnecessary time-interval triggers
- For frequently changing sensors, consider event-driven instead of polling

### Issue 4: High Memory Usage

```bash
# Check HA container resource usage
docker stats homeassistant

# Limit HA memory usage
# Add to docker-compose.yml:
mem_limit: 1g
mem_reservation: 512m
```

---

## Summary

| Step | Action | Estimated Time |
|------|--------|----------------|
| 1 | Environment Preparation | 15 min |
| 2 | Deploy Home Assistant | 10 min |
| 3 | Configure HTTPS & Domain | 15 min |
| 4 | Connect Devices | 30-60 min |
| 5 | Create Automations | 30-60 min |
| 6 | Enhanced Features | As needed |
| 7 | Security Hardening | 20 min |

**Total: ~2-3 hours**, after which you'll have a fully self-managed smart home hub.

The core value of Home Assistant is this: **Your home, your rules**. No vendor lock-in, no data leaks, no service outages. A cheap VPS ($3-5/month) makes all of this possible.

---

*This guide is based on Home Assistant 2026.6. For version differences, refer to the [Home Assistant Official Documentation](https://www.home-assistant.io/docs/).*
