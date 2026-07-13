from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SYSTEM_DIR = REPO_ROOT / "aimilivpn" / "system"


class ManagerRuntimeContextStaticTests(unittest.TestCase):
    def test_context_root_only_delegates_to_segment_modules(self) -> None:
        source = (SYSTEM_DIR / "manager_runtime_context.py").read_text(encoding="utf-8")

        self.assertIn("context_environment.apply_runtime_environment(self, compiled=compiled)", source)
        self.assertIn("context_foundation.build_repository_runtime(self)", source)
        self.assertIn("context_support.build_fetch_runtime(self)", source)
        self.assertIn("context_connection.build_connection_runtime(self)", source)
        self.assertIn("context_web.build_web_runtime(self)", source)
        self.assertIn("context_process.build_openvpn_runtime(self)", source)
        self.assertNotIn("build_manager_runtime_environment(", source)
        self.assertNotIn("RuntimeWiring(", source)
        self.assertNotIn("build_repositories(", source)

    def test_vpngate_manager_entry_does_not_import_context_segments(self) -> None:
        source = (SYSTEM_DIR / "vpngate_manager.py").read_text(encoding="utf-8")

        self.assertIn("manager_runtime_context as runtime_context", source)
        self.assertNotIn("manager_runtime_context_foundation", source)
        self.assertNotIn("manager_runtime_context_connection", source)
        self.assertNotIn("manager_runtime_context_environment", source)
        self.assertNotIn("manager_runtime_context_process", source)
        self.assertNotIn("manager_runtime_context_support", source)
        self.assertNotIn("manager_runtime_context_web", source)

    def test_runtime_context_exposes_explicit_service_contract_bundle(self) -> None:
        source = (SYSTEM_DIR / "manager_runtime_context.py").read_text(encoding="utf-8")

        self.assertIn("self.services = ManagerRuntimeServices(", source)
        for name in ("config", "repositories", "connection", "monitoring", "lifecycle", "logs", "web"):
            self.assertIn(f"{name}=", source)

    def test_internal_runtime_modules_do_not_import_compat_entrypoint(self) -> None:
        offenders = []
        for path in SYSTEM_DIR.glob("*.py"):
            if path.name == "vpngate_manager.py":
                continue
            source = path.read_text(encoding="utf-8")
            if "import vpngate_manager" in source or "from vpngate_manager" in source:
                offenders.append(path.name)

        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
