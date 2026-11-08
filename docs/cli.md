# Command Line

## CLI Commands

```bash
# Start the main daemon
libmbus2mqtt run

# Scan for M-Bus devices (one-time)
libmbus2mqtt scan

# Show M-Bus adapter information
libmbus2mqtt device-info

# Show version
libmbus2mqtt version
# or
libmbus2mqtt --version

# Validate configuration file
libmbus2mqtt config validate

# Generate example configuration
libmbus2mqtt config init

# Install/uninstall systemd service
libmbus2mqtt install
libmbus2mqtt uninstall

# Install libmbus (native installation only)
libmbus2mqtt libmbus install
```

## Using a Custom Config File

Commands use `/etc/libmbus2mqtt/config.yaml` natively and `/data/config/config.yaml` in Docker. To use another file:

```bash
libmbus2mqtt run --config /path/to/config.yaml
libmbus2mqtt scan --config /path/to/config.yaml
```
