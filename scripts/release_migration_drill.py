#!/usr/bin/env python3
"""Exercise legacy authentication/JSON upgrade and a verified JSON rollback."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import shutil
import sys
import tempfile
import threading
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aimilivpn.core.auth import verify_password  # noqa: E402
from aimilivpn.core.storage import (  # noqa: E402
    NodeRepository,
    SettingsRepository,
    SqliteStore,
    migrate_json_to_sqlite,
)
from aimilivpn.system.ui_config import UiConfigStore  # noqa: E402


LEGACY_PASSWORD = "release-drill-legacy-password"


def bounded_int(value: object, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if minimum <= parsed <= maximum else default


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_drill(root: Path) -> dict[str, object]:
    data_dir = root / "legacy-data"
    data_dir.mkdir(parents=True)
    auth_file = data_dir / "ui_auth.json"
    nodes_file = data_dir / "nodes.json"
    settings_file = data_dir / "settings.json"
    database = data_dir / "aimilivpn.db"

    auth_file.write_text(
        json.dumps(
            {
                "username": "legacy-admin",
                "password": LEGACY_PASSWORD,
                "host": "127.0.0.1",
                "port": 8787,
                "proxy_port": 7928,
            }
        ),
        encoding="utf-8",
    )
    nodes_file.write_text(
        json.dumps([{"id": "jp_legacy", "country_short": "JP", "ip": "203.0.113.10"}]),
        encoding="utf-8",
    )
    settings_file.write_text(json.dumps({"proxy_port": 7928}), encoding="utf-8")
    original_checksums = {
        nodes_file.name: file_sha256(nodes_file),
        settings_file.name: file_sha256(settings_file),
    }

    ui_store = UiConfigStore(
        data_dir=data_dir,
        lock=threading.RLock(),
        ui_host="127.0.0.1",
        ui_port=8787,
        proxy_port=7928,
        bounded_int=bounded_int,
        password_factory=lambda: "unused-generated-password",
        username_factory=lambda: "unused-generated-user",
    )
    with contextlib.redirect_stdout(io.StringIO()):
        migrated_auth = ui_store.load()
    if "password" in migrated_auth or not verify_password(LEGACY_PASSWORD, migrated_auth["password_hash"]):
        raise RuntimeError("legacy authentication migration failed")
    secure_auth_snapshot = auth_file.read_bytes()

    sqlite_store = SqliteStore(database)
    summary = migrate_json_to_sqlite(
        {nodes_file: "nodes", settings_file: "settings"},
        sqlite_store,
    )
    if summary is None or len(summary.documents) != 2:
        raise RuntimeError("JSON to SQLite migration did not produce the expected summary")
    backup_dir = Path(summary.backup_dir)
    summary_file = backup_dir / "migration-summary.json"
    if not summary_file.exists():
        raise RuntimeError("migration summary was not persisted")
    if NodeRepository(nodes_file, store=sqlite_store).list_node_dicts()[0]["id"] != "jp_legacy":
        raise RuntimeError("migrated node data could not be read")
    if SettingsRepository(settings_file, store=sqlite_store).get("proxy_port") != 7928:
        raise RuntimeError("migrated settings could not be read")

    nodes_file.write_text(json.dumps([{"id": "upgrade-only"}]), encoding="utf-8")
    settings_file.write_text(json.dumps({"proxy_port": 9999}), encoding="utf-8")
    for path in (nodes_file, settings_file):
        shutil.copy2(backup_dir / path.name, path)
    auth_file.write_bytes(secure_auth_snapshot)

    rolled_back_nodes = NodeRepository(nodes_file).list_node_dicts()
    rolled_back_settings = SettingsRepository(settings_file).get("proxy_port")
    with contextlib.redirect_stdout(io.StringIO()):
        rolled_back_auth = ui_store.load()
    if rolled_back_nodes[0]["id"] != "jp_legacy" or rolled_back_settings != 7928:
        raise RuntimeError("JSON rollback verification failed")
    if "password" in rolled_back_auth or not verify_password(LEGACY_PASSWORD, rolled_back_auth["password_hash"]):
        raise RuntimeError("secure authentication rollback verification failed")
    for name, expected in original_checksums.items():
        if file_sha256(data_dir / name) != expected:
            raise RuntimeError(f"rollback checksum mismatch: {name}")

    # A rollback must leave JSON as a valid source for a subsequent upgrade,
    # rather than only proving that the first SQLite import worked.
    reupgrade_store = SqliteStore(data_dir / "aimilivpn-reupgrade.db")
    reupgrade_summary = migrate_json_to_sqlite(
        {nodes_file: "nodes", settings_file: "settings"},
        reupgrade_store,
    )
    if reupgrade_summary is None or reupgrade_summary.total_count != summary.total_count:
        raise RuntimeError("JSON to SQLite re-upgrade did not preserve document counts")
    if NodeRepository(nodes_file, store=reupgrade_store).list_node_dicts()[0]["id"] != "jp_legacy":
        raise RuntimeError("re-upgraded node data could not be read")
    if SettingsRepository(settings_file, store=reupgrade_store).get("proxy_port") != 7928:
        raise RuntimeError("re-upgraded settings could not be read")
    if sorted(item.checksum for item in reupgrade_summary.documents) != sorted(item.checksum for item in summary.documents):
        raise RuntimeError("re-upgrade checksums do not match the original import")

    return {
        "status": "passed",
        "auth_plaintext_removed": True,
        "migrated_documents": len(summary.documents),
        "migrated_items": summary.total_count,
        "backup_summary": summary_file.name,
        "rollback_checksums_verified": sorted(original_checksums),
        "reupgrade_checksums_verified": True,
    }


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="aimilivpn-release-drill-") as tmp:
        result = run_drill(Path(tmp))
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
