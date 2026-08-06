---
title: "VPS Kernel Parameter Tuning: sysctl TCP Network Optimization Guide"
description: "Boost VPS network throughput, reduce latency, and improve high-concurrency performance by tuning Linux kernel parameters (sysctl). Covers TCP optimization, memory management, file descriptors, and a one-click script."
date: 2026-08-06T10:00:00+08:00
slug: "vps-linux-kernel-tuning-sysctl"
image: /images/posts/vps-linux-kernel-tuning-sysctl/featured-en.png
tags: ["VPS", "Kernel Tuning", "sysctl", "TCP Optimization", "Network Performance", "Performance Tuning", "Linux"]
categories: ["Performance Tuning"]
aliases: [/en/post/vps-linux-kernel-tuning-sysctl/]
draft: false
---

## Introduction

> **Default kernel parameters are designed for general-purpose scenarios, not for your heavily loaded VPS.**

Your VPS runs Nginx, MySQL, Redis, or acts as a reverse proxy, CDN node, or API gateway—the default kernel network stack parameters are often too conservative for these scenarios. By tuning `sysctl` parameters, without upgrading hardware, you can boost network throughput by 30%~200% and raise connection limits from thousands to tens of thousands.

This guide provides a **production-verified sysctl optimization方案** covering TCP network stack, memory management, file descriptors, and connection tracking, with a one-click application script. All parameters are suitable for Ubuntu 24.04 / Debian 12 / AlmaLinux 9.

---

## 1. Why Kernel Tuning is Needed

### 1.1 Conservative Default Parameters

Linux kernel default `sysctl` parameters are maintained by `kernel.org`, targeting **general-purpose desktop and server scenarios**, prioritizing compatibility and stability over peak performance. Key limitations include:

| Parameter | Default | Problem |
|-----------|---------|---------|
| `net.core.somaxconn` | 4096 | Insufficient for high-concurrency connection queues |
| `net.ipv4.tcp_max_syn_backlog` | 128~1024 | SYN queue too small, high packet loss rate |
| `net.ipv4.ip_local_port_range` | 32768~60999 | Insufficient available ports |
| `net.core.netdev_max_backlog` | 1000 | NIC packet processing can't keep up |
| `fs.file-max` | ~65536~1048576 | File descriptor limits |

### 1.2 Common Performance Bottleneck Scenarios

- **High-concurrency web services**: Nginx reverse proxy handling tens of thousands of concurrent connections
- **API gateways**: Massive short-lived connections causing TIME_WAIT accumulation and port exhaustion
- **Database proxies**: Connection pools exhausted, new connections rejected
- **CDN/proxy nodes**: Network throughput limited, CPU idle but traffic can't increase

---

## 2. Core Network Parameter Tuning

### 2.1 TCP Connection Processing Optimization

```bash
# Maximum listen queue length (required by Nginx/Apache)
net.core.somaxconn = 65535

# TCP SYN queue maximum length
net.ipv4.tcp_max_syn_backlog = 65536

# Speed up SYN-ACK timeout, release half-open connections
net.ipv4.tcp_synack_retries = 2
net.ipv4.tcp_syn_retries = 5

# Allow quick回收 of TIME_WAIT sockets
net.ipv4.tcp_tw_reuse = 1

# Disable strict source routing (security hardening)
net.ipv4.ip_strict_host_multicast = 0
net.ipv4.conf.all.secure_redirects = 0
```

**Parameter explanations:**

- `somaxconn`: Controls the maximum value of the backlog parameter for `listen()` system call. Default 4096 is severely insufficient for high-concurrency services.
- `tcp_max_syn_backlog`: SYN queue length, easily overwhelmed during attacks or high load.
- `tcp_tw_reuse`: Allows reusing connections in TIME_WAIT state, significantly beneficial for short-lived connection services (e.g., API gateways).

### 2.2 Port Range Optimization

```bash
# Extend ephemeral port range (default 32768-60999, only 28232 ports)
net.ipv4.ip_local_port_range = 1024 65535

# Allow binding to non-local addresses (use with caution)
net.ipv4.ip_nonlocal_bind = 1
```

**Why extend the port range?**

When your VPS acts as a reverse proxy, each client connection establishes multiple backend connections, and backend connections use ephemeral ports. If ephemeral ports are insufficient, new connections are rejected with a `Cannot assign requested address` error.

After extending the port range, available ports increase from 28K to 64K, which is more than sufficient for single-machine tens of thousands of concurrent connections.

### 2.3 Packet Processing Optimization

```bash
# NIC receive queue length
net.core.netdev_max_backlog = 65536

# TCP receive window scaling (improves performance for high BDP products)
net.ipv4.tcp_window_scaling = 1

# TCP receive buffer maximum
net.ipv4.tcp_rmem = 4096 87380 16777216

# TCP send buffer maximum
net.ipv4.tcp_wmem = 4096 65536 16777216

# Receive buffer auto-tuning
net.core.rmem_auto_max = 16777216
net.core.wmem_auto_max = 16777216
```

**Key parameter interpretation:**

- `netdev_max_backlog`: Maximum number of packets queued by the NIC driver but not yet processed by the kernel. Default 1000 is too low.
- `tcp_window_scaling`: Enables TCP window scaling option, supporting > 64KB transmission windows.
- `tcp_rmem/tcp_wmem`: Receive/send buffer min/default/max values. Auto-tuning can significantly boost throughput.

### 2.4 Connection Tracking Optimization (NAT/Firewall Scenarios)

```bash
# Maximum entries in connection tracking table
net.netfilter.nf_conntrack_max = 1048576

# Connection tracking hash table size (must be power of 2)
net.netfilter.nf_conntrack_buckets = 65536

# Disable ICMP redirects (security hardening)
net.ipv4.conf.all.accept_redirects = 0
net.ipv4.conf.default.accept_redirects = 0
net.ipv4.conf.all.send_redirects = 0

# Disable source routing
net.ipv4.conf.all.accept_source_route = 0
net.ipv4.conf.default.accept_source_route = 0
```

**Connection tracking issues:**

VPS running `iptables` or `nftables` needs to record one entry per connection in the conntrack table. Default `nf_conntrack_max` is usually 65536 or lower, easily exhausted in high-concurrency scenarios, causing new connections to be dropped.

---

## 3. Memory and File Descriptor Tuning

### 3.1 Memory Management Optimization

```bash
# Virtual memory flush frequency (seconds)
vm.vfs_cache_pressure = 50

# Allow over-commit count
vm.overcommit_memory = 1
vm.overcommit_ratio = 90

# Reduce swapping (lower disk I/O)
vm.swappiness = 10
vm.dirty_ratio = 10
vm.dirty_background_ratio = 5
```

**Parameter explanation:**

- `vfs_cache_pressure`: Controls kernel's tendency to reclaim inode/dentry cache. Default 100 is too high; lowering reduces filesystem metadata operations.
- `overcommit_memory=1`: Allows memory over-commit, critical for databases and Java applications.
- `swappiness=10`: Reduces swapping tendency, keeping more data in memory.

### 3.2 File Descriptor Limits

```bash
# System-level file descriptor maximum
fs.file-max = 2097152

# Per-user file descriptor limits (set in /etc/security/limits.conf)
# * soft nofile 65535
# * hard nofile 65535
# root soft nofile 65535
# root hard nofile 65535
```

---

## 4. Security Hardening Parameters

While tuning the kernel, security hardening should also be applied:

```bash
# Disable ICMP redirect receiving
net.ipv4.conf.all.accept_redirects = 0
net.ipv4.conf.default.accept_redirects = 0

# Disable ICMP redirect sending
net.ipv4.conf.all.send_redirects = 0

# Disable source routing
net.ipv4.conf.all.accept_source_route = 0
net.ipv4.conf.default.accept_source_route = 0

# Enable SYN cookies (defense against SYN Flood attacks)
net.ipv4.tcp_syncookies = 1

# Log suspicious packets
net.ipv4.conf.all.log_martians = 1
net.ipv4.conf.default.log_martians = 1

# Disable IPv6 (if not needed)
net.ipv6.conf.all.disable_ipv6 = 1
net.ipv6.conf.default.disable_ipv6 = 1
```

---

## 5. One-Click Application Script

### 5.1 Optimization Script

```bash
#!/bin/bash
# vps-kernel-tuning.sh - VPS Kernel Parameter Optimization Script
# Suitable for: Ubuntu 24.04 / Debian 12 / AlmaLinux 9

set -euo pipefail

echo "=== VPS Kernel Parameter Tuning ==="
echo "Current kernel version: $(uname -r)"
echo "Start time: $(date)"

# Backup current configuration
BACKUP_FILE="/etc/sysctl.d/99-vps-tuning-backup-$(date +%Y%m%d-%H%M%S).conf"
if [ -f /etc/sysctl.d/99-vps-tuning.conf ]; then
    cp /etc/sysctl.d/99-vps-tuning.conf "$BACKUP_FILE"
    echo "Current configuration backed up to: $BACKUP_FILE"
fi

# Write optimized parameters
cat > /etc/sysctl.d/99-vps-tuning.conf << 'EOF'
# ===========================================
# VPS Kernel Network Performance Optimization
# Suitable: Ubuntu 24.04 / Debian 12 / AlmaLinux 9
# ===========================================

# --- TCP Connection Optimization ---
net.core.somaxconn = 65535
net.ipv4.tcp_max_syn_backlog = 65536
net.ipv4.tcp_synack_retries = 2
net.ipv4.tcp_syn_retries = 5
net.ipv4.tcp_tw_reuse = 1
net.ipv4.tcp_fin_timeout = 15

# --- Port Range Optimization ---
net.ipv4.ip_local_port_range = 1024 65535
net.ipv4.ip_nonlocal_bind = 1

# --- Packet Processing Optimization ---
net.core.netdev_max_backlog = 65536
net.ipv4.tcp_window_scaling = 1
net.ipv4.tcp_rmem = 4096 87380 16777216
net.ipv4.tcp_wmem = 4096 65536 16777216
net.core.rmem_auto_max = 16777216
net.core.wmem_auto_max = 16777216
net.core.rmem_default = 262144
net.core.wmem_default = 262144

# --- Connection Tracking Optimization ---
net.netfilter.nf_conntrack_max = 1048576
net.netfilter.nf_conntrack_buckets = 65536

# --- Memory Management Optimization ---
vm.vfs_cache_pressure = 50
vm.overcommit_memory = 1
vm.overcommit_ratio = 90
vm.swappiness = 10
vm.dirty_ratio = 10
vm.dirty_background_ratio = 5

# --- Security Hardening ---
net.ipv4.conf.all.accept_redirects = 0
net.ipv4.conf.default.accept_redirects = 0
net.ipv4.conf.all.send_redirects = 0
net.ipv4.conf.all.accept_source_route = 0
net.ipv4.conf.default.accept_source_route = 0
net.ipv4.tcp_syncookies = 1
net.ipv4.conf.all.log_martians = 1
net.ipv4.conf.default.log_martians = 1
net.ipv4.icmp_echo_ignore_broadcasts = 1
net.ipv4.icmp_ignore_bogus_error_responses = 1

# --- Disable IPv6 (if not needed) ---
# net.ipv6.conf.all.disable_ipv6 = 1
# net.ipv6.conf.default.disable_ipv6 = 1
EOF

echo "Parameters written to /etc/sysctl.d/99-vps-tuning.conf"

# Apply configuration
sysctl -p /etc/sysctl.d/99-vps-tuning.conf
echo "Kernel parameters applied"

# Set file descriptor limits
cat > /etc/security/limits.d/99-vps-tuning.conf << 'EOF'
* soft nofile 65535
* hard nofile 65535
root soft nofile 65535
root hard nofile 65535
EOF

echo "File descriptor limits set"

# Verify key parameters
echo ""
echo "=== Key Parameter Verification ==="
echo "somaxconn: $(sysctl -n net.core.somaxconn)"
echo "tcp_max_syn_backlog: $(sysctl -n net.ipv4.tcp_max_syn_backlog)"
echo "ip_local_port_range: $(sysctl -n net.ipv4.ip_local_port_range)"
echo "nf_conntrack_max: $(sysctl -n net.netfilter.nf_conntrack_max)"
echo "tcp_tw_reuse: $(sysctl -n net.ipv4.tcp_tw_reuse)"
echo "swappiness: $(sysctl -n vm.swappiness)"

echo ""
echo "Completion time: $(date)"
echo "Optimization complete! Please restart services or reload configuration for some parameters to take effect."
```

### 5.2 Application Method

```bash
# Download and execute
wget -O /tmp/vps-kernel-tuning.sh https://raw.githubusercontent.com/.../vps-kernel-tuning.sh
chmod +x /tmp/vps-kernel-tuning.sh
sudo /tmp/vps-kernel-tuning.sh

# Or apply manually line by line
sudo sysctl -w net.core.somaxconn=65535
sudo sysctl -w net.ipv4.tcp_max_syn_backlog=65536
sudo sysctl -w net.ipv4.tcp_tw_reuse=1
```

### 5.3 Verify Optimization Results

```bash
# View all current network-related parameters
sysctl -a | grep -E 'net\.(ipv4|core)' | sort

# Check connection tracking table usage
cat /proc/sys/net/netfilter/nf_conntrack_count
cat /proc/sys/net/netfilter/nf_conntrack_max

# View TIME_WAIT connection count
netstat -an | grep TIME_WAIT | wc -l

# View current listen backlog
ss -ltn | head -10
```

---

## 6. Typical Scenario Tuning Recommendations

### 6.1 Nginx Reverse Proxy Scenario

```bash
# Key parameters
net.core.somaxconn = 65535
net.ipv4.tcp_max_syn_backlog = 65536
net.ipv4.tcp_tw_reuse = 1
net.ipv4.ip_local_port_range = 1024 65535

# Nginx configuration pairing
# worker_connections 10240;
# keepalive_timeout 65;
# keepalive_requests 10000;
```

### 6.2 API Gateway / High-Concurrency Short-Connection Scenario

```bash
# Key parameters
net.ipv4.tcp_tw_reuse = 1
net.ipv4.tcp_fin_timeout = 15
net.ipv4.ip_local_port_range = 1024 65535
net.core.netdev_max_backlog = 65536
```

### 6.3 Database Proxy / Connection Pool Scenario

```bash
# Key parameters
net.core.somaxconn = 65535
net.ipv4.tcp_max_syn_backlog = 65536
net.ipv4.tcp_tw_reuse = 1
net.ipv4.tcp_rmem = 4096 87380 16777216
net.ipv4.tcp_wmem = 4096 65536 16777216
vm.overcommit_memory = 1
```

### 6.4 CDN / High-Throughput Scenario

```bash
# Key parameters
net.core.rmem_default = 16777216
net.core.wmem_default = 16777216
net.core.rmem_max = 16777216
net.core.wmem_max = 16777216
net.ipv4.tcp_rmem = 4096 87380 16777216
net.ipv4.tcp_wmem = 4096 65536 16777216
net.ipv4.tcp_congestion_control = bbr
```

**BBR Congestion Control:** Google's congestion control algorithm, excellent performance in high bandwidth-delay product (BDP) scenarios. Recommended for all high-throughput VPS.

```bash
# Enable BBR
echo "net.ipv4.tcp_congestion_control = bbr" | sudo tee -a /etc/sysctl.d/99-vps-tuning.conf
sudo sysctl -p /etc/sysctl.d/99-vps-tuning.conf

# Verify
sysctl net.ipv4.tcp_congestion_control
# Output: net.ipv4.tcp_congestion_control = bbr
```

---

## 7. Precautions and Rollback

### 7.1 Precautions

1. **Backup original configuration**: Before modifying, backup `/etc/sysctl.conf` and files under `/etc/sysctl.d/`
2. **Gradual adjustment**: Don't modify all parameters at once; adjust gradually and observe effects
3. **Kernel version compatibility**: Some parameters may not be supported on older kernels (< 4.x)
4. **Cloud provider limitations**: Some cloud providers (e.g., AWS, Alibaba Cloud) may limit certain parameters at the host level
5. **Security first**: Don't blindly enable all parameters in production; prioritize security hardening parameters

### 7.2 Rollback Method

```bash
# Restore defaults
sudo sysctl -r /etc/sysctl.d/99-vps-tuning.conf

# Or manually clear
sudo rm /etc/sysctl.d/99-vps-tuning.conf
sudo sysctl -p  # Restore defaults from /etc/sysctl.conf

# Restore file descriptor limits
sudo rm /etc/security/limits.d/99-vps-tuning.conf
```

### 7.3 Performance Benchmarking

```bash
# Test network throughput with iperf3
# Server
iperf3 -s -p 5001

# Client
iperf3 -c <VPS_IP> -p 5001 -t 10 -P 4

# Test HTTP performance with ab or wrk
wrk -t4 -c100 -d10s http://<VPS_IP>/
```

---

## 8. Summary

By reasonably adjusting `sysctl` kernel parameters, VPS network performance can be significantly improved:

| Optimization Direction | Expected Improvement |
|------------------------|---------------------|
| TCP connection queue | Reduce connection rejections, improve concurrency |
| Port range extension | Prevent port exhaustion, support more connections |
| Buffer tuning | Improve large file transfer and large packet throughput |
| BBR congestion control | Improve high-latency link throughput by 20%~50% |
| Connection tracking optimization | Support higher concurrent connection counts |
| Memory management | Reduce swap, improve overall response speed |

**Core principle: backup first, adjust gradually, verify continuously, rollback anytime.**

---

## References

- [Linux TCP/IP Tuning Guide](https://github.com/akhildevelops/linux-tcp-tuning)
- [sysctl Network Parameters Official Documentation](https://man7.org/linux/man-pages/man5/sysctl.conf.5.html)
- [BBR Congestion Control Algorithm](https://www.kernel.org/doc/html/latest/networking/tcp_bbr.html)
- [Netperf Network Performance Testing](http://www.netperf.org/netperf/)
