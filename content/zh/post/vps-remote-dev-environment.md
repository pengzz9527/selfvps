---
title: "自建 VPS 远程开发环境：Code-Server + Jupyter + Git 一体化方案"
description: "告别本地开发环境配置烦恼，在 VPS 上部署 VS Code + Jupyter + Git 一体化远程开发平台，随时随地从任何设备编码、跑实验、管理代码，全流程零依赖本地硬件"
date: 2026-08-31T10:00:00+08:00
lastmod: 2026-08-31T10:00:00+08:00
slug: "vps-remote-dev-environment"
image: /images/posts/vps-remote-dev-environment/featured.png
tags: ["VPS", "远程开发", "Code-Server", "Jupyter", "Git", "Docker", "DevOps", "自托管"]
categories: ["开发工具"]
aliases: [/zh/post/vps-remote-dev-environment/]
draft: false
---

## 引言

你是不是经历过这些场景？

- 换了新电脑，半天时间全花在配开发环境上
- 家里电脑性能不够，跑 AI 模型/编译大项目卡成 PPT
- 想在家用平板/iPad 写代码，发现根本没法干
- 和同事协作调试，对方环境跟你不一样，"在我机器上是好的"
- 半夜突发需求，家里电脑关机了，只能等第二天

这些问题都有一个共同的解法：**把开发环境搬到 VPS 上**。

本文带你搭建一套完整的 **VPS 远程开发环境**：VS Code 网页版（Code-Server）+ JupyterLab + Git，配合 Nginx 反向代理、HTTPS 加密、安全认证，让你从任何设备、任何浏览器都能无缝编码、跑实验、管理代码。

---

## 一、架构总览

```
┌─────────────────────────────────────────────────────────────────┐
│                        你的任意设备                              │
│   Mac / Windows / Linux / iPad / 手机  →  浏览器                │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTPS
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    VPS (Ubuntu 24.04)                           │
│                                                                 │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────────┐   │
│  │   Nginx      │──▶│  Code-Server │   │  JupyterLab      │   │
│  │  :443 HTTPS  │   │  :8080       │   │  :8888           │   │
│  │  反向代理    │   │  VS Code 网页 │   │  Notebook 环境   │   │
│  └──────┬───────┘   └──────┬───────┘   └────────┬─────────┘   │
│         │                  │                     │             │
│         │                  └────────┬────────────┘             │
│         │                           ▼                          │
│         │                  ┌─────────────────┐                 │
│         │                  │   Docker        │                 │
│         │                  │  Git 仓库目录   │                 │
│         │                  │  Python/Node等  │                 │
│         │                  │  开发工具链     │                 │
│         │                  └─────────────────┘                 │
│                                                                 │
│  域名: dev.yourdomain.com → Nginx 分发                         │
└─────────────────────────────────────────────────────────────────┘
```

---

## 二、环境准备

### 2.1 VPS 最低配置

| 用途 | 最低配置 | 推荐配置 |
|------|---------|---------|
| Code-Server 基础开发 | 2 CPU / 4GB RAM / 40GB Disk | 4 CPU / 8GB RAM / 100GB SSD |
| 含 Jupyter + AI 项目 | 4 CPU / 8GB RAM / 80GB Disk | 8 CPU / 16GB RAM / 200GB NVMe |
| 多容器 + GPU 推理 | 8 CPU / 32GB RAM / 500GB SSD | 16 CPU / 64GB RAM + GPU |

### 2.2 系统初始化

```bash
# 更新系统
sudo apt update && sudo apt upgrade -y

# 安装基础工具
sudo apt install -y curl wget git unzip htop net-tools

# 安装 Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# 安装 Nginx
sudo apt install -y nginx certbot python3-certbot-nginx
```

### 2.3 域名解析

将 `dev.yourdomain.com` 指向你的 VPS IP：

```bash
# DNS A 记录
dev.yourdomain.com  →  你的 VPS IP
```

---

## 三、部署 Code-Server（VS Code 网页版）

### 3.1 使用 Docker 部署

```bash
# 创建工作目录
mkdir -p ~/dev-environment/code-server/{data,projects}
cd ~/dev-environment

# 拉取并启动 Code-Server
docker run -d \
  --name code-server \
  --restart unless-stopped \
  -p 127.0.0.1:8080:8080 \
  -v ~/dev-environment/projects:/home/coder/projects \
  -v ~/dev-environment/code-server/data:/home/coder/.local/share/code-server \
  -e PASSWORD=你的强密码 \
  -e TZ=Asia/Shanghai \
  -e PROXY_DOMAIN=dev.yourdomain.com \
  ghcr.io/coder/code-server:latest
```

### 3.2 验证部署

```bash
# 查看容器状态
docker ps | grep code-server

# 本地测试访问
curl -k https://localhost:8080
# 或者用 ssh 端口转发临时访问
ssh -L 8080:localhost:8080 your-vps
# 然后浏览器打开 http://localhost:8080
```

### 3.3 推荐安装的扩展

进入 Code-Server 后，在扩展市场搜索安装：

| 扩展名 | 用途 |
|--------|------|
| Chinese Language Pack | 中文界面 |
| Remote - SSH | SSH 远程开发 |
| Python | Python 开发支持 |
| Go | Go 语言支持 |
| Prettier | 代码格式化 |
| ESLint | JavaScript/TypeScript  lint |
| GitLens | Git 增强 |
| Project Manager | 多项目管理 |
| Material Icon Theme | 文件图标美化 |
| Error Lens | 行内错误提示 |

---

## 四、部署 JupyterLab

### 4.1 Docker 一键部署

```bash
mkdir -p ~/dev-environment/jupyter/{notebooks,projects}
cd ~/dev-environment

docker run -d \
  --name jupyter \
  --restart unless-stopped \
  -p 127.0.0.1:8888:8888 \
  -v ~/dev-environment/projects:/home/jovyan/work \
  -v ~/dev-environment/jupyter/notebooks:/home/jovyan/notebooks \
  -e PASSWORD=你的Jupyter密码 \
  -e TZ=Asia/Shanghai \
  jupyter/base-notebook:latest
```

### 4.2 常用镜像选择

```bash
# 基础版（最小）
jupyter/base-notebook

# Python + 科学计算
jupyter/scipy-notebook

# AI/ML 完整版
jupyter/pyspark-notebook

# 带 GPU 支持（需要 nvidia-container-toolkit）
jupyter/torch-notebook
```

### 4.3 安装额外 Python 包

```bash
# 进入容器安装
docker exec -it jupyter bash

# 安装常用包
pip install numpy pandas matplotlib seaborn scikit-learn
pip install torch torchvision torchaudio
pip install transformers datasets accelerate
pip install langchain langgraph llama-index

# 退出后保存为镜像
docker commit jupyter jupyter:custom
```

---

## 五、Nginx 反向代理配置

### 5.1 获取 SSL 证书

```bash
sudo certbot --nginx -d dev.yourdomain.com --non-interactive --agree-tos -m your@email.com
```

### 5.2 Nginx 配置

```bash
sudo tee /etc/nginx/sites-available/dev.yourdomain.com << 'EOF'
server {
    listen 443 ssl http2;
    server_name dev.yourdomain.com;

    ssl_certificate     /etc/letsencrypt/live/dev.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/dev.yourdomain.com/privkey.pem;

    # 安全头
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Strict-Transport-Security "max-age=31536000" always;

    # Code-Server
    location / {
        proxy_pass                         http://127.0.0.1:8080;
        proxy_http_version                 1.1;
        proxy_set_header Upgrade           $http_upgrade;
        proxy_set_header Connection        upgrade;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass                 $http_upgrade;
        proxy_read_timeout                  86400;
    }

    # JupyterLab
    location /jupyter/ {
        proxy_pass                         http://127.0.0.1:8888/jupyter/;
        proxy_http_version                 1.1;
        proxy_set_header Upgrade           $http_upgrade;
        proxy_set_header Connection        upgrade;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout                  86400;
        proxy_set_header X-Frame-Options   "";
    }

    # 静态资源
    location ~* \.(css|js|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
        proxy_pass http://127.0.0.1:8080;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
}

# HTTP 重定向到 HTTPS
server {
    listen 80;
    server_name dev.yourdomain.com;
    return 301 https://$host$request_uri;
}
EOF

sudo ln -sf /etc/nginx/sites-available/dev.yourdomain.com /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

### 5.3 自动续期证书

```bash
# 测试续期
sudo certbot renew --dry-run

# 确认定时任务存在
sudo systemctl status certbot.timer
```

---

## 六、Git 集成与代码管理

### 6.1 配置 Git

```bash
# 进入 Code-Server 终端，配置全局信息
git config --global user.name "你的名字"
git config --global user.email "you@email.com"
git config --global core.editor "code --wait"
git config --global init.defaultBranch main

# 生成 SSH 密钥
ssh-keygen -t ed25519 -C "your@email.com"
cat ~/.ssh/id_ed25519.pub  # 复制到 GitHub/GitLab
```

### 6.2 项目目录组织

```
~/projects/
├── web-app/              # Web 项目
│   ├── src/
│   ├── package.json
│   └── README.md
├── ml-experiments/       # AI/ML 项目
│   ├── notebooks/
│   ├── models/
│   └── requirements.txt
├── scripts/              # 工具脚本
└── personal/             # 个人笔记
    └── obsidian-vault/
```

### 6.3 代码同步策略

```bash
# 方式一：Git 推送远程仓库（推荐）
cd ~/projects/my-project
git init
git remote add origin git@github.com:username/my-project.git
git add .
git commit -m "初始提交"
git push -u origin main

# 方式二：rsync 同步到本地
rsync -avz --progress coder@your-vps:~/projects/my-project/ ./my-project/

# 方式三：使用 syncthing 双向同步
# 详见：https://syncthing.net/
```

---

## 七、安全加固

### 7.1 防火墙配置

```bash
# 只开放必要端口
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp      # SSH
sudo ufw allow 80/tcp      # HTTP（重定向用）
sudo ufw allow 443/tcp     # HTTPS
sudo ufw enable
```

### 7.2 Fail2ban 防护

```bash
sudo apt install -y fail2ban

sudo tee /etc/fail2ban/jail.local << 'EOF'
[sshd]
enabled = true
port = ssh
filter = sshd
logpath = /var/log/auth.log
maxretry = 3
bantime = 3600

[code-server]
enabled = true
port = http,https
filter = http-auth
logpath = /home/coder/.local/share/code-server/logs
maxretry = 5
bantime = 3600
EOF

sudo systemctl enable fail2ban
sudo systemctl restart fail2ban
```

### 7.3 备份配置

```bash
# 定期备份开发环境配置
sudo tar czf /backup/dev-environment-$(date +%Y%m%d).tar.gz \
  ~/dev-environment/ \
  ~/.ssh/ \
  ~/.gitconfig

# 上传到对象存储（可选）
aws s3 cp /backup/dev-environment-$(date +%Y%m%d).tar.gz \
  s3://your-backup-bucket/dev-environment/
```

---

## 八、进阶：Docker Compose 一键启动

将所有服务整合到一个 `docker-compose.yml`：

```yaml
# ~/dev-environment/docker-compose.yml
version: "3.8"

services:
  code-server:
    image: ghcr.io/coder/code-server:latest
    container_name: code-server
    restart: unless-stopped
    ports:
      - "127.0.0.1:8080:8080"
    volumes:
      - ./projects:/home/coder/projects
      - ./code-server/data:/home/coder/.local/share/code-server
    environment:
      - PASSWORD=${CS_PASSWORD}
      - TZ=Asia/Shanghai
      - PROXY_DOMAIN=dev.yourdomain.com
    networks:
      - dev-net

  jupyter:
    image: jupyter/scipy-notebook:latest
    container_name: jupyter
    restart: unless-stopped
    ports:
      - "127.0.0.1:8888:8888"
    volumes:
      - ./projects:/home/jovyan/work
      - ./jupyter/notebooks:/home/jovyan/notebooks
    environment:
      - PASSWORD=${JPY_PASSWORD}
      - TZ=Asia/Shanghai
    networks:
      - dev-net

networks:
  dev-net:
    driver: bridge
```

```bash
# 创建 .env 文件
cat > ~/dev-environment/.env << EOF
CS_PASSWORD=你的CodeServer密码
JPY_PASSWORD=你的Jupyter密码
EOF

# 一键启动
cd ~/dev-environment
docker compose up -d

# 查看日志
docker compose logs -f
```

---

## 九、实际使用场景

### 9.1 场景一：用 iPad 写代码

```
iPad Safari → dev.yourdomain.com → Code-Server
                ↓
         完整 VS Code 体验
         键盘 + 鼠标（或触控）
         保存的代码实时推送 Git
```

### 9.2 场景二：跑 AI 实验不费家里的电

```bash
# 在 VPS 上跑训练，家里电脑只看结果
cd ~/projects/ml-experiments
python train.py --epochs 100  # 跑在你的 VPS 上
# 同时用 Jupyter 实时监控训练曲线
```

### 9.3 场景三：随时随地接入团队项目

```bash
# 任何设备登录 → 环境完全一致
git clone https://github.com/team/project.git
code project/  # 直接在浏览器里打开
# 代码自动保存，不用担心丢文件
```

---

## 十、常见问题

### Q1：Code-Server 访问慢怎么办？

```bash
# 检查带宽占用
iftop -i eth0

# 在 code-server 中禁用动画
# 设置 → 外观 → 减少动画
```

### Q2：如何共享开发环境给团队成员？

```bash
# 方案一：每个人有自己的容器，共享 projects 目录
# 方案二：使用 GitHub Codespaces 风格的 DevContainer
# 方案三：Nginx 加基本认证限制访问
```

### Q3：磁盘空间不足怎么办？

```bash
# 清理 Docker 未使用的资源
docker system df          # 查看占用
docker system prune -a    # 清理（谨慎使用）
docker volume prune       # 清理匿名卷

# 迁移项目到其他盘
mv /home/coder/projects /mnt/large-disk/projects
ln -s /mnt/large-disk/projects /home/coder/projects
```

### Q4：忘记密码怎么办？

```bash
# Code-Server 密码在配置文件中
cat ~/dev-environment/code-server/data/User/settings.json
# 或直接重置
docker exec code-server passwd coder
```

---

## 总结

通过本文，你学会了：

| 能力 | 工具 |
|------|------|
| VS Code 网页版 | Code-Server |
| 交互式编程 | JupyterLab |
| 代码版本管理 | Git + GitHub |
| 安全访问 | Nginx + HTTPS + Fail2ban |
| 一键部署 | Docker Compose |

**核心收益：**
- 🎯 **环境一致**：任何设备，环境完全相同
- 💰 **成本节省**：廉价 VPS 替代高性能本地电脑
- 🔒 **数据安全**：代码始终在你的服务器上
- 🚀 **效率提升**：随时开工，不再被硬件束缚
- 🌍 **移动办公**：手机/iPad 也能写代码

访问 `https://dev.yourdomain.com` 开始你的云端开发之旅吧！
