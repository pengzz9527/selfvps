---
title: "AI 自动生成 VPS 运维日报：用本地 LLM 搭建智能监控与分析系统"
description: "还在手动 SSH 登录排查问题？让本地 LLM 每天自动读取系统状态、分析日志趋势、生成运维日报，并在发现问题时给出修复建议甚至自动执行。本文带你在 VPS 上搭建一套完整方案。"
date: 2026-06-02T21:30:00+08:00
slug: "ai-vps-daily-operations-report"
tags: ["AI运维", "LLM", "监控", "日志分析", "自动运维", "VPS管理", "Ollama", "Shell脚本"]
categories: ["AI运维"]
image: /images/posts/ai-vps-daily-operations-report/featured.png
draft: false
---

VPS 买了、服务搭了、网站上线了——然后呢？

如果你和大多数独立开发者一样，VPS 的日常运维基本靠"等出事再说"。硬盘满了才想起来清理、进程挂了才发现服务宕机、日志里藏着入侵痕迹却无人问津。

本文要解决的就是这个问题：**让本地运行的 LLM（大语言模型）每天自动生成一份运维报告**，像你的私人运维工程师一样，帮你检查服务器健康、分析异常、给出建议。

## 为什么需要 AI 运维报告？

传统监控工具（Prometheus + Grafana、Netdata、Uptime Kuma）能告诉你"什么出了问题"，但它们不会分析"为什么"和"该怎么办"。

| 能力 | 传统监控 | AI 运维报告 |
|------|---------|-----------|
| 磁盘使用率告警 | ✅ 达到阈值发通知 | ✅ 分析增长趋势，预测何时爆满 |
| CPU 异常 | ✅ 显示负载曲线 | ✅ 关联进程上下文，判断是否被挖矿 |
| 日志分析 | ❌ 只能关键词匹配 | ✅ 语义理解，发现未知模式 |
| 故障修复 | ❌ 人工介入 | ✅ 生成修复命令，可选自动执行 |
| 趋势报告 | ⚠️ 需要手动配置 | ✅ 自动生成每日/每周摘要 |
| 成本 | 多个组件需维护 | 一个脚本 + 本地 LLM |

## 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                    VPS 服务器                            │
│                                                         │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │  数据采集器   │  │  LLM 分析引擎 │  │  报告生成器    │  │
│  │  collect.sh  │→│  Ollama API  │→│  report.sh    │  │
│  │              │  │  (本地模型)   │  │               │  │
│  │  • 系统指标   │  │              │  │  • 格式化报告  │  │
│  │  • 日志片段   │  │  • 异常分析   │  │  • 邮件/Telegram│  │
│  │  • 进程列表   │  │  • 趋势判断   │  │  • Web 预览    │  │
│  │  • 磁盘/网络  │  │  • 建议生成   │  │  • 历史存档    │  │
│  └─────────────┘  └──────────────┘  └───────────────┘  │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### 组件详解

1. **数据采集器**：Shell 脚本，采集系统状态、日志摘要、进程信息
2. **LLM 分析引擎**：本地运行的 Ollama + 轻量模型（如 Qwen2.5 7B 或 Llama 3.1 8B）
3. **报告生成器**：将 LLM 分析结果格式化为美观的报告，推送到你的通知渠道

## 第一步：部署本地 LLM（Ollama）

如果你已经部署了 Ollama，这一步可以跳过。如果没有，只需要两分钟：

```bash
# 安装 Ollama
curl -fsSL https://ollama.com/install.sh | sh

# 拉取轻量模型（推荐 Qwen2.5 7B，2GB 内存即可运行）
ollama pull qwen2.5:7b

# 验证
ollama list
```

> **选择建议**：2GB 内存 VPS 推荐 `qwen2.5:7b` 或 `llama3.1:8b`（量化版本）。1GB 内存建议使用 `qwen2.5:3b` 或 `phi3:mini`。

## 第二步：数据采集脚本

创建一个系统数据采集脚本，收集运维报告需要的原始数据：

```bash
#!/bin/bash
# /usr/local/bin/collect-ops-data.sh

REPORT_DIR="/var/ops-reports/$(date +%Y%m%d)"
mkdir -p "$REPORT_DIR"

# 1. 系统基础指标
cat > "$REPORT_DIR/system.txt" << 'EOF'
=== 系统基础信息 ===
EOF
echo "主机名: $(hostname)" >> "$REPORT_DIR/system.txt"
echo "运行时间: $(uptime -p)" >> "$REPORT_DIR/system.txt"
echo "负载均值: $(uptime | awk -F'load average:' '{print $2}')" >> "$REPORT_DIR/system.txt"
echo "CPU 使用率: $(top -bn1 | grep 'Cpu(s)' | awk '{print $2 + $4}')%" >> "$REPORT_DIR/system.txt"
echo "内存使用: $(free -h | awk '/^Mem:/{print $3 " / " $2}')" >> "$REPORT_DIR/system.txt"
echo "交换分区: $(free -h | awk '/^Swap:/{print $3 " / " $2}')" >> "$REPORT_DIR/system.txt"
echo "磁盘使用: $(df -h / | awk 'NR==2{print $3 " / " $2 " (" $5 ")"}')" >> "$REPORT_DIR/system.txt"
echo "磁盘 Inode: $(df -i / | awk 'NR==2{print $5}')" >> "$REPORT_DIR/system.txt"

# 2. 进程信息
ps aux --sort=-%cpu | head -15 > "$REPORT_DIR/top-processes.txt"

# 3. Docker 状态
if command -v docker &>/dev/null; then
  docker ps -a --format "table {{.Names}}\t{{.Status}}\t{{.Image}}\t{{.Ports}}" > "$REPORT_DIR/docker-status.txt"
  docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemPerc}}\t{{.NetIO}}" 2>/dev/null > "$REPORT_DIR/docker-stats.txt"
fi

# 4. 网络连接
ss -tuln > "$REPORT_DIR/network-listening.txt"
ss -t state established | head -30 > "$REPORT_DIR/network-connections.txt"

# 5. 关键日志（过去 24 小时异常）
journalctl --since "24 hours ago" -p err --no-pager -n 100 > "$REPORT_DIR/journal-errors.txt" 2>/dev/null
journalctl --since "24 hours ago" -p crit --no-pager -n 50 > "$REPORT_DIR/journal-critical.txt" 2>/dev/null

# 6. SSH 登录失败统计
if [ -f /var/log/auth.log ]; then
  grep "Failed password" /var/log/auth.log | tail -50 > "$REPORT_DIR/ssh-failures.txt"
  echo "SSH 失败总数（24h）: $(grep "Failed password" /var/log/auth.log | wc -l)" >> "$REPORT_DIR/ssh-failures.txt"
elif [ -f /var/log/secure ]; then
  grep "Failed password" /var/log/secure | tail -50 > "$REPORT_DIR/ssh-failures.txt"
  echo "SSH 失败总数（24h）: $(grep "Failed password" /var/log/secure | wc -l)" >> "$REPORT_DIR/ssh-failures.txt"
fi

# 7. 最近文件变更（可疑）
find /var/www /etc -type f -mtime -1 2>/dev/null | head -30 > "$REPORT_DIR/recent-changes.txt"

# 8. Certbot 证书状态
if command -v certbot &>/dev/null; then
  certbot certificates 2>/dev/null > "$REPORT_DIR/certificates.txt"
fi

echo "✅ 数据采集完成: $REPORT_DIR"
```

赋予执行权限并测试：

```bash
chmod +x /usr/local/bin/collect-ops-data.sh
sudo /usr/local/bin/collect-ops-data.sh
```

## 第三步：LLM 分析引擎

下一步，将采集到的数据发送给本地 LLM，让它进行分析：

```bash
#!/bin/bash
# /usr/local/bin/analyze-with-llm.sh

REPORT_DIR="/var/ops-reports/$(date +%Y%m%d)"
MODEL="qwen2.5:7b"

# 构建 Prompt
PROMPT="你是一位专业的 VPS 运维工程师。请根据以下服务器数据，生成一份运维分析报告。

请包含以下内容：
1. **健康评分**（0-100，基于系统负载、磁盘、内存、错误日志综合评估）
2. **异常发现**（列出所有值得关注的问题，按严重程度排序）
3. **趋势分析**（如果有历史数据，对比变化趋势）
4. **具体建议**（针对每个问题给出可执行的修复命令或操作）
5. **安全摘要**（SSH 爆破尝试、可疑文件变更等）

请用中文回答，保持专业且简洁。

=== 系统数据 ===

$(cat "$REPORT_DIR/system.txt")

=== Top 进程 ===
$(cat "$REPORT_DIR/top-processes.txt")

=== Docker 状态 ===
$(cat "$REPORT_DIR/docker-status.txt" 2>/dev/null || echo "无 Docker")

=== 日志错误摘要 ===
$(head -60 "$REPORT_DIR/journal-errors.txt" 2>/dev/null || echo "无错误日志")

=== SSH 爆破统计 ===
$(cat "$REPORT_DIR/ssh-failures.txt" 2>/dev/null || echo "无 SSH 日志")

=== 近期文件变更 ===
$(cat "$REPORT_DIR/recent-changes.txt" 2>/dev/null || echo "无")
"

# 发送给 Ollama
curl -s http://localhost:11434/api/generate \
  -d "{\"model\": \"$MODEL\", \"prompt\": \"$PROMPT\", \"stream\": false}" \
  | jq -r '.response' > "$REPORT_DIR/analysis.txt"

echo "✅ AI 分析完成: $REPORT_DIR/analysis.txt"
```

设置定时任务，每天早上 8 点自动执行：

```bash
# crontab -e
0 8 * * * /usr/local/bin/collect-ops-data.sh && /usr/local/bin/analyze-with-llm.sh
```

## 第四步：报告推送（Telegram / Email / Web）

报告生成后，需要推送到你日常使用的渠道。

### Telegram Bot 推送

```bash
#!/bin/bash
# /usr/local/bin/send-report-telegram.sh

BOT_TOKEN="你的_BOT_TOKEN"
CHAT_ID="你的_CHAT_ID"
REPORT_DIR="/var/ops-reports/$(date +%Y%m%d)"

REPORT=$(cat "$REPORT_DIR/analysis.txt")

# 拼接消息（Telegram 限制 4096 字符，超长则分段）
MSG="📊 *VPS 运维日报 - $(date '+%Y-%m-%d')*
\`\`\`
$REPORT
\`\`\`
#selfvps #运维日报"

curl -s -X POST "https://api.telegram.org/bot$BOT_TOKEN/sendMessage" \
  -d "chat_id=$CHAT_ID&text=$MSG&parse_mode=Markdown&disable_web_page_preview=true"
```

### 生成 Web 页面

也可以生成 HTML 页面，方便在浏览器中查看历史报告：

```bash
#!/bin/bash
# /usr/local/bin/gen-report-html.sh

REPORT_DIR="/var/ops-reports/$(date +%Y%m%d)"
ANALYSIS=$(cat "$REPORT_DIR/analysis.txt" | sed 's/$/<br>/g')
SYSTEM=$(cat "$REPORT_DIR/system.txt" | sed 's/$/<br>/g')

cat > "$REPORT_DIR/report.html" << HTML
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>VPS 运维日报 - $(date '+%Y-%m-%d')</title>
  <style>
    body { font-family: 'Segoe UI', sans-serif; max-width: 800px; margin: 40px auto; padding: 20px; background: #0d1117; color: #c9d1d9; }
    h1 { color: #58a6ff; border-bottom: 1px solid #30363d; padding-bottom: 10px; }
    h2 { color: #7ee787; }
    pre { background: #161b22; padding: 16px; border-radius: 8px; overflow-x: auto; }
    .meta { color: #8b949e; font-size: 0.9em; }
    .healthy { color: #3fb950; }
    .warning { color: #d29922; }
    .danger { color: #f85149; }
  </style>
</head>
<body>
  <h1>📊 VPS 运维日报</h1>
  <p class="meta">生成时间: $(date '+%Y-%m-%d %H:%M:%S') | 服务器: $(hostname)</p>
  <div>$ANALYSIS</div>
  <hr>
  <h2>原始系统数据</h2>
  <pre>$SYSTEM</pre>
</body>
</html>
HTML

echo "✅ HTML 报告: $REPORT_DIR/report.html"
```

## 进阶：自动修复（Self-Healing）

这是最有价值的部分——当 LLM 发现问题时，可以让它**自动执行修复**。实现思路是让 LLM 输出结构化的 JSON 指令：

```bash
#!/bin/bash
# /usr/local/bin/auto-heal.sh

REPORT_DIR="/var/ops-reports/$(date +%Y%m%d)"
MODEL="qwen2.5:7b"

# 构建"诊断 + 修复"Prompt
PROMPT="你是一位 VPS 自动修复工程师。请分析以下系统数据，如果发现问题，输出 JSON 格式的修复指令。

如果一切正常，输出: {\"status\": \"healthy\", \"score\": 95, \"message\": \"系统运行正常\"}

如果发现问题，请输出:
{
  \"status\": \"issues_found\",
  \"score\": 60,
  \"issues\": [
    {
      \"severity\": \"high|medium|low\",
      \"problem\": \"问题描述\",
      \"fix_command\": \"可执行的修复命令\",
      \"auto_fix\": true
    }
  ]
}

=== 系统数据 ===
$(cat "$REPORT_DIR/system.txt")

=== 关键错误日志 ===
$(head -30 "$REPORT_DIR/journal-errors.txt" 2>/dev/null || echo "无")

=== Docker 状态 ===
$(cat "$REPORT_DIR/docker-status.txt" 2>/dev/null || echo "无")
"

# 获取 LLM 响应
RESPONSE=$(curl -s http://localhost:11434/api/generate \
  -d "{\"model\": \"$MODEL\", \"prompt\": \"$PROMPT\", \"stream\": false, \"format\": \"json\"}" \
  | jq -r '.response')

echo "$RESPONSE" > "$REPORT_DIR/heal-plan.json"

# 自动执行修复
HEAL_STATUS=$(echo "$RESPONSE" | jq -r '.status')

if [ "$HEAL_STATUS" = "issues_found" ]; then
  echo "$RESPONSE" | jq -c '.issues[] | select(.auto_fix == true and .severity != "low")' | while read issue; do
    PROBLEM=$(echo "$issue" | jq -r '.problem')
    CMD=$(echo "$issue" | jq -r '.fix_command')
    SEVERITY=$(echo "$issue" | jq -r '.severity')

    echo "🛠  [$SEVERITY] $PROBLEM"
    echo "   执行: $CMD"
    eval "$CMD" || echo "   ⚠️ 修复命令执行失败"
  done
fi
```

> **安全提示**：自动执行 LLM 生成的命令存在风险。建议从 `severity: medium` 和 `severity: low` 开始，高风险问题只生成建议，手动确认后执行。

## 实际运行效果

以下是真实 VPS 上生成的报告示例片段：

```
📊 VPS 运维日报 - 2026-06-02
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🏥 健康评分: 72/100（良好，但有改进空间）

🔴 高风险问题 (1个):
  1. 磁盘使用率 87%，预计 12 天内占满
     → 修复: sudo journalctl --vacuum-size=500M && docker system prune -af

🟡 中风险问题 (2个):
  2. Docker 容器 'postgres' 内存使用 1.8GB，超出基线 40%
     → 建议: 检查 PostgreSQL 配置，考虑限制容器内存
  3. SSH 爆破: 过去 24 小时 247 次失败尝试（来自 38 个 IP）
     → 修复: 已自动执行 fail2ban 封禁

🟢 低风险/信息:
  • Certbot 证书: 全部有效，下次续期 2026-08-15
  • 系统更新: 12 个安全更新待安装
  • Swap 使用: 0%，正常

📈 趋势（与昨日对比）:
  • 磁盘使用: 86% → 87% (+1%) ⚠️
  • 平均负载: 0.8 → 1.2 (正常波动)
  • 日志错误数: 34 → 28 (改善中)
```

## 定时任务完整配置

将以上所有功能整合到 crontab：

```bash
# 每天早上 8 点生成运维日报
0 8 * * * /usr/local/bin/collect-ops-data.sh && /usr/local/bin/analyze-with-llm.sh && /usr/local/bin/send-report-telegram.sh

# 每 4 小时检查一次关键指标，发现问题立即自愈
0 */4 * * * /usr/local/bin/collect-ops-data.sh && /usr/local/bin/auto-heal.sh

# 每周日生成详细周报
0 9 * * 0 /usr/local/bin/gen-report-html.sh

# 每月清理历史报告（保留最近 90 天）
0 6 1 * * find /var/ops-reports/ -maxdepth 1 -type d -mtime +90 -exec rm -rf {} \;
```

## 资源消耗评估

这套系统对 VPS 的额外负担很小：

| 组件 | CPU | 内存 | 磁盘 |
|------|-----|------|------|
| 数据采集 | ~2 秒/次 | — | ~100KB/次 |
| LLM 分析（7B 模型） | ~30 秒 | ~4GB | ~4.5GB（模型文件） |
| LLM 分析（3B 轻量模型） | ~10 秒 | ~2GB | ~2.2GB（模型文件） |
| 报告推送 | ~1 秒 | — | — |

> 如果你使用的是 2GB 内存 VPS，建议使用 `qwen2.5:3b` 或 `phi3:mini`。分析一次大约 10 秒、2GB 内存，日常后台运行完全可行。

## 扩展思路

1. **多服务器聚合报告**：多个 VPS 的数据汇总到一台机器分析，生成全局运维看板
2. **AI 预测扩容**：根据磁盘/内存增长趋势，自动预测扩容时间并发出提醒
3. **Webhook 集成**：与 PagerDuty、Slack、钉钉等平台集成
4. **自定义知识库**：将你的服务器架构文档喂给 LLM，让它给出更贴合架构的分析
5. **Ansible 集成**：将 LLM 生成的修复命令转化为 Ansible Playbook

## 总结

用本地 LLM 生成 VPS 运维日报，本质上是用"AI 运维工程师"替代了人工巡检。你不用再每天 SSH 登录检查状态、不用再翻日志找问题——AI 帮你读完、分析完、给出方案，甚至自动修好。

这套方案的核心优势：
- ✅ **数据隐私**：所有数据在本地，不离开你的 VPS
- ✅ **成本极低**：使用现有 VPS 资源，无需额外云服务
- ✅ **持续改进**：随着 LLM 模型进步，分析质量持续提升
- ✅ **完全可控**：随时调整 Prompt、修复策略、通知方式

从今天开始，让 AI 帮你管服务器。
