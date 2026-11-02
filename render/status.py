"""Pre-render the Kindle's status images: what the dashboard is doing while it connects or updates.

They are drawn into the footer's right-hand slot (where "Updated ..." sits), so a busy or offline
dashboard never looks frozen:

    status/wifi_1..3.png    "Looking for Wi-Fi" with 1-3 filled dots, stepped every few seconds
    status/update_1..3.png  "Updating" with 1-3 filled dots, while a fresh image is rendered
    status/start.png        full screen for the very first start, before any image exists

The offline pill ("Offline. Updated 7:05 AM") needs the render time, so render.py makes it.

    python render/status.py     # writes kindle/dashboard/status/
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import doodles  # noqa: E402
from render import BLACK, DARK, H, MARGIN, ROOT, STALE_H, STALE_W, W, WHITE, font, quantize  # noqa: E402

S = 4


def wifi_icon(d: ImageDraw.ImageDraw, cx: float, cy: float, r: float, fill=BLACK, slash=False, bg=WHITE):
    """Wi-Fi fan: a dot and two arcs (supersampled coordinates)."""
    d.ellipse([cx - 3.2 * S, cy - 3.2 * S, cx + 3.2 * S, cy + 3.2 * S], fill=fill)
    for k in (1, 2):
        rr = r * k / 2
        d.arc([cx - rr, cy - rr, cx + rr, cy + rr], start=225, end=315, fill=fill, width=round(3.5 * S))
    if slash:
        d.line([cx - r * 0.75, cy - r * 0.95, cx + r * 0.55, cy + 0.2 * r], fill=bg, width=round(8 * S))
        d.line([cx - r * 0.75, cy - r * 0.95, cx + r * 0.55, cy + 0.2 * r], fill=fill, width=round(3.5 * S))


def update_icon(d: ImageDraw.ImageDraw, cx: float, cy: float, r: float):
    """Circular arrow."""
    d.arc([cx - r, cy - r, cx + r, cy + r], start=40, end=330, fill=BLACK, width=round(3.5 * S))
    a = math.radians(330)
    tx, ty = cx + r * math.cos(a), cy + r * math.sin(a)
    d.polygon([(tx + 6 * S, ty - 1 * S), (tx - 5 * S, ty - 6 * S), (tx - 1 * S, ty + 7 * S)], fill=BLACK)


def pill(text: str, icon: str, dots: int = 0, inverted: bool = False) -> Image.Image:
    """Status pill right-aligned in the footer slot: icon, text, then three progress dots."""
    im = Image.new("L", (STALE_W * S, STALE_H * S), WHITE)
    d = ImageDraw.Draw(im)
    fg, bg = (WHITE, BLACK) if inverted else (BLACK, WHITE)
    icon_w, gap, pad = 34 * S, 10 * S, 18 * S
    dots_w = (3 * 10 + 2 * 7) * S + gap if dots else 0
    room = STALE_W * S - (pad + icon_w + gap + dots_w + pad)
    size = 28
    while size > 20 and ImageDraw.Draw(im).textlength(text, font=font("semibold", size * S)) > room:
        size -= 1
    f = font("semibold", size * S)
    tw = d.textlength(text, font=f)
    width = min(STALE_W * S, pad + icon_w + gap + tw + dots_w + pad)
    x1, x0 = STALE_W * S, STALE_W * S - width
    y0, y1 = 3 * S, (STALE_H - 3) * S
    d.rounded_rectangle([x0, y0, x1 - S, y1], radius=22 * S, fill=bg, outline=BLACK, width=round(2.5 * S))
    cy = (y0 + y1) / 2
    ix = x0 + pad + icon_w / 2
    if icon == "wifi":
        wifi_icon(d, ix, cy + 7 * S, 26 * S, fill=fg, bg=bg)
    elif icon == "wifi-off":
        wifi_icon(d, ix, cy + 7 * S, 26 * S, fill=fg, slash=True, bg=bg)
    else:
        update_icon(d, ix, cy, 11 * S)
    tx = x0 + pad + icon_w + gap
    d.text((tx, cy + 10 * S), text, font=f, fill=fg, anchor="ls")
    if dots:
        dx = tx + tw + gap
        for k in range(3):
            c = dx + 5 * S + k * 17 * S
            if k < dots:
                d.ellipse([c - 5 * S, cy - 5 * S, c + 5 * S, cy + 5 * S], fill=fg)
            else:
                d.ellipse([c - 5 * S, cy - 5 * S, c + 5 * S, cy + 5 * S], outline=fg, width=round(2.2 * S))
    return quantize(im.resize((STALE_W, STALE_H), Image.LANCZOS))


def start_screen() -> Image.Image:
    """First start, before any dashboard image has been downloaded."""
    img = Image.new("L", (W, H), WHITE)
    d = ImageDraw.Draw(img)
    cup = doodles.coffee_cup(380)
    img.paste(cup, ((W - cup.width) // 2, 300))
    d.text((W / 2, 820), "Starting your dashboard", font=font("bold", 72), fill=BLACK, anchor="ms")
    # Wi-Fi fan and status line, drawn at 4x for smooth arcs.
    lay = Image.new("L", (W * S, 120 * S), WHITE)
    ld = ImageDraw.Draw(lay)
    label = "Looking for Wi-Fi and downloading today's dashboard"
    lf = font("regular", 38 * S)
    lw = ld.textlength(label, font=lf)
    x = (W * S - lw - 56 * S) / 2
    wifi_icon(ld, x + 18 * S, 74 * S, 40 * S, fill=DARK)
    ld.text((x + 56 * S, 74 * S), label, font=lf, fill=DARK, anchor="ls")
    img.paste(lay.resize((W, 120), Image.LANCZOS), (0, 860))
    d.text((W / 2, 1060), "This usually takes under a minute.", font=font("regular", 34), fill=DARK, anchor="ms")
    d.text((W / 2, H - 120), "Double-tap the screen to go back to the Kindle.", font=font("regular", 30), fill=DARK, anchor="ms")
    return quantize(img)


def main() -> int:
    out = ROOT / "kindle" / "dashboard" / "status"
    out.mkdir(parents=True, exist_ok=True)
    for n in (1, 2, 3):
        pill("Looking for Wi-Fi", "wifi", n).save(out / f"wifi_{n}.png", optimize=True)
        pill("Updating", "update", n).save(out / f"update_{n}.png", optimize=True)
    start_screen().save(out / "start.png", optimize=True)
    print(f"wrote status images to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
