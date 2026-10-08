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

# Seconds until the next HH:00 (local time).
secs_until_hour() {
    h=$(date +%H); m=$(date +%M); sec=$(date +%S)
    now=$(( ${h#0} * 3600 + ${m#0} * 60 + ${sec#0} ))
    t=$(( $1 * 3600 ))
    if [ $now -lt $t ]; then echo $(( t - now )); else echo $(( 86400 - now + t )); fi
}

in_night() {
    h=$(date +%H); h=${h#0}
    [ "$h" -ge "$NIGHT_START" ] && [ "$h" -lt "$NIGHT_END" ]
}

# Background sleep + wait, so a double tap is handled immediately.
pause() {
    sleep "$1" &
    SLEEP_PID=$!
    wait "$SLEEP_PID"
    SLEEP_PID=""
}

# Suspend to RAM with an RTC alarm $1 seconds ahead. Returns non-zero if this Kindle won't do it.
rtc_suspend() {
    rtc=""
    for r in /sys/class/rtc/rtc0/wakealarm /sys/class/rtc/rtc1/wakealarm; do
        [ -w "$r" ] && { rtc="$r"; break; }
    done
    [ -n "$rtc" ] || return 1
    echo 0 >"$rtc"
    echo "+$1" >"$rtc" 2>/dev/null || echo $(( $(date +%s) + $1 )) >"$rtc" || return 1
    echo mem >/sys/power/state 2>/dev/null || return 1
}

# Midnight to 6 AM: show the night screen, switch Wi-Fi off, deep sleep (or idle) until morning.
night() {
    secs=$(secs_until_hour "$NIGHT_END")
    deadline=$(( $(date +%s) + secs ))
    log "Night: sleeping ${secs}s until ${NIGHT_END}:00"
    if [ -f "$DIR/night.png" ]; then
        fb="$(find_fbink)"
        if [ -n "$fb" ]; then "$fb" -q -c -f -g file="$DIR/night.png"; else eips -c; eips -f -g "$DIR/night.png"; fi
    fi
    show_battery
    sleep 3
    lipc-set-prop com.lab126.cmd wirelessEnable 0 2>/dev/null
    early=0
    while [ "$NIGHT_SUSPEND" = 1 ] && [ $early -lt 3 ]; do
        left=$(( deadline - $(date +%s) ))
        [ $left -gt 120 ] || break
        t0=$(date +%s)
        if ! rtc_suspend "$left"; then
            log "Deep sleep isn't available; idling with Wi-Fi off instead"
            break
        fi
        slept=$(( $(date +%s) - t0 ))
        log "Woke after ${slept}s of deep sleep"
        [ $slept -lt 60 ] && early=$((early + 1))
    done
    [ $early -ge 3 ] && log "Deep sleep kept ending straight away; idling with Wi-Fi off instead"
    left=$(( deadline - $(date +%s) ))
    [ $left -gt 0 ] && pause "$left"
    lipc-set-prop com.lab126.cmd wirelessEnable 1 2>/dev/null
    deep_clean
    log "Good morning (screen cleaned)"
}

refresh() {
    log "Refreshing (battery $(battery_level)%)"
    if wait_for_wifi; then
        # Ask for a fresh render first (GitHub skips many scheduled runs), then download.
        t0=$(date +%s)
        trigger_render && wait_for_render $(( t0 - 120 ))
        fetch_image || log "Keeping the previous image"
    else
        log "No Wi-Fi; keeping the previous image"
    fi
    [ -f "$IMG" ] && show_image
    show_battery
    show_stale_if_old
}

in_night || refresh
sleep 2          # let the tap that launched us settle before watching for the next one
watch_input
BATTERY_EVERY=600   # redraw the battery indicator every 10 minutes between refreshes
while true; do
    if in_night; then
        night
        LOGGED=""
        refresh
        continue
    fi
    wait_s=$(seconds_until_refresh)
    to_night=$(secs_until_hour "$NIGHT_START")
    [ "$to_night" -lt "$wait_s" ] && wait_s=$to_night
    step=$wait_s
    [ "$step" -gt "$BATTERY_EVERY" ] && step=$BATTERY_EVERY
    [ -n "$LOGGED" ] || log "Next refresh in ${wait_s}s"
    LOGGED=1
    pause "$step"
    if [ "$step" -lt "$wait_s" ]; then
        show_battery
        show_stale_if_old
    elif ! in_night; then
        LOGGED=""
        refresh
    fi
done
