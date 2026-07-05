from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aimilivpn.system.state_store import RuntimeStateStore, read_json_file, write_json_file


class FakeLock:
    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None


def build_store(path: Path) -> RuntimeStateStore:
    return RuntimeStateStore(
        state_file=path,
        lock=FakeLock(),
        active_node_id=lambda: "node-1",
        is_connecting=lambda: True,
        load_ui_config=lambda: {
            "username": "admin",
            "port": 8787,
            "secret_path": "secret",
            "password_hash": "hash",
            "proxy_port": 7928,
            "routing_mode": "fixed_region",
            "force_country": "region:asia",
            "routing_ip_type": "ipv4",
            "connection_enabled": False,
            "fixed_node_id": "node-1",
            "favorite_node_ids": ["node-1"],
            "fav_fail_fallback": False,
        },
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
    )


class StateStoreTests(unittest.TestCase):
    def test_read_write_json_file_round_trips_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nested" / "state.json"

            write_json_file(path, {"ok": True}, FakeLock())

            self.assertEqual(read_json_file(path, {}, FakeLock()), {"ok": True})

    def test_read_json_file_returns_default_for_invalid_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            path.write_text("{", encoding="utf-8")

            self.assertEqual(read_json_file(path, {"fallback": True}, FakeLock()), {"fallback": True})

    def test_get_state_injects_runtime_and_ui_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            path.write_text(json.dumps({"password": "secret", "last_check_message": "ok"}), encoding="utf-8")

            state = build_store(path).get_state()

            self.assertNotIn("password", state)
            self.assertEqual(state["active_openvpn_node_id"], "node-1")
            self.assertTrue(state["is_connecting"])
            self.assertEqual(state["allowed_countries"], ["JP", "KR"])
            self.assertEqual(state["local_proxy"], "http://[::1]:7928")
            self.assertEqual(state["username"], "admin")
            self.assertTrue(state["password_set"])
            self.assertEqual(state["routing_mode"], "fixed_region")
            self.assertEqual(state["favorite_node_ids"], ["node-1"])
            self.assertFalse(state["fav_fail_fallback"])

    def test_set_state_merges_updates_into_current_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"

            build_store(path).set_state(last_check_message="updated")

            state = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(state["last_check_message"], "updated")
            self.assertEqual(state["instance_id"], "inst-1")


if __name__ == "__main__":
    unittest.main()
