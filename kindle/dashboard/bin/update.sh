#!/bin/sh
# Over-the-air updates and remote logs. Sourced after common.sh by dash.sh and start.sh.
#
# Every render publishes kindle.tar (this folder as it is on GitHub) and kindle.version to the
# output branch. At each refresh the Kindle compares kindle.version with its VERSION file. When
# they differ it downloads the bundle, checks it, backs up every file it replaces, installs it and
# restarts the dashboard. A watchdog puts the backup back if the new dashboard hasn't started
# within WATCHDOG_SECS; that version is then skipped until a newer one is published.
# config.sh, the log and the downloaded images are never touched.

UPD="$T/dash-update"
BACKUP="$DIR/.backup"              # the files the last update replaced, for a rollback
PENDING="$DIR/.update-pending"     # "<new> <old>" until the new dash.sh says it started
BAD="$DIR/.update-bad"             # a version that didn't start; skipped
LOGFILE="$DIR/dashboard.log"
LOG_SENT="$DIR/.log-sent"          # bytes of dashboard.log already sent to GitHub
LOG_MAX=30000                      # most log bytes per upload (GitHub caps the request size)
WATCHDOG_SECS="${WATCHDOG_SECS:-150}"

installed_version() { cat "$DIR/VERSION" 2>/dev/null || echo none; }

# Install a newer bundle if one is published. Returns 0 when one was installed (restart needed).
apply_update() {
    [ "${UPDATES:-1}" = 1 ] || return 1
    have="$(installed_version)"
    gh_get kindle.version "$T/dash.version" 2>/dev/null || return 1
    want="$(tr -dc '0-9a-f' <"$T/dash.version")"
    rm -f "$T/dash.version"
    [ -n "$want" ] && [ "$want" != "$have" ] || return 1
    [ "$want" = "$(cat "$BAD" 2>/dev/null)" ] && return 1
    log "Update: $have -> $want"
    rm -rf "$UPD"
    mkdir -p "$UPD/new"
    if ! gh_get kindle.tar "$UPD/kindle.tar"; then
        log "Update: download failed; trying again at the next refresh"
        rm -rf "$UPD"; return 1
    fi
    if ! tar -xf "$UPD/kindle.tar" -C "$UPD/new" 2>"$UPD/err"; then
        log "Update: couldn't unpack the bundle: $(head -c 200 "$UPD/err")"
        rm -rf "$UPD"; return 1
    fi
    if ! check_bundle "$UPD/new" "$want"; then
        echo "$want" >"$BAD"
        rm -rf "$UPD"; return 1
    fi
    # The watchdog runs the current (known good) scripts, not the new ones.
    cp "$DIR/bin/common.sh" "$T/dash-wd-common.sh"
    cp "$DIR/bin/update.sh" "$T/dash-wd-update.sh"
    install_bundle "$UPD/new" "$have" "$want"
    rm -rf "$UPD"
    start_watchdog
    return 0
}

# Refuse a bundle that is incomplete, has a shell syntax error or doesn't match its version.
check_bundle() {
    for f in bin/common.sh bin/dash.sh bin/start.sh bin/update.sh bin/gestures.lua menu.json config.xml; do
        [ -s "$1/$f" ] || { log "Update rejected: $f is missing"; return 1; }
    done
    for f in "$1"/bin/*.sh "$1"/settings.sh; do
        [ -f "$f" ] || continue
        if ! sh -n "$f" 2>"$UPD/err"; then
            log "Update rejected: ${f#"$1"/} has a syntax error: $(head -c 200 "$UPD/err")"
            return 1
        fi
    done
    if [ -x "$LUAJIT" ] && ! "$LUAJIT" -e "assert(loadfile('$1/bin/gestures.lua'))" 2>"$UPD/err"; then
        log "Update rejected: gestures.lua doesn't load: $(head -c 200 "$UPD/err")"
        return 1
    fi
    [ "$(cat "$1/VERSION" 2>/dev/null)" = "$2" ] || { log "Update rejected: the bundle isn't version $2"; return 1; }
}

# Copy the bundle over $DIR, keeping a copy of each file it replaces: install_bundle DIR OLD NEW
install_bundle() {
    rm -rf "$BACKUP"
    mkdir -p "$BACKUP"
    echo "$2" >"$BACKUP/.version"
    : >"$BACKUP/.added"
    : >"$BACKUP/.changed"
    (cd "$1" && find . -type f ! -name VERSION) | while read -r f; do
        f="${f#./}"
        case "$f" in config.sh|dashboard.log) continue ;; esac
        if [ -f "$DIR/$f" ]; then
            cmp -s "$1/$f" "$DIR/$f" && continue
            mkdir -p "$BACKUP/$(dirname "$f")"
            cp "$DIR/$f" "$BACKUP/$f"
        else
            echo "$f" >>"$BACKUP/.added"
        fi
        mkdir -p "$DIR/$(dirname "$f")"
        # New file, then rename: a running shell keeps reading the old one undisturbed.
        cp "$1/$f" "$DIR/$f.new" && mv -f "$DIR/$f.new" "$DIR/$f"
        echo "$f" >>"$BACKUP/.changed"
    done
    # Scripts the new version doesn't have any more (a renamed helper, for example).
    for f in "$DIR"/bin/*; do
        [ -e "$f" ] || continue
        b="bin/${f##*/}"
        [ -e "$1/$b" ] && continue
        mkdir -p "$BACKUP/bin"
        mv -f "$f" "$BACKUP/$b"
        echo "$b" >>"$BACKUP/.changed"
    done
    echo "$3" >"$DIR/VERSION"
    echo "$3 $2" >"$PENDING"
    sync
    log "Update: installed $3 ($(wc -l <"$BACKUP/.changed" | tr -d ' ') files changed)"
}

# Called by the new dash.sh once it's up: the update worked, so the watchdog stands down.
confirm_update() {
    [ -f "$PENDING" ] || return 0
    log "Update: $(cut -d' ' -f1 "$PENDING") is running"
    rm -f "$PENDING"
    sync
}

# Put back the files the last update replaced.
rollback_update() {
    [ -f "$BACKUP/.version" ] || { log "Update: no backup to roll back to"; return 1; }
    bad="$(cut -d' ' -f1 "$PENDING" 2>/dev/null)"
    (cd "$BACKUP" && find . -type f ! -name .version ! -name .added ! -name .changed) | while read -r f; do
        f="${f#./}"
        mkdir -p "$DIR/$(dirname "$f")"
        cp "$BACKUP/$f" "$DIR/$f.new" && mv -f "$DIR/$f.new" "$DIR/$f"
    done
    while read -r f; do [ -n "$f" ] && rm -f "$DIR/$f"; done <"$BACKUP/.added"
    cp "$BACKUP/.version" "$DIR/VERSION"
    [ -n "$bad" ] && echo "$bad" >"$BAD"
    rm -f "$PENDING"
    rm -rf "$BACKUP"
    sync
    log "Update: rolled back to $(installed_version); $bad will be skipped"
}

# Start the dashboard loop in its own session, so it outlives whoever started it.
launch_dashboard() {
    if command -v setsid >/dev/null 2>&1; then
        setsid sh "$DIR/bin/dash.sh" >>"$LOGFILE" 2>&1 </dev/null &
    else
        nohup sh "$DIR/bin/dash.sh" >>"$LOGFILE" 2>&1 </dev/null &
    fi
}

# Watch the new version from outside: if it hasn't confirmed in time, stop it, roll back and
# start the old one. Runs the copies of the old scripts saved by apply_update.
start_watchdog() {
    cmd='. "$1"; . "$2"; watchdog'
    if command -v setsid >/dev/null 2>&1; then
        setsid sh -c "$cmd" watchdog "$T/dash-wd-common.sh" "$T/dash-wd-update.sh" >>"$LOGFILE" 2>&1 </dev/null &
    else
        nohup sh -c "$cmd" watchdog "$T/dash-wd-common.sh" "$T/dash-wd-update.sh" >>"$LOGFILE" 2>&1 </dev/null &
    fi
}
watchdog() {
    trap '' HUP
    sleep "$WATCHDOG_SECS"
    [ -f "$PENDING" ] || exit 0
    log "Update: $(cut -d' ' -f1 "$PENDING") didn't start within ${WATCHDOG_SECS}s; rolling back"
    # Stop the new dashboard if it's still there (hung, say): its whole process group, which
    # holds its gesture readers, but only if the pid file really names a dash.sh.
    pid="$(cat "$PIDFILE" 2>/dev/null)"
    if [ -n "$pid" ] && tr '\0' ' ' 2>/dev/null <"/proc/$pid/cmdline" | grep -qF "bin/dash.sh"; then
        if [ "$(cut -d' ' -f5 "/proc/$pid/stat" 2>/dev/null)" = "$pid" ]; then kill -9 -- "-$pid"; else kill -9 "$pid"; fi
    fi
    pkill -f "bin/gestures.lua" 2>/dev/null
    rm -f "$PIDFILE"
    rollback_update && launch_dashboard
    exit 0
}

# One line about the device for the logs branch (status.txt).
device_status() {
    up="$(cut -d. -f1 /proc/uptime 2>/dev/null)"
    free="$(df -k "$R/mnt/us" 2>/dev/null | awk 'NR == 2 { printf "%d MB", $4 / 1024 }')"
    chg=no; battery_charging && chg=yes
    echo "version $(installed_version), battery $(battery_level)% (charging: $chg), page ${PAGE:-1}," \
        "up $(( ${up:-0} / 3600 )) h, free $free, Wi-Fi $(lipc-get-prop com.lab126.wifid cmState 2>/dev/null || echo unknown)"
}

# Text on stdin as the inside of a JSON string.
json_text() {
    tr '\t\r' '  ' | tr -d '\000-\010\013-\037' | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' | awk '{ printf "%s\\n", $0 }'
}

# The body of a render request: the new log lines and the device status ride along, so sending
# them costs no extra GitHub Actions run. Sets LOG_UPTO to the log size it covers.
render_request() {
    LOG_UPTO=""
    if [ "${LOG_UPLOAD:-1}" != 1 ] || [ ! -f "$LOGFILE" ]; then
        echo '{"ref":"main"}'
        return
    fi
    size=$(wc -c <"$LOGFILE" | tr -d ' ')
    sent=$(cat "$LOG_SENT" 2>/dev/null)
    case "$sent" in ''|*[!0-9]*) sent=0 ;; esac
    [ "$sent" -gt "$size" ] && sent=0          # the log was cut short since
    from=$sent
    [ $((size - sent)) -gt $LOG_MAX ] && from=$((size - LOG_MAX))
    {
        if [ $from -gt $sent ]; then
            echo "[... $((from - sent)) earlier bytes of dashboard.log not sent]"
            tail -c +$((from + 1)) "$LOGFILE" | head -c $((size - from)) | sed 1d   # 1d: a cut line
        else
            tail -c +$((from + 1)) "$LOGFILE" | head -c $((size - from))
        fi
    } >"$T/dash.lognew"
    printf '{"ref":"main","inputs":{"log":"%s","device":"%s"}}\n' \
        "$(json_text <"$T/dash.lognew")" "$(device_status | json_text | sed 's/\\n$//')"
    rm -f "$T/dash.lognew"
    LOG_UPTO=$size
}

# After a render request with the log went through: remember how far it got, and keep the
# file on the Kindle small (in place: the running dashboard appends to this same file).
log_sent() {
    [ -n "$LOG_UPTO" ] || return 0
    echo "$LOG_UPTO" >"$LOG_SENT"
    [ "$LOG_UPTO" -gt 400000 ] || return 0
    unsent=$(( $(wc -c <"$LOGFILE") - LOG_UPTO ))   # written since the request was made
    tail -n 1500 "$LOGFILE" >"$T/dash.logkeep" && cat "$T/dash.logkeep" >"$LOGFILE"
    rm -f "$T/dash.logkeep"
    echo $(( $(wc -c <"$LOGFILE") - unsent )) >"$LOG_SENT"
}
