---
title: "Cloudflare Tunnel 零端口转发：免公网IP内网服务暴露指南"
description: "无需开放防火墙端口、无需公网IP，使用 Cloudflare Tunnel 将内网服务安全暴露到互联网。完整教程涵盖 Zero Trust 模式、Warp 客户端、自动证书和多服务路由。"
date: 2026-06-22T10:00:00+08:00
lastmod: 2026-06-22T10:00:00+08:00
slug: "cloudflare-tunnel-zero-port-forwarding"
tags: ["Cloudflare", "Tunnel", "零信任", "反向代理", "无公网IP", "Docker", "网络安全", "自托管"]
categories: ["网络架构"]
draft: false
image: /images/posts/cloudflare-tunnel-zero-port-forwarding/featured.png
aliases: [/zh/post/cloudflare-tunnel-zero-port-forwarding/]
---

## 为什么需要 Cloudflare Tunnel？

对于自托管爱好者而言，一个常见痛点是：**如何从外网访问家里的 NAS、Home Assistant、或者 VPS 上的私有服务？**

传统方案通常是：

- **端口转发（Port Forwarding）**：需要在路由器上开放端口，暴露你的公网 IP，安全风险高
- **DDNS + 端口映射**：动态 DNS 配合端口转发，但仍需暴露服务端口
- **FRP / Ngrok**：需要自建中转服务器或依赖第三方，延迟高且存在单点故障

**Cloudflare Tunnel** 提供了一个全新的思路：**不需要开放任何端口，不需要公网 IP，所有流量通过 Cloudflare 的安全网络进行隧道传输**。

## 核心原理

Cloudflare Tunnel 的工作方式与传统反向代理截然不同：

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   用户浏览器  │────▶│  Cloudflare CDN  │────▶│  Cloudflared    │
│             │     │  (全球边缘节点)    │     │  (你的服务器上)  │
└─────────────┘     └──────────────────┘     └────────┬────────┘
                                                       │
                                                       ▼
                                              ┌─────────────────┐
                                              │  内网服务 (本地)  │
                                              │  :8080 / :3000  │
                                              └─────────────────┘
```

关键区别：
- **出站连接**：`cloudflared` 主动建立到 Cloudflare 边缘的加密隧道（ outbound-only ）
- **无需入站规则**：防火墙不需要开放任何端口
- **DDoS 防护**：流量先经过 Cloudflare 全球网络清洗
- **自动 HTTPS**：免费 SSL 证书，Cloudflare 自动管理

## 前置条件

1. **一个域名**：在 Cloudflare 上注册或转移域名（免费计划即可）
2. **一台服务器**：可以是 VPS、树莓派、NAS 等任意能运行 Docker 的设备
3. **Docker 环境**：推荐使用 Docker Compose 管理

## 方案一：Zero Trust Dashboard（推荐）

这是 Cloudflare 官方推荐的现代方式，通过 Zero Trust 面板管理所有隧道。

### 步骤 1：创建 Zero Trust 组织

1. 访问 [one.cloudflare.com](https://one.cloudflare.com)
2. 登录你的 Cloudflare 账号
3. 点击 **"Start free trial"** 创建 Zero Trust 组织（免费计划足够）

### 步骤 2：创建隧道

```bash
# 安装 cloudflared CLI
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o cloudflared
chmod +x cloudflared
sudo mv cloudflared /usr/local/bin/

# 认证（会打开浏览器让你登录）
cloudflared tunnel login
```

执行 `cloudflared tunnel login` 后，浏览器会弹出 Cloudflare 授权页面，授权后会在当前目录下生成一个 `cert.pem` 文件。

### 步骤 3：创建隧道并获取 Tunnel ID

```bash
# 创建名为 selfvps-tunnel 的隧道
cloudflared tunnel create selfvps-tunnel

# 输出类似：
# Created tunnel selfvps-tunnel with id abc12345-def6-7890-ghij-klmnopqrstuv
```

记下输出的 Tunnel ID（如 `abc12345-def6-7890-ghij-klmnopqrstuv`）。

### 步骤 4：配置路由规则

创建配置文件 `~/.cloudflared/config.yml`：

```yaml
tunnel: abc12345-def6-7890-ghij-klmnopqrstuv
credentials-file: /root/.cloudflared/abc12345-def6-7890-ghij-klmnopqrstuv.json

# 路由规则：将域名解析到隧道
ingress:
  # Home Assistant
  - hostname: ha.selfvps.net
    service: http://localhost:8123
  
  # 你的博客
  - hostname: blog.selfvps.net
    service: http://localhost:1313
  
  # NAS Web 界面
  - hostname: nas.selfvps.net
    service: http://localhost:5000
  
  # 默认规则：404
  - service: http_status:404
```

### 步骤 5：注册隧道并启动

```bash
# 注册隧道到 Cloudflare
cloudflared tunnel route dns selfvps-tunnel ha.selfvps.net
cloudflared tunnel route dns selfvps-tunnel blog.selfvps.net
cloudflared tunnel route dns selfvps-tunnel nas.selfvps.net

# 启动隧道
cloudflared tunnel run selfvps-tunnel
```

### 步骤 6：设置为系统服务

创建 `/etc/systemd/system/cloudflared.service`：

```ini
[Unit]
Description=Cloudflare Tunnel
After=network.target

[Service]
Type=exec
ExecStart=/usr/local/bin/cloudflared tunnel --config /root/.cloudflared/config.yml run selfvps-tunnel
Restart=on-failure
RestartSec=5
Environment=NO_UPDATE_NOTIFIER=1

[Install]
WantedBy=multi-user.target
```

启用并启动：

```bash
sudo systemctl daemon-reload
sudo systemctl enable cloudflared
sudo systemctl start cloudflared
sudo systemctl status cloudflared
```

## 方案二：Docker Compose 一键部署

更适合不想手动管理 systemd 的用户。

### 创建 docker-compose.yml

```yaml
version: "3.8"

services:
  cloudflared:
    image: cloudflare/cloudflared:latest
    container_name: cloudflared
    restart: unless-stopped
    command: tunnel --no-autoupdate run --token TOKEN_HERE
    networks:
      - tunnel-net

  # 示例：Home Assistant
  homeassistant:
    image: ghcr.io/home-assistant/home-assistant:stable
    container_name: homeassistant
    restart: unless-stopped
    network_mode: service:cloudflared  # 注意：这需要特殊配置
    volumes:
      - ./homeassistant:/config
    # 实际上更推荐用下面的方式

networks:
  tunnel-net:
    driver: bridge
```

### 更实用的 Docker 方案（使用配置挂载）

```yaml
version: "3.8"

services:
  cloudflared:
    image: cloudflare/cloudflared:latest
    container_name: cloudflared
    restart: unless-stopped
    volumes:
      - ./cloudflared-config:/etc/cloudflared
      - cloudflared-certs:/root/.cloudflared
    command: tunnel --config /etc/cloudflared/config.yml run
    # 如果已有 token，可以用更简洁的方式：
    # command: tunnel --no-autoupdate run --token $(cat /etc/cloudflared/token.txt)

  # 其他服务保持在各自的 network 中
  homepage:
    image: ghcr.io/gethomepage/homepage:latest
    container_name: homepage
    restart: unless-stopped
    ports:
      - "3000:3000"
    volumes:
      - ./homepage/config:/app/config

networks:
  default:
    driver: bridge
```

### 使用 Token 模式的简化方案

如果你已经通过 Zero Trust Dashboard 创建了隧道，可以使用 token 模式，无需维护配置文件：

```bash
# 在 Zero Trust Dashboard 的 Tunnels 页面获取 token
# 然后：
docker run -d \
  --name cloudflared \
  --restart unless-stopped \
  cloudflare/cloudflared:latest \
  tunnel --no-autoupdate run --token YOUR_TOKEN_HERE
```

Token 模式的缺点是**所有路由规则必须在 Zero Trust Dashboard 的网页界面中配置**，不如本地配置文件灵活。

## 方案三：Zero Trust Dashboard 网页配置

适合不想碰命令行的用户。

1. 登录 [one.cloudflare.com](https://one.cloudflare.com)
2. 进入 **Networks → Tunnels**
3. 点击 **Create a tunnel**
4. 选择 **Cloudflared** 作为 connector
5. 按照提示在你的服务器上运行安装命令
6. 在网页上配置 Public Hostname 和 Service URL

Dashboard 配置界面：
- **Public Hostname**：输入子域名（如 `app.selfvps.net`）
- **Subdomain**：选择域名
- **Domain**：选择你的主域名
- **Service Type**：选择 `http` 或 `https`
- **Service URL**：填写内网地址（如 `localhost:3000`）

## 进阶配置

### 添加基本认证（Basic Auth）

保护你的服务不被未授权访问：

```yaml
ingress:
  - hostname: secure.selfvps.net
    service: http://localhost:8080
    originRequest:
      noTLSVerify: true
```

然后在 Zero Trust Dashboard 中：
1. 进入 **Access → Applications**
2. 点击 **Add an application**
3. 选择 **Self-hosted**
4. 配置 **Application domain** 为你的子域名
5. 设置 **Policy**：可以选择邮件认证、OAuth 等

### 启用 WAF 规则

Cloudflare Tunnel 自带 Web 应用防火墙：

1. 进入 **Security → WAF**
2. 为你的域名添加自定义规则
3. 例如阻止特定 IP 段、限制请求频率等

### 多区域部署（高可用）

```yaml
# 在多台服务器上运行相同的 cloudflared
# Zero Trust Dashboard 会自动负载均衡
cloudflared tunnel run selfvps-tunnel
```

当一台服务器的 cloudflared 下线，流量会自动路由到其他健康的 connector。

### 监控隧道状态

```bash
# 查看隧道状态
cloudflared tunnel info selfvps-tunnel

# 查看路由
cloudflared tunnel list-routes selfvps-tunnel

# 查看日志
journalctl -u cloudflared -f
```

## 安全最佳实践

| 实践 | 说明 |
|------|------|
| **最小权限原则** | 只暴露必要的服务，不要暴露管理面板 |
| **启用 Access Policy** | 为敏感服务添加身份验证 |
| **定期轮换 Token** | 每 90 天更新一次隧道凭证 |
| **使用独立域名** | 不要用主域名直接暴露内部服务 |
| **启用 DDoS 防护** | Cloudflare 免费计划已包含基础防护 |
| **监控异常流量** | 在 Zero Trust Dashboard 查看流量日志 |

## 常见问题

### Q: Tunnel 断连了怎么办？

检查 cloudflared 进程状态：
```bash
sudo systemctl status cloudflared
sudo journalctl -u cloudflared -n 50 --no-pager
```

常见原因：
- 服务器重启后服务未自动启动
- 网络连接不稳定导致隧道断开
- 凭证文件过期或被删除

### Q: 可以不用 Cloudflare 域名吗？

不可以。Cloudflare Tunnel 要求域名必须在 Cloudflare 的 DNS 上解析。如果你的域名在其他服务商处，需要修改 Nameserver 为 Cloudflare 的 NS。

### Q: 性能如何？

- 延迟增加约 10-50ms（取决于你到 Cloudflare 边缘的距离）
- 吞吐量受 Cloudflare 免费计划的限制（100Gbps 共享带宽）
- 对于大多数自托管场景完全够用

### Q: 免费计划有什么限制？

- 无限隧道数量
- 无限带宽（但有公平使用策略）
- 所有安全功能可用
- 不支持自定义 SSL 证书上传（使用 Cloudflare 提供的证书）

## 总结

Cloudflare Tunnel 是自托管场景下**最优雅的内网暴露方案**：

- ✅ **零端口开放**：无需配置防火墙规则
- ✅ **免费**：Cloudflare 免费计划完全够用
- ✅ **安全**：内置 DDoS 防护、WAF、自动 HTTPS
- ✅ **简单**：几分钟即可完成部署
- ✅ **可靠**：全球边缘网络，高可用性

对于任何想要安全暴露内网服务的自托管用户来说，Cloudflare Tunnel 都是首选方案。

---

**相关文章推荐：**
- [Headscale 自建 Tailscale 控制平面](/zh/post/headscale-self-hosted-tailscale/)
- [VPS 监控：Prometheus + Grafana 完整部署](/zh/post/vps-monitoring-prometheus-grafana/)
- [Vaultwarden 密码管理器部署指南](/zh/post/vaultwarden-deployment-guide/)
