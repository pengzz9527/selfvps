---
title: "自建邮件发送服务：用 Gmail API 从 VPS 免费发送邮件"
description: "手把手教你用 Gmail API 从 VPS 免费发送邮件——系统监控告警、服务通知、密码找回，告别付费邮件服务商"
date: 2026-05-23T10:00:00+08:00
lastmod: 2026-05-23T10:00:00+08:00
slug: "self-hosted-email-gmail-api"
image: /images/posts/self-hosted-email-gmail-api/featured.png
tags: ["Gmail", "邮件", "自托管", "云省钱", "运维", "API", "自动化"]
categories: ["云省钱"]
aliases: [/zh/post/self-hosted-email-gmail-api/]
---

## 引言

运行 VPS 后，一个有"发送邮件"能力的服务器才算是真正"活"起来的。系统告警通知、SSL 证书到期提醒、备份失败报告、用户注册验证——这些都需要邮件送达能力。

市面上有 SendGrid、Mailgun、Resend 等服务，但它们要么有额度限制，要么需要绑定信用卡才开始计费。**而 Gmail API 是完全免费的**：每个 Google 账号每天可发送 100 封邮件，完全够个人/VPS 运维使用。

本文教你从零搭建 Gmail API 邮件发送服务，支持 Python 脚本和 Shell 脚本两种方式，让你彻底告别第三方邮件服务的付费账单。

---

## 1. 为什么选择 Gmail API？

| 方案 | 费用 | 每日限额 | 设置复杂度 |
|------|------|----------|-----------|
| **Gmail API** | 免费 | 100 封/天 | ⭐⭐ |
| SendGrid 免费版 | 免费 | 100 封/天 | ⭐⭐ |
| Mailgun 免费版 | 免费 | 100 封/天 | ⭐⭐⭐ |
| SMTP 直接搭建 | 免费 | 无限制 | ⭐⭐⭐⭐⭐ |
| Amazon SES | 按量付费 | 200 封/天(沙盒) | ⭐⭐⭐ |

Gmail API 的优势在于：
- **零成本**：不用绑定信用卡，直接用你的 Google 账号
- **高送达率**：Gmail 的 IP 信誉极佳，不会进垃圾箱
- **支持标签**：可自动在 Gmail 中归类，便于管理
- **无需维护**：Google 负责基础设施，你只管发信

> ⚠️ **注意**：如果你需要发送大量营销邮件（如 newsletter），Gmail API 不是好选择——别用个人 Gmail 账号做群发，会触发风控。本文场景是**运维通知和事务性邮件**。

---

## 2. 准备工作：开通 Google Cloud 项目

### 2.1 创建项目

1. 打开 [Google Cloud Console](https://console.cloud.google.com/)
2. 点击顶部项目下拉菜单 → **新建项目**
3. 项目名称输入 `VPS Email Sender`（随意命名），点击创建
4. 等待项目创建完成后，确保当前选中了该项目

### 2.2 启用 Gmail API

1. 进入左侧菜单 **API 和服务 → 库**
2. 搜索 **Gmail API**
3. 点击进入 → 点击 **启用**

### 2.3 配置 OAuth 同意屏幕

1. 进入 **API 和服务 → OAuth 同意屏幕**
2. 选择 **外部用户（External）**→ 创建
3. 填写：
   - **应用名称**：VPS Email Sender
   - **用户支持邮箱**：你的邮箱
   - **开发者联系信息**：你的邮箱
4. 跳过 **Scopes** 步骤（点"保存并继续"）
5. **测试用户**：添加你的 Gmail 地址（否则只有你自己能授权）
6. 点 **返回摘要** → 发布应用（设为"发布到生产环境"）

### 2.4 创建凭据

1. 进入 **API 和服务 → 凭据**
2. 点 **创建凭据 → OAuth 客户端 ID**
3. 应用类型选择 **桌面应用（Desktop application）**
4. 名称输入 `VPS Email Client`
5. 创建后，点击 **下载 JSON**，保存为 `credentials.json`

---

## 3. 安装依赖并发送第一封邮件

### 3.1 服务端设置

在 VPS 上安装 Python 依赖：

```bash
pip install --upgrade google-api-python-client google-auth-httplib2 google-auth-oauthlib
```

### 3.2 授权脚本

创建一个授权脚本，在你的本地机器上运行一次，生成 token 文件：

```python
# quickstart.py
import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ['https://www.googleapis.com/auth/gmail.send']

def authenticate():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return creds

if __name__ == '__main__':
    authenticate()
    print("✅ 授权成功！token.json 已生成")
```

运行这个脚本（**在本地电脑上**，因为需要打开浏览器）：

```bash
python3 quickstart.py
```

浏览器会弹出 Google 登录页面，授权后会在当前目录生成 `token.json`。

> 💡 **小技巧**：如果 VPS 没有图形界面，可以在本地运行授权，然后将 `token.json` 和 `credentials.json` 通过 `scp` 传到 VPS。

### 3.3 发信脚本

把 `token.json` 上传到 VPS 后，使用以下脚本发送邮件：

```python
# send_email.py
import base64
import os
import sys
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from email.mime.text import MIMEText

SCOPES = ['https://www.googleapis.com/auth/gmail.send']

def get_service():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            raise Exception("Token 无效，请重新运行授权")
    return build('gmail', 'v1', credentials=creds)

def send_email(to, subject, body):
    service = get_service()
    message = MIMEText(body, 'plain', 'utf-8')
    message['To'] = to
    message['Subject'] = subject
    # 默认用已授权账号的邮箱发信（即 YOUR_EMAIL@gmail.com）
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    
    try:
        result = service.users().messages().send(
            userId='me', body={'raw': raw}
        ).execute()
        print(f"✅ 发送成功！Message ID: {result['id']}")
        return True
    except HttpError as error:
        print(f"❌ 发送失败: {error}")
        return False

if __name__ == '__main__':
    to = sys.argv[1] if len(sys.argv) > 1 else input("收件人: ")
    subject = sys.argv[2] if len(sys.argv) > 2 else "测试邮件"
    body = sys.argv[3] if len(sys.argv) > 3 else "这是一封通过 Gmail API 发送的测试邮件。"
    send_email(to, subject, body)
```

测试发送：

```bash
python3 send_email.py "your-email@gmail.com" "Gmail API 测试" "Hello! 这是从我的 VPS 发出的邮件 🎉"
```

---

## 4. 高级用法：Shell 脚本发送

对于系统脚本和 crontab 任务，可以封装一个简单的 Shell 包装脚本：

```bash
#!/bin/bash
# send_email.sh — 用 Gmail API 发送邮件
# 用法: ./send_email.sh "收件人" "主题" "正文"

TO="$1"
SUBJECT="$2"
BODY="$3"

python3 -c "
import sys
sys.path.insert(0, '/opt/email-sender')
from send_email import send_email
send_email('$TO', '$SUBJECT', '$BODY')
"
```

把它加入 crontab，实现系统监控告警：

```bash
# 每天上午8点检查 SSL 证书
0 8 * * * /opt/scripts/check_ssl.sh || /opt/email-sender/send_email.sh "admin@example.com" "⚠️ SSL 证书即将过期" "$(date): 证书检测异常，请检查"

# 每月1号发送 VPS 账单汇总
0 9 1 * * /opt/scripts/summary.sh && /opt/email-sender/send_email.sh "admin@example.com" "📊 月度 VPS 报告" "$(cat /tmp/monthly_report.txt)"
```

---

## 5. 实战案例：系统监控告警集成

### 5.1 磁盘空间告警

```bash
#!/bin/bash
# disk_alert.sh
THRESHOLD=85
USAGE=$(df -h / | awk 'NR==2 {print $5}' | sed 's/%//')

if [ "$USAGE" -ge "$THRESHOLD" ]; then
    /opt/email-sender/send_email.sh \
        "admin@example.com" \
        "🚨 磁盘空间告警: 已使用 ${USAGE}%" \
        "服务器: $(hostname)\n时间: $(date)\n当前磁盘使用率: ${USAGE}%\n\n$(df -h)"
fi
```

加入 crontab 每小时检查一次：

```bash
0 * * * * /opt/scripts/disk_alert.sh
```

### 5.2 Docker 容器重启通知

```bash
#!/bin/bash
# docker_restart_notify.sh
RESTARTED=$(docker ps -a --filter "status=exited" --format "{{.Names}} {{.Status}}" | head -5)
if [ -n "$RESTARTED" ]; then
    /opt/email-sender/send_email.sh \
        "admin@example.com" \
        "🔄 Docker 容器异常退出" \
        "以下容器已退出:\n\n$RESTARTED\n\n请及时排查。"
fi
```

### 5.3 Nginx 错误日志监控

```bash
#!/bin/bash
# nginx_error_monitor.sh
ERRORS=$(tail -n 50 /var/log/nginx/error.log | grep -iE "error|critical|alert" | tail -10)
if [ -n "$ERRORS" ]; then
    /opt/email-sender/send_email.sh \
        "admin@example.com" \
        "⚠️ Nginx 发现错误" \
        "最近 Nginx 错误日志:\n\n$ERRORS"
fi
```

---

## 6. 安全与优化

### 6.1 Token 管理
- `token.json` 相当于你的邮箱密钥——**绝对不要提交到 GitHub**
- 建议存放路径：`/opt/email-sender/token.json`
- 权限设置：`chmod 600 /opt/email-sender/token.json`
- 使用 `git-crypt` 或 `sops` 加密存储

### 6.2 速率限制
Gmail API 的限额：
- 每天 100 封（免费账号）
- 每 100 秒最多 10 封
- 超过限制会返回 `429 Too Many Requests`

建议在脚本中加入重试机制：

```python
import time
from googleapiclient.errors import HttpError

def send_with_retry(service, body, max_retries=3):
    for attempt in range(max_retries):
        try:
            return service.users().messages().send(
                userId='me', body=body
            ).execute()
        except HttpError as e:
            if e.resp.status == 429 and attempt < max_retries - 1:
                wait = 2 ** attempt
                print(f"⚠️ 触发限流，等待 {wait} 秒后重试...")
                time.sleep(wait)
            else:
                raise
    return None
```

### 6.3 多账号轮询
如果需要超过 100 封/天的额度，可以准备多个 Gmail 账号，轮流发送：

```python
TOKENS = ['token1.json', 'token2.json', 'token3.json']
current = 0

def get_next_token():
    global current
    token = TOKENS[current % len(TOKENS)]
    current += 1
    return token
```

---

## 7. 常见问题排错

### ❌ `Token has been expired or revoked`
**原因**：token 过期或被撤销
**解决**：删除旧的 `token.json`，重新运行授权流程

### ❌ `Access blocked: XXXXXXXXX`
**原因**：Google 的安全检测
**解决**：确保 OAuth 应用已发布（设为"生产环境"），测试用户已添加

### ❌ `Recipient address rejected`
**原因**：收件人地址格式错误或不存在
**解决**：检查收件人邮箱地址是否正确

### ❌ 邮件进了 Gmail 垃圾箱
**原因**：IP 信誉或内容被标记
**解决**：
- 添加 SPF/DKIM 记录（如果使用自定义域名发信）
- 避免使用过多 URL
- 不用敏感关键词（如"urgent"、"free"等营销词）

---

## 总结

通过 Gmail API 发送邮件是 VPS 运维中最实惠、最可靠的方案之一。整个过程无需任何费用，只需花费 15 分钟配置一次，就能让服务器的监控和通知体系运转起来。

**关键要点**：
- ✅ 免费：0 元成本，100 封/天足够个人运维
- ✅ 高效：Gmail 的送达率远高于自建邮件服务器
- ✅ 简单：只需一个 Python 脚本 + 一个 token 文件
- ✅ 可扩展：支持多账号轮询、模板邮件、HTML 格式

从今天开始，告别付费邮件服务商，让你的 VPS 拥有自己的邮件发送能力！

---

*本文是"云省钱"系列的一部分。关注 selfvps.net，获取更多自托管省钱技巧。*
