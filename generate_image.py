#!/usr/bin/env python3
"""Generate featured images for blog posts."""
import sys
import os
from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 1200, 630
FONT_BOLD = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
FONT_REGULAR = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"


def generate_post_image(slug: str, title_lines: list, subtitle: str):
    """Generate a 1200x630 featured image for a blog post."""
    img = Image.new("RGB", (WIDTH, HEIGHT), (15, 23, 42))
    draw = ImageDraw.Draw(img)

    font_title = ImageFont.truetype(FONT_BOLD, 64)
    font_subtitle = ImageFont.truetype(FONT_REGULAR, 28)
    font_tag = ImageFont.truetype(FONT_BOLD, 22)

    # Subtle top gradient
    for y in range(HEIGHT):
        alpha = int(35 * (1 - y / HEIGHT))
        draw.rectangle([(0, y), (WIDTH, y)], fill=(alpha, alpha, alpha * 2))

    # Accent bar at top
    draw.rectangle([(0, 0), (WIDTH, 6)], fill=(0, 120, 255))

    # Decorative circles
    draw.ellipse([(WIDTH - 300, -100), (WIDTH - 100, 100)], fill=(0, 80, 180, 40))
    draw.ellipse([(-60, HEIGHT - 180), (100, HEIGHT - 20)], fill=(0, 100, 200, 30))

    # Left vertical accent line
    draw.rectangle([(60, 200), (64, HEIGHT - 80)], fill=(0, 180, 255))

    # Title
    y_offset = 170
    for line in title_lines:
        draw.text((90, y_offset), line, fill=(255, 255, 255), font=font_title)
        y_offset += 80

    # Subtitle
    draw.text((90, y_offset + 15), subtitle, fill=(160, 180, 210), font=font_subtitle)

    # Tag badges at bottom
    tags = ["AI", "VPS", "Docker", "Open-Source"]
    tag_x = 90
    tag_y = HEIGHT - 70
    for tag in tags:
        tw = draw.textbbox((0, 0), tag, font=font_tag)[2]
        th = draw.textbbox((0, 0), tag, font=font_tag)[3]
        draw.rectangle(
            [(tag_x - 8, tag_y - 4), (tag_x + tw + 10, tag_y + th + 6)],
            fill=(0, 80, 180),
            outline=(0, 150, 255),
            width=1,
        )
        draw.text((tag_x, tag_y), tag, fill=(200, 220, 255), font=font_tag)
        tag_x += tw + 30

    # Domain
    font_domain = ImageFont.truetype(FONT_REGULAR, 20)
    draw.text(
        (WIDTH - 220, HEIGHT - 60),
        "selfvps.net",
        fill=(80, 120, 180),
        font=font_domain,
    )

    # Save
    output_dir = f"static/images/posts/{slug}"
    os.makedirs(output_dir, exist_ok=True)
    output_path = f"{output_dir}/featured.png"
    img.save(output_path, "PNG")
    print(f"Saved: {output_path}")


if __name__ == "__main__":
    slug = sys.argv[1]
    # Support both comma-separated and colon-separated title lines
    title_arg = sys.argv[2]
    subtitle = sys.argv[3]
    title_lines = [t.strip() for t in title_arg.split("|")]
    generate_post_image(slug, title_lines, subtitle)
