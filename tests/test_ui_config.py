from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aimilivpn.core.auth import verify_password
from aimilivpn.system.ui_config import UiConfigStore, generate_username


class FakeLock:
    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None


def bounded_int(value: object, default: int, min_value: int, max_value: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    if parsed < min_value or parsed > max_value:
        return default
    return parsed


def build_store(root: Path) -> UiConfigStore:
    return UiConfigStore(
        data_dir=root,
        lock=FakeLock(),
        ui_host="127.0.0.1",
        ui_port=8787,
        proxy_port=7928,
        bounded_int=bounded_int,
        password_factory=lambda: "GeneratedPassword123",
        username_factory=lambda: "AdminUser1",
    )


class UiConfigStoreTests(unittest.TestCase):
    def test_generate_username_has_expected_complexity(self) -> None:
        username = generate_username()

        self.assertEqual(len(username), 12)
        self.assertTrue(username[0].isalpha())
        self.assertTrue(any(ch.islower() for ch in username))
        self.assertTrue(any(ch.isupper() for ch in username))
        self.assertTrue(any(ch.isdigit() for ch in username))

    def test_load_creates_missing_config_with_generated_auth(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = build_store(Path(tmp))

            with patch("builtins.print"):
                config = store.load()

            self.assertEqual(config["username"], "AdminUser1")
            self.assertTrue(verify_password("GeneratedPassword123", config["password_hash"]))
            self.assertNotIn("password", config)
            self.assertTrue(store.auth_file.exists())

    def test_load_migrates_legacy_plaintext_password(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = build_store(Path(tmp))
            store.auth_file.write_text(
                json.dumps({"username": "admin", "password": "legacy"}),
                encoding="utf-8",
            )

            with patch("builtins.print"):
                config = store.load()

            self.assertEqual(config["username"], "admin")
            self.assertTrue(verify_password("legacy", config["password_hash"]))
            self.assertNotIn("password", config)
            saved = json.loads(store.auth_file.read_text(encoding="utf-8"))
            self.assertNotIn("password", saved)

    def test_load_normalizes_invalid_and_conflicting_ports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = build_store(Path(tmp))
            store.auth_file.write_text(
                json.dumps({
                    "username": "admin",
                    "password_hash": "hash",
                    "port": "bad",
                    "proxy_port": 8787,
                }),
                encoding="utf-8",
            )

            with patch("builtins.print"):
                config = store.load()

            self.assertEqual(config["port"], 8787)
            self.assertEqual(config["proxy_port"], 7928)

    def test_save_migrates_plaintext_password(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = build_store(Path(tmp))

            store.save({"username": "admin", "password": "secret"})

            saved = json.loads(store.auth_file.read_text(encoding="utf-8"))
            self.assertNotIn("password", saved)
            self.assertTrue(verify_password("secret", saved["password_hash"]))


if __name__ == "__main__":
    unittest.main()
