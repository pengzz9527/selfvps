---
title: "VPS 自动化运维脚本集：系统巡检、日志清理与告警通知"
description: "告别手动 SSH 登录排查！本文提供一套开箱即用的 VPS 自动化运维脚本——系统健康巡检、日志自动清理、资源超限告警，让你的服务器 24 小时有人值守"
date: 2026-08-15T08:00:00+08:00
lastmod: 2026-08-15T08:00:00+08:00
slug: "vps-automation-script-collection"
image: /images/posts/vps-automation-script-collection/featured.png
tags: ["VPS", "自动化", "Shell脚本", "运维", "巡检", "日志清理", "告警", "Cron", "systemd"]
categories: ["运维实战"]
aliases: [/zh/post/vps-automation-script-collection/]
draft: false
---

## 引言

你是否经历过这样的场景：

- 早上到公司，发现网站打不开了，因为昨晚磁盘被日志写满了；
- 月底看账单，才发现某台 VPS 的 CPU 一个月都跑在 90% 以上，却毫无察觉；
- 服务器被暴力破解了，因为 SSH 登录失败日志堆积了几个 G，你从来没清理过；
- SSL 证书过期导致服务中断，因为你忘记在日历里设置提醒。

**这些问题的根源只有一个：缺乏自动化运维。**

手动登录服务器检查状态，永远是滞后的——等你发现问题时，用户已经投诉了。本文将为你构建一套**开箱即用的 VPS 自动化运维脚本集**，涵盖系统巡检、日志清理、资源告警三大核心场景，配合 Cron 定时任务，让你的服务器实现 24 小时无人值守守护。

---

## 一、脚本架构设计

在动手写代码之前，先明确我们的设计原则：

| 原则 | 说明 |
|------|------|
| **模块化** | 每个脚本独立运行，可单独调用也可组合执行 |
| **零依赖** | 只使用系统自带工具（bash、awk、grep、curl 等），无需额外安装 |
| **可配置** | 通过环境变量或配置文件控制阈值、通知方式等 |
| **易扩展** | 新增巡检项目只需添加一个函数 |

我们将创建以下文件结构：

```
~/vps-automation/
├── config.sh          # 统一配置文件
├── health-check.sh    # 系统健康巡检
├── log-cleanup.sh     # 日志自动清理
├── alert.sh           # 告警通知（支持多通道）
└── run-all.sh         # 一键执行全部任务
```

---

## 二、统一配置文件

`config.sh` 是所有脚本共享的配置中心：

```bash
#!/bin/bash
# VPS 自动化运维 - 统一配置文件
# 通过环境变量覆盖默认值

# === 基础路径 ===
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="${LOG_DIR:-/var/log/vps-automation}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/vps-automation}"
STATE_FILE="${STATE_FILE:-${LOG_DIR}/.state}"

# === 告警配置 ===
ALERT_ENABLED="${ALERT_ENABLED:-true}"
ALERT_EMAIL="${ALERT_EMAIL:-}"           # 邮箱告警
ALERT_WEBHOOK="${ALERT_WEBHOOK:-}"       # Webhook（飞书/钉钉/Slack）
ALERT_TELEGRAM="${ALERT_TELEGRAM:-}"     # Telegram Bot Token
ALERT_CHAT_ID="${ALERT_CHAT_ID:-}"       # Telegram Chat ID

# === 资源阈值 ===
THRESHOLD_CPU="${THRESHOLD_CPU:-85}"     # CPU 使用率告警阈值
THRESHOLD_MEM="${THRESHOLD_MEM:-90}"     # 内存使用率告警阈值
THRESHOLD_DISK="${THRESHOLD_DISK:-85}"   # 磁盘使用率告警阈值
THRESHOLD_LOAD="${THRESHOLD_LOAD:-}"     # 负载告警阈值（默认=CPU核数）

# === 日志清理 ===
LOG_RETENTION_DAYS="${LOG_RETENTION_DAYS:-30}"     # 日志保留天数
JOURNAL_RETENTION_DAYS="${JOURNAL_RETENTION_DAYS:-14}"  # systemd journal 保留天数
CLEAN_TMP_DAYS="${CLEAN_TMP_DAYS:-7}"              # /tmp 清理天数

# === 计算默认负载阈值 ===
if [[ -z "$THRESHOLD_LOAD" ]]; then
    THRESHOLD_LOAD=$(nproc 2>/dev/null || echo 1)
fi

# === 确保目录存在 ===
mkdir -p "${LOG_DIR}" "${BACKUP_DIR}"
```

---

## 三、系统健康巡检脚本

`health-check.sh` 负责全面检查服务器状态：

```bash
#!/bin/bash
# VPS 自动化运维 - 系统健康巡检
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/config.sh"

TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
REPORT=""
ISSUES=0

# 颜色定义
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
NC='\033[0m'

report() {
    local level="$1" msg="$2"
    case "$level" in
        OK)     REPORT+="✅ $msg\n" ;;
        WARN)   REPORT+="⚠️  $msg\n"; ((ISSUES++)) || true ;;
        ERROR)  REPORT+="❌ $msg\n"; ((ISSUES+=2)) || true ;;
    esac
}

echo "=== VPS 健康巡检 $(date '+%Y-%m-%d %H:%M:%S') ==="

# 1. CPU 使用率
CPU_USAGE=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | cut -d'%' -f1 2>/dev/null || echo "0")
CPU_USAGE=${CPU_USAGE%.*}  # 取整数部分
if [[ -n "$CPU_USAGE" && "$CPU_USAGE" -gt "$THRESHOLD_CPU" ]]; then
    report "ERROR" "CPU 使用率 ${CPU_USAGE}% 超过阈值 ${THRESHOLD_CPU}%"
elif [[ -n "$CPU_USAGE" && "$CPU_USAGE" -gt $((THRESHOLD_CPU - 10)) ]]; then
    report "WARN" "CPU 使用率 ${CPU_USAGE}% 接近阈值"
else
    report "OK" "CPU 使用率 ${CPU_USAGE:-正常}"
fi

# 2. 内存使用
MEM_INFO=$(free | grep Mem)
MEM_TOTAL=$(echo "$MEM_INFO" | awk '{print $2}')
MEM_USED=$(echo "$MEM_INFO" | awk '{print $3}')
MEM_PCT=$(awk "BEGIN {printf \"%d\", ($MEM_USED/$MEM_TOTAL)*100}")

if [[ "$MEM_PCT" -gt "$THRESHOLD_MEM" ]]; then
    report "ERROR" "内存使用率 ${MEM_PCT}% 超过阈值 ${THRESHOLD_MEM}%"
elif [[ "$MEM_PCT" -gt $((THRESHOLD_MEM - 10)) ]]; then
    report "WARN" "内存使用率 ${MEM_PCT}% 接近阈值"
else
    report "OK" "内存使用率 ${MEM_PCT}% (${MEM_USED}MB/${MEM_TOTAL}MB)"
fi

# 3. 磁盘使用
DISK_ISSUES=""
while IFS= read -r line; do
    USE_PCT=$(echo "$line" | awk '{print $5}' | tr -d '%')
    MOUNT=$(echo "$line" | awk '{print $6}')
    if [[ "$USE_PCT" -gt "$THRESHOLD_DISK" ]]; then
        DISK_ISSUES+=" ${MOUNT}=${USE_PCT}%"
    fi
done < <(df -h --output=pcent,target 2>/dev/null | tail -n +2)

if [[ -n "$DISK_ISSUES" ]]; then
    report "ERROR" "磁盘空间不足:${DISK_ISSUES}"
else
    report "OK" "磁盘空间正常"
fi

# 4. 系统负载
LOAD=$(cat /proc/loadavg | awk '{print $1}')
LOAD_INT=${LOAD%.*}
if [[ "$LOAD_INT" -ge "$THRESHOLD_LOAD" ]]; then
    report "WARN" "系统负载 ${LOAD} 接近/超过核数 ${THRESHOLD_LOAD}"
else
    report "OK" "系统负载 ${LOAD}"
fi

# 5. SSH 暴力破解检测
FAILED_LOGINS=$(grep -c "Failed password" /var/log/auth.log 2>/dev/null || echo "0")
if [[ "$FAILED_LOGINS" -gt 100 ]]; then
    report "WARN" "检测到 ${FAILED_LOGINS} 次 SSH 失败登录，可能存在暴力破解"
else
    report "OK" "SSH 登录正常（失败次数: ${FAILED_LOGINS}）"
fi

# 6. SSL 证书到期检查
CERT_HOST="${CERT_HOST:-$(hostname -f 2>/dev/null || echo 'localhost')}"
if command -v openssl &>/dev/null; then
    CERT_EXPIRY=$(echo | openssl s_client -servername "${CERT_HOST}" -connect "${CERT_HOST}:443" 2>/dev/null | \
        openssl x509 -noout -dates 2>/dev/null | grep "notAfter" | cut -d= -f2)
    if [[ -n "$CERT_EXPIRY" ]]; then
        DAYS_LEFT=$(( ($(date -d "$CERT_EXPIRY" +%s) - $(date +%s)) / 86400 ))
        if [[ "$DAYS_LEFT" -lt 7 ]]; then
            report "ERROR" "SSL 证书将在 ${DAYS_LEFT} 天后过期: ${CERT_EXPIRY}"
        elif [[ "$DAYS_LEFT" -lt 30 ]]; then
            report "WARN" "SSL 证书将在 ${DAYS_LEFT} 天后过期"
        else
            report "OK" "SSL 证书剩余 ${DAYS_LEFT} 天有效"
        fi
    fi
fi

# 7. 关键服务状态
for svc in sshd nginx docker; do
    if systemctl is-active --quiet "${svc}" 2>/dev/null; then
        report "OK" "服务 ${svc} 运行中"
    else
        report "WARN" "服务 ${svc} 未运行"
    fi
done

# 8. 僵尸进程检测
ZOMBIE_COUNT=$(ps aux | awk '$8=="Z"' | wc -l)
if [[ "$ZOMBIE_COUNT" -gt 0 ]]; then
    report "WARN" "检测到 ${ZOMBIE_COUNT} 个僵尸进程"
else
    report "OK" "无僵尸进程"
fi

# 输出报告
echo -e "$REPORT"

# 保存报告
REPORT_FILE="${LOG_DIR}/health-$(date +%Y%m%d-%H%M%S).txt"
echo -e "$REPORT" > "$REPORT_FILE"
echo "报告已保存: ${REPORT_FILE}"

# 发送告警
if [[ "$ALERT_ENABLED" == "true" && "$ISSUES" -gt 0 ]]; then
    source "${SCRIPT_DIR}/alert.sh"
    send_alert "VPS 健康巡检告警" "$REPORT" "$ISSUES"
fi

exit ${ISSUES}
```

---

## 四、日志自动清理脚本

`log-cleanup.sh` 智能清理各类日志，防止磁盘被撑满：

```bash
#!/bin/bash
# VPS 自动化运维 - 日志自动清理
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/config.sh"

echo "=== VPS 日志清理 $(date '+%Y-%m-%d %H:%M:%S') ==="
FREED=0

# 1. 清理 systemd journal
if command -v journalctl &>/dev/null; then
    BEFORE=$(du -sh /var/log/journal 2>/dev/null | awk '{print $1}' || echo "0")
    journalctl --vacuum-time="${JOURNAL_RETENTION_DAYS}d" 2>/dev/null || true
    AFTER=$(du -sh /var/log/journal 2>/dev/null | awk '{print $1}' || echo "0")
    echo "✅ systemd journal: ${BEFORE} → ${AFTER} (保留${JOURNAL_RETENTION_DAYS}天)"
fi

# 2. 清理应用日志（按保留天数）
find /var/log -name "*.log" -type f -mtime +${LOG_RETENTION_DAYS} 2>/dev/null | while read -r f; do
    SIZE=$(du -sh "$f" 2>/dev/null | awk '{print $1}')
    rm -f "$f"
    echo "🗑️  已删除: $f (${SIZE})"
done

# 3. 压缩未清理的大日志文件
find /var/log -name "*.log" -type f -size +100M 2>/dev/null | while read -r f; do
    if [[ ! -f "${f}.gz" ]]; then
        gzip -f "$f" 2>/dev/null && echo "📦 已压缩: ${f}.gz"
    fi
done

# 4. 清理 /tmp 临时文件
find /tmp -type f -mtime +${CLEAN_TMP_DAYS} -delete 2>/dev/null && \
    echo "🧹 已清理 ${CLEAN_TMP_DAYS} 天前的 /tmp 文件"

# 5. 清理 Docker 垃圾（如果运行 Docker）
if command -v docker &>/dev/null; then
    echo "🔄 Docker 垃圾清理..."
    docker system prune -f --filter "until=720h" 2>/dev/null || true
    docker volume prune -f 2>/dev/null || true
    echo "✅ Docker 清理完成"
fi

# 6. 清理 apt 缓存
if command -v apt-get &>/dev/null; then
    apt-get clean -y 2>/dev/null && echo "🧹 apt 缓存已清理"
fi

# 7. 清理 yum/dnf 缓存
if command -v dnf &>/dev/null; then
    dnf clean all 2>/dev/null && echo "🧹 dnf 缓存已清理"
elif command -v yum &>/dev/null; then
    yum clean all 2>/dev/null && echo "🧹 yum 缓存已清理"
fi

# 8. 显示清理后磁盘状态
echo ""
echo "=== 清理后磁盘状态 ==="
df -h | grep -E "^Filesystem|/dev/"

echo ""
echo "=== 日志清理完成 ==="
```

---

## 五、告警通知脚本

`alert.sh` 支持多种通知渠道：

```bash
#!/bin/bash
# VPS 自动化运维 - 告警通知
# 支持: 邮件、Webhook(飞书/钉钉/Slack)、Telegram

send_alert() {
    local title="$1"
    local message="$2"
    local issue_count="${3:-0}"

    # 只在实际有问题时发送告警
    if [[ "$issue_count" -eq 0 ]]; then
        return 0
    fi

    local hostname=$(hostname)
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    local severity="WARNING"
    [[ "$issue_count" -gt 2 ]] && severity="CRITICAL"

    # === 飞书 Webhook ===
    if [[ -n "$ALERT_WEBHOOK" ]]; then
        local payload=$(cat <<EOF
{
    "msg_type": "interactive",
    "card": {
        "header": {
            "title": {"content": "🚨 ${title}", "tag": "plain_text"},
            "template": "$([ "$severity" == "CRITICAL" ] && echo "red" || echo "orange")"
        },
        "elements": [
            {
                "tag": "div",
                "text": {
                    "content": "**服务器:** ${hostname}\n**时间:** ${timestamp}\n**严重程度:** ${severity}\n\n${message}",
                    "tag": "lark_md"
                }
            },
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"content": "查看服务器状态", "tag": "lark_md"},
                        "url": "ssh://${hostname}",
                        "type": "default"
                    }
                ]
            }
        ]
    }
}
EOF
)
        curl -s -X POST -H "Content-Type: application/json" -d "$payload" "$ALERT_WEBHOOK" \
            >/dev/null 2>&1 || echo "⚠️ 飞书告警发送失败"
    fi

    # === 钉钉 Webhook ===
    if [[ -n "$ALERT_WEBHOOK" && "$ALERT_WEBHOOK" == *"dingtalk"* ]]; then
        local payload=$(cat <<EOF
{
    "msgtype": "markdown",
    "markdown": {
        "title": "${title}",
        "text": "### 🚨 ${title}\n\n**服务器:** ${hostname}\n**时间:** ${timestamp}\n**严重程度:** ${severity}\n\n${message}\n\n> 请及时处理！"
    }
}
EOF
)
        curl -s -X POST -H "Content-Type: application/json" -d "$payload" "$ALERT_WEBHOOK" \
            >/dev/null 2>&1 || echo "⚠️ 钉钉告警发送失败"
    fi

    # === Telegram ===
    if [[ -n "$ALERT_TELEGRAM" && -n "$ALERT_CHAT_ID" ]]; then
        local tg_text="🚨 *${title}*\n\n🖥 服务器: ${hostname}\n⏰ 时间: ${timestamp}\n🔴 严重度: ${severity}\n\n${message}"
        curl -s -X POST \
            "https://api.telegram.org/bot${ALERT_TELEGRAM}/sendMessage" \
            -d chat_id="$ALERT_CHAT_ID" \
            -d parse_mode="Markdown" \
            -d text="$tg_text" \
            >/dev/null 2>&1 || echo "⚠️ Telegram 告警发送失败"
    fi

    # === 邮件 ===
    if [[ -n "$ALERT_EMAIL" && -n "$(command -v mail)" ]]; then
        echo -e "${message}" | mail -s "[${severity}] ${title} - ${hostname}" "$ALERT_EMAIL" \
            2>/dev/null || echo "⚠️ 邮件告警发送失败"
    fi

    # === 系统日志 ===
    logger -t "vps-automation" "${severity}: ${title} - ${hostname} - Issues: ${issue_count}"
}

# 导出函数供其他脚本调用
export -f send_alert
```

---

## 六、一键执行脚本

`run-all.sh` 整合所有任务：

```bash
#!/bin/bash
# VPS 自动化运维 - 一键执行全部任务
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="${SCRIPT_DIR}/../log/run-$(date +%Y%m%d-%H%M%S).log"

mkdir -p "$(dirname "$LOG_FILE")"

echo "========================================" | tee "$LOG_FILE"
echo "  VPS 自动化运维 - 全面执行" | tee -a "$LOG_FILE"
echo "  时间: $(date '+%Y-%m-%d %H:%M:%S')" | tee -a "$LOG_FILE"
echo "========================================" | tee "$LOG_FILE"

cd "$SCRIPT_DIR"

# 1. 健康巡检
echo "" | tee -a "$LOG_FILE"
echo "[1/3] 系统健康巡检..." | tee -a "$LOG_FILE"
bash "${SCRIPT_DIR}/health-check.sh" 2>&1 | tee -a "$LOG_FILE" || true

# 2. 日志清理
echo "" | tee -a "$LOG_FILE"
echo "[2/3] 日志清理..." | tee -a "$LOG_FILE"
bash "${SCRIPT_DIR}/log-cleanup.sh" 2>&1 | tee -a "$LOG_FILE"

# 3. 资源使用情况总结
echo "" | tee -a "$LOG_FILE"
echo "[3/3] 资源状态快照..." | tee -a "$LOG_FILE"
echo "--- CPU ---" | tee -a "$LOG_FILE"
top -bn1 | head -5 | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"
echo "--- 内存 ---" | tee -a "$LOG_FILE"
free -h | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"
echo "--- 磁盘 ---" | tee -a "$LOG_FILE"
df -h | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"
echo "  执行完成: $(date '+%Y-%m-%d %H:%M:%S')" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"
```

---

## 七、配置定时任务

### 使用 Cron

编辑 crontab：

```bash
crontab -e
```

添加以下条目：

```cron
# 每天早上 6 点执行全面巡检和清理
0 6 * * * /root/vps-automation/run-all.sh >> /root/vps-automation/logs/cron.log 2>&1

# 每小时执行轻量级健康检查（仅告警不清理）
0 * * * * /root/vps-automation/health-check.sh >> /root/vps-automation/logs/hourly-check.log 2>&1

# 每周日凌晨 3 点执行深度清理
0 3 * * 0 /root/vps-automation/log-cleanup.sh --deep-clean >> /root/vps-automation/logs/weekly-cleanup.log 2>&1
```

### 使用 systemd timer（推荐）

创建 timer 单元文件：

```ini
# /etc/systemd/system/vps-health-check.timer
[Unit]
Description=VPS 健康检查定时器

[Timer]
OnCalendar=*:00
Persistent=true
RandomizedDelaySec=60

[Install]
WantedBy=timers.target
```

```ini
# /etc/systemd/system/vps-health-check.service
[Unit]
Description=VPS 健康检查服务

[Service]
Type=oneshot
User=root
WorkingDirectory=/root/vps-automation
ExecStart=/bin/bash health-check.sh
```

启用 timer：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now vps-health-check.timer
sudo systemctl status vps-health-check.timer
```

---

## 八、配置告警渠道

### 飞书机器人 Webhook

1. 在飞书群中添加自定义机器人
2. 复制 Webhook 地址
3. 编辑 `config.sh`：
   ```bash
   ALERT_WEBHOOK="https://open.feishu.cn/open-apis/bot/v2/hook/xxxxx"
   ```

### 钉钉机器人 Webhook

1. 在钉钉群中添加自定义机器人（选择加签方式）
2. 复制 Webhook 地址
3. 编辑 `config.sh`：
   ```bash
   ALERT_WEBHOOK="https://oapi.dingtalk.com/robot/send?access_token=xxxxx"
   ```

### Telegram Bot

1. 在 Telegram 中找 @BotFather 创建机器人
2. 获取 Bot Token
3. 将机器人加入群组并获取 Chat ID
4. 编辑 `config.sh`：
   ```bash
   ALERT_TELEGRAM="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
   ALERT_CHAT_ID="-1001234567890"
   ```

---

## 九、进阶：多服务器统一管理

如果你有多个 VPS，可以用一个脚本批量管理：

```bash
#!/bin/bash
# 多服务器批量巡检
SERVERS=("user@vps1.example.com" "user@vps2.example.com" "user@vps3.example.com")

for server in "${SERVERS[@]}"; do
    echo "=== 巡检 ${server} ==="
    ssh -o ConnectTimeout=10 "${server}" "bash <(curl -s https://raw.githubusercontent.com/yourrepo/vps-automation/main/run-all.sh)" \
        || echo "❌ 无法连接 ${server}"
    echo ""
done
```

配合 **SSH 密钥免密登录** 和 **Ansible**，可以实现真正的批量自动化运维。

---

## 十、总结

这套 VPS 自动化运维脚本集的核心价值在于：

| 能力 | 效果 |
|------|------|
| **系统巡检** | 自动发现 CPU/内存/磁盘/服务异常，不再依赖人工排查 |
| **日志清理** | 防止磁盘被日志撑满，自动压缩和归档历史日志 |
| **告警通知** | 问题发生时第一时间通知你，支持飞书/钉钉/Telegram/邮件 |
| **定时执行** | Cron 或 systemd timer 确保任务按时执行，7×24 小时守护 |

**下一步建议：**

1. 根据实际需求调整阈值配置（`config.sh`）
2. 选择合适的告警渠道并配置 Webhook
3. 设置 systemd timer 替代 Cron（更可靠）
4. 定期查看巡检报告，持续优化脚本

> 💡 **记住：最好的运维是让你不需要运维的运维。** 把重复性的检查工作交给脚本，你只需要在告警发生时处理真正的问题。

---

## 附录：快速部署命令

```bash
# 一键部署
mkdir -p ~/vps-automation && cd ~/vps-automation
# 将上述脚本分别保存为对应文件
chmod +x *.sh
# 配置告警渠道
vim config.sh
# 设置定时任务
crontab -e
# 立即测试
./run-all.sh
```
