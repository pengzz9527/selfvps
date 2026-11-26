---
title: "Self-Host SFTPGo: One 1C1G VPS Replaces $25-50/mo Managed File-Transfer SaaS"
date: 2026-11-24
tags: ["VPS", "SFTPGo", "SFTP", "File Transfer", "Self-hosting", "Cost Savings", "DevOps"]
draft: false
image: /images/posts/vps-sftp-server-file-server/featured.png
description: "SFTPGo (Apache-2.0, written in Rust) runs SFTP/FTPS/WebDAV in one process on a 1C1G VPS (~30-60MB idle): per-user storage/concurrency/bandwidth quotas + fully REST-API-driven user lifecycle. $4-5/mo replaces managed file-transfer SaaS ($25-50/mo), saving $300-600/yr. systemd hardening, FTPS TLS, restic->R2 backup, and 5 hard-won pitfalls."
---

# Self-Host SFTPGo: One 1C1G VPS Replaces $25-50/mo Managed File-Transfer SaaS

Team file exchange, partner material hand-off, sending deliverables to clients — none of this needs a full-featured cloud drive, yet commercial **managed file-transfer SaaS** (FileTransferJunkie, Tecton, ShareFile and the like) bills on three stacked meters: seats, storage, and transfer volume, with entry tiers starting around $25-50/mo and overage charges on top. Move that same SFTP/FTPS/WebDAV server onto a $4-5/mo 1C1G VPS and you keep the functionality with per-user controls that are often *finer* than the SaaS version, cutting annual cost by 80-90%.

**What is SFTPGo**: an Apache-2.0 open-source file server written in Rust. A single binary serves **SFTP (over SSH), FTPS (FTP over TLS), and WebDAV** at the same time, with a built-in admin UI, REST API, per-user quotas (storage / concurrent sessions / bandwidth), and an abstracted storage backend (local disk or S3-compatible). No plugin hell, no multi-component stack — one process and one JSON config file.

**SFTP and SFTPGo are two different things — get this straight first**: SFTP (SSH File Transfer Protocol) is file transfer over the SSH protocol (RFC 4271, default port 22). SFTPGo is the *server software* that speaks SFTP/FTPS/WebDAV. The one hard pre-check before buying a VPS: make sure the provider doesn't block port 22 — most clouds whitelist 22, a few lock down anything except 80/443. Check the docs or test a connection before you commit. Also note SFTPGo listens on 22 by default; you can move it to 2222/2022, but clients then have to connect with the new port flag.

## 1. The math: calculate before you build

| Option | Monthly cost | Notes |
|---|---|---|
| Managed file-transfer SaaS (FileTransferJunkie / Tecton / ShareFile) | $25-50/mo and up | Seats + storage + transfer, triple-metered, overage fees |
| Self-hosted SFTPGo on a 1C1G VPS (Hetzner CX22 class) | $4-5/mo + 20GB disk | SFTP/FTPS/WebDAV, all included |

**You save $300-600/yr.** On 1C1G, SFTPGo idles at ~30-60MB; a single core comfortably handles 5-10 concurrent transfers, so bandwidth is the only real bottleneck. Hetzner/V.PS-class boxes ship 200GB of monthly traffic; a personal or small-team file-exchange workload typically burns 30-50GB/mo — far inside the cap.

**Cost twist**: SFTPGo user storage can live on an S3-compatible backend (e.g. Cloudflare R2, $0 egress). Large files land on R2 while the VPS keeps only the index — once storage grows, that beats "buy more VPS disk" every time.

## 2. 30-minute deploy: systemd + JSON config

Debian/Ubuntu-based; works on Hetzner, Netcup, V.PS and similar.

```bash
# 1. Binary (x86_64; grab the latest version from GitHub releases)
sudo apt install -y curl
curl -sL -o /tmp/sftpgo.tar.gz \
  https://github.com/drone-emdr/sftpgo/releases/latest/download/sftpgo_1.5.0_amd64_linux.tar.gz
sudo mkdir -p /opt/sftpgo
sudo tar -xzf /tmp/sftpgo.tar.gz -C /opt/sftpgo
sudo /opt/sftpgo/sftpgo version

# 2. Config / state / data dirs, all owned by the sftpgo user
sudo groupadd sftpgo
sudo useradd -r -g sftpgo -d /opt/sftpgo -s /usr/sbin/nologin sftpgo
sudo mkdir -p /etc/sftpgo/{config,state} /srv/sftpgo
sudo chown -R sftpgo:sftpgo /etc/sftpgo /opt/sftpgo /srv/sftpgo
sudo chmod 700 /etc/sftpgo/state /etc/sftpgo/config
```

systemd unit `/etc/systemd/system/sftpgo.service` — the `MemoryMax` hard cap protects the 1C1G memory budget (same idea as the [systemd socket-activation memory budget](/en/post/vps-systemd-socket-activation-memory-budget/) article):

```ini
[Unit]
Description=SFTPGo file server (SFTP/FTPS/WebDAV)
After=network-online.target
Wants=network-online.target

[Service]
User=sftpgo
Group=sftpgo
WorkingDirectory=/opt/sftpgo
ExecStart=/opt/sftpgo/sftpgo server /etc/sftpgo/config.json
Restart=on-failure
RestartSec=5
MemoryMax=400M
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
```

Minimal working `/etc/sftpgo/config.json`:

```json
{
  "general": { "user_id_prefix": "sftpgo", "max_retries": 3 },
  "sftp": {
    "enabled": true,
    "endpoints": [{ "address": "0.0.0.0", "port": 22 }]
  },
  "ftps": { "enabled": false },
  "webdav": {
    "enabled": true,
    "endpoints": [{ "address": "0.0.0.0", "port": 50080 }]
  },
  "api": {
    "enabled": true,
    "endpoints": [{ "address": "127.0.0.1", "port": 8080 }]
  },
  "data": {
    "storage_backend": {
      "type": "local",
      "local": { "base_dir": "/srv/sftpgo" }
    },
    "users": [],
    "users_backends": [{ "name": "sftpgo", "type": "json" }]
  },
  "http_credentials": { "user": "admin", "pass_enc": "d033e22ae348aeb5660fc2140aec35850c4da997" }
}
```

`pass_enc` is the SHA1 hex of the password (the example above is the default admin/admin hash — change it on day one).

```bash
sudo systemctl enable --now sftpgo
sudo systemctl status sftpgo
# WebDAV liveness probe:
curl -I http://127.0.0.1:50080/
# API health check:
curl -s http://127.0.0.1:8080/api/v2/health -u admin:admin
```

The admin UI and API share port 8080 (`http://<VPS>:8080/`), with the **admin/admin** default credentials — the first thing after going live is rotating that password, one API call:

```bash
curl -s -X PATCH http://127.0.0.1:8080/api/v2/users \
  -u admin:admin -H 'Content-Type: application/json' \
  -d '{"username":"admin","pass_enc":"<SHA1 hex of the new password>"}'
```

The API listens on loopback only by default. To manage it remotely, go through Tailscale (see [Tailscale zero-config private access](/en/post/vps-tailscale-zero-config-remote-access/)) — never expose 8080 directly.

## 3. Users, public keys, and FTPS TLS

**User management via REST API** (no JSON editing, no restarts):

```bash
# Create user alice: home /srv/sftpgo/alice, 512MB quota, max 2 sessions
curl -s -X POST http://127.0.0.1:8080/api/v2/users -u admin:<new-password> \
  -H 'Content-Type: application/json' -d '{
    "username": "alice",
    "home_dir": "/srv/sftpgo/alice",
    "pass_enc": "d3bd0e88f8a8a9f5c4d7f9b1e0c2a4b6c8d9e0f1",
    "max_sessions": 2,
    "quota_size": 536870912,
    "permissions": {
      "/": ["read", "create", "delete", "mkdir", "rename"]
    }
  }'
```

`pass_enc` is the SHA1 hex of the password. **Recommended: disable password login entirely and use public keys only** — drop the client's `ssh-keygen -t ed25519` public key into the user's `public_keys` array and leave the password field empty.

**FTPS needs TLS to turn on**: attach a certificate to the instance via the admin UI (or API). A self-signed CA leaf is plenty for internal/team use:

```bash
# Quick self-signed cert (internal team scenario)
mkdir /etc/sftpgo/tls && cd /etc/sftpgo/tls
openssl req -x509 -newkey rsa:2048 -nodes -days 365 \
  -keyout ftps.key -out ftps.crt -subj "/CN=sftpgo.internal"
sudo chown sftpgo:sftpgo ftps.key ftps.crt
```

Enable FTPS in config.json:

```json
"ftps": {
  "enabled": true,
  "endpoints": [
    { "address": "0.0.0.0", "port": 21,  "tls_mode": "explicit" },
    { "address": "0.0.0.0", "port": 990, "tls_mode": "implicit" }
  ],
  "cert_file": "/etc/sftpgo/tls/ftps.crt",
  "key_file":  "/etc/sftpgo/tls/ftps.key"
}
```

**Implicit vs explicit — pick the wrong one and the connection dies**: implicit (SSL) encrypts from the first byte on port 990; explicit (TLS) starts clear on port 21 and upgrades via `AUTH TLS`. Clients (FileZilla, lftp, curl) must select the matching mode, and a mismatch fails every time. Most clients default to explicit; the 990 implicit port exists for legacy FTP clients — run only one, not both.

## 4. Quotas and traffic control: three dials

SFTPGo's per-user control set, all edited via `PATCH /api/v2/users`:

| Control | Field | Suggested value on 1C1G |
|---|---|---|
| Storage quota | `quota_size` (bytes) | 512MB-2GB per user |
| Concurrent sessions | `max_sessions` | 2-5 |
| Bandwidth limit | `bwlimit` (with start/stop time windows) | 5-10MB/s in peak hours |

**Quota ≠ total cap**: ten users × 1GB quota = 10GB demand, but a 20GB disk also has to hold the OS, logs, and swap. Cap total quotas at 80% of disk and keep the L2 disk-usage alert as backstop, or over-quota writes will fill the disk and take the box down with them.

## 5. API automation: the whole user lifecycle in one command

Beyond the UI (which shares port 8080 — UI at `/`, API at `/api/v2`), every lifecycle step is an API call:

```bash
API=http://127.0.0.1:8080/api/v2
AUTH='admin:<new-password>'

# List all users (storage used + status included)
curl -s $API/users -u $AUTH

# Suspend bob (data kept, new sessions rejected immediately)
curl -s -X PATCH $API/users/bob -u $AUTH \
  -H 'Content-Type: application/json' -d '{"suspended": true}'

# Check bob's actual usage
curl -s $API/users/bob -u $AUTH | grep -o '"quota_size":[^,}]*\|"quota_size_used":[^,}]*'

# Delete user (with data)
curl -s -X DELETE $API/users/bob -u $AUTH
```

Put this in a 5-minute crontab and "provision an external collaborator account" becomes a three-liner: generate the key → POST the user → hand the counterpart the key + port. When the engagement ends (deliverables transferred), one DELETE, keep or wipe the data.

## 6. Monitoring and alerting: three layers

**L1 liveness**: `GET /api/v2/health` returns `{"Status":"ok"}`; HTTP 200 = alive.

**L2 capacity**: `df` percentage on the data disk.

**L3 abuse**: count `auth failed` lines in the logs — the fingerprint of brute force / credential stuffing. SFTPGo logs JSON lines by default (`/var/log/sftpgo/sftpgo.log`; the actual path is `log_file` in your config), and combined with [CrowdSec + nftables IP-reputation blocking](/en/post/vps-ipset-l7-filter-crowdsec/) bad IPs get banned automatically.

Prometheus textfile collector (`/usr/local/bin/sftpgo-prom-collector.sh`, pointed to by the node-exporter textfile collector):

```bash
#!/bin/bash
OUT=/var/lib/prometheus-node-exporter/sftpgo.prom
{
  code=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8080/api/v2/health -u admin:$SFTPGO_ADMIN_PASS)
  echo "sftpgo_up 0"
  [ "$code" = "200" ] && echo "sftpgo_up 1"
  pct=$(df -P /srv/sftpgo | awk 'NR==2{print $5}' | tr -d '%')
  echo "sftpgo_data_disk_used_percent $pct"
  fails=$(tail -n 5000 /var/log/sftpgo/sftpgo.log 2>/dev/null | grep -c 'auth failed' || true)
  echo "sftpgo_recent_auth_failures $fails"
} > "$OUT"
```

```bash
sudo crontab -e
*/5 * * * * /usr/local/bin/sftpgo-prom-collector.sh
```

Three alert rules in Grafana/Prometheus:

| Metric | Threshold | Severity |
|---|---|---|
| `sftpgo_up == 0` | for 5m | critical |
| `sftpgo_data_disk_used_percent > 85` | for 10m | critical (>75 = warning) |
| `sftpgo_recent_auth_failures > 50` | for 15m | warning (feed to CrowdSec) |

## 7. Backup and restore: restic → R2

SFTPGo keeps **users, permissions, and quotas all in the `state/` directory**; `config.json` holds protocol/port/TLS settings; `/srv/sftpgo` holds user data — all three go into the restic backup set (see the [restic → S3/R2 backup system](/en/post/vps-restic-automated-backup-s3/)):

```bash
restic -r rest:backup-sftpgo \
  --exclude-file /etc/restic/sftpgo-excludes \
  backup /etc/sftpgo /srv/sftpgo
```

`/etc/restic/sftpgo-excludes`:

```
/srv/sftpgo/**/*.tmp
/srv/sftpgo/**/.partial
```

```bash
sudo crontab -e
# Daily 03:00, keep 7 snapshots
0 3 * * * restic -r rest:backup-sftpgo --last-backup 23H backup /etc/sftpgo /srv/sftpgo && restic forget --keep-daily 7 --prune
```

**Quarterly restore drill** (10 minutes):

```bash
restic -r rest:backup-sftpgo restore last \
  --target /tmp/sftpgo-restore
diff -r /tmp/sftpgo-restore/etc/sftpgo/state /etc/sftpgo/state   # user list matches
ls /tmp/sftpgo-restore/srv/sftpgo                                 # tree intact
```

**The second 1 in 2-1-1**: for big-file workloads, add a nightly `rsync -a --delete /srv/sftpgo/ backup@2nd-vps:sftp-mirror/` push to a second VPS. When the whole box dies, restore from the off-site copy.

## 8. 5 pitfalls (the kind you only learn by hitting them)

1. **Default admin/admin on a public 8080**: the API listening on loopback-only is safe by default, but the moment you expose 8080 for remote management without rotating the password, credential-stuffing bots are in within 10 minutes. Rotate the password *and* keep access on Tailscale/SSH-tunnel only — neither alone is enough.
2. **Backed up the data dir but missed `state/`**: users, permissions, and quotas all live in `state/`. Restoring only `/srv/sftpgo` gives you a file tree with no server — the restic set must include *both* `/etc/sftpgo` and `/srv/sftpgo`.
3. **FTPS implicit/explicit mixed up**: configuring both the 990 implicit and 21 explicit endpoints, with clients picking the wrong mode, produces "connects then immediately drops" failures that eat hours. For internal teams, run a single port.
4. **Per-user quota ≠ total cap**: each user's `quota_size` counts independently, and their sum can exceed the physical disk. Cap the total at 80% of disk and let the L2 disk-usage alert backstop it.
5. **Using SFTPGo as an S3 client**: it is not an S3 API server. "S3-compatible" means user storage can be *placed on* an S3 backend (R2) — data on R2, index on the VPS. If you need to *serve* S3 API, that's MinIO's job (see [MinIO object storage cost savings](/en/post/vps-minio-object-storage-cost-saving/)).

## 9. Hybrid mode: when SaaS is still the right call

Compliance requirements (SOC 2 reporting, audit trails) or 50+ users who need an SLA — the SaaS compliance overhead beats self-maintenance. For personal or small teams (<20 users, internal + a few external collaborators): self-hosted SFTPGo at $4-5/mo, saving $300-600/yr, with per-user quotas and API control that are actually finer-grained than most SaaS tiers.

---

*Once SFTPGo is running and you want to manage the credentials it protects, see [Self-hosted Vault on a VPS](/en/post/vps-vault-selfhosted-secrets-management/); for the cache tier, see [Self-host Valkey](/en/post/vps-valkey-selfhosted-redis-replacement/).*
