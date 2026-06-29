---
title: "WireGuard 自建 VPN 完全指南：在 VPS 上搭建高速私有网络，替代 Tailscale 与 OpenVPN"
description: "从零开始在 VPS 上部署 WireGuard VPN —— 比 OpenVPN 快 3-5 倍，比 Tailscale 更可控。完整的安装、配置、多设备连接、防火墙规则与故障排除指南，适合所有 Linux 发行版。"
date: 2026-06-29T10:00:00+08:00
lastmod: 2026-06-29T10:00:00+08:00
slug: "wireguard-vps-vpn-guide"
tags: ["WireGuard", "VPN", "Docker", "网络安全", "VPS部署", "自托管", "防火墙", "隧道"]
categories: ["部署教程"]
draft: false
image: /images/posts/wireguard-vps-vpn-guide/featured.png
aliases: [/zh/post/wireguard-vps-vpn-guide/]
---

## 为什么选择 WireGuard？

在自托管和 VPS 运维领域，VPN 是最基础也最重要的工具之一。无论是保护公共 Wi-Fi 上的数据传输、实现跨地域内网互联，还是搭建家庭网络的出口代理，VPN 都是不可或缺的基础设施。

市面上主流的 VPN 方案有 OpenVPN、WireGuard、Tailscale 等。那么 WireGuard 有什么特别之处？

### WireGuard vs OpenVPN vs Tailscale 对比

| 特性 | WireGuard | OpenVPN | Tailscale |
|------|-----------|---------|-----------|
| 协议复杂度 | **极简**（约 4000 行代码） | 复杂（数百万行） | 基于 WireGuard + NAT 穿透 |
| 连接速度 | **极快**（内核态实现） | 较慢（用户态） | 快（依赖中继节点） |
| 资源占用 | **极低**（~2MB 内存） | 较高（~20MB+） | 中等 |
| 配置难度 | **简单**（几行配置） | 复杂（证书管理繁琐） | 极简（零配置） |
| 审计安全性 | **经过独立审计** | 经过审计 | 部分开源 |
| 是否需要公网 IP | 不需要 | 不需要 | 不需要 |
| 成本 | **完全免费** | 完全免费 | 免费层有限制 |
|  NAT 穿透 | 需要手动配置 | 需要端口转发 | **自动** |

WireGuard 的核心优势在于**极简设计**——它不是功能堆砌的产品，而是专注于做一件事：在两台机器之间建立加密隧道。代码量只有 OpenVPN 的 1/1000，经过多次独立安全审计，被证明是安全的。

对于 VPS 用户来说，WireGuard 提供了最佳的**性能/复杂度平衡**：比 Tailscale 更可控（不依赖第三方中继），比 OpenVPN 更快更轻。

## 环境准备

本指南假设你有一台运行以下系统的 VPS：
- **Ubuntu 22.04/24.04 LTS**（推荐）
- **Debian 11/12**
- **CentOS Stream 9** / **Rocky Linux 9**
- **Alpine Linux**

以及一个普通用户（具备 sudo 权限）。

## 方法一：原生安装 WireGuard（推荐）

### 第 1 步：安装 WireGuard

**Ubuntu/Debian：**

```bash
sudo apt update
sudo apt install -y wireguard-tools resolvconf
```

**CentOS/Rocky Linux：**

```bash
# RHEL 9+ 内核已包含 WireGuard 模块
sudo dnf install -y epel-release
sudo dnf install -y wireguard-tools
```

**Alpine Linux：**

```bash
sudo apk add wireguard-tools
```

### 第 2 步：生成密钥对

WireGuard 使用非对称加密，每台设备都需要一对密钥。

```bash
# 生成服务端密钥对
wg genkey | tee /etc/wireguard/privatekey_server | wg pubkey > /etc/wireguard/publickey_server
chmod 600 /etc/wireguard/privatekey_server

# 生成客户端密钥对（以手机为例）
wg genkey | tee /etc/wireguard/privatekey_client | wg pubkey > /etc/wireguard/publickey_client
chmod 600 /etc/wireguard/privatekey_client
```

> **安全提示**：密钥文件权限设为 `600`，确保只有 root 可读。生产环境中建议将私钥存储在安全的位置，并定期轮换。

### 第 3 步：创建服务端配置文件

编辑 `/etc/wireguard/wg0.conf`：

```ini
[Interface]
# 服务端配置
Address = 10.8.0.1/24
ListenPort = 51820
PrivateKey = 服务端私钥（从上面生成）
PostUp = iptables -A FORWARD -i %i -j ACCEPT; iptables -A FORWARD -o %i -j ACCEPT; iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
PostDown = iptables -D FORWARD -i %i -j ACCEPT; iptables -D FORWARD -o %i -j ACCEPT; iptables -t nat -D POSTROUTING -o eth0 -j MASQUERADE
SaveConfig = true

[Peer]
# 第一个客户端（手机）
# 客户端公钥 = wg genkey | wg pubkey
AllowedIPs = 10.8.0.2/32
PublicKey = 客户端1公钥

[Peer]
# 第二个客户端（电脑）
AllowedIPs = 10.8.0.3/32
PublicKey = 客户端2公钥
```

**关键参数说明：**

- `Address`：VPN 网段，服务端地址为 `10.8.0.1`
- `ListenPort`：WireGuard 默认监听 UDP 51820 端口
- `PostUp/PostDown`：自动配置 iptables 规则，允许客户端通过 VPS 上网（NAT 转发）
- `AllowedIPs`：指定该客户端可访问的 IP 范围。`/32` 表示只分配一个 IP
- `SaveConfig = true`：每次停止服务时自动保存当前连接的客户端列表

### 第 4 步：启用 IP 转发

WireGuard 作为网关使用时，需要开启 IP 转发功能：

```bash
# 临时启用
echo 1 | sudo tee /proc/sys/net/ipv4/ip_forward

# 永久启用：编辑 /etc/sysctl.conf
echo "net.ipv4.ip_forward = 1" | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
```

### 第 5 步：启动并启用 WireGuard

```bash
sudo systemctl enable wg-quick@wg0
sudo systemctl start wg-quick@wg0
sudo systemctl status wg-quick@wg0
```

### 第 6 步：配置防火墙

确保 UDP 51820 端口对外可见：

```bash
# UFW（Ubuntu 默认防火墙）
sudo ufw allow 51820/udp
sudo ufw reload

# firewalld（CentOS/RHEL）
sudo firewall-cmd --permanent --add-port=51820/udp
sudo firewall-cmd --reload

# iptables 直接配置
sudo iptables -A INPUT -p udp --dport 51820 -j ACCEPT
sudo iptables-save | sudo tee /etc/iptables/rules.v4
```

### 第 7 步：验证连接

```bash
# 查看活跃连接
sudo wg

# 查看统计数据
sudo wg show wg0 dump

# 测试 VPN 连通性
ping -c 3 10.8.0.1
```

## 方法二：Docker 容器化部署

如果你更喜欢容器化管理，WireGuard 也有官方 Docker 镜像。

### 创建 docker-compose.yml

```yaml
version: '3.8'

services:
  wireguard:
    container_name: wireguard
    image: lscr.io/linuxserver/wireguard:latest
    cap_add:
      - NET_ADMIN
      - SYS_MODULE
    environment:
      - PUID=1000
      - PGID=1000
      - TZ=Asia/Shanghai
      - SERVERURL=your-vps-ip  # 可选：动态 DNS 地址
      - SERVERPORT=51820        # WireGuard 监听端口
      - PEERS=2                 # 客户端数量
      - PEERDNS=auto
      - INTERNAL_SUBNET=10.8.0.0
      - ALLOWEDIPS=0.0.0.0/0    # 客户端流量全部走 VPN（全网代理）
    volumes:
      - ./config:/config
      - /lib/modules:/lib/modules
    ports:
      - 51820:51820/udp
    sysctls:
      - net.ipv4.conf.all.src_valid_mark=1
    restart: unless-stopped
```

### 启动服务

```bash
mkdir -p ./wireguard/config
docker compose up -d
```

LinuxServer 的 WireGuard 镜像会在首次启动时自动生成密钥对和配置文件。客户端配置文件保存在 `./config/peer1/peer1.conf`。

### 查看客户端配置

```bash
cat ./wireguard/config/peer1/peer1.conf
```

输出的配置文件可以直接导入到 WireGuard 客户端中。

## 客户端配置

### Linux 客户端

```bash
sudo apt install -y wireguard-tools

# 将服务端提供的 .conf 文件复制到 /etc/wireguard/
sudo cp server.conf /etc/wireguard/wg0.conf

# 启动连接
sudo wg-quick up wg0

# 验证
wg show
```

### Windows 客户端

1. 从 [WireGuard 官网](https://www.wireguard.com/install/) 下载 Windows 客户端
2. 点击"添加隧道" → "从文件添加隧道"
3. 选择服务端提供的 `.conf` 文件
4. 点击"连接"

### macOS 客户端

1. 从 Mac App Store 安装 **WireGuard**
2. 或使用 Homebrew：`brew install --cask wireguard`
3. 导入 `.conf` 配置文件即可

### Android 客户端

1. 从 [Google Play](https://play.google.com/store/apps/details?id=com.wireguard.android) 或 [F-Droid](https://f-droid.org/packages/com.wireguard.android/) 下载安装
2. 扫描二维码或手动导入配置文件

### iOS/iPadOS 客户端

1. 从 [App Store](https://apps.apple.com/app/wireguard/id1451685025) 下载官方应用
2. 导入配置文件后连接

## 高级配置技巧

### 1. 全网代理（All Traffic via VPN）

默认情况下，客户端只能访问 VPN 网段内的设备。如果你希望所有流量都通过 VPS 代理出去（类似 SOCKS 代理）：

在服务端配置中，修改客户端的 `AllowedIPs`：

```ini
[Peer]
PublicKey = 客户端公钥
AllowedIPs = 0.0.0.0/0   # 所有 IPv4 流量
    ::/0                  # 所有 IPv6 流量（可选）
```

同时确保服务端开启了 IP 转发和 NAT：

```ini
PostUp = iptables -A FORWARD -i wg0 -j ACCEPT; iptables -A FORWARD -o eth0 -j ACCEPT; iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
PostDown = iptables -D FORWARD -i wg0 -j ACCEPT; iptables -D FORWARD -o eth0 -j ACCEPT; iptables -t nat -D POSTROUTING -o eth0 -j MASQUERADE
```

### 2. 路由隔离（Split Tunneling）

如果只想让特定流量走 VPN，而其他流量正常走本地网络：

```ini
[Peer]
PublicKey = 客户端公钥
AllowedIPs = 10.8.0.0/24, 192.168.1.0/24
```

这样客户端只能通过 VPN 访问 `10.8.0.0/24`（VPN 网段）和 `192.168.1.0/24`（内网），其他流量走本地网关。

### 3. 持久化连接与 Keep-Alive

WireGuard 使用 `PersistentKeepalive` 来保持 NAT 后的连接存活：

```ini
[Peer]
PublicKey = 客户端公钥
AllowedIPs = 10.8.0.2/32
PersistentKeepalive = 25  # 每 25 秒发送一次心跳包
```

这对于移动端设备（手机/笔记本）特别有用——当设备从睡眠状态恢复时，能快速重新建立连接。

### 4. 多网卡/VPS 场景

如果你的 VPS 有多块网卡（例如 eth0 公网 + eth1 内网），需要明确指定出站接口：

```ini
PostUp = iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
PostDown = iptables -t nat -D POSTROUTING -o eth0 -j MASQUERADE
```

### 5. 客户端限流（Bandwidth Limiting）

WireGuard 本身不支持速率限制，但可以结合 `wondershaper` 实现：

```bash
sudo apt install -y wondershaper

# 限制 wg0 接口的上行/下行速度（单位：kbps）
sudo wondershaper wg0 10000 50000  # 上行 10Mbps，下行 50Mbps
```

## 安全加固

### 1. 限制客户端访问

不要盲目开放所有流量。在生产环境中，建议只允许客户端访问必要的资源：

```ini
[Peer]
PublicKey = 客户端公钥
AllowedIPs = 10.8.0.2/32  # 仅允许访问 VPN 网段，不开放互联网
```

如果需要互联网访问，配合 iptables 白名单：

```bash
# 只允许访问特定域名/IP
sudo iptables -t nat -A POSTROUTING -o eth0 -s 10.8.0.0/24 -d 8.8.8.8 -j MASQUERADE
sudo iptables -t nat -A POSTROUTING -o eth0 -s 10.8.0.0/24 -j MASQUERADE
```

### 2. 禁用不必要的端口

```bash
# 只开放 WireGuard 必需的 UDP 端口
sudo ufw default deny incoming
sudo ufw allow 22/tcp     # SSH
sudo ufw allow 51820/udp  # WireGuard
sudo ufw enable
```

### 3. 密钥轮换

定期更换密钥可以增强安全性：

```bash
# 生成新密钥对
wg genkey | tee /tmp/new_privatekey | wg pubkey > /tmp/new_publickey

# 更新配置文件中的公钥
# 重启 WireGuard
sudo systemctl restart wg-quick@wg0
```

### 4. 监控连接状态

```bash
# 实时监控连接
watch -n 5 'sudo wg show wg0 dump'

# 记录连接日志
sudo journalctl -u wg-quick@wg0 -f
```

## 常见问题与故障排除

### Q1: 客户端能连接但无法上网

**原因**：IP 转发未启用或 NAT 规则缺失。

**解决**：
```bash
# 检查 IP 转发
cat /proc/sys/net/ipv4/ip_forward
# 应该输出 1

# 检查 NAT 规则
sudo iptables -t nat -L POSTROUTING -v -n

# 手动添加 NAT 规则
sudo iptables -t nat -A POSTROUTING -o eth0 -s 10.8.0.0/24 -j MASQUERADE
```

### Q2: 连接频繁断开

**原因**：NAT 超时或防火墙规则冲突。

**解决**：
```bash
# 在客户端配置中添加 PersistentKeepalive
PersistentKeepalive = 25

# 检查防火墙是否阻断了 UDP 流量
sudo iptables -L INPUT -v -n | grep 51820
```

### Q3: 客户端获取了 IP 但 ping 不通服务端

**原因**：防火墙阻止了 ICMP 或 WireGuard 服务未正常运行。

**解决**：
```bash
# 检查服务状态
sudo systemctl status wg-quick@wg0

# 检查接口是否创建
ip addr show wg0

# 临时关闭防火墙测试
sudo iptables -F INPUT
```

### Q4: 移动端连接后耗电严重

**原因**：`PersistentKeepalive` 设置过低导致频繁唤醒。

**解决**：
```ini
# 将心跳间隔提高到 120 秒或更高
PersistentKeepalive = 120
```

### Q5: 如何查看某个客户端的实时流量？

```bash
# 显示每个 Peer 的发送/接收字节数
sudo wg show wg0 transfer

# 输出示例：
# peer: xxxxxxxx..., allowed ips: 10.8.0.2/32, 
#       transmit: 1.23 GiB, received: 456.78 MiB
```

## 性能调优

### 调整 MTU 值

默认的 MTU 是 1420，但在某些网络环境下可能需要调整：

```bash
# 在 Interface 配置中添加
MTU = 1400  # 降低 MTU 以适应高延迟网络
```

### 调整并发连接数

```bash
# 增加最大并发 Peer 数（默认 4096）
echo "net.core.rmem_max = 134217728" | sudo tee -a /etc/sysctl.conf
echo "net.core.wmem_max = 134217728" | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
```

### 使用 UDP-GSO（Linux 5.16+）

较新的内核支持 UDP Generic Segmentation Offload，可以显著提升吞吐量：

```bash
# 检查内核是否支持
grep -i gso /sys/module/wireguard/parameters/features
```

## 总结

WireGuard 是目前最优秀、最轻量的 VPN 解决方案之一。它的极简设计带来了卓越的性能和安全性，而配置复杂度远低于 OpenVPN。

**核心要点回顾：**

1. **安装简单**：一条命令即可安装，`wg genkey` 生成密钥
2. **配置简洁**：一个 `.conf` 文件搞定服务端和客户端
3. **性能出众**：内核态实现，延迟低、吞吐高
4. **安全可靠**：经过多次独立审计，加密算法成熟
5. **跨平台支持**：Linux、Windows、macOS、iOS、Android 全覆盖

对于 VPS 用户来说，WireGuard 是最值得投资的自托管项目之一——它不仅能保护你的网络通信，还能作为跨地域组网、远程办公、家庭网络出口的基础设施。

**下一步行动：**
- [ ] 在你的 VPS 上安装 WireGuard
- [ ] 生成密钥对并配置服务端
- [ ] 在各设备上导入客户端配置
- [ ] 测试连接速度和稳定性
- [ ] 根据需求调整安全策略和流量路由

---

*享受自由、安全、高速的网络连接！🔐*
