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
- Template system to support different M-Bus device types
- Docker support with pre-compiled libmbus
- Systemd service for native Linux installation

## Table of Contents

- [Requirements](#requirements)
- ⚡[Quick Start with Docker (recommended)](#quick-start-with-docker-recommended)
- [Native Installation](#native-installation)
- [Configuration](#configuration)
- [Running libmbus2mqtt](#running-libmbus2mqtt)
- [Home Assistant Integration](#home-assistant-integration)
- [Device Templates](#device-templates)
- [Hardware Setup](#hardware-setup)
- [Troubleshooting](#troubleshooting)
- [Supported Devices](#supported-devices)

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
- **Python 3.11+** for native installation

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
```

Save and exit (Ctrl+O, Ctrl+X).

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

## Native Installation

For running directly on Linux without Docker.

### Step 1: Install libmbus

libmbus2mqtt can install libmbus for you:

```bash
# Install dependencies first (Debian/Ubuntu)
sudo apt-get install git build-essential libtool autoconf automake

# Clone and install libmbus2mqtt
git clone https://github.com/nilvanis/libmbus2mqtt
cd libmbus2mqtt
pip install .

# Install libmbus
sudo libmbus2mqtt libmbus install
```

Or install libmbus manually - see [libmbus on GitHub](https://github.com/rscada/libmbus).

### Step 2: Create configuration

```bash
# Create config directory
sudo mkdir -p /data/config

# Generate example configuration
libmbus2mqtt config init --config /data/config/config.yaml

# Edit the configuration
sudo nano /data/config/config.yaml
```

### Step 3: Test the connection

```bash
# Check if your M-Bus device is accessible
libmbus2mqtt device-info

# Scan for connected meters
libmbus2mqtt scan
```

### Step 4: Run the daemon

```bash
libmbus2mqtt run
```

### Step 5: Install as a service (optional)

To run libmbus2mqtt automatically at startup:

```bash
sudo libmbus2mqtt install
```

This creates a systemd service that starts on boot. To manage the service:

```bash
# Check status
sudo systemctl status libmbus2mqtt

# View logs
sudo journalctl -u libmbus2mqtt -f

# Stop the service
sudo systemctl stop libmbus2mqtt

# Remove the service
sudo libmbus2mqtt uninstall
```

---

## Configuration

Configuration is stored in a YAML file. By default, libmbus2mqtt looks for `/data/config/config.yaml`.

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
  port: 1883                    # Broker port
  username:                     # Username (if required)
  password:                     # Password (if required)
  client_id:                    # Client ID (auto-generated if empty)
  keepalive: 60                 # Connection keepalive in seconds
  qos: 1                        # Message quality of service (0, 1, or 2)
  base_topic: libmbus2mqtt      # Base MQTT topic

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
    template:                   # Template name (auto-detect if empty)

# Device Availability
availability:
  timeout_polls: 3              # Consecutive failures before marking offline

# Logging
logs:
  level: INFO                   # Log level: DEBUG, INFO, WARNING, ERROR, CRITICAL
  save_to_file: false           # Enable file logging
  file: data/log/libmbus2mqtt.log  # Log file path
  max_size_mb: 10               # Max file size before rotation (1-1000 MB)
  backup_count: 5               # Number of rotated backup files (0-100)
```

### Environment Variables

Environment variables can be used to provide config values (handy in Docker). When both the YAML file and an environment variable set the same field, the **environment variable takes precedence** and the override is logged.\
Env var naming convention is based on config.yaml: `LIBMBUS2MQTT_SECTION_OPTION`. Below is complete list:

```
LIBMBUS2MQTT_MBUS_DEVICE
LIBMBUS2MQTT_MBUS_BAUDRATE
LIBMBUS2MQTT_MBUS_POLL_INTERVAL
LIBMBUS2MQTT_MBUS_STARTUP_DELAY
LIBMBUS2MQTT_MBUS_TIMEOUT
LIBMBUS2MQTT_MBUS_RETRY_COUNT
LIBMBUS2MQTT_MBUS_RETRY_DELAY
LIBMBUS2MQTT_MBUS_AUTOSCAN
LIBMBUS2MQTT_MQTT_HOST
LIBMBUS2MQTT_MQTT_PORT
LIBMBUS2MQTT_MQTT_USERNAME
LIBMBUS2MQTT_MQTT_PASSWORD
LIBMBUS2MQTT_MQTT_CLIENT_ID
LIBMBUS2MQTT_MQTT_KEEPALIVE
LIBMBUS2MQTT_MQTT_QOS
LIBMBUS2MQTT_MQTT_BASE_TOPIC
LIBMBUS2MQTT_HOMEASSISTANT_ENABLED
LIBMBUS2MQTT_HOMEASSISTANT_DISCOVERY_PREFIX
LIBMBUS2MQTT_AVAILABILITY_TIMEOUT_POLLS
LIBMBUS2MQTT_LOGS_LEVEL
LIBMBUS2MQTT_LOGS_SAVE_TO_FILE
LIBMBUS2MQTT_LOGS_FILE
LIBMBUS2MQTT_LOGS_MAX_SIZE_MB
LIBMBUS2MQTT_LOGS_BACKUP_COUNT
```

Docker Compose example with environment variables:

```yaml
services:
  libmbus2mqtt:
    image: nilvanis/libmbus2mqtt:latest
    environment:
      LIBMBUS2MQTT_MBUS_DEVICE: /dev/ttyUSB0
      LIBMBUS2MQTT_MQTT_HOST: 192.168.1.100
      LIBMBUS2MQTT_MQTT_USERNAME: user
      LIBMBUS2MQTT_MQTT_PASSWORD: secret
      LIBMBUS2MQTT_HOMEASSISTANT_ENABLED: "true"
    devices:
      - /dev/ttyUSB0:/dev/ttyUSB0
    volumes:
      - ./data:/data
```

---

## Running libmbus2mqtt

### CLI Commands

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

### Using a Custom Config File

```bash
libmbus2mqtt run --config /path/to/config.yaml
libmbus2mqtt scan --config /path/to/config.yaml
```

---

## Home Assistant Integration

When `homeassistant.enabled` is set to `true`, libmbus2mqtt automatically creates devices and entities in Home Assistant using MQTT Discovery.

### Bridge Device

libmbus2mqtt creates a "Bridge" device in Home Assistant with these entities:

| Entity               | Type   | Description                                          |
| -------------------- | ------ | ---------------------------------------------------- |
| Discovered Devices | Sensor | Number of M-Bus devices found |
| Online Devices | Sensor | Number of devices currently responding |
| Firmware Version | Sensor | libmbus2mqtt version |
| Last Scan | Sensor | When devices were last scanned (disabled by default) |
| Uptime | Sensor | How long the bridge has been running (disabled by default) |
| Last Poll Duration | Sensor | Duration of last polling cycle in ms (disabled by default) |
| Rescan Devices | Button | Trigger a new device scan |
| Log Level | Select | Change logging level (DEBUG, INFO, WARNING, ERROR) |
| Poll Interval | Number | Change polling interval (10-3600 seconds) |

>[!IMPORTANT]
> Settings changed via MQTT (e.g. `Log level`) are changed only for the current **runtime**, meaning it will revert to config.yml setting (or default if not set) after restart of libmbus2mqtt.

### M-Bus Devices

Each discovered M-Bus meter appears as a separate device in Home Assistant, linked to the Bridge device. The entities created depend on:

1. **Device template** - If a template exists for your meter, entities are created with proper names, units, and icons
2. **Generic fallback** - If no template exists, generic sensors are created for each data record

### MQTT Topics

Data is published to these MQTT topics:

```text
libmbus2mqtt/bridge/state          # Bridge availability (online/offline)
libmbus2mqtt/bridge/info           # Bridge status JSON
libmbus2mqtt/device/{id}/state     # Device data JSON
libmbus2mqtt/device/{id}/availability  # Device availability
libmbus2mqtt/command/rescan        # Trigger rescan (send any message)
libmbus2mqtt/command/log_level     # Change log level (DEBUG/INFO/WARNING/ERROR)
libmbus2mqtt/command/poll_interval # Change poll interval (10-3600)
```

---

## Device Templates

Templates define how M-Bus data records are mapped to Home Assistant entities. They provide friendly names, icons, units, and device classes.

### Bundled Templates

libmbus2mqtt includes templates for common devices. Check the [Supported Devices](#supported-devices) section.

### Custom Templates

You can create custom templates for your devices. Place them in `/data/templates/`:

```text
/data/
└── templates/
    ├── index.json              # Maps devices to templates
    └── my_custom_meter.json    # Your template file
```

#### index.json

Maps device information to template files:

```json
{
    "my_custom_meter.json": {
        "Manufacturer": "ACME",
        "ProductName": "Water Meter Pro"
    }
}
```

#### Template File

Defines entities for each data record:

```json
{
    "0": {
        "name": "Serial Number",
        "icon": "mdi:identifier",
        "component": "sensor",
        "value_template": "{{ value_json.serial_number }}",
        "entity_category": "diagnostic"
    },
    "1": {
        "name": "Total Volume",
        "icon": "mdi:water",
        "component": "sensor",
        "device_class": "water",
        "state_class": "total_increasing",
        "unit_of_measurement": "m³",
        "value_template": "{{ value_json.volume }}"
    },
    "custom-daily": {
        "name": "Daily Usage",
        "icon": "mdi:water-outline",
        "component": "sensor",
        "unit_of_measurement": "L",
        "value_template": "{{ value_json.daily_usage }}"
    }
}
```

The numbers (`"0"`, `"1"`, etc.) correspond to `<DataRecord id="X">` in the M-Bus XML output. You can also create additional, custom sensors. Every custom sensor JSON section name must be preceded with `custom-`. All section names must be unique.
Since custom sensors does not have it's own DataRecord in libmbus xml output, value must be derived from other data.
Common use case is creating dedicated sensors from data in Manufacturer Specific field value.

Template lookup order:
- libmbus2mqtt first checks `/data/templates/index.json` for a matching entry and template file.
- If no match is found in the user index, it falls back to the bundled index/templates.
This lets you add templates without blocking built-in ones; if you want to override a built-in, add a matching entry to your user index and provide the file in `/data/templates/`.

### Getting Your Device's Data Records

To see what data your meter provides, run:

```bash
# Using libmbus2mqtt
libmbus2mqtt scan

# Or directly with libmbus
mbus-serial-request-data -b 2400 /dev/ttyUSB0 1
```

This shows the XML output with all data records. Use this to create a custom template.

Need help? Open an [issue](https://github.com/nilvanis/libmbus2mqtt/issues) with your XML output, and we can help create a template.

---

## Hardware Setup

### Raspberry Pi with TTL-to-M-Bus Converter

**Important: Disconnect all power before wiring!**

#### Step 1: Enable UART

```bash
sudo raspi-config
```

Navigate to: `3 Interface Options` → `Serial Port` → `No` (login shell) → `Yes` (hardware enabled)

Reboot the Pi.

#### Step 2: Connect the Adapter

Connect the TTL-to-M-Bus adapter to the Raspberry Pi GPIO:

| Raspberry Pi | TTL-to-M-Bus |
|--------------|--------------|
| Pin 2 (5V)   | TTLVCC       |
| Pin 4 (5V)   | VIN          |
| Pin 6 (GND)  | GND          |
| Pin 8 (TX)   | TXD          |
| Pin 10 (RX)  | RXD          |

<img src="../assets/libmbus2mqtt_rpi_converter.jpg" width="550">

See [pinout.xyz](https://pinout.xyz/) for GPIO pin locations.

#### Step 3: Verify

After powering on, the device should be available at `/dev/ttyAMA0` or `/dev/serial0`.

### USB-to-M-Bus Adapter

Simply plug in the USB adapter. It will typically appear as `/dev/ttyUSB0` or `/dev/ttyACM0`.

Check with:

```bash
ls -l /dev/ttyUSB* /dev/ttyACM*
```

## IPv4 TCP using ser2net
You can run libmbus2mqtt on one device and access M-Bus Master connected to another one. Below is an example how to configure that:

#### Step 1: Connect M-Bus Master to a linux device
Use the information above and note the device path.

#### Step 2: Install and configure ser2net
```cli
sudo apt update && sudo apt install ser2net -y
sudo nano /etc/ser2net.yaml
```
Remove existing ser2net config if not used.
Create new entry for your M-Bus Master (example for Raspberry Pi UART):
```
connection: &uart0
  accepter: tcp(nodelay=true),0.0.0.0,4001
  enable: on
  options:
    kickolduser: true
    chardelay: false
  connector:  serialdev,/dev/ttyAMA0,2400e81,local
```

- `4001` is the TCP port number over which your M-Bus Master will be available.
- `0.0.0.0` means that the ser2net will open port on all IP interfaces configured on the linux host. You can specify a single IP here if needed.
- `/dev/ttyAMA0` is the M-Bus master device path
- `2400e81` - serial settings:
  - speed: `2400` baud
  - parity: `e` (even)
  - data bits: `8`
  - stop bits: `1`

Start the ser2net service:
```
sudo systemctl enable ser2net
sudo systemctl start ser2net
```

You might also need to open firewall if used (inbound TCP/4001)

#### Step 3: Configure libmbus2mqtt
In libmbus2mqtt `config.yaml` file you just need to set mbus.device to IP:4001, e.g.:
```yaml
mbus:
  device: '192.168.1.50:4001'
```

> [!IMPORTANT]
> M-Bus scan over TCP can take up to 20 minutes! Currently it should take around 5 minutes if using Docker.

---

## Troubleshooting

### Permission Denied on Serial Device

Add your user to the `dialout` group:

```bash
sudo usermod -aG dialout $USER
```

Log out and back in for the change to take effect.

### No Devices Found

1. **Check wiring** - Ensure M-Bus devices are properly connected
2. **Check baudrate** - Most M-Bus devices use 2400, but some use 300 or 9600
3. **Test with libmbus directly**:

   ```bash
   mbus-serial-scan -b 2400 /dev/ttyUSB0
   ```

4. **Check power** - M-Bus devices need power from the M-Bus master

### Device Shows Offline

- Check if the device is physically connected
- Increase `availability.timeout_polls` in config
- Check for loose wiring

### Home Assistant Doesn't Show Devices

1. Verify `homeassistant.enabled: true` in config
2. Check MQTT broker connection
3. Verify `discovery_prefix` matches Home Assistant (default: `homeassistant`)
4. Check Home Assistant MQTT integration is enabled
5. Check mosquitto addon logs

### View Logs

```bash
# Docker
docker compose logs -f libmbus2mqtt

# Systemd service
sudo journalctl -u libmbus2mqtt -f
```

You can set log level to DEBUG temporarily in Home Assistant MQTT device "libmbus2mqtt Bridge".\
You can also set the log level permanently using either:
- config.yaml `log.level` option
- `LIBMBUS2MQTT_LOGS_LEVEL` env variable

### Persistent Log Files

Enable file logging in your configuration:

```yaml
logs:
  save_to_file: true
  file: data/log/libmbus2mqtt.log  # Log files will be here
```

Log files are automatically rotated when they reach `max_size_mb` (default: 10 MB). Old files are kept up to `backup_count` (default: 5).

> [!NOTE]
> Log level changes via MQTT (`libmbus2mqtt/command/log_level`) are not persisted - they reset to the config value on restart. To permanently change the log level, edit `logs.level` in your config file.
> Also, make sure the data/ directory is writable by libmbus2mqtt user if using Docker

---

## Supported Devices

libmbus2mqtt includes templates for these devices:

### Itron Cyble M-Bus
![Itron Cyble M-Bus](../assets/itron-cyble-mbus.jpg?raw=true)\
Data sheet: https://se.itron.com/o/commerce-media/accounts/-1/attachments/3809944

### APATOR APT-MBUS-NA-1
![APATOR APT-MBUS-NA-1](../assets/apt-mbus-na-1.jpg?raw=true)\
Data sheet: https://api.apator.com/uploads/oferta/woda-i-cieplo/systemy/przewodowy/apt-mbus-na/apt-mbus-na-1-catalogue.pdf

### Kamstrup Multical 401
<img src="../assets/kamstrup-multical-401.jpg?raw-true" width="550">
Data Sheet: https://documentation.kamstrup.com/docs/MULTICAL_401/en-GB/Data_sheet/CONTF9A902FD213B4A1BB4F5122E640B3AB7/

### B METERS FRM-MB1
<img src="../assets/bmeters-rfm-bm1.jpg?raw-true" width="550">
Data Sheet: https://www.bmeters.com/wp-content/uploads/2023/07/RFM-MB1_v3.2.pdf

### ZENNER EDC Communication Module with M-Bus and Pulse Output
<img src="../assets/zenner-edc-mb-p.jpg?raw-true" width="550">
Data Sheet: https://pim.zenner.com/wp-content/uploads/documents/data_sheets/AMR_technology/EN/DB_ST_EDC-MODUL_MB-Puls_EN.pdf

### Other Devices

If your device isn't listed, libmbus2mqtt should still work - it creates generic sensors for all data records. For a better experience, you can [create a custom template](#custom-templates) or [request one](https://github.com/nilvanis/libmbus2mqtt/issues).

---

## Contributing

Contributions are welcome! Please open an issue or pull request on [GitHub](https://github.com/nilvanis/libmbus2mqtt).

## Support

- [Open an issue](https://github.com/nilvanis/libmbus2mqtt/issues) for bugs or feature requests
- Include your M-Bus XML output when requesting device support
