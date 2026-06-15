---
title: "VPS 自建 Firefly III 个人财务管理系统：从零搭建你的私人记账平台"
description: "告别第三方记账软件的数据风险——在 VPS 上自建 Firefly III，完全掌控你的财务数据，支持多账户追踪、预算管理和智能报表。"
date: 2026-06-15T10:00:00+08:00
lastmod: 2026-06-15T10:00:00+08:00
slug: "firefly-iii-self-hosted-vps"
tags: ["Firefly III", "财务管理", "自托管", "Docker", "隐私", "个人理财", "VPS"]
categories: ["自托管应用"]
draft: false
image: /images/posts/firefly-iii-self-hosted-vps/featured.png
aliases: [/zh/post/firefly-iii-self-hosted-vps/]
---

## 引言

你是否曾经用过某个记账 App，后来却发现它要把你的消费数据上传到云端？或者更糟——公司倒闭了，你的几年记账记录瞬间消失？

**你的财务数据，应该属于你。**

Firefly III 是一款开源的个人财务管理工具，支持交易记录、预算管理、多币种、报表分析等功能。最重要的是——它运行在你自己的 VPS 上，数据完全私有。

本文将带你从零开始在 VPS 上搭建 Firefly III，包括 Docker 部署、Nginx 反向代理、自动备份和日常维护。

---

## 为什么选择 Firefly III？

市面上有 Mint、YNAB、随手记等记账工具，但它们都有一个共同问题：**你的数据不在你手里**。

| 特性 | Firefly III | 第三方记账 App |
|------|-------------|----------------|
| 数据所有权 | ✅ 完全自有 | ❌ 存储在服务商服务器 |
| 隐私保护 | ✅ 端到端私有 | ❌ 可能被用于广告画像 |
| 一次性成本 | ✅ 免费开源 | ❌ 订阅制收费 |
| 自定义程度 | ✅ 完全可定制 | ❌ 功能固定 |
| 多账户支持 | ✅ 无限账户 | ⚠️ 通常有限制 |
| API 接口 | ✅ RESTful API | ⚠️ 部分提供 |
| 数据导出 | ✅ 完整导出 | ⚠️ 格式受限 |

Firefly III 的核心功能：

- **交易管理** — 记录每一笔收支，支持分类、标签、重复交易
- **预算管理** — 按月/周设置预算，实时追踪进度
- **多账户追踪** — 现金、银行卡、信用卡、投资账户全覆盖
- **报表分析** — 可视化图表展示收支趋势
- **多币种支持** — 内置汇率更新，自动转换
- **API 集成** — 可与 Home Assistant、Grafana 等联动
- **规则引擎** — 自动分类交易，减少手动操作

---

## 系统要求

| 组件 | 最低配置 | 推荐配置 |
|------|----------|----------|
| VPS | 1核 CPU / 512MB RAM | 2核 CPU / 2GB RAM |
| 磁盘 | 5GB 可用空间 | 10GB+ SSD |
| 操作系统 | Ubuntu 22.04 / Debian 12 | Ubuntu 24.04 / Debian 12 |
| 域名 | 可选（建议配置） | 已解析的域名 |

---

## 第一步：准备环境

### 安装 Docker 和 Docker Compose

```bash
# 更新系统
sudo apt update && sudo apt upgrade -y

# 安装 Docker
curl -fsSL https://get.docker.com | sh

# 将当前用户加入 docker 组
sudo usermod -aG docker $USER

# 安装 Docker Compose（如果未预装）
sudo apt install docker-compose-plugin -y

# 验证安装
docker --version
docker compose version
```

### 创建项目目录结构

```bash
mkdir -p /opt/fireflyiii/{data,storage,uploads}
cd /opt/fireflyiii
```

---

## 第二步：编写 Docker Compose 配置

创建 `docker-compose.yml`：

```yaml
services:
  firefly:
    image: fireflyiii/core:latest
    container_name: fireflyiii
    restart: unless-stopped
    ports:
      - "127.0.0.1:8080:8080"
    environment:
      - APP_ENV=production
      - APP_KEY=base64:YOUR_RANDOM_KEY_HERE
      - APP_URL=http://your-domain.com
      - TRUSTED_PROXIES=**
      - WEBPACK_SECURE=false
      - DB_CONNECTION=mysql
      - DB_HOST=mysql
      - DB_PORT=3306
      - DB_DATABASE=firefly
      - DB_USERNAME=firefly
      - DB_PASSWORD=YOUR_DB_PASSWORD_HERE
      - MAIL_MAILER=smtp
      - MAIL_HOST=smtp.your-mail-server.com
      - MAIL_PORT=587
      - MAIL_USERNAME=noreply@your-domain.com
      - MAIL_PASSWORD=YOUR_MAIL_PASSWORD
      - MAIL_ENCRYPTION=tls
      - MAIL_FROM_ADDRESS=noreply@your-domain.com
      - MAIL_FROM_NAME="Firefly III"
    volumes:
      - ./storage/upload:/var/www/html/storage/upload
      - ./storage/logs:/var/www/html/storage/logs
    depends_on:
      mysql:
        condition: service_healthy

  mysql:
    image: mysql:8.0
    container_name: fireflyiii-mysql
    restart: unless-stopped
    environment:
      - MYSQL_ROOT_PASSWORD=YOUR_ROOT_PASSWORD_HERE
      - MYSQL_DATABASE=firefly
      - MYSQL_USER=firefly
      - MYSQL_PASSWORD=YOUR_DB_PASSWORD_HERE
    volumes:
      - mysql_data:/var/lib/mysql
    command: >
      --default-authentication-plugin=caching_sha2_password
      --character-set-server=utf8mb4
      --collation-server=utf8mb4_unicode_ci
      --max-connections=200
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost", "-u", "firefly", "-p${MYSQL_PASSWORD}"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  mysql_data:
```

> **⚠️ 重要提示：** 在部署前，务必替换所有 `YOUR_*_HERE` 占位符。特别是 `APP_KEY`，可以使用以下命令生成：
> ```bash
> openssl rand -base64 32
> ```

---

## 第三步：启动服务

```bash
cd /opt/fireflyiii
docker compose up -d

# 查看日志
docker compose logs -f firefly

# 等待初始化完成（首次启动可能需要几分钟）
```

初始化完成后，访问 `http://your-domain.com`，使用默认凭据登录：

- 用户名：`firefly@fireflyiii.org`
- 密码：`password`

**登录后请立即修改密码！**

---

## 第四步：配置 Nginx 反向代理

使用 HTTPS 保护你的财务数据至关重要。

```nginx
server {
    listen 443 ssl http2;
    server_name your-domain.com;

    # SSL 证书（使用 Let's Encrypt）
    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    # SSL 安全配置
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 1d;
    ssl_stapling on;
    ssl_stapling_verify on;

    # 安全头
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    client_max_body_size 50M;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
    }

    # 静态资源缓存
    location ~* \.(css|js|png|jpg|jpeg|gif|ico|svg|woff|woff2)$ {
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
}

# HTTP 重定向到 HTTPS
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$host$request_uri;
}
```

获取 SSL 证书：

```bash
sudo certbot certonly --nginx -d your-domain.com
sudo certbot renew --dry-run  # 测试自动续期
```

---

## 第五步：配置邮件通知

Firefly III 支持通过邮件发送预算提醒、报告等通知。

### 使用 SMTP 配置

在 `docker-compose.yml` 中配置 `MAIL_*` 环境变量：

```yaml
environment:
  - MAIL_MAILER=smtp
  - MAIL_HOST=smtp.gmail.com
  - MAIL_PORT=587
  - MAIL_USERNAME=your-email@gmail.com
  - MAIL_PASSWORD=your-app-password
  - MAIL_ENCRYPTION=tls
  - MAIL_FROM_ADDRESS=your-email@gmail.com
  - MAIL_FROM_NAME="Firefly III"
```

> **Gmail 用户注意：** 需要使用「应用专用密码」而非普通密码。先在 Google 账号中开启两步验证，然后生成应用专用密码。

### 使用 Mailpit（开发环境）

如果不想配置真实邮箱，可以本地搭建 Mailpit 进行测试：

```yaml
services:
  mailpit:
    image: axllent/mailpit:latest
    container_name: fireflyiii-mailpit
    restart: unless-stopped
    ports:
      - "127.0.0.1:8025:8025"
    environment:
      - MP_MAX_MESSAGES=5000
      - MP_DATABASE=/data/mailpit.db
    volumes:
      - mailpit_data:/data

volumes:
  mailpit_data:
```

然后将 `MAIL_HOST` 改为 `mailpit`，`MAIL_PORT` 改为 `1025`。

---

## 第六步：设置自动备份

### 数据库备份

创建备份脚本 `/opt/fireflyiii/backup.sh`：

```bash
#!/bin/bash
set -euo pipefail

BACKUP_DIR="/opt/fireflyiii/backups"
DATE=$(date +%Y%m%d_%H%M%S)
CONTAINER="fireflyiii-mysql"
DB_USER="firefly"
DB_PASS="YOUR_DB_PASSWORD_HERE"
DB_NAME="firefly"

# 创建备份目录
mkdir -p "$BACKUP_DIR"

# 备份数据库
docker exec "$CONTAINER" mysqldump -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" \
  | gzip > "$BACKUP_DIR/firefly_$DATE.sql.gz"

# 删除 30 天前的备份
find "$BACKUP_DIR" -name "firefly_*.sql.gz" -mtime +30 -delete

echo "Backup completed: firefly_$DATE.sql.gz"
```

添加定时任务：

```bash
chmod +x /opt/fireflyiii/backup.sh

# 每天凌晨 2 点备份
echo "0 2 * * * /opt/fireflyiii/backup.sh >> /opt/fireflyiii/backup.log 2>&1" | crontab -
```

### 文件备份

```bash
# 备份上传文件和配置文件
tar czf "$BACKUP_DIR/firefly_files_$DATE.tar.gz" \
  -C /opt/fireflyiii \
  --exclude='backups' \
  --exclude='mysql_data' \
  storage upload docker-compose.yml
```

### 远程备份（推荐）

```bash
# 同步到远程服务器
rsync -avz --delete /opt/fireflyiii/backups/ user@remote-server:/backups/fireflyiii/

# 或使用 rclone 同步到云存储
rclone copy /opt/fireflyiii/backups/ remote:fireflyiii-backups/ --max-age 30d
```

---

## 第七步：日常使用技巧

### 1. 设置交易规则（自动化分类）

Firefly III 的规则引擎可以自动标记交易：

```
规则示例：
- 如果描述包含 "星巴克" → 分类为「餐饮」，标签为「咖啡」
- 如果描述包含 "工资" → 分类为「收入」，标签为「月薪」
- 如果金额 > 1000 且分类为「购物」 → 标签为「大额支出」
```

### 2. 导入银行对账单

支持 CSV、OFX、QIF 格式：

```bash
# 从银行导出 CSV 后，在 Web 界面导入
# 设置映射规则，自动匹配字段
```

### 3. 设置预算提醒

- 进入「预算」页面
- 按月设置各类别预算上限
- 开启邮件提醒，当支出达到 80%、100% 时通知你

### 4. 使用 API 集成

Firefly III 提供完整的 RESTful API：

```bash
# 获取 API Token（在 Web 界面生成）
# 查询最近 7 天的交易
curl -H "Authorization: Bearer YOUR_TOKEN" \
  "https://your-domain.com/api/v1/transactions?date_start=2026-06-08&date_end=2026-06-15"

# 与 Grafana 联动，用 InfluxDB + Telegraf 做长期趋势分析
```

### 5. 多币种支持

```
- 添加支持的货币
- 设置汇率来源（ECB 或自定义）
- 交易时自动按当日汇率转换
```

---

## 第八步：安全加固

### 1. 启用两步验证

在「设置」→「安全」中开启 TOTP 两步验证，推荐使用 Authy 或 Google Authenticator。

### 2. 限制访问 IP

在 Nginx 配置中添加 IP 白名单：

```nginx
allow 203.0.113.0/24;  # 你的 IP 段
deny all;
```

### 3. 定期更新

```bash
# 每周检查更新
docker compose pull && docker compose up -d

# 或使用 Watchtower 自动更新
docker run -d \
  --name watchtower \
  -v /var/run/docker.sock:/var/run/docker.sock \
  containrrr/watchtower \
  --cleanup --schedule "0 3 * * 0" \
  fireflyiii
```

### 4. 防火墙配置

```bash
# 只开放必要端口
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

---

## 常见问题

### Q: 首次登录后无法修改某些设置？

Firefly III 首次登录后需要运行迁移命令：

```bash
docker exec -it fireflyiii php artisan firefly-iii:upgrade-database
```

### Q: 如何迁移到新服务器？

```bash
# 旧服务器导出
docker exec fireflyiii-mysql mysqldump -u firefly -p firefly > dump.sql
tar czf files.tar.gz storage upload

# 新服务器导入
docker compose up -d
docker exec -i fireflyiii-mysql mysql -u firefly -p firefly < dump.sql
tar xzf files.tar.gz -C /opt/fireflyiii/
```

### Q: 数据库越来越大怎么办？

```bash
# 清理日志表（谨慎操作）
docker exec -it fireflyiii php artisan db:optimize

# 归档旧数据
docker exec -it fireflyiii php artisan firefly-iii:archive-old-transactions
```

### Q: 如何恢复备份？

```bash
# 停止服务
docker compose down

# 恢复数据库
gunzip < backups/firefly_20260615_020000.sql.gz | docker exec -i fireflyiii-mysql mysql -u firefly -p firefly

# 恢复文件
tar xzf backups/firefly_files_20260615.tar.gz -C /opt/fireflyiii/

# 重启
docker compose up -d
```

---

## 总结

Firefly III 是一个功能强大、完全私有的个人财务管理方案。通过自建，你获得了：

- **数据主权** — 所有财务数据存储在本地，不受第三方限制
- **完全自由** — 自定义分类、标签、规则，完全按照你的习惯
- **零成本** — 开源免费，只需 VPS 费用
- **生态整合** — 通过 API 与 Home Assistant、Grafana 等工具联动

对于注重隐私、希望完全掌控自己财务数据的用户来说，Firefly III 是目前最好的自托管解决方案之一。

---

## 参考链接

- [Firefly III 官方文档](https://docs.firefly-iii.org/)
- [GitHub 仓库](https://github.com/firefly-iii/firefly-iii)
- [Docker Hub](https://hub.docker.com/r/fireflyiii/core)
- [Firefly III 论坛](https://forums.firefly-iii.org/)
