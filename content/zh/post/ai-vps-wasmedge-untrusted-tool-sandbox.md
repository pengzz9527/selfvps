---
title: "AI Agent 工具沙箱：用 WasmEdge 隔离 LLM 生成代码，冷启动 3ms 的 VPS 实践"
date: 2026-11-04
tags: ["VPS", "AI", "WasmEdge", "沙箱", "安全", "Agent"]
draft: false
image: /images/posts/ai-vps-wasmedge-untrusted-tool-sandbox/featured.png
description: "让本地 LLM 帮你写运维脚本很爽，让它在你的 VPS 上直接跑就是事故：一条 rm -rf 或 curl | bash 就能带走整台机器。本文用 WasmEdge + WASI 把一个 AI Agent 的工具调用层改造成默认拒绝的沙箱执行器：能力白名单（只给指定目录读写权）、网络默认关闭、内存/CPU/超时硬限制、毫秒级冷启动，2C4G VPS 上单次工具调用开销 <6ms，比起一个 Docker 容器快 300 倍。"
---

# AI Agent 工具沙箱：用 WasmEdge 隔离 LLM 生成代码，冷启动 3ms 的 VPS 实践

我给站点写了个本地运维 Agent：它读日志、查指标、然后**生成一段脚本让我确认执行**。第一次跑通时我很兴奋，第二次就出了一身冷汗——模型给的那段脚本里有一行 `curl -s https://... | bash`，域名拼错了一个字母。

这不是模型"变坏"了，而是**概率性系统本来就会有概率性输出**。把 LLM 生成的代码直接丢进 `bash -c`，等于把一台 VPS 的 root 权限交给一个你无法审计、无法复现、无法做代码审查的组件。

传统做法是套一层 Docker：`docker run --rm --network none -v ... python:3.12`。它能用，但代价是每次工具调用要 300ms~1.5s 启动，Agent 一轮对话调 5 个工具就是额外几秒；更麻烦的是容器镜像动辄几百 MB，2C4G 的小机器上跑几个就吃紧了。

本文的方案：**把工具执行层换成 WebAssembly 沙箱**（WasmEdge + WASI）。收益非常直接：

| 指标 | `bash -c` 直接跑 | Docker 容器 | WasmEdge 沙箱 |
|------|:---:|:---:|:---:|
| 单次执行冷启动 | ~2ms | 300–1500ms | **3–8ms** |
| 运行时体积 | 0（系统自带） | 镜像 100MB~1GB | 模块 2–15MB |
| 网络默认隔离 | ❌ 完全开放 | ✅ `--network none` | ✅ 默认无 socket |
| 文件系统隔离 | ❌ 全盘可写 | ✅ 挂载点控制 | ✅ 预开目录（preopen） |
| 内存上限 | ❌ | ✅ `--memory` | ✅ `--memory-limit` |
| 宿主机内核攻击面 | ❌ 完整 syscall | ⚠️ 共享内核 | ✅ 几百条 syscall 的子集 |
| 逃逸后能读到宿主机吗 | 是 | 视配置 | **否（无 syscall 可达）** |

最后一行才是关键：容器隔离是**内核命名空间级**的，共享同一个 Linux 内核；Wasm 隔离是**指令集级**的，模块根本**没有**执行 `openat`、`fork`、`ptrace` 的能力——除非宿主显式把对应能力注入进去。对"跑一段不可信代码"这个场景，Wasm 的默认姿态天然就是安全的。

## 一、架构：Agent → 能力网关 → Wasm 沙箱

在 VPS 上不要尝试"让 LLM 直接 exec"，中间必须有一个**确定性**的网关层。三层结构：

```
┌──────────────┐   JSON tool_call    ┌────────────────┐   argv + stdin   ┌──────────────┐
│ 本地 LLM      │ ──────────────────▶ │ 能力网关 (Python)│ ───────────────▶ │ Wasm 沙箱     │
│ Ollama/Qwen2.5│                     │ 白名单 + 限额    │ ◀─────────────── │ wasmedge run  │
└──────────────┘ ◀──── 结构化结果 ──── └────────────────┘   stdout/stderr  └──────────────┘
                                              │
                                        审计日志 SQLite
```

三条不可越过的规则：

1. **模型只能选工具，不能拼命令**。工具是预编译 `.wasm`，模型只填 JSON 参数（`{"path": "/var/log/nginx/error.log", "pattern": "timeout"}`），参数经过类型 + 正则 + 路径归一化校验后传给网关。模型写不出 `rm -rf /`，因为它压根没有写 shell 的通道。
2. **能力开在网关上，不开在代码里**。要读日志？网关挂载 `/var/log/nginx` 这个 preopen 目录。要联网？网关给一个只允许 GET 到特定域名的 fetch 代理，而不是给 socket。
3. **超时/内存/CPU 是硬限制**，不是"尽力而为"。Wasm 运行时把这几个阀门做在虚拟机内部，越界即终止，不依赖外部 kill。

## 二、装 WasmEdge 与编译第一个工具（3 分钟）

WasmEdge 是 CNCF 沙箱项目，国内 VPS 拉二进制包很稳：

```bash
# 1. 安装 WasmEdge（约 40MB，含 AOT 编译器）
curl -sSf https://raw.githubusercontent.com/WasmEdge/WasmEdge/master/utils/install.sh \
  | bash -s -- -p /opt/wasmedge --version 0.14.1
echo 'export PATH=/opt/wasmedge/bin:$PATH' >> /etc/profile.d/wasmedge.sh

wasmedge --version
# wasmedge version 0.14.1-rc.1

# 2. 装 Rust wasm32-wasi target（只需一次）
apt install -y build-essential pkg-config
curl -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal
source ~/.cargo/env
rustup target add wasm32-wasi
```

工具之一：`log_grep` —— 只允许在挂载的日志目录里做正则匹配，返回前 N 条命中。注意它的参数是**结构化**的，代码里没有任何 shell 拼接空间：

```rust
// tools/log_grep/src/main.rs
use std::io::{self, Read, Write};
use regex::Regex;

fn main() {
    let mut input = String::new();
    io::stdin().read_to_string(&mut input).unwrap();
    // 网关以 JSON 传入：{"path":"/logs/error.log","pattern":"timeout","limit":20}
    let v: serde_json::Value = serde_json::from_str(&input).unwrap();
    let path = v["path"].as_str().unwrap_or("");
    let pat  = v["pattern"].as_str().unwrap_or("");
    let limit = v["limit"].as_u64().unwrap_or(20) as usize;

    // 双保险：路径必须在 /logs 下且不含 ..（即便网关被绕过）
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
        .map(|l| l.chars().take(500).collect())   // 截断，防超大行打爆上下文
        .collect();
    println!("{}", serde_json::json!({"count": hits.len(), "lines": hits}));
}
```

```bash
cd tools/log_grep && cargo build --release --target wasm32-wasi
ls -lh target/wasm32-wasi/release/log_grep.wasm
# -rwxr-xr-x  2.6M  log_grep.wasm

# 3. 用 AOT 预编译，把冷启动从 ~40ms 降到个位数 ms
wasmedge compile log_grep.wasm log_grep_aot.wasm
# 编译后约 3MB，之后每次执行都是原生代码
```

实测（2C4G，NVMe）：AOT 编译后 `wasmedge run` 一个 2.6MB 模块、解析 12MB 日志文件耗时 **5.8ms**（不含 IO），与启动一个 `python3 -c` 的 22ms 相比还快 4 倍。

## 三、网关：把每一次工具调用关进笼子

网关是唯一可信组件，负责参数校验、能力注入、资源限额、审计。核心是一段 subprocess 调用，但参数全部由网关自己拼：

```python
# gateway.py
import json, re, sqlite3, subprocess, hashlib, time, os

WASMEDGE = "/opt/wasmedge/bin/wasmedge"
SANDBOX  = "/srv/agent/tools"

# 能力表：工具 -> (wasm 文件, 预开只读目录, 参数 schema)
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

几个必须解释的设计点：

**`--dir /logs:/var/log/nginx:ro` 是能力，不是路径**。Wasm 模块里 `/logs` 这个路径根本不存在，只有宿主通过 preopen 显式映射才会出现在模块的 fd 表里。模块尝试访问 `/etc/shadow` 会得到 `ENOTCAPABLE`，而不是 `EACCES`——它是**不知道**这个路径存在，而不是权限不够。

**没有 `--dir` 就没有文件系统**。默认情况下 WASI 模块能看到的环境是一个空世界：没有文件、没有环境变量、没有 socket。这就是为什么这里连 `chroot` 都不需要。

**路径正则 + 模块内二次校验**。网关的正则挡住 `../../etc/passwd`，模块里再查一次。防御纵深不是因为不信任某一层，而是因为 LLM 网关将来会被改。

**审计哈希链**。每次调用的输出算 SHA-256 存储。事后复盘"那天 Agent 到底读了什么"，有可验证的凭据，而不是靠日志被没被改过。

## 四、给 Agent 套上：结构化 tool_call 到 wasm 执行

Agent 侧的改动极小——它从"生成 bash"改成"填 JSON"：

```python
# agent_tools.py —— 暴露给本地 Ollama 的工具描述（OpenAI tools 格式）
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "log_grep",
            "description": "在 Nginx 日志中按正则检索行，返回最多 20 条。只能访问日志目录。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "形如 /logs/error.log"},
                    "pattern": {"type": "string", "description": "RE2 正则表达式"},
                },
                "required": ["path", "pattern"],
            },
        },
    },
]

# 在 Agent 主循环里
from gateway import run_tool

def dispatch(call):
    name = call.function.name
    args = json.loads(call.function.arguments or "{}")
    r = run_tool(name, args)          # 任何异常都在这里变成结构化错误
    return json.dumps(r, ensure_ascii=False)[:8000]
```

实测一次完整的 7 轮对话（Qwen2.5-7B-q4，`log_grep` 调 4 次、`csv_stats` 调 2 次）：

| 环节 | 耗时 |
|------|------|
| LLM 生成 tool_call（4 次×7B） | 11.4s |
| 6 次 Wasm 工具执行合计 | **38ms** |
| 网关校验 + 审计写入 | 9ms |
| 总轮次 | 11.8s |

工具执行占总耗时的 **0.3%**。换成 Docker 方案，6 次 `docker run` 大概要 3~5s，占总时长 30% 以上——这才是"沙箱很有用但没人用"的真实原因。

## 五、用 systemd 兜底：让沙箱自己也跑在笼子里

Wasm 隔离很强，但宿主的 `wasmedge` 进程本身仍是普通进程。最后一层地基交给 systemd：

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

# 网关自身也最小化：
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

这套组合的语义很清晰：`ReadOnlyPaths` 让网关自己都改不了工具二进制（防止"沙箱程序被替换"这类绕过），`MemoryMax` 让网关即使被 DoS 也拉不垮整机，`SystemCallFilter` 让子进程连 `clone(CLONE_NEWUSER)` 这种可能被拿来玩的系统调用都拿不到。

## 六、踩过的三个坑

**坑 1：`--memory-limit` 不是硬 OOM。** WasmEdge 达到内存上限时模块会收到分配失败，但如果模块自己 `panic!` 后没处理好，返回的是 `exit code 1` 而不是优雅错误。网关里必须把非零退出码统一转成 `{"error": ...}` 给模型，否则模型会以为"工具成功了但没输出"然后开始瞎编。这是我第一版最大的 bug。

**坑 2：WASI 预览 1 没有 `clock_time_get` 之外的时区/时间格式化。** 工具里想输出"3 小时前"这类人性化时间，得自己在 Rust 侧算，或者干脆让模型去算。别指望 `strftime`。

**坑 3：AOT 编译产物与 CPU 特性绑定。** 在支持 AVX-512 的机器上编译的 `.so` 拿到老 Xeon 上会 `SIGILL`。如果 VPS 集群异构，用 `wasmedge compile --generic` 关掉特定指令集优化（代价是慢 10~20%，仍然比解释执行快 5 倍以上）。

## 七、什么时候别用 Wasm

诚实地说，Wasm 沙箱不是银弹：

- **需要 GPU/NPU 的推理**：WASI-NN 生态还在早期，CUDA 支持有限。这类工具要么留在宿主机上单独跑并严格鉴权，要么干脆不给 Agent 调用。
- **需要大规模文件 IO 的批处理**：WASI 的文件 IO 路径比原生慢，处理 GB 级数据还是原生 + `bubblewrap` 更合适。
- **依赖大量系统工具的脚本**（`awk`、`jq`、`ffmpeg`）：Wasm 里没有这些二进制，要么用 Rust 重写，要么退回容器方案。

我的判断标准很简单：**如果这个工具是"模型生成参数 → 我预编译的逻辑去执行"，用 Wasm；如果这个工具是"模型生成一整段 shell"，那问题的答案不是换沙箱，而是别让它生成 shell。**

## 结语

AI Agent 落地到 VPS 的过程中，最容易被低估的不是模型能力，而是**执行边界**。把工具层换成 Wasm 只花了一个下午（装 WasmEdge 20 分钟，写两个工具 2 小时，网关 1 小时），换来的是：模型可以随便胡说八道，最坏结果也只是返回一条错误 JSON——而不是让整台机器重装系统。

这笔投入的性价比，比任何一次"给它加个更严格的 system prompt"要高得多。

**参考资源**

- WasmEdge 官方文档：<https://wasmedge.org/docs/>
- WASI 能力模型规范：<https://github.com/WebAssembly/WASI/blob/main/legacy/preview1/docs.md>
- Rust `wasm32-wasi` 目标：<https://doc.rust-lang.org/rustc/platform-support/wasm32-wasi.html>
- systemd 沙箱指令速查：`man 5 systemd.exec`
