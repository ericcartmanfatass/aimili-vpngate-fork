from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import Mock, sentinel, patch

from aimilivpn.system.manager_openvpn import ManagerOpenVPNRuntime


class ManagerOpenVPNRuntimeTests(unittest.TestCase):
    def make_runtime(self) -> ManagerOpenVPNRuntime:
        return ManagerOpenVPNRuntime(
            openvpn_cmd="openvpn",
            auth_file=Path("auth.txt"),
            data_dir=Path("data"),
            config_dir=Path("configs"),
            upstream_proxy_auth_path=Path("upstream-auth.txt"),
            root_dir=Path("root"),
            default_dev=Mock(name="default_dev", return_value="tun9"),
            policy_table=Mock(name="policy_table", return_value="109"),
            default_timeout_seconds=Mock(name="default_timeout_seconds", return_value=12),
            get_upstream_proxy=Mock(name="get_upstream_proxy"),
            write_upstream_proxy_auth_file=Mock(name="write_upstream_proxy_auth_file"),
            diagnose_openvpn_failure=Mock(name="diagnose_openvpn_failure"),
            status_callback=Mock(name="status_callback"),
            log_vpn_line=Mock(name="log_vpn_line"),
            log_routing_line=Mock(name="log_routing_line"),
            print_line=Mock(name="print_line"),
            sleep=Mock(name="sleep"),
        )

    def test_openvpn_facade_is_cached_and_wired(self) -> None:
        runtime = self.make_runtime()

        with patch("aimilivpn.system.manager_openvpn.OpenVPNRuntimeFacade", return_value=sentinel.facade) as facade_cls:
            first = runtime.openvpn_runtime_facade()
            second = runtime.openvpn_runtime_facade()

        self.assertIs(first, sentinel.facade)
        self.assertIs(second, sentinel.facade)
        facade_cls.assert_called_once()
        kwargs = facade_cls.call_args.kwargs
        self.assertEqual(kwargs["openvpn_cmd"], "openvpn")
        self.assertEqual(kwargs["auth_file"], Path("auth.txt"))
        self.assertIs(kwargs["get_upstream_proxy"], runtime.get_upstream_proxy)
        self.assertIs(kwargs["write_upstream_proxy_auth_file"], runtime.write_upstream_proxy_auth_file)

    def test_policy_routing_facade_is_cached_and_wired(self) -> None:
        runtime = self.make_runtime()

        with patch("aimilivpn.system.manager_openvpn.PolicyRoutingFacade", return_value=sentinel.facade) as facade_cls:
            first = runtime.policy_routing_facade()
            second = runtime.policy_routing_facade()

        self.assertIs(first, sentinel.facade)
        self.assertIs(second, sentinel.facade)
        facade_cls.assert_called_once_with(
            sleep=runtime.sleep,
            print_line=runtime.print_line,
            log_line=runtime.log_routing_line,
        )

    def test_run_openvpn_until_ready_uses_defaults_and_callbacks(self) -> None:
        runtime = self.make_runtime()
        facade = Mock()
        facade.run_until_ready.return_value = (True, "ready", None)
        runtime._openvpn_runtime_facade = facade

        result = runtime.run_openvpn_until_ready("node.ovpn", keep_alive=True, route_nopull=False)

        self.assertEqual(result, (True, "ready", None))
        facade.run_until_ready.assert_called_once_with(
            config_file="node.ovpn",
            keep_alive=True,
            route_nopull=False,
            timeout=12,
            dev="tun9",
            cwd=Path("root"),
            diagnose_failure=runtime.diagnose_openvpn_failure,
            log_line=runtime.log_vpn_line,
            status_callback=runtime.status_callback,
            print_line=runtime.print_line,
        )

    def test_policy_routing_wrappers_use_defaults(self) -> None:
        runtime = self.make_runtime()
        facade = Mock()
        runtime._policy_routing_facade = facade

        runtime.setup_policy_routing()
        runtime.cleanup_policy_routing()

        facade.setup.assert_called_once_with("tun9", "109")
        facade.cleanup.assert_called_once_with("109")


if __name__ == "__main__":
    unittest.main()
