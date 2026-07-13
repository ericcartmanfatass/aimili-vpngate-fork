from __future__ import annotations

import unittest

from aimilivpn.core.connection_state import (
    ConnectionPhase,
    connection_phase_update,
    normalize_connection_phase,
)


class ConnectionStateTests(unittest.TestCase):
    def test_all_public_connection_phases_are_stable(self) -> None:
        self.assertEqual(
            [phase.value for phase in ConnectionPhase],
            ["idle", "fetching", "probing", "connecting", "connected", "switching", "failed"],
        )

    def test_phase_update_keeps_legacy_connecting_flag_consistent(self) -> None:
        connecting = connection_phase_update(
            ConnectionPhase.CONNECTING,
            message="connecting",
            node_id="jp_1",
        )
        connected = connection_phase_update(ConnectionPhase.CONNECTED, node_id="jp_1")

        self.assertTrue(connecting["is_connecting"])
        self.assertEqual(connecting["connection_state"], "connecting")
        self.assertFalse(connected["is_connecting"])
        self.assertEqual(connected["connection_state"], "connected")

    def test_legacy_state_is_normalized_deterministically(self) -> None:
        self.assertEqual(normalize_connection_phase("unknown", is_connecting=True), "connecting")
        self.assertEqual(normalize_connection_phase(None, active_node_id="jp_1"), "connected")
        self.assertEqual(normalize_connection_phase(None), "idle")


if __name__ == "__main__":
    unittest.main()
