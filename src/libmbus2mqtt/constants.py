"""Application-wide constants."""

from pathlib import Path

# Application info
APP_NAME = "libmbus2mqtt"
APP_VERSION = "2.0.1"

# Paths
DEFAULT_DATA_DIR = Path("/data")
CONFIG_DIR = DEFAULT_DATA_DIR / "config"
TEMPLATES_DIR = DEFAULT_DATA_DIR / "templates"
DEFAULT_CONFIG_FILE = CONFIG_DIR / "config.yaml"

# M-Bus
MBUS_ID_MIN = 0  # 0 is valid but generates warning (default address)
MBUS_ID_MAX = 254
MBUS_BAUDRATES = [300, 2400, 9600]
MBUS_DEFAULT_BAUDRATE = 2400
MBUS_DEFAULT_TIMEOUT = 5
MBUS_DEFAULT_RETRY_COUNT = 3
MBUS_DEFAULT_RETRY_DELAY = 1
MBUS_DEFAULT_SCAN_TIMEOUT = 1200  # TCP scan with default 4s timeout takes 17-18minutes for full range

# MQTT
MQTT_DEFAULT_PORT = 1883
MQTT_DEFAULT_KEEPALIVE = 60
MQTT_DEFAULT_QOS = 1
MQTT_DEFAULT_BASE_TOPIC = "libmbus2mqtt"

# MQTT Topics (format strings)
TOPIC_DEVICE_STATE = "{base}/device/{device_id}/state"
TOPIC_DEVICE_AVAILABILITY = "{base}/device/{device_id}/availability"
TOPIC_BRIDGE_STATE = "{base}/bridge/state"
TOPIC_COMMAND_RESCAN = "{base}/command/rescan"
TOPIC_COMMAND_LOG_LEVEL = "{base}/command/log_level"
TOPIC_COMMAND_POLL_INTERVAL = "{base}/command/poll_interval"

# Home Assistant
HA_DEFAULT_DISCOVERY_PREFIX = "homeassistant"

# Polling
POLLING_DEFAULT_INTERVAL = 60
POLLING_DEFAULT_STARTUP_DELAY = 5

# Availability
AVAILABILITY_DEFAULT_TIMEOUT_POLLS = 3

# Libmbus
LIBMBUS_REPO = "https://github.com/rscada/libmbus.git"
LIBMBUS_SERIAL_BINARIES = ["mbus-serial-scan", "mbus-serial-request-data"]
LIBMBUS_TCP_BINARIES = ["mbus-tcp-scan", "mbus-tcp-request-data"]
LIBMBUS_BINARIES = LIBMBUS_SERIAL_BINARIES + LIBMBUS_TCP_BINARIES
LIBMBUS_DEFAULT_INSTALL_PATH = Path("/usr/local/bin")
LIBMBUS_BUILD_DIR = Path("/tmp/libmbus-build")

# Systemd service installation
SYSTEMD_SERVICE_NAME = "libmbus2mqtt.service"
SYSTEMD_SERVICE_DIR = Path("/etc/systemd/system")

# Service user/group
SERVICE_USER = "libmbus2mqtt"
SERVICE_GROUP = "dialout"

# Service directories
SERVICE_CONFIG_DIR = Path("/etc/libmbus2mqtt")
SERVICE_DATA_DIR = Path("/var/lib/libmbus2mqtt")

# Logging (fixed format, not user-configurable)
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
LOG_COLORS = {
    "DEBUG": "\033[36m",  # Cyan
    "INFO": "\033[32m",  # Green
    "WARNING": "\033[33m",  # Yellow
    "ERROR": "\033[31m",  # Red
    "CRITICAL": "\033[35m",  # Magenta
}
LOG_RESET = "\033[0m"
LOG_LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

# File logging defaults
LOG_DEFAULT_DIR = DEFAULT_DATA_DIR / "log"
LOG_DEFAULT_FILE = LOG_DEFAULT_DIR / "libmbus2mqtt.log"
LOG_DEFAULT_MAX_SIZE_MB = 10
LOG_DEFAULT_BACKUP_COUNT = 5

# Environment variable prefix
ENV_PREFIX = "LIBMBUS2MQTT"
