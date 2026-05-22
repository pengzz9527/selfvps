---
title: "Build a Private AI Search Engine on VPS: Vector Database + LLM for Personal Knowledge Retrieval"
description: "Step-by-step guide to building a private AI search engine on your VPS using Qdrant, Ollama, and open-source embedding models for document retrieval, semantic search, and AI-powered Q&A"
date: 2026-05-22T21:30:00+08:00
slug: "build-private-ai-search-engine-vps"
tags: ["AI", "Vector Database", "Qdrant", "Ollama", "RAG", "Embedding", "Semantic Search", "Docker", "Self-hosting", "Search Engine"]
categories: ["AI Deployment"]
image: /images/posts/build-private-ai-search-engine-vps/featured.png
draft: false
---

## Why a Private AI Search Engine?

Google is great, but when you need to search your own notes, technical documentation, codebase, or local files, traditional search engines fall short. Here's what a private AI search engine offers:

| Capability | Traditional Search | AI Semantic Search |
|------------|-------------------|-------------------|
| Keyword matching | ✅ Exact match | ✅ Fuzzy match + synonyms |
| Intent understanding | ❌ Keywords only | ✅ Natural language |
| Cross-document reasoning | ❌ Single document | ✅ Multi-document synthesis |
| Privacy | ❌ Data goes to cloud | ✅ Fully local |
| Personalization | ❌ Generic results | ✅ Tailored to your content |

In 2026, the open-source ecosystem is mature enough: **Qdrant** (vector database) handles storage and retrieval, **Ollama** runs LLMs for understanding and generation, and **sentence-transformers** handles text vectorization. A VPS with 4GB RAM is enough to run the whole stack.

## Architecture Overview

```
┌──────────────┐     ┌──────────────────┐     ┌──────────────┐
│  Documents     │ ──► │  Embedding Service │ ──► │  Qdrant      │
│  Markdown/PDF  │     │  (BGE-M3 etc.)    │     │  Vector DB   │
└──────────────┘     └──────────────────┘     └──────────────┘
                                                    │
┌──────────────┐     ┌──────────────────┐           │
│  User Query   │ ──► │  Query Pipeline   │ ──────────┘
│  Natural Lang │     │  + LLM Generation │
└──────────────┘     └──────────────────┘
```

Workflow:
1. **Indexing**: Documents → Chunks → Embedding vectors → Stored in Qdrant
2. **Retrieval**: User query → Embedding vector → Semantic search → Top relevant chunks
3. **Generation**: Relevant chunks + query → LLM → Natural language answer with citations

## Step 1: Deploy Qdrant Vector Database

[Qdrant](https://qdrant.tech) is a high-performance vector search engine written in Rust, supporting filtering, sharding, and multiple similarity algorithms. One-command Docker deployment:

```bash
# Create persistent storage
mkdir -p ~/qdrant_storage

# Run Qdrant
docker run -d --name qdrant \
  -p 6333:6333 \
  -p 6334:6334 \
  -v ~/qdrant_storage:/qdrant/storage \
  qdrant/qdrant

# Verify deployment
curl http://localhost:6333/health | python3 -m json.tool
# Output: {"status": "ok"}
```

Ports:
- `6333` — HTTP API (RESTful interface)
- `6334` — gRPC API (high-performance)

### Create a Collection

```bash
curl -X PUT http://localhost:6333/collections/my-knowledge \
  -H 'Content-Type: application/json' \
  -d '{
    "vectors": {
      "size": 1024,
      "distance": "Cosine"
    }
  }'
```

`size=1024` matches the output dimension of BGE-M3 and similar models. Cosine distance works best for semantic similarity.

## Step 2: Deploy the Embedding Service

[Embedding models](https://huggingface.co/BAAI/bge-m3) convert text into vectors. BGE-M3 by BAAI is an excellent multilingual embedding model supporting both English and Chinese.

Run it locally with [sentence-transformers](https://www.sbert.net/):

```bash
# Create Python virtual environment
python3 -m venv ~/embeddings-env
source ~/embeddings-env/bin/activate

# Install dependencies
pip install sentence-transformers qdrant-client flask gunicorn

# Create embedding API server
cat > ~/embedding_server.py << 'EOF'
from flask import Flask, request, jsonify
from sentence_transformers import SentenceTransformer
import os

app = Flask(__name__)

model_name = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
model = SentenceTransformer(model_name)

@app.route("/embed", methods=["POST"])
def embed():
    data = request.json
    texts = data.get("texts", [])
    if not texts:
        return jsonify({"error": "no texts provided"}), 400
    
    embeddings = model.encode(texts, normalize_embeddings=True)
    return jsonify({
        "embeddings": embeddings.tolist(),
        "dimension": embeddings.shape[1]
    })

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "model": model_name})

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8001))
    app.run(host="0.0.0.0", port=port, threaded=True)
EOF

# Run with Gunicorn for production
pip install gunicorn
gunicorn -w 2 -b 0.0.0.0:8001 embedding_server:app &
```

> ⚠️ **Memory note**: BGE-M3 takes ~2GB RAM. If your VPS has limited memory (<4GB), use a lighter model like `all-MiniLM-L6-v2` (384 dimensions, ~500MB). Just remember to update the Qdrant collection's `size` parameter accordingly.

### Verify the Embedding Service

```bash
curl http://localhost:8001/embed \
  -H 'Content-Type: application/json' \
  -d '{"texts": ["What is a vector database?", "Qdrant is a vector search engine"]}'

# Returns:
# {"embeddings": [[0.012, -0.034, ...], [...]], "dimension": 1024}
```

## Step 3: Document Indexing Pipeline

Now we need an indexing tool that chunks documents, vectorizes them, and stores them in Qdrant. Here's the core script:

```bash
cat > ~/index_docs.py << 'PYEOF'
#!/usr/bin/env python3
"""Index local documents into Qdrant"""
import os
import glob
import uuid
from qdrant_client import QdrantClient
from qdrant_client.http.models import PointStruct
import requests

# Configuration
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))
EMBEDDING_URL = os.getenv("EMBEDDING_URL", "http://localhost:8001")
COLLECTION_NAME = os.getenv("COLLECTION", "my-knowledge")
DOC_DIR = os.getenv("DOC_DIR", os.path.expanduser("~/documents"))

client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

def chunk_text(text, chunk_size=512, overlap=64):
    """Split text into overlapping chunks"""
    words = list(text)
    chunks = []
    start = 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunk_text = "".join(words[start:end])
        if len(chunk_text.strip()) > 20:
            chunks.append({
                "text": chunk_text,
                "start": start,
                "end": end
            })
        start += chunk_size - overlap
    return chunks

def get_embedding(texts):
    """Call embedding API to get vectors"""
    resp = requests.post(f"{EMBEDDING_URL}/embed", json={"texts": texts})
    resp.raise_for_status()
    return resp.json()["embeddings"]

def index_file(filepath):
    """Index a single file"""
    print(f"📄 Processing: {filepath}")
    
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    
    rel_path = os.path.relpath(filepath, DOC_DIR)
    chunks = chunk_text(content)
    print(f"  Chunks: {len(chunks)}")
    
    texts = [c["text"] for c in chunks]
    embeddings = get_embedding(texts)
    
    points = []
    for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
        point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{rel_path}:{i}"))
        points.append(PointStruct(
            id=point_id,
            vector=emb,
            payload={
                "text": chunk["text"],
                "source": rel_path,
                "chunk_index": i
            }
        ))
    
    for batch_start in range(0, len(points), 100):
        batch = points[batch_start:batch_start + 100]
        client.upsert(collection_name=COLLECTION_NAME, points=batch)
    
    print(f"  ✅ Indexed {len(points)} chunks")
    return len(points)

def main():
    try:
        client.get_collection(COLLECTION_NAME)
        print(f"✅ Connected to Qdrant collection: {COLLECTION_NAME}")
    except Exception:
        print(f"❌ Cannot connect to Qdrant or collection doesn't exist")
        return
    
    total = 0
    for ext in ["*.md", "*.txt", "*.rst", "*.html"]:
        files = glob.glob(os.path.join(DOC_DIR, "**", ext), recursive=True)
        for f in files:
            total += index_file(f)
    
    print(f"\n🎉 Done! Indexed {total} text chunks")

if __name__ == "__main__":
    main()
PYEOF

# Run the indexer (put your docs in ~/documents first)
mkdir -p ~/documents
python3 ~/index_docs.py
```

## Step 4: Intelligent Search & AI Q&A

With the index in place, we can build search and Q&A functionality:

```bash
cat > ~/search_engine.py << 'PYEOF'
#!/usr/bin/env python3
"""AI Search Engine: Semantic Search + LLM Answer Generation"""
import os
import requests
from qdrant_client import QdrantClient

# Configuration
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))
EMBEDDING_URL = os.getenv("EMBEDDING_URL", "http://localhost:8001")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
COLLECTION_NAME = os.getenv("COLLECTION", "my-knowledge")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen2.5:7b")
TOP_K = int(os.getenv("TOP_K", "5"))

client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

def get_query_embedding(query):
    """Convert query to vector"""
    resp = requests.post(f"{EMBEDDING_URL}/embed", json={"texts": [query]})
    resp.raise_for_status()
    return resp.json()["embeddings"][0]

def search(query, top_k=TOP_K):
    """Semantic search returning the most relevant document chunks"""
    query_vector = get_query_embedding(query)
    
    results = client.search(
        collection_name=COLLECTION_NAME,
        query_vector=query_vector,
        limit=top_k,
        with_payload=True
    )
    
    return results

def generate_answer(query, search_results):
    """Generate answer using LLM based on search results"""
    context_parts = []
    for i, res in enumerate(search_results, 1):
        source = res.payload.get("source", "unknown")
        text = res.payload.get("text", "")
        context_parts.append(f"[Chunk {i}] Source: {source}\n{text}\n")
    
    context = "\n---\n".join(context_parts)
    
    prompt = f"""You are an AI assistant powered by a personal knowledge base. Answer the user's question based on the provided reference documents.

Reference Documents:
{context}

User Question: {query}

Guidelines:
1. Only answer based on the reference documents
2. If the documents don't contain relevant information, say so honestly
3. Cite sources in your answer
4. Answer in the same language as the question

Answer:"""
    
    resp = requests.post(f"{OLLAMA_URL}/api/generate", json={
        "model": LLM_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.3,
            "top_k": 40,
            "num_ctx": 4096
        }
    })
    resp.raise_for_status()
    return resp.json()["response"]

def interactive_mode():
    """Interactive search REPL"""
    print("🔍 AI Search Engine Started")
    print(f"  Model: {LLM_MODEL} | Top-K: {TOP_K}")
    print("  Type 'quit' to exit\n")
    
    while True:
        query = input("Q: ").strip()
        if query.lower() in ("quit", "exit", "q"):
            break
        if not query:
            continue
        
        print(f"\n  🔎 Searching documents...")
        results = search(query)
        
        print(f"  📄 Found {len(results)} relevant chunks:")
        for r in results:
            score = r.score
            source = r.payload.get("source", "?")
            preview = r.payload.get("text", "")[:80].replace("\n", " ")
            print(f"     [{score:.3f}] {source}: {preview}...")
        
        print(f"\n  🤖 Generating answer...")
        answer = generate_answer(query, results)
        print(f"\n  📝 Answer:\n{answer}\n")

if __name__ == "__main__":
    interactive_mode()
PYEOF
```

### Test the Search

```bash
# Make sure Ollama is running
docker run -d --name ollama -p 11434:11434 \
  -v ollama:/root/.ollama ollama/ollama

docker exec ollama ollama pull qwen2.5:7b

# Run the interactive search engine
python3 ~/search_engine.py
```

Example session:

```
Q: What security considerations should I follow when running Docker on a VPS?

  🔎 Searching documents...
  📄 Found 5 relevant chunks:
     [0.892] docker-security.md: Docker security best practices — don't run containers as root...
     [0.765] vps-setup.md: VPS basic setup includes firewall, SSH key authentication...
     [0.621] docker-compose.md: Run Docker daemon with non-root user...

  🤖 Generating answer...

  📝 Answer:
Based on the reference documents, here are key security considerations for running Docker on a VPS:

1. **Don't run containers as root** (Source: docker-security.md): Always use a non-root user for container processes via the USER directive in your Dockerfile.
2. **Configure a firewall** (Source: vps-setup.md): Only expose necessary ports and use ufw or iptables to restrict access.
3. **Use secure base images**: Choose official or security-audited images.
4. **Keep everything updated**: Regularly update Docker Engine and all your images.
```

## Advanced Optimizations

### 1. Web UI Instead of CLI

Use [Quivr](https://github.com/QuivrHQ/quivr) or [DocsGPT](https://github.com/arc53/DocsGPT) as a visual frontend:

```bash
# Quivr — open-source AI knowledge base
docker run -d --name quivr \
  -p 5050:5050 \
  stangirard/quivr
```

### 2. Scheduled Auto-Indexing

Use `cron` to keep your knowledge base fresh:

```bash
# Re-index every 6 hours
echo "0 */6 * * * cd ~ && python3 ~/index_docs.py >> ~/index_log.txt 2>&1" | crontab -
```

### 3. Multi-Format Document Support

Use [unstructured](https://unstructured.io) or [markitdown](https://github.com/microsoft/markitdown) to handle PDF, Word, Excel, and more:

```bash
pip install unstructured markitdown
python3 -c "
from markitdown import MarkItDown
md = MarkItDown()
result = md.convert('report.pdf')
print(result.text_content)
"
```

### 4. Hybrid Search

Qdrant supports combining full-text search with vector search for better precision:

```python
from qdrant_client.http.models import Filter, FieldCondition, MatchText

# Create full-text payload index
client.create_payload_index(
    collection_name=COLLECTION_NAME,
    field_name="text",
    field_type="text"
)

# Hybrid search
results = client.search(
    collection_name=COLLECTION_NAME,
    query_vector=query_vector,
    query_filter=Filter(
        must=[
            FieldCondition(
                key="text",
                match=MatchText(text="Docker security")
            )
        ]
    ),
    limit=10
)
```

## Resource Requirements

| Component | RAM | Disk | Notes |
|-----------|-----|------|-------|
| Qdrant | ~200MB | Depends on doc volume | Very lightweight |
| Embedding Service (BGE-M3) | ~2GB | ~2GB (model files) | Can use lighter models |
| Ollama (qwen2.5:7b) | ~8GB | ~4GB | Can use 3B model instead |
| **Minimum Total** | **~3.5GB** | **~8GB** | Using lightweight models |

> 💡 **Budget-friendly setup**: Replace BGE-M3 with `all-MiniLM-L6-v2` (384 dimensions) and use `qwen2.5:3b` instead of 7B — runs on as little as 2GB RAM.

## Summary

Through this tutorial, you've built a complete private AI search engine on your VPS:

1. **Qdrant** — High-performance vector database for storage and semantic retrieval
2. **Embedding Service** — Converts text and queries into vectors
3. **Ollama + LLM** — Generates natural language answers from retrieved content
4. **Indexing Pipeline** — Automatically chunks, vectorizes, and stores your documents

The core value proposition: **Your data stays on your server**. Every step runs locally — no data leaks, no API fees, and deep customization for your specific content.

### Further Reading

- [Deploying Open-Source AI Tools: LocalAI, Ollama & More on Your VPS](/en/post/deploying-open-source-ai-tools/)
- [Deploy Khoj: Your AI Second Brain on a VPS](/en/post/deploy-khoj-ai-second-brain-vps/)
- [Harbor AI Stack Deployment Guide](/en/post/harbor-ai-stack-deployment/)

> 🔗 **Resources**:
> - [Qdrant Documentation](https://qdrant.tech/documentation/)
> - [BGE-M3 on HuggingFace](https://huggingface.co/BAAI/bge-m3)
> - [Sentence-Transformers](https://www.sbert.net/)
