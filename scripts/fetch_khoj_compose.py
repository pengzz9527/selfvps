#!/usr/bin/env python3
"""Fetch full docker-compose.yml from Khoj."""
import json, sys
try:
    import urllib.request
    url = "https://raw.githubusercontent.com/khoj-ai/khoj/master/docker-compose.yml"
    req = urllib.request.Request(url, headers={"User-Agent": "Hermes-Agent/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        content = resp.read().decode('utf-8')
        print(content)
except Exception as e:
    print(f"Error: {e}", file=sys.stderr)
    sys.exit(1)
