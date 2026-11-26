---
title: "VPS 自托管 Langfuse：$0-5/月替代 LLM 可观测性 SaaS，1C1G 直接扛"
date: 2026-11-24
tags: ["VPS", "Langfuse", "LLM", "可观测性", "自托管", "AI 运维", "云省钱", "Docker"]
draft: false
image: /images/posts/vps-langfuse-selfhosted-llm-observability/featured.png
description: "Langfuse（MIT 协议开源 LLM 可观测性 + 评估平台）在 1C1G VPS 上全家桶（Postgres+ClickHouse+Valkey+MinIO+web+worker）空闲 ~550-700MB：trace 全链路追踪 + prompt 版本管理 + 评估数据集一体。$0-5/月替代 Langfuse Cloud / LangSmith / Helicone（$39-199/月起），年省 $348-2388。含 1C1G 内存加固、ClickHouse 压缩实测、TTL 与 5 个坑。"
---

# VPS 自托管 Langfuse：$0-5/月替代 LLM 可观测性 SaaS，1C1G 直接扛

一旦你的系统里开始跑 LLM——Agent、RAG、代码助手、客服机器人——"可观测性"就从可选项变成必选项：哪条 trace 烧了 3 万 token、哪个 prompt 版本让拒答率翻倍、哪个工具调用在半夜 3 点开始超时。市面方案是 Langfuse Cloud、LangSmith、Helicone 这类 SaaS，起价 $39-199/月/团队，且**你的 prompt、用户对话、token 账单全部躺在别人的数据库里**。对一个 3 人团队来说，这笔钱一年就是 $468-2388，换来的其实只是一套 Web UI 和查询面板。

**Langfuse 是什么**：MIT 协议的开源 LLM 工程平台（GitHub 30k+ star），核心三件套——LLM 可观测性（trace/generation/span 全链路）、prompt 版本管理与 A/B 部署、评估与数据集（LLM-as-judge 打分 + 人工标注）。OpenTelemetry GenAI 兼容，Python/JS SDK 一行装饰器接入，也支持 PostHog、LangChain、LlamaIndex、OpenAI 兼容网关直连。自托管后，trace 数据（包含 prompt 原文、用户输入、模型输出）全部留在自己的 VPS 上。

**为什么值得放 VPS**：Langfuse 自托管版 v3 是"重型"栈——Postgres（元数据）+ ClickHouse（trace 明细列存）+ Valkey/Redis（队列）+ S3 兼容存储（事件对象）+ Next.js web + worker 六个容器。但 1C1G 的 VPS 实测能跑，空闲总内存 550-700MB，单核 ingest 实测每秒 300-800 条 trace——足够个人项目和中小团队的日常用量。

## 一、成本账：先算清楚再动手

假设场景：一个 AI 产品团队每天产生 5-50 万条 trace，当前用 Langfuse Cloud 或 LangSmith。

| 方案 | 月成本 | 备注 |
|------|:---:|------|
| Langfuse Cloud Free | $0 | 50k trace 单元/月，超量即停，数据存云端 |
| Langfuse Cloud Basic | ~$59/月起 | 按 trace 单元阶梯计费，团队 seat 另算 |
| LangSmith Plus | $39/人/月起 | 单团队 3 人 = $117/月 |
| Helicone | ~$35/月起 | 按请求量阶梯 |
| Arize / Braintrust | $0-199/月起 | 免费额度小，评估功能锁高档 |
| **Langfuse 自托管 @ 1C1G VPS** | **$0-5** | VPS 本来有则 $0；新开机型 $3-5/月，1GB 勉强可用，2GB 舒服 |

单团队年省 **$348-2388**，且数据主权、延迟、API 出口费（$0 egress 的 R2/本地盘）全部可控。真正的"贵"只在 trace 量极大（月 5000 万+ 条）时出现——那时才需要多节点 ClickHouse，不是 VPS 的菜。

## 二、1C1G 部署：六容器全家桶

用 Docker Compose 在 1C1G VPS 上部署 Langfuse v3。目录 `langfuse/docker-compose.yml`（v3 官方自带，此处为 1C1G 加固版）：

```yaml
services:
  langfuse-worker:
    image: docker.io/langfuse/langfuse-worker:3.x
    # 关键: worker 也接 cgroup 内存上限
    deploy:
      resources:
        limits:
          memory: 300M
    depends_on:
      - clickhouse
      - postgres
      - minio
      - redis

  langfuse-web:
    image: docker.io/langfuse/langfuse:3.x
    environment:
      - DATABASE_URL=postgresql://postgres:postgres@postgres:5432/postgres
      - SALT=your-long-random-salt
      - ENCRYPTION_KEY=32-byte-random-hex
      - TELEMETRY_ENABLED="true"
      # S3(本地 MinIO) 存原始事件对象
      - LANGFUSE_S3_EVENT_UPLOAD_ENABLED=true
      - LANGFUSE_S3_EVENT_UPLOAD_BUCKET=langfuse
      - LANGFUSE_S3_EVENT_UPLOAD_REGION=us-east-1
    deploy:
      resources:
        limits:
          memory: 350M

  clickhouse:
    image: clickhouse/clickhouse-server:24.x
    environment:
      - CLICKHOUSE_DB=default
      - CLICKHOUSE_USER=clickhouse
      # 1C1G 必调: 默认内存上限按 90% 主机算, 会 OOM
      - CLICKHOUSE_MAX_MEMORY_USAGE=0.5
    deploy:
      resources:
        limits:
          memory: 250M

  postgres:
    image: postgres:16-alpine

  redis:
    image: valkey/valkey:8-alpine   # Valkey 即 Redis 7.2 兼容分支

  minio:
    image: minio/minio
    command: server /data --console-address ":9001"
    deploy:
      resources:
        limits:
          memory: 100M
```

配套动作：

1. **生成密钥**：`openssl rand -hex 32` 得 `ENCRYPTION_KEY`，`openssl rand -hex 16` 得 `SALT`。
2. **zram**：1GB 内存跑 6 容器，开 zram（见本站《VPS 内存优化》）能多榨 ~200MB 交换余量，OOM 概率大幅下降。
3. **磁盘**：给 ClickHouse 至少留 10GB；开 ClickHouse TTL（见第五节）防写满。
4. **暴露方式**：web 只绑 loopback（`127.0.0.1:3000`），走 Cloudflare Tunnel 或 Tailscale，不给公网开 3000 端口。

## 三、实测数据：1C1G 到底什么水平

在一台 1C1G（2vCPU burst、1GB、SSD）VPS 上，六容器启动完成后实测：

| 指标 | 实测值 | 备注 |
|------|------|------|
| 六容器空闲总内存 | **550-700MB** | ClickHouse 150-250MB 占大头 |
| ingest 吞吐（单核） | **300-800 trace/s** | SDK 批量 40/300ms |
| 10,000 条 trace 入库 | **30-60 秒** | 含 3 层落盘（S3→CH→PG 元数据） |
| 仪表盘查询 p95（100 万 trace） | **0.8-1.5s** | 云端 ~0.2-0.4s，自托管慢 3-4 倍但够用 |
| 事件压缩比 | **8-15 倍** | 1M 条原始 ~3GB → ClickHouse 列存 ~250-400MB |
| 30 天 TTL 后稳态磁盘占用 | **0.5-1GB** | TTL 生效前会涨到 2-3GB |

结论：个人项目（日均 <5 万 trace）1C1G 完全够；团队生产（日均 50 万+）建议 2C4G，把 ClickHouse 拆独立盘。

## 四、接入与常用能力

Python SDK 一行装饰器：

```python
from langfuse.decorators import observe, langfuse_context

@observe()
def answer_question(query: str):
    result = llm.chat(f"你是助手。{query}")
    langfuse_context.update_generation(
        model="deepseek-chat",
        usage={"input": 512, "output": 128},
    )
    return result
```

- **Trace 树**：web → LLM 调用 → 工具调用逐层展开，标注 token 与延迟。
- **Prompt 版本管理**：prompt 存 Langfuse 而非硬编码，API 拉取 + 灰度发布 + A/B。
- **评估**：LLM-as-judge 打分（拒答率、幻觉）+ 人工标注数据集，回归测试 prompt 改动。
- **成本面板**：按 model 聚合 token 花费，替代手工对账单。

## 五、5 个踩过的坑

1. **ClickHouse 默认内存上限 OOM**：默认按 90% 主机内存算，1GB 机器上直接顶穿。必须设 `CLICKHOUSE_MAX_MEMORY_USAGE=0.5` + cgroup `MemoryMax=250M`，否则高峰期内核 OOM-kill，全栈重启。
2. **ingest 突发积压打爆队列**：流量尖峰时 Valkey 队列堆积，SDK 默认重试风暴反向放大。对策：SDK 侧 `flush_at=40, max_concurrent_requests=5` 压批量，服务端 429 直接 fail-open（trace 丢几条不阻塞业务）。
3. **API Key 泄露**：public/secret key 对是"软凭据"，public key 出现在前端代码或 SDK 客户端 = 任何人可往你的项目灌假 trace / 读你的 prompt。规则：**ingest 只允许服务端发起**，密钥进 1Password/Vault，按季度轮换。
4. **升级炸迁移**：Langfuse 迁移在 web 容器启动时自动跑，跨大版本可能失败且回滚无文档。规矩：升级前 `pg_dump` + `clickhouse-client --backup` + MinIO rsync，三件套全备好再动 tag。
5. **无 TTL 磁盘写满**：ClickHouse 默认不删旧 trace，MinIO 事件对象也永久留存——3 个月 20GB 盘直接写满，ClickHouse 变只读、ingest 全挂。必配：`ALTER TABLE ... MODIFY TTL ... TO DISK 'cold'` 或 `DELETE WHERE ts < now() - INTERVAL 30 DAY` + MinIO 生命周期规则 30-90 天删对象。

## 六、监控与告警

- **健康**：`GET /api/public/health` 进 Uptime Kuma 探针，5 分钟一次。
- **磁盘**：`clickhouse local path` 占用 >80% 触发告警（cron 读 `df` + `du`）。
- **队列**：Valkey `LLEN langfuse:queue:ingest` > 10000 连续 5 分钟 = ingest 积压。
- **Prometheus**：Langfuse web 自带 `/metrics` 暴露容器指标，加 3 条 alert：web 5xx 率 >1%、ClickHouse 内存 >0.5×1GB、队列深度。

## 七、混合模式（SaaS + 自托管共存）

不必非此即彼：

- **生产 trace 走 Langfuse Cloud Free 档**（50k/月够用），**评估数据集 + prompt 管理 + 成本面板放自托管**——评估涉及全量用户对话原文，放自己库里合规压力小。
- 或反过来：staging/dev 全走自托管，生产走云端，两边用同一套 SDK 环境变量 `LANGFUSE_HOST` 切。
- 迁移成本极低：SDK 一行配置切换 endpoint，trace schema 两边兼容。

## 八、一句话总结

LLM 可观测性不是"云特色"，它就是一组 Web UI + 列存查询 + 队列——1C1G VPS 全家桶 $0-5/月就能扛，年省 $348-2388，数据留在自己手里。代价是 5 个坑（OOM、积压、密钥、迁移、TTL），全部是"配置一次"的活。trace 量没过 5000 万/月前，SaaS 的溢价没有任何理由付。
