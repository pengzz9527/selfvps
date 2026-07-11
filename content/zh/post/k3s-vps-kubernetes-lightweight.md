---
title: "在 VPS 上部署轻量级 K3s Kubernetes 集群 — 边缘计算与微服务架构完全指南"
date: 2026-07-11
description: "从零开始在 VPS 上搭建 K3s Kubernetes 集群，实现容器编排、服务网格和自动化部署。相比传统 K8s 节省 90% 资源开销，单核 VPS 即可运行。"
tags: ["Kubernetes", "K3s", "容器编排", "DevOps", "VPS优化", "边缘计算", "微服务"]
categories: ["Kubernetes", "基础设施"]
image: "/images/posts/k3s-vps-kubernetes-lightweight/featured.png"
draft: false
---

## 为什么选择 K3s？

在传统观念中，Kubernetes 需要至少 3 台节点、每台 4GB+ 内存才能运行。但对于个人开发者、小团队或边缘计算场景，这种规模既不经济也不必要。**K3s**（Kubernetes light）由 Rancher Labs 开发，将完整的 Kubernetes 功能压缩到一个不到 100MB 的二进制文件中，资源占用降低 90% 以上。

| 特性 | 传统 Kubernetes | K3s |
|------|----------------|-----|
| 最小内存需求 | 4GB+ | 512MB |
| 安装包大小 | ~500MB | <100MB |
| 组件数量 | 7+ 独立组件 | 1 个二进制文件 |
| etcd 依赖 | 必须 | 内置 SQLite 可选 |
| 适用场景 | 数据中心 | VPS/边缘/IoT |

## 环境准备

### 系统要求

- **操作系统**: Ubuntu 22.04 LTS / Debian 12（推荐）
- **CPU**: 至少 1 核（2 核推荐）
- **内存**: 512MB 最低，1GB 推荐
- **磁盘**: 10GB 可用空间
- **网络**: 开放端口 6443（API Server）、80/443（Ingress）

### 初始化脚本

```bash
# 更新系统
sudo apt update && sudo apt upgrade -y

# 安装必要工具
sudo apt install -y curl wget apt-transport-https ca-certificates

# 禁用 swap（K3s 要求）
sudo swapoff -a
sudo sed -i '/ swap / s/^/#/' /etc/fstab
```

## 安装 K3s

### 单节点服务器模式（最快上手）

```bash
# 一键安装 K3s 服务器
curl -sfL https://get.k3s.io | sh -

# 验证安装
sudo systemctl status k3s
kubectl get nodes
kubectl get pods -n kube-system
```

安装完成后，kubeconfig 自动保存在 `/etc/rancher/k3s/k3s.yaml`，kubectl 已配置好：

```bash
# 测试集群
kubectl cluster-info
kubectl get svc --all-namespaces
```

### 多节点集群模式

#### 主节点安装

```bash
# 获取安装令牌
export K3S_TOKEN=my-secret-token

# 安装为主节点
curl -sfL https://get.k3s.io | sh -s - server \
  --cluster-init \
  --token ${K3S_TOKEN} \
  --disable traefik
```

#### 工作节点加入

```bash
# 在工作节点上执行
export K3S_TOKEN=my-secret-token
export K3S_URL=https://<MASTER_IP>:6443

curl -sfL https://get.k3s.io | sh -s - agent \
  --server ${K3S_URL} \
  --token ${K3S_TOKEN}
```

## 核心组件配置

### 1. 配置 kubectl 本地访问

```bash
# 复制配置文件到用户目录
mkdir -p ~/.kube
sudo cp /etc/rancher/k3s/k3s.yaml ~/.kube/config
sudo chown $(whoami):$(whoami) ~/.kube/config

# 设置别名
echo 'alias k="kubectl"' >> ~/.bashrc
echo 'alias kubectl="k3s kubectl"' >> ~/.bashrc
source ~/.bashrc
```

### 2. 配置 Traefik Ingress Controller

K3s 默认内置 Traefik，但建议自定义配置以获得更好的性能：

```yaml
# configs/traefik-config.yaml
apiVersion: helm.cattle.io/v1
kind: HelmChartConfig
metadata:
  name: traefik
  namespace: kube-system
spec:
  valuesContent: |-
    ports:
      web:
        redirectTo:
          port: websecure
      websecure:
        tls:
          enabled: true
    additionalArgs:
      - --providers.kubernetesIngress
      - --providers.kubernetesIngress.publishedService.enabled=true
```

### 3. 持久化存储配置

```yaml
# storage/local-path-provisioner.yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: app-data-pvc
  namespace: default
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: local-path
  resources:
    requests:
      storage: 5Gi
```

## 部署第一个应用

### 示例：部署 Nginx + MySQL 栈

```yaml
# deployments/app-stack.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: nginx-app
  labels:
    app: nginx
spec:
  replicas: 2
  selector:
    matchLabels:
      app: nginx
  template:
    metadata:
      labels:
        app: nginx
    spec:
      containers:
      - name: nginx
        image: nginx:1.25-alpine
        ports:
        - containerPort: 80
        resources:
          requests:
            memory: "32Mi"
            cpu: "50m"
          limits:
            memory: "64Mi"
            cpu: "100m"
---
apiVersion: v1
kind: Service
metadata:
  name: nginx-service
spec:
  selector:
    app: nginx
  ports:
  - port: 80
    targetPort: 80
  type: ClusterIP
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: nginx-ingress
  annotations:
    traefik.ingress.kubernetes.io/router.entrypoints: websecure
spec:
  rules:
  - host: myapp.example.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: nginx-service
            port:
              number: 80
```

```bash
# 部署应用
kubectl apply -f deployments/app-stack.yaml

# 验证
kubectl get pods
kubectl get svc
kubectl get ingress
```

## 安全加固

### 1. RBAC 权限控制

```yaml
# rbac/readonly-user.yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: readonly-user
  namespace: default
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: readonly-role
  namespace: default
rules:
- apiGroups: ["", "apps", "networking.k8s.io"]
  resources: ["pods", "deployments", "services", "ingresses"]
  verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: readonly-binding
  namespace: default
subjects:
- kind: ServiceAccount
  name: readonly-user
roleRef:
  kind: Role
  name: readonly-role
  apiGroup: rbac.authorization.k8s.io
```

### 2. 网络策略

```yaml
# network-policies/default-deny.yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-all
  namespace: default
spec:
  podSelector: {}
  policyTypes:
  - Ingress
  - Egress
---
# 允许 DNS 和 Traefik 通信
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-dns-and-traefik
  namespace: default
spec:
  podSelector: {}
  ingress:
  - ports:
    - port: 53
      protocol: UDP
    - port: 53
      protocol: TCP
  - from:
    - namespaceSelector:
        matchLabels:
          kubernetes.io/metadata.name: kube-system
```

### 3. TLS 证书管理

使用 cert-manager 自动管理 TLS 证书：

```bash
# 安装 cert-manager
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.14.0/cert-manager.yaml

# 创建 ClusterIssuer（Let's Encrypt）
cat <<EOF | kubectl apply -f -
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: admin@example.com
    privateKeySecretRef:
      name: letsencrypt-key
    solvers:
    - http01:
        ingress:
          class: traefik
EOF
```

## 监控与日志

### 部署 Metrics Server

```bash
# K3s 默认未启用 metrics-server
k3s kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml

# 修改参数以支持 HTTP
k3s kubectl patch deployment metrics-server -n kube-system --type='json' \
  -p='[{"op": "add", "path": "/spec/template/spec/containers/0/args/-", "value": "--kubelet-insecure-tls"}]'
```

### 轻量级监控方案

对于资源有限的 VPS，推荐使用 **Prometheus + Grafana** 的简化版：

```yaml
# monitoring/prometheus-minimal.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: prometheus
  namespace: monitoring
spec:
  replicas: 1
  selector:
    matchLabels:
      app: prometheus
  template:
    metadata:
      labels:
        app: prometheus
    spec:
      containers:
      - name: prometheus
        image: prom/prometheus:v2.48.0
        ports:
        - containerPort: 9090
        resources:
          requests:
            memory: "128Mi"
            cpu: "50m"
          limits:
            memory: "256Mi"
            cpu: "200m"
---
apiVersion: v1
kind: Namespace
metadata:
  name: monitoring
```

## 备份与恢复

### 集群备份策略

```bash
#!/bin/bash
# backup/k3s-backup.sh
BACKUP_DIR="/opt/k3s-backups"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
mkdir -p ${BACKUP_DIR}/${TIMESTAMP}

# 备份 etcd 数据
sudo k3s etcd-snapshot save --target ${BACKUP_DIR}/${TIMESTAMP}/etcd-snapshot.db

# 备份 manifests
sudo cp -r /var/lib/rancher/k3s/server/manifests/ ${BACKUP_DIR}/${TIMESTAMP}/manifests/
sudo cp -r /var/lib/rancher/k3s/server/conf/ ${BACKUP_DIR}/${TIMESTAMP}/conf/

# 保留最近 7 天备份
find ${BACKUP_DIR} -maxdepth 1 -type d -mtime +7 -exec rm -rf {} +

echo "Backup completed: ${BACKUP_DIR}/${TIMESTAMP}"
```

### 定时备份（cron）

```bash
# 每天凌晨 3 点自动备份
echo "0 3 * * * /opt/k3s-backup.sh" | crontab -
```

## 成本对比分析

| 方案 | 月成本 | 可扩展性 | 管理复杂度 |
|------|--------|----------|------------|
| 单台 4GB VPS + Docker Compose | $5-10 | 低 | 低 |
| **K3s 单节点集群** | **$5-10** | **中** | **中** |
| K3s 3节点集群 | $15-30 | 高 | 中高 |
| 云托管 K8s (EKS/GKE) | $50-200+ | 极高 | 低 |

**关键优势**：K3s 让你在同样的 $5-10 VPS 上获得完整的 Kubernetes 生态——包括 Helm 包管理、声明式 API、自动重启、滚动更新等能力，而无需承担云托管 K8s 的高昂费用。

## 常见问题排查

### 节点 NotReady

```bash
# 检查节点状态
kubectl describe node <node-name>

# 查看 kubelet 日志
journalctl -u k3s -n 100 --no-pager

# 常见原因：
# 1. 资源不足（CPU/Memory）
# 2. 网络插件问题
# 3. 时间不同步
sudo chronyc makestep  # 修复时间同步
```

### Pod 启动失败

```bash
# 查看 Pod 事件
kubectl describe pod <pod-name> -n <namespace>

# 查看容器日志
kubectl logs <pod-name> -n <namespace> --previous

# 检查镜像拉取
kubectl get events --sort-by='.lastTimestamp'
```

## 总结

K3s 是将 Kubernetes 能力带入个人 VPS 的最佳方案。通过合理的资源配置和应用部署，你可以在一台 $5 的 VPS 上运行多个微服务、实现自动化部署和弹性伸缩，同时保持极低的资源消耗。

**下一步建议**：
1. 从单节点开始，熟悉 K3s 基本操作
2. 逐步添加 Helm Chart 管理你的应用
3. 配置 CI/CD 流水线（GitLab CI + ArgoCD）
4. 最终扩展为多节点高可用集群

---

*本文首发于 [selfvps.net](https://selfvps.net)，获取更多自托管与云省钱技巧，请访问我们的网站。*
