---
title: "在 VPS 上部署 Open WebUI + Ollama：搭建你的私人 ChatGPT"
description: "完整教程：用 Docker 在 VPS 上一键部署 Open WebUI + Ollama 组合，搭建完全私有的 AI 对话平台。支持离线运行、多模型切换、RAG 知识库，彻底告别 ChatGPT 订阅。"
date: 2026-05-21T21:30:00+08:00
slug: "open-webui-ollama-vps-deployment"
tags: ["Open WebUI", "Ollama", "AI", "Docker", "VPS部署", "大语言模型", "ChatGPT替代", "自托管", "RAG"]
categories: ["AI部署"]
aliases: [/zh/post/open-webui-ollama-vps-deployment/]
draft: false
image: /images/posts/open-webui-ollama-vps-deployment/featured.png
---

## 为什么选择 Open WebUI + Ollama？

如果你想运行自己的 AI 助手，又不想每月支付 ChatGPT Plus 订阅费，**Open WebUI + Ollama** 是目前最成熟的自托管方案。这套组合让你在 VPS 上拥有：

- **完全私有** — 数据不离开你的服务器，无需担心隐私泄露
- **零订阅成本** — 只需支付 VPS 费用，无 API 调用费
- **离线可用** — 不需要互联网连接即可使用
- **多模型支持** — 同时运行 Llama、Qwen、DeepSeek、Mistral、Gemma 等模型
- **类 ChatGPT 体验** — 与 OpenAI 接口完全兼容的 Web 界面
- **RAG 知识库** — 上传文档让 AI 基于你的数据回答问题
- **多用户支持** — 团队成员共享同一台服务器

## 前置条件

在开始之前，确保你拥有：

- **一台 VPS**（推荐配置：4 核 CPU、8 GB RAM、50 GB SSD）
- **Docker 和 Docker Compose**（已安装）
- **域名**（可选，用于配置 HTTPS）
- **基本 Linux 操作知识**

### 推荐 VPS 规格

| 模型大小 | 推荐内存 | 所需磁盘 | 适用场景 |
|---------|---------|---------|---------|
| 1B-3B 参数 | 4 GB | 10 GB | 轻量对话、翻译、摘要 |
| 7B-8B 参数 | 8 GB | 20 GB | 通用问答、代码辅助 |
| 14B-20B 参数 | 16 GB | 40 GB | 复杂推理、专业写作 |
| 70B+ 参数 | 32 GB+ | 80 GB+ | 高级推理、多语言 |

> **提示**：对于大多数场景，8 GB 内存的 VPS 运行 7B 模型（如 Qwen2.5-7B、Llama-3.1-8B）已经能提供非常出色的效果。

## 第一步：安装 Docker 和 Docker Compose

如果尚未安装，执行以下命令：

```bash
# 更新系统
apt update && apt upgrade -y

# 安装 Docker
curl -fsSL https://get.docker.com | bash

# 验证安装
docker --version
docker compose version
```

## 第二步：创建 Docker Compose 配置

创建一个项目目录和配置文件：

```bash
mkdir -p ~/open-webui && cd ~/open-webui
nano docker-compose.yml
```

写入以下内容：

```yaml
version: "3.8"

services:
  ollama:
    image: ollama/ollama:latest
    container_name: ollama
    volumes:
      - ./ollama_data:/root/.ollama
    ports:
      - "11434:11434"
    restart: unless-stopped
    networks:
      - ai-net
    environment:
      - OLLAMA_KEEP_ALIVE=24h
      - OLLAMA_NUM_PARALLEL=1
      - OLLAMA_MAX_LOADED_MODELS=1

  open-webui:
    image: ghcr.io/open-webui/open-webui:main
    container_name: open-webui
    depends_on:
      - ollama
    volumes:
      - ./webui_data:/app/backend/data
    ports:
      - "3000:8080"
    restart: unless-stopped
    networks:
      - ai-net
    environment:
      - OLLAMA_BASE_URL=http://ollama:11434
      - WEBUI_SECRET_KEY=请替换为随机生成的密钥
      - WEBUI_NAME=My AI Chat
    extra_hosts:
      - "host.docker.internal:host-gateway"

networks:
  ai-net:
    driver: bridge
```

> **安全提示**：用 `openssl rand -base64 32` 生成一个随机密钥替换 `WEBUI_SECRET_KEY`。

## 第三步：启动服务

```bash
docker compose up -d
```

检查服务状态：

```bash
docker compose ps
docker compose logs -f
```

看到如下日志说明启动成功：

```
open-webui  | INFO:     Application startup complete.
ollama      | 2026/05/21 10:30:00 server.go:89: Listening on 0.0.0.0:11434
```

## 第四步：下载 AI 模型

现在来下载并运行你的第一个模型：

```bash
# 拉取模型（以 Qwen2.5-7B 为例，中文能力出色）
docker exec ollama ollama pull qwen2.5:7b

# 其他推荐模型
# docker exec ollama ollama pull llama3.1:8b    # 英文最佳
# docker exec ollama ollama pull deepseek-r1:8b  # 推理能力强
# docker exec ollama ollama pull gemma2:9b       # Google 出品

# 下载完成后测试一下
docker exec ollama ollama run qwen2.5:7b "你好，请介绍一下你自己"
```

模型下载时间取决于 VPS 网速，7B 模型大约需要 4-5 GB 空间，下载可能需要 5-20 分钟。

### 查看已下载的模型

```bash
docker exec ollama ollama list
```

## 第五步：访问 Open WebUI

### 通过 IP 访问

如果你的 VPS 防火墙开放了 `3000` 端口，直接在浏览器访问：

```
http://你的VPS_IP:3000
```

### 配置 Nginx 反向代理 + HTTPS（推荐）

创建一个 Nginx 配置：

```bash
sudo nano /etc/nginx/sites-available/open-webui
```

```nginx
server {
    listen 80;
    server_name chat.你的域名.com;

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400s;
        proxy_send_timeout 86400s;
    }
}
```

启用站点并申请 SSL 证书：

```bash
sudo ln -s /etc/nginx/sites-available/open-webui /etc/nginx/sites-enabled/
sudo certbot --nginx -d chat.你的域名.com
sudo nginx -t && sudo systemctl reload nginx
```

## 进阶配置

### 1. 配置 RAG 知识库

Open WebUI 内置了 RAG（检索增强生成）功能，可以让 AI 读取你的文档：

1. 点击对话输入框左侧的 **"+"** 按钮
2. 上传 PDF、TXT、Markdown 等文档
3. AI 会自动索引文档内容
4. 后续对话中 AI 会基于文档内容回答

### 2. 多模型同时运行

修改 `docker-compose.yml` 中的环境变量：

```yaml
environment:
  - OLLAMA_KEEP_ALIVE=-1    # 模型常驻内存
  - OLLAMA_NUM_PARALLEL=4   # 允许并行请求
  - OLLAMA_MAX_LOADED_MODELS=3  # 最多加载3个模型
```

### 3. 配置 GPU 加速

如果 VPS 有 GPU（如 NVIDIA 的云 GPU 实例），添加以下配置：

```yaml
services:
  ollama:
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
```

### 4. 集成云端模型

Open WebUI 也支持调用云端 API。在 Web 界面中设置：

- **OpenAI API** — 直接填入 API Key 即可使用 GPT-4
- **Google Gemini** — 配置 Gemini API Key
- **Anthropic Claude** — 配置 Claude API Key
- **自定义端点** — 支持任意 OpenAI 兼容 API

### 5. 开启联网搜索

在 Open WebUI 的"管理面板 → 设置 → 联网搜索"中启用搜索引擎，AI 就能实时获取最新信息。

## 性能优化建议

### 内存优化

```bash
# 设置 swap 空间（内存不足时的保底方案）
fallocate -l 8G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab

# 调整 swappiness（默认 60，降低以减少 swap 使用）
sysctl vm.swappiness=10
echo 'vm.swappiness=10' >> /etc/sysctl.conf
```

### 模型量化选择

同一模型的不同量化版本对性能影响巨大：

| 量化 | 精度 | 内存需求 | 质量 |
|-----|------|---------|------|
| Q4_K_M | 4-bit | 约 5 GB（7B） | 推荐平衡 |
| Q5_K_M | 5-bit | 约 6 GB（7B） | 更高精度 |
| Q8_0 | 8-bit | 约 8 GB（7B） | 接近无损 |
| fp16 | 16-bit | 约 16 GB（7B） | 原始精度 |

推荐在 8 GB VPS 上使用 `qwen2.5:7b`（默认 Q4_K_M）或 `qwen2.5:7b-q5_k_m`。

## 常见问题

### Q: 模型回答速度很慢怎么办？
**A:** 7B 模型在 CPU 上约每秒生成 5-15 tokens，属于正常范围。要提升速度可：① 使用更小的模型（如 1.5B/3B）；② 升级 VPS 到更高性能 CPU；③ 配置 GPU 加速。

### Q: 容器重启后对话记录会丢失吗？
**A:** 不会。`webui_data` 和 `ollama_data` 卷持久化保存在宿主机上，容器重启不会丢失数据。

### Q: 如何升级 Open WebUI？
**A:** 只需重新拉取镜像并重启：
```bash
docker compose pull
docker compose up -d --force-recreate
```

### Q: 内存不足导致 Ollama 崩溃？
**A:** 限制模型使用的 CPU 线程数：
```bash
docker exec ollama ollama run qwen2.5:7b --num-thread 4
```
或在 Ollama 配置中设置 `OLLAMA_NUM_THREADS=4`。

## 总结

通过 Open WebUI + Ollama 的组合，你可以在任何 VPS 上搭建一个功能完整的私有 AI 对话平台。它不仅完全免费、保护隐私，还支持多模型切换、RAG 知识库和联网搜索等高级功能。

这套方案尤其适合：

- **开发者** — 代码辅助、技术问答、本地文档搜索
- **中小团队** — 共享 AI 助理，节省 API 费用
- **隐私敏感用户** — 医疗、法律、金融等数据不出服务器
- **离线环境** — 内部网络中的 AI 能力部署

今天就动手试试吧！选择一台合适的 VPS，几分钟就能拥有属于自己的私人 AI 助手。
