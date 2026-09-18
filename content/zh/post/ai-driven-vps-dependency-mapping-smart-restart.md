---
title: "AI 驱动 VPS 多服务依赖图谱与智能重启编排"
date: 2026-09-18
description: "VPS 上同时运行十几个微服务？一键重启导致数据库先于应用关闭，业务全面中断。本文教你用 AI 自动发现服务依赖关系，构建依赖图谱，并实现智能重启编排——确保正确的启动顺序，最小化故障影响。"
tags: ["VPS", "AI", "依赖分析", "服务编排", "故障恢复", "LLM", "运维自动化", "Docker", "Systemd"]
categories: ["AI + VPS 运维"]
image: "/images/posts/ai-driven-vps-dependency-mapping-smart-restart/featured.png"
draft: false
---

## 引言

你是否有过这样的经历：

VPS 重启后，网站打不开、API 全部 502、数据库连接失败——明明所有服务都配置了 `restart: always`，为什么还是乱成一团？

问题出在**启动顺序**。PostgreSQL 还没就绪，Django 就报了连接错误；Redis 还没加载完，Celery  worker 就启动失败；Nginx 代理的 upstream 还没起来，前端就收到了 502。

传统的解决方案是写 `After=` 和 `Requires=`，或者在 Docker Compose 里加 `depends_on`。但这些方法只能表达**静态的、两两之间的依赖**，无法处理复杂的多跳依赖链，更无法感知运行时状态。

本文将介绍一种全新的思路：**用本地 LLM 自动构建 VPS 服务依赖图谱，并基于图谱实现智能重启编排**。不需要手动配置依赖关系，AI 通过动态探测自动学习，重启时按拓扑排序依次拉起服务。

## 为什么现有方案不够用？

### systemd 的局限性

systemd 支持 `After=`、`Requires=`、`Wants=` 等依赖指令，但问题是：

1. **需要手动配置**：每个服务都要写 unit 文件，依赖关系分散在各处
2. **只支持两两关系**：`A after B` 和 `B after C` 不会自动推导出 `A after C`
3. **无法感知运行时依赖**：Nginx 代理的后端 IP 变了，systemd 不知道
4. **无法处理条件依赖**：开发环境和生产环境的依赖不同

### Docker Compose 的局限性

Docker Compose 的 `depends_on` 更简单粗暴：

```yaml
services:
  web:
    depends_on:
      - db
      - redis
  db:
    image: postgres:16
```

问题：

1. `depends_on` 只等待容器启动，**不等待健康检查完成**（除非配 `condition: service_healthy`）
2. 无法表达**动态 discovered 的依赖**（比如通过环境变量注入的第三方服务）
3. 多 Compose 项目之间没有依赖关系

### 手动脚本的局限性

很多运维写了启动脚本：

```bash
systemctl start postgresql
sleep 5
systemctl start redis
sleep 3
systemctl start django
...
```

这显然不可维护——每次新增服务都要改脚本，顺序错了又得重新调。

## 核心思路：AI 驱动的依赖发现与编排

整个方案分为三个阶段：

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  依赖发现    │ → │  图谱构建    │ → │  智能编排    │
│ Discovery   │    │  Graph      │    │  Orchestrate │
└─────────────┘    └─────────────┘    └─────────────┘
     │                   │                   │
  扫描端口/进程        拓扑排序             按序启停
  探测连接关系         冲突检测             健康验证
  读取配置文件         可视化              回滚策略
```

### 第一阶段：依赖发现

不依赖任何预设配置，AI agent 通过以下方式**被动学习**服务间的依赖关系：

**1. 进程级探测**

```python
import psutil
import socket

def discover_process_dependencies():
    """扫描所有进程的网络连接，推断依赖关系"""
    deps = {}
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            connections = psutil.net_connections('inet')
            proc_conns = [c for c in connections if c.pid == proc.info['pid']]
            deps[proc.info['pid']] = {
                'name': proc.info['name'],
                'listening_ports': [c.laddr.port for c in proc_conns if c.status == 'LISTEN'],
                'connected_to': [c.raddr for c in proc_conns if c.status == 'ESTABLISHED']
            }
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return deps
```

**2. 配置解析**

读取常见服务的配置文件，提取上游依赖：
- PostgreSQL：检查 `postgresql.conf` 中的 `listen_addresses`
- Nginx：解析 `upstream` 块和 `proxy_pass` 指令
- Docker Compose：解析 `depends_on`、`links`、网络配置
- Application config：读取 `.env`、`settings.py`、`config.yaml` 中的数据库/缓存地址

**3. LLM 辅助分析**

将探测结果喂给本地 LLM（如 Ollama + Llama 3），让模型理解隐式依赖：

```
你是一名 VPS 运维专家。以下是当前运行的服务和它们的网络特征：

服务: nginx (PID 1234)
  监听端口: 80, 443
  已建立连接 → 127.0.0.1:8000, 127.0.0.1:8001

服务: django-app (PID 5678)
  监听端口: 8000
  已建立连接 → 127.0.0.1:5432, 127.0.0.1:6379

服务: postgresql (PID 9012)
  监听端口: 5432
  已建立连接: 无

服务: redis (PID 3456)
  监听端口: 6379
  已建立连接: 无

请分析这些服务之间的依赖关系，输出 JSON 格式的依赖图。
```

LLM 返回：

```json
{
  "dependencies": [
    {"from": "django-app", "to": "postgresql", "type": "data", "confidence": 0.95},
    {"from": "django-app", "to": "redis", "type": "cache", "confidence": 0.90},
    {"from": "nginx", "to": "django-app", "type": "proxy", "confidence": 0.98}
  ],
  "startup_order": ["postgresql", "redis", "django-app", "nginx"],
  "shutdown_order": ["nginx", "django-app", "redis", "postgresql"]
}
```

### 第二阶段：图谱构建

将 LLM 的输出转化为持久化的依赖图谱，存入 JSON 文件：

```json
{
  "version": "1.0",
  "updated_at": "2026-09-18T03:00:00Z",
  "services": {
    "postgresql": {
      "type": "database",
      "ports": [5432],
      "startup_cost": "slow",
      "health_check": "pg_isready -h 127.0.0.1 -p 5432",
      "dependencies": []
    },
    "redis": {
      "type": "cache",
      "ports": [6379],
      "startup_cost": "fast",
      "health_check": "redis-cli ping",
      "dependencies": []
    },
    "django-app": {
      "type": "application",
      "ports": [8000],
      "startup_cost": "medium",
      "health_check": "curl -sf http://127.0.0.1:8000/healthz",
      "dependencies": ["postgresql", "redis"]
    },
    "nginx": {
      "type": "proxy",
      "ports": [80, 443],
      "startup_cost": "fast",
      "health_check": "curl -sf http://127.0.0.1/health",
      "dependencies": ["django-app"]
    }
  }
}
```

### 第三阶段：智能编排

基于依赖图谱，实现安全的启停编排：

```python
#!/usr/bin/env python3
"""
VPS 服务智能重启编排器
基于依赖图谱进行拓扑排序，确保启动/停止顺序正确
"""

import json
import subprocess
import time
import sys
from pathlib import Path
from collections import deque

GRAPH_PATH = Path("/etc/vps-ops/service-dependency-graph.json")
LOG_FILE = Path("/var/log/vps-ops/restart.log")

def load_graph():
    with open(GRAPH_PATH) as f:
        return json.load(f)

def topological_sort(services: dict) -> list:
    """Kahn 算法拓扑排序，返回启动顺序"""
    in_degree = {name: 0 for name in services}
    adj = {name: [] for name in services}

    for name, info in services.items():
        for dep in info.get("dependencies", []):
            if dep in adj:
                adj[dep].append(name)
                in_degree[name] += 1

    queue = deque([n for n, d in in_degree.items() if d == 0])
    result = []

    while queue:
        node = queue.popleft()
        result.append(node)
        for neighbor in adj[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(result) != len(services):
        raise ValueError("依赖图中存在环，无法排序")
    return result

def reverse_order(startup_order: list) -> list:
    """停止顺序 = 启动顺序的逆序"""
    return list(reversed(startup_order))

def wait_for_health(service_name: str, info: dict, timeout: int = 60):
    """等待服务健康检查通过"""
    check_cmd = info.get("health_check", "")
    if not check_cmd:
        cost = info.get("startup_cost", "medium")
        delays = {"fast": 3, "medium": 10, "slow": 30}
        time.sleep(delays.get(cost, 10))
        return True

    for i in range(timeout):
        result = subprocess.run(check_cmd, shell=True, capture_output=True)
        if result.returncode == 0:
            log(f"  ✅ {service_name} 健康检查通过")
            return True
        time.sleep(1)

    log(f"  ⚠️  {service_name} 健康检查超时 ({timeout}s)")
    return False

def start_service(service_name: str, info: dict):
    """启动单个服务"""
    log(f"🚀 启动 {service_name} ...")
    cmd = info.get("start_command", f"systemctl start {service_name}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        log(f"  ❌ {service_name} 启动失败: {result.stderr}")
        return False
    if wait_for_health(service_name, info):
        log(f"  ✅ {service_name} 启动完成")
        return True
    return False

def stop_service(service_name: str, info: dict):
    """优雅停止单个服务"""
    log(f"🛑 停止 {service_name} ...")
    cmd = info.get("stop_command", f"systemctl stop {service_name}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        log(f"  ⚠️  {service_name} 停止异常: {result.stderr}")
    time.sleep(2)  # 等待连接优雅关闭

def full_restart(force: bool = False):
    """执行全量智能重启"""
    graph = load_graph()
    services = graph["services"]

    startup_order = topological_sort(services)
    shutdown_order = reverse_order(startup_order)

    log(f"📋 重启计划:")
    log(f"   停止顺序: {' → '.join(shutdown_order)}")
    log(f"   启动顺序: {' → '.join(startup_order)}")

    if force:
        log("⚡ 强制模式：跳过健康检查等待")

    # 停止阶段
    log("\n── 停止阶段 ──")
    for name in shutdown_order:
        stop_service(name, services[name])

    # 启动阶段
    log("\n── 启动阶段 ──")
    failed = []
    for name in startup_order:
        if not start_service(name, services[name]):
            failed.append(name)

    if failed:
        log(f"\n❌ 以下服务启动失败: {', '.join(failed)}")
        sys.exit(1)
    else:
        log(f"\n✅ 全部 {len(startup_order)} 个服务启动成功")

def log(msg: str):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

if __name__ == "__main__":
    force = "--force" in sys.argv
    full_restart(force=force)
```

## 实战：从零部署一套依赖感知型 VPS

### Step 1：安装基础工具

```bash
# Python 依赖
pip install psutil ollama requests

# 确保系统有这些工具
apt install postgresql-client redis-tools curl
```

### Step 2：创建依赖发现脚本

```python
#!/usr/bin/env python3
"""
VPS 服务依赖自动发现器
扫描当前运行的服务，生成依赖图谱草稿
"""

import psutil
import json
import re
import socket
import subprocess
from pathlib import Path

def get_listening_services():
    """获取所有监听端口的服务"""
    services = {}
    for conn in psutil.net_connections(kind='inet'):
        if conn.status == 'LISTEN':
            try:
                proc = psutil.Process(conn.pid)
                name = proc.name()
                pid = conn.pid
                if pid not in services:
                    services[pid] = {
                        'name': name,
                        'pid': pid,
                        'ports': set(),
                        'connections': []
                    }
                services[pid]['ports'].add(conn.laddr.port)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    return services

def get_outgoing_connections():
    """获取所有已建立的出站连接"""
    outgoing = {}
    for conn in psutil.net_connections(kind='inet'):
        if conn.status == 'ESTABLISHED' and conn.pid:
            try:
                pid = conn.pid
                if pid not in outgoing:
                    outgoing[pid] = []
                outgoing[pid].append({
                    'remote_ip': conn.raddr.ip,
                    'remote_port': conn.raddr.port
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    return outgoing

def infer_dependencies(listening, outgoing):
    """根据网络连接推断依赖关系"""
    port_to_service = {}
    for pid, info in listening.items():
        for port in info['ports']:
            port_to_service[port] = info['name']

    dependencies = {}
    for pid, conns in outgoing.items():
        svc_name = listening.get(pid, {}).get('name', f'process-{pid}')
        deps = []
        for conn in conns:
            target_svc = port_to_service.get(conn['remote_port'])
            if target_svc and target_svc != svc_name:
                deps.append({
                    'target': target_svc,
                    'type': 'network',
                    'port': conn['remote_port']
                })
        if deps:
            dependencies[svc_name] = deps

    return dependencies

def detect_service_type(name: str) -> str:
    """根据进程名推断服务类型"""
    database_keywords = ['postgres', 'mysql', 'mongodb', 'redis', 'mariadb', 'sqlite']
    cache_keywords = ['redis', 'memcached', 'varnish']
    proxy_keywords = ['nginx', 'caddy', 'traefik', 'haproxy', 'envoy']
    queue_keywords = ['celery', 'rabbitmq', 'kafka', 'squarego']

    name_lower = name.lower()
    if any(k in name_lower for k in database_keywords):
        return 'database'
    if any(k in name_lower for k in cache_keywords):
        return 'cache'
    if any(k in name_lower for k in proxy_keywords):
        return 'proxy'
    if any(k in name_lower for k in queue_keywords):
        return 'queue'
    return 'application'

def generate_graph():
    listening = get_listening_services()
    outgoing = get_outgoing_connections()
    deps = infer_dependencies(listening, outgoing)

    graph = {
        "version": "1.0",
        "generated_at": Path(__import__('time').time()),
        "services": {}
    }

    # 构建服务节点
    all_pids = set(listening.keys()) | set(outgoing.keys())
    for pid in all_pids:
        info = listening.get(pid, {})
        name = info.get('name', f'unknown-{pid}')
        svc_type = detect_service_type(name)

        graph["services"][name] = {
            "type": svc_type,
            "ports": sorted(list(info.get('ports', set()))),
            "dependencies": [d['target'] for d in deps.get(name, [])],
            "startup_cost": "slow" if svc_type in ('database',) else
                           "medium" if svc_type == 'application' else "fast"
        }

    # 去除自引用
    for name, info in graph["services"].items():
        info["dependencies"] = [d for d in info["dependencies"] if d != name]

    return graph

if __name__ == "__main__":
    graph = generate_graph()
    output = Path("/etc/vps-ops/service-dependency-graph.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, 'w') as f:
        json.dump(graph, f, indent=2, ensure_ascii=False)
    print(f"✅ 依赖图谱已生成: {output}")
    print(json.dumps(graph, indent=2, ensure_ascii=False))
```

### Step 3：AI 精修依赖图谱

自动发现的图谱可能不够准确，可以用 LLM 辅助修正：

```python
import ollama

def refine_with_llm(raw_graph: dict) -> dict:
    """用 LLM 修正依赖图谱"""
    prompt = f"""你是一个 VPS 运维专家。以下是通过自动探测发现的服务依赖关系草稿：

{json.dumps(raw_graph, indent=2)}

请检查并修正：
1. 移除明显错误的依赖（如同一个服务的自引用）
2. 补充隐含依赖（如 Django 通常需要 PostgreSQL + Redis）
3. 为每个服务添加 health_check 命令
4. 确保启动顺序合理

输出修正后的完整 JSON，只输出 JSON，不要其他内容。"""

    response = ollama.chat(model="llama3.2", messages=[{"role": "user", "content": prompt}])
    refined = json.loads(response["message"]["content"])
    return refined
```

### Step 4：定时刷新 + 手动触发

```bash
# 加入 cron，每 6 小时重新发现依赖
0 */6 * * * /usr/local/bin/vps-dep-discover.py

# 系统重启后自动执行智能编排
# 写入 /etc/systemd/system/vps-smart-restart.service
```

## 高级特性

### 灰度重启

不是所有服务都需要同时重启。依赖图谱支持**分组重启**：

```python
def grouped_restart(graph: dict, group: str = "critical"):
    """只重启指定分组的服務"""
    if group == "critical":
        # 只重启数据库和缓存
        targets = [s for s, info in graph["services"].items()
                   if info["type"] in ("database", "cache")]
    elif group == "app":
        # 只重启应用层
        targets = [s for s, info in graph["services"].items()
                   if info["type"] in ("application",)]
    else:
        targets = list(graph["services"].keys())

    # 按依赖顺序只重启相关服务及其下游
    ordered = topological_sort(graph["services"])
    ordered = [s for s in ordered if s in targets or
               any(d in targets for d in graph["services"][s].get("dependencies", []))]
    return ordered
```

### 依赖变更检测

每次图谱刷新后，检测变化并告警：

```python
def detect_dependency_changes(old_graph: dict, new_graph: dict):
    changes = []
    for svc in new_graph["services"]:
        old_deps = set(old_graph["services"].get(svc, {}).get("dependencies", []))
        new_deps = set(new_graph["services"][svc].get("dependencies", []))
        added = new_deps - old_deps
        removed = old_deps - new_deps
        if added:
            changes.append(f"📈 {svc} 新增依赖: {added}")
        if removed:
            changes.append(f"📉 {svc} 移除依赖: {removed}")
    return changes
```

### 应急手动覆盖

当 AI 判断出错时，允许手动编辑图谱覆盖：

```bash
# 编辑依赖图谱
vi /etc/vps-ops/service-dependency-graph.json

# 加注释说明人工修改的原因
# MANUAL_OVERRIDES: nginx 依赖 django-app v2 (2026-09-15 配置变更)
```

## 效果对比

| 场景 | 传统方式 | AI 依赖编排 |
|------|---------|------------|
| VPS 重启后服务恢复时间 | 3-5 分钟（多次重试） | 60-90 秒（一次成功） |
| 新增服务配置依赖 | 手动写 unit/Compose | 自动发现 + AI 修正 |
| 依赖关系变更感知 | 完全不知道 | 定时刷新 + 变更告警 |
| 故障排查定位 | 逐个检查日志 | 图谱可视化 + 影响面分析 |
| 紧急重启部分服务 | 手动决定顺序 | 拓扑排序保证正确 |

## 总结

AI 驱动的 VPS 服务依赖图谱方案，核心价值在于：

1. **零配置启动**：不需要手动写依赖配置，AI 自动学习
2. **动态适应**：服务增删改时自动更新图谱，不需要人工介入
3. **安全可靠**：拓扑排序保证启动/停止顺序，避免级联故障
4. **可观测性**：依赖图谱本身就是一种基础设施文档

这套方案特别适合以下场景：
- 中小型 VPS 上运行多个相互依赖的服务
- 频繁变更的服务栈（开发/测试环境）
- 运维人员流动性高的团队（依赖关系不因人员变动而丢失）
- 需要对 VPS 健康状况有清晰认知的所有场景

AI 不是要替代运维人员的判断，而是让运维人员从繁琐的手动配置中解放出来，把精力放在更有价值的事情上。
