---
title: "Hermes Agent VPS 部署指南：在服务器上跑一个自我进化的 AI 助手"
description: "完整教程：在 VPS 上一键部署 Hermes Agent（GitHub 156K+ ⭐）——包含 VPS 资源推荐、一键安装、Telegram 网关配置、24小时稳定运行的生产级建议"
date: 2026-05-19T21:30:00+08:00
slug: "hermes-agent-vps-deployment"
tags: ["Hermes Agent", "AI Agent", "Nous Research", "VPS部署", "自托管", "Telegram", "Docker", "自动化"]
categories: ["AI部署"]
aliases: [/zh/post/hermes-agent-vps-deployment/]
draft: false
---

## Hermes Agent 是什么？

[Hermes Agent](https://github.com/NousResearch/hermes-agent)（GitHub 156K+ ⭐）是由 [Nous Research](https://nousresearch.com) 打造的自我进化 AI 智能体。和传统的 AI 助手不同（每次对话从头开始），Hermes 拥有内置的**学习循环**：

- **持久记忆**：跨会话保存关于你的信息——偏好、环境细节、项目惯例
- **自动创建技能**：完成复杂任务后，自动生成可复用的技能，下次做得更好
- **跨会话搜索**：使用 FTS5 全文搜索 + LLM 摘要，可以回忆之前对话的内容
- **无需锁定平台**：可以本地 CLI 使用，也可以通过 Telegram、Discord、Slack、WhatsApp、Signal、Email 远程交互
- **任意模型**：支持 OpenRouter（200+ 模型）、OpenAI、Nous Portal、HuggingFace 等，`hermes model` 一键切换
- **定时自动化**：内置 cron 调度器，日报、夜备、自动发布全自动
- **子代理并行**：为复杂任务启动多个并行子代理同时工作

对 VPS 用户最大的亮点：**一台 $5 的 VPS 就能跑**，你可以在手机上通过 Telegram 和它聊天，幕后它就在你的服务器上工作。

---

## VPS 资源推荐

Hermes Agent 对资源要求很低。因为它是调用外部 AI API（OpenRouter、OpenAI 等），绝大部分计算发生在云端，VPS 只需要运行代理进程、工具和消息网关。

### 最低配置
| 资源 | 要求 | 说明 |
|------|------|------|
| **CPU** | 1 核 (x86_64 / ARM64) | ARM 也能跑（如 Oracle 免费实例） |
| **内存** | 1 GB | 操作系统占 512MB 后够用 |
| **磁盘** | 5 GB | 包含系统 + Hermes + 工具 |
| **网络** | 任意公网 IP | 1 Mbps 即可满足 API 通信 |

### 推荐配置
| 资源 | 要求 | 说明 |
|------|------|------|
| **CPU** | 2 核 | 多任务更流畅 |
| **内存** | 2 GB | 可以同时跑 cron 任务 + 网关 + 浏览器工具 |
| **磁盘** | 20 GB | 存放下载文件、克隆仓库、技能缓存 |
| **网络** | 100 Mbps | 更快的 git clone 和 API 响应 |

### 推荐 VPS 厂商

| 厂商 | 价格 | 配置 | 适合场景 |
|------|------|------|----------|
| **Hetzner** | €3.99/月 (CX22) | 2核, 4GB, 40GB | ⭐ 性价比之王，首推 |
| **Oracle Cloud 免费** | 免费 | 4核ARM, 24GB | 如果能注册成功的话 |
| **DigitalOcean** | $6/月 | 1核, 1GB, 25GB | 设置最简单 |
| **Vultr** | $6/月 | 1核, 1GB, 25GB | 全球数据中心多 |
| **RackNerd** | $1.50/月 | 1核, 1GB, 20GB | 最便宜 |
| **BuyVM** | $3.50/月 | 1核, 1GB, 20GB | 适合跑媒体工具 |

**我的推荐：** Hetzner CX22（€3.99/月），或者能注册到 Oracle Cloud 免费实例的话用免费。

---

## 详细部署步骤

### 1. 购买并登录 VPS

选择 Ubuntu 22.04 或 24.04 LTS。登录：

```bash
ssh root@你的VPS-IP
```

### 2. 安装系统依赖

```bash
apt update && apt upgrade -y
apt install -y curl git ffmpeg build-essential
```

### 3. 一键安装 Hermes Agent

只需要一条命令，一分钟内完成：

```bash
curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash
source ~/.bashrc
```

安装脚本自动处理：
- **uv**（Python 包管理器，比 pip 快 10 倍）
- Python 3.11
- Node.js（部分工具需要）
- ripgrep（会话搜索用）
- ffmpeg（音视频处理）
- 所有 Python 依赖

### 4. 验证安装

```bash
hermes doctor
```

会检查所有组件是否就绪，应该全部绿色通过。

### 5. 配置模型提供商

```bash
hermes model
# 选择一个提供商，或者直接配置 API Key
hermes config set provider openrouter
hermes config set openrouter_api_key sk-or-v1-xxx
hermes model openrouter/anthropic/claude-sonnet-4
```

### 6. 配置 Telegram 网关（强烈推荐）

这是在 VPS 上最实用的用法——装一次，手机上就能用了：

```bash
hermes gateway setup
# 按提示操作：
# 1. 在 Telegram 搜索 @BotFather
# 2. /newbot 创建一个新 Bot
# 3. 复制 Bot Token
# 4. 输入 Token 完成配置
hermes gateway start
```

现在你可以给 Telegram Bot 发消息，Hermes 会自动响应。网关进程在 VPS 后台运行，你关机睡觉它也醒着。

### 7. 使用 CLI

```bash
hermes
```

启动交互式终端界面（TUI），可以聊天、创建技能、安排 cron 任务等。

---

## 生产环境运维建议

### 使用 tmux 保持会话

把 Hermes 放在 tmux 里，断开 SSH 也不会停：

```bash
tmux new -s hermes
hermes
# Ctrl+B, D 分离（程序继续运行）
tmux attach -t hermes  # 重新连接
```

### 开机自启网关

编辑 crontab 添加：

```bash
crontab -e
# 添加：
@reboot cd /root && hermes gateway start &
```

### 使用 SSH Backend 模式

如果你想在本地电脑上跑 Hermes CLI，但让它操作 VPS：

```bash
hermes config set terminal.backend ssh
hermes config set terminal.ssh_host 你的VPS-IP
```

这样 Hermes 进程在你的电脑，但所有终端命令都在 VPS 上执行。

---

## Docker 部署（备选方案）

```bash
docker run -it --rm \
  -v ~/.hermes:/root/.hermes \
  ghcr.io/nousresearch/hermes-agent
```

不过对于 VPS 来说，原生安装更简单、资源占用更少，推荐用上面的步骤。

---

## 总结

| 项目 | 数据 |
|------|------|
| 安装耗时 | ~30 秒 |
| 安装后磁盘占用 | ~800 MB |
| 空闲内存占用 | ~150 MB |
| 对话中内存占用 | ~300-500 MB |
| 推荐 VPS | Hetzner CX22 (€3.99/月) |
| 远程控制 | Telegram / Discord 网关 |
| 定时任务 | 内置 cron 调度器 |

Hermes Agent 是目前最适合在 VPS 上部署的 AI 智能体之一——资源占用极低、可通过消息平台远程控制、内置自动化调度器。部署一次，你就有了一个 24/7 在线、会不断进化的 AI 助手。
