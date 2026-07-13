from __future__ import annotations

import socket
import threading
import unittest
from base64 import b64encode
from pathlib import Path
from unittest.mock import Mock, patch

import proxy_server
from aimilivpn.system import proxy_server as proxy_runtime
from aimilivpn.system import proxy_service
from aimilivpn.system.proxy_auth import check_credentials, parse_http_basic_auth
from aimilivpn.system.proxy_server import dns_server_address, parse_host_port, relay


REPO_ROOT = Path(__file__).resolve().parents[1]


class ProxyServerTests(unittest.TestCase):
    def test_dns_server_address_uses_ipv4_family(self) -> None:
        family, address = dns_server_address("8.8.8.8")

        self.assertEqual(family, socket.AF_INET)
        self.assertEqual(address, ("8.8.8.8", 53))

    def test_dns_server_address_uses_ipv6_family(self) -> None:
        family, address = dns_server_address("[2001:4860:4860::8888]")

        self.assertEqual(family, socket.AF_INET6)
        self.assertEqual(address, ("2001:4860:4860::8888", 53, 0, 0))

    def test_parse_host_port_supports_bracketed_ipv6(self) -> None:
        self.assertEqual(parse_host_port("[2001:db8::1]:8443", 443), ("2001:db8::1", 8443))
        self.assertEqual(parse_host_port("[2001:db8::1]", 443), ("2001:db8::1", 443))

    def test_http_basic_auth_parser_decodes_credentials(self) -> None:
        token = b64encode(b"user:pass").decode("ascii")

        self.assertEqual(parse_http_basic_auth([f"Proxy-Authorization: Basic {token}"]), ("user", "pass"))
        self.assertEqual(parse_http_basic_auth(["Proxy-Authorization: Basic invalid-token"]), (None, None))

    def test_check_credentials_uses_proxy_environment(self) -> None:
        with patch.dict("os.environ", {"LOCAL_PROXY_USER": "user", "LOCAL_PROXY_PASS": "pass"}, clear=True):
            self.assertTrue(check_credentials("user", "pass"))
            self.assertFalse(check_credentials("user", "wrong"))

    def test_relay_forwards_bidirectionally(self) -> None:
        if not hasattr(socket, "socketpair"):
            self.skipTest("socketpair is unavailable on this platform")

        left_client, left_proxy = socket.socketpair()
        right_proxy, right_server = socket.socketpair()
        sockets = [left_client, left_proxy, right_proxy, right_server]
        try:
            for sock in sockets:
                sock.settimeout(2)
            thread = threading.Thread(target=relay, args=(left_proxy, right_proxy), daemon=True)
            thread.start()

            left_client.sendall(b"hello")
            self.assertEqual(right_server.recv(5), b"hello")

            right_server.sendall(b"world")
            self.assertEqual(left_client.recv(5), b"world")

            left_client.shutdown(socket.SHUT_WR)
            thread.join(timeout=2)
            self.assertFalse(thread.is_alive())
        finally:
            for sock in sockets:
                try:
                    sock.close()
                except OSError:
                    pass

    def test_root_proxy_server_wrapper_reexports_runtime(self) -> None:
        self.assertIs(proxy_server.start_proxy_server, proxy_runtime.start_proxy_server)

    def test_proxy_server_entrypoint_stays_thin(self) -> None:
        source = (REPO_ROOT / "aimilivpn" / "system" / "proxy_server.py").read_text(encoding="utf-8")

        self.assertIn("from aimilivpn.system.proxy_service import start_proxy_server", source)
        self.assertNotIn("def socks5_client", source)
        self.assertNotIn("def http_client", source)
        self.assertNotIn("def start_proxy_server", source)

    def test_proxy_listener_closes_when_runtime_stop_is_requested(self) -> None:
        stop_event = threading.Event()
        server = Mock()

        def accept() -> object:
            stop_event.set()
            raise socket.timeout()

        server.accept.side_effect = accept
        with patch.object(proxy_service.socket, "socket", return_value=server):
            proxy_service.start_proxy_server("127.0.0.1", 7928, stop_event=stop_event)

        server.settimeout.assert_called_once_with(1.0)
        server.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
