from __future__ import annotations

import unittest
from unittest.mock import Mock, sentinel, patch

from aimilivpn.system.manager_monitoring import ManagerMonitoringRuntime
from aimilivpn.system.manager_state import ManagerMutableState


class ManagerMonitoringRuntimeTests(unittest.TestCase):
    def make_runtime(self) -> ManagerMonitoringRuntime:
        return ManagerMonitoringRuntime(
            state=ManagerMutableState(),
            now=Mock(name="now"),
            sleep=Mock(name="sleep"),
            print_line=Mock(name="print_line"),
            log_line=Mock(name="log_line"),
            set_state=Mock(name="set_state"),
            maintain_valid_nodes=Mock(name="maintain_valid_nodes"),
            active_openvpn_running=Mock(name="active_openvpn_running"),
            check_interval_seconds=Mock(name="check_interval_seconds"),
            check_proxy_health=Mock(name="check_proxy_health"),
            is_connecting=Mock(name="is_connecting"),
            set_is_connecting=Mock(name="set_is_connecting"),
            get_active_node_id=Mock(name="get_active_node_id"),
            load_ui_config=Mock(name="load_ui_config"),
            read_nodes=Mock(name="read_nodes"),
            write_nodes=Mock(name="write_nodes"),
            run_locked=Mock(name="run_locked"),
            mark_blacklisted=Mock(name="mark_blacklisted"),
            auto_switch_node=Mock(name="auto_switch_node"),
            connect_node=Mock(name="connect_node"),
            proxy_port=Mock(name="proxy_port"),
            ping_latency_ms=Mock(name="ping_latency_ms"),
            parse_int=Mock(name="parse_int"),
        )

    def test_heartbeat_setters_update_mutable_state(self) -> None:
        runtime = self.make_runtime()

        runtime.set_collector_heartbeat(1.0)
        runtime.set_checker_heartbeat(2.0)
        runtime.set_pinger_heartbeat(3.0)

        self.assertEqual(runtime.state.last_collector_heartbeat, 1.0)
        self.assertEqual(runtime.state.last_checker_heartbeat, 2.0)
        self.assertEqual(runtime.state.last_pinger_heartbeat, 3.0)

    def test_runtime_is_cached_and_wired(self) -> None:
        runtime = self.make_runtime()

        with patch("aimilivpn.system.manager_monitoring.MonitoringRuntime", return_value=sentinel.runtime) as runtime_cls:
            first = runtime.runtime()
            second = runtime.runtime()

        self.assertIs(first, sentinel.runtime)
        self.assertIs(second, sentinel.runtime)
        runtime_cls.assert_called_once()
        kwargs = runtime_cls.call_args.kwargs
        self.assertIs(kwargs["now"], runtime.now)
        self.assertIs(kwargs["sleep"], runtime.sleep)
        self.assertIs(kwargs["set_collector_heartbeat"].__self__, runtime)
        self.assertIs(kwargs["set_collector_heartbeat"].__func__, ManagerMonitoringRuntime.set_collector_heartbeat)
        self.assertIs(kwargs["maintain_valid_nodes"], runtime.maintain_valid_nodes)
        self.assertIs(kwargs["active_openvpn_running"], runtime.active_openvpn_running)

    def test_loop_wrappers_delegate_to_cached_runtime(self) -> None:
        runtime = self.make_runtime()
        delegate = Mock()
        runtime._runtime = delegate

        runtime.collector_loop()
        runtime.proxy_checker_loop()
        runtime.active_node_pinger_loop()

        delegate.collector_loop.assert_called_once_with()
        delegate.proxy_checker_loop.assert_called_once_with()
        delegate.active_node_pinger_loop.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
