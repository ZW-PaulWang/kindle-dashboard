# Fonts

| File | Family | License | Source |
|---|---|---|---|
| IBMPlexSans-{Regular,Medium,SemiBold,Bold,Italic}.ttf | IBM Plex Sans (IBM Corp.) | SIL OFL 1.1 — `OFL-IBMPlexSans.txt` | https://github.com/IBM/plex (packages/plex-sans/fonts/complete/ttf) |
| weathericons-regular.ttf | Weather Icons (Erik Flowers) | SIL OFL 1.1 — `OFL-WeatherIcons.txt` | https://github.com/erikflowers/weather-icons (font/weathericons-regular-webfont.ttf) |
| EBGaramond-VF.ttf, EBGaramond-Italic-VF.ttf | EB Garamond (Georg Duffner, Octavio Pardo), variable weight 400–800 | SIL OFL 1.1 — `OFL-EBGaramond.txt` | https://github.com/google/fonts (ofl/ebgaramond/EBGaramond[wght].ttf, EBGaramond-Italic[wght].ttf), renamed |
| NotoSerifSC-SemiBold-subset.ttf | Noto Serif SC (Google), static weight 600, subset to GB2312 + Big5 level 1 (simplified and common traditional hanzi) | SIL OFL 1.1 — `OFL-NotoSerifSC.txt` | https://github.com/google/fonts (ofl/notoserifsc/NotoSerifSC[wght].ttf), instanced and subset by `subset_cjk.py` |
| NotoEmoji-Medium.ttf | Noto Emoji (Google), monochrome, static weight 500 | SIL OFL 1.1 — `OFL-NotoEmoji.txt` | https://github.com/google/fonts (ofl/notoemoji/NotoEmoji[wght].ttf), instanced |

EB Garamond is used only by the menu page (render/menu.py); weights are picked with `set_variation_by_axes`.

The menu page falls back per character to Noto Serif SC for Chinese dish names and to Noto Emoji for emoji (render/menu.py `Face`). Hanzi outside the subset (rare characters) show as boxes; rebuild it with a wider range using `subset_cjk.py` (needs fontTools, not used by the renderer). If either fallback file is missing, only its characters are affected.
