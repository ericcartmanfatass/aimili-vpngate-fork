from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from aimilivpn.core.maintenance import (
    ensure_node_config_files,
    format_fetch_error_message,
    format_maintenance_status_report,
    maintenance_node_status,
    maintenance_recovery_action,
    merge_candidate_nodes,
    select_maintenance_test_nodes,
    should_auto_connect_after_maintenance,
    should_diagnose_fetch_error,
)


def parse_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


class MaintenanceSelectionTests(unittest.TestCase):
    def test_selects_untested_before_stale_nodes_by_priority(self) -> None:
        nodes = [
            {"id": "active", "active": True, "probe_status": "not_checked", "ping": 1, "score": 999},
            {"id": "slow", "probe_status": "not_checked", "ping": 300, "score": 10},
            {"id": "fast", "probe_status": "not_checked", "ping": 20, "score": 10},
            {"id": "stale", "probe_status": "available", "probed_at": 10, "ping": 1, "score": 500},
        ]

        selected = select_maintenance_test_nodes(
            nodes,
            now=1000,
            routing_mode="auto",
            force_country="",
            node_matches_allowed=lambda node: True,
            filter_nodes_by_routing_region=lambda items, target: items,
            parse_int=parse_int,
            retest_interval_seconds=100,
            max_nodes=10,
        )

        self.assertEqual(selected, ["fast", "slow", "stale"])

    def test_skips_fresh_available_and_unavailable_nodes(self) -> None:
        nodes = [
            {"id": "fresh-ok", "probe_status": "available", "probed_at": 950},
            {"id": "fresh-bad", "probe_status": "unavailable", "probed_at": 950},
            {"id": "old-ok", "probe_status": "available", "probed_at": 100},
            {"id": "old-bad", "probe_status": "unavailable", "probed_at": 100},
        ]

        selected = select_maintenance_test_nodes(
            nodes,
            now=1000,
            routing_mode="auto",
            force_country="",
            node_matches_allowed=lambda node: True,
            filter_nodes_by_routing_region=lambda items, target: items,
            parse_int=parse_int,
            retest_interval_seconds=100,
            max_nodes=10,
        )

        self.assertEqual(selected, ["old-ok", "old-bad"])

    def test_applies_region_filter_and_limit(self) -> None:
        nodes = [
            {"id": "jp-1", "country_short": "JP", "probe_status": "not_checked"},
            {"id": "jp-2", "country_short": "JP", "probe_status": "not_checked"},
            {"id": "us-1", "country_short": "US", "probe_status": "not_checked"},
        ]

        selected = select_maintenance_test_nodes(
            nodes,
            now=1000,
            routing_mode="fixed_region",
            force_country="JP",
            node_matches_allowed=lambda node: True,
            filter_nodes_by_routing_region=lambda items, target: [
                item for item in items if item.get("country_short") == target
            ],
            parse_int=parse_int,
            retest_interval_seconds=100,
            max_nodes=1,
        )

        self.assertEqual(selected, ["jp-1"])

    def test_skips_disallowed_nodes(self) -> None:
        nodes = [
            {"id": "jp", "country_short": "JP", "probe_status": "not_checked"},
            {"id": "us", "country_short": "US", "probe_status": "not_checked"},
        ]

        selected = select_maintenance_test_nodes(
            nodes,
            now=1000,
            routing_mode="auto",
            force_country="",
            node_matches_allowed=lambda node: node.get("country_short") == "JP",
            filter_nodes_by_routing_region=lambda items, target: items,
            parse_int=parse_int,
            retest_interval_seconds=100,
            max_nodes=10,
        )

        self.assertEqual(selected, ["jp"])

    def test_merge_candidate_nodes_keeps_active_first_and_deduplicates(self) -> None:
        merged = merge_candidate_nodes(
            [
                {"id": "active", "score": 1},
                {"id": "new1"},
                {"id": "new2"},
            ],
            active_node={"id": "active", "active": True},
            max_nodes=2,
        )

        self.assertEqual([node["id"] for node in merged], ["active", "new1"])
        self.assertTrue(merged[0]["active"])

    def test_ensure_node_config_files_writes_missing_files(self) -> None:
        with TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "node.ovpn"
            existing_path = Path(tmp) / "existing.ovpn"
            existing_path.write_text("old", encoding="utf-8")
            written: list[tuple[Path, str]] = []

            def write_config(path: Path, config_text: str) -> None:
                written.append((path, config_text))
                path.write_text(config_text, encoding="utf-8")

            ensure_node_config_files(
                [
                    {"id": "new", "config_file": str(config_path), "config_text": "client\n"},
                    {"id": "old", "config_file": str(existing_path), "config_text": "ignored\n"},
                    {"id": "missing"},
                ],
                write_config=write_config,
            )

            self.assertEqual(written, [(config_path, "client\n")])
            self.assertEqual(config_path.read_text(encoding="utf-8"), "client\n")
            self.assertEqual(existing_path.read_text(encoding="utf-8"), "old")

    def test_maintenance_node_status_counts_allowed_nodes(self) -> None:
        status = maintenance_node_status(
            [
                {"id": "ok-jp", "country_short": "JP", "probe_status": "available"},
                {"id": "bad-jp", "country_short": "JP", "probe_status": "unavailable"},
                {"id": "ok-us", "country_short": "US", "probe_status": "available"},
                {"id": "active", "active": True, "probe_status": "available"},
            ],
            node_matches_allowed=lambda node: node.get("country_short") in ("JP", None),
        )

        self.assertEqual(status["available_node_ids"], ["ok-jp", "active"])
        self.assertEqual(status["unavailable_node_ids"], ["bad-jp"])
        self.assertEqual(status["active_node_id"], "active")
        self.assertEqual(status["valid_nodes_count"], 2)

    def test_format_maintenance_status_report_includes_counts(self) -> None:
        report = format_maintenance_status_report(
            total_nodes=3,
            available_node_ids=["a", "b"],
            unavailable_node_ids=["c"],
            active_node_id="a",
        )

        self.assertIn("候选节点共 3 个", report)
        self.assertIn("【可用节点】2 个", report)
        self.assertIn("【不可用节点】1 个", report)
        self.assertIn("活动连接节点】为: a", report)

    def test_should_auto_connect_after_maintenance_requires_enabled_connection(self) -> None:
        nodes = [{"id": "ok", "probe_status": "available"}]

        should_connect = should_auto_connect_after_maintenance(
            nodes,
            ui_config={"connection_enabled": False},
            node_matches_allowed=lambda node: True,
            filter_nodes_by_routing_region=lambda items, target: items,
            parse_int=parse_int,
        )

        self.assertFalse(should_connect)

    def test_should_auto_connect_after_maintenance_skips_fixed_ip_mode(self) -> None:
        nodes = [{"id": "ok", "probe_status": "available"}]

        should_connect = should_auto_connect_after_maintenance(
            nodes,
            ui_config={"routing_mode": "fixed_ip"},
            node_matches_allowed=lambda node: True,
            filter_nodes_by_routing_region=lambda items, target: items,
            parse_int=parse_int,
        )

        self.assertFalse(should_connect)

    def test_should_auto_connect_after_maintenance_uses_routing_filters(self) -> None:
        nodes = [
            {"id": "jp", "country_short": "JP", "probe_status": "available", "ip_type": "hosting"},
            {"id": "us", "country_short": "US", "probe_status": "available", "ip_type": "residential"},
        ]

        should_connect = should_auto_connect_after_maintenance(
            nodes,
            ui_config={"routing_mode": "fixed_region", "force_country": "US", "routing_ip_type": "residential"},
            node_matches_allowed=lambda node: True,
            filter_nodes_by_routing_region=lambda items, target: [
                item for item in items if item.get("country_short") == target
            ],
            parse_int=parse_int,
        )

        self.assertTrue(should_connect)

    def test_should_auto_connect_after_maintenance_honors_favorite_no_fallback(self) -> None:
        nodes = [{"id": "ok", "probe_status": "available"}]

        should_connect = should_auto_connect_after_maintenance(
            nodes,
            ui_config={
                "routing_mode": "favorites",
                "favorite_node_ids": ["missing"],
                "fav_fail_fallback": False,
            },
            node_matches_allowed=lambda node: True,
            filter_nodes_by_routing_region=lambda items, target: items,
            parse_int=parse_int,
        )

        self.assertFalse(should_connect)

    def test_maintenance_recovery_action_reconnects_fixed_ip_target(self) -> None:
        action = maintenance_recovery_action(
            ui_config={"connection_enabled": True, "routing_mode": "fixed_ip", "fixed_node_id": "jp"},
            nodes=[{"id": "jp"}],
            active_node_id="",
            openvpn_running=False,
        )

        self.assertEqual(action, {"action": "reconnect_fixed", "target_id": "jp"})

    def test_maintenance_recovery_action_skips_when_disabled_or_running(self) -> None:
        self.assertEqual(
            maintenance_recovery_action(
                ui_config={"connection_enabled": False, "routing_mode": "auto"},
                nodes=[{"id": "jp"}],
                active_node_id="jp",
                openvpn_running=False,
            ),
            {"action": "none", "target_id": ""},
        )
        self.assertEqual(
            maintenance_recovery_action(
                ui_config={"connection_enabled": True, "routing_mode": "fixed_ip", "fixed_node_id": "jp"},
                nodes=[{"id": "jp"}],
                active_node_id="",
                openvpn_running=True,
            ),
            {"action": "none", "target_id": ""},
        )

    def test_maintenance_recovery_action_auto_switches_after_lost_process(self) -> None:
        action = maintenance_recovery_action(
            ui_config={"connection_enabled": True, "routing_mode": "auto"},
            nodes=[{"id": "old"}],
            active_node_id="old",
            openvpn_running=False,
        )

        self.assertEqual(action, {"action": "auto_switch_after_lost_process", "target_id": "old"})

    def test_fetch_error_helpers_keep_existing_diagnostic_codes(self) -> None:
        self.assertFalse(should_diagnose_fetch_error("[ERR_TIMEOUT] failed"))
        self.assertFalse(should_diagnose_fetch_error("[错误代码 1001] failed"))
        self.assertTrue(should_diagnose_fetch_error("network down"))

        calls: list[str] = []

        def diagnose(url: str) -> tuple[int, str]:
            calls.append(url)
            return 1001, "dns failed"

        self.assertEqual(
            format_fetch_error_message(
                RuntimeError("[ERR_TIMEOUT] failed"),
                api_url="https://example.test",
                diagnose_api_failure=diagnose,
            ),
            "[ERR_TIMEOUT] failed",
        )
        self.assertEqual(calls, [])
        self.assertEqual(
            format_fetch_error_message(
                RuntimeError("network down"),
                api_url="https://example.test",
                diagnose_api_failure=diagnose,
            ),
            "[错误代码 1001] 获取节点失败: network down | 诊断结果: dns failed",
        )
        self.assertEqual(calls, ["https://example.test"])


if __name__ == "__main__":
    unittest.main()
