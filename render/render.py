#!/usr/bin/env python3
"""Render the Kindle e-ink dashboard (weather today and by hour, to-do, coffee) to a PNG.

Target: Kindle Paperwhite 5 (11th gen), 1236x1648 portrait, 16 gray levels.
Dependencies: Pillow + Python stdlib only.

Usage:
    python render/render.py --out out/dashboard.png
        [--weather-json render/sample_weather.json] [--now 2026-10-07T10:02]
        [--todo path/to/todo.md] [--coffee path/to/coffee.md]
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import unicodedata
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import doodles  # noqa: E402

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
FONT_DIR = ROOT / "fonts"
TZ = ZoneInfo("America/New_York")
CUP_SEASON = ""   # cup accessory for the current month (set by render())
CITY = "Boston"

WEATHER_URL = (
    "https://api.open-meteo.com/v1/forecast?latitude=42.3601&longitude=-71.0589"
    "&timezone=America%2FNew_York&temperature_unit=fahrenheit&wind_speed_unit=mph"
    "&precipitation_unit=inch"
    "&current=temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,"
    "wind_speed_10m,is_day"
    "&hourly=temperature_2m,precipitation_probability,weather_code"
    "&daily=weather_code,temperature_2m_max,temperature_2m_min,"
    "precipitation_probability_max,sunrise,sunset&forecast_days=2&past_days=1"
)

W, H = 1236, 1648
WEATHER_BOTTOM = 852
MARGIN = 64
CONTENT_W = W - 2 * MARGIN

# Gray palette - all multiples of 17 so they survive 16-level quantization.
WHITE = 255
BLACK = 0
DARK = 68      # secondary text (labels, units)
MID = 102      # de-emphasised text (done items); 119+ thin text washes out on e-ink
RULE = 187     # hairline dividers

# --------------------------------------------------------------------------
# Fonts
# --------------------------------------------------------------------------
_FONT_FILES = {
    "regular": "IBMPlexSans-Regular.ttf",
    "medium": "IBMPlexSans-Medium.ttf",
    "semibold": "IBMPlexSans-SemiBold.ttf",
    "bold": "IBMPlexSans-Bold.ttf",
    "italic": "IBMPlexSans-Italic.ttf",
    "icons": "weathericons-regular.ttf",
}
_font_cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}


def font(style: str, size: int) -> ImageFont.FreeTypeFont:
    key = (style, int(size))
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(str(FONT_DIR / _FONT_FILES[style]), int(size))
    return _font_cache[key]


# Weather Icons (Erik Flowers) codepoints.
ICON = {
    "day-sunny": "\uf00d", "night-clear": "\uf02e",
    "day-sunny-overcast": "\uf00c", "night-alt-partly-cloudy": "\uf081",
    "day-cloudy": "\uf002", "night-alt-cloudy": "\uf086",
    "cloudy": "\uf013", "fog": "\uf014", "day-fog": "\uf003", "night-fog": "\uf04a",
    "sprinkle": "\uf01c", "rain": "\uf019", "rain-mix": "\uf017", "showers": "\uf01a",
    "snow": "\uf01b", "sleet": "\uf0b5", "thunderstorm": "\uf01e", "hail": "\uf015",
    "raindrop": "\uf078", "umbrella": "\uf084", "strong-wind": "\uf050",
    "sunrise": "\uf051", "sunset": "\uf052", "humidity": "\uf07a", "na": "\uf07b", "cloud": "\uf041",
}

# WMO weather code -> (text, day icon, night icon)
WMO = {
    0: ("Clear", "day-sunny", "night-clear"),
    1: ("Mostly clear", "day-sunny-overcast", "night-alt-partly-cloudy"),
    2: ("Partly cloudy", "day-cloudy", "night-alt-cloudy"),
    3: ("Overcast", "cloudy", "cloudy"),
    45: ("Fog", "day-fog", "night-fog"),
    48: ("Freezing fog", "fog", "fog"),
    51: ("Light drizzle", "sprinkle", "sprinkle"),
    53: ("Drizzle", "sprinkle", "sprinkle"),
    55: ("Heavy drizzle", "sprinkle", "sprinkle"),
    56: ("Freezing drizzle", "rain-mix", "rain-mix"),
    57: ("Freezing drizzle", "rain-mix", "rain-mix"),
    61: ("Light rain", "rain", "rain"),
    63: ("Rain", "rain", "rain"),
    65: ("Heavy rain", "rain", "rain"),
    66: ("Freezing rain", "rain-mix", "rain-mix"),
    67: ("Freezing rain", "rain-mix", "rain-mix"),
    71: ("Light snow", "snow", "snow"),
    73: ("Snow", "snow", "snow"),
    75: ("Heavy snow", "snow", "snow"),
    77: ("Snow grains", "snow", "snow"),
    80: ("Light showers", "showers", "showers"),
    81: ("Showers", "showers", "showers"),
    82: ("Heavy showers", "showers", "showers"),
    85: ("Snow showers", "snow", "snow"),
    86: ("Heavy snow showers", "snow", "snow"),
    95: ("Thunderstorm", "thunderstorm", "thunderstorm"),
    96: ("Thunderstorm, hail", "hail", "hail"),
    99: ("Thunderstorm, hail", "hail", "hail"),
}


def wmo(code, is_day: bool = True) -> tuple[str, str]:
    try:
        text, day_icon, night_icon = WMO[int(code)]
    except (KeyError, TypeError, ValueError):
        return ("Unknown", "na")
    return text, (day_icon if is_day else night_icon)


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------
def warn(msg: str) -> None:
    print(f"warning: {msg}", file=sys.stderr)


def deg(v) -> str:
    n = int(round(float(v)))
    sign = "\u2212" if n < 0 else ""   # true minus sign, not a hyphen
    return f"{sign}{abs(n)}\u00b0"


def deg_c(f) -> str:
    """Fahrenheit value -> Celsius label, e.g. 54 -> "12°C"."""
    return deg((float(f) - 32) * 5 / 9) + "C"


def clock(dt: datetime) -> str:
    h = dt.hour % 12 or 12
    return f"{h}:{dt.minute:02d} {'AM' if dt.hour < 12 else 'PM'}"


def hour_label(dt: datetime) -> str:
    h = dt.hour % 12 or 12
    return f"{h} {'AM' if dt.hour < 12 else 'PM'}"


def text_w(s: str, f: ImageFont.FreeTypeFont) -> float:
    return f.getlength(s)


def ellipsize(s: str, f, max_w: float) -> str:
    if text_w(s, f) <= max_w:
        return s
    ell = "…"
    while s and text_w(s.rstrip() + ell, f) > max_w:
        s = s[:-1]
    return s.rstrip(" ,;:-") + ell


def wrap(s: str, f, max_w: float, max_lines: int | None = None) -> list[str]:
    """Greedy word wrap; splits over-long words; ellipsizes the last allowed line."""
    words = s.split()
    lines: list[str] = []
    cur = ""
    for word in words:
        cand = f"{cur} {word}" if cur else word
        if text_w(cand, f) <= max_w:
            cur = cand
            continue
        if cur:
            lines.append(cur)
        # break words that are wider than a full line
        while text_w(word, f) > max_w:
            i = len(word)
            while i > 1 and text_w(word[:i], f) > max_w:
                i -= 1
            lines.append(word[:i])
            word = word[i:]
        cur = word
    if cur:
        lines.append(cur)
    if max_lines is not None and len(lines) > max_lines:
        rest = " ".join(lines[max_lines - 1:])
        lines = lines[: max_lines - 1] + [ellipsize(rest, f, max_w)]
    return lines or [""]


def clean_md(s: str) -> str:
    """Strip light inline markdown so the e-ink text reads cleanly."""
    s = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", s)   # links / images
    s = re.sub(r"(\*\*|__|\*|_|`|~~)(.+?)\1", r"\2", s)  # emphasis, code
    return s.strip()


def draw_icon(d: ImageDraw.ImageDraw, name: str, cx: float, cy: float, box: int, fill=BLACK):
    """Draw a weather-icons glyph scaled so its ink fits a box x box square, centred."""
    ch = ICON.get(name, ICON["na"])
    ref = font("icons", 200)
    l, t, r, b = ref.getbbox(ch)
    scale = box / max(r - l, b - t, 1)
    f = font("icons", max(8, int(200 * scale)))
    l, t, r, b = f.getbbox(ch)
    d.text((cx - (l + r) / 2, cy - (t + b) / 2), ch, font=f, fill=fill)


def hrule(d, y, x0=MARGIN, x1=W - MARGIN, fill=RULE, width=2):
    d.rectangle([x0, y, x1, y + width - 1], fill=fill)


def section_label(d, x, y, label: str, right: str | None = None, x1: float | None = None, minor: bool = False):
    """Section title in sentence case (baseline at y); minor=True for quieter column heads."""
    f = font("regular", 30) if minor else font("semibold", 36)
    d.text((x, y), label, font=f, fill=DARK if minor else BLACK, anchor="ls")
    if right and x1 is not None:
        d.text((x1, y), right, font=font("regular", 30), fill=DARK, anchor="rs")


# --------------------------------------------------------------------------
# Data loading
# --------------------------------------------------------------------------
def load_weather(path: str | None) -> dict | None:
    try:
        if path:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        else:
            req = urllib.request.Request(WEATHER_URL, headers={"User-Agent": "kindle-dashboard/1.0"})
            last = None
            for _ in range(3):
                try:
                    with urllib.request.urlopen(req, timeout=20) as resp:
                        data = json.loads(resp.read().decode("utf-8"))
                    break
                except Exception as e:  # noqa: BLE001
                    last = e
            else:
                raise last  # type: ignore[misc]
        for key in ("current", "hourly", "daily"):
            if key not in data:
                raise ValueError(f"response missing '{key}'")
        return data
    except Exception as e:  # noqa: BLE001
        warn(f"weather unavailable ({e.__class__.__name__}: {e})")
        return None


TODO_RE = re.compile(r"^\s*[-*+]\s+\[([ xX])\]\s+(.*\S)\s*$")


def load_todos(path: Path) -> tuple[list[str], list[str]]:
    open_items, done_items = [], []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception as e:  # noqa: BLE001
        warn(f"could not read {path}: {e}")
        return open_items, done_items
    for line in lines:
        m = TODO_RE.match(line)
        if not m:
            continue
        text = clean_md(m.group(2))
        if not text:
            continue
        (done_items if m.group(1) in "xX" else open_items).append(text)
    return open_items, done_items


META_RE = re.compile(r"^\s*[-*+]\s+([^:]{1,40}?)\s*:\s*(.+?)\s*$")


def load_beans(path: Path) -> tuple[list[dict], dict[str, str]]:
    """Saved beans (`## Name` + `- Key: value`) and the choice of beans to show.

    The choice is the `- Coffee: name` and `- Decaf: name` lines above the first bean.
    """
    beans: list[dict] = []
    chosen: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception as e:  # noqa: BLE001
        warn(f"could not read {path}: {e}")
        return beans, chosen
    cur = None
    for line in lines:
        if line.startswith("## "):
            cur = {"name": clean_md(line[3:]), "meta": []}
            beans.append(cur)
            continue
        if line.startswith("#"):
            cur = None if not line.startswith("###") else cur
            continue
        m = META_RE.match(line)
        if not m:
            continue
        if cur is not None:
            cur["meta"].append((clean_md(m.group(1)), en_dash(clean_md(m.group(2)))))
        elif not beans and m.group(1).strip().lower() in ("coffee", "decaf"):
            chosen[m.group(1).strip().lower()] = clean_md(m.group(2))
    return [b for b in beans if b["name"]], chosen


def en_dash(s: str) -> str:
    """Typographic ranges: '28-30 s' -> '28–30 s'."""
    return re.sub(r"(\d)\s*-\s*(\d)", "\\1\u2013\\2", s)


def bean_key(name: str) -> str:
    """Match names loosely: "Café  de Huila" and "cafe de huila" are the same bean."""
    s = unicodedata.normalize("NFKD", name)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.lower().split())


def pick_beans(beans: list[dict], chosen: dict[str, str], now: datetime) -> list[dict]:
    """[regular] or [regular, decaf]. A chosen name that is not saved shows with no settings."""
    by_key = {bean_key(b["name"]): b for b in beans}

    def find(name):
        return by_key.get(bean_key(name), {"name": name, "meta": [], "missing": True})

    decaf = find(chosen["decaf"]) if chosen.get("decaf") else None
    if chosen.get("coffee"):
        regular = find(chosen["coffee"])
    else:  # no choice: rotate daily through the saved beans
        pool = [b for b in beans if b is not decaf] or beans
        if not pool:
            return [decaf] if decaf else []
        regular = pool[now.timetuple().tm_yday % len(pool)]
    return [regular, decaf] if decaf else [regular]


# --------------------------------------------------------------------------
# Weather section
# --------------------------------------------------------------------------
def _local(ts: str) -> datetime:
    return datetime.fromisoformat(ts)  # Open-Meteo returns naive local times


def draw_weather(img: Image.Image, d: ImageDraw.ImageDraw, wx: dict | None, now: datetime, top: int, bottom: int):
    if wx is None:
        draw_weather_unavailable(d, top, bottom)
        return
    try:
        _draw_weather(img, d, wx, now, top)
    except Exception as e:  # noqa: BLE001  (malformed response - keep the rest alive)
        warn(f"weather data malformed ({e.__class__.__name__}: {e})")
        d.rectangle([0, top, W, bottom], fill=WHITE)
        draw_weather_unavailable(d, top, bottom)


def draw_weather_unavailable(d, top, bottom):
    pad = 24
    d.rounded_rectangle([MARGIN, top + pad, W - MARGIN, bottom - pad], radius=24, outline=MID, width=3)
    cy = (top + bottom) / 2
    draw_icon(d, "cloud", W / 2, cy - 70, 130, fill=MID)
    d.text((W / 2, cy + 50), "Weather unavailable", font=font("bold", 52), fill=BLACK, anchor="ms")
    d.text((W / 2, cy + 105), "Will retry at the next update", font=font("regular", 34), fill=DARK, anchor="ms")


def _draw_weather(img, d, wx, now, top):
    cur = wx["current"]
    daily = wx["daily"]
    hourly = wx["hourly"]
    now_naive = now.replace(tzinfo=None)
    today = now_naive.date().isoformat()

    di = daily["time"].index(today) if today in daily["time"] else 0
    is_day = bool(cur.get("is_day", 1))
    cond, icon = wmo(cur.get("weather_code"), is_day)

    # ---- Hero: icon + giant temperature (left), condition block (right) ----
    hero_top = top
    hero_h = 232
    cy = hero_top + hero_h / 2
    icon_box = 200
    hero = doodles.weather(doodles.weather_kind(cur.get("weather_code"), is_day), icon_box)
    img.paste(hero, (MARGIN, int(cy - hero.height / 2)))

    temp_x = MARGIN + icon_box + 40
    right_x = 760
    temp = deg(cur["temperature_2m"])
    size = 220
    while size > 120 and text_w(temp, font("medium", size)) > right_x - 48 - temp_x:
        size -= 10
    tf = font("medium", size)
    # Celsius below the digits; centre the pair (digit cap top .. Celsius baseline) on the hero centre line.
    _, t, _, _ = tf.getbbox("0", anchor="ls")
    cf_ = font("regular", 44)
    c_cap = -cf_.getbbox("0", anchor="ls")[1]
    gap = 34
    base = cy + (-t - gap - c_cap) / 2
    d.text((temp_x, base), temp, font=tf, fill=BLACK, anchor="ls")
    d.text((temp_x + 8, base + gap + c_cap), deg_c(cur["temperature_2m"]), font=cf_, fill=DARK, anchor="ls")

    # Right column
    cw = W - MARGIN - right_x
    csize = 56 if text_w(cond, font("semibold", 56)) <= cw else 44
    cf = font("semibold", csize)
    clh = int(csize * 1.18)
    cond_lines = wrap(cond, cf, cw, max_lines=2)
    # Centre the block (cond cap-top .. H/L baseline) on the hero centre line.
    block_h = 0.70 * csize + clh * (len(cond_lines) - 1) + 56 + 52
    y = cy - block_h / 2 + 0.70 * csize
    for ln in cond_lines:
        d.text((right_x, y), ln, font=cf, fill=BLACK, anchor="ls")
        y += clh
    y += 56 - clh
    rf = font("regular", 38)
    d.text((right_x, y), f"Feels like {deg(cur['apparent_temperature'])}", font=rf, fill=DARK, anchor="ls")
    y += 52
    hi, lo = daily["temperature_2m_max"][di], daily["temperature_2m_min"][di]
    bf = font("bold", 38)
    x = right_x
    for part, f, col in (("H ", rf, DARK), (deg(hi), bf, BLACK), ("   L ", rf, DARK), (deg(lo), bf, BLACK)):
        d.text((x, y), part, font=f, fill=col, anchor="ls")
        x += text_w(part, f)

    # ---- One sentence in plain words ----
    sentence = weather_sentence(wx, now)
    sy = hero_top + hero_h + 58
    if sentence:
        sf = fit_font("medium", sentence, CONTENT_W, 38, 30)
        d.text((MARGIN, sy), ellipsize(sentence, sf, CONTENT_W), font=sf, fill=BLACK, anchor="ls")

    # ---- Stat row: rain and wind, then a daylight bar across the right half ----
    y0 = sy + 22
    cell = CONTENT_W / 4
    pp = daily.get("precipitation_probability_max", [None] * (di + 1))[di]
    stats = [("umbrella", f"{int(pp) if pp is not None else 0}%", "Rain"),
             ("strong-wind", f"{int(round(cur.get('wind_speed_10m', 0)))} mph", "Wind")]
    for i, (ic, val, label) in enumerate(stats):
        x = MARGIN + i * cell
        draw_icon(d, ic, x + 30, y0 + 40, 52)
        d.text((x + 76, y0 + 40), val, font=font("bold", 40), fill=BLACK, anchor="ls")
        d.text((x + 76, y0 + 78), label, font=font("regular", 30), fill=DARK, anchor="ls")
    draw_daylight(img, d, MARGIN + 2 * cell + 6, W - MARGIN, y0,
                  _local(daily["sunrise"][di]), _local(daily["sunset"][di]), now_naive)
    y = y0 + 104
    hrule(d, y)

    # ---- Next 12 hours: temperature line, rain bars, a label every 3 hours ----
    draw_hourly_chart(img, d, hourly, daily, now_naive, y, WEATHER_BOTTOM)


def _smooth(xs, ys, steps=10):
    """Catmull-Rom spline through the points, for a hand-drawn-looking line."""
    pts = list(zip(xs, ys))
    ext = [pts[0]] + pts + [pts[-1]]
    out = []
    for i in range(1, len(ext) - 2):
        (x0, y0), (x1, y1), (x2, y2), (x3, y3) = ext[i - 1], ext[i], ext[i + 1], ext[i + 2]
        for k in range(steps):
            t = k / steps
            t2, t3 = t * t, t * t * t
            out.append((0.5 * (2 * x1 + (-x0 + x2) * t + (2 * x0 - 5 * x1 + 4 * x2 - x3) * t2 + (-x0 + 3 * x1 - 3 * x2 + x3) * t3),
                        0.5 * (2 * y1 + (-y0 + y2) * t + (2 * y0 - 5 * y1 + 4 * y2 - y3) * t2 + (-y0 + 3 * y1 - 3 * y2 + y3) * t3)))
    out.append(pts[-1])
    return out


def _layer(w, h, S=4):
    im = Image.new("L", (int(w * S), int(h * S)), WHITE)
    return im, ImageDraw.Draw(im)


def draw_daylight(img, d, x0, x1, y0, sunrise, sunset, now_n):
    """Sunrise-to-sunset bar: thick black for daylight gone, thin gray for daylight left, a sun at now."""
    S = 4
    h = 60
    lay, ld = _layer(x1 - x0, h)
    by = 28                         # bar centre within the layer
    w = x1 - x0
    pad = 16                        # room for the marker at either end
    a, b = pad, w - pad
    if now_n <= sunrise:
        frac, marker = 0.0, "moon"
    elif now_n >= sunset:
        frac, marker = 1.0, "moon"
    else:
        frac, marker = (now_n - sunrise) / (sunset - sunrise), "sun"
    mx = a + (b - a) * frac
    ld.line([(a * S, by * S), (b * S, by * S)], fill=RULE, width=4 * S)
    for x in (a, b):
        ld.ellipse([(x - 2) * S, (by - 2) * S, (x + 2) * S, (by + 2) * S], fill=RULE)
    if mx > a:
        ld.line([(a * S, by * S), (mx * S, by * S)], fill=BLACK, width=7 * S)
        ld.ellipse([(a - 3.5) * S, (by - 3.5) * S, (a + 3.5) * S, (by + 3.5) * S], fill=BLACK)
    if marker == "sun":
        for k in range(8):
            t = math.radians(k * 45)
            ld.line([((mx + 15 * math.cos(t)) * S, (by + 15 * math.sin(t)) * S),
                     ((mx + 21 * math.cos(t)) * S, (by + 21 * math.sin(t)) * S)], fill=BLACK, width=round(3.5 * S))
        ld.ellipse([(mx - 10) * S, (by - 10) * S, (mx + 10) * S, (by + 10) * S], fill=WHITE, outline=BLACK, width=round(3.5 * S))
    else:
        ld.ellipse([(mx - 11) * S, (by - 11) * S, (mx + 11) * S, (by + 11) * S], fill=BLACK)
        ld.ellipse([(mx - 4) * S, (by - 15) * S, (mx + 15) * S, (by + 4) * S], fill=WHITE)
    img.paste(lay.resize((int(w), h), Image.LANCZOS), (int(x0), int(y0 - 2)))
    tf = font("bold", 32)
    d.text((x0 + 6, y0 + 78), clock(sunrise), font=tf, fill=BLACK, anchor="ls")
    d.text((x1, y0 + 78), clock(sunset), font=tf, fill=BLACK, anchor="rs")
    mins = int((sunset - sunrise).total_seconds() // 60)
    d.text(((x0 + x1) / 2 + 6, y0 + 78), f"{mins // 60} h {mins % 60} m", font=font("regular", 28), fill=DARK, anchor="ms")


def draw_hourly_chart(img, d, hourly, daily, now_n, top, bottom):
    times = [_local(t) for t in hourly["time"]]
    start = max((i for i, t in enumerate(times) if t <= now_n), default=0)
    idx = list(range(start, min(start + 13, len(times))))
    if len(idx) < 2:
        return
    temps = [hourly["temperature_2m"][i] for i in idx]
    probs = [(hourly.get("precipitation_probability") or [0] * len(times))[i] or 0 for i in idx]
    x0, x1 = MARGIN + 46, W - MARGIN - 46
    xs = [x0 + (x1 - x0) * k / (len(idx) - 1) for k in range(len(idx))]
    icon_cy = top + 42
    line_top, line_bot = top + 128, top + 176
    bar_base, bar_max = bottom - 50, 32
    lo, hi = min(temps), max(temps)
    span = max(hi - lo, 4)
    ys = [line_bot - (t - lo) / span * (line_bot - line_top) for t in temps]
    marks = list(range(0, len(idx), 3))

    S = 4
    lay, ld = _layer(W, bottom - top)
    Y = lambda v: (v - top) * S  # noqa: E731
    # Rain chance: one bar per hour, height = probability.
    ld.line([(x0 - 14) * S, Y(bar_base) + S, (x1 + 14) * S, Y(bar_base) + S], fill=RULE, width=2 * S)
    for x, pr in zip(xs, probs):
        if pr >= 20:
            hgt = max(4, bar_max * pr / 100)
            ld.rounded_rectangle([(x - 9) * S, Y(bar_base - hgt), (x + 9) * S, Y(bar_base)], radius=3 * S, fill=153)
    # Temperature line and dots at the labelled hours; "now" gets a ring.
    ld.line([(x * S, Y(y)) for x, y in _smooth(xs, ys)], fill=BLACK, width=5 * S, joint="curve")
    for k in marks:
        x, y = xs[k], ys[k]
        r = 11 if k == 0 else 7
        ld.ellipse([(x - r) * S, Y(y - r), (x + r) * S, Y(y + r)], fill=BLACK)
        if k == 0:
            ld.ellipse([(x - 5) * S, Y(y - 5), (x + 5) * S, Y(y + 5)], fill=WHITE)
    img.paste(lay.resize((W, bottom - top), Image.LANCZOS), (0, top))

    sun = {t: (_local(daily["sunrise"][k]), _local(daily["sunset"][k])) for k, t in enumerate(daily["time"])}
    tf, cf, lf = font("bold", 38), font("regular", 26), font("regular", 30)
    for k in marks:
        i, x, y = idx[k], xs[k], ys[k]
        t = times[i]
        sr, ss = sun.get(t.date().isoformat(), (None, None))
        day = (sr <= t < ss) if sr and ss else (6 <= t.hour < 19)
        draw_icon(d, wmo(hourly["weather_code"][i], day)[1], x, icon_cy, 46)
        f_txt, c_txt = deg(temps[k]), " " + deg_c(temps[k])
        wf, wc = text_w(f_txt, tf), text_w(c_txt, cf)
        lx = min(max(x - (wf + wc) / 2, MARGIN), W - MARGIN - wf - wc)   # keep edge labels inside the margins
        d.text((lx, y - 22), f_txt, font=tf, fill=BLACK, anchor="ls")
        d.text((lx + wf, y - 22), c_txt, font=cf, fill=DARK, anchor="ls")
        d.text((x, bottom - 12), "Now" if k == 0 else hour_label(t), font=lf, fill=BLACK if k == 0 else DARK, anchor="ms")
    # Label the wettest hour if rain is worth mentioning.
    wet = max(range(len(idx)), key=lambda k: probs[k])
    if probs[wet] >= 30:
        hgt = max(4, bar_max * probs[wet] / 100)
        d.text((xs[wet] + 14, bar_base - hgt + 18), f"{int(probs[wet])}%", font=font("regular", 26), fill=DARK, anchor="ls")

SNOW_CODES = {71, 73, 75, 77, 85, 86}


def weather_sentence(wx: dict, now: datetime) -> str:
    """One plain sentence about the next 12 hours, plus a comparison with yesterday when it's notable."""
    hourly, daily = wx["hourly"], wx["daily"]
    now_n = now.replace(tzinfo=None)
    times = [_local(t) for t in hourly["time"]]
    probs = [p or 0 for p in (hourly.get("precipitation_probability") or [0] * len(times))]
    codes = [c if c is not None else -1 for c in hourly["weather_code"]]
    win = [i for i, t in enumerate(times) if now_n - timedelta(minutes=59) <= t <= now_n + timedelta(hours=12)]
    if not win:
        return ""
    at = lambda i: "now" if times[i] <= now_n else f"around {hour_label(times[i])}"  # noqa: E731
    parts = []
    storm = next((i for i in win if codes[i] >= 95), None)
    snow = next((i for i in win if codes[i] in SNOW_CODES and probs[i] >= 40), None)
    rain = next((i for i in win if probs[i] >= 50), None)
    if storm is not None:
        parts.append(f"Thunderstorms possible {at(storm)}.")
    elif snow is not None:
        parts.append("Snow likely now." if times[snow] <= now_n else f"Snow likely from about {hour_label(times[snow])}.")
    elif rain is not None:
        if times[rain] <= now_n:
            end = next((i for i in win if i > rain and probs[i] < 30), None)
            parts.append(f"Rain until about {hour_label(times[end])}." if end is not None else "Rain on and off for the next 12 hours.")
        else:
            parts.append(f"Rain likely from about {hour_label(times[rain])}. Take an umbrella.")
    else:
        peak = max(win, key=lambda i: probs[i])
        if probs[peak] >= 30:
            parts.append(f"A chance of showers {at(peak)}.")
        else:
            parts.append("No rain expected tonight." if now_n.hour >= 18 else "No rain expected today.")
    days = daily["time"]
    today, yday = now_n.date().isoformat(), (now_n.date() - timedelta(days=1)).isoformat()
    if today in days and yday in days:
        diff = round(daily["temperature_2m_max"][days.index(today)] - daily["temperature_2m_max"][days.index(yday)])
        if abs(diff) >= 6:
            parts.append(f"{abs(diff)}° {'warmer' if diff > 0 else 'colder'} than yesterday.")
    return " ".join(parts)


# --------------------------------------------------------------------------
# To-do section
# --------------------------------------------------------------------------
def draw_checkbox(d, x, y, size, done: bool):
    if done:
        d.rounded_rectangle([x, y, x + size, y + size], radius=6, outline=MID, width=3)
        d.line([(x + size * 0.22, y + size * 0.52), (x + size * 0.42, y + size * 0.72),
                (x + size * 0.80, y + size * 0.28)], fill=MID, width=4, joint="curve")
    else:
        d.rounded_rectangle([x, y, x + size, y + size], radius=6, outline=BLACK, width=3)


def draw_todo(d, x0, x1, top, bottom, open_items, done_items):
    section_label(d, x0, top + 30, "To-do",
                  f"{len(open_items)} open" if open_items else None, x1)
    y = top + 76
    n = len(open_items)
    size = 44 if n <= 3 else 40 if n <= 5 else 38      # short lists get bigger type
    f = font("regular", size)
    lh = size + 12
    box = 30
    tx = x0 + box + 22
    tw = x1 - tx

    if not open_items and not done_items:
        d.text((x0, y + 38), "Nothing on the list.", font=font("italic", 38), fill=DARK, anchor="ls")
        return y + 60

    if not open_items:
        d.text((x0, y + 38), "All done!", font=font("bold", 38), fill=BLACK, anchor="ls")
        y += lh + 18

    shown = 0
    for i, item in enumerate(open_items):
        remaining = len(open_items) - i - 1
        reserve = lh if remaining else 0
        fit = int((bottom - y - reserve) // lh)   # lines still available
        if fit < 1:
            break
        lines = wrap(item, f, tw, max_lines=min(3 if n <= 3 else 2, fit))
        need = len(lines) * lh
        draw_checkbox(d, x0, y + size - 28, box, False)
        for k, ln in enumerate(lines):
            d.text((tx, y + size + k * lh), ln, font=f, fill=BLACK, anchor="ls")
        y += need + 16
        shown += 1

    hidden_open = len(open_items) - shown
    if hidden_open:
        d.text((tx, y + 34), f"+{hidden_open} more", font=font("bold", 34), fill=DARK, anchor="ls")
        return y + 50

    # Done items: de-emphasised, one line each, only while space remains.
    df = font("regular", 34)
    dlh = 46
    shown_done = 0
    if done_items:
        y += 8
    for i, item in enumerate(done_items):
        remaining = len(done_items) - i - 1
        reserve = dlh if remaining else 0
        if y + dlh + reserve > bottom:
            break
        draw_checkbox(d, x0, y + 8, box, True)
        s = ellipsize(item, df, tw)
        d.text((tx, y + 34), s, font=df, fill=MID, anchor="ls")
        sy = y + 34 - 12
        d.line([(tx, sy), (tx + text_w(s, df), sy)], fill=MID, width=2)
        y += dlh + 8
        shown_done += 1
    hidden_done = len(done_items) - shown_done
    if hidden_done:
        d.text((tx, y + 34), f"+{hidden_done} done", font=font("regular", 32), fill=DARK, anchor="ls")
        y += 50
    return y


# --------------------------------------------------------------------------
# Coffee section
# --------------------------------------------------------------------------
def draw_coffee(img, d, x0, x1, top, bottom, shown, cup_mood="awake"):
    if len(shown) == 2:
        draw_coffee_pair(img, d, x0, x1, top, bottom, shown, cup_mood)
        return
    section_label(d, x0, top + 30, "Coffee of the day")
    if not shown:
        d.text((x0, top + 114), "No beans yet.", font=font("italic", 38), fill=DARK, anchor="ls")
        d.text((x0, top + 164), "Add one to coffee.md", font=font("regular", 32), fill=DARK, anchor="ls")
        return
    b = shown[0]
    width = x1 - x0
    y = top + 76

    # Cartoon cup in the bottom-right corner; rows beside it wrap short of it.
    mascot = doodles.coffee_cup(170, cup_mood, CUP_SEASON)
    mx, my = int(x1 - mascot.width), int(bottom - mascot.height)
    img.paste(mascot, (mx, my))

    # Bean name: big and bold, up to two lines.
    nf = font("bold", 52)
    for ln in wrap(b["name"], nf, width, max_lines=2):
        d.text((x0, y + 50), ln, font=nf, fill=BLACK, anchor="ls")
        y += 64
    y += 30
    hrule(d, y - 14, x0, x1)

    # Key / value rows (Grams, Grind, Roast, ...): gray label, large bold value.
    # Use the roomiest layout where every row fits; the last one drops rows that don't.
    if not b["meta"]:
        if b.get("missing"):
            d.text((x0, y + 40), "No saved settings", font=font("italic", 34), fill=DARK, anchor="ls")
        return
    layouts = [dict(vsize=46, row_gap=26, max_lines=2), dict(vsize=42, row_gap=14, max_lines=2),
               dict(vsize=40, row_gap=10, max_lines=1)]
    for n, cfg in enumerate(layouts):
        if _bean_rows(None, b["meta"], x0, width, y, bottom, mx, my, **cfg) or n == len(layouts) - 1:
            _bean_rows(d, b["meta"], x0, width, y, bottom, mx, my, **cfg)
            return


def fit_font(style: str, s: str, max_w: float, size: int, min_size: int) -> ImageFont.FreeTypeFont:
    """Largest font from size down to min_size in which s fits max_w (min_size if none does)."""
    while size > min_size and text_w(s, font(style, size)) > max_w:
        size -= 2
    return font(style, size)


def draw_coffee_pair(img, d, x0, x1, top, bottom, shown, cup_mood="awake"):
    """Regular and decaf side by side: one column per bean, one row per setting."""
    section_label(d, x0, top + 30, "Coffee")
    keys: list[str] = []
    for b in shown:
        keys += [k for k, _ in b["meta"] if k.lower() not in (x.lower() for x in keys)]
    lf = font("regular", 30)
    label_w = max([text_w(k, lf) for k in keys] + [0]) + 22
    colw = (x1 - x0 - label_w - 24) / 2
    cols = [x0 + label_w, x0 + label_w + colw + 24]

    # Column heads: kind (small caps) then the bean name, shrunk or wrapped to fit.
    y = top + 82
    for cx, kind in zip(cols, ("Regular", "Decaf")):
        section_label(d, cx, y + 26, kind, minor=True)
    y += 44
    # One size for both names: the largest at which every word fits its column.
    words = [w for b in shown for w in b["name"].split()] or [""]
    nf = fit_font("bold", max(words, key=lambda w: text_w(w, font("bold", 40))), colw, 40, 28)
    lh = nf.size + 8
    name_lines = [wrap(b["name"], nf, colw, max_lines=2) for b in shown]
    for cx, lines in zip(cols, name_lines):
        for i, ln in enumerate(lines):
            d.text((cx, y + nf.size + i * lh), ln, font=nf, fill=BLACK, anchor="ls")
    y += max(len(lines) for lines in name_lines) * lh + 18
    hrule(d, y, x0, x1)
    y += 14

    if not keys:
        d.text((x0, y + 40), "No saved settings", font=font("italic", 34), fill=DARK, anchor="ls")
        return
    # Rows: gray label, then each bean's value (a dash if it has none).
    row_h = min(62, (bottom - y) // len(keys))
    for k in keys:
        d.text((x0, y + row_h - 16), ellipsize(k, lf, label_w - 12), font=lf, fill=DARK, anchor="ls")
        for cx, b in zip(cols, shown):
            v = next((v for kk, v in b["meta"] if kk.lower() == k.lower()), "\u2013")
            vf = fit_font("bold", v, colw, 42, 30)
            d.text((cx, y + row_h - 16), ellipsize(v, vf, colw), font=vf, fill=BLACK, anchor="ls")
        y += row_h

    # Cartoon cup in the bottom-right corner, if the rows left room for it.
    room = bottom - y - 8
    if room >= 110:
        mascot = doodles.coffee_cup(min(170, room), cup_mood, CUP_SEASON)
        img.paste(mascot, (int(x1 - mascot.width), int(bottom - mascot.height)))


def _bean_rows(d, meta, x0, width, y, bottom, mx, my, vsize, row_gap, max_lines) -> bool:
    """Draw (or with d=None, measure) the key/value rows. Returns True if all rows fit."""
    lf, vf = font("regular", 32), font("bold", vsize)
    line_h = vsize + 10
    label_w = min(max(text_w(k, lf) for k, _ in meta) + 28, width * 0.42)
    for k, v in meta:
        avail = width - label_w
        if y + line_h * max_lines > my:  # this row may reach down beside the cup
            avail = mx - 20 - (x0 + label_w)
        vlines = wrap(v, vf, avail, max_lines=max_lines)
        if y + 14 + line_h * len(vlines) > bottom:
            return False
        if d is not None:
            d.text((x0, y + vsize), ellipsize(k, lf, label_w - 16), font=lf, fill=DARK, anchor="ls")
            for i, ln in enumerate(vlines):
                d.text((x0 + label_w, y + vsize + i * line_h), ln, font=vf, fill=BLACK, anchor="ls")
        y += line_h * len(vlines) + row_gap
    return True


# --------------------------------------------------------------------------
# Page
# --------------------------------------------------------------------------
def render(now: datetime, wx: dict | None, todo_path: Path, coffee_path: Path) -> Image.Image:
    img = Image.new("L", (W, H), WHITE)
    d = ImageDraw.Draw(img)

    # Header
    d.text((MARGIN, 104), f"{now:%A}, {now:%B} {now.day}", font=font("bold", 60), fill=BLACK, anchor="ls")
    d.text((W - MARGIN, 104), CITY, font=font("regular", 38), fill=DARK, anchor="rs")
    hrule(d, 134, fill=BLACK, width=4)

    # Weather
    weather_top, weather_bottom = 158, WEATHER_BOTTOM
    draw_weather(img, d, wx, now, weather_top, weather_bottom)
    hrule(d, weather_bottom, fill=BLACK, width=4)

    # Lower: to-do (left) | coffee (right)
    footer_rule = H - 106
    low_top, low_bottom = weather_bottom + 30, footer_rule - 24
    gutter = 72
    colw = (CONTENT_W - gutter) / 2
    lx0, lx1 = MARGIN, MARGIN + colw
    rx0, rx1 = lx1 + gutter, W - MARGIN
    d.rectangle([lx1 + gutter / 2 - 1, low_top + 8, lx1 + gutter / 2, low_bottom], fill=RULE)
    try:
        open_items, done_items = load_todos(todo_path)
        list_end = draw_todo(d, lx0, lx1, low_top, low_bottom, open_items, done_items) or low_bottom
        # Clipboard centred in the space the list leaves, so short lists don't leave a hole.
        free = low_bottom - list_end
        if free >= 150:
            mood = "cheer" if not open_items else "busy" if len(open_items) >= 6 else "happy"
            board = doodles.clipboard(int(min(215, free - 40) * 200 / 212), mood)
            img.paste(board, (int((lx0 + lx1 - board.width) / 2), int(list_end + (free - board.height) / 2)))
    except Exception as e:  # noqa: BLE001  never let one section kill the image
        warn(f"to-do section failed ({e.__class__.__name__}: {e})")
    try:
        cup_mood = "sleepy" if now.hour >= 17 or now.hour < 5 else "awake"
        global CUP_SEASON
        CUP_SEASON = doodles.season_for(now.month)
        draw_coffee(img, d, rx0, rx1, low_top, low_bottom, pick_beans(*load_beans(coffee_path), now), cup_mood)
    except Exception as e:  # noqa: BLE001
        warn(f"coffee section failed ({e.__class__.__name__}: {e})")

    # Footer
    hrule(d, footer_rule)
    ff = font("regular", 30)
    d.text((MARGIN, H - 56), "Weather: Open-Meteo.com", font=ff, fill=DARK, anchor="ls")
    d.text((W - MARGIN, H - 56), f"Updated {clock(now)}", font=ff, fill=DARK, anchor="rs")

    # Quantize to the panel's 16 gray levels (multiples of 17).
    return img.point([min(255, int(v / 17 + 0.5) * 17) for v in range(256)])


# Footer slots the Kindle draws into (keep in sync with kindle/dashboard/bin/common.sh).
STALE_W, STALE_H = 420, 50
STALE_X, STALE_Y = W - MARGIN - STALE_W, H - 92


def render_stale(now: datetime) -> Image.Image:
    """Bold black pill the Kindle shows over the footer when this image is more than 3 hours old."""
    S = 4
    im = Image.new("L", (STALE_W * S, STALE_H * S), WHITE)
    d = ImageDraw.Draw(im)
    text = f"Last updated {clock(now)}"
    f = font("bold", 30 * S)
    tw = d.textlength(text, font=f)
    pad = 20 * S
    x1 = STALE_W * S
    d.rounded_rectangle([x1 - tw - 2 * pad, 4 * S, x1, (STALE_H - 4) * S], radius=21 * S, fill=BLACK)
    d.text((x1 - pad, 36 * S), text, font=f, fill=WHITE, anchor="rs")
    out = im.resize((STALE_W, STALE_H), Image.LANCZOS)
    return out.point([min(255, int(v / 17 + 0.5) * 17) for v in range(256)])


def render_night(now: datetime, wx: dict | None) -> Image.Image:
    """Shown from midnight to 6 AM while the Kindle sleeps: a sleepy moon and the coming day's weather."""
    img = Image.new("L", (W, H), WHITE)
    d = ImageDraw.Draw(img)
    moon = doodles.weather("moon", 420)
    img.paste(moon, ((W - moon.width) // 2, 170))
    d.text((W / 2, 720), "Good night", font=font("bold", 84), fill=BLACK, anchor="ms")
    d.text((W / 2, 790), "The dashboard is asleep until 6 AM.", font=font("regular", 40), fill=DARK, anchor="ms")
    day = now.date() if now.hour < 6 else now.date() + timedelta(days=1)
    try:
        daily = wx["daily"]
        i = daily["time"].index(day.isoformat())
        top = 900
        hrule(d, top)
        d.text((MARGIN, top + 76), f"{day:%A}", font=font("semibold", 48), fill=BLACK, anchor="ls")
        code = daily["weather_code"][i]
        art = doodles.weather(doodles.weather_kind(code, True), 230)
        img.paste(art, (MARGIN, top + 120))
        x = MARGIN + 270
        d.text((x, top + 230), f"{deg(daily['temperature_2m_max'][i])}", font=font("bold", 120), fill=BLACK, anchor="ls")
        hx = x + text_w(deg(daily["temperature_2m_max"][i]), font("bold", 120)) + 30
        d.text((hx, top + 230), f"/ {deg(daily['temperature_2m_min'][i])}", font=font("regular", 64), fill=DARK, anchor="ls")
        d.text((x, top + 300), wmo(code)[0], font=font("semibold", 48), fill=BLACK, anchor="ls")
        pp = daily.get("precipitation_probability_max", [None] * (i + 1))[i]
        if pp is not None:
            d.text((x, top + 356), f"{int(pp)}% chance of rain", font=font("regular", 40), fill=DARK, anchor="ls")
        d.text((x, top + 408), f"Sunrise {clock(_local(daily['sunrise'][i]))}", font=font("regular", 40), fill=DARK, anchor="ls")
    except Exception as e:  # noqa: BLE001  (no forecast: the moon alone is fine)
        warn(f"night forecast skipped ({e.__class__.__name__}: {e})")
    return img.point([min(255, int(v / 17 + 0.5) * 17) for v in range(256)])


def parse_now(s: str | None) -> datetime:
    if not s:
        return datetime.now(TZ)
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return dt.replace(tzinfo=TZ) if dt.tzinfo is None else dt.astimezone(TZ)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(ROOT / "out" / "dashboard.png"))
    ap.add_argument("--weather-json", help="use a saved Open-Meteo response instead of the network")
    ap.add_argument("--now", help="override the clock (ISO 8601; naive = America/New_York)")
    ap.add_argument("--todo", default=str(ROOT / "todo.md"))
    ap.add_argument("--coffee", default=str(ROOT / "coffee.md"))
    args = ap.parse_args(argv)

    now = parse_now(args.now)
    wx = load_weather(args.weather_json)
    img = render(now, wx, Path(args.todo), Path(args.coffee))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, format="PNG", optimize=True)
    # Companions the Kindle downloads with the image: render time, stale banner and night screen.
    render_stale(now).save(out.parent / "stale.png", optimize=True)
    render_night(now, wx).save(out.parent / "night.png", optimize=True)
    (out.parent / "meta.json").write_text(json.dumps({"rendered_at": int(now.timestamp()), "label": clock(now)}) + "\n")
    print(f"wrote {out} ({img.size[0]}x{img.size[1]}, mode {img.mode}) + stale.png, night.png, meta.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
