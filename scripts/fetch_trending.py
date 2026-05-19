#!/usr/bin/env python3
"""Fetch trending AI projects from GitHub for article inspiration."""
import json
import urllib.request
import urllib.error
import sys

queries = [
    ("mcp+server", "MCP Server"),
    ("ai+agent+self-hosted", "AI Agent Self-hosted"),
    ("ollama+tools+deploy", "Ollama Tools"),
    ("vps+ai+deployment", "VPS+AI Deployment"),
]

seen = set()
results = []

for q, label in queries:
    url = f"https://api.github.com/search/repositories?q={q}&sort=stars&order=desc&per_page=5"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Hermes-Agent/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            for r in data.get("items", []):
                name = r["full_name"]
                if name not in seen:
                    seen.add(name)
                    results.append({
                        "name": name,
                        "stars": r["stargazers_count"],
                        "desc": r.get("description") or "N/A",
                        "url": r["html_url"],
                        "topic": label,
                    })
    except Exception as e:
        print(f"Query '{q}' failed: {e}", file=sys.stderr)

results.sort(key=lambda x: x["stars"], reverse=True)
for r in results:
    print(f"{r['name']} | ⭐{r['stars']} | [{r['topic']}] {r['desc'][:120]}")
    print(f"  {r['url']}")
    print()
