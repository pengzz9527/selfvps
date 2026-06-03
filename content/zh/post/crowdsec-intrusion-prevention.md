---
title: "CrowdSec 入侵防护指南：为你的 VPS 打造智能安全屏障"
description: "还在用 fail2ban 被动防御？CrowdSec 是新一代协作式入侵防护系统——基于行为分析、全球威胁情报、支持 Docker 和 Nginx 集成。本文详细讲解安装部署与实战配置。"
date: 2026-06-03T10:00:00+08:00
slug: "crowdsec-intrusion-prevention"
tags: ["CrowdSec", "安全", "入侵检测", "IPS", "Docker", "Nginx", "SSH防护", "fail2ban替代"]
categories: ["安全加固"]
image: /images/posts/crowdsec-intrusion-prevention/featured.png
draft: false
aliases: [/zh/post/crowdsec-intrusion-prevention/]
---

你有多久没检查过 VPS 的 `/var/log/auth.log` 了？每天有多少扫描器在试探你的 SSH 端口？你的 Nginx 是否在上报奇怪的 404 请求？

传统的 fail2ban 虽然管用，但它**单兵作战**——每个服务器各自为政，只有本地规则，永远不会知道"隔壁"服务器正在经历什么攻击。而 CrowdSec 带来了根本性的改变：**协作式威胁情报 + 行为分析引擎**。

## 什么是 CrowdSec？

CrowdSec 是一个开源、协作式的入侵防护系统（IPS）。它用 Go 语言编写，轻量高效，继承了 fail2ban 的"封禁 IP"思路，但在架构上做了革命性升级：

| 特性 | fail2ban | CrowdSec |
|------|----------|----------|
| 威胁情报 | 仅本地规则 | 本地 + 全球社区共享 |
| 检测引擎 | 日志正则匹配 | 行为分析 + 场景编排 |
| 封禁方式 | 单机 iptables | 多组件解耦（检测/决策/执行） |
| 扩展性 | 手动写规则 | 丰富的 Hub 插件生态 |
| API 与管理 | 无 | 完善的 REST API + Prometheus 指标 |
| 更新机制 | 静态规则 | 动态规则更新 + 主动防御 |

简单来说：fail2ban 是"挨打了才知道还手"，CrowdSec 是"从社区学习经验，防患于未然"。

## 核心架构

CrowdSec 采用了微服务风格的组件架构：

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│  CrowdSec   │────▶│  Local API   │────▶│  Bouncers    │
│  (检测引擎)  │     │  (LAPI)      │     │  (执行器)    │
└─────────────┘     └──────┬───────┘     └──────────────┘
                           │
                    ┌──────▼───────┐
                    │  CrowdSec    │
                    │   Console    │
                    │  (云端/自托)  │
                    └──────────────┘
```

- **CrowdSec (检测引擎)**：分析日志，运行场景（scenarios），识别攻击行为
- **Local API (LAPI)**：管理封禁决策，提供 API 供 Bouncers 查询
- **Bouncers (执行器)**：实际执行封禁动作（iptables、Nginx deny、Cloudflare API 等）
- **CrowdSec Console**：集中管理面板，可选择云端 SaaS 或自托管

### 与 fail2ban 的关键区别

1. **检测与执行分离**：CrowdSec 只负责检测，封禁由 Bouncer 执行。一个检测引擎可以对接多个不同类型的 Bouncer。
2. **全局威胁情报**：CrowdSec 工具人（称为"信号"）会上报匿名化攻击信息到社区，同时从社区获取最新的攻击 IP 列表。你的服务器越多人用，大家就越安全。
3. **主动防御**：无需等你的日志出现攻击模式——如果一个 IP 在社区中被标记为恶意，它在新服务器上的第一次连接就会被阻止。

## 安装部署

CrowdSec 支持多种安装方式，我推荐 Docker Compose 部署，也支持直接通过包管理器安装。

### 方式一：Docker Compose 部署（推荐）

创建 `docker-compose.yml`：

```yaml
version: "3.8"

services:
  crowdsec:
    image: crowdsecurity/crowdsec:latest
    container_name: crowdsec
    environment:
      - COLLECTIONS=crowdsecurity/linux crowdsecurity/nginx crowdsecurity/http-cve
      - GID=1000
      - UID=1000
    volumes:
      - ./crowdsec/db:/var/lib/crowdsec/data
      - ./crowdsec/config:/etc/crowdsec
      - /var/log:/var/log:ro
      - /var/log/nginx:/var/log/nginx:ro
      - /var/log/auth.log:/var/log/auth.log:ro
    ports:
      - "8080:8080"
    restart: unless-stopped

  crowdsec-bouncer:
    image: crowdsecurity/firewall-bouncer:latest
    container_name: crowdsec-bouncer
    environment:
      - API_URL=http://crowdsec:8080
      - API_KEY=${BOUNCER_API_KEY}
      - DISABLE_IPV6=true
    cap_add:
      - NET_ADMIN
      - NET_RAW
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
    restart: unless-stopped
    depends_on:
      - crowdsec
```

启动服务：

```bash
# 生成 API 密钥
docker run --rm crowdsecurity/crowdsec:latest \
  cscli machines add crowdsec-bouncer --auto \
  -f /dev/stdout

# 启动 CrowdSec
docker compose up -d
```

### 方式二：APT 安装（Debian/Ubuntu）

```bash
# 添加仓库
curl -s https://packagecloud.io/install/repositories/crowdsec/crowdsec/script.deb.sh | sudo bash

# 安装 CrowdSec
sudo apt install crowdsec

# 安装防火墙拦截器
sudo apt install crowdsec-firewall-bouncer-iptables

# 安装 Nginx 拦截器（可选）
sudo apt install crowdsec-nginx-bouncer
```

安装后自动启动，你可以用 `cscli` 查看状态：

```bash
# 查看所有场景
cscli scenarios list

# 查看当前活跃的封禁
cscli decisions list

# 查看日志
cscli alerts list
```

## 关键配置详解

### 采集器（Acquisitions）

CrowdSec 通过 acquisition 文件配置日志源。在 `/etc/crowdsec/acquis.yaml` 中配置：

```yaml
# 采集 Nginx 访问日志
filename: /var/log/nginx/access.log
labels:
  type: nginx

# 采集 Nginx 错误日志
filename: /var/log/nginx/error.log
labels:
  type: nginx

# 采集系统认证日志
filename: /var/log/auth.log
labels:
  type: syslog

# 采集 Docker 容器日志
container_name:
  - nginx
  - postgres
  - wordpress
labels:
  type: docker
```

### 场景（Scenarios）

场景是 CrowdSec 的核心检测逻辑。安装常用场景集合：

```bash
# 安装 Linux 基础防护集合
cscli collections install crowdsecurity/linux

# 安装 Nginx 防护集合
cscli collections install crowdsecurity/nginx

# 安装 HTTP 通用漏洞防护
cscli collections install crowdsecurity/http-cve

# 安装 SSH 暴力破解防护
cscli scenarios install crowdsecurity/ssh-bf
```

每个场景由 YAML 定义，例如 `ssh-bf` 的逻辑是："在 10 秒内同一个 IP 出现 5 次 SSH 认证失败则触发告警"。

### 封禁策略（Profiles）

配置文件 `/etc/crowdsec/profiles.yaml` 定义不同场景的响应策略：

```yaml
name: default_ip_remediation
filters:
  - Alert.Remediation == true && Alert.GetScope() == "Ip"
decisions:
  - type: ban
    duration: 4h
on_success: break

---
name: http_remediation
filters:
  - Alert.Remediation == true && Alert.GetScenario() contains "http"
decisions:
  - type: ban
    duration: 24h
on_success: break
```

你可以为不同类型攻击设定不同封禁时长——SSH 暴力破解封 4 小时，HTTP 攻击封 24 小时，恶意爬虫永久封禁。

## 实战集成

### 与 Nginx 集成（CrowdSec Bouncer）

Nginx Bouncer 作为反向代理模块，在 Nginx 层面拦截恶意请求，比防火墙封禁更精细：

安装 Nginx Bouncer：

```bash
# 使用 Docker 部署 Nginx Bouncer
docker run -d \
  --name crowdsec-nginx-bouncer \
  -e API_URL=http://crowdsec:8080 \
  -e API_KEY=${API_KEY} \
  -p 8081:8080 \
  crowdsecurity/nginx-bouncer:latest
```

在 Nginx 配置中添加：

```nginx
location / {
    proxy_pass http://backend;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    
    # CrowdSec Nginx Bouncer 模块
    # 需要编译时添加 --add-module=/path/to/crowdsec-nginx-bouncer
    crowdsec_bouncer on;
    crowdsec_bouncer_ban_code 403;
    crowdsec_bouncer_mode "live";
}
```

### 与 Docker 容器集成

CrowdSec 的 Docker Bouncer 支持容器级别的网络隔离：

```bash
# 安装 Docker Bouncer
docker run -d \
  --name crowdsec-docker-bouncer \
  -e API_URL=http://crowdsec:8080 \
  -e API_KEY=${API_KEY} \
  -v /var/run/docker.sock:/var/run/docker.sock:ro \
  crowdsecurity/docker-bouncer:latest
```

Docker Bouncer 会自动将恶意 IP 加入 Docker 网络的黑名单，所有关联容器同时受保护。

### 集成 Cloudflare

如果你的站点使用 Cloudflare CDN，可以配置 CrowdSec 通过 Cloudflare API 封禁 IP：

```yaml
# /etc/crowdsec/bouncers/cloudflare.yaml
type: cloudflare
api_token: YOUR_CLOUDFLARE_API_TOKEN
mode: "block"
zones:
  - yourdomain.com
```

### 保护 SSH 服务

最经典也最实用的场景——保护 SSH 免遭暴力破解：

```bash
# 确认 SSH 日志已采集
cscli metrics

# 查看 SSH 攻击事件
cscli alerts list --type ssh

# 查看被封禁的 IP 详情
cscli decisions inspect <IP_ADDRESS>
```

你可以结合 `fail2ban` 时代的经验：设置了密钥登录的服务器仍然需要 CrowdSec，因为它可以防御针对 Nginx、WordPress 等其他服务的攻击。

## 监控与管理

### 命令行管理（cscli）

```bash
# 查看所有告警
cscli alerts list

# 查看封禁记录
cscli decisions list

# 手动封禁 IP
cscli decisions add --ip 1.2.3.4 --duration 24h

# 手动解封 IP
cscli decisions delete --ip 1.2.3.4

# 查看系统状态
cscli metrics

# 更新 Hub 插件
cscli hub update
cscli collections upgrade crowdsecurity/linux
```

### CrowdSec Console

CrowdSec Console 提供 Web 管理界面，可以直观地查看：

- 实时攻击地图
- 告警趋势图
- 各服务器的安全状态
- 全局威胁情报统计

注册地址：https://app.crowdsec.net/

也可以自托管 Console（推荐在独立 VPS 上部署）。

### 集成 Prometheus

CrowdSec 原生暴露 Prometheus 指标：

```yaml
# docker-compose.yml 中启用
environment:
  - PROMETHEUS_ENABLED=true
```

Grafana 面板 ID：`15097`（CrowdSec Official Dashboard）

## 性能与资源占用

CrowdSec 以轻量著称，实测数据：

| 资源 | 占用情况 |
|------|---------|
| CPU | 空闲 < 1%，峰值 < 5% |
| 内存 | ~80-150 MB |
| 磁盘 | ~200 MB（含 IP 数据库）|
| 日志处理延迟 | < 100ms |

在一台 2 核 4GB 的 VPS 上运行 CrowdSec，几乎不会对现有服务造成任何影响。

## 进阶技巧

### 自定义场景

假设你想检测某个应用特有的攻击模式，可以编写自定义场景：

```yaml
# /etc/crowdsec/scenarios/myapp-bf.yaml
type: leaky
name: myapp/bruteforce
description: "Detect brute force on myapp login"
filter: "evt.Meta.log_type == 'myapp_failed_auth'"
leaky:
  capacity: 5
  leak_speed: "10s"
groupby: evt.Meta.source_ip
labels:
  service: myapp
  confidence: 3
  classification:
    - attack.bruteforce
```

### 白名单管理

放行信任 IP（如监控服务器、跳板机）：

```yaml
# /etc/crowdsec/parsers/s02-enrich/whitelist.yaml
name: crowdsecurity/whitelists
description: "Whitelist trusted IPs"
whitelist:
  reason: "Trusted IPs"
  ips:
    - 192.168.1.0/24
    - 10.0.0.0/8
  expressions:
    - "'my-company-vpn' in evt.Meta.service"
```

### 多服务器部署

在多台 VPS 上，可以让所有服务器共享同一个 LAPI：

```
VPS-A (CrowdSec + Bouncer)
    │
    ├──▶ LAPI (主节点)
    │
VPS-B (CrowdSec + Bouncer)
    │
    ├──▶ LAPI (同上)
    │
VPS-C (CrowdSec + Bouncer)
    │
    └──▶ LAPI (同上)
```

所有服务器共享封禁决策——A 服务器发现了攻击 IP，B 和 C 服务器自动同步封禁。

## 常见问题

**Q: CrowdSec 会不会误封正常用户？**
A: CrowdSec 的阈值设计比较保守，默认场景误报率很低。如果你发现误封，可以通过白名单放行，或调整场景参数。

**Q: 可以和 fail2ban 同时使用吗？**
A: 可以，但不推荐。两者会独立封禁，导致 iptables 规则膨胀。建议迁移后卸载 fail2ban。

**Q: 使用 CrowdSec 需要注册账号吗？**
A: 不强制注册。但注册后可以获得云控制台和全局威胁情报服务，极大提升防护效果。免费版的社区情报已经足够日常使用。

**Q: 每天产生多少流量？**
A: CrowdSec 的信号上报非常轻量，每天仅几 KB，几乎可以忽略不计。

## 总结

CrowdSec 代表了现代服务器安全的发展方向：从"单机被动防御"到"协作式主动防御"。它并不复杂，但带来的安全提升是质的飞跃。

如果你的 VPS 还没有部署任何入侵防护系统——**从今天开始，就用 CrowdSec 代替传统的 fail2ban**。如果已经在用 fail2ban，迁移到 CrowdSec 只需要三十分钟。

最后提醒：安全是一个持续的过程，任何工具都不能一劳永逸。定期更新规则、关注告警、审查封禁记录，才能让你的 VPS 真正固若金汤。

---

*下一篇我们将介绍 CrowdSec 的高级用法——如何与 WAF（Web 应用防火墙）联动，构建多层安全防护体系。*
