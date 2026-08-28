---
title: "Self-Hosted MinIO Object Storage on VPS: Complete Guide to Cutting Cloud Storage Costs"
date: 2026-08-28T10:00:00+08:00
description: "Deploy MinIO object storage on your VPS as a cost-effective alternative to AWS S3. Complete guide covering single-node setup, multi-node clusters, S3-compatible API usage, performance tuning, and real cost savings analysis."
tags: ["MinIO", "Object Storage", "S3 Compatible", "VPS", "Self-Hosting", "Cost Optimization", "Docker", "Data Storage"]
categories: ["Self-Hosted Apps"]
slug: "vps-minio-object-storage-cost-saving"
image: "/images/posts/vps-minio-object-storage-cost-saving/featured.png"
draft: false
aliases: [/en/post/vps-minio-object-storage-cost-saving/]
---

## Why Self-Host Object Storage?

Cloud object storage services (like AWS S3, Aliyun OSS) are convenient, but costs grow linearly with data volume. For individual developers, small teams, or content creators, monthly storage bills of tens to hundreds of dollars add up quickly.

**MinIO** is a high-performance, distributed object storage system that is fully S3 API-compatible and can be easily deployed on your own VPS. This article presents a real-world case: a blogger migrated a 2TB photo library from AWS S3 to a self-hosted MinIO on VPS, saving $120 per month.

## Key Advantages Comparison

| Feature | AWS S3 | Self-Hosted MinIO (2TB VPS) |
|---------|--------|----------------------------|
| Monthly Cost | ~$46/mo (Standard) | ~$20/mo (Fixed VPS) |
| Request Fees | Pay-per-request | Free |
| Egress Fees | Per GB | None |
| Data Sovereignty | Stored on cloud provider | Fully under your control |
| API Compatibility | Native S3 | 100% S3 Compatible |
| Scalability | Unlimited | Limited by VPS hardware |

## Environment Setup

### Recommended Configuration

- **CPU**: 2+ cores
- **Memory**: 4GB+
- **Disk**: SSD, 500GB+ recommended (expandable)
- **OS**: Ubuntu 22.04 / Debian 12
- **Docker**: 24.0+

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# Verify installation
docker --version && docker compose version
```

## Single-Node Deployment (Quick Start)

### Docker Compose Configuration

Create `minio-single.yml`:

```yaml
version: '3.8'

services:
  minio:
    image: minio/minio:latest
    container_name: minio
    restart: unless-stopped
    ports:
      - "9000:9000"   # API port
      - "9001:9001"   # Console port
    environment:
      MINIO_ROOT_USER: admin
      MINIO_ROOT_PASSWORD: YourStrongPassword123!
      MINIO_REGION: us-east-1
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

Start the service:

```bash
docker compose -f minio-single.yml up -d
```

### Access the Admin Console

- **Console**: `http://your-vps-ip:9001`
- **Username**: `admin`
- **Password**: `YourStrongPassword123!`

## Production-Grade Deployment (Multi-Node Cluster)

### Architecture Design

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
          4 disks each         4 disks each         4 disks each
          (12 disks total)     (12 disks total)     (12 disks total)
```

### Docker Compose Cluster Configuration

Create `minio-cluster.yml`:

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
      MINIO_REGION: us-east-1
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
      MINIO_REGION: us-east-1
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
      MINIO_REGION: us-east-1
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

### Nginx Reverse Proxy Configuration

Create `nginx.conf`:

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

## Configuring Bucket Policies

### Using the mc Client

```bash
# Add MinIO alias
mc alias set myminio http://localhost:9000 admin YourStrongPassword123!

# Create buckets
mc mb myminio/photos
mc mb myminio/backups
mc mb myminio/videos

# Set public read (for photo display)
mc anonymous set download myminio/photos

# Set private (for backups)
mc anonymous set none myminio/backups

# View policies
mc anonymous get myminio/photos
```

### Version Control and Lifecycle Policies

```bash
# Enable versioning
mc version enable myminio/photos

# Set lifecycle rule: expire old versions after 90 days
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

## S3-Compatible API Usage

### Python Example

```python
import boto3
from botocore.config import Config

# Configure S3 client (pointing to self-hosted MinIO)
s3 = boto3.client('s3',
    endpoint_url='http://your-vps-ip:9000',
    aws_access_key_id='admin',
    aws_secret_access_key='YourStrongPassword123!',
    config=Config(s3={'addressing_style': 'path'})
)

# Upload file
s3.upload_file('large_file.zip', 'backups', 'backup_2026.zip')

# List buckets
buckets = s3.list_buckets()
for b in buckets['Buckets']:
    print(f"Bucket: {b['Name']}, Created: {b['CreationDate']}")

# Presigned URL (valid for 7 days)
url = s3.generate_presigned_url(
    'get_object',
    Params={'Bucket': 'photos', 'Key': 'image.jpg'},
    ExpiresIn=604800
)
print(f"Access URL: {url}")
```

### Essential mc Commands Cheat Sheet

```bash
# Basic operations
mc ls myminio                          # List all buckets
mc ls myminio/photos                   # List bucket contents
mc cp localfile.zip myminio/backups/   # Upload file
mc mb myminio/new-bucket               # Create bucket
mc rm myminio/photos/old-file.jpg      # Delete file

# Sync operations
mc mirror /local/data myminio/photos/  # Sync local to MinIO
mc mirror myminio/photos/ /local/data/ # Sync MinIO to local

# Statistics
mc du myminio/photos                   # Calculate bucket size
mc stat myminio/photos/image.jpg       # View file details
```

## Performance Tuning

### Filesystem Optimization

```bash
# Use XFS filesystem (ideal for large files)
mkfs.xfs -f /dev/sdb
mount -o noatime,nodiratime /dev/sdb /data1

# Write cache optimization
echo 'vm.dirty_ratio = 10' >> /etc/sysctl.conf
echo 'vm.dirty_background_ratio = 5' >> /etc/sysctl.conf
sysctl -p
```

### MinIO Performance Tuning

```bash
# Modify MinIO startup parameters
export MINIO_BROWSER_REDIRECT_URL=http://your-vps:9001
export MINIO_STORAGE_CLASS_STANDARD=EC:2
export MINIO_STORAGE_CLASS_RRS=EC:1

# EC:2 means double erasure coding, allows losing 1 disk simultaneously
```

## Backup and Recovery

### Using rsync to Backup MinIO Data

```bash
#!/bin/bash
# minio-backup.sh

REMOTE="backup-server:/mnt/minio-backup/"
LOCAL="/data/minio/data"

rsync -avz --delete \
    --exclude='*.tmp' \
    $LOCAL $REMOTE

# Keep only the last 30 days of backups
find $REMOTE -type d -mtime +30 -exec rm -rf {} \; 2>/dev/null
```

### Cross-Region Replication

```bash
# On the second cluster, create a remote alias
mc alias set remote-minio http://secondary-vps:9000 admin Password456!

# Create replication rules
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

## Cost Analysis

### Self-Hosted vs Cloud Service Comparison

Assuming 5TB storage, 1M requests, and 500GB egress per month:

| Item | AWS S3 | Self-Hosted MinIO (500GB VPS) |
|------|--------|-------------------------------|
| Storage Cost | $115/mo | $20/mo (Fixed) |
| Request Fees | ~$4/mo | $0 |
| Egress Fees | ~$45/mo | $0 (Internal transfer) |
| **Total** | **~$164/mo** | **~$20/mo** |
| **Yearly Savings** | - | **~$1,728/year** |

### Important Considerations

1. **Performance Ceiling**: Self-hosted solutions are limited by VPS bandwidth and disk I/O
2. **Reliability**: Requires self-maintained high availability and backup strategies
3. **Operations Cost**: Monitoring, updates, and troubleshooting require time investment
4. **Elastic Scaling**: Manual scaling needed during traffic spikes

## Summary

Self-hosting MinIO object storage is an effective solution for VPS users seeking data sovereignty and significant storage cost reduction. Deploy quickly with Docker Compose (single node or cluster), integrate seamlessly with existing applications via S3-compatible APIs, and save thousands of dollars annually on storage fees.

Key takeaways:
- Single-node suitable for personal projects; cluster mode supports high availability
- Fully S3 API compatible with minimal migration cost
- SSD storage + XFS filesystem delivers best performance
- Pair with regular backups for data security assurance

---

**Next Step**: Try switching the storage backend of self-hosted apps like Nextcloud or Wiki.js to MinIO, further integrating your self-hosted ecosystem.
