"""TTY device utilities."""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import TypedDict

from libmbus2mqtt.logging import get_logger

logger = get_logger("mbus.tty")


class UsbInfo(TypedDict):
    """USB device information."""

    vendor: str
    product: str | None
    manufacturer: str | None


class TtyDeviceInfo(TypedDict):
    """TTY device information."""

    exists: bool
    readable: bool
    writable: bool
    is_tty: bool
    is_busy: bool
    type: str
    driver: str | None
    usb_info: UsbInfo | None


def check_tty_device(device_path: str) -> TtyDeviceInfo:
    """
    Check if TTY device is available and accessible.

    Supports: USB serial, TTL/UART, Serial over Ethernet (socat pts).

    Args:
        device_path: Path to the device (e.g., /dev/ttyUSB0)

    Returns:
        Dictionary with device status and information.
    """
    path = Path(device_path)

    result: TtyDeviceInfo = {
        "exists": False,
        "readable": False,
        "writable": False,
        "is_tty": False,
        "is_busy": False,
        "type": "unknown",
        "driver": None,
        "usb_info": None,
    }

    if not path.exists():
        return result

    result["exists"] = True

    # Check permissions
    result["readable"] = os.access(device_path, os.R_OK)
    result["writable"] = os.access(device_path, os.W_OK)

    # Check if it's a character device (TTY)
    try:
        mode = path.stat().st_mode
        result["is_tty"] = stat.S_ISCHR(mode)
    except OSError:
        pass

    # Determine device type
    result["type"] = _determine_device_type(device_path)

    # Get USB info if applicable
    if result["type"] == "USB Serial":
        result["usb_info"] = _get_usb_info(device_path)
        result["driver"] = _get_driver_name(device_path)

    # Check if device is busy (try to detect lock)
    result["is_busy"] = _check_device_busy(device_path)

    return result


def _determine_device_type(device_path: str) -> str:
    """Determine the type of TTY device."""
    path = Path(device_path)
    name = path.name

    # USB serial devices
    if name.startswith("ttyUSB") or name.startswith("ttyACM"):
        return "USB Serial"

    # PTY (pseudo-terminal) - used by socat, etc.
    if name.startswith("pts") or device_path.startswith("/dev/pts/"):
        return "PTY (Serial over Ethernet / socat)"

    # UART/TTL devices (Raspberry Pi, embedded)
    if name.startswith("ttyAMA") or name.startswith("ttyS") or name.startswith("serial"):
        return "UART/TTL"

    # Other TTY devices
    if name.startswith("tty"):
        return "TTY"

    return "Unknown"


def _get_usb_info(device_path: str) -> UsbInfo | None:
    """Get USB device information."""
    path = Path(device_path)
    name = path.name

    # Find the sysfs path for this device
    sysfs_base = Path("/sys/class/tty") / name

    if not sysfs_base.exists():
        return None

    # Navigate to the USB device info
    try:
        device_link = sysfs_base / "device"
        if not device_link.exists():
            return None

        # Go up the tree to find USB info
        usb_path = device_link.resolve()

        # Look for idVendor and idProduct in parent directories
        for _ in range(5):  # Max 5 levels up
            usb_path = usb_path.parent

            id_vendor_file = usb_path / "idVendor"
            id_product_file = usb_path / "idProduct"

            if id_vendor_file.exists() and id_product_file.exists():
                vendor_id = id_vendor_file.read_text().strip()
                product_id = id_product_file.read_text().strip()

                # Try to get product name
                product_name: str | None = None
                product_file = usb_path / "product"
                if product_file.exists():
                    product_name = product_file.read_text().strip()

                # Try to get manufacturer
                manufacturer: str | None = None
                manufacturer_file = usb_path / "manufacturer"
                if manufacturer_file.exists():
                    manufacturer = manufacturer_file.read_text().strip()

                return {
                    "vendor": f"{vendor_id}:{product_id}",
                    "product": product_name,
                    "manufacturer": manufacturer,
                }

    except (OSError, PermissionError):
        pass

    return None


def _get_driver_name(device_path: str) -> str | None:
    """Get the kernel driver name for a USB serial device."""
    path = Path(device_path)
    name = path.name

    sysfs_path = Path("/sys/class/tty") / name / "device" / "driver"

    try:
        if sysfs_path.exists():
            # The driver is a symlink, get its name
            driver_path = sysfs_path.resolve()
            return driver_path.name
    except (OSError, PermissionError):
        pass

    return None


def _check_device_busy(device_path: str) -> bool:
    """Check if the device appears to be in use."""
    # Check for lock files
    path = Path(device_path)
    name = path.name

    lock_paths = [
        Path(f"/var/lock/LCK..{name}"),
        Path(f"/var/lock/lockdev/LCK..{name}"),
        Path(f"/run/lock/LCK..{name}"),
    ]

    for lock_path in lock_paths:
        if lock_path.exists():
            return True

    return False
