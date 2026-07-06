---
title: "GoTrue 自托管用户认证系统：Supabase Auth 的开源替代方案"
description: "从零开始在 VPS 上部署 GoTrue 认证服务 —— Supabase Auth 的开源引擎，支持 OAuth、邮件验证码、MFA 等企业级功能，完全掌控你的用户数据。"
date: 2026-07-06T10:00:00+08:00
lastmod: 2026-07-06T10:00:00+08:00
slug: "gotrue-selfhosted-auth-guide"
tags: ["GoTrue", "Supabase", "认证", "OAuth", "自托管", "Docker", "用户管理", "安全"]
categories: ["部署教程"]
draft: false
image: /images/posts/gotrue-selfhosted-auth-guide/featured.png
aliases: [/zh/post/gotrue-selfhosted-auth-guide/]
---

## 为什么需要自托管认证？

在构建自托管应用时，用户认证是最基础也最容易被忽视的组件。大多数开发者要么重复造轮子——手写 JWT 验证和会话管理，要么依赖第三方服务如 Firebase Auth、Auth0 或 Supabase Auth。但这些服务各有局限：

- **Firebase Auth**：锁定严重，自定义能力有限
- **Auth0**：免费版限制严格，价格随用户增长快速攀升
- **Supabase Auth**：方便但数据存储在 Supabase 云上，无法完全掌控

**GoTrue** 是 Supabase Auth 的开源核心引擎，用 Go 编写，支持 Docker 部署。它提供完整的认证功能，却可以完全运行在你的基础设施上。

## GoTrue 核心功能

| 功能 | 说明 |
|------|------|
| JWT 令牌管理 | 签发、验证、刷新访问令牌和刷新令牌 |
| 邮箱密码注册 | 支持邮箱注册、登录、密码重置 |
| 邮件验证码 | 无需密码，通过邮件链接或验证码登录 |
| OAuth 社交登录 | Google、GitHub、GitLab、Discord 等 20+ 提供商 |
| MFA（多因素认证） | TOTP、短信等多种第二因素验证方式 |
| 用户管理 API | 创建、更新、删除用户的 RESTful API |
| 角色权限 | 基于角色的访问控制（RBAC）基础支持 |
| SAML/SSO | 企业级单点登录支持 |

## 架构概览

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   Client     │────▶│  GoTrue      │────▶│   PostgreSQL│
│ (Web/Mobile) │◀────│  Auth Server │◀────│   Database  │
└─────────────┘     └──────────────┘     └─────────────┘
                          │
                          ▼
                   ┌──────────────┐
                   │   SMTP       │
                   │   Server     │
                   └──────────────┘
```

GoTrue 依赖三个核心组件：
1. **GoTrue 服务**：认证逻辑的核心
2. **PostgreSQL**：存储用户数据和会话信息
3. **SMTP 服务器**：发送验证邮件

## 完整部署指南

### 第一步：准备 Docker Compose 文件

创建 `docker-compose.yml`：

```yaml
version: '3.8'

services:
  gotrue:
    image: ghcr.io/supabase/gotrue:v2.158.1
    container_name: gotrue
    restart: unless-stopped
    ports:
      - "9999:9999"
    environment:
      # GoTrue 主密钥（生产环境务必修改！）
      GOTRUE_DB_DRIVER: postgres
      GOTRUE_DB_DATABASE_URL: "postgresql://supabase_gotrue:supabase_gotrue_password@db:5432/postgres"
      
      # JWT 配置
      GOTRUE_JWT_ADMIN_ROLES: "admin"
      GOTRUE_JWT_AUD: "authenticated"
      GOTRUE_JWT_EXP: "3600"
      GOTRUE_JWT_SECRET: "your-super-secret-jwt-token-with-at-least-32-characters-long"
      
      # API 配置
      GOTRUE_API_HOST: "0.0.0.0"
      GOTRUE_API_PORT: 9999
      GOTRUE_API_RATE_LIMIT_HEADER: "X-Forwarded-For"
      GOTRUE_API_RATE_LIMIT: "100"
      
      # SMTP 邮件配置
      GOTRUE_MAILER_AUTOCONFIRM: "false"
      GOTRUE_SMTP_HOST: "smtp.your-email-provider.com"
      GOTRUE_SMTP_PORT: "587"
      GOTRUE_SMTP_USER: "your-smtp-user"
      GOTRUE_SMTP_PASS: "your-smtp-password"
      GOTRUE_SMTP_ADMIN_EMAIL: "admin@yourdomain.com"
      GOTRUE_SMTP_SENDER_NAME: "Your App Name"
      
      # 站点 URL
      GOTRUE_SITE_URL: "https://auth.yourdomain.com"
      GOTRUE_URI_ALLOW_UPDATES: "true"
      
      # OAuth 配置（按需启用）
      GOTRUE_EXTERNAL_GITHUB_ENABLED: "true"
      GOTRUE_EXTERNAL_GITHUB_CLIENT_ID: "your-github-oauth-client-id"
      GOTRUE_EXTERNAL_GITHUB_SECRET: "your-github-oauth-client-secret"
      
      GOTRUE_EXTERNAL_GOOGLE_ENABLED: "true"
      GOTRUE_EXTERNAL_GOOGLE_CLIENT_ID: "your-google-oauth-client-id"
      GOTRUE_EXTERNAL_GOOGLE_SECRET: "your-google-oauth-client-secret"
      
      # 密码策略
      GOTRUE_PASSWORD_MIN_LENGTH: 8
      GOTRUE_ALLOW_SIGNUP_WITHOUT_EMAIL_VERIFICATION: "false"
      
      # CORS
      GOTRUE_EXTERNAL_REDIRECT_URLS: "https://yourdomain.com,https://app.yourdomain.com"
      
      # 邮件模板
      GOTRUE_MAILER_URLPATHS_INVITE: "/auth/callback"
      GOTRUE_MAILER_URLPATHS_CONFIRMATION: "/auth/callback"
      GOTRUE_MAILER_URLPATHS_RECOVERY: "/auth/callback"
      GOTRUE_MAILER_URLPATHS_EMAIL_CHANGE: "/auth/callback"

    depends_on:
      db:
        condition: service_healthy

  db:
    image: postgres:16-alpine
    container_name: gotrue-db
    restart: unless-stopped
    ports:
      - "5433:5432"
    environment:
      POSTGRES_DB: supabase_gotrue
      POSTGRES_USER: supabase_gotrue
      POSTGRES_PASSWORD: supabase_gotrue_password
      POSTGRES_INITDB_ARGS: "--auth-host=scram-sha-256"
    volumes:
      - gotrue_db_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U supabase_gotrue -d supabase_gotrue"]
      interval: 5s
      timeout: 5s
      retries: 5

volumes:
  gotrue_db_data:
    driver: local
```

### 第二步：配置环境变量

在生产环境中，**绝对不要**将敏感信息硬编码在 docker-compose.yml 中。改用 `.env` 文件：

```bash
# .env
GOTRUE_JWT_SECRET=$(openssl rand -base64 32)
GOTRUE_DB_DATABASE_URL=postgresql://user:password@db:5432/dbname
GOTRUE_SMTP_PASS=your-smtp-password
GOTRUE_EXTERNAL_GITHUB_SECRET=your-github-secret
GOTRUE_EXTERNAL_GOOGLE_SECRET=your-google-secret
```

然后在 docker-compose.yml 中使用变量引用：

```yaml
environment:
  GOTRUE_JWT_SECRET: ${GOTRUE_JWT_SECRET}
  GOTRUE_SMTP_PASS: ${GOTRUE_SMTP_PASS}
```

### 第三步：启动服务

```bash
docker compose up -d
```

等待数据库初始化完成（约 30 秒），然后验证服务：

```bash
# 检查 GoTrue 是否正常运行
curl http://localhost:9999/health

# 预期响应: {"status":"OK"}
```

## 配置 OAuth 社交登录

### GitHub OAuth 配置

1. 前往 [GitHub Developer Settings](https://github.com/settings/developers)
2. 创建新的 OAuth App
3. 设置 Authorization callback URL 为 `https://auth.yourdomain.com/auth/callback`
4. 获取 Client ID 和 Client Secret

```yaml
environment:
  GOTRUE_EXTERNAL_GITHUB_ENABLED: "true"
  GOTRUE_EXTERNAL_GITHUB_CLIENT_ID: "${GITHUB_CLIENT_ID}"
  GOTRUE_EXTERNAL_GITHUB_SECRET: "${GITHUB_CLIENT_SECRET}"
  GOTRUE_EXTERNAL_GITHUB_REDIRECT_URI: "https://auth.yourdomain.com/auth/callback"
```

### Google OAuth 配置

1. 前往 [Google Cloud Console](https://console.cloud.google.com/)
2. 创建 OAuth 2.0 凭据
3. 添加授权重定向 URI：`https://auth.yourdomain.com/auth/callback`
4. 获取 Client ID 和 Client Secret

```yaml
environment:
  GOTRUE_EXTERNAL_GOOGLE_ENABLED: "true"
  GOTRUE_EXTERNAL_GOOGLE_CLIENT_ID: "${GOOGLE_CLIENT_ID}"
  GOTRUE_EXTERNAL_GOOGLE_SECRET: "${GOOGLE_CLIENT_SECRET}"
  GOTRUE_EXTERNAL_GOOGLE_REDIRECT_URI: "https://auth.yourdomain.com/auth/callback"
```

## 与前端应用集成

### 使用 GoTrue JS SDK

```bash
npm install @supabase/gotrue-js
```

```javascript
import { GoTrueClient } from '@supabase/gotrue-js';

const client = new GoTrueClient({
  url: 'http://localhost:9999',
});

// 邮箱注册
async function signUp(email, password) {
  const { data, error } = await client.signUp({
    email,
    password,
  });
  if (error) throw error;
  return data;
}

// 邮箱登录
async function signIn(email, password) {
  const { data, error } = await client.signInWithPassword({
    email,
    password,
  });
  if (error) throw error;
  return data;
}

// 使用刷新令牌
async function refreshSession(refreshToken) {
  const { data, error } = await client.refreshSession({ refreshToken });
  if (error) throw error;
  return data;
}

// 登出
async function signOut() {
  await client.signOut();
}
```

### 后端 API 集成示例（Node.js）

```javascript
const express = require('express');
const jwt = require('jsonwebtoken');

const app = express();
const GOTRUE_API_URL = 'http://localhost:9999';
const JWT_SECRET = process.env.GOTRUE_JWT_SECRET;

// 中间件：验证 JWT
function authenticate(req, res, next) {
  const token = req.headers.authorization?.split(' ')[1];
  if (!token) {
    return res.status(401).json({ error: '未授权' });
  }
  
  try {
    const decoded = jwt.verify(token, JWT_SECRET);
    req.user = decoded;
    next();
  } catch (err) {
    return res.status(401).json({ error: '令牌无效' });
  }
}

// 受保护的 API 端点
app.get('/api/protected', authenticate, (req, res) => {
  res.json({ 
    message: '认证成功', 
    userId: req.user.sub,
    email: req.user.email 
  });
});

app.listen(3000);
```

## 管理用户

### 使用 Admin API

GoTrue 提供了完整的用户管理 API。使用 admin token 可以执行管理操作：

```bash
# 列出所有用户
curl -X GET "http://localhost:9999/admin/users" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"

# 创建用户
curl -X POST "http://localhost:9999/admin/users" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "newuser@example.com",
    "password": "securepassword123",
    "app_metadata": {"role": "user"},
    "user_metadata": {"name": "New User"}
  }'

# 删除用户
curl -X DELETE "http://localhost:9999/admin/users/{user_id}" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"
```

### Admin Token 生成

Admin Token 是一个带有 `admin` 角色的 JWT：

```bash
# 使用 jwt-cli 生成（需要安装）
jwt sign -s "your-secret" -a '{"role":"admin"}'

# 或在代码中生成
const adminToken = jwt.sign(
  { role: 'admin', aud: 'authenticated' },
  process.env.GOTRUE_JWT_SECRET,
  { expiresIn: '1h' }
);
```

## 邮件配置详解

### 使用 Mailgun

```yaml
environment:
  GOTRUE_SMTP_HOST: "smtp.mailgun.org"
  GOTRUE_SMTP_PORT: "587"
  GOTRUE_SMTP_USER: "postmaster@yourdomain.mailgun.org"
  GOTRUE_SMTP_PASS: "your-mailgun-api-key"
  GOTRUE_SMTP_ADMIN_EMAIL: "admin@yourdomain.com"
  GOTRUE_SMTP_SENDER_NAME: "My App"
```

### 使用 SendGrid

```yaml
environment:
  GOTRUE_SMTP_HOST: "smtp.sendgrid.net"
  GOTRUE_SMTP_PORT: "587"
  GOTRUE_SMTP_USER: "apikey"
  GOTRUE_SMTP_PASS: "your-sendgrid-api-key"
  GOTRUE_SMTP_ADMIN_EMAIL: "admin@yourdomain.com"
  GOTRUE_SMTP_SENDER_NAME: "My App"
```

### 使用本地 Postfix

对于测试环境，可以使用本地 Postfix：

```yaml
services:
  postfix:
    image: tvial/docker-mailserver:latest
    container_name: postfix
    ports:
      - "25:25"
    environment:
      - MAIL_HOSTNAME=mail.local
      - MAIL_ENVFILE=/etc/mail/environment

  gotrue:
    environment:
      GOTRUE_SMTP_HOST: "postfix"
      GOTRUE_SMTP_PORT: "25"
      GOTRUE_SMTP_USER: ""
      GOTRUE_SMTP_PASS: ""
      GOTRUE_MAILER_AUTOCONFIRM: "true"  # 测试环境自动确认
```

## 自定义邮件模板

GoTrue 支持通过 API 自定义邮件模板。创建 `template.json`：

```json
{
  "invite": {
    "subject": "邀请加入 {{ .SiteURL }}",
    "body": "<p>你好 {{ .Email }}，</p><p>点击以下链接完成注册：</p><p><a href=\"{{ .ConfirmationURL }}\">确认注册</a></p>"
  },
  "confirmation": {
    "subject": "确认您的邮箱",
    "body": "<p>请点击以下链接确认您的邮箱地址：</p><p><a href=\"{{ .ConfirmationURL }}\">确认邮箱</a></p>"
  },
  "recovery": {
    "subject": "重置密码",
    "body": "<p>请点击以下链接重置密码：</p><p><a href=\"{{ .RecoveryURL }}\">重置密码</a></p>"
  },
  "email_change": {
    "subject": "确认邮箱变更",
    "body": "<p>请点击以下链接确认邮箱变更：</p><p><a href=\"{{ .EmailChangeConfirmUrl }}\">确认变更</a></p>"
  }
}
```

然后通过 API 上传模板：

```bash
curl -X PUT "http://localhost:9999/admin/settings" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "mailer": {
      "templates": {
        "invite": {"subject": "...", "body": "..."},
        "confirmation": {"subject": "...", "body": "..."}
      }
    }
  }'
```

## 生产环境最佳实践

### 1. 使用反向代理

在生产环境中，建议通过 Nginx 或 Caddy 反向代理访问 GoTrue：

```nginx
server {
    listen 443 ssl http2;
    server_name auth.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/auth.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/auth.yourdomain.com/privkey.pem;

    location / {
        proxy_pass http://localhost:9999;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### 2. 启用 HTTPS

GoTrue 不直接处理 TLS，所有 HTTPS 终止应在反向代理层面完成。

### 3. 数据库备份

```bash
# 每日自动备份
0 2 * * * docker exec gotrue-db pg_dump -U supabase_gotrue supabase_gotrue | gzip > /backups/gotrue_$(date +\%Y\%m\%d).sql.gz
```

### 4. 资源限制

```yaml
services:
  gotrue:
    deploy:
      resources:
        limits:
          cpus: '1.0'
          memory: 512M
        reservations:
          cpus: '0.25'
          memory: 128M
```

### 5. 健康检查和监控

```yaml
services:
  gotrue:
    healthcheck:
      test: ["CMD", "wget", "--spider", "-q", "http://localhost:9999/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s
```

### 6. 速率限制

GoTrue 内置了速率限制，但建议在反向代理层面也做一层：

```nginx
limit_req_zone $binary_remote_addr zone=auth_limit:10m rate=10r/s;

location /auth/signup {
    limit_req zone=auth_limit burst=20 nodelay;
    proxy_pass http://localhost:9999;
}
```

## 常见问题

### Q1: 收不到验证邮件？

1. 检查 SMTP 配置是否正确
2. 查看 GoTrue 日志：`docker logs gotrue`
3. 确认 `GOTRUE_MAILER_AUTOCONFIRM` 在生产环境中设为 `"false"`
4. 检查防火墙是否阻止了出站 SMTP 连接

### Q2: OAuth 回调失败？

1. 确认 callback URL 完全匹配（包括末尾斜杠）
2. 检查 OAuth 应用的 redirect URI 设置
3. 验证 `GOTRUE_EXTERNAL_REDIRECT_URLS` 包含你的域名

### Q3: 如何迁移现有用户到 GoTrue？

```bash
# 批量导入用户
curl -X POST "http://localhost:9999/admin/users" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password_hash": "$2b$12$...",
    "email_verified": true,
    "phone_verified": false
  }'
```

使用 bcrypt 哈希密码后导入，不要直接导入明文密码。

### Q4: GoTrue 和 Supabase 的关系？

GoTrue 是 Supabase Auth 的底层引擎。Supabase 在 GoTrue 之上添加了：
- Supabase CLI 工具
- 管理界面
- 与 Supabase 其他服务（Realtime、Storage）的集成
- 额外的管理 API

如果你只需要认证功能，GoTrue 是更轻量、更独立的选择。

## 与其他认证方案对比

| 特性 | GoTrue | Firebase Auth | Auth0 | Keycloak |
|------|--------|--------------|-------|----------|
| 部署复杂度 | ⭐⭐ 低 | ⭐ 无需部署 | ⭐ 无需部署 | ⭐⭐⭐⭐ 高 |
| 自定义程度 | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| OAuth 支持 | ✅ 丰富 | ✅ 基本 | ✅ 丰富 | ✅ 丰富 |
| MFA | ✅ 支持 | ✅ 支持 | ✅ 支持 | ✅ 支持 |
| 资源占用 | ~100MB | N/A | N/A | ~1GB+ |
| 学习曲线 | 中等 | 低 | 中等 | 陡峭 |
| 社区活跃度 | 高 | 极高 | 高 | 高 |

## 总结

GoTrue 为自托管应用提供了一个强大、灵活且轻量的认证解决方案。它继承了 Supabase Auth 的所有核心功能，同时让你完全掌控用户数据和基础设施。

**关键要点：**
- 使用 Docker 一键部署，配合 PostgreSQL 持久化数据
- 支持完整的 OAuth 社交登录生态
- 通过 Admin API 实现用户管理和批量操作
- 生产环境务必配置 HTTPS、备份和监控
- 与前端 JS SDK 无缝集成，开发体验优秀

通过自托管认证服务，你不仅节省了第三方服务的费用，更重要的是获得了数据的完全控制权——这在合规性要求严格的场景中尤为重要。
