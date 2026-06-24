---
title: "Docker Container Resource Limits: A Complete Guide to Preventing Single-Service VPS Crashes"
description: "Learn how to use Docker's CPU, memory, I/O, and process isolation features to prevent a single container from consuming all VPS resources and taking down your services"
date: 2026-06-24T10:00:00+08:00
lastmod: 2026-06-24T10:00:00+08:00
slug: "docker-container-resource-limits"
image: /images/posts/docker-container-resource-limits/featured.png
tags: ["Docker", "Resource Limits", "Container Isolation", "VPS", "DevOps", "Performance", "Cgroups", "Compose"]
categories: ["Container Operations"]
aliases: [/en/post/docker-container-resource-limits/]
---

## Introduction

You bought a $5/month VPS with 1 vCPU and 1GB RAM, running Nginx, PostgreSQL, a Python application, and Redis. Everything works fine until one day your Python app hits a memory leak on a particular request — the entire VPS gets consumed instantly. SSH becomes unreachable, your site returns 502 errors, and all services crash.

**Containers without resource limits are like cars without brakes.** Today we'll cover how to set proper resource ceilings for each container in Docker, keeping your VPS stable even when running multiple services.

---

## Why Do You Need Container Resource Limits?

By default, Docker containers can use all host resources without restriction. This means:

- A runaway container can consume all CPU, preventing other containers from being scheduled
- A memory-leaking container can eat all RAM, triggering the OOM Killer to kill critical processes
- Disk I/O monopolized by one container can make database queries excruciatingly slow
- Network bandwidth eaten by a video transcoding container can make your site unusable

**Core principle: Every container should have its own resource ceiling.**

---

## 1. Memory Limits

### 1.1 Command Line

```bash
docker run -d \
  --memory="512m" \
  --memory-swap="1g" \
  --memory-reservation="256m" \
  --name myapp \
  myapp:latest
```

| Parameter | Meaning | Description |
|-----------|---------|-------------|
| `--memory` | Hard limit | Maximum physical memory; container is OOM-Killed beyond this |
| `--memory-swap` | Swap total limit | Combined memory + swap; twice the memory value is reasonable |
| `--memory-reservation` | Soft limit | When system is under pressure, containers below this are evicted first |

### 1.2 Docker Compose

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

### 1.3 Memory Limit Best Practices

```
Total Available Memory: 1GB
├── PostgreSQL:  512MB (50%)  ← Databases need the most memory
├── Application: 256MB  (25%)
├── Redis:       128MB  (13%)
├── Nginx:       64MB   (6%)
└── System:      64MB   (6%) ← Kernel + OS reserved
```

> **Rule of thumb**: Give databases the largest share, web servers the smallest, applications in between. Never allocate more than 80% of physical memory to containers — you need space left for the operating system itself.

---

## 2. CPU Limits

### 2.1 Understanding CPU Limit Units

Docker uses **CPU shares** and **CPU periods** to control CPU usage:

```bash
# Limit container to 0.5 CPU cores (50% of one core)
docker run -d --cpus="0.5" --name halfcpu myapp

# Limit container to 1.5 CPU cores
docker run -d --cpus="1.5" --name onecpu_half myapp

# Precise control with cfs_quota_us and cfs_period_us
# cfs_quota_us=25000, cfs_period_us=100000 → 25ms per 100ms
docker run -d \
  --cpu-quota=25000 \
  --cpu-period=100000 \
  --name precise myapp
```

### 2.2 CPU Limits in Compose

```yaml
services:
  app:
    deploy:
      resources:
        limits:
          cpus: "0.75"    # Max 75% of one core
        reservations:
          cpus: "0.25"    # Guaranteed minimum 25%
```

### 2.3 CPU Limit Best Practices

| Service Type | Recommended CPU | Reason |
|-------------|----------------|--------|
| Nginx/Caddy | 0.25-0.5 | Lightweight, mainly proxying |
| PostgreSQL | 0.5-1.0 | Queries need compute power |
| Python/Node.js App | 0.5-1.0 | Depends on concurrency |
| Redis | 0.1-0.25 | Pure memory ops, low CPU need |
| Video Transcoding | 1.0-2.0 | Compute-intensive, should be isolated |
| Batch Jobs | 0.1-0.5 | Shouldn't impact online services |

---

## 3. I/O Limits (Block I/O)

Disk I/O is the most overlooked resource contention scenario. A container doing heavy log writes can make database IOPS plummet.

```bash
# Limit write bandwidth to 10MB/s
docker run -d \
  --device-write-bps /dev/sda:10mb \
  --name slowwriter myapp

# Limit read bandwidth to 20MB/s
docker run -d \
  --device-read-bps /dev/sda:20mb \
  --name limitedreader myapp

# Limit IOPS (IO operations per second)
docker run -d \
  --device-write-iops /dev/sda:100 \
  --name iopslimited myapp
```

### I/O Limits in Compose

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

> **Note**: `blkio_config` only works in Docker Swarm mode. For standalone Compose, use `docker update` or command-line flags.

---

## 4. Process Limits (PIDs Limit)

A container stuck in a loop might spawn processes endlessly, eventually exhausting the system PID table.

```bash
# Limit container to max 100 processes
docker run -d --pids-limit=100 --name pidlimited myapp

# No limit (default)
docker run -d --pids-limit=-1 --name unlimited myapp
```

### PID Limits in Compose

```yaml
version: "3.8"
services:
  app:
    pids_limit: 200
```

---

## 5. Network Bandwidth Limits

Docker doesn't provide native network bandwidth limiting, but you can achieve it with Linux `tc` (traffic control):

```bash
# Limit container network bandwidth to 10Mbps
docker run -d --name limitednet myapp

# Get container PID
CONTAINER_PID=$(docker inspect -f '{{.State.Pid}}' limitednet)

# Add tc rule to limit outbound bandwidth
tc qdisc add dev eth0 root handle 1: htb default 10
tc class add dev eth0 parent 1: classid 1:10 htb rate 10mbit
tc filter add dev eth0 protocol ip parent 1: prio 1 u32 \
  match ip dst 0.0.0.0/0 flowid 1:10
```

For most VPS scenarios, CPU and memory limits are sufficient. Network bandwidth limiting is only needed in special cases.

---

## 6. Real-World Example: Complete VPS Resource Configuration

Assuming you have a **2 vCPU, 2GB RAM** VPS running these services:

```yaml
# docker-compose.yml
version: "3.8"
services:
  # Frontend Web Server
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

  # Backend API Service
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

  # Database
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

  # Cache
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

### Resource Allocation Overview

```
┌──────────────────────────────────────────────────────┐
│           2 vCPU / 2GB RAM VPS                       │
├──────────┬───────────┬───────────┬───────────────────┤
│ Service  │ CPU (Limit) │ Memory (Limit) │ Priority       │
├──────────┼───────────┼───────────┼───────────────────┤
│ Nginx    │ 0.25 core │ 128MB     │ High - Edge layer  │
│ API      │ 1.0 core  │ 768MB     │ Critical - Core    │
│ Postgres │ 0.75 core │ 512MB     │ Critical - Data    │
│ Redis    │ 0.25 core │ 128MB     │ High - Cache layer │
│ Reserved │ -         │ 512MB     │ N/A - OS           │
└──────────┴───────────┴───────────┴───────────────────┘
```

---

## 7. Monitoring and Tuning

After setting resource limits, you need to continuously monitor actual usage to tune them:

### 7.1 Using docker stats

```bash
# Real-time monitoring of all containers
docker stats --no-stream

# View specific container
docker stats myapp

# Export to file for analysis
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" > usage.txt
```

### 7.2 Using cAdvisor + Prometheus

```yaml
# cadvisor service (lightweight monitoring)
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

### 7.3 Identifying Resource Issues

```bash
# Check for OOM-Killed containers
journalctl -k | grep -i "oom\|out of memory"

# Check for CPU throttling
docker stats --format "{{.Name}}\t{{.CPUPerc}}\t{{.MemPerc}}"

# Check for containers restarting frequently (possibly OOM)
docker ps -a --filter "exited=137"  # 137 = SIGKILL (usually OOM)
```

> **Exit code 137** means the container was terminated by SIGKILL, most commonly due to hitting its memory limit. If you see this, you need to increase the memory cap for that container.

---

## 8. Common Mistakes

### ❌ Mistake 1: No limits, "my VPS is big enough anyway"

Even with a 16GB RAM VPS, multiple containers going rogue simultaneously can exhaust all resources. **Limits aren't restrictions — they're guarantees.**

### ❌ Mistake 2: Limits set too tight

If you give an app only 64MB of memory but it needs 100MB to start, the container will OOM-restart repeatedly, creating a vicious cycle. Observe actual usage for 24 hours before setting limits.

### ❌ Mistake 3: Only limiting memory, ignoring CPU

Unrestricted CPU usage causes:
- Other containers can't get enough CPU time slices
- Overall system responsiveness degrades
- SSH management becomes difficult

### ❌ Mistake 4: Ignoring system reservation

The sum of container limits cannot exceed physical resources. Always reserve at least 10-20% for the OS, Docker daemon, and system components.

---

## 9. Advanced: Fine-Grained Control with cgroup v2

Modern Linux distributions (Ubuntu 22.04+, Debian 12+) use cgroup v2 by default:

```bash
# Check cgroup version
stat -fc %T /sys/fs/cgroup/
# Returns cgroup2fs if using v2

# cgroup v2 unified resource control
cat /sys/fs/cgroup/docker.slice/memory.current
cat /sys/fs/cgroup/docker.slice/cpu.max
```

Key improvements in cgroup v2 over v1:
- Unified hierarchy, no separate memory controller
- More intuitive `cpu.max` format: `quota period` (e.g., `25000 100000` = 25%)
- Better fair scheduling algorithm

---

## Summary

| Limit Type | CLI Flag | Compose Key | Importance |
|-----------|----------|-------------|------------|
| Memory Hard Limit | `--memory` | `deploy.resources.limits.memory` | ⭐⭐⭐⭐⭐ |
| CPU Limit | `--cpus` | `deploy.resources.limits.cpus` | ⭐⭐⭐⭐⭐ |
| Swap Limit | `--memory-swap` | `deploy.resources.limits.memory_swap` | ⭐⭐⭐⭐ |
| PID Limit | `--pids-limit` | `pids_limit` | ⭐⭐⭐⭐ |
| I/O Bandwidth | `--device-write-bps` | `blkio_config` | ⭐⭐⭐ |
| Memory Soft Limit | `--memory-reservation` | `deploy.resources.reservations.memory` | ⭐⭐⭐ |

**Remember: Resource limits aren't constraints — they're the fuses that let multiple services coexist.** Spend 10 minutes configuring limits, and you'll save 10 hours debugging "why did my VPS go down."

---

*Found this helpful? Visit [selfvps.net](https://selfvps.net) for more VPS operations and self-hosting guides.*
