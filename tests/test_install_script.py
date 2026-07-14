from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class InstallScriptTests(unittest.TestCase):
    def test_single_script_entry_supports_install_and_lifecycle_actions(self) -> None:
        text = (ROOT / "install.sh").read_text(encoding="utf-8")

        for option in (
            "--menu",
            "--ref",
            "--status",
            "--web",
            "--reset-password",
            "--uninstall",
        ):
            self.assertIn(option, text)
        self.assertIn("choose_menu_action()", text)
        self.assertIn("run_installed_action()", text)
        self.assertIn("offer_initial_password_reset()", text)
        self.assertIn("handoff_to_pinned_installer()", text)
        self.assertIn("curl --proto '=https' --proto-redir '=https' --tlsv1.2", text)
        self.assertIn("exec /usr/bin/ml uninstall --yes", text)

    def test_release_builder_emits_archive_checksum_from_tag(self) -> None:
        text = (ROOT / "scripts" / "build-release.sh").read_text(encoding="utf-8")

        self.assertIn('git archive --format=tar --prefix=', text)
        self.assertIn("gzip -n", text)
        self.assertIn('sha256sum "$ARCHIVE" > SHA256SUMS', text)

    def test_readme_requires_verified_local_installer(self) -> None:
        text = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertNotIn("bash <(curl", text)
        self.assertIn("docs/installation.md", text)

    def test_ml_wrapper_uses_package_cli(self) -> None:
        text = (ROOT / "install.sh").read_text(encoding="utf-8")

        self.assertIn("write_ml_wrapper()", text)
        self.assertIn('exec /usr/bin/python3 -m aimilivpn.cli.main "\\$@"', text)
        self.assertNotIn("cat > /usr/bin/ml <<'EOF'", text)
        self.assertNotIn(": <<'EOF'", text)

    def test_update_defaults_to_fast_forward_and_gates_force_reset(self) -> None:
        text = (ROOT / "install.sh").read_text(encoding="utf-8")

        self.assertIn('git merge --ff-only "$TARGET_COMMIT"', text)
        self.assertIn('if [ "${FORCE_UPDATE:-0}" = "1" ]; then', text)
        self.assertIn('git reset --hard "$TARGET_COMMIT"', text)
        self.assertIn('git bundle create "$BACKUP_DIR/source.bundle" --all', text)
        self.assertIn("git stash push --include-untracked", text)
        self.assertLess(
            text.index('git bundle create "$BACKUP_DIR/source.bundle" --all'),
            text.index('git reset --hard "$TARGET_COMMIT"'),
        )
        self.assertNotIn("git pull origin \"${DEPLOY_BRANCH}\"", text)

    def test_remote_install_uses_fixed_repository_and_immutable_ref_metadata(self) -> None:
        text = (ROOT / "install.sh").read_text(encoding="utf-8")

        self.assertIn('GITHUB_URL="https://github.com/ericcartmanfatass/aimili-vpngate-fork.git"', text)
        self.assertIn('INSTALL_REF="${AIMILIVPN_REF:-}"', text)
        self.assertIn('DEPLOY_REF="$INSTALL_REF"', text)
        self.assertIn("validate_deploy_ref()", text)
        self.assertIn('INSTALL_SHA256=$(sha256sum "${INSTALL_DIR}/install.sh"', text)
        self.assertIn('SOURCE_METADATA="/etc/aimilivpn/install-source.json"', text)
        self.assertIn("BOOTSTRAP_SHA256", text)
        self.assertIn("CHECKOUT_INSTALLER_SHA256", text)
        self.assertIn('if [ "$BOOTSTRAP_SHA256" != "$CHECKOUT_INSTALLER_SHA256" ]', text)
        self.assertNotIn('GITHUB_USER="${1:', text)

    def test_fresh_multi_instance_install_creates_jp_only(self) -> None:
        text = (ROOT / "install.sh").read_text(encoding="utf-8")

        self.assertIn('COUNTRIES="${COUNTRIES:-JP}"', text)
        self.assertNotIn('COUNTRIES="${COUNTRIES:-JP,US,KR}"', text)
        self.assertIn('systemctl enable --now "aimilivpn@${CC_LO}.service"', text)
        self.assertIn("PRESERVE_EXISTING_INSTANCES=1", text)
        self.assertIn("Preserving ${#CC_LIST[@]} existing instance catalog entries", text)

    def test_local_source_sync_includes_package_directory(self) -> None:
        text = (ROOT / "install.sh").read_text(encoding="utf-8")

        self.assertIn("for src_dir in aimilivpn tests docs; do", text)
        self.assertIn("README.md SECURITY.md MIGRATION.md TESTING.md", text)
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
        self.assertIn("sudo ml password reset", text)

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
        self.assertIn("99-aimilivpn.conf.preinstall", text)
        self.assertIn("network-changes.json", text)
        self.assertIn("RP_FILTER_ALL_BEFORE", text)
        self.assertIn('"runtime_before": runtime_before', text)
        self.assertLess(text.index("RP_FILTER_ALL_BEFORE="), text.index('systemctl enable --now "aimilivpn@'))
        self.assertIn('"dns_modified": False', text)
        self.assertIn("leaving /etc/sysctl.conf untouched", text)
        self.assertNotIn(">> /etc/sysctl.conf", text)
        self.assertNotIn("sed -i 's/net.ipv4.conf", text)

    def test_systemd_units_use_capability_and_filesystem_hardening(self) -> None:
        text = (ROOT / "install.sh").read_text(encoding="utf-8")

        self.assertEqual(text.count("NoNewPrivileges=yes"), 2)
        self.assertEqual(text.count("PrivateTmp=yes"), 2)
        self.assertIn("ProtectSystem=strict", text)
        self.assertIn("CapabilityBoundingSet=CAP_NET_ADMIN CAP_NET_RAW", text)
        self.assertIn("AmbientCapabilities=CAP_NET_ADMIN CAP_NET_RAW", text)
        self.assertIn("CapabilityBoundingSet=\n", text)
        self.assertEqual(text.count("UMask=0077"), 2)

    def test_management_interfaces_install_on_loopback_only(self) -> None:
        text = (ROOT / "install.sh").read_text(encoding="utf-8")

        self.assertIn('"host": "127.0.0.1"', text)
        self.assertIn("UI_HOST=127.0.0.1", text)
        self.assertNotIn('"host": "0.0.0.0"', text)
        self.assertNotIn('"host": "::"', text)
        self.assertNotIn("http://${PUBLIC_IP}:${CONSOLE_PORT}", text)
        self.assertNotIn("http://${PUBLIC_IP}:${UI_PORT}", text)

    def test_installer_points_remote_management_to_tls_proxy_docs(self) -> None:
        text = (ROOT / "install.sh").read_text(encoding="utf-8")

        self.assertIn("docs/reverse-proxy.md", text)
        self.assertIn("127.0.0.1:${CONSOLE_PORT}", text)


if __name__ == "__main__":
    unittest.main()
