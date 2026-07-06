from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import Mock, sentinel, patch

from aimilivpn.system.manager_runtime_files import ManagerRuntimeFiles


class ManagerRuntimeFilesTests(unittest.TestCase):
    def make_runtime(self) -> ManagerRuntimeFiles:
        return ManagerRuntimeFiles(
            paths=Mock(name="paths", return_value=sentinel.paths),
            auth_user=Mock(name="auth_user", return_value="vpn"),
            auth_pass=Mock(name="auth_pass", return_value="gate"),
            get_upstream_proxy_auth=Mock(name="get_upstream_proxy_auth"),
            print_line=Mock(name="print_line"),
        )

    def test_ensure_dirs_delegates_to_runtime_paths(self) -> None:
        runtime = self.make_runtime()

        with patch("aimilivpn.system.manager_runtime_files.ensure_runtime_dirs") as ensure_runtime_dirs:
            runtime.ensure_dirs()

        ensure_runtime_dirs.assert_called_once_with(sentinel.paths, "vpn", "gate")

    def test_upstream_proxy_auth_file_delegates_to_runtime_paths(self) -> None:
        runtime = self.make_runtime()

        with patch(
            "aimilivpn.system.manager_runtime_files.write_upstream_proxy_auth_file",
            return_value="proxy-auth.txt",
        ) as write_auth:
            result = runtime.upstream_proxy_auth_file()

        self.assertEqual(result, "proxy-auth.txt")
        write_auth.assert_called_once_with(sentinel.paths, runtime.get_upstream_proxy_auth, runtime.print_line)

    def test_write_ovpn_config_delegates_to_openvpn_core(self) -> None:
        runtime = self.make_runtime()

        with patch("aimilivpn.system.manager_runtime_files.openvpn_core.write_ovpn_config") as write_config:
            runtime.write_ovpn_config(Path("node.ovpn"), "client\n")

        write_config.assert_called_once_with(Path("node.ovpn"), "client\n")


if __name__ == "__main__":
    unittest.main()
