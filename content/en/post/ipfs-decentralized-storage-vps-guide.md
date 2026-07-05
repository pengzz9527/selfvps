---
title: "IPFS Decentralized Storage: Build a Permanent File Network on Your VPS"
description: "Deploy an IPFS node from scratch, build censorship-resistant persistent storage, configure pinning services, publish websites, and understand content addressing."
date: 2026-07-05T10:00:00+08:00
lastmod: 2026-07-05T10:00:00+08:00
slug: "ipfs-decentralized-storage-vps-guide"
tags: ["IPFS", "Decentralized Storage", "VPS Deployment", "Self-Hosting", "File Sharing", "Web3", "Distributed Systems", "Pinning"]
categories: ["Deployment Guide"]
draft: false
image: /images/posts/ipfs-decentralized-storage-vps-guide/featured.png
aliases: [/en/post/ipfs-decentralized-storage-vps-guide/]
---

## What Is IPFS?

IPFS (InterPlanetary File System) is a decentralized, peer-to-peer protocol for storing and transferring files. Unlike traditional HTTP, IPFS uses **content addressing** instead of location addressing — you don't need to remember a server address; you retrieve files by their cryptographic hash.

This means:
- Files published on IPFS are **permanently accessible** (as long as someone pins them)
- No single point of failure, censorship-resistant
- The same file is distributed across multiple nodes globally, resulting in faster access

## Why Run an IPFS Node on Your VPS?

Most individual developers only consume IPFS (via IPFS Desktop or services like Pinata). But if you want to truly leverage decentralized storage in your self-hosting ecosystem, running your own IPFS node is the best approach:

| Advantage | Description |
|-----------|-------------|
| **Full control** | Data isn't dependent on third-party providers; your VPS becomes part of the network |
| **Low cost** | A $5/month VPS is sufficient for a production-grade IPFS node |
| **Persistent storage** | Combined with IPFS pinning services, critical files stay online long-term |
| **Censorship resistance** | No central authority can remove your files |
| **Development & testing** | Local nodes make it easy to test dApps, NFT metadata, and static site deployment |

## Prerequisites

- Ubuntu 22.04/24.04 VPS (recommended 2C4G or higher)
- At least 50GB SSD storage (the IPFS repository grows over time)
- Public IP or Cloudflare Tunnel for exposure
- Docker installed

> **Note:** Disk usage depends on how much content you pin. If you're running a basic node without actively pinning large amounts of data, 10-20GB is enough to start.

## Step 1: Deploy the IPFS Node

Docker makes this straightforward:

```bash
# Create persistent storage directories
mkdir -p ~/ipfs/data ~/ipfs/config

# Start the IPFS node
docker run -d \
  --name ipfs-node \
  --restart unless-stopped \
  -v ~/ipfs/data:/data/ipfs \
  -v ~/ipfs/config:/config/ipfs \
  -p 4001:4001/tcp \
  -p 4001:4001/udp \
  -p 5001:5001 \
  -p 8080:8080 \
  -e IPFS_PATH=/data/ipfs \
  ghcr.io/ipfs/kubo:latest
```

Port explanations:
- `4001`: libp2p communication port (node-to-node data exchange)
- `5001`: API port (local management interface)
- `8080`: HTTP Gateway (access IPFS content via browser)

Verify the installation:

```bash
docker exec ipfs-node ipfs id
```

You should see output like:

```json
{
  "ID": "12D3Koo...",
  "Addresses": [...],
  "AgentVersion": "kubo/0.30.0/",
  "ProtocolVersion": "ipfs/0.1.0"
}
```

## Step 2: Configuration & Optimization

### Adjust Storage Strategy

By default, IPFS automatically removes infrequently accessed content (ARC policy). To make your node an effective pinning node, adjust the configuration:

```bash
# Disable automatic garbage collection interval
docker exec ipfs-node ipfs config Republisher.RepublishPeriod 24h
docker exec ipfs-node ipfs config Datastore.GCThreshold 100GiB

# Restart the node
docker restart ipfs-node
```

### Add Bootstrap Nodes

Ensure your node can discover peers on the network:

```bash
docker exec ipfs-node ipfs bootstrap add /dnsaddr/bootstrap.libp2p.io/p/quic-v1
docker exec ipfs-node ipfs bootstrap add /dnsaddr/bootstrap.libp2p.io/p/tcp
```

### Configure HTTP Gateway

Enable the gateway for convenient browser-based access to IPFS content:

```bash
# Enable public gateway (use caution — may expose your node)
docker exec ipfs-node ipfs config Gateway.HTTPHeaders.Access-Control-Allow-Origin '["*"]'
docker exec ipfs-node ipfs config Gateway.PublicPath /ipfs
docker exec ipfs-node ipfs config Gateway.IPCIDPath /ipfs/raw
```

## Step 3: Upload & Retrieve Files

### Upload Files

```bash
# Upload a single file
docker exec -i ipfs-node ipfs add < myfile.txt

# Upload an entire directory
docker exec -i ipfs-node ipfs add -r ./my-folder/

# Example output:
# added QmXoypizjy4WQi5dEexbG1fovVJXYqUVhBNkfKapFcRZKw myfile.txt
```

The returned `QmXo...` string is the file's **CID** (Content Identifier). You use this to reference the file anywhere on the IPFS network.

### Retrieve Files by CID

```bash
# Download a file by CID
docker exec ipfs-node ipfs get QmXoypizjy4WQi5dEexbG1fovVJXYqUVhBNkfKapFcRZKw

# Access via HTTP Gateway (also works in browsers)
curl http://localhost:8080/ipfs/QmXoypizjy4WQi5dEexbG1fovVJXYqUVhBNkfKapFcRZKw
```

### Pin Content Permanently

Ensure your files remain available on the network long-term:

```bash
# Pin a specific CID
docker exec ipfs-node ipfs pin add QmXoypizjy4WQi5dEexbG1fovVJXYqUVhBNkfKapFcRZKw

# List all pinned content
docker exec ipfs-node ipfs pin ls

# Unpin (remove from your node)
docker exec ipfs-node ipfs pin rm QmXoypizjy4WQi5dEexbG1fovVJXYqUVhBNkfKapFcRZKw
```

## Step 4: Publish a Website on IPFS

IPFS is ideal for hosting static websites with permanent availability.

### Method 1: Direct HTML Upload

```bash
# Create a sample website
mkdir -p ~/my-site
cat > ~/my-site/index.html << 'EOF'
<!DOCTYPE html>
<html>
<head><title>My IPFS Site</title></head>
<body>
<h1>Hello from IPFS!</h1>
<p>This site is permanently available on the decentralized web.</p>
</body>
</html>
EOF

# Upload and get the CID
cd ~/my-site
CID=$(docker exec -i ipfs-node ipfs add -r --cid-version 1 . | tail -1 | awk '{print $NF}')
echo "Site CID: $CID"
echo "Visit: https://gateway.ipfs.io/ipfs/$CID"
```

### Method 2: Nginx Reverse Proxy + IPFS Gateway

Use Nginx as a reverse proxy to serve IPFS content from your local node:

```nginx
server {
    listen 80;
    server_name files.yourdomain.com;

    location /ipfs/ {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
    }

    location /api/v0/ {
        proxy_pass http://127.0.0.1:5001;
        proxy_set_header Host $host;
        # Allow only local API access
        allow 127.0.0.1;
        deny all;
    }
}
```

## Advanced: Paid Pinning Services

If your VPS disk is limited or you want higher availability, supplement your node with paid pinning services:

| Service | Free Tier | Features |
|---------|-----------|----------|
| [Pinata](https://pinata.cloud) | 1GB | Most popular IPFS pinning service, comprehensive API |
| [Infura](https://infura.io) | Free | Good Ethereum ecosystem integration |
| [web3.storage](https://web3.storage) | 1TB | By Protocol Labs, developer-friendly |
| [Crust Network](https://crust.network) | Free | Decentralized pinning based on Polkadot |

Usage example:

```bash
# Upload via Pinata API
curl -X POST "https://api.pinata.cloud/pinning/pinFileToIPFS" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -F "file=@myfile.pdf"

# The returned pinned_hash — pin it on your local node too
docker exec ipfs-node ipfs pin add /ipfs/QmYourHashHere
```

## FAQ

### Q: My IPFS node is using too much disk space?

Clean up unpinned content regularly:

```bash
# Manually trigger garbage collection
docker exec ipfs-node ipfs repo gc

# Check storage usage
docker exec ipfs-node ipfs repo stat
```

Set up monitoring on `repo.stat` and alert when usage exceeds a threshold.

### Q: How do I make my node publicly reachable?

IPFS nodes need to establish connections with other peers. Ensure firewall rules allow:

```bash
# Allow libp2p ports
sudo ufw allow 4001/tcp
sudo ufw allow 4001/udp
sudo ufw allow 5001/tcp
sudo ufw allow 8080/tcp
```

If your VPS is behind NAT, use [libp2p NAT traversal](https://docs.ipfs.tech/install/libp2p-relays/) or [libp2p Relays](https://docs.ipfs.tech/concepts/how-ipfs-works/#relays) for transit connectivity.

### Q: What's the difference between IPFS and Filecoin?

IPFS is the **protocol layer** for file transfer and storage; Filecoin is the **incentive layer** built on top of IPFS. Simply put:
- IPFS lets you store and retrieve files
- Filecoin provides economic incentives for storage providers to keep your data long-term
- You can use IPFS independently; Filecoin is an optional enhancement

## Summary

Running an IPFS node on your VPS is a crucial step in the self-hosting ecosystem. It frees your data from dependency on a single server and makes you an active participant in the global decentralized storage network.

**Key takeaways:**
- ✅ Deploy IPFS node quickly with Docker
- ✅ Configure HTTP Gateway for browser access
- ✅ Learn to upload and retrieve files via CID
- ✅ Combine with pinning services for persistent storage
- ✅ Build censorship-resistant static websites

The decentralized future isn't on someone else's server — it's on yours.
