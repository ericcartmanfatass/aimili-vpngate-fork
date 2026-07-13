from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CiBaselineTests(unittest.TestCase):
    def test_reference_python_version_is_pinned(self) -> None:
        self.assertEqual((ROOT / ".python-version").read_text(encoding="utf-8").strip(), "3.12")

    def test_linux_ci_runs_all_baseline_checks(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

        for expected in (
            'os: ["ubuntu-22.04", "ubuntu-24.04"]',
            'python: ["3.10", "3.12"]',
            "python -m compileall -q",
            "bash -n install.sh",
            "python -m unittest discover -s tests -p 'test*.py'",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, workflow)

    def test_testing_document_records_isolated_unit_test_contract(self) -> None:
        text = (ROOT / "TESTING.md").read_text(encoding="utf-8")

        self.assertIn("must not require a live VPN", text)
        self.assertIn("113 `PermissionError`", text)
        self.assertIn("Linux CI is the", text)


if __name__ == "__main__":
    unittest.main()
