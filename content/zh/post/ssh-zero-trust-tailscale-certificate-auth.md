---
title: "SSH 零信任架构：Tailscale + SSH 证书认证实现无密码安全访问"
description: "结合 Tailscale 内网穿透与 OpenSSH 证书颁发机构，构建零信任 SSH 访问体系，告别 SSH Key 管理噩梦，实现设备身份验证、自动过期和设备吊销的完整安全链路"
date: 2026-06-23T10:00:00+08:00
lastmod: 2026-06-23T10:00:00+08:00
slug: "ssh-zero-trust-tailscale-certificate-auth"
image: /images/posts/ssh-zero-trust-tailscale-certificate-auth/featured.png
tags: ["SSH安全", "零信任", "Tailscale", "证书认证", "OpenSSH", "VPS安全", "内网穿透"]
categories: ["网络安全"]
aliases: [/zh/post/ssh-zero-trust-tailscale-certificate-auth/]
draft: false
---

## 引言

你的 VPS 暴露在公网，SSH 端口 22 每天被暴力破解数百次。你加了防火墙规则、改了端口、配了 fail2ban，但每次新设备要连上去，又要折腾 SSH Key 的复制粘贴——`scp id_rsa`、`ssh-copy-id`、`chmod 600`……管理越来越混乱。

**有没有一种方式，让 SSH 访问像访问内网服务一样简单，同时具备企业级的身份验证和设备管理能力？**

本文将介绍如何结合 **Tailscale 的零信任网络** 与 **OpenSSH 证书颁发机构（CA）**，构建一套完整的零信任 SSH 访问体系。核心思路是：Tailscale 负责网络层隔离（只有授权设备能到达），SSH 证书负责应用层身份验证（只有授权用户能在授权时间内操作）。

---

## 架构总览

```
┌─────────────────────────────────────────────────────┐
│                   Tailscale MagicDNS                 │
│                                                      │
│  ┌──────────┐    WireGuard     ┌──────────────────┐  │
│  │  Laptop   │◄──────────────►│  VPS (SSH Server) │  │
│  │ (User A)  │   加密隧道       │  Port 8022       │  │
│  └──────────┘                  │                  │  │
│                                │  sshd -CA verify  │  │
│  ┌──────────┐                  │  Cert + Tailnet   │  │
│  │ Phone     │◄──────────────►│  Auth Policy      │  │
│  │ (User B)  │   WireGuard     │                  │  │
│  └──────────┘                  └──────────────────┘  │
│                                                      │
│  ┌──────────┐         无公网暴露                      │
│  │ Desktop  │         端口不对外                      │
│  │ (User C) │         证书自动过期                    │
│  └──────────┘         设备可吊销                     │
└─────────────────────────────────────────────────────┘
```

这套架构的三大优势：

| 层级 | 传统方案 | 零信任方案 |
|------|---------|-----------|
| **网络可达性** | 公网暴露，端口扫描可见 | Tailscale 内网，仅授权设备可达 |
| **身份验证** | SSH Key 静态管理，永不过期 | SSH 证书 + 有效期 + 用户身份绑定 |
| **设备管理** | 手动管理 authorized_keys | Tailscale ACL + SSH CA 证书吊销 |

---

## 第一步：部署 Tailscale 作为网络层零信任

### 1.1 在 VPS 上安装 Tailscale

```bash
# Ubuntu/Debian
curl -fsSL https://tailscale.com/install.sh | sh

# 启动并登录（使用 Google/GitHub/微软账号）
sudo tailscale up --hostname=selfvps-server

# 查看 Tailnet 地址
tailscale status
```

安装完成后，你的 VPS 会获得一个 `100.x.y.z` 的 Tailnet IP 和一个 MagicDNS 域名，例如 `selfvps-server.tailcast-xxx.tailnet-yyy.ts.net`。

### 1.2 修改 SSH 监听端口

为了避免与系统 SSH 冲突，我们将 Tailscale 上的 SSH 监听在非标准端口：

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

> **提示：** 如果你不想创建额外服务，也可以直接在 `/etc/ssh/sshd_config` 中添加 `ListenAddress 100.x.y.z` 和 `Port 8022`，然后重启 `sshd`。

### 1.3 配置 Tailscale ACL（可选但推荐）

在 Tailscale 控制台的 Access Controls 中，你可以精细控制哪些设备可以访问哪些资源：

```json
{
  "players": {
    "user-a@example.com": ["selfvps-server"],
    "user-b@example.com": ["selfvps-server"]
  },
  "hosts": {
    "selfvps-server": {
      "interfaces": ["100.x.y.z"]
    }
  },
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

这确保了即使 Tailscale 网络中有其他设备，也只有明确授权的用户可以 SSH 到你的 VPS。

---

## 第二步：搭建 SSH 证书颁发机构（CA）

SSH 证书的核心思想是：用一个主密钥（CA 密钥）签发短期有效的用户证书，替代传统的 SSH Key 认证。

### 2.1 生成 CA 密钥对

```bash
# 在 VPS 上生成主机证书 CA
sudo ssh-keygen -t ed25519 -f /etc/ssh/ca_host_key -N "" -C "SelfVPS Host CA"

# 生成用户证书 CA
sudo ssh-keygen -t ed25519 -f /etc/ssh/ca_user_key -N "" -C "SelfVPS User CA"
```

这里生成了两个 CA：
- **主机 CA (`ca_host_key`)**：用于签发服务器证书，客户端用它验证"我连的是不是真的 VPS"
- **用户 CA (`ca_user_key`)**：用于签发用户证书，服务器用它验证"这个人有没有权限登录"

### 2.2 配置 SSH 服务器启用证书验证

编辑 `/etc/ssh/sshd_config`：

```bash
# 监听 Tailscale 地址和非标准端口
Port 8022
ListenAddress 100.x.y.z

# 禁用密码登录（只允许证书）
PasswordAuthentication no
PermitRootLogin prohibit-password

# 指定 CA 公钥位置
HostCertificate /etc/ssh/host-cert.pub
HostKey /etc/ssh/ssh_host_ed25519_key

# 启用证书验证
TrustedUserCAKeys /etc/ssh/ca_user_key.pub
AuthorizedPrincipalsFile /etc/ssh/user_principals/%u

# 禁用传统公钥认证（可选，完全依赖证书）
# PubkeyAuthentication no
```

> **注意：** `AuthorizedPrincipalsFile` 定义了哪些用户 principal 可以登录到哪些系统账户。这是 SSH 证书体系中最灵活的部分。

### 2.3 配置用户 Principal 映射

创建 `/etc/ssh/user_principals/` 目录和映射文件：

```bash
sudo mkdir -p /etc/ssh/user_principals

# 允许 user-a 以 root 和 ubuntu 身份登录
echo "root" | sudo tee /etc/ssh/user_principals/root
echo "user-a@example.com" | sudo tee -a /etc/ssh/user_principals/root

# 允许 user-b 以 ubuntu 身份登录
echo "ubuntu" | sudo tee /etc/ssh/user_principals/ubuntu
echo "user-b@example.com" | sudo tee -a /etc/ssh/user_principals/ubuntu
```

这样，即使用户证书中的 principal 是邮箱地址，也能正确映射到系统账户。

### 2.4 重新加载 SSH 配置

```bash
sudo systemctl restart sshd-tailscale
# 或者
sudo systemctl reload sshd
```

---

## 第三步：签发用户证书

现在客户端需要获取由你的 SSH CA 签发的证书才能登录。

### 3.1 在客户端生成 SSH Key

```bash
# 在你的笔记本电脑上
ssh-keygen -t ed25519 -f ~/.ssh/id_selfvps -C "user-a@laptop"
```

### 3.2 将公钥发送到服务器请求签发

```bash
# 通过 Tailscale 连接（此时仍可用传统 key 认证一次）
scp ~/.ssh/id_selfvps.pub user-a@100.x.y.z:/tmp/user-a-cert.pub
```

### 3.3 在服务器上签发证书

```bash
# 在 VPS 上执行
sudo ssh-keygen -s /etc/ssh/ca_user_key \
  -I "user-a-laptop" \
  -n "user-a@example.com" \
  -V "+52w" \
  /tmp/user-a-cert.pub

# 将签发的证书复制回客户端
scp user-a@example.com-cert.pub user-a@100.x.y.z:/tmp/

# 在客户端上将证书放到正确位置
cp /tmp/user-a@example.com-cert.pub ~/.ssh/id_selfvps-cert.pub
```

关键字段说明：

| 参数 | 含义 |
|------|------|
| `-s` | 指定签发用的 CA 私钥 |
| `-I` | 证书的身份标识（identity） |
| `-n` | 证书的 principals（允许登录的用户名列表） |
| `-V` | 证书的有效期，`+52w` 表示 52 周 |

### 3.4 配置客户端自动使用证书

编辑 `~/.ssh/config`：

```
Host selfvps-server
    HostName 100.x.y.z
    Port 8022
    User user-a
    IdentityFile ~/.ssh/id_selfvps
    CertificateFile ~/.ssh/id_selfvps-cert.pub
    IdentitiesOnly yes
```

之后只需 `ssh selfvps-server` 即可连接。

---

## 第四步：自动化证书生命周期管理

手动签发证书不方便，我们来自动化它。

### 4.1 证书签发脚本

```bash
#!/bin/bash
# sign-user-cert.sh - 自动化签发 SSH 用户证书
# 用法: ./sign-user-cert.sh <用户名> <principal> <有效期>

USERNAME="${1:?Usage: $0 <username> <principal> <validity>}"
PRINCIPAL="${2:-${USERNAME}}"
VALIDITY="${3:+52w}"

PUBKEY_FILE="/tmp/${USERNAME}-cert.pub"

# 检查公钥是否存在
if [[ ! -f "$PUBKEY_FILE" ]]; then
    echo "错误: 找不到公钥文件 $PUBKEY_FILE"
    exit 1
fi

# 签发证书
ssh-keygen -s /etc/ssh/ca_user_key \
    -I "${USERNAME}-$(date +%Y%m%d)" \
    -n "${PRINCIPAL}" \
    -V "${VALIDITY}" \
    "$PUBKEY_FILE"

echo "✅ 证书已签发: ${USERNAME}@$(date +%Y%m%d)-cert.pub"
echo "   Principals: ${PRINCIPAL}"
echo "   有效期: ${VALIDITY}"

# 清理临时文件
rm -f "$PUBKEY_FILE"
```

### 4.2 证书续期脚本

```bash
#!/bin/bash
# renew-user-cert.sh - 续期 SSH 用户证书
# 用法: ./renew-user-cert.sh <用户名>

USERNAME="$1"

# 检查当前证书是否即将过期
CERT_FILE="${HOME}/.ssh/id_${USERNAME}-cert.pub"

if [[ ! -f "$CERT_FILE" ]]; then
    echo "错误: 找不到证书文件 $CERT_FILE"
    exit 1
fi

# 提取公钥
ssh-keygen -y -f <(grep -v cert-type "$CERT_FILE" | head -1) > /tmp/renew-pub.tmp 2>/dev/null

# 重新签发
ssh-keygen -s /etc/ssh/ca_user_key \
    -I "${USERNAME}-renewed" \
    -n "${USERNAME}" \
    -V "+52w" \
    /tmp/renew-pub.tmp

echo "🔄 证书已续期"
```

### 4.3 客户端证书自动续期

在客户端机器上添加 cron 任务，定期检查证书有效期：

```bash
# crontab -e
0 9 * * 1 /opt/scripts/check-ssh-cert-renew.sh user-a 2>&1 | logger -t ssh-cert
```

`check-ssh-cert-renew.sh` 示例：

```bash
#!/bin/bash
# 检查 SSH 证书是否在 7 天内过期，如果是则自动续期
USERNAME="$1"
CERT_FILE="${HOME}/.ssh/id_${USERNAME}-cert.pub"
DAYS_THRESHOLD=7

if [[ ! -f "$CERT_FILE" ]]; then
    exit 0
fi

# 解析证书过期时间
EXPIRY=$(ssh-keygen -L -f "$CERT_FILE" 2>/dev/null | grep "Valid:" | awk '{print $2}')
if [[ -z "$EXPIRY" ]]; then
    exit 0
fi

# 计算剩余天数
EXPIRY_EPOCH=$(date -d "$EXPIRY" +%s 2>/dev/null)
NOW_EPOCH=$(date +%s)
DAYS_LEFT=$(( (EXPIRY_EPOCH - NOW_EPOCH) / 86400 ))

if [[ $DAYS_LEFT -lt $DAYS_THRESHOLD ]]; then
    echo "⚠️  证书将在 ${DAYS_LEFT} 天后过期，正在续期..."
    scp ~/.ssh/id_${USERNAME}.pub "${USERNAME}@100.x.y.z:/tmp/${USERNAME}-cert.pub"
    ssh "${USERNAME}@100.x.y.z" "sudo /opt/scripts/sign-user-cert.sh ${USERNAME} ${USERNAME} +52w"
    scp "${USERNAME}@100.x.y.z:/tmp/${USERNAME}@$(date +%Y%m%d)-cert.pub" ~/.ssh/id_${USERNAME}-cert.pub
    echo "✅ 证书已续期"
else
    echo "✅ 证书有效，剩余 ${DAYS_LEFT} 天"
fi
```

---

## 第五步：吊销证书和设备

零信任的核心能力之一是快速响应——当某台设备丢失或某个员工离职时，能够立即撤销其访问权限。

### 5.1 吊销用户证书

SSH 证书本身不支持在线吊销列表，但可以通过以下策略实现等效效果：

**策略一：缩短证书有效期 + 定期轮换**

将证书有效期设为较短时间（如 30 天），强制用户定期续期。如果某人离职，不再为其签发新证书，旧证书到期后自动失效。

**策略二：修改 AuthorizedPrincipalsFile**

如果需要在证书有效期内立即吊销：

```bash
# 从 principal 映射文件中移除该用户
sed -i '/^user-a@example.com$/d' /etc/ssh/user_principals/root
sed -i '/^user-a@example.com$/d' /etc/ssh/user_principals/ubuntu

# 重载 SSH
sudo systemctl reload sshd
```

这样即使证书仍然有效，也会因为 principal 不匹配而被拒绝。

**策略三：撤销 CA 密钥（极端情况）**

如果怀疑 CA 密钥泄露，可以生成新的 CA 密钥对，重新为所有合法用户签发证书：

```bash
# 备份旧 CA
sudo mv /etc/ssh/ca_user_key /etc/ssh/ca_user_key.bak
sudo mv /etc/ssh/ca_user_key.pub /etc/ssh/ca_user_key.pub.bak

# 生成新 CA
sudo ssh-keygen -t ed25519 -f /etc/ssh/ca_user_key -N "" -C "SelfVPS User CA (revoked)"

# 更新 sshd_config 中的 TrustedUserCAKeys 路径（如果改变了文件名）
sudo systemctl restart sshd

# 为所有合法用户重新签发证书
for user in user-a user-b user-c; do
    scp "${user}@client-machine:~/.ssh/id_${user}.pub" "/tmp/${user}-new.pub"
    sudo ssh-keygen -s /etc/ssh/ca_user_key -I "${user}-new" -n "${user}" -V "+52w" "/tmp/${user}-new.pub"
    scp "/tmp/${user}-new-cert.pub" "${user}@client-machine:~/.ssh/"
done
```

### 5.2 Tailscale 设备吊销

对于设备级别的吊销，Tailscale 提供了原生支持：

```bash
# 在 Tailscale 控制台中找到设备，点击 "Reauth" 或 "Remove"
# 或通过 API：
curl -X POST "https://api.tailscale.com/api/v2/device/${device-id}/deauth" \
  -H "Authorization: Bearer ${TAILSCALE_API_KEY}"
```

设备被吊销后，其 Tailnet 身份立即失效，无法再建立 WireGuard 隧道，自然也无法访问 SSH。

---

## 完整部署清单

以下是从零开始部署的完整步骤总结：

```bash
# ===== 服务器端 =====

# 1. 安装 Tailscale
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up --hostname=selfvps-server

# 2. 配置 SSH 监听 Tailscale 地址
echo "Port 8022" >> /etc/ssh/sshd_config
echo "ListenAddress 100.x.y.z" >> /etc/ssh/sshd_config
echo "PasswordAuthentication no" >> /etc/ssh/sshd_config
echo "TrustedUserCAKeys /etc/ssh/ca_user_key.pub" >> /etc/ssh/sshd_config
echo "AuthorizedPrincipalsFile /etc/ssh/user_principals/%u" >> /etc/ssh/sshd_config

# 3. 生成 CA 密钥
sudo ssh-keygen -t ed25519 -f /etc/ssh/ca_user_key -N "" -C "SelfVPS User CA"

# 4. 配置用户 Principal 映射
sudo mkdir -p /etc/ssh/user_principals
echo "root" > /etc/ssh/user_principals/root
echo "user-a@example.com" >> /etc/ssh/user_principals/root

# 5. 重启 SSH
sudo systemctl restart sshd

# ===== 客户端 =====

# 6. 安装 Tailscale 并加入 Tailnet
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up

# 7. 生成 SSH Key
ssh-keygen -t ed25519 -f ~/.ssh/id_selfvps -C "user@laptop"

# 8. 发送公钥到服务器请求签发
scp ~/.ssh/id_selfvps.pub user@100.x.y.z:/tmp/user-cert.pub

# 9. 在服务器上签发（步骤略，见上文）

# 10. 下载证书并配置 SSH
# 将 -cert.pub 复制到 ~/.ssh/ 并重命名为 id_selfvps-cert.pub
# 配置 ~/.ssh/config 如上
```

---

## 安全最佳实践

### 防御纵深策略

| 措施 | 作用 | 实施难度 |
|------|------|---------|
| **Tailscale 网络隔离** | SSH 端口不对公网开放，消除暴力破解 | ⭐ |
| **SSH 证书认证** | 替代静态 Key，支持有效期和 principal | ⭐⭐ |
| **禁用密码登录** | 防止弱口令攻击 | ⭐ |
| **Fail2ban** | 即使在内网也提供额外的失败尝试防护 | ⭐ |
| **证书短期有效** | 限制泄露窗口期 | ⭐⭐ |
| **定期审计证书** | 及时发现未续期的废弃证书 | ⭐⭐⭐ |

### 关键建议

1. **永远不要将 CA 私钥放在客户端**。CA 私钥只存在于受信任的服务器上。
2. **使用 ed25519 算法**。相比 RSA，ed25519 更快、更安全、密钥更短。
3. **设置合理的证书有效期**。开发环境可以用 52 周，生产环境建议 30-90 天。
4. **启用日志审计**。在 `sshd_config` 中添加 `LogLevel VERBOSE`，记录证书验证详情。
5. **备份 CA 私钥**。如果 CA 私钥丢失，所有现有证书都无法续期。将其加密存储到安全的备份位置。

---

## 常见问题

### Q: 传统 SSH Key 和证书认证有什么区别？

传统 SSH Key 认证中，用户的公钥直接放在服务器的 `authorized_keys` 文件中，没有有效期概念，吊销需要手动删除。SSH 证书将公钥封装在一个由 CA 签发的证书中，证书包含有效期、允许的 principal、扩展权限等信息，支持批量管理和自动过期。

### Q: Tailscale 免费计划够用吗？

对于个人或小团队（≤100 台设备），Tailscale 免费版完全够用。它提供了完整的 WireGuard 加密隧道、MagicDNS、SNEK 协议和基本的 ACL 控制。超过 100 台设备才需要付费计划。

### Q: 可以同时使用证书和传统 Key 认证吗？

可以。在 `sshd_config` 中，默认行为是先检查证书，再检查传统公钥。如果你想强制只使用证书，添加 `PubkeyAuthentication no`（但这会影响基于 Key 的其他服务如 `scp`，需谨慎）。

### Q: Windows 客户端怎么办？

Windows 用户可以通过 WSL2 或 Git Bash 使用 OpenSSH 客户端。SSH 证书的工作方式与 Linux/macOS 完全一致。Tailscale 也有官方 Windows 客户端。

---

## 总结

通过结合 Tailscale 和 OpenSSH 证书认证，你构建了一个真正的零信任 SSH 访问体系：

- **网络层**：Tailscale 确保只有授权设备能到达 SSH 服务，公网端口完全关闭
- **身份层**：SSH 证书将用户身份、权限和有效期绑定在一起，替代了混乱的 Key 管理
- **设备层**：Tailscale ACL 和证书吊销机制确保失去授权的设备/用户能立即被隔离

这套方案的运维成本极低——不需要额外的证书服务器（如 HashiCorp Vault 或 OpenSSL PKI），所有组件都是开源且内置的。对于个人开发者、小团队和自由职业者来说，这是一套真正实用的零信任安全实践。

现在，关掉你的公网 SSH 端口，拥抱零信任吧。
