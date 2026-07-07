from __future__ import annotations

import unittest
from types import SimpleNamespace

from aimilivpn.system.manager_compat_callbacks import bind_compat_callbacks
from aimilivpn.system.manager_compat_exports import CONTEXT_EXPORTS, RUNTIME_CONTEXT_EXPORTS, export_context_globals


class ManagerCompatExportTests(unittest.TestCase):
    def test_export_context_globals_preserves_legacy_names(self) -> None:
        namespace: dict[str, object] = {}
        runtime = SimpleNamespace(**{name: f"runtime:{name}" for name in RUNTIME_CONTEXT_EXPORTS})
        context = SimpleNamespace(**{attr: f"context:{attr}" for _, attr in CONTEXT_EXPORTS})

        export_context_globals(namespace, context, runtime)

        self.assertEqual(namespace["QualityResult"], "runtime:QualityResult")
        self.assertEqual(namespace["ROOT_DIR"], "context:root_dir")
        self.assertEqual(namespace["UPSTREAM_PROXY_AUTH_FILE"], "context:upstream_proxy_auth_file_path")
        self.assertEqual(namespace["manager_web_runtime"], "context:manager_web_runtime")

    def test_bind_compat_callbacks_uses_current_namespace_functions(self) -> None:
        calls: list[tuple[str, object]] = []
        namespace = {
            "manager_quality_runtime": SimpleNamespace(),
            "manager_connection_runtime": SimpleNamespace(),
            "manager_monitoring_runtime": SimpleNamespace(),
            "manager_web_runtime": SimpleNamespace(),
            "manager_openvpn_runtime": SimpleNamespace(),
            "manager_service_runtime": SimpleNamespace(),
            "manager_entry_runtime": SimpleNamespace(),
            "manager_node_probe_runtime": SimpleNamespace(),
            "cleanup_policy_routing": lambda: calls.append(("cleanup", None)),
            "stop_process": lambda process: calls.append(("stop", process)),
            "kill_existing_openvpn_processes": lambda: calls.append(("kill", None)),
            "run_openvpn_until_ready": lambda *args, **kwargs: calls.append(("openvpn", (args, kwargs))),
            "setup_policy_routing": lambda interface: calls.append(("routing", interface)),
            "check_proxy_health": lambda: calls.append(("proxy", None)),
            "select_maintenance_test_nodes": lambda nodes: calls.append(("select", nodes)),
            "test_multiple_nodes": lambda node_ids: calls.append(("test", node_ids)),
            "maintain_valid_nodes": lambda force: calls.append(("maintain", force)),
            "active_openvpn_running": lambda: calls.append(("active", None)),
            "auto_switch_node": lambda: calls.append(("switch", None)),
            "connect_node": lambda node_id: calls.append(("connect", node_id)),
            "test_node_by_id": lambda node_id: calls.append(("test-node", node_id)),
            "check_quality_ip": lambda ip: calls.append(("quality-ip", ip)),
            "check_quality_region": lambda region_id, limit: calls.append(("quality-region", (region_id, limit))),
            "stop_active_openvpn": lambda: calls.append(("stop-active", None)),
            "start_maintenance_thread": lambda: calls.append(("maintenance", None)),
            "update_handshake_status": lambda line: calls.append(("status", line)),
            "collector_loop": lambda: calls.append(("collector", None)),
            "background_proxy_checker": lambda: calls.append(("checker", None)),
            "active_node_pinger": lambda: calls.append(("pinger", None)),
            "web_server_runtime": lambda: calls.append(("web", None)),
            "record_quality_result_from_probe": lambda *args, **kwargs: calls.append(("record", (args, kwargs))),
        }

        bind_compat_callbacks(namespace)
        namespace["connect_node"] = lambda node_id: calls.append(("connect-current", node_id))

        namespace["manager_web_runtime"].connect_node("jp_1")
        namespace["manager_connection_runtime"].run_openvpn_until_ready("config.ovpn")

        self.assertEqual(calls[0], ("connect-current", "jp_1"))
        self.assertEqual(calls[1][0], "openvpn")
        self.assertEqual(calls[1][1][0], ("config.ovpn",))
        self.assertEqual(calls[1][1][1], {"keep_alive": True, "route_nopull": True})


if __name__ == "__main__":
    unittest.main()
