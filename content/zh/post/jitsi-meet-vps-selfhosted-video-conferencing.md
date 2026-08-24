---
title: "自建 Jitsi Meet 视频会议：VPS 私有化部署完整指南，零成本替代 Zoom"
description: "手把手教你在 VPS 上部署 Jitsi Meet 视频会议系统，支持多人高清通话、屏幕共享、会议录制。完全私有化部署，无需付费订阅，保护隐私的同时大幅降低企业通讯成本。"
date: 2026-08-24T10:00:00+08:00
lastmod: 2026-08-24T10:00:00+08:00
slug: "jitsi-meet-vps-selfhosted-video-conferencing"
tags: ["Jitsi Meet", "视频会议", "自托管", "VPS部署", "开源方案", "Zoom替代", "Docker", "隐私保护"]
categories: ["自托管"]
draft: false
image: /images/posts/jitsi-meet-vps-selfhosted-video-conferencing/featured.png
aliases: [/zh/post/jitsi-meet-vps-selfhosted-video-conferencing/]
---

## 引言：为什么选择自建 Jitsi Meet？

Zoom、Google Meet 和 Microsoft Teams 虽然功能强大，但都存在明显的短板：**收费模式越来越激进**、**隐私数据存在合规风险**、**企业版功能门槛高**。对于个人用户、小团队和中小企业来说，自建视频会议系统是最优解。

**Jitsi Meet** 是目前最成熟的开源视频会议方案之一，具有以下核心优势：

- **完全免费开源**：无会议时长限制，无参会人数收费
- **零配置入会**：无需注册账号，打开链接即可加入
- **端到端加密**：可选开启 E2E 加密，保护会议内容
- **功能完整**：支持屏幕共享、会议录制、虚拟背景、聊天室
- **私有化部署**：所有数据存于你自己的服务器，无第三方访问

## 系统要求与架构设计

### 最低配置要求

| 参会规模 | CPU | 内存 | 带宽 | 推荐配置 |
|---------|-----|------|------|---------|
| 10人以下 | 2核 | 2GB | 10Mbps | 入门级 VPS |
| 20-50人 | 4核 | 4GB | 50Mbps | 标准 VPS |
| 50人以上 | 8核 | 8GB+ | 100Mbps+ | 高性能 VPS |

### 架构组件

Jitsi Meet 由以下核心组件构成：

1. **Jitsi Videobridge (JVB)**：媒体转发服务器，处理音视频流
2. **Jitsi Meet (Web)**：前端界面，基于 React 的 Web 应用
3. **Prosody**：XMPP 服务器，处理认证和信令
4. **Nginx**：反向代理，处理 HTTPS 和 WebSocket
5. **Jicofo**：会议控制器，管理媒体流路由

## 第一步：服务器准备

### 1.1 选择 VPS 服务商

推荐使用以下 VPS 服务商（按性价比排序）：

| 服务商 | 起步价 | 特点 |
|--------|--------|------|
| **Hetzner** | €4.51/月 | 欧洲超低资费，性能强劲 |
| **RamNode** | $5/月 | 不限流量，性价比极高 |
| **CloudCone** | $4.5/月 | 美国节点，稳定可靠 |
| **BandwagonHost** | $29/年 | 中文友好，CN2 线路 |
| **DigitalOcean** | $6/月 | 生态完善，文档丰富 |

### 1.2 系统安装

建议使用 Debian 12 或 Ubuntu 22.04 LTS：

```bash
# SSH 登录服务器
ssh root@your-vps-ip

# 更新系统
apt update && apt upgrade -y

# 安装基础工具
apt install -y curl wget git vim htop net-tools

# 设置 hostname
hostnamectl set-hostname meet.yourdomain.com
```

## 第二步：域名与 SSL 证书

### 2.1 配置 DNS

在域名管理面板中添加 A 记录：

```
meet.yourdomain.com  →  你的VPS_IP
```

### 2.2 安装 Nginx 和 Certbot

```bash
# 安装 Nginx
apt install -y nginx certbot python3-certbot-nginx

# 创建 Nginx 配置文件
cat > /etc/nginx/sites-available/jitsi << 'EOF'
server {
    listen 80;
    server_name meet.yourdomain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name meet.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/meet.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/meet.yourdomain.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    # 安全头
    add_header X-Frame-Options SAMEORIGIN always;
    add_header X-Content-Type-Options nosniff always;
    add_header Strict-Transport-Security "max-age=31536000" always;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF

ln -s /etc/nginx/sites-available/jitsi /etc/nginx/sites-enabled/
nginx -t && systemctl restart nginx

# 申请 SSL 证书
certbot --nginx -d meet.yourdomain.com --non-interactive --agree-tos -m your@email.com
```

## 第三步：Docker 部署 Jitsi Meet

### 3.1 安装 Docker

```bash
# 安装 Docker
curl -fsSL https://get.docker.com | sh

# 添加用户到 docker 组
usermod -aG docker $USER

# 启动 Docker
systemctl enable docker && systemctl start docker
```

### 3.2 克隆 Jitsi Meet 项目

```bash
# 创建工作目录
mkdir -p /opt/jitsi && cd /opt/jitsi

# 克隆 jitsi/docker-jitsi-meet
git clone https://github.com/jitsi/docker-jitsi-meet.git
cd docker-jitsi-meet

# 复制环境变量模板
cp .env.example .env
```

### 3.3 配置环境变量

编辑 `.env` 文件：

```bash
# =============== 核心配置 ===============
# 域名
DOMAIN=meet.yourdomain.com

# 随机生成的安全密码（必需）
JITSI_METEOR_INTERNAL_SECRET=MbEiVsHbcspvFgzFs
JICOFO_AUTH_PASSWORD=Kns4xJh7Qz9Km2Lp
PROSODY_AUTH_PASSWORD=Lp8Nx5Qw2Yz7Km3J

# 生成随机密码
# openssl rand -hex 16

# =============== JVB 配置 ===============
# 媒体转发器配置
JVB_ADVERTISE_IPS=
JVB_STUN_SERVERS=stun.l.google.com:19302,stun1.l.google.com:19302

# =============== 录制配置（可选） ===============
# ENABLE_RECORDING=1
# RECORDING_STORAGE_PATH=/opt/jitsi/recordings

# =============== 安全配置 ===============
# 启用 E2E 加密（可选，会增加 CPU 负载）
# ENABLE_ENCRYPTION=1
```

### 3.4 启动服务

```bash
# 首次启动（耗时较长，约 5-10 分钟）
./install.sh

# 启动 Jitsi Meet
docker compose up -d

# 查看运行状态
docker compose ps
docker compose logs -f jitsi-web
```

### 3.5 访问测试

浏览器打开 `https://meet.yourdomain.com`，你应该能看到 Jitsi Meet 界面。

创建测试会议：
1. 输入会议室名称（如 `test-meeting`）
2. 输入你的名字
3. 点击"加入"
4. 允许浏览器访问摄像头和麦克风

## 第四步：性能优化

### 4.1 调整 JVB 资源限制

编辑 `config/jvb/sip-communicator.properties`：

```properties
# 最大参会人数
org.jitsi.videobridge.xmpp.user.shard.MAX_PARTICIPANTS=50

# 带宽限制（bps）
org.jitsi.videobridge.BANDWIDTH_VOICE=128000
org.jitsi.videobridge.BANDWIDTH_AUDIO=64000
org.jitsi.videobridge.BANDWIDTH_VGA_15=600000
org.jitsi.videobridge.BANDWIDTH_HD=1500000
org.jitsi.videobridge.BANDWIDTH_FHD=3000000

# 并发流限制
org.jitsi.videobridge.ENABLE_STATISTICS=true
org.jitsi.videobridge.TLS_MAX_CONCURRENT_STREAMS=200
```

### 4.2 Nginx 优化

编辑 `/etc/nginx/nginx.conf`：

```nginx
worker_processes auto;
worker_rlimit_nofile 65535;

events {
    worker_connections 4096;
    multi_accept on;
    use epoll;
}

http {
    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    types_hash_max_size 2048;

    # Gzip 压缩
    gzip on;
    gzip_vary on;
    gzip_proxied any;
    gzip_comp_level 6;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml;

    # 超时优化
    client_body_timeout 12;
    client_header_timeout 12;
    send_timeout 10;
}
```

### 4.3 系统级优化

```bash
# 编辑 /etc/sysctl.conf
cat >> /etc/sysctl.conf << 'EOF'
# 网络优化
net.core.somaxconn = 65535
net.ipv4.tcp_max_syn_backlog = 8192
net.ipv4.tcp_tw_reuse = 1
net.ipv4.ip_local_port_range = 1024 65535

# 文件描述符
fs.file-max = 65535
fs.nr_open = 65535

# 内存优化
vm.swappiness = 10
vm.dirty_ratio = 10
vm.dirty_background_ratio = 5
EOF

sysctl -p
```

## 第五步：安全加固

### 5.1 启用 E2E 加密

在 `.env` 中启用：

```bash
ENABLE_ENCRYPTION=1
```

然后重启服务：

```bash
docker compose down && docker compose up -d
```

### 5.2 配置密码保护

Jitsi Meet 支持会议室密码功能。在会议创建界面，用户可以设置密码保护。

### 5.3 启用限流防护

编辑 `config/jicofo/sip-communicator.properties`：

```properties
# 每分钟最大新会话数
org.jitsi.jicofo.bridge.channel-per-busy-period=10
org.jitsi.jicofo.session-per-channel-per-busy-period=5
```

### 5.4 防火墙规则

```bash
# 安装 UFW
apt install -y ufw

# 配置防火墙
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp       # SSH
ufw allow 80/tcp       # HTTP
ufw allow 443/tcp      # HTTPS
ufw allow 10000/udp    # JVB 媒体端口
ufw allow 5349/tcp     # JVB TCP fallback
ufw enable

# 查看状态
ufw status verbose
```

## 第六步：功能增强

### 6.1 启用会议录制

```bash
# 在 .env 中启用录制
ENABLE_RECORDING=1

# 创建录制目录
mkdir -p /opt/jitsi/recordings
chmod 755 /opt/jitsi/recordings
```

录制文件保存在 `/opt/jitsi/recordings/` 目录下，格式为 MP4。

### 6.2 LDAP/AD 集成

```bash
# 在 .env 中配置 LDAP
ENABLE_AUTH=1
ENABLE_GUESTS=1
LDAP_URL=ldap://ldap.example.com
LDAP_BASE_DC=dc=example,dc=com
LDAP_BIND_DN=cn=admin,dc=example,dc=com
LDAP_BIND_PW=your_ldap_password
LDAP_FILTER=(uid=$username)
```

然后重启服务以应用 LDAP 配置。

### 6.3 多服务器集群部署

对于大规模使用，可以考虑集群部署：

```
                    ┌─────────────┐
                    │   Nginx     │
                    │  (负载均衡)  │
                    └──────┬──────┘
                           │
           ┌───────────────┼───────────────┐
           │               │               │
    ┌──────▼──────┐ ┌─────▼──────┐ ┌─────▼─────┐
    │  JVB Node 1 │ │ JVB Node 2 │ │ JVB Node 3│
    │  (媒体转发)  │ │            │ │           │
    └─────────────┘ └────────────┘ └───────────┘
           │               │               │
           └───────────────┼───────────────┘
                           │
                    ┌──────▼──────┐
                    │  Prosody    │
                    │  (信令认证)  │
                    └─────────────┘
```

## 成本对比：自建 vs 云服务

| 方案 | 月费 | 参会人数 | 功能 |
|------|------|---------|------|
| **Zoom 免费版** | $0 | 40分钟/场 | 基础功能 |
| **Zoom Pro** | $15/人/月 | 无限时长 | 云录制 |
| **Google Meet** | $6/人/月 | 100人 | 集成 GSuite |
| **自建 Jitsi Meet** | VPS费用 | 取决于配置 | 全部功能 |

以 Hetzner CPX31 为例（€4.51/月，2 vCPU, 2GB RAM）：
- 可支持 10-15 人同时会议
- 无时长限制
- 无参会人数收费
- 完全私有化

## 故障排查

### 常见问题 1：视频无法连接

```bash
# 检查 JVB 状态
docker compose logs jitsi-videobridge

# 检查防火墙
ufw status

# 确认 UDP 10000 端口开放
netstat -ulnp | grep jvb
```

### 常见问题 2：音频有问题

```bash
# 检查音频配置
docker compose logs jitsi-jicofo | grep -i audio

# 在浏览器中测试音频
# 打开 https://your-domain.com/test-audio
```

### 常见问题 3：服务器内存不足

```bash
# 查看内存使用
free -h

# 限制单用户带宽
# 编辑 config/jvb/sip-communicator.properties
org.jitsi.videobridge.BANDWIDTH_VGA_15=300000
```

### 常见问题 4：SSL 证书过期

```bash
# 自动续期
certbot renew --dry-run

# 设置定时任务
echo "0 3 * * * certbot renew --quiet" | crontab -
```

## 总结

自建 Jitsi Meet 视频会议系统是一次值得的投资。一次性配置后，你可以：

- ✅ **零月费**：无需支付 Zoom/Teams 订阅费
- ✅ **数据隐私**：所有会议数据留在自己的服务器
- ✅ **无限时长**：不再有 40 分钟限制
- ✅ **功能完整**：屏幕共享、录制、聊天、虚拟背景
- ✅ **易于维护**：Docker 部署，一键更新

对于小团队（10-50人）来说，一台 $5-10/月的 VPS 就能满足日常会议需求，相比云服务的按人收费，每年可节省数百至数千元。

---

**延伸阅读**：
- [Jitsi Meet 官方文档](https://jitsi.github.io/handbook/)
- [Docker-Jitsi-Meet GitHub](https://github.com/jitsi/docker-jitsi-meet)
- [Jitsi 性能调优指南](https://jitsi.github.io/handbook/docs/performance)
