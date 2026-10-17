---
title: "VPS 云成本智能管家：本地 LLM 驱动的账单异常检测与闲置自动关机实战"
description: "云账单总是月底才看到？本文在 VPS 上用本地 LLM（Ollama + Qwen2.5）+ Prometheus 构建智能云成本管家：按小时采集云资源用量与账单，LLM 识别异常消费模式（闲置实例、规格浪费、突发流量），自动关停闲置实例并生成每日省钱报告推送 Telegram，数据不出内网。"
date: 2026-10-17T20:00:00+08:00
lastmod: 2026-10-17T20:00:00+08:00
slug: "ai-vps-cloud-cost-anomaly-autoscale"
tags: ["AI", "云成本", "FinOps", "Prometheus", "Ollama", "VPS运维", "自动化", "省钱"]
categories: ["云成本优化"]
draft: false
image: /images/posts/ai-vps-cloud-cost-anomaly-autoscale/featured.png
aliases: [/zh/post/ai-vps-cloud-cost-anomaly-autoscale/]
---

## 引言：账单不该是月底的惊喜

自托管省钱，最容易被忽视的不是 VPS 本身，而是围绕它的一整圈云资源：

- 为了开发环境留着的**闲置 VPS / 云主机**，每月几百到几千元
- 规格**严重超配**的实例（4 核 8G 跑了个 200MB 内存的静态站）
- 突发流量导致的**带宽超量费**（对象存储、CDN、出站流量）
- 忘了停的**测试集群 / K8s 节点**，7×24 计费
- 快照、磁盘、IP 这些**沉默的固定成本**

传统做法是月底人工翻账单。更好的做法：**让 LLM 每天看一次，异常自动发现，闲置自动关停**。

本文的方案：

```
云账单/用量 API 采集 → Prometheus 时序化 → LLM 异常研判
        ↕                     ↕                    ↕
   多云 API 统一适配      小时级消费曲线      "闲置/超配/突发" 三类模式识别
                                        ↕
                              自动执行（关机/降配建议）
                                        ↕
                              每日省钱报告 → Telegram
```

全链路本地 LLM（Ollama + Qwen2.5），账单数据不出内网。

---

## 整体架构

```
┌─────────────────────────────────────────────────────────┐
│            VPS 云成本智能管家（FinOps + LLM）             │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌──────────┐   ┌──────────┐   ┌───────────────────┐   │
│  │ 云成本   │──▶│ 采集器   │──▶│ Prometheus        │   │
│  │ API 适配层│   │ (Crawler)│   │ (时序存储)         │   │
│  │ (多云)   │   │ 每小时   │   │ 用量+账单双指标    │   │
│  └──────────┘   └──────────┘   └────────┬──────────┘   │
│                                          │              │
│       ▼                                  ▼              │
│  ┌──────────┐   ┌──────────┐   ┌───────────────────┐   │
│  │ 自动执行层│   │ Ollama + │◀──│ 异常检测引擎      │   │
│  │ 关机/降配 │   │ Qwen2.5  │   │ (规则 + LLM 研判) │   │
│  └──────────┘   └──────────┘   └────────┬──────────┘   │
│       ▲                                  │              │
│       │                                  ▼              │
│  ┌──────────┐                    ┌──────────────────┐   │
│  │ 白名单/  │◀─── 安全闸门 ──────│ 每日省钱报告      │   │
│  │ 冷却期   │                    │ → Telegram 推送   │   │
│  └──────────┘                    └──────────────────┘   │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## 第一步：多云成本数据统一采集

不同云厂商的账单 API 差异很大，但输出可以统一为**三个时序指标**：

| 指标 | 含义 | 采集频率 |
|------|------|---------|
| `cloud_cost_hourly{vendor,resource}` | 小时消费金额（元） | 每小时 |
| `cloud_utilization{resource}` | 资源利用率（CPU/内存 0-100） | 每小时 |
| `cloud_traffic_gb{resource,region}` | 出站流量 | 每小时 |

阿里云 / AWS / 腾讯云等都有 OpenAPI 可查账单与监控。这里以"采集器"抽象层为例，写一个最小可运行的 Python 采集器，你只需要实现各厂商的 `fetch` 方法：

```python
#!/usr/bin/env python3
"""
cloud-cost-crawler.py — 多云成本采集器（抽象层）
将各家账单/监控 API 归一化为 Prometheus exposition 格式
"""
from abc import ABC, abstractmethod
from datetime import datetime, timezone

class CostProvider(ABC):
    name: str

    @abstractmethod
    def fetch(self) -> dict:
        """返回 {resource_id: {"cost": float, "cpu": float, "mem": float, "traffic_gb": float, "type": str}}"""

class AliyunProvider(CostProvider):
    name = "aliyun"
    def fetch(self) -> dict:
        # 调用 BSS OpenAPI（QueryBill / QueryInstanceBill）
        # + CMS DescribeMetricLast（CPU/内存利用率）
        # 这里留空，按 AK 自行实现
        raise NotImplementedError

class GenericProvider(CostProvider):
    """通用：从本地账单 CSV 文件解析（适合导出型账单）"""
    name = "local"
    def __init__(self, csv_path: str):
        self.csv_path = csv_path
    def fetch(self) -> dict:
        import csv
        out = {}
        with open(self.csv_path) as f:
            for row in csv.DictReader(f):
                out[row["resource_id"]] = {
                    "cost": float(row.get("cost", 0)),
                    "cpu": float(row.get("cpu", 0)),
                    "mem": float(row.get("mem", 0)),
                    "traffic_gb": float(row.get("traffic_gb", 0)),
                    "type": row.get("type", "vm"),
                }
        return out

def render_exposition(providers: list) -> str:
    """输出 Prometheus text exposition 格式，供 Prometheus 拉取"""
    ts = int(datetime.now(timezone.utc).timestamp())
    lines = []
    for p in providers:
        try:
            data = p.fetch()
        except Exception as e:
            print(f"[warn] provider {p.name} failed: {e}")
            continue
        for rid, m in data.items():
            lines.append(f'cloud_cost_hourly{{vendor="{p.name}",resource="{rid}"}} {m["cost"]} {ts}')
            lines.append(f'cloud_utilization_cpu{{vendor="{p.name}",resource="{rid}"}} {m["cpu"]} {ts}')
            lines.append(f'cloud_utilization_mem{{vendor="{p.name}",resource="{rid}"}} {m["mem"]} {ts}')
            lines.append(f'cloud_traffic_gb{{vendor="{p.name}",resource="{rid}"}} {m["traffic_gb"]} {ts}')
    return "\n".join(lines) + "\n"

if __name__ == "__main__":
    import argparse, http.server, threading

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = render_exposition([GenericProvider("/opt/finops/bill.csv")])
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(body.encode())

    http.server.HTTPServer(("0.0.0.0", 9415), Handler).serve_forever()
```

Prometheus 端添加 scrape 配置（只允许内网访问）：

```yaml
# prometheus.yml 追加
scrape_configs:
  - job_name: "cloud-cost"
    static_configs:
      - targets: ["127.0.0.1:9415"]
    scrape_interval: 1h   # 账单粒度是小时，无需更密
```

> 💡 **成本采集不需要秒级**——1 小时粒度对 FinOps 完全够用，还能省掉大量 API 配额。

---

## 第二步：用 PromQL 预筛"可疑资源"

LLM 很聪明，但直接喂几千条时序给它既浪费 token 又容易幻觉。先用 PromQL 做**粗筛**，只把可疑资源交给 LLM 精判：

```promql
# 1. 高消费 + 低利用率（超配嫌疑）
cloud_cost_hourly * on(resource) group_left cloud_utilization_cpu
  * 100
  < 15
  and on(resource) cloud_cost_hourly > 0.5

# 2. 连续 72 小时零流量（闲置嫌疑，静态站/测试机常见）
absent_over_time(cloud_traffic_gb[72h])
  or (sum by (resource) (increase(cloud_traffic_gb[72h])) == 0)

# 3. 小时消费突刺（突发流量/超量嫌疑）
cloud_cost_hourly > (avg(cloud_cost_hourly[24h]) * 3)
```

把三条结果汇合成一份"嫌疑清单" JSON，这是 LLM 研判的输入：

```bash
#!/usr/bin/env bash
# suspicious-resources.sh — 导出嫌疑资源清单
set -euo pipefail
PROM="http://127.0.0.1:9090"
OUT="/opt/finops/suspicious.json"

{
echo "{"
echo "  \"generated_at\": \"$(date -Iseconds)\","
echo "  \"oversized\": ($(curl -sG "$PROM/api/v1/query" --data-urlencode \
    'query=sum by (resource,vendor) (cloud_cost_hour * cloud_utilization_cpu/100) and on(resource) sum by (resource) (cloud_cost_hourly) > 0.5' | jq '.data.result | map({resource:.metric.resource, cost_hourly:.value[1][0], cpu:.value[1][1], est_daily:.value[1][0]*24})'),"
echo "  \"idle_candidates\": ($(curl -sG "$PROM/api/v1/query" --data-urlencode \
    'query=absent_over_time(cloud_traffic_gb[72h])' | jq '.data.result'),"
echo "  \"spike_alerts\": ($(curl -sG "$PROM/api/v1/query" --data-urlencode \
    'query=cloud_cost_hourly > (avg(cloud_cost_hourly[24h]) * 3)' | jq '.data.result | map({resource:.metric.resource, current:.value[1][0], base_avg:.value[1][1]})'),"
echo "  \"whitelist\": [\"prod-k8s-node-1\", \"backup-db\"]"
echo "}"
} > "$OUT"
echo "✅ 嫌疑清单已生成: $OUT"
```

---

## 第三步：LLM 异常研判（Ollama + Qwen2.5，本地）

```python
#!/usr/bin/env python3
"""
llm-cost-judge.py — LLM 驱动的云成本异常研判
输入: 嫌疑清单 JSON（PromQL 粗筛结果）
输出: 分类结论（闲置可关停 / 超配建议降配 / 突发需关注）+ 每日省钱预估
本地运行（Ollama + Qwen2.5），账单数据不出 VPS
"""
import json, requests

OLLAMA = "http://localhost:11434"
MODEL  = "qwen2.5:7b"

JUDGE_PROMPT = """你是云成本优化（FinOps）专家。以下是从 Prometheus 粗筛出的可疑云资源清单。

嫌疑清单：
{suspicious_json}

白名单（禁止操作）：
{whitelist}

请逐条分析并输出严格 JSON 数组，每项包含：
- resource: 资源 ID
- verdict: 取值为 "idle_shutdown"（闲置可关停）| "oversize_downsize"（超配建议降配）| "spike_watch"（突发流量需关注）| "normal"（实际正常，误报）
- daily_saving_rmb: 若关停/降配，预计每日节省金额（保留 2 位小数）
- reason: 一句话理由（引用具体数值，如"72h 零流量且 CPU 均值 <5%"）
- action: 具体操作建议（如"执行 shutdown / 降配到 2 核 4G"）

规则约束：
1. 白名单资源 verdict 必须为 "normal"
2. 只有连续 72h 零流量 且 无已知定时任务 才能判 idle_shutdown
3. CPU<15% 持续 7 天 且 内存充足 才能判 oversize_downsize
4. 拿不准的一律判 "normal"（宁可放过，不可误杀生产）

只输出 JSON 数组，无额外文字。"""

def judge(suspicious: dict, whitelist: list) -> list:
    payload = JUDGE_PROMPT.format(
        suspicious_json=json.dumps(
            {k: v for k, v in suspicious.items() if k != "whitelist"},
            ensure_ascii=False, indent=2,
        )[:6000],  # 控制 token 上限
        whitelist="\n".join(f"- {w}" for w in whitelist) or "（无）",
    )
    resp = requests.post(
        f"{OLLAMA}/api/generate",
        json={"model": MODEL, "prompt": payload, "stream": False,
              "options": {"temperature": 0.1, "num_ctx": 8192}},
        timeout=180,
    )
    resp.raise_for_status()
    text = resp.json()["response"].strip()
    # 容错：提取 JSON 数组部分
    if "```" in text:
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text)

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--input", default="/opt/finops/suspicious.json")
    p.add_argument("--output", default="/opt/finops/judgement.json")
    args = p.parse_args()

    with open(args.input) as f:
        data = json.load(f)
    result = judge(data, data.get("whitelist", []))

    with open(args.output, "w") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    total = sum(float(r.get("daily_saving_rmb", 0)) for r in result)
    print(f"✅ 研判完成: {len(result)} 条可疑资源，预计每日可省 ¥{total:.2f}")
```

---

## 第四步：自动执行 + 安全闸门

LLM 说的"可关停"不能直接执行——必须有**三重安全闸门**：

1. **白名单**：白名单资源永远跳过
2. **冷却期**：同一资源 7 天内只自动操作一次，防止反复开关机
3. **人工确认开关**：关停动作默认 dry-run，需 `--execute` 才真正执行

```python
#!/usr/bin/env python3
"""
auto-optimizer.py — 根据 LLM 研判结果自动执行成本优化
默认 dry-run；加 --execute 才真正关机/降配
"""
import json, subprocess, time, argparse

STATE = "/opt/finops/cooldown.json"   # 冷却期记录 {resource: last_action_ts}
WHITELIST = {"prod-k8s-node-1", "backup-db"}

def load_state() -> dict:
    try:
        with open(STATE) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_state(s: dict):
    with open(STATE, "w") as f:
        json.dump(s, f, indent=2)

def within_cooldown(s: dict, resource: str, days: int = 7) -> bool:
    last = s.get(resource, 0)
    return (time.time() - last) < days * 86400

def shutdown_vps(resource: str, provider: str):
    """
    按厂商映射关机命令。示例：
      - 阿里云:  aliyun ecs StopInstance --InstanceId <id>
      - AWS:     aws ec2 stop-instances --instance-ids <id>
      - 腾讯云:  tencentcloud cvm StopInstances --InstanceId.0 <id>
      - 本地VM:  走 SSH 执行 systemctl poweroff
    请按实际 AK / 厂商 SDK 实现，建议密钥放 /root/.config/finops/ (chmod 700)
    """
    cmds = {
        "aliyun": ["aliyun", "ecs", "StopInstance", "--InstanceId", resource],
        "aws":    ["aws", "ec2", "stop-instances", "--instance-ids", resource],
        "tencent": ["tencentcloud", "cvm", "StopInstances", "--InstanceId.0", resource],
    }
    cmd = cmds.get(provider, ["echo", "unknown-provider", provider, resource])
    print(f"  -> 执行: {' '.join(cmd)}")
    subprocess.run(cmd, check=False)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--judgement", default="/opt/finops/judgement.json")
    ap.add_argument("--execute", action="store_true",
                    help="真正执行；默认 dry-run 只打印")
    args = ap.parse_args()

    with open(args.judgement) as f:
        verdicts = json.load(f)
    state = load_state()

    for v in verdicts:
        rid = v["resource"]
        if v["verdict"] == "normal" or rid in WHITELIST:
            print(f"  ⏭️  跳过 {rid}（{v['verdict']}）")
            continue
        if within_cooldown(state, rid):
            print(f"  ⏰ {rid} 冷却期内，跳过")
            continue

        if args.execute:
            if v["verdict"] == "idle_shutdown":
                shutdown_vps(rid, provider_hint(rid))
                state[rid] = time.time()
                save_state(state)
                print(f"  ✅ 已关停 {rid}（省 ¥{v.get('daily_saving_rmb')} / 天）")
            elif v["verdict"] == "oversize_downsize":
                print(f"  📐 降配建议：{rid} → {v.get('action')}（需人工执行 API）")
        else:
            print(f"  [dry-run] 将{ '关停' if v['verdict']=='idle_shutdown' else '降配' } {rid}")

    print("（提示：加 --execute 并配好云厂商 CLI 才能真正生效）")

def provider_hint(rid: str) -> str:
    if rid.startswith("i-") and len(rid) > 20: return "aliyun"
    if rid.startswith("i-") and len(rid) == 17: return "aws"
    if rid.startswith("ins-"): return "tencent"
    return "local"

main()
```

> ⚠️ 生产环境强烈建议：先跑一周 dry-run 观察误判率，再加 `--execute`。关停类动作务必保留 7 天冷却期 + 白名单双保险。

---

## 第五步：每日省钱报告 → Telegram

把 LLM 研判结果汇总成一份**人话报告**，推送到 Telegram 频道：

```python
#!/usr/bin/env python3
"""
daily-report.py — 生成每日云成本省钱报告并推送 Telegram
"""
import json, requests

TG_BOT  = "https://api.telegram.org/bot{TOKEN}/sendMessage"   # 从 /root/.config/finops/tg.env 读取
TG_CHAT = "-100123456789"

def render_report(verdicts: list, total_saving: float) -> str:
    lines = ["📊 每日云成本智能管家报告"]
    for v in verdicts:
        icon = {"idle_shutdown": "⏻", "oversize_downsize": "📐",
                "spike_watch": "⚡", "normal": "✅"}[v["verdict"]]
        lines.append(f"{icon} {v['resource']}: {v['reason']}")
        lines.append(f"   建议: {v['action']}")
    lines.append(f"\n💰 今日预计节省: ¥{total_saving:.2f}/天 ≈ ¥{total_saving*30:.0f}/月")
    return "\n".join(lines)

def push_telegram(text: str):
    import os
    from dotenv import load_dotenv
    load_dotenv("/root/.config/finops/tg.env")   # TG_TOKEN=xxx / TG_CHAT=yyy
    r = requests.post(
        f"https://api.telegram.org/bot{os.environ['TG_TOKEN']}/sendMessage",
        json={"chat_id": os.environ["TG_CHAT"], "text": text,
              "parse_mode": "Markdown"},
        timeout=30,
    )
    r.raise_for_status()
    print("✅ 报告已推送 Telegram")

if __name__ == "__main__":
    with open("/opt/finops/judgement.json") as f:
        verdicts = json.load(f)
    total = sum(float(v.get("daily_saving_rmb", 0)) for v in verdicts)
    push_telegram(render_report(verdicts, total))
```

systemd 定时（每天 09:00 跑完整流水线）：

```ini
# /etc/systemd/system/cloud-finops-daily.service
[Unit]
Description=Daily cloud cost LLM judgement + auto-optimize
After=network-online.target ollama.service

[Service]
User=root
WorkingDirectory=/opt/finops
Environment=OLLAMA_HOST=http://localhost:11434
ExecStart=/usr/bin/bash -lc 'bash suspicious-resources.sh && python3 llm-cost-judge.py && python3 auto-optimizer.py && python3 daily-report.py'
# 确认无误后改为: ExecStart=... 'python3 auto-optimizer.py --execute && ...'

[Install]
WantedBy=multi-user.target
```

---

## 成本与资源

| 组件 | 额外内存 | 额外磁盘 | 说明 |
|------|---------|---------|------|
| Ollama + Qwen2.5-7B | ~5 GB（按需） | ~4 GB | 已有则零增量 |
| Prometheus（含账单指标） | ~200 MB | ~1 GB/月 | 账单指标只有小时粒度，非常省 |
| 采集器 + 研判脚本 | 0 | <10 MB | 纯 Python |

**总增量：磁盘 +1 GB（Prometheus 保留 30 天账单数据），无常驻内存开销。**

对比收益：哪怕只帮你关掉 2 台闲置 VPS（~¥300/月），投入产出比就超过 100 倍。

---

## 总结

云成本优化不是"月底看账单"，而是**每天自动体检**：

| 环节 | 传统做法 | 本文方案 |
|------|---------|---------|
| 数据采集 | 手动导出账单 CSV | 多云 API 统一采集 + Prometheus 小时级时序 |
| 异常发现 | 人工翻账单，月底才看到 | PromQL 粗筛 + LLM 精判，每日 09:00 出报告 |
| 闲置处理 | 忘了关，一直计费 | 自动 dry-run → 确认后关机，7 天冷却期 + 白名单双保险 |
| 超配处理 | 凭感觉降配 | LLM 引用具体 CPU/内存数值给出降配建议 |
| 结果触达 | 邮件周报（没人看） | Telegram 每日推送，每条建议附具体数字 |

**下一步可以探索：**
- 接入各厂商"抢占式实例"做降配替代（测试环境省 60-80%）
- 用 SLO 预算驱动：给每个服务设"成本预算"，超预算 LLM 自动降级
- 多 VPS 集群统一 FinOps 看板（参考 `ai-vps-fleet-intelligence-cross-node-correlation`）

> ⚠️ 本文所有 LLM 推理在本地完成，账单数据（含金额、资源 ID）不经过公网。
