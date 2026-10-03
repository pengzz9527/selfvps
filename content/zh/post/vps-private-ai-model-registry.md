---
title: "VPS 私有镜像仓库实战：从 Docker Registry 到 GitLab 的 AI 模型分发方案"
description: "AI 模型体积大、更新快，官方镜像拉取又慢又贵？自建 VPS 私有镜像仓库：5 分钟搭好 Docker Registry，10 行脚本自动同步 NVIDIA Llama 3 官方镜像，让团队秒级拉取、成本归零"
date: 2026-10-03T20:00:00+08:00
lastmod: 2026-10-03T20:00:00+08:00
slug: "vps-private-container-registry"
image: /images/posts/vps-private-container-registry/featured.png
tags: ["Docker Registry", "VPS", "AI 模型分发", "私有仓库", "Llama 3", "CI/CD", "自托管", "成本优化"]
categories: ["AI + VPS"]
aliases: [/zh/post/vps-private-container-registry/]
---

## 引言

跑 AI 推理服务，你大概率遇到过这些场景：

- 团队要跑 Llama 3 8B，官方 `ghcr.io` / `nvidia/cuda` 镜像动辄 5~10GB，国内拉取慢到崩溃；
- 每次上游更新模型或基础镜像，团队成员各自手动 `docker pull`，版本不一致导致"在我机器上是好的"；
- 用 Harbor 太重（要 K8s、要 LDAP），用 GitLab Container Registry 又怕 GitLab 实例本身拖垮 VPS；
- 最朴素的 `docker push/pull` 公网 registry，要么被限流、要么收费、要么需要账号。

**问题本质：你需要一个"内网镜像分发中枢"，而不是又一个重型平台。**

本文的方案只依赖三样东西：

1. 一台 1~2 核 2GB 的 VPS（或闲置云主机）；
2. `docker registry:2`（官方轻量镜像，几百 MB）；
3. 一段 10 行的同步脚本。

效果：官方上游更新 → 自动同步到你的 VPS → 团队 `docker pull your-vps:5000/llama3` 秒级完成。带宽成本 ≈ 0（只在首次上传时走一次公网），内部拉取走内网，零额外费用。

---

## 架构设计

```
┌──────────────────────────────────────────────────────┐
│                 公网上游（按需拉取）                    │
│   ghcr.io / docker.io / quay.io（NVIDIA 官方镜像）    │
└──────────────────────┬───────────────────────────────┘
                       │  定时同步（cron / CI）
                       │  docker pull + retag + push
                       ▼
┌──────────────────────────────────────────────────────┐
│             VPS：私有 Docker Registry (:5000)          │
│   docker registry:2 + TLS 证书 + 内网带宽计费          │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐  │
│  │ llama3:8b   │  │ llama3:70b  │  │ cuda:12.4     │  │
│  │ (5.8 GB)    │  │ (41 GB, 分片)│  │ (3.2 GB)     │  │
│  └─────────────┘  └─────────────┘  └──────────────┘  │
└──────────────────────┬───────────────────────────────┘
                       │  内网 / VPN（Tailscale / WireGuard）
                       │  docker pull 走私有仓库
                       ▼
┌──────────────────────────────────────────────────────┐
│   团队开发机 / 推理服务器 / K8s 节点                    │
│   docker pull vps.internal:5000/llama3:8b            │
└──────────────────────────────────────────────────────┘
```

**关键决策**：不做"智能镜像同步"（Harbor 那种），而是**显式白名单 + 定期同步**。原因：

- 白名单模型可控：只有你审核过的镜像能进内网，避免供应链投毒；
- 同步频率 = 你的 CI 节奏，不浪费 VPS 带宽；
- 故障隔离：上游 registry 挂了，内网业务照常跑。

---

## 第一步：搭建 Registry

### 1.1 选机器

- **规格**：1 核 2GB 即可跑 registry 本身；但要预留磁盘——Llama 3 8B 镜像 5.8GB，70B 分片 41GB。建议 **100GB SSD 起步**，或把仓库放 S3 兼容存储（后文有说明）。
- **带宽**：重点看**内网/同区域流量免费额度**。若团队机器都在同一云区域，内网拉取零成本；跨可用区才计费。
- **TLS**：生产环境必须 HTTPS（registry 也支持 HTTP，仅限 Docker 20.10+ 的 `hosts` 配置场景，不推荐）。

### 1.2 一键部署

```bash
# 在 VPS 上执行
mkdir -p /data/registry/certs && cd /data/registry

# 自签证书（内网够用）；公网请换 Let's Encrypt
openssl req -newkey rsa:4096 -nodes \
  -keyout certs/registry.key \
  -x509 -days 3650 \
  -out certs/registry.crt \
  -subj "/CN=registry.your-vps.net"

docker run -d --name registry \
  --restart unless-stopped \
  -p 5000:5000 \
  -v /data/registry/registry-data:/var/lib/registry \
  -v /data/registry/certs:/certs:ro \
  -e REGISTRY_STORAGE_FILESYSTEM_ROOTDIR=/var/lib/registry \
  -e REGISTRY_HTTP_TLS_CERTIFICATE=/certs/registry.crt \
  -e REGISTRY_HTTP_TLS_KEY=/certs/registry.key \
  docker.io/library/registry:2
```

### 1.3 客户端配置

```bash
# 在每台拉取机器上（或用 /etc/hosts 映射内网 IP）
# 方式 A：hosts（最省事）
echo "10.0.1.5 registry.your-vps.net" | sudo tee -a /etc/hosts

# 方式 B：Docker 信任私有仓库（避免 "server certificate" 报错）
sudo tee /etc/docker/daemon.json <<EOF
{
  "insecure-registries": ["registry.your-vps.net:5000"]
}
EOF
sudo systemctl restart docker
```

> 若开了 TLS 证书，`insecure-registries` 可不加，但客户端需把自签 CA 放进系统信任链。

---

## 第二步：镜像同步脚本

这是整个方案的核心。一个 30 行的 bash 脚本，完成"上游拉取 → 打标签 → 推送内网"：

```bash
#!/usr/bin/env bash
# sync-registry.sh —— 在同步机（或 VPS 本机）执行
set -euo pipefail

UPSTREAM="ghcr.io/nvidia/llama3"      # 换成你的上游
PRIVATE="registry.your-vps.net:5000"
IMAGE="llama3"
VERSION="8b-instruct"

# 1. 拉上游（带 tag）
docker pull "${UPSTREAM}:${VERSION}"

# 2. 重打内网标签
docker tag  "${UPSTREAM}:${VERSION}"  "${PRIVATE}/${IMAGE}:${VERSION}"
# 可选：同时打一个 stable 标签，CI 里引用 stable 更稳
docker tag  "${UPSTREAM}:${VERSION}"  "${PRIVATE}/${IMAGE}:stable"

# 3. 推送
docker push "${PRIVATE}/${IMAGE}:${VERSION}"
docker push "${PRIVATE}/${IMAGE}:stable"

# 4. 清理上游缓存（保留内网）
docker rmi "${UPSTREAM}:${VERSION}" || true

echo "✓ ${PRIVATE}/${IMAGE}:${VERSION} 同步完成"
```

**调度方式**（三选一）：

| 方式 | 适用场景 | 配置 |
|------|---------|------|
| VPS 本机 cron | 镜像更新频率 ≤ 每周 | `0 3 * * 1 /opt/sync/sync-registry.sh >> /var/log/sync.log 2>&1` |
| GitLab CI / Gitea Actions | 与代码发版联动 | 触发器：tag 推送 或 每日定时 |
| Watch 模式 | 上游更新即时同步 | 配合 webhook，复杂度高 |

**白名单机制**（推荐放在脚本顶部）：

```bash
ALLOWED=(
  "ghcr.io/nvidia/llama3:8b-instruct"
  "ghcr.io/nvidia/llama3:8b-instruct-fp16"
  "docker.io/nvidia/cuda:12.4.1-cudnn8-ubuntu22.04"
)
for img in "${ALLOWED[@]}"; do sync_one "$img"; done
```

只有白名单内的镜像才能进内网，防止误推或投毒。

---

## 第三步：接入 CI/CD

团队发版时，**不要引用上游 registry**，统一指向你的 VPS：

```yaml
# .gitlab-ci.yml（Gitea Actions 同理）
stages: [sync, build, test, deploy]

sync:llama3:
  stage: sync
  only:
    - tags
  script:
    - docker login -u "$REGISTRY_USER" -p "$REGISTRY_PASS" registry.your-vps.net:5000
    - /opt/sync/sync-registry.sh   # 或直接在 CI 里跑上面那段

build:
  stage: build
  script:
    - docker build --pull
      -f Dockerfile.ai
      --build-arg MODEL="registry.your-vps.net:5000/llama3:stable"
      -t your-app:latest .
```

```dockerfile
# Dockerfile.ai —— 基于内网 Llama 镜像
ARG MODEL
FROM ${MODEL}

COPY app/ /opt/app
WORKDIR /opt/app
CMD ["python", "inference.py"]
```

**好处**：

- 构建耗时从"拉 5GB 上游镜像"变成"拉内网已缓存镜像"，**CI 提速 3~5 倍**；
- 上游 registry 限流/抽风不影响你的发版；
- `stable` 标签保证"今天发版用的模型"可复现。

---

## 第四步（可选）：冷存储归档

Llama 3 70B 这类大镜像放 VPS 本地 SSD 不现实（贵）。两个低成本的"冷备"方案：

### 方案 A：S3 兼容对象存储 + 按需回源

```bash
# 用 docker 官方 registry 的 S3 backend，大镜像自动落到 MinIO / 云 S3
docker run -d --name registry-s3 \
  -p 5000:5000 \
  -v /data/registry/certs:/certs:ro \
  -e REGISTRY_STORAGE_S3_BUCKET=my-registry \
  -e REGISTRY_STORAGE_S3_REGION=ap-southeast-1 \
  -e REGISTRY_STORAGE_S3_ACCESSKEY="$S3_KEY" \
  -e REGISTRY_STORAGE_S3_SECRETKEY="$S3_SECRET" \
  docker.io/library/registry:2
```

内网首次拉取会回源 S3（按流量计费），之后命中本地缓存。

### 方案 B：分层推送

```bash
# 小镜像（< 5GB）→ VPS 本地 SSD
docker push registry.your-vps.net:5000/llama3:8b-instruct

# 大镜像（> 10GB）→ 直接发 MinIO / 云 S3，给个 presigned URL 下载
aws s3 cp model-safetensors/ s3://ai-models/llama3-70b/ --region ap-southeast-1
echo "下载地址: $(aws s3 presign s3://ai-models/llama3-70b/ --region ap-southeast-1 --expires-in 3600)"
```

实践中 70B 级别用方案 B 更划算——S3 存储 $0.023/GB/月，比 VPS 加 100GB 数据盘便宜。

---

## 安全加固清单

私有 registry 是内网的信任锚点，务必检查：

- [ ] **TLS 证书**：生产必须 HTTPS，自签证书要下发到所有客户端信任链
- [ ] **Basic Auth**：`REGISTRY_AUTH_htt` 开启，至少区分读/写账号
- [ ] **白名单同步**：脚本里硬编码 `ALLOWED` 列表，**不要**让任何人都能 push 到内网
- [ ] **镜像签名**：用 `cosign` 对关键镜像做签名，CI 里校验
  ```bash
  cosign sign --key /keys/cosign.key registry.your-vps.net:5000/llama3:stable
  ```
- [ ] **漏洞扫描**：同步后跑一遍 `trivy image`
  ```bash
  trivy image --exit-code 0 registry.your-vps.net:5000/llama3:stable
  ```
- [ ] **访问审计**：registry 自带 access log，接到 Uptime Kuma / Loki 做告警
- [ ] **网络隔离**：registry 只对内网/VLAN 开放，公网 5000 端口**关闭**

---

## 性能与成本对比

| 方案 | 首次拉取耗时（团队 10 台机器） | 月成本 | 复杂度 |
|------|---------------------------|--------|--------|
| 公网 ghcr.io 直连 | 5~30 min/台（限流严重） | 0（免费额度内） | 低 |
| Harbor | 首次 10 min/台，后续秒级 | 实例 + 存储费用 | 高 |
| GitLab Registry | 依赖 GitLab 性能 | GitLab 全量成本 | 中 |
| **本文方案** | **首次 30s~2min/台，后续秒级** | **VPS 已含 + 流量** | **低** |

> 假设 10 台机器每天拉一次 5.8GB 镜像，内网带宽免费，**月成本 ≈ 0**。跨区域场景下，S3 存储 $0.5/月 + 流量 $1~3/月，依然远低于商业 registry。

---

## 故障排查

| 现象 | 原因 | 解决 |
|------|------|------|
| `x509: certificate signed by unknown authority` | 客户端没信任自签 CA | `sudo cp certs/registry.crt /usr/local/share/ca-certificates/ && update-ca-certificates` |
| `HEAD /v2/... 401` 但本地 docker 没登录 | 匿名拉取被禁 | 检查 `REGISTRY_AUTH` 配置，或临时放开 `REGISTRY_AUTH_DISABLE` |
| 同步脚本 `denied: requested access to the resource is not allowed` | push 账号无写权限 | 给 Basic Auth 用户加权限，或用 token 鉴权 |
| 大镜像 push 中途断 | VPS 内存不足（registry 默认流式写，但解压时会吃 RAM） | 加 swap，或设 `REGISTRY_STORAGE_FILESYSTEM_MAINTENANCE` |
| 内网拉取比公网还慢 | DNS 解析走了公网 DNS | 在拉取机器上把 registry 域名映射到内网 IP |

---

## 扩展方向

1. **多 region 镜像**：在两个 VPS 各跑一个 registry，用 `registry:2` 的 replication 功能（或自写 cron 双向同步），做到异地灾备；
2. **模型热更新**：在 registry 里维护 `model-weights` 仓库，推理服务启动时 `git pull` 权重文件 + `docker pull` 推理镜像，实现"模型即容器"的 A/B 发版；
3. **签名 + 准入**：CI 里用 `cosign verify` + 策略引擎（OPA Gatekeeper），只允许已签名的镜像在 K8s 里跑；
4. **带宽监控**：registry 暴露 `prometheus` 指标端点，接 Grafana 看拉取 QPS / 流量。

---

## 总结

自建 VPS 私有镜像仓库不是"再搭一个 Harbor"，而是**用最轻的方式解决最痛的问题**：AI 模型镜像又大、又贵、又慢。

三步走：

1. **10 分钟**：`docker registry:2` + TLS，内网可访问；
2. **30 行脚本**：白名单同步上游 Llama 3 / CUDA 镜像；
3. **改一行 CI**：所有 `docker build` 指向内网 registry，CI 提速 3~5 倍。

总成本 ≈ 0（VPS 你本来就有的），收益是**确定性**：团队发版不再受上游 registry 限流影响，模型版本可复现，内网拉取秒级完成。

**私有 registry 不是大公司的奢侈品，是自运维 AI 团队的刚需基建。** 先从 10 行同步脚本跑起来，再按需升级到 S3 冷备。
