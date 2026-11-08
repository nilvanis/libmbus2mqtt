# Changelog

## 2.2.0 (unreleased)

### Docker: file ownership and permissions

- **Changed:** the container now runs as `PUID:PGID` (default `1000:1000`)
  instead of uid `999`. A new entrypoint starts as root only to prepare `/data`:
  it creates missing directories, hands files to `PUID:PGID`, removes access
  for other users and grants the groups of mapped devices. It then drops to
  that user with `setpriv` (no capabilities, `no_new_privs`).
  - Existing `./data` directories from older images are migrated automatically
    on first start. No `chmod 777` is needed.
  - USB/serial adapters mapped with `devices:` work without `group_add`.
- With `user:` the entrypoint changes nothing (hardened mode for `cap_drop: ALL`
  and read-only root filesystems); `PUID: 0` supports rootless Docker/Podman.
- The image no longer ships a placeholder config generated at build time.

### Fixes

- SIGTERM/SIGINT during the startup scan or `startup_delay` was ignored and the
  daemon went on polling; `docker stop` then ended in SIGKILL. Shutdown now
  interrupts running libmbus tools, retry delays and the poll loop.
- An exception in the MQTT connect callback stopped paho's network thread, so
  the bridge never reconnected. Callbacks are isolated, and post-connect
  republishing now runs on the main thread instead of racing it.
- `libmbus install` built as root in the fixed path `/tmp/libmbus-build`; it now
  uses a private temporary directory.
- The MQTT log-level command and Home Assistant select accept `CRITICAL`, like
  the config.

### Startup checks

- `run` and `scan` check data directory and serial device access up front and
  report the process uid/gid, the path owner and how to fix it, instead of
  failing with "unable to open database file" or silent polling errors.
- `config init` creates the file with mode `0600`; `install` prints the
  `chown` step the service needs to read it.
- Rescan and poll-interval commands take effect immediately instead of after
  the current poll interval.

### Also in this release

- Added `--data-dir` for runtime storage, user templates, and the default log
  file. Docker keeps `/data`; the systemd service passes
  `/var/lib/libmbus2mqtt`.
- File logging is enabled by default, with size-based rotation and five backups.
- Bundled the systemd unit in Python wheels and aligned its writable paths with
  the daemon's storage configuration.
- Redacted secrets in environment override logs and hid input values in
  configuration validation errors.
- Fixed an unclosed SQLite connection in the test helpers.
- Pinned libmbus source to a commit and shared its TCP timeout patch between
  Docker and native installations. Docker now installs runtime dependencies
  from `uv.lock` and uses pinned Python and uv versions.
- Added installed-wheel and container/MQTT integration checks, a single source
  of the package version, and required checks before release publication.
- Added commit-specific tags alongside the mutable `dev` image tag.
