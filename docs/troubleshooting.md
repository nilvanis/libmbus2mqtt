# Troubleshooting

## Permission Denied on Serial Device

- **Docker (default mode):** make sure the adapter is correctly listed under `devices:`.
- **Docker with `user:`:** add the device's group: `group_add: ["<gid>"]`, where `<gid>` comes from `stat -c %g /dev/ttyUSB0`.
- **Native:** the service user `libmbus2mqtt` is already in `dialout`. Check that the adapter's group is `dialout`, with `stat -c %G /dev/ttyUSB0`. To run commands as your own user instead of `sudo -u libmbus2mqtt`, add yourself to that group, then log out and back in:

```bash
sudo usermod -aG dialout $USER
```

## Permission Denied on /data (Docker)

- **Default mode:** set `PUID`/`PGID` in `docker-compose.yml` and don't set `user:`. The entrypoint then fixes ownership on start.
- **[Hardened mode](docker.md#hardened-mode):** run `sudo chown -R <uid>:<gid> data` on the host, where `data` is the data directory for libmbus2mqtt.

## No Devices Found

1. **Check wiring** - Ensure M-Bus devices are properly connected
2. **Check baudrate** - Most M-Bus devices use 2400, but some use 300 or 9600
3. **Test with libmbus directly**:

   ```bash
   mbus-serial-scan -b 2400 /dev/ttyUSB0
   ```

4. **Check power** - M-Bus devices need power from the M-Bus master

## Device Shows Offline

- Check if the device is physically connected
- Increase `availability.timeout_polls` in config
- Check for loose wiring

## Home Assistant Doesn't Show Devices

1. Verify `homeassistant.enabled: true` in config
2. Check MQTT broker connection
3. Verify `discovery_prefix` matches Home Assistant (default: `homeassistant`)
4. Check Home Assistant MQTT integration is enabled
5. Check mosquitto addon logs

## View Logs

```bash
# Docker
docker compose logs -f libmbus2mqtt

# Systemd service
sudo journalctl -u libmbus2mqtt -f
```

You can set log level to DEBUG temporarily in Home Assistant MQTT device "libmbus2mqtt Bridge".\
You can also set the log level permanently using either:
- config.yaml `logs.level` option
- `LIBMBUS2MQTT_LOGS_LEVEL` env variable

## Persistent Log Files

File logging is enabled by default:

```yaml
logs:
  save_to_file: true
  file:                        # Default: <data-dir>/log/libmbus2mqtt.log
```

Log files are automatically rotated when they reach `max_size_mb` (default: 10 MB). Old files are kept up to `backup_count` (default: 5).

> [!NOTE]
> Log level changes via MQTT (`libmbus2mqtt/command/log_level`) are not persisted - they reset to the config value on restart. To permanently change the log level, edit `logs.level` in your config file.
