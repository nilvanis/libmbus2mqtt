"""Exercise a built image against a real MQTT broker and a simulated M-Bus meter.

Requires Docker. All containers, networks, and bind mounts are temporary; no
physical serial device or production broker is used.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
import sys
import time
import uuid
import xml.etree.ElementTree as ET
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory


def docker(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(["docker", *args], text=True, capture_output=True, timeout=90)
    if check and result.returncode:
        raise RuntimeError(f"docker {' '.join(args)} failed:\n{result.stdout}\n{result.stderr}")
    return result


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: smoke_container.py <BUILT_IMAGE>")
    image = sys.argv[1]
    broker_image = "eclipse-mosquitto:2.0.22"
    fixture = Path(__file__).resolve().parent.parent / "tests/fixtures/apator_apt-mbus-na-1.xml"
    xml = ET.fromstring(fixture.read_text())
    meter_id = xml.findtext("SlaveInformation/Id")
    record_value = xml.findtext("DataRecord[@id='0']/Value")
    assert meter_id is not None and record_value is not None
    name = f"libmbus2mqtt-smoke-{uuid.uuid4().hex[:12]}"
    broker, daemon = f"{name}-broker", f"{name}-daemon"

    docker("pull", broker_image)
    with TemporaryDirectory(prefix="libmbus2mqtt-container-") as directory:
        work = Path(directory)
        work.chmod(0o755)
        data = work / "data"
        templates = data / "templates"
        templates.mkdir(parents=True)
        data.chmod(0o777)
        # Keep test-created files removable by the host after the container exits.
        (data / "log").mkdir(mode=0o777)
        (data / "log").chmod(0o777)
        (data / "config").mkdir()
        shutil.copyfile(fixture, work / "payload.xml")
        adapter = work / "mbus-serial-request-data"
        adapter.write_text("#!/bin/sh\ncat /smoke/payload.xml\n")
        adapter.chmod(0o755)
        (work / "mosquitto.conf").write_text(
            "listener 1883\nallow_anonymous true\npersistence false\nlog_dest stdout\n"
        )
        (templates / "index.json").write_text(
            json.dumps(
                {"smoke.json": {"Manufacturer": "APA", "ProductName": None, "DataRecordCount": 12}}
            )
        )
        (templates / "smoke.json").write_text(
            json.dumps(
                {
                    str(i): {
                        "name": f"Smoke {i}",
                        "component": "sensor",
                        "value_template": "{{ value_json.record_" + str(i) + " }}",
                    }
                    for i in range(12)
                }
            )
        )
        (data / "config/config.yaml").write_text("""\
mbus:
  device: /dev/simulated-mbus
  autoscan: false
  startup_delay: 0
  poll_interval: 60
  retry_count: 0
mqtt:
  host: broker
homeassistant:
  enabled: true
devices:
  - id: 1
""")
        try:
            # Verify that the actual C tools can load their runtime libraries.
            docker(
                "run",
                "--rm",
                "--entrypoint",
                "python",
                image,
                "-c",
                """
import os, subprocess
assert os.geteuid() != 0, 'Container must run as a non-root user'
assert 'LIBMBUS2MQTT_DATA_DIR' not in os.environ
assert 'LIBMBUS2MQTT_CONFIG' not in os.environ
for name in ['mbus-serial-scan', 'mbus-serial-request-data', 'mbus-tcp-scan', 'mbus-tcp-request-data']:
    result = subprocess.run([name], capture_output=True, timeout=5)
    assert result.returncode in (0, 1), (name, result.stderr)
""",
            )
            docker("network", "create", name)
            docker(
                "run",
                "--detach",
                "--name",
                broker,
                "--network",
                name,
                "--network-alias",
                "broker",
                "--user",
                "1883:1883",
                "--mount",
                f"type=bind,source={work / 'mosquitto.conf'},target=/mosquitto/config/mosquitto.conf,readonly",
                broker_image,
            )
            deadline = time.monotonic() + 20
            while True:
                probe = docker(
                    "exec", broker, "mosquitto_pub", "-t", "smoke/probe", "-m", "ready", check=False
                )
                if probe.returncode == 0:
                    break
                if time.monotonic() >= deadline:
                    raise RuntimeError("MQTT smoke broker did not start")
                time.sleep(0.2)
            docker(
                "run",
                "--detach",
                "--name",
                daemon,
                "--network",
                name,
                "--read-only",
                "--cap-drop",
                "ALL",
                "--env",
                "PYTHONDONTWRITEBYTECODE=1",
                "--mount",
                f"type=bind,source={work},target=/smoke,readonly",
                "--mount",
                f"type=bind,source={data},target=/data",
                "--mount",
                f"type=bind,source={adapter},target=/usr/local/bin/mbus-serial-request-data,readonly",
                image,
            )

            def retained(topic: str) -> str:
                return docker(
                    "exec", broker, "mosquitto_sub", "-t", topic, "-C", "1", "-W", "20"
                ).stdout.strip()

            state = json.loads(retained(f"libmbus2mqtt/device/{meter_id}/state"))
            assert state["record_0"] == record_value, state
            assert retained(f"libmbus2mqtt/device/{meter_id}/availability") == "online"
            assert json.loads(retained("homeassistant/sensor/+/config"))["device"]["identifiers"]
            assert retained("libmbus2mqtt/bridge/state") == "online"
            for level in ["DEBUG", "INFO"]:
                docker(
                    "exec",
                    broker,
                    "mosquitto_pub",
                    "-t",
                    "libmbus2mqtt/command/log_level",
                    "-m",
                    level,
                )
                deadline = time.monotonic() + 5
                while json.loads(retained("libmbus2mqtt/bridge/info"))["log_level"] != level:
                    if time.monotonic() >= deadline:
                        raise AssertionError(f"Log level {level} was not confirmed immediately")
                    time.sleep(0.1)
            with closing(
                sqlite3.connect(f"file:{data / 'libmbus2mqtt.db'}?mode=ro", uri=True)
            ) as conn:
                assert conn.execute("SELECT COUNT(*) FROM device_snapshot").fetchone()[0] == 1
            docker("stop", "--time", "10", daemon)
            assert (
                docker("inspect", "--format", "{{.State.ExitCode}}", daemon).stdout.strip() == "0"
            )
            assert retained("libmbus2mqtt/bridge/state") == "offline"
            log_file = data / "log/libmbus2mqtt.log"
            assert log_file.is_file(), "Default file logging must create /data/log/libmbus2mqtt.log"
            assert "Setting log level to DEBUG" in log_file.read_text()
            print("Container startup, /data storage, file logs, templates, MQTT, and shutdown: OK")
        except Exception:
            print(docker("logs", daemon, check=False).stdout, file=sys.stderr)
            print(docker("logs", broker, check=False).stderr, file=sys.stderr)
            raise
        finally:
            docker("rm", "--force", daemon, broker, check=False)
            docker("network", "rm", name, check=False)


if __name__ == "__main__":
    main()
