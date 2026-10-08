# Kindle dashboard

An always-on e-ink dashboard for a jailbroken Kindle Paperwhite 5: Boston weather, a to-do list and a coffee bean of the day.

## Updating it

Use the web page in `docs/` (see [Web page](#web-page)), or edit these files on GitHub (the web editor is fine, and you can tick to-do boxes there):

- `todo.md`: `- [ ] item` for open items, `- [x] item` for done ones.
- `coffee.md`: saved beans, one `## Bean name` per bean, then `- Key: value` lines (Grams, Grind, Roast, Ratio, Time). The `- Coffee: name` and `- Decaf: name` lines at the top choose the beans the dashboard shows. Leave `Decaf:` empty to show one bean only. If `Coffee:` is empty, the dashboard rotates through the saved beans daily.

Each edit triggers a new render. The Kindle downloads the latest image at 5 minutes past every hour.

## Web page

`docs/index.html` is a single page that edits `todo.md` and `coffee.md` through the GitHub API. Type a saved bean's name in the Coffee or Decaf box to show it on the dashboard; save the settings of a new bean once and they come back when you type its name again. The page also shows the current dashboard image.

1. Make a fine-grained token at GitHub → Settings → Developer settings → Personal access tokens: this repository only, **Contents: Read and write**. (The Kindle's token is read-only, so it does not work here.)
2. Open the page and paste the token. The page keeps it in that browser's local storage only.

To host the page: Settings → Pages → Build and deployment → Deploy from a branch → `main`, folder `/docs`. The page is at `https://OWNER.github.io/kindle-dashboard/`. It contains no data and no token, so a public address is safe. For a private repository, GitHub Pages needs a paid plan (GitHub Pro, free with GitHub Education). Without Pages, download `docs/index.html` and open it in a browser; it works the same.

## How it works

1. `.github/workflows/render.yml` runs `render/render.py` when the Kindle asks for it (just before each hourly download), on every push, and every 3 hours as a backup. It fetches the weather from [Open-Meteo](https://open-meteo.com/) and draws a 1236×1648 grayscale PNG, plus `meta.json` (render time), `stale.png` (the "Last updated" banner) and `night.png` (the midnight-to-6 AM screen).
2. These files are force-pushed as a single commit to the `output` branch, so history doesn't grow.
3. On the Kindle, the KUAL extension in `kindle/dashboard/` stops the Kindle UI and downloads and displays the image hourly. It then draws a battery indicator (icon, exact %, charging bolt) in the middle of the footer, because only the Kindle knows the level. The icons are pre-rendered by `render/battery.py` into `kindle/dashboard/battery/`, and the indicator is redrawn every 10 minutes. To get the normal Kindle UI back, double-tap the screen (uses KOReader's LuaJIT). In an emergency, hold the power button ~15 s to restart.

## Render locally

```sh
pip install pillow
python render/render.py --out out/dashboard.png                                         # live weather
python render/render.py --out out/dashboard.png --weather-json render/sample_weather.json  # offline
```

## Kindle setup

1. Copy `kindle/dashboard/` to `extensions/dashboard/` on the Kindle.
2. Copy `config.example.sh` to `config.sh` and set `REPO` and `GITHUB_TOKEN`. Use a fine-grained token for this repo only, with Contents set to read-only.
3. In KUAL, run **Dashboard → Test download**, then **Start dashboard**. Logs are written to `extensions/dashboard/dashboard.log`.

Changes to `kindle/dashboard/` (for example the battery level) reach the Kindle only when you copy the folder again over USB. Keep your `config.sh`. The image itself always comes from GitHub.

## Adding to-dos from an iPhone

`.github/workflows/add-todo.yml` appends a to-do and re-renders. An iPhone Shortcut runs it with one request:

- `POST https://api.github.com/repos/ZW-PaulWang/kindle-dashboard/actions/workflows/add-todo.yml/dispatches`
- Headers: `Authorization: Bearer <token>`, `Accept: application/vnd.github+json`
- JSON body: `{"ref": "main", "inputs": {"item": "<the to-do>"}}`

The token needs **Actions: Read and write** on this repository.

## Night sleep

From midnight to 6 AM the Kindle shows `night.png`, turns Wi-Fi off and tries to suspend until morning (set `NIGHT_SUSPEND=0` in `config.sh` to only idle). Change the hours with `NIGHT_START` and `NIGHT_END`.

## Morning bus times

On weekday mornings (6–11 AM) a band under the weather shows the next three Harvard-bound **66** buses from Cambridge St opp Hano St, with arrival times at N Harvard St by HBS, from the [MBTA's public API](https://www.mbta.com/developers/v3-api). Live predictions get a small signal icon; scheduled-only times are gray. From 7 to 10 AM the Kindle refreshes every 10 minutes instead of hourly. The stops, route and hours are in `COMMUTE` at the top of the commute section of `render/render.py`; the Kindle's refresh window is in `config.sh` (`COMMUTE_START`, `COMMUTE_END`, `COMMUTE_EVERY`, `COMMUTE_LAST_DAY`).

