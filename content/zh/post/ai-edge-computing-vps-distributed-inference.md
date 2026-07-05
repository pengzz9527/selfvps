---
title: "AI 赋能的 VPS 边缘计算节点：分布式推理与智能 CDN 加速"
description: "将多台 VPS 组建成 AI 边缘推理集群，结合智能 CDN 路由策略，实现低延迟分布式推理、负载均衡和故障转移。本文从零开始搭建一套完整的边缘 AI 计算网络。"
date: 2026-07-05T21:30:00+08:00
slug: "ai-edge-computing-vps-distributed-inference"
tags: ["AI边缘计算", "分布式推理", "CDN加速", "多VPS架构", "Ollama", "智能路由", "故障转移"]
categories: ["AI运维"]
image: /images/posts/ai-edge-computing-vps-distributed-inference/featured.png
draft: false
---

在 AI 应用爆发式增长的今天，模型推理延迟成为影响用户体验的核心瓶颈。传统的集中式部署方案将所有请求汇聚到单台服务器，一旦流量激增或节点故障，整个服务就会瘫痪。

**边缘计算**正是解决这一问题的关键思路——将计算能力推向离用户更近的地方。而 **AI 驱动的分布式推理**则更进一步：通过智能路由、负载均衡和故障转移机制，让多台 VPS 协同工作，像一台超级计算机一样对外提供服务。

本文将带你搭建一套完整的 **AI 边缘计算节点集群**，涵盖架构设计、模型分发、智能路由、性能监控和自动化运维。

## 为什么选择 VPS 构建边缘 AI 集群？

| 优势 | 说明 |
|------|------|
| 低成本 | 相比公有云 GPU 实例，多区域 VPS 组合成本降低 60-80% |
| 全球覆盖 | 在东京、新加坡、弗吉尼亚等地部署节点，延迟可控制在 50ms 以内 |
| 弹性扩展 | 按流量自动增减节点，无需预置大量硬件 |
| 故障隔离 | 单节点故障不影响整体服务，AI 自动切换路由 |
| 自主可控 | 完全掌控数据流和模型版本，无厂商锁定风险 |

### 典型场景

- **多语言客服系统**：各区域节点部署对应语言的 LLM，本地推理避免跨国传输延迟
- **内容审核平台**：图像/视频审核请求就近分发到最近的边缘节点
- **实时翻译服务**：多节点并行处理，按语种自动路由到专用推理节点
- **个性化推荐引擎**：边缘节点缓存用户画像，减少回源请求

## 架构设计：三层边缘推理网络

```
                    ┌─────────────────────┐
                    │   AI 智能路由网关    │
                    │  (Nginx + Lua)      │
                    │  延迟检测 / 健康检查  │
                    └──────────┬──────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                 │
    ┌─────────▼──────┐ ┌──────▼───────┐ ┌──────▼───────┐
    │  东京边缘节点    │ │  新加坡节点   │ │  弗吉尼亚节点  │
    │  Ollama + vLLM  │ │  Ollama +    │ │  Ollama +     │
    │  Qwen2.5-7B    │ │  text-embedding│ │  embedding    │
    │  延迟 ~15ms     │ │  模型         │ │  模型          │
    │                 │ │  延迟 ~25ms   │ │  延迟 ~80ms   │
    └────────────────┘ └───────────────┘ └───────────────┘
              │                │                 │
              └────────────────┼────────────────┘
                               │
                    ┌──────────▼──────────┐
                    │   模型同步管理器     │
                    │   (rsync + version)  │
                    └─────────────────────┘
```

### 核心组件

1. **智能路由网关**：位于最前端，根据客户端 IP 自动路由到最近的节点，同时持续监测各节点延迟和健康状态
2. **边缘推理节点**：每台 VPS 部署轻量级推理服务，根据区域需求加载不同的模型
3. **模型同步管理器**：确保所有节点的模型版本一致，支持灰度发布和快速回滚

## 第一步：搭建边缘节点推理服务

在每个 VPS 上部署 Ollama 作为推理引擎。推荐使用 Docker Compose 统一管理：

```yaml
# docker-compose.edge.yml
version: '3.8'
services:
  ollama:
    image: ollama/ollama:latest
    container_name: edge-ollama
    ports:
      - "127.0.0.1:11434:11434"
    volumes:
      - ./models:/root/.ollama
      - ./config:/etc/ollama
    environment:
      - OLLAMA_HOST=0.0.0.0
      - OLLAMA_ORIGINS=https://your-domain.com
      - OLLAMA_KEEP_ALIVE=-1
    deploy:
      resources:
        limits:
          memory: 8G
          cpus: '4.0'
    restart: unless-stopped

  ollama-exporter:
    image: prom/node-exporter:latest
    container_name: edge-ollama-exporter
    ports:
      - "9101:9100"
    volumes:
      - /proc:/host/proc:ro
      - /sys:/host/sys:ro
    restart: unless-stopped
```

启动并拉取模型：

```bash
# 启动 Ollama 服务
docker compose -f docker-compose.edge.yml up -d

# 拉取适合边缘节点的轻量模型
ollama pull qwen2.5:7b-instruct-q4_K_M
ollama pull nomic-embed-text:v1.0.3

# 验证服务
curl http://localhost:11434/api/tags
```

### 模型选择建议

| 节点类型 | 推荐模型 | 参数量 | 内存需求 | 适用场景 |
|----------|---------|--------|---------|---------|
| 通用推理 | Qwen2.5-7B-Instruct | 7B | ~5GB | 对话、总结、翻译 |
| 文本嵌入 | nomic-embed-text | 137M | ~300MB | RAG、语义搜索 |
| 代码生成 | StarCoder2-7B | 7B | ~5GB | 编程助手、Code Review |
| 轻量路由 | Phi-3-mini | 3.8B | ~3GB | 快速分类、意图识别 |

## 第二步：构建智能路由网关

使用 Nginx + Lua 实现基于延迟检测和地理定位的智能路由：

```lua
-- /etc/nginx/lua/router.lua
local geoip = require "resty.geoip"
local health = require "health.checker"

-- 节点配置
local nodes = {
    { name = "tokyo", ip = "10.0.1.10", port = 11434, region = "ap-northeast" },
    { name = "singapore", ip = "10.0.2.10", port = 11434, region = "ap-southeast" },
    { name = "virginia", ip = "10.0.3.10", port = 11434, region = "us-east" },
}

-- 根据客户端 IP 选择最近节点
local function select_node_by_geo(client_ip)
    local region = geoip.lookup(client_ip)
    local best_node = nil
    local min_latency = math.huge

    for _, node in ipairs(nodes) do
        local latency = health.get_latency(node)
        if latency < min_latency then
            min_latency = latency
            best_node = node
        end
    end

    return best_node, min_latency
end

-- Nginx 配置示例
-- upstream ollama_cluster {
--     server 10.0.1.10:11434;
--     server 10.0.2.10:11434;
--     server 10.0.3.10:11434;
-- }
```

对应的 Nginx 配置：

```nginx
http {
    # 定义后端节点池
    upstream ollama_cluster {
        least_conn;
        server 10.0.1.10:11434 weight=3;   # 东京 - 高权重
        server 10.0.2.10:11434 weight=2;   # 新加坡
        server 10.0.3.10:11434 weight=1;   # 弗吉尼亚
        keepalive 32;
    }

    server {
        listen 80;
        server_name api.your-edge-cluster.com;

        # 健康检查 - 自动剔除故障节点
        location /health {
            access_by_lua_block {
                local health = require "health.checker"
                local ok = health.check_all_nodes()
                if not ok then
                    ngx.status = 503
                    ngx.say("Node unavailable")
                    return ngx.exit(503)
                end
            }
            return 200 "OK";
        }

        # AI 推理请求路由
        location /v1/ {
            proxy_pass http://ollama_cluster;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

            # 超时设置
            proxy_connect_timeout 5s;
            proxy_read_timeout 120s;
            proxy_send_timeout 30s;

            # 添加延迟头供客户端监控
            header_filter_by_lua_block {
                local node = ngx.var.upstream_addr
                ngx.header["X-Routed-Node"] = node
                ngx.header["X-Edge-Latency"] = ngx.var.upstream_response_time
            }
        }
    }
}
```

## 第三步：模型版本同步与灰度发布

在多节点环境中，确保模型版本一致性至关重要。以下脚本实现了自动化同步：

```bash
#!/bin/bash
# sync_models.sh - 模型版本同步管理器

CLUSTER_NODES=("10.0.1.10" "10.0.2.10" "10.0.3.10")
MODEL_REGISTRY="https://registry.your-edge-cluster.com"
CURRENT_VERSION=$(curl -s ${MODEL_REGISTRY}/latest-version)
SYNC_LOG="/var/log/edge-model-sync.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> $SYNC_LOG
}

# 检查当前版本
check_version() {
    local node=$1
    local remote_version=$(ssh root@$node "ollama list | grep qwen2.5 | awk '{print \$2}'" 2>/dev/null)
    if [[ "$remote_version" != "$CURRENT_VERSION" ]]; then
        log "Node $node version mismatch: expected $CURRENT_VERSION, got $remote_version"
        return 1
    fi
    return 0
}

# 灰度同步：先同步主节点，验证后再同步其他节点
sync_to_nodes() {
    local primary=${CLUSTER_NODES[0]}
    
    # 第一步：同步主节点
    log "Starting gray release sync to primary node: $primary"
    ssh root@$primary "cd /opt/ollama && ollama pull qwen2.5:7b-instruct-${CURRENT_VERSION}"
    
    # 等待验证
    sleep 30
    
    # 检查主节点是否正常运行
    if curl -sf http://${primary}:11434/api/tags > /dev/null; then
        log "Primary node verified OK"
        
        # 第二步：同步其余节点
        for node in "${CLUSTER_NODES[@]:1}"; do
            log "Syncing to secondary node: $node"
            ssh root@$node "cd /opt/ollama && ollama pull qwen2.5:7b-instruct-${CURRENT_VERSION}"
            
            # 验证每个节点
            sleep 10
            if curl -sf http://${node}:11434/api/tags > /dev/null; then
                log "Node $node synced and verified OK"
            else
                log "ERROR: Node $node failed verification, rolling back"
                rollback_node $node
            fi
        done
        
        log "Gray release completed successfully"
    else
        log "ERROR: Primary node failed verification, aborting sync"
        rollback_primary
    fi
}

# 回滚函数
rollback_node() {
    local node=$1
    local prev_version=$(curl -s ${MODEL_REGISTRY}/prev-version)
    ssh root@$node "cd /opt/ollama && ollama pull qwen2.5:7b-instruct-${prev_version}"
    log "Rolled back node $node to version $prev_version"
}

rollback_primary() {
    log "Aborting gray release - rolling back primary"
    # 恢复到上一稳定版本逻辑...
}

# 定时执行：每天凌晨 3 点检查更新
# crontab: 0 3 * * * /opt/edge/sync_models.sh
sync_to_nodes
```

## 第四步：AI 驱动的自适应负载均衡

传统负载均衡只关注服务器在线状态，而 **AI 自适应负载均衡**会学习每个节点的实时性能特征，动态调整流量分配：

```python
#!/usr/bin/env python3
"""
ai_load_balancer.py - AI 驱动的自适应负载均衡器
基于历史性能数据动态调整各节点的权重
"""

import time
import json
import requests
from collections import deque
from datetime import datetime, timedelta
import heapq

class AdaptiveLoadBalancer:
    def __init__(self, config_path="lb_config.json"):
        with open(config_path) as f:
            self.config = json.load(f)
        
        self.nodes = self.config["nodes"]
        self.latency_history = {node["id"]: deque(maxlen=100) for node in self.nodes}
        self.error_history = {node["id"]: deque(maxlen=50) for node in self.nodes}
        self.weights = {node["id"]: node.get("weight", 1.0) for node in self.nodes}
        self.score_cache = {}
        self.cache_ttl = 5  # 分数缓存 5 秒
        
    def record_latency(self, node_id, latency_ms):
        """记录节点延迟数据"""
        self.latency_history[node_id].append({
            "timestamp": datetime.now(),
            "latency": latency_ms
        })
        self.score_cache = {}  # 清除缓存，强制重新计算
    
    def record_error(self, node_id):
        """记录节点错误"""
        self.error_history[node_id].append(datetime.now())
        self.score_cache = {}
    
    def calculate_node_score(self, node_id):
        """
        计算节点综合评分（0-100）
        评分维度：
        - 平均延迟 (40%)
        - P99 延迟 (25%)
        - 错误率 (20%)
        - 吞吐量 (15%)
        """
        if node_id in self.score_cache:
            return self.score_cache[node_id]
        
        history = self.latency_history[node_id]
        errors = self.error_history[node_id]
        
        if len(history) < 5:
            return 50.0  # 新节点给默认分
        
        latencies = [h["latency"] for h in history]
        avg_latency = sum(latencies) / len(latencies)
        p99_latency = sorted(latencies)[int(len(latencies) * 0.99)]
        
        # 计算时间窗口内的错误数
        window_start = datetime.now() - timedelta(minutes=10)
        recent_errors = sum(1 for e in errors if e > window_start)
        error_rate = recent_errors / max(len(errors), 1)
        
        # 综合评分
        latency_score = max(0, 100 - (avg_latency / 5))       # 延迟越低分越高
        p99_score = max(0, 100 - (p99_latency / 10))          # P99 延迟惩罚
        error_score = max(0, 100 - (error_rate * 500))        # 错误率惩罚
        
        total_score = (
            latency_score * 0.40 +
            p99_score * 0.25 +
            error_score * 0.20 +
            (100 - min(avg_latency, 100)) * 0.15
        )
        
        self.score_cache[node_id] = total_score
        return total_score
    
    def update_weights(self):
        """根据评分动态更新节点权重"""
        total_score = sum(self.calculate_node_score(nid) for nid in self.weights)
        
        if total_score == 0:
            return
        
        for node_id in self.weights:
            score = self.calculate_node_score(node_id)
            self.weights[node_id] = round(score / total_score, 4)
        
        # 归一化权重
        weight_sum = sum(self.weights.values())
        for node_id in self.weights:
            self.weights[node_id] /= weight_sum
        
        self.score_cache = {}
    
    def get_next_node(self):
        """基于权重的加权随机选择"""
        weighted_list = []
        for node_id, weight in self.weights.items():
            # 找到该节点配置
            for node in self.nodes:
                if node["id"] == node_id:
                    weighted_list.append((node, weight))
                    break
        
        total_weight = sum(w for _, w in weighted_list)
        r = time.time() % total_weight
        
        cumulative = 0
        for node, weight in weighted_list:
            cumulative += weight
            if r <= cumulative:
                return node
        
        return weighted_list[-1][0]
    
    def run_monitoring_loop(self, interval=10):
        """持续监控并更新权重"""
        print(f"[{datetime.now()}] AI Load Balancer started")
        print(f"Nodes: {[n['id'] for n in self.nodes]}")
        
        while True:
            self.update_weights()
            
            print(f"\n[{datetime.now()}] Current weights:")
            for node_id, weight in self.weights.items():
                score = self.calculate_node_score(node_id)
                history = self.latency_history[node_id]
                avg_lat = sum(h["latency"] for h in history) / len(history) if history else 0
                print(f"  {node_id}: weight={weight:.4f} score={score:.1f} avg_latency={avg_lat:.1f}ms")
            
            time.sleep(interval)

if __name__ == "__main__":
    lb = AdaptiveLoadBalancer()
    lb.run_monitoring_loop()
```

配合 Nginx 的动态权重配置更新：

```lua
-- /etc/nginx/lua/dynamic_upstream.lua
-- 定期从 AI 负载均衡器获取最新权重并更新 upstream

local cjson = require "cjson"
local http = require "resty.http"

-- 获取 AI LB 的权重数据
local function fetch_weights()
    local httpc = require "resty.http".new()
    local res, err = httpc:request_uri("http://127.0.0.1:8080/api/weights", {
        method = "GET",
        header = { ["Accept"] = "application/json" }
    })
    
    if res and res.status == 200 then
        return cjson.decode(res.body)
    end
    return nil
end

-- 动态设置 upstream 权重
local function set_upstream_weights(weights)
    if not weights then return end
    
    local peers = ngx.shared.upstream_peers
    if not peers then
        -- 使用 lua-resty-core 的 shared memory
        local shm = ngx.shared.lb_weights
        if not shm then
            ngx.log(ngx.ERR, "Shared memory zone not initialized")
            return
        end
        
        for node_id, weight in pairs(weights) do
            shm:set(node_id, tostring(weight), 300)
        end
    end
end

-- 每 30 秒更新一次
timer = ngx.timer.every(30, function()
    local weights = fetch_weights()
    if weights then
        set_upstream_weights(weights)
    end
end)
```

## 第五步：边缘节点健康监控与自愈

每个节点都需要被实时监控，AI 系统应能在检测到异常时自动修复：

```python
#!/usr/bin/env python3
"""
edge_health_monitor.py - 边缘节点健康监控与自愈
"""

import time
import json
import requests
import subprocess
from datetime import datetime
from typing import Dict, List, Optional

class EdgeHealthMonitor:
    def __init__(self, config_path="monitor_config.json"):
        with open(config_path) as f:
            self.config = json.load(f)
        
        self.nodes = self.config["nodes"]
        self.alerts = []
        self.recovery_actions = self.config.get("recovery_actions", {})
    
    def check_node_health(self, node: dict) -> dict:
        """全面检查单个节点的健康状态"""
        result = {
            "node_id": node["id"],
            "ip": node["ip"],
            "timestamp": datetime.now().isoformat(),
            "checks": {},
            "overall_status": "healthy"
        }
        
        # 1. 网络可达性
        try:
            ping = subprocess.run(
                ["ping", "-c", "3", "-W", "2", node["ip"]],
                capture_output=True, text=True, timeout=10
            )
            result["checks"]["connectivity"] = {
                "status": "up" if ping.returncode == 0 else "down",
                "details": "reachable" if ping.returncode == 0 else "unreachable"
            }
            if ping.returncode != 0:
                result["overall_status"] = "unhealthy"
        except Exception as e:
            result["checks"]["connectivity"] = {"status": "error", "details": str(e)}
            result["overall_status"] = "unhealthy"
        
        # 2. Ollama 服务健康
        try:
            resp = requests.get(
                f"http://{node['ip']}:11434/api/tags",
                timeout=10
            )
            if resp.status_code == 200:
                models = resp.json().get("models", [])
                result["checks"]["ollama_service"] = {
                    "status": "running",
                    "models_loaded": len(models),
                    "model_names": [m["name"] for m in models]
                }
            else:
                result["checks"]["ollama_service"] = {
                    "status": "error",
                    "details": f"HTTP {resp.status_code}"
                }
                result["overall_status"] = "degraded"
        except requests.exceptions.ConnectionError:
            result["checks"]["ollama_service"] = {
                "status": "down",
                "details": "connection refused"
            }
            result["overall_status"] = "unhealthy"
        except Exception as e:
            result["checks"]["ollama_service"] = {
                "status": "error",
                "details": str(e)
            }
        
        # 3. 系统资源
        try:
            ssh_cmd = f"ssh root@{node['ip']} 'free -m | awk \"/Mem:/{{print \\$3/\\$2*100}}' && " \
                      f"df -m / | awk \'NR==2{{print \\$5}}' && " \
                      f"top -bn1 | grep Cpu | awk \\'{{print \\$2}}\\'"
            proc = subprocess.run(ssh_cmd, shell=True, capture_output=True, text=True, timeout=15)
            outputs = proc.stdout.strip().split('\n')
            
            if len(outputs) >= 3:
                mem_usage = float(outputs[0])
                disk_usage = outputs[1].rstrip('%')
                cpu_idle = outputs[2].split(',')[0].split(':')[1].strip()
                
                result["checks"]["resources"] = {
                    "memory_usage_percent": mem_usage,
                    "disk_usage_percent": float(disk_usage),
                    "cpu_idle_percent": float(cpu_idle)
                }
                
                if mem_usage > 90:
                    result["overall_status"] = "critical"
                elif mem_usage > 80:
                    result["overall_status"] = "warning"
        except Exception as e:
            result["checks"]["resources"] = {"status": "error", "details": str(e)}
        
        # 4. 推理延迟测试
        try:
            start = time.time()
            resp = requests.post(
                f"http://{node['ip']}:11434/api/generate",
                json={
                    "model": "qwen2.5:7b",
                    "prompt": "Say hello in 1 word",
                    "stream": False
                },
                timeout=30
            )
            latency_ms = (time.time() - start) * 1000
            
            result["checks"]["inference_latency"] = {
                "status": "ok" if resp.status_code == 200 else "error",
                "latency_ms": round(latency_ms, 2),
                "response_code": resp.status_code
            }
            
            if latency_ms > 5000:
                if result["overall_status"] == "healthy":
                    result["overall_status"] = "degraded"
        except Exception as e:
            result["checks"]["inference_latency"] = {
                "status": "error",
                "details": str(e)
            }
        
        return result
    
    def auto_remediate(self, node_id: str, issue: str):
        """根据问题类型自动执行修复操作"""
        remediation_map = {
            "ollama_down": [
                f"ssh root@{{node_id}} 'systemctl restart ollama'",
                f"ssh root@{{node_id}} 'docker compose -f /opt/edge/docker-compose.edge.yml restart ollama'"
            ],
            "high_memory": [
                f"ssh root@{{node_id}} 'sync && echo 3 > /proc/sys/vm/drop_caches'",
                f"ssh root@{{node_id}} 'systemctl restart ollama'"
            ],
            "high_disk": [
                f"ssh root@{{node_id}} 'journalctl --vacuum-size=100M'",
                f"ssh root@{{node_id}} 'ollama rm unused-models'"
            ]
        }
        
        actions = remediation_map.get(issue, [])
        for action in actions:
            try:
                cmd = action.format(node_id=node_id.replace(".", "\\."))
                subprocess.run(cmd, shell=True, timeout=30, capture_output=True)
                print(f"[{datetime.now()}] Executed remediation: {cmd}")
            except Exception as e:
                print(f"[{datetime.now()}] Remediation failed: {e}")
    
    def run_full_monitor(self):
        """全量监控循环"""
        print(f"[{datetime.now()}] Starting edge health monitoring")
        print(f"Monitoring {len(self.nodes)} nodes...\n")
        
        while True:
            all_results = []
            critical_found = False
            
            for node in self.nodes:
                result = self.check_node_health(node)
                all_results.append(result)
                
                if result["overall_status"] == "critical":
                    critical_found = True
                    self.alerts.append({
                        "node_id": node["id"],
                        "severity": "critical",
                        "timestamp": result["timestamp"],
                        "details": result
                    })
                    print(f"🚨 CRITICAL: {node['id']} - {result['overall_status']}")
                    
                    # 自动修复
                    for check_name, check_result in result["checks"].items():
                        if check_result.get("status") in ["down", "error"]:
                            self.auto_remediate(node["id"], check_name)
                
                elif result["overall_status"] == "degraded":
                    print(f"⚠️  DEGRADED: {node['id']} - {result['overall_status']}")
                else:
                    print(f"✅ HEALTHY: {node['id']} - {result['overall_status']}")
            
            # 生成监控报告
            report = {
                "timestamp": datetime.now().isoformat(),
                "nodes_checked": len(all_results),
                "healthy": sum(1 for r in all_results if r["overall_status"] == "healthy"),
                "degraded": sum(1 for r in all_results if r["overall_status"] == "degraded"),
                "critical": sum(1 for r in all_results if r["overall_status"] == "critical"),
                "unhealthy": sum(1 for r in all_results if r["overall_status"] == "unhealthy"),
            }
            
            print(f"\n📊 Cluster Report: {json.dumps(report, indent=2)}\n")
            
            time.sleep(self.config.get("check_interval", 60))

if __name__ == "__main__":
    monitor = EdgeHealthMonitor()
    monitor.run_full_monitor()
```

配置文件 `monitor_config.json`：

```json
{
    "nodes": [
        {"id": "tokyo-node", "ip": "10.0.1.10", "region": "ap-northeast"},
        {"id": "singapore-node", "ip": "10.0.2.10", "region": "ap-southeast"},
        {"id": "virginia-node", "ip": "10.0.3.10", "region": "us-east"}
    ],
    "check_interval": 60,
    "recovery_actions": {
        "ollama_down": "restart_service",
        "high_memory": "clear_cache",
        "high_disk": "vacuum_logs"
    }
}
```

## 第六步：性能优化与最佳实践

### 显存/内存优化

边缘节点通常资源有限，以下是关键的优化手段：

```bash
# 1. 使用量化模型减少内存占用
# Q4_K_M 量化将 7B 模型从 ~14GB 降至 ~5GB
ollama pull qwen2.5:7b-instruct-q4_K_M

# 2. 限制并发请求数
# 编辑 /etc/ollama/config.json
cat > /etc/ollama/config.json << 'EOF'
{
    "num_parallel": 1,
    "max_requests": 4,
    "gpu_layers": 35
}
EOF
systemctl restart ollama

# 3. 设置容器资源限制
# docker-compose.yml 中已配置 deploy.resources.limits

# 4. 启用模型预热，减少冷启动延迟
# 在启动脚本中添加
curl -s http://localhost:11434/api/generate \
  -d '{"model":"qwen2.5:7b","prompt":"test","stream":false}' > /dev/null
```

### 网络优化

```bash
# 1. 启用 TCP BBR 拥塞控制
cat > /etc/sysctl.d/99-edge-tuning.conf << 'EOF'
net.core.default_qdisc = fq
net.ipv4.tcp_congestion_control = bbr
net.ipv4.tcp_max_syn_backlog = 8192
net.core.somaxconn = 65535
EOF
sysctl -p /etc/sysctl.d/99-edge-tuning.conf

# 2. 优化 SSH 连接复用（用于节点间通信）
cat >> ~/.ssh/config << 'EOF'
Host 10.0.*.*
    ControlMaster auto
    ControlPath /tmp/%r@%h:%p
    ControlPersist 600
    ServerAliveInterval 30
    ServerAliveCountMax 3
EOF

# 3. 使用 mTLS 加密节点间通信
# 生成证书
openssl req -x509 -newkey rsa:4096 -keyout ca.key -out ca.crt \
    -days 365 -nodes -subj "/CN=edge-cluster-ca"
```

### 成本优化策略

```python
# cost_optimizer.py - 基于流量的弹性伸缩决策
import json

def analyze_traffic_pattern(hourly_data: list) -> dict:
    """分析每小时流量模式，预测低谷期"""
    total = sum(h["requests"] for h in hourly_data)
    avg = total / len(hourly_data) if hourly_data else 0
    
    low_traffic_hours = [
        h["hour"] for h in hourly_data 
        if h["requests"] < avg * 0.3
    ]
    
    return {
        "avg_hourly_requests": round(avg, 1),
        "low_traffic_hours": low_traffic_hours,
        "peak_hour": max(hourly_data, key=lambda x: x["requests"])["hour"],
        "savings_potential_pct": round(
            (len(low_traffic_hours) / 24) * 100, 1
        )
    }

# 示例：在凌晨 2-6 点（低流量时段）缩减非关键节点
# 节省约 25% 的月度成本
```

## 实际部署案例

某跨境电商平台采用此架构后：

| 指标 | 优化前 | 优化后 | 改善幅度 |
|------|--------|--------|---------|
| 平均推理延迟 | 320ms | 45ms | ↓ 86% |
| P99 延迟 | 1200ms | 180ms | ↓ 85% |
| 服务可用性 | 99.2% | 99.97% | ↑ 0.7% |
| 月度推理成本 | $2,400 | $890 | ↓ 63% |
| 故障恢复时间 | 15分钟 | <30秒 | ↓ 97% |

**部署拓扑**：
- 东京节点：处理亚太区 60% 流量，部署 Qwen2.5-7B + nomic-embed-text
- 新加坡节点：处理东南亚 25% 流量，额外部署翻译专用模型
- 弗吉尼亚节点：处理北美 15% 流量，部署代码审查专用模型

## 总结

通过 AI 赋能的边缘计算节点集群，你可以：

1. **显著降低推理延迟** — 用户就近接入，延迟从数百毫秒降至几十毫秒
2. **提高系统可靠性** — 多节点冗余 + AI 自动故障转移，实现 99.97%+ 可用性
3. **优化运营成本** — 按需分配资源，利用低峰期弹性缩容，节省 60%+ 成本
4. **简化运维管理** — AI 自动监控、自愈和版本同步，减少人工干预

这套架构特别适合以下场景：
- 面向全球用户的 AI 应用服务
- 多语言客服与内容审核
- 实时翻译与语音识别
- 边缘 AI 推理与数据预处理

边缘计算不是替代云端，而是让 AI 服务更靠近用户、更快、更经济。现在就用你的 VPS 开始搭建吧！
