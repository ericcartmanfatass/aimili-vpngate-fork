from __future__ import annotations

import unittest
from pathlib import Path
from threading import RLock
from unittest.mock import Mock, sentinel, patch

from aimilivpn.system.manager_connection import ManagerConnectionRuntime
from aimilivpn.system.manager_state import ManagerMutableState


class ManagerConnectionRuntimeTests(unittest.TestCase):
    def make_runtime(self) -> ManagerConnectionRuntime:
        return ManagerConnectionRuntime(
            state=ManagerMutableState(),
            lock=RLock(),
            cleanup_policy_routing=Mock(name="cleanup_policy_routing"),
            read_nodes=Mock(name="read_nodes"),
            write_nodes=Mock(name="write_nodes"),
            load_ui_config=Mock(name="load_ui_config"),
            save_ui_config=Mock(name="save_ui_config"),
            stop_process=Mock(name="stop_process"),
            kill_existing_openvpn_processes=Mock(name="kill_existing_openvpn_processes"),
            set_state=Mock(name="set_state"),
            run_locked=Mock(name="run_locked"),
            log_vpn_line=Mock(name="log_vpn_line"),
            log_line=Mock(name="log_line"),
            print_line=Mock(name="print_line"),
            ensure_dirs=Mock(name="ensure_dirs"),
            start_thread=Mock(name="start_thread"),
            try_acquire_maintenance=Mock(name="try_acquire_maintenance"),
            release_maintenance=Mock(name="release_maintenance"),
            node_matches_allowed=Mock(name="node_matches_allowed"),
            allowed_countries=Mock(name="allowed_countries"),
            filter_nodes_by_routing_region=Mock(name="filter_nodes_by_routing_region"),
            routing_target_label=Mock(name="routing_target_label"),
            parse_int=Mock(name="parse_int"),
            ping_latency_ms=Mock(name="ping_latency_ms"),
            write_ovpn_config=Mock(name="write_ovpn_config"),
            run_openvpn_until_ready=Mock(name="run_openvpn_until_ready"),
            setup_policy_routing=Mock(name="setup_policy_routing"),
            check_proxy_health=Mock(name="check_proxy_health"),
            fetch_candidates=Mock(name="fetch_candidates"),
            check_and_fix_dns=Mock(name="check_and_fix_dns"),
            diagnose_api_failure=Mock(name="diagnose_api_failure"),
            select_maintenance_test_nodes=Mock(name="select_maintenance_test_nodes"),
            test_multiple_nodes=Mock(name="test_multiple_nodes"),
            now=Mock(name="now"),
            api_url=Mock(name="api_url"),
            tun_dev=Mock(name="tun_dev"),
            proxy_host=Mock(name="proxy_host"),
            proxy_port=Mock(name="proxy_port"),
            maintenance_test_limit=Mock(name="maintenance_test_limit"),
            node_test_workers=Mock(name="node_test_workers"),
            exclude_datacenter=Mock(name="exclude_datacenter"),
        )

    def test_connection_runtime_facade_is_cached_and_wired(self) -> None:
        runtime = self.make_runtime()

        with patch("aimilivpn.system.manager_connection.ActiveConnectionRuntimeFacade", return_value=sentinel.facade) as facade_cls:
            first = runtime.connection_runtime_facade()
            second = runtime.connection_runtime_facade()

        self.assertIs(first, sentinel.facade)
        self.assertIs(second, sentinel.facade)
        facade_cls.assert_called_once()
        kwargs = facade_cls.call_args.kwargs
        self.assertIs(kwargs["read_nodes"], runtime.read_nodes)
        self.assertIs(kwargs["write_nodes"], runtime.write_nodes)
        self.assertIs(kwargs["stop_process"], runtime.stop_process)
        self.assertIs(kwargs["run_exclusive"], runtime.run_locked)
        self.assertIs(kwargs["log_line"], runtime.log_vpn_line)

    def test_connection_orchestrator_is_cached_and_uses_runtime_state_methods(self) -> None:
        runtime = self.make_runtime()
        runtime._connection_runtime_facade = sentinel.connection_facade

        with patch("aimilivpn.system.manager_connection.ConnectionOrchestrator", return_value=sentinel.orchestrator) as orchestrator_cls:
            first = runtime.connection_orchestrator()
            second = runtime.connection_orchestrator()

        self.assertIs(first, sentinel.orchestrator)
        self.assertIs(second, sentinel.orchestrator)
        orchestrator_cls.assert_called_once()
        kwargs = orchestrator_cls.call_args.kwargs
        self.assertIs(kwargs["connection_runtime"](), sentinel.connection_facade)
        self.assertIs(kwargs["get_is_connecting"].__self__, runtime)
        self.assertIs(kwargs["get_is_connecting"].__func__, ManagerConnectionRuntime.get_is_connecting)
        self.assertIs(kwargs["set_active_connection"].__self__, runtime)
        self.assertIs(kwargs["set_active_connection"].__func__, ManagerConnectionRuntime.set_active_openvpn_connection)
        self.assertIs(kwargs["run_openvpn_until_ready"], runtime.run_openvpn_until_ready)

    def test_state_accessors_update_mutable_state(self) -> None:
        runtime = self.make_runtime()

        runtime.set_is_connecting(False)
        runtime.set_active_openvpn_node_id("jp_1")
        runtime.set_last_active_ping_time(12.5)
        runtime.set_last_active_latency(88)

        self.assertFalse(runtime.get_is_connecting())
        self.assertEqual(runtime.get_active_openvpn_node_id(), "jp_1")
        self.assertEqual(runtime.get_last_active_ping_time(), 12.5)
        self.assertEqual(runtime.get_last_active_latency(), 88)

    def test_stop_active_openvpn_updates_state_from_facade(self) -> None:
        runtime = self.make_runtime()
        process = object()
        runtime.state.set_active_connection(process, "jp_1")
        facade = Mock()
        facade.stop_active.return_value = (None, "")
        runtime._connection_runtime_facade = facade

        runtime.stop_active_openvpn()

        facade.stop_active.assert_called_once_with(process, "jp_1")
        self.assertIsNone(runtime.state.active_openvpn_process)
        self.assertEqual(runtime.state.active_openvpn_node_id, "")

    def test_clear_active_connection_state_updates_state_from_facade(self) -> None:
        runtime = self.make_runtime()
        process = object()
        runtime.state.set_active_connection(process, "jp_1")
        facade = Mock()
        facade.clear_active_state.return_value = (None, "")
        runtime._connection_runtime_facade = facade

        runtime.clear_active_connection_state("failed")

        facade.clear_active_state.assert_called_once_with(process, "failed")
        self.assertIsNone(runtime.state.active_openvpn_process)
        self.assertEqual(runtime.state.active_openvpn_node_id, "")


if __name__ == "__main__":
    unittest.main()
