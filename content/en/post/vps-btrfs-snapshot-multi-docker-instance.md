---
title: "VPS Cost Cutting: Btrfs Snapshots + Multi-Instance Docker — One Box Punches Like Three"
description: "Btrfs subvolumes + snapshots let a single VPS host 3–5 independent deployments: second-level rollback, zero-cost environment cloning, and ~50% less disk. This guide builds subvolumes, automated snapshots, and isolated multi-Docker instances with full commands and monitoring."
date: 2026-10-22T10:00:00+08:00
lastmod: 2026-10-22T10:00:00+08:00
slug: "vps-btrfs-snapshot-multi-docker-instance"
image: /images/posts/vps-btrfs-snapshot-multi-docker-instance/featured.png
tags: ["VPS", "Btrfs", "snapshots", "Docker", "self-hosting", "storage optimization", "DevOps", "cost control"]
categories: ["VPS Operations", "Storage Optimization"]
draft: false
aliases: [/en/post/vps-btrfs-snapshot-multi-docker-instance/]
---

## Introduction: Why Your VPS Is Always "One Thing Short"

You have a 2-core 4G, 40G SSD VPS and want to run three projects at once: a personal blog, an internal tool, and an AI inference service. The traditional move — buy three VPS instances, and the monthly bill blows past $100. Or cram them into one box, where you're scared to change any config, any broken environment means a full reinstall, and the disk is always one file away from full.

**You can host 3–5 fully independent deployments on a single VPS without upgrading hardware — just change the storage layer.**

That's what Linux's **Btrfs filesystem** gives you: subvolumes + snapshots. It unlocks three things cloud providers usually charge extra for:

1. **Second-level snapshot rollback** — a broken config is reverted in 5 seconds, 100× faster than a reinstall
2. **Zero-cost environment cloning** — copy a new environment from an old one; only the diff is stored
3. **Halved disk usage** — multiple deployments sharing the same base images + configs store shared blocks once

This guide provides a complete, production-grade playbook:

- Btrfs subvolume layout design (Docker / projects / data separation)
- Automated scheduled snapshots + smart cleanup
- Multi-Docker-instance isolation (different subvolumes, users, ports)
- Second-level rollback and cloning operation manual
- Disk-usage monitoring script (Prometheus / WeChat alerting)

> **Bottom line**: Btrfs snapshots cost nearly zero in extra disk, yet the "multi-instance + instant rollback" capability they enable lets you raise a single VPS's utilization 2–3× without new hardware.

## 1. What Btrfs Gives You: Three Capabilities

| Capability | ext4 | Btrfs | Real value |
|-----------|------|-------|-----------|
| Snapshots | None (needs LVM) | Native, CoW, instant | Revert a broken config in 5s |
| Cloning | Full copy, 2× space | Stores only the diff | Half the disk for many deployments |
| Space mgmt | Fixed partitions | Multiple subvolumes share one pool | Flexible allocation, no waste |

Btrfs's copy-on-write (CoW) means a snapshot is not "store another copy" — it records "which blocks changed." A 40G deployment that only changed 500MB of config produces a ~500MB snapshot.

## 2. Disk Layout Design

Check disk state and plan the subvolume hierarchy:

```bash
# Inspect disks and partitions
lsblk
# Assume the system disk is /dev/vda, root partition /dev/vda1

# Check whether Btrfs is already in use
df -Th /
# If it's ext4, migrate first (next section); if already btrfs, move on
```

**Recommended subvolume layout** (separate "frequently changing config" from "stable base images"):

```
/ (btrfs root)
├── @            default system subvolume (OS)
├── @docker      Docker's /var/lib/docker (images + containers)
├── @projects    project code directories
├── @data        persistent data (databases, uploads)
└── @snapshots   snapshot storage (written by scheduled jobs)
```

Why separate `@docker`? Docker image layers are read-only and shareable across instances. Isolating Docker into its own subvolume means multiple deployments pulling the same base image store it once.

### Migrating to Btrfs (if you're on ext4)

```bash
# 1. Create a btrfs partition (assume the whole disk /dev/vda)
# BACK UP FIRST.
dd if=/dev/vda1 of=/backup-root.img bs=4M status=progress  # full-disk backup elsewhere

# 2. Format
mkfs.btrfs /dev/vda1

# 3. Mount and create subvolumes
mount /dev/vda1 /mnt
btrfs subvolume create /mnt/@docker
btrfs subvolume create /mnt/@projects
btrfs subvolume create /mnt/@data
btrfs subvolume create /mnt/@snapshots

# 4. Load the old ext4 data into /mnt
# Update /etc/fstab to mount each subvolume with subvol=
```

> Always rehearse on a test machine first in production, and keep a full-disk image before you begin.

## 3. Create and Mount Subvolumes

```bash
# Confirm btrfs is mounted
mount | grep btrfs

# Create subvolumes (idempotent — no error if they exist)
btrfs subvolume create /@docker 2>/dev/null || true
btrfs subvolume create /@projects 2>/dev/null || true
btrfs subvolume create /@data 2>/dev/null || true
btrfs subvolume create /@snapshots 2>/dev/null || true

# Verify
btrfs subvolume list /
```

Update `/etc/fstab` so each subvolume mounts independently:

```
# /etc/fstab excerpt (assume btrfs root partition is /dev/vda1)
/dev/vda1  /opt/docker     btrfs  subvol=@docker,compress=zstd:1    0 0
/dev/vda1  /opt/projects   btrfs  subvol=@projects,compress=zstd:1  0 0
/dev/vda1  /opt/data       btrfs  subvol=@data,compress=zstd:1      0 0
/dev/vda1  /opt/snapshots  btrfs  subvol=@snapshots,compress=zstd:1 0 0
```

`compress=zstd:1` compresses text/logs heavily for a little extra savings. Mount points:

```bash
mkdir -p /opt/docker /opt/projects /opt/data /opt/snapshots
# Then bind each subvol to the mount point per fstab
mkdir -p /opt/docker && echo "/dev/vda1 /opt/docker btrfs subvol=@docker,compress=zstd:1 0 0" >> /etc/fstab
mount -a
```

## 4. Point Docker at the Isolated Subvolume

```bash
# Stop docker first
systemctl stop docker

# Edit /etc/docker/daemon.json
cat > /etc/docker/daemon.json <<EOF
{
  "data-root": "/opt/docker"
}
EOF

# Start it (old images migrate lazily; first run may be slow)
systemctl start docker
docker info | grep "Docker Root Dir"
```

All Docker layers now live in the `@docker` subvolume. When multiple deployments share image layers, they're stored once on physical disk.

## 5. Multi-Docker-Instance Isolation

To run three independent deployments on one VPS, the cleanest approach is **subvolumes + isolated data dirs**, not three Docker daemons (too heavy). Use three data directories for three projects:

```bash
# Each project gets its own subvolume mount point
mkdir -p /opt/projects/blog /opt/projects/tool /opt/projects/ai-infer
```

Each project uses its own `docker-compose` and distinct ports to avoid clashes:

```yaml
# blog/docker-compose.yml (port 8081)
services:
  web:
    image: nginx:1.27
    volumes: ["./html:/usr/share/nginx/html"]
    ports: ["8081:80"]
```

```yaml
# tool/docker-compose.yml (port 8082)
services:
  app:
    image: ghcr.io/myorg/tool:latest
    ports: ["8082:3000"]
    environment:
      - DB_HOST=localhost
```

```yaml
# ai-infer/docker-compose.yml (port 8083)
services:
  ollama:
    image: ollama/ollama
    ports: ["8083:11434"]
    volumes: ["/opt/data/ollama:/root/.ollama"]
```

Isolation essentials:

- **No port clashes**: 8081 / 8082 / 8083
- **Data lives in `@data`**: persistent data goes to `/opt/data/*`, separated from code
- **Shared images**: all three build on `nginx:1.27`; stored physically once
- **Resource limits**: add `mem_limit` to each compose so one project can't eat all RAM

```yaml
services:
  app:
    mem_limit: 1g
    cpus: 0.8
```

## 6. Second-Level Snapshot Rollback

This is Btrfs's killer feature. Snapshot before changing config; revert in 5 seconds.

```bash
# Snapshot @projects (stored under @snapshots)
btrfs snapshot -r /@projects /@snapshots/projects-$(date +%Y%m%d%H%M%S)
# -r = read-only, even cheaper

# Broke it? Mount the snapshot back
mkdir -p /opt/projects && umount /opt/projects
mount -o subvol=@snapshots/projects-20261022103000 /dev/vda1 /opt/projects
# Business recovers with zero downtime — two orders of magnitude faster than reinstall
```

**Daily habit**: before touching any production config, run `btrfs snapshot`. Break it and roll back — no data loss, no service restart.

## 7. Automated Scheduled Snapshots + Cleanup

Use a systemd timer or crontab to snapshot at 03:00 daily, keep 7:

```bash
cat > /usr/local/sbin/btrfs-snap.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
SNAP_ROOT=/opt/snapshots
STAMP=$(date +%Y%m%d_%H%M%S)

# Snapshot the three subvolumes
for sv in @projects @data @docker; do
  btrfs snapshot -r "/${sv#@}" "$SNAP_ROOT/${sv#@}-${STAMP}" 2>/dev/null || true
done

# Cleanup: keep only the 7 newest per subvolume
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
# Run daily at 03:00
(crontab -l 2>/dev/null; echo "0 3 * * * /usr/local/sbin/btrfs-snap.sh >> /var/log/btrfs-snap.log 2>&1") | crontab -
```

## 8. Zero-Cost Environment Cloning

Need a production-matching environment for the team? Don't reinstall — clone a snapshot:

```bash
# Clone a "clean" project snapshot into a new subvolume
btrfs subvolume create /@projects-dev
btrfs snapshot /@snapshots/projects-20261022030000 /@projects-dev
# Instant; physically stores only the diff
# Mount /opt/projects-dev as the dev environment
```

Mangle the dev environment as much as you like — it can't touch production; delete the subvolume when done and space is reclaimed automatically.

## 9. Disk-Usage Monitoring + Alerting

Btrfs is a "shared pool" — one subvolume being full doesn't mean the whole pool is. Monitor the total pool and each subvolume:

```bash
cat > /usr/local/sbin/btrfs-check.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
# Read btrfs pool usage
USAGE=$(df -h /opt/projects | awk 'NR==2{print $5}' | tr -d '%')
echo "[$(date '+%F %T')] btrfs usage=${USAGE}%"

# Fire an alert above 85% (example: WeChat / Telegram)
if [ "$USAGE" -ge 85 ]; then
  curl -s -X POST "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY" \
    -H 'Content-Type: application/json' \
    -d "{\"msgtype\":\"text\",\"text\":{\"content\":\"⚠️ VPS Btrfs usage ${USAGE}% — expand or clean up\"}}" || true
fi
EOF
chmod +x /usr/local/sbin/btrfs-check.sh

# Check every 10 minutes
(crontab -l 2>/dev/null; echo "*/10 * * * * /usr/local/sbin/btrfs-check.sh") | crontab -
```

## 10. Common Pitfalls & Caveats

1. **Snapshots are not backups**: snapshots guard against "misclick / broken config," not "disk failure / accidental delete of the whole btrfs." Critical data still needs off-site backup (see our Restic/S3 series).
2. **Use zstd, not zlib, for compression**: zstd is faster and better ratio; `compress=zstd:1` is enough.
3. **Don't edit inside a snapshot**: a `-r` read-only snapshot is a baseline; to change, create a new subvolume and clone into it.
4. **Memory is the real bottleneck**: Btrfs saves disk, not RAM. Isolated multi-Docker instances need `mem_limit` — 2G RAM is fine for three light services, but three large models will OOM.
5. **Migration risk**: ext4→btrfs migration demands a full-disk backup first. Rehearse the whole flow on a new machine in production.
6. **Watch the pool, not one partition**: Btrfs is a shared pool; one partition at 100% doesn't mean out of space. Use `btrfs fi usage /` for real remaining capacity.

## Summary

| Capability | Command / Method | Effect |
|-----------|-----------------|--------|
| Second-level rollback | `btrfs snapshot` + mount | Broken config reverted in 5s |
| Multi-instance isolation | Subvolumes + isolated data dirs | One VPS runs 3–5 deployments |
| Halved disk | Shared image layers + zstd | Many deployments stored once |
| Zero-cost cloning | `btrfs subvolume create` | Instantly clone production |
| Auto snapshots | systemd/cron + keep 7 | No manual work |

**In one sentence**: Btrfs is a "cloud backup + clone" capability you already own, for free. Spend an afternoon wiring up subvolumes, auto-snapshots, and multi-instance isolation, and you'll be bold enough to change config — because you know you can revert in five seconds.

Related: [Restic Automated Backup to S3](/en/post/vps-restic-automated-backup-s3/) · [VPS Disk Cleanup & Auto-Scaling](/en/post/vps-disk-cleanup-auto-scaling/)
