#!/bin/sh
# Check, without Wi-Fi, that this Kindle has the tools the dashboard and its updates use.
# The report goes to dashboard.log (and so to GitHub with the next upload) and on screen.
. "${DASH_ROOT:-}/mnt/us/extensions/dashboard/bin/common.sh"
. "$DIR/bin/update.sh"
ok=0; bad=""
need() { if command -v "$1" >/dev/null 2>&1; then ok=$((ok + 1)); else bad="$bad $1"; fi; }
{
    log "Self-check: version $(installed_version), $(busybox 2>/dev/null | head -n 1 || echo "no busybox")"
    for c in tar cmp find awk sed tr cut head tail wc pkill curl ping lipc-get-prop; do need "$c"; done
    command -v setsid >/dev/null 2>&1 || log "Self-check: no setsid (nohup is used instead)"
    w="$T/dash-selfcheck"; rm -rf "$w"; mkdir -p "$w/a/bin" "$w/b"
    echo "hello" >"$w/a/bin/x.sh"
    if (cd "$w/a" && tar -cf "$w/t.tar" .) && tar -xf "$w/t.tar" -C "$w/b" && cmp -s "$w/a/bin/x.sh" "$w/b/bin/x.sh"; then
        tarok=yes
    else
        tarok=no; bad="$bad tar-extract"
    fi
    rm -rf "$w"
    [ -x "$LUAJIT" ] && "$LUAJIT" -e "assert(loadfile('$DIR/bin/gestures.lua'))" 2>/dev/null || bad="$bad luajit/gestures.lua"
    for f in "$DIR"/bin/*.sh; do sh -n "$f" 2>/dev/null || bad="$bad syntax:${f##*/}"; done
    log "Self-check: $ok tools found, tar unpacking $tarok, missing or failing:${bad:- nothing}"
} >>"$LOGFILE" 2>&1
fb="$(find_fbink)"
if [ -z "$bad" ]; then msg="Dashboard self-check: all good"; else msg="Self-check problems:$bad"; fi
[ -n "$fb" ] && "$fb" -q -m -M "$msg"
