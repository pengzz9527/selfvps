---
title: "月花 4 欧元，拥有一个自己管数据的 AI 助手：Hermes Agent 自部署教程"
description: "在同一个月花 $200 用 ChatGPT 的世界里，你也可以花 €3.99 在 VPS 上部署开源 AI 代理 Hermes Agent——数据在自己手里、7×24 小时在线、还能通过 Telegram 远程操控。本文是一份完整部署教程，也是系列开篇。"
date: 2026-05-22T18:00:00+08:00
slug: "hermes-self-hosted-ai-agent"
tags: ["Hermes Agent", "AI Agent", "自托管", "VPS部署", "开源", "隐私", "Telegram"]
categories: ["AI部署"]
draft: false
---

## 为什么需要自己部署？

把代码贴进 ChatGPT 问 bug，代码可能成为训练数据。让 AI 操作你的服务器，相当于把 root 权限交给第三方。

Hermes Agent 是 [Nous Research](https://nousresearch.com) 开源的 AI 代理框架（GitHub 156K+ ⭐）。安装在自己的 VPS 上，所有对话、记忆、技能文件都存在你的服务器上，不经过任何第三方。

开源 + 自托管 = 你的数据只有你能访问。

## 成本

VPS 选 Hetzner CX22（€3.99/月，2核/4GB/40GB），或者 RackNerd $1.50/月（1核/1GB）也能跑。

API 调用费因人而异。日常编程用 DeepSeek V3（$0.27/百万输入 token），一个月重度使用约 $20-30。**你只付算力，不付订阅费。**

作为参考：ChatGPT Plus $20/月（不能自托管），Claude Pro $20/月（不能自托管）。

## 部署步骤

### 1. 买 VPS

Hetzner CX22（€3.99/月），选 Ubuntu 24.04。如果是 Oracle Cloud 免费 ARM 实例也一样跑。

> 国内用户可以用 RackNerd $1.50/月或 BuyVM $3.50/月，区别不大。

### 2. 安装依赖

```bash
ssh root@你的VPS-IP

apt update && apt upgrade -y
apt install -y curl git ffmpeg build-essential
```

`ffmpeg` 是音视频处理用的，跑 cron 任务生成视频/音频时需要。

### 3. 安装 Hermes Agent

```bash
curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash
source ~/.bashrc
```

安装脚本会处理 uv（Python 包管理器）、Python 3.11、Node.js（部分工具需要）、ripgrep（会话搜索用）、以及所有 Python 依赖。耗时约 30 秒。

### 4. 验证

```bash
hermes doctor
```

全部绿色通过就对了。如果有红色报错，通常是缺某个系统包，`apt install` 补上就行。

### 5. 配置模型

```bash
hermes model
```

交互式选模型。或者直接指定：

```bash
hermes config set provider openrouter
hermes config set openrouter_api_key sk-or-v1-你的key
hermes model openrouter/anthropic/claude-sonnet-4
```

**省钱方案：** DeepSeek V3、Qwen 2.5 系列、Llama 3 系列，编程能力够用，成本低很多。

### 6. 配置 Telegram 网关（推荐）

装一次，之后所有操作都在手机上完成，不用反复 SSH。

```bash
hermes gateway setup
```

按提示：
1. 在 Telegram 搜 @BotFather
2. `/newbot` 创建 Bot，取个名字
3. 复制 Bot Token，粘贴

```bash
hermes gateway start
```

现在给 Bot 发消息，Hermes 会响应。

## 让它永不掉线

### 方案 A：crontab 开机自启（最简单）

```bash
crontab -e
# 加一行：
@reboot cd /root && hermes gateway start &
```

### 方案 B：systemd 服务（更可靠）

```ini
# /etc/systemd/system/hermes-gateway.service
[Unit]
Description=Hermes Gateway
After=network.target

[Service]
ExecStart=/root/.hermes/hermes-agent/venv/bin/python -m hermes_cli.main gateway run
WorkingDirectory=/root
Restart=always
User=root

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable --now hermes-gateway
```

推荐方案 B。`Restart=always` 保证进程挂了自动重启，crontab 做不到。

## 部署后常见问题

### 网关启动报错

检查 `~/.hermes/logs/gateway.log`，大部分问题是 Bot Token 配错了。重新跑 `hermes gateway setup`。

### 内存不够

1GB 的 VPS 默认跑 Hermes + 浏览器工具可能 OOM。关掉不用的工具：

```bash
hermes tools disable browser
hermes tools disable vision
```

只保留 terminal / file / web 三个核心工具，内存占用降到 200MB 以下。

### ARM 架构（Oracle 免费实例）

安装脚本自动处理 ARM 兼容性。唯一要注意的是有些 Python 包可能需要编译，安装时间稍长。

### 模型 API 超时

OpenRouter 免费模型经常超时。切换到付费模型，或在配置里调高 timeout：

```bash
hermes config set agent.max_turns 120
```

### 如何更新

```bash
hermes update
```

更新后 `/restart` 或重启 gateway 生效。

## 磁盘管理

Hermes 默认保存会话日志，长时间运行会累积几 GB。定期清理：

```bash
hermes sessions prune --older-than 30
```

或者设置自动清理策略（编辑 config.yaml）：

```yaml
sessions:
  retention_days: 30
```

## 接下来

部署完 Hermes，你有了一个 24 小时在线、数据私有的 AI 代理。它具体能帮你做什么？

这是系列第一篇。后续文章：

- **第二篇：** 用 Hermes 自动发布博客文章——从写作到 Git push 全自动
- **第三篇：** 用 Hermes 监控服务器——异常告警、日志分析、自动修复
- **第四篇：** 用 Hermes 运营 Telegram 频道——定时推送、热点抓取、内容改写
- **第五篇：** 用 Hermes 做数据 ETL——采集、清洗、入库一条龙

这系列的核心观点：**AI 代理最有价值的用法，不是在云端和你聊天——而是在你自己的基础设施上，替你干活。**

下一篇见。

---

*系列索引：[第二篇：用 Hermes 自动发布博客文章]()（撰写中）*
