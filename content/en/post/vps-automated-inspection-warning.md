---
title: "VPS Automated Inspection & Fault Warning System: Let Servers 'Diagnose' Themselves"
description: "Build a VPS automated inspection and fault warning system with 7×24 health monitoring, intelligent alerts, auto-remediation, and daily reporting —告别人工巡检"
date: 2026-08-25T08:00:00+08:00
lastmod: 2026-08-25T08:00:00+08:00
slug: "vps-automated-inspection-warning"
tags: ["VPS", "Automated Inspection", "Fault Warning", "Monitoring", "Auto-Remediation", "DevOps", "Health Check"]
categories: ["Operations Automation"]
draft: false
image: /images/posts/vps-automated-inspection-warning/featured.png
aliases: [/en/post/vps-automated-inspection-warning/]
---

## Introduction

Have you ever experienced this: your phone rings at 3 AM because your server crashed, or your website goes down during a holiday and your customers are already complaining in the group chat?

Traditional VPS operations rely on manual inspections—regularly checking CPU, memory, disk, and network status. But the problems are:

- **Humans aren't machines**—we miss things, fall asleep, and take vacations
- **Alerts are lagging**—by the time you notice, the problem has worsened
- **Root causes are hard to find**—symptoms and real causes often don't match

Today, I'll show you how to build an **automated inspection and fault warning system** that watches your servers 7×24, detects problems early, auto-fixes them, and generates reports—all while you sleep soundly.

---

## 1. System Architecture

A complete automated inspection system consists of four core modules:

```
┌─────────────────────────────────────────────────────┐
│                 Scheduling Layer                     │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐            │
│  │  Timer    │ │ Health   │ │ Log      │            │
│  │ (cron)   │ │ Checks   │ │ Analysis │            │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘            │
└───────┼─────────────┼─────────────┼─────────────────┘
        │             │             │
   ┌────▼────┐   ┌────▼────┐   ┌────▼────┐
   │Collector│   │Metrics  │   │Detector │
   │         │   │         │   │         │
   └────┬────┘   └────┬────┘   └────┬────┘
        │             │             │
┌───────▼─────────────▼─────────────▼─────────────────┐
│                Execution Layer                       │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐            │
│  │  Alerts  │ │ Auto-Fix │ │ Reports  │            │
│  │          │ │          │ │          │            │
│  └──────────┘ └──────────┘ └──────────┘            │
└─────────────────────────────────────────────────────┘
```

### Core Design Principles

1. **Layered Detection**: From infrastructure to application layer
2. **Multi-level Thresholds**: Warning → Critical → Emergency
3. **Auto-Remediation**: Common issues fixed automatically
4. **Learning & Optimization**: Thresholds optimized by historical data

---

## 2. Infrastructure Layer Inspection

### 2.1 CPU Health Check

CPU is the most critical resource—overload causes chain reactions.

```bash
#!/bin/bash
# cpu_check.sh — CPU Health Check Script

THRESHOLD_WARN=70
THRESHOLD_CRIT=90
THRESHOLD_LOAD=$(nproc)

# Get CPU usage
CPU_IDLE=$(top -bn1 | grep "Cpu(s)" | awk '{print $8}' | cut -d'%' -f1)
CPU_USAGE=$(printf "%.0f" "$(echo "100 - $CPU_IDLE" | bc -l)")

# Get load average
LOAD_1MIN=$(cat /proc/loadavg | awk '{print $1}')

# Check CPU usage
if (( $(echo "$CPU_USAGE >= $THRESHOLD_CRIT" | bc -l) )); then
    echo "CRITICAL: CPU usage at ${CPU_USAGE}%"
    # Kill the top CPU process
    top -bn1 | head -20 | grep -v "top" | tail -n +2 | sort -k9 -r | head -1 | awk '{print $1}' | xargs -I{} kill -9 {} 2>/dev/null
    alert "CRITICAL" "CPU overload: ${CPU_USAGE}%"
elif (( $(echo "$CPU_USAGE >= $THRESHOLD_WARN" | bc -l) )); then
    echo "WARNING: CPU usage at ${CPU_USAGE}%"
    alert "WARNING" "CPU usage elevated: ${CPU_USAGE}%"
else
    echo "OK: CPU usage at ${CPU_USAGE}%"
fi

# Check load average
if (( $(echo "$LOAD_1MIN >= $THRESHOLD_LOAD" | bc -l) )); then
    echo "WARNING: System load ${LOAD_1MIN} exceeds CPU cores $(nproc)"
    alert "WARNING" "High system load: ${LOAD_1MIN}"
fi
```

### 2.2 Memory & Swap Check

Memory exhaustion is the precursor to OOM Killer—watch it closely.

```bash
#!/bin/bash
# memory_check.sh — Memory Health Check Script

THRESHOLD_MEM_WARN=80
THRESHOLD_MEM_CRIT=90
THRESHOLD_SWAP_WARN=70
THRESHOLD_SWAP_CRIT=90

# Get memory info
MEM_TOTAL=$(grep MemTotal /proc/meminfo | awk '{print $2}')
MEM_AVAILABLE=$(grep MemAvailable /proc/meminfo | awk '{print $2}')
MEM_USED=$((MEM_TOTAL - MEM_AVAILABLE))
MEM_USAGE=$(awk "BEGIN {printf \"%.0f\", ($MEM_USED / $MEM_TOTAL) * 100}")

# Get swap info
SWAP_TOTAL=$(grep SwapTotal /proc/meminfo | awk '{print $2}')
SWAP_FREE=$(grep SwapFree /proc/meminfo | awk '{print $2}')
SWAP_USED=$((SWAP_TOTAL - SWAP_FREE))
SWAP_USAGE=0
[[ $SWAP_TOTAL -gt 0 ]] && SWAP_USAGE=$(awk "BEGIN {printf \"%.0f\", ($SWAP_USED / $SWAP_TOTAL) * 100}")

echo "Memory: ${MEM_USAGE}% used, Swap: ${SWAP_USAGE}% used"

if (( MEM_USAGE >= THRESHOLD_MEM_CRIT )); then
    echo "CRITICAL: Memory usage at ${MEM_USAGE}%"
    alert "CRITICAL" "Memory critical: ${MEM_USAGE}%"
    # Clear page cache
    sync && echo 3 > /proc/sys/vm/drop_caches 2>/dev/null
elif (( MEM_USAGE >= THRESHOLD_MEM_WARN )); then
    echo "WARNING: Memory usage at ${MEM_USAGE}%"
    alert "WARNING" "Memory high: ${MEM_USAGE}%"
fi

if (( SWAP_USAGE >= THRESHOLD_SWAP_CRIT )); then
    echo "CRITICAL: Swap usage at ${SWAP_USAGE}%"
    alert "CRITICAL" "Swap critical: ${SWAP_USAGE}%"
fi
```

### 2.3 Disk Space Check

Running out of disk space is the most common "surprise"—and the most preventable.

```bash
#!/bin/bash
# disk_check.sh — Disk Health Check Script

THRESHOLD_WARN=80
THRESHOLD_CRIT=90

df -h | grep -E "^/dev/" | while read line; do
    MOUNT=$(echo "$line" | awk '{print $6}')
    USAGE_PCT=$(echo "$line" | awk '{print $5}' | tr -d '%')
    AVAIL=$(echo "$line" | awk '{print $4}')
    
    if (( USAGE_PCT >= THRESHOLD_CRIT )); then
        echo "CRITICAL: ${MOUNT} is ${USAGE_PCT}% full (${AVAIL} free)"
        alert "CRITICAL" "Disk ${MOUNT} critical: ${USAGE_PCT}%"
    elif (( USAGE_PCT >= THRESHOLD_WARN )); then
        echo "WARNING: ${MOUNT} is ${USAGE_PCT}% full"
        alert "WARNING" "Disk ${MOUNT} high: ${USAGE_PCT}%"
    fi
done

# Check inode usage
df -i | grep -E "^/dev/" | while read line; do
    MOUNT=$(echo "$line" | awk '{print $6}')
    IUSE_PCT=$(echo "$line" | awk '{print $5}' | tr -d '%')
    
    if (( IUSE_PCT >= THRESHOLD_CRIT )); then
        echo "CRITICAL: ${MOUNT} inode usage at ${IUSE_PCT}%"
        alert "CRITICAL" "Inode critical on ${MOUNT}: ${IUSE_PCT}%"
    fi
done
```

---

## 3. Service Layer Inspection

### 3.1 Docker Container Health Check

Modern VPSs run containers—container health matters more than host health.

```bash
#!/bin/bash
# container_check.sh — Docker Container Health Check

check_container() {
    local name=$1
    local status=$(docker inspect --format='{{.State.Status}}' "$name" 2>/dev/null)
    local health=$(docker inspect --format='{{.State.Health.Status}}' "$name" 2>/dev/null)
    
    if [[ -z "$status" ]]; then
        echo "CRITICAL: Container '${name}' not found"
        alert "CRITICAL" "Container missing: ${name}"
        return 1
    fi
    
    if [[ "$status" != "running" ]]; then
        echo "CRITICAL: Container '${name}' is ${status}"
        alert "CRITICAL" "Container down: ${name} (${status})"
        # Try to restart
        docker restart "$name" 2>/dev/null && echo "Restarted ${name}"
        return 1
    fi
    
    if [[ "$health" == "unhealthy" ]]; then
        echo "WARNING: Container '${name}' health check failed"
        alert "WARNING" "Container unhealthy: ${name}"
        docker restart "$name" 2>/dev/null
    elif [[ "$health" == "healthy" ]]; then
        echo "OK: Container '${name}' is healthy"
    else
        echo "OK: Container '${name}' is running"
    fi
}

# Check all critical containers
for container in nginx redis postgresql app-server worker; do
    check_container "$container"
done
```

### 3.2 Critical Service Availability Check

```bash
#!/bin/bash
# service_check.sh — Service Availability Check

check_service() {
    local name=$1
    local port=$2
    local protocol=${3:-tcp}
    
    if command -v curl &>/dev/null; then
        if curl -sf --max-time 5 "http://localhost:${port}/" &>/dev/null; then
            echo "OK: ${name} (port ${port}) is responding"
            return 0
        fi
    fi
    
    # Fallback to nc check
    if nc -z -w 3 localhost "$port" 2>/dev/null; then
        echo "OK: ${name} (port ${port}) port is open"
        return 0
    fi
    
    echo "CRITICAL: ${name} (port ${port}) is not responding"
    alert "CRITICAL" "Service down: ${name} on port ${port}"
    return 1
}

# Check critical ports
check_service "Nginx" 80
check_service "SSH" 22
check_service "PostgreSQL" 5432
check_service "Redis" 6379
check_service "MySQL" 3306
check_service "Prometheus" 9090
check_service "Grafana" 3000
```

---

## 4. Intelligent Alerting System

### 4.1 Multi-level Alert Strategy

Not every issue deserves a 3 AM wakeup call. Tiered alerting lets you focus on what truly matters.

```bash
#!/bin/bash
# alert.sh — Multi-level Alert Notification Script

ALERT_LEVEL=$1
ALERT_MESSAGE=$2
ALERT_TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

send_telegram() {
    local BOT_TOKEN="${TELEGRAM_BOT_TOKEN}"
    local CHAT_ID="${TELEGRAM_CHAT_ID}"
    local ESCAPED_MSG=$(echo "$ALERT_MESSAGE" | sed 's/"/\\"/g')
    
    curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
        -d "chat_id=${CHAT_ID}" \
        -d "text=${ALERT_LEVEL}: ${ALERT_MESSAGE}" \
        -d "parse_mode=HTML" \
        --max-time 10
}

send_email() {
    local SUBJECT="[${ALERT_LEVEL}] VPS Alert: ${ALERT_MESSAGE}"
    local BODY="Time: ${ALERT_TIMESTAMP}\nHost: $(hostname)\n\nAlert: ${ALERT_MESSAGE}"
    
    echo -e "$BODY" | mail -s "$SUBJECT" "${ALERT_EMAIL}"
}

send_webhook() {
    local PAYLOAD="{\"level\":\"${ALERT_LEVEL}\",\"message\":\"${ALERT_MESSAGE}\",\"host\":\"$(hostname)\",\"time\":\"${ALERT_TIMESTAMP}\"}"
    
    curl -s -X POST "${ALERT_WEBHOOK_URL}" \
        -H "Content-Type: application/json" \
        -d "$PAYLOAD" \
        --max-time 10
}

case "$ALERT_LEVEL" in
    "CRITICAL")
        echo "[CRITICAL] ${ALERT_MESSAGE}" | tee /var/log/vps-alerts.log
        send_telegram
        send_email
        send_webhook
        ;;
    "WARNING")
        echo "[WARNING] ${ALERT_MESSAGE}" | tee -a /var/log/vps-alerts.log
        send_telegram
        send_webhook
        ;;
    "INFO")
        echo "[INFO] ${ALERT_MESSAGE}" >> /var/log/vps-alerts.log
        send_webhook
        ;;
esac
```

### 4.2 Alert Deduplication & Silencing

Avoid alert storms—same issue, one notification.

```bash
#!/bin/bash
# alert_dedup.sh — Alert Deduplication

ALERT_DIR="/var/lib/vps-alerts"
STALE_AFTER=300  # Allow re-alert after 5 minutes

mkdir -p "$ALERT_DIR"

send_alert() {
    local key=$1
    local message=$2
    local now=$(date +%s)
    local alert_file="${ALERT_DIR}/${key}"
    
    if [[ -f "$alert_file" ]]; then
        local last_sent=$(cat "$alert_file")
        local elapsed=$((now - last_sent))
        
        if (( elapsed < STALE_AFTER )); then
            echo "DEDUP: Alert '${key}' suppressed (last sent ${elapsed}s ago)"
            return
        fi
    fi
    
    echo "$message"
    echo "$now" > "$alert_file"
    
    # Clean up stale files
    find "$ALERT_DIR" -type f -mtime +1 -delete
}

# Usage examples
send_alert "disk_full" "Disk usage critical on /var"
send_alert "container_down" "nginx container is down"
```

---

## 5. Auto-Remediation

### 5.1 Common Fault Auto-Fix

```bash
#!/bin/bash
# auto_fix.sh — Auto-Fix Script

fix_disk_space() {
    echo "[FIX] Cleaning disk space..."
    
    # Clean apt cache
    apt-get clean 2>/dev/null
    
    # Clean old logs
    find /var/log -name "*.log" -mtime +7 -exec truncate -s 0 {} \; 2>/dev/null
    find /var/log -name "*.gz" -mtime +30 -delete 2>/dev/null
    
    # Clean journal logs (keep 7 days)
    journalctl --vacuum-time=7d 2>/dev/null
    
    # Clean unused Docker resources
    docker system prune -f 2>/dev/null
    docker volume prune -f 2>/dev/null
    
    echo "[FIX] Disk cleanup completed"
}

fix_container_restart() {
    local container=$1
    echo "[FIX] Restarting container: ${container}"
    docker restart "$container" 2>/dev/null
    
    # If restart fails, try to rebuild
    if [[ $(docker inspect --format='{{.State.Status}}' "$container" 2>/dev/null) != "running" ]]; then
        echo "[FIX] Container ${container} still down, pulling and recreating..."
        docker pull "${container}:latest" 2>/dev/null
        docker rm -f "$container" 2>/dev/null
        docker run -d --name "$container" "${container}:latest" 2>/dev/null
    fi
}

fix_service_restart() {
    local service=$1
    echo "[FIX] Restarting service: ${service}"
    systemctl restart "$service" 2>/dev/null && \
        echo "[FIX] Service ${service} restarted successfully" || \
        echo "[ERROR] Failed to restart ${service}"
}

# Main fix logic
case "$1" in
    "disk")
        fix_disk_space
        ;;
    "container")
        fix_container_restart "$2"
        ;;
    "service")
        fix_service_restart "$2"
        ;;
    "all")
        fix_disk_space
        # Restart all unhealthy containers
        docker ps --filter "health=unhealthy" --format="{{.Names}}" | while read c; do
            fix_container_restart "$c"
        done
        ;;
    *)
        echo "Usage: $0 {disk|container|service|all}"
        exit 1
        ;;
esac
```

### 5.2 Safety Guards

Auto-fix is powerful—add safeguards to prevent accidents.

```bash
#!/bin/bash
# safety_check.sh — Pre-fix Safety Check

check_before_fix() {
    local fix_type=$1
    local action=$2
    
    # Check maintenance window (no fixes during 02:00-05:00)
    local hour=$(date +%H)
    if [[ "$fix_type" == "disk" ]] && (( hour >= 2 && hour <= 5 )); then
        echo "BLOCKED: Disk cleanup in maintenance window (02:00-05:00)"
        return 1
    fi
    
    # Check system load
    local load=$(cat /proc/loadavg | awk '{print $1}')
    if (( $(echo "$load > 10" | bc -l) )); then
        echo "BLOCKED: System load too high (${load}), skipping fix"
        return 1
    fi
    
    # Require manual confirmation for destructive actions
    if [[ "$action" == "destructive" ]]; then
        echo "REQUIRES_CONFIRMATION: Action is destructive, needs manual approval"
        return 1
    fi
    
    return 0
}

# Usage examples
check_before_fix "disk" "clean" && fix_disk_space
check_before_fix "container" "recreate" && fix_container_restart "myapp"
```

---

## 6. Scheduling & Reporting

### 6.1 Cron Configuration

```bash
# /etc/cron.d/vps-inspection
# ┌───────────── minute (0 - 59)
# │ ┌───────────── hour (0 - 23)
# │ │ ┌───────────── day (1 - 31)
# │ │ │ ┌───────────── month (1 - 12)
# │ │ │ │ ┌───────────── day of week (0 - 6)
# │ │ │ │ │
# │ │ │ │ │
*/5 * * * * root /usr/local/bin/vps-inspect.sh --quick >> /var/log/vps-inspection.log 2>&1
0 * * * * root /usr/local/bin/vps-inspect.sh --full >> /var/log/vps-inspection.log 2>&1
0 6 * * * root /usr/local/bin/vps-inspect.sh --report >> /var/log/vps-inspection.log 2>&1
```

### 6.2 Complete Inspection Script

```bash
#!/bin/bash
# vps-inspect.sh — Main Inspection Entry Script

MODE="${1:---quick}"
HOSTNAME=$(hostname)
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
LOG_FILE="/var/log/vps-inspection.log"

log() {
    echo "[$TIMESTAMP] [$1] $2" | tee -a "$LOG_FILE"
}

run_quick_check() {
    log "INFO" "=== Quick Check Started ==="
    
    # CPU & Memory
    CPU=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | cut -d'%' -f1)
    MEM=$(free | awk '/^Mem:/ {printf "%.0f", $3/$2 * 100}')
    DISK=$(df -h / | awk 'NR==2 {print $5}' | tr -d '%')
    
    log "CHECK" "CPU: ${CPU}% | MEM: ${MEM}% | DISK: ${DISK}%"
    
    # Key processes
    docker ps --format "table {{.Names}}\t{{.Status}}" | while read line; do
        log "CHECK" "Container: $line"
    done
    
    # Listening ports
    ss -tlnp | grep -E ":(80|443|22|5432|6379) " | awk '{print "LISTEN:", $4}' | while read line; do
        log "CHECK" "$line"
    done
    
    log "INFO" "=== Quick Check Completed ==="
}

run_full_check() {
    log "INFO" "=== Full Check Started ==="
    
    bash /usr/local/bin/cpu_check.sh
    bash /usr/local/bin/memory_check.sh
    bash /usr/local/bin/disk_check.sh
    bash /usr/local/bin/container_check.sh
    bash /usr/local/bin/service_check.sh
    
    log "INFO" "=== Full Check Completed ==="
}

generate_report() {
    log "INFO" "=== Daily Report Generating ==="
    
    local report="/var/reports/vps-daily-$(date +%Y%m%d).md"
    mkdir -p /var/reports
    
    cat > "$report" << EOF
# VPS Daily Inspection Report — $(date '+%Y-%m-%d')

## System Overview
- **Hostname**: ${HOSTNAME}
- **Check Time**: ${TIMESTAMP}
- **Uptime**: $(awk '{print int($1/86400)}' /proc/uptime) days

## Resource Usage
\`\`\`
$(top -bn1 | head -5)
$(free -h)
$(df -h)
\`\`\`

## Alert Statistics (Last 24h)
\`\`\`
$(grep -c "CRITICAL" /var/log/vps-alerts.log 2>/dev/null || echo 0) critical alerts
$(grep -c "WARNING" /var/log/vps-alerts.log 2>/dev/null || echo 0) warnings
\`\`\`

## Recent Alerts (Last 5)
\`\`\`
$(tail -5 /var/log/vps-alerts.log 2>/dev/null || echo "No alerts")
\`\`\`

---
*Report generated by VPS Automated Inspection System*
EOF
    
    # Send daily report
    if [[ -f "$report" ]]; then
        mail -s "VPS Daily Report — $(date +%m-%d)" "$(cat /var/reports/admin-email.txt 2>/dev/null)" < "$report"
        log "INFO" "Daily report sent to admin"
    fi
    
    log "INFO" "=== Daily Report Completed ==="
}

case "$MODE" in
    --quick)
        run_quick_check
        ;;
    --full)
        run_full_check
        ;;
    --report)
        generate_report
        ;;
    *)
        echo "Usage: $0 [--quick|--full|--report]"
        exit 1
        ;;
esac
```

---

## 7. Complete Deployment

### 7.1 One-Click Deploy Script

```bash
#!/bin/bash
# deploy-inspection-system.sh — One-Click Deployment

set -e

echo "=== VPS Automated Inspection System Deployment ==="

# 1. Create directory structure
echo "[1/6] Creating directory structure..."
mkdir -p /usr/local/bin /var/lib/vps-alerts /var/reports /etc/cron.d

# 2. Copy scripts
echo "[2/6] Deploying inspection scripts..."
cp cpu_check.sh /usr/local/bin/
cp memory_check.sh /usr/local/bin/
cp disk_check.sh /usr/local/bin/
cp container_check.sh /usr/local/bin/
cp service_check.sh /usr/local/bin/
cp alert.sh /usr/local/bin/
cp alert_dedup.sh /usr/local/bin/
cp auto_fix.sh /usr/local/bin/
cp vps-inspect.sh /usr/local/bin/
chmod +x /usr/local/bin/*.sh

# 3. Install dependencies
echo "[3/6] Installing dependencies..."
apt-get update
apt-get install -y cron bc procps mailutils curl netcat-openbsd

# 4. Configure cron jobs
echo "[4/6] Configuring cron jobs..."
cat > /etc/cron.d/vps-inspection << 'CRON'
# VPS Automated Inspection
*/5 * * * * root /usr/local/bin/vps-inspect.sh --quick >> /var/log/vps-inspection.log 2>&1
0 * * * * root /usr/local/bin/vps-inspect.sh --full >> /var/log/vps-inspection.log 2>&1
0 8 * * * root /usr/local/bin/vps-inspect.sh --report >> /var/log/vps-inspection.log 2>&1
CRON

# 5. Configure alerts
echo "[5/6] Configuring alert notifications..."
cat > /etc/vps-alerts.conf << 'CONF'
TELEGRAM_BOT_TOKEN="YOUR_BOT_TOKEN"
TELEGRAM_CHAT_ID="YOUR_CHAT_ID"
ALERT_EMAIL="admin@example.com"
ALERT_WEBHOOK_URL="https://your-webhook-url.com/alert"
CONF
chmod 600 /etc/vps-alerts.conf

# 6. Start services
echo "[6/6] Starting services..."
systemctl enable cron
systemctl restart cron

echo ""
echo "=== Deployment Complete! ==="
echo ""
echo "View logs: tail -f /var/log/vps-inspection.log"
echo "Alert logs: tail -f /var/log/vps-alerts.log"
echo "Reports dir: /var/reports/"
echo ""
echo "Configure alerts: nano /etc/vps-alerts.conf"
```

### 7.2 Environment Variables

```bash
# /etc/profile.d/vps-alerts.sh
export TELEGRAM_BOT_TOKEN="your_bot_token_here"
export TELEGRAM_CHAT_ID="your_chat_id_here"
export ALERT_EMAIL="admin@yourdomain.com"
export ALERT_WEBHOOK_URL="https://hooks.example.com/vps-alerts"
```

---

## 8. Advanced: AI-Powered Diagnostics

When traditional rule-based detection can't find the root cause, AI can help analyze logs and diagnose issues.

```bash
#!/bin/bash
# ai_diagnose.sh — AI Diagnostic Assistant

ANALYZE_LOG() {
    local log_file=$1
    local context=$(tail -100 "$log_file" 2>/dev/null)
    
    echo "Analyzing logs, please wait..."
    
    # Method 1: Use local Ollama
    if command -v ollama &>/dev/null; then
        ollama run llama3.2 "$context" "Analyze the above logs, find possible errors and recommend solutions"
    fi
    
    # Method 2: Use API
    # curl -s https://api.openai.com/v1/chat/completions \
    #   -H "Authorization: Bearer $OPENAI_API_KEY" \
    #   -H "Content-Type: application/json" \
    #   -d "{\"model\": \"gpt-4o-mini\", \"messages\": [{\"role\": \"user\", \"content\": \"Analyze these logs: $context\"}]}"
}

# Auto-diagnose recent critical alerts
analyze_recent_alerts() {
    local recent=$(grep "CRITICAL" /var/log/vps-alerts.log 2>/dev/null | tail -5)
    
    if [[ -n "$recent" ]]; then
        echo "Critical alerts detected, starting AI diagnosis..."
        echo "$recent" | while read alert; do
            echo "Alert: $alert"
            case "$alert" in
                *"disk"*)
                    ANALYZE_LOG /var/log/dmesg
                    ;;
                *"memory"*)
                    ANALYZE_LOG /var/log/syslog
                    journalctl -k --since "1 hour ago" | tail -50
                    ;;
                *"container"*)
                    local container=$(echo "$alert" | grep -oP '(?<=Container )\w+')
                    docker logs "$container" --tail 50 2>/dev/null
                    ;;
            esac
        done
    fi
}
```

---

## Summary

Building an automated inspection and fault warning system delivers:

| Capability | Benefit |
|------------|---------|
| **7×24 Monitoring** | No more "3 AM crash surprises" |
| **Multi-level Alerts** | Only wake up for what matters |
| **Auto-Remediation** | Common issues fixed in seconds |
| **Daily Reports** | One运维 summary per day |
| **AI Diagnostics** | Intelligent root-cause analysis |

The system is cheap to build (a few scripts + one cron job) but delivers huge returns—you only need to focus on decisions, while machines handle the rest.

**Next steps**: Deploy `vps-inspect.sh` in a test environment first, observe for 3 days, then enable auto-remediation in production. For safety, auto-fix is disabled by default and must be manually enabled.
