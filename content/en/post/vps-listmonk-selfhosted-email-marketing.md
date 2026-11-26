---
title: "Self-Host Listmonk: $0-5/mo Mailchimp/Brevo Replacement on a 1C1G VPS"
date: 2026-11-26
tags: ["VPS", "Listmonk", "Email Marketing", "Self-hosting", "Cost Savings", "PostgreSQL", "DevOps"]
draft: false
image: /images/posts/vps-listmonk-selfhosted-email-marketing/featured.png
description: "Listmonk (MIT, single Go binary ~15MB) + PostgreSQL idles at ~60-100MB on a 1C1G VPS: campaigns, subscribers, event automations, segments and templates, 10k sends in 3-8 minutes on one core. $0-5/mo replaces Mailchimp/Brevo/Klaviyo ($15-50/mo and up), saving $180-600/yr. Outbound-25 pre-checks, IP-reputation warm-up discipline, Postgres bloat control, and 5 hard-won pitfalls."
---

# Self-Host Listmonk: $0-5/mo Mailchimp/Brevo Replacement on a 1C1G VPS

Newsletter, product digest, EDM campaigns, win-back flows — the moment your product has "send mail to a list", you start fighting email-marketing SaaS bills: **Mailchimp, Brevo, Klaviyo and friends meter three stacked meters — subscribers + send volume + seats** — with free tiers capped at 300-500 subscribers / 1000-3000 sends a month, and the first paid tier jumping to $15-50/mo. On top of that, **your entire subscriber list, send history and engagement data live in someone else's database**.

Moving the whole thing onto a $4-5/mo 1C1G VPS keeps — or upgrades — the features: per-subscriber-timezone sending, event-triggered automations, A/B subject-line testing, things SaaS only unlocks at mid-tier prices. That's what **Listmonk** is for.

**What is Listmonk**: an MIT-licensed open-source email marketing platform written in Go. **One ~15MB static binary** serves the Web UI, REST API and CLI, and its only dependency is PostgreSQL. No Node full-stack, no queue middleware, no search service — one process plus one Postgres is the entire stack. Campaigns, subscribers, automations (event-triggered), RSS-fed campaigns, segments and tags, Mustache templates, DKIM signing, full API automation: the feature set competes directly with Mailchimp's Standard tier.

**Why a VPS**: the Go binary is memory-frugal — 20-50MB idle, plus 30-40MB for a small Postgres, so the whole stack idles at 60-100MB on 1C1G and leaves plenty of headroom. Measured on a single core: 10,000 campaigns go out in 3-8 minutes; a 100k-subscriber list is 1-2GB on disk in Postgres. The part that actually deserves attention isn't compute — it's the pre-checks below.

## 1. The math: calculate before you build

Scenario: a product newsletter, 2,000-10,000 subscribers, 1-2 campaigns a week, 10-40k sends/month.

| Option | Monthly cost | Notes |
|------|:---:|------|
| Mailchimp Free | $0 | 500 subscribers / 1,000 sends/mo, hard-capped |
| Mailchimp paid | ~$13-20 | from 500 contacts, ladders up by subscriber count |
| Brevo | $0 (300/day) → ~$22.50 | 300 sends/day free; paid starts ~6k sends/mo |
| Klaviyo | ~$25/mo | from 500 contacts, most feature-complete for e-commerce |
| **Listmonk @ 1C1G VPS** | **$0-5** | VPS $0 (already have one) - $4; SMTP relay $0-2 (SES PAYG ~$0.10/1k) |

You save **$180-600/yr** per project, and the subscriber list, send data and templates all live on your own hardware (GDPR pressure drops accordingly). Above 500k sends/mo the relay fee ($5-10) becomes the main variable — still far below SaaS tier jumps.

## 2. Pre-checks: outbound port 25 and IP reputation (before you buy)

The life-or-death of an email marketing stack is not the software, it's the **sending IP and domain reputation**. Two hard pre-checks, both $0, done before you commit:

1. **Outbound port 25**: most clouds block outbound 25 by default (DO and OVH flat-out, Hetzner/Netcup blocked but with a free allowlist request, Vultr/AWS account-policy-dependent). Test: `nc -vz mail.example.com 25` or `swaks --to test@example.com`. If it's blocked, you have two paths — ask for an unblock (free at some providers) or use an SMTP relay (SES / Mailgun / Brevo API, $0-2/mo, natively supported by Listmonk).
2. **PTR + SPF/DKIM/DMARC**: can you set a PTR record for your sending IP (`nslookup -query=ptr <ip>`)? Set up SPF (`v=spf1 mx -all` plus relay authorization), DKIM (Listmonk can sign for you), and DMARC (start `p=none`, read the reports, tighten later). No PTR and no relay = goodbye, inbox.

Use a separate sending domain from your main site domain (`mail.yourdomain.com`) — when reputation takes a hit, you don't burn your brand.

## 3. Deploy on 1C1G: one binary + one Postgres

Two containers in Docker Compose (`listmonk/docker-compose.yml`, hardened for 1C1G):

```yaml
services:
  listmonk:
    image: listmonk/listmonk:latest
    ports:
      - "127.0.0.1:10000:10000"   # loopback only; reach it via Cloudflare Tunnel/Tailscale
    environment:
      - POSTGRES_USER=listmonk
      - POSTGRES_PASSWORD=<***>
      - POSTGRES_HOST=postgres
      - POSTGRES_DATABASE=listmonk
      - LISTMONK_SMTP_HOST=smtp.mailgun.org
      - LISTMONK_SMTP_PORT=587
      - LISTMONK_SMTP_USERNAME=postmaster
      - LISTMONK_SMTP_PASSWORD=<***>
      - LISTMONK_SMTP_ENCRYPTION=starttls
      - LISTMONK_SMTP_FROM=hello@yourdomain.com
      # 50 concurrency is the warm-up discipline; raise to 100-200 once established
      - LISTMONK_SMTP_CONCURRENCY=50
      - LISTMONK_SMTP_SENDER=<***>
    volumes:
      - listmonk-data:/listmonk/uploads   # images / media assets
    deploy:
      resources:
        limits:
          memory: 150M

  postgres:
    image: postgres:16-alpine
    environment:
      - POSTGRES_USER=listmonk
      - POSTGRES_PASSWORD=<***>
      - POSTGRES_DATABASE=listmonk
    volumes:
      - pg-data:/var/lib/postgresql/data
    deploy:
      resources:
        limits:
          memory: 120M

volumes:
  listmonk-data:
  pg-data:
```

Companion steps:

1. **Exposure**: bind 10000 to loopback only; reach the UI via Cloudflare Tunnel or Tailscale. A leaked admin UI = a leaked list.
2. **Relay choice**: low volume (<20k/mo) → Brevo free tier (300/day) or SES PAYG (~$0.10/1k, new accounts need sender verification); high volume or reputation-sensitive → dedicated-IP relay.
3. **Disk**: give Postgres 10GB+ (100k subscribers + a year of send history); budget the uploads volume separately if you push heavy media.
4. **Timezones**: Listmonk sends at subscriber-local time by default — no manual UTC math.

Prefer bare metal: the official binary + distro Postgres + systemd (`MemoryMax=150M`) works fine and costs less.

## 4. Measured on a real 1C1G box

On a 1C1G VPS (2vCPU burst, 1GB, SSD), Postgres + Listmonk running steady:

| Metric | Measured | Notes |
|------|------|------|
| Combined idle memory | **60-100MB** | Listmonk 20-50MB + PG 30-40MB |
| 10,000-send campaign | **3-8 min** | concurrency 50, relay-bound |
| 100,000-send campaign | **30-90 min** | concurrency 100-200; relay limits set the ceiling |
| 100,000 subscribers | **1-2GB disk** | Postgres 16, normal vacuum |
| Automation events | **<50ms/event** | subscribe/unsubscribe/tag triggers |
| Web UI at 100k subs | **snappy** | search/segment queries <2s |

Conclusion: solo/small-team scale (<500k subscribers, <200k sends/mo) fits 1C1G entirely; beyond that, bump concurrency and the relay first — the box won't be the constraint.

## 5. Feature highlights: what SaaS charges for, free

- **Campaigns**: full/segmented sends, scheduling, A/B subject lines, Mustache templates with merge tags, HTML + plain-text variants.
- **Automations (event-triggered)**: subscribe → welcome sequence, tag → nurture flow, unsubscribe → win-back; multi-step delayed chains, replacing SaaS "Automations" paid modules.
- **RSS campaigns**: point one at your blog feed and new posts auto-push to subscribers — the highest-leverage use for content sites.
- **DKIM signing**: Listmonk holds the private key and signs; the public key goes in DNS TXT — use it when your relay won't sign.
- **CLI/API for everything**: the `listmonk` CLI launches campaigns, imports subscribers, pulls stats; the REST API lets CI ship newsletters as the last step of a content pipeline (`/api/v1/campaigns` + `/campaigns/{id}/launch`).

## 6. Five hard-won pitfalls

1. **Cold-start IP straight into the spam folder**: a fresh IP/domain blasting 10k in week one gets blacklisted by Gmail/Outlook. Discipline: week 1 = 100-200/day (your most-engaged subscribers), double weekly to target; keep concurrency at 50; let per-subscriber timezones spread the sends. Scale up only after Kitterman/Google Postmaster metrics cooperate.
2. **Hard bounces left alone burn the domain**: dead addresses in your list push bounce rate past 5% and Gmail starts punishing the whole domain. Listmonk writes bounces back to subscriber status, but **someone has to look**: a cron pulls `/api/v1/subscribers?status=bounced` daily, hard bounces twice → auto-unsubscribe; wire relay webhooks (SES Bounce notifications) into cleanup.
3. **Unverified lists degrade forever**: imported lists without double opt-in watch open rates slide from 30% to 10%. Run a verification flow on import (send a confirm mail, purge non-clicks after 14 days); prune hard bounces weekly.
4. **Postgres send-history bloat**: `campaign_messages` grows as campaigns × subscribers — 200 campaigns/year × 100k subs = 20M rows, and autovacuum can't keep up, bloating to slow queries. Rules: `autovacuum_vacuum_scale_factor=0.02` + monthly `VACUUM ANALYZE`; archive or drop send history older than a year. Backups: nightly `pg_dump` + uploads volume restic → R2 ($0 egress), 7 generations.
5. **Template placeholder errors → mass hard bounces**: a missing merge tag renders as a literal or empty, and the unsubscribe link 404s for that subset. Before any big send: Listmonk's built-in test-send to a 5-person test group, `listmonk send` dry-run, and default-everything in templates (`{{.name | default "there"}}`).

## 7. Monitoring & alerts

- **Health**: Uptime Kuma probe on the UI (via Tailscale to 127.0.0.1), every 5 minutes; `/api/v1/stats` returning 200 = alive.
- **Send quality**: daily cron pulls last-campaign bounce/unsubscribe rates from the API; >5% / >1% pushes a Telegram alert.
- **Disk**: Postgres data dir >80% alerts (pitfall 4 out of control).
- **Reputation**: Kitterman/Google Postmaster weekly, scripted or manual — more honest than any dashboard metric.

## 8. Hybrid mode (SaaS + self-hosted coexist)

You don't have to pick one:

- **High-volume low-cost content mail on self-hosted** (digests, RSS auto-push), **high-value acquisition/win-back campaigns on SaaS or a clean-IP relay** — two tracks, two lists, with unsubscribes synced one-way (SaaS → self-hosted).
- Or the reverse: start on the SaaS free tier under 1,000 subscribers, then import with one `listmonk` CLI command (CSV) and cut over in under 10 minutes, archiving the old campaigns.
- The list is the core asset: either way, **weekly full `pg_dump` + incremental restic to R2** — losing the list kills you faster than the platform does.

## 9. One-line summary

Email marketing isn't a "cloud feature" — it's a Web UI, a queue and a Postgres. Listmonk's single binary handles it on 1C1G for $0-5/mo, replacing Mailchimp/Brevo entry tiers and saving $180-600/yr, with the list and the data in your own hands. The cost is five pitfalls (cold-start reputation, bounce hygiene, list verification, PG bloat, template placeholders) — all "discipline + configure-once" work. Do the outbound-25 and PTR checks before you buy; everything after that is downhill.
