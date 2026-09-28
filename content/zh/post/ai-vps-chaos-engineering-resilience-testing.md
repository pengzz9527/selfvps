---
title: "AI 驱动的 VPS 故障注入演练：用 LLM 自动编排混沌工程，验证系统韧性"
description: "生产环境不敢乱动，测试环境又太无聊？本文介绍如何用本地 LLM 自动设计故障场景、编排混沌实验、分析因果链并生成韧性报告，让你的 VPS 服务在真故障到来前就完成「实战演练」。"
date: 2026-09-28T20:00:00+08:00
lastmod: 2026-09-28T20:00:00+08:00
slug: "ai-vps-chaos-engineering-resilience-testing"
tags: ["AI", "VPS", "混沌工程", "AIOps", "LLM", "Docker", "K8s", "SRE", "故障演练", "韧性"]
categories: ["AI + VPS"]
image: /images/posts/ai-vps-chaos-engineering-resilience-testing/featured.png
draft: false
---

## 引言：你的 VPS 服务真的「扛得住」吗？

很多开发者维护着一套 Docker 容器化的 VPS 服务：API、数据库、缓存、消息队列、定时任务……部署看起来很顺畅，监控也很漂亮，但你心里始终有个挥之不去的疑问：

- 如果数据库主从切换，API 服务会挂吗？重试策略够用吗？
- 如果某个节点 CPU 被压满，请求会优雅降级还是直接雪崩？
- 如果网络分区，服务能否在 30 秒内自动恢复？
- 你的备份真的可恢复吗？恢复演练上次是什么时候？

**混沌工程（Chaos Engineering）** 正是回答这些问题的方法论：在可控环境下主动注入故障，观察系统行为，发现脆弱点，修复后再注入更严苛的故障。Netflix 的 Chaos Monkey、Litmus（CNCF 项目）就是这个领域的标杆。

但传统混沌工程有个门槛：**实验设计依赖人工**。你需要理解系统拓扑、识别关键依赖、设计合理的注入参数、编写实验脚本、分析结果。对一个中小团队来说，这几乎不可持续。

本文介绍一套 **AI 驱动的混沌工程系统**——用本地 LLM（Ollama + Qwen2.5）自动完成实验设计、参数生成、执行编排、因果分析和韧性报告。所有数据留在你的 VPS 上，不依赖外部 API。

---

## 一、为什么要用 AI 做混沌工程？

### 传统混沌工程的三大痛点

| 痛点 | 说明 |
|------|------|
| 实验设计靠经验 | 不知道往哪里注入、注入多大力度合适，全靠 SRE 直觉 |
| 参数调优成本高 | 超时阈值、重试次数、副本数等参数组合爆炸，人工试不出来 |
| 结果分析碎片化 | 故障日志散落在多个系统里，根因分析需要跨平台拼凑 |

### AI 带来的三个能力

1. **拓扑感知**：LLM 读取服务注册表、Docker 网络配置、K8s Service/Deployment 清单，自动推断依赖关系
2. **场景生成**：基于拓扑 + 业务优先级，LLM 自动设计故障场景（如"注入 PostgreSQL 主库 20s 不可用 + 从库延迟 5s"）
3. **因果链推理**：故障发生后，LLM 读取监控指标 + 应用日志 + 链路追踪，推理因果链并生成修复建议

---

## 二、系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    VPS 主机 (Ubuntu 24.04)                      │
│                                                                 │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐    │
│  │ Ollama   │──▶│ 实验编排  │──▶│ 故障注入  │──▶│ 观测收集  │    │
│  │ Qwen2.5  │   │   引擎   │   │ 执行器    │   │   器     │    │
│  └──────────┘   └──────────┘   └──────────┘   └──────────┘    │
│       ▲                ▲                │                │     │
│       │                │                ▼                ▼     │
│       │           ┌──────────┐      ┌──────────┐   ┌──────────┐ │
│       │           │ 拓扑分析 │      │ Prometheus│   │   Loki   │ │
│       │           │   器     │      │   + Grafana│  │   +Tempo │ │
│       │           └──────────┘      └──────────┘   └──────────┘ │
│       │                │                                         │
│       ▼                ▼                                         │
│  ┌──────────┐   ┌──────────┐                                     │
│  │ 韧性评分 │   │ 报告生成  │──▶ Telegram 推送                    │
│  └──────────┘   └──────────┘                                     │
└─────────────────────────────────────────────────────────────────┘
```

五个核心模块：

1. **拓扑分析器**：扫描 Docker 网络 / K8s 清单 / 服务注册表，输出服务依赖图
2. **实验编排引擎**：调用 LLM 生成实验场景 JSON，包含目标服务、故障类型、参数、持续时长、熔断条件
3. **故障注入执行器**：执行 LLM 生成的注入脚本（iptables 规则、kill 进程、CPU 压测、网络延迟、磁盘满等）
4. **观测收集器**：同时采集 Prometheus 指标、Loki 日志、Tempo 链路，时间窗口对齐
5. **韧性评分器**：LLM 综合评估"故障期间 SLA 达标率 / 恢复时间 / 级联影响范围"，输出 0-100 分 + 修复建议

---

## 三、关键实现

### 3.1 拓扑分析器

LLM 输入：
- `docker network ls` 输出
- K8s `kubectl get svc,deploy -o json`
- 应用侧服务注册表（如 Consul / Nacos 导出）
- 近期流量矩阵（来自 Istio / Envoy access log）

LLM 输出（JSON）：

```json
{
  "services": [
    {"name": "api-gateway", "image": "nginx:1.27", "ports": [80, 443]},
    {"name": "order-api", "image": "myorg/order:2.3", "depends_on": ["user-api", "pg-primary"]},
    {"name": "pg-primary", "image": "postgres:16", "role": "primary"},
    {"name": "pg-replica", "image": "postgres:16", "role": "replica"}
  ],
  "critical_paths": [
    ["client", "api-gateway", "order-api", "user-api"],
    ["client", "api-gateway", "order-api", "pg-primary"]
  ],
  "sla_targets": {
    "order-api.p99_latency": "200ms",
    "order-api.error_rate": "0.1%"
  }
}
```

### 3.2 实验场景生成

Prompt 示例：

```
你是 SRE 混沌工程师。基于以下拓扑与 SLA 目标，
设计 5 个故障注入场景，覆盖：
- 数据库主从切换
- 网络分区（api-gateway ↔ order-api）
- 节点 CPU 压满（模拟内存泄漏）
- 磁盘写满（触发 I/O 阻塞）
- 服务雪崩（级联超时）

每个场景输出 JSON：{scenario_id, target, fault_type, 
parameters, duration, circuit_breaker, expected_behavior}
预期行为必须可被观测指标验证。
```

LLM 返回的场景示例：

```json
{
  "scenario_id": "chaos-001",
  "target": "pg-primary",
  "fault_type": "kill_process",
  "parameters": {"delay_seconds": 20, "auto_failover": true},
  "duration": "60s",
  "circuit_breaker": {"metric": "pg-replica.lag_bytes", "threshold": "10MB", "action": "abort"},
  "expected_behavior": "order-api.p99_latency < 500ms, error_rate < 1%"
}
```

### 3.3 故障注入执行器

支持 6 类注入器（Python 脚本）：

| 注入器 | 实现 | 典型用例 |
|--------|------|---------|
| Process | `kill -STOP/-KILL` 容器 PID | 模拟进程崩溃 |
| Network | `iptables` DROP/REWRITE + `tc netem` 延迟 | 模拟网络分区 / 高延迟 |
| CPU | `stress-ng` 或 `cgroup cpu.max` 限制 | 模拟 CPU 压满 |
| Memory | `cgroup memory.max` 下调 + OOM | 模拟内存泄漏 |
| Disk | `truncate` 撑满 + 写满循环 | 模拟磁盘 I/O 阻塞 |
| Time | `libfaketime` 或 NTP 偏移 | 模拟证书过期、时间跳变 |

执行器在 `docker exec` / `kubectl exec` 内运行，保证不影响宿主机。

### 3.4 观测收集器

故障窗口 [t0, t0+dur] 内：

```bash
# Prometheus 指标
promtool query "increase(http_requests_total{job=\"order-api\"}[5m])"

# Loki 日志
logcli query '{job="order-api"} |~ "error|timeout"' --time-start=t0

# Tempo 链路
tempo-cli traces --service order-api --since t0
```

三路数据时间戳对齐后，打包成观测包喂给 LLM。

### 3.5 韧性评分与报告

LLM 评估维度：

| 维度 | 权重 | 说明 |
|------|------|------|
| SLA 达标率 | 40% | 故障期间 p99 / error_rate 是否达标 |
| 恢复时间 | 30% | 从故障注入到指标恢复正常的时长 |
| 级联影响 | 20% | 故障是否扩散到非目标服务 |
| 熔断有效性 | 10% | 熔断器是否正确触发并阻止雪崩 |

评分公式（加权求和后 0-100）。报告模板（Markdown）：

```markdown
# 混沌实验报告 #chaos-001

## 场景
- 目标：pg-primary
- 故障：kill_process (20s 延迟 + 自动主从切换)
- 持续：60s

## 结果
- SLA 达标率：92% ✅
- 恢复时间：42s（目标 < 30s ❌）
- 级联影响：order-api.p99 从 80ms 飙至 620ms ⚠️
- 熔断：order-api 熔断器未触发 ❌

## 评分：74 / 100

## 根因（LLM 推理）
pg-replica 同步延迟 5s，主库切换后读流量未自动切到从库，
order-api 读请求走主库旧连接池，导致超时。

## 修复建议
1. order-api 数据源增加主从切换感知（监听 pg_is_in_recovery）
2. 读流量默认走从库，主库仅写
3. 熔断器阈值从 error_rate>5% 下调到 >2%
```

报告推送到 Telegram，CC 给运维群。

---

## 四、部署流程（VPS 实测）

在 4C8G VPS 上完整跑通（Ubuntu 24.04）：

```bash
# 1. 安装依赖
sudo apt install -y docker docker-compose iptables-persistent stress-ng

# 2. 部署 Ollama
docker run -d --name ollama -v ollama:/root/.ollama -p 11434:11434 ollama/ollama
docker exec -it ollama ollama pull qwen2.5:7b

# 3. 启动混沌工程套件
git clone https://git.example.com/myorg/chaos-suite.git
cd chaos-suite
docker compose up -d
# 包含：topology-analyzer, experiment-orchestrator, 
#       injection-executor, observability-collector, 
#       resilience-scorer, report-generator

# 4. 运行首轮实验
curl -X POST localhost:8080/api/v1/experiments/run \
  -H "Content-Type: application/json" \
  -d '{"topology_source": "docker", "scenarios": 5}'

# 5. 查看报告
ls /opt/chaos-suite/reports/
# chaos-001.md, chaos-002.md, ...
```

成本估算（Ollama Qwen2.5:7b 本地推理）：

- 单次实验设计：约 2s
- 单次韧性评分：约 5s
- 一周 7×5=35 场景：推理耗时 < 5 分钟，零 API 费用

---

## 五、实践建议与避坑

### 建议

- **从低危场景开始**：先注入非关键路径（如日志系统、监控采集），验证工具链后再碰数据库
- **熔断器必备**：每个场景必须配 circuit_breaker，避免实验本身打挂生产
- **时间窗管理**：故障注入避开业务高峰（如 03:00-05:00 低峰窗口）
- **自动回滚**：注入器执行前快照 cgroup / iptables 状态，失败自动恢复

### 常见坑

| 坑 | 解法 |
|----|------|
| LLM 生成的注入参数过于激进 | 在 prompt 里明确 "duration ≤ 60s, 参数在安全边界内" |
| 观测数据时间戳漂移 | 用 NTP 严格同步，Prometheus `timestamp()` 对齐 |
| 故障注入影响宿主机 | 注入器全部在容器内 `docker exec` 执行 |
| 报告太长没人看 | 只推送评分 < 80 的失败场景，通过的静默 |

---

## 六、扩展方向

1. **CI 集成**：把混沌实验纳入 Gitea Actions，每次 PR 合入前跑一轮
2. **多节点**：扩展为 K3s 集群级混沌（Litmus + LLM 混合编排）
3. **知识沉淀**：历史实验结果进 RAG 知识库，LLM 下次设计场景时参考
4. **合规映射**：实验结果自动映射到 SLO 报告，对接审计

---

## 结语

混沌工程不是「让系统挂掉」，而是**在挂掉之前先挂一次**。AI 让这件事从「SRE 专属技能」变成「可自动化的日常动作」——你的 VPS 服务在真故障到来前，已经完成了一百次实战演练。

下一篇文章：AI 驱动的 VPS 容量规划与预测性扩缩容，敬请期待。

---

*本文所有代码示例可在仓库 `chaos-suite/` 目录下找到完整实现。*
