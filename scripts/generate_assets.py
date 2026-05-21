"""Generate favicon and social-card OG image for selfvps.net"""
from PIL import Image, ImageDraw, ImageFont
import os, math

output_dir = "/root/selfvps/static"

# === 1. Favicon (96x96 PNG + SVG fallback) ===
# PNG favicon
favicon_size = 96
img = Image.new("RGBA", (favicon_size, favicon_size), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

# Draw a VPS/server icon: simple rounded rectangle with inner glow
cx, cy = favicon_size // 2, favicon_size // 2
r = 38

# Outer glow ring
for i in range(6, 1, -1):
    alpha = int(60 / i)
    draw.ellipse(
        [cx - r - i, cy - r - i, cx + r + i, cy + r + i],
        fill=(59, 130, 246, alpha),  # blue-500 glow
    )

# Main circle
draw.ellipse(
    [cx - r, cy - r, cx + r, cy + r],
    fill=(30, 64, 175),  # blue-800
)

# Inner circle highlight
draw.ellipse(
    [cx - r + 8, cy - r + 8, cx + r - 8, cy + r - 8],
    fill=(37, 99, 235),  # blue-600
)

# Server icon - simple stylized server rack
# Top indicator light
draw.ellipse([cx - 18, cy - 15, cx - 6, cy - 3], fill=(34, 197, 94))
draw.ellipse([cx + 6, cy - 15, cx + 18, cy - 3], fill=(34, 197, 94))

# Server slots
for idx, yy in enumerate([cy + 5, cy + 16, cy + 27]):
    draw.rectangle(
        [cx - 22, yy, cx + 22, yy + 7],
        fill=(59, 130, 246) if idx == 0 else (96, 165, 250),
    )

# S letter
try:
    font_large = ImageFont.truetype("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc", 18)
except:
    font_large = ImageFont.load_default()

img.save(os.path.join(output_dir, "favicon.png"), "PNG")
print("✅ Favicon PNG saved")

# === 2. Social-card (1200×630 OG image) ===
w, h = 1200, 630
card = Image.new("RGBA", (w, h), (15, 23, 42))  # slate-950
draw = ImageDraw.Draw(card)

# Gradient background - draw horizontal gradient
for x in range(w):
    ratio = x / w
    r_val = int(15 + ratio * 20)
    g_val = int(23 + ratio * 15)
    b_val = int(42 + ratio * 20)
    draw.line([(x, 0), (x, h)], fill=(r_val, g_val, b_val))

# Accent glow at top-right
for i in range(80, 0, -1):
    alpha = max(0, int(15 - 15 * (i / 80)))
    draw.ellipse(
        [w - 500 + i, -200 + i, w - 100 - i, 200 - i],
        fill=(59, 130, 246, alpha),
    )

# Bottom-left accent
for i in range(60, 0, -1):
    alpha = max(0, int(10 - 10 * (i / 60)))
    draw.ellipse(
        [50 + i, h - 250 + i, 250 - i, h - 50 - i],
        fill=(139, 92, 246, alpha),
    )

# Title
try:
    font_title = ImageFont.truetype("/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc", 64)
    font_sub = ImageFont.truetype("/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf", 28)
    font_url = ImageFont.truetype("/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf", 20)
except:
    try:
        font_title = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", 56)
        font_sub = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", 24)
        font_url = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", 18)
    except:
        font_title = ImageFont.load_default()
        font_sub = ImageFont.load_default()
        font_url = ImageFont.load_default()

# Title lines
lines = ["SelfVPS 指南", "自托管 · 云省钱 · VPS 运维"]
y_start = 140
for i, line in enumerate(lines):
    font = font_title if i == 0 else font_sub
    color = (255, 255, 255) if i == 0 else (148, 163, 184)  # white / slate-400
    draw.text((80, y_start + i * 80), line, fill=color, font=font)

# Decorative line
draw.rectangle([80, 380, 400, 386], fill=(59, 130, 246))

# Features
features = [
    "✓ 开源工具自托管部署",
    "✓ 云服务器省钱攻略",
    "✓ Docker/Caddy/Traefik 实战",
    "✓ AI 模型本地化部署",
]
y_feat = 420
for feat in features:
    draw.text((80, y_feat), feat, fill=(148, 163, 184), font=font_sub)
    y_feat += 44

# URL
draw.text((80, h - 60), "selfvps.net", fill=(99, 102, 241), font=font_url)

card_path = os.path.join(output_dir, "social-card.png")
card.save(card_path, "PNG")
print(f"✅ Social-card saved: {card_path}")

# Verify dimensions
card_check = Image.open(card_path)
print(f"   Size: {card_check.size[0]}x{card_check.size[1]}, {os.path.getsize(card_path)} bytes")
