#!/bin/sh
# Shared helpers for the dashboard scripts.
DIR="/mnt/us/extensions/dashboard"
IMG="$DIR/dashboard.png"
TMP_IMG="/tmp/dashboard.png.part"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*"; }

load_config() {
    if [ ! -f "$DIR/config.sh" ]; then
        log "ERROR: $DIR/config.sh is missing (copy config.example.sh and fill it in)"
        return 1
    fi
    . "$DIR/config.sh"
    BRANCH="${BRANCH:-output}"
    REFRESH_MINUTE="${REFRESH_MINUTE:-5}"
    if [ -z "$REPO" ] || [ -z "$GITHUB_TOKEN" ]; then
        log "ERROR: REPO and GITHUB_TOKEN must be set in config.sh"
        return 1
    fi
}

find_fbink() {
    for f in /mnt/us/libkh/bin/fbink /mnt/us/koreader/fbink /usr/bin/fbink; do
        [ -x "$f" ] && { echo "$f"; return 0; }
    done
    return 1
}

# Download the latest image; only replace the current one if the download is a valid PNG.
fetch_image() {
    url="https://api.github.com/repos/$REPO/contents/dashboard.png?ref=$BRANCH"
    rm -f "$TMP_IMG"
    if command -v curl >/dev/null 2>&1; then
        curl -fsS --max-time 60 --retry 3 --retry-delay 10 \
            -H "Authorization: Bearer $GITHUB_TOKEN" \
            -H "Accept: application/vnd.github.raw" \
            -H "X-GitHub-Api-Version: 2022-11-28" \
            -o "$TMP_IMG" "$url" || { log "ERROR: curl download failed"; return 1; }
    else
        wget -q -T 60 -O "$TMP_IMG" \
            --header "Authorization: Bearer $GITHUB_TOKEN" \
            --header "Accept: application/vnd.github.raw" \
            "$url" || { log "ERROR: wget download failed"; return 1; }
    fi
    # PNG signature check (\x89PNG)
    if [ "$(dd if="$TMP_IMG" bs=1 skip=1 count=3 2>/dev/null)" != "PNG" ]; then
        log "ERROR: download is not a PNG: $(head -c 200 "$TMP_IMG")"
        return 1
    fi
    cat "$TMP_IMG" >"$IMG" && rm -f "$TMP_IMG"
    log "Downloaded $(wc -c <"$IMG") bytes"
}

show_image() {
    fb="$(find_fbink)"
    if [ -n "$fb" ]; then
        "$fb" -q -c -f -g file="$IMG" && return 0
    fi
    eips -c
    eips -f -g "$IMG"
}

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
