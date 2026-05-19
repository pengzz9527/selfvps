#!/usr/bin/env python3
"""Fetch Khoj docs for setup info."""
import json, sys
try:
    import urllib.request
    # Try to get docker-compose or setup from docs
    urls = [
        "https://raw.githubusercontent.com/khoj-ai/khoj/master/docker-compose.yml",
        "https://raw.githubusercontent.com/khoj-ai/khoj/master/docker-compose.gpu.yml",
        "https://raw.githubusercontent.com/khoj-ai/khoj/master/docker/Dockerfile",
    ]
    for url in urls:
        req = urllib.request.Request(url, headers={"User-Agent": "Hermes-Agent/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                content = resp.read().decode('utf-8')
                print(f"=== {url.split('/')[-1]} ===")
                print(content[:500])
                print("...")
                print()
        except Exception as e:
            print(f"=== {url.split('/')[-1]} === FAILED: {e}")
            print()
except Exception as e:
    print(f"Error: {e}", file=sys.stderr)
    sys.exit(1)
