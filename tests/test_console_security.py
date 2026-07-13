from __future__ import annotations

import unittest

from aimilivpn.system.console_security import LoginAttemptLimiter


class LoginAttemptLimiterTests(unittest.TestCase):
    def test_limiter_is_per_ip_and_recovers_after_window(self) -> None:
        now = [100.0]
        limiter = LoginAttemptLimiter(2, 10, clock=lambda: now[0])

        self.assertTrue(limiter.allow("198.51.100.1"))
        self.assertTrue(limiter.allow("198.51.100.1"))
        self.assertFalse(limiter.allow("198.51.100.1"))
        self.assertTrue(limiter.allow("198.51.100.2"))

        now[0] = 111.0
        self.assertTrue(limiter.allow("198.51.100.1"))

    def test_reset_clears_client_attempts(self) -> None:
        limiter = LoginAttemptLimiter(1, 60, clock=lambda: 100.0)
        self.assertTrue(limiter.allow("198.51.100.1"))
        self.assertFalse(limiter.allow("198.51.100.1"))

        limiter.reset("198.51.100.1")

        self.assertTrue(limiter.allow("198.51.100.1"))


if __name__ == "__main__":
    unittest.main()
