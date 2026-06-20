---
title: "自建 Headscale 替代 Tailscale 控制平面：在 VPS 上实现完全掌控的零信任网络"
description: "从零开始部署 Headscale——一个开源的 Tailscale 控制平面替代品。支持 Docker 一键部署、自定义 DNS、ACL 访问控制、节点管理，让你的内网穿透完全自主可控。"
date: 2026-06-20T10:00:00+08:00
lastmod: 2026-06-20T10:00:00+08:00
slug: "headscale-selfhosted-tailscale"
tags: ["Headscale", "Tailscale", "零信任网络", "VPS部署", "Docker", "内网穿透", "网络安全", "自托管"]
categories: ["网络安全"]
draft: false
image: "/images/posts/headscale-selfhosted-tailscale/featured.png"
aliases: [/zh/post/headscale-selfhosted-tailscale/]
---

## 为什么需要自建 Headscale？

[Tailscale](https://tailscale.com/) 是一款革命性的零信任组网工具，通过 WireGuard 协议将分散在全球的设备连接成虚拟局域网。但它的默认控制平面由 Tailscale Inc. 运营，这意味着：

- 你的节点列表、DNS 配置、ACL 规则都存储在 Tailscale 的服务器上
- 公司合规要求可能不允许将网络拓扑暴露给第三方
- 你无法完全控制身份认证和密钥管理

[Headscale](https://github.com/juanfont/headscale) 是一个用 Go 编写的**开源 Tailscale 控制平面替代品**，让你在自己的 VPS 上完全掌控整个 Zero Trust 网络架构。

## Headscale 核心功能对比

| 特性 | Tailscale 官方 | Headscale 自建 |
|------|---------------|----------------|
| 控制平面 | Tailscale Inc. 托管 | 你自己的 VPS |
| 成本 | 免费（基础功能） | 完全免费 |
| 数据主权 | 数据经 Tailscale 服务器 | 完全本地化 |
| ACL 控制 | Web UI 管理 | YAML 配置文件 |
| DNS 服务 | 内置 MagicDNS | 内置 DNS 解析 |
| 多租户 | 团队/企业版收费 | 开源免费 |
| 审计日志 | 企业版功能 | 自带完整日志 |

## 环境准备

### 系统要求

- Ubuntu 22.04/24.04 或 Debian 12+
- 至少 1 CPU 核心、512MB 内存
- Docker 和 Docker Compose

### 安装 Docker

```bash
curl -fsSL https://get.docker.com | sh
systemctl enable --now docker
```

## 部署 Headscale

### 第一步：创建项目目录结构

```bash
mkdir -p /opt/headscale/{config,data}
cd /opt/headscale
```

### 第二步：生成预共享密钥

```bash
headscale preauth-key --reusable --expiration 720h
```

> 💡 这个密钥用于在客户端注册节点时自动授权，有效期可自定义。

### 第三步：创建配置文件 `/opt/headscale/config/config.yaml`

```yaml
---
# Headscale 监听地址和端口
listen_addr: 0.0.0.0:8080

# 测量服务（可选）
measurement_server_addr: 0.0.0.0:9090

# TLS 配置（生产环境强烈建议启用）
tls_letsencrypt_cache_dir: /var/www/cache
tls_letsencrypt_hostname: ""
tls_cert_path: ""
tls_key_path: ""

# 域名设置
derper:
  active: true
  url: "https://derper.example.com"
  private_key: ""

# 自定义 DNS
dns_config:
  override_local_dns: true
  nameservers:
    - "1.1.1.1"
    - "8.8.8.8"

# 域列表
proxied: false

# 数据库
database:
  type: sqlite
  sqlite:
    db_path: "/var/lib/headscale/db.sqlite"

# 日志
log:
  format: json
  level: info

# 私钥
private_key_path: "/var/lib/headscale/private.key"

# Unix socket（用于 tailcontrol API）
unix_socket: /var/run/headscale/headscale.sock
unix_socket_permission: "0770"
```

### 第四步：使用 Docker Compose 部署

创建 `/opt/headscale/docker-compose.yml`：

```yaml
version: "3.9"

services:
  headscale:
    image: headscale/headscale:v0.23.0
    container_name: headscale
    restart: unless-stopped
    command: serve
    volumes:
      - ./config:/etc/headscale:ro
      - headscale-data:/var/lib/headscale
    ports:
      - "8080:8080"
      - "9090:9090"
    networks:
      - headscale-net

  headscale-ui:
    image: ghcr.io/gurucomputing/headscale-ui:latest
    container_name: headscale-ui
    restart: unless-stopped
    ports:
      - "9443:443"
    networks:
      - headscale-net

networks:
  headscale-net:
    driver: bridge

volumes:
  headscale-data:
```

启动服务：

```bash
docker compose up -d
```

### 第五步：初始化数据库和用户

```bash
# 进入容器执行初始化
docker exec headscale headscale users create default

# 创建第一个管理员用户
docker exec headscale headscale users create admin

# 查看状态
docker exec headscale headscale nodes list
```

## 配置 Tailscale 客户端连接 Headscale

### Linux 客户端配置

```bash
# 停止官方 Tailscale 服务
sudo systemctl stop tailscaled
sudo systemctl disable tailscaled

# 编辑 Tailscale 配置
sudo mkdir -p /etc/tailscale
sudo tee /etc/tailscale/auth.env > /dev/null <<EOF
HEADSCALE_URL=http://your-vps-ip:8080
EOF

# 重新配置 Tailsale 使用 Headscale
sudo tailscale up --login-url=http://your-vps-ip:8080/admin/users/default/s/device
```

### macOS 客户端配置

```bash
# 下载 Tailscale for macOS
brew install tailscale

# 配置 Headscale 后端
sudo tailscale configure-host
sudo tailscale up --login-url=http://your-vps-ip:8080/admin/users/default/s/device
```

### Windows 客户端配置

1. 从 [tailscale.com](https://tailscale.com/download) 下载安装包
2. 打开 PowerShell（管理员）：
```powershell
Restart-Service tailscaled
tailscale config set-control-url http://your-vps-ip:8080
tailscale up
```

## ACL 访问控制配置

Headscale 使用 YAML 格式的 ACL 文件来控制节点间通信。创建 `/opt/headscale/config/acls.yaml`：

```yaml
# ACL 配置示例
# 允许所有节点互相通信
- action: accept
  sources:
    - '*'
  protocols:
    - tcp
    - udp
    - icmp

# 限制特定子网访问
- action: accept
  sources:
    - 'user:admin'
  protocols:
    - tcp:22

# 阻止某些流量
- action: drop
  sources:
    - 'group:guest'
  protocols:
    - tcp:443
```

在配置文件中引用 ACL：

```yaml
# config.yaml 中添加
acl:
  auto_appends:
    - user:admin
  distributions:
    - group:admins:
      - admin
```

## 启用 HTTPS（生产环境）

### 选项一：Let's Encrypt（推荐）

```yaml
# config.yaml
tls_letsencrypt_hostname: "headscale.yourdomain.com"
tls_letsencrypt_cache_dir: "/var/lib/headscale/cert"
tls_letsencrypt_email: "admin@yourdomain.com"
```

配合 Nginx 反向代理：

```nginx
server {
    listen 443 ssl http2;
    server_name headscale.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/headscale.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/headscale.yourdomain.com/privkey.pem;

    location / {
        proxy_pass http://localhost:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### 选项二：自有证书

```yaml
tls_cert_path: "/etc/ssl/certs/headscale.crt"
tls_key_path: "/etc/ssl/private/headscale.key"
```

## 常用管理命令

```bash
# 列出所有节点
docker exec headscale headscale nodes list

# 查看节点详情
docker exec headscale headscale nodes list --json

# 重命名节点
docker exec headscale headscale nodes rename old-name new-name

# 强制刷新节点
docker exec headscale headscale nodes expire <node-id>

# 查看预共享密钥
docker exec headscale headscale keys list

# 创建新的预共享密钥（7天有效）
docker exec headscale headscale preauth-key create --user default --reusable --expiration 168h

# 查看日志
docker logs -f headscale

# 健康检查
curl -s http://localhost:8080/health
```

## 与官方 Tailscale 的迁移

如果你正在从 Tailscale 迁移到 Headscale：

1. 在 Headscale 上创建相同的用户和组
2. 在每个客户端上重新配置 `--login-url`
3. 重新执行 `tailscale up` 进行认证
4. 迁移 ACL 配置
5. 保留原有的 WireGuard 密钥（如果需要）

> ⚠️ 迁移后原有节点的 Machine Key 会改变，但 Ephemeral Key 保持不变。

## 监控与告警

### Prometheus 指标

Headscale 自带 `/metrics` 端点，可以集成到 Prometheus：

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'headscale'
    static_configs:
      - targets: ['headscale:9090']
```

### Grafana 仪表盘

导入 [社区仪表盘](https://github.com/juankivz/headscale-grafana-dashboard) 来可视化：
- 在线节点数量
- API 请求延迟
- 数据库大小增长
- 认证事件频率

## 常见问题

### Q: Headscale 能替代 Tailscale 的所有功能吗？

A: 大部分核心功能都可以：P2P 直连、DERP 中继、MagicDNS、ACL 控制。但 Tailscale 的 Tailnet Lock、SaaS 集成、审计日志等企业功能在 Headscale 中需要自行实现。

### Q: DERP 中继服务器怎么配置？

A: Headscale 内置了简单的 DERP 服务器，也可以配置公共 DERP：

```yaml
derper:
  active: true
  stun:
    active: true
    listen_addr: "0.0.0.0:3478"
```

### Q: 如何备份 Headscale 数据？

```bash
# 备份数据库
cp /var/lib/headscale/db.sqlite backup-headscale-$(date +%Y%m%d).sqlite

# 备份密钥
cp /var/lib/headscale/private.key backup-private-key.key

# 备份配置
tar czf headscale-config-backup.tar.gz /opt/headscale/config/
```

### Q: Headscale 支持 IPv6 吗？

A: 是的，Headscale 原生支持 IPv6。只需在配置中启用：

```yaml
ip_prefixes:
  - fd7a:115c:a1e0::/48
  - 2a01:4f8:c2c:123f::/64
```

## 总结

Headscale 为那些希望完全掌控自己网络基础设施的用户提供了一个优秀的开源替代方案。在 VPS 上部署 Headscale 后，你拥有了：

- ✅ 完全的数据主权和网络拓扑可见性
- ✅ 零成本的无限节点扩展
- ✅ 灵活的 ACL 和 DNS 配置
- ✅ 完整的审计日志能力
- ✅ 与 Tailscale 客户端的无缝兼容

对于注重隐私、合规性要求高的用户来说，自建 Headscale 是最值得投入的 VPS 项目之一。

---

> 📌 **下一步**：结合 [CrowdSec](/zh/post/crowdsec-intrusion-prevention/) 为 Headscale 添加入侵检测，构建完整的零信任安全体系。