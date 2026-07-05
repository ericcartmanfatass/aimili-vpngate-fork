from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any, Callable

from aimilivpn.core.probe import TestIndexPool
from aimilivpn.system.node_probe_runtime import NodeProbeRuntime


class NodeProbeRuntimeTests(unittest.TestCase):
    def build_runtime(
        self,
        *,
        nodes: list[dict[str, Any]],
        config_dir: Path,
        allowed: Callable[[dict[str, Any]], bool] | None = None,
        written_nodes: list[list[dict[str, Any]]] | None = None,
    ) -> NodeProbeRuntime:
        written_nodes = written_nodes if written_nodes is not None else []
        allowed = allowed or (lambda node: True)

        def run_locked(callback: Callable[[], Any]) -> Any:
            return callback()

        def write_nodes(updated: list[dict[str, Any]]) -> None:
            nodes[:] = updated
            written_nodes.append([dict(item) for item in updated])

        return NodeProbeRuntime(
            read_nodes=lambda: nodes,
            write_nodes=write_nodes,
            run_locked=run_locked,
            node_matches_allowed=allowed,
            allowed_countries=lambda: {"JP"},
            config_dir=lambda: config_dir,
            safe_name=lambda value: value.replace("/", "_"),
            write_config=lambda path, text: path.write_text(text, encoding="utf-8"),
            ping_latency_ms=lambda host, port, fallback: fallback or 42,
            run_openvpn=lambda *args, **kwargs: (True, "ready", object()),
            index_pool=lambda: TestIndexPool(start=2, stop=4),
            parse_int=lambda value: int(value or 0),
            enrich_ip_info=lambda items: [item.update({"owner": "example-owner"}) for item in items],
            record_quality=lambda node, openvpn_success, latency_ms, message: {
                "ok": openvpn_success,
                "latency": latency_ms,
                "message": message,
            },
            quality_to_patch=lambda quality: {
                "quality": "ok" if quality["ok"] else "failed",
                "quality_latency": quality["latency"],
            },
            sort_nodes=lambda items: sorted(items, key=lambda item: str(item.get("id"))),
            now=lambda: 123.0,
            print_line=lambda message: None,
            load_ui_config=lambda: {"routing_mode": "auto", "force_country": ""},
            filter_nodes_by_routing_region=lambda items, target: items,
            retest_interval_seconds=lambda: 3600,
            max_maintenance_nodes=lambda: 10,
        )

    def test_single_node_probe_updates_stored_node(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            nodes = [
                {
                    "id": "jp_1",
                    "ip": "203.0.113.1",
                    "remote_port": "1194",
                    "ping": "70",
                    "config_text": "client",
                }
            ]
            runtime = self.build_runtime(nodes=nodes, config_dir=Path(tmp))

            result = runtime.test_node_by_id("jp_1")

        self.assertEqual(result["id"], "jp_1")
        self.assertEqual(result["probe_status"], "available")
        self.assertEqual(result["latency_ms"], 70)
        self.assertEqual(result["quality"], "ok")
        self.assertEqual(nodes[0]["owner"], "example-owner")

    def test_batch_probe_filters_disallowed_nodes_and_writes_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            nodes = [
                {"id": "jp_1", "ip": "203.0.113.1", "remote_port": "1194", "config_text": "client"},
                {"id": "us_1", "ip": "203.0.113.2", "remote_port": "1194", "config_text": "client"},
            ]
            written: list[list[dict[str, Any]]] = []
            runtime = self.build_runtime(
                nodes=nodes,
                config_dir=Path(tmp),
                allowed=lambda node: str(node.get("id", "")).startswith("jp_"),
                written_nodes=written,
            )

            results = runtime.test_multiple_nodes(["jp_1", "us_1"], timeout=5, max_workers=2)

        self.assertEqual([item["id"] for item in results], ["jp_1"])
        self.assertEqual(nodes[0]["probe_status"], "available")
        self.assertNotIn("probe_status", nodes[1])
        self.assertTrue(written)

    def test_select_maintenance_nodes_uses_configured_limits(self) -> None:
        nodes = [
            {"id": "jp_1", "probe_status": "unavailable", "probed_at": 0},
            {"id": "jp_2", "probe_status": "available", "probed_at": 122.0},
        ]
        runtime = self.build_runtime(nodes=nodes, config_dir=Path("."))

        selected = runtime.select_maintenance_test_nodes(nodes)

        self.assertEqual(selected, ["jp_1"])


if __name__ == "__main__":
    unittest.main()
