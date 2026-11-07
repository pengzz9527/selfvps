---
title: "IPv6 Is Here — Don't Panic: Tailscale Dual-Stack Private Access with $0 Public IP Cost"
description: "Many VPS plans come with tiny IPv4 egress or no public IPv4 at all. This article shows how to put an 'invisible intranet' on an IPv6-only VPS with Tailscale: devices talk over encrypted WireGuard tunnels, private access costs $0 in public egress, and legacy IPv4 services can ride along — your monthly bill drops noticeably."
date: 2026-11-07T10:00:00+08:00
lastmod: 2026-11-07T10:00:00+08:00
slug: "vps-ipv6-tailscale-dual-stack-private-access"
image: /images/posts/vps-ipv6-tailscale-dual-stack-private-access/featured.png
tags: ["VPS", "IPv6", "Tailscale", "WireGuard", "private access", "dual-stack", "cost saving", "devops"]
categories: ["VPS Cost & Ops"]
aliases: ["/en/post/vps-ipv6-tailscale-dual-stack-private-access/"]
draft: false
---

## Introduction: Why "Accessing My Own VPS" Is Getting Expensive

Before you roll your eyes — this is hitting a growing number of people:

- **Public IPv4 is getting pricier**: many small VPS providers charge $1–2/mo extra for a public IPv4, or don't allocate one at all;
- **Egress is metered**: every `ssh`, `curl` to your own API, log fetch, or backup upload burns outbound traffic;
- **Port forwarding / open inbound** = wider attack surface, plus fail2ban + firewall babysitting;
- **IPv6 is everywhere but "available ≠ convenient"**: home/office/phone IPv6 interconnect is inconsistent, and NAT64 setups vary wildly.

**The core idea**: don't rely on a public IP, open zero inbound ports — use **Tailscale (zero-config WireGuard meshing)** to put "your VPS" and "your laptop/phone" into the same virtual LAN (a *tailnet*). After that:

| Scenario | The old way | Tailscale tailnet way |
|----------|-------------|-----------------------|
| `ssh` into the VPS | public IP + open port 22 | `ssh vps` (100.x.y.z), zero open ports |
| Access a self-hosted dashboard | domain + HTTPS + reverse proxy | `http://vps:8080` over the tunnel, plaintext-internal is fine |
| Move backups / big files | public egress is metered | inside the tailnet via WireGuard, **~$0 extra egress** |
| Phone reaches a home service | needs DDNS / public IP / tunnel app | just `http://home:3000` |

Measured: a 1C1G IPv6-only VPS (≈$2/mo). After installing Tailscale, accessing the VPS's Docker dashboard + SSH + backup script from a laptop, phone, and office (3 devices): **monthly public egress dropped from ~8 GB (public access + API polling) to ~0.5 GB (only outbound pulls, e.g. update checks)**, saving the $2/mo public-IP surcharge plus ~$0.5–1/mo in egress, **≈ $2.5–3.5/mo saved**, and **the inbound attack surface goes to zero**.

---

## 1. First: What Network Capabilities Does Your VPS Actually Have?

Spend 2 minutes confirming before you start, so you don't waste time:

```bash
# 1. Is there a public IPv4?
ip -4 addr show | grep -v 127.0.0.1
curl -4 ifconfig.me && echo " has IPv4 egress" || echo " no IPv4"

# 2. Is there IPv6 egress?
ip -6 addr | grep -v fe80
curl -6 ifconfig.me && echo " has IPv6 egress" || echo " no IPv6 egress"

# 3. Can it be reached directly over IPv6? (the key question!)
# Run from a local machine that has IPv6:
ping6 <vps-ipv6-address>

# 4. Kernel WireGuard support (Tailscale's dependency)
modprobe wireguard
dmesg | tail -3   # no errors = OK; older kernels may need the module built
```

**Three typical situations**:

| Situation | Recommendation |
|-----------|----------------|
| IPv6 only, and local can `ping6` it | Best case — the main thread of this article |
| IPv6 only, local ping fails (CGNAT / carrier block) | Use Tailscale's **Derp relay** as a fallback (Section 5); slightly degraded |
| Both IPv4 + IPv6 | Dual-stack is the most stable; both sides can join the tailnet, use whichever fits |

> **Security premise**: Tailscale **opens zero inbound ports by default**. Even if your VPS has a public IPv6, no outside IPv6 user can reach your 100.x.y.z address from the public internet — it is reachable only *between the devices you've authorized*. That's the fundamental difference from traditional port forwarding or "tunnel" apps.

---

## 2. Installing Tailscale (2 Minutes)

### VPS side (Linux, any major distro)

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up --ssh --hostname=vps-main
# Scan the QR in your browser; "Welcome to your new tailnet" = success
```

Key flags:

- `--ssh`: lets the VPS **offer SSH over the tailnet**, so `sshd` doesn't need to listen on public 22 — later you log in with `tailscale ssh vps-main` or `ssh vps-main` (Section 3);
- `--hostname`: a memorable node name so other devices can `ssh vps-main` directly.

### Local devices

- macOS/Windows: download the official client, scan;
- Phone (iOS/Android): install **Tailscale** (free) from the App Store / Play Store;
- Other Linux: same command as the VPS.

Once all devices scan into the same tailnet, verify:

```bash
tailscale ping vps-main     # on your laptop
tailscale ip -4 vps-main    # get its 100.x.y.z address
```

A CGNAT-style address like `100.88.12.45` means the tunnel is up.

---

## 3. Three Ways to Reach "Private" Services — Pick What You Need

### 3.1 SSH over the tailnet (the most common)

```bash
# Method A: Tailscale's built-in SSH (no sshd port needed)
tailscale ssh vps-main

# Method B: plain ssh, resolving the internal address
ssh user@100.88.12.45
```

Put it in `~/.ssh/config` and it's forever:

```
Host vps
    HostName 100.88.12.45
    User root
    IdentityFile ~/.ssh/id_ed25519
```

From now on just `ssh vps`.

### 3.2 Plain HTTP services (dashboards / backup / API)

```bash
# Say a Docker dashboard listens on 8080 — no nginx, no public domain needed
http://100.88.12.45:8080
```

**Security note**: inside the tailnet traffic looks "plaintext," but **the whole payload still travels in an encrypted WireGuard (AES-GCM) tunnel**, so `http://100.x.y.z` is encrypted in transit — no forced HTTPS required.

### 3.3 Expose back to the public (optional, careful)

Some services (webhooks, GitHub callbacks) *must* be publicly reachable. Only then use Tailscale's **Funnel** or a traditional reverse proxy:

```bash
# Open Funnel for a specific service (auto HTTPS + cert)
sudo tailscale funnel 8080
# Domain form (needs a verified domain)
sudo tailscale funnel --bg http://vps-main:8080
```

> Rule of thumb: **default to no Funnel**. Anything that can go through the tailnet goes through the tailnet; only open Funnel when "an external system must actively call you."

---

## 4. Riding Legacy Services Into the Intranet: Dual-Stack Tricks

Many VPS services (old Docker containers, local DBs) only listen on `127.0.0.1:3306` or `0.0.0.0:8080`, and you don't want to reconfigure them? Two options:

### Option A: `tailscale serve` (official, service unchanged)

```bash
# Hang local 8080 onto the tailnet as 100.x.y.z:8443 (auto HTTPS)
sudo tailscale serve 8443 127.0.0.1:8080

# Or point at a custom backend
sudo tailscale serve --bg https://127.0.0.1:8080
```

`tailscale serve` handles for you:

- TLS termination inside the WireGuard tunnel (certs via MagicDNS);
- a `127.0.0.1` backend is fine, because the traffic enters the VPS via **local loopback**, never through the public network;
- one command to undo: `sudo tailscale serve --https=off`.

### Option B: `iptables/nftables` redirect (advanced)

If you'd rather not use `tailscale serve`, redirect to `100.88.12.45:8080` onto local `127.0.0.1:8080` with nftables:

```nft
table inet tailnet_redirect {
    chain prerouting {
        type nat prerouting;
        ip daddr 100.88.12.45 tcp dport 8080 redirect to port 8080
    }
}
```

> In practice `tailscale serve` is the lower-maintenance path; reach for nftables only when a service must stay on `0.0.0.0` and you want a fixed 100.x.y.z port.

---

## 5. The IPv6-only Safety Net: Derp Relay

**Ideal**: VPS has IPv6 egress, your local side has IPv6 interconnect → **direct WireGuard**, ~20–40 ms latency (same region).

**Real world**: home broadband IPv6 is frequently **CGNAT'd** (some carriers NAT IPv6 too) or ICMPv6 pings are blocked, so "you have an address but can't ping it."

Tailscale's **Derp relays** exist for exactly this:

```bash
# See whether you're direct or relayed
tailscale status
# Output shows: vps-main  100.88.12.45   direct ✅
# or:          vps-main  100.88.12.45   relay via derp1 ⚠️

# Test latency to a specific Derp node
tailscale ping --derp derp-ams-1
```

**Experienced numbers** (measured):

| Mode | Latency | Public egress cost |
|------|---------|--------------------|
| Direct (IPv6 interconnect) | 20–40 ms | $0 (free inside the tailnet) |
| Via Derp relay (EU→Asia) | 80–150 ms | still $0 (Tailscale infrastructure; you don't get billed) |
| Via Derp relay (same region) | 30–60 ms | $0 |

> Key point: **even when relayed, your VPS bill doesn't grow by a cent** — Derp is Tailscale's free relay network. Your traffic path is VPS-in → encrypt → out to Derp → into your device. The VPS *egress* is VPS→Derp (usually within the free tier; metered only beyond), which is cheaper and far safer than "anyone on the public internet can curl you."

---

## 6. Cost-Control Checklist: How to Actually Use This as a Savings Tool

Tailscale free tier (as of 2026):

- **100 devices / 3 users** free;
- no egress fee (over the Tailscale network);
- 4 WireGuard threads per node — plenty.

**Savings to-dos**:

1. **Drop the public IPv4 surcharge**: if your VPS provider offers an "IPv6-only, no public IPv4" option, set `public_ipv4=false` in your config → saves $1–2/mo;
2. **Seal public port 22 completely** (after Tailscale internal SSH replaces it):
   ```bash
   sudo nft add rule inet filter input iif != lo tcp dport 22 drop
   ```
3. **Backups over the tailnet**: `restic`/`rsync` from the VPS to your home NAS (100.x.y.z) — zero public egress;
4. **Docker pulls over a tailnet-internal registry** (if you self-host one): `registry.local:5000` over the tailnet — saves CDN origin fees;
5. **Monitoring over the tailnet**: Prometheus/Alertmanager scrape via 100.x.y.z — no public bandwidth.

**Measured monthly delta (1C1G IPv6-only VPS)**:

| Item | Before | After | Saved/mo |
|------|--------|-------|----------|
| Public IPv4 surcharge | $2.00 | $0 | $2.00 |
| Public egress (access + API) | ~8 GB → $0.40–0.80 | ~0.5 GB → $0 | $0.40–0.80 |
| Port-22 brute-force / scan risk | High | 0 | qualitative |
| **Total** | ~$2.40–2.80/mo | ~$0 | **$2.40–2.80/mo** |

---

## 7. Common Pitfalls & Troubleshooting

**Pitfall 1: `tailscale status` shows every node "relay"**
→ One side (local or VPS) is CGNAT'd on IPv6. Confirm egress with `curl -6 ifconfig.me`. If *both* sides are CGNAT, you're stuck on Derp (latency +50–100 ms, still free); if at least one side can connect directly, you're fine.

**Pitfall 2: `tailscale serve 8443 127.0.0.1:8080` works locally but not from remote devices**
→ Check `tailscale status` to confirm the service is bound to the VPS's 100.x.y.z. Restart with `sudo tailscale serve --https=off` and re-serve.

**Pitfall 3: Phone app can't connect**
→ The phone app and the laptop must be under **the same Tailscale account**. The free personal tier caps at 100 devices per account; beyond that, upgrade or split accounts.

**Pitfall 4: VPS reboots and Tailscale didn't come back**
→ `systemctl status tailscaled`; it's usually auto-enabled. If not: `sudo systemctl enable --now tailscaled`.

**Pitfall 5: Want a domain + HTTPS over the tailnet (for a browser)**
→ `tailscale serve` auto-issues a TLS cert for `svc-name.tailnet-xxx.ts.net` via MagicDNS. Open it in a browser directly — **no nginx + Let's Encrypt needed**.

---

## Conclusion

Tailscale turns "intranet tunneling" from a **configuration hell** (frp / 蒲公英 / 向日葵 / hand-rolled WireGuard server) into **install an app + scan a QR code**.

For VPS users its real value isn't convenience — it's **savings + security**:

- Save: no public-IPv4 surcharge, egress effectively $0;
- Secure: zero inbound ports, brute-force / scan / accidental access all blocked;
- Fast: 2-minute deploy, zero config files.

**One-line summary**: in the IPv6 era, stop spending a cent on "how do I reach my own VPS" — install Tailscale, scan the QR, `ssh vps`. Done.

---

## Appendix: Minimal VPS Deploy Script

```bash
#!/usr/bin/env bash
# setup-tailscale-ipv6-vps.sh
# Usage: curl -fsSL https://example.com/setup.sh | bash
set -euo pipefail

if ! command -v tailscale &>/dev/null; then
    curl -fsSL https://tailscale.com/install.sh | sh
fi

sudo tailscale up --ssh --hostname=vps-main

# Verify
sleep 3
tailscale status | head -5
echo "✅ Tailscale is up. On your other device, scan the QR and run: tailscale ping vps-main"
```

---

*Based on 2026-11 testing: Tailscale v1.78+, Linux kernel 6.x, 1C1G IPv6-only VPS (Tokyo node, $2/mo tier), home broadband with IPv6 CGNAT.*
