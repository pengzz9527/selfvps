#!/usr/bin/env python3
"""Generate dark gradient cover image for VPS Memory Optimization article."""
import os
from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 1200, 630
FONT_BOLD = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
FONT_REGULAR = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"

def wrap_text(text, font, max_width, draw):
    lines = []
    for paragraph in text.split('\n'):
        if not paragraph.strip():
            lines.append('')
            continue
        current_line = ''
        for char in paragraph:
            test_line = current_line + char
            bbox = draw.textbbox((0, 0), test_line, font=font)
            if bbox[2] - bbox[0] > max_width:
                if current_line:
                    lines.append(current_line)
                current_line = char
            else:
                current_line = test_line
        if current_line:
            lines.append(current_line)
    return lines

def generate_cover(title_lines, subtitle, category, output_path):
    img = Image.new('RGB', (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(img)

    # Dark gradient background #0f172a → #1e293b
    for y in range(HEIGHT):
        ratio = y / HEIGHT
        r = int(15 + ratio * 13)
        g = int(23 + ratio * 18)
        b = int(42 + ratio * 25)
        draw.line([(0, y), (WIDTH, y)], fill=(r, g, b))

    # Top accent line - indigo glow
    draw.rectangle([0, 0, WIDTH, 4], fill=(99, 102, 241))
    draw.rectangle([0, 4, WIDTH, 8], fill=(99, 102, 241, 80))

    # Decorative elements - glowing circles
    draw.ellipse([WIDTH - 250, -80, WIDTH - 50, 120], fill=(99, 102, 241, 25))
    draw.ellipse([WIDTH - 180, -20, WIDTH - 10, 180], fill=(99, 102, 241, 15))
    draw.ellipse([20, HEIGHT - 150, 180, HEIGHT + 10], fill=(67, 56, 202, 20))

    # Bottom right corner accent
    draw.rectangle([WIDTH - 100, HEIGHT - 60, WIDTH, HEIGHT], fill=(99, 102, 241, 12))
    draw.line([(WIDTH - 100, HEIGHT - 30), (WIDTH - 30, HEIGHT - 30)], fill=(99, 102, 241, 40), width=2)
    draw.line([(WIDTH - 60, HEIGHT - 60), (WIDTH - 60, HEIGHT - 30)], fill=(99, 102, 241, 40), width=2)

    # Left vertical accent line
    draw.rectangle([40, 150, 44, HEIGHT - 80], fill=(99, 102, 241, 60))

    # Title text
    title_font = ImageFont.truetype(FONT_BOLD, 52)
    total_title_h = 0
    all_lines = []
    for title in title_lines:
        lines = wrap_text(title, title_font, WIDTH - 160, draw)
        all_lines.extend(lines)
        total_title_h += len(lines) * 64

    start_y = max(100, (HEIGHT // 2 - 60 - total_title_h // 2))
    for i, line in enumerate(all_lines):
        bbox = draw.textbbox((0, 0), line, font=title_font)
        text_w = bbox[2] - bbox[0]
        x = 90
        y = start_y + i * 64
        draw.text((x, y), line, fill=(255, 255, 255), font=title_font)

    # Subtitle
    if subtitle:
        sub_font = ImageFont.truetype(FONT_REGULAR, 26)
        bbox = draw.textbbox((0, 0), subtitle, font=sub_font)
        text_w = bbox[2] - bbox[0]
        x = (WIDTH - text_w) // 2
        y = start_y + total_title_h + 30
        draw.text((x, y), subtitle, fill=(148, 163, 184), font=sub_font)

    # Category badge
    if category:
        tag_font = ImageFont.truetype(FONT_BOLD, 20)
        tag_bbox = draw.textbbox((0, 0), category, font=tag_font)
        tag_w = tag_bbox[2] - tag_bbox[0] + 24
        tag_x = 90
        tag_y = HEIGHT - 55
        draw.rectangle([tag_x, tag_y, tag_x + tag_w, tag_y + 32], fill=(99, 102, 241))
        draw.text((tag_x + 12, tag_y + 6), category, fill=(255, 255, 255), font=tag_font)

    # Domain URL bottom right
    domain_font = ImageFont.truetype(FONT_REGULAR, 16)
    draw.text((WIDTH - 200, HEIGHT - 45), "selfvps.net", fill=(99, 102, 241), font=domain_font)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    img.save(output_path, "PNG")
    print(f"Cover saved: {output_path}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--title', required=True, nargs='+')
    parser.add_argument('--subtitle', default='')
    parser.add_argument('--category', default='')
    parser.add_argument('--width', type=int, default=1200)
    parser.add_argument('--height', type=int, default=630)
    parser.add_argument('--output', default='cover.png')
    args = parser.parse_args()
    generate_cover(args.title, args.subtitle, args.category, args.output)
