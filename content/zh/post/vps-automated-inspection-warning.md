---
title: "VPS 自动化巡检与故障预警系统：让服务器自己会'看病'"
description: "构建 VPS 自动化巡检与故障预警系统，实现 7×24 小时健康监测、智能告警、自动修复与报告生成，彻底告别人工巡检时代"
date: 2026-08-25T08:00:00+08:00
lastmod: 2026-08-25T08:00:00+08:00
slug: "vps-automated-inspection-warning"
tags: ["VPS", "自动化巡检", "故障预警", "监控告警", "自动修复", "运维效率", "健康检查"]
categories: ["运维自动化"]
draft: false
image: /images/posts/vps-automated-inspection-warning/featured.png
aliases: [/zh/post/vps-automated-inspection-warning/]
---

## 引言

你有没有经历过这样的场景：凌晨三点手机狂响，服务器宕机了；或者放假期间网站突然打不开，客户已经在群里骂街了？

传统的 VPS 运维依赖人工巡检——定期检查 CPU、内存、磁盘、网络状态。但问题是：

- **人不是机器**，会漏看、会打盹、会休假
- **告警滞后**，等发现时问题已经恶化
- **根因难查**，故障现象和真实原因往往不一致

今天，我要教你搭建一套**自动化巡检与故障预警系统**，让它代替你 7×24 小时盯着服务器，提前发现问题、自动修复、生成报告——你只需要睡好觉。

---

## 一、系统架构设计

一个完整的自动化巡检系统由四个核心模块组成：

```
┌─────────────────────────────────────────────────────┐
│                   巡检调度层                          │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐            │
│  │ 定时触发器 │ │ 健康检查  │ │ 日志分析  │            │
│  │ (cron)   │ │ (check)  │ │ (analyze)│            │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘            │
└───────┼─────────────┼─────────────┼─────────────────┘
        │             │             │
   ┌────▼────┐   ┌────▼────┐   ┌────▼────┐
   │ 资源采集 │   │ 指标计算 │   │ 异常检测 │
   │ (collector)│ │ (metrics)│ │ (detect) │
   └────┬────┘   └────┬────┘   └────┬────┘
        │             │             │
┌───────▼─────────────▼─────────────▼─────────────────┐
│                   执行响应层                          │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐            │
│  │  告警通知 │ │ 自动修复  │ │ 报告生成  │            │
│  │ (alert)  │ │ (fix)    │ │ (report) │            │
│  └──────────┘ └──────────┘ └──────────┘            │
└─────────────────────────────────────────────────────┘
```

### 核心设计原则

1. **分层检测**：从基础设施层到应用层，逐层深入
2. **多级阈值**：警告 → 严重 → 紧急，不同级别不同处理
3. **自动修复**：常见故障自动处理，无需人工介入
4. **学习优化**：基于历史数据优化阈值和规则

---

## 二、基础设施层巡检

### 2.1 CPU 健康检查

CPU 是最核心的资源，过载会导致连锁反应。

```bash
#!/bin/bash
# cpu_check.sh — CPU 健康检查脚本

THRESHOLD_WARN=70
THRESHOLD_CRIT=90
THRESHOLD_LOAD=$(nproc)

# 获取 CPU 使用率
CPU_IDLE=$(top -bn1 | grep "Cpu(s)" | awk '{print $8}' | cut -d'%' -f1)
CPU_USAGE=$(printf "%.0f" "$(echo "100 - $CPU_IDLE" | bc -l)")

# 获取负载均值
LOAD_1MIN=$(cat /proc/loadavg | awk '{print $1}')

# 检查 CPU 使用率
if (( $(echo "$CPU_USAGE >= $THRESHOLD_CRIT" | bc -l) )); then
    echo "CRITICAL: CPU usage at ${CPU_USAGE}%"
    # 自动杀除异常进程
    top -bn1 | head -20 | grep -v "top" | tail -n +2 | sort -k9 -r | head -1 | awk '{print $1}' | xargs -I{} kill -9 {} 2>/dev/null
    alert "CRITICAL" "CPU overload: ${CPU_USAGE}%"
elif (( $(echo "$CPU_USAGE >= $THRESHOLD_WARN" | bc -l) )); then
    echo "WARNING: CPU usage at ${CPU_USAGE}%"
    alert "WARNING" "CPU usage elevated: ${CPU_USAGE}%"
else
    echo "OK: CPU usage at ${CPU_USAGE}%"
fi

# 检查负载均值
if (( $(echo "$LOAD_1MIN >= $THRESHOLD_LOAD" | bc -l) )); then
    echo "WARNING: System load ${LOAD_1MIN} exceeds CPU cores $(nproc)"
    alert "WARNING" "High system load: ${LOAD_1MIN}"
fi
```

### 2.2 内存与 Swap 检查

内存不足是 OOM Killer 的前兆，需要重点关注。

```bash
#!/bin/bash
# memory_check.sh — 内存健康检查脚本

THRESHOLD_MEM_WARN=80
THRESHOLD_MEM_CRIT=90
THRESHOLD_SWAP_WARN=70
THRESHOLD_SWAP_CRIT=90

# 获取内存信息
MEM_TOTAL=$(grep MemTotal /proc/meminfo | awk '{print $2}')
MEM_AVAILABLE=$(grep MemAvailable /proc/meminfo | awk '{print $2}')
MEM_USED=$((MEM_TOTAL - MEM_AVAILABLE))
MEM_USAGE=$(awk "BEGIN {printf \"%.0f\", ($MEM_USED / $MEM_TOTAL) * 100}")

# 获取 Swap 信息
SWAP_TOTAL=$(grep SwapTotal /proc/meminfo | awk '{print $2}')
SWAP_FREE=$(grep SwapFree /proc/meminfo | awk '{print $2}')
SWAP_USED=$((SWAP_TOTAL - SWAP_FREE))
SWAP_USAGE=0
[[ $SWAP_TOTAL -gt 0 ]] && SWAP_USAGE=$(awk "BEGIN {printf \"%.0f\", ($SWAP_USED / $SWAP_TOTAL) * 100}")

echo "Memory: ${MEM_USAGE}% used, Swap: ${SWAP_USAGE}% used"

if (( MEM_USAGE >= THRESHOLD_MEM_CRIT )); then
    echo "CRITICAL: Memory usage at ${MEM_USAGE}%"
    alert "CRITICAL" "Memory critical: ${MEM_USAGE}%"
    # 清理页面缓存
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

### 2.3 磁盘空间检查

磁盘满是最常见的"意外"，但完全可以预防。

```bash
#!/bin/bash
# disk_check.sh — 磁盘健康检查脚本

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

# 检查 inode 使用率
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

## 三、服务层巡检

### 3.1 Docker 容器健康检查

现代 VPS 上跑的大部分是容器，容器健康比主机健康更重要。

```bash
#!/bin/bash
# container_check.sh — Docker 容器健康检查

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
        # 尝试重启
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

# 检查所有关键容器
for container in nginx redis postgresql app-server worker; do
    check_container "$container"
done
```

### 3.2 关键服务可用性检查

```bash
#!/bin/bash
# service_check.sh — 服务可用性检查

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
    
    # 降级到 nc 检查
    if nc -z -w 3 localhost "$port" 2>/dev/null; then
        echo "OK: ${name} (port ${port}) port is open"
        return 0
    fi
    
    echo "CRITICAL: ${name} (port ${port}) is not responding"
    alert "CRITICAL" "Service down: ${name} on port ${port}"
    return 1
}

# 检查关键端口
check_service "Nginx" 80
check_service "SSH" 22
check_service "PostgreSQL" 5432
check_service "Redis" 6379
check_service "MySQL" 3306
check_service "Prometheus" 9090
check_service "Grafana" 3000
```

---

## 四、智能告警系统

### 4.1 多级告警策略

不是所有问题都需要凌晨叫醒你。分级告警让你只关注真正重要的事。

```bash
#!/bin/bash
# alert.sh — 多级告警通知脚本

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
        send_telegram      # Telegram 强提醒
        send_email         # 邮件存档
        send_webhook       # 企业 webhook
        ;;
    "WARNING")
        echo "[WARNING] ${ALERT_MESSAGE}" | tee -a /var/log/vps-alerts.log
        send_telegram      # Telegram 提醒
        send_webhook
        ;;
    "INFO")
        echo "[INFO] ${ALERT_MESSAGE}" >> /var/log/vps-alerts.log
        send_webhook       # 仅 webhook
        ;;
esac
```

### 4.2 告警去重与静默

避免告警风暴，同一问题只报一次。

```bash
#!/bin/bash
# alert_dedup.sh — 告警去重机制

ALERT_DIR="/var/lib/vps-alerts"
STALE_AFTER=300  # 5 分钟后允许重新告警

mkdir -p "$ALERT_DIR"

send_alert() {
    local key=$1
    local message=$2
    local now=$(date +%s)
    local alert_file="${ALERT_DIR}/${key}"
    
    # 检查是否已发送且未过期
    if [[ -f "$alert_file" ]]; then
        local last_sent=$(cat "$alert_file")
        local elapsed=$((now - last_sent))
        
        if (( elapsed < STALE_AFTER )); then
            echo "DEDUP: Alert '${key}' suppressed (last sent ${elapsed}s ago)"
            return
        fi
    fi
    
    # 发送告警
    echo "$message"
    echo "$now" > "$alert_file"
    
    # 清理过期文件
    find "$ALERT_DIR" -type f -mtime +1 -delete
}

# 使用示例
send_alert "disk_full" "Disk usage critical on /var"
send_alert "container_down" "nginx container is down"
```

---

## 五、自动修复能力

### 5.1 常见故障自动修复

```bash
#!/bin/bash
# auto_fix.sh — 自动修复脚本

fix_disk_space() {
    echo "[FIX] Cleaning disk space..."
    
    # 清理 apt 缓存
    apt-get clean 2>/dev/null
    
    # 清理旧日志
    find /var/log -name "*.log" -mtime +7 -exec truncate -s 0 {} \; 2>/dev/null
    find /var/log -name "*.gz" -mtime +30 -delete 2>/dev/null
    
    # 清理 journal 日志（保留 7 天）
    journalctl --vacuum-time=7d 2>/dev/null
    
    # 清理 Docker 未使用的资源
    docker system prune -f 2>/dev/null
    docker volume prune -f 2>/dev/null
    
    echo "[FIX] Disk cleanup completed"
}

fix_container_restart() {
    local container=$1
    echo "[FIX] Restarting container: ${container}"
    docker restart "$container" 2>/dev/null
    
    # 如果重启失败，尝试重建
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

# 主修复逻辑
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
        # 重启所有非健康容器
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

### 5.2 防误操作保护

自动修复有风险，需要安全阀。

```bash
#!/bin/bash
# safety_check.sh — 修复前安全检查

check_before_fix() {
    local fix_type=$1
    local action=$2
    
    # 检查修复时间窗口（禁止在维护窗口期修复）
    local hour=$(date +%H)
    if [[ "$fix_type" == "disk" ]] && (( hour >= 2 && hour <= 5 )); then
        echo "BLOCKED: Disk cleanup in maintenance window (02:00-05:00)"
        return 1
    fi
    
    # 检查系统负载
    local load=$(cat /proc/loadavg | awk '{print $1}')
    if (( $(echo "$load > 10" | bc -l) )); then
        echo "BLOCKED: System load too high (${load}), skipping fix"
        return 1
    fi
    
    # 检查是否需要人工确认
    if [[ "$action" == "destructive" ]]; then
        echo "REQUIRES_CONFIRMATION: Action is destructive, needs manual approval"
        return 1
    fi
    
    return 0
}

# 使用示例
check_before_fix "disk" "clean" && fix_disk_space
check_before_fix "container" "recreate" && fix_container_restart "myapp"
```

---

## 六、定时调度与报告生成

### 6.1 巡检调度配置

```bash
# /etc/cron.d/vps-inspection
# ┌───────────── 分钟 (0 - 59)
# │ ┌───────────── 小时 (0 - 23)
# │ │ ┌───────────── 日 (1 - 31)
# │ │ │ ┌───────────── 月 (1 - 12)
# │ │ │ │ ┌───────────── 星期 (0 - 6, 周日=0)
# │ │ │ │ │
# │ │ │ │ │
# │ │ │ │ │
*/5 * * * * root /usr/local/bin/vps-inspect.sh --quick >> /var/log/vps-inspection.log 2>&1
0 * * * * root /usr/local/bin/vps-inspect.sh --full >> /var/log/vps-inspection.log 2>&1
0 6 * * * root /usr/local/bin/vps-inspect.sh --report >> /var/log/vps-inspection.log 2>&1
```

### 6.2 完整巡检脚本

```bash
#!/bin/bash
# vps-inspect.sh — 完整巡检入口脚本

MODE="${1:---quick}"
HOSTNAME=$(hostname)
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
LOG_FILE="/var/log/vps-inspection.log"

log() {
    echo "[$TIMESTAMP] [$1] $2" | tee -a "$LOG_FILE"
}

run_quick_check() {
    log "INFO" "=== Quick Check Started ==="
    
    # CPU & 内存
    CPU=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | cut -d'%' -f1)
    MEM=$(free | awk '/^Mem:/ {printf "%.0f", $3/$2 * 100}')
    DISK=$(df -h / | awk 'NR==2 {print $5}' | tr -d '%')
    
    log "CHECK" "CPU: ${CPU}% | MEM: ${MEM}% | DISK: ${DISK}%"
    
    # 关键进程
    docker ps --format "table {{.Names}}\t{{.Status}}" | while read line; do
        log "CHECK" "Container: $line"
    done
    
    # 端口监听
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
# VPS 每日巡检报告 — $(date '+%Y-%m-%d')

## 系统概况
- **主机名**: ${HOSTNAME}
- **检查时间**: ${TIMESTAMP}
- **运行天数**: $(awk '{print int($1/86400)}' /proc/uptime) 天

## 资源使用
\`\`\`
$(top -bn1 | head -5)
$(free -h)
$(df -h)
\`\`\`

## 告警统计 (过去 24 小时)
\`\`\`
$(grep -c "CRITICAL" /var/log/vps-alerts.log 2>/dev/null || echo 0) 个严重告警
$(grep -c "WARNING" /var/log/vps-alerts.log 2>/dev/null || echo 0) 个警告
\`\`\`

## 近 5 条告警记录
\`\`\`
$(tail -5 /var/log/vps-alerts.log 2>/dev/null || echo "暂无告警")
\`\`\`

---
*本报告由 VPS 自动化巡检系统自动生成*
EOF
    
    # 发送日报
    if [[ -f "$report" ]]; then
        mail -s "VPS 每日巡检报告 — $(date +%m-%d)" "$(cat /var/reports/admin-email.txt 2>/dev/null)" < "$report"
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

## 七、完整部署方案

### 7.1 一键部署脚本

```bash
#!/bin/bash
# deploy-inspection-system.sh — 一键部署巡检系统

set -e

echo "=== VPS 自动化巡检系统部署 ==="

# 1. 创建目录结构
echo "[1/6] 创建目录结构..."
mkdir -p /usr/local/bin /var/lib/vps-alerts /var/reports /etc/cron.d

# 2. 复制脚本
echo "[2/6] 部署巡检脚本..."
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

# 3. 安装依赖
echo "[3/6] 安装依赖..."
apt-get update
apt-get install -y cron bc procps mailutils curl netcat-openbsd

# 4. 配置定时任务
echo "[4/6] 配置定时任务..."
cat > /etc/cron.d/vps-inspection << 'CRON'
# VPS 自动化巡检 — 每 5 分钟快速检查
*/5 * * * * root /usr/local/bin/vps-inspect.sh --quick >> /var/log/vps-inspection.log 2>&1
# 每小时完整检查
0 * * * * root /usr/local/bin/vps-inspect.sh --full >> /var/log/vps-inspection.log 2>&1
# 每天早上 8 点生成日报
0 8 * * * root /usr/local/bin/vps-inspect.sh --report >> /var/log/vps-inspection.log 2>&1
CRON

# 5. 配置告警
echo "[5/6] 配置告警通知..."
cat > /etc/vps-alerts.conf << 'CONF'
TELEGRAM_BOT_TOKEN="YOUR_BOT_TOKEN"
TELEGRAM_CHAT_ID="YOUR_CHAT_ID"
ALERT_EMAIL="admin@example.com"
ALERT_WEBHOOK_URL="https://your-webhook-url.com/alert"
CONF
chmod 600 /etc/vps-alerts.conf

# 6. 启动服务
echo "[6/6] 启动服务..."
systemctl enable cron
systemctl restart cron

echo ""
echo "=== 部署完成！ ==="
echo ""
echo "查看日志: tail -f /var/log/vps-inspection.log"
echo "告警日志: tail -f /var/log/vps-alerts.log"
echo "日报目录: /var/reports/"
echo ""
echo "配置告警: nano /etc/vps-alerts.conf"
```

### 7.2 环境变量配置

```bash
# /etc/profile.d/vps-alerts.sh
export TELEGRAM_BOT_TOKEN="your_bot_token_here"
export TELEGRAM_CHAT_ID="your_chat_id_here"
export ALERT_EMAIL="admin@yourdomain.com"
export ALERT_WEBHOOK_URL="https://hooks.example.com/vps-alerts"
```

---

## 八、进阶：接入 AI 智能诊断

当传统规则检测无法定位问题时，AI 可以帮你分析日志、定位根因。

```bash
#!/bin/bash
# ai_diagnose.sh — AI 智能诊断辅助

ANALYZE_LOG() {
    local log_file=$1
    local context=$(tail -100 "$log_file" 2>/dev/null)
    
    # 调用本地 AI 模型分析
    echo "正在分析日志，请稍候..."
    
    # 方式 1: 使用本地 Ollama
    if command -v ollama &>/dev/null; then
        ollama run llama3.2 "$context" "请分析以上日志，找出可能的错误和推荐解决方案"
    fi
    
    # 方式 2: 使用 API
    # curl -s https://api.openai.com/v1/chat/completions \
    #   -H "Authorization: Bearer $OPENAI_API_KEY" \
    #   -H "Content-Type: application/json" \
    #   -d "{\"model\": \"gpt-4o-mini\", \"messages\": [{\"role\": \"user\", \"content\": \"Analyze these logs: $context\"}]}"
}

# 自动诊断最近的关键告警
analyze_recent_alerts() {
    local recent=$(grep "CRITICAL" /var/log/vps-alerts.log 2>/dev/null | tail -5)
    
    if [[ -n "$recent" ]]; then
        echo "检测到关键告警，启动 AI 诊断..."
        echo "$recent" | while read alert; do
            echo "告警: $alert"
            # 根据告警类型分析对应日志
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

## 总结

搭建自动化巡检与故障预警系统，核心价值在于：

| 能力 | 效果 |
|------|------|
| **7×24 小时监控** | 不再有"凌晨宕机"的意外 |
| **多级告警** | 只被打扰真正重要的事 |
| **自动修复** | 常见故障秒级恢复 |
| **日报生成** | 每天一份运维摘要 |
| **AI 诊断** | 复杂问题智能分析 |

这套系统搭建成本低（一个脚本 + 一个 cron），但回报巨大——你只需要关注真正需要决策的问题，其余交给机器。

**下一步行动**：先在测试环境部署 `vps-inspect.sh`，观察 3 天确认无误后，再在生产环境启用自动修复功能。安全起见，自动修复默认关闭，需要手动开启。
