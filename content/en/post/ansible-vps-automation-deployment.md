---
title: "Automating VPS Deployment with Ansible: Building a Configuration Management System from Scratch"
description: "Stop manually logging into each server to configure environments. Learn how to build an Ansible-based configuration management system with Playbooks for one-click deployment of Nginx, Docker, databases, and more across multiple servers."
date: 2026-06-18T10:00:00+08:00
slug: "ansible-vps-automation-deployment"
tags: ["Ansible", "Automation", "VPS Operations", "Configuration Management", "DevOps", "Batch Deployment"]
categories: ["Automation & Ops"]
image: /images/posts/ansible-vps-automation-deployment/featured.png
draft: false
---

Have you ever experienced this scenario: you bought a new VPS and need to install Nginx, configure the firewall, deploy Docker containers, set up SSL certificates… Every time you have to manually SSH in and type commands line by line. What if you have 10 or 20 servers? This repetitive work becomes unbearable.

**Ansible** solves exactly this problem. It's an open-source automation configuration management tool that communicates via SSH and requires no agent installation on managed nodes. You just write a YAML configuration file (Playbook), and Ansible automatically executes the specified operations on all target servers.

Today, we'll build a complete Ansible-based VPS automation deployment system from scratch.

## Why Choose Ansible?

In the configuration management space, Chef, Puppet, and SaltStack are all established players. But Ansible stands out with several advantages:

- **Agentless architecture**: No client software needed on target servers—just SSH access
- **YAML syntax**: Playbooks use human-readable YAML, with a gentle learning curve
- **Idempotency guarantee**: Running the same Playbook multiple times produces no side effects; configured services aren't reinstalled
- **Rich module library**: 2000+ built-in modules covering package installation, file management, service control, cloud APIs, and more
- **Strong community ecosystem**: Galaxy repository has tens of thousands of reusable community-written Roles

## Environment Setup

### Installing Ansible

Ansible only needs to be installed on the **control machine** (your local computer or bastion host):

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install ansible -y

# macOS (Homebrew)
brew install ansible

# Verify installation
ansible --version
```

### Configuring SSH Key Authentication

Ansible connects to target servers via SSH, so you need to set up key-based authentication:

```bash
# Generate SSH key (if you don't have one)
ssh-keygen -t ed25519 -C "ansible@control"

# Distribute the public key to all target servers
ssh-copy-id root@192.168.1.10
ssh-copy-id root@192.168.1.11
ssh-copy-id root@192.168.1.12
```

### Creating the Inventory

Create an `inventory.ini` file in your project directory to define server groups:

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

## First Playbook: Basic System Initialization

Let's start with a practical scenario—basic system initialization for new servers.

Create `playbooks/init.yml`:

```yaml
---
- name: Server Base System Initialization
  hosts: all
  become: true
  gather_facts: true

  vars:
    timezone: Asia/Shanghai
    ntp_server: ntp.aliyun.com
    default_locale: zh_CN.UTF-8

  tasks:
    - name: Update system packages
      apt:
        update_cache: true
        upgrade: dist
      when: ansible_os_family == "Debian"

    - name: Install common utilities
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

    - name: Configure timezone
      timezone:
        timezone: "{{ timezone }}"

    - name: Configure NTP sync
      ansible.builtin.apt:
        name: chrony
        state: present
      notify: Start NTP service

    - name: Create operations user
      user:
        name: deploy
        groups: sudo
        shell: /bin/bash
        state: present
        ssh_authorized_keys:
          - "{{ lookup('file', '~/.ssh/id_ed25519.pub') }}"

    - name: Disable root remote login
      lineinfile:
        path: /etc/ssh/sshd_config
        regexp: "^PermitRootLogin"
        line: "PermitRootLogin prohibit-password"
      notify: Restart SSH service
```

Run this Playbook:

```bash
ansible-playbook -i inventory.ini playbooks/init.yml
```

## Deploying Web Services: Nginx + Let's Encrypt

Next, let's write a more complex Playbook that deploys Nginx and configures HTTPS automatically.

Create `playbooks/webserver.yml`:

```yaml
---
- name: Deploy Nginx Web Server
  hosts: webservers
  become: true
  vars:
    domain: example.com
    web_root: /var/www/example.com
    ssl_email: admin@example.com

  tasks:
    - name: Install Nginx and Certbot
      apt:
        name:
          - nginx
          - certbot
          - python3-certbot-nginx
        state: present

    - name: Create website directory structure
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

    - name: Deploy Nginx configuration
      template:
        src: templates/nginx.conf.j2
        dest: /etc/nginx/sites-available/{{ domain }}
        owner: root
        group: root
        mode: "0644"
      notify: Reload Nginx

    - name: Enable site configuration
      file:
        src: /etc/nginx/sites-available/{{ domain }}
        dest: /etc/nginx/sites-enabled/{{ domain }}
        state: link
      notify: Test and reload Nginx

    - name: Obtain SSL certificate
      community.general.certbot:
        command: certonly
        email: "{{ ssl_email }}"
        domains:
          - "{{ domain }}"
          - "www.{{ domain }}"
        webroot_path: "{{ web_root }}"
        account_sid: "{{ web_root }}/letsencrypt_account"
        accept_terms: true
      notify: Reload Nginx

    - name: Set up automatic certificate renewal
      cron:
        name: "Certbot auto-renewal"
        special_time: daily
        job: "certbot renew --quiet && systemctl reload nginx"
```

The corresponding Nginx template `templates/nginx.conf.j2`:

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

## Deploying Docker Environment

For servers that need to run containers, you can deploy Docker with a single Ansible Playbook:

Create `playbooks/docker.yml`:

```yaml
---
- name: Install and Configure Docker
  hosts: all
  become: true

  tasks:
    - name: Install Docker dependencies
      apt:
        name:
          - apt-transport-https
          - ca-certificates
          - curl
          - gnupg
          - lsb-release
        state: present

    - name: Add Docker GPG key
      apt_key:
        url: https://download.docker.com/linux/ubuntu/gpg
        state: present

    - name: Add Docker repository
      apt_repository:
        repo: >-
          deb [arch=amd64]
          https://download.docker.com/linux/ubuntu
          {{ ansible_distribution_release }} stable
        state: present

    - name: Install Docker
      apt:
        name:
          - docker-ce
          - docker-ce-cli
          - containerd.io
          - docker-compose-plugin
        state: present
        update_cache: true

    - name: Configure Docker registry mirror
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
      notify: Restart Docker

    - name: Enable and start Docker
      systemd:
        name: docker
        enabled: true
        state: started

    - name: Allow current user to manage Docker
      user:
        name: "{{ ansible_user }}"
        groups: docker
        append: true
```

## Organizing Complex Projects with Roles

As your Playbooks grow more complex, use **Roles** to organize your code.

Create a role directory structure:

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

`roles/common/tasks/main.yml`:

```yaml
---
- name: Install common packages
  apt:
    name: "{{ common_packages }}"
    state: present

- name: Configure kernel parameters
  sysctl:
    name: "{{ item.key }}"
    value: "{{ item.value }}"
    sysctl_set: true
    state: present
    reload: true
  loop: "{{ kernel_params | default([]) }}"

- name: Configure ulimits
  pam_limits:
    domain: "*"
    limit_type: "{{ item.type }}"
    limit_item: "{{ item.item }}"
    value: "{{ item.value }}"
  loop: "{{ ulimit_configs | default([]) }}"
```

Then reference them in the main Playbook:

```yaml
---
- name: Full-stack server initialization
  hosts: all
  roles:
    - common
    - docker

- name: Deploy web services
  hosts: webservers
  roles:
    - nginx

- name: Deploy monitoring stack
  hosts: monitoring
  roles:
    - monitoring
```

## Variable Management and Environment Isolation

In real-world operations, different environments (development, staging, production) have different configurations. Ansible provides multiple ways to manage variables:

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

Override variables with the `-e` flag:

```bash
# Specify environment and extra variables
ansible-playbook -i inventory/prod/hosts.yml \
  -e "domain=prod.example.com" \
  -e "replicas=3" \
  playbooks/deploy.yml
```

## Complete LAMP Stack Deployment

Let's integrate everything into a complete LAMP stack deployment Playbook:

```yaml
---
- name: Deploy LAMP Website Stack
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
    - name: Check disk space
      assert:
        that:
          - ansible_mounts | selectattr('mount', 'equalto', '/') | map(attribute='size_available') | first > 5368709120
        fail_msg: "Root partition has less than 5GB free space"
        success_msg: "Disk space is sufficient"

  roles:
    - role: common

  tasks:
    - name: Install Apache
      apt:
        name:
          - apache2
          - "libapache2-mod-php{{ php_version }}"
        state: present

    - name: Install MySQL
      apt:
        name:
          - mysql-server
          - python3-mysqldb
        state: present
      notify: Start MySQL

    - name: Install PHP extensions
      apt:
        name:
          - "php{{ php_version }}-mysql"
          - "php{{ php_version }}-curl"
          - "php{{ php_version }}-gd"
          - "php{{ php_version }}-mbstring"
          - "php{{ php_version }}-xml"
        state: present

    - name: Configure virtual host
      template:
        src: templates/vhost.conf.j2
        dest: /etc/apache2/sites-available/{{ app_name }}.conf
      notify: Reload Apache

    - name: Create database and user
      community.mysql.mysql_db:
        name: "{{ db_name }}"
        state: present
      community.mysql.mysql_user:
        name: "{{ db_user }}"
        password: "{{ db_password }}"
        priv: "{{ db_name }}.*:ALL"
        state: present

    - name: Deploy application code
      copy:
        src: "../apps/{{ app_name }}/"
        dest: "/var/www/{{ app_name }}/"
        owner: www-data
        group: www-data
      notify: Reload Apache
```

Note the use of `vault_db_password`—Ansible Vault encrypts sensitive information:

```bash
# Create encrypted file
ansible-vault create vars/secrets.yml

# Edit encrypted file
ansible-vault edit vars/secrets.yml

# Run with password prompt
ansible-playbook --ask-vault-pass playbooks/deploy.yml

# Or provide a password file
ansible-playbook --vault-password-file .vault_pass playbooks/deploy.yml
```

## Best Practices Summary

1. **Prioritize idempotency**: Every task should be safe to run repeatedly
2. **Externalize variables**: Don't hardcode values in Playbooks—use variables and inventory
3. **Reuse roles**: Encapsulate common functionality into Roles for reuse across projects
4. **Leverage Galaxy**: Community roles save massive amounts of time (`ansible-galaxy install geerlingguy.docker`)
5. **Integrate with CI/CD**: Embed Ansible in GitLab CI / GitHub Actions for automated deployment pipelines
6. **Document everything**: Write READMEs for each Role explaining purpose, variables, and dependencies
7. **Test first**: Use Molecule for unit testing Roles to ensure changes don't break existing configurations

## Conclusion

Ansible has a gentle learning curve—you can start with simple single-server automation and gradually scale up to multi-environment, multi-role architectures. Paired with version control (Git), your infrastructure becomes traceable, rollable-back, and collaboratively manageable code.

Once you get used to managing servers with Playbooks, you'll never want to go back to manual SSH sessions.

---

*Found this guide helpful? Share your interesting Ansible projects in the comments!*
