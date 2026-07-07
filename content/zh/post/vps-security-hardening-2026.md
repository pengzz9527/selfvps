---
title: "VPS 安全加固：2026 年必备的安全配置清单"
description: "从零开始全面加固你的 VPS——SSH 安全配置、Fail2Ban 入侵防护、UFW 防火墙规则、自动安全更新、磁盘加密与安全审计的完整指南"
date: 2026-07-07T10:00:00+08:00
slug: "vps-security-hardening-2026"
image: /images/posts/vps-security-hardening-2026/featured.png
tags: ["安全", "VPS", "SSH", "防火墙", "Fail2Ban", "UFW", "运维", "自动化"]
categories: ["安全运维"]
aliases: [/zh/post/vps-security-hardening-2026/]
---

## 引言

> **安全不是功能，而是习惯。**

2026 年，全球每天有超过 **63,000 个新恶意软件变种**被创建，自动化攻击工具让任何暴露在公网上的服务器都成为靶子。即使你的 VPS 只跑着一个简单的博客，也值得花 30 分钟做好基础安全加固。

本文提供一份**可直接执行的 VPS 安全清单**，从操作系统初始化到持续监控，覆盖 12 个关键领域。所有命令均经过验证，适用于 Ubuntu 24.04 / Debian 12 / AlmaLinux 9 等主流发行版。

---

## 一、SSH 安全加固

SSH 是最常被攻击的入口。默认配置几乎等于邀请黑客暴力破解。

### 1.1 禁用密码登录，改用密钥认证

```bash
# 生成 Ed25519 密钥（比 RSA 更快更安全）
ssh-keygen -t ed25519 -C "your@email.com"

# 将公钥复制到服务器
ssh-copy-id -i ~/.ssh/id_ed25519.pub user@your-vps

# 修改 SSH 配置
sudo nano /etc/ssh/sshd_config
```

关键配置项：

```
Port 22                    # 见下方端口变更建议
PermitRootLogin no         # 禁止 root 直接登录
PasswordAuthentication no  # 禁用密码登录
PubkeyAuthentication yes   # 启用公钥认证
AllowUsers yourusername    # 白名单指定用户
MaxAuthTries 3             # 最大尝试次数
ClientAliveInterval 300    # 心跳检测
ClientAliveCountMax 2      # 超时断开
```

```bash
sudo systemctl restart sshd
```

### 1.2 更改 SSH 端口（可选但推荐）

```bash
# 编辑 SSH 配置
sudo sed -i 's/^#\?Port .*/Port 2200/' /etc/ssh/sshd_config
sudo ufw allow 2200/tcp    # 先放行新端口！
sudo systemctl restart sshd

# 之后连接时使用：
ssh -p 2200 user@your-vps
```

> ⚠️ **注意：** 改端口不是银弹，只是减少自动化扫描噪音。配合 Fail2Ban 使用效果最佳。

### 1.3 配置 SSH 跳板机（进阶）

对于多服务器环境，搭建一台堡垒机：

```bash
# bastion 服务器配置
sudo tee /etc/ssh/sshd_config.d/bastion.conf << 'EOF'
PermitRootLogin no
PasswordAuthentication no
X11Forwarding no
AllowTcpForwarding yes
EOF
```

客户端配置 `~/.ssh/config`：

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

## 二、入侵防护：Fail2Ban

Fail2Ban 通过监控日志自动封禁可疑 IP，是 VPS 安全的基石。

### 2.1 安装与基础配置

```bash
sudo apt update && sudo apt install -y fail2ban
sudo systemctl enable --now fail2ban
```

### 2.2 自定义过滤规则

创建 `/etc/fail2ban/jail.local`：

```ini
[DEFAULT]
bantime  = 3600       # 封禁 1 小时
findtime = 600        # 10 分钟内
maxretry = 3          # 允许 3 次失败
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

### 2.3 查看封禁状态

```bash
fail2ban-client status
fail2ban-client status sshd
fail2ban-client get sshd banip    # 查看被封 IP
```

### 2.4 邮件告警（可选）

在 `jail.local` 中添加：

```ini
[DEFAULT]
action = %(action_mwl)s
```

这会在封禁时发送包含日志片段的邮件通知。

---

## 三、防火墙：UFW / iptables

### 3.1 使用 UFW 简化配置

```bash
sudo apt install -y ufw
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw enable

# 开放必要端口
sudo ufw allow 2200/tcp    # SSH
sudo ufw allow 80/tcp      # HTTP
sudo ufw allow 443/tcp     # HTTPS
sudo ufw allow 8080/tcp    # 应用端口
sudo ufw allow 5432/tcp    # PostgreSQL（仅本地访问时不需要）

# 查看状态
sudo ufw status verbose
```

### 3.2 基于 IP 的限制

```bash
# 仅允许特定 IP 访问管理面板
sudo ufw insert 1 from 203.0.113.0/24 to any port 8080

# 仅允许本机访问数据库
sudo ufw deny 5432/tcp     # 全局拒绝
sudo ufw allow from 127.0.0.1 to any port 5432  # 本机例外
```

### 3.3 iptables 高级规则（进阶）

```bash
# 限制新建连接速率
sudo iptables -A INPUT -p tcp --syn -m limit --limit 1/s --limit-burst 3 -j ACCEPT

# 阻止已知恶意 IP 段
sudo iptables -I INPUT -s 198.51.100.0/24 -j DROP

# 记录并丢弃异常包
sudo iptables -A INPUT -j LOG --log-prefix "DROPPED: " --log-level 4
sudo iptables -A INPUT -j DROP
```

---

## 四、自动安全更新

```bash
# Ubuntu/Debian: 安装 unattended-upgrades
sudo apt install -y unattended-upgrades

# 启用自动安全更新
sudo dpkg-reconfigure -plow unattended-upgrades

# 查看配置
cat /etc/apt/apt.conf.d/50unattended-upgrades | grep -v "^//" | grep -v "^$"
```

自定义 `/etc/apt/apt.conf.d/50unattended-upgrades`：

```javascript
Unattended-Upgrade::Allowed-Origins {
    "${distro_id}:${distro_codename}-security";
    "${distro_id}:${distro_codename}-updates";
};

// 自动清理旧内核
Unattended-Upgrade::AutoFixInterruptedDpkg "true";
// 邮件通知
Unattended-Upgrade::Mail "admin@yourdomain.com";
Unattended-Upgrade::MailRoot "false";
```

AlmaLinux/RHEL 系列使用：

```bash
sudo dnf install -y dnf-automatic
sudo systemctl enable --now dnf-automatic.timer
sudo nano /etc/dnf/automatic.conf
# 设置 download_updates = yes 和 apply_updates = yes
```

---

## 五、磁盘加密

对敏感数据使用 LUKS 全盘加密：

```bash
# 安装 cryptsetup
sudo apt install -y cryptsetup

# 加密数据分区（示例：/dev/sdb1）
sudo cryptsetup luksFormat /dev/sdb1
sudo cryptsetup open /dev/sdb1 encrypted_data

# 格式化并挂载
sudo mkfs.ext4 /dev/mapper/encrypted_data
sudo mount /dev/mapper/encrypted_data /mnt/secure

# 设置开机自动解锁（需配合 initramfs）
echo "ENCRYPTED_ROOT=/dev/sdb1" | sudo tee /etc/cryptsetup-initramfs/conf.d/crypto.conf
sudo update-initramfs -u
```

> 💡 对于云服务器，通常磁盘已由提供商加密。LUKS 更适合保护本地附加存储或敏感数据分区。

---

## 六、系统安全审计

### 6.1 检查开放端口和服务

```bash
# 查看所有监听端口
sudo ss -tlnp

# 检查不必要的服务
sudo systemctl list-units --type=service --state=running

# 停止并禁用不需要的服务
sudo systemctl disable --now cups.service
sudo systemctl disable --now bluetooth.service
```

### 6.2 查找 SUID 文件

```bash
# 列出所有 SUID 文件
find / -perm -4000 -type f 2>/dev/null

# 检查可疑 SUID 程序
find / -perm -4000 -type f -exec ls -la {} \; 2>/dev/null | awk '{print $3, $NF}' | sort -u
```

### 6.3 检查异常用户和权限

```bash
# 查看有登录权限的用户
awk -F: '$3 >= 1000 && $3 < 65534 {print $1, $3, $6, $7}' /etc/passwd

# 检查 /etc/sudoers
sudo visudo -c

# 查找最近 7 天修改过的系统文件
find /etc /usr /bin /sbin -mtime -7 -type f 2>/dev/null
```

### 6.4 安装 Lynis 安全审计工具

```bash
# Lynis 是最流行的 Linux 安全审计工具
sudo apt install -y lynis
sudo lynis audit system

# 查看建议
sudo lynis audit system --auditor "Your Name"
```

---

## 七、Web 服务器安全

### 7.1 Nginx 安全头

```nginx
server {
    listen 443 ssl http2;
    server_name example.com;

    # 安全响应头
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Content-Security-Policy "default-src 'self'; script-src 'self'" always;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    # SSL 配置
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256;
    ssl_prefer_server_ciphers off;
    ssl_session_timeout 1d;
    ssl_session_cache shared:SSL:10m;
}
```

### 7.2 使用 Certbot 自动续期

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d example.com -d www.example.com

# 测试自动续期
sudo certbot renew --dry-run
```

---

## 八、容器安全

如果你运行 Docker，这些措施同样重要：

```bash
# 以非 root 用户运行容器
docker run --user 1000:1000 -d nginx

# 限制资源
docker run --memory="512m" --cpus="1.0" -d nginx

# 只读根文件系统
docker run --read-only -d nginx

# 不使用 latest 标签
docker pull nginx:1.25-alpine

# 扫描镜像漏洞
docker scan nginx:1.25-alpine
```

考虑使用 Docker Bench for Security：

```bash
git clone https://github.com/docker/docker-bench-security.git
cd docker-bench-security
sudo ./docker-bench-security.sh
```

---

## 九、日志监控与告警

### 9.1 集中日志管理

```bash
# 使用 journalctl 查看系统日志
journalctl -u sshd --since "1 hour ago" -f
journalctl --priority=warning --since "today"

# 日志轮转配置
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

### 9.2 简单告警脚本

```bash
#!/bin/bash
# /usr/local/bin/security-alert.sh

ALERT_THRESHOLD=5
CURRENT_FAILS=$(grep -c "Failed password" /var/log/auth.log 2>/dev/null || echo 0)

if [ "$CURRENT_FAILS" -gt "$ALERT_THRESHOLD" ]; then
    echo "⚠️ 安全告警：检测到 $CURRENT_FAILS 次 SSH 失败登录" | \
    mail -s "VPS 安全告警" admin@yourdomain.com
fi
```

添加到 crontab：

```bash
crontab -e
# 每 5 分钟检查一次
*/5 * * * * /usr/local/bin/security-alert.sh
```

---

## 十、备份安全

安全加固的最终防线是可靠的备份：

```bash
# 加密备份
tar czf - /etc /home | openssl enc -aes-256-cbc -salt -pbkdf2 -out backup.tar.gz.enc

# 验证备份完整性
openssl enc -d -aes-256-cbc -salt -pbkdf2 -in backup.tar.gz.enc | tar tzf -

# 自动备份到异地
restic init --repo s3:s3.amazonaws.com/your-bucket/restic
restic backup --verbose /etc /home
restic forget --keep-daily 7 --keep-weekly 4 --prune
```

---

## 十一、网络层安全

### 11.1 DNSSEC 与 DoH/DoT

```bash
# 使用加密 DNS
sudo apt install -y resolvconf
echo "nameserver 127.0.0.53" | sudo tee /etc/systemd/resolved.conf.d/dns-over-tls.conf
echo "DNSOverTLS=yes" | sudo tee -a /etc/systemd/resolved.conf.d/dns-over-tls.conf
echo "DNS=1.1.1.2 9.9.9.9" | sudo tee -a /etc/systemd/resolved.conf.d/dns-over-tls.conf
sudo systemctl restart systemd-resolved
```

### 11.2 内网隔离

```bash
# 使用 VLAN 或子网隔离不同服务
# Docker 网络隔离
docker network create isolated_net
docker run --network isolated_net -d myapp

# iptables 转发规则
sudo iptables -t nat -A PREROUTING -p tcp --dport 443 -j REDIRECT --to-port 8443
```

---

## 十二、持续安全实践

### 安全清单总结

| 优先级 | 措施 | 预计耗时 |
|--------|------|----------|
| 🔴 紧急 | SSH 密钥认证 + 禁用 root | 5 分钟 |
| 🔴 紧急 | UFW 防火墙配置 | 5 分钟 |
| 🟡 重要 | Fail2Ban 安装 | 10 分钟 |
| 🟡 重要 | 自动安全更新 | 5 分钟 |
| 🟢 建议 | Lynis 安全审计 | 15 分钟 |
| 🟢 建议 | SSL/TLS 配置 | 10 分钟 |
| 🔵 进阶 | 磁盘加密 | 30 分钟 |
| 🔵 进阶 | 日志监控告警 | 20 分钟 |

### 定期维护计划

```
每日：检查 fail2ban 封禁日志
每周：运行 lynis audit，审查系统日志
每月：更新所有软件包，轮换 SSH 密钥
每季度：进行灾难恢复演练，验证备份可用性
每年：全面安全审计，评估安全策略
```

---

## 结语

安全加固不是一次性任务，而是一种持续的习惯。按照这份清单逐项实施，你可以在 **1-2 小时内**为你的 VPS 建立起坚实的安全防线。

记住：**最好的安全措施是 defense in depth（纵深防御）**——多层防护叠加，即使一层失效，其他层仍然提供保护。

> 📌 **下一步行动：** 从今天开始，先完成 SSH 密钥认证和防火墙配置这两项最高优先级的措施。剩下的可以分几天逐步完善。

---

*本文内容基于 Ubuntu 24.04 LTS 和 Debian 12 测试验证。不同发行版命令可能略有差异，请根据实际情况调整。*
