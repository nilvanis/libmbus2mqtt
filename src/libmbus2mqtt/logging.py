"""Logging configuration with colored output and optional file logging."""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from libmbus2mqtt.constants import LOG_COLORS, LOG_DATE_FORMAT, LOG_FORMAT, LOG_RESET

if TYPE_CHECKING:
    from libmbus2mqtt.config import LogsConfig


class ColoredFormatter(logging.Formatter):
    """Formatter that adds colors to log levels."""

    COLORS: ClassVar[dict[str, str]] = LOG_COLORS

    def __init__(self, use_colors: bool = True) -> None:
        super().__init__(fmt=LOG_FORMAT, datefmt=LOG_DATE_FORMAT)
        self.use_colors = use_colors

    def format(self, record: logging.LogRecord) -> str:
        # Format the message first
        message = super().format(record)

        if self.use_colors and record.levelname in self.COLORS:
            color = self.COLORS[record.levelname]
            # Color only the level name portion
            message = message.replace(
                f"| {record.levelname:<8} |",
                f"| {color}{record.levelname:<8}{LOG_RESET} |",
            )

        return message


class PlainFormatter(logging.Formatter):
    """Formatter without colors for file output."""

    def __init__(self) -> None:
        super().__init__(fmt=LOG_FORMAT, datefmt=LOG_DATE_FORMAT)


def _setup_file_handler(
    logger: logging.Logger,
    config: LogsConfig,
    level: int,
) -> None:
    """
    Set up rotating file handler.

    Args:
        logger: The logger to add the handler to.
        config: LogsConfig with file logging settings.
        level: Log level to use for the file handler.
    """
    log_path = Path(config.file)

    # Ensure log directory exists
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        # Can't create directory - log warning and skip file logging
        logger.warning(f"Cannot create log directory {log_path.parent}: {e}")
        return

    # Create rotating file handler
    try:
        file_handler = RotatingFileHandler(
            filename=log_path,
            maxBytes=config.max_size_mb * 1024 * 1024,  # Convert MB to bytes
            backupCount=config.backup_count,
            encoding="utf-8",
        )
    except OSError as e:
        logger.warning(f"Cannot create log file {log_path}: {e}")
        return

    file_handler.setFormatter(PlainFormatter())
    file_handler.setLevel(level)
    logger.addHandler(file_handler)


def setup_logging(
    level: str = "INFO",
    use_colors: bool | None = None,
    logs_config: LogsConfig | None = None,
) -> None:
    """
    Configure application logging.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        use_colors: Enable colored output. Auto-detected if None.
        logs_config: Optional LogsConfig for file logging configuration.
    """
    colors_enabled: bool = use_colors if use_colors is not None else sys.stdout.isatty()

    # Get numeric level
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(ColoredFormatter(use_colors=colors_enabled))

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Remove existing handlers
    root_logger.handlers.clear()
    root_logger.addHandler(console_handler)

    # Add file handler if configured
    if logs_config and logs_config.save_to_file:
        _setup_file_handler(root_logger, logs_config, numeric_level)

    # Set level for our package
    logging.getLogger("libmbus2mqtt").setLevel(numeric_level)

    # Quiet down noisy libraries
    logging.getLogger("paho.mqtt").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a logger for the given name."""
    if not name.startswith("libmbus2mqtt"):
        name = f"libmbus2mqtt.{name}"
    return logging.getLogger(name)


def set_log_level(level: str) -> None:
    """
    Change the log level at runtime.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logging.getLogger().setLevel(numeric_level)
    logging.getLogger("libmbus2mqtt").setLevel(numeric_level)
