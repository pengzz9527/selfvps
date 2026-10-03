---
title: "Private AI Model Registry on VPS: From Docker Registry to GitLab — a Zero-Cost Distribution Pipeline"
description: "AI model images are huge, upstream pulls are slow and expensive. Build a private Docker Registry on a VPS in 5 minutes, auto-sync official Llama 3 images with a 10-line script, and let your team pull in seconds at near-zero cost"
date: 2026-10-03T20:00:00+08:00
lastmod: 2026-10-03T20:00:00+08:00
slug: "vps-private-ai-model-registry"
image: /images/posts/vps-private-ai-model-registry/featured.png
tags: ["Docker Registry", "VPS", "AI model distribution", "private registry", "Llama 3", "CI/CD", "self-hosted", "cost optimization"]
categories: ["AI + VPS"]
aliases: [/en/post/vps-private-ai-model-registry/]
---

## Introduction

If you run AI inference workloads, you've likely hit these walls:

- The team needs Llama 3 8B; official `ghcr.io` / `nvidia/cuda` images are 5–10GB each, and pulling from within China crawls or times out;
- Every time the upstream model or base image updates, everyone on the team manually `docker pull`s — version drift ensues;
- Harbor is too heavy (K8s, LDAP), GitLab Container Registry risks dragging down a single VPS;
- Plain public registries get you rate-limited, charged, or asked for accounts.

**The real problem: you need an "internal distribution hub," not another heavyweight platform.**

This article's solution depends on only three things:

1. A 1–2 core / 2GB VPS (or an idle cloud instance);
2. `docker registry:2` (the official lightweight image, a few hundred MB);
3. A 10-line sync script.

Result: upstream updates → auto-sync to your VPS → the team runs `docker pull your-vps:5000/llama3` in seconds. Bandwidth cost ≈ 0 (public traffic only on first upload), internal pulls go over the private network, zero extra fees.

---

## Architecture

```
┌──────────────────────────────────────────────────────┐
│              Public upstream (pull on demand)         │
│   ghcr.io / docker.io / quay.io (NVIDIA official)    │
└──────────────────────┬───────────────────────────────┘
                       │  scheduled sync (cron / CI)
                       │  docker pull + retag + push
                       ▼
┌──────────────────────────────────────────────────────┐
│         VPS: Private Docker Registry (:5000)         │
│   docker registry:2 + TLS cert + private-network    │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐ │
│  │ llama3:8b   │  │ llama3:70b  │  │ cuda:12.4     │ │
│  │ (5.8 GB)    │  │ (41 GB, shard)│ │ (3.2 GB)     │ │
│  └─────────────┘  └─────────────┘  └──────────────┘ │
└──────────────────────┬───────────────────────────────┘
                       │  LAN / VPN (Tailscale / WireGuard)
                       │  docker pull from the private repo
                       ▼
┌──────────────────────────────────────────────────────┐
│   Dev machines / inference servers / K8s nodes        │
│   docker pull vps.internal:5000/llama3:8b            │
└──────────────────────────────────────────────────────┘
```

**Key decision**: no "smart registry replication" (the Harbor way) — instead, an **explicit allow-list + periodic sync**. Why:

- Allow-list keeps the model set auditable: only reviewed images enter the intranet, blocking supply-chain attacks;
- Sync frequency = your CI cadence, so no wasted VPS bandwidth;
- Fault isolation: if the upstream registry is down, internal workloads keep running.

---

## Step 1: Spin Up the Registry

### 1.1 Picking the machine

- **Spec**: 1 core / 2GB runs the registry itself; but leave headroom for storage — Llama 3 8B is 5.8GB, the 70B sharded build is 41GB. Start with **100GB SSD**, or back the repo on S3-compatible storage (see later).
- **Bandwidth**: check the **free-tier allowance for intra-region traffic**. If the team's machines are in the same cloud region, internal pulls are free; cross-availability-zone traffic is billed.
- **TLS**: production must be HTTPS (registry also supports HTTP, but only in the Docker 20.10+ `hosts`-config scenario — not recommended).

### 1.2 One-shot deploy

```bash
# Run on the VPS
mkdir -p /data/registry/certs && cd /data/registry

# Self-signed cert (fine for intranet); use Let's Encrypt for public
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

### 1.3 Client config

```bash
# On every pulling machine (or map an intranet IP via /etc/hosts)
# Option A: hosts (simplest)
echo "10.0.1.5 registry.your-vps.net" | sudo tee -a /etc/hosts

# Option B: make Docker trust the private registry (avoids "server certificate" errors)
sudo tee /etc/docker/daemon.json <<EOF
{
  "insecure-registries": ["registry.your-vps.net:5000"]
}
EOF
sudo systemctl restart docker
```

> If you enable TLS, you can skip `insecure-registries` — but the client must trust your self-signed CA.

---

## Step 2: The Sync Script

This is the heart of the whole setup. A 30-line bash script that does "pull upstream → retag → push internal":

```bash
#!/usr/bin/env bash
# sync-registry.sh — run on the sync box (or the VPS itself)
set -euo pipefail

UPSTREAM="ghcr.io/nvidia/llama3"      # swap in your upstream
PRIVATE="registry.your-vps.net:5000"
IMAGE="llama3"
VERSION="8b-instruct"

# 1. Pull upstream (tagged)
docker pull "${UPSTREAM}:${VERSION}"

# 2. Retag for the intranet
docker tag  "${UPSTREAM}:${VERSION}"  "${PRIVATE}/${IMAGE}:${VERSION}"
# Optional: also tag a stable alias so CI can pin to stable
docker tag  "${UPSTREAM}:${VERSION}"  "${PRIVATE}/${IMAGE}:stable"

# 3. Push
docker push "${PRIVATE}/${IMAGE}:${VERSION}"
docker push "${PRIVATE}/${IMAGE}:stable"

# 4. Clean the upstream cache (keep the internal copy)
docker rmi "${UPSTREAM}:${VERSION}" || true

echo "✓ ${PRIVATE}/${IMAGE}:${VERSION} synced"
```

**Scheduling** (pick one):

| Method | When to use | Config |
|--------|-------------|--------|
| VPS-local cron | Upstream updates ≤ weekly | `0 3 * * 1 /opt/sync/sync-registry.sh >> /var/log/sync.log 2>&1` |
| GitLab CI / Gitea Actions | Tied to release cadence | Trigger: tag push or daily schedule |
| Watch mode | Instant upstream sync | Webhook-driven, high complexity |

**Allow-list mechanism** (recommended, at the top of the script):

```bash
ALLOWED=(
  "ghcr.io/nvidia/llama3:8b-instruct"
  "ghcr.io/nvidia/llama3:8b-instruct-fp16"
  "docker.io/nvidia/cuda:12.4.1-cudnn8-ubuntu22.04"
)
for img in "${ALLOWED[@]}"; do sync_one "$img"; done
```

Only allow-listed images can enter the intranet — no accidental pushes, no supply-chain attacks.

---

## Step 3: Wire Into CI/CD

When the team ships, **never reference the upstream registry** — point everything at your VPS:

```yaml
# .gitlab-ci.yml (Gitea Actions is analogous)
stages: [sync, build, test, deploy]

sync:llama3:
  stage: sync
  only:
    - tags
  script:
    - docker login -u "$REGISTRY_USER" -p "$REGISTRY_PASS" registry.your-vps.net:5000
    - /opt/sync/sync-registry.sh   # or inline the steps above

build:
  stage: build
  script:
    - docker build --pull
      -f Dockerfile.ai
      --build-arg MODEL="registry.your-vps.net:5000/llama3:stable"
      -t your-app:latest .
```

```dockerfile
# Dockerfile.ai — build against the intranet Llama image
ARG MODEL
FROM ${MODEL}

COPY app/ /opt/app
WORKDIR /opt/app
CMD ["python", "inference.py"]
```

**Benefits**:

- Build time goes from "pull a 5GB upstream image" to "pull a cached intranet image" — **CI is 3–5× faster**;
- Upstream registry rate limits or outages no longer block your releases;
- The `stable` tag guarantees reproducibility: "the model that shipped today" is pinned.

---

## Step 4 (optional): Cold-Storage Archiving

Llama 3 70B-class images don't belong on a VPS's local SSD (too pricey). Two low-cost "cold" options:

### Option A: S3-compatible object storage + on-demand backsource

```bash
# Use the registry's S3 backend so big images land in MinIO / cloud S3
docker run -d --name registry-s3 \
  -p 5000:5000 \
  -v /data/registry/certs:/certs:ro \
  -e REGISTRY_STORAGE_S3_BUCKET=my-registry \
  -e REGISTRY_STORAGE_S3_REGION=ap-southeast-1 \
  -e REGISTRY_STORAGE_S3_ACCESSKEY="$S3_KEY" \
  -e REGISTRY_STORAGE_S3_SECRETKEY=*** \
  docker.io/library/registry:2
```

First internal pull backsources from S3 (pay per byte); subsequent pulls hit the local cache.

### Option B: Tiered push

```bash
# Small images (< 5GB) → VPS local SSD
docker push registry.your-vps.net:5000/llama3:8b-instruct

# Big images (> 10GB) → push straight to MinIO / cloud S3, share a presigned URL
aws s3 cp model-safetensors/ s3://ai-models/llama3-70b/ --region ap-southeast-1
echo "Download: $(aws s3 presign s3://ai-models/llama3-70b/ --region ap-southeast-1 --expires-in 3600)"
```

In practice, 70B-class workloads use Option B — S3 storage is $0.023/GB/month, far cheaper than adding 100GB of VPS data disk.

---

## Security Hardening Checklist

A private registry is your intranet's trust anchor. Verify:

- [ ] **TLS certs**: production must be HTTPS; distribute self-signed CAs to all clients
- [ ] **Basic Auth**: enable `REGISTRY_AUTH` with at least separate read/write accounts
- [ ] **Allow-list sync**: hardcode the `ALLOWED` list in the script; **nobody** gets push access to the intranet
- [ ] **Image signing**: sign critical images with `cosign`; verify in CI
  ```bash
  cosign sign --key /keys/cosign.key registry.your-vps.net:5000/llama3:stable
  ```
- [ ] **Vuln scanning**: run `trivy image` after each sync
  ```bash
  trivy image --exit-code 0 registry.your-vps.net:5000/llama3:stable
  ```
- [ ] **Access audit**: feed registry access logs to Uptime Kuma / Loki for alerts
- [ ] **Network isolation**: expose the registry only on the private network / VLAN; **close port 5000 to the public internet**

---

## Performance & Cost Comparison

| Approach | First-pull latency (10 team machines) | Monthly cost | Complexity |
|----------|---------------------------------------|--------------|------------|
| Public ghcr.io direct | 5–30 min/machine (severe rate limits) | 0 (free tier) | Low |
| Harbor | 10 min/machine first time, then seconds | Instance + storage | High |
| GitLab Registry | Depends on GitLab sizing | Full GitLab stack | Medium |
| **This article's setup** | **30s–2min/machine first time, then seconds** | **VPS included + traffic** | **Low** |

> Assume 10 machines pull a 5.8GB image daily over free intranet bandwidth: **monthly cost ≈ 0**. In a cross-region scenario, S3 storage is $0.5/mo + $1–3/mo traffic — still far cheaper than a commercial registry.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `x509: certificate signed by unknown authority` | Client doesn't trust the self-signed CA | `sudo cp certs/registry.crt /usr/local/share/ca-certificates/ && update-ca-certificates` |
| `HEAD /v2/... 401` on a machine that hasn't logged in | Anonymous pull is disabled | Check `REGISTRY_AUTH` config; temporarily set `REGISTRY_AUTH_DISABLE` |
| Sync script hits `denied: requested access to the resource is not allowed` | Push account lacks write | Grant Basic Auth user write access, or use token auth |
| Large-image push drops mid-transfer | VPS out of RAM (registry streams, but extraction eats memory) | Add swap, or tune `REGISTRY_STORAGE_FILESYSTEM_MAINTENANCE` |
| Intranet pull slower than public | DNS resolves through a public resolver | Map the registry domain to the intranet IP on the pulling machine |

---

## Where to Take It Next

1. **Multi-region replication**: run a registry on two VPSes, use `registry:2` replication (or a hand-rolled bidirectional cron) for DR;
2. **Hot model updates**: keep a `model-weights` repo; at startup the inference service `git pull`s weights and `docker pull`s the runtime image — "the model as a container" for A/B rollouts;
3. **Sign + admission**: in CI, `cosign verify` + an OPA Gatekeeper policy so only signed images run in K8s;
4. **Bandwidth monitoring**: the registry exposes a Prometheus endpoint — wire it into Grafana to track pull QPS and traffic.

---

## Summary

A private VPS registry isn't "yet another Harbor" — it's the **lightest way to solve the most painful problem**: AI model images that are big, expensive, and slow to pull.

Three steps:

1. **10 minutes**: `docker registry:2` + TLS, reachable on the intranet;
2. **A 30-line script**: allow-list sync of upstream Llama 3 / CUDA images;
3. **One line in CI**: every `docker build` points at the intranet registry — CI gets 3–5× faster.

Total cost ≈ 0 (you already own the VPS); the payoff is **certainty**: team releases no longer depend on upstream registry rate limits, model versions are reproducible, and internal pulls finish in seconds.

**A private registry is not a luxury for big companies — it's baseline infrastructure for teams that self-host AI.** Start with the 10-line sync script; graduate to S3 cold storage when you need it.
