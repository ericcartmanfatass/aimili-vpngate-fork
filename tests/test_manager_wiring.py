from __future__ import annotations

import unittest
from dataclasses import fields
from unittest.mock import Mock, sentinel, patch

from aimilivpn.system.manager_wiring import (
    ConnectionRuntimeWiring,
    MonitoringRuntimeWiring,
    ServiceRuntimeWiring,
    build_connection_runtime,
    build_monitoring_runtime,
    build_service_runtime,
)


def make_wiring(wiring_cls):
    values = {field.name: Mock(name=field.name) for field in fields(wiring_cls)}
    return wiring_cls(**values)


class ManagerWiringTests(unittest.TestCase):
    def test_build_connection_runtime_passes_wiring_fields(self) -> None:
        wiring = make_wiring(ConnectionRuntimeWiring)

        with patch("aimilivpn.system.manager_wiring.ManagerConnectionRuntime", return_value=sentinel.runtime) as runtime_cls:
            runtime = build_connection_runtime(wiring)

        self.assertIs(runtime, sentinel.runtime)
        runtime_cls.assert_called_once_with(**vars(wiring))

    def test_build_monitoring_runtime_passes_wiring_fields(self) -> None:
        wiring = make_wiring(MonitoringRuntimeWiring)

        with patch("aimilivpn.system.manager_wiring.ManagerMonitoringRuntime", return_value=sentinel.runtime) as runtime_cls:
            runtime = build_monitoring_runtime(wiring)

        self.assertIs(runtime, sentinel.runtime)
        runtime_cls.assert_called_once_with(**vars(wiring))

    def test_build_service_runtime_passes_wiring_fields(self) -> None:
        wiring = make_wiring(ServiceRuntimeWiring)

        with patch("aimilivpn.system.manager_wiring.ManagerServiceRuntime", return_value=sentinel.runtime) as runtime_cls:
            runtime = build_service_runtime(wiring)

        self.assertIs(runtime, sentinel.runtime)
        runtime_cls.assert_called_once_with(**vars(wiring))


if __name__ == "__main__":
    unittest.main()
