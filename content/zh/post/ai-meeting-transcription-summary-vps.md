---
title: "在 VPS 上搭建 AI 会议记录与总结助手：Whisper 自动转录 + LLM 智能总结"
description: "开会一小时，笔记半小时？用 VPS 搭建私有 AI 会议助手——Whisper 自动将语音转为文字，本地 LLM 智能生成摘要、待办事项和决策要点。全程数据不出服务器，支持 Zoom/Teams/本地录音。"
date: 2026-05-29T21:30:00+08:00
slug: "ai-meeting-transcription-summary-vps"
tags: ["Whisper", "LLM", "会议转录", "语音转文字", "Ollama", "自托管", "AI总结", "自动化"]
categories: ["AI工具"]
image: /images/posts/ai-meeting-transcription-summary-vps/featured.png
draft: false
---

## 为什么要自己搭建会议记录助手？

你每周开多少小时会？一小时会议，至少再花半小时整理笔记。更糟的是，使用在线转录服务意味着把敏感的商业对话上传到第三方服务器。

**自己搭建的优势：**

| 能力 | 在线服务 | 自托管方案 |
|------|---------|-----------|
| 数据隐私 | 上传到第三方服务器 | ✅ 全程在 VPS 上处理 |
| 费用 | $10-30/月订阅 | 💰 一次部署，按月付 VPS 费 |
| 模型选择 | 厂商锁定 | ✅ 自由切换 Whisper 模型大小 |
| 集成 | 受限的 API | ✅ 任意对接 n8n/Slack/Telegram |
| 自定义提示词 | ❌ 固定模板 | ✅ 完全自定义总结风格 |

### 适用场景

- **创业团队**：不想把会议录音上传到第三方
- **自由职业者**：需要自动整理客户沟通记录
- **研究者**：批量转录讲座、访谈音频
- **任何重视隐私的人**：你的会议内容只属于你

## 架构总览

```
┌─────────────┐    ┌──────────────┐    ┌─────────────┐
│  录音文件    │───→│  Whisper     │───→│  原始文本    │
│ (MP3/MP4/WAV)│    │  语音转文字  │    │  (SRT/TXT)  │
└─────────────┘    └──────────────┘    └─────────────┘
                                            │
                                            ▼
┌─────────────┐    ┌──────────────┐    ┌─────────────┐
│  Telegram/  │←───│  本地 LLM    │←───│  分段文本    │
│  Web UI     │    │  (Ollama)    │    │  (分块处理)  │
└─────────────┘    └──────────────┘    └─────────────┘
                          │
                          ▼
              ┌─────────────────────┐
              │  会议摘要 + 待办    │
              │  决策要点 + 时间线  │
              └─────────────────────┘
```

## 环境要求

### 最低配置（小模型 + 短音频）

| 组件 | 要求 |
|------|------|
| VPS | 2 核, 4GB RAM, 20GB 磁盘 |
| 模型 | Whisper `tiny` 或 `base` |

### 推荐配置（中等模型 + 日常使用）

| 组件 | 要求 |
|------|------|
| VPS | 4 核, 8GB RAM, 40GB 磁盘 |
| 模型 | Whisper `small` + Llama 3.1 8B |
| GPU | 有更好，非必需 |

> 💡 **GPU 选配**：如果 VPS 有 NVIDIA GPU（如 RunPod、Vast.ai），Whisper 转录速度提升 5-10 倍。没有 GPU 也能用——CPU 模式转录一小时会议约需 10-20 分钟（`small` 模型）。

## 第一步：部署 Whisper 转录服务

### 1.1 安装 Docker（如未安装）

```bash
# 安装 Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER
```

### 1.2 部署 Whisper 服务

我们使用 `whisper-asr-webservice`——一个将 OpenAI Whisper 封装为 HTTP API 的 Docker 镜像，开箱即用。

```bash
# 拉取并启动 Whisper 服务（CPU 模式）
docker run -d \
  --name whisper-server \
  -p 9000:9000 \
  -e ASR_MODEL=base \
  -e ASR_ENGINE=openai_whisper \
  --restart unless-stopped \
  onerahmet/openai-whisper-asr-webservice:latest-gpu
```

> 如果 VPS 有 GPU，用 `latest-gpu` 镜像并加上 `--gpus all` 参数。

**验证服务运行：**

```bash
curl http://localhost:9000/health
# 返回: {"status": "ok"}
```

**测试转录：**

```bash
# 用你的一段录音测试
curl -X POST http://localhost:9000/asr \
  -F "audio_file=@meeting.mp3" \
  -F "response_format=text"
# 返回转录文本
```

### 1.3 模型大小选择指南

| 模型 | 参数 | 速度 | 准确率 | 磁盘占用 | 推荐场景 |
|------|------|------|--------|---------|---------|
| `tiny` | 39M | ⚡⚡⚡⚡⚡ | 一般 | ~150MB | 快速测试 |
| `base` | 74M | ⚡⚡⚡⚡ | 良好 | ~290MB | 日常使用 |
| `small` | 244M | ⚡⚡⚡ | 很好 | ~950MB | 高质量转录 |
| `medium` | 769M | ⚡⚡ | 优秀 | ~3GB | 嘈杂环境 |
| `large-v3` | 1.55B | ⚡ | 最佳 | ~6GB | 多语言/专业场景 |

对于中文会议录音，推荐使用 `small` 或 `medium` 模型，中文识别准确率更高。

## 第二步：部署 Ollama + 本地 LLM

### 2.1 安装 Ollama

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

### 2.2 拉取推荐模型

```bash
# 用于总结的 LLM（推荐 8B 参数以上）
ollama pull llama3.1:8b

# 如果 VPS 内存有限，用更小的模型
ollama pull qwen2.5:7b   # 中文支持更好
ollama pull gemma2:9b    # 英文场景优秀
```

### 2.3 验证 LLM 可用

```bash
ollama run llama3.1:8b "请用一句话总结：今天会议讨论了服务器架构升级方案"
```

## 第三步：搭建会议记录处理管道

### 3.1 创建处理脚本

以下是完整的自动化转录 + 总结脚本：

```python
#!/usr/bin/env python3
"""
AI 会议助手：自动转录 + 智能总结
支持：本地文件、URL 下载、目录监控
"""

import os
import sys
import json
import time
import argparse
import requests
from pathlib import Path

# ── 配置 ──────────────────────────────────────────
WHISPER_URL = "http://localhost:9000/asr"
OLLAMA_URL = "http://localhost:11434/api/generate"
LLM_MODEL = "llama3.1:8b"  # 或 "qwen2.5:7b"

OUTPUT_DIR = Path.home() / "meeting_notes"
OUTPUT_DIR.mkdir(exist_ok=True)

# ── Whisper 转录 ──────────────────────────────────

def transcribe_audio(audio_path: str, model: str = "base",
                     language: str = "zh") -> str:
    """调用 Whisper API 进行语音转文字"""
    print(f"[转录] 正在处理: {audio_path}")
    with open(audio_path, "rb") as f:
        files = {"audio_file": f}
        data = {
            "response_format": "text",
            "language": language,
            "model": model,
        }
        resp = requests.post(WHISPER_URL, files=files, data=data, timeout=600)
        resp.raise_for_status()
    text = resp.text.strip()
    print(f"[转录] 完成！共 {len(text)} 字符")
    return text

# ── LLM 总结 ──────────────────────────────────────

SUMMARY_PROMPT_TEMPLATE = """你是一个专业的会议记录助理。请基于以下会议转录内容，生成一份结构清晰的会议纪要。

请包含以下部分：
1. **会议概要**：一句话概括本次会议主题
2. **讨论要点**：按重要性列出核心讨论内容
3. **决策记录**：明确记录的决策事项
4. **待办事项**：列出需要跟进的任务，格式为「负责人：任务内容」
5. **时间线**：如有明确时间节点，列出关键时间线

转录内容：
{transcript}

请用{language}回复。
"""

def generate_summary(transcript: str, language: str = "中文") -> str:
    """调用本地 LLM 生成会议总结"""
    print("[总结] 正在生成会议纪要...")
    prompt = SUMMARY_PROMPT_TEMPLATE.format(
        transcript=transcript[:8000],  # 限制上下文长度
        language=language
    )
    payload = {
        "model": LLM_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.3,  # 低温度，更精确
            "num_predict": 2048
        }
    }
    resp = requests.post(OLLAMA_URL, json=payload, timeout=120)
    resp.raise_for_status()
    summary = resp.json()["response"]
    print(f"[总结] 完成！共 {len(summary)} 字符")
    return summary

# ── 主流程 ────────────────────────────────────────

def process_meeting(audio_path: str, language: str = "zh",
                    whisper_model: str = "base"):
    """处理单个会议录音的完整流程"""
    audio_file = Path(audio_path)
    base_name = audio_file.stem
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    
    # 1. 转录
    transcript = transcribe_audio(audio_path, model=whisper_model, language=language)
    
    # 保存转录文本
    transcript_file = OUTPUT_DIR / f"{base_name}_{timestamp}_transcript.txt"
    transcript_file.write_text(transcript)
    print(f"[保存] 转录文本: {transcript_file}")
    
    # 2. 总结
    lang_name = "中文" if language.startswith("zh") else "English"
    summary = generate_summary(transcript, language=lang_name)
    
    # 保存总结
    summary_file = OUTPUT_DIR / f"{base_name}_{timestamp}_summary.md"
    summary_file.write_text(summary)
    print(f"[保存] 会议纪要: {summary_file}")
    
    # 3. 保存完整记录（JSON 格式，方便程序读取）
    record = {
        "file": audio_path,
        "timestamp": timestamp,
        "language": language,
        "model": whisper_model,
        "transcript": transcript,
        "summary": summary,
    }
    json_file = OUTPUT_DIR / f"{base_name}_{timestamp}_record.json"
    json_file.write_text(json.dumps(record, ensure_ascii=False, indent=2))
    print(f"[保存] 完整记录: {json_file}")
    
    return summary

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI 会议助手")
    parser.add_argument("audio", help="音频文件路径")
    parser.add_argument("--lang", default="zh", help="音频语言 (zh/en/ja)")
    parser.add_argument("--model", default="base", help="Whisper 模型大小")
    args = parser.parse_args()
    
    summary = process_meeting(args.audio, args.lang, args.model)
    print("\n" + "="*50)
    print("📋 会议纪要")
    print("="*50)
    print(summary)
```

### 3.2 运行测试

```bash
# 安装依赖
pip install requests

# 转录并总结一段中文录音
python3 meeting_assistant.py meeting.mp3 --lang zh --model small

# 英文录音
python3 meeting_assistant.py team_sync.mp3 --lang en --model small
```

## 第四步：搭建 Web 上传界面（可选）

用 Streamlit 快速搭建一个可视化界面：

### 4.1 安装 Streamlit

```bash
pip install streamlit
```

### 4.2 创建 Web 界面

```python
# app.py
import streamlit as st
import tempfile
import os
from meeting_assistant import process_meeting

st.set_page_config(page_title="AI 会议助手", layout="wide")
st.title("🎙️ AI 会议记录与总结助手")

st.markdown("上传会议录音，自动生成转录文本和智能总结。")

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("📤 上传录音")
    audio_file = st.file_uploader(
        "选择音频文件 (MP3, WAV, M4A)",
        type=["mp3", "wav", "m4a", "ogg"]
    )
    
    if audio_file:
        st.audio(audio_file, format="audio/mp3")
    
    lang = st.selectbox("音频语言", ["中文", "English", "日本語"])
    model_size = st.selectbox(
        "Whisper 模型",
        ["base", "small", "medium"],
        index=1
    )
    
    lang_map = {"中文": "zh", "English": "en", "日本語": "ja"}
    
    if st.button("开始处理 🚀", disabled=not audio_file):
        with st.spinner("正在转录中..."):
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
                tmp.write(audio_file.getvalue())
                tmp_path = tmp.name
            
            summary = process_meeting(
                tmp_path,
                language=lang_map[lang],
                whisper_model=model_size
            )
            os.unlink(tmp_path)
            
            with col2:
                st.subheader("📋 会议纪要")
                st.markdown(summary)

with col2:
    st.subheader("💡 使用提示")
    st.info("""
    - 支持格式：MP3, WAV, M4A, OGG
    - 建议录音质量：≥16kHz 采样率
    - 单文件上限：由 VPS 磁盘空间决定
    - 处理时间：每小时录音约需 10-20 分钟
    """)
```

### 4.3 启动 Web UI

```bash
streamlit run app.py --server.port 8501 --server.address 0.0.0.0
```

用反向代理（Caddy/Nginx）绑定域名，或者直接用 `http://你的VPSIP:8501` 访问。

## 第五步：集成到即时通讯工具

### 5.1 对接 Telegram Bot

用 Telegram Bot 接收录音并返回纪要：

```python
# telegram_bot.py
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from meeting_assistant import process_meeting
import tempfile
import os

TOKEN = "YOUR_BOT_TOKEN"

async def handle_audio(update: Update, context):
    """处理用户发送的语音/音频消息"""
    await update.message.reply_text("🎧 正在处理录音，请稍候...")
    
    # 下载录音
    audio_file = await update.message.voice.get_file()
    with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as tmp:
        await audio_file.download_to_drive(tmp.name)
        tmp_path = tmp.name
    
    # 处理
    summary = process_meeting(tmp_path, language="zh", whisper_model="small")
    os.unlink(tmp_path)
    
    await update.message.reply_text(f"📋 会议纪要：\n\n{summary}")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.VOICE, handle_audio))
    app.run_polling()

if __name__ == "__main__":
    main()
```

### 5.2 集成 n8n 自动化

如果已在 VPS 上部署 n8n，可以用 Webhook 串联整个流程：

```
录音上传 → Google Drive/Dropbox 监控
  → n8n Webhook 触发
    → 调用 Whisper API 转录
      → 调用 Ollama 总结
        → 发送到 Slack/Telegram/Email
```

## 生产环境优化

### 性能优化

1. **使用 GPU 加速**：有 GPU 的 VPS（如 RunPod、Vast.ai）可使 Whisper 提速 5-10 倍
2. **批量处理**：用 `concurrent.futures` 并行处理多个音频文件
3. **模型缓存**：Whisper 首次加载后会缓存模型，后续处理更快

### 存储管理

```bash
# 设置自动清理脚本（每月运行一次）
find ~/meeting_notes -name "*.json" -mtime +90 -delete
find ~/meeting_notes -name "*.txt" -mtime +90 -delete
```

### 安全建议

- 用 Caddy 反向代理 Web UI，自动获取 HTTPS 证书
- 为 Whisper API 添加简单认证（如 nginx basic auth）
- 定期备份会议记录到对象存储

## 总结

至此，你已经拥有了一台完全私有的 AI 会议记录助手：

| 能力 | 实现方式 |
|------|---------|
| 🎤 语音转文字 | Whisper (`base`-`large`) |
| 🤖 智能总结 | Ollama + Llama 3.1/Qwen 2.5 |
| 🌐 Web 界面 | Streamlit |
| 📱 移动端 | Telegram Bot |
| 🔒 数据隐私 | 全程本地处理 |

**成本估算：**

- VPS（4核 8GB）：约 $10-15/月
- 存储费用：转录结果很小，< 1GB/月
- API 费用：$0（全部使用开源模型）
- 对比在线服务：Otter.ai $16.99/月，Fireflies.ai $18/月

**下一步：** 试试在 VPS 上部署 [Open WebUI](https://github.com/open-webui/open-webui)，把会议转录作为知识库的一环，实现「向你的所有会议记录提问」的能力。
