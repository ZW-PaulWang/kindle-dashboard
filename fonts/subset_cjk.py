"""Rebuild fonts/NotoSerifSC-SemiBold-subset.ttf (the menu page's Chinese fallback).

Not run by the renderer; needs fontTools (pip install fonttools) on your own machine.

    curl -L -o NotoSerifSC.ttf "https://github.com/google/fonts/raw/main/ofl/notoserifsc/NotoSerifSC%5Bwght%5D.ttf"
    python fonts/subset_cjk.py NotoSerifSC.ttf fonts/NotoSerifSC-SemiBold-subset.ttf 600

Keeps every character of GB2312 (simplified, 6,763 hanzi) and Big5 level 1 (traditional,
5,401 common hanzi), CJK punctuation and fullwidth forms, at one static weight. Rarer
characters fall outside the subset and show as boxes; widen the ranges below to add them.
"""
import sys

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

src, out, wght = sys.argv[1], sys.argv[2], float(sys.argv[3])
chars = set()


def add_codec(codec, lead, trail):
    for a in lead:
        for b in trail:
            try:
                chars.update(bytes([a, b]).decode(codec))
            except UnicodeDecodeError:
                pass


add_codec("gb2312", range(0xA1, 0xF8), range(0xA1, 0xFF))
add_codec("big5", range(0xA4, 0xC7), list(range(0x40, 0x7F)) + list(range(0xA1, 0xFF)))  # level 1
chars.update(map(chr, range(0x3000, 0x3040)))   # CJK symbols and punctuation
chars.update(map(chr, range(0xFF00, 0xFFF0)))   # fullwidth forms
chars.update(map(chr, range(0x2010, 0x2030)))   # dashes, quotes, ellipsis
chars.update(map(chr, range(0x20, 0x7F)))
f = TTFont(src)
cmap = f.getBestCmap()
keep = sorted(ord(c) for c in chars if ord(c) in cmap)
print("chars kept", len(keep), "not in the font", sum(1 for c in chars if ord(c) not in cmap))
f = instancer.instantiateVariableFont(f, {"wght": wght})
opts = subset.Options()
opts.layout_features = ["*"]
opts.name_IDs = ["*"]
opts.notdef_outline = True
opts.hinting = False
ss = subset.Subsetter(opts)
ss.populate(unicodes=keep)
ss.subset(f)
f.save(out)
