---
title: "Nginx Proxy Manager：自托管反向代理的 Web UI 利器，无需手写 Nginx 配置"
description: "Nginx Proxy Manager（NPM）让你通过 Web 界面管理反向代理、SSL 证书和访问控制，彻底告别手写 Nginx 配置文件的痛苦。本文手把手教你用 Docker 部署 NPM，添加代理主机、申请 Let's Encrypt 免费证书、配置访问列表和 WebSocket 支持。"
date: 2026-06-01T10:00:00+08:00
slug: "nginx-proxy-manager-guide"
tags: ["Nginx Proxy Manager", "NPM", "反向代理", "Docker", "SSL", "Let's Encrypt", "自托管", "VPS", "Web UI"]
categories: ["DevOps", "Web 服务器"]
aliases: [/zh/post/nginx-proxy-manager-guide/]
draft: false
image: /images/posts/nginx-proxy-manager-guide/featured.png
---

如果你在一台 VPS 上跑了多个自托管服务——一个 Jellyfin 看片、一个 Immich 管理照片、一个 Vaultwarden 管密码、一个 Gitea 写代码——你一定会面临一个实际问题：**怎么让它们都用 443 端口，同时自动配好 HTTPS？**

传统方案有两个：Caddy 极其优雅但 Caddyfile 仍需学习；Nginx 功能最全但配置语法出了名的折磨人。**Nginx Proxy Manager（NPM）** 给了第三条路：一个干净、完整的 Web UI，让你在浏览器里点几下鼠标就搞定反向代理和 SSL。

本文你将学会：

- 用 Docker Compose 一分钟部署 NPM
- 通过 Web UI 添加代理主机（Proxy Host）
- 自动申请和续期 Let's Encrypt SSL 证书
- 配置访问列表、IP 白名单和基础认证
- 支持 WebSocket 和 HTTP/2
- 高级：自定义 location 块和流式代理

---

## 什么是 Nginx Proxy Manager？

Nginx Proxy Manager（NPM）是一个基于 Nginx 的反向代理管理面板，由 `jc21` 开发并开源。它的核心思想很简单：**把 Nginx 配置可视化**。

你不需要记住 `server {}` 块怎么写、不需要手动拼接 `ssl_certificate` 路径、不需要用 `certbot` 在命令行里折腾。打开浏览器，填域名、选端口、勾一下「SSL」，系统自动生成配置、自动申请证书、自动续期。

**核心特性：**

| 特性 | 说明 |
|------|------|
| Web UI 管理 | 浏览器操作，零 CLI 依赖 |
| 自动 SSL | 内置 Let's Encrypt 客户端，自动申请/续期 |
| 访问控制 | IP 白名单/黑名单、基础认证、Access List |
| 多用户 | 支持多用户权限分离 |
| 流式代理 | WebSocket、TCP/UDP 代理（高级模式） |
| 免费开源 | MIT 许可证，GitHub 5.5k+ stars |

---

## 一、Docker Compose 部署

用 Docker Compose 部署 NPM 是最推荐的方式。创建项目目录：

```bash
mkdir -p ~/nginx-proxy-manager && cd ~/nginx-proxy-manager
```

创建 `docker-compose.yml`：

```yaml
version: '3.8'

services:
  app:
    image: 'jc21/nginx-proxy-manager:latest'
    restart: unless-stopped
    ports:
      # HTTP 入口
      - '80:80'
      # HTTPS 入口（SSL 反向代理就用这个端口）
      - '443:443'
      # NPM 管理面板端口
      - '81:81'
    volumes:
      # NPM 配置、证书、数据库持久化
      - ./data:/data
      - ./letsencrypt:/etc/letsencrypt
    environment:
      DB_SQLITE_FILE: "/data/database.sqlite"
```

启动：

```bash
docker compose up -d
```

> ⚠️ **重要：** 如果 VPS 上原有服务已经占用 80/443，需要先停掉它们，或者把 NPM 的端口映射改成其他端口（但 Let's Encrypt HTTP 验证默认需要 80 端口可用）。

### 防火墙配置

确保云服务商的安全组和服务器防火墙放行 80、443 和 81 端口：

```bash
# ufw
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 81/tcp

# 或者 iptables
iptables -A INPUT -p tcp --dport 80 -j ACCEPT
iptables -A INPUT -p tcp --dport 443 -j ACCEPT
iptables -A INPUT -p tcp --dport 81 -j ACCEPT
```

---

## 二、首次登录与初始配置

打开浏览器访问 `http://你的VPS_IP:81`。

**默认管理员账号：**
- 邮箱：`admin@example.com`
- 密码：`changeme`

首次登录会强制要求修改邮箱和密码，**务必修改为强密码**。

![NPM 登录界面](https://nginxproxymanager.com/screenshots/login.png)

登录后你会看到干净的主面板（Dashboard），这里显示：

- 当前代理主机数量
- SSL 证书数量
- 访问列表数量
- 系统运行状态

---

## 三、添加第一个代理主机

假设你已经在 VPS 上用 Docker 跑了一个 Jellyfin 媒体服务器（端口 `8096`），你想通过 `jellyfin.你的域名.com` 来访问它。

### 步骤

1. 点击左侧 **Hosts → Proxy Hosts**
2. 点击右上角 **Add Proxy Host**

![添加代理主机](https://nginxproxymanager.com/screenshots/add-proxy-host.png)

**填写信息：**

| 字段 | 填写内容 | 说明 |
|------|----------|------|
| Domain Names | `jellyfin.你的域名.com` | 多个域名逗号分隔 |
| Scheme | `http` | 上游服务是 HTTP 就用 http |
| Forward Hostname / IP | `172.17.0.2` 或 `jellyfin` | Docker 容器名或 IP |
| Forward Port | `8096` | 上游服务端口 |
| Cache Assets | ❌ | 动态内容不缓存 |
| Block Common Exploits | ✅ | 安全建议开启 |
| Websockets Support | ✅ | 如果服务需要 WebSocket |

### 配置 SSL

切换到 **SSL** 标签页：

1. **SSL Certificate** → 选择 **Request a new SSL Certificate**
2. 填入邮箱（用于 Let's Encrypt 提醒）
3. 勾选 **I agree to the Let's Encrypt Terms of Service**
4. 点击 **Save**

系统会自动：
- 向 Let's Encrypt 发起验证（HTTP-01 挑战）
- 颁发证书
- 保存到数据库
- 应用配置并 reload Nginx

整个过程通常 **10-30 秒**。完成后你的服务就可以通过 `https://jellyfin.你的域名.com` 安全访问了。

---

## 四、SSL 证书管理

NPM 的 SSL 管理非常省心。

### 查看证书

左侧 **SSL Certificates** 可以看到所有已申请的证书及其过期时间。

### 自动续期

NPM 内置了一个每日 cron 任务，自动检查并续期即将过期的证书。你**不需要**手动执行 certbot renew。

### 使用已有证书

如果你已经有通配符证书（Wildcard DNS-01），可以手动导入：

1. **SSL Certificates → Add SSL Certificate → Custom**
2. 粘贴证书内容（Certificate）和私钥（Key）
3. 保存后在代理主机的 SSL 标签页选择它

### DNS Challenge（通配符证书）

NPM 也支持 DNS Challenge 申请 `*.你的域名.com` 通配符证书，需要配置 DNS 提供商 API：

1. **SSL Certificates → Add SSL Certificate → Let's Encrypt**
2. **Use DNS Challenge** → 选择你的 DNS 提供商
3. 填入 API 凭证（不同提供商格式不同）
4. 申请证书

目前支持的 DNS 提供商：Cloudflare、AWS Route53、DNSPod、阿里云 DNS 等数十种。

---

## 五、访问列表与安全加固

### 创建访问列表

左侧 **Access Lists**：

1. 点击 **Add Access List**
2. 命名（如 "家庭白名单"）
3. 添加授权规则：
   - **Satisfy Any**：满足任一规则即允许
   - **Satisfy All**：必须满足所有规则

**规则类型：**

| 类型 | 示例 | 说明 |
|------|------|------|
| Allow | `192.168.1.0/24` | 允许内网段 |
| Deny | `0.0.0.0/0` | 拒绝所有（配合白名单使用） |
| Satisfy Any | — | 登录或 IP 白名单满足其一即可 |

### 基础认证

在 Access List 中可以添加用户（用户名+密码），这样访问代理的服务时会弹出 HTTP 基本认证对话框。适合：

- 管理后台
- 测试环境
- 不想暴露给公网的服务

---

## 六、高级配置

### 自定义 Nginx 配置

在代理主机的 **Advanced** 标签页，可以插入自定义 Nginx 配置片段。例如：

```nginx
# 限制上传大小
client_max_body_size 100M;

# 添加安全头
add_header X-Frame-Options "SAMEORIGIN" always;
add_header X-Content-Type-Options "nosniff" always;
add_header Strict-Transport-Security "max-age=31536000" always;
```

### WebSocket 支持

代理主机编辑 → **Advanced** 标签页，确保开启 **Websocket Support**。NPM 会自动添加以下配置：

```nginx
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection "upgrade";
```

### 404 页面和重定向

左侧 **Hosts → Redirection Hosts** 可以创建：

- **301 永久重定向**：将旧域名跳转到新域名
- **302 临时重定向**：用于维护模式

**Dead Hosts** 可以自定义 404 页面显示内容。

### 流式代理（TCP/UDP）

NPM 完整版支持 TCP/UDP 流代理（Streams），适合代理 SSH、数据库等非 HTTP 服务：

左侧 **Hosts → Streams → Add Stream**

| 字段 | 示例 | 说明 |
|------|------|------|
| Incoming Port | `2222` | NPM 监听的端口 |
| Forward Host | `192.168.1.10` | 目标服务器 IP |
| Forward Port | `22` | 目标 SSH 端口 |

---

## 七、运维技巧

### 备份与恢复

NPM 的所有配置都存储在 SQLite 数据库中，备份整个 `./data` 目录即可：

```bash
# 备份
tar czf npm-backup-$(date +%Y%m%d).tar.gz ./data ./letsencrypt

# 恢复
tar xzf npm-backup-20260601.tar.gz
docker compose restart
```

### 查看日志

```bash
# 实时日志
docker compose logs -f

# Nginx 访问日志
docker exec -it nginx-proxy-manager-app-1 cat /data/logs/default-host.log
```

### 更新

```bash
docker compose pull
docker compose up -d
```

### 使用第三方域名 DNS 管理

推荐搭配 Cloudflare DNS 使用：

1. 将域名的 NS 记录指向 Cloudflare
2. 在 Cloudflare 添加 A 记录指向 VPS IP
3. NPM 中申请 SSL 证书时选择 Cloudflare DNS Challenge
4. 通配符证书一条搞定所有子域名

---

## 八、NPM vs Caddy vs Traefik 对比

| 特性 | Nginx Proxy Manager | Caddy v2 | Traefik |
|------|:---:|:---:|:---:|
| Web UI | ✅ 完整 UI | ❌ 无 | ✅ 华丽 Dashboard |
| 配置难度 | ⭐（极简单） | ⭐⭐（较简单） | ⭐⭐⭐（中等） |
| 自动 HTTPS | ✅ Let's Encrypt | ✅ 全自动 | ✅ Let's Encrypt |
| 动态重载 | ✅ 保存即生效 | ❌ 需 reload | ✅ 自动发现 |
| 容器自动发现 | ❌ 手动添加 | ❌ 手动添加 | ✅ Docker label |
| 自定义 Nginx | ✅ Advanced 标签 | ❌ 不需要 | ❌ |
| 资源占用 | 中等 | 极低 | 中等 |
| 学习曲线 | 平缓 | 平缓 | 较陡 |

**选型建议：**
- **只想点鼠标、不想写配置** → NPM
- **追求极简、愿意写几行 DSL** → Caddy
- **全容器化、Kubernetes 环境** → Traefik

---

## 九、常见问题

### Q: Let's Encrypt 验证失败？
A: 最常见的原因是 80 端口不通。确保：
1. VPS 防火墙放行了 80 端口
2. 域名 A 记录已指向 VPS IP
3. 没有其他服务占用 80 端口

### Q: 代理的服务打不开？
A: 检查：
1. 上游服务是否正常运行
2. Docker 网络能否互通（用容器名替代 IP）
3. 目标端口是否正确

### Q: 如何让 Docker 容器能通过容器名访问？
A：确保 NPM 和上游服务在同一个 Docker 网络：

```yaml
# 在 docker-compose.yml 中
networks:
  npm_network:
    external: true
```

或者更简单的方法：把 NPM 加入上游服务的已有网络：

```bash
docker network connect 上游服务网络名 nginx-proxy-manager-app-1
```

### Q: 如何限制管理面板只允许内网访问？
A：修改 docker-compose.yml，只监听内网 IP：

```yaml
ports:
  - '127.0.0.1:81:81'
```

然后通过 SSH 隧道访问：

```bash
ssh -L 8081:127.0.0.1:81 root@你的VPS_IP
```

---

## 总结

Nginx Proxy Manager 是目前**最易上手**的自托管反向代理方案之一。它对不想折腾配置文件、只想快速安全地暴露服务的用户来说非常合适。加上 Docker 的便利性和 Let's Encrypt 的自动化，你可以在 **5 分钟内**让第一个服务通过 HTTPS 上线。

不过它也有限制：Web UI 无法覆盖 Nginx 的全部功能，复杂场景（如 gRPC、高级负载均衡）需要回到手动配置。但覆盖 90% 的日常场景绰绰有余。

**下一步你可以尝试：**

- 把 Jellyfin、Immich、Vaultwarden、Gitea 全部代理到 NPM 后面
- 配合 Cloudflare Tunnel 实现零暴露公网 IP
- 用 NPM 的 Access List 为家庭用户创建更安全的内网穿透方案

你值得把时间花在打磨服务本身，而不是写 Nginx 配置。
