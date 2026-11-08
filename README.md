# libmbus2mqtt

[![CI](https://github.com/nilvanis/libmbus2mqtt/actions/workflows/ci.yml/badge.svg)](https://github.com/nilvanis/libmbus2mqtt/actions/workflows/ci.yml)
[![Docker Hub](https://img.shields.io/docker/v/nilvanis/libmbus2mqtt?label=Docker%20Hub&sort=semver)](https://hub.docker.com/r/nilvanis/libmbus2mqtt)

M-Bus to MQTT bridge with Home Assistant integration.

Read your wired M-Bus meters (water, heat, gas, electricity) and send the data to Home Assistant or any MQTT broker.

> **Disclaimer**: This software is provided 'as-is' without any guarantees.

## Features

- Reading M-Bus devices via serial M-Bus Master connected over:
  - TTL (UART)
  - USB
  - IPv4 TCP (using for example **ser2net**)
- Automatic discovery of connected M-Bus meters
- Publishing meter data to MQTT
- Home Assistant MQTT Discovery integration:
  - Automatic device and entity creation
  - Device availability reporting
  - Bridge device entity with controls (rescan, log level, poll interval)
- Template system to support different M-Bus device types ([supported devices](docs/supported-devices.md))
- Docker support with pre-compiled libmbus
- Systemd service for native Linux installation

## Documentation

- ⚡[Quick Start with Docker (recommended)](#quick-start-with-docker-recommended)
- [Configuration](#configuration) - all `config.yaml` options
- [Docker](docs/docker.md) - permissions, hardened mode, rootless Docker
- [Native Installation](docs/native-installation.md) - systemd service without Docker
- [Environment Variables](docs/environment-variables.md)
- [Command Line](docs/cli.md)
- [Home Assistant Integration](docs/home-assistant.md)
- [MQTT](docs/mqtt.md) - topics and TLS
- [Device Templates](docs/templates.md)
- [Hardware Setup](docs/hardware.md) - Raspberry Pi UART, USB adapters, ser2net
- [Supported Devices](docs/supported-devices.md)
- [Troubleshooting](docs/troubleshooting.md)

---

## Requirements

- **M-Bus Master adapter** - converts TTL/USB signals to M-Bus protocol
  - TTL to M-Bus converter ([example from AliExpress](https://s.click.aliexpress.com/e/_c2w4h9UB))
  - USB to M-Bus adapter ([example from AliExpress](https://s.click.aliexpress.com/e/_c4kbrInv))
- **Any Linux host device** with access to M-Bus Master via:
  - UART (TTL)
  - USB
  - IPv4 TCP
- **Docker** / **Docker Compose**
- **Python 3.11+** for [native installation](docs/native-installation.md)

---

## Quick Start with Docker (recommended)

Docker is the easiest way to get started - libmbus is pre-compiled in the image.

### Step 1: Create the project directory

```bash
mkdir libmbus2mqtt
cd libmbus2mqtt
```

### Step 2: Create docker-compose.yml

```bash
nano docker-compose.yml
```

Paste the following content:

```yaml
services:
  libmbus2mqtt:
    image: nilvanis/libmbus2mqtt:latest
    container_name: libmbus2mqtt
    restart: unless-stopped
    volumes:
      - ./data:/data
    devices:
      # Change this to match your M-Bus adapter
      - /dev/ttyUSB0:/dev/ttyUSB0
    environment:
      TZ: Europe/London
      # Owner of ./data on the host
      PUID: 1000
      PGID: 1000
```

Save and exit (Ctrl+O, Ctrl+X).

Set `PUID`/`PGID` to your own user (run `id -u` and `id -g` on the host). The files in `./data` then belong to you, and you can edit the config without `sudo`. More about permissions in [Docker](docs/docker.md).

### Step 3: Create configuration

```bash
mkdir -p data/config
nano data/config/config.yaml
```

Paste the following content and edit to match your setup:

```yaml
mbus:
  device: /dev/ttyUSB0          # Your M-Bus adapter device (or IPv4:port for TCP masters)

mqtt:
  host: 192.168.1.100           # Your MQTT broker IP address
  # username: user              # Uncomment if authentication required
  # password: secret

homeassistant:
  enabled: true                 # Set to true for Home Assistant integration
```

Save and exit (Ctrl+O, Ctrl+X).
> [!NOTE]
> Full config options are described [here](#configuration).

### Step 4: Start the container

```bash
docker compose up -d
```

### Step 5: Check the logs

```bash
docker compose logs -f
```

You should see your M-Bus devices being discovered and data published to MQTT.

---

## Configuration

Configuration is stored in a YAML file:

- **Docker:** `data/config/config.yaml` on the host
- **native:** `/etc/libmbus2mqtt/config.yaml`.

### Minimal Configuration

Only two settings are required:

```yaml
mbus:
  device: /dev/ttyUSB0

mqtt:
  host: 192.168.1.100
```

### Full Configuration Reference

```yaml
# M-Bus Interface
mbus:
  device: /dev/ttyUSB0          # REQUIRED - Serial device path OR IPv4:port (TCP master)
                                # Serial examples: /dev/ttyUSB0, /dev/ttyACM0, /dev/ttyAMA0
                                # TCP example: 192.168.1.50:9999 (IPv4 only, no hostnames)
  baudrate: 2400                # M-Bus baudrate (300, 2400, or 9600) - ignored for TCP
  poll_interval: 60             # Seconds between polling cycles
  startup_delay: 5              # Seconds to wait before first poll/scan
  timeout: 5                    # Seconds to wait for device response
  retry_count: 3                # Number of retries on failure
  retry_delay: 1                # Seconds between retries
  autoscan: true                # Scan for devices on startup

# MQTT Broker
mqtt:
  host: 192.168.1.100           # REQUIRED - Broker IP or hostname
  port: 1883                    # Broker port (default: 1883, or 8883 with TLS)
  username:                     # Username (if required)
  password:                     # Password (if required)
  client_id:                    # Client ID (auto-generated if empty)
  keepalive: 60                 # Connection keepalive in seconds
  qos: 1                        # Message quality of service (0, 1, or 2)
  base_topic: libmbus2mqtt      # Base MQTT topic
  tls:                          # See docs/mqtt.md#mqtt-over-tls
    enabled: false              # Enable TLS encryption
    ca_certs:                   # Use specific CA cert (empty/default: system CAs)
    certfile:                   # Client certificate, if the broker requires one (empty - do not use)
    keyfile:                    # Client private key, if not included in certfile
    insecure: false             # true = don't verify the broker certificate (accepts self-signed)

# Home Assistant Integration
homeassistant:
  enabled: false                # Enable Home Assistant MQTT Discovery
  discovery_prefix: homeassistant

# Devices (optional)
# Must be defined if 'mbus' -> 'autoscan' is set to 'false')
# Can be also used as override for specific devices
devices:
  - id: 1                       # M-Bus address (0-254)
    name: "Water Meter Kitchen" # Friendly name
    enabled: true               # Set false to ignore this device
    template:                   # Template filename (skip auto-detect if set)

# Device Availability
availability:
  timeout_polls: 3              # Consecutive failures before marking offline

# Logging
logs:
  level: INFO                   # Log level: DEBUG, INFO, WARNING, ERROR, CRITICAL
  save_to_file: true            # Enable file logging
  file: data/log/libmbus2mqtt.log  # Log file path
  max_size_mb: 10               # Max file size before rotation (1-1000 MB)
  backup_count: 5               # Number of rotated backup files (0-100)
```

All options except `devices` can also be set with environment variables named `LIBMBUS2MQTT_SECTION_OPTION`, e.g. `LIBMBUS2MQTT_MQTT_HOST`. They take precedence over the YAML file; see [Environment Variables](docs/environment-variables.md).

---

## Contributing

Contributions are welcome! Please open an issue or pull request on [GitHub](https://github.com/nilvanis/libmbus2mqtt).

## Support

- [Open an issue](https://github.com/nilvanis/libmbus2mqtt/issues) for bugs or feature requests
- Include your M-Bus XML output when requesting device support
