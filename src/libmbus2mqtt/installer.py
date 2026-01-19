"""Installation utilities for systemd service and libmbus."""

from __future__ import annotations

import os
import pwd
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console

from libmbus2mqtt.constants import LIBMBUS_BINARIES, LIBMBUS_DEFAULT_INSTALL_PATH

if TYPE_CHECKING:
    from collections.abc import Sequence

console = Console()


def is_root() -> bool:
    """Check if running as root/sudo."""
    return os.geteuid() == 0


def require_root(command_name: str) -> None:
    """Exit with error if not running as root."""
    if not is_root():
        console.print(f"[red]Error:[/red] '{command_name}' requires root privileges.")
        console.print(f"Please run with sudo: [bold]sudo libmbus2mqtt {command_name}[/bold]")
        raise SystemExit(1)


def run_command(
    cmd: Sequence[str | Path],
    *,
    dry_run: bool = False,
    check: bool = True,
    capture_output: bool = False,
    cwd: Path | None = None,
    description: str | None = None,
) -> subprocess.CompletedProcess[str] | None:
    """
    Run a shell command with optional dry-run mode.

    Args:
        cmd: Command and arguments as sequence
        dry_run: If True, print command instead of executing
        check: If True, raise on non-zero exit
        capture_output: If True, capture stdout/stderr
        cwd: Working directory for command
        description: Optional description for dry-run output

    Returns:
        CompletedProcess result or None if dry_run
    """
    cmd_str = " ".join(str(c) for c in cmd)

    if dry_run:
        prefix = f"[dim]{description}:[/dim] " if description else ""
        console.print(f"  {prefix}[cyan]{cmd_str}[/cyan]")
        return None

    try:
        return subprocess.run(
            [str(c) for c in cmd],
            check=check,
            capture_output=capture_output,
            text=True,
            cwd=cwd,
        )
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Command failed:[/red] {cmd_str}")
        if e.stderr:
            console.print(f"[dim]{e.stderr}[/dim]")
        raise


def user_exists(username: str) -> bool:
    """Check if a system user exists."""
    try:
        pwd.getpwnam(username)
        return True
    except KeyError:
        return False


def confirm_action(message: str, *, default: bool = False, yes: bool = False) -> bool:
    """
    Prompt for user confirmation.

    Args:
        message: Prompt message
        default: Default if user presses Enter
        yes: If True, skip prompt and return True

    Returns:
        True if confirmed, False otherwise
    """
    if yes:
        return True

    suffix = " [Y/n]" if default else " [y/N]"
    response = console.input(f"{message}{suffix} ").strip().lower()

    if not response:
        return default
    return response in ("y", "yes")


def check_command_available(command: str) -> bool:
    """Check if a command is available in PATH."""
    return shutil.which(command) is not None


def find_libmbus_binaries() -> dict[str, Path | None]:
    """
    Find libmbus binary locations.

    Returns:
        Dict mapping binary name to path (or None if not found).
        Example: {"mbus-serial-scan": Path("/usr/local/bin/mbus-serial-scan"), ...}
    """
    result: dict[str, Path | None] = {}

    for binary in LIBMBUS_BINARIES:
        # First check default install path
        default_path = LIBMBUS_DEFAULT_INSTALL_PATH / binary
        if default_path.exists():
            result[binary] = default_path
            continue

        # Then check PATH
        which_result = shutil.which(binary)
        if which_result:
            result[binary] = Path(which_result)
        else:
            result[binary] = None

    return result


def is_libmbus_installed() -> bool:
    """Check if all libmbus binaries are installed."""
    binaries = find_libmbus_binaries()
    return all(path is not None for path in binaries.values())
