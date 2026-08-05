---
title: "VPS 数据备份与灾难恢复完全指南：从裸机到数据无忧"
description: "从零开始构建 VPS 自动备份系统，涵盖数据库、文件、Docker 卷的完整备份方案，实现一键灾难恢复，让你的数据永远安全。"
date: 2026-08-05T10:00:00+08:00
lastmod: 2026-08-05T10:00:00+08:00
slug: "vps-backup-disaster-recovery"
image: /images/posts/vps-backup-disaster-recovery/featured.png
tags: ["VPS", "备份", "灾难恢复", "Restic", "Docker", "自动化", "数据安全", "DevOps"]
categories: ["运维实践"]
aliases: [/zh/post/vps-backup-disaster-recovery/]
---

## 引言

数据是 VPS 上最珍贵的资产。无论是个人博客、企业网站还是 API 服务，一旦数据丢失，恢复成本可能是重建的数十倍。

你是否经历过这些噩梦场景？

- 磁盘突然损坏，所有数据瞬间消失
- 误删了数据库，且没有备份
- 勒索软件加密了所有文件
- 云服务器宕机，服务商无法及时恢复

**没有备份的 VPS 就像没有保险的房屋**——你可能一直平安无事，但一次意外就足以毁灭一切。

本文将带你构建一套完整的 VPS 备份与灾难恢复系统，实现：

1. **自动备份**：定时执行，无需人工干预
2. **多存储策略**：本地 + 远程双重保障
3. **快速恢复**：一键恢复到任意时间点
4. **灾难恢复**：整机备份与快速重建

---

## 备份策略设计

### 3-2-1 备份原则

行业标准是 **3-2-1 备份原则**：

- **3 份数据副本**：原始数据 + 2 个备份
- **2 种存储介质**：如本地磁盘 + 云存储
- **1 个异地副本**：防止单点故障

```
┌─────────────────────────────────────────────────────┐
│                    VPS (生产环境)                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐           │
│  │  数据库   │  │  网站文件  │  │ Docker卷  │           │
│  └─────┬────┘  └─────┬────┘  └─────┬────┘           │
│        │             │             │                 │
│        └──────────────┼──────────────┘                 │
│                       │                               │
│              ┌────────▼────────┐                       │
│              │   Restic 备份    │                       │
│              └────────┬────────┘                       │
│                       │                               │
│          ┌────────────┼────────────┐                  │
│          │            │            │                  │
│    ┌─────▼────┐ ┌─────▼────┐ ┌─────▼────┐            │
│    │本地SSD   │ │ S3兼容   │ │ AWS S3   │            │
│    │ /backup  │ │  MinIO   │ │ (异地)    │            │
│    └─────────┘ └──────────┘ └──────────┘            │
└─────────────────────────────────────────────────────┘
```

### 备份对象分类

| 数据类型 | 备份策略 | 频率 | 保留策略 |
|---------|---------|------|---------|
| 数据库 | 逻辑备份 (mysqldump/pg_dump) | 每小时 | 30 天 |
| 网站文件 | Restic 加密备份 | 每天 | 7 天完整 + 30 天增量 |
| Docker 卷 | Restic 备份 | 每天 | 7 天完整 + 30 天增量 |
| 系统配置 | rsync 同步 | 每天 | 7 天 |
| 整机镜像 | Timeshift | 每周 | 4 周 |

---

## 第一部分：数据库备份

### MySQL/MariaDB 备份

#### 方案一：逻辑备份 (mysqldump)

```bash
#!/bin/bash
# mysql-backup.sh

BACKUP_DIR="/backup/mysql"
DATE=$(date +%Y%m%d_%H%M%S)
RETAIN_DAYS=30

# 创建备份目录
mkdir -p $BACKUP_DIR/$DATE

# 备份所有数据库
mysqldump --all-databases \
  --single-transaction \
  --routines \
  --triggers \
  --events \
  --quick \
  | gzip > $BACKUP_DIR/$DATE/all-databases.sql.gz

# 备份每个数据库单独文件
for db in $(mysql -e 'SHOW DATABASES' -s --skip-column-names | grep -v '^information_schema$' | grep -v '^performance_schema$'); do
  mysqldump --single-transaction --routines --triggers "$db" \
    | gzip > $BACKUP_DIR/$DATE/${db}.sql.gz
done

# 删除过期备份
find $BACKUP_DIR -type d -mtime +$RETAIN_DAYS -exec rm -rf {} \; 2>/dev/null

# 上传到远程存储
# restic -r s3:s3.amazonaws.com/your-bucket/backups/mysql init
restic -r s3:s3.amazonaws.com/your-bucket/backup/mysql backup $BACKUP_DIR/$DATE

echo "[$(date)] MySQL backup completed: $DATE"
```

#### 方案二：物理备份 (Percona XtraBackup)

对于大型数据库，使用物理备份更快：

```bash
# 安装 Percona XtraBackup
sudo apt-get install -y percona-xtrabackup-80

# 热备份
xtrabackup --backup \
  --target-dir=/backup/mysql/physical/$(date +%Y%m%d_%H%M%S) \
  --user=root \
  --password=your_password

# 准备备份（使其一致）
xtrabackup --prepare --target-dir=/backup/mysql/physical/20260805_100000
```

### PostgreSQL 备份

#### 逻辑备份 (pg_dump)

```bash
#!/bin/bash
# pg-backup.sh

BACKUP_DIR="/backup/postgres"
DATE=$(date +%Y%m%d_%H%M%S)
RETAIN_DAYS=30

mkdir -p $BACKUP_DIR/$DATE

# 备份所有数据库
pg_dumpall -h localhost | gzip > $BACKUP_DIR/$DATE/all-databases.sql.gz

# 备份每个数据库
for db in $(psql -lqt | cut -d \| -f 1 | grep -v '^$\|^Name$' | grep -v 'template[01]'); do
  pg_dump "$db" | gzip > $BACKUP_DIR/$DATE/${db}.sql.gz
done

# 清理过期备份
find $BACKUP_DIR -type d -mtime +$RETAIN_DAYS -exec rm -rf {} \; 2>/dev/null

echo "[$(date)] PostgreSQL backup completed: $DATE"
```

#### 连续归档 (WAL 归档)

对于需要 Point-in-Time Recovery (PITR) 的场景：

```bash
# postgresql.conf 配置
wal_level = replica
archive_mode = on
archive_command = 'restic -r s3:s3.amazonaws.com/your-bucket/wal archive %p'
```

```bash
# 定期全量备份
pg_backup_schedule="0 2 * * * pg_basebackup -D /backup/postgres/base/$(date +%Y%m%d) -Ft -z"
```

---

## 第二部分：文件备份

### Restic：现代备份工具

[Restic](https://restic.net/) 是目前最推荐的备份工具之一，支持：

- 增量备份（只备份变化的数据）
- 端到端加密
- 去重存储（节省空间）
- 支持多种后端（本地、S3、SFTP、Azure 等）

#### 安装 Restic

```bash
# Ubuntu/Debian
wget https://github.com/restic/restic/releases/download/v0.16.1/restic_0.16.1_amd64.deb
sudo dpkg -i restic_0.16.1_amd64.deb

# 或直接从源码编译
go install github.com/restic/restic@latest
```

#### 初始化仓库

```bash
# 本地仓库
restic -r /backup/repos/main init

# S3 兼容存储（如 MinIO）
export RESTIC_REPOSITORY=s3:s3.minio.local:9000/vps-backup
export AWS_ACCESS_KEY_ID=your_access_key
export AWS_SECRET_ACCESS_KEY=your_secret_key
restic init

# AWS S3
export RESTIC_REPOSITORY=s3:s3.amazonaws.com/your-bucket/vps-backup
restic init
```

#### 备份网站文件

```bash
#!/bin/bash
# file-backup.sh

export RESTIC_REPOSITORY=s3:s3.amazonaws.com/your-bucket/vps-backup
export RESTIC_PASSWORD=your_secure_password

# 备份网站目录
restic backup /var/www/html --exclude='*.tmp' --exclude='cache/*'

# 备份配置文件
restic backup /etc/nginx /etc/ssl /root/.ssh

# 备份 Docker 配置
restic backup /opt/docker-compose /root/docker

# 生成快照标签
restic tag add --tag=website /var/www/html

# 清理旧快照（保留最近 7 天）
restic forget --keep-daily=7 --keep-weekly=4 --keep-monthly=12 --prune
```

#### 备份 Docker 卷

```bash
#!/bin/bash
# docker-backup.sh

export RESTIC_REPOSITORY=s3:s3.amazonaws.com/your-bucket/vps-backup
export RESTIC_PASSWORD=your_secure_password

# 备份所有 Docker 卷
for vol in $(docker volume ls -q); do
  restic backup \
    --exclude='*.log' \
    /var/lib/docker/volumes/$vol/_data \
    --tag=$vol
done

# 或使用 docker 备份卷的标准方法
docker run --rm \
  -v backup-data:/data \
  -v /var/lib/docker/volumes:/backup \
  alpine tar czf /data/backup-$(date +%Y%m%d).tar.gz /backup
```

---

## 第三部分：自动化备份

### Cron 定时任务

```bash
# 编辑 crontab
crontab -e

# 添加以下任务
# 每小时备份数据库（工作日）
0 * * * * /opt/scripts/mysql-backup.sh >> /var/log/backup/mysql.log 2>&1

# 每天凌晨 2 点备份文件
0 2 * * * /opt/scripts/file-backup.sh >> /var/log/backup/file.log 2>&1

# 每周日凌晨 3 点备份系统配置
0 3 * * 0 /opt/scripts/config-backup.sh >> /var/log/backup/config.log 2>&1

# 每月 1 号凌晨 4 点整机备份
0 4 1 * * /opt/scripts/full-backup.sh >> /var/log/backup/full.log 2>&1
```

### 备份脚本完整示例

```bash
#!/bin/bash
# full-backup.sh - 完整备份脚本

set -euo pipefail

# 配置
BACKUP_ROOT="/backup/full/$(date +%Y%m%d_%H%M%S)"
RESTIC_REPO="s3:s3.amazonaws.com/your-bucket/vps-backup"
RESTIC_PASSWORD="your_secure_password"
LOG_FILE="/var/log/backup/full-$(date +%Y%m%d).log"

# 日志函数
log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# 错误处理
trap 'log "ERROR: Backup failed at line $LINENO"; exit 1' ERR

log "=== 开始完整备份 ==="

# 1. 创建备份目录
mkdir -p $BACKUP_ROOT/{mysql,postgres,files,config,docker}

# 2. 数据库备份
log "备份 MySQL..."
mysqldump --all-databases --single-transaction | \
  gzip > $BACKUP_ROOT/mysql/all-databases.sql.gz

log "备份 PostgreSQL..."
pg_dumpall | gzip > $BACKUP_ROOT/postgres/all-databases.sql.gz

# 3. 文件备份（使用 Restic）
log "备份网站文件..."
export RESTIC_REPOSITORY=$RESTIC_REPO
export RESTIC_PASSWORD=$RESTIC_PASSWORD

restic backup /var/www/html --tag=website >> $LOG_FILE 2>&1
restic backup /etc --tag=config >> $LOG_FILE 2>&1
restic backup /opt/docker-compose --tag=docker >> $LOG_FILE 2>&1

# 4. 系统配置同步
log "同步系统配置..."
rsync -avz --delete /etc/ $BACKUP_ROOT/config/etc/ >> $LOG_FILE 2>&1
rsync -avz /root/.ssh/ $BACKUP_ROOT/config/ssh/ >> $LOG_FILE 2>&1

# 5. 清理旧备份
log "清理过期备份..."
find $BACKUP_ROOT -type f -mtime +30 -delete 2>/dev/null || true

# 6. 验证备份
log "验证备份完整性..."
restic check >> $LOG_FILE 2>&1

# 7. 生成备份报告
BACKUP_SIZE=$(du -sh $BACKUP_ROOT | cut -f1)
SNAPSHOT_COUNT=$(restic snapshots | wc -l)

log "=== 备份完成 ==="
log "备份大小: $BACKUP_SIZE"
log "快照数量: $SNAPSHOT_COUNT"
log "备份位置: $BACKUP_ROOT"

# 发送通知
curl -X POST "https://api.telegram.org/bot${TG_BOT_TOKEN}/sendMessage" \
  -d "chat_id=${TG_CHAT_ID}" \
  -d "text=✅ VPS 备份完成\n📦 大小: $BACKUP_SIZE\n📸 快照: $SNAPSHOT_COUNT"
```

---

## 第四部分：灾难恢复

### 恢复单个数据库

```bash
# MySQL 恢复
gunzip < /backup/mysql/20260805_100000/all-databases.sql.gz | mysql

# PostgreSQL 恢复
gunzip < /backup/postgres/20260805_100000/all-databases.sql.gz | psql

# 恢复到指定时间点（需要 WAL 归档）
pg_restore -d postgres -c \
  --dbname=template1 \
  /backup/postgres/base/20260805/base.tar.gz
```

### 使用 Restic 恢复

```bash
# 列出所有快照
restic snapshots

# 恢复整个备份
restic restore latest --target=/restore

# 恢复特定目录
restic restore latest --target=/restore --include=/var/www/html

# 恢复单个文件
restic restore snapshot-id --target=/tmp --include=/var/www/html/index.html

# 交互式恢复
restic restore latest --target=/restore --interactive
```

### 整机恢复流程

当 VPS 完全损坏时，使用以下步骤快速恢复：

#### 步骤 1：重建系统

```bash
# 1. 重新安装操作系统
# 2. 安装必要软件
sudo apt-get update
sudo apt-get install -y docker.io nginx mysql-server postgresql restic

# 3. 配置 Restic
export RESTIC_REPOSITORY=s3:s3.amazonaws.com/your-bucket/vps-backup
export RESTIC_PASSWORD=your_secure_password
```

#### 步骤 2：恢复数据

```bash
#!/bin/bash
# disaster-recovery.sh

# 1. 恢复网站文件
restic restore latest \
  --target=/var/www \
  --include=/var/www/html

# 2. 恢复数据库
gunzip < /backup/mysql/latest/all-databases.sql.gz | mysql
gunzip < /backup/postgres/latest/all-databases.sql.gz | psql

# 3. 恢复 Docker 配置
docker compose -f /opt/docker-compose/docker-compose.yml up -d

# 4. 恢复系统配置
rsync -avz /backup/config/etc/ /etc/
rsync -avz /backup/config/ssh/ /root/.ssh/

# 5. 重启服务
systemctl restart nginx mysql postgresql docker
```

#### 步骤 3：验证恢复

```bash
# 检查服务状态
systemctl status nginx mysql postgresql docker

# 检查备份完整性
restic check
restic snapshots

# 验证网站访问
curl -I https://yourdomain.com

# 验证数据库连接
mysql -e "SHOW DATABASES;"
psql -c "\l"
```

---

## 第五部分：监控与告警

### 备份健康检查

```bash
#!/bin/bash
# backup-monitor.sh

LOG_FILE="/var/log/backup/monitor.log"

# 检查最新备份
LATEST_MYSQL=$(find /backup/mysql -type d -mtime -1 | head -1)
LATEST_FILE=$(restic snapshots --tag=website | head -1)

if [ -z "$LATEST_MYSQL" ]; then
  echo "[$(date)] ERROR: No MySQL backup in last 24 hours" | tee -a $LOG_FILE
  # 发送告警
  curl -X POST "https://api.telegram.org/bot${TG_BOT_TOKEN}/sendMessage" \
    -d "chat_id=${TG_CHAT_ID}" \
    -d "text=❌ MySQL 备份失败！"
fi

if [ -z "$LATEST_FILE" ]; then
  echo "[$(date)] ERROR: No file backup in last 24 hours" | tee -a $LOG_FILE
fi

# 检查备份大小异常
BACKUP_SIZE=$(du -sh /backup/full/latest 2>/dev/null | cut -f1)
if [ "$BACKUP_SIZE" = "0" ] || [ -z "$BACKUP_SIZE" ]; then
  echo "[$(date)] ERROR: Backup size is zero!" | tee -a $LOG_FILE
fi
```

### Prometheus + Grafana 监控

```yaml
# node_exporter 收集备份指标
# backup_metrics.yml
backup_duration_seconds:
  help: "Duration of last backup"
backup_failures_total:
  help: "Total number of backup failures"
backup_size_bytes:
  help: "Size of last backup"
```

---

## 第六部分：最佳实践

### 1. 加密备份

```bash
# 使用 Restic 内置加密
export RESTIC_PASSWORD=$(openssl rand -base64 32)

# 或使用 GPG 加密
gpg --encrypt --recipient your@email.com backup.sql
```

### 2. 测试恢复

定期测试恢复流程，确保备份可用：

```bash
# 每月执行一次恢复测试
restic restore latest \
  --target=/tmp/test-restore \
  --exclude='*/proc/*' \
  --exclude='*/sys/*'

# 验证文件完整性
md5sum -c /backup/checksums.md5
```

### 3. 监控存储空间

```bash
#!/bin/bash
# disk-monitor.sh

THRESHOLD=80
USAGE=$(df -h /backup | awk 'NR==2 {print $5}' | sed 's/%//')

if [ "$USAGE" -gt "$THRESHOLD" ]; then
  echo "Disk usage at ${USAGE}%! Cleaning old backups..."
  restic forget --keep-daily=3 --prune
fi
```

### 4. 备份密钥安全

```bash
# 不要将密码硬编码在脚本中
# 使用环境变量或密钥管理工具
echo "RESTIC_PASSWORD=$(openssl rand -base64 32)" >> ~/.bashrc

# 或使用 Vault
vault write secret/backup password=$(openssl rand -base64 32)
```

---

## 结论

构建完善的备份与灾难恢复系统是 VPS 运维的核心能力。通过本文，你学会了：

1. **设计备份策略**：遵循 3-2-1 原则，分层保护不同数据类型
2. **实施数据库备份**：mysqldump/pg_dump + WAL 归档
3. **使用 Restic**：现代备份工具，支持加密、去重、增量
4. **自动化流程**：Cron + 脚本实现无人值守备份
5. **灾难恢复**：整机备份 + 快速重建流程
6. **监控告警**：确保备份系统持续健康运行

**记住：备份的价值不在于备份本身，而在于恢复的成功。** 定期测试你的恢复流程，确保在真正需要时能够成功恢复数据。

---

## 参考资源

- [Restic 官方文档](https://restic.net/documentation/)
- [MySQL 备份最佳实践](https://dev.mysql.com/doc/refman/8.0/en/backup-methods.html)
- [PostgreSQL 备份恢复](https://www.postgresql.org/docs/current/backup.html)
- [3-2-1 备份策略](https://www.backblaze.com/blog/the-3-2-1-backup-strategy/)
