---
title: "Caddy v2 + Docker：自托管服务最轻松的反向代理，自动 HTTPS 一把梭"
description: "手把手教你用 Caddy v2 + Docker 搭建反向代理，自动 Let's Encrypt TLS 证书、泛域名证书、多服务部署，一台 VPS 搞定所有自托管应用的入口。"
date: 2026-05-21T10:00:00+08:00
slug: "caddy-docker-reverse-proxy"
tags: ["Caddy", "反向代理", "Docker", "HTTPS", "Let's Encrypt", "自托管", "VPS", "泛域名证书"]
categories: ["DevOps", "Web 服务器"]
aliases: [/zh/post/caddy-docker-reverse-proxy/]
draft: false
---

如果你在一台 VPS 上跑了多个自托管服务，你一定需要一个反向代理。Nginx 功能强大但配置语法折磨人；Traefik 很聪明但动态配置模型有学习门槛。**Caddy v2** 恰好踩在最舒服的位置：开箱即用、HTTPS 全自动、Caddyfile 一眼就能看懂。

本文你将学会：

- 用 Docker Compose 搭建 Caddy v2
- 自动配置 Let's Encrypt TLS（含 DNS 验证泛域名证书）
- 在单个 Caddy 实例后面代理多个自托管服务
- 启用实时日志、安全头和基础认证
- 用 Caddy API 做动态配置

## 为什么选 Caddy？

| 特性 | Caddy v2 | Traefik | Nginx |
|---|---|---|---|
| 自动 HTTPS | ✅ 内置，零配置 | ✅ 自动 | ❌ 需 certbot |
| 配置格式 | Caddyfile（简单易懂） | TOML/YAML 标签 | 复杂的 `.conf` 文件 |
| Docker 标签 | ✅ 通过 `caddy-docker-proxy` | ✅ 原生 | ❌ 需第三方工具 |
| 泛域名证书 | ✅ 一行 DNS 验证搞定 | ✅ 支持 | ❌ certbot + cron |
| 内存占用 | ~15 MB | ~30-50 MB | ~5-10 MB |

Caddy 非常适合中小规模的自托管场景——你想要 HTTPS "免费赠送"，又不想写 50 行 Nginx 配置。

## 第一步：基础 Caddy + Docker Compose 搭建

创建目录和 `docker-compose.yml`：

```yaml
version: "3.8"

services:
  caddy:
    image: caddy:2-alpine
    container_name: caddy
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
      - caddy_config:/config
    restart: unless-stopped
    networks:
      - caddy_net

volumes:
  caddy_data:
  caddy_config:

networks:
  caddy_net:
    name: caddy_net
    external: false
```

创建最小 `Caddyfile`：

```caddy
# 全局选项
{
    email your@email.com  # Let's Encrypt 账户邮箱
    admin off             # 生产环境关闭管理 API
}

# 默认兜底：显示静态页面
:80 {
    respond "Caddy is running!"
}
```

启动：

```bash
docker compose up -d
```

Caddy 会自动为指向它的任何域名申请 HTTP-01 验证的 Let's Encrypt 证书。

## 第二步：代理一个真实服务

假设同一个 Docker 网络上跑着一个 **Vaultwarden** 实例。

在 `docker-compose.yml` 中添加服务：

```yaml
  vaultwarden:
    image: vaultwarden/server:latest
    container_name: vaultwarden
    volumes:
      - ./vw-data:/data
    restart: unless-stopped
    networks:
      - caddy_net
    expose:
      - "80"
```

然后在 `Caddyfile` 中更新：

```caddy
vault.yourdomain.com {
    reverse_proxy vaultwarden:80
}
```

Caddy 自动检测 `vault.yourdomain.com`，申请 Let's Encrypt 证书，将流量代理到 `vaultwarden` 容器。只需两行——就这么简单。

## 第三步：DNS 验证泛域名证书

如果你有很多子域名——`nextcloud.yourdomain.com`、`n8n.yourdomain.com`、`grafana.yourdomain.com`——通常每个子域名需要一张证书。有了泛域名证书，一张证书覆盖 `*.yourdomain.com` 所有子域名。

这需要 DNS 挑战，即 Caddy 需要访问你的 DNS 提供商 API。Caddy 内置支持 40+ 种 DNS 提供商。

### 示例：Cloudflare

```caddy
{
    email your@email.com
}

*.yourdomain.com, yourdomain.com {
    tls {
        dns cloudflare YOUR_CLOUDFLARE_API_TOKEN
    }

    @nextcloud host nextcloud.yourdomain.com
    handle @nextcloud {
        reverse_proxy nextcloud:80
    }

    @n8n host n8n.yourdomain.com
    handle @n8n {
        reverse_proxy n8n:80
    }

    @grafana host grafana.yourdomain.com
    handle @grafana {
        reverse_proxy grafana:3000
    }

    # 默认：404
    respond 404
}
```

要点：
- 在 Caddy 容器中设置 `CLOUDFLARE_API_TOKEN` 环境变量
- 泛域名证书覆盖所有 `*.yourdomain.com` 子域名
- `handle` 指令按主机名路由——比单独写 site block 更清爽

## 第四步：安全头与中间件

Caddy 添加安全头极其简单：

```caddy
vault.yourdomain.com {
    # 安全头
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
        Referrer-Policy "strict-origin-when-cross-origin"
        Permissions-Policy "geolocation=(), microphone=(), camera=()"
    }

    # 限速（每秒 10 请求，突发 20）
    rate_limit {
        zone dynamic {
            key {remote_host}
            events 20
            window 1s
        }
    }

    reverse_proxy vaultwarden:80
}
```

## 第五步：为内部工具添加基础认证

需要给内部分析面板加个锁？

```caddy
internal.yourdomain.com {
    basicauth {
        # 密码哈希用以下命令生成：
        # caddy hash-password --plaintext "你的密码"
        admin $2a$14$ZaPPKZPGnVPGnRCeGQGZ5u
    }
    reverse_proxy dashboard:8080
}
```

生成密码哈希：

```bash
docker exec caddy caddy hash-password --plaintext "你的密码"
```

## 第六步：实时日志与访问日志

```caddy
{
    log {
        output file /var/log/caddy/access.log {
            roll_size 50mb
            roll_keep 5
        }
        format json
    }
}

vault.yourdomain.com {
    log {
        output file /var/log/caddy/vaultwarden.log
    }
    reverse_proxy vaultwarden:80
}
```

实时查看日志：

```bash
docker logs -f caddy
# 或查看特定站点日志：
tail -f /var/log/caddy/vaultwarden.log
```

## 第七步：上线前检查清单

在生产环境上线前，逐一检查：

| 项目 | 检查 |
|---|---|
| **防火墙** | 开放 80/443 端口；管理端口（如 2019）关闭 |
| **自动重启** | compose 中 `restart: unless-stopped` |
| **资源限制** | 为 Caddy 容器添加 `deploy.resources.limits` |
| **备份 Caddy 数据** | 备份 `caddy_data` 卷（内含证书） |
| **监控** | 健康检查端点或 Prometheus 指标 |
| **更新** | `docker compose pull caddy && docker compose up -d` |

### 资源限制示例

```yaml
services:
  caddy:
    image: caddy:2-alpine
    deploy:
      resources:
        limits:
          cpus: "0.5"
          memory: "128M"
```

## Caddy vs Traefik：何时选哪个

**选 Caddy，如果：**
- 你想要最少配置就能获得 HTTPS
- 你需要一眼就能看懂的 Caddyfile
- 你管理不超过 ~20 个服务
- 你想要一行搞定泛域名证书

**选 Traefik，如果：**
- 你在跑大规模微服务架构
- 你需要 Kubernetes 风格的动态服务发现
- 你想要不重启容器就能热加载配置
- 你需要内置指标和中间件链

对于大多数在单台 VPS 上跑 5-15 个服务的自托管玩家来说，**Caddy 是更简单的选择**。

## 下一步

Caddy 跑起来后，你还可以：

1. **添加监控**：通过 `caddy-metrics` 模块暴露 Prometheus 指标
2. **启用 fail2ban**：解析 Caddy 日志封禁恶意 IP
3. **使用 Caddy API**：动态添加/删除路由，无需编辑 Caddyfile
4. **设置 ZeroSSL**：作为 Let's Encrypt 的替代方案

Caddy v2 是你自托管堆栈中能加的最佳组件之一。它消除了运行家庭实验室最痛苦的部分——TLS 证书管理——并把所有配置包裹在一个真正合理的格式里。

你试过 Caddy 吗？你的反向代理方案是什么样的？欢迎留言分享你的配置！
