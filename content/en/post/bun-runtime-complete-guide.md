---
title: "The Complete Bun Runtime Guide: 4x Faster Node.js Alternative with Built-in Tooling"
description: "Bun is the next-generation JavaScript/TypeScript runtime that's 4x faster than Node.js, with a built-in package manager, bundler, and test runner. Master Bun installation, configuration, migration, and production deployment on your VPS."
date: 2026-08-08T10:00:00+08:00
lastmod: 2026-08-08T10:00:00+08:00
slug: "bun-runtime-complete-guide"
tags: ["Bun", "JavaScript", "TypeScript", "Node.js", "VPS Deployment", "Self-Hosted", "Performance", "DevTools"]
categories: ["Deployment Guides"]
draft: false
image: /images/posts/bun-runtime-complete-guide/featured.png
aliases: [/en/post/bun-runtime-complete-guide/]
---

## Why Choose Bun?

In the self-hosting and VPS ecosystem, JavaScript/TypeScript dominates half the landscape. From Next.js websites to API services, from WebSocket servers to AI inference gateways, Node.js has been the default choice. But Node.js has a hidden problem: **it only does one thing—run JavaScript. Everything else requires additional tools.**

Bun changes this landscape. It's an **all-in-one runtime** that merges Node.js, npm, webpack, Vitest, and ESBuild into a single binary. For VPS users, this means:

- **Smaller images**: Docker images shrink from 1GB+ (Node.js) to ~50MB (Bun)
- **Faster builds**: Dependency installation is 20-30x faster than npm
- **Lower costs**: Faster startup means less cloud instance resource waste
- **Simpler toolchain**: One tool replaces five

## Bun vs Node.js Feature Comparison

| Feature | Node.js | Bun | Advantage |
|---------|---------|-----|-----------|
| Runtime Speed | Baseline | **2-4x faster** | JavaScript execution |
| Package Manager | npm (slow) | **Built-in, 20-30x faster** | Dependency installation |
| Bundler | webpack/Vite (separate) | **Built-in bundler** | Zero configuration |
| Test Runner | Jest/Vitest (separate) | **Built-in test** | Ready to use |
| TypeScript Support | Requires tsc compilation | **Native support** | Run directly |
| Docker Image Size | 1GB+ | **~50MB** | Save storage & bandwidth |
| Startup Time | 500ms-2s | **50-100ms** | Cold start optimization |
| Built-in HTTP Server | Requires Express/Nginx | **Built-in serve** | Fewer dependencies |
| Database Clients | Install separately | **Built-in SQLite + Postgres** | Development convenience |

## Installing Bun

### Linux (Ubuntu/Debian)

```bash
# One-line install
curl -fsSL https://bun.sh/install | bash

# Or using apt
curl -fsSL https://bun.sh/install | sudo apt-key add -
echo "deb https://dl.cloudsmith.io/public/bun/bun/deb.deb" | sudo tee /etc/apt/sources.list.d/bun.list
sudo apt update && sudo apt install bun
```

### Docker (Recommended for Production)

```dockerfile
FROM oven/bun:1-alpine

WORKDIR /app

# Copy package.json first to leverage Docker layer caching
COPY package.json bun.lockb ./
RUN bun install --frozen-lockfile

COPY . .

# Production build
RUN bun build ./src/index.ts --target bun --outdir ./dist

EXPOSE 3000
CMD ["bun", "dist/index.js"]
```

Using the Alpine base image, the final image is only **~50MB**, compared to 1GB+ for an equivalent Node.js application.

### macOS

```bash
curl -fsSL https://bun.sh/install | bash
```

### Windows

```powershell
irm https://bun.sh/install | iex
```

## Project Initialization & Package Management

### Creating a New Project

```bash
# Interactive creation (recommended)
bun init

# Or specify manually
bun init --yarn
bun init --npm
bun init --pnpm
```

`bun init` creates a `package.json` and `bun.lockb` (Bun's binary lockfile).

### Installing Dependencies

```bash
# Install a single package
bun add express
bun add typescript @types/express

# Install dev dependencies
bun add -d vitest @testing-library/jest-dom

# Global CLI tools
bun add -g serve ts-node
```

**Speed comparison**: Installing a project with 500 dependencies takes npm 3-5 minutes, while Bun completes it in **5-15 seconds**.

### Lockfile

Bun uses `.lockb` files (binary format), which are smaller and faster than `package-lock.json`. When sharing with a team:

```bash
# Export to npm-compatible format (if needed for CI/CD integration)
bun pm lock --package-json
```

## Native TypeScript Support

Bun can run TypeScript files directly without compilation:

```bash
# Run .ts files directly
bun run src/server.ts

# Or shorthand
bun src/server.ts
```

### tsconfig.json Configuration

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "outDir": "./dist",
    "rootDir": "./src"
  },
  "include": ["src/**/*"],
  "exclude": ["node_modules", "dist"]
}
```

Key configurations:
- `moduleResolution: "bundler"`: Bun uses bundler-style module resolution
- `target: "ES2022"`: Leverages Bun's high-performance implementation of modern JS features

## Built-in Bundler

Bun's built-in bundler can replace Webpack, Rollup, and ESBuild:

### Bundle to Single File

```bash
# Development mode (preserves source, fast)
bun build ./src/index.ts --target bun --out-dir ./dist

# Production mode (optimized compression)
bun build ./src/index.ts --target bun --minify --out-dir ./dist

# Bundle for Node.js compatibility (for non-Bun deployments)
bun build ./src/index.ts --target node --minify --out-dir ./dist
```

### Multi-entry Bundling

```bash
bun build \
  ./src/server.ts \
  ./src/worker.ts \
  --target bun \
  --minify \
  --outdir ./dist
```

### Build Options Explained

| Option | Description | Recommended Value |
|--------|-------------|-------------------|
| `--target` | Target platform: `bun` / `node` / `browser` | `bun` (VPS deployment) |
| `--minify` | Minify code | Enable for production |
| `--outfile` | Output single file | Simple deployments |
| `--external` | Exclude dependencies from bundling | When using node_modules |
| `--define` | Global variable replacement | Environment variable injection |

## Built-in Test Runner

Bun comes with a built-in test framework compatible with Jest API:

### Creating Test Files

```typescript
// src/utils.test.ts
import { describe, it, expect } from "bun:test";
import { calculateTotal } from "./utils";

describe("calculateTotal", () => {
  it("should sum numbers correctly", () => {
    expect(calculateTotal([1, 2, 3])).toBe(6);
  });

  it("should return 0 for empty array", () => {
    expect(calculateTotal([])).toBe(0);
  });
});
```

### Running Tests

```bash
# Basic run
bun test

# Watch mode (recommended for development)
bun test --watch

# Coverage report
bun test --coverage

# Specific file
bun test src/utils.test.ts
```

### Jest-Compatible API

Bun's test framework supports most Jest APIs, making migration easy:

```typescript
// Jest syntax → Bun syntax
import { describe, it, expect, beforeEach, jest } from "bun:test";

// Mock functions
const mockFn = jest.fn();
mockFn(1, 2);
expect(mockFn).toHaveBeenCalledWith(1, 2);

// Mock modules
jest.mock("./api", () => ({
  fetchUser: () => Promise.resolve({ id: 1, name: "Test" }),
}));
```

## Database Integration

Bun has built-in native support for common databases:

### SQLite (Zero Configuration)

```typescript
import { Database } from "bun:sqlite";

const db = new Database(":memory:");
db.run("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)");
db.run("INSERT INTO users (name) VALUES (?)", "Alice");
const users = db.query("SELECT * FROM users").all();
```

### PostgreSQL

```typescript
import { Client } from "pg";

const client = new Client({
  connectionString: process.env.DATABASE_URL,
});

await client.connect();
const result = await client.query("SELECT * FROM users");
await client.end();
```

### Redis

```typescript
// Use ioredis or other clients
import Redis from "ioredis";

const redis = new Redis(process.env.REDIS_URL);
await redis.set("key", "value");
const value = await redis.get("key");
```

## Real-World Project: Deploying a Full-Stack App

### Project Structure

```
my-app/
├── src/
│   ├── index.ts          # Entry point
│   ├── routes/           # API routes
│   │   ├── users.ts
│   │   └── health.ts
│   └── utils/
│       ├── db.ts
│       └── auth.ts
├── tests/
│   └── index.test.ts
├── package.json
├── bun.lockb
├── tsconfig.json
└── Dockerfile
```

### Entry File

```typescript
// src/index.ts
import { Hono } from "hono";
import { logger } from "hono/logger";
import { bearerAuth } from "hono/bearer-auth";
import { getUser, createUser } from "./routes/users";
import { healthCheck } from "./routes/health";

const app = new Hono<{ Bindings: Env }>();

app.use("*", logger());

// Health check (no auth required)
app.get("/health", healthCheck);

// API routes (requires auth)
app.use("/api/*", bearerAuth({ token: process.env.API_TOKEN }));
app.get("/api/users", getUser);
app.post("/api/users", createUser);

// Start server
export default {
  port: parseInt(process.env.PORT || "3000"),
  fetch: app.fetch,
};
```

### Dockerfile (Production Optimized)

```dockerfile
# Build stage
FROM oven/bun:1-alpine AS builder
WORKDIR /app
COPY package.json bun.lockb ./
RUN bun install --frozen-lockfile
COPY . .
RUN bun build ./src/index.ts --target node --minify --outdir ./dist

# Runtime stage
FROM oven/bun:1-alpine AS runner
WORKDIR /app
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./package.json

ENV NODE_ENV=production
ENV PORT=3000

EXPOSE 3000
CMD ["bun", "dist/index.js"]
```

### Build & Deploy

```bash
# Local testing
bun test
bun run src/index.ts

# Build
bun build ./src/index.ts --target node --minify --outdir ./dist

# Docker build (only 50MB)
docker build -t my-app:bun .
docker run -p 3000:3000 -e API_TOKEN=secret my-app:bun
```

## Migrating from Node.js to Bun

### Compatibility Check

Bun strives for Node.js API compatibility, but there are some differences to be aware of:

```typescript
// ✅ Compatible APIs
import fs from "fs";          // bun:fs
import path from "path";      // bun:path
import crypto from "crypto";  // bun:crypto
import http from "http";      // bun:http

// ⚠️ APIs to check
import { exec } from "child_process";  // bun:child_process (slightly different API)
import { Worker } from "worker_threads"; // bun:worker (different Worker model)
```

### Migration Steps

```bash
# 1. Install Bun
curl -fsSL https://bun.sh/install | bash

# 2. Replace package.json scripts
# Before (Node.js):
# "start": "node dist/index.js"
# "dev": "ts-node src/index.ts"
# "build": "tsc"

# After (Bun):
# "start": "bun dist/index.js"
# "dev": "bun run src/index.ts"
# "build": "bun build ./src/index.ts --minify --outdir ./dist"

# 3. Replace lockfile
rm package-lock.json
bun install

# 4. Run tests
bun test

# 5. Test run
bun run src/index.ts
```

### Common Issues & Solutions

| Issue | Cause | Solution |
|-------|-------|----------|
| `import.meta` undefined | Bundling config issue | Ensure `moduleResolution: "bundler"` |
| WebSocket connection failed | Server config | Use Bun's built-in `serve` or configure reverse proxy |
| Some npm packages incompatible | C++ native modules | Check for Bun-compatible versions or use `--no-verify` |
| Path resolution differences | Windows vs Unix | Use `import.meta.dir` instead of `__dirname` |

## Performance Benchmarks

### Startup Speed Comparison

| Framework | Cold Start Time | Memory Usage |
|-----------|-----------------|--------------|
| Node.js + Express | 800ms | ~60MB |
| Fastify (Node) | 400ms | ~45MB |
| **Bun + Hono** | **50ms** | **~15MB** |

### Request Processing Speed

```
AB Test: 1000 requests, 100 concurrent

Node.js + Express:    12,500 req/s
Bun + Hono:          48,000 req/s    ← 3.8x faster
```

### Memory Efficiency

Bun uses a streamlined V8 engine with more aggressive memory management:

```typescript
// Memory limit test
const arr = new Array(10_000_000).fill(1);
// Node.js: ~80MB
// Bun:     ~60MB    ← 25% savings
```

For VPS users, this means **the same hardware can handle more requests**, directly reducing cloud service costs.

## Production Deployment Best Practices

### 1. Managing Processes with systemd

```ini
# /etc/systemd/system/my-bun-app.service
[Unit]
Description=My Bun Application
After=network.target

[Service]
Type=simple
User=vpsuser
WorkingDirectory=/opt/my-app
ExecStart=/home/vpsuser/.bun/bin/bun run dist/index.js
Environment=NODE_ENV=production
Environment=PORT=3000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable my-bun-app
sudo systemctl start my-bun-app
sudo systemctl status my-bun-app
```

### 2. Nginx Reverse Proxy

```nginx
server {
    listen 80;
    server_name api.example.com;

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Timeout settings (WebSocket needs longer timeout)
        proxy_connect_timeout 7d;
        proxy_send_timeout 7d;
        proxy_read_timeout 7d;
    }
}
```

### 3. Monitoring & Health Checks

```typescript
// Add health check endpoint
app.get("/health", (c) => {
  return c.json({
    status: "ok",
    timestamp: new Date().toISOString(),
    uptime: process.uptime(),
    memory: {
      rss: formatBytes(process.memoryUsage().rss),
      heapUsed: formatBytes(process.memoryUsage().heapUsed),
    },
  });
});

function formatBytes(bytes: number): string {
  const units = ["B", "KB", "MB", "GB"];
  let i = 0;
  while (bytes >= 1024 && i < units.length - 1) {
    bytes /= 1024;
    i++;
  }
  return `${bytes.toFixed(2)} ${units[i]}`;
}
```

## Summary

Bun represents a significant upgrade in the JavaScript/TypeScript ecosystem, solving Node.js toolchain fragmentation through **integrated design**. For VPS self-hosting users, Bun delivers tangible benefits:

**Core Benefits:**

1. **Faster development experience**: 20-30x dependency installation speed, zero-configuration TypeScript
2. **Lower operational costs**: 50MB Docker images vs 1GB+, saving storage and bandwidth
3. **Higher performance**: 3-4x request processing speed, same VPS handles more traffic
4. **Simpler toolchain**: One Bun replaces npm + webpack + Vitest + tsc

**Use Cases:**

- ✅ New Node.js/Bun projects (highly recommended)
- ✅ Performance-critical API services
- ✅ Resource-constrained VPS (under 1GB RAM)
- ✅ Serverless functions requiring fast cold starts
- ⚠️ Migrating existing Node.js projects (requires compatibility testing)
- ❌ Projects relying heavily on C++ native modules (verify each one)

**Next Steps:**

- [ ] Try Bun in a new project
- [ ] Migrate existing Node.js services to Bun
- [ ] Optimize Docker images, switch from Node.js to Bun Alpine
- [ ] Configure CI/CD support for Bun
- [ ] Monitor performance metrics, quantify migration benefits

---

*Let Bun be the accelerator for your VPS operations! 🚀*
