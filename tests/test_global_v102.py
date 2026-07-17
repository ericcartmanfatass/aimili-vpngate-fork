from __future__ import annotations

import base64
import json
import shutil
import tempfile
import threading
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from aimilivpn.core.global_backup import BackupValidationError, build_backup_payload, preview_backup, validate_backup_payload
from aimilivpn.core.global_config import GlobalConfigError, load_global_settings, public_global_settings, save_global_settings
from aimilivpn.core.global_quality import QualityBatchProcessor
from aimilivpn.core.global_storage import GlobalRepository
from aimilivpn.system.global_console import GlobalConsoleRuntime
from aimilivpn.system.global_scheduler import GlobalScheduler
from aimilivpn.system.service_runtime import Tee


def api_text(*ips: str) -> str:
    encoded = base64.b64encode(b"client\nproto tcp\nremote 203.0.113.1 443\n").decode("ascii")
    header = "#HostName,IP,Score,Ping,Speed,CountryLong,CountryShort,NumVpnSessions,OpenVPN_ConfigData_Base64"
    rows = [f"node-{index},{ip},100,20,1000,Japan,JP,3,{encoded}" for index, ip in enumerate(ips)]
    return "\n".join([header, *rows]) + "\n"


def country_api_text(*entries: tuple[str, str]) -> str:
    encoded = base64.b64encode(b"client\nproto tcp\nremote 203.0.113.1 443\n").decode("ascii")
    header = "#HostName,IP,Score,Ping,Speed,CountryLong,CountryShort,NumVpnSessions,OpenVPN_ConfigData_Base64"
    rows = [
        f"node-{index},{ip},100,20,1000,{country} VPN,{country},3,{encoded}"
        for index, (country, ip) in enumerate(entries)
    ]
    return "\n".join([header, *rows]) + "\n"


class GlobalV102Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def test_global_defaults_are_versioned_and_api_key_is_separate(self) -> None:
        save_global_settings(
            self.root,
            {"scamalytics_enabled": True, "scamalytics_username": "user"},
            scamalytics_api_key="secret-key",
        )

        public = public_global_settings(self.root)
        self.assertEqual(load_global_settings(self.root).vpn_gate_schedule_time, "03:30")
        self.assertTrue(public["scamalytics_api_key_configured"])
        self.assertNotIn("secret-key", (self.root / "global_settings.json").read_text(encoding="utf-8"))
        self.assertNotIn("secret-key", json.dumps(public))

    def test_global_settings_reject_invalid_schedule_and_url(self) -> None:
        with self.assertRaises(GlobalConfigError):
            save_global_settings(self.root, {"vpn_gate_schedule_time": "25:00"})
        with self.assertRaises(GlobalConfigError):
            save_global_settings(self.root, {"vpn_gate_api_url": "https://user:pass@example.test/api"})

    def test_scheduler_deduplicates_ips_and_publishes_snapshot(self) -> None:
        published: list[list[dict[str, object]]] = []
        scheduler = GlobalScheduler(
            self.root,
            self.root / "data",
            fetcher=lambda: api_text("203.0.113.1", "203.0.113.1", "203.0.113.2"),
            clock=lambda: 1000.0,
            publish=published.append,
        )

        result = scheduler.run_once()

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["node_count"], 2)
        self.assertEqual(len(scheduler.read_nodes()), 2)
        self.assertEqual(len(published), 1)
        self.assertTrue((self.root / "data" / "global" / "country_index.json").exists())

    def test_empty_response_preserves_previous_snapshot_and_uses_backoff(self) -> None:
        responses = iter([api_text("203.0.113.1"), "bad response"])
        now = [1000.0]
        scheduler = GlobalScheduler(self.root, self.root / "data", fetcher=lambda: next(responses), clock=lambda: now[0])

        self.assertEqual(scheduler.run_once()["status"], "ok")
        now[0] = 2000.0
        failed = scheduler.run_once()

        self.assertEqual(failed["status"], "error")
        self.assertEqual(failed["error_code"], "invalid_response")
        self.assertEqual(len(scheduler.read_nodes()), 1)
        self.assertGreater(failed["next_run_at"], now[0])

    def test_missing_country_is_retained_for_grace_then_expires(self) -> None:
        responses = iter(
            [
                country_api_text(("JP", "203.0.113.1"), ("US", "203.0.113.2")),
                country_api_text(("JP", "203.0.113.3")),
                country_api_text(("JP", "203.0.113.4")),
            ]
        )
        now = [1000.0]
        scheduler = GlobalScheduler(
            self.root,
            self.root / "data",
            fetcher=lambda: next(responses),
            clock=lambda: now[0],
        )

        self.assertEqual(scheduler.run_once()["status"], "ok")
        now[0] = 2000.0
        self.assertEqual(scheduler.run_once()["status"], "ok")
        retained = {item["server_ip"]: item for item in scheduler.read_nodes()}
        self.assertIn("203.0.113.2", retained)
        self.assertTrue(retained["203.0.113.2"]["snapshot_country_stale"])
        self.assertIn("US", scheduler.status()["country_snapshot_stale_countries"])

        now[0] = 1000.0 + 48 * 3600 + 1
        self.assertEqual(scheduler.run_once()["status"], "ok")
        self.assertNotIn("203.0.113.2", {item["server_ip"] for item in scheduler.read_nodes()})
        self.assertIn("US", scheduler.status()["country_expired_countries"])

    def test_scheduler_run_is_guarded_by_process_lock(self) -> None:
        scheduler = GlobalScheduler(self.root, self.root / "data", fetcher=lambda: api_text("203.0.113.1"))
        self.assertTrue(scheduler._thread_lock.acquire(blocking=False))
        try:
            self.assertEqual(scheduler.run_once()["status"], "already_running")
        finally:
            scheduler._thread_lock.release()

    def test_quality_batch_deduplicates_cache_and_quota(self) -> None:
        calls: list[str] = []
        nodes = [{"ip": "203.0.113.1"}, {"ip": "203.0.113.1"}, {"ip": "203.0.113.2"}]
        processor = QualityBatchProcessor(self.root / "quality.json", rate_limit_per_minute=1, now=lambda: 1000.0)

        first = processor.run(nodes, lambda ip: calls.append(ip) or {"risk_score": 10, "raw_response": {"secret": "x"}})
        second = processor.run(nodes, lambda ip: calls.append(ip) or {"risk_score": 20})

        self.assertEqual(first.to_dict(), {"unique_ips": 2, "cache_hits": 0, "requested": 1, "failed": 0, "deferred": 1})
        self.assertEqual(second.cache_hits, 1)
        self.assertEqual(second.requested, 1)
        self.assertEqual(second.deferred, 0)
        self.assertEqual(calls, ["203.0.113.1", "203.0.113.2"])
        self.assertNotIn("secret", (self.root / "quality.json").read_text(encoding="utf-8"))

    def test_backup_preview_and_validation_reject_secrets_and_system_resources(self) -> None:
        payload = build_backup_payload(
            global_settings={"vpn_gate_enabled": True, "scamalytics_api_key": "secret"},
            instances=[{"id": "jp", "country": "JP"}],
        )
        self.assertNotIn("secret", json.dumps(payload))
        self.assertFalse(preview_backup(payload, payload)["changed"])
        unsafe = dict(payload)
        unsafe["instances"] = [{"id": "jp", "country": "JP", "service": "ssh.service"}]
        with self.assertRaises(BackupValidationError):
            validate_backup_payload(unsafe)

    def test_text_log_rotates_by_size(self) -> None:
        path = self.root / "vpngate.log"
        tee = Tee(str(path), stdout=StringIO(), max_bytes=32, backup_count=2)
        try:
            tee.write("a" * 20)
            tee.write("b" * 20)
            tee.flush()
        finally:
            tee.file.close()
        self.assertTrue(path.exists())
        self.assertTrue(path.with_name("vpngate.log.1").exists())

    def test_global_sqlite_repository_survives_restart_and_uses_domain_tables(self) -> None:
        root = self.root / "global"
        first = GlobalRepository(root, backend="sqlite")
        nodes = [
            {"id": "jp-1", "server_ip": "203.0.113.1", "country_short": "JP", "config_text": "secret config"},
            {"id": "us-1", "server_ip": "203.0.113.2", "country_short": "US"},
        ]
        first.replace_nodes(nodes, updated_at=1000.0)
        first.upsert_quality("203.0.113.1", {"status": "ok", "risk_score": 12, "raw_response": {"secret": "x"}})
        first.write_task_state({"status": "ok", "last_success_at": 1000.0})
        first.append_history({"status": "ok", "at": 1000.0, "node_count": 2})

        second = GlobalRepository(root, backend="sqlite")
        self.assertEqual([item["id"] for item in second.read_nodes()], ["jp-1", "us-1"])
        self.assertEqual(second.snapshot_updated_at(), 1000.0)
        self.assertEqual(second.get_quality("203.0.113.1")["risk_score"], 12)  # type: ignore[index]
        self.assertEqual(second.read_task_state()["status"], "ok")
        self.assertEqual(len(second.read_history()), 1)
        self.assertNotIn("secret config", json.dumps(second.read_nodes()))
        self.assertNotIn("secret", json.dumps(second.read_quality()))

        import sqlite3

        conn = sqlite3.connect(root / "global.db")
        try:
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        finally:
            conn.close()
        self.assertTrue({
            "global_nodes",
            "global_quality_results",
            "global_job_history",
            "global_task_state",
            "global_settings",
        } <= tables)

    def test_global_json_fallback_rejects_sensitive_settings(self) -> None:
        repository = GlobalRepository(self.root / "global-json")
        repository.replace_nodes([{"id": "jp-1", "server_ip": "203.0.113.1"}], updated_at=1000.0)
        repository.upsert_quality("203.0.113.1", {"status": "ok", "risk_score": 9})
        repository.write_settings({"vpn_gate_enabled": True})

        with self.assertRaises(ValueError):
            repository.write_settings({"scamalytics_api_key": "secret"})
        self.assertEqual(repository.read_nodes()[0]["id"], "jp-1")
        self.assertEqual(repository.read_quality()["203.0.113.1"]["risk_score"], 9)

    def test_scheduler_restarts_from_sqlite_task_state_and_snapshot(self) -> None:
        root = self.root / "scheduler"
        repository = GlobalRepository(root / "data" / "global", backend="sqlite")
        first = GlobalScheduler(
            root,
            root / "data",
            repository=repository,
            fetcher=lambda: api_text("203.0.113.1"),
            clock=lambda: 1000.0,
        )
        self.assertEqual(first.run_once()["status"], "ok")

        restarted = GlobalScheduler(
            root,
            root / "data",
            repository=GlobalRepository(root / "data" / "global", backend="sqlite"),
            fetcher=lambda: api_text("203.0.113.2"),
            clock=lambda: 1000.0,
        )
        self.assertEqual(restarted.status()["last_success_at"], 1000.0)
        self.assertEqual(restarted.read_nodes()[0]["server_ip"], "203.0.113.1")
        self.assertEqual(len(restarted.repository.read_history()), 1)

    def test_quality_batch_persists_deferred_queue_and_retries_after_restart(self) -> None:
        repository = GlobalRepository(self.root / "quality-global", backend="sqlite")
        calls: list[str] = []
        nodes = [{"server_ip": "203.0.113.1"}, {"server_ip": "203.0.113.2"}]
        first = QualityBatchProcessor(
            self.root / "unused.json",
            rate_limit_per_minute=1,
            now=lambda: 1000.0,
            repository=repository,
        )
        summary = first.run(nodes, lambda ip: calls.append(ip) or {"risk_score": 10})
        self.assertEqual(summary.deferred, 1)
        self.assertEqual([item["ip"] for item in repository.read_quality_queue()], ["203.0.113.2"])

        restarted = QualityBatchProcessor(
            self.root / "unused.json",
            rate_limit_per_minute=1,
            now=lambda: 1000.0,
            repository=GlobalRepository(self.root / "quality-global", backend="sqlite"),
        )
        restarted.run(nodes, lambda ip: calls.append(ip) or {"risk_score": 20})
        self.assertEqual(calls, ["203.0.113.1", "203.0.113.2"])
        self.assertEqual(restarted.repository.read_quality()["203.0.113.2"]["risk_score"], 20)  # type: ignore[union-attr]
        self.assertEqual(restarted.repository.read_quality_queue(), [])

    def test_quality_batch_persists_failure_backoff(self) -> None:
        repository = GlobalRepository(self.root / "quality-retry", backend="sqlite")
        now = [1000.0]
        processor = QualityBatchProcessor(
            self.root / "unused.json",
            now=lambda: now[0],
            repository=repository,
            retry_backoff_seconds=(300, 600),
        )
        processor.run([{"server_ip": "203.0.113.3"}], lambda ip: (_ for _ in ()).throw(RuntimeError("offline")))
        queued = repository.read_quality_queue()[0]
        self.assertEqual(queued["attempts"], 1)
        self.assertEqual(queued["next_attempt_at"], 1300.0)
        now[0] = 1100.0
        self.assertEqual(processor.run([{"server_ip": "203.0.113.3"}], lambda ip: {"risk_score": 1}).deferred, 1)
        now[0] = 1300.0
        self.assertEqual(processor.run([{"server_ip": "203.0.113.3"}], lambda ip: {"risk_score": 1}).requested, 1)
        self.assertEqual(repository.read_quality_queue(), [])

    def test_quality_batch_persists_daily_quota_metrics_and_resets_by_day(self) -> None:
        repository = GlobalRepository(self.root / "quality-metrics", backend="sqlite")
        now = [1000.0]
        processor = QualityBatchProcessor(
            self.root / "unused.json",
            rate_limit_per_minute=10,
            daily_quota=1,
            now=lambda: now[0],
            repository=repository,
        )
        first = processor.run(
            [{"server_ip": "203.0.113.1"}, {"server_ip": "203.0.113.2"}],
            lambda ip: {"risk_score": 10},
        )
        self.assertEqual(first.requested, 1)
        self.assertEqual(first.deferred, 1)
        self.assertEqual(repository.read_quality_metrics()["remaining"], 0)
        self.assertEqual(repository.read_quality_metrics()["requests"], 1)

        now[0] = 87400.0
        second = processor.run(
            [{"server_ip": "203.0.113.1"}, {"server_ip": "203.0.113.2"}],
            lambda ip: {"risk_score": 20},
        )
        self.assertEqual(second.requested, 1)
        metrics = repository.read_quality_metrics()
        self.assertEqual(metrics["requests"], 1)
        self.assertEqual(metrics["cache_hits"], 1)
        self.assertEqual(metrics["remaining"], 0)

    def test_full_console_restore_writes_business_data_and_clears_queue(self) -> None:
        config_dir = self.root / "config"
        install_dir = self.root / "install"
        repository = GlobalRepository(install_dir / "data" / "global", backend="sqlite")
        scheduler = GlobalScheduler(
            config_dir,
            install_dir / "data",
            repository=repository,
            fetcher=lambda: api_text("203.0.113.9"),
            clock=lambda: 2000.0,
        )
        runtime = GlobalConsoleRuntime(config_dir, install_dir, scheduler)
        save_global_settings(config_dir, {"vpn_gate_enabled": True})
        repository.replace_nodes([{"id": "old-1", "server_ip": "203.0.113.1", "country_short": "JP"}], updated_at=1000.0)
        repository.upsert_quality("203.0.113.1", {"status": "ok", "risk_score": 12, "checked_at": 1000.0})
        repository.write_quality_metrics({"date": "old", "quota": 10, "requests": 2, "remaining": 8})
        repository.enqueue_quality_ips(["203.0.113.1"], now=1000.0)
        repository.append_history({"status": "old", "at": 1000.0})
        runtime.scheduler.snapshot_dir.mkdir(parents=True, exist_ok=True)
        (runtime.scheduler.snapshot_dir / "blacklist.json").write_text(
            json.dumps({"old-1": {"reason": "old"}}), encoding="utf-8"
        )

        candidate = build_backup_payload(
            global_settings={"vpn_gate_enabled": False},
            instances=[],
            regions=[],
            backup_type="full",
            nodes=[{"id": "new-1", "server_ip": "203.0.113.2", "country_short": "US"}],
            quality_results=[{"ip": "203.0.113.2", "status": "ok", "risk_score": 4, "checked_at": 2000.0}],
            blacklist={"new-1": {"reason": "new"}},
            job_history=[{"status": "new", "at": 2000.0}],
            quality_metrics={"date": "new", "quota": 20, "requests": 3, "remaining": 17},
        )

        with patch("aimilivpn.system.global_console.load_instances", return_value=[]):
            result = runtime.restore(candidate, confirmed=True)

        self.assertTrue(result["ok"])
        self.assertEqual([item["id"] for item in repository.read_nodes()], ["new-1"])
        self.assertEqual(repository.read_quality()["203.0.113.2"]["risk_score"], 4)
        self.assertEqual(repository.read_quality_queue(), [])
        self.assertEqual(repository.read_history()[0]["status"], "new")
        self.assertEqual(repository.read_quality_metrics()["remaining"], 17)
        restored_blacklist = json.loads((runtime.scheduler.snapshot_dir / "blacklist.json").read_text(encoding="utf-8"))
        self.assertEqual(restored_blacklist["new-1"]["reason"], "new")
        self.assertFalse((runtime.scheduler.snapshot_dir / "restored_business_data.json").exists())


if __name__ == "__main__":
    unittest.main()
