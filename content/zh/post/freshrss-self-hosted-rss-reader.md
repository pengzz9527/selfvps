---
title: "告别信息碎片化：用 FreshRSS 在 VPS 上搭建自托管 RSS 阅读器"
description: "FreshRSS + Docker 打造你的个人信息中枢，告别算法推荐，掌控阅读主动权"
date: 2026-06-08T10:00:00+08:00
lastmod: 2026-06-08T10:00:00+08:00
slug: "freshrss-self-hosted-rss-reader"
image: /images/posts/freshrss-self-hosted-rss-reader/featured.png
tags: ["FreshRSS", "RSS", "自托管", "Docker", "信息聚合", "阅读", "隐私"]
categories: ["自托管"]
aliases: [/zh/post/freshrss-self-hosted-rss-reader/]
---

## 为什么你还需要 RSS？

在这个算法为王、信息流永远刷不完的时代，我们看似拥有了海量信息，实际上却陷入了**信息茧房**。

- 抖音、小红书用推荐算法喂养你，你看到的全是它想让你看到的；
- Twitter/X 的时间线被置顶内容、付费推广和机器人账号污染；
- 你关注的博主发了新文章，你可能一周都刷不到。

**RSS（Really Simple Syndication）** 是互联网上最后一片没有被资本和算法完全吞噬的净土。它让你**主动获取**信息，而不是被被动投喂。

而你缺的只是一个靠谱的 RSS 阅读器——自建在 VPS 上，数据完全掌控在自己手里。

## 为什么选择 FreshRSS？

市面上 RSS 阅读器不少，为什么是 FreshRSS？

| 特性 | FreshRSS | Feedly | Inoreader |
|------|----------|--------|-----------|
| 部署方式 | 自托管 | SaaS | SaaS |
| 数据归属 | 完全私有 | 平台拥有 | 平台拥有 |
| 免费方案 | 无限制 | 仅 100 源 | 仅 150 源 |
| API 支持 | ✅ 全功能 | 付费 | 付费 |
| 平台扩展 | ✅ 丰富 | ❌ | ❌ |
| 支持平台 | 任何 VPS | 网页/APP | 网页/APP |

FreshRSS 的核心优势：**数据在你手里**，插件生态丰富（AI 摘要、翻译、去重），资源占用极低（512MB VPS 绰绰有余）。

## 准备工作

你需要：

- 一台 VPS（1 核 1G 起步）
- Docker + Docker Compose 已安装
- 一个域名（可选，但强烈建议）
- 10 分钟空闲时间

## 一键部署 FreshRSS

### 第一步：创建 Docker Compose 配置

在你的 VPS 上创建目录并写入配置：

```bash
mkdir -p /opt/freshrss && cd /opt/freshrss
```

创建 `docker-compose.yaml`：

```yaml
services:
  freshrss:
    image: freshrss/freshrss:latest
    container_name: freshrss
    restart: unless-stopped
    ports:
      - "8080:80"
    volumes:
      - freshrss_data:/var/www/freshrss/data
      - freshrss_ext:/var/www/freshrss/extensions
    environment:
      - CRON=min
      - TZ=Asia/Shanghai

volumes:
  freshrss_data:
  freshrss_ext:
```

启动服务：

```bash
docker compose up -d
```

### 第二步：配置反向代理

如果你有自己的域名（比如 `rss.yourdomain.com`），建议搭配 Nginx 或 Caddy 配置 HTTPS：

**Nginx 示例：**

```nginx
server {
    listen 443 ssl http2;
    server_name rss.yourdomain.com;

    ssl_certificate     /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

**Caddy 示例（更简单，自动 HTTPS）：**

```caddy
rss.yourdomain.com {
    reverse_proxy localhost:8080
}
```

### 第三步：完成初始化

访问 `http://你的IP:8080` 或 `https://rss.yourdomain.com`，按向导完成初始化设置：

1. 设置管理员账号和密码
2. 配置数据库（默认 SQLite，小 VPS 完全够用）
3. 设置时区和语言（中文）

## 开始收集你的信息源

### 添加订阅源

FreshRSS 支持标准的 RSS/Atom 格式。常见的订阅源格式：

| 平台 | 订阅方式 |
|------|---------|
| 博客 | 直接粘贴 RSS 链接 |
| YouTube | `https://www.youtube.com/feeds/videos.xml?channel_id=CHANNEL_ID` |
| Twitter/X | 使用 [HiveStream](https://github.com/Rouk1en/hivestream) 或 Nitter 实例 |
| 知乎 | 使用 [RSSHub](https://docs.rsshub.app) 生成 |
| 微信公众号 | 使用 [WeRSS](https://werss.app) 或 [RSSHub](https://docs.rsshub.app) |
| B站UP主 | `https://rsshub.app/bilibili/user/video/{uid}` |

### 使用 RSSHub 扩展源

**RSSHub** 是开源的 RSS 生成器，可以为几乎所有中文平台生成 RSS 源：

```bash
# 使用 Docker 部署 RSSHub
docker run -d --name rsshub -p 1200:1200 diygod/rsshub
```

然后通过 RSSHub 获取源：

```
# 示例：某个 B站 UP 主的 RSS 源
https://你的rsshub地址/bilibili/user/video/123456789

# 示例：知乎热榜
https://你的rsshub地址/zhihu/hot-list
```

RSSHub 文档非常完善：[docs.rsshub.app](https://docs.rsshub.app)

### 搜索和发现 RSS 源

- [Feed43](https://feed43.com) — 将任意网页转为 RSS
- [RSSHub 路由目录](https://docs.rsshub.app) — 300+ 平台支持
- [FindRSS](https://findrss.net) — 搜索网站的 RSS 源

## 高级功能配置

### AI 智能摘要

FreshRSS 支持通过扩展实现 AI 摘要功能。安装 [AI Summary 扩展](https://github.com/Mantoux09/freshrss-ai-summary)：

```bash
cd /opt/freshrss/freshrss/extensions
git clone https://github.com/Mantoux09/freshrss-ai-summary.git AI-Summary
# 在 FreshRSS 管理后台启用扩展
```

搭配 Ollama 在本地运行，可实现完全私密的 AI 摘要。

### 自动归档策略

设置文章自动归档，避免数据库无限膨胀：

**管理后台 → 配置 → 自动归档**

| 设置项 | 推荐值 | 说明 |
|--------|--------|------|
| 保留数量 | 5000 | 每个源最多保留的文章数 |
| 最大保留天数 | 30 | 超过 30 天的文章自动归档 |
| 最大数据库大小 | 500MB | 触发归档的阈值 |

### 邮件/推送通知

在 **管理后台 → 配置 → 通知** 中配置：

- **邮件通知**：新订阅源有新内容时发送邮件
- **Webhook**：对接 Telegram Bot、Bark、Pushbullet 等推送服务

### 浏览器插件：Miniflux Reader Plus / FreshRSS-Helper

安装浏览器扩展后，访问任意网页时自动检测 RSS 源：

- Chrome: [FreshRSS Helper](https://chrome.google.com/webstore/detail/freshrss-helper)
- Firefox: 类似扩展
- 功能：一键订阅、高亮 RSS 图标、批量添加源

## 数据备份与安全

### 数据备份

FreshRSS 的数据全部存储在 Docker 卷中，备份非常简单：

```bash
# 备份完整数据
docker run --rm \
  -v freshrss_data:/data:ro \
  -v /backup:/backup \
  alpine tar czf /backup/freshrss-data-$(date +%Y%m%d).tar.gz -C /data .

# 备份扩展配置
docker run --rm \
  -v freshrss_ext:/data:ro \
  -v /backup:/backup \
  alpine tar czf /backup/freshrss-extensions-$(date +%Y%m%d).tar.gz -C /data .
```

建议加入 cron 定时任务：

```bash
# 每天凌晨 3 点自动备份
echo "0 3 * * * /path/to/backup-script.sh" | crontab -
```

### 安全加固

1. **启用 HTTPS**：强制 SSL 加密传输
2. **修改默认路径**：不要使用默认的 `/` 作为访问路径
3. **启用双因素认证（2FA）**：管理后台 → 安全
4. **定期更新**：`docker compose pull && docker compose up -d`
5. **限制访问 IP**：通过 Nginx 或防火墙限制仅家/NAT IP 可访问

## 替代方案对比

如果你的需求比较特殊，也可以考虑这些替代方案：

| 方案 | 语言 | 资源占用 | 特点 |
|------|------|---------|------|
| **FreshRSS** | PHP | ⭐ 极低 | 功能全面，插件多，首选 |
| Miniflux | Go | ⭐ 极低 | 极简设计，单二进制文件 |
| **Tiny Tiny RSS** | PHP | ⭐⭐ 低 | 功能强大，但配置较复杂 |
| Feedly | SaaS | N/A | 免费方案限制多 |
| Inoreader | SaaS | N/A | 规则引擎强大，付费 |

对于大多数 VPS 用户，**FreshRSS 是最佳平衡点**：轻量、功能全面、生态成熟。

## 每日阅读工作流建议

好的阅读器不只是收集信息，更是**管理注意力**的工具：

1. **早晨 10 分钟**：快速浏览所有源，标记星标
2. **集中阅读时段**：每天安排 1 小时深度阅读，只看星标内容
3. **每周整理**：清理失效源，调整分类，归档已读文章
4. **每月回顾**：评估信息源质量，取消低质量订阅

记住：**你不需要阅读所有内容，你只需要阅读正确的内容。**

## 总结

自托管 RSS 阅读器，本质上是在信息时代夺回**注意力主权**。FreshRSS 凭借低资源占用、丰富的扩展生态和完全的数据私有化，成为 VPS 自托管场景下的首选方案。

花 10 分钟搭建，它能为你省下每天数小时的无效信息浏览时间。这就是自托管的价值——**把控制权拿回自己手里**。

---

*文章由 [selfvps.net](https://selfvps.net) 自动生成与分发*
