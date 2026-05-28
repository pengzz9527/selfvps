---
title: "Tailscale + VPS：构建零信任自托管网络"
description: "手把手教程：用 Tailscale 在 VPS 上搭建零信任安全网络，安全访问自托管服务，无需公网 IP、无需端口转发、无需配置防火墙。"
date: 2026-05-28T10:00:00+08:00
slug: "tailscale-vps-zero-trust-network"
image: /images/posts/tailscale-vps-zero-trust-network/featured.png
tags: ["Tailscale", "VPN", "零信任", "WireGuard", "网络", "VPS部署", "自托管", "安全"]
categories: ["网络运维"]
aliases: [/zh/post/tailscale-vps-zero-trust-network/]
draft: false
---

## 为什么需要 Tailscale？

当你在 VPS 上部署了越来越多自托管服务后，一个棘手的问题随之而来：**如何安全地访问这些服务？**

传统做法是开放端口、配置防火墙、使用密码认证，但这带来了巨大的攻击面。每次新增服务都要操心 SSL 证书、反向代理、身份认证——繁琐且容易出错。

[Tailscale](https://tailscale.com) 提供了一种全新的思路：基于 **WireGuard** 的零信任网络。它让你在任何设备之间建立安全的加密隧道，无需公网 IP、无需端口转发、无需复杂的防火墙规则。

### Tailscale 的核心优势

- 🔒 **零信任架构**：基于设备身份和用户身份认证，而非 IP 地址
- 🚀 **基于 WireGuard**：内核级加密，性能损耗极小
- 🌐 **无需公网 IP**：通过 DERP 中继或 NAT 穿透直连
- 📱 **全平台支持**：Linux、macOS、Windows、iOS、Android 全平台覆盖
- 🎯 **Tailscale Funnel**：可将内网服务直接暴露到公网（可选）
- 🏢 **SSO 集成**：支持 Google、GitHub、Microsoft 等单点登录
- 💰 **免费套餐慷慨**：个人用户最多 100 台设备，完全免费

---

## 架构概览

典型的 Tailscale + VPS 网络拓扑如下：

```
┌─────────────────────────────────────────────────────────┐
│                      Tailscale 网络                        │
│                    (100.x.x.x/10)                        │
│                                                          │
│   ┌──────────┐    ┌──────────┐    ┌──────────┐          │
│   │ VPS 节点  │    │ 笔记本   │    │ 手机     │          │
│   │ (子网路由) │    │ (直接连接) │    │ (4G/5G)  │          │
│   └────┬─────┘    └──────────┘    └──────────┘          │
│        │                                                  │
│   ┌────┴─────┐                                           │
│   │ Docker  │                                           │
│   │ 容器网络 │                                           │
│   │ 172.17.x │                                           │
│   └──────────┘                                           │
└─────────────────────────────────────────────────────────┘
```

核心思路：VPS 作为 **子网路由节点（Subnet Router）**，将 VPS 上的 Docker 容器网络暴露给 Tailscale 网络中的其他设备。你可以在笔记本上直接通过容器内网 IP 访问服务，全程加密。

---

## 第一步：安装 Tailscale

### 在 VPS 上安装

```bash
# 一键安装脚本（支持所有主流 Linux 发行版）
curl -fsSL https://tailscale.com/install.sh | sh

# 启动并设置开机自启
sudo systemctl enable --now tailscaled

# 登录你的 Tailscale 账号
sudo tailscale up
```

执行 `tailscale up` 后，终端会输出一个登录链接。在浏览器中打开链接，用你的 Google/GitHub/Microsoft 账号登录即可。

### 在本地电脑上安装

- **macOS**：`brew install --cask tailscale` 或从官网下载
- **Windows**：从 [tailscale.com/download](https://tailscale.com/download) 下载安装包
- **Linux**：同上的一键安装脚本
- **iOS/Android**：App Store / Google Play 搜索 Tailscale

所有设备登录同一个 Tailscale 账号后，它们会自动组成一个安全的虚拟网络。

### 验证连接

```bash
# 查看 Tailscale 网络中的设备
tailscale status

# 输出示例：
# 100.x.x.x    your-vps-name        your-user@ linux   -
# 100.y.y.y    your-laptop          your-user@ macOS   -
# 100.z.z.z    your-phone           your-user@ iOS    -

# 测试 ping
ping 100.x.x.x
```

如果所有设备都能 ping 通，说明 Tailscale 网络已经建立成功。

---

## 第二步：配置子网路由

这是关键步骤——让 VPS 充当路由器，把 VPS 上的 Docker 容器网络暴露给 Tailscale 网络。

### 启用 IP 转发

```bash
# 开启内核 IP 转发
echo 'net.ipv4.ip_forward = 1' | sudo tee -a /etc/sysctl.conf
echo 'net.ipv6.conf.all.forwarding = 1' | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
```

### 重新登录并启用子网路由

```bash
# 假设你的 Docker 内网网段是 172.17.0.0/16
# 退出当前 Tailscale 会话
sudo tailscale down

# 重新登录，启用子网路由和接受路由
sudo tailscale up --advertise-routes=172.17.0.0/16 --accept-routes

# 如果有多个网段，用逗号分隔
# sudo tailscale up --advertise-routes=172.17.0.0/16,10.0.0.0/24 --accept-routes
```

### 在 Tailscale 管理面板开启路由

1. 打开 [https://login.tailscale.com/admin/machines](https://login.tailscale.com/admin/machines)
2. 找到你的 VPS 节点
3. 点击 **"..." → "Edit route settings"**
4. 勾选你通告的子网网段
5. 点击 **"Save"**

> 在管理面板的 Machines 页面，点击 VPS 节点旁的 "..." 菜单 → "Edit route settings" → 勾选子网 → "Save"

> ⚠️ **重要**：管理面板中必须手动勾选批准子网路由，否则客户端不会接受这些路由。

---

## 第三步：配置 Docker 网络

为了让 Tailscale 能路由到 Docker 容器，我们最好使用固定的 Docker 网段。

### 创建自定义 Docker 网络

```bash
# 创建一个固定子网的 Docker 网络
docker network create --subnet=10.0.100.0/24 selfhosted-net
```

### 启动服务时指定网络

```bash
# 示例：将 Nginx 连接到自定义网络
docker run -d --name my-app \
  --network selfhosted-net \
  --ip 10.0.100.10 \
  nginx:alpine
```

或者使用 Docker Compose：

```yaml
# docker-compose.yml
version: '3.8'

networks:
  selfhosted-net:
    driver: bridge
    ipam:
      config:
        - subnet: 10.0.100.0/24

services:
  n8n:
    image: n8nio/n8n
    networks:
      selfhosted-net:
        ipv4_address: 10.0.100.10
    ports:
      - "5678:5678"

  postgres:
    image: postgres:15
    networks:
      selfhosted-net:
        ipv4_address: 10.0.100.20
    volumes:
      - pgdata:/var/lib/postgresql/data
```

### 更新 Tailscale 路由

如果之前只通告了 `172.17.0.0/16`，现在需要加上自定义网段：

```bash
sudo tailscale up \
  --advertise-routes=10.0.100.0/24,172.17.0.0/16 \
  --accept-routes
```

然后在管理面板中批准新的子网路由。

---

## 第四步：安全访问你的服务

现在，你可以在任何 Tailscale 网络中的设备上直接通过容器内网 IP 访问服务了。

### 直接访问

```bash
# 在你的笔记本上
curl http://10.0.100.10:5678  # 直接访问 N8N 服务
```

### 使用 MagicDNS（推荐）

Tailscale 提供 MagicDNS，让你可以用主机名代替 IP 地址。

```bash
# 启用 MagicDNS（在管理面板中开启）
# 设置主机的 Tailscale 域名
sudo tailscale up --advertise-routes=10.0.100.0/24 --accept-routes

# 现在你可以用主机名访问了
curl http://your-vps-hostname:5678
```

### 配置 SSH 通过 Tailscale

```bash
# 在 VPS 上配置 SSH 只监听 Tailscale 接口
# 编辑 /etc/ssh/sshd_config
# ListenAddress 0.0.0.0 改成 ListenAddress 100.x.x.x（你的 Tailscale IP）

# 或者用防火墙只允许 Tailscale 子网
sudo ufw allow from 100.64.0.0/10 to any port 22
sudo ufw deny 22
```

### 浏览器中访问

直接在浏览器地址栏输入：
```
http://10.0.100.10:5678
```

就可以看到你在 VPS 上运行的服务了，所有流量都经过 WireGuard 加密传输，不经过任何公网暴露。

---

## 第五步：高级配置

### 5.1 使用 Tailscale Funnel 安全暴露服务

如果你需要让不在 Tailscale 网络中的用户访问某个服务（比如给客户展示 Demo），可以使用 **Tailscale Funnel**。

```bash
# 安装 serve（Tailscale 的 HTTP 代理工具）
sudo tailscale serve --bg --https=443 serve 10.0.100.10:80

# 启用 Funnel
sudo tailscale funnel --bg 443 on
```

这会通过 Tailscale 的 Funnel 服务将你的内网服务暴露到公网，但连接仍然经过 Tailscale 的加密基础设施。

### 5.2 ACL 访问控制

Tailscale 提供细粒度的访问控制列表（ACL）：

```json
// Tailscale ACL 配置示例
{
  "acls": [
    // 允许所有设备访问 VPS 上的 5678 端口（N8N）
    {"action": "accept", "src": ["*"], "dst": ["your-vps:5678"]},
    // 只允许特定用户访问数据库
    {"action": "accept", "src": ["user1@", "user2@"], "dst": ["your-vps:5432"]},
    // 拒绝所有其他入站连接
    {"action": "deny", "src": ["*"], "dst": ["*:*"]}
  ]
}
```

在 [https://login.tailscale.com/admin/acls](https://login.tailscale.com/admin/acls) 编辑 ACL。

### 5.3 使用 Exit Node 做安全出口

将 VPS 配置为 Exit Node，所有流量都通过 VPS 出口：

```bash
# VPS 端
sudo tailscale up --advertise-exit-node
```

```bash
# 客户端端（笔记本）
sudo tailscale up --exit-node=your-vps-tailscale-ip
```

这对于在公共 Wi-Fi 上保护你的网络流量非常有用。

### 5.4 多 VPS 互联

如果有多个 VPS（比如新加坡、美国、欧洲），它们之间可以建立直接的 Tailscale 连接：

```bash
# 每个 VPS 都安装 Tailscale 并加入同一网络
# 然后互相通告子网路由

# VPS 新加坡
sudo tailscale up --advertise-routes=10.0.100.0/24 --accept-routes

# VPS 美国
sudo tailscale up --advertise-routes=10.0.200.0/24 --accept-routes

# 然后新加坡的容器 10.0.100.10 可以直接访问美国的 10.0.200.20
```

---

## 性能对比

| 方案 | 延迟 | 吞吐量 | 安全性 | 配置复杂度 |
|------|------|--------|--------|-----------|
| 公网直接暴露 | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐⭐⭐ |
| 传统 VPN (WireGuard) | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ |
| **Tailscale** | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| Cloudflare Tunnel | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| ngrok | ⭐⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ |

Tailscale 在安全性上无可匹敌，配置也最简单。由于基于 WireGuard，性能和传统 WireGuard VPN 几乎没有差别。

---

## 常见问题

### Q: Tailscale 免费版有什么限制？
A: 免费版支持最多 **100 台设备**、**3 个用户**。对于个人和小团队使用完全够用。

### Q: 如果两台设备都处于严格的 NAT 后面，无法直连怎么办？
A: Tailscale 会自动使用 DERP 中继服务器进行流量中继。中继服务器由 Tailscale 官方提供，支持端到端加密（Tailscale 也无法解密你的流量）。

### Q: 可以自建 DERP 中继服务器吗？
A: 当然可以！你可以在自己的 VPS 上部署私有 DERP 中继服务器，然后配置 Tailscale 使用它。这在某些网络受限的环境中非常有用。

### Q: Tailscale 与普通 WireGuard 有什么区别？
A: Tailscale 基于 WireGuard，但增加了自动 NAT 穿透、设备管理、ACL、MagicDNS 等功能。你可以把 Tailscale 理解为 "WireGuard + 控制平面"。

### Q: 我的 Docker 容器没有固定 IP，还能用吗？
A: 可以。你可以使用容器名称或 Docker 网络内的 DNS 解析，但子网路由需要固定的 CIDR 网段才能工作。建议始终为 Docker 网络指定固定子网。

---

## 总结

Tailscale 彻底改变了我们访问自托管服务的方式。通过将 VPS 配置为子网路由节点，你可以：

1. ✅ **零端口暴露**——VPS 上无需开放任何端口
2. ✅ **全链路加密**——所有流量经过 WireGuard 加密
3. ✅ **零配置访问**——在任何设备上无缝访问 VPS 服务
4. ✅ **细粒度控制**——通过 ACL 精确控制访问权限
5. ✅ **跨地域互联**——轻松连接全球各地的 VPS 和服务

最重要的是，Tailscale 的免费套餐对于个人和小团队来说已经非常慷慨。今天就试试看，让你的自托管服务更安全、更易管理。

### 快速开始命令速查

```bash
# 安装
curl -fsSL https://tailscale.com/install.sh | sh

# 启动
sudo tailscale up

# 配置子网路由
sudo tailscale up --advertise-routes=10.0.100.0/24 --accept-routes

# 查看状态
tailscale status

# 查看 IP
tailscale ip -4
```

---

*觉得这篇文章有用？欢迎分享给更多自托管爱好者！*
