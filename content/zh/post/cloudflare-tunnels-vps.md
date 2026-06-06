---
title: "Cloudflare Tunnels 零端口暴露 VPS 服务：无需公网 IP 的安全方案"
description: "通过 Cloudflare Tunnels 将 VPS 上的 Docker 服务安全暴露到公网，无需开放任何端口、无需配置公网 IP、无需 SSL 证书，全程零配置"
date: 2026-06-06T10:00:00+08:00
lastmod: 2026-06-06T10:00:00+08:00
slug: "cloudflare-tunnels-vps"
image: /images/posts/cloudflare-tunnels-vps/featured.png
tags: ["Cloudflare", "Tunnels", "网络安全", "VPS", "Docker", "反向代理", "零信任", "自托管"]
categories: ["网络运维"]
aliases: [/zh/post/cloudflare-tunnels-vps/]
---

## 引言

假设你有一台位于内网的 VPS，上面跑着 Home Assistant、Nextcloud 或某个自建博客。你想从外面访问它，但——

- 运营商不给公网 IPv4 地址；
- 你不想在路由器上开一堆端口映射；
- 你懒得自己搞 SSL 证书；
- 你担心直接暴露 SSH 和 Web 端口不安全。

**Cloudflare Tunnels** 就是为此而生的。它通过在你的服务器上安装一个轻量级隧道守护进程（`cloudflared`），将你的服务加密转发到 Cloudflare 全球边缘网络。整个过程**不需要开放任何入站端口**，也不需要公网 IP。

本文将带你从零搭建一套基于 Cloudflare Tunnels 的 VPS 服务暴露方案，配合 Docker 使用，全程自动化。

---

## 工作原理

```
[浏览器] ←HTTPS→ [Cloudflare 边缘节点] ←TLS→ [cloudflared 隧道] ←HTTP→ [你的 VPS 服务]
```

1. 你在 VPS 上运行 `cloudflared`，它会主动向外发起 TCP 连接到 Cloudflare 边缘
2. 因为连接方向是**出向**的，所以你的防火墙无需放行任何入站端口
3. Cloudflare 收到用户的 HTTPS 请求后，通过隧道将流量转发到你的 VPS
4. 隧道两端都使用加密传输，确保数据安全

### 核心优势

| 特性 | 传统方案 | Cloudflare Tunnels |
|------|----------|-------------------|
| 需要公网 IP | ✅ 必须 | ❌ 不需要 |
| 需要开放端口 | ✅ 80/443 | ❌ 不需要 |
| SSL 证书 | 手动管理 | Cloudflare 自动管理 |
| DDoS 防护 | 需额外配置 | Cloudflare 内置 |
| WAF / Bot 防护 | 需额外配置 | Cloudflare 内置 |
| 地域访问限制 | 手动配置 | 内置 GeoIP 功能 |

---

## 第一步：注册 Cloudflare 并添加域名

1. 访问 [cloudflare.com](https://cloudflare.com) 注册账号
2. 添加你的域名（可以使用已拥有的域名，也可以免费注册一个 `.cf` 域名）
3. 将域名的 NS 记录指向 Cloudflare 提供的 NS 服务器
4. 等待 DNS 生效（通常几分钟到几小时）

> 💡 **省钱技巧**：如果你还没有域名，Cloudflare 偶尔会提供免费注册域名的活动。或者使用 [Freenom](https://freenom.com) 获取免费的 `.tk` / `.ml` 域名（但稳定性不如付费域名）。

---

## 第二步：安装 cloudflared

### 方式一：使用 Docker（推荐）

```bash
# 创建配置目录
mkdir -p ~/cloudflared/config
cd ~/cloudflared

# 拉取镜像
docker pull cloudflare/cloudflared:latest
```

### 方式二：直接安装二进制

```bash
# Ubuntu/Debian
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
chmod +x cloudflared-linux-amd64
sudo mv cloudflared-linux-amd64 /usr/local/bin/cloudflared

# 验证安装
cloudflared --version
```

---

## 第三步：创建隧道并认证

### 使用 Access Tunnel（最简单，适合个人使用）

```bash
# 运行认证命令
cloudflared tunnel login
```

这会在浏览器中打开 Cloudflare 的认证页面。选择你要关联的域名账户，授权后即可。认证信息会保存到 `~/.cloudflared/cert.pem`。

### 使用 Tunnel CID（适合团队/生产环境）

```bash
# 创建隧道
cloudflared tunnel create my-vps-tunnel

# 输出类似：
# Tunnel credentials saved to /home/user/.cloudflared/<tunnel-id>.json
# Tunnel my-vps-tunnel (xxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx) created
```

记录输出的 **Tunnel ID**，后面会用到。

---

## 第四步：配置路由规则

### 方法一：YAML 配置文件

创建配置文件 `~/cloudflared/config/config.yml`：

```yaml
tunnel: <你的TUNNEL_ID>
credentials-file: /home/<你的用户名>/.cloudflared/<TUNNEL_ID>.json

ingress:
  # 主域名 → 博客
  - hostname: blog.yourdomain.com
    service: http://localhost:8080
  
  # Nextcloud
  - hostname: files.yourdomain.com
    service: http://localhost:8081
  
  # Home Assistant
  - hostname: home.yourdomain.com
    service: http://localhost:8123
  
  # 默认 404
  - service: http_status:404
```

### 方法二：Docker Compose 集成

创建 `~/cloudflared/docker-compose.yml`：

```yaml
version: "3.8"

services:
  cloudflared:
    image: cloudflare/cloudflared:latest
    container_name: cloudflared
    restart: unless-stopped
    command: tunnel --no-autoupdate run
    volumes:
      - ./config:/etc/cloudflared:ro
    environment:
      - TUNNEL_TOKEN=<你的TUNNEL_TOKEN>  # 如果用 login 方式可省略

  # 示例：一个博客服务
  blog:
    image: ghcr.io/go-hugo/hugo:extended
    container_name: hugo-blog
    restart: unless-stopped
    ports:
      - "8080:80"
    volumes:
      - ./blog:/src

  # 示例：Nextcloud
  nextcloud:
    image: nextcloud:apache
    container_name: nextcloud
    restart: unless-stopped
    ports:
      - "8081:80"
    volumes:
      - nextcloud_data:/var/www/html
    environment:
      - MYSQL_DATABASE=nextcloud
      - MYSQL_USER=nextcloud
      - MYSQL_PASSWORD=secure_password_here
      - MYSQL_HOST=db

  db:
    image: mysql:8
    container_name: nextcloud-db
    restart: unless-stopped
    volumes:
      - mysql_data:/var/lib/mysql
    environment:
      - MYSQL_ROOT_PASSWORD=root_secure_password
      - MYSQL_DATABASE=nextcloud
      - MYSQL_USER=nextcloud
      - MYSQL_PASSWORD=secure_password_here

volumes:
  nextcloud_data:
  mysql_data:
```

---

## 第五步：启动隧道

### 使用 systemd 守护（推荐生产环境）

```bash
# 创建服务文件
sudo tee /etc/systemd/system/cloudflared.service > /dev/null << 'EOF'
[Unit]
Description=Cloudflare Tunnel
After=network-online.target
Wants=network-online.target

[Service]
Type=notify
ExecStart=/usr/local/bin/cloudflared tunnel --config /home/<用户名>/.cloudflared/config.yml run
Restart=on-failure
RestartSec=5
LimitNOFILE=infinity

[Install]
WantedBy=multi-user.target
EOF

# 启动并设置开机自启
sudo systemctl daemon-reload
sudo systemctl enable --now cloudflared

# 查看状态
sudo systemctl status cloudflared

# 查看隧道日志
cloudflared tunnel route dns <tunnel-name> <子域名>.yourdomain.com
```

### 使用 Docker Compose 启动

```bash
cd ~/cloudflared
docker compose up -d
```

---

## 第六步：DNS 路由配置

将子域名关联到你的隧道：

```bash
# 添加 DNS 记录（使用 TUNNEL_ID）
cloudflared tunnel route dns my-vps-tunnel blog.yourdomain.com
cloudflared tunnel route dns my-vps-tunnel files.yourdomain.com
cloudflared tunnel route dns my-vps-tunnel home.yourdomain.com

# 验证 DNS 记录
cloudflared tunnel info my-vps-tunnel
```

完成后，浏览器访问 `https://blog.yourdomain.com` 即可看到你的服务。

---

## 第七步（可选）：Cloudflare Access 身份验证

如果你希望只允许特定人员访问某些服务（比如 Home Assistant），可以启用 **Cloudflare Access**：

```bash
# 在 Cloudflare Dashboard 中：
# 1. 进入 Zero Trust → Access → Applications
# 2. 点击 "Add an application"
# 3. 选择 "Self-hosted"
# 4. 设置 Domain: home.yourdomain.com
# 5. 设置 Auth Domain: yourdomain.com
# 6. 选择验证方式（Google/GitHub/邮箱等）
```

启用后，访问 `home.yourdomain.com` 时会自动跳转到登录页面，只有经过认证的用户才能访问。

### 通过 CLI 配置 Access Policy

```bash
# 使用 Cloudflare API Token 配置
curl -X POST "https://api.cloudflare.com/client/v4/accounts/<ACCOUNT_ID>/access/services/gateway/service_report" \
  -H "Authorization: Bearer <API_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "enabled": true
  }'
```

---

## 常见问题与排查

### 1. 隧道连接失败

```bash
# 检查 cloudflared 日志
sudo journalctl -u cloudflared -f

# 常见原因：
# - cert.pem 过期（重新运行 cloudflared tunnel login）
# - TUNNEL_ID 错误（检查配置文件）
# - 网络问题（确认 VPS 可以访问 200.0.0.0/4）
```

### 2. 服务返回 502 Bad Gateway

- 确认你的本地服务确实在运行：`curl http://localhost:8080`
- 确认 `config.yml` 中的端口号正确
- 检查服务监听的是 `0.0.0.0` 而不是 `127.0.0.1`

### 3. SSL 证书问题

Cloudflare Tunnels 默认使用 Cloudflare 的泛域名证书。如果你的浏览器提示证书不安全：

- 确认域名已正确添加到 Cloudflare
- 确认 TLS 模式设置为 **Full**（Cloudflare Dashboard → DNS → SSL/TLS）
- 清除浏览器缓存重试

### 4. 带宽限制

Cloudflare Tunnels 免费版有 **100 GB/月** 的出站流量限制。对于个人自用通常足够。如果超出：

- 监控用量：Cloudflare Dashboard → Analytics
- 考虑升级到 Pro 计划（$20/月）
- 对大流量服务启用缓存规则

---

## 与其他方案对比

| 方案 | 成本 | 复杂度 | 安全性 | 适合场景 |
|------|------|--------|--------|----------|
| **Cloudflare Tunnels** | 免费 | ⭐ 低 | ⭐⭐⭐⭐⭐ | 个人/中小团队 |
| Ngrok | 免费（限速） | ⭐ 低 | ⭐⭐⭐ | 临时测试 |
| frp | 需要中继服务器 | ⭐⭐⭐ | ⭐⭐⭐ | 有 VPS 的用户 |
| Caddy 反向代理 | 免费（自动证书） | ⭐⭐ | ⭐⭐⭐⭐ | 有公网 IP |
| Tailscale | 免费（100 设备） | ⭐ 低 | ⭐⭐⭐⭐⭐ | 私人访问 |

> 💡 **最佳实践**：个人自托管推荐组合——Cloudflare Tunnels（公网暴露）+ Tailscale（内网管理）。公网服务走 Tunnels，SSH 管理走 Tailscale，各取所长。

---

## 总结

Cloudflare Tunnels 是目前**最适合自托管爱好者的 VPS 暴露方案**：

- ✅ **零端口开放**——安全性大幅提升
- ✅ **自动 HTTPS**——无需自己管理证书
- ✅ **DDoS 防护**——Cloudflare 全球网络兜底
- ✅ **免费使用**——100GB/月出站流量足够个人使用
- ✅ **Access 集成**——轻松添加身份验证

对于搭建博客、Nextcloud、Home Assistant 等自托管服务，Cloudflare Tunnels 是最省心的选择。配合 Docker 使用，整个部署过程不到 10 分钟。

开始部署吧，让你的服务安全地上网！

---

*更多 VPS 自托管指南，请访问 [selfvps.net](https://selfvps.net)*
