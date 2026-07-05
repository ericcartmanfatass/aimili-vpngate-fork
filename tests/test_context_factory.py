from __future__ import annotations

import unittest

from aimilivpn.web.context_factory import WebRouteContextFactory


def build_factory(calls: dict[str, object]) -> WebRouteContextFactory:
    return WebRouteContextFactory(
        region_repository=object(),
        read_regions=lambda: [],
        read_nodes=lambda: [],
        region_from_payload=lambda payload, existing: existing,  # type: ignore[return-value]
        quality_provider_status=lambda: {"ok": True},
        latest_quality_for_node=lambda node_id: None,
        latest_quality_map=lambda: {},
        test_node_by_id=lambda node_id: {"id": node_id},
        check_quality_ip=lambda ip: None,  # type: ignore[return-value]
        check_quality_region=lambda region, limit: {"region": region, "limit": limit},
        bounded_int=lambda value, default, min_value, max_value: default,
        scamalytics_errors=(RuntimeError,),
        write_nodes=lambda nodes: calls.__setitem__("nodes", nodes),
        filter_nodes_by_region=lambda nodes, region: nodes,
        get_state=lambda: {"state": "ok"},
        set_state=lambda **state: calls.__setitem__("state", state),
        get_active_node_id=lambda: "node-1",
        get_last_active_ping_time=lambda: 12.0,
        set_last_active_ping_time=lambda value: calls.__setitem__("ping_time", value),
        get_last_active_latency=lambda: 34,
        set_last_active_latency=lambda value: calls.__setitem__("latency", value),
        now=lambda: 100.0,
        ping_latency_ms=lambda host, port, timeout: 56,
        parse_int=lambda value: int(value),
        start_daemon_thread=lambda target, args: calls.__setitem__("daemon_args", args),
        test_multiple_nodes=lambda nodes: [],
        connect_node=lambda node_id: node_id,
        stop_active_openvpn=lambda: calls.__setitem__("stopped", True),
        load_ui_config=lambda: {"secret_path": "secret"},
        save_ui_config=lambda config: calls.__setitem__("config", config),
        maintain_valid_nodes=lambda force: "ok",
        maintenance_running=lambda: False,
        start_maintenance=lambda: calls.__setitem__("maintenance", True),
        validate_routing_region_target=lambda mode, region: None,
        clear_sessions=lambda: calls.__setitem__("sessions_cleared", True),
        schedule_restart=lambda message: calls.__setitem__("restart", message),
        verify_password=lambda password, password_hash: password == password_hash,
        verify_username=lambda username, expected: username == expected,
        generate_session_token=lambda: "token-1",
        add_session=lambda token, expires_at: calls.__setitem__("session", (token, expires_at)),
        remove_session=lambda token: calls.__setitem__("removed_session", token),
        check_proxy_health=lambda: {"ok": True},
        ui_host="127.0.0.1",
        ui_port=8080,
        proxy_host="127.0.0.1",
        proxy_port=1080,
        proxy_gateway_status=lambda: (True, ""),
        active_openvpn_running=lambda: True,
        is_linux=lambda: False,
        tun_dev="tun0",
        tun_exists=lambda: True,
        server_start_time=1.0,
        last_collector_heartbeat=lambda: 2.0,
        last_checker_heartbeat=lambda: 3.0,
        last_pinger_heartbeat=lambda: 4.0,
        check_interval_seconds=60,
        format_local_time=lambda value: str(value),
        read_log_entries=lambda: [{"message": "ok"}],
        login_html_fallback="<html>login</html>",
        index_html_fallback="<html>index</html>",
    )


class WebRouteContextFactoryTests(unittest.TestCase):
    def test_api_get_wires_node_status_and_logs_contexts(self) -> None:
        calls: dict[str, object] = {}
        context = build_factory(calls).api_get()

        context.node.set_last_active_latency(99)

        self.assertEqual(calls["latency"], 99)
        self.assertEqual(context.status.active_node_id(), "node-1")
        self.assertEqual(context.logs.read_log_entries(), [{"message": "ok"}])

    def test_api_post_wires_auth_config_proxy_and_authorization(self) -> None:
        calls: dict[str, object] = {}
        context = build_factory(calls).api_post(lambda: "secret", lambda: True)

        context.auth.add_session("token-1", 200.0)
        context.config.schedule_restart("restart")
        context.proxy.set_state(proxy_ok=True)

        self.assertTrue(context.is_authorized())
        self.assertEqual(context.auth.get_secret_path(), "secret")
        self.assertEqual(calls["session"], ("token-1", 200.0))
        self.assertEqual(calls["restart"], "restart")
        self.assertEqual(calls["state"], {"proxy_ok": True})


if __name__ == "__main__":
    unittest.main()
