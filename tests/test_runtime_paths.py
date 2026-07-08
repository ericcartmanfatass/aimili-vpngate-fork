from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from aimilivpn.system.runtime_paths import (
    build_runtime_paths,
    ensure_runtime_dirs,
    write_upstream_proxy_auth_file,
)


class RuntimePathsTests(unittest.TestCase):
    def test_build_runtime_paths_uses_explicit_data_dir(self) -> None:
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as data:
            paths = build_runtime_paths(Path(root), data)

        self.assertEqual(paths.root_dir, Path(root).resolve())
        self.assertEqual(paths.data_dir, Path(data).resolve())
        self.assertEqual(paths.config_dir, Path(data).resolve() / "configs")
        self.assertEqual(paths.nodes_file, Path(data).resolve() / "nodes.json")
        self.assertEqual(paths.quality_results_file, Path(data).resolve() / "quality_results.json")
        self.assertEqual(paths.settings_file, Path(data).resolve() / "settings.json")

    def test_build_runtime_paths_treats_blank_data_dir_as_default(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            paths = build_runtime_paths(Path(root), "   ")

        self.assertEqual(paths.data_dir, Path(root).resolve() / "vpngate_data")
        self.assertEqual(paths.nodes_file, Path(root).resolve() / "vpngate_data" / "nodes.json")
        self.assertEqual(paths.settings_file, Path(root).resolve() / "vpngate_data" / "settings.json")

    def test_ensure_runtime_dirs_creates_auth_file_once(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            paths = build_runtime_paths(Path(root))

            ensure_runtime_dirs(paths, "vpn", "secret")
            paths.auth_file.write_text("custom\nvalue\n", encoding="utf-8")
            ensure_runtime_dirs(paths, "vpn", "changed")

            self.assertTrue(paths.config_dir.exists())
            self.assertEqual(paths.auth_file.read_text(encoding="utf-8"), "custom\nvalue\n")

    def test_write_upstream_proxy_auth_file_writes_configured_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            paths = build_runtime_paths(Path(root))

            result = write_upstream_proxy_auth_file(
                paths,
                lambda: ("alice", "secret"),
                lambda message: self.fail(f"unexpected log: {message}"),
            )

            self.assertEqual(result, str(paths.upstream_proxy_auth_file))
            self.assertEqual(paths.upstream_proxy_auth_file.read_text(encoding="utf-8"), "alice\nsecret\n")

    def test_write_upstream_proxy_auth_file_skips_empty_username(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            paths = build_runtime_paths(Path(root))

            result = write_upstream_proxy_auth_file(
                paths,
                lambda: (None, None),
                lambda message: self.fail(f"unexpected log: {message}"),
            )

            self.assertIsNone(result)
            self.assertFalse(paths.upstream_proxy_auth_file.exists())


if __name__ == "__main__":
    unittest.main()
