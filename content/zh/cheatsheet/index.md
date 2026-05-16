---
title: "自托管速查表"
description: "Docker、Nginx、Linux、SSL、systemd 常用命令速查——VPS 自托管必备"
date: 2026-05-16T10:00:00+08:00
slug: "cheatsheet"
---

## Docker

```bash
# --- 容器生命周期 ---
docker ps                      # 列出运行中的容器
docker ps -a                   # 列出所有容器（含已停止）
docker start <容器名/ID>       # 启动已停止的容器
docker stop <容器名/ID>        # 优雅停止容器
docker restart <容器名/ID>     # 重启容器
docker rm <容器名/ID>          # 删除已停止的容器
docker rm -f <容器名/ID>       # 强制删除运行中的容器

# --- 镜像管理 ---
docker images                  # 列出已下载的镜像
docker pull <镜像名>:<标签>    # 拉取镜像（如 n8nio/n8n:latest）
docker rmi <镜像名>            # 删除镜像
docker build -t <名>:<标签> .  # 从 Dockerfile 构建镜像
docker system prune -a         # 清除所有未使用的镜像、容器、网络

# --- 日志与调试 ---
docker logs <容器名>           # 查看日志
docker logs -f <容器名>        # 跟踪日志输出（类似 tail -f）
docker logs --tail 100 <容器>  # 只看最后 100 行
docker exec -it <容器> /bin/sh # 进入容器 shell
docker exec -it <容器> bash    # 进入容器 bash（如果有）
docker inspect <容器>          # 查看容器详细信息（JSON 格式）

# --- Compose ---
docker compose up -d           # 后台启动所有服务
docker compose down            # 停止并删除容器
docker compose down -v         # 同时删除数据卷（⚠️ 会丢数据）
docker compose logs -f         # 跟踪所有服务的日志
docker compose pull            # 拉取所有服务的最新镜像
docker compose restart         # 重启所有服务
docker compose ps              # 查看 compose 项目的容器列表

# --- 数据卷和网络 ---
docker volume ls               # 列出数据卷
docker volume prune            # 删除未使用的数据卷
docker network ls              # 列出网络
docker network create <名称>   # 创建自定义网络
```

## Nginx

```bash
# --- 基本命令 ---
nginx -t                       # 测试配置文件语法
nginx -s reload                # 重载配置（不停机）
nginx -s stop                  # 强制停止
nginx -s quit                  # 优雅停止（处理完当前请求）
systemctl restart nginx        # 通过 systemd 重启
systemctl status nginx         # 检查状态
journalctl -u nginx --no-pager # 查看 nginx 日志

# --- 常用文件路径 ---
/etc/nginx/nginx.conf          # 主配置文件
/etc/nginx/sites-available/    # 站点配置（通过软链接启用）
/etc/nginx/sites-enabled/      # 已启用的站点配置
/etc/nginx/conf.d/             # 额外配置片段
/var/log/nginx/access.log      # 访问日志
/var/log/nginx/error.log       # 错误日志
/var/www/html/                 # 默认网站根目录
```

```nginx
# --- 反向代理模板 ---
server {
    listen 80;
    server_name example.com;

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```nginx
# --- SSL + Let's Encrypt ---
server {
    listen 443 ssl;
    server_name example.com;

    ssl_certificate     /etc/letsencrypt/live/example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/example.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        # WebSocket 支持（N8N 等需要）
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}

server {
    listen 80;
    server_name example.com;
    return 301 https://$server_name$request_uri;  # HTTP → HTTPS 跳转
}
```

```bash
# --- Certbot ---
certbot --nginx -d example.com           # 申请证书并自动配置 nginx
certbot renew                            # 续期所有证书
certbot renew --dry-run                  # 测试续期（不实际执行）
certbot certificates                      # 列出所有证书
```

## Linux (Ubuntu/Debian)

```bash
# --- 系统信息 ---
uname -a                    # 完整的系统信息
cat /etc/os-release         # 操作系统版本
hostnamectl                 # 主机名 + 系统详情
free -h                     # 内存使用情况（人类可读格式）
df -h                       # 磁盘使用情况
du -sh *                    # 当前目录下各文件夹大小
uptime                      # 系统运行时长
top / htop                  # 进程监控器
lscpu                       # CPU 信息

# --- 文件操作 ---
ls -lah                     # 列出文件（含权限、大小）
cp -r <源> <目标>           # 递归复制目录
mv <源> <目标>              # 移动/重命名
rm -rf <目录>               # 删除目录及内容（⚠️ 小心使用）
find / -name "文件名"       # 按文件名搜索
grep -r "关键词" /路径      # 递归搜索文本内容
wc -l <文件>                # 统计文件行数

# --- 权限管理 ---
chmod 755 <文件>            # rwxr-xr-x（所有者全部，其他只读执行）
chmod 600 <文件>            # rw-------（仅所有者可读写）
chown 用户:组 <文件>        # 修改文件所有者和组
chown -R 用户:组 <目录>     # 递归修改目录所有权

# --- 进程管理 ---
ps aux                      # 列出所有运行中的进程
ps aux | grep <名称>        # 查找特定进程
kill <PID>                  # 按进程 ID 终止
kill -9 <PID>               # 强制终止
pkill <名称>                # 按名称终止进程
nohup <命令> &              # 后台运行，退出终端也不停止

# --- 网络工具 ---
ss -tlnp                    # 查看监听中的 TCP 端口（含进程）
ss -tulpn                   # 查看所有监听端口（TCP + UDP）
curl -I https://example.com # 查看 HTTP 响应头
curl -s ifconfig.me         # 获取公网 IP
ping -c 4 <主机>            # 测试网络连通性
dig <域名>                  # DNS 查询
mtr <主机>                  # 网络诊断（可替代 traceroute）
```

## systemd

```bash
# --- 服务管理 ---
systemctl start <服务名>       # 启动服务
systemctl stop <服务名>        # 停止服务
systemctl restart <服务名>     # 重启服务
systemctl enable <服务名>      # 设置开机自启
systemctl disable <服务名>     # 取消开机自启
systemctl status <服务名>      # 查看状态 + 最近日志
systemctl daemon-reload        # 修改 unit 文件后重载

# --- 查看日志 ---
journalctl -u <服务名>         # 查看服务的日志
journalctl -u <服务名> -f      # 跟踪日志（类似 tail -f）
journalctl -u <服务名> --no-pager | tail -50  # 看最后 50 行
```

## SSL / 证书

```bash
# --- 快速查看证书有效期 ---
openssl s_client -connect example.com:443 -servername example.com \
  </dev/null 2>/dev/null | openssl x509 -noout -dates

# --- 生成自签名证书（测试用） ---
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout /etc/ssl/private/selfsigned.key \
  -out /etc/ssl/certs/selfsigned.crt

# --- 远程查看证书过期时间 ---
echo | openssl s_client -connect example.com:443 -servername example.com \
  2>/dev/null | openssl x509 -noout -enddate
```

## 快速参考

| 场景 | 命令 |
|------|------|
| 重载 nginx 配置 | `nginx -s reload` |
| 检查 nginx 语法 | `nginx -t` |
| 重启 Docker | `systemctl restart docker` |
| 查看端口占用 | `ss -tulpn \| grep :端口号` |
| 查看目录磁盘占用 | `du -sh /路径` |
| 查找 >100MB 大文件 | `find / -type f -size +100M -exec ls -lh {} \;` |
| 最近内核日志 | `dmesg \| tail -20` |
| 防火墙规则 | `ufw status verbose` |
