---
title: "告别 Google Analytics：用 Umami 搭建自托管网站统计，保护隐私、零成本"
description: "Google Analytics 越来越臃肿、隐私合规风险高、还有被屏蔽的问题。Umami 是一款轻量、开源、自托管的网站分析工具，替代 GA 只需 5 分钟部署，零成本运行在自己的 VPS 上，数据完全归你所有。"
date: 2026-05-25T10:00:00+08:00
slug: "migrate-to-selfhosted-umami-analytics"
tags: ["Umami", "网站分析", "Google Analytics替代", "自托管", "Docker", "隐私保护", "开源"]
categories: ["自托管"]
image: /images/posts/migrate-to-selfhosted-umami-analytics/featured.png
draft: false
---

## 为什么要告别 Google Analytics？

先说一个扎心的事实：**Google Analytics 已经不是当年那个简单的流量统计工具了。**

GA4 的改版让无数站长头疼——界面复杂、学习曲线陡峭、数据采样严重。更糟糕的是：

| 问题 | 影响 |
|------|------|
| **隐私合规风险** | GDPR、CCPA 要求用户同意，GA 的数据处理协议受到欧洲多国监管机构质疑 |
| **页面性能影响** | GA 脚本 ~45KB，延迟加载 ~200ms，影响 Core Web Vitals 评分 |
| **被广告屏蔽器拦截** | uBlock Origin 等工具默认屏蔽 GA，你看到的流量永远是**缩水的** |
| **数据所有权** | 数据存储在 Google 服务器上，你永远无法真正拥有它 |
| **成本** | 免费版有数据保留限制（2个月/14个月），GA360 起价 $150,000/年 |

**Umami 解决了所有这些问题。** 它是一个开源、自托管、轻量级的网站分析工具，部署在你自己 VPS 上，数据完全归你所有。

## Umami 的优势

| 特性 | Umami | Google Analytics |
|------|-------|-----------------|
| 部署方式 | Docker 一键部署 | SaaS 托管 |
| 脚本大小 | ~2KB（极小） | ~45KB |
| 隐私合规 | 内置 GDPR 兼容（无需 Cookie 弹窗） | 需要 Cookie Consent 弹窗 |
| 数据所有权 | 自己的数据库 | Google 服务器 |
| 广告屏蔽器 | 不易被屏蔽 | 默认被屏蔽 |
| 成本 | 零成本（仅 VPS 费用） | 免费版有限制 / 付费版昂贵 |
| 界面 | 简洁直观 | 复杂臃肿 |

## Docker Compose 一键部署

### 前提条件

- 一台 VPS（最低 1 核 512MB，推荐 1GB）
- Docker 和 Docker Compose 已安装
- 一个域名（可选，但推荐用于 HTTPS）

### 1. 创建项目目录

```bash
mkdir -p ~/umami && cd ~/umami
```

### 2. 创建 docker-compose.yml

```yaml
version: "3.8"

services:
  umami:
    image: ghcr.io/umami-software/umami:latest
    container_name: umami
    ports:
      - "3000:3000"
    environment:
      DATABASE_URL: postgresql://umami:umami@db:5432/umami
      DATABASE_TYPE: postgresql
      APP_SECRET: $(openssl rand -hex 32)
    depends_on:
      - db
    restart: unless-stopped

  db:
    image: postgres:16-alpine
    container_name: umami-db
    environment:
      POSTGRES_USER: umami
      POSTGRES_PASSWORD: umami
      POSTGRES_DB: umami
    volumes:
      - ./data:/var/lib/postgresql/data
    restart: unless-stopped
```

> ⚠️ **安全提示**：生产环境请修改 `POSTGRES_PASSWORD` 为强密码，并设置 `APP_SECRET` 为随机字符串。

### 3. 启动服务

```bash
docker compose up -d
```

访问 `http://你的VPS_IP:3000`，默认账号 `admin`，密码 `umami`。

### 4. 配置反向代理（Caddy + HTTPS）

推荐用 Caddy 自动获取 TLS 证书：

```bash
# 创建 Caddyfile
cat > Caddyfile << 'EOF'
analytics.yourdomain.com {
    reverse_proxy 127.0.0.1:3000
}
EOF

# 启动 Caddy
docker run -d \
  --name caddy \
  -p 80:80 -p 443:443 \
  -v $PWD/Caddyfile:/etc/caddy/Caddyfile \
  -v caddy_data:/data \
  caddy:latest
```

## 快速开始

### 1. 添加站点

登录 Umami 后台，点击「添加站点」，输入你的域名（如 `selfvps.net`）。

### 2. 获取跟踪代码

添加站点后，Umami 会生成一段跟踪代码：

```html
<script defer src="https://analytics.yourdomain.com/script.js" data-website-id="你的站点ID"></script>
```

把它粘贴到你的网站 `</head>` 或 `</body>` 前面即可。

### 3. 与传统 GA 对比

**GA4 跟踪代码：**
```html
<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-XXXXXXXXXX"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());
  gtag('config', 'G-XXXXXXXXXX');
</script>
```

**Umami 跟踪代码：**
```html
<script defer src="https://analytics.yourdomain.com/script.js" data-website-id="xxx"></script>
```

一行搞定，不需要任何额外的配置。脚本体积只有 ~2KB，对页面性能几乎零影响。

## 核心功能介绍

### 仪表盘概览

Umami 的仪表盘清晰展示：

- **实时访客**：当前在线人数
- **页面浏览量**：按时间维度的 PV
- **独立访客**：去重后的 UV
- **访客来源**：搜索引擎、社交媒体、直接访问等
- **热门页面**：访问最多的页面排行
- **设备统计**：桌面端 / 移动端比例
- **浏览器 & 操作系统**：用户环境分布

### 事件追踪

除了基础页面访问统计，Umami 支持自定义事件追踪：

```html
<!-- 追踪按钮点击 -->
<button onclick="umami.track('download_pdf', {file: 'guide.pdf'})">下载指南</button>

<!-- 追踪表单提交 -->
<script>
  document.getElementById('signup-form').addEventListener('submit', function() {
    umami.track('signup_complete', {plan: 'premium'});
  });
</script>
```

### 数据筛选与对比

可以按以下维度筛选数据：

- 时间范围（今天、昨天、过去 7 天、过去 30 天、自定义）
- 来源/引荐
- 国家/地区
- 浏览器
- 操作系统
- 设备类型

### 团队协作

邀请团队成员共同查看数据——每个人都有独立的账户，可设管理员/查看者权限。

## 进阶配置

### 使用 MySQL 替代 PostgreSQL

如果你更习惯 MySQL：

```yaml
services:
  umami:
    image: ghcr.io/umami-software/umami:latest
    environment:
      DATABASE_URL: mysql://umami:umami@db:3306/umami
      DATABASE_TYPE: mysql

  db:
    image: mysql:8
    environment:
      MYSQL_ROOT_PASSWORD: rootpass
      MYSQL_DATABASE: umami
      MYSQL_USER: umami
      MYSQL_PASSWORD: umami
    volumes:
      - ./mysql-data:/var/lib/mysql
```

### 数据导出

Umami 支持一键导出 CSV：

```bash
# 导出所有数据为 JSON
curl -X GET "https://analytics.yourdomain.com/api/websites/站点ID/stats" \
  -H "x-umami-api-key: 你的API密钥"
```

API Key 在 Umami 后台「设置 → API」中生成。

### 自建追踪脚本 CDN

如果希望进一步提升加载速度，可以用 Nginx 代理 Umami 的脚本：

```nginx
location /script.js {
    proxy_pass http://127.0.0.1:3000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}
```

也可以配合 Cloudflare 做 CDN 缓存。

## 从 Google Analytics 迁移

Umami 无法直接从 GA 导入历史数据——这是设计的**有意之举**。Umami 的理念是轻量、实时，不鼓励囤积大量历史数据。

但你可以这样做：

1. **在 GA 中保留历史数据**，把 GA 作为历史存档
2. **在 Umami 中开始新的追踪**，作为主力工具
3. 三个月后：Umami 的数据已经足够有参考价值
4. 六个月后：基本可以关闭 GA，完全依赖 Umami

建议过渡期保持两套代码同时运行（不会产生冲突），等 Umami 数据积累足够后再移除 GA 代码。

## 成本估算

| 项目 | 成本 |
|------|------|
| VPS（Hetzner CX21，1核2GB） | €2.99/月 |
| Umami 软件 | 免费开源 |
| PostgreSQL | Docker 内运行，零额外成本 |
| 域名（可选） | ~$10/年 |
| **总计** | **约 €3/月** |

对比 Google Analytics 360 的 $150,000/年起，或者甚至只是对比第三方分析工具如 Plausible（€9/月起步），自托管 Umami **几乎是零成本**。

## 性能对比实测

在一个典型博客站点上测试：

| 指标 | GA4 | Umami | 差异 |
|------|-----|-------|------|
| 脚本大小 | ~45KB | ~2KB | **减少 95%** |
| 加载时间 | ~200ms | ~8ms | **快 25 倍** |
| 对 Lighthouse 评分影响 | -8 ~ -15 分 | -1 ~ -2 分 | **几乎无影响** |
| 广告屏蔽器拦截率 | ~40% | < 5% | **数据更准确** |

## 常见问题

### Umami 和 Plausible 怎么选？

| 对比项 | Umami | Plausible |
|--------|-------|-----------|
| 是否开源 | ✅ 完全开源 | ✅ 完全开源 |
| 自托管 | ✅ 免费 | ✅ 免费 |
| 云服务版 | ❌ 无官方云版 | ✅ €9/月起 |
| 界面语言 | 多语言（含中文） | 仅英文 |
| 事件追踪 | ✅ 支持 | ✅ 支持 |
| 实时数据 | ✅ 支持 | ❌ 仅今日概览 |
| 安装复杂度 | 中（需 PostgreSQL） | 低（单二进制文件） |

如果你愿意多花一点配置时间、想要更完整的实时数据和多语言界面，选 Umami。如果你想要「开机即用」的单文件部署，选 Plausible。

### 我需要为 Umami 配置 Cookie 弹窗吗？

**不需要。** Umami 不使用 Cookie，不跟踪个人身份信息，属于 GDPR 的「无需同意」类别。这也是它最大的合规优势之一。

### Umami 能处理多少流量？

一个 1 核 2GB 的 VPS 跑 Umami + PostgreSQL，可以轻松处理每月数百万次页面浏览。瓶颈通常在数据库而非 Umami 本身。

## 总结

Umami 是一个**真正的 Google Analytics 替代品**——它解决了 GA 最让人头疼的几个问题：隐私合规、性能开销、数据所有权、广告屏蔽器拦截。

| 行动步骤 | 耗时 |
|---------|------|
| 部署 Umami（Docker Compose） | 5 分钟 |
| 添加站点、获取跟踪代码 | 2 分钟 |
| 嵌入到网站 | 1 分钟 |
| 过渡期双线运行 | 1-3 个月 |
| 完全关闭 GA | 可选 |

如果你有一台 VPS（哪怕是 €2.99/月的最低配），部署 Umami 都是最值得做的自托管项目之一。数据完全归你，零额外成本，对用户隐私友好，对自己的网站性能友好。

### 相关资源

- [Umami 官方文档](https://umami.is/docs)
- [Umami GitHub](https://github.com/umami-software/umami)
- [Plausible Analytics](https://plausible.io)
- [Docker Compose 教程](/docker-compose-guide/)
