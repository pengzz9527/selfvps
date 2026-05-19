#!/usr/bin/env python3
"""Fetch details about specific GitHub repos."""
import json, sys
try:
    import urllib.request
    repos = ["khoj-ai/khoj", "1Panel-dev/1Panel", "sillynxiao/xiaoju", "kossakovsky/n8n-install"]
    for repo in repos:
        url = f"https://api.github.com/repos/{repo}"
        req = urllib.request.Request(url, headers={"User-Agent": "Hermes-Agent/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            d = json.loads(resp.read().decode())
            print(f"=== {repo} ===")
            print(f"Description: {d.get('description','N/A')}")
            print(f"Stars: {d.get('stargazers_count')}")
            print(f"Language: {d.get('language')}")
            print(f"Topics: {d.get('topics',[])}")
            print(f"License: {d.get('license',{}).get('spdx_id','N/A') if d.get('license') else 'N/A'}")
            print(f"Created: {d.get('created_at')}")
            print(f"Updated: {d.get('updated_at')}")
            print()
except Exception as e:
    print(f"Error: {e}", file=sys.stderr)
    sys.exit(1)
