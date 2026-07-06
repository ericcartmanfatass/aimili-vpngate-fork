from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from aimilivpn.core.probe import TestIndexPool
from aimilivpn.providers.local_probe import quality_result_to_node_patch
from aimilivpn.system.node_probe_runtime import NodeProbeRuntime


@dataclass
class ManagerNodeProbeRuntime:
    read_nodes: Callable[[], list[dict[str, Any]]]
    write_nodes: Callable[[list[dict[str, Any]]], None]
    run_locked: Callable[[Callable[[], Any]], Any]
    node_matches_allowed: Callable[[dict[str, Any]], bool]
    allowed_countries: Callable[[], set[str]]
    config_dir: Callable[[], Path]
    safe_name: Callable[[str], str]
    write_config: Callable[[Path, str], None]
    ping_latency_ms: Callable[[str, int, int], int]
    run_openvpn: Callable[..., tuple[bool, str, object]]
    parse_int: Callable[[Any], int]
    enrich_ip_info: Callable[[list[dict[str, Any]]], None]
    record_quality: Callable[[dict[str, Any], bool | None, int, str], Any]
    sort_nodes: Callable[[list[dict[str, Any]]], list[dict[str, Any]]]
    now: Callable[[], float]
    print_line: Callable[[str], None]
    load_ui_config: Callable[[], dict[str, Any]]
    filter_nodes_by_routing_region: Callable[[list[dict[str, Any]], str], list[dict[str, Any]]]
    retest_interval_seconds: Callable[[], int]
    max_maintenance_nodes: Callable[[], int]
    _index_pool: TestIndexPool = field(default_factory=TestIndexPool, init=False)
    _runtime: NodeProbeRuntime | None = field(default=None, init=False)

    def runtime(self) -> NodeProbeRuntime:
        if self._runtime is None:
            self._runtime = NodeProbeRuntime(
                read_nodes=self.read_nodes,
                write_nodes=self.write_nodes,
                run_locked=self.run_locked,
                node_matches_allowed=self.node_matches_allowed,
                allowed_countries=self.allowed_countries,
                config_dir=self.config_dir,
                safe_name=self.safe_name,
                write_config=self.write_config,
                ping_latency_ms=self.ping_latency_ms,
                run_openvpn=self.run_openvpn,
                index_pool=lambda: self._index_pool,
                parse_int=self.parse_int,
                enrich_ip_info=self.enrich_ip_info,
                record_quality=self.record_quality,
                quality_to_patch=quality_result_to_node_patch,
                sort_nodes=self.sort_nodes,
                now=self.now,
                print_line=self.print_line,
                load_ui_config=self.load_ui_config,
                filter_nodes_by_routing_region=self.filter_nodes_by_routing_region,
                retest_interval_seconds=self.retest_interval_seconds,
                max_maintenance_nodes=self.max_maintenance_nodes,
            )
        return self._runtime

    def test_node_by_id(self, node_id: str) -> dict[str, Any]:
        return self.runtime().test_node_by_id(node_id)

    def test_multiple_nodes(
        self,
        node_ids: list[str],
        *,
        timeout: int,
        max_workers: int,
    ) -> list[dict[str, Any]]:
        return self.runtime().test_multiple_nodes(
            node_ids,
            timeout=timeout,
            max_workers=max_workers,
        )

    def select_maintenance_test_nodes(self, nodes: list[dict[str, Any]]) -> list[str]:
        return self.runtime().select_maintenance_test_nodes(nodes)
