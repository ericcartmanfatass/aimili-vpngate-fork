from __future__ import annotations

import unittest
from unittest.mock import Mock

from aimilivpn.system.manager_auth import ManagerAuthRuntime


class ManagerAuthRuntimeTests(unittest.TestCase):
    def make_runtime(self) -> ManagerAuthRuntime:
        return ManagerAuthRuntime(
            token_factory=Mock(name="token_factory", return_value="token"),
            password_verifier=Mock(name="password_verifier", return_value=True),
            username_verifier=Mock(name="username_verifier", return_value=True),
        )

    def test_generate_and_get_session_token_delegate_to_factory(self) -> None:
        runtime = self.make_runtime()

        self.assertEqual(runtime.generate_session_token(), "token")
        self.assertEqual(runtime.get_session_token("password", "admin"), "token")
        self.assertEqual(runtime.token_factory.call_count, 2)

    def test_verifiers_delegate_to_core_auth(self) -> None:
        runtime = self.make_runtime()

        self.assertTrue(runtime.verify_password("password", "hash"))
        self.assertTrue(runtime.verify_username("admin", "expected-admin"))

        runtime.password_verifier.assert_called_once_with("password", "hash")
        runtime.username_verifier.assert_called_once_with("admin", "expected-admin")


if __name__ == "__main__":
    unittest.main()
