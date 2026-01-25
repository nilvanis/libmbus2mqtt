"""Command-line interface using Typer."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from libmbus2mqtt.constants import APP_NAME, APP_VERSION, DEFAULT_CONFIG_FILE

app = typer.Typer(
    name=APP_NAME,
    help="M-Bus to MQTT bridge with Home Assistant integration",
    no_args_is_help=True,
)
config_app = typer.Typer(help="Configuration management commands")
libmbus_app = typer.Typer(help="libmbus installation commands")

app.add_typer(config_app, name="config")
app.add_typer(libmbus_app, name="libmbus")

console = Console()

# Common options
ConfigOption = Annotated[
    Path | None,
    typer.Option(
        "--config",
        "-c",
        help="Path to configuration file",
        envvar="LIBMBUS2MQTT_CONFIG",
    ),
]

LogLevelOption = Annotated[
    str | None,
    typer.Option(
        "--log-level",
        "-l",
        help="Log level",
        envvar="LIBMBUS2MQTT_LOG_LEVEL",
    ),
]


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        console.print(f"{APP_NAME} {APP_VERSION}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            "-v",
            help="Show version and exit",
            callback=version_callback,
            is_eager=True,
        ),
    ] = False,
) -> None:
    """libmbus2mqtt - M-Bus to MQTT bridge."""
    pass


@app.command()
def run(
    config: ConfigOption = None,
    log_level: LogLevelOption = None,
) -> None:
    """Start the libmbus2mqtt daemon."""
    from libmbus2mqtt.config import AppConfig
    from libmbus2mqtt.logging import setup_logging

    config_path = config or DEFAULT_CONFIG_FILE
    try:
        app_config = AppConfig.load(config_path)
    except FileNotFoundError:
        # Setup basic logging before showing error
        setup_logging(level=log_level or "INFO")
        console.print(f"[red]Error:[/red] Configuration file not found: {config_path}")
        console.print(f"Run '[bold]{APP_NAME} config init[/bold]' to create one.")
        raise typer.Exit(1) from None
    except Exception as e:
        setup_logging(level=log_level or "INFO")
        console.print(f"[red]Error loading configuration:[/red] {e}")
        raise typer.Exit(1) from None

    # CLI --log-level overrides config if provided
    effective_level = log_level if log_level else app_config.logs.level
    setup_logging(level=effective_level, logs_config=app_config.logs)

    # Import and run main loop
    from libmbus2mqtt.main import run_daemon

    run_daemon(app_config)


@app.command()
def scan(
    config: ConfigOption = None,
    log_level: LogLevelOption = None,
) -> None:
    """Scan for M-Bus devices (one-shot)."""
    from libmbus2mqtt.config import AppConfig
    from libmbus2mqtt.logging import setup_logging

    config_path = config or DEFAULT_CONFIG_FILE
    try:
        app_config = AppConfig.load(config_path)
    except FileNotFoundError:
        setup_logging(level=log_level or "INFO")
        console.print(f"[red]Error:[/red] Configuration file not found: {config_path}")
        raise typer.Exit(1) from None
    except Exception as e:
        setup_logging(level=log_level or "INFO")
        console.print(f"[red]Error loading configuration:[/red] {e}")
        raise typer.Exit(1) from None

    # CLI --log-level overrides config if provided
    effective_level = log_level if log_level else app_config.logs.level
    setup_logging(level=effective_level, logs_config=app_config.logs)

    # Import and run scan
    from libmbus2mqtt.mbus.interface import MbusInterface

    console.print(f"[bold]Scanning M-Bus devices on {app_config.mbus.device}...[/bold]")

    try:
        interface = MbusInterface(
            device=app_config.mbus.device,
            baudrate=app_config.mbus.baudrate,
            retry_count=app_config.mbus.retry_count,
            retry_delay=app_config.mbus.retry_delay,
        )
        devices = interface.scan()

        if not devices:
            console.print("[yellow]No devices found.[/yellow]")
            return

        table = Table(title="Discovered M-Bus Devices")
        table.add_column("ID", style="cyan")
        table.add_column("Status", style="green")

        for device_id in devices:
            table.add_row(str(device_id), "Found")

        console.print(table)
        console.print(f"\n[bold]Total:[/bold] {len(devices)} device(s) found")

    except Exception as e:
        console.print(f"[red]Scan failed:[/red] {e}")
        raise typer.Exit(1) from None


@app.command(name="device-info")
def device_info(
    config: ConfigOption = None,
) -> None:
    """Show M-Bus master device information."""
    from libmbus2mqtt.config import AppConfig
    from libmbus2mqtt.mbus.tty import check_tty_device

    config_path = config or DEFAULT_CONFIG_FILE
    try:
        app_config = AppConfig.load(config_path)
    except FileNotFoundError:
        console.print(f"[red]Error:[/red] Configuration file not found: {config_path}")
        console.print(f"Run '[bold]{APP_NAME} config init[/bold]' to create one.")
        console.print("\n[yellow]Note:[/yellow] mbus.device must be configured before using this command.")
        raise typer.Exit(1) from None
    except Exception as e:
        console.print(f"[red]Error loading configuration:[/red] {e}")
        raise typer.Exit(1) from None

    device_path = app_config.mbus.device
    baudrate = app_config.mbus.baudrate
    info = check_tty_device(device_path)

    console.print("\n[bold]M-Bus Master Device Info[/bold]")
    console.print("=" * 30)
    console.print(f"Device:     {device_path}")

    if info["exists"]:
        if info["readable"] and info["writable"]:
            status = "[green]Available[/green]"
        else:
            status = "[yellow]Limited access[/yellow]"
    else:
        status = "[red]Not found[/red]"

    console.print(f"Status:     {status}")

    if info["exists"]:
        console.print(f"Type:       {info['type']}")

        if info.get("driver"):
            console.print(f"Driver:     {info['driver']}")

        usb_info = info.get("usb_info")
        if usb_info:
            console.print(f"USB Vendor: {usb_info.get('vendor', 'Unknown')}")
            if usb_info.get("product"):
                console.print(f"USB Product: {usb_info['product']}")

        if info.get("is_busy"):
            console.print("[yellow]Warning:    Device may be in use by another process[/yellow]")

    console.print(f"Baudrate:   {baudrate} (configured)")
    console.print()


@app.command()
def version() -> None:
    """Show version information."""
    console.print(f"[bold]{APP_NAME}[/bold] version {APP_VERSION}")


@app.command()
def install(
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", "-n", help="Show what would be done without making changes"),
    ] = False,
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Skip confirmation prompts"),
    ] = False,
) -> None:
    """Install systemd service for libmbus2mqtt."""
    import shutil

    from libmbus2mqtt.constants import (
        SERVICE_CONFIG_DIR,
        SERVICE_DATA_DIR,
        SERVICE_GROUP,
        SERVICE_USER,
        SYSTEMD_SERVICE_DIR,
        SYSTEMD_SERVICE_NAME,
    )
    from libmbus2mqtt.installer import (
        confirm_action,
        require_root,
        run_command,
        user_exists,
    )

    # Check root privileges (unless dry-run)
    if not dry_run:
        require_root("install")

    console.print("[bold]Installing libmbus2mqtt systemd service[/bold]\n")

    if dry_run:
        console.print("[yellow]Dry-run mode - no changes will be made[/yellow]\n")

    # Show what will be done and confirm
    console.print("This will:")
    console.print(f"  1. Create service user '{SERVICE_USER}' (if not exists)")
    console.print(f"  2. Create directory {SERVICE_CONFIG_DIR}")
    console.print(f"  3. Create directory {SERVICE_DATA_DIR}")
    console.print(f"  4. Install service file to {SYSTEMD_SERVICE_DIR / SYSTEMD_SERVICE_NAME}")
    console.print("  5. Reload systemd daemon")
    console.print("  6. Enable the service\n")

    if not confirm_action("Proceed with installation?", default=True, yes=yes):
        console.print("[yellow]Installation cancelled[/yellow]")
        raise typer.Exit(0)

    console.print()

    # Create service user
    if not user_exists(SERVICE_USER):
        console.print(f"Creating user '{SERVICE_USER}'...")
        run_command(
            ["useradd", "-r", "-s", "/bin/false", "-G", SERVICE_GROUP, SERVICE_USER],
            dry_run=dry_run,
            description="Create service user",
        )
        if not dry_run:
            console.print(f"  [green]User '{SERVICE_USER}' created[/green]")
    else:
        console.print(f"  [dim]User '{SERVICE_USER}' already exists[/dim]")

    # Create config directory
    console.print(f"Creating {SERVICE_CONFIG_DIR}...")
    if dry_run:
        run_command(["mkdir", "-p", str(SERVICE_CONFIG_DIR)], dry_run=True)
    else:
        SERVICE_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        console.print(f"  [green]Created {SERVICE_CONFIG_DIR}[/green]")

    # Create data directory with proper ownership
    console.print(f"Creating {SERVICE_DATA_DIR}...")
    if dry_run:
        run_command(["mkdir", "-p", str(SERVICE_DATA_DIR)], dry_run=True)
        run_command(["chown", f"{SERVICE_USER}:{SERVICE_GROUP}", str(SERVICE_DATA_DIR)], dry_run=True)
    else:
        SERVICE_DATA_DIR.mkdir(parents=True, exist_ok=True)
        shutil.chown(SERVICE_DATA_DIR, user=SERVICE_USER, group=SERVICE_GROUP)
        console.print(f"  [green]Created {SERVICE_DATA_DIR}[/green]")

    # Find and copy service file
    console.print("Installing service file...")
    service_src = _find_service_file()
    if service_src is None:
        console.print("[red]Error:[/red] Could not find libmbus2mqtt.service file")
        console.print("Expected in package's systemd/ directory")
        raise typer.Exit(1)

    service_dest = SYSTEMD_SERVICE_DIR / SYSTEMD_SERVICE_NAME

    if dry_run:
        run_command(["cp", str(service_src), str(service_dest)], dry_run=True)
    else:
        shutil.copy2(service_src, service_dest)
        service_dest.chmod(0o644)
        console.print(f"  [green]Installed {service_dest}[/green]")

    # Reload systemd
    console.print("Reloading systemd daemon...")
    run_command(["systemctl", "daemon-reload"], dry_run=dry_run)
    if not dry_run:
        console.print("  [green]Systemd daemon reloaded[/green]")

    # Enable service
    console.print("Enabling service...")
    run_command(["systemctl", "enable", SYSTEMD_SERVICE_NAME], dry_run=dry_run)
    if not dry_run:
        console.print("  [green]Service enabled[/green]")

    # Done
    console.print()
    if dry_run:
        console.print("[yellow]Dry-run complete - no changes were made[/yellow]")
    else:
        console.print("[green]Installation complete![/green]")
        console.print()
        console.print("Next steps:")
        console.print(
            f"  1. Create config: [bold]sudo libmbus2mqtt config init -c {SERVICE_CONFIG_DIR / 'config.yaml'}[/bold]"
        )
        console.print(f"  2. Edit config:   [bold]sudo nano {SERVICE_CONFIG_DIR / 'config.yaml'}[/bold]")
        console.print(f"  3. Start service: [bold]sudo systemctl start {SYSTEMD_SERVICE_NAME}[/bold]")
        console.print(f"  4. Check status:  [bold]sudo systemctl status {SYSTEMD_SERVICE_NAME}[/bold]")


def _find_service_file() -> Path | None:
    """Locate the bundled systemd service file."""
    import libmbus2mqtt

    pkg_dir = Path(libmbus2mqtt.__file__).parent

    # Check various possible locations
    candidates = [
        pkg_dir.parent.parent / "systemd" / "libmbus2mqtt.service",  # Development
        pkg_dir / "systemd" / "libmbus2mqtt.service",  # If bundled in package
        Path("/usr/share/libmbus2mqtt/libmbus2mqtt.service"),  # System install
    ]

    for candidate in candidates:
        if candidate.exists():
            return candidate

    return None


@app.command()
def uninstall(
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", "-n", help="Show what would be done without making changes"),
    ] = False,
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Skip confirmation prompts"),
    ] = False,
    purge: Annotated[
        bool,
        typer.Option("--purge", help="Also remove config, data directories, and user"),
    ] = False,
) -> None:
    """Remove systemd service for libmbus2mqtt."""
    import shutil

    from libmbus2mqtt.constants import (
        SERVICE_CONFIG_DIR,
        SERVICE_DATA_DIR,
        SERVICE_USER,
        SYSTEMD_SERVICE_DIR,
        SYSTEMD_SERVICE_NAME,
    )
    from libmbus2mqtt.installer import (
        confirm_action,
        require_root,
        run_command,
        user_exists,
    )

    # Check root privileges (unless dry-run)
    if not dry_run:
        require_root("uninstall")

    console.print("[bold]Uninstalling libmbus2mqtt systemd service[/bold]\n")

    if dry_run:
        console.print("[yellow]Dry-run mode - no changes will be made[/yellow]\n")

    service_file = SYSTEMD_SERVICE_DIR / SYSTEMD_SERVICE_NAME

    # Check if service is installed
    if not service_file.exists() and not dry_run:
        console.print("[yellow]Service is not installed[/yellow]")
        raise typer.Exit(0)

    # Show what will be done and confirm
    console.print("This will:")
    console.print("  1. Stop the service (if running)")
    console.print("  2. Disable the service")
    console.print(f"  3. Remove {service_file}")
    console.print("  4. Reload systemd daemon")

    if purge:
        console.print(f"  5. [red]Remove {SERVICE_CONFIG_DIR} (--purge)[/red]")
        console.print(f"  6. [red]Remove {SERVICE_DATA_DIR} (--purge)[/red]")
        console.print(f"  7. [red]Remove user '{SERVICE_USER}' (--purge)[/red]")

    console.print()

    warning = "[red]WARNING: --purge will delete all configuration and data![/red]\n" if purge else ""
    if not confirm_action(f"{warning}Proceed with uninstallation?", default=False, yes=yes):
        console.print("[yellow]Uninstallation cancelled[/yellow]")
        raise typer.Exit(0)

    console.print()

    # Stop the service
    console.print("Stopping service...")
    run_command(
        ["systemctl", "stop", SYSTEMD_SERVICE_NAME],
        dry_run=dry_run,
        check=False,  # Don't fail if not running
    )
    if not dry_run:
        console.print("  [green]Service stopped[/green]")

    # Disable the service
    console.print("Disabling service...")
    run_command(
        ["systemctl", "disable", SYSTEMD_SERVICE_NAME],
        dry_run=dry_run,
        check=False,  # Don't fail if not enabled
    )
    if not dry_run:
        console.print("  [green]Service disabled[/green]")

    # Remove service file
    console.print(f"Removing {service_file}...")
    if dry_run:
        run_command(["rm", str(service_file)], dry_run=True)
    else:
        if service_file.exists():
            service_file.unlink()
        console.print(f"  [green]Removed {service_file}[/green]")

    # Reload systemd
    console.print("Reloading systemd daemon...")
    run_command(["systemctl", "daemon-reload"], dry_run=dry_run)
    if not dry_run:
        console.print("  [green]Systemd daemon reloaded[/green]")

    # Purge (optional)
    if purge:
        console.print()
        console.print("[bold red]Purging data...[/bold red]")

        # Remove config directory
        if SERVICE_CONFIG_DIR.exists() or dry_run:
            console.print(f"Removing {SERVICE_CONFIG_DIR}...")
            if dry_run:
                run_command(["rm", "-rf", str(SERVICE_CONFIG_DIR)], dry_run=True)
            else:
                shutil.rmtree(SERVICE_CONFIG_DIR, ignore_errors=True)
                console.print(f"  [green]Removed {SERVICE_CONFIG_DIR}[/green]")

        # Remove data directory
        if SERVICE_DATA_DIR.exists() or dry_run:
            console.print(f"Removing {SERVICE_DATA_DIR}...")
            if dry_run:
                run_command(["rm", "-rf", str(SERVICE_DATA_DIR)], dry_run=True)
            else:
                shutil.rmtree(SERVICE_DATA_DIR, ignore_errors=True)
                console.print(f"  [green]Removed {SERVICE_DATA_DIR}[/green]")

        # Remove user
        if user_exists(SERVICE_USER) or dry_run:
            console.print(f"Removing user '{SERVICE_USER}'...")
            run_command(["userdel", SERVICE_USER], dry_run=dry_run, check=False)
            if not dry_run:
                console.print(f"  [green]User '{SERVICE_USER}' removed[/green]")

    # Done
    console.print()
    if dry_run:
        console.print("[yellow]Dry-run complete - no changes were made[/yellow]")
    else:
        console.print("[green]Uninstallation complete![/green]")


# Config subcommands
@config_app.command(name="validate")
def config_validate(
    config: ConfigOption = None,
) -> None:
    """Validate configuration file."""
    from libmbus2mqtt.config import AppConfig

    config_path = config or DEFAULT_CONFIG_FILE

    try:
        app_config = AppConfig.load(config_path)
        console.print(f"[green]Configuration is valid:[/green] {config_path}")

        # Show summary
        console.print("\n[bold]Summary:[/bold]")
        console.print(f"  M-Bus device:    {app_config.mbus.device}")
        console.print(f"  MQTT broker:     {app_config.mqtt.host}:{app_config.mqtt.port}")
        console.print(
            f"  Home Assistant:  {'Enabled' if app_config.homeassistant.enabled else 'Disabled'}"
        )
        console.print(f"  Poll interval:   {app_config.polling.interval}s")
        console.print(f"  Autoscan:        {'Enabled' if app_config.mbus.autoscan else 'Disabled'}")
        console.print(f"  Devices defined: {len(app_config.devices)}")

    except FileNotFoundError:
        console.print(f"[red]Configuration file not found:[/red] {config_path}")
        raise typer.Exit(1) from None
    except Exception as e:
        console.print(f"[red]Configuration error:[/red] {e}")
        raise typer.Exit(1) from None


@config_app.command(name="init")
def config_init(
    config: ConfigOption = None,
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Overwrite existing file"),
    ] = False,
) -> None:
    """Generate example configuration file."""
    from libmbus2mqtt.config import generate_example_config

    config_path = Path(config) if config else DEFAULT_CONFIG_FILE

    if config_path.exists() and not force:
        console.print(f"[yellow]Configuration file already exists:[/yellow] {config_path}")
        console.print("Use [bold]--force[/bold] to overwrite")
        raise typer.Exit(1)

    config_path.parent.mkdir(parents=True, exist_ok=True)

    with config_path.open("w") as f:
        f.write(generate_example_config())

    console.print(f"[green]Configuration file created:[/green] {config_path}")
    console.print("\nEdit the file and set required values:")
    console.print("  - [bold]mbus.device[/bold]: Your serial device path")
    console.print("  - [bold]mqtt.host[/bold]: Your MQTT broker address")


# Libmbus subcommands
@libmbus_app.command(name="status")
def libmbus_status() -> None:
    """Check libmbus installation status."""
    from libmbus2mqtt.constants import LIBMBUS_BINARIES
    from libmbus2mqtt.installer import find_libmbus_binaries

    console.print("[bold]libmbus status:[/bold]\n")

    binaries = find_libmbus_binaries()
    all_installed = True

    for binary in LIBMBUS_BINARIES:
        path = binaries.get(binary)
        if path:
            console.print(f"  {binary}: [green]{path}[/green] [OK]")
        else:
            console.print(f"  {binary}: [red]NOT FOUND[/red]")
            all_installed = False

    console.print()

    if all_installed:
        console.print("[green]libmbus is installed and ready.[/green]")
    else:
        console.print("[yellow]libmbus is NOT installed or incomplete.[/yellow]")
        console.print("\nRun '[bold]libmbus2mqtt libmbus install[/bold]' to install from source.")
        raise typer.Exit(1)


@libmbus_app.command(name="install")
def libmbus_install(
    install_path: Annotated[
        Path,
        typer.Option("--path", "-p", help="Installation path for binaries"),
    ] = Path("/usr/local/bin"),
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", "-n", help="Show what would be done without making changes"),
    ] = False,
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Skip confirmation prompts"),
    ] = False,
    keep_build: Annotated[
        bool,
        typer.Option("--keep-build", help="Keep build directory after installation"),
    ] = False,
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Reinstall even if already installed"),
    ] = False,
) -> None:
    """Install libmbus from source (native installation)."""
    import shutil
    import subprocess

    from rich.progress import Progress, SpinnerColumn, TextColumn

    from libmbus2mqtt.constants import (
        LIBMBUS_BINARIES,
        LIBMBUS_BUILD_DIR,
        LIBMBUS_REPO,
    )
    from libmbus2mqtt.installer import (
        check_command_available,
        confirm_action,
        find_libmbus_binaries,
        is_libmbus_installed,
        require_root,
        run_command,
    )

    # Check if already installed (unless --force)
    if not force and is_libmbus_installed():
        console.print("[bold]libmbus is already installed:[/bold]\n")
        binaries = find_libmbus_binaries()
        for binary, path in binaries.items():
            if path:
                console.print(f"  {binary}: [green]{path}[/green]")
        console.print("\nUse [bold]--force[/bold] to reinstall.")
        raise typer.Exit(0)

    # Check root privileges (for system-wide install)
    needs_root = str(install_path).startswith("/usr")
    if needs_root and not dry_run:
        require_root("libmbus install")

    console.print("[bold]Installing libmbus from source[/bold]\n")

    if dry_run:
        console.print("[yellow]Dry-run mode - no changes will be made[/yellow]\n")

    # Check build dependencies
    console.print("Checking build dependencies...")
    dep_checks = {
        "git": "git",
        "build-essential": "gcc",
        "libtool": "libtool",
        "autoconf": "autoconf",
        "automake": "automake",
    }

    missing_deps: list[str] = []
    for pkg, cmd in dep_checks.items():
        if check_command_available(cmd):
            console.print(f"  [green]OK[/green] {pkg}")
        else:
            console.print(f"  [red]MISSING[/red] {pkg}")
            missing_deps.append(pkg)

    if missing_deps:
        console.print()
        console.print("[red]Error:[/red] Missing build dependencies")
        console.print("Install them with:")
        console.print(f"  [bold]sudo apt-get install {' '.join(missing_deps)}[/bold]")
        raise typer.Exit(1)

    console.print()

    # Show plan and confirm
    console.print("This will:")
    console.print(f"  1. Clone {LIBMBUS_REPO}")
    console.print(f"  2. Build libmbus in {LIBMBUS_BUILD_DIR}")
    console.print(f"  3. Install binaries to {install_path}")
    console.print(f"     - {', '.join(LIBMBUS_BINARIES)}")
    console.print("  4. Install libraries to /usr/local/lib")
    if not keep_build:
        console.print("  5. Clean up build directory")
    console.print()

    if not confirm_action("Proceed with installation?", default=True, yes=yes):
        console.print("[yellow]Installation cancelled[/yellow]")
        raise typer.Exit(0)

    console.print()

    # Create and clean build directory
    build_dir = LIBMBUS_BUILD_DIR
    repo_dir = build_dir / "libmbus"

    if build_dir.exists() and not dry_run:
        console.print(f"Cleaning existing build directory {build_dir}...")
        shutil.rmtree(build_dir)

    if not dry_run:
        build_dir.mkdir(parents=True, exist_ok=True)

    # Clone repository
    console.print("Cloning libmbus repository...")
    if dry_run:
        run_command(
            ["git", "clone", "--depth", "1", LIBMBUS_REPO, str(repo_dir)],
            dry_run=True,
        )
    else:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task("Cloning...", total=None)
            run_command(
                ["git", "clone", "--depth", "1", LIBMBUS_REPO, str(repo_dir)],
                capture_output=True,
            )
        console.print("  [green]Repository cloned[/green]")

    # Build libmbus
    console.print("Building libmbus...")
    if dry_run:
        run_command(["./build.sh"], dry_run=True, description="Run build.sh")
    else:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task("Building (this may take a minute)...", total=None)

            result = subprocess.run(
                ["./build.sh"],
                cwd=repo_dir,
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                console.print("[red]Build failed![/red]")
                console.print(result.stderr)
                raise typer.Exit(1)

        console.print("  [green]Build complete[/green]")

    # Install
    console.print("Installing binaries and libraries...")
    if dry_run:
        run_command(["make", "install"], dry_run=True, description="Install to system")
    else:
        result = subprocess.run(
            ["make", "install"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            console.print("[red]Installation failed![/red]")
            console.print(result.stderr)
            raise typer.Exit(1)

        # Update library cache
        run_command(["ldconfig"], check=False)
        console.print("  [green]Installation complete[/green]")

    # Verify installation
    console.print("Verifying installation...")
    all_found = True
    for binary in LIBMBUS_BINARIES:
        binary_path = install_path / binary
        if dry_run or binary_path.exists() or check_command_available(binary):
            console.print(f"  [green]OK[/green] {binary}")
        else:
            console.print(f"  [red]NOT FOUND[/red] {binary}")
            all_found = False

    if not all_found and not dry_run:
        console.print()
        console.print("[yellow]Warning:[/yellow] Some binaries were not found in expected location")
        console.print("They may be installed in a different path. Check with: [bold]which mbus-serial-scan[/bold]")

    # Cleanup
    if not keep_build and not dry_run:
        console.print("Cleaning up build directory...")
        shutil.rmtree(build_dir, ignore_errors=True)
        console.print("  [green]Build directory removed[/green]")

    # Done
    console.print()
    if dry_run:
        console.print("[yellow]Dry-run complete - no changes were made[/yellow]")
    else:
        console.print("[green]libmbus installation complete![/green]")
        console.print()
        console.print("Verify with: [bold]mbus-serial-scan --help[/bold]")


if __name__ == "__main__":
    app()
