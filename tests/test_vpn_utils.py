from __future__ import annotations

import builtins
import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import vpn_utils


class VpnUtilsTests(unittest.TestCase):
    def test_parse_proxy_endpoint_url(self) -> None:
        self.assertEqual(vpn_utils.parse_proxy_endpoint("socks5://user:pass@example.com:1080", 8080), ("example.com", 1080))

    def test_parse_proxy_endpoint_ipv6(self) -> None:
        self.assertEqual(vpn_utils.parse_proxy_endpoint("[2001:db8::1]:1080", 8080), ("2001:db8::1", 1080))

    def test_parse_remote_uses_proto_line_and_remote(self) -> None:
        config = "client\nproto tcp\nremote vpn.example.test 443\n"

        self.assertEqual(vpn_utils.parse_remote(config), ("vpn.example.test", 443, "tcp"))

    def test_parse_remote_inline_proto_wins(self) -> None:
        config = "proto udp\nremote 198.51.100.1 1194 tcp\n"

        self.assertEqual(vpn_utils.parse_remote(config), ("198.51.100.1", 1194, "tcp"))

    def test_check_and_fix_dns_only_reports_when_dns_is_broken(self) -> None:
        class FakeSocket:
            def settimeout(self, timeout: float) -> None:
                self.timeout = timeout

            def connect(self, address: tuple[str, int]) -> None:
                self.address = address

            def close(self) -> None:
                pass

        output = io.StringIO()
        with (
            patch.object(vpn_utils.socket, "getaddrinfo", side_effect=vpn_utils.socket.gaierror()),
            patch.object(vpn_utils.socket, "socket", return_value=FakeSocket()),
            patch.object(builtins, "open", side_effect=AssertionError("must not edit resolv.conf")),
            redirect_stdout(output),
        ):
            vpn_utils.check_and_fix_dns()

        self.assertIn("will not modify /etc/resolv.conf", output.getvalue())


if __name__ == "__main__":
    unittest.main()
