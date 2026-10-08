"""Pre-render the footer battery indicator that the Kindle overlays on the dashboard.

The dashboard is rendered on GitHub, which can't know the Kindle's battery level, so
the Kindle draws one of these small images into BATTERY_SLOT after each refresh.

    python render/battery.py            # writes kindle/dashboard/battery/bat_<level>[_c].png
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render import BLACK, DARK, WHITE, H, ROOT, W, font  # noqa: E402

# Footer centre, between "Weather: Open-Meteo.com" and "Updated ...". Keep in sync with
# BATTERY_X/BATTERY_Y in kindle/dashboard/bin/common.sh.
SLOT_W, SLOT_H = 220, 50
SLOT_X, SLOT_Y = (W - SLOT_W) // 2, H - 92
BASELINE = 36            # text baseline inside the slot (footer text sits at H - 56)
LEVELS = range(0, 101)


def battery_image(level: int, charging: bool) -> Image.Image:
    S = 4  # supersample for crisp rounded corners
    im = Image.new("L", (SLOT_W * S, SLOT_H * S), WHITE)
    d = ImageDraw.Draw(im)
    low = level <= 15 and not charging
    tf = font("bold" if low else "regular", 30 * S)
    text = f"{level}%"
    tw = d.textlength(text, font=tf) / S

    bolt_w = 18 if charging else 0
    body_w, body_h, nub_w = 54, 26, 5
    gap = 12
    total = bolt_w + (8 if charging else 0) + body_w + nub_w + gap + tw
    x = (SLOT_W - total) / 2
    cy = BASELINE - 11   # optical centre of the 30 px footer text

    def B(*v):
        return [c * S for c in v]

    if charging:
        bx, by = x, cy - 13
        d.polygon([(px * S, py * S) for px, py in
                   ((bx + 11, by), (bx + 1, by + 15), (bx + 8, by + 15), (bx + 5, by + 26),
                    (bx + 17, by + 10), (bx + 10, by + 10), (bx + 13, by))], fill=BLACK)
        x += bolt_w + 8
    top = cy - body_h / 2
    d.rounded_rectangle(B(x, top, x + body_w, top + body_h), radius=5 * S, outline=BLACK, width=3 * S)
    d.rounded_rectangle(B(x + body_w, cy - 5, x + body_w + nub_w, cy + 5), radius=2 * S, fill=BLACK)
    inner = body_w - 10
    fill_w = round(inner * level / 100)
    if fill_w > 0:
        d.rounded_rectangle(B(x + 5, top + 5, x + 5 + fill_w, top + body_h - 5), radius=2 * S, fill=BLACK)
    x += body_w + nub_w + gap
    d.text((x * S, BASELINE * S), text, font=tf, fill=BLACK if low else DARK, anchor="ls")

    out = im.resize((SLOT_W, SLOT_H), Image.LANCZOS)
    return out.point([min(255, int(v / 17 + 0.5) * 17) for v in range(256)])


def main() -> int:
    out_dir = ROOT / "kindle" / "dashboard" / "battery"
    out_dir.mkdir(parents=True, exist_ok=True)
    for level in LEVELS:
        for charging in (False, True):
            name = f"bat_{level:03d}{'_c' if charging else ''}.png"
            battery_image(level, charging).save(out_dir / name, optimize=True)
    print(f"wrote {len(LEVELS) * 2} images to {out_dir} (slot x={SLOT_X} y={SLOT_Y} {SLOT_W}x{SLOT_H})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
