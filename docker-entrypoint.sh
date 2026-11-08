#!/bin/sh
# Prepare /data for the runtime user, then run libmbus2mqtt without root.
#
# Started as root (the default): make /data owned by PUID:PGID, grant the groups
# of mapped character devices (serial adapters) and drop to that user with
# setpriv. Started with `user:` / --user: run the app directly; ownership and
# device access are then the operator's responsibility.
set -eu

DATA_DIR="${LIBMBUS2MQTT_DATA_DIR:-/data}"
umask 027

if [ "$(id -u)" != 0 ]; then
    # Setting no_new_privs needs no privileges; keep the same guarantee as below.
    exec setpriv --no-new-privs libmbus2mqtt "$@"
fi

PUID="${PUID:-1000}"
PGID="${PGID:-1000}"

log() {
    echo "docker-entrypoint: $*" >&2
}

is_uint() {
    case "$1" in
        '' | *[!0-9]*) return 1 ;;
        *) return 0 ;;
    esac
}

if ! is_uint "$PUID" || ! is_uint "$PGID"; then
    log "PUID and PGID must be numeric (got PUID='$PUID' PGID='$PGID')"
    exit 64
fi

# Ownership is changed recursively below: refuse anything but a real subdirectory.
case "$DATA_DIR" in
    /?*) ;;
    *)
        log "LIBMBUS2MQTT_DATA_DIR must be an absolute path other than / (got '$DATA_DIR')"
        exit 64
        ;;
esac

if [ "$PUID" = 0 ]; then
    log "WARNING: PUID=0, running libmbus2mqtt as root"
    exec libmbus2mqtt "$@"
fi

prepare_data_dir() {
    mkdir -p "$DATA_DIR/config" "$DATA_DIR/log" "$DATA_DIR/templates" &&
        # Only touch what differs; -h changes symlinks themselves, never their targets.
        find "$DATA_DIR" \( ! -user "$PUID" -o ! -group "$PGID" \) \
            -exec chown -h "$PUID:$PGID" {} + &&
        # The config holds MQTT credentials: nothing in /data is meant for other users.
        find "$DATA_DIR" ! -type l -perm /o=rwx -exec chmod o-rwx {} +
}

if ! prepare_data_dir; then
    log "cannot prepare $DATA_DIR for $PUID:$PGID."
    log "With cap_drop: ALL or a read-only /data, run the container with" \
        "user: \"$PUID:$PGID\" and set the ownership on the host instead."
    exit 1
fi

# Mapped serial adapters keep their host group (e.g. dialout = 20): grant those.
# Skip root (0) and tty (5) so no unrelated access comes along.
groups="$PGID"
for gid in $(find /dev \( -path /dev/pts -o -path /dev/shm -o -path /dev/mqueue \) -prune \
    -o -type c -printf '%G\n' | sort -un); do
    case "$gid" in
        0 | 5 | "$PGID") ;;
        *) groups="$groups,$gid" ;;
    esac
done

exec setpriv --reuid="$PUID" --regid="$PGID" --groups="$groups" \
    --no-new-privs --inh-caps=-all --bounding-set=-all \
    libmbus2mqtt "$@"
