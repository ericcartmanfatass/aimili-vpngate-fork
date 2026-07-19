from __future__ import annotations

import unittest
from typing import Any, Callable

from aimilivpn.system.monitoring_runtime import MonitoringRuntime


class MonitoringRuntimeTests(unittest.TestCase):
    def build_runtime(
        self,
        *,
        nodes: list[dict[str, Any]] | None = None,
        maintain_result: str = "Fetched 1 nodes. Tested 1 non-active nodes.",
        proxy_result: dict[str, Any] | None = None,
        active_node_id: str = "",
        active_running: bool = False,
        connecting: bool = False,
        routing_mode: str = "auto",
    ) -> tuple[MonitoringRuntime, dict[str, Any]]:
        nodes = nodes if nodes is not None else []
        state: dict[str, Any] = {
            "now": 123.0,
            "collector_heartbeat": 0.0,
            "checker_heartbeat": 0.0,
            "pinger_heartbeat": 0.0,
            "states": [],
            "logs": [],
            "messages": [],
            "blacklisted": [],
            "auto_switches": 0,
            "connects": [],
            "connecting": connecting,
        }

        def run_locked(callback: Callable[[], Any]) -> Any:
            return callback()

        runtime = MonitoringRuntime(
            now=lambda: float(state["now"]),
            sleep=lambda seconds: state.setdefault("sleeps", []).append(seconds),
            set_collector_heartbeat=lambda value: state.update(collector_heartbeat=value),
            set_checker_heartbeat=lambda value: state.update(checker_heartbeat=value),
            set_pinger_heartbeat=lambda value: state.update(pinger_heartbeat=value),
            print_line=lambda message: state["messages"].append(message),
            log_line=lambda level, module, message: state["logs"].append((level, module, message)),
            set_state=lambda **updates: state["states"].append(dict(updates)),
            maintain_valid_nodes=lambda force: maintain_result,
            active_openvpn_running=lambda: active_running,
            check_interval_seconds=lambda: 120,
            check_proxy_health=lambda: proxy_result or {"ok": True, "ip": "198.51.100.1", "latency_ms": 20},
            is_connecting=lambda: bool(state["connecting"]),
            set_is_connecting=lambda value: state.update(connecting=value),
            get_active_node_id=lambda: active_node_id,
            load_ui_config=lambda: {"routing_mode": routing_mode},
            read_nodes=lambda: nodes,
            write_nodes=lambda updated: state.update(written_nodes=[dict(item) for item in updated]),
            run_locked=run_locked,
            mark_blacklisted=lambda node, message: state["blacklisted"].append((dict(node), message)),
            auto_switch_node=lambda: state.update(auto_switches=state["auto_switches"] + 1),
            connect_node=lambda node_id: state["connects"].append(node_id) or f"Connected {node_id}",
            proxy_port=lambda: 7928,
            ping_latency_ms=lambda host, port, fallback: 42,
            parse_int=lambda value: int(value or 0),
        )
        return runtime, state

    def test_collector_cycle_success_uses_configured_interval(self) -> None:
        runtime, state = self.build_runtime()

        sleep_seconds = runtime.run_collector_cycle()

        self.assertEqual(sleep_seconds, 120)
        self.assertEqual(state["collector_heartbeat"], 123.0)
        self.assertIn(("INFO", "Main", "开始执行节点拉取与可用性检测周期任务..."), state["logs"])

    def test_collector_cycle_without_new_nodes_uses_retry_interval(self) -> None:
        runtime, _ = self.build_runtime(maintain_result="没有拉取到新节点")

        sleep_seconds = runtime.run_collector_cycle()

        self.assertEqual(sleep_seconds, 30)

    def test_proxy_failure_marks_active_node_and_auto_switches(self) -> None:
        nodes = [{"id": "jp_1", "probe_status": "available"}]
        runtime, state = self.build_runtime(
            nodes=nodes,
            proxy_result={"ok": False, "error": "down"},
            active_node_id="jp_1",
            routing_mode="auto",
        )

        sleep_seconds = runtime.run_proxy_checker_cycle()

        self.assertEqual(sleep_seconds, 30)
        self.assertEqual(nodes[0]["probe_status"], "unavailable")
        self.assertEqual(state["auto_switches"], 1)
        self.assertEqual(state["blacklisted"][0][0]["id"], "jp_1")

    def test_fixed_ip_proxy_failure_enters_orchestrated_retry(self) -> None:
        runtime, state = self.build_runtime(
            proxy_result={"ok": False, "error": "down"},
            active_node_id="jp_1",
            routing_mode="fixed_ip",
        )

        runtime.run_proxy_checker_cycle()

        self.assertEqual(state["auto_switches"], 1)
        self.assertEqual(state["connects"], [])
        self.assertIn("退避重试", state["messages"][-1])

    def test_proxy_checker_skips_while_connecting(self) -> None:
        runtime, state = self.build_runtime(connecting=True)

        sleep_seconds = runtime.run_proxy_checker_cycle()

        self.assertEqual(sleep_seconds, 5)
        self.assertEqual(state["states"], [])

    def test_active_node_ping_cycle_sets_latency(self) -> None:
        nodes = [{"id": "jp_1", "remote_host": "203.0.113.1", "remote_port": "1194", "ping": "20"}]
        runtime, state = self.build_runtime(nodes=nodes, active_node_id="jp_1", active_running=True)

        sleep_seconds = runtime.run_active_node_ping_cycle()

        self.assertEqual(sleep_seconds, 10)
        self.assertEqual(state["pinger_heartbeat"], 123.0)
        self.assertEqual(state["states"][-1]["active_node_latency"], "42 ms")

    def test_collector_loop_exits_when_runtime_stop_is_requested(self) -> None:
        runtime, _ = self.build_runtime()
        waits: list[int | float] = []
        runtime.wait_for_stop = lambda seconds: waits.append(seconds) or True

        runtime.collector_loop()

        self.assertEqual(waits, [120])


if __name__ == "__main__":
    unittest.main()
