"""Install a built wheel outside the checkout and exercise its CLI and resources."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: smoke_package.py dist/libmbus2mqtt-<VERSION>-py3-none-any.whl")
    wheel = Path(sys.argv[1]).resolve(strict=True)
    with TemporaryDirectory(prefix="libmbus2mqtt-package-") as directory:
        work = Path(directory)
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        env.pop("PYTHONHOME", None)
        for key in list(env):
            if key.startswith("LIBMBUS2MQTT_"):
                del env[key]
        python = work / "venv/bin/python"
        cli = work / "venv/bin/libmbus2mqtt"
        subprocess.run(["uv", "venv", "--python", sys.executable, str(work / "venv")], check=True)
        requirements = work / "requirements.txt"
        subprocess.run(
            [
                "uv",
                "export",
                "--locked",
                "--no-dev",
                "--no-emit-project",
                "--format",
                "requirements-txt",
                "--output-file",
                str(requirements),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        subprocess.run(
            [
                "uv",
                "pip",
                "install",
                "--python",
                str(python),
                "--require-hashes",
                "-r",
                str(requirements),
            ],
            check=True,
        )
        subprocess.run(
            ["uv", "pip", "install", "--python", str(python), "--no-deps", str(wheel)], check=True
        )

        def run(*args: str) -> None:
            subprocess.run(list(args), cwd=work, env=env, check=True)

        run(str(cli), "--version")
        run(str(cli), "--help")
        run(str(cli), "run", "--help")
        config = work / "config.yaml"
        run(str(cli), "config", "init", "--config", str(config))
        run(str(cli), "config", "validate", "--config", str(config))
        run(str(cli), "install", "--dry-run", "--yes")
        run(
            str(python),
            "-c",
            """
from importlib.metadata import version
from importlib.resources import files
from logging.handlers import RotatingFileHandler
from pathlib import Path
from unittest.mock import patch
import logging
import libmbus2mqtt
from libmbus2mqtt.cli import run
from libmbus2mqtt.config import AppConfig
from libmbus2mqtt.constants import DEFAULT_CONFIG_FILE, DEFAULT_DATA_DIR
from libmbus2mqtt.installer import get_libmbus_source, get_libmbus_version, get_service_content
from libmbus2mqtt.main import Daemon
from libmbus2mqtt.templates import load_template

assert version('libmbus2mqtt') == libmbus2mqtt.__version__
assert Path(libmbus2mqtt.__file__).is_relative_to(Path('venv').resolve())
assert 'StateDirectory=libmbus2mqtt' in get_service_content()
assert '--data-dir /var/lib/libmbus2mqtt' in get_service_content()
assert 'LIBMBUS2MQTT_DATA_DIR' not in get_service_content()
assert DEFAULT_CONFIG_FILE == Path('/etc/libmbus2mqtt/config.yaml')
assert DEFAULT_DATA_DIR == Path('/var/lib/libmbus2mqtt')
assert len(get_libmbus_source()[1]) == 40
assert get_libmbus_version() == '0.10.4'
assert files('libmbus2mqtt').joinpath('resources/libmbus-tcp-timeout.patch').is_file()
assert load_template('apt-mbus-na-1.json') is not None
config = AppConfig.load('config.yaml')
data_dir = Path('runtime')
with patch('libmbus2mqtt.main.run_daemon') as run_daemon:
    run(config=Path('config.yaml'), data_dir=data_dir)
    assert run_daemon.call_args.kwargs['data_dir'] == data_dir
daemon = Daemon(config, data_dir=data_dir)
daemon._init_state_store()
assert (data_dir / 'libmbus2mqtt.db').is_file()
assert (data_dir / 'log/libmbus2mqtt.log').is_file()
handler = next(h for h in logging.getLogger().handlers if isinstance(h, RotatingFileHandler))
assert handler.maxBytes == 10 * 1024 * 1024 and handler.backupCount == 5
print('Installed wheel, CLI, resources, runtime storage, and file logging: OK')
""",
        )


if __name__ == "__main__":
    main()
