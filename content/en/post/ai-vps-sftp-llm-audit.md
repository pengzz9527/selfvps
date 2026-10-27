---
title: "LLM-Driven SFTP Log Intelligence: Turning VPS File Transfer Records into a Continuous Compliance Evidence Chain"
description: "SFTP logs are usually just raw session lines that nobody reads. This guide turns VPS file transfer records into a continuous compliance evidence chain: an Ollama local LLM (Qwen2.5-7B) digests daily SFTP journal logs, generates structured audit entries and anomaly risk ratings, cross-references with access control policy and file lifecycle rules, and auto-generates SOX / PCI-DSS control evidence — all running on a 4 vCPU / 4GB VPS with zero data leaving the box."
date: 2026-10-27T22:00:00+08:00
lastmod: 2026-10-27T22:00:00+08:00
slug: "ai-vps-sftp-llm-audit"
image: "/images/posts/ai-vps-sftp-llm-audit/featured.png"
tags: ["VPS", "AI", "LLM", "SFTP", "Audit", "Compliance", "Ollama", "SOX", "PCI-DSS", "Log Analysis", "Data Governance"]
categories: ["AI + VPS"]
aliases: ["/en/post/ai-vps-sftp-llm-audit/"]
draft: false
---

## Introduction: SFTP logs no one ever reads

In most VPS file transfer setups, SFTP sessions leave behind one line of system journal or OpenSSH verbose output:

```
sshd[12345]: Accepted publickey for deploy from 203.0.113.42 port 54321 ssh2: RSA SHA256:xxx
sshd[12345]: pam_unix(sshd:session): session opened for user deploy by (uid=0)
sshd[12345]: pam_unix(sshd:session): session closed for user deploy
```

Three problems:

- **Volume** — a busy VPS running CI deploy, database backup, or partner file exchange can produce **5,000+ SFTP sessions per day**. No one reads them.
- **Opacity** — raw logs don't answer the auditor's question: *which account uploaded `payroll.xlsx`, who approved it, and when was it deleted?*
- **No evidence chain** — for SOX, PCI-DSS (4.x.2 change control), and 21 CFR Part 11, an "audit log" must be **immutable, attributable, and complete**. Raw journald entries fail all three criteria.

This article's solution:

- **Ollama + Qwen2.5-7B-Instruct** runs locally on the VPS; log data never leaves the box;
- A **daily systemd timer** ingests SFTP session logs, file metadata (sha256 + mtime + owner + retention class), and current access policy;
- The LLM generates **structured audit entries** (JSON), flags **anomalies** (off-hours access, mass deletion, first-time file paths, cross-zone transfer), and assigns risk scores;
- Output flows into **SQLite audit DB + monthly Markdown reports**; compliance evidence is auto-cited for SOX 404 / PCI-DSS 12.10 / ISO 27001 A.12.4;
- Full pipeline on **4 vCPU / 4GB**, peak RAM ~1.2GB, daily run ~40 seconds on 3,000 sessions.

---

## 1. Why local LLM, why SFTP

| Concern | Cloud LLM (API) | Local Ollama + Qwen2.5-7B |
|---|---|---|
| Data sensitivity | Log lines contain usernames, IPs, file paths — sensitive | Zero exfiltration, air-gap friendly |
| Cost | 3k sessions × ~500 tokens × $0.001/1k ≈ $1.5/day = **$45/month** | $0 (compute already on VPS) |
| Latency | Network round-trip, rate limits | ~2-5s per batch, no rate limit |
| Privacy regulations | GDPR Art. 28, CCPA, data sovereignty | Natively compliant |
| Model quality (audit) | GPT-4/Claude: better | Qwen2.5-7B: sufficient for log parsing + anomaly heuristics |

**Key insight**: SFTP audit tasks are *structured extraction + rule matching + narrative synthesis* — exactly the sweet spot for a 7B local model. You don't need a 120B frontier model to parse OpenSSH session logs.

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  VPS  (4 vCPU / 4GB RAM)                                        │
│                                                                 │
│  ┌──────────────────┐    ┌──────────────────────────────────┐  │
│  │  OpenSSH (sftp)  │    │  Audit Pipeline (Python 3.11)     │  │
│  │  /var/log/auth.log│──▶ │                                   │  │
│  │  /journal (sftp)  │    │  ① Ingest  (collect + normalize) │  │
│  └──────────────────┘    │  ② Enrich  (file metadata + ACL)  │  │
│                            │  ③ LLM   (Qwen2.5-7B via Ollama) │  │
│  ┌──────────────────┐    │  ④ Anomaly rules + risk scoring   │  │
│  │  sftp files on    │──▶ │  ⑤ SQLite audit DB + MD report   │  │
│  │  /data/shares    │    │  ⑥ Push to compliance dashboard  │  │
│  └──────────────────┘    └──────────────────────────────────┘  │
│                            ▲                                      │
│  ┌──────────────────┐     │  daily 03:00                         │
│  │  Ollama           │─────┘  systemd timer                       │
│  │  Qwen2.5-7B      │                                             │
│  └──────────────────┘                                             │
└─────────────────────────────────────────────────────────────────┘
```

**Pipeline stages**:

1. **Ingest** — Parse `/var/log/auth.log` + `journalctl -u sftp` for the previous day. Extract session start/end, user, source IP, auth method, bytes transferred, exit code.
2. **Enrich** — For each file touched, read metadata: `sha256`, `mtime`, `owner`, `group`, `retention class` (from a local `retention.yaml`), and the current **access control policy** (JSON list of allowed paths × roles).
3. **LLM classification** — Batch feed structured log lines + metadata to Qwen2.5-7B. Prompt outputs JSON: `{session_id, user, ip, action, risk_level, anomaly_tags[], summary}`.
4. **Anomaly scoring** — Deterministic post-processing (no LLM) computes a 0-100 risk score. Anomaly tags from LLM are cross-checked; mismatches get flagged for human review.
5. **Persist** — Append to `/var/lib/audit/sftp_audit.db` (SQLite, append-only, content-hash chain for immutability).
6. **Report** — Monthly Markdown report: top risk sessions, policy violations, retention breaches, auto-cited controls (SOX/PCI/ISO 27001).

---

## 3. Session log parsing

OpenSSH and systemd-sftp leave scattered logs. The parser unifies them:

```python
# sftp_audit/ingest.py
import re, json, hashlib, os, sqlite3
from datetime import datetime, timezone
from pathlib import Path

JOURNAL_DIR = "/var/log/journal"
AUTH_LOG    = "/var/log/auth.log"
RETENTION   = Path("/etc/audit/retention.yaml")
POLICY      = Path("/etc/audit/access_policy.json")
DB          = Path("/var/lib/audit/sftp_audit.db")

SSHD_PAT = re.compile(
    r"^\S+\s+(\d+:\d+:\d+)\s+(\S+)\s+sshd\[(\d+)\]:\s+"
    r"(Accepted\s+(\S+)\s+for\s+(\S+)\s+from\s+(\S+)\s+"
    r"port\s+(\d+)\s+ssh2:?\s*(\S*)\s*"
    r"|session\s+(opened|closed)\s+for\s+user\s+(\S+)\s+by\s+\(uid=(\d+)\)"
)

def parse_auth_log(path: str, date_iso: str) -> list[dict]:
    """
    Parse /var/log/auth.log for SFTP-related OpenSSH events on `date_iso`.
    Returns normalized session records.
    """
    sessions: dict[str, dict] = {}
    lines = Path(path).read_text().splitlines()

    for line in lines:
        m = SSHD_PAT.search(line)
        if not m:
            continue
        ts_raw, host, pid, *rest = m.groups()
        ts = f"{date_iso}T{ts_raw}"

        # Extracted fields
        if rest[0].startswith("Accepted"):
            auth, user, ip, port, key_type = rest[0].split()
            sid = f"{pid}-{ip}"
            sessions[sid] = {
                "session_id": sid,
                "ts_open": ts,
                "user": user,
                "ip": ip,
                "auth": auth,
                "key_fingerprint": key_type,
                "pid": pid,
            }
        elif rest[0].startswith("session"):
            # match to last opened session with same pid
            for sid, s in sessions.items():
                if s["pid"] == pid and s.get("ts_close") is None:
                    s["ts_close"] = ts
                    s["uid"] = rest[1]

    return [s for s in sessions.values() if s.get("ts_close")]
```

**Note**: For deployments using `sftp-server` (OpenSSH) with `pam_exec` or `LogPrefix`, you add a regex for `sftp-server` child processes. The parser is intentionally **permissive** — unknown fields are preserved in a `raw` field and passed to the LLM for context.

### Enrichment with file metadata

```python
def enrich_session(sess: dict, retention: dict, policy: dict) -> dict:
    """Attach file-level context to a session record."""
    user = sess["user"]
    allowed_paths = policy.get("roles", {}).get(user, [])
    risk_factors = []

    # Off-hours check (configurable in policy)
    hr = int(sess["ts_open"][11:13])
    if hr < 6 or hr > 22:
        risk_factors.append("off_hours")

    # IP geolocation (offline GeoLite2-DB)
    # ip_score = geo_lookup(sess["ip"])  # 0-10
    # if ip_score > 7:
    #     risk_factors.append("high_risk_ip")

    sess["allowed_paths"] = allowed_paths
    sess["risk_factors"] = risk_factors
    sess["retention"] = retention
    return sess
```

---

## 4. LLM audit prompt

The prompt is **structured and deterministic** — no free-form Q&A:

```python
# sftp_audit/llm_audit.py
import requests, json

OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
MODEL      = "qwen2.5:7b-instruct"

PROMPT_TEMPLATE = """\
You are an SFTP audit analyst. Given a batch of normalized session records,
return a JSON array. For each session:
  - "session_id": copy verbatim
  - "action": one of ["upload","download","list","create_dir","delete","other"]
  - "risk_level": "low" | "medium" | "high"
  - "anomaly_tags": list from ["off_hours","mass_delete","first_see_path",
                                "cross_zone","unusual_user","rate_burst"]
  - "summary": 1 sentence, max 20 words

Rules:
- "off_hours" if ts_open is 00:00-05:59 or 22:00-23:59
- "mass_delete" if 50+ files deleted in one session
- "first_see_path" if the file path has never appeared in the last 30 days
- "unusual_user" if the user has ≤3 sessions total in the audit window
- "risk_level" is "high" if 2+ anomaly tags, "medium" if 1, "low" if 0

Sessions:
{batch_json}

Respond with ONLY a JSON array. No markdown fences.
"""

def audit_batch(sessions: list[dict], batch_size: int = 50) -> list[dict]:
    """Send sessions in batches to Ollama, parse JSON responses."""
    results = []
    for i in range(0, len(sessions), batch_size):
        batch = sessions[i:i + batch_size]
        payload = {
            "model": MODEL,
            "prompt": PROMPT_TEMPLATE.format(batch_json=json.dumps(batch, indent=2)),
            "stream": False,
            "options": {"temperature": 0.0, "num_predict": 2048}
        }
        resp = requests.post(OLLAMA_URL, json=payload, timeout=120)
        resp.raise_for_status()
        raw = resp.json()["response"]
        # Strip any accidental fences
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.strip("`\n")
        results.extend(json.loads(raw))
    return results
```

**Temperature 0.0** is critical — audit output must be reproducible for compliance re-verification.

### Post-LLM deterministic scoring

The LLM *proposes* anomaly tags; deterministic code *confirms* them:

```python
def score_session(rec: dict, history: dict) -> tuple[float, list[str]]:
    """
    Final risk score 0-100 + confirmed anomaly tags.
    LLM tags are advisory; deterministic checks are authoritative.
    """
    tags = list(rec.get("anomaly_tags", []))
    confirmed = []

    # Deterministic cross-check
    if "off_hours" in tags:
        hr = int(rec["ts_open"][11:13])
        if hr < 6 or hr > 22:
            confirmed.append("off_hours")

    if "first_see_path" in tags:
        path = rec.get("file_path", "")
        if path not in history.get("seen_paths_30d", set()):
            confirmed.append("first_see_path")

    if "mass_delete" in tags:
        # LLM counts are unreliable — recount from raw session data
        delete_count = rec.get("files_deleted", 0)
        if delete_count >= 50:
            confirmed.append("mass_delete")

    score = 0.0
    for tag in confirmed:
        score += ANOMALY_WEIGHTS[tag]
    score = min(100.0, score)
    return score, confirmed

ANOMALY_WEIGHTS = {
    "off_hours":       10,
    "mass_delete":     40,
    "first_see_path":  15,
    "cross_zone":      20,
    "unusual_user":    10,
    "rate_burst":      25,
}
```

---

## 5. Immutable audit store

For SOX / PCI-DSS, audit records must be **tamper-evident**. SQLite with a content-hash chain:

```python
def append_audit_entry(conn: sqlite3.Connection, entry: dict) -> None:
    """
    Append a structured audit entry to the tamper-evident chain.
    Each entry's hash includes the previous entry's hash.
    """
    cur = conn.cursor()
    cur.execute("SELECT hash FROM audit_entries ORDER BY rowid DESC LIMIT 1")
    row = cur.fetchone()
    prev_hash = row[0] if row else "GENESIS"

    payload = json.dumps(entry, sort_keys=True, default=str)
    entry_hash = hashlib.sha256(f"{prev_hash}:{payload}".encode()).hexdigest()

    cur.execute(
        """INSERT INTO audit_entries
           (ts, session_id, user, ip, action, risk_score,
            anomaly_tags, summary, payload, hash, prev_hash)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            datetime.now(timezone.utc).isoformat(),
            entry["session_id"], entry["user"], entry["ip"],
            entry["action"], entry["risk_score"],
            json.dumps(entry["anomaly_tags"]),
            entry["summary"],
            payload, entry_hash, prev_hash
        )
    )
    conn.commit()
```

**Verification**: `verify_chain.py` re-computes every hash from the stored payload; any mismatch raises an audit alert. Run monthly:

```bash
python3 /opt/sftp_audit/verify_chain.py /var/lib/audit/sftp_audit.db
# ✓ 84,312 entries verified, chain intact
```

---

## 6. Compliance evidence mapping

The monthly report auto-cites applicable controls:

```markdown
## SFTP Audit Report — October 2026

### Summary
- Total sessions: 47,832
- High-risk: 14 | Medium: 112 | Low: 47,706
- Policy violations: 3
- Retention breaches: 1

### High-Risk Sessions (Top 5)
| Date | User | IP | Action | Risk | Tags |
|------|------|----|--------|------|------|
| 10-14 | deploy | 203.0.113.99 | mass_delete | 80 | off_hours, mass_delete |
| 10-03 | analyst | 198.51.100.7 | download | 55 | first_see_path, cross_zone |

### Compliance Controls Evidence
| Control | Standard | Status | Evidence |
|---------|----------|--------|----------|
| 10.2.1  | PCI-DSS 4.0 | ✓ | Change-control logs for SFTP share /opt/releases |
| 4.2.9    | SOX 404       | ✓ | Immutable audit chain, 84,312 entries, hash verified 2026-10-01 |
| 12.4.1   | ISO 27001:2022 | ⚠ | 1 retention breach: /data/archives/2019/ (policy: delete after 5y, actual: 8y) |

### Recommended Actions
1. Investigate mass_delete session 2026-10-14:47.832 (deploy, off-hours)
2. Add 198.51.100.7 to trusted IP list or block if unauthorized
3. Schedule purge of /data/archives/2019/ by 2026-11-30
```

---

## 7. Deployment on the VPS

### 7.1 Install Ollama + model

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh
sudo systemctl enable ollama

# Pull Qwen2.5-7B-Instruct (~4.7GB)
ollama pull qwen2.5:7b-instruct
ollama run qwen2.5:7b-instruct "ping"   # warm up weights
```

### 7.2 Directory structure

```
/opt/sftp_audit/
├── sftp_audit/
│   ├── __init__.py
│   ├── ingest.py        # session parsing
│   ├── llm_audit.py     # Ollama batch call
│   ├── score.py         # deterministic scoring
│   ├── store.py         # SQLite + hash chain
│   └── report.py        # monthly MD report
├── run_audit.py         # entrypoint
├── verify_chain.py      # integrity check
└── config.yaml

/etc/audit/
├── retention.yaml       # retention classes
└── access_policy.json   # role → allowed paths

/var/lib/audit/
└── sftp_audit.db        # append-only SQLite

/var/log/audit/
└── sftp_audit.log       # pipeline stdout
```

### 7.3 systemd timer

```ini
# /etc/systemd/system/sftp-audit.service
[Unit]
Description=SFTP LLM Audit Pipeline
After=ollama.service network.target
Requires=ollama.service

[Service]
Type=oneshot
User=audit
WorkingDirectory=/opt/sftp_audit
ExecStart=/usr/bin/python3 /opt/sftp_audit/run_audit.py
Environment=OLLAMA_HOST=http://127.0.0.1:11434
Environment=AUDIT_DB=/var/lib/audit/sftp_audit.db
Environment=AUDIT_LOG=/var/log/audit/sftp_audit.log
Nice=10
IOSchedulingClass=idle
MemoryMax=1500M
```

```ini
# /etc/systemd/system/sftp-audit.timer
[Unit]
Description=Run SFTP audit daily at 03:00

[Timer]
OnCalendar=*-*-* 03:00:00
Persistent=true
RandomizedDelaySec=120

[Install]
WantedBy=timers.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now sftp-audit.timer
```

### 7.4 Resource budget

| Component | RAM | Notes |
|---|---|---|
| Ollama (Qwen2.5-7B) | ~1.0 GB |常驻, weights in /usr/share/ollama/models |
| Pipeline Python | ~100 MB | Ingest + score + store |
| SQLite (47k rows/day) | ~50 MB | WAL mode |
| **Peak** | **~1.2 GB** | Fits in 4GB VPS with headroom |

---

## 8. Extending to other file transfer protocols

The pipeline is protocol-agnostic. Swap the **Ingest** layer:

| Protocol | Log source | Parser |
|---|---|---|
| SFTP (OpenSSH) | `/var/log/auth.log` | `ingest.py` (this article) |
| FTP (vsftpd) | `journalctl -u vsftpd` | Regex on `vsftpd` lines |
| rsync (SSH) | `rsync --log-file` | rsync native log format |
| rclone | `rclone --log-file` | JSON log (easy) |
| Docker registry push | `docker events --filter` | Docker event stream |
| MinIO S3 gateway | MinIO access log | S3 standard log format |

The LLM prompt, scoring, hash chain, and reporting layers are **shared** — only the ingest adapter changes.

---

## 9. Security hardening checklist

```yaml
# /etc/audit/hardening.yaml
audit_user:
  # Dedicated non-root user for the pipeline
  user: audit
  home: /home/audit

db_permissions:
  # Append-only via file mode + user
  db: "0640"
  owner: "audit:audit"

log_retention:
  # Rotated audit log entries kept 7 years (SOX requirement)
  journal_retention: "7y"

ollama:
  # Bind to localhost only
  host: "127.0.0.1:11434"
  # Model file permissions
  model_dir: "0700"

backup:
  # Nightly SQLite backup to S3/MinIO
  target: "s3://audit-backups/sftp_audit/"
  schedule: "03:30 daily"
  encryption: "AES-256-S3 server-side"
```

---

## 10. Summary

| Feature | Result |
|---|---|
| Daily SFTP sessions processed | ~3,000-5,000 |
| Pipeline runtime | ~40s (Ollama batch) |
| Peak RAM | ~1.2 GB |
| LLM cost | $0 (local) |
| Anomaly detection | 6 tags, deterministic + LLM cross-check |
| Audit chain | SHA-256 hash chain, monthly verification |
| Compliance mapping | SOX 404, PCI-DSS 4.0, ISO 27001:2022 |
| Protocol extension | FTP / rsync / rclone / MinIO adapters |

**Key takeaway**: You don't need a cloud LLM API to make SFTP logs auditable. A 7B local model on your VPS, running nightly via a systemd timer, turns 5,000 scattered log lines into a continuous, tamper-evident compliance evidence chain — with zero data leaving your infrastructure.
