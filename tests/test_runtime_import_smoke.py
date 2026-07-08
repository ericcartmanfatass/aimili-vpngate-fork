from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class RuntimeImportSmokeTests(unittest.TestCase):
    def run_import_smoke(self, script: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-c", script],
            cwd=ROOT,
            env={**os.environ, **env},
            capture_output=True,
            text=True,
            timeout=15,
        )

    def test_packaged_backend_import_initializes_context_without_starting_service(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            script = (
                "import aimilivpn.system.vpngate_manager as manager; "
                "assert manager.MANAGER_CONTEXT.data_dir; "
                "assert manager.Handler"
            )
            result = self.run_import_smoke(
                script,
                {
                    "AIMILIVPN_INSTALL_DIR": str(ROOT),
                    "VPNGATE_DATA_DIR": tmp,
                    "LOCAL_PROXY_HOST": "127.0.0.1",
                    "UI_HOST": "127.0.0.1",
                },
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertTrue((Path(tmp) / "ui_auth.json").exists())

    def test_packaged_console_import_does_not_require_system_config_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            script = (
                "import aimilivpn.system.console_server as console; "
                "assert console.Handler; "
                "assert callable(console.main)"
            )
            result = self.run_import_smoke(
                script,
                {
                    "AIMILIVPN_CONFIG_DIR": tmp,
                    "AIMILIVPN_CONSOLE_AUTH": str(Path(tmp) / "console_auth.json"),
                    "AIMILIVPN_INSTANCES_FILE": str(Path(tmp) / "instances.json"),
                    "CONSOLE_PORT": "bad",
                },
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)


if __name__ == "__main__":
    unittest.main()
