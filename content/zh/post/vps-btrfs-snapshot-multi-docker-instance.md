---
title: "VPS 低成本扩容：Btrfs 快照 + 多实例 Docker，让一台机器跑出三台的能力"
description: "Btrfs 子卷 + 快照，让一台 VPS 轻松承载 3-5 套独立部署：秒级回滚配置、零成本克隆环境、磁盘占用直接砍半。本文从零搭建子卷、配置自动快照、多 Docker 实例隔离，附完整命令与监控脚本。"
date: 2026-10-22T10:00:00+08:00
lastmod: 2026-10-22T10:00:00+08:00
slug: "vps-btrfs-snapshot-multi-docker-instance"
image: /images/posts/vps-btrfs-snapshot-multi-docker-instance/featured.png
tags: ["VPS", "Btrfs", "快照", "Docker", "自托管", "存储优化", "运维", "成本控制"]
categories: ["VPS 运维", "存储优化"]
draft: false
aliases: [/zh/post/vps-btrfs-snapshot-multi-docker-instance/]
---

## 引言：为什么你的 VPS 总是"差一点点"

你有一台 2 核 4G、40G SSD 的 VPS，想同时跑三个项目：一个个人博客、一个内部工具、一个 AI 推理服务。传统做法——各自买一台 VPS，月账单轻松破百。或者硬挤在一台里，配置改坏了不敢动，环境搞脏了只能重装，磁盘塞满了没地方扩容。

**其实你可以不升级硬件，只换存储层，就让一台 VPS 同时支撑 3-5 套完全独立的部署。**

靠的就是 Linux 的 **Btrfs 文件系统**：子卷（subvolume）+ 快照（snapshot）。它给你三样云厂商通常要额外收费的能力：

1. **秒级快照回滚**：改崩配置 5 秒内回退到上一版，比重装快 100 倍
2. **零成本克隆环境**：新环境从老环境复制一份，只占差值空间
3. **磁盘占用砍半**：相同基础镜像 + 配置的多套部署，只存一次共享块

本文提供一套完整的生产级方案，包含：

- Btrfs 子卷布局设计（Docker / 项目 / 数据分离）
- 自动化定时快照 + 智能清理策略
- 多 Docker 实例隔离（不同子卷、不同用户、不同端口）
- 秒级回滚与克隆的操作手册
- 磁盘用量监控脚本（接入 Prometheus / 微信告警）

> **核心结论**：Btrfs 快照的额外磁盘成本接近 0，但带来的"多实例并行 + 随时回滚"能力，让你在不加硬件的前提下把单台 VPS 的利用率提升 2-3 倍。

## 一、Btrfs 能给你什么：三个能力

| 能力 | 传统 ext4 | Btrfs | 实际价值 |
|------|-----------|-------|---------|
| 快照 | 无（需 LVM 外挂） | 原生，CoW 秒级 | 改崩配置 5 秒回滚 |
| 克隆 | 全量拷贝占双份 | 只存差值 | 多套部署磁盘减半 |
| 空间管理 | 固定分区 | 多子卷共享池 | 灵活分配，不浪费 |

Btrfs 的写时复制（Copy-on-Write）意味着：快照不是"再存一份"，而是记录"哪些块变了"。一个 40G 的部署做快照，如果只改了 500MB 配置，快照本身只占 500MB。

## 二、磁盘布局设计

先确认磁盘情况，规划子卷层级：

```bash
# 查看磁盘与分区
lsblk
# 假设系统盘是 /dev/vda，根分区 /dev/vda1

# 检查是否已用 Btrfs
df -Th /
# 如果是 ext4，需要先迁移（见下节）；如果已是 btrfs 直接进下一步
```

**推荐子卷层级**（把"会频繁变化的配置"和"稳定的基础镜像"分开）：

```
/ (btrfs 根)
├── @            系统默认子卷（OS 用）
├── @docker      Docker 的 /var/lib/docker（镜像+容器）
├── @projects    各项目代码目录
├── @data        持久化数据（数据库、上传文件）
└── @snapshots   快照存放区（定时任务写这里）
```

为什么要拆 `@docker`？因为 Docker 的镜像层是只读的、可跨实例共享的。把 Docker 独立子卷后，多套部署拉取相同基础镜像时，只存一份。

### 迁移到 Btrfs（如果是 ext4）

```bash
# 1. 创建 btrfs 分区（假设 /dev/vda 整盘）
# 先备份！
dd if=/dev/vda1 of=/backup-root.img bs=4M status=progress  # 整盘备份到异机

# 2. 格式化
mkfs.btrfs /dev/vda1

# 3. 挂载并建子卷
mount /dev/vda1 /mnt
btrfs subvolume create /mnt/@docker
btrfs subvolume create /mnt/@projects
btrfs subvolume create /mnt/@data
btrfs subvolume create /mnt/@snapshots

# 4. 把原 ext4 数据灌进 /mnt
# 调整 /etc/fstab 用 subvol 参数挂载各子卷
```

> 生产环境务必先在测试机演练，且保留整盘镜像再动手。

## 三、创建并挂载子卷

```bash
# 确认 btrfs 已挂载
mount | grep btrfs

# 创建子卷（幂等，已存在不报错）
btrfs subvolume create /@docker 2>/dev/null || true
btrfs subvolume create /@projects 2>/dev/null || true
btrfs subvolume create /@data 2>/dev/null || true
btrfs subvolume create /@snapshots 2>/dev/null || true

# 验证
btrfs subvolume list /
```

修改 `/etc/fstab`，让各子卷独立挂载：

```
# /etc/fstab 片段（假设 btrfs 根分区是 /dev/vda1）
/dev/vda1  /mnt-docker    btrfs  subvol=@docker,compress=zstd:1  0 0
/dev/vda1  /mnt-projects  btrfs  subvol=@projects,compress=zstd:1 0 0
/dev/vda1  /mnt-data      btrfs  subvol=@data,compress=zstd:1     0 0
/dev/vda1  /mnt-snapshots btrfs  subvol=@snapshots,compress=zstd:1 0 0
```

`compress=zstd:1` 对文本/日志压缩率极高，再省一点空间。挂载点：

```bash
mkdir -p /opt/docker /opt/projects /opt/data /opt/snapshots
# 然后按 fstab 把 subvol 指向 /opt/docker 等
mkdir -p /opt/docker && echo "/dev/vda1 /opt/docker btrfs subvol=@docker,compress=zstd:1 0 0" >> /etc/fstab
mount -a
```

## 四、把 Docker 指向独立子卷

```bash
# 先停 docker
systemctl stop docker

# 编辑 /etc/docker/daemon.json
cat > /etc/docker/daemon.json <<EOF
{
  "data-root": "/opt/docker"
}
EOF

# 启动（旧镜像会惰性迁移，首次可能慢）
systemctl start docker
docker info | grep "Docker Root Dir"
```

现在 Docker 的所有层都落在 `@docker` 子卷。多套部署共享镜像层时，物理磁盘只存一份。

## 五、多 Docker 实例隔离

一台 VPS 想跑 3 套独立部署，最干净的做法是**子卷 + 独立数据目录**，而不是开多套 Docker daemon（太重）。用三个数据目录对应三套项目：

```bash
# 三套项目各占一个子卷挂载点
mkdir -p /opt/projects/blog /opt/projects/tool /opt/projects/ai-infer
```

各项目用独立的 `docker-compose` 与独立端口，避免冲突：

```yaml
# blog/docker-compose.yml（端口 8081）
services:
  web:
    image: nginx:1.27
    volumes: ["./html:/usr/share/nginx/html"]
    ports: ["8081:80"]
```

```yaml
# tool/docker-compose.yml（端口 8082）
services:
  app:
    image: ghcr.io/myorg/tool:latest
    ports: ["8082:3000"]
    environment:
      - DB_HOST=localhost
```

```yaml
# ai-infer/docker-compose.yml（端口 8083）
services:
  ollama:
    image: ollama/ollama
    ports: ["8083:11434"]
    volumes: ["/opt/data/ollama:/root/.ollama"]
```

隔离要点：

- **端口不冲突**：8081 / 8082 / 8083
- **数据落在 `@data`**：持久化数据放 `/opt/data/*`，与代码分离
- **镜像共享**：三套都基于 `nginx:1.27`，物理只存一份
- **资源限额**：每套 compose 加 `mem_limit`，防止某一套吃光内存

```yaml
services:
  app:
    mem_limit: 1g
    cpus: 0.8
```

## 六、秒级快照回滚

这是 Btrfs 的杀手锏。改崩配置前打快照，5 秒回退。

```bash
# 给 @projects 打快照（存到 @snapshots 下）
btrfs snapshot -r /@projects /@snapshots/projects-$(date +%Y%m%d%H%M%S)
# -r 只读，更省空间

# 改崩了？把快照挂回去
mkdir -p /opt/projects && umount /opt/projects
mount -o subvol=@snapshots/projects-20261022103000 /dev/vda1 /opt/projects
# 业务无感知恢复，比重装快两个数量级
```

**日常操作习惯**：改任何生产配置前，先 `btrfs snapshot`。改崩就回滚，不丢数据、不重启服务。

## 七、自动化定时快照 + 清理

用 systemd timer 或 crontab，每天凌晨打快照，保留 7 份：

```bash
cat > /usr/local/sbin/btrfs-snap.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
SNAP_ROOT=/opt/snapshots
STAMP=$(date +%Y%m%d_%H%M%S)

# 给三个子卷打快照
for sv in @projects @data @docker; do
  btrfs subvolume list -s -o / | grep -q "/${sv#@}$" || true
  btrfs snapshot -r "/${sv#@}" "$SNAP_ROOT/${sv#@}-${STAMP}" 2>/dev/null || true
done

# 清理：每个子卷只保留最近 7 份
for prefix in projects data docker; do
  ls -1t "$SNAP_ROOT/${prefix}-" 2>/dev/null | tail -n +8 | while read s; do
    btrfs subvolume delete "$s" 2>/dev/null || true
  done
done
echo "[btrfs-snap] snapshot @ $STAMP done"
EOF
chmod +x /usr/local/sbin/btrfs-snap.sh
```

```bash
# 每天 03:00 执行
(crontab -l 2>/dev/null; echo "0 3 * * * /usr/local/sbin/btrfs-snap.sh >> /var/log/btrfs-snap.log 2>&1") | crontab -
```

## 八、零成本克隆一套环境

要给团队发一套和生产一致的环境？不用重装，克隆快照即可：

```bash
# 克隆一个"干净"项目快照到新子卷
btrfs subvolume create /@projects-dev
btrfs snapshot /@snapshots/projects-20261022030000 /@projects-dev
# 瞬间完成，物理只占差值
# 挂载 /opt/projects-dev 作为开发环境
```

开发环境改得再烂，与生产互不影响；需要时再删除子卷，空间自动归还。

## 九、磁盘用量监控 + 告警

Btrfs 是"共享池"，单个子卷满了不代表整体满。监控要盯总池 + 各子卷：

```bash
cat > /usr/local/sbin/btrfs-check.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
# 取 btrfs 根池用量
LINE=$(df -h | awk 'NR>1 && $2 ~ /G/ && $1 ~ /dev/ {print}')
USAGE=$(df -h /opt/projects | awk 'NR==2{print $5}' | tr -d '%')
echo "[$(date '+%F %T')] btrfs usage=${USAGE}%"

# 超过 85% 触发告警（示例接入微信/Telegram）
if [ "${USAGE:0:1}" -ge 8 ] && [ "$USAGE" -ge 85 ]; then
  curl -s -X POST "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY" \
    -H 'Content-Type: application/json' \
    -d "{\"msgtype\":\"text\",\"text\":{\"content\":\"⚠️ VPS Btrfs 用量 ${USAGE}%，请扩容或清理\"}}" || true
fi
EOF
chmod +x /usr/local/sbin/btrfs-check.sh

# 每 10 分钟检查一次
(crontab -l 2>/dev/null; echo "*/10 * * * * /usr/local/sbin/btrfs-check.sh") | crontab -
```

## 十、常见坑与注意事项

1. **快照不是备份**：快照防"误操作/改崩"，不防"磁盘坏/误删整个 btrfs"。重要数据仍需异地备份（见本站 Restic/S3 系列文章）。
2. **压缩选 zstd 别选 zlib**：zstd 压缩比更高、速度更快，`compress=zstd:1` 即可。
3. **别在快照里改业务**：`-r` 只读快照是"基线"，要改请新建子卷再克隆。
4. **内存是瓶颈**：Btrfs 省磁盘不省内存。多套 Docker 实例要配 `mem_limit`，2G 内存跑 3 套轻服务没问题，跑 3 套大模型会 OOM。
5. **迁移风险**：ext4→btrfs 迁移务必先整盘备份。生产环境建议在新机先演练全流程。
6. **监控盯总池**：Btrfs 共享池，单分区 100% 不代表没空间，用 `btrfs fi usage /` 看真实剩余。

## 总结

| 能力 | 命令 / 做法 | 效果 |
|------|-------------|------|
| 秒级回滚 | `btrfs snapshot` + 挂载 | 改崩 5s 恢复 |
| 多实例隔离 | 子卷 + 独立数据目录 | 一套 VPS 跑 3-5 套 |
| 磁盘减半 | 镜像层共享 + zstd 压缩 | 多套部署只存一份 |
| 零成本克隆 | `btrfs subvolume create` | 瞬时复制生产环境 |
| 自动快照 | systemd/cron + 保留 7 份 | 无需人工 |

**一句话**：Btrfs 是你手里没花钱买的"云备份 + 克隆"能力。花一个下午把子卷、自动快照、多实例隔离搭好，以后改配置敢大胆动手——因为你知道 5 秒就能回退。

相关：[Restic 自动备份到 S3](/zh/post/vps-restic-automated-backup-s3/) · [VPS 磁盘清理与自动扩容](/zh/post/vps-disk-cleanup-auto-scaling/)
