from __future__ import annotations

import threading
import unittest
from pathlib import Path
from typing import Any

from aimilivpn.system.web_runtime import WebRuntimeWiring


def build_wiring(calls: dict[str, Any] | None = None) -> WebRuntimeWiring:
    calls = calls if calls is not None else {}
    sessions: dict[str, float] = {}
    lock = threading.RLock()
    return WebRuntimeWiring(
        region_repository=object(),
        read_regions=lambda: [],
        read_nodes=lambda: [],
        region_from_payload=lambda payload, existing=None: existing,  # type: ignore[return-value]
        quality_provider_status=lambda: {"ok": True},
        latest_quality_for_node=lambda node_id: None,
        latest_quality_map=lambda: {},
        test_node_by_id=lambda node_id: {"id": node_id},
        check_quality_ip=lambda ip: None,  # type: ignore[return-value]
        check_quality_region=lambda region_id, limit: {"region": region_id, "limit": limit},
        bounded_int=lambda value, default, min_value, max_value: default,
        scamalytics_errors=(RuntimeError,),
        write_nodes=lambda nodes: calls.__setitem__("nodes", nodes),
        filter_nodes_by_region=lambda nodes, region_id: nodes,
        get_state=lambda: {"state": "ok"},
        set_state=lambda **updates: calls.__setitem__("state", updates),
        get_active_node_id=lambda: "jp_1",
        get_last_active_ping_time=lambda: 10.0,
        set_last_active_ping_time=lambda value: calls.__setitem__("ping_time", value),
        get_last_active_latency=lambda: 20,
        set_last_active_latency=lambda value: calls.__setitem__("latency", value),
        now=lambda: 100.0,
        ping_latency_ms=lambda host, port, fallback: 30,
        parse_int=lambda value: int(value or 0),
        start_daemon_thread=lambda target, args: calls.__setitem__("daemon", args),
        test_multiple_nodes=lambda node_ids: [],
        connect_node=lambda node_id: f"Connected {node_id}",
        stop_active_openvpn=lambda: calls.__setitem__("stopped", True),
        load_ui_config=lambda: {"secret_path": "secret"},
        save_ui_config_unlocked=lambda config: calls.__setitem__("config", dict(config)),
        maintain_valid_nodes=lambda force: "maintained",
        maintenance_running=lambda: False,
        start_maintenance=lambda: calls.__setitem__("maintenance", True),
        validate_routing_region_target=lambda mode, target: None,
        verify_password=lambda password, password_hash: password == password_hash,
        verify_username=lambda username, expected: username == expected,
        generate_session_token=lambda: "token-1",
        check_proxy_health=lambda: {"ok": True},
        ui_host=lambda: "127.0.0.1",
        ui_port=lambda: 8787,
        proxy_host=lambda: "127.0.0.1",
        proxy_port=lambda: 7928,
        active_openvpn_running=lambda: True,
        is_linux=lambda: False,
        tun_dev=lambda: "tun0",
        server_start_time=lambda: 1.0,
        last_collector_heartbeat=lambda: 2.0,
        last_checker_heartbeat=lambda: 3.0,
        last_pinger_heartbeat=lambda: 4.0,
        check_interval_seconds=lambda: 60,
        login_html_fallback=lambda: "<html>login</html>",
        index_html_fallback=lambda: "<html>index</html>",
        active_sessions=sessions,
        lock=lock,
        data_dir=lambda: Path("."),
        console_token=lambda: "console-token",
        diagnose_local_obstructions=lambda port, host: None,
        start_thread=lambda target: calls.setdefault("threads", []).append(target),
        sleep=lambda seconds: calls.__setitem__("sleep", seconds),
        exit_process=lambda code: calls.__setitem__("exit", code),
        print_line=lambda message: calls.__setitem__("print", message),
    )


class WebRuntimeWiringTests(unittest.TestCase):
    def test_session_helpers_share_runtime_sessions(self) -> None:
        wiring = build_wiring()

        wiring.add_active_session("token-1", 200.0)
        runtime = wiring.web_server_runtime()
        self.assertEqual(runtime.active_sessions["token-1"], 200.0)

        wiring.remove_active_session("token-1")
        self.assertNotIn("token-1", runtime.active_sessions)

        wiring.add_active_session("token-2", 300.0)
        wiring.clear_active_sessions()
        self.assertEqual(runtime.active_sessions, {})

    def test_route_context_factory_uses_wiring_helpers(self) -> None:
        calls: dict[str, Any] = {}
        wiring = build_wiring(calls)
        context = wiring.route_context_factory()

        context.node().set_last_active_latency(99)
        context.config().save_ui_config({"port": 8788})
        context.auth(lambda: "secret").add_session("token-1", 200.0)

        self.assertEqual(calls["latency"], 99)
        self.assertEqual(calls["config"], {"port": 8788})
        self.assertEqual(wiring.active_sessions["token-1"], 200.0)
        self.assertEqual(context.status().active_node_id(), "jp_1")

    def test_schedule_server_restart_runs_deferred_callback(self) -> None:
        calls: dict[str, Any] = {}
        wiring = build_wiring(calls)

        wiring.schedule_server_restart("restart now")
        callback = calls["threads"][0]
        callback()

        self.assertEqual(calls["sleep"], 2)
        self.assertEqual(calls["print"], "[系统] restart now")
        self.assertEqual(calls["exit"], 0)


if __name__ == "__main__":
    unittest.main()