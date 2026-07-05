from __future__ import annotations

import unittest

from aimilivpn.core.security import UnsafeOpenVPNConfig, redact_sensitive_text, sanitize_ovpn_config


SAFE_CONFIG = """client
dev tun
proto udp
remote 203.0.113.10 1194
resolv-retry infinite
nobind
persist-key
persist-tun
remote-cert-tls server
auth SHA1
cipher AES-128-CBC
verb 3
<ca>
-----BEGIN CERTIFICATE-----
MIIB
-----END CERTIFICATE-----
</ca>
"""


class SecurityTests(unittest.TestCase):
    def test_sanitize_allows_common_vpngate_config(self) -> None:
        sanitized = sanitize_ovpn_config(SAFE_CONFIG)

        self.assertIn("remote 203.0.113.10 1194", sanitized)
        self.assertTrue(sanitized.endswith("\n"))

    def test_sanitize_rejects_script_hooks(self) -> None:
        with self.assertRaises(UnsafeOpenVPNConfig):
            sanitize_ovpn_config(SAFE_CONFIG + "script-security 2\nup /tmp/x\n")

    def test_redact_private_key_block(self) -> None:
        text = "<key>\nsecret\n</key>\npassword=abc"

        redacted = redact_sensitive_text(text)

        self.assertNotIn("secret", redacted)
        self.assertNotIn("abc", redacted)


if __name__ == "__main__":
    unittest.main()

