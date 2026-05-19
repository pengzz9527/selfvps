#!/usr/bin/env python3
"""Fetch Khoj README and docs for deployment info."""
import json, sys, re
try:
    import urllib.request
    # Get README from GitHub API
    url = "https://api.github.com/repos/khoj-ai/khoj/readme"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Hermes-Agent/1.0",
        "Accept": "application/vnd.github.v3+json"
    })
    with urllib.request.urlopen(req, timeout=15) as resp:
        d = json.loads(resp.read().decode())
        import base64
        content = base64.b64decode(d['content']).decode('utf-8')
        # Print first 200 lines
        lines = content.split('\n')
        for line in lines[:200]:
            print(line)
except Exception as e:
    print(f"Error: {e}", file=sys.stderr)
    sys.exit(1)
