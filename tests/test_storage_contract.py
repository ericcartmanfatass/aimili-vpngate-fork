from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from aimilivpn.core.models import QualityResult, RegionProfile
from aimilivpn.core.storage import (
    JsonStore,
    NodeRepository,
    QualityRepository,
    RegionRepository,
    SettingsRepository,
    SqliteStore,
    StorageValidationError,
    migrate_json_to_sqlite,
)
from aimilivpn.system.manager_wiring_factories_foundation import build_repositories


SAFE_CONFIG = """client
dev tun
proto udp
remote 203.0.113.10 1194
nobind
<ca>
certificate
</ca>
"""


def quality(node_id: str = "jp_1") -> QualityResult:
    return QualityResult(
        node_id=node_id,
        exit_ip="203.0.113.10",
        tcp_latency_ms=50,
        openvpn_success=True,
        handshake_ms=1000,
        risk_provider="scamalytics",
        risk_score=20,
        risk_level="low",
        proxy_detected=False,
        datacenter_detected=False,
        country_match=True,
        checked_at="2026-07-13T00:00:00Z",
        raw_response={"secret": "server-only"},
        score=90,
        label="Excellent",
    )


class FailingSqliteStore(SqliteStore):
    def __init__(self, db_path: Path) -> None:
        super().__init__(db_path)
        self.upserts = 0

    def _upsert(self, conn, document_key, payload, kind, count, checksum) -> None:  # type: ignore[no-untyped-def]
        self.upserts += 1
        if self.upserts == 2:
            raise sqlite3.OperationalError("injected migration failure")
        SqliteStore._upsert(conn, document_key, payload, kind, count, checksum)


class StorageContractTests(unittest.TestCase):
    def test_json_and_sqlite_share_repository_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stores = [JsonStore(), SqliteStore(root / "aimilivpn.db")]
            for index, store in enumerate(stores):
                with self.subTest(store=type(store).__name__):
                    prefix = Path(f"backend-{index}") if isinstance(store, SqliteStore) else root / f"backend-{index}"
                    nodes = NodeRepository(prefix / "nodes.json", store=store)
                    regions = RegionRepository(prefix / "regions.json", store=store)
                    qualities = QualityRepository(prefix / "quality.json", store=store)
                    settings = SettingsRepository(prefix / "settings.json", store=store)
                    nodes.replace_all_dicts([{"id": "jp_1", "country_short": "JP"}])
                    regions.create(RegionProfile(id="jp", name="Japan", country_codes=["JP"]))
                    qualities.save(quality())
                    settings.set("proxy_port", 7928)

                    self.assertEqual(nodes.list_node_dicts()[0]["id"], "jp_1")
                    self.assertEqual(regions.get("jp").name, "Japan")  # type: ignore[union-attr]
                    self.assertEqual(qualities.latest_for_node("jp_1").risk_score, 20)  # type: ignore[union-attr]
                    self.assertEqual(settings.get("proxy_port"), 7928)

    def test_json_schema_metadata_detects_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nodes.json"
            repo = NodeRepository(path)
            repo.replace_all_dicts([{"id": "jp_1", "country_short": "JP"}])
            path.write_text(json.dumps([{"id": "us_1", "country_short": "US"}]), encoding="utf-8")

            with self.assertRaisesRegex(StorageValidationError, "checksum"):
                repo.list_node_dicts()

    def test_migration_backs_up_and_reports_counts_and_checksums(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            nodes_path = root / "nodes.json"
            settings_path = root / "settings.json"
            nodes_path.write_text(json.dumps([{"id": "jp_1"}]), encoding="utf-8")
            settings_path.write_text(json.dumps({"proxy_port": 7928}), encoding="utf-8")
            store = SqliteStore(root / "aimilivpn.db")

            summary = migrate_json_to_sqlite(
                {nodes_path: "nodes", settings_path: "settings"},
                store,
                clock=lambda: datetime(2026, 7, 13, tzinfo=timezone.utc),
            )

            self.assertIsNotNone(summary)
            assert summary is not None
            self.assertEqual(summary.total_count, 2)
            self.assertTrue(Path(summary.backup_dir, "nodes.json").exists())
            self.assertTrue(Path(summary.backup_dir, "migration-summary.json").exists())
            self.assertEqual(NodeRepository(nodes_path, store=store).list_node_dicts()[0]["id"], "jp_1")
            self.assertTrue(all(len(item.checksum) == 64 for item in summary.documents))

    def test_sqlite_repository_bootstrap_automatically_migrates_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = SimpleNamespace(
                nodes_file=root / "nodes.json",
                regions_file=root / "regions.json",
                quality_results_file=root / "quality.json",
                settings_file=root / "settings.json",
                blacklist_file=root / "blacklist.json",
            )
            paths.nodes_file.write_text(json.dumps([{"id": "jp_1"}]), encoding="utf-8")

            repositories = build_repositories(
                paths,
                storage_backend="sqlite",
                sqlite_db_path=root / "aimilivpn.db",
            )

            self.assertEqual(repositories.node_repository.list_node_dicts()[0]["id"], "jp_1")
            store = repositories.node_repository.store
            self.assertIsInstance(store, SqliteStore)
            assert isinstance(store, SqliteStore)
            self.assertIsNotNone(store.last_migration_summary)
            self.assertTrue(Path(store.last_migration_summary.backup_dir).exists())  # type: ignore[union-attr]

    def test_migration_failure_rolls_back_all_documents(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            nodes_path = root / "nodes.json"
            settings_path = root / "settings.json"
            nodes_path.write_text(json.dumps([{"id": "jp_1"}]), encoding="utf-8")
            settings_path.write_text(json.dumps({"proxy_port": 7928}), encoding="utf-8")
            store = FailingSqliteStore(root / "aimilivpn.db")

            with self.assertRaises(sqlite3.OperationalError):
                migrate_json_to_sqlite({nodes_path: "nodes", settings_path: "settings"}, store)

            conn = sqlite3.connect(store.db_path)
            try:
                count = conn.execute("SELECT COUNT(*) FROM json_documents").fetchone()[0]
            finally:
                conn.close()
            self.assertEqual(count, 0)

    def test_sensitive_raw_response_and_openvpn_config_stay_out_of_sqlite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = SqliteStore(root / "aimilivpn.db")
            nodes = NodeRepository(root / "nodes.json", store=store)
            qualities = QualityRepository(root / "quality.json", store=store)
            nodes.replace_all_dicts([{
                "id": "jp_1",
                "country_short": "JP",
                "config_text": SAFE_CONFIG,
            }])
            qualities.save(quality())

            conn = sqlite3.connect(store.db_path)
            try:
                payloads = "\n".join(str(row[0]) for row in conn.execute("SELECT payload FROM json_documents"))
            finally:
                conn.close()
            self.assertNotIn("certificate", payloads)
            self.assertNotIn("server-only", payloads)
            self.assertTrue((root / "configs" / "jp_1.ovpn").exists())
            self.assertIn("remote 203.0.113.10 1194", nodes.list_node_dicts()[0]["config_text"])

    def test_sensitive_settings_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = SettingsRepository(Path(tmp) / "settings.json")

            with self.assertRaisesRegex(StorageValidationError, "sensitive setting"):
                settings.set("proxy_password", "secret")


if __name__ == "__main__":
    unittest.main()
