from __future__ import annotations

import unittest
from unittest.mock import Mock, sentinel

from aimilivpn.system.manager_entry import ManagerEntryRuntime


class ManagerEntryRuntimeTests(unittest.TestCase):
    def make_runtime(self) -> ManagerEntryRuntime:
        return ManagerEntryRuntime(
            service_runtime_factory=Mock(name="service_runtime_factory", return_value=sentinel.service_runtime),
            web_server_runtime=Mock(name="web_server_runtime", return_value=sentinel.web_server_runtime),
        )

    def test_service_runtime_delegates_to_factory(self) -> None:
        runtime = self.make_runtime()

        self.assertIs(runtime.service_runtime(), sentinel.service_runtime)
        runtime.service_runtime_factory.assert_called_once_with()

    def test_handler_class_is_cached_and_uses_current_web_runtime(self) -> None:
        runtime = self.make_runtime()

        first = runtime.handler_class()
        second = runtime.handler_class()
        handler = object.__new__(first)

        self.assertIs(first, second)
        self.assertIs(handler.runtime, sentinel.web_server_runtime)
        runtime.web_server_runtime.assert_called_once_with()

    def test_main_delegates_to_service_runtime(self) -> None:
        delegate = Mock()
        runtime = ManagerEntryRuntime(
            service_runtime_factory=Mock(name="service_runtime_factory", return_value=delegate),
            web_server_runtime=Mock(name="web_server_runtime"),
        )

        runtime.main()

        delegate.main.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
