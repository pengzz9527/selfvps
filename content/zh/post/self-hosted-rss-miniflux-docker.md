---
title: "自建 RSS 阅读器：Miniflux + Docker 搭建轻量级订阅平台"
description: "告别信息焦虑，用 Miniflux 搭建属于自己的 RSS 阅读器。Docker 一键部署、支持 15+ 源格式、移动端友好，从此掌控你的信息流，不再被算法投喂。"
date: 2026-09-05T08:00:00+08:00
slug: "self-hosted-rss-miniflux-docker"
tags: ["RSS", "Miniflux", "Docker", "自托管", "信息聚合", "反算法", "生产力工具"]
categories: ["自托管应用"]
image: "/images/posts/self-hosted-rss-miniflux-docker/featured.png"
draft: false
---

## 为什么自建 RSS 阅读器？

你有没有这样的体验——打开社交媒体，原本只想看两眼，结果刷了半小时；算法不断推送你"可能感兴趣"的内容，却让你失去了主动选择信息的能力。

**RSS（Really Simple Syndication）** 是互联网早期的信息订阅协议，它让你**主动获取**内容，而非被动接受推荐。自建 RSS 阅读器的核心价值：

- **信息自主权**：只看你关注的源，算法无法操控你的时间线
- **隐私保护**：不追踪你的阅读行为，不卖给广告商
- **跨平台同步**：手机、电脑、平板，随时随地访问
- **免费无广告**：一次部署，终身使用，无需订阅费

## 方案对比

| 方案 | 部署难度 | 功能丰富度 | 资源占用 | 适合人群 |
|------|---------|-----------|---------|---------|
| Miniflux | ⭐⭐ 简单 | ⭐⭐⭐ 中等 | ⭐ 极低 | 追求简洁高效 |
| FreshRSS | ⭐⭐⭐ 中等 | ⭐⭐⭐⭐ 丰富 | ⭐⭐ 中等 | 需要高级功能 |
| Tiny Tiny RSS | ⭐⭐⭐ 中等 | ⭐⭐⭐⭐ 丰富 | ⭐⭐ 中等 | 老牌用户偏好 |
| Feedly（SaaS） | ⭐ 一键即用 | ⭐⭐⭐⭐⭐ 最全 | ❌ 依赖第三方 | 不愿维护服务器 |

**Miniflux** 是一个 Go 编写的轻量级 RSS 阅读器，数据库仅支持 PostgreSQL 或 SQLite，API 完整，支持所有主流客户端。对于个人 VPS 用户，它是最佳选择。

## 第一步：准备服务器

确保你的 VPS 满足以下要求：

```bash
# 检查 Docker 是否已安装
docker --version
docker-compose --version

# 如果没有，一键安装
curl -fsSL https://get.docker.com | sh
```

推荐使用 Debian 12 或 Ubuntu 22.04+，至少 512MB 内存即可运行。

## 第二步：Docker Compose 部署 Miniflux

创建项目目录并编写配置文件：

```bash
mkdir -p ~/miniflux && cd ~/miniflux
```

创建 `docker-compose.yml`：

```yaml
services:
  miniflux:
    image: miniflux/miniflux:v30
    container_name: miniflux
    restart: unless-stopped
    ports:
      - "8080:8080"
    environment:
      # 数据库配置（使用 SQLite 最简单）
      DATABASE_URL: postgres://miniflux:CHANGE-ME@db:5432/miniflux?sslmode=disable
      DATABASE_DRIVER: postgres
      RUN_MIGRATIONS: 1
      CREATE_ADMIN: 1
      ADMIN_USERNAME: admin
      ADMIN_PASSWORD: YourStrongPassword123!
      # 时区设置
      USER_TIMEZONE: Asia/Shanghai
      # 自动刷新间隔（分钟）
      REFRESH_FREQUENCY: 30
      # 每日最大请求数（防止被封）
      FETCHER_REQUESTS_PER_SECOND: 1
      FETCHER_BURST_SIZE: 5
    depends_on:
      db:
        condition: service_healthy
    networks:
      - miniflux-net

  db:
    image: postgres:16-alpine
    container_name: miniflux-db
    restart: unless-stopped
    volumes:
      - pgdata:/var/lib/postgresql/data
    environment:
      POSTGRES_USER: miniflux
      POSTGRES_PASSWORD: CHANGE-ME
      POSTGRES_DB: miniflux
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U miniflux -d miniflux"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - miniflux-net

volumes:
  pgdata:

networks:
  miniflux-net:
```

启动服务：

```bash
docker-compose up -d
```

等待几秒后，访问 `http://你的VPS_IP:8080` 即可看到 Miniflux 界面。

## 第三步：配置 Nginx 反向代理（可选但推荐）

生产环境强烈建议使用域名 + HTTPS。以 Nginx 为例：

```nginx
server {
    listen 80;
    server_name rss.yourdomain.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name rss.yourdomain.com;

    ssl_certificate     /etc/letsencrypt/live/rss.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/rss.yourdomain.com/privkey.pem;

    location / {
        proxy_pass         http://127.0.0.1:8080;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
    }
}
```

使用 Certbot 自动申请 SSL 证书：

```bash
apt install certbot python3-certbot-nginx -y
certbot --nginx -d rss.yourdomain.com
```

## 第四步：添加订阅源

Miniflux 支持多种源格式：

| 格式 | 示例 | 说明 |
|------|------|------|
| RSS 2.0 | https://example.com/feed | 最常见 |
| Atom | https://example.com/atom | 博客常用 |
| JSON Feed | https://example.com/feed.json | 现代格式 |
| Twitter/X | @username | 关注特定用户动态 |
| YouTube | UCxxx (频道ID) | 视频更新通知 |
| Reddit | r/linux |  subreddit 订阅 |
| Hacker News | hackernews | 技术新闻 |
| GitHub Releases | github/releases | 软件更新通知 |

在 Miniflux 界面中点击 **Add Feeds**，粘贴 URL 即可。也可以批量导入 OPML 文件。

## 第五步：配置多用户与权限

Miniflux 支持多用户系统，适合团队协作：

```bash
# 通过 API 创建普通用户（限制只能读自己订阅）
curl -X POST http://localhost:8080/users \
  -H "Content-Type: application/json" \
  -H "X-Auth-Token: YOUR_ADMIN_TOKEN" \
  -d '{"username":"user1","password":"password123","role":"user"}'
```

角色权限：

| 角色 | 权限 |
|------|------|
| admin | 管理所有用户和设置 |
| user | 管理自己的订阅，不可见他人数据 |
| restricted | 只读，无法添加/删除源 |

## 第六步：移动端访问

Miniflux 提供完整的 **JSON API**，支持所有主流 RSS 客户端：

- **iOS**: Reeder、Unread、Feed Wrangler
- **Android**: FeedMe、Readably、Bright
- **macOS**: NetNewsWire、Feedy
- **跨平台**: Thunderbird、Inoreader（导入 API）

以 Reeder 为例，添加账户时选择 **Miniflux**，输入你的域名、用户名和密码即可同步。

## 第七步：自动化与备份

### 定时备份数据库

```bash
# 添加到 crontab
0 3 * * * docker exec miniflux-db pg_dump miniflux -U miniflux | gzip > /backup/miniflux-$(date +\%Y\%m\%d).sql.gz
```

### 监控容器健康

```yaml
# docker-compose.yml 中添加
labels:
  - "com.centurylinklabs.watchtower.enable=true"
```

使用 Watchtower 自动更新镜像：

```bash
docker run -d \
  --name watchtower \
  -v /var/run/docker.sock:/var/run/docker.sock \
  containrrr/watchtower \
  --cleanup --interval 3600 \
  miniflux
```

## 成本分析

自建 Miniflux 的成本几乎为零：

| 项目 | 费用 |
|------|------|
| VPS（最低配） | ¥30-50/月 |
| 域名 | ¥50/年 |
| SSL 证书 | 免费（Let's Encrypt） |
| **总计** | **≈ ¥80/年** |

对比 Feedly Premium（¥108/年/设备）或 Unread（¥198/年），自建方案在部署完成后**零边际成本**。

## 常见问题

**Q: 订阅太多源，刷新慢怎么办？**

A: 调整 `REFRESH_FREQUENCY` 和 `FETCHER_REQUESTS_PER_SECOND` 参数，限制请求频率避免被封。对不常用的源可以设置为 120 分钟刷新一次。

**Q: 如何迁移到 Miniflux？**

A: 支持 OPML 导入导出，从任何 RSS 阅读器迁移只需一键。

**Q: 移动端推送通知如何实现？**

A: Miniflux 本身不提供推送，可结合 ntfy.sh 或 Pushover 实现新文章通知。

## 总结

自建 RSS 阅读器是对抗信息焦虑最有效的方式之一。Miniflux 以其极简的设计、低资源占用和完整的 API，成为个人 VPS 用户的理想选择。花一小时部署，享受永久的信息自主权。

现在就开始吧——订阅你真正关心的内容，让算法失去对你的控制。
