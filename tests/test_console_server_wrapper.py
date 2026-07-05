from __future__ import annotations

import unittest

import console_server
from aimilivpn.system import console_server as console_runtime


class ConsoleServerWrapperTests(unittest.TestCase):
    def test_root_console_server_wrapper_reexports_runtime(self) -> None:
        self.assertIs(console_server.main, console_runtime.main)
        self.assertIs(console_server.Handler, console_runtime.Handler)


if __name__ == "__main__":
    unittest.main()
