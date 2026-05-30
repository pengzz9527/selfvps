---
title: "Docker 日志管理：用 Loki + Grafana + Promtail 搭建轻量日志系统"
description: "手把手教你用 Grafana Loki + Promtail 为 Docker 容器搭建轻量级集中式日志系统，告别 docker logs 和杂乱日志文件，实现可视化日志分析与告警"
date: 2026-05-30T10:00:00+08:00
lastmod: 2026-05-30T10:00:00+08:00
slug: "docker-log-management-loki-grafana-promtail"
image: /images/posts/docker-log-management-loki-grafana-promtail/featured.png
tags: ["Docker", "日志管理", "Loki", "Grafana", "Promtail", "自托管", "容器", "运维"]
categories: ["容器运维"]
aliases: [/zh/post/docker-log-management-loki-grafana-promtail/]
draft: false
---

## 引言

当你管理多个 Docker 容器时，日志查看很快变成一场噩梦：

- 每个容器单独 `docker logs -f`，切来切去
- 容器重启后历史日志丢失
- 无法跨容器搜索关键词
- 没有时间线、可视化、告警

**Loki** 是 Grafana 团队开发的日志聚合系统，专为 Kubernetes 和 Docker 设计，和 Prometheus 使用相同的标签机制。它与 Elasticsearch 的最大区别是 **不索引日志内容，只索引标签**——因此存储成本极低，查询速度飞快。

本文将带你用 **Loki + Promtail + Grafana** 三部曲，在 VPS 上搭建一套完整的容器日志管理方案。

## 架构概览

日志流动路径：

```
容器 stdout/stderr → Promtail（日志采集） → Loki（存储+索引） → Grafana（查询+可视化）
```

- **Promtail**：运行在每个 Docker 主机上，读取容器日志文件，添加标签（容器名、镜像名等），推送到 Loki
- **Loki**：日志存储后端，通过标签索引日志，支持 LogQL 查询语言
- **Grafana**：日志查询和可视化面板，支持告警

所有组件都是 **Grafana 全家桶**，全部开源免费，资源占用极低。

## 环境准备

假设你已经在 VPS 上安装了 Docker 和 Docker Compose。最低配置需求：

- 1 核 CPU / 1GB RAM（足够处理单机 20+ 个容器的日志）
- 20GB 磁盘（日志存储，可根据需求调整保留时间）
- Docker Compose v2+

## 第一步：创建 Docker Compose 部署文件

我们将 Loki、Promtail 和 Grafana 统一放在一个 Compose 文件中管理。

```yaml
# docker-compose.yml
version: "3.8"

networks:
  loki:

services:
  # ── Loki 日志存储 ──
  loki:
    image: grafana/loki:2.9.6
    container_name: loki
    ports:
      - "3100:3100"
    volumes:
      - ./loki-config.yaml:/etc/loki/local-config.yaml
      - ./loki-data:/loki
    command: -config.file=/etc/loki/local-config.yaml
    networks:
      - loki
    restart: unless-stopped

  # ── Promtail 日志采集 ──
  promtail:
    image: grafana/promtail:2.9.6
    container_name: promtail
    volumes:
      - ./promtail-config.yaml:/etc/promtail/config.yaml
      - /var/log:/var/log
      - /var/lib/docker/containers:/var/lib/docker/containers:ro
    command: -config.file=/etc/promtail/config.yaml
    networks:
      - loki
    restart: unless-stopped
    depends_on:
      - loki

  # ── Grafana 可视化 ──
  grafana:
    image: grafana/grafana:10.4.1
    container_name: grafana
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin    # 首次登录密码，记得修改！
      - GF_INSTALL_PLUGINS=
    volumes:
      - ./grafana-data:/var/lib/grafana
    networks:
      - loki
    restart: unless-stopped
    depends_on:
      - loki
```

## 第二步：配置 Loki

创建 `loki-config.yaml`：

```yaml
auth_enabled: false

server:
  http_listen_port: 3100

common:
  path_prefix: /loki
  storage:
    filesystem:
      chunks_directory: /loki/chunks
      rules_directory: /loki/rules
  replication_factor: 1
  ring:
    kvstore:
      store: inmemory

schema_config:
  configs:
    - from: 2024-01-01
      store: tsdb
      object_store: filesystem
      schema: v13
      index:
        prefix: index_
        period: 24h

# 单实例模式，零依赖
table_manager:
  retention_deletes_enabled: false
  retention_period: 0s

limits_config:
  reject_old_samples: true
  reject_old_samples_max_age: 168h
  max_query_series: 5000
```

> **提示**：对于单机 VPS，文件系统存储就足够了。如果磁盘空间紧张，可以配置 `retention_period` 来限制日志保留时间，例如 `720h`（30天）。

## 第三步：配置 Promtail

创建 `promtail-config.yaml`：

```yaml
server:
  http_listen_port: 9080
  grpc_listen_port: 0

positions:
  filename: /etc/promtail/positions.yaml  # 记录已读取位置，避免重复

clients:
  - url: http://loki:3100/loki/api/v1/push

scrape_configs:
  - job_name: docker
    # 自动发现 Docker 容器日志
    docker_sd_configs:
      - host: unix:///var/run/docker.sock
        refresh_interval: 5s
    pipeline_stages:
      - docker: {}                              # 自动解析 Docker 日志格式
      - labels:
          container_name: ""                     # 容器名作为标签
          container_image: ""                    # 镜像名作为标签
      - regex:
          expression: "^(?P<level>\\w+)\\s"     # 提取日志级别
      - labels:
          level: ""                              # 日志级别作为标签
    relabel_configs:
      - source_labels: ["__meta_docker_container_name"]
        regex: "/(.*)"
        target_label: "container"
        replacement: "$1"
```

这个配置会自动发现所有正在运行的 Docker 容器，将它们的 stdout/stderr 日志发送到 Loki。

> **关键点**：`/var/run/docker.sock` 需要被挂载到 Promtail 容器内，才能实现自动容器发现。

## 第四步：启动服务

```bash
# 创建数据目录
mkdir -p loki-data grafana-data

# 启动
docker compose up -d

# 检查状态
docker compose ps
docker compose logs -f promtail  # 确认日志采集正常
```

首次启动后，用浏览器访问 `http://你的VPS地址:3000`，用 `admin` / 你设置的环境变量密码登录 Grafana。

## 第五步：在 Grafana 中添加 Loki 数据源

1. 登录 Grafana，进入 **Connections → Data sources**
2. 点击 **Add data source**，选择 **Loki**
3. URL 填写 `http://loki:3100`
4. 点击 **Save & Test**，确认 "Data source connected and labels found."

如果看到标签列表（如 `container_name`、`container_image`、`level`），说明一切正常。

## 第六步：探索日志 — LogQL 查询

Grafana 的 Explore 面板（🔍 图标）是查询日志的主要入口。

### 基础查询

```logql
# 查看所有日志
{container_name=~".+"}

# 只看特定容器的日志
{container_name="nginx"}

# 同时查看多个容器
{container_name=~"nginx|traefik|app-web"}

# 按镜像名过滤
{container_image=~"nginx:.*"}
```

### 带内容的搜索

```logql
# 包含错误关键词
{container_name=~".+"} |= "error"

# 排除健康检查日志
{container_name="nginx"} != "/health"

# 正则匹配
{container_name="app"} |~ "Exception|Timeout|Fatal"

# JSON 日志解析并过滤
{container_name="api"} | json | status >= 400
```

### 指标化查询（类似于 PromQL）

```logql
# 每分钟每容器的日志条数
rate({container_name=~".+"}[1m]) by (container_name)

# 错误日志的趋势
sum by (container_name) (rate({container_name=~".+"} |= "error"[5m]))
```

## 第七步：设置日志告警

Loki 日志告警和 Prometheus 指标告警同样强大。假设你想在某个容器出现大量 5xx 错误时收到通知：

1. 进入 Grafana **Alerting → Alert rules → New alert rule**
2. 选择 **Loki** 数据源
3. 输入查询：

```logql
sum by (container_name) (
  count_over_time(
    {container_name=~".+"} | json | status >= 500
    [5m]
  )
) > 10
```

4. 设置评估周期 `1m`，条件 `WHEN avg() OF query IS ABOVE 10`
5. 配置通知渠道（Email、Telegram、Slack、Webhook 等）

这样当任何容器在 5 分钟内出现超过 10 次 5xx 错误时，你就会收到告警。

## 第八步：接入现有 DNS / 反向代理

如果你已经部署了 Traefik 或 Nginx 反向代理，可以给 Grafana 加个域名：

```yaml
# Traefik labels 示例
services:
  grafana:
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.grafana.rule=Host(`logs.你的域名.com`)"
      - "traefik.http.routers.grafana.entrypoints=https"
      - "traefik.http.services.grafana.loadbalancer.server.port=3000"
```

## 优化与维护建议

### 日志保留策略

Loki 本身不内置日志删除，但可以通过配置 `retention_period` 控制。或者用外部 cron 任务清理 `loki-data` 目录：

```bash
# 只保留最近 7 天的日志数据
find /opt/loki/loki-data -mtime +7 -delete
```

### 资源占用参考

| 容器数量 | 日志量 | Loki 内存 | Promtail 内存 |
|----------|--------|-----------|--------------|
| 5 个     | 轻量   | ~150MB    | ~30MB        |
| 20 个    | 中等   | ~400MB    | ~80MB        |
| 50 个    | 大量   | ~1GB      | ~150MB       |

### 安全加固

- 给 Grafana 设置强密码（通过 `GF_SECURITY_ADMIN_PASSWORD` 环境变量）
- 生产环境务必配置 HTTPS（通过反向代理）
- Promtail 的 HTTP 端口（9080）不需要暴露到公网
- 考虑为 Grafana 开启 OAuth/OIDC 认证

## 替代方案对比

| 特性                | Loki + Promtail          | Elasticsearch + Filebeat | 自建 Graylog    |
|---------------------|--------------------------|--------------------------|-----------------|
| 资源占用             | ⭐ 极低                   | 🟡 高                    | 🟡 中           |
| 部署复杂度           | ⭐ 极简（2个YAML）        | 🔴 复杂（需调JVM堆）     | 🟡 中等         |
| 查询语言             | LogQL（类PromQL）        | Query DSL（JSON）        | Lucene查询      |
| Grafana 原生集成     | ✅ 完美                   | ✅ 支持                   | ⚠️ 需插件       |
| 适合 VPS             | ⭐ 非常推荐               | ❌ 太吃资源               | 🟡 勉强可行     |

## 总结

通过 **Loki + Promtail + Grafana** 三步走，你在几分钟内就拥有了一套完整的 Docker 容器日志管理方案：

- **Loki** 负责日志存储和索引，资源占用极低
- **Promtail** 自动发现所有 Docker 容器并采集日志
- **Grafana** 提供强大的 LogQL 查询和可视化面板
- 支持告警、多容器联合搜索、日志趋势分析

最重要的是——**全部开源免费**，没有 Elastic 的许可限制，没有日志量收费，没有用户数限制。对轻量级 VPS 来说，这是目前性价比最高的日志方案。

下一步你可以尝试：将 Loki 与 Prometheus 指标数据联动，在 Grafana 同一个面板里同时查看指标和日志，实现完整的可观测性。
