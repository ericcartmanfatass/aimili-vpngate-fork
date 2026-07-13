from __future__ import annotations

import unittest
from pathlib import Path
from threading import RLock
from unittest.mock import Mock, sentinel, patch

from aimilivpn.system.manager_web import ManagerWebRuntime, default_index_html, default_login_html
from aimilivpn.system.manager_web_wiring import build_web_runtime_wiring


class ManagerWebRuntimeTests(unittest.TestCase):
    def make_runtime(self) -> ManagerWebRuntime:
        return ManagerWebRuntime(
            region_repository=sentinel.region_repository,
            read_regions=Mock(name="read_regions"),
            read_nodes=Mock(name="read_nodes"),
            region_from_payload=Mock(name="region_from_payload"),
            quality_provider_status=Mock(name="quality_provider_status"),
            latest_quality_for_node=Mock(name="latest_quality_for_node"),
            latest_quality_map=Mock(name="latest_quality_map"),
            test_node_by_id=Mock(name="test_node_by_id"),
            check_quality_ip=Mock(name="check_quality_ip"),
            check_quality_region=Mock(name="check_quality_region"),
            bounded_int=Mock(name="bounded_int"),
            scamalytics_errors=(RuntimeError,),
            write_nodes=Mock(name="write_nodes"),
            filter_nodes_by_region=Mock(name="filter_nodes_by_region"),
            get_state=Mock(name="get_state"),
            set_state=Mock(name="set_state"),
            get_active_node_id=Mock(name="get_active_node_id"),
            get_last_active_ping_time=Mock(name="get_last_active_ping_time"),
            set_last_active_ping_time=Mock(name="set_last_active_ping_time"),
            get_last_active_latency=Mock(name="get_last_active_latency"),
            set_last_active_latency=Mock(name="set_last_active_latency"),
            now=Mock(name="now"),
            ping_latency_ms=Mock(name="ping_latency_ms"),
            parse_int=Mock(name="parse_int"),
            start_daemon_thread=Mock(name="start_daemon_thread"),
            test_multiple_nodes=Mock(name="test_multiple_nodes"),
            connect_node=Mock(name="connect_node"),
            stop_active_openvpn=Mock(name="stop_active_openvpn"),
            load_ui_config=Mock(name="load_ui_config"),
            save_ui_config_unlocked=Mock(name="save_ui_config_unlocked"),
            maintain_valid_nodes=Mock(name="maintain_valid_nodes"),
            maintenance_running=Mock(name="maintenance_running"),
            start_maintenance=Mock(name="start_maintenance"),
            validate_routing_region_target=Mock(name="validate_routing_region_target"),
            verify_password=Mock(name="verify_password"),
            verify_username=Mock(name="verify_username"),
            generate_session_token=Mock(name="generate_session_token"),
            check_proxy_health=Mock(name="check_proxy_health"),
            ui_host=Mock(name="ui_host"),
            ui_port=Mock(name="ui_port"),
            trust_proxy_headers=Mock(name="trust_proxy_headers"),
            trusted_proxy_addresses=Mock(name="trusted_proxy_addresses"),
            proxy_host=Mock(name="proxy_host"),
            proxy_port=Mock(name="proxy_port"),
            active_openvpn_running=Mock(name="active_openvpn_running"),
            is_linux=Mock(name="is_linux"),
            tun_dev=Mock(name="tun_dev"),
            server_start_time=Mock(name="server_start_time"),
            last_collector_heartbeat=Mock(name="last_collector_heartbeat"),
            last_checker_heartbeat=Mock(name="last_checker_heartbeat"),
            last_pinger_heartbeat=Mock(name="last_pinger_heartbeat"),
            check_interval_seconds=Mock(name="check_interval_seconds"),
            login_html_fallback=Mock(name="login_html_fallback"),
            index_html_fallback=Mock(name="index_html_fallback"),
            active_sessions={},
            lock=RLock(),
            data_dir=Mock(name="data_dir", return_value=Path(".")),
            console_token=Mock(name="console_token"),
            diagnose_local_obstructions=Mock(name="diagnose_local_obstructions"),
            start_thread=Mock(name="start_thread"),
            sleep=Mock(name="sleep"),
            exit_process=Mock(name="exit_process"),
            print_line=Mock(name="print_line"),
        )

    def test_wiring_is_cached_and_wired(self) -> None:
        runtime = self.make_runtime()

        with patch("aimilivpn.system.manager_web.build_web_runtime_wiring", return_value=sentinel.wiring) as build:
            first = runtime.wiring()
            second = runtime.wiring()

        self.assertIs(first, sentinel.wiring)
        self.assertIs(second, sentinel.wiring)
        build.assert_called_once_with(runtime)

    def test_build_web_runtime_wiring_passes_runtime_fields(self) -> None:
        runtime = self.make_runtime()

        wiring = build_web_runtime_wiring(runtime)

        self.assertIs(wiring.region_repository, sentinel.region_repository)
        self.assertIs(wiring.read_nodes, runtime.read_nodes)
        self.assertIs(wiring.active_sessions, runtime.active_sessions)
        self.assertIs(wiring.lock, runtime.lock)
        self.assertEqual(wiring.scamalytics_errors, (RuntimeError,))
        self.assertIs(wiring.trust_proxy_headers, runtime.trust_proxy_headers)
        self.assertIs(wiring.trusted_proxy_addresses, runtime.trusted_proxy_addresses)

    def test_wrappers_delegate_to_cached_wiring(self) -> None:
        runtime = self.make_runtime()
        wiring = Mock()
        wiring.proxy_gateway_status.return_value = (True, "")
        wiring.read_api_log_entries.return_value = [{"message": "ok"}]
        wiring.route_context_factory.return_value = sentinel.context_factory
        wiring.web_server_runtime.return_value = sentinel.web_server_runtime
        runtime._wiring = wiring

        runtime.clear_active_sessions()
        runtime.schedule_server_restart("restart")
        runtime.save_ui_config_locked({"port": 8787})
        runtime.add_active_session("token", 123.0)
        runtime.remove_active_session("token")
        self.assertEqual(runtime.proxy_gateway_status(), (True, ""))
        self.assertEqual(runtime.read_api_log_entries(), [{"message": "ok"}])
        self.assertIs(runtime.route_context_factory(), sentinel.context_factory)
        self.assertIs(runtime.web_server_runtime(), sentinel.web_server_runtime)

        wiring.clear_active_sessions.assert_called_once_with()
        wiring.schedule_server_restart.assert_called_once_with("restart")
        wiring.save_ui_config_locked.assert_called_once_with({"port": 8787})
        wiring.add_active_session.assert_called_once_with("token", 123.0)
        wiring.remove_active_session.assert_called_once_with("token")

    def test_default_fallback_html(self) -> None:
        self.assertIn("AimiliVPN Login", default_login_html())
        self.assertIn("AimiliVPN", default_index_html())


if __name__ == "__main__":
    unittest.main()
