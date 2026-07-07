from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class InstallScriptTests(unittest.TestCase):
    def test_ml_wrapper_uses_package_cli(self) -> None:
        text = (ROOT / "install.sh").read_text(encoding="utf-8")

        self.assertIn("write_ml_wrapper()", text)
        self.assertIn('exec /usr/bin/python3 -m aimilivpn.cli.main "\\$@"', text)
        self.assertNotIn("cat > /usr/bin/ml <<'EOF'", text)
        self.assertNotIn(": <<'EOF'", text)

    def test_update_defaults_to_fast_forward_and_gates_force_reset(self) -> None:
        text = (ROOT / "install.sh").read_text(encoding="utf-8")

        self.assertIn('git pull --ff-only origin "${DEPLOY_BRANCH}"', text)
        self.assertIn('if [ "${FORCE_UPDATE:-0}" = "1" ]; then', text)
        self.assertIn('git reset --hard "origin/${DEPLOY_BRANCH}"', text)
        self.assertLess(
            text.index('if [ "${FORCE_UPDATE:-0}" = "1" ]; then'),
            text.index('git reset --hard "origin/${DEPLOY_BRANCH}"'),
        )
        self.assertNotIn("git pull origin \"${DEPLOY_BRANCH}\"", text)

    def test_local_source_sync_includes_package_directory(self) -> None:
        text = (ROOT / "install.sh").read_text(encoding="utf-8")

        self.assertIn("for src_dir in aimilivpn tests; do", text)
        self.assertIn('cp -a "${SCRIPT_DIR}/${src_dir}" "${INSTALL_DIR}/${src_dir}"', text)

    def test_console_service_uses_packaged_runtime(self) -> None:
        text = (ROOT / "install.sh").read_text(encoding="utf-8")

        self.assertIn("ExecStart=/usr/bin/python3 -m aimilivpn.system.console_server", text)
        self.assertNotIn("ExecStart=/usr/bin/python3 console_server.py", text)

    def test_backend_service_uses_packaged_runtime(self) -> None:
        text = (ROOT / "install.sh").read_text(encoding="utf-8")

        self.assertIn("ExecStart=/usr/bin/python3 -m aimilivpn.system.vpngate_manager", text)
        self.assertIn('command_args="-m aimilivpn.system.vpngate_manager"', text)
        self.assertNotIn("ExecStart=/usr/bin/python3 vpngate_manager.py", text)

    def test_completion_output_does_not_print_plaintext_passwords(self) -> None:
        text = (ROOT / "install.sh").read_text(encoding="utf-8")

        self.assertNotIn("CONSOLE_PASS=", text)
        self.assertNotIn('PASSWORD=$(python3 -c "import json;', text)
        self.assertNotIn("Console password: ${YELLOW}${CONSOLE_PASS}", text)
        self.assertNotIn("网页管理密码:  ${YELLOW}${PASSWORD}", text)
        self.assertIn("Password status:", text)
        self.assertIn("ml password", text)

    def test_completion_output_uses_current_simple_cli_commands(self) -> None:
        text = (ROOT / "install.sh").read_text(encoding="utf-8")

        self.assertNotIn("ml jp logs", text)
        self.assertNotIn("ml us logs", text)
        self.assertNotIn("ml kr logs", text)
        self.assertNotIn("ml console restart", text)
        self.assertIn("ml logs", text)
        self.assertIn("ml restart", text)
        self.assertIn("ml web", text)

    def test_initial_auth_files_use_password_hash(self) -> None:
        text = (ROOT / "install.sh").read_text(encoding="utf-8")

        self.assertIn("from aimilivpn.core.auth import hash_password", text)
        self.assertIn('"password_hash": hash_password(password)', text)
        self.assertNotIn('"password": password', text)

    def test_install_generated_credentials_use_secrets(self) -> None:
        text = (ROOT / "install.sh").read_text(encoding="utf-8")

        self.assertIn("import secrets", text)
        self.assertIn("secrets.choice", text)
        self.assertNotIn("import random", text)
        self.assertNotIn("random.choices", text)

    def test_sysctl_persistence_does_not_edit_sysctl_conf(self) -> None:
        text = (ROOT / "install.sh").read_text(encoding="utf-8")

        self.assertIn("/etc/sysctl.d/99-aimilivpn.conf", text)
        self.assertIn("sysctl -w net.ipv4.conf.all.rp_filter=2", text)
        self.assertIn("leaving /etc/sysctl.conf untouched", text)
        self.assertNotIn(">> /etc/sysctl.conf", text)
        self.assertNotIn("sed -i 's/net.ipv4.conf", text)

    def test_systemd_units_use_low_risk_hardening(self) -> None:
        text = (ROOT / "install.sh").read_text(encoding="utf-8")

        self.assertEqual(text.count("NoNewPrivileges=yes"), 2)
        self.assertEqual(text.count("PrivateTmp=yes"), 2)
        self.assertNotIn("ProtectSystem=strict", text)
        self.assertNotIn("CapabilityBoundingSet=", text)


if __name__ == "__main__":
    unittest.main()
