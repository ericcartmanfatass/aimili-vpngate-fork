from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any, Callable

from aimilivpn.system.connection_orchestrator import ConnectionOrchestrator


class FakeConnectionRuntime:
    def __init__(self, nodes: list[dict[str, Any]], states: list[dict[str, Any]]) -> None:
        self.nodes = nodes
        self.states = states

    def begin_connect(self, **kwargs: Any) -> bool:
        if kwargs["is_connecting"]:
            raise RuntimeError(kwargs["busy_error_message"])
        self.states.append({
            "is_connecting": True,
            "active_node_latency": kwargs["active_node_latency"],
            "last_check_message": kwargs["last_check_message"].format(node_id=kwargs["node_id"]),
        })
        return True

    def prepare_target(
        self,
        node_id: str,
        *,
        node_matches_allowed: Callable[[dict[str, Any]], bool],
        allowed_countries: set[str],
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        node = next(item for item in self.nodes if item["id"] == node_id)
        if not node_matches_allowed(node):
            raise ValueError(f"Node {node_id} is outside this instance allowed countries: {sorted(allowed_countries)}")
        return self.nodes, node

    def handle_start_failure(self, **kwargs: Any) -> str:
        return ""

    def register_active_process(self, process: object, node_id: str) -> tuple[object, str]:
        return process, node_id

    def finish_connecting(self) -> bool:
        return False


class ConnectionOrchestratorTests(unittest.TestCase):
    def test_maintenance_flow_lives_in_connection_maintenance_module(self) -> None:
        source = (Path(__file__).resolve().parents[1] / "aimilivpn" / "system" / "connection_orchestrator.py").read_text(encoding="utf-8")

        self.assertIn("from aimilivpn.system import connection_connect, connection_maintenance, connection_switching", source)
        self.assertIn("connection_maintenance.maintain_valid_nodes(self, force)", source)
        self.assertNotIn("format_fetch_error_message", source)
        self.assertNotIn("maintenance_recovery_action", source)
        self.assertNotIn("from aimilivpn.core.maintenance import", source)

    def test_connection_flows_live_in_dedicated_modules(self) -> None:
        source = (Path(__file__).resolve().parents[1] / "aimilivpn" / "system" / "connection_orchestrator.py").read_text(encoding="utf-8")

        self.assertIn("connection_switching.auto_switch_node(self, attempt)", source)
        self.assertIn("connection_connect.connect_node(self, node_id)", source)
        self.assertNotIn("from aimilivpn.core.connection import", source)
        self.assertNotIn("from aimilivpn.core.nodes import", source)
        self.assertNotIn("from aimilivpn.core.monitoring import", source)

    def build_orchestrator(
        self,
        *,
        nodes: list[dict[str, Any]] | None = None,
        tmp_dir: Path,
        ui_config: dict[str, Any] | None = None,
        acquire_maintenance: Callable[[], bool] | None = None,
    ) -> tuple[ConnectionOrchestrator, dict[str, Any]]:
        nodes = nodes if nodes is not None else []
        states: list[dict[str, Any]] = []
        logs: list[tuple[str, str, str]] = []
        messages: list[str] = []
        written_nodes: list[list[dict[str, Any]]] = []
        runtime = FakeConnectionRuntime(nodes, states)
        state = {
            "is_connecting": False,
            "active_node_id": "",
            "last_latency": 0,
            "last_ping_time": 0.0,
            "active_process": None,
            "released": False,
            "threads": [],
            "states": states,
            "logs": logs,
            "messages": messages,
            "written_nodes": written_nodes,
            "phases": [],
        }

        def run_locked(callback: Callable[[], Any]) -> Any:
            return callback()

        def set_state(**updates: Any) -> None:
            states.append(dict(updates))

        def write_nodes(updated: list[dict[str, Any]]) -> None:
            nodes[:] = updated
            written_nodes.append([dict(item) for item in updated])

        orchestrator = ConnectionOrchestrator(
            connection_runtime=lambda: runtime,  # type: ignore[return-value]
            ensure_dirs=lambda: None,
            run_locked=run_locked,
            read_nodes=lambda: nodes,
            write_nodes=write_nodes,
            load_ui_config=lambda: dict(ui_config or {}),
            set_state=set_state,
            log_line=lambda level, module, message: logs.append((level, module, message)),
            print_line=lambda message: messages.append(message),
            start_thread=lambda target: state["threads"].append(target),
            try_acquire_maintenance=acquire_maintenance or (lambda: True),
            release_maintenance=lambda: state.update(released=True),
            get_is_connecting=lambda: bool(state["is_connecting"]),
            set_is_connecting=lambda value: state.update(is_connecting=value),
            get_active_node_id=lambda: str(state["active_node_id"]),
            set_active_node_id=lambda node_id: state.update(active_node_id=node_id),
            get_last_active_latency=lambda: int(state["last_latency"]),
            set_last_active_latency=lambda value: state.update(last_latency=value),
            set_last_active_ping_time=lambda value: state.update(last_ping_time=value),
            set_active_connection=lambda process, node_id: state.update(active_process=process, active_node_id=node_id),
            node_matches_allowed=lambda node: True,
            allowed_countries=lambda: {"JP"},
            filter_nodes_by_routing_region=lambda items, target: items,
            routing_target_label=lambda target: target,
            parse_int=lambda value: int(value or 0),
            ping_latency_ms=lambda host, port, fallback: fallback or 25,
            write_ovpn_config=lambda path, text: path.write_text(text, encoding="utf-8"),
            run_openvpn_until_ready=lambda config_file: (True, "ready", object()),
            stop_active_openvpn=lambda: state.update(active_process=None, active_node_id=""),
            active_openvpn_running=lambda: state["active_process"] is not None,
            setup_policy_routing=lambda interface: state.update(route_interface=interface),
            check_proxy_health=lambda: {"ok": True, "ip": "198.51.100.1", "latency_ms": 5},
            clear_active_connection_state=lambda message: state.update(active_process=None, active_node_id="", clear_message=message),
            fetch_candidates=lambda: [],
            check_and_fix_dns=lambda: state.update(dns_checked=True),
            diagnose_api_failure=lambda url: (1001, "diagnosis"),
            select_maintenance_test_nodes=lambda items: [],
            test_multiple_nodes=lambda node_ids: [],
            now=lambda: 123.0,
            api_url=lambda: "https://example.test/api",
            tun_dev=lambda: "tun0",
            proxy_host=lambda: "127.0.0.1",
            proxy_port=lambda: 7928,
            maintenance_test_limit=lambda: 10,
            node_test_workers=lambda: 2,
            exclude_datacenter=lambda: False,
            set_connection_phase=lambda phase, message, node_id: state["phases"].append(
                (getattr(phase, "value", phase), message, node_id)
            ),
        )
        return orchestrator, state

    def test_successful_connect_uses_shared_connection_state_machine(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_file = Path(tmp) / "jp_1.ovpn"
            nodes = [{"id": "jp_1", "config_file": str(config_file), "config_text": "client"}]
            orchestrator, state = self.build_orchestrator(nodes=nodes, tmp_dir=Path(tmp))

            result = orchestrator.connect_node("jp_1")

        self.assertEqual(result, "已连接 jp_1")
        self.assertEqual(state["phases"][-1], ("connected", "已连接到 jp_1", "jp_1"))

    def test_auto_switch_connects_best_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            nodes = [
                {"id": "jp_1", "probe_status": "available", "latency_ms": "40"},
                {"id": "jp_2", "probe_status": "available", "latency_ms": "10"},
            ]
            orchestrator, _ = self.build_orchestrator(nodes=nodes, tmp_dir=Path(tmp))
            connected: list[str] = []
            orchestrator.connect_node = lambda node_id: connected.append(node_id) or f"Connected {node_id}"  # type: ignore[method-assign]

            orchestrator.auto_switch_node()

        self.assertEqual(connected, ["jp_2"])

    def test_auto_switch_schedules_connection_retry_with_backoff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            nodes = [{"id": "jp_1", "probe_status": "available", "latency_ms": "10"}]
            orchestrator, state = self.build_orchestrator(nodes=nodes, tmp_dir=Path(tmp))
            orchestrator.connect_node = lambda node_id: (_ for _ in ()).throw(RuntimeError("offline"))  # type: ignore[method-assign]

            orchestrator.auto_switch_node()

        self.assertEqual(len(state["threads"]), 1)
        self.assertEqual(state["states"][-1]["connection_retry_level"], 1)
        self.assertEqual(state["states"][-1]["next_connection_retry_at"], 183.0)

    def test_connect_node_success_updates_runtime_state_and_nodes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "jp_1.ovpn"
            nodes = [
                {
                    "id": "jp_1",
                    "config_file": str(config_path),
                    "config_text": "client",
                    "ip": "203.0.113.1",
                    "remote_port": "1194",
                    "ping": "33",
                }
            ]
            orchestrator, state = self.build_orchestrator(nodes=nodes, tmp_dir=Path(tmp))

            result = orchestrator.connect_node("jp_1")
            config_text = config_path.read_text(encoding="utf-8")

        self.assertEqual(result, "已连接 jp_1")
        self.assertEqual(state["active_node_id"], "jp_1")
        self.assertEqual(state["last_latency"], 33)
        self.assertEqual(state["route_interface"], "tun0")
        self.assertTrue(nodes[0]["active"])
        self.assertEqual(config_text, "client")
        self.assertFalse(state["is_connecting"])

    def test_maintenance_busy_returns_existing_message(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator, state = self.build_orchestrator(
                tmp_dir=Path(tmp),
                acquire_maintenance=lambda: False,
            )

            result = orchestrator.maintain_valid_nodes()

        self.assertEqual(result, "节点维护任务正在运行，请稍后再试")
        self.assertFalse(state["released"])
        self.assertEqual(state["states"][-1]["last_check_message"], result)

    def test_maintenance_success_merges_candidates_and_tests_selected_nodes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "jp_1.ovpn"
            orchestrator, state = self.build_orchestrator(tmp_dir=Path(tmp))
            tested: list[str] = []
            orchestrator.fetch_candidates = lambda: [  # type: ignore[method-assign]
                {
                    "id": "jp_1",
                    "config_file": str(config_path),
                    "config_text": "client",
                    "probe_status": "not_checked",
                }
            ]
            orchestrator.select_maintenance_test_nodes = lambda nodes: ["jp_1"]  # type: ignore[method-assign]
            orchestrator.test_multiple_nodes = lambda node_ids: tested.extend(node_ids) or []  # type: ignore[method-assign]

            result = orchestrator.maintain_valid_nodes()
            config_text = config_path.read_text(encoding="utf-8")

        self.assertEqual(result, "已获取 1 个节点，已检测 1 个非当前节点。")
        self.assertEqual(tested, ["jp_1"])
        self.assertEqual(config_text, "client")
        self.assertTrue(state["released"])
        self.assertEqual(state["written_nodes"][0][0]["id"], "jp_1")


if __name__ == "__main__":
    unittest.main()
