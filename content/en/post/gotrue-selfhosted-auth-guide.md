---
title: "Self-Hosting GoTrue (Supabase Auth): Complete Authentication System Guide"
description: "Deploy GoTrue authentication server on your VPS from scratch — supporting OAuth, email verification, MFA, and enterprise-grade features with full data control."
date: 2026-07-06T10:00:00+08:00
lastmod: 2026-07-06T10:00:00+08:00
slug: "gotrue-selfhosted-auth-guide"
tags: ["GoTrue", "Supabase", "Authentication", "OAuth", "Self-Hosting", "Docker", "User Management", "Security"]
categories: ["Deployment Guides"]
draft: false
image: /images/posts/gotrue-selfhosted-auth-guide/featured.png
aliases: [/en/post/gotrue-selfhosted-auth-guide/]
---

## Why Self-Host Authentication?

When building self-hosted applications, user authentication is one of the most fundamental yet often overlooked components. Most developers either reinvent the wheel—hand-rolling JWT validation and session management—or rely on third-party services like Firebase Auth, Auth0, or Supabase Auth. But these services have limitations:

- **Firebase Auth**: Heavy vendor lock-in, limited customization
- **Auth0**: Free tier is restrictive, pricing scales quickly with users
- **Supabase Auth**: Convenient but data lives on Supabase's cloud, not fully under your control

**GoTrue** is the open-source core engine behind Supabase Auth, written in Go and deployable via Docker. It provides complete authentication functionality while keeping everything on your infrastructure.

## GoTrue Core Features

| Feature | Description |
|---------|-------------|
| JWT Token Management | Issue, verify, and refresh access and refresh tokens |
| Email/Password Auth | Registration, login, and password reset via email |
| Magic Links | Passwordless login via email verification links |
| OAuth Social Login | 20+ providers including Google, GitHub, GitLab, Discord |
| MFA (Multi-Factor Auth) | TOTP, SMS, and other second-factor verification methods |
| User Management API | RESTful API for creating, updating, and deleting users |
| Role-Based Access | Basic RBAC support through JWT claims |
| SAML/SSO | Enterprise-grade single sign-on support |

## Architecture Overview

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   Client     │────▶│  GoTrue      │────▶│   PostgreSQL│
│ (Web/Mobile) │◀────│  Auth Server │◀────│   Database  │
└─────────────┘     └──────────────┘     └─────────────┘
                          │
                          ▼
                   ┌──────────────┐
                   │   SMTP       │
                   │   Server     │
                   └──────────────┘
```

GoTrue relies on three core components:
1. **GoTrue Service**: The authentication logic engine
2. **PostgreSQL**: Stores user data and session information
3. **SMTP Server**: Sends verification emails

## Complete Deployment Guide

### Step 1: Prepare the Docker Compose File

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  gotrue:
    image: ghcr.io/supabase/gotrue:v2.158.1
    container_name: gotrue
    restart: unless-stopped
    ports:
      - "9999:9999"
    environment:
      # GoTrue database driver
      GOTRUE_DB_DRIVER: postgres
      GOTRUE_DB_DATABASE_URL: "postgresql://supabase_gotrue:***@db:5432/postgres"
      
      # JWT configuration
      GOTRUE_JWT_ADMIN_ROLES: "admin"
      GOTRUE_JWT_AUD: "authenticated"
      GOTRUE_JWT_EXP: "3600"
      GOTRUE_JWT_SECRET: "your-super-secret-jwt-token-with-at-least-32-characters-long"
      
      # API configuration
      GOTRUE_API_HOST: "0.0.0.0"
      GOTRUE_API_PORT: 9999
      GOTRUE_API_RATE_LIMIT_HEADER: "X-Forwarded-For"
      GOTRUE_API_RATE_LIMIT: "100"
      
      # SMTP email configuration
      GOTRUE_MAILER_AUTOCONFIRM: "false"
      GOTRUE_SMTP_HOST: "smtp.your-email-provider.com"
      GOTRUE_SMTP_PORT: "587"
      GOTRUE_SMTP_USER: "your-smtp-user"
      GOTRUE_SMTP_PASS: "your-smtp-password"
      GOTRUE_SMTP_ADMIN_EMAIL: "admin@yourdomain.com"
      GOTRUE_SMTP_SENDER_NAME: "Your App Name"
      
      # Site URL
      GOTRUE_SITE_URL: "https://auth.yourdomain.com"
      GOTRUE_URI_ALLOW_UPDATES: "true"
      
      # OAuth configuration (enable as needed)
      GOTRUE_EXTERNAL_GITHUB_ENABLED: "true"
      GOTRUE_EXTERNAL_GITHUB_CLIENT_ID: "your-github-oauth-client-id"
      GOTRUE_EXTERNAL_GITHUB_SECRET: "your-github-oauth-client-secret"
      
      GOTRUE_EXTERNAL_GOOGLE_ENABLED: "true"
      GOTRUE_EXTERNAL_GOOGLE_CLIENT_ID: "your-google-oauth-client-id"
      GOTRUE_EXTERNAL_GOOGLE_SECRET: "your-google-oauth-client-secret"
      
      # Password policy
      GOTRUE_PASSWORD_MIN_LENGTH: 8
      GOTRUE_ALLOW_SIGNUP_WITHOUT_EMAIL_VERIFICATION: "false"
      
      # CORS
      GOTRUE_EXTERNAL_REDIRECT_URLS: "https://yourdomain.com,https://app.yourdomain.com"
      
      # Email template paths
      GOTRUE_MAILER_URLPATHS_INVITE: "/auth/callback"
      GOTRUE_MAILER_URLPATHS_CONFIRMATION: "/auth/callback"
      GOTRUE_MAILER_URLPATHS_RECOVERY: "/auth/callback"
      GOTRUE_MAILER_URLPATHS_EMAIL_CHANGE: "/auth/callback"

    depends_on:
      db:
        condition: service_healthy

  db:
    image: postgres:16-alpine
    container_name: gotrue-db
    restart: unless-stopped
    ports:
      - "5433:5432"
    environment:
      POSTGRES_DB: supabase_gotrue
      POSTGRES_USER: supabase_gotrue
      POSTGRES_PASSWORD: supabase_gotrue_password
      POSTGRES_INITDB_ARGS: "--auth-host=scram-sha-256"
    volumes:
      - gotrue_db_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U supabase_gotrue -d supabase_gotrue"]
      interval: 5s
      timeout: 5s
      retries: 5

volumes:
  gotrue_db_data:
    driver: local
```

### Step 2: Configure Environment Variables

In production, **never** hardcode sensitive information in docker-compose.yml. Use a `.env` file instead:

```bash
# .env
GOTRUE_JWT_SECRET=$(openssl rand -base64 32)
GOTRUE_DB_DATABASE_URL=postgresql://user:password@db:5432/dbname
GOTRUE_SMTP_PASS=your-smtp-password
GOTRUE_EXTERNAL_GITHUB_SECRET=your-github-client-secret

```yaml
environment:
  GOTRUE_JWT_SECRET: ${GOTRUE_JWT_SECRET}
  GOTRUE_SMTP_PASS: ${GOTRUE_SMTP_PASS}
```

### Step 3: Start the Services

```bash
docker compose up -d
```

Wait for the database to initialize (about 30 seconds), then verify the service:

```bash
# Check if GoTrue is running
curl http://localhost:9999/health

# Expected response: {"status":"OK"}
```

## Configuring OAuth Social Login

### GitHub OAuth Setup

1. Go to [GitHub Developer Settings](https://github.com/settings/developers)
2. Create a new OAuth App
3. Set Authorization callback URL to `https://auth.yourdomain.com/auth/callback`
4. Get your Client ID and Client Secret

```yaml
environment:
  GOTRUE_EXTERNAL_GITHUB_ENABLED: "true"
  GOTRUE_EXTERNAL_GITHUB_CLIENT_ID: "${GITHUB_CLIENT_ID}"
  GOTRUE_EXTERNAL_GITHUB_SECRET: "${GITHUB_CLIENT_SECRET}"
  GOTRUE_EXTERNAL_GITHUB_REDIRECT_URI: "https://auth.yourdomain.com/auth/callback"
```

### Google OAuth Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create OAuth 2.0 credentials
3. Add authorized redirect URI: `https://auth.yourdomain.com/auth/callback`
4. Get your Client ID and Client Secret

```yaml
environment:
  GOTRUE_EXTERNAL_GOOGLE_ENABLED: "true"
  GOTRUE_EXTERNAL_GOOGLE_CLIENT_ID: "${GOOGLE_CLIENT_ID}"
  GOTRUE_EXTERNAL_GOOGLE_SECRET: "${GOOGLE_CLIENT_SECRET}"
  GOTRUE_EXTERNAL_GOOGLE_REDIRECT_URI: "https://auth.yourdomain.com/auth/callback"
```

## Integrating with Frontend Applications

### Using GoTrue JS SDK

```bash
npm install @supabase/gotrue-js
```

```javascript
import { GoTrueClient } from '@supabase/gotrue-js';

const client = new GoTrueClient({
  url: 'http://localhost:9999',
});

// Email registration
async function signUp(email, password) {
  const { data, error } = await client.signUp({
    email,
    password,
  });
  if (error) throw error;
  return data;
}

// Email/password login
async function signIn(email, password) {
  const { data, error } = await client.signInWithPassword({
    email,
    password,
  });
  if (error) throw error;
  return data;
}

// Refresh session using refresh token
async function refreshSession(refreshToken) {
  const { data, error } = await client.refreshSession({ refreshToken });
  if (error) throw error;
  return data;
}

// Sign out
async function signOut() {
  await client.signOut();
}
```

### Backend API Integration Example (Node.js)

```javascript
const express = require('express');
const jwt = require('jsonwebtoken');

const app = express();
const GOTRUE_API_URL = 'http://localhost:9999';
const JWT_SECRET = process.env.GOTRUE_JWT_SECRET;

// Middleware: Verify JWT token
function authenticate(req, res, next) {
  const token = req.headers.authorization?.split(' ')[1];
  if (!token) {
    return res.status(401).json({ error: 'Unauthorized' });
  }
  
  try {
    const decoded = jwt.verify(token, JWT_SECRET);
    req.user = decoded;
    next();
  } catch (err) {
    return res.status(401).json({ error: 'Invalid token' });
  }
}

// Protected API endpoint
app.get('/api/protected', authenticate, (req, res) => {
  res.json({ 
    message: 'Authentication successful', 
    userId: req.user.sub,
    email: req.user.email 
  });
});

app.listen(3000);
```

## User Management

### Using the Admin API

GoTrue provides a complete user management API. Use an admin token to perform administrative operations:

```bash
# List all users
curl -X GET "http://localhost:9999/admin/users" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"

# Create a user
curl -X POST "http://localhost:9999/admin/users" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "newuser@example.com",
    "password": "securepassword123",
    "app_metadata": {"role": "user"},
    "user_metadata": {"name": "New User"}
  }'

# Delete a user
curl -X DELETE "http://localhost:9999/admin/users/{user_id}" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"
```

### Admin Token Generation

An Admin Token is a JWT with the `admin` role:

```bash
# Generate using jwt-cli (requires installation)
jwt sign -s "your-secret" -a '{"role":"admin"}'

# Or generate in code
const adminToken = jwt.sign(
  { role: 'admin', aud: 'authenticated' },
  process.env.GOTRUE_JWT_SECRET,
  { expiresIn: '1h' }
);
```

## Email Configuration Details

### Using Mailgun

```yaml
environment:
  GOTRUE_SMTP_HOST: "smtp.mailgun.org"
  GOTRUE_SMTP_PORT: "587"
  GOTRUE_SMTP_USER: "postmaster@yourdomain.mailgun.org"
  GOTRUE_SMTP_PASS: "your-mailgun-api-key"
  GOTRUE_SMTP_ADMIN_EMAIL: "admin@yourdomain.com"
  GOTRUE_SMTP_SENDER_NAME: "My App"
```

### Using SendGrid

```yaml
environment:
  GOTRUE_SMTP_HOST: "smtp.sendgrid.net"
  GOTRUE_SMTP_PORT: "587"
  GOTRUE_SMTP_USER: "apikey"
  GOTRUE_SMTP_PASS: "your-sendgrid-api-key"
  GOTRUE_SMTP_ADMIN_EMAIL: "admin@yourdomain.com"
  GOTRUE_SMTP_SENDER_NAME: "My App"
```

### Using Local Postfix

For development/testing, you can use local Postfix:

```yaml
services:
  postfix:
    image: tvial/docker-mailserver:latest
    container_name: postfix
    ports:
      - "25:25"
    environment:
      - MAIL_HOSTNAME=mail.local

  gotrue:
    environment:
      GOTRUE_SMTP_HOST: "postfix"
      GOTRUE_SMTP_PORT: "25"
      GOTRUE_SMTP_USER: ""
      GOTRUE_SMTP_PASS: ""
      GOTRUE_MAILER_AUTOCONFIRM: "true"  # Auto-confirm in dev
```

## Customizing Email Templates

GoTrue supports custom email templates via the API. Create a `template.json`:

```json
{
  "invite": {
    "subject": "Invitation to join {{ .SiteURL }}",
    "body": "<p>Hello {{ .Email }},</p><p>Click the link below to confirm your account:</p><p><a href=\"{{ .ConfirmationURL }}\">Confirm Registration</a></p>"
  },
  "confirmation": {
    "subject": "Confirm your email",
    "body": "<p>Please click the link below to confirm your email address:</p><p><a href=\"{{ .ConfirmationURL }}\">Confirm Email</a></p>"
  },
  "recovery": {
    "subject": "Reset your password",
    "body": "<p>Please click the link below to reset your password:</p><p><a href=\"{{ .RecoveryURL }}\">Reset Password</a></p>"
  },
  "email_change": {
    "subject": "Confirm email change",
    "body": "<p>Please click the link below to confirm your email change:</p><p><a href=\"{{ .EmailChangeConfirmUrl }}\">Confirm Change</a></p>"
  }
}
```

Then upload templates via the API:

```bash
curl -X PUT "http://localhost:9999/admin/settings" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "mailer": {
      "templates": {
        "invite": {"subject": "...", "body": "..."},
        "confirmation": {"subject": "...", "body": "..."}
      }
    }
  }'
```

## Production Best Practices

### 1. Use a Reverse Proxy

In production, access GoTrue through Nginx or Caddy reverse proxy:

```nginx
server {
    listen 443 ssl http2;
    server_name auth.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/auth.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/auth.yourdomain.com/privkey.pem;

    location / {
        proxy_pass http://localhost:9999;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### 2. Enable HTTPS

GoTrue does not handle TLS directly. All HTTPS termination should happen at the reverse proxy level.

### 3. Database Backups

```bash
# Automated daily backup
0 2 * * * docker exec gotrue-db pg_dump -U supabase_gotrue supabase_gotrue | gzip > /backups/gotrue_$(date +\%Y\%m\%d).sql.gz
```

### 4. Resource Limits

```yaml
services:
  gotrue:
    deploy:
      resources:
        limits:
          cpus: '1.0'
          memory: 512M
        reservations:
          cpus: '0.25'
          memory: 128M
```

### 5. Health Checks and Monitoring

```yaml
services:
  gotrue:
    healthcheck:
      test: ["CMD", "wget", "--spider", "-q", "http://localhost:9999/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s
```

### 6. Rate Limiting

GoTrue has built-in rate limiting, but add a layer at the reverse proxy too:

```nginx
limit_req_zone $binary_remote_addr zone=auth_limit:10m rate=10r/s;

location /auth/signup {
    limit_req zone=auth_limit burst=20 nodelay;
    proxy_pass http://localhost:9999;
}
```

## Frequently Asked Questions

### Q1: Not receiving verification emails?

1. Check SMTP configuration is correct
2. Review GoTrue logs: `docker logs gotrue`
3. Ensure `GOTRUE_MAILER_AUTOCONFIRM` is set to `"false"` in production
4. Verify firewall isn't blocking outbound SMTP connections

### Q2: OAuth callback failing?

1. Confirm the callback URL matches exactly (including trailing slash)
2. Check the OAuth app's redirect URI settings
3. Verify `GOTRUE_EXTERNAL_REDIRECT_URLS` includes your domain

### Q3: How to migrate existing users to GoTrue?

```bash
# Bulk import users
curl -X POST "http://localhost:9999/admin/users" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password_hash": "$2b$12$...",
    "email_verified": true,
    "phone_verified": false
  }'
```

Import users with bcrypt-hashed passwords, never with plaintext passwords.

### Q4: What is the relationship between GoTrue and Supabase?

GoTrue is the underlying engine of Supabase Auth. Supabase adds on top of GoTrue:
- Supabase CLI tooling
- Management dashboard
- Integration with other Supabase services (Realtime, Storage)
- Additional admin APIs

If you only need authentication, GoTrue is the more lightweight and independent choice.

## Comparison with Other Auth Solutions

| Feature | GoTrue | Firebase Auth | Auth0 | Keycloak |
|---------|--------|--------------|-------|----------|
| Deployment Complexity | ⭐⭐ Low | ⭐ Zero | ⭐ Zero | ⭐⭐⭐⭐ High |
| Customization Level | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| OAuth Support | ✅ Rich | ✅ Basic | ✅ Rich | ✅ Rich |
| MFA | ✅ Supported | ✅ Supported | ✅ Supported | ✅ Supported |
| Resource Usage | ~100MB | N/A | N/A | ~1GB+ |
| Learning Curve | Moderate | Low | Moderate | Steep |
| Community Activity | High | Very High | High | High |

## Summary

GoTrue provides a powerful, flexible, and lightweight authentication solution for self-hosted applications. It inherits all the core features of Supabase Auth while giving you complete control over user data and infrastructure.

**Key Takeaways:**
- Deploy with Docker in minutes, backed by PostgreSQL for persistence
- Full OAuth social login ecosystem support
- User management via Admin API for programmatic and batch operations
- Production environments must configure HTTPS, backups, and monitoring
- Seamless frontend integration with the JS SDK for excellent developer experience

By self-hosting your authentication service, you not only save on third-party service costs but, more importantly, gain complete data control—which is crucial in scenarios with strict compliance requirements.
