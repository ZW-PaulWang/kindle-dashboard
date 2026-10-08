#!/bin/sh
# Dashboard loop: stop the Kindle UI, show the dashboard, refresh hourly.
# Double-tap the screen to exit back to the normal Kindle UI.
. /mnt/us/extensions/dashboard/bin/common.sh

echo $$ >"$DIR/dashboard.pid"
log "Starting dashboard (pid $$)"
load_config || exit 1

SLEEP_PID=""
EXITING=""

restore_ui() {
    [ -n "$EXITING" ] && return
    EXITING=1
    log "Exiting dashboard ($(cat /tmp/dashboard.input 2>/dev/null || echo signal)), restarting the Kindle UI"
    [ -n "$SLEEP_PID" ] && kill "$SLEEP_PID" 2>/dev/null
    pkill -f "doubletap.lua" 2>/dev/null
    rm -f "$DIR/dashboard.pid" /tmp/dashboard.input
    lipc-set-prop com.lab126.powerd preventScreenSaver 0 2>/dev/null
    # The UI takes a while to come back; say so right away so the tap clearly registered.
    show_notice "Leaving dashboard..." "The Kindle home screen will appear in about 30 seconds."
    start lab126_gui 2>/dev/null || /etc/init.d/framework start
    # Once the UI answers, make sure we land on the home screen.
    i=0
    while [ $i -lt 120 ]; do
        lipc-get-prop com.lab126.appmgrd activeApp >/dev/null 2>&1 && break
        sleep 1; i=$((i + 1))
    done
    log "Kindle UI answered after ${i}s"
    sleep 5
    lipc-set-prop com.lab126.appmgrd start app://com.lab126.booklet.home 2>/dev/null
    exit 0
}

# Stop the UI so it doesn't draw over the dashboard. The job sends SIGTERM on stop; ignore it.
trap "" TERM
stop lab126_gui 2>/dev/null || /etc/init.d/framework stop
sleep 2
trap restore_ui USR1 INT HUP TERM

lipc-set-prop com.lab126.powerd preventScreenSaver 1
lipc-set-prop com.lab126.cmd wirelessEnable 1 2>/dev/null

# Exit on a double tap. The touchscreen is the input device that reports absolute
# positions; its event path differs between units, so find it via sysfs.
LUAJIT=/mnt/us/koreader/luajit
watch_input() {
    rm -f /tmp/dashboard.input
    if [ ! -x "$LUAJIT" ]; then
        log "WARNING: $LUAJIT not found (is KOReader installed?), double-tap exit disabled"
        return
    fi
    found=""
    for caps in /sys/class/input/event*/device/capabilities/abs; do
        [ "$(cat "$caps" 2>/dev/null)" = "0" ] && continue
        ev="$(basename "$(dirname "$(dirname "$(dirname "$caps")")")")"
        name="$(cat "/sys/class/input/$ev/device/name" 2>/dev/null)"
        found="$found $ev"
        log "Watching /dev/input/$ev ($name) for a double tap"
        (
            "$LUAJIT" "$DIR/bin/doubletap.lua" "/dev/input/$ev" >/tmp/dashboard.input 2>&1 || exit 0
            kill -USR1 $$
        ) &
    done
    [ -z "$found" ] && log "WARNING: no touchscreen found, double-tap exit disabled"
}

wait_for_wifi() {
    i=0
    while [ $i -lt 60 ]; do
        ping -c 1 -W 2 api.github.com >/dev/null 2>&1 && return 0
        i=$((i + 1)); sleep 2
    done
    return 1
}

# Seconds until REFRESH_MINUTE past the next hour (or this hour, if still ahead).
seconds_until_refresh() {
    m=$(date +%M); s=$(date +%S)
    now=$(( ${m#0} * 60 + ${s#0} ))
    target=$(( REFRESH_MINUTE * 60 ))
    if [ $now -lt $target ]; then echo $(( target - now )); else echo $(( 3600 - now + target )); fi
}

refresh() {
    log "Refreshing (battery $(gasgauge-info -c 2>/dev/null))"
    if wait_for_wifi && fetch_image; then
        show_image
        show_battery
    else
        [ -f "$IMG" ] && show_image && show_battery
        show_message "Offline - last update failed $(date '+%H:%M') UTC"
    fi
}

refresh
sleep 2          # let the tap that launched us settle before watching for the next one
watch_input
while true; do
    wait_s=$(seconds_until_refresh)
    log "Next refresh in ${wait_s}s"
    # Background sleep + wait, so the exit signal is handled immediately.
    sleep "$wait_s" &
    SLEEP_PID=$!
    wait "$SLEEP_PID"
    SLEEP_PID=""
    refresh
done
