from __future__ import annotations

"""Durable storage for the v1.0.2 global catalog.

The global scheduler has a different lifecycle from an individual instance:
one VPNGate snapshot is shared by all instances, while quality checks and job
history need to survive a Console restart.  This module keeps that data in
small, purpose-specific SQLite tables and retains the existing JSON layout as
an explicit fallback for upgrades and emergency recovery.
"""

import json
import os
import sqlite3
import threading
import time
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping

from .storage import SENSITIVE_SETTING_KEYS, StorageValidationError


GLOBAL_STORAGE_SCHEMA_VERSION = 1
_GLOBAL_SECRET_KEYS = SENSITIVE_SETTING_KEYS | {
    "scamalytics_api_key",
    "scamalytics_password",
    "upstream_proxy_password",
}


def _atomic_json_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        temporary.chmod(0o600)
    except OSError:
        pass
    os.replace(temporary, path)
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return default


def _safe_node(node: Mapping[str, Any]) -> dict[str, Any]:
    clean = dict(node)
    # OpenVPN content is deliberately kept in the restricted config file.
    clean.pop("config_text", None)
    clean.pop("raw_response", None)
    return clean


def _safe_quality(ip: str, result: Mapping[str, Any]) -> dict[str, Any]:
    allowed = {
        "risk_score",
        "risk_level",
        "proxy_detected",
        "datacenter_detected",
        "provider",
        "source",
        "country",
        "asn",
        "status",
        "error_type",
        "checked_at",
        "cache_expires_at",
    }
    clean = {key: result[key] for key in allowed if key in result}
    clean["ip"] = ip
    return clean


class GlobalRepository:
    """Read/write global data using SQLite or the legacy JSON files.

    ``backend="json"`` is the compatibility default.  The scheduler can opt
    into SQLite with ``backend="sqlite"`` without changing its public data
    shape, which makes rollback to the JSON snapshot straightforward.
    """

    def __init__(self, root: Path, *, backend: str = "json", db_path: Path | None = None) -> None:
        self.root = Path(root)
        normalized = (backend or "json").strip().lower()
        if normalized not in {"json", "sqlite"}:
            raise ValueError(f"unsupported global storage backend: {backend}")
        self.backend = normalized
        self.db_path = Path(db_path) if db_path is not None else self.root / "global.db"
        self.nodes_path = self.root / "nodes.json"
        self.quality_path = self.root / "quality_results.json"
        self.quality_queue_path = self.root / "quality_queue.json"
        self.quality_metrics_path = self.root / "quality_metrics.json"
        self.history_path = self.root / "task_history.json"
        self.state_path = self.root / "task_state.json"
        self.settings_path = self.root / "global_settings.json"
        self._lock = threading.RLock()

    def replace_nodes(self, nodes: list[dict[str, Any]], *, updated_at: float) -> None:
        clean_nodes = [_safe_node(node) for node in nodes if isinstance(node, dict) and str(node.get("id") or "").strip()]
        if not clean_nodes:
            raise StorageValidationError("global node snapshot must contain at least one node")
        if self.backend == "json":
            _atomic_json_write(
                self.nodes_path,
                {
                    "schema_version": GLOBAL_STORAGE_SCHEMA_VERSION,
                    "source": "vpngate",
                    "updated_at": float(updated_at),
                    "node_count": len(clean_nodes),
                    "nodes": clean_nodes,
                },
            )
            return

        with self._transaction() as conn:
            conn.execute("DELETE FROM global_nodes")
            conn.executemany(
                """
                INSERT INTO global_nodes(node_id, server_ip, country_code, rank_no, payload, updated_at)
                VALUES(?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        str(clean.get("id")),
                        str(clean.get("server_ip") or clean.get("ip") or ""),
                        str(clean.get("country_short") or clean.get("country_code") or "").upper(),
                        index,
                        json.dumps(clean, ensure_ascii=False, separators=(",", ":")),
                        float(updated_at),
                    )
                    for index, clean in enumerate(clean_nodes)
                ],
            )
            self._set_metadata(conn, "nodes_updated_at", float(updated_at))
            self._set_metadata(conn, "nodes_source", "vpngate")

    def clear_nodes(self, *, updated_at: float | None = None) -> None:
        """Remove the catalog explicitly (used only by a validated restore)."""
        timestamp = time.time() if updated_at is None else float(updated_at)
        if self.backend == "json":
            _atomic_json_write(
                self.nodes_path,
                {
                    "schema_version": GLOBAL_STORAGE_SCHEMA_VERSION,
                    "source": "restore",
                    "updated_at": timestamp,
                    "node_count": 0,
                    "nodes": [],
                },
            )
            return
        with self._transaction() as conn:
            conn.execute("DELETE FROM global_nodes")
            self._set_metadata(conn, "nodes_updated_at", timestamp)
            self._set_metadata(conn, "nodes_source", "restore")

    def read_nodes(self) -> list[dict[str, Any]]:
        if self.backend == "json":
            payload = _read_json(self.nodes_path, {})
            items = payload.get("nodes", []) if isinstance(payload, dict) else payload
            return [dict(item) for item in items if isinstance(item, dict) and str(item.get("id") or "").strip()]
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT payload FROM global_nodes ORDER BY rank_no, node_id").fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            try:
                item = json.loads(str(row[0]))
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                result.append(item)
        return result

    def snapshot_updated_at(self) -> float | None:
        if self.backend == "json":
            payload = _read_json(self.nodes_path, {})
            value = payload.get("updated_at") if isinstance(payload, dict) else None
            try:
                return float(value) if value is not None else None
            except (TypeError, ValueError):
                return None
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT value FROM global_metadata WHERE name = ?", ("nodes_updated_at",)).fetchone()
        try:
            return float(json.loads(str(row[0]))) if row is not None else None
        except (TypeError, ValueError, json.JSONDecodeError):
            return None

    def read_quality(self) -> dict[str, dict[str, Any]]:
        if self.backend == "json":
            payload = _read_json(self.quality_path, {})
            return {str(key): dict(value) for key, value in payload.items() if isinstance(value, dict)} if isinstance(payload, dict) else {}
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT ip, payload FROM global_quality_results ORDER BY ip").fetchall()
        result: dict[str, dict[str, Any]] = {}
        for ip, payload in rows:
            try:
                item = json.loads(str(payload))
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                result[str(ip)] = item
        return result

    def get_quality(self, ip: str, *, now: float | None = None) -> dict[str, Any] | None:
        key = str(ip).strip()
        if not key:
            return None
        result = self.read_quality().get(key)
        if not result:
            return None
        if now is not None:
            try:
                if float(result.get("cache_expires_at") or 0) <= now:
                    return None
            except (TypeError, ValueError):
                return None
        return result

    def upsert_quality(self, ip: str, result: Mapping[str, Any]) -> None:
        key = str(ip).strip()
        if not key:
            raise StorageValidationError("quality result IP is required")
        clean = _safe_quality(key, result)
        if self.backend == "json":
            payload = self.read_quality()
            payload[key] = clean
            _atomic_json_write(self.quality_path, payload)
            return
        checked_at = _as_float(clean.get("checked_at"), time.time())
        expires_at = _as_float(clean.get("cache_expires_at"), 0.0)
        with self._transaction() as conn:
            conn.execute(
                """
                INSERT INTO global_quality_results(ip, status, checked_at, expires_at, payload)
                VALUES(?, ?, ?, ?, ?)
                ON CONFLICT(ip) DO UPDATE SET
                    status = excluded.status,
                    checked_at = excluded.checked_at,
                    expires_at = excluded.expires_at,
                    payload = excluded.payload
                """,
                (key, str(clean.get("status") or "unknown"), checked_at, expires_at, json.dumps(clean, ensure_ascii=False, separators=(",", ":"))),
            )

    def upsert_quality_many(self, results: Mapping[str, Mapping[str, Any]]) -> None:
        for ip, result in results.items():
            self.upsert_quality(str(ip), result)

    def replace_quality(self, results: Iterable[Mapping[str, Any]]) -> None:
        """Replace all cached quality results as one restore operation."""
        clean_results: list[tuple[str, dict[str, Any]]] = []
        for result in results:
            if not isinstance(result, Mapping):
                continue
            ip = str(result.get("ip") or result.get("server_ip") or "").strip()
            if ip:
                clean_results.append((ip, _safe_quality(ip, result)))
        if self.backend == "json":
            _atomic_json_write(self.quality_path, {ip: result for ip, result in clean_results})
            return
        with self._transaction() as conn:
            conn.execute("DELETE FROM global_quality_results")
            conn.executemany(
                """
                INSERT INTO global_quality_results(ip, status, checked_at, expires_at, payload)
                VALUES(?, ?, ?, ?, ?)
                """,
                [
                    (
                        ip,
                        str(result.get("status") or "unknown"),
                        _as_float(result.get("checked_at"), time.time()),
                        _as_float(result.get("cache_expires_at"), 0.0),
                        json.dumps(result, ensure_ascii=False, separators=(",", ":")),
                    )
                    for ip, result in clean_results
                ],
            )

    def enqueue_quality_ips(self, ips: list[str], *, now: float | None = None) -> None:
        timestamp = time.time() if now is None else float(now)
        keys = [str(ip).strip() for ip in ips if str(ip).strip()]
        if not keys:
            return
        if self.backend == "json":
            payload = _read_json(self.quality_queue_path, {})
            queue = dict(payload) if isinstance(payload, dict) else {}
            for ip in keys:
                queue.setdefault(ip, {"ip": ip, "status": "pending", "attempts": 0, "next_attempt_at": 0, "updated_at": timestamp})
            _atomic_json_write(self.quality_queue_path, queue)
            return
        with self._transaction() as conn:
            conn.executemany(
                """
                INSERT INTO global_quality_queue(ip, status, attempts, next_attempt_at, last_error, updated_at)
                VALUES(?, 'pending', 0, 0, '', ?)
                ON CONFLICT(ip) DO NOTHING
                """,
                [(ip, timestamp) for ip in keys],
            )

    def read_quality_queue(self, *, limit: int = 10000) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 100000))
        if self.backend == "json":
            payload = _read_json(self.quality_queue_path, {})
            values = [dict(item) for item in payload.values() if isinstance(item, dict)] if isinstance(payload, dict) else []
            return sorted(values, key=lambda item: (float(item.get("next_attempt_at") or 0), str(item.get("ip") or "")))[:limit]
        with closing(self._connect()) as conn:
            rows = conn.execute(
                """
                SELECT ip, status, attempts, next_attempt_at, last_error, updated_at
                FROM global_quality_queue ORDER BY next_attempt_at, ip LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            {
                "ip": str(ip),
                "status": str(status),
                "attempts": int(attempts),
                "next_attempt_at": float(next_attempt_at),
                "last_error": str(last_error or ""),
                "updated_at": float(updated_at),
            }
            for ip, status, attempts, next_attempt_at, last_error, updated_at in rows
        ]

    def mark_quality_queue(
        self,
        ip: str,
        *,
        status: str,
        attempts: int,
        next_attempt_at: float,
        last_error: str = "",
        now: float | None = None,
    ) -> None:
        key = str(ip).strip()
        if not key:
            return
        timestamp = time.time() if now is None else float(now)
        payload = {
            "ip": key,
            "status": str(status),
            "attempts": max(0, int(attempts)),
            "next_attempt_at": float(next_attempt_at),
            "last_error": str(last_error or "")[:256],
            "updated_at": timestamp,
        }
        if self.backend == "json":
            queue = _read_json(self.quality_queue_path, {})
            queue = dict(queue) if isinstance(queue, dict) else {}
            queue[key] = payload
            _atomic_json_write(self.quality_queue_path, queue)
            return
        with self._transaction() as conn:
            conn.execute(
                """
                INSERT INTO global_quality_queue(ip, status, attempts, next_attempt_at, last_error, updated_at)
                VALUES(?, ?, ?, ?, ?, ?)
                ON CONFLICT(ip) DO UPDATE SET
                    status = excluded.status,
                    attempts = excluded.attempts,
                    next_attempt_at = excluded.next_attempt_at,
                    last_error = excluded.last_error,
                    updated_at = excluded.updated_at
                """,
                (key, payload["status"], payload["attempts"], payload["next_attempt_at"], payload["last_error"], timestamp),
            )

    def remove_quality_queue(self, ip: str) -> None:
        key = str(ip).strip()
        if not key:
            return
        if self.backend == "json":
            queue = _read_json(self.quality_queue_path, {})
            if isinstance(queue, dict) and key in queue:
                queue.pop(key, None)
                _atomic_json_write(self.quality_queue_path, queue)
            return
        with self._transaction() as conn:
            conn.execute("DELETE FROM global_quality_queue WHERE ip = ?", (key,))

    def clear_quality_queue(self) -> None:
        if self.backend == "json":
            _atomic_json_write(self.quality_queue_path, {})
            return
        with self._transaction() as conn:
            conn.execute("DELETE FROM global_quality_queue")

    def read_quality_metrics(self) -> dict[str, Any]:
        if self.backend == "json":
            payload = _read_json(self.quality_metrics_path, {})
            return dict(payload) if isinstance(payload, dict) else {}
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT value FROM global_metadata WHERE name = ?", ("quality_metrics",)).fetchone()
        if row is None:
            return {}
        try:
            payload = json.loads(str(row[0]))
        except json.JSONDecodeError:
            return {}
        return dict(payload) if isinstance(payload, dict) else {}

    def write_quality_metrics(self, metrics: Mapping[str, Any]) -> None:
        clean = dict(metrics)
        if self.backend == "json":
            _atomic_json_write(self.quality_metrics_path, clean)
            return
        with self._transaction() as conn:
            self._set_metadata(conn, "quality_metrics", clean)

    def read_history(self, *, limit: int = 100) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 1000))
        if self.backend == "json":
            payload = _read_json(self.history_path, [])
            return [dict(item) for item in payload[-limit:] if isinstance(item, dict)] if isinstance(payload, list) else []
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT payload FROM global_job_history ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in reversed(rows):
            try:
                item = json.loads(str(row[0]))
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                result.append(item)
        return result

    def append_history(self, item: Mapping[str, Any], *, limit: int = 100) -> None:
        clean = dict(item)
        clean.pop("raw_response", None)
        if self.backend == "json":
            history = self.read_history(limit=max(limit, 1000))
            history.append(clean)
            _atomic_json_write(self.history_path, history[-max(1, int(limit)):])
            return
        created_at = _as_float(clean.get("at") or clean.get("created_at"), time.time())
        with self._transaction() as conn:
            conn.execute(
                "INSERT INTO global_job_history(task, status, created_at, payload) VALUES(?, ?, ?, ?)",
                (str(clean.get("task") or "vpngate"), str(clean.get("status") or "unknown"), created_at, json.dumps(clean, ensure_ascii=False, separators=(",", ":"))),
            )
            conn.execute(
                "DELETE FROM global_job_history WHERE id NOT IN (SELECT id FROM global_job_history ORDER BY id DESC LIMIT ?)",
                (max(1, int(limit)),),
            )

    def replace_history(self, items: Iterable[Mapping[str, Any]], *, limit: int = 100) -> None:
        """Replace task history while keeping the same bounded retention policy."""
        clean_items: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, Mapping):
                continue
            clean = dict(item)
            clean.pop("raw_response", None)
            clean_items.append(clean)
        clean_items = clean_items[-max(1, int(limit)):]
        if self.backend == "json":
            _atomic_json_write(self.history_path, clean_items)
            return
        with self._transaction() as conn:
            conn.execute("DELETE FROM global_job_history")
            conn.executemany(
                "INSERT INTO global_job_history(task, status, created_at, payload) VALUES(?, ?, ?, ?)",
                [
                    (
                        str(item.get("task") or "vpngate"),
                        str(item.get("status") or "unknown"),
                        _as_float(item.get("at") or item.get("created_at"), time.time()),
                        json.dumps(item, ensure_ascii=False, separators=(",", ":")),
                    )
                    for item in clean_items
                ],
            )

    def read_task_state(self, task: str = "global") -> dict[str, Any]:
        if self.backend == "json":
            payload = _read_json(self.state_path, {})
            return dict(payload) if isinstance(payload, dict) else {}
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT payload FROM global_task_state WHERE task = ?", (task,)).fetchone()
        if row is None:
            return {}
        try:
            payload = json.loads(str(row[0]))
        except json.JSONDecodeError:
            return {}
        return dict(payload) if isinstance(payload, dict) else {}

    def write_task_state(self, state: Mapping[str, Any], task: str = "global") -> None:
        clean = dict(state)
        if self.backend == "json":
            _atomic_json_write(self.state_path, clean)
            return
        with self._transaction() as conn:
            conn.execute(
                """
                INSERT INTO global_task_state(task, payload, updated_at) VALUES(?, ?, ?)
                ON CONFLICT(task) DO UPDATE SET payload = excluded.payload, updated_at = excluded.updated_at
                """,
                (task, json.dumps(clean, ensure_ascii=False, separators=(",", ":")), time.time()),
            )

    def read_settings(self) -> dict[str, Any]:
        if self.backend == "json":
            payload = _read_json(self.settings_path, {})
            return self._safe_settings(payload) if isinstance(payload, dict) else {}
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT name, value FROM global_settings ORDER BY name").fetchall()
        settings: dict[str, Any] = {}
        for name, value in rows:
            try:
                settings[str(name)] = json.loads(str(value))
            except json.JSONDecodeError:
                continue
        return settings

    def write_settings(self, settings: Mapping[str, Any]) -> None:
        clean = self._safe_settings(settings)
        if self.backend == "json":
            _atomic_json_write(self.settings_path, clean)
            return
        with self._transaction() as conn:
            conn.execute("DELETE FROM global_settings")
            conn.executemany(
                "INSERT INTO global_settings(name, value, updated_at) VALUES(?, ?, ?)",
                [(key, json.dumps(value, ensure_ascii=False, separators=(",", ":")), time.time()) for key, value in clean.items()],
            )

    def migrate_json(self) -> dict[str, int]:
        """Import legacy JSON files once, without overwriting SQLite data."""
        if self.backend != "sqlite":
            return {"nodes": 0, "quality": 0, "history": 0, "state": 0, "settings": 0}

        imported = {"nodes": 0, "quality": 0, "history": 0, "state": 0, "settings": 0}
        if not self.read_nodes():
            payload = _read_json(self.nodes_path, {})
            items = payload.get("nodes", []) if isinstance(payload, dict) else []
            if isinstance(items, list) and items:
                updated_at = _as_float(payload.get("updated_at"), time.time()) if isinstance(payload, dict) else time.time()
                self.replace_nodes([dict(item) for item in items if isinstance(item, dict)], updated_at=updated_at)
                imported["nodes"] = len(self.read_nodes())

        if not self.read_quality():
            payload = _read_json(self.quality_path, {})
            if isinstance(payload, dict):
                self.upsert_quality_many({str(ip): value for ip, value in payload.items() if isinstance(value, dict)})
                imported["quality"] = len(self.read_quality())

        if not self.read_history():
            payload = _read_json(self.history_path, [])
            if isinstance(payload, list):
                for item in payload[-100:]:
                    if isinstance(item, dict):
                        self.append_history(item)
                imported["history"] = len(self.read_history())

        if not self.read_quality_metrics():
            payload = _read_json(self.quality_metrics_path, {})
            if isinstance(payload, dict) and payload:
                self.write_quality_metrics(payload)

        if not self.read_task_state():
            payload = _read_json(self.state_path, {})
            if isinstance(payload, dict) and payload:
                self.write_task_state(payload)
                imported["state"] = 1

        if not self.read_settings():
            payload = _read_json(self.settings_path, {})
            if isinstance(payload, dict) and payload:
                self.write_settings(payload)
                imported["settings"] = len(payload)
        return imported

    def _safe_settings(self, settings: Mapping[str, Any]) -> dict[str, Any]:
        for key in settings:
            if str(key).strip().lower() in _GLOBAL_SECRET_KEYS:
                raise StorageValidationError(f"sensitive setting must not be persisted: {key}")
        return {str(key): value for key, value in settings.items()}

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=5)
        conn.execute("PRAGMA busy_timeout = 5000")
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS global_nodes (
                node_id TEXT PRIMARY KEY,
                server_ip TEXT NOT NULL,
                country_code TEXT NOT NULL,
                rank_no INTEGER NOT NULL,
                payload TEXT NOT NULL,
                updated_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_global_nodes_country ON global_nodes(country_code);
            CREATE TABLE IF NOT EXISTS global_quality_results (
                ip TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                checked_at REAL NOT NULL,
                expires_at REAL NOT NULL,
                payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS global_quality_queue (
                ip TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                next_attempt_at REAL NOT NULL DEFAULT 0,
                last_error TEXT NOT NULL DEFAULT '',
                updated_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS global_job_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at REAL NOT NULL,
                payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS global_task_state (
                task TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                updated_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS global_settings (
                name TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS global_metadata (
                name TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )
        conn.commit()
        try:
            self.db_path.chmod(0o600)
        except OSError:
            pass
        return conn

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _set_metadata(conn: sqlite3.Connection, name: str, value: Any) -> None:
        conn.execute(
            "INSERT INTO global_metadata(name, value) VALUES(?, ?) ON CONFLICT(name) DO UPDATE SET value = excluded.value",
            (name, json.dumps(value, ensure_ascii=False, separators=(",", ":"))),
        )


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
