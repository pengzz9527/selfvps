---
title: "SearXNG 自建隐私搜索引擎 —— 聚合全球搜索，拒绝数据追踪"
description: "在 VPS 上部署 SearXNG，聚合 Google/Bing/DuckDuckGo 等 70+ 搜索引擎结果，不追踪用户、不存储数据，完全掌控你的搜索隐私。"
date: 2026-08-16T10:00:00+08:00
slug: "searxng-selfhosted-privacy-search-engine"
tags: ["SearXNG", "搜索引擎", "隐私", "自托管", "Docker", "VPS运维", "搜索聚合"]
categories: ["搜索与隐私"]
image: /images/posts/searxng-selfhosted-privacy-search-engine/featured.png
draft: false
---

## 引言

你的每一次搜索，都在被追踪。

Google 记录你搜索的一切：关键词、点击记录、停留时长、地理位置。DuckDuckGo 号称隐私保护，但结果源仍受制于第三方。当你需要真正**不泄露任何信息**的搜索体验时，唯一的选择是——**自己搭一个搜索引擎**。

SearXNG 正是为此而生。它是一个开源的、自托管的元搜索引擎，聚合了 70+ 主流搜索引擎的结果，不记录用户数据、不存储搜索历史，支持 Docker 一键部署，15 分钟就能拥有属于你的隐私搜索平台。

## SearXNG 是什么？

SearXNG 是 SearX 的社区延续版（原项目已停止维护），核心特性：

- 🔍 **70+ 搜索引擎聚合**：Google、Bing、DuckDuckGo、Baidu、维基百科、GitHub 等
- 🔒 **零数据追踪**：不记录 IP、不存储搜索历史、不创建用户画像
- 🌐 **多语言支持**：中文界面友好，支持多语言搜索
- 📱 **响应式设计**：手机、平板、桌面端均可正常使用
- 🛡️ **反追踪保护**：自动混淆请求头，避免被搜索引擎封禁
- 🔧 **高度可定制**：插件系统、结果排序、搜索引擎偏好配置
- 🐳 **Docker 一键部署**：5 分钟完成搭建

## 一、Docker 快速部署

SearXNG 官方推荐使用 Docker 部署，最简单的方式如下：

### 1. 单容器部署（快速体验）

```bash
docker run -d \
  --name searxng \
  -p 8080:8080 \
  -v /data/searxng:/etc/searxng \
  --restart unless-stopped \
  searxng/searxng:latest
```

部署完成后，浏览器访问 `http://你的VPS_IP:8080` 即可使用。

### 2. Docker Compose 部署（推荐生产环境）

```yaml
# docker-compose.yml
version: '3.8'

services:
  searxng:
    image: searxng/searxng:latest
    container_name: searxng
    ports:
      - "8080:8080"
    volumes:
      - ./searxng-settings:/etc/searxng
    environment:
      - SEARXNG_BASE_URL=http://localhost:8080/
      - TZ=Asia/Shanghai
    restart: unless-stopped
    mem_limit: 512m
    cpus: 1.0
```

```bash
mkdir -p ./searxng
docker compose up -d
```

## 二、反向代理 + HTTPS 配置

将 SearXNG 暴露到公网需要 HTTPS 保护，推荐使用 Caddy（自动 TLS）或 Nginx。

### Caddy 配置（最简单）

```caddyfile
search.yourdomain.com {
    reverse_proxy localhost:8080
}
```

一行配置搞定，Caddy 自动申请 Let's Encrypt 证书。

### Nginx 配置

```nginx
server {
    listen 443 ssl http2;
    server_name search.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

    # 安全头
    add_header X-Content-Type-Options nosniff;
    add_header X-Frame-Options SAMEORIGIN;
    add_header Referrer-Policy no-referrer;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
        proxy_request_buffering off;
    }
}
```

## 三、SearXNG 核心配置

SearXNG 的配置文件位于 `/etc/searxng/settings.yml`，通过 Docker volume 挂载即可修改。

### 1. 基础配置

```yaml
# settings.yml
general:
  instance_name: "My Private Search"
  contact_url: false
  debug: false

search:
  safe_search: 0        # 0=关闭, 1=中等, 2=严格
  autocomplete: "google"
  default_lang: "auto"
  formats:
    - html
    - json

server:
  port: 8080
  bind_address: "0.0.0.0"
  secret_key: "your-random-secret-key-here"  # 请替换为随机字符串
  limiter: false
  image_proxy: true   # 代理图片，保护隐私
```

### 2. 搜索引擎偏好设置

```yaml
engines:
  - name: google
    disabled: false
    weight: 3

  - name: bing
    disabled: false
    weight: 2

  - name: baidu
    disabled: false
    weight: 1

  - name: duckduckgo
    disabled: false
    weight: 2

  - name: wikipedia
    disabled: false
    weight: 1

  # 可选：禁用不需要的引擎
  - name: amazon
    disabled: true
```

### 3. 启用 JSON API（用于集成）

SearXNG 提供 RESTful JSON API，可被其他应用调用：

```bash
# 搜索测试
curl -s "https://search.yourdomain.com/search?q=VPS+推荐&format=json" | jq .

# 结果示例结构
# {
#   "results": [
#     {
#       "title": "...",
#       "url": "...",
#       "content": "...",
#       "engine": "google"
#     }
#   ]
# }
```

### 4. 配置插件（Plugin）

SearXNG 支持丰富的插件系统，常用插件：

```yaml
plugins:
  - plugin_name: 'Hostnames plugin'
  - plugin_name: 'Tracker URL remover'    # 自动移除搜索链接中的追踪参数
  - plugin_name: 'Tor check plugin'
  - plugin_name: 'Self Open Results'
  - plugin_name: 'Ahmia blacklist'        # 黑名单过滤
```

`Tracker URL remover` 插件非常实用，它会自动清除结果链接中的 UTM 参数和追踪 ID，避免点击后被目标网站追踪。

## 四、高级功能

### 1. 分类搜索

SearXNG 支持多种搜索分类，界面提供快捷入口：

| 分类 | 说明 |
|------|------|
| **General** | 综合搜索（Google、Bing 等） |
| **Images** | 图片搜索 |
| **Videos** | 视频搜索 |
| **News** | 新闻搜索 |
| **Music** | 音乐搜索 |
| **IT** | IT/技术搜索（GitHub、Stack Overflow） |
| **Science** | 学术论文搜索 |
| **Files** | 文件搜索 |

### 2. 结果排序与过滤

每次搜索后，你可以：
- 按**相关性**或**时间**排序
- 切换**语言**和**地区**（如 zh-CN、en-US）
- 启用**Safe Search**过滤不当内容
- 选择**分页大小**（默认 30 条/页）

### 3. SearXNG 作为系统默认搜索引擎

**Chrome/Edge**：安装扩展「Search by SearXNG」后，在浏览器设置中将默认搜索引擎设为 SearXNG 实例 URL。

**Firefox**：设置 → 搜索 → 搜索引擎 → 添加 SearXNG 自定义引擎：
```
URL: https://search.yourdomain.com/search?q=%s
```

### 4. RSS 订阅搜索结果

SearXNG 支持 RSS 输出，可将搜索结果订阅到 Feed 阅读器：

```
https://search.yourdomain.com/search?q=关键词&format=rss
```

## 五、SearXNG vs 其他搜索方案对比

| 工具 | 免费 | 自托管 | 隐私保护 | 中文支持 | 部署难度 |
|------|------|--------|----------|----------|----------|
| **SearXNG** | ✅ | ✅ | ✅ 完全匿名 | ✅ | ⭐ 极简 |
| Google | ❌ | ❌ | ❌ 全链路追踪 | ✅ | N/A |
| DuckDuckGo | ✅ | ❌ | ✅ 较好 | ✅ | N/A |
| Bing | ❌ | ❌ | ❌ 微软追踪 | ✅ | N/A |
| Presearch | ✅ | ❌ | ⚠️ 需代币 | ✅ | N/A |
| Mojeek | ✅ | ❌ | ✅ | ⚠️ 弱 | N/A |

**结论**：如果你追求**绝对的搜索隐私**且不想依赖任何第三方，SearXNG 是唯一正确选择。自建实例意味着你的搜索行为只属于你自己。

## 六、安全加固与最佳实践

### 1. 限制访问

如果你只需要在家庭或团队内部使用，建议加上认证：

```caddyfile
search.yourdomain.com {
    reverse_proxy localhost:8080
}

# 加上 Basic Auth
search.yourdomain.com {
    reverse_proxy localhost:8080
}
```

或在 Nginx 中添加：
```nginx
auth_basic "Private Search";
auth_basic_user_file /etc/nginx/.htpasswd;
```

### 2. 性能优化

- 设置 `results_limit: 50` 控制单次最大结果数
- 启用 `cache_limit: 1 day` 缓存搜索结果减少重复请求
- 根据实际需求增减搜索引擎数量（越多引擎 = 越慢）

### 3. 定时更新容器

```bash
# 添加到 crontab，每周更新一次
0 3 * * 0 docker pull searxng/searxng:latest && docker restart searxng
```

### 4. 备份配置

```bash
# 备份 SearXNG 配置
tar czf searxng-config-backup-$(date +%Y%m%d).tar.gz ./searxng/
```

## 七、替代方案参考

如果你不喜欢 SearXNG 的界面，以下同类工具也值得了解：

| 工具 | 特点 | 语言 |
|------|------|------|
| **SearXNG** | 功能最全，插件丰富，社区活跃 | Python |
| **Whoogle** | 极简 Google 镜像，Go 编写 | Go |
| **Lug** | 专注于学术搜索 | Python |
| **Yandex Search** | 俄系搜索引擎，隐私政策较好 | — |

其中 Whoogle 更为轻量（单二进制文件），适合资源极其有限的 VPS。

## 总结

SearXNG 是 VPS 上最值得部署的隐私工具之一：

- **部署极简**：Docker 一条命令，15 分钟完成
- **搜索强大**：聚合 70+ 引擎，结果质量不输 Google
- **隐私彻底**：零追踪、零记录、零画像
- **免费开源**：MIT 协议，完全自主可控

在这个数据即资产的时代，拥有一个完全属于自己的搜索引擎，是对数字隐私最基本的尊重。

> **相关阅读**：[Cloudflare Tunnel 零配置内网穿透指南](/zh/post/cloudflare-tunnel-zero-config-guide/) | [VPS 安全加固：2026 年生产环境配置手册](/zh/post/vps-security-hardening-2026/)
