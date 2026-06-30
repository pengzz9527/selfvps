---
title: "Self-Hosted GitLab CI/CD Pipeline: Build a Complete Continuous Integration & Deployment Platform from Scratch"
description: "Deploy a complete GitLab CI/CD pipeline from scratch on your VPS — covering Runner configuration, Docker-in-Docker builds, automated deployment to production, best practices, and troubleshooting guide."
date: 2026-06-30T10:00:00+08:00
lastmod: 2026-06-30T10:00:00+08:00
slug: "gitlab-cicd-selfhosted-guide"
tags: ["GitLab", "CI/CD", "DevOps", "Docker", "Deployment Automation", "Runner", "Continuous Integration", "VPS"]
categories: ["Deployment Guides"]
draft: false
image: /images/posts/gitlab-cicd-selfhosted-guide/featured.png
aliases: [/en/post/gitlab-cicd-selfhosted-guide/]
---

## Why Self-Host GitLab CI/CD?

In the world of self-hosting and VPS administration, CI/CD (Continuous Integration/Continuous Deployment) is the core infrastructure that boosts development efficiency. GitHub Actions and GitLab CI are the two most popular choices today. For teams that value data sovereignty, privacy, and cost control, self-hosting GitLab CI/CD offers significant advantages:

- **Full Control**: Code, build artifacts, and deployment flows are all in your hands
- **Cost Predictability**: No per-minute billing from third-party platforms — ideal for long-running heavy tasks
- **Flexible Customization**: Customize Runner resources, build environments, and deployment strategies
- **Offline Ready**: Works perfectly in air-gapped or internal network environments

## Architecture Overview

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   GitLab     │────▶│  GitLab CI   │────▶│  Runner     │
│   Server     │     │  (Pipeline)  │     │  (Docker)   │
│  :8080/:443  │     │              │     │             │
└─────────────┘     └──────────────┘     └──────┬──────┘
                                                │
                                        ┌───────▼────────┐
                                        │  Target Server │
                                        │  (Staging/Prod)│
                                        └────────────────┘
```

## Step 1: Deploy the GitLab Server

### One-Click Deployment with Docker Compose

The official GitLab Omnibus image managed via Docker Compose is recommended:

```yaml
# docker-compose.yml
version: '3.8'

services:
  gitlab:
    image: gitlab/gitlab-ce:latest
    container_name: gitlab
    hostname: gitlab.example.com
    ports:
      - "80:80"
      - "443:443"
      - "2222:22"
    volumes:
      - ./config:/etc/gitlab
      - ./logs:/var/log/gitlab
      - ./data:/var/opt/gitlab
    shm_size: '256m'
    restart: unless-stopped
    mem_limit: 8g
    cpus: 4
```

### Initial Configuration

After the first launch, edit `/config/gitlab.rb`:

```ruby
# External URL
external_url 'https://gitlab.example.com'

# SSH port mapping
gitlab_rails['gitlab_shell_ssh_port'] = 2222

# Memory optimization (for 4GB VPS)
unicorn['worker_memory_min'] = 5
unicorn['worker_memory_max'] = 150

# Backup strategy
gitlab_rails['manage_backup_path'] = true
gitlab_rails['backup_path'] = "/var/opt/gitlab/backups"
gitlab_rails['backup_keep_time'] = 604800  # Keep for 7 days
```

### Reconfigure and Start

```bash
docker compose up -d
# Wait for GitLab initialization (first startup may take 5-10 minutes)
docker exec -it gitlab gitlab-ctl reconfigure
```

## Step 2: Configure GitLab Runner

Runners are the components that actually execute CI/CD tasks. The Docker Executor mode is recommended.

### Register the Runner

```bash
# Get registration token (from GitLab Web UI: Settings > CI/CD > Runners)
docker run --rm -v /srv/gitlab-runner/config:/etc/gitlab-runner \
  gitlab/gitlab-runner:latest \
  register \
  --non-interactive \
  --url "https://gitlab.example.com" \
  --registration-token "YOUR_REGISTRATION_TOKEN" \
  --executor "docker" \
  --description "Docker Runner" \
  --docker-image "docker:latest" \
  --docker-volumes /var/run/docker.sock:/var/run/docker.sock \
  --tag-list "docker,linux" \
  --locked="false" \
  --run-untagged="true"
```

### Docker-in-Docker (DinD) Mode

For containerized builds (e.g., building Docker images), use DinD:

```yaml
# gitlab-runner/config/config.toml
[[runners]]
  executor = "docker"
  [runners.docker]
    image = "docker:latest"
    privileged = true
    disable_entrypoint_overwrite = false
    oom_kill_disable = false
    disable_cache = false
    volumes = ["/cache"]
    shm_size = 0
```

### Multi-Runner Strategy

| Runner Type | Use Case | Tags |
|------------|----------|------|
| Shared Runner | Small projects, lightweight builds | `docker`, `linux` |
| Dedicated Runner | Large projects, GPU builds | `gpu`, `large` |
| Environment Runner | Deploy to specific environments only | `staging`, `production` |

## Step 3: Write .gitlab-ci.yml

### Basic Pipeline Template

```yaml
# .gitlab-ci.yml
stages:
  - build
  - test
  - deploy-staging
  - deploy-production

variables:
  DOCKER_IMAGE: $CI_REGISTRY_IMAGE:$CI_COMMIT_SHORT_SHA
  DEPLOY_SERVER: "deploy@example.com"
  DEPLOY_PATH: "/var/www/app"

# Code linting stage
lint:
  stage: build
  image: node:20-alpine
  script:
    - npm ci
    - npm run lint
  rules:
    - changes:
        - "src/**/*"
        - "package.json"

# Build stage
build:
  stage: build
  image: docker:24-dind
  services:
    - docker:24-docker
  variables:
    DOCKER_TLS_CERTDIR: ""
  script:
    - docker login -u $CI_REGISTRY_USER -p $CI_REGISTRY_PASSWORD $CI_REGISTRY
    - docker build -t $DOCKER_IMAGE .
    - docker push $DOCKER_IMAGE
  rules:
    - if: '$CI_COMMIT_BRANCH == "main"'
    - if: '$CI_COMMIT_BRANCH == "develop"'

# Test stage
test:
  stage: test
  image: node:20-alpine
  script:
    - npm ci
    - npm run test:coverage
  coverage: '/Lines\s*:\s*(\d+.?\d*)/'
  artifacts:
    reports:
      coverage_report:
        coverage_format: cobertura
        path: "coverage/cobertura-coverage.xml"
  rules:
    - changes:
        - "src/**/*"

# Deploy to staging environment
deploy-staging:
  stage: deploy-staging
  image: alpine:latest
  script:
    - apk add --no-cache openssh-client rsync
    - eval $(ssh-agent -s)
    - echo "$SSH_PRIVATE_KEY" | ssh-add -
    - ssh-keyscan -H $DEPLOY_SERVER >> ~/.ssh/known_hosts
    - rsync -avz --delete -e "ssh -o StrictHostKeyChecking=no" \
        ./ $DEPLOY_SERVER:$DEPLOY_PATH/staging/
    - ssh $DEPLOY_SERVER "cd $DEPLOY_PATH/staging && docker compose up -d"
  environment:
    name: staging
    url: https://staging.gitlab.example.com
  rules:
    - if: '$CI_COMMIT_BRANCH == "main"'

# Deploy to production (requires manual trigger)
deploy-production:
  stage: deploy-production
  image: alpine:latest
  script:
    - apk add --no-cache openssh-client rsync
    - eval $(ssh-agent -s)
    - echo "$SSH_PRIVATE_KEY" | ssh-add -
    - ssh-keyscan -H $DEPLOY_SERVER >> ~/.ssh/known_hosts
    - rsync -avz --delete -e "ssh -o StrictHostKeyChecking=no" \
        ./ $DEPLOY_SERVER:$DEPLOY_PATH/production/
    - ssh $DEPLOY_SERVER "cd $DEPLOY_PATH/production && docker compose up -d"
  environment:
    name: production
    url: https://gitlab.example.com
  rules:
    - if: '$CI_COMMIT_BRANCH == "main"'
      when: manual
```

### Multi-Language Project Examples

#### Python Project

```yaml
.python-test:
  image: python:3.12-slim
  variables:
    PIP_CACHE_DIR: "$CI_PROJECT_DIR/.cache/pip"
  cache:
    key: "${CI_COMMIT_REF_SLUG}-pip"
    paths:
      - .cache/pip
  before_script:
    - pip install --upgrade pip
    - pip install -r requirements.txt
    - pip install pytest pytest-cov

unit-tests:
  extends: .python-test
  stage: test
  script:
    - pytest tests/ --cov=app --cov-report=xml
  artifacts:
    reports:
      coverage_report:
        coverage_format: cobertura
        path: coverage.xml
```

#### Go Project

```yaml
.go-build:
  image: golang:1.22-alpine
  cache:
    key: "${CI_COMMIT_REF_SLUG}-go"
    paths:
      - go.mod
      - go.sum
      - ~/go/pkg/mod/
  before_script:
    - go version
    - go mod download

build-binary:
  extends: .go-build
  stage: build
  script:
    - CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o app ./cmd/app
  artifacts:
    paths:
      - app
```

## Step 4: Security Configuration

### SSH Key Management

```bash
# Set CI/CD variables in GitLab
# Settings > CI/CD > Variables

# Recommended security practices:
# 1. Use Deploy Keys (read-only) for code checkout
# 2. Use CI/CD Variables for sensitive information
# 3. Enable variable masking to prevent log leakage
# 4. Scope runners to specific projects/environments
```

### GitLab CI/CD Variable Types

| Variable Type | Purpose | Example |
|--------------|---------|---------|
| Variable | Standard environment variable | `DEPLOY_PATH=/var/www` |
| File | Written to file (certificates/keys) | `SSL_CERT_FILE` |
| Masked | Hidden value (shows **** in logs) | `SSH_PRIVATE_KEY` |
| Protected | Only available on protected branches | `PROD_DEPLOY_KEY` |
| Environment | Bound to specific environment | `STAGING_URL` |

### Protected Branch Strategy

```yaml
# Configure in GitLab Settings > Repository > Protected Branches:
# main branch:
#   - Direct pushes prohibited
#   - Only Merge Request merges allowed
#   - Requires at least 1 reviewer approval
#   - All CI pipeline jobs must pass

# Configure Merge Request template
# .merge_request_template.md:
# ## Change Type
# - [ ] New Feature
# - [ ] Bug Fix
# - [ ] Refactoring
# - [ ] Documentation Update

# ## Testing Verification
# - [ ] Unit tests passed
# - [ ] Integration tests passed
# - [ ] Manual testing completed
```

## Step 5: Advanced Techniques

### Cache Optimization

```yaml
cache:
  key: "${CI_COMMIT_REF_SLUG}"
  paths:
    - node_modules/
    - .npm/
  policy: pull-push  # Default strategy
  # Options: pull / push / pull-push

# Multi-level cache strategy
variables:
  NPM_CACHE_DIR: ".npm"
cache:
  key:
    files:
      - package-lock.json
    prefix: ${CI_COMMIT_REF_SLUG}
  paths:
    - .npm/
```

### Parallel Pipelines

```yaml
# Use parallel to execute tests concurrently
test:parallel:
  stage: test
  image: node:20-alpine
  script:
    - npm run test:parallel
  parallel:
    matrix:
      - SHARD: [1, 2, 3, 4]
  variables:
    TEST_SHARD: $SHARD
```

### Dynamic Environments

```yaml
# Create temporary environments for each MR
deploy-preview:
  stage: deploy-staging
  image: alpine:latest
  script:
    - echo "Deploying to preview-$CI_MERGE_REQUEST_IID"
    - ./scripts/deploy-preview.sh $CI_MERGE_REQUEST_IID
  environment:
    name: preview/$CI_MERGE_REQUEST_IID
    url: https://preview-$CI_MERGE_REQUEST_IID.gitlab.example.com
    on_stop: stop_preview
    stop_action: stop
  rules:
    - if: '$CI_PIPELINE_SOURCE == "merge_request_event"'

stop_preview:
  stage: deploy-staging
  script:
    - docker rm -f preview-$CI_ENVIRONMENT_SLUG
  environment:
    name: preview/$CI_MERGE_REQUEST_IID
    stop_action: stop
  when: manual
```

### Monitoring and Alerting

```bash
# Install Node Exporter on Runner servers
# docker-compose.yml for monitoring
services:
  prometheus:
    image: prom/node-exporter:latest
    ports:
      - "9100:9100"
  
  grafana:
    image: grafana/grafana:latest
    ports:
      - "3001:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=***
```

## Step 6: Backup and Disaster Recovery

### GitLab Data Backup

```bash
# Create a backup
docker exec -t gitlab gitlab-rake gitlab:backup:create

# Automated backup (add to crontab)
0 2 * * * docker exec -t gitlab gitlab-rake gitlab:backup:create CRON=1

# Backup file location
/var/opt/gitlab/backups/1719705600_2026_06_30_16-4-3_gitlab_backup.tar

# Restore a backup
docker exec -t gitlab gitlab-rake gitlab:backup:restore BACKUP=1719705600_2026_06_30_16-4-3
```

### Runner Configuration Backup

```bash
# Backup Runner configuration
cp /srv/gitlab-runner/config/config.toml ~/gitlab-runner-backup/

# Re-register Runner (if configuration is lost)
docker run --rm -v /srv/gitlab-runner/config:/etc/gitlab-runner \
  gitlab/gitlab-runner:latest \
  register \
  --token "YOUR_REGISTRATION_TOKEN" \
  --executor "docker" \
  --docker-image "docker:latest"
```

## Troubleshooting

### Issue 1: Runner Status Shows "Online" But Jobs Won't Run

```bash
# Check Runner logs
docker logs gitlab-runner

# Common causes:
# 1. Runner tags don't match job requirements
# 2. Project hasn't enabled the Runner
# 3. Docker permission issues

# Solution:
# Ensure Runner tags match the rules/tags in .gitlab-ci.yml
# In GitLab, verify: Settings > CI/CD > Runners > Confirm Runner is linked to project
```

### Issue 2: Docker-in-Docker Build Fails

```bash
# Check Docker socket mount
docker inspect gitlab-runner | grep -A 5 "Mounts"

# Ensure privileged mode is enabled
# In config.toml confirm:
# [runners.docker]
#   privileged = true

# If OOM issues, adjust Docker limits
docker run --memory=2g --cpus=2 --rm docker:latest info
```

### Issue 3: SSH Connection Timeout During Deployment

```bash
# Test SSH connectivity
ssh -v -p 22 deploy@example.com

# Common issues:
# 1. Firewall blocking SSH port
# 2. Incorrect SSH key permissions
# 3. Conflicting entries in known_hosts

# Solutions:
chmod 600 ~/.ssh/id_rsa
ssh-keygen -R example.com  # Clear old host key
```

## Hardware Recommendations

| Scale | CPU | RAM | Disk | Use Case |
|-------|-----|-----|------|----------|
| Micro | 2 cores | 4GB | 40GB SSD | Personal projects, 1-2 Runners |
| Small | 4 cores | 8GB | 100GB SSD | Small team, 3-5 Runners |
| Medium | 8 cores | 16GB | 200GB SSD | Medium team, 5-10 Runners |
| Large | 16+ cores | 32GB+ | 500GB+ NVMe | Enterprise, 10+ Runners |

## Summary

Self-hosting a GitLab CI/CD pipeline is a worthwhile investment that achieves a perfect balance between data sovereignty, cost, and flexibility. The key steps are:

1. **Deploy GitLab Server** — Simplify installation with Docker Compose
2. **Configure Runners** — Choose the right Executor mode for your needs
3. **Write CI/CD Configurations** — Leverage stages, rules, and caching to optimize pipelines
4. **Strengthen Security** — Manage keys and access controls properly
5. **Continuously Optimize** — Adjust resource allocation based on project demands

With proper architecture design and best practices, you can run a fully functional, secure, and reliable CI/CD platform on your own VPS — matching the capabilities of GitHub Actions and GitLab.com.
