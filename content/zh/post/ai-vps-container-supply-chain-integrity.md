---
title: "AI 容器镜像供应链完整性：LLM 驱动的 SBOM 签名与溯源实战"
description: "构建镜像只是第一步，真正安全的是整条供应链。本文用本地 LLM（Ollama + Qwen2.5）+ cosign/Sigstore + Trivy 构建 VPS 上的容器镜像供应链完整性体系：自动 SBOM 生成、密钥签名、溯源验证，以及 LLM 驱动的智能风险研判与自动修复。"
date: 2026-10-13T20:00:00+08:00
lastmod: 2026-10-13T20:00:00+08:00
slug: "ai-vps-container-supply-chain-integrity"
tags: ["AI", "容器安全", "供应链安全", "SBOM", "cosign", "Sigstore", "Trivy", "Ollama", "VPS运维", "自动化"]
categories: ["AI 安全"]
draft: false
image: /images/posts/ai-vps-container-supply-chain-integrity/featured.png
aliases: [/zh/post/ai-vps-container-supply-chain-integrity/]
---

## 引言：镜像构建 ≠ 供应链安全

大多数团队的安全意识止步于 `docker build`。但真正的供应链攻击往往发生在构建之后：

- 构建节点被植入恶意层（Layer 注入）
- 依赖的第三方镜像被投毒（Typosquatting / 仿冒镜像）
- 上游基础镜像被替换（如 `alpine` 被替换为恶意 fork）
- 本地 `docker pull` 拉取了被篡改的镜像
- 缺少签名验证，任何镜像都可以运行

**核心问题：你无法证明"这个镜像就是你构建的那个"，也无法证明"它没有被篡改"。**

本文的方案在 VPS 上构建一套完整的**容器镜像供应链完整性体系**：

```
构建 → SBOM 生成 → cosign 签名 → Trivy 扫描 → LLM 风险研判
       ↕                    ↕
   Sigstore 公钥          自动修复建议
       ↕
   部署时验证签名 + 溯源
```

全链路本地 LLM（Ollama + Qwen2.5），数据不出内网。

---

## 整体架构

```
┌─────────────────────────────────────────────────────────┐
│  VPS 容器镜像供应链完整性体系                              │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌──────────┐   ┌──────────┐   ┌───────────────────┐   │
│  │ CI/CD    │──▶│ SBOM     │──▶│ Trivy 扫描        │   │
│  │ 构建镜像  │   │ (Syft)   │   │ (CVE + 漏洞评级)   │   │
│  └──────────┘   └──────────┘   └────────┬──────────┘   │
│       │                                  │              │
│       ▼                                  ▼              │
│  ┌──────────┐   ┌──────────┐   ┌───────────────────┐   │
│  │ cosign   │──▶│ Sigstore │   │ Ollama + Qwen2.5  │   │
│  │ 签名     │   │ 公钥注册  │   │ 风险研判 + 修复建议  │   │
│  └──────────┘   └──────────┘   └────────┬──────────┘   │
│       ▲                                  │              │
│       │                                  ▼              │
│  ┌──────────┐                    ┌──────────────────┐   │
│  │ 部署验证  │◀───────────────────│ Telegram 通知      │   │
│  │ cosign   │  阻断未签名/篡改镜像 │ + 修复报告推送     │   │
│  └──────────┘                    └──────────────────┘   │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## 第一步：安装核心工具链

在 VPS（Ubuntu 24.04）上一次性安装所有工具：

```bash
# Trivy — 镜像扫描
curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh | sh -s -- -b /usr/local/bin

# Syft — SBOM 生成
curl -sfL https://raw.githubusercontent.com/anchore/syft/main/install.sh | sh -s -- -b /usr/local/bin

# cosign — 镜像签名/验证
curl -sfL https://github.com/sigstore/cosign/releases/download/v2.4.0/cosign-linux-amd64 \
  -o /usr/local/bin/cosign && chmod +x /usr/local/bin/cosign

# 验证
trivy --version && syft --version && cosign version
```

> **注意**：cosign 默认使用 Sigstore 的公共密钥服务（fulcio.sigs.k8s.io），在 VPS 上可以配置离线密钥对避免依赖外部服务：
>
> ```bash
> mkdir -p ~/.cosign && chmod 700 ~/.cosign
> cosign generate key-pair --key gen-key:password --output-key \
>   /root/.cosign/cosign.key --output-public-key /root/.cosign/cosign.pub
> ```

---

## 第二步：生成 SBOM（Software Bill of Materials）

SBOM 是供应链安全的"成分表"——它记录镜像中每一个依赖的精确版本。没有它，你就无法回答"这个镜像里有什么"。

```bash
# 对构建好的镜像生成 SBOM（CycloneDX 格式，机器可读）
syft pkg:registry --output cyclonedx-json:myapp:1.2.3 --file sbom.cdx.json

# 也可以针对 Dockerfile 静态生成（CI 阶段，无需拉取镜像）
syft . --output cyclonedx-json:sbom.cdx.json
```

**为什么选 CycloneDX 而不是 SPDX？**

| 维度 | CycloneDX | SPDX |
|------|-----------|------|
| 生态支持 | GitHub/Trivy/Syft 原生 | Linux 基金会 |
| 漏洞数据 | Trivy 直接消费 | 需转换 |
| 供应链完整性 | Sigstore 推荐 | 逐步支持 |
| 本文场景 | ✅ 推荐 | 备选 |

---

## 第三步：cosign 签名 + Sigstore 溯源

签名是证明"这个镜像确实是构建方产出的"的关键。使用离线密钥对（避免依赖 fulcio）：

```bash
export COSIGN_KEY=/root/.cosign/cosign.key
export COSIGN_PASSWORD="your-strong-password"

# 签名镜像（推送到你的私有 registry）
cosign sign --registry-allowlist my.registry.local \
  my.registry.local/myapp:1.2.3

# 同时签名 SBOM（证明 SBOM 与镜像对应关系）
cosign sign --sbom sbom.cdx.json \
  my.registry.local/myapp:1.2.3

# 验证（部署时执行）
cosign verify --key /root/.cosign/cosign.pub \
  my.registry.local/myapp:1.2.3
```

**部署时强制验证（在 K8s 或 Docker 启动脚本中）：**

```bash
#!/usr/bin/env bash
# secure-pull.sh — 只拉取已签名且通过验证的镜像
set -euo pipefail

IMAGE="${1:?usage: secure-pull.sh <image>}"

# 1. 拉取
docker pull "$IMAGE"

# 2. 验证签名
cosign verify --key /root/.cosign/cosign.pub "$IMAGE" 2>/dev/null
if [[ $? -eq 0 ]]; then
  echo "✅ Signature valid: $IMAGE"
else
  echo "❌ Signature invalid or missing: $IMAGE" >&2
  exit 1
fi

# 3. 验证 SBOM 完整性（确保 SBOM 与镜像哈希一致）
cosign verify --sbom "$IMAGE" 2>/dev/null
echo "✅ SBOM integrity confirmed"
```

---

## 第四步：Trivy 扫描 + LLM 风险研判

这是整条链路中最有价值的一环。Trivy 告诉你"有 47 个 CVE"，但**哪个真正影响你的业务？哪个可以延期？哪个需要立刻修？**——这是 LLM 的强项。

### 4.1 扫描并导出 JSON

```bash
trivy image --format json --output trivy-report.json \
  --severity CRITICAL,HIGH \
  my.registry.local/myapp:1.2.3
```

### 4.2 LLM 风险研判脚本

```python
#!/usr/bin/env python3
"""
LLM 驱动的 CVE 风险研判
输入: trivy JSON 报告 + SBOM + 业务上下文
输出: 优先级排序的修复计划 + 理由
本地运行（Ollama + Qwen2.5），数据不出 VPS
"""
import json
import requests

OLLAMA = "http://localhost:11434"
MODEL  = "qwen2.5:7b"

def load_scan_report(path: str) -> dict:
    with open(path) as f:
        return json.load(f)

def build_prompt(report: dict, sbom: dict, context: str) -> str:
    vulns = report.get("Results", [{}])[0].get("Vulnerabilities", [])
    critical = [v for v in vulns if v.get("Severity") == "CRITICAL"]
    high     = [v for v in vulns if v.get("Severity") == "HIGH"]

    # 只取 top 20 避免 token 爆炸
    top_vulns = (critical + high)[:20]
    vuln_lines = []
    for v in top_vulns:
        pkg = v.get("PkgName", "unknown")
        ver = v.get("InstalledVersion", "?")
        fixed = v.get("FixedVersion", "none")
        cve = v.get("VulnerabilityID", "N/A")
        cvss = v.get("CVSS", [{}])[0].get("V3Score", "N/A") if "CVSS" in v else "N/A"
        vuln_lines.append(f"  {cve} [{v.get('Severity')}] {pkg}@{ver} → fix {fixed} (CVSS {cvss})")

    prompt = f"""你是 VPS 容器安全专家。以下是 Trivy 扫描结果（前 {len(top_vulns)} 条高危/严重漏洞）：

{chr(10).join(vuln_lines)}

业务上下文：{context}

SBOM 摘要（前 5 个直接依赖）：
{json.dumps(list(sbom.get('components', {}).values())[:5] if 'components' in sbom else {}, indent=2)[:800]}

请输出：
1. 需要**立即修复**的 CVE 列表（附理由：是否可被网络利用、是否在入口点）
2. 可以**延期至下个迭代**的 CVE（附理由）
3. 每个需要修复的 CVE 给出具体操作（如 apt-get upgrade / 升级基础镜像 tag）
4. 如果基础镜像有可用安全更新，给出升级后的 tag 建议

格式：Markdown，中文。
"""
    return prompt

def llm_judge(report: dict, sbom: dict, context: str) -> str:
    prompt = build_prompt(report, sbom, context)
    resp = requests.post(
        f"{OLLAMA}/api/chat",
        json={
            "model": MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {"temperature": 0.2, "num_ctx": 8192},
        },
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["message"]["content"]

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("report", help="trivy JSON report path")
    p.add_argument("sbom",   help="Syft CycloneDX JSON path")
    p.add_argument("--context", default="Web 应用，对外暴露 80/443", help="业务上下文描述")
    args = p.parse_args()

    result = llm_judge(load_scan_report(args.report),
                       json.load(open(args.sbom)),
                       args.context)
    print(result)
```

**运行示例：**

```bash
python3 llm-cve-judge.py \
  --report trivy-report.json \
  --sbom sbom.cdx.json \
  --context "Node.js Web 应用，Express 框架，对外 443，无数据库"

# 输出示例：
# 1. 立即修复
#    - CVE-2025-XXXXX (CRITICAL, CVSS 9.8) pkg:node@18.x → 18.20.4
#      理由：该 CVE 影响 http 解析模块，攻击者可通过畸形 HTTP 请求触发 RCE，
#      且 443 端口对外暴露，属于**网络可利用**。
#      操作：升级基础镜像 FROM node:18 → node:18.20.4
#
# 2. 可延期
#    - CVE-2025-YYYYY (HIGH, CVSS 7.5) pkg:lodash@4.17.20
#      理由：影响 prototype 污染，但当前代码中未使用 lodash 的 merge 函数，
#      实际攻击面极小，可在下个迭代统一升级至 4.17.21。
```

---

## 第五步：自动化修复流水线

将 LLM 建议转化为可执行的修复操作，并在 CI 中自动触发：

```yaml
# .github/workflows/supply-chain.yaml
# 触发条件：Dockerfile 变更 或 每周定时
on:
  push:
    paths:
      - "Dockerfile"
      - ".github/workflows/supply-chain.yaml"
  schedule:
    - cron: "0 2 * * 1"   # 每周一 02:00 UTC

jobs:
  scan-sign-deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Generate SBOM
        run: |
          syft . --output cyclonedx-json:sbom.cdx.json

      - name: Build image
        run: docker build -t my.registry.local/myapp:${{ github.sha }} .

      - name: Trivy scan (fail on CRITICAL)
        uses: aquasecurity/trivy-action@master
        with:
          image: my.registry.local/myapp:${{ github.sha }}
          format: json
          output: trivy-report.json
          severity: CRITICAL,HIGH
          exit-code: "1"

      - name: LLM CVE triage
        id: llm_triage
        run: |
          python3 llm-cve-judge.py \
            --report trivy-report.json \
            --sbom sbom.cdx.json \
            --context "Node.js Web 应用，Express，对外 443" \
            > llm-triage.md

      - name: Sign image
        env:
          COSIGN_KEY: ${{ secrets.COSIGN_KEY }}
          COSIGN_PASSWORD: ${{ secrets.COSIGN_PASSWORD }}
        run: |
          docker push my.registry.local/myapp:${{ github.sha }}
          cosign sign my.registry.local/myapp:${{ github.sha }}
          cosign sign --sbom sbom.cdx.json my.registry.local/myapp:${{ github.sha }}

      - name: Push SBOM artifact
        uses: actions/upload-artifact@v4
        with:
          name: sbom-${{ github.sha }}
          path: sbom.cdx.json

      - name: Push LLM triage report
        uses: actions/upload-artifact@v4
        with:
          name: llm-triage-${{ github.sha }}
          path: llm-triage.md
```

---

## 第六步：部署侧强制验证（VPS 本地）

在 VPS 的部署脚本中嵌入签名验证，确保只有经过完整供应链的镜像才能上线：

```bash
#!/usr/bin/env bash
# deploy-verified.sh — 在 VPS 上部署前验证完整供应链
set -euo pipefail

IMAGE="${1:?usage: deploy-verified.sh <image:tag>}"
PUB_KEY="/root/.cosign/cosign.pub"
SBOM_PATH="/var/lib/supply-chain/sbom-${IMAGE##*:}.cdx.json"

echo "=== 1. 验证 cosign 签名 ==="
cosign verify --key "$PUB_KEY" "$IMAGE"
echo "   ✅ 签名有效"

echo "=== 2. 验证 SBOM 与镜像绑定 ==="
cosign verify --sbom "$IMAGE"
echo "   ✅ SBOM 完整性确认"

echo "=== 3. 检查 SBOM 是否在允许列表 ==="
if [[ -f "$SBOM_PATH" ]]; then
  echo "   ✅ SBOM 已在本地缓存"
else
  echo "   ⚠️  首次部署，拉取 SBOM 并缓存..."
  cosign download sbom "$IMAGE" -o "$SBOM_PATH"
fi

echo "=== 4. Trivy 最终扫描（仅 CRITICAL） ==="
trivy image --severity CRITICAL "$IMAGE"
if [[ $? -eq 0 ]]; then
  echo "   ✅ 无 CRITICAL 漏洞"
else
  echo "   ❌ 存在 CRITICAL 漏洞，阻断部署"
  exit 1
fi

echo "=== 5. 部署 ==="
docker stop myapp 2>/dev/null || true
docker run -d --name myapp --network mynet "$IMAGE"
echo "✅ 部署完成: $IMAGE"
```

---

## 第七步：LLM 生成供应链策略文档

让本地 LLM 根据实际扫描结果，自动生成可执行的供应链策略（写入 Git，纳入版本控制）：

```python
def generate_policy_llm(triage_result: str, image_info: dict) -> str:
    """根据 LLM 研判结果生成供应链策略文档"""
    prompt = f"""根据以下 CVE 研判结果，为 {image_info['name']} 生成供应链策略文档。

研判结果：
{triage_result}

请生成 Markdown 格式的策略文档，包含：
1. 基础镜像白名单（允许的 tag 范围）
2. 依赖锁定策略（lockfile 必须使用哪个版本）
3. 签名验证要求（哪些镜像必须验证，哪些可以豁免）
4. 紧急响应流程（CRITICAL CVE 出现后 30 分钟内的操作步骤）
5. 季度复审清单

输出纯 Markdown，无额外说明。
"""
    resp = requests.post(
        f"{OLLAMA}/api/generate",
        json={"model": MODEL, "prompt": prompt, "stream": False,
              "options": {"temperature": 0.1}},
        timeout=180,
    )
    return resp.json()["response"]
```

---

## 成本与资源

| 组件 | 额外内存 | 额外磁盘 | 说明 |
|------|---------|---------|------|
| Ollama + Qwen2.5-7B | ~5 GB | ~4 GB | 已有则无需额外 |
| Trivy + Syft + cosign | 0 | ~100 MB | 纯二进制 |
| Sigstore 公钥缓存 | 0 | ~50 MB | 本地签名，无需 fulcio |

**总增量：无额外常驻内存（Ollama 按需启动），磁盘 +150 MB。**

---

## 总结

容器镜像供应链完整性不是一道选择题，而是一道必答题。这套方案的核心价值：

| 环节 | 传统做法 | 本文方案 |
|------|---------|---------|
| SBOM | 手动导出，格式不统一 | Syft 自动化，CycloneDX 标准 |
| 签名 | 跳过或手动 | cosign 自动，部署前强制验证 |
| 漏洞研判 | 看 Trivy 报告，人工判断 | LLM 结合业务上下文智能分级 |
| 修复建议 | 文档里写"建议升级" | LLM 给出具体 tag / apt 命令 |
| 策略文档 | 写在 Confluence 里吃灰 | LLM 生成，纳入 Git 版本控制 |

**下一步可以探索：**
- 将 LLM 研判结果接入 Gitea/GitHub Issue，自动创建修复 PR
- 用 SLSA provenance 替代/补充 cosign 签名
- 对多节点 VPS 集群统一供应链策略（参考 `ai-vps-fleet-intelligence-cross-node-correlation`）

> ⚠️ 本文所有工具均在本地运行，LLM 推理不经过公网，敏感镜像元数据不出 VPS。
