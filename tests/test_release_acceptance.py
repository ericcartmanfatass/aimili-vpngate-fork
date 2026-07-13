from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ReleaseAcceptanceTests(unittest.TestCase):
    def test_migration_drill_upgrades_and_rolls_back_real_storage(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "release_migration_drill.py")],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "passed")
        self.assertTrue(payload["auth_plaintext_removed"])
        self.assertEqual(payload["migrated_documents"], 2)
        self.assertEqual(payload["rollback_checksums_verified"], ["nodes.json", "settings.json"])

    def test_linux_source_gate_covers_all_release_checks(self) -> None:
        text = (ROOT / "scripts" / "release-acceptance.sh").read_text(encoding="utf-8")

        self.assertIn('"$(uname -s)" != "Linux"', text)
        self.assertIn("python", text.lower())
        self.assertIn("unittest discover", text)
        self.assertIn("frontend_dom.test.js", text)
        self.assertIn("release_migration_drill.py", text)
        self.assertIn("git diff --check", text)


if __name__ == "__main__":
    unittest.main()
