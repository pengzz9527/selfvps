---
title: "VPS 上部署生产级 LLM 推理服务：自动伸缩架构指南"
subtitle: "Deploying Production LLM Inference on VPS with Auto-Scaling Architecture"
date: 2026-07-27
draft: false
tags: ["AI", "LLM", "推理", "自动伸缩", "VPS", "Docker", "Kubernetes", "成本优化"]
categories: ["AI + VPS"]
image: /images/posts/ai-llm-inference-vps-auto-scaling/featured.png
description: "在自建 VPS 上构建生产级大语言模型推理服务的完整指南，涵盖架构设计、自动伸缩策略、成本优化技术和实际部署模式。"
aliases: [/zh/post/ai-llm-inference-vps-auto-scaling/]
---

## 引言

在自己的 VPS 上部署大语言模型（LLM）推理服务，意味着**完全掌控数据**、**保护隐私**和**降低长期成本**——但随着流量增长，运维复杂性也会迅速增加。本文提供了一个从入门到实践的完整指南，帮助您在资源受限的 VPS 环境中构建**具备智能自动伸缩和成本控制能力的生产级 LLM 推理系统**。

无论您是在构建业务关键型应用、定制 AI 助手，还是为社区提供开源模型的托管服务，本文将帮助您平衡**性能**、**可靠性**与**成本**这三个核心目标。

## 为什么选择 VPS 自托管 LLM 推理？

在选择云服务还是自建之前，了解两者的优劣至关重要：

| 对比维度 | 云端 API（OpenAI、Anthropic 等） | VPS 自托管 |
|----------|----------------------------------|------------|
| 数据隐私 | 数据发送第三方机构 | 数据完全本地，无外泄风险 |
| 成本预测 | 按 token 计费，难以预估 | 固定基础设施成本，支出可预测 |
| 自定义能力 | 受限于服务商选项 | 完全可控模型、量化方式及优化策略 |
| 延迟 | 依赖网络质量 | 本地访问，延迟极低 |
| 吞吐量限制 | 服务商设置配额 | 依硬件配置，无硬性上限 |
| 模型选择 | 仅限服务商提供的模型 | 任意开源模型，包括微调版本 |

对于涉及敏感数据、高并发请求或专用领域模型的工作场景，**自建不仅是选择而是必须**。但在单台有限资源的 VPS 上实现弹性伸缩，需要精心设计的架构决策。

## 架构图解

本系统采用分层微服务风格，专为单机环境下的弹性和韧性而设计：

```
┌─────────────────────────────────────────────────────────────┐
│                    客户端应用                               │
│   (Web 界面、移动应用、第三方服务、定时任务)                 │
└──────────────────────────────┬──────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────┐
│            负载均衡器与请求路由                             │
│        (NGINX/Traefik 限流与认证功能)                      │
└──────────────────────────────┬──────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────┐
│              API 网关服务                                   │
│  (健康检查、请求验证、指标采集、日志记录)                   │
└──────────────────────────────┬──────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────┐
│       推理控制器 + 自动伸缩引擎                              │
│  (管理 Worker 实例，监控 GPU/CPU/内存，触发扩缩容)           │
└──────────────────────────────┬──────────────────────────────┘
          ┌────────────────────┼────────────────────┐        │
          ▼                    ▼                    ▼        │
┌──────────────┐      ┌──────────────┐      ┌──────────────┐  │
│ 推理 Worker 1│      │ 推理 Worker 2│      │ 推理 Worker 3│  │
│  (vLLM)      │      │   (Ollama)   │      │ (TensorRT)   │  │
└──────────────┘      └──────────────┘      └──────────────┘  │
          ▲                    │                             │
          └────────────────────┼─────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────┐
│          模型存储与缓存层                                    │
│  (本地磁盘、SSD 缓存、可选远程存储)                        │
└─────────────────────────────────────────────────────────────┘
```

### 核心设计原则

1. **无状态 Worker**: 每个推理容器均可替换，支持在同一主机内水平扩展。

2. **解耦的伸缩逻辑**: 监控与决策分离，使健康指标与伸缩策略可独立演进。

3. **资源隔离**: Docker 容器设置明确的 CPU/内存上限，避免"邻域效应"，确保公平的资源共享。

4. **可观测性优先**: 所有组件输出结构化日志、指标和链路追踪，完整可见系统行为。

5. **渐进式发布**: 新版本模型可与旧版本并行运行，逐步切换流量，更新时无停机。

## 推理引擎选型

根据您的工作负载特性、模型格式和性能需求选择合适的推理引擎：

### vLLM（高吞吐服务）

**适用场景**: 高吞吐批处理、长上下文模型、生产级工作负载

**优势**:
- PagedAttention 内存管理实现高吞吐和低内存占用
- 支持多卡张量并行推理
- 连续批处理提升 GPU 利用率
- OpenAPI 兼容接口

**劣势**:
- 相比其他引擎需要更多内存
- 主要加速于 GPU（CPU 模式功能有限）

```yaml
# docker-compose-vllm.yml
version: '3.8'
services:
  vllm-engine:
    image: vllm/vllm-openai:latest
    ports:
      - "8000:8000"
    volumes:
      - models:/models
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [compute, utility]
        limits:
          memory: 32G
    environment:
      - VLLM_HOST=0.0.0.0
      - VLLM_PORT=8000
      - MODEL_NAME=qwen/qwen-7b-chat
```

### Text Generation Inference (TGI)

**适用场景**: Rust 构建的生产环境、Docker 为主的部署流程

**优势**:
- Hugging Face 出品，生产环境验证过
- 支持分片并行化部署多 GPU
- 高效 Token 生成，支持流式输出
- Docker 原生部署

**劣势**:
- 配置曲线较陡峭
- 基线内存占用较高

### Ollama（灵活易用）

**适用场景**: 快速开发、小模型、CPU/GPU 混合负载

**优势**:
- 极简设置（`ollama run llama3`）
- 自动模型下载与缓存
- RESTful API 配合 WebUI
- 纯 CPU 机器也能良好运行

**劣势**:
- 相比 vLLM/TGI 吞吐量较低
- 高并发生产环境优化不足

### TensorRT-LLM（NVIDIA 生态优化）

**适用场景**: NVIDIA GPU 优化部署，追求极致性能

**优势**:
- NVIDIA GPU 上吞吐量最高
- 高级量化支持（INT8、FP8）
- 与 CUDA 深度集成

**劣势**:
- 仅限 NVIDIA 硬件
- 构建和部署流程更复杂

## 生产部署模式

对于大多数 VPS 场景，我推荐**混合方案**：对 GPU 专属节点上的重型模型使用 vLLM，在通用节点上用 Ollama 处理较小模型，所有入口统一经过反向代理和 API 网关。

### 完整的 docker-compose 生产栈

以下是一个生产就绪的 `docker-compose.yml`，编排了所有核心组件：

```yaml
# docker-compose-production.yml
version: '3.8'

services:
  # ====================
  # 反向代理层
  # ====================
  nginx-proxy:
    image: traefik:v2.10
    command:
      - "--api.insecure=true"
      - "--providers.docker=true"
      - "--providers.docker.exposedbydefault=false"
      - "--entrypoints.web.address=:80"
      - "--entrypoints.websecure.address:443"
    ports:
      - "80:80"
      - "443:443"
      - "8080:8080"
    volumes:
      - "/var/run/docker.sock:/var/run/docker.sock:ro"
      - "./traefik.yml:/etc/traefik/traefik.yml"
      - ./traefik-certs:/certs
    restart: unless-stopped

  # ====================
  # API 网关与认证
  # ====================
  api-gateway:
    build: ./api-gateway
    image: selfvps/api-gateway:latest
    ports:
      - "8081:8081"
    environment:
      - VLLM_ENDPOINT=http://vllm-engine:8000
      - OLLAMA_ENDPOINT=http://ollama:11434
      - JWT_SECRET=***
      - RATE_LIMIT=1000/hr
    depends_on:
      - vllm-engine
      - ollama
    restart: unless-stopped

  # ====================
  # 推理引擎
  # ====================
  vllm-engine:
    image: vllm/vllm-openai:latest
    command: ["--model", "mistralai/Mistral-7B-Instruct-v0.3", 
              "--port", "8000", "--host", "0.0.0.0",
              "--max-model-len", "32768"]
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [compute, utility]
        limits:
          memory: 24G
    volumes:
      - ./models:/models
    environment:
      - VLLM_HOST=0.0.0.0
      - VLLM_PORT=8000
    restart: unless-stopped

  ollama:
    image: ollama/ollama:latest
    ports:
      - "11434:11434"
    volumes:
      - ./ollama-storage:/root/.ollama
    environment:
      - OLLAMA_HOST=0.0.0.0
      - OLLAMA_PORT=11434
    restart: unless-stopped

  # ====================
  # 自动伸缩控制器
  # ====================
  autoscaler:
    image: selfvps/autoscaler:latest
    command: [--scale-down-interval=30s, --scale-up-threshold=0.7]
    environment:
      - SCALING_METRICS_URL=http://prometheus:9090
      - VLLM_CONTAINER_NAME=vllm-engine
      - MIN_WORKERS=1
      - MAX_WORKERS=4
      - COOLDOWN_PERIOD=300s
    depends_on:
      - prometheus
    restart: unless-stopped

  # ====================
  # 监控栈
  # ====================
  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
    restart: unless-stopped

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=***
    restart: unless-stopped

volumes:
  models:
  ollama-storage:
  prometheus-data:
```

## 自动伸缩实现

VPS 规模推理的核心挑战在于如何在**资源争用**和**请求延迟**之间取得平衡。在 GPU 内存有限的单机上，启动过多 Worker 会导致资源竞争，而过少则引起排队延迟。

### 伸缩策略概述

我建议采用**三层自适应伸缩机制**：

1. **短期伸缩（秒级）**：基于队列长度和等待时间。如果请求处理速度跟不上到达速度，立即启动额外 Worker。

2. **中期伸缩（分钟级）**：基于 GPU 利用率百分比。如果平均 GPU 利用率持续超过 70%，逐步增加容量。

3. **长期伸缩（小时/天级）**：基于需求预测。利用历史模式在预计流量高峰前预加载 Worker。

### Python 自动伸缩器示例

以下是简化的自动伸缩器示例，监控 GPU 内存、请求延迟和队列深度，然后触发扩缩容决策：

```python
#!/usr/bin/env python3
"""
LLM 推理自动伸缩器（VPS 部署版）
监控 GPU 内存、请求延迟和队列深度
触发扩缩容决策
"""

import subprocess
import time
import json
import psutil
from collections import deque
from datetime import datetime, timedelta

class InferenceAutoscaler:
    def __init__(self, min_workers=1, max_workers=4, 
                 gpu_threshold=0.7, cooldown=300):
        self.min_workers = min_workers
        self.max_workers = max_workers
        self.gpu_threshold = gpu_threshold  # 70% 利用率
        self.cooldown = cooldown  # 决策间隔秒数
        self.last_decision = None
        self.latency_history = deque(maxlen=100)
    
    def get_gpu_memory_info(self):
        """使用 nvidia-smi 获取 GPU 内存使用情况"""
        try:
            result = subprocess.run(
                ['nvidia-smi', '--query-gpu=index,memory.used,memory.total', 
                 '--format=csv,noheader,nounits'],
                capture_output=True, text=True, timeout=10
            )
            lines = result.stdout.strip().split('\n')
            if len(lines) >= 1:
                used, total = map(int, lines[0].split(','))
                return used / total if total > 0 else 0
        except Exception as e:
            print(f"GPU 查询错误: {e}")
        return None
    
    def get_worker_status(self):
        """检查当前正在运行的推理 Worker 数量"""
        try:
            result = subprocess.run(
                ['docker', 'ps', '--filter', 'name=vllm-engine', 
                 '--format', '{{.Names}}'],
                capture_output=True, text=True, timeout=5
            )
            workers = [w.strip() for w in result.stdout.strip().split('\n') if w.strip()]
            return len(workers), workers
        except Exception as e:
            print(f"Docker 检查错误: {e}")
            return 0, []
    
    def should_scale_up(self, current_workers):
        """判断是否需要扩容"""
        if current_workers >= self.max_workers:
            return False
            
        now = time.time()
        if self.last_decision and (now - self.last_decision) < self.cooldown:
            return False
        
        gpu_util = self.get_gpu_memory_info()
        if gpu_util is None:
            cpu_load = psutil.getloadaverage()[0]
            avg_cpu_per_worker = cpu_load / max(current_workers, 1)
            if avg_cpu_per_worker > self.gpu_threshold * 4:
                return True
            return False
        
        if gpu_util > self.gpu_threshold:
            return True
        
        # 检查延迟和队列（占位符）
        # 生产环境中应查询 Prometheus 或其他指标端点
        
        return False
    
    def should_scale_down(self, current_workers):
        """判断是否可以缩减"""
        if current_workers <= self.min_workers:
            return False
            
        now = time.time()
        if self.last_decision and (now - self.last_decision) < self.cooldown:
            return False
        
        # 只有在长时间稳定时才允许缩容
        gpu_util = self.get_gpu_memory_info()
        if gpu_util and gpu_util < self.gpu_threshold * 0.5:
            return True
        
        return False
    
    def make_scaling_decision(self, current_workers):
        """执行最终的伸缩决策"""
        now = time.time()
        
        if self.should_scale_up(current_workers):
            new_count = current_workers + 1
            print(f"[{datetime.now()}] 扩容: {current_workers} → {new_count} 个 Worker")
            self.trigger_scale_up(new_count)
            self.last_decision = now
            return new_count
            
        elif self.should_scale_down(current_workers):
            new_count = current_workers - 1
            print(f"[{datetime.now()}] 缩容: {current_workers} → {new_count} 个 Worker")
            self.trigger_scale_down(new_count)
            self.last_decision = now
            return new_count
        
        return current_workers
    
    def trigger_scale_up(self, target_count):
        """扩容执行（调用 Docker Compose 或 Kubernetes）"""
        print(f"正在扩容至 {target_count} 个 Worker...")
        pass  # 实际实现
    
    def trigger_scale_down(self, target_count):
        """缩容执行"""
        print(f"正在缩容至 {target_count} 个 Worker...")
        pass  # 实际实现
    
    def monitor_loop(self, interval=30):
        """主监控循环"""
        print("启动自动伸缩器监控...")
        while True:
            current_workers, worker_names = self.get_worker_status()
            print(f"当前 Worker 数: {current_workers}")
            
            new_count = self.make_scaling_decision(current_workers)
            
            time.sleep(interval)

if __name__ == '__main__':
    scaler = InferenceAutoscaler(min_workers=1, max_workers=4, gpu_threshold=0.7)
    try:
        scaler.monitor_loop(interval=30)
    except KeyboardInterrupt:
        print("\n自动伸缩器已停止")
```

### Docker 基础的手动伸缩脚本

对于没有 Kubernetes 的简单部署，可以使用 shell 脚本辅助：

```bash
#!/bin/bash
THRESHOLD=70
CURRENT=$(docker stats --no-stream --format "{{.Name}} {{.CPUPerc}}" | grep vllm | awk '{sum+=$2} END {print sum/NR}')

if (( $(echo "$CURRENT > $THRESHOLD" | bc -l) )); then
    COMPOSE_COUNT=$(docker compose ps vllm-engine | wc -l)
    if [ $COMPOSE_COUNT -lt 4 ]; then
        docker compose up -d --scale vllm-engine=$((COMPOSE_COUNT + 1))
        echo "已扩容至 $((COMPOSE_COUNT + 1)) 个 Worker"
    fi
fi
```

## 成本优化技巧

在 VPS 上运行 LLM 推理涉及计算、内存和存储的多重成本。以下策略帮助优化开支：

### 1. 模型量化与降维

使用量化版本减少内存占用并提高吞吐：

```bash
# GGUF 格式适合 CPU 推理
ollama pull qwen:7b-q4_0  # 4-bit 量化版本 (~4GB vs 全精度 ~14GB)

# 或 GPU 友好的 AWQ/GPTQ 量化格式
ollama pull codestarcoder/starcodercode-15b-awq
```

量化通常将内存占用减少 50-75%，对大多数推理任务的质量影响很小。

### 2. 动态批大小调整

根据可用 GPU 内存和请求模式调整批量大小：

```bash
# vLLM 配置中使用动态批处理
--enable-pipelined-scheduler
--max-num-seqs-per-batch 64  # 根据您的 GPU VRAM 调整
```

### 3. 闲置资源管理

在低峰期自动缩容以节省成本：

```yaml
# cron 脚本：每日夜间自动缩容
0 8 * * * /usr/local/bin/vps-autoscale --scale-down --min 1
0 20 * * * /usr/local/bin/vps-autoscale --scale-up --max 4
```

### 4. 模型缓存策略

实施激进的模型加载缓存以避免重复磁盘 I/O：

```bash
# 引导时预加载常用模型
sudo systemctl enable ollama-preload.service

# SSD 高速缓存目录
mount -o noatime,discard /dev/ssd0 /var/ollama-cache
```

### 5. Spot 实例考量

如果使用云 VPS 提供商提供的 Spot/抢占式实例：

- 在 Spot 实例启动期间安排模型预热
- 实现中断后的检查点和恢复逻辑
- 跨多实例构建冗余以处理抢占

### 成本对比表

| 方案 | 月估算成本(典型使用) | 吞吐量(tokens/sec) |
|------|---------------------|-------------------|
| 云端 API(按用量付费) | $150-$500+ | 受配额限制 |
| 单 GPU(VPS) | $100-$300 + 电费 | 50-200 tokens/sec |
| 多 GPU 集群(3 卡) | $300-$900 + 电费 | 300-800 tokens/sec |
| CPU 仅(量化版) | $30-$80 + 电费 | 5-20 tokens/sec |
| 混合(热路径 GPU，冷路径 CPU) | $80-$200 + 电费 | 混合 |

*注：成本随地区、硬件规格和使用模式而异*

## 性能优化技巧

除了基本部署，以下高级技术能从您的 VPS 中榨取每一分性能：

### 内核和操作系统级优化

```bash
# 开启透明 Huge Pages 改善内存性能
echo always > /sys/kernel/mm/transparent_hugepage/enabled

# 优化网络栈以降低推理延迟
sysctl -w net.core.somaxconn=65535
sysctl -w net.ipv4.tcp_slow_start_after_idle=0

# 为推理进程绑定 CPU 核
numactl --cpunodebind=0 --membind=0 python inference_worker.py
```

### Docker 资源配置优化

```yaml
deploy:
  resources:
    limits:
      cpus: '4.0'
      memory: 32g
    reservations:
      cpus: '2.0'
      memory: 16g
      devices:
        - driver: nvidia
          count: 1
          capabilities: [compute, utility]
```

### 推理特定优化

1. **Flash Attention**: 如模型和框架支持，启用此优化
2. **KV Cache 管理**: 配置合适的缓存大小以平衡内存和速度
3. **推测解码**: 用小而快的模型起草响应，再由大而慢的模型验证
4. **连续批处理**: 保持 GPU 满负荷处理多个请求

## 安全考虑

暴露 LLM 端到公共网络时，安全至关重要：

```nginx
# NGINX 安全配置示例
location / {
    add_header X-Frame-DENY always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    
    # 边缘层限流
    limit_req zone=req_rate burst=5 nodelay;
    
    # 身份验证
    auth_basic "Restricted";
    auth_basic_user_file /etc/nginx/.htpasswd;
}
```

关键安全实践：
- **API 认证**: 所有端点要求 API Key 或 JWT 令牌
- **速率限制**: 在入口层防止滥用和 DDoS 攻击
- **输入过滤**: 清理用户输入，防范提示注入
- **模型访问控制**: 限制不同用户可调用的模型
- **审计日志**: 记录所有推理请求，用于合规和调试
- **网络隔离**: 推理工置于内部网络，仅通过网关访问

## 实施清单

✅ [ ] **基础设施规划**: 评估 VPS 规格（RAM、GPU、磁盘 I/O）是否满足模型需求  
✅ [ ] **模型选择**: 根据工作负载选择合适的模型（量化 vs 全精度）  
✅ [ ] **容器化封装**: 创建带固定依赖和基础镜像的 Docker 镜像  
✅ [ ] **编排设置**: 配置 docker-compose 或 Kubernetes 清单，设定资源限制  
✅ [ ] **反向代理**: 设置 Traefik/NGINX，完成 TLS 终止和健康检查  
✅ [ ] **监控栈集成**: 整合 Prometheus、Grafana 和告警规则  
✅ [ ] **伸缩器配置**: 定义伸缩阈值、冷却时间和动作钩子  
✅ [ ] **安全加固**: 实现认证、限流和审计日志  
✅ [ ] **备份策略**: 定期备份模型快照和配置版本控制  
✅ [ ] **文档编写**: 创建常见故障场景的操作手册和恢复程序  

## 真实场景示例

### 场景 1: 客户支持聊天机器人

- **需求**: 低延迟（<500ms）、中等并发（50-100 RPM）、高可用性
- **配置**: 2 个 vLLM Worker 运行在 24GB GPU 上，高峰期自动扩容至 4 个，7B 参数模型
- **成本**: 约 $150/月（含 VPS 和电力）
- **优势**: 个性化回复无需将客户数据发送至第三方 API

### 场景 2: 企业内部知识库助手

- **需求**: 通过 RAG 访问公司文档，优先级低于面向 Web 的应用
- **配置**: 1 个 Ollama Worker 运行在 CPU-only 节点，量化 Qwen-7B 模型，集成 Pinecone 向量存储
- **成本**: 约 $30/月（共享 VPS）
- **优势**: 数据主权完整，无外部依赖

### 场景 3: 面向社区的公共 API 服务

- **需求**: 高吞吐量、需求波动大、可能遇到流量洪峰
- **配置**: 多节点集群（3 台 VPS），每台运行 vLLG，全局负载均衡器，跨节点自动伸缩
- **成本**: 约 $600/月
- **优势**: 弹性容量适应不可预测的流量模式

## 结论

在自托管 VPS 上构建生产级的 LLM 推理服务完全可行，前提是做出正确的架构选择。通过实现**无状态的容器化 Worker**、**智能的自动伸缩**和**全面的可观测性**，您可以获得一个在性能、可靠性和成本之间取得良好平衡的系统。

最重要的经验是：**渐进式改进优于完美规划**。从一个基础的单 Worker 部署开始，在实际流量下测量其表现，然后根据实际需求逐步添加伸缩、监控和优化功能。这种方法将 upfront 风险降至最低，同时确保每次架构改进都解决了实际痛点而非理论假设。

随着 LLM 技术的不断发展，这里阐述的原则——容器化、资源感知、可观测性和渐进式伸缩——将继续成为成功自托管推理部署的基础。