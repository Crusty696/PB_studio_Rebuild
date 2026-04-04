#!/usr/bin/env python
"""
Generate pb_studio.ico and pb_studio.png for PB Studio Rebuild.

Design: Dark circle with gold "PB" lettermark and a subtle waveform accent.
Colors match the premium gold-on-dark theme of PB Studio.
"""

from PIL import Image, ImageDraw, ImageFont
import math
import os

# --- Color palette (gold-accent dark theme) ---
BG_DARK     = (18, 18, 22, 255)       # near-black background
GOLD_PRIMARY= (212, 175, 55, 255)     # rich gold
GOLD_LIGHT  = (255, 215, 90, 255)     # highlight gold
GOLD_DIM    = (140, 110, 30, 255)     # shadow gold
WHITE       = (255, 255, 255, 255)
TRANSPARENT = (0, 0, 0, 0)


def draw_icon(size: int) -> Image.Image:
    """Draw a single icon at `size x size` pixels."""
    img = Image.new("RGBA", (size, size), TRANSPARENT)
    draw = ImageDraw.Draw(img)

    cx, cy = size / 2, size / 2
    r = size / 2 - 1  # outer circle radius

    # --- Background circle ---
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=BG_DARK)

    # --- Subtle inner glow ring ---
    ring_r = r - max(1, size // 32)
    draw.ellipse(
        [cx - ring_r, cy - ring_r, cx + ring_r, cy + ring_r],
        outline=GOLD_DIM,
        width=max(1, size // 48),
    )

    # --- Gold outer ring ---
    draw.ellipse(
        [cx - r + 1, cy - r + 1, cx + r - 1, cy + r - 1],
        outline=GOLD_PRIMARY,
        width=max(1, size // 32),
    )

    # --- Waveform bar accent (bottom third) ---
    if size >= 32:
        bar_count = 7
        bar_w = size * 0.06
        spacing = size * 0.065
        total_w = bar_count * bar_w + (bar_count - 1) * (spacing - bar_w)
        heights = [0.08, 0.14, 0.22, 0.30, 0.22, 0.14, 0.08]  # relative heights
        start_x = cx - total_w / 2
        base_y = cy + r * 0.62

        for i, rel_h in enumerate(heights):
            bx = start_x + i * spacing
            bh = r * rel_h * 2
            by = base_y - bh
            alpha = 200 if i in (0, 6) else 230 if i in (1, 5) else 255
            bar_color = (*GOLD_PRIMARY[:3], alpha)
            draw.rectangle(
                [bx, by, bx + bar_w, base_y],
                fill=bar_color,
            )

    # --- "PB" lettermark ---
    # Scale font size to icon size
    font_size = int(size * 0.38)
    font = None
    # Try to load a system font; fall back to default
    font_paths = [
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/calibrib.ttf",
        "C:/Windows/Fonts/trebucbd.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
    for fp in font_paths:
        if os.path.exists(fp):
            try:
                font = ImageFont.truetype(fp, font_size)
                break
            except (OSError, IOError):
                pass
    if font is None:
        font = ImageFont.load_default()

    text = "PB"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = cx - tw / 2 - bbox[0]
    ty = cy - th / 2 - bbox[1] - size * 0.05  # slight upward offset for waveform

    # Shadow
    shadow_offset = max(1, size // 64)
    draw.text((tx + shadow_offset, ty + shadow_offset), text, font=font, fill=GOLD_DIM)
    # Main text
    draw.text((tx, ty), text, font=font, fill=GOLD_LIGHT)

    return img


def main():
    out_dir = os.path.join(os.path.dirname(__file__), "..", "resources")
    os.makedirs(out_dir, exist_ok=True)

    sizes = [16, 32, 48, 64, 128, 256]
    images = []

    print("Generating PB Studio icons...")
    for s in sizes:
        img = draw_icon(s)
        images.append(img)
        print(f"  {s}x{s} ✓")

    # Save .ico (multi-size)
    ico_path = os.path.join(out_dir, "pb_studio.ico")
    images[0].save(
        ico_path,
        format="ICO",
        append_images=images[1:],
        sizes=[(s, s) for s in sizes],
    )
    print(f"Saved: {ico_path}")

    # Save .png (256px)
    png_path = os.path.join(out_dir, "pb_studio.png")
    images[-1].save(png_path, format="PNG")
    print(f"Saved: {png_path}")

    print("Done.")


if __name__ == "__main__":
    main()
