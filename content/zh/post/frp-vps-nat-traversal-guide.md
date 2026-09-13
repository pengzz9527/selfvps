---
title: "VPS 内网穿透实战：FRP 自建高速反向代理，打通私有网络"
description: "没有公网 IP 也能让外界访问你的服务。FRP（Fast Reverse Proxy）帮你用一台有公网 IP 的 VPS 做穿透中转，免费、高速、完全可控，替代付费穿透服务。"
date: 2026-09-13T10:00:00+08:00
lastmod: 2026-09-13T10:00:00+08:00
slug: "frp-vps-nat-traversal-guide"
tags: ["VPS", "FRP", "内网穿透", "反向代理", "NAT", "自托管", "网络", "穿透服务"]
categories: ["网络工具"]
draft: false
image: /images/posts/frp-vps-nat-traversal-guide/featured.png
aliases: [/zh/post/frp-vps-nat-traversal-guide/]
---

## 为什么需要内网穿透？

你在家里的 NAS 上跑了 Plex、搭了 Nextcloud，回家却连不上——因为小区宽带没有公网 IP。你在 VPS 上部署了个人博客，但只想让朋友通过域名访问，不想暴露 SSH 端口。你有一台树莓派在角落吃灰，上面跑了 Home Assistant，但出门后就再也控制不了。

这些场景的共同痛点是：**设备在内网，服务却想对外暴露**。

传统方案有几种：DDNS + 端口映射（需要路由器支持且暴露风险大）、付费穿透服务（如 ngrok 商业版，按月收费）、Cloudflare Tunnel（免费但功能有限）。今天介绍另一种方案：**FRP**——免费、开源、高速、完全自控。

---

## FRP 是什么？

FRP（Fast Reverse Proxy）是一个高性能的反向代理应用，专注于为内网服务提供公网访问能力。它由 fatedier 开发，GitHub 星标超过 75,000，是目前最流行的开源穿透工具之一。

核心架构很简单：

```
互联网 ──▶ [FRP 服务端] ──▶ [FRP 客户端] ──▶ 内网服务
            (VPS, 公网IP)    (家中/办公室)    (NAS/树莓派/本地开发机)
```

- **frps（服务端）**：部署在有公网 IP 的 VPS 上，监听穿透端口
- **frpc（客户端）**：部署在内网设备上，连接服务端并注册要暴露的服务
- **穿透协议**：支持 TCP、UDP、HTTP、HTTPS、STCP（隐藏服务）、SUDP 等多种模式

---

## 前置条件

- 一台有公网 IP 的 VPS（可以是低配，带宽 1-5Mbps 即可）
- 内网设备（NAS、树莓派、家庭服务器等）
- 内网设备能主动访问外网（大多数情况满足）

---

## 第一步：部署 FRP 服务端

### 1. 下载与安装

登录到你的 VPS，下载最新版本的 FRP：

```bash
# 查看最新版本
FRP_VERSION=$(curl -s https://api.github.com/repos/fatedier/frp/releases/latest | grep tag_name | cut -d'"' -f4)
echo "Latest version: $FRP_VERSION"

# 下载 Linux amd64 版本
wget "https://github.com/fatedier/frp/releases/download/${FRP_VERSION}/frp_${FRP_VERSION}_linux_amd64.tar.gz"
tar -xzf "frp_${FRP_VERSION}_linux_amd64.tar.gz"
cd "frp_${FRP_VERSION}_linux_amd64"
```

### 2. 配置 frps

编辑 `frps.ini`（新版使用 `frps.toml`）：

```toml
# frps.toml
bindPort = 7000
vhostHTTPPort = 80
vhostHTTPSPort = 443

# Web 控制面板（可选，方便查看连接状态）
webServer.addr = "0.0.0.0"
webServer.port = 7500
webServer.user = "admin"
webServer.password = "your_strong_password_here"

# 认证 token（关键安全设置）
token = "your_secret_token_2026"

# 连接池配置
maxPoolCount = 50
heartbeatTimeout = 90

# 日志
log.to = "/var/log/frps.log"
log.level = "info"
log.maxDays = 7
```

### 3. 设置 systemd 服务

```bash
sudo cp frps /usr/local/bin/
sudo cp assets/frps/systemd/frps.service /etc/systemd/system/

# 修改 service 文件中的路径
sudo sed -i 's|/etc/frp/frps.ini|/root/frp/frps.toml|' /etc/systemd/system/frps.service
sudo sed -i 's|/usr/bin/frps|/usr/local/bin/frps|' /etc/systemd/system/frps.service

sudo systemctl daemon-reload
sudo systemctl enable frps
sudo systemctl start frps
sudo systemctl status frps
```

### 4. 配置防火墙

```bash
# 只开放必要端口
sudo ufw allow 7000/tcp   # FRP 主连接
sudo ufw allow 7500/tcp   # Web 面板（可选）
sudo ufw allow 80/tcp     # HTTP 虚拟主机（可选）
sudo ufw allow 443/tcp    # HTTPS 虚拟主机（可选）
sudo ufw reload
```

---

## 第二步：部署 FRP 客户端

### 1. 在 NAS / 树莓派上安装

以树莓派（Linux ARM64）为例：

```bash
# 下载对应平台版本
FRP_VERSION=$(curl -s https://api.github.com/repos/fatedier/frp/releases/latest | grep tag_name | cut -d'"' -f4)
wget "https://github.com/fatedier/frp/releases/download/${FRP_VERSION}/frp_${FRP_VERSION}_linux_arm64.tar.gz"
tar -xzf "frp_${FRP_VERSION}_linux_arm64.tar.gz"
cd "frp_${FRP_VERSION}_linux_arm64"
```

### 2. 配置 frpc

```toml
# frpc.toml
serverAddr = "your-vps-public-ip"
serverPort = 7000
token = "your_secret_token_2026"

# 心跳间隔
heartbeatInterval = 30
heartbeatTimeout = 90

# DNS 解析优化（防止 DNS 污染）
dnsServer = "8.8.8.8"

[[proxies]]
name = "ssh-home"
type = "tcp"
localIP = "127.0.0.1"
localPort = 22
remotePort = 2222

[[proxies]]
name = "nextcloud"
type = "https"
localIP = "192.168.1.100"
localPort = 443
customDomains = ["nextcloud.yourdomain.com"]

[[proxies]]
name = "plex"
type = "https"
localIP = "192.168.1.100"
localPort = 32400
customDomains = ["plex.yourdomain.com"]

[[proxies]]
name = "homeassistant"
type = "stcp"           # 隐藏服务，只有授权用户可访问
localIP = "192.168.1.50"
localPort = 8123
sk = "your_stcp_secret"
allowUsers = ["admin"]

[[proxies]]
name = "raspi-stats"
type = "tcp"
localIP = "127.0.0.1"
localPort = 9090
remotePort = 9090
```

### 3. 设置客户端自启动

```bash
sudo cp frpc /usr/local/bin/
sudo tee /etc/systemd/system/frpc.service > /dev/null << 'EOF'
[Unit]
Description=FRPC Client
After=network.target

[Service]
Type=simple
User=root
ExecStart=/usr/local/bin/frpc -c /root/frp/frpc.toml
ExecReload=/usr/local/bin/frpc -reload -c /root/frp/frpc.toml
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable frpc
sudo systemctl start frpc
sudo systemctl status frpc
```

---

## 第三步：配置域名与 HTTPS

### 1. DNS 解析

在你的域名服务商处添加 DNS 记录：

```
nextcloud.yourdomain.com  →  VPS 公网 IP
plex.yourdomain.com       →  VPS 公网 IP
```

### 2. 使用 Caddy 做 TLS 终结（推荐）

在 VPS 上安装 Caddy，让它处理 HTTPS：

```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install caddy
```

配置 `/etc/caddy/Caddyfile`：

```
nextcloud.yourdomain.com {
    reverse_proxy localhost:8080
    encode gzip
}

plex.yourdomain.com {
    reverse_proxy localhost:8081
    encode gzip
}
```

然后修改 frps.toml，让 Caddy 的 8080/8081 端口与 FRP 对接。或者更简单的方式——直接在 frps 中配置 TLS：

```toml
# frps.toml - 启用 TLS
vhostHTTPSPort = 443

[[httpsServers]]
addr = "0.0.0.0:443"
certificate = "/path/to/fullchain.pem"
private_key = "/path/to/privkey.pem"
```

用 Certbot 获取证书：

```bash
sudo certbot certonly --standalone -d nextcloud.yourdomain.com -d plex.yourdomain.com
```

---

## 高级用法

### STCP 隐身穿透（推荐用于敏感服务）

STCP（Secret TCP）模式不暴露 remotePort，只有同样配置了 `sk` 的客户端才能访问：

```toml
# 服务端（frps.toml）- 无需额外配置

# 内网侧（frpc.toml）
[[proxies]]
name = "hidden-service"
type = "stcp"
localIP = "127.0.0.1"
localPort = 3389       # RDP
sk = "super_secret_key"
allowUsers = ["viewer"]

# 访问侧（另一台 frpc.toml）
[[visitors]]
name = "hidden-service visitor"
type = "stcp"
serverName = "hidden-service"
sk = "super_secret_key"
bindAddr = "127.0.0.1"
bindPort = 3390
```

这样你的 RDP 服务不会在公网留下任何开放端口，只有知道 `sk` 的设备才能连接。

### UDP 穿透（游戏 / VoIP）

```toml
[[proxies]]
name = "minecraft"
type = "udp"
localIP = "192.168.1.200"
localPort = 25565
remotePort = 25565
```

### P2P 直连（XTCP 模式，零服务端转发）

当客户端之间有对称 NAT 时，FRP 支持 XTCP 模式实现 P2P 直连，流量不经过服务端：

```toml
# 服务端配置
xtcpPunchholeProbe = true

# 内网侧
[[proxies]]
name = "p2p-ssh"
type = "xtcp"
localIP = "127.0.0.1"
localPort = 22
secret = "p2p_secret_key"

# 访问侧
[[visitors]]
name = "p2p-ssh visitor"
type = "xtcp"
serverName = "p2p-ssh"
secret = "p2p_secret_key"
bindAddr = "127.0.0.1"
bindPort = 6000
```

P2P 模式下延迟最低（直连），但需要双方都在线且 NAT 类型允许（一般家用路由器可行，运营商级 NAT 不行）。

---

## 性能调优

### 服务端优化

```toml
# frps.toml 性能参数
maxPoolCount = 100              # 连接池大小
heartbeatTimeout = 90           # 心跳超时（秒）
tlsTrustedCaFile = ""           # 可选：限制仅信任特定 CA
startProtocols = ["tcp", "udp", "http", "https", "stcp", "xtcp"]

# 带宽限制（防止被滥用）
# bandwidthLimit = "10MB"
# bandwidthLimitMode = "server"
```

### 客户端优化

```toml
# frpc.toml
loginFailExit = false           # 登录失败不退出（配合 systemd restart）
runMode = "normal"              # normal / fake / random
tcpMux = true                   # TCP 多路复用，减少连接数
tcpMuxKeepaliveInterval = 60
log.level = "warn"              # 生产环境降低日志级别
```

### Linux 内核参数优化

```bash
# /etc/sysctl.d/99-frp.conf
net.core.somaxconn = 65535
net.ipv4.tcp_max_syn_backlog = 8192
net.ipv4.ip_local_port_range = 1024 65535
net.ipv4.tcp_fin_timeout = 30
net.ipv4.tcp_keepalive_time = 600
net.ipv4.tcp_tw_reuse = 1
fs.file-max = 100000

sudo sysctl -p /etc/sysctl.d/99-frp.conf
```

---

## 与替代方案对比

| 方案 | 成本 | 速度 | 难度 | 隐私性 | 适用场景 |
|------|------|------|------|--------|----------|
| **FRP（自建）** | 仅 VPS 费用 | ⭐⭐⭐⭐⭐ | 中 | ⭐⭐⭐⭐⭐ | 技术用户、多服务 |
| Tailscale | 免费额度内免费 | ⭐⭐⭐⭐ | 低 | ⭐⭐⭐⭐ | 个人设备组网 |
| Cloudflare Tunnel | 免费 | ⭐⭐⭐ | 低 | ⭐⭐⭐ | 网站/API 对外 |
| ngrok | 免费 8KB/s，$8/月起 | ⭐⭐⭐ | 低 | ⭐⭐ | 临时调试 |
| ZeroTier | 免费 50 设备 | ⭐⭐⭐⭐ | 中 | ⭐⭐⭐⭐ | 多节点组网 |
| 付费穿透（向日葵等） | ¥30-200/月 | ⭐⭐ | 低 | ⭐ | 非技术用户 |

---

## 常见问题排查

### 客户端一直 reconnecting

```bash
# 检查 VPS 防火墙是否放行 7000 端口
sudo ufw status

# 检查 frps 日志
sudo journalctl -u frps -f

# 检查客户端网络
curl -v telnet://your-vps-ip:7000
```

### 域名访问返回 404

- 确认 DNS 已解析到 VPS IP：`dig nextcloud.yourdomain.com`
- 确认 frps 中 `vhostHTTPPort` 配置正确
- 确认客户端 proxy 的 `customDomains` 与 DNS 一致

### HTTPS 证书问题

使用 Certbot 时确保域名已解析到 VPS，否则 `--standalone` 模式会失败：

```bash
# 先用 A 记录解析，再申请证书
sudo certbot certonly --nginx -d yourdomain.com
```

### 带宽瓶颈

FRP 默认单连接，高带宽场景下建议：

```toml
# 启用 TCP Mux 复用多个逻辑连接
tcpMux = true
tcpMuxKeepaliveInterval = 60

# 增加连接池
maxPoolCount = 100
```

---

## 安全建议

1. **务必设置 token**——未认证的 frps 任何人都能穿透你的内网
2. **不要暴露 SSH 到公网**——用 STCP 模式替代，或至少改默认端口 + key 认证
3. **定期更新 FRP**——关注 GitHub releases，修复已知漏洞
4. **限制 allowUsers**——STCP 模式下明确指定允许访问的用户
5. **启用 TLS**——frps 与 frpc 之间使用加密连接：

```toml
# frps.toml
tls.force = true
tls.certFile = "/path/to/server.pem"
tls.keyFile = "/path/to/server.key"

# frpc.toml
tls.enable = true
tls.trustedCaFile = "/path/to/ca.pem"
```

---

## 总结

FRP 是自建内网穿透最灵活、最自由的方案。与付费穿透服务相比，你的流量完全走自己的 VPS，不受第三方限速和内容审查。与 Tailscale 相比，FRP 支持更多协议类型（HTTP/HTTPS/UDP/P2P），适合需要暴露特定端口的服务场景。

核心要点回顾：
- **frps** 部署在公网 VPS，**frpc** 部署在内网设备
- 用 **token 认证**保护连接，用 **STCP 模式**隐藏敏感服务
- **XTCP P2P 模式**可实现零中转直连，延迟最低
- **TCP Mux + 内核参数调优**可突破单连接带宽限制
- 配合 **Caddy/Nginx + Certbot** 实现自动化 HTTPS

有了 FRP，你家里的 NAS、树莓派、开发机都能安全地通过域名对外提供服务，无需购买额外穿透服务，无需暴露原始端口，完全掌控自己的网络。
