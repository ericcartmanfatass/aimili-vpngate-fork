from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import sentinel, patch

from aimilivpn.system import manager_runtime_context_environment as environment


class ManagerRuntimeContextEnvironmentTests(unittest.TestCase):
    def test_apply_runtime_environment_copies_config_and_paths(self) -> None:
        config = SimpleNamespace(**{name: f"config:{name}" for name in environment.CONFIG_ATTRIBUTES})
        paths = SimpleNamespace()
        for item in environment.PATH_ATTRIBUTES:
            _, source = item if isinstance(item, tuple) else (item, item)
            setattr(paths, source, f"path:{source}")
        runtime_environment = SimpleNamespace(
            root_dir=sentinel.root_dir,
            config=config,
            paths=paths,
        )
        ctx = SimpleNamespace()

        with patch.object(
            environment,
            "build_manager_runtime_environment",
            return_value=runtime_environment,
        ) as build_environment:
            environment.apply_runtime_environment(ctx, compiled=True)

        build_environment.assert_called_once_with(compiled=True)
        self.assertIs(ctx.environment, runtime_environment)
        self.assertIs(ctx.root_dir, sentinel.root_dir)
        self.assertIs(ctx.config, config)
        self.assertEqual(ctx.storage_backend, "config:storage_backend")
        self.assertEqual(ctx.sqlite_db_path, "config:sqlite_db_path")
        self.assertEqual(ctx.runtime_paths, paths)
        self.assertEqual(ctx.settings_file, "path:settings_file")
        self.assertEqual(ctx.upstream_proxy_auth_file_path, "path:upstream_proxy_auth_file")


if __name__ == "__main__":
    unittest.main()
