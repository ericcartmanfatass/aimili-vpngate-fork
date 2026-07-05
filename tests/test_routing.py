from __future__ import annotations

import subprocess
import unittest

from aimilivpn.core.routing import (
    cleanup_route_commands,
    classify_route_error,
    format_route_error,
    policy_route_commands,
    rp_filter_commands,
)


class RoutingHelperTests(unittest.TestCase):
    def test_policy_route_commands(self) -> None:
        self.assertEqual(
            policy_route_commands("tun7", "107"),
            [
                ["ip", "route", "add", "default", "dev", "tun7", "table", "107"],
                ["ip", "rule", "add", "oif", "tun7", "table", "107"],
            ],
        )

    def test_cleanup_route_commands(self) -> None:
        self.assertEqual(
            cleanup_route_commands("107"),
            [
                ["ip", "rule", "del", "table", "107"],
                ["ip", "route", "flush", "table", "107"],
            ],
        )

    def test_rp_filter_commands(self) -> None:
        self.assertEqual(
            rp_filter_commands("tun7"),
            [
                ["sysctl", "-w", "net.ipv4.conf.all.rp_filter=2"],
                ["sysctl", "-w", "net.ipv4.conf.default.rp_filter=2"],
                ["sysctl", "-w", "net.ipv4.conf.tun7.rp_filter=2"],
            ],
        )

    def test_classify_route_error(self) -> None:
        self.assertEqual(classify_route_error(FileNotFoundError("ip")), "command_not_found")
        self.assertEqual(classify_route_error(PermissionError("operation not permitted")), "permission_denied")
        self.assertEqual(classify_route_error(subprocess.TimeoutExpired(["ip"], 2)), "timeout")
        self.assertEqual(classify_route_error(RuntimeError("boom")), "failed")

    def test_format_route_error_mentions_table_and_permissions(self) -> None:
        message = format_route_error(PermissionError("denied"), table="107")

        self.assertIn("107", message)
        self.assertIn("CAP_NET_ADMIN", message)


if __name__ == "__main__":
    unittest.main()

