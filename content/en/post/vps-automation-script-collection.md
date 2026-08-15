---
title: "VPS Automation Script Collection: System Inspection, Log Cleanup & Alerting"
description: "Stop manually SSH-ing into your server to check status! This guide provides a ready-to-use VPS automation script collection—system health checks, automated log cleanup, and resource threshold alerts—keeping your server guarded 24/7."
date: 2026-08-15T08:00:00+08:00
lastmod: 2026-08-15T08:00:00+08:00
slug: "vps-automation-script-collection"
image: /images/posts/vps-automation-script-collection/featured-en.png
tags: ["VPS", "Automation", "Shell Script", "DevOps", "Monitoring", "Log Management", "Alerting", "Cron", "systemd"]
categories: ["DevOps"]
aliases: [/en/post/vps-automation-script-collection/]
draft: false
---

## Introduction

Have you ever experienced these scenarios?

- You arrive at the office in the morning and find your website is down because the disk was filled with logs overnight;
- You check your monthly bill and realize a VPS has been running at 90% CPU for a whole month without anyone noticing;
- Your server got brute-forced because SSH failed login logs堆积了几个 G and you never cleaned them;
- Your SSL certificate expired and caused service interruption because you forgot to set a calendar reminder.

**The root cause of all these problems is the same: lack of automation.**

Manually logging into servers to check status is always reactive—by the time you discover the problem, users have already complained. This article will build you a **ready-to-use VPS automation script collection**, covering three core scenarios: system inspection, log cleanup, and resource alerts. Paired with Cron scheduled tasks, your server will have 24/7无人值守守护.

---

## Section 1: Script Architecture Design

Before writing code, let's clarify our design principles:

| Principle | Description |
|-----------|-------------|
| **Modular** | Each script runs independently, can be called individually or combined |
| **Zero Dependencies** | Only uses system-built-in tools (bash, awk, grep, curl, etc.), no extra installations needed |
| **Configurable** | Control thresholds, notification methods via environment variables or config files |
| **Extensible** | Adding new inspection items only requires adding one function |

We will create the following file structure:

```
~/vps-automation/
├── config.sh          # Unified configuration file
├── health-check.sh    # System health inspection
├── log-cleanup.sh     # Automated log cleanup
├── alert.sh           # Alert notification (multi-channel support)
└── run-all.sh         # One-click execution of all tasks
```

---

## Section 2: Unified Configuration File

`config.sh` is the shared configuration center for all scripts:

```bash
#!/bin/bash
# VPS Automation - Unified Configuration
# Override defaults via environment variables

# === Base Paths ===
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="${LOG_DIR:-/var/log/vps-automation}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/vps-automation}"
STATE_FILE="${STATE_FILE:-${LOG_DIR}/.state}"

# === Alert Configuration ===
ALERT_ENABLED="${ALERT_ENABLED:-true}"
ALERT_EMAIL="${ALERT_EMAIL:-}"           # Email alerts
ALERT_WEBHOOK="${ALERT_WEBHOOK:-}"       # Webhook (Feishu/DingTalk/Slack)
ALERT_TELEGRAM="${ALERT_TELEGRAM:-}"     # Telegram Bot Token
ALERT_CHAT_ID="${ALERT_CHAT_ID:-}"       # Telegram Chat ID

# === Resource Thresholds ===
THRESHOLD_CPU="${THRESHOLD_CPU:-85}"     # CPU usage alert threshold
THRESHOLD_MEM="${THRESHOLD_MEM:-90}"     # Memory usage alert threshold
THRESHOLD_DISK="${THRESHOLD_DISK:-85}"   # Disk usage alert threshold
THRESHOLD_LOAD="${THRESHOLD_LOAD:-}"     # Load alert threshold (default = CPU cores)

# === Log Cleanup ===
LOG_RETENTION_DAYS="${LOG_RETENTION_DAYS:-30}"     # Log retention days
JOURNAL_RETENTION_DAYS="${JOURNAL_RETENTION_DAYS:-14}"  # systemd journal retention
CLEAN_TMP_DAYS="${CLEAN_TMP_DAYS:-7}"              # /tmp cleanup days

# === Calculate default load threshold ===
if [[ -z "$THRESHOLD_LOAD" ]]; then
    THRESHOLD_LOAD=$(nproc 2>/dev/null || echo 1)
fi

# === Ensure directories exist ===
mkdir -p "${LOG_DIR}" "${BACKUP_DIR}"
```

---

## Section 3: System Health Inspection Script

`health-check.sh` performs comprehensive server status checks:

```bash
#!/bin/bash
# VPS Automation - System Health Inspection
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/config.sh"

TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
REPORT=""
ISSUES=0

# Color definitions
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

echo "=== VPS Health Inspection $(date '+%Y-%m-%d %H:%M:%S') ==="

# 1. CPU Usage
CPU_USAGE=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | cut -d'%' -f1 2>/dev/null || echo "0")
CPU_USAGE=${CPU_USAGE%.*}
if [[ -n "$CPU_USAGE" && "$CPU_USAGE" -gt "$THRESHOLD_CPU" ]]; then
    report "ERROR" "CPU usage ${CPU_USAGE}% exceeds threshold ${THRESHOLD_CPU}%"
elif [[ -n "$CPU_USAGE" && "$CPU_USAGE" -gt $((THRESHOLD_CPU - 10)) ]]; then
    report "WARN" "CPU usage ${CPU_USAGE}% approaching threshold"
else
    report "OK" "CPU usage ${CPU_USAGE:-normal}"
fi

# 2. Memory Usage
MEM_INFO=$(free | grep Mem)
MEM_TOTAL=$(echo "$MEM_INFO" | awk '{print $2}')
MEM_USED=$(echo "$MEM_INFO" | awk '{print $3}')
MEM_PCT=$(awk "BEGIN {printf \"%d\", ($MEM_USED/$MEM_TOTAL)*100}")

if [[ "$MEM_PCT" -gt "$THRESHOLD_MEM" ]]; then
    report "ERROR" "Memory usage ${MEM_PCT}% exceeds threshold ${THRESHOLD_MEM}%"
elif [[ "$MEM_PCT" -gt $((THRESHOLD_MEM - 10)) ]]; then
    report "WARN" "Memory usage ${MEM_PCT}% approaching threshold"
else
    report "OK" "Memory usage ${MEM_PCT}% (${MEM_USED}MB/${MEM_TOTAL}MB)"
fi

# 3. Disk Usage
DISK_ISSUES=""
while IFS= read -r line; do
    USE_PCT=$(echo "$line" | awk '{print $5}' | tr -d '%')
    MOUNT=$(echo "$line" | awk '{print $6}')
    if [[ "$USE_PCT" -gt "$THRESHOLD_DISK" ]]; then
        DISK_ISSUES+=" ${MOUNT}=${USE_PCT}%"
    fi
done < <(df -h --output=pcent,target 2>/dev/null | tail -n +2)

if [[ -n "$DISK_ISSUES" ]]; then
    report "ERROR" "Disk space insufficient:${DISK_ISSUES}"
else
    report "OK" "Disk space normal"
fi

# 4. System Load
LOAD=$(cat /proc/loadavg | awk '{print $1}')
LOAD_INT=${LOAD%.*}
if [[ "$LOAD_INT" -ge "$THRESHOLD_LOAD" ]]; then
    report "WARN" "System load ${LOAD} approaching/exceeding core count ${THRESHOLD_LOAD}"
else
    report "OK" "System load ${LOAD}"
fi

# 5. SSH Brute Force Detection
FAILED_LOGINS=$(grep -c "Failed password" /var/log/auth.log 2>/dev/null || echo "0")
if [[ "$FAILED_LOGINS" -gt 100 ]]; then
    report "WARN" "Detected ${FAILED_LOGINS} SSH failed logins, possible brute force attack"
else
    report "OK" "SSH login normal (failed attempts: ${FAILED_LOGINS})"
fi

# 6. SSL Certificate Expiry Check
CERT_HOST="${CERT_HOST:-$(hostname -f 2>/dev/null || echo 'localhost')}"
if command -v openssl &>/dev/null; then
    CERT_EXPIRY=$(echo | openssl s_client -servername "${CERT_HOST}" -connect "${CERT_HOST}:443" 2>/dev/null | \
        openssl x509 -noout -dates 2>/dev/null | grep "notAfter" | cut -d= -f2)
    if [[ -n "$CERT_EXPIRY" ]]; then
        DAYS_LEFT=$(( ($(date -d "$CERT_EXPIRY" +%s) - $(date +%s)) / 86400 ))
        if [[ "$DAYS_LEFT" -lt 7 ]]; then
            report "ERROR" "SSL certificate expires in ${DAYS_LEFT} days: ${CERT_EXPIRY}"
        elif [[ "$DAYS_LEFT" -lt 30 ]]; then
            report "WARN" "SSL certificate expires in ${DAYS_LEFT} days"
        else
            report "OK" "SSL certificate valid for ${DAYS_LEFT} more days"
        fi
    fi
fi

# 7. Critical Service Status
for svc in sshd nginx docker; do
    if systemctl is-active --quiet "${svc}" 2>/dev/null; then
        report "OK" "Service ${svc} is running"
    else
        report "WARN" "Service ${svc} is not running"
    fi
done

# 8. Zombie Process Detection
ZOMBIE_COUNT=$(ps aux | awk '$8=="Z"' | wc -l)
if [[ "$ZOMBIE_COUNT" -gt 0 ]]; then
    report "WARN" "Detected ${ZOMBIE_COUNT} zombie processes"
else
    report "OK" "No zombie processes"
fi

# Output report
echo -e "$REPORT"

# Save report
REPORT_FILE="${LOG_DIR}/health-$(date +%Y%m%d-%H%M%S).txt"
echo -e "$REPORT" > "$REPORT_FILE"
echo "Report saved: ${REPORT_FILE}"

# Send alert
if [[ "$ALERT_ENABLED" == "true" && "$ISSUES" -gt 0 ]]; then
    source "${SCRIPT_DIR}/alert.sh"
    send_alert "VPS Health Inspection Alert" "$REPORT" "$ISSUES"
fi

exit ${ISSUES}
```

---

## Section 4: Automated Log Cleanup Script

`log-cleanup.sh` intelligently cleans various logs to prevent disk exhaustion:

```bash
#!/bin/bash
# VPS Automation - Automated Log Cleanup
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/config.sh"

echo "=== VPS Log Cleanup $(date '+%Y-%m-%d %H:%M:%S') ==="

# 1. Clean systemd journal
if command -v journalctl &>/dev/null; then
    BEFORE=$(du -sh /var/log/journal 2>/dev/null | awk '{print $1}' || echo "0")
    journalctl --vacuum-time="${JOURNAL_RETENTION_DAYS}d" 2>/dev/null || true
    AFTER=$(du -sh /var/log/journal 2>/dev/null | awk '{print $1}' || echo "0")
    echo "✅ systemd journal: ${BEFORE} → ${AFTER} (retaining ${JOURNAL_RETENTION_DAYS} days)"
fi

# 2. Clean application logs (by retention days)
find /var/log -name "*.log" -type f -mtime +${LOG_RETENTION_DAYS} 2>/dev/null | while read -r f; do
    SIZE=$(du -sh "$f" 2>/dev/null | awk '{print $1}')
    rm -f "$f"
    echo "🗑️  Deleted: $f (${SIZE})"
done

# 3. Compress large uncompressed log files
find /var/log -name "*.log" -type f -size +100M 2>/dev/null | while read -r f; do
    if [[ ! -f "${f}.gz" ]]; then
        gzip -f "$f" 2>/dev/null && echo "📦 Compressed: ${f}.gz"
    fi
done

# 4. Clean /tmp temporary files
find /tmp -type f -mtime +${CLEAN_TMP_DAYS} -delete 2>/dev/null && \
    echo "🧹 Cleaned /tmp files older than ${CLEAN_TMP_DAYS} days"

# 5. Clean Docker garbage (if Docker is running)
if command -v docker &>/dev/null; then
    echo "🔄 Docker garbage cleanup..."
    docker system prune -f --filter "until=720h" 2>/dev/null || true
    docker volume prune -f 2>/dev/null || true
    echo "✅ Docker cleanup complete"
fi

# 6. Clean apt cache
if command -v apt-get &>/dev/null; then
    apt-get clean -y 2>/dev/null && echo "🧹 apt cache cleaned"
fi

# 7. Clean yum/dnf cache
if command -v dnf &>/dev/null; then
    dnf clean all 2>/dev/null && echo "🧹 dnf cache cleaned"
elif command -v yum &>/dev/null; then
    yum clean all 2>/dev/null && echo "🧹 yum cache cleaned"
fi

# 8. Show disk status after cleanup
echo ""
echo "=== Disk Status After Cleanup ==="
df -h | grep -E "^Filesystem|/dev/"

echo ""
echo "=== Log Cleanup Complete ==="
```

---

## Section 5: Alert Notification Script

`alert.sh` supports multiple notification channels:

```bash
#!/bin/bash
# VPS Automation - Alert Notification
# Supports: Email, Webhook (Feishu/DingTalk/Slack), Telegram

send_alert() {
    local title="$1"
    local message="$2"
    local issue_count="${3:-0}"

    # Only send alerts when there are actual issues
    if [[ "$issue_count" -eq 0 ]]; then
        return 0
    fi

    local hostname=$(hostname)
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    local severity="WARNING"
    [[ "$issue_count" -gt 2 ]] && severity="CRITICAL"

    # === Feishu (Lark) Webhook ===
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
                    "content": "**Server:** ${hostname}\n**Time:** ${timestamp}\n**Severity:** ${severity}\n\n${message}",
                    "tag": "lark_md"
                }
            },
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"content": "View Server Status", "tag": "lark_md"},
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
            >/dev/null 2>&1 || echo "⚠️ Feishu alert send failed"
    fi

    # === DingTalk Webhook ===
    if [[ -n "$ALERT_WEBHOOK" && "$ALERT_WEBHOOK" == *"dingtalk"* ]]; then
        local payload=$(cat <<EOF
{
    "msgtype": "markdown",
    "markdown": {
        "title": "${title}",
        "text": "### 🚨 ${title}\n\n**Server:** ${hostname}\n**Time:** ${timestamp}\n**Severity:** ${severity}\n\n${message}\n\n> Please handle promptly!"
    }
}
EOF
)
        curl -s -X POST -H "Content-Type: application/json" -d "$payload" "$ALERT_WEBHOOK" \
            >/dev/null 2>&1 || echo "⚠️ DingTalk alert send failed"
    fi

    # === Telegram ===
    if [[ -n "$ALERT_TELEGRAM" && -n "$ALERT_CHAT_ID" ]]; then
        local tg_text="🚨 *${title}*\n\n🖥 Server: ${hostname}\n⏰ Time: ${timestamp}\n🔴 Severity: ${severity}\n\n${message}"
        curl -s -X POST \
            "https://api.telegram.org/bot${ALERT_TELEGRAM}/sendMessage" \
            -d chat_id="$ALERT_CHAT_ID" \
            -d parse_mode="Markdown" \
            -d text="$tg_text" \
            >/dev/null 2>&1 || echo "⚠️ Telegram alert send failed"
    fi

    # === Email ===
    if [[ -n "$ALERT_EMAIL" && -n "$(command -v mail)" ]]; then
        echo -e "${message}" | mail -s "[${severity}] ${title} - ${hostname}" "$ALERT_EMAIL" \
            2>/dev/null || echo "⚠️ Email alert send failed"
    fi

    # === System Log ===
    logger -t "vps-automation" "${severity}: ${title} - ${hostname} - Issues: ${issue_count}"
}

# Export function for other scripts
export -f send_alert
```

---

## Section 6: One-Click Execution Script

`run-all.sh` integrates all tasks:

```bash
#!/bin/bash
# VPS Automation - One-Click Execution of All Tasks
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="${SCRIPT_DIR}/../log/run-$(date +%Y%m%d-%H%M%S).log"

mkdir -p "$(dirname "$LOG_FILE")"

echo "========================================" | tee "$LOG_FILE"
echo "  VPS Automation - Full Execution" | tee -a "$LOG_FILE"
echo "  Time: $(date '+%Y-%m-%d %H:%M:%S')" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"

cd "$SCRIPT_DIR"

# 1. Health Inspection
echo "" | tee -a "$LOG_FILE"
echo "[1/3] System Health Inspection..." | tee -a "$LOG_FILE"
bash "${SCRIPT_DIR}/health-check.sh" 2>&1 | tee -a "$LOG_FILE" || true

# 2. Log Cleanup
echo "" | tee -a "$LOG_FILE"
echo "[2/3] Log Cleanup..." | tee -a "$LOG_FILE"
bash "${SCRIPT_DIR}/log-cleanup.sh" 2>&1 | tee -a "$LOG_FILE"

# 3. Resource Usage Summary
echo "" | tee -a "$LOG_FILE"
echo "[3/3] Resource Status Snapshot..." | tee -a "$LOG_FILE"
echo "--- CPU ---" | tee -a "$LOG_FILE"
top -bn1 | head -5 | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"
echo "--- Memory ---" | tee -a "$LOG_FILE"
free -h | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"
echo "--- Disk ---" | tee -a "$LOG_FILE"
df -h | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"
echo "  Execution Complete: $(date '+%Y-%m-%d %H:%M:%S')" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"
```

---

## Section 7: Configure Scheduled Tasks

### Using Cron

Edit crontab:

```bash
crontab -e
```

Add the following entries:

```cron
# Run full inspection and cleanup every day at 6 AM
0 6 * * * /root/vps-automation/run-all.sh >> /root/vps-automation/logs/cron.log 2>&1

# Run lightweight health check every hour (alerts only, no cleanup)
0 * * * * /root/vps-automation/health-check.sh >> /root/vps-automation/logs/hourly-check.log 2>&1

# Run deep cleanup every Sunday at 3 AM
0 3 * * 0 /root/vps-automation/log-cleanup.sh --deep-clean >> /root/vps-automation/logs/weekly-cleanup.log 2>&1
```

### Using systemd timer (Recommended)

Create timer unit file:

```ini
# /etc/systemd/system/vps-health-check.timer
[Unit]
Description=VPS Health Check Timer

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
Description=VPS Health Check Service

[Service]
Type=oneshot
User=root
WorkingDirectory=/root/vps-automation
ExecStart=/bin/bash health-check.sh
```

Enable the timer:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now vps-health-check.timer
sudo systemctl status vps-health-check.timer
```

---

## Section 8: Configure Alert Channels

### Feishu (Lark) Bot Webhook

1. Add a custom bot to your Feishu group
2. Copy the Webhook URL
3. Edit `config.sh`:
   ```bash
   ALERT_WEBHOOK="https://open.feishu.cn/open-apis/bot/v2/hook/xxxxx"
   ```

### DingTalk Bot Webhook

1. Add a custom bot to your DingTalk group (choose signature method)
2. Copy the Webhook URL
3. Edit `config.sh`:
   ```bash
   ALERT_WEBHOOK="https://oapi.dingtalk.com/robot/send?access_token=xxxxx"
   ```

### Telegram Bot

1. Find @BotFather in Telegram to create a bot
2. Get the Bot Token
3. Add the bot to a group and get the Chat ID
4. Edit `config.sh`:
   ```bash
   ALERT_TELEGRAM="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
   ALERT_CHAT_ID="-1001234567890"
   ```

---

## Section 9: Advanced — Multi-Server Management

If you have multiple VPS instances, you can manage them all from one script:

```bash
#!/bin/bash
# Batch health inspection across multiple servers
SERVERS=("user@vps1.example.com" "user@vps2.example.com" "user@vps3.example.com")

for server in "${SERVERS[@]}"; do
    echo "=== Inspecting ${server} ==="
    ssh -o ConnectTimeout=10 "${server}" "bash <(curl -s https://raw.githubusercontent.com/yourrepo/vps-automation/main/run-all.sh)" \
        || echo "❌ Cannot connect to ${server}"
    echo ""
done
```

Paired with **SSH key passwordless login** and **Ansible**, you can achieve true batch automated operations.

---

## Section 10: Summary

The core value of this VPS automation script collection:

| Capability | Benefit |
|------------|---------|
| **System Inspection** | Automatically detect CPU/memory/disk/service anomalies, no longer rely on manual checks |
| **Log Cleanup** | Prevent disk from being filled by logs, automatically compress and archive historical logs |
| **Alert Notification** | Get notified第一时间 when problems occur, supports Feishu/DingTalk/Telegram/Email |
| **Scheduled Execution** | Cron or systemd timer ensures tasks run on time, 24/7 guarding |

**Next steps:**

1. Adjust threshold configurations in `config.sh` based on your actual needs
2. Choose your preferred alert channel and configure the Webhook
3. Set up systemd timer instead of Cron (more reliable)
4. Review inspection reports regularly and continuously optimize scripts

> 💡 **Remember: The best operations is the kind of operations that lets you not need to operate.** Hand over repetitive work to scripts, and you only need to handle real problems when alerts arrive.

---

## Appendix: Quick Deployment Commands

```bash
# One-click deployment
mkdir -p ~/vps-automation && cd ~/vps-automation
# Save the above scripts as corresponding files
chmod +x *.sh
# Configure alert channels
vim config.sh
# Set up scheduled tasks
crontab -e
# Test immediately
./run-all.sh
```
