---
title: "IPFS 去中心化存储：在 VPS 上搭建永久文件网络，告别服务器磁盘焦虑"
description: "从零开始部署 IPFS 节点，构建抗审查、可持久化的去中心化文件存储网络。本文涵盖安装配置、pinning 服务、Web 发布与内容寻址原理。"
date: 2026-07-05T10:00:00+08:00
lastmod: 2026-07-05T10:00:00+08:00
slug: "ipfs-decentralized-storage-vps-guide"
tags: ["IPFS", "去中心化存储", "VPS部署", "自托管", "文件共享", "Web3", "分布式系统", "pinning"]
categories: ["部署教程"]
draft: false
image: /images/posts/ipfs-decentralized-storage-vps-guide/featured.png
aliases: [/zh/post/ipfs-decentralized-storage-vps-guide/]
---

## 什么是 IPFS？

IPFS（InterPlanetary File System，星际文件系统）是一个去中心化的点对点文件存储和传输协议。与传统 HTTP 不同，IPFS 通过**内容寻址**而非位置寻址来定位文件——你不再需要记住服务器地址，而是通过文件的哈希值来获取它。

这意味着：
- 文件一旦被发布到 IPFS 网络，就**永久存在**（只要有人 pin 住它）
- 没有单点故障，抗审查
- 同一个文件在全球多个节点间分发，访问速度更快

## 为什么要在 VPS 上运行 IPFS 节点？

大多数个人开发者只使用 IPFS 作为消费者（通过 IPFS Desktop 或 Pinata 等服务）。但如果你想在自托管生态中真正发挥去中心化存储的价值，运行一个自己的 IPFS 节点是最佳选择：

| 优势 | 说明 |
|------|------|
| **完全掌控** | 数据不依赖第三方服务商，你的 VPS 就是网络的一部分 |
| **低成本** | 一台 $5/月的 VPS 即可运行生产级 IPFS 节点 |
| **持久化存储** | 配合 IPFS-Pinning 服务，确保关键文件长期在线 |
| **内容审核抵抗** | 没有中心机构可以删除你的文件 |
| **开发调试** | 本地节点方便测试 dApp、NFT 元数据、静态站点部署 |

## 环境要求

- Ubuntu 22.04/24.04 VPS（推荐 2C4G 及以上）
- 至少 50GB SSD 存储空间（IPFS 仓库会持续增长）
- 公网 IP 或 Cloudflare Tunnel 暴露
- Docker 已安装

> **注意：** IPFS 节点的存储消耗取决于你 pin 了多少内容。如果只是运行一个基础节点而不主动 pin 大量数据，10-20GB 也可以起步。

## 第一步：部署 IPFS 节点

使用 Docker 是最简单的方式：

```bash
# 创建持久化存储目录
mkdir -p ~/ipfs/data ~/ipfs/config

# 启动 IPFS 节点
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

参数说明：
- `4001`: libp2p 通信端口（节点间交换数据）
- `5001`: API 端口（本地管理接口）
- `8080`: HTTP Gateway（通过浏览器访问 IPFS 内容）

启动后验证：

```bash
docker exec ipfs-node ipfs id
```

你应该看到类似这样的输出：

```json
{
  "ID": "12D3Koo...",
  "Addresses": [...],
  "AgentVersion": "kubo/0.30.0/",
  "ProtocolVersion": "ipfs/0.1.0"
}
```

## 第二步：配置与优化

### 调整存储策略

IPFS 默认会自动删除不常用的内容（ARC 策略）。如果你想让节点成为有效的 pinning 节点，需要调整配置：

```bash
# 禁用自动垃圾回收
docker exec ipfs-node ipfs config Republisher.RepublishPeriod 24h
docker exec ipfs-node ipfs config Datastore.GCThreshold 100GiB

# 重启节点使配置生效
docker restart ipfs-node
```

### 添加 Bootstrap 节点

确保节点能发现网络中的其他对等体：

```bash
docker exec ipfs-node ipfs bootstrap add /dnsaddr/bootstrap.libp2p.io/p/quic-v1
docker exec ipfs-node ipfs bootstrap add /dnsaddr/bootstrap.libp2p.io/p/tcp
```

### 配置 HTTP Gateway

启用网关后可以方便地通过浏览器访问 IPFS 内容：

```bash
# 启用公共网关（谨慎使用，可能暴露你的节点）
docker exec ipfs-node ipfs config Gateway.HTTPHeaders.Access-Control-Allow-Origin '["*"]'
docker exec ipfs-node ipfs config Gateway.PublicPath /ipfs
docker exec ipfs-node ipfs config Gateway.IPCIDPath /ipfs/raw
```

## 第三步：上传与获取文件

### 上传文件

```bash
# 上传单个文件
docker exec -i ipfs-node ipfs add < myfile.txt

# 上传整个目录
docker exec -i ipfs-node ipfs add -r ./my-folder/

# 输出示例：
# added QmXoypizjy4WQi5dEexbG1fovVJXYqUVhBNkfKapFcRZKw myfile.txt
```

返回的 `QmXo...` 就是文件的 CID（Content Identifier），你可以用它来引用该文件。

### 通过 CID 获取文件

```bash
# 通过 CID 下载文件
docker exec ipfs-node ipfs get QmXoypizjy4WQi5dEexbG1fovVJXYqUVhBNkfKapFcRZKw

# 通过 HTTP Gateway 访问（浏览器也能用）
curl http://localhost:8080/ipfs/QmXoypizjy4WQi5dEexbG1fovVJXYqUVhBNkfKapFcRZKw
```

### 持久化 Pin（固定内容）

确保你的文件在网络中长期存在：

```bash
# 固定某个 CID
docker exec ipfs-node ipfs pin add QmXoypizjy4WQi5dEexbG1fovVJXYqUVhBNkfKapFcRZKw

# 查看已固定的内容
docker exec ipfs-node ipfs pin ls

# 取消固定
docker exec ipfs-node ipfs pin rm QmXoypizjy4WQi5dEexbG1fovVJXYqUVhBNkfKapFcRZKw
```

## 第四步：搭建 Web 发布站点

IPFS 非常适合托管静态网站。以下是一个完整的部署流程：

### 方法一：直接上传 HTML

```bash
# 创建示例网站
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

# 上传并获取 CID
cd ~/my-site
CID=$(docker exec -i ipfs-node ipfs add -r --cid-version 1 . | tail -1 | awk '{print $NF}')
echo "Site CID: $CID"
echo "访问: https://gateway.ipfs.io/ipfs/$CID"
```

### 方法二：使用 Nginx + IPFS Gateway 组合

将 Nginx 作为反向代理，优先从本地 IPFS 节点获取内容：

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
        # 仅允许本地访问 API
        allow 127.0.0.1;
        deny all;
    }
}
```

## 进阶：付费 Pinning 服务

如果你的 VPS 磁盘有限，或者想要更高可用性，可以使用付费 pinning 服务作为补充：

| 服务 | 免费额度 | 特点 |
|------|----------|------|
| [Pinata](https://pinata.cloud) | 1GB | 最流行的 IPFS pinning 服务，API 完善 |
| [Infura](https://infura.io) | 免费 | Ethereum 生态集成好 |
| [web3.storage](https://web3.storage) | 1TB | Protocol Labs 出品，开发者友好 |
| [Crust Network](https://crust.network) | 免费 | 基于 Polkadot 的去中心化 pinning |

搭配使用方式：

```bash
# 通过 Pinata API 上传
curl -X POST "https://api.pinata.cloud/pinning/pinFileToIPFS" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -F "file=@myfile.pdf"

# 返回 pinned_hash，在你的 IPFS 节点上 pin 它
docker exec ipfs-node ipfs pin add /ipfs/QmYourHashHere
```

## 常见问题

### Q: IPFS 节点占用太多磁盘怎么办？

定期清理未 pin 的内容：

```bash
# 手动触发垃圾回收
docker exec ipfs-node ipfs repo gc

# 查看存储使用情况
docker exec ipfs-node ipfs repo stat
```

建议设置 `repo.stat` 监控，当使用量超过阈值时告警。

### Q: 如何让节点对外可见？

IPFS 节点需要与其他节点建立连接。确保防火墙放行：

```bash
# 放行 libp2p 端口
sudo ufw allow 4001/tcp
sudo ufw allow 4001/udp
sudo ufw allow 5001/tcp
sudo ufw allow 8080/tcp
```

如果 VPS 在内网后面，可以使用 [libp2p 的 NAT 穿透](https://docs.ipfs.tech/install/libp2p-relays/) 或通过 [libp2p Relay](https://docs.ipfs.tech/concepts/how-ipfs-works/#relays) 中转。

### Q: IPFS 和 Filecoin 是什么关系？

IPFS 是文件传输和存储的**协议层**，Filecoin 是在 IPFS 之上构建的**激励层**。简单来说：
- IPFS 让你能存储和检索文件
- Filecoin 提供经济激励，让存储提供商愿意长期保存你的数据
- 你可以单独使用 IPFS，Filecoin 是可选的增强层

## 总结

在 VPS 上部署 IPFS 节点是自托管生态中至关重要的一步。它不仅让你的数据摆脱了对单一服务器的依赖，还让你成为了全球去中心化存储网络的一部分。

**核心要点回顾：**
- ✅ 使用 Docker 快速部署 IPFS 节点
- ✅ 配置 HTTP Gateway 便于浏览器访问
- ✅ 学会通过 CID 上传和获取文件
- ✅ 结合 Pinning 服务实现持久化存储
- ✅ 搭建抗审查的静态网站

去中心化的未来不在别人的服务器上——就在你自己的 VPS 里。
