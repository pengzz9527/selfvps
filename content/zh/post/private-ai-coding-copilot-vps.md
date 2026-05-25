---
title: "在 VPS 上搭建私有 AI 编程助手：Continue.dev + Ollama 完全指南"
description: "GitHub Copilot 涨价、Cursor 闭源——用 VPS + 开源大模型搭建完全属于你自己的 AI 编程助手。完整部署指南，涵盖 Ollama 模型管理、Continue.dev 配置、VS Code/JetBrains 集成，月费不到 $10。"
date: 2026-05-25T21:30:00+08:00
slug: "private-ai-coding-copilot-vps"
tags: ["AI编程助手", "Continue.dev", "Ollama", "VPS部署", "开源", "编程效率", "自托管"]
categories: ["AI开发工具"]
image: /images/posts/private-ai-coding-copilot-vps/featured.png
draft: false
---

## 为什么需要自己的 AI 编程助手？

2025 年底开始，AI 编程助手的格局发生了巨大变化：

- **GitHub Copilot** 涨价到 $10/月（个人）/$19/月（企业），且代码数据存于微软服务器
- **Cursor** 闭源策略引发争议，$20/月起
- 越来越多的公司禁止员工将代码上传到第三方 AI 服务

**解决方案**：在自有的 VPS 上部署 [Ollama](https://ollama.ai) 运行开源大模型，配合 [Continue.dev](https://continue.dev)（开源 IDE 插件）实现完全自托管的 AI 编程体验。

**你的代码永远停留在本地，模型推理在你自己的 VPS 上进行。** 没有第三方能看到你的代码。

## 架构概览

```
你的电脑 (VS Code / JetBrains)
       │
       │ Continue.dev 插件
       │
       ▼
你的 VPS (Ollama 服务)
       │
       ├── deepseek-coder-v2 (代码补全)
       ├── codestral (代码补全备选)
       ├── qwen2.5-coder:7b (轻量备选)
       └── llama3.1:8b (闲聊/解释)
```

## 成本分析

| 方案 | 月费 | 隐私 | 可用模型 |
|------|------|------|----------|
| GitHub Copilot | $10-19 | ❌ 代码上传微软 | 单一模型 |
| Cursor Pro | $20 | ⚠️ 部分闭源 | 有限选择 |
| **本方案** | **$4-8** | **✅ 完全私有** | **任意模型** |

VPS 建议配置（起）：

- **入门**：Hetzner CX22（€3.99/月，2核/4GB/40GB）—— 跑 7B 模型足够
- **推荐**：Hetzner CAX21（€5.99/月，4核/8GB/40GB ARM）—— 跑 14B 模型
- **进阶**：Netcup RS1000（€5.50/月，4核/8GB）或带 GPU 的 VPS

> 💡 纯 CPU 推理 7B 模型（如 `qwen2.5-coder:7b`）每次补全约 2-5 秒，体验完全可以接受。14B 模型建议 8GB 以上内存。

## 第一步：VPS 部署 Ollama

### 1. 安装 Ollama

```bash
# SSH 到你的 VPS
ssh root@你的VPS-IP

# 一键安装 Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# 验证安装
ollama --version
```

### 2. 拉取编程专用模型

```bash
# DeepSeek Coder V2（推荐，代码能力最强）
ollama pull deepseek-coder-v2:16b

# Qwen2.5 Coder 7B（轻量级，响应快）
ollama pull qwen2.5-coder:7b

# Llama 3.1 8B（通用对话辅助）
ollama pull llama3.1:8b

# 查看已下载模型
ollama list
```

> 初次拉取模型需要几分钟，取决于 VPS 带宽。deepseek-coder-v2:16b 约 9GB，qwen2.5-coder:7b 约 4.5GB。

### 3. 配置 Ollama 允许远程访问

Ollama 默认只监听本地。我们需要让它监听所有网络接口，供本地 IDE 连接。

```bash
# 编辑 systemd 服务配置
systemctl edit ollama

# 添加以下内容（覆盖默认配置）：
```

```ini
[Service]
Environment="OLLAMA_HOST=0.0.0.0:11434"
```

```bash
# 重启 Ollama
systemctl daemon-reload
systemctl restart ollama

# 验证监听状态
ss -tlnp | grep 11434
```

### 4. 安全加固（重要！）

**不要将 Ollama 直接暴露在公网上**，否则任何人都可以调用你的模型。使用 ufw 限制 IP：

```bash
# 安装 ufw
apt install -y ufw

# 只允许你的家庭/办公室 IP 访问
ufw allow from 你的本机IP到 any port 11434 proto tcp
ufw enable

# 或者使用 WireGuard VPN（更推荐）
# 通过 VPN 连接后，Ollama 只监听在 VPN 接口上
```

> 最佳实践：为 Ollama 服务部署一个简单的 API 密钥验证反向代理（下面会介绍）。

## 第二步：配置 Continue.dev

### 1. 安装 Continue 插件

- **VS Code**：在扩展市场搜索 "Continue" 并安装
- **JetBrains**：在插件市场搜索 "Continue"

### 2. 配置 Ollama 连接

Continue 安装后，点击侧边栏的 Continue 图标，打开配置文件 `~/.continue/config.json`：

```json
{
  "models": [
    {
      "title": "DeepSeek Coder V2 (VPS)",
      "provider": "ollama",
      "model": "deepseek-coder-v2:16b",
      "apiBase": "http://你的VPS-IP:11434",
      "completionOptions": {
        "temperature": 0.1,
        "topP": 0.9,
        "maxTokens": 4096
      }
    },
    {
      "title": "Qwen2.5 Coder 7B (VPS)",
      "provider": "ollama",
      "model": "qwen2.5-coder:7b",
      "apiBase": "http://你的VPS-IP:11434",
      "completionOptions": {
        "temperature": 0.1,
        "topP": 0.9,
        "maxTokens": 2048
      }
    }
  ],
  "tabAutocompleteModel": {
    "title": "Qwen2.5 Coder (Tab Auto)",
    "provider": "ollama",
    "model": "qwen2.5-coder:7b",
    "apiBase": "http://你的VPS-IP:11434"
  },
  "slashCommands": [
    {
      "name": "edit",
      "description": "编辑选中代码"
    },
    {
      "name": "comment",
      "description": "为代码添加注释"
    },
    {
      "name": "optimize",
      "description": "优化代码性能"
    },
    {
      "name": "explain",
      "description": "解释代码逻辑"
    }
  ]
}
```

### 3. Tab 自动补全设置

Continue 的 Tab 自动补全功能是它最亮眼的功能之一。在 VS Code 中：

1. 打开命令面板（`Cmd+Shift+P` / `Ctrl+Shift+P`）
2. 输入 "Continue: Toggle Tab Autocomplete"
3. 启用后，代码补全建议会以内联灰色文本显示
4. 按 `Tab` 接受建议

`tabAutocompleteModel` 建议使用响应速度最快的模型。`qwen2.5-coder:7b` 在 4GB VPS 上约 2-4 秒返回补全，体验流畅。

## 第三步（进阶）：API 密钥验证 + 反向代理

直接暴露 11434 端口不够安全。用 Nginx 做反向代理并添加 API 密钥验证：

```bash
# 安装 Nginx
apt install -y nginx

# 创建配置
cat > /etc/nginx/sites-available/ollama-proxy << 'EOF'
server {
    listen 443 ssl;
    server_name ollama.你的域名.com;

    ssl_certificate /etc/letsencrypt/live/ollama.你的域名.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/ollama.你的域名.com/privkey.pem;

    location / {
        # API 密钥验证
        if ($http_x_api_key != "你的密钥") {
            return 401;
        }

        proxy_pass http://127.0.0.1:11434;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
EOF

# 启用配置
ln -s /etc/nginx/sites-available/ollama-proxy /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
```

然后在 Continue 配置中更新 `apiBase` 为 HTTPS 地址，并在 HTTP 请求头中添加 `X-Api-Key`。

## 模型选择建议

| 模型 | 参数 | 内存需求 | 代码能力 | 速度(4核CPU) |
|------|------|----------|----------|-------------|
| `qwen2.5-coder:1.5b` | 1.5B | < 2GB | ⭐⭐ | ⚡ 极快 |
| `qwen2.5-coder:7b` | 7B | ~4GB | ⭐⭐⭐⭐ | ⚡ 快 |
| `deepseek-coder-v2:16b` | 16B | ~9GB | ⭐⭐⭐⭐⭐ | 🐢 较慢 |
| `codestral:22b` | 22B | ~12GB | ⭐⭐⭐⭐⭐ | 🐢 慢 |
| `starcoder2:15b` | 15B | ~8GB | ⭐⭐⭐⭐ | ⏳ 中等 |

> **新手推荐**：先上 `qwen2.5-coder:7b`，它在 4GB VPS 上表现最好，速度和质量的平衡最佳。

## 进阶优化技巧

### 使用 GPU 加速（如你有 GPU VPS）

如果 VPS 有 NVIDIA GPU，Ollama 会自动使用 CUDA 加速：

```bash
# 在 GPU VPS 上安装 NVIDIA 驱动
apt install -y nvidia-driver-545 nvidia-utils-545

# 验证 GPU
nvidia-smi

# Ollama 自动检测 GPU，无需额外配置
# 运行 16B 模型时 GPU 推理比 CPU 快 5-10 倍
```

### 多 VPS 负载均衡

如果有多个 VPS，可以用 Nginx 做负载均衡：

```nginx
upstream ollama_backend {
    server vps1:11434 weight=3;
    server vps2:11434 weight=1;
}
```

### 使用内存盘加速模型加载

```bash
# 创建 16GB 内存盘（需要足够 RAM）
mount -t tmpfs -o size=16G tmpfs /mnt/ramdisk

# 将模型链接到内存盘
ln -s /mnt/ramdisk/blobs /usr/share/ollama/.ollama/models/blobs
```

## 使用体验对比

以实际编码场景做个对比测试——生成一个 Python 斐波那契生成器：

**DeepSeek Coder V2 (16B)**：
```python
def fibonacci(n: int) -> list[int]:
    """Generate first n Fibonacci numbers."""
    if n <= 0:
        return []
    fib = [0, 1]
    for _ in range(2, n):
        fib.append(fib[-1] + fib[-2])
    return fib[:n]
```
- 质量：⭐⭐⭐⭐⭐ 代码规范，类型提示完善
- 速度：4-6 秒（VPS 4核）

**Qwen2.5 Coder (7B)**：
- 质量：⭐⭐⭐⭐ 代码基本正确，偶尔有小错
- 速度：2-3 秒（VPS 4核）

> 日常开发中，7B 模型的体验已经足够好。16B 模型更适合复杂的算法和架构任务。

## 常见问题

### Q: 网络延迟会不会很明显？

A: 取决于 VPS 地理位置。如果你的 VPS 在邻近区域（比如你在国内、VPS 在香港/日本），延迟约 10-30ms。配合流式输出（Continue 默认支持），打字时几乎无感知。

### Q: 同时使用多个 IDE 可以吗？

A: 可以。Ollama 支持多个并发请求，每个 IDE 实例配置不同的 `apiBase` 指向同一个 VPS 即可。

### Q: 代码会被 VPS 存储吗？

A: Ollama 只处理推理，不存储输入/输出。你发送的代码片段仅在 RAM 中处理，推理完成即丢弃。如有更高安全要求，可在 VPS 上启用全盘加密。

### Q: 如何更换模型？

A: 只需 `ollama pull` 新模型，然后在 Continue 配置中修改 `model` 字段，无需重启任何服务。

## 总结

通过 VPS + Ollama + Continue.dev 搭建私有 AI 编程助手，你获得的是：

- ✅ **完全的数据隐私**——代码永不离开你的网络
- ✅ **免费的 AI 补全**——只需付 VPS 月费
- ✅ **模型自由**——随时切换任意开源模型
- ✅ **团队共享**——一个 VPS 服务整个团队
- ✅ **可审计**——完全开源，无黑箱操作

相比 GitHub Copilot 和 Cursor 每月 $10-20 的费用，一台 €3.99/月的 VPS 就能提供同等甚至更好的体验。更重要的是——你的代码始终在你自己手里。

**下一步行动**：马上 SSH 到你的 VPS，`curl -fsSL https://ollama.ai/install.sh | sh`，然后 `ollama pull qwen2.5-coder:7b`，十分钟内就能拥有自己的 AI 编程助手。
