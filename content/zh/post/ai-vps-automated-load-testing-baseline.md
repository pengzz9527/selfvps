---
title: "VPS 上搭建 AI 驱动的自动化压测与性能基准系统"
description: "告别凭感觉调优的运维方式——用本地 LLM 自动设计压测方案、执行并发测试、建立性能基线、检测性能回归，并智能生成调优建议。本文提供完整 Docker Compose 部署指南。"
date: 2026-09-03T21:30:00+08:00
lastmod: 2026-09-03T21:30:00+08:00
slug: "ai-vps-automated-load-testing-baseline"
tags: ["AI运维", "LLM", "性能测试", "压测", "基准测试", "VPS优化", "Ollama", "Docker"]
categories: ["AI运维"]
image: /images/posts/ai-vps-automated-load-testing-baseline/featured.png
draft: false
aliases: [/zh/post/ai-vps-automated-load-testing-baseline/]
---

你的 VPS 跑得慢，但不知道慢在哪里？每次发布新版本后，性能是变好了还是变差了？凭经验调优就像蒙眼射箭——有时命中，更多时候浪费子弹。

本文将教你在 VPS 上搭建一套 **AI 驱动的自动化压测与性能基准系统**：让本地 LLM 帮你设计压测场景、分析测试结果、建立性能基线、检测回归，并给出精准的调优建议。

## 传统压测的痛点

| 痛点 | 传统方式 | AI 驱动方式 |
|------|---------|------------|
| 压测场景设计 | 依赖工程师经验，容易遗漏边界场景 | LLM 分析应用架构，自动生成覆盖全面的测试方案 |
| 结果解读 | 需要手动对比历史数据，难以发现隐性退化 | LLM 自动关联性能变化与代码/配置变更 |
| 基线管理 | Excel 表格或纸质记录，更新困难 | 自动存储每次压测基线，趋势可视化 |
| 回归检测 | 人工抽查，容易漏检 | 每次部署后自动触发，与基线对比告警 |
| 调优建议 | 泛泛而谈，缺乏针对性 | 基于具体指标给出可执行的优化命令 |

## 系统架构

```
┌──────────────────────────────────────────────────────────────────┐
│                        VPS 服务器                                 │
│                                                                   │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────────┐     │
│  │  压测执行器   │──→│  LLM 分析引擎 │──→│   报告与通知     │     │
│  │  k6 / wrk2   │   │  Ollama API  │   │  • 趋势图表      │     │
│  │              │   │  (本地模型)   │   │  • 差异高亮      │     │
│  │  • 并发模拟   │   │              │   │  • 修复建议      │     │
│  │  • 场景调度   │   │  • 结果分析   │   │  • 基线存储      │     │
│  │  • 指标采集   │   │  • 基线对比   │   │  • Telegram/Web  │     │
│  └──────────────┘   │  • 建议生成   │   └──────────────────┘     │
│                     └──────────────┘                             │
│                           │                                      │
│                     ┌─────▼─────┐                                │
│                     │  被测服务   │                                │
│                     │  (Web/API) │                                │
│                     └───────────┘                                │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐     │
│  │  数据存储：SQLite (基线) + JSON (报告) + Grafana (可视化) │     │
│  └─────────────────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────────────────┘
```

### 核心组件

1. **压测执行器**：使用 k6 作为核心压测工具（Go 编写，高性能，脚本友好），支持 HTTP/HTTPS、WebSocket、gRPC 等多种协议
2. **LLM 分析引擎**：本地 Ollama + Qwen2.5 7B，分析压测数据并生成可读报告
3. **基线管理器**：SQLite 数据库存储历史性能基线，支持趋势查询和回归检测
4. **调度器**：cron/systemd timer 定时触发，或在 CI/CD 流水线中集成
5. **通知模块**：Telegram Bot 推送异常告警，Web Dashboard 展示趋势

## 第一步：部署本地 LLM

```bash
# 安装 Ollama
curl -fsSL https://ollama.com/install.sh | sh

# 拉取适合 VPS 的模型（7B 量化版，内存占用约 4-5GB）
ollama pull qwen2.5:7b-instruct

# 验证
ollama list
ollama run qwen2.5:7b-instruct "你好，请用一句话介绍你自己"
```

> **内存建议**：7B 模型需至少 6GB RAM（含系统开销）。2GB 内存 VPS 可用 `qwen2.5:3b`，1GB 可用 `phi3:mini`。

## 第二步：部署压测工具 k6

```bash
# 方法一：直接安装（推荐）
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -s https://packagecloud.io/install/repositories/k6io/k6/script.deb.sh | sudo bash
sudo apt install -y k6

# 方法二：Docker 运行
docker run --rm -i grafana/k6 run - <script.js

# 验证
k6 version
# k6 v0.52.0 (go1.21.1, amd64)
```

## 第三步：编写压测脚本

创建一个标准的 HTTP 压测脚本 `loadtest/http_probe.js`：

```javascript
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend } from 'k6/metrics';

// 自定义指标
const errorRate = new Rate('error_rate');
const p99Trend = new Trend('response_time_p99');

export const options = {
  stages: [
    { duration: '30s', target: 50 },   // 渐进升温：30秒内达到50并发
    { duration: '2m', target: 50 },    // 稳态压力：维持50并发2分钟
    { duration: '30s', target: 100 },  // 峰值压力：冲到100并发
    { duration: '1m', target: 100 },   // 峰值维持
    { duration: '30s', target: 0 },    // 冷却
  ],
  thresholds: {
    http_req_duration: ['p(95)<500', 'p(99)<1000'], // p95<500ms, p99<1000ms
    http_req_failed: ['rate<0.01'],                  // 错误率<1%
  },
};

const BASE_URL = __ENV.BASE_URL || 'http://localhost';

export default function () {
  // 模拟真实用户行为
  const scenarios = [
    // 首页加载
    () => {
      const res = http.get(`${BASE_URL}/`);
      check(res, {
        'home status 200': (r) => r.status === 200,
        'home fast': (r) => r.timings.duration < 500,
      });
      errorRate.add(res.status >= 500 ? 1 : 0);
      p99Trend.add(res.timings.duration);
    },
    // API 查询
    () => {
      const res = http.get(`${BASE_URL}/api/health`);
      check(res, {
        'api status 200': (r) => r.status === 200,
        'api fast': (r) => r.timings.duration < 200,
      });
      errorRate.add(res.status >= 500 ? 1 : 0);
      p99Trend.add(res.timings.duration);
    },
    // 随机思考时间
    () => sleep(Math.random() * 2 + 0.5),
  ];

  // 随机执行一个场景
  const choice = Math.floor(Math.random() * scenarios.length);
  scenarios[choice]();
}
```

## 第四步：构建 LLM 分析管道

创建分析脚本 `tools/analyze_results.py`：

```python
#!/usr/bin/env python3
"""
AI-Powered Load Test Result Analyzer
Uses local LLM to analyze k6 results and generate optimization recommendations.
"""

import json
import subprocess
import sqlite3
import os
from datetime import datetime
from pathlib import Path

DB_PATH = Path.home() / ".vps-ops" / "baseline.db"
OLLAMA_URL = "http://localhost:11434"
MODEL = "qwen2.5:7b-instruct"


def init_db():
    """初始化基线数据库"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS baselines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            scenario TEXT NOT NULL,
            vus INTEGER,
            duration_sec INTEGER,
            p50_ms REAL,
            p95_ms REAL,
            p99_ms REAL,
            max_ms REAL,
            rps REAL,
            error_rate REAL,
            total_requests INTEGER,
            total_errors INTEGER,
            metadata TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            metric TEXT,
            current_value REAL,
            baseline_value REAL,
            deviation_pct REAL,
            severity TEXT,
            recommendation TEXT
        )
    """)
    conn.commit()
    return conn


def parse_k6_report(report_path: str) -> dict:
    """解析 k6 JSON 报告"""
    with open(report_path) as f:
        data = json.load(f)

    metrics = data.get("metrics", {})
    result = {
        "timestamp": datetime.now().isoformat(),
        "p50_ms": metrics.get("http_req_duration", {}).get("p(50)", 0) / 1000,
        "p95_ms": metrics.get("http_req_duration", {}).get("p(95)", 0) / 1000,
        "p99_ms": metrics.get("http_req_duration", {}).get("p(99)", 0) / 1000,
        "max_ms": metrics.get("http_req_duration", {}).get("max", 0) / 1000,
        "rps": metrics.get("http_reqs", {}).get("rate", 0),
        "error_rate": metrics.get("http_req_failed", {}).get("rate", 0),
        "total_requests": int(metrics.get("http_reqs", {}).get("count", 0)),
        "total_errors": int(metrics.get("http_req_failed", {}).get("fails", 0)),
    }
    return result


def save_baseline(conn: sqlite3.Connection, result: dict, scenario: str, vus: int):
    """保存性能基线"""
    conn.execute(
        """INSERT INTO baselines
           (timestamp, scenario, vus, duration_sec, p50_ms, p95_ms, p99_ms,
            max_ms, rps, error_rate, total_requests, total_errors, metadata)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            result["timestamp"], scenario, vus, 180,
            result["p50_ms"], result["p95_ms"], result["p99_ms"],
            result["max_ms"], result["rps"], result["error_rate"],
            result["total_requests"], result["total_errors"],
            json.dumps(result),
        ),
    )
    conn.commit()


def get_latest_baseline(conn: sqlite3.Connection, scenario: str) -> dict | None:
    """获取最新基线用于对比"""
    cur = conn.execute(
        """SELECT p50_ms, p95_ms, p99_ms, max_ms, rps, error_rate, timestamp
           FROM baselines WHERE scenario=? ORDER BY timestamp DESC LIMIT 1""",
        (scenario,),
    )
    row = cur.fetchone()
    if not row:
        return None
    return {
        "p50_ms": row[0], "p95_ms": row[1], "p99_ms": row[2],
        "max_ms": row[3], "rps": row[4], "error_rate": row[5],
        "timestamp": row[6],
    }


def analyze_with_llm(current: dict, baseline: dict | None, scenario: str) -> str:
    """调用本地 LLM 分析压测结果"""
    prompt = f"""你是一个专业的性能工程师。请分析以下压测结果，给出简洁的诊断和优化建议。

**测试场景**: {scenario}
**测试时间**: {current['timestamp']}

当前结果:
- P50 响应时间: {current['p50_ms']:.2f}ms
- P95 响应时间: {current['p95_ms']:.2f}ms
- P99 响应时间: {current['p99_ms']:.2f}ms
- 最大响应时间: {current['max_ms']:.2f}ms
- 吞吐量: {current['rps']:.2f} req/s
- 错误率: {current['error_rate']:.2%}
- 总请求数: {current['total_requests']}

"""
    if baseline:
        p95_change = ((current["p95_ms"] - baseline["p95_ms"]) / baseline["p95_ms"]) * 100
        rps_change = ((current["rps"] - baseline["rps"]) / baseline["rps"]) * 100 if baseline["rps"] else 0
        prompt += f"""上次基线 ({baseline['timestamp']}):
- P95: {baseline['p95_ms']:.2f}ms, 变化: {p95_change:+.1f}%
- 吞吐量: {baseline['rps']:.2f} req/s, 变化: {rps_change:+.1f}%
"""
    else:
        prompt += "（首次测试，无历史基线对比）\n"

    prompt += """
请用以下格式回复：
1. **健康状态**: 🟢正常 / 🟡关注 / 🔴异常
2. **关键发现**: 2-3条最重要的观察
3. **优化建议**: 具体的、可执行的调优命令或配置建议
4. **风险提示**: 如果有潜在风险请指出

保持简洁，每点不超过2行。"""

    try:
        result = subprocess.run(
            ["ollama", "run", MODEL, prompt],
            capture_output=True, text=True, timeout=60
        )
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        return "LLM分析超时，请检查 Ollama 服务状态。"
    except Exception as e:
        return f"LLM 调用失败: {e}"


def check_regression(current: dict, baseline: dict) -> list[dict]:
    """检测性能回归"""
    alerts = []
    thresholds = {"p95_ms": 0.20, "rps": -0.15, "error_rate": 0.01}  # 20%恶化或1%错误

    for metric, threshold in thresholds.items():
        if metric == "error_rate":
            change = current[metric] - baseline.get(metric, 0)
            if change > threshold:
                alerts.append({
                    "metric": metric, "current": current[metric],
                    "baseline": baseline.get(metric, 0),
                    "deviation": change, "severity": "high"
                })
        else:
            base_val = baseline.get(metric, 0)
            if base_val > 0:
                change_pct = (current[metric] - base_val) / base_val
                if change_pct > abs(threshold):
                    alerts.append({
                        "metric": metric, "current": current[metric],
                        "baseline": base_val, "deviation": change_pct,
                        "severity": "high" if change_pct > 0.5 else "medium"
                    })
    return alerts


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True, help="k6 JSON report path")
    parser.add_argument("--scenario", default="default", help="测试场景名")
    parser.add_argument("--vus", type=int, default=50, help="虚拟用户数")
    parser.add_argument("--notify", action="store_true", help="发送通知")
    args = parser.parse_args()

    conn = init_db()

    # 解析报告
    current = parse_k6_report(args.report)
    print(f"✅ 解析完成: P95={current['p95_ms']:.1f}ms, RPS={current['rps']:.1f}, 错误率={current['error_rate']:.2%}")

    # 保存基线
    save_baseline(conn, current, args.scenario, args.vus)

    # LLM 分析
    baseline = get_latest_baseline(conn, args.scenario)
    analysis = analyze_with_llm(current, baseline, args.scenario)
    print(f"\n🤖 LLM 分析结果:\n{analysis}")

    # 回归检测
    if baseline:
        alerts = check_regression(current, baseline)
        if alerts:
            for a in alerts:
                conn.execute(
                    """INSERT INTO alerts (timestamp, metric, current_value, baseline_value, deviation_pct, severity, recommendation)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (current["timestamp"], a["metric"], a["current"], a["baseline"],
                     a["deviation"], a["severity"], "")
                )
            conn.commit()
            print(f"\n⚠️ 检测到 {len(alerts)} 项性能回归！")
        else:
            print("\n✅ 无性能回归，各项指标正常")

    conn.close()


if __name__ == "__main__":
    main()
```

## 第五步：Docker Compose 一键部署

创建 `docker-compose.yml`：

```yaml
version: '3.8'

services:
  # ─── Ollama (LLM 分析引擎) ───
  ollama:
    image: ollama/ollama:latest
    container_name: vps-ollama
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama
    restart: unless-stopped
    # 限制 GPU 内存使用（如有 NVIDIA GPU）
    # deploy:
    #   resources:
    #     reservations:
    #       devices:
    #         - driver: nvidia
    #           count: 1
    #           capabilities: [gpu]

  # ─── k6 压测服务 ───
  k6-runner:
    image: grafana/k6:latest
    container_name: vps-k6
    volumes:
      - ./loadtest:/mnt/scripts
      - ./reports:/mnt/reports
    environment:
      - BASE_URL=http://your-app:8080
    restart: "no"
    depends_on:
      - ollama

  # ─── Grafana (可视化) ───
  grafana:
    image: grafana/grafana-oss:latest
    container_name: vps-grafana
    ports:
      - "3000:3000"
    volumes:
      - grafana_data:/var/lib/grafana
      - ./grafana/datasources:/etc/grafana/provisioning/datasources
      - ./grafana/dashboards:/etc/grafana/provisioning/dashboards
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin123
      - GF_USERS_ALLOW_SIGN_UP=false
    restart: unless-stopped

volumes:
  ollama_data:
  grafana_data:
```

## 第六步：创建调度与自动触发

创建 `scripts/run-benchmark.sh`：

```bash
#!/bin/bash
set -euo pipefail

SCENARIO="${1:-default}"
VUS="${2:-50}"
REPORT_DIR="/root/vps-ops/reports"
mkdir -p "$REPORT_DIR"

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
REPORT_FILE="$REPORT_DIR/${SCENARIO}-${TIMESTAMP}.json"

echo "🚀 开始压测: scenario=$SCENARIO, vus=$VUS"

# 执行 k6 压测
docker run --rm \
  -v "$PWD/loadtest:/mnt/scripts" \
  -v "$REPORT_DIR:/mnt/reports" \
  -e BASE_URL="${BASE_URL:-http://localhost}" \
  grafana/k6:latest run \
  --out json=/mnt/reports/${SCENARIO}-${TIMESTAMP}.json \
  /mnt/scripts/http_probe.js \
  --vus $VUS --duration 180s

echo "📊 报告已保存: $REPORT_FILE"

# AI 分析
echo "🤖 启动 LLM 分析..."
python3 /root/vps-ops/tools/analyze_results.py \
  --report "$REPORT_FILE" \
  --scenario "$SCENARIO" \
  --vus "$VUS"

echo "✅ 压测与分析完成"
```

添加 cron 定时任务：

```bash
# 每天凌晨 3 点执行基准压测
crontab -e
# 添加：
0 3 * * * cd /root/vps-ops && bash scripts/run-benchmark.sh default 50 >> /var/log/vps-benchmark.log 2>&1

# 每周日执行高负载压测（100 并发）
0 4 * * 0 cd /root/vps-ops && bash scripts/run-benchmark.sh stress 100 >> /var/log/vps-benchmark.log 2>&1
```

## 第七步：CI/CD 集成（可选）

在 GitHub Actions 中集成压测，每次部署后自动验证性能：

```yaml
name: Performance Regression Test
on:
  push:
    branches: [main]
  workflow_dispatch:

jobs:
  load-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Run k6 load test
        uses: grafana/k6-action@v0.3.1
        with:
          filename: loadtest/http_probe.js
          parallel-vus: 50
          duration: 180s

      - name: AI Analysis
        run: |
          python3 tools/analyze_results.py \
            --report k6-result.json \
            --scenario "ci-${{ github.sha }}"

      - name: Check thresholds
        run: |
          # 简单阈值检查（也可由 LLM 做深度分析）
          p95=$(jq '.metrics.http_req_duration."p(95)"' k6-result.json)
          if (( $(echo "$p95 > 500" | bc -l) )); then
            echo "⚠️ P95 超过 500ms 阈值"
            exit 1
          fi
```

## 实际效果示例

一次典型的压测分析报告输出：

```
✅ 解析完成: P95=142.3ms, RPS=287.5, 错误率=0.00%

🤖 LLM 分析结果:
1. **健康状态**: 🟢正常
2. **关键发现**:
   - P95 响应时间较上次提升 18%（28ms → 23ms），表现优秀
   - 吞吐量稳定在 287 req/s，无波动
   - 零错误率，服务完全稳定
3. **优化建议**:
   - 当前配置已较优，可考虑进一步增加并发至 100 VU 测试极限
   - 建议开启 gzip 压缩可降低约 30% 带宽消耗
4. **风险提示**: 无

✅ 无性能回归，各项指标正常
```

## 进阶：接入 Grafana 可视化

在 `grafana/dashboards/` 下配置 k6 官方 Dashboard JSON，即可在 Grafana 中看到：
- 实时吞吐量曲线
- 响应时间分位数（P50/P95/P99）趋势
- 错误率变化
- 并发用户数波形
- 基线对比叠加图

## 总结

这套系统的核心价值在于**把性能优化的经验沉淀为可重复、可量化的自动化流程**：

1. **自动化压测**：定时或触发式执行，无需人工干预
2. **AI 智能分析**：本地 LLM 理解结果，给出可读报告和优化建议
3. **基线追踪**：SQLite 持久化存储，随时回溯历史
4. **回归告警**：自动检测性能退化，早发现早修复
5. **CI/CD 集成**：每次部署自动验证，防止性能回退

成本几乎为零：一个 4GB 内存的 VPS + Ollama + k6 + Grafana，月费用不超过 ¥50。

现在就去搭建你的 AI 压测系统吧——让数据代替直觉，让自动化代替手动。
