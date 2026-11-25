---
title: "VPS 自托管 Meilisearch：$0/月替代 Algolia 搜索"
date: 2026-11-25
tags: ["VPS", "Meilisearch", "Algolia", "搜索", "自托管", "云省钱", "运维"]
draft: false
image: /images/posts/vps-meilisearch-selfhosted-algolia-replacement/featured.png
description: "Meilisearch（Rust 引擎，AGPL-3.0，v1.57）单二进制，空闲 ~50-100MB：容错搜索 + 分面过滤 + 排序规则一体。1C1G 上把 max-indexing-memory 压到 256MB + cgroup 硬顶 512M 防 OOM；每日 --schedule-snapshot 快照 restic→R2（出口费 $0），每月 --import-snapshot 演练；前端只发一把只读搜索 key。$0-5/月替代 Algolia Grow（典型站点 $15-126/月），年省 $180-1500。含 systemd 加固、监控告警与 5 个坑。"
---

# VPS 自托管 Meilisearch：$0/月替代 Algolia 搜索

搜索是"隐性账单"里涨得最凶的一项：Algolia 按搜索请求数 + 记录数双计费，一个不防抖的 SaaS 应用每月 18 万次搜索就是 $85+，中型电商 24 万记录 + 15 万次搜索是 $126+/月——而 90% 的用法只是"网站站内搜索 + 文档搜索 + 商品搜索"这类关键词检索。把这类负载换到 1C1G VPS 上的 Meilisearch，搜索请求量不再计价，账单直接砍到 $0-5/月。

**Meilisearch** 是什么：Rust 编写的开源搜索引擎（AGPL-3.0，Meili 公司开源），LMDB 存储，单二进制无外部依赖。原生容错拼写（typo-tolerant，"seach" 也能搜到 "search"）、多语言、分面过滤（facets）、可配置排序规则（ranking rules），REST API 五分钟接入。当前版本 **v1.57**（2026-11-16 发布），1.x 稳定线。

**为什么选它而不是 Elasticsearch/OpenSearch**：ES 全家桶（JVM + 集群协议 + ILM）在 1C1G 上跑不动、运维重；Meilisearch 单进程、~50-100MB 空闲内存、350MB 的下载量解压即用，为"站内搜索"这类规模就是最优解。100 万文档以上再考虑 ES 或托管。

## 一、成本账：先算清楚再动手

场景：一个 SaaS/电商站点需要 10-50 万记录、每月 5-18 万次搜索，当前用 Algolia（2026-10 价格）。

| 方案 | 月成本 | 搜索请求 | 记录数 | 备注 |
|------|:---:|:---:|:---:|------|
| Algolia Free | $0 | 1 万 | 5 万 | 超量需升级 |
| Algolia Grow（文档站：2 万记录 + 4 万搜索） | ~$15 | 10K 内含 | 10 万 | 超额 $0.50/1K 请求、$0.40/1K 记录 |
| Algolia Grow（SaaS：5 万记录 + 18 万搜索，无防抖） | ~$85 | 10K 内含 | 10 万 | 不防抖的搜索量直接烧钱 |
| Algolia Grow（中型商店：24 万记录 + 15 万搜索） | ~$126 | 10K 内含 | 10 万 | 记录超额 $0.40/1K |
| Algolia Grow Plus（AI 排序） | ~$297 | 10K 内含 | 10 万 | 超额 $1.75/1K 请求 |
| **Meilisearch @ 1C1G VPS** | **$0-5** | **不限** | **不限** | VPS 已有则 $0；新开机型 $3-5 |

**年省 $180-1,500**（典型站点）；中型商店替换后年省 $1,500-4,300。搜索请求不再计量 = 突发流量（营销活动、被引用上热搜）不再产生账单尖峰。

**边界要说清**：自托管 ≠ 白嫖。你放弃了厂商的 99.99% SLA 和 AI 排序（NeuralSearch），换来的是：搜索量不计量、数据全在 R2（出口费 $0）、没有厂商按量计费失控风险。搜索挂了不影响下单主流程——应用层降级到数据库 LIKE 查询即可（fail-open）。

**AGPL 注意**：自托管、不改引擎 = 零成本零义务；若你修改 Meilisearch 源码并以服务形式对外提供，需开源修改部分。内部使用不触发。

## 二、原理：为什么单进程能扛站内搜索

Meilisearch 架构核心：LMDB 内存映射索引 + 异步任务队列（所有写操作进队列后台构建）：

| 能力 | 说明 | 对应 Algolia 计费项 |
|------|------|------|
| 容错拼写 | typo-tolerance，编辑距离可配（默认 1 字符 1 错、2 字符 2 错） | 基础功能 |
| 分面过滤 | facets 按字段分组 + 计数（v1.56 新增 sampledCount 大目录采样加速） | 基础功能 |
| 排序规则 | rankingRules 可配（typo → words → proximity → attribute → customRank → criteria） | 部分在 AI 计划 |
| 模糊/精确混合 | filter + q 组合，facet 分布可限制 | 基础功能 |
| 异步写 | 文档 POST 立即返回 task id，后台增量建索引 | 按写操作计费 |

关键设计点：

- **内存有红线**：`--max-indexing-memory` 默认吃系统 RAM 的 2/3（1G 机器 = 665MB）——共享 VPS 上必须显式压低（见部署节），另有 `--experimental-reduce-indexing-memory-usage`（LMDB WRITEMAP）进一步降驻留内存；
- **磁盘即上限**：索引数据 + 任务库 + 快照都在数据目录，10 万文档 ≈ 200-400MB，10-20GB 的 VPS 磁盘毫无压力；
- **搜索不占建索引线程**：`--max-indexing-threads` 默认 = 可用核数的一半；但**单核机器上索引只能抢那唯一的核心**——索引窗口期搜索会变慢（官方文档明确说明），所以重索引要避开高峰；
- **密钥分层**：master key 只留服务端；前端只发一把只读 search key（权限 scope 到单索引 + search 动作）。

## 三、架构：一台 VPS 上的四个角色

```
 [前端 JS / API / 爬虫索引器]
        │  HTTPS (443, 只发只读 search key)
        ▼
 [Caddy/Nginx 反代]
        │  127.0.0.1:7700 + Authorization: Bearer ***
        ▼
 ┌─────────────────────────┐
 │  Meilisearch (单进程)    │
 │  --env production        │
 │  max-indexing-memory 256M│
 │  cgroup 硬顶 512M        │
 └────┬───────────────┬────┘
      │ /stats /tasks │ snapshots/ (每日 24h 快照)
      ▼               ▼
 [Prometheus /metrics]  [restic 夜备 → R2 ($0 出口)]
 [3 条告警]             [7 代保留, --import-snapshot 恢复]
```

要点：

- **7700 默认绑 127.0.0.1**（Meilisearch 出厂默认 localhost:7700）：公网面走 Caddy/Traefik 反代 + TLS；纯内网搜索直接 Tailscale（见 [Tailscale 零配置远程访问](/post/vps-tailscale-zero-config-remote-access/)）；
- **快照走 R2**：`--schedule-snapshot`（默认 24h 一次）+ restic 夜备 `snapshots/` + `data.ms/` 到 Cloudflare R2，出口费 $0，7 代保留。注意：S3 直传快照是 **Enterprise 版专属**，社区版用 restic 同步；
- **监控**：`--experimental-enable-metrics` 开 Prometheus `/metrics` 端点（实验特性，升级前确认存在）；不可用就 5 分钟 cron 拉 `/stats` + `/tasks` 落地 textfile（见第五节）。

## 四、部署：systemd + cgroup 加固

### 1. 安装（Debian/Ubuntu 22.04+）

```bash
# 官方 .deb（v1.57）
curl -fsSL https://downloads.meilisearch.meilisearch.cn/meilisearch.deb -o /tmp/meili.deb
# 或 GitHub Releases 官方二进制（~350MB，静态，无依赖）：
#   meilisearch-linux-amd64 → /usr/local/bin/meilisearch
dpkg -i /tmp/meili.deb
meilisearch --version   # v1.57.x
```

（官方 .deb 装完有 systemd 单元和 `meilisearch` 用户，改单元后重新 enable 即可。）

### 2. 密钥

```bash
mkdir -p /etc/meilisearch
# master key：≥16 字节，生产模式必须提供
openssl rand -hex 32 > /etc/meilisearch/master.key
chmod 600 /etc/meilisearch/master.key

cat > /etc/meilisearch/meilisearch.env <<'EOF'
MEILI_MASTER_KEY=***
MEILI_ENV=production
MEILI_NO_ANALYTICS=1
EOF
chmod 600 /etc/meilisearch/meilisearch.env
```

启动后用 master key 生成两把 API key（存好，创建后只显示一次）：

```bash
curl -s -XPOST 'http://127.0.0.1:7700/keys' \
  -H "Authorization: Bearer $(cat /etc/meilisearch/master.key)" \
  -H 'Content-Type: application/json' -d '{
  "description": "public read-only search key (ship to frontend)",
  "actions": ["search", "query"],
  "indexes": ["docs", "products"],
  "expiresAt": null
}'
```

- **public search key**：只读、限定索引，可以硬编码进前端 JS——搜不到全量数据也造不成破坏；
- **admin key**（`actions: ["*"]`）：只留服务端 + Tailscale/SSH 隧道，任何写操作走它。

### 3. systemd 单元（cgroup 硬约束）

`/etc/systemd/system/meilisearch.service`（覆盖官方单元的 [Service] 段）：

```ini
[Unit]
Description=Meilisearch search engine
After=network.target

[Service]
User=meilisearch
Group=meilisearch
EnvironmentFile=/etc/meilisearch/meilisearch.env
ExecStart=/usr/local/bin/meilisearch \
  --db-path /var/lib/meilisearch/data.ms \
  --http-addr 127.0.0.1:7700 \
  --max-indexing-memory 256mb \
  --experimental-reduce-indexing-memory-usage \
  --schedule-snapshot \
  --snapshot-dir /var/lib/meilisearch/snapshots \
  --no-analytics
Restart=on-failure
RestartSec=2
# 内存硬顶：1G 机器上 512M，超限 OOM 先杀 Meilisearch 而不是邻居
MemoryMax=512M
MemoryHigh=448M
CPUQuota=150%
LimitNOFILE=65536
# 快照临时暂存在 TMPDIR（全量拷贝），指到数据盘避免 /tmp 满
Environment=TMPDIR=/var/lib/meilisearch/tmp

[Install]
WantedBy=multi-user.target
```

```bash
mkdir -p /var/lib/meilisearch/tmp
systemctl daemon-reload && systemctl enable --now meilisearch
systemctl status meilisearch
```

`--max-indexing-memory 256mb` + `MemoryMax=512M` 双层保险：Meilisearch 自己是软顶（建索引时超了就回退处理），cgroup 是硬顶（超了直接杀进程）——保证 1C1G 上 nginx、systemd、cron 永远活得下来。`--experimental-reduce-indexing-memory-usage`（LMDB WRITEMAP）在 UNIX 上可进一步降驻留内存，代价是写速度略降，小 VPS 划算。

### 4. 公网面（Caddy 反代）

```
search.example.com {
    reverse_proxy 127.0.0.1:7700
    header -Server
    request_header Authorization "Bearer meili_public_search_key_xxx"  # 仅演示；生产用前端自带 key
}
```

前端直接打 `https://search.example.com/indexes/docs/search?q=...`（带只读 key），管理面不暴露。

## 五、搜索 API 实战

```bash
MEILI=http://127.0.0.1:7700
AUTH="Authorization: Bearer $(cat /etc/meilisearch/master.key)"

# 1. 建索引
curl -s -XPOST "$MEILI/indexes" -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"uid":"docs","primaryKey":"slug"}'

# 2. 推文档（10 万条分批 1000/批，异步任务）
curl -s -XPOST "$MEILI/indexes/docs/documents" -H "$AUTH" -H 'Content-Type: application/json' \
  -d @docs_batch.json
# → {"taskUid": 123, ...}  GET /tasks/123 查状态

# 3. 调搜索行为
curl -s -XPATCH "$MEILI/indexes/docs/settings" -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{
    "searchableAttributes": ["title","body","tags"],
    "filterableAttributes": ["tags","category"],
    "typoTolerance": {"minTwoTypos": 1, "minOneTypos": 2},
    "rankingRules": ["typo","words","proximity","attribute","criteria"]
  }'

# 4. 搜索（前端用只读 key）
curl -s "$MEILI/indexes/docs/search?q=seach&filter=tags:backup&limit=10" \
  -H "Authorization: Bearer ***"
# "seach" 拼错照样命中
```

**夜间全量重建（避开高峰，单核索引窗口期搜索会变慢）**：

```bash
#!/usr/bin/env bash
# /usr/local/bin/meili-reindex.sh  02:30 跑
curl -s -XPOST "$MEILI/indexes/docs/documents/delete" -H "$AUTH" -d '{}'
for f in /var/lib/meili-source/docs_*.json; do
  curl -s -XPOST "$MEILI/indexes/docs/documents" -H "$AUTH" -d @"$f"
done
```

配合 `--task-webhook-url`（NDJSON 通知每个任务完成）可以把"全量重建完成"推到 Telegram/Gotify（见 [Gotify 自托管实时告警](/post/vps-gotify-selfhosted-realtime-alerts/)）。

## 六、监控与告警

**首选**：单元加 `--experimental-enable-metrics`，Prometheus 直接 scrape `http://127.0.0.1:7700/metrics`（实验特性，大版本升级前确认端点仍在）。

**保底**（5 分钟 cron → textfile，与 [Valkey 监控](/post/vps-valkey-selfhosted-redis-replacement/) 同款模式）：

```bash
#!/usr/bin/env bash
# /usr/local/bin/meili-metrics.sh
OUT=/var/lib/prometheus/node_exporter_textfile/meilisearch.prom
AUTH="Authorization: Bearer $(cat /etc/meilisearch/master.key)"
curl -s "$MEILI/stats" -H "$AUTH" > /tmp/ms_stats
curl -s "$MEILI/tasks?limit=1&statuses=fail" -H "$AUTH" > /tmp/ms_fail
curl -s "$MEILI/tasks?limit=1" -H "$AUTH" > /tmp/ms_last
failed=$(jq -r '.total' /tmp/ms_fail)
lag=$(jq -r '.results[0].enqueuedAt // empty' /tmp/ms_last)   # 最后任务入队时间
cat > "$OUT" <<EOF
meili_tasks_failed_total $failed
meili_index_size_bytes $(jq '.dbSize' /tmp/ms_stats)
meili_last_task_ts $(date -d "$lag" +%s 2>/dev/null || echo 0)
EOF
```

3 条告警：

| 告警 | 条件 | 级别 |
|------|------|------|
| 索引膨胀 | `meili_index_size_bytes` > 磁盘 70% 水位（10GB 盘 = 7GB） | warning（清理旧数据 / 扩容 / 分索引） |
| 建索引滞后 | 最后任务入队 > 10 分钟仍未 processed（队列积压） | warning（源端写入太猛 / CPU 被占） |
| 任务失败 | `meili_tasks_failed_total` 增长 | critical（payload 超限 / schema 冲突 / 磁盘满） |

Kuma 加 `GET /health`（200 即活，无需 key）做存活探测。

## 七、备份与恢复

Meilisearch 1.x 自带**快照机制**（比旧版 dump 更顺手）：

- `--schedule-snapshot`：默认 24h 自动快照到 `--snapshot-dir`（传值 = 秒数，如 `--schedule-snapshot 43200` 每 12h）；
- `--import-snapshot /path/to/x.snapshot`：启动时导入（**数据目录已存在会报错**——恢复时先清 `data.ms/`）；
- 升级引擎：`--upgrade-db`（dumpless 迁移，v1.51 前叫 `--experimental-dumpless-upgrade`；**非原子操作**，升级前必须先手动导一份快照）。

异地链路（restic → R2，与 [restic 自动备份](/post/vps-restic-automated-backup-s3.md) 同款）：

```bash
# 夜备：快照 + 数据目录 → R2（出口 $0，7 代保留）
restic -r $R2_REPO backup /var/lib/meilisearch
# 每月演练：R2 → scratch → 临时实例导入
restic -r $R2_REPO restore latest -t /tmp/meili-restore
systemctl stop meilisearch
rm -rf /var/lib/meilisearch/data.ms
cp /tmp/meili-restore/snapshots/latest.snapshot /tmp/x.snapshot
meilisearch --import-snapshot /tmp/x.snapshot --db-path /var/lib/meilisearch/data.ms &
# 校验后切回 systemd 管理
```

恢复预期：200-400MB 数据在 50Mbps 带宽下 R2 拉取 + 导入 < 2-4 分钟。

## 八、实测预期（1C1G VPS，经验值）

| 指标 | 数值 |
|------|------|
| 空闲内存 | ~50-100MB（建索引时瞬时 +256MB 缓冲） |
| 磁盘（10 万文档 + 2 代快照） | ~0.5-1GB |
| 搜索 P50（10 万文档） | ~3-15ms，单核 ~500-2000 qps |
| 全量建索引（10 万条，首次） | 1-3 分钟（单核，窗口期搜索变慢） |
| 增量更新（1000 条/批） | 秒级，任务队列异步 |
| 快照 400MB | ~5-15 秒 |

容量红线：1C1G 建议 ≤ 20 万文档；20-100 万上 1C2G；再大上 2C4G 或回托管。

## 九、5 个坑

1. **开发模式 + 公网暴露 = 无锁保险箱**：`--env development` 不配 master key 时所有路由无保护，且默认 7700。公网机器必须 `--env production` + master key（≥16 字节）+ `127.0.0.1` 绑定 + `--no-analytics`。
2. **默认 2/3 RAM 建索引内存没压**：1G 机器默认吃 665MB，一次全量重建把 nginx 挤进 OOM。`--max-indexing-memory 256mb` + cgroup `MemoryMax=512M` + WRITEMAP 三件套必做。
3. **单核上"索引即卡顿"**：1 核机器建索引时索引线程和搜索线程抢同一核，搜索 P99 从 15ms 飙到 200ms+。全量重建放 02:30 低峰 + 分批推送 + 大目录上机直接 2 核。
4. **快照暂存目录 /tmp 爆**：生成快照/升级先往 `TMPDIR`（默认 `/tmp`）拷一份全量数据库——小 VPS 的 /tmp 常在根分区或 tmpfs 上，数据 1GB 就能把 /tmp 打满报 `No space left`。单元里 `Environment=TMPDIR=/var/lib/meilisearch/tmp` 指到数据盘。
5. **dumpless 升级非原子**：`--upgrade-db` 中途失败可能留下损坏库。铁律：升级二进制前先手动导一份快照到 R2，再升；失败回滚 = 旧二进制 + `--import-snapshot`。

## 十、混合模式（不放心就先用这个）

- **开发自托管，生产托管**：前端搜索 URL 走环境变量，staging 全用 Meilisearch，生产留 Algolia，跑稳再切——切换零代码；
- **L1 自托管关键词 + L2 托管 AI 排序**：Meilisearch 承担 95% 流量（不计量），长尾复杂查询/NeuralSearch 路由到 Algolia Grow Plus，账单只付 AI 部分；
- **降级开关**：搜索端点 5xx 时前端自动 fallback 到数据库 `LIKE` + 标题匹配（fail-open），搜索挂了不影响主业务；
- **迁移路径**：Algolia → Meilisearch 用 Algolia 导出 API（`export`）拿 JSON，转 schema 推入即可，双读对比 1 周后下线 Algolia 索引，全程不停服。

---

**总结**：Meilisearch 把"搜索税"从 Algolia 的计量计费打成了 $0-5/月的固定成本：单二进制、10 万文档 P50 3-15ms、搜索量不计量（营销突发零账单）、每日快照 + restic→R2 出口费 $0。前置纪律四条：生产模式 + master key、压死建索引内存、重索引避峰、快照暂存指数据盘。做到这四条，Algolia 的月度账单可以删了。
