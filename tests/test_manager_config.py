from __future__ import annotations

import os
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from aimilivpn.system.manager_config import (
    apply_ui_config_overrides,
    bounded_int,
    build_manager_runtime_environment,
    env_bool,
    env_choice,
    env_int,
    env_text,
    load_manager_runtime_config,
    resolve_manager_root_dir,
)


class ManagerConfigTests(unittest.TestCase):
    def test_resolve_manager_root_dir_uses_compiled_executable_parent(self) -> None:
        root = resolve_manager_root_dir(
            compiled=True,
            executable=Path("dist") / "aimilivpn" / "manager.exe",
        )

        self.assertEqual(root, (Path("dist") / "aimilivpn").resolve())

    def test_resolve_manager_root_dir_prefers_install_dir_then_cwd(self) -> None:
        install_dir = Path("installed").resolve()

        with patch.dict(os.environ, {"AIMILIVPN_INSTALL_DIR": str(install_dir)}, clear=True):
            self.assertEqual(resolve_manager_root_dir(cwd=Path("ignored")), install_dir)

        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(resolve_manager_root_dir(cwd=Path("runtime")), Path("runtime").resolve())

        with patch.dict(os.environ, {"AIMILIVPN_INSTALL_DIR": "   "}, clear=True):
            self.assertEqual(resolve_manager_root_dir(cwd=Path("runtime")), Path("runtime").resolve())

        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(resolve_manager_root_dir(install_dir="   ", cwd=Path("runtime")), Path("runtime").resolve())

    def test_build_manager_runtime_environment_groups_root_config_and_paths(self) -> None:
        root = Path("runtime-root").resolve()
        data_dir = Path("runtime-data").resolve()

        with patch.dict(os.environ, {"VPNGATE_DATA_DIR": str(data_dir)}, clear=True):
            environment = build_manager_runtime_environment(cwd=root)

        self.assertEqual(environment.root_dir, root)
        self.assertIs(environment.paths, environment.config.paths)
        self.assertEqual(environment.config.root_dir, root)
        self.assertEqual(environment.paths.data_dir, data_dir)

    def test_load_manager_runtime_config_reads_environment(self) -> None:
        root = Path("sample-root").resolve()
        data_dir = Path("sample-data").resolve()
        env = {
            "VPNGATE_DATA_DIR": str(data_dir),
            "FETCH_INTERVAL_SECONDS": "10",
            "CHECK_INTERVAL_SECONDS": "11",
            "TARGET_VALID_NODES": "4",
            "MAX_SCAN_ROWS": "50",
            "OPENVPN_TEST_TIMEOUT_SECONDS": "12",
            "OPENVPN_MAINTENANCE_TEST_TIMEOUT_SECONDS": "9",
            "NODE_TEST_WORKERS": "3",
            "NODE_RETEST_INTERVAL_SECONDS": "120",
            "OPENVPN_CMD": "openvpn --verb 3",
            "OPENVPN_AUTH_USER": "user",
            "OPENVPN_AUTH_PASS": "pass",
            "LOCAL_PROXY_HOST": "0.0.0.0",
            "LOCAL_PROXY_PORT": "8888",
            "UI_HOST": "127.0.0.1",
            "UI_PORT": "9999",
            "INVALID_BACKOFF_SECONDS": "44",
            "INSTANCE_ID": " JP ",
            "TUN_DEV": "tun9",
            "POLICY_TABLE": "109",
            "ALLOWED_COUNTRIES": "jp, us",
            "EXCLUDE_DATACENTER": "true",
            "ALLOW_INSECURE_FETCH": "1",
            "STORAGE_BACKEND": "sqlite",
            "SQLITE_DB_PATH": "data/aimilivpn.db",
        }

        with patch.dict(os.environ, env, clear=True):
            config = load_manager_runtime_config(root)

        self.assertEqual(config.root_dir, root)
        self.assertEqual(config.paths.data_dir, data_dir)
        self.assertEqual(config.fetch_interval_seconds, 10)
        self.assertEqual(config.check_interval_seconds, 11)
        self.assertEqual(config.target_valid_nodes, 4)
        self.assertEqual(config.max_maintenance_test_nodes, 24)
        self.assertEqual(config.openvpn_cmd, "openvpn --verb 3")
        self.assertEqual(config.openvpn_auth_user, "user")
        self.assertEqual(config.openvpn_auth_pass, "pass")
        self.assertEqual(config.local_proxy_host, "0.0.0.0")
        self.assertEqual(config.local_proxy_port, 8888)
        self.assertEqual(config.ui_host, "127.0.0.1")
        self.assertEqual(config.ui_port, 9999)
        self.assertEqual(config.instance_id, "jp")
        self.assertEqual(config.tun_dev, "tun9")
        self.assertEqual(config.policy_table, "109")
        self.assertEqual(config.allowed_countries, {"JP", "US"})
        self.assertTrue(config.exclude_datacenter)
        self.assertTrue(config.allow_insecure_fetch)
        self.assertEqual(config.storage_backend, "sqlite")
        self.assertEqual(config.sqlite_db_path, root / "data" / "aimilivpn.db")

    def test_load_manager_runtime_config_defaults_invalid_storage_backend(self) -> None:
        root = Path("sample-root").resolve()

        with patch.dict(os.environ, {"STORAGE_BACKEND": "bad"}, clear=True):
            with redirect_stdout(StringIO()):
                config = load_manager_runtime_config(root)

        self.assertEqual(config.storage_backend, "json")

    def test_load_manager_runtime_config_defaults_blank_sqlite_path_to_data_dir(self) -> None:
        root = Path("sample-root").resolve()
        data_dir = Path("sample-data").resolve()

        with patch.dict(os.environ, {"VPNGATE_DATA_DIR": str(data_dir), "SQLITE_DB_PATH": "   "}, clear=True):
            config = load_manager_runtime_config(root)

        self.assertEqual(config.sqlite_db_path, data_dir / "aimilivpn.db")

    def test_load_manager_runtime_config_defaults_blank_data_dir(self) -> None:
        root = Path("sample-root").resolve()

        with patch.dict(os.environ, {"VPNGATE_DATA_DIR": "   "}, clear=True):
            config = load_manager_runtime_config(root)

        self.assertEqual(config.paths.data_dir, root / "vpngate_data")
        self.assertEqual(config.sqlite_db_path, root / "vpngate_data" / "aimilivpn.db")

    def test_load_manager_runtime_config_defaults_blank_runtime_strings(self) -> None:
        root = Path("sample-root").resolve()
        env = {
            "OPENVPN_CMD": "   ",
            "LOCAL_PROXY_HOST": "   ",
            "UI_HOST": "   ",
        }

        with patch.dict(os.environ, env, clear=True):
            config = load_manager_runtime_config(root)

        self.assertEqual(config.openvpn_cmd, "openvpn")
        self.assertEqual(config.local_proxy_host, "127.0.0.1")
        self.assertEqual(config.ui_host, "::")

    def test_env_int_and_bounded_int_apply_defaults(self) -> None:
        with patch.dict(os.environ, {"COUNT": "bad", "LOW": "0", "HIGH": "99", "BLANK": "   ", "PADDED": " 5 "}, clear=True):
            with redirect_stdout(StringIO()):
                self.assertEqual(env_int("COUNT", 7), 7)
                self.assertEqual(env_int("LOW", 7, 1), 7)
                self.assertEqual(env_int("HIGH", 7, None, 10), 7)
                self.assertEqual(env_int("BLANK", 7), 7)
                self.assertEqual(env_int("PADDED", 7), 5)

        self.assertEqual(bounded_int("5", 1, 1, 10), 5)
        self.assertEqual(bounded_int("0", 1, 1, 10), 1)
        self.assertEqual(bounded_int("bad", 1, 1, 10), 1)

    def test_env_choice_applies_defaults(self) -> None:
        with patch.dict(os.environ, {"BACKEND": "bad"}, clear=True):
            with redirect_stdout(StringIO()):
                self.assertEqual(env_choice("BACKEND", "json", {"json", "sqlite"}), "json")

        with patch.dict(os.environ, {"BACKEND": "SQLITE"}, clear=True):
            self.assertEqual(env_choice("BACKEND", "json", {"json", "sqlite"}), "sqlite")

        with patch.dict(os.environ, {"BACKEND": "   "}, clear=True):
            self.assertEqual(env_choice("BACKEND", "json", {"json", "sqlite"}), "json")

    def test_env_text_strips_and_defaults_blank_values(self) -> None:
        with patch.dict(os.environ, {"VALUE": "  configured  ", "BLANK": "   "}, clear=True):
            self.assertEqual(env_text("VALUE", "default"), "configured")
            self.assertEqual(env_text("BLANK", "default"), "default")
            self.assertEqual(env_text("MISSING", "default"), "default")

    def test_env_bool_applies_truthy_values_and_defaults(self) -> None:
        with patch.dict(
            os.environ,
            {"TRUE_VALUE": " yes ", "FALSE_VALUE": "0", "BLANK": "   "},
            clear=True,
        ):
            self.assertTrue(env_bool("TRUE_VALUE"))
            self.assertFalse(env_bool("FALSE_VALUE"))
            self.assertTrue(env_bool("BLANK", default=True))
            self.assertFalse(env_bool("MISSING"))

    def test_apply_ui_config_overrides_normalizes_ports(self) -> None:
        host, ui_port, proxy_port = apply_ui_config_overrides(
            {"host": "127.0.0.1", "port": "9000", "proxy_port": "9001"},
            "::",
            8787,
            7928,
        )

        self.assertEqual(host, "127.0.0.1")
        self.assertEqual(ui_port, 9000)
        self.assertEqual(proxy_port, 9001)

    def test_apply_ui_config_overrides_keeps_defaults_for_invalid_ports(self) -> None:
        host, ui_port, proxy_port = apply_ui_config_overrides(
            {"port": "0", "proxy_port": "1"},
            "::",
            8787,
            7928,
        )

        self.assertEqual(host, "::")
        self.assertEqual(ui_port, 8787)
        self.assertEqual(proxy_port, 7928)


if __name__ == "__main__":
    unittest.main()
