---
title: "Terraform + VPS: Infrastructure as Code入门，一条命令重建整台服务器"
description: "Manage VPS infrastructure with Terraform — from server provisioning to Nginx config, SSL certificates, fully automated. Say goodbye to manual SSH operations and hello to reproducible, version-controlled server setups."
date: 2026-09-23T10:00:00+08:00
lastmod: 2026-09-23T10:00:00+08:00
slug: "terraform-vps-iac"
image: /images/posts/terraform-vps-iac/featured.png
tags: ["Terraform", "VPS", "Infrastructure as Code", "DevOps", "Automation", "Nginx", "LetsEncrypt", "Cloud Cost"]
categories: ["Operations", "DevOps"]
aliases: [/en/post/terraform-vps-iac/]
---

## Why Do You Need Terraform for VPS Management?

If you've ever experienced this:

> You buy a new VPS, SSH in manually, run `apt install` here and there, configure Nginx, apply for SSL certificates, deploy your app... A few months later, you get a new server and realize you can't remember what you installed or how you configured everything.

This is the **pain of manual operations** — every time you start from scratch, configs can't be replicated, and disaster recovery is costly. **Infrastructure as Code (IaC)** exists to solve exactly this problem.

**Terraform** is the most popular IaC tool today. It lets you describe your desired server state in declarative code, then automatically applies the changes. Best of all, **it can manage existing servers** — you don't need to start from scratch by creating cloud instances.

---

## Core Terraform Concepts

Before diving into VPS management, understand Terraform's three core concepts:

| Concept | Description | Analogy |
|---------|-------------|---------|
| **Provider** | Plugin that interacts with APIs (e.g., DigitalOcean, AWS, Local) | Driver |
| **Resource** | What you want to create or manage (server, domain, SSL cert) | Building materials |
| **State** | Database recording current actual state | Construction blueprint |

For VPS scenarios, the most practical providers are `null` (local operations) and `proxmox` (Proxmox VE) or `digitalocean` (cloud VPS). This article focuses on the **local Terraform + remote-exec** approach, applicable to any VPS.

---

## Environment Setup

### Install Terraform

```bash
# Ubuntu/Debian
curl -fsSL https://apt.releases.hashicorp.com/gpg | sudo apt-key add -
sudo apt-add-repository "deb [arch=amd64] https://apt.releases.hashicorp.com $(lsb_release -cs) main"
sudo apt update && sudo apt install terraform -y

# Or via Homebrew (macOS)
brew install terraform

# Verify installation
terraform --version
# Terraform v1.7.x
```

### Create Project Directory

```bash
mkdir -p ~/terraform-vps && cd ~/terraform-vps
```

---

## Step 1: Define Provider and Variables

Create a `main.tf` file:

```hcl
# Provider config — use local to execute remote commands
provider "null" {}

# Variable definitions
variable "vps_host" {
  description = "VPS SSH address"
  type        = string
  default     = "your-vps-ip"
}

variable "vps_user" {
  description = "SSH username"
  type        = string
  default     = "root"
}

variable "vps_key_file" {
  description = "SSH private key path"
  type        = string
  default     = "~/.ssh/id_rsa"
}

variable "app_port" {
  description = "Application port"
  type        = number
  default     = 8080
}
```

---

## Step 2: Create Base Environment

Use `null_resource` + `provisioner "remote-exec"` to run commands on your existing VPS:

```hcl
# Update system and install base tools
resource "null_resource" "base_setup" {
  triggers = {
    always_run = timestamp()
  }

  connection {
    type        = "ssh"
    user        = var.vps_user
    host        = var.vps_host
    private_key = file(var.vps_key_file)
  }

  provisioner "remote-exec" {
    inline = [
      "apt-get update && apt-get upgrade -y",
      "apt-get install -y curl wget git ca-certificates gnupg lsb-release",
      # Create application user
      "useradd -m -s /bin/bash appuser",
      "mkdir -p /opt/app /var/log/app /etc/app",
    ]
  }
}
```

Run deployment:

```bash
terraform init
terraform plan   # Preview changes
terraform apply  # Apply changes
```

---

## Step 3: Configure Nginx Reverse Proxy

Terraform can directly manage Nginx configuration:

```hcl
# Nginx site config template
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

# Deploy Nginx configuration
resource "null_resource" "nginx_setup" {
  depends_on = [null_resource.base_setup]

  connection {
    type        = "ssh"
    user        = var.vps_user
    host        = var.vps_host
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

## Step 4: Auto-Provision SSL Certificates

Integrate Certbot for HTTPS with automatic renewal:

```hcl
# Output variables
output "vps_ip" {
  value       = var.vps_host
  description = "VPS IP address"
}

output "deploy_time" {
  value       = timestamp()
  description = "Deployment time"
}
```

Add domain variable to `variables.tf`, then execute:

```bash
# Apply for SSL certificate and configure auto-renewal
terraform apply -var="domain_name=your-domain.com"
```

Complete Certbot integration script:

```bash
# provisioner "local-exec" runs locally
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

## Step 5: Manage Docker Services

If your app runs in Docker, Terraform can manage it too:

```hcl
# Docker Compose file template
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
    type        = "ssh"
    user        = var.vps_user
    host        = var.vps_host
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

## Complete Project Structure

```
terraform-vps/
├── main.tf           # Main config (resource definitions)
├── variables.tf      # Variable definitions
├── outputs.tf        # Output definitions
├── terraform.tfvars  # Variable values (DO NOT commit to Git!)
├── .gitignore
└── scripts/
    ├── setup.sh      # Remote execution scripts
    └── deploy.sh
```

`terraform.tfvars` example (add to `.gitignore`):

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

`.gitignore`:

```
*.tfvars
.terraform/
terraform.tfstate
terraform.tfstate.backup
*.pkr.hcl
```

---

## Best Practices and Considerations

### 1. Never Commit State Files
`terraform.tfstate` contains sensitive information (IPs, keys). Always add it to `.gitignore`. Use a remote state backend (S3, Terraform Cloud).

### 2. Use Workspaces for Multi-Environment
```bash
terraform workspace new staging
terraform workspace new production
```

### 3. Use `replace_triggers` for Precise Restart Control
```hcl
resource "null_resource" "app_restart" {
  triggers = {
    # Only restart when config file content changes
    config_hash = filemd5("${path.module}/app.conf")
  }
  # ...
}
```

### 4. Combine with Ansible for Complex Configurations
Terraform excels at creating resources; Ansible excels at detailed configuration. Use them together:
- Terraform creates the server → outputs IP
- Ansible uses the IP for detailed setup
```bash
terraform output -raw vps_ip > inventory.ini
ansible-playbook -i inventory.ini setup.yml
```

### 5. Cost Monitoring
Every `terraform apply` records changes. Regularly review `terraform plan` output to avoid unnecessary resource creation.

---

## Common Error Troubleshooting

| Error | Cause | Solution |
|-------|-------|----------|
| `Authentication failed` | SSH key issue | Check `private_key` path and permissions |
| `connection refused` | SSH port not 22 | Add `port = 2222` to connection block |
| `provisioner error` | Remote command failed | Test commands one by one with `inline` |
| `state lock` | Concurrent Terraform execution | `terraform force-unlock <id>` |
| `module not found` | Haven't run `terraform init` | Re-run `terraform init` |

---

## Summary

The core value of Terraform for VPS management:

- **Reproducible**: Rebuild an entire server with one command — no more relying on memory
- **Version controlled**: Config code committed to Git, changes are traceable
- **Zero-downtime updates**: `terraform apply` executes incrementally, only changing diffs
- **Team collaboration**: Multiple people share the same infrastructure definition, reducing communication overhead

For VPS users, when server configuration exceeds 5 steps or requires regular rebuilding, Terraform's ROI becomes very apparent.

---

*Originally published on [SelfVPS](https://selfvps.net). Follow for more VPS self-hosting and cloud cost optimization content.*
