---
title: "VPS 自托管 Stalwart：$0 月费自建邮件服务器，替代 Google Workspace"
date: 2026-11-19
tags: ["VPS", "Stalwart", "邮件", "自托管", "云省钱", "DKIM", "DMARC", "运维"]
draft: false
image: /images/posts/vps-stalwart-selfhosted-mail-server/featured.png
description: "1C1G VPS 上跑 Stalwart（单 Rust 二进制，空闲 ~95MB）：SMTP+IMAP+JMAP+CalDAV/CardDAV 全家桶，内置 SPF/DKIM/DMARC 校验与 Let's Encrypt，$0 替代 5 用户 Google Workspace（$35-70/月），年省 $430-840。含 25 端口/rDNS 前置检查、DNS 全配置、8 周暖机纪律与 5 个坑。"
---

# VPS 自托管 Stalwart：$0 月费自建邮件服务器，替代 Google Workspace

邮件是"自托管"清单里最常被跳过的一项：网盘有 Syncthing，搜索有 SearXNG，监控有 Uptime Kuma，但邮箱几乎人人都在用 Google/微软——因为自建邮件服务器"很难"的口碑已经流传了十几年。真正难的其实只有三件事：25 端口可达、rDNS 可设、送达率纪律。把这三件事前置检查做掉，剩下的就是一个 ~95MB 内存的单二进制。

**Stalwart**（Rust 写的现代邮件服务器，Apache-2.0）把这件事的成本打到了地板上：

- **单二进制、无 JVM 无依赖**：SMTP（25/465/587）+ IMAP（143/993）+ JMAP（443）+ CalDAV + CardDAV 一个进程全包，空闲内存 ~95MB，1C1G 直接塞得下；
- **内置一切合规件**：SPF/DKIM/DMARC/ARC 校验、Let's Encrypt 自动签发、内容过滤器，不用旁边再挂一堆小服务；
- **REST 管理 API**（JSON over 127.0.0.1:8081）：建域、建用户、取 DKIM 公钥全部 curl 搞定，适合脚本化部署，不依赖 Web UI；
- **数据全在自己手里**：邮箱、日历、联系人都在你的 VPS 盘上，配合 restic 夜备到 R2（出口费 $0），离职/停订/涨价都不影响。

5 个用户的 Google Workspace 年付约 $35-55/月（$7-12/用户），M365 Business 约 $30/月起。落到一台已有（或新开 ~$4/月）的 1C1G VPS 上，**$0-5/月，年省 $430-840**。

## 一、成本账：先算清楚再动手

假设场景：5 人小团队/家庭共享，每人 5-20GB 邮箱 + 日历 + 联系人，当前方案是托管邮箱 SaaS。

| 方案 | 5 用户月成本 | 数据位置 | 备注 |
|------|:---:|:---:|------|
| Google Workspace Starter | $35-45 | 厂商云 | 年付 $7/用户；月付上浮 ~30% |
| Google Workspace Standard | $70-90 | 厂商云 | $14/用户年付，含 25GB 每人 |
| M365 Business Basic | $30-40 | 厂商云 | $6/用户，含 Teams/SharePoint 全家 |
| Zoho Mail | $5-30 | 厂商云 | 最便宜的 SaaS 备选，仍非自有 |
| **Stalwart @ 1C1G VPS** | **$0-5** | 自有 VPS | VPS 本来就有则 $0；新开机型 $4-5 |

**年省 $430-840**（5 用户），且没有 5TB 共享盘、无锁定、可整体 restic 备份带走。

**边界要说清**：自建邮件 ≠ 100% 进收件箱。送达率是"运维纪律"不是"功能"——下面第五节的 25 端口/rDNS 前置检查和 8 周暖机纪律，不做到就只能走第七节的混合模式。

## 二、原理：为什么单二进制能扛起邮件全家桶

传统邮件栈是 Postfix + Dovecot + OpenDKIM + Amavis + Rspamd + ACME 客户端……六个组件、五份配置、四个故障域。Stalwart 的思路是**一个 Rust 进程 + 一套配置 + 一个 REST API**：

| 协议 | 端口 | 用途 |
|------|:---:|------|
| SMTP 入站 | 25 | 其他邮件服务器投递给你 |
| Submission | 587 / 465 | 你的客户端发信（需认证） |
| IMAP | 143 / 993 | 所有成熟客户端读信 |
| JMAP | 443 (HTTP/2) | 现代移动读信协议，比 IMAP 省 60%+ 流量 |
| CalDAV / CardDAV | 443 | 日历/联系人，iCal 客户端直连 |
| 管理 API | 127.0.0.1:8081 | JSON REST：域/用户/DKIM/证书 |

关键设计点：

- **内置键值存储**：小规模（几十用户、百 GB 内）不需要外部数据库；上量后切 Postgres/MySQL 后端，配置热切换；
- **ACME 内建**：Let's Encrypt 证书自动申请/续期，443 上的 JMAP/CalDAV 直接 HTTPS，不用 Caddy/Nginx 反代；
- **JMAP 对 1C1G 很友好**：无状态的 HTTP/2 批量同步，客户端拉 1000 封邮件比 IMAP 全量 IDLE 轮询省一个数量级的带宽与 CPU。

## 三、架构：一台 VPS 上的四个角色

```
 [Thunderbird / Apple Mail / 手机 IMAP] ──993──▶ ┌─────────────────────┐
 [本机脚本 / CI 发信]          ──587──▶ │  Stalwart (1 个进程)      │
 [Gmail/其他域 MTA]            ──25 ──▶ │  SMTP+IMAP+JMAP+CalDAV   │
 [iOS/Android 省电读信]        ──443──▶ │  内置 ACME/SPF/DKIM/DMARC │
 └─────────────────────────────┬─────────┘
              127.0.0.1:8081 │ REST 管理 API（仅回环）
              ┌──────────────▼──────────────┐
              │ curl 自动化：建域/建用户/     │
              │ 取 DKIM 公钥/查证书          │
              └──────────────┬──────────────┘
 [restic nightly] ──加密────▶ [R2 对象存储 $0 出口]（异地副本）
 [Uptime Kuma]    ──探测────▶ IMAP 登录 / SMTP EHLO / JMAP ping
```

管理 API 只绑回环，外部访问走 Cloudflare Tunnel 零信任入口（见 [Cloudflare Tunnel 零信任访问](/post/vps-cloudflare-tunnel-zero-trust/)），8081 永远不对公网开放。

## 四、部署：systemd + DNS 全配置

### 0. 前置检查（最重要，买机器之前做）

自建邮件的 90% 失败发生在买完机器之后才发现端口不通。两项硬性前置：

```bash
# 1) 25 出站：从【另一台机器】测试目标 VPS 的 25（入站）+ 目标 VPS 测外部 25（出站）
nc -vz mail.example.com 25 -w 5        # 入站
# 在 VPS 上：nc -vz gmail-smtp-in.l.google.com 25 -w 5   # 出站

# 2) rDNS：IP 能否设 PTR 且 dig -x 生效
dig -x YOUR_IP +short
```

DigitalOcean / Vultr / AWS 默认**封锁 25 出站**（工单不一定批、批了也可能再封）；Hetzner、Netcup、OVH（工单开通）默认开放。**没有"25 可达 + 专用 IP + 可设 rDNS"的 VPS，直接进第七节混合模式，别硬刚。**

### 1. 安装（固定版本，systemd 托管）

```bash
sudo useradd -r -s /usr/sbin/nologin stalwart
sudo mkdir -p /etc/stalwart /var/lib/stalwart /var/log/stalwart
VER=v2026-05; ARCH=amd64
curl -fsSLO "https://stalw.art/install/${VER}/stalwart-mysql-${ARCH}.tar.gz" \
  && tar xzf stalwart-mysql-${ARCH}.tar.gz -C /usr/local/bin

sudo cat > /etc/systemd/system/stalwart.service <<'EOF'
[Unit]
Description=Stalwart Mail Server
After=network-online.target
[Service]
User=stalwart
ExecStart=/usr/local/bin/stalwart
RuntimeDirectory=stalwart
MemoryMax=512M
CPUQuota=75%
Restart=on-failure
[Install]
WantedBy=multi-user.target
EOF
sudo systemctl enable --now stalwart
```

`MemoryMax=512M` 给足余量：空闲 ~95MB，大附件批量收信时可能冲到 200-300MB。

### 2. 最小配置（内置存储 + ACME + DKIM 自动生成）

`/etc/stalwart/config.toml` 核心段：

```toml
server.type = "main"
server.bind = ["0.0.0.0:25", "0.0.0.0:143", "0.0.0.0:465", "0.0.0.0:587", "0.0.0.0:443"]
tls.letsencrypt.domain = "mail.example.com"

dkim = { enabled = true, auto = true, ttl = 30 }          # 建域时自动生成密钥
admin.bind = "127.0.0.1:8081"                              # 管理 API 仅回环
store.type = "builtin"                                      # 小规模免 DB
store.path = "/var/lib/stalwart"
```

### 3. DNS 记录（五件套一次配齐）

| 类型 | 主机 | 值 |
|------|------|-----|
| A | mail.example.com | VPS_IP |
| MX | example.com | 10 mail.example.com |
| TXT | example.com (SPF) | `v=spf1 ip4:VPS_IP -all` |
| TXT | mail._domainkey.example.com | 下方 curl 取回的公钥 |
| TXT | _dmarc.example.com | `v=DMARC1; p=none; rua=mailto:dmarc@example.com; pct=100` |

PTR（rDNS）不在 DNS 面板——向 VPS 提供商申请 `VPS_IP → mail.example.com`。

### 4. 建域 + 取 DKIM 公钥发布

```bash
ADMIN=http://127.0.0.1:8081
curl -s -X POST "$ADMIN/config/set" -H 'content-type: application/json' \
  -d '{"path":["domain","example.com"],"data":{"enabled":true,"dkim":{"auto":true}}}'
curl -s -X POST "$ADMIN/user/example.com/you" -d '{"password":"..."}'

# 取 DKIM 公钥 → 发布为 TXT 记录 mail._domainkey.example.com
curl -s "$ADMIN/dkim/example.com/mail/public"
```

### 5. 验证（三项全绿再开客户端）

1. **mail-tester.com**：发一封给自己，目标 ≥9/10；
2. **MXToolbox**：SPF/DKIM/DMARC/PTR/MX 逐项 pass；
3. **三端实收**：Gmail / Outlook / Apple Mail 各发一封，确认进**收件箱**而非垃圾邮件。

### 6. 客户端参数

| 项目 | 值 |
|------|-----|
| IMAP | mail.example.com:993/SSL，账号=全邮箱地址 |
| SMTP 发信 | mail.example.com:587/STARTTLS，同上 |
| CalDAV | https://mail.example.com/dav/calendar/ |
| JMAP | https://mail.example.com/jmap/（新客户端优先选它，省电省流量） |

## 五、监控：Prometheus + Uptime Kuma + 每周体检

邮件故障最阴险的形态是**静默**：你被加进 Spamhaus 后，发信照发、对端照收、只是悄悄进垃圾箱——不看监控永远不会知道。

- **Prometheus textfile**：Stalwart 管理 API 暴露 `/metrics`，每 5 分钟 curl 一次落 textfile 目录，Prometheus 抓取。三条告警：
  - `stalwart_smtp_rejects{type="greylist"}` 或投递失败率 >2/小时 → P1；
  - 每周 Spamhaus API 查询命中 SBL/XBL → 立即电话级告警；
  - 数据盘 >80% → P2（邮箱膨胀是磁盘杀手）。
- **Uptime Kuma** 三探测（[部署参考](/post/vps-uptime-kuma-monitoring/)）：IMAP 登录、SMTP `EHLO`、JMAP `capabilities` ping，任一失败推 **Gotify**（[参考](/post/vps-gotify-selfhosted-realtime-alerts/)）；
- **每周 cron 体检**：mail-tester + 三大黑名单查询，结果进 Loki（[日志聚合参考](/post/vps-loki-selfhosted-log-aggregation/)），分数 <7/10 自动告警。

## 六、5 个坑（都踩过）

1. **先开机后检查 25 端口/rDNS**：DO/Vultr 工单开 25 是"概率事件"，有的区域永久封。买机器前跑第四节的 nc/dig 检查，不达标换家——这是唯一无法事后补救的一项。
2. **暖机期冲量**：新 IP 第一周发 10 封/天到真实活跃收件人，每 7 天翻一倍，8 周达标。**任何营销邮件、群发、加到陌生列表的行为，都会让域名进 SBL/XBL，恢复以周/月计**；暖机域与正式域分开。
3. **自动转发烧掉送达率**：Gmail 投诉率红线 ~0.3%、Outlook ~0.1%，一次无效转发风暴就能触顶。关闭 catchall，转发前校验收件地址可解析（MX 查询），失败走 NDR 队列人工处理。
4. **数据只在 VPS 本地盘**：内置存储 = 一个目录。VPS 挂了邮箱就没了。restic 每晚增量 + R2 异地副本（2-1-1 策略，[参考](/post/vps-restic-s3-six-layer-encryption-2-1-1-backup/)），R2 出口 $0。
5. **只看流量不看送达**：SMTP 220 响应正常 ≠ 进收件箱。靠第五节的 Kuma 三探测 + 每周 mail-tester cron + 黑名单告警兜底，而不是"感觉还能收信"。

## 七、实测数据与成本总结

在 1C1G（1GB RAM / 40GB 盘 / 500Mbps）实测：

| 指标 | 数值 |
|------|------|
| 空闲内存（builtin 存储） | ~95MB |
| 启动时间 | ~1.5s |
| 空闲 CPU | <1%（1C） |
| 1000 封小邮件入站接收 | 2-4s |
| JMAP 同步 1000 封（移动端） | 200-400ms |
| 2GB 邮箱 + 500 日历事件 | 无压力 |

**成本总结**：5 用户 Google Workspace/M365 $30-90/月 → Stalwart @ 既有 VPS **$0/月**（新开机型 $4-5/月），年省 **$430-840**；换来的是邮箱/日历/联系人数据全部自有、无订阅锁定、可整体加密备份带走。

**混合模式（过不了前置检查的退路）**：保留 1 个 $1-7/用户的 SaaS 邮箱**只做发信中继**，收信/存储全走自建 IMAP/JMAP——数据主权照样拿到，送达率交给 SaaS，仍省 80% 以上。

**边界再说一遍**：自建邮件的价值是"数据自有 + $0 订阅"，不是"营销冷邮件渠道"。做 cold outreach / 营销群发的，别用主域名自托管发信——送达率纪律兜不住商业发送量，那条路请走专业邮件服务商。

> 相关：[Restic 6 层加密备份 + 2-1-1 策略](/post/vps-restic-s3-six-layer-encryption-2-1-1-backup/)（邮箱数据异地副本）、[VPS 自托管 Loki](/post/vps-loki-selfhosted-log-aggregation/)（邮件服务日志聚合）、[Uptime Kuma 监控](/post/vps-uptime-kuma-monitoring/)（三探测兜底）、[Cloudflare Tunnel 零信任](/post/vps-cloudflare-tunnel-zero-trust/)（管理 API 入口）。
