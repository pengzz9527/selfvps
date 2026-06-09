---
title: "Jellyfin VPS 部署指南：在 VPS 上搭建私有媒体服务器，打造个人 Netflix"
description: "使用 Docker 在 VPS 上部署 Jellyfin 媒体服务器教程——支持硬件转码、多设备串流、远程访问和自动化管理，让你的 VPS 变成专属的私人影院"
date: 2026-06-09T10:00:00+08:00
lastmod: 2026-06-09T10:00:00+08:00
slug: "jellyfin-vps-media-server"
tags: ["Jellyfin", "媒体服务器", "Docker", "VPS部署", "自托管", "影音串流", "硬件转码"]
categories: ["部署教程"]
draft: false
image: /images/posts/jellyfin-vps-media-server/featured.png
aliases: [/zh/post/jellyfin-vps-media-server/]
---

## 为什么选择 Jellyfin？

你是否有过这样的经历：收藏了数百部电影和剧集，却因为没有合适的设备来整理和观看而吃灰？NAS 太贵，购买流媒体服务又意味着每月持续的订阅费用。

[Jellyfin](https://jellyfin.org/) 是一个**完全免费、开源**的媒体服务器软件，可以将你的 VPS 变成私人影音中心。它支持自动媒体库管理、多设备串流、硬件转码和远程访问，是 Plex 和 Emby 的最佳免费替代品。

### Jellyfin 的核心优势

| 特性 | Jellyfin | Plex | Emby |
|------|----------|------|------|
| 价格 | **完全免费** | 高级功能收费 | 部分功能收费 |
| 开源 | ✅ 完全开源 | ❌ 闭源 | ⚠️ 部分开源 |
| 硬件转码 | 免费 | 付费（Plex Pass） | 付费 |
| 自托管 | ✅ | ✅ | ✅ |
| 平台支持 | 全平台 | 全平台 | 全平台 |

- 🎬 **全自动媒体管理**：自动下载海报、剧情简介和元数据
- 📱 **多设备支持**：手机、平板、电视、浏览器均可访问
- 🔄 **实时转码**：根据网络带宽自动调整画质
- 🔒 **完全私有**：数据完全掌控在自己手中

---

## 环境准备

### VPS 配置建议

| 用途 | 最低配置 | 推荐配置 |
|------|----------|----------|
| 轻量使用（1080p 软解） | 1核 2GB | 2核 4GB |
| 硬件转码（推荐） | 1核 2GB + GPU | 2核 4GB + GPU |
| 大量媒体库 | 2核 4GB | 4核 8GB |

### 需要的软件

- Docker ≥ 20.10
- Docker Compose ≥ 2.0
- Linux VPS（推荐 Ubuntu 22.04/24.04 或 Debian 12）

---

## 第一步：安装 Docker

如果你的 VPS 还没有安装 Docker，运行以下命令：

```bash
# 安装 Docker
curl -fsSL https://get.docker.com | sh

# 将当前用户加入 docker 组（避免每次使用 sudo）
sudo usermod -aG docker $USER

# 重启 Docker 服务
sudo systemctl enable docker
sudo systemctl start docker

# 验证安装
docker --version
docker compose version
```

---

## 第二步：创建 Jellyfin 目录结构

```bash
# 创建项目目录
mkdir -p ~/jellyfin/{config,media,music,transcode}

# 创建媒体目录
mkdir -p ~/jellyfin/media/{movies,tv-shows,anime}
mkdir -p ~/jellyfin/music

# 设置权限（如果使用 GPU 转码需要这一步）
sudo chmod -R 755 ~/jellyfin
```

### 目录说明

- **config/** — Jellyfin 配置数据、数据库和缓存
- **media/** — 电影、电视剧等媒体文件
- **music/** — 音乐文件
- **transcode/** — 转码临时文件输出目录

---

## 第三步：编写 Docker Compose 文件

创建 `~/jellyfin/docker-compose.yml`：

```yaml
services:
  jellyfin:
    image: jellyfin/jellyfin:latest
    container_name: jellyfin
    restart: unless-stopped
    user: 1000:1000
    ports:
      - "8096:8096"     # HTTP 端口
      - "8920:8920"     # HTTPS 端口
      - "7359:7359/udp" # 服务发现（UPnP）
      - "1900:1900/udp" # DLNA
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

如果你使用硬件转码（NVIDIA GPU），需要额外添加：

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

> ⚠️ **注意**：使用 NVIDIA GPU 转码需要安装 [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)。

---

## 第四步：启动 Jellyfin

```bash
cd ~/jellyfin
docker compose up -d
```

启动后访问 `http://你的VPS_IP:8096`，你会看到 Jellyfin 的初始设置向导。

---

## 第五步：初始设置

### 1. 创建管理员账户

按照向导设置管理员用户名和密码。

### 2. 添加媒体库

在设置面板中添加你的媒体文件夹：

- **电影库** — 指向 `/media/movies`
- **电视剧库** — 指向 `/media/tv-shows`
- **动漫库** — 指向 `/media/anime`（可选）
- **音乐库** — 指向 `/music`

### 3. 配置元数据下载器

Jellyfin 会自动从以下来源下载海报、剧情简介等信息：

- TheMovieDB（默认）
- TheTVDB
- TheAudioDB（音乐）

建议在设置中启用中文元数据，这样你的媒体库会显示中文名称和简介。

---

## 第六步：配置硬件转码（推荐）

软件转码对 CPU 压力较大，尤其是 1080p/4K 视频。硬件转码可以大幅降低资源消耗。

### Intel Quick Sync Video（QSV）

对于支持 Intel GPU 的 VPS 或服务器：

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

### 验证转码是否正常工作

在 Jellyfin 控制面板 → 仪表板 → 转码中，查看硬件转码状态是否显示为"可用"。

---

## 第七步：配置反向代理和 HTTPS

生产环境强烈建议使用 Nginx 或 Caddy 做反向代理，并配置 HTTPS。

### 使用 Caddy

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

### 使用 Nginx

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
        
        # WebSocket 支持（用于远程串流）
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

---

## 第八步：媒体文件组织

良好的文件组织对 Jellyfin 的元数据匹配至关重要。

### 推荐的目录结构

```
~/jellyfin/media/
├── movies/
│   ├── The Shawshank Redemption (1994)/
│   │   ├── The.Shawshank.Redemption.1994.1080p.mkv
│   │   ├── poster.jpg          # 可选，Jellyfin 会自动下载
│   │   └── fanart.jpg          # 可选
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

### 文件命名规范

Jellyfin 使用文件路径和文件名来匹配元数据，遵循以下规则可以得到最佳匹配：

- **电影**：`电影名 (年份).扩展名`
- **电视剧**：`剧集名/Season XX/剧集名 - S0XE0Y - 集名.扩展名`
- **音乐**：`音乐名/专辑名/序号 - 歌名.扩展名`

---

## 第九步：远程访问和外网串流

Jellyfin 支持多种远程访问方案：

### 方案一：Cloudflare Tunnel（推荐）

零配置、无需开放端口，最安全：

```bash
# 安装 cloudflared
curl -fsSL https://bin.equinox.io/c/bNyj1mQVY4c/cloudflared-stable-linux-amd64.tgz | tar xz
sudo mv cloudflared /usr/local/bin/

# 认证
cloudflared tunnel login

# 创建隧道
cloudflared tunnel create jellyfin
cloudflared tunnel route dns jellyfin jellyfin.yourdomain.com

# 配置
cloudflared tunnel config jellyfin
```

### 方案二：Tailscale

如果你的客户端设备都安装了 Tailscale：

```bash
# 在 VPS 上安装 Tailscale
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up

# 将 Jellyfin 端口暴露给 Tailscale 网络
# 直接通过 Tailscale IP + 端口访问
```

### 方案三：frp 内网穿透

适合需要低延迟串流的场景：

```ini
# frps.toml (服务端)
bindPort = 7000

# frpc.toml (客户端/VPS)
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

## 第十步：备份和自动化

### 备份 Jellyfin 配置

```bash
#!/bin/bash
# backup-jellyfin.sh

BACKUP_DIR="/root/backups/jellyfin"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
mkdir -p "$BACKUP_DIR"

# 备份配置
tar czf "$BACKUP_DIR/config_$TIMESTAMP.tar.gz" -C ~/jellyfin/config .

# 只保留最近 30 天的备份
find "$BACKUP_DIR" -name "config_*.tar.gz" -mtime +30 -delete

echo "Backup completed: $BACKUP_DIR/config_$TIMESTAMP.tar.gz"
```

将其添加到 crontab 实现每日自动备份：

```bash
crontab -e
# 添加以下行（每天凌晨 3 点备份）
0 3 * * * /root/backup-jellyfin.sh
```

### Docker 自动重启策略

`docker-compose.yml` 中已设置 `restart: unless-stopped`，这保证了 Jellyfin 在 VPS 重启后自动启动。

---

## 常见问题

### Q1: 视频无法播放或卡顿

- 检查转码配置是否正确
- 如果是远程访问，确认带宽是否足够（1080p 需要 5Mbps+，4K 需要 25Mbps+）
- 启用硬件转码可大幅改善性能
- 检查代理配置中的 WebSocket 支持

### Q2: 元数据匹配不准

- 确保文件命名规范（电影名 年份.扩展名）
- 在 Jellyfin 中手动编辑媒体信息
- 使用 `FileBot` 批量重命名工具
- 尝试不同的元数据源（TheMovieDB / TheTVDB）

### Q3: 硬盘空间不足

- 使用外部存储挂载（如 NAS、对象存储）
- 配置 Jellyfin 的缓存路径到不同分区
- 定期清理转码临时文件（`transcode/` 目录）
- 考虑使用压缩视频格式（HEVC/H.265）

### Q4: 手机无法连接到 Jellyfin

- 确认防火墙开放了相应端口
- 如果使用反向代理，确认域名 DNS 解析正确
- 尝试直接使用 IP + 端口访问（内网环境）
- 安装 Jellyfin 官方 App（Android / iOS）

---

## 总结

通过本文，你已经学会了如何在 VPS 上从零搭建 Jellyfin 媒体服务器。核心要点：

1. **Docker 一键部署** — 使用 `docker compose` 管理，简单可靠
2. **硬件转码** — 显著降低 CPU 负担，支持 4K 串流
3. **反向代理 + HTTPS** — 安全和远程访问的基础
4. **规范的媒体组织** — 良好的文件结构让元数据自动匹配更精准
5. **安全远程访问** — Cloudflare Tunnel 或 Tailscale 实现安全外网访问

现在，你的 VPS 已经变成了一个功能强大的私人影院。无论是 1080p 还是 4K 内容，无论在家还是在外，随时随地享受属于你的影音时光。

---

## 附录：完整 docker-compose.yml

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
    # 如需 GPU 转码，取消下方注释
    # deploy:
    #   resources:
    #     reservations:
    #       devices:
    #         - driver: nvidia
    #           count: 1
    #           capabilities: [gpu]
```

> 📌 **下一步建议**：配置自动化媒体下载（Jackett + Sonarr + Radarr），让你的媒体库自动更新。
