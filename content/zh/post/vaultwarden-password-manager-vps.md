---
title: "Vaultwarden 自建密码管理器：在 VPS 上部署 Bitwarden 兼容方案，彻底告别订阅费"
description: "使用 Docker 在 VPS 上一键部署 Vaultwarden —— 完全兼容 Bitwarden 客户端，支持双因素认证、安全分享、密码生成器。无需付费订阅，数据完全掌握在自己手中。"
date: 2026-07-01T10:00:00+08:00
lastmod: 2026-07-01T10:00:00+08:00
slug: "vaultwarden-password-manager-vps"
tags: ["Vaultwarden", "密码管理", "Bitwarden", "Docker", "自托管", "数据安全", "VPS部署", "隐私"]
categories: ["部署教程"]
draft: false
image: /images/posts/vaultwarden-password-manager-vps/featured.png
aliases: [/zh/post/vaultwarden-password-manager-vps/]
---

## 为什么需要自建密码管理器？

在数字化时代，我们每个人平均需要管理 **50-150 个密码**。使用"123456"或"password"作为所有账户的密码，无异于把家门钥匙挂在门口。密码管理器通过加密存储和自动生成强密码，成为每个人必备的网络安全工具。

主流商业密码管理器（1Password、LastPass、Bitwarden Cloud）虽然好用，但存在几个问题：

- **持续订阅费用**：1Password 每人每月 $3-5，LastPass 高级版 $3/月
- **数据不在自己手中**：密码存储在第三方服务器，存在数据泄露风险
- **服务中断风险**：商业服务可能关闭或更改定价策略
- **隐私顾虑**：即使声称零知识加密，信任第三方总是有风险

**Vaultwarden** 提供了一个完美的替代方案——它是 Bitwarden 服务器的开源、轻量级重新实现，使用 Rust 编写，资源占用极低，完全兼容 Bitwarden 所有官方客户端。

## 什么是 Vaultwarden？

Vaultwarden（原名 bitwarden_rs）是一个第三方实现的 Bitwarden 服务端程序，具有以下特点：

| 特性 | 说明 |
|------|------|
| **语言** | Rust，高性能低内存占用 |
| **兼容性** | 完全兼容 Bitwarden 官方客户端（桌面、移动、浏览器扩展） |
| **数据库** | SQLite（轻量）或 PostgreSQL（高并发） |
| **资源需求** | 最低 64MB 内存即可运行 |
| **许可证** | Apache 2.0，完全免费开源 |
| **功能** | 密码存储、安全分享、双因素认证、密码生成器、TOTP 验证器 |

## 环境准备

假设你有一台运行以下系统的 VPS：

- **操作系统**：Ubuntu 22.04 LTS 或 Debian 12
- **内存**：至少 512MB（推荐 1GB）
- **存储**：至少 5GB 可用空间
- **域名**：指向 VPS IP（用于 HTTPS）
- **已安装**：Docker 和 Docker Compose

如果尚未安装 Docker：

```bash
# 安装 Docker
curl -fsSL https://get.docker.com | sh

# 将当前用户加入 docker 组
sudo usermod -aG docker $USER

# 验证安装
docker --version
docker compose version
```

## 部署 Vaultwarden

### 第一步：创建项目目录

```bash
mkdir -p ~/vaultwarden/data
cd ~/vaultwarden
```

### 第二步：编写 docker-compose.yml

```yaml
services:
  vaultwarden:
    image: vaultwarden/server:latest
    container_name: vaultwarden
    restart: always
    ports:
      - "80:80"
      - "443:443"
    environment:
      # 管理员邮件（用于接收管理员通知）
      ADMIN_TOKEN: "$(openssl rand -base64 32)"
      # 网站 URL
      SIGNUPS_ALLOWED: "false"
      DOMAIN: "https://your-domain.com"
      # 数据库路径
      DATABASE_URL: /data/db.sqlite3
      # 启用 Web Vault（网页版管理界面）
      WEBSOCKET_ENABLED: "true"
      WEBSOCKET_ADDRESS: "0.0.0.0"
      WEBSOCKET_PORT: "3012"
      # 日志轮转
      LOG_FILE: "/data/vaultwarden.log"
      MAX_LOG_SIZE: "10MB"
      # 备份相关
      BACKUP_FOLDER: "/data/backups"
    volumes:
      - ./data:/data
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

> **安全提示**：在生产环境中，请将 `ADMIN_TOKEN` 替换为一个随机生成的强密码，并妥善保管。

### 第三步：启动服务

```bash
docker compose up -d
```

等待几秒后检查容器状态：

```bash
docker compose ps
```

你应该看到 `vaultwarden` 容器的状态为 `healthy`。

### 第四步：配置反向代理与 HTTPS

Vaultwarden 需要 HTTPS 才能正常工作（Bitwarden 客户端强制要求）。推荐使用 **Nginx Proxy Manager** 或手动配置 **Caddy**：

#### 方案 A：使用 Caddy（推荐，自动 HTTPS）

```yaml
services:
  vaultwarden:
    image: vaultwarden/server:latest
    container_name: vaultwarden
    restart: always
    ports:
      - "80:80"
    environment:
      ADMIN_TOKEN: "your-admin-token-here"
      SIGNUPS_ALLOWED: "false"
      DOMAIN: "https://your-domain.com"
      DATABASE_URL: /data/db.sqlite3
      WEBSOCKET_ENABLED: "true"
      WEBSOCKET_PORT: "3012"
    volumes:
      - ./data:/data

  caddy:
    image: caddy:2-alpine
    container_name: caddy
    restart: always
    ports:
      - "443:443"
      - "80:80"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile
      - caddy_data:/data
      - caddy_config:/config
    depends_on:
      - vaultwarden

volumes:
  caddy_data:
  caddy_config:
```

`Caddyfile` 配置：

```
your-domain.com {
    reverse_proxy vaultwarden:80
    
    encode gzip zstd
    
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
        Referrer-Policy "strict-origin-when-cross-origin"
    }
}
```

#### 方案 B：使用 Nginx Proxy Manager

如果你已经部署了 Nginx Proxy Manager（推荐参考我们的 [Nginx Proxy Manager 指南](/zh/post/nginx-proxy-manager-guide/)），只需在面板中添加一个代理主机：

- **域名**：你的域名
- **IP**：vaultwarden 容器 IP 或 `vaultwarden`（如果使用 Docker Compose）
- **端口**：80
- **SSL**：申请 Let's Encrypt 证书

## 初始配置

### 创建管理员账户

1. 访问 `https://your-domain.com/admin`
2. 输入你在 `docker-compose.yml` 中设置的 `ADMIN_TOKEN`
3. 点击 "Create your admin account"
4. 设置管理员邮箱和密码

### 禁用公开注册

出于安全考虑，建议禁用公开注册，只允许管理员邀请新用户：

```yaml
environment:
  SIGNUPS_ALLOWED: "false"
  SIGNUPS_VERIFY: "true"
  INVITATIONS_ALLOWED: "true"
```

### 启用双因素认证

Vaultwarden 支持多种 TOTP（基于时间的一次性密码）实现方式：

- **WebAuthn**：使用安全密钥（YubiKey 等）
- **TOTP**：使用 Google Authenticator、Authy 等应用
- **DUO**：集成 DUO Security

在 Bitwarden 客户端中，进入 **设置 > 双因素身份验证**，选择你偏好的方式。

## 客户端连接

Vaultwarden 的最大优势是 **完全兼容 Bitwarden 客户端**。你可以使用：

- **桌面端**：Windows、macOS、Linux 原生应用
- **浏览器扩展**：Chrome、Firefox、Edge、Safari
- **移动端**：iOS、Android 官方应用
- **命令行**：`bw` CLI 工具

### 添加自定义服务器

在任意 Bitwarden 客户端中：

1. 打开 **设置 > 账户 > 服务**
2. 点击 **自定义**
3. 输入你的 Vaultwarden 实例地址：`https://your-domain.com`
4. 登录你的管理员账户

连接成功后，所有功能（密码存储、生成器、安全事件、分享等）均可正常使用。

## 安全加固

### 1. 限制注册

```yaml
environment:
  SIGNUPS_ALLOWED: "false"
  ADMIN_TOKEN: "$(openssl rand -base64 48)"
```

### 2. 启用日志监控

```yaml
environment:
  LOG_FILE: "/data/vaultwarden.log"
  MAX_LOG_SIZE: "10MB"
  LOG_FORMAT: "json"
```

### 3. 定期备份

```bash
#!/bin/bash
# backup-vaultwarden.sh
BACKUP_DIR="$HOME/vaultwarden/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
mkdir -p "$BACKUP_DIR"

docker exec vaultwarden cp /data/db.sqlite3 "/data/backup_${TIMESTAMP}.db"
docker cp vaultwarden:/data/backup_${TIMESTAMP}.db "$BACKUP_DIR/"
docker exec vaultwarden rm -f /data/backup_${TIMESTAMP}.db

# 保留最近 30 天的备份
find "$BACKUP_DIR" -name "backup_*.db" -mtime +30 -delete

echo "Backup completed: ${BACKUP_DIR}/backup_${TIMESTAMP}.db"
```

将其添加到 crontab 实现自动化：

```bash
crontab -e
# 每天凌晨 3 点备份
0 3 * * * /path/to/backup-vaultwarden.sh >> /var/log/vaultwarden-backup.log 2>&1
```

### 4. 网络隔离

仅暴露必要的端口，使用 Docker 网络隔离：

```yaml
networks:
  vaultwarden-net:
    driver: bridge

services:
  vaultwarden:
    networks:
      - vaultwarden-net
  caddy:
    networks:
      - vaultwarden-net
```

### 5. 防火墙规则

```bash
# 仅开放必要端口
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP (重定向到 HTTPS)
sudo ufw allow 443/tcp   # HTTPS
sudo ufw enable
```

## 高级功能

### 密码健康检查

Bitwarden/Vaultwarden 提供内置的 **密码健康检查** 功能：

- **重复使用的密码**：检测你在多个网站使用的相同密码
- **弱密码**：识别容易被破解的密码
- **已泄露的密码**：与 HaveIBeenPwned 数据库比对，检查密码是否曾在数据泄露中出现
- **未加密的密码**：标记未使用加密存储的密码

定期查看 **安全事件** 页面，更新不安全的密码。

### 安全分享

Vaultwarden 支持 **安全分享** 功能，可以通过加密链接与信任的人共享敏感信息（如 WiFi 密码、Wi-Fi 配置文件、API 密钥等），而无需直接明文发送。

### 组织与团队

对于小团队或家庭使用，Vaultwarden 支持 **组织** 功能：

- 创建家庭或团队空间
- 共享密码库
- 管理成员权限
- 审计日志追踪

### TOTP 验证码管理

除了密码存储，Vaultwarden 还可以作为 **TOTP 验证器** 使用，管理你的双因素认证代码，替代 Google Authenticator。

## 迁移指南

### 从其他密码管理器迁移

#### 从 LastPass 迁移

1. 导出 LastPass CSV 文件
2. 导入 Bitwarden 客户端：设置 > 导出 > 选择 CSV 文件
3. 验证导入的数据完整性

#### 从 1Password 迁移

1. 在 1Password 中导出 `.1pux` 或 CSV 格式
2. 转换为 Bitwarden 格式（使用 [1pass-to-bitwarden](https://github.com/dghouston/1pass-to-bitwarden) 工具）
3. 在 Bitwarden 客户端中导入

#### 从 Bitwarden Cloud 迁移

1. 在 Bitwarden Web 界面导出数据
2. 在 Vaultwarden 客户端中导入
3. 验证所有条目

### 迁移注意事项

- **迁移前务必备份现有密码库**
- **迁移后验证所有重要账户**的密码是否正确
- **建议先在小范围测试**，确认无误后再全面迁移
- **旧密码管理器不要立即删除**，保留 1-2 周作为缓冲期

## 故障排除

### 问题 1：客户端无法连接

**症状**：Bitwarden 客户端提示 "Connection error"

**解决方案**：
- 确认域名 DNS 解析正确
- 确认 HTTPS 证书有效（自签名证书可能导致问题）
- 检查 `DOMAIN` 环境变量是否与客户端配置的地址一致
- 确认防火墙未阻止 443 端口

### 问题 2：Web Vault 无法访问

**症状**：访问 `/admin` 返回 404

**解决方案**：
- 确认容器正常运行：`docker compose ps`
- 检查日志：`docker compose logs vaultwarden`
- 确认反向代理配置正确

### 问题 3：存储空间不足

**症状**：Vaultwarden 无法写入数据

**解决方案**：
- 清理旧日志：`docker exec vaultwarden truncate -s 0 /data/vaultwarden.log`
- 检查磁盘空间：`df -h`
- 增加存储空间或清理不必要的数据

### 问题 4：双因素认证丢失

**症状**：无法登录，2FA 设备不可用

**解决方案**：
- 通过管理员面板临时禁用该用户的 2FA
- 或使用 `ADMIN_TOKEN` 登录后重置

## 总结

| 项目 | 详情 |
|------|------|
| **部署难度** | ⭐⭐☆☆☆（简单，一条 docker compose 命令） |
| **资源占用** | 64MB-256MB 内存，< 100MB 磁盘 |
| **安全性** | 高（AES-256 加密，端到端安全） |
| **兼容性** | 完美兼容 Bitwarden 全平台客户端 |
| **成本** | 免费（仅需 VPS 费用） |
| **维护成本** | 极低（自动更新容器镜像即可） |

Vaultwarden 是自托管密码管理器的最佳选择。它结合了 Bitwarden 的完整功能和极低的资源需求，让你的密码安全完全掌握在自己手中。

**立即行动**：在你的 VPS 上部署 Vaultwarden，开始使用强密码和双因素认证保护你的数字生活。

## 参考资源

- [Vaultwarden GitHub 仓库](https://github.com/dani-garcia/vaultwarden)
- [Bitwarden 官方文档](https://bitwarden.com/help/)
- [Have I Been Pwned](https://haveibeenpwned.com/) — 检查密码是否泄露
- [Nginx Proxy Manager 部署指南](/zh/post/nginx-proxy-manager-guide/)
