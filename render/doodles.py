"""Cute line-art doodles for the dashboard: weather mascots, a to-do clipboard and a coffee cup.

Each doodle is drawn at 4x in a 200-unit design space (black outlines, white fills,
gray blush) and downsampled, so the strokes stay smooth on the e-ink panel.
"""
from __future__ import annotations

import math

from PIL import Image, ImageChops, ImageDraw

S = 4            # supersampling factor
INK = 0
PAPER = 255
SHADE = 68       # dark gray fill (coffee, clip, eraser band)
BLUSH = 170
LW = 7           # outline width in design units


class Canvas:
    def __init__(self, w: int = 200, h: int = 200):
        self.w, self.h = w, h
        self.im = Image.new("L", (w * S, h * S), PAPER)
        self.d = ImageDraw.Draw(self.im)

    @staticmethod
    def box(x0, y0, x1, y1):
        return [x0 * S, y0 * S, x1 * S, y1 * S]

    def line(self, pts, width=LW, fill=INK):
        """Polyline with rounded joints and round end caps."""
        p = [(x * S, y * S) for x, y in pts]
        self.d.line(p, fill=fill, width=round(width * S), joint="curve")
        r = width * S / 2
        for x, y in (p[0], p[-1]):
            self.d.ellipse([x - r, y - r, x + r, y + r], fill=fill)

    def arc(self, x0, y0, x1, y1, start, end, width=LW):
        self.d.arc(self.box(x0, y0, x1, y1), start=start, end=end, fill=INK, width=round(width * S))

    def circle(self, cx, cy, r, fill=PAPER, outline=INK, width=LW):
        self.d.ellipse(self.box(cx - r, cy - r, cx + r, cy + r), fill=fill,
                       outline=outline, width=round(width * S) if outline is not None else 0)

    def oval(self, cx, cy, rx, ry, fill=INK):
        self.d.ellipse(self.box(cx - rx, cy - ry, cx + rx, cy + ry), fill=fill)

    def disk_mask(self, cx, cy, r):
        m = Image.new("L", self.im.size, 0)
        ImageDraw.Draw(m).ellipse(self.box(cx - r, cy - r, cx + r, cy + r), fill=255)
        return m

    def render(self, width: int) -> Image.Image:
        return self.im.resize((width, round(width * self.h / self.w)), Image.LANCZOS)


# --------------------------------------------------------------------------
# Building blocks
# --------------------------------------------------------------------------
def face(c: Canvas, cx, cy, s=1.0, mood="happy"):
    """Two eyes, blush and a mouth. mood: happy | sleepy | worried | cheer."""
    ex = 16 * s
    for sx in (-1, 1):
        x = cx + sx * ex
        if mood == "sleepy":
            c.arc(x - 7 * s, cy - 7 * s, x + 7 * s, cy + 5 * s, 20, 160, width=4.5 * s)
        elif mood == "cheer":   # ^ ^ smiling eyes
            c.arc(x - 7 * s, cy - 4 * s, x + 7 * s, cy + 10 * s, 200, 340, width=4.5 * s)
        else:
            c.oval(x, cy, 6 * s, 8.5 * s)
            c.oval(x - 2 * s, cy - 3.5 * s, 2.4 * s, 2.4 * s, fill=PAPER)
        c.oval(cx + sx * (ex + 13 * s), cy + 12 * s, 8 * s, 4.5 * s, fill=BLUSH)
    if mood == "worried":
        c.d.ellipse(c.box(cx - 5 * s, cy + 7 * s, cx + 5 * s, cy + 18 * s),
                    outline=INK, width=round(4 * s * S), fill=PAPER)
    elif mood == "cheer":   # wide open grin
        c.d.chord(c.box(cx - 11 * s, cy - 4 * s, cx + 11 * s, cy + 20 * s), 0, 180, fill=INK)
    else:
        c.arc(cx - 8 * s, cy + 2 * s, cx + 8 * s, cy + 16 * s, 20, 160, width=4.5 * s)


def sun(c: Canvas, cx, cy, r, ray_gap=14, ray_len=20, with_face=True):
    for i in range(8):
        a = i * math.pi / 4 + math.pi / 8
        r0, r1 = r + ray_gap, r + ray_gap + ray_len
        c.line([(cx + math.cos(a) * r0, cy + math.sin(a) * r0),
                (cx + math.cos(a) * r1, cy + math.sin(a) * r1)])
    c.circle(cx, cy, r)
    if with_face:
        face(c, cx, cy + r * 0.08, r / 46)


def moon(c: Canvas, cx, cy, R, with_face=True):
    """Crescent: a disk minus an offset disk, outlined."""
    ox, oy, r = cx + 0.5 * R, cy - 0.38 * R, 0.74 * R
    outer = ImageChops.subtract(c.disk_mask(cx, cy, R), c.disk_mask(ox, oy, r))
    inner = ImageChops.subtract(c.disk_mask(cx, cy, R - LW), c.disk_mask(ox, oy, r + LW))
    c.im.paste(INK, mask=outer)
    c.im.paste(PAPER, mask=inner)
    if with_face:
        face(c, cx - 0.38 * R, cy + 0.24 * R, R / 78, mood="sleepy")


CLOUD = (("c", 70, 112, 34), ("c", 108, 92, 44), ("c", 146, 118, 30), ("r", 36, 112, 176, 152, 20))


def cloud(c: Canvas, dx=0.0, dy=0.0, k=1.0, mood="happy"):
    """Union of circles + a rounded base: fill every part black, then every part shrunk by LW white."""
    for grow, fill in ((0, INK), (-LW, PAPER)):
        for part in CLOUD:
            if part[0] == "c":
                _, x, y, r = part
                X, Y, R = dx + x * k, dy + y * k, r * k + grow
                c.d.ellipse(c.box(X - R, Y - R, X + R, Y + R), fill=fill)
            else:
                _, x0, y0, x1, y1, rad = part
                c.d.rounded_rectangle(c.box(dx + x0 * k - grow, dy + y0 * k - grow,
                                            dx + x1 * k + grow, dy + y1 * k + grow),
                                      radius=(rad * k + grow) * S, fill=fill)
    if mood:
        face(c, dx + 106 * k, dy + 122 * k, 0.9 * k, mood=mood)


def drop(c: Canvas, cx, cy, r):
    pts = [(cx * S, (cy - 2.3 * r) * S)]
    for a in range(-25, 206, 10):
        t = math.radians(a)
        pts.append(((cx + r * math.cos(t)) * S, (cy + r * math.sin(t)) * S))
    c.d.polygon(pts, fill=INK)


def flake(c: Canvas, cx, cy, r):
    for i in range(3):
        a = i * math.pi / 3 + math.pi / 2
        c.line([(cx - math.cos(a) * r, cy - math.sin(a) * r), (cx + math.cos(a) * r, cy + math.sin(a) * r)], width=5)


def sweat(c: Canvas, cx, cy, r):
    pts = [(cx * S, (cy - 2.2 * r) * S)]
    for a in range(-20, 201, 10):
        t = math.radians(a)
        pts.append(((cx + r * math.cos(t)) * S, (cy + r * math.sin(t)) * S))
    c.d.polygon(pts, fill=PAPER, outline=INK, width=round(4 * S))


def sparkle(c: Canvas, cx, cy, r):
    c.line([(cx - r, cy), (cx + r, cy)], width=4.5)
    c.line([(cx, cy - r), (cx, cy + r)], width=4.5)


# --------------------------------------------------------------------------
# Weather mascots
# --------------------------------------------------------------------------
def weather_kind(code, is_day: bool) -> str:
    try:
        code = int(code)
    except (TypeError, ValueError):
        return "cloud"
    if code in (0, 1):
        return "sun" if is_day else "moon"
    if code == 2:
        return "partly" if is_day else "partly-night"
    if code == 3:
        return "cloud"
    if code in (45, 48):
        return "fog"
    if 71 <= code <= 77 or code in (85, 86):
        return "snow"
    if code >= 95:
        return "storm"
    if 51 <= code <= 67 or 80 <= code <= 82:
        return "rain"
    return "cloud"


def weather(kind: str, size: int) -> Image.Image:
    c = Canvas()
    high = dict(dx=100 - 106 * 1.1, dy=74 - 100 * 1.1, k=1.1)  # cloud raised to leave room below
    if kind == "sun":
        sun(c, 100, 100, 50, ray_gap=14, ray_len=22)
    elif kind == "moon":
        moon(c, 92, 104, 72)
        sparkle(c, 160, 52, 10)
        sparkle(c, 172, 128, 7)
        c.line([(140, 82), (154, 82), (140, 96), (154, 96)], width=4.5)       # z
    elif kind in ("partly", "partly-night"):
        if kind == "partly":
            sun(c, 68, 70, 34, ray_gap=10, ray_len=16, with_face=False)
        else:
            moon(c, 70, 66, 42, with_face=False)
        cloud(c, dx=12, dy=22, k=1.0)
    elif kind == "cloud":
        cloud(c, dx=100 - 106 * 1.25, dy=100 - 100 * 1.25, k=1.25)
    elif kind == "rain":
        cloud(c, **high)
        for x, y in ((64, 166), (100, 184), (136, 166)):
            drop(c, x, y, 9)
    elif kind == "snow":
        cloud(c, **high)
        for x, y in ((64, 168), (100, 186), (136, 168)):
            flake(c, x, y, 11)
    elif kind == "storm":
        cloud(c, mood="worried", **high)
        c.d.polygon([(x * S, y * S) for x, y in
                     ((108, 136), (84, 172), (101, 172), (92, 198), (124, 158), (106, 158), (118, 136))], fill=INK)
    elif kind == "fog":
        cloud(c, mood="sleepy", **high)
        for i, y in enumerate((158, 175, 192)):
            pts = [(x, y + 4 * math.sin(x / 9 + i)) for x in range(42 + i * 8, 160 - i * 8, 3)]
            c.line(pts, width=6)
    else:
        cloud(c, dx=100 - 106 * 1.25, dy=100 - 100 * 1.25, k=1.25)
    return c.render(size)


# --------------------------------------------------------------------------
# Section mascots
# --------------------------------------------------------------------------
def clipboard(size: int, mood: str = "happy") -> Image.Image:
    """A clipboard with ticked lines and a pencil. mood: happy | cheer (all done) | busy (long list)."""
    c = Canvas(200, 212)
    c.d.rounded_rectangle(c.box(38, 30, 156, 200), radius=16 * S, fill=PAPER, outline=INK, width=LW * S)
    c.d.rounded_rectangle(c.box(74, 16, 120, 44), radius=10 * S, fill=SHADE, outline=INK, width=LW * S)
    c.circle(97, 25, 4, fill=PAPER, outline=None)
    for y in (68, 96):
        c.d.rounded_rectangle(c.box(54, y - 9, 72, y + 9), radius=4 * S, outline=INK, width=round(4.5 * S))
        c.line([(57, y), (62, y + 5), (70, y - 6)], width=4.5)
        c.line([(82, y), (138, y)], width=5)
    if mood == "cheer":
        face(c, 97, 146, 1.0, mood="cheer")
        for x, y, r in ((22, 40, 9), (12, 112, 6), (176, 30, 7)):
            sparkle(c, x, y, r)
    elif mood == "busy":
        face(c, 97, 146, 1.0, mood="worried")
        sweat(c, 140, 132, 7)
    else:
        face(c, 97, 146, 1.0)
    # Pencil: eraser end A, tip B.
    ax, ay, bx, by = 186, 92, 160, 194
    ux, uy = bx - ax, by - ay
    n = math.hypot(ux, uy)
    ux, uy = ux / n, uy / n
    nx, ny = -uy * 10, ux * 10

    def P(x, y):
        return (x * S, y * S)

    cx_, cy_ = bx - ux * 26, by - uy * 26                     # where the wood cone starts
    body = [P(ax + nx, ay + ny), P(cx_ + nx, cy_ + ny), P(cx_ - nx, cy_ - ny), P(ax - nx, ay - ny)]
    c.d.polygon(body, fill=PAPER, outline=INK, width=round(5 * S))
    c.d.polygon([P(cx_ + nx, cy_ + ny), P(bx, by), P(cx_ - nx, cy_ - ny)], fill=PAPER, outline=INK, width=round(5 * S))
    tx, ty = bx - ux * 9, by - uy * 9                         # graphite tip
    c.d.polygon([P(tx + nx * 0.35, ty + ny * 0.35), P(bx, by), P(tx - nx * 0.35, ty - ny * 0.35)], fill=INK)
    ex, ey = ax + ux * 16, ay + uy * 16                       # eraser band
    c.d.polygon([P(ax + nx, ay + ny), P(ex + nx, ey + ny), P(ex - nx, ey - ny), P(ax - nx, ay - ny)],
                fill=SHADE, outline=INK, width=round(5 * S))
    return c.render(size)


SEASONS = {9: "leaf", 10: "witch", 11: "scarf", 12: "santa", 1: "scarf", 2: "scarf",
           3: "flower", 4: "flower", 5: "flower", 6: "shades", 7: "shades", 8: "shades"}


def season_for(month: int) -> str:
    return SEASONS.get(month, "")


def _hat(c: Canvas, kind: str):
    """A hat perched on the left of the rim (witch or santa)."""
    P = lambda pts: [(x * S, y * S) for x, y in pts]  # noqa: E731
    if kind == "witch":
        # Tall bent cone, wide brim, light band: unmistakably a witch hat at small sizes.
        c.d.polygon(P(((42, 72), (60, 34), (52, 6), (80, 30), (98, 72))), fill=SHADE, outline=INK, width=round(5 * S))
        c.d.ellipse(c.box(14, 62, 126, 86), fill=SHADE, outline=INK, width=round(5 * S))
        c.d.rounded_rectangle(c.box(44, 58, 96, 70), radius=3 * S, fill=PAPER, outline=INK, width=round(4 * S))
    else:  # santa: dark cone flopping right, white fur band and pompom
        c.d.polygon(P(((34, 74), (54, 30), (88, 14), (112, 34), (100, 74))), fill=SHADE, outline=INK, width=round(5 * S))
        c.d.rounded_rectangle(c.box(24, 64, 112, 88), radius=12 * S, fill=PAPER, outline=INK, width=round(5 * S))
        c.circle(116, 36, 12)


def _scarf(c: Canvas):
    c.d.rounded_rectangle(c.box(26, 158, 154, 178), radius=8 * S, fill=PAPER, outline=INK, width=round(5 * S))
    for x in range(44, 150, 18):
        c.line([(x, 162), (x - 6, 174)], width=3.5)
    c.d.polygon([(x * S, y * S) for x, y in ((128, 172), (146, 172), (152, 200), (132, 200))], fill=PAPER, outline=INK, width=round(5 * S))
    for x in (136, 141, 146):
        c.line([(x, 200), (x, 207)], width=3)


def _shades(c: Canvas):
    for ex in (68, 112):
        c.d.rounded_rectangle(c.box(ex - 16, 120, ex + 16, 142), radius=9 * S, fill=INK)
    c.line([(84, 126), (96, 126)], width=4)
    c.line([(52, 124), (34, 118)], width=4)
    c.line([(128, 124), (148, 118)], width=4)


def _flower(c: Canvas):
    c.line([(180, 188), (177, 136)], width=5)
    c.line([(178, 166), (194, 154)], width=4.5)
    for k in range(5):
        t = math.radians(k * 72 - 90)
        c.circle(177 + 12 * math.cos(t), 122 + 12 * math.sin(t), 9, width=4.5)
    c.circle(177, 122, 7, fill=SHADE, width=3.5)


def _leaf(c: Canvas):
    pts = []
    for k in range(0, 361, 8):
        t = math.radians(k)
        x, y = 26 * math.cos(t), 14 * math.sin(t) * (1 - 0.3 * math.cos(t))
        r = math.radians(-35)
        pts.append(((30 + x * math.cos(r) - y * math.sin(r)) * S, (40 + x * math.sin(r) + y * math.cos(r)) * S))
    c.d.polygon(pts, fill=PAPER, outline=INK, width=round(5 * S))
    c.line([(8, 58), (50, 26)], width=4)


def coffee_cup(size: int, mood: str = "awake", season: str = "") -> Image.Image:
    """A mug on a saucer. awake: big eyes, steam curling into a heart. sleepy: closed eyes, a drowsy z z.
    season adds an accessory: leaf, witch, scarf, santa, flower or shades."""
    c = Canvas(200, 212)
    hat = season in ("witch", "santa")
    if hat:
        # The hat sits where the left steam and heart would be; keep one wisp on the right.
        c.line([(122 + 6 * math.sin(t / 10), 74 - t) for t in range(0, 34)], width=5)
    elif mood == "sleepy":
        c.line([(90 + 5 * math.sin(t / 9), 72 - t) for t in range(0, 30)], width=5)
        c.line([(132, 30), (148, 30), (132, 46), (148, 46)], width=4.5)
        c.line([(156, 6), (168, 6), (156, 18), (168, 18)], width=4)
    else:
        for cx, phase in ((58, 0.0), (122, math.pi)):
            c.line([(cx + 6 * math.sin(t / 10 + phase), 74 - t) for t in range(0, 34)], width=5)
        heart = []
        for i in range(0, 361, 4):
            t = math.radians(i)
            x = 16 * math.sin(t) ** 3
            y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
            heart.append(((90 + x * 1.35) * S, (38 - y * 1.35) * S))
        c.d.line(heart + heart[:2], fill=INK, width=5 * S, joint="curve")
    c.d.ellipse(c.box(8, 180, 192, 208), fill=PAPER, outline=INK, width=LW * S)
    c.arc(124, 108, 184, 166, -80, 80)
    c.d.rounded_rectangle(c.box(30, 88, 150, 190), radius=30 * S, fill=PAPER, outline=INK,
                          width=LW * S, corners=(False, False, True, True))
    c.d.ellipse(c.box(30, 76, 150, 102), fill=PAPER, outline=INK, width=LW * S)
    c.d.ellipse(c.box(42, 82, 138, 96), fill=SHADE)
    face(c, 90, 131, 1.35, mood="sleepy" if mood == "sleepy" else "happy")
    if hat:
        _hat(c, season)
    elif season == "scarf":
        _scarf(c)
    elif season == "shades":
        _shades(c)
    elif season == "flower":
        _flower(c)
    elif season == "leaf":
        _leaf(c)
    return c.render(size)


if __name__ == "__main__":  # preview sheet: python render/doodles.py out/doodles.png
    import sys
    kinds = ["sun", "moon", "partly", "partly-night", "cloud", "rain", "snow", "storm", "fog"]
    tiles = [weather(k, 200) for k in kinds] + [clipboard(200), clipboard(200, "cheer"), clipboard(200, "busy"),
                                                coffee_cup(200), coffee_cup(200, "sleepy")]
    tiles += [coffee_cup(200, "awake", k) for k in ("leaf", "witch", "scarf", "santa", "flower", "shades")]
    sheet = Image.new("L", (4 * 240, 6 * 250), PAPER)
    for i, t in enumerate(tiles):
        sheet.paste(t, ((i % 4) * 240 + 20, (i // 4) * 250 + 20))
    sheet.save(sys.argv[1] if len(sys.argv) > 1 else "doodles.png")
