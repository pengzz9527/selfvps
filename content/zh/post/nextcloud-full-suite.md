---
title: "Nextcloud 全家桶：在 VPS 上搭建完整的个人云办公套件（文档协作、视频会议、邮件服务）"
subtitle: "Build a Complete Self-Hosted Office Suite on VPS — Nextcloud, Collabora, Mail & Video Chat"
date: 2026-07-12
draft: false
tags: ["Nextcloud", "Collabora", "自托管", "Docker", "邮件服务", "文档协作", "视频会议"]
categories: ["自托管应用"]
image: /images/posts/nextcloud-full-suite/featured.png
description: "从零开始在 VPS 上部署 Nextcloud 全家桶——集成 Collabora 在线文档编辑、Talk 视频会议和 Mail 邮件客户端，打造完全属于你的私有办公平台。"
---

## 引言：为什么你需要一个完整的个人云办公套件？

在云服务越来越昂贵的今天，越来越多的技术爱好者选择将数据和服务迁移到自托管方案。但大多数指南只教你部署一个 Nextcloud 实例——文件同步和共享。真正的生产力工具应该是一个**完整的办公套件**：

- 📄 **在线文档编辑** — 类似 Google Docs，支持多人实时协作
- 💬 **视频会议** — 无需第三方平台的私密通话
- 📧 **邮件客户端** — 统一管理所有邮箱账户
- 🔐 **完全的数据主权** — 你的数据，你的服务器

本文将带你从零开始在 VPS 上搭建一套完整的 Nextcloud 全家桶，使用 Docker Compose 实现一键部署和轻松维护。

## 架构概览

```
┌──────────────────────────────────────────────────────┐
│              Nextcloud Full Suite                     │
├──────────────────────────────────────────────────────┤
│                                                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐          │
│  │  Nextcloud│  │ Collabora│  │  Mail    │          │
│  │  (核心)   │  │  (文档)  │  │  (邮件)  │          │
│  └─────┬────┘  └────┬─────┘  └────┬─────┘          │
│        │            │             │                  │
│  ┌─────▼────────────▼─────────────▼─────┐           │
│  │         Nginx Reverse Proxy           │           │
│  │      (SSL/TLS + 域名路由)              │           │
│  └────────────────┬─────────────────────┘           │
│                   │                                  │
│  ┌────────────────▼─────────────────────┐           │
│  │       PostgreSQL + Redis              │           │
│  │       MariaDB (可选)                  │           │
│  └────────────────┬─────────────────────┘           │
│                   │                                  │
│  ┌────────────────▼─────────────────────┐           │
│  │        Docker Storage Volume          │           │
│  │       (持久化数据 + 备份)              │           │
│  └──────────────────────────────────────┘           │
└──────────────────────────────────────────────────────┘
```

## 第一步：服务器准备

### 推荐配置

| 组件 | 最低配置 | 推荐配置 |
|------|----------|----------|
| CPU | 2 核 | 4 核 |
| 内存 | 4 GB | 8 GB |
| 存储 | 40 GB SSD | 100 GB+ NVMe SSD |
| 带宽 | 5 Mbps | 10 Mbps+ |
| 系统 | Ubuntu 22.04/24.04 | Ubuntu 24.04 LTS |

### 初始化设置

```bash
# 更新系统
sudo apt update && sudo apt upgrade -y

# 安装基础工具
sudo apt install -y curl wget git unzip htop net-tools

# 创建非 root 用户
sudo adduser nextcloud
sudo usermod -aG sudo nextcloud
su - nextcloud
```

## 第二步：安装 Docker 和 Docker Compose

```bash
# 卸载旧版本
for pkg in docker.io docker-doc docker-compose podman-docker containerd runc; do
    sudo apt remove -y $pkg 2>/dev/null || true
done

# 安装 Docker
sudo apt install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# 验证安装
docker --version
docker compose version

# 将当前用户加入 docker 组（避免每次 sudo）
sudo usermod -aG docker $USER
newgrp docker
```

## 第三步：项目目录结构

```bash
mkdir -p ~/nextcloud-suite
cd ~/nextcloud-suite

# 创建目录结构
mkdir -p data/{nextcloud,collabora,mail,postgres,redis}
mkdir -p config/nginx
mkdir -p logs
```

## 第四步：编写 Docker Compose 配置

### 主配置文件 `docker-compose.yml`

```yaml
version: '3.8'

services:
  # ========== Nginx 反向代理 ==========
  nginx:
    image: nginx:alpine
    container_name: nc-nginx
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./config/nginx:/etc/nginx/conf.d:ro
      - ./data/nextcloud/html:/var/www/html:ro
      - ./logs/nginx:/var/log/nginx
      - /etc/letsencrypt:/etc/letsencrypt:ro
    depends_on:
      - nextcloud
      - collabora
      - mailserver
    restart: unless-stopped
    networks:
      - nextcloud-net

  # ========== Nextcloud 核心 ==========
  nextcloud:
    image: nextcloud:30-apache
    container_name: nc-nextcloud
    volumes:
      - ./data/nextcloud/html:/var/www/html
      - ./data/nextcloud/data:/var/www/html/data
      - ./data/nextcloud/config:/var/www/html/config
      - ./data/nextcloud/custom_apps:/var/www/html/apps
      - ./data/nextcloud/themes/default:/var/www/html/themes/default
    environment:
      - MYSQL_HOST=db
      - MYSQL_DATABASE=nextcloud
      - MYSQL_USER=nc_user
      - MYSQL_PASSWORD=${NC_DB_PASSWORD}
      - REDIS_HOST=redis
      - NEXTADMIN_TRUSTED_PROXIES=172.18.0.0/16
      - OVERWRITEPROTOCOL=https
      - DEFAULTPHONEREGION=CN
      - NEXTCLOUD_ADMIN_USER=admin
      - NEXTCLOUD_ADMIN_PASSWORD=${NC_ADMIN_PASSWORD}
      - APACHE_DISABLE_REWRITE_IP=1
    depends_on:
      - db
      - redis
    restart: unless-stopped
    networks:
      - nextcloud-net

  # ========== 数据库 ==========
  db:
    image: mariadb:10.11
    container_name: nc-db
    command: --transaction-isolation=READ-COMMITTED --binlog-format=ROW
    restart: unless-stopped
    volumes:
      - ./data/postgres/mariadb:/var/lib/mysql
    environment:
      - MYSQL_ROOT_PASSWORD=${DB_ROOT_PASSWORD}
      - MYSQL_DATABASE=nextcloud
      - MYSQL_USER=nc_user
      - MYSQL_PASSWORD=${NC_DB_PASSWORD}
    networks:
      - nextcloud-net

  # ========== Redis 缓存 ==========
  redis:
    image: redis:7-alpine
    container_name: nc-redis
    restart: unless-stopped
    command: redis-server --requirepass ${REDIS_PASSWORD} --maxmemory 256mb --maxmemory-policy allkeys-lru
    volumes:
      - ./data/redis:/data
    networks:
      - nextcloud-net

  # ========== Collabora 在线文档编辑 ==========
  collabora:
    image: collabora/code:latest
    container_name: nc-collabora
    restart: unless-stopped
    environment:
      - domain=${COLLABORA_DOMAIN}
      - username=admin
      - password=${COLLABORA_ADMIN_PASSWORD}
      - DONT_GEN_SSL_CERTIFICATES=true
    cap_add:
      - MKNOD
    volumes:
      - ./data/collabora:/var/lib/collabora
    networks:
      - nextcloud-net

  # ========== Mail Server (邮件) ==========
  mailserver:
    image: mailserver/docker-mailserver:latest
    container_name: nc-mail
    hostname: mail
    domainname: ${MAIL_DOMAIN}
    ports:
      - "25:25"
      - "143:143"
      - "587:587"
      - "993:993"
    volumes:
      - ./data/mail/maildata:/var/mail
      - ./data/mail/mailstate:/var/mail-state
      - ./data/mail/logs:/var/log/mail
      - ./data/mail/config:/tmp/dms/fix-mymacros
      - ./data/mail/config/sogo:/etc/sogo
      - ./data/mail/config/dovecot:/tmp/dms/dovecot-backup
    environment:
      - ENABLE_SPAMASSASSIN=1
      - SPAMASSASSIN_SPAM_TO_INBOX=1
      - ENABLE_CLAMAV=1
      - ENABLE_FAIL2BAN=1
      - ENABLE_POSTGREY=1
      - ONE_DIR=1
      - DMS_DEBUG=0
      - SSL_TYPE=manual
      - POSTMASTER_ADDRESS=postmaster@${MAIL_DOMAIN}
    restart: unless-stopped
    networks:
      - nextcloud-net

networks:
  nextcloud-net:
    driver: bridge
```

### 环境变量文件 `.env`

```bash
# 生成随机密码
openssl rand -base64 32

# 编辑 .env 文件
cat > .env << 'EOF'
# Nextcloud
NC_ADMIN_PASSWORD=your_strong_admin_password
NC_DB_PASSWORD=your_strong_db_password

# Database
DB_ROOT_PASSWORD=your_root_password

# Redis
REDIS_PASSWORD=your_redis_password

# Collabora
COLLABORA_DOMAIN=nextcloud\.yourdomain\.com
COLLABORA_ADMIN_PASSWORD=collabora_secure_password

# Mail
MAIL_DOMAIN=mail.yourdomain.com
EOF
```

## 第五步：Nginx 反向代理配置

### `config/nginx/nextcloud.conf`

```nginx
# HTTP to HTTPS redirect
server {
    listen 80;
    server_name nextcloud.yourdomain.com;
    
    location /.well-known/acme-challenge/ {
        root /etc/letsencrypt/www;
    }
    
    location / {
        return 301 https://$host$request_uri;
    }
}

# Nextcloud
server {
    listen 443 ssl http2;
    server_name nextcloud.yourdomain.com;
    
    ssl_certificate /etc/letsencrypt/live/nextcloud.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/nextcloud.yourdomain.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    
    # Security headers
    add_header X-Content-Type-Options nosniff;
    add_header X-Frame-Options "SAMEORIGIN";
    add_header X-XSS-Protection "1; mode=block";
    add_header X-Robots-Tag none;
    add_header XDownloadOptions noopen;
    add_header XPermittedCrossDomainPolicies none;
    add_header Referrer-Policy no-referrer;
    
    # Max upload size
    client_max_body_size 10G;
    
    location / {
        proxy_pass http://nextcloud:80;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket support for Talk
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}

# Collabora Online
server {
    listen 443 ssl http2;
    server_name collabora.yourdomain.com;
    
    ssl_certificate /etc/letsencrypt/live/collabora.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/collabora.yourdomain.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    
    location / {
        proxy_pass http://collabora:9980;
        proxy_set_header Host $http_host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        
        # Large buffers for WOPI protocol
        proxy_buffering off;
        proxy_request_buffering off;
    }
}
```

## 第六步：获取 SSL 证书

```bash
# 安装 Certbot
sudo apt install -y certbot python3-certbot-nginx

# 为 Nextcloud 获取证书
sudo certbot certonly --standalone \
  -d nextcloud.yourdomain.com \
  --email your-email@example.com \
  --agree-tos --no-eff-email

# 为 Collabora 获取证书
sudo certbot certonly --standalone \
  -d collabora.yourdomain.com \
  --email your-email@example.com \
  --agree-tos --no-eff-email

# 设置自动续期
sudo crontab -e
# 添加: 0 3 * * * certbot renew --quiet && docker restart nc-nginx
```

## 第七步：启动服务

```bash
cd ~/nextcloud-suite

# 首次启动（可能需要几分钟）
docker compose up -d

# 查看日志
docker compose logs -f nextcloud

# 检查所有容器状态
docker compose ps
```

预期输出：
```
NAME            IMAGE                    STATUS
nc-nginx        nginx:alpine             Up
nc-nextcloud    nextcloud:30-apache      Up
nc-db           mariadb:10.11            Up
nc-redis        redis:7-alpine           Up
nc-collabora    collabora/code:latest    Up
nc-mail         mailserver/docker-mailserver Up
```

## 第八步：初始配置

### 1. 登录 Nextcloud

访问 `https://nextcloud.yourdomain.com`，使用你设置的 admin 账号登录。

### 2. 安装必要应用

进入 **设置 → 应用**，安装以下应用：

| 应用名称 | 功能 | 说明 |
|----------|------|------|
| **Richdocuments** | Collabora 集成 | 启用在线文档编辑 |
| **Mail** | 邮件客户端 | 内置邮件管理 |
| **Talk** | 视频会议 | 音视频通话和聊天 |
| **Deck** | 项目管理 | Trello 风格的看板 |
| **Calendar** | 日历 | 日程管理 |
| **Contacts** | 联系人 | 地址簿 |
| **News** | RSS 阅读器 | 信息聚合 |
| **Photos** | 相册 | 照片管理 |

### 3. 配置 Collabora 集成

在 Nextcloud 中：
1. 进入 **设置 → 管理 → Collabora Online**
2. 填入 Collabora 服务器地址：`https://collabora.yourdomain.com`
3. 勾选"使用自己的服务器"
4. 保存并测试连接

### 4. 配置 Talk（视频会议）

1. 进入 **设置 → Talk**
2. 启用"允许创建房间"
3. 配置 TURN/STUN 服务器（如需穿透 NAT）：
   ```
   STUN: stun.nextcloud.com:443
   ```

### 5. 配置邮件客户端

1. 进入 **设置 → Mail**
2. 添加你的邮箱账户（Gmail、Outlook、或自建 Postfix/Dovecot）
3. 如果使用 IMAP/SMTP 外部邮箱，填写对应服务器信息

## 第九步：性能优化

### Nextcloud 性能调优

编辑 `data/nextcloud/config/config.php`：

```php
<?php
$CONFIG = array(
  // 启用 OPcache
  'opcache.enable' => 1,
  'opcache.memory_consumption' => 256,
  'opcache.interned_strings_buffer' => 8,
  'opcache.max_accelerated_files' => 10000,
  
  // Redis 缓存
  'memcache.local' => '\\OC\\Memcache\\Redis',
  'memcache.locking' => '\\OC\\Memcache\\Redis',
  'redis' => array(
    'host' => 'redis',
    'port' => 6379,
    'password' => '${REDIS_PASSWORD}',
  ),
  
  // PHP 设置
  'php_enable_filelocking' => true,
  'maintenance_window' => 3,
  
  // 文件扫描优化
  'filesystem_check_changes' => 1,
  
  // 日志级别（生产环境建议 1）
  'loglevel' => 1,
  'logfile' => '/var/www/html/data/nextcloud.log',
);
```

### 数据库优化（MariaDB）

创建 `data/postgres/mariadb/init.sql`：

```sql
-- 调整 InnoDB 缓冲池大小（根据内存调整）
SET GLOBAL innodb_buffer_pool_size = 1073741824;  -- 1GB

-- 调整连接数
SET GLOBAL max_connections = 200;

-- 调整查询缓存
SET GLOBAL query_cache_type = 1;
SET GLOBAL query_cache_size = 67108864;  -- 64MB
```

### 浏览器缓存配置

在 Nginx 配置中添加：

```nginx
location ~* \.(css|js|jpg|jpeg|png|gif|ico|svg|woff|woff2|ttf)$ {
    expires 30d;
    add_header Cache-Control "public, immutable";
}
```

## 第十步：备份策略

### 自动化备份脚本

创建 `~/nextcloud-suite/scripts/backup.sh`：

```bash
#!/bin/bash
set -euo pipefail

DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/backup/nextcloud"
RETENTION_DAYS=30

# 确保备份目录存在
mkdir -p "$BACKUP_DIR"

echo "[$(date)] Starting backup..."

# 1. 备份数据库
docker exec nc-db mysqldump -u nc_user -p"${NC_DB_PASSWORD}" nextcloud \
  | gzip > "$BACKUP_DIR/db_nextcloud_$DATE.sql.gz"

# 2. 备份 Nextcloud 数据
docker exec nc-nextcloud tar czf /tmp/nc_data_$DATE.tar.gz \
  -C /var/www/html/data .
docker cp nc-nextcloud:/tmp/nc_data_$DATE.tar.gz \
  "$BACKUP_DIR/nc_data_$DATE.tar.gz"

# 3. 备份配置文件
tar czf "$BACKUP_DIR/config_$DATE.tar.gz" \
  -C "$(dirname "$BACKUP_DIR")" nextcloud-suite/docker-compose.yml \
  nextcloud-suite/.env \
  nextcloud-suite/config/

# 4. 清理过期备份
find "$BACKUP_DIR" -name "*.gz" -mtime +${RETENTION_DAYS} -delete

# 5. 上传到远程存储（可选，使用 rclone）
if command -v rclone &> /dev/null; then
    rclone sync "$BACKUP_DIR" remote:nextcloud-backups/
fi

echo "[$(date)] Backup completed successfully."
```

### 设置定时任务

```bash
crontab -e
# 每天凌晨 2 点执行备份
0 2 * * * /home/nextcloud/nextcloud-suite/scripts/backup.sh >> /var/log/nextcloud-backup.log 2>&1
```

### 灾难恢复流程

```bash
# 1. 停止所有服务
docker compose down

# 2. 恢复数据库
zcat /backup/nextcloud/db_nextcloud_20260712_020000.sql.gz | \
  docker exec -i nc-db mysql -u root -p"${DB_ROOT_PASSWORD}" nextcloud

# 3. 恢复数据
docker compose up -d db redis
sleep 30
docker rm -f nc-nextcloud
docker volume rm nextcloud-suite_nextcloud-data  # 如果有 volume
docker cp /backup/nextcloud/nc_data_*.tar.gz nc-nextcloud:/tmp/
docker exec nc-nextcloud tar xzf /tmp/nc_data_*.tar.gz -C /var/www/html/data

# 4. 重启
docker compose up -d
```

## 常见问题与解决

### Q1: Collabora 无法连接

**症状**：Nextcloud 中打开文档时报错 "无法连接 Collabora Online"

**解决**：
```bash
# 检查 Collabora 容器日志
docker logs nc-collabora

# 确认域名配置正确
# 在 .env 中，COLLABORA_DOMAIN 需要使用正则表达式格式
COLLABORA_DOMAIN=nextcloud\.yourdomain\.com

# 检查防火墙
sudo ufw allow 9980/tcp
```

### Q2: 大文件上传失败

**症状**：超过 2GB 的文件上传中断

**解决**：
```bash
# 修改 php.ini
sudo docker exec -it nc-nextcloud bash
# 编辑 /usr/local/etc/php/conf.d/uploads.ini
upload_max_filesize = 10G
post_max_size = 10G
max_execution_time = 3600
max_input_time = 3600
memory_limit = 512M
```

### Q3: 邮件服务无法收发信

**症状**：SMTP/IMAP 连接失败

**解决**：
```bash
# 检查端口是否开放
sudo ss -tlnp | grep -E ':(25|143|587|993)'

# 检查 DNS MX 记录
dig MX yourdomain.com

# 检查邮件日志
docker logs nc-mail

# 常见原因：
# 1. 云服务商封禁了 25 端口 → 使用 587 STARTTLS
# 2. SPF/DKIM/DMARC 未配置 → 导致邮件被标记为垃圾邮件
# 3. IPv6 问题 → 禁用 IPv6 或配置双栈
```

### Q4: 性能问题

**症状**：大量文件时响应缓慢

**解决**：
```bash
# 1. 启用文件索引
sudo docker exec -it nc-nextcloud php occ files:scan --all

# 2. 清理未使用的文件
sudo docker exec -it nc-nextcloud php occ files:cleanup

# 3. 检查数据库性能
sudo docker exec -it nc-db mysql -u root -p"${DB_ROOT_PASSWORD}" -e "SHOW STATUS LIKE 'Innodb_buffer_pool%';"

# 4. 监控资源使用
docker stats --no-stream
```

## 安全加固清单

| 项目 | 操作 |
|------|------|
| **强密码** | 管理员密码至少 16 位，包含大小写、数字、特殊字符 |
| **2FA** | 启用 TOTP 双因素认证 |
| **IP 白名单** | 管理后台限制特定 IP 访问 |
| **定期更新** | 每月检查并更新 Docker 镜像 |
| **备份加密** | 使用 `gpg` 加密备份文件 |
| **防火墙** | 仅开放 80/443 端口，其他端口仅限内网 |
| **Fail2Ban** | 启用暴力破解防护 |
| **审计日志** | 开启 Nextcloud 审计日志，监控异常行为 |

### 启用 Fail2Ban

```bash
# 安装 fail2ban
sudo apt install -y fail2ban

# 创建 Nextcloud jail
sudo cat > /etc/fail2ban/jail.local << 'EOF'
[nextcloud]
enabled = true
port = http,https
filter = nextcloud
logpath = /var/www/html/data/nextcloud.log
maxretry = 5
bantime = 3600
findtime = 600
EOF

# 创建过滤器
sudo mkdir -p /etc/fail2ban/filter.d
sudo cat > /etc/fail2ban/filter.d/nextcloud.conf << 'EOF'
[Definition]
failregex = ^.*"message":"Login failed:.*$
ignoreregex =
EOF

sudo systemctl enable fail2ban
sudo systemctl restart fail2ban
```

## 成本估算

| 项目 | 月费 | 年费 |
|------|------|------|
| VPS (4核 8GB) | ¥50-150 | ¥600-1800 |
| 域名 | ¥50-100 | ¥50-100 |
| SSL 证书 | 免费 (Let's Encrypt) | 免费 |
| 总成本 | **¥50-150/月** | **¥650-1900/年** |

对比云端 SaaS 服务：
- Google Workspace：¥108/用户/年 × N 人
- Microsoft 365：¥130/用户/年 × N 人
- Dropbox Business：¥168/用户/年 × N 人

对于 **3 人以下团队**，自托管方案成本仅为 SaaS 的 **10-20%**。

## 总结

通过本文的指南，你已经成功搭建了一个完整的个人云办公套件：

✅ **Nextcloud** — 文件同步、分享和协作  
✅ **Collabora** — 在线文档编辑（Writer、Calc、Presentation）  
✅ **Talk** — 私密视频会议和即时通讯  
✅ **Mail** — 统一邮件管理  
✅ **自动化备份** — 每日完整备份 + 远程存储  
✅ **安全加固** — SSL、Fail2Ban、2FA  

这套方案的核心理念是：**数据主权 + 成本控制 + 功能完整**。无论你是个人用户还是小团队，都能在保护隐私的同时获得媲美商业 SaaS 的体验。

---

## Conclusion

In this guide, we've built a complete self-hosted office suite on a VPS using Nextcloud and its ecosystem. You now have:

- **File sync and sharing** with Nextcloud core
- **Online document editing** via Collabora Online
- **Video conferencing** with Nextcloud Talk
- **Email management** with the Mail app
- **Automated backups** with disaster recovery procedures
- **Security hardening** including SSL, Fail2Ban, and 2FA

The total monthly cost is approximately **$7-21 USD**, compared to **$9-14 per user/month** for commercial alternatives. For small teams under 3 people, self-hosting saves **80-90%** while giving you complete control over your data.

The key takeaway: **you don't need to choose between privacy, cost, and functionality**. With Docker and open-source tools, you can have it all.
