#!/bin/sh
# Runs the app as an unprivileged user (PUID/PGID), fixing ownership of the upload folder first.
set -e

if [ "$(id -u)" = "0" ]; then
    mkdir -p "$UPLOAD_FOLDER"
    # Only touches entries with a different owner, so restarts stay fast
    find "$UPLOAD_FOLDER" \( ! -user "$PUID" -o ! -group "$PGID" \) -exec chown -h "$PUID:$PGID" {} +
    exec setpriv --reuid="$PUID" --regid="$PGID" --clear-groups --inh-caps=-all "$@"
fi

exec "$@"
