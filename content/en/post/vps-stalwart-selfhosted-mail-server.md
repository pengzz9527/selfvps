---
title: "Self-Hosted Stalwart on a VPS: $0/mo Mail Server That Replaces Google Workspace"
date: 2026-11-19
tags: ["VPS", "Stalwart", "Mail", "Self-hosting", "Cost Savings", "DKIM", "DMARC", "DevOps"]
draft: false
image: /images/posts/vps-stalwart-selfhosted-mail-server/featured.png
description: "Run Stalwart (a single Rust binary, ~95MB idle) on a 1C1G VPS: SMTP + IMAP + JMAP + CalDAV/CardDAV in one process, built-in SPF/DKIM/DMARC validation and Let's Encrypt, replacing a 5-user Google Workspace ($35-70/mo) for $0, saving $430-840/yr. Port-25/rDNS pre-checks, full DNS config, 8-week warm-up discipline, 5 hard-won pitfalls."
---

# Self-Hosted Stalwart on a VPS: $0/mo Mail Server That Replaces Google Workspace

Mail is the one line item that almost always gets skipped on the self-hosting list: you self-host your sync with Syncthing, your search with SearXNG, your monitoring with Uptime Kuma — but nobody self-hosts their inbox, because "mail servers are hard" has been the folklore for fifteen years. The things that are actually hard are three: outbound port 25, a settable PTR record, and deliverability discipline. Do those three as pre-checks before you buy anything, and the rest is a single binary idling at ~95MB.

**Stalwart** (a modern mail server written in Rust, Apache-2.0) drives this to the floor:

- **One binary, no JVM, no dependencies**: SMTP (25/465/587) + IMAP (143/993) + JMAP (443) + CalDAV + CardDAV in a single process, ~95MB idle, which fits a 1C1G VPS;
- **Compliance built in**: SPF/DKIM/DMARC/ARC validation, Let's Encrypt automation, content filtering — no sidecar zoo;
- **REST admin API** (JSON on 127.0.0.1:8081): create domains, users, and fetch DKIM keys with curl — fully scriptable, no web UI required;
- **Data on your infrastructure**: mailboxes, calendars, and contacts live on your VPS disk, and with a nightly restic backup to R2 ($0 egress) a departure, a cancellation, or a price hike never touches it.

A 5-user Google Workspace costs roughly $35-55/mo on annual billing ($7-12/user); M365 Business starts around $30/mo. Put Stalwart on a VPS you already have (or a ~$4/mo box), and you're at **$0-5/mo, saving $430-840/yr**.

## 1. The math: calculate before you build

Scenario: a 5-person team / family sharing, 5-20GB mailboxes each plus calendars and contacts, currently on a hosted mail SaaS.

| Option | 5-user monthly | Data lives in | Notes |
|--------|:---:|:---:|-------|
| Google Workspace Starter | $35-45 | Vendor cloud | $7/user annual; monthly billing adds ~30% |
| Google Workspace Standard | $70-90 | Vendor cloud | $14/user annual, 25GB each |
| M365 Business Basic | $30-40 | Vendor cloud | $6/user, includes Teams/SharePoint |
| Zoho Mail | $5-30 | Vendor cloud | Cheapest SaaS fallback, still not yours |
| **Stalwart @ 1C1G VPS** | **$0-5** | Your VPS | $0 if the VPS exists; $4-5 for a new box |

**Saves $430-840/yr** for 5 users, with no 5TB shared-pool ceiling, no lock-in, and a complete encrypted backup you can carry away.

**The boundary, stated upfront**: self-hosted mail ≠ 100% inbox placement. Deliverability is *operational discipline*, not a feature — the port-25/PTR pre-checks in section 4 and the 8-week warm-up in section 5 are non-negotiable. If you can't do them, use the hybrid mode from section 7.

## 2. Why one binary can run the whole mail stack

The classic stack is Postfix + Dovecot + OpenDKIM + Amavis + Rspamd + an ACME client: six components, five config files, four failure domains. Stalwart's model is **one Rust process + one config + one REST API**:

| Protocol | Port | Purpose |
|----------|:---:|---------|
| SMTP inbound | 25 | Other MTAs deliver to you |
| Submission | 587 / 465 | Your clients send (authenticated) |
| IMAP | 143 / 993 | Read on any mature client |
| JMAP | 443 (HTTP/2) | Modern mobile sync, 60%+ less traffic than IMAP |
| CalDAV / CardDAV | 443 | Calendars/contacts for iCal clients |
| Admin API | 127.0.0.1:8081 | JSON REST: domains/users/DKIM/certs |

Key design points:

- **Built-in key-value store**: no external database needed at small scale; flip to a Postgres/MySQL backend as you grow — a hot config switch;
- **Native ACME**: Let's Encrypt certs auto-issue and renew; JMAP/CalDAV on 443 is plain HTTPS, no Caddy/Nginx in front;
- **JMAP is kind to a 1C1G box**: stateless HTTP/2 batch sync means pulling 1,000 messages costs an order of magnitude less bandwidth and CPU than IMAP IDLE polling.

## 3. Architecture: four roles on one VPS

```
 [Thunderbird / Apple Mail / IMAP phones] ──993──▶ ┌──────────────────────────┐
 [local scripts / CI senders]          ──587──▶  │  Stalwart (1 process)    │
 [Gmail/other-domain MTAs]             ──25 ──▶  │  SMTP+IMAP+JMAP+CalDAV  │
 [battery-conscious mobile sync]       ──443──▶  │  built-in ACME/SPF/DKIM │
 └────────────────────────────────┬────────────────┘ DMARC/content filter
              127.0.0.1:8081 REST admin API (loopback only)
              ┌───────────────────▼──────────────────┐
              │ curl automation: domains, users,     │
              │ DKIM public keys, cert status         │
              └───────────────────┬──────────────────┘
 [restic nightly] ──encrypted──▶ [R2 object storage, $0 egress] (off-site copy)
 [Uptime Kuma]      ──probes───▶ IMAP login / SMTP EHLO / JMAP ping
```

The admin API binds to loopback only; external access goes through a Cloudflare Tunnel zero-trust entry point (see [Cloudflare Tunnel zero-trust access](/en/post/vps-cloudflare-tunnel-zero-trust/)) — 8081 never faces the public internet.

## 4. Deploy: systemd + full DNS

### 0. Pre-checks (do these before buying the box)

90% of self-hosted mail fails after purchase, when it turns out the port was blocked. Two hard gates:

```bash
# 1) Port 25: test inbound from [another machine], test outbound from the VPS
nc -vz mail.example.com 25 -w 5          # inbound
# on the VPS: nc -vz gmail-smtp-in.l.google.com 25 -w 5   # outbound

# 2) PTR: can this IP have a reverse record, and does dig -x see it?
dig -x YOUR_IP +short
```

DigitalOcean / Vultr / AWS **block outbound 25 by default** (tickets may be denied or re-blocked); Hetzner, Netcup, and OVH (ticket) ship with it open. **If the VPS can't do "port 25 reachable + dedicated IP + settable PTR", go straight to the hybrid mode in section 7 — don't fight it.**

### 1. Install (pinned version, systemd-managed)

```bash
sudo useradd -r -s /usr/sbin/nologin stalwart
sudo mkdir -p /etc/stalwart /var/lib/stalwart /var/log/stalwart
VER=v2026-05; ARCH=amd64
curl -fsSLO "https://stalw.art/install/${VER}/stalwart-mysql-${ARCH}.tar.gz" \
  && tar xzf stalwart-mysql-${ARCH}.tar.gz -C /usr/local/bin

sudo cat > /etc/systemd/system/stalwart.service <<'EOF'
[Unit]
Description=Stalwart Mail Server
After=network-online.target
[Service]
User=stalwart
ExecStart=/usr/local/bin/stalwart
RuntimeDirectory=stalwart
MemoryMax=512M
CPUQuota=75%
Restart=on-failure
[Install]
WantedBy=multi-user.target
EOF
sudo systemctl enable --now stalwart
```

`MemoryMax=512M` leaves headroom: ~95MB idle, but bulk receipt of large attachments can spike to 200-300MB.

### 2. Minimal config (built-in store + ACME + auto-DKIM)

Core of `/etc/stalwart/config.toml`:

```toml
server.type = "main"
server.bind = ["0.0.0.0:25", "0.0.0.0:143", "0.0.0.0:465", "0.0.0.0:587", "0.0.0.0:443"]
tls.letsencrypt.domain = "mail.example.com"

dkim = { enabled = true, auto = true, ttl = 30 }          # keys auto-generated per domain
admin.bind = "127.0.0.1:8081"                              # admin API loopback-only
store.type = "builtin"                                      # no DB at small scale
store.path = "/var/lib/stalwart"
```

### 3. DNS records (all five at once)

| Type | Host | Value |
|------|------|-------|
| A | mail.example.com | VPS_IP |
| MX | example.com | 10 mail.example.com |
| TXT | example.com (SPF) | `v=spf1 ip4:VPS_IP -all` |
| TXT | mail._domainkey.example.com | public key from the curl below |
| TXT | _dmarc.example.com | `v=DMARC1; p=none; rua=mailto:dmarc@example.com; pct=100` |

PTR (rDNS) is not in your DNS panel — file it with the VPS provider: `VPS_IP → mail.example.com`.

### 4. Create the domain + publish the DKIM public key

```bash
ADMIN=http://127.0.0.1:8081
curl -s -X POST "$ADMIN/config/set" -H 'content-type: application/json' \
  -d '{"path":["domain","example.com"],"data":{"enabled":true,"dkim":{"auto":true}}}'
curl -s -X POST "$ADMIN/user/example.com/you" -d '{"password":"..."}'

# fetch the DKIM public key → publish as TXT record mail._domainkey.example.com
curl -s "$ADMIN/dkim/example.com/mail/public"
```

### 5. Verify (all three green before enabling clients)

1. **mail-tester.com**: send yourself a test, target ≥9/10;
2. **MXToolbox**: SPF/DKIM/DMARC/PTR/MX each passing;
3. **Live inbox test**: one mail each to Gmail / Outlook / Apple Mail — it must land in the **inbox**, not junk.

### 6. Client settings

| Item | Value |
|------|-------|
| IMAP | mail.example.com:993/SSL, username = full email address |
| SMTP | mail.example.com:587/STARTTLS, same credentials |
| CalDAV | https://mail.example.com/dav/calendar/ |
| JMAP | https://mail.example.com/jmap/ (prefer on new clients — cheaper, lighter on batteries) |

## 5. Monitoring: Prometheus + Uptime Kuma + weekly health checks

The insidious failure mode of mail is *silence*: you land on Spamhaus and keep sending, the recipient keeps "receiving" — it just quietly lands in spam. Nobody notices without monitoring.

- **Prometheus textfile**: the Stalwart admin API exposes `/metrics`; curl it every 5 minutes into a textfile directory, scrape with Prometheus. Three alerts:
  - SMTP reject/delivery-failure rate >2/hour → P1;
  - weekly Spamhaus API check hits SBL/XBL → immediate page-level alert;
  - data disk >80% → P2 (mailbox growth is the disk killer).
- **Uptime Kuma** with three probes ([deployment reference](/en/post/vps-uptime-kuma-monitoring/)): IMAP login, SMTP `EHLO`, JMAP `capabilities` ping; any failure pushes to **Gotify** ([reference](/en/post/vps-gotify-selfhosted-realtime-alerts/));
- **Weekly cron health check**: mail-tester + the three major blocklists, results into Loki ([log aggregation reference](/en/post/vps-loki-selfhosted-log-aggregation/)), auto-alert when the score drops below 7/10.

## 6. Five pitfalls (all walked into)

1. **Buying the box first, checking ports after**: unblocking port 25 on DO/Vultr is a lottery — some regions are permanently closed. Run the nc/dig checks in section 4 *before* purchase; this is the only one you cannot fix later.
2. **Volume spikes during warm-up**: week one is 10-20 mails/day to real, active recipients, double every 7 days for 8 weeks. **Any marketing mail, bulk send, or unknown-recipient list burn will get the domain onto SBL/XBL, where recovery takes weeks to months** — keep a separate warm-up domain.
3. **Auto-forwarding destroys your sender score**: Gmail's spam-rate red line is ~0.3%, Outlook's ~0.1% — one forwarding storm to dead addresses hits it. Turn catchall off; before forwarding, verify the recipient's domain has an MX record; failures go to a manual NDR queue.
4. **Data lives only on the VPS disk**: the built-in store is a single directory. VPS dies = mail dies. Nightly restic incremental + off-site R2 copy (2-1-1 strategy, [reference](/en/post/vps-restic-s3-six-layer-encryption-2-1-1-backup/)); R2 egress is $0.
5. **Watching traffic instead of placement**: an SMTP 220 response is not inbox delivery. The Kuma three-probes + weekly mail-tester cron + blocklist alerts in section 5 are the floor, not "it still seems to work".

## 7. Measured data and cost summary

Measured on a 1C1G (1GB RAM / 40GB disk / 500Mbps):

| Metric | Value |
|--------|-------|
| Idle memory (built-in store) | ~95MB |
| Startup time | ~1.5s |
| Idle CPU | <1% on 1C |
| Inbound acceptance of 1,000 small mails | 2-4s |
| JMAP sync of 1,000 messages (mobile) | 200-400ms |
| 2GB mailbox + 500 calendar events | no strain |

**Cost summary**: 5 users on Google Workspace/M365 at $30-90/mo → Stalwart on an existing VPS **$0/mo** (or $4-5/mo on a new box), saving **$430-840/yr**; in exchange your mail/calendars/contacts are fully self-owned, with no subscription lock-in and a complete encrypted off-site backup.

**Hybrid mode (the fallback when pre-checks fail)**: keep a $1-7/user SaaS mailbox **purely as the outbound relay**; all reading and storage stay on your self-hosted IMAP/JMAP. You keep the data sovereignty and hand deliverability to the SaaS — still 80%+ savings.

**The boundary, one more time**: the value of self-hosted mail is "data owned + $0 subscription", not "a cold-outreach marketing channel". If your job is cold outreach or marketing blasts, don't send from your primary domain on a self-hosted server — deliverability discipline cannot absorb commercial volume; that path belongs to a professional mail provider.

> Related: [Restic 6-layer encrypted backup + 2-1-1 strategy](/en/post/vps-restic-s3-six-layer-encryption-2-1-1-backup/) (off-site mail copies), [Self-Hosted Loki on a VPS](/en/post/vps-loki-selfhosted-log-aggregation/) (mail service log aggregation), [Uptime Kuma monitoring](/en/post/vps-uptime-kuma-monitoring/) (three-probe safety net), [Cloudflare Tunnel zero-trust](/en/post/vps-cloudflare-tunnel-zero-trust/) (admin API entry point).
