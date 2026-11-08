# Docker

The basic setup is described in the [Quick Start](../README.md#quick-start-with-docker-recommended).

## Permissions

The container starts as root only long enough to prepare `/data`, then runs libmbus2mqtt as `PUID:PGID` with no capabilities and `no_new_privs` set.

Set `PUID`/`PGID` to your own user (run `id -u` and `id -g` on the host). The files in `./data` then belong to you, and you can edit the config without `sudo`.

## Hardened Mode

If the container must never start as root (for example with `cap_drop: ALL` or a read-only root filesystem), set `user:` instead of `PUID`/`PGID`. The entrypoint then changes nothing, so prepare `./data` and device access yourself:

```yaml
    user: "1000:1000"
    group_add: ["20"]        # group of the adapter: stat -c %g /dev/ttyUSB0
    read_only: true
    cap_drop: [ALL]
```

```bash
sudo chown -R 1000:1000 data && chmod -R o-rwx data
```

## Rootless Docker

With rootless Docker, set `PUID: 0`. In those runtimes the container's root is your own user.

## Configuration Without a File

The whole configuration, except `devices`, can be passed as environment variables in `docker-compose.yml`. See [Environment Variables](environment-variables.md).
