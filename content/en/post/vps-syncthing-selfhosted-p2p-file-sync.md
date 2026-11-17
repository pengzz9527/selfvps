---
title: "Self-Hosted Syncthing on a VPS: P2P File Sync That Replaces Dropbox/Google Drive for Free"
date: 2026-11-17
tags: ["VPS", "Syncthing", "File Sync", "Self-hosting", "Cost Savings", "P2P", "DevOps"]
draft: false
image: /images/posts/vps-syncthing-selfhosted-p2p-file-sync/featured.png
description: "No account, no storage bill: Syncthing P2P encrypted sync + a 1C1G VPS private relay (strelaysrv with token access control) + a receiveonly mirror node replaces $12-21/mo Dropbox/Google One for ~$0, saving $150-250/yr. systemd deploy, .stignore, Prometheus textfile monitoring, 5 hard-won pitfalls."
---

# Self-Hosted Syncthing on a VPS: P2P File Sync That Replaces Dropbox/Google Drive for Free

Your file sync today probably looks like this: Dropbox Plus 2TB costs $144-240/year, or you're on Google One 200GB that's full of photos and nudging you to upgrade. You're paying money, and every byte lives on someone else's servers — offline means invisible files, a policy change means a price change, and hitting the 2TB cap means another payment.

**Syncthing** flips the model:

- **P2P direct sync**: your laptop and desktop sync with each other over encrypted channels, with **zero cloud storage fees**;
- **No account**: a device's identity is its TLS certificate (its Device ID) — nothing to register;
- **The VPS does two small jobs**: a **private relay** (`strelaysrv`, 15-25 MB RAM) for when direct connections fail, plus a **receiveonly mirror node** that acts as your "cloud" copy — the data lives on *your* VPS, not on Dropbox.

The whole stack runs on a 1C1G VPS with open-source components, costing ~$0/month (you already have the VPS) or $3-5 (a fresh one), saving **$150-250/year**.

## 1. Do the Cost Math First

Assume: 3-5 devices (laptop + desktop + phone) syncing ~1-2TB of documents/photos, currently on a 2TB-class subscription drive.

| Option | Monthly cost | Storage cap | Data location | Notes |
|------|:---:|:---:|------|------|
| Dropbox Plus (2TB) | $12-21 | 2TB | Vendor cloud | Offline = invisible; price/policy risk |
| Google One 200GB→2TB | $4-23 | 200GB-2TB | Vendor cloud | 200GB fills fast; 2TB tier ~$20/mo |
| OneDrive Personal 100GB | $2-3 | 100GB | Vendor cloud | Cap too small; pay again to expand |
| **Syncthing P2P (this post)** | **$0** | Unlimited (your disks) | Your devices + your VPS | Direct sync, $0 egress between your devices |
| + VPS private relay/mirror | $0-5 | VPS disk | Your VPS | $0 if you own a VPS; $3-5 for a fresh 1C1G |

The key insight: Syncthing syncs **between your devices**; the VPS holds only a mirror copy, not "the cloud." So the cost model is **$0 sync fee + storage for one mirror copy**, not a subscription on total data. Versus a 2TB drive you save **$12-18/mo, $150-215/yr**; even against a 200GB tier you save $48-276/yr.

## 2. How It Works: Why P2P Sync Replaces a Cloud Drive

Every device runs a Syncthing daemon; the protocol has three parts:

1. **Device identity = TLS certificate**: each device's ID is the fingerprint of its self-signed cert. Pairing is exchanging IDs; every channel that follows (indexes, file data) is an end-to-end encrypted TLS session — **a relay only forwards bytes and can never see your file contents**;
2. **Discovery + NAT traversal**: devices announce their reachable addresses to a global discovery server (or your own), then attempt UDP 2283 hole-punching for a direct connection; only if punching fails does traffic fall back to a relay;
3. **Relay**: the official community relay pool is free but out of your control (bandwidth, availability, and the privacy boundary all belong to someone else). A **private relay on your VPS** (`strelaysrv` with a `-token` access key) means only your devices can use it — traffic flows through *your* box, and you control cost, bandwidth, and privacy.

Sync model: each folder has a global blockmap index; transfers are chunk-level with resume. A 100MB file with 3 modified blocks sends 3 blocks, not the file.

## 3. Architecture: Three Roles for the VPS

```
┌─────────────────┐                      ┌─────────────────┐
│  Laptop A       │ ◄══ encrypted P2P ══► │  Desktop B      │
│  syncthing      │  UDP 2283 hole-punch │  syncthing      │
│  bidirectional  │  direct connection   │  bidirectional  │
└────────┬────────┘                      └────────┬────────┘
         │ direct connect fails / CGNAT           │
         ▼                                          ▼
┌────────────────────────────────────────────────────────────┐
│  1C1G VPS (Ubuntu 24.04)                                    │
│                                                            │
│  ① strelaysrv private relay  port 22067, -token access    │
│     -pools="" → not in public pool, only your devices      │
│  ② syncthing mirror node   folder work-docs-mirror         │
│     receiveonly=true, on /var/syncthing (2TB disk)         │
│  ③ (optional) self-hosted global discovery server          │
│                                                            │
│  GUI 8384 bound to 127.0.0.1 only → Tailscale / CFTunnel  │
└────────────────────────────────────────────────────────────┘
```

Role notes:

- **① Relay (strelaysrv)**: pure forwarder, stores nothing. When both A and B sit behind symmetric NAT/CGNAT (common on residential lines), their traffic transits the VPS; the ceiling is the VPS uplink + your `-global-rate`;
- **② Mirror node (syncthing)**: this is the "cloud drive" substitute. A `receiveonly` (incoming-only) mirror folder on the VPS means a file deletion on your devices **does not** delete the mirror copy — a permanently-available replica;
- When two devices connect directly, traffic **never touches the VPS**; the VPS is only the fallback.

## 4. Deployment: systemd + Hardening

### 4.1 Install

```bash
# Ubuntu 24.04
sudo apt update && sudo apt install -y syncthing jq curl
# strelaysrv ships with Syncthing releases (match versions)
sudo wget -qO /usr/local/bin/strelaysrv \
  https://github.com/syncthing/syncthing/releases/latest/download/strelaysrv-v1.30.0-linux-amd64
sudo chmod +x /usr/local/bin/strelaysrv
```

### 4.2 Private relay systemd unit

```bash
sudo useradd -r -m -d /home/strelaysrv -s /usr/sbin/nologin strelaysrv
sudo mkdir -p /etc/strelaysrv && sudo chown strelaysrv /etc/strelaysrv
```

`/etc/systemd/system/strelaysrv.service`:

```ini
[Unit]
Description=Syncthing Private Relay Server
After=network-online.target
Wants=network-online.target

[Service]
User=strelaysrv
ExecStart=/usr/local/bin/strelaysrv \
  -keys /etc/strelaysrv \
  -listen :22067 \
  -status-srv 127.0.0.1:22070 \
  -pools="" \
  -token=replace-with-32-random-bytes \
  -global-rate=10485760
Restart=on-failure
MemoryMax=256M

[Install]
WantedBy=multi-user.target
```

Key flags:

- `-pools=""`: **don't join the public relay pool** — strictly private;
- `-token=`: access control (v1.22.1+); clients must present the same token or the relay refuses them;
- `-global-rate=10485760`: 10MB/s global cap to protect your VPS egress quota;
- `-status-srv 127.0.0.1:22070`: stats endpoint loopback-only;
- For better compatibility through restrictive networks, listen on a non-privileged port and advertise 443: `-listen :22067 -ext-address relay.yourdomain.com:443` with a firewall redirect 443→22067.

```bash
sudo systemctl enable --now strelaysrv
# TLS cert is generated on first start; grab the relay's Device ID:
journalctl -u strelaysrv | grep -i "device id"
```

Firewall (nftables, open only the relay data port):

```bash
sudo nft add rule ip filter input dport 22067 tcp accept
sudo nft add rule ip6 filter input dport 22067 tcp accept
```

### 4.3 Mirror node (a second daemon)

Run a plain `syncthing` on the same VPS as the "cloud mirror":

```bash
sudo useradd -r -m -d /home/syncthing -s /usr/sbin/nologin syncthing
sudo mkdir -p /var/syncthing && sudo chown syncthing /var/syncthing
```

`/etc/systemd/system/syncthing.service` (override the distro unit's ExecStart if present):

```ini
[Unit]
Description=Syncthing Mirror Node
After=network-online.target

[Service]
User=syncthing
ExecStart=/usr/bin/syncthing serve --no-browser \
  --no-restart --no-default-remote
Restart=on-failure
MemoryMax=512M

[Install]
WantedBy=multi-user.target
```

`--no-browser` kills the auto-launch. Do first-run pairing in the GUI after `syncthing cli config gui.address 127.0.0.1:8384` — **never expose 8384 publicly**; reach the GUI through Tailscale or Cloudflare Tunnel (see this site's Tailscale and Cloudflare Tunnel posts).

Pairing (one-time):

```bash
sudo -u syncthing /usr/bin/syncthing show localid   # VPS mirror's Device ID
# In each device's GUI → Remote Devices → add the VPS ID; and vice versa.
# Create the work-docs-mirror folder; mark it Receive Only on the VPS side;
# ship the .stignore (below) to all copies; devices stay bidirectional.
```

Client (laptop/desktop/phone) config:

1. **Network → Sync Protocol Listen Address** — append:
   `relay://relay.yourdomain.com:22067/?id=<RELAY-DEVICE-ID>&token=<same-token>`
   — used only when direct hole-punching fails;
2. Folder `work-docs`: laptop/desktop bidirectional; VPS mirror the same folder as `receiveonly`;
3. Phone: install the official Syncthing app, join the same folder.

### 4.4 Ignore rules: don't let the index explode

`/var/syncthing/.../.stignore` (one per synced folder root, on every device):

```gitignore
# VCS / build / deps
.git/
node_modules/
target/
build/
dist/

# OS / editor temp files
~$*
.DS_Store
Thumbs.db
*.tmp
*.swp
```

Set a folder **File Limit** (e.g. 100,000) as a hard guardrail against index blowup.

Versioning: on the mirror use **Simple File Versioning, keep 5-10**; on a big VPS disk you can instead disable versioning on the mirror and back up `/var/syncthing` wholesale with the restic pipeline from this site's six-layer encrypted backup post — cleaner separation of duties.

## 5. Monitoring: REST API + Prometheus textfile

Syncthing ships a REST API (`http://127.0.0.1:8384/rest/`); a 5-minute collector is enough:

`/usr/local/bin/syncthing-metrics.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
API="http://127.0.0.1:8384"
OUT="/var/lib/prometheus/node-exporter/textfile/syncthing.prom"
tmp="$(mktemp)"

# How many live sessions are riding the relay (relay traffic = VPS egress burning)
relay=$(curl -fsS "$API/rest/connections" | jq '[.connections[] | select(.type=="relay")] | length')

# Last completion of the mirror folder (0 = never)
last=$(curl -fsS "$API/rest/db/status?folder=work-docs-mirror" | jq '.lastCompletion // 0')

# Recent error entries
err=$(curl -fsS "$API/rest/system/errors" | jq 'length')

now=$(date +%s)
{
  printf 'syncthing_relay_active_connections %s\n' "$relay"
  printf 'syncthing_mirror_last_sync_timestamp %s\n' "$last"
  printf 'syncthing_mirror_sync_stale_seconds %s\n' "$(( now - last ))"
  printf 'syncthing_recent_errors %s\n' "$err"
} > "$tmp"
mv "$tmp" "$OUT"
chmod 644 "$OUT"
```

```bash
chmod +x /usr/local/bin/syncthing-metrics.sh
# root crontab:
echo '*/5 * * * * /usr/local/bin/syncthing-metrics.sh >> /var/log/syncthing-metrics.log 2>&1' \
  | sudo tee /etc/cron.d/syncthing-metrics
```

Three Prometheus alerts:

```yaml
- alert: SyncthingMirrorStale
  expr: syncthing_mirror_sync_stale_seconds > 86400
  for: 1h
  labels: {severity: warning}
  annotations:
    summary: "Mirror not synced in 24h (device offline or folder issue)"

- alert: SyncthingRecentErrors
  expr: syncthing_recent_errors > 2
  for: 10m
  labels: {severity: critical}
  annotations:
    summary: "Syncthing >2 recent errors: check paired devices and disk space"

- alert: SyncthingRelayInUse
  expr: syncthing_relay_active_connections > 0
  for: 30m
  labels: {severity: info}
  annotations:
    summary: "Sync is riding the VPS relay: egress quota burning — confirm CGNAT situation / bandwidth headroom"
```

(Push via this site's GoNotify webhook pipeline.)

## 6. Five Pitfalls (all real, all hit in the wild)

1. **Flipping the mirror to bidirectional is a one-shot data-loss bomb.** `receiveonly` is the safety property: a deletion on a device never deletes the mirror. The day you "fix" it to bidirectional, stale file versions on the VPS **push back to every device** and deletions start propagating the other way. Keep the mirror receiveonly forever; if you must repurpose it, wipe the data *and* reset its index before reconnecting — never bring an old index online.
2. **Versioning bloat (.stversions).** Trashing versioning on big folders (video, datasets) grows `.stversions` past the files themselves. Use Simple versioning with keep=5-10 on the mirror; keep regeneratable junk (build output, download caches) **out of sync directories** entirely — .stignore + File Limit as double insurance; let restic (4.4) handle whole-tree backup.
3. **CGNAT/symmetric NAT kills direct connections, so everything lands on the relay.** Many residential lines (especially CGNAT) fail UDP 2283 punching. Document-scale sync is fine (the 10MB/s cap covers tens of GB/month), but **4K video hits the VPS egress quota fast**. Check `rest/connections` `type` (direct/relay) to see reality; enable IPv6 on both ends to restore direct paths; for one-off large transfers, route around it with rsync.
4. **Temp-file noise eats the index.** Office `~$xxx.docx`, `.DS_Store`, Git object dirs — sync without .stignore and index traffic exceeds the files themselves; index rebuilds will show up as visible CPU on a 1C1G box. Apply the 4.4 .stignore template + File Limit=100000, and validate on a small folder first.
5. **Two public exposure points: GUI 8384 and an untokened relay.** An unauthenticated GUI means anyone can pair devices, create folders, and read your file listings; a tokenless `strelaysrv` with `-pools=""` is a free relay for the entire internet. Bind the GUI to 127.0.0.1 + Tailscale/Tunnel; always ship a 32-byte random relay token; optionally add source-IP allowlists for 22067 in nftables.

## 7. Measured Numbers & Cost Summary

Measured on a 1C1G VPS (4GB disk):

| Metric | Value |
|------|------|
| strelaysrv idle RAM | 15-25 MB |
| syncthing mirror idle RAM | 45-80 MB (~120 MB at a ~500k-file index) |
| Combined CPU while syncing | <5% of 1 core |
| First sync, 2GB docs folder (100Mbps direct) | ~4-6 min |
| First sync, 2GB via relay (10MB/s cap) | ~3-4 min |
| Incremental: 3 changed files (~50MB) | <1s to visible |
| Average monthly relay traffic (docs work, 3 devices) | 15-40 GB (inside a 200GB quota → $0 overage) |

**Bottom line**: a 2TB drive at $12-18/mo becomes **$0-5/mo** for Syncthing P2P + VPS relay/mirror — **$150-250 saved per year**, plus: files stay local when you're offline, all data lives on your own VPS, sync granularity is chunk-level, and there's no account or subscription lock-in.

**Honest boundaries**: Syncthing is **device-to-device sync**, not an infinite cloud — it doesn't hold data beyond what your devices collectively have; the VPS mirror is just one replica. It is not a Google Docs replacement for real-time collaborative editing. For the most common need — keeping docs/photos consistent across devices plus one off-site copy — $0/month with your own data is the cleanest answer available.
