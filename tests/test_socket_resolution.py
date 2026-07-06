from __future__ import annotations

import unittest

from aimilivpn.system.socket_resolution import install_ipv4_preferred_getaddrinfo


class FakeSocketModule:
    AF_INET = 2
    AF_INET6 = 23

    class gaierror(OSError):
        pass

    def __init__(self, fail_ipv4: bool = False) -> None:
        self.calls: list[tuple[object, ...]] = []
        self.fail_ipv4 = fail_ipv4
        self.getaddrinfo = self._getaddrinfo

    def _getaddrinfo(self, host, port, family=0, type=0, proto=0, flags=0):
        self.calls.append((host, port, family, type, proto, flags))
        if self.fail_ipv4 and family == self.AF_INET:
            raise self.gaierror("ipv4 failed")
        return [(family, host, port)]


class SocketResolutionTests(unittest.TestCase):
    def test_install_prefers_ipv4_for_unspecified_family(self) -> None:
        fake_socket = FakeSocketModule()

        install_ipv4_preferred_getaddrinfo(fake_socket)
        result = fake_socket.getaddrinfo("example.test", 443)

        self.assertEqual(fake_socket.calls[0][2], fake_socket.AF_INET)
        self.assertEqual(result, [(fake_socket.AF_INET, "example.test", 443)])

    def test_ipv6_literal_uses_ipv6_family(self) -> None:
        fake_socket = FakeSocketModule()
        install_ipv4_preferred_getaddrinfo(fake_socket)

        fake_socket.getaddrinfo("2001:db8::1", 443)

        self.assertEqual(fake_socket.calls[0][2], fake_socket.AF_INET6)

    def test_falls_back_to_system_default_when_ipv4_fails(self) -> None:
        fake_socket = FakeSocketModule(fail_ipv4=True)
        install_ipv4_preferred_getaddrinfo(fake_socket)

        result = fake_socket.getaddrinfo("example.test", 443)

        self.assertEqual(fake_socket.calls[0][2], fake_socket.AF_INET)
        self.assertEqual(fake_socket.calls[1][2], 0)
        self.assertEqual(result, [(0, "example.test", 443)])


if __name__ == "__main__":
    unittest.main()
