# Changelog

## 2.1.1 (unreleased)

- Added `data_dir` / `LIBMBUS2MQTT_DATA_DIR` for runtime storage, user templates,
  and the default log file. Docker keeps `/data`; the systemd service uses
  `/var/lib/libmbus2mqtt`.
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
