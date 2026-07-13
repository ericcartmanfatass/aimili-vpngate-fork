from __future__ import annotations

from types import SimpleNamespace
import unittest

from aimilivpn.web.proxy_trust import (
    DEFAULT_TRUSTED_PROXY_ADDRESSES,
    is_loopback_host,
    management_http_notice,
    parse_trusted_proxy_addresses,
    request_uses_trusted_https,
)


def request(*, peer: str, proto: str = "https") -> SimpleNamespace:
    return SimpleNamespace(
        client_address=(peer, 43123),
        headers={"X-Forwarded-Proto": proto},
    )


class ProxyTrustTests(unittest.TestCase):
    def test_default_trusted_proxy_addresses_are_loopback_only(self) -> None:
        self.assertEqual(DEFAULT_TRUSTED_PROXY_ADDRESSES, ("127.0.0.1", "::1"))
        self.assertTrue(all(is_loopback_host(item) for item in DEFAULT_TRUSTED_PROXY_ADDRESSES))

    def test_parse_trusted_proxy_addresses_rejects_non_loopback_values(self) -> None:
        parsed = parse_trusted_proxy_addresses("127.0.0.1, 10.0.0.8, ::1, invalid")

        self.assertEqual(parsed, ("127.0.0.1", "::1"))

    def test_forwarded_proto_is_ignored_by_default(self) -> None:
        self.assertFalse(
            request_uses_trusted_https(
                request(peer="127.0.0.1"),
                trust_proxy_headers=False,
                trusted_proxy_addresses=DEFAULT_TRUSTED_PROXY_ADDRESSES,
            )
        )

    def test_forwarded_proto_is_ignored_from_untrusted_peer(self) -> None:
        self.assertFalse(
            request_uses_trusted_https(
                request(peer="198.51.100.8"),
                trust_proxy_headers=True,
                trusted_proxy_addresses=DEFAULT_TRUSTED_PROXY_ADDRESSES,
            )
        )

    def test_https_is_accepted_only_from_explicit_loopback_proxy(self) -> None:
        self.assertTrue(
            request_uses_trusted_https(
                request(peer="127.0.0.1", proto="https"),
                trust_proxy_headers=True,
                trusted_proxy_addresses=("127.0.0.1",),
            )
        )
        self.assertFalse(
            request_uses_trusted_https(
                request(peer="127.0.0.1", proto="http"),
                trust_proxy_headers=True,
                trusted_proxy_addresses=("127.0.0.1",),
            )
        )

    def test_plaintext_public_bind_gets_high_priority_warning(self) -> None:
        notice = management_http_notice(
            "Console",
            "0.0.0.0",
            8788,
            trust_proxy_headers=False,
        )

        self.assertIn("安全警告", notice)
        self.assertIn("0.0.0.0:8788", notice)
        self.assertIn("127.0.0.1", notice)

    def test_loopback_http_notice_requires_tls_proxy_for_remote_access(self) -> None:
        notice = management_http_notice(
            "Console",
            "127.0.0.1",
            8788,
            trust_proxy_headers=False,
        )

        self.assertIn("本机明文 HTTP", notice)
        self.assertIn("TLS 反向代理", notice)


if __name__ == "__main__":
    unittest.main()
