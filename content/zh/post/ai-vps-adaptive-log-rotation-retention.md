---
title: "AI 驱动的 VPS 日志智能轮转与保留策略：从固定周期到自适应生命周期管理"
description: "Logrotate 固定 7 天保留、日志盘写满触发 OOM——这些痛点的根源是"一刀切"。本文介绍如何用本地 LLM（Ollama + Qwen2.5）分析日志价值密度、异常密度和服务重要性，动态生成每个日志目录的轮转周期、压缩策略和保留天数，并生成可执行的 systemd timer 方案"
date: 2026-10-07T20:00:00+08:00
lastmod: 2026-10-07T20:00:00+08:00
slug: "ai-vps-adaptive-log-rotation-retention"
image: /images/posts/ai-vps-adaptive-log-rotation-retention/featured.png
tags: ["AI", "VPS", "日志管理", "Logrotate", "LLM", "Ollama", "Qwen2.5", "磁盘优化", "自适应策略"]
categories: ["AI 运维"]
aliases: [/zh/post/ai-vps-adaptive-log-rotation-retention/]
---

## 引言

VPS 日志管理有一个经典困境：**保留太短，故障排查时关键日志已经没了；保留太长，磁盘写满、IO 打满，服务直接宕机。**

多数人的方案是：

```bash
# 经典的"一刀切" logrotate 配置
/var/log/nginx/*.log {
    daily
    rotate 7          # 固定 7 天
    compress
    missingok
}
```

简单、能跑、但完全不智能：

- **Nginx 访问日志**（日均 50MB，正常无异常）和 **应用错误日志**（日均 200KB，但每条都是潜在故障线索）用同一个 7 天保留策略；
- **CI/CD 构建日志**（一次构建几百 MB，保留 30 天完全浪费）和 **安全审计日志**（保留 30 天远远不够，合规要求 90 天）也共用同一个策略；
- 日志目录越来越多，手动逐个调 logrotate 配置不可持续。

**AI 自适应日志生命周期管理**的思路是：让 LLM 分析每个日志目录的**价值密度**（异常日志占比）、**数据增长速率**和**业务重要性**，动态计算出每个目录最合理的轮转周期、压缩方式和保留天数——不是 7 天，也不是 30 天，而是**恰好是你需要的天数**。

---

## 架构设计

```
┌─────────────────────────────────────────────────────────┐
│                    VPS 日志目录（/var/log/）             │
│  nginx/  app-error/  build/  security-audit/  ...      │
└──────────────┬──────────────────────────────────────────┘
               │ 采样（最近 N 小时）
               ▼
┌─────────────────────────────────────────────────────────┐
│            日志分析器（Python 脚本）                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐     │
│  │ 异常密度   │  │ 增长率    │  │ 数据价值评分     │     │
│  │(grep/统计) │  │(du/df)   │  │(LLM 语义判断)    │     │
│  └──────┬───┘  └──────┬───┘  └────────┬─────────┘     │
└─────────┼──────────────┼───────────────┼────────────────┘
          │              │               │
          ▼              ▼               ▼
┌─────────────────────────────────────────────────────────┐
│              Ollama + Qwen2.5（本地推理）                 │
│  输入：日志样本 + 目录元数据 + 业务标签                     │
│  输出：JSON 格式轮转/保留建议（含置信度）                  │
└────────────────────────────┬────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────┐
│              策略生成器（Python）                         │
│  → 生成 /etc/logrotate.d/* 配置                          │
│  → 生成 systemd timer 替代 cron（精确到小时）             │
│  → 生成 Grafana dashboard 数据源配置                     │
└────────────────────────────┬────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────┐
│              告警通道（Telegram Bot）                     │
│  策略变更通知 / 磁盘水位预警 / 日志异常密度飙升告警         │
└─────────────────────────────────────────────────────────┘
```

---

## 实现步骤

### 1. 安装 Ollama 并拉取 Qwen2.5

```bash
# 安装 Ollama（2GB 内存 VPS 可用）
curl -fsSL https://ollama.com/install.sh | sh

# 拉取 Qwen2.5 7B（4GB 量化版，适合 2GB+ VPS）
ollama pull qwen2.5:7b-q4_0
```

验证：

```bash
curl -s http://localhost:11434/api/generate \
  -d '{"model":"qwen2.5:7b-q4_0","prompt":"你好","stream":false}' \
  | python3 -m json.tool
```

### 2. 日志采样器：收集目录元数据

```python
#!/usr/bin/env python3
"""
log_sampler.py — 采样 /var/log/ 下各目录的关键指标
"""
import os, json, time, re
from pathlib import Path
from datetime import datetime, timedelta

LOG_ROOT = "/var/log"
SAMPLE_DIR = Path("/tmp/log_analysis_samples")
SAMPLE_DIR.mkdir(exist_ok=True)

# 关注的日志目录（按需扩展）
TARGET_DIRS = [
    "nginx/access.log",
    "nginx/error.log",
    "app/production.log",
    "app/error.log",
    "build/ci-build.log",
    "security/audit.log",
    "security/fail2ban.log",
]

def count_lines(filepath, max_lines=50000):
    """快速统计行数（上限 5 万行避免大文件阻塞）"""
    count = 0
    with open(filepath, 'r', errors='replace') as f:
        for _ in f:
            count += 1
            if count >= max_lines:
                break
    return count

def sample_anomalies(filepath, keywords=None, max_scan_lines=20000):
    """
    统计异常日志占比
    keywords: 各服务的异常关键词（可扩展）
    """
    if keywords is None:
        keywords = [
            r'\b(ERROR|FATAL|CRITICAL)\b',
            r'OOMKilled', r'memory cgroup out of memory',
            r'segmentation fault', r'kernel panic',
            r'connection refused', r'timeout', r'5\d\d',
        ]

    total = 0
    anomalies = 0
    with open(filepath, 'r', errors='replace') as f:
        for line in f:
            total += 1
            if total > max_scan_lines:
                break
            for kw in keywords:
                if re.search(kw, line, re.IGNORECASE):
                    anomalies += 1
                    break
    return anomalies, total

def get_disk_usage(path):
    st = os.statvfs(path)
    return {
        "total_gb": st.f_blocks * st.f_frsize / (1024**3),
        "used_gb": (st.f_blocks - st.f_bfree) * st.f_frsize / (1024**3),
        "used_pct": round((1 - st.f_bfree / st.f_blocks) * 100, 1),
    }

def dir_daily_growth(filepath, days=7):
    """估算日均增长（基于文件修改时间和大小）"""
    try:
        stat = os.stat(filepath)
        mtime = datetime.fromtimestamp(stat.st_mtime)
        age_days = max((datetime.now() - mtime).total_seconds() / 86400, 1)
        return round(stat.st_size / 1024 / 1024 / age_days, 3)  # MB/day
    except:
        return 0.0

def main():
    results = {}
    disk = get_disk_usage(LOG_ROOT)

    for rel in TARGET_DIRS:
        filepath = os.path.join(LOG_ROOT, rel)
        if not os.path.exists(filepath):
            continue

        anomalies, total = sample_anomalies(filepath)
        anomaly_density = anomalies / total if total else 0.0
        daily_mb = dir_daily_growth(filepath)

        results[rel] = {
            "size_mb": round(os.path.getsize(filepath) / 1024**2, 2),
            "total_lines_scanned": total,
            "anomaly_count": anomalies,
            "anomaly_density": round(anomaly_density, 4),
            "daily_growth_mb": daily_mb,
        }

    meta = {
        "timestamp": datetime.now().isoformat(),
        "disk": disk,
        "dirs": results,
    }

    out_file = SAMPLE_DIR / f"meta_{int(time.time())}.json"
    out_file.write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    print(f"采样完成 → {out_file}")
    return meta

if __name__ == "__main__":
    main()
```

### 3. LLM 策略生成器：核心提示词

```python
#!/usr/bin/env python3
"""
llm_strategy.py — 调用本地 Ollama 生成每个目录的轮转/保留策略
"""
import json, urllib.request

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen2.5:7b-q4_0"

SYSTEM_PROMPT = """\
你是一名 VPS 日志管理专家。根据提供的日志目录指标，生成最优的轮转和保留策略。

规则：
- 异常密度 > 5% 的目录：保留天数 ≥ 30（故障排查需要足够历史）
- 异常密度 1~5%：保留 14~30 天
- 异常密度 < 1%：保留 7~14 天（正常日志价值低）
- 日均增长 > 100MB 的目录：必须压缩（compress），轮转周期 ≤ 1 天
- 日均增长 10~100MB：压缩 + 轮转周期 1~3 天
- 日均增长 < 10MB：可不压缩，轮转周期 7~30 天
- 安全审计日志（audit/fail2ban）：强制保留 ≥ 90 天（合规要求）
- 构建日志（build/ci）：保留 3~7 天即可（可重新触发）
- 输出必须是合法 JSON，不要包含 markdown 代码块

输出格式（JSON）：
{
  "directory": "nginx/access.log",
  "rotation_period_days": 1,
  "compress": true,
  "retention_days": 7,
  "reasoning": "访问日志量大（日均 150MB），异常密度 0.3%，低价值高频数据，日轮转+压缩+保留7天",
  "confidence": 0.85
}
"""

def call_ollama(prompt: str) -> dict:
    payload = json.dumps({
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "system": SYSTEM_PROMPT,
        "options": {"temperature": 0.1, "num_predict": 1024}
    }).encode()

    req = urllib.request.Request(
        OLLAMA_URL, data=payload,
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        result = json.loads(resp.read())
    return result.get("response", "")

def generate_strategy(meta: dict) -> list:
    strategies = []
    for dir_path, data in meta["dirs"].items():
        user_prompt = f"""
日志目录: /var/log/{dir_path}
当前大小: {data['size_mb']} MB
日均增长: {data['daily_growth_mb']} MB/天
异常密度: {data['anomaly_density']*100:.2f}% (扫描 {data['total_lines_scanned']} 行，异常 {data['anomaly_count']} 条)
磁盘已用: {meta['disk']['used_pct']}%

请生成该目录的轮转策略。
"""
        try:
            raw = call_ollama(user_prompt).strip()
            # 提取 JSON（兼容 LLM 有时加了 ```json 包裹）
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            strategy = json.loads(raw)
            strategy["directory"] = f"/var/log/{dir_path}"
            strategies.append(strategy)
        except Exception as e:
            print(f"[WARN] {dir_path} 策略生成失败: {e}")

    return strategies

if __name__ == "__main__":
    import sys
    meta_file = sys.argv[1] if len(sys.argv) > 1 else None
    if meta_file:
        meta = json.load(open(meta_file))
        s = generate_strategy(meta)
        print(json.dumps(s, indent=2, ensure_ascii=False))
```

### 4. 生成 logrotate 配置 + systemd timer

```python
#!/usr/bin/env python3
"""
strategy_applier.py — 将 LLM 策略落地为可执行配置
"""
import json, os, stat
from pathlib import Path

LOGROTATE_CONF = Path("/etc/logrotate.d/ai-adaptive")
LOGROTATE_CONF.parent.mkdir(parents=True, exist_ok=True)

def generate_logrotate_conf(strategies: list) -> str:
    lines = ["# 由 AI 自适应日志策略生成 — 修改请重新运行 llm_strategy.py\n"]
    for s in strategies:
        dir_path = s.get("directory", "")
        period = s.get("rotation_period_days", 1)
        compress = s.get("compress", True)
        retention = s.get("retention_days", 7)

        if period == 1:
            period_str = "daily"
        elif period == 7:
            period_str = "weekly"
        elif period == 30:
            period_str = "monthly"
        else:
            period_str = f"{period}"  # logrotate 支持数字（小时）需配合 hourdelay

        lines.append(f'{dir_path} {{')
        lines.append(f'    {period_str}')
        lines.append(f'    rotate {retention}')
        if compress:
            lines.append('    compress')
            lines.append('    delaycompress')  # 最近一份不压缩，方便实时查看
        lines.append('    missingok')
        lines.append('    notifempty')
        lines.append('}\n')

    return "\n".join(lines)

def write_logrotate(strategies: list):
    conf = generate_logrotate_conf(strategies)
    LOGROTATE_CONF.write_text(conf)
    # 确保 logrotate 可以读取
    os.chmod(LOGROTATE_CONF, 0o644)
    print(f"✅ 已写入 {LOGROTATE_CONF}")
    print("-----")
    print(conf)

def generate_systemd_timer(strategies: list):
    """
    用 systemd timer 替代 cron，精确到小时
    /usr/local/bin/log_rotate_hourly.sh → 每小时执行
    """
    timer_unit = """[Unit]
Description=AI Adaptive Log Rotation (Hourly)

[Service]
Type=oneshot
ExecStart=/usr/local/bin/log_rotate_hourly.sh
User=root

[Install]
WantedBy=timers.target
"""
    timer_file = Path("/etc/systemd/system/ai-log-rotate.timer")
    timer_file.write_text(timer_unit)
    print(f"✅ systemd timer 已写入 {timer_file}")
    print("运行: systemctl enable --now ai-log-rotate.timer")

if __name__ == "__main__":
    import sys
    strategies = json.load(open(sys.argv[1]))
    write_logrotate(strategies)
    generate_systemd_timer(strategies)
```

### 5. 磁盘水位监控 + Telegram 告警

```python
#!/usr/bin/env python3
"""
disk_guard.py — 磁盘水位守护（systemd timer 每 15 分钟运行）
"""
import os, json, urllib.request, urllib.parse
from pathlib import Path

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")

def send_telegram(text: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"[DRY-RUN] Telegram: {text}")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown"
    }).encode()
    urllib.request.urlopen(
        urllib.request.Request(url, data=data), timeout=10
    )

def check_disk():
    st = os.statvfs("/var/log")
    used_pct = (1 - st.f_bfree / st.f_blocks) * 100

    if used_pct >= 90:
        send_telegram(
            f"🚨 VPS 日志磁盘水位预警\n"
            f"已用: {used_pct:.1f}%\n"
            f"建议: 立即手动执行 logrotate -f /etc/logrotate.conf\n"
            f"或运行 python3 /usr/local/bin/llm_strategy.py 重新生成策略"
        )
    elif used_pct >= 75:
        send_telegram(
            f"⚠️ VPS 日志磁盘用量 {used_pct:.1f}%\n"
            f"接近告警阈值，建议检查 AI 策略是否生效"
        )

if __name__ == "__main__":
    check_disk()
```

注册 systemd timer（每 15 分钟）：

```bash
cat > /etc/systemd/system/disk-guard.timer <<'EOF'
[Unit]
Description=Disk Water Guard (15min)

[Timer]
OnBoot=15min
OnUnitActiveSec=15min

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now disk-guard.timer
```

---

## 完整运行流程

```bash
# 1. 采样
python3 /usr/local/bin/log_sampler.py > /tmp/log_meta.json

# 2. LLM 生成策略（Ollama 需先启动：systemctl enable --now ollama）
python3 /usr/local/bin/llm_strategy.py /tmp/log_meta.json > /tmp/strategies.json

# 3. 应用策略
python3 /usr/local/bin/strategy_applier.py /tmp/strategies.json

# 4. 验证
logrotate -d /etc/logrotate.conf   # dry-run，不实际轮转
systemctl list-timers             # 确认 timer 已注册
```

**预期输出示例：**

```json
[
  {
    "directory": "/var/log/nginx/access.log",
    "rotation_period_days": 1,
    "compress": true,
    "retention_days": 7,
    "reasoning": "访问日志日均 150MB，异常密度 0.2%，高频低价值，日轮转+压缩+保留 7 天",
    "confidence": 0.82
  },
  {
    "directory": "/var/log/app/error.log",
    "rotation_period_days": 1,
    "compress": false,
    "retention_days": 30,
    "reasoning": "错误日志异常密度 12.4%，每条都是潜在故障线索，保留 30 天不压缩便于快速检索",
    "confidence": 0.91
  },
  {
    "directory": "/var/log/security/audit.log",
    "rotation_period_days": 1,
    "compress": true,
    "retention_days": 90,
    "reasoning": "安全审计日志合规要求 90 天，必须保留，压缩降低磁盘占用",
    "confidence": 0.97
  },
  {
    "directory": "/var/log/build/ci-build.log",
    "rotation_period_days": 1,
    "compress": true,
    "retention_days": 3,
    "reasoning": "构建日志可重新触发，3 天足够排查最近构建失败原因",
    "confidence": 0.79
  }
]
```

---

## 关键设计决策

| 决策点 | 选择 | 原因 |
|--------|------|------|
| LLM 模型 | Qwen2.5 7B q4_0 | 2GB VPS 可运行，推理速度 ~20 token/s，够用 |
| 温度参数 | 0.1 | 策略生成需要确定性，不需要创造性 |
| 轮转执行 | systemd timer | 比 cron 精确，支持依赖管理（Ollama 先启动再跑策略） |
| 告警通道 | Telegram Bot | 轻量、免费、移动端实时 |
| 配置落地 | logrotate（非自研） | 生态成熟，有 dry-run 模式，安全 |

---

## 故障排查

**Q: Ollama 推理超时（>120s）？**
A: 2GB VPS 首次加载模型较慢，后续推理正常。可加 `timeout=180`，或在提示词中限制输出长度（`num_predict: 512`）。

**Q: LLM 输出的 JSON 解析失败？**
A: 这是 LLM 的常见问题。`llm_strategy.py` 中已做了 ````json` 剥离处理。若仍失败，增加 `temperature: 0.0` 或换用 Qwen2.5 14B（需 4GB+ VPS）。

**Q: 策略生成后磁盘占用反而增加了？**
A: 检查 `delaycompress` 选项——最近一份日志不压缩，短时间内磁盘占用会略高。可改为 `compress` 去掉 `delaycompress`，代价是最近日志无法实时查看。

---

## 总结

| 维度 | 传统 logrotate | AI 自适应策略 |
|------|---------------|--------------|
| 保留天数 | 固定 7/14/30 天 | 按异常密度动态计算 |
| 压缩策略 | 全部压缩或不压缩 | 按增长速率判断 |
| 合规日志 | 容易遗漏 | 强制 90 天标记 |
| 维护成本 | 目录增多后不可持续 | 每次重新采样+生成，全自动 |
| 告警 | 无 | Telegram 水位预警 + 策略变更通知 |

**核心价值：把"日志保留"从静态配置问题变成动态决策问题，让 LLM 替你做判断，让 systemd timer 替你做执行。**

---

*本方案适用于 2GB 以上内存的 VPS，Ollama 是核心依赖。若你的 VPS 资源紧张，可将 `llm_strategy.py` 的采样频率从每日降低到每周，减少推理次数。*
