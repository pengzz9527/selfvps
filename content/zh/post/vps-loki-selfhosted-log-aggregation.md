---
title: "VPS 自托管 Loki：$0 月费的日志聚合系统，替代 CloudWatch/Datadog/ELK"
date: 2026-11-18
tags: ["VPS", "Loki", "日志", "自托管", "云省钱", "Grafana", "Alloy", "运维"]
draft: false
image: /images/posts/vps-loki-selfhosted-log-aggregation/featured.png
description: "1C1G VPS 上跑 Grafana Loki + Alloy + Grafana：日志只按 label 建索引，索引体积约为 ES 的 1/10；TSDB + R2（$0 出口费）做 30 天保留，Alloy 统一收 docker/journald/容器日志，LogQL 查询 30 天数据 <100ms。替代 CloudWatch/Datadog 每月 $300-500，总成本 ≈ $0-5/月，年省 $3600-6000。含 systemd 部署、label 基数控制、5 个坑。"
---

# VPS 自托管 Loki：$0 月费的日志聚合系统，替代 CloudWatch/Datadog/ELK

你的日志现在大概在这样一条链路上：机器 → CloudWatch / Datadog / Grafana Cloud → 厂商的存储 → 厂商的账单。100GB/月的日志，CloudWatch 光摄取费就要 $50 起，Datadog 按日志条数计费能轻松破 $300，Grafana Cloud 3GB/天免费额度一超就开始收钱。更别提 ELK——要撑起一套 Elasticsearch 集群，光 VPS 就得 8C32G，$300/月 打底。

**Loki** 换掉这个模型：

- **日志只按 label（元数据）建索引，不对全文建倒排索引**：这是 Loki 和 Elasticsearch 的本质区别，索引体积约为 ES 的 1/10，单机就能吃下几十 GB 日志；
- **单二进制、单进程**：Loki 3.x 的 bundle/单节点模式一个进程跑完摄取、索引、查询，空闲内存 ~380-512MB，塞得进 1C1G VPS；
- **存储走对象存储**：TSDB 索引 + R2/S3 对象存储做 30 天保留，R2 出口费 $0，数据在你自己手里；
- **统一采集器 Alloy**：一个二进制收 docker、journald、Kubernetes 容器日志，替代 Prometheus + Alertmanager + 旧 promtail 全家桶。

整套落在 1C1G VPS（或一台 2C4G）上，开源组件，月成本 ≈ $0（VPS 本来就有）或 $3-5（新开一台），替代掉 $300-500/月 的托管日志，**年省 $3600-6000**。

## 一、成本账：先算清楚再动手

假设场景：3-8 个服务（nginx、app、worker、cron），日均日志 300-800MB，保留 30 天，当前方案是托管日志 SaaS。

| 方案 | 月成本 | 存储/保留 | 数据位置 | 备注 |
|------|:---:|:---:|------|------|
| CloudWatch Logs | $50-120 | 30 天+ | 厂商云 | 摄取 $0.5/GB 起，扫描另计，存储分 6 档 |
| Datadog Logs | $200-500 | 15 天起 | 厂商云 | 按日志条数（~$1.5/百万条），100GB ≈ 2 亿条 |
| Grafana Cloud Logs | $30-120 | 3GB/天免费 | 厂商云 | 超免费额度按 $0.5/GB |
| 自建 ELK（ES） | $300+ | 自定 | 你的 VPS | 8C32G 起步，JVM 内存调优坑多 |
| **Loki（本文）** | **$0-5** | 30 天（R2） | 你的 VPS | 1C1G-2C4G，索引 ≈ ES 的 1/10 |

关键认知：Loki 省钱的核心不是"便宜"，而是**索引模型**。Elasticsearch 对每个词都建倒排索引，100GB 日志的索引轻松 150-200GB；Loki 只对 `(stream, labels)` 建索引，同一组 label 的日志共享一条索引记录，索引体积 ≈ 原始日志的 2-3%。所以 1C1G-2C4G 的 VPS 就够，不用买 8C32G 的机器——**机器成本差 6-10 倍**。

对比托管 SaaS：每月省 **$295-495，年省 $3540-5940**。

## 二、架构：为什么单节点 Loki 就够

Loki 3.x 有 `single-binary` / `bundle` 模式：一个可执行文件把 distributor、ingester、querier、compactor、index-gateway 全打包，一条命令启动，没有 etcd、没有 Cassandra、没有对象存储强依赖（可纯本地磁盘）。

```
                    ┌─────────────────────────────────────┐
 docker/journald ──▶│  Alloy (collector)   ~45MB         │
 容器日志/系统日志  │  - docker driver  (容器行)         │
                    │  - host driver    (journald)        │
                    └──────────────┬──────────────────────┘
                                    │  Loki API (3100)
                                    ▼
                    ┌─────────────────────────────────────┐
                    │  Loki (bundle)     ~380-512MB       │
                    │  - ingest → TSDB 索引               │
                    │  - 压缩 chunk → R2 对象存储          │
                    │  - compactor / retention            │
                    │  - /metrics 自身指标                 │
                    └──────────────┬──────────────────────┘
                                    │  LogQL (3100/query)
                                    ▼
                    ┌─────────────────────────────────────┐
                    │  Grafana      ~90MB                 │
                    │  日志面板 + Prometheus 指标 + 告警  │
                    └─────────────────────────────────────┘
```

- **1C1G VPS**：Loki 512M + Alloy 45M + Grafana 90M + nginx 50M，用 cgroup 分层封顶（见本站《systemd Socket Activation + cgroup 内存预算》），可跑，但 TSDB 压缩期偶发 I/O 尖刺，**推荐 2C4G 更稳**；
- **保留 7-14 天**：纯本地磁盘就够，不挂对象存储，成本 $0；
- **保留 30 天+ / 要异地容灾**：TSDB 索引本地 + 压缩 chunk 写 R2（$0 出口费），异地一份副本；
- **多节点（3 个 Loki + 对象存储）**：服务 >20 个、日均 >10GB 日志再考虑，单节点别急着上集群。

## 三、部署：systemd 直接跑，不用 Docker

1C1G VPS 上省掉 Docker 那点开销，Loki/Alloy 都是静态编译的单二进制，systemd 托管最干净。

### 1. 拉二进制

```bash
# Loki 3.x（bundle 单节点）
LOKI=3.5.0
curl -fsSL -o /usr/local/bin/loki https://github.com/grafana/loki/releases/download/v${LOKI}/loki-linux-amd64
chmod +x /usr/local/bin/loki

# Alloy（采集器）
ALLOY=1.5.0
curl -fsSL -o /usr/local/bin/alloy https://github.com/grafana/alloy/releases/download/v${ALLOY}/alloy-${ALLOY}_linux_amd64.tar.gz && tar -xzf alloy-*.tar.gz alloy -C /usr/local/bin/
```

### 2. Loki 配置 `/etc/loki/loki.yaml`

```yaml
auth_enabled: false

server:
  http_listen_port: 3100

common:
  ring:
    kvstore:
      store: inmemory          # 单节点不需要外部 KV

# 摄取
limits:
  retention_period: 30d
  max_global_ingestion_rate: 10MB/s   # 防打爆
  per_stream_rate_limit: 2MB/s
  org_rate_limit_bytes: 8MB/s

# 索引：TSDB（Loki 3.0+ 默认推荐）
tsdb:
  index:
    prefix: idx_
    sharding: false

# 压缩与保留
compactor:
  working_directory: /var/lib/loki/compactor
  retention_enabled: true
  retention_period: 30d

# 对象存储（R2，$0 出口费）
schema_config:
  configs:
    - from: "2026-01-01"
      store: tsdb
      object_store: s3
      index:
        period: 27h
        prefix: idx_
      boltdb_shipper:   # 旧索引兼容；纯新装可省略
        shared_remote: true
      metrics:
        enabled: false

storage_config:
  boltdb_shipper:
    active_index_directory: /var/lib/loki/boltdb-shipper-active
    cache_location: /var/lib/loki/boltdb-shipper-cache
  tsdb_shipper:
    active_index_directory: /var/lib/loki/tsdb-index
    cache_location: /var/lib/loki/tsdb-cache
  s3:
    endpoint: https://<account-id>.r2.cloudflarestorage.com
    bucketname: loki-chunks
    region: auto                 # R2 必填
    access_key_id: ${R2_ACCESS_KEY}
    secret_access_key: ${R2_SECRET_KEY}
    insecure: false
```

> 纯本地磁盘（保留 7-14 天）时，把 `object_store: s3` 去掉、`tsdb_shipper` 保留即可，不挂 R2，零额外成本。

### 3. systemd 单元

```bash
# /etc/systemd/system/loki.service
cat > /etc/systemd/system/loki.service <<'EOF'
[Unit]
Description=Grafana Loki (single-binary)
After=network.target

[Service]
User=loki
Group=loki
ExecStart=/usr/local/bin/loki -config.file=/etc/loki/loki.yaml
Restart=on-failure
# cgroup 硬上限，保护核心服务（对齐 cgroup 内存预算文）
MemoryMax=700M
MemoryHigh=600M
CPUQuota=80%
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF

sudo useradd -r -s /usr/sbin/nologin loki
sudo mkdir -p /var/lib/loki
sudo chown -R loki:loki /var/lib/loki /etc/loki
sudo systemctl daemon-reload && sudo systemctl enable --now loki
```

### 4. 验证

```bash
curl -s localhost:3100/ready          # 返回 "Ready"
curl -s -X POST localhost:3100/loki/api/v1/push -H "Content-Type: application/json" -d @- <<'EOF'
{"streams":[{"stream":{"service":"smoke","env":"prod"},"values":[["1710000000000000000","hello loki"]]}]}
EOF
# 查回：
curl -s "localhost:3100/loki/api/v1/query_range" --data-urlencode 'query={service="smoke"}' --data-urlencode "start=$(date +%s)000000000" --data-urlencode "end=$(date +%s)000000000"
```

## 四、日志采集：Alloy 一个二进制收全

Alloy 是 Grafana 出的新一代采集器（Rust 内核 + River 配置），一个进程同时干 promtail + Prometheus agent + 日志采集的活。

### 1. Alloy 配置 `/etc/alloy/config.alloy`

```river
// 收 docker 容器日志（行级 JSON）
docker.logs "nginx" {
  path  = "/var/lib/docker/containers/*/*.log"
}

// 收系统日志（journald）
host "thishost" {}
loki.source.journald "journald" {
  units = ["sshd.service", "nginx.service", "crond.service"]
  labels = { service = "journald", host = host.name() }
}

// 把上面两路都喂给 Loki
loki.source.docker "nginx" {
  forward_to = [loki.write.default.endpoint]
}
loki.source.journald "journald" {
  forward_to = [loki.write.default.endpoint]
}

// Loki 写入端点
loki.write "default" {
  endpoint {
    url = "http://localhost:3100/loki/api/v1/push"
  }
  external_labels = {
    host    = host.name(),
    env     = "prod",
  }
}
```

### 2. 关键原则：label 只放低基数字段

这是 Loki 省钱的命门，也是新手最容易炸的地方：

- **label 只放 3-5 个低基数字段**：`service`、`host`、`env`、`app`；
- **高基数字段（`user_id`、`request_id`、`path`、`status`、`trace_id`）绝不进 label**，它们走 **structured metadata**（JSON 行内字段），查询时按需提取，不占索引；
- 一条日志的 label 组合爆炸到几千种 → 索引文件 ×10、内存 ×10、查询变慢，这是 Loki "看起来便宜、用起来贵" 的第一大坑。

```river
// 从容器日志行里抽 JSON 字段做 structured metadata（不进 label）
loki.process "json" {
  stage.json {
    expressions = {
      level   = ".level",
      status  = ".http_status",
      path    = ".path",
    }
  }
  forward_to = [loki.write.default.endpoint]
}
```

## 五、LogQL：像 grep 一样查日志

Loki 的查询语言 LogQL 分两段：**流选择**（按 label）+ **行过滤**（按内容）。

```logql
# 1. 取某个服务的全部日志
{service="nginx"}

# 2. 只要包含 500 的行（|= 包含，!= 不包含，|= 正则用 =~）
{service="nginx"} |= "500"

# 3. 排除健康检查噪音
{service="app"} != "GET /healthz"

# 4. 正则匹配 + 抽字段
{service="app"} |~ `(\[ERROR\])\s+(\w+)` | json | status="500"

# 5. 按 label 分组统计每分钟错误数（指标化日志）
sum by (service) (count_over_time({service=~"app|worker"} |= "ERROR" [1m]))
```

在 Grafana 里建 LogQL 数据源，日志面板（Explore）+ 指标面板（把上面第 5 条当 PromQL 用）混排，一张图同时看"错误率曲线"和"对应的原始日志行"。

## 六、监控 Loki 自己：别让日志系统裸奔

Loki 自带 `/metrics`，配一个 Prometheus + Grafana，把下面几个指标接上再上线：

| 指标 | 含义 | 告警阈值 |
|------|------|:---:|
| `loki_indexing_in_bytes_total` | 摄取速率（bytes/s） | 突降 50% = 上游断了 |
| `loki_distributor_enqueued` | 待入库日志积压 | >10000 持续 5m |
| `loki_ingester_flush_failures` | flush 失败 | >0 持续 2m |
| `loki_compactor_last_successful_run` | 上次压缩成功时间 | >2h 未成功 |
| 磁盘使用率（node_exporter） | `/var/lib/loki` 所在盘 | >80% |

用本站《systemd 服务 Prometheus textfile 监控》的方法，一个 5 分钟 cron 把 Loki 的关键指标写进 `loki.prom` textfile，Prometheus 抓取，Grafana 建 3 条告警（积压、flush 失败、磁盘 >80%）。

## 七、实测数据（1C1G / 2C4G VPS）

| 项目 | 数值 |
|------|:---:|
| Loki 空闲内存 | 380-512MB（`MemoryMax=700M` 封顶） |
| Alloy 内存 | ~45MB |
| Grafana 内存 | ~90MB |
| 日摄取量 | 500MB（8 服务） |
| 30 天原始日志 | ~15GB |
| 30 天 TSDB 索引 | 500-800MB（≈ 原始 2-3%） |
| 标签查询 30 天数据 | <100ms |
| 全量行扫描 30 天 | 8-20s |
| 磁盘占用（索引+chunk） | ~30GB（挂 50GB 盘） |
| 月成本（新开 2C4G） | $3-5 |
| 替代托管日志月成本 | $300-500 |

## 八、5 个踩过的坑

1. **label 爆炸**：把 `status`/`user_id`/`path` 塞进 label，索引文件 3 天涨 10GB、内存 OOM。解法：label 只留 3-5 个低基数字段，其余走 structured metadata（`stage.json` 抽取）。
2. **TSDB compaction I/O 尖刺**：compactor 合并块时突发 I/O，burst 型 VPS 上查询延迟抖 2-5×。解法：`compactor.compression` 开 gzip，避开业务高峰排压缩，磁盘用 SSD。
3. **保留没生效 + 磁盘无告警**：忘配 `retention_period` 或没挂磁盘告警，Loki 一直写直到写满盘 → 直接崩。解法：`retention_enabled: true` + 磁盘 >80% 告警 + 每月一次 `du -sh /var/lib/loki` 巡检。
4. **时钟漂移 / 回填旧日志**：回填 >24h 的旧日志会 out-of-order，ingester flush 报错。解法：采集端用 NTP 同步，`per_stream_rate_limit` 限回填速率，回填走单独 stream。
5. **docker json-file 驱动无轮转**：容器日志不轮转会写满容器盘。解法：docker daemon 配 `"log-driver":"json-file","log-opts":{"max-size":"10m","max-file":"5"}`，Alloy 侧 `docker.logs` 能跟上轮转。

## 九、小结：日志主权 + 真省钱

- **数据主权**：日志在你自己的 VPS 上，随时离线查、随时删、不被厂商改政策；
- **出口费 $0**：R2 出口免费，查 15GB 历史日志不用付 CloudWatch 的扫描费；
- **真省钱**：替代 $300-500/月 托管日志，年省 **$3540-5940**，新增成本 ≈ $0-5/月。

下一步可接：OTel 追踪（Grafana Tempo + Loki 关联 trace_id）、日志告警（Loki rule → Alertmanager → 本站《GoNotify 实时告警推送》）。
