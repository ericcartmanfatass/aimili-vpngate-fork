from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from aimilivpn.core.maintenance import select_maintenance_test_nodes as select_maintenance_test_nodes_core
from aimilivpn.core.probe import (
    TestIndexPool,
    apply_quality_patches_to_probe_results,
    enrich_available_probe_nodes,
    execute_openvpn_probe,
    merge_probe_results_into_nodes,
    probe_result_to_node_patch,
    run_probe_batch,
    select_probe_nodes,
)


@dataclass
class NodeProbeRuntime:
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
    index_pool: Callable[[], TestIndexPool]
    parse_int: Callable[[Any], int]
    enrich_ip_info: Callable[[list[dict[str, Any]]], None]
    record_quality: Callable[[dict[str, Any], bool | None, int, str], Any]
    quality_to_patch: Callable[[Any], dict[str, Any]]
    sort_nodes: Callable[[list[dict[str, Any]]], list[dict[str, Any]]]
    now: Callable[[], float]
    print_line: Callable[[str], None]
    load_ui_config: Callable[[], dict[str, Any]]
    filter_nodes_by_routing_region: Callable[[list[dict[str, Any]], str], list[dict[str, Any]]]
    retest_interval_seconds: Callable[[], int]
    max_maintenance_nodes: Callable[[], int]

    def test_node_by_id(self, node_id: str) -> dict[str, Any]:
        def load_target() -> dict[str, Any]:
            nodes = self.read_nodes()
            node = next((item for item in nodes if item.get("id") == node_id), None)
            if not node:
                raise ValueError(f"Node not found: {node_id}")
            if not self.node_matches_allowed(node):
                raise ValueError(
                    f"Node {node_id} is outside this instance allowed countries: "
                    f"{sorted(self.allowed_countries())}"
                )
            return dict(node)

        node = self.run_locked(load_target)
        config_text = node.get("config_text") or ""
        remote_host = str(node.get("remote_host") or node.get("ip"))
        remote_port = self.parse_int(node.get("remote_port"))
        fallback_ping = self.parse_int(node.get("ping"))

        probe = execute_openvpn_probe(
            node_id=node_id,
            config_text=config_text,
            remote_host=remote_host,
            remote_port=remote_port,
            fallback_ping=fallback_ping,
            config_dir=self.config_dir(),
            safe_name=self.safe_name,
            write_config=self.write_config,
            ping_latency=self.ping_latency_ms,
            run_openvpn=self.run_openvpn,
            index_pool=self.index_pool(),
            timeout=12,
            raise_write_error=True,
        )

        result_patch = probe_result_to_node_patch(
            probe,
            {"id": node_id, "ip": remote_host},
            probed_at=self.now(),
        )
        if probe.ok:
            self.enrich_ip_info([result_patch])
        quality_result = self.record_quality(result_patch, probe.ok, probe.latency_ms, probe.message)
        result_patch.update(self.quality_to_patch(quality_result))

        def save_result() -> dict[str, Any]:
            nodes = self.read_nodes()
            stored_node = next((item for item in nodes if item.get("id") == node_id), None)
            if not stored_node:
                return {}
            stored_node.update(result_patch)
            sorted_nodes = self.sort_nodes(nodes)
            self.write_nodes(sorted_nodes)
            return next((item for item in sorted_nodes if item.get("id") == node_id), stored_node)

        return self.run_locked(save_result)

    def test_multiple_nodes(
        self,
        node_ids: list[str],
        *,
        timeout: int,
        max_workers: int,
    ) -> list[dict[str, Any]]:
        def load_targets() -> list[dict[str, Any]]:
            nodes = self.read_nodes()
            return select_probe_nodes(nodes, node_ids, node_matches_allowed=self.node_matches_allowed)

        to_test = self.run_locked(load_targets)

        def test_worker(args: tuple[int, dict[str, Any]]) -> dict[str, Any]:
            _, node_info = args
            node_id = str(node_info["id"])
            remote_host = str(node_info.get("remote_host") or node_info.get("ip"))
            probe = execute_openvpn_probe(
                node_id=node_id,
                config_text=node_info.get("config_text") or "",
                remote_host=remote_host,
                remote_port=self.parse_int(node_info.get("remote_port")),
                fallback_ping=self.parse_int(node_info.get("ping")),
                config_dir=self.config_dir(),
                safe_name=self.safe_name,
                write_config=self.write_config,
                ping_latency=self.ping_latency_ms,
                run_openvpn=self.run_openvpn,
                index_pool=self.index_pool(),
                timeout=timeout,
            )
            return probe_result_to_node_patch(probe, node_info, probed_at=self.now())

        updated_nodes_map = run_probe_batch(to_test, probe_node=test_worker, max_workers=max_workers)
        probe_results = list(updated_nodes_map.values())

        enrich_available_probe_nodes(
            probe_results,
            self.enrich_ip_info,
            on_error=lambda exc: self.print_line(f"[test_multiple_nodes] Failed to enrich IP info: {exc}"),
        )
        apply_quality_patches_to_probe_results(
            probe_results,
            record_quality=self.record_quality,
            quality_to_patch=self.quality_to_patch,
            parse_int=self.parse_int,
            on_error=lambda res, exc: self.print_line(
                f"[test_multiple_nodes] Failed to save quality result for {res.get('id')}: {exc}"
            ),
        )

        def save_results() -> None:
            current_nodes = self.read_nodes()
            sorted_nodes = merge_probe_results_into_nodes(
                current_nodes,
                updated_nodes_map,
                sort_nodes=self.sort_nodes,
            )
            self.write_nodes(sorted_nodes)

        self.run_locked(save_results)
        return probe_results

    def select_maintenance_test_nodes(self, nodes: list[dict[str, Any]]) -> list[str]:
        ui_cfg = self.load_ui_config()
        return select_maintenance_test_nodes_core(
            nodes,
            now=self.now(),
            routing_mode=str(ui_cfg.get("routing_mode") or "auto"),
            force_country=str(ui_cfg.get("force_country") or ""),
            node_matches_allowed=self.node_matches_allowed,
            filter_nodes_by_routing_region=self.filter_nodes_by_routing_region,
            parse_int=self.parse_int,
            retest_interval_seconds=self.retest_interval_seconds(),
            max_nodes=self.max_maintenance_nodes(),
        )
