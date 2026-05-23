---
title: "Build a Private RAG System on VPS: Document Q&A AI for Your Knowledge Base"
description: "Step-by-step guide to building a complete RAG (Retrieval-Augmented Generation) system on a VPS — using Ollama for local LLM inference, ChromaDB as vector store, and LangChain to wire the pipeline. Ask AI questions about your own documents, with data staying on your server."
date: 2026-05-23T21:30:00+08:00
slug: "build-private-rag-system-vps"
tags: ["RAG", "Retrieval-Augmented Generation", "Ollama", "ChromaDB", "LangChain", "AI Deployment", "Knowledge Base", "Docker", "Embedding"]
categories: ["AI Deployment"]
image: /images/posts/build-private-rag-system-vps/featured.png
draft: false
---

## What Is RAG and Why Do You Need It?

RAG (Retrieval-Augmented Generation) is one of the most practical techniques in self-hosted AI. The core idea is simple:

**When a user asks a question, first retrieve relevant document fragments from a knowledge base, then feed those fragments as context to an LLM to generate an answer.**

Compare it to traditional approaches:

| Approach | Pros | Cons |
|----------|------|------|
| Ask LLM directly | Simple | Knowledge cutoff — can't answer about private docs |
| Fine-tune a model | Deep customization | Expensive ($500+), retrain needed for doc updates |
| **RAG** | **Zero training cost, real-time doc updates** | Requires pipeline setup |

RAG's killer feature: **just drop your PDFs, Markdown files, and web pages into a vector database**, and the AI can answer questions about them instantly. No training needed, no GPU required, and updating documents is as simple as re-indexing.

---

## Architecture Overview

```
                      ┌──────────────┐
                      │   Your Docs   │
                      │ (PDF/MD/TXT)  │
                      └──────┬───────┘
                             │
                             ▼
                      ┌──────────────┐
                      │ Text Splitter │
                      └──────┬───────┘
                             │
                             ▼
                      ┌──────────────┐
                      │  Embedding    │ ← Ollama (nomic-embed-text)
                      └──────┬───────┘
                             │
                             ▼
                      ┌──────────────┐
                      │  ChromaDB     │
                      │ (Vector Store)│
                      └──────┬───────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
              ▼              ▼              ▼
         ┌──────────┐ ┌──────────┐ ┌──────────────┐
         │  Query   │ │ Semantic │ │ LLM Generates │
         │          │ │ Retrieval│ │   Answer      │
         └──────────┘ └──────────┘ └──────────────┘
                              │
                         Ollama + LLM
                         (qwen2.5 / mistral)
```

All components run on **a single VPS** — your data never leaves your server.

---

## Requirements

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| VPS | 2 vCPU / 2GB RAM | 4 vCPU / 8GB RAM |
| Storage | 10GB | 20GB+ |
| Docker | ✅ Required | Docker Compose |
| OS | Ubuntu 22.04 / 24.04 | Debian 12 |

> **No GPU needed.** RAG runs fine on CPU — both embedding and LLM inference use the CPU. On a 4-core VPS with moderate document volume, responses arrive in 3-8 seconds.

**Provider picks:** Hetzner CX22 (€3.99/mo) is enough to start. CX32 (€6.95/mo) gives more headroom. Budget option: RackNerd $2.50/mo works but is slightly slower.

---

## Step 1: Install Ollama (Local LLM + Embedding)

Ollama handles two jobs:
1. Runs `nomic-embed-text` — converts documents to vector embeddings
2. Runs `qwen2.5` or `mistral` — generates answers from retrieved context

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull the embedding model (only 274MB)
ollama pull nomic-embed-text

# Pull the LLM (7B class recommended)
ollama pull qwen2.5:7b    # Great for mixed Chinese/English, ~4.7GB
# or
ollama pull mistral:7b    # Great for English-only, ~4.1GB

# Verify
ollama list
```

Ollama listens on `localhost:11434` by default. LangChain will call this API later.

---

## Step 2: Deploy Web UI + Vector Database

Use Docker Compose to deploy Open WebUI (with built-in RAG pipeline) and ChromaDB:

```yaml
# docker-compose.yml
version: '3.8'

services:
  # ── Open WebUI (includes RAG pipeline) ──
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

  # ── ChromaDB (vector database) ──
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

Start it up:

```bash
docker compose up -d
```

Visit `http://your-vps-ip:3000` and register an admin account.

---

## Step 3: Configure RAG in Open WebUI

### 3.1 Connect to Ollama

Go to **Admin Panel → Settings → External Connections**:

- Ollama API URL: `http://host.docker.internal:11434`
- Click "Verify Connection" — green check means success

### 3.2 Configure Embedding Model

Go to **Admin Panel → Settings → Documents**:

- Select `nomic-embed-text` as the embedding model
- This auto-vectorizes every document you upload

### 3.3 Configure RAG Pipeline

Go to **Admin Panel → Pipelines**, make sure:

- **RAG Pipeline** is enabled
- Top-K retrieval: default is 3, set to **5** for better recall
- Chunk Size: default 1000 characters, set to **500** for finer retrieval
- Chunk Overlap: **100** to prevent context breaks

---

## Step 4: Upload Documents & Test

### 4.1 Upload Documents

In the Open WebUI chat interface:

1. Click the `+` icon left of the input box
2. Select "Upload Documents"
3. Supported formats: `PDF`, `TXT`, `Markdown`, `DOCX`, `CSV`

The system automatically:
1. Splits documents into 500-char chunks
2. Generates embeddings via `nomic-embed-text`
3. Stores them in ChromaDB

### 4.2 Test Q&A

Upload a technical document (like your server ops manual), then ask:

> **"I changed my SSH port. Do I need to update my Caddy config too?"**

The RAG system will:
1. Convert your question to a vector
2. Find the 5 most similar document chunks in ChromaDB
3. Send those chunks + your question to the LLM
4. Generate an answer with source references

---

## Step 5: Batch Import with Python (Advanced)

Uploading through the web UI works for a few docs. For **hundreds of documents**, use this script to write directly to ChromaDB:

```python
# batch_ingest.py
import os
from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.embeddings import OllamaEmbeddings
from langchain_community.vectorstores import Chroma

# 1. Load all docs from directory
loader = DirectoryLoader(
    "./docs/",
    glob=["**/*.md", "**/*.txt", "**/*.pdf"],
    loader_cls=TextLoader,
    loader_kwargs={"encoding": "utf-8"}
)
docs = loader.load()
print(f"Loaded {len(docs)} documents")

# 2. Split into chunks
splitter = RecursiveCharacterTextSplitter(
    chunk_size=500,
    chunk_overlap=100
)
chunks = splitter.split_documents(docs)
print(f"Split into {len(chunks)} chunks")

# 3. Generate embeddings and store in ChromaDB
embeddings = OllamaEmbeddings(model="nomic-embed-text")
vectorstore = Chroma.from_documents(
    documents=chunks,
    embedding=embeddings,
    persist_directory="./chroma_db"
)
vectorstore.persist()
print("✅ Batch import complete!")
```

Run it:

```bash
pip install langchain langchain-community chromadb pypdf
python batch_ingest.py
```

---

## Performance Tuning

### 1. Choose the Right LLM

| Model | Size | Chinese | English | Best For |
|-------|------|---------|---------|----------|
| qwen2.5:7b | 4.7GB | ⭐⭐⭐ | ⭐⭐⭐ | Mixed-language docs |
| mistral:7b | 4.1GB | ⭐⭐ | ⭐⭐⭐⭐ | English-only docs |
| phi4:14b | 9.1GB | ⭐⭐ | ⭐⭐⭐⭐ | High-end (8GB+ RAM) |
| llama3.2:3b | 2.0GB | ⭐ | ⭐⭐⭐ | Low-spec VPS |

**For 2GB RAM VPS:** `qwen2.5:7b` or `mistral:7b` + `nomic-embed-text` ≈ 5GB disk, ~3.5GB RAM runtime.

**For 4GB RAM VPS:** `phi4:14b` — noticeably better answer quality.

### 2. Tune Chunk Strategy

- **Code docs**: chunk_size=300, overlap=50 (short code segments, precise matching)
- **Tech manuals**: chunk_size=500, overlap=100 (balance precision & context)
- **Long articles**: chunk_size=1000, overlap=200 (paragraph integrity)

### 3. Widen the Retrieval Window

In Open WebUI settings, bump Top-K from 3 to **5-7** to give the LLM more relevant fragments.

---

## Advanced: Add Caddy Reverse Proxy

```caddyfile
# /etc/caddy/Caddyfile
rag.yourdomain.com {
    reverse_proxy localhost:3000
}
```

Benefits:
- Automatic HTTPS via Let's Encrypt
- Domain access instead of IP:port
- Easy team sharing

```bash
apt install caddy
systemctl enable --now caddy
```

---

## Disk Management

Vector database growth per document volume:

- 100 documents ~ 50MB (ChromaDB storage)
- 1,000 documents ~ 500MB
- 10,000 documents ~ 5GB

Periodic cleanup:

```bash
# Check DB size
du -sh /var/lib/docker/volumes/chroma-data/

# Prune unused Docker data
docker system prune -f
```

---

## FAQ

### RAG answers are inaccurate

1. **Increase Top-K**: 3 → 7, see if that helps
2. **Decrease Chunk Size**: 500 → 300 for finer retrieval
3. **Upgrade LLM**: `qwen2.5:7b` → `phi4:14b` is a big quality jump
4. **Document format**: Prefer Markdown; PDF quality depends on parsing

### PDF upload produces garbled text

Open WebUI uses PyMuPDF for PDF parsing. Fixes:
- Use Markdown instead when possible
- Ensure PDFs are text-based (not scanned)
- For scans, pre-process with `ocrmypdf`

### Out of memory

```bash
# Check Ollama memory usage
ollama ps

# Keep only active models
ollama stop <model-name>

# Or switch to a smaller model
ollama pull llama3.2:3b
ollama rm qwen2.5:7b
```

### ChromaDB connection failure

```bash
# Check container status
docker ps | grep chroma

# View logs
docker logs chromadb

# Restart
docker compose restart chromadb
```

---

## What's Next

Once your RAG system is running, you can:

- **Build a personal knowledge base** — search and ask questions across all your docs
- **Team Wiki** — deploy in your intranet so new members can ask "how do we deploy?"
- **Code documentation search** — index your project READMEs and API docs
- **Automated workflows** — combine with n8n to auto-crawl and index new docs daily

RAG offers the **best ROI in self-hosted AI** right now — no GPU, no training, just a €4/month VPS. The more documents you feed it, the more valuable it becomes.

---

## Resources

- [Ollama Documentation](https://github.com/ollama/ollama)
- [Open WebUI Docs](https://docs.open-webui.com/)
- [ChromaDB Documentation](https://docs.trychroma.com/)
- [LangChain RAG Tutorial](https://python.langchain.com/docs/tutorials/rag/)

---

*Questions about your RAG deployment? Drop a comment below. Next up: automating knowledge updates with RAG + n8n.*
