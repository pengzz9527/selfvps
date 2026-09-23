---
title: "Terraform + VPS：基础设施即代码入门，一条命令重建整台服务器"
description: "用 Terraform 管理 VPS 基础设施，从服务器创建到 Nginx 配置、SSL 证书全自动部署。告别手动 SSH 操作，实现可重复、可版本控制的服务器配置。"
date: 2026-09-23T10:00:00+08:00
lastmod: 2026-09-23T10:00:00+08:00
slug: "terraform-vps-iac"
image: /images/posts/terraform-vps-iac/featured.png
tags: ["Terraform", "VPS运维", "基础设施即代码", "DevOps", "自动化", "Nginx", "LetsEncrypt", "云成本优化"]
categories: ["运维自动化", "DevOps"]
aliases: [/zh/post/terraform-vps-iac/]
---

## 为什么需要 Terraform 管理 VPS？

如果你曾经有过这样的经历：

> 新买一台 VPS，手动 SSH 进去，apt install 这一套、那一套，改 Nginx 配置、申请 SSL 证书、部署应用……过了几个月，换了新服务器，发现根本记不清之前装过什么、怎么配置的。

这就是**手动运维的困境**——每次都是从零开始，配置无法复制，故障恢复成本高。**基础设施即代码（IaC）** 正是为了解决这个问题而生。

**Terraform** 是目前最流行的 IaC 工具，它让你用声明式代码描述你想要的服务器状态，然后自动执行变更。更重要的是，**它能管理已有服务器**，不必非要从零创建云实例。

---

## Terraform 核心概念

在深入 VPS 之前，先理解 Terraform 的三个核心概念：

| 概念 | 说明 | 类比 |
|------|------|------|
| **Provider** | 插件，负责与 API 交互（如 DigitalOcean、AWS、Local） | 驱动程序 |
| **Resource** | 要创建或管理的资源（服务器、域名、SSL 证书） | 要买的建材 |
| **State** | 记录当前实际状态的数据库 | 施工蓝图 |

对于 VPS 场景，最实用的 Provider 是 `null`（本地操作）和 `proxmox`（Proxmox VE）或 `digitalocean`（云 VPS）。本文重点讲解 **本地 Terraform + Remote-exec** 方案，适用于任何 VPS。

---

## 环境准备

### 安装 Terraform

```bash
# Ubuntu/Debian
curl -fsSL https://apt.releases.hashicorp.com/gpg | sudo apt-key add -
sudo apt-add-repository "deb [arch=amd64] https://apt.releases.hashicorp.com $(lsb_release -cs) main"
sudo apt update && sudo apt install terraform -y

# 或通过 Homebrew（macOS）
brew install terraform

# 验证安装
terraform --version
# Terraform v1.7.x
```

### 创建项目目录

```bash
mkdir -p ~/terraform-vps && cd ~/terraform-vps
```

---

## 第一步：定义 Provider 和变量

创建一个 `main.tf` 文件：

```hcl
# provider 配置 —— 使用 local 执行远程命令
provider "null" {}

# 变量定义
variable "vps_host" {
  description = "VPS SSH 地址"
  type        = string
  default     = "your-vps-ip"
}

variable "vps_user" {
  description = "SSH 用户名"
  type        = string
  default     = "root"
}

variable "vps_key_file" {
  description = "SSH 私钥路径"
  type        = string
  default     = "~/.ssh/id_rsa"
}

variable "app_port" {
  description = "应用端口"
  type        = number
  default     = 8080
}
```

---

## 第二步：创建基础环境

用 `null_resource` + `provisioner "remote-exec"` 在已有 VPS 上执行命令：

```hcl
# 更新系统并安装基础工具
resource "null_resource" "base_setup" {
  triggers = {
    always_run = timestamp()
  }

  connection {
    type     = "ssh"
    user     = var.vps_user
    host     = var.vps_host
    private_key = file(var.vps_key_file)
  }

  provisioner "remote-exec" {
    inline = [
      "apt-get update && apt-get upgrade -y",
      "apt-get install -y curl wget git ca-certificates gnupg lsb-release",
      # 创建应用用户
      "useradd -m -s /bin/bash appuser",
      "mkdir -p /opt/app /var/log/app /etc/app",
    ]
  }
}
```

运行部署：

```bash
terraform init
terraform plan   # 预览变更
terraform apply  # 执行变更
```

---

## 第三步：配置 Nginx 反向代理

Terraform 可以直接管理 Nginx 配置：

```hcl
# Nginx 站点配置模板
locals {
  nginx_config = <<EOF
server {
    listen 80;
    server_name ${var.domain_name};

    location / {
        proxy_pass http://127.0.0.1:${var.app_port};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF
}

# 部署 Nginx 配置
resource "null_resource" "nginx_setup" {
  depends_on = [null_resource.base_setup]

  connection {
    type     = "ssh"
    user     = var.vps_user
    host     = var.vps_host
    private_key = file(var.vps_key_file)
  }

  provisioner "remote-exec" {
    inline = [
      "apt-get install -y nginx",
      "echo '${local.nginx_config}' > /etc/nginx/sites-available/default",
      "nginx -t && systemctl reload nginx",
    ]
  }
}
```

---

## 第四步：自动申请 SSL 证书

结合 Certbot 实现 HTTPS 自动续期：

```hcl
# 输出变量
output "vps_ip" {
  value       = var.vps_host
  description = "VPS IP 地址"
}

output "deploy_time" {
  value       = timestamp()
  description = "部署时间"
}
```

在 `variables.tf` 中添加域名变量，然后执行：

```bash
# 申请 SSL 证书并配置自动续期
terraform apply -var="domain_name=your-domain.com"
```

完整 Certbot 集成脚本：

```bash
# provisioner "local-exec" 在本地执行
provisioner "local-exec" {
  command = <<EOT
    ssh -i ${var.vps_key_file} ${var.vps_user}@${var.vps_host} \
      "apt-get install -y certbot python3-certbot-nginx && \
       certbot --nginx -d ${var.domain_name} --non-interactive --agree-tos --email admin@${var.domain_name} && \
       crontab -l 2>/dev/null | grep -q 'certbot' || \
       (crontab -l 2>/dev/null; echo '0 3 * * * certbot renew --quiet') | crontab -"
  EOT
}
```

---

## 第五步：管理 Docker 服务

如果你的应用跑在 Docker 中，Terraform 同样可以管理：

```hcl
# Docker Compose 文件模板
locals {
  docker_compose = <<EOF
version: '3.8'
services:
  app:
    image: ${var.docker_image}:${var.docker_tag}
    container_name: ${var.app_name}
    ports:
      - "${var.app_port}:8080"
    volumes:
      - ./data:/app/data
    restart: unless-stopped
    environment:
      - TZ=Asia/Shanghai
EOF
}

resource "null_resource" "docker_deploy" {
  depends_on = [null_resource.nginx_setup]

  connection {
    type     = "ssh"
    user     = var.vps_user
    host     = var.vps_host
    private_key = file(var.vps_key_file)
  }

  provisioner "remote-exec" {
    inline = [
      "curl -fsSL https://get.docker.com | sh",
      "usermod -aG docker ${var.vps_user}",
      "mkdir -p /opt/app && cd /opt/app",
      "echo '${local.docker_compose}' > docker-compose.yml",
      "docker compose up -d",
    ]
  }
}
```

---

## 完整项目结构

```
terraform-vps/
├── main.tf           # 主配置（资源定义）
├── variables.tf      # 变量定义
├── outputs.tf        # 输出定义
├── terraform.tfvars  # 变量值（勿提交到 Git！）
├── .gitignore
└── scripts/
    ├── setup.sh      # 远程执行脚本
    └── deploy.sh
```

`terraform.tfvars` 示例（加入 `.gitignore`）：

```hcl
vps_host     = "1.2.3.4"
vps_user     = "root"
vps_key_file = "~/.ssh/id_rsa"
domain_name  = "myapp.example.com"
app_port     = 8080
docker_image = "myapp"
docker_tag   = "latest"
app_name     = "myapp"
```

`.gitignore`：

```
*.tfvars
.terraform/
terraform.tfstate
terraform.tfstate.backup
*.pkr.hcl
```

---

## 最佳实践与注意事项

### 1. 永远不要提交 State 文件
`terraform.tfstate` 包含敏感信息（IP、密钥等），必须加入 `.gitignore`。建议使用远程 State 后端（S3、Terraform Cloud）。

### 2. 使用 Workspaces 管理多环境
```bash
terraform workspace new staging
terraform workspace new production
```

### 3. 利用 `replace_triggers` 精确控制重启
```hcl
resource "null_resource" "app_restart" {
  triggers = {
    # 只有配置文件内容变化时才重启
    config_hash = filemd5("${path.module}/app.conf")
  }
  # ...
}
```

### 4. 配合 Ansible 处理复杂配置
Terraform 擅长创建资源，Ansible 擅长配置细节。两者结合：
- Terraform 创建服务器 → 输出 IP
- Ansible 用 IP 进行详细配置
```bash
terraform output -raw vps_ip > inventory.ini
ansible-playbook -i inventory.ini setup.yml
```

### 5. 成本监控
每执行一次 `terraform apply`，都会记录变更。定期审查 `terraform plan` 输出，避免不必要的资源创建。

---

## 常见错误排查

| 错误 | 原因 | 解决方法 |
|------|------|----------|
| `Authentication failed` | SSH 密钥问题 | 检查 `private_key` 路径和权限 |
| `connection refused` | SSH 端口非 22 | 添加 `port = 2222` 到 connection 块 |
| `provisioner error` | 远程命令失败 | 用 `inline` 逐一测试命令 |
| `state lock` | 并发执行 Terraform | `terraform force-unlock <id>` |
| `module not found` | 未执行 `terraform init` | 重新运行 `terraform init` |

---

## 总结

Terraform 管理 VPS 的核心价值在于：

- **可重复**：一条命令重建整台服务器，不再依赖记忆
- **可版本控制**：配置代码提交 Git，变更有迹可查
- **零停机更新**：`terraform apply` 增量执行，只变更差异部分
- **团队协作**：多人共用同一套基础设施定义，减少沟通成本

对于 VPS 用户来说，当服务器配置超过 5 个步骤、或需要定期重建时，Terraform 的投入产出比就非常明显了。

---

*本文首发于 [SelfVPS](https://selfvps.net)，关注获取更多 VPS 自托管与云成本优化干货。*
