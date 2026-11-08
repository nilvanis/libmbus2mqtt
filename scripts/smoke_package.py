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
        env["LIBMBUS2MQTT_DATA_DIR"] = str(work / "runtime")
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
from pathlib import Path
import os
import libmbus2mqtt
from libmbus2mqtt.config import AppConfig
from libmbus2mqtt.installer import get_libmbus_source, get_service_content
from libmbus2mqtt.state import StateStore
from libmbus2mqtt.templates import load_template

assert version('libmbus2mqtt') == libmbus2mqtt.__version__
assert Path(libmbus2mqtt.__file__).is_relative_to(Path('venv').resolve())
assert 'StateDirectory=libmbus2mqtt' in get_service_content()
assert len(get_libmbus_source()[1]) == 40
assert files('libmbus2mqtt').joinpath('resources/libmbus-tcp-timeout.patch').is_file()
assert load_template('apt-mbus-na-1.json') is not None
config = AppConfig.load('config.yaml')
assert config.data_dir == Path(os.environ['LIBMBUS2MQTT_DATA_DIR'])
store = StateStore(config.db_path)
assert store.db_path.is_file()
assert config.templates_dir == config.data_dir / 'templates'
assert config.log_file == config.data_dir / 'log/libmbus2mqtt.log'
print('Installed wheel, CLI, resources, and runtime paths: OK')
""",
        )


if __name__ == "__main__":
    main()
