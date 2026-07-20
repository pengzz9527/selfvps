---
title: "Cloudflare R2 Complete Guide: Zero Egress Fee Object Storage, Goodbye AWS S3 Bills"
date: 2026-07-20T10:00:00+08:00
lastmod: 2026-07-20T10:00:00+08:00
slug: "cloudflare-r2-zero-egress"
image: /images/posts/cloudflare-r2-zero-egress/featured.png
tags: ["Cloudflare R2", "Object Storage", "Zero Egress Fee", "S3 Compatible", "Self-hosted", "Cost Saving", "CDN"]
categories: ["Cost Saving", "Infrastructure"]
aliases: [/en/post/cloudflare-r2-zero-egress/]
description: "Cloudflare R2 offers AWS S3-compatible object storage with zero egress fees. Learn how to host Hugo static sites on R2 + Cloudflare CDN and save dozens of dollars monthly."
draft: false
---

## Why You Need Cloudflare R2

For self-hosters and small teams, the most painful part of cloud bills is often **egress fees**. Take AWS S3 as an example:

| Provider | Storage $/GB/mo | Egress Fee $/GB | Request Fee /10K |
|----------|----------------|-----------------|------------------|
| AWS S3 Standard | $0.023 | **$0.09** | $5 |
| Backblaze B2 | $0.006 | $0.01 (free tier) | $0 |
| Cloudflare R2 | $0.015 | **$0** | $0 |
| MinIO Self-hosted | Electricity + HDD | Bandwidth cost | $0 |

R2's core advantage is clear: **zero egress fees**. This means when you put static assets, backup files, or media content on R2 and distribute them through Cloudflare CDN, you pay nothing for traffic regardless of how many people access it. For VPS users with limited bandwidth (e.g., 1TB/month), this is a massive cost optimization.

## Core Features of R2

### 1. Full S3 Compatibility

R2 uses the same API interface as AWS S3, meaning nearly every tool that supports S3 can connect directly:

```bash
# Sync local files to R2 using rclone
rclone copy ./website s3:r2-bucket --s3-provider=Cloudflare \
  --s3-env-auth --s3-chunk-size=50M

# Using awscli (with endpoint configured)
aws s3 cp file.zip s3://my-bucket/ \
  --endpoint-url https://ACCOUNT_ID.r2.cloudflarestorage.com
```

### 2. Zero Egress Fees

All data distributed from R2 through the Cloudflare network incurs **no charges**. Even if you access the R2 endpoint directly without Cloudflare CDN, there are no egress fees (but using CDN is recommended for better performance).

### 3. Automatic Replication & High Availability

R2 automatically replicates data across three geographic regions by default, providing 99.99% data availability. You don't need to configure multi-replica strategies yourself.

### 4. Unlimited Storage, Pay-as-you-go

No pre-provisioned capacity limits, no minimum spend. You pay only for what you store — perfect for starting small.

## Getting Started: Creating an R2 Bucket

### Step 1: Log in to Dashboard

1. Go to [Cloudflare Dashboard](https://dash.cloudflare.com)
2. Select **R2 Object Storage** from the left menu
3. Click **Create Bucket**

### Step 2: Create Your Bucket

```
Bucket Name: my-static-site
Region: auto (default is fine)
Storage Class: Standard
```

After creation, note your **Account ID** (visible in the top-right of the R2 page) — you'll need it later.

### Step 3: Create an API Token

Go to **R2 → API Tokens** and create a token with write permissions:

```json
{
  "name": "r2-write-token",
  "permissions": {
    "R2": "READ"
  }
}
```

> ⚠️ Security tip: The Secret Key can only be viewed once after generation. Save it securely.

## Use Case 1: Hosting a Hugo Static Site on R2

This is one of the most practical use cases. Upload your Hugo build artifacts to R2 and leverage Cloudflare CDN for global distribution.

### 1. Install s5cmd or rclone

**s5cmd** is recommended for its speed and simple commands:

```bash
# Ubuntu/Debian
wget https://github.com/peak/s5cmd/releases/download/v2.2.3/s5cmd_2.2.3_amd64.tar.gz
tar -xzf s5cmd_2.2.3_amd64.tar.gz
sudo mv s5cmd /usr/local/bin/

# Or use rclone
sudo apt install rclone
```

### 2. Configure Credentials

```bash
# With s5cmd
export AWS_ACCESS_KEY_ID="YOUR_R2_ACCESS_KEY"
export AWS_SECRET_ACCESS_KEY="YOUR...port AWS_DEFAULT_REGION="auto"

# Test connection
s5cmd ls s3://my-static-site
```

### 3. Build and Deploy

```bash
# Build Hugo site
hugo --minify

# Sync to R2 (first time)
s5cmd sync public/ s3://my-static-site/

# Set static website index
s5cmd put index.html s3://my-static-site/index.html

# Future updates just resync
hugo --minify && s5cmd sync public/ s3://my-static-site/
```

### 4. Configure Custom Domain

Add a CNAME record in Cloudflare Dashboard:

```
Type: CNAME
Name: static
Value: <bucket-name>.r2.dev
TTL: Auto
Proxy status: Proxied (orange cloud on)
```

Your site is now accessible at `static.yourdomain.com`, with all traffic routed through Cloudflare CDN.

## Use Case 2: R2 as VPS Backup Target

VPS backups are another major R2 use case. Since R2 has no egress fees, uploading backups from your VPS is extremely cheap.

### Backing Up with Restic

```bash
# Install restic
sudo apt install restic

# Initialize repository
restic init \
  --repo s3:s3.amazonaws.com/my-backup-bucket \
  --endpoint https://ACCOUNT_ID.r2.cloudflarestorage.com \
  --access-key YOUR_ACCESS_KEY \
  --secret-key YOUR_SECRET_KEY

# Backup critical directories
restic backup \
  --repo s3:s3.amazonaws.com/my-backup-bucket \
  --endpoint https://ACCOUNT_ID.r2.cloudflarestorage.com \
  --exclude='/proc/*' --exclude='/sys/*' \
  /etc /home /var/www

# Compress and encrypt
restic backup --compress zstd /data
```

### Automated Scheduled Backups

```bash
#!/bin/bash
# /usr/local/bin/r2-backup.sh

BACKUP_DIR="/tmp/restic-backup-$$"
mkdir -p "$BACKUP_DIR"

# Backup
restic backup \
  --repo s3:s3.amazonaws.com/my-backup-bucket \
  --endpoint https://ACCOUNT_ID.r2.cloudflarestorage.com \
  --password-file ~/.restic-password \
  /etc /home /var/www

# Prune old snapshots (keep last 7 days)
restic prune --repo s3:s3.amazonaws.com/my-backup-bucket \
  --endpoint https://ACCOUNT_ID.r2.cloudflarestorage.com \
  --password-file ~/.restic-password

# Cleanup
rm -rf "$BACKUP_DIR"
```

Add to crontab:

```cron
0 2 * * * /usr/local/bin/r2-backup.sh >> /var/log/r2-backup.log 2>&1
```

## Use Case 3: R2 + Workers for Dynamic Image Processing

For dynamic image processing (thumbnails, watermarks, format conversion), combine Cloudflare Workers with R2 to build a Serverless image service.

```javascript
// Cloudflare Worker example: dynamic thumbnail generation
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname.slice(1);
    
    // Fetch original image
    const object = await env.MY_BUCKET.get(path);
    if (!object) return new Response('Not Found', { status: 404 });
    
    // Process image (using R2 Image Resizing)
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

## Cost Comparison: R2 vs S3 vs Self-hosted MinIO

Assuming your site serves 100GB of static assets per month:

| Item | AWS S3 | Cloudflare R2 | MinIO Self-hosted |
|------|--------|---------------|-------------------|
| Store 100GB | $2.30 | $1.50 | $0 (HDD cost) |
| 100GB Egress | **$9.00** | **$0** | Bandwidth fee |
| 10M Requests | $5.00 | $0 | $0 |
| CDN Cost | $0 (CloudFront extra) | $0 (included) | VPS bandwidth |
| **Monthly Total** | **~$16.30** | **~$1.50** | Electricity + HDD |

For small to medium users, R2's total cost is typically **1/10th or less** of S3.

## Best Practices & Considerations

### ✅ Recommended

1. **Enable Cloudflare CDN Proxy**: Turn on the orange cloud for global acceleration and DDoS protection
2. **Set appropriate Cache-Control**: Long cache times for static assets
3. **Enable Versioning**: Protect against accidental deletions
4. **Configure CORS**: If frontend JS needs direct access, set up cross-origin policies
5. **Monitor Usage**: Set usage alerts in Cloudflare Dashboard

### ⚠️ Things to Know

- **Cold Start Latency**: First access may have slight delay (CDN origin fetch)
- **List Performance**: Large file listing is not as efficient as S3
- **Lifecycle Rules**: Basic lifecycle management supported, but less flexible than S3
- **Cross-region Replication**: Manual region selection not currently available
- **Free Plan Limits**: 100K reads/day, 1K writes/day on free tier

### 💡 Advanced Tips

```bash
# Batch delete expired files
s5cmd rm "s3://my-bucket/old-files/*.tmp"

# Set public read ACL (for static assets)
s5cmd cp --acl public-read image.jpg s3://my-bucket/images/

# Use multipart upload for large files
s5cmd cp large-backup.tar.gz s3://my-bucket/backups/ \
  --concurrency 10 --chunk-size 100M
```

## Summary

Cloudflare R2 is currently one of the most cost-effective object storage solutions for the self-hosting community. The **zero egress fee** feature makes it an ideal choice for static site hosting, backup storage, and CDN origin scenarios.

For VPS users, migrating static assets to R2 can:
- 📉 Significantly reduce monthly cloud spending
- 🚀 Leverage Cloudflare's global CDN for acceleration
- 🔒 Gain enterprise-grade data security and high availability
- 🔄 Seamlessly replace existing S3 workflows

If your VPS bandwidth is nearing its limit, or you're looking for a more economical static asset hosting solution, R2 is definitely worth trying.
