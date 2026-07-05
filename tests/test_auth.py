from __future__ import annotations

import unittest

from aimilivpn.core.auth import (
    generate_password,
    generate_session_token,
    hash_password,
    migrate_auth_config,
    verify_password,
)


class AuthTests(unittest.TestCase):
    def test_hash_and_verify_password(self) -> None:
        stored = hash_password("correct horse battery staple")

        self.assertTrue(verify_password("correct horse battery staple", stored))
        self.assertFalse(verify_password("wrong", stored))
        self.assertTrue(stored.startswith("pbkdf2_sha256$260000$"))

    def test_migrate_plaintext_password_removes_password(self) -> None:
        migrated, changed, generated = migrate_auth_config({"username": "admin", "password": "secret"})

        self.assertTrue(changed)
        self.assertIsNone(generated)
        self.assertNotIn("password", migrated)
        self.assertTrue(verify_password("secret", migrated["password_hash"]))

    def test_generate_session_tokens_are_distinct(self) -> None:
        self.assertNotEqual(generate_session_token(), generate_session_token())

    def test_generate_password_has_minimum_complexity(self) -> None:
        password = generate_password()

        self.assertGreaterEqual(len(password), 24)
        self.assertTrue(any(ch.islower() for ch in password))
        self.assertTrue(any(ch.isupper() for ch in password))
        self.assertTrue(any(ch.isdigit() for ch in password))


if __name__ == "__main__":
    unittest.main()

