---
title: "Docker 安全加固：容器安全的十大最佳实践"
description: "全面解析 Docker 容器安全——从镜像扫描、非 root 运行到 Seccomp/AppArmor 配置，教你如何加固生产环境中的容器安全"
date: 2026-05-22T10:00:00+08:00
lastmod: 2026-05-22T10:00:00+08:00
slug: "docker-security-hardening"
image: /images/posts/docker-security-hardening/featured.png
tags: ["Docker", "安全", "容器", "运维", "最佳实践", "Linux", "DevOps"]
categories: ["安全运维"]
aliases: [/zh/post/docker-security-hardening/]
---

## 引言

Docker 彻底改变了我们部署应用的方式，但"容器不等于安全"。默认的 Docker 配置为易用性做了优化，而非安全性。在生产环境中，未加固的容器可能成为攻击者的突破口。

本文将介绍 **10 个 Docker 容器安全最佳实践**，从基础配置到高级加固，帮助你在享受容器化便利的同时，确保系统安全。

---

## 1. 使用非 root 用户运行容器 ⭐

**这是最重要的安全实践！**

Docker 默认以 root 运行容器进程。如果攻击者通过容器漏洞逃逸到宿主机，将直接获得 root 权限。

```dockerfile
# ❌ 不安全的做法 — 默认 root
FROM node:18
COPY . /app
CMD ["node", "server.js"]

# ✅ 安全的做法 — 使用非 root 用户
FROM node:18
RUN groupadd -r appgroup && useradd -r -g appgroup appuser
USER appuser
COPY . /app
CMD ["node", "server.js"]
```

**在 docker-compose.yml 中指定用户：**

```yaml
services:
  app:
    image: myapp:latest
    user: "1000:1000"  # 使用非 root 用户运行
```

**运行时指定：**

```bash
docker run --user 1000:1000 myapp
```

## 2. 使用只读文件系统

容器文件系统默认是可写的，这给了攻击者写入恶意文件的机会。

```yaml
services:
  app:
    image: myapp:latest
    read_only: true    # 根文件系统只读
    tmpfs:
      - /tmp           # 仅临时目录可写
      - /var/run
    volumes:
      - app_data:/app/data  # 需要写入的路径用 volume
```

## 3. 限制内核能力（Capabilities）

Docker 容器默认拥有大量 Linux capabilities。遵循**最小权限原则**，只赋予必要的能力。

```bash
# 查看容器当前的能力
docker run --rm alpine getpcaps 1

# 删除所有能力，只添加需要的
docker run --rm \
  --cap-drop=ALL \
  --cap-add=NET_BIND_SERVICE \
  nginx:alpine
```

**docker-compose 配置：**

```yaml
services:
  app:
    image: nginx:alpine
    cap_drop:
      - ALL
    cap_add:
      - NET_BIND_SERVICE
      - NET_RAW          # 按需添加
```

### 常见能力对照表

| 能力 | 作用 | 风险等级 |
|------|------|---------|
| `NET_BIND_SERVICE` | 绑定低端口 (<1024) | 🟢 低 |
| `CHOWN` | 修改文件所有者 | 🟡 中 |
| `SYS_ADMIN` | 系统管理（极度危险） | 🔴 高 |
| `SYS_PTRACE` | 调试进程 | 🔴 高 |
| `NET_ADMIN` | 网络配置 | 🔴 高 |
| `SYS_MODULE` | 加载内核模块 | 🔴 极高 |

## 4. 使用 Seccomp 限制系统调用

Seccomp（Secure Computing Mode）可以限制容器可以执行的系统调用。Docker 默认提供一个安全的 seccomp 配置文件，但你也可以自定义更严格的规则。

```bash
# 查看当前的 seccomp 配置
docker run --rm -it alpine cat /proc/self/status | grep Seccomp
# 输出: Seccomp: 2  （2 = 过滤模式）

# 使用默认 seccomp 配置
docker run --rm --security-opt seccomp=default alpine

# 使用自定义 seccomp 配置
docker run --rm \
  --security-opt seccomp=/path/to/custom.json \
  alpine
```

**自定义 seccomp 示例（仅允许所需系统调用）：**

```json
{
  "defaultAction": "SCMP_ACT_ERRNO",
  "architectures": ["SCMP_ARCH_X86_64"],
  "syscalls": [
    {
      "names": ["read", "write", "open", "close", "mmap", "munmap", "brk", "exit", "exit_group", "fstat", "stat", "lseek", "ioctl", "clone", "execve", "getdents64"],
      "action": "SCMP_ACT_ALLOW"
    }
  ]
}
```

## 5. 使用 AppArmor 或 SELinux

### AppArmor（Ubuntu/Debian）

```bash
# 使用 Docker 默认的 AppArmor 配置
docker run --rm --security-opt apparmor=docker-default alpine

# 加载自定义配置
sudo apparmor_parser -r -W /etc/apparmor.d/custom-docker
docker run --rm --security-opt apparmor=custom-docker alpine
```

### SELinux（CentOS/RHEL/Fedora）

```bash
# 启用 SELinux 安全标签
docker run --rm --security-opt label=level:TopSecret alpine

# 允许容器访问特定目录
docker run --rm -v /data:/data:Z alpine
```

## 6. 镜像安全扫描

在部署前扫描镜像中的漏洞。

### Trivy — 最流行的镜像扫描工具

```bash
# 安装 Trivy
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
  aquasec/trivy image nginx:alpine

# 严重漏洞检查
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
  aquasec/trivy image --severity CRITICAL,HIGH nginx:1.25

# CI/CD 集成（失败退出码）
trivy image --exit-code 1 --severity CRITICAL myapp:latest
```

### Docker Scout（Docker 内置）

```bash
# 启用 Docker Scout
docker scout quickview nginx:alpine

# 比较镜像差异
docker scout compare nginx:alpine nginx:1.25-alpine
```

### 推荐的基础镜像选择

| 镜像 | 大小 | CVE 数量 | 适用场景 |
|------|------|---------|---------|
| `alpine:3.19` | ~7MB | 0-5 | ✅ 首选 |
| `distroless` | ~15MB | 0-3 | ✅ 极安全 |
| `slim` (如 node:slim) | ~50MB | 10-30 | ⚠️ 中等 |
| `ubuntu:22.04` | ~77MB | 30-100+ | ❌ 不推荐 |
| `debian:bookworm` | ~124MB | 50-150+ | ❌ 不推荐 |

> **经验法则**：优先使用 `alpine` 或 `distroless` 基础镜像。它们体积小、攻击面小。

## 7. 限制资源使用

限制容器的 CPU、内存和磁盘使用，防止 DoS 攻击或资源耗尽。

```yaml
services:
  app:
    image: myapp:latest
    deploy:
      resources:
        limits:
          cpus: '0.50'       # 最多 0.5 个 CPU 核心
          memory: 512M       # 最多 512MB 内存
          pids: 100          # 限制进程数
        reservations:
          cpus: '0.25'       # 预留 0.25 核心
          memory: 256M       # 预留 256MB 内存
    # 更严格的限制
    oom_kill_disable: false   # 允许 OOM killer
    ulimits:
      nofile:
        soft: 1024
        hard: 2048
    storage_opt:
      size: '10G'            # 磁盘限制
```

**命令行方式：**

```bash
docker run --rm \
  --memory="512m" \
  --cpus="0.5" \
  --pids-limit=100 \
  --storage-opt size=10G \
  myapp
```

## 8. 使用 Docker Content Trust（镜像签名）

确保只运行经过签名的可信镜像。

```bash
# 启用内容信任
export DOCKER_CONTENT_TRUST=1

# 现在拉取未签名的镜像会被拒绝
docker pull myapp:latest
# Error: remote trust data does not exist

# 推送并签名镜像
docker push myapp:latest
# 会自动要求签名密钥

# 也可以在 docker-compose 中全局启用
# .env 文件
DOCKER_CONTENT_TRUST=1
```

**在 CI/CD 中配置签名：**

```yaml
# .github/workflows/deploy.yml
jobs:
  deploy:
    steps:
      - name: Sign and push image
        env:
          DOCKER_CONTENT_TRUST: 1
          DOCKER_CONTENT_TRUST_SERVER: "https://notary.example.com"
        run: |
          docker push myapp:${{ github.sha }}
```

## 9. 安全日志与审计

### 配置 Docker 审计日志

```bash
# 审计 Docker 守护进程活动
sudo auditctl -w /usr/bin/docker -p wa -k docker
sudo auditctl -w /var/lib/docker -p wa -k docker
sudo auditctl -w /etc/docker -p wa -k docker

# 查看日志
sudo ausearch -k docker --start today
```

### 容器日志最佳实践

```yaml
services:
  app:
    image: myapp:latest
    logging:
      driver: "json-file"
      options:
        max-size: "10m"      # 单个日志最大 10MB
        max-file: "3"        # 保留 3 个轮换文件
        compress: "true"     # 压缩旧日志
    # 避免敏感信息落入日志
    environment:
      - DB_PASSWORD_FILE=/run/secrets/db_password
```

### Falco — 运行时安全监控

```bash
# 安装 Falco（容器安全运行时）
docker run --rm -i \
  --privileged \
  -v /var/run/docker.sock:/host/var/run/docker.sock \
  -v /proc:/host/proc:ro \
  falcosecurity/falco:latest

# Falco 能检测：
# - 容器中启动交互式 Shell
# - 敏感文件读取（/etc/shadow）
# - 意外的网络连接
# - 权限提升尝试
```

## 10. 网络安全隔离

### 使用自定义网络

```yaml
services:
  app:
    image: myapp:latest
    networks:
      - internal
      - traefik_proxy

  db:
    image: postgres:16-alpine
    networks:
      - internal   # 数据库仅在内部网络

  redis:
    image: redis:7-alpine
    networks:
      - internal

networks:
  internal:
    internal: true       # ❗ 阻止外部访问
  traefik_proxy:
    external: true
```

### 禁止容器间通信（默认是允许的）

```yaml
# docker-compose.yml
services:
  app:
    image: myapp:latest
    network_mode: "none"  # 完全隔离

# 或者在 Docker 守护进程级别禁止
```

```bash
# 配置 /etc/docker/daemon.json
sudo tee /etc/docker/daemon.json <<EOF
{
  "icc": false,
  "iptables": true,
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  },
  "live-restore": true,
  "userland-proxy": false
}
EOF

# 重启 Docker
sudo systemctl restart docker
```

---

## Docker 安全速查表

| # | 实践 | 命令/配置 |
|---|------|-----------|
| 1 | 非 root 用户 | `USER appuser` in Dockerfile |
| 2 | 只读文件系统 | `read_only: true` in compose |
| 3 | 限制 Capabilities | `--cap-drop=ALL --cap-add=...` |
| 4 | Seccomp 过滤 | `--security-opt seccomp=...` |
| 5 | AppArmor/SELinux | `--security-opt apparmor=...` |
| 6 | 镜像扫描 | `trivy image myapp` |
| 7 | 资源限制 | `--memory=512m --cpus=0.5` |
| 8 | 内容信任 | `DOCKER_CONTENT_TRUST=1` |
| 9 | 安全审计 | Falco + auditd |
| 10 | 网络隔离 | 内部网络 + `icc: false` |

---

## Docker 安全基线检查脚本

将以下脚本保存为 `docker-security-check.sh` 并在服务器上运行：

```bash
#!/bin/bash
# Docker 安全基线检查脚本

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "========================================"
echo "  Docker 安全基线检查"
echo "========================================"
echo ""

# 1. 检查 Docker 版本
DOCKER_VER=$(docker version --format '{{.Server.Version}}')
echo -e "Docker 版本: $DOCKER_VER"

# 2. 检查 Docker 守护进程配置
if [ -f /etc/docker/daemon.json ]; then
  echo -e "${GREEN}✓${NC} daemon.json 存在"
  if grep -q '"icc": false' /etc/docker/daemon.json; then
    echo -e "${GREEN}✓${NC} 容器间通信已禁用 (icc: false)"
  else
    echo -e "${RED}✗${NC} 容器间通信未限制"
  fi
else
  echo -e "${RED}✗${NC} daemon.json 不存在"
fi

# 3. 检查运行中容器
RUNNING=$(docker ps -q | wc -l)
echo -e "运行中容器数: $RUNNING"

# 4. 检查非 root 容器
for c in $(docker ps -q); do
  user=$(docker inspect --format '{{.Config.User}}' $c)
  name=$(docker inspect --format '{{.Name}}' $c | cut -d'/' -f2)
  if [ -z "$user" ] || [ "$user" == "0" ] || [ "$user" == "root" ]; then
    echo -e "${RED}✗${NC} 容器 '$name' 以 root 运行"
  else
    echo -e "${GREEN}✓${NC} 容器 '$name' 以用户 $user 运行"
  fi
done

# 5. 检查镜像漏洞（需要 Trivy）
if command -v trivy &> /dev/null; then
  echo -e "\n检查关键镜像漏洞..."
  for img in $(docker images --format '{{.Repository}}:{{.Tag}}' | grep -v '<none>' | sort -u); do
    critical=$(trivy image --severity CRITICAL --quiet --no-progress $img 2>/dev/null | grep -c "CRITICAL:" || true)
    if [ "$critical" -gt 5 ]; then
      echo -e "${RED}✗${NC} $img — $critical 个严重漏洞"
    else
      echo -e "${GREEN}✓${NC} $img — 安全 (严重漏洞 <= 5)"
    fi
  done
fi

echo ""
echo "========================================"
echo "  检查完成"
echo "========================================"
```

## 总结

Docker 安全不是一次性的工作，而是一个持续的过程。以下是我们的核心建议：

1. **从基础做起**：非 root 运行 + 只读文件系统 + 限制 Capabilities — 这三步就能阻挡 80% 的常见攻击
2. **自动化扫描**：在 CI/CD 流程中集成 Trivy 镜像扫描
3. **使用最小基础镜像**：Alpine 和 Distroless 是最安全的选择
4. **运行时防护**：Seccomp + AppArmor/SELinux + Falco 三重保护
5. **网络隔离**：使用内部网络，禁止不必要的容器间通信

> 💡 **记住**：安全的容器化应用 = 安全的基础镜像 + 最小权限原则 + 运行时加固 + 持续监控。

## 参考资源

- [Docker 安全官方文档](https://docs.docker.com/engine/security/)
- [CIS Docker Benchmark](https://www.cisecurity.org/benchmark/docker)
- [Trivy GitHub](https://github.com/aquasecurity/trivy)
- [Falco 运行时安全](https://falco.org/)
- [Docker Content Trust 文档](https://docs.docker.com/engine/security/trust/)

---

*本文发布于 [SelfVPS 指南](https://selfvps.net)，转载请注明出处。*
