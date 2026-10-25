---
title: "在 VPS 上自建 Dnsmasq + dnsmasq-china-list：一份跑得又快又准的本地 DNS 体验"
description: "公共 DNS 慢、污染、隐私不可控？本文在 1 核 512MB 的小 VPS 上从零搭建 Dnsmasq 递归缓存 + 国内域名分流，含 dnsmasq-china-list 自动更新、DNSSEC 校验、缓存调优、systemd 加固与 Prometheus 指标，实测把平均解析耗时压到 3ms 以内，内存占用不到 40MB。"
date: 2026-10-25T10:30:00+08:00
lastmod: 2026-10-25T10:30:00+08:00
slug: "vps-selfhosted-dnsmasq-china-list"
image: "/images/posts/vps-selfhosted-dnsmasq-china-list/featured.png"
tags: ["DNS", "Dnsmasq", "VPS", "自托管", "网络优化", "DNSSEC", "缓存", "运维"]
categories: ["网络与基础设施"]
aliases: ["/zh/post/vps-selfhosted-dnsmasq-china-list/"]
draft: false
---

## 引言：你每天要等几百次 DNS 查询

打开一个网页，平均触发 15～30 次 DNS 查询：主域、CDN、埋点、字体、API 子域。每次查询如果走公共 DNS 花掉 30ms，一次页面加载就被硬生生拖慢将近一秒；如果遇上被污染的域名，你得到的是一个错误的 IP，然后看着连接超时。

很多人把 DNS 当成「配好就不管」的基础设施，但它是整条链路里**最容易优化、收益最直接**的一环。本文在台 1 核 512MB 的 VPS 上从零搭一套本地 DNS：

- **Dnsmasq** 做递归缓存 + 分流，纯 C 写的小巧实现；
- **dnsmasq-china-list** 提供国内域名清单，国内域名走国内上游，其余走加密/干净的海外上游；
- **DNSSEC 校验** 挡住伪造应答；
- **systemd 加固** + 直接 `bind` 在 `53`，不跑在 Docker 里（省一层 NAT，也省一份复杂度）；
- **Prometheus 文本导出** 让你看到缓存命中率和上游延迟。

结论先给：**缓存命中时延 0.2～0.4ms，整体平均 2.7ms，常驻内存 32MB，单核负载可忽略**。

---

## 一、为什么是 Dnsmasq，不是 Unbound / CoreDNS

三者都能做本地 DNS，取舍很清楚：

| 方案 | 递归能力 | 分流复杂度 | 内存 | 适合场景 |
|---|---|---|---|---|
| **Dnsmasq** | 需转发上游（可叠加 `unbound` 做真递归） | 极低，`server=/cn/1.1.1.1` 一行 | ~30MB | 单机分流 + 缓存，本文选择 |
| Unbound | 原生递归，DNSSEC 完整 | 中等，需 `forward-zone` 多段 | ~60MB | 追求纯递归、无第三方上游 |
| CoreDNS | 需插件组合 | 中等，要写 Corefile + hosts 插件 | ~80MB | 多实例/集群、K8s 环境 |

对单台 VPS 来说，**我们要的是「快 + 分流 + 好维护」**，而不是「纯递归」。Dnsmasq 在这一档几乎没有对手：配置十几行、热重载不丢缓存、`SIGHUP` 即生效。

> 如果你坚持完全自主递归（不接受任何上游），文末「进阶」一节给了 Unbound 叠加方案，Dnsmasq 只做缓存与分流前端。

---

## 二、整体架构

```
                    ┌──────────────────────────────────────────┐
   LAN / 本机应用    │  VPS  (1 vCPU / 512MB)                    │
   ┌───────────┐    │                                          │
   │ app / curl│───▶│  dnsmasq :53  (bind 127.0.0.1 + 内网 IP)  │
   └───────────┘    │      │                                   │
                    │      ├─ 缓存命中 ──▶ 直接应答 (<0.5ms)     │
                    │      │                                   │
                    │      ├─ 域名 ∈ china-list ──▶ 223.5.5.5  │
                    │      │                      119.29.29.29 │
                    │      │                                   │
                    │      └─ 其余域名 ──▶ 1.1.1.1 / 9.9.9.9  │
                    │                        (DoH 上游更佳)     │
                    │                                          │
                    │  china-list 定时同步 (systemd timer)      │
                    │  metrics exporter :9100 (textfile)       │
                    └──────────────────────────────────────────┘
```

三层职责：

1. **缓存层**：`cache-size=10000`，命中即答，这是 90% 收益的来源；
2. **分流层**：`server=/domain/upstream` 语法，国内域名精准走国内 DNS，避免「被引导到香港节点再回来」；
3. **校验层**：`dnssec` 让上游返回带签名，Dnsmasq 用内置信任锚验证（需上游支持，Cloudflare/Google 支持，DNSPod 部分支持）。

---

## 三、安装与最小可用配置

Debian 12 / Ubuntu 24.04：

```bash
sudo apt update
sudo apt install -y dnsmasq dnsutils curl jq

# 阻止 apt 自动拉起的 systemd-resolved 抢 53 端口
sudo systemctl disable --now systemd-resolved
sudo rm -f /etc/resolv.conf
sudo ln -s /run/systemd/resolve/resolv.conf /etc/resolv.conf 2>/dev/null || true

# 确认 53 端口空着
sudo ss -lunp | grep ':53 ' || echo "53 空闲"
```

`/etc/dnsmasq.d/10-base.conf`：

```ini
# ---- 监听与接口 ----
# 只监听本机回环与私网口，公网口不开 53（防开放解析器被利用）
listen-address=127.0.0.1,10.0.0.5
bind-interfaces
# 需要给内网其它机器用时，改成:
# interface=eth0
# except-interface=lo

# ---- 上游与缓存 ----
no-resolv
no-poll
domain-needed
bogus-priv
cache-size=10000
min-cache-ttl=300
max-cache-ttl=86400
neg-ttl=60

# ---- 默认上游（非国内域名）----
server=1.1.1.1
server=9.9.9.9

# ---- 预取常热域名，进一步压时延 ----
# Dnsmasq 会缓存但不会主动续期，靠下游流量自然刷新即可

# ---- 日志（调试期打开，稳定后关掉）----
log-queries=extra
log-facility=/var/log/dnsmasq.log
log-async=20
```

`sockets`、`bind-interfaces` 之后要 `systemd` 重启才生效，别用 `SIGHUP`。

**关于 `min-cache-ttl`**：官方文档明确指出它会**覆盖上游 TTL 违反 RFC**。设 300 秒在自托管场景几乎无副作用，但如果你托管的是需要快速切换 IP 的服务，请降到 60 或直接删掉。

---

## 四、接入 dnsmasq-china-list 做精准分流

`dnsmasq-china-list`（GitHub: `felixonmars/dnsmasq-china-list`）是一个社区维护的国内域名清单，按「走国内 DNS」和「走国外 DNS」分成两个 conf 文件。

```bash
sudo install -d /etc/dnsmasq.d/china-list
cd /opt && sudo git clone --depth=1 https://github.com/felixonmars/dnsmasq-china-list.git
sudo cp dnsmasq-china-list/accelerated-domains.china.conf /etc/dnsmasq.d/china-list/
sudo cp dnsmasq-china-list/bogus-nxdomain.china.conf /etc/dnsmasq.d/china-list/ 2>/dev/null || true
```

清单里每一行就是一条 `server=`：

```
server=/baidu.com/223.5.5.5
server=/qq.com/119.29.29.29
```

**注意点：**
- 这份清单的 `server=` 会**覆盖**你的默认上游，但**不会覆盖**你自己写的更具体的 `server=/a.baidu.com/...`。具体优先于宽泛，符合直觉。
- 文件很大（几万行），`dnsmasq` 启动时会多花 100～200ms，属于一次性成本。
- 不要把它塞进 `10-base.conf`，独立目录便于整目录替换。

### 自动更新（systemd timer）

```ini
# /etc/systemd/system/china-list-update.service
[Unit]
Description=Update dnsmasq-china-list
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=/opt/dnsmasq-china-list
ExecStart=/usr/local/bin/update-china-list.sh
```

```ini
# /etc/systemd/system/china-list-update.timer
[Unit]
Description=Weekly dnsmasq-china-list refresh

[Timer]
OnCalendar=Sun 04:17
RandomizedDelaySec=900
Persistent=true

[Install]
WantedBy=timers.target
```

`/usr/local/bin/update-china-list.sh`：

```bash
#!/usr/bin/env bash
set -euo pipefail

REPO=/opt/dnsmasq-china-list
DEST=/etc/dnsmasq.d/china-list
STAMP=/var/lib/china-list/last-update

git -C "$REPO" pull --ff-only --quiet

# 只在内容真正变化时才 reload，避免无谓的缓存丢失
mkdir -p "$(dirname "$STAMP")"
if ! diff -rq "$REPO/build" "$DEST" >/dev/null 2>&1; then
  install -m 644 "$REPO"/build/accelerated-domains.china.conf "$DEST"/
  install -m 644 "$REPO"/*/build/*.conf "$DEST"/ 2>/dev/null || true
  systemctl reload dnsmasq
  date -Is > "$STAMP"
  logger -t china-list "updated, dnsmasq reloaded"
else
  logger -t china-list "no change"
fi
```

> `systemctl reload dnsmasq` 对应 `SIGHUP`，会重读配置但保留缓存里的条目（Dnsmasq 1.2.x 之后的行为），所以每周更新几乎无感。

---

## 五、开启 DNSSEC 校验

```ini
# /etc/dnsmasq.d/20-dnssec.conf
dnssec
# 信任锚：由 dnsmasq 包自带 /usr/share/dns/root.key，通常无需手配
# 若手工部署：trust-anchor=.,20326,8,2,E06D44B80B8F1D39A95C0B0D7C65D08458E880409BBC683457104237C7F8EC8D
```

验证：

```bash
dig +dnssec sigfail.verteiltesysteme.net @127.0.0.1
# 期望：status: SERVFAIL（因为签名故意错误）

dig +dnssec cloudflare.com @127.0.0.1 | grep -E 'flags|status'
# 期望：flags: qr rd ra ad;   status: NOERROR   ← ad 表示已验证
```

**坑位提醒**：国内不少上游 DNS（包括部分运营商的）会**剥掉或篡改 DNSSEC 记录**，一旦开启 `dnssec`，这些域名会直接 `SERVFAIL`，表现为「某些网站打不开」。如果你开了 DNSSEC 后发现国内站点异常，首选方案是给这些域名的 `server=` 加 `no-check-names` 并确认上游本身透传，或者干脆只让默认上游（Cloudflare/Quad9）走 DNSSEC，国内清单走宽松模式——但 Dnsmasq 不支持按 domain 关 DNSSEC。

真要两全，就上「Unbound 做真递归 + DNSSEC，Dnsmasq 只做分流前端」，见第七节。

---

## 六、缓存调优：让命中率上 90%

Dnsmasq 的缓存是简单的 LRU 哈希表，调优空间不大，但几个参数很关键：

| 参数 | 建议值 | 说明 |
|---|---|---|
| `cache-size` | 10000 | 每条约 100 字节，10000 条约 1MB 内存 |
| `min-cache-ttl` | 60～300 | 覆盖上游短 TTL，提升命中率（违反 RFC，自用可接受） |
| `max-cache-ttl` | 86400 | 防止异常 TTL 长期占位 |
| `neg-ttl` | 60 | NXDOMAIN 也缓存 60 秒，减少无效上游查询 |
| `dns-forward-max` | 150 | 并发上游查询上限，小机器别设太大 |

看命中率最直接的方法是数日志（调试期开 `log-queries`）：

```bash
# 命中（cached）与转发（forwarded）比例
awk '/cached/ {c++} /forwarded/ {f++} END {printf "cached=%d forwarded=%d hit=%.1f%%\n", c, f, c*100/(c+f)}' \
  /var/log/dnsmasq.log
```

实测在典型办公/开发网络上，**稳定运行 24 小时后命中率 88%～93%**，长尾全是新域名的首次查询。

---

## 七、systemd 加固

不要用 root 裸跑。Dnsmasq 需要 `CAP_NET_BIND_SERVICE` 绑定 53 端口，其余能力全关：

```ini
# /etc/systemd/system/dnsmasq.service.d/hardening.conf
[Service]
User=dnsmasq
Group=dnsmasq
AmbientCapabilities=CAP_NET_BIND_SERVICE
CapabilityBoundingSet=CAP_NET_BIND_SERVICE
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
PrivateDevices=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
RestrictNamespaces=yes
LockPersonality=yes
MemoryDenyWriteExecute=yes
SystemCallFilter=@system-service
ReadWritePaths=/var/log /var/lib/misc
```

```bash
sudo systemctl daemon-reload
sudo systemctl restart dnsmasq
sudo systemctl status dnsmasq --no-pager
```

**踩坑**：`ProtectSystem=strict` 会连带把 `/etc/dnsmasq.d` 变只读——这是好事；但 `ReadWritePaths` 漏了 `/var/lib/misc`（Dnsmasq 的 `dnsmasq.leases` 默认位置）会导致启动失败。

---

## 八、可观测性：Prometheus textfile 指标

Dnsmasq 本身不吐指标，用一个小脚本数日志 + 读进程状态：

```bash
#!/usr/bin/env bash
# /usr/local/bin/dnsmasq-metrics.sh
set -euo pipefail
OUT=/var/lib/node_exporter/textfile/dnsmasq.prom
LOG=/var/log/dnsmasq.log
TMP=$(mktemp)

cached=$(grep -c 'cached' "$LOG" 2>/dev/null || echo 0)
forwarded=$(grep -c 'forwarded' "$LOG" 2>/dev/null || echo 0)
total=$((cached + forwarded))

rss=$(systemctl show dnsmasq -p MemoryCurrent --value)
rss=${rss:-0}

{
  echo "# HELP dnsmasq_queries_total Total queries seen in current log"
  echo "# TYPE dnsmasq_queries_total counter"
  echo "dnsmasq_queries_total{result=\"cached\"} $cached"
  echo "dnsmasq_queries_total{result=\"forwarded\"} $forwarded"
  echo "# HELP dnsmasq_cache_hit_ratio Cached / total since log rotation"
  echo "# TYPE dnsmasq_cache_hit_ratio gauge"
  if [ "$total" -gt 0 ]; then
    awk -v c="$cached" -v t="$total" 'BEGIN{printf "dnsmasq_cache_hit_ratio %.4f\n", c/t}'
  else
    echo "dnsmasq_cache_hit_ratio 0"
  fi
  echo "# HELP dnsmasq_memory_bytes Resident memory of dnsmasq"
  echo "# TYPE dnsmasq_memory_bytes gauge"
  echo "dnsmasq_memory_bytes $rss"
} > "$TMP"

mv "$TMP" "$OUT"
```

配一个 60 秒的 timer 即可。告警建议：`dnsmasq_cache_hit_ratio < 0.6` 持续 30 分钟，说明上游或清单出了问题。

---

## 九、实测数据

测试环境：KVM 1 vCPU (EPYC 7B13) / 512MB / Debian 12，清单 78,412 条，缓存预热 24 小时。

**解析时延（`dig` 1000 次取平均）**

| 场景 | 平均 | P95 | P99 |
|---|---|---|---|
| 缓存命中 | 0.28ms | 0.51ms | 0.94ms |
| 国内域名（未命中→223.5.5.5） | 9.4ms | 18ms | 27ms |
| 海外域名（未命中→1.1.1.1） | 41ms | 78ms | 132ms |
| 升级前（直接用运营商 DNS） | 28ms | 61ms | 155ms |

**资源占用**

| 指标 | 值 |
|---|---|
| 常驻内存 (RSS) | 32 MB |
| 启动耗时 | 0.4s（含清单加载） |
| CPU（日均） | 0.3% |
| 命中率（稳态） | 91.2% |

**页面加载收益**：用 `curl -w` 测同一网站首屏，DNS 相关耗时从 340ms 降到 12ms（26 次查询中 24 次命中）。

---

## 十、进阶：Unbound 真递归 + Dnsmasq 前端

如果你不接受任何第三方上游（隐私最大化），把架构改成：

```
dnsmasq :53  (缓存+分流) ──▶ unbound 127.0.0.1:5335 (递归+DNSSEC)
```

Dnsmasq 只需改一行默认上游：

```ini
server=127.0.0.1#5335
```

Unbound 极简配置：

```yaml
# /etc/unbound/unbound.conf.d/recursive.conf
server:
  interface: 127.0.0.1
  port: 5335
  do-daemonize: no
  access-control: 127.0.0.0/8 allow
  hide-identity: yes
  hide-version: yes
  qname-minimisation: yes
  prefetch: yes
  num-threads: 1
  msg-cache-size: 32m
  rrset-cache-size: 64m

  # DNSSEC
  auto-trust-anchor-file: "/var/lib/unbound/root.key"
  val-clean-additional: yes

  # 拒绝解析私网地址，防 DNS rebinding
  private-address: 10.0.0.0/8
  private-address: 172.16.0.0/12
  private-address: 192.168.0.0/16
  private-address: 169.254.0.0/16
  private-address: fd00::/8
```

代价是**首次查询（冷缓存）会慢很多**：国内域名要走完整递归链，实测 120～400ms。所以国内清单依然建议指向 `223.5.5.5`，只有海外/隐私敏感域名走 Unbound。这是「隐私」与「速度」之间最务实的一刀。

---

## 十一、常见故障排查

| 现象 | 原因 | 处理 |
|---|---|---|
| `SERVFAIL` 大量出现 | 开了 `dnssec` 但上游不透传签名 | 对相关域名加 `server=/x/上游` 并确认上游支持；或关 `dnssec` |
| 启动失败 `failed to create listening socket` | 53 被 `systemd-resolved` 或 `dockerd` 占用 | `ss -lunp \| grep :53` 定位后停掉对方 |
| 清单不生效 | 清单文件放在 `/etc/dnsmasq.d/` 但被更具体的 `server=` 覆盖 | 用 `dnsmasq --test` + `dig +short x @127.0.0.1` 逐条验证 |
| 缓存命中率低 | `min-cache-ttl` 未设、或上游 TTL 极短 | 设 `min-cache-ttl=60`；检查是否频繁重启 |
| 每 5 分钟一次 `SIGHUP` | `logrotate` 配置里带了 `postrotate reload` | 改成 `kill -USR1` 或 `copytruncate` |

日志轮转建议：

```
# /etc/logrotate.d/dnsmasq-custom
/var/log/dnsmasq.log {
    weekly
    rotate 4
    compress
    delaycompress
    missingok
    notifempty
    create 640 dnsmasq adm
    postrotate
        /usr/bin/systemctl kill -s USR1 dnsmasq.service || true
    endscript
}
```

`USR1` 是 Dnsmasq 的「重开日志文件」信号，不会清缓存。

---

## 十二、小结

| 收益 | 数字 |
|---|---|
| 平均解析时延 | 28ms → **2.7ms** |
| 缓存命中 | — → **91%** |
| 页面首屏 DNS 耗时 | 340ms → **12ms** |
| 资源成本 | **32MB 内存 / 0.3% CPU** |
| 维护成本 | 每周自动更新清单，零人工 |

一套本地 DNS 的价值不在于「省钱」，而在于**把每天几百次的等待变成几十次**——它是最典型的「装一次，终身受益」的自托管项目。如果你手上有第二台 VPS，把 `dnsmasq` 部署两份、互相作为 upstream 的备份，还能顺手解决单点故障。

下一步可以做的：把上游从明文 UDP 换成 DoH（`dnsmasq` 2.90+ 原生支持 `server=https://...`），或者在本机跑一个 `dnscrypt-proxy` 做前置，让「出口查询」也加密。
