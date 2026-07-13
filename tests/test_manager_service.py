from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import Mock, sentinel, patch

from aimilivpn.system.manager_service import ManagerServiceRuntime


class ManagerServiceRuntimeTests(unittest.TestCase):
    def make_runtime(self) -> ManagerServiceRuntime:
        return ManagerServiceRuntime(
            ensure_dirs=Mock(name="ensure_dirs"),
            kill_existing_openvpn_processes=Mock(name="kill_existing_openvpn_processes"),
            data_dir=Mock(name="data_dir", return_value=Path("data")),
            state_file=Mock(name="state_file", return_value=Path("state.json")),
            write_json=Mock(name="write_json"),
            api_url=Mock(name="api_url"),
            instance_id=Mock(name="instance_id"),
            tun_dev=Mock(name="tun_dev"),
            policy_table=Mock(name="policy_table"),
            allowed_countries=Mock(name="allowed_countries"),
            target_valid_nodes=Mock(name="target_valid_nodes"),
            fetch_interval_seconds=Mock(name="fetch_interval_seconds"),
            check_interval_seconds=Mock(name="check_interval_seconds"),
            local_proxy_host=Mock(name="local_proxy_host"),
            local_proxy_port=Mock(name="local_proxy_port"),
            ui_host=Mock(name="ui_host"),
            ui_port=Mock(name="ui_port"),
            start_proxy_server=Mock(name="start_proxy_server"),
            collector_loop=Mock(name="collector_loop"),
            background_proxy_checker=Mock(name="background_proxy_checker"),
            active_node_pinger=Mock(name="active_node_pinger"),
            start_daemon_threads=Mock(name="start_daemon_threads"),
            wait_for_gateway=Mock(name="wait_for_gateway"),
            load_ui_config=Mock(name="load_ui_config"),
            bounded_int=Mock(name="bounded_int"),
            web_server_runtime=Mock(name="web_server_runtime"),
            serve_web_forever=Mock(name="serve_web_forever"),
            print_line=Mock(name="print_line"),
            set_stdout=Mock(name="set_stdout"),
            set_stderr=Mock(name="set_stderr"),
            shutdown_background_threads=Mock(name="shutdown_background_threads"),
            stop_active_openvpn=Mock(name="stop_active_openvpn"),
            tee_factory=Mock(name="tee_factory"),
        )

    def test_runtime_is_cached_and_wired(self) -> None:
        runtime = self.make_runtime()

        with patch("aimilivpn.system.manager_service.VpnGateServiceRuntime", return_value=sentinel.runtime) as runtime_cls:
            first = runtime.runtime()
            second = runtime.runtime()

        self.assertIs(first, sentinel.runtime)
        self.assertIs(second, sentinel.runtime)
        runtime_cls.assert_called_once()
        kwargs = runtime_cls.call_args.kwargs
        self.assertIs(kwargs["ensure_dirs"], runtime.ensure_dirs)
        self.assertIs(kwargs["kill_existing_openvpn_processes"], runtime.kill_existing_openvpn_processes)
        self.assertIs(kwargs["collector_loop"], runtime.collector_loop)
        self.assertIs(kwargs["web_server_runtime"], runtime.web_server_runtime)
        self.assertIs(kwargs["shutdown_background_threads"], runtime.shutdown_background_threads)
        self.assertIs(kwargs["stop_active_openvpn"], runtime.stop_active_openvpn)
        self.assertIs(kwargs["tee_factory"], runtime.tee_factory)

    def test_main_delegates_to_cached_runtime(self) -> None:
        runtime = self.make_runtime()
        delegate = Mock()
        runtime._runtime = delegate

        runtime.main()

        delegate.main.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
