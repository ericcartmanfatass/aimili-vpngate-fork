from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from aimilivpn.core.blacklist import blacklist_entry, clean_blacklist
from aimilivpn.core.connection import (
    auto_switch_block_reason,
    auto_switch_connect_message,
    auto_switch_no_candidate_message,
    auto_switch_retry_message,
    build_proxy_url,
    clear_active_flags,
    connection_failure_state,
    connection_success_state,
    delete_file_if_exists,
    enable_connection_config,
    find_active_config_file,
    latency_label,
    mark_active_node,
    mark_connection_active,
    mark_connection_failed,
    measure_node_latency,
    normalize_node_id,
    prepare_connection_target,
    require_connectable_node,
    should_clear_failed_connection,
)
from aimilivpn.core.nodes import select_auto_switch_candidates, sort_nodes_for_display


def parse_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


class NodeCoreTests(unittest.TestCase):
    def test_connection_preflight_helpers(self) -> None:
        nodes = [{"id": "jp1", "country_short": "JP"}, {"id": "us1", "country_short": "US"}]

        self.assertEqual(normalize_node_id("  jp1 "), "jp1")
        with self.assertRaisesRegex(ValueError, "Node id is required"):
            normalize_node_id("")

        node = require_connectable_node(
            nodes,
            "jp1",
            node_matches_allowed=lambda item: item.get("country_short") == "JP",
            allowed_countries={"JP"},
        )
        self.assertIs(node, nodes[0])

        with self.assertRaisesRegex(ValueError, "Node not found: missing"):
            require_connectable_node(
                nodes,
                "missing",
                node_matches_allowed=lambda item: True,
                allowed_countries={"JP"},
            )

        with self.assertRaisesRegex(ValueError, "outside this instance allowed countries"):
            require_connectable_node(
                nodes,
                "us1",
                node_matches_allowed=lambda item: item.get("country_short") == "JP",
                allowed_countries={"JP"},
            )

    def test_enable_connection_config_updates_fixed_ip_target(self) -> None:
        config = {"routing_mode": "fixed_ip", "connection_enabled": False}

        returned = enable_connection_config(config, "jp1")

        self.assertIs(returned, config)
        self.assertTrue(config["connection_enabled"])
        self.assertEqual(config["fixed_node_id"], "jp1")

    def test_prepare_connection_target_validates_node_and_updates_ui_config(self) -> None:
        nodes = [{"id": "jp1", "country_short": "JP"}]
        ui_config = {"routing_mode": "fixed_ip", "connection_enabled": False}

        node, updated_config = prepare_connection_target(
            nodes,
            "jp1",
            ui_config,
            node_matches_allowed=lambda item: item.get("country_short") == "JP",
            allowed_countries={"JP"},
        )

        self.assertIs(node, nodes[0])
        self.assertIs(updated_config, ui_config)
        self.assertTrue(updated_config["connection_enabled"])
        self.assertEqual(updated_config["fixed_node_id"], "jp1")

    def test_connection_state_helpers_build_expected_state(self) -> None:
        self.assertEqual(
            connection_failure_state("openvpn failed"),
            {
                "active_openvpn_node_id": "",
                "is_connecting": False,
                "active_node_latency": "无活动连接",
                "last_check_message": "连接失败: openvpn failed",
            },
        )
        self.assertEqual(
            connection_success_state("jp1", latency_ms=42, timeout_label="检测超时"),
            {
                "active_openvpn_node_id": "jp1",
                "is_connecting": False,
                "last_check_message": "Connected jp1",
                "active_node_latency": "42 ms",
            },
        )
        self.assertEqual(
            connection_success_state("jp1", latency_ms=0, timeout_label="检测超时")["active_node_latency"],
            "检测超时",
        )

    def test_should_clear_failed_connection_matches_existing_policy(self) -> None:
        self.assertTrue(
            should_clear_failed_connection(
                stopped_existing=True,
                active_node_id="old",
                requested_node_id="new",
                active_running=True,
            )
        )
        self.assertTrue(
            should_clear_failed_connection(
                stopped_existing=False,
                active_node_id="new",
                requested_node_id="new",
                active_running=False,
            )
        )

    def test_delete_file_if_exists_removes_existing_file_and_ignores_missing(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "node.ovpn"
            path.write_text("client\n", encoding="utf-8")

            self.assertTrue(delete_file_if_exists(path))
            self.assertFalse(path.exists())
            self.assertFalse(delete_file_if_exists(path))
            self.assertFalse(delete_file_if_exists(None))
        self.assertFalse(
            should_clear_failed_connection(
                stopped_existing=False,
                active_node_id="old",
                requested_node_id="new",
                active_running=False,
            )
        )

    def test_auto_switch_helpers_report_block_reasons_and_messages(self) -> None:
        self.assertEqual(auto_switch_block_reason({"connection_enabled": False}), "disabled")
        self.assertEqual(auto_switch_block_reason({"routing_mode": "fixed_ip"}), "fixed_ip")
        self.assertIsNone(auto_switch_block_reason({"routing_mode": "auto"}))

        self.assertEqual(
            auto_switch_connect_message("jp1"),
            "当前连接已失效或代理连通性检测失败，正在自动切换至最佳备用节点: jp1",
        )
        self.assertEqual(
            auto_switch_retry_message("jp1", RuntimeError("failed")),
            "切换到备用节点 jp1 失败: failed，将尝试下一个...",
        )
        self.assertEqual(
            auto_switch_no_candidate_message(
                routing_mode="fixed_region",
                target_country="jp",
                routing_target_label=lambda target: target.upper(),
            ),
            "没有可用的【JP】备用节点，已断开连接，将在后台持续尝试获取新节点...",
        )
        self.assertEqual(
            auto_switch_no_candidate_message(
                routing_mode="auto",
                target_country="",
                routing_target_label=lambda target: target,
            ),
            "没有可用的备选节点，将自动断开并清理当前连接状态，同时在后台异步获取新节点...",
        )

    def test_measure_node_latency_uses_remote_endpoint_and_fallback(self) -> None:
        calls: list[tuple[str, int, int]] = []

        def ping(host: str, port: int, fallback: int) -> int:
            calls.append((host, port, fallback))
            return 88

        latency = measure_node_latency(
            {"remote_host": "198.51.100.1", "remote_port": "1194", "ping": "200"},
            parse_int=parse_int,
            ping_latency_ms=ping,
        )

        self.assertEqual(latency, 88)
        self.assertEqual(calls, [("198.51.100.1", 1194, 200)])
        self.assertEqual(
            measure_node_latency({}, parse_int=parse_int, ping_latency_ms=ping),
            0,
        )

    def test_sort_nodes_for_display_groups_by_probe_status(self) -> None:
        nodes = [
            {"id": "bad", "probe_status": "unavailable", "score": 10, "probed_at": 30},
            {"id": "untested", "probe_status": "not_checked", "score": 90, "ping": 80},
            {"id": "hosting", "probe_status": "available", "ip_type": "hosting", "latency_ms": 10, "score": 50},
            {"id": "res", "probe_status": "available", "ip_type": "residential", "latency_ms": 50, "score": 10},
        ]

        sorted_nodes = sort_nodes_for_display(nodes, parse_int=parse_int)

        self.assertEqual([node["id"] for node in sorted_nodes], ["res", "hosting", "untested", "bad"])

    def test_select_auto_switch_candidates_applies_favorites_and_ip_type(self) -> None:
        nodes = [
            {"id": "jp1", "probe_status": "available", "latency_ms": 90, "score": 10, "ip_type": "hosting"},
            {"id": "jp2", "probe_status": "available", "latency_ms": 30, "score": 20, "ip_type": "residential"},
            {"id": "us1", "probe_status": "available", "latency_ms": 10, "score": 30, "ip_type": "residential"},
            {"id": "bad", "probe_status": "unavailable", "latency_ms": 1, "score": 999},
        ]

        candidates = select_auto_switch_candidates(
            nodes,
            ui_config={
                "routing_mode": "favorites",
                "favorite_node_ids": ["jp2", "us1"],
                "routing_ip_type": "residential",
            },
            node_matches_allowed=lambda node: node["id"] != "us1",
            filter_nodes_by_routing_region=lambda items, target: items,
            parse_int=parse_int,
        )

        self.assertEqual([node["id"] for node in candidates], ["jp2"])

    def test_select_auto_switch_candidates_can_disable_favorites_fallback(self) -> None:
        candidates = select_auto_switch_candidates(
            [{"id": "jp1", "probe_status": "available", "latency_ms": 1}],
            ui_config={"routing_mode": "favorites", "favorite_node_ids": ["missing"], "fav_fail_fallback": False},
            node_matches_allowed=lambda node: True,
            filter_nodes_by_routing_region=lambda items, target: items,
            parse_int=parse_int,
        )

        self.assertEqual(candidates, [])

    def test_clean_blacklist_removes_expired_and_invalid_entries(self) -> None:
        cleaned, changed = clean_blacklist(
            {
                "keep": {"until": 200},
                "expired": {"until": 50},
                "invalid": "bad",
            },
            now=100,
        )

        self.assertTrue(changed)
        self.assertEqual(cleaned, {"keep": {"until": 200}})

    def test_blacklist_entry_builds_ttl_entry(self) -> None:
        entry = blacklist_entry(
            {"id": "node1", "remote_host": "198.51.100.1", "country": "JP"},
            message="failed",
            now=100,
            backoff_seconds=30,
        )

        self.assertEqual(entry["id"], "node1")
        self.assertEqual(entry["ip"], "198.51.100.1")
        self.assertEqual(entry["until"], 130)

    def test_connection_state_helpers_update_nodes(self) -> None:
        nodes = [
            {"id": "old", "active": True, "config_file": "/tmp/old.ovpn"},
            {"id": "new", "active": False, "config_file": "/tmp/new.ovpn"},
        ]

        self.assertEqual(find_active_config_file(nodes, "old"), "/tmp/old.ovpn")
        clear_active_flags(nodes)
        self.assertFalse(any(node["active"] for node in nodes))

        mark_active_node(nodes, "new", proxy_url="http://127.0.0.1:7928")

        self.assertFalse(nodes[0]["active"])
        self.assertTrue(nodes[1]["active"])
        self.assertEqual(nodes[1]["probe_message"], "Active node. HTTP proxy: http://127.0.0.1:7928")
        self.assertEqual(latency_label(42), "42 ms")
        self.assertEqual(latency_label(0, timeout_label="检测超时"), "检测超时")

    def test_connection_patch_helpers_mark_failed_and_active_nodes(self) -> None:
        nodes = [
            {"id": "old", "active": True, "probe_status": "available"},
            {"id": "new", "active": False, "probe_status": "not_checked"},
        ]

        failed = mark_connection_failed(nodes, "new", message="openvpn failed")

        self.assertIs(failed, nodes[1])
        self.assertFalse(nodes[0]["active"])
        self.assertFalse(nodes[1]["active"])
        self.assertEqual(nodes[1]["probe_status"], "unavailable")
        self.assertEqual(nodes[1]["probe_message"], "openvpn failed")

        proxy_url = mark_connection_active(nodes, "old", proxy_host="::1", proxy_port=7928)

        self.assertEqual(proxy_url, "http://[::1]:7928")
        self.assertTrue(nodes[0]["active"])
        self.assertFalse(nodes[1]["active"])
        self.assertEqual(nodes[0]["probe_message"], "Active node. HTTP proxy: http://[::1]:7928")
        self.assertEqual(build_proxy_url("127.0.0.1", 8080), "http://127.0.0.1:8080")


if __name__ == "__main__":
    unittest.main()
