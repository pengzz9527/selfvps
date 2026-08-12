---
title: "VPS Remote Desktop Access: XRDP and NoMachine Configuration Guide"
date: 2026-08-12
draft: false
tags: ["VPS", "Remote Desktop", "XRDP", "NoMachine", "GUI", "Operations"]
categories: ["VPS Operations"]
description: "Compare XRDP and NoMachine for VPS remote desktop access, with detailed configuration steps, performance tuning, and security best practices for Linux GUI remote access."
image: "/images/posts/vps-remote-desktop-access-guide/featured.png"
---

## Introduction

Most VPS tutorials assume you only work with the command line. But in real-world operations, you often need a graphical interface — installing GUI software, debugging web applications, viewing visual dashboards, or simply accessing a local service through a browser.

This guide covers two mainstream Linux remote desktop solutions: **XRDP** (open-source, lightweight) and **NoMachine** (high-performance, feature-rich), with complete configuration steps and optimization tips.

---

## Solution Comparison

| Feature | XRDP | NoMachine |
|---------|------|-----------|
| Protocol | RDP (Microsoft Remote Desktop) | NX (proprietary) |
| Installation | Simple | Moderate |
| Performance | Moderate, suitable for basic tasks | Excellent, supports HD video |
| Bandwidth | Moderate | Low, smart compression |
| Audio forwarding | Supported (needs config) | Native support |
| File transfer | Limited | Full support |
| Multi-user | Supported | Supported |
| Free tier | Fully free | Free version sufficient (2 concurrent) |
| Best for | Lightweight remote management | High-performance remote work |

---

## Solution 1: XRDP Configuration

### 1. Install XRDP

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install -y xrdp

# CentOS/Rocky Linux
sudo yum install -y epel-release
sudo yum install -y xrdp
```

### 2. Install a Desktop Environment

XRDP needs a desktop environment to work. If you don't have one:

```bash
# Install lightweight XFCE desktop (recommended, low resource usage)
sudo apt install -y xfce4 xfce4-goodies

# Or install lightweight MATE desktop
sudo apt install -y mate-desktop-environment-core
```

### 3. Configure XRDP Session

```bash
# Set default desktop environment
echo "xfce4-session" > ~/.xsessionrc

# Configure XRDP to use the correct session
sudo tee /etc/xrdp/startwm.sh << 'EOF'
#!/bin/sh
if [ -r /etc/default/locale ]; then
  . /etc/default/locale
  export LANG
  export LANGUAGE
fi
startxfce4
EOF

sudo chmod 755 /etc/xrdp/startwm.sh
```

### 4. Start and Enable Auto-start

```bash
sudo systemctl enable xrdp
sudo systemctl start xrdp
sudo systemctl status xrdp
```

### 5. Configure Firewall

```bash
# Allow RDP port (default 3389)
sudo ufw allow 3389/tcp
# Or with firewalld
sudo firewall-cmd --permanent --add-port=3389/tcp
sudo firewall-cmd --reload
```

### 6. Connect to Remote Desktop

Use any RDP-compatible client:
- **Windows**: Built-in "Remote Desktop Connection"
- **macOS**: Microsoft Remote Desktop (free from App Store)
- **Linux**: Remmina, rdesktop
- **Mobile**: Microsoft Remote Desktop (iOS/Android)

Connection format: `your_vps_ip:3389`

### XRDP Troubleshooting

**Issue 1: Black screen or login loop**

```bash
# Check desktop environment configuration
cat ~/.xsessionrc
cat ~/.Xauthority

# Fix permission issues
sudo chown -R $USER:$USER ~/.Xauthority
sudo chmod 600 ~/.Xauthority
```

**Issue 2: Resolution mismatch**

In the Windows Remote Desktop client, click "Show Options" → "Display" to adjust resolution.

**Issue 3: XRDP service fails to start**

```bash
# Check port conflicts
sudo lsof -i :3389

# Check logs
sudo journalctl -u xrdp -n 50 --no-pager
```

---

## Solution 2: NoMachine Configuration

### 1. Install NoMachine

```bash
# Download the latest version
wget https://download.nxnode.com/nx/nomachine_8.14.2_1_amd64.deb.tar.xz

# Extract and install
tar -xf nomachine_8.14.2_1_amd64.deb.tar.xz
cd nomachine_*
sudo dpkg -i nomachine_*.deb

# Or for RPM systems
wget https://download.nxnode.com/nx/nomachine_8.14.2_1_x86_64.rpm.tar.xz
tar -xf nomachine_8.14.2_1_x86_64.rpm.tar.xz
cd nomachine_*
sudo rpm -i nomachine_*.rpm
```

### 2. Configure NoMachine

```bash
# Check service status
sudo systemctl status nxserver

# Default port is 4000 (NX protocol)
sudo ufw allow 4000/tcp
```

### 3. Download Client

Visit [nomachine.com](https://www.nomachine.com/download) to download the client for your platform.

### 4. Connection

Client address format: `your_vps_ip:4000`

### NoMachine Performance Tuning

```bash
# Edit server configuration
sudo nano /usr/NX/etc/server.cfg

# Optimize network parameters
VideoCodecQuality 4        # Highest quality
MaxColorDepth 32           # 32-bit color
MaxSessionFPS 60           # Max frame rate
MinCompressionLevel 0      # Minimal compression (LAN)
```

---

## Security Hardening

### 1. Use SSH Tunnel Instead of Exposing Ports Directly

```bash
# Create local tunnel
ssh -L 3389:localhost:3389 user@your-vps-ip
# Then connect to localhost:3389
```

### 2. Change Default Ports

```bash
# XRDP port change
sudo nano /etc/xrdp/xrdp.ini
# port=3389 → port=3390

# NoMachine port change
sudo nano /usr/NX/etc/server.cfg
# port=4000 → port=4001
```

### 3. Enable SSH Two-Factor Authentication

```bash
# Install Google Authenticator PAM
sudo apt install -y libpam-google-authenticator
sudo nano /etc/pam.d/sshd
# Add: auth required pam_google_authenticator.so
```

### 4. Configure fail2ban to Prevent Brute Force

```bash
sudo apt install -y fail2ban

# Create XRDP filter rule
sudo nano /etc/fail2ban/jail.local
```

```ini
[xrdp]
enabled = true
port = 3389
filter = xrdp
maxretry = 3
bantime = 3600
```

---

## Performance Tuning Comparison

### XRDP Optimization

```bash
# Reduce color depth for speed
# Select 16-bit color when connecting from client

# Enable compression
sudo sed -i 's/MaxBpp=32/MaxBpp=24/' /etc/xrdp/sesman.ini
sudo sed -i 's/MaxBpp=32/MaxBpp=16/' /etc/xrdp/sesman.ini

# Adjust scaling
sudo nano /etc/xrdp/sesman.ini
# [Settings]
# Scale=70  # 70% scaling, saves bandwidth
```

### NoMachine Optimization

```bash
# NoMachine is already very efficient, but you can adjust for network conditions
# On the server:
sudo nano /usr/NX/etc/server.cfg

# High bandwidth environment (LAN/private line)
VideoCodecQuality 4
MinCompressionLevel 0

# Low bandwidth environment (public internet/mobile)
VideoCodecQuality 2
MinCompressionLevel 3
```

---

## Recommended Use Cases

| Scenario | Recommended | Reason |
|----------|-------------|--------|
| Occasional access, light management | XRDP | Simple setup, low resource usage |
| Frequent use, needs smooth experience | NoMachine | NX protocol is highly efficient |
| Limited bandwidth (overseas VPS) | NoMachine | Smart compression saves bandwidth |
| Multiple concurrent users | XRDP | Fully free, no concurrency limits |
| Need audio forwarding | NoMachine | Native support, easy setup |
| Mobile device remote access | NoMachine | Better mobile experience |

---

## Summary

For most VPS users:

- **If you only need occasional graphical operations**, XRDP is more than sufficient — simple to install and completely free
- **If you need frequent remote desktop access** or require smooth visual performance, NoMachine is worth the investment

Whichever solution you choose, always use it with an SSH tunnel and avoid exposing remote desktop ports directly to the public internet. Security should always be your top priority.
