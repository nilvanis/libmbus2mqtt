"""M-Bus endpoint parsing utilities."""

from __future__ import annotations

import re
import socket
from dataclasses import dataclass
from typing import Literal

EndpointType = Literal["serial", "tcp"]


@dataclass
class MbusEndpoint:
    """Normalized representation of an M-Bus endpoint."""

    type: EndpointType
    device: str
    host: str | None = None
    port: int | None = None


_TCP_PATTERN = re.compile(r"^(?P<ip>(?:\d{1,3}\.){3}\d{1,3}):(?P<port>\d{1,5})$")


def parse_mbus_device(device: str) -> MbusEndpoint:
    """Determine if a device string is serial or TCP (IPv4:port).

    Returns:
        MbusEndpoint describing the connection type. Falls back to ``serial``
        when the input does not strictly match IPv4:port.
    Raises:
        ValueError: if the string looks like IPv4:port but octets/port are out of range.
    """

    match = _TCP_PATTERN.match(device)
    if match:
        ip = match.group("ip")
        port = int(match.group("port"))

        octets = [int(o) for o in ip.split(".")]
        if any(o > 255 for o in octets):
            raise ValueError("Invalid IPv4 address in mbus.device; octets must be 0-255")
        if port < 1 or port > 65535:
            raise ValueError("Invalid TCP port in mbus.device; must be 1-65535")

        return MbusEndpoint(type="tcp", device=device, host=ip, port=port)

    if ":" in device:
        raise ValueError("Only IPv4:port is supported for TCP mbus.device")

    return MbusEndpoint(type="serial", device=device)


def check_tcp_connectivity(host: str, port: int, timeout: float = 2.0) -> bool:
    """Try to establish a TCP connection; return True if reachable."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False
