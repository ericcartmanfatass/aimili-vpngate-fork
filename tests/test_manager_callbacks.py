from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from aimilivpn.system import manager_callbacks


class ManagerCallbacksTests(unittest.TestCase):
    def test_module_log_writer_adds_module_name(self) -> None:
        log_to_json = Mock()
        writer = manager_callbacks.module_log_writer(log_to_json, "VPN")

        writer("INFO", "ready")

        log_to_json.assert_called_once_with("INFO", "VPN", "ready")

    def test_diagnose_with_host_keyword_adapts_host_argument(self) -> None:
        diagnose = Mock(return_value=(True, "ok"))
        adapted = manager_callbacks.diagnose_with_host_keyword(diagnose)

        self.assertEqual(adapted(7928, "127.0.0.1"), (True, "ok"))
        diagnose.assert_called_once_with(7928, host="127.0.0.1")

    def test_print_line_flushes(self) -> None:
        with patch("aimilivpn.system.manager_callbacks.print") as print_mock:
            manager_callbacks.print_line("hello")

        print_mock.assert_called_once_with("hello", flush=True)

    def test_console_token_reads_environment(self) -> None:
        with patch.dict("aimilivpn.system.manager_callbacks.os.environ", {"INSTANCE_API_TOKEN": "token"}, clear=True):
            self.assertEqual(manager_callbacks.console_token(), "token")

    def test_stream_setters_update_sys_streams(self) -> None:
        stdout = object()
        stderr = object()
        original_stdout = manager_callbacks.sys.stdout
        original_stderr = manager_callbacks.sys.stderr
        try:
            manager_callbacks.set_stdout(stdout)
            manager_callbacks.set_stderr(stderr)
            self.assertIs(manager_callbacks.sys.stdout, stdout)
            self.assertIs(manager_callbacks.sys.stderr, stderr)
        finally:
            manager_callbacks.sys.stdout = original_stdout
            manager_callbacks.sys.stderr = original_stderr

    def test_exit_process_delegates_to_os_exit(self) -> None:
        with patch("aimilivpn.system.manager_callbacks.os._exit") as exit_mock:
            manager_callbacks.exit_process(3)

        exit_mock.assert_called_once_with(3)


if __name__ == "__main__":
    unittest.main()
