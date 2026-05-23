---
title: "在 VPS 上搭建私有 RAG 系统：用 AI 文档问答打造个人知识库"
description: "手把手教你在一台 VPS 上搭建完整的 RAG（检索增强生成）系统——用 Ollama 运行本地 LLM、ChromaDB 做向量存储、LangChain 串联管道，让你用自己的文档向 AI 提问，数据不出服务器。"
date: 2026-05-23T21:30:00+08:00
slug: "build-private-rag-system-vps"
tags: ["RAG", "检索增强生成", "Ollama", "ChromaDB", "LangChain", "AI部署", "知识库", "Docker", "Embedding"]
categories: ["AI部署"]
image: /images/posts/build-private-rag-system-vps/featured.png
draft: false
---

## 什么是 RAG？为什么你需要它？

RAG（Retrieval-Augmented Generation，检索增强生成）是目前自托管 AI 领域最实用的技术之一。它的核心思路很简单：

**当用户提问时，先从知识库中检索相关文档片段，再把这些片段作为上下文交给 LLM 生成回答。**

对比传统方案的优势一目了然：

| 方案 | 优点 | 缺点 |
|------|------|------|
| 直接问 LLM | 简单 | 知识截止于训练数据，无法回答私有文档内容 |
| 微调模型 | 深度定制 | 成本高（$500+），每次更新文档需要重新训练 |
| **RAG** | **零训练成本，文档实时更新** | 需要搭建管道 |

RAG 的杀手特性：你只需要**把 PDF、Markdown、网页等文档丢进向量数据库**，AI 就能随时根据这些文档回答提问。不需要训练、不需要 GPU、文档更新只需重新索引。

---

## 架构概览

```
                      ┌──────────────┐
                      │   你的文档     │
                      │  (PDF/MD/TXT) │
                      └──────┬───────┘
                             │
                             ▼
                      ┌──────────────┐
                      │   文档切割     │
                      │  (Text Split) │
                      └──────┬───────┘
                             │
                             ▼
                      ┌──────────────┐
                      │  Embedding 模型 │ ← Ollama (nomic-embed-text)
                      └──────┬───────┘
                             │
                             ▼
                      ┌──────────────┐
                      │  ChromaDB     │
                      │ (向量存储)      │
                      └──────┬───────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
              ▼              ▼              ▼
         ┌──────────┐ ┌──────────┐ ┌──────────────┐
         │ 用户提问  │ │ 语义检索  │ │ LLM 生成回答  │
         └──────────┘ └──────────┘ └──────────────┘
                              │
                         Ollama + LLM
                         (qwen2.5 / mistral)
```

所有组件运行在 **一台 VPS** 上，数据不出服务器。

---

## 环境要求

| 资源 | 最低要求 | 推荐配置 |
|------|---------|---------|
| VPS | 2 核 / 2GB RAM | 4 核 / 8GB RAM |
| 存储 | 10GB | 20GB+（取决于文档量） |
| Docker | ✅ 需要 | Docker Compose |
| 系统 | Ubuntu 22.04 / 24.04 | Debian 12 |

> **没有 GPU 也可以跑。** RAG 不需要 GPU——Embedding 和 LLM 推理都跑在 CPU 上，4 核 VPS 的中等文档量响应在 3-8 秒。

**服务商推荐：** Hetzner CX22（€3.99/月）起步够用，CX32（€6.95/月）更舒服。如果想省钱，RackNerd $2.50/月也能跑但略慢。

---

## 第一步：安装 Ollama（本地 LLM + Embedding）

Ollama 负责两件事：
1. 运行 `nomic-embed-text` 模型——将文档转换为向量
2. 运行 `qwen2.5` 或 `mistral`——基于检索内容生成回答

```bash
# 安装 Ollama
curl -fsSL https://ollama.com/install.sh | sh

# 拉取 Embedding 模型（仅 274MB）
ollama pull nomic-embed-text

# 拉取 LLM 模型（推荐 7B 级别）
ollama pull qwen2.5:7b    # 中文优秀，~4.7GB
# 或
ollama pull mistral:7b    # 英文优秀，~4.1GB

# 确认运行中
ollama list
```

Ollama 默认监听 `localhost:11434`，后续 LangChain 会从这里调用 API。

---

## 第二步：搭建 Web UI + 向量数据库

我们使用 Docker Compose 部署 Open WebUI（带 RAG 功能）和 ChromaDB：

```yaml
# docker-compose.yml
version: '3.8'

services:
  # ── Open WebUI（含内置 RAG 管道）──
  open-webui:
    image: ghcr.io/open-webui/open-webui:main
    container_name: open-webui
    restart: unless-stopped
    ports:
      - "3000:8080"
    volumes:
      - open-webui-data:/app/backend/data
    environment:
      - OLLAMA_BASE_URL=http://host.docker.internal:11434
      - WEBUI_SECRET_KEY=your-random-secret-key-here
    extra_hosts:
      - "host.docker.internal:host-gateway"

  # ── ChromaDB（向量数据库）──
  chromadb:
    image: chromadb/chroma:latest
    container_name: chromadb
    restart: unless-stopped
    ports:
      - "8000:8000"
    volumes:
      - chroma-data:/chroma/chroma
    environment:
      - IS_PERSISTENT=TRUE
      - ANONYMIZED_TELEMETRY=FALSE

volumes:
  open-webui-data:
  chroma-data:
```

启动：

```bash
docker compose up -d
```

现在访问 `http://你的VPS-IP:3000`，注册管理员账号。

---

## 第三步：在 Open WebUI 中配置 RAG

### 3.1 连接到 Ollama

进入 **管理面板 → 设置 → 外部连接**：

- Ollama API URL: `http://host.docker.internal:11434`
- 点击「验证连接」——绿色提示成功

### 3.2 配置 Embedding 模型

进入 **管理面板 → 设置 → 文档**：

- Embedding 模型选择器选择 `nomic-embed-text`
- 这会将上传的文档自动转为向量存入本地

### 3.3 配置 RAG 管道

进入 **管理面板 → 管道**，确保：

- **RAG Pipeline** 处于启用状态
- 检索 Top-K（默认 3）：建议设为 **5**，提高召回率
- 块大小（Chunk Size）：默认 1000 字符，建议 **500**（更精细检索）
- 块重叠（Chunk Overlap）：**100**（防止上下文断裂）

---

## 第四步：上传文档并测试

### 4.1 上传文档

在 Open WebUI 的对话界面：

1. 点击输入框左侧的 `+` 号
2. 选择「上传文档」
3. 支持格式：`PDF`、`TXT`、`Markdown`、`DOCX`、`CSV`

上传后系统自动：
1. 切割文档为 500 字块
2. 用 `nomic-embed-text` 生成向量
3. 存入 ChromaDB

### 4.2 测试问答

上传一份技术文档（比如你的服务器运维手册），然后问：

> **「我的服务器 SSH 端口改了，Caddy 配置里需要同步改哪里？」**

RAG 系统会：
1. 将问题转为向量
2. 在 ChromaDB 中检索最相似的 5 个文档片段
3. 将片段 + 问题一起发给 LLM
4. 生成带引用来源的回答

---

## 第五步：用 Python 脚本批量导入文档（高级）

Open WebUI 的 Web 界面上传适合少量文档。如果你有**几百个文档**需要批量索引，可以用这个脚本直接写入 ChromaDB：

```python
# batch_ingest.py
import os
from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.embeddings import OllamaEmbeddings
from langchain_community.vectorstores import Chroma

# 1. 加载文档目录中的所有文件
loader = DirectoryLoader(
    "./docs/",
    glob=["**/*.md", "**/*.txt", "**/*.pdf"],
    loader_cls=TextLoader,
    loader_kwargs={"encoding": "utf-8"}
)
docs = loader.load()
print(f"加载了 {len(docs)} 个文档")

# 2. 切割
splitter = RecursiveCharacterTextSplitter(
    chunk_size=500,
    chunk_overlap=100
)
chunks = splitter.split_documents(docs)
print(f"切割为 {len(chunks)} 个块")

# 3. 生成向量并存入 ChromaDB
embeddings = OllamaEmbeddings(model="nomic-embed-text")
vectorstore = Chroma.from_documents(
    documents=chunks,
    embedding=embeddings,
    persist_directory="./chroma_db"
)
vectorstore.persist()
print("✅ 批量导入完成！")
```

运行：

```bash
pip install langchain langchain-community chromadb pypdf
python batch_ingest.py
```

---

## 性能调优

### 1. 选择正确的 LLM

| 模型 | 大小 | 中文 | 英文 | 推荐场景 |
|------|------|------|------|----------|
| qwen2.5:7b | 4.7GB | ⭐⭐⭐ | ⭐⭐⭐ | 中英混合文档 |
| mistral:7b | 4.1GB | ⭐⭐ | ⭐⭐⭐⭐ | 纯英文文档 |
| phi4:14b | 9.1GB | ⭐⭐ | ⭐⭐⭐⭐ | 高端（需 8GB+ RAM） |
| llama3.2:3b | 2.0GB | ⭐ | ⭐⭐⭐ | 低配 VPS 专用 |

**2GB RAM VPS 推荐：** `qwen2.5:7b` 或 `mistral:7b` + `nomic-embed-text`，两者共存约 5GB 磁盘，运行时 RAM 约 3.5GB（含系统开销）。

**4GB RAM VPS 推荐：** `phi4:14b`，回答问题质量明显更高。

### 2. 修改 Chunk 策略

- **代码文档**：chunk_size=300，overlap=50（代码段短，精确定位）
- **技术手册**：chunk_size=500，overlap=100（平衡精度与上下文）
- **长篇文章**：chunk_size=1000，overlap=200（保持段落完整性）

### 3. 增加检索窗口

在 Open WebUI 设置中把 Top-K 从 3 调到 **5-7**，召回更多相关片段供 LLM 参考。

---

## 进阶：用 Caddy 反代加域名访问

```caddyfile
# /etc/caddy/Caddyfile
rag.你的域名.com {
    reverse_proxy localhost:3000
}
```

再加一层 Caddy 的好处：
- HTTPS 自动证书
- 域名访问而非 IP:端口
- 方便分享给团队

```bash
apt install caddy
systemctl enable --now caddy
```

---

## 磁盘管理

向量数据库会随文档量增长。按经验：

- 100 份文档 ~ 50MB（ChromaDB 存储）
- 1000 份文档 ~ 500MB
- 1万份文档 ~ 5GB

定期清理临时文件：

```bash
# 查看数据库大小
du -sh /var/lib/docker/volumes/chroma-data/

# 清理未使用的 Docker 数据
docker system prune -f
```

---

## 常见问题

### RAG 回答不准确

1. **增大 Top-K**：从 3 调到 7，看看是否改善
2. **减小 Chunk Size**：500 → 300，更细粒度的检索
3. **换更好的 LLM**：`qwen2.5:7b` → `phi4:14b` 质量有跃升
4. **文档格式**：尽量用 Markdown，PDF 的解析质量依赖 OCR

### 上传 PDF 乱码

Open WebUI 使用 PyMuPDF 解析 PDF。如果出现乱码：
- 优先用 Markdown 格式
- 确认 PDF 是文字型（非扫描件）
- 扫描件需要 OCR 预处理（推荐 `ocrmypdf`）

### 内存不足

```bash
# 查看 Ollama 占用
ollama ps

# 只保留正在使用的模型
ollama stop <model-name>

# 或者换小模型
ollama pull llama3.2:3b
ollama rm qwen2.5:7b
```

### ChromaDB 连接失败

```bash
# 检查容器是否运行
docker ps | grep chroma

# 查看日志
docker logs chromadb

# 重启
docker compose restart chromadb
```

---

## 下一步

有了 RAG 系统，你可以：

- **搭建个人知识库**：所有技术文档、笔记、手册都可以搜索问答
- **团队内部 Wiki**：部署在公司内网，新成员可以直接问「服务器怎么部署」
- **代码库文档检索**：把项目 README 和 API 文档导入，开发时快速查询
- **自动化工作流**：结合 n8n，每天自动爬取新文档并索引

RAG 是当前自托管 AI 领域**投入产出比最高**的应用之一——不需要 GPU、不需要训练、一台 €4/月的 VPS 就能跑。文档越来越多，RAG 系统的价值也越来越大。

---

## 参考资源

- [Ollama 官方文档](https://github.com/ollama/ollama)
- [Open WebUI 文档](https://docs.open-webui.com/)
- [ChromaDB 文档](https://docs.trychroma.com/)
- [LangChain RAG 教程](https://python.langchain.com/docs/tutorials/rag/)

---

*如果你对 RAG 部署有任何问题，欢迎在评论区留言。下一篇文章会介绍如何用 RAG + n8n 搭建自动化知识更新工作流。*
