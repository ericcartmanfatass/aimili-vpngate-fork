from __future__ import annotations

import socket
import threading
import unittest

import proxy_server
from aimilivpn.system import proxy_server as proxy_runtime
from aimilivpn.system.proxy_server import dns_server_address, parse_host_port, relay


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


if __name__ == "__main__":
    unittest.main()
