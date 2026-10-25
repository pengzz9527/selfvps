#!/usr/bin/env python3
"""Generate selfvps dark-gradient feature cover (1200x630).

Style spec: #0f172a -> #1e293b gradient, white title, #94a3b8 subtitle,
indigo #6366f1 URL bottom-right, rounded glow accents.
"""
import argparse
import os
from PIL import Image, ImageDraw, ImageFont, ImageFilter

FONT_BOLD = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
FONT_REG = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"


def font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def wrap(text, fnt, max_w, draw):
    lines, cur = [], ""
    for ch in text:
        if ch == "\n":
            lines.append(cur)
            cur = ""
            continue
        trial = cur + ch
        if draw.textbbox((0, 0), trial, font=fnt)[2] > max_w and cur:
            lines.append(cur)
            cur = ch
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--title", required=True)
    ap.add_argument("--subtitle", default="")
    ap.add_argument("--category", default="")
    ap.add_argument("--output", required=True)
    ap.add_argument("--width", type=int, default=1200)
    ap.add_argument("--height", type=int, default=630)
    a = ap.parse_args()

    W, H = a.width, a.height
    img = Image.new("RGB", (W, H))

    # ---- vertical gradient #0f172a -> #1e293b ----
    top = (15, 23, 42)
    bot = (30, 41, 59)
    for y in range(H):
        t = y / (H - 1)
        img.paste(
            (int(top[0] + (bot[0] - top[0]) * t),
             int(top[1] + (bot[1] - top[1]) * t),
             int(top[2] + (bot[2] - top[2]) * t)),
            (0, y, W, y + 1),
        )

    # ---- glow layer (drawn then blurred) ----
    glow = Image.new("RGB", (W, H), (0, 0, 0))
    g = ImageDraw.Draw(glow)
    g.ellipse([W - 340, -190, W + 40, 190], fill=(99, 102, 241))
    g.ellipse([-180, H - 230, 180, H + 130], fill=(56, 189, 248))
    glow = glow.filter(ImageFilter.GaussianBlur(90))
    img = Image.blend(img, Image.composite(glow, img, glow.convert("L").point(lambda v: int(v * 0.42))), 0.55)

    draw = ImageDraw.Draw(img, "RGBA")

    # ---- rounded decorative frame ----
    draw.rounded_rectangle([28, 28, W - 28, H - 28], radius=22,
                           outline=(99, 102, 241, 110), width=2)
    # corner accent
    draw.rounded_rectangle([28, 28, 200, 34], radius=3, fill=(99, 102, 241, 235))

    # ---- category pill ----
    x, y = 72, 84
    if a.category:
        cf = font(FONT_BOLD, 22)
        tw = draw.textbbox((0, 0), a.category, font=cf)[2]
        draw.rounded_rectangle([x, y, x + tw + 34, y + 44], radius=22,
                               fill=(99, 102, 241, 46), outline=(129, 140, 248, 180), width=1)
        draw.text((x + 17, y + 9), a.category, font=cf, fill=(165, 180, 252))
        y += 78

    # ---- title ----
    tf = font(FONT_BOLD, 56)
    lines = wrap(a.title, tf, W - 160, draw)
    if len(lines) > 3:
        tf = font(FONT_BOLD, 46)
        lines = wrap(a.title, tf, W - 160, draw)
    line_h = tf.size + 18
    for line in lines:
        draw.text((72, y), line, font=tf, fill=(255, 255, 255))
        y += line_h

    # ---- subtitle ----
    if a.subtitle:
        sf = font(FONT_REG, 26)
        y += 14
        for line in wrap(a.subtitle, sf, W - 170, draw)[:2]:
            draw.text((72, y), line, font=sf, fill=(148, 163, 184))
            y += 38

    # ---- URL bottom-right ----
    uf = font(FONT_BOLD, 14 + 6)
    url = "selfvps.net"
    uw = draw.textbbox((0, 0), url, font=uf)[2]
    draw.text((W - 72 - uw, H - 84), url, font=uf, fill=(99, 102, 241))

    os.makedirs(os.path.dirname(a.output), exist_ok=True)
    img.save(a.output, "PNG", optimize=True)
    print("saved", a.output, img.size)


if __name__ == "__main__":
    main()
