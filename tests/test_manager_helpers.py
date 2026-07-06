from __future__ import annotations

import unittest

from aimilivpn.system.manager_helpers import parse_int, safe_name


class ManagerHelpersTests(unittest.TestCase):
    def test_safe_name_normalizes_untrusted_text(self) -> None:
        self.assertEqual(safe_name(" jp node/1 "), "jp_node_1")
        self.assertEqual(safe_name("..."), "node")

    def test_parse_int_returns_zero_for_invalid_values(self) -> None:
        self.assertEqual(parse_int("42"), 42)
        self.assertEqual(parse_int(None), 0)
        self.assertEqual(parse_int("bad"), 0)


if __name__ == "__main__":
    unittest.main()
