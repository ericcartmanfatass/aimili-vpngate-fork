from __future__ import annotations

import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aimilivpn.core.auth import verify_password
from aimilivpn.system import console_backend, console_config, console_instances


class ConsoleConfigTests(unittest.TestCase):
    def test_load_console_auth_migrates_plaintext_password(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            auth_file = Path(tmp) / "console_auth.json"
            auth_file.write_text(
                json.dumps({"username": "admin", "password": "secret", "secret_path": "consoleabc"}),
                encoding="utf-8",
            )

            with patch.object(console_config, "AUTH_FILE", auth_file):
                auth = console_config.load_console_auth()

            self.assertEqual(auth["username"], "admin")
            self.assertEqual(auth["secret_path"], "consoleabc")
            self.assertNotIn("password", auth)
            self.assertTrue(verify_password("secret", auth["password_hash"]))
            saved = json.loads(auth_file.read_text(encoding="utf-8"))
            self.assertNotIn("password", saved)

    def test_write_json_creates_private_json_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nested" / "data.json"

            console_config.write_json(path, {"ok": True})

            self.assertEqual(console_config.read_json(path, {}), {"ok": True})

    def test_console_config_defaults_blank_and_invalid_environment(self) -> None:
        env = {
            "AIMILIVPN_CONFIG_DIR": "   ",
            "AIMILIVPN_INSTALL_DIR": "   ",
            "AIMILIVPN_CONSOLE_AUTH": "   ",
            "AIMILIVPN_INSTANCES_FILE": "   ",
            "CONSOLE_HOST": "   ",
            "CONSOLE_PORT": "bad",
        }
        try:
            with patch.dict(os.environ, env, clear=True):
                reloaded = importlib.reload(console_config)

            self.assertEqual(reloaded.CONFIG_DIR, Path("/etc/aimilivpn"))
            self.assertEqual(reloaded.INSTALL_DIR, Path("/opt/aimilivpn"))
            self.assertEqual(reloaded.AUTH_FILE, Path("/etc/aimilivpn/console_auth.json"))
            self.assertEqual(reloaded.INSTANCES_FILE, Path("/etc/aimilivpn/instances.json"))
            self.assertEqual(reloaded.CONSOLE_HOST, "127.0.0.1")
            self.assertEqual(reloaded.CONSOLE_PORT, 8788)
            self.assertFalse(reloaded.TRUST_PROXY_HEADERS)
            self.assertEqual(reloaded.TRUSTED_PROXY_ADDRESSES, ("127.0.0.1", "::1"))
        finally:
            importlib.reload(console_config)


class ConsoleInstanceTests(unittest.TestCase):
    def test_load_instances_reads_instances_file_and_env_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env_file = root / "jp.env"
            data_dir = root / "data" / "jp"
            data_dir.mkdir(parents=True)
            (data_dir / "ui_auth.json").write_text(json.dumps({"secret_path": "jpsecret"}), encoding="utf-8")
            env_file.write_text(
                "\n".join([
                    "ALLOWED_COUNTRIES=JP",
                    f"VPNGATE_DATA_DIR={data_dir}",
                    "UI_PORT=8787",
                    "LOCAL_PROXY_PORT=7928",
                    "TUN_DEV=tun-jp",
                    "POLICY_TABLE=100",
                ]),
                encoding="utf-8",
            )
            instances_file = root / "instances.json"
            instances_file.write_text(json.dumps({"instances": [{"id": "jp", "env_file": str(env_file)}]}), encoding="utf-8")

            with (
                patch.object(console_instances, "CONFIG_DIR", root),
                patch.object(console_instances, "INSTALL_DIR", root / "install"),
                patch.object(console_instances, "INSTANCES_FILE", instances_file),
            ):
                instances = console_instances.load_instances()

            self.assertEqual(len(instances), 1)
            self.assertEqual(instances[0]["country"], "JP")
            self.assertEqual(instances[0]["ui_port"], 8787)
            self.assertEqual(instances[0]["proxy_port"], 7928)
            self.assertEqual(instances[0]["secret_path"], "jpsecret")

    def test_available_country_catalog_aggregates_vpngate_data_without_summing_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_jp = root / "data" / "jp"
            data_us = root / "data" / "us"
            data_jp.mkdir(parents=True)
            data_us.mkdir(parents=True)
            for instance_id, data_dir, countries in (
                ("jp", data_jp, [{"country": "DE", "name": "Germany", "node_count": 4}]),
                ("us", data_us, [{"country": "DE", "name": "Germany", "node_count": 3}, {"country": "FR", "name": "France", "node_count": 2}]),
            ):
                (root / f"{instance_id}.env").write_text("", encoding="utf-8")
                (data_dir / "country_catalog.json").write_text(
                    json.dumps({"countries": countries}),
                    encoding="utf-8",
                )
            instances_file = root / "instances.json"
            instances_file.write_text(
                json.dumps({"instances": [
                    {"id": "jp", "country": "JP", "env_file": str(root / "jp.env"), "data_dir": str(data_jp)},
                    {"id": "us", "country": "US", "env_file": str(root / "us.env"), "data_dir": str(data_us)},
                ]}),
                encoding="utf-8",
            )

            with (
                patch.object(console_instances, "CONFIG_DIR", root),
                patch.object(console_instances, "INSTALL_DIR", root),
                patch.object(console_instances, "INSTANCES_FILE", instances_file),
            ):
                catalog = console_instances.load_available_country_catalog()

        by_country = {item["country"]: item for item in catalog}
        self.assertEqual(by_country["DE"]["node_count"], 4)
        self.assertEqual(by_country["FR"]["node_count"], 2)
        self.assertEqual(by_country["JP"]["node_count"], 0)
        self.assertEqual(by_country["US"]["node_count"], 0)

    def test_normalize_instance_defaults_blank_and_invalid_env_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env_file = root / "jp.env"
            env_file.write_text(
                "\n".join([
                    "ALLOWED_COUNTRIES=   ",
                    "VPNGATE_DATA_DIR=   ",
                    "UI_HOST=   ",
                    "LOCAL_PROXY_HOST=   ",
                    "UI_PORT=bad",
                    "LOCAL_PROXY_PORT=   ",
                    "TUN_DEV= tun-jp ",
                    "POLICY_TABLE= 100 ",
                ]),
                encoding="utf-8",
            )

            with (
                patch.object(console_instances, "CONFIG_DIR", root),
                patch.object(console_instances, "INSTALL_DIR", root / "install"),
            ):
                instance = console_instances.normalize_instance({"id": "jp", "env_file": str(env_file)})

        self.assertEqual(instance["country"], "JP")
        self.assertEqual(instance["data_dir"], str(root / "install" / "data" / "jp"))
        self.assertEqual(instance["ui_host"], "127.0.0.1")
        self.assertEqual(instance["proxy_host"], "127.0.0.1")
        self.assertEqual(instance["ui_port"], 0)
        self.assertEqual(instance["proxy_port"], 0)
        self.assertEqual(instance["tun_dev"], "tun-jp")
        self.assertEqual(instance["policy_table"], "100")

    def test_instance_state_and_stripped_nodes_hide_openvpn_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            (data_dir / "state.json").write_text(json.dumps({"active_openvpn_node_id": "jp_1"}), encoding="utf-8")
            (data_dir / "nodes.json").write_text(
                json.dumps([
                    {"id": "jp_1", "ip": "203.0.113.1", "country": "JP", "config_text": "secret"},
                ]),
                encoding="utf-8",
            )
            inst = {
                "id": "jp",
                "country": "JP",
                "service": "aimilivpn@jp.service",
                "data_dir": str(data_dir),
                "ui_port": 8787,
                "proxy_host": "127.0.0.1",
                "proxy_port": 7928,
                "tun_dev": "tun-jp",
                "policy_table": "100",
            }

            state = console_instances.instance_state(inst, service_active=lambda service: service.endswith("jp.service"))
            nodes = console_instances.stripped_nodes(inst, state_factory=lambda item: state)

            self.assertTrue(state["service_active"])
            self.assertEqual(state["active_node"]["id"], "jp_1")
            self.assertEqual(state["local_proxy"], "socks5://127.0.0.1:7928")
            self.assertNotIn("config_text", nodes["nodes"][0])

    def test_instance_state_formats_ipv6_proxy_host(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            inst = {
                "id": "jp",
                "country": "JP",
                "service": "aimilivpn@jp.service",
                "data_dir": tmp,
                "ui_port": 8787,
                "proxy_host": "::1",
                "proxy_port": 7928,
                "tun_dev": "tun-jp",
                "policy_table": "100",
            }

            state = console_instances.instance_state(inst, service_active=lambda service: True)

        self.assertEqual(state["local_proxy"], "socks5://[::1]:7928")

    def test_normalize_instance_rejects_unmanaged_env_path_and_service(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            managed_env = root / "jp.env"
            managed_env.write_text("UI_PORT=8787", encoding="utf-8")
            with patch.object(console_instances, "CONFIG_DIR", root):
                with self.assertRaisesRegex(ValueError, "managed configuration"):
                    console_instances.normalize_instance({"id": "jp", "env_file": str(root / "other.env")})
                with self.assertRaisesRegex(ValueError, "installer managed"):
                    console_instances.normalize_instance(
                        {"id": "jp", "env_file": str(managed_env), "service": "ssh.service"}
                    )

    def test_instance_by_id_rejects_invalid_id_without_loading_instances(self) -> None:
        with patch.object(console_instances, "load_instances", side_effect=AssertionError("should not load")):
            self.assertIsNone(console_instances.instance_by_id("../../ssh"))


class ConsoleBackendTests(unittest.TestCase):
    def test_service_action_rejects_unknown_action_without_systemctl(self) -> None:
        with patch.object(console_backend, "systemctl", side_effect=AssertionError("should not run")):
            result = console_backend.service_action("aimilivpn@jp.service", "reload")

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "unsupported service action")

    def test_service_action_rejects_unmanaged_or_mismatched_service(self) -> None:
        with patch.object(console_backend, "systemctl", side_effect=AssertionError("should not run")):
            unmanaged = console_backend.service_action("ssh.service", "restart", instance_id="jp")
            mismatched = console_backend.service_action(
                "aimilivpn@us.service", "restart", instance_id="jp"
            )

        self.assertEqual(unmanaged["error"], "service operation rejected")
        self.assertEqual(mismatched["error"], "service operation rejected")

    def test_service_action_does_not_echo_exception_details(self) -> None:
        with patch.object(console_backend, "systemctl", side_effect=RuntimeError("sensitive detail")):
            result = console_backend.service_action(
                "aimilivpn@jp.service", "restart", instance_id="jp"
            )

        self.assertEqual(result, {"ok": False, "error": "服务操作失败"})
        self.assertNotIn("sensitive detail", str(result))

    def test_backend_request_does_not_echo_connection_details(self) -> None:
        with patch("http.client.HTTPConnection.request", side_effect=OSError("sensitive detail")):
            result = console_backend.backend_request({"id": "jp", "ui_port": 8787}, "/api/status")

        self.assertEqual(result, {"ok": False, "status": 502, "error": "backend unavailable"})


if __name__ == "__main__":
    unittest.main()
