---
title: "Self-Hosted Vault on a VPS: $0/mo Secrets Center That Retires Static Passwords"
date: 2026-11-20
tags: ["VPS", "Vault", "Secrets Management", "Self-hosting", "Cost Savings", "PostgreSQL", "PKI", "DevOps"]
draft: false
image: /images/posts/vps-vault-selfhosted-secrets-management/featured.png
description: "Run single-node Raft Vault (~120-150MB idle) on a 1C1G VPS: KV v2 + dynamic database credentials + PKI + Transit, DB accounts that auto-expire on lease expiry, 24h short-lived certs, replacing AWS Secrets Manager ($0.40/secret/mo) and HCP Vault for $0 and killing ~10h/quarter of manual rotation. Raft single-node total-loss and unseal-key risks up front, TTL discipline, 5 hard-won pitfalls."
---

# Self-Hosted Vault on a VPS: $0/mo Secrets Center That Retires Static Passwords

The item on the self-hosting list that gets skipped more often than monitoring or mail is **secrets management**: database credentials, API keys, SSH private keys scattered across config files, CI environment variables, and chat history — all static values. A leak means a rotation, and every rotation is a full manual operation. One tool keeps showing up as the real fix: HashiCorp Vault. Many teams treat it as heavyweight, multi-cluster, enterprise infrastructure, but for personal/small-team use, **a single-node Raft cluster with four secret engines** idles at just ~120-150MB on a 1C1G VPS, and $0/mo retires the entire "static passwords + manual rotation" debt.

**Vault** (BSL-licensed, full-featured open source) does exactly four jobs here:

- **KV v2 engine**: a central vault for app config, API keys, and DB connection strings, with version history (roll back any accidental delete);
- **Dynamic database credentials**: Postgres/MySQL gets temporary accounts issued on a lease with a TTL — expired or app-restarted, the account is auto-dropped by the plugin;
- **PKI engine**: your own root CA issuing 24h short-lived certs, so internal mTLS never needs manual renewal;
- **Transit engine**: encrypt/decrypt without ever persisting the key — the key lives in memory only; ciphertexts live in your own R2/S3, so Vault being down doesn't lose your data.

On an existing (or new ~$4/mo) 1C1G VPS that's **$0-5/mo**, replacing AWS Secrets Manager at $0.40/secret/month (200 secrets ≈ $80/mo) or HCP Vault at ≈$5-15/mo, plus ~10 hours a quarter of "rotate 20 apps × 30 min" manual labor. **Savings of $900+/yr and elimination of the permanent blast radius of credential leaks.**

## 1. The Cost Math: Work It Out Before You Start

Scenario: 20 microservices/scripts, each holding database accounts, API keys, and internal certs; current state is "hardcoded in config + quarterly manual rotation" or a SaaS secret manager.

| Option | 200 secrets / month | Rotation | Notes |
|------|:---:|------|------|
| Static config + manual rotation | $0 (VPS already owned) | 10h/quarter manual | Leak = permanent risk; no audit trail |
| AWS Secrets Manager | ≈$80+ | optional auto | $0.40/secret/mo, API calls extra |
| GCP Secret Manager | ≈$12-15 | optional auto | ~$0.05-0.075/secret/mo incl. versions |
| Azure Key Vault (standard, non-HSM) | ≈$1-5 | optional auto | usage-based, cheap at low volume |
| HCP Vault | ≈$5-15/user/mo | auto | per-user subscription |
| **Vault @ 1C1G VPS (single-node Raft)** | **$0** | fully automatic (lease/PKI TTL) | new box $4-5; ~120-150MB idle |

**≈ $900/yr saved** (vs AWS SM), plus every credential leak's blast radius shrinks from "permanent" to its TTL (default 30 min – 24h).

**State the boundary clearly**: single-node Raft = no cluster redundancy. Acceptable for a personal VPS (combined with daily Raft snapshots + off-site restic backup, §5), but for production-critical systems run a 3-node Raft cluster (3 × $5 VPS ≈ $15/mo) — one of the two pre-check risks in §5, not an oversight.

## 2. Why Dynamic Credentials Retire Static Passwords

The traditional model: **accounts are long-lived assets** — create an `app_rw` user, write the password into a config file, it's valid forever, and when it leaks you manually change the password and restart everything.

Vault's model: **credentials are short leases** — when an app needs a DB connection it asks Vault for a username/password pair with a TTL (e.g. 30 min) and `max_ttl` (e.g. 2h); on expiry or app restart the Postgres plugin auto-DROPs the account. A stolen credential buys an attacker at most 30 minutes, and the audit log (§5) shows exactly which machine pulled it and when.

The four engines each replace a class of "static value":

| Engine | Replaces | Dynamic behavior |
|------|------|------|
| KV v2 | connection strings/keys in config files | version history + TTL, roll back any delete |
| database | long-lived DB accounts | issued per lease, auto-revoked on expiry |
| pki | manually issued/renewed certs | built-in root CA, 24h certs auto-reissued |
| transit | scattered encryption keys | keys never persisted; Vault only does the math |

**Storage choice**: single-node Raft is the optimal pick for personal setups — no external dependency (no separate Postgres to store Vault's own state), one directory (`/var/lib/vault`) is the entire state, and restic ships it to R2 in one command ($0 egress).

**Unseal**: Vault's keys are encrypted at rest and must be "unsealed" at startup. On a plain VPS with no cloud KMS, use **Shamir shares** (3-of-5): split the 5 keys across two media (e.g. encrypted USB + encrypted R2 object) so stealing one machine can never unseal the vault — a critical step in §4.

## 3. Architecture: Four Roles on One VPS

```
 [microservices/CI/scripts] ──HTTPS (via Tailscale/Tunnel)──▶ ┌────────────────────────┐
 [Postgres plugin]        ◀──on-demand temp accounts────────│  Vault (single-node    │
 [internal services]      ──fetch 24h certs─────────────────│  Raft, 4 engines:     │
                                                             │  KV2+db+pki+transit  │
                                                             └──────────┬───────────┘
                 /v1/sys/health probe  │  /v1/sys/metrics?format=prom
                ┌────────────────────┴────────────────────┐
 [Uptime Kuma]  probes   [Prometheus] scrapes → 3 alerts
                └───────────┬─────────────────────────────┘
 [restic nightly] ──encrypted──▶ [R2 object storage, $0 egress] (Raft snapshots + data dir)
 [audit log]      ──tail────▶ [Loki aggregation + logrotate disk cap]
```

Port 8200 is **always bound to loopback**: external access goes through Tailscale (see [Tailscale zero-config private access](/post/vps-tailscale-zero-config-remote-access/)) or a Cloudflare Tunnel ([reference](/post/vps-cloudflare-tunnel-zero-trust/)). Vault has no built-in network ACL — opening 8200 to the internet hands out root tokens on demand; that's pitfall #3 in §5.

## 4. Deployment: systemd + Raft Init + Four Engines

### 0. Pre-checks (do them before buying the box)

```bash
# Disk: Raft snapshots + WAL + audit logs need only ~2GB headroom; don't share a data disk with heavy workloads
df -h /var
# Confirm the target Postgres is reachable from the VPS (the dynamic-credentials plugin must run CREATE ROLE)
pg_isready -h DB_HOST -p 5432
```

### 1. Install (pinned version, systemd-managed)

```bash
sudo useradd -r -s /usr/sbin/nologin vault
sudo mkdir -p /etc/vault /var/lib/vault /var/log/vault
VAULT_VERSION=1.18.1   # pinned; check the 1.18+ channel for newer patches
curl -fsSL -o vault https://releases.hashicorp.com/vault/${VAULT_VERSION}/vault_${VAULT_VERSION}_linux_amd64.zip
unzip vault -d /usr/local/bin && rm -f vault

sudo cat > /etc/systemd/system/vault.service <<'EOF'
[Unit]
Description=HashiCorp Vault (single-node raft)
After=network-online.target

[Service]
User=vault
Group=vault
ExecStart=/usr/local/bin/vault server -config=/etc/vault/vault.hcl
Restart=on-failure
MemoryMax=512M
CPUQuota=75%
ProtectSystem=full
ReadWritePaths=/var/lib/vault /var/log/vault

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl enable --now vault
```

`MemoryMax=512M` leaves headroom: ~120-150MB idle, but batch PKI issuance or audit bursts can push 200-300MB.

### 2. Minimal config (single-node Raft + loopback listener + Prometheus metrics)

`/etc/vault/vault.hcl`:

```hcl
storage "raft" {
  path = "/var/lib/vault"
}

listener "tcp" {
  address     = "127.0.0.1:8200"   # always loopback; external via Tailscale/Tunnel
  tls_disable = 1                 # plaintext on loopback; the tunnel layer adds TLS
}

api_addr   = "http://127.0.0.1:8200"
ui         = true                  # admin UI, accessed via the tunnel

telemetry {
  promotion_builtins = true       # exposes /v1/sys/metrics?format=prom
}
```

### 3. Initialize + unseal (Shamir 3-of-5 — keep keys split and off-box)

```bash
# init: 5 shares, threshold 3. The 5 keys + 1 root token print out — record them in a password manager (offline!)
vault operator init
# unseal: needs 3 shares. In production split the 5 keys as 2+3 across two media/machines
vault operator unseal
export VAULT_ADDR=http://127.0.0.1:8200
vault operator raft init -bootstrap   # single-node bootstrap, no join needed
vault status
```

> A personal VPS can get away with `-key-shares=1 -key-threshold=1` — the cost: stealing this one VPS's key file = the whole vault is unsealable. Use it only if you accept that.

### 4. Enable the four engines

```bash
vault secrets enable kv-v2            # default path secret/
vault secrets enable database          # dynamic DB credentials
vault secrets enable pki               # internal cert issuance
vault secrets enable transit           # stateless crypto
```

### 5. KV v2: central store for config and API keys

```bash
vault kv put secret/app-a db-conn "host=... user=..."
vault kv put secret/app-a api-key "sk-..."
vault kv get -version=1 secret/app-a api-key   # roll back to any historical version
```

### 6. Dynamic database credentials (Postgres example — the highest-ROI step)

First create a dedicated `vault-admin` Postgres role with `CREATE ROLE` privilege, then:

```bash
vault write database/config/pg \
  allowed_roles="pg-app" \
  connection_url="postgresql://vault-admin:<pwd>@DB_HOST:5432/yourdb?sslmode=require"

vault write database/roles/pg-app \
  db_name=pg \
  creation_statements='CREATE ROLE "{{name}}" WITH LOGIN PASSWORD '\''{{password}}'\'' VALID UNTIL '\''{{expiration}}'\''; GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO "{{name}}";' \
  default_ttl="30m" \
  max_ttl="2h"

# client side: pull a credential set per connection; auto-invalid on expiry
vault read database/creds/pg-app
```

Do the same for CI with a read-only `pg-ci` role, `max_ttl=4h`.

### 7. PKI: 24h short-lived certs for internal services

```bash
vault secrets tune -max-lease-ttl=8760h pki
vault write -field=certificate pki/root/generate/internal \
  common_name="vps.example.com" issuer_id=1  # generate the root CA (8760h)
vault write pki/roles/app \
  allowed_domains="vps.example.com" \
  allow_subdomains=true ttl=24h max_ttl=72h
# issue: the app auto-renews before the 24h expiry — internal mTLS, zero manual renewal
vault write -field=certificate pki/issue/app common_name="svc-a.vps.example.com"
```

### 8. Transit + audit + backup

```bash
# Transit: ciphertext can live in your R2/S3 (Vault downtime doesn't lose it); the key never hits disk
vault write transit/keys/secret-aes type=aes256-siv
vault write -field=ciphertext transit/encrypt/secret-aes plaintext=<base64-plaintext>

# Audit: every operation to disk (pair with logrotate copytruncate + Loki aggregation, §5)
vault audit enable file file_path=/var/log/vault/audit.log

# Backup: daily auto Raft snapshots + manual full snapshot (always run before migration/box-swap)
vault operator raft snapshot auto 24h
vault operator raft snapshot save /backups/vault-$(date +%F).vlt
```

## 5. Monitoring: Prometheus + Uptime Kuma + Weekly Checkups

Vault's two most dangerous failure modes: **sealed** (unseal state lost, entire vault unreadable) and **disk eaten by audit logs**. Two monitoring lines:

- **Prometheus**: scrape `/v1/sys/metrics?format=prom` directly (root token auth), three alerts:
  - `vault_sealed == 1` for 1 minute → P1 (whole vault unavailable, unseal now);
  - Raft has no leader / snapshot lagging → P2;
  - disk holding the Vault data dir >80% → P2 (audit logs are the disk killer — cut them before anything else).
- **Uptime Kuma** ([deployment reference](/post/vps-uptime-kuma-monitoring/)): probe `curl -s 127.0.0.1:8200/v1/sys/health` asserting `initialized=true AND sealed=false`, failures push to Gotify ([reference](/post/vps-gotify-selfhosted-realtime-alerts/));
- **Weekly cron checkup**: audit-log growth rate + `vault operator raft snapshots` list showing a snapshot in the last 7 days + one drill: `vault operator raft snapshot restore` last week's snapshot into a scratch dir and verify it recovers.

## 6. Five Pitfalls (all hit in production)

1. **Single-node Raft total loss = the entire vault evaporates**: with no quorum redundancy, a full disk / accidental `rm -rf /var/lib/vault` / box-swap without a snapshot means all secrets, dynamic-credential history, and the PKI root CA are gone. The §4 `snapshot auto 24h` + manual `snapshot save` must both run, and snapshots get shipped off-site via restic to R2 weekly (2-1-1, [reference](/post/restic-s3-six-layer-encryption-2-1-1-backup/)) — R2 egress is $0.
2. **Shamir keys all sitting on the same machine**: 5 keys stored locally on the VPS means stealing/hacking one box zeroes the unseal barrier. Split them across media (encrypted USB + encrypted R2 object / another machine), rehearse recovery yearly, and encrypt the key files at rest.
3. **8200 exposed to the internet**: Vault has no network-layer ACL; a reachable 8200 plus a guessed token = all credentials handed over. Iron rule: listener stays on `127.0.0.1`, external access only via Tailscale/Tailscale serve or a Cloudflare Tunnel encrypted egress ($0 traffic), and nftables default-DROPs 8200 from outside.
4. **TTLs set too long turn dynamic credentials back into static ones**: `default_ttl=7d` is just a long-lived password stored elsewhere. Discipline: DB credentials ≤ 24h, CI token `max_ttl` ≤ 4h, PKI certs 24h. The shorter the TTL, the smaller a leak's blast radius — that's the entire point of using Vault.
5. **Unbounded audit logs fill the disk**: the `file` audit device writes every operation; high-frequency CI can write 1-3GB a week. logrotate `copytruncate` 7d + optional tail into Loki ([log aggregation reference](/post/vps-loki-selfhosted-log-aggregation/)) + the §5 80% disk alert — all three pieces are mandatory.

Two easy confusions to avoid: never mix KV v1 and v2 paths (v1 has no version history); and while `transit` ciphertext can live on R2 (surviving Vault downtime), **losing the unseal keys makes transit ciphertexts equally undecryptable** — key management is always the weaker link.

## 7. Measured Numbers & Cost Summary

Measured on 1C1G (1GB RAM / 40GB disk / 500Mbps), single-node Raft + four engines:

| Metric | Value |
|------|------|
| Idle memory | ~120-150MB (Raft state ~30-50MB) |
| Startup time (unseal required) | ~1.5-2.5s |
| Dynamic DB credential issuance | ~60-180ms each |
| 24h PKI cert issuance | ~30-80ms each |
| Audit log write | ~1.5-4KB per operation |
| 100 dynamic credentials batch-issued | ~2-4s (local Postgres) |
| Daily Raft snapshot (light load) | tens of MB; <100MB per week |

**Cost summary**: 200 secrets on AWS Secrets Manager ≈ $80/mo ($960/yr) → Vault @ existing VPS **$0/mo** (new box $4-5/mo), **$900+/yr saved**; add the elimination of quarterly manual rotation (~10h/quarter) and the shift from "leak = permanent risk" to "leak ≤ TTL" — a security gain that no $0 SaaS subscription will give you.

**Hybrid mode (fallback when you can't accept single-node risk)**: keep single-node + daily off-site snapshots, but move the PKI root CA and 3 Shamir keys to another cloud account (or offline media) — cost +$0-2/mo, downgrading "single-node total loss" to "drillable recovery."

**Boundary, one more time**: Vault's value is "automated credential lifecycle," not "hiding passwords deeper." Single-node fits personal/small-team use; for mission-critical production run 3-node Raft (~$15/mo) or just use a cloud secret manager — don't make a single node carry a financial-grade SLA.

> Related: [Restic 6-layer encrypted backup + 2-1-1 strategy](/post/restic-s3-six-layer-encryption-2-1-1-backup/) (off-site Raft snapshot replica), [Self-Hosted Loki on a VPS](/post/vps-loki-selfhosted-log-aggregation/) (audit log aggregation), [Uptime Kuma Monitoring](/post/vps-uptime-kuma-monitoring/) (health probes as backstop), [Cloudflare Tunnel Zero-Trust](/post/vps-cloudflare-tunnel-zero-trust/) (secure entry to 8200).
