from __future__ import annotations

import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aimilivpn.cli.main import main
from aimilivpn.core.models import QualityResult, RegionProfile
from aimilivpn.core.storage import NodeRepository, QualityRepository, RegionRepository


class CliParserTests(unittest.TestCase):
    def run_cli(self, data_dir: str, *args: str, runner=None, extra_env: dict[str, str] | None = None) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        env = {"VPNGATE_DATA_DIR": data_dir}
        if extra_env:
            env.update(extra_env)
        with patch.dict(os.environ, env, clear=False):
            code = main(args, stdout=stdout, stderr=stderr, root_dir=Path(data_dir), runner=runner)
        return code, stdout.getvalue(), stderr.getvalue()

    def write_instances(self, tmp: str, install_dir: Path | None = None) -> Path:
        cfg_dir = Path(tmp) / "etc"
        cfg_dir.mkdir()
        data_dir = (install_dir / "data" / "jp") if install_dir else (Path(tmp) / "jp-data")
        (cfg_dir / "instances.json").write_text(json.dumps({
            "instances": [
                {
                    "id": "jp",
                    "country": "JP",
                    "service": "aimilivpn@jp.service",
                    "data_dir": str(data_dir),
                    "ui_host": "127.0.0.1",
                    "ui_port": 8787,
                    "proxy_port": 7928,
                    "tun_dev": "tun0",
                    "policy_table": 100,
                }
            ]
        }), encoding="utf-8")
        (cfg_dir / "console_auth.json").write_text(json.dumps({
            "username": "admin",
            "password": "plain-secret",
            "secret_path": "consoleabc",
            "host": "0.0.0.0",
            "port": 8788,
        }), encoding="utf-8")
        data_dir.mkdir(parents=True)
        (data_dir / "ui_auth.json").write_text(json.dumps({
            "username": "webadmin",
            "password_hash": "hash-secret",
            "secret_path": "webabc",
            "port": 8787,
            "proxy_port": 7928,
        }), encoding="utf-8")
        return cfg_dir

    def test_status_outputs_json_without_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = {
                "VPNGATE_DATA_DIR": tmp,
                "SCAMALYTICS_USERNAME": "demo-user",
                "SCAMALYTICS_API_KEY": "super-secret",
            }
            stdout = io.StringIO()
            stderr = io.StringIO()
            with patch.dict(os.environ, env, clear=False):
                code = main(["--json", "status"], stdout=stdout, stderr=stderr, root_dir=Path(tmp))

        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["scamalytics_configured"])
        self.assertNotIn("super-secret", stdout.getvalue())
        self.assertEqual(stderr.getvalue(), "")

    def test_nodes_list_filters_by_region_and_outputs_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            NodeRepository(Path(tmp) / "nodes.json").replace_all_dicts([
                {"id": "jp_1", "country_short": "JP", "ip": "203.0.113.1", "latency_ms": 80},
                {"id": "us_1", "country_short": "US", "ip": "203.0.113.2", "latency_ms": 120},
            ])
            RegionRepository(Path(tmp) / "regions.json").create(
                RegionProfile(id="japan", name="Japan", country_codes=["JP"])
            )
            QualityRepository(Path(tmp) / "quality_results.json").save(QualityResult(
                node_id="jp_1",
                exit_ip="203.0.113.1",
                tcp_latency_ms=80,
                openvpn_success=True,
                handshake_ms=None,
                risk_provider="scamalytics",
                risk_score=15,
                risk_level="low",
                proxy_detected=False,
                datacenter_detected=False,
                country_match=None,
                checked_at="2026-06-17T00:00:00Z",
                score=90,
                label="Excellent",
            ))

            code, out, err = self.run_cli(tmp, "--json", "nodes", "list", "--region", "japan")

        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["id"], "jp_1")
        self.assertEqual(payload[0]["quality_score"], 90)
        self.assertEqual(err, "")

    def test_nodes_short_command_lists_nodes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            NodeRepository(Path(tmp) / "nodes.json").replace_all_dicts([
                {"id": "jp_1", "country_short": "JP", "ip": "203.0.113.1"},
            ])

            code, out, err = self.run_cli(tmp, "nodes", "--json")

        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)[0]["id"], "jp_1")
        self.assertEqual(err, "")

    def test_json_flag_works_after_subcommand(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            RegionRepository(Path(tmp) / "regions.json").create(
                RegionProfile(id="asia", name="Asia", country_codes=["JP"])
            )

            code, out, err = self.run_cli(tmp, "regions", "list", "--json")

        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload[0]["id"], "asia")
        self.assertEqual(err, "")

    def test_regions_list_outputs_table(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            RegionRepository(Path(tmp) / "regions.json").create(
                RegionProfile(id="asia", name="Asia", country_codes=["JP", "KR"], max_risk_score=40)
            )

            code, out, err = self.run_cli(tmp, "regions", "list")

        self.assertEqual(code, 0)
        self.assertIn("id\tname\tcountries", out)
        self.assertIn("asia\tAsia\tJP,KR", out)
        self.assertEqual(err, "")

    def test_start_operates_instance_and_console_services(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg_dir = self.write_instances(tmp)
            calls: list[list[str]] = []

            def runner(command: list[str]) -> subprocess.CompletedProcess[str]:
                calls.append(command)
                return subprocess.CompletedProcess(command, 0, "active\n", "")

            code, out, err = self.run_cli(
                tmp,
                "start",
                runner=runner,
                extra_env={"AIMILIVPN_CONFIG_DIR": str(cfg_dir)},
            )

        self.assertEqual(code, 0)
        self.assertIn(["systemctl", "start", "aimilivpn@jp.service"], calls)
        self.assertIn(["systemctl", "start", "aimilivpn-console.service"], calls)
        self.assertIn("start requested", out)
        self.assertEqual(err, "")

    def test_logs_uses_journalctl_for_discovered_services(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg_dir = self.write_instances(tmp)
            calls: list[list[str]] = []

            def runner(command: list[str]) -> subprocess.CompletedProcess[str]:
                calls.append(command)
                return subprocess.CompletedProcess(command, 0, "log line\n", "")

            code, out, err = self.run_cli(
                tmp,
                "logs",
                "--lines",
                "5",
                runner=runner,
                extra_env={"AIMILIVPN_CONFIG_DIR": str(cfg_dir)},
            )

        self.assertEqual(code, 0)
        self.assertEqual(calls[0], ["journalctl", "-u", "aimilivpn@jp.service", "-u", "aimilivpn-console.service", "-n", "5"])
        self.assertEqual(out, "log line\n")
        self.assertEqual(err, "")

    def test_web_port_password_do_not_print_password_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg_dir = self.write_instances(tmp)
            env = {"AIMILIVPN_CONFIG_DIR": str(cfg_dir)}

            web_code, web_out, _ = self.run_cli(tmp, "web", "--json", extra_env=env)
            port_code, port_out, _ = self.run_cli(tmp, "port", extra_env=env)
            password_code, password_out, _ = self.run_cli(tmp, "password", extra_env=env)

        self.assertEqual(web_code, 0)
        self.assertEqual(port_code, 0)
        self.assertEqual(password_code, 0)
        combined = web_out + port_out + password_out
        self.assertIn("http://127.0.0.1:8788/consoleabc/", combined)
        self.assertIn("7928", combined)
        self.assertIn("change in Web UI", combined)
        self.assertNotIn("plain-secret", combined)
        self.assertNotIn("hash-secret", combined)

    def test_uninstall_requires_explicit_yes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code, out, err = self.run_cli(tmp, "uninstall")

        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("uninstall requires --yes", err)

    def test_uninstall_preserves_data_and_source_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            install_dir = Path(tmp) / "opt" / "aimilivpn"
            cfg_dir = self.write_instances(tmp, install_dir=install_dir)
            unit_dir = Path(tmp) / "systemd"
            ml_path = Path(tmp) / "bin" / "ml"
            data_dir = install_dir / "data" / "jp"
            install_dir.mkdir(parents=True, exist_ok=True)
            unit_dir.mkdir()
            ml_path.parent.mkdir()
            ml_path.write_text("#!/bin/sh\n", encoding="utf-8")
            (unit_dir / "aimilivpn@.service").write_text("unit", encoding="utf-8")
            (unit_dir / "aimilivpn-console.service").write_text("unit", encoding="utf-8")
            calls: list[list[str]] = []

            def runner(command: list[str]) -> subprocess.CompletedProcess[str]:
                calls.append(command)
                return subprocess.CompletedProcess(command, 0, "", "")

            env = {
                "AIMILIVPN_CONFIG_DIR": str(cfg_dir),
                "AIMILIVPN_INSTALL_DIR": str(install_dir),
                "AIMILIVPN_SYSTEMD_UNIT_DIRS": str(unit_dir),
                "AIMILIVPN_ML_PATH": str(ml_path),
            }
            code, out, err = self.run_cli(tmp, "uninstall", "--yes", runner=runner, extra_env=env)

            self.assertEqual(code, 0)
            self.assertIn(["systemctl", "stop", "aimilivpn@jp.service"], calls)
            self.assertIn(["systemctl", "disable", "aimilivpn-console.service"], calls)
            self.assertFalse(cfg_dir.exists())
            self.assertFalse(ml_path.exists())
            self.assertFalse((unit_dir / "aimilivpn@.service").exists())
            self.assertTrue(data_dir.exists())
            self.assertTrue(install_dir.exists())
            self.assertIn("Data preserved by default", out)
            self.assertEqual(err, "")

    def test_uninstall_delete_data_requires_extra_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg_dir = self.write_instances(tmp)
            env = {"AIMILIVPN_CONFIG_DIR": str(cfg_dir)}

            code, out, err = self.run_cli(tmp, "uninstall", "--yes", "--delete-data", extra_env=env)

        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("--delete-data requires --confirm-delete-data", err)

    def test_uninstall_can_delete_data_with_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            install_dir = Path(tmp) / "opt" / "aimilivpn"
            cfg_dir = self.write_instances(tmp, install_dir=install_dir)
            unit_dir = Path(tmp) / "systemd"
            ml_path = Path(tmp) / "bin" / "ml"
            data_dir = install_dir / "data" / "jp"
            install_dir.mkdir(parents=True, exist_ok=True)
            unit_dir.mkdir()
            ml_path.parent.mkdir()
            ml_path.write_text("#!/bin/sh\n", encoding="utf-8")
            calls: list[list[str]] = []

            def runner(command: list[str]) -> subprocess.CompletedProcess[str]:
                calls.append(command)
                return subprocess.CompletedProcess(command, 0, "", "")

            env = {
                "AIMILIVPN_CONFIG_DIR": str(cfg_dir),
                "AIMILIVPN_INSTALL_DIR": str(install_dir),
                "AIMILIVPN_SYSTEMD_UNIT_DIRS": str(unit_dir),
                "AIMILIVPN_ML_PATH": str(ml_path),
            }
            code, out, err = self.run_cli(
                tmp,
                "uninstall",
                "--yes",
                "--delete-data",
                "--confirm-delete-data",
                runner=runner,
                extra_env=env,
            )

            self.assertEqual(code, 0)
            self.assertFalse(data_dir.exists())
            self.assertTrue(install_dir.exists())
            self.assertIn("AimiliVPN uninstall actions complete", out)
            self.assertEqual(err, "")

    def test_uninstall_refuses_data_path_outside_install_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            install_dir = Path(tmp) / "opt" / "aimilivpn"
            cfg_dir = self.write_instances(tmp)
            outside_data = Path(tmp) / "jp-data"
            env = {
                "AIMILIVPN_CONFIG_DIR": str(cfg_dir),
                "AIMILIVPN_INSTALL_DIR": str(install_dir),
                "AIMILIVPN_SYSTEMD_UNIT_DIRS": str(Path(tmp) / "systemd"),
                "AIMILIVPN_ML_PATH": str(Path(tmp) / "bin" / "ml"),
            }

            code, out, err = self.run_cli(
                tmp,
                "uninstall",
                "--yes",
                "--delete-data",
                "--confirm-delete-data",
                extra_env=env,
            )

            self.assertEqual(code, 1)
            self.assertTrue(outside_data.exists())
            self.assertIn("refusing to remove path outside allowed roots", err)

    def test_quality_latest_reports_missing_node(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code, out, err = self.run_cli(tmp, "quality", "latest", "missing")

        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("quality result not found: missing", err)


if __name__ == "__main__":
    unittest.main()
