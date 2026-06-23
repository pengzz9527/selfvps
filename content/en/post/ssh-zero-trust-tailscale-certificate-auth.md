---
title: "SSH Zero-Trust Architecture: Tailscale + SSH Certificate Authentication for Passwordless Secure Access"
description: "Combine Tailscale's private networking with OpenSSH Certificate Authority to build a zero-trust SSH access system,告别 SSH key management chaos with device identity verification, automatic expiration, and revocation"
date: 2026-06-23T10:00:00+08:00
lastmod: 2026-06-23T10:00:00+08:00
slug: "ssh-zero-trust-tailscale-certificate-auth"
image: /images/posts/ssh-zero-trust-tailscale-certificate-auth/featured.png
tags: ["SSH Security", "Zero Trust", "Tailscale", "Certificate Auth", "OpenSSH", "VPS Security", "Private Networking"]
categories: ["Network Security"]
aliases: [/en/post/ssh-zero-trust-tailscale-certificate-auth/]
draft: false
---

## Introduction

Your VPS is exposed to the public internet. SSH port 22 gets hammered with brute-force attempts hundreds of times a day. You've added firewall rules, changed ports, configured fail2ban—but every time a new device needs access, you're back to the same SSH key shuffle: `scp id_rsa`, `ssh-copy-id`, `chmod 600`... managing keys becomes a growing nightmare.

**What if SSH access could be as simple as connecting to an internal service, while maintaining enterprise-grade identity verification and device management?**

This guide shows how to combine **Tailscale's zero-trust networking** with **OpenSSH Certificate Authority (CA)** to build a complete zero-trust SSH access system. The core idea: Tailscale handles network-layer isolation (only authorized devices can reach your server), while SSH certificates handle application-layer identity verification (only authorized users can operate within authorized time windows).

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                   Tailscale MagicDNS                 │
│                                                      │
│  ┌──────────┐    WireGuard     ┌──────────────────┐  │
│  │  Laptop   │◄──────────────►│  VPS (SSH Server) │  │
│  │ (User A)  │   Encrypted     │  Port 8022       │  │
│  └──────────┘   Tunnel         │                  │  │
│                                │  sshd CA Verify  │  │
│  ┌──────────┐                  │  Cert + Tailnet  │  │
│  │ Phone     │◄──────────────►│  Auth Policy     │  │
│  │ (User B)  │   WireGuard     │                  │  │
│  └──────────┘                  └──────────────────┘  │
│                                                      │
│  ┌──────────┐         No public exposure             │
│  │ Desktop  │         Port not publicly reachable    │
│  │ (User C) │         Certificates auto-expire       │
│  └──────────┘         Devices can be revoked         │
└─────────────────────────────────────────────────────┘
```

Three key advantages over traditional setups:

| Layer | Traditional Approach | Zero-Trust Approach |
|-------|---------------------|---------------------|
| **Network Reachability** | Publicly exposed, visible to port scanners | Tailscale private network, only authorized devices |
| **Authentication** | Static SSH Keys, never expire | SSH Certificates + expiry + user identity binding |
| **Device Management** | Manual authorized_keys management | Tailscale ACL + SSH CA certificate revocation |

---

## Step 1: Deploy Tailscale as Network-Layer Zero Trust

### 1.1 Install Tailscale on Your VPS

```bash
# Ubuntu/Debian
curl -fsSL https://tailscale.com/install.sh | sh

# Start and authenticate (using Google/GitHub/Microsoft account)
sudo tailscale up --hostname=selfvps-server

# Check Tailnet status
tailscale status
```

After installation, your VPS gets a `100.x.y.z` Tailnet IP and a MagicDNS hostname like `selfvps-server.tailcast-xxx.tailnet-yyy.ts.net`.

### 1.2 Configure SSH to Listen on Tailscale Address

To avoid conflicts with your system SSH, we'll listen on a non-standard port via Tailscale:

```bash
sudo mkdir -p /etc/systemd/system/sshd-tailscale.service.d
cat <<'EOF' | sudo tee /etc/systemd/system/sshd-tailscale.service.d/override.conf
[Service]
ExecStart=
ExecStart=/usr/sbin/sshd -p 8022 -o ListenAddress=100.x.y.z
EOF

sudo systemctl daemon-reload
sudo systemctl restart sshd-tailscale
```

> **Tip:** Instead of creating a separate service, you can add `ListenAddress 100.x.y.z` and `Port 8022` directly to `/etc/ssh/sshd_config` and restart `sshd`.

### 1.3 Configure Tailscale ACLs (Recommended)

In the Tailscale console under Access Controls, you can finely control which devices access which resources:

```json
{
  "acl": {
    "autoApprovers": {
      "routes": {
        "100.x.y.z/32": true
      }
    },
    "rules": [
      { "action": "accept", "src": ["user-a@example.com"], "dst": ["selfvps-server:8022"] },
      { "action": "accept", "src": ["user-b@example.com"], "dst": ["selfvps-server:8022"] }
    ],
    "ssh": [
      { "action": "accept", "src": ["user-a@example.com"], "dst": ["selfvps-server"], "users": ["root", "ubuntu"] },
      { "action": "accept", "src": ["user-b@example.com"], "dst": ["selfvps-server"], "users": ["ubuntu"] }
    ]
  }
}
```

This ensures that even if other devices are on your Tailnet, only explicitly authorized users can SSH into your VPS.

---

## Step 2: Set Up SSH Certificate Authority

The core idea of SSH certificates: use a master key (the CA key) to issue short-lived user certificates, replacing traditional SSH key authentication.

### 2.1 Generate CA Key Pairs

```bash
# Generate host certificate CA on the VPS
sudo ssh-keygen -t ed25519 -f /etc/ssh/ca_host_key -N "" -C "SelfVPS Host CA"

# Generate user certificate CA
sudo ssh-keygen -t ed25519 -f /etc/ssh/ca_user_key -N "" -C "SelfVPS User CA"
```

Two CAs are created:
- **Host CA (`ca_host_key`)**: Used to sign server certificates. Clients use it to verify "am I connecting to the real VPS?"
- **User CA (`ca_user_key`)**: Used to sign user certificates. The server uses it to verify "does this person have permission to log in?"

### 2.2 Configure SSH Server for Certificate Verification

Edit `/etc/ssh/sshd_config`:

```bash
# Listen on Tailscale address and non-standard port
Port 8022
ListenAddress 100.x.y.z

# Disable password authentication (certificates only)
PasswordAuthentication no
PermitRootLogin prohibit-password

# Specify CA public key locations
HostCertificate /etc/ssh/host-cert.pub
HostKey /etc/ssh/ssh_host_ed25519_key

# Enable certificate verification
TrustedUserCAKeys /etc/ssh/ca_user_key.pub
AuthorizedPrincipalsFile /etc/ssh/user_principals/%u

# Disable traditional pubkey auth (optional, certificate-only mode)
# PubkeyAuthentication no
```

> **Note:** `AuthorizedPrincipalsFile` defines which user principals can log in as which system accounts. This is the most flexible part of the SSH certificate system.

### 2.3 Configure User Principal Mappings

Create the `/etc/ssh/user_principals/` directory and mapping files:

```bash
sudo mkdir -p /etc/ssh/user_principals

# Allow user-a to log in as root and ubuntu
echo "root" | sudo tee /etc/ssh/user_principals/root
echo "user-a@example.com" | sudo tee -a /etc/ssh/user_principals/root

# Allow user-b to log in as ubuntu
echo "ubuntu" | sudo tee /etc/ssh/user_principals/ubuntu
echo "user-b@example.com" | sudo tee -a /etc/ssh/user_principals/ubuntu
```

Even if the user certificate's principal is an email address, it correctly maps to the system account.

### 2.4 Reload SSH Configuration

```bash
sudo systemctl restart sshd-tailscale
# Or
sudo systemctl reload sshd
```

---

## Step 3: Issue User Certificates

Now clients need certificates signed by your SSH CA to log in.

### 3.1 Generate SSH Key on Client

```bash
# On your laptop
ssh-keygen -t ed25519 -f ~/.ssh/id_selfvps -C "user-a@laptop"
```

### 3.2 Send Public Key to Server for Signing

```bash
# Connect via Tailscale (still using traditional key for first connection)
scp ~/.ssh/id_selfvps.pub user-a@100.x.y.z:/tmp/user-a-cert.pub
```

### 3.3 Sign Certificate on Server

```bash
# On the VPS
sudo ssh-keygen -s /etc/ssh/ca_user_key \
  -I "user-a-laptop" \
  -n "user-a@example.com" \
  -V "+52w" \
  /tmp/user-a-cert.pub

# Copy the signed certificate back to the client
scp user-a@example.com-cert.pub user-a@100.x.y.z:/tmp/

# On the client, place the certificate in the correct location
cp /tmp/user-a@example.com-cert.pub ~/.ssh/id_selfvps-cert.pub
```

Key fields explained:

| Parameter | Meaning |
|-----------|---------|
| `-s` | CA private key used for signing |
| `-I` | Certificate identity label |
| `-n` | Certificate principals (allowed usernames for login) |
| `-V` | Certificate validity period, `+52w` means 52 weeks |

### 3.4 Configure Client to Use Certificates Automatically

Edit `~/.ssh/config`:

```
Host selfvps-server
    HostName 100.x.y.z
    Port 8022
    User user-a
    IdentityFile ~/.ssh/id_selfvps
    CertificateFile ~/.ssh/id_selfvps-cert.pub
    IdentitiesOnly yes
```

Then simply run `ssh selfvps-server` to connect.

---

## Step 4: Automate Certificate Lifecycle Management

Manual certificate signing is inconvenient. Let's automate it.

### 4.1 Certificate Signing Script

```bash
#!/bin/bash
# sign-user-cert.sh - Automated SSH user certificate signing
# Usage: ./sign-user-cert.sh <username> <principal> <validity>

USERNAME="${1:?Usage: $0 <username> <principal> <validity>}"
PRINCIPAL="${2:-${USERNAME}}"
VALIDITY="+52w"

PUBKEY_FILE="/tmp/${USERNAME}-cert.pub"

if [[ ! -f "$PUBKEY_FILE" ]]; then
    echo "Error: Public key file not found: $PUBKEY_FILE"
    exit 1
fi

ssh-keygen -s /etc/ssh/ca_user_key \
    -I "${USERNAME}-$(date +%Y%m%d)" \
    -n "${PRINCIPAL}" \
    -V "${VALIDITY}" \
    "$PUBKEY_FILE"

echo "✅ Certificate issued: ${USERNAME}@$(date +%Y%m%d)-cert.pub"
echo "   Principals: ${PRINCIPAL}"
echo "   Validity: ${VALIDITY}"

rm -f "$PUBKEY_FILE"
```

### 4.2 Certificate Renewal Script

```bash
#!/bin/bash
# renew-user-cert.sh - Renew SSH user certificates
# Usage: ./renew-user-cert.sh <username>

USERNAME="$1"
CERT_FILE="${HOME}/.ssh/id_${USERNAME}-cert.pub"

if [[ ! -f "$CERT_FILE" ]]; then
    echo "Error: Certificate file not found: $CERT_FILE"
    exit 1
fi

# Extract public key and re-sign
ssh-keygen -s /etc/ssh/ca_user_key \
    -I "${USERNAME}-renewed" \
    -n "${USERNAME}" \
    -V "+52w" \
    <(grep -v 'cert-authority\|ssh-ed25519' "$CERT_FILE" | head -1)

echo "🔄 Certificate renewed"
```

### 4.3 Automatic Client Certificate Renewal

Add a cron job on the client machine to periodically check certificate expiry:

```bash
# crontab -e
0 9 * * 1 /opt/scripts/check-ssh-cert-renew.sh user-a 2>&1 | logger -t ssh-cert
```

Example `check-ssh-cert-renew.sh`:

```bash
#!/bin/bash
# Check if SSH certificate expires within 7 days, auto-renew if needed
USERNAME="$1"
CERT_FILE="${HOME}/.ssh/id_${USERNAME}-cert.pub"
DAYS_THRESHOLD=7

if [[ ! -f "$CERT_FILE" ]]; then
    exit 0
fi

EXPIRY=$(ssh-keygen -L -f "$CERT_FILE" 2>/dev/null | grep "Valid:" | awk '{print $2}')
if [[ -z "$EXPIRY" ]]; then
    exit 0
fi

EXPIRY_EPOCH=$(date -d "$EXPIRY" +%s 2>/dev/null)
NOW_EPOCH=$(date +%s)
DAYS_LEFT=$(( (EXPIRY_EPOCH - NOW_EPOCH) / 86400 ))

if [[ $DAYS_LEFT -lt $DAYS_THRESHOLD ]]; then
    echo "⚠️  Certificate expires in ${DAYS_LEFT} days, renewing..."
    scp ~/.ssh/id_${USERNAME}.pub "${USERNAME}@100.x.y.z:/tmp/${USERNAME}-cert.pub"
    ssh "${USERNAME}@100.x.y.z" "sudo /opt/scripts/sign-user-cert.sh ${USERNAME} ${USERNAME} +52w"
    scp "${USERNAME}@100.x.y.z:/tmp/${USERNAME}@$(date +%Y%m%d)-cert.pub" ~/.ssh/id_${USERNAME}-cert.pub
    echo "✅ Certificate renewed"
else
    echo "✅ Certificate valid, ${DAYS_LEFT} days remaining"
fi
```

---

## Step 5: Revoke Certificates and Devices

A core capability of zero-trust is rapid response—when a device is lost or an employee leaves, you can immediately revoke access.

### 5.1 Revoking User Certificates

SSH certificates don't support online revocation lists natively, but you can achieve equivalent results:

**Strategy 1: Short Certificate Validity + Regular Rotation**

Set short certificate lifetimes (e.g., 30 days), forcing regular renewal. If someone leaves, stop issuing new certificates. Old ones expire automatically.

**Strategy 2: Modify AuthorizedPrincipalsFile**

For immediate revocation within the certificate lifetime:

```bash
# Remove the user from principal mapping files
sed -i '/^user-a@example.com$/d' /etc/ssh/user_principals/root
sed -i '/^user-a@example.com$/d' /etc/ssh/user_principals/ubuntu

# Reload SSH
sudo systemctl reload sshd
```

Even if the certificate is still valid, it's rejected due to principal mismatch.

**Strategy 3: Revoke the CA Key (Extreme Case)**

If you suspect the CA key is compromised, generate a new CA keypair and re-issue certificates for all legitimate users:

```bash
# Backup old CA
sudo mv /etc/ssh/ca_user_key /etc/ssh/ca_user_key.bak
sudo mv /etc/ssh/ca_user_key.pub /etc/ssh/ca_user_key.pub.bak

# Generate new CA
sudo ssh-keygen -t ed25519 -f /etc/ssh/ca_user_key -N "" -C "SelfVPS User CA (revoked)"

# Update TrustedUserCAKeys in sshd_config if filename changed
sudo systemctl restart sshd

# Re-issue certificates for all legitimate users
for user in user-a user-b user-c; do
    scp "${user}@client-machine:~/.ssh/id_${user}.pub" "/tmp/${user}-new.pub"
    sudo ssh-keygen -s /etc/ssh/ca_user_key -I "${user}-new" -n "${user}" -V "+52w" "/tmp/${user}-new.pub"
    scp "/tmp/${user}-new-cert.pub" "${user}@client-machine:~/.ssh/"
done
```

### 5.2 Tailscale Device Revocation

For device-level revocation, Tailscale provides native support:

```bash
# In the Tailscale console, find the device, click "Reauth" or "Remove"
# Or via API:
curl -X POST "https://api.tailscale.com/api/v2/device/${device-id}/deauth" \
  -H "Authorization: Bearer ${TAILSCALE_API_KEY}"
```

After deauthentication, the device's Tailnet identity is immediately invalidated. It can no longer establish WireGuard tunnels and thus cannot access SSH.

---

## Complete Deployment Checklist

Here's the complete step-by-step summary for a zero-to-one deployment:

```bash
# ===== SERVER SIDE =====

# 1. Install Tailscale
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up --hostname=selfvps-server

# 2. Configure SSH to listen on Tailscale address
echo "Port 8022" >> /etc/ssh/sshd_config
echo "ListenAddress 100.x.y.z" >> /etc/ssh/sshd_config
echo "PasswordAuthentication no" >> /etc/ssh/sshd_config
echo "TrustedUserCAKeys /etc/ssh/ca_user_key.pub" >> /etc/ssh/sshd_config
echo "AuthorizedPrincipalsFile /etc/ssh/user_principals/%u" >> /etc/ssh/sshd_config

# 3. Generate CA keys
sudo ssh-keygen -t ed25519 -f /etc/ssh/ca_user_key -N "" -C "SelfVPS User CA"

# 4. Configure user principal mappings
sudo mkdir -p /etc/ssh/user_principals
echo "root" > /etc/ssh/user_principals/root
echo "user-a@example.com" >> /etc/ssh/user_principals/root

# 5. Restart SSH
sudo systemctl restart sshd

# ===== CLIENT SIDE =====

# 6. Install Tailscale and join the Tailnet
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up

# 7. Generate SSH key
ssh-keygen -t ed25519 -f ~/.ssh/id_selfvps -C "user@laptop"

# 8. Send public key to server for signing
scp ~/.ssh/id_selfvps.pub user@100.x.y.z:/tmp/user-cert.pub

# 9. Sign on server (see steps above)

# 10. Download certificate and configure SSH
# Copy -cert.pub to ~/.ssh/ and rename to id_selfvps-cert.pub
# Configure ~/.ssh/config as shown above
```

---

## Security Best Practices

### Defense-in-Depth Strategy

| Measure | Purpose | Effort |
|---------|---------|--------|
| **Tailscale Network Isolation** | SSH port not public, eliminates brute force | ⭐ |
| **SSH Certificate Auth** | Replaces static keys with expiry and principals | ⭐⭐ |
| **Disable Password Login** | Prevents weak password attacks | ⭐ |
| **Fail2ban** | Additional failed-attempt protection even on private net | ⭐ |
| **Short Certificate Validity** | Limits damage window if compromised | ⭐⭐ |
| **Regular Certificate Audit** | Detect abandoned un-renewed certs | ⭐⭐⭐ |

### Key Recommendations

1. **Never store the CA private key on client machines.** The CA private key exists only on trusted servers.
2. **Use ed25519 algorithm.** Faster, more secure, and shorter keys than RSA.
3. **Set reasonable certificate validity.** 52 weeks for development, 30–90 days for production.
4. **Enable verbose logging.** Add `LogLevel VERBOSE` to `sshd_config` to record certificate verification details.
5. **Back up the CA private key.** If the CA key is lost, no existing certificates can be renewed. Store it encrypted in a secure backup location.

---

## Frequently Asked Questions

### Q: What's the difference between traditional SSH keys and certificate authentication?

Traditional SSH key authentication places user public keys directly in the server's `authorized_keys` file with no expiry concept. Revocation requires manual deletion. SSH certificates encapsulate the public key in a CA-signed certificate containing validity periods, allowed principals, extended permissions, and more—supporting batch management and automatic expiration.

### Q: Is Tailscale's free plan enough?

For individuals or small teams (≤100 devices), the free plan is fully sufficient. It provides complete WireGuard encryption, MagicDNS, the SNEK protocol, and basic ACL controls. Paid plans are only needed beyond 100 devices.

### Q: Can I use certificates and traditional keys simultaneously?

Yes. By default, `sshd` checks certificates first, then falls back to traditional keys. To enforce certificate-only mode, add `PubkeyAuthentication no` (but be cautious—this also affects services like `scp` that rely on key-based auth).

### Q: What about Windows clients?

Windows users can use WSL2 or Git Bash with OpenSSH client. SSH certificates work identically on Windows as on Linux/macOS. Tailscale also has an official Windows client.

---

## Summary

By combining Tailscale with OpenSSH certificate authentication, you've built a genuine zero-trust SSH access system:

- **Network layer**: Tailscale ensures only authorized devices reach the SSH service—the public port is completely closed.
- **Identity layer**: SSH certificates bind user identity, permissions, and validity periods together, replacing chaotic key management.
- **Device layer**: Tailscale ACLs and certificate revocation ensure compromised or unauthorized devices/users are immediately isolated.

The operational cost is minimal—no additional certificate servers (like HashiCorp Vault or OpenSSL PKI) required. All components are open-source and built-in. For individual developers, small teams, and freelancers, this is a genuinely practical zero-trust security implementation.

Now, close that public SSH port and embrace zero trust.
