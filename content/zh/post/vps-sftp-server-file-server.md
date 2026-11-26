---
title: "SFTP 文件服务器自托管：SFTPGo 三协议一体，1C1G 替代商业文件传输 SaaS"
date: 2026-11-24
tags: ["VPS", "SFTPGo", "SFTP", "文件传输", "自托管", "云省钱", "运维"]
draft: false
image: /images/posts/vps-sftp-server-file-server/featured.png
description: "SFTPGo（Apache-2.0，Rust 编写）在 1C1G VPS 上 SFTP/FTPS/WebDAV 三协议一体，空闲 ~30-60MB：按用户容量/并发/带宽三重配额 + REST API 全自动化，$4-5/月替代商业托管文件传输 SaaS（$25-50/月），年省 $300-600。含 systemd 加固、FTPS TLS、restic→R2 备份与 5 个坑。"
---

# SFTP 文件服务器自托管：SFTPGo 三协议一体，1C1G 替代商业文件传输 SaaS

团队文件交换、合作伙伴传资料、给客户发交付物——这些场景用不上 Dropbox/Google Drive 那种全功能网盘，但商业**托管文件传输 SaaS**（FileTransferJunkie、Tecton、ShareFile 这一类）按"用户席位 + 存储量 + 传输量"三层叠收，最小档普遍 $25-50/月起步，传输量超了再加钱。而把一个 SFTP/FTPS/WebDAV 文件服务器搬上 $4-5/月 的 1C1G VPS，功能一样、按用户配额还更细，年成本直接砍掉 80-90%。

**SFTPGo** 是什么：Rust 编写的 Apache-2.0 开源文件服务器，一个二进制同时提供 **SFTP（SSH 协议）、FTPS（TLS 加密 FTP）、WebDAV** 三种协议入口，自带管理 UI、REST API、按用户配额（存储/并发/带宽）和存储后端抽象（本地磁盘或 S3 兼容存储）。没有 Go 插件地狱，没有多组件拼装，一个进程 + 一个 JSON 配置就能跑。

**SFTP 和 SFTPGo 是两回事，先分清**：SFTP（SSH File Transfer Protocol）是跑在 SSH 协议上的文件传输（RFC 4271，默认 22 端口）；SFTPGo 是支持 SFTP/FTPS/WebDAV 的**服务器软件**。选 VPS 时的硬性前置检查就一条：提供商是否封了 22 端口——大部分云厂商对 22 开白名单放行，少数封死 80/443 以外的端口，下单前看文档或花 $0 试连一次。另外 SFTPGo 默认监听 22，可以改 2222/2022，但记得客户端要带 `-P` 参数连新端口。

## 一、成本账：先算清楚再动手

| 方案 | 月成本 | 说明 |
|---|---|---|
| 商业文件传输 SaaS（FileTransferJunkie/Tecton/ShareFile） | $25-50/月起 | 席位 + 存储 + 传输三层计费，超额加钱 |
| 自建 SFTPGo @ 1C1G VPS（Hetzner CX22 级别） | $4-5/月 + 20GB 磁盘 | 含 SFTP/FTPS/WebDAV 全协议 |

**年省 $300-600**。1C1G 上 SFTPGo 空闲 ~30-60MB，单核跑 5-10 并发传输绰绰有余，瓶颈只在带宽——Hetzner/V.PS 级别 200GB 月流量，个人/小团队文件交换场景通常只用到 30-50GB/月，远够。

**一个省钱的延伸**：SFTPGo 的用户存储可以挂在 S3 兼容后端（比如 Cloudflare R2，出口费 $0），大文件直接存 R2，VPS 本地只留索引——存储量上去之后，比"VPS 加块盘"便宜得多。

## 二、30 分钟部署：systemd + JSON 配置

以下基于 Debian/Ubuntu，Hetzner/Netcup/V.PS 都适用。

```bash
# 1. 二进制（x86_64 为例，版本去 GitHub releases 取最新）
sudo apt install -y curl
curl -sL -o /tmp/sftpgo.tar.gz \
  https://github.com/drone-emdr/sftpgo/releases/latest/download/sftpgo_1.5.0_amd64_linux.tar.gz
sudo mkdir -p /opt/sftpgo
sudo tar -xzf /tmp/sftpgo.tar.gz -C /opt/sftpgo
sudo /opt/sftpgo/sftpgo version

# 2. 建配置/状态/数据目录，统一归 sftpgo 用户所有
sudo groupadd sftpgo
sudo useradd -r -g sftpgo -d /opt/sftpgo -s /usr/sbin/nologin sftpgo
sudo mkdir -p /etc/sftpgo/{config,state} /srv/sftpgo
sudo chown -R sftpgo:sftpgo /etc/sftpgo /opt/sftpgo /srv/sftpgo
sudo chmod 700 /etc/sftpgo/state /etc/sftpgo/config
```

systemd 单元 `/etc/systemd/system/sftpgo.service`（`MemoryMax` 硬上限兜底 1C1G 的内存预算，参照 [systemd socket 激活内存预算](/zh/post/vps-systemd-socket-activation-memory-budget/) 的思路）：

```ini
[Unit]
Description=SFTPGo file server (SFTP/FTPS/WebDAV)
After=network-online.target
Wants=network-online.target

[Service]
User=sftpgo
Group=sftpgo
WorkingDirectory=/opt/sftpgo
ExecStart=/opt/sftpgo/sftpgo server /etc/sftpgo/config.json
Restart=on-failure
RestartSec=5
MemoryMax=400M
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
```

`/etc/sftpgo/config.json` 最小可跑配置：

```json
{
  "general": { "user_id_prefix": "sftpgo", "max_retries": 3 },
  "sftp": {
    "enabled": true,
    "endpoints": [{ "address": "0.0.0.0", "port": 22 }]
  },
  "ftps": { "enabled": false },
  "webdav": {
    "enabled": true,
    "endpoints": [{ "address": "0.0.0.0", "port": 50080 }]
  },
  "api": {
    "enabled": true,
    "endpoints": [{ "address": "127.0.0.1", "port": 8080 }]
  },
  "data": {
    "storage_backend": {
      "type": "local",
      "local": { "base_dir": "/srv/sftpgo" }
    },
    "users": [],
    "users_backends": [{ "name": "sftpgo", "type": "json" }]
  },
  "http_credentials": { "user": "admin", "pass_enc": "d033e22ae348aeb5660fc2140aec35850c4da997" }
}
```

`pass_enc` 是密码的 SHA1 hex 值（上例是默认 admin/admin 的哈希，上线即改）。

```bash
sudo systemctl enable --now sftpgo
sudo systemctl status sftpgo
# WebDAV 入口 curl 探活：
curl -I http://127.0.0.1:50080/
# API 健康检查：
curl -s http://127.0.0.1:8080/api/v2/health -u admin:admin
```

管理 UI 与 API 同端口（`http://<VPS>:8080/`），默认账号 **admin/admin**——**上线第一件事是改密码**，用 API 一条命令：

```bash
curl -s -X PATCH http://127.0.0.1:8080/api/v2/users \
  -u admin:admin -H 'Content-Type: application/json' \
  -d '{"username":"admin","pass_enc":"<新密码的 SHA1 hex>"}'
```

API 默认只听 loopback，生产要远程管理就走 Tailscale（见 [Tailscale 零配置内网](/zh/post/vps-tailscale-zero-config-remote-access/)），不要直接暴露 8080。

## 三、用户、公钥与 FTPS TLS

**用户创建走 REST API**（免改 JSON、免重启）：

```bash
# 建用户 alice：主目录 /srv/sftpgo/alice，配额 512MB，最多 2 并发
curl -s -X POST http://127.0.0.1:8080/api/v2/users -u admin:<新密码> \
  -H 'Content-Type: application/json' -d '{
    "username": "alice",
    "home_dir": "/srv/sftpgo/alice",
    "pass_enc": "d3bd0e88f8a8a9f5c4d7f9b1e0c2a4b6c8d9e0f1",
    "max_sessions": 2,
    "quota_size": 536870912,
    "permissions": {
      "/": ["read", "create", "delete", "mkdir", "rename"]
    }
  }'
```

`pass_enc` 是密码的 SHA1 hex 值；**推荐直接禁用密码登录、只留公钥**：把客户端 `ssh-keygen -t ed25519` 生成的公钥放进用户的 `public_keys` 数组，密码字段留空。

**FTPS 要 TLS 才能开**：先在管理 UI（或 API）里给实例挂一张证书——自签 CA 的叶子证书即可，内网/团队用完全够用：

```bash
# 快速自签（内网团队场景）
mkdir /etc/sftpgo/tls && cd /etc/sftpgo/tls
openssl req -x509 -newkey rsa:2048 -nodes -days 365 \
  -keyout ftps.key -out ftps.crt -subj "/CN=sftpgo.internal"
sudo chown sftpgo:sftpgo ftps.key ftps.crt
```

config.json 里开 FTPS：

```json
"ftps": {
  "enabled": true,
  "endpoints": [
    { "address": "0.0.0.0", "port": 21,  "tls_mode": "explicit" },
    { "address": "0.0.0.0", "port": 990, "tls_mode": "implicit" }
  ],
  "cert_file": "/etc/sftpgo/tls/ftps.crt",
  "key_file":  "/etc/sftpgo/tls/ftps.key"
}
```

**隐式 vs 显式，选错连不上**：隐式（implicit/SSL）990 端口握手第一字节就加密；显式（explicit/TLS）21 端口先明文 `AUTH TLS` 再升级。客户端（FileZilla、lftp、curl）要按模式选对，混用必然失败。多数客户端默认走显式，990 隐式口是给老 FTP 客户端兼容用的——只留一个口，别两个都开。

## 四、配额与流量治理：三层限制

SFTPGo 的按用户控制三件套，全在用户对象里改（PATCH `/api/v2/users`）：

| 控制项 | 字段 | 1C1G 建议值 |
|---|---|---|
| 存储配额 | `quota_size`（字节） | 512MB-2GB/用户 |
| 并发会话 | `max_sessions` | 2-5 |
| 带宽限制 | `bwlimit`（含 start/stop 时段） | 峰值时段 5-10MB/s |

注意**配额 ≠ 总上限**：10 个用户各 1GB 配额 = 10GB 需求，但 20GB 磁盘里还有系统/日志/swap 的空间，总配额要按盘的 80% 封顶，否则超额的写会直接把盘写满。

## 五、API 自动化：用户全生命周期一条命令

管理 UI 之外，整个用户生命周期都能走 API（管理 UI 与 REST API 同端口，UI 在 `/`，API 在 `/api/v2`）：

```bash
API=http://127.0.0.1:8080/api/v2
AUTH='admin:<新密码>'

# 列出所有用户（含存储用量与状态）
curl -s $API/users -u $AUTH

# 停用 bob（保留数据，立即拒绝新会话）
curl -s -X PATCH $API/users/bob -u $AUTH \
  -H 'Content-Type: application/json' -d '{"suspended": true}'

# 查 bob 的实际占用
curl -s $API/users/bob -u $AUTH | grep -o '"quota_size":[^,}]*\|"quota_size_used":[^,}]*'

# 删除用户（连同数据）
curl -s -X DELETE $API/users/bob -u $AUTH
```

配 5 分钟 crontab，把"新建外部协作方账号"变成 3 行脚本：生成公钥 → POST 用户 → 把公钥/端口发给对方。账号生命周期结束（交付物传完）一条 DELETE，数据可留可删。

## 六、监控与告警：三层

**L1 存活**：`GET /api/v2/health` 返回 `{"Status":"ok"}`，200 即活。

**L2 容量**：数据盘的 `df` 百分比。

**L3 滥用**：日志里 `auth failed` 计数——暴力破解/撞库的指纹。SFTPGo 默认 JSON 行日志（`/var/log/sftpgo/sftpgo.log`），配合 [CrowdSec + nftables IP 信誉封禁](/zh/post/vps-ipset-l7-filter-crowdsec/) 可自动封异常 IP。

Prometheus textfile 采集器（`/usr/local/bin/sftpgo-prom-collector.sh`，`prometheus-node-exporter` 的 textfile collector 指向它）：

```bash
#!/bin/bash
OUT=/var/lib/prometheus-node-exporter/sftpgo.prom
{
  code=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8080/api/v2/health -u admin:$SFTPGO_ADMIN_PASS)
  echo "sftpgo_up 0"
  [ "$code" = "200" ] && echo "sftpgo_up 1"
  pct=$(df -P /srv/sftpgo | awk 'NR==2{print $5}' | tr -d '%')
  echo "sftpgo_data_disk_used_percent $pct"
  fails=$(tail -n 5000 /var/log/sftpgo/sftpgo.log 2>/dev/null | grep -c 'auth failed' || true)
  echo "sftpgo_recent_auth_failures $fails"
} > "$OUT"
```

```bash
sudo crontab -e
*/5 * * * * /usr/local/bin/sftpgo-prom-collector.sh
```

Grafana/Prometheus 三条告警规则：

| 指标 | 阈值 | 级别 |
|---|---|---|
| `sftpgo_up == 0` | 持续 5m | critical |
| `sftpgo_data_disk_used_percent > 85` | 持续 10m | critical（>75 warning） |
| `sftpgo_recent_auth_failures > 50` | 持续 15m | warning（转 CrowdSec 封禁） |

## 七、备份与恢复：restic → R2

SFTPGo 的**用户、权限、配额全部在 `state/` 目录**，`config.json` 是协议/端口/TLS 配置，`/srv/sftpgo` 是用户数据——三者都在 restic 的备份集里（见 [restic → S3/R2 备份体系](/zh/post/vps-restic-automated-backup-s3/)）：

```bash
restic -r rest:backup-sftpgo \
  --exclude-file /etc/restic/sftpgo-excludes \
  backup /etc/sftpgo /srv/sftpgo
```

`/etc/restic/sftpgo-excludes`：

```
/srv/sftpgo/**/*.tmp
/srv/sftpgo/**/.partial
```

```bash
sudo crontab -e
# 每日 03:00，保留 7 份快照
0 3 * * * restic -r rest:backup-sftpgo --last-backup 23H backup /etc/sftpgo /srv/sftpgo && restic forget --keep-daily 7 --prune
```

**恢复演练**（每季度做一次，10 分钟）：

```bash
restic -r rest:backup-sftpgo restore last \
  --target /tmp/sftpgo-restore
diff -r /tmp/sftpgo-restore/etc/sftpgo/state /etc/sftpgo/state   # 用户清单一致
ls /tmp/sftpgo-restore/srv/sftpgo                                 # 目录树完整
```

**2-1-1 的第二个 1**：大文件场景再加 `rsync -a --delete /srv/sftpgo/ backup@2nd-vps:sftp-mirror/` 夜推一次到备用 VPS，VPS 整机挂掉时异地拉取即可恢复。

## 八、5 个坑（踩过的才算数）

1. **默认 admin/admin 挂在公网 8080**：API 默认只 listen loopback 是安全的，但如果你为了远程管理把 8080 直接映射公网且没改默认密码，撞库 10 分钟内就进来了。改密码 + 只走 Tailscale/SSH 隧道，二者一个都不能少。
2. **只备份了数据目录，漏了 `state/`**：用户/权限/配额全在 `state/` 里，数据文件搬回去没有 `state/` 等于一台空服务器。restic 的备份集必须 `/etc/sftpgo` + `/srv/sftpgo` 两个路径一起进。
3. **FTPS 隐式/显式混用**：990 隐式口和 21 显式口各配一套，客户端选错模式就是"连上立刻断开"，排查半天。内网团队场景只留一个口。
4. **按用户配额 ≠ 总上限**：每个用户的 `quota_size` 独立计，总和可以超过物理盘。总配额按盘的 80% 封顶，再配 L2 的磁盘使用率告警兜底。
5. **把 SFTPGo 当 S3 客户端用**：它不是 S3 API 的服务器，"S3 兼容"指的是**用户存储可以挂在 S3 后端（R2）上**，数据存 R2、VPS 只留索引。真要对外提供 S3 API，那是 MinIO 的活（见 [MinIO 对象存储省钱](/zh/post/vps-minio-object-storage-cost-saving/)）。

## 九、混合模式：什么时候还是买 SaaS

合规要求（SOC 2 报告、审计留痕）或用户数 >50 且要求 SLA 时，商业 SaaS 的合规成本低于自维护。个人/小团队（<20 用户、内部 + 少量外部协作）：自托管 SFTPGo，$4-5/月，省 $300-600/年，配额和 API 控制反而比 SaaS 更细。

---

*部署了 SFTPGo 之后想管密钥和凭据轮换，看 [VPS 自托管 Vault 密钥中心](/zh/post/vps-vault-selfhosted-secrets-management/)；缓存层自托管，看 [VPS 自托管 Valkey](/zh/post/vps-valkey-selfhosted-redis-replacement/)。*
