---
title: "Self-Hosted DNS on a VPS: Dnsmasq + China-List for a Fast, Correct Resolver"
description: "Public DNS is slow, privacy-hostile, and sometimes poisoned. This guide builds a local resolver on a 1-vCPU / 512MB VPS: Dnsmasq caching, the dnsmasq-china-list split-routing set, DNSSEC validation, hardened systemd units, and Prometheus metrics — measured at 2.7ms average resolution time and 32MB RAM."
date: 2026-10-25T10:30:00+08:00
lastmod: 2026-10-25T10:30:00+08:00
slug: "vps-selfhosted-dnsmasq-china-list"
image: "/images/posts/vps-selfhosted-dnsmasq-china-list/featured-en.png"
tags: ["DNS", "Dnsmasq", "VPS", "Self-hosted", "Networking", "DNSSEC", "Caching", "Ops"]
categories: ["Network & Infrastructure"]
aliases: ["/en/post/vps-selfhosted-dnsmasq-china-list/"]
draft: false
---

## Introduction: you wait through hundreds of DNS lookups a day

One page load triggers 15 to 30 DNS queries: the primary domain, a CDN, analytics, fonts, API subdomains. At 30ms per uncached query, a single page view loses almost a second to name resolution. If a domain is being poisoned, you lose even more — you get a wrong IP and then watch the connection time out.

Most people treat DNS as "set it once and forget it" infrastructure. In reality it is **the easiest link in the chain to optimize, with the most immediate payoff**. This article builds a full local DNS stack on a 1-vCPU / 512MB VPS:

- **Dnsmasq** for recursion via upstreams, caching, and split routing — a tiny C implementation;
- **dnsmasq-china-list** to route mainland-China domains to domestic resolvers and everything else to a clean/encrypted upstream;
- **DNSSEC validation** to reject forged answers;
- **Hardened systemd** and a direct bind on port 53 (no Docker — saves a NAT layer and a lot of complexity);
- **Prometheus textfile metrics** so you can actually see cache hit rates and upstream latency.

Bottom line up front: **0.2–0.4ms on cache hits, 2.7ms average overall, 32MB resident memory, negligible CPU.**

---

## 1. Why Dnsmasq and not Unbound / CoreDNS

All three can serve as a local resolver. The trade-offs are clear:

| Option | Recursion | Split routing | Memory | Best for |
|---|---|---|---|---|
| **Dnsmasq** | Via upstreams (can chain to `unbound` for true recursion) | Trivial — one line: `server=/cn/1.1.1.1` | ~30MB | Single-box caching + split routing; chosen here |
| Unbound | Native, full DNSSEC | Medium — multiple `forward-zone` blocks | ~60MB | Pure recursion, no third-party upstreams |
| CoreDNS | Plugin composition | Medium — Corefile + hosts plugin | ~80MB | Multi-instance, Kubernetes |

For a single VPS, **what we want is fast + split + maintainable**, not "pure recursion". Dnsmasq has essentially no rival in that lane: a dozen lines of config, reload without losing the cache, `SIGHUP` and you're done.

> If you insist on fully independent recursion (zero third-party upstreams), section 7 shows the Unbound-in-front variant, with Dnsmasq reduced to cache + split-routing front end.

---

## 2. Architecture

```
                    ┌──────────────────────────────────────────┐
   LAN / local apps │  VPS  (1 vCPU / 512MB)                    │
   ┌───────────┐    │                                          │
   │ app / curl│───▶│  dnsmasq :53  (bind 127.0.0.1 + private)  │
   └───────────┘    │      │                                   │
                    │      ├─ cache hit ──▶ answer (<0.5ms)     │
                    │      │                                   │
                    │      ├─ domain ∈ china-list ──▶ 223.5.5.5│
                    │      │                          119.29…  │
                    │      │                                   │
                    │      └─ everything else ──▶ 1.1.1.1      │
                    │                             9.9.9.9       │
                    │                                          │
                    │  china-list sync (systemd timer)         │
                    │  metrics exporter (textfile, 60s)        │
                    └──────────────────────────────────────────┘
```

Three responsibilities:

1. **Cache layer** — `cache-size=10000`, answer from memory. This is where 90% of the benefit comes from.
2. **Split layer** — the `server=/domain/upstream` syntax. Chinese domains go to Chinese resolvers, avoiding "routed to Hong Kong and back" CDN answers.
3. **Validation layer** — `dnssec` asks upstreams for signed answers and verifies them against the built-in trust anchor (Cloudflare and Quad9 support this; some domestic resolvers do not).

---

## 3. Install and a minimal working config

Debian 12 / Ubuntu 24.04:

```bash
sudo apt update
sudo apt install -y dnsmasq dnsutils curl jq

# Stop systemd-resolved from squatting on port 53
sudo systemctl disable --now systemd-resolved
sudo rm -f /etc/resolv.conf
sudo ln -s /run/systemd/resolve/resolv.conf /etc/resolv.conf 2>/dev/null || true

# Confirm port 53 is free
sudo ss -lunp | grep ':53 ' || echo "53 is free"
```

`/etc/dnsmasq.d/10-base.conf`:

```ini
# ---- Listeners ----
# Only loopback and the private interface. Never open 53 to the public
# internet, or you become an open resolver and a DDoS amplifier.
listen-address=127.0.0.1,10.0.0.5
bind-interfaces
# To serve other LAN machines, use instead:
# interface=eth0
# except-interface=lo

# ---- Upstreams and cache ----
no-resolv
no-poll
domain-needed
bogus-priv
cache-size=10000
min-cache-ttl=300
max-cache-ttl=86400
neg-ttl=60

# ---- Default upstreams (non-China domains) ----
server=1.1.1.1
server=9.9.9.9

# ---- Logging (on while tuning, off when stable) ----
log-queries=extra
log-facility=/var/log/dnsmasq.log
log-async=20
```

Changes to `bind-interfaces` need a `systemctl restart`; `SIGHUP` is not enough.

**A note on `min-cache-ttl`:** the docs are explicit that it overrides upstream TTLs and therefore violates the RFC. 300s is almost harmless for self-hosting, but if you host services that need fast IP failover, drop it to 60 or remove it.

---

## 4. Split routing with dnsmasq-china-list

`dnsmasq-china-list` (GitHub: `felixonmars/dnsmasq-china-list`) is a community-maintained list of domains that resolve better through mainland-China DNS.

```bash
sudo install -d /etc/dnsmasq.d/china-list
cd /opt && sudo git clone --depth=1 https://github.com/felixonmars/dnsmasq-china-list.git
sudo cp dnsmasq-china-list/build/accelerated-domains.china.conf /etc/dnsmasq.d/china-list/
sudo cp dnsmasq-china-list/build/bogus-nxdomain.china.conf /etc/dnsmasq.d/china-list/ 2>/dev/null || true
```

Each line is just a `server=` directive:

```
server=/baidu.com/223.5.5.5
server=/qq.com/119.29.29.29
```

**Things to know:**
- These entries **override your default upstream** but **do not override** a more specific `server=/a.baidu.com/...` that you wrote yourself. Specific beats general, which is intuitive.
- The file is huge (tens of thousands of lines). Dnsmasq takes an extra 100–200ms to start. One-time cost.
- Keep it in its own directory so you can replace the whole directory atomically.

### Automatic updates (systemd timer)

```ini
# /etc/systemd/system/china-list-update.service
[Unit]
Description=Update dnsmasq-china-list
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=/opt/dnsmasq-china-list
ExecStart=/usr/local/bin/update-china-list.sh
```

```ini
# /etc/systemd/system/china-list-update.timer
[Unit]
Description=Weekly dnsmasq-china-list refresh

[Timer]
OnCalendar=Sun 04:17
RandomizedDelaySec=900
Persistent=true

[Install]
WantedBy=timers.target
```

`/usr/local/bin/update-china-list.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

REPO=/opt/dnsmasq-china-list
DEST=/etc/dnsmasq.d/china-list
STAMP=/var/lib/china-list/last-update

git -C "$REPO" pull --ff-only --quiet

# Reload only when content actually changed, so we don't churn the cache
mkdir -p "$(dirname "$STAMP")"
if ! diff -rq "$REPO/build" "$DEST" >/dev/null 2>&1; then
  install -m 644 "$REPO"/build/*.conf "$DEST"/
  systemctl reload dnsmasq
  date -Is > "$STAMP"
  logger -t china-list "updated, dnsmasq reloaded"
else
  logger -t china-list "no change"
fi
```

> `systemctl reload dnsmasq` sends `SIGHUP`, which re-reads config while keeping cached entries. Weekly updates are effectively invisible.

---

## 5. Enabling DNSSEC validation

```ini
# /etc/dnsmasq.d/20-dnssec.conf
dnssec
# Trust anchor ships with the package at /usr/share/dns/root.key
# Manual alternative:
# trust-anchor=.,20326,8,2,E06D44B80B8F1D39A95C0B0D7C65D08458E880409BBC683457104237C7F8EC8D
```

Verify:

```bash
dig +dnssec sigfail.verteiltesysteme.net @127.0.0.1
# Expect: status: SERVFAIL (the signature is deliberately broken)

dig +dnssec cloudflare.com @127.0.0.1 | grep -E 'flags|status'
# Expect: flags: qr rd ra ad;   status: NOERROR   ← 'ad' means validated
```

**Gotcha:** many domestic upstream resolvers strip or mangle DNSSEC records. With `dnssec` enabled, those domains return `SERVFAIL` — which users experience as "some sites won't load". Dnsmasq cannot disable DNSSEC per-domain, so if you hit this, your options are: point those domains at an upstream that does pass records through, or only run DNSSEC on the default path. The clean answer is the Unbound front end in section 7.

---

## 6. Cache tuning: getting past 90% hit rate

Dnsmasq's cache is a simple LRU hash table; there isn't much to tune, but a few parameters matter.

| Parameter | Suggested | Why |
|---|---|---|
| `cache-size` | 10000 | ~100 bytes per entry, so ~1MB total |
| `min-cache-ttl` | 60–300 | Overrides short upstream TTLs, raises hit rate (RFC violation, fine for self-use) |
| `max-cache-ttl` | 86400 | Prevents absurd TTLs from pinning entries |
| `neg-ttl` | 60 | Cache NXDOMAIN too, cutting useless upstream queries |
| `dns-forward-max` | 150 | Concurrent upstream queries; keep low on small boxes |

Measuring hit rate is easiest from logs (enable `log-queries` temporarily):

```bash
awk '/cached/ {c++} /forwarded/ {f++} END {printf "cached=%d forwarded=%d hit=%.1f%%\n", c, f, c*100/(c+f)}' \
  /var/log/dnsmasq.log
```

On typical office/developer traffic I measured **88–93% after 24 hours of uptime**; the tail is new-domain first lookups.

---

## 7. Hardening the systemd unit

Don't run it as root. Dnsmasq needs exactly one capability, `CAP_NET_BIND_SERVICE`, to bind port 53:

```ini
# /etc/systemd/system/dnsmasq.service.d/hardening.conf
[Service]
User=dnsmasq
Group=dnsmasq
AmbientCapabilities=CAP_NET_BIND_SERVICE
CapabilityBoundingSet=CAP_NET_BIND_SERVICE
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
PrivateDevices=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
RestrictNamespaces=yes
LockPersonality=yes
MemoryDenyWriteExecute=yes
SystemCallFilter=@system-service
ReadWritePaths=/var/log /var/lib/misc
```

```bash
sudo systemctl daemon-reload
sudo systemctl restart dnsmasq
sudo systemctl status dnsmasq --no-pager
```

**Gotcha:** `ProtectSystem=strict` makes `/etc/dnsmasq.d` read-only (good), but forgetting `/var/lib/misc` in `ReadWritePaths` breaks startup, because that's where `dnsmasq.leases` lives.

---

## 8. Observability: Prometheus textfile metrics

Dnsmasq doesn't expose metrics. A small script can count log lines and read process memory:

```bash
#!/usr/bin/env bash
# /usr/local/bin/dnsmasq-metrics.sh
set -euo pipefail
OUT=/var/lib/node_exporter/textfile/dnsmasq.prom
LOG=/var/log/dnsmasq.log
TMP=$(mktemp)

cached=$(grep -c 'cached' "$LOG" 2>/dev/null || echo 0)
forwarded=$(grep -c 'forwarded' "$LOG" 2>/dev/null || echo 0)
total=$((cached + forwarded))

rss=$(systemctl show dnsmasq -p MemoryCurrent --value)
rss=${rss:-0}

{
  echo "# HELP dnsmasq_queries_total Total queries seen in current log"
  echo "# TYPE dnsmasq_queries_total counter"
  echo "dnsmasq_queries_total{result=\"cached\"} $cached"
  echo "dnsmasq_queries_total{result=\"forwarded\"} $forwarded"
  echo "# HELP dnsmasq_cache_hit_ratio Cached / total since log rotation"
  echo "# TYPE dnsmasq_cache_hit_ratio gauge"
  if [ "$total" -gt 0 ]; then
    awk -v c="$cached" -v t="$total" 'BEGIN{printf "dnsmasq_cache_hit_ratio %.4f\n", c/t}'
  else
    echo "dnsmasq_cache_hit_ratio 0"
  fi
  echo "# HELP dnsmasq_memory_bytes Resident memory of dnsmasq"
  echo "# TYPE dnsmasq_memory_bytes gauge"
  echo "dnsmasq_memory_bytes $rss"
} > "$TMP"

mv "$TMP" "$OUT"
```

Run it from a 60-second timer. Suggested alert: `dnsmasq_cache_hit_ratio < 0.6` for 30 minutes — usually means the upstream or the list broke.

---

## 9. Measured results

Test rig: KVM, 1 vCPU (EPYC 7B13), 512MB, Debian 12, list of 78,412 entries, cache warmed for 24 hours.

**Resolution latency (average of 1000 `dig` runs)**

| Case | Mean | P95 | P99 |
|---|---|---|---|
| Cache hit | 0.28ms | 0.51ms | 0.94ms |
| China domain (miss → 223.5.5.5) | 9.4ms | 18ms | 27ms |
| Overseas domain (miss → 1.1.1.1) | 41ms | 78ms | 132ms |
| Before (ISP DNS directly) | 28ms | 61ms | 155ms |

**Resource usage**

| Metric | Value |
|---|---|
| Resident memory | 32 MB |
| Startup time | 0.4s (including list load) |
| CPU (daily average) | 0.3% |
| Hit rate (steady state) | 91.2% |

**Page-load effect:** measuring the same site with `curl -w`, DNS-related time dropped from 340ms to 12ms (24 of 26 queries hit cache).

---

## 10. Advanced: Unbound for true recursion, Dnsmasq in front

If you refuse any third-party upstream (maximum privacy), change the topology to:

```
dnsmasq :53  (cache + split) ──▶ unbound 127.0.0.1:5335 (recursion + DNSSEC)
```

Dnsmasq only needs one line changed:

```ini
server=127.0.0.1#5335
```

Minimal Unbound config:

```yaml
# /etc/unbound/unbound.conf.d/recursive.conf
server:
  interface: 127.0.0.1
  port: 5335
  do-daemonize: no
  access-control: 127.0.0.0/8 allow
  hide-identity: yes
  hide-version: yes
  qname-minimisation: yes
  prefetch: yes
  num-threads: 1
  msg-cache-size: 32m
  rrset-cache-size: 64m

  auto-trust-anchor-file: "/var/lib/unbound/root.key"
  val-clean-additional: yes

  # Refuse private addresses to blunt DNS rebinding
  private-address: 10.0.0.0/8
  private-address: 172.16.0.0/12
  private-address: 192.168.0.0/16
  private-address: 169.254.0.0/16
  private-address: fd00::/8
```

The cost is **much slower cold-cache lookups**: a full recursion chain for a China domain measured 120–400ms. So still point the China list at `223.5.5.5`, and let only overseas / privacy-sensitive domains go through Unbound. That's the most pragmatic cut between privacy and speed.

---

## 11. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Mass `SERVFAIL` | `dnssec` on, but upstream strips signatures | Pin those domains to a validating upstream, or disable `dnssec` |
| `failed to create listening socket` | Port 53 taken by `systemd-resolved` or `dockerd` | `ss -lunp \| grep :53`, stop the offender |
| List seemingly ignored | Your own more specific `server=` wins | Verify with `dnsmasq --test` and `dig +short x @127.0.0.1` |
| Low hit rate | No `min-cache-ttl`, or very short upstream TTLs | Set `min-cache-ttl=60`; check for restart loops |
| `SIGHUP` every 5 minutes | `logrotate` uses `postrotate reload` | Change to `systemctl kill -s USR1` or `copytruncate` |

Suggested log rotation:

```
# /etc/logrotate.d/dnsmasq-custom
/var/log/dnsmasq.log {
    weekly
    rotate 4
    compress
    delaycompress
    missingok
    notifempty
    create 640 dnsmasq adm
    postrotate
        /usr/bin/systemctl kill -s USR1 dnsmasq.service || true
    endscript
}
```

`USR1` reopens the log file without dropping the cache.

---

## 12. Summary

| Gain | Number |
|---|---|
| Mean resolution latency | 28ms → **2.7ms** |
| Cache hit rate | — → **91%** |
| DNS time on first paint | 340ms → **12ms** |
| Resource cost | **32MB RAM / 0.3% CPU** |
| Maintenance | Weekly automatic list refresh, zero manual work |

The value of a local resolver isn't "saving money" — it's turning **hundreds of daily waits into a handful**. It's the archetypal self-hosted project: configure once, benefit forever. If you have a second VPS, run Dnsmasq on both and point each at the other as a fallback upstream, and you've removed the single point of failure for free.

Next steps worth doing: switch upstreams from plaintext UDP to DoH (`dnsmasq` 2.90+ supports `server=https://...` natively), or put `dnscrypt-proxy` in front so even your egress queries are encrypted.
