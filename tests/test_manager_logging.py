from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from threading import RLock

from aimilivpn.system.manager_logging import ManagerJsonLogRuntime


class ManagerJsonLogRuntimeTests(unittest.TestCase):
    def test_log_to_json_writes_redacted_log_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = ManagerJsonLogRuntime(
                data_dir=Path(tmp),
                lock=RLock(),
                redact_message=lambda message: message.replace("secret", "***"),
            )

            runtime.log_to_json("INFO", "Test", "secret value")

            log_files = list((Path(tmp) / "logs").glob("*.json"))
            self.assertEqual(len(log_files), 1)
            entry = json.loads(log_files[0].read_text(encoding="utf-8").strip())
            self.assertEqual(entry["message"], "*** value")

    def test_cleanup_old_logs_uses_shared_cleanup_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = ManagerJsonLogRuntime(
                data_dir=Path(tmp),
                lock=RLock(),
                redact_message=lambda message: message,
            )

            runtime.cleanup_old_logs(Path(tmp) / "logs")

            self.assertIn("last_cleanup_time", runtime.cleanup_state)


if __name__ == "__main__":
    unittest.main()
