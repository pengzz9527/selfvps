---
title: "ActivePieces 自托管工作流自动化：免费替代 Make/Zapier，年省 $600+"
description: "用 ActivePieces 在 VPS 上搭建可视化工作流自动化平台，零代码连接 200+ 应用，完全免费无执行次数限制，替代 Make($19/月起)和 Zapier($20/月起)，年省 $600+。"
date: 2026-09-18T10:00:00+08:00
lastmod: 2026-09-18T10:00:00+08:00
slug: "activepieces-selfhosted-workflow-automation"
image: /images/posts/activepieces-selfhosted-workflow-automation/featured.png
tags: ["ActivePieces", "自动化", "工作流", "Make", "Zapier", "Docker", "自托管", "零成本", "省钱"]
categories: ["工具测评", "自托管"]
aliases: [/zh/post/activepieces-selfhosted-workflow-automation/]
---

## 为什么要自建工作流自动化？

你是否有过这样的场景：

> 每当收到邮件中的发票 → 自动保存到 Google Drive → 同步到 Notion → 发通知到 Slack？

或者更日常的：

> 用户注册了你的网站 → 自动发送欢迎邮件 → 创建用户档案 → 加入 Mailchimp 列表 → 在 CRM 中记录？

这些重复性工作如果用 **Zapier** 或 **Make**（原 Integromat）来做，免费版有严格的执行次数限制——Zapier 免费版每月 100 次，Make 免费版每月 1,000 次操作。一旦你的业务增长，付费方案轻松达到 **$19~$59/月**。

**ActivePieces** 是这一切的完美替代方案——**开源、免费、自托管、无执行次数限制**。同样的工作流，在本地运行，数据完全在你手中，每月花费 **$0**。

---

## ActivePieces vs Make vs Zapier 费用对比

| 功能 | ActivePieces（自托管） | Make（标准版） | Zapier（Professional） |
|------|----------------------|---------------|----------------------|
| 月费 | **$0** | $9/月（$108/年） | $29/月（$348/年） |
| 任务执行次数 | **无限** | 10,000/月 | 750,000/月 |
| 多步骤工作流 | ✅ | ✅ | ✅ |
| 条件分支/循环 | ✅ | ✅ | ✅（付费） |
| 自定义代码块 | ✅ JavaScript | ✅ JavaScript | ✅ Python/JS |
| 200+ 应用集成 | ✅ | ✅ | ✅ |
| 数据隐私 | **完全私有** | 第三方服务器 | 第三方服务器 |
| Webhook 触发 | ✅ | ✅ | ✅ |
| 定时触发器 | ✅ | ✅ | ✅ |
| 团队权限管理 | ✅ | ✅ | ✅（付费） |
| API 访问 | ✅ | ✅ | ✅（付费） |

**每年节省：$108 ~ $348+**（仅软件费用，还不算隐私和数据控制权的价值）

---

## 核心架构一览

```
┌─────────────────────────────────────────────────────┐
│                   你的 VPS / 本地服务器              │
│                                                     │
│  ┌──────────┐    ┌──────────────┐    ┌──────────┐  │
│  │  Nginx   │───▶│ ActivePieces │───▶│  PostgreSQL│ │
│  │  Reverse │    │   (Node.js)  │    │  (存储)   │  │
│  │  Proxy   │    │  :3000       │    └──────────┘  │
│  └────┬─────┘    └──────┬───────┘          ▲       │
│       │                 │                  │       │
│       ▼                 ▼                  │       │
│  ┌──────────┐    ┌──────────────┐         │       │
│  │  TLS     │    │   Redis      │─────────┘       │
│  │  (证书)  │    │  (队列)      │                 │
│  └──────────┘    └──────────────┘                 │
│                                                    │
│  ┌──────────────────────────────────────────┐     │
│  │         外部服务触发 & 回调               │     │
│  │  Gmail · Notion · Slack · Google Drive   │     │
│  │  GitHub · Telegram · Discord · HTTP      │     │
│  │  + 200+ 更多应用                          │     │
│  └──────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────┘
```

---

## 第一步：一键 Docker Compose 部署

这是最简单的部署方式，10 分钟完成从 0 到可用。

### 1. 创建工作目录

```bash
mkdir -p ~/activepieces && cd ~/activepieces
```

### 2. 创建 docker-compose.yml

```yaml
services:
  activepieces:
    image: ghcr.io/activepieces/activepieces:latest
    restart: unless-stopped
    ports:
      - "5050:80"
    environment:
      AP_ENGINE_EXECUTABLE_PATH: "dist/main"
      AP_ENCRYPTION_KEY: "your-random-32-char-key-here"
      AP_JWT_SECRET: "your-random-jwt-secret"
      AP_FRONTEND_URL: "https://flows.yourdomain.com"
      AP_BACKEND_URL: "http://localhost:5050"
      AP_EXECUTION_MODE: "FULL"
      AP_REDIS_HOST: "redis"
      AP_POSTGRES_HOST: "postgres"
      AP_POSTGRES_PORT: "5432"
      AP_POSTGRES_DATABASE: "activepieces"
      AP_POSTGRES_USER: "postgres"
      AP_POSTGRES_PASSWORD: "your-strong-password"
      AP_TELEMETRY_ENABLED: "true"
    depends_on:
      redis:
        condition: service_healthy
      postgres:
        condition: service_healthy

  redis:
    image: redis:7-alpine
    restart: unless-stopped
    command: redis-server --appendonly yes
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  postgres:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_DB: activepieces
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: "your-strong-password"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  redis_data:
  postgres_data:
```

### 3. 启动服务

```bash
docker compose up -d
```

### 4. 验证部署

```bash
# 查看容器状态
docker compose ps

# 查看日志
docker compose logs -f activepieces
```

看到 `Application is ready!` 即表示部署成功。

---

## 第二步：配置 Nginx 反向代理 + HTTPS

ActivePieces 需要 HTTPS 才能正常运作（用于 OAuth 回调和 Webhook）。

### 创建 Nginx 配置

```nginx
server {
    listen 80;
    server_name flows.yourdomain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name flows.yourdomain.com;

    ssl_certificate     /etc/nginx/ssl/flows.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/nginx/ssl/flows.yourdomain.com/privkey.pem;

    # 安全头
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # 超时设置（长轮询需要）
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;
    send_timeout 3600s;

    location / {
        proxy_pass http://127.0.0.1:5050;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # WebSocket 支持
    location /ws {
        proxy_pass http://127.0.0.1:5050;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }
}
```

### 用 Certbot 申请免费 SSL 证书

```bash
# 安装 certbot
apt install certbot python3-certbot-nginx -y

# 申请证书（先临时开 80 端口让 certbot 验证）
certbot certonly --standalone -d flows.yourdomain.com

# 创建 SSL 目录并复制证书
mkdir -p /etc/nginx/ssl/flows.yourdomain.com
cp /etc/letsencrypt/live/flows.yourdomain.com/fullchain.pem \
   /etc/nginx/ssl/flows.yourdomain.com/
cp /etc/letsencrypt/live/flows.yourdomain.com/privkey.pem \
   /etc/nginx/ssl/flows.yourdomain.com/
```

### 启用站点并重启 Nginx

```bash
ln -s /etc/nginx/sites-available/activepieces \
       /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
```

---

## 第三步：创建你的第一个自动化工作流

### 场景：新邮件附件自动保存到 Google Drive

#### 1. 创建触发器（Trigger）

登录 `https://flows.yourdomain.com`，点击 **"New Piece"** → 选择 **"Schedule"** 触发器：

- **类型**：Polling（轮询模式）
- **频率**：每 5 分钟检查一次
- **应用**：Gmail

#### 2. 配置 Gmail 触发器

```
触发条件：
- 收件箱中有新邮件
- 包含附件
- 来自特定发件人（可选）
```

#### 3. 添加动作（Action）：保存到 Google Drive

```
动作：Google Drive → 上传文件
- 来源：Gmail 附件
- 目标文件夹：/AutoPieces/Email-Attachments
- 文件命名：{日期}_{发件人}_{文件名}
```

#### 4. 添加第二个动作：发送 Telegram 通知

```
动作：Telegram → 发送消息
- 聊天 ID：你的 Telegram Chat ID
- 消息：📎 新邮件附件已保存
  文件名：{{attachments.0.name}}
  大小：{{attachments.0.size}}
  链接：{{drive_link}}
```

#### 5. 保存并启用工作流

点击右上角 **"Save & Turn On"**，工作流即刻开始运行。

---

## 进阶：使用 ActivePieces 自建 CI/CD 通知系统

### 场景：GitHub Push 事件 → 自动通知多个渠道

```
触发器：GitHub Webhook（Push 事件）
    │
    ├─→ 动作1：解析 commit 信息
    │         （JavaScript 代码片段）
    │
    ├─→ 动作2a：发送 Telegram 通知
    │
    ├─→ 动作2b：发送 Slack 消息
    │
    └─→ 动作2c：更新 Google Sheets 记录
```

### GitHub Webhook 配置

1. 在 GitHub 仓库 Settings → Webhooks → Add webhook
2. Payload URL：`https://flows.yourdomain.com/api/v1/hook/github`
3. Content type：`application/json`
4. Secret：设置一个密钥用于验证

### JavaScript 代码片段示例

在 ActivePieces 中可以直接写 JavaScript 处理数据：

```javascript
// 解析 GitHub push 事件
const push = params.body;
const repo = push.repository.full_name;
const branch = push.ref.replace('refs/heads/', '');
const commits = push.commits;

// 格式化输出
const commitList = commits.map(c => 
  `• ${c.message.split('\n')[0].substring(0, 50)}`
).join('\n');

return {
  repo,
  branch,
  author: push.pusher.name,
  commitCount: commits.length,
  commits: commitList
};
```

---

## 费用计算：自托管 vs SaaS

假设你每月需要：
- 500 次任务执行
- 3 个多步骤工作流
- 5 个应用集成

| 方案 | 月费 | 年费 | 备注 |
|------|------|------|------|
| **ActivePieces（自托管）** | **$0** | **$0** | 仅需 VPS 费用 |
| Make（Standard） | $9 | $108 | 10K ops/月 |
| Make (Premium) | $29 | $348 | 100K ops/月 |
| Zapier (Professional) | $29 | $348 | 750K ops/月 |
| Zapier (Team) | $166 | $1,992 | 2000K ops/月 |

**结论**：只要你的 VPS 还有余量，ActivePieces 就是免费的。即使单独为一台轻量 VPS 付费（$5/月），也比 Make/Zapier 便宜 80%+，而且获得的是无限执行次数 + 完全的数据隐私。

---

## 常见问题

### Q：ActivePieces 和 n8n 有什么区别？

两者都是优秀的自托管工作流自动化工具，主要区别：
- **ActivePieces**：更轻量，上手更快，UI 更简洁，适合中小型工作流
- **n8n**：功能更丰富，节点更多，适合复杂的企业级场景
- **许可**：ActivePieces 使用 MIT 协议（完全开放），n8n 使用 Sustainable Use License

### Q：是否需要域名？

**建议有**，因为很多应用的 OAuth 回调需要 HTTPS 域名。如果你只是内部使用，可以用 IP + 自签名证书，但会失去部分集成能力。

### Q：VPS 最低配置要求？

- CPU：1 vCPU
- 内存：**1GB RAM**（推荐 2GB）
- 磁盘：10GB
- 网络：需要出站互联网访问（用于调用外部 API）

### Q：数据安全性如何？

所有数据（工作流配置、执行日志、认证 token）都存储在你自己的数据库中。相比 SaaS 方案，你避免了：
- 第三方服务器上的数据泄露风险
- 服务商停机导致工作流中断
- 服务商变更定价策略的风险

---

## 总结

ActivePieces 是目前自托管工作流自动化领域最值得推荐的方案之一：

- ✅ **完全免费**，无执行次数限制
- ✅ **Docker 一键部署**，10 分钟上线
- ✅ **200+ 应用原生集成**，可视化拖拽
- ✅ **JavaScript 扩展**，满足自定义需求
- ✅ **MIT 开源协议**，可二次开发
- ✅ **年省 $100~$2000+**（取决于替代的 SaaS 方案）

对于任何已经在 VPS 上运行服务的用户来说，部署 ActivePieces 几乎是零额外成本的——你的 VPS 本来就有余量。现在就试试吧！

---

*本文发布于 [SelfVPS](https://selfvps.net/zh/) —— 专注自托管与云服务省钱指南*
