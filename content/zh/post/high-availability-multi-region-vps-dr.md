---
title: "构建高可用多区域 VPS 灾备架构：从零到生产级容灾方案"
description: "手把手教你用多区域 VPS + DNS 故障转移 + 自动同步构建生产级高可用架构，实现单点故障自动恢复，RTO < 5 分钟，RPO ≈ 0"
date: 2026-06-26T10:00:00+08:00
lastmod: 2026-06-26T10:00:00+08:00
slug: "high-availability-multi-region-vps-dr"
tags: ["高可用", "灾备", "多区域", "DNS故障转移", "VPS架构", "自动化运维", "Cloudflare", "rsync"]
categories: ["架构设计"]
draft: false
image: /images/posts/high-availability-multi-region-vps-dr/featured.png
aliases: [/zh/post/high-availability-multi-region-vps-dr/]
---

## 为什么你需要多区域灾备？

大多数 VPS 用户只使用一台服务器——这是典型的**单点故障（Single Point of Failure）**架构。一旦这台机器出现问题，你的网站、API 服务、数据库全部不可用。

常见故障场景：

| 故障类型 | 发生频率 | 影响范围 |
|---------|---------|---------|
| VPS 供应商数据中心宕机 | 低（~1%/年） | 全部服务中断 |
| DDoS 攻击导致 IP 被封 | 中（~10%/季） | 全部服务中断 |
| 人为误操作删除数据 | 高（~50%/月） | 数据丢失 |
| 硬件老化导致性能下降 | 中 | 响应变慢、超时 |
| 安全漏洞被利用 | 中 | 数据泄露、服务被控 |

**核心思路**：将服务部署在两个或以上不同地域的 VPS 上，配合自动故障转移，实现：

- **RTO（恢复时间目标）< 5 分钟**：故障自动切换，用户几乎无感知
- **RPO（恢复点目标）≈ 0**：数据实时同步，零丢失
- **成本可控**：两台入门级 VPS 总费用通常不超过 $20/月

---

## 架构总览

```
                    ┌─────────────────┐
                    │   Cloudflare    │
                    │   DNS / Anycast │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
              ┌────┤  Failover Rule  ├──┐
              │    └────────┬────────┘   │
              │             │            │
     ┌────────▼───┐   ┌────▼────────┐
     │  Primary   │   │   Secondary  │
     │  Region A  │   │  Region B    │
     │  (Active)  │   │  (Standby)   │
     │            │   │             │
     │  Web + DB  │◄─►│  Warm Standby│
     │  App Server│   │  Sync Mirror │
     └────────────┘   └─────────────┘
```

**关键组件**：

1. **Cloudflare DNS** — 提供全球 Anycast DNS 和快速故障转移
2. **Primary VPS** — 主服务器，处理全部流量
3. **Secondary VPS** — 备用服务器，保持热备状态
4. **数据同步层** — rsync + MySQL/MariaDB 主从复制
5. **健康检查层** — Uptime Kuma 或自定义脚本
6. **自动故障转移** — Cloudflare Workers + DNS API

---

## 第一步：准备两台不同区域的 VPS

### 推荐方案

| 角色 | 推荐区域 | 最低配置 | 月费用参考 |
|------|---------|---------|-----------|
| Primary | 新加坡（亚太） | 2C4G | $6-10 |
| Secondary | 法兰克福（欧洲） | 2C4G | €5-8 |

**选择原则**：

- 两个区域之间网络延迟 < 150ms（保证同步效率）
- 使用**不同供应商**（如 DigitalOcean + Hetzner），避免同一厂商全局故障
- 两个区域属于不同的法律管辖区

### 初始化两台服务器

```bash
# === 两台 VPS 都需要执行 ===

# 1. 更新系统
apt update && apt upgrade -y

# 2. 安装基础工具
apt install -y curl wget git htop tmux unzip

# 3. 配置防火墙（仅开放必要端口）
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 3306/tcp   # 仅允许 Primary 的 IP
ufw enable

# 4. 创建非 root 用户
adduser deploy
usermod -aG sudo deploy
echo 'deploy ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers

# 5. 配置 SSH 密钥登录，禁用密码登录
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519 -N ""
ssh-copy-id deploy@<secondary-ip>
echo "PermitRootLogin no" >> /etc/ssh/sshd_config
echo "PasswordAuthentication no" >> /etc/ssh/sshd_config
systemctl restart sshd
```

---

## 第二步：搭建主从数据库同步

使用 MariaDB 主从复制实现**近实时数据同步**。

### Primary 服务器配置

```bash
# 安装 MariaDB
apt install -y mariadb-server mariadb-client

# 编辑配置文件
cat > /etc/mysql/mariadb.conf.d/99-replication.cnf << 'EOF'
[mysqld]
server-id = 1
log-bin = mariadb-bin
binlog-format = ROW
binlog-do-db = myapp
bind-address = 0.0.0.0
EOF

# 重启 MariaDB
systemctl restart mariadb

# 创建复制用户
mysql -u root << 'EOSQL'
CREATE USER 'repl_user'@'%' IDENTIFIED BY 'R3pl!c@Str0ng';
GRANT REPLICATION SLAVE ON *.* TO 'repl_user'@'%';
FLUSH PRIVILEGES;

-- 创建示例应用数据库
CREATE DATABASE IF NOT EXISTS myapp CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'myapp_user'@'%' IDENTIFIED BY 'My@ppStr0ng!';
GRANT ALL PRIVILEGES ON myapp.* TO 'myapp_user'@'%';
FLUSH PRIVILEGES;
EOSQL
```

### Secondary 服务器配置

```bash
# 安装 MariaDB
apt install -y mariadb-server mariadb-client

# 编辑配置文件
cat > /etc/mysql/mariadb.conf.d/99-replication.cnf << 'EOF'
[mysqld]
server-id = 2
relay-log = relay-bin
bind-address = 0.0.0.0
EOF

# 重启 MariaDB
systemctl restart mariadb

# 配置主从关系
mysql -u root << EOSQL
STOP SLAVE;
CHANGE MASTER TO
  MASTER_HOST = '<primary-ip>',
  MASTER_USER = 'repl_user',
  MASTER_PASSWORD = 'R3pl!c@Str0ng',
  MASTER_PORT = 3306,
  MASTER_LOG_FILE = '',
  MASTER_LOG_POS = 0,
  MASTER_CONNECT_RETRY = 10;
START SLAVE;

-- 检查复制状态
SHOW SLAVE STATUS\G
EOSQL
```

**确认复制正常**的输出关键字：

```
Slave_IO_Running: Yes
Slave_SQL_Running: Yes
Seconds_Behind_Master: 0
```

---

## 第三步：配置双向 rsync 文件同步

Web 文件需要同步到 Secondary，但 Secondary 不能反向覆盖 Primary（避免循环）。

### Primary → Secondary 单向同步（推荐方案）

```bash
# === 在 Primary 服务器上 ===

# 创建同步脚本 /opt/scripts/rsync-sync.sh
cat > /opt/scripts/rsync-sync.sh << 'EOF'
#!/bin/bash
# Rsync files from Primary to Secondary
SECONDARY_IP="<secondary-ip>"
SYNC_USER="deploy"
SYNC_DIRS="/var/www /etc/nginx /etc/letsencrypt"
LOG_FILE="/var/log/rsync-sync.log"

for dir in $SYNC_DIRS; do
    rsync -avz --delete \
        -e "ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10" \
        "$dir/" "${SYNC_USER}@${SECONDARY_IP}:${dir}/" 2>&1 | \
        tee -a "$LOG_FILE"
done

# Sync crontab
crontab -u deploy -l | ssh "${SYNC_USER}@${SECONDARY_IP}" "crontab -u deploy -"
EOF

chmod +x /opt/scripts/rsync-sync.sh

# 测试同步
/opt/scripts/rsync-sync.sh
```

### 定时同步

```bash
# Primary 上设置每 5 分钟同步一次
(crontab -l 2>/dev/null; echo "*/5 * * * * /opt/scripts/rsync-sync.sh") | crontab -
```

---

## 第四步：Secondary 服务器热备配置

Secondary 服务器需要保持服务可用，以便故障切换时能立即接管。

```bash
# === 在 Secondary 服务器上 ===

# 1. 从 Primary 拉取初始文件
rsync -avz -e "ssh -o StrictHostKeyChecking=no" \
    deploy@<primary-ip>:/var/www/ /var/www/
rsync -avz -e "ssh -o StrictHostKeyChecking=no" \
    deploy@<primary-ip>:/etc/nginx/ /etc/nginx/

# 2. 配置 Nginx 监听所有接口
cat > /etc/nginx/sites-available/default << 'EOF'
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    
    root /var/www/html;
    index index.html;
    
    server_name _;
    
    location / {
        try_files $uri $uri/ =404;
    }
}
EOF

# 3. 配置 MariaDB 从库可读（用于故障切换后直接提供服务）
cat > /etc/mysql/mariadb.conf.d/99-read-only.cnf << 'EOF'
[mysqld]
read-only = 1
super-read-only = 1
EOF

# 4. 安装 Uptime Kuma 用于健康监控
docker run -d --restart=unless-stopped \
    -v uptime-kuma:/app/data \
    -p 3001:3001 \
    louislam/uptime-kuma:1
```

---

## 第五步：DNS 故障转移配置

### 方案 A：Cloudflare DNS 手动切换（简单可靠）

```bash
# === 在 Primary 服务器上安装 Cloudflare CLI ===
curl -s https://api.cloudflare.com/client/v4/scripts/ | sh
# 或者使用 cloudflared CLI
apt install -y cloudflared

# 获取 API Token（在 Cloudflare Dashboard → My Profile → API Tokens）
export CF_API_TOKEN="your_cloudflare_api_token"
export CF_ACCOUNT_ID="your_account_id"
export CF_ZONE_ID="your_zone_id"

# 创建故障转移脚本 /opt/scripts/failover-dns.sh
cat > /opt/scripts/failover-dns.sh << 'SCRIPT'
#!/bin/bash
set -euo pipefail

ZONE_ID="$CF_ZONE_ID"
RECORD_ID=""
PRIMARY_IP="<primary-ip>"
SECONDARY_IP="<secondary-ip>"
DOMAIN="example.com"

# 查找现有 DNS 记录
RECORD_ID=$(curl -s -X GET "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/dns_records?type=A&name=$DOMAIN" \
    -H "Authorization: Bearer $CF_API_TOKEN" \
    -H "Content-Type: application/json" | jq -r '.result[0].id')

# 切换到备用 IP
curl -s -X PUT "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/dns_records/$RECORD_ID" \
    -H "Authorization: Bearer $CF_API_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"type\":\"A\",\"name\":\"$DOMAIN\",\"content\":\"$SECONDARY_IP\",\"ttl\":1,\"proxied\":true}"

echo "DNS switched to secondary: $SECONDARY_IP"
SCRIPT

chmod +x /opt/scripts/failover-dns.sh
```

### 方案 B：Cloudflare Worker 自动故障转移（高级方案）

```javascript
// === Cloudflare Worker: auto-failover.js ===
export default {
  async fetch(request) {
    const url = new URL(request.url);
    const primaryIP = '<primary-ip>';
    const secondaryIP = '<secondary-ip>';
    
    // 尝试连接 Primary
    const healthCheck = await fetch(`http://${primaryIP}/health`, {
      method: 'GET',
      timeout: 5000,
    });
    
    if (healthCheck.ok) {
      // Primary 正常，直接代理
      return fetch(request);
    }
    
    // Primary 不可用，切换到 Secondary
    console.warn(`Primary unhealthy, failover to ${secondaryIP}`);
    
    // 更新 DNS（可选，降低 TTL 更快生效）
    await updateDNSRecord(secondaryIP);
    
    // 代理请求到 Secondary
    const modifiedRequest = new Request(
      request.url.toString().replace(primaryIP, secondaryIP),
      request
    );
    
    return fetch(modifiedRequest);
  },
};

async function updateDNSRecord(ip) {
  // 调用 Cloudflare API 更新 A 记录
  const resp = await fetch('https://api.cloudflare.com/client/v4/zones/YOUR_ZONE/dns_records', {
    method: 'PUT',
    headers: {
      'Authorization': 'Bearer YOUR_CF_TOKEN',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      type: 'A',
      name: 'example.com',
      content: ip,
      ttl: 60,
      proxied: true,
    }),
  });
  return resp.json();
}
```

---

## 第六步：自动化健康检查与告警

### 使用 Uptime Kuma 监控

```yaml
# docker-compose.yml for Uptime Kuma (Primary)
version: '3.8'
services:
  uptime-kuma:
    image: louislam/uptime-kuma:1
    container_name: uptime-kuma
    restart: unless-stopped
    ports:
      - "3001:3001"
    volumes:
      - uptime-kuma-data:/app/data

volumes:
  uptime-kuma-data:
```

**添加监控项**：

1. **Primary HTTP** — `http://primary-ip/health`（每 30 秒）
2. **Secondary HTTP** — `http://secondary-ip/health`（每 30 秒）
3. **MariaDB Replication** — 通过 MySQL 插件监控 `Slave_IO_Running`
4. **Cloudflare DNS** — Ping 监控域名解析 IP
5. **磁盘空间** — 自定义脚本检查 `/` 分区使用率

### 自定义健康检查脚本

```bash
# /opt/scripts/health-check.sh
#!/bin/bash
set -euo pipefail

PRIMARY_IP="<primary-ip>"
SECONDARY_IP="<secondary-ip>"
WEBHOOK_URL="https://your-webhook-url/slack-alerts"

check_http() {
    local ip=$1
    local code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 "http://${ip}/health" 2>/dev/null || echo "000")
    echo "$code"
}

check_mysql_replication() {
    local status=$(mysql -u root -e "SHOW SLAVE STATUS\G" 2>/dev/null | grep -E "Slave_(IO|SQL)_Running" | tr '\n' ',')
    echo "$status"
}

# 检查自身健康
SELF_HTTP=$(check_http "$(hostname -i)")
if [[ "$SELF_HTTP" != "200" ]]; then
    echo "ALERT: Self HTTP check failed: $SELF_HTTP"
    curl -s -X POST "$WEBHOOK_URL" \
        -H "Content-Type: application/json" \
        -d "{\"text\":\"🚨 Primary VPS HTTP check failed: $SELF_HTTP\"}" > /dev/null 2>&1
    
    # 触发故障转移
    /opt/scripts/failover-dns.sh
    exit 1
fi

# 检查 Secondary 是否可达
SECONDARY_HTTP=$(check_http "$SECONDARY_IP")
if [[ "$SECONDARY_HTTP" != "200" ]]; then
    echo "WARNING: Secondary unreachable: $SECONDARY_HTTP"
    curl -s -X POST "$WEBHOOK_URL" \
        -H "Content-Type: application/json" \
        -d "{\"text\":\"⚠️ Secondary VPS unreachable\"}" > /dev/null 2>&1
fi

# 检查数据库复制状态
REPL_STATUS=$(check_mysql_replication)
if [[ "$REPL_STATUS" != *"Yes,Yes"* ]]; then
    echo "ALERT: MySQL replication broken: $REPL_STATUS"
    mysql -u root -e "STOP SLAVE; START SLAVE;" 2>/dev/null
    curl -s -X POST "$WEBHOOK_URL" \
        -H "Content-Type: application/json" \
        -d "{\"text\":\"🔴 MySQL replication broken on $(hostname)\"}" > /dev/null 2>&1
fi

echo "All checks passed on $(hostname)"
```

```bash
# 每 60 秒执行一次
(crontab -l 2>/dev/null; echo "* * * * * /opt/scripts/health-check.sh >> /var/log/health-check.log 2>&1") | crontab -
```

---

## 第七步：数据备份策略

### 三级备份方案

```
Level 1: 实时同步（主从复制 + rsync）→ RPO ≈ 0
Level 2: 每小时快照（VPS 供应商快照）→ RPO = 1h
Level 3: 每日异地备份（S3 / Backblaze B2）→ RPO = 24h
```

```bash
# === 每日备份脚本 ===
cat > /opt/scripts/daily-backup.sh << 'EOF'
#!/bin/bash
set -euo pipefail

BACKUP_DIR="/opt/backups"
DATE=$(date +%Y%m%d_%H%M%S)
MYSQL_USER="myapp_user"
MYSQL_PASS="My@ppStr0ng!"
MYSQL_DB="myapp"

# 1. 数据库备份
mkdir -p "$BACKUP_DIR/mysql"
mysqldump -u "$MYSQL_USER" -p"$MYSQL_PASS" \
    --single-transaction --routines --triggers \
    "$MYSQL_DB" > "$BACKUP_DIR/mysql/${DATE}_${MYSQL_DB}.sql"

# 2. 压缩
gzip "$BACKUP_DIR/mysql/${DATE}_${MYSQL_DB}.sql"

# 3. 上传到 S3 兼容存储（Backblaze B2 / AWS S3）
export B2_ACCOUNT_ID="your_b2_account_id"
export B2_APPLICATION_KEY="your_b2_application_key"
b2 upload-file --json myapp-backups "$BACKUP_DIR/mysql/${DATE}_${MYSQL_DB}.sql.gz" "backups/${DATE}_${MYSQL_DB}.sql.gz"

# 4. 清理 30 天前的备份
find "$BACKUP_DIR" -name "*.gz" -mtime +30 -delete

echo "Backup completed: $DATE"
EOF

chmod +x /opt/scripts/daily-backup.sh

# 每天凌晨 2 点执行
echo "0 2 * * * /opt/scripts/daily-backup.sh" | crontab -
```

---

## 故障切换演练

**定期演练是灾备架构的核心**。建议每月执行一次完整切换测试：

```bash
# 模拟故障切换流程
cat > /opt/scripts/dr-drill.sh << 'EOF'
#!/bin/bash
set -euo pipefail

echo "=== DR Drill Starting at $(date) ==="

# Step 1: 记录当前状态
echo "[1/5] Recording current state..."
PRIMARY_IP="<primary-ip>"
SECONDARY_IP="<secondary-ip>"
CURRENT_IP=$(dig +short example.com | head -1)
echo "Current active IP: $CURRENT_IP"

# Step 2: 暂停 Primary 服务
echo "[2/5] Simulating Primary failure..."
systemctl stop nginx
echo "Primary Nginx stopped"

# Step 3: 等待 DNS 切换（或手动触发）
echo "[3/5] Waiting for DNS failover..."
sleep 10
# 或使用自动脚本: /opt/scripts/failover-dns.sh

# Step 4: 验证 Secondary 接管
echo "[4/5] Verifying Secondary takeover..."
NEW_IP=$(dig +short example.com | head -1)
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://$NEW_IP/")
echo "New active IP: $NEW_IP"
echo "Response code: $HTTP_CODE"

if [[ "$HTTP_CODE" == "200" ]]; then
    echo "✅ Failover successful!"
else
    echo "❌ Failover failed! HTTP code: $HTTP_CODE"
fi

# Step 5: 恢复 Primary
echo "[5/5] Restoring Primary..."
systemctl start nginx
echo "Primary Nginx restarted"

echo "=== DR Drill Completed at $(date) ==="
EOF

chmod +x /opt/scripts/dr-drill.sh
```

---

## 成本估算

| 项目 | 费用 |
|------|------|
| Primary VPS (2C4G, 新加坡) | ~$6-10/月 |
| Secondary VPS (2C4G, 法兰克福) | ~€5-8/月 |
| Cloudflare Pro (可选, 高级 Workers) | $5/月 |
| Backblaze B2 存储 (100GB) | ~$0.60/月 |
| **总计** | **~$17-24/月** |

对比：单台高性能 VPS ($20-40/月) + 每次故障停机损失 (未知，可能数千美元)。

---

## 总结

| 组件 | 选型 | 作用 |
|------|------|------|
| DNS 故障转移 | Cloudflare DNS API | 快速切换流量 |
| 数据库同步 | MariaDB 主从复制 | 近实时数据同步 |
| 文件同步 | rsync (cron) | 静态文件同步 |
| 健康检查 | Uptime Kuma + 自定义脚本 | 自动检测故障 |
| 告警通知 | Slack/Discord Webhook | 即时通知 |
| 数据备份 | mysqldump + B2/S3 | 长期备份 |

这套架构可以在 **$20/月** 的成本下，为你的业务提供**企业级高可用性**。关键不在于技术有多复杂，而在于**定期演练**和**持续监控**。

> 💡 **下一步**：根据你的业务规模，可以考虑扩展到三区域部署、引入负载均衡器、或使用 Terraform 实现基础设施即代码（IaC）。
