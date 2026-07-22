---
title: "CrowdSec + Fail2Ban 联动防御：VPS 入侵防护的终极组合，比单一方案强 10 倍"
description: "将 CrowdSec 的 AI 智能威胁情报与 Fail2Ban 的传统封禁能力结合，构建多层 VPS 安全防护体系。本文详解安装配置、联动机制、自定义场景、面板管理和实战调优。"
date: 2026-07-22T10:00:00+08:00
lastmod: 2026-07-22T10:00:00+08:00
slug: "crowdsec-fail2ban-intrusion-defense"
tags: ["CrowdSec", "Fail2Ban", "VPS安全", "入侵检测", "自动封禁", "自托管", "防火墙", "SSH保护"]
categories: ["安全运维"]
draft: false
image: /images/posts/crowdsec-fail2ban-intrusion-defense/featured.png
aliases: [/zh/post/crowdsec-fail2ban-intrusion-defense/]
---

## 为什么需要双重防御？

在 VPS 运维中，暴力破解是最常见的攻击手段。据统计，一台暴露在公网的 SSH 服务器每天会收到 **数百到数千次** 登录尝试。单一防护工具往往存在盲区：

- **Fail2Ban** 基于本地日志规则，反应快但缺乏全局视野，容易被绕过
- **CrowdSec** 利用社区威胁情报和机器学习，能识别新型攻击模式，但部署复杂度高

将两者结合，可以实现 **本地快速响应 + 全球威胁情报** 的双重保护，让攻击者无处可逃。

## 核心架构

```
攻击流量 → Nginx/Apache/SSH → 日志系统
                              ↓
                    ┌─────────────────────┐
                    │   CrowdSec Engine    │
                    │  (AI + 社区情报分析)  │
                    └──────────┬──────────┘
                               ↓ bouncer
                    ┌─────────────────────┐
                    │   Fail2Ban          │
                    │  (本地日志封禁)       │
                    └──────────┬──────────┘
                               ↓
                    ┌─────────────────────┐
                    │   Firewall (iptables)│
                    │   / nftables         │
                    └─────────────────────┘
```

## 环境准备

本教程假设你有一台运行以下系统的 VPS：

- **Ubuntu 22.04/24.04 LTS**（推荐）
- **Debian 12**
- 具备 sudo 权限的普通用户

### 前置要求

```bash
sudo apt update
sudo apt install -y curl wget ufw
```

## 第一步：安装 CrowdSec

CrowdSec 是一个开源的入侵检测与响应引擎，通过收集系统日志进行智能分析。

### 添加官方仓库

```bash
curl -s https://install.crowdsec.net | bash
```

如果脚本无法访问，手动安装：

```bash
# 添加 GPG 密钥
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://packagecloud.io/crowdsec/crowdsec/gpgkey | sudo gpg --dearmor -o /etc/apt/keyrings/crowdsec.gpg

# 添加仓库
echo "deb [signed-by=/etc/apt/keyrings/crowdsec.gpg] https://packagecloud.io/crowdsec/crowdsec/ubuntu/ $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/crowdsec.list

sudo apt update
sudo apt install -y crowdsec
```

### 初始化配置

```bash
sudo cscli bootstrapping
```

### 安装场景包

CrowdSec 使用"场景"来定义检测规则。先安装基础场景：

```bash
# 安装 SSH 暴力破解场景
sudo cscli scenarios add cs-ssh-bf

# 安装 Web 应用攻击场景
sudo cscli scenarios add cs-http-probing
sudo cscli scenarios add cs-http-generic-bf

# 安装 SQL 注入场景
sudo cscli scenarios add cs-sql-injection

# 查看已安装场景
sudo cscli scenarios list
```

### 配置日志采集

CrowdSec 需要读取系统日志。对于 Ubuntu/Debian：

```bash
# 启用 journald 日志采集
sudo cscli collections add crowdsecurity/journald

# 或者使用 syslog 文件
sudo cscli collections add crowdsecurity/syslog
```

重启 CrowdSec 服务：

```bash
sudo systemctl restart crowdsec
sudo systemctl enable crowdsec
```

检查状态：

```bash
sudo cscli metrics
```

## 第二步：安装 Fail2Ban

Fail2Ban 是经典的基于日志的入侵防御系统，通过分析日志自动封禁恶意 IP。

```bash
sudo apt install -y fail2ban
```

### 基本配置

创建自定义配置文件：

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

配置说明：

- `bantime`：封禁时长，默认 1 小时，SSH 设为 24 小时
- `findtime`：统计窗口，600 秒内触发 maxretry 次即封禁
- `maxretry`：最大重试次数

重启 Fail2Ban：

```bash
sudo systemctl restart fail2ban
sudo systemctl enable fail2ban
```

## 第三步：配置 CrowdSec 与 Fail2Ban 联动

这是最关键的一步。CrowdSec 通过 Bouncer 插件将封禁指令传递给 Fail2Ban。

### 安装 CrowdSec Bouncer

```bash
sudo apt install -y crowdsec-firewall-bouncer
```

### 配置 Bouncer

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

重启 CrowdSec 使配置生效：

```bash
sudo systemctl restart crowdsec
sudo systemctl restart crowdsec-firewall-bouncer
```

### 双向联动机制

现在我们需要实现真正的双向联动：

1. **CrowdSec → Fail2Ban**：CrowdSec 检测到恶意 IP 后，通过 bouncer 写入 Fail2Ban 数据库
2. **Fail2Ban → CrowdSec**：Fail2Ban 封禁的 IP 也同步到 CrowdSec 社区情报

配置 Fail2Ban 通知 CrowdSec：

```bash
sudo nano /etc/fail2ban/jail.local
```

添加：

```ini
[DEFAULT]
action = %(action_mwl)s
```

或者使用更高级的联动配置：

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

## 第四步：配置 Nginx/Apache 日志监控

### Nginx 场景

```bash
sudo cscli collections add crowdsecurity/nginx
sudo cscli scenarios add cs-nginx-http-denied
```

### Apache 场景

```bash
sudo cscli collections add crowdsecurity/apache
sudo cscli scenarios add cs-apache-http-denied
```

### 验证日志采集

```bash
# 查看 CrowdSec 日志
sudo journalctl -u crowdsec -f

# 查看 Fail2Ban 日志
sudo journalctl -u fail2ban -f
```

## 第五步：管理面板与可视化

### 使用 CrowdSec Web UI

CrowdSec 提供简单的命令行管理界面：

```bash
# 查看封禁列表
sudo cscli decisions list

# 添加白名单 IP
sudo cscli decisions add --ip 192.168.1.100 --duration +24h

# 移除封禁
sudo cscli decisions delete --ip 192.168.1.100

# 查看威胁情报
sudo cscli metadb list
```

### 使用 Fail2Ban 命令

```bash
# 查看当前封禁
fail2ban-client status sshd

# 手动封禁 IP
fail2ban-client set sshd banip 1.2.3.4

# 手动解封 IP
fail2ban-client set sshd unbanip 1.2.3.4
```

## 第六步：自定义防护规则

### 创建自定义场景

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

### 自定义 Fail2Ban 过滤器

```bash
sudo nano /etc/fail2ban/filter.d/custom-webattack.conf
```

```ini
[Definition]
failregex = ^<HOST> .* "(GET|POST|HEAD) .*(union.*select|drop.*table|<script>)
ignoreregex =
datepattern = ^%Y-%m-%dT%H:%M:%S
```

## 第七步：性能优化与安全调优

### 防止误封禁

```bash
# 在 CrowdSec 中添加重要 IP 到白名单
sudo cscli exclusions add --type ip --value 192.168.1.100

# 在 Fail2Ban 中添加白名单
sudo nano /etc/fail2ban/jail.local
```

添加：

```ini
[DEFAULT]
ignoreip = 127.0.0.1/8 ::1 192.168.1.0/24
```

### 调整封禁策略

```bash
# 渐进式封禁：第一次 1 小时，第二次 24 小时，第三次永久
sudo nano /etc/fail2ban/jail.local
```

```ini
[sshd]
enabled = true
maxretry = 3
bantime.increment = true
bantime.factor = 2
bantime.maxtime = 604800
```

### 日志轮转

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

## 第八步：监控与告警

### 设置邮件告警

```bash
sudo apt install -y mailutils
```

配置 Fail2Ban 邮件告警：

```bash
sudo nano /etc/fail2ban/jail.local
```

添加：

```ini
[DEFAULT]
destemail = admin@yourdomain.com
sender = fail2ban@yourdomain.com
mta = sendmail
action = %(action_mwl)s
```

### 设置 Slack/钉钉告警

```bash
sudo nano /etc/fail2ban/action.d/notification.conf
```

```ini
[Definition]
actionban = curl -X POST -H 'Content-type: application/json' \
            --data '{"text":"Fail2Ban: IP <ip> banned by <name>"}' \
            https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

## 实战测试

### 模拟攻击测试

```bash
# 使用 hydra 测试 SSH 暴力破解
hydra -l root -P /usr/share/wordlists/rockyou.txt ssh://your-vps-ip

# 观察 CrowdSec 和 Fail2Ban 的反应
sudo journalctl -u crowdsec -f
sudo journalctl -u fail2ban -f
```

### 验证防护效果

```bash
# 查看封禁记录
sudo cscli decisions list
fail2ban-client status sshd

# 检查防火墙规则
sudo iptables -L INPUT -n | grep crowdsec
```

## 常见问题排查

### CrowdSec 不工作

```bash
# 检查服务状态
sudo systemctl status crowdsec

# 查看详细日志
sudo journalctl -u crowdsec -n 100

# 重新加载配置
sudo cscli hub update
sudo cscli scenarios list
```

### Fail2Ban 误封禁

```bash
# 查看被封禁的 IP
fail2ban-client status sshd

# 解封
fail2ban-client set sshd unbanip <IP>

# 检查白名单配置
grep ignoreip /etc/fail2ban/jail.local
```

### 联动失效

```bash
# 检查 bouncer 状态
sudo cscli bouncers list

# 重启相关服务
sudo systemctl restart crowdsec
sudo systemctl restart crowdsec-firewall-bouncer
sudo systemctl restart fail2ban
```

## 总结

CrowdSec + Fail2Ban 联动方案提供了：

1. **多层防护**：本地规则 + 全球情报
2. **智能检测**：AI 分析 + 传统匹配
3. **快速响应**：自动封禁 + 实时告警
4. **灵活配置**：自定义场景 + 白名单管理

这种组合特别适合：

- 暴露公网的 VPS 服务器
- 运行 Web 应用的服务器
- 需要合规审计的环境
- 对安全性要求较高的自托管服务

通过本文的配置，你的 VPS 将获得企业级的入侵防御能力，同时保持开源免费的优势。
