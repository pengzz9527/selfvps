---
title: "在 VPS 上部署 Khoj：搭建你的 AI 第二大脑"
description: "手把手教程：在 VPS 上用 Docker 自托管 Khoj —— 开源 AI 第二大脑。连接本地 Ollama 运行大模型，开启联网搜索，创建自定义 AI 智能体。"
date: 2026-05-19T12:00:00+08:00
slug: "deploy-khoj-ai-second-brain-vps"
tags: ["Khoj", "AI", "自托管", "Ollama", "RAG", "Docker", "VPS部署", "AI智能体", "开源"]
categories: ["AI部署"]
aliases: [/zh/post/deploy-khoj-ai-second-brain-vps/]
draft: false
---

## Khoj 是什么？

[Khoj](https://khoj.dev) 是一款开源的、可自托管的 **AI 第二大脑**，能够充当你的个人 AI 助手。该项目在 GitHub 上拥有超过 34,000 颗星，是目前最受欢迎的自托管 AI 平台之一。

Khoj 的核心能力包括：

- **与任何 LLM 对话** — 支持本地模型（通过 Ollama、llama.cpp）和云端模型（GPT、Claude、Gemini、DeepSeek）
- **搜索你的文档** — 支持 PDF、Markdown、Notion、Word、图片等格式的语义搜索
- **构建自定义 AI 智能体** — 配置专属知识库、人设、对话模型和工具
- **自动化研究** — 自动生成个性化简报和智能通知发送到你的邮箱
- **多平台访问** — 浏览器、Obsidian、Emacs、桌面端、手机或 WhatsApp
- **图像生成与语音** — 内置文生图和文字转语音功能

最重要的是，它完全开源（AGPL-3.0 许可），从设计之初就支持自托管部署。

## 为什么在 VPS 上运行 Khoj？

在 VPS 上运行 Khoj 能带来以下优势：

1. **全天候在线** — 你的 AI 第二大脑 7×24 小时可用
2. **完全隐私** — 你的文档和查询永远不会离开你的服务器
3. **连接本地大模型** — 搭配 Ollama 运行 Qwen3、Llama 3、Phi-4 等模型，完全在自有硬件上运行
4. **多设备同步** — 随时随地通过任何设备访问
5. **自定义集成** — 连接你自己的工具、API 和数据源

### 推荐 VPS 配置

| 组件 | 最低配置 | 推荐配置 |
|------|---------|---------|
| CPU  | 2 核    | 4 核    |
| 内存 | 4 GB   | 8 GB+   |
| 存储 | 20 GB  | 50 GB+ SSD |
| 系统 | Ubuntu 22.04+ | Ubuntu 24.04 |
| Docker | 已安装 | Docker Compose v2 |

如果计划在 Khoj 旁边同时运行 Ollama 本地大模型，建议 **8 GB 以上内存**，并考虑支持 GPU 的 VPS（NVIDIA T4、A10 等）。

## 第一步：安装 Docker 和 Docker Compose

在 VPS 上安装 Docker：

```bash
# 更新系统
sudo apt update && sudo apt upgrade -y

# 安装 Docker
curl -fsSL https://get.docker.com | sudo sh

# 将当前用户加入 docker 组
sudo usermod -aG docker $USER

# 登出后重新登录，或直接执行：
newgrp docker

# 验证安装
docker --version
docker compose version
```

## 第二步：使用 Docker Compose 部署 Khoj

创建 Khoj 目录并下载官方的 docker-compose 文件：

```bash
mkdir -p ~/khoj && cd ~/khoj
wget https://raw.githubusercontent.com/khoj-ai/khoj/master/docker-compose.yml
```

`docker-compose.yml` 包含四个服务：

- **database** — 带 pgvector 扩展的 PostgreSQL，用于向量存储
- **sandbox** — Terrarium 代码执行沙箱
- **search** — SearXNG 元搜索引擎，提供网页搜索能力
- **server** — Khoj 主应用

### 配置环境变量

编辑 docker-compose.yml，设置必要环境变量：

```bash
nano docker-compose.yml
```

在 `server` 服务的 `environment` 部分修改以下变量：

```yaml
environment:
  - POSTGRES_PASSWORD=your_secure_password        # 修改默认密码
  - KHOJ_DJANGO_SECRET_KEY=your_random_secret_key  # 生成随机密钥
  - KHOJ_DEBUG=False
  - KHOJ_ADMIN_EMAIL=admin@yourdomain.com
  - KHOJ_ADMIN_PASSWORD=your_admin_password
```

生成 Django 密钥：

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(50))"
```

### 启动 Khoj

```bash
cd ~/khoj
docker compose up -d
```

检查启动日志：

```bash
docker compose logs -f server
```

启动成功后，Khoj 将在 `http://your-vps-ip:42110` 可用。

## 第三步：连接 Ollama 使用本地大模型

想要完全在本地运行模型，可以在同一台 VPS 上安装 Ollama：

```bash
# 安装 Ollama
curl -fsSL https://ollama.com/install.sh | sh

# 拉取模型（以 Qwen3 为例，中英双语支持优秀）
ollama pull qwen3:8b

# 内存有限的话，可以使用更小的模型
ollama pull phi4-mini:3.8b
```

在 docker-compose.yml 的 `server` 服务中添加以下环境变量：

```yaml
- OPENAI_BASE_URL=http://host.docker.internal:11434/v1/
- KHOJ_DEFAULT_CHAT_MODEL=qwen3
```

重启 Khoj：

```bash
docker compose down && docker compose up -d
```

现在 Khoj 将使用你本地的 Ollama 模型作为默认对话后端。

## 第四步：配置反向代理与 HTTPS（推荐）

为了保证安全访问，推荐使用 Caddy 或 Nginx 配置 HTTPS。

### 使用 Caddy（最简单）

```bash
# 安装 Caddy
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install caddy
```

创建 `/etc/caddy/Caddyfile`：

```
khoj.yourdomain.com {
    reverse_proxy localhost:42110
}
```

### 使用 Nginx

```bash
sudo apt install nginx
```

创建 `/etc/nginx/sites-available/khoj`：

```nginx
server {
    server_name khoj.yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:42110;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400;
    }
}
```

启用并配置 HTTPS：

```bash
sudo ln -s /etc/nginx/sites-available/khoj /etc/nginx/sites-enabled/
sudo certbot --nginx -d khoj.yourdomain.com
sudo nginx -t && sudo systemctl reload nginx
```

然后更新 Khoj 的环境变量以支持公网访问：

```yaml
- KHOJ_NO_HTTPS=True
- KHOJ_DOMAIN=khoj.yourdomain.com
```

## 第五步：首次登录与初始配置

1. 打开 `https://khoj.yourdomain.com`（或 `http://your-vps-ip:42110`）
2. 使用你在 docker-compose.yml 中设置的管理员凭据登录
3. 进入 **设置 → 内容** 添加你的文档源
4. 进入 **设置 → 对话** 配置你偏好的 LLM

### 添加文档

Khoj 支持直接上传文件或指定目录。支持的格式包括：

- PDF、Markdown、纯文本
- Microsoft Word（.docx）
- 图片（支持 OCR 识别文字）
- Org-mode、Notion 导出
- GitHub 仓库

从 Web 界面添加内容：

1. 导航到 **设置 → 内容**
2. 点击 **添加内容**
3. 选择来源类型（文件上传、目录或 URL）
4. Khoj 将自动索引并使其可搜索

## 第六步：创建自定义 AI 智能体

Khoj 最强大的功能之一就是自定义智能体。创建方法如下：

1. 点击侧边栏的 **智能体**
2. 点击 **创建智能体**
3. 配置以下参数：
   - **名称与人设** — 定义智能体的性格和行为方式
   - **知识库** — 选择该智能体可以访问的文档
   - **模型** — 选择驱动此智能体的 LLM
   - **工具** — 启用联网搜索、代码执行、图像生成等功能
   - **指令** — 给智能体设定特定的系统提示词

**示例**：创建一个「技术文档写手」智能体，让它只访问你的技术文档文件夹，并以专业风格回复问题。

## 第七步：启用联网搜索与高级功能

### 使用 SearXNG 联网搜索

docker-compose.yml 已包含 SearXNG。要让 Khoj 具备联网搜索能力：

1. 取消 `SERPER_DEV_API_KEY` 行的注释，从 [serper.dev](https://serper.dev) 获取免费 API 密钥
2. 或使用 [Firecrawl](https://firecrawl.dev) 获得搜索+页面读取的整合能力
3. 重启 Khoj：`docker compose down && docker compose up -d`

### 启用 Khoj 的计算机能力（实验性）

Khoj 可以在虚拟计算机上执行操作：

```yaml
- KHOJ_OPERATOR_ENABLED=True
# 挂载 Docker 套接字让 Khoj 控制容器
# - /var/run/docker.sock:/var/run/docker.sock
```

## 故障排除

### 连接 Ollama 时出现"Connection refused"

确保 docker-compose.yml 中包含以下配置：

```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"
```

### Khoj 无法启动

检查日志：

```bash
docker compose logs server
docker compose logs database
```

常见原因：
- 内存不足（至少需要 2 GB 可用内存）
- PostgreSQL 尚未完全初始化（等待 30 秒）
- 端口 42110 已被占用

### 本地 LLM 响应缓慢

- 使用量化模型（Q4_K_M 或 Q5_K_M）
- 考虑使用更小的模型如 Phi-4-mini（3.8B）而非 7B+
- 如果有 GPU，启用硬件加速

## 日常运维

```bash
# 停止 Khoj
cd ~/khoj && docker compose down

# 更新 Khoj
cd ~/khoj && docker compose pull && docker compose up -d

# 查看日志
cd ~/khoj && docker compose logs -f

# 备份数据（数据卷位于 /var/lib/docker/volumes/）
docker run --rm -v khoj_khoj_db:/data -v $(pwd):/backup alpine tar czf /backup/khoj-db-backup.tar.gz -C /data .
docker run --rm -v khoj_khoj_config:/data -v $(pwd):/backup alpine tar czf /backup/khoj-config-backup.tar.gz -C /data .
```

## 性能优化建议

1. **使用 SSD 存储** — 向量搜索对 I/O 性能敏感
2. **内存不足时增加 Swap**：
   ```bash
   sudo fallocate -l 4G /swapfile
   sudo chmod 600 /swapfile
   sudo mkswap /swapfile
   sudo swapon /swapfile
   echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
   ```
3. **限制并发用户** — Khoj 适合个人或小团队使用
4. **使用更小的向量模型** — 在设置中配置以加快索引速度
5. **考虑混合方案** — 复杂推理用云端 LLM，日常查询用本地模型

## 总结

在 VPS 上部署 Khoj 让你拥有一个私有的、全天候在线的 AI 第二大脑。它能保护你的隐私，并可根据你的需求进行深度定制。使用 Docker Compose，整个安装过程只需几分钟。搭配 Ollama 本地模型，你可以构建一个完全自给自足的 AI 生态系统。

无论你是需要搜索数千份文档的研究人员、想要 AI 辅助编程的开发者，还是仅仅需要一个私人 AI 助手，在 VPS 上运行 Khoj 都是一个强大而实用的选择。

**下一步行动：**
- 阅读 [Khoj 官方文档](https://docs.khoj.dev)
- 加入 [Khoj Discord 社区](https://discord.gg/BDgyabRM6e)
- 尝试为你的工作流创建自定义智能体
- 设置从云存储自动同步文档
