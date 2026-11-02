#!/bin/sh
# Shared helpers for the dashboard scripts.
# DASH_ROOT is only for desktop simulations (a fake /mnt/us, /tmp, /sys, /dev); unset on the Kindle.
R="${DASH_ROOT:-}"
T="$R/tmp"
DIR="$R/mnt/us/extensions/dashboard"
IMG="$DIR/dashboard.png"       # page 1
MENU_IMG="$DIR/menu.png"       # page 2: today's menu (optional; older renders don't publish it)
PIDFILE="$T/dashboard.pid"     # tmpfs: a reboot clears it, so a crash never leaves a stale one

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*"; }

load_config() {
    if [ ! -f "$DIR/config.sh" ]; then
        log "ERROR: $DIR/config.sh is missing (copy config.example.sh and fill it in)"
        return 1
    fi
    . "$DIR/config.sh"
    BRANCH="${BRANCH:-output}"
    REFRESH_MINUTE="${REFRESH_MINUTE:-5}"
    NIGHT_START="${NIGHT_START:-0}"      # the dashboard sleeps from NIGHT_START:00 ...
    NIGHT_END="${NIGHT_END:-6}"          # ... to NIGHT_END:00 (local time)
    NIGHT_SUSPEND="${NIGHT_SUSPEND:-0}"  # 0: idle with Wi-Fi off at night (default); 1: also try a real deep sleep
    COMMUTE_START="${COMMUTE_START:-7}"      # weekday mornings from COMMUTE_START:00 ...
    COMMUTE_END="${COMMUTE_END:-10}"         # ... to COMMUTE_END:00, refresh every COMMUTE_EVERY minutes
    COMMUTE_EVERY="${COMMUTE_EVERY:-10}"
    COMMUTE_LAST_DAY="${COMMUTE_LAST_DAY:-5}"  # 5 = Monday to Friday, 7 = every day
    if [ -z "$REPO" ] || [ -z "$GITHUB_TOKEN" ]; then
        log "ERROR: REPO and GITHUB_TOKEN must be set in config.sh"
        return 1
    fi
}

find_fbink() {
    for f in "$R/mnt/us/libkh/bin/fbink" "$R/mnt/us/koreader/fbink" "$R/usr/bin/fbink"; do
        [ -x "$f" ] && { echo "$f"; return 0; }
    done
    return 1
}

API="https://api.github.com/repos"

# Download one published file from the output branch: gh_get <name> <dest>
gh_get() {
    url="$API/$REPO/contents/$1?ref=$BRANCH"
    if command -v curl >/dev/null 2>&1; then
        curl -fsS --max-time 60 --retry 2 --retry-delay 5 \
            -H "Authorization: Bearer $GITHUB_TOKEN" \
            -H "Accept: application/vnd.github.raw" \
            -H "X-GitHub-Api-Version: 2022-11-28" \
            -o "$2" "$url"
    else
        wget -q -T 60 -O "$2" \
            --header "Authorization: Bearer $GITHUB_TOKEN" \
            --header "Accept: application/vnd.github.raw" \
            "$url"
    fi
}

is_png() { [ "$(dd if="$1" bs=1 skip=1 count=3 2>/dev/null)" = "PNG" ]; }

# Render time (epoch seconds) recorded in a meta.json, default the current one.
meta_epoch() { sed -n 's/.*"rendered_at": *\([0-9][0-9]*\).*/\1/p' "${1:-$DIR/meta.json}" 2>/dev/null; }

# Download the image and its companions (render time, stale banner, night screen, menu page).
# The current set is only replaced when the new image is a valid PNG; a companion that is
# missing or not a PNG keeps its previous copy.
fetch_image() {
    rm -f "$T"/dash.*.part
    if ! gh_get dashboard.png "$T"/dash.png.part; then
        log "ERROR: download failed"
        return 1
    fi
    if ! is_png "$T"/dash.png.part; then
        log "ERROR: download is not a PNG: $(head -c 200 "$T"/dash.png.part)"
        return 1
    fi
    gh_get meta.json "$T"/dash.meta.part 2>/dev/null || rm -f "$T"/dash.meta.part
    for f in stale offline night menu; do
        gh_get "$f.png" "$T/dash.$f.part" 2>/dev/null && is_png "$T/dash.$f.part" || rm -f "$T/dash.$f.part"
    done
    if [ ! -f "$T"/dash.menu.part ]; then
        if [ -f "$MENU_IMG" ]; then log "Couldn't download menu.png; keeping the previous menu"; else log "No menu.png published yet"; fi
    fi
    cat "$T"/dash.png.part >"$IMG"
    [ -f "$T"/dash.meta.part ] && cat "$T"/dash.meta.part >"$DIR/meta.json"
    [ -f "$T"/dash.stale.part ] && cat "$T"/dash.stale.part >"$DIR/stale.png"
    [ -f "$T"/dash.offline.part ] && cat "$T"/dash.offline.part >"$DIR/offline.png"
    [ -f "$T"/dash.night.part ] && cat "$T"/dash.night.part >"$DIR/night.png"
    [ -f "$T"/dash.menu.part ] && cat "$T"/dash.menu.part >"$MENU_IMG"
    rm -f "$T"/dash.*.part
    log "Downloaded $(wc -c <"$IMG") bytes (rendered $(sed -n 's/.*"label": *"\([^"]*\)".*/\1/p' "$DIR/meta.json" 2>/dev/null))"
}

# Ask GitHub to render right now. Needs "Actions: Read and write" on the token.
trigger_render() {
    body='{"ref":"main"}'
    url="$API/$REPO/actions/workflows/render.yml/dispatches"
    if command -v curl >/dev/null 2>&1; then
        code="$(curl -s -o "$T"/dash.dispatch -w '%{http_code}' --max-time 30 -X POST \
            -H "Authorization: Bearer $GITHUB_TOKEN" \
            -H "Accept: application/vnd.github+json" \
            -H "X-GitHub-Api-Version: 2022-11-28" \
            -d "$body" "$url")"
    else
        wget -q -T 30 -O "$T"/dash.dispatch --post-data "$body" \
            --header "Authorization: Bearer $GITHUB_TOKEN" \
            --header "Accept: application/vnd.github+json" "$url" && code=204 || code=error
    fi
    [ "$code" = 204 ] && return 0
    log "Couldn't start a render (HTTP $code): $(head -c 160 "$T"/dash.dispatch 2>/dev/null)"
    [ "$code" = 403 ] && log "  Add 'Actions: Read and write' to the Kindle's GitHub token so it can ask for fresh renders."
    return 1
}

# Wait up to 3 minutes for a render published at or after $1 (epoch seconds).
wait_for_render() {
    i=0
    while [ $i -lt 12 ]; do
        show_status "update_$(( i % 3 + 1 ))"
        nap 15
        if gh_get meta.json "$T"/dash.poll 2>/dev/null && [ "$(meta_epoch "$T"/dash.poll)" -ge "$1" ] 2>/dev/null; then
            return 0
        fi
        i=$((i + 1))
    done
    log "No new render after 3 minutes; using the latest published one"
    return 1
}

# Full-screen refresh with an image: show_image [file], default the dashboard.
show_image() {
    fb="$(find_fbink)"
    if [ -n "$fb" ]; then
        "$fb" -q -c -f -g file="${1:-$IMG}" && return 0
    fi
    eips -c
    eips -f -g "${1:-$IMG}"
}

# Sleep $1 seconds in the background and wait for it, so trapped signals (double tap, swipe)
# are handled straight away. A trapped signal makes 'wait' return early: handle any queued
# swipes, then keep waiting while the sleep is still running, so the pause keeps its length.
SLEEP_PID=""
nap() {
    sleep "$1" &
    SLEEP_PID=$!
    handle_swipes
    while :; do
        wait "$SLEEP_PID" 2>/dev/null
        handle_swipes
        kill -0 "$SLEEP_PID" 2>/dev/null || break
    done
    SLEEP_PID=""
}
handle_swipes() { :; }   # dash.sh replaces this; other scripts have no pages

# Print a one-line message along the bottom of the screen.
show_message() {
    fb="$(find_fbink)"
    if [ -n "$fb" ]; then
        "$fb" -q -m -y -2 "$*"
    else
        eips 1 38 "$*"
    fi
}

# Clear the screen and show a centred two-line notice.
show_notice() {
    fb="$(find_fbink)"
    if [ -n "$fb" ]; then
        "$fb" -q -c -f -m -M -S 3 "$1" && "$fb" -q -m -M -y 3 "$2"
    else
        eips -c
        eips 10 18 "$1"
        eips 4 21 "$2"
    fi
}

# Footer battery indicator: pre-rendered images (render/battery.py) drawn into a fixed slot.
BATTERY_X=508
BATTERY_Y=1556

battery_level() {
    for f in "$R"/sys/class/power_supply/bd71827_bat/capacity "$R"/sys/class/power_supply/*/capacity; do
        [ -r "$f" ] && { cat "$f"; return; }
    done
    b="$(lipc-get-prop com.lab126.powerd battLevel 2>/dev/null | tr -dc '0-9')"
    [ -n "$b" ] && { echo "$b"; return; }
    gasgauge-info -c 2>/dev/null | tr -dc '0-9'
}

battery_charging() {
    for d in "$R"/sys/class/power_supply/bd71827_bat "$R"/sys/class/power_supply/*; do
        [ -r "$d/status" ] || continue
        case "$(cat "$d/status")" in Charging|Full) return 0 ;; *) return 1 ;; esac
    done
    return 1
}

show_battery() {
    lvl="$(battery_level)"
    case "$lvl" in ''|*[!0-9]*) return ;; esac
    [ "$lvl" -gt 100 ] && lvl=100
    img="$(printf '%s/battery/bat_%03d' "$DIR" "$lvl")"
    battery_charging && img="${img}_c"
    img="$img.png"
    [ -f "$img" ] || return
    draw_overlay "$img" $BATTERY_X $BATTERY_Y
}

# Draw a small image at x,y without clearing the rest of the screen.
draw_overlay() {
    fb="$(find_fbink)"
    if [ -n "$fb" ]; then
        "$fb" -q -g file="$1",x="$2",y="$3"
    else
        eips -g "$1" -x "$2" -y "$3"
    fi
}

# Status pills (render/status.py) in the same footer slot as "Updated ...", so a busy
# dashboard never looks frozen: show_status wifi_1..3 | update_1..3.
show_status() {
    LAST_STATUS="$1"   # so a page flipped mid-refresh can redraw the same pill
    [ -f "$DIR/status/$1.png" ] && draw_overlay "$DIR/status/$1.png" $STALE_X $STALE_Y
}

# Black "Offline. Updated 7:05 AM" pill (render/render.py) after a refresh that couldn't download.
show_offline() {
    if [ -f "$DIR/offline.png" ]; then draw_overlay "$DIR/offline.png" $STALE_X $STALE_Y; else show_stale_if_old; fi
}

# "Last updated ..." banner (render/render.py render_stale) over the footer's right side,
# shown when the image on screen is more than 3 hours old.
STALE_X=752
STALE_Y=1556
STALE_AFTER=10800
show_stale_if_old() {
    r="$(meta_epoch)"
    [ -n "$r" ] && [ -f "$DIR/stale.png" ] || return 0
    age=$(( $(date +%s) - r ))
    [ "$age" -gt "$STALE_AFTER" ] || return 0
    log "Image is $((age / 60)) minutes old; showing the stale banner"
    draw_overlay "$DIR/stale.png" $STALE_X $STALE_Y
}

# Black-then-white flash that clears e-ink ghosting; run once a day when the dashboard wakes.
deep_clean() {
    fb="$(find_fbink)"
    if [ -n "$fb" ]; then
        "$fb" -q -k -f -h
        sleep 1
        "$fb" -q -k -f
    else
        eips -c
        sleep 1
        eips -c
    fi
}
