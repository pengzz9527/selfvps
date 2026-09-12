---
title: "VPS 上搭建 GitOps 持续部署流水线：ArgoCD + Helm + GitHub 实现一键发布"
description: "在 VPS 上从零搭建 GitOps 持续部署体系，使用 ArgoCD 监听 GitHub 仓库，Helm 管理应用配置，实现每次代码提交自动同步、自动部署、自动回滚。告别手动操作，让发布变成一次 git push。"
date: 2026-09-12T08:00:00+08:00
lastmod: 2026-09-12T08:00:00+08:00
slug: "vps-gitops-argocd-helm-deployment"
tags: ["GitOps", "ArgoCD", "Helm", "Kubernetes", "K3s", "自托管", "CI/CD", "DevOps", "自动化部署"]
categories: ["容器化运维"]
draft: false
image: /images/posts/vps-gitops-argocd-helm-deployment/featured.png
aliases: [/zh/post/vps-gitops-argocd-helm-deployment/]
---

## 引言

你有没有经历过这样的发布场景：

凌晨两点，你需要紧急修复一个线上 bug。你 SSH 到服务器上，手动修改配置文件，重新构建镜像，推送 registry，然后逐个重启容器。等你确认服务恢复正常，已经过了三点。

这不是你的错——**传统的手动部署方式本身就是风险源**。每次手动操作都可能引入错误，每次变更都没有版本记录，每次回滚都是一次赌博。

GitOps 的核心思想很简单：**用 Git 作为唯一的真相来源**。你的基础设施配置、应用部署定义全部写在 Git 仓库里。部署工具监听仓库变化，自动将集群状态同步到期望状态。你想发布新版本？提交一个 commit。想回滚？ revert 那个 commit。

本文将带你从零搭建一套完整的 GitOps 持续部署流水线：在 K3s 上安装 ArgoCD，用 Helm 管理应用配置，配置 GitHub Webhook 实现自动同步，最终实现 **git push → 自动部署** 的完整闭环。

---

## 一、GitOps 架构设计

```
┌──────────────────┐     git push      ┌──────────────────────┐
│  Developer       │ ────────────────▶ │  GitHub Repository   │
│  (IDE / Terminal)│                   │  (infra/ + apps/)    │
└──────────────────┘                   └──────────┬───────────┘
                                                   │ Webhook
                                                   ▼
┌──────────────────┐     watch            ┌──────────────────────┐
│  ArgoCD Server   │ ◀────────────────── │  K3s Cluster          │
│  :8080 / :80     │  sync status         │  (你的 VPS)           │
└────────┬─────────┘                      └──────────┬───────────┘
         │                                            │
         │   Helm Chart                              kubectl
         │   (values.yaml)                            │
         ▼                                            ▼
┌──────────────────┐     apply            ┌──────────────────────┐
│  Helm Charts     │ ───────────────────▶ │  Pods / Services     │
│  (本地或 Git)     │                     │  ConfigMaps / Secrets│
└──────────────────┘                     └──────────────────────┘
```

**核心组件说明：**

| 组件 | 作用 | 为什么选它 |
|------|------|-----------|
| **K3s** | 轻量级 Kubernetes | VPS 资源有限，K3s 仅占用 ~50MB 内存 |
| **ArgoCD** | GitOps 持续部署引擎 | 原生支持 Helm，可视化 UI，自动同步 |
| **Helm** | Kubernetes 包管理器 | 参数化模板，版本化管理配置 |
| **GitHub** | Git 仓库 + Webhook | 代码即基础设施，审计日志完整 |

---

## 二、环境准备

### 2.1 前置条件

- 一台至少 2 CPU / 4GB 内存的 VPS
- Linux 系统（推荐 Ubuntu 22.04 / Debian 12）
- 一个 GitHub 账号
- 一个域名（用于 ArgoCD UI 访问，可选）

### 2.2 安装 K3s

```bash
# 一键安装 K3s
curl -sfL https://get.k3s.io | sh -

# 验证安装
sudo k3s kubectl get nodes
# NAME     STATUS   ROLES       AGE   VERSION
# vps01    Ready    control-plane  2m  v1.29.4-k3s1
```

K3s 默认将 kubeconfig 保存到 `/etc/rancher/k3s/k3s.yaml`，你可以复制到本地方便后续操作：

```bash
scp root@your-vps:/etc/rancher/k3s/k3s.yaml ~/.kube/config
# 修改 config 中的 server 地址为你的 VPS IP
sed -i 's/127.0.0.1/your-vps-ip/g' ~/.kube/config
```

---

## 三、搭建 Git 仓库结构

### 3.1 仓库布局

在 GitHub 上创建两个仓库（或一个 mono-repo）：

```
github.com/yourname/
├── infra-k8s/              # 基础设施配置仓库（ArgoCD 监听这个）
│   ├── argocd/             # ArgoCD 自身配置
│   │   ├── applications/
│   │   │   └── apps.yaml
│   │   └── kustomization.yaml
│   └── apps/               # 应用声明
│       ├── webapp/
│       │   ├── values.yaml
│       │   └── app.yaml
│       ├── monitoring/
│       │   ├── values.yaml
│       │   └── app.yaml
│       └── database/
│           ├── values.yaml
│           └── app.yaml
└── app-source/             # 实际业务代码仓库
    └── (你的应用代码)
```

### 3.2 应用声明文件示例

每个应用目录下创建一个 `app.yaml`，声明该应用到 ArgoCD：

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
      prune: true          # 自动删除不在 Manifest 中的资源
      selfHeal: true       # 自动修复漂移的配置
    syncOptions:
      - CreateNamespace=true
```

关键参数解读：

- **`prune: true`**：自动删除手动创建的多余资源，确保集群状态与 Git 一致
- **`selfHeal: true`**：如果有人手动修改了集群状态，ArgoCD 会自动恢复
- **`CreateNamespace=true`**：自动创建所需的 namespace

---

## 四、安装 ArgoCD

### 4.1 安装 ArgoCD

```bash
# 创建 ArgoCD 命名空间并安装
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

# 验证安装
kubectl get pods -n argocd
# NAME                                             READY   STATUS    RESTARTS   AGE
# argocd-applicationset-controller-xxx            1/1     Running   0          30s
# argocd-dex-server-xxx                           1/1     Running   0          30s
# argocd-notifications-controller-xxx             1/1     Running   0          30s
# argocd-redis-xxx                                1/1     Running   0          30s
# argocd-repo-server-xxx                          1/1     Running   0          30s
# argocd-server-xxx                               1/1     Running   0          30s
```

### 4.2 暴露 ArgoCD UI

K3s 环境中，ArgoCD Server 默认是 ClusterIP 类型。我们可以通过 NodePort 暴露：

```bash
# 修改 Service 类型为 NodePort
kubectl patch svc argocd-server -n argocd -p '{"spec":{"type":"NodePort"}}'

# 查看分配的端口
kubectl get svc argocd-server -n argocd
# NAME            TYPE       CLUSTER-IP     EXTERNAL-IP   PORT(S)                      AGE
# argocd-server   NodePort   10.43.xxx.xxx  <none>        443:30443/TCP,80:30955/TCP   5m
```

通过 `https://your-vps-ip:30443` 访问 ArgoCD UI。

### 4.3 获取管理员密码

```bash
# 获取默认管理员密码
sudo k3s kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d

# 首次登录后请立即修改密码
# 同时修改默认 admin 用户名（可选）
```

默认用户名是 `admin`，密码是上述命令输出的字符串。

---

## 五、配置 Helm Chart

### 5.1 创建应用 Helm Chart

以部署一个简单的 Nginx 服务为例：

```bash
# 创建 Helm Chart 结构
helm create apps/webapp
rm apps/webapp/templates/*.yaml  # 删除默认模板
```

**values.yaml：**

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

**templates/deployment.yaml：**

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

**templates/ingress.yaml：**

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

## 六、配置自动同步

### 6.1 安装 Traefik Ingress Controller

K3s 默认已包含 Traefik，但我们需要配置 TLS 证书：

```bash
# 创建 cert-manager（用于自动签发 TLS 证书）
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.14.4/cert-manager.yaml

# 等待 cert-manager 就绪
kubectl wait --for=condition=ready pod -l app=cert-manager -n cert-manager --timeout=120s

# 创建 ClusterIssuer（使用 Let's Encrypt 生产环境）
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

### 6.2 配置 ArgoCD 应用

```bash
# 创建目标 namespace
kubectl create namespace webapp

# 将应用声明文件应用到 ArgoCD
kubectl apply -f apps/webapp/app.yaml
```

此时打开 ArgoCD UI，你应该能看到 `webapp` 应用已注册，状态为 `OutOfSync`（因为 Git 仓库中还没有对应的 Helm Chart 资源）。

### 6.3 手动触发首次同步

在 ArgoCD UI 中点击 `SYNC` 按钮，选择 `PRUNE` 和 `SELF-HEAL`，然后点击 `SYNCHRONIZE`。

ArgoCD 将会：
1. 读取 `apps/webapp/values.yaml`
2. 用 Helm 渲染 Kubernetes Manifest
3. 将资源应用到 K3s 集群
4. 监控运行状态

### 6.4 配置自动同步（无需 UI 操作）

修改 `app.yaml`，启用 `syncPolicy`：

```yaml
spec:
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
    revisionHistoryLimit: 10   # 保留最近 10 次部署历史
```

配置完成后，每次 Git 仓库有变化，ArgoCD 会在 **30 秒内** 自动检测并同步。

---

## 七、GitHub Webhook 实时触发

### 7.1 在 ArgoCD 中配置 Webhook

ArgoCD 支持 GitHub Webhook 实现实时同步，无需轮询：

```bash
# 获取 ArgoCD Server 的 webhook secret
kubectl get secret argocd-server -n argocd -o jsonpath='{.data.token}' | base64 -d
```

### 7.2 在 GitHub 仓库配置 Webhook

1. 进入 `infra-k8s` 仓库 → Settings → Webhooks → Add webhook
2. **Payload URL**：`https://your-argocd-url/api/webhook`
3. **Content type**：`application/json`
4. **Secret**：粘贴上面获取的 token
5. **Events**：选择 `Just the push event`
6. 点击 `Add webhook`

### 7.3 验证 Webhook 工作正常

```bash
# 在 ArgoCD 容器中查看 webhook 日志
kubectl exec -it -n argocd $(kubectl get pod -n argocd -l app=argocd-server -o jsonpath='{.items[0].metadata.name}') -- argocd server webhook --loglevel debug
```

每次向 `infra-k8s` 仓库推送代码，ArgoCD 都会立即收到通知并开始同步。

---

## 八、完整发布流程实战

### 8.1 发布新版本应用

```bash
# 1. 修改 values.yaml，更新镜像版本
# apps/webapp/values.yaml
image:
  tag: "1.28-alpine"   # 从 1.27 升级到 1.28

# 2. 提交并推送
cd apps/webapp
git add values.yaml
git commit -m "chore: bump nginx to 1.28"
git push origin main

# 3. ArgoCD 自动检测到变更，开始同步
# 查看同步状态
kubectl get application -n argocd
# NAME     SYNC STATUS   HEALTH STATUS
# webapp   Synced        Healthy
```

### 8.2 一键回滚

```bash
# 查看部署历史
kubectl rollout history deployment/webapp -n webapp
# REVISION  CHANGE-CAUSE
# 1         git SHA: abc1234
# 2         git SHA: def5678

# 回滚到上一个版本
git revert HEAD  # revert 导致问题的 commit
git push origin main

# ArgoCD 自动同步，集群恢复到之前的状态
```

### 8.3 多环境部署

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
        - values-staging.yaml   # 覆盖 staging 环境配置
  destination:
    server: https://kubernetes.default.svc
    namespace: webapp-staging
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

通过不同的 `valueFiles`，你可以为 staging 和 production 使用不同的资源配置，而共享相同的 Chart 模板。

---

## 九、成本对比

| 方案 | 月成本 | 维护复杂度 | 自动回滚 | 审计日志 |
|------|--------|-----------|---------|---------|
| **手动部署** | $0 | 高 | ❌ | ❌ |
| **GitHub Actions + kubectl** | $0~20 | 中 | 手动 | 部分 |
| **ArgoCD (自托管)** | $0* | 低 | ✅ 自动 | ✅ 完整 |
| **ArgoCD Cloud** | $50+ | 低 | ✅ 自动 | ✅ 完整 |

*\*假设你已经有一台运行 K3s 的 VPS*

**核心省钱点：**
- 无需额外购买托管 K8s 服务（EKS/GKE/AKS 起步 $70/月）
- 无需购买 CI/CD 托管服务（GitHub Actions 超出免费额度后按分钟计费）
- ArgoCD 本身完全免费开源

---

## 十、最佳实践与注意事项

### 10.1 安全建议

```bash
# 1. 修改 ArgoCD 默认密码
kubectl patch secret argocd-secret -n argocd -p '{"stringData":{
  "admin.password": "$(bcrypt-new-password)",
  "admin.passwordMtime": "$(date +%Y-%m-%dT%H:%M:%SZ)"
}}'

# 2. 启用 RBAC 限制访问
# 3. 使用 TLS 证书（cert-manager 自动管理）
# 4. 限制 GitHub Webhook 只接受特定仓库
```

### 10.2 常见坑点

| 问题 | 原因 | 解决方案 |
|------|------|---------|
| ArgoCD 一直显示 `OutOfSync` | Helm value 文件中有多余的空行或格式问题 | 使用 `helm lint` 检查 |
| Pod 一直 `CrashLoopBackOff` | 资源配置过低或镜像 tag 错误 | 查看 `kubectl logs` 和 `kubectl describe pod` |
| Webhook 无响应 | GitHub 无法访问你的 VPS | 使用 `ngrok` 或配置公网 IP + 域名 |
| 同步失败 | RBAC 权限不足 | 检查 ArgoCD Application 的 ServiceAccount |

### 10.3 监控与告警

```bash
# 启用 ArgoCD Notifications（可选）
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj-labs/argocd-notifications/master/manifests/install.yaml

# 配置 Telegram 告警（在 ArgoCD UI 中设置）
# 应用状态变更时自动发送 Telegram 消息
```

---

## 总结

通过本文，你已经在 VPS 上搭建了一套完整的 GitOps 持续部署流水线：

- **K3s** 提供轻量级 Kubernetes 运行时
- **ArgoCD** 实现声明式部署和自动同步
- **Helm** 管理应用配置模板
- **GitHub Webhook** 实现实时触发

这套方案的核心价值在于：**你的基础设施就是代码**。每一次变更都有版本记录，每一次部署都可以回滚，每一台服务器状态都可以从 Git 仓库推导出来。

对于自托管爱好者和小型团队来说，这是从"手动运维"迈向"自动化运维"的最佳入门路径。

---

*有任何问题或建议？欢迎在 GitHub 上提交 Issue，或在评论区交流。*
