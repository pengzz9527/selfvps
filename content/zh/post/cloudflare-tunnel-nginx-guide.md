---
title: "Cloudflare Tunnel + Nginx 自托管安全暴露指南：无需公网 IP 的完整方案"
description: "零端口转发、零公网 IP，用 Cloudflare Tunnel 将本地 Nginx 服务安全暴露到互联网。本文涵盖 Cloudflared 安装配置、HTTPS 自动证书、WAF 防护和防火墙加固"
date: 2026-06-14T10:00:00+08:00
lastmod: 2026-06-14T10:00:00+08:00
slug: "cloudflare-tunnel-nginx-guide"
tags: ["Cloudflare", "Tunnel", "Nginx", "自托管", "网络安全", "无公网IP", "零信任", "DDoS"]
categories: ["部署教程"]
draft: false
aliases: [/zh/post/cloudflare-tunnel-nginx-guide/]
image: /images/posts/cloudflare-tunnel-nginx-guide/featured.png
---

## 为什么需要 Cloudflare Tunnel？

在传统自托管方案中，要将本地服务暴露到互联网，你通常需要：

- 公网 IP 地址（很多宽带/VPS 都不提供）
- 在路由器上做端口转发
- 自己管理 SSL 证书
- 面对直接的互联网攻击（CC 攻击、DDoS、端口扫描）

**Cloudflare Tunnel**（原名 Argo Tunnel）彻底改变了这一局面：

> 你的服务器不需要对外开放任何端口，Cloudflare 会建立一条从 Cloudflare 边缘到你们服务器的加密隧道，所有流量经过 Cloudflare 全球 CDN 网络。

### 核心优势

| 特性 | 传统端口转发 | Cloudflare Tunnel |
|------|-------------|-------------------|
| 公网 IP 要求 | ✅ 需要 | ❌ 不需要 |
| 端口暴露 | 所有端口 | 零端口暴露 |
| SSL 证书 | 手动管理 | 自动免费 |
| DDoS 防护 | 需额外方案 | Cloudflare 免费 CDN |
| 防火墙 | 需复杂配置 | 零信任策略 |
| 成本 | 端口转发免费 | Cloudflare 免费版可用 |

## 架构概览

```
┌─────────────┐     HTTPS      ┌──────────────────┐     加密隧道      ┌──────────────────┐
│   用户浏览器  │ ──────────────→│  Cloudflare CDN  │ ─────────────────→│  Cloudflared 代理  │
│             │     全球边缘    │  (WAF/CDN/CaaS)   │                   │  (你的 VPS 上)   │
└─────────────┘                 └──────────────────┘                   └────────┬─────────┘
                                                                              │
                                                                              ▼
                                                                       ┌──────────────────┐
                                                                       │   Nginx (本地)    │
                                                                       │   :80 / :443     │
                                                                       └──────────────────┘
```

## 前置条件

- 一个 Cloudflare 账户（免费注册）
- 一个通过 Cloudflare 管理的域名
- 一台 VPS 或本地服务器（Ubuntu 22.04+ 示例）
- Docker 已安装（可选，也可用二进制）

## 第一步：创建 Cloudflare Tunnel

### 1. 在 Cloudflare 控制台创建 Tunnel

登录 [Cloudflare Zero Trust 面板](https://one.dash.cloudflare.com/)，进入 **Networks → Tunnels**，点击 **Create a tunnel**。

选择 **cloudflared** 作为连接器类型，你会得到一个 **Tunnel Token**。保存它！

```bash
# 记下这个 token，接下来要用
TUNNEL_TOKEN="eyJhIjoiY2YtMTIz...省略..."
```

### 2. 使用 Token 注册 Tunnel

```bash
# 安装 cloudflared
curl -fsSL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o /usr/local/bin/cloudflared
chmod +x /usr/local/bin/cloudflared

# 使用 Token 创建隧道连接
cloudflared tunnel --no-autoupdate create selfvps-tunnel

# 获取 Tunnel ID
TUNNEL_ID=$(cat ~/.cloudflared/selfvps-tunnel.json | jq -r .TunnelID)
echo "Tunnel ID: $TUNNEL_ID"
```

## 第二步：配置 Nginx 本地服务

### 1. 安装 Nginx

```bash
sudo apt update && sudo apt install -y nginx
sudo systemctl enable --now nginx
```

### 2. 配置 Nginx Server Block

创建 `/etc/nginx/sites-available/selfvps.net`：

```nginx
server {
    listen 80;
    server_name selfvps.net www.selfvps.net;
    
    root /var/www/selfvps.net;
    index index.html;

    # 基本安全头
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    location / {
        try_files $uri $uri/ =404;
    }

    # 静态资源缓存
    location ~* \.(jpg|jpeg|png|gif|ico|css|js|woff2)$ {
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # 拒绝访问隐藏文件
    location ~ /\. {
        deny all;
        access_log off;
        log_not_found off;
    }
}
```

启用站点：

```bash
sudo ln -s /etc/nginx/sites-available/selfvps.net /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

### 3. 验证本地 Nginx 工作正常

```bash
curl -I http://localhost
# 应该返回 200 OK
```

## 第三步：配置 Tunnel 路由

### 1. 创建 DNS 记录

在 Cloudflare DNS 中添加一条 CNAME 记录：

```
Hostname: www.selfvps.net
Type: CNAME
Target: <TUNNEL_ID>.cfargotunnel.com
```

或者直接通过 Cloudflared 管理 DNS：

```bash
cloudflared tunnel --no-autoupdate route dns selfvps-tunnel www.selfvps.net
cloudflared tunnel --no-autoupdate route dns selfvps-tunnel selfvps.net
```

### 2. 创建 Tunnel 配置文件

```bash
sudo mkdir -p /etc/cloudflared
sudo tee /etc/cloudflared/config.yaml > /dev/null << 'EOF'
tunnel: selfvps-tunnel
credentials-file: /etc/cloudflared/<TUNNEL_ID>.json

protocol: http2

# 不公开仪表板
no-autoupdate: true

ingress:
  # 主站点
  - hostname: www.selfvps.net
    service: http://localhost:80

  # 博客子路径
  - hostname: blog.selfvps.net
    service: http://localhost:80

  # 管理面板（限制来源）
  - hostname: admin.selfvps.net
    service: http://localhost:8080
    originRequest:
      noTLSVerify: false
      originServerName: admin.selfvps.net

  # 默认返回 404
  - service: http_status:404
EOF
```

> **安全提示**：确保 `<TUNNEL_ID>.json` 文件权限严格限制：
> ```bash
> sudo chmod 600 /etc/cloudflared/<TUNNEL_ID>.json
> sudo chown root:root /etc/cloudflared/<TUNNEL_ID>.json
> ```

### 3. 使用 Cloudflare 原生 DNS 管理

如果你不想让 Cloudflared 修改 DNS 记录，可以在 Cloudflare 控制台手动添加 CNAME 记录。这是推荐的生产环境做法。

## 第四步：启动 Tunnel 服务

### 用 Systemd 运行（推荐）

```bash
# 创建 systemd 服务
sudo tee /etc/systemd/system/cloudflared.service > /dev/null << 'EOF'
[Unit]
Description=Cloudflare Tunnel
After=network-online.target
Wants=network-online.target

[Service]
Type=notify
ExecStart=/usr/local/bin/cloudflared --no-autoupdate tunnel --config /etc/cloudflared/config.yaml run
Restart=on-failure
RestartSec=5
KillMode=mixed

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now cloudflared
sudo systemctl status cloudflared
```

### 或者用 Docker 运行

```bash
docker run -d --name cloudflared-tunnel \
  --restart unless-stopped \
  -v /etc/cloudflared:/etc/cloudflared \
  cloudflare/cloudflared:latest \
  tunnel --no-autoupdate run
```

## 第五步：配置 Cloudflare 安全策略

### 1. 开启 WAF（Web Application Firewall）

在 Cloudflare 控制台进入 **Security → WAF**：

- 开启 **Super Bot Fight Mode**（免费）
- 针对关键页面设置自定义规则

```
# 示例：仅允许 API 路径使用指定 HTTP 方法
http.request.uri contains "/api" and not http.request.method in {"GET", "POST"} → Block

# 示例：对登录页面启用 Challenge
http.request.uri contains "/admin/login" → Challenge
```

### 2. 配置缓存规则

在 **Caching → Configuration** 中：

```
Cache Level: Basic
Cache Everything: 关闭（对动态内容）
Browser TTL: 2 hours
Edge TTL: 4 hours
```

对于静态资源：

```
Cache Rule:
Path: /*.{js,css,png,jpg,jpeg,gif,svg,ico,woff,woff2}
Cache Level: Cache Everything
Browser TTL: 1 month
Edge TTL: 1 week
Override Host: {origin}
```

### 3. 设置防火墙规则

**Security → WAF → Managed Headers** — 开启所有选项

**Security → WAF → Managed Filters** — 开启：
- Cloudflare Essential Rules
- Cloudflare OWASP Core Ruleset

### 4. 启用 Always Use HTTPS

在 **SSL/TLS → Overview** 中设置：

- Encryption mode: **Full**（因为 cloudflared 到 origin 是 HTTP）
- Always Use HTTPS: **开启**

## 第六步：进阶安全加固

### 1. 本地 Nginx 只监听 Loopback

```nginx
# 只监听 127.0.0.1，不接受外部直接连接
server {
    listen 127.0.0.1:80;
    server_name _;
    # ... 配置同上
}
```

```bash
sudo nginx -t && sudo systemctl reload nginx
```

### 2. 配置 UFW 防火墙

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw allow 7844/tcp  # cloudflared 出站（通常不需要）
sudo ufw enable
```

### 3. 启用 Cloudflare 访问规则

在 **Zero Trust → Access → Applications** 中：

1. 添加 **Private Application**
2. 输入子域名（如 `admin.selfvps.net`）
3. 设置 Access Policy：
   - **Require** → **One or more of these** → 指定邮箱域名
   - 或要求通过 **Cloudflare Access** 认证

这样只有授权人员才能访问管理面板。

### 4. 配置 Rate Limiting

```
# 每 10 秒最多 100 次请求
http.request.uri path eq "/" and http.request.method eq "GET"
Rate limit: 100 requests per 10 seconds
Action: Challenge
```

## 常见问题排查

### Tunnel 连接断开

```bash
# 查看 cloudflared 日志
journalctl -u cloudflared -f --no-pager

# 常见问题：
# 1. DNS 解析失败 → 检查网络
# 2. Token 过期 → 重新生成 tunnel token
# 3. 防火墙阻止 → 检查出站 7844/443 端口
```

### 502 Bad Gateway

通常表示 Nginx 未运行或配置错误：

```bash
sudo systemctl status nginx
sudo nginx -t
sudo journalctl -u nginx -n 50
```

### SSL 证书问题

Cloudflare 自动管理证书。如果证书不生效：

1. 检查 DNS 记录是否正确指向 Tunnel
2. SSL 模式应为 **Full**
3. 清除浏览器缓存后重试

## 监控与告警

### 使用 Health Checks

在 Cloudflare 控制台添加 Origin 健康检查：

- **URL**: `http://127.0.0.1:80/health`
- **Interval**: 60 秒
- **Timeout**: 10 秒

### 监控 cloudflared 运行状态

```bash
# 简单的 health check 脚本
cat > /usr/local/bin/check-tunnel.sh << 'EOF'
#!/bin/bash
if ! systemctl is-active --quiet cloudflared; then
    curl -s -X POST "https://hooks.slack.com/services/YOUR/WEBHOOK" \
        -d '{"text":"🚨 Cloudflared tunnel is DOWN!"}'
    sudo systemctl restart cloudflared
fi
EOF
chmod +x /usr/local/bin/check-tunnel.sh

# 加入 crontab，每分钟检查
(crontab -l 2>/dev/null; echo "* * * * * /usr/local/bin/check-tunnel.sh") | crontab -
```

## 总结

通过 Cloudflare Tunnel，你可以：

1. ✅ **零端口暴露** — 服务器上没有任何端口面向互联网开放
2. ✅ **自动 HTTPS** — Cloudflare 免费管理 SSL 证书
3. ✅ **CDN 加速** — 全球边缘缓存静态资源
4. ✅ **DDoS 防护** — Cloudflare 免费 CDN 层防护
5. ✅ **零信任访问** — 管理面板仅需授权用户可访问
6. ✅ **无需公网 IP** — 任何网络环境均可部署

这套方案特别适合：博客、文档站、管理面板、内部工具、CI/CD runner 等场景。

---

*这篇文章覆盖了从零开始到生产就绪的完整流程。如果你的场景有特殊需求（如 WebSocket 支持、负载均衡、多区域部署），欢迎在评论区讨论。*
