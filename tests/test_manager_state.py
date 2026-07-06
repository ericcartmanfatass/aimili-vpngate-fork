from __future__ import annotations

import unittest

from aimilivpn.system.manager_state import ManagerMutableState


class ManagerMutableStateTests(unittest.TestCase):
    def test_defaults_and_active_connection_helpers(self) -> None:
        state = ManagerMutableState()

        self.assertEqual(state.active_node_id(), "")
        self.assertTrue(state.is_connecting)
        self.assertIsNone(state.active_openvpn_process)

        process = object()
        state.set_active_connection(process, "jp_1")

        self.assertIs(state.active_openvpn_process, process)
        self.assertEqual(state.active_openvpn_node_id, "jp_1")
        self.assertEqual(state.active_node_id(), "jp_1")

    def test_ping_and_latency_helpers(self) -> None:
        state = ManagerMutableState()

        state.set_last_active_ping_time(123.5)
        state.set_last_active_latency(88)

        self.assertEqual(state.last_active_ping_time, 123.5)
        self.assertEqual(state.last_active_latency, 88)


if __name__ == "__main__":
    unittest.main()
