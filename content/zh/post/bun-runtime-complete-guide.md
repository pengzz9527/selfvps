---
title: "Bun 运行时完全指南：4 倍速替代 Node.js，一站式搞定构建与测试"
description: "Bun 是新一代 JavaScript/TypeScript 运行时，比 Node.js 快 4 倍，内置包管理器、打包工具和测试框架。本指南带你从零掌握 Bun 的安装、配置、迁移与生产部署，让你的 VPS 开发效率翻倍。"
date: 2026-08-08T10:00:00+08:00
lastmod: 2026-08-08T10:00:00+08:00
slug: "bun-runtime-complete-guide"
tags: ["Bun", "JavaScript", "TypeScript", "Node.js", "VPS部署", "自托管", "性能优化", "开发工具"]
categories: ["部署教程"]
draft: false
image: /images/posts/bun-runtime-complete-guide/featured.png
aliases: [/zh/post/bun-runtime-complete-guide/]
---

## 为什么选择 Bun？

在 VPS 自托管领域，JavaScript/TypeScript 生态占据了半壁江山。从 Next.js 网站到 FastAPI 替代品，从 WebSocket 服务到 AI 推理网关，Node.js 一直是默认选择。但 Node.js 有个隐性问题：**它只做一件事——运行 JavaScript，其他一切都需要额外工具**。

Bun 的出现改变了这个格局。它是一个**一体化运行时**，把 Node.js、npm、webpack、Vitest、ESBuild 等多个工具合并成了一个二进制文件。对于 VPS 用户来说，这意味着：

- **更小的镜像**：Docker 镜像从 Node.js 的 1GB+ 降到 Bun 的 50MB
- **更快的构建**：依赖安装速度是 npm 的 20-30 倍
- **更低的成本**：更快的启动意味着更少的云实例资源浪费
- **更简单的工具链**：一个工具替代五个

## Bun 核心优势对比

| 特性 | Node.js | Bun | 优势 |
|------|---------|-----|------|
| 运行时速度 | 基准 | **2-4x 更快** | JavaScript 执行 |
| 包管理器 | npm（慢） | **内置，20-30x 快** | 依赖安装 |
| 打包工具 | webpack/Vite（独立） | **内置 bundler** | 零配置 |
| 测试框架 | Jest/Vitest（独立） | **内置 test** | 开箱即用 |
| TypeScript 支持 | 需要 tsc 编译 | **原生支持** | 直接运行 |
| Docker 镜像大小 | 1GB+ | **~50MB** | 节省存储和带宽 |
| 启动时间 | 500ms-2s | **50-100ms** | 冷启动优化 |
| 内置 HTTP 服务器 | 需要 Express/Nginx | **内置 serve** | 减少依赖 |
| 数据库客户端 | 需要独立安装 | **内置 SQLite + Postgres** | 开发便利 |

## 安装 Bun

### Linux（Ubuntu/Debian）

```bash
# 一键安装
curl -fsSL https://bun.sh/install | bash

# 或者使用 apt
curl -fsSL https://bun.sh/install | sudo apt-key add -
echo "deb https://dl.cloudsmith.io/public/bun/bun/deb.deb" | sudo tee /etc/apt/sources.list.d/bun.list
sudo apt update && sudo apt install bun
```

### Docker 方式（推荐用于生产）

```dockerfile
FROM oven/bun:1-alpine

WORKDIR /app

# 先复制 package.json 利用 Docker 缓存层
COPY package.json bun.lockb ./
RUN bun install --frozen-lockfile

COPY . .

# 生产构建
RUN bun build ./src/index.ts --target bun --outdir ./dist

EXPOSE 3000
CMD ["bun", "dist/index.js"]
```

使用 Alpine 基础镜像，最终镜像大小仅 **~50MB**，而同等 Node.js 应用通常需要 1GB+。

### macOS

```bash
curl -fsSL https://bun.sh/install | bash
```

### Windows

```powershell
irm https://bun.sh/install | iex
```

## 项目初始化与包管理

### 创建新项目

```bash
# 交互式创建（推荐）
bun init

# 或手动指定
bun init --yarn
bun init --npm
bun init --pnpm
```

`bun init` 会创建一个 `package.json` 和 `bun.lockb`（Bun 的二进制锁文件）。

### 安装依赖

```bash
# 安装单个包
bun add express
bun add typescript @types/express

# 安装开发依赖
bun add -d vitest @testing-library/jest-dom

# 全局安装 CLI 工具
bun add -g serve ts-node
```

**速度对比**：安装一个包含 500 个依赖的项目，npm 需要 3-5 分钟，而 Bun 只需 **5-15 秒**。

### 锁定文件

Bun 使用 `.lockb` 文件（二进制格式），比 `package-lock.json` 更小、更快。在团队中共享时，建议：

```bash
# 导出为 npm 兼容格式（如需与 CI/CD 集成）
bun pm lock --package-json
```

## TypeScript 原生支持

Bun 无需编译即可直接运行 TypeScript 文件：

```bash
# 直接运行 .ts 文件
bun run src/server.ts

# 或简写
bun src/server.ts
```

### tsconfig.json 配置

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

关键配置：
- `moduleResolution: "bundler"`：Bun 使用打包器风格的模块解析
- `target: "ES2022"`：利用 Bun 对现代 JS 特性的高性能实现

## 内置打包工具

Bun 内置的打包器可以替代 Webpack、Rollup 和 ESBuild：

### 打包为单文件

```bash
# 开发模式（保留源码，快速）
bun build ./src/index.ts --target bun --out-dir ./dist

# 生产模式（优化压缩）
bun build ./src/index.ts --target bun --minify --out-dir ./dist

# 打包为 Node.js 兼容格式（用于部署到非 Bun 环境）
bun build ./src/index.ts --target node --minify --out-dir ./dist
```

### 多入口打包

```bash
bun build \
  ./src/server.ts \
  ./src/worker.ts \
  --target bun \
  --minify \
  --outdir ./dist
```

### 打包选项详解

| 选项 | 说明 | 推荐值 |
|------|------|--------|
| `--target` | 目标平台：`bun` / `node` / `browser` | `bun`（VPS 部署） |
| `--minify` | 压缩代码 | 生产环境启用 |
| `--outfile` | 输出单个文件 | 简单部署 |
| `--external` | 排除打包的依赖 | 使用 node_modules 时 |
| `--define` | 全局变量替换 | 环境变量注入 |

## 内置测试框架

Bun 自带测试框架，兼容 Jest API：

### 创建测试文件

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

### 运行测试

```bash
# 基本运行
bun test

# 监听模式（开发时推荐）
bun test --watch

# 覆盖率报告
bun test --coverage

# 指定文件
bun test src/utils.test.ts
```

### Jest 兼容 API

Bun 测试框架支持大部分 Jest API，迁移成本低：

```typescript
// Jest 写法 → Bun 写法
import { describe, it, expect, beforeEach, jest } from "bun:test";

// mock 函数
const mockFn = jest.fn();
mockFn(1, 2);
expect(mockFn).toHaveBeenCalledWith(1, 2);

// mock 模块
jest.mock("./api", () => ({
  fetchUser: () => Promise.resolve({ id: 1, name: "Test" }),
}));
```

## 数据库集成

Bun 内置了对常用数据库的原生支持：

### SQLite（零配置）

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
// 使用 ioredis 或其他客户端
import Redis from "ioredis";

const redis = new Redis(process.env.REDIS_URL);
await redis.set("key", "value");
const value = await redis.get("key");
```

## 实际项目：部署一个全栈应用

### 项目结构

```
my-app/
├── src/
│   ├── index.ts          # 入口
│   ├── routes/           # API 路由
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

### 入口文件

```typescript
// src/index.ts
import { Hono } from "hono";
import { logger } from "hono/logger";
import { bearerAuth } from "hono/bearer-auth";
import { getUser, createUser } from "./routes/users";
import { healthCheck } from "./routes/health";

const app = new Hono<{ Bindings: Env }>();

app.use("*", logger());

// 健康检查（无需认证）
app.get("/health", healthCheck);

// API 路由（需要认证）
app.use("/api/*", bearerAuth({ token: process.env.API_TOKEN }));
app.get("/api/users", getUser);
app.post("/api/users", createUser);

// 启动服务器
export default {
  port: parseInt(process.env.PORT || "3000"),
  fetch: app.fetch,
};
```

### Dockerfile（生产优化）

```dockerfile
# 构建阶段
FROM oven/bun:1-alpine AS builder
WORKDIR /app
COPY package.json bun.lockb ./
RUN bun install --frozen-lockfile
COPY . .
RUN bun build ./src/index.ts --target node --minify --outdir ./dist

# 运行阶段
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

### 构建与部署

```bash
# 本地测试
bun test
bun run src/index.ts

# 构建
bun build ./src/index.ts --target node --minify --outdir ./dist

# Docker 构建（仅 50MB）
docker build -t my-app:bun .
docker run -p 3000:3000 -e API_TOKEN=secret my-app:bun
```

## 从 Node.js 迁移到 Bun

### 兼容性检查

Bun 尽力兼容 Node.js API，但仍有一些差异需要注意：

```typescript
// ✅ 兼容的 API
import fs from "fs";          // bun:fs
import path from "path";      // bun:path
import crypto from "crypto";  // bun:crypto
import http from "http";      // bun:http

// ⚠️ 需要检查的 API
import { exec } from "child_process";  // bun:child_process（API 略有不同）
import { Worker } from "worker_threads"; // bun:worker（不同的 Worker 模型）
```

### 迁移步骤

```bash
# 1. 安装 Bun
curl -fsSL https://bun.sh/install | bash

# 2. 替换 package.json 中的 scripts
# Before (Node.js):
# "start": "node dist/index.js"
# "dev": "ts-node src/index.ts"
# "build": "tsc"

# After (Bun):
# "start": "bun dist/index.js"
# "dev": "bun run src/index.ts"
# "build": "bun build ./src/index.ts --minify --outdir ./dist"

# 3. 替换锁文件
rm package-lock.json
bun install

# 4. 运行测试
bun test

# 5. 测试运行
bun run src/index.ts
```

### 常见问题与解决

| 问题 | 原因 | 解决方案 |
|------|------|----------|
| `import.meta` 未定义 | 打包配置问题 | 确保 `moduleResolution: "bundler"` |
| WebSocket 连接失败 | 服务器配置 | 使用 Bun 内置的 `serve` 或配置反向代理 |
| 某些 npm 包不兼容 | C++ 原生模块 | 检查是否有 Bun 兼容版本或使用 `--no-verify` |
| 路径解析差异 | Windows vs Unix | 使用 `import.meta.dir` 代替 `__dirname` |

## 性能基准测试

### 启动速度对比

| 框架 | 冷启动时间 | 内存占用 |
|------|-----------|---------|
| Node.js + Express | 800ms | ~60MB |
| Fastify (Node) | 400ms | ~45MB |
| **Bun + Hono** | **50ms** | **~15MB** |

### 请求处理速度

```
AB 测试：1000 请求，100 并发

Node.js + Express:    12,500 req/s
Bun + Hono:          48,000 req/s    ← 3.8x 更快
```

### 内存效率

Bun 使用 V8 引擎的精简版本，内存管理更激进：

```typescript
// 内存限制测试
const arr = new Array(10_000_000).fill(1);
// Node.js: ~80MB
// Bun:     ~60MB    ← 节省 25%
```

对于 VPS 用户，这意味着**同样的硬件可以承载更多请求**，直接降低云服务成本。

## 生产部署最佳实践

### 1. 使用 systemd 管理进程

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

### 2. Nginx 反向代理

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
        
        # 超时设置（WebSocket 需要较长超时）
        proxy_connect_timeout 7d;
        proxy_send_timeout 7d;
        proxy_read_timeout 7d;
    }
}
```

### 3. 监控与健康检查

```typescript
// 添加健康检查端点
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

## 总结

Bun 是 JavaScript/TypeScript 生态的一次重要升级，它通过**一体化设计**解决了 Node.js 工具链碎片化的问题。对于 VPS 自托管用户来说，Bun 带来的好处是实实在在的：

**核心收益：**

1. **更快的开发体验**：依赖安装 20-30 倍提速，TypeScript 零配置运行
2. **更低的运维成本**：50MB Docker 镜像 vs 1GB+，节省存储和带宽
3. **更高的性能**：3-4 倍请求处理速度，同样的 VPS 承载更多流量
4. **更简单的工具链**：一个 Bun 替代 npm + webpack + Vitest + tsc

**适用场景：**

- ✅ 新建的 Node.js/Bun 项目（强烈推荐）
- ✅ 对性能敏感的 API 服务
- ✅ 资源受限的 VPS（1GB 内存以下）
- ✅ 需要快速冷启动的 Serverless 函数
- ⚠️ 迁移现有 Node.js 项目（需要兼容性测试）
- ❌ 依赖大量 C++ 原生模块的项目（需逐个验证）

**下一步行动：**

- [ ] 在新项目中尝试 Bun
- [ ] 将现有 Node.js 服务迁移到 Bun
- [ ] 优化 Docker 镜像，从 Node.js 切换到 Bun Alpine
- [ ] 配置 CI/CD 支持 Bun
- [ ] 监控性能指标，量化迁移收益

---

*让 Bun 成为你 VPS 运维的加速器！🚀*
