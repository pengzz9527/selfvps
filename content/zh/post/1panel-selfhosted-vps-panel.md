---
title: "1Panel 自建面板：开箱即用的 VPS 应用管理器，告别命令行焦虑"
description: "1Panel 是新一代开源 Linux 面板，一条命令部署 Web 应用、SSL 证书、数据库、Docker 容器，可视化全栈管理，替代宝塔免费版限制，零成本掌控你的 VPS。"
date: 2026-09-19T10:00:00+08:00
lastmod: 2026-09-19T10:00:00+08:00
slug: "1panel-selfhosted-vps-panel"
image: /images/posts/1panel-selfhosted-vps-panel/featured.png
tags: ["1Panel", "VPS运维", "面板", "Docker", "自托管", "可视化", "零成本", "Web管理"]
categories: ["运维自动化", "自托管"]
aliases: [/zh/post/1panel-selfhosted-vps-panel/]
---

## 为什么需要 1Panel？

你可能有过这样的经历：

> 刚买了一台 VPS，想搭个网站，打开文档看了半小时——Nginx 配置、SSL 证书、Docker Compose、反向代理……命令行敲了一堆，结果网站还是 404。

手动配置每一台服务确实繁琐，而市面上大多数面板（如宝塔）免费版有功能限制，高级功能还要收费。**1Panel** 的出现正是为了解决这个问题——**开源免费、基于 Docker 容器管理、界面现代化、功能完整无阉割**。

---

## 1Panel 核心功能一览

| 功能 | 说明 |
|------|------|
| 应用管理 | 一键部署 WordPress、Nginx、MySQL、Redis、Docker 等 50+ 热门应用 |
| Web 服务 | 可视化配置 Nginx，支持反向代理、负载均衡、HTTPS 自动续签 |
| 数据库 | 图形化管理 MySQL、PostgreSQL、Redis、MongoDB，支持备份恢复 |
| Docker 管理 | 镜像/容器/网络/卷的可视化操作，无需记命令 |
| 文件管理 | 在线文件编辑器、压缩包管理、权限设置 |
| 监控告警 | CPU/内存/磁盘/网络实时图表，告警推送至 Telegram/Discord/邮件 |
| 定时任务 | 备份、清理、脚本执行，支持 Cron 表达式 |
| 安全加固 | SSH 端口修改、Fail2Ban 集成、防火墙规则管理 |

---

## 与宝塔面板对比

| 特性 | 1Panel | 宝塔（免费版）|
|------|--------|-------------|
| 价格 | **完全免费开源** | 基础功能免费，高级功能收费 |
| 架构 | 基于 Docker 容器化部署 | 传统进程管理，依赖系统环境 |
| 安全性 | 容器隔离，污染风险低 | 共享环境，一个应用崩溃影响全局 |
| 可视化 | 现代化 UI，响应式设计 | 界面较传统 |
| 扩展性 | 原生支持 Docker Compose 编排 | 有限 |
| 社区活跃度 | 高，持续迭代 | 稳定但更新节奏较慢 |

---

## 第一步：一键安装 1Panel

### 系统要求

- 操作系统：Ubuntu 20.04+ / Debian 11+ / CentOS 8+ / Rocky Linux 9+
- 内存：≥ 1GB（推荐 2GB+）
- 磁盘：≥ 10GB 可用空间
- 权限：root 或 sudo 权限

### 安装命令

```bash
# 使用官方一键安装脚本（推荐）
curl -sSL https://resource.fit2cloud.com/1panel/package/quick_start.sh -o quick_start.sh
sudo bash quick_start.sh install
```

安装过程中会提示你设置管理员用户名和密码，请妥善记录：

```
=========================================
        1Panel 安装完成
=========================================
面板地址: http://你的VPS_IP:38080/xK9mP2vL
用户名: admin
密码: [随机生成的强密码]
=========================================
```

> **注意**：首次登录请务必修改默认密码，并将 38080 端口在防火墙中仅对信任 IP 开放。

---

## 第二步：初始配置与安全加固

### 1. 修改默认端口

登录后立即进入「面板设置」→「安全设置」，将访问端口从 38080 改为一个不常见的端口（如 28080），并设置 SSL 证书。

### 2. 绑定域名 + HTTPS

```bash
# 在 1Panel 中添加站点
# 输入你的域名，例如 panel.yourdomain.com
# 1Panel 会自动申请 Let's Encrypt 证书
```

### 3. 开启两步验证（2FA）

在「面板设置」→「安全设置」中启用 TOTP 两步验证，扫描 QR 码绑定 Google Authenticator 或 Authy。

### 4. 配置 IP 白名单

在安全设置中限制只允许特定 IP 段访问面板，防止暴力破解。

---

## 第三步：部署你的第一个 Web 应用

以部署 WordPress 为例：

### 方式一：一键应用商店

1. 进入「应用商店」，搜索 "WordPress"
2. 点击安装，填写数据库密码
3. 等待安装完成，点击「访问」即可进入 WordPress 设置向导

### 方式二：使用 Docker Compose 自定义部署

对于需要高度定制化的场景，可以自定义 `docker-compose.yml`：

```yaml
version: '3.8'
services:
  wordpress:
    image: wordpress:latest
    ports:
      - "8080:80"
    environment:
      WORDPRESS_DB_HOST: db
      WORDPRESS_DB_USER: wp_user
      WORDPRESS_DB_PASSWORD: ${DB_PASSWORD}
      WORDPRESS_DB_NAME: wordpress
    volumes:
      - wp_data:/var/www/html
    depends_on:
      - db
  db:
    image: mysql:8.0
    environment:
      MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT}
      MYSQL_DATABASE: wordpress
      MYSQL_USER: wp_user
      MYSQL_PASSWORD: ${DB_PASSWORD}
    volumes:
      - db_data:/var/lib/mysql
volumes:
  wp_data:
  db_data:
```

在 1Panel 的「容器」→「Compose」中导入即可一键启动。

---

## 第四步：配置反向代理与 HTTPS

假设你已经通过 1Panel 部署了一个内部应用（如 Portainer，运行在 9000 端口），现在需要让它通过域名 `portainer.yourdomain.com` 访问并启用 HTTPS。

### 在 1Panel 中添加反代：

1. 进入「网站」→「反向代理」
2. 代理名称：`portainer`
3. 域名：`portainer.yourdomain.com`
4. 目标地址：`127.0.0.1:9000`
5. 开启 HTTPS，选择自动申请证书

### 自动生成 Nginx 配置：

```nginx
server {
    listen 443 ssl http2;
    server_name portainer.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/portainer.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/portainer.yourdomain.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;

    location / {
        proxy_pass http://127.0.0.1:9000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## 第五步：数据库管理与备份策略

### 图形化数据库管理

1Panel 内置 phpMyAdmin（MySQL）和 Adminer（PostgreSQL），无需额外安装即可在浏览器中管理数据库。

### 自动备份配置

```
路径：数据库 → 选择数据库 → 备份策略
```

推荐备份策略：
- **频率**：每日凌晨 3 点自动备份
- **保留数量**：最近 7 份
- **备份目的地**：本地 + S3/B2 远程存储（通过 1Panel 的文件备份功能）

```bash
# 也可以手动执行备份
1panel toolbox backup --db all --target s3://your-bucket/backups/
```

---

## 第六步：监控告警设置

### 开启系统监控

1Panel 默认收集 CPU、内存、磁盘、网络数据，在「监控」页面可实时查看。

### 配置告警规则

1. 进入「监控」→「告警规则」
2. 添加规则示例：
   - CPU 使用率 > 90% 持续 5 分钟 → 发送 Telegram 告警
   - 磁盘使用率 > 85% → 发送邮件告警
   - 内存使用率 > 95% → 发送Discord Webhook 告警

### Telegram 告警配置

在「告警设置」中填写：
- Webhook URL：`https://api.telegram.org/bot<BOT_TOKEN>/sendMessage`
- Chat ID：你的 Telegram 群组或频道 ID

---

## 成本对比：1Panel vs 商业面板

| 方案 | 月费 | 功能限制 | 适合场景 |
|------|------|---------|---------|
| 1Panel（自建） | **$0** | 无 | 个人开发者、小团队 |
| 宝塔专业版 | ¥199/年 | 部分高级功能 | 中小企业 |
| cPanel | $19/月起 | 无 | 虚拟主机服务商 |
| Plesk | $9/月起 | 部分功能 | WordPress 托管 |

对于拥有 1~5 台 VPS 的个人开发者或小型团队，**1Panel 是唯一零成本的全功能选择**。

---

## 常见问题

### Q：1Panel 和宝塔面板哪个更适合新手？

A：两者都很友好，但 1Panel 基于 Docker 架构，应用隔离性更好，崩溃不会影响其他服务。宝塔界面更贴近国内用户习惯，插件生态更丰富。如果你是 Docker 用户，优先选 1Panel；如果你是传统 LAMP/LNMP 用户，宝塔上手更快。

### Q：1Panel 支持 Windows 吗？

A：目前 1Panel 仅支持 Linux，不支持 Windows Server。Windows 用户可以考虑宝塔 Windows 版或 XAMPP。

### Q：如何从宝塔迁移到 1Panel？

A：1Panel 提供数据迁移工具，支持从宝塔导入网站、数据库、FTP 账户等信息。具体操作：「工具箱」→「数据迁移」→「宝塔迁移」。

### Q：1Panel 安全吗？

A：1Panel 代码开源可审计，采用 Docker 容器隔离，默认不开放高危端口。但仍建议：①修改默认端口 ②启用 HTTPS ③配置 IP 白名单 ④定期更新面板版本。

---

## 总结

1Panel 让 VPS 管理从"命令行焦虑"变成了"可视化操作"——一键部署应用、图形化配置 Nginx、容器化管理、实时监控告警，全部在一个现代化界面中完成。**零成本、开源、容器化**，是每个 VPS 用户值得拥有的管理面板。

如果你的 VPS 还停在命令行时代，是时候试试 1Panel 了。
