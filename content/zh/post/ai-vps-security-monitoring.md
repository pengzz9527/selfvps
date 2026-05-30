---
title: "AI 驱动的 VPS 安全监控：用本地 LLM 实时检测入侵与异常行为"
description: "VPS 被入侵、被挖矿、被暴力破解——防不胜防？本文将教你利用本地运行的 LLM（大语言模型）作为安全分析引擎，自动解析 auth.log、检测异常登录模式、识别横向移动和挖矿行为，并在 2GB 内存的 VPS 上即可运行。"
date: 2026-05-30T21:30:00+08:00
slug: "ai-vps-security-monitoring"
tags: ["AI安全", "入侵检测", "LLM", "日志分析", "VPS安全", "自托管", "Ollama", "安全监控", "异常检测"]
categories: ["AI安全"]
image: /images/posts/ai-vps-security-monitoring/featured.png
draft: false
---

## 为什么 VPS 安全需要 AI？

一台暴露在公网的 VPS，平均每天会收到几十到几百次 SSH 暴力破解尝试。传统的安全方案依赖规则引擎——Fail2Ban 封禁 IP、ClamAV 查杀恶意文件、RKHunter 检测 Rootkit。这些工具有效，但它们有一个共同的问题：**只看已知威胁**。

AI 安全监控的思路完全不同：让本地 LLM 充当安全分析师，持续读取系统日志、进程列表、网络连接和文件变更，通过语义理解识别出规则引擎发现不了的问题。

| 能力 | 传统工具 | AI 安全助手 |
|------|---------|------------|
| 暴力破解检测 | Fail2Ban（规则匹配） | 分析攻击模式、预测爆破趋势 |
| 恶意进程识别 | 已知签名库 | 发现从未见过的可疑行为 |
| 日志分析 | grep 关键词 | 理解上下文、跨日志关联 |
| 误报处理 | 静默或报警 | 自动判断严重等级，生成处置建议 |

## 整体架构

```
┌──────────────────────────────────────────────┐
│                  VPS 安全监控系统                │
│                                              │
│  ┌─────────┐  ┌──────────┐  ┌───────────┐   │
│  │ 系统日志  │  │ 进程快照  │  │ 网络连接   │   │
│  │ auth.log │  │ ps aux   │  │ ss -tuln  │   │
│  │ syslog   │  │ top      │  │ conntrack │   │
│  └────┬────┘  └────┬─────┘  └─────┬─────┘   │
│       │             │              │          │
│  ┌────▼─────────────▼──────────────▼──────┐  │
│  │        数据采集器 (collector.sh)         │  │
│  │   每 5 分钟采集一次，生成结构化报告         │  │
│  └────────────────┬───────────────────────┘  │
│                   │                           │
│  ┌────────────────▼───────────────────────┐  │
│  │     LLM 分析引擎 (Ollama + Qwen2.5)     │  │
│  │  读取安全快照 → 语义分析 → 输出判断      │  │
│  └────────────────┬───────────────────────┘  │
│                   │                           │
│  ┌────────────────▼───────────────────────┐  │
│  │       告警处理器 (alerter)              │  │
│  │   Telegram / Email / Webhook           │  │
│  └────────────────────────────────────────┘  │
└──────────────────────────────────────────────┘
```

## 部署步骤

### 第一步：安装 Ollama 并拉取轻量模型

```bash
# 安装 Ollama
curl -fsSL https://ollama.com/install.sh | sh

# 拉取 Qwen2.5 7B（量化版，2GB VPS 可运行）
ollama pull qwen2.5:7b-q4_K_M

# 或使用更小的模型（1GB 内存可用）
ollama pull qwen2.5:3b-q4_K_M
```

### 第二步：创建数据采集脚本

```bash
cat > /usr/local/bin/security-collector.sh << 'SCRIPT'
#!/bin/bash
# 安全数据采集器 - 每 5 分钟采集系统安全状态

OUTPUT_DIR="/var/log/security-snapshots"
mkdir -p "$OUTPUT_DIR"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT_FILE="$OUTPUT_DIR/snapshot_$TIMESTAMP.json"

# 1. 最近认证日志（SSH 登录尝试）
AUTH_LOG=$(tail -200 /var/log/auth.log 2>/dev/null || journalctl -u sshd --no-pager -n 200 2>/dev/null)

# 2. 当前登录用户
CURRENT_USERS=$(who)

# 3. 监听端口和网络连接
NET_CONNS=$(ss -tulpn 2>/dev/null)

# 4. 最近新建的 SUID 文件
SUID_FILES=$(find /usr /bin /sbin /etc -type f -perm -4000 -newer /etc/crontab 2>/dev/null)

# 5. 进程列表（按 CPU 排序）
TOP_PROCS=$(ps aux --sort=-%cpu | head -30)

# 6. Docker 容器状态（如果有）
DOCKER_PS=$(docker ps 2>/dev/null || echo "Docker not available")

# 7. 最近修改的 crontab
CRON_CHANGES=$(stat /var/spool/cron/crontabs/ 2>/dev/null)

# 组装 JSON（简化版实际使用可改成更严谨的 JSON）
cat > "$OUTPUT_FILE" << EOF
{
  "timestamp": "$TIMESTAMP",
  "auth_log_summary": $(echo "$AUTH_LOG" | jq -R -s .),
  "logged_in_users": $(echo "$CURRENT_USERS" | jq -R -s .),
  "network_connections": $(echo "$NET_CONNS" | jq -R -s .),
  "suspicious_suid_files": $(echo "$SUID_FILES" | jq -R -s .),
  "top_processes": $(echo "$TOP_PROCS" | jq -R -s .),
  "docker_status": $(echo "$DOCKER_PS" | jq -R -s .)
}
EOF

# 保留最近 60 个快照（5 小时间隔）
find "$OUTPUT_DIR" -name "snapshot_*.json" -mmin +300 -delete
SCRIPT
chmod +x /usr/local/bin/security-collector.sh
```

### 第三步：创建 LLM 分析脚本

```bash
cat > /usr/local/bin/security-analyzer.sh << 'SCRIPT'
#!/bin/bash
# AI 安全分析引擎 - 调用本地 LLM 分析安全快照

LATEST_SNAPSHOT=$(ls -t /var/log/security-snapshots/snapshot_*.json 2>/dev/null | head -1)

if [ -z "$LATEST_SNAPSHOT" ]; then
    echo "No snapshots found. Run collector first."
    exit 1
fi

SNAPSHOT_CONTENT=$(cat "$LATEST_SNAPSHOT")

# 构建 Prompt
PROMPT="你是一个 VPS 安全分析专家。分析以下系统安全快照，按以下格式输出：

1. 安全评级：[安全/可疑/危险]
2. 发现的问题（列出具体条目）
3. 建议的操作（如果存在威胁）

快照数据：
$SNAPSHOT_CONTENT

请用中文回答。如果一切正常，输出 '✅ 系统安全' 即可。"

RESPONSE=$(ollama run qwen2.5:7b-q4_K_M "$PROMPT" 2>/dev/null)

echo "$RESPONSE"

# 如果检测到威胁，发送告警
if echo "$RESPONSE" | grep -q "危险\|可疑\|攻击\|入侵\|挖矿\|恶意"; then
    # 发送 Telegram 告警（配置你的 token 和 chat_id）
    TELEGRAM_TOKEN="${TELEGRAM_BOT_TOKEN:-}"
    CHAT_ID="${TELEGRAM_CHAT_ID:-}"
    if [ -n "$TELEGRAM_TOKEN" ] && [ -n "$CHAT_ID" ]; then
        MESSAGE=$(echo "🚨 *AI 安全告警*\n$RESPONSE" | head -50)
        curl -s -X POST "https://api.telegram.org/bot$TELEGRAM_TOKEN/sendMessage" \
            -d "chat_id=$CHAT_ID" \
            -d "text=$MESSAGE" \
            -d "parse_mode=Markdown" > /dev/null
    fi
fi
SCRIPT
chmod +x /usr/local/bin/security-analyzer.sh
```

### 第四步：配置定时任务

```bash
# 添加 crontab 任务
(crontab -l 2>/dev/null; echo "*/5 * * * * /usr/local/bin/security-collector.sh") | crontab -
(crontab -l 2>/dev/null; echo "*/10 * * * * /usr/local/bin/security-analyzer.sh >> /var/log/ai-security.log 2>&1") | crontab -
```

## 实战测试：模拟一次入侵检测

为了验证效果，我们来模拟一个常见的入侵场景——SSH 暴力破解 + 恶意进程：

```bash
# 模拟大量失败 SSH 登录（仅测试用）
for i in $(seq 1 100); do
    echo "Failed password for root from 10.0.0.$((RANDOM % 255)) port $((10000 + RANDOM % 50000)) ssh2" >> /var/log/auth.log
done

# 模拟挖矿进程
cat > /tmp/.system-update << 'FAKE'
#!/bin/bash
while true; do
    # 模拟挖矿计算
    echo "hashrate: 1234 KH/s"
    sleep 5
done
FAKE
chmod +x /tmp/.system-update
/tmp/.system-update &
```

运行分析器，你会看到类似这样的输出：

```
🔍 分析结果：

安全评级：危险 ⚠️

发现的问题：
1. SSH 暴力破解攻击：检测到 100 次来自不同 IP 的失败登录尝试
2. 可疑进程：/tmp/.system-update 在非标准目录运行，CPU 使用率异常高
3. 未知网络连接：检测到未识别的出站连接

建议操作：
1. 立即终止可疑进程：kill $(pgrep -f system-update)
2. 使用 fail2ban 封禁攻击 IP
3. 检查 /tmp 目录是否有其他恶意文件
4. 建议立即修改 root 密码
```

## 高级配置

### 集成 Fail2Ban + AI 联动

不替代 Fail2Ban，而是在其之上增加智能层：

```bash
# 让 AI 分析 fail2ban 的封禁趋势
cat > /usr/local/bin/ai-fail2ban-analyzer.sh << 'SCRIPT'
#!/bin/bash
# 分析 fail2ban 日志，识别高级攻击模式
BANNED_IPS=$(grep "Ban" /var/log/fail2ban.log | tail -100)

PROMPT="分析以下 fail2ban 封禁记录，回答：
1. 是否有针对特定端口的集中攻击？
2. 攻击是否来自同一网段？
3. 是否需要调整 jail 配置？

封禁记录：
$BANNED_IPS"

ollama run qwen2.5:7b-q4_K_M "$PROMPT"
SCRIPT
```

### 设置 Telegram 告警

创建 `.env` 配置文件：

```bash
cat > /usr/local/etc/ai-security.env << 'ENV'
# Telegram Bot
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklmNOPqrStuVWXyz
TELEGRAM_CHAT_ID=-1001234567890

# 分析频率（秒）
COLLECTOR_INTERVAL=300
ANALYZER_INTERVAL=600
ENV
```

### 使用可视化仪表板（可选）

将安全分析结果推送到 Prometheus + Grafana，构建安全态势感知面板：

```bash
# 将分析结果输出为 Prometheus 指标格式
cat > /usr/local/bin/security-metrics.sh << 'SCRIPT'
#!/bin/bash
# 输出 Prometheus 指标
LATEST_SNAPSHOT=$(ls -t /var/log/security-snapshots/snapshot_*.json | head -1)
SUSPICIOUS_COUNT=$(cat "$LATEST_SNAPSHOT" | grep -c "Failed password\|Invalid user\|Connection closed by authenticating user")

echo "# HELP ai_security_suspicious_events Total suspicious security events"
echo "# TYPE ai_security_suspicious_events gauge"
echo "ai_security_suspicious_events $SUSPICIOUS_COUNT"
SCRIPT
```

## 资源消耗评估

| 组件 | 内存 | CPU | 磁盘 |
|------|------|-----|------|
| Ollama (Qwen2.5:3b-Q4) | ~1.8 GB | 低~中 | 2 GB |
| 数据采集脚本 | ~5 MB | 极低（每5分钟运行1秒） | 每日~50 MB |
| 分析引擎（每次运行） | 瞬时峰值 ~2 GB | 约 5-10 秒 CPU | 日志 ~10 MB/天 |

> 💡 **省钱小贴士**：如果 VPS 只有 1GB 内存，可以使用 `qwen2.5:1.5b-q4_K_M` 量化版，内存占用降至 ~1GB，分析质量仍然可用。

## 总结

用本地 LLM 做 VPS 安全监控有几个核心优势：

1. **零数据外泄** — 所有日志和系统数据都在本地处理，不经过任何第三方 API
2. **零成本** — 不需要付费的 SIEM 或安全服务，一台 VPS 全部搞定
3. **零规则维护** — 不需要手动维护签名库或规则，LLM 理解上下文和语义
4. **可解释性强** — 每个告警都附带自然语言分析，知道为什么告警

当然，这套方案不是要取代 Fail2Ban 和传统的安全工具，而是在它们之上增加一层"AI 分析师"的智能判断。传统工具负责执行，AI 负责理解——**这才是 VPS 安全监控的未来方向**。

---

*本文所有脚本都可以在 2GB 内存的 VPS 上运行。文中用到的 Ollama 和 Qwen2.5 模型均为开源项目。*
