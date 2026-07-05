from __future__ import annotations

from pathlib import Path
import socket
import tempfile
import unittest

from aimilivpn.web.status import probe_proxy_gateway, read_json_log_entries


class FakeSocket:
    def __init__(self, fail_hosts: set[str] | None = None) -> None:
        self.fail_hosts = fail_hosts or set()
        self.closed = False
        self.timeout = None
        self.connected_to: tuple[str, int] | None = None

    def settimeout(self, timeout: float) -> None:
        self.timeout = timeout

    def connect(self, address: tuple[str, int]) -> None:
        host, port = address
        if host in self.fail_hosts:
            raise OSError(f"cannot connect {host}")
        self.connected_to = (host, port)

    def close(self) -> None:
        self.closed = True


class WebStatusTests(unittest.TestCase):
    def test_probe_proxy_gateway_succeeds(self) -> None:
        sockets: list[FakeSocket] = []

        def socket_factory(*args: object) -> FakeSocket:
            sock = FakeSocket()
            sockets.append(sock)
            return sock

        ok, error = probe_proxy_gateway(
            "127.0.0.1",
            7928,
            lambda port: (False, f"diagnosed {port}"),
            socket_factory=socket_factory,  # type: ignore[arg-type]
        )

        self.assertTrue(ok)
        self.assertEqual(error, "")
        self.assertEqual(sockets[0].connected_to, ("127.0.0.1", 7928))
        self.assertTrue(sockets[0].closed)

    def test_probe_proxy_gateway_falls_back_from_ipv6_any_to_ipv4_loopback(self) -> None:
        sockets: list[FakeSocket] = []

        def socket_factory(family: int, kind: int) -> FakeSocket:
            sock = FakeSocket(fail_hosts={"::1"} if family == socket.AF_INET6 else set())
            sockets.append(sock)
            return sock

        ok, error = probe_proxy_gateway(
            "::",
            7928,
            lambda port: (False, f"diagnosed {port}"),
            socket_factory=socket_factory,  # type: ignore[arg-type]
        )

        self.assertTrue(ok)
        self.assertEqual(error, "")
        self.assertEqual(sockets[0].connected_to, None)
        self.assertEqual(sockets[1].connected_to, ("127.0.0.1", 7928))

    def test_probe_proxy_gateway_reports_diagnosis(self) -> None:
        def socket_factory(*args: object) -> FakeSocket:
            return FakeSocket(fail_hosts={"127.0.0.1"})

        ok, error = probe_proxy_gateway(
            "127.0.0.1",
            7928,
            lambda port: (False, f"port {port} blocked"),
            socket_factory=socket_factory,  # type: ignore[arg-type]
        )

        self.assertFalse(ok)
        self.assertEqual(error, "port 7928 blocked")

    def test_read_json_log_entries_skips_invalid_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log_dir = Path(tmp)
            (log_dir / "2026-06-17.json").write_text(
                '{"level":"INFO","message":"ok"}\n'
                'not-json\n'
                '["not", "a", "dict"]\n'
                '{"level":"ERROR","message":"bad"}\n',
                encoding="utf-8",
            )

            entries = read_json_log_entries(log_dir, date_str="2026-06-17")

        self.assertEqual(entries, [
            {"level": "INFO", "message": "ok"},
            {"level": "ERROR", "message": "bad"},
        ])


if __name__ == "__main__":
    unittest.main()
