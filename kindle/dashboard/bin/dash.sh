#!/bin/sh
# Dashboard loop: stop the Kindle UI, show the dashboard, refresh hourly.
# Press the power button to exit back to the normal Kindle UI.
. /mnt/us/extensions/dashboard/bin/common.sh

echo $$ >"$DIR/dashboard.pid"
log "Starting dashboard (pid $$)"
load_config || exit 1

restore_ui() {
    log "Exiting dashboard, restarting the Kindle UI"
    lipc-set-prop com.lab126.powerd preventScreenSaver 0 2>/dev/null
    rm -f "$DIR/dashboard.pid"
    start lab126_gui 2>/dev/null || /etc/init.d/framework start
    exit 0
}
trap restore_ui INT HUP

# Stop the UI so it doesn't draw over the dashboard. The job sends SIGTERM on stop; ignore it.
trap "" TERM
stop lab126_gui 2>/dev/null || /etc/init.d/framework stop
sleep 2
trap restore_ui TERM

lipc-set-prop com.lab126.powerd preventScreenSaver 1
lipc-set-prop com.lab126.cmd wirelessEnable 1 2>/dev/null

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
while true; do
    wait_s=$(seconds_until_refresh)
    log "Next refresh in ${wait_s}s"
    # Sleep until the next refresh, but wake immediately if the power button is pressed.
    started=$(date +%s)
    ev="$(lipc-wait-event -s "$wait_s" com.lab126.powerd goingToScreenSaver 2>/dev/null)"
    case "$ev" in
        *goingToScreenSaver*) restore_ui ;;
    esac
    # If lipc-wait-event returned early without an event, sleep out the rest instead of spinning.
    left=$(( wait_s - ($(date +%s) - started) ))
    [ $left -gt 5 ] && sleep $left
    refresh
done
