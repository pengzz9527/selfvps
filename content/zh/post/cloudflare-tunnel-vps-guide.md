---
title: "Cloudflare Tunnel + VPS：免费实现公网访问内网服务"
description: "无需公网 IP，无需端口转发，通过 Cloudflare Tunnel 将 VPS 上的自托管服务安全暴露到互联网，附带 Docker Compose 完整部署方案"
date: 2026-06-25T08:00:00+08:00
slug: "cloudflare-tunnel-vps-guide"
tags: ["Cloudflare", "Tunnel", "反向代理", "无公网IP", "自托管", "Docker", "网络安全"]
categories: ["网络架构"]
aliases: [/zh/post/cloudflare-tunnel-vps-guide/]
image: /images/posts/cloudflare-tunnel-vps-guide/featured.png
---

## 为什么需要 Cloudflare Tunnel？

大多数家庭用户和低配 VPS 用户面临一个共同问题：**没有公网 IP**。即使你有 VPS，如果运营商分配的是内网 IP（如 CGNAT），你也无法直接从互联网访问你的服务。

传统的解决方案是端口转发（Port Forwarding），但这需要：
- 路由器支持端口转发
- 拥有公网 IPv4/IPv6 地址
- 暴露端口带来安全风险

**Cloudflare Tunnel**（原 Argo Tunnel）提供了一条完全不同的路径——它通过在您的服务器上运行一个轻量级代理进程，主动向外建立加密连接，从而让 Cloudflare 的边缘网络能够将流量安全地转发到您的内网服务。**无需开放任何端口，无需公网 IP。**

## 工作原理

```
互联网用户 → Cloudflare CDN 边缘节点 → cloudflared 隧道 → 您的 VPS 本地服务
     (DNS)         (HTTPS/TLS)              (出站TCP)          (localhost:port)
```

1. **cloudflared** 在您的 VPS 上运行，主动向 Cloudflare 的边缘节点建立出站 TCP 连接
2. 用户访问您的域名时，DNS 解析到 Cloudflare 的边缘 IP
3. Cloudflare 通过已建立的隧道将请求转发到您的 VPS
4. 所有传输均经过 TLS 加密

**关键优势**：出站连接不需要防火墙放行，因为连接是从内向外发起的。

## 准备工作

### 所需条件

- 一台 VPS（任何配置均可，即使只有 512MB RAM）
- 一个已注册到 Cloudflare 的域名
- Docker 和 Docker Compose（推荐使用容器化部署 cloudflared）

### 创建 Cloudflare Tunnel

1. 登录 [Cloudflare Dashboard](https://dash.cloudflare.com)
2. 选择您的域名 → **Zero Trust** → **Networks** → **Tunnels**
3. 点击 **Create a tunnel**，选择 **Cloudflared** 作为连接器
4. 复制生成的安装令牌（Token）

## 在 VPS 上部署 cloudflared

### 方法一：Docker Compose（推荐）

创建一个 `docker-compose.yml` 文件：

```yaml
version: '3.8'

services:
  cloudflared:
    image: cloudflare/cloudflared:latest
    container_name: cloudflared
    restart: unless-stopped
    command: tunnel --no-autoupdate run --token ${TUNNEL_TOKEN}
    environment:
      - TUNNEL_TOKEN=your_token_here
    networks:
      - web

networks:
  web:
    driver: bridge
```

启动服务：

```bash
export TUNNEL_TOKEN="eyJhIjoiYWNjb3VudC1pZCIsInQiOiJ0dW5uZWwtdG9rZW4iLCJzIjoic2VjcmV0In0="
docker compose up -d
```

### 方法二：直接安装

```bash
# Debian/Ubuntu
curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg \
  | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null

echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] \
  https://pkg.cloudflare.com/cloudflared $(lsb_release -cs) main" \
  | sudo tee /etc/apt/sources.list.d/cloudflared.list

sudo apt update && sudo apt install -y cloudflared

# 配置隧道
sudo cloudflared tunnel setup my-tunnel \
  --token "your_token_here"

sudo systemctl enable cloudflared-my-tunnel
sudo systemctl start cloudflared-my-tunnel
```

## 配置路由规则

### 通过 CLI 配置（Docker 方式）

首先需要在 Cloudflare Dashboard 中为隧道添加路由规则。或者使用 CLI：

```bash
# 列出所有隧道
cloudflared tunnel list

# 查看隧道详情
cloudflared tunnel info my-tunnel

# 添加路由规则：将 HTTP 服务映射到隧道
cloudflared tunnel route dns my-tunnel demo.yourdomain.com
```

### 通过 Dashboard 配置

1. 回到 Zero Trust → Tunnels → 选择您的隧道
2. 进入 **Public Hostnames** 标签页
3. 点击 **Add a public hostname**
4. 填写配置：
   - **Subdomain**: `demo`
   - **Domain**: `yourdomain.com`
   - **Service Type**: `HTTP`
   - **URL**: `localhost:8080`（或您的服务端口）
5. 点击 **Save tunnel**

### 多服务示例

您可以为一个隧道配置多个路由，将不同子域名指向不同的本地服务：

| 子域名 | 服务类型 | 目标地址 | 对应服务 |
|--------|----------|----------|----------|
| `home.yourdomain.com` | HTTP | `localhost:8080` | Home Assistant |
| `docs.yourdomain.com` | HTTP | `localhost:3000` | Wiki.js |
| `files.yourdomain.com` | HTTP | `localhost:80` | Nextcloud |
| `monitor.yourdomain.com` | HTTP | `localhost:3001` | Uptime Kuma |
| `chat.yourdomain.com` | HTTPS | `localhost:8443` | ChatGPT-Next-Web |

## 完整自托管服务示例

以下是一个完整的 Docker Compose 配置，同时运行 cloudflared 和您自己的服务：

```yaml
version: '3.8'

services:
  # 您的自托管服务
  nextcloud:
    image: nextcloud:apache
    container_name: nextcloud
    restart: unless-stopped
    volumes:
      - nextcloud_data:/var/www/html
      - nextcloud_config:/var/www/html/config
    environment:
      - MYSQL_HOST=db
      - MYSQL_PASSWORD=nextcloud
      - MYSQL_DATABASE=nextcloud
      - MYSQL_USER=nextcloud
    networks:
      - apps

  # 数据库
  db:
    image: mariadb:10.11
    container_name: nextcloud-db
    restart: unless-stopped
    command: --transaction-isolation=READ-COMMITTED --binlog-format=ROW
    volumes:
      - db_data:/var/lib/mysql
    environment:
      - MYSQL_ROOT_PASSWORD=rootpass
      - MYSQL_PASSWORD=nextcloud
      - MYSQL_DATABASE=nextcloud
      - MYSQL_USER=nextcloud
    networks:
      - apps

  # cloudflared 隧道
  cloudflared:
    image: cloudflare/cloudflared:latest
    container_name: cloudflared
    restart: unless-stopped
    command: tunnel --no-autoupdate run --token ${TUNNEL_TOKEN}
    environment:
      - TUNNEL_TOKEN=${TUNNEL_TOKEN}
    networks:
      - apps
    depends_on:
      - nextcloud

volumes:
  nextcloud_data:
  nextcloud_config:
  db_data:

networks:
  apps:
    driver: bridge
```

环境变量配置：

```bash
# .env 文件
TUNNEL_TOKEN=eyJhIjoiYWNjb3VudC1pZCIsInQiOiJ0dW5uZWwtdG9rZW4iLCJzIjoic2VjcmV0In0=
```

配置路由（Dashboard 中）：
- `nextcloud.yourdomain.com` → `http://nextcloud:80`

## 安全性增强

### 启用 Cloudflare Access（零信任访问控制）

Cloudflare Tunnel 可以与 Cloudflare Access 集成，为您的服务添加额外的身份验证层：

1. 在 Zero Trust Dashboard 中创建 **Access Policy**
2. 设置规则，例如：
   - 仅允许特定邮箱域名访问
   - 要求 OAuth 2.0 认证（Google、GitHub 等）
   - 设备合规性检查
3. 将策略应用到您的隧道子域名

### 其他安全建议

- **使用 HTTPS**：Cloudflare 默认提供免费的 Let's Encrypt SSL 证书
- **启用 WAF 规则**：在 Cloudflare Dashboard 中配置 Web 应用防火墙
- **限制源 IP**：如果服务本身有 IP 白名单，配合 Cloudflare Proxy IP
- **定期轮换 Token**：Tunnel Token 泄露时可快速重建

## 常见问题排查

### 服务无法访问

```bash
# 检查 cloudflared 容器状态
docker logs cloudflared

# 查看隧道连接状态
cloudflared tunnel info my-tunnel

# 测试本地服务是否正常运行
curl http://localhost:8080
```

### DNS 解析问题

```bash
# 确认 DNS 记录已创建
dig demo.yourdomain.com CNAME
# 应返回类似：demo.yourdomain.com CNAME xxxxxxxx.cfargotunnel.com

# 检查 Cloudflare Dashboard 中的 DNS 设置
```

### 性能优化

- 启用 Cloudflare **Auto Minify**（HTML/CSS/JS）
- 开启 ** Brotli 压缩**
- 配置 **缓存规则**，将静态资源缓存时间设长
- 对于高流量服务，考虑升级 Cloudflare 计划以获得更好的边缘性能

## 与 Nginx Proxy Manager 对比

| 特性 | Cloudflare Tunnel | Nginx Proxy Manager |
|------|-------------------|---------------------|
| 需要公网 IP | ❌ 不需要 | ✅ 需要 |
| 需要端口开放 | ❌ 不需要 | ✅ 需要 |
| SSL 证书 | ✅ 自动 | 手动/自动 |
| CDN 加速 | ✅ 内置 | ❌ 无 |
| DDoS 防护 | ✅ 内置 | ❌ 无 |
| 访问控制 | ✅ Access 集成 | ✅ Basic Auth |
| 跨地域访问 | ✅ 全球边缘 | ❌ 单点 |
| 免费额度 | ✅ 无限带宽* | ✅ 完全免费 |

*\*Cloudflare 免费计划无带宽限制，但高级功能需付费*

## 总结

Cloudflare Tunnel 是自托管爱好者和中小团队的理想选择：

1. **零成本**：无需公网 IP，无需额外硬件
2. **高安全**：出站连接，端口不暴露，TLS 加密
3. **易维护**：Docker 一键部署，Dashboard 可视化配置
4. **可扩展**：支持任意数量的服务和子域名
5. **全球加速**：利用 Cloudflare 200+ 边缘节点

对于没有公网 IP 的用户来说，Cloudflare Tunnel 几乎是唯一的选择。而对于有公网 IP 的用户，它也是一个极佳的安全补充——将服务放在 Cloudflare 的防护伞下，比直接暴露在公网安全得多。

开始部署吧！只需几分钟，您就可以安全地将任何自托管服务暴露到互联网上。
