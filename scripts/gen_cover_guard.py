#!/usr/bin/env python3
"""Guard wrapper for generate_dark_cover.py: skips gracefully when a
1200x630 cover already exists, validates output, supports zh/en variants."""
import argparse
import os
import subprocess
import sys

GEN = "/root/.hermes/scripts/generate_dark_cover.py"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--title", required=True)
    ap.add_argument("--subtitle", default="")
    ap.add_argument("--category", default="")
    ap.add_argument("--width", type=int, default=1200)
    ap.add_argument("--height", type=int, default=630)
    ap.add_argument("--output", required=True)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()

    os.makedirs(os.path.dirname(a.output) or ".", exist_ok=True)

    if os.path.exists(a.output) and not a.force:
        print(f"skip existing: {a.output}")
        return 0

    if not os.path.exists(GEN):
        print(f"ERROR: generator missing: {GEN}", file=sys.stderr)
        return 2

    cmd = [
        sys.executable, GEN,
        "--title", a.title,
        "--subtitle", a.subtitle,
        "--category", a.category,
        "--width", str(a.width),
        "--height", str(a.height),
        "--output", a.output,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    sys.stdout.write(r.stdout)
    if r.returncode != 0:
        sys.stderr.write(r.stderr)
        return r.returncode

    if not os.path.exists(a.output) or os.path.getsize(a.output) < 5000:
        print(f"ERROR: cover not produced or too small: {a.output}", file=sys.stderr)
        return 3

    print(f"ok: {a.output} ({os.path.getsize(a.output)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
