---
title: "用开源 WhatsApp 网关 + AI 搭建聊天机器人，躺着接单"
description: "OpenWA 开源 WhatsApp API 网关搭配 n8n 和 AI，无需编程即可搭建自动客服系统，每月轻松接单变现"
date: 2026-05-20T22:00:00+08:00
lastmod: 2026-05-20T22:00:00+08:00
slug: "openwa-whatsapp-ai-chatbot"
tags: ["WhatsApp", "AI", "聊天机器人", "n8n", "开源项目", "副业", "自托管", "Docker"]
categories: ["AI 实战"]
draft: false
---

## 📌 主题介绍

有没有想过——帮楼下的水果店、小区里的健身房、你常去的美容院做一个 AI 客服，每个月收几百块维护费？这个想法以前很贵（Twilio 等商业 WhatsApp API 每月起步几百美元），但今天完全变了。

OpenWA 是目前最火的开源项目——它是一个完全免费、自托管的 WhatsApp API 网关。装好之后，你的电脑就变成了一个 WhatsApp 消息服务器，可以接入 AI 自动回复消息。

最关键的是，它内置了 n8n 集成。n8n 是一个类似 Zapier 的无代码自动化平台，你不需要写一行代码，就能像搭积木一样把 WhatsApp、ChatGPT/Claude API、Google Sheets 串联起来。

---

## 💡 核心价值

为什么这个工具适合做副业？

**🥇 零成本启动** — OpenWA 完全开源免费，装在自己的旧电脑或云服务器上就能跑。对比商业 WhatsApp API（每月 $50-$500），这简直是白嫖。

**🥇 n8n 无代码对接 AI** — OpenWA 直接集成了 n8n 社区节点。你用鼠标拖一拖，就能让 GPT 自动回复 WhatsApp 消息。不需要会写 Python 或 JavaScript。

**🥇 多账号管理** — 一个实例可以同时管理多个 WhatsApp 号码。你做 5 个客户的业务，不用装 5 套系统。

**🥇 一键部署** — 项目提供了 Docker 一键启动命令，跟着敲两行回车就行。

---

## 🛠️ 实操步骤

### 第一步：准备工作

- 一台能上网的电脑（或几十块/月的云服务器）
- 一个用于测试的 WhatsApp 号码
- 一个 AI API 密钥（OpenAI 或 Claude）

### 第二步：一键安装 OpenWA

打开终端（Mac 搜索"终端"，Windows 搜索"PowerShell"），依次输入：

```bash
git clone https://github.com/rmyndharis/OpenWA.git
cd OpenWA
docker compose -f docker-compose.dev.yml up -d
```

等几秒钟，访问 `http://localhost:2886`，你就看到了管理后台界面。扫码登录 WhatsApp，搞定。

### 第三步：连接 AI

- 打开 n8n（也可以用官方的 n8n.cloud 免费版）
- 创建一个新工作流：当 WhatsApp 收到消息 → 发给 ChatGPT → 自动回复
- 全部用鼠标拖拽节点完成，不需要写代码

整个过程，一个新手大概 30 分钟就能跑通。

---

## 💰 变现思路

根据海外 freelancer 社区的分享，目前 WhatsApp AI 客服的需求非常旺盛：

**1️⃣ 本地商家代运营** — 帮餐馆/理发店/健身房搭建 AI 客服，处理预约、菜单查询、营业时间等常见问题。每月收费 500-2000 元/店。

**2️⃣ 私域流量自动回复** — 帮微商/社群团长搭建自动回复系统，处理订单查询、发货通知。可以按消息量收费或包月。

**3️⃣ 跨境客服外包** — 很多跨境电商卖家需要 24 小时客服，用 AI WhatsApp 机器人可以覆盖 80% 的常见问题。这在小红书/闲鱼上有大量需求。

**4️⃣ 教育/课程咨询** — 帮培训机构搭建自动招生咨询机器人，自动回答课程时间、价格、报名流程。

参考价格：根据 Upwork 和 Fiverr 的数据，一个 WhatsApp 聊天机器人搭建服务平均报价在 **$100-$500 美元**（约 700-3500 人民币），维护费另算。

---

## 🎯 适合人群

✅ 不懂编程但对 AI 感兴趣的人——整个过程不需要写代码

✅ 有本地商家资源的人——身边有小店老板、培训机构、健身房，他们都需要客服

✅ 想做被动收入的上班族/学生——搭建一次，每月收维护费

✅ 有基础电脑操作能力——能跟着教程敲命令行就行

---

总结：OpenWA 把原本需要编程才能搞定的 WhatsApp AI 客服，变成了"会打字就能做"的副业项目。趁热度还在，赶紧试试。

### 🔗 相关资源

- OpenWA GitHub: [github.com/rmyndharis/OpenWA](https://github.com/rmyndharis/OpenWA)
- n8n 官网: [n8n.io](https://n8n.io)（免费版可用）
