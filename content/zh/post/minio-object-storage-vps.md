---
title: "自建 MinIO 对象存储：低成本替代 AWS S3 的完整方案"
description: "从零开始在你的 VPS 上部署 MinIO 对象存储服务——兼容 S3 API，支持 Docker 一键部署、HTTPS 加密、自动备份和跨机房同步，月成本不到 $5"
date: 2026-06-28T10:00:00+08:00
lastmod: 2026-06-28T10:00:00+08:00
slug: "minio-object-storage-vps"
tags: ["MinIO", "S3", "对象存储", "Docker", "VPS部署", "自托管", "云省钱", "私有云"]
categories: ["部署教程"]
image: /images/posts/minio-object-storage-vps/featured.png
draft: false
---

## 为什么自建对象存储？

AWS S3 是全球最流行的对象存储服务，但它的费用随着数据量增长而飙升。对于个人开发者、小型团队或内容创作者来说：

| 场景 | AWS S3 月费估算 | MinIO 自建月费 |
|------|----------------|----------------|
| 100GB 存储 | ~$2.30 | **$0.50** (VPS分摊) |
| 1TB 存储 | ~$23.00 | **$0.50** |
| 5TB 存储 | ~$115.00 | **$0.50** |
| 每月 100万次读取 | ~$4.00 | **$0.50** |
| 数据传输（出站） | **按量计费，无底洞** | **包含在VPS带宽内** |

关键点：**S3 的数据出站流量费（Data Transfer Out）是最容易被忽视的成本黑洞**。而自建 MinIO，只要 VPS 有足够的带宽，数据传输就是"免费"的。

## MinIO 是什么？

[MinIO](https://min.io/) 是一个高性能、兼容 S3 API 的对象存储服务器，用 Go 语言编写。它的核心特点：

- **S3 完全兼容**：任何支持 S3 的工具都可以直接对接
- **极简部署**：Docker 一条命令启动
- **资源占用低**：1GB RAM 即可运行
- **企业级功能**：版本控制、生命周期策略、加密、跨区域复制
- **开源免费**：AGPL v3 许可

## 环境准备

### 硬件要求

| 配置 | 最低 | 推荐 |
|------|------|------|
| CPU | 1核 | 2核+ |
| 内存 | 1GB | 2GB+ |
| 存储 | 50GB SSD | 200GB+ NVMe SSD |
| 带宽 | 10Mbps | 100Mbps+ |

### 推荐的 VPS 服务商

对于对象存储场景，重点看**带宽和出站流量**：

- **Hetzner**：10Gbps 端口，无限流量（德国/芬兰），性价比之王
- **OVH**：500Gbps 端口，DDoS 防护，适合高流量场景
- **Contabo**：大硬盘便宜，适合纯存储需求
- **阿里云/腾讯云**：内网传输免费，适合国内业务

> 💡 **省钱技巧**：MinIO 对磁盘 I/O 敏感但不吃 CPU。选一块便宜的 SSD VPS 就够了，不需要 GPU 或高性能 CPU。

## 方案一：Docker 一键部署（推荐）

### 基础部署

```yaml
# docker-compose.yml
version: "3.8"

services:
  minio:
    image: quay.io/minio/minio:latest
    container_name: minio
    restart: unless-stopped
    ports:
      - "9000:9000"   # API 端口
      - "9001:9001"   # Console 端口
    environment:
      MINIO_ROOT_USER: your-access-key
      MINIO_ROOT_PASSWORD: your-secret-key
      MINIO_PROMETHEUS_AUTH_TYPE: public
    volumes:
      - /data/minio/data:/data
      - /data/minio/config:/root/.minio
    command: server /data --console-address ":9001"
    healthcheck:
      test: ["CMD", "mc", "ready", "local"]
      interval: 30s
      timeout: 20s
      retries: 3
```

启动：

```bash
mkdir -p /data/minio/{data,config}
chmod 750 /data/minio/data
docker compose up -d
```

### 初始化配置

访问 `http://your-vps-ip:9001`，使用刚才设置的 Access Key 和 Secret Key 登录。首次登录后：

1. 创建 Bucket（相当于文件夹）
2. 设置访问策略（公开/私有）
3. 配置用户和权限

### 启用 HTTPS（生产环境必做）

```bash
# 申请证书（使用 Certbot + Let's Encrypt）
apt install certbot python3-certbot-nginx -y

# 配置 Nginx 反向代理
cat > /etc/nginx/sites-available/minio <<'EOF'
server {
    listen 443 ssl http2;
    server_name minio.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/minio.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/minio.yourdomain.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;

    location / {
        proxy_pass http://127.0.0.1:9000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        client_max_body_size 0;  # 允许上传大文件
    }
}

server {
    listen 80;
    server_name minio.yourdomain.com;
    return 301 https://$host$request_uri;
}
EOF

nginx -t && systemctl reload nginx
```

更新 Docker Compose 环境变量：

```yaml
environment:
  MINIO_SERVER_URL: "https://minio.yourdomain.com"
  MINIO_BROWSER_REDIRECT_URL: "https://minio.yourdomain.com:9001"
```

## 方案二：分布式部署（多盘/多节点）

当单盘容量不够时，可以搭建分布式 MinIO 集群：

```yaml
version: "3.8"

services:
  minio:
    image: quay.io/minio/minio:latest
    container_name: minio-distributed
    restart: unless-stopped
    ports:
      - "9000:9000"
      - "9001:9001"
    environment:
      MINIO_ROOT_USER: your-access-key
      MINIO_ROOT_PASSWORD: your-secret-key
      MINIO_SERVER_URL: "https://minio.yourdomain.com"
    volumes:
      - /mnt/disk1/minio/data1:/data1
      - /mnt/disk2/minio/data2:/data2
      - /mnt/disk3/minio/data3:/data3
      - /mnt/disk4/minio/data4:/data4
      - /data/minio/config:/root/.minio
    command: server http://minio{1...4}/data{1...4} --console-address ":9001"
    
  # 如果是多节点集群，在每个节点上运行：
  # command: server http://node1/minio/data1 http://node2/minio/data2 http://node3/minio/data3 http://node4/minio/data4 --console-address ":9001"
```

> ⚠️ 分布式模式至少需要 4 个节点（或 4 个磁盘卷），支持 EC 纠删码（Erasure Coding），允许同时丢失一半的磁盘而不丢数据。

## 日常管理

### 使用 mc 命令行工具

MinIO 提供了 `mc` 命令行工具，类似 AWS CLI：

```bash
# 安装 mc
wget https://dl.min.io/client/mc/release/linux-amd64/mc
chmod +x mc
sudo mv mc /usr/local/bin/

# 配置别名
mc alias set myminio http://localhost:9000 your-access-key your-secret-key

# 创建 bucket
mc mb myminio/my-backups

# 上传文件
mc cp ./large-file.tar.gz myminio/my-backups/

# 列出所有 bucket
mc ls myminio

# 查看 bucket 用量
mc du myminio/my-backups

# 同步本地目录到 MinIO
mc mirror ./local-data myminio/my-backups/
```

### 生命周期策略（自动清理旧数据）

在 Console 中配置 Lifecycle Rules，或直接用 mc：

```bash
# 30天后删除未版本化对象
mc ilm rule add myminio/photos --expiry-days 30

# 90天后将对象转为低频存储
mc ilm rule add myminio/videos --storage-class GLACIER --expiry-days 90
```

### 版本控制（防误删）

```bash
# 通过 mc 启用 bucket 版本控制
mc version suspend myminio/my-bucket   # 暂停
mc version enable myminio/my-bucket     # 启用
```

启用后，每次覆盖或删除操作都会创建新版本，可以恢复到任意历史版本。

## 安全加固

### 1. 网络隔离

```yaml
# docker-compose.yml 中添加
networks:
  minio-net:
    driver: bridge

services:
  minio:
    networks:
      - minio-net
    # 只暴露给内网，通过 Nginx 反向代理对外
    ports:
      - "127.0.0.1:9000:9000"
      - "127.0.0.1:9001:9001"
```

### 2. IAM 策略（最小权限）

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject"],
      "Resource": ["arn:aws:s3:::myapp/uploads/*"]
    },
    {
      "Effect": "Deny",
      "Action": ["s3:DeleteBucket"],
      "Resource": ["arn:aws:s3:::myapp"]
    }
  ]
}
```

### 3. 服务端加密（SSE）

MinIO 默认对所有写入进行服务端加密：

```bash
# 启用 SSE-S3（MinIO 管理密钥）
mc admin config set myminio encryption sse-s3

# 或使用 SSE-KMS（外部密钥管理）
mc admin config set myminio encryption sse-kms key-id=your-key-id
```

### 4. 审计日志

```bash
# 启用 audit 日志
mc admin trace myminio --verbose --all
```

## 备份与容灾

### 跨机房复制（CCR）

MinIO 支持跨集群复制，适合异地容灾：

```bash
# 在源集群上添加目标集群
mc mirror --region us-east-1 myminio/source-bucket backup-minio/dest-bucket

# 启用持续复制
mc replicate add myminio/source-bucket arn:minio:replication:backup-minio
```

### 定期快照备份

```bash
#!/bin/bash
# backup-minio.sh
BACKUP_DIR="/mnt/backup/minio"
DATE=$(date +%Y%m%d_%H%M%S)

# 使用 mc mirror 增量同步
mc mirror myminio/important-bucket ${BACKUP_DIR}/${DATE}/

# 保留最近 7 天备份
find ${BACKUP_DIR} -maxdepth 1 -mtime +7 -exec rm -rf {} \;

echo "Backup completed: ${DATE}"
```

## 性能调优

### 磁盘选择

MinIO 对磁盘 I/O 非常敏感：

| 磁盘类型 | 顺序读写 | 随机 IOPS | 适用场景 |
|----------|---------|-----------|----------|
| SATA SSD | 500MB/s | 50K | 个人/小团队 |
| NVMe SSD | 3GB/s | 500K+ | 生产环境 |
| HDD | 150MB/s | 100 | 仅冷数据存储 |

> 💡 **建议**：至少使用 SATA SSD，预算充足上 NVMe。不要将 MinIO 数据盘和系统盘混用。

### 网络优化

```bash
# 调整 TCP 参数
sysctl -w net.core.rmem_max=134217728
sysctl -w net.core.wmem_max=134217728
sysctl -w net.ipv4.tcp_window_scaling=1

# 持久化配置
cat >> /etc/sysctl.conf <<'EOF'
net.core.rmem_max = 134217728
net.core.wmem_max = 134217728
net.ipv4.tcp_window_scaling = 1
EOF
```

### 监控告警

MinIO 内置 Prometheus 指标暴露：

```yaml
# docker-compose.yml 添加
environment:
  MINIO_PROMETHEUS_AUTH_TYPE: public

# Grafana Dashboard 导入 ID: 14411
```

关键监控指标：
- `minio_http_requests_total` — 请求总量
- `minio_cluster_disk_offline_total` — 离线磁盘数
- `minio_bucket_usage_total` — Bucket 使用量
- `minio_heal_objects_effected_total` — 自愈对象数

## 成本对比总结

| 项目 | AWS S3 | MinIO 自建 (Hetzner CPX31) |
|------|--------|---------------------------|
| VPS 费用 | $0 | **$5.50/月** |
| 1TB 存储 | $23.00/月 | 包含在 VPS 中 |
| 100GB/月 出站流量 | $11.50 | 包含在无限流量中 |
| API 请求 | $0.0044/千次 | $0 |
| **总计（1TB + 100GB流量）** | **~$37/月** | **~$5.50/月** |

> **年省 $378**，数据量越大省得越多。

## 常见问题

### Q: MinIO 能替代所有云存储场景吗？

**不适合的场景**：
- 需要全球 CDN 加速分发 → 搭配 Cloudflare R2 或自建 CDN
- 需要极高可用性（99.999%）→ 需要多地域分布式部署
- 需要与其他云服务深度集成 → 如 AWS Lambda 触发器

**非常适合的场景**：
- 备份存储
- 静态网站托管
- 媒体文件存储（图片、视频）
- 开发/测试环境
- 内部应用的文件存储后端

### Q: 数据安全吗？

自建意味着你完全掌控数据。配合以下措施，安全性不输公有云：
- HTTPS + TLS 1.3
- 服务端加密（SSE）
- IAM 细粒度权限控制
- 定期异地备份
- 防火墙 + Fail2ban 保护

### Q: 如何迁移从 AWS S3 到 MinIO？

```bash
# 使用 s5cmd 高速迁移
curl -sSL https://github.com/peak/s5cmd/releases/latest/download/s5cmd_linux_amd64.tar.gz | tar xz
sudo mv s5cmd /usr/local/bin/

# 从 S3 同步到 MinIO
AWS_ACCESS_KEY_ID=xxx AWS_SECRET_ACCESS_KEY=xxx \
s5cmd sync s3://my-bucket/ minio.mydomain.com/my-bucket/
```

## 结语

MinIO 是自建对象存储的最佳选择——它足够简单，一条 Docker 命令就能跑起来；又足够强大，支持企业级的版本控制、加密和分布式部署。对于想要摆脱云存储账单、掌握数据主权的个人和团队来说，MinIO 是最值得投资的自托管项目之一。

**下一步行动**：
1. 选一台 VPS（推荐 Hetzner / OVH）
2. 部署 MinIO（参考上面的 Docker Compose）
3. 配置 HTTPS 和域名
4. 用 mc 或 S3 客户端连接测试
5. 开始迁移你的数据

---

*这篇文章对你有帮助吗？欢迎在 [GitHub](https://github.com/pengzz9527/selfvps) 提交 Issue 或 PR 来改进内容。*
