---
title: "Jellyfin VPS Deployment Guide: Build Your Personal Netflix with a Self-Hosted Media Server"
description: "Complete tutorial for deploying Jellyfin media server on VPS using Docker — with hardware transcoding, multi-device streaming, remote access, and automated management for your private home cinema"
date: 2026-06-09T10:00:00+08:00
lastmod: 2026-06-09T10:00:00+08:00
slug: "jellyfin-vps-media-server"
tags: ["Jellyfin", "Media Server", "Docker", "VPS Deployment", "Self-Hosting", "Streaming", "Hardware Transcoding"]
categories: ["Deployment Guide"]
draft: false
image: /images/posts/jellyfin-vps-media-server/featured.png
aliases: [/en/post/jellyfin-vps-media-server/]
---

## Why Jellyfin?

Do you have hundreds of movies and TV shows sitting unused because you don't have a proper way to organize and watch them? NAS devices are expensive, and streaming subscriptions mean ongoing monthly costs.

[Jellyfin](https://jellyfin.org/) is a **completely free, open-source** media server that transforms your VPS into a personal media hub. It supports automatic media library management, multi-device streaming, hardware transcoding, and remote access — the best free alternative to Plex and Emby.

### Jellyfin Feature Comparison

| Feature | Jellyfin | Plex | Emby |
|---------|----------|------|------|
| Price | **Completely Free** | Premium features paid | Some features paid |
| Open Source | ✅ Fully Open Source | ❌ Closed Source | ⚠️ Partially Open |
| Hardware Transcoding | Free | Paid (Plex Pass) | Paid |
| Self-Hosted | ✅ | ✅ | ✅ |
| Platform Support | All Platforms | All Platforms | All Platforms |

- 🎬 **Automated Media Management** — Auto-download posters, synopsis, and metadata
- 📱 **Multi-Device Support** — Access from phones, tablets, TVs, and browsers
- 🔄 **Real-Time Transcoding** — Auto-adjust quality based on network bandwidth
- 🔒 **Fully Private** — Complete control over your data

---

## Environment Preparation

### Recommended VPS Configuration

| Use Case | Minimum | Recommended |
|------------|---------|-------------|
| Light Use (1080p Software Decode) | 1 Core 2GB | 2 Core 4GB |
| Hardware Transcoding (Recommended) | 1 Core 2GB + GPU | 2 Core 4GB + GPU |
| Large Media Library | 2 Core 4GB | 4 Core 8GB |

### Required Software

- Docker ≥ 20.10
- Docker Compose ≥ 2.0
- Linux VPS (Ubuntu 22.04/24.04 or Debian 12 recommended)

---

## Step 1: Install Docker

If Docker isn't installed on your VPS:

```bash
# Install Docker
curl -fsSL https://get.docker.com | sh

# Add current user to docker group (avoids sudo every time)
sudo usermod -aG docker $USER

# Enable and start Docker
sudo systemctl enable docker
sudo systemctl start docker

# Verify installation
docker --version
docker compose version
```

> ⚠️ Log out and back in (or run `newgrp docker`) for group changes to take effect.

---

## Step 2: Create Directory Structure

```bash
# Create project directory
mkdir -p ~/jellyfin/{config,media,music,transcode}

# Create media directories
mkdir -p ~/jellyfin/media/{movies,tv-shows,anime}
mkdir -p ~/jellyfin/music

# Set permissions (needed for GPU transcoding)
sudo chmod -R 755 ~/jellyfin
```

### Directory Purpose

- **config/** — Jellyfin configuration, database, and cache
- **media/** — Movies, TV shows, and other media files
- **music/** — Music files
- **transcode/** — Transcoded temporary file output

---

## Step 3: Docker Compose Configuration

Create `~/jellyfin/docker-compose.yml`:

```yaml
services:
  jellyfin:
    image: jellyfin/jellyfin:latest
    container_name: jellyfin
    restart: unless-stopped
    user: 1000:1000
    ports:
      - "8096:8096"      # HTTP port
      - "8920:8920"      # HTTPS port
      - "7359:7359/udp"  # Service discovery (UPnP)
      - "1900:1900/udp"  # DLNA
    volumes:
      - ./config:/config
      - ./media:/media
      - ./music:/music
      - ./transcode:/transcode
    environment:
      - TZ=Asia/Shanghai
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.jellyfin.rule=Host(`jellyfin.yourdomain.com`)"
      - "traefik.http.services.jellyfin.loadbalancer.server.port=8096"
```

For hardware transcoding with an NVIDIA GPU, add:

```yaml
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    environment:
      - TZ=Asia/Shanghai
      - JELLYFIN_PublishedServerUrl=jellyfin.yourdomain.com
```

> ⚠️ **Note**: NVIDIA GPU transcoding requires installing the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html).

---

## Step 4: Start Jellyfin

```bash
cd ~/jellyfin
docker compose up -d
```

Visit `http://your-vps-ip:8096` to see the Jellyfin initial setup wizard.

---

## Step 5: Initial Setup

### 1. Create Admin Account

Follow the wizard to set up your admin username and password.

### 2. Add Media Libraries

Add your media folders in the settings panel:

- **Movies** — Point to `/media/movies`
- **TV Shows** — Point to `/media/tv-shows`
- **Anime** — Point to `/media/anime` (optional)
- **Music** — Point to `/music`

### 3. Configure Metadata Scrapers

Jellyfin automatically downloads posters, synopses, and other info from:

- TheMovieDB (default)
- TheTVDB
- TheAudioDB (music)

Enable metadata in your preferred language for localized titles and descriptions.

---

## Step 6: Hardware Transcoding (Recommended)

Software transcoding puts heavy CPU load, especially for 1080p/4K content. Hardware transcoding significantly reduces resource usage.

### Intel Quick Sync Video (QSV)

For VPS or servers with Intel integrated GPU:

```yaml
    devices:
      - /dev/dri:/dev/dri
    environment:
      - TZ=Asia/Shanghai
      - NVIDIA_DRIVER_CAPABILITIES=all
```

### NVIDIA GPU

```yaml
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    environment:
      - TZ=Asia/Shanghai
```

### Verify Transcoding Works

In the Jellyfin dashboard → Dashboard → Transcoding, check that hardware transcoding status shows as "available."

---

## Step 7: Reverse Proxy and HTTPS

A reverse proxy with HTTPS is strongly recommended for production use.

### Using Caddy

```caddy
jellyfin.yourdomain.com {
    reverse_proxy localhost:8096
    
    encode gzip zstd
    
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Content-Type-Options "nosniff"
    }
}
```

### Using Nginx

```nginx
server {
    listen 443 ssl http2;
    server_name jellyfin.yourdomain.com;

    ssl_certificate     /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8096;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket support for remote streaming
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

---

## Step 8: Organize Media Files

Proper file organization is critical for Jellyfin's metadata matching.

### Recommended Directory Structure

```
~/jellyfin/media/
├── movies/
│   ├── The Shawshank Redemption (1994)/
│   │   ├── The.Shawshank.Redemption.1994.1080p.mkv
│   │   ├── poster.jpg          # Optional, Jellyfin auto-downloads
│   │   └── fanart.jpg          # Optional
│   ├── Inception (2010)/
│   │   └── Inception.2010.4K.mkv
├── tv-shows/
│   ├── Breaking Bad/
│   │   ├── Season 1/
│   │   │   ├── Breaking Bad - S01E01 - Pilot.mkv
│   │   │   └── Breaking Bad - S01E02 - Cat's in the Bag.mkv
│   │   └── Season 2/
├── anime/
│   ├── Attack on Titan/
│   │   ├── Season 1/
│   │   └── Season 2/
└── music/
    ├── Artist Name/
    │   └── Album Name/
    │       ├── 01 - Song Title.flac
    │       └── 02 - Another Song.flac
```

### File Naming Conventions

Jellyfin uses file paths and names to match metadata. Follow these rules for best results:

- **Movies**: `Movie Title (Year).extension`
- **TV Shows**: `Show Name/Season XX/Show Name - S0XE0Y - Episode Title.extension`
- **Music**: `Artist Name/Album Name/TrackNumber - Song Title.extension`

---

## Step 9: Remote Access and External Streaming

Jellyfin supports multiple remote access solutions:

### Option 1: Cloudflare Tunnel (Recommended)

Zero configuration, no port exposure, most secure:

```bash
# Install cloudflared
curl -fsSL https://bin.equinox.io/c/bNyj1mQVY4c/cloudflared-stable-linux-amd64.tgz | tar xz
sudo mv cloudflared /usr/local/bin/

# Authenticate
cloudflared tunnel login

# Create tunnel
cloudflared tunnel create jellyfin
cloudflared tunnel route dns jellyfin jellyfin.yourdomain.com

# Configure
cloudflared tunnel config jellyfin
```

### Option 2: Tailscale

If all your client devices have Tailscale installed:

```bash
# Install Tailscale on VPS
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up

# Access Jellyfin directly via Tailscale IP + port
```

### Option 3: frp Reverse Tunnel

For low-latency streaming scenarios:

```ini
# frps.toml (server)
bindPort = 7000

# frpc.toml (client/VPS)
serverAddr = "your-server.com"
serverPort = 7000

[[proxies]]
name = "jellyfin"
type = "tcp"
localIP = "127.0.0.1"
localPort = 8096
remotePort = 8096
```

---

## Step 10: Backup and Automation

### Backup Jellyfin Configuration

```bash
#!/bin/bash
# backup-jellyfin.sh

BACKUP_DIR="/root/backups/jellyfin"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
mkdir -p "$BACKUP_DIR"

# Backup configuration
tar czf "$BACKUP_DIR/config_$TIMESTAMP.tar.gz" -C ~/jellyfin/config .

# Keep only last 30 days of backups
find "$BACKUP_DIR" -name "config_*.tar.gz" -mtime +30 -delete

echo "Backup completed: $BACKUP_DIR/config_$TIMESTAMP.tar.gz"
```

Add to crontab for daily automatic backup:

```bash
crontab -e
# Add this line (daily backup at 3 AM)
0 3 * * * /root/backup-jellyfin.sh
```

### Docker Auto-Restart

The `restart: unless-stopped` policy in `docker-compose.yml` ensures Jellyfin automatically starts after VPS reboots.

---

## Troubleshooting

### Q1: Videos Won't Play or Buffer Slowly

- Verify transcoding configuration is correct
- For remote access, ensure sufficient bandwidth (1080p: 5Mbps+, 4K: 25Mbps+)
- Enable hardware transcoding for significant performance improvement
- Check WebSocket support in proxy configuration

### Q2: Poor Metadata Matching

- Ensure proper file naming conventions (Movie Title Year.extension)
- Manually edit media info in Jellyfin
- Use `FileBot` for bulk file renaming
- Try different metadata sources (TheMovieDB / TheTVDB)

### Q3: Insufficient Disk Space

- Mount external storage (NAS, object storage)
- Configure Jellyfin cache path to a different partition
- Regularly clean transcode temp files (`transcode/` directory)
- Consider compressed video formats (HEVC/H.265)

### Q4: Mobile App Can't Connect

- Verify firewall rules allow the required ports
- If using a reverse proxy, confirm DNS resolution
- Try direct IP + port access (on local network)
- Install the official Jellyfin app (Android / iOS)

---

## Summary

This guide covered building a Jellyfin media server on VPS from scratch. Key takeaways:

1. **Docker One-Click Deployment** — Simple and reliable with `docker compose`
2. **Hardware Transcoding** — Significantly reduces CPU load, enables 4K streaming
3. **Reverse Proxy + HTTPS** — Foundation for security and remote access
4. **Proper Media Organization** — Well-structured file layouts enable accurate metadata matching
5. **Secure Remote Access** — Cloudflare Tunnel or Tailscale for safe external access

Your VPS is now a powerful home cinema. Whether 1080p or 4K, at home or on the go, enjoy your personal media library anytime, anywhere.

---

## Appendix: Complete docker-compose.yml

```yaml
services:
  jellyfin:
    image: jellyfin/jellyfin:latest
    container_name: jellyfin
    restart: unless-stopped
    user: 1000:1000
    ports:
      - "8096:8096"
      - "8920:8920"
      - "7359:7359/udp"
      - "1900:1900/udp"
    volumes:
      - ./config:/config
      - ./media:/media
      - ./music:/music
      - ./transcode:/transcode
    environment:
      - TZ=Asia/Shanghai
    # Uncomment for GPU transcoding
    # deploy:
    #   resources:
    #     reservations:
    #       devices:
    #         - driver: nvidia
    #           count: 1
    #           capabilities: [gpu]
```

> 📌 **Next Steps**: Set up automated media downloading (Jackett + Sonarr + Radarr) to keep your library automatically updated.
