from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aimilivpn.system.json_logs import JsonLogWriter, cleanup_json_logs


class FakeLock:
    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None


class JsonLogTests(unittest.TestCase):
    def test_writer_appends_redacted_json_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            logs_dir = Path(tmp)
            writer = JsonLogWriter(
                logs_dir=logs_dir,
                lock=FakeLock(),
                redact_message=lambda message: message.replace("secret", "***"),
                cleanup_state={},
            )

            with patch("aimilivpn.system.json_logs.time.time", return_value=1_704_067_200.0):
                writer.write("INFO", "Main", "token=secret")

            log_file = logs_dir / "2024-01-01.json"
            entry = json.loads(log_file.read_text(encoding="utf-8").strip())
            self.assertEqual(entry["level"], "INFO")
            self.assertEqual(entry["module"], "Main")
            self.assertEqual(entry["message"], "token=***")

    def test_cleanup_deletes_logs_at_least_three_days_old(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            logs_dir = Path(tmp)
            old_log = logs_dir / "2024-01-01.json"
            recent_log = logs_dir / "2024-01-03.json"
            old_log.write_text("{}", encoding="utf-8")
            recent_log.write_text("{}", encoding="utf-8")

            with patch("builtins.print"):
                cleanup_json_logs(logs_dir, FakeLock(), {}, now=1_704_326_400.0)

            self.assertFalse(old_log.exists())
            self.assertTrue(recent_log.exists())

    def test_cleanup_is_throttled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            logs_dir = Path(tmp)
            old_log = logs_dir / "2024-01-01.json"
            old_log.write_text("{}", encoding="utf-8")

            cleanup_json_logs(logs_dir, FakeLock(), {"last_cleanup_time": 1_704_326_000.0}, now=1_704_326_400.0)

            self.assertTrue(old_log.exists())


if __name__ == "__main__":
    unittest.main()
