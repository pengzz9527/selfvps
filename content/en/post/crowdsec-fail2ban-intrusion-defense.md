---
title: "CrowdSec + Fail2Ban联动防御：VPS入侵防护的终极组合，比单一方案强10倍"
description: "将CrowdSec的AI智能威胁情报与Fail2Ban的传统封禁能力结合，构建多层VPS安全防护体系。本文详解安装配置、联动机制、自定义场景、面板管理和实战调优。"
date: 2026-07-22T10:00:00+08:00
lastmod: 2026-07-22T10:00:00+08:00
slug: "crowdsec-fail2ban-intrusion-defense"
tags: ["CrowdSec", "Fail2Ban", "VPS安全", "入侵检测", "自动封禁", "自托管", "防火墙", "SSH保护"]
categories: ["安全运维"]
draft: false
image: /images/posts/crowdsec-fail2ban-intrusion-defense/featured.png
aliases: [/en/post/crowdsec-fail2ban-intrusion-defense/]
---

## Why Dual Defense?

In VPS operations, brute-force attacks are the most common threat. Statistics show that a publicly exposed SSH server receives **hundreds to thousands** of login attempts daily. A single defense tool often has blind spots:

- **Fail2Ban** reacts quickly based on local log rules but lacks global visibility and can be bypassed
- **CrowdSec** leverages community threat intelligence and machine learning to identify novel attack patterns, but has higher deployment complexity

Combining both achieves **local fast response + global threat intelligence** dual protection, leaving attackers nowhere to hide.

## Core Architecture

```
Attack Traffic → Nginx/Apache/SSH → Log System
                              ↓
                    ┌─────────────────────┐
                    │   CrowdSec Engine    │
                    │  (AI + Community Intel)│
                    └──────────┬──────────┘
                               ↓ bouncer
                    ┌─────────────────────┐
                    │   Fail2Ban          │
                    │  (Local Log Bans)    │
                    └──────────┬──────────┘
                               ↓
                    ┌─────────────────────┐
                    │   Firewall (iptables)│
                    │   / nftables         │
                    └─────────────────────┘
```

## Prerequisites

This tutorial assumes you have a VPS running one of the following:

- **Ubuntu 22.04/24.04 LTS** (recommended)
- **Debian 12**
- A regular user with sudo privileges

### Initial Setup

```bash
sudo apt update
sudo apt install -y curl wget ufw
```

## Step 1: Install CrowdSec

CrowdSec is an open-source intrusion detection and response engine that performs intelligent analysis by collecting system logs.

### Add Official Repository

```bash
curl -s https://install.crowdsec.net | bash
```

For manual installation:

```bash
# Add GPG key
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://packagecloud.io/crowdsec/crowdsec/gpgkey | sudo gpg --dearmor -o /etc/apt/keyrings/crowdsec.gpg

# Add repository
echo "deb [signed-by=/etc/apt/keyrings/crowdsec.gpg] https://packagecloud.io/crowdsec/crowdsec/ubuntu/ $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/crowdsec.list

sudo apt update
sudo apt install -y crowdsec
```

### Initialize Configuration

```bash
sudo cscli bootstrapping
```

### Install Scenario Packages

CrowdSec uses "scenarios" to define detection rules. Start with basic scenarios:

```bash
# SSH brute-force detection
sudo cscli scenarios add cs-ssh-bf

# Web application attack detection
sudo cscli scenarios add cs-http-probing
sudo cscli scenarios add cs-http-generic-bf

# SQL injection detection
sudo cscli scenarios add cs-sql-injection

# List installed scenarios
sudo cscli scenarios list
```

### Configure Log Collection

CrowdSec needs to read system logs. For Ubuntu/Debian:

```bash
# Enable journald log collection
sudo cscli collections add crowdsecurity/journald

# Or use syslog file
sudo cscli collections add crowdsecurity/syslog
```

Restart CrowdSec:

```bash
sudo systemctl restart crowdsec
sudo systemctl enable crowdsec
```

Verify status:

```bash
sudo cscli metrics
```

## Step 2: Install Fail2Ban

Fail2Ban is a classic log-based intrusion prevention system that automatically bans malicious IPs by analyzing logs.

```bash
sudo apt install -y fail2ban
```

### Basic Configuration

Create custom configuration:

```bash
sudo nano /etc/fail2ban/jail.local
```

```ini
[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 5
backend = auto

[sshd]
enabled = true
port = ssh
filter = sshd
logpath = /var/log/auth.log
maxretry = 3
bantime = 86400
```

Configuration explanation:

- `bantime`: Ban duration, default 1 hour, SSH set to 24 hours
- `findtime`: Statistics window, triggers ban if maxretry reached within 600 seconds
- `maxretry`: Maximum retry attempts

Restart Fail2Ban:

```bash
sudo systemctl restart fail2ban
sudo systemctl enable fail2ban
```

## Step 3: Configure CrowdSec-Fail2Ban Integration

This is the most critical step. CrowdSec passes ban instructions to Fail2Ban through the Bouncer plugin.

### Install CrowdSec Bouncer

```bash
sudo apt install -y crowdsec-firewall-bouncer
```

### Configure Bouncer

```bash
sudo nano /etc/crowdsec/bouncers/crowdsec-firewall-bouncer.yaml
```

```yaml
update_frequency: 10s
report_same_ipv: true
ipv4: true
ipv6: true
firewall_backend: iptables
log_level: info
log_truncation: 1048576
```

Restart CrowdSec to apply configuration:

```bash
sudo systemctl restart crowdsec
sudo systemctl restart crowdsec-firewall-bouncer
```

### Bidirectional Linkage Mechanism

Now we implement true bidirectional integration:

1. **CrowdSec → Fail2Ban**: When CrowdSec detects a malicious IP, it writes to Fail2Ban database through bouncer
2. **Fail2Ban → CrowdSec**: IPs banned by Fail2Ban are also synced to CrowdSec community intelligence

Configure Fail2Ban to notify CrowdSec:

```bash
sudo nano /etc/fail2ban/jail.local
```

Add:

```ini
[DEFAULT]
action = %(action_mwl)s
```

Or use more advanced linkage configuration:

```bash
sudo nano /etc/fail2ban/action.d/crowdsec.conf
```

```ini
[Definition]
actionstart = cscli bouncer add fail2ban --type f2b
actionstop = cscli bouncer remove fail2ban --type f2b
actioncheck = cscli bouncers list | grep -q fail2ban
actionban = cscli bouncers get fail2ban addip <ip> --expire <bantime>s
actionunban = cscli bouncers get fail2ban delip <ip>

[Init]
type = simple
```

## Step 4: Configure Nginx/Apache Log Monitoring

### Nginx Scenarios

```bash
sudo cscli collections add crowdsecurity/nginx
sudo cscli scenarios add cs-nginx-http-denied
```

### Apache Scenarios

```bash
sudo cscli collections add crowdsecurity/apache
sudo cscli scenarios add cs-apache-http-denied
```

### Verify Log Collection

```bash
# View CrowdSec logs
sudo journalctl -u crowdsec -f

# View Fail2Ban logs
sudo journalctl -u fail2ban -f
```

## Step 5: Management Panel & Visualization

### Using CrowdSec CLI

CrowdSec provides a command-line management interface:

```bash
# View ban list
sudo cscli decisions list

# Add whitelist IP
sudo cscli decisions add --ip 192.168.1.100 --duration +24h

# Remove ban
sudo cscli decisions delete --ip 192.168.1.100

# View threat intelligence
sudo cscli metadb list
```

### Using Fail2Ban Commands

```bash
# View current bans
fail2ban-client status sshd

# Manually ban IP
fail2ban-client set sshd banip 1.2.3.4

# Manually unban IP
fail2ban-client set sshd unbanip 1.2.3.4
```

## Step 6: Custom Protection Rules

### Create Custom Scenarios

```bash
sudo nano /etc/crowdsec/local-parsers/01-custom-parse.yaml
```

```yaml
name: CustomWebAttackParser
description: "Parse custom web attack patterns"
filter: "Dataset.Service == 'http' or Dataset.Service == 'https'"
match:
  - "Regex.MatchAll(Regex.New('(?i)(union\\s+select|drop\\s+table|<script)', ''), Event.Value).Len() > 0"
labels:
  type: web_attack
```

### Custom Fail2Ban Filters

```bash
sudo nano /etc/fail2ban/filter.d/custom-webattack.conf
```

```ini
[Definition]
failregex = ^<HOST> .* "(GET|POST|HEAD) .*(union.*select|drop.*table|<script>)
ignoreregex =
datepattern = ^%Y-%m-%dT%H:%M:%S
```

## Step 7: Performance Optimization & Security Tuning

### Prevent False Positives

```bash
# Add important IPs to CrowdSec whitelist
sudo cscli exclusions add --type ip --value 192.168.1.100

# Add whitelist to Fail2Ban
sudo nano /etc/fail2ban/jail.local
```

Add:

```ini
[DEFAULT]
ignoreip = 127.0.0.1/8 ::1 192.168.1.0/24
```

### Adjust Ban Strategy

```bash
# Progressive banning: 1st time 1 hour, 2nd time 24 hours, 3rd time permanent
sudo nano /etc/fail2ban/jail.local
```

Add:

```ini
[sshd]
enabled = true
maxretry = 3
bantime.increment = true
bantime.factor = 2
bantime.maxtime = 604800
```

### Log Rotation

```bash
sudo nano /etc/logrotate.d/fail2ban
```

```
/var/log/fail2ban.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
}
```

## Step 8: Monitoring & Alerting

### Email Alerts

```bash
sudo apt install -y mailutils
```

Configure Fail2Ban email alerts:

```bash
sudo nano /etc/fail2ban/jail.local
```

Add:

```ini
[DEFAULT]
destemail = admin@yourdomain.com
sender = fail2ban@yourdomain.com
mta = sendmail
action = %(action_mwl)s
```

### Slack/DingTalk Alerts

```bash
sudo nano /etc/fail2ban/action.d/notification.conf
```

```ini
[Definition]
actionban = curl -X POST -H 'Content-type: application/json' \
            --data '{"text":"Fail2Ban: IP <ip> banned by <name>"}' \
            https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

## Practical Testing

### Simulate Attack Tests

```bash
# Test SSH brute-force with hydra
hydra -l root -P /usr/share/wordlists/rockyou.txt ssh://your-vps-ip

# Observe CrowdSec and Fail2Ban responses
sudo journalctl -u crowdsec -f
sudo journalctl -u fail2ban -f
```

### Verify Protection Effectiveness

```bash
# View ban records
sudo cscli decisions list
fail2ban-client status sshd

# Check firewall rules
sudo iptables -L INPUT -n | grep crowdsec
```

## Troubleshooting

### CrowdSec Not Working

```bash
# Check service status
sudo systemctl status crowdsec

# View detailed logs
sudo journalctl -u crowdsec -n 100

# Reload configuration
sudo cscli hub update
sudo cscli scenarios list
```

### Fail2Ban False Bans

```bash
# View banned IPs
fail2ban-client status sshd

# Unban
fail2ban-client set sshd unbanip <IP>

# Check whitelist configuration
grep ignoreip /etc/fail2ban/jail.local
```

### Integration Failure

```bash
# Check bouncer status
sudo cscli bouncers list

# Restart related services
sudo systemctl restart crowdsec
sudo systemctl restart crowdsec-firewall-bouncer
sudo systemctl restart fail2ban
```

## Summary

The CrowdSec + Fail2Ban integration provides:

1. **Multi-layer Protection**: Local rules + Global intelligence
2. **Intelligent Detection**: AI analysis + Traditional matching
3. **Fast Response**: Auto-banning + Real-time alerts
4. **Flexible Configuration**: Custom scenarios + Whitelist management

This combination is ideal for:

- VPS servers exposed to the public internet
- Servers running web applications
- Environments requiring compliance auditing
- Self-hosted services with high security requirements

With the configuration in this guide, your VPS will gain enterprise-grade intrusion prevention capabilities while maintaining the advantage of being open-source and free.
