---
title: "AI-Powered Automated Load Testing & Performance Baseline on VPS"
description: "Stop guessing what's slow—let a local LLM design load tests, analyze results, establish performance baselines, detect regressions, and generate precise optimization recommendations. Complete Docker Compose deployment guide included."
date: 2026-09-03T21:30:00+08:00
lastmod: 2026-09-03T21:30:00+08:00
slug: "ai-vps-automated-load-testing-baseline"
tags: ["AI Ops", "LLM", "Load Testing", "Benchmarking", "Performance", "VPS Optimization", "Ollama", "Docker"]
categories: ["AI Operations"]
image: /images/posts/ai-vps-automated-load-testing-baseline/featured.png
draft: false
aliases: [/en/post/ai-vps-automated-load-testing-baseline/]
---

Your VPS feels slow, but you can't pinpoint why? After every deployment, is performance actually better or worse? Tuning by gut feeling is like shooting arrows blindfolded—sometimes you hit the mark, mostly you waste them.

This guide shows you how to build an **AI-powered automated load testing and performance baseline system** on your VPS: let a local LLM design test scenarios, analyze results, establish baselines, detect regressions, and deliver precise tuning recommendations.

## The Pain Points of Traditional Load Testing

| Pain Point | Traditional Approach | AI-Powered Approach |
|-----------|---------------------|---------------------|
| Test scenario design | Relies on engineer experience, easy to miss edge cases | LLM analyzes app architecture, auto-generates comprehensive test plans |
| Result interpretation | Manual comparison with historical data, hard to spot subtle regressions | LLM correlates performance changes with code/config modifications |
| Baseline management | Excel sheets or paper notes, hard to update | Auto-stored baselines with trend visualization |
| Regression detection | Manual sampling, easy to miss | Auto-triggered after every deployment, compared against baselines |
| Tuning recommendations | Generic advice, lacks specificity | Actionable optimization commands based on specific metrics |

## System Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│                        VPS Server                                   │
│                                                                     │
│  ┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐   │
│  │  Load Test      │──→│  LLM Analysis   │──→│  Reports &      │   │
│  │  Executor       │   │  Engine         │   │  Notifications  │   │
│  │  k6 / wrk2      │   │  Ollama API     │   │  • Trend charts │   │
│  │                 │   │  (local model)   │   │  • Diff highlight│   │
│  │  • Concurrency  │   │                 │   │  • Fix advice   │   │
│  │  • Scenario     │   │  • Result       │   │  • Baseline DB  │   │
│  │  • Metric       │   │    analysis     │   │  • Telegram/   │   │
│  └─────────────────┘   │  • Baseline     │   │    Web UI       │   │
│                         │    comparison   │   └─────────────────┘   │
│                         │  • Suggestion   │                          │
│                         └─────────────────┘                          │
│                               │                                      │
│                         ┌─────▼──────┐                              │
│                         │ Target App  │                              │
│                         │ (Web/API)   │                              │
│                         └─────────────┘                              │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ Storage: SQLite (baselines) + JSON (reports) + Grafana (viz) │    │
│  └─────────────────────────────────────────────────────────────┘    │
└────────────────────────────────────────────────────────────────────┘
```

### Core Components

1. **Load Test Executor**: k6 as the core tool (Go-based, high-performance, script-friendly), supporting HTTP/HTTPS, WebSocket, gRPC protocols
2. **LLM Analysis Engine**: Local Ollama + Qwen2.5 7B for analyzing test data and generating readable reports
3. **Baseline Manager**: SQLite database storing historical performance baselines with trend queries and regression detection
4. **Scheduler**: cron/systemd timer for scheduled runs, or integrated into CI/CD pipelines
5. **Notification Module**: Telegram Bot for anomaly alerts, Web Dashboard for trend visualization

## Step 1: Deploy Local LLM

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull a VPS-friendly model (7B quantized, ~4-5GB RAM usage)
ollama pull qwen2.5:7b-instruct

# Verify
ollama list
ollama run qwen2.5:7b-instruct "Hello, introduce yourself in one sentence"
```

> **Memory guidance**: 7B models need at least 6GB RAM (including OS overhead). For 2GB VPS, use `qwen2.5:3b`; for 1GB, use `phi3:mini`.

## Step 2: Install Load Test Tool k6

```bash
# Method 1: Direct install (recommended)
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -s https://packagecloud.io/install/repositories/k6io/k6/script.deb.sh | sudo bash
sudo apt install -y k6

# Method 2: Docker
docker run --rm -i grafana/k6 run - <script.js

# Verify
k6 version
# k6 v0.52.0 (go1.21.1, amd64)
```

## Step 3: Write Load Test Scripts

Create a standard HTTP load test script `loadtest/http_probe.js`:

```javascript
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend } from 'k6/metrics';

// Custom metrics
const errorRate = new Rate('error_rate');
const p99Trend = new Trend('response_time_p99');

export const options = {
  stages: [
    { duration: '30s', target: 50 },   // Ramp-up: 50 VUs over 30s
    { duration: '2m', target: 50 },    // Steady state: 50 VUs for 2min
    { duration: '30s', target: 100 },  // Peak: ramp to 100 VUs
    { duration: '1m', target: 100 },   // Peak hold
    { duration: '30s', target: 0 },    // Cool down
  ],
  thresholds: {
    http_req_duration: ['p(95)<500', 'p(99)<1000'], // p95<500ms, p99<1000ms
    http_req_failed: ['rate<0.01'],                  // Error rate <1%
  },
};

const BASE_URL = __ENV.BASE_URL || 'http://localhost';

export default function () {
  const scenarios = [
    // Homepage load
    () => {
      const res = http.get(`${BASE_URL}/`);
      check(res, {
        'home status 200': (r) => r.status === 200,
        'home fast': (r) => r.timings.duration < 500,
      });
      errorRate.add(res.status >= 500 ? 1 : 0);
      p99Trend.add(res.timings.duration);
    },
    // API query
    () => {
      const res = http.get(`${BASE_URL}/api/health`);
      check(res, {
        'api status 200': (r) => r.status === 200,
        'api fast': (r) => r.timings.duration < 200,
      });
      errorRate.add(res.status >= 500 ? 1 : 0);
      p99Trend.add(res.timings.duration);
    },
    // Random think time
    () => sleep(Math.random() * 2 + 0.5),
  ];

  const choice = Math.floor(Math.random() * scenarios.length);
  scenarios[choice]();
}
```

## Step 4: Build the LLM Analysis Pipeline

Create the analysis script `tools/analyze_results.py`:

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
    """Initialize baseline database"""
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
    """Parse k6 JSON report"""
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
    """Save performance baseline"""
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
    """Get latest baseline for comparison"""
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
    """Call local LLM to analyze load test results"""
    prompt = f"""You are a professional performance engineer. Analyze the following load test results and provide concise diagnosis and optimization recommendations.

**Test scenario**: {scenario}
**Test time**: {current['timestamp']}

Current results:
- P50 response time: {current['p50_ms']:.2f}ms
- P95 response time: {current['p95_ms']:.2f}ms
- P99 response time: {current['p99_ms']:.2f}ms
- Max response time: {current['max_ms']:.2f}ms
- Throughput: {current['rps']:.2f} req/s
- Error rate: {current['error_rate']:.2%}
- Total requests: {current['total_requests']}

"""
    if baseline:
        p95_change = ((current["p95_ms"] - baseline["p95_ms"]) / baseline["p95_ms"]) * 100
        rps_change = ((current["rps"] - baseline["rps"]) / baseline["rps"]) * 100 if baseline["rps"] else 0
        prompt += f"""Previous baseline ({baseline['timestamp']}):
- P95: {baseline['p95_ms']:.2f}ms, change: {p95_change:+.1f}%
- Throughput: {baseline['rps']:.2f} req/s, change: {rps_change:+.1f}%
"""
    else:
        prompt += "(First test, no historical baseline for comparison)\n"

    prompt += """
Reply in this format:
1. **Health Status**: 🟢 Normal / 🟡 Warning / 🔴 Critical
2. **Key Findings**: 2-3 most important observations
3. **Optimization Recommendations**: Specific, actionable tuning commands or config suggestions
4. **Risk Notes**: Point out any potential risks

Keep it concise, each point no more than 2 lines."""

    try:
        result = subprocess.run(
            ["ollama", "run", MODEL, prompt],
            capture_output=True, text=True, timeout=60
        )
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        return "LLM analysis timed out. Check Ollama service status."
    except Exception as e:
        return f"LLM call failed: {e}"


def check_regression(current: dict, baseline: dict) -> list[dict]:
    """Detect performance regressions"""
    alerts = []
    thresholds = {"p95_ms": 0.20, "rps": -0.15, "error_rate": 0.01}

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
    parser.add_argument("--scenario", default="default", help="Test scenario name")
    parser.add_argument("--vus", type=int, default=50, help="Virtual user count")
    parser.add_argument("--notify", action="store_true", help="Send notification")
    args = parser.parse_args()

    conn = init_db()

    current = parse_k6_report(args.report)
    print(f"✅ Parsed: P95={current['p95_ms']:.1f}ms, RPS={current['rps']:.1f}, Errors={current['error_rate']:.2%}")

    save_baseline(conn, current, args.scenario, args.vus)

    baseline = get_latest_baseline(conn, args.scenario)
    analysis = analyze_with_llm(current, baseline, args.scenario)
    print(f"\n🤖 LLM Analysis:\n{analysis}")

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
            print(f"\n⚠️ Detected {len(alerts)} performance regressions!")
        else:
            print("\n✅ No performance regressions, all metrics normal")

    conn.close()


if __name__ == "__main__":
    main()
```

## Step 5: Docker Compose One-Click Deployment

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  # ─── Ollama (LLM Analysis Engine) ───
  ollama:
    image: ollama/ollama:latest
    container_name: vps-ollama
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama
    restart: unless-stopped

  # ─── k6 Load Test Runner ───
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

  # ─── Grafana (Visualization) ───
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

## Step 6: Create Scheduler & Auto-Trigger

Create `scripts/run-benchmark.sh`:

```bash
#!/bin/bash
set -euo pipefail

SCENARIO="${1:-default}"
VUS="${2:-50}"
REPORT_DIR="/root/vps-ops/reports"
mkdir -p "$REPORT_DIR"

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
REPORT_FILE="$REPORT_DIR/${SCENARIO}-${TIMESTAMP}.json"

echo "🚀 Starting load test: scenario=$SCENARIO, vus=$VUS"

docker run --rm \
  -v "$PWD/loadtest:/mnt/scripts" \
  -v "$REPORT_DIR:/mnt/reports" \
  -e BASE_URL="${BASE_URL:-http://localhost}" \
  grafana/k6:latest run \
  --out json=/mnt/reports/${SCENARIO}-${TIMESTAMP}.json \
  /mnt/scripts/http_probe.js \
  --vus $VUS --duration 180s

echo "📊 Report saved: $REPORT_FILE"

echo "🤖 Starting LLM analysis..."
python3 /root/vps-ops/tools/analyze_results.py \
  --report "$REPORT_FILE" \
  --scenario "$SCENARIO" \
  --vus "$VUS"

echo "✅ Load test and analysis complete"
```

Add cron scheduled tasks:

```bash
# Daily baseline load test at 3 AM
crontab -e
# Add:
0 3 * * * cd /root/vps-ops && bash scripts/run-benchmark.sh default 50 >> /var/log/vps-benchmark.log 2>&1

# Weekly stress test (100 concurrent) on Sundays
0 4 * * 0 cd /root/vps-ops && bash scripts/run-benchmark.sh stress 100 >> /var/log/vps-benchmark.log 2>&1
```

## Step 7: CI/CD Integration (Optional)

Integrate load testing into GitHub Actions, auto-validating performance after every deployment:

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
          p95=$(jq '.metrics.http_req_duration."p(95)"' k6-result.json)
          if (( $(echo "$p95 > 500" | bc -l) )); then
            echo "⚠️ P95 exceeds 500ms threshold"
            exit 1
          fi
```

## Real-World Output Example

A typical load test analysis report output:

```
✅ Parsed: P95=142.3ms, RPS=287.5, Errors=0.00%

🤖 LLM Analysis:
1. **Health Status**: 🟢 Normal
2. **Key Findings**:
   - P95 response time improved 18% vs last run (28ms → 23ms), excellent
   - Throughput stable at 287 req/s, no fluctuation
   - Zero errors, service fully stable
3. **Optimization Recommendations**:
   - Current config is already good; consider increasing to 100 VUs to test limits
   - Enable gzip compression to reduce bandwidth by ~30%
4. **Risk Notes**: None

✅ No performance regressions, all metrics normal
```

## Advanced: Connect Grafana Visualization

Configure the k6 official Dashboard JSON in `grafana/dashboards/` to see in Grafana:
- Real-time throughput curves
- Response time percentiles (P50/P95/P99) trends
- Error rate changes
- Concurrent user count waveforms
- Baseline comparison overlay charts

## Summary

The core value of this system is **turning performance optimization experience into repeatable, quantifiable automation**:

1. **Automated load testing**: Scheduled or trigger-based execution, no manual intervention needed
2. **AI-powered analysis**: Local LLM understands results and generates readable reports with optimization advice
3. **Baseline tracking**: SQLite persistence for full historical recall
4. **Regression alerting**: Auto-detects performance degradation, early detection = early fix
5. **CI/CD integration**: Auto-validation on every deployment, preventing performance rollback

Cost is nearly zero: a 4GB RAM VPS + Ollama + k6 + Grafana, under $5/month.

Start building your AI load testing system now—let data replace intuition, let automation replace manual effort.
