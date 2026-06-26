---
title: "Building a High-Availability Multi-Region VPS Disaster Recovery Architecture: From Zero to Production-Grade"
description: "Step-by-step guide to building a production-grade HA architecture with multi-region VPS + DNS failover + automatic sync — achieve automatic recovery from single-point failures with RTO < 5 min, RPO ≈ 0"
date: 2026-06-26T10:00:00+08:00
lastmod: 2026-06-26T10:00:00+08:00
slug: "high-availability-multi-region-vps-dr"
tags: ["High Availability", "Disaster Recovery", "Multi-Region", "DNS Failover", "VPS Architecture", "Automation", "Cloudflare", "rsync"]
categories: ["Architecture Design"]
draft: false
image: /images/posts/high-availability-multi-region-vps-dr/featured.png
aliases: [/en/post/high-availability-multi-region-vps-dr/]
---

## Why Do You Need Multi-Region Disaster Recovery?

Most VPS users operate with a single server — this is a classic **Single Point of Failure (SPOF)** architecture. When that machine goes down, your website, API services, and databases all become unavailable.

Common failure scenarios:

| Failure Type | Frequency | Impact |
|-------------|-----------|--------|
| VPS provider datacenter outage | Low (~1%/yr) | Complete service interruption |
| DDoS attack causing IP ban | Medium (~10%/quarter) | Complete service interruption |
| Human error deleting data | High (~50%/month) | Data loss |
| Hardware degradation | Medium | Slow responses, timeouts |
| Security vulnerability exploited | Medium | Data breach, compromised services |

**Core idea**: Deploy services across two or more geographically distributed VPS instances, combined with automated failover, to achieve:

- **RTO (Recovery Time Objective) < 5 minutes**: Automatic failover on failure, nearly imperceptible to users
- **RPO (Recovery Point Objective) ≈ 0**: Real-time data sync, zero data loss
- **Cost-effective**: Two entry-level VPS instances typically cost under $20/month total

---

## Architecture Overview

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

**Key components**:

1. **Cloudflare DNS** — Global Anycast DNS with fast failover
2. **Primary VPS** — Main server handling all traffic
3. **Secondary VPS** — Backup server kept in warm standby
4. **Data sync layer** — rsync + MySQL/MariaDB master-slave replication
5. **Health check layer** — Uptime Kuma or custom scripts
6. **Automated failover** — Cloudflare Workers + DNS API

---

## Step 1: Prepare Two VPS Instances in Different Regions

### Recommended Setup

| Role | Recommended Region | Minimum Config | Monthly Cost |
|------|-------------------|----------------|--------------|
| Primary | Singapore (APAC) | 2C4G | $6-10 |
| Secondary | Frankfurt (EU) | 2C4G | €5-8 |

**Selection principles**:

- Network latency between regions < 150ms (ensures sync efficiency)
- Use **different providers** (e.g., DigitalOcean + Hetzner) to avoid single-provider global outages
- Regions should be in different legal jurisdictions

### Initial Server Setup

```bash
# === Run on BOTH VPS instances ===

# 1. Update the system
apt update && apt upgrade -y

# 2. Install base tools
apt install -y curl wget git htop tmux unzip

# 3. Configure firewall (only essential ports)
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 3306/tcp   # Only allow Primary's IP
ufw enable

# 4. Create non-root user
adduser deploy
usermod -aG sudo deploy
echo 'deploy ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers

# 5. Configure SSH key login, disable password authentication
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519 -N ""
ssh-copy-id deploy@<secondary-ip>
echo "PermitRootLogin no" >> /etc/ssh/sshd_config
echo "PasswordAuthentication no" >> /etc/ssh/sshd_config
systemctl restart sshd
```

---

## Step 2: Set Up Master-Slave Database Replication

Use MariaDB master-slave replication for **near-real-time data sync**.

### Primary Server Configuration

```bash
# Install MariaDB
apt install -y mariadb-server mariadb-client

# Edit configuration
cat > /etc/mysql/mariadb.conf.d/99-replication.cnf << 'EOF'
[mysqld]
server-id = 1
log-bin = mariadb-bin
binlog-format = ROW
binlog-do-db = myapp
bind-address = 0.0.0.0
EOF

# Restart MariaDB
systemctl restart mariadb

# Create replication user
mysql -u root << 'EOSQL'
CREATE USER 'repl_user'@'%' IDENTIFIED BY 'R3pl!c@Str0ng';
GRANT REPLICATION SLAVE ON *.* TO 'repl_user'@'%';
FLUSH PRIVILEGES;

-- Create sample application database
CREATE DATABASE IF NOT EXISTS myapp CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'myapp_user'@'%' IDENTIFIED BY 'My@ppStr0ng!';
GRANT ALL PRIVILEGES ON myapp.* TO 'myapp_user'@'%';
FLUSH PRIVILEGES;
EOSQL
```

### Secondary Server Configuration

```bash
# Install MariaDB
apt install -y mariadb-server mariadb-client

# Edit configuration
cat > /etc/mysql/mariadb.conf.d/99-replication.cnf << 'EOF'
[mysqld]
server-id = 2
relay-log = relay-bin
bind-address = 0.0.0.0
EOF

# Restart MariaDB
systemctl restart mariadb

# Configure master-slave relationship
mysql -u root << EOSQL
STOP SLAVE;
CHANGE MASTER TO
  MASTER_HOST = '<primary-ip>',
  MASTER_USER = 'repl_user',
  MASTER_PASSWORD='***',
  MASTER_PORT = 3306,
  MASTER_LOG_FILE = '',
  MASTER_LOG_POS = 0,
  MASTER_CONNECT_RETRY = 10;
START SLAVE;

-- Check replication status
SHOW SLAVE STATUS\G
EOSQL
```

**Expected output confirming replication is healthy**:

```
Slave_IO_Running: Yes
Slave_SQL_Running: Yes
Seconds_Behind_Master: 0
```

---

## Step 3: Configure One-Way rsync File Sync

Web files need to sync to Secondary, but Secondary must not sync back to Primary (to avoid loops).

### Primary → Secondary One-Way Sync (Recommended)

```bash
# === On the Primary server ===

# Create sync script at /opt/scripts/rsync-sync.sh
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

# Sync crontabs
crontab -u deploy -l | ssh "${SYNC_USER}@${SECONDARY_IP}" "crontab -u deploy -"
EOF

chmod +x /opt/scripts/rsync-sync.sh

# Test the sync
/opt/scripts/rsync-sync.sh
```

### Scheduled Sync

```bash
# On Primary, set up 5-minute interval sync
(crontab -l 2>/dev/null; echo "*/5 * * * * /opt/scripts/rsync-sync.sh") | crontab -
```

---

## Step 4: Configure Secondary as Warm Standby

The Secondary server must keep services running so it can immediately take over on failover.

```bash
# === On the Secondary server ===

# 1. Pull initial files from Primary
rsync -avz -e "ssh -o StrictHostKeyChecking=no" \
    deploy@<primary-ip>:/var/www/ /var/www/
rsync -avz -e "ssh -o StrictHostKeyChecking=no" \
    deploy@<primary-ip>:/etc/nginx/ /etc/nginx/

# 2. Configure Nginx to listen on all interfaces
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

# 3. Configure MariaDB slave as read-only (for direct service after failover)
cat > /etc/mysql/mariadb.conf.d/99-read-only.cnf << 'EOF'
[mysqld]
read-only = 1
super-read-only = 1
EOF

# 4. Install Uptime Kuma for health monitoring
docker run -d --restart=unless-stopped \
    -v uptime-kuma:/app/data \
    -p 3001:3001 \
    louislam/uptime-kuma:1
```

---

## Step 5: DNS Failover Configuration

### Option A: Cloudflare DNS Manual Switch (Simple & Reliable)

```bash
# === Install Cloudflare CLI on Primary ===
apt install -y cloudflared

# Get API Token (Dashboard → My Profile → API Tokens)
export CF_API_TOKEN="your_api_token_here"
export CF_ACCOUNT_ID="your_account_id"
export CF_ZONE_ID="your_zone_id"

# Create failover script at /opt/scripts/failover-dns.sh
cat > /opt/scripts/failover-dns.sh << 'SCRIPT'
#!/bin/bash
set -euo pipefail

ZONE_ID="$CF_ZONE_ID"
RECORD_ID=$(curl -s -X GET \
    "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/dns_records?type=A&name=example.com" \
    -H "Authorization: Bearer $CF_API_TOKEN" \
    -H "Content-Type: application/json" | jq -r '.result[0].id')

PRIMARY_IP="<primary-ip>"
SECONDARY_IP="<secondary-ip>"
DOMAIN="example.com"

# Switch to secondary IP
curl -s -X PUT \
    "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/dns_records/$RECORD_ID" \
    -H "Authorization: Bearer $CF_API_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"type\":\"A\",\"name\":\"$DOMAIN\",\"content\":\"$SECONDARY_IP\",\"ttl\":60,\"proxied\":true}"

echo "DNS switched to secondary: $SECONDARY_IP"
SCRIPT

chmod +x /opt/scripts/failover-dns.sh
```

### Option B: Cloudflare Worker Auto-Failover (Advanced)

```javascript
// === Cloudflare Worker: auto-failover.js ===
export default {
  async fetch(request) {
    const primaryIP = '<primary-ip>';
    const secondaryIP = '<secondary-ip>';
    
    // Attempt to reach Primary
    const healthCheck = await fetch(`http://${primaryIP}/health`, {
      method: 'GET',
      timeout: 5000,
    });
    
    if (healthCheck.ok) {
      // Primary is healthy, proxy normally
      return fetch(request);
    }
    
    // Primary is down, switch to Secondary
    console.warn(`Primary unhealthy, failover to ${secondaryIP}`);
    
    // Update DNS record (optional, lower TTL for faster propagation)
    await updateDNSRecord(secondaryIP);
    
    // Proxy request to Secondary
    const modifiedUrl = request.url.toString().replace(primaryIP, secondaryIP);
    const modifiedRequest = new Request(modifiedUrl, request);
    
    return fetch(modifiedRequest);
  },
};

async function updateDNSRecord(ip) {
  const resp = await fetch(
    'https://api.cloudflare.com/client/v4/zones/YOUR_ZONE/dns_records',
    {
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
    }
  );
  return resp.json();
}
```

---

## Step 6: Automated Health Checks & Alerts

### Monitoring with Uptime Kuma

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

**Add monitoring targets**:

1. **Primary HTTP** — `http://primary-ip/health` (every 30s)
2. **Secondary HTTP** — `http://secondary-ip/health` (every 30s)
3. **MariaDB Replication** — Monitor `Slave_IO_Running` via MySQL plugin
4. **Cloudflare DNS** — Ping monitor for domain resolution IP
5. **Disk Space** — Custom script checking `/` partition usage

### Custom Health Check Script

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

# Check self-health
SELF_HTTP=$(check_http "$(hostname -i)")
if [[ "$SELF_HTTP" != "200" ]]; then
    echo "ALERT: Self HTTP check failed: $SELF_HTTP"
    curl -s -X POST "$WEBHOOK_URL" \
        -H "Content-Type: application/json" \
        -d "{\"text\":\"🚨 Primary VPS HTTP check failed: $SELF_HTTP\"}" > /dev/null 2>&1
    
    # Trigger failover
    /opt/scripts/failover-dns.sh
    exit 1
fi

# Check Secondary reachability
SECONDARY_HTTP=$(check_http "$SECONDARY_IP")
if [[ "$SECONDARY_HTTP" != "200" ]]; then
    echo "WARNING: Secondary unreachable: $SECONDARY_HTTP"
    curl -s -X POST "$WEBHOOK_URL" \
        -H "Content-Type: application/json" \
        -d "{\"text\":\"⚠️ Secondary VPS unreachable\"}" > /dev/null 2>&1
fi

# Check database replication status
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
# Run every 60 seconds
(crontab -l 2>/dev/null; echo "* * * * * /opt/scripts/health-check.sh >> /var/log/health-check.log 2>&1") | crontab -
```

---

## Step 7: Data Backup Strategy

### Three-Tier Backup Approach

```
Level 1: Real-time sync (master-slave + rsync) → RPO ≈ 0
Level 2: Hourly snapshots (VPS provider snapshots) → RPO = 1h
Level 3: Daily off-site backup (S3 / Backblaze B2) → RPO = 24h
```

```bash
# === Daily backup script ===
cat > /opt/scripts/daily-backup.sh << 'EOF'
#!/bin/bash
set -euo pipefail

BACKUP_DIR="/opt/backups"
DATE=$(date +%Y%m%d_%H%M%S)
MYSQL_USER="myapp_user"
MYSQL_PASS="My@ppStr0ng!"
MYSQL_DB="myapp"

# 1. Database backup
mkdir -p "$BACKUP_DIR/mysql"
mysqldump -u "$MYSQL_USER" -p"$MYSQL_PASS" \
    --single-transaction --routines --triggers \
    "$MYSQL_DB" > "$BACKUP_DIR/mysql/${DATE}_${MYSQL_DB}.sql"

# 2. Compress
gzip "$BACKUP_DIR/mysql/${DATE}_${MYSQL_DB}.sql"

# 3. Upload to S3-compatible storage (Backblaze B2 / AWS S3)
export B2_ACCOUNT_ID="your_b2_account_id"
export B2_APPLICATION_KEY="your_b2_application_key"
b2 upload-file --json myapp-backups \
    "$BACKUP_DIR/mysql/${DATE}_${MYSQL_DB}.sql.gz" \
    "backups/${DATE}_${MYSQL_DB}.sql.gz"

# 4. Clean up backups older than 30 days
find "$BACKUP_DIR" -name "*.gz" -mtime +30 -delete

echo "Backup completed: $DATE"
EOF

chmod +x /opt/scripts/daily-backup.sh

# Run daily at 2 AM
echo "0 2 * * * /opt/scripts/daily-backup.sh" | crontab -
```

---

## Failover Drill

**Regular drills are the core of any disaster recovery architecture**. Perform a full switchover test monthly:

```bash
# Simulate failover procedure
cat > /opt/scripts/dr-drill.sh << 'EOF'
#!/bin/bash
set -euo pipefail

echo "=== DR Drill Starting at $(date) ==="

# Step 1: Record current state
echo "[1/5] Recording current state..."
PRIMARY_IP="<primary-ip>"
SECONDARY_IP="<secondary-ip>"
CURRENT_IP=$(dig +short example.com | head -1)
echo "Current active IP: $CURRENT_IP"

# Step 2: Pause Primary services
echo "[2/5] Simulating Primary failure..."
systemctl stop nginx
echo "Primary Nginx stopped"

# Step 3: Wait for DNS failover (or trigger manually)
echo "[3/5] Waiting for DNS failover..."
sleep 10
# Or use auto script: /opt/scripts/failover-dns.sh

# Step 4: Verify Secondary takeover
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

# Step 5: Restore Primary
echo "[5/5] Restoring Primary..."
systemctl start nginx
echo "Primary Nginx restarted"

echo "=== DR Drill Completed at $(date) ==="
EOF

chmod +x /opt/scripts/dr-drill.sh
```

---

## Cost Breakdown

| Item | Cost |
|------|------|
| Primary VPS (2C4G, Singapore) | ~$6-10/month |
| Secondary VPS (2C4G, Frankfurt) | ~€5-8/month |
| Cloudflare Pro (optional, advanced Workers) | $5/month |
| Backblaze B2 Storage (100GB) | ~$0.60/month |
| **Total** | **~$17-24/month** |

Compare this to: a single high-performance VPS ($20-40/month) + downtime costs per incident (unknown, potentially thousands of dollars).

---

## Summary

| Component | Choice | Purpose |
|-----------|--------|---------|
| DNS Failover | Cloudflare DNS API | Fast traffic switching |
| Database Sync | MariaDB Master-Slave | Near-real-time data sync |
| File Sync | rsync (cron) | Static file sync |
| Health Checks | Uptime Kuma + custom scripts | Automatic fault detection |
| Alert Notifications | Slack/Discord Webhook | Instant notifications |
| Data Backup | mysqldump + B2/S3 | Long-term backup |

This architecture delivers **enterprise-grade high availability** for your business at just **$20/month**. The key isn't technical complexity — it's **regular drills** and **continuous monitoring**.

> 💡 **Next steps**: Based on your business scale, consider expanding to three-region deployment, introducing load balancers, or using Terraform for Infrastructure as Code (IaC).
