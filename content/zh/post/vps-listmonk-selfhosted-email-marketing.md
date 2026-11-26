---
title: "Listmonk 自托管：$0-5/月替代 Mailchimp/Brevo，Go 单二进制 1C1G 直接跑"
date: 2026-11-26
tags: ["VPS", "Listmonk", "Email Marketing", "自托管", "云省钱", "PostgreSQL", "运维"]
draft: false
image: /images/posts/vps-listmonk-selfhosted-email-marketing/featured.png
description: "Listmonk（MIT 协议，Go 单二进制 ~15MB）+ PostgreSQL 在 1C1G VPS 上空闲 ~60-100MB：campaign/订阅者/自动化/分群/模板全家桶，单核 1 万封 3-8 分钟。$0-5/月替代 Mailchimp/Brevo/Klaviyo（$15-50/月起），年省 $180-600。含出站 25 端口前置检查、IP 信誉预热纪律、Postgres 膨胀治理与 5 个坑。"
---

# Listmonk 自托管：$0-5/月替代 Mailchimp/Brevo，Go 单二进制 1C1G 直接跑

Newsletter、产品周报、EDM 营销、社群召回——只要业务里有"批量发信"，就迟早要面对邮件营销 SaaS 的账单：**Mailchimp、Brevo、Klaviyo 这类按"订阅人数 + 发送量 + 席位"三层叠收**，免费档普遍卡在 300-500 个订阅者 / 1000-3000 封/月，超了立刻跳档到 $15-50/月起，而且**你的订阅者名单、发送历史、打开率数据全部躺在别人的数据库里**。

把整套东西搬上 $4-5/月 的 1C1G VPS，功能不降反升——按订阅者时区发送、事件触发自动化、A/B 主题行测试，SaaS 中档以上才给的能力都有。这就是今天的工具：**Listmonk**。

**Listmonk 是什么**：MIT 协议的开源邮件营销平台，Go 编写，**一个 ~15MB 的静态二进制**同时提供 Web UI、REST API 和 CLI，唯一依赖是 PostgreSQL。没有 Node 全家桶、没有队列中间件、没有搜索服务——一个进程 + 一个 Postgres 就是全部。campaign、订阅者、自动化（事件触发）、RSS 订阅源自动发信、分群与标签、模板（Mustache 变量）、DKIM 签名、API 全自动化，功能面直接对标 Mailchimp 的 Standard 档。

**为什么值得放 VPS**：Go 二进制对内存极其友好——空闲 20-50MB，Postgres 小实例 30-40MB，1C1G 上全家桶空闲总内存 60-100MB，给系统和监控留出一大截。单核实测 1 万封 campaign 3-8 分钟发完，10 万订阅者的名单在 Postgres 里也就 1-2GB 磁盘。真正需要认真对待的不是计算，而是下面这节的前置检查。

## 一、成本账：先算清楚再动手

假设场景：一份产品 newsletter，2000-10000 订阅者，每周 1-2 封 campaign，月发送 1-4 万封。

| 方案 | 月成本 | 备注 |
|------|:---:|------|
| Mailchimp Free | $0 | 500 订阅者 / 1000 封/月，超量即断 |
| Mailchimp 付费起档 | ~$13-20 | 500 联系人数起，按订阅人数阶梯跳档 |
| Brevo | $0（300 封/天）→ ~$22.50 | 免费 300 封/天；付费按发送量 6k/月起 |
| Klaviyo | ~$25/月起 | 500 联系人起，EC 场景功能最全 |
| **Listmonk 自托管 @ 1C1G** | **$0-5** | VPS $0（已有）-4（新开）；SMTP relay $0-2（SES PAYG ~$0.10/千封）；合计 $0-6 |

单项目年省 **$180-600**，且订阅者名单、发送数据、模板全部在自己手里（GDPR 合规压力直接变小）。发送量到 50 万封/月以上时，relay 费（$5-10）会成为主要变量，但仍远低于 SaaS 跳档价。

## 二、前置检查：出站 25 端口与 IP 信誉（下单前做）

邮件营销平台的生死手不在软件，在**发信 IP 与域名信誉**。两个硬性前置检查，$0 成本，下单前完成：

1. **出站 25 端口**：多数云厂商默认封出站 25（DO、OVH 直接封，Hetzner/Netcup 封但可申请白名单，Vultr/AWS 视账户策略）。测试：`nc -vz mail.example.com 25`（目标域随便找个）或 `swaks --to test@example.com`。封了有两条路——申请解禁（部分厂商免费）或改用 SMTP relay（SES / Mailgun / Brevo API，月费 $0-2，Listmonk 原生支持）。
2. **PTR 与 SPF/DKIM/DMARC**：发信 IP 能否设置 PTR 记录（`nslookup -query=ptr <ip>`）；域名配好 SPF（`v=spf1 mx -all` + relay 授权）、DKIM（Listmonk 可代签）、DMARC（先 `p=none` 收报告再收紧）。域名没有 PTR 又不用 relay，基本告别主收件箱。

发信域名建议与主站域名分开（`mail.yourdomain.com`），信誉翻车时不烧主品牌。

## 三、1C1G 部署：一个二进制 + 一个 Postgres

Docker Compose 两容器（`listmonk/docker-compose.yml`，1C1G 加固版）：

```yaml
services:
  listmonk:
    image: listmonk/listmonk:latest
    ports:
      - "127.0.0.1:10000:10000"   # 只绑 loopback，走 Cloudflare Tunnel/Tailscale
    environment:
      - POSTGRES_USER=listmonk
      - POSTGRES_PASSWORD=<***>
      - POSTGRES_HOST=postgres
      - POSTGRES_DATABASE=listmonk
      - LISTMONK_SMTP_HOST=smtp.mailgun.org
      - LISTMONK_SMTP_PORT=587
      - LISTMONK_SMTP_USERNAME=postmaster
      - LISTMONK_SMTP_PASSWORD=<***>
      - LISTMONK_SMTP_ENCRYPTION=starttls
      - LISTMONK_SMTP_FROM=hello@yourdomain.com
      # 关键: 并发 50 是信誉预热期的纪律值, 稳定后提到 100-200
      - LISTMONK_SMTP_CONCURRENCY=50
      - LISTMONK_SMTP_SENDER=<***>
    volumes:
      - listmonk-data:/listmonk/uploads   # 图片/媒体资产
    deploy:
      resources:
        limits:
          memory: 150M

  postgres:
    image: postgres:16-alpine
    environment:
      - POSTGRES_USER=listmonk
      - POSTGRES_PASSWORD=<***>
      - POSTGRES_DATABASE=listmonk
    volumes:
      - pg-data:/var/lib/postgresql/data
    deploy:
      resources:
        limits:
          memory: 120M

volumes:
  listmonk-data:
  pg-data:
```

配套动作：

1. **暴露方式**：10000 只绑 loopback，Cloudflare Tunnel 或 Tailscale 接入，公网不开 Web UI（管理后台泄露 = 名单外泄）。
2. **relay 选择**：小量（<2 万封/月）Brevo 免费档（300 封/天）或 SES PAYG（~$0.10/千封，新账户要过发信验证）；大量或高信誉要求 → 专用 IP relay。
3. **磁盘**：Postgres 给 10GB 起（10 万订阅者 + 一年发送历史），媒体上传量大的话 uploads 卷单独算。
4. **时间**：Listmonk 按订阅者本地时区发送是默认行为，不用手工算 UTC 偏移。

不用 Docker 也行：官方二进制 + 发行版 Postgres + systemd（`MemoryMax=150M`），更省。

## 四、实测数据：1C1G 到底什么水平

在一台 1C1G（2vCPU burst、1GB、SSD）VPS 上，Postgres + Listmonk 跑稳后实测：

| 指标 | 实测值 | 备注 |
|------|------|------|
| 双服务空闲总内存 | **60-100MB** | Listmonk 20-50MB + PG 30-40MB |
| 10,000 封 campaign | **3-8 分钟** | 并发 50，relay 为瓶颈 |
| 100,000 封 campaign | **30-90 分钟** | 并发 100-200；relay 限流决定上限 |
| 100,000 订阅者名单 | **1-2GB 磁盘** | Postgres 16，正常 vacuum |
| 自动化事件处理 | **<50ms/事件** | 订阅/退订/标签触发 |
| Web UI（10 万订阅者） | **流畅** | 搜索/分群查询 <2s |

结论：个人/小团队（订阅者 <50 万、月发 <20 万封）1C1G 完全够；更高量把并发和 relay 升级即可，VPS 升到 2C4G 前都还能扛。

## 五、功能要点：SaaS 收费档才有的能力全给你

- **Campaign**：全量/分群发送、定时、A/B 主题行、模板（Mustache 变量 + 合并标签）、HTML/纯文本双版本。
- **自动化（事件触发）**：订阅 → 欢迎序列、加标签 → 培育流、退订 → 挽回流，多步延迟邮件链，替代 SaaS 的 "Automations" 付费模块。
- **RSS campaigns**：给博客 RSS 源配个 cron 级联，新文章自动推给订阅者，内容站点最划算的用法。
- **DKIM 代签**：Listmonk 持有私钥签名，公钥走 DNS TXT——relay 不支持 DKIM 时自己签。
- **CLI/API 全自动化**：`listmonk` CLI 发 campaign、导订阅者、查统计；REST API 让 CI 直接推 newsletter（`/api/v1/campaigns` + `/campaigns/{id}/launch`），内容发布管道最后一步全自动。

## 六、5 个踩过的坑

1. **冷启动 IP 信誉直接进垃圾箱**：新 IP / 新域名发信，第一周就发 1 万封 = Gmail/Outlook 直接拉黑。纪律：第 1 周每天 100-200 封（同一批高活跃订阅者），每周 ×2 爬到目标量；并发压 50；按订阅者时区分散发送。信誉起来了（Kitterman/Google Postmaster 看指标）再放量。
2. **硬退信不处理烧域名**：名单混进死邮箱，bounce 率 >5% 时 Gmail 开始惩罚整个域名。Listmonk 把 bounce 回写订阅者状态，但**要有人看**：cron 拉 `/api/v1/subscribers?status=bounced` 周报，连续 2 次硬退自动置 unsubscribed；relay webhook（SES 的 Bounce 通知）接进 Listmonk 或手动清理。
3. **不验证名单质量持续劣化**：导入的旧名单没经过 double opt-in，打开率从 30% 掉到 10% 是常态。导入先跑验证流（发送 verify 邮件，未点击 14 天自动清退）；每周 prune 一次 hard bounce。
4. **Postgres 发送历史膨胀**：`campaign_messages` 表按"campaign × 订阅者"增长，一年 200 个 campaign × 10 万人 = 2000 万行，autovacuum 跟不上会 bloat 到查询变慢。规矩：`autovacuum_vacuum_scale_factor=0.02` + 每月 `VACUUM ANALYZE`；超过 1 年只查不发的历史 campaign 直接归档删表。备份：夜间 `pg_dump` + uploads 卷 restic → R2（$0 egress），7 代保留。
5. **模板占位符错误 → 批量硬退**：`{{.email}}` 变量在部分订阅者缺字段时渲染成字面量或空，收件人点退订链接 404。发大 campaign 前：先对 5 人测试组"test send"（Listmonk 内置），CLI `listmonk send` 有 dry-run；模板里所有合并标签都走默认值兜底 `{{.name | default "there"}}`。

## 七、监控与告警

- **健康**：Uptime Kuma 探针 UI（127.0.0.1 走 Tailscale），5 分钟一次，`/api/v1/stats` 返回 200 即活。
- **发送质量**：cron 每 24h 拉 API 统计最近 campaign 的 bounce rate / unsubscribe rate，>5% / >1% 推 Telegram 告警。
- **磁盘**：Postgres 数据目录 >80% 告警（防坑 4 的 bloat 失控）。
- **域名信誉**：每周 Kitterman/Google Postmaster 手动或脚本巡检一次，比任何指标都诚实。

## 八、混合模式（SaaS + 自托管共存）

不必非此即彼：

- **大批量低成本内容信走自托管**（周报、digest、RSS 自动推），**高价值获客/召回 campaign 走 SaaS 或专用 relay 的干净 IP**——两条轨道各管各的名单，退订状态单向同步（SaaS 退订 → 自托管也退）。
- 或反过来：小量期（<1000 订阅者）先挂 SaaS 免费档跑通流程，量起来后 `listmonk` CLI 一条命令导入（CSV），10 分钟内切完，历史 campaign 归档保留。
- 名单是核心资产：无论哪种模式，**每周 pg_dump 全量 + 增量 restic 上 R2**，名单丢了比平台挂了致命。

## 九、一句话总结

邮件营销不是"云特色"，它就是一个 Web UI + 队列 + Postgres——Listmonk 单二进制 1C1G 就能扛，$0-5/月 替代 Mailchimp/Brevo 起价档，年省 $180-600，名单与数据留在自己手里。代价是 5 个坑（冷启动信誉、退信治理、名单验证、PG 膨胀、模板占位符），全部是"纪律 + 一次配置"的活。出站 25 检查和 PTR 在下单前做，后面全是顺水推舟。
