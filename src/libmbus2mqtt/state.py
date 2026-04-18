"""SQLite-backed persistent runtime state."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from libmbus2mqtt.constants import DEFAULT_DB_FILE
from libmbus2mqtt.logging import get_logger

SCHEMA_VERSION = 2
logger = get_logger("state")


def utcnow_iso() -> str:
    """Return the current UTC time as an ISO string."""
    return datetime.now(UTC).isoformat()


def build_identity_key(object_id: str, manufacturer: str, model: str) -> str:
    """Build a stable identity key from raw device identity fields."""
    return json.dumps([object_id, manufacturer, model], separators=(",", ":"), ensure_ascii=True)


@dataclass(frozen=True)
class DeviceIdentityRecord:
    """Persisted identity information for a physical device."""

    identity_key: str
    object_id: str
    manufacturer: str
    model: str
    status: str
    first_seen_at: str
    last_seen_at: str
    last_address: int
    activation_count: int
    last_status_change_at: str


@dataclass(frozen=True)
class AddressBindingRecord:
    """Persisted binding between an M-Bus address and the current active identity."""

    address: int
    identity_key: str
    configured_name: str | None
    published_device_name: str
    template_mode: str
    template_name: str | None
    template_source: str
    datarecord_count: int
    updated_at: str


@dataclass(frozen=True)
class PublishedEntityRecord:
    """Persisted Home Assistant discovery publication metadata."""

    discovery_object_id: str
    identity_key: str
    component: str
    entity_key: str
    discovery_topic: str
    entity_availability_topic: str | None
    config_json: str
    lifecycle_state: str
    frozen: bool
    published_at: str
    last_updated_at: str

    @property
    def config(self) -> dict[str, Any]:
        """Decode the stored discovery config."""
        return cast(dict[str, Any], json.loads(self.config_json))


@dataclass(frozen=True)
class DeviceSnapshotRecord:
    """Persisted last-known MQTT state for an active device identity."""

    address: int
    identity_key: str
    object_id: str
    state_json: str
    availability: str
    updated_at: str

    @property
    def state(self) -> dict[str, Any]:
        """Decode the stored state payload."""
        return cast(dict[str, Any], json.loads(self.state_json))


class StateStore:
    """Persist daemon runtime state in SQLite."""

    def __init__(self, db_path: Path = DEFAULT_DB_FILE) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
        except sqlite3.Error:
            conn.close()
            raise
        return conn

    @contextmanager
    def _connection(self, operation: str) -> Iterator[sqlite3.Connection]:
        conn: sqlite3.Connection | None = None
        operation_error = False
        try:
            conn = self._connect()
        except sqlite3.Error as exc:
            logger.error(
                "SQLite connection failed for %s (%s): %s",
                operation,
                self.db_path,
                exc,
            )
            raise

        try:
            with conn:
                yield conn
        except sqlite3.Error as exc:
            operation_error = True
            logger.error(
                "SQLite operation %s failed (%s): %s",
                operation,
                self.db_path,
                exc,
            )
            raise
        finally:
            try:
                conn.close()
            except sqlite3.Error as exc:
                if not operation_error:
                    logger.error(
                        "SQLite close failed for %s (%s): %s",
                        operation,
                        self.db_path,
                        exc,
                    )
                    raise

    def _initialize(self) -> None:
        with self._connection("initialize") as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS device_identity (
                    identity_key TEXT PRIMARY KEY,
                    object_id TEXT NOT NULL,
                    manufacturer TEXT NOT NULL,
                    model TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('active', 'replaced')),
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    last_address INTEGER NOT NULL,
                    activation_count INTEGER NOT NULL DEFAULT 0,
                    last_status_change_at TEXT NOT NULL,
                    UNIQUE(object_id, manufacturer, model)
                );

                CREATE TABLE IF NOT EXISTS address_binding (
                    address INTEGER PRIMARY KEY,
                    identity_key TEXT NOT NULL REFERENCES device_identity(identity_key),
                    configured_name TEXT,
                    published_device_name TEXT NOT NULL,
                    template_mode TEXT NOT NULL CHECK(template_mode IN ('explicit', 'auto', 'generic')),
                    template_name TEXT,
                    template_source TEXT NOT NULL CHECK(template_source IN ('explicit', 'user_index', 'bundled_index', 'generic')),
                    datarecord_count INTEGER NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS published_entity (
                    discovery_object_id TEXT PRIMARY KEY,
                    identity_key TEXT NOT NULL REFERENCES device_identity(identity_key),
                    component TEXT NOT NULL,
                    entity_key TEXT NOT NULL,
                    discovery_topic TEXT NOT NULL UNIQUE,
                    entity_availability_topic TEXT,
                    config_json TEXT NOT NULL,
                    lifecycle_state TEXT NOT NULL CHECK(lifecycle_state IN ('active', 'retired', 'replaced')),
                    frozen INTEGER NOT NULL DEFAULT 0,
                    published_at TEXT NOT NULL,
                    last_updated_at TEXT NOT NULL,
                    UNIQUE(identity_key, entity_key)
                );

                CREATE TABLE IF NOT EXISTS device_snapshot (
                    identity_key TEXT PRIMARY KEY REFERENCES device_identity(identity_key),
                    object_id TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    availability TEXT NOT NULL CHECK(availability IN ('online', 'offline', 'unknown')),
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS identity_event (
                    id INTEGER PRIMARY KEY,
                    address INTEGER NOT NULL,
                    event_type TEXT NOT NULL CHECK(event_type IN ('bootstrap', 'activate', 'replace', 'reactivate', 'template_rematch', 'rename')),
                    from_identity_key TEXT,
                    to_identity_key TEXT,
                    details_json TEXT,
                    created_at TEXT NOT NULL
                );
                """
            )
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def get_identity(self, identity_key: str) -> DeviceIdentityRecord | None:
        """Get an identity row by primary key."""
        with self._connection("get_identity") as conn:
            row = conn.execute(
                "SELECT * FROM device_identity WHERE identity_key = ?",
                (identity_key,),
            ).fetchone()
        return self._row_to_identity(row)

    def get_identity_by_tuple(
        self,
        object_id: str,
        manufacturer: str,
        model: str,
    ) -> DeviceIdentityRecord | None:
        """Get an identity row by raw identity fields."""
        with self._connection("get_identity_by_tuple") as conn:
            row = conn.execute(
                """
                SELECT * FROM device_identity
                WHERE object_id = ? AND manufacturer = ? AND model = ?
                """,
                (object_id, manufacturer, model),
            ).fetchone()
        return self._row_to_identity(row)

    def upsert_identity(
        self,
        *,
        identity_key: str,
        object_id: str,
        manufacturer: str,
        model: str,
        status: str,
        last_address: int,
        increment_activation: bool = False,
        seen_at: str | None = None,
    ) -> DeviceIdentityRecord:
        """Insert or update a device identity row."""
        timestamp = seen_at or utcnow_iso()
        activation_increment = 1 if increment_activation else 0
        with self._connection("upsert_identity") as conn:
            conn.execute(
                """
                INSERT INTO device_identity (
                    identity_key, object_id, manufacturer, model, status,
                    first_seen_at, last_seen_at, last_address, activation_count, last_status_change_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(identity_key) DO UPDATE SET
                    object_id = excluded.object_id,
                    manufacturer = excluded.manufacturer,
                    model = excluded.model,
                    status = excluded.status,
                    last_seen_at = excluded.last_seen_at,
                    last_address = excluded.last_address,
                    activation_count = device_identity.activation_count + ?,
                    last_status_change_at = CASE
                        WHEN device_identity.status != excluded.status OR ? = 1
                            THEN excluded.last_status_change_at
                        ELSE device_identity.last_status_change_at
                    END
                """,
                (
                    identity_key,
                    object_id,
                    manufacturer,
                    model,
                    status,
                    timestamp,
                    timestamp,
                    last_address,
                    activation_increment,
                    timestamp,
                    activation_increment,
                    activation_increment,
                ),
            )
            row = conn.execute(
                "SELECT * FROM device_identity WHERE identity_key = ?",
                (identity_key,),
            ).fetchone()
        if row is None:
            msg = f"Identity row missing after upsert: {identity_key}"
            raise RuntimeError(msg)
        identity = self._row_to_identity(row)
        if identity is None:
            msg = f"Failed to convert identity row after upsert: {identity_key}"
            raise RuntimeError(msg)
        return identity

    def set_identity_status(
        self,
        identity_key: str,
        status: str,
        *,
        last_address: int,
        seen_at: str | None = None,
    ) -> None:
        """Update the status of an identity row."""
        timestamp = seen_at or utcnow_iso()
        with self._connection("set_identity_status") as conn:
            conn.execute(
                """
                UPDATE device_identity
                SET status = ?,
                    last_seen_at = ?,
                    last_address = ?,
                    last_status_change_at = ?
                WHERE identity_key = ?
                """,
                (status, timestamp, last_address, timestamp, identity_key),
            )

    def get_address_binding(self, address: int) -> AddressBindingRecord | None:
        """Get the current active identity binding for an address."""
        with self._connection("get_address_binding") as conn:
            row = conn.execute(
                "SELECT * FROM address_binding WHERE address = ?",
                (address,),
            ).fetchone()
        return self._row_to_binding(row)

    def upsert_address_binding(
        self,
        *,
        address: int,
        identity_key: str,
        configured_name: str | None,
        published_device_name: str,
        template_mode: str,
        template_name: str | None,
        template_source: str,
        datarecord_count: int,
        updated_at: str | None = None,
    ) -> AddressBindingRecord:
        """Insert or update the active identity binding for an address."""
        timestamp = updated_at or utcnow_iso()
        with self._connection("upsert_address_binding") as conn:
            conn.execute(
                """
                DELETE FROM address_binding
                WHERE identity_key = ? AND address != ?
                """,
                (identity_key, address),
            )
            conn.execute(
                """
                INSERT INTO address_binding (
                    address, identity_key, configured_name, published_device_name,
                    template_mode, template_name, template_source, datarecord_count, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(address) DO UPDATE SET
                    identity_key = excluded.identity_key,
                    configured_name = excluded.configured_name,
                    published_device_name = excluded.published_device_name,
                    template_mode = excluded.template_mode,
                    template_name = excluded.template_name,
                    template_source = excluded.template_source,
                    datarecord_count = excluded.datarecord_count,
                    updated_at = excluded.updated_at
                """,
                (
                    address,
                    identity_key,
                    configured_name,
                    published_device_name,
                    template_mode,
                    template_name,
                    template_source,
                    datarecord_count,
                    timestamp,
                ),
            )
            row = conn.execute(
                "SELECT * FROM address_binding WHERE address = ?",
                (address,),
            ).fetchone()
        if row is None:
            msg = f"Address binding missing after upsert: {address}"
            raise RuntimeError(msg)
        binding = self._row_to_binding(row)
        if binding is None:
            msg = f"Failed to convert address binding row after upsert: {address}"
            raise RuntimeError(msg)
        return binding

    def upsert_published_entity(
        self,
        *,
        discovery_object_id: str,
        identity_key: str,
        component: str,
        entity_key: str,
        discovery_topic: str,
        entity_availability_topic: str | None,
        config: dict[str, Any],
        lifecycle_state: str,
        frozen: bool,
        updated_at: str | None = None,
    ) -> PublishedEntityRecord:
        """Insert or update a stored Home Assistant entity discovery row."""
        timestamp = updated_at or utcnow_iso()
        config_json = json.dumps(config, separators=(",", ":"), ensure_ascii=True)
        with self._connection("upsert_published_entity") as conn:
            conn.execute(
                """
                INSERT INTO published_entity (
                    discovery_object_id, identity_key, component, entity_key, discovery_topic,
                    entity_availability_topic, config_json, lifecycle_state, frozen,
                    published_at, last_updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(discovery_object_id) DO UPDATE SET
                    identity_key = excluded.identity_key,
                    component = excluded.component,
                    entity_key = excluded.entity_key,
                    discovery_topic = excluded.discovery_topic,
                    entity_availability_topic = excluded.entity_availability_topic,
                    config_json = excluded.config_json,
                    lifecycle_state = excluded.lifecycle_state,
                    frozen = excluded.frozen,
                    last_updated_at = excluded.last_updated_at
                """,
                (
                    discovery_object_id,
                    identity_key,
                    component,
                    entity_key,
                    discovery_topic,
                    entity_availability_topic,
                    config_json,
                    lifecycle_state,
                    1 if frozen else 0,
                    timestamp,
                    timestamp,
                ),
            )
            row = conn.execute(
                "SELECT * FROM published_entity WHERE discovery_object_id = ?",
                (discovery_object_id,),
            ).fetchone()
        if row is None:
            msg = f"Published entity missing after upsert: {discovery_object_id}"
            raise RuntimeError(msg)
        entity = self._row_to_published_entity(row)
        if entity is None:
            msg = f"Failed to convert published entity row after upsert: {discovery_object_id}"
            raise RuntimeError(msg)
        return entity

    def list_published_entities(
        self,
        identity_key: str,
        *,
        lifecycle_states: tuple[str, ...] | None = None,
    ) -> list[PublishedEntityRecord]:
        """List all published entities for an identity."""
        query = """
            SELECT * FROM published_entity
            WHERE identity_key = ?
        """
        params: list[str] = [identity_key]
        if lifecycle_states:
            placeholders = ", ".join("?" for _ in lifecycle_states)
            query += f" AND lifecycle_state IN ({placeholders})"
            params.extend(lifecycle_states)
        query += " ORDER BY discovery_object_id"

        with self._connection("list_published_entities") as conn:
            rows = conn.execute(
                query,
                tuple(params),
            ).fetchall()
        return [
            entity for row in rows if (entity := self._row_to_published_entity(row)) is not None
        ]

    def upsert_device_snapshot(
        self,
        *,
        identity_key: str,
        object_id: str,
        state: dict[str, Any],
        availability: str,
        updated_at: str | None = None,
    ) -> DeviceSnapshotRecord:
        """Insert or update the last-known retained payload for a device identity."""
        timestamp = updated_at or utcnow_iso()
        state_json = json.dumps(state)
        with self._connection("upsert_device_snapshot") as conn:
            conn.execute(
                """
                INSERT INTO device_snapshot (
                    identity_key, object_id, state_json, availability, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(identity_key) DO UPDATE SET
                    object_id = excluded.object_id,
                    state_json = excluded.state_json,
                    availability = excluded.availability,
                    updated_at = excluded.updated_at
                """,
                (identity_key, object_id, state_json, availability, timestamp),
            )
            row = conn.execute(
                """
                SELECT address_binding.address, device_snapshot.*
                FROM device_snapshot
                JOIN address_binding ON address_binding.identity_key = device_snapshot.identity_key
                WHERE device_snapshot.identity_key = ?
                """,
                (identity_key,),
            ).fetchone()
        if row is None:
            msg = f"Device snapshot missing after upsert: {identity_key}"
            raise RuntimeError(msg)
        snapshot = self._row_to_snapshot(row)
        if snapshot is None:
            msg = f"Failed to convert device snapshot after upsert: {identity_key}"
            raise RuntimeError(msg)
        return snapshot

    def update_device_snapshot_availability(
        self,
        identity_key: str,
        availability: str,
        *,
        updated_at: str | None = None,
    ) -> None:
        """Update availability for an existing device snapshot."""
        timestamp = updated_at or utcnow_iso()
        with self._connection("update_device_snapshot_availability") as conn:
            conn.execute(
                """
                UPDATE device_snapshot
                SET availability = ?,
                    updated_at = ?
                WHERE identity_key = ?
                """,
                (availability, timestamp, identity_key),
            )

    def list_active_device_snapshots(self) -> list[DeviceSnapshotRecord]:
        """List snapshots for identities that still own the active address binding."""
        with self._connection("list_active_device_snapshots") as conn:
            rows = conn.execute(
                """
                SELECT address_binding.address, device_snapshot.*
                FROM address_binding
                JOIN device_identity ON device_identity.identity_key = address_binding.identity_key
                JOIN device_snapshot ON device_snapshot.identity_key = address_binding.identity_key
                WHERE device_identity.status = 'active'
                ORDER BY address_binding.address
                """,
            ).fetchall()
        return [snapshot for row in rows if (snapshot := self._row_to_snapshot(row)) is not None]

    def mark_entities_replaced(self, identity_key: str, *, updated_at: str | None = None) -> None:
        """Mark active entities for an identity as replaced and frozen."""
        timestamp = updated_at or utcnow_iso()
        with self._connection("mark_entities_replaced") as conn:
            conn.execute(
                """
                UPDATE published_entity
                SET lifecycle_state = 'replaced',
                    frozen = 1,
                    last_updated_at = ?
                WHERE identity_key = ? AND lifecycle_state = 'active'
                """,
                (timestamp, identity_key),
            )

    def mark_entity_retired(
        self,
        identity_key: str,
        entity_key: str,
        *,
        updated_at: str | None = None,
    ) -> None:
        """Mark a single entity as retired and frozen."""
        timestamp = updated_at or utcnow_iso()
        with self._connection("mark_entity_retired") as conn:
            conn.execute(
                """
                UPDATE published_entity
                SET lifecycle_state = 'retired',
                    frozen = 1,
                    last_updated_at = ?
                WHERE identity_key = ? AND entity_key = ?
                """,
                (timestamp, identity_key, entity_key),
            )

    def record_event(
        self,
        *,
        address: int,
        event_type: str,
        from_identity_key: str | None = None,
        to_identity_key: str | None = None,
        details: dict[str, Any] | None = None,
        created_at: str | None = None,
    ) -> None:
        """Append a runtime identity event."""
        timestamp = created_at or utcnow_iso()
        details_json = None if details is None else json.dumps(details, separators=(",", ":"))
        with self._connection("record_event") as conn:
            conn.execute(
                """
                INSERT INTO identity_event (
                    address, event_type, from_identity_key, to_identity_key, details_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (address, event_type, from_identity_key, to_identity_key, details_json, timestamp),
            )

    def list_events(self) -> list[sqlite3.Row]:
        """Return all identity events for tests and diagnostics."""
        with self._connection("list_events") as conn:
            rows = conn.execute(
                "SELECT * FROM identity_event ORDER BY id",
            ).fetchall()
        return cast(list[sqlite3.Row], rows)

    def _row_to_identity(self, row: sqlite3.Row | None) -> DeviceIdentityRecord | None:
        if row is None:
            return None
        return DeviceIdentityRecord(
            identity_key=row["identity_key"],
            object_id=row["object_id"],
            manufacturer=row["manufacturer"],
            model=row["model"],
            status=row["status"],
            first_seen_at=row["first_seen_at"],
            last_seen_at=row["last_seen_at"],
            last_address=row["last_address"],
            activation_count=row["activation_count"],
            last_status_change_at=row["last_status_change_at"],
        )

    def _row_to_binding(self, row: sqlite3.Row | None) -> AddressBindingRecord | None:
        if row is None:
            return None
        return AddressBindingRecord(
            address=row["address"],
            identity_key=row["identity_key"],
            configured_name=row["configured_name"],
            published_device_name=row["published_device_name"],
            template_mode=row["template_mode"],
            template_name=row["template_name"],
            template_source=row["template_source"],
            datarecord_count=row["datarecord_count"],
            updated_at=row["updated_at"],
        )

    def _row_to_published_entity(self, row: sqlite3.Row | None) -> PublishedEntityRecord | None:
        if row is None:
            return None
        return PublishedEntityRecord(
            discovery_object_id=row["discovery_object_id"],
            identity_key=row["identity_key"],
            component=row["component"],
            entity_key=row["entity_key"],
            discovery_topic=row["discovery_topic"],
            entity_availability_topic=row["entity_availability_topic"],
            config_json=row["config_json"],
            lifecycle_state=row["lifecycle_state"],
            frozen=bool(row["frozen"]),
            published_at=row["published_at"],
            last_updated_at=row["last_updated_at"],
        )

    def _row_to_snapshot(self, row: sqlite3.Row | None) -> DeviceSnapshotRecord | None:
        if row is None:
            return None
        return DeviceSnapshotRecord(
            address=row["address"],
            identity_key=row["identity_key"],
            object_id=row["object_id"],
            state_json=row["state_json"],
            availability=row["availability"],
            updated_at=row["updated_at"],
        )
