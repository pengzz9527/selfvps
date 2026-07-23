---
title: "VPS 磁盘空间清理与自动扩容 — 告别存储焦虑的完整方案"
date: 2026-07-23
description: "从手动清理到自动化监控，教你用最低成本保持 VPS 磁盘健康运行。"
tags: [vps, 磁盘管理, 自动扩容, 运维]
category: "VPS 运维"
image: "/images/posts/vps-disk-cleanup-auto-scaling/featured.png"
---

## 为什么磁盘空间是 VPS 最大的隐形杀手？

很多 VPS 用户都有过这样的经历：某天突然网站打不开了，SSH 连不上去了，一查才发现——**磁盘满了**。

磁盘爆满不只是"存不下文件"那么简单，它会导致：
- **数据库写入失败**（MySQL/PostgreSQL 直接报错）
- **日志无法写入**（系统日志堆积，排查问题无从下手）
- **网站服务崩溃**（Nginx/Apache 无法生成临时文件）
- **系统启动异常**（swap 分区无法使用）

本文将带你建立一套从**手动清理 → 监控告警 → 自动扩容**的完整方案。

---

## 第一步：快速定位谁在吃磁盘

### 查看整体使用情况

```bash
df -h
```

输出示例：
```
Filesystem      Size  Used Avail Use% Mounted on
/dev/sda1        50G   47G  3.0G  94% /
tmpfs           1.6G     0  1.6G   0% /dev/shm
```

### 找出大文件和大目录

```bash
# 查看各目录占用（MB 级别）
du -sh /* | sort -rh | head -20

# 深入某个目录
du -sh /var/* | sort -rh | head -10
```

### 常见"藏污纳垢"的地方

| 位置 | 常见问题 | 清理方式 |
|------|---------|---------|
| `/var/log` | 日志文件堆积 | `journalctl --vacuum-size=100M` |
| `/var/cache/apt` | 软件包缓存 | `apt clean` |
| `~/.local/share/Trash` | 回收站未清空 | `rm -rf ~/.local/share/Trash/*` |
| `/tmp` | 临时文件未清理 | `sudo rm -rf /tmp/*` |
| Docker | 悬空镜像和构建缓存 | `docker system prune -a` |

---

## 第二步：自动化清理脚本

创建一个自动清理脚本 `/usr/local/bin/disk-cleanup.sh`：

```bash
#!/bin/bash

LOG_FILE="/var/log/disk-cleanup.log"
THRESHOLD=80

echo "$(date): Starting disk cleanup..." >> $LOG_FILE

# 1. 清理 apt/yum 缓存
apt-get clean && apt-get autoremove -y >> $LOG_FILE 2>&1

# 2. 清理 journal 日志（保留最近 7 天）
journalctl --vacuum-time=7d >> $LOG_FILE 2>&1

# 3. 清理系统日志
find /var/log -name "*.gz" -delete
find /var/log -name "*.old" -delete
find /var/log -size +100M -exec truncate -s 0 {} \;

# 4. 清理 Docker
docker system prune -af >> $LOG_FILE 2>&1

# 5. 清理临时文件
find /tmp -type f -atime +3 -delete
find /var/tmp -type f -atime +3 -delete

# 检查清理后剩余空间
USE_PERCENT=$(df / | tail -1 | awk '{print $5}' | sed 's/%//')
echo "$(date): Disk usage after cleanup: ${USE_PERCENT}%" >> $LOG_FILE

# 如果仍然超过阈值，发送告警
if [ "$USE_PERCENT" -ge "$THRESHOLD" ]; then
    echo "$(date): WARNING - Disk usage still above ${THRESHOLD}%!" >> $LOG_FILE
    # 这里可以添加邮件或 webhook 通知
fi
```

设置为每周自动执行：

```bash
chmod +x /usr/local/bin/disk-cleanup.sh
crontab -e
# 添加：0 3 * * 0 /usr/local/bin/disk-cleanup.sh
```

---

## 第三步：磁盘使用监控与告警

### 使用 Prometheus + Node Exporter

```yaml
# docker-compose.yml
version: '3'
services:
  prometheus:
    image: prom/prometheus
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - prom_data:/prometheus

  node_exporter:
    image: prom/node-exporter
    ports:
      - "9100:9100"
    restart: unless-stopped

volumes:
  prom_data:
```

```yaml
# prometheus.yml
global:
  scrape_interval: 30s

scrape_configs:
  - job_name: 'node'
    static_configs:
      - targets: ['localhost:9100']
```

### 简单的 Shell 告警脚本

```bash
#!/bin/bash
THRESHOLD=85
WEBHOOK_URL="https://your-webhook-url"

USE_PERCENT=$(df / | tail -1 | awk '{print $5}' | sed 's/%//')

if [ "$USE_PERCENT" -ge "$THRESHOLD" ]; then
    curl -X POST $WEBHOOK_URL \
        -H 'Content-Type: application/json' \
        -d "{\"text\":\"⚠️ VPS 磁盘使用率已达 ${USE_PERCENT}%\"}"
fi
```

---

## 第四步：在线扩容磁盘

当清理也来不及的时候，你需要的是**扩容**。

### 云服务商在线扩容

大多数云平台支持在线扩容：
1. 控制台找到云服务器 → 磁盘管理
2. 点击"扩容"，选择新容量
3. 登录服务器，执行以下命令：

```bash
# 1. 查看当前磁盘分区
lsblk

# 2. 扩展分区（以 /dev/sda 为例）
growpart /dev/sda 1

# 3. 扩展文件系统
# ext4:
resize2fs /dev/sda1
# xfs:
xfs_growfs /

# 4. 验证
df -h
```

### 使用 LVM 实现灵活扩容

如果你的 VPS 使用了 LVM（逻辑卷管理），扩容就非常简单了：

```bash
# 1. 扩展物理卷
pvresize /dev/sda1

# 2. 扩展逻辑卷
lvextend -l +100%FREE /dev/mapper/vg0-root

# 3. 扩展文件系统
resize2fs /dev/mapper/vg0-root
```

---

## 第五步：预防性策略

### 1. 日志轮转配置

编辑 `/etc/logrotate.conf`：

```
/var/log/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 0640 root adm
}
```

### 2. 限制 Docker 磁盘使用

```bash
# /etc/docker/daemon.json
{
    "storage-driver": "overlay2",
    "log-driver": "json-file",
    "log-opts": {
        "max-size": "10m",
        "max-file": "3"
    },
    "data-root": "/var/lib/docker"
}
```

重启 Docker：`systemctl restart docker`

### 3. 定期磁盘健康检查

```bash
# 检查 SMART 状态
smartctl -a /dev/sda

# 检查文件系统错误
e2fsck -n /dev/sda1
```

---

## 总结

| 阶段 | 操作 | 频率 |
|------|------|------|
| 手动清理 | `du` / `df` / `apt clean` | 每月一次 |
| 自动清理 | cron 脚本 | 每周一次 |
| 监控告警 | Prometheus / Shell 脚本 | 实时 |
| 在线扩容 | 云平台控制台 | 按需 |

**核心原则：不要等磁盘满了才行动。** 建立"监控 → 告警 → 清理 → 扩容"的闭环，才能让 VPS 长期稳定运行。

---

*本文适用于所有 Linux VPS，无论你是用阿里云、腾讯云、AWS 还是 DigitalOcean，这套方案都能帮你省下大量运维时间和数据丢失风险。*
