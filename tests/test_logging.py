"""File creation, runtime level changes, and actual log rotation."""

import logging
from collections.abc import Iterator
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pytest

from libmbus2mqtt.config import LogsConfig
from libmbus2mqtt.logging import set_log_level, setup_logging


@pytest.fixture
def isolated_logging() -> Iterator[None]:
    root = logging.getLogger()
    handlers = root.handlers[:]
    loggers = [
        root,
        *(logging.getLogger(name) for name in ("libmbus2mqtt", "paho.mqtt", "urllib3")),
    ]
    levels = [logger.level for logger in loggers]
    try:
        yield
    finally:
        for handler in root.handlers:
            if handler not in handlers:
                handler.close()
        root.handlers[:] = handlers
        for logger, level in zip(loggers, levels, strict=True):
            logger.setLevel(level)


@pytest.mark.usefixtures("isolated_logging")
@pytest.mark.parametrize("custom_file", [False, True])
def test_default_file_logging_follows_runtime_level_changes(
    tmp_path: Path, custom_file: bool
) -> None:
    default_file = tmp_path / "runtime/log/libmbus2mqtt.log"
    explicit_file = tmp_path / "custom/bridge.log" if custom_file else None
    log_file = explicit_file or default_file
    setup_logging(
        logs_config=LogsConfig(file=explicit_file), default_log_file=default_file, use_colors=False
    )
    handler = next(
        handler
        for handler in logging.getLogger().handlers
        if isinstance(handler, RotatingFileHandler)
    )
    assert handler.maxBytes == 10 * 1024 * 1024
    assert handler.backupCount == 5
    logger = logging.getLogger("libmbus2mqtt.file_test")
    logger.info("initial-info")
    logger.debug("hidden-before-debug")
    set_log_level("DEBUG")
    logger.debug("visible-after-debug")
    set_log_level("INFO")
    logger.debug("hidden-after-info")
    handler.flush()

    content = log_file.read_text()
    assert "initial-info" in content
    assert "visible-after-debug" in content
    assert "hidden-before-debug" not in content
    assert "hidden-after-info" not in content
    if custom_file:
        assert not default_file.exists()


@pytest.mark.usefixtures("isolated_logging")
def test_file_rotation_limits_size_and_retains_latest_backups(tmp_path: Path) -> None:
    log_file = tmp_path / "log/bridge.log"
    setup_logging(logs_config=LogsConfig(max_size_mb=1, backup_count=2), default_log_file=log_file)
    logger = logging.getLogger("libmbus2mqtt.rotation_test")
    for index in range(5):
        logger.info("record-%s %s", index, "x" * 600_000)

    assert {path.name for path in log_file.parent.iterdir()} == {
        "bridge.log",
        "bridge.log.1",
        "bridge.log.2",
    }
    for suffix, index in [("", 4), (".1", 3), (".2", 2)]:
        path = Path(f"{log_file}{suffix}")
        assert path.stat().st_size < 1024 * 1024
        assert f"record-{index} " in path.read_text()
