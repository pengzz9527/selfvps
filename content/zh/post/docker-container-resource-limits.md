---
title: "Docker 容器资源限制：防止单个服务拖垮整台 VPS 的完整指南"
description: "学习如何使用 Docker 的 CPU、内存、I/O 和资源隔离功能，避免单个容器耗尽 VPS 资源导致整体服务崩溃"
date: 2026-06-24T10:00:00+08:00
lastmod: 2026-06-24T10:00:00+08:00
slug: "docker-container-resource-limits"
image: /images/posts/docker-container-resource-limits/featured.png
tags: ["Docker", "资源限制", "容器隔离", "VPS", "运维", "性能优化", "Cgroups", "Compose"]
categories: ["容器运维"]
aliases: [/zh/post/docker-container-resource-limits/]
---

## 引言

你花 $5/月 买了一台 1核 1GB 的 VPS，在上面跑了 Nginx、PostgreSQL、一个 Python 应用和一个 Redis 缓存。一切运转良好，直到某天你的 Python 应用在某个请求中触发了内存泄漏——整个 VPS 瞬间被吃光，SSH 连不上、网站 502、所有服务全部瘫痪。

**没有资源限制的容器，就像没有刹车的汽车。** 今天我们就来聊聊如何在 Docker 中为每个容器设置合理的资源上限，让你的 VPS 在多服务环境下依然稳如泰山。

---

## 为什么需要容器资源限制？

Docker 容器默认情况下可以无限制地使用宿主机的所有资源。这意味着：

- 一个失控的容器可以耗尽全部 CPU，导致其他容器无法调度
- 内存泄漏的容器可以吃掉所有 RAM，触发 OOM Killer 杀死关键进程
- 磁盘 I/O 被某个容器占满，数据库查询变得极慢
- 网络带宽被视频转码容器吃光，网站访问卡顿

**核心原则：每个容器都应该有自己的资源天花板。**

---

## 1. 内存限制（Memory Limits）

### 1.1 命令行方式

```bash
docker run -d \
  --memory="512m" \
  --memory-swap="1g" \
  --memory-reservation="256m" \
  --name myapp \
  myapp:latest
```

| 参数 | 含义 | 说明 |
|------|------|------|
| `--memory` | 硬限制 | 容器最多使用的物理内存，超过则被 OOM Kill |
| `--memory-swap` | Swap 总限制 | 内存 + swap 的总和，设为 memory 的两倍较合理 |
| `--memory-reservation` | 软限制 | 当系统资源紧张时优先驱逐低于此值的容器 |

### 1.2 Docker Compose 方式

```yaml
version: "3.8"
services:
  web:
    image: nginx:alpine
    deploy:
      resources:
        limits:
          cpus: "0.5"
          memory: 256M
        reservations:
          cpus: "0.25"
          memory: 128M

  postgres:
    image: postgres:16-alpine
    deploy:
      resources:
        limits:
          cpus: "1.0"
          memory: 512M
        reservations:
          cpus: "0.5"
          memory: 256M

  redis:
    image: redis:7-alpine
    deploy:
      resources:
        limits:
          cpus: "0.25"
          memory: 128M
        reservations:
          cpus: "0.1"
          memory: 64M
```

### 1.3 内存限制最佳实践

```
总可用内存: 1GB
├── PostgreSQL:  512MB (50%)  ← 数据库需要最多内存
├── Application: 256MB  (25%)
├── Redis:       128MB  (13%)
├── Nginx:       64MB   (6%)
└── System:      64MB   (6%) ← 内核 + 系统保留
```

> **经验法则**：给数据库分配最大份额，Web 服务器最小，应用居中。永远不要给容器分配超过物理内存 80% 的限制——你需要留出空间给操作系统本身。

---

## 2. CPU 限制（CPU Quotas）

### 2.1 理解 CPU 限制单位

Docker 使用 **CPU 份额（shares）** 和 **CPU 周期（periods）** 来控制 CPU 使用：

```bash
# 限制容器最多使用 0.5 个 CPU 核心（即 50% 的单核）
docker run -d --cpus="0.5" --name halfcpu myapp

# 限制容器最多使用 1.5 个 CPU 核心
docker run -d --cpus="1.5" --name onecpu_half myapp

# 使用 cfs_quota_us 和 cfs_period_us 精确控制
# cfs_quota_us=25000, cfs_period_us=100000 → 每 100ms 可用 25ms
docker run -d \
  --cpu-quota=25000 \
  --cpu-period=100000 \
  --name precise myapp
```

### 2.2 Compose 中的 CPU 限制

```yaml
services:
  app:
    deploy:
      resources:
        limits:
          cpus: "0.75"    # 最多使用 75% 的一个核心
        reservations:
          cpus: "0.25"    # 保证至少有 25% 的核心可用
```

### 2.3 CPU 限制最佳实践

| 服务类型 | 推荐 CPU 限制 | 理由 |
|----------|--------------|------|
| Nginx/Caddy | 0.25-0.5 | 轻量级，主要做转发 |
| PostgreSQL | 0.5-1.0 | 查询需要计算力 |
| Python/Node.js 应用 | 0.5-1.0 | 取决于并发量 |
| Redis | 0.1-0.25 | 纯内存操作，CPU 需求低 |
| 视频转码 | 1.0-2.0 | 计算密集型，应单独限制 |
| 批处理任务 | 0.1-0.5 | 不应影响在线服务 |

---

## 3. I/O 限制（Block I/O）

磁盘 I/O 是最容易被忽视的资源争抢场景。一个大量读写日志的容器可以让数据库的 IOPS 暴跌。

```bash
# 限制写入带宽为 10MB/s
docker run -d \
  --device-write-bps /dev/sda:10mb \
  --name slowwriter myapp

# 限制读取带宽为 20MB/s
docker run -d \
  --device-read-bps /dev/sda:20mb \
  --name limitedreader myapp

# 限制 IOPS（每秒 IO 操作数）
docker run -d \
  --device-write-iops /dev/sda:100 \
  --name iopslimited myapp
```

### Compose 中的 I/O 限制

```yaml
version: "3.8"
services:
  app:
    devices:
      - "/dev/sda:rw"
    blkio_config:
      device_read_bps:
        - path: "/dev/sda"
          rate: 20mb
      device_write_bps:
        - path: "/dev/sda"
          rate: 10mb
```

> **注意**：blkio_config 在 Docker Swarm 模式下才生效。单机 Compose 需要使用 `docker update` 或命令行参数。

---

## 4. 进程数限制（PIDs Limit）

一个陷入死循环的容器可能疯狂创建进程，最终耗尽系统 PID 表。

```bash
# 限制容器最多创建 100 个进程
docker run -d --pids-limit=100 --name pidlimited myapp

# 不限制（默认值）
docker run -d --pids-limit=-1 --name unlimited myapp
```

### Compose 中的 PID 限制

```yaml
version: "3.8"
services:
  app:
    pids_limit: 200
```

---

## 5. 网络带宽限制

Docker 本身不提供原生的网络带宽限制，但可以通过 Linux tc（traffic control）实现：

```bash
# 限制容器的网络带宽为 10Mbps
docker run -d --name limitednet myapp

# 获取容器 PID
CONTAINER_PID=$(docker inspect -f '{{.State.Pid}}' limitednet)

# 添加 tc 规则限制出站带宽
tc qdisc add dev eth0 root handle 1: htb default 10
tc class add dev eth0 parent 1: classid 1:10 htb rate 10mbit
tc filter add dev eth0 protocol ip parent 1: prio 1 u32 \
  match ip dst 0.0.0.0/0 flowid 1:10
```

对于大多数 VPS 场景，CPU 和内存限制已经足够，网络带宽限制仅在特殊场景下需要。

---

## 6. 实际案例：一个完整的 VPS 资源配置

假设你有一台 **2核 2GB** 的 VPS，运行以下服务：

```yaml
# docker-compose.yml
version: "3.8"
services:
  # 前端 Web 服务器
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    deploy:
      resources:
        limits:
          cpus: "0.25"
          memory: 128M
        reservations:
          cpus: "0.1"
          memory: 64M
    pids_limit: 50

  # 后端 API 服务
  api:
    build: ./api
    ports:
      - "8080:8080"
    deploy:
      resources:
        limits:
          cpus: "1.0"
          memory: 768M
        reservations:
          cpus: "0.5"
          memory: 256M
    pids_limit: 200

  # 数据库
  postgres:
    image: postgres:16-alpine
    volumes:
      - pgdata:/var/lib/postgresql/data
    deploy:
      resources:
        limits:
          cpus: "0.75"
          memory: 512M
        reservations:
          cpus: "0.25"
          memory: 256M
    pids_limit: 100

  # 缓存
  redis:
    image: redis:7-alpine
    deploy:
      resources:
        limits:
          cpus: "0.25"
          memory: 128M
        reservations:
          cpus: "0.1"
          memory: 64M
    pids_limit: 50

volumes:
  pgdata:
```

### 资源分配总览

```
┌──────────────────────────────────────────────────────┐
│              2 核 CPU / 2GB 内存 VPS                  │
├──────────┬───────────┬───────────┬───────────────────┤
│ 服务      │ CPU (限制) │ 内存 (限制) │ 优先级            │
├──────────┼───────────┼───────────┼───────────────────┤
│ Nginx    │ 0.25 核   │ 128MB     │ 高 - 入口层       │
│ API      │ 1.0 核    │ 768MB     │ 最高 - 业务核心    │
│ Postgres │ 0.75 核   │ 512MB     │ 最高 - 数据层      │
│ Redis    │ 0.25 核   │ 128MB     │ 高 - 缓存层        │
│ 系统预留 │ -         │ 512MB     │ N/A - 操作系统    │
└──────────┴───────────┴───────────┴───────────────────┘
```

---

## 7. 监控与调优

设置了资源限制后，你需要持续监控实际使用情况来调优：

### 7.1 使用 docker stats

```bash
# 实时监控所有容器资源使用
docker stats --no-stream

# 查看特定容器
docker stats myapp

# 导出到文件用于分析
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" > usage.txt
```

### 7.2 使用 cAdvisor + Prometheus

```yaml
# cadvisor 服务（轻量级监控）
cadvisor:
  image: gcr.io/cadvisor/cadvisor:latest
  ports:
    - "8080:8080"
  volumes:
    - /:/rootfs:ro
    - /var/run:/var/run:ro
    - /sys:/sys:ro
    - /var/lib/docker/:/var/lib/docker:ro
  deploy:
    resources:
      limits:
        cpus: "0.25"
        memory: 128M
```

### 7.3 识别资源不足

```bash
# 查看被 OOM Kill 的容器
journalctl -k | grep -i "oom\|out of memory"

# 查看容器的 CPU throttling（被限流）
docker stats --format "{{.Name}}\t{{.CPUPerc}}\t{{.MemPerc}}"

# 检查是否有容器频繁重启（可能是内存超限）
docker ps -a --filter "exited=137"  # 137 = SIGKILL (通常 OOM)
```

> **退出码 137** 意味着容器被 SIGKILL 信号终止，最常见的原因是触发了内存限制。如果你看到这个，说明需要增加该容器的内存上限。

---

## 8. 常见误区

### ❌ 误区一：不设限制，"反正我 VPS 够大"

即使你有 16GB 内存的 VPS，多个容器同时失控也会耗尽资源。**限制不是阉割，而是保障。**

### ❌ 误区二：限制设得太紧

如果给应用只分配 64MB 内存，而启动就需要 100MB，容器会反复 OOM 重启，形成恶性循环。建议先观察 24 小时的实际使用情况再设定限制。

### ❌ 误区三：只限制内存，不限制 CPU

CPU 无限使用会导致：
- 其他容器无法获得足够的 CPU 时间片
- 系统整体响应变慢
- SSH 管理变得困难

### ❌ 误区四：忽略系统预留

容器限制之和不能超过物理资源。务必为操作系统、Docker 守护进程和其他系统组件预留至少 10-20% 的资源。

---

## 9. 进阶：使用 cgroup v2 精细控制

现代 Linux 发行版（Ubuntu 22.04+、Debian 12+）默认使用 cgroup v2：

```bash
# 检查 cgroup 版本
stat -fc %T /sys/fs/cgroup/
# 返回 cgroup2fs 表示使用 v2

# cgroup v2 的统一资源控制
cat /sys/fs/cgroup/docker.slice/memory.current
cat /sys/fs/cgroup/docker.slice/cpu.max
```

cgroup v2 相比 v1 的主要改进：
- 统一的层级结构，不再有独立的 memory controller
- 更直观的 `cpu.max` 格式：`quota period`（如 `25000 100000` = 25%）
- 更好的公平调度算法

---

## 总结

| 限制类型 | 命令参数 | Compose 关键字 | 重要性 |
|----------|---------|---------------|--------|
| 内存硬限制 | `--memory` | `deploy.resources.limits.memory` | ⭐⭐⭐⭐⭐ |
| CPU 限制 | `--cpus` | `deploy.resources.limits.cpus` | ⭐⭐⭐⭐⭐ |
| Swap 限制 | `--memory-swap` | `deploy.resources.limits.memory_swap` | ⭐⭐⭐⭐ |
| PID 限制 | `--pids-limit` | `pids_limit` | ⭐⭐⭐⭐ |
| I/O 带宽 | `--device-write-bps` | `blkio_config` | ⭐⭐⭐ |
| 内存软限制 | `--memory-reservation` | `deploy.resources.reservations.memory` | ⭐⭐⭐ |

**记住：资源限制不是束缚，而是让你多服务共存的保险丝。** 花 10 分钟配置好限制，可以避免 10 小时排查"为什么我的 VPS 挂了"的问题。

---

*这篇文章对你有帮助吗？欢迎在 [selfvps.net](https://selfvps.net) 查看更多 VPS 运维和自托管指南。*
