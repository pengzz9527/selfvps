---
title: "自建 Bitwarden 密码管理器：Docker 部署全流程，替代付费密码管理方案"
description: "在自家 VPS 上部署 Bitwarden RS，免费开源、数据自控，彻底摆脱 1Password、LastPass 等付费订阅的高昂费用，同时享受更快的同步速度和更高的隐私保障。"
date: 2026-09-17
lastmod: 2026-09-17
slug: "vps-bitwarden-self-hosted"
image: "/images/posts/vps-bitwarden-self-hosted/featured.png"
tags: ["Bitwarden", "密码管理", "自托管", "Docker", "网络安全", "开源", "VPS", "隐私"]
categories: ["自托管工具"]
aliases: [/zh/post/vps-bitwarden-self-hosted/]
---

## 引言

你有多少个密码？

10 个？50 个？还是 100 个以上？

每个网站、每个应用、每个服务都要密码——邮箱、银行、社交、工作系统……你不可能记住所有密码，也不可能所有地方都用同一个（那太危险了）。

于是你买了 **1Password** 或 **LastPass**，每月付 $3-$4，数据存在别人服务器上。直到某天——

- LastPass 被黑，800 万用户的密码泄露；
- 1Password 涨价到 $36/年/人，家庭版更贵；
- 你发现所谓的"安全加密"，密钥其实掌握在服务商手里。

**为什么要把数字身份的钥匙交给别人？**

Bitwarden 开源版提供了一个完全不同的选择：**在自己服务器上运行密码管理器，数据完全自控，零成本，无限用户。** 本文带你从零部署一套完整的 Bitwarden 自托管方案。

---

## 1. 为什么选择自托管 Bitwarden？

| 对比项 | 付费云方案（1Password/LastPass） | 自托管 Bitwarden |
|--------|-------------------------------|-----------------|
| **成本** | $36-48/年/人 | **免费**（仅需 VPS 费用） |
| **数据隐私** | 加密密钥在服务商手中 | **密钥完全在你手中** |
| **用户数量** | 按人头收费 | **无限制** |
| **同步速度** | 经过海外服务器 | **本地/近端，极快** |
| **功能完整性** | 部分功能需付费 | **全部功能免费开放** |
| **审计能力** | 无法审计 | **可完全审计代码与数据** |
| **合规性** | 依赖第三方 | **满足自身合规要求** |
| **离线使用** | 受限 | **完全支持** |

自托管 Bitwarden 的核心优势：**你不是在"租用"一个密码管理工具，你是在"拥有"它。** 这意味着：

- 你的密码库只存在于你的服务器
- 没有人能访问你的加密数据，包括 Bitwarden 官方
- 你可以随时导出、迁移、审计你的全部数据
- 团队、家庭、朋友——想用多少人就用多少人

---

## 2. 系统要求

Bitwarden 自托管版对资源的需求非常低：

| 组件 | 最低配置 | 推荐配置 |
|------|---------|---------|
| **VPS 内存** | 512MB | 1GB+ |
| **磁盘空间** | 1GB | 5GB+（随数据增长） |
| **CPU** | 1 核 | 1-2 核 |
| **操作系统** | Ubuntu 20.04+ / Debian 11+ | 同上 |
| **域名** | 需要（用于 HTTPS） | 子域名即可 |
| **Docker** | 20.10+ | 最新版 |

你的 VPS 不需要很高配置。事实上，Bitwarden 官方推荐的最低配置就是 512MB 内存——这意味着即使是 $5/月的轻量 VPS 也能跑起来。

> **提示**：如果你已经有 Running 的 VPS，可以直接在上面加 Docker Compose，无需额外购买服务器。

---

## 3. 架构概览

```
┌──────────────────────────────────────────────────────┐
│                    你的域名 (vault.yourdomain.com)     │
│                          │                           │
│                    ┌─────▼─────┐                     │
│                    │  Nginx    │ ← HTTPS 反向代理     │
│                    │  + Certbot│    自动续期 Let's    │
│                    └─────┬─────┘    Encrypt 证书       │
│                          │                           │
│              ┌───────────┼───────────┐               │
│              │           │           │               │
│        ┌─────▼─────┐ ┌──▼────┐ ┌───▼────┐         │
│        │ Bitwarden │ │ MySQL │ │ SSH fwd│         │
│        │  (API)    │ │/PgSQL │ │(admin) │         │
│        └─────┬─────┘ └───┬───┘ └───┬────┘         │
│              │           │           │             │
│        ┌─────▼───────────▼───────────▼─────┐       │
│        │         Docker Compose             │       │
│        │      (三容器一体化部署)             │       │
│        └────────────────────────────────────┘       │
└──────────────────────────────────────────────────────┘
```

核心组件：
- **Bitwarden 容器**：提供 Web Vault、API、Identity、Notifications 四大服务
- **MySQL 8**：存储加密后的密码数据（也可以用 PostgreSQL）
- **Nginx**：反向代理 + HTTPS 终止
- **Certbot**：自动申请和续期 SSL 证书

---

## 4. 一键部署（Docker Compose）

### 4.1 安装 Docker 和 Docker Compose

```bash
# Ubuntu/Debian
curl -fsSL https://get.docker.com | sh
docker compose plugin install  # Docker 23+ 自带，否则：
# apt install docker-compose-plugin
```

### 4.2 创建部署目录

```bash
mkdir -p ~/bitwarden && cd ~/bitwarden
```

### 4.3 生成关键环境变量

你需要两个核心值：**master_password**（管理员密码）和 **roaringfortress**（安装密钥）。

```bash
# 生成随机安装密钥（用于注册新管理员）
docker run --rm bitwardenrs/server:latest gen-install-token

# 生成随机 master password（或者你自己设一个强密码）
openssl rand -base64 32
```

### 4.4 创建 .env 配置文件

```bash
cat > .env << 'EOF'
# ===== 基础配置 =====
BITWARDENSSL_ENABLED=true
BITWARDENSSL_CERT_FILE=/etc/ssl/vault.crt
BITWARDENSSL_KEY_FILE=/etc/ssl/vault.key

# ===== 域名 =====
DOMAIN=vault.yourdomain.com

# ===== 数据库（MySQL）=====
MYSQL_ROOT_PASSWORD=$(openssl rand -base64 32)
MYSQL_DATABASE=bitwarden
MYSQL_USER=bitwarden
MYSQL_PASSWORD=$(openssl rand -base64 32)

# ===== 管理密码（初始管理员密码）=====
ADMIN_TOKEN=$(openssl rand -base64 48)

# ===== 邮件配置（用于密码重置通知）=====
SMTP_HOST=smtp.yourdomain.com
SMTP_PORT=587
SMTP_FROM=noreply@yourdomain.com
SMTP_SSL=true
SMTP_USERNAME=your_smtp_user
SMTP_PASSWORD=your_smtp_pass

# ===== 功能开关 =====
SIGNUPS_ALLOWED=false
INVITATIONS_ALLOWED=false
EOF
```

> **安全提醒**：永远不要把 `.env` 文件提交到 Git 仓库！建议在 `.gitignore` 中添加 `.env`。

### 4.5 创建 docker-compose.yml

```yaml
version: "3.8"

services:
  # ── Bitwarden 主服务 ──
  bitwarden:
    image: bitwardenrs/server:latest
    container_name: bitwarden
    restart: unless-stopped
    ports:
      - "127.0.0.1:8089:80"
    environment:
      WEBSITE_HOSTNAME: "${DOMAIN}"
      SIGNUPS_ALLOWED: "false"
      ADMIN_TOKEN: "${ADMIN_TOKEN}"
      MYSQL_HOST: db
      MYSQL_PORT: 3306
      MYSQL_DATABASE: bitwarden
      MYSQL_USER: bitwarden
      MYSQL_PASSWORD: "${MYSQL_PASSWORD}"
      SMTP_HOST: "${SMTP_HOST}"
      SMTP_PORT: "${SMTP_PORT}"
      SMTP_FROM: "${SMTP_FROM}"
      SMTP_SSL: "${SMTP_SSL}"
      SMTP_USERNAME: "${SMTP_USERNAME}"
      SMTP_PASSWORD: "${SMTP_PASSWORD}"
    volumes:
      - ./bwdata/icons:/opt/bitwarden/web/assets/icons
    depends_on:
      - db

  # ── MySQL 数据库 ──
  db:
    image: mysql:8.0
    container_name: bitwarden-db
    restart: unless-stopped
    command: --default-authentication-plugin=mysql_native_password
    environment:
      MYSQL_ROOT_PASSWORD: "${MYSQL_ROOT_PASSWORD}"
      MYSQL_DATABASE: bitwarden
      MYSQL_USER: bitwarden
      MYSQL_PASSWORD: "${MYSQL_PASSWORD}"
    volumes:
      - ./bwdata/db:/var/lib/mysql
    # 限制只接受本地连接
    networks:
      default:
        aliases:
          - db

networks:
  default:
    driver: bridge
```

### 4.6 启动服务

```bash
# 创建数据目录
mkdir -p bwdata/db bwdata/icons

# 启动
docker compose up -d

# 查看日志
docker compose logs -f bitwarden
```

等待约 30-60 秒，服务就绪后你会看到类似输出：

```
bitwarden    | [2026-09-17 10:00:00][][info]: Server listening on http://0.0.0.0:80
bitwarden    | [2026-09-17 10:00:00][][info]: Administration token: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

---

## 5. 配置 Nginx 反向代理与 HTTPS

### 5.1 安装 Nginx 和 Certbot

```bash
apt update && apt install -y nginx certbot python3-certbot-nginx
```

### 5.2 创建 Nginx 配置

```bash
cat > /etc/nginx/sites-available/vault.yourdomain.com << 'EOF'
server {
    listen 80;
    server_name vault.yourdomain.com;

    location / {
        return 301 https://$host$request_uri;
    }
}

server {
    listen 443 ssl http2;
    server_name vault.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/vault.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/vault.yourdomain.com/privkey.pem;
    ssl_trusted_certificate /etc/letsencrypt/live/vault.yourdomain.com/chain.pem;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers on;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_session_timeout 1d;
    ssl_session_cache shared:SSL:10m;
    ssl_session_tickets off;
    ssl_stapling on;
    ssl_stapling_verify on;

    client_max_body_size 128M;

    location / {
        proxy_pass http://127.0.0.1:8089;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
        proxy_request_buffering off;
    }

    location /notifications/hub {
        proxy_pass http://127.0.0.1:8089;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_buffering off;
    }

    location /notifications/hub/negotiate {
        proxy_pass http://127.0.0.1:8089;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_buffering off;
    }
}
EOF

ln -s /etc/nginx/sites-available/vault.yourdomain.com /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
```

### 5.3 申请 SSL 证书

```bash
# 确保域名 A 记录已指向你的 VPS IP
# 然后申请证书
certbot --nginx -d vault.yourdomain.com --non-interactive --agree-tos --email your@email.com

# 设置自动续期（Certbot 通常已自动配置，验证一下）
systemctl status certbot.timer
```

### 5.4 重启 Bitwarden 以启用 HTTPS

```bash
docker compose restart bitwarden
```

现在访问 `https://vault.yourdomain.com` 应该能看到 Bitwarden 的登录页面。

---

## 6. 创建管理员账户并导入密码

### 6.1 获取管理员注册令牌

```bash
docker exec bitwarden cat /etc/bitwarden/admin_token
# 或者从 .env 文件中读取 ADMIN_TOKEN
grep ADMIN_TOKEN .env
```

### 6.2 创建管理员账户

```bash
# 使用 CLI 创建管理员（推荐方式）
docker exec -it bitwarden /usr/local/bin/bw register \
  --masterpasswordhash "$(echo -n 'your_master_password' | sha256sum | cut -d' ' -f1)" \
  --email "admin@yourdomain.com" \
  --token "$(grep ADMIN_TOKEN .env | cut -d'=' -f2)"
```

### 6.3 登录 Web 界面

1. 打开 `https://vault.yourdomain.com`
2. 使用刚才创建的管理员账户登录
3. 进入 **工具 → 导入数据** 页面
4. 选择来源格式（1Password、LastPass、 KeePass、Chrome 等）
5. 上传导出的加密文件，完成迁移

### 6.4 关闭公开注册

```bash
# 确认 Signups 已禁用（在 .env 中设置）
grep SIGNUPS_ALLOWED .env
# 输出应为: SIGNUPS_ALLOWED=false

# 重启服务使配置生效
docker compose restart bitwarden
```

---

## 7. 客户端配置

Bitwarden 客户端覆盖所有平台：

| 平台 | 下载地址 |
|------|---------|
| **Web 界面** | `https://vault.yourdomain.com` |
| **桌面（Windows/Mac/Linux）** | [bitwarden.com/download](https://bitwarden.com/download/) |
| **手机（iOS/Android）** | App Store / Google Play 搜索 "Bitwarden" |
| **浏览器插件** | Chrome / Firefox / Edge 扩展商店 |
| **命令行** | `brew install bitwarden-cli` 或 `snap install bitwarden` |

### 修改服务器地址（关键步骤）

默认情况下，Bitwarden 客户端连接的是官方服务器 `vault.bitwarden.com`。你需要手动改为自己的 VPS：

**方法一：通过配置修改**

桌面客户端 → 设置 → 高级 → Server Uri：
```
https://vault.yourdomain.com
```

**方法二：修改 hosts 文件（不推荐，仅临时）**

```bash
echo "123.45.67.89  vault.bitwarden.com" | sudo tee -a /etc/hosts
```

**方法三：DNS 重定向（生产环境推荐）**

在你的 DNS 服务商处，将 `vault.bitwarden.com` 解析到你的 VPS IP（仅当你的域包含 `bitwarden.com` 时可行，一般用户不适用）。

**推荐方法一**：在客户端设置中修改 Server Uri 即可。

---

## 8. 安全加固

自托管虽然方便，但安全责任完全在你。以下是必要的加固措施：

### 8.1 启用双因素认证（2FA）

管理员登录后，立即为所有账户启用 TOTP 2FA：

1. 进入 **设置 → 安全 → 双因素认证**
2. 选择 **认证器应用**
3. 扫描二维码绑定 Google Authenticator / Authy
4. **务必保存好恢复码！**

### 8.2 限制管理员访问

```bash
# 仅允许特定 IP 访问管理面板
# 在 Nginx 配置中添加
location /admin {
    allow 1.2.3.4;  # 你的管理 IP
    deny all;
    proxy_pass http://127.0.0.1:8089;
}
```

### 8.3 定期备份

```bash
# 创建备份脚本
cat > ~/bitwarden/backup.sh << 'EOF'
#!/bin/bash
BACKUP_DIR="/backup/bitwarden"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p $BACKUP_DIR

# 备份数据库
docker exec bitwarden-db mysqldump -u bitwarden -p${MYSQL_PASSWORD} bitwarden > $BACKUP_DIR/db_$DATE.sql
# 备份 Bitwarden 数据目录
tar czf $BACKUP_DIR/bwdata_$DATE.tar.gz /root/bitwarden/bwdata/
# 删除 30 天前的备份
find $BACKUP_DIR -name "*.sql" -mtime +30 -delete
find $BACKUP_DIR -name "bwdata_*.tar.gz" -mtime +30 -delete
echo "Backup completed: $DATE"
EOF

chmod +x ~/bitwarden/backup.sh

# 添加到 crontab（每天凌晨 3 点备份）
(crontab -l 2>/dev/null; echo "0 3 * * * /root/bitwarden/backup.sh") | crontab -
```

### 8.4 防火墙配置

```bash
# 仅开放必要端口
ufw default deny incoming
ufw allow 80/tcp    # HTTP（重定向到 HTTPS）
ufw allow 443/tcp   # HTTPS
ufw allow 22/tcp    # SSH
ufw enable
```

### 8.5 禁用不必要的功能

在 `.env` 中：

```bash
# 禁用注册（已设置）
SIGNUPS_ALLOWED=false
# 禁用邀请
INVITATIONS_ALLOWED=false
# 禁用密码生成历史（减少数据暴露面）
PASSWORD_HISTORY_ENABLED=false
```

---

## 9. 常见问题与排查

### 问题 1：无法登录，提示"密码错误"

Bitwarden 使用 PBKDF2 密钥派生。确认你使用的是**主密码**（master password）而非邮箱密码。如果忘记密码：

```bash
# 重置管理员密码（需要服务器访问权限）
docker exec -it bitwarden /usr/local/bin/bw reset-admin-password \
  --newpassword "YourNewMasterPassword"
```

### 问题 2：客户端无法连接服务器

检查以下几点：
1. 服务器 URL 是否正确（必须是 `https://` 开头）
2. SSL 证书是否有效（`curl -I https://vault.yourdomain.com`）
3. 防火墙是否放行了 443 端口
4. Docker 容器是否正常运行（`docker compose ps`）

### 问题 3：附件上传失败

Bitwarden 默认将附件存储在本地文件系统。确保：
- `bwdata` 目录有写入权限
- `client_max_body_size` 在 Nginx 配置中设置得足够大
- 磁盘空间充足

如需使用对象存储（S3 兼容），可挂载 MinIO：

```yaml
# 在 docker-compose.yml 中添加
  minio:
    image: minio/minio:latest
    command: server /data --console-address ":9001"
    ports:
      - "127.0.0.1:9000:9000"
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: $(openssl rand -base64 32)
    volumes:
      - ./bwdata/minio:/data
```

然后在 Bitwarden 环境变量中添加：

```bash
ATTACHMENTS_EXTENSION__S3__BUCKET=bitwarden-attachments
ATTACHMENTS_EXTENSION__S3__REGION=us-east-1
ATTACHMENTS_EXTENSION__S3__USE_PATH_STYLE=false
ATTACHMENTS_EXTENSION__S3__URL=http://127.0.0.1:9000
ATTACHMENTS_EXTENSION__S3__KEY=minioadmin
ATTACHMENTS_EXTENSION__S3__SECRET=your_minio_secret
```

### 问题 4：数据库体积增长过快

MySQL 数据文件会随使用增长。建议：
- 定期执行 `docker exec bitwarden-db mysql -u root -p${MYSQL_ROOT_PASSWORD} bitwarden -e "OPTIMIZE TABLE cards; OPTIMIZE TABLE send; OPTIMIZE TABLE attachment;"`
- 监控磁盘使用：`docker exec bitwarden-db du -sh /var/lib/mysql/`

---

## 10. 升级与维护

### 升级 Bitwarden

```bash
cd ~/bitwarden
docker compose pull
docker compose up -d
```

每次升级前建议先备份：

```bash
./backup.sh
```

### 监控服务状态

```bash
# 查看容器状态
docker compose ps

# 查看实时日志
docker compose logs -f

# 查看资源占用
docker stats bitwarden
```

正常情况下，Bitwarden 容器占用约 **80-150MB 内存**，非常轻量。

---

## 总结

自托管 Bitwarden 的核心价值在于：**你将密码管理的控制权从服务商手中夺回。**

花费不到 $5/月的 VPS 费用，你获得了：
- ✅ **完全的数据主权** — 你的密码只有你能解密
- ✅ **无限用户免费** — 全家桶、团队版都不额外收费
- ✅ **更快的体验** — 本地/DDoS 防护下的低延迟同步
- ✅ **零供应商锁定** — 数据随时可导出为标准格式
- ✅ **100% 功能免费** — 没有付费墙，没有功能阉割

从 LastPass 或 1Password 迁移过来的过程非常平滑——只需导出 CSV/加密文件，然后在 Bitwarden 中导入即可。花 30 分钟部署，之后每年省下数百元的订阅费。

**你的密码，你的服务器，你的规则。**

---

## 相关资源

- [Bitwarden 官方文档](https://help.bitwarden.com/article/self-hosting/)
- [Bitwarden GitHub 仓库](https://github.com/dani-garcia/vaultwarden)
- [Let's Encrypt 证书申请](https://letsencrypt.org/)
- [Docker Compose 最佳实践](https://docs.docker.com/compose/best-practices/)
