from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import threading
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

from .models import QualityResult, RegionProfile, VpnNode, node_from_dict, node_to_dict
from .openvpn import write_ovpn_config
from .regions import normalized_region
from .security import sanitize_ovpn_config


SCHEMA_VERSION = 1
SENSITIVE_SETTING_KEYS = {
    "api_key",
    "config_text",
    "openvpn_config",
    "password",
    "proxy_auth",
    "proxy_password",
    "scamalytics_api_key",
    "upstream_proxy_password",
}


class StorageValidationError(ValueError):
    """Raised when a persisted domain document does not match its schema."""


class Store(Protocol):
    def read(self, path: Path, default: Any) -> Any: ...
    def write(self, path: Path, data: Any) -> None: ...


@dataclass(frozen=True)
class MigrationDocumentSummary:
    kind: str
    source: str
    count: int
    checksum: str


@dataclass(frozen=True)
class MigrationSummary:
    backup_dir: str
    documents: tuple[MigrationDocumentSummary, ...]

    @property
    def total_count(self) -> int:
        return sum(document.count for document in self.documents)


class JsonStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()

    def read(self, path: Path, default: Any) -> Any:
        with self._lock:
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return default

    def read_versioned(self, path: Path, kind: str, default: Any) -> Any:
        if not path.exists():
            return default
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise StorageValidationError(f"invalid JSON payload for {kind}: {path}") from exc
        _validate_document(kind, data)
        metadata_path = _metadata_path(path)
        if metadata_path.exists():
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise StorageValidationError(f"invalid schema metadata for {kind}: {metadata_path}") from exc
        else:
            metadata = {}
        if metadata:
            _validate_metadata(kind, data, metadata)
        return data

    def write(self, path: Path, data: Any) -> None:
        with self._lock:
            _atomic_json_write(path, data)

    def write_versioned(self, path: Path, kind: str, data: Any) -> None:
        count = _validate_document(kind, data)
        with self._lock:
            _atomic_json_write(path, data)
            _atomic_json_write(
                _metadata_path(path),
                {
                    "schema_version": SCHEMA_VERSION,
                    "document_kind": kind,
                    "item_count": count,
                    "checksum": document_checksum(data),
                },
            )


class SqliteStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._lock = threading.RLock()
        self.last_migration_summary: MigrationSummary | None = None

    def read(self, path: Path, default: Any) -> Any:
        with self._lock:
            conn: sqlite3.Connection | None = None
            try:
                conn = self._connect()
                row = conn.execute(
                    "SELECT payload FROM json_documents WHERE document_key = ?",
                    (self._document_key(path),),
                ).fetchone()
                if row is None:
                    return default
                return json.loads(str(row[0]))
            except (OSError, sqlite3.DatabaseError, json.JSONDecodeError):
                return default
            finally:
                if conn is not None:
                    conn.close()

    def read_versioned(self, path: Path, kind: str, default: Any) -> Any:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    """
                    SELECT payload, schema_version, document_kind, item_count, checksum
                    FROM json_documents WHERE document_key = ?
                    """,
                    (self._document_key(path),),
                ).fetchone()
            finally:
                conn.close()
        if row is None:
            return default
        try:
            data = json.loads(str(row[0]))
        except json.JSONDecodeError as exc:
            raise StorageValidationError(f"invalid JSON payload for {kind}") from exc
        _validate_metadata(
            kind,
            data,
            {
                "schema_version": row[1],
                "document_kind": row[2],
                "item_count": row[3],
                "checksum": row[4],
            },
        )
        return data

    def write(self, path: Path, data: Any) -> None:
        self._write_document(path, "legacy", data, validate=False)

    def write_versioned(self, path: Path, kind: str, data: Any) -> None:
        self._write_document(path, kind, data, validate=True)

    def has_document(self, path: Path) -> bool:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT 1 FROM json_documents WHERE document_key = ?",
                    (self._document_key(path),),
                ).fetchone()
                return row is not None
            finally:
                conn.close()

    def import_documents(self, documents: Mapping[Path, tuple[str, Any]]) -> None:
        prepared: list[tuple[str, str, int, str, str]] = []
        for path, (kind, data) in documents.items():
            count = _validate_document(kind, data)
            prepared.append(
                (
                    self._document_key(path),
                    json.dumps(data, ensure_ascii=False, indent=2),
                    count,
                    document_checksum(data),
                    kind,
                )
            )
        with self._lock:
            conn = self._connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                for document_key, payload, count, checksum, kind in prepared:
                    self._upsert(conn, document_key, payload, kind, count, checksum)
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    def _write_document(self, path: Path, kind: str, data: Any, *, validate: bool) -> None:
        count = _validate_document(kind, data) if validate else _document_count(data)
        payload = json.dumps(data, ensure_ascii=False, indent=2)
        with self._lock:
            conn = self._connect()
            try:
                self._upsert(conn, self._document_key(path), payload, kind, count, document_checksum(data))
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    @staticmethod
    def _upsert(
        conn: sqlite3.Connection,
        document_key: str,
        payload: str,
        kind: str,
        count: int,
        checksum: str,
    ) -> None:
        conn.execute(
            """
            INSERT INTO json_documents(
                document_key, payload, schema_version, document_kind, item_count, checksum
            ) VALUES(?, ?, ?, ?, ?, ?)
            ON CONFLICT(document_key) DO UPDATE SET
                payload = excluded.payload,
                schema_version = excluded.schema_version,
                document_kind = excluded.document_kind,
                item_count = excluded.item_count,
                checksum = excluded.checksum
            """,
            (document_key, payload, SCHEMA_VERSION, kind, count, checksum),
        )

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS json_documents (
                document_key TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                schema_version INTEGER NOT NULL DEFAULT 1,
                document_kind TEXT NOT NULL DEFAULT 'legacy',
                item_count INTEGER NOT NULL DEFAULT 0,
                checksum TEXT NOT NULL DEFAULT ''
            )
            """
        )
        columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(json_documents)")}
        additions = {
            "schema_version": "INTEGER NOT NULL DEFAULT 1",
            "document_kind": "TEXT NOT NULL DEFAULT 'legacy'",
            "item_count": "INTEGER NOT NULL DEFAULT 0",
            "checksum": "TEXT NOT NULL DEFAULT ''",
        }
        for name, definition in additions.items():
            if name not in columns:
                conn.execute(f"ALTER TABLE json_documents ADD COLUMN {name} {definition}")
        conn.commit()
        try:
            self.db_path.chmod(0o600)
        except OSError:
            pass
        return conn

    @staticmethod
    def _document_key(path: Path) -> str:
        return str(path)


def build_store(backend: str = "json", *, sqlite_db_path: Path | None = None) -> Store:
    normalized = (backend or "json").strip().lower()
    if normalized == "json":
        return JsonStore()
    if normalized == "sqlite":
        if sqlite_db_path is None:
            raise ValueError("sqlite_db_path is required for sqlite storage")
        return SqliteStore(sqlite_db_path)
    raise ValueError(f"unsupported storage backend: {backend}")


def migrate_json_to_sqlite(
    documents: Mapping[Path, str],
    sqlite_store: SqliteStore,
    *,
    clock: Callable[[], Any] | None = None,
) -> MigrationSummary | None:
    """Back up and atomically import existing JSON domain documents into SQLite."""
    pending: dict[Path, tuple[str, Any]] = {}
    summaries: list[MigrationDocumentSummary] = []
    for path, kind in documents.items():
        if not path.exists() or sqlite_store.has_document(path):
            continue
        data = JsonStore().read_versioned(path, kind, None)
        count = _validate_document(kind, data)
        prepared_data = _prepare_document_for_persistence(path, kind, data)
        pending[path] = (kind, prepared_data)
        summaries.append(
            MigrationDocumentSummary(
                kind=kind,
                source=str(path),
                count=count,
                checksum=document_checksum(prepared_data),
            )
        )
    if not pending:
        return None

    now = clock() if clock is not None else datetime.now(timezone.utc)
    if isinstance(now, (int, float)):
        now = datetime.fromtimestamp(now, timezone.utc)
    stamp = now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = _unique_backup_dir(sqlite_store.db_path.parent, f"json-backup-{stamp}")
    backup_dir.mkdir(parents=True, exist_ok=False)
    for path in pending:
        shutil.copy2(path, backup_dir / path.name)
        metadata_path = _metadata_path(path)
        if metadata_path.exists():
            shutil.copy2(metadata_path, backup_dir / metadata_path.name)

    sqlite_store.import_documents(pending)
    summary = MigrationSummary(str(backup_dir), tuple(summaries))
    sqlite_store.last_migration_summary = summary
    _atomic_json_write(backup_dir / "migration-summary.json", asdict(summary))
    return summary


class _VersionedRepository:
    kind: str

    def __init__(self, path: Path, store: Store | None = None) -> None:
        self.path = path
        self.store = store or JsonStore()

    def _read(self, default: Any) -> Any:
        reader = getattr(self.store, "read_versioned", None)
        if reader is not None:
            return reader(self.path, self.kind, default)
        data = self.store.read(self.path, default)
        _validate_document(self.kind, data)
        return data

    def _write(self, data: Any) -> None:
        writer = getattr(self.store, "write_versioned", None)
        if writer is not None:
            writer(self.path, self.kind, data)
            return
        _validate_document(self.kind, data)
        self.store.write(self.path, data)


class NodeRepository(_VersionedRepository):
    kind = "nodes"

    def list_nodes(self, filters: dict[str, Any] | None = None) -> list[VpnNode]:
        nodes = [node_from_dict(item) for item in self.list_node_dicts()]
        if not filters:
            return nodes
        country = filters.get("country_code")
        if country:
            nodes = [node for node in nodes if (node.country_code or "").upper() == str(country).upper()]
        return nodes

    def get(self, node_id: str) -> VpnNode | None:
        return next((node for node in self.list_nodes() if node.id == node_id), None)

    def list_node_dicts(self) -> list[dict[str, Any]]:
        items = self._read([])
        return [self._hydrate_config(dict(item)) for item in items if isinstance(item, dict)]

    def replace_all_dicts(self, nodes: list[dict[str, Any]]) -> None:
        clean_nodes = [self._externalize_config(dict(node)) for node in nodes if isinstance(node, dict)]
        self._write(clean_nodes)

    def upsert_many_dicts(self, nodes: list[dict[str, Any]]) -> None:
        existing = {str(node.get("id") or ""): node for node in self.list_node_dicts() if node.get("id")}
        for node in nodes:
            node_id = str(node.get("id") or "")
            if node_id:
                existing[node_id] = dict(node)
        self.replace_all_dicts(list(existing.values()))

    def upsert_many(self, nodes: list[VpnNode]) -> None:
        existing = {node.id: node for node in self.list_nodes()}
        for node in nodes:
            existing[node.id] = node
        self.replace_all_dicts([node_to_dict(node) for node in existing.values()])

    def update_node(self, node_id: str, patch: dict[str, Any]) -> None:
        items = self.list_node_dicts()
        for item in items:
            if item.get("id") == node_id:
                item.update(patch)
                self.replace_all_dicts(items)
                return
        raise KeyError(node_id)

    def _externalize_config(self, node: dict[str, Any]) -> dict[str, Any]:
        return _externalize_node_config(self.path, node)

    def _hydrate_config(self, node: dict[str, Any]) -> dict[str, Any]:
        config_path = self._config_path(str(node.get("id") or ""))
        if config_path.exists():
            try:
                node["config_text"] = config_path.read_text(encoding="utf-8")
                node["config_file"] = str(config_path)
            except OSError:
                pass
        return node

    def _config_path(self, node_id: str) -> Path:
        safe_id = "".join(char if char.isalnum() or char in "._-" else "_" for char in node_id).strip("._")
        if not safe_id:
            raise StorageValidationError("node id is required for OpenVPN configuration")
        return self.path.parent / "configs" / f"{safe_id}.ovpn"


class RegionRepository(_VersionedRepository):
    kind = "regions"

    def list_regions(self) -> list[RegionProfile]:
        return [normalized_region(RegionProfile(**item)) for item in self._read([]) if isinstance(item, dict)]

    def get(self, region_id: str) -> RegionProfile | None:
        return next((region for region in self.list_regions() if region.id == region_id), None)

    def create(self, region: RegionProfile) -> None:
        region = normalized_region(region)
        if self.get(region.id):
            raise ValueError(f"region already exists: {region.id}")
        regions = self.list_regions()
        regions.append(region)
        self._write([region.__dict__ for region in regions])

    def update(self, region_id: str, patch: dict[str, Any]) -> None:
        regions = [region.__dict__ for region in self.list_regions()]
        for region in regions:
            if region.get("id") == region_id:
                region.update(patch)
                normalized = normalized_region(RegionProfile(**region))
                region.clear()
                region.update(normalized.__dict__)
                self._write(regions)
                return
        raise KeyError(region_id)

    def delete(self, region_id: str) -> None:
        regions = [region.__dict__ for region in self.list_regions()]
        remaining = [region for region in regions if region.get("id") != region_id]
        if len(remaining) == len(regions):
            raise KeyError(region_id)
        self._write(remaining)


class QualityRepository(_VersionedRepository):
    kind = "quality_results"

    def save(self, result: QualityResult) -> None:
        items = self._read([])
        safe_result = replace(result, raw_response=None)
        items.append(asdict(safe_result))
        self._write(items)

    def latest_for_node(self, node_id: str) -> QualityResult | None:
        return self.list_latest().get(node_id)

    def list_latest(self) -> dict[str, QualityResult]:
        latest: dict[str, QualityResult] = {}
        for item in self._read([]):
            if not isinstance(item, dict):
                continue
            result = QualityResult(**item)
            if result.node_id:
                latest[result.node_id] = result
        return latest

    def provider_cache(self) -> "ProviderCacheRepository":
        path = self.path.with_name(f"{self.path.stem}_provider_cache.json")
        return ProviderCacheRepository(path, self.store)


class ProviderCacheRepository(_VersionedRepository):
    kind = "provider_cache"

    def get(self, provider: str, key: str, *, now: float) -> QualityResult | None:
        entry = self._read({}).get(f"{provider}:{key}")
        if not isinstance(entry, dict) or float(entry.get("expires_at") or 0) <= now:
            return None
        result = entry.get("result")
        if not isinstance(result, dict):
            return None
        return QualityResult(**result)

    def put(self, provider: str, key: str, result: QualityResult, *, expires_at: float) -> None:
        data = self._read({})
        data[f"{provider}:{key}"] = {
            "expires_at": float(expires_at),
            "result": asdict(replace(result, raw_response=None)),
        }
        self._write(data)


class SettingsRepository(_VersionedRepository):
    kind = "settings"

    def get(self, key: str, default: Any = None) -> Any:
        data = self._read({})
        return data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        if str(key).strip().lower() in SENSITIVE_SETTING_KEYS:
            raise StorageValidationError(f"sensitive setting must not be persisted: {key}")
        data = self._read({})
        data[key] = value
        self._write(data)


class BlacklistRepository(_VersionedRepository):
    kind = "blacklist"

    def read_raw_entries(self) -> dict[str, Any]:
        """Read legacy entries so the blacklist domain cleaner can repair them."""
        data = self.store.read(self.path, {})
        return dict(data) if isinstance(data, dict) else {}

    def read_entries(self) -> dict[str, dict[str, Any]]:
        return {str(key): dict(value) for key, value in self._read({}).items() if isinstance(value, dict)}

    def write_entries(self, entries: Mapping[str, Mapping[str, Any]]) -> None:
        self._write({str(key): dict(value) for key, value in entries.items()})


def document_checksum(data: Any) -> str:
    payload = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _validate_document(kind: str, data: Any) -> int:
    if kind in {"nodes", "regions", "quality_results"}:
        if not isinstance(data, list):
            raise StorageValidationError(f"{kind} document must be a list")
        for item in data:
            if not isinstance(item, dict):
                raise StorageValidationError(f"{kind} entries must be objects")
            if kind == "nodes" and not str(item.get("id") or "").strip():
                raise StorageValidationError("node id is required")
            if kind == "regions":
                try:
                    normalized_region(RegionProfile(**item))
                except (TypeError, ValueError) as exc:
                    raise StorageValidationError("invalid region entry") from exc
            if kind == "quality_results":
                try:
                    QualityResult(**item)
                except (TypeError, ValueError) as exc:
                    raise StorageValidationError("invalid quality result entry") from exc
        return len(data)
    if kind in {"settings", "blacklist", "provider_cache"}:
        if not isinstance(data, dict):
            raise StorageValidationError(f"{kind} document must be an object")
        if kind == "blacklist" and any(not isinstance(value, dict) for value in data.values()):
            raise StorageValidationError("blacklist entries must be objects")
        if kind == "provider_cache":
            for entry in data.values():
                if not isinstance(entry, dict) or not isinstance(entry.get("result"), dict):
                    raise StorageValidationError("provider cache entries must contain results")
                float(entry.get("expires_at") or 0)
                QualityResult(**entry["result"])
        return len(data)
    if kind == "legacy":
        return _document_count(data)
    raise StorageValidationError(f"unknown document kind: {kind}")


def _validate_metadata(kind: str, data: Any, metadata: Mapping[str, Any]) -> None:
    version = int(metadata.get("schema_version") or 0)
    if version != SCHEMA_VERSION:
        raise StorageValidationError(f"unsupported {kind} schema version: {version}")
    stored_kind = str(metadata.get("document_kind") or "")
    if stored_kind not in {kind, "legacy"}:
        raise StorageValidationError(f"document kind mismatch: expected {kind}, got {stored_kind}")
    count = _validate_document(kind, data)
    stored_count = metadata.get("item_count")
    if stored_kind != "legacy" and stored_count is not None and int(stored_count) != count:
        raise StorageValidationError(f"{kind} item count mismatch")
    checksum = str(metadata.get("checksum") or "")
    if stored_kind != "legacy" and checksum and checksum != document_checksum(data):
        raise StorageValidationError(f"{kind} checksum mismatch")


def _document_count(data: Any) -> int:
    return len(data) if isinstance(data, (list, dict)) else 1


def _metadata_path(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".meta")


def _unique_backup_dir(parent: Path, name: str) -> Path:
    candidate = parent / name
    suffix = 1
    while candidate.exists():
        candidate = parent / f"{name}-{suffix}"
        suffix += 1
    return candidate


def _prepare_document_for_persistence(path: Path, kind: str, data: Any) -> Any:
    if kind == "nodes":
        return [_externalize_node_config(path, dict(node)) for node in data]
    if kind == "quality_results":
        return [{key: value for key, value in item.items() if key != "raw_response"} for item in data]
    if kind == "settings":
        return {key: value for key, value in data.items() if str(key).strip().lower() not in SENSITIVE_SETTING_KEYS}
    if kind == "provider_cache":
        prepared = json.loads(json.dumps(data))
        for entry in prepared.values():
            if isinstance(entry, dict) and isinstance(entry.get("result"), dict):
                entry["result"].pop("raw_response", None)
        return prepared
    return data


def _externalize_node_config(path: Path, node: dict[str, Any]) -> dict[str, Any]:
    config_text = str(node.pop("config_text", "") or "")
    if not config_text:
        return node
    node_id = str(node.get("id") or "")
    safe_id = "".join(char if char.isalnum() or char in "._-" else "_" for char in node_id).strip("._")
    if not safe_id:
        raise StorageValidationError("node id is required for OpenVPN configuration")
    config_path = path.parent / "configs" / f"{safe_id}.ovpn"
    sanitized = sanitize_ovpn_config(config_text)
    try:
        unchanged = config_path.read_text(encoding="utf-8") == sanitized
    except OSError:
        unchanged = False
    if not unchanged:
        write_ovpn_config(config_path, sanitized)
    node["config_file"] = str(config_path)
    return node


def _atomic_json_write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        tmp.chmod(0o600)
    except OSError:
        pass
    os.replace(tmp, path)
    try:
        path.chmod(0o600)
    except OSError:
        pass
