"""Exercise a built image against a real MQTT broker and a simulated M-Bus meter.

Requires Docker. All containers, networks, and bind mounts are temporary; no
physical serial device or production broker is used.

Scenarios:
- default: the entrypoint starts as root, takes over a host-owned /data (including
  files left by the pre-2.2 uid 999) for PUID/PGID and drops privileges;
- hardened: `--user` with a read-only root filesystem and no capabilities, also
  checking that SIGTERM ends the startup delay immediately;
- unwritable /data: startup fails with an actionable message instead of a traceback;
- MQTT over TLS with a client certificate (mutual TLS), and a clear error when the
  broker certificate is signed by an unknown CA;
- `insecure: true` against a self-signed broker certificate for another host name.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import stat
import subprocess
import sys
import time
import uuid
import xml.etree.ElementTree as ET
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

CONFIG = """\
mbus:
  device: /dev/simulated-mbus
  autoscan: false
  startup_delay: {startup_delay}
  poll_interval: 60
  retry_count: 0
mqtt:
  host: broker
homeassistant:
  enabled: true
devices:
  - id: 1
"""


def docker(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(["docker", *args], text=True, capture_output=True, timeout=90)
    if check and result.returncode:
        raise RuntimeError(f"docker {' '.join(args)} failed:\n{result.stdout}\n{result.stderr}")
    return result


def process_status(container: str) -> dict[str, str]:
    """/proc/1/status of the container: the daemon itself after the entrypoint exec."""
    lines = docker("exec", container, "cat", "/proc/1/status").stdout.splitlines()
    return dict(line.split(":\t", 1) for line in lines if ":\t" in line)


def assert_unprivileged(container: str, uid: int, gid: int) -> dict[str, str]:
    status = process_status(container)
    assert status["Uid"].split() == [str(uid)] * 4, status["Uid"]
    assert status["Gid"].split() == [str(gid)] * 4, status["Gid"]
    assert status["NoNewPrivs"].strip() == "1", status["NoNewPrivs"]
    assert int(status["CapEff"], 16) == 0, status["CapEff"]
    return status


def make_certificates(directory: Path) -> None:
    """Throwaway CA, broker certificate for the host name "broker", client cert, other CA,
    and a self-signed broker certificate for a name other than "broker"."""
    directory.mkdir()

    def openssl(*args: str) -> None:
        subprocess.run(["openssl", *args], cwd=directory, check=True, capture_output=True)

    for ca in ("ca", "wrong-ca"):
        openssl(
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "2",
            "-keyout",
            f"{ca}.key",
            "-out",
            f"{ca}.crt",
            "-subj",
            f"/CN=smoke {ca}",
        )
    (directory / "server.ext").write_text("subjectAltName=DNS:broker\n")
    for serial, (leaf, subject) in enumerate(
        (("server", "/CN=broker"), ("client", "/CN=libmbus2mqtt")), start=1
    ):
        openssl(
            "req",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            f"{leaf}.key",
            "-out",
            f"{leaf}.csr",
            "-subj",
            subject,
        )
        extra = ["-extfile", "server.ext"] if leaf == "server" else []
        openssl(
            "x509",
            "-req",
            "-in",
            f"{leaf}.csr",
            "-CA",
            "ca.crt",
            "-CAkey",
            "ca.key",
            "-set_serial",
            str(serial),
            "-days",
            "2",
            "-out",
            f"{leaf}.crt",
            *extra,
        )
    openssl(
        "req",
        "-x509",
        "-newkey",
        "rsa:2048",
        "-nodes",
        "-days",
        "2",
        "-keyout",
        "self-signed.key",
        "-out",
        "self-signed.crt",
        "-subj",
        "/CN=mosquitto.invalid",
    )
    directory.chmod(0o755)
    # The broker runs as uid 1883 and must read its keys; these are test-only keys.
    for key in ("server.key", "self-signed.key"):
        (directory / key).chmod(0o644)


def wait_for_log(container: str, text: str, timeout: float = 30) -> None:
    deadline = time.monotonic() + timeout
    while True:
        logs = docker("logs", container, check=False)
        if text in logs.stdout:
            return
        if time.monotonic() >= deadline:
            raise AssertionError(f"{container} did not log {text!r}:\n{logs.stdout}{logs.stderr}")
        time.sleep(0.2)


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
    broker, daemon, hardened = f"{name}-broker", f"{name}-daemon", f"{name}-hardened"
    tls_daemon, insecure_daemon = f"{name}-tls", f"{name}-insecure"
    uid, gid = os.getuid(), os.getgid()
    serial = Path("/dev/ttyS0")
    serial_gid = serial.stat().st_gid if serial.is_char_device() else None

    docker("pull", broker_image)
    with TemporaryDirectory(prefix="libmbus2mqtt-container-") as directory:
        work = Path(directory)
        work.chmod(0o755)
        # Created like the README tells users to: by the host user, mode 0755.
        data = work / "data"
        templates = data / "templates"
        templates.mkdir(parents=True)
        (data / "config").mkdir()
        (data / "log").mkdir()
        unwritable = work / "unwritable"
        unwritable.mkdir()
        shutil.copyfile(fixture, work / "payload.xml")
        adapter = work / "mbus-serial-request-data"
        adapter.write_text("#!/bin/sh\ncat /smoke/payload.xml\n")
        adapter.chmod(0o755)
        certs = work / "certs"
        make_certificates(certs)
        tls_data = work / "tls-data"
        tls_data.mkdir()
        insecure_data = work / "insecure-data"
        insecure_data.mkdir()
        (work / "mosquitto.conf").write_text(
            "listener 1883\nallow_anonymous true\npersistence false\nlog_dest stdout\n"
            "listener 8883\ncafile /mosquitto/certs/ca.crt\n"
            "certfile /mosquitto/certs/server.crt\nkeyfile /mosquitto/certs/server.key\n"
            "require_certificate true\n"
            "listener 8884\ncertfile /mosquitto/certs/self-signed.crt\n"
            "keyfile /mosquitto/certs/self-signed.key\n"
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
        (data / "config/config.yaml").write_text(CONFIG.format(startup_delay=0))
        (work / "config-delay.yaml").write_text(CONFIG.format(startup_delay=300))
        # No port: TLS defaults to 8883, where the broker requires a client certificate.
        (work / "config-tls.yaml").write_text(
            CONFIG.format(startup_delay=0).replace(
                "mqtt:\n  host: broker\n",
                "mqtt:\n  host: broker\n  base_topic: tlssmoke\n  tls:\n    enabled: true\n"
                "    ca_certs: /smoke/certs/ca.crt\n    certfile: /smoke/certs/client.crt\n"
                "    keyfile: /smoke/certs/client.key\n",
            )
        )
        # Self-signed certificate for another name, no CA given: only insecure connects.
        (work / "config-insecure.yaml").write_text(
            CONFIG.format(startup_delay=0).replace(
                "mqtt:\n  host: broker\n",
                "mqtt:\n  host: broker\n  port: 8884\n  base_topic: insecuresmoke\n"
                "  tls:\n    enabled: true\n    insecure: true\n",
            )
        )

        def as_root(*command: str) -> None:
            docker(
                "run",
                "--rm",
                "--user",
                "0",
                "--entrypoint",
                command[0],
                "--mount",
                f"type=bind,source={data},target=/data",
                image,
                *command[1:],
            )

        common = [
            "--network",
            name,
            "--env",
            "PYTHONDONTWRITEBYTECODE=1",
            "--mount",
            f"type=bind,source={work},target=/smoke,readonly",
            "--mount",
            f"type=bind,source={adapter},target=/usr/local/bin/mbus-serial-request-data,readonly",
        ]
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
# CLI defaults are the native paths; the image redirects every command to /data.
assert os.environ['LIBMBUS2MQTT_DATA_DIR'] == '/data'
assert os.environ['LIBMBUS2MQTT_CONFIG'] == '/data/config/config.yaml'
for name in ['mbus-serial-scan', 'mbus-serial-request-data', 'mbus-tcp-scan', 'mbus-tcp-request-data']:
    result = subprocess.run([name], capture_output=True, timeout=5)
    assert result.returncode in (0, 1), (name, result.stderr)
""",
            )
            # Leftovers of a pre-2.2 installation, which ran as uid 999.
            (data / "log/libmbus2mqtt.log").write_text("old log\n")
            as_root("chown", "-R", "999:999", "/data/log")

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
                "--mount",
                f"type=bind,source={certs},target=/mosquitto/certs,readonly",
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

            # Default mode: no --user, ownership handed to PUID/PGID by the entrypoint.
            device = ["--device", f"{serial}:/dev/ttyUSB0"] if serial_gid is not None else []
            docker(
                "run",
                "--detach",
                "--name",
                daemon,
                *common,
                "--env",
                f"PUID={uid}",
                "--env",
                f"PGID={gid}",
                *device,
                "--mount",
                f"type=bind,source={data},target=/data",
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
            status = assert_unprivileged(daemon, uid, gid)
            if serial_gid is not None and serial_gid not in (0, 5, gid):
                assert str(serial_gid) in status["Groups"].split(), status["Groups"]
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
            log_text = log_file.read_text()
            assert log_text.startswith("old log\n"), "Logs from uid 999 must stay appendable"
            assert "Setting log level to DEBUG" in log_text
            for path in [data, *data.rglob("*")]:
                st = path.lstat()
                assert (st.st_uid, st.st_gid) == (uid, gid), f"{path} not owned by {uid}:{gid}"
                assert not stat.S_IMODE(st.st_mode) & 0o007, f"{path} is accessible to others"

            # One-off commands find /data/config/config.yaml without any flags.
            validated = docker(
                "run",
                "--rm",
                "--env",
                f"PUID={uid}",
                "--env",
                f"PGID={gid}",
                "--mount",
                f"type=bind,source={data},target=/data",
                image,
                "config",
                "validate",
            )
            assert "Configuration is valid: /data/config/config.yaml" in validated.stdout, (
                validated.stdout
            )

            # Hardened mode: never root, read-only rootfs, no capabilities.
            docker(
                "run",
                "--detach",
                "--name",
                hardened,
                *common,
                "--user",
                f"{uid}:{gid}",
                "--read-only",
                "--cap-drop",
                "ALL",
                "--mount",
                f"type=bind,source={data},target=/data",
                image,
                "run",
                "--config",
                "/smoke/config-delay.yaml",
                "--data-dir",
                "/data",
            )
            wait_for_log(hardened, "Waiting 300s before first poll")
            assert_unprivileged(hardened, uid, gid)
            started = time.monotonic()
            docker("stop", "--time", "10", hardened)
            assert time.monotonic() - started < 5, "SIGTERM must end the startup delay at once"
            assert (
                docker("inspect", "--format", "{{.State.ExitCode}}", hardened).stdout.strip() == "0"
            )

            # A /data the process cannot write: one clear message, no traceback.
            failed = docker(
                "run",
                "--rm",
                *common,
                "--user",
                "4242:4242",
                "--mount",
                f"type=bind,source={unwritable},target=/data",
                image,
                "run",
                "--config",
                "/smoke/config-delay.yaml",
                "--data-dir",
                "/data",
                check=False,
            )
            output = failed.stdout + failed.stderr
            assert failed.returncode == 1, output
            assert "Data directory /data" in output and "is not writable" in output, output
            assert "uid=4242" in output, output
            assert "Traceback" not in output, output

            # MQTT over TLS with a client certificate; the config path comes from the env.
            tls_run = [
                *common,
                "--env",
                f"PUID={uid}",
                "--env",
                f"PGID={gid}",
                "--env",
                "LIBMBUS2MQTT_CONFIG=/smoke/config-tls.yaml",
                "--mount",
                f"type=bind,source={tls_data},target=/data",
            ]
            docker("run", "--detach", "--name", tls_daemon, *tls_run, image)
            # No user templates here: the bundled Apator template maps record 0.
            state = json.loads(retained(f"tlssmoke/device/{meter_id}/state"))
            assert state["fabrication_number"] == record_value, state
            wait_for_log(tls_daemon, "MQTT over TLS (CA: /smoke/certs/ca.crt")
            docker("stop", "--time", "10", tls_daemon)

            # A broker certificate from an unknown CA: a clear error, no traceback.
            failed = docker(
                "run",
                "--rm",
                *tls_run,
                "--env",
                "LIBMBUS2MQTT_MQTT_TLS_CA_CERTS=/smoke/certs/wrong-ca.crt",
                image,
                check=False,
            )
            output = failed.stdout + failed.stderr
            assert failed.returncode == 1, output
            assert "TLS connection to broker:8883 failed" in output, output
            assert "certificate verify failed" in output, output
            assert "Traceback" not in output, output

            # insecure: true accepts a self-signed certificate issued for another name.
            docker(
                "run",
                "--detach",
                "--name",
                insecure_daemon,
                *common,
                "--env",
                f"PUID={uid}",
                "--env",
                f"PGID={gid}",
                "--env",
                "LIBMBUS2MQTT_CONFIG=/smoke/config-insecure.yaml",
                "--mount",
                f"type=bind,source={insecure_data},target=/data",
                image,
            )
            state = json.loads(retained(f"insecuresmoke/device/{meter_id}/state"))
            assert state["fabrication_number"] == record_value, state
            wait_for_log(insecure_daemon, "without verifying the broker certificate")
            docker("stop", "--time", "10", insecure_daemon)
            print(
                "Container ownership/privilege drop, hardened mode, startup checks, "
                "/data storage, file logs, templates, MQTT, MQTT over TLS (verified and insecure), "
                "and shutdown: OK"
            )
        except Exception:
            for container in (daemon, hardened, tls_daemon, insecure_daemon):
                logs = docker("logs", container, check=False)
                print(logs.stdout, logs.stderr, file=sys.stderr)
            print(docker("logs", broker, check=False).stderr, file=sys.stderr)
            raise
        finally:
            docker(
                "rm", "--force", daemon, hardened, tls_daemon, insecure_daemon, broker, check=False
            )
            docker("network", "rm", name, check=False)
            # Hand anything a failed run left behind back to the host user for cleanup.
            docker(
                "run",
                "--rm",
                "--user",
                "0",
                "--entrypoint",
                "chown",
                "--mount",
                f"type=bind,source={data},target=/data",
                image,
                "-R",
                f"{uid}:{gid}",
                "/data",
                check=False,
            )


if __name__ == "__main__":
    main()
