from __future__ import annotations

import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import Mock, patch

import console_server
from aimilivpn.system import console_server as console_runtime


class ConsoleServerWrapperTests(unittest.TestCase):
    def test_root_console_server_wrapper_reexports_runtime(self) -> None:
        self.assertIs(console_server.main, console_runtime.main)
        self.assertIs(console_server.Handler, console_runtime.Handler)

    def test_console_startup_log_hides_secret_path_and_warns_about_plain_http(self) -> None:
        server = Mock()
        auth = {
            "host": "127.0.0.1",
            "port": 8788,
            "secret_path": "do-not-log-this",
        }

        with (
            patch.object(console_runtime, "load_console_auth", return_value=auth),
            patch.object(console_runtime, "ThreadingHTTPServer", return_value=server),
            redirect_stdout(StringIO()) as output,
        ):
            console_runtime.main()

        text = output.getvalue()
        self.assertNotIn("do-not-log-this", text)
        self.assertIn("secret path hidden", text)
        self.assertIn("本机明文 HTTP", text)
        server.serve_forever.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
