from __future__ import annotations

import unittest
from pathlib import Path
from threading import RLock
from unittest.mock import Mock, sentinel, patch

from aimilivpn.system.manager_ui import ManagerUiRuntime


class ManagerUiRuntimeTests(unittest.TestCase):
    def make_runtime(self) -> ManagerUiRuntime:
        return ManagerUiRuntime(
            data_dir=Mock(name="data_dir", return_value=Path("data")),
            lock=RLock(),
            ui_host=Mock(name="ui_host", return_value="127.0.0.1"),
            ui_port=Mock(name="ui_port", return_value=8787),
            proxy_port=Mock(name="proxy_port", return_value=7928),
            bounded_int=Mock(name="bounded_int"),
            password_factory=Mock(name="password_factory", return_value="password"),
            username_factory=Mock(name="username_factory", return_value="user"),
        )

    def test_store_uses_current_dynamic_ports(self) -> None:
        runtime = self.make_runtime()

        with patch("aimilivpn.system.manager_ui.UiConfigStore", return_value=sentinel.store) as store_cls:
            store = runtime.store()

        self.assertIs(store, sentinel.store)
        kwargs = store_cls.call_args.kwargs
        self.assertEqual(kwargs["data_dir"], Path("data"))
        self.assertEqual(kwargs["ui_host"], "127.0.0.1")
        self.assertEqual(kwargs["ui_port"], 8787)
        self.assertEqual(kwargs["proxy_port"], 7928)
        self.assertIs(kwargs["bounded_int"], runtime.bounded_int)

    def test_load_and_save_delegate_to_store(self) -> None:
        runtime = self.make_runtime()
        store = Mock()
        store.load.return_value = {"port": 8787}

        with patch.object(runtime, "store", return_value=store):
            self.assertEqual(runtime.load(), {"port": 8787})
            runtime.save({"port": 8788})

        store.load.assert_called_once_with()
        store.save.assert_called_once_with({"port": 8788})

    def test_random_generators_use_factories(self) -> None:
        runtime = self.make_runtime()

        self.assertEqual(runtime.generate_random_password(), "password")
        self.assertEqual(runtime.generate_random_username(), "user")


if __name__ == "__main__":
    unittest.main()
