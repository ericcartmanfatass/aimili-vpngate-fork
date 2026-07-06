from __future__ import annotations

import unittest

from aimilivpn.system.openvpn_status import handshake_status_update, update_handshake_status


class OpenVPNStatusTests(unittest.TestCase):
    def test_handshake_status_update_matches_known_step(self) -> None:
        update = handshake_status_update("VERIFY OK: depth=1")

        self.assertIsNotNone(update)
        self.assertEqual(update["active_node_latency"], "证书校验")  # type: ignore[index]
        self.assertIn("证书", update["last_check_message"])  # type: ignore[index]

    def test_handshake_status_update_ignores_unknown_line(self) -> None:
        self.assertIsNone(handshake_status_update("unrelated log line"))

    def test_update_handshake_status_calls_set_state(self) -> None:
        updates: list[dict[str, str]] = []

        update_handshake_status("tun/tap device opened", lambda **kwargs: updates.append(kwargs))

        self.assertEqual(updates[0]["active_node_latency"], "创建网卡")


if __name__ == "__main__":
    unittest.main()
