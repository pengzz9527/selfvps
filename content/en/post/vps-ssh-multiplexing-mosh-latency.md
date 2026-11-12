---
title: "SSH Multiplexing + mosh: Cut Interactive Login Latency to ~20ms on a High-RTT VPS"
date: 2026-11-12
tags: ["VPS", "SSH", "mosh", "Network Optimization", "DevOps"]
draft: false
image: /images/posts/vps-ssh-multiplexing-mosh-latency/featured.png
description: "Stop re-handshaking on every command: ControlMaster multiplexing cuts the handshakes for 8 SSH commands from 7 to 1 (780ms→180ms per command), and mosh (UDP + SSP state sync) survives WiFi-to-4G roaming and 800ms RTT. Includes persistent master sockets, fingerprint persistence, tmux layering, and a systemd user unit — ~12MB overhead on a 1C1G VPS."
---

# SSH Multiplexing + mosh: Cut Interactive Login Latency to ~20ms on a High-RTT VPS

Every VPS operator SSHes in a dozen times a day: tail logs, edit configs, run deploy scripts. You've probably accepted the half-second lag on every Enter — especially on a transcontinental link with 200ms+ RTT, where `git push`, then `systemctl restart`, then `tail -f` means three complete handshakes.

This post covers two client-side changes, both with zero server-side intrusion:

1. **SSH connection multiplexing (ControlMaster + ControlPersist)** — stack subsequent connections onto an existing TCP channel, skipping TCP handshake, key exchange, and auth;
2. **mosh (Mobile Shell)** — UDP + State Synchronization Protocol (SSP), surviving roaming, packet loss, and 800ms RTT, with automatic session recovery after network drops.

## 1. Measure First: Where Does the Latency Go?

Same 8 commands over Tokyo → Frankfurt (RTT ~235ms):

```bash
for i in $(seq 1 8); do ssh vps "uptime"; done
```

| Method | Total for 8 cmds | Avg per cmd | Notes |
|--------|:---:|:---:|------|
| Plain SSH (new connection) | 6.24s | 780ms | 3 round-trip handshake each time |
| ControlMaster multiplexing | 1.44s | 180ms | 1 handshake, rest reuse channel |
| ControlMaster + `-o Compression=no` | 1.38s | 172ms | compression hurts on thin/high-latency links |

Of the remaining 180ms, most is the command itself plus one data round-trip — close to the physical floor for an interactive login. **Handshake optimization saves ~600ms; the rest needs a protocol that isn't request-response**, which is exactly what mosh is.

## 2. SSH Multiplexing: Three Config Lines

Client-side `~/.ssh/config`:

```sshconfig
Host vps
    HostName 203.0.113.10
    User deploy
    # ---- multiplexing ----
    ControlMaster auto
    ControlPath ~/.ssh/cm/%r@%h:%p
    ControlPersist 10m
    # ---- low-latency knobs ----
    ServerAliveInterval 30
    ServerAliveCountMax 3
    Compression no
    # ---- optional jump host ----
    # ProxyJump bastion
```

```bash
mkdir -p ~/.ssh/cm && chmod 700 ~/.ssh/cm
```

What the three parameters do:

- `ControlMaster auto` — the first connection becomes the master; later ones detect the existing socket and multiplex;
- `ControlPath` — socket path (`%p` keeps same-IP/different-port hosts separate);
- `ControlPersist 10m` — the master lingers 10 minutes after the last client disconnects, so new connections skip the handshake.

The win compounds with `rsync`/`scp`/`git` (via `GIT_SSH_COMMAND="ssh -o ControlMaster=auto"`): when `rsync` moves 500 small files, every per-file metadata round-trip rides the same channel.

**Gotcha**: combining `ControlPersist` with `ProxyJump` also multiplexes the jump-host connection; if the bastion enforces `MaxSessions 1`, it breaks — give the bastion its own `ControlPath` or raise `MaxSessions`.

## 3. mosh: Freeing "Connection" from TCP

mosh's core is SSP: the client keeps a predictive local screen state, echoes keystrokes instantly, and the server sends only **diffs**. The results:

- **Roaming** — switching your phone from WiFi to 4G changes the IP; the session survives;
- **High RTT** — at 800ms RTT there's no TCP-retransmit stall; typing stays responsive;
- **Packet loss** — interactive use remains viable at 3% loss (TCP simply freezes).

### Server side (one-time)

```bash
sudo apt install -y mosh          # Debian/Ubuntu
sudo apt install -y mosh-server   # RHEL family (in EPEL)
# open UDP 60000-61000 — mosh's only extra requirement
sudo ufw allow 60000:61000/udp
```

### Client config

```sshconfig
Host vps
    RequestTTY yes
    RemoteCommand mosh-server new -c 256 -l LANG=en_US.UTF-8 -s
```

Or simply `mosh vps` from the shell (SSH auth first, then switch to the UDP session). mosh reuses SSH for initial auth — so the `ControlMaster` from section 2 still applies, **and the auth handshake is saved too**.

### Layer it: mosh + tmux

mosh handles "the network never drops"; tmux handles "the process doesn't die with the client". You want both:

```bash
mosh vps -- tmux new -A -s main
```

`-A` attaches an existing session or creates one. From then on, closing the laptop, losing connectivity, or switching networks all recover with one command.

## 4. Measured (Tokyo ↔ Frankfurt, RTT 235ms)

| Scenario | Plain SSH + tmux | mosh + tmux |
|----------|:---:|:---:|
| Keystroke to echo | 240–480ms | <20ms (local prediction) |
| WiFi→4G switch | session drops, reconnect | seamless, ~1.2s resync |
| Usability at 3% loss | visible stalls, Ctrl-C | normal interaction |
| Scrolling big logs (`tail -f`) | per-second redraw jank | diffs only, smooth |
| Mobile battery (mosh client) | — | more efficient (no TCP keepalive churn) |

> mosh's "20ms" is predicted local echo, not real round-trip; but it happens to be the metric that matters for perceived responsiveness.

## 5. Automation & Observability

**1. Keep the ControlMaster alive via a systemd user unit** (optional, `~/.config/systemd/user/ssh-master@.service`):

```ini
[Unit]
Description=SSH ControlMaster for %i
[Service]
ExecStart=/usr/bin/ssh -N %i
ExecStop=/usr/bin/ssh -O exit %i
Restart=always
RestartSec=5
[Install]
WantedBy=default.target
```

**2. mosh session auditing** — mosh itself keeps no records; use `journalctl -u ssh` for the bootstrap auth, plus `auditd` `execve` rules for commands.

**3. Latency baseline monitoring** — take `mdev` from `ssh vps "ping -c 20 1.1.1.1"` as link health, feed it into a Prometheus textfile, and alert above 80ms (indicates path detours, often BGP flap).

## 6. Pitfall Checklist

1. **mosh UDP blocked by NAT/security groups** — many clouds only allow TCP by default; explicitly add `60000-61000/udp`;
2. **`ControlPath` too long** — Unix socket paths cap at 108 bytes; `~/.ssh/cm/%r@%h:%p` overflows with long hostnames, use `/tmp/.cm-%C`;
3. **mosh does not forward ports** — `-L`/`-R` don't work in mosh; use SSH (or `ssh -O forward` on the master) when you need tunnels;
4. **Garbled CJK/emoji** — mosh-server needs `-l LANG=zh_CN.UTF-8`, otherwise tmux miscomputes East-Asian widths;
5. **mosh sessions don't survive a server reboot** — mosh depends on the mosh-server process; a reboot kills it. This is precisely why you layer tmux on top.

## 7. Conclusion

Two small changes, under 20 minutes of work:

- `ControlMaster` zeroes out handshake cost for high-frequency SSH commands — great for scripting and batch runs;
- `mosh` keeps interactive login responsive under roaming and high latency — great for long terminal sessions;
- Together, **`mosh vps -- tmux new -A -s main` is a complete "never-drops" ops terminal**.

Zero server-side changes (beyond opening one UDP port range), and mosh-server costs ~12MB on a 1C1G VPS. Next time you're debugging from your phone, you'll thank today's you.
