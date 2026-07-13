from __future__ import annotations

import socket
import unittest
from typing import Any

from aimilivpn.system.startup import build_initial_state, format_proxy_url, wait_for_gateway


class FakeSocket:
    def __init__(self, should_connect: bool) -> None:
        self.should_connect = should_connect
        self.timeout: float | None = None
        self.closed = False
        self.address: tuple[str, int] | None = None

    def settimeout(self, value: float) -> None:
        self.timeout = value

    def connect(self, address: tuple[str, int]) -> None:
        self.address = address
        if not self.should_connect:
            raise OSError("not ready")

    def close(self) -> None:
        self.closed = True


class StartupTests(unittest.TestCase):
    def test_format_proxy_url_brackets_ipv6_host(self) -> None:
        self.assertEqual(format_proxy_url("::1", 7928), "http://[::1]:7928")
        self.assertEqual(format_proxy_url("127.0.0.1", 7928), "http://127.0.0.1:7928")

    def test_build_initial_state_uses_sorted_countries_and_proxy_url(self) -> None:
        state = build_initial_state(
            api_url="https://example.test",
            instance_id="inst-1",
            tun_dev="tun0",
            policy_table="100",
            allowed_countries={"KR", "JP"},
            target_valid_nodes=3,
            fetch_interval_seconds=60,
            check_interval_seconds=30,
            local_proxy_host="::1",
            local_proxy_port=7928,
            last_check_message="starting",
            active_node_latency="pending",
        )

        self.assertEqual(state["allowed_countries"], ["JP", "KR"])
        self.assertEqual(state["local_proxy"], "http://[::1]:7928")
        self.assertEqual(state["last_fetch_status"], "starting")
        self.assertTrue(state["is_connecting"])
        self.assertEqual(state["connection_state"], "fetching")

    def test_wait_for_gateway_succeeds_after_retry(self) -> None:
        outcomes = [False, True]
        sockets: list[FakeSocket] = []

        def socket_factory(family: int, sock_type: int) -> FakeSocket:
            self.assertEqual(family, socket.AF_INET)
            self.assertEqual(sock_type, socket.SOCK_STREAM)
            sock = FakeSocket(outcomes.pop(0))
            sockets.append(sock)
            return sock

        self.assertTrue(
            wait_for_gateway(
                "127.0.0.1",
                7928,
                attempts=2,
                delay_seconds=0,
                socket_factory=socket_factory,
                sleep=lambda value: None,
            )
        )
        self.assertTrue(all(sock.closed for sock in sockets))

    def test_wait_for_gateway_falls_back_from_ipv6_any_to_ipv4_loopback(self) -> None:
        attempts: list[tuple[int, Any]] = []

        def socket_factory(family: int, sock_type: int) -> FakeSocket:
            attempts.append((family, sock_type))
            return FakeSocket(should_connect=family == socket.AF_INET)

        self.assertTrue(
            wait_for_gateway(
                "::",
                7928,
                attempts=1,
                delay_seconds=0,
                socket_factory=socket_factory,
                sleep=lambda value: None,
            )
        )
        self.assertEqual(attempts, [(socket.AF_INET6, socket.SOCK_STREAM), (socket.AF_INET, socket.SOCK_STREAM)])


if __name__ == "__main__":
    unittest.main()
