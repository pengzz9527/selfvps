---
title: "Cloudflare Tunnel 零公网IP内网穿透完全指南：无需端口转发，安全暴露本地服务"
description: "从零搭建 Cloudflare Tunnel（cloudflared），让本地 VPS 服务无需公网IP即可安全暴露到互联网。支持 HTTP/HTTPS、SSH、数据库、内网穿透，比 Ngrok 更安全免费，比 frp 更简单。"
date: 2026-08-17T10:00:00+08:00
lastmod: 2026-08-17T10:00:00+08:00
slug: "cloudflare-tunnel-zero-trust-network"
tags: ["Cloudflare", "Tunnel", "内网穿透", "零信任", "VPS", "自托管", "网络安全", "Docker", "frp替代", "端口转发"]
categories: ["部署教程"]
draft: false
image: /images/posts/cloudflare-tunnel-zero-trust-network/featured.png
aliases: [/zh/post/cloudflare-tunnel-zero-trust-network/]
---

## 为什么需要 Cloudflare Tunnel？

在自托管和 VPS 运维中，我们常常需要把本地服务暴露到互联网：个人博客、NAS、摄像头、Home Assistant、甚至 SSH 远程桌面。传统方案有两种：

1. **端口转发**：在路由器/防火墙开放端口，指向内网 IP。问题：暴露公网 IP、容易被扫描攻击、需要动态 DNS。
2. **Ngrok/frp 等工具**：搭建中转服务器，需要自己维护服务器和端口。

**Cloudflare Tunnel（cloudflared）** 是第三种选择——它通过加密隧道将你的服务连接到 Cloudflare 边缘网络，**完全不需要公网 IP、不需要端口转发、不需要维护中转服务器**。所有流量都经过 Cloudflare 的 DDoS 防护和 WAF 过滤，安全性远超传统方案。

---

## Cloudflare Tunnel 工作原理

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────┐
│  你的服务    │────▶│  cloudflared     │────▶│  Cloudflare │
│  (本地VPS)   │     │  (隧道客户端)     │     │  边缘网络    │
└─────────────┘     └──────────────────┘     └──────┬──────┘
                                                     │
                                                     ▼
                                               ┌─────────────┐
                                               │   互联网用户  │
                                               │  *.yourdomain.com │
                                               └─────────────┘
```

核心优势：
- **出站连接**：cloudflared 主动向 Cloudflare 边缘发起连接， inbound 端口完全封闭
- **零信任架构**：无需开放任何端口，攻击面降至最低
- **免费 HTTPS**：自动签发 TLS 证书，无需 Let's Encrypt
- **DDoS 防护**：所有流量经过 Cloudflare 全球 CDN

---

## 第一步：准备工作

### 1.1 拥有 Cloudflare 账户和域名

访问 [cloudflare.com](https://cloudflare.com) 注册账户，并将域名的 DNS 托管到 Cloudflare（在域名注册商处将 nameserver 改为 Cloudflare 提供的 NS）。

### 1.2 安装 cloudflared

```bash
# Ubuntu/Debian
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb -o cloudflared.deb
sudo dpkg -i cloudflared.deb

# 或一键安装脚本
curl -s https://bin.equinox.io/c/bNyj1mQVY4c/cloudflared-stable-linux-amd64.tgz | sudo tar -xzf - -C /usr/local/bin

# 验证安装
cloudflared --version
```

---

## 第二步：认证与隧道创建

### 2.1 登录 Cloudflare

```bash
cloudflared tunnel login
```

执行后会生成一个认证 URL，在浏览器中打开并选择你的域名授权。授权完成后，凭证文件保存在 `~/.cloudflared/*.json`。

### 2.2 创建隧道

```bash
# 创建命名隧道
cloudflared tunnel create my-tunnel

# 记录 Tunnel ID（后续需要）
# 输出类似：Tunnel credentials saved to /root/.cloudflared/<uuid>.json
# Tunnel ID: abcdef12-3456-7890-abcd-ef1234567890
```

### 2.3 创建 DNS 记录

```bash
# 查看隧道对应的 CNAME 记录
cloudflared tunnel list

# 在 Cloudflare DNS 中添加 CNAME
# 例如，想让 http://app.yourdomain.com 指向隧道：
# Name: app
# Type: CNAME
# Target: abcdef12-3456-7890-abcd-ef1234567890.trycloudflare.com
```

> **提示**：也可以直接使用 `cloudflared tunnel route dns my-tunnel` 命令自动添加 DNS 记录。

---

## 第三步：配置路由

### 3.1 配置文件方式（推荐）

创建配置文件 `~/.cloudflared/config.yml`：

```yaml
tunnel: abcdef12-3456-7890-abcd-ef1234567890
credentials-file: /root/.cloudflared/<uuid>.json

ingress:
  # 规则1：暴露本地 Web 服务
  - hostname: app.yourdomain.com
    service: http://localhost:3000
  
  # 规则2：暴露 SSH（替代传统端口转发）
  - hostname: ssh.yourdomain.com
    service: ssh://localhost:22
  
  # 规则3：暴露数据库管理界面（加访问控制）
  - hostname: db.yourdomain.com
    service: http://localhost:8080
    originRequest:
      noTLSVerify: true
      http2Origin: false
  
  # 默认规则：404
  - service: http_status:404
```

### 3.2 命令行方式（简单场景）

```bash
cloudflared tunnel route ip add 10.0.0.1  # 添加 IP 路由（可选）
cloudflared tunnel route dns add my-tunnel app.yourdomain.com  # 添加 DNS 路由
```

---

## 第四步：启动隧道

### 4.1 前台运行（测试用）

```bash
cloudflared tunnel run my-tunnel
```

观察日志确认隧道状态正常：
```
$ cloudflared tunnel run my-tunnel
INFO  Connection xxx.x.xx.x:xxxxx is authenticated  via token
INFO  Certified tunnel hostname: abcdef.trycloudflare.com
INFO  Listening on https://app.yourdomain.com
```

### 4.2 后台运行（生产用）

#### 方式一：systemd 服务（推荐）

```bash
# 创建 systemd 服务
sudo tee /etc/systemd/system/cloudflared.service > /dev/null <<'EOF'
[Unit]
Description=Cloudflare Tunnel
After=network-online.target

[Service]
Type=notify
ExecStart=/usr/local/bin/cloudflared tunnel run --no-autoupdate my-tunnel
Restart=always
RestartSec=10
Environment=CF_TUNNEL_TOKEN=abcdef12-3456-7890-abcd-ef1234567890

[Install]
WantedBy=multi-user.target
EOF

# 启动服务
sudo systemctl daemon-reload
sudo systemctl enable cloudflared
sudo systemctl start cloudflared

# 查看状态
sudo systemctl status cloudflared
journalctl -u cloudflared -f
```

#### 方式二：Docker 运行

```bash
docker run -d \
  --name cloudflared \
  --restart unless-stopped \
  -v ~/.cloudflared:/home/user/.cloudflared \
  -e TUNNEL_TOKEN=abcdef12-3456-7890-abcd-ef1234567890 \
  cloudflare/cloudflared:latest \
  tunnel --no-autoupdate run my-tunnel
```

---

## 第五步：添加安全增强

### 5.1 启用 Cloudflare Access（零信任访问控制）

在 Cloudflare Dashboard → Zero Trust → Access → Applications 中配置：

- 设置应用规则（如 `*.yourdomain.com`）
- 选择认证方式：邮箱验证、Google OAuth、GitHub OAuth 等
- 可为不同子域设置不同认证策略

```
Dashboard: Zero Trust → Networks → Tunnels
选择你的隧道 → Edit → 开启 "Access" 策略
```

### 5.2 配置 WAF 规则

```
Dashboard → Security → WAF
为 tunnel 域名添加规则：
- 阻止常见扫描器 User-Agent
- 限制特定 IP 段访问管理界面
- 启用 Bot Fight Mode
```

### 5.3 限制 origin _only_ 来自 Tunnel

在 Cloudflare Dashboard → Network → Tunnel 中，启用 **"Only allow traffic from Cloudflare Tunnels"**，这样即使有人知道你的服务器 IP，也无法直接访问服务。

---

## 实战案例

### 案例1：暴露 Home Assistant

```yaml
ingress:
  - hostname: home.yourdomain.com
    service: http://localhost:8123
  - service: http_status:404
```

### 案例2：暴露 Syncthing/WebUI

```yaml
ingress:
  - hostname: sync.yourdomain.com
    service: http://localhost:8384
  - service: http_status:404
```

### 案例3：暴露 PostgreSQL 管理界面（Adminer/phpMyAdmin）

```yaml
ingress:
  - hostname: dbadmin.yourdomain.com
    service: http://localhost:8080
    originRequest:
      noTLSVerify: true
  - service: http_status:404
```

> ⚠️ **安全提醒**：数据库管理界面务必启用 Cloudflare Access 认证，切勿裸暴露！

### 案例4：替代 frp 做多服务分流

```yaml
ingress:
  - hostname: blog.yourdomain.com
    service: http://localhost:4000
  
  - hostname: wiki.yourdomain.com
    service: http://localhost:7777
  
  - hostname: monitor.yourdomain.com
    service: http://localhost:9090
  
  - hostname: ssh.yourdomain.com
    service: ssh://localhost:22
  
  - service: http_status:404
```

---

## Cloudflare Tunnel vs 其他方案对比

| 特性 | Cloudflare Tunnel | frp | Ngrok | Tailscale |
|------|-------------------|-----|-------|-----------|
| 公网IP需求 | **不需要** | 需要中转服务器 | 需要中转服务器 | **不需要** |
| 端口转发 | **不需要** | 需要 | 需要 | **不需要** |
| 免费额度 | **无限** | 自维护 | 有限制 | 64设备 |
| HTTPS | **自动** | 需配置 | 自动 | 自动 |
| DDoS防护 | **有** | 无 | 部分 | 无 |
| 访问控制 | **Zero Trust** | 需自建 | Basic Auth | 需自建 |
| 延迟 | 低（边缘节点） | 取决于中转服务器 | 中 | 低 |
| 自建服务暴露 | ✅ | ✅ | ✅ | ❌（P2P）|

---

## 故障排查

### 问题1：隧道连接失败

```bash
# 检查凭证文件
ls -la ~/.cloudflared/

# 重新登录
cloudflared tunnel login
cloudflared tunnel route dns add my-tunnel app.yourdomain.com

# 测试连接
cloudflared tunnel ingress validate
```

### 问题2：DNS 解析不正确

```bash
# 检查 CNAME 是否正确
dig app.yourdomain.com CNAME

# 应指向 abcdef.trycloudflare.com
# 而非直接指向 IP
```

### 问题3：服务返回 502/503

检查本地服务是否正常运行：
```bash
# 测试本地访问
curl http://localhost:3000

# 查看隧道日志
journalctl -u cloudflared -n 50
```

### 问题4：SSH 连接慢

在 `~/.cloudflared/config.yml` 中为 SSH 规则添加超时配置：
```yaml
ingress:
  - hostname: ssh.yourdomain.com
    service: ssh://localhost:22
    originRequest:
      connectTimeout: 30s
      noHappyEyeballs: true
```

---

## 总结

Cloudflare Tunnel 是目前**最优雅的自托管服务暴露方案**：

- ✅ **零公网IP**：彻底告别端口转发和动态 DNS
- ✅ **免费无限制**：不收费、不限流量
- ✅ **企业级安全**：DDoS 防护 + Zero Trust 访问控制
- ✅ **简单易用**：一条命令即可启动
- ✅ **多协议支持**：HTTP、SSH、TCP、UDP 全覆盖

对于 VPS 自托管用户来说，Cloudflare Tunnel 几乎是必装工具。配合 Cloudflare 的免费 CDN 和 SSL 证书，你的自托管服务可以安全、稳定地运行在任意网络环境下。

立即行动：登录 Cloudflare Dashboard，创建一个 Tunnel，让你的服务安全地上网吧！
