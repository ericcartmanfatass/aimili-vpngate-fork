from __future__ import annotations

import unittest
from pathlib import Path
from threading import RLock
from unittest.mock import Mock, sentinel, patch

from aimilivpn.system.manager_runtime_state import ManagerRuntimeState
from aimilivpn.system.manager_state import ManagerMutableState
from aimilivpn.core.connection_state import ConnectionPhase


class ManagerRuntimeStateTests(unittest.TestCase):
    def make_runtime(self) -> ManagerRuntimeState:
        return ManagerRuntimeState(
            state_file=Mock(name="state_file", return_value=Path("state.json")),
            lock=RLock(),
            mutable_state=ManagerMutableState(),
            load_ui_config=Mock(name="load_ui_config"),
            api_url=Mock(name="api_url", return_value="https://example.test/api"),
            instance_id=Mock(name="instance_id", return_value="default"),
            tun_dev=Mock(name="tun_dev", return_value="tun0"),
            policy_table=Mock(name="policy_table", return_value="100"),
            allowed_countries=Mock(name="allowed_countries", return_value={"JP"}),
            target_valid_nodes=Mock(name="target_valid_nodes", return_value=3),
            fetch_interval_seconds=Mock(name="fetch_interval_seconds", return_value=60),
            check_interval_seconds=Mock(name="check_interval_seconds", return_value=30),
            local_proxy_host=Mock(name="local_proxy_host", return_value="127.0.0.1"),
            local_proxy_port=Mock(name="local_proxy_port", return_value=7928),
        )

    def test_store_is_built_from_current_runtime_values(self) -> None:
        runtime = self.make_runtime()
        runtime.mutable_state.set_active_connection(None, "jp_1")

        with patch("aimilivpn.system.manager_runtime_state.RuntimeStateStore", return_value=sentinel.store) as store_cls:
            store = runtime.store()

        self.assertIs(store, sentinel.store)
        kwargs = store_cls.call_args.kwargs
        self.assertEqual(kwargs["state_file"], Path("state.json"))
        self.assertEqual(kwargs["active_node_id"](), "jp_1")
        self.assertTrue(kwargs["is_connecting"]())
        self.assertEqual(kwargs["api_url"], "https://example.test/api")
        self.assertEqual(kwargs["allowed_countries"], {"JP"})

    def test_json_helpers_delegate_to_state_store_helpers(self) -> None:
        runtime = self.make_runtime()

        with (
            patch("aimilivpn.system.manager_runtime_state.write_json_file") as write_json_file,
            patch("aimilivpn.system.manager_runtime_state.read_json_file", return_value=sentinel.data) as read_json_file,
        ):
            runtime.write_json(Path("state.json"), {"ok": True})
            result = runtime.read_json(Path("state.json"), {})

        write_json_file.assert_called_once_with(Path("state.json"), {"ok": True}, runtime.lock)
        read_json_file.assert_called_once_with(Path("state.json"), {}, runtime.lock)
        self.assertIs(result, sentinel.data)

    def test_get_and_set_state_delegate_to_store(self) -> None:
        runtime = self.make_runtime()
        store = Mock()
        store.get_state.return_value = {"state": "ok"}

        with patch.object(runtime, "store", return_value=store):
            self.assertEqual(runtime.get_state(), {"state": "ok"})
            runtime.set_state(last_check_message="updated")

        store.get_state.assert_called_once_with()
        store.set_state.assert_called_once_with(last_check_message="updated")

    def test_connection_phase_uses_shared_state_model(self) -> None:
        runtime = self.make_runtime()
        with patch.object(runtime, "set_state") as set_state:
            runtime.set_connection_phase(ConnectionPhase.CONNECTING, "connecting", "jp_1")

        set_state.assert_called_once_with(
            connection_state="connecting",
            is_connecting=True,
            last_check_message="connecting",
            active_openvpn_node_id="jp_1",
        )


if __name__ == "__main__":
    unittest.main()
