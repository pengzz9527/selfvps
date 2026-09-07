---
title: "VPS 无端口暴露：Cloudflare Tunnel 安全远程访问完整指南"
description: "告别端口映射和防火墙开放，用 Cloudflare Tunnel 为你的 VPS 服务提供零信任安全访问——无需公网 IP、无需 DDNS、HTTPS 自动加密，适合所有自托管爱好者"
date: 2026-09-07T10:00:00+08:00
lastmod: 2026-09-07T10:00:00+08:00
slug: "vps-cloudflare-tunnel-zero-trust"
image: /images/posts/vps-cloudflare-tunnel-zero-trust/featured.png
tags: ["Cloudflare", "Tunnel", "零信任", "安全访问", "自托管", "VPS", "无公网IP", "DDNS替代"]
categories: ["网络安全"]
aliases: [/zh/post/vps-cloudflare-tunnel-zero-trust/]
---

## 引言

你有一台 VPS，在上面跑着各种自托管服务——Nextcloud、Home Assistant、Pi-hole、Gitea……但你是否遇到过这些困扰？

- 为了让外网能访问，不得不把端口暴露在公网上，每天被扫描、被攻击；
- 没有公网 IP，只能用 DDNS + 端口转发，配置复杂且不稳定；
- SSL 证书管理麻烦，Let's Encrypt 续签时不时出问题；
- 想给服务加个访问控制，却发现没有现成的方案。

**Cloudflare Tunnel（原名 Argon Tunnel）** 完美解决了这些问题。它在你 VPS 上运行一个轻量级客户端 `cloudflared`，主动向外建立加密隧道连接到 Cloudflare 边缘节点。你的服务端口永远保持关闭，外界通过 `https://your-service.your-domain.com` 访问，全程 HTTPS 加密，且自带 Cloudflare 的 DDoS 防护和 WAF 能力。

本文将带你从零开始，完成 Cloudflare Tunnel 的完整配置，覆盖：基础安装、多服务配置、访问控制、集成 Zero Trust 面板、以及常见问题排查。

---

## 架构原理

```
┌─────────────────────────────────────────────────────────────────┐
│                        用户浏览器                               │
│                    https://app.your-domain.com                  │
└──────────────────────┬──────────────────────────────────────────┘
                       │ HTTPS (Cloudflare Edge)
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Cloudflare 边缘网络                           │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────────┐   │
│  │  DDoS    │  │   WAF    │  │  CDN     │  │  Access/Zero  │   │
│  │ 防护     │  │  防火墙  │  │  缓存    │  │   Trust       │   │
│  └──────────┘  └──────────┘  └──────────┘  └───────────────┘   │
└──────────────────────┬──────────────────────────────────────────┘
                       │ 加密隧道 (QUIC/TCP)
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│                    VPS 本地网络                                 │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │              cloudflared 客户端                          │    │
│  │  ┌───────────┐  ┌───────────┐  ┌───────────┐           │    │
│  │  │ Nextcloud │  │ HomeAssit │  │  Pi-hole  │           │    │
│  │  │ :8080     │  │ :8123     │  │ :53/443   │           │    │
│  │  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘           │    │
│  │        └───────────────┴───────────────┘                │    │
│  │                      本地路由                            │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
│  🔥 所有入站端口全部关闭！仅需出站连接                             │
└─────────────────────────────────────────────────────────────────┘
```

核心要点：
- **出站连接**：`cloudflared` 主动连接 Cloudflare，无需任何入站端口
- **零信任架构**：访问控制完全在 Cloudflare 侧管理，不暴露服务
- **自动 HTTPS**：Cloudflare 为你签发和管理证书
- **多服务路由**：一个 Tunnel 可路由多个本地服务

---

## 前置条件

1. **一个域名**：在 Cloudflare 注册并托管 DNS（免费套餐即可）
2. **一台 VPS**：Linux 系统（推荐 Debian 12 / Ubuntu 22.04+）
3. **Cloudflare 账号**：免费注册 https://dash.cloudflare.com
4. **基础 Linux 命令知识**

---

## 第一步：安装 cloudflared

### 方式一：官方 APT 仓库（推荐）

```bash
# Debian/Ubuntu
sudo apt install -y curl gnupg
curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg.key | sudo tee /usr/share/keyrings/cloudflare-main.gpg > /dev/null

echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflare-main debian main" | sudo tee /etc/apt/sources.list.d/cloudflare.list

sudo apt update && sudo apt install cloudflared
```

### 方式二：直接下载二进制

```bash
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
sudo mv cloudflared-linux-amd64 /usr/local/bin/cloudflared
sudo chmod +x /usr/local/bin/cloudflared
```

验证安装：

```bash
cloudflared --version
# cloudflared version 2024.x.x (built ...)
```

---

## 第二步：创建 Tunnel

### 2.1 登录 Cloudflare

```bash
cloudflared tunnel login
```

执行后会输出一个 URL，在浏览器中打开，选择域名并授权。授权成功后会在当前目录下生成 `cert.pem` 文件。

### 2.2 创建 Tunnel

```bash
# 创建 Tunnel（记录生成的 Tunnel ID）
cloudflared tunnel create vps-primary

# 输出示例：
# Tunnel credentials written to /root/.cloudflared/<TUNNEL_ID>.json
# Created tunnel vps-primary -> <TUNNEL_ID>
```

### 2.3 配置 DNS CNAME

```bash
cloudflared tunnel route dns vps-primary your-domain.com
```

这会在你的 DNS 中创建一条 CNAME 记录：`your-domain.com → <TUNNEL_ID>.cfargotunnel.com`

你也可以手动添加 DNS 记录：
- 类型：CNAME
- 名称：`@`（根域名）
- 目标：`<TUNNEL_ID>.cfargotunnel.com`

---

## 第三步：配置路由规则

编辑配置文件 `~/.cloudflared/config.yml`：

```yaml
# 基础配置
tunnel: <TUNNEL_ID>
credentials-file: /root/.cloudflared/<TUNNEL_ID>.json

# 日志
loglevel: info
logdir: /var/log/cloudflared

# 路由规则 - 将不同子域名路由到不同本地服务
ingress:
  # 主网站 / Nextcloud
  - hostname: app.your-domain.com
    service: http://localhost:8080

  # Home Assistant
  - hostname: home.your-domain.com
    service: http://localhost:8123

  # Pi-hole 管理界面
  - hostname: pihole.your-domain.com
    service: http://localhost:8081

  # Gitea Git 服务
  - hostname: git.your-domain.com
    service: http://localhost:3000

  # 默认返回 404
  - service: http_status:404
```

创建日志目录并设置权限：

```bash
sudo mkdir -p /var/log/cloudflared
sudo chown root:root /var/log/cloudflared
```

---

## 第四步：注册为系统服务

### 创建 systemd 服务单元

```bash
sudo tee /etc/systemd/system/cloudflared.service > /dev/null <<'EOF'
[Unit]
Description=Cloudflare Tunnel
After=network-online.target

[Service]
Type=notify
ExecStart=/usr/local/bin/cloudflared tunnel --no-autoupdate run vps-primary
Environment="CF_TUNNEL_METRICS=localhost:2000"
Restart=on-failure
RestartSec=10
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF
```

启动并设置开机自启：

```bash
sudo systemctl daemon-reload
sudo systemctl enable cloudflared
sudo systemctl start cloudflared

# 检查状态
sudo systemctl status cloudflared
```

预期输出：
```
● cloudflared.service - Cloudflare Tunnel
   Active: active (running) since Mon 2026-09-07 10:00:00 +08; 5s ago
 Main PID: 1234 (cloudflared)
    Tasks: 10 (limit: 4915)
   Memory: 25.0M
```

### 查看 Tunnel 状态

```bash
cloudflared tunnel list
cloudflared tunnel info vps-primary
```

---

## 第五步：配置访问控制（可选但推荐）

### 5.1 使用 Cloudflare Access（零信任）

访问 https://one.dash.cloudflare.com，进入 **Access → Applications**：

1. 点击 **Add an application**
2. 选择 **Self-hosted**
3. 设置 Application domain：`app.your-domain.com`
4. 选择 Policy，例如：
   - **Block all**（完全阻止）
   - **Allow email domains**（仅允许特定邮箱后缀）
   - **Allow specific emails**（仅允许指定邮箱）

### 5.2 简单密码保护（无需 Cloudflare Access）

如果只需要简单密码保护，可以在服务前加一个反向代理：

```nginx
# Nginx 反向代理 + 基础认证
server {
    listen 8080;
    server_name app.your-domain.com;

    location / {
        proxy_pass http://localhost:8080;  # 你的实际服务
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;

        # 基础认证
        auth_basic "Restricted Access";
        auth_basic_user_file /etc/nginx/.htpasswd;
    }
}
```

生成 htpasswd 文件：

```bash
sudo apt install apache2-utils
sudo htpasswd -c /etc/nginx/.htpasswd admin
```

### 5.3 IP 白名单（最简单）

在 `config.yml` 的 ingress 规则中无法直接做 IP 过滤，但你可以在本地服务前加一个简单的 IP 限制：

```bash
# 使用 iptables 仅允许你的 IP 访问本地端口
sudo iptables -A INPUT -p tcp --dport 8080 -s YOUR_IP/32 -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 8080 -j DROP
```

---

## 第六步：健康检查与监控

### 6.1 内置监控端点

Cloudflare Tunnel 自带 HTTP 监控端点：

```bash
# 查看隧道状态
curl http://localhost:2000/ready
curl http://localhost:2000/status

# 查看连接指标
curl http://localhost:2000/metrics
```

### 6.2 集成 Prometheus + Grafana

如果你的 VPS 已有 Prometheus，可以添加 cloudflared 的 metrics：

```yaml
# prometheus.yml 追加
scrape_configs:
  - job_name: 'cloudflared'
    static_configs:
      - targets: ['localhost:2000']
```

Grafana Dashboard ID：`19397`（Cloudflare Tunnel 官方仪表板）

### 6.3 健康检查告警

```bash
# 简单的监控脚本
#!/bin/bash
# /usr/local/bin/check-tunnel.sh

STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:2000/ready)

if [ "$STATUS" != "200" ]; then
    echo "Cloudflare Tunnel 不健康！状态码: $STATUS"
    # 发送告警（钉钉/Telegram/邮件）
    curl -X POST "https://api.telegram.org/bot<TOKEN>/sendMessage" \
         -d "chat_id=<CHAT_ID>" \
         -d "text=🚨 Cloudflare Tunnel 异常！"
fi
```

添加到 crontab 每分钟检查：

```bash
* * * * * /usr/local/bin/check-tunnel.sh
```

---

## 第七步：多 Tunnel 高可用配置

对于生产环境，建议在多台 VPS 上运行 Tunnel 实现冗余：

```bash
# 在第二台 VPS 上同样安装 cloudflared
# 使用相同的 Tunnel ID 运行
cloudflared tunnel --no-autoupdate run vps-primary
```

Cloudflare 会自动在多个 Tunnel 端点之间做负载均衡。如果一台 VPS 宕机，另一台自动接管。

你还可以通过 `--url` 参数指定备用路由：

```bash
cloudflared tunnel run vps-primary --url https://your-backup-service.com
```

---

## 常见问题排查

### 问题 1：Tunnel 连接不稳定

```bash
# 查看详细日志
sudo journalctl -u cloudflared -f

# 检查网络连接
curl -I https://region1.tunnel.cfargotunnel.com
```

如果是国内 VPS，可能需要配置代理或使用 China-region 端点：
```bash
cloudflared tunnel --region cn run vps-primary
```

### 问题 2：DNS 解析失败

```bash
# 检查 CNAME 是否正确
dig your-domain.com CNAME
# 应返回: your-domain.com. CNAME <TUNNEL_ID>.cfargotunnel.com.

# 清除本地 DNS 缓存
sudo systemd-resolve --flush-caches
```

### 问题 3：服务返回 502/503

检查 `config.yml` 中的 ingress 路由是否正确指向本地服务：

```bash
# 确认本地服务正在运行
curl http://localhost:8080
curl http://localhost:8123

# 检查 cloudflared 日志
sudo journalctl -u cloudflared -n 50
```

常见原因：本地服务未启动、端口配置错误、防火墙阻止了本地回环。

### 问题 4：证书问题

Cloudflare Tunnel 自动管理证书，通常不需要手动处理。如果遇到证书错误：

```bash
# 重新登录获取证书
cloudflared tunnel login
# 重启服务
sudo systemctl restart cloudflared
```

---

## 成本分析

| 项目 | 费用 |
|------|------|
| Cloudflare 免费套餐 | ¥0/月（含 Tunnel 功能） |
| 域名（如有） | ~¥60/年 |
| VPS | 已有 |
| **总计** | **≈ ¥0/月（除域名外）** |

相比传统方案：
- 无需公网 IP（节省 ¥50-200/月）
- 无需 DDNS 服务（节省 ¥0-30/月）
- 无需手动管理 SSL 证书（节省时间）
- 自带 DDoS 防护（价值 ¥100+/月）

---

## 总结

Cloudflare Tunnel 是自托管爱好者的必备工具：

1. **零端口暴露**：所有服务端口保持关闭，极大减少攻击面
2. **自动 HTTPS**：无需手动配置 Let's Encrypt
3. **免费可用**：Cloudflare 免费套餐完全支持
4. **企业级安全**：DDoS 防护 + WAF + 可选的 Zero Trust 访问控制
5. **简单易用**：一条命令即可运行

现在就去配置你的第一个 Tunnel 吧！你的 VPS 会感谢你的。

---

## 参考资料

- [Cloudflare Tunnel 官方文档](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/)
- [cloudflared GitHub](https://github.com/cloudflare/cloudflared)
- [Cloudflare Zero Trust](https://one.dash.cloudflare.com)
