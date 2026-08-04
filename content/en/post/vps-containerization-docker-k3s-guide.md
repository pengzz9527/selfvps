---
title: "VPS Containerization Guide: Complete Docker to K3s Deployment"
description: "Learn VPS containerization from scratch - master Docker basics, Docker Compose orchestration, and lightweight Kubernetes K3s deployment for more efficient and reliable application management"
date: 2026-08-04
lastmod: 2026-08-04
slug: "vps-containerization-docker-k3s-guide"
image: /images/posts/vps-containerization-docker-k3s-guide/featured.png
tags: ["Docker", "K3s", "Containerization", "VPS", "Kubernetes", "DevOps", "Deployment", "Orchestration"]
categories: ["Containerization"]
aliases: [/en/post/vps-containerization-docker-k3s-guide/]
---

## Introduction

Running applications on a VPS traditionally means installing software directly on the server and configuring environments. As application complexity grows, this approach brings numerous problems: inconsistent environments, dependency conflicts, difficult deployments, and poor scalability. Containerization technology was born to solve these exact issues.

Docker and Kubernetes (along with its lightweight distribution K3s) have become the standard tools of the cloud-native era. This guide takes you from scratch to master complete containerized deployment on your VPS - from basic Docker container management to multi-container orchestration, and finally to lightweight Kubernetes cluster setup.

## Why Choose Containerization?

Containerization offers these core advantages over traditional deployment:

- **Environment Consistency**: Development, testing, and production environments are identical, eliminating the "it works on my machine" problem
- **Fast Deployment**: One-click image deployment, second-level startup, supporting rolling updates and quick rollbacks
- **Resource Isolation**: Each container runs independently without affecting others, with controllable resource quotas
- **Horizontal Scaling**: Easily replicate multiple container instances to handle traffic spikes
- **Rich Ecosystem**: Docker Hub and major cloud providers offer countless pre-built images

## Phase 1: Docker Basics

### 1.1 Install Docker

```bash
# Ubuntu/Debian
curl -fsSL https://get.docker.com | sh

# Add current user to docker group (avoid using sudo each time)
sudo usermod -aG docker $USER

# Apply changes
newgrp docker

# Verify installation
docker --version
docker info
```

### 1.2 Run Your First Container

```bash
# Pull and run Nginx
docker run -d \
  --name nginx \
  -p 80:80 \
  -v /opt/nginx/html:/usr/share/nginx/html:ro \
  nginx:alpine

# Check running status
docker ps

# Access the service
curl http://localhost
```

### 1.3 Docker Quick Reference

```bash
# Image management
docker images          # List local images
docker pull nginx      # Pull image
docker rmi nginx       # Remove image

# Container management
docker ps -a           # List all containers
docker stop nginx      # Stop container
docker start nginx     # Start container
docker rm nginx        # Remove container
docker logs nginx      # View logs

# Enter container
docker exec -it nginx bash

# Resource limits
docker run -d --name app \
  --cpus="1.5" \
  --memory="512m" \
  -p 8080:80 \
  myapp:latest
```

## Phase 2: Docker Compose Multi-Container Orchestration

### 2.1 What is Docker Compose?

Docker Compose is a tool for defining and running multi-container Docker applications. Configure your application stack with a single YAML file and start all services with one command.

### 2.2 Typical Application Stack Configuration

Using "website + database + cache" as an example:

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

### 2.3 Compose Common Commands

```bash
# Start all services
docker compose up -d

# Check service status
docker compose ps

# View logs
docker compose logs -f app

# Restart service
docker compose restart app

# Stop and remove containers (preserve data volumes)
docker compose down

# Rebuild image and restart
docker compose up -d --build
```

## Phase 3: K3s Lightweight Kubernetes

### 3.1 What is K3s?

K3s is Rancher's lightweight Kubernetes distribution, designed for edge computing, IoT, and VPS scenarios:

- Single binary file, installation package only 60MB
- Memory footprint as low as 256MB
- Built-in Traefik Ingress and ServiceLB
- Fully compatible with Kubernetes API

### 3.2 One-Command K3s Installation

```bash
# Single node K3s server
curl -sfL https://get.k3s.io | sh -

# Check node status
sudo k3s kubectl get nodes
sudo k3s kubectl get pods -A

# Configure kubectl alias
echo 'alias k=k3s kubectl' >> ~/.bashrc
source ~/.bashrc

# Verify
k get nodes
```

### 3.3 High Availability K3s Cluster

For production environments, use a multi-node high-availability architecture:

```bash
# Configure HTTPS load balancer (HAProxy + Keepalived)
# Reference: https://rancher.com/docs/k3s/latest/en/advanced/#high-availability-with-an-external-database

# Generate token
sudo cat /etc/rancher/k3s/token

# Join worker nodes to the cluster
curl -sfL https://get.k3s.io | K3S_URL=https://LOADBALANCER:6443 K3S_TOKEN=xxx sh -
```

### 3.4 Kubernetes Core Concepts

```
Pod          # Smallest deployment unit, contains one or more containers
Deployment   # Manages Pod replicas and update strategies
Service      # Exposes Pod network access
ConfigMap    # Externalized configuration
Secret       # Encrypted sensitive information storage
Ingress      # HTTP routing and SSL termination
PV/PVC       # Persistent storage
```

### 3.5 Practice: Deploy a Complete Application Stack

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
# Apply configuration
kubectl apply -f k3s-app.yaml

# Check status
kubectl get pods
kubectl get svc
kubectl get ingress

# Rolling update
kubectl set image deployment/web-app nginx=nginx:1.25-alpine
```

## Phase 4: Production Best Practices

### 4.1 Resource Limits and Quality of Service

```yaml
resources:
  requests:
    memory: "128Mi"
    cpu: "100m"
  limits:
    memory: "256Mi"
    cpu: "500m"
```

### 4.2 Health Checks

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

### 4.3 Persistent Storage

```yaml
# K3s comes with local-path storage class
kubectl get storageclass

# PVC example
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

### 4.4 Backup and Recovery

```bash
# Backup etcd (K3s manages automatically)
sudo /usr/local/bin/k3s-etcd-snapshot save

# List backups
sudo /usr/local/bin/k3s-etcd-snapshot ls

# Restore
sudo /usr/local/bin/k3s-etcd-snapshot restore /path/to/snapshot.db
```

## Phase 5: Choosing the Right Solution

| Scenario | Recommended Solution | Reason |
|----------|---------------------|--------|
| Single application deployment | Docker + Docker Compose | Simple and intuitive, ready to use |
| Multi-service microservices | K3s | Native service discovery, load balancing, auto-scaling |
| Edge computing/IoT | K3s | Extremely low resource footprint |
| Development/test environments | Docker Compose | Quick setup, easy to destroy and rebuild |
| Production environment | K3s HA cluster | Fault recovery, rolling updates, version management |

## Conclusion

Containerization is an essential skill for VPS operations. From Docker to K3s, you can choose the appropriate solution based on project complexity and team size. Remember: **Keep it simple for simple tasks, have frameworks for complex ones.**

For personal projects and small teams, Docker Compose is usually sufficient; when application scale grows and you need multi-environment deployment and auto-scaling, K3s provides a smooth upgrade path.

## References

- Docker Documentation: https://docs.docker.com/
- Docker Compose Documentation: https://docs.docker.com/compose/
- K3s Documentation: https://docs.k3s.io/
- Kubernetes Documentation: https://kubernetes.io/docs/
