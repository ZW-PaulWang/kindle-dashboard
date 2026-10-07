#!/usr/bin/env python3
"""Render the Kindle e-ink dashboard (weather, to-do, coffee of the day) to a PNG.

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
import urllib.request
from datetime import datetime
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
CITY = "Boston"

WEATHER_URL = (
    "https://api.open-meteo.com/v1/forecast?latitude=42.3601&longitude=-71.0589"
    "&timezone=America%2FNew_York&temperature_unit=fahrenheit&wind_speed_unit=mph"
    "&precipitation_unit=inch"
    "&current=temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,"
    "wind_speed_10m,is_day"
    "&hourly=temperature_2m,precipitation_probability,weather_code"
    "&daily=weather_code,temperature_2m_max,temperature_2m_min,"
    "precipitation_probability_max,sunrise,sunset&forecast_days=4"
)

W, H = 1236, 1648
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


def section_label(d, x, y, label: str, right: str | None = None, x1: float | None = None):
    """Small tracked uppercase section label (baseline at y)."""
    f = font("semibold", 30)
    cx = x
    for ch in label.upper():
        d.text((cx, y), ch, font=f, fill=DARK, anchor="ls")
        cx += text_w(ch, f) + 3
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


def load_beans(path: Path) -> list[dict]:
    beans: list[dict] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception as e:  # noqa: BLE001
        warn(f"could not read {path}: {e}")
        return beans
    cur = None
    for line in lines:
        if line.startswith("## "):
            cur = {"name": clean_md(line[3:]), "meta": []}
            beans.append(cur)
            continue
        if line.startswith("#"):
            cur = None if not line.startswith("###") else cur
            continue
        if cur is None:
            continue
        m = META_RE.match(line)
        if m:
            cur["meta"].append((clean_md(m.group(1)), clean_md(m.group(2))))
    return [b for b in beans if b["name"]]


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
    size = 250
    while size > 120 and text_w(temp, font("medium", size)) > right_x - 48 - temp_x:
        size -= 10
    tf = font("medium", size)
    # Optically centre the digits' cap height on the hero centre line.
    _, t, _, b = tf.getbbox("0", anchor="ls")
    d.text((temp_x, cy - (t + b) / 2), temp, font=tf, fill=BLACK, anchor="ls")

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

    # ---- Stat row ----
    y0 = hero_top + hero_h + 12
    stats = []
    pp = daily.get("precipitation_probability_max", [None] * (di + 1))[di]
    stats.append(("umbrella", f"{int(pp) if pp is not None else 0}%", "Rain"))
    stats.append(("strong-wind", f"{int(round(cur.get('wind_speed_10m', 0)))} mph", "Wind"))
    stats.append(("sunrise", clock(_local(daily["sunrise"][di])), "Sunrise"))
    stats.append(("sunset", clock(_local(daily["sunset"][di])), "Sunset"))
    cell = CONTENT_W / len(stats)
    for i, (ic, val, label) in enumerate(stats):
        x = MARGIN + i * cell
        draw_icon(d, ic, x + 30, y0 + 40, 52)
        d.text((x + 76, y0 + 40), val, font=font("bold", 40), fill=BLACK, anchor="ls")
        d.text((x + 76, y0 + 78), label, font=font("regular", 30), fill=DARK, anchor="ls")
    y = y0 + 104
    hrule(d, y)

    # ---- Hourly strip: next ~12 hours, every 2 hours ----
    times = [_local(t) for t in hourly["time"]]
    start = next((i for i, t in enumerate(times) if t > now_naive), len(times))
    idxs = [i for i in range(start, len(times), 2)][:6]
    probs = hourly.get("precipitation_probability") or [None] * len(times)
    any_rain = any(probs[i] is not None and probs[i] >= 10 for i in idxs)
    y_h = y + (23 if any_rain else 41)
    if idxs:
        colw = CONTENT_W / len(idxs)
        sun = {}
        for k, t in enumerate(daily["time"]):
            sun[t] = (_local(daily["sunrise"][k]), _local(daily["sunset"][k]))
        for n, i in enumerate(idxs):
            cx = MARGIN + colw * (n + 0.5)
            t = times[i]
            sr, ss = sun.get(t.date().isoformat(), (None, None))
            day = (sr <= t < ss) if sr and ss else (6 <= t.hour < 19)
            _, ic = wmo(hourly["weather_code"][i], day)
            d.text((cx, y_h + 26), hour_label(t), font=font("regular", 32), fill=DARK, anchor="ms")
            draw_icon(d, ic, cx, y_h + 70, 60)
            d.text((cx, y_h + 142), deg(hourly["temperature_2m"][i]), font=font("bold", 44), fill=BLACK, anchor="ms")
            p = probs[i]
            if p is not None and p >= 10:
                pf = font("regular", 30)
                pw = text_w(f"{int(p)}%", pf) + 24
                draw_icon(d, "raindrop", cx - pw / 2 + 8, y_h + 168, 22, fill=DARK)
                d.text((cx - pw / 2 + 24, y_h + 178), f"{int(p)}%", font=pf, fill=DARK, anchor="ls")
    y = y + 222
    hrule(d, y)

    # ---- Next 3 days ----
    y_d = y + 24
    days = [k for k in range(di + 1, min(di + 4, len(daily["time"])))]
    if not days:
        return
    probs_d = daily.get("precipitation_probability_max") or [None] * len(daily["time"])
    nf, hf, lf, pf = font("semibold", 38), font("bold", 40), font("regular", 40), font("regular", 32)
    icon_w, gap = 76, 18
    cards = []
    for k in days:
        dt = _local(daily["time"][k])
        p = probs_d[k]
        cards.append(dict(
            dt=dt, icon=wmo(daily["weather_code"][k], True)[1],
            hi=deg(daily["temperature_2m_max"][k]), lo=deg(daily["temperature_2m_min"][k]),
            rain=f"{int(p)}%" if p is not None and p >= 10 else ""))

    def line2_w(c, rain_inline):
        w = text_w(c["hi"], hf) + 14 + text_w(c["lo"], lf)
        return w + (22 + 28 + text_w(c["rain"], pf) if c["rain"] and rain_inline else 0)

    def card_w(c, fmt, rain_on_2):
        line1 = text_w(c["dt"].strftime(fmt), nf)
        if c["rain"] and not rain_on_2:
            line1 += 18 + 28 + text_w(c["rain"], pf)
        return icon_w + gap + max(line1, line2_w(c, rain_on_2))

    # Variants from roomiest to most compact; first whose cards fit with >=40px gaps wins.
    for fmt, rain_on_2 in (("%A", True), ("%a", True), ("%a", False)):
        widths = [card_w(c, fmt, rain_on_2) for c in cards]
        if sum(widths) + 40 * (len(cards) - 1) <= CONTENT_W:
            break
    # Justify: first card flush left, last flush right, equal gaps between.
    spacing = (CONTENT_W - sum(widths)) / (len(cards) - 1) if len(cards) > 1 else 0
    x = MARGIN
    for c, cw in zip(cards, widths):
        draw_icon(d, c["icon"], x + icon_w / 2, y_d + 50, 76)
        tx = x + icon_w + gap
        name = c["dt"].strftime(fmt)
        d.text((tx, y_d + 36), name, font=nf, fill=BLACK, anchor="ls")
        d.text((tx, y_d + 86), c["hi"], font=hf, fill=BLACK, anchor="ls")
        hx = tx + text_w(c["hi"], hf) + 14
        d.text((hx, y_d + 86), c["lo"], font=lf, fill=DARK, anchor="ls")
        if c["rain"]:
            if rain_on_2:
                rx, ry = hx + text_w(c["lo"], lf) + 22, y_d + 86
            else:
                rx, ry = tx + text_w(name, nf) + 18, y_d + 36
            draw_icon(d, "raindrop", rx + 9, ry - 13, 22, fill=DARK)
            d.text((rx + 28, ry), c["rain"], font=pf, fill=DARK, anchor="ls")
        x += cw + spacing


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
    f = font("regular", 38)
    lh = 50
    box = 30
    tx = x0 + box + 22
    tw = x1 - tx

    if not open_items and not done_items:
        d.text((x0, y + 38), "Nothing on the list.", font=font("italic", 38), fill=DARK, anchor="ls")
        return

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
        lines = wrap(item, f, tw, max_lines=min(2, fit))
        need = len(lines) * lh
        draw_checkbox(d, x0, y + 10, box, False)
        for k, ln in enumerate(lines):
            d.text((tx, y + 38 + k * lh), ln, font=f, fill=BLACK, anchor="ls")
        y += need + 16
        shown += 1

    hidden_open = len(open_items) - shown
    if hidden_open:
        d.text((tx, y + 34), f"+{hidden_open} more", font=font("bold", 34), fill=DARK, anchor="ls")
        return

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


# --------------------------------------------------------------------------
# Coffee section
# --------------------------------------------------------------------------
def draw_coffee(img, d, x0, x1, top, bottom, beans, now):
    section_label(d, x0, top + 30, "Coffee of the day")
    if not beans:
        d.text((x0, top + 114), "No beans yet.", font=font("italic", 38), fill=DARK, anchor="ls")
        d.text((x0, top + 164), "Add one to coffee.md", font=font("regular", 32), fill=DARK, anchor="ls")
        return
    b = beans[now.timetuple().tm_yday % len(beans)]
    width = x1 - x0
    y = top + 76

    # Cartoon cup in the bottom-right corner; rows beside it wrap short of it.
    mascot = doodles.coffee_cup(170)
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
        return
    layouts = [dict(vsize=46, row_gap=26, max_lines=2), dict(vsize=42, row_gap=14, max_lines=2),
               dict(vsize=40, row_gap=10, max_lines=1)]
    for n, cfg in enumerate(layouts):
        if _bean_rows(None, b["meta"], x0, width, y, bottom, mx, my, **cfg) or n == len(layouts) - 1:
            _bean_rows(d, b["meta"], x0, width, y, bottom, mx, my, **cfg)
            return


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
    weather_top, weather_bottom = 158, 876
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
        draw_todo(d, lx0, lx1, low_top, low_bottom, open_items, done_items)
        board = doodles.clipboard(175)
        bx, by = int(lx0), int(low_bottom - board.height)
        if img.crop((bx, by - 16, bx + board.width, by + board.height)).getextrema() == (WHITE, WHITE):
            img.paste(board, (bx, by))
    except Exception as e:  # noqa: BLE001  never let one section kill the image
        warn(f"to-do section failed ({e.__class__.__name__}: {e})")
    try:
        draw_coffee(img, d, rx0, rx1, low_top, low_bottom, load_beans(coffee_path), now)
    except Exception as e:  # noqa: BLE001
        warn(f"coffee section failed ({e.__class__.__name__}: {e})")

    # Footer
    hrule(d, footer_rule)
    ff = font("regular", 30)
    d.text((MARGIN, H - 56), "Weather: Open-Meteo.com", font=ff, fill=DARK, anchor="ls")
    d.text((W - MARGIN, H - 56), f"Updated {clock(now)}", font=ff, fill=DARK, anchor="rs")

    # Quantize to the panel's 16 gray levels (multiples of 17).
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
    print(f"wrote {out} ({img.size[0]}x{img.size[1]}, mode {img.mode})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
