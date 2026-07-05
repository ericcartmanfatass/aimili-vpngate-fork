from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aimilivpn.system.blacklist_store import BlacklistStore


class FakeLock:
    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None


def build_store(path: Path, now: float = 100.0) -> BlacklistStore:
    return BlacklistStore(path=path, lock=FakeLock(), backoff_seconds=30, now=lambda: now)


class BlacklistStoreTests(unittest.TestCase):
    def test_load_cleans_expired_and_invalid_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "blacklist.json"
            path.write_text(
                json.dumps({
                    "active": {"until": 130.0},
                    "expired": {"until": 90.0},
                    "invalid": "bad",
                }),
                encoding="utf-8",
            )

            cleaned = build_store(path).load()

            self.assertEqual(cleaned, {"active": {"until": 130.0}})
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), cleaned)

    def test_mark_writes_ttl_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "blacklist.json"

            build_store(path).mark({"id": "node-1", "ip": "203.0.113.1", "country": "Japan"}, "failed")

            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["node-1"]["reason"], "failed")
            self.assertEqual(data["node-1"]["marked_at"], 100.0)
            self.assertEqual(data["node-1"]["until"], 130.0)

    def test_mark_ignores_node_without_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "blacklist.json"

            build_store(path).mark({"ip": "203.0.113.1"}, "failed")

            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
