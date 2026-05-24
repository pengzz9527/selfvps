---
title: "VPS 自动化备份指南：数据库、文件与 Docker 卷的完整方案"
description: "全面讲解 VPS 上的自动化备份策略——涵盖 PostgreSQL/MySQL/SQLite 数据库备份、Docker 卷快照、文件定期归档，以及自动同步到 S3/B2 异地的完整方案"
date: 2026-05-24T10:00:00+08:00
slug: "vps-backup-automation-guide"
image: /images/posts/vps-backup-automation-guide/featured.png
tags: ["备份", "自动化", "VPS", "Docker", "数据库", "运维", "B2", "S3"]
categories: ["运维实战"]
aliases: [/zh/post/vps-backup-automation-guide/]
---

## 引言

> **"只有两份备份还不够——你需要第三份在异地。"**

自托管最大的优势是数据掌控权，但最大的风险也是**数据丢失**。硬盘故障、误操作删除、勒索软件攻击——事故一旦发生，没有备份就意味着一切归零。

本文不是讲"要不要备份"，而是给你一套**可以直接上手的自动化备份方案**，涵盖：

- ✅ 数据库自动备份（PostgreSQL / MySQL / SQLite）
- ✅ Docker 卷的冷备份与快照
- ✅ 文件定期归档与版本管理
- ✅ 自动同步到云存储（Backblaze B2 / S3 兼容存储）
- ✅ 备份完整性校验与自动清理
- ✅ 灾难恢复测试方法

---

## 架构概览

```
┌─────────────────────────────┐
│          VPS 服务器           │
│  ┌──────────┐ ┌──────────┐  │
│  │ 定时任务  │ │ 备份脚本  │  │
│  │ (cron)  │→│(backup.sh)│  │
│  └──────────┘ └─────┬────┘  │
│                     │       │
│          ┌──────────▼────┐  │
│          │   本地备份目录   │  │
│          │  /var/backups/ │  │
│          └──────┬────────┘  │
│                 │          │
│        ┌────────▼────────┐ │
│        │ 异地同步 (rclone)│ │
│        │ → B2 / S3 / GCS │ │
│        └─────────────────┘ │
└─────────────────────────────┘
```

核心原则：**3-2-1 备份策略**
- **3** 份数据副本
- **2** 种不同存储介质
- **1** 份异地存储

---

## 1. 数据库自动备份

### 1.1 PostgreSQL 备份脚本

```bash
#!/bin/bash
# pg_backup.sh — PostgreSQL 定时备份
PG_DATABASES=("myapp" "nextcloud" "matrix")
BACKUP_DIR="/var/backups/postgresql"
RETENTION_DAYS=30
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

mkdir -p "$BACKUP_DIR"

for db in "${PG_DATABASES[@]}"; do
    # 使用 pg_dump 导出压缩格式
    pg_dump -U postgres "$db" \
      --format=custom \
      --compress=9 \
      --file="${BACKUP_DIR}/${db}_${TIMESTAMP}.dump"

    # 生成校验和
    sha256sum "${BACKUP_DIR}/${db}_${TIMESTAMP}.dump" \
      > "${BACKUP_DIR}/${db}_${TIMESTAMP}.dump.sha256"

    echo "✅ PostgreSQL backup completed: $db"
done

# 清理超过保留天数的旧备份
find "$BACKUP_DIR" -name "*.dump" -mtime +$RETENTION_DAYS -delete
find "$BACKUP_DIR" -name "*.dump.sha256" -mtime +$RETENTION_DAYS -delete
```

### 1.2 MySQL/MariaDB 备份脚本

```bash
#!/bin/bash
# mysql_backup.sh — MySQL/MariaDB 定时备份
MYSQL_USER="backup_user"
MYSQL_PASSWORD="your_secure_password"
BACKUP_DIR="/var/backups/mysql"
RETENTION_DAYS=30
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

mkdir -p "$BACKUP_DIR"

# 获取所有数据库列表（排除系统库）
databases=$(mysql -u "$MYSQL_USER" -p"$MYSQL_PASSWORD" \
  -e "SHOW DATABASES;" | grep -Ev \
  "(Database|information_schema|performance_schema|mysql|sys)")

for db in $databases; do
    mysqldump -u "$MYSQL_USER" -p"$MYSQL_PASSWORD" \
      --single-transaction \
      --routines \
      --triggers \
      --events \
      "$db" | gzip -9 \
      > "${BACKUP_DIR}/${db}_${TIMESTAMP}.sql.gz"

    sha256sum "${BACKUP_DIR}/${db}_${TIMESTAMP}.sql.gz" \
      > "${BACKUP_DIR}/${db}_${TIMESTAMP}.sql.gz.sha256"

    echo "✅ MySQL backup completed: $db"
done

# 清理旧备份
find "$BACKUP_DIR" -name "*.sql.gz" -mtime +$RETENTION_DAYS -delete
find "$BACKUP_DIR" -name "*.sql.gz.sha256" -mtime +$RETENTION_DAYS -delete
```

### 1.3 SQLite 在线备份

SQLite 无法像 PG/MySQL 那样远程导出，但可以使用 `sqlite3` 的在线备份命令：

```bash
#!/bin/bash
# sqlite_backup.sh
BACKUP_DIR="/var/backups/sqlite"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# 查找所有 SQLite 数据库并逐个备份
find /var/lib -name "*.db" -o -name "*.sqlite" | while read db_path; do
    db_name=$(basename "$db_path")
    backup_file="${BACKUP_DIR}/${db_name}_${TIMESTAMP}.bak"

    sqlite3 "$db_path" ".backup '$backup_file'"
    gzip -9 "$backup_file"

    sha256sum "${backup_file}.gz" > "${backup_file}.gz.sha256"
    echo "✅ SQLite backup: $db_name"
done
```

> ⚠️ **注意**：SQLite 的 `.backup` 命令在备份时会持有读锁，对写入操作短暂的阻塞。建议在低峰期运行。

---

## 2. Docker 卷备份

Docker 卷通常存储在 `/var/lib/docker/volumes/` 下，但直接复制可能存在一致性风险。最佳做法是通过临时容器实现一致性快照。

### 2.1 Docker 卷备份脚本

```bash
#!/bin/bash
# docker_volume_backup.sh
BACKUP_DIR="/var/backups/docker-volumes"
RETENTION_DAYS=30
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

VOLUMES=$(docker volume ls --format '{{.Name}}')

for volume in $VOLUMES; do
    echo "Backing up volume: $volume"

    # 用临时 Alpine 容器打包卷内容
    docker run --rm \
      -v "${volume}:/source:ro" \
      -v "${BACKUP_DIR}:/backup" \
      alpine:latest \
      tar czf "/backup/${volume}_${TIMESTAMP}.tar.gz" \
        -C /source .

    sha256sum "${BACKUP_DIR}/${volume}_${TIMESTAMP}.tar.gz" \
      > "${BACKUP_DIR}/${volume}_${TIMESTAMP}.tar.gz.sha256"

    echo "✅ Volume backup: $volume"
done

# 清理旧备份
find "$BACKUP_DIR" -name "*.tar.gz" -mtime +$RETENTION_DAYS -delete
```

### 2.2 运行中服务的零停机备份

对于数据库之类的有状态服务，最安全的方式是走"数据库自身的导出工具"（如 1.1 和 1.2 中的 pg_dump/mysqldump），而不是直接备份卷文件。

对于文件存储类的卷（如 Nextcloud 数据、Nginx 静态资源），上述 tar 方法在只读挂载下是安全的。

---

## 3. 文件与配置备份

### 3.1 增量备份（基于 rsync）

```bash
#!/bin/bash
# rsync_backup.sh — 增量文件同步
SOURCE_DIRS=(
    "/etc/nginx"
    "/etc/letsencrypt"
    "/home"
    "/var/www"
)
BACKUP_DIR="/var/backups/files"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

mkdir -p "$BACKUP_DIR"

for dir in "${SOURCE_DIRS[@]}"; do
    dir_name=$(echo "$dir" | tr '/' '_')
    # 硬链接方式实现增量备份（类似 Time Machine）
    latest_link="${BACKUP_DIR}/latest_${dir_name}"
    target="${BACKUP_DIR}/${dir_name}_${TIMESTAMP}"

    rsync -aHAXS --link-dest="$latest_link" \
      "$dir" "$target"

    # 更新 latest 软链接
    rm -f "$latest_link"
    ln -s "$target" "$latest_link"

    echo "✅ rsync backup: $dir → $target"
done
```

这种方案的精妙之处在于：**第一次备份是全量，之后每次只保存变更的文件**，未修改的文件通过硬链接共享，不占用额外空间。

### 3.2 加密备份（GPG）

如果需要将备份传输到云端，强烈建议加密：

```bash
# 加密单个备份文件
gpg --symmetric --cipher-algo AES256 \
  --passphrase "your-backup-passphrase" \
  -o backup.tar.gz.gpg backup.tar.gz

# 解密
gpg --decrypt --passphrase "your-backup-passphrase" \
  -o backup.tar.gz backup.tar.gz.gpg
```

---

## 4. 异地同步（rclone）

### 4.1 安装和配置 rclone

```bash
# 安装 rclone
curl https://rclone.org/install.sh | sudo bash

# 交互式配置存储后端
rclone config

# 选择 provider：Backblaze B2 / Amazon S3 / Google Cloud Storage 等
```

### 4.2 自动同步脚本

```bash
#!/bin/bash
# rclone_sync.sh — 同步本地备份到异地
REMOTE="b2:my-vps-backups"  # 替换为你的 rclone remote
LOCAL_BACKUP_DIR="/var/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# 同步到 B2（增量，跳过已有文件）
rclone sync "$LOCAL_BACKUP_DIR" "$REMOTE/${TIMESTAMP}/" \
  --progress \
  --transfers=4 \
  --checkers=8 \
  --ignore-existing

# 保留最近 7 次远程快照
rclone lsd "$REMOTE" | awk '{print $5}' | sort | head -n -7 \
  | while read old_snapshot; do
    rclone purge "${REMOTE}/${old_snapshot}/"
    echo "🧹 Purged old remote snapshot: $old_snapshot"
done
```

### 4.3 成本对比

| 目标存储 | 价格（每 GB/月） | 出站流量 | 适合场景 |
|---------|----------------|---------|---------|
| Backblaze B2 | ~$0.006/GB | 前 10GB 免费，之后 $0.01/GB | ⭐ 最推荐的冷备份 |
| AWS S3 Glacier | ~$0.004/GB | $0.09/GB | 长期归档 |
| Cloudflare R2 | $0.015/GB | 免费 | 频繁访问的备份 |
| Hetzner Storage Box | €0.04/GB | 免费（内网） | 如果你用 Hetzner |
| rsync.net | $0.02/GB | 免费 | 纯 POSIX 兼容 |

> 💡 **推荐**：个人用户选择 **Backblaze B2**，每月 10GB 以内的备份几乎是免费的。如果已有 Hetzner VPS，用 Storage Box 内网同步速度更快、成本更低。

---

## 5. 整合定时任务

### 5.1 统一编排脚本

```bash
#!/bin/bash
# /usr/local/bin/backup-all.sh — 全自动备份编排
set -e

NOTIFY_URL="https://hooks.slack.com/services/YOUR/WEBHOOK"
START_TIME=$(date +%s)

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# Step 1: 数据库备份
log "Starting database backups..."
bash /usr/local/bin/pg_backup.sh
bash /usr/local/bin/mysql_backup.sh
bash /usr/local/bin/sqlite_backup.sh

# Step 2: Docker 卷备份
log "Starting Docker volume backups..."
bash /usr/local/bin/docker_volume_backup.sh

# Step 3: 文件备份
log "Starting file backups..."
bash /usr/local/bin/rsync_backup.sh

# Step 4: 校验完整性
log "Verifying backup integrity..."
find /var/backups -name "*.sha256" -exec sh -c '
    sha256sum -c "$1" || echo "❌ FAILED: $1"
' _ {} \;

# Step 5: 同步到异地
log "Syncing to remote storage..."
bash /usr/local/bin/rclone_sync.sh

# 完成
DURATION=$(( $(date +%s) - START_TIME ))
log "✅ All backups completed in ${DURATION}s"

# 可选：发送通知
# curl -s -X POST -H "Content-Type: application/json" \
#   -d "{\"text\": \"✅ Backup completed in ${DURATION}s\"}" \
#   "$NOTIFY_URL"
```

### 5.2 设置 crontab

```bash
# 编辑 crontab
sudo crontab -e

# 每天凌晨 3:00 执行全备
0 3 * * * /usr/local/bin/backup-all.sh >> /var/log/backup.log 2>&1

# 每 4 小时执行一次数据库备份（可选高频）
0 */4 * * * /usr/local/bin/pg_backup.sh >> /var/log/backup.log 2>&1
0 */4 * * * /usr/local/bin/mysql_backup.sh >> /var/log/backup.log 2>&1
```

---

## 6. 恢复演练

> **没有测试过的备份等于没有备份。**

### 6.1 PostgreSQL 恢复

```bash
# 从自定义格式恢复
pg_restore -U postgres -d myapp \
  --clean --if-exists \
  /var/backups/postgresql/myapp_20260524_030000.dump

# 从 SQL 文件恢复
psql -U postgres -d myapp \
  -f /var/backups/postgresql/myapp_20260524_030000.sql
```

### 6.2 Docker 卷恢复

```bash
# 创建新卷并从备份恢复
docker volume create myapp_data

docker run --rm \
  -v "myapp_data:/target" \
  -v "/var/backups/docker-volumes:/backup:ro" \
  alpine:latest \
  tar xzf "/backup/myapp_data_20260524_030000.tar.gz" \
    -C /target
```

### 6.3 自动化恢复测试

```bash
#!/bin/bash
# test_restore.sh — 在临时目录测试最近一次备份的可恢复性
set -e

TEST_DIR="/tmp/restore-test-$(date +%s)"
mkdir -p "$TEST_DIR"

echo "=== Testing restore of latest DB backups ==="

# 对 PostgreSQL 测试恢复
latest_pg=$(ls -t /var/backups/postgresql/*.dump | head -1)
pg_restore -l "$latest_pg" > /dev/null \
  && echo "✅ PostgreSQL dump is valid: $latest_pg" \
  || echo "❌ PostgreSQL dump is CORRUPT: $latest_pg"

# 对 MySQL 测试恢复
latest_mysql=$(ls -t /var/backups/mysql/*.sql.gz | head -1)
gunzip -t "$latest_mysql" \
  && echo "✅ MySQL dump is valid: $latest_mysql" \
  || echo "❌ MySQL dump is CORRUPT: $latest_mysql"

# 对 tar 文件测试完整性
find /var/backups/docker-volumes -name "*.tar.gz" -exec sh -c '
    if ! tar tzf "$1" > /dev/null 2>&1; then
        echo "❌ CORRUPT archive: $1"
    fi
' _ {} \;

rm -rf "$TEST_DIR"
echo "=== Restore test complete ==="
```

建议每月运行一次恢复测试（放入 crontab）：

```bash
# 每月 1 号凌晨 5 点执行恢复测试
0 5 1 * * /usr/local/bin/test_restore.sh >> /var/log/backup-test.log 2>&1
```

---

## 7. 监控与告警

### 7.1 备份成功率监控

在备份脚本末尾添加 Exit Code 检查：

```bash
# 如果任意步骤失败，发送告警
if [ $? -ne 0 ]; then
    curl -s "https://api.healthchecks.io/ping/YOUR-UUID/fail"
else
    curl -s "https://api.healthchecks.io/ping/YOUR-UUID"
fi
```

[Healthchecks.io](https://healthchecks.io) 是一个免费的开源监控服务，如果备份脚本未按时执行，它会发送告警通知。

### 7.2 备份大小趋势

```bash
# 记录每日备份大小
du -sh /var/backups/ \
  >> /var/log/backup-size.log

# 查看趋势
tail -30 /var/log/backup-size.log
```

---

## 8. 完整自动化部署

用一行命令部署整套备份方案：

```bash
# 从 GitHub 下载完整备份脚本集
git clone https://github.com/yourname/vps-backup-scripts.git /opt/backup-scripts

# 创建备份目录
sudo mkdir -p /var/backups/{postgresql,mysql,sqlite,docker-volumes,files}

# 安装依赖
sudo apt install -y postgresql-client mysql-client rclone

# 设置 crontab
(crontab -l 2>/dev/null; echo "0 3 * * * /opt/backup-scripts/backup-all.sh >> /var/log/backup.log 2>&1") | crontab -

# 配置 rclone
rclone config
```

---

## 总结

一个可靠的备份方案不需要复杂的工具链。本文的方案使用 bash 脚本 + cron + rclone 三件套，零外部依赖、完全开源、极其灵活。

**行动清单：**

| 步骤 | 操作 | 耗时 |
|------|------|------|
| 1 | 选择异地存储（推荐 B2） | 10 分钟 |
| 2 | 部署数据库备份脚本 | 15 分钟 |
| 3 | 部署 Docker 卷备份 | 10 分钟 |
| 4 | 配置 rclone 异地同步 | 15 分钟 |
| 5 | 设置 crontab 自动执行 | 5 分钟 |
| 6 | 进行一次完整恢复演练 | 30 分钟 |

备份不是"做了就行"——**定期测试恢复**才是关键。记住：你的第一次真正恢复，不应该发生在事故现场。

---

## 延伸阅读

- [rclone 官方文档](https://rclone.org/docs/)
- [Backblaze B2 与 rclone 集成](https://help.backblaze.com/hc/en-us/articles/217666928-Backblaze-B2-with-rclone)
- [Healthchecks.io — 开源任务监控](https://healthchecks.io/)
- [borgbackup — 更高级的去重备份工具](https://www.borgbackup.org/)
- [restic — 快速、安全的加密备份](https://restic.net/)
