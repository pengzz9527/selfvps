---
title: "从零搭建 VPS AI 智能搜索引擎：向量数据库 + LLM 实现个人知识检索"
description: "用 Qdrant + Ollama + 开源 Embedding 模型在 VPS 上搭建私有人工智能搜索引擎，实现文档检索、语义搜索和 AI 增强问答"
date: 2026-05-22T21:30:00+08:00
slug: "build-private-ai-search-engine-vps"
tags: ["AI", "向量数据库", "Qdrant", "Ollama", "RAG", "Embedding", "语义搜索", "Docker", "自托管", "搜索引擎"]
categories: ["AI部署"]
aliases: [/zh/post/build-private-ai-search-engine-vps/]
image: /images/posts/build-private-ai-search-engine-vps/featured.png
draft: false
---

## 为什么需要私有 AI 搜索引擎？

Google 搜索很好用，但当你需要搜索自己的笔记、技术文档、代码库或者本地文件时，传统搜索引擎就无能为力了。私有 AI 搜索引擎的核心优势：

| 能力 | 传统搜索 | AI 语义搜索 |
|------|----------|------------|
| 关键词匹配 | ✅ 精确匹配 | ✅ 模糊匹配 + 同义词 |
| 理解意图 | ❌ 只认关键词 | ✅ 理解自然语言 |
| 跨文档推理 | ❌ 单文档 | ✅ 聚合多文档回答 |
| 隐私保护 | ❌ 数据上传云端 | ✅ 纯本地运行 |
| 个人化 | ❌ 通用结果 | ✅ 针对你的内容 |

2026 年，开源生态已经成熟：**Qdrant**（向量数据库）做存储和检索，**Ollama** 运行 LLM 做理解与生成，**sentence-transformers** 做文本向量化。三者结合，一台 4GB 内存的 VPS 就能跑起来。

## 架构总览

```
┌──────────────┐     ┌──────────────────┐     ┌──────────────┐
│  文档/笔记    │ ──► │  Embedding 服务   │ ──► │  Qdrant      │
│  Markdown/PDF │     │  (BGE-M3 等模型)  │     │  向量数据库   │
└──────────────┘     └──────────────────┘     └──────────────┘
                                                    │
┌──────────────┐     ┌──────────────────┐           │
│  用户查询     │ ──► │  Query Pipeline   │ ──────────┘
│  自然语言     │     │  + LLM 生成回答   │
└──────────────┘     └──────────────────┘
```

工作流程：
1. **索引阶段**：文档 → 切片 → Embedding 向量 → 存入 Qdrant
2. **检索阶段**：用户问题 → Embedding 向量 → 语义搜索 → 召回最相关片段
3. **生成阶段**：相关片段 + 问题 → LLM → 自然语言回答 + 引用来源

## 第一步：部署 Qdrant 向量数据库

[Qdrant](https://qdrant.tech) 是一个用 Rust 编写的高性能向量搜索引擎，支持过滤、分片和多种相似度算法。Docker 一键部署：

```bash
# 创建持久化数据目录
mkdir -p ~/qdrant_storage

# 运行 Qdrant
docker run -d --name qdrant \
  -p 6333:6333 \
  -p 6334:6334 \
  -v ~/qdrant_storage:/qdrant/storage \
  qdrant/qdrant

# 验证部署
curl http://localhost:6333/health | python3 -m json.tool
# 输出: {"status": "ok"}
```

端口说明：
- `6333` — HTTP API（RESTful 接口）
- `6334` — gRPC API（高性能通信）

### 创建 Collection（集合）

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

`size=1024` 对应 BGE-M3 等模型的输出维度。Cosine 距离适合语义相似度计算。

## 第二步：部署 Embedding 服务

[Embedding 模型](https://huggingface.co/BAAI/bge-m3) 将文本转换成向量。BGE-M3 是 BAAI 开源的通用多语言 Embedding 模型，支持中文和英文。

推荐使用 [sentence-transformers](https://www.sbert.net/) 在本地运行：

```bash
# 创建 Python 虚拟环境
python3 -m venv ~/embeddings-env
source ~/embeddings-env/bin/activate

# 安装依赖
pip install sentence-transformers qdrant-client flask gunicorn

# 启动 Embedding API 服务
cat > ~/embedding_server.py << 'EOF'
from flask import Flask, request, jsonify
from sentence_transformers import SentenceTransformer
import os

app = Flask(__name__)

# 加载模型（首次会自动下载，后续缓存到本地）
model_name = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
model = SentenceTransformer(model_name)

@app.route("/embed", methods=["POST"])
def embed():
    data = request.json
    texts = data.get("texts", [])
    if not texts:
        return jsonify({"error": "no texts provided"}), 400

    # BGE 模型需要在文本前加 instruction 前缀以便检索
    if os.getenv("USE_PREFIX", "true").lower() == "true":
        texts = [f"为这个句子生成表示以用于检索相关文章：{t}" for t in texts]

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

# 使用 Gunicorn 在生产环境运行
pip install gunicorn
gunicorn -w 2 -b 0.0.0.0:8001 embedding_server:app &
```

> ⚠️ **内存说明**：BGE-M3 模型约占用 2GB 内存。如果 VPS 内存不足（<4GB），可换用轻量模型如 `all-MiniLM-L6-v2`（384 维，约 500MB）。但请记得修改 Qdrant collection 的 `size` 参数。

### 验证 Embedding 服务

```bash
curl http://localhost:8001/embed \
  -H 'Content-Type: application/json' \
  -d '{"texts": ["什么是向量数据库？", "Qdrant is a vector search engine"]}'

# 返回结果示例：
# {"embeddings": [[0.012, -0.034, ...], [...]], "dimension": 1024}
```

## 第三步：文档索引与入库

现在我们需要一个索引工具，把文档切片、向量化后存入 Qdrant。以下是核心脚本：

```bash
cat > ~/index_docs.py << 'PYEOF'
#!/usr/bin/env python3
"""将本地文档索引到 Qdrant"""
import os
import glob
import uuid
import hashlib
from qdrant_client import QdrantClient
from qdrant_client.http.models import PointStruct
import requests

# 配置
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))
EMBEDDING_URL = os.getenv("EMBEDDING_URL", "http://localhost:8001")
COLLECTION_NAME = os.getenv("COLLECTION", "my-knowledge")
DOC_DIR = os.getenv("DOC_DIR", os.path.expanduser("~/documents"))

# 初始化 Qdrant 客户端
client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

def chunk_text(text, chunk_size=512, overlap=64):
    """将文本切成有重叠的片段"""
    words = list(text)
    chunks = []
    start = 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunk_text = "".join(words[start:end])
        if len(chunk_text.strip()) > 20:  # 过滤过短的片段
            chunks.append({
                "text": chunk_text,
                "start": start,
                "end": end
            })
        start += chunk_size - overlap
    return chunks

def get_embedding(texts):
    """调用 Embedding API 获取向量"""
    resp = requests.post(f"{EMBEDDING_URL}/embed", json={"texts": texts})
    resp.raise_for_status()
    return resp.json()["embeddings"]

def index_file(filepath):
    """索引单个文件"""
    print(f"📄 正在处理: {filepath}")
    
    # 读取文件
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    
    # 获取相对路径作为元数据
    rel_path = os.path.relpath(filepath, DOC_DIR)
    
    # 切片
    chunks = chunk_text(content)
    print(f"  切片数量: {len(chunks)}")
    
    # 批量向量化
    texts = [c["text"] for c in chunks]
    embeddings = get_embedding(texts)
    
    # 构造 points
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
    
    # 批量入库（每批 100 条）
    for batch_start in range(0, len(points), 100):
        batch = points[batch_start:batch_start + 100]
        client.upsert(
            collection_name=COLLECTION_NAME,
            points=batch
        )
    
    print(f"  ✅ 入库 {len(points)} 个片段")
    return len(points)

def main():
    # 检查 Qdrant 连接
    try:
        client.get_collection(COLLECTION_NAME)
        print(f"✅ 已连接到 Qdrant collection: {COLLECTION_NAME}")
    except Exception:
        print(f"❌ 无法连接 Qdrant 或 collection 不存在")
        return
    
    # 扫描文档目录
    total = 0
    for ext in ["*.md", "*.txt", "*.rst", "*.html"]:
        files = glob.glob(os.path.join(DOC_DIR, "**", ext), recursive=True)
        for f in files:
            total += index_file(f)
    
    print(f"\n🎉 完成！共索引 {total} 个文本片段")

if __name__ == "__main__":
    main()
PYEOF

# 运行索引（假设 ~/documents 下有你需要索引的笔记）
mkdir -p ~/documents
# 放入一些示例文档...
python3 ~/index_docs.py
```

## 第四步：智能检索与 AI 问答

有了索引后，我们可以构建搜索和问答功能：

```bash
cat > ~/search_engine.py << 'PYEOF'
#!/usr/bin/env python3
"""AI 搜索引擎：语义搜索 + LLM 生成回答"""
import os
import requests
from qdrant_client import QdrantClient

# 配置
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))
EMBEDDING_URL = os.getenv("EMBEDDING_URL", "http://localhost:8001")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
COLLECTION_NAME = os.getenv("COLLECTION", "my-knowledge")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen2.5:7b")
TOP_K = int(os.getenv("TOP_K", "5"))

client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

def get_query_embedding(query):
    """将查询转为向量"""
    resp = requests.post(f"{EMBEDDING_URL}/embed", json={
        "texts": [query]
    })
    resp.raise_for_status()
    return resp.json()["embeddings"][0]

def search(query, top_k=TOP_K):
    """语义搜索，返回最相关的文档片段"""
    query_vector = get_query_embedding(query)
    
    results = client.search(
        collection_name=COLLECTION_NAME,
        query_vector=query_vector,
        limit=top_k,
        with_payload=True
    )
    
    return results

def generate_answer(query, search_results):
    """用 LLM 基于搜索结果生成回答"""
    # 构建上下文
    context_parts = []
    for i, res in enumerate(search_results, 1):
        source = res.payload.get("source", "unknown")
        text = res.payload.get("text", "")
        context_parts.append(f"[片段 {i}] 来源: {source}\n{text}\n")
    
    context = "\n---\n".join(context_parts)
    
    # 构造 prompt
    prompt = f"""你是一个基于个人知识库的 AI 助手。请根据以下参考文档回答用户问题。

参考文档：
{context}

用户问题：{query}

要求：
1. 仅基于参考文档内容回答
2. 如果文档中没有相关信息，请如实告知
3. 在回答中引用相关文档来源
4. 用中文回答

回答："""
    
    # 调用 Ollama
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
    """交互式搜索"""
    print("🔍 AI 搜索引擎已启动")
    print(f"  模型: {LLM_MODEL} | 召回: TOP-{TOP_K}")
    print("  输入 'quit' 退出\n")
    
    while True:
        query = input("Q: ").strip()
        if query.lower() in ("quit", "exit", "q"):
            break
        if not query:
            continue
        
        print(f"\n  🔎 搜索相关文档...")
        results = search(query)
        
        print(f"  📄 找到 {len(results)} 个相关片段:")
        for r in results:
            score = r.score
            source = r.payload.get("source", "?")
            text_preview = r.payload.get("text", "")[:80].replace("\n", " ")
            print(f"     [{score:.3f}] {source}: {text_preview}...")
        
        print(f"\n  🤖 正在生成回答...")
        answer = generate_answer(query, results)
        print(f"\n  📝 回答:\n{answer}\n")

if __name__ == "__main__":
    interactive_mode()
PYEOF
```

### 测试搜索

```bash
# 确保 Ollama 已运行（如果还没装）
docker run -d --name ollama -p 11434:11434 \
  -v ollama:/root/.ollama ollama/ollama

docker exec ollama ollama pull qwen2.5:7b

# 运行交互式搜索引擎
python3 ~/search_engine.py
```

示例搜索：

```
Q: VPS 上部署 Docker 需要注意哪些安全问题？

  🔎 搜索相关文档...
  📄 找到 5 个相关片段:
     [0.892] docker-security.md: Docker 安全最佳实践——不要以 root 运行容器...
     [0.765] vps-setup.md: VPS 基础配置包括防火墙、SSH 密钥登录...
     [0.621] docker-compose.md: 使用非 root 用户运行 Docker 守护进程...

  🤖 正在生成回答...

  📝 回答:
在 VPS 上部署 Docker 需要注意以下安全问题（参考文档）：

1. **不要以 root 运行容器**（来源: docker-security.md）：始终使用非 root 用户运行容器进程，可以通过 Dockerfile 中的 USER 指令实现。
2. **配置防火墙**（来源: vps-setup.md）：仅开放必要端口，使用 ufw 或 iptables 限制访问。
3. **使用安全的基础镜像**：选择官方或经过安全审计的镜像。
4. **定期更新**：保持 Docker Engine 和镜像的更新。
```

## 进阶优化

### 1. 使用 Web UI 替代命令行

推荐使用 [Quivr](https://github.com/QuivrHQ/quivr) 或 [DocsGPT](https://github.com/arc53/DocsGPT) 作为前段界面，它们支持可视化文档管理和搜索：

```bash
# Quivr — 开源的 AI 知识库
docker run -d --name quivr \
  -p 5050:5050 \
  -e SUPABASE_URL=... \
  -e OPENAI_API_KEY=... \
  stangirard/quivr
```

### 2. 定时自动索引

用 `cron` 定期更新索引，保持知识库新鲜：

```bash
# 每 6 小时重新索引一次
echo "0 */6 * * * cd ~ && python3 ~/index_docs.py >> ~/index_log.txt 2>&1" | crontab -
```

### 3. 多格式文档支持

用 [unstructured](https://unstructured.io) 或 [markitdown](https://github.com/microsoft/markitdown) 支持 PDF、Word、Excel 等格式：

```bash
pip install unstructured markitdown
python3 -c "
from markitdown import MarkItDown
md = MarkItDown()
result = md.convert('report.pdf')
print(result.text_content)
"
```

### 4. 混合搜索（Hybrid Search）

Qdrant 支持全文搜索 + 向量搜索的混合模式，提升精确关键词匹配能力：

```python
from qdrant_client.http.models import Filter, FieldCondition, MatchText

# 创建全文索引
client.create_payload_index(
    collection_name=COLLECTION_NAME,
    field_name="text",
    field_type="text"
)

# 混合搜索
results = client.search(
    collection_name=COLLECTION_NAME,
    query_vector=query_vector,
    query_filter=Filter(
        must=[
            FieldCondition(
                key="text",
                match=MatchText(text="Docker安全")
            )
        ]
    ),
    limit=10
)
```

## 性能与资源

| 组件 | 内存 | 磁盘 | 说明 |
|------|------|------|------|
| Qdrant | ~200MB | 取决于文档量 | 极省资源 |
| Embedding 服务 (BGE-M3) | ~2GB | ~2GB (模型文件) | 可用轻量模型替代 |
| Ollama (qwen2.5:7b) | ~8GB | ~4GB | 可用 3B 模型替代 |
| **最低配置合计** | **~3.5GB** | **~8GB** | 使用轻量模型 |

> 💡 **省资源方案**：用 `all-MiniLM-L6-v2`（384 维）替代 BGE-M3，用 `qwen2.5:3b` 替代 7B 模型，最低 2GB 内存也能跑。

## 总结

通过本教程，你已经学会了在 VPS 上搭建一套完整的私有 AI 搜索引擎：

1. **Qdrant** — 高性能向量数据库，负责存储和语义检索
2. **Embedding 服务** — 将文本和查询转化为向量
3. **Ollama + LLM** — 基于检索结果生成自然语言回答
4. **索引管线** — 自动切片、向量化、入库

这套系统的核心价值在于：**你的数据永远在你的服务器上**。所有处理都在本地完成，没有数据泄露风险，没有 API 费用，还能针对你的内容进行深度定制。

### 推荐阅读

- [部署开源 AI 工具合集：在 VPS 上搭建 LocalAI、Ollama 等](/zh/post/deploying-open-source-ai-tools/)
- [在 VPS 上部署 Khoj：搭建你的 AI 第二大脑](/zh/post/deploy-khoj-ai-second-brain-vps/)
- [Harbor AI 堆栈部署指南](/zh/post/harbor-ai-stack-deployment/)

> 🔗 **相关资源**：
> - [Qdrant 官方文档](https://qdrant.tech/documentation/)
> - [BGE-M3 模型](https://huggingface.co/BAAI/bge-m3)
> - [Sentence-Transformers](https://www.sbert.net/)
