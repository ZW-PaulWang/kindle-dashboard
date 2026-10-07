#!/bin/sh
# Dashboard loop: stop the Kindle UI, show the dashboard, refresh hourly.
# Tap the screen or press the power button to exit back to the normal Kindle UI.
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
    pkill -f "dd if=/dev/input/" 2>/dev/null
    rm -f "$DIR/dashboard.pid" /tmp/dashboard.input
    lipc-set-prop com.lab126.powerd preventScreenSaver 0 2>/dev/null
    start lab126_gui 2>/dev/null || /etc/init.d/framework start
    exit 0
}

# Stop the UI so it doesn't draw over the dashboard. The job sends SIGTERM on stop; ignore it.
trap "" TERM
stop lab126_gui 2>/dev/null || /etc/init.d/framework stop
sleep 2
trap restore_ui USR1 INT HUP TERM

lipc-set-prop com.lab126.powerd preventScreenSaver 1
lipc-set-prop com.lab126.cmd wirelessEnable 1 2>/dev/null

# Exit on any touch or button press: one blocking reader per input device signals us.
# (evdev readers don't steal events, so this doesn't interfere with anything else.)
watch_input() {
    rm -f /tmp/dashboard.input
    for dev in /dev/input/event*; do
        [ -e "$dev" ] || continue
        (
            dd if="$dev" of=/dev/null bs=64 count=1 2>/dev/null || exit 0
            name="$(cat "/sys/class/input/$(basename "$dev")/device/name" 2>/dev/null)"
            echo "$dev $name" >/tmp/dashboard.input
            kill -USR1 $$
        ) &
    done
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
    else
        [ -f "$IMG" ] && show_image
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
