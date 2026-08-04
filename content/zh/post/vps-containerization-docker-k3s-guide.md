---
title: "VPS 容器化部署实战：从 Docker 到 K3s 的完整指南"
description: "从零开始学习 VPS 容器化部署，掌握 Docker 基础、Docker Compose 编排，以及轻量级 Kubernetes K3s 的完整部署流程，让应用管理更高效、更可靠"
date: 2026-08-04
lastmod: 2026-08-04
slug: "vps-containerization-docker-k3s-guide"
image: /images/posts/vps-containerization-docker-k3s-guide/featured.png
tags: ["Docker", "K3s", "容器化", "VPS", "Kubernetes", "DevOps", "部署", "编排"]
categories: ["容器化部署"]
aliases: [/zh/post/vps-containerization-docker-k3s-guide/]
---

## 引言

在 VPS 上运行应用，传统方式是直接在服务器上安装软件、配置环境。但随着应用复杂度增加，这种方式带来了诸多问题：环境不一致、依赖冲突、部署困难、扩展性差。容器化技术正是为了解决这些问题而生。

Docker 和 Kubernetes（及其轻量级发行版 K3s）已经成为云原生时代的标准工具。本文将带你从零开始，学习如何在 VPS 上实现完整的容器化部署，从基础的 Docker 容器管理，到多容器编排，再到轻量级 Kubernetes 集群的搭建。

## 为什么选择容器化？

容器化相比传统部署有以下核心优势：

- **环境一致性**：开发、测试、生产环境完全一致，消除"在我机器上能跑"的问题
- **快速部署**：镜像一键部署，秒级启动，支持滚动更新和快速回滚
- **资源隔离**：每个容器独立运行，互不影响，资源配额可控
- **横向扩展**：轻松复制多个容器实例，应对流量高峰
- **生态丰富**：Docker Hub 和各大云厂商提供海量预构建镜像

## 第一阶段：Docker 基础部署

### 1.1 安装 Docker

```bash
# Ubuntu/Debian
curl -fsSL https://get.docker.com | sh

# 添加当前用户到 docker 组（避免每次用 sudo）
sudo usermod -aG docker $USER

# 重启生效
newgrp docker

# 验证安装
docker --version
docker info
```

### 1.2 运行第一个容器

```bash
# 拉取并运行 Nginx
docker run -d \
  --name nginx \
  -p 80:80 \
  -v /opt/nginx/html:/usr/share/nginx/html:ro \
  nginx:alpine

# 查看运行状态
docker ps

# 访问服务
curl http://localhost
```

### 1.3 Docker 常用命令速查

```bash
# 镜像管理
docker images          # 查看本地镜像
docker pull nginx      # 拉取镜像
docker rmi nginx       # 删除镜像

# 容器管理
docker ps -a           # 查看所有容器
docker stop/nginx      # 停止容器
docker start nginx     # 启动容器
docker rm nginx        # 删除容器
docker logs nginx      # 查看日志

# 进入容器
docker exec -it nginx bash

# 资源限制
docker run -d --name app \
  --cpus="1.5" \
  --memory="512m" \
  -p 8080:80 \
  myapp:latest
```

## 第二阶段：Docker Compose 多容器编排

### 2.1 什么是 Docker Compose？

Docker Compose 是用于定义和运行多容器 Docker 应用的工具。通过一个 YAML 文件配置应用栈，一条命令即可启动所有服务。

### 2.2 典型应用栈配置

以"网站 + 数据库 + 缓存"为例：

```yaml
# docker-compose.yml
version: '3.8'

services:
  web:
    image: nginx:alpine
    ports:
      - "80:80"
    volumes:
      - ./html:/usr/share/nginx/html:ro
    depends_on:
      - app
    networks:
      - frontend

  app:
    build: ./app
    ports:
      - "3000:3000"
    environment:
      - DB_HOST=db
      - DB_PASSWORD=${DB_PASSWORD}
    depends_on:
      - db
      - redis
    networks:
      - frontend
      - backend

  db:
    image: postgres:15-alpine
    volumes:
      - postgres_data:/var/lib/postgresql/data
    environment:
      - POSTGRES_PASSWORD=${DB_PASSWORD}
      - POSTGRES_DB=myapp
    networks:
      - backend

  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data
    networks:
      - backend

volumes:
  postgres_data:
  redis_data:

networks:
  frontend:
  backend:
```

### 2.3 Compose 常用命令

```bash
# 启动所有服务
docker compose up -d

# 查看服务状态
docker compose ps

# 查看日志
docker compose logs -f app

# 重启服务
docker compose restart app

# 停止并删除容器（保留数据卷）
docker compose down

# 重建镜像并重启
docker compose up -d --build
```

## 第三阶段：K3s 轻量级 Kubernetes

### 3.1 什么是 K3s？

K3s 是 Rancher 推出的轻量级 Kubernetes 发行版，专为边缘计算、IoT 和 VPS 场景设计：

- 单一二进制文件，安装包仅 60MB
- 内存占用低至 256MB
- 内置 Traefik Ingress 和 ServiceLB
- 完全兼容 Kubernetes API

### 3.2 一键安装 K3s

```bash
# 单节点 K3s 服务器
curl -sfL https://get.k3s.io | sh -

# 查看节点状态
sudo k3s kubectl get nodes
sudo k3s kubectl get pods -A

# 配置 kubectl 别名
echo 'alias k=k3s kubectl' >> ~/.bashrc
source ~/.bashrc

# 验证
k get nodes
```

### 3.3 高可用 K3s 集群

对于生产环境，建议使用多节点高可用架构：

```bash
# 配置 HTTPS 负载均衡（HAProxy + Keepalived）
# 参考：https://rancher.com/docs/k3s/latest/en/advanced/#high-availability-with-an-external-database

# 生成 token
sudo cat /etc/rancher/k3s/token

# 在 Worker 节点加入集群
curl -sfL https://get.k3s.io | K3S_URL=https://LOADBALANCER:6443 K3S_TOKEN=xxx sh -
```

### 3.4 Kubernetes 核心概念

```
Pod          # 最小部署单元，包含一个或多个容器
Deployment   # 管理 Pod 的副本数和更新策略
Service      # 暴露 Pod 的网络访问
ConfigMap    # 外部化配置
Secret       # 敏感信息加密存储
Ingress      # HTTP 路由和 SSL 终止
PV/PVC       # 持久化存储
```

### 3.5 实战：部署一个完整应用栈

```yaml
# k3s-app.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web-app
spec:
  replicas: 2
  selector:
    matchLabels:
      app: web-app
  template:
    metadata:
      labels:
        app: web-app
    spec:
      containers:
      - name: nginx
        image: nginx:alpine
        ports:
        - containerPort: 80
        resources:
          limits:
            memory: "128Mi"
            cpu: "250m"
---
apiVersion: v1
kind: Service
metadata:
  name: web-app-service
spec:
  selector:
    app: web-app
  ports:
  - port: 80
    targetPort: 80
  type: ClusterIP
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: web-app-ingress
  annotations:
    nginx.ingress.kubernetes.io/rewrite-target: /
spec:
  rules:
  - host: myapp.example.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: web-app-service
            port:
              number: 80
```

```bash
# 应用配置
kubectl apply -f k3s-app.yaml

# 查看状态
kubectl get pods
kubectl get svc
kubectl get ingress

# 滚动更新
kubectl set image deployment/web-app nginx=nginx:1.25-alpine
```

## 第四阶段：生产环境最佳实践

### 4.1 资源限制与质量保障

```yaml
resources:
  requests:
    memory: "128Mi"
    cpu: "100m"
  limits:
    memory: "256Mi"
    cpu: "500m"
```

### 4.2 健康检查

```yaml
livenessProbe:
  httpGet:
    path: /healthz
    port: 8080
  initialDelaySeconds: 10
  periodSeconds: 30
readinessProbe:
  httpGet:
    path: /ready
    port: 8080
  initialDelaySeconds: 5
  periodSeconds: 10
```

### 4.3 持久化存储

```yaml
# K3s 自带 local-path 存储类
kubectl get storageclass

# PVC 示例
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: app-data
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: local-path
  resources:
    requests:
      storage: 5Gi
```

### 4.4 备份与恢复

```bash
# 备份 etcd（K3s 自动管理）
sudo /usr/local/bin/k3s-etcd-snapshot save

# 查看备份
sudo /usr/local/bin/k3s-etcd-snapshot ls

# 恢复
sudo /usr/local/bin/k3s-etcd-snapshot restore /path/to/snapshot.db
```

## 第五阶段：选择适合你的方案

| 场景 | 推荐方案 | 理由 |
|------|----------|------|
| 单应用部署 | Docker + Docker Compose | 简单直观，开箱即用 |
| 多服务微服务 | K3s | 原生服务发现、负载均衡、自动伸缩 |
| 边缘计算/IoT | K3s | 资源占用极低 |
| 开发测试环境 | Docker Compose | 快速搭建、易于销毁重建 |
| 生产环境 | K3s 高可用集群 | 故障恢复、滚动更新、版本管理 |

## 结语

容器化是 VPS 运维的必备技能。从 Docker 到 K3s，你可以根据项目复杂度和团队规模选择合适的方案。记住：**简单的事情简单做，复杂的事情有框架**。

对于个人项目和小型团队，Docker Compose 通常足够；当应用规模增长、需要多环境部署和自动伸缩时，K3s 提供了平滑的升级路径。

## 参考资源

- Docker 官方文档：https://docs.docker.com/
- Docker Compose 文档：https://docs.docker.com/compose/
- K3s 文档：https://docs.k3s.io/
- Kubernetes 官方文档：https://kubernetes.io/docs/
