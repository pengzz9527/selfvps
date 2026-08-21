---
title: "用 Tailscale 实现 VPS 内网穿透：零配置远程访问所有服务"
date: 2026-08-21
description: "不需要端口转发、不需要公网 IP、不需要配置反向代理。Tailscale 让你用一条命令安全访问 VPS 上的任何服务——SSH、Web 面板、数据库、Docker 容器，全部通过加密隧道互联。"
tags: ["VPS", "Tailscale", "内网穿透", "远程访问", "零信任", "WireGuard", "组网"]
categories: ["网络工具"]
image: "/images/posts/vps-tailscale-zero-config-remote-access/featured.png"
draft: false
---

## 引言

你是否遇到过这样的场景？

- 在 VPS 上搭了 Nextcloud，回家想用但家里没有公网 IP；
- SSH 连 VPS 需要暴露 22 端口，担心被暴力破解；
- 想访问 VPS 上的 phpMyAdmin，但每次都要配 Nginx 反向代理加域名；
- 多台 VPS 之间需要互通，但运营商不同、节点分散。

传统方案是开端口、配 DDNS、搞反向代理——麻烦且不安全。今天介绍一个更优雅的解决方案：**Tailscale**。

Tailscale 是一个基于 WireGuard 的零配置 VPN 组网工具，安装后所有设备自动组成加密内网，无需公网 IP、无需端口转发、无需暴露服务。一条命令，随时随地安全访问你的 VPS 上所有服务。

## 为什么选择 Tailscale？

| 方案 | 配置难度 | 安全性 | 需要公网 IP | 成本 |
|------|---------|--------|------------|------|
| 端口转发 + DDNS | ⭐⭐⭐⭐⭐ | ⭐⭐ | 必须 | 免费 |
| Nginx 反向代理 + 域名 | ⭐⭐⭐⭐ | ⭐⭐⭐ | 推荐 | 域名费用 |
| Cloudflare Tunnel | ⭐⭐⭐ | ⭐⭐⭐⭐ | 不需要 | 免费 |
| **Tailscale** | **⭐** | **⭐⭐⭐⭐⭐** | **不需要** | **免费（<20 台设备）** |

Tailscale 的核心优势：

1. **零配置**：安装客户端 → OAuth 登录 → 自动组网，30 秒完成；
2. **端到端加密**：所有流量通过 WireGuard 加密，不经过任何中间服务器（除控制平面）；
3. ** NAT 穿透**：自动处理各种复杂网络环境，手机、家里路由器后面都能连；
4. **访问控制**：支持 ACL 规则，精确控制谁可以访问哪些设备；
5. **免费额度**：个人使用最多 20 台设备完全免费。

## 第一步：安装 Tailscale

### 在 VPS 上安装

```bash
# Ubuntu/Debian
curl -fsSL https://tailscale.com/install.sh | sh

# CentOS/RHEL
curl -fsSL https://tailscale.com/install.sh | sh

# 启动服务
sudo tailscale up
```

安装完成后，Tailscale 会自动创建一个 `tailscale0` 网络接口，并分配一个 `100.x.x.x` 格式的 Tailnet IP。

### 在本地设备安装

同样在你的手机、笔记本电脑、家里 NAS 上安装 Tailscale 客户端：

- **Windows/macOS**：下载桌面客户端 [tailscale.com/download](https://tailscale.com/download)
- **Linux**：`curl -fsSL https://tailscale.com/install.sh | sh && sudo tailscale up`
- **Android/iOS**：App Store 或 Google Play 搜索 Tailscale
- **路由器**：支持 OpenWrt、pfSense、UniFi 等

### 登录并认证

```bash
# 在任意设备上执行
sudo tailscale up

# 这会输出一个 URL，复制到浏览器中登录
# 使用 Google/GitHub/Microsoft 账号 OAuth 授权即可
```

登录成功后，你的 VPS 和所有设备就组成了一个加密内网。

## 第二步：验证组网成功

```bash
# 查看本机 Tailnet IP
tailscale ip

# 查看当前组网内的所有设备
tailscale status

# 输出示例：
# 100.64.0.1
# vps-prod        linux    -          100.64.1.1   idle  5min ago
# macbook-pro     darwin   -          100.64.1.2   active 2min ago
# iphone          android  -          100.64.1.3   active 1min ago
# nas-home        linux    -          100.64.1.4   idle  1h ago
```

每个设备都有一个唯一的 `100.x.x.x` IP，同一 Tailnet 内的设备可以互相 ping 通。

```bash
# 从本地访问 VPS
ping 100.64.1.1

# 从 VPS 访问家里 NAS
ping 100.64.1.4
```

## 第三步：通过 Tailnet IP 访问服务

### SSH 访问（最常用）

```bash
# 不再需要暴露 22 端口！直接用 Tailnet IP 连接
ssh user@100.64.1.1

# 配置 SSH 客户端（~/.ssh/config）
Host vps
    HostName 100.64.1.1
    User root
    Port 22
```

**安全优势**：你的 VPS 22 端口对公网完全关闭，只有加入 Tailnet 的设备才能连接。即使被扫描，也找不到开放端口。

### Web 面板访问

```bash
# 在浏览器中直接访问
# http://100.64.1.1:8080  (CasaOS)
# http://100.64.1.1:3000  (Gitea)
# http://100.64.1.1:9000  (MinIO)
# http://100.64.1.1:3001  (Grafana)
```

**关键**：这些服务不需要配置域名、不需要 Nginx 反向代理、不需要 SSL 证书。因为整个 Tailnet 通信都是加密的，直接通过 IP 访问即可。

### Docker 容器访问

如果你的服务运行在 Docker 中，不需要把端口映射到宿主机：

```yaml
# docker-compose.yml - 不需要 ports 映射！
version: '3.8'
services:
  nextcloud:
    image: nextcloud:latest
    # 不映射端口到宿主机
    # ports:
    #   - "8080:80"
    networks:
      - tailscale

networks:
  tailscale:
    external: false
```

Tailscale 的 IP 分配是全局的，无论服务在容器内还是宿主机上，都可以通过 `100.x.x.x` 直接访问。

### 数据库远程访问

```bash
# 从本地连接 VPS 上的 MySQL
mysql -h 100.64.1.1 -u admin -p

# 从本地连接 VPS 上的 Redis
redis-cli -h 100.64.1.1

# 从本地连接 VPS 上的 PostgreSQL
psql -h 100.64.1.1 -U postgres
```

## 第四步：进阶配置

### 配置 SSH 使用 Tailscale（推荐）

为了让 SSH 体验更接近直接连接，可以配置 DNS 名称：

```bash
# 在 VPS 上设置机器名称
sudo tailscale up --hostname=vps-prod

# 之后可以用域名访问
ssh user@vps-prod.tail xxxx.ts.net
```

或者在本地 `~/.ssh/config` 中：

```
Host *.tail.net
    User root
    IdentityFile ~/.ssh/id_ed25519
```

### 使用 MagicDNS（可选）

Tailscale 提供免费的 MagicDNS 功能，让你用机器名代替 IP 地址：

```bash
# 在管理后台开启 MagicDNS
# https://login.tailscale.com/admin/dns

# 或者通过 CLI 配置
sudo tailscale up --accept-dns=true
```

开启后，组网内所有设备可以用短名互访：

```bash
ping vps-prod      # 替代 ping 100.64.1.1
ssh nas-home       # 替代 ssh 100.64.1.4
```

### 访问控制（ACL）

Tailscale 支持精细的访问控制。创建一个 `acl.json` 文件：

```json
{
  "groups": {
    "group:admins": ["admin@example.com"],
    "group:devs": ["dev1@example.com", "dev2@example.com"]
  },
  "users": {
    "tailnet-private-key": "sl-private..."
  },
  "aclTests": [
    { "user": "admin@example.com", "src": ["*"], "dst": ["*: *"], "accept": true }
  ],
  "ssh": [
    {
      "action": "accept",
      "src": ["group:admins"],
      "dst": ["*"],
      "users": ["root", "autogid:1000"]
    },
    {
      "action": "accept",
      "src": ["group:devs"],
      "dst": ["vps-prod"],
      "users": ["*"]
    }
  ],
  "tagOwners": {
    "tag:infra": ["group:admins"]
  },
  "hosts": {
    "vps-prod": "100.64.1.1"
  }
}
```

上传 ACL 规则：

```bash
sudo tailscale up --accept-routes --login-server=https://login.tailscale.com
# 然后通过管理面板上传 acl.json
```

### 子网路由（让其他设备也加入 Tailnet）

如果你想让家里局域网的所有设备都能通过 Tailscale 访问 VPS，可以配置子网路由：

```bash
# 在能访问家里局域网的设备上（如家庭路由器或常开的电脑）
sudo tailscale up --advertise-routes=192.168.1.0/24

# 然后在管理面板批准这个路由
# https://login.tailscale.com/admin/acl
```

配置后，VPS 上的服务可以访问你家里 `192.168.1.x` 网段的任何设备。

## 第五步：与 Nginx 配合使用

虽然 Tailscale 已经能解决大部分访问需求，但如果你仍有公网访问需求（如给外部用户提供 Web 服务），可以结合使用：

```nginx
# /etc/nginx/sites-available/your-site
server {
    listen 443 ssl http2;
    server_name your-domain.com;

    # 公网访问
    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # SSL 证书用 Let's Encrypt
    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;
}

# Tailscale 内部访问 - 用不同域名或 IP
server {
    listen 80;
    server_name 100.64.1.1;

    location / {
        proxy_pass http://127.0.0.1:3000;
    }
}
```

这样公网用户访问域名，内部用户通过 Tailscale IP 访问，互不干扰。

## 安全最佳实践

### 1. 关闭 VPS 的公网 SSH 端口

```bash
# 确认 Tailscale 工作正常后，关闭公网 22 端口
sudo ufw deny 22/tcp
# 或者用 iptables
sudo iptables -I INPUT -p tcp --dport 22 -j DROP
```

### 2. 使用 Tailscale 的派生钥匙（Derp 节点）

Tailscale 默认使用他们的 DERP 中继服务器。如果你介意流量经过第三方：

```bash
# 自建 DERP 服务器
# https://tailscale.com/kb/1118/custom-derp-servers/
sudo tailscale up --derp-region=<your-derp-region-id>
```

### 3. 设备认证与注销

定期检查已连接设备：

```bash
# 查看所有已认证设备
tailscale status --json | jq '.Peers[] | {key: .DNSName, lastSeen: .LastHandshake}'

# 在管理面板远程注销可疑设备
# https://login.tailscale.com/admin/machines
```

### 4. 避免在 Tailscale 上运行敏感管理界面

虽然 Tailscale 加密了流量，但像 phpMyAdmin、Adminer 这类管理工具仍然建议：
- 加上应用层密码保护（如 .htaccess）
- 或者通过 Tailscale 的 SSH 通道隧道访问

```bash
# 本地 SSH 隧道（备用方案）
ssh -L 8888:localhost:80 root@100.64.1.1
# 然后本地访问 http://localhost:8888
```

## 实际应用场景

### 场景一：远程管理多台 VPS

```bash
# ~/.ssh/config
Host vps-*
    User root
    IdentityFile ~/.ssh/id_ed25519

Host vps-prod
    HostName 100.64.1.1

Host vps-dev
    HostName 100.64.1.2

Host vps-backup
    HostName 100.64.1.3
```

一个 `ssh vps-prod` 就能连接，无论你在哪里、用什么网络。

### 场景二：家庭 NAS + VPS 互通

```bash
# 家里 NAS 安装 Tailscale 并启用子网路由
sudo tailscale up --advertise-routes=192.168.0.0/24

# VPS 上可以访问家里所有设备
ping 192.168.0.100   # NAS
ping 192.168.0.50    # 智能电视
ping 192.168.0.10    # 打印机
```

### 场景三：远程开发环境

```bash
# 在 VPS 上跑开发服务器
cd ~/project && python3 -m http.server 8000

# 本地浏览器直接访问
# http://100.64.1.1:8000
# 就像访问本地服务一样流畅
```

### 场景四：替代 TeamViewer/向日葵

对于技术用户，Tailscale 比远程桌面软件更轻量、更安全：

```bash
# SSH 远程桌面
ssh -X user@100.64.1.1 gnome-control-center

# 或使用 noVNC 访问 VPS 上的图形界面
# https://github.com/novnc/noVNC
```

## 常见问题

### Q: Tailscale 免费版的 20 台设备限制够吗？

对个人用户来说通常够用：手机 + 笔记本 + 家庭 NAS + VPS = 4-5 台。如果需要更多，可以：
- 升级到 Business 版（$2/用户/月，无限设备）
- 或者自建控制平面（完全免费，无限制）

### Q: Tailscale 会影响网络速度吗？

Tailscale 使用 WireGuard 加密，性能损耗极小（通常 <5%）。对于 SSH、Web 面板访问等场景，几乎感觉不到延迟差异。只有在传输大量数据时才可能有轻微影响。

### Q: 断网后能连上吗？

Tailscale 有 P2P 直连模式。如果你的 VPS 和本地设备都在同一个 NAT 后面（如同一家庭网络），它们会尝试直连，不经过任何中继服务器，速度最快。

### Q: 可以替代 Cloudflare Tunnel 吗？

取决于需求：
- **内部访问**（你自己用）→ Tailscale 更简单
- **对外提供服务**（用户访问）→ Cloudflare Tunnel 更合适
- **两者结合**→ 最佳实践：Tailscale 用于内部管理，Cloudflare Tunnel 用于对外服务

## 总结

Tailscale 重新定义了"远程访问"的方式：

1. **安装即组网**：不用配置路由、不用开端口、不用买域名；
2. **加密即安全**：所有通信端到端加密，公网扫描也无效；
3. **简单即强大**：一个 `tailscale up` 解决所有远程访问问题。

对于自托管爱好者来说，Tailscale 几乎是必装工具。它让你专注于构建服务，而不是折腾网络配置。

现在就安装试试——30 秒内，你的 VPS 就变成随时随地可访问的安全节点。

---

*附上 Tailscale 官方文档：*
- *安装指南：https://tailscale.com/kb/1017/install*
- *ACL 配置：https://tailscale.com/kb/1018/acls*
- *MagicDNS：https://tailscale.com/kb/1081/magicdns*
