---
title: "Home Assistant 自托管搭建指南：在 VPS 上部署开源智能家居中枢，完全掌控你的 IoT 设备"
description: "摆脱云服务和厂商锁定：在 VPS 上用 Docker 搭建 Home Assistant，统一管理所有智能家居设备，实现自动化场景、本地推理与隐私保护。"
date: 2026-06-07T10:00:00+08:00
slug: "home-assistant-vps-deploy"
tags: ["Home Assistant", "智能家居", "IoT", "Docker", "自托管", "自动化", "VPS", "开源"]
categories: ["自托管", "智能家居"]
aliases: [/zh/post/home-assistant-vps-deploy/]
draft: false
image: /images/posts/home-assistant-vps-deploy/featured.png
---

## 为什么要在 VPS 上运行 Home Assistant？

智能家居市场充斥着各种厂商的云服务——米家、HomeKit、Google Home、Alexa……每个平台都要求你将设备数据上传到他们的服务器。**隐私泄露、服务中断、厂商锁定**是长期自托管用户最头疼的问题。

**Home Assistant (HA)** 是一个开源的智能家居自动化平台，核心理念是：**所有数据处理都在本地完成，不依赖任何云服务**。将 HA 部署在 VPS 上，你可以：

- **统一管控多品牌设备** — 小米、苹果、三星、涂鸦等 3000+ 集成，一个平台全搞定
- **隐私完全可控** — 所有传感器数据和自动化逻辑都在你的服务器上运行
- **不受厂商服务中断影响** — 没有云服务宕机，你的自动化永远在线
- **低延迟响应** — 本地设备联动无需经过云端，响应在毫秒级
- **远程控制** — 搭配 Let's Encrypt 证书 + 反向代理，随时随地从手机访问

---

## 系统架构

```
┌─────────────────────────────────────────────────────┐
│                   你的手机 / 平板                      │
│              📱 Home Assistant App                    │
└──────────────┬──────────────────────────────────────┘
               │ HTTPS (wss://your-domain.com)
               ▼
┌─────────────────────────────────────────────────────┐
│              反向代理 (Caddy / Nginx)                 │
│         Let's Encrypt TLS + WebSocket 代理          │
└──────────────┬──────────────────────────────────────┘
               │ localhost:8123
               ▼
┌─────────────────────────────────────────────────────┐
│           VPS / 云服务器 (Debian 12+)                 │
│                                                     │
│  ┌───────────────────────────────────────────────┐  │
│  │        Docker Container: Home Assistant       │  │
│  │                                               │  │
│  │  ┌───────────┐  ┌──────────┐  ┌───────────┐  │  │
│  │  │ Core 核心  │  │ 集成插件  │  │ 自动化引擎│  │  │
│  │  │ (Python)  │  │3000+     │  │Blueprints │  │  │
│  │  └───────────┘  └──────────┘  └───────────┘  │  │
│  │         │                    │                │  │
│  │  ┌──────▼────┐    ┌─────────▼──────────┐     │  │
│  │  │  SQLite / │    │  自动化规则引擎     │     │  │
│  │  │  InfluxDB │    │  如果…就… 触发器    │     │  │
│  │  └───────────┘    └────────────────────┘     │  │
│  └───────────────────────────────────────────────┘  │
│                                                     │
│  ┌───────────────────────────────────────────────┐  │
│  │              设备集成层                         │  │
│  │  WiFi: 小米 · 苹果 · 涂鸦 ·  Philips Hue      │  │
│  │  Zigbee: Zigbee2MQTT / ZHA                    │  │
│  │  MQTT: 大量开源 IoT 设备                        │  │
│  │  HTTP: 任何支持 API 的设备                      │  │
│  └───────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

---

## 第一步：环境准备

### 推荐配置

| 配置项 | 最低配置 | 推荐配置 |
|--------|----------|----------|
| CPU | 1 核 | 2 核 |
| 内存 | 1 GB | 2 GB+ |
| 存储 | 16 GB SSD | 32 GB+ SSD |
| 网络 | 普通带宽 | 10 Mbps+ |
| 操作系统 | Debian 12 / Ubuntu 22.04 | Debian 12 |

> **提示：** Home Assistant 本身不需要太大资源。如果你的 VPS 内存 ≥4 GB，可以额外跑 MQTT  broker（Mosquitto）、InfluxDB 时序数据库等增强功能。

### 安装 Docker

```bash
# 更新系统
apt update && apt upgrade -y

# 安装 Docker
curl -fsSL https://get.docker.com | sh

# 将当前用户加入 docker 组（避免每次 sudo）
usermod -aG docker $USER
newgrp docker

# 验证安装
docker --version
docker compose version
```

---

## 第二步：部署 Home Assistant

### 方法一：Docker Compose（推荐）

创建一个专用目录并编写 `docker-compose.yml`：

```bash
mkdir -p ~/home-assistant
cd ~/home-assistant
```

创建 `docker-compose.yml`：

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
    network_mode: host  # Home Assistant 推荐 host 模式
    # 如果使用 bridge 模式，需要映射端口：
    # ports:
    #   - "8123:8123"
```

启动容器：

```bash
docker compose up -d
```

### 方法二：直接使用 Docker run

```bash
docker run -d \
  --name homeassistant \
  --restart=unless-stopped \
  -v /root/home-assistant/config:/config \
  -v /etc/localtime:/etc/localtime:ro \
  --network=host \
  ghcr.io/home-assistant/home-assistant:stable
```

### 验证部署

```bash
# 查看日志
docker logs -f homeassistant

# 等待几秒后访问
# 浏览器打开 http://你的VPS_IP:8123
```

首次启动时，Home Assistant 会进行初始化配置，包括创建管理员账户和选择地区。

---

## 第三步：配置 HTTPS 和远程访问

直接在浏览器通过 IP 访问 HA 不方便也不安全。我们用 Caddy 作为反向代理来实现 HTTPS 访问。

### 安装 Caddy

```bash
# 方式一：Docker 安装
mkdir -p ~/caddy-data
cat > ~/caddy/Caddyfile << 'EOF'
your-domain.com {
    reverse_proxy localhost:8123
    
    # 安全头
    header {
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
    }
}
EOF
```

### 使用 Caddy 代理 Home Assistant

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

启动 Caddy：

```bash
cd ~/caddy && docker compose up -d
```

现在你可以通过 `https://your-domain.com` 安全地访问 Home Assistant，Let's Encrypt 会自动为你签发证书。

### 配置 Home Assistant 内部设置

在 HA 界面的 **Settings → System → Network** 中：

1. 确保 **Home Assistant URL** 设置为 `https://your-domain.com`
2. 启用 **SSL** 选项
3. 关闭 **Allow X-Forwarded-For headers**（如果通过 Caddy 代理）

---

## 第四步：接入智能设备

Home Assistant 的强大之处在于它能接入几乎任何品牌的设备。以下是几种常见的接入方式：

### 方式一：集成现有品牌设备

HA 内置了 3000+ 集成。在 **Settings → Devices & Services → Add Integration** 中搜索：

- **Xiaomi Mi Home** — 接入小米生态链设备（米家传感器、空调、灯泡等）
- **Tuya** — 接入涂鸦平台的所有设备
- **Aqara** — 接入苹果 HomeKit 生态的 Aqara 设备
- **Philips Hue** — 飞利浦智能照明
- **TP-Link/Kasa** — TP-Link 智能插座
- **Sonoff** — 易微联生态设备

### 方式二：Zigbee 设备（推荐 Zigbee2MQTT）

如果你有一批 Zigbee 设备（如 Aqara 传感器、小米门窗传感器），这是最佳方案：

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
      - /dev/ttyACM0:/dev/ttyACM0  # Zigbee USB 适配器
    network_mode: host
```

需要一个 Zigbee USB 适配器（如 CC2652P），插在 VPS 的 USB 口或通过 USB-over-IP 桥接到 VPS。

### 方式三：MQTT 协议接入开源设备

大量开源硬件（ESPHome、Home Assistant GlowWave 等）使用 MQTT 协议。

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

在 HA 中，MQTT 集成只需要配置 broker 地址即可自动发现所有发布 MQTT 消息的设备。

---

## 第五步：创建自动化场景

Home Assistant 的自动化引擎是整个系统的核心。你可以用图形化界面或 YAML 配置自动化逻辑。

### 场景一：离家模式

```yaml
# configuration.yaml 中的自动化示例
automation:
  - alias: "离家模式"
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
          message: "🏠 离家模式已开启，所有灯光已关闭"
```

### 场景二：人来灯亮，人走灯灭

```yaml
  - alias: "人来灯亮"
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

  - alias: "人走灯灭"
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

### 场景三：温度自适应空调

```yaml
  - alias: "温度自适应调节"
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

## 第六步：增强功能

### 安装 InfluxDB + Grafana 可视化

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

在 Home Assistant 中安装 **InfluxDB** 集成，配置输出历史数据到 InfluxDB，然后用 Grafana 连接 InfluxDB 创建可视化面板。

### 语音助手集成

```yaml
# 安装 voice-assistant 集成后，在 configuration.yaml 添加：
conversation:
  language: "zh"

tts:
  - platform: edge_tts
    service_name: edge_tts_say
    language: zh-CN
    voice: zh-CN-XiaoxiaoNeural
```

### 备份策略

```bash
#!/bin/bash
# ~/home-assistant/backup.sh

DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/backup/home-assistant"
CONFIG_DIR="/root/home-assistant/config"

# 创建备份
mkdir -p "$BACKUP_DIR"
tar czf "$BACKUP_DIR/ha-backup-$DATE.tar.gz" \
  -C /root/home-assistant config/

# 删除 30 天前的备份
find "$BACKUP_DIR" -name "ha-backup-*.tar.gz" -mtime +30 -delete

# 可选：上传到云存储
# rclone copy "$BACKUP_DIR/ha-backup-$DATE.tar.gz" remote:ha-backups/
```

添加到 crontab：

```bash
crontab -e
# 每天凌晨 3 点备份
0 3 * * * /root/home-assistant/backup.sh
```

---

## 第七步：安全加固

### 1. 启用 Two-Factor Authentication (2FA)

在 HA 界面中启用 **Google Authenticator** 集成，为所有用户账户配置双因素认证。

### 2. 网络隔离

```yaml
# 使用 Docker 网络隔离 HA 容器
version: "3.8"

services:
  homeassistant:
    networks:
      - ha-net
    # 不暴露任何端口到宿主机

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

### 3. 保持更新

```bash
# 每天检查更新
docker compose pull && docker compose up -d

# 或使用 Watchtower 自动更新
docker run -d \
  --name watchtower \
  --volume /var/run/docker.sock:/var/run/docker.sock \
  containrrr/watchtower \
  --cleanup --interval 21600 --label-enable
```

### 4. 限制 API 访问

在 `configuration.yaml` 中：

```yaml
http:
  ssl_certificate: /config/ssl/fullchain.pem
  ssl_key: /config/ssl/privkey.pem
  trusted_proxies:
    - 172.18.0.0/16  # Docker 内部网络
    - ::1              # localhost IPv6
```

---

## 常见问题排查

### 问题 1：WebSockets 连接断开

Home Assistant 通过 WebSockets 实现实时更新。如果连接频繁断开：

```bash
# 检查防火墙是否允许 WebSocket
# 确保反向代理配置中包含 WebSocket 支持
# Caddy 配置自动支持 WebSocket，无需额外配置

# 在 Caddyfile 中确保：
# reverse_proxy localhost:8123
# 不需要额外的 websocket 配置
```

### 问题 2：设备扫描找不到设备

- 确保所有设备在同一局域网
- 如果使用 bridge 网络模式，HA 无法发现局域网设备
- 使用 `network_mode: host` 或配置 mDNS/Bonjour

### 问题 3：自动化延迟高

- 检查 InfluxDB 或 SQLite 是否磁盘 I/O 瓶颈
- 减少不必要的时间间隔触发器
- 对频繁变化的传感器考虑使用事件驱动而非轮询

### 问题 4：内存占用过高

```bash
# 检查 HA 容器资源使用
docker stats homeassistant

# 限制 HA 的内存使用
# 在 docker-compose.yml 中添加：
mem_limit: 1g
mem_reservation: 512m
```

---

## 总结

| 步骤 | 操作 | 预计时间 |
|------|------|----------|
| 1 | 环境准备 | 15 分钟 |
| 2 | 部署 Home Assistant | 10 分钟 |
| 3 | 配置 HTTPS 和域名 | 15 分钟 |
| 4 | 接入设备 | 30-60 分钟 |
| 5 | 创建自动化 | 30-60 分钟 |
| 6 | 增强功能 | 按需 |
| 7 | 安全加固 | 20 分钟 |

**总耗时约 2-3 小时**，之后你就可以拥有一个完全由你掌控的智能家庭中枢了。

Home Assistant 的核心价值在于：**你的家，由你做主**。没有厂商锁定、没有数据泄露风险、没有服务中断。一台廉价的 VPS（月租 $3-5）就能实现这一切。

---

*本文内容基于 Home Assistant 2026.6 版本。如有版本差异，请参考 [Home Assistant 官方文档](https://www.home-assistant.io/docs/)。*
