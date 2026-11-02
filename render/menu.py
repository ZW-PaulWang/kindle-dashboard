#!/usr/bin/env python3
"""Page 2 of the Kindle dashboard: today's meal plan as a fine-dining menu card.

Reads menu.md (an optional "# Title", an optional "Date: YYYY-MM-DD", then "## Breakfast",
"## Lunch" and "## Dinner" with one "- Dish: details" line per dish) and draws a
1236x1648, 16-gray-level PNG the Kindle shows when you swipe to the second page.

Every dish goes through tidy_dish() first: deterministic polish (spacing, bullets, title
case, "w/" -> "with") that never adds, drops or reorders the words you typed.

    python render/menu.py --out out/menu.png [--menu menu.md] [--now 2026-11-02T08:00]
    python render/menu.py --selftest
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date, datetime
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import doodles  # noqa: E402
from render import (BLACK, DARK, FONT_DIR, H, MARGIN, MID, ROOT, W, WHITE, clock, font,  # noqa: E402
                    hrule, page_dots, parse_now, quantize, text_w, warn, wrap)

MEALS = ("breakfast", "lunch", "dinner")
DEFAULT_TITLE = "Today's Menu"
FOOTER_RULE = H - 106

# --------------------------------------------------------------------------
# Tidy: deterministic, faithful polish of one dish line
# --------------------------------------------------------------------------
# Joining words that stay lowercase in a title (unless first, or typed with a capital).
SMALL_WORDS = frozenset("""
    a an the and or nor but of in on at to for with by from per as vs via into onto over
    au aux de du des la le les et en à al alla della di da del con y e w/o
""".split())

_BULLET_RE = re.compile(r"^(?:[-*+•·–—]\s*|\d{1,2}[.)]\s+|\(\d{1,2}\)\s*|\[[ xX]?\]\s*)+")
_EMPHASIS_RE = re.compile(r"(\*\*|__|`|\*(?=\S))(.+?)\1")   # **bold**, __bold__, `code`, *italic*
# "w/" -> "with", but never "w/o" (= without: turning it into "with o" would invert the meaning).
_WITH_RE = re.compile(r"(?<!\S)[wW]/(?![oO](?![^\W\d_]))")
_AMP_RE = re.compile(r"(?<=\w) & (?=\w)")
# Chinese input methods type fullwidth punctuation (：，；、。！); it is treated like its ASCII twin.
_TRAIL_RE = re.compile(r"[\s.,;:!。，；：！、]+$")
_LEAD_RE = re.compile(r"^[\s.,;:。，；：、]+")


def _squash(s: str) -> str:
    return " ".join(s.split())


def _cap_word(word: str, first: bool) -> str:
    """Title-case one word, keeping words typed with capitals or digits exactly as typed."""
    if any(ch.isupper() or ch.isdigit() for ch in word):
        return word
    if not first and word.lower() in SMALL_WORDS:
        return word

    def up(part: str) -> str:   # capitalise the first letter, after any leading punctuation
        for i, ch in enumerate(part):
            if ch.isalpha():
                return part[:i] + ch.upper() + part[i + 1:]
        return part
    # "half-and-half" -> "Half-and-Half": small words inside a hyphenated word stay lowercase too
    return "-".join(p if j and p in SMALL_WORDS else up(p) for j, p in enumerate(word.split("-")))


def title_case(s: str) -> str:
    return " ".join(_cap_word(w, i == 0) for i, w in enumerate(s.split()))


def tidy_details(s: str) -> str:
    """Comma-separated, whitespace collapsed, no trailing punctuation; letter case as typed."""
    parts = [_TRAIL_RE.sub("", _LEAD_RE.sub("", _squash(p))) for p in re.split(r"[,;，；、]", s)]
    return ", ".join(p for p in parts if p)


def tidy_dish(name_line: str) -> tuple[str, str]:
    """One dish line -> (name, details). Polish only: never adds, reorders or drops words.

    "  - greek yogurt:  honey ,walnuts. " -> ("Greek Yogurt", "honey, walnuts")
    "salmon w/ miso glaze"               -> ("Salmon", "miso glaze")
    """
    s = _squash(name_line)
    s = _EMPHASIS_RE.sub(r"\2", s)
    s = _BULLET_RE.sub("", s)
    s = _WITH_RE.sub("with ", s)                 # "w/rice" and "w/ rice" -> "with rice"
    s = _squash(s)
    s = _AMP_RE.sub(" and ", s)                  # "mac & cheese"; "R&D" and "& co" untouched
    m = re.search(r":(?:\s+|$)|：\s*", s)       # "10:30" is not a separator; "红烧肉：米饭" is
    if m:
        name, details = s[:m.start()], s[m.end():]
    else:
        name, details = s, ""
        i = s.find(" with ")
        if i > 0:
            name, details = s[:i], s[i + len(" with "):]
    name = _TRAIL_RE.sub("", _LEAD_RE.sub("", _squash(name)))
    details = tidy_details(details)
    if not name and details:                     # "- : honey" -> the details are the dish
        name, details = details, ""
    return title_case(name), details


# --------------------------------------------------------------------------
# menu.md
# --------------------------------------------------------------------------
_DISH_RE = re.compile(r"^\s*(?:[-*+•]|\d{1,2}[.)])\s+(.*\S)\s*$")
_DATE_RE = re.compile(r"^\s*date\s*:\s*(\d{4}-\d{2}-\d{2})\s*$", re.I)


def parse_menu(text: str) -> dict:
    """-> {"title": str, "date": date | None, "meals": {"breakfast": [(name, details)], ...}}"""
    menu = {"title": DEFAULT_TITLE, "date": None, "meals": {m: [] for m in MEALS}}
    have_title = False
    cur = None
    for line in text.splitlines():
        st = line.strip()
        if st.startswith("## "):
            key = st[3:].strip().rstrip(":").strip().lower()   # "## Breakfast:" is fine too
            cur = key if key in MEALS else None
            continue
        if st.startswith("# ") and not have_title:
            t = _squash(st[2:])
            if t:
                menu["title"], have_title = t, True
            continue
        m = _DATE_RE.match(line)
        if m:
            try:
                menu["date"] = date.fromisoformat(m.group(1))
            except ValueError:
                pass
            continue
        if cur is None:
            continue
        m = _DISH_RE.match(line)
        if m:
            name, details = tidy_dish(m.group(1))
            if name:
                menu["meals"][cur].append((name, details))
    return menu


# --------------------------------------------------------------------------
# Type
# --------------------------------------------------------------------------
_SERIF = {False: "EBGaramond-VF.ttf", True: "EBGaramond-Italic-VF.ttf"}
# Fallbacks for characters EB Garamond lacks, tried in order, each with a size factor that
# matches its ink height to Garamond's: Chinese (Noto Serif SC, GB2312 + Big5 level 1 subset,
# see fonts/subset_cjk.py) and monochrome emoji (Noto Emoji). No italic exists for either.
_FALLBACKS = (("NotoSerifSC-SemiBold-subset.ttf", 0.88), ("NotoEmoji-Medium.ttf", 0.82))
# Invisible joiners and modifiers that would otherwise draw as boxes (display only).
_INVISIBLE_RE = re.compile("[‍︎️\U0001f3fb-\U0001f3ff]")
_serif_cache: dict = {}
_ref_cache: dict = {}
_glyph_cache: dict = {}


def _has_glyph(fname: str, ch: str) -> bool:
    """Does the font map ch to a real glyph? (Pillow has no cmap lookup: compare with .notdef.)"""
    key = (fname, ch)
    if key not in _glyph_cache:
        if fname not in _ref_cache:
            try:
                ref = ImageFont.truetype(str(FONT_DIR / fname), 48)
                nd = "\U0010fffd"   # private use, never in these fonts
                _ref_cache[fname] = (ref, ref.getlength(nd), bytes(ref.getmask(nd)))
            except OSError as e:     # a missing fallback font costs only its characters
                if fname in _SERIF.values():
                    raise
                warn(f"font {fname} unavailable ({e}); its characters will show as boxes")
                _ref_cache[fname] = None
        if _ref_cache[fname] is None:
            _glyph_cache[key] = False
        else:
            ref, nd_len, nd_mask = _ref_cache[fname]
            _glyph_cache[key] = ch.isspace() or not (ref.getlength(ch) == nd_len and bytes(ref.getmask(ch)) == nd_mask)
    return _glyph_cache[key]


def _load(fname: str, size: int, weight: int | None) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(str(FONT_DIR / fname), max(1, int(size)))
    if weight is not None:
        try:
            f.set_variation_by_axes([weight])
        except Exception as e:  # noqa: BLE001  (FreeType without variations: default weight)
            warn(f"serif weight {weight} unavailable ({e})")
    return f


class Face:
    """EB Garamond at one size/weight, falling back per character to Chinese and emoji fonts.

    Quacks like a FreeTypeFont where render.wrap()/ellipsize() need it (.size, .getlength);
    draw with .text() instead of ImageDraw.text so each run gets its own font."""

    def __init__(self, size: int, weight: int, italic: bool):
        self.size = int(size)
        self.primary = _load(_SERIF[italic], size, weight)
        self._names = [_SERIF[italic]] + [fn for fn, _ in _FALLBACKS]
        self._fonts = [self.primary] + [None] * len(_FALLBACKS)

    def _font(self, i: int) -> ImageFont.FreeTypeFont:
        if self._fonts[i] is None:
            fname, k = _FALLBACKS[i - 1]
            self._fonts[i] = _load(fname, round(self.size * k), None)
        return self._fonts[i]

    def runs(self, s: str) -> list:
        """[(text, font)] runs; a character no font has stays with Garamond (an honest box)."""
        out: list = []
        for ch in _INVISIBLE_RE.sub("", s):
            i = next((j for j, fn in enumerate(self._names) if _has_glyph(fn, ch)), 0)
            if out and out[-1][1] == i:
                out[-1][0] += ch
            else:
                out.append([ch, i])
        return [(t, self._font(i)) for t, i in out]

    def getlength(self, s: str) -> float:
        return sum(f.getlength(t) for t, f in self.runs(s))

    def text(self, d, xy, s: str, fill, anchor: str = "ls"):
        """Draw s with its baseline at xy[1]; anchor "ls" (left), "ms" (centre) or "rs" (right)."""
        runs = self.runs(s)
        x, y = xy
        total = sum(f.getlength(t) for t, f in runs)
        x -= {"l": 0, "m": total / 2, "r": total}[anchor[0]]
        for t, f in runs:
            d.text((x, y), t, font=f, fill=fill, anchor="ls")
            x += f.getlength(t)


def serif(size: int, weight: int = 400, italic: bool = False) -> Face:
    """EB Garamond (variable: weight 400-800) with Chinese and emoji fallback."""
    key = (int(size), int(weight), italic)
    if key not in _serif_cache:
        _serif_cache[key] = Face(size, weight, italic)
    return _serif_cache[key]


def typeset(s: str) -> str:
    """Display-only typography: curly quotes and apostrophes."""
    s = re.sub(r"(?<=\w)'|'(?=\s|$)", "’", s)
    s = s.replace("'", "‘")
    s = re.sub(r'"(?=\w)', "“", s)
    s = re.sub(r"(?<=[\u3400-\u9fff]), (?=[\u3400-\u9fff])", "、", s)   # Chinese list: 醋、姜丝
    return s.replace('"', "”")


def tracked(d, cx, y, s, f, fill, tracking):
    """Letter-spaced caps centred on cx (baseline y)."""
    widths = [text_w(ch, f) for ch in s]
    total = sum(widths) + tracking * (len(s) - 1)
    x = cx - total / 2
    for ch, w in zip(s, widths):
        f.text(d, (x, y), ch, fill, "ls")
        x += w + tracking
    return total


# --------------------------------------------------------------------------
# Ornaments (supersampled, like doodles.py)
# --------------------------------------------------------------------------
S = 4


def _paste_ss(img, draw_fn, x, y, w, h):
    """Draw at 4x on white, downsample, and lay it over img (darker wins, so nothing is erased)."""
    tile = Image.new("L", (w * S, h * S), WHITE)
    draw_fn(ImageDraw.Draw(tile))
    small = tile.resize((w, h), Image.LANCZOS)
    img.paste(ImageChops.darker(img.crop((x, y, x + w, y + h)), small), (x, y))


def divider(img, cx, cy, half=170, fill=DARK):
    """A fine rule broken by a small hollow diamond flanked by two dots."""
    w, h = 2 * half + 8, 32

    def draw(d):
        m, c = h * S / 2, w * S / 2
        lw = 2.5 * S
        for sgn in (-1, 1):
            a, b = c + sgn * 44 * S, c + sgn * half * S
            d.line([(min(a, b), m), (max(a, b), m)], fill=fill, width=round(lw))
            r = 3.2 * S
            dx = c + sgn * 28 * S
            d.ellipse([dx - r, m - r, dx + r, m + r], fill=fill)
        r = 10 * S
        d.polygon([(c, m - r), (c + r, m), (c, m + r), (c - r, m)], outline=fill, width=round(3 * S))
    _paste_ss(img, draw, int(cx - w / 2), int(cy - h / 2), w, h)


FRAME = (40, 34, W - 40, FOOTER_RULE - 34)   # the card's double rule, clear of the footer


def frame(img, box=FRAME, fill=DARK):
    """Menu-card border: a fine outer rule and an inner hairline with concave (scooped) corners."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0 + 1, y1 - y0 + 1

    def draw(d):
        lw_o, lw_i = round(3 * S), round(1.75 * S)
        d.rectangle([0, 0, w * S - 1, h * S - 1], outline=fill, width=lw_o)
        g, r = 13 * S, 26 * S                      # inner rule inset, corner scoop radius
        a0, b0, a1, b1 = g, g, w * S - 1 - g, h * S - 1 - g
        half = lw_i / 2
        d.rectangle([a0 + r, b0 - half, a1 - r, b0 + half], fill=fill)
        d.rectangle([a0 + r, b1 - half, a1 - r, b1 + half], fill=fill)
        d.rectangle([a0 - half, b0 + r, a0 + half, b1 - r], fill=fill)
        d.rectangle([a1 - half, b0 + r, a1 + half, b1 - r], fill=fill)
        for cx, cy, start in ((a0, b0, 0), (a1, b0, 90), (a1, b1, 180), (a0, b1, 270)):
            d.arc([cx - r, cy - r, cx + r, cy + r], start, start + 90, fill=fill, width=lw_i)
            dr = 5 * S                                 # a small solid diamond in each scoop
            ox = cx + (dr * 1.9 if cx == a0 else -dr * 1.9)
            oy = cy + (dr * 1.9 if cy == b0 else -dr * 1.9)
            d.polygon([(ox, oy - dr), (ox + dr, oy), (ox, oy + dr), (ox - dr, oy)], fill=fill)
    _paste_ss(img, draw, x0, y0, w, h)


def cloche(size: int, mood: str = "happy") -> Image.Image:
    """A domed silver cloche on a plate, with a contented face and a few sparkles."""
    c = doodles.Canvas(240, 176)
    INK, PAPER = doodles.INK, doodles.PAPER
    # plate
    c.d.ellipse(c.box(14, 146, 226, 170), fill=PAPER, outline=INK, width=doodles.LW * S)
    # dome (upper half of an ellipse) and its rim band
    c.d.chord(c.box(40, 58, 200, 238), 180, 360, fill=PAPER, outline=INK, width=doodles.LW * S)
    c.d.rounded_rectangle(c.box(30, 140, 210, 154), radius=7 * S, fill=PAPER, outline=INK, width=round(6 * S))
    # knob
    c.line([(120, 50), (120, 60)], width=6)
    c.circle(120, 42, 10)
    # shine
    c.arc(62, 80, 178, 210, 200, 236, width=5)
    doodles.face(c, 120, 112, 1.0, mood="sleepy" if mood == "sleepy" else "happy")
    if mood == "sleepy":
        c.line([(172, 54), (186, 54), (172, 68), (186, 68)], width=4.5)
        c.line([(194, 28), (205, 28), (194, 39), (205, 39)], width=4)
    else:
        doodles.sparkle(c, 30, 72, 10)
        doodles.sparkle(c, 208, 46, 8)
        doodles.sparkle(c, 214, 104, 5.5)
    return c.render(size)


# --------------------------------------------------------------------------
# Layout
# --------------------------------------------------------------------------
# Size steps, largest first: dish, details, header, dish gap, section gap.
# A light day gets the two largest steps, so it reads from across the room.
STEPS = [
    dict(name=68, det=42, head=40, dish_gap=40, sec_gap=72),
    dict(name=63, det=39, head=40, dish_gap=37, sec_gap=68),
    dict(name=58, det=36, head=38, dish_gap=34, sec_gap=64),
    dict(name=54, det=34, head=36, dish_gap=30, sec_gap=56),
    dict(name=50, det=32, head=36, dish_gap=26, sec_gap=50),
    dict(name=46, det=30, head=34, dish_gap=22, sec_gap=44),
    dict(name=42, det=29, head=32, dish_gap=18, sec_gap=38),
    dict(name=38, det=28, head=30, dish_gap=14, sec_gap=32),
]
NAME_W = 980
DET_W = 900
MAX_LINES = 3   # per dish name and per details, before an ellipsis


def _meal_ops(meal: str, dishes: list, k: int, P: dict) -> list:
    """Draw operations for one meal at size step P, showing its first k dishes."""
    nf = serif(P["name"], 500)
    df = serif(P["det"], 500, italic=True)
    ops = [("head", (meal, P["head"]), round(P["head"] * 1.15)),
           ("gap", None, round(P["head"] * 0.7))]
    if not dishes:
        ef = serif(max(32, P["det"]), 500, italic=True)
        lh = round(ef.size * 1.25)
        return ops + [("text", (["To be decided"], ef, MID, lh), lh)]
    lines = P.get("lines", MAX_LINES)
    for j, (name, det) in enumerate(dishes[:k]):
        if j:
            ops.append(("gap", None, P["dish_gap"]))
        nl = wrap(typeset(name), nf, NAME_W, lines)
        nlh = round(nf.size * 1.12)
        ops.append(("text", (nl, nf, BLACK, nlh), nlh * len(nl)))
        if det:
            dl = wrap(typeset(det), df, DET_W, lines)
            dlh = round(df.size * 1.22)
            ops.append(("gap", None, round(df.size * 0.18)))
            ops.append(("text", (dl, df, DARK, dlh), dlh * len(dl)))
    if k < len(dishes):
        mf = serif(32, 500, italic=True)
        ops.append(("gap", None, P["dish_gap"]))
        ops.append(("text", ([f"+{len(dishes) - k} more"], mf, DARK, 40), 40))
    return ops


def _meal_blocks(meals: dict, shown: dict, P: dict) -> list:
    """The whole menu as draw operations: (kind, payload, advance), kind = head | text | gap | secgap.
    secgap (between meals) is the stretchable space."""
    ops = []
    for i, meal in enumerate(MEALS):
        if i:
            ops.append(("secgap", None, P["sec_gap"]))
        ops += _meal_ops(meal, meals[meal], shown[meal], P)
    return ops


def _height(ops) -> int:
    return sum(h for _, _, h in ops)


def plan_layout(meals: dict, avail: int) -> tuple[list, dict]:
    """Largest size step that fits. If even the smallest is too tall, trim the tallest meal
    (with a "+N more" line) until it fits; as a last resort allow fewer wrapped lines."""
    shown = {m: len(meals[m]) for m in MEALS}
    for P in STEPS:
        ops = _meal_blocks(meals, shown, P)
        if _height(ops) <= avail:
            return ops, P
    for P in (STEPS[-1], dict(STEPS[-1], lines=2), dict(STEPS[-1], lines=1)):
        shown = {m: len(meals[m]) for m in MEALS}
        while True:
            ops = _meal_blocks(meals, shown, P)
            if _height(ops) <= avail:
                return ops, P
            h = {m: _height(_meal_ops(m, meals[m], shown[m], P)) for m in MEALS if shown[m] > 1}
            if not h:
                break
            m = max(h, key=h.get)
            # Hide at least one dish more than shown now; skip a cut that saves no height
            # ("+1 more" in place of a one-line dish).
            k = shown[m] - 1
            while k > 1 and _height(_meal_ops(m, meals[m], k, P)) >= h[m]:
                k -= 1
            shown[m] = k
    return ops, P   # pathological input: draw it anyway (it runs close to the frame, never clipped mid-glyph)


def draw_ops(d, ops, top):
    y = top
    for kind, payload, h in ops:
        if kind in ("gap", "secgap"):
            y += h
            continue
        if kind == "head":
            meal, size = payload
            f = serif(size, 600)
            label = meal.upper()
            tr = f.size * 0.32
            base = y + round(f.size * 0.82)
            tw = tracked(d, W / 2, base, label, f, BLACK, tr)
            # short hairlines either side, at mid-cap height
            my = base - round(f.size * 0.33)
            for sgn in (-1, 1):
                a = W / 2 + sgn * (tw / 2 + 28)
                b = a + sgn * 64
                d.rectangle([min(a, b), my - 1, max(a, b), my], fill=DARK)
            y += h
            continue
        lines, f, col, lh = payload
        for ln in lines:
            f.text(d, (W / 2, y + round(f.size * 0.86)), ln, col, "ms")
            y += lh
    return y


def date_note(plan: date | None, today: date) -> str | None:
    """Honest note when the plan was written for another day."""
    if plan is None or plan == today:
        return None
    diff = (plan - today).days
    if diff == 1:
        return f"Planned for tomorrow, {plan:%A}"
    if diff == -1:
        return f"Planned for yesterday, {plan:%A}"
    year = f", {plan.year}" if plan.year != today.year else ""
    return f"Planned for {plan:%A}, {plan:%B} {plan.day}{year}"


def _header(img, d, title: str, now: datetime, note: str | None, art: bool = True) -> int:
    """Cloche, title, date line, optional note and divider. Returns the y below it."""
    if art:
        pic = cloche(210)
        img.paste(pic, ((W - pic.width) // 2, 66))
        y = 66 + pic.height + 104
    else:
        y = 190
    tf = serif(96, 560)
    size = 96
    while size > 60 and text_w(typeset(title), tf) > W - 2 * MARGIN - 40:
        size -= 4
        tf = serif(size, 560)
    title_lines = wrap(typeset(title), tf, W - 2 * MARGIN - 40, 2)
    for ln in title_lines:
        tf.text(d, (W / 2, y), ln, BLACK, "ms")
        y += round(size * 1.08)
    y += 58 - round(size * 1.08)
    df = serif(32, 520)
    tracked(d, W / 2, y, f"{now:%A}  ·  {now:%B} {now.day}".upper(), df, DARK, 32 * 0.2)
    if note:
        y += 50
        serif(34, 450, italic=True).text(d, (W / 2, y), note, DARK, "ms")
    y += 50
    divider(img, W / 2, y)
    return y + 30


def _footer(d, now: datetime):
    hrule(d, FOOTER_RULE)
    # Left only: the right-hand slot (status pills) and the centre (battery) stay white.
    d.text((MARGIN, H - 56), f"Updated {clock(now)}", font=font("regular", 30), fill=DARK, anchor="ls")


def render_menu(now: datetime, path: Path) -> Image.Image:
    img = Image.new("L", (W, H), WHITE)
    d = ImageDraw.Draw(img)
    frame(img)
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        text = None
    except Exception as e:  # noqa: BLE001
        warn(f"could not read {path}: {e}")
        text = None

    if text is None:
        render_empty_state(img, d, now)
    else:
        menu = parse_menu(text)
        note = date_note(menu["date"], now.date())
        top = _header(img, d, menu["title"], now, note)
        bottom = FRAME[3] - 40
        avail = bottom - top - 20
        ops, _ = plan_layout(menu["meals"], avail)
        # Spread spare room into the section gaps (capped), then centre what's left.
        spare = avail - _height(ops)
        n_sec = sum(1 for k, _, _ in ops if k == "secgap")
        add = min(spare // (n_sec + 2), 70)
        if add > 0:
            ops = [(k, p, h + add) if k == "secgap" else (k, p, h) for k, p, h in ops]
        spare = avail - _height(ops)
        draw_ops(d, ops, top + 20 + max(0, spare) // 2)

    _footer(d, now)
    page_dots(img, 2)
    return quantize(img)


def render_empty_state(img, d, now: datetime):
    """No menu.md yet: a sleepy cloche and how to add a menu."""
    y = _header(img, d, DEFAULT_TITLE, now, None, art=False)
    pic = cloche(330, "sleepy")
    bottom = FRAME[3] - 40
    block = pic.height + 70 + 56 + 4 * 52
    top = y + (bottom - y - block) // 2
    img.paste(pic, ((W - pic.width) // 2, top))
    ty = top + pic.height + 110
    serif(56, 500).text(d, (W / 2, ty), "Nothing on the menu yet", BLACK, "ms")
    hf = serif(36, 500, italic=True)
    msg = ("Plan breakfast, lunch and dinner on the dashboard web page, or add menu.md "
           "to the repository. It appears here after the next update.")
    for i, ln in enumerate(wrap(msg, hf, 760)):
        hf.text(d, (W / 2, ty + 70 + i * 50), ln, DARK, "ms")


# --------------------------------------------------------------------------
# Self-test
# --------------------------------------------------------------------------
TIDY_CASES = [
    # contract examples
    ("Greek yogurt: honey, walnuts", ("Greek Yogurt", "honey, walnuts")),
    ("flat white", ("Flat White", "")),
    ("chicken caesar salad", ("Chicken Caesar Salad", "")),
    ("Salmon: miso glaze, rice, broccoli", ("Salmon", "miso glaze, rice, broccoli")),
    ("BBQ ribs", ("BBQ Ribs", "")),
    ("chicken Caesar salad", ("Chicken Caesar Salad", "")),
    ("2 eggs on toast", ("2 Eggs on Toast", "")),
    # whitespace, bullets, numbering, punctuation
    ("   greek   yogurt :  honey ,walnuts.  ", ("Greek Yogurt", "honey, walnuts")),
    ("- oatmeal", ("Oatmeal", "")),
    ("* - oatmeal", ("Oatmeal", "")),
    ("1. pancakes: maple syrup", ("Pancakes", "maple syrup")),
    ("2) pancakes", ("Pancakes", "")),
    ("• toast", ("Toast", "")),
    ("[ ] toast", ("Toast", "")),
    ("toast.", ("Toast", "")),
    ("soup: tomato; basil;", ("Soup", "tomato, basil")),
    ("soup: tomato,, basil , ", ("Soup", "tomato, basil")),
    # small words
    ("the best toast", ("The Best Toast", "")),
    ("steak au poivre", ("Steak au Poivre", "")),
    ("pasta e fagioli", ("Pasta e Fagioli", "")),
    ("a bowl of pho", ("A Bowl of Pho", "")),
    ("coq au vin: with mushrooms", ("Coq au Vin", "with mushrooms")),
    # "w/", "&", " with "
    ("salmon w/ rice", ("Salmon", "rice")),
    ("salmon w/rice", ("Salmon", "rice")),
    ("toast: butter w/ jam", ("Toast", "butter with jam")),
    ("mac & cheese", ("Mac and Cheese", "")),
    ("R&D bar", ("R&D Bar", "")),
    ("chicken with rice and peas", ("Chicken", "rice and peas")),
    ("chicken with rice: soy", ("Chicken with Rice", "soy")),
    ("Salmon With Rice", ("Salmon With Rice", "")),   # capital "With" typed on purpose: kept
    ("with love", ("With Love", "")),
    # case kept as typed
    ("iced latte: Oatly, no sugar", ("Iced Latte", "Oatly, no sugar")),
    ("pb&j", ("Pb&j", "")),
    ("stir-fry: tofu", ("Stir-Fry", "tofu")),
    ("chef's salad", ("Chef's Salad", "")),
    ("(leftover) lasagna", ("(Leftover) Lasagna", "")),
    ("**pizza** night", ("Pizza Night", "")),
    # time-like colons are not separators
    ("brunch at 10:30", ("Brunch at 10:30", "")),
    # degenerate
    (": honey", ("Honey", "")),
    ("", ("", "")),
    ("   ", ("", "")),
    # review additions: meaning-preserving edge cases
    ("salmon w/o sauce", ("Salmon w/o Sauce", "")),       # "w/o" is "without": never "with o"
    ("tea w/oat milk", ("Tea", "oat milk")),
    ("half-and-half latte", ("Half-and-Half Latte", "")),
    ("cafe-au-lait", ("Cafe-au-Lait", "")),
    ("pasta: *fresh* basil", ("Pasta", "fresh basil")),
    ("GREEK YOGURT: HONEY", ("GREEK YOGURT", "HONEY")),   # typed capitals are kept
    ("crème brûlée: vanilla bean.", ("Crème Brûlée", "vanilla bean")),
    ("éclair au chocolat", ("Éclair au Chocolat", "")),
    ("红烧肉: 米饭, 青菜", ("红烧肉", "米饭, 青菜")),
    ("小笼包 with 醋", ("小笼包", "醋")),
    ("pizza 🍕: extra cheese", ("Pizza 🍕", "extra cheese")),
    ("coffee: 10:30 meeting", ("Coffee", "10:30 meeting")),
    ("toast: butter: jam", ("Toast", "butter: jam")),
    ("omelette: 2 eggs, cheddar!", ("Omelette", "2 eggs, cheddar")),
    ("steak & eggs", ("Steak and Eggs", "")),
    ("fish&chips", ("Fish&chips", "")),
    ("soup?", ("Soup?", "")),
    ("红烧肉：米饭，青菜。", ("红烧肉", "米饭, 青菜")),     # fullwidth punctuation from a Chinese IME
    ("早餐粥：皮蛋、瘦肉", ("早餐粥", "皮蛋, 瘦肉")),
]


def selftest() -> int:
    bad = 0
    for raw, want in TIDY_CASES:
        got = tidy_dish(raw)
        if got != want:
            bad += 1
            print(f"FAIL tidy_dish({raw!r}) = {got!r}, want {want!r}")
        if got[0] and tidy_dish(got[0] + (": " + got[1] if got[1] else "")) != got:
            bad += 1
            print(f"FAIL not idempotent: {raw!r} -> {got!r}")
    sample = parse_menu(
        "# Sunday Supper\nDate: 2026-11-01\nnotes here are ignored\n\n## breakfast\n- flat white\n"
        "## Snacks\n- chips\n## DINNER\n- Salmon: miso glaze\n* rice\nloose line\n## Breakfast\n- toast\n")
    want = {"title": "Sunday Supper", "date": date(2026, 11, 1),
            "meals": {"breakfast": [("Flat White", ""), ("Toast", "")], "lunch": [],
                      "dinner": [("Salmon", "miso glaze"), ("Rice", "")]}}
    if sample != want:
        bad += 1
        print(f"FAIL parse_menu: {sample!r}")
    if parse_menu("")["title"] != DEFAULT_TITLE or parse_menu("Date: 2026-13-45")["date"] is not None:
        bad += 1
        print("FAIL parse_menu defaults")
    today = date(2026, 11, 2)
    for plan, want_note in ((None, None), (today, None), (date(2026, 11, 1), "Planned for yesterday, Sunday"),
                            (date(2026, 11, 3), "Planned for tomorrow, Tuesday"),
                            (date(2026, 10, 25), "Planned for Sunday, October 25"),
                            (date(2025, 12, 31), "Planned for Wednesday, December 31, 2025")):
        if date_note(plan, today) != want_note:
            bad += 1
            print(f"FAIL date_note({plan}) = {date_note(plan, today)!r}")
    total = len(TIDY_CASES) + 2 + 6
    # Fonts: Chinese (simplified and traditional) and emoji come from the fallbacks, not as boxes.
    f = serif(58, 500)
    for s, want_font in (("红烧肉米饭青菜麻婆豆腐", 1), ("紅燒肉飯小籠包蘿蔔糕", 1), ("🍕🧀☕", 2), ("Crème brûlée", 0)):
        total += 1
        got = {f._fonts.index(ft) for _, ft in f.runs(s.replace(" ", ""))}
        if got != {want_font}:
            bad += 1
            print(f"FAIL font fallback for {s!r}: fonts {got}, want {{{want_font}}}")
    # Canvas rules on a hard case: size, mode, 16 grays, white overlay slots, page dots.
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "menu.md"
        p.write_text("# 今日菜单\n## Breakfast\n- 小笼包: 醋, 姜丝\n- pizza 🍕\n## Lunch\n"
                     + "".join(f"- dish number {i}: with a long list, of details, that wrap\n" for i in range(14))
                     + "## Dinner\n- 麻婆豆腐 with 米饭\n", encoding="utf-8")
        now = parse_now("2026-11-02T08:19")
        for path in (p, Path(td) / "missing.md"):
            im = render_menu(now, path)
            total += 1
            problems = []
            if im.size != (W, H) or im.mode != "L":
                problems.append(f"size/mode {im.size} {im.mode}")
            if any(n and v % 17 for v, n in enumerate(im.histogram())):
                problems.append("gray levels not multiples of 17")
            for box in ((508, 1556, 728, 1606), (752, 1556, 1172, 1606)):
                if im.crop(box).getextrema() != (255, 255):
                    problems.append(f"overlay slot {box} not white")
            left, right = im.getpixel((W // 2 - 15, 1628)), im.getpixel((W // 2 + 15, 1628))
            if not (left > 200 and right < 60):
                problems.append(f"page dots wrong ({left}, {right})")
            if problems:
                bad += 1
                print(f"FAIL render {path.name}: {'; '.join(problems)}")
    print(f"{'ok' if not bad else 'FAILED'}: {total - bad}/{total} checks passed")
    return 1 if bad else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(ROOT / "out" / "menu.png"))
    ap.add_argument("--menu", default=str(ROOT / "menu.md"))
    ap.add_argument("--now", help="override the clock (ISO 8601; naive = America/New_York)")
    ap.add_argument("--selftest", action="store_true", help="check the tidy rules and the parser")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    img = render_menu(parse_now(args.now), Path(args.menu))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, format="PNG", optimize=True)
    print(f"wrote {out} ({img.size[0]}x{img.size[1]}, mode {img.mode})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
