---
title: "Cloudflare R2 完全指南：零流量费对象存储，告别 AWS S3 天价账单"
date: 2026-07-20T10:00:00+08:00
lastmod: 2026-07-20T10:00:00+08:00
slug: "cloudflare-r2-zero-egress"
image: /images/posts/cloudflare-r2-zero-egress/featured.png
tags: ["Cloudflare R2", "对象存储", "零流量费", "S3兼容", "自托管", "云省钱", "CDN"]
categories: ["云省钱", "基础设施"]
aliases: [/zh/post/cloudflare-r2-zero-egress/]
description: "Cloudflare R2 提供与 AWS S3 完全兼容的对象存储服务，且零出口流量费。本文教你从零搭建 R2 + Hugo + Cloudflare CDN 的静态网站托管方案，每月节省数十美元。"
draft: false
---

## 为什么需要 Cloudflare R2？

对于自托管爱好者和小团队来说，云服务账单中最让人头疼的往往是**出口流量费（Egress Fee）**。以 AWS S3 为例：

| 服务商 | 存储价格/GB/月 | 出口流量费/GB | 请求费/万次 |
|--------|---------------|--------------|------------|
| AWS S3 Standard | $0.023 | **$0.09** | $5 |
| Backblaze B2 | $0.006 | $0.01（有免费额度） | $0 |
| Cloudflare R2 | $0.015 | **$0** | $0 |
| MinIO 自建 | 电费+硬盘 | 带宽费 | $0 |

R2 的核心优势非常明确：**零出口流量费**。这意味着你把静态资源、备份文件、媒体内容放在 R2 上，通过 Cloudflare CDN 分发，无论多少人访问，都不会产生流量费用。对于 VPS 带宽有限（比如 1TB/月）的用户来说，这是巨大的成本优化。

## R2 核心特性

### 1. S3 完全兼容

R2 使用与 AWS S3 相同的 API 接口，这意味着几乎所有支持 S3 的工具都可以直接对接：

```bash
# 使用 rclone 同步本地文件到 R2
rclone copy ./website s3:r2-bucket --s3-provider=Cloudflare \
  --s3-env-auth --s3-chunk-size=50M

# 使用 awscli（配置 endpoint）
aws s3 cp file.zip s3://my-bucket/ \
  --endpoint-url https://ACCOUNT_ID.r2.cloudflarestorage.com
```

### 2. 无出口流量费

所有从 R2 通过 Cloudflare 网络分发的数据**不收取任何费用**。即使你不使用 Cloudflare CDN，直接访问 R2 端点也没有出口费（但建议走 CDN 以获得更好的性能）。

### 3. 自动复制与高可用

R2 默认在三个地理区域自动复制数据，提供 99.99% 的数据可用性。你不需要自己配置多副本策略。

### 4. 无限存储，按量付费

没有预置容量限制，没有最低消费。你存多少就付多少，非常适合从小规模起步。

## 从零开始：创建 R2 Bucket

### 第一步：注册并进入 Dashboard

1. 登录 [Cloudflare Dashboard](https://dash.cloudflare.com)
2. 左侧菜单选择 **R2 Object Storage**
3. 点击 **Create Bucket**

### 第二步：创建 Bucket

```
Bucket Name: my-static-site
Region: auto（默认即可）
Storage Class: Standard
```

创建完成后，记录你的 **Account ID**（在 R2 页面右上角可以看到），后续配置需要用到。

### 第三步：创建 API Token

进入 **R2 → API Tokens**，创建一个具有写入权限的 Token：

```json
{
  "name": "r2-write-token",
  "permissions": {
    "R2": "READ"
  }
}
```

> ⚠️ 安全提示：Token 一旦生成后只能看到一次 Secret Key，请妥善保存。

## 实战一：用 R2 托管 Hugo 静态网站

这是最实用的场景之一。将 Hugo 构建产物上传到 R2，配合 Cloudflare CDN 全球分发。

### 1. 安装 s5cmd 或 rclone

推荐使用 **s5cmd**，速度快且命令简洁：

```bash
# Ubuntu/Debian
wget https://github.com/peak/s5cmd/releases/download/v2.2.3/s5cmd_2.2.3_amd64.tar.gz
tar -xzf s5cmd_2.2.3_amd64.tar.gz
sudo mv s5cmd /usr/local/bin/

# 或使用 rclone
sudo apt install rclone
```

### 2. 配置凭证

```bash
# 使用 s5cmd
export AWS_ACCESS_KEY_ID="YOUR_R2_ACCESS_KEY"
export AWS_SECRET_ACCESS_KEY="YOUR_R2_SECRET_KEY"
export AWS_DEFAULT_REGION="auto"

# 测试连接
s5cmd ls s3://my-static-site
```

### 3. 构建并部署

```bash
# 构建 Hugo 站点
hugo --minify

# 同步到 R2（首次）
s5cmd sync public/ s3://my-static-site/

# 设置静态网站索引
s5cmd put index.html s3://my-static-site/index.html

# 后续更新只需重新同步
hugo --minify && s5cmd sync public/ s3://my-static-site/
```

### 4. 配置自定义域名

在 Cloudflare Dashboard 中为你的域名添加 CNAME 记录：

```
Type: CNAME
Name: static
Value: <bucket-name>.r2.dev
TTL: Auto
Proxy status: Proxied（开启橙色云朵）
```

现在你的网站可以通过 `static.yourdomain.com` 访问，所有流量都经过 Cloudflare CDN。

## 实战二：R2 作为 VPS 备份目标

VPS 备份是 R2 的另一大应用场景。由于 R2 没有出口流量费，从 VPS 上传备份到 R2 的成本极低。

### 使用 restic 备份到 R2

```bash
# 安装 restic
sudo apt install restic

# 初始化仓库
restic init \
  --repo s3:s3.amazonaws.com/my-backup-bucket \
  --endpoint https://ACCOUNT_ID.r2.cloudflarestorage.com \
  --access-key YOUR_ACCESS_KEY \
  --secret-key YOUR_SECRET_KEY

# 备份关键目录
restic backup \
  --repo s3:s3.amazonaws.com/my-backup-bucket \
  --endpoint https://ACCOUNT_ID.r2.cloudflarestorage.com \
  --exclude='/proc/*' --exclude='/sys/*' \
  /etc /home /var/www

# 自动压缩和加密
restic backup --compress zstd /data
```

### 自动化定时备份

```bash
#!/bin/bash
# /usr/local/bin/r2-backup.sh

BACKUP_DIR="/tmp/restic-backup-$$"
mkdir -p "$BACKUP_DIR"

# 备份
restic backup \
  --repo s3:s3.amazonaws.com/my-backup-bucket \
  --endpoint https://ACCOUNT_ID.r2.cloudflarestorage.com \
  --password-file ~/.restic-password \
  /etc /home /var/www

# 保留最近 7 天快照
restic prune --repo s3:s3.amazonaws.com/my-backup-bucket \
  --endpoint https://ACCOUNT_ID.r2.cloudflarestorage.com \
  --password-file ~/.restic-password

# 清理临时文件
rm -rf "$BACKUP_DIR"
```

添加到 crontab：

```cron
0 2 * * * /usr/local/bin/r2-backup.sh >> /var/log/r2-backup.log 2>&1
```

## 实战三：R2 + Workers 实现动态图片处理

如果你需要动态图片处理（缩略图、水印、格式转换），可以结合 Cloudflare Workers 和 R2 实现 Serverless 图片服务。

```javascript
// Cloudflare Worker 示例：动态生成缩略图
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname.slice(1);
    
    // 获取原图
    const object = await env.MY_BUCKET.get(path);
    if (!object) return new Response('Not Found', { status: 404 });
    
    // 处理图片（使用 R2 的 Image Resizing）
    const contentType = object.httpMetadata?.contentType || 'image/png';
    
    return new Response(object.body, {
      headers: {
        'Content-Type': contentType,
        'Cache-Control': 'public, max-age=86400',
      },
    });
  }
};
```

## 成本对比：R2 vs S3 vs 自建 MinIO

假设你的网站每月有 100GB 静态资源被访问：

| 项目 | AWS S3 | Cloudflare R2 | MinIO 自建 |
|------|--------|---------------|------------|
| 存储 100GB | $2.30 | $1.50 | $0（硬盘成本） |
| 100GB 出口流量 | **$9.00** | **$0** | 带宽费 |
| 1000万次请求 | $5.00 | $0 | $0 |
| CDN 费用 | $0（CloudFront另计） | $0（已含） | VPS 带宽 |
| **月总计** | **~$16.30** | **~$1.50** | 电费+硬盘 |

对于中小规模用户，R2 的综合成本通常是 S3 的 **1/10** 甚至更低。

## 最佳实践与注意事项

### ✅ 推荐做法

1. **启用 Cloudflare CDN 代理**：开启橙色云朵，享受全球加速和 DDoS 防护
2. **设置合理的 Cache-Control**：静态资源设置较长的缓存时间
3. **使用版本控制**：开启 Bucket 版本控制，防止误删除
4. **配置 CORS**：如果需要前端 JS 直接访问，配置跨域策略
5. **监控用量**：在 Cloudflare Dashboard 设置用量告警

### ⚠️ 需要注意的限制

- **冷启动延迟**：R2 首次访问可能有轻微延迟（CDN 回源）
- **列表操作性能**：大量文件的列表操作不如 S3 高效
- **生命周期规则**：支持基础的生命周期管理，但不如 S3 灵活
- **跨区域复制**：目前不支持手动指定复制区域
- **Free Plan 限制**：免费计划每天最多 10万次读取、1000次写入

### 💡 进阶技巧

```bash
# 批量删除过期文件
s5cmd rm "s3://my-bucket/old-files/*.tmp"

# 设置公共读取权限（适用于静态资源）
s5cmd cp --acl public-read image.jpg s3://my-bucket/images/

# 使用 multipart 上传大文件
s5cmd cp large-backup.tar.gz s3://my-bucket/backups/ \
  --concurrency 10 --chunk-size 100M
```

## 总结

Cloudflare R2 是目前自托管社区中最具性价比的对象存储方案之一。**零出口流量费**的特性让它成为静态网站托管、备份存储、CDN 源站等场景的理想选择。

对于 VPS 用户来说，将静态资源迁移到 R2 可以：
- 📉 大幅降低月度云支出
- 🚀 利用 Cloudflare 全球 CDN 加速
- 🔒 获得企业级数据安全和高可用
- 🔄 无缝替换现有 S3 工作流

如果你的 VPS 带宽已经接近上限，或者你正在寻找更经济的静态资源托管方案，R2 绝对值得尝试。
