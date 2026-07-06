from __future__ import annotations

import unittest
from unittest.mock import Mock, sentinel, patch

from aimilivpn.system.manager_proxy_health import ManagerProxyHealthRuntime


class ManagerProxyHealthRuntimeTests(unittest.TestCase):
    def make_runtime(self) -> ManagerProxyHealthRuntime:
        return ManagerProxyHealthRuntime(
            proxy_host=Mock(name="proxy_host", return_value="127.0.0.1"),
            proxy_port=Mock(name="proxy_port", return_value=7928),
            tun_dev=Mock(name="tun_dev", return_value="tun9"),
            is_linux=Mock(name="is_linux", return_value=True),
            get_proxy_credentials=Mock(name="get_proxy_credentials"),
            diagnose_local_obstructions=Mock(name="diagnose_local_obstructions"),
        )

    def test_check_proxy_health_uses_current_runtime_values(self) -> None:
        runtime = self.make_runtime()

        with patch("aimilivpn.system.manager_proxy_health.proxy_core.check_proxy_health", return_value=sentinel.result) as check:
            result = runtime.check_proxy_health()

        self.assertIs(result, sentinel.result)
        check.assert_called_once_with(
            proxy_host="127.0.0.1",
            proxy_port=7928,
            tun_dev="tun9",
            is_linux=True,
            get_proxy_credentials=runtime.get_proxy_credentials,
            diagnose_local_obstructions=runtime.diagnose_local_obstructions,
        )


if __name__ == "__main__":
    unittest.main()
