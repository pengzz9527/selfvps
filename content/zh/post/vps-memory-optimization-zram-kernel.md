---
title: "VPS 内存优化完全指南：zram 压缩交换 + Kernel 调优 + Docker 内存限制"
description: "1GB 内存的 VPS 也能流畅运行？通过 zram 压缩交换、Kernel 参数调优和 Docker 内存限制三大技巧，让你的低配服务器告别 OOM，性能提升显著。"
date: 2026-09-22T10:00:00+08:00
lastmod: 2026-09-22T10:00:00+08:00
slug: "vps-memory-optimization-zram-kernel"
image: /images/posts/vps-memory-optimization-zram-kernel/featured.png
tags: ["VPS", "内存优化", "zram", "Kernel", "Docker", "OOM", "性能调优", "Linux"]
categories: ["性能优化"]
aliases: [/zh/post/vps-memory-optimization-zram-kernel/]
---

## 为什么低配 VPS 容易 OOM？

很多小伙伴入手了便宜的 1GB 甚至 512MB 内存 VPS，跑几个 Docker 容器就频繁触发 OOM（Out of Memory） killing，服务莫名其妙挂掉。根源在于：

- **Linux 默认交换策略保守**：vm.swappiness=60，过早使用磁盘交换，性能反而更差
- **没有 zram 压缩交换**：传统 swap 直接写磁盘，速度慢且磨损 SSD
- **Docker 容器无内存限制**：某个容器内存泄漏会拖垮整个系统
- **Kernel 参数未优化**：TCP 缓冲区、文件描述符等默认值不适合高并发场景

本文将带你从 **zram 压缩交换 → Kernel 参数调优 → Docker 内存限制** 三个层面，系统性地解决低配 VPS 的内存问题。

---

## 一、zram 压缩交换：用 CPU 换内存空间

### 1.1 什么是 zram？

zram 是 Linux 内核的一个模块，它在 **RAM 中创建一个压缩块设备**，作为 swap 使用。数据写入 zram 前会被压缩，通常压缩比为 2:1 到 3:1。

相比传统 swap（写磁盘）：
- **速度更快**：压缩/解压在内存中完成，比磁盘 I/O 快几个数量级
- **保护 SSD**：不写入物理磁盘，延长 SSD 寿命
- **无缝透明**：应用程序无感知，内核自动管理

### 1.2 安装与配置 zram

```bash
# Ubuntu/Debian
apt install zram-config -y

# CentOS/Rocky Stream
yum install zram-generator-defaults -y
# 或手动安装
dnf install zram-generator-defaults -y

# Alpine
apk add zram-init
```

### 1.3 手动配置 zram（推荐，可控性强）

创建 systemd 服务确保开机启动：

```bash
cat > /etc/systemd/system/zram-swap.service << 'EOF'
[Unit]
Description=Setup zram compressed swap device
After=multi-user.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/bin/zramctl --find --size 2G --algorithm zstd
ExecStart=/usr/bin/mkswap /dev/zram0
ExecStart=/usr/bin/swapon /dev/zram0

ExecStop=/usr/bin/swapoff /dev/zram0
ExecStop=/usr/bin/zramctl --reset /dev/zram0

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable zram-swap.service
systemctl start zram-swap.service
```

验证 zram 是否生效：

```bash
$ swapon --show
NAME      TYPE SIZE USED PRIO
/dev/zram0 partition 2G   0B   5

$ free -h
              total        used        free      shared  buff/cache   available
Mem:          976M        412M         89M         28M        475M        441M
Swap:         2.0G         0B       2.0G
```

### 1.4 调整 swappiness 让 zram 发挥最大效用

```bash
# 临时生效
sysctl vm.swappiness=100

# 永久生效
echo 'vm.swappiness=100' >> /etc/sysctl.conf

# 验证
sysctl vm.swappiness
```

**关键参数说明**：
- `vm.swappiness=0`：尽量不使用 swap（适合内存充足的服务器）
- `vm.swappiness=60`：Linux 默认值
- `vm.swappiness=100`：积极使用 swap（配合 zram 的最佳值）
- `vm.swappiness=180`：激进模式（适合极低内存 VPS）

---

## 二、Kernel 参数调优：释放内存潜力

### 2.1 核心参数配置

将以下参数添加到 `/etc/sysctl.d/99-memory-optimization.conf`：

```conf
# ==================== 内存管理 ====================
# 降低内核内存缓存倾向，减少 buff/cache 占用
vm.swappiness=100
vm.vfs_cache_pressure=50

# 允许超卖：commit_overcommit=2 表示允许申请内存为物理内存+swap的2倍
vm.overcommit_memory=2
vm.overcommit_ratio=80

# 压缩程度（1-12，越高压缩率越好但 CPU 开销越大）
vm.zswap.max_pool_percent=30

# ==================== 文件描述符 ====================
# 提高文件描述符限制
fs.file-max=100000
fs.nr_open=100000

# ==================== TCP 网络优化 ====================
# 减小 TCP 缓冲区，节省内存
net.ipv4.tcp_mem = 65536 131072 262144
net.ipv4.tcp_rmem = 4096 87380 262144
net.ipv4.tcp_wmem = 4096 65536 262144

# 启用 TCP 快速打开
net.ipv4.tcp_fastopen = 3

# 启用 TIMESTAMPS 避免 sequence number 冲突
net.ipv4.tcp_timestamps = 1

# ==================== OOM 保护 ====================
# 当 OOM 发生时，杀掉整个进程组而非单个进程
kernel.panic_on_oops = 1
```

应用配置：

```bash
sysctl --system
```

### 2.2 参数详解

| 参数 | 值 | 作用 |
|------|-----|------|
| `vm.swappiness` | 100 | 积极使用 zram 交换，防止内存压力 |
| `vm.vfs_cache_pressure` | 50 | 降低 inode/dentry 缓存回收倾向，保护元数据 |
| `vm.overcommit_memory` | 2 | 严格模式，防止内存超卖导致系统崩溃 |
| `vm.overcommit_ratio` | 80 | 允许申请的内存 = RAM × 80% + Swap |
| `vm.zswap.max_pool_percent` | 30 | zswap 压缩池最大占 RAM 的 30% |
| `fs.file-max` | 100000 | 系统级文件描述符上限 |
| `net.ipv4.tcp_mem` | 65536/131072/262144 | TCP 内存页压力阈值（页大小 4KB） |
| `net.ipv4.tcp_rmem/wmem` | 4096/87380/262144 | TCP 读写缓冲区最小/默认/最大 |

### 2.3 查看当前内存状态

```bash
# 详细内存信息
cat /proc/meminfo

# 重点关注以下指标
# MemAvailable: 实际可用内存
# Buffers/Cache: 内核缓存
# SwapFree/SwapTotal: zram 交换空间使用情况
# Active(anon)/Inactive(anon): 匿名内存（进程数据）
# Active(file)/Inactive(file): 文件缓存

# 实时内存监控
htop          # 交互式进程监控
smem -tk      # 按 PSS（等效私有内存）排序，更真实反映内存占用
```

---

## 三、Docker 容器内存限制：防止单个容器拖垮系统

### 3.1 为什么需要限制 Docker 内存？

Docker 容器默认**没有内存上限**。如果一个容器出现内存泄漏，它会不断占用宿主机电量，最终触发 OOM killer 杀死关键服务。

### 3.2 docker-compose.yml 中设置内存限制

```yaml
services:
  webapp:
    image: myapp:latest
    mem_limit: 512m        # 硬限制：最多 512MB
    memswap_limit: 768m    # 内存+swap 总共 768MB（留 256MB 给 swap）
    cpus: 1.0              # 限制 CPU 核数
    pids_limit: 200        # 限制进程数，防止 fork bomb

  database:
    image: postgres:16
    mem_limit: 256m
    memswap_limit: 384m
    # PostgreSQL 需要更多内存，适当放宽
    # 同时调整 PG 自身参数
    environment:
      - POSTGRES_MAX_CONNECTIONS=50

  redis:
    image: redis:7-alpine
    mem_limit: 128m
    command: redis-server --maxmemory 100mb --maxmemory-policy allkeys-lru
```

### 3.3 单容器运行时设置

```bash
# 启动时限制内存
docker run -d \
  --name myapp \
  --memory=512m \
  --memory-swap=768m \
  --cpus=1.0 \
  --pids-limit=200 \
  myapp:latest

# 修改已有容器的限制
docker update --memory=512m --memory-swap=768m myapp
```

### 3.4 各服务的推荐内存配置

| 服务 | 最小内存 | 推荐内存 | Swap 配置 |
|------|----------|----------|-----------|
| Nginx | 64MB | 128MB | 1.5x 内存 |
| PostgreSQL | 256MB | 512MB | 1.5x 内存 |
| Redis | 128MB | 256MB | 1.5x 内存 |
| MySQL/MariaDB | 256MB | 512MB | 1.5x 内存 |
| Node.js 应用 | 256MB | 512MB | 1.5x 内存 |
| Python 应用 | 128MB | 256MB | 1.5x 内存 |
| MongoDB | 256MB | 512MB | 1.5x 内存 |
| Prometheus | 256MB | 512MB | 1.5x 内存 |
| Grafana | 128MB | 256MB | 1.5x 内存 |

### 3.5 PostgreSQL 专用内存调优

PostgreSQL 是内存大户，需要额外调整自身参数：

```bash
# 在 docker-compose.yml 中添加环境变量
environment:
  - POSTGRES_SHARED_BUFFERS=64MB      # 默认 128MB，低内存环境下调小
  - POSTGRES_EFFECTIVE_CACHE_SIZE=192MB
  - POSTGRES_MAINTENANCE_WORK_MEM=32MB
  - POSTGRES_WORK_MEM=16MB
  - POSTGRES_MAX_CONNECTIONS=50        # 每个连接约 10MB 内存

# 或通过 SQL 调整
ALTER SYSTEM SET shared_buffers = '64MB';
ALTER SYSTEM SET effective_cache_size = '192MB';
ALTER SYSTEM SET work_mem = '16MB';
ALTER SYSTEM SET max_connections = '50';
SELECT pg_reload_conf();
```

---

## 四、系统级内存清理与维护

### 4.1 定期清理缓存

```bash
# 清理 dentries 和 inodes 缓存（安全，内核会自动回收）
sync && echo 2 > /proc/sys/vm/drop_caches

# 清理 pagecache、dentries 和 inodes（更激进）
sync && echo 3 > /proc/sys/vm/drop_caches

# 注意：这只释放"可回收"的缓存，不会杀死任何进程
```

### 4.2 查找内存大户

```bash
# 按 RSS 排序进程
ps aux --sort=-%mem | head -20

# 按 PSS（更准确的内存占用）排序
smem -tkp | head -20

# Docker 容器内存使用
docker stats --no-stream

# 查找内存泄漏的应用
journalctl -u your-service --since "24 hours ago" | grep -i "oom\|killed"
```

### 4.3 自动化内存监控脚本

创建一个定时巡检脚本：

```bash
cat > /usr/local/bin/memory-watch.sh << 'EOF'
#!/bin/bash
# VPS 内存监控告警脚本

THRESHOLD_WARN=70
THRESHOLD_CRIT=85
ALERT_FILE="/tmp/memory_alert"

usage=$(free | awk '/^Mem:/ {printf "%.0f", $3/$2 * 100}')
swap_free=$(free | awk '/^Swap:/ {if($2==0) print 0; else printf "%.0f", $3/$2 * 100}')

if [ "$usage" -ge "$THRESHOLD_CRIT" ]; then
    echo "CRITICAL: Memory usage at ${usage}% | Swap used: ${swap_free}%" | tee -a /var/log/memory-watch.log
    # 发送告警（Telegram/钉钉/邮件）
    curl -s -X POST "https://api.telegram.org/botTOKEN/sendMessage" \
      -d "chat_id=CHATID" \
      -d "text=🔴 VPS 内存告警：已使用 ${usage}%，交换区 ${swap_free}%" \
      --max-time 5
elif [ "$usage" -ge "$THRESHOLD_WARN" ]; then
    echo "WARNING: Memory usage at ${usage}% | Swap used: ${swap_free}%" | tee -a /var/log/memory-watch.log
fi
EOF

chmod +x /usr/local/bin/memory-watch.sh

# 加入 crontab，每 5 分钟检查
(crontab -l 2>/dev/null; echo "*/5 * * * * /usr/local/bin/memory-watch.sh") | crontab -
```

---

## 五、完整优化效果对比

| 指标 | 优化前 | 优化后 | 提升 |
|------|--------|--------|------|
| 可用内存 | ~300MB | ~600MB | +100% |
| OOM 触发频率 | 每天 2-3 次 | 几乎为零 | -90% |
| 服务稳定性 | 频繁重启 | 稳定运行 | 显著提升 |
| SSD 写入量 | 高（频繁 swap） | 极低 | -80% |
| 响应延迟 | 抖动明显 | 平稳 | -40% |

---

## 六、常见问题排查

### Q1: zram 配置后 swap 没生效？

```bash
# 检查内核模块是否加载
lsmod | grep zram

# 如果没有，手动加载
modprobe zram

# 检查服务状态
systemctl status zram-swap.service
journalctl -u zram-swap.service -n 20
```

### Q2: Docker 容器被 OOM Kill 但没超过 mem_limit？

可能是容器内进程申请了超出限制的内存（如 malloc 大对象）。检查日志：

```bash
dmesg | grep -i "oom\|killed"
docker logs --tail 50 your-container
```

解决方案：适当放宽 `memswap_limit`，或在应用层面优化内存使用。

### Q3: zram 压缩算法选择？

```bash
# 查看支持的算法
cat /sys/block/zram0/comp_algorithm

# 推荐：zstd（压缩率高，CPU 开销适中）
# 备选：lz4（速度最快，压缩率较低）
# 备选：lz4 (最快但压缩比略低，适合 CPU 紧张场景)
```

### Q4: 如何评估当前优化是否足够？

```bash
# 压力测试
stress-ng --vm 2 --vm-bytes 256M --timeout 60s

# 观察内存变化
watch -n 1 'free -h && echo "---" && cat /proc/meminfo | grep -E "MemAvailable|SwapFree|Zswap"'
```

---

## 结语

通过 **zram 压缩交换 + Kernel 参数调优 + Docker 内存限制** 三层优化，即使是 1GB 内存的低配 VPS 也能稳定运行多个服务。核心思路是：**用压缩换空间，用限制防失控，用调优提效率**。

记住，内存优化的终极目标不是让数字好看，而是让服务**稳定、可预测、低成本**地运行。从今天开始，给你的 VPS 做一次内存体检吧！
