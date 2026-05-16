#!/bin/bash
# SelfVPS Blog - Deploy Script
set -e

cd "$(dirname "$0")"

echo "🔨 Building Hugo site..."
hugo --gc --minify

echo "✅ Build complete: public/"

if git remote -v | grep -q origin; then
    echo "📤 Pushing to GitHub..."
    git add -A
    git commit -m "blog: auto-update $(date +%Y-%m-%d)"
    git push origin master
    echo "✅ Deployed!"
else
    echo "⚠️  No git remote configured."
fi
