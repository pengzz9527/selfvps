---
title: "用 Ansible 实现 VPS 批量自动化部署：从零搭建配置管理系统"
description: "告别手动登录每台服务器配置环境的痛苦。本文教你用 Ansible 搭建配置管理系统，通过 Playbook 一键部署 Nginx、Docker、数据库等服务，支持多服务器批量管理，让运维效率提升 10 倍。"
date: 2026-06-18T10:00:00+08:00
slug: "ansible-vps-automation-deployment"
tags: ["Ansible", "自动化", "VPS运维", "配置管理", "DevOps", "批量部署"]
categories: ["自动化运维"]
image: /images/posts/ansible-vps-automation-deployment/featured.png
draft: false
---

你是否经历过这样的场景：新买了一台 VPS，需要安装 Nginx、配置防火墙、部署 Docker 容器、设置 SSL 证书……每次都要手动 SSH 登录、一行行敲命令。如果有 10 台、20 台服务器，这种重复劳动简直令人崩溃。

**Ansible** 就是来解决这个问题的。它是一款开源的自动化配置管理工具，基于 SSH 通信，无需在被管理节点安装任何代理程序。你只需要编写一份 YAML 格式的配置文件（Playbook），Ansible 就能自动在所有目标服务器上执行指定的操作。

今天，我们就来从零搭建一套基于 Ansible 的 VPS 自动化部署系统。

## 为什么选择 Ansible？

在配置管理领域，Chef、Puppet、SaltStack 都是老牌选手，但 Ansible 凭借以下优势脱颖而出：

- **无代理架构**：不需要在目标服务器上安装任何客户端，只需 SSH 可达即可
- **YAML 语法**：Playbook 使用人类可读的 YAML 格式，学习曲线平缓
- **幂等性保证**：多次执行同一 Playbook 不会产生副作用，已配置的服务不会重复安装
- **丰富的模块库**：内置 2000+ 模块，涵盖软件包安装、文件管理、服务控制、云服务 API 调用等
- **社区生态强大**：Galaxy 仓库有数万社区编写的角色（Role）可直接复用

## 环境准备

### 安装 Ansible

Ansible 只需要在**控制机**（你本地电脑或跳板机）上安装：

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install ansible -y

# macOS (Homebrew)
brew install ansible

# 验证安装
ansible --version
```

### 配置 SSH 免密登录

Ansible 通过 SSH 连接目标服务器，所以首先需要配置密钥认证：

```bash
# 生成 SSH 密钥（如果还没有的话）
ssh-keygen -t ed25519 -C "ansible@control"

# 将公钥分发到所有目标服务器
ssh-copy-id root@192.168.1.10
ssh-copy-id root@192.168.1.11
ssh-copy-id root@192.168.1.12
```

### 创建主机清单

在项目目录下创建 `inventory.ini` 文件，定义服务器分组：

```ini
[webservers]
web1 ansible_host=192.168.1.10 ansible_user=root
web2 ansible_host=192.168.1.11 ansible_user=root

[databases]
db1 ansible_host=192.168.1.12 ansible_user=root

[monitoring]
mon1 ansible_host=192.168.1.13 ansible_user=root

[all:vars]
ansible_python_interpreter=/usr/bin/python3
ntp_server=ntp.aliyun.com
```

## 第一个 Playbook：基础系统初始化

让我们从一个实用的场景开始——为新服务器做基础系统初始化。

创建 `playbooks/init.yml`：

```yaml
---
- name: 服务器基础系统初始化
  hosts: all
  become: true
  gather_facts: true

  vars:
    timezone: Asia/Shanghai
    ntp_server: ntp.aliyun.com
    default_locale: zh_CN.UTF-8

  tasks:
    - name: 更新系统软件包
      apt:
        update_cache: true
        upgrade: dist
      when: ansible_os_family == "Debian"

    - name: 安装常用工具
      apt:
        name:
          - curl
          - wget
          - htop
          - tmux
          - git
          - unzip
          - jq
          - fail2ban
        state: present

    - name: 配置时区
      timezone:
        timezone: "{{ timezone }}"

    - name: 配置 NTP 同步
      ansible.builtin.apt:
        name: chrony
        state: present
      notify: 启动 NTP 服务

    - name: 创建运维用户
      user:
        name: deploy
        groups: sudo
        shell: /bin/bash
        state: present
        ssh_authorized_keys:
          - "{{ lookup('file', '~/.ssh/id_ed25519.pub') }}"

    - name: 禁用 root 远程登录
      lineinfile:
        path: /etc/ssh/sshd_config
        regexp: "^PermitRootLogin"
        line: "PermitRootLogin prohibit-password"
      notify: 重启 SSH 服务
```

运行这个 Playbook：

```bash
ansible-playbook -i inventory.ini playbooks/init.yml
```

## 部署 Web 服务：Nginx + Let's Encrypt

接下来，让我们编写一个更复杂的 Playbook，自动部署 Nginx 并配置 HTTPS。

创建 `playbooks/webserver.yml`：

```yaml
---
- name: 部署 Nginx Web 服务器
  hosts: webservers
  become: true
  vars:
    domain: example.com
    web_root: /var/www/example.com
    ssl_email: admin@example.com

  tasks:
    - name: 安装 Nginx 和 Certbot
      apt:
        name:
          - nginx
          - certbot
          - python3-certbot-nginx
        state: present

    - name: 创建网站目录结构
      file:
        path: "{{ item }}"
        state: directory
        owner: www-data
        group: www-data
        mode: "0755"
      loop:
        - "{{ web_root }}"
        - "{{ web_root }}/logs"
        - "{{ web_root }}/ssl"

    - name: 部署 Nginx 配置
      template:
        src: templates/nginx.conf.j2
        dest: /etc/nginx/sites-available/{{ domain }}
        owner: root
        group: root
        mode: "0644"
      notify: 重载 Nginx

    - name: 启用站点配置
      file:
        src: /etc/nginx/sites-available/{{ domain }}
        dest: /etc/nginx/sites-enabled/{{ domain }}
        state: link
      notify: 测试并重载 Nginx

    - name: 获取 SSL 证书
      community.general.certbot:
        command: certonly
        email: "{{ ssl_email }}"
        domains:
          - "{{ domain }}"
          - "www.{{ domain }}"
        webroot_path: "{{ web_root }}"
        account_sid: "{{ web_root }}/letsencrypt_account"
        accept_terms: true
      notify: 重载 Nginx

    - name: 设置证书自动续期
      cron:
        name: "Certbot 自动续期"
        special_time: daily
        job: "certbot renew --quiet && systemctl reload nginx"
```

对应的 Nginx 模板 `templates/nginx.conf.j2`：

```nginx
server {
    listen 80;
    server_name {{ domain }} www.{{ domain }};
    root {{ web_root }};

    location /.well-known/acme-challenge/ {
        root {{ web_root }};
    }

    location / {
        return 301 https://$host$request_uri;
    }
}

server {
    listen 443 ssl http2;
    server_name {{ domain }} www.{{ domain }};

    ssl_certificate {{ web_root }}/ssl/fullchain.pem;
    ssl_certificate_key {{ web_root }}/ssl/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    root {{ web_root }};
    index index.html;

    location / {
        try_files $uri $uri/ =404;
    }

    location /logs/ {
        autoindex on;
        alias {{ web_root }}/logs/;
    }
}
```

## 部署 Docker 环境

对于需要运行容器的服务器，我们可以用 Ansible 一键部署 Docker：

创建 `playbooks/docker.yml`：

```yaml
---
- name: 安装和配置 Docker
  hosts: all
  become: true

  tasks:
    - name: 安装 Docker 依赖
      apt:
        name:
          - apt-transport-https
          - ca-certificates
          - curl
          - gnupg
          - lsb-release
        state: present

    - name: 添加 Docker GPG 密钥
      apt_key:
        url: https://download.docker.com/linux/ubuntu/gpg
        state: present

    - name: 添加 Docker 源
      apt_repository:
        repo: >-
          deb [arch=amd64]
          https://download.docker.com/linux/ubuntu
          {{ ansible_distribution_release }} stable
        state: present

    - name: 安装 Docker
      apt:
        name:
          - docker-ce
          - docker-ce-cli
          - containerd.io
          - docker-compose-plugin
        state: present
        update_cache: true

    - name: 配置 Docker 镜像加速
      copy:
        content: |
          {
            "registry-mirrors": ["https://docker.m.daocloud.io"],
            "exec-opts": ["native.cgroupdriver=systemd"],
            "log-driver": "json-file",
            "log-opts": {
              "max-size": "100m",
              "max-file": "3"
            }
          }
        dest: /etc/docker/daemon.json
        mode: "0644"
      notify: 重启 Docker

    - name: 启用并启动 Docker
      systemd:
        name: docker
        enabled: true
        state: started

    - name: 允许当前用户管理 Docker
      user:
        name: "{{ ansible_user }}"
        groups: docker
        append: true
```

## 使用 Role 组织复杂项目

当 Playbook 越来越复杂时，推荐使用 **Role** 来组织代码。

创建角色目录结构：

```
roles/
├── common/
│   ├── tasks/
│   │   └── main.yml
│   ├── handlers/
│   │   └── main.yml
│   ├── templates/
│   ├── vars/
│   │   └── main.yml
│   └── defaults/
│       └── main.yml
├── nginx/
│   └── ...
├── docker/
│   └── ...
└── monitoring/
    └── ...
```

`roles/common/tasks/main.yml`：

```yaml
---
- name: 安装公共依赖包
  apt:
    name: "{{ common_packages }}"
    state: present

- name: 配置系统内核参数
  sysctl:
    name: "{{ item.key }}"
    value: "{{ item.value }}"
    sysctl_set: true
    state: present
    reload: true
  loop: "{{ kernel_params | default([]) }}"

- name: 配置 ulimit
  pam_limits:
    domain: "*"
    limit_type: "{{ item.type }}"
    limit_item: "{{ item.item }}"
    value: "{{ item.value }}"
  loop: "{{ ulimit_configs | default([]) }}"
```

然后在主 Playbook 中引用：

```yaml
---
- name: 全栈服务器初始化
  hosts: all
  roles:
    - common
    - docker

- name: 部署 Web 服务
  hosts: webservers
  roles:
    - nginx

- name: 部署监控系统
  hosts: monitoring
  roles:
    - monitoring
```

## 变量管理与环境隔离

实际运维中，不同环境（开发、测试、生产）的配置差异很大。Ansible 提供了多种变量管理方式：

```
inventory/
├── dev/
│   ├── hosts.ini
│   └── vars.yml
├── staging/
│   ├── hosts.ini
│   └── vars.yml
└── prod/
    ├── hosts.ini
    └── vars.yml
```

通过 `-e` 参数覆盖变量：

```bash
# 指定环境和额外变量
ansible-playbook -i inventory/prod/hosts.yml \
  -e "domain=prod.example.com" \
  -e "replicas=3" \
  playbooks/deploy.yml
```

## 实战：一键部署完整 LAMP 栈

让我们把前面的知识整合起来，写一个完整的 LAMP 栈部署 Playbook：

```yaml
---
- name: 部署 LAMP 网站栈
  hosts: webservers
  become: true
  vars:
    app_name: myapp
    app_port: 8080
    db_name: myapp_db
    db_user: myapp_user
    db_password: "{{ vault_db_password }}"
    php_version: "8.3"

  pre_tasks:
    - name: 检查磁盘空间
      assert:
        that:
          - ansible_mounts | selectattr('mount', 'equalto', '/') | map(attribute='size_available') | first > 5368709120
        fail_msg: "根分区可用空间不足 5GB"
        success_msg: "磁盘空间充足"

  roles:
    - role: common

  tasks:
    - name: 安装 Apache
      apt:
        name:
          - apache2
          - "libapache2-mod-php{{ php_version }}"
        state: present

    - name: 安装 MySQL
      apt:
        name:
          - mysql-server
          - python3-mysqldb
        state: present
      notify: 启动 MySQL

    - name: 安装 PHP 扩展
      apt:
        name:
          - "php{{ php_version }}-mysql"
          - "php{{ php_version }}-curl"
          - "php{{ php_version }}-gd"
          - "php{{ php_version }}-mbstring"
          - "php{{ php_version }}-xml"
        state: present

    - name: 配置虚拟主机
      template:
        src: templates/vhost.conf.j2
        dest: /etc/apache2/sites-available/{{ app_name }}.conf
      notify: 重载 Apache

    - name: 创建数据库和用户
      community.mysql.mysql_db:
        name: "{{ db_name }}"
        state: present
      community.mysql.mysql_user:
        name: "{{ db_user }}"
        password: "{{ db_password }}"
        priv: "{{ db_name }}.*:ALL"
        state: present

    - name: 部署应用代码
      copy:
        src: "../apps/{{ app_name }}/"
        dest: "/var/www/{{ app_name }}/"
        owner: www-data
        group: www-data
      notify: 重载 Apache
```

注意这里使用了 `vault_db_password`——Ansible Vault 用于加密敏感信息：

```bash
# 创建加密文件
ansible-vault create vars/secrets.yml

# 编辑加密文件
ansible-vault edit vars/secrets.yml

# 运行时需要解密
ansible-playbook --ask-vault-pass playbooks/deploy.yml

# 或者提供密码文件
ansible-playbook --vault-password-file .vault_pass playbooks/deploy.yml
```

## 最佳实践总结

1. **幂等性优先**：每个任务都应该可以安全地重复执行
2. **变量外置**：不要把硬编码的值写在 Playbook 里，用变量和 inventory 管理
3. **角色复用**：将通用功能封装成 Role，在不同项目中复用
4. **使用 Galaxy**：社区角色可以节省大量时间（`ansible-galaxy install geerlingguy.docker`）
5. **CI/CD 集成**：将 Ansible 集成到 GitLab CI / GitHub Actions 中实现自动化部署流水线
6. **文档化**：为每个 Role 编写 README，说明用途、变量和依赖
7. **测试先行**：用 Molecule 对 Role 进行单元测试，确保变更不会破坏现有配置

## 结语

Ansible 的学习曲线很平缓——你可以从最简单的单台服务器自动化开始，逐步扩展到多环境、多角色的复杂架构。配合版本控制系统（Git），你的基础设施就变成了可追溯、可回滚、可协作的代码。

当你习惯了用 Playbook 管理服务器之后，就再也回不去手动 SSH 的时代了。

---

*这篇文章对你有帮助吗？欢迎在评论区分享你用 Ansible 做的有趣项目！*
