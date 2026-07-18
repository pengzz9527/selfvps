---
title: "Cloudflare Tunnel 完全指南：零端口转发，安全暴露本地服务到公网"
description: "无需公网 IP、无需配置路由器端口转发，通过 Cloudflare Tunnel 将本地 VPS/家庭 NAS 上的服务安全暴露到互联网。完整教程涵盖安装、配置、多服务管理与故障排除。"
date: 2026-07-18T10:00:00+08:00
lastmod: 2026-07-18T10:00:00+08:00
slug: "cloudflare-tunnel-zero-config-guide"
tags: ["Cloudflare", "Tunnel", "网络安全", "自托管", "零信任", "Docker", "内网穿透", "反向代理"]
categories: ["部署教程"]
draft: false
image: /images/posts/cloudflare-tunnel-zero-config-guide/featured.png
aliases: [/zh/post/cloudflare-tunnel-zero-config-guide/]
---

## 什么是 Cloudflare Tunnel？

Cloudflare Tunnel（原名 Argo Tunnel）是 Cloudflare 提供的一项免费服务，它允许你将本地运行的服务（Web 应用、SSH、数据库等）**安全地暴露到互联网**，而无需：

- 拥有公网 IP 地址
- 在路由器上配置端口转发
- 开放防火墙入站规则
- 暴露服务器的真实 IP

其核心原理是在你的服务器上运行一个轻量级代理进程（`cloudflared`），该进程与 Cloudflare 的全球边缘网络建立**出站 TLS 加密连接**。当用户访问你的域名时，请求通过 Cloudflare 的边缘节点，经由隧道转发到你的本地服务。

```
用户 → Cloudflare 边缘节点 → TLS 隧道 → cloudflared → 本地服务
```

## 为什么选择 Cloudflare Tunnel？

### 与传统端口转发的对比

| 特性 | 端口转发 | Cloudflare Tunnel |
|------|---------|-------------------|
| 需要公网 IP | ✅ 必须 | ❌ 不需要 |
| 路由器配置 | ✅ 复杂 | ❌ 零配置 |
| 暴露真实 IP | ✅ 是 | ❌ Cloudflare IP |
| DDoS 防护 | ❌ 无 | ✅ 自动 |
| HTTPS/SSL | ❌ 需自行配置 | ✅ 自动 |
| 成本 | 可能有额外费用 | 完全免费 |
| 安全模型 | 防火墙规则 | 零信任架构 |

### 核心优势

1. **安全性提升**：你的服务器 IP 对互联网完全隐藏，Cloudflare 的 DDoS 防护自动生效
2. **零配置 HTTPS**：Cloudflare 自动为你的域名签发和管理 SSL 证书
3. **跨网络环境**：在 NAT 后面、公司防火墙后、家庭宽带中都能工作
4. **多服务支持**：一个 Tunnel 可以路由多个域名和子路径到不同本地服务
5. **全球加速**：利用 Cloudflare 100+ 个边缘节点，全球访问速度更快

## 准备工作

### 前提条件

- 一个 **Cloudflare 账户**（免费注册）
- 一个已通过 Cloudflare 托管 DNS 的**域名**
- 一台运行 Linux 的 VPS 或家庭服务器
- 至少一个需要在公网访问的本地服务（如 Web 应用、NAS、Home Assistant 等）

### 验证域名是否在 Cloudflare 上

登录 Cloudflare Dashboard，确认你的域名已添加到 Cloudflare 管理中，并且 DNS 记录正在使用 Cloudflare 的 nameserver。

## 安装 cloudflared

### Ubuntu / Debian

```bash
# 添加 Cloudflare GPG 密钥和仓库
curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg \
  | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null

echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] \
  https://pkg.cloudflare.com/cloudflared $(lsb_release -cs) main" \
  | sudo tee /etc/apt/sources.list.d/cloudflared.list

sudo apt update && sudo apt install -y cloudflared
```

### CentOS / RHEL / Rocky Linux

```bash
sudo rpm -ivh https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-x86_64.rpm
```

### 使用 Docker 安装

```yaml
# docker-compose.yml
version: "3.8"
services:
  cloudflared:
    image: cloudflare/cloudflared:latest
    restart: unless-stopped
    command: tunnel --no-autoupdate run
    environment:
      - TUNNEL_TOKEN=${TUNNEL_TOKEN}
    networks:
      - tunnel-net

networks:
  tunnel-net:
    driver: bridge
```

### 验证安装

```bash
cloudflared --version
# 输出类似: cloudflared version 2025.x.x (built ...)
```

## 方法一：使用 Cloudflare Zero Trust Dashboard（推荐）

这是最简单的方式，适合大多数用户。

### 步骤 1：创建 Tunnel

1. 登录 [Cloudflare Zero Trust Dashboard](https://one.dash.cloudflare.com/)
2. 进入 **Networks** → **Tunnels**
3. 点击 **Create a tunnel**
4. 选择 **Cloudflared** 作为连接器类型
5. 输入 Tunnel 名称（如 `my-server`），点击 **Save tunnel**

### 步骤 2：获取安装命令

Dashboard 会显示安装命令，根据你的操作系统选择：

```bash
# Ubuntu / Debian
sudo cloudflared service install <TOKEN>
```

其中 `<TOKEN>` 是 Dashboard 生成的长令牌字符串。

### 步骤 3：配置路由规则

安装完成后，在 Dashboard 中配置 **Public Hostnames**：

| Subdomain | Domain | Type | URL |
|-----------|--------|------|-----|
| blog | example.com | HTTP | http://localhost:8080 |
| admin | example.com | HTTP | http://localhost:3000 |
| files | example.com | HTTP | http://localhost:8090 |

每个规则将子域名映射到你本地运行的服务端口。

### 步骤 4：验证

```bash
# 检查 Tunnel 状态
sudo systemctl status cloudflared

# 查看日志
sudo journalctl -u cloudflared -f
```

## 方法二：使用 YAML 配置文件（高级用户）

适合需要版本控制配置、自动化部署的场景。

### 步骤 1：认证并创建 Tunnel

```bash
# 登录 Cloudflare（使用 API Token）
cloudflared tunnel login

# 创建 Tunnel
cloudflared tunnel create my-server
# 输出: Tunnel credentials written to /root/.cloudflared/<UUID>.json
# 注意保存 Tunnel UUID
```

### 步骤 2：配置 YAML

```yaml
# /etc/cloudflared/config.yaml
tunnel: <YOUR-TUNNEL-UUID>
credentials-file: /root/.cloudflared/<UUID>.json

ingress:
  # 主网站
  - hostname: blog.example.com
    service: http://localhost:8080
  
  # 管理面板
  - hostname: admin.example.com
    service: http://localhost:3000
  
  # 文件服务
  - hostname: files.example.com
    service: http://localhost:8090
  
  # 默认规则（必须存在）
  - service: http_status:404
```

### 步骤 3：注册 DNS 记录

```bash
# 为每个子域名添加 DNS CNAME 记录
cloudflared tunnel route dns my-server blog.example.com
cloudflared tunnel route dns my-server admin.example.com
cloudflared tunnel route dns my-server files.example.com
```

### 步骤 4：启动并设置开机自启

```bash
# 测试配置是否正确
cloudflared tunnel --config /etc/cloudflared/config.yaml run

# 设置为系统服务
sudo cloudflared service install

# 启用自启
sudo systemctl enable cloudflared
sudo systemctl start cloudflared
```

## 进阶配置

### 使用 Docker Compose 管理多服务

```yaml
# docker-compose.yml
version: "3.8"

services:
  # 本地服务示例
  blog:
    image: wordpress:latest
    ports:
      - "8080:80"
    volumes:
      - ./wordpress:/var/www/html
    environment:
      WORDPRESS_DB_HOST: db
      WORDPRESS_DB_USER: wordpress
      WORDPRESS_DB_PASSWORD: secure_password_here
      WORDPRESS_DB_NAME: wordpress
    restart: unless-stopped

  admin-panel:
    image: portainer/portainer-ce:latest
    ports:
      - "3000:9000"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - portainer_data:/data
    restart: unless-stopped

  file-server:
    image: filebrowser/filebrowser:latest
    ports:
      - "8090:80"
    volumes:
      - ./data:/srv
      - filebrowser_db:/data/filebrowser.db
    restart: unless-stopped

  # Cloudflare Tunnel
  cloudflared:
    image: cloudflare/cloudflared:latest
    restart: unless-stopped
    command: tunnel --no-autoupdate run --token ${TUNNEL_TOKEN}
    depends_on:
      - blog
      - admin-panel
      - file-server
    environment:
      - TUNNEL_TOKEN=<从Dashboard获取的Token>

volumes:
  portainer_data:
  filebrowser_db:
```

### 为 SSH 创建 Tunnel

```yaml
# 配置 ingress 规则
ingress:
  - hostname: ssh.example.com
    service: ssh://localhost:22
    originRequest:
      noTLSVerify: true
```

通过 Tunnel 访问 SSH：

```bash
ssh -o ProxyCommand="cloudflared access ssh --hostname ssh.example.com" user@example.com
```

### 健康检查与监控

```yaml
# 在 ingress 中添加健康检查端点
ingress:
  - hostname: monitor.example.com
    service: http://localhost:9090  # Prometheus/Grafana
```

### 使用 CNAME 而不是子域名

如果你不想创建新的子域名，可以将 Tunnel 绑定到现有域名的 CNAME：

```
# DNS 记录
_cname.cfargotunnel.com.  CNAME  <tunnel-uuid>.cfargotunnel.com.
```

然后通过以下格式的路由规则匹配：

```yaml
ingress:
  - hostname: "*.example.com"
    service: http://localhost:8080
```

## 安全最佳实践

### 1. 启用 Access Policies

在 Cloudflare Zero Trust 中为 Tunnel 添加访问策略：

- **管理员页面**：要求公司邮箱或 MFA 验证
- **内部工具**：限制特定 IP 范围或设备合规性
- **公开服务**：无需认证即可访问

```
设置路径: Zero Trust → Access → Applications → Add an Application
```

### 2. 最小化暴露面

只暴露真正需要公网访问的服务：

```yaml
ingress:
  # ✅ 需要公网访问
  - hostname: app.example.com
    service: http://localhost:8080
  
  # ❌ 不要暴露数据库、Redis 等内部服务
  # 即使它们在 localhost 上
```

### 3. 定期轮换 Token

```bash
# 在 Dashboard 中重新生成 Tunnel Token
# 然后更新配置并重启
sudo systemctl restart cloudflared
```

### 4. 监控 Tunnel 状态

```bash
# 检查 Tunnel 连接状态
cloudflared tunnel info my-server

# 查看实时日志
journalctl -u cloudflared -f --output=json | jq '.'
```

## 故障排除

### 问题 1：Tunnel 连接不稳定

```bash
# 增加连接超时
cloudflared tunnel run --grace-period 120s

# 检查网络质量
mtr -r -c 100 cloudflaretunnel.com
```

### 问题 2：DNS 解析失败

```bash
# 验证 DNS 记录是否正确
dig blog.example.com CNAME

# 检查 Tunnel 是否已注册 DNS
cloudflared tunnel info my-server
```

### 问题 3：502 Bad Gateway

```bash
# 检查本地服务是否正常运行
curl http://localhost:8080

# 查看 cloudflared 日志
sudo journalctl -u cloudflared -n 50
```

常见原因：
- 本地服务未启动
- 端口配置错误
- 防火墙阻止了 localhost 通信（极少见）

### 问题 4：证书问题

Cloudflare Tunnel 自动管理证书，如果遇到问题：

```bash
# 清除缓存的证书
rm -rf /root/.cloudflared/*.json

# 重新认证
cloudflared tunnel login
```

## 性能优化

### 启用 HTTP/2 和 HTTP/3

```yaml
ingress:
  - hostname: app.example.com
    service: https://localhost:8443
    originRequest:
      http2Origin: true
```

### 启用缓存

在 Cloudflare Dashboard 中为 Tunnel 域名配置缓存规则：

```
Rules → Transform Rules → Cache Rules

Cache Rule 示例:
- Match: URL path ends with .css, .js, .png, .jpg
- Cache Level: Cache Everything
- Edge TTL: 1 month
```

### 带宽优化

```yaml
originRequest:
  connectTimeout: 30s
  noHappyEyeballs: false
  keepAliveConnections: 100
  keepAliveTimeout: 90s
```

## 总结

Cloudflare Tunnel 是目前最优雅的本地服务暴露方案，特别适合：

- 家庭实验室 / Homelab 用户
- 没有公网 IP 的宽带用户
- 需要快速部署和撤销服务的场景
- 重视安全的自托管项目

通过 Tunnel，你可以在不牺牲安全性的前提下，让任何本地服务安全地服务于全球用户。

---

**推荐阅读**：[Cloudflare Tunnel 官方文档](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/)
