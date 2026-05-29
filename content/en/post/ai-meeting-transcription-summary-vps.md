---
title: "Build an AI Meeting Note-Taker on VPS: Whisper Transcription + LLM Summarization"
description: "One hour of meetings = 30 minutes of note-taking. Stop it. Deploy a private AI meeting assistant on your VPS — Whisper auto-transcribes speech to text, local LLM generates summaries, action items, and key decisions. All data stays on your server. Supports Zoom/Teams/local recordings."
date: 2026-05-29T21:30:00+08:00
slug: "ai-meeting-transcription-summary-vps"
tags: ["Whisper", "LLM", "Meeting Transcription", "Speech-to-Text", "Ollama", "Self-hosting", "AI Summary", "Automation"]
categories: ["AI Tools"]
image: /images/posts/ai-meeting-transcription-summary-vps/featured.png
draft: false
---

## Why Build Your Own Meeting Assistant?

How many hours do you spend in meetings each week? And how much more time writing up notes? With cloud transcription services, you're also sending sensitive business conversations to third-party servers.

**Self-hosted vs. Cloud services:**

| Feature | Cloud Service | Self-Hosted |
|---------|--------------|-------------|
| Data Privacy | Uploaded to 3rd party | ✅ Stays on your VPS |
| Cost | $10-30/month subscription | 💰 One-time setup + VPS cost |
| Model Choice | Vendor locked | ✅ Switch Whisper models freely |
| Integration | Limited API | ✅ Connect to n8n/Slack/Telegram |
| Custom Prompts | ❌ Fixed templates | ✅ Fully customizable summaries |

### Perfect For

- **Startups** that don't want meeting recordings on third-party servers
- **Freelancers** who need automated client call notes
- **Researchers** batch-transcribing lectures and interviews
- **Anyone privacy-conscious** — your meetings belong to you

## Architecture Overview

```
┌─────────────┐    ┌──────────────┐    ┌─────────────┐
│  Audio File  │───→│  Whisper     │───→│  Raw Text    │
│ (MP3/MP4/WAV)│    │  Speech→Text │    │  (SRT/TXT)  │
└─────────────┘    └──────────────┘    └─────────────┘
                                            │
                                            ▼
┌─────────────┐    ┌──────────────┐    ┌─────────────┐
│  Telegram/  │←───│  Local LLM   │←───│  Chunked    │
│  Web UI     │    │  (Ollama)    │    │  Text       │
└─────────────┘    └──────────────┘    └─────────────┘
                          │
                          ▼
              ┌─────────────────────┐
              │  Summary + Actions  │
              │  Decisions + Timeline│
              └─────────────────────┘
```

## System Requirements

### Minimum (small model + short audio)

| Component | Requirement |
|-----------|-------------|
| VPS | 2 vCPU, 4GB RAM, 20GB disk |
| Model | Whisper `tiny` or `base` |

### Recommended (daily use)

| Component | Requirement |
|-----------|-------------|
| VPS | 4 vCPU, 8GB RAM, 40GB disk |
| Model | Whisper `small` + Llama 3.1 8B |
| GPU | Nice-to-have, not required |

> 💡 **GPU Note**: If your VPS has an NVIDIA GPU (e.g., RunPod, Vast.ai), Whisper transcription is 5-10x faster. CPU-only is perfectly usable — a 1-hour meeting takes ~10-20 minutes with `small` model on CPU.

## Step 1: Deploy Whisper Transcription Service

### 1.1 Install Docker

```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER
```

### 1.2 Run Whisper ASR Server

We'll use `whisper-asr-webservice` — a ready-to-use Docker image wrapping OpenAI Whisper as an HTTP API.

```bash
docker run -d \
  --name whisper-server \
  -p 9000:9000 \
  -e ASR_MODEL=base \
  -e ASR_ENGINE=openai_whisper \
  --restart unless-stopped \
  onerahmet/openai-whisper-asr-webservice:latest-gpu
```

> If your VPS has a GPU, add `--gpus all` to the docker run command.

**Verify it's running:**

```bash
curl http://localhost:9000/health
# Returns: {"status": "ok"}
```

**Test transcription:**

```bash
curl -X POST http://localhost:9000/asr \
  -F "audio_file=@meeting.mp3" \
  -F "response_format=text"
```

### 1.3 Model Size Guide

| Model | Params | Speed | Accuracy | Disk | Use Case |
|-------|--------|-------|----------|------|----------|
| `tiny` | 39M | ⚡⚡⚡⚡⚡ | Fair | ~150MB | Quick testing |
| `base` | 74M | ⚡⚡⚡⚡ | Good | ~290MB | Daily use |
| `small` | 244M | ⚡⚡⚡ | Very Good | ~950MB | Quality transcription |
| `medium` | 769M | ⚡⚡ | Excellent | ~3GB | Noisy environments |
| `large-v3` | 1.55B | ⚡ | Best | ~6GB | Multi-language/professional |

For English meetings, `small` or `medium` provides excellent results for most scenarios.

## Step 2: Deploy Ollama + Local LLM

### 2.1 Install Ollama

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

### 2.2 Pull a Recommended Model

```bash
# Best all-rounder for summaries
ollama pull llama3.1:8b

# If you have limited RAM
ollama pull gemma2:9b     # Excellent for English
ollama pull qwen2.5:7b    # Strong multilingual support
```

### 2.3 Verify the LLM Works

```bash
ollama run llama3.1:8b "Summarize this in one sentence: The team discussed migrating to a microservices architecture with Kubernetes orchestration."
```

## Step 3: Build the Meeting Processing Pipeline

### 3.1 Create the Processing Script

Here's the complete auto-transcription + summarization script:

```python
#!/usr/bin/env python3
"""
AI Meeting Assistant: Auto-transcribe + Smart Summarization
Supports: local files, URL downloads, directory watching
"""

import os
import sys
import json
import time
import argparse
import requests
from pathlib import Path

# ── Config ─────────────────────────────────────────
WHISPER_URL = "http://localhost:9000/asr"
OLLAMA_URL = "http://localhost:11434/api/generate"
LLM_MODEL = "llama3.1:8b"

OUTPUT_DIR = Path.home() / "meeting_notes"
OUTPUT_DIR.mkdir(exist_ok=True)

# ── Whisper Transcription ──────────────────────────

def transcribe_audio(audio_path: str, model: str = "base",
                     language: str = "en") -> str:
    """Transcribe audio using Whisper API"""
    print(f"[Transcribe] Processing: {audio_path}")
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
    print(f"[Transcribe] Done! {len(text)} characters")
    return text

# ── LLM Summarization ──────────────────────────────

SUMMARY_PROMPT_TEMPLATE = """You are a professional meeting minutes assistant. Based on the following meeting transcript, generate a well-structured meeting summary.

Include these sections:
1. **Meeting Overview**: One-sentence summary of the meeting topic
2. **Discussion Points**: Key discussion items in order of importance
3. **Decisions Made**: Clearly documented decisions
4. **Action Items**: Tasks to follow up, formatted as "Owner: Task"
5. **Timeline**: Key dates or milestones if any

Transcript:
{transcript}
"""

def generate_summary(transcript: str) -> str:
    """Generate meeting summary using local LLM"""
    print("[Summarize] Generating meeting minutes...")
    prompt = SUMMARY_PROMPT_TEMPLATE.format(
        transcript=transcript[:8000]
    )
    payload = {
        "model": LLM_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.3,
            "num_predict": 2048
        }
    }
    resp = requests.post(OLLAMA_URL, json=payload, timeout=120)
    resp.raise_for_status()
    summary = resp.json()["response"]
    print(f"[Summarize] Done! {len(summary)} characters")
    return summary

# ── Main Pipeline ──────────────────────────────────

def process_meeting(audio_path: str, language: str = "en",
                    whisper_model: str = "base"):
    """Full pipeline: transcribe → summarize → save"""
    audio_file = Path(audio_path)
    base_name = audio_file.stem
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    
    # 1. Transcribe
    transcript = transcribe_audio(audio_path, model=whisper_model, language=language)
    
    transcript_file = OUTPUT_DIR / f"{base_name}_{timestamp}_transcript.txt"
    transcript_file.write_text(transcript)
    print(f"[Save] Transcript: {transcript_file}")
    
    # 2. Summarize
    summary = generate_summary(transcript)
    
    summary_file = OUTPUT_DIR / f"{base_name}_{timestamp}_summary.md"
    summary_file.write_text(summary)
    print(f"[Save] Summary: {summary_file}")
    
    # 3. Save full record as JSON
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
    print(f"[Save] Full record: {json_file}")
    
    return summary

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI Meeting Assistant")
    parser.add_argument("audio", help="Path to audio file")
    parser.add_argument("--lang", default="en", help="Audio language (en/zh/ja)")
    parser.add_argument("--model", default="base", help="Whisper model size")
    args = parser.parse_args()
    
    summary = process_meeting(args.audio, args.lang, args.model)
    print("\n" + "="*50)
    print("📋 Meeting Minutes")
    print("="*50)
    print(summary)
```

### 3.2 Test It

```bash
# Install dependencies
pip install requests

# Transcribe and summarize an English recording
python3 meeting_assistant.py team_sync.mp3 --lang en --model small
```

## Step 4: Build a Web Upload Interface (Optional)

Use Streamlit for a visual interface:

### 4.1 Install Streamlit

```bash
pip install streamlit
```

### 4.2 Create the Web App

```python
# app.py
import streamlit as st
import tempfile
import os
from meeting_assistant import process_meeting

st.set_page_config(page_title="AI Meeting Assistant", layout="wide")
st.title("🎙️ AI Meeting Transcription & Summary")

st.markdown("Upload a meeting recording to get instant transcription and smart summaries.")

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("📤 Upload Recording")
    audio_file = st.file_uploader(
        "Choose an audio file (MP3, WAV, M4A)",
        type=["mp3", "wav", "m4a", "ogg"]
    )
    
    if audio_file:
        st.audio(audio_file, format="audio/mp3")
    
    lang = st.selectbox("Audio Language", ["English", "中文", "日本語"])
    model_size = st.selectbox(
        "Whisper Model",
        ["base", "small", "medium"],
        index=1
    )
    
    lang_map = {"English": "en", "中文": "zh", "日本語": "ja"}
    
    if st.button("Process 🚀", disabled=not audio_file):
        with st.spinner("Transcribing..."):
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
                st.subheader("📋 Meeting Minutes")
                st.markdown(summary)

with col2:
    st.subheader("💡 Tips")
    st.info("""
    - Supported formats: MP3, WAV, M4A, OGG
    - Recommended quality: ≥16kHz sample rate
    - File limit: constrained by VPS disk space
    - Processing time: ~10-20 min per hour of audio
    """)
```

### 4.3 Launch the Web UI

```bash
streamlit run app.py --server.port 8501 --server.address 0.0.0.0
```

Protect it with a reverse proxy (Caddy/Nginx) for HTTPS and authentication.

## Step 5: Integrate with Messaging Tools

### 5.1 Telegram Bot

Receive recordings and get summaries via Telegram:

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
    """Handle voice/audio messages"""
    await update.message.reply_text("🎧 Processing your recording...")
    
    audio_file = await update.message.voice.get_file()
    with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as tmp:
        await audio_file.download_to_drive(tmp.name)
        tmp_path = tmp.name
    
    summary = process_meeting(tmp_path, language="en", whisper_model="small")
    os.unlink(tmp_path)
    
    await update.message.reply_text(f"📋 Meeting Minutes:\n\n{summary}")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.VOICE, handle_audio))
    app.run_polling()

if __name__ == "__main__":
    main()
```

### 5.2 Connect with n8n

If you're already running n8n on your VPS, chain the workflow:

```
Recording uploaded → Google Drive/Dropbox watch
  → n8n Webhook trigger
    → Call Whisper API → transcribe
      → Call Ollama → summarize
        → Send to Slack/Telegram/Email
```

## Production Optimization

### Performance Tuning

1. **GPU acceleration**: GPU-backed VPS (RunPod, Vast.ai) speeds Whisper 5-10x
2. **Batch processing**: Use `concurrent.futures` for parallel file processing
3. **Model caching**: Whisper caches models after first load — subsequent runs are faster

### Storage Management

```bash
# Auto-cleanup (run monthly via cron)
find ~/meeting_notes -name "*.json" -mtime +90 -delete
find ~/meeting_notes -name "*.txt" -mtime +90 -delete
```

### Security Practices

- Use Caddy as a reverse proxy for the Web UI (auto-HTTPS)
- Add basic auth to the Whisper API with nginx
- Back up meeting notes to object storage periodically

## Summary

You now have a fully private AI meeting assistant running on your own VPS:

| Capability | Implementation |
|-----------|---------------|
| 🎤 Speech-to-Text | Whisper (`base`-`large`) |
| 🤖 Smart Summarization | Ollama + Llama 3.1/Qwen 2.5 |
| 🌐 Web Interface | Streamlit |
| 📱 Mobile Access | Telegram Bot |
| 🔒 Data Privacy | 100% local processing |

**Cost Breakdown:**

- VPS (4 vCPU, 8GB): ~$10-15/month
- Storage: Minimal — transcripts are text
- API fees: $0 (all open-source models)
- vs. Cloud: Otter.ai $16.99/mo, Fireflies.ai $18/mo

**Next Steps:** Try deploying [Open WebUI](https://github.com/open-webui/open-webui) on your VPS and feed meeting transcripts into a searchable knowledge base. Soon you'll be able to "ask questions about all your past meetings."
