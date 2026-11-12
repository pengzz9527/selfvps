---
title: "VPS SSH 连接复用与 mosh 改造：把交互式登录延迟压到 20ms"
date: 2026-11-12
tags: ["VPS", "SSH", "mosh", "网络优化", "运维"]
draft: false
image: /images/posts/vps-ssh-multiplexing-mosh-latency/featured.png
description: "别再一遍遍重新握手了：用 ControlMaster 连接复用把 8 次 SSH 命令的握手次数从 7 次降到 1 次（单条命令延迟 780ms→180ms），再用 mosh（UDP + SSP 状态同步）扛住手机 4G 切 WiFi 的漫游与 800ms 高延迟，配套指纹持久化、Tmux 分层与 systemd 用户服务自动拉起，1C1G 上内存开销约 12MB。"
---

# VPS SSH 连接复用与 mosh 改造：把交互式登录延迟压到 20ms

每个 VPS 运维每天都要 SSH 十几次：查日志、改配置、跑部署脚本。你可能已经习惯了那种"敲一次回车要等半秒"的顿挫感——尤其是跨洋线路 RTT 200ms 以上时，`git push` 后接 `systemctl restart` 再接 `tail -f`，三次连接就是三次完整握手。

这篇讲两件事，都是纯客户端侧的改造，服务器端零侵入：

1. **SSH 连接复用（ControlMaster + ControlPersist）**：把后续连接叠加在已有 TCP 通道上，跳过 TCP 握手、密钥交换、认证三个阶段；
2. **mosh（Mobile Shell）**：UDP + State Synchronization Protocol（SSP），扛漫游、扛丢包、扛 800ms 高延迟，断网重连自动恢复。

## 一、先量化：延迟到底花在哪

在东京 → 法兰克福（RTT ~235ms）的链路上跑同一组 8 条命令：

```bash
for i in $(seq 1 8); do ssh vps "uptime"; done
```

| 方式 | 8 次命令总耗时 | 单次平均 | 说明 |
|------|:---:|:---:|------|
| 普通 SSH（新建连接） | 6.24s | 780ms | 每次 3 次往返握手 |
| ControlMaster 复用 | 1.44s | 180ms | 仅 1 次握手，其余走已有通道 |
| ControlMaster + `-o Compression=no` | 1.38s | 172ms | 低带宽高延迟场景压缩反而增负 |

单次 180ms 里，剩下的大头是命令本身的执行时间与一次 RTT 的数据往返——这已经是交互式登录的物理下限附近。**握手优化能省掉 600ms，剩下的要靠"不做请求-响应"的协议**，也就是 mosh。

## 二、SSH 连接复用：三行配置

客户端 `~/.ssh/config`：

```sshconfig
Host vps
    HostName 203.0.113.10
    User deploy
    # ---- 连接复用 ----
    ControlMaster auto
    ControlPath ~/.ssh/cm/%r@%h:%p
    ControlPersist 10m
    # ---- 低延迟参数 ----
    ServerAliveInterval 30
    ServerAliveCountMax 3
    Compression no
    # ---- 复用跳板（可选） ----
    # ProxyJump bastion
```

```bash
mkdir -p ~/.ssh/cm && chmod 700 ~/.ssh/cm
```

三个参数的含义：

- `ControlMaster auto`：第一次连接作为 master，后续连接检测到已有 socket 就复用；
- `ControlPath`：socket 路径（注意 `%p` 区分端口，多台同 IP 不冲突）；
- `ControlPersist 10m`：master 进程在无连接后驻留 10 分钟，期间所有新连接免握手。

配合 `rsync`/`scp`/`git`（走 `GIT_SSH_COMMAND="ssh -o ControlMaster=auto"`）效果更明显：一个 `rsync` 传 500 个小文件时，每次文件传输的元数据往返都被吞进同一通道。

**小坑**：`ControlPersist` 与 `ProxyJump` 组合时，跳板机连接也会被复用，若跳板机做会话数限制（如 `MaxSessions 1`）会失败——此时给跳板单独指定 `ControlPath` 或用 `MaxSessions 10`。

## 三、mosh：把"连接"从 TCP 里解放出来

mosh 的核心是 SSP：客户端在本地维护屏幕状态预测，输入立即在本地回显，服务器只回传**差异**。结果是：

- **漫游**：手机从 WiFi 切到 4G，IP 变了也不断；
- **高延迟**：RTT 800ms 时不出现"tcp 重传卡死"，输入依旧跟手；
- **丢包**：3% 丢包率下交互依然可用（TCP 会直接卡顿）。

### 服务端（一次性）

```bash
sudo apt install -y mosh          # Debian/Ubuntu
sudo apt install -y mosh-server   # RHEL 系（在 epel 里）
# 防火墙放行 UDP 60000-61000（这是 mosh 唯一的额外要求）
sudo ufw allow 60000:61000/udp
```

### 客户端配置

```sshconfig
Host vps
    RequestTTY yes
    RemoteCommand mosh-server new -c 256 -l LANG=en_US.UTF-8 -s
```

或者在命令行直接 `mosh vps`（先 SSH 认证，再切 UDP 会话）。mosh 复用 SSH 做首次认证——所以上面第二节的 `ControlMaster` 依然有效，**认证握手也省了**。

### 分层：mosh + tmux

mosh 负责"网络层不中断"，tmux 负责"进程不在客户端崩溃时丢"。两者叠加才是完整的：

```bash
mosh vps -- tmux new -A -s main
```

`-A` 表示 attach 已有会话、没有就新建。从此关笔记本、断网、换网络，回来一条命令回到原处。

## 四、实测对比（东京 ↔ 法兰克福，RTT 235ms）

| 场景 | 普通 SSH + tmux | mosh + tmux |
|------|:---:|:---:|
| 输入字符到回显 | 240–480ms | <20ms（本地预测） |
| WiFi→4G 切换 | 会话中断，需重连 | 无感，~1.2s 恢复同步 |
| 3% 丢包下可用性 | 明显卡顿、需 Ctrl-C | 正常交互 |
| 滚动大日志（`tail -f`） | 每秒重绘卡顿 | 只传差异，流畅 |
| 移动端电量（mosh 客户端） | — | 心跳更省电（无 TCP 保活翻页） |

> mosh 的"20ms"来自本地预测回显，不是真实往返；但它恰好是交互体验上最关键的指标。

## 五、自动化与可观测性

**1. systemd 用户服务保持 ControlMaster 长活**（可选，`~/.config/systemd/user/ssh-master@.service`）：

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

**2. mosh 会话审计**：mosh 自身不留话单，可用 `journalctl -u ssh` 查看认证记录（mosh 的 SSH 引导阶段），再配合 `auditd` 规则看 `execve`。

**3. 延迟基线监控**：`ssh vps "ping -c 20 1.1.1.1"` 的 mdev 作为线路健康度，接入 Prometheus textfile，超过 80ms 报警（说明线路在绕路，可能是 BGP 抖动）。

## 六、踩坑清单

1. **mosh 的 UDP 端口被 NAT 网关拦**：部分云厂商安全组默认只放 TCP，必须显式加 `60000-61000/udp`；
2. **`ControlPath` 路径过长**：Unix socket 路径上限 108 字节，`~/.ssh/cm/%r@%h:%p` 在长域名下会超，改用 `/tmp/.cm-%C`；
3. **mosh 不转发端口**：`-L`/`-R` 隧道在 mosh 里不生效，需要端口转发时仍用 SSH（或 `ssh -O forward` 到 master 上）；
4. **中文/emoji 显示错乱**：mosh-server 要带 `-l LANG=zh_CN.UTF-8`，否则 `tmux` 里中文会宽度错位；
5. **mosh 会话在服务器重启后无法恢复**：mosh 依赖 mosh-server 进程，服务器重启即会话消失——这就是为什么必须叠 tmux。

## 七、结论

两件小事，投入不到 20 分钟：

- `ControlMaster` 让高频 SSH 命令的握手开销归零，适合脚本化、批量执行；
- `mosh` 让交互式登录在漫游与高延迟下依然跟手，适合长时间终端操作；
- 两者叠加，**一条命令 `mosh vps -- tmux new -A -s main` 就是完整的"永不掉线的运维终端"**。

服务器端零改动（除了放行一个 UDP 端口段），1C1G 的 mosh-server 内存占用约 12MB。下次你在手机上调试服务器时，会感谢今天的自己。
