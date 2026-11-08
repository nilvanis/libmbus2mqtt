# Native Installation

For running directly on Linux without Docker, as a systemd service. Requires Python 3.11+.

| Path | Contents |
| --- | --- |
| `/opt/libmbus2mqtt` | Program (Python virtual environment) |
| `/etc/libmbus2mqtt/config.yaml` | Configuration |
| `/var/lib/libmbus2mqtt` | Database, logs, user templates |

## Step 1: Install libmbus2mqtt and libmbus

```bash
# Build dependencies (Debian/Ubuntu/Raspberry Pi OS)
sudo apt-get install python3-venv ca-certificates git build-essential libtool libltdl-dev autoconf automake

# Install libmbus2mqtt into its own virtual environment
sudo python3 -m venv /opt/libmbus2mqtt
sudo /opt/libmbus2mqtt/bin/pip install git+https://github.com/nilvanis/libmbus2mqtt
sudo ln -s /opt/libmbus2mqtt/bin/libmbus2mqtt /usr/local/bin/libmbus2mqtt

# Build and install libmbus
sudo libmbus2mqtt libmbus install
```

Or install libmbus manually - see [libmbus on GitHub](https://github.com/rscada/libmbus).

## Step 2: Install the service

```bash
sudo libmbus2mqtt install
```

This creates:

- the `libmbus2mqtt` user, a member of `dialout` so it can open serial adapters;
- `/etc/libmbus2mqtt/config.yaml` from the example, readable only by that user (an existing file is kept);
- `/var/lib/libmbus2mqtt`;
- the systemd service, enabled at boot but not started yet.

## Step 3: Edit the configuration

```bash
sudo nano /etc/libmbus2mqtt/config.yaml
```

Set at least `mbus.device` and `mqtt.host`; see [Configuration](../README.md#configuration).

## Step 4: Test the connection (optional)

Run the checks as the service user, so they use the same permissions as the service:

```bash
# Check if your M-Bus device is accessible
sudo -u libmbus2mqtt libmbus2mqtt device-info

# Scan for connected meters
sudo -u libmbus2mqtt libmbus2mqtt scan
```

## Step 5: Start the service

```bash
sudo systemctl start libmbus2mqtt
sudo journalctl -u libmbus2mqtt -f
```

## Managing the Service

```bash
# Check status
sudo systemctl status libmbus2mqtt

# Stop the service
sudo systemctl stop libmbus2mqtt

# Update libmbus2mqtt
sudo /opt/libmbus2mqtt/bin/pip install --upgrade git+https://github.com/nilvanis/libmbus2mqtt
sudo systemctl restart libmbus2mqtt

# Remove the service (--purge also deletes the config, data and user)
sudo libmbus2mqtt uninstall
```
