---
title: "本周自托管精选合集：N8N、开源AI工具与VPS省钱秘籍（2026年5月第2周）"
description: "一周自托管精选——N8N工作流自动化部署指南、LocalAI/Ollama等开源AI工具大盘点、VPS省钱终极对比，外加本周热门自托管项目推荐"
date: 2026-05-17T10:00:00+08:00
lastmod: 2026-05-17T10:00:00+08:00
slug: "weekly-roundup-may-week2"
tags: ["自托管", "每周精选", "N8N", "AI工具", "VPS省钱", "开源项目", "Docker", "Hetzner"]
categories: ["最佳合集"]
draft: false
---

## 📅 本周导读

欢迎来到 SelfVPS 指南的第一期「本周最佳合集」！本周我们发布了三篇深度教程，覆盖了自托管领域中 **最常见的三个痛点**：工作流自动化、开源AI部署和云服务省钱。本文将这些内容整理成一份精华合集，并补充本周社区中最热门的自托管项目推荐。

---

## 🥇 本周推荐工具 Top 5

### 1️⃣ N8N — 开源工作流自动化之王

**阅读完整教程**：[N8N 部署指南](/zh/post/n8n-deployment-guide/)

N8N 是本周最受关注的工具。它被称为"开源的 Zapier"，支持 **400+ 集成**，从 Slack、Gmail 到 GitHub、Discord 一应俱全。

**核心数据对比：**

| 方案 | 月费 | 用户限制 | 数据控制 |
|------|------|----------|----------|
| Zapier 免费版 | $0 | 100任务/月 | ❌ 云端 |
| Zapier 专业版 | $29.99 | 750任务/月 | ❌ 云端 |
| Make 免费版 | $0 | 1000操作/月 | ❌ 云端 |
| **N8N 自托管** | **$0** | **无限制** | ✅ **完全自控** |

**一句话总结**：如果你每个月的工作流任务超过 1000 个，自托管 N8N 在第一年就能为您节省 **$360 以上**。

### 2️⃣ LocalAI — 私有化 LLM 推理

**阅读完整教程**：[部署开源 AI 工具合集](/zh/post/deploying-open-source-ai-tools/)

LocalAI 是一个与 OpenAI API 完全兼容的开源替代品。部署后，您只需将代码中的 `api.openai.com` 替换为您自己的服务器地址即可。

```bash
# 一行命令启动 LocalAI
docker run -p 8080:8080 --name localai \
  -v $PWD/models:/build/models \
  localai/localai:latest
```

**为什么要用 LocalAI 而非 ChatGPT？**

| 对比项 | ChatGPT Plus | LocalAI 自托管 |
|--------|-------------|----------------|
| 月费 | $20/月 | VPS 成本 ~$8-15/月 |
| 数据隐私 | OpenAI 可查看 | 完全私密 |
| 速率限制 | 50条/3小时 | 无限制 |
| 模型选择 | 有限 | 任意开源模型 |

### 3️⃣ Ollama — 最简 LLM 运行方案

如果你觉得 LocalAI 配置太复杂，Ollama 是绝对的"开箱即用"之选：

```bash
# 安装 Ollama
curl -fsSL https://ollama.com/install.sh | sh

# 下载并运行 Mistral 7B
ollama run mistral
```

Ollama 在当前 VPS 生态中热度极高，GitHub Stars 已突破 **150K+**。它支持 100+ 模型，从 3B 到 70B 参数均可运行。

### 4️⃣ Uptime Kuma — 自托管监控面板

Uptime Kuma 是一个漂亮的、功能丰富的自托管监控工具，本周在社区中讨论度很高。

```yaml
# docker-compose.yml 一键部署
version: '3.8'
services:
  uptime-kuma:
    image: louislam/uptime-kuma:latest
    container_name: uptime-kuma
    restart: unless-stopped
    ports:
      - "3001:3001"
    volumes:
      - uptime_kuma_data:/app/data

volumes:
  uptime_kuma_data:
```

**与商业方案对比：**

| 功能 | Uptime Kuma (自托管) | Better Uptime | Pingdom |
|------|---------------------|---------------|---------|
| 价格 | 免费 | $24+/月 | $14.99+/月 |
| 监控数量 | 无限制 | 5个(免费版) | 10个(免费版) |
| 通知渠道 | 90+ | 20+ | 15+ |
| 状态页面 | ✅ | ✅ | ✅ |

### 5️⃣ Vaultwarden — 密码管理自托管

Bitwarden 的 Rust 实现，比官方版轻量 10 倍，仅需 256MB RAM 即可运行。

```bash
docker run -d --name vaultwarden \
  -v /vw-data/:/data/ \
  -p 80:80 \
  vaultwarden/server:latest
```

**节省计算：** 相比 Bitwarden 官方自托管版（需要 2GB+ RAM），Vaultwarden 的资源消耗仅为前者的 **1/10**。

---

## 💰 本周省钱攻略精华

### Hetzner — 2026 年性价比王者

从我们的 VPS 省钱攻略中节选关键数据：

| 服务商 | 2核/4GB 月费 | 4核/8GB 月费 | 按年优惠 |
|--------|-------------|-------------|---------|
| **Hetzner** | **€4.15** | **€8.85** | 无额外折扣（本身已最低） |
| DigitalOcean | $24 | $48 | 10-20% 年付优惠 |
| Vultr | $24 | $48 | 无 |
| 阿里云 (国内) | ¥68 | ¥128 | 1年8折 |

**年度成本差距惊人：**
- Hetzner 2核/4GB：€4.15 × 12 = **€49.80/年**
- DigitalOcean 同等规格：$24 × 12 = **$288/年**
- 差距：**5.8 倍**

### 云省钱三大原则

1. **选对服务商**：Hetzner 4核/8GB 仅 €8.85/月，运行 N8N + LocalAI + Ollama + Uptime Kuma 完全没问题
2. **用 Docker 整合**：一台 VPS 跑多个服务，最大化资源利用率
3. **按量付费 vs 预付费**：流量稳定的服务选固定套餐，波动大的选按量付费

---

## 🛠 本周运维小技巧

### 1. 用 Docker Compose 统一管理所有服务

```yaml
# 统一管理多个自托管服务
version: '3.8'
services:
  n8n:
    extends:
      file: ./n8n/docker-compose.yml
      service: n8n
  ollama:
    image: ollama/ollama:latest
    container_name: ollama
    restart: unless-stopped
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama
  uptime-kuma:
    extends:
      file: ./uptime-kuma/docker-compose.yml
      service: uptime-kuma

volumes:
  n8n_data:
  ollama_data:
  uptime_kuma_data:
```

### 2. 设置自动化备份

```bash
#!/bin/bash
# 每周自动备份所有 Docker 数据
BACKUP_DIR="/backups/$(date +%Y-%m-%d)"
mkdir -p $BACKUP_DIR

# 备份所有 Docker volumes
for volume in $(docker volume ls -q); do
  docker run --rm -v $volume:/data -v $BACKUP_DIR:/backup \
    alpine tar czf /backup/${volume}.tar.gz -C /data .
done

# 保留最近 30 天的备份
find /backups -type d -mtime +30 -exec rm -rf {} \;
```

### 3. 监控资源使用

```bash
# 查看所有容器的资源占用
docker stats --no-stream

# 安装 Netdata 一键监控
bash <(curl -Ss https://my-netdata.io/kickstart.sh)
```

---

## 🔮 下周预告

下周我们将带来更多精彩的教程：

| 日期 | 主题 |
|------|------|
| 周一 | **Affine 部署教程** — Notion 的开源替代品，知识库自托管 |
| 周二 | **CDN 省钱攻略** — Cloudflare + 自建 CDN 混合方案 |
| 周三 | **ComfyUI 部署指南** — Stable Diffusion 最强大的工作流工具 |
| 周四 | **Docker 安全加固** — 容器安全的 10 个最佳实践 |
| 周五 | **Spot 实例生存指南** — AWS/Azure 竞价实例省钱技巧 |
| 周六 | **自托管 vs SaaS 全面成本分析** |

---

## 💬 结语

自托管的世界精彩纷呈。本周我们看到了 N8N 可以替代 Zapier 节省 **95% 以上的成本**，LocalAI 和 Ollama 让私有 AI 触手可及，而最低仅 €4.15/月的 Hetzner VPS 就能跑起这一切。

**工具不在多，在于精**。一台 VPS + Docker + 合适的开源工具，就能构建出完全不输 SaaS 服务的基础设施。

如果您有任何建议或想要了解的自托管工具，欢迎在评论区留言！下周日再见 👋

---

*本文发布于 [SelfVPS 指南](https://selfvps.net)，转载请注明出处。*
