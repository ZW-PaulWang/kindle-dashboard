# Kindle dashboard

An always-on e-ink dashboard for a jailbroken Kindle Paperwhite 5: Boston weather, a to-do list and a coffee recipe of the day.

## Updating it

Edit these files on GitHub (the web editor is fine, and you can tick to-do boxes there):

- `todo.md`: `- [ ] item` for open items, `- [x] item` for done ones.
- `coffee.md`: one `## Recipe name` per recipe, then `- Key: value` lines, then numbered steps. The featured recipe rotates daily.

Each edit triggers a new render. The Kindle downloads the latest image at 5 minutes past every hour.

## How it works

1. `.github/workflows/render.yml` runs `render/render.py` hourly (at :45) and on every push. It fetches the weather from [Open-Meteo](https://open-meteo.com/) and draws a 1236×1648 grayscale PNG.
2. The image is force-pushed as a single commit to the `output` branch, so history doesn't grow.
3. On the Kindle, the KUAL extension in `kindle/dashboard/` stops the Kindle UI and downloads and displays the image hourly. To get the normal Kindle UI back, press the power button.

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
