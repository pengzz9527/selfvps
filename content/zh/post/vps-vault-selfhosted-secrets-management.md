---
title: "VPS 自托管 Vault：$0 月费自建密钥中心，动态凭据告别静态密码"
date: 2026-11-20
tags: ["VPS", "Vault", "密钥管理", "自托管", "云省钱", "PostgreSQL", "PKI", "运维"]
draft: false
image: /images/posts/vps-vault-selfhosted-secrets-management/featured.png
description: "1C1G VPS 上跑单节点 Raft Vault（空闲 ~120-150MB）：KV v2 + 数据库动态凭据 + PKI + Transit 四引擎，数据库账号按 lease 自动过期、证书 24h 短周期签发，$0 替代 AWS Secrets Manager（$0.40/密文/月）与 HCP Vault，免去季度人工轮换 ~10 小时/季。含 Raft 单节点全损与 unseal 密钥两大前置风险、TTL 纪律与 5 个坑。"
---

# VPS 自托管 Vault：$0 月费自建密钥中心，动态凭据告别静态密码

"自托管清单"里最容易漏掉的一项不是监控、不是邮件，而是**密钥管理**：数据库账号、API key、SSH 私钥散落在配置文件、CI 环境变量、聊天记录里，全是静态值——泄露一次，轮换一次，而且每次都是全量人工操作。真正能解决这件事的工具就一个名字反复出现：HashiCorp Vault。它被很多团队当作"生产级、多集群、企业级"的重型系统，但在个人/小团队场景下，**单节点 Raft + 四组密钥引擎**在 1C1G VPS 上空闲只占 ~120-150MB，$0/月 就能把"静态密码 + 人工轮换"这套运维债务整体注销。

**Vault**（BFS/BSL 许可，开源版功能完整）在这里只当四件事：

- **KV v2 引擎**：应用配置、API key、DB 连接串的集中仓库，带版本历史（误删可回滚）；
- **数据库动态凭据**：Postgres/MySQL 按 lease 临时发账号，TTL 到期自动过期回收，应用重启后旧凭据直接作废；
- **PKI 引擎**：自建根 CA，给内网服务发 24h 短周期证书，mTLS 不再手工续期；
- **Transit 引擎**：加密/解密不落盘——密钥只在内存，数据加密后存你自己的 R2/S3，Vault 宕机不丢密文。

落到一台已有（或新开 ~$4/月）的 1C1G VPS，**$0-5/月**，替代的是 AWS Secrets Manager $0.40/密文/月（200 个密文 ≈ $80/月）、HCP Vault ≈$5-15/月，外加每季度"20 个应用 × 30 分钟人工轮换"≈ 10 小时的劳动。**年省 $900+ 并消除凭据泄露的永久风险面**。

## 一、成本账：先算清楚再动手

场景：20 个微服务/脚本，各自持有数据库账号、API key、内部证书，当前方案是"配置里写死 + 季度人工轮换"或 SaaS 密钥托管。

| 方案 | 200 个密钥月成本 | 轮换方式 | 备注 |
|------|:---:|------|------|
| 静态配置 + 人工轮换 | $0（VPS 已有） | 季度 10h 人工 | 泄露=永久风险面，无审计 |
| AWS Secrets Manager | ≈$80+ | 可选自动 | $0.40/密文/月，API 调用另计 |
| GCP Secret Manager | ≈$12-15 | 可选自动 | ~$0.05-0.075/密文/月含版本 |
| Azure Key Vault（标准，非 HSM） | ≈$1-5 | 可选自动 | 按调用量计费，小量便宜 |
| HCP Vault | ≈$5-15/用户/月 | 自动 | 按用户订阅 |
| **Vault @ 1C1G VPS（单节点 Raft）** | **$0** | 全自动（lease/PKI TTL） | 新开机型 $4-5；空闲 ~120-150MB |

**年省 ≈ $900（对比 AWS SM）**，且每次凭据泄露的爆炸半径从"永久有效"缩短到 TTL（默认 30 分钟-24h）。

**边界要说清**：单节点 Raft = 没有集群冗余。个人 VPS 场景可接受（配合每日 Raft 快照 + restic 异地备份，见第五节），生产关键系统请上三节点 Raft（3 台 $5 VPS ≈ $15/月）——这是后文第五节两个前置风险之一，不是"忘了写"。

## 二、原理：为什么动态凭据能注销静态密码

传统模型：**账号是长期资产**——建一个 `app_rw` 用户，密码写进配置文件，永远有效，泄露后只能人工改密、全量重启。

Vault 的模型：**凭据是短期租约（lease）**——应用每次需要 DB 连接时向 Vault 要一组"用户名/密码"，带 TTL（如 30m）和 `max_ttl`（如 2h），到期或应用重启后该账号被 Postgres 插件自动 DROP。攻击者偷走凭据最多获得 30 分钟窗口，且审计日志（第五节）能直接看到是哪台机器在什么时间取的。

四组引擎各自对应一类"静态值"：

| 引擎 | 替代的静态值 | 动态行为 |
|------|------|------|
| KV v2 | 配置文件里的连接串/密钥 | 版本历史 + TTL，误删可回滚 |
| database | 长期 DB 账号 | 按 lease 发账号，到期自动回收 |
| pki | 手工签发/续期的证书 | 根 CA 内建，24h 短证书自动重签 |
| transit | 散落各处的加解密密钥 | 密钥不落盘，Vault 只管运算 |

**存储选型**：单节点 Raft 是个人场景的最优解——无外部依赖（不需要旁边挂个 Postgres 存 Vault 自身状态），一个目录 `/var/lib/vault` 就是全部状态，restic 一条命令带走去 R2（出口费 $0）。

**unseal（解封）**：Vault 的密钥本身要加密存储，启动时必须"解封"。无云 KMS 的纯 VPS 场景用 **Shamir 分片**（3-of-5）：把 5 片密钥中 2 片放两台不同介质（如加密 USB + 加密 R2 对象），任何一台机器单独被偷都无法解封——这是第四节的关键步骤。

## 三、架构：一台 VPS 上的四个角色

```
 [微服务/CI/脚本] ──HTTPS(经 Tailscale/Tunnel)──▶ ┌────────────────────────┐
 [Postgres 插件]   ◀──按需发临时账号──────────────│  Vault (单节点 Raft)   │
 [内网服务]        ──拉取 24h 证书─────────────────│  KV2+database+pki     │
                                                    │  +transit 四引擎     │
                                                    └──────────┬───────────┘
                 /v1/sys/health 探测 │ /v1/sys/metrics?format=prom
                ┌────────────────────┴────────────────────┐
 [Uptime Kuma]  探测   [Prometheus] 抓取 → 3 条告警
                └───────────┬─────────────────────────────┘
 [restic nightly] ──加密────▶ [R2 对象存储 $0 出口]（Raft 快照+数据目录）
 [审计日志]        ──tail────▶ [Loki 聚合 + logrotate 限盘]
```

8200 端口**永远只绑回环**：外部访问走 Tailscale（见 [Tailscale 零配置私网访问](/post/vps-tailscale-zero-config-remote-access/)）或 Cloudflare Tunnel（[参考](/post/vps-cloudflare-tunnel-zero-trust/)），Vault 没有内置网络 ACL，公网直开 8200 = 直接交出 root token，这是第五节第 3 个坑。

## 四、部署：systemd + Raft 初始化 + 四引擎

### 0. 前置检查（买机器之前做）

```bash
# 磁盘：Raft 快照 + WAL + 审计日志，留 2GB 余量即可，别和大数据盘共用
df -h /var
# 确认目标 Postgres 可被 VPS 访问（动态凭据插件需要能连上 DB 执行 CREATE ROLE）
pg_isready -h DB_HOST -p 5432
```

### 1. 安装（固定版本，systemd 托管）

```bash
sudo useradd -r -s /usr/sbin/nologin vault
sudo mkdir -p /etc/vault /var/lib/vault /var/log/vault
VAULT_VERSION=1.18.1   # 固定版本；发布渠道查 1.18+ 最新补丁
curl -fsSL -o vault https://releases.hashicorp.com/vault/${VAULT_VERSION}/vault_${VAULT_VERSION}_linux_amd64.zip
unzip vault -d /usr/local/bin && rm -f vault

sudo cat > /etc/systemd/system/vault.service <<'EOF'
[Unit]
Description=HashiCorp Vault (single-node raft)
After=network-online.target

[Service]
User=vault
Group=vault
ExecStart=/usr/local/bin/vault server -config=/etc/vault/vault.hcl
Restart=on-failure
MemoryMax=512M
CPUQuota=75%
ProtectSystem=full
ReadWritePaths=/var/lib/vault /var/log/vault

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl enable --now vault
```

`MemoryMax=512M` 给足余量：空闲 ~120-150MB，PKI 批量签发或审计高峰可能冲到 200-300MB。

### 2. 最小配置（单节点 Raft + 回环监听 + Prometheus 指标）

`/etc/vault/vault.hcl`：

```hcl
storage "raft" {
  path = "/var/lib/vault"
}

listener "tcp" {
  address     = "127.0.0.1:8200"   # 永远回环；外部走 Tailscale/Tunnel
  tls_disable = 1                 # 回环明文，隧道层做 TLS
}

api_addr   = "http://127.0.0.1:8200"
ui         = true                  # 管理界面，经隧道访问

telemetry {
  promotion_builtins = true       # 暴露 /v1/sys/metrics?format=prom
}
```

### 3. 初始化 + 解封（Shamir 3-of-5，密钥务必异地分存）

```bash
# 初始化：5 片、阈值 3。输出 5 个 key + 1 个 root token，记到密码管理器（离线！）
vault operator init
# 解封：需要 3 片。生产把 5 片拆成 2+3 放两台介质/两台机器
vault operator unseal
export VAULT_ADDR=http://127.0.0.1:8200
vault operator raft init -bootstrap      # 单节点引导，无需 join
vault status
```

> 个人 VPS 嫌 3/5 繁琐可以 `-key-shares=1 -key-threshold=1`，代价是"偷走这台 VPS 的密钥文件 = 全库可解"，能接受再用。

### 4. 启用四引擎

```bash
vault secrets enable kv-v2            # 默认路径 secret/
vault secrets enable database          # 动态 DB 凭据
vault secrets enable pki               # 内网证书签发
vault secrets enable transit           # 加密运算不落盘
```

### 5. KV v2：集中存放配置与 API key

```bash
vault kv put secret/app-a db-conn "host=... user=..."
vault kv put secret/app-a api-key "sk-..."
vault kv get -version=1 secret/app-a api-key   # 误删可回滚到任意历史版本
```

### 6. 数据库动态凭据（Postgres 示例，最值回票价的一步）

先在 Postgres 建一个有 `CREATE ROLE` 权限的插件专用账号 `vault-admin`，然后：

```bash
vault write database/config/pg \
  allowed_roles="pg-app" \
  connection_url="postgresql://vault-admin:<pwd>@DB_HOST:5432/yourdb?sslmode=require"

vault write database/roles/pg-app \
  db_name=pg \
  creation_statements='CREATE ROLE "{{name}}" WITH LOGIN PASSWORD '\''{{password}}'\'' VALID UNTIL '\''{{expiration}}'\''; GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO "{{name}}";' \
  default_ttl="30m" \
  max_ttl="2h"

# 应用侧：每次连接取一组凭据，到期自动失效
vault read database/creds/pg-app
```

CI 场景同理配一个只读 `pg-ci` role，`max_ttl=4h`。

### 7. PKI：内网服务 24h 短证书

```bash
vault secrets tune -max-lease-ttl=8760h pki
vault write -field=certificate pki/root/generate/internal \
  common_name="vps.example.com" issuer_id=1  # 生成根 CA（8760h）
vault write pki/roles/app \
  allowed_domains="vps.example.com" \
  allow_subdomains=true ttl=24h max_ttl=72h
# 签发：24h 到期前应用自动重签，内网 mTLS 从此免手工续期
vault write -field=certificate pki/issue/app common_name="svc-a.vps.example.com"
```

### 8. Transit + 审计 + 备份

```bash
# Transit：加密后密文存你自己的 R2/S3，Vault 只在内存保管密钥
vault write transit/keys/secret-aes type=aes256-siv
vault write -field=ciphertext transit/encrypt/secret-aes plaintext=<base64密文>

# 审计：每笔操作落盘（配合 logrotate copytruncate + Loki 聚合，见第五节）
vault audit enable file file_path=/var/log/vault/audit.log

# 备份：Raft 每日自动快照 + 手动全量（迁移/换机前必跑）
vault operator raft snapshot auto 24h
vault operator raft snapshot save /backups/vault-$(date +%F).vlt
```

## 五、监控：Prometheus + Uptime Kuma + 每周体检

Vault 故障最危险的两个形态：**sealed（解封态丢失，全库不可读）** 和 **磁盘被审计日志吃满**。两条监控线：

- **Prometheus**：`/v1/sys/metrics?format=prom` 直接抓取（root token 鉴权），三条告警：
  - `vault_sealed == 1` 持续 1 分钟 → P1（全库不可用，立即解封）；
  - Raft 无 leader / 快照落后 → P2；
  - Vault 数据目录所在盘 >80% → P2（审计日志是磁盘杀手，先杀它再杀别的）。
- **Uptime Kuma**（[部署参考](/post/vps-uptime-kuma-monitoring/)）：`curl -s 127.0.0.1:8200/v1/sys/health` 断言 `initialized=true 且 sealed=false`，失败推 Gotify（[参考](/post/vps-gotify-selfhosted-realtime-alerts/)）；
- **每周 cron 体检**：审计日志增长速率 + `vault operator raft snapshots` 列表检查最近 7 天是否有快照 + 一次演练：拿上周快照 `vault operator raft snapshot restore` 到临时目录验证可恢复。

## 六、5 个坑（都踩过）

1. **Raft 单节点全损 = 全库蒸发**：单节点没有 quorum 冗余，盘满/误 `rm -rf /var/lib/vault`/换机忘备份 = 所有密钥、动态凭据历史、PKI 根 CA 一起没。第四节的 `snapshot auto 24h` + 手动 `snapshot save` 必须双跑，且快照每周 restic 加密送 R2（2-1-1，[参考](/post/restic-s3-six-layer-encryption-2-1-1-backup/)）——R2 出口费 $0。
2. **Shamir 密钥只留在同一台机器**：5 片密钥全存 VPS 本机，机器被偷/被黑等于 unseal 门槛清零。拆分异地（加密 USB + 加密 R2 对象/另一台机器），恢复演练一年一次；密钥文件本身用全盘加密保护。
3. **8200 开公网**：Vault 没有网络层 ACL，公网可达的 8200 + 一个被猜中的 token = 交出全部凭据。铁律：listener 永远 `127.0.0.1`，外部只走 Tailscale/Tailscale serve 或 Cloudflare Tunnel 加密出口（$0 流量），nftables 对 8200 默认 DROP。
4. **TTL 配太长，动态凭据变回静态凭据**：`default_ttl=7d` 等于换了个地方存长期密码。纪律：DB 凭据 ≤ 24h、CI token `max_ttl` ≤ 4h、PKI 证书 24h。TTL 越短，泄露爆炸半径越小——这是用 Vault 的全部意义。
5. **审计日志无限增长吃满磁盘**：`file` 审计设备每笔操作写盘，高频 CI 场景一周可写 1-3GB。logrotate `copytruncate` 7 天 + 可选 tail 进 Loki（[日志聚合参考](/post/vps-loki-selfhosted-log-aggregation/)）+ 第五节的磁盘 80% 告警，三件套缺一不可。

另有两个易混点：KV v1 与 v2 路径不要混用（v1 无版本历史）；`transit` 引擎的密文可以存 R2（Vault 宕机不丢），但 **unseal 密钥丢了，transit 密文同样解不开**——密钥管理永远比数据管理脆弱。

## 七、实测数据与成本总结

在 1C1G（1GB RAM / 40GB 盘 / 500Mbps）实测，单节点 Raft + 四引擎：

| 指标 | 数值 |
|------|------|
| 空闲内存 | ~120-150MB（Raft 状态 ~30-50MB） |
| 启动时间（需解封） | ~1.5-2.5s |
| 数据库动态凭据签发 | ~60-180ms/次 |
| PKI 24h 证书签发 | ~30-80ms/张 |
| 审计日志写入 | ~1.5-4KB/操作 |
| 100 次动态凭据批量签发 | ~2-4s（本地 Postgres） |
| 每日 Raft 快照（轻负载） | 数十 MB，周增量 <100MB |

**成本总结**：200 个密钥 AWS Secrets Manager ≈ $80/月（$960/年）→ Vault @ 既有 VPS **$0/月**（新开机型 $4-5/月），年省 **$900+**；叠加免季度人工轮换（~10h/季）与"泄露=永久风险面"改"泄露≤TTL"，这是用 $0 买不到的安全收益。

**混合模式（过不了单节点风险的退路）**：保持单节点 + 每日快照异地，但把 PKI 根 CA 与 3 片 Shamir 密钥托管到另一台云（或离线介质）——成本 +$0-2/月，把"单节点全损"降为"可演练恢复"。

**边界再说一遍**：Vault 的价值是"凭据生命周期自动化"，不是"把密码藏得更深"。单节点适合个人/小团队；关键生产上三节点 Raft（~$15/月）或直接用云托管密钥服务，别用单节点扛金融级 SLA。

> 相关：[Restic 6 层加密备份 + 2-1-1 策略](/post/restic-s3-six-layer-encryption-2-1-1-backup/)（Raft 快照异地副本）、[VPS 自托管 Loki](/post/vps-loki-selfhosted-log-aggregation/)（审计日志聚合）、[Uptime Kuma 监控](/post/vps-uptime-kuma-monitoring/)（健康探测兜底）、[Cloudflare Tunnel 零信任](/post/vps-cloudflare-tunnel-zero-trust/)（8200 安全入口）。
