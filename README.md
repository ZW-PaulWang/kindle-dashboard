# Kindle dashboard

An always-on e-ink dashboard for a jailbroken Kindle Paperwhite 5: Boston weather, a to-do list and a coffee bean of the day. Swipe to a second page: today's meal plan, set like a restaurant menu.

## Updating it

Use the web page in `docs/` (see [Web page](#web-page)), or edit these files on GitHub (the web editor is fine, and you can tick to-do boxes there):

- `todo.md`: `- [ ] item` for open items, `- [x] item` for done ones.
- `coffee.md`: saved beans, one `## Bean name` per bean, then `- Key: value` lines (Grams, Grind, Roast, Ratio, Time). The `- Coffee: name` and `- Decaf: name` lines at the top choose the beans the dashboard shows. Leave `Decaf:` empty to show one bean only. If `Coffee:` is empty, the dashboard rotates through the saved beans daily.
- `menu.md`: today's meal plan for the second page (see [Today's menu](#todays-menu)).

Each edit triggers a new render. The Kindle downloads the latest image at 5 minutes past every hour.

## Web page

`docs/index.html` is a single page that edits `todo.md`, `coffee.md` and `menu.md` through the GitHub API. Type a saved bean's name in the Coffee or Decaf box to show it on the dashboard; save the settings of a new bean once and they come back when you type its name again. The page also shows the current dashboard and menu images (tap Dashboard / Menu, or swipe the preview).

1. Make a fine-grained token at GitHub → Settings → Developer settings → Personal access tokens: this repository only, **Contents: Read and write**. (The Kindle's token is read-only, so it does not work here.)
2. Open the page and paste the token. The page keeps it in that browser's local storage only.

To host the page: Settings → Pages → Build and deployment → Deploy from a branch → `main`, folder `/docs`. The page is at `https://OWNER.github.io/kindle-dashboard/`. It contains no data and no token, so a public address is safe. For a private repository, GitHub Pages needs a paid plan (GitHub Pro, free with GitHub Education). Without Pages, download `docs/index.html` and open it in a browser; it works the same.

## Today's menu

The Kindle's second page shows the day's breakfast, lunch and dinner as a fine-dining menu card. On the web page, type one dish per line in the Breakfast, Lunch and Dinner boxes, with any details after a colon (`Salmon: miso glaze, rice`), and save. The new menu appears on the Kindle at its next download. Each save stamps today's date. If the menu was planned on an earlier day, the page says so.

`menu.md` can also be edited by hand:

```md
# Today's Menu
Date: 2026-11-02

## Breakfast
- Greek yogurt: honey, walnuts
- flat white

## Lunch
- chicken caesar salad

## Dinner
- Salmon: miso glaze, rice, broccoli
```

The title line and `Date:` are optional. Only `- ` (or `* `, `+ `, `1.`) lines under `## Breakfast`, `## Lunch` and `## Dinner` count as dishes, and a meal can be empty.

The renderer (`render/menu.py`) tidies each dish without an LLM and never adds a word:
- It collapses spaces and strips stray bullets, numbering and `**bold**` marks.
- It sets dish names in title case, with small words such as "and", "with", "of" and "au" in lowercase. Words you typed with capitals or digits stay as typed ("BBQ", "2 eggs").
- It keeps details in the case you typed, joins them with commas and drops trailing punctuation.
- It turns `w/` into "with" and `&` between words into "and". `w/o` stays as typed.
- With no colon, the part after the first " with " becomes the details: "salmon with rice" becomes "Salmon", "rice".
- Chinese punctuation (`：`, `，`) works like `:` and `,`.

To check the tidying locally, run `python render/menu.py --selftest`.

## How it works

1. `.github/workflows/render.yml` runs `render/render.py` when the Kindle asks for it (just before each hourly download), on every push, and every 3 hours as a backup. It fetches the weather from [Open-Meteo](https://open-meteo.com/) and draws a 1236×1648 grayscale PNG, plus `meta.json` (render time), `stale.png` (the "Last updated" banner) and `night.png` (the midnight-to-6 AM screen) and `menu.png` (page 2, the menu). If the menu fails to render, the dashboard is still published.
2. These files are force-pushed as a single commit to the `output` branch, so history doesn't grow.
3. On the Kindle, the KUAL extension in `kindle/dashboard/` stops the Kindle UI and downloads and displays the image hourly. It then draws a battery indicator (icon, exact %, charging bolt) in the middle of the footer, because only the Kindle knows the level. The icons are pre-rendered by `render/battery.py` into `kindle/dashboard/battery/`, and the indicator is redrawn every 10 minutes. Swipe left or right to flip between the dashboard and the menu (the dots at the bottom show the page). Single taps do nothing. Swipes are ignored overnight. To get the normal Kindle UI back, double-tap the screen. `bin/gestures.lua` reads the touchscreen using KOReader's LuaJIT. In an emergency, hold the power button ~15 s to restart.

## Render locally

```sh
pip install pillow
python render/render.py --out out/dashboard.png                                         # live weather
python render/render.py --out out/dashboard.png --weather-json render/sample_weather.json  # offline
```

## Kindle setup

1. Copy `kindle/dashboard/` to `extensions/dashboard/` on the Kindle.
2. Copy `config.example.sh` to `config.sh` and set `REPO` and `GITHUB_TOKEN`. Use a fine-grained token for this repo only, with **Contents: Read-only** and **Actions: Read and write** (the Kindle asks GitHub for fresh renders and sends its log that way).
3. In KUAL, run **Dashboard → Test download**, then **Start dashboard**. Logs are written to `extensions/dashboard/dashboard.log`.

That is the only time the Kindle needs a USB cable.

## Over-the-air updates

Every render also publishes `kindle.tar` (the `kindle/dashboard/` folder) and `kindle.version` (the git tree hash of that folder) to the `output` branch. A push that changes `kindle/dashboard/` triggers a render, so a new version is published within a minute or two.

At each refresh the Kindle (`bin/update.sh`) compares `kindle.version` with its `VERSION` file. When they differ, it:

1. downloads and unpacks the bundle in `/tmp`;
2. refuses it if a required file is missing, a script has a shell syntax error, `gestures.lua` doesn't load, or the version doesn't match;
3. copies each changed file over the old one, keeping the old copies in `.backup/`, and moves away scripts in `bin/` that the new version no longer has;
4. restarts the dashboard with the new scripts. The Kindle UI stays off and the screen keeps its image.

A watchdog started from the old scripts checks that the new `dash.sh` starts within 150 seconds. If it doesn't, the watchdog stops it, puts the backup back and starts the old version again. The failed version is recorded in `.update-bad` and skipped until a newer one is published. **Start dashboard** in KUAL also installs a published update before starting, so a dashboard that broke after an update can be fixed by pushing a fix and tapping Start.

Updates never touch `config.sh`, the log or the downloaded images. Set `UPDATES=0` in `config.sh` to turn them off on one Kindle.

## Settings

`kindle/dashboard/settings.sh` holds the refresh minute, night hours, commute window and the update and log switches. It reaches the Kindle with each update, so change it on GitHub. `config.sh` on the Kindle holds only the repo and token. It is read after `settings.sh`, so a setting added there overrides the repo's value on that Kindle.

## Remote logs

With each render request the Kindle sends the new lines of `dashboard.log` (at most the newest 30 KB) and a status line (version, battery, page, uptime, free space, Wi-Fi). The render workflow appends them to the `logs` branch before it renders, so this costs no extra Actions run:

- `kindle.log`: the last 5000 lines.
- `status.txt`: the latest status line, with the time it arrived.

The log arrives with the next refresh, so it is up to an hour behind (10 minutes on weekday mornings). Read it with `gh api "repos/OWNER/kindle-dashboard/contents/kindle.log?ref=logs" -H "Accept: application/vnd.github.raw"`, or on GitHub by switching to the `logs` branch. Once the log on the Kindle passes 400 KB after an upload, it is trimmed to its last 1500 lines. Set `LOG_UPLOAD=0` to stop sending it.

## Adding to-dos from an iPhone

`.github/workflows/add-todo.yml` appends a to-do and re-renders. An iPhone Shortcut runs it with one request:

- `POST https://api.github.com/repos/ZW-PaulWang/kindle-dashboard/actions/workflows/add-todo.yml/dispatches`
- Headers: `Authorization: Bearer <token>`, `Accept: application/vnd.github+json`
- JSON body: `{"ref": "main", "inputs": {"item": "<the to-do>"}}`

The token needs **Actions: Read and write** on this repository.

## Night sleep

From midnight to 6 AM the Kindle shows `night.png`, turns Wi-Fi off and idles until morning, then starts again on the dashboard page. `NIGHT_SUSPEND=1` also tries a real deep sleep; it saved no battery and may have caused a crash, so it is off. Change the hours with `NIGHT_START` and `NIGHT_END` in `settings.sh`.

## Morning bus times

On weekday mornings (6–11 AM) a band under the weather shows the next three Harvard-bound **66** buses from Cambridge St opp Hano St, with arrival times at N Harvard St by HBS, from the [MBTA's public API](https://www.mbta.com/developers/v3-api). Live predictions get a small signal icon; scheduled-only times are gray. From 7 to 10 AM the Kindle refreshes every 10 minutes instead of hourly. The stops, route and hours are in `COMMUTE` at the top of the commute section of `render/render.py`; the Kindle's refresh window is in `settings.sh` (`COMMUTE_START`, `COMMUTE_END`, `COMMUTE_EVERY`, `COMMUTE_LAST_DAY`).

