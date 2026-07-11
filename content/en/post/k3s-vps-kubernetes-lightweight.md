---
title: "Deploying Lightweight K3s Kubernetes Cluster on VPS — Edge Computing & Microservices Architecture Complete Guide"
date: 2026-07-11
description: "Build a K3s Kubernetes cluster from scratch on your VPS for container orchestration, service mesh, and automated deployments. Uses 90% less resources than traditional K8s — runs on a single-core VPS."
tags: ["Kubernetes", "K3s", "Container Orchestration", "DevOps", "VPS Optimization", "Edge Computing", "Microservices"]
categories: ["Kubernetes", "Infrastructure"]
image: "/images/posts/k3s-vps-kubernetes-lightweight/featured.png"
draft: false
---

## Why K3s?

In the conventional view, Kubernetes requires at least 3 nodes with 4GB+ memory each. But for individual developers, small teams, or edge computing scenarios, this scale is neither economical nor necessary. **K3s** (Kubernetes light), developed by Rancher Labs, compresses full Kubernetes functionality into a binary under 100MB, reducing resource overhead by over 90%.

| Feature | Traditional Kubernetes | K3s |
|---------|----------------------|-----|
| Minimum Memory | 4GB+ | 512MB |
| Package Size | ~500MB | <100MB |
| Components | 7+ separate binaries | 1 binary file |
| etcd Dependency | Required | SQLite optional |
| Use Cases | Data centers | VPS / Edge / IoT |

## Environment Preparation

### System Requirements

- **OS**: Ubuntu 22.04 LTS / Debian 12 (recommended)
- **CPU**: At least 1 core (2 cores recommended)
- **Memory**: 512MB minimum, 1GB recommended
- **Disk**: 10GB available space
- **Network**: Ports 6443 (API Server), 80/443 (Ingress) open

### Initial Setup Script

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install required tools
sudo apt install -y curl wget apt-transport-https ca-certificates

# Disable swap (required by K3s)
sudo swapoff -a
sudo sed -i '/ swap / s/^/#/' /etc/fstab
```

## Installing K3s

### Single-Node Server Mode (Quickest Start)

```bash
# One-command K3s server installation
curl -sfL https://get.k3s.io | sh -

# Verify installation
sudo systemctl status k3s
kubectl get nodes
kubectl get pods -n kube-system
```

After installation, the kubeconfig is automatically saved at `/etc/rancher/k3s/k3s.yaml`, and kubectl is pre-configured:

```bash
# Test the cluster
kubectl cluster-info
kubectl get svc --all-namespaces
```

### Multi-Node Cluster Mode

#### Master Node Installation

```bash
# Generate install token
export K3S_TOKEN=my-sec...n
# Install as master node
curl -sfL https://get.k3s.io | sh -s - server \
  --cluster-init \
  --token ${K3S_TOKEN} \
  --disable traefik
```

#### Worker Node Join

```bash
# On worker nodes
export K3S_TOKEN=my-sec...port K3S_URL=https://<MASTER_IP>:6443

curl -sfL https://get.k3s.io | sh -s - agent \
  --server ${K3S_URL} \
  --token ${K3S_TOKEN}
```

## Core Component Configuration

### 1. Configure Local kubectl Access

```bash
# Copy config to user directory
mkdir -p ~/.kube
sudo cp /etc/rancher/k3s/k3s.yaml ~/.kube/config
sudo chown $(whoami):$(whoami) ~/.kube/config

# Set aliases
echo 'alias k="kubectl"' >> ~/.bashrc
echo 'alias kubectl="k3s kubectl"' >> ~/.bashrc
source ~/.bashrc
```

### 2. Configure Traefik Ingress Controller

K3s ships with Traefik built-in, but custom configuration yields better performance:

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

### 3. Persistent Storage Configuration

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

## Deploying Your First Application

### Example: Nginx + MySQL Stack Deployment

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
# Deploy application
kubectl apply -f deployments/app-stack.yaml

# Verify
kubectl get pods
kubectl get svc
kubectl get ingress
```

## Security Hardening

### 1. RBAC Permission Control

```yaml
# rbac/readonly-user.yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: readonly-user
  namespace: default
---
apiVersion:rbac.authorization.k8s.io/v1
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

### 2. Network Policies

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
# Allow DNS and Traefik communication
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

### 3. TLS Certificate Management

Use cert-manager for automatic TLS certificate management:

```bash
# Install cert-manager
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.14.0/cert-manager.yaml

# Create ClusterIssuer (Let's Encrypt)
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

## Monitoring and Logging

### Deploy Metrics Server

```bash
# Metrics-server not enabled by default in K3s
k3s kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml

# Patch for insecure kubelet connections
k3s kubectl patch deployment metrics-server -n kube-system --type='json' \
  -p='[{"op": "add", "path": "/spec/template/spec/containers/0/args/-", "value": "--kubelet-insecure-tls"}]'
```

### Lightweight Monitoring Solution

For resource-constrained VPS, the simplified **Prometheus + Grafana** stack is recommended:

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

## Backup and Recovery

### Cluster Backup Strategy

```bash
#!/bin/bash
# backup/k3s-backup.sh
BACKUP_DIR="/opt/k3s-backups"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
mkdir -p ${BACKUP_DIR}/${TIMESTAMP}

# Backup etcd data
sudo k3s etcd-snapshot save --target ${BACKUP_DIR}/${TIMESTAMP}/etcd-snapshot.db

# Backup manifests
sudo cp -r /var/lib/rancher/k3s/server/manifests/ ${BACKUP_DIR}/${TIMESTAMP}/manifests/
sudo cp -r /var/lib/rancher/k3s/server/conf/ ${BACKUP_DIR}/${TIMESTAMP}/conf/

# Keep last 7 days of backups
find ${BACKUP_DIR} -maxdepth 1 -type d -mtime +7 -exec rm -rf {} +

echo "Backup completed: ${BACKUP_DIR}/${TIMESTAMP}"
```

### Scheduled Backups (cron)

```bash
# Automatic daily backup at 3 AM
echo "0 3 * * * /opt/k3s-backup.sh" | crontab -
```

## Cost Comparison Analysis

| Solution | Monthly Cost | Scalability | Management Complexity |
|----------|-------------|-------------|----------------------|
| Single 4GB VPS + Docker Compose | $5-10 | Low | Low |
| **K3s Single-Node Cluster** | **$5-10** | **Medium** | **Medium** |
| K3s 3-Node Cluster | $15-30 | High | Medium-High |
| Cloud Managed K8s (EKS/GKE) | $50-200+ | Very High | Low |

**Key Advantage**: K3s gives you the complete Kubernetes ecosystem — including Helm package management, declarative APIs, auto-restart, rolling updates — on the same $5-10 VPS, without paying cloud-managed K8s premiums.

## Troubleshooting FAQ

### Node NotReady

```bash
# Check node status
kubectl describe node <node-name>

# View kubelet logs
journalctl -u k3s -n 100 --no-pager

# Common causes:
# 1. Insufficient resources (CPU/Memory)
# 2. Network plugin issues
# 3. Time desynchronization
sudo chronyc makestep  # Fix time sync
```

### Pod Startup Failures

```bash
# Check pod events
kubectl describe pod <pod-name> -n <namespace>

# View container logs
kubectl logs <pod-name> -n <namespace> --previous

# Check image pull
kubectl get events --sort-by='.lastTimestamp'
```

## Summary

K3s is the best solution for bringing Kubernetes capabilities to personal VPS environments. With proper resource allocation and application deployment, you can run multiple microservices, achieve automated deployments and elastic scaling on a $5 VPS, all while maintaining extremely low resource consumption.

**Next Steps**:
1. Start with single-node to learn basic K3s operations
2. Gradually add Helm Chart management for your applications
3. Configure CI/CD pipelines (GitLab CI + ArgoCD)
4. Eventually scale to multi-node high-availability cluster

---

*Originally published on [selfvps.net](https://selfvps.net). For more self-hosting and cloud cost-saving tips, visit our website.*
