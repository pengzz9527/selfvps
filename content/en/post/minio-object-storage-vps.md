---
title: "Self-Host MinIO Object Storage: The Complete Guide to Replacing AWS S3 on Your VPS"
description: "Deploy MinIO object storage on your VPS from scratch — S3-compatible, Docker one-command setup, HTTPS encryption, auto-backup and cross-region replication for under $5/month"
date: 2026-06-28T10:00:00+08:00
lastmod: 2026-06-28T10:00:00+08:00
slug: "minio-object-storage-vps"
tags: ["MinIO", "S3", "Object Storage", "Docker", "VPS Deployment", "Self-Hosted", "Cloud Savings", "Private Cloud"]
categories: ["Deployment Guides"]
image: /images/posts/minio-object-storage-vps/featured.png
draft: false
---

## Why Self-Host Object Storage?

AWS S3 is the world's most popular object storage service, but costs skyrocket as your data grows. For individual developers, small teams, or content creators:

| Scenario | AWS S3 Monthly Cost | MinIO Self-Hosted Monthly Cost |
|----------|-------------------|-------------------------------|
| 100GB storage | ~$2.30 | **$0.50** (VPS share) |
| 1TB storage | ~$23.00 | **$0.50** |
| 5TB storage | ~$115.00 | **$0.50** |
| 1M reads/month | ~$4.00 | **$0.50** |
| Data transfer (outbound) | **Unlimited cost, no cap** | **Included in VPS bandwidth** |

Key insight: **S3's Data Transfer Out fees are the most overlooked cost trap**. With self-hosted MinIO, as long as your VPS has sufficient bandwidth, data transfer is essentially "free."

## What Is MinIO?

[MinIO](https://min.io/) is a high-performance, S3 API-compatible object storage server written in Go. Its core features:

- **Full S3 Compatibility**: Any tool supporting S3 works out of the box
- **Minimal Deployment**: One Docker command to start
- **Low Resource Usage**: Runs on 1GB RAM
- **Enterprise Features**: Versioning, lifecycle policies, encryption, cross-cluster replication
- **Open Source & Free**: AGPL v3 licensed

## Prerequisites

### Hardware Requirements

| Config | Minimum | Recommended |
|--------|---------|-------------|
| CPU | 1 core | 2+ cores |
| RAM | 1GB | 2GB+ |
| Storage | 50GB SSD | 200GB+ NVMe SSD |
| Bandwidth | 10Mbps | 100Mbps+ |

### Recommended VPS Providers

For object storage, focus on **bandwidth and outbound traffic**:

- **Hetzner**: 10Gbps port, unlimited traffic (Germany/Finland), best value
- **OVH**: 500Gbps port, DDoS protection, ideal for high traffic
- **Contabo**: Large disks cheap, great for pure storage needs
- **Alibaba Cloud / Tencent Cloud**: Free internal transfer, ideal for China-based services

> 💡 **Money-saving tip**: MinIO is I/O-sensitive but CPU-light. A cheap SSD VPS is enough—no GPU or high-performance CPU needed.

## Option 1: Docker One-Command Deployment (Recommended)

### Basic Setup

```yaml
# docker-compose.yml
version: "3.8"

services:
  minio:
    image: quay.io/minio/minio:latest
    container_name: minio
    restart: unless-stopped
    ports:
      - "9000:9000"   # API port
      - "9001:9001"   # Console port
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

Start:

```bash
mkdir -p /data/minio/{data,config}
chmod 750 /data/minio/data
docker compose up -d
```

### Initial Configuration

Visit `http://your-vps-ip:9001`, log in with your Access Key and Secret Key. After first login:

1. Create Buckets (like folders)
2. Set access policies (public/private)
3. Configure users and permissions

### Enable HTTPS (Required for Production)

```bash
# Get certificates (Certbot + Let's Encrypt)
apt install certbot python3-certbot-nginx -y

# Configure Nginx reverse proxy
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
        client_max_body_size 0;  # Allow large file uploads
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

Update Docker Compose environment variables:

```yaml
environment:
  MINIO_SERVER_URL: "https://minio.yourdomain.com"
  MINIO_BROWSER_REDIRECT_URL: "https://minio.yourdomain.com:9001"
```

## Option 2: Distributed Deployment (Multi-Disk / Multi-Node)

When a single disk isn't enough, set up a distributed MinIO cluster:

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
    
  # For multi-node clusters, run on each node:
  # command: server http://node1/minio/data1 http://node2/minio/data2 http://node3/minio/data3 http://node4/minio/data4 --console-address ":9001"
```

> ⚠️ Distributed mode requires at least 4 nodes (or 4 disk volumes) and supports Erasure Coding, allowing simultaneous loss of half the disks without data loss.

## Daily Management

### Using the mc CLI Tool

MinIO provides the `mc` command-line tool, similar to AWS CLI:

```bash
# Install mc
wget https://dl.min.io/client/mc/release/linux-amd64/mc
chmod +x mc
sudo mv mc /usr/local/bin/

# Configure alias
mc alias set myminio http://localhost:9000 your-access-key your-secret-key

# Create bucket
mc mb myminio/my-backups

# Upload file
mc cp ./large-file.tar.gz myminio/my-backups/

# List all buckets
mc ls myminio

# Check bucket usage
mc du myminio/my-backups

# Sync local directory to MinIO
mc mirror ./local-data myminio/my-backups/
```

### Lifecycle Policies (Auto-Cleanup Old Data)

Configure Lifecycle Rules in the Console, or use mc directly:

```bash
# Delete non-versioned objects after 30 days
mc ilm rule add myminio/photos --expiry-days 30

# Move objects to infrequent storage after 90 days
mc ilm rule add myminio/videos --storage-class GLACIER --expiry-days 90
```

### Version Control (Anti-Accidental-Deletion)

```bash
# Enable bucket versioning via mc
mc version suspend myminio/my-bucket   # Pause
mc version enable myminio/my-bucket     # Enable
```

Once enabled, every overwrite or delete operation creates a new version—you can restore any historical version.

## Security Hardening

### 1. Network Isolation

```yaml
# Add to docker-compose.yml
networks:
  minio-net:
    driver: bridge

services:
  minio:
    networks:
      - minio-net
    # Only expose to localhost, serve through Nginx reverse proxy
    ports:
      - "127.0.0.1:9000:9000"
      - "127.0.0.1:9001:9001"
```

### 2. IAM Policies (Least Privilege)

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

### 3. Server-Side Encryption (SSE)

MinIO encrypts all writes by default:

```bash
# Enable SSE-S3 (MinIO-managed keys)
mc admin config set myminio encryption sse-s3

# Or SSE-KMS (external key management)
mc admin config set myminio encryption sse-kms key-id=your-key-id
```

### 4. Audit Logging

```bash
# Enable audit logging
mc admin trace myminio --verbose --all
```

## Backup & Disaster Recovery

### Cross-Cluster Replication (CCR)

MinIO supports cross-cluster replication for geo-disaster recovery:

```bash
# Add target cluster on source
mc mirror --region us-east-1 myminio/source-bucket backup-minio/dest-bucket

# Enable continuous replication
mc replicate add myminio/source-bucket arn:minio:replication:backup-minio
```

### Scheduled Snapshot Backups

```bash
#!/bin/bash
# backup-minio.sh
BACKUP_DIR="/mnt/backup/minio"
DATE=$(date +%Y%m%d_%H%M%S)

# Incremental sync with mc mirror
mc mirror myminio/important-bucket ${BACKUP_DIR}/${DATE}/

# Keep last 7 days of backups
find ${BACKUP_DIR} -maxdepth 1 -mtime +7 -exec rm -rf {} \;

echo "Backup completed: ${DATE}"
```

## Performance Tuning

### Disk Selection

MinIO is very sensitive to disk I/O:

| Disk Type | Sequential Read/Write | Random IOPS | Use Case |
|-----------|---------------------|-------------|----------|
| SATA SSD | 500MB/s | 50K | Personal/small team |
| NVMe SSD | 3GB/s | 500K+ | Production |
| HDD | 150MB/s | 100 | Cold storage only |

> 💡 **Recommendation**: At least SATA SSD; NVMe if budget allows. Never mix MinIO data disks with the system disk.

### Network Optimization

```bash
# Tune TCP parameters
sysctl -w net.core.rmem_max=134217728
sysctl -w net.core.wmem_max=134217728
sysctl -w net.ipv4.tcp_window_scaling=1

# Persist configuration
cat >> /etc/sysctl.conf <<'EOF'
net.core.rmem_max = 134217728
net.core.wmem_max = 134217728
net.ipv4.tcp_window_scaling = 1
EOF
```

### Monitoring & Alerting

MinIO exposes Prometheus metrics natively:

```yaml
# Add to docker-compose.yml
environment:
  MINIO_PROMETHEUS_AUTH_TYPE: public

# Import Grafana Dashboard ID: 14411
```

Key monitoring metrics:
- `minio_http_requests_total` — Total requests
- `minio_cluster_disk_offline_total` — Offline disks
- `minio_bucket_usage_total` — Bucket usage
- `minio_heal_objects_effected_total` — Healed objects

## Cost Comparison Summary

| Item | AWS S3 | MinIO Self-Hosted (Hetzner CPX31) |
|------|--------|----------------------------------|
| VPS Cost | $0 | **$5.50/month** |
| 1TB Storage | $23.00/month | Included in VPS |
| 100GB/mo Outbound Traffic | $11.50 | Included (unlimited) |
| API Requests | $0.0044/1K | $0 |
| **Total (1TB + 100GB traffic)** | **~$37/month** | **~$5.50/month** |

> **Save $378/year**, and the more data you have, the more you save.

## FAQ

### Q: Can MinIO replace all cloud storage scenarios?

**Not ideal for**:
- Global CDN acceleration → Pair with Cloudflare R2 or self-hosted CDN
- Ultra-high availability (99.999%) → Requires multi-region distributed deployment
- Deep integration with other cloud services → e.g., AWS Lambda triggers

**Perfect for**:
- Backup storage
- Static website hosting
- Media file storage (images, videos)
- Development/testing environments
- Internal application file storage backend

### Q: Is it secure?

Self-hosting means you have complete control over your data. Combined with these measures, security rivals public clouds:
- HTTPS + TLS 1.3
- Server-side encryption (SSE)
- Fine-grained IAM access controls
- Regular off-site backups
- Firewall + Fail2ban protection

### Q: How to migrate from AWS S3 to MinIO?

```bash
# Use s5cmd for high-speed migration
curl -sSL https://github.com/peak/s5cmd/releases/latest/download/s5cmd_linux_amd64.tar.gz | tar xz
sudo mv s5cmd /usr/local/bin/

# Sync from S3 to MinIO
AWS_ACCESS_KEY_ID=xxx AWS_SECRET_ACCESS_KEY=*** \
s5cmd sync s3://my-bucket/ minio.yourdomain.com/my-bucket/
```

## Conclusion

MinIO is the best choice for self-hosted object storage—it's simple enough to run with one Docker command, yet powerful enough to support enterprise-grade versioning, encryption, and distributed deployment. For individuals and teams looking to escape cloud storage bills and take back data sovereignty, MinIO is one of the most worthwhile self-hosted projects to invest in.

**Next Steps**:
1. Pick a VPS (recommended: Hetzner / OVH)
2. Deploy MinIO (see Docker Compose above)
3. Configure HTTPS and domain
4. Connect and test with mc or an S3 client
5. Start migrating your data

---

*Found this helpful? Feel free to submit Issues or PRs on [GitHub](https://github.com/pengzz9527/selfvps) to improve the content.*
