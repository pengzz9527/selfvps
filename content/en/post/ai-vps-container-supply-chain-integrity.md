---
title: "AI-Powered Container Supply Chain Integrity: LLM-Driven SBOM Signing & Provenance"
description: "Building a container image is only the first step — true security covers the entire supply chain. This guide builds a complete container image supply chain integrity system on VPS using local LLM (Ollama + Qwen2.5), cosign/Sigstore signing, Trivy scanning, SBOM generation, and LLM-driven intelligent CVE triage with auto-remediation. All inference stays on your VPS."
date: 2026-10-13T20:00:00+08:00
lastmod: 2026-10-13T20:00:00+08:00
slug: "ai-vps-container-supply-chain-integrity"
tags: ["AI", "Container Security", "Supply Chain", "SBOM", "cosign", "Sigstore", "Trivy", "Ollama", "VPS Ops", "Automation"]
categories: ["AI Security"]
draft: false
image: /images/posts/ai-vps-container-supply-chain-integrity/featured.png
aliases: [/en/post/ai-vps-container-supply-chain-integrity/]
---

## Introduction: Building an Image ≠ Supply Chain Security

Most teams' security awareness stops at `docker build`. But real supply chain attacks happen *after* the build:

- Malicious layers injected at the build node
- Typosquatting or impersonation of third-party images
- Upstream base image swapped for a malicious fork
- A `docker pull` fetching a tampered image from a compromised registry
- No signature verification — *any* image can be run

**Core problem: you cannot prove "this image is the one I built" or "it hasn't been tampered with."**

This guide builds a complete **container image supply chain integrity system** on a VPS:

```
Build → SBOM → cosign Sign → Trivy Scan → LLM Risk Triage
       ↕                  ↕
   Sigstore Keys    Auto-Remediation Advice
       ↕
   Deploy: Verify Signature + Provenance
```

All LLM inference is local (Ollama + Qwen2.5). No data leaves your VPS.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  VPS Container Image Supply Chain Integrity System       │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌──────────┐   ┌──────────┐   ┌───────────────────┐   │
│  │ CI/CD    │──▶│ SBOM     │──▶│ Trivy Scan        │   │
│  │ Build    │   │ (Syft)   │   │ (CVE + Severity)  │   │
│  └──────────┘   └──────────┘   └────────┬──────────┘   │
│       │                                  │              │
│       ▼                                  ▼              │
│  ┌──────────┐   ┌──────────┐   ┌───────────────────┐   │
│  │ cosign   │──▶│ Sigstore │   │ Ollama + Qwen2.5  │   │
│  │ Sign     │   │ Public   │   │ Risk Triage +     │   │
│  └──────────┘   │ Key Reg. │   │ Remediation       │   │
│                 └──────────┘   └────────┬──────────┘   │
│       ▲                                  │              │
│       │                                  ▼              │
│  ┌──────────┐                    ┌──────────────────┐   │
│  │ Deploy   │◀───────────────────│ Telegram Alerts   │   │
│  │ Verify   │  Block unsigned / │ + Remediation     │   │
│  └──────────┘  tampered images   │ Report Push       │   │
│                                  └──────────────────┘   │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## Step 1: Install the Toolchain

One-time setup on a VPS (Ubuntu 24.04):

```bash
# Trivy — image scanning
curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh | sh -s -- -b /usr/local/bin

# Syft — SBOM generation
curl -sfL https://raw.githubusercontent.com/anchore/syft/main/install.sh | sh -s -- -b /usr/local/bin

# cosign — image signing / verification
curl -sfL https://github.com/sigstore/cosign/releases/download/v2.4.0/cosign-linux-amd64 \
  -o /usr/local/bin/cosign && chmod +x /usr/local/bin/cosign

# Verify
trivy --version && syft --version && cosign version
```

> **Note:** cosign defaults to Sigstore's public key service (fulcio.sigs.k8s.io). On a VPS you can configure offline key pairs to avoid external dependencies:
>
> ```bash
> mkdir -p ~/.cosign && chmod 700 ~/.cosign
> cosign generate key-pair --key gen-key:password --output-key \
>   /root/.cosign/cosign.key --output-public-key /root/.cosign/cosign.pub
> ```

---

## Step 2: Generate an SBOM (Software Bill of Materials)

An SBOM is the "ingredient list" for your image — it records every dependency at its exact version. Without it, you cannot answer "what's actually in this image."

```bash
# Generate SBOM for a built image (CycloneDX format, machine-readable)
syft pkg:registry --output cyclonedx-json:myapp:1.2.3 --file sbom.cdx.json

# Or generate from Dockerfile context in CI (no image pull required)
syft . --output cyclonedx-json:sbom.cdx.json
```

**Why CycloneDX over SPDX?**

| Dimension | CycloneDX | SPDX |
|-----------|-----------|------|
| Ecosystem | Native in GitHub/Trivy/Syft | Linux Foundation |
| Vulnerability data | Consumed directly by Trivy | Requires conversion |
| Supply chain integrity | Recommended by Sigstore | Increasingly supported |
| This guide | ✅ Recommended | Backup |

---

## Step 3: cosign Signing + Sigstore Provenance

Signing proves "this image was indeed produced by the build party." Using an offline key pair (avoids fulcio dependency):

```bash
export COSIGN_KEY=/root/.cosign/cosign.key
export COSIGN_PASSWORD="your...n
# Sign the image (pushed to your private registry)
cosign sign --registry-allowlist my.registry.local \
  my.registry.local/myapp:1.2.3

# Also sign the SBOM (proves SBOM ↔ image binding)
cosign sign --sbom sbom.cdx.json \
  my.registry.local/myapp:1.2.3

# Verify (run at deploy time)
cosign verify --key /root/.cosign/cosign.pub \
  my.registry.local/myapp:1.2.3
```

**Mandatory verification at deployment (in your K8s or Docker startup script):**

```bash
#!/usr/bin/env bash
# secure-pull.sh — only pull signed and verified images
set -euo pipefail

IMAGE="${1:?usage: secure-pull.sh <image>}"

# 1. Pull
docker pull "$IMAGE"

# 2. Verify signature
cosign verify --key /root/.cosign/cosign.pub "$IMAGE" 2>/dev/null
if [[ $? -eq 0 ]]; then
  echo "✅ Signature valid: $IMAGE"
else
  echo "❌ Signature invalid or missing: $IMAGE" >&2
  exit 1
fi

# 3. Verify SBOM integrity (SBOM hash matches image)
cosign verify --sbom "$IMAGE" 2>/dev/null
echo "✅ SBOM integrity confirmed"
```

---

## Step 4: Trivy Scan + LLM Risk Triage

This is the highest-value step. Trivy tells you "there are 47 CVEs" — but **which ones actually affect your workload? Which can wait? Which need immediate attention?** That's where LLMs shine.

### 4.1 Scan and Export JSON

```bash
trivy image --format json --output trivy-report.json \
  --severity CRITICAL,HIGH \
  my.registry.local/myapp:1.2.3
```

### 4.2 LLM Risk Triage Script

```python
#!/usr/bin/env python3
"""
LLM-driven CVE risk triage
Input: Trivy JSON report + SBOM + business context
Output: Prioritized remediation plan with reasoning
Runs locally (Ollama + Qwen2.5), data stays on VPS
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

    # Top 20 to avoid token explosion
    top_vulns = (critical + high)[:20]
    vuln_lines = []
    for v in top_vulns:
        pkg = v.get("PkgName", "unknown")
        ver = v.get("InstalledVersion", "?")
        fixed = v.get("FixedVersion", "none")
        cve = v.get("VulnerabilityID", "N/A")
        cvss = v.get("CVSS", [{}])[0].get("V3Score", "N/A") if "CVSS" in v else "N/A"
        vuln_lines.append(f"  {cve} [{v.get('Severity')}] {pkg}@{ver} → fix {fixed} (CVSS {cvss})")

    prompt = f"""You are a VPS container security expert. Below are Trivy scan results (top {len(top_vulns)} HIGH/CRITICAL vulnerabilities):

{chr(10).join(vuln_lines)}

Business context: {context}

SBOM summary (first 5 direct dependencies):
{json.dumps(list(sbom.get('components', {}).values())[:5] if 'components' in sbom else {}, indent=2)[:800]}

Output:
1. CVEs requiring **immediate fix** (with reasoning: network-exploitable? at entry point?)
2. CVEs that can **wait until next iteration** (with reasoning)
3. Specific remediation steps for each (e.g. apt-get upgrade / base image tag bump)
4. If a base image security update is available, recommend the new tag

Format: Markdown, in English.
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
    p.add_argument("report", help="Trivy JSON report path")
    p.add_argument("sbom",   help="Syft CycloneDX JSON path")
    p.add_argument("--context", default="Web app, exposed on 80/443", help="Business context")
    args = p.parse_args()

    result = llm_judge(load_scan_report(args.report),
                       json.load(open(args.sbom)),
                       args.context)
    print(result)
```

**Example output:**

```
1. Immediate fixes
   - CVE-2025-XXXXX (CRITICAL, CVSS 9.8) pkg:node@18.x → 18.20.4
     Reasoning: Affects HTTP parsing module; attacker can trigger RCE via
     malformed HTTP request; port 443 is externally exposed → network
     exploitable.
     Action: bump base image FROM node:18 → node:18.20.4

2. Can defer
   - CVE-2025-YYYYY (HIGH, CVSS 7.5) pkg:lodash@4.17.20
     Reasoning: Prototype pollution in lodash, but current codebase does not
     use lodash.merge — actual attack surface is minimal. Schedule for next
     iteration; bump to 4.17.21.
```

---

## Step 5: Automated Remediation Pipeline

Convert LLM recommendations into executable actions, triggered in CI:

```yaml
# .github/workflows/supply-chain.yaml
on:
  push:
    paths:
      - "Dockerfile"
      - ".github/workflows/supply-chain.yaml"
  schedule:
    - cron: "0 2 * * 1"   # Weekly, Monday 02:00 UTC

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
        run: |
          python3 llm-cve-judge.py \
            --report trivy-report.json \
            --sbom sbom.cdx.json \
            --context "Node.js Web app, Express, exposed on 443" \
            > llm-triage.md

      - name: Sign image
        env:
          COSIGN_KEY: ${{ secrets.COSIGN_KEY }}
          COSIGN_PASSWORD: ${{ secrets.COSIGN_PASSWORD }}
        run: |
          docker push my.registry.local/myapp:${{ github.sha }}
          cosign sign my.registry.local/myapp:${{ github.sha }}
          cosign sign --sbom sbom.cdx.json my.registry.local/myapp:${{ github.sha }}

      - name: Upload SBOM artifact
        uses: actions/upload-artifact@v4
        with:
          name: sbom-${{ github.sha }}
          path: sbom.cdx.json

      - name: Upload LLM triage report
        uses: actions/upload-artifact@v4
        with:
          name: llm-triage-${{ github.sha }}
          path: llm-triage.md
```

---

## Step 6: Deployment-Side Verification (On VPS)

Embed signature verification in your VPS deployment script to ensure only fully-supply-chained images go live:

```bash
#!/usr/bin/env bash
# deploy-verified.sh — verify full supply chain before VPS deployment
set -euo pipefail

IMAGE="${1:?usage: deploy-verified.sh <image:tag>}"
PUB_KEY="/root/.cosign/cosign.pub"
SBOM_PATH="/var/lib/supply-chain/sbom-${IMAGE##*:}.cdx.json"

echo "=== 1. Verify cosign signature ==="
cosign verify --key "$PUB_KEY" "$IMAGE"
echo "   ✅ Signature valid"

echo "=== 2. Verify SBOM ↔ image binding ==="
cosign verify --sbom "$IMAGE"
echo "   ✅ SBOM integrity confirmed"

echo "=== 3. Check SBOM against local allowlist ==="
if [[ -f "$SBOM_PATH" ]]; then
  echo "   ✅ SBOM cached locally"
else
  echo "   ⚠️  First deploy — fetching and caching SBOM..."
  cosign download sbom "$IMAGE" -o "$SBOM_PATH"
fi

echo "=== 4. Final Trivy scan (CRITICAL only) ==="
trivy image --severity CRITICAL "$IMAGE"
if [[ $? -eq 0 ]]; then
  echo "   ✅ No CRITICAL vulnerabilities"
else
  echo "   ❌ CRITICAL vulnerability found — deployment blocked"
  exit 1
fi

echo "=== 5. Deploy ==="
docker stop myapp 2>/dev/null || true
docker run -d --name myapp --network mynet "$IMAGE"
echo "✅ Deployed: $IMAGE"
```

---

## Step 7: LLM-Generated Supply Chain Policy Docs

Let the local LLM generate an executable supply chain policy document based on actual scan results, committed to Git for version control:

```python
def generate_policy_llm(triage_result: str, image_info: dict) -> str:
    """Generate supply chain policy document from LLM triage results"""
    prompt = f"""Based on the following CVE triage results, generate a supply chain policy
document for {image_info['name']}.

Triage results:
{triage_result}

Generate a Markdown policy document containing:
1. Base image allowlist (permitted tag ranges)
2. Dependency lock strategy (which lockfile versions are pinned)
3. Signature verification requirements (which images must be verified, any exemptions)
4. Emergency response procedure (steps to complete within 30 minutes of a CRITICAL CVE)
5. Quarterly review checklist

Output pure Markdown, no extra commentary.
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

## Cost & Resource Impact

| Component | Extra RAM | Extra Disk | Notes |
|-----------|----------|------------|-------|
| Ollama + Qwen2.5-7B | ~5 GB | ~4 GB | Skip if already running |
| Trivy + Syft + cosign | 0 | ~100 MB | Static binaries |
| Sigstore key cache | 0 | ~50 MB | Offline signing, no fulcio |

**Total incremental: no extra resident RAM (Ollama starts on demand), +150 MB disk.**

---

## Summary

Container image supply chain integrity is not optional. The core value of this system:

| Stage | Traditional Approach | This Guide |
|-------|---------------------|------------|
| SBOM | Manual export, inconsistent formats | Syft automated, CycloneDX standard |
| Signing | Skipped or manual | cosign automated, enforced at deploy |
| CVE triage | Manual review of Trivy report | LLM contextual risk prioritization |
| Remediation | "Upgrade recommended" in docs | LLM outputs specific tags / apt commands |
| Policy docs | Living in Confluence, stale | LLM-generated, Git-versioned |

**Next steps to explore:**
- Wire LLM triage results into Gitea/GitHub Issues with auto-created fix PRs
- Use SLSA provenance as a complement to cosign signing
- Extend to multi-node VPS fleets with unified supply chain policy (see `ai-vps-fleet-intelligence-cross-node-correlation`)

> ⚠️ All tools run locally. LLM inference never leaves your VPS. Sensitive image metadata is never transmitted externally.
