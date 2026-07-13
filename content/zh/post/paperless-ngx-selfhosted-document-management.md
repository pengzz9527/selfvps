---
title: "Paperless-ngx 自托管文档管理系统 — 用 Docker 搭建你的私人数字档案库"
description: "在 VPS 上从零部署 Paperless-ngx，实现纸质文档数字化、OCR 智能识别、全文搜索与标签分类。告别混乱的文件存储，打造高效的知识管理体系。"
date: 2026-07-13T10:00:00+08:00
lastmod: 2026-07-13T10:00:00+08:00
slug: "paperless-ngx-selfhosted-document-management"
tags: ["Paperless-ngx", "Docker", "OCR", "文档管理", "自托管", "知识管理", "VPS", "开源"]
categories: ["自托管"]
draft: false
image: /images/posts/paperless-ngx-selfhosted-document-management/featured.png
aliases: [/zh/post/paperless-ngx-selfhosted-document-management/]
---

## 什么是 Paperless-ngx？

**Paperless-ngx** 是一款开源的文档管理系统（DMS），专为个人和小团队设计。它能将纸质文档扫描后上传，自动进行 OCR 文字识别，并支持全文检索、标签分类、元数据提取等功能。

> **核心优势**：完全自托管，数据掌握在自己手中；Docker 一键部署；支持多用户协作；API 完善可集成自动化流程。

### 为什么选择自托管文档管理？

| 方案 | 隐私性 | 成本 | 灵活性 | 学习曲线 |
|------|--------|------|--------|----------|
| Google Drive/Dropbox | ⭐⭐⭐ | 高（按存储收费） | ⭐⭐ | 低 |
| Evernote/Notion | ⭐⭐ | 中高 | ⭐⭐⭐ | 低 |
| Paperless-ngx | ⭐⭐⭐⭐⭐ | 极低（仅服务器成本） | ⭐⭐⭐⭐⭐ | 中 |

## 系统要求

| 组件 | 最低配置 | 推荐配置 |
|------|----------|----------|
| CPU | 1 核 | 2 核+ |
| 内存 | 1 GB | 2 GB+ |
| 存储 | 10 GB SSD | 50 GB+ SSD |
| 操作系统 | Ubuntu 22.04+ | Ubuntu 24.04 LTS |

## 第一步：环境准备

### 安装 Docker 和 Docker Compose

```bash
# 更新系统
sudo apt update && sudo apt upgrade -y

# 安装 Docker
curl -fsSL https://get.docker.com | sudo sh

# 将当前用户加入 docker 组
sudo usermod -aG docker $USER

# 安装 Docker Compose
sudo apt install docker-compose-plugin -y

# 验证安装
docker --version
docker compose version
```

### 创建项目目录

```bash
mkdir -p ~/paperless-ngx/{data,media,export,pgdata}
cd ~/paperless-ngx
```

## 第二步：编写 Docker Compose 配置

创建 `docker-compose.yml`：

```yaml
services:
  broker:
    image: docker.io/library/redis:7
    restart: unless-stopped
    volumes:
      - redis_data:/data

  db:
    image: docker.io/library/postgres:16
    restart: unless-stopped
    volumes:
      - pgdata:/var/lib/postgresql/data
    environment:
      POSTGRES_DB: paperless
      POSTGRES_USER: paperless
      POSTGRES_PASSWORD: paperless_secret

  webserver:
    image: ghcr.io/paperless-ngx/paperless-ngx:latest
    restart: unless-stopped
    depends_on:
      - db
      - broker
      - gotenberg
      - tika
    ports:
      - "8000:8000"
    volumes:
      - data:/usr/src/paperless/data
      - media:/usr/src/paperless/media
      - export:/usr/src/paperless/export
      - consume:/usr/src/paperless/consume
    environment:
      PAPERLESS_REDIS: redis://broker:6379
      PAPERLESS_DBHOST: db
      PAPERLESS_DBUSER: paperless
      PAPERLESS_DBPASSWORD: paperless_secret
      PAPERLESS_ADMIN_USER: admin
      PAPERLESS_ADMIN_PASSWORD: admin_password_change_me
      PAPERLESS_URL: http://your-domain.com
      # OCR 语言设置
      PAPERLESS_OCR_LANGUAGES: chi_sim, eng
      # 时区
      TZ: Asia/Shanghai

  gotenberg:
    image: docker.io/gotenberg/gotenberg:8
    restart: unless-stopped

  tika:
    image: docker.io/apache/tika:latest
    restart: unless-stopped

volumes:
  data:
  media:
  export:
  consume:
  pgdata:
  redis_data:
```

## 第三步：启动服务

```bash
# 启动所有服务
docker compose up -d

# 查看日志确认启动成功
docker compose logs -f webserver
```

等待约 1-2 分钟，服务完全启动后访问 `http://your-vps-ip:8000`。

### 默认登录信息

- **用户名**：`admin`
- **密码**：`admin_password_change_me`（首次登录后立即修改！）

## 第四步：配置反向代理（Nginx + HTTPS）

生产环境务必使用 HTTPS，以下为 Nginx 配置示例：

```nginx
server {
    listen 443 ssl http2;
    server_name docs.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/docs.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/docs.yourdomain.com/privkey.pem;

    client_max_body_size 50M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket 支持
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}

server {
    listen 80;
    server_name docs.yourdomain.com;
    return 301 https://$host$request_uri;
}
```

获取 SSL 证书（使用 Certbot）：

```bash
sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d docs.yourdomain.com
```

## 第五步：文档导入与 OCR

### 批量导入文档

1. 将扫描的 PDF/JPG/PNG 放入 `consume` 目录，或通过 Web 界面上传
2. Paperless-ngx 会自动执行 OCR 处理
3. 识别完成后，文档出现在库中，可进行搜索

### 配置 OCR 语言

在 `docker-compose.yml` 中修改 `PAPERLESS_OCR_LANGUAGES`：

```yaml
environment:
  # 中文简体 + 英文
  PAPERLESS_OCR_LANGUAGES: chi_sim, eng
  # 如需繁体中文
  # PAPERLESS_OCR_LANGUAGES: chi_tra, eng
  # 如需多语言
  # PAPERLESS_OCR_LANGUAGES: chi_sim, eng, jpn, kor
```

### 标签与分类

Paperless-ngx 支持多级标签体系：

- **来源标签**：发票、合同、收据、信件、证件
- **自定义标签**：按项目、部门、时间等维度分类
- **文档类型**：自动从文件名或内容推断

## 第六步：自动化工作流

### 使用 API 自动归档

Paperless-ngx 提供完整的 REST API：

```python
import requests

API_TOKEN = "your-api-token"
BASE_URL = "https://docs.yourdomain.com/api"

headers = {
    "Authorization": f"Token {API_TOKEN}",
}

# 上传文档
with open("invoice_202607.pdf", "rb") as f:
    response = requests.post(
        f"{BASE_URL}/documents/",
        headers=headers,
        files={"document": f},
        data={
            "title": "2026年7月发票",
            "tags": "1,2",  # 标签ID
            "correspondent": "3",  # 对应方ID
        }
    )
    print(response.json())
```

### 定时扫描文件夹

```bash
#!/bin/bash
# auto_archive.sh - 监控指定文件夹并自动上传

WATCH_DIR="/home/user/incoming"
API_TOKEN="your-token"
BASE_URL="https://docs.yourdomain.com/api"

inotifywait -m -r -e close_write "$WATCH_DIR" |
while read path action file; do
    if [[ "$file" =~ \.(pdf|jpg|png|tiff)$ ]]; then
        curl -s -X POST "$BASE_URL/documents/" \
            -H "Authorization: Token $API_TOKEN" \
            -F "document=@${path}${file}" \
            -F "title=$(basename ${file})" \
            -F "tags=1"
        echo "Archived: $file"
    fi
done
```

## 数据备份策略

### 完整备份脚本

```bash
#!/bin/bash
# backup_paperless.sh

BACKUP_DIR="/backup/paperless"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p "$BACKUP_DIR/$DATE"

# 备份数据库
docker exec paperless-ngx-db_1 pg_dump -U paperless paperless \
    > "$BACKUP_DIR/$DATE/database.sql"

# 备份媒体文件
docker cp paperless-ngx-webserver_1:/usr/src/paperless/media \
    "$BACKUP_DIR/$DATE/media"

# 备份配置文件
docker cp paperless-ngx-webserver_1:/usr/src/paperless/data \
    "$BACKUP_DIR/$DATE/data"

# 压缩
tar czf "$BACKUP_DIR/paperless_$DATE.tar.gz" \
    "$BACKUP_DIR/$DATE"

# 清理临时文件
rm -rf "$BACKUP_DIR/$DATE"

# 保留最近30天备份
find "$BACKUP_DIR" -name "paperless_*.tar.gz" -mtime +30 -delete
```

### 自动化定时备份

```bash
# 每天凌晨2点备份
echo "0 2 * * * /path/to/backup_paperless.sh" | crontab -
```

## 性能优化建议

### 调整 OCR 并发数

```yaml
environment:
  # 根据CPU核心数调整
  PAPERLESS_CONSUMER_WORKERS: 4
  PAPERLESS_TASK_WORKERS: 4
```

### 存储优化

- 使用 SSD 存储提升 OCR 速度
- 定期清理 `consume` 目录中的原始文件
- 启用文档压缩：`PAPERLESS_COMPRESS_IMAGES=true`

### 内存优化

对于低配 VPS（1GB 内存），可限制 Tika 内存使用：

```yaml
tika:
  environment:
    JVM_OPTS: "-Xms128m -Xmx256m"
```

## 安全加固

### 修改默认凭据

首次登录后立即：
1. 修改管理员密码
2. 创建普通用户账号
3. 禁用匿名访问

### 防火墙配置

```bash
# 仅允许 HTTPS
sudo ufw allow 443/tcp
sudo ufw allow 22/tcp
sudo ufw enable
```

### API 密钥管理

- 为每个应用/用户生成独立的 API token
- 定期轮换 API 密钥
- 使用环境变量存储敏感信息，不硬编码

## 常见问题排查

### OCR 识别率低

```bash
# 检查日志
docker compose logs gotenberg
docker compose logs webserver

# 确保安装了中文字体
docker exec -it paperless-ngx-webserver_1 \
    apt-get update && apt-get install -y fonts-noto-cjk
```

### 上传大文件失败

调整 Nginx 配置：

```nginx
client_max_body_size 100M;
proxy_request_buffering off;
```

### 服务无法启动

```bash
# 检查磁盘空间
df -h

# 检查内存
free -m

# 重启服务
docker compose down
docker compose up -d
```

## 结语

Paperless-ngx 是自建文档管理的优秀选择，它将复杂的文档处理流程简化为一次上传。配合 Docker 部署，即使是技术新手也能在 30 分钟内完成搭建。

**关键要点回顾**：
- ✅ Docker Compose 一键部署，依赖自动管理
- ✅ OCR 支持中英文等多语言识别
- ✅ REST API 可实现自动化归档
- ✅ 完整的数据备份策略保障数据安全
- ✅ 通过 Nginx + HTTPS 保证传输安全

数据是你最宝贵的资产——选择自托管，把控制权握在自己手中。
