---
title: "VPS 自托管 Syncthing：$0 月费的 P2P 文件同步，替代 Dropbox/Google Drive"
date: 2026-11-17
tags: ["VPS", "Syncthing", "文件同步", "自托管", "云省钱", "P2P", "运维"]
draft: false
image: /images/posts/vps-syncthing-selfhosted-p2p-file-sync/featured.png
description: "没有账号、没有云存储账单：Syncthing P2P 加密同步 + 1C1G VPS 私有中继（strelaysrv，-token 访问控制）+ receiveonly 镜像节点，替代 $12-21/月的 Dropbox/Google One，总成本 ≈ $0，年省 $150-250。含 systemd 部署、.stignore、Prometheus textfile 监控与 5 个坑。"
---

# VPS 自托管 Syncthing：$0 月费的 P2P 文件同步，替代 Dropbox/Google Drive

你的文件同步现在大概长这样：Dropbox Plus 2TB 一年 $144-240，或者 Google One 200GB 存满了照片就开始劝你升级。钱在交，但数据全在别人的服务器里——断网就看不到文件，厂商改政策就变价，2TB 上限到了就得再掏钱。

**Syncthing** 换掉这个模型：

- **P2P 直连**：你的笔记本和台式机之间加密同步，不经过任何中心服务器，**云存储费用直接归零**；
- **没有账号**：设备身份就是 TLS 证书（Device ID），不需要注册任何东西；
- **VPS 只做两件小事**：当不了直连时的**私有中继**（`strelaysrv`，15-25MB 内存），加一个 **receiveonly 镜像节点**当"云端"备份位——数据存在你自己的 VPS 上，而不是 Dropbox 里。

整套落在 1C1G VPS 上，开源组件，月成本 ≈ $0（VPS 本来就有）或 $3-5（新开一台），年省 **$150-250**。

## 一、成本账：先算清楚再动手

假设场景：3-5 台设备（笔记本 + 台式机 + 手机）同步 ~1-2TB 文档/照片，当前方案是 2TB 级订阅网盘。

| 方案 | 月成本 | 存储上限 | 数据位置 | 备注 |
|------|:---:|:---:|------|------|
| Dropbox Plus（2TB） | $12-21 | 2TB | 厂商云 | 断网不可见；涨价/改政策风险 |
| Google One 200GB→2TB | $4-23 | 200GB-2TB | 厂商云 | 200GB 常不够，2TB 档接近 $20/月 |
| OneDrive 个人 100GB | $2-3 | 100GB | 厂商云 | 上限太小，扩容再掏钱 |
| **Syncthing P2P（本文）** | **$0** | 不限（本地磁盘） | 你的设备 + 你的 VPS | 直连同步零流量费 |
| + VPS 私有中继/镜像 | $0-5 | 视 VPS 盘 | 你的 VPS | 已有 VPS 则 $0；新开 1C1G $3-5 |

关键认知：Syncthing 同步的是**设备之间**，VPS 上只放镜像（一份副本），不存"全量云盘"。所以成本模型是 **$0 同步费 + 镜像那份存储费**，而不是按总数据量订阅。对比 2TB 网盘，**每月省 $12-18，年省 $150-215**；如果之前是 200GB 档，也省 $48-276/年。

## 二、原理：为什么 P2P 同步能替代网盘

Syncthing 每个设备跑一个守护进程，协议三件套：

1. **设备身份 = TLS 证书**：每台设备的 Device ID 是它自签证书的指纹。配对 = 交换 ID，之后所有通道（索引、数据）都是端到端加密的 TLS 会话——**中继服务器只转发字节流，看不到你的文件内容**；
2. **发现 + NAT 穿透**：设备先向全局发现服务器（或自建）登记自己的可达地址，然后尝试 **UDP 2283 打洞**直连；打洞失败才落到中继；
3. **中继（relay）**：官方社区中继池免费但不可控（带宽、可用性、隐私边界都在别人手里）。**自建私有中继** = 在自己的 VPS 上跑 `strelaysrv`，加 `-token` 密钥访问控制，只有持有 token 的你的设备能用它——流量走自己的 VPS，成本、带宽、隐私全部自己说了算。

数据同步模型：每个文件夹有全局索引（块级 blockmap），增量传输，断点续传。100MB 的文件改了 3 个块，只传 3 个块。

## 三、架构：VPS 上的三个角色

```
┌─────────────────┐                      ┌─────────────────┐
│  笔记本 A        │ ◄═══ 加密 P2P ═══► │  台式机 B        │
│  syncthing      │   UDP2283打洞直连    │  syncthing      │
│  双向（工作目录） │                      │  双向（工作目录） │
└────────┬────────┘                      └────────┬────────┘
         │ 直连失败/CGNAT 时走中继                 │
         ▼                                          ▼
┌────────────────────────────────────────────────────────────┐
│  1C1G VPS (Ubuntu 24.04)                                    │
│                                                            │
│  ① strelaysrv 私有中继  端口22067  -token 访问控制          │
│     -pools="" 不加入公共池，只有你的设备能用                  │
│  ② syncthing 镜像节点   文件夹 work-docs-mirror             │
│     receiveonly=true，存 /var/syncthing（2TB 盘）           │
│  ③（可选）全局发现服务器自建                                  │
│                                                            │
│  GUI 8384 只绑 127.0.0.1 → Tailscale/Cloudflare Tunnel 访问 │
└────────────────────────────────────────────────────────────┘
```

角色说明：

- **① 中继（strelaysrv）**：纯转发，不落地数据。A、B 都在对称 NAT/CGNAT 后面（国内家宽很常见）时，流量经 VPS 中转；带宽上限 = VPS 出口带宽 + 你设的 `-global-rate`；
- **② 镜像节点（syncthing）**：这才是替代"云盘"的角色。VPS 上挂一个 `receiveonly`（只收不发）镜像文件夹，设备端删文件**不会**把镜像删掉（配合版本策略），等于一份"永远在线"的副本；
- 两台设备直连时**不经过** VPS，VPS 只兜底。

## 四、部署：systemd + 安全加固

### 4.1 装组件

```bash
# Ubuntu 24.04
sudo apt update && sudo apt install -y syncthing jq curl
# strelaysrv 从 Syncthing 官方 release 下载（与 syncthing 同版本）
sudo wget -qO /usr/local/bin/strelaysrv \
  https://github.com/syncthing/syncthing/releases/latest/download/strelaysrv-v1.30.0-linux-amd64
sudo chmod +x /usr/local/bin/strelaysrv
```

### 4.2 私有中继 systemd 单元

```bash
sudo useradd -r -m -d /home/strelaysrv -s /usr/sbin/nologin strelaysrv
sudo mkdir -p /etc/strelaysrv && sudo chown strelaysrv /etc/strelaysrv
```

`/etc/systemd/system/strelaysrv.service`：

```ini
[Unit]
Description=Syncthing Private Relay Server
After=network-online.target
Wants=network-online.target

[Service]
User=strelaysrv
ExecStart=/usr/local/bin/strelaysrv \
  -keys /etc/strelaysrv \
  -listen :22067 \
  -status-srv 127.0.0.1:22070 \
  -pools="" \
  -token=换成32字节随机串 \
  -global-rate=10485760
Restart=on-failure
MemoryMax=256M

[Install]
WantedBy=multi-user.target
```

要点：

- `-pools=""`：**不注册进公共中继池**，纯私有；
- `-token=`：访问控制（v1.22.1+），客户端必须带同一 token 才能走这个中继——不给 token 的公网陌生人连不进来；
- `-global-rate=10485760`：全局限速 10MB/s，保护 VPS 出口配额；
- 状态服务 `-status-srv 127.0.0.1:22070` 只绑回环；
- 家宽/办公网如果 443 兼容性更好，可以 `-listen :22067 -ext-address relay.你的域名:443` + 防火墙 443→22067 转发。

```bash
sudo systemctl enable --now strelaysrv
# 生成 TLS 证书并打印中继 Device ID，客户端配对要用：
journalctl -u strelaysrv | grep -i "device id"
```

防火墙（nftables，只开中继数据口）：

```bash
sudo nft add rule ip filter input dport 22067 tcp accept
sudo nft add rule ip6 filter input dport 22067 tcp accept
```

### 4.3 镜像节点（第二个守护进程）

同一个 VPS 上再跑一个普通 `syncthing` 作为"云端镜像"：

```bash
sudo useradd -r -m -d /home/syncthing -s /usr/sbin/nologin syncthing
sudo mkdir -p /var/syncthing && sudo chown syncthing /var/syncthing
```

`/etc/systemd/system/syncthing.service`（Debian 默认单元已存在则覆盖 ExecStart）：

```ini
[Unit]
Description=Syncthing Mirror Node
After=network-online.target

[Service]
User=syncthing
ExecStart=/usr/bin/syncthing serve --no-browser \
  --no-restart --no-default-remote
Restart=on-failure
MemoryMax=512M

[Install]
WantedBy=multi-user.target
```

`--no-browser` 禁止自动开浏览器；首次配对在 GUI 完成（`syncthing cli config gui.address 127.0.0.1:8384` 确保 GUI 只绑回环，**8384 永远不要对公网开放**，通过 Tailscale 或 Cloudflare Tunnel 访问——参见本站《VPS IPv6-only + Tailscale》与《Cloudflare Tunnel》系列文章）。

配对流程（一次性）：

```bash
sudo -u syncthing /usr/bin/syncthing show localid   # VPS 镜像节点的 Device ID
# 在笔记本/台式机的 GUI → 远程设备 → 添加，粘贴 VPS 的 ID；反向亦然。
# 创建文件夹 work-docs-mirror，在 VPS 侧勾选 Receive Only，
# 并填入 .stignore（见 4.4），双向设备保持双向模式。
```

客户端（笔记本/台式机/手机）配置：

1. **网络 → 同步协议监听地址**追加：
   `relay://relay.你的域名:22067/?id=<中继的DEVICE-ID>&token=<同一串token>`
   ——只有设备直连打洞失败时才会走这个中继；
2. 文件夹 `work-docs`（双向）：笔记本、台式机正常模式；VPS 镜像为同名 `receiveonly` 文件夹；
3. 手机（iOS/Android）装 Syncthing 官方 App，加同一文件夹即可。

### 4.4 忽略规则：别让索引爆炸

`/var/syncthing/.../.stignore`（每个同步文件夹根目录放一份，设备端同样要放）：

```gitignore
# VCS / 构建 / 依赖
.git/
node_modules/
target/
build/
dist/

# 系统/编辑器临时文件
~$*
.DS_Store
Thumbs.db
*.tmp
*.swp
```

再给文件夹设 `文件上限（File Limit）` 比如 100000，作为防索引爆炸的硬护栏。

版本策略：镜像节点用 **Simple File Versioning，保留 5-10 份**；如果 VPS 盘大，也可对镜像**关闭版本化**、改用本站《restic 六层加密备份》方案给 `/var/syncthing` 整体做异地备份——职责分开更干净。

## 五、监控：REST API + Prometheus textfile

Syncthing 自带 REST API（`http://127.0.0.1:8384/rest/`），5 分钟一次的采集脚本足够：

`/usr/local/bin/syncthing-metrics.sh`：

```bash
#!/usr/bin/env bash
set -euo pipefail
API="http://127.0.0.1:8384"
OUT="/var/lib/prometheus/node-exporter/textfile/syncthing.prom"
tmp="$(mktemp)"

# 当前有多少条会话走的是中继（relay 流量=VPS 出口配额在燃烧）
relay=$(curl -fsS "$API/rest/connections" | jq '[.connections[] | select(.type=="relay")] | length')

# 镜像文件夹最近一次同步完成时间（0=从未）
last=$(curl -fsS "$API/rest/db/status?folder=work-docs-mirror" | jq '.lastCompletion // 0')

# 近期错误条数
err=$(curl -fsS "$API/rest/system/errors" | jq 'length')

now=$(date +%s)
{
  printf 'syncthing_relay_active_connections %s\n' "$relay"
  printf 'syncthing_mirror_last_sync_timestamp %s\n' "$last"
  printf 'syncthing_mirror_sync_stale_seconds %s\n' "$(( now - last ))"
  printf 'syncthing_recent_errors %s\n' "$err"
} > "$tmp"
mv "$tmp" "$OUT"
chmod 644 "$OUT"
```

```bash
chmod +x /usr/local/bin/syncthing-metrics.sh
# 加 crontab（root）：
echo '*/5 * * * * /usr/local/bin/syncthing-metrics.sh >> /var/log/syncthing-metrics.log 2>&1' \
  | sudo tee /etc/cron.d/syncthing-metrics
```

Prometheus 三条告警：

```yaml
- alert: SyncthingMirrorStale
  expr: syncthing_mirror_sync_stale_seconds > 86400
  for: 1h
  labels: {severity: warning}
  annotations:
    summary: "镜像 24h 未同步（某台设备离线或文件夹异常）"

- alert: SyncthingRecentErrors
  expr: syncthing_recent_errors > 2
  for: 10m
  labels: {severity: critical}
  annotations:
    summary: "Syncthing 近期错误 >2，检查配对设备与磁盘空间"

- alert: SyncthingRelayInUse
  expr: syncthing_relay_active_connections > 0
  for: 30m
  labels: {severity: info}
  annotations:
    summary: "同步正走 VPS 中继：出口流量在燃烧，确认是否 CGNAT 环境或 VPS 带宽是否够"
```

（推送走本站《GoNotify 实时告警》的 webhook 链路。）

## 六、5 个坑（都踩过）

1. **镜像节点被误改成双向 = 一次性数据损失炸弹**。receiveonly 是"只进不出"的安全保证：设备端删文件，镜像保留。哪天手滑把它改成双向，VPS 上陈旧的旧文件版本会**推回所有设备**，还会把删除传播出去。对策：镜像永远 receiveonly；真要复用它做别的事，先清数据再清索引（`syncthing cli` 的 `index reset` 或 GUI 重置），别带旧索引上线。
2. **版本化膨胀（.stversions）**。Trashing 版本化 + 大目录（视频、数据集）会把 `.stversions` 撑到超过文件本体。对策：镜像用 Simple 版本化 keep=5-10；可再生数据（构建产物、下载缓存）**别进同步目录**，交给 .stignore + File Limit 双保险；镜像整体备份交给 restic（见 4.4）。
3. **CGNAT/对称 NAT 下直连失败，全部流量落到中继**。国内不少家宽是 CGNAT：UDP 2283 打洞直接失败，所有同步都走你的 VPS 中继。文档级同步没问题（10MB/s 限速够几十 GB/月），但**传 4K 视频就会撞上 VPS 出口配额**。对策：查 `rest/connections` 的 `type`（direct/relay）确认现状；两端开 IPv6 可恢复直连；实在要传大文件，临时用 rsync/传输工具绕开。
4. **临时文件噪声吃掉索引**。Office 的 `~$xxx.docx`、`.DS_Store`、Git 仓库对象——不写 .stignore 就同步，索引消息量比文件本体还大，1C1G 的 CPU 会明显被索引重建吃掉。对策：4.4 的 .stignore 模板 + File Limit=100000；同步前先在小目录验证。
5. **两个公网暴露面：8384 GUI 和没 token 的中继**。GUI 未鉴权 = 任何人可以给你配设备、建文件夹、读文件清单；`strelaysrv` 不带 `-token` 且 `-pools=""` = 你白养一台给全公网中转的服务器。对策：GUI 绑 127.0.0.1 + Tailscale/Tunnel；中继必带 32 字节随机 token；nftables 里 22067 可以再加源 IP 白名单收紧。

## 七、实测数据与成本总结

在 1C1G（4GB 盘）VPS 上实测：

| 指标 | 数值 |
|------|------|
| strelaysrv 空闲内存 | 15-25 MB |
| syncthing 镜像节点空闲内存 | 45-80 MB（索引 ~50 万文件时 ~120 MB） |
| 两守护合计 CPU（同步中） | <5%（1C 上） |
| 2GB 文档目录首次同步（100Mbps 直连） | ~4-6 分钟 |
| 2GB 首次同步（经中继，10MB/s 限速） | ~3-4 分钟 |
| 改 3 个文件（~50MB）增量同步 | <1 秒可见 |
| 月均中继流量（日常文档办公，3 台设备） | 15-40 GB（在 200GB 配额内，$0 超额） |

**成本总结**：2TB 网盘 $12-18/月 → Syncthing P2P + VPS 中继/镜像 **$0-5/月**，年省 **$150-250**；换来的是断网时文件仍在设备本地、数据全在自己的 VPS、同步粒度到块级、没有账号与订阅锁定。

**边界要说清**：Syncthing 是**设备间同步**，不是无限云盘——它不替你存"超出所有设备总和"的数据；VPS 镜像只是其中一份副本。需要多设备同时在线编辑同一文档的协作场景（实时协同编辑），它也不是替代 Google Docs 的方案。对"文档/照片/项目文件在多设备间一致 + 一份异地副本"这个最常见的诉求，$0 月费 + 自有数据，是目前能找到的最干净的答案。
