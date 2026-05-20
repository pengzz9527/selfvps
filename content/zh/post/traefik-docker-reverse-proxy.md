---
title: "Traefik + Docker：自托管服务的终极反向代理方案"
description: "完整指南：使用 Traefik 作为 Docker 反向代理 — 自动 SSL 证书、中间件链、限流、生产级安全配置，让你的 VPS 管理多个服务变得前所未有的简单"
date: 2026-05-20T10:00:00+08:00
slug: "traefik-docker-reverse-proxy"
tags: ["Traefik", "Docker", "反向代理", "SSL", "Let's Encrypt", "VPS", "网络"]
categories: ["DevOps", "自托管基础设施"]
aliases: [/zh/post/traefik-docker-reverse-proxy/]
draft: false
---

如果你在一台 VPS 上自托管多个服务——比如 Nextcloud、n8n、Vaultwarden 和个人博客——你一定需要一个反向代理。**Traefik** 是基于 Docker 部署的金标准方案：它能自动发现运行中的容器，自动申请 Let's Encrypt TLS 证书，零配置即可完成流量路由。

本文你将学会：

- 使用 Docker Compose 部署 Traefik v3
- 配置 Let's Encrypt 自动 HTTPS（HTTP-01 + TLS-ALPN-01）
- 使用 Docker labels 实现零配置路由
- 链式组合中间件实现限流、压缩、IP 白名单
- 用 HTTP Basic Auth 保护管理面板
- 生产环境安全加固 Traefik

## 为什么选 Traefik 而不是 Nginx 或 Caddy？

| 特性 | Traefik | Nginx Proxy Manager | Caddy |
|---|---|---|---|
| 自动服务发现 | ✅ 原生 Docker API | ❌ 手动 | ❌ 手动 |
| 自动 SSL + 续期 | ✅（原生） | ✅（界面） | ✅（原生） |
| 动态配置免重启 | ✅ | ❌ | ✅ |
| 中间件链 | ✅ 丰富的生态 | ⚠️ 有限 | ✅ 基础 |
| Kubernetes 支持 | ✅ | ❌ | ❌ |
| Prometheus 指标 | ✅ | ❌ | ⚠️ 需插件 |

如果你在 VPS 上运行 5 个以上 Docker 服务，并且经常增删，Traefik 的自动发现能力能为你节省大量时间。

## 第一步：目录结构

创建专门的 Traefik 目录：

```bash
mkdir -p /opt/traefik
cd /opt/traefik
mkdir -p data config
touch data/acme.json
chmod 600 data/acme.json
```

`acme.json` 存储 Let's Encrypt 证书——`chmod 600` 是必需的，否则 Traefik 会拒绝启动。

## 第二步：Docker Compose 配置

创建 `/opt/traefik/docker-compose.yml`：

```yaml
services:
  traefik:
    image: traefik:v3.2
    container_name: traefik
    restart: unless-stopped
    security_opt:
      - no-new-privileges:true
    networks:
      - proxy
    ports:
      - "80:80"
      - "443:443"
    environment:
      - CF_API_EMAIL=${CF_API_EMAIL}
      - CF_DNS_API_TOKEN=${CF_DNS_API_TOKEN}
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - ./data/acme.json:/acme.json
      - ./config:/config
      - ./data/logs:/var/log/traefik
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.traefik.entrypoints=websecure"
      - "traefik.http.routers.traefik.rule=Host(`traefik.yourdomain.com`)"
      - "traefik.http.routers.traefik.tls.certresolver=letsencrypt"
      - "traefik.http.routers.traefik.service=api@internal"
      # 管理面板 Basic Auth
      - "traefik.http.routers.traefik.middlewares=auth"
      - "traefik.http.middlewares.auth.basicauth.users=${TRAEFIK_ADMIN_USER}:${TRAEFIK_ADMIN_PASSWORD_HASH}"

networks:
  proxy:
    external: true
```

> **重要：** 先创建 proxy 网络：`docker network create proxy`

## 第三步：静态配置文件（traefik.yml）

创建 `config/traefik.yml`：

```yaml
api:
  dashboard: true
  debug: false

entryPoints:
  web:
    address: ":80"
    http:
      redirections:
        entryPoint:
          to: websecure
          scheme: https
          permanent: true
  websecure:
    address: ":443"

providers:
  docker:
    endpoint: "unix:///var/run/docker.sock"
    exposedByDefault: false
    watch: true
  file:
    directory: /config
    watch: true

certificatesResolvers:
  letsencrypt:
    acme:
      email: youremail@example.com
      storage: /acme.json
      # 使用 DNS-01 挑战以支持通配符证书
      # dnsChallenge:
      #   provider: cloudflare
      #   resolvers:
      #     - "1.1.1.1:53"
      #     - "8.8.8.8:53"
      httpChallenge:
        entryPoint: web

log:
  level: INFO
  filePath: /var/log/traefik/traefik.log

accessLog:
  filePath: /var/log/traefik/access.log
  bufferingSize: 100
  format: json
```

## 第四步：环境变量文件

创建 `.env`：

```bash
CF_API_EMAIL=youremail@example.com
CF_DNS_API_TOKEN=你的_cloudflare_token
TRAEFIK_ADMIN_USER=admin
# 用以下命令生成：$(htpasswd -nb admin securepassword)
TRAEFIK_ADMIN_PASSWORD_HASH=admin:$2y$05$xxx...
```

生成密码哈希：

```bash
apt install apache2-utils -y
htpasswd -nb admin "你的强密码"
```

将输出复制到 `.env` 文件中。

## 第五步：动态文件配置（中间件）

创建 `config/middlewares.yml`：

```yaml
http:
  middlewares:
    # 限流 — 每 IP 每分钟 100 次请求
    rate-limit:
      rateLimit:
        average: 100
        burst: 50
        period: 1m
        sourceCriterion:
          ipStrategy:
            depth: 1

    # 安全响应头
    sec-headers:
      headers:
        frameDeny: true
        sslRedirect: true
        browserXssFilter: true
        contentTypeNosniff: true
        forceSTSHeader: true
        stsIncludeSubdomains: true
        stsPreload: true
        stsSeconds: 31536000
        customFrameOptionsValue: "SAMEORIGIN"
        referrerPolicy: "strict-origin-when-cross-origin"
        permissionsPolicy: "camera=(), microphone=(), geolocation=()"

    # IP 白名单（管理员专用服务）
    whitelist:
      ipWhiteList:
        sourceRange:
          - "10.0.0.0/8"
          - "192.168.0.0/16"
          - "你的家庭IP/32"
          - "100.64.0.0/10"

    # Gzip 压缩
    compress:
      compress:
        excludedContentTypes:
          - "text/event-stream"
          - "image/webp"
          - "image/png"

    # CORS（用于 n8n 等 API 服务）
    cors:
      headers:
        accessControlAllowMethods:
          - "GET"
          - "POST"
          - "PUT"
          - "DELETE"
          - "OPTIONS"
        accessControlAllowOriginList:
          - "*"
        accessControlMaxAge: 100
        accessControlAllowCredentials: true
        addVaryHeader: true
```

## 第六步：启动 Traefik

```bash
docker compose up -d
# 查看日志
docker compose logs -f
```

如果一切配置正确，你应该能看到：

```
time="..." level=info msg="Configuration loaded from provider: docker"
time="..." level=info msg="Starting provider aggregator ..."
```

访问 `https://traefik.yourdomain.com` 查看管理面板。

## 第七步：使用 Docker Labels 路由服务

将任何 Docker 服务通过 Traefik 暴露出去，无需修改任何配置文件。以 n8n 为例：

```yaml
services:
  n8n:
    image: n8nio/n8n:latest
    networks:
      - proxy  # <-- 和 Traefik 在同一网络
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.n8n.rule=Host(`n8n.yourdomain.com`)"
      - "traefik.http.routers.n8n.entrypoints=websecure"
      - "traefik.http.routers.n8n.tls.certresolver=letsencrypt"
      - "traefik.http.services.n8n.loadbalancer.server.port=5678"
      # 中间件链
      - "traefik.http.routers.n8n.middlewares=rate-limit,sec-headers,compress@file"
```

就这样。运行 `docker compose up -d` 启动 n8n，Traefik 会自动：

1. 通过 Docker API 检测新容器
2. 生成路由规则
3. 从 Let's Encrypt 获取 SSL 证书
4. 应用中间件链
5. 开始服务 HTTPS 流量——无需重启 Traefik

## 第八步：生产环境安全加固清单

在将 Traefik 暴露到公网之前：

- [ ] **使用 DNS-01 挑战** 替代 HTTP-01——支持通配符证书（`*.yourdomain.com`），且不需要 80 端口直接可达
- [ ] **启用 fail2ban** 保护 SSH 和 Traefik 访问日志：
  ```bash
  # /etc/fail2ban/jail.local
  [traefik]
  enabled = true
  port = http,https
  filter = traefik
  logpath = /opt/traefik/data/logs/access.log
  maxretry = 20
  findtime = 600
  bantime = 3600
  ```
- [ ] **限制 Docker socket 权限**——以只读方式挂载（`:ro`），切勿暴露给不受信任的容器
- [ ] **对所有路由设置限流**（使用上面配置的 `rate-limit` 中间件）
- [ ] **启用 Prometheus 指标** 用于监控：
  ```yaml
  metrics:
    prometheus:
      addEntryPointsLabels: true
      addServicesLabels: true
      entryPoint: metrics
  ```
- [ ] **使用环境变量** 存储密钥（`.env` 文件），绝不硬编码
- [ ] **保持 Traefik 更新**：`docker compose pull && docker compose up -d`
- [ ] **配置日志轮转** 防止磁盘溢出：
  ```yaml
  log:
    filePath: /var/log/traefik/traefik.log
    format: json
    level: WARN  # 调试用 INFO，生产用 WARN
  ```

## 实战案例：$10 VPS 上的完整堆栈

在一台 10 美元/月的 VPS 上，Traefik 背后可以运行所有这些服务：

| 服务 | 域名 | 配置方式 |
|---|---|---|
| Nextcloud | cloud.yourdomain.com | 在 Nextcloud 容器加 labels |
| Vaultwarden | vault.yourdomain.com | 在 Vaultwarden 容器加 labels |
| n8n | n8n.yourdomain.com | 在 n8n 容器加 labels |
| Grafana | grafana.yourdomain.com | 在 Grafana 容器加 labels |
| Traefik 面板 | traefik.yourdomain.com | 在 Traefik 自身加 labels |

全部运行在一台 2 vCPU / 2 GB RAM 的 VPS 上。每个服务独立隔离在各自容器中，Traefik 统一管理 SSL 和路由，增删服务只需一条 `docker compose up -d`。

## 常见问题排查

**"404 page not found"** → 容器不在 `proxy` 网络里。给服务加上 `networks: [proxy]`。

**"Certificate is not valid for hostname"** → `Host()` 规则与实际域名不匹配，或者 DNS 尚未传播。

**Traefik 因 acme.json 权限无法启动** → 运行 `chmod 600 data/acme.json`。这是最常见的坑。

**"dial tcp 127.0.0.1:xxxx: connect: connection refused"** → 服务没有在你指定的端口上监听。检查容器的内部端口。

**限流太严格** → 调整中间件中的 `average` 和 `burst` 值。普通 Web 应用建议从 200/100 开始尝试。

## 总结

Traefik 彻底改变了管理自托管服务的方式。自动 SSL 证书管理、基于 Docker labels 的零配置服务发现、丰富的中间件生态——这些特性的组合使它成为在 VPS 上运行多个服务的最佳反向代理。

初次配置只需 15 分钟。但在服务器的整个生命周期中——每次你添加、删除或更新一个服务——节省的时间会不断累积。无论你运行 3 个还是 30 个服务，Traefik 都是让整个堆栈变得可控的基础。

**下一步：** 添加 Prometheus + Grafana 监控 Traefik 指标，设置 `acme.json` 的自动备份，通过 Traefik Pilot 插件生态探索 IP 白名单和机器人检测等高级功能。
