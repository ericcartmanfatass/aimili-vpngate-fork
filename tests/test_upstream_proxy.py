from __future__ import annotations

import socket
import unittest

from aimilivpn.core.upstream_proxy import (
    decode_http_body,
    fetch_text_via_proxy,
    format_host_port,
    proxy_basic_auth_header,
    socks5_address_bytes,
)


class FakeSocket:
    def __init__(self, response: bytes) -> None:
        self._response = response
        self.sent = b""
        self.connected_to: tuple[str, int] | None = None
        self.timeout: float | None = None
        self.closed = False

    def settimeout(self, timeout: float) -> None:
        self.timeout = timeout

    def connect(self, address: tuple[str, int]) -> None:
        self.connected_to = address

    def sendall(self, data: bytes) -> None:
        self.sent += data

    def recv(self, size: int) -> bytes:
        chunk = self._response[:size]
        self._response = self._response[size:]
        return chunk

    def close(self) -> None:
        self.closed = True


class UpstreamProxyTests(unittest.TestCase):
    def test_proxy_basic_auth_header(self) -> None:
        self.assertEqual(
            proxy_basic_auth_header("user", "pass"),
            "Proxy-Authorization: Basic dXNlcjpwYXNz\r\n",
        )

    def test_socks5_address_bytes_supports_ip_and_domain(self) -> None:
        self.assertEqual(socks5_address_bytes("127.0.0.1"), (1, b"\x7f\x00\x00\x01"))
        address_type, address = socks5_address_bytes("example.com")
        self.assertEqual(address_type, 3)
        self.assertEqual(address, b"\x0bexample.com")

    def test_format_host_port_brackets_ipv6(self) -> None:
        self.assertEqual(format_host_port("2001:db8::1", 443), "[2001:db8::1]:443")
        self.assertEqual(format_host_port("example.com", 443), "example.com:443")

    def test_decode_http_body_handles_plain_and_chunked(self) -> None:
        self.assertEqual(
            decode_http_body(b"HTTP/1.1 200 OK\r\nContent-Length: 5\r\n\r\nhello"),
            "hello",
        )
        self.assertEqual(
            decode_http_body(b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n5\r\nhello\r\n0\r\n\r\n"),
            "hello",
        )
        with self.assertRaisesRegex(RuntimeError, "HTTP Server returned status 500"):
            decode_http_body(b"HTTP/1.1 500 Server Error\r\n\r\nfail")

    def test_fetch_text_via_http_proxy_uses_absolute_url_and_auth(self) -> None:
        fake = FakeSocket(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok")

        result = fetch_text_via_proxy(
            "http://example.com/path?q=1",
            "http",
            "127.0.0.1",
            8080,
            proxy_auth=lambda: ("user", "pass"),
            socket_factory=lambda family, socktype: fake,  # type: ignore[return-value]
        )

        self.assertEqual(result, "ok")
        self.assertEqual(fake.connected_to, ("127.0.0.1", 8080))
        request = fake.sent.decode("utf-8")
        self.assertIn("GET http://example.com/path?q=1 HTTP/1.1", request)
        self.assertIn("Host: example.com", request)
        self.assertIn("Proxy-Authorization: Basic dXNlcjpwYXNz", request)
        self.assertTrue(fake.closed)

    def test_fetch_text_via_socks_proxy_establishes_tunnel(self) -> None:
        response = (
            b"\x05\x00"
            b"\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00"
            b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok"
        )
        fake = FakeSocket(response)

        result = fetch_text_via_proxy(
            "http://example.com/path",
            "socks",
            "127.0.0.1",
            1080,
            proxy_auth=lambda: (None, None),
            socket_factory=lambda family, socktype: fake,  # type: ignore[return-value]
        )

        self.assertEqual(result, "ok")
        self.assertEqual(fake.connected_to, ("127.0.0.1", 1080))
        self.assertTrue(fake.sent.startswith(b"\x05\x01\x00"))
        self.assertIn(b"GET /path HTTP/1.1", fake.sent)
        self.assertTrue(fake.closed)


if __name__ == "__main__":
    unittest.main()
