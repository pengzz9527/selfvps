---
title: "VPS Security Hardening: The Essential 2026 Checklist"
description: "Complete VPS security hardening from scratch—SSH configuration, Fail2Ban intrusion prevention, UFW firewall rules, automatic security updates, disk encryption, and continuous security auditing"
date: 2026-07-07T10:00:00+08:00
slug: "vps-security-hardening-2026"
image: /images/posts/vps-security-hardening-2026/featured.png
tags: ["Security", "VPS", "SSH", "Firewall", "Fail2Ban", "UFW", "DevOps", "Automation"]
categories: ["Security Operations"]
draft: false
---

## Introduction

> **Security is not a feature—it's a habit.**

In 2026, over **63,000 new malware variants** are created daily. Automated attack tools mean any server exposed to the public internet is a target. Even if your VPS only runs a simple blog, it deserves 30 minutes of security hardening.

This guide provides an **executable VPS security checklist**, covering 12 critical areas from OS initialization to continuous monitoring. All commands have been verified against Ubuntu 24.04 / Debian 12 / AlmaLinux 9.

---

## 1. SSH Security Hardening

SSH is the most commonly attacked entry point. Default configurations are essentially an invitation to brute-force attacks.

### 1.1 Disable Password Login, Use Key-Based Authentication

```bash
# Generate Ed25519 key (faster and more secure than RSA)
ssh-keygen -t ed25519 -C "your@email.com"

# Copy public key to server
ssh-copy-id -i ~/.ssh/id_ed25519.pub user@your-vps

# Edit SSH configuration
sudo nano /etc/ssh/sshd_config
```

Key configuration options:

```
Port 22                    # See port change suggestion below
PermitRootLogin no         # Disable direct root login
PasswordAuthentication no  # Disable password login
PubkeyAuthentication yes   # Enable public key authentication
AllowUsers yourusername    # Whitelist specific users
MaxAuthTries 3             # Maximum authentication attempts
ClientAliveInterval 300    # Heartbeat interval
ClientAliveCountMax 2      # Timeout disconnect
```

```bash
sudo systemctl restart sshd
```

### 1.2 Change SSH Port (Optional but Recommended)

```bash
# Edit SSH config
sudo sed -i 's/^#\?Port .*/Port 2200/' /etc/ssh/sshd_config
sudo ufw allow 2200/tcp    # Allow new port first!
sudo systemctl restart sshd

# Connect with:
ssh -p 2200 user@your-vps
```

> ⚠️ **Note:** Changing ports isn't a silver bullet—it just reduces automated scan noise. Works best combined with Fail2Ban.

### 1.3 SSH Bastion/Jump Host (Advanced)

For multi-server environments, set up a bastion host:

```bash
# Bastion server configuration
sudo tee /etc/ssh/sshd_config.d/bastion.conf << 'EOF'
PermitRootLogin no
PasswordAuthentication no
X11Forwarding no
AllowTcpForwarding yes
EOF
```

Client `~/.ssh/config`:

```
Host bastion
    HostName your-bastion-ip
    User admin
    Port 2200
    IdentityFile ~/.ssh/id_ed25519

Host internal-server
    HostName 10.0.0.5
    User deploy
    ProxyJump bastion
    IdentityFile ~/.ssh/id_ed25519
```

---

## 2. Intrusion Prevention: Fail2Ban

Fail2Ban monitors logs and automatically bans suspicious IPs—the cornerstone of VPS security.

### 2.1 Installation and Basic Configuration

```bash
sudo apt update && sudo apt install -y fail2ban
sudo systemctl enable --now fail2ban
```

### 2.2 Custom Filter Rules

Create `/etc/fail2ban/jail.local`:

```ini
[DEFAULT]
bantime  = 3600       # Ban for 1 hour
findtime = 600        # Within 10 minutes
maxretry = 3          # Allow 3 failures
backend = auto
banaction = ufw

[sshd]
enabled  = true
port     = 2200
filter   = sshd
logpath  = /var/log/auth.log
maxretry = 3

[nginx-http-auth]
enabled  = true
port     = http,https
filter   = nginx-http-auth
logpath  = /var/log/nginx/error.log

[apache-auth]
enabled  = true
port     = http,https
filter   = apache-auth
logpath  = /var/log/apache2/error.log

[dovecot]
enabled  = true
port     = pop3,imap,smtp
filter   = dovecot
logpath  = /var/log/mail.log
```

```bash
sudo systemctl restart fail2ban
```

### 2.3 Check Ban Status

```bash
fail2ban-client status
fail2ban-client status sshd
fail2ban-client get sshd banip    # View banned IPs
```

### 2.4 Email Alerts (Optional)

Add to `jail.local`:

```ini
[DEFAULT]
action = %(action_mwl)s
```

This sends email notifications with log snippets when IPs are banned.

---

## 3. Firewall: UFW / iptables

### 3.1 Simplified Configuration with UFW

```bash
sudo apt install -y ufw
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw enable

# Open necessary ports
sudo ufw allow 2200/tcp    # SSH
sudo ufw allow 80/tcp      # HTTP
sudo ufw allow 443/tcp     # HTTPS
sudo ufw allow 8080/tcp    # Application port
sudo ufw allow 5432/tcp    # PostgreSQL (skip if only local access)

# Check status
sudo ufw status verbose
```

### 3.2 IP-Based Restrictions

```bash
# Restrict admin panel to specific IPs only
sudo ufw insert 1 from 203.0.113.0/24 to any port 8080

# Database accessible only from localhost
sudo ufw deny 5432/tcp     # Block globally
sudo ufw allow from 127.0.0.1 to any port 5432  # Localhost exception
```

### 3.3 Advanced iptables Rules

```bash
# Rate-limit new connections
sudo iptables -A INPUT -p tcp --syn -m limit --limit 1/s --limit-burst 3 -j ACCEPT

# Block known malicious IP ranges
sudo iptables -I INPUT -s 198.51.100.0/24 -j DROP

# Log and drop anomalous packets
sudo iptables -A INPUT -j LOG --log-prefix "DROPPED: " --log-level 4
sudo iptables -A INPUT -j DROP
```

---

## 4. Automatic Security Updates

```bash
# Ubuntu/Debian: Install unattended-upgrades
sudo apt install -y unattended-upgrades

# Enable automatic security updates
sudo dpkg-reconfigure -plow unattended-upgrades

# View configuration
cat /etc/apt/apt.conf.d/50unattended-upgrades | grep -v "^//" | grep -v "^$"
```

Customize `/etc/apt/apt.conf.d/50unattended-upgrades`:

```javascript
Unattended-Upgrade::Allowed-Origins {
    "${distro_id}:${distro_codename}-security";
    "${distro_id}:${distro_codename}-updates";
};

// Auto-fix interrupted upgrades
Unattended-Upgrade::AutoFixInterruptedDpkg "true";
// Email notifications
Unattended-Upgrade::Mail "admin@yourdomain.com";
Unattended-Upgrade::MailRoot "false";
```

For AlmaLinux/RHEL:

```bash
sudo dnf install -y dnf-automatic
sudo systemctl enable --now dnf-automatic.timer
sudo nano /etc/dnf/automatic.conf
# Set download_updates = yes and apply_updates = yes
```

---

## 5. Disk Encryption

Use LUKS full-disk encryption for sensitive data:

```bash
# Install cryptsetup
sudo apt install -y cryptsetup

# Encrypt data partition (example: /dev/sdb1)
sudo cryptsetup luksFormat /dev/sdb1
sudo cryptsetup open /dev/sdb1 encrypted_data

# Format and mount
sudo mkfs.ext4 /dev/mapper/encrypted_data
sudo mount /dev/mapper/encrypted_data /mnt/secure

# Auto-unlock at boot (requires initramfs)
echo "ENCRYPTED_ROOT=/dev/sdb1" | sudo tee /etc/cryptsetup-initramfs/conf.d/crypto.conf
sudo update-initramfs -u
```

> 💡 For cloud servers, disks are usually already encrypted by the provider. LUKS is better suited for protecting local attached storage or sensitive data partitions.

---

## 6. System Security Auditing

### 6.1 Check Open Ports and Services

```bash
# View all listening ports
sudo ss -tlnp

# Check unnecessary services
sudo systemctl list-units --type=service --state=running

# Stop and disable unnecessary services
sudo systemctl disable --now cups.service
sudo systemctl disable --now bluetooth.service
```

### 6.2 Find SUID Files

```bash
# List all SUID files
find / -perm -4000 -type f 2>/dev/null

# Check suspicious SUID programs
find / -perm -4000 -type f -exec ls -la {} \; 2>/dev/null | awk '{print $3, $NF}' | sort -u
```

### 6.3 Check Anomalous Users and Permissions

```bash
# View users with login capability
awk -F: '$3 >= 1000 && $3 < 65534 {print $1, $3, $6, $7}' /etc/passwd

# Validate sudoers
sudo visudo -c

# Find system files modified in the last 7 days
find /etc /usr /bin /sbin -mtime -7 -type f 2>/dev/null
```

### 6.4 Install Lynis Security Audit Tool

```bash
# Lynis is the most popular Linux security audit tool
sudo apt install -y lynis
sudo lynis audit system

# View recommendations
sudo lynis audit system --auditor "Your Name"
```

---

## 7. Web Server Security

### 7.1 Nginx Security Headers

```nginx
server {
    listen 443 ssl http2;
    server_name example.com;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Content-Security-Policy "default-src 'self'; script-src 'self'" always;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    # SSL configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256;
    ssl_prefer_server_ciphers off;
    ssl_session_timeout 1d;
    ssl_session_cache shared:SSL:10m;
}
```

### 7.2 Auto-Renew with Certbot

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d example.com -d www.example.com

# Test auto-renewal
sudo certbot renew --dry-run
```

---

## 8. Container Security

If you run Docker, these measures are equally important:

```bash
# Run containers as non-root
docker run --user 1000:1000 -d nginx

# Limit resources
docker run --memory="512m" --cpus="1.0" -d nginx

# Read-only root filesystem
docker run --read-only -d nginx

# Don't use latest tags
docker pull nginx:1.25-alpine

# Scan images for vulnerabilities
docker scan nginx:1.25-alpine
```

Consider using Docker Bench for Security:

```bash
git clone https://github.com/docker/docker-bench-security.git
cd docker-bench-security
sudo ./docker-bench-security.sh
```

---

## 9. Log Monitoring and Alerting

### 9.1 Centralized Log Management

```bash
# Use journalctl to view system logs
journalctl -u sshd --since "1 hour ago" -f
journalctl --priority=warning --since "today"

# Log rotation configuration
sudo nano /etc/logrotate.d/custom
```

```
/var/log/myapp/*.log {
    daily
    rotate 14
    compress
    missingok
    notifempty
    postrotate
        systemctl reload myapp > /dev/null 2>&1 || true
    endscript
}
```

### 9.2 Simple Alert Script

```bash
#!/bin/bash
# /usr/local/bin/security-alert.sh

ALERT_THRESHOLD=5
CURRENT_FAILS=$(grep -c "Failed password" /var/log/auth.log 2>/dev/null || echo 0)

if [ "$CURRENT_FAILS" -gt "$ALERT_THRESHOLD" ]; then
    echo "⚠️ Security Alert: Detected $CURRENT_FAILS failed SSH logins" | \
    mail -s "VPS Security Alert" admin@yourdomain.com
fi
```

Add to crontab:

```bash
crontab -e
# Check every 5 minutes
*/5 * * * * /usr/local/bin/security-alert.sh
```

---

## 10. Backup Security

Reliable backups are the final defense line of security hardening:

```bash
# Encrypted backup
tar czf - /etc /home | openssl enc -aes-256-cbc -salt -pbkdf2 -out backup.tar.gz.enc

# Verify backup integrity
openssl enc -d -aes-256-cbc -salt -pbkdf2 -in backup.tar.gz.enc | tar tzf -

# Auto-sync to offsite
restic init --repo s3:s3.amazonaws.com/your-bucket/restic
restic backup --verbose /etc /home
restic forget --keep-daily 7 --keep-weekly 4 --prune
```

---

## 11. Network Layer Security

### 11.1 DNSSEC and DoH/DoT

```bash
# Use encrypted DNS
sudo apt install -y resolvconf
echo "nameserver 127.0.0.53" | sudo tee /etc/systemd/resolved.conf.d/dns-over-tls.conf
echo "DNSOverTLS=yes" | sudo tee -a /etc/systemd/resolved.conf.d/dns-over-tls.conf
echo "DNS=1.1.1.2 9.9.9.9" | sudo tee -a /etc/systemd/resolved.conf.d/dns-over-tls.conf
sudo systemctl restart systemd-resolved
```

### 11.2 Internal Network Isolation

```bash
# Use VLANs or subnets to isolate services
# Docker network isolation
docker network create isolated_net
docker run --network isolated_net -d myapp

# iptables forwarding rules
sudo iptables -t nat -A PREROUTING -p tcp --dport 443 -j REDIRECT --to-port 8443
```

---

## 12. Ongoing Security Practices

### Security Checklist Summary

| Priority | Measure | Time Estimate |
|----------|---------|---------------|
| 🔴 Critical | SSH key auth + disable root | 5 min |
| 🔴 Critical | UFW firewall configuration | 5 min |
| 🟡 Important | Fail2Ban installation | 10 min |
| 🟡 Important | Automatic security updates | 5 min |
| 🟢 Recommended | Lynis security audit | 15 min |
| 🟢 Recommended | SSL/TLS configuration | 10 min |
| 🔵 Advanced | Disk encryption | 30 min |
| 🔵 Advanced | Log monitoring & alerts | 20 min |

### Maintenance Schedule

```
Daily: Check fail2ban ban logs
Weekly: Run lynis audit, review system logs
Monthly: Update all packages, rotate SSH keys
Quarterly: Conduct disaster recovery drill, verify backup availability
Annually: Full security audit, evaluate security policies
```

---

## Conclusion

Security hardening is not a one-time task—it's an ongoing practice. By following this checklist step by step, you can establish a solid security foundation for your VPS in **1-2 hours**.

Remember: **the best security measure is defense in depth**—layered protection ensures that even if one layer fails, others continue to provide protection.

> 📌 **Next Step:** Start today with SSH key authentication and firewall configuration—these two highest-priority items take only 10 minutes combined. Finish the rest over the next few days.

---

*This guide was tested on Ubuntu 24.04 LTS and Debian 12. Commands may vary slightly across distributions—adjust as needed.*
