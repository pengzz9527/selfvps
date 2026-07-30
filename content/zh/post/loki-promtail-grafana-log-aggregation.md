---
title: "使用 Loki + Promtail + Grafana 构建自托管日志聚合系统"
description: "全面指南：学习如何在 VPS 上部署 Loki 日志聚合系统，结合 Promtail 采集和 Grafana 可视化。实现低成本、高性能的集中式日志管理，替代 ELK Stack，节省资源成本高达 90%。"
date: 2026-07-30T21:00:00+08:00
lastmod: 2026-07-30T21:00:00+08:00
slug: "loki-promtail-grafana-log-aggregation"
image: "/images/posts/loki-promtail-grafana-log-aggregation/featured.png"
tags: ["Loki", "Promtail", "Grafana", "日志聚合", "DevOps", "可观测性", "ELK 替代", "运维工具"]
categories: ["运维工具"]
aliases: [/zh/post/loki-promtail-grafana-log-aggregation/]
---

## 为什么选择 Loki？

在传统的日志解决方案中，**ELK Stack（Elasticsearch + Logstash + Kibana）** 曾经是行业标准。但随着数据量的增长，Elasticsearch 的资源消耗问题日益突出——它不仅要存储日志本身，还要建立完整的索引以支持全文搜索，这对内存和磁盘的要求非常高。

**Grafana Loki** 的出现为这个问题提供了一个优雅的答案。Loki 遵循与 Prometheus 相同的理念：**只索引日志的标签（labels），而不索引日志内容本身**。这种设计带来了以下显著优势：

| 特性 | Elasticsearch (ELK) | Grafana Loki |
|------|---------------------|--------------|
| 索引方式 | 全文索引（所有文本） | 标签索引（仅元数据） |
| 资源消耗 | 高（GB/TB 级日志需 TB 级存储） | 低（仅需存储原始日志文本） |
| 查询速度 | 快但昂贵 | 极快且成本低 |
| 部署复杂度 | 复杂 | 简单，与 Prometheus 兼容 |
| 存储成本 | 高（3-5 倍压缩率） | 极高（10-20 倍压缩率） |

对于大多数 VPS 用户来说，Loki 可以在 **相同的硬件上处理 10 倍以上** 的日志量，而只需要不到原来 1/10 的存储成本。这就是为什么越来越多的团队从 ELK 迁移到 Loki Stack。

## Loki 架构概览

Loki Stack 由三个核心组件组成：

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   Promtail  │────▶│     Loki      │────▶│   Grafana   │
│  (日志采集)   │     │(日志存储 & 查询)│  │  (可视化面板) │
└─────────────┘     └──────────────┘     └─────────────┘
      │                   ▲                   │
      ▼                   │                   │
┌─────────────┐          │            ┌──────────────┐
│ 应用程序    │◄─────────┼────────────│  Docker/K8s │
│ / 容器      │           │            │  / 虚拟机    │
└─────────────┘          │            └──────────────┘
                         │
                 ┌──────────────────┐
                 │ 对象存储 (S3/MinIO)│
                 └──────────────────┘
```

### Promtail：日志采集器

Promtail 是 Loki 的日志客户端代理，负责从各种来源收集日志并发送给 Loki 服务器。它类似于 Filebeat（ELK Stack），但与 Loki 无缝集成，配置更加简单。

### Loki：日志存储服务

Loki 接收来自 Promtail 的日志数据，根据标签对数据进行分片，并将实际日志内容写入后端存储（如本地磁盘或对象存储）。Lofi 不索引日志内容，这使得查询非常高效且成本极低。

### Grafana：可视化查询界面

Grafana 是日志的最终展示层，用户可以通过 Loki 的数据源插件查询日志，并与 Prometheus 指标在同一张仪表板上进行关联分析。这是 Loki Stack 最大的亮点之一——**日志与指标的关联可视化**。

## 快速部署：Docker Compose 方案

对于大多数 VPS 用户，使用 Docker Compose 是最快的启动方式。以下是完整的 `docker-compose.yml` 配置：

```yaml
version: '3.8'

services:
  # ----------------------------
  # Loki - 日志聚合引擎
  # ----------------------------
  loki:
    image: grafana/loki:3.0.0
    container_name: loki
    ports:
      - "3100:3100"
    command: |-
      -config.file=/etc/loki/local-config.yaml
    volumes:
      - ./loki/config:/etc/loki
      - ./loki/data:/tmp/loki/data
    deploy:
      resources:
        limits:
          cpus: '0.5'
          memory: 512M
    restart: unless-stopped

  # ----------------------------
  # Promtail - 日志采集器
  # ----------------------------
  promtail:
    image: grafana/promtail:3.0.0
    container_name: promtail
    ports: []
    volumes:
      - /var/log:/var/log:ro
      - /var/lib/docker/containers:/var/lib/docker/containers:ro
      - ./promtail/config:/etc/promtail
      - /etc/passwd:/etc/passwd:ro
      - /etc/group:/etc/group:ro
    command:
      - -config.file=/etc/promtail/config.toml
    depends_on:
      - loki
    restart: unless-stopped

  # ----------------------------
  # Grafana - 可视化界面
  # ----------------------------
  grafana:
    image: grafana/grafana:11.4.0
    container_name: grafana
    ports:
      - "3000:3000"
    environment:
      GF_SECURITY_ADMIN_PASSWORD: admin123
      GF_PLUGINS_ALLOW_LOADING_UNPLUGINS: "true"
    volumes:
      - ./grafana/data:/var/lib/grafana
      - ./grafana/plugins:/var/lib/grafana/plugins
    restart: unless-stopped

  # ----------------------------
  # MinIO - 可选：Loki 后端存储
  # ----------------------------
  minio:
    image: minio/minio:latest
    container_name: minio
    ports:
      - "9000:9000"
      - "9001:9001"
    environment:
      MINIO_ROOT_USER: admin
      MINIO_ROOT_PASSWORD: securepassword123
    command: server /data --console-address ":9001"
    volumes:
      - ./minio-data:/data
    deploy:
      resources:
        limits:
          cpus: '0.5'
          memory: 1G
    restart: unless-stopped
```

## 配置文件详解

### 1. Loki 配置 (`loki/config/config.yaml`)

```yamlauth:
  enabled: false

server:
  http_listen_port: 3100
  cors_allow_origins:
    - ".*"

distributor:
  receivers:
    otlp:
      protocols: [grpc]
    promql:
    logs:

storage:
  chunk_store_config:
    max_look_back_hour: 168
  local:
    directory: /tmp/loki/data

compactor:
  enabled: true
  compaction_interval: 1h

ruler:
  storage:
    type: local
    local:
      dir: /tmp/loki/ruler

alerting:
  enabled: true
  alerts_to:
    - alertmanager
  
trace:
  enabled: true
  backends:
    - local
```

### 2. Promtail 配置 (`promtail/config/config.toml`)

这是最关键的部分，决定了 Promtail 如何收集日志：

```tomlserver {
  http_listen_port = 9080
  grpc_listen_port = 0
}

positions_directory = "/tmp/positions"

clients:
  - url: "http://loki:3100/loki/api/v1/push"

scrape_configs:
  # ========================
  # 1. Docker 容器日志
  # ========================
  - job_name: docker-system
    docker_sd_configs:
      - host: "unix:///var/run/docker.sock"
        role: containers
    relabel_configs:
      - source_labels: __meta_docker_container_log_stream
        separator: ;
        regex: stdout|stderr
        target_label: log_type
        replacement: "$1"
      - source_labels: __meta_docker_name
        regex: "/(.*)"
        target_label: instance
        replacement: "${1}"
      - source_labels: [log_type]
        separator: ;
        regex: .*
        target_label: labels.__skip_labels__
        action: drop

  # 过滤掉不必要的标签，减少索引大小
    label_attributes:
      ingress_public: ["log_type"]
      ingress_private: ["__skip_labels__"]

  # ========================
  # 2. 系统日志 (journalctl)
  # ========================
  - job_name: journal
    journal:
      max_age: 12h
      mode: systemd
      units: ["docker.service", "systemd.service"]
    relabel_configs:
      - source_labels: __journal_label_systemd_unit
        target_label: unit

  # ========================
  # 3. 自定义应用日志文件
  # ========================
  - job_name: custom-apps
    static_configs:
      - targets:
          - app
        labels:
          job: custom-apps
    tail:
      paths:
        - /var/log/*.log
        - /opt/*/logs/*.log
      read_from_start: false

  # ========================
  # 4. Nginx 访问日志
  # ========================
  - job_name: nginx-access
    static_configs:
      - targets:
          - nginx
        labels:
          job: nginx-access
    tail:
      paths:
        - /var/log/nginx/access.log
      read_from_start: true
      labels:
        stream: access
```

**关键点解释：**

- `relabel_configs`：**最重要的部分**。通过重定位标签来定义 Loki 的索引键。常见的标签包括 `job`, `instance`, `level`, `error_code` 等。
- `label_attributes`：指定哪些标签应该被公开索引（`ingress_public`），哪些应该被排除以节省空间（`ingress_private`）。**不索引的标签将保留在原始日志中，但不计入索引存储成本。**
- `docker_sd_configs`：自动发现新的 Docker 容器，当容器启动时自动开始收集日志。

### 3. Grafana 配置

Grafana 的配置相对简单，主要通过 Web UI 完成数据源设置。在首次访问后（默认用户名 `admin`，密码 `admin123`）：

1. 点击左侧菜单的 **+ Add data source**
2. 选择 **Loki**
3. 输入 URL：`http://localhost:3100`（如果是独立部署，填写正确的 Loki 地址）
4. 保存并测试连接

## 查询语言：LogQL

Loki 使用自己的查询语言 **LogQL（Log Query Language）**，它分为两类查询：

### A. 日志流选择器（Instant Queries）

选择特定标签组合的日志流：

```logql
{job="docker-system",level="error"}
```

可以添加多个标签进行精确筛选：

```logql
{instance="api-server",namespace="production",level="warn"}
```

### B. 范围查询（Range Queries）

用于查看一段时间内的日志：

```logql
{job="nginx-access"}[5m]  // 最近 5 分钟的日志
```

### C. 常用查询模式

**1. 查找错误日志：**
```logql
{job="docker-system",level="error"} |= "panic"
```

**2. 按关键词搜索：**
```logql
{instance="app-service"} |= "authentication failed"
```

**3. 状态码分析：**
```logql
{job="nginx-access"} |~ "200|301|302" | csv_parse "status"
```

**4. 多标签组合查询：**
```logql
{namespace="prod",env="production",level="critical"}
```

### D. 管道操作符

LogQL 支持使用管道符 `|` 对日志内容进行进一步过滤：

```logql
# 先选标签，再过滤内容
{job="docker-system"} |= "ERROR" |~ "timeout"

# 多个条件组合
{job="docker-system",level="error"} |= "database" |!= "connection refused"
```

### E. 统计查询（With Metrics）

Loki 的一大特色是可以将日志查询转化为数值指标：

```logql
# 计算每分钟的错误数
count_overline({job="docker-system",level="error"}[5m])

# 按级别统计日志数量
{job="docker-system"} | level_count(level)
```

这允许你在 Grafana 中将日志指标与 Prometheus 指标放在同一张图表中进行对比分析。

## 实际应用案例

### 案例 1：数据库慢查询监控

PostgreSQL 配置到 Loki 后，你可以这样监控慢查询：

```logql
{pg_service="main",log_line="slow query:"}
```

或者更精确地：

```logql
{job="postgresql",level="LOG"} | "duration:" | parse "duration:\"(?<time>[^,]+)\""
  | time > 1000
  | rate_overline()[5m]
```

这会返回过去 5 分钟内执行时间超过 1000ms 的查询次数。

### 案例 2：Web 服务异常检测

```lognl
{service="frontend-api",level="error"} 
  | "500 Internal Server Error" 
  | rate_overline()[15m] > 5
```

这个查询可以设置为 Grafana 告警规则：如果每分钟 500 错误数超过 5 次就触发通知。

### 案例 3：安全审计日志分析

```logql
{service="auth",log_action="login_failure"}
  | parse "ip=\"(?<ip>[^\"]+)\"" 
  | ip =~ "192\.168\." 
  | count_by(ip)[1h] > 10
```

这可以识别来自内网的异常登录尝试（每小时超过 10 次失败登录）。

## 性能优化建议

### 1. 压缩策略配置

在 Loki 配置中可以调整压缩策略来平衡存储成本和查询性能：

```yamlstorage:
  chunk_store_config:
    max_chunk_age: 15m
    compaction_interval: 2h
  level:
    compaction_level: eager
```

- `max_chunk_age`：旧块被压缩前的最大时间
- `compaction_interval`：触发压缩的时间间隔
- `compaction_level`：激进模式（eager）会频繁压缩但占用更多 CPU，谨慎模式（steady）则相反

### 2. 日志轮转配置

确保你的应用程序配置了合理的日志轮转，避免单个文件过大：

```bash
# logrotate 示例
/var/log/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 644 root root
}
```

### 3. 标签粒度控制

不要给每条日志都打太多标签！这是 Loki 中最常见的性能陷阱。建议只索引那些**经常用于过滤**的标签，其他标签应该放在日志正文中作为普通文本。

### 4. 多实例部署（生产环境）

对于生产环境的 Loki Stack，建议采用分布式部署：

```
┌─────────────┐       ┌─────────────┐
│ Distributor │◄──────│ Distributor │├─ Pushes chunks to ingesters
└─────────────┘       └─────────────┘       │
    │                   │                   ▼
    │                   │         ┌──────────────┐
    └───────────────────┼────────►│  Ingesters   │◄─ Ingestion of log streams
                        │         └──────────────┘
                        │               │
                        ▼               │
                    ┌──────────┐        │
                    │ Query    │◄───────┤ (Replication factor)
                    │ Frontend │        │
                    └──────────┘        │
                        │              │
                        ▼              ▼
                  ┌──────────┐   ┌────────────┐
                  │ Compactor│   │  Storage   │◄─ Local or object
                  │(Merge)   │   │   (S3/MinIO)│ storage
                  └──────────┘   └────────────┘
```

## 与现有生态系统的集成

### Prometheus 联动

Loki 和 Prometheus 天然兼容，因为它们都是 Grafana Labs 的项目。你可以在同一个 Grafana 实例中同时配置两个数据源，并在同一个仪表板中展示：

- 上半部分：CPU/内存/Prometheus 指标（折线图）
- 下半部分：对应时间点的日志（日志浏览器）

这使得**指标异常时的根因分析**变得非常简单：当 CPU 突然飙升时，你可以直接向下钻取到当时的日志查看异常信息。

### Alertmanager 告警

Loki 可以与 Alertmanager 集成实现基于日志的告警：

```yaml
# Loki 规则配置示例
groups:
  - name: log-rules
    rules:
      - alert: HighErrorRate
        expr: |
          count_overline({job="docker-system",level="error"}[5m]) > 100
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "High error rate detected"
          description: "{{ $value }} errors per minute over last 5 minutes"
```

这个规则会在每分钟错误数超过 100 持续 2 分钟后触发告警。

### CI/CD 流水线集成

在 CI/CD 管道中，你可以将构建日志发送到 Loki，方便调试：

```yaml
# .github/workflows/deploy.yml
- name: Ship logs to Loki
  run: |
    echo "Build started at $(date)" | curl -s -X POST \
      http://loki:3100/loki/api/v1/push \
      -H "Content-Type: application/json" \
      -d '{
        "streams": [{
          "stream": { "job": "ci-cd", "pipeline": "deploy" },
          "entries": [{ "timestamp": $(date +%s), "log": "Build started" }]
        }]'
```

## 迁移到 Loki Stack 的注意事项

如果你正在从 ELK 迁移过来，需要注意以下几点：

1. **查询逻辑差异**：ELK 使用 Lucene 语法，Loki 使用 LogQL。学习曲线存在但较短。

2. **索引设计不同**：在 Elasticsearch 中，你通常会对所有字段建索引；而在 Loki 中，你选择性地只对某些标签建索引。这需要重新设计日志收集策略。

3. **数据生命周期**：Loki 默认保留所有数据（直到存储空间耗尽）。需要配合 Compactor 定期清理旧数据。

4. **无全文搜索**：如果你依赖复杂的全文搜索功能，可能需要搭配专门的文本搜索引擎，或者接受 Loki 的标签 + 关键字搜索能力。

## 结论

Loki + Promtail + Grafana 构成了一个强大而轻量级的自托管日志聚合解决方案。它的核心优势在于：

- 💰 **成本效益**：比 ELK 节省 80-90% 的存储和计算资源
- 🚀 **部署简单**：单行 Docker Compose 即可启动
- 🔍 **查询灵活**：LogQL 支持复杂的日志过滤和分析
- 📊 **可视化一流**：Grafana 提供无与伦比的日志可视化体验
- 🔄 **生态兼容**：与 Prometheus、Alertmanager 深度集成

对于 VPS 用户、小型团队以及预算有限但需要专业日志分析能力的开发者来说，Loki Stack 是一个绝佳的选择。无论你是否已经在使用 Prometheus，引入 Loki 都会极大地提升你的可观测性能力。

现在就开始部署吧！只需几分钟，你就可以拥有一个功能完备的日志分析平台，并从此告别 SSH 逐行查看日志的低效时代。

---

> 📌 **延伸阅读**：结合前文 [AI 驱动的 VPS 日志分析与根因诊断](/zh/post/ai-vps-log-analysis-llm/)，可以在 Loki 之上构建 AI 增强型的日志分析系统，实现自动化的异常检测和智能告警。