---
title: "Docker Security Hardening: Top 10 Best Practices for Container Security"
description: "A comprehensive guide to Docker container security — from image scanning and non-root execution to Seccomp/AppArmor configuration — harden your containers for production"
date: 2026-05-22T10:00:00+08:00
lastmod: 2026-05-22T10:00:00+08:00
slug: "docker-security-hardening"
image: /images/posts/docker-security-hardening/featured.png
tags: ["Docker", "security", "containers", "DevOps", "Linux", "best-practices", "cloud-native"]
categories: ["Security & Operations"]
---

## Introduction

Docker revolutionized how we deploy applications, but **"containerized" doesn't mean "secure"**. The default Docker configuration optimizes for ease of use, not security. In production, unhardened containers can be an easy entry point for attackers.

This guide covers **10 Docker container security best practices** — from basic configuration to advanced hardening — helping you enjoy containerization benefits while keeping your systems safe.

---

## 1. Run Containers as a Non-Root User ⭐

**This is the single most important security practice!**

Docker runs container processes as root by default. If an attacker escapes the container through a vulnerability, they gain root access to the host immediately.

```dockerfile
# ❌ Insecure — default root
FROM node:18
COPY . /app
CMD ["node", "server.js"]

# ✅ Secure — non-root user
FROM node:18
RUN groupadd -r appgroup && useradd -r -g appgroup appuser
USER appuser
COPY . /app
CMD ["node", "server.js"]
```

**Specify user in docker-compose.yml:**

```yaml
services:
  app:
    image: myapp:latest
    user: "1000:1000"  # Run as non-root user
```

**Runtime override:**

```bash
docker run --user 1000:1000 myapp
```

## 2. Use Read-Only Filesystems

Container filesystems are writable by default, giving attackers the ability to write malicious files.

```yaml
services:
  app:
    image: myapp:latest
    read_only: true    # Root filesystem is read-only
    tmpfs:
      - /tmp           # Only temp directories are writable
      - /var/run
    volumes:
      - app_data:/app/data  # Use volumes for write-needed paths
```

## 3. Drop Unnecessary Linux Capabilities

Docker containers come with many Linux capabilities by default. Follow the **principle of least privilege** — drop all capabilities and add back only what's needed.

```bash
# Check current capabilities
docker run --rm alpine getpcaps 1

# Drop all capabilities, add only what's needed
docker run --rm \
  --cap-drop=ALL \
  --cap-add=NET_BIND_SERVICE \
  nginx:alpine
```

**docker-compose configuration:**

```yaml
services:
  app:
    image: nginx:alpine
    cap_drop:
      - ALL
    cap_add:
      - NET_BIND_SERVICE
      - NET_RAW
```

### Common Capabilities Reference

| Capability | What It Does | Risk Level |
|------------|-------------|------------|
| `NET_BIND_SERVICE` | Bind to low ports (<1024) | 🟢 Low |
| `CHOWN` | Change file ownership | 🟡 Medium |
| `SYS_ADMIN` | System administration (extremely dangerous) | 🔴 High |
| `SYS_PTRACE` | Debug processes | 🔴 High |
| `NET_ADMIN` | Network configuration | 🔴 High |
| `SYS_MODULE` | Load kernel modules | 🔴 Critical |

## 4. Use Seccomp to Restrict System Calls

Seccomp (Secure Computing Mode) limits which system calls a container can execute. Docker provides a secure default profile, but you can define stricter rules.

```bash
# Check current seccomp mode
docker run --rm -it alpine cat /proc/self/status | grep Seccomp
# Output: Seccomp: 2  (2 = filtering mode)

# Use default seccomp
docker run --rm --security-opt seccomp=default alpine

# Use custom seccomp profile
docker run --rm \
  --security-opt seccomp=/path/to/custom.json \
  alpine
```

**Custom seccomp example (only allow necessary syscalls):**

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

## 5. Use AppArmor or SELinux

### AppArmor (Ubuntu/Debian)

```bash
# Use Docker's default AppArmor profile
docker run --rm --security-opt apparmor=docker-default alpine

# Load a custom profile
sudo apparmor_parser -r -W /etc/apparmor.d/custom-docker
docker run --rm --security-opt apparmor=custom-docker alpine
```

### SELinux (CentOS/RHEL/Fedora)

```bash
# Enable SELinux security labels
docker run --rm --security-opt label=level:TopSecret alpine

# Allow access to specific directories
docker run --rm -v /data:/data:Z alpine
```

## 6. Image Security Scanning

Scan images for vulnerabilities before deployment.

### Trivy — Most Popular Image Scanner

```bash
# Install Trivy
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
  aquasec/trivy image nginx:alpine

# Check critical vulnerabilities only
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
  aquasec/trivy image --severity CRITICAL,HIGH nginx:1.25

# CI/CD integration (fails on critical)
trivy image --exit-code 1 --severity CRITICAL myapp:latest
```

### Docker Scout (Built-in)

```bash
# Quick vulnerability view
docker scout quickview nginx:alpine

# Compare images
docker scout compare nginx:alpine nginx:1.25-alpine
```

### Recommended Base Images

| Image | Size | CVEs | Recommendation |
|-------|------|------|---------------|
| `alpine:3.19` | ~7MB | 0-5 | ✅ Preferred |
| `distroless` | ~15MB | 0-3 | ✅ Very secure |
| `slim` (e.g., node:slim) | ~50MB | 10-30 | ⚠️ Moderate |
| `ubuntu:22.04` | ~77MB | 30-100+ | ❌ Not recommended |
| `debian:bookworm` | ~124MB | 50-150+ | ❌ Not recommended |

> **Rule of thumb**: Prefer `alpine` or `distroless` base images. They're smaller and have a smaller attack surface.

## 7. Limit Resource Usage

Restrict CPU, memory, and disk usage to prevent DoS attacks or resource exhaustion.

```yaml
services:
  app:
    image: myapp:latest
    deploy:
      resources:
        limits:
          cpus: '0.50'       # Max 0.5 CPU cores
          memory: 512M       # Max 512MB memory
          pids: 100          # Limit number of processes
        reservations:
          cpus: '0.25'       # Reserve 0.25 cores
          memory: 256M       # Reserve 256MB memory
    oom_kill_disable: false   # Allow OOM killer
    ulimits:
      nofile:
        soft: 1024
        hard: 2048
    storage_opt:
      size: '10G'            # Disk limit
```

**Command-line equivalent:**

```bash
docker run --rm \
  --memory="512m" \
  --cpus="0.5" \
  --pids-limit=100 \
  --storage-opt size=10G \
  myapp
```

## 8. Use Docker Content Trust (Image Signing)

Ensure only signed, trusted images are run in production.

```bash
# Enable content trust
export DOCKER_CONTENT_TRUST=1

# Pulling unsigned images will now fail
docker pull myapp:latest
# Error: remote trust data does not exist

# Push and sign images
docker push myapp:latest
# Will prompt for signing key

# Enable globally in docker-compose
# .env file
DOCKER_CONTENT_TRUST=1
```

**CI/CD signing configuration:**

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

## 9. Security Logging & Auditing

### Configure Docker Audit Logs

```bash
# Audit Docker daemon activity
sudo auditctl -w /usr/bin/docker -p wa -k docker
sudo auditctl -w /var/lib/docker -p wa -k docker
sudo auditctl -w /etc/docker -p wa -k docker

# View logs
sudo ausearch -k docker --start today
```

### Container Logging Best Practices

```yaml
services:
  app:
    image: myapp:latest
    logging:
      driver: "json-file"
      options:
        max-size: "10m"      # 10MB max per log file
        max-file: "3"        # Keep 3 rotated files
        compress: "true"     # Compress old logs
    # Avoid sensitive info in logs
    environment:
      - DB_PASSWORD_FILE=/run/secrets/db_password
```

### Falco — Runtime Security Monitoring

```bash
# Install Falco (container-native runtime security)
docker run --rm -i \
  --privileged \
  -v /var/run/docker.sock:/host/var/run/docker.sock \
  -v /proc:/host/proc:ro \
  falcosecurity/falco:latest

# Falco detects:
# - Interactive shells spawned in containers
# - Sensitive file reads (/etc/shadow)
# - Unexpected network connections
# - Privilege escalation attempts
```

## 10. Network Security Isolation

### Use Custom Networks

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
      - internal   # Database is internal only

  redis:
    image: redis:7-alpine
    networks:
      - internal

networks:
  internal:
    internal: true       # ❗ Block external access
  traefik_proxy:
    external: true
```

### Disable Inter-Container Communication (enabled by default)

```yaml
# docker-compose.yml
services:
  app:
    image: myapp:latest
    network_mode: "none"  # Full isolation

# Or disable at Docker daemon level
```

```bash
# Configure /etc/docker/daemon.json
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

# Restart Docker
sudo systemctl restart docker
```

---

## Docker Security Quick Reference

| # | Practice | Command/Config |
|---|----------|----------------|
| 1 | Non-root user | `USER appuser` in Dockerfile |
| 2 | Read-only FS | `read_only: true` in compose |
| 3 | Drop capabilities | `--cap-drop=ALL --cap-add=...` |
| 4 | Seccomp filter | `--security-opt seccomp=...` |
| 5 | AppArmor/SELinux | `--security-opt apparmor=...` |
| 6 | Image scanning | `trivy image myapp` |
| 7 | Resource limits | `--memory=512m --cpus=0.5` |
| 8 | Content trust | `DOCKER_CONTENT_TRUST=1` |
| 9 | Security auditing | Falco + auditd |
| 10 | Network isolation | Internal network + `icc: false` |

---

## Docker Security Baseline Check Script

Save the following script as `docker-security-check.sh` and run it on your server:

```bash
#!/bin/bash
# Docker Security Baseline Check Script

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "========================================"
echo "  Docker Security Baseline Check"
echo "========================================"
echo ""

# 1. Check Docker version
DOCKER_VER=$(docker version --format '{{.Server.Version}}')
echo -e "Docker version: $DOCKER_VER"

# 2. Check Docker daemon config
if [ -f /etc/docker/daemon.json ]; then
  echo -e "${GREEN}✓${NC} daemon.json exists"
  if grep -q '"icc": false' /etc/docker/daemon.json; then
    echo -e "${GREEN}✓${NC} Inter-container communication disabled (icc: false)"
  else
    echo -e "${RED}✗${NC} Inter-container communication not restricted"
  fi
else
  echo -e "${RED}✗${NC} daemon.json not found"
fi

# 3. Count running containers
RUNNING=$(docker ps -q | wc -l)
echo -e "Running containers: $RUNNING"

# 4. Check for root containers
for c in $(docker ps -q); do
  user=$(docker inspect --format '{{.Config.User}}' $c)
  name=$(docker inspect --format '{{.Name}}' $c | cut -d'/' -f2)
  if [ -z "$user" ] || [ "$user" == "0" ] || [ "$user" == "root" ]; then
    echo -e "${RED}✗${NC} Container '$name' running as root"
  else
    echo -e "${GREEN}✓${NC} Container '$name' running as user $user"
  fi
done

# 5. Check for critical vulnerabilities (requires Trivy)
if command -v trivy &> /dev/null; then
  echo -e "\nChecking for critical vulnerabilities..."
  for img in $(docker images --format '{{.Repository}}:{{.Tag}}' | grep -v '<none>' | sort -u); do
    critical=$(trivy image --severity CRITICAL --quiet --no-progress $img 2>/dev/null | grep -c "CRITICAL:" || true)
    if [ "$critical" -gt 5 ]; then
      echo -e "${RED}✗${NC} $img — $critical critical vulnerabilities"
    else
      echo -e "${GREEN}✓${NC} $img — safe (≤ 5 critical)"
    fi
  done
fi

echo ""
echo "========================================"
echo "  Check Complete"
echo "========================================"
```

## Summary

Docker security isn't a one-time task — it's an ongoing process. Here are our core recommendations:

1. **Start with the basics**: Non-root + read-only FS + drop capabilities — these three steps block 80% of common attacks
2. **Automate scanning**: Integrate Trivy into your CI/CD pipeline
3. **Use minimal base images**: Alpine and Distroless are the most secure choices
4. **Runtime protection**: Seccomp + AppArmor/SELinux + Falco provide triple-layer defense
5. **Network isolation**: Use internal networks, block unnecessary inter-container communication

> 💡 **Remember**: Secure containerized apps = secure base images + least privilege + runtime hardening + continuous monitoring.

## Resources

- [Docker Security Documentation](https://docs.docker.com/engine/security/)
- [CIS Docker Benchmark](https://www.cisecurity.org/benchmark/docker)
- [Trivy on GitHub](https://github.com/aquasecurity/trivy)
- [Falco Runtime Security](https://falco.org/)
- [Docker Content Trust Docs](https://docs.docker.com/engine/security/trust/)

---

*Published on [SelfVPS Guide](https://selfvps.net). All rights reserved.*
