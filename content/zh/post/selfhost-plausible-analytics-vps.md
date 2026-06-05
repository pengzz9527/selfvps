---
title: "自托管 Plausible Analytics 到 VPS：隐私友好的 Google Analytics 替代方案"
description: "一步步教你用 Docker 在 VPS 上部署 Plausible Analytics——开源、隐私优先的网站统计工具，彻底告别 Google Analytics 的数据收集，同时节省订阅费用"
date: 2026-06-05T10:00:00+08:00
lastmod: 2026-06-05T10:00:00+08:00
slug: "selfhost-plausible-analytics-vps"
image: /images/posts/selfhost-plausible-analytics-vps/featured.png
tags: ["Plausible", "Analytics", "自托管", "Docker", "隐私", "VPS", "开源", "建站"]
categories: ["自托管"]
aliases: [/zh/post/selfhost-plausible-analytics-vps/]
---

## 引言

网站分析工具是了解用户行为的必需品，但 Google Analytics 存在几个痛点：

- **隐私问题**：Google 收集大量用户数据，违反 GDPR 等隐私法规
- **性能影响**：GA 脚本臃肿，拖慢页面加载速度
- **费用高昂**：GA4 虽然免费，但 GA360 企业版价格不菲；许多隐私友好的 SaaS 分析工具（如 Fathom、Simple Analytics）每月收费 $10-30
- **广告拦截器屏蔽**：Google Analytics 被各种广告拦截器广泛屏蔽，数据准确性受影响

**Plausible Analytics** 是一款开源、轻量、隐私优先的网站统计工具，具有以下优势：

| 特性 | Plausible | Google Analytics |
|------|-----------|-----------------|
| 脚本大小 | < 1KB | 45KB+ |
| GDPR 合规 | ✅ 原生支持（无 Cookie） | ⚠️ 需要配置 |
| 自托管 | ✅ 开源免费 | ❌ 仅 SaaS |
| 广告拦截器屏蔽 | ⚠️ 部分屏蔽 | ✅ 大量屏蔽 |
| 数据所有权 | ✅ 完全掌控 | ❌ Google 拥有 |
| 月成本（自托管） | 约 $3-5（VPS 费用） | 免费/付费 |

本文教你用 Docker 在 VPS 上部署 Plausible，支持 PostgreSQL + ClickHouse 双数据库架构，并配置 Nginx/Caddy 反向代理和 HTTPS。

---

## 前置要求

- 一台 VPS（推荐最低配置：1 vCPU, 1GB RAM, 20GB SSD）
- 一个域名（如 `analytics.yourdomain.com`）
- Docker 和 Docker Compose（v2+）
- 基础的 Linux 操作知识

## 1. 准备环境

### 安装 Docker

```bash
# 安装 Docker（如已安装可跳过）
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# 安装 Docker Compose v2
sudo apt-get update
sudo apt-get install -y docker-compose-plugin

# 验证安装
docker --version
docker compose version
```

### 设置目录结构

```bash
# 创建 Plausible 目录
mkdir -p ~/plausible && cd ~/plausible

# 目录结构
# ~/plausible/
# ├── docker-compose.yml
# ├── plausible-conf.env
# ├── clickhouse/
# │   └── (数据目录，自动创建)
# └── plausible/
#     └── (数据目录，自动创建)
```

## 2. 配置 Docker Compose

Plausible 需要三个服务：
1. **Plausible** — 主应用（Elixir 编写）
2. **PostgreSQL** — 存储元数据（用户、站点配置）
3. **ClickHouse** — 存储分析事件数据（列式数据库，专为分析优化）

创建 `docker-compose.yml`：

```yaml
version: '3.8'

services:
  plausible:
    image: plausible/analytics:v2.1
    restart: unless-stopped
    command: sh -c "sleep 10 && /entrypoint.sh db migrate && /entrypoint.sh run"
    ports:
      - "127.0.0.1:8000:8000"
    depends_on:
      - plausible_db
      - plausible_events_db
    env_file:
      - plausible-conf.env
    volumes:
      - plausible_data:/var/lib/plausible/data
      - ./plausible/geoip:/var/lib/plausible/geoip:ro

  plausible_db:
    image: postgres:16-alpine
    restart: unless-stopped
    volumes:
      - db_data:/var/lib/postgresql/data
    environment:
      - POSTGRES_DB=plausible
      - POSTGRES_USER=plausible
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-plausible_secret_password}

  plausible_events_db:
    image: clickhouse/clickhouse-server:24.3-alpine
    restart: unless-stopped
    volumes:
      - event_data:/var/lib/clickhouse
      - ./clickhouse/clickhouse-config.xml:/etc/clickhouse-server/config.d/logging.xml:ro
    environment:
      - CLICKHOUSE_DB=plausible_events
      - CLICKHOUSE_USER=plausible
      - CLICKHOUSE_PASSWORD=${CLICKHOUSE_PASSWORD:-plausible_secret_password}

volumes:
  db_data:
  event_data:
  plausible_data:
```

### ClickHouse 日志配置

创建 `clickhouse/clickhouse-config.xml` 以减少日志输出：

```bash
mkdir -p clickhouse
```

```xml
<clickhouse>
  <logger>
    <level>warning</level>
    <log>/var/log/clickhouse-server/clickhouse-server.log</log>
    <errorlog>/var/log/clickhouse-server/clickhouse-server.err.log</errorlog>
    <size>10M</size>
    <count>3</count>
  </logger>
</clickhouse>
```

## 3. 配置环境变量

创建 `plausible-conf.env`：

```bash
cat > plausible-conf.env << 'EOF'
# ── 基础配置 ──
BASE_URL=https://analytics.yourdomain.com
SECRET_KEY_BASE=$(openssl rand -base64 48)
DISABLE_REGISTRATION=true

# ── 数据库配置 ──
DATABASE_URL=postgres://plausible:plausible_secret_password@plausible_db:5432/plausible
CLICKHOUSE_DATABASE_URL=http://plausible:plausible_secret_password@plausible_events_db:8123/plausible_events

# ── 性能优化 ──
# 限制单个查询的事件数，防止 OOM
CLICKHOUSE_QUERY_TIMEOUT_MS=30000
# 并行查询数
DATABASE_POOL_SIZE=15

# ── 邮件配置（可选，用于报告）─
# MAILER_ADAPTER=Bamboo.SMTPAdapter
# SMTP_HOST_ADDR=smtp.example.com
# SMTP_HOST_PORT=587
# SMTP_USER_NAME=user@example.com
# SMTP_USER_PWD=password
# SMTP_HOST_SSL_ENABLED=true
# MAILER_EMAIL=analytics@yourdomain.com
EOF
```

> ⚠️ **重要**：将 `BASE_URL` 替换为你的实际域名，将 `POSTGRES_PASSWORD` 和 `CLICKHOUSE_PASSWORD` 替换为强密码。

### 生成密钥

```bash
# 生成 SECRET_KEY_BASE
openssl rand -base64 48

# 生成数据库密码
openssl rand -base64 24
```

## 4. 启动 Plausible

```bash
# 启动所有服务
docker compose up -d

# 查看启动日志
docker compose logs -f

# 检查服务状态
docker compose ps

# 验证 Plausible 是否运行
curl -s http://127.0.0.1:8000 | head -5
```

启动后，访问 `http://your-vps-ip:8000` 应该能看到 Plausible 的界面。

### 创建管理员账号

首次访问会要求注册账号。由于 `DISABLE_REGISTRATION=true`，之后其他人无法再注册。

```bash
# 或者通过 CLI 直接创建用户
docker compose exec plausible /entrypoint.sh db create-admin \
  --email admin@yourdomain.com \
  --name "管理员" \
  --password "your-strong-password"
```

## 5. 配置反向代理和 HTTPS

### 方案 A：使用 Caddy（推荐，自动 HTTPS）

Caddy 会自动申请 Let's Encrypt 证书，配置极简。

```bash
# 安装 Caddy
sudo apt-get install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt-get update
sudo apt-get install caddy
```

创建 `/etc/caddy/Caddyfile`：

```caddy
analytics.yourdomain.com {
    reverse_proxy 127.0.0.1:8000
    
    # 安全头部
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"
        X-Content-Type-Options nosniff
        X-Frame-Options DENY
        X-XSS-Protection "1; mode=block"
        Referrer-Policy strict-origin-when-cross-origin
    }
    
    # 日志
    log {
        output file /var/log/caddy/analytics.log
    }
}
```

```bash
# 测试配置
sudo caddy validate --config /etc/caddy/Caddyfile

# 重载 Caddy
sudo systemctl reload caddy

# 查看证书状态
sudo caddy cert-info analytics.yourdomain.com
```

### 方案 B：使用 Nginx

```nginx
# /etc/nginx/sites-available/analytics.yourdomain.com
upstream plausible {
    server 127.0.0.1:8000;
}

server {
    listen 80;
    server_name analytics.yourdomain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name analytics.yourdomain.com;

    ssl_certificate     /etc/letsencrypt/live/analytics.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/analytics.yourdomain.com/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;

    # 安全头部（同 Caddy 配置）

    location / {
        proxy_pass http://plausible;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_redirect off;
        proxy_buffering off;
        client_max_body_size 10m;
    }
}
```

```bash
# 启用站点
sudo ln -s /etc/nginx/sites-available/analytics.yourdomain.com /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

## 6. 添加网站并部署追踪脚本

### 在 Plausible 中添加站点

1. 访问 `https://analytics.yourdomain.com`
2. 登录管理员账号
3. 点击「Add website」
4. 输入你的域名（如 `selfvps.net`）
5. 复制追踪脚本

### 部署追踪脚本

将以下代码添加到你的网站 `<head>` 标签中：

```html
<script defer data-domain="yourdomain.com" src="https://analytics.yourdomain.com/js/script.js"></script>
```

对于 Hugo 博客，在 `layouts/partials/head.html` 中添加：

```html
{{ if not .Site.IsServer }}
<script defer data-domain="{{ .Site.BaseURL | urlize }}" src="https://analytics.yourdomain.com/js/script.js"></script>
{{ end }}
```

### 自定义事件追踪

Plausible 支持自定义事件和目标追踪：

```javascript
// 追踪按钮点击
plausible('Signup', { props: { method: 'Email' }});

// 追踪 404 页面
plausible('404', { props: { path: document.location.pathname }});

// 追踪文件下载
document.querySelectorAll('a[href$=".pdf"]').forEach(link => {
    link.addEventListener('click', () => {
        plausible('Download', { props: { file: link.href }});
    });
});
```

## 7. 性能优化

### 为 Plausible VPS 做优化

```bash
# ── 系统级优化 ──

# 1. 增加系统文件描述符限制
echo "fs.file-max = 100000" | sudo tee -a /etc/sysctl.conf

# 2. 网络优化
cat >> /etc/sysctl.conf << 'EOF'
net.core.somaxconn = 65535
net.ipv4.tcp_max_syn_backlog = 65535
net.ipv4.tcp_tw_reuse = 1
net.ipv4.tcp_fastopen = 3
EOF
sudo sysctl -p

# 3. 设置 Swap（1GB RAM VPS 建议）
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

### Docker 资源限制

在 `docker-compose.yml` 中为关键服务设置资源限制：

```yaml
services:
  plausible:
    # ... 其他配置 ...
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: '0.75'
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  plausible_events_db:
    # ... 其他配置 ...
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: '0.5'
```

### ClickHouse 性能调优

创建 `clickhouse/clickhouse-performance.xml`：

```xml
<clickhouse>
  <max_memory_usage>300000000</max_memory_usage>
  <max_server_memory_usage>400000000</max_server_memory_usage>
  <max_concurrent_queries>10</max_concurrent_queries>
  <merge_tree>
    <max_suspicious_broken_parts>5</max_suspicious_broken_parts>
    <parts_to_throw_insert>300</parts_to_throw_insert>
    <parts_to_delay_insert>150</parts_to_delay_insert>
  </merge_tree>
</clickhouse>
```

## 8. 数据备份与恢复

### 自动化备份脚本

创建 `backup.sh`：

```bash
#!/bin/bash
# Plausible 数据备份脚本

BACKUP_DIR="/root/backups/plausible"
DATE=$(date +%Y%m%d_%H%M%S)
RETENTION_DAYS=30

mkdir -p $BACKUP_DIR

echo "==> 备份 PostgreSQL 数据库..."
docker compose exec -T plausible_db pg_dumpall -U plausible | gzip > "$BACKUP_DIR/plausible_db_$DATE.sql.gz"

echo "==> 备份 ClickHouse 数据..."
docker compose exec -T plausible_events_db clickhouse-client --query "BACKUP TABLE plausible_events.* TO 'file:///var/lib/clickhouse/backup/backup_$DATE'" 2>/dev/null || {
    echo "⚠️ ClickHouse 备份失败，改用数据目录备份..."
    tar czf "$BACKUP_DIR/clickhouse_data_$DATE.tar.gz" -C /var/lib/docker/volumes/$(basename $(pwd))_event_data/_data .
}

echo "==> 清理旧备份（保留 $RETENTION_DAYS 天）..."
find $BACKUP_DIR -name "*.sql.gz" -mtime +$RETENTION_DAYS -delete
find $BACKUP_DIR -name "*.tar.gz" -mtime +$RETENTION_DAYS -delete

echo "✅ 备份完成！备份文件：$BACKUP_DIR"
ls -lh $BACKUP_DIR
```

```bash
chmod +x backup.sh

# 设置定时备份（每天凌晨 3 点）
(crontab -l 2>/dev/null; echo "0 3 * * * cd ~/plausible && ./backup.sh >> /var/log/plausible-backup.log 2>&1") | crontab -
```

### 恢复备份

```bash
# 停止服务
docker compose down

# 恢复 PostgreSQL
gunzip -c plausible_db_20260605_030000.sql.gz | docker compose exec -T plausible_db psql -U plausible

# 重启服务
docker compose up -d
```

## 9. 监控与维护

### 检查 Plausible 健康状态

```bash
# 健康检查端点
curl -s https://analytics.yourdomain.com/health

# 查看资源使用
docker stats --no-stream plausible plausible_db plausible_events_db

# 查看日志
docker compose logs --tail=100 plausible

# 检查数据库连接
docker compose exec plausible_db pg_isready -U plausible
```

### 升级 Plausible

```bash
# 备份数据
./backup.sh

# 拉取最新镜像
docker compose pull

# 重启服务
docker compose up -d

# 执行数据库迁移（自动在启动时完成）
docker compose logs -f plausible | grep "migration"
```

### 集成 Uptime Kuma 监控

```yaml
# 在 Uptime Kuma 中添加
# 监控地址: https://analytics.yourdomain.com/health
# 预期状态码: 200
# 通知方式: Telegram / Email
```

## 10. 常见问题排查

### Q: 访问 Plausible 页面空白或 502

```bash
# 检查服务是否运行
docker compose ps

# 查看错误日志
docker compose logs plausible | tail -50

# 检查数据库连接
docker compose exec plausible_db psql -U plausible -d plausible -c "SELECT 1"

# 常见原因：数据库未就绪时 Plausible 已启动
docker compose restart plausible
```

### Q: ClickHouse 内存不足

```bash
# 查看 ClickHouse 日志
docker compose logs plausible_events_db | grep -i "memory\|OOM\|error"

# 解决方案：限制 ClickHouse 内存使用
# 编辑 clickhouse-performance.xml 中的 max_memory_usage
```

### Q: 数据不显示/追踪不到

```bash
# 1. 检查追踪脚本是否正确部署
curl -s https://analytics.yourdomain.com/js/script.js | head -5

# 2. 检查 DNS 解析
dig analytics.yourdomain.com

# 3. 查看 Plausible 是否有收到事件
docker compose logs plausible | grep "tracking\|event\|pageview"

# 4. 检查是否有 CSP 限制
# 在 Nginx/Caddy 中添加:
# Content-Security-Policy: script-src 'self' https://analytics.yourdomain.com;
```

### Q: 数据库空间不足

```bash
# 查看 Docker 卷使用情况
docker system df -v

# 进入 ClickHouse 清理旧数据
docker compose exec plausible_events_db clickhouse-client \
  --query "SELECT table, formatReadableSize(sum(bytes)) FROM system.parts WHERE active GROUP BY table"

# 设置数据保留时间（在 plausible-conf.env 中添加）
# CLICKHOUSE_DATA_RETENTION_DAYS=90
```

## 成本分析

| 项目 | 月费用 |
|------|--------|
| VPS（1C1G，如 RackNerd $18/年） | $1.5 |
| 域名（如 `analytics.yourdomain.com`） | $0（子域名） |
| **总计** | **~$1.5/月** |

对比第三方 Plausible Cloud 定价：**$9/月**（10K 页面浏览量）→ 自托管节省 **83%**！

> 💡 **省钱建议**：如果你已经有 VPS 在运行其他服务，Plausible 可以直接部署在同一台 VPS 上，边际成本几乎为零。

## 总结

通过本文，你已经成功在 VPS 上自托管了 Plausible Analytics：

✅ 用 Docker Compose 部署了 Plausible + PostgreSQL + ClickHouse
✅ 配置了 Caddy/Nginx 反向代理和自动 HTTPS
✅ 在网站上部署了追踪脚本
✅ 设置了自动备份和监控

Plausible 是 Google Analytics 的最佳自托管替代方案。它不仅保护用户隐私，还让你完全掌控自己的数据——这正是自托管的精神所在。

### 下一步

- 📊 设置邮件报告：配置 SMTP，接收每周/每月分析报告
- 🔗 集成 Slack/Telegram：通过 Webhook 接收实时数据推送
- 🎯 设置目标追踪：监控注册、下载、购买等转化事件
- 🚀 扩展到多站点：用同一个实例管理所有网站的分析数据

## 参考资源

- [Plausible 官方自托管文档](https://plausible.io/docs/self-hosting)
- [Plausible GitHub](https://github.com/plausible/analytics)
- [ClickHouse 官方文档](https://clickhouse.com/docs)
- [Caddy 官方文档](https://caddyserver.com/docs/)
- [Docker Compose V2 文档](https://docs.docker.com/compose/)

---

*本文发布于 [SelfVPS 指南](https://selfvps.net)，转载请注明出处。*
