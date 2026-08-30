---
title: "VPS Process Management & System Diagnosis: From Beginner to Master"
description: "Master essential Linux commands for process monitoring, CPU/memory/disk I/O analysis, and log troubleshooting — a comprehensive guide from ps to journalctl"
date: 2026-08-30T10:00:00+08:00
slug: "vps-process-management-system-diagnosis"
image: /images/posts/vps-process-management-system-diagnosis/featured.png
tags: ["VPS", "Linux", "Process Management", "System Diagnosis", "DevOps", "Performance Monitoring", "journalctl"]
categories: ["System Operations"]
aliases: [/en/post/vps-process-management-system-diagnosis/]
---

## Introduction

> **Diagnosis is the first principle of operations.**

When your VPS slows down, CPU spikes, memory runs low, or disk I/O becomes abnormal, the first step isn't to panic and restart — it's to **systematically pinpoint the issue**. This guide takes you from zero to mastery in Linux process management and system diagnosis, not by listing commands, but by teaching you a reusable troubleshooting mindset.

All commands apply to Ubuntu 24.04 / Debian 12 / AlmaLinux 9, covering five dimensions: CPU, memory, disk I/O, network, and logs.

---

## 1. Process Inspection: Advanced ps and pstree

### 1.1 Essential ps Commands

```bash
# View all processes with full info (most used)
ps aux

# Sort by memory usage (find memory hogs)
ps aux --sort=-%mem | head -20

# Sort by CPU usage
ps aux --sort=-%cpu | head -20

# Show only processes for a specific user
ps -u www-data

# Display process tree with parent-child relationships
ps auxf

# Show details for a specific PID
ps -p 1234 -o pid,ppid,cmd,%cpu,%mem,etime
```

### 1.2 Key Output Fields

| Field | Meaning | Troubleshooting Tip |
|-------|---------|---------------------|
| `%CPU` | CPU usage percentage |持续关注 >90% |
| `%MEM` | Physical memory usage % | Watch for memory leaks |
| `VSZ` | Virtual memory size (KB) | Abnormally large may indicate issues |
| `RSS` | Actual physical memory (KB) | More realistic than VSZ |
| `STAT` | Process state (see below) | D=uninterruptible sleep, Z=zombie |
| `etime` | Elapsed time | Check for abnormally long-running processes |

### 1.3 STAT State Reference

```
R  → Running
S  → Interruptible sleep (waiting for event)
D  → Uninterruptible sleep (usually waiting for disk I/O) ⚠️
Z  → Zombie (dead but parent hasn't reaped) ⚠️
T  → Stopped
X  → Dead
```

Many `D` state processes indicate a severe disk I/O bottleneck. `Z` zombies need the parent process cleaned up.

### 1.4 pstree: Visualizing Process Lineage

```bash
# Show complete process tree
pstree -p

# Show descendants of a specific process
pstree -p 1234

# Show process tree with commands
pstree -apul
```

---

## 2. Real-Time Monitoring: top and htop

### 2.1 top Command Deep Dive

```bash
# Start top (refreshes every 3 seconds by default)
top

# Set refresh interval (seconds)
top -d 1

# Show only a specific user's processes
top -u www-data

# Sort by memory (press M inside top)
top

# Sort by CPU (press P inside top)
top

# Non-interactive single snapshot
top -b -n 1
```

**Key top regions:**
- Line 1: Uptime, login count, load averages (1/5/15 min)
- Line 2: Total processes, running/sleeping/zombie counts
- Line 3: CPU usage (us=user, sy=sys, id=idle, wa=IO wait)
- Line 4: Memory usage (total/free/buff/cache)
- Line 5: Swap partition

**Load Average Interpretation:**
- Load < CPU cores: healthy
- Load ≈ CPU cores: moderate
- Load > CPU cores × 2: severely overloaded, investigate immediately

### 2.2 htop: A Modern Alternative

```bash
# Install (Debian/Ubuntu)
sudo apt install htop

# Launch htop
htop

# F2: Settings / F3: Search / F9: Send signal / F10: Exit
```

htop advantages over top:
- Color-coded display for instant visual scanning
- Mouse support
- Direct process killing (F9)
- Intuitive disk and network IO bar graphs
- Thread-level visibility

---

## 3. Disk I/O Analysis: iotop and iostat

### 3.1 iotop: Find IO Heavyweights

```bash
# Install
sudo apt install iotop

# Real-time monitoring (requires root)
sudo iotop

# Show only processes with IO activity
sudo iotop -o

# Single snapshot
sudo iotop -b -n 1
```

**Key fields:**
- `DISK READ/WRITE`: Current read/write speed
- `IO %`: IO utilization percentage
- `SWAPIN` / `OUTIN`: Swap IO ratio

### 3.2 iostat: Device-Level IO Statistics

```bash
# Install
sudo apt install sysstat

# Refresh every second, 5 samples
iostat -xz 1 5

# Disks only (no CPU)
iostat -dx 1 5

# Historical IO data (if enabled)
sar -d -p
```

**Key metrics:**
- `await`: Average IO request wait time (ms), >20ms needs attention
- `%util`: Device utilization, near 100% means disk is the bottleneck
- `r_await/w_await`: Read/write response times
- `rkB/s wkB/s`: Read/write throughput

---

## 4. Deep Memory Analysis

### 4.1 free Command

```bash
# Human-readable output
free -h

# In megabytes
free -m
```

**Output interpretation:**
```
              total        used        free      shared  buff/cache   available
Mem:           7.6G        2.1G        3.2G        256M        2.3G        5.0G
Swap:          2.0G        0.0B        2.0G
```

**Key point:** `available` is more useful than `free` — it represents memory truly available to applications (including reclaimable buff/cache).

### 4.2 Deeper Insights: smem and /proc/meminfo

```bash
# Install smem (more accurate memory stats)
sudo apt install smem

# Sort by RSS (actual physical memory)
smem -t -k

# Sort by PSS (fair share after considering shared libraries)
smem -t -k -p

# Kernel memory details
cat /proc/meminfo | head -30

# Key memory values
cat /proc/meminfo | grep -E "MemTotal|MemFree|MemAvailable|Buffers|Cached|SwapTotal|SwapFree"
```

### 4.3 Detecting Memory Leaks

```bash
# Track a process's memory over time
watch -n 1 'ps aux --sort=-%mem | head -10'

# View a process's detailed memory mappings
cat /proc/<PID>/smaps | head -50

# Safely drop page caches (won't affect running apps)
sudo sync; echo 1 > /proc/sys/vm/drop_caches
```

---

## 5. CPU Performance Analysis

### 5.1 mpstat: Multi-Core CPU Monitoring

```bash
# Install
sudo apt install sysstat

# Per-core usage, refreshing every second
mpstat -P ALL 1 5

# Overall summary
mpstat 1 3
```

**Interpretation:** If one core shows high `usr` while others are idle, it's a single-thread bottleneck. If all cores are saturated, consider horizontal scaling.

### 5.2 vmstat: Virtual Memory Statistics

```bash
# System-wide overview, refreshing every second
vmstat 1 10

# Summary only (no refresh)
vmstat -s
```

**Key fields:**
- `si/so`: Swap in/out — continuously non-zero means insufficient RAM
- `bi bo`: Block device read/write — persistently high means IO pressure
- `us sy id wa st`: CPU state breakdown

### 5.3 pidstat: Per-Process CPU Statistics

```bash
# Install
sudo apt install sysstat

# Per-process CPU every second
pidstat -u 1 5

# Specific PID only
pidstat -u 1 5 -p 1234

# Context switches (high rate impacts performance)
pidstat -r 1 5
```

---

## 6. Network Diagnostics

### 6.1 Connections and Ports

```bash
# View all network connections (with PID)
ss -tulnap

# TCP connections only
ss -tna

# Listening ports
ss -tlnp

# netstat alternative (deprecated, use ss)
netstat -tulnap  # still works but not recommended
```

**Connection State Reference:**
- `ESTAB`: Normal connection
- `TIME_WAIT`: Connection waiting to close (too many affect new connections)
- `CLOSE_WAIT`: Remote closed but local hasn't ⚠️
- `SYN_RECV`: Many may indicate SYN Flood attack ⚠️
- `LISTEN`: Normal listening state

### 6.2 Network Traffic Monitoring

```bash
# Real-time network traffic
iftop

# Install
sudo apt install iftop

# Per-connection traffic distribution
nload eth0

# Bandwidth statistics
sudo apt install bandwhich
bandwhich
```

### 6.3 Link Quality Testing

```bash
# Trace route to destination
traceroute example.com

# Fast traceroute (no root needed)
mtr example.com

# Test DNS resolution
dig example.com +trace

# Measure DNS resolution speed
time dig example.com
```

---

## 7. Log Analysis: Complete journalctl Guide

### 7.1 Basic Queries

```bash
# All logs since boot
journalctl

# Only this boot
journalctl -b

# Previous boot
journalctl -b -1

# Follow logs in real-time (like tail -f)
journalctl -f

# Last 100 lines
journalctl -n 100

# Pipe to pager
journalctl | less
```

### 7.2 Service Filtering

```bash
# nginx-related logs
journalctl -u nginx

# Multiple services
journalctl -u nginx -u postgresql

# Recent logs for a service
journalctl -u nginx --since "10 minutes ago"

# Errors and warnings only
journalctl -u nginx -p err..alert
```

### 7.3 Advanced Filtering

```bash
# Time range
journalctl --since "2026-08-29 10:00:00" --until "2026-08-29 12:00:00"

# By priority (0=emergency 7=debug)
journalctl -p err
journalctl -p crit
journalctl -p warning

# Kernel messages only
journalctl -k

# Specific PID
journalctl _PID=1234

# Specific program
journalctl _COMM=nginx

# Combined filters
journalctl -u nginx -p err --since "1 hour ago"
```

### 7.4 Log Rotation and Persistence

```bash
# Check log disk usage
journalctl --disk-usage

# Set max retention (default 4 months)
sudo journalctl --vacuum-time=7d

# Limit log size (max 100MB)
sudo journalctl --vacuum-size=100M

# Logs persist to disk by default
# Location: /var/log/journal/
```

---

## 8. Comprehensive Troubleshooting Workflow

When your VPS has issues, follow this sequence:

```
┌─────────────────────────────────────────────────────┐
│  1. Quick overview: uptime / top (confirm load level) │
│  2. CPU analysis: top -c or mpstat (find CPU bottlenecks) │
│  3. Memory analysis: free -h + smem (check RAM sufficiency) │
│  4. Disk IO: iotop -o + iostat -xz (find IO heavyweights) │
│  5. Network check: ss -tna + mtr (connections & link quality) │
│  6. Log review: journalctl -u <service> -p err │
│  7. Kernel info: dmesg | tail (hardware/driver errors) │
└─────────────────────────────────────────────────────┘
```

### Practice Example: CPU Spike Troubleshooting

```bash
# Step 1: Confirm load
uptime

# Step 2: Find high-CPU processes
top -bn1 | head -20

# Step 3: Deep dive into the process
pidstat -u 1 3 -p <PID>

# Step 4: Process details
ps -p <PID> -o pid,ppid,cmd,%cpu,%mem,stat,etime

# Step 5: Files opened by the process
lsof -p <PID> | head -20

# Step 6: Check related service logs
journalctl -u nginx -p err --since "30 minutes ago"
```

### Practice Example: Out of Memory Troubleshooting

```bash
# Step 1: Check memory status
free -h
vmstat -s

# Step 2: Find memory hogs
ps aux --sort=-%mem | head -15
smem -t -k

# Step 3: Check swap usage
cat /proc/swaps
swapon --show

# Step 4: Check for OOM Killer events
journalctl -k | grep -i "oom\|out of memory"

# Step 5: Temporary relief if needed
sudo systemctl restart <heavy-service>
```

---

## 9. Performance Baseline: Building Your VPS Health Profile

Troubleshooting requires knowing what "normal" looks like. Record a baseline daily:

```bash
#!/bin/bash
echo "=== System Baseline $(date) ==="
echo "--- Uptime ---"
uptime
echo "--- Memory ---"
free -h
echo "--- CPU Load ---"
cat /proc/loadavg
echo "--- IO Wait ---"
vmstat 1 3 | tail -1
echo "--- Top Memory Processes ---"
ps aux --sort=-%mem | head -6
echo "--- Top CPU Processes ---"
ps aux --sort=-%cpu | head -6
echo "--- Disk Usage ---"
df -h
echo "--- Network Connections ---"
ss -s
```

Save as `~/scripts/baseline.sh`, run via cron daily, and compare against baselines when anomalies occur.

---

## Summary

VPS troubleshooting isn't about guessing — it's about **letting data speak**. With this toolchain, you can pinpoint most performance issues within 5 minutes:

| Symptom | Priority Tool |
|---------|--------------|
| System slowdown | `top` → `vmstat` → `mpstat` |
| Disk full | `df -h` → `du -sh /*` |
| Insufficient memory | `free -h` → `smem` → `dmesg \| grep oom` |
| IO bottleneck | `iotop -o` → `iostat -xz` |
| Network issues | `ss -tna` → `mtr` |
| Service failure | `journalctl -u <service>` → `dmesg` |

**Consistent practice is the only shortcut.** Spend 5 minutes daily running `top` and `free -h` to build intuition for your server's normal state. When anomalies hit, that intuition will help you locate problems faster.
