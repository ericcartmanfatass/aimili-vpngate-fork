from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import Mock, sentinel, patch

from aimilivpn.providers.local_probe import quality_result_to_node_patch
from aimilivpn.system.manager_node_probe import ManagerNodeProbeRuntime


class ManagerNodeProbeRuntimeTests(unittest.TestCase):
    def make_runtime(self) -> ManagerNodeProbeRuntime:
        return ManagerNodeProbeRuntime(
            read_nodes=Mock(name="read_nodes"),
            write_nodes=Mock(name="write_nodes"),
            run_locked=Mock(name="run_locked"),
            node_matches_allowed=Mock(name="node_matches_allowed"),
            allowed_countries=Mock(name="allowed_countries"),
            config_dir=Mock(name="config_dir", return_value=Path("configs")),
            safe_name=Mock(name="safe_name"),
            write_config=Mock(name="write_config"),
            ping_latency_ms=Mock(name="ping_latency_ms"),
            run_openvpn=Mock(name="run_openvpn"),
            parse_int=Mock(name="parse_int"),
            enrich_ip_info=Mock(name="enrich_ip_info"),
            record_quality=Mock(name="record_quality"),
            sort_nodes=Mock(name="sort_nodes"),
            now=Mock(name="now"),
            print_line=Mock(name="print_line"),
            load_ui_config=Mock(name="load_ui_config"),
            filter_nodes_by_routing_region=Mock(name="filter_nodes_by_routing_region"),
            retest_interval_seconds=Mock(name="retest_interval_seconds"),
            max_maintenance_nodes=Mock(name="max_maintenance_nodes"),
        )

    def test_runtime_builds_node_probe_runtime_once(self) -> None:
        manager_runtime = self.make_runtime()

        with patch("aimilivpn.system.manager_node_probe.NodeProbeRuntime", return_value=sentinel.runtime) as runtime_cls:
            first = manager_runtime.runtime()
            second = manager_runtime.runtime()

        self.assertIs(first, sentinel.runtime)
        self.assertIs(second, sentinel.runtime)
        runtime_cls.assert_called_once()
        kwargs = runtime_cls.call_args.kwargs
        self.assertIs(kwargs["read_nodes"], manager_runtime.read_nodes)
        self.assertIs(kwargs["write_nodes"], manager_runtime.write_nodes)
        self.assertIs(kwargs["quality_to_patch"], quality_result_to_node_patch)
        self.assertIs(kwargs["index_pool"](), manager_runtime._index_pool)

    def test_wrappers_delegate_to_cached_runtime(self) -> None:
        manager_runtime = self.make_runtime()
        delegate = Mock()
        delegate.test_node_by_id.return_value = {"id": "jp_1"}
        delegate.test_multiple_nodes.return_value = [{"id": "jp_1"}]
        delegate.select_maintenance_test_nodes.return_value = ["jp_1"]
        manager_runtime._runtime = delegate

        self.assertEqual(manager_runtime.test_node_by_id("jp_1"), {"id": "jp_1"})
        self.assertEqual(
            manager_runtime.test_multiple_nodes(["jp_1"], timeout=5, max_workers=2),
            [{"id": "jp_1"}],
        )
        self.assertEqual(manager_runtime.select_maintenance_test_nodes([{"id": "jp_1"}]), ["jp_1"])

        delegate.test_node_by_id.assert_called_once_with("jp_1")
        delegate.test_multiple_nodes.assert_called_once_with(["jp_1"], timeout=5, max_workers=2)
        delegate.select_maintenance_test_nodes.assert_called_once_with([{"id": "jp_1"}])


if __name__ == "__main__":
    unittest.main()
