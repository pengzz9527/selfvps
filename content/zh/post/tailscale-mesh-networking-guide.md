---
title: "Tailscale 组网指南：在 VPS 间建立安全内网穿透与远程访问"
description: "从零开始使用 Tailscale 构建跨地域 VPS 内网穿透网络，实现安全的远程访问、服务暴露和节点互联，无需公网 IP 或端口映射"
date: 2026-06-16T10:00:00+08:00
lastmod: 2026-06-16T10:00:00+08:00
slug: "tailscale-mesh-networking-guide"
tags: ["Tailscale", "内网穿透", "VPS组网", "零信任网络", "远程访问", "自托管", "网络安全"]
categories: ["网络架构"]
draft: false
aliases: [/zh/post/tailscale-mesh-networking-guide/]
image: /images/posts/tailscale-mesh-networking-guide/featured.png
---

## 为什么需要 Tailscale？

在自托管领域，我们常常面临这样一个问题：**我的服务跑在 VPS 上，但我想从家里或其他地方安全地访问它**。传统方案包括：

- **端口映射（Port Forwarding）**：需要公网 IP，暴露风险大
- **SSH 隧道**：配置繁琐，不适合长期运行多服务
- **Cloudflare Tunnel**：适合 Web 服务，但对非 HTTP 协议支持有限
- **OpenVPN/WireGuard**：需要自行维护基础设施

[Tailscale](https://tailscale.com/) 是一个基于 [WireGuard](https://www.wireguard.com/) 协议的零信任网络解决方案，它通过 **DERP 中继服务器** 和 **NAT 穿透** 技术，让任意两台安装了 Tailscale 的设备直接组成一个加密的虚拟局域网（LAN）。你只需要一个账号登录，所有设备就会自动发现彼此，无需配置复杂的网络规则。

### Tailscale 的核心优势

| 特性 | Tailscale | 传统 VPN | Cloudflare Tunnel |
|------|-----------|----------|-------------------|
| 配置复杂度 | ⭐ 极简 | ⭐⭐⭐ 复杂 | ⭐⭐ 中等 |
| 延迟 | 低（直连时） | 中 | 中 |
| 支持协议 | 任意 TCP/UDP | 任意 TCP/UDP | 仅 HTTP/HTTPS |
| NAT 穿透 | 自动 | 需手动 | 不适用 |
| 身份认证 | Tailnet 身份体系 | 证书/密码 | 域名验证 |
| 成本 | 免费（最多 100 设备） | 自建成本高 | 免费 |

- 🔒 **端到端加密**：所有流量通过 WireGuard 加密，零知识架构
- 🌐 **自动 NAT 穿透**：无需公网 IP，支持几乎所有网络环境
- 🔍 **服务发现**：自动发现同一 Tailnet 中的设备和服务
- 👥 **ACL 控制**：细粒度的访问权限管理
- 🖥️ **子网路由**：将本地 LAN 上的设备暴露给整个 Tailnet

## 环境准备

假设我们有以下场景：

- **VPS A**：阿里云香港（运行 Home Assistant）
- **VPS B**：AWS 新加坡（运行 Nextcloud）
- **本地电脑**：家中 macOS（需要访问上述两个服务）

目标：让这三台设备组成一个安全的私有网络，互访无需暴露公网端口。

## 第一步：安装 Tailscale

### Linux (Debian/Ubuntu)

```bash
# 添加 Tailscale 官方源
curl -fsSL https://tailscale.com/install.sh | sh

# 启动 Tailscale 服务
sudo systemctl enable --now tailscaled

# 登录你的 Tailnet
sudo tailscale up
```

登录后会输出一个类似 `https://login.tailscale.com/a/xxxxx` 的链接，用浏览器打开并完成 OAuth 认证（支持 Google、Microsoft、GitHub 等账号）。

### Docker 容器

如果你已经在用 Docker，可以直接挂载 Tailscale 容器：

```yaml
version: '3'
services:
  tailscale:
    container_name: tailscale
    image: tailscale/tailscale:latest
    restart: unless-stopped
    volumes:
      - ./tailscale:/var/lib/tailscale
      - /dev/net/tun:/dev/net/tun
    cap_add:
      - NET_ADMIN
      - NET_RAW
    command: "start --advertise-tags=tag:home"
```

然后在其他 Docker 服务中引用这个网络：

```yaml
services:
  homeassistant:
    container_name: homeassistant
    image: ghcr.io/home-assistant/home-assistant:stable
    restart: unless-stopped
    network_mode: service:tailscale
    volumes:
      - ./homeassistant:/config
```

### macOS / Windows

从 [tailscale.com/download](https://tailscale.com/download) 下载安装包，登录后自动配置。

## 第二步：验证连接

安装完成后，检查状态：

```bash
# 查看当前 Tailnet 状态
tailscale status

# 查看自己的 IP 地址
tailscale ip

# 测试连通性
tailscale ping <另一台设备的 IP 或 hostname>
```

每台设备会获得一个 `100.x.x.x` 开头的 Tailnet IP，以及一个可在同网络内使用的 DNS 名称（如 `yourname.tail1234.ts.net`）。

## 第三步：配置 ACL（访问控制）

Tailscale 的 ACL 系统允许你精细控制哪些设备可以互相通信。创建一个 `acl.json` 文件：

```json
{
  "users": {
    "alice@example.com": "alice",
    "bob@example.com": "bob"
  },
  "groups": {
    "group:admin": ["alice@example.com"],
    "group:server": ["alice@*.ts.net", "bob@*.ts.net"]
  },
  "hosts": {
    "vps-a-homeassistant": "100.1.1.1",
    "vps-b-nextcloud": "100.1.1.2",
    "macbook-pro": "100.1.1.3"
  },
  "aclTests": [],
  "acls": [
    {
      "action": "accept",
      "src": ["group:admin"],
      "dst": ["*:"]
    },
    {
      "action": "accept",
      "src": ["group:server"],
      "dst": ["vps-a-homeassistant:8123"]
    },
    {
      "action": "accept",
      "src": ["group:server"],
      "dst": ["vps-b-nextcloud:80"]
    },
    {
      "action": "accept",
      "src": ["macbook-pro"],
      "dst": ["vps-a-homeassistant:8123", "vps-b-nextcloud:80"]
    },
    {
      "action": "accept",
      "src": ["alice@example.com"],
      "dst": ["*:22"]
    },
    {
      "action": "accept",
      "src": ["bob@example.com"],
      "dst": ["*:22"]
    }
  ],
  "ssh": [
    {
      "action": "accept",
      "src": ["*"],
      "dst": ["*"],
      "users": ["root", "autogroup-insert"]
    }
  ],
  "cat": [],
  "disableUPnP": false,
  "exitDNS": {
    "DNSResolvers": {
      "local": "https://dns.google/dns-query",
      "global": "https://dns.google/dns-query"
    }
  }
}
```

将 ACL 文件上传到 Tailnet 控制台：进入 [Tailnet Admin Console](https://login.tailscale.com/admin/acl) → 点击 "Policy editor" → 粘贴 JSON 并保存。

### ACL 规则解读

- **`acls`**：定义哪些用户可以访问哪些端口的服务
- **`ssh`**：控制 Tailnet 内的 SSH 访问权限
- **`src`**：源（用户、组、主机）
- **`dst`**：目标（主机:端口，`*:*` 表示全部）

对于个人用户，最简单的 ACL 就是允许所有人互通：

```json
{
  "acls": [
    { "action": "accept", "src": ["*"], "dst": ["*:*"] }
  ]
}
```

## 第四步：暴露本地服务

### 场景 1：让 Tailnet 访问本地 LAN 设备（子网路由）

假设你家里有一台 NAS（IP: `192.168.1.100`），你想让所有 Tailnet 上的设备都能访问它：

```bash
# 在家庭路由器或网关上安装 Tailscale
sudo tailscale up --advertise-routes=192.168.1.0/24

# 在 Tailnet 控制台开启子网路由权限
# 进入 Admin Console → Nodes → 点击你的设备 → Subnets → 开启 "Advertise routes"
```

这样，`100.x.x.x` 的 Tailnet 设备就可以通过子网路由访问 `192.168.1.x` 的所有设备了。

### 场景 2：从 Tailnet 访问 VPS 上的服务

这一步最简单——既然 VPS 已经加入 Tailnet，它的所有端口对 Tailnet 都是可达的。直接访问 `http://100.x.x.x:端口` 即可。

例如：
- Home Assistant：`http://100.1.1.1:8123`
- Nextcloud：`http://100.1.1.2:80`
- 任意 SSH：`ssh user@100.1.1.1`

## 第五步：进阶配置

### 5.1 启用 Exit Node（出口节点）

如果你想让某台 VPS 作为整个 Tailnet 的出口，所有流量都经过它：

```bash
# 在 VPS 上允许它作为出口节点
sudo tailscale up --advertise-exit-node

# 在需要使用的设备上连接到该出口
sudo tailscale up --exit-node=<exit-node-ip>
```

配合 [AdGuard Home](https://github.com/AdguardTeam/AdGuardHome) 或 Pi-hole，你可以实现 **全网 DNS 过滤**，所有 Tailnet 设备的流量都经过家庭广告过滤器。

### 5.2 配置 MagicDNS

MagicDNS 让你可以用主机名代替 IP 地址访问设备：

```bash
# 在每台设备上启用
sudo tailscale up --accept-dns=true

# 在 Admin Console 中配置 DNS 搜索域
# Admin Console → Settings → DNS → 启用 MagicDNS
```

启用后，你就可以用 `ping vps-a-homeassistant.tailnet-name.ts.net` 来替代 `ping 100.1.1.1`。

### 5.3 使用 Tags 进行更灵活的 ACL

Tags 是比 ACL 更简单的访问控制方式。给设备打标签：

```bash
# 给 VPS 打上服务标签
sudo tailscale up --advertise-tags=tag:service,tag:home,tag:media

# ACL 中引用 tags
{
  "acls": [
    { "action": "accept", "src": ["tag:home"], "dst": ["tag:service:*"] }
  ]
}
```

### 5.4 多尾网（Multiple Tailnets）

如果你有多个团队或项目需要隔离的网络，可以创建多个 Tailnet。Tailscale 支持通过 [Tailnet Peering](https://tailscale.com/kb/1331/magicsock-peering) 在不同 Tailnet 之间建立安全连接。

## 第六步：安全最佳实践

### 6.1 启用设备审批

在 Tailnet 设置中开启 **Key Expiry** 和设备审批：

1. 进入 Admin Console → Settings → Access controls
2. 设置设备密钥过期时间（建议 90 天）
3. 启用 "Require device approval"

### 6.2 使用 Southern Cross 节点降低延迟

如果你的设备分布在全球，可以在 Admin Console 中选择 DERP 中继区域，优先使用离你最近的节点。

### 6.3 定期审计 ACL

```bash
# 导出当前 ACL 配置
tailscale debug export-acl

# 检查设备列表
tailscale status --json | jq '.Nodes[] | {Name, PrimaryIP, OS, LastSeen}'
```

### 6.4 限制 SSH 访问

虽然 Tailscale 提供了加密通道，但仍建议：

- 使用密钥认证而非密码
- 在 ACL 中限制 SSH 访问来源
- 启用 Tailscale 内置的 SSH 功能（基于 Tailnet 身份）

```bash
# 启用 Tailscale SSH
sudo tailscale up --ssh
```

## 实际应用场景

### 场景一：跨地域 VPS 管理

你有 5 台不同服务商的 VPS（阿里云、AWS、DigitalOcean、Vultr、Hetzner），想统一管理：

```bash
# 在所有 VPS 上安装 Tailscale 并登录
# 然后用一台跳板机 SSH 到所有节点
ssh root@vps-aws.ts.net
ssh root@vps-do.ts.net
ssh root@vps-hetzner.ts.net
```

### 场景二：自托管服务矩阵

| 服务 | 部署位置 | Tailscale 访问地址 |
|------|----------|-------------------|
| Home Assistant | 家庭 NAS | `http://100.1.1.5:8123` |
| Nextcloud | AWS | `http://100.2.1.3:80` |
| Plex | 家庭 NAS | `http://100.1.1.5:32400` |
| AdGuard Home | 家庭路由器 | `http://100.1.1.1:3000` |
| Gitea | 阿里云 | `http://100.3.1.2:3000` |
| Uptime Kuma | DigitalOcean | `http://100.4.1.2:3000` |

所有服务都不需要公网 IP、不需要域名解析、不需要 SSL 证书配置——Tailscale 自动处理一切。

### 场景三：远程办公安全接入

将公司内网的服务（如 Jenkins、GitLab、内部 Wiki）通过 Tailscale 暴露给远程员工，替代传统的 OpenVPN 方案，配置时间从几小时缩短到几分钟。

## 常见问题排查

### 问题 1：设备无法互相 ping 通

```bash
# 检查 Tailscale 服务状态
sudo systemctl status tailscaled

# 查看详细日志
sudo journalctl -u tailscaled -f

# 检查防火墙是否阻止了 UDP 41641
sudo ufw allow 41641/udp
sudo iptables -L -n | grep 41641
```

### 问题 2：NAT 穿透失败，只能走 DERP 中继

DERP 中继会增加延迟。如果直连失败：

```bash
# 查看连接类型（direct 表示直连，derp 表示中继）
tailscale status --json | jq '.Peers[].LastHandshake'

# 强制打洞
sudo tailscale up --sneak-preview

# 检查 UPnP 是否可用
tailscale up --advertise-endpoints
```

### 问题 3：ACL 不生效

```bash
# 查看当前 ACL 配置
tailscale debug export-acl

# 重新加载 ACL
sudo systemctl reload tailscaled

# 检查设备是否被正确授权
tailscale cert <hostname>.tailnet-name.ts.net
```

## 总结

Tailscale 是目前最优雅的自托管网络解决方案之一。它让你：

1. **无需公网 IP** 即可安全访问任何设备
2. **无需端口映射** 即可暴露任意服务
3. **一键组网**，所有设备自动发现
4. **企业级安全**，端到端加密 + 细粒度 ACL
5. **免费可用**，100 台设备以内完全免费

对于自托管爱好者来说，Tailscale 几乎应该成为每个 VPS 的标准配置。搭配 Docker、Home Assistant、Nextcloud 等自托管工具，你可以轻松构建一个跨地域的安全服务矩阵，而无需担心网络安全和配置复杂度。

---

**下一步**：试试在你的第一台 VPS 上安装 Tailscale，体验一下"零配置组网"的力量。🚀
