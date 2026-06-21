---
title: "Synapse 自托管指南：搭建私有 Matrix 即时通讯与 VoIP 服务器，实现完全掌控的通信"
description: "从零开始在 VPS 上部署 Matrix Synapse 服务器，搭配 Element 客户端实现端到端加密的即时通讯、语音/视频会议、机器人集成和团队协作，彻底告别第三方通讯平台的数据隐私风险"
date: 2026-06-21T10:00:00+08:00
lastmod: 2026-06-21T10:00:00+08:00
slug: "synapse-matrix-selfhosted-guide"
tags: ["Matrix", "Synapse", "即时通讯", "端到端加密", "VoIP", "Element", "自托管", "Docker", "VPS部署", "隐私"]
categories: ["部署教程"]
draft: false
image: /images/posts/synapse-matrix-selfhosted-guide/featured.png
aliases: [/zh/post/synapse-matrix-selfhosted-guide/]
---

## 为什么需要自建即时通讯平台？

在 Telegram、WhatsApp、Signal 等主流通讯工具中，你的消息内容、联系人关系和通话记录都存储在第三方服务器上。即使这些平台声称端到端加密，你仍然需要信任它们的运营方——而历史表明，没有任何商业公司能永远保护你的数据。

[Matrix](https://matrix.org/) 是一个开放的实时通信协议，类似于电子邮件的 SMTP 协议：它不绑定任何单一服务商，允许任何人搭建自己的服务器并与其他服务器互联互通。[Synapse](https://github.com/element-hq/synapse) 是 Matrix 协议的参考实现服务器，用 Python 编写，配合 [Element](https://element.io/) 客户端即可构建完整的私有通讯系统。

### Matrix 生态的核心优势

| 特性 | 说明 |
|------|------|
| **去中心化** | 像邮件一样，你可以选择自己的服务器，也能与其他服务器互通 |
| **端到端加密** | 默认支持 Olm/Megolm 加密，服务器也无法查看消息内容 |
| **多媒体通信** | 支持文字、语音通话、视频会议（通过 Jitsi 集成） |
| **机器人集成** | 丰富的 Bot API，可对接 CI/CD、监控、AI 等自动化场景 |
| **跨平台客户端** | Element 覆盖 Web、iOS、Android、Windows、macOS、Linux |
| **数据主权** | 所有数据完全存储在你自己的 VPS 上 |

## 环境准备

### 服务器要求

| 规模 | CPU | 内存 | 磁盘 | 适用场景 |
|------|-----|------|------|----------|
| 最小 | 1 核 | 1GB | 10GB | 1-5 人团队 |
| 推荐 | 2 核 | 2GB | 20GB | 5-50 人团队 |
| 生产 | 4 核 | 4GB+ | 50GB+ | 50+ 人团队 |

本文以 **2 核 2GB 的 VPS** 为例进行部署。

### 前置条件

- VPS 运行 Ubuntu 22.04/24.04 或 Debian 12
- 已安装 Docker 和 Docker Compose
- 一个指向 VPS 的域名（如 `matrix.yourdomain.com`）
- 可选：SSL 证书（Let's Encrypt）

## 第一步：安装 Docker 环境

如果你的 VPS 还没有 Docker：

```bash
# 安装 Docker
curl -fsSL https://get.docker.com | sh

# 启动 Docker 服务
sudo systemctl enable docker
sudo systemctl start docker

# 将当前用户加入 docker 组（避免每次用 sudo）
sudo usermod -aG docker $USER
newgrp docker
```

验证安装：

```bash
docker --version
# Docker version 27.x.x

docker compose version
# Docker Compose version v2.x.x
```

## 第二步：创建 Synapse 配置文件

首先创建项目目录结构：

```bash
mkdir -p ~/matrix-synapse/{homeserver,data,logs,nginx,certs}
cd ~/matrix-synapse
```

使用 Docker 容器生成初始配置：

```bash
docker run --rm \
  -v ./homeserver:/data \
  matrixdotorg/synapse:latest \
  generate

# 编辑配置文件
nano homeserver/homeserver.yaml
```

关键配置项修改：

```yaml
# 服务器名称（必须与你域名的 server_name 一致）
server_name: "matrix.yourdomain.com"
pedantic_server_names: true

# 监听配置
listeners:
  - port: 8008
    tls: false
    type: http
    x_forwarded: true
    resources:
      - names: [client, federation]
        compress: false

# 数据库配置
database:
  name: sqlite3
  args:
    database: /data/homeserver.db

# 注册权限密钥（首次注册用户时使用）
registration_shared_secret: "生成一个随机密钥"

# 允许远程注册（生产环境建议关闭，用管理员手动添加）
enable_registration: true

# 日志配置
log_config: "/data/matrix.yourdomain.com.log.config"
```

生成 registration shared secret：

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

配置日志：

```yaml
# homeserver/matrix.yourdomain.com.log.config
version: 1

formatters:
  precise:
    format: "%(asctime)s %(levelname)-5s %(process)s %(name)s:%(lineno)d %(message)s"

handlers:
  file:
    class: logging.handlers.RotatingFileHandler
    formatter: precise
    filename: /data/logs/homeserver.log
    maxBytes: 104857600  # 100MB
    backupCount: 10

root:
  level: INFO
  handlers:
    - file
```

## 第三步：使用 Docker Compose 启动 Synapse

创建 `docker-compose.yaml`：

```yaml
services:
  synapse:
    image: matrixdotorg/synapse:latest
    container_name: synapse
    restart: unless-stopped
    ports:
      - "8008:8008"
    volumes:
      - ./homeserver:/data
      - ./logs:/data/logs
    environment:
      - TZ=Asia/Shanghai
    depends_on:
      - db

  db:
    image: postgres:16-alpine
    container_name: synapse-db
    restart: unless-stopped
    environment:
      - POSTGRES_USER=synapse
      - POSTGRES_PASSWORD=synapse_password_here
      - POSTGRES_DB=synapse
      - TZ=Asia/Shanghai
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U synapse"]
      interval: 10s
      timeout: 5s
      retries: 5
```

> **注意**：生产环境推荐使用 PostgreSQL 而非 SQLite。SQLite 在小规模部署时可行，但当并发连接增多时性能会明显下降。

启动服务：

```bash
docker compose up -d

# 查看日志确认启动成功
docker logs -f synapse
```

## 第四步：注册管理员账户

```bash
# 进入容器执行注册命令
docker exec -it synapse register_new_matrix_user \
  -c /data/homeserver.yaml \
  http://localhost:8008 \
  --admin \
  -u admin \
  -p 'your_secure_password_here'
```

注册成功后，你会收到一条确认邮件（如果配置了 email）。管理员账户拥有所有权限，包括创建其他用户。

## 第五步：配置 Nginx 反向代理与 HTTPS

Synapse 本身不提供 HTTPS，需要通过 Nginx 或 Caddy 做反向代理。

### 安装 Nginx 和 SSL 证书

```bash
sudo apt install -y nginx certbot python3-certbot-nginx
```

### 获取 SSL 证书

```bash
sudo certbot --nginx -d matrix.yourdomain.com
```

### 配置 Nginx

```nginx
server {
    listen 443 ssl http2;
    server_name matrix.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/matrix.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/matrix.yourdomain.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    # 客户端请求限制
    client_max_body_size 50M;

    # Matrix Client API
    location /_matrix/client/ {
        proxy_pass http://127.0.0.1:8008;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_buffering off;
        chunked_transfer_encoding off;
    }

    # Matrix Federation API
    location /_matrix/federation/ {
        proxy_pass http://127.0.0.1:8008;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_buffering off;
    }

    # Matrix Media Repo
    location /_matrix/media/ {
        proxy_pass http://127.0.0.1:8008;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # Synapse Server Key
    location /_matrix/key/v2/ {
        proxy_pass http://127.0.0.1:8008;
        proxy_set_header Host $host;
    }

    # Well-known configuration
    location /.well-known/matrix/server {
        add_header Content-Type application/json;
        return 200 '{"m.server": "matrix.yourdomain.com:443"}';
    }

    location /.well-known/matrix/client {
        add_header Content-Type application/json;
        return 200 '{
            "m.home_server": "matrix.yourdomain.com",
            "m.server": "matrix.yourdomain.com:443"
        }';
    }
}

# HTTP → HTTPS 重定向
server {
    listen 80;
    server_name matrix.yourdomain.com;
    return 301 https://$server_name$request_uri;
}
```

```bash
# 测试配置并重载 Nginx
sudo nginx -t
sudo systemctl reload nginx
```

## 第六步：配置邮件服务（可选但推荐）

在 `homeserver.yaml` 中添加邮件配置：

```yaml
email:
  smtp_host: smtp.yourdomain.com
  smtp_port: 587
  smtp_user: "noreply@yourdomain.com"
  smtp_pass: "your_smtp_password"
  require_transport_security: true
  notif_from: "Your Name <noreply@yourdomain.com>"

  app_name: "MyPrivateMatrix"

  notif_template_html: notif_mail.html
  notif_template_text: notif_mail.txt
```

## 第七步：安装 Element 客户端

### Web 版（最快上手）

访问 `https://matrix.yourdomain.com`，Element 会自动检测你的服务器。点击「创建账户」即可注册新用户。

### 桌面客户端

- **Linux**: `sudo apt install element-desktop` 或从 [element.io](https://element.io/download) 下载 AppImage
- **Windows/macOS**: 从官网下载对应安装包
- **移动端**: iOS/Android 应用商店搜索「Element」

### 使用 Element 登录

1. 打开 Element，选择「自定义服务器」
2. 输入你的域名：`https://matrix.yourdomain.com`
3. 用刚才注册的管理员账号登录

## 第八步：邀请用户与日常管理

### 创建普通用户

```bash
# 作为管理员，在服务器上执行
docker exec -it synapse register_new_matrix_user \
  -c /data/homeserver.yaml \
  http://localhost:8008 \
  -u alice \
  -p 'alice_secure_password'
```

### 邀请用户通过链接

在 Element 中，点击房间设置 → 邀请 → 复制链接。被邀请者可以通过该链接自动发现你的服务器并注册。

### 管理用户

```bash
# 列出所有用户
docker exec -it synapse list_users -c /data/homeserver.yaml

# 禁用用户
docker exec -it synapse deactivate_user -c /data/homeserver.yaml user@matrix.yourdomain.com

# 重置密码
docker exec -it synapse update_password -c /data/homeserver.yaml user@matrix.yourdomain.com new_password_here
```

## 第九步：配置语音/视频会议

Synapse 本身不处理媒体流，需要配合 Jitsi Meet 实现音视频通话。

### 方法一：使用公共 Jitsi 实例（简单）

在 Element 的房间设置中，直接配置 Jitsi 域名即可。但公共实例可靠性有限。

### 方法二：自建 Jitsi Meet（推荐）

```bash
mkdir -p ~/jitsi-meet
cd ~/jitsi-meet

# 使用官方安装脚本
wget -qO - https://download.jitsi.org/jitsi-key.gpg.key | gpg --dearmor > /usr/share/keyrings/jitsi-keyring.gpg
echo 'deb [signed-by=/usr/share/keyrings/jitsi-keyring.gpg] https://download.jitsi.org stable/' | tee /etc/apt/sources.list.d/jitsi-stable.list > /dev/null
apt update
apt install -y jitsi-meet
```

安装过程中会要求输入域名（如 `meet.yourdomain.com`），然后自动配置 SSL 证书。

在 Element 的房间设置中将 Jitsi 域名设置为 `https://meet.yourdomain.com`。

## 第十步：配置机器人（Bot）集成

Matrix 的 Bot API 非常强大，可以对接各种自动化工具。

### 常用 Bot 示例

#### 1. 部署 Gatus 健康检查 Bot

```bash
# 克隆 Gatus Bot
git clone https://github.com/TwiN/gatus.git
cd gatus/docker/bot

# 修改 config.yaml 填入你的 bot token
```

#### 2. 部署 Matrix IRC Bridge

将 Matrix 房间与 IRC 频道桥接：

```yaml
# docker-compose.yaml 片段
irc-bot:
  image: matrix-org/matrix-appservice-irc:latest
  volumes:
    - ./irc-config:/config
  ports:
    - "9000:9000"
```

#### 3. 部署 Matrix CI/CD Bot

使用 [matrix-bot-sdk](https://github.com/matrix-org/matrix-bot-sdk) 编写自定义 Bot：

```python
from matrix_bot_sdk import MatrixClient

client = MatrixClient("https://matrix.yourdomain.com")
home = client.join_room("!roomid:matrix.yourdomain.com")

@home.on_event("m.room.message")
def handle_message(event):
    content = event["content"]["body"]
    if content.startswith("!deploy"):
        home.send_markdown_message("正在部署...")
        # 执行部署逻辑
        home.send_markdown_message("✅ 部署完成！")

client.run()
```

## 进阶配置

### 配置媒体存储限制

防止用户上传过多文件占满磁盘：

```yaml
# homeserver.yaml
max_upload_size_mb: 100
media_storage_path: /data/media_store
write_back:
  engine: ffi
  blob_store_path: /data/blob_store
  blob_store_keep_days: 90
```

### 配置速率限制

```yaml
rate_limits:
  concurrent_login_limit_per_user: 5
  concurrent_login_window: 30s
  concurrent_login_reauth_window: 30s
```

### 启用 Federation（允许其他 Matrix 服务器连接）

```yaml
# homeserver.yaml
federation_domain_whitelist:
  - matrix.org
  - element.io

suppress_send_errors: false
```

> **提示**：启用 Federation 后，你的服务器将成为 Matrix 全球网络的一部分，其他服务器上的用户可以与你通信。如果只想内部使用，保持关闭即可。

### 定期备份

```bash
#!/bin/bash
# backup-matrix.sh
BACKUP_DIR="/backup/matrix"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p "$BACKUP_DIR"

# 备份数据库
docker exec synapse-db pg_dump -U synapse synapse > "$BACKUP_DIR/synapse_$DATE.sql"

# 备份上传的媒体文件
tar czf "$BACKUP_DIR/media_$DATE.tar.gz" -C /root/matrix-synapse/data/media_store .

# 保留最近 30 天备份
find "$BACKUP_DIR" -mtime +30 -delete

echo "Backup completed: $DATE"
```

添加到 crontab：

```bash
crontab -e
# 每天凌晨 2 点备份
0 2 * * * /root/scripts/backup-matrix.sh
```

## 常见问题排查

### 问题 1：Element 无法连接服务器

检查 Nginx 配置是否正确转发 `/_matrix/` 路径：

```bash
curl -I https://matrix.yourdomain.com/_matrix/client/versions
# 应返回 200 OK 和 JSON 响应
```

### 问题 2： federation 连接失败

确保防火墙开放了 443 端口用于联邦通信：

```bash
sudo ufw allow 443/tcp
sudo ufw allow 8448/tcp  # 如果使用非标准端口
```

### 问题 3：存储空间不足

```bash
# 查看磁盘使用
df -h

# 清理旧媒体文件
docker exec synapse python3 -m synapse.admin purge_media_cache \
  -c /data/homeserver.yaml \
  --size 1GB \
  --min-age 30d
```

### 问题 4：PostgreSQL 连接问题

```bash
# 检查数据库状态
docker logs synapse-db

# 重启数据库
docker restart synapse-db

# 检查连接
docker exec synapse-db pg_isready -U synapse
```

## 安全加固清单

- [x] 启用 HTTPS（Let's Encrypt 自动续期）
- [x] 关闭公开注册（生产环境）
- [x] 配置 rate limiting
- [x] 限制最大上传文件大小
- [x] 定期更新 Synapse 镜像
- [x] 配置防火墙（仅开放 80/443）
- [x] 启用数据库备份
- [x] 设置日志轮转
- [x] 使用强密码策略

## 总结

通过本文的教程，你已经成功在 VPS 上部署了一个完整的 Matrix 即时通讯服务器。与商业通讯平台相比，自托管 Synapse 的优势在于：

1. **完全的数据控制权** — 所有消息、文件、联系人都在你自己的服务器上
2. **零成本运营** — 只需 VPS 费用，无订阅费
3. **高度可扩展** — 从 5 人到 5000 人都能应对
4. **丰富的生态** — Bot、Bridge、插件让它可以对接几乎任何工作流
5. **真正的端到端加密** — 即使服务器管理员也无法查看消息内容

Matrix 协议就像电子邮件一样，是一种开放的、去中心化的通讯标准。当你拥有自己的 Synapse 服务器时，你就拥有了属于自己的「邮件服务器」——只不过这次是即时的、加密的、支持音视频的。

开始使用吧，把隐私还给自己！
