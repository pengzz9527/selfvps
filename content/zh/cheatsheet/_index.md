---
title: "自托管速查表"
description: "实用的 VPS 自托管速查表——Docker 命令、Nginx 配置、Linux 运维常用命令一页掌握"
date: 2026-05-16T10:00:00+08:00
slug: "cheatsheet"
menu:
  main:
    weight: 55
    identifier: cheatsheet
---

## 自托管速查表

实用的 DevOps 和自托管常用命令速查。

### Docker 基础命令

```bash
# 查看运行中的容器
docker ps

# 查看所有容器
docker ps -a

# 启动/停止容器
docker start <container>
docker stop <container>

# 查看容器日志
docker logs -f <container>

# 进入容器 Shell
docker exec -it <container> /bin/bash

# 拉取镜像
docker pull <image>:<tag>

# 清理未使用的资源
docker system prune -a
```

### Docker Compose

```bash
# 启动所有服务
docker compose up -d

# 查看服务日志
docker compose logs -f

# 重新构建并启动
docker compose up -d --build

# 停止并删除容器
docker compose down

# 查看运行中的服务
docker compose ps
```

### Nginx 配置

```nginx
# HTTP 重定向到 HTTPS
server {
    listen 80;
    server_name example.com;
    return 301 https://$server_name$request_uri;
}

# 反向代理
server {
    listen 443 ssl;
    server_name example.com;
    
    location / {
        proxy_pass http://localhost:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### Linux 运维

```bash
# 查看磁盘使用
df -h

# 查看内存使用
free -h

# 查看系统负载
htop  # 或 top

# 查找大文件
du -sh /* 2>/dev/null | sort -rh | head -10

# 防火墙管理 (UFW)
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable
ufw status verbose

# SSL 证书 (acme.sh)
acme.sh --issue -d example.com --nginx
acme.sh --renew -d example.com --force
```
