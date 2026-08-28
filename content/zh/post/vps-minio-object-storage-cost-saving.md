---
title: "VPS 自建 MinIO 对象存储：低成本替代 AWS S3 的完整方案"
date: 2026-08-28T10:00:00+08:00
description: "在 VPS 上部署 MinIO 对象存储服务，实现与 AWS S3 完全兼容的存储方案。从零开始搭建高可用对象存储集群，节省 90% 云存储费用，支持图片、视频、备份文件等多种场景。"
tags: ["MinIO", "对象存储", "S3兼容", "VPS", "自托管", "成本优化", "Docker", "数据存储"]
categories: ["自托管应用"]
slug: "vps-minio-object-storage-cost-saving"
image: "/images/posts/vps-minio-object-storage-cost-saving/featured.png"
draft: false
aliases: [/zh/post/vps-minio-object-storage-cost-saving/]
---

## 为什么自建对象存储？

云对象存储服务（如 AWS S3、阿里云 OSS）虽然方便，但费用会随着数据量线性增长。对于个人开发者、小团队或内容创作者来说，每月数十到数百美元的存储费用并不便宜。

**MinIO** 是一个高性能、分布式对象存储系统，完全兼容 S3 API，可以在自己的 VPS 上轻松部署。本文将以一个真实案例说明：某博主将 2TB 图片库从 AWS S3 迁移到 VPS 自建 MinIO，每月节省 $120。

## 核心优势对比

| 特性 | AWS S3 | 自建 MinIO (2TB VPS) |
|------|--------|----------------------|
| 月费用 | ~$46/月 (标准存储) | ~$20/月 (VPS 固定) |
| 请求费用 | 按量计费 | 免费 |
| 数据取出费 | 按 GB 计费 | 无 |
| 数据主权 | 存储在云厂商 | 完全自控 |
| API 兼容 | 原生 S3 | 100% S3 兼容 |
| 扩展性 | 无限 | 受 VPS 硬件限制 |

## 环境准备

### 推荐配置

- **CPU**: 2 核以上
- **内存**: 4GB 以上
- **磁盘**: SSD，建议 500GB+（根据需求扩展）
- **系统**: Ubuntu 22.04 / Debian 12
- **Docker**: 24.0+

```bash
# 更新系统
sudo apt update && sudo apt upgrade -y

# 安装 Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# 验证安装
docker --version && docker compose version
```

## 单节点部署（快速上手）

### 使用 Docker Compose

创建 `minio-single.yml`：

```yaml
version: '3.8'

services:
  minio:
    image: minio/minio:latest
    container_name: minio
    restart: unless-stopped
    ports:
      - "9000:9000"   # API 端口
      - "9001:9001"   # Console 端口
    environment:
      MINIO_ROOT_USER: admin
      MINIO_ROOT_PASSWORD: YourStrongPassword123!
      MINIO_REGION: cn-north-1
    volumes:
      - /data/minio/data:/data
      - /data/minio/config:/root/.minio
    command: server /data --console-address ":9001"
    
  minio-client:
    image: minio/mc:latest
    container_name: minio-client
    depends_on:
      - minio
    entrypoint: >
      /bin/sh -c "
      mc alias set minio http://minio:9000 admin YourStrongPassword123! &&
      mc mb minio/photos &&
      mc mb minio/backups &&
      mc mb minio/videos &&
      mc anon set download minio/photos &&
      tail -f /dev/null
      "
```

启动服务：

```bash
docker compose -f minio-single.yml up -d
```

### 访问管理控制台

- **Console**: `http://你的VPS_IP:9001`
- **用户名**: `admin`
- **密码**: `YourStrongPassword123!`

## 生产级部署（多节点集群）

### 架构设计

```
                    ┌─────────────────┐
                    │   Load Balancer  │
                    │   (Nginx/HAProxy)│
                    └────────┬────────┘
                             │
            ┌────────────────┼────────────────┐
            │                │                │
     ┌──────┴──────┐  ┌─────┴─────┐  ┌──────┴──────┐
     │  MinIO Node1 │  │ MinIO Node2│  │  MinIO Node3 │
     │  /data/1-4   │  │ /data/1-4  │  │  /data/1-4   │
     └──────────────┘  └────────────┘  └──────────────┘
          每节点4块盘         每节点4块盘         每节点4块盘
          (共12个盘)         (共12个盘)         (共12个盘)
```

### Docker Compose 集群配置

创建 `minio-cluster.yml`：

```yaml
version: '3.8'

services:
  minio1:
    image: minio/minio:latest
    container_name: minio1
    restart: unless-stopped
    hostname: minio1
    ports:
      - "9000:9000"
      - "9001:9001"
    environment:
      MINIO_ROOT_USER: admin
      MINIO_ROOT_PASSWORD: YourStrongPassword123!
      MINIO_SERVER_URL: http://minio1:9000
      MINIO_REGION: cn-north-1
    volumes:
      - /data1/minio:/data1
      - /data2/minio:/data2
      - /data3/minio:/data3
      - /data4/minio:/data4
    command: server http://minio{1...3}:9000/data{1...4} --console-address ":9001"
    networks:
      - minio-network

  minio2:
    image: minio/minio:latest
    container_name: minio2
    restart: unless-stopped
    hostname: minio2
    ports:
      - "9002:9000"
      - "9003:9001"
    environment:
      MINIO_ROOT_USER: admin
      MINIO_ROOT_PASSWORD: YourStrongPassword123!
      MINIO_SERVER_URL: http://minio2:9000
      MINIO_REGION: cn-north-1
    volumes:
      - /data1/minio:/data1
      - /data2/minio:/data2
      - /data3/minio:/data3
      - /data4/minio:/data4
    command: server http://minio{1...3}:9000/data{1...4} --console-address ":9003"
    networks:
      - minio-network

  minio3:
    image: minio/minio:latest
    container_name: minio3
    restart: unless-stopped
    hostname: minio3
    ports:
      - "9004:9000"
      - "9005:9001"
    environment:
      MINIO_ROOT_USER: admin
      MINIO_ROOT_PASSWORD: YourStrongPassword123!
      MINIO_SERVER_URL: http://minio3:9000
      MINIO_REGION: cn-north-1
    volumes:
      - /data1/minio:/data1
      - /data2/minio:/data2
      - /data3/minio:/data3
      - /data4/minio:/data4
    command: server http://minio{1...3}:9000/data{1...4} --console-address ":9005"
    networks:
      - minio-network

  nginx:
    image: nginx:alpine
    container_name: minio-nginx
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - ./ssl:/etc/nginx/ssl:ro
    depends_on:
      - minio1
      - minio2
      - minio3
    networks:
      - minio-network

networks:
  minio-network:
    driver: bridge
```

### Nginx 反代配置

创建 `nginx.conf`：

```nginx
events {
    worker_connections 4096;
}

http {
    upstream minio_servers {
        server minio1:9000;
        server minio2:9000;
        server minio3:9000;
    }

    server {
        listen 80;
        server_name _;
        return 301 https://$host$request_uri;
    }

    server {
        listen 443 ssl http2;
        server_name _;

        ssl_certificate     /etc/nginx/ssl/cert.pem;
        ssl_certificate_key /etc/nginx/ssl/key.pem;

        client_max_body_size 0;
        keepalive_requests 10000;
        keepalive_timeout 60;

        location / {
            proxy_pass                         http://minio_servers;
            proxy_http_version                 1.1;
            proxy_set_header                   Host              $host;
            proxy_set_header                   X-Real-IP         $remote_addr;
            proxy_set_header                   X-Forwarded-For   $proxy_add_x_forwarded_for;
            proxy_set_header                   X-Forwarded-Proto $scheme;
            proxy_set_header                   Connection        "";
            proxy_buffering                      off;
            proxy_request_buffering              off;
            proxy_read_timeout                   86400;
            proxy_send_timeout                   86400;
        }
    }
}
```

## 配置 Bucket 策略

### 使用 mc 客户端

```bash
# 添加 MinIO 别名
mc alias set myminio http://localhost:9000 admin YourStrongPassword123!

# 创建 Bucket
mc mb myminio/photos
mc mb myminio/backups
mc mb myminio/videos

# 设置公开读取（用于图片展示）
mc anonymous set download myminio/photos

# 设置私有（用于备份）
mc anonymous set none myminio/backups

# 查看策略
mc anonymous get myminio/photos
```

### 版本控制与生命周期策略

```bash
# 启用版本控制
mc version enable myminio/photos

# 设置生命周期规则：90天后删除旧版本
cat > lifecycle.json << 'EOF'
{
  "Rule": [
    {
      "ID": "expire-old-versions",
      "Status": "Enabled",
      "Filter": {},
      "NoncurrentVersionExpiration": {
        "NoncurrentDays": 90
      }
    }
  ]
}
EOF

mc ilm import myminio/photos < lifecycle.json
```

## S3 兼容 API 使用

### Python 示例

```python
import boto3
from botocore.config import Config

# 配置 S3 客户端（指向自建 MinIO）
s3 = boto3.client('s3',
    endpoint_url='http://your-vps-ip:9000',
    aws_access_key_id='admin',
    aws_secret_access_key='YourStrongPassword123!',
    config=Config(s3={'addressing_style': 'path'})
)

# 上传文件
s3.upload_file('large_file.zip', 'backups', 'backup_2026.zip')

# 列出 Bucket
buckets = s3.list_buckets()
for b in buckets['Buckets']:
    print(f"Bucket: {b['Name']}, Created: {b['CreationDate']}")

# 预签名 URL（7天有效）
url = s3.generate_presigned_url(
    'get_object',
    Params={'Bucket': 'photos', 'Key': 'image.jpg'},
    ExpiresIn=604800
)
print(f"访问链接: {url}")
```

### 常用 mc 命令速查

```bash
# 基本操作
mc ls myminio                          # 列出所有 Bucket
mc ls myminio/photos                   # 列出 Bucket 内容
mc cp localfile.zip myminio/backups/   # 上传文件
mc mb myminio/new-bucket               # 创建 Bucket
mc rm myminio/photos/old-file.jpg      # 删除文件

# 同步操作
mc mirror /local/data myminio/photos/  # 本地同步到 MinIO
mc mirror myminio/photos/ /local/data/ # MinIO 同步到本地

# 统计信息
mc du myminio/photos                   # 计算 Bucket 大小
mc stat myminio/photos/image.jpg       # 查看文件详情
```

## 性能调优

### 文件系统优化

```bash
# 使用 XFS 文件系统（适合大文件）
mkfs.xfs -f /dev/sdb
mount -o noatime,nodiratime /dev/sdb /data1

# 写入缓存优化
echo 'vm.dirty_ratio = 10' >> /etc/sysctl.conf
echo 'vm.dirty_background_ratio = 5' >> /etc/sysctl.conf
sysctl -p
```

### MinIO 性能调优

```bash
# 修改 MinIO 启动参数
export MINIO_BROWSER_REDIRECT_URL=http://your-vps:9001
export MINIO_STORAGE_CLASS_STANDARD=EC:2
export MINIO_STORAGE_CLASS_RRS=EC:1

# EC:2 表示双纠删码，允许同时丢失 1 个盘
```

## 备份与恢复

### 使用 rsync 备份 MinIO 数据

```bash
#!/bin/bash
# minio-backup.sh

REMOTE="backup-server:/mnt/minio-backup/"
LOCAL="/data/minio/data"

rsync -avz --delete \
    --exclude='*.tmp' \
    $LOCAL $REMOTE

# 保留最近 30 天的备份
find $REMOTE -type d -mtime +30 -exec rm -rf {} \; 2>/dev/null
```

### 跨地域复制

```bash
# 在第二个集群上创建远程别名
mc alias set remote-minio http://secondary-vps:9000 admin Password456!

# 创建复制规则
cat > replication.json << 'EOF'
{
  "Version": "2",
  "Rule": [
    {
      "ID": "replicate-to-secondary",
      "Status": "Enabled",
      "Priority": 1000,
      "Destination": {
        "bucket": "arn:aws:s3:::remote-bucket",
        "storageClass": "STANDARD",
        "secrets": [
          {
            "id": "secondary-creds",
            "accessKey": "admin",
            "secretKey": "Password456!"
          }
        ]
      },
      "CopyObjectOperation": {
        "filter": {
          "prefix": "photos/",
          "tags": []
        }
      }
    }
  ]
}
EOF
```

## 成本分析

### 自建 vs 云服务对比

假设每月 5TB 存储、100万次请求、500GB 流出：

| 项目 | AWS S3 | 自建 MinIO (500GB VPS) |
|------|--------|----------------------|
| 存储费用 | $115/月 | $20/月 (固定) |
| 请求费用 | ~$4/月 | $0 |
| 数据流出 | ~$45/月 | $0 (内网传输) |
| **总计** | **~$164/月** | **~$20/月** |
| **年省** | - | **~$1,728/年** |

### 注意事项

1. **性能上限**: 自建方案受限于 VPS 带宽和磁盘 I/O
2. **可靠性**: 需要自行维护高可用和备份策略
3. **运维成本**: 监控、更新、故障排查需要投入时间
4. **弹性扩展**: 流量突发时需要手动扩容

## 总结

自建 MinIO 对象存储是 VPS 用户实现数据自主可控、大幅降低存储成本的有效方案。通过 Docker Compose 快速部署单节点或集群，配合 S3 兼容 API 无缝对接现有应用，年节省数千美元存储费用。

关键点回顾：
- 单节点适合个人项目，集群模式支持高可用
- 完全兼容 S3 API，迁移成本极低
- SSD 存储 + XFS 文件系统可获得最佳性能
- 配合定期备份实现数据安全保障

---

**下一步**: 尝试将 Nextcloud、Wiki.js 等自托管应用的存储后端切换到 MinIO，进一步整合你的自托管生态。
