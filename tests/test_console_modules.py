from __future__ import annotations

import json
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
                "proxy_port": 7928,
                "tun_dev": "tun-jp",
                "policy_table": "100",
            }

            state = console_instances.instance_state(inst, service_active=lambda service: service.endswith("jp.service"))
            nodes = console_instances.stripped_nodes(inst, state_factory=lambda item: state)

            self.assertTrue(state["service_active"])
            self.assertEqual(state["active_node"]["id"], "jp_1")
            self.assertNotIn("config_text", nodes["nodes"][0])


class ConsoleBackendTests(unittest.TestCase):
    def test_service_action_rejects_unknown_action_without_systemctl(self) -> None:
        with patch.object(console_backend, "systemctl", side_effect=AssertionError("should not run")):
            result = console_backend.service_action("aimilivpn@jp.service", "reload")

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "unsupported service action")


if __name__ == "__main__":
    unittest.main()
