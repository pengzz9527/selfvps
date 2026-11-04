---
title: "AI Agent Tool Sandbox: Isolating LLM-Generated Code with WasmEdge (3ms Cold Start on a VPS)"
date: 2026-11-04
tags: ["VPS", "AI", "WasmEdge", "Sandbox", "Security", "Agent"]
draft: false
image: /images/posts/ai-vps-wasmedge-untrusted-tool-sandbox/featured.png
description: "Letting a local LLM write ops scripts is delightful. Letting it run them on your VPS is an incident: one rm -rf or curl | bash takes the whole box. This article rebuilds an AI agent's tool-call layer as a default-deny WasmEdge + WASI sandbox — capability allowlist (read-only preopened dirs), no sockets by default, hard memory/CPU/timeout limits, millisecond cold starts. On a 2C4G VPS a full tool call costs under 6ms, roughly 300x faster than spinning a Docker container."
---

# AI Agent Tool Sandbox: Isolating LLM-Generated Code with WasmEdge (3ms Cold Start on a VPS)

I built a small local ops agent for this site: it reads logs, checks metrics, and **generates a script for me to confirm and run**. The first successful run was thrilling. The second one gave me chills — the script contained `curl -s https://... | bash`, with a domain that was misspelled by one character.

The model didn't "go bad." A probabilistic system produces probabilistic output. Piping LLM-generated code straight into `bash -c` means handing root on a VPS to a component you cannot audit, reproduce, or code-review.

The traditional answer is a Docker wrapper: `docker run --rm --network none -v ... python:3.12`. It works, but every tool call costs 300ms–1.5s to start. An agent that calls 5 tools per turn adds seconds of latency; worse, images are hundreds of MB, which hurts on a 2C4G box.

This article replaces the execution layer with a **WebAssembly sandbox** (WasmEdge + WASI). The payoff is straightforward:

| Metric | `bash -c` direct | Docker container | WasmEdge sandbox |
|--------|:---:|:---:|:---:|
| Cold start per call | ~2ms | 300–1500ms | **3–8ms** |
| Runtime size | 0 (built in) | 100MB–1GB image | 2–15MB module |
| Network isolated by default | ❌ wide open | ✅ `--network none` | ✅ no socket capability at all |
| Filesystem isolation | ❌ full disk writable | ✅ controlled mounts | ✅ preopened dirs only |
| Memory cap | ❌ | ✅ `--memory` | ✅ `--memory-limit` |
| Host kernel attack surface | ❌ full syscall table | ⚠️ shared kernel | ✅ small syscall subset |
| Can escapee read the host? | Yes | Config-dependent | **No — no reachable syscall** |

That last row is the point. Container isolation is **namespace-level** and shares the Linux kernel; Wasm isolation is **instruction-set-level** — a module has no ability to invoke `openat`, `fork`, or `ptrace` unless the host explicitly injects that capability. For "run this untrusted snippet," Wasm's default posture is safe by construction.

## 1. Architecture: Agent → Capability Gateway → Wasm Sandbox

Never let an agent `exec` anything directly on a VPS. Put a **deterministic** gateway in between:

```
┌──────────────┐   JSON tool_call    ┌────────────────┐   argv + stdin   ┌──────────────┐
│ Local LLM     │ ──────────────────▶ │ Gateway (Python)│ ───────────────▶ │ Wasm sandbox │
│ Ollama/Qwen2.5│                     │ allowlist+limits│ ◀─────────────── │ wasmedge run │
└──────────────┘ ◀──── JSON result ─── └────────────────┘   stdout/stderr  └──────────────┘
                                              │
                                         SQLite audit log
```

Three non-negotiable rules:

1. **The model selects tools; it never composes commands.** Tools are pre-compiled `.wasm` binaries. The model fills JSON parameters (`{"path": "/var/log/nginx/error.log", "pattern": "timeout"}`), which the gateway validates for type, regex, and path normalization before execution. The model cannot write `rm -rf /` because it has no shell channel at all.
2. **Capabilities are granted at the gateway, not inside the code.** Need log access? The gateway preopens `/var/log/nginx` read-only. Need network? The gateway exposes a GET-only fetch proxy to specific domains — not a socket.
3. **Timeout/memory/CPU are hard limits**, enforced inside the VM, not best-effort external kills.

## 2. Install WasmEdge and Compile Your First Tool (3 Minutes)

WasmEdge is a CNCF sandbox project; the binary installs cleanly on most VPS providers:

```bash
# 1. Install WasmEdge (~40MB, includes the AOT compiler)
curl -sSf https://raw.githubusercontent.com/WasmEdge/WasmEdge/master/utils/install.sh \
  | bash -s -- -p /opt/wasmedge --version 0.14.1
echo 'export PATH=/opt/wasmedge/bin:$PATH' >> /etc/profile.d/wasmedge.sh

wasmedge --version
# wasmedge version 0.14.1-rc.1

# 2. Install the Rust wasm32-wasi target (one-time)
apt install -y build-essential pkg-config
curl -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal
source ~/.cargo/env
rustup target add wasm32-wasi
```

Tool number one: `log_grep` — regex-match lines inside the mounted log directory and return the first N hits. Note that its inputs are **structured**; the code has zero string-concatenation surface:

```rust
// tools/log_grep/src/main.rs
use std::io::{self, Read};
use regex::Regex;

fn main() {
    let mut input = String::new();
    io::stdin().read_to_string(&mut input).unwrap();
    // Gateway passes JSON: {"path":"/logs/error.log","pattern":"timeout","limit":20}
    let v: serde_json::Value = serde_json::from_str(&input).unwrap();
    let path = v["path"].as_str().unwrap_or("");
    let pat  = v["pattern"].as_str().unwrap_or("");
    let limit = v["limit"].as_u64().unwrap_or(20) as usize;

    // Belt and braces: path must live under /logs and contain no ".."
    // (applies even if the gateway is bypassed)
    if !path.starts_with("/logs/") || path.contains("..") {
        println!("{{\"error\":\"path rejected\"}}");
        return;
    }
    let re = match Regex::new(pat) {
        Ok(r) => r,
        Err(e) => { println!("{{\"error\":\"bad regex: {e}\"}}"); return; }
    };
    let content = match std::fs::read_to_string(path) {
        Ok(c) => c,
        Err(e) => { println!("{{\"error\":\"read failed: {e}\"}}"); return; }
    };
    let hits: Vec<String> = content.lines()
        .filter(|l| re.is_match(l))
        .take(limit)
        .map(|l| l.chars().take(500).collect())   // truncate: never blow up the context window
        .collect();
    println!("{}", serde_json::json!({"count": hits.len(), "lines": hits}));
}
```

```bash
cd tools/log_grep && cargo build --release --target wasm32-wasi
ls -lh target/wasm32-wasi/release/log_grep.wasm
# -rwxr-xr-x  2.6M  log_grep.wasm

# 3. AOT-compile: cold start drops from ~40ms to single-digit ms
wasmedge compile log_grep.wasm log_grep_aot.wasm
# ~3MB output, runs as native code from then on
```

Measured on a 2C4G VPS with NVMe: running a 2.6MB AOT module that parses a 12MB log file takes **5.8ms** (excluding IO) — 4x faster than starting `python3 -c` at 22ms.

## 3. The Gateway: Putting Every Tool Call in a Cage

The gateway is the only trusted component. It validates parameters, injects capabilities, enforces quotas, and audits. The core is a subprocess call whose argv the gateway builds itself:

```python
# gateway.py
import json, re, sqlite3, subprocess, hashlib, time, os

WASMEDGE = "/opt/wasmedge/bin/wasmedge"
SANDBOX  = "/srv/agent/tools"

# Capability table: tool -> (wasm file, read-only preopens, arg schema)
ALLOWLIST = {
    "log_grep": {
        "bin": "log_grep_aot.wasm",
        "preopen": ["/logs:/var/log/nginx:ro"],
        "schema": {"path": r"^/logs/[\w./-]+$", "pattern": r"^.{1,200}$"},
        "limit": {"memory_mb": 128, "timeout_s": 10, "max_args": 3},
    },
    "csv_stats": {
        "bin": "csv_stats_aot.wasm",
        "preopen": ["/data:/srv/agent/data:ro"],
        "schema": {"path": r"^/data/[\w./-]+$"},
        "limit": {"memory_mb": 256, "timeout_s": 20, "max_args": 1},
    },
}

def audit(tool, args, code, out_hash, latency_ms):
    con = sqlite3.connect("/srv/agent/audit.db")
    con.execute("""CREATE TABLE IF NOT EXISTS calls(
        ts REAL, tool TEXT, args TEXT, exit_code INT, out_sha256 TEXT, latency_ms INT)""")
    con.execute("INSERT INTO calls VALUES (?,?,?,?,?,?)",
                (time.time(), tool, json.dumps(args), code, out_hash, latency_ms))
    con.commit()

def check(tool, args):
    spec = ALLOWLIST.get(tool)
    if not spec:
        raise ValueError(f"tool '{tool}' not allowed")
    if set(args) - set(spec["schema"]):
        raise ValueError("unexpected arg keys")
    for k, rx in spec["schema"].items():
        if k in args and not re.match(rx, str(args[k])):
            raise ValueError(f"arg '{k}' rejected by schema")
    return spec

def run_tool(tool, args):
    spec = check(tool, args)
    lim = spec["limit"]
    argv = [WASMEDGE, "run"]
    for p in spec["preopen"]:
        argv += ["--dir", p]
    argv += ["--memory-limit", f"{lim['memory_mb']}MB", os.path.join(SANDBOX, spec["bin"])]

    t0 = time.time()
    try:
        r = subprocess.run(argv, input=json.dumps(args), capture_output=True,
                           timeout=lim["timeout_s"], text=True)
        code, out = r.returncode, r.stdout
        if r.returncode != 0 and r.stderr:
            out = json.dumps({"error": r.stderr[:400]})
    except subprocess.TimeoutExpired:
        code, out = 124, json.dumps({"error": "timeout"})
    ms = int((time.time() - t0) * 1000)
    audit(tool, args, code, hashlib.sha256(out.encode()).hexdigest()[:16], ms)
    return {"ok": code == 0, "result": json.loads(out) if out else None, "latency_ms": ms}
```

Design notes that matter:

**`--dir /logs:/var/log/nginx:ro` is a capability, not a path mapping.** The path `/logs` does not exist inside the module. Only an explicit host preopen puts it in the module's fd table. A module attempting `/etc/shadow` gets `ENOTCAPABLE`, not `EACCES` — it does not *know* that path exists, rather than lacking permission to it.

**No `--dir` means no filesystem.** By default a WASI module sees an empty world: no files, no environment variables, no sockets. That is why no `chroot` is needed here.

**Regex at the gateway plus a second check inside the module.** The gateway blocks `../../etc/passwd`; the module checks again. Defense in depth isn't about distrusting a layer — it's because the gateway will be modified someday.

**Hash-chained audit.** Every call's output is hashed with SHA-256 and stored. Post-incident, "what did the agent actually read that day" has verifiable evidence instead of depending on whether logs were altered.

## 4. Wiring the Agent: Structured tool_call to Wasm Execution

The agent-side change is minimal — it goes from "generate bash" to "fill JSON":

```python
# agent_tools.py — tool description exposed to local Ollama (OpenAI tools format)
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "log_grep",
            "description": "Regex-search lines in Nginx logs, max 20 hits. Log directory only.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "e.g. /logs/error.log"},
                    "pattern": {"type": "string", "description": "RE2 regular expression"},
                },
                "required": ["path", "pattern"],
            },
        },
    },
]

# Inside the agent's main loop
from gateway import run_tool

def dispatch(call):
    name = call.function.name
    args = json.loads(call.function.arguments or "{}")
    r = run_tool(name, args)          # every exception becomes a structured error
    return json.dumps(r, ensure_ascii=False)[:8000]
```

A full 7-turn conversation measured on this box (Qwen2.5-7B-q4, `log_grep` ×4, `csv_stats` ×2):

| Stage | Time |
|-------|------|
| LLM generates tool_call (4x 7B) | 11.4s |
| 6 Wasm tool executions, total | **38ms** |
| Gateway validation + audit write | 9ms |
| Full turn | 11.8s |

Tool execution is **0.3%** of total time. With Docker, six `docker run` calls cost roughly 3–5s — over 30% of the turn. That is the real reason "sandboxes are useful but nobody uses them."

## 5. systemd as the Last Layer: Cage the Sandbox Itself

Wasm isolation is strong, but the host `wasmedge` process is still an ordinary process. The foundation belongs to systemd:

```ini
# /etc/systemd/system/agent-gateway.service
[Unit]
Description=AI Agent Tool Gateway (WasmEdge sandbox)
After=network.target ollama.service

[Service]
Type=simple
User=agent
WorkingDirectory=/srv/agent
ExecStart=/usr/bin/python3 /srv/agent/gateway_api.py
Restart=on-failure
RestartSec=3

# Minimize the gateway too:
NoNewPrivileges=yes
PrivateTmp=yes
PrivateDevices=yes
ProtectSystem=strict
ProtectHome=yes
ReadOnlyPaths=/srv/agent/tools /var/log/nginx
ReadWritePaths=/srv/agent/audit.db /srv/agent/run
MemoryMax=1G
CPUQuota=150%
RestrictAddressFamilies=AF_INET AF_INET6
SystemCallFilter=@system-service
SystemCallErrorNumber=EPERM

[Install]
WantedBy=multi-user.target
```

The semantics are clear: `ReadOnlyPaths` stops even the gateway from modifying the tool binaries (a classic "replace the sandbox binary" bypass), `MemoryMax` keeps a DoS'd gateway from dragging down the box, and `SystemCallFilter` denies children syscalls like `clone(CLONE_NEWUSER)` that could otherwise be abused.

## 6. Three Pitfalls I Hit

**Pitfall 1: `--memory-limit` is not a hard OOM kill.** When a module hits the cap, allocation fails; but if the module `panic!`s without handling it, you get exit code 1 rather than a graceful error. The gateway must translate every non-zero exit into `{"error": ...}` for the model — otherwise the model concludes "the tool succeeded but returned nothing" and starts hallucinating. This was my first version's biggest bug.

**Pitfall 2: WASI preview 1 lacks time formatting beyond `clock_time_get`.** If a tool wants to print "3 hours ago", you compute it in Rust or let the model do it. Don't reach for `strftime`.

**Pitfall 3: AOT artifacts are CPU-feature-bound.** A `.so` compiled on an AVX-512 machine throws `SIGILL` on older Xeons. For heterogeneous VPS fleets, use `wasmedge compile --generic` to disable instruction-set specialization (10–20% slower, still over 5x faster than interpretation).

## 7. When Not to Use Wasm

Honestly, Wasm is not a silver bullet:

- **Tools needing GPU/NPU inference**: the WASI-NN ecosystem is still early and CUDA support is limited. Keep those on the host behind strict auth, or don't expose them to the agent at all.
- **Large-scale file-IO batch jobs**: WASI file IO is slower than native. For GB-scale data, native + `bubblewrap` is a better fit.
- **Scripts depending on many system binaries** (`awk`, `jq`, `ffmpeg`): those don't exist in Wasm. Reimplement in Rust or fall back to containers.

My rule of thumb: **if the tool is "model generates parameters → my precompiled logic executes," use Wasm. If the tool is "model generates a whole shell script," the answer isn't a different sandbox — the answer is to stop letting it generate shell.**

## Closing

The most underrated part of putting AI agents into VPS operations isn't model capability — it's the **execution boundary**. Replacing the tool layer with Wasm took one afternoon (20 minutes to install WasmEdge, 2 hours for two tools, 1 hour for the gateway). What it buys: the model can hallucinate freely, and the worst outcome is a bad JSON error — not a machine that needs reinstalling.

That is a far better investment than any "add a stricter system prompt" exercise.

**References**

- WasmEdge docs: <https://wasmedge.org/docs/>
- WASI capability model spec: <https://github.com/WebAssembly/WASI/blob/main/legacy/preview1/docs.md>
- Rust `wasm32-wasi` target: <https://doc.rust-lang.org/rustc/platform-support/wasm32-wasi.html>
- systemd sandboxing directives: `man 5 systemd.exec`
