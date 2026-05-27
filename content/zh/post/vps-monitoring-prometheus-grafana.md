---
title: "VPS 监控面板搭建：Prometheus + Grafana 零成本方案"
description: "用开源 Prometheus + Grafana + Node Exporter 搭建完整的 VPS 监控系统，实时追踪 CPU、内存、磁盘、网络指标，邮件告警一步到位"
date: 2026-05-27T10:00:00+08:00
lastmod: 2026-05-27T10:00:00+08:00
slug: "vps-monitoring-prometheus-grafana"
image: /images/posts/vps-monitoring-prometheus-grafana/featured.png
tags: ["Prometheus", "Grafana", "监控", "VPS", "运维", "告警", "Docker", "开源"]
categories: ["监控运维"]
aliases: [/zh/post/vps-monitoring-prometheus-grafana/]
---

## 引言

你手上有一台低配 VPS，跑着几个 Docker 容器，偶尔还挂个网站。一切看似正常，直到——

- 某天 SSH 登不上去，才发现磁盘已被日志撑满；
- 网站突然 502，但监控面板是第三方付费服务，刚好在这个月到期了；
- 内存泄漏把 VPS 搞 OOM，你甚至不知道什么时候发生的。

**别把监控留给直觉。** 今天我们用三款开源工具，在你的 VPS 上搭建一套完整的零成本监控系统：

| 组件 | 作用 | 资源消耗 |
|------|------|----------|
| **Prometheus** | 时序数据库 + 指标采集 | ~100MB 内存 |
| **Node Exporter** | 系统指标采集器 | ~20MB 内存 |
| **Grafana** | 可视化仪表盘 + 告警 | ~80MB 内存 |

三件套加起来只需 **200MB 内存**，任何 1GB 的 VPS 都能轻松运行。

---

## 1. 架构概览

```
┌─────────────────────────────────────┐
│            你的 VPS                   │
│  ┌──────────┐  ┌───────────────┐    │
│  │  Node     │  │  Prometheus   │    │
│  │  Exporter │──│  (抓取指标)   │    │
│  │  :9100    │  │  :9090       │    │
│  └──────────┘  └───────┬───────┘    │
│                        │            │
│                 ┌──────▼───────┐    │
│                 │   Grafana    │    │
│                 │  :3000       │    │
│                 └──────┬───────┘    │
│                        │            │
│            ┌───────────▼──────┐     │
│            │  浏览器/手机      │     │
│            └──────────────────┘     │
└─────────────────────────────────────┘
```

- **Node Exporter** 采集 CPU、内存、磁盘、网络等系统指标，暴露在 :9100
- **Prometheus** 定期拉取 Node Exporter 的数据，存入时序数据库
- **Grafana** 从 Prometheus 读取数据，渲染可视化面板，触发告警

---

## 2. 使用 Docker Compose 一键部署

创建一个项目目录：

```bash
mkdir -p ~/monitoring && cd ~/monitoring
```

创建 `docker-compose.yml`：

```yaml
version: '3.8'

services:
  prometheus:
    image: prom/prometheus:v2.53.0
    container_name: prometheus
    restart: unless-stopped
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    ports:
      - "9090:9090"
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--storage.tsdb.retention.time=30d'

  node_exporter:
    image: prom/node-exporter:v1.8.0
    container_name: node_exporter
    restart: unless-stopped
    volumes:
      - /proc:/host/proc:ro
      - /sys:/host/sys:ro
      - /:/rootfs:ro
    command:
      - '--path.procfs=/host/proc'
      - '--path.sysfs=/host/sys'
      - '--path.rootfs=/rootfs'
      - '--collector.filesystem.mount-points-exclude=^/(sys|proc|dev|host|etc)($$|/)'
    ports:
      - "9100:9100"

  grafana:
    image: grafana/grafana:11.1.0
    container_name: grafana
    restart: unless-stopped
    volumes:
      - grafana_data:/var/lib/grafana
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin   # ← 首次登录后立即修改！
      - GF_INSTALL_PLUGINS=grafana-piechart-panel

volumes:
  prometheus_data:
  grafana_data:
```

创建 Prometheus 配置文件 `prometheus.yml`：

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

alerting:
  alertmanagers: []

rule_files: []

scrape_configs:
  - job_name: 'node'
    static_configs:
      - targets: ['node_exporter:9100']
```

启动所有服务：

```bash
docker compose up -d
```

验证状态：

```bash
# 检查 Prometheus 目标状态
curl -s http://localhost:9090/api/v1/targets | jq .

# 检查 Node Exporter 指标
curl -s http://localhost:9100/metrics | head -20

# 访问 Grafana
echo "打开 http://你的VPS_IP:3000  (账号: admin / admin)"
```

---

## 3. 在 Grafana 中配置数据源

1. 浏览器访问 `http://你的VPS_IP:3000`
2. 首次登录：用户名 `admin`，密码 `admin`（会提示修改密码）
3. 进入 **Connections → Data Sources → Add data source**
4. 选择 **Prometheus**
5. URL 填写 `http://prometheus:9090`
6. 点击 **Save & Test**，看到绿色提示即成功

---

## 4. 导入经典监控仪表盘

用 Grafana 官方仪表盘 ID **1860**（Node Exporter Full）快速获得漂亮面板：

```bash
# 方式一：通过 Grafana CLI 导入
docker exec grafana grafana cli \
  plugins install grafana-piechart-panel

# 方式二：通过 Web UI 导入
# 1. 点击左侧 "+" → Import
# 2. 输入 ID: 1860
# 3. 选择你的 Prometheus 数据源
# 4. 点击 Import
```

导入后你将看到：

- 📊 **CPU 使用率** — 每个核心的实时负载
- 💾 **内存用量** — RAM、Swap、缓存分布
- 💽 **磁盘空间** — 各分区使用率、IO 读写速率
- 🌐 **网络流量** — 入站/出站流量图
- ⏱ **系统运行时间** — 以及 Load Average

---

## 5. 配置邮件告警（可选但推荐）

### 5.1 配置 Grafana 告警

修改 `docker-compose.yml`，添加 SMTP 配置到 Grafana 的环境变量中：

```yaml
environment:
  - GF_SMTP_ENABLED=true
  - GF_SMTP_HOST=smtp.gmail.com:587
  - GF_SMTP_USER=youraccount@gmail.com
  - GF_SMTP_PASSWORD=你的应用专用密码
  - GF_SMTP_FROM_ADDRESS=youraccount@gmail.com
  - GF_SMTP_FROM_NAME=VPS告警
```

重启 Grafana：

```bash
docker compose up -d grafana
```

### 5.2 创建告警规则

在 Grafana 中：

1. 进入 **Alerting → Alert rules → New alert rule**
2. 设置条件：`disk_usage_percent > 85`（磁盘使用率超过 85%）
3. 设置评估间隔：每 5 分钟检查一次
4. 添加联系人：配置邮件通知
5. 保存启用

**推荐设置的告警规则：**

| 指标 | 阈值 | 说明 |
|------|------|------|
| 磁盘使用率 | > 85% | 磁盘空间不足 |
| 内存使用率 | > 90% | 可能导致 OOM |
| CPU 负载 (15min) | > 2.0 | CPU 压力过高 |
| 根分区 inode | < 10% | inode 耗尽无法创建文件 |

---

## 6. 安全加固要点

### 6.1 使用 Nginx 反向代理 + HTTPS

```nginx
# /etc/nginx/sites-available/grafana
server {
    listen 443 ssl;
    server_name grafana.你的域名.com;

    ssl_certificate /etc/letsencrypt/live/你的域名.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/你的域名.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### 6.2 限制端口暴露

只暴露 Grafana 端口（通过反向代理），Prometheus 和 Node Exporter 不对外暴露：

```yaml
# docker-compose.yml 中移除 Prometheus 和 Node Exporter 的 ports
# 让它们仅在 Docker 内网通信
services:
  prometheus:
    expose:
      - "9090"    # 仅内部网络可达
    # 去掉 ports: 部分

  node_exporter:
    expose:
      - "9100"    # 仅内部网络可达
    # 去掉 ports: 部分
```

### 6.3 为 Grafana 设置强密码

```bash
# 通过环境变量设置更强密码
environment:
  - GF_SECURITY_ADMIN_PASSWORD=Your_Strong_P@ssw0rd!
  - GF_SECURITY_DISABLE_INIT_ADMIN_CREATION=false
```

---

## 7. 资源占用实测

在 **1GB 内存 / 1 核 / 20GB 磁盘** 的廉价 VPS 上实测：

| 组件 | 内存 (RSS) | 磁盘 |
|------|-----------|------|
| Prometheus | ~85 MB | 每天 ~300MB（采集 100+ 指标） |
| Node Exporter | ~18 MB | 0 |
| Grafana | ~65 MB | ~50MB（插件+DB） |
| **总计** | **~168 MB** | **~350MB/天** |

**结论：** 1GB 的 VPS 完全够用，30 天保留期约占用 10GB 磁盘，建议预留 15GB 以上。

---

## 8. 扩展阅读：更多 Exporter

这套方案可以轻松扩展，你想监控什么就加什么 Exporter：

| Exporter | 监控目标 | 端口 |
|----------|---------|------|
| [cAdvisor](https://github.com/google/cadvisor) | Docker 容器指标 | :8080 |
| [Blackbox Exporter](https://github.com/prometheus/blackbox_exporter) | 外部站点健康检查 | :9115 |
| [PostgreSQL Exporter](https://github.com/prometheus-community/postgres_exporter) | 数据库性能 | :9187 |
| [Nginx Exporter](https://github.com/nginxinc/nginx-prometheus-exporter) | Nginx 指标 | :9113 |

在 Prometheus 的 `scrape_configs` 中添加对应配置即可自动纳入监控。

---

## 总结

Prometheus + Grafana + Node Exporter 是 VPS 监控的"黄金三件套"——完全免费、社区庞大、扩展性极强。相比第三方付费监控服务（如 Datadog、New Relic），这套自建方案在**1GB 廉价 VPS** 上就能流畅运行，数据完全掌握在自己手中。

**关键要点回顾：**
- ✅ Docker Compose 一键部署，5 分钟上线
- ✅ 经典仪表盘 ID 1860，导入即用
- ✅ 邮件告警配置，异常第一时间通知
- ✅ Nginx 反代 + HTTPS 保障安全访问
- ✅ 可扩展至容器、数据库、站点监控

记住：**监控不是可选项，是运维的基本功。** 在你下一次遇到故障之前，先把这套监控搭起来吧。
