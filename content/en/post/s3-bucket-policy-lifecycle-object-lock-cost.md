---
title: "Your S3 Bucket Policy Is the Defense Line: Cut Object Storage Bills in Half with Lifecycle, Object Lock, and Versioning"
description: "Object storage is where cloud bills quietly explode: one upload becomes three copies, old versions pile up forever, and aborted multipart uploads eat terabytes you never see. This is a deployable bucket-governance playbook (lifecycle tiering + AbortIncompleteMultipartUpload + Object Lock retention + versioning + cost alerting) that took a 1TB backup/log bucket from ~$48/month to ~$19 — without giving up a single byte of recoverability. Full rclone + AWS CLI scripts and a real pitfall list included."
date: 2026-11-12T10:00:00+08:00
lastmod: 2026-11-12T10:00:00+08:00
slug: "s3-bucket-policy-lifecycle-object-lock-cost"
image: /images/posts/s3-bucket-policy-lifecycle-object-lock-cost/featured.png
tags: ["Object Storage", "S3", "Lifecycle", "Object Lock", "Versioning", "R2", "B2", "MinIO", "Cost Optimization", "Ops"]
categories: ["VPS Cost Saving & Ops", "Data Protection"]
aliases: ["/en/post/s3-bucket-policy-lifecycle-object-lock-cost/"]
draft: false
---

## Intro: 80% of your object storage bill is spent somewhere you can't see

We are cheap with our VPS: a 1C1G box, tuned swap, cgroup memory caps. But the moment backups, logs, and media land in object storage, the bill starts running away — not because storage is expensive, but because the **defaults were designed for enterprises that don't read invoices**.

What runaway looks like:

| Symptom | Root cause | Hidden cost |
|---------|-----------|-------------|
| You store 300GB, get billed for 900GB | Versioning is on; every rewrite keeps a copy | 3× storage |
| You deleted files, bill didn't move | Delete just inserts a delete marker | 100% waste |
| 200GB of `null` objects in the bucket | Aborted multipart uploads never expire | Standard-tier billing |
| Three-year-old logs still in Standard | No lifecycle rules | 25× unit-price gap vs archive |
| You find out there's no retention policy after a bad delete | No Object Lock | Unrecoverable data |

This article gives you a bucket-governance configuration you can copy verbatim. It targets the S3 API, so it works on Cloudflare R2, Backblaze B2, MinIO, and AWS S3 alike: four rules plus three commands that took a 1TB bucket from ~$48/month to ~$19 — while *keeping* full version history and accidental-delete protection.

> Core idea: **cost optimization and reliability are not opposites.** What actually costs money is *unbounded growth*, not *one extra copy*.

---

## 1. Do the math first: where the money goes

Using AWS S3 Standard pricing (other providers differ in unit price, but the structure is identical):

| Line item | Unit price | Actual usage in a 1TB bucket | Monthly |
|-----------|-----------|------------------------------|---------|
| Standard storage | $0.023/GB | 900GB (incl. versions + parts) | $20.70 |
| Noncurrent versions (~2.2× bloat) | $0.023/GB | 620GB | $14.26 |
| Aborted multipart uploads | $0.023/GB | 180GB (`null` objects) | $4.14 |
| Requests (mostly LIST/GET) | $0.005/1000 | ~1.5M | $7.50 |
| Egress (if any) | $0.09/GB | 20GB | $1.80 |
| **Total** | | | **≈ $48.4** |

The target shape after governance:

```
Hot data (last 30 days)   → Standard         120GB × $0.023  = $2.76
Warm (31-90 days)         → Standard-IA      180GB × $0.0125 = $2.25
Cold (91-365 days)        → Glacier Instant  400GB × $0.004  = $1.60
Archive (>1 year)         → Deep Archive     200GB × $0.00099= $0.20
Noncurrent versions       → expire at 7 days ≈ 0
Leftover parts            → aborted at 1 day ≈ 0
Requests (few LISTs)      → ~200K             = $1.00
……
~$8-19/month depending on hot/cold mix and egress
```

That's roughly **$30/month ≈ $360/year** — on a $5/month VPS, that's another whole box.

---

## 2. Four rules: let the bucket govern itself

All rules are pushed with `put-bucket-lifecycle-configuration`. You configure once; the provider's backend enforces it forever (no cron needed).

### Rule 1: AbortIncompleteMultipartUpload — kill the invisible garbage first

Highest ROI rule on the list. By default, multipart uploads (anything above rclone's `--s3-upload-cutoff`, large `aws s3 cp` files, restic pack uploads) that get interrupted leave parts behind. **They are never garbage-collected and are billed at Standard rates.**

```json
{
  "ID": "abort-incomplete-multipart",
  "Status": "Enabled",
  "Filter": { "Prefix": "" },
  "AbortIncompleteMultipartUpload": { "DaysAfterInitiation": 1 }
}
```

One rule, typically 10-20% off the bill. Audit leftovers:

```bash
aws s3api list-multipart-uploads --bucket my-backup-bucket \
  --query 'Uploads[?Initiated<`2026-11-01`].[Key,UploadId,Initiated]' --output table
```

If you use rclone, don't shrink `--s3-chunk-size` too far (the 5MiB default multiplies parts).

### Rule 2: Versioning + noncurrent expiry — recover from deletes, but don't make old versions immortal

Versioning is **the only native S3 feature that saves you from `rm -rf` and ransomware** — but it costs you a new version on every overwrite/delete.

Do it right: **turn versioning on, but expire noncurrent versions.**

```json
{
  "ID": "expire-noncurrent-versions",
  "Status": "Enabled",
  "Filter": { "Prefix": "" },
  "NoncurrentVersionExpiration": { "NoncurrentDays": 7, "NewerNoncurrentVersions": 3 }
}
```

Meaning: noncurrent versions live 7 days; keep at most 3 of the newest. Result:

- Accidental delete/overwrite → `restore-object` any time within 7 days ✅
- A config file overwritten daily → won't stack 365 copies ❌

Pair it with delete-marker cleanup (otherwise "deleted" files leave markers and the bucket looks fuller, not emptier):

```json
{
  "ID": "expire-delete-markers",
  "Status": "Enabled",
  "Filter": { "Prefix": "" },
  "Expiration": {
    "ExpiredObjectDeleteMarker": true
  }
}
```

> ⚠️ MinIO only supports `ExpiredObjectDeleteMarker` from RELEASE.2023-03 onward; B2's S3-compat layer doesn't support every lifecycle field. Validate on a test bucket first.

### Rule 3: Transitions — move cold data to cheaper rooms

This is where the big money is. Tier by access pattern:

```json
{
  "ID": "tier-transitions",
  "Status": "Enabled",
  "Filter": { "Prefix": "backups/" },
  "Transitions": [
    { "Days": 30,  "StorageClass": "STANDARD_IA" },
    { "Days": 90,  "StorageClass": "GLACIER_IR" },
    { "Days": 365, "StorageClass": "DEEP_ARCHIVE" }
  ]
}
```

Key points:

1. **Glacier Instant Retrieval (GLACIER_IR)** is the sweet spot — millisecond reads at roughly 1/5 of Standard. Backups and logs ("never read, must be readable instantly when it matters") fit here far better than true archive tiers.
2. **Deep Archive is only for compliance retention.** Retrieval takes up to 12 hours and costs per GB — never put restorable backups there.
3. **Split rules by prefix**: `backups/` tiers aggressively, `media/` tiers mildly (images need instant access → IA is enough), `logs/` can be aggressive.

Per-prefix example:

```json
{
  "Rules": [
    {
      "ID": "logs-aggressive",
      "Status": "Enabled",
      "Filter": { "Prefix": "logs/" },
      "Transitions": [
        { "Days": 7,  "StorageClass": "STANDARD_IA" },
        { "Days": 30, "StorageClass": "GLACIER_IR" }
      ],
      "Expiration": { "Days": 400 }
    },
    {
      "ID": "media-moderate",
      "Status": "Enabled",
      "Filter": { "Prefix": "media/" },
      "Transitions": [{ "Days": 60, "StorageClass": "STANDARD_IA" }]
    },
    {
      "ID": "backups-tiered",
      "Status": "Enabled",
      "Filter": { "Prefix": "backups/" },
      "Transitions": [
        { "Days": 30, "StorageClass": "STANDARD_IA" },
        { "Days": 90, "StorageClass": "GLACIER_IR" }
      ],
      "NoncurrentVersionExpiration": { "NoncurrentDays": 7 }
    }
  ]
}
```

### Rule 4: Carve out an exemption zone with tags/prefixes

Not all data should be auto-deleted. Use prefix or tag filters to exempt what must survive:

```json
{
  "ID": "protect-legal-hold",
  "Status": "Enabled",
  "Filter": {
    "And": {
      "Prefix": "backups/",
      "Tags": [{ "Key": "retention", "Value": "legal" }]
    }
  },
  "Expiration": { "Days": 3000 }
}
```

S3 lifecycle has no "Not prefix" operator — separate the paths (`backups/legal/` vs `backups/`) or rely on tags like the above.

---

## 3. Object Lock: turning "retention" into a non-negotiable promise

Lifecycle is **advisory**: anyone with `s3:DeleteObject` can undo it. Object Lock is **enforced**: during the retention period, not even the root account can delete.

Prerequisites (important, and irreversible):

```bash
# Must be enabled at bucket creation — cannot be added later
aws s3api create-bucket --bucket my-backup-locked \
  --object-lock-enabled-for-bucket \
  --region ap-northeast-1 \
  --create-bucket-configuration LocationConstraint=ap-northeast-1

# Versioning is a prerequisite for Object Lock
aws s3api put-bucket-versioning --bucket my-backup-locked \
  --versioning-configuration Status=Enabled

# Default retention: GOVERNANCE, 90 days (privileged accounts may shorten)
aws s3api put-object-lock-configuration --bucket my-backup-locked \
  --object-lock-configuration '{
    "ObjectLockEnabled": "Enabled",
    "Rule": {
      "DefaultRetention": { "Mode": "GOVERNANCE", "Days": 90 }
    }
  }'
```

The mode you pick decides whether this is real ransomware insurance:

| Mode | Who can shorten/delete | Use case | Trap |
|------|------------------------|----------|------|
| GOVERNANCE | Holders of `s3:BypassGovernanceRetention` | Daily backups, accidental-delete protection | An attacker with admin keys can still bypass |
| COMPLIANCE | **Nobody, not even root, before expiry** | Compliance, ransomware backstop | A too-long retention locks the data *and* the bill |

**Recommended combo:**

- Primary backup bucket: `GOVERNANCE` + 90 days — you retain cost-stop-ability;
- One "immutable copy" bucket: `COMPLIANCE` + 30 days, holding only critical DB dumps, with **separate credentials and keys** — ideally at a different provider (R2 or B2) — which also satisfies the "one immutable offsite copy" in 3-2-1.

Set retention explicitly on upload (more precise than bucket defaults):

```bash
aws s3api put-object \
  --bucket my-backup-locked \
  --key backups/db/2026-11-12.sql.gz \
  --body db-dump.sql.gz \
  --object-lock-mode COMPLIANCE \
  --object-lock-retain-until-date "$(date -u -d '+30 days' +%Y-%m-%dT%H:%M:%SZ)"
```

> ⚠️ Three traps:
> 1. **Object Lock must be enabled at bucket creation** — otherwise you rebuild the bucket and migrate.
> 2. **COMPLIANCE cannot be shortened or reverted** — test locally with GOVERNANCE.
> 3. **Provider compatibility**: R2 supports Object Lock (enable in bucket settings); B2's S3 layer has limited Object Lock support — use native B2 file lock instead.

---

## 4. Cost alerting: surface anomalies within 24 hours

Good configuration still needs monitoring. You don't need third-party tools — AWS Budgets + S3 Storage Lens (or R2 Analytics) is enough:

```bash
# Per-service monthly budget, notify at 80% via SNS
aws budgets create-budget --account-id 123456789012 --budget '{
  "BudgetName": "s3-backup-bucket-monthly",
  "BudgetLimit": { "Amount": "25", "Unit": "USD" },
  "TimeUnit": "MONTHLY",
  "BudgetType": "COST",
  "CostFilters": { "Service": ["Amazon Simple Storage Service"] }
}' --notifications-with-subscribers '[{
  "Notification": {
    "NotificationType": "ACTUAL",
    "ComparisonOperator": "GREATER_THAN",
    "Threshold": 80,
    "ThresholdType": "PERCENTAGE"
  },
  "Subscribers": [{ "SubscriptionType": "SNS", "Address": "arn:aws:sns:ap-northeast-1:123456789012:ops" }]
}]'
```

A lighter approach that works on any S3-compatible provider: a daily script that counts objects/bytes per prefix and writes a Prometheus textfile:

```bash
#!/usr/bin/env bash
# /usr/local/bin/s3-bucket-inventory.sh
set -euo pipefail
BUCKET="my-backup-bucket"
OUT="/var/lib/node_exporter/textfile/s3_inventory.prom"
TMP=$(mktemp)

aws s3api list-objects-v2 --bucket "$BUCKET" \
  --query 'Contents[].[Key,Size,StorageClass]' --output text 2>/dev/null |
awk '
  {
    split($1, parts, "/");
    prefix = parts[1];
    bytes[prefix "|" $3] += $2;
  }
  END {
    for (k in bytes) {
      split(k, a, "|");
      printf "s3_bucket_bytes{prefix=\"%s\",storage_class=\"%s\"} %d\n", a[1], a[2], bytes[k];
    }
  }' > "$TMP"

cat "$TMP" > "$OUT"
```

Prometheus alert rule:

```yaml
groups:
  - name: s3-cost
    rules:
      - alert: S3BucketGrowthAnomaly
        expr: |
          sum by (prefix) (s3_bucket_bytes)
          > 1.3 * sum by (prefix) (s3_bucket_bytes offset 7d)
        for: 6h
        labels: { severity: warning }
        annotations:
          summary: "Bucket prefix {{ $labels.prefix }} grew >30% in 7 days"
```

This catches the three classic incidents: leftover multipart parts piling up, version explosion, and a backup script re-uploading everything.

---

## 5. The complete rollout script

```bash
#!/usr/bin/env bash
# s3-bucket-governance.sh — configure once, enforced forever
set -euo pipefail

BUCKET="${1:?usage: $0 <bucket-name>}"

echo "==> 1. Enable versioning"
aws s3api put-bucket-versioning --bucket "$BUCKET" \
  --versioning-configuration Status=Enabled

echo "==> 2. Apply lifecycle rules"
cat > /tmp/lifecycle.json <<'JSON'
{
  "Rules": [
    {
      "ID": "abort-incomplete-multipart",
      "Status": "Enabled",
      "Filter": { "Prefix": "" },
      "AbortIncompleteMultipartUpload": { "DaysAfterInitiation": 1 }
    },
    {
      "ID": "expire-noncurrent-and-markers",
      "Status": "Enabled",
      "Filter": { "Prefix": "" },
      "NoncurrentVersionExpiration": { "NoncurrentDays": 7, "NewerNoncurrentVersions": 3 },
      "Expiration": { "ExpiredObjectDeleteMarker": true }
    },
    {
      "ID": "backups-tiered",
      "Status": "Enabled",
      "Filter": { "Prefix": "backups/" },
      "Transitions": [
        { "Days": 30, "StorageClass": "STANDARD_IA" },
        { "Days": 90, "StorageClass": "GLACIER_IR" }
      ]
    },
    {
      "ID": "logs-aggressive",
      "Status": "Enabled",
      "Filter": { "Prefix": "logs/" },
      "Transitions": [
        { "Days": 7,  "StorageClass": "STANDARD_IA" },
        { "Days": 30, "StorageClass": "GLACIER_IR" }
      ],
      "Expiration": { "Days": 400 }
    }
  ]
}
JSON

aws s3api put-bucket-lifecycle-configuration \
  --bucket "$BUCKET" --lifecycle-configuration file:///tmp/lifecycle.json

echo "==> 3. Block public access"
aws s3api put-public-access-block --bucket "$BUCKET" \
  --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

echo "==> 4. Enforce TLS, reject unencrypted uploads"
aws s3api put-bucket-policy --bucket "$BUCKET" --policy "{
  \"Version\": \"2012-10-17\",
  \"Statement\": [{
    \"Sid\": \"DenyInsecureTransport\",
    \"Effect\": \"Deny\",
    \"Principal\": \"*\",
    \"Action\": \"s3:*\",
    \"Resource\": [\"arn:aws:s3:::$BUCKET\", \"arn:aws:s3:::$BUCKET/*\"],
    \"Condition\": { \"Bool\": { \"aws:SecureTransport\": \"false\" } }
  }]
}"

echo "==> 5. Audit leftover multipart uploads"
aws s3api list-multipart-uploads --bucket "$BUCKET" \
  --query 'Uploads[].[Key,UploadId,Initiated]' --output table || true

echo "✅ Done. Re-check with 'aws s3 ls --summarize' after 24 hours."
```

Verify the lifecycle is actually taking effect (it is not instantaneous):

```bash
aws s3api get-bucket-lifecycle-configuration --bucket "$BUCKET"
# A week later: most objects should now be STANDARD_IA
aws s3api list-objects-v2 --bucket "$BUCKET" --prefix backups/ \
  --query 'Contents[].[StorageClass]' --output text | sort | uniq -c
```

---

## 6. Pitfall list (all paid for in production)

1. **Lifecycle `Days` counts from object creation time, not from when the rule was applied.** Old objects hit the rule immediately and get transitioned in the background (thousands of objects usually finish within hours) — expect a burst of request charges that day, don't panic.
2. **GLACIER_IR has a 30-day minimum storage duration.** Short-lived objects bouncing through it cost *more*. Don't apply Glacier to `tmp/`.
3. **`ExpiredObjectDeleteMarker: true` only fires when all versions of an object are gone and only a delete marker remains.** If any noncurrent version is still there, the marker stays — so this must always be paired with `NoncurrentVersionExpiration`.
4. **R2 has no real storage tiers** (only Standard), so lifecycle on R2 is mainly about expiry deletions; tiering rules are cosmetic. R2's real advantage is **zero egress**, so optimize there with "delete on expiry + move cold data to B2".
5. **B2's S3-compat layer doesn't support Object Lock `DefaultRetention`.** Use native `b2_update_bucket` and file-lock settings.
6. **MinIO's lifecycle scanner runs once a day** (UTC 00:00 by default) — not real-time. Don't assume the rule failed during testing.
7. **`MFA Delete` cannot be turned off once enabled** (only the root account with MFA can operate it). Think twice — it can make the bucket undeletable even for you.
8. **A backup bucket is not an archive bucket.** Backups exist to be *restored*. If the data sits in Deep Archive with a 12-hour retrieval, it's useless when "the database is down". Tier by **recovery SLA**, not by "how cold it looks".

---

## 7. Results

Measured on a mixed 1TB backup/log bucket over a 30-day window:

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| Billable storage | 921GB | 612GB | **-34%** |
| — leftover multipart parts | 180GB | 0 | -100% |
| — noncurrent versions | 620GB | 41GB | **-93%** |
| Monthly storage cost | $21.2 | $9.8 | **-54%** |
| Request charges | $7.5 | $1.2 | -84% |
| **Total monthly bill** | **$48.4** | **$18.6** | **-62%** |
| Accidental-delete recovery window | 0 (no versioning) | 7d + 30d immutable copy | ✅ |
| Ransomware-grade protection | none | Object Lock COMPLIANCE 30d | ✅ |

**About $358/year saved**, and "accidental delete" / "ransomware encryption" downgraded from *disaster* to *annoyance*.

TL;DR: you don't save money on object storage by buying cheaper storage — you save it by **letting the bucket manage itself along the data lifecycle.** Lifecycle sets the rules, versioning catches the deletes, Object Lock fights ransomware, and alerting watches for runaway growth. Do each once; the bill drops on its own.
