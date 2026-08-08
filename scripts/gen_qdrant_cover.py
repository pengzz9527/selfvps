#!/usr/bin/env python3
"""Generate dark gradient featured cover for Qdrant article."""
import os
import sys
from PIL import Image, ImageDraw, ImageFont

# Configuration
WIDTH, HEIGHT = 1200, 630
SLUG = "qdrant-selfhost-vector-database"
TITLE_CHINESE = "Qdrant 自托管向量数据库"
TITLE_ENGLISH = "Self-Hosted Qdrant Vector Database"
SUBTITLE = "替代云端付费方案 · 90%+ 成本节省 · AI 降本指南"
CATEGORY = "云省钱 / Cloud Savings"

# Color definitions
COLOR_BG_START = (15, 23, 42)      # #0f172a
COLOR_BG_END = (30, 41, 59)        # #1e293b
COLOR_TITLE = (255, 255, 255)      # White
COLOR_SUBTITLE = (148, 163, 184)   # #94a3b8 - light gray
COLOR_URL = (99, 102, 241)         # #6366f1 - indigo
COLOR_ACCENT = (99, 102, 241)      # indigo for decorations

def get_font(size, bold=False):
    """Try to load NotoSansCJK font, fallback to default if not found."""
    font_paths = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    ]
    if bold:
        path_candidates = [p for p in font_paths if "Bold" in p]
    else:
        path_candidates = [p for p in font_paths if "Regular" in p or "Bold" not in p]

    for path in path_candidates:
        try:
            return ImageFont.truetype(path, size)
        except (IOError, OSError):
            continue
    # Fallback to default font (may not support Chinese)
    try:
        return ImageFont.truetype("/usr/share/fonts/dejavu/DejaVuSans.ttf", size)
    except Exception:
        return ImageFont.load_default()

def draw_gradient_background(draw, width, height):
    """Create vertical gradient from top color to bottom color."""
    for y in range(height):
        # Interpolate colors based on position
        ratio = y / height
        r = int(COLOR_BG_START[0] * (1 - ratio) + COLOR_BG_END[0] * ratio)
        g = int(COLOR_BG_START[1] * (1 - ratio) + COLOR_BG_END[1] * ratio)
        b = int(COLOR_BG_START[2] * (1 - ratio) + COLOR_BG_END[2] * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b))

def draw_decorative_elements(draw, width, height):
    """Draw rounded corner lines and glow effects."""
    # Top-right glowing arc
    draw.ellipse(
        [(width - 200, -50), (width + 50, 200)],
        outline=(99, 102, 241, 30),
        width=2
    )
    
    # Bottom-left rounded accent line
    draw.rounded_rectangle(
        [(50, height - 150), (200, height - 50)],
        radius=20,
        outline=(99, 102, 241, 40),
        width=3
    )
    
    # Center subtle dot pattern
    for i in range(5):
        x = 300 + i * 150
        y = height // 2
        draw.ellipse(
            [(x - 2, y - 2), (x + 2, y + 2)],
            fill=(148, 163, 184, 20)
        )

def main():
    # Create image with initial background
    img = Image.new("RGB", (WIDTH, HEIGHT), COLOR_BG_START)
    draw = ImageDraw.Draw(img)

    # Draw gradient background
    draw_gradient_background(draw, WIDTH, HEIGHT)

    # Decorative elements
    draw_decorative_elements(draw, WIDTH, HEIGHT)

    # Try to load fonts
    title_font_chinese = get_font(52, bold=True)
    title_font_english = get_font(44, bold=True)
    subtitle_font = get_font(26, bold=False)
    url_font = get_font(14, bold=False)

    # Calculate positions for multi-line Chinese title
    title_chinese_lines = []
    try:
        # Try to measure text and split if too wide
        bbox_chinese = title_font_chinese.measure(TITLE_CHINESE)
        if bbox_chinese > WIDTH - 200:
            # Split into two lines
            mid = len(TITLE_CHINESE) // 2
            title_chinese_lines = [TITLE_CHINESE[:mid], TITLE_CHINESE[mid:]]
        else:
            title_chinese_lines = [TITLE_CHINESE]
    except Exception:
        title_chinese_lines = [TITLE_CHINESE]

    # Title Y position (centered vertically with padding)
    title_start_y = (HEIGHT - 200) // 2

    # Draw English title above Chinese
    try:
        english_bbox = title_font_english.measure(TITLE_ENGLISH)
        english_x = (WIDTH - english_bbox) // 2
        draw.text((english_x, title_start_y - 80), TITLE_ENGLISH, font=title_font_english, fill=COLOR_TITLE)
    except Exception:
        pass

    # Draw Chinese title lines
    for i, line in enumerate(title_chinese_lines):
        try:
            bbox = title_font_chinese.measure(line)
            x = (WIDTH - bbox) // 2
            draw.text((x, title_start_y + i * 60), line, font=title_font_chinese, fill=COLOR_TITLE)
        except Exception:
            draw.text((50, title_start_y + i * 60), line, font=title_font_chinese, fill=COLOR_TITLE)

    # Draw subtitle
    try:
        subtitle_bbox = subtitle_font.measure(SUBTITLE)
        subtitle_x = (WIDTH - subtitle_bbox) // 2
        draw.text((subtitle_x, title_start_y + len(title_chinese_lines) * 60 + 30), SUBTITLE, font=subtitle_font, fill=COLOR_SUBTITLE)
    except Exception:
        draw.text((50, title_start_y + len(title_chinese_lines) * 60 + 30), SUBTITLE, font=subtitle_font, fill=COLOR_SUBTITLE)

    # Draw category badge at bottom left
    try:
        category_text = f"[ {CATEGORY} ]"
        category_bbox = subtitle_font.measure(category_text)
        cat_x = 50
        cat_y = HEIGHT - 80
        draw.rounded_rectangle(
            [(cat_x - 10, cat_y - 15), (cat_x + category_bbox + 10, cat_y + 15)],
            radius=8,
            fill=(99, 102, 241, 20),
            outline=COLOR_ACCENT,
            width=1
        )
        draw.text((cat_x, cat_y - 12), category_text, font=subtitle_font, fill=COLOR_ACCENT)
    except Exception:
        pass

    # Draw URL at bottom right (indigo, 14px)
    url_text = "selfvps.net"
    try:
        url_bbox = url_font.measure(url_text)
        url_x = WIDTH - url_bbox - 50
        url_y = HEIGHT - 30
        draw.text((url_x, url_y), url_text, font=url_font, fill=COLOR_URL)
    except Exception:
        draw.text((WIDTH - 150, HEIGHT - 30), url_text, font=url_font, fill=COLOR_URL)

    # Add glow effect around title (optional overlay)
    try:
        glow_layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow_layer)
        for i in range(3):
            glow_draw.ellipse(
                [(title_start_y - 100 - i*2, -i*5), (title_start_y + 200 + i*2, HEIGHT - 50 + i*5)],
                outline=(99, 102, 241, 10 if i == 2 else 5)
            )
        img = Image.alpha_composite(img.convert("RGBA"), glow_layer).convert("RGB")
    except Exception:
        pass

    # Ensure output directory exists
    output_dir = f"static/images/posts/{SLUG}"
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "featured.png")

    # Save image
    img.save(output_path, "PNG")
    print(f"Saved: {output_path}")
    print(f"Dimensions: {WIDTH}x{HEIGHT}")

if __name__ == "__main__":
    main()
