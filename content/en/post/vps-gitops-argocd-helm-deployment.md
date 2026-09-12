---
title: "Build a GitOps Continuous Deployment Pipeline on VPS: ArgoCD + Helm + GitHub for One-Click Releases"
description: "Build a complete GitOps continuous deployment system on your VPS from scratch. Use ArgoCD to watch GitHub repos, Helm to manage application configs, and achieve automatic sync, deploy, and rollback on every code commit. Say goodbye to manual operations—let every release be just a git push away."
date: 2026-09-12T08:00:00+08:00
lastmod: 2026-09-12T08:00:00+08:00
slug: "vps-gitops-argocd-helm-deployment"
tags: ["GitOps", "ArgoCD", "Helm", "Kubernetes", "K3s", "Self-hosted", "CI/CD", "DevOps", "Automated Deployment"]
categories: ["Containerized Operations"]
draft: false
image: /images/posts/vps-gitops-argocd-helm-deployment/featured.png
aliases: [/en/post/vps-gitops-argocd-helm-deployment/]
---

## Introduction

Have you ever experienced this deployment scenario:

It's 2 AM and you need to urgently fix a production bug. You SSH into your server, manually modify config files, rebuild the Docker image, push to the registry, and restart containers one by one. By the time you confirm the service is back online, it's already past 3 AM.

This isn't your fault—**the traditional manual deployment approach is inherently risky**. Every manual operation can introduce errors, every change lacks version records, and every rollback is a gamble.

The core idea of GitOps is simple: **use Git as the single source of truth**. Your infrastructure configurations and application deployment definitions are all written in Git repositories. The deployment tool watches for changes and automatically syncs the cluster state to the desired state. Want to release a new version? Submit a commit. Want to roll back? Revert that commit.

This article will guide you from scratch to build a complete GitOps continuous deployment pipeline: install ArgoCD on K3s, manage application configs with Helm, configure GitHub Webhooks for automatic sync, and ultimately achieve a complete loop of **git push → automatic deployment**.

---

## 1. GitOps Architecture Design

```
┌──────────────────┐     git push      ┌──────────────────────┐
│  Developer       │ ────────────────▶ │  GitHub Repository   │
│  (IDE / Terminal)│                   │  (infra/ + apps/)    │
└──────────────────┘                   └──────────┬───────────┘
                                                   │ Webhook
                                                   ▼
┌──────────────────┐     watch            ┌──────────────────────┐
│  ArgoCD Server   │ ◀────────────────── │  K3s Cluster          │
│  :8080 / :80     │  sync status         │  (Your VPS)          │
└────────┬─────────┘                      └──────────┬───────────┘
         │                                            │
         │   Helm Chart                              kubectl
         │   (values.yaml)                            │
         ▼                                            ▼
┌──────────────────┐     apply            ┌──────────────────────┐
│  Helm Charts     │ ───────────────────▶ │  Pods / Services     │
│  (Local or Git)  │                     │  ConfigMaps / Secrets│
└──────────────────┘                     └──────────────────────┘
```

**Core Components:**

| Component | Role | Why Choose It |
|-----------|------|---------------|
| **K3s** | Lightweight Kubernetes | Minimal resource footprint (~50MB RAM) for VPS |
| **ArgoCD** | GitOps deployment engine | Native Helm support, visual UI, auto-sync |
| **Helm** | Kubernetes package manager | Parameterized templates, version-controlled configs |
| **GitHub** | Git repo + Webhooks | Infrastructure as code, complete audit trail |

---

## 2. Environment Preparation

### 2.1 Prerequisites

- A VPS with at least 2 CPUs / 4GB RAM
- Linux system (Ubuntu 22.04 / Debian 12 recommended)
- A GitHub account
- A domain name (for ArgoCD UI access, optional)

### 2.2 Install K3s

```bash
# One-command K3s installation
curl -sfL https://get.k3s.io | sh -

# Verify installation
sudo k3s kubectl get nodes
# NAME     STATUS   ROLES       AGE   VERSION
# vps01    Ready    control-plane  2m  v1.29.4-k3s1
```

K3s saves the kubeconfig to `/etc/rancher/k3s/k3s.yaml` by default. You can copy it locally for convenience:

```bash
scp root@your-vps:/etc/rancher/k3s/k3s.yaml ~/.kube/config
# Update the server address to your VPS IP
sed -i 's/127.0.0.1/your-vps-ip/g' ~/.kube/config
```

---

## 3. Set Up Git Repository Structure

### 3.1 Repository Layout

Create two repositories on GitHub (or one mono-repo):

```
github.com/yourname/
├── infra-k8s/              # Infrastructure config repo (ArgoCD watches this)
│   ├── argocd/             # ArgoCD self-configuration
│   │   ├── applications/
│   │   │   └── apps.yaml
│   │   └── kustomization.yaml
│   └── apps/               # Application declarations
│       ├── webapp/
│       │   ├── values.yaml
│       │   └── app.yaml
│       ├── monitoring/
│       │   ├── values.yaml
│       │   └── app.yaml
│       └── database/
│           ├── values.yaml
│           └── app.yaml
└── app-source/             # Actual application code repo
    └── (your application code)
```

### 3.2 Application Declaration Example

Create an `app.yaml` in each application directory to declare it to ArgoCD:

```yaml
# apps/webapp/app.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: webapp
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/yourname/infra-k8s.git
    targetRevision: main
    path: apps/webapp
    helm:
      valueFiles:
        - values.yaml
  destination:
    server: https://kubernetes.default.svc
    namespace: webapp
  syncPolicy:
    automated:
      prune: true          # Auto-delete resources not in Manifest
      selfHeal: true       # Auto-repair drifted configs
    syncOptions:
      - CreateNamespace=true
```

Key parameters explained:

- **`prune: true`**: Automatically deletes manually created extra resources, ensuring cluster state matches Git
- **`selfHeal: true`**: If someone manually modifies cluster state, ArgoCD automatically restores it
- **`CreateNamespace=true`**: Auto-creates required namespaces

---

## 4. Install ArgoCD

### 4.1 Install ArgoCD

```bash
# Create ArgoCD namespace and install
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

# Verify installation
kubectl get pods -n argocd
# NAME                                             READY   STATUS    RESTARTS   AGE
# argocd-applicationset-controller-xxx            1/1     Running   0          30s
# argocd-dex-server-xxx                           1/1     Running   0          30s
# argocd-notifications-controller-xxx             1/1     Running   0          30s
# argocd-redis-xxx                                1/1     Running   0          30s
# argocd-repo-server-xxx                          1/1     Running   0          30s
# argocd-server-xxx                               1/1     Running   0          30s
```

### 4.2 Expose ArgoCD UI

In K3s, ArgoCD Server defaults to ClusterIP type. We'll expose it via NodePort:

```bash
# Patch Service to NodePort type
kubectl patch svc argocd-server -n argocd -p '{"spec":{"type":"NodePort"}}'

# Check assigned port
kubectl get svc argocd-server -n argocd
# NAME            TYPE       CLUSTER-IP     EXTERNAL-IP   PORT(S)                      AGE
# argocd-server   NodePort   10.43.xxx.xxx  <none>        443:30443/TCP,80:30955/TCP   5m
```

Access ArgoCD UI at `https://your-vps-ip:30443`.

### 4.3 Get Admin Password

```bash
# Get default admin password
sudo k3s kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d

# Change password immediately after first login
# Also consider changing the default admin username
```

Default username is `admin`, password is the string output by the above command.

---

## 5. Configure Helm Chart

### 5.1 Create Application Helm Chart

Take deploying a simple Nginx service as an example:

```bash
# Create Helm Chart structure
helm create apps/webapp
rm apps/webapp/templates/*.yaml  # Remove default templates
```

**values.yaml:**

```yaml
# apps/webapp/values.yaml
replicaCount: 2

image:
  repository: nginx
  tag: "1.27-alpine"
  pullPolicy: IfNotPresent

service:
  type: ClusterIP
  port: 80

ingress:
  enabled: true
  hostname: app.yourdomain.com
  className: traefik
  tls: true

resources:
  requests:
    memory: "64Mi"
    cpu: "50m"
  limits:
    memory: "128Mi"
    cpu: "200m"
```

**templates/deployment.yaml:**

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ .Release.Name }}
  labels:
    app: {{ .Release.Name }}
spec:
  replicas: {{ .Values.replicaCount }}
  selector:
    matchLabels:
      app: {{ .Release.Name }}
  template:
    metadata:
      labels:
        app: {{ .Release.Name }}
    spec:
      containers:
        - name: {{ .Chart.Name }}
          image: "{{ .Values.image.repository }}:{{ .Values.image.tag }}"
          imagePullPolicy: {{ .Values.image.pullPolicy }}
          ports:
            - name: http
              containerPort: 80
              protocol: TCP
          resources:
            {{- toYaml .Values.resources | nindent 12 }}
---
apiVersion: v1
kind: Service
metadata:
  name: {{ .Release.Name }}
spec:
  type: {{ .Values.service.type }}
  ports:
    - port: {{ .Values.service.port }}
      targetPort: http
      protocol: TCP
  selector:
    app: {{ .Release.Name }}
```

**templates/ingress.yaml:**

```yaml
{{- if .Values.ingress.enabled }}
apiVersion: traefik.containo.us/v1alpha1
kind: IngressRoute
metadata:
  name: {{ .Release.Name }}
spec:
  entryPoints:
    - web
  routes:
    - match: Host(`{{ .Values.ingress.hostname }}`)
      kind: Rule
      services:
        - name: {{ .Release.Name }}
          port: {{ .Values.service.port }}
  {{- if .Values.ingress.tls }}
  tls:
    secretName: {{ .Release.Name }}-tls
  {{- end }}
{{- end }}
```

---

## 6. Configure Automatic Sync

### 6.1 Install Traefik Ingress Controller

K3s includes Traefik by default, but we need to configure TLS certificates:

```bash
# Install cert-manager (for automatic TLS certificate issuance)
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.14.4/cert-manager.yaml

# Wait for cert-manager to be ready
kubectl wait --for=condition=ready pod -l app=cert-manager -n cert-manager --timeout=120s

# Create ClusterIssuer (using Let's Encrypt production)
cat <<EOF | kubectl apply -f -
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: your-email@example.com
    privateKeySecretRef:
      name: letsencrypt-prod-key
    solvers:
      - http01:
          ingress:
            class: traefik
EOF
```

### 6.2 Configure ArgoCD Application

```bash
# Create target namespace
kubectl create namespace webapp

# Apply application declaration to ArgoCD
kubectl apply -f apps/webapp/app.yaml
```

At this point, opening the ArgoCD UI should show the `webapp` application registered with `OutOfSync` status (since the Helm Chart resources haven't been committed to the Git repo yet).

### 6.3 Manually Trigger First Sync

In the ArgoCD UI, click the `SYNC` button, select `PRUNE` and `SELF-HEAL`, then click `SYNCHRONIZE`.

ArgoCD will:
1. Read `apps/webapp/values.yaml`
2. Render Kubernetes Manifests using Helm
3. Apply resources to the K3s cluster
4. Monitor running status

### 6.4 Configure Automatic Sync (No UI Required)

Modify `app.yaml` to enable `syncPolicy`:

```yaml
spec:
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
    revisionHistoryLimit: 10   # Keep last 10 deployment histories
```

After configuration, ArgoCD will automatically detect and sync within **30 seconds** of any Git repo changes.

---

## 7. GitHub Webhook Real-Time Trigger

### 7.1 Configure Webhook in ArgoCD

ArgoCD supports GitHub Webhooks for real-time sync without polling:

```bash
# Get ArgoCD Server webhook secret
kubectl get secret argocd-server -n argocd -o jsonpath='{.data.token}' | base64 -d
```

### 7.2 Configure Webhook in GitHub Repository

1. Go to `infra-k8s` repo → Settings → Webhooks → Add webhook
2. **Payload URL**: `https://your-argocd-url/api/webhook`
3. **Content type**: `application/json`
4. **Secret**: Paste the token from above
5. **Events**: Select `Just the push event`
6. Click `Add webhook`

### 7.3 Verify Webhook is Working

```bash
# Check webhook logs in ArgoCD container
kubectl exec -it -n argocd $(kubectl get pod -n argocd -l app=argocd-server -o jsonpath='{.items[0].metadata.name}') -- argocd server webhook --loglevel debug
```

Every time you push code to the `infra-k8s` repo, ArgoCD receives the notification immediately and starts syncing.

---

## 8. Complete Release Workflow

### 8.1 Release a New Application Version

```bash
# 1. Modify values.yaml to update image version
# apps/webapp/values.yaml
image:
  tag: "1.28-alpine"   # Upgrade from 1.27 to 1.28

# 2. Commit and push
cd apps/webapp
git add values.yaml
git commit -m "chore: bump nginx to 1.28"
git push origin main

# 3. ArgoCD auto-detects changes and syncs
# Check sync status
kubectl get application -n argocd
# NAME     SYNC STATUS   HEALTH STATUS
# webapp   Synced        Healthy
```

### 8.2 One-Click Rollback

```bash
# View deployment history
kubectl rollout history deployment/webapp -n webapp
# REVISION  CHANGE-CAUSE
# 1         git SHA: abc1234
# 2         git SHA: def5678

# Roll back to previous version
git revert HEAD  # Revert the problematic commit
git push origin main

# ArgoCD auto-syncs, cluster returns to previous state
```

### 8.3 Multi-Environment Deployment

```yaml
# apps/webapp/app-staging.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: webapp-staging
  namespace: argocd
spec:
  source:
    repoURL: https://github.com/yourname/infra-k8s.git
    targetRevision: main
    path: apps/webapp
    helm:
      valueFiles:
        - values.yaml
        - values-staging.yaml   # Override staging environment config
  destination:
    server: https://kubernetes.default.svc
    namespace: webapp-staging
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

With different `valueFiles`, you can use different resource configurations for staging and production while sharing the same Chart templates.

---

## 9. Cost Comparison

| Approach | Monthly Cost | Maintenance Complexity | Auto Rollback | Audit Log |
|----------|-------------|----------------------|---------------|-----------|
| **Manual Deployment** | $0 | High | ❌ | ❌ |
| **GitHub Actions + kubectl** | $0~20 | Medium | Manual | Partial |
| **ArgoCD (Self-hosted)** | $0* | Low | ✅ Automatic | ✅ Complete |
| **ArgoCD Cloud** | $50+ | Low | ✅ Automatic | ✅ Complete |

*\*Assuming you already have a VPS running K3s*

**Key Cost Savings:**
- No need for managed K8s services (EKS/GKE/AKS start at $70/month)
- No need for hosted CI/CD services (GitHub Actions bills per minute after free tier)
- ArgoCD is completely free and open-source

---

## 10. Best Practices & Notes

### 10.1 Security Recommendations

```bash
# 1. Change ArgoCD default password
kubectl patch secret argocd-secret -n argocd -p '{"stringData":{
  "admin.password": "$(bcrypt-new-password)",
  "admin.passwordMtime": "$(date +%Y-%m-%dT%H:%M:%SZ)"
}}'

# 2. Enable RBAC to restrict access
# 3. Use TLS certificates (cert-manager manages automatically)
# 4. Restrict GitHub Webhook to specific repos only
```

### 10.2 Common Pitfalls

| Problem | Cause | Solution |
|---------|-------|----------|
| ArgoCD shows `OutOfSync` constantly | Extra whitespace or formatting issues in Helm values | Use `helm lint` to check |
| Pods in `CrashLoopBackOff` | Resources too low or wrong image tag | Check `kubectl logs` and `kubectl describe pod` |
| Webhook not responding | GitHub can't reach your VPS | Use `ngrok` or configure public IP + domain |
| Sync fails | RBAC permission issues | Check ArgoCD Application's ServiceAccount |

### 10.3 Monitoring & Alerting

```bash
# Enable ArgoCD Notifications (optional)
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj-labs/argocd-notifications/master/manifests/install.yaml

# Configure Telegram alerts (set in ArgoCD UI)
# Get Telegram messages when application status changes
```

---

## Summary

Through this article, you've built a complete GitOps continuous deployment pipeline on your VPS:

- **K3s** provides a lightweight Kubernetes runtime
- **ArgoCD** enables declarative deployment and automatic sync
- **Helm** manages application configuration templates
- **GitHub Webhooks** enable real-time triggering

The core value of this approach is: **your infrastructure is code**. Every change has version records, every deployment can be rolled back, and every server state can be derived from the Git repository.

For self-hosting enthusiasts and small teams, this is the best entry path from "manual operations" to "automated operations."

---

*Have questions or suggestions? Feel free to open an Issue on GitHub or share in the comments.*
