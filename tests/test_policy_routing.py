from __future__ import annotations

import unittest

from aimilivpn.system.policy_routing import PolicyRoutingFacade


class PolicyRoutingFacadeTests(unittest.TestCase):
    def test_setup_runs_cleanup_policy_routes_and_rp_filter(self) -> None:
        calls: list[tuple[list[str], dict[str, object]]] = []
        messages: list[str] = []

        def run_command(command: list[str], **kwargs: object) -> object:
            calls.append((command, kwargs))
            return object()

        facade = PolicyRoutingFacade(
            run_command=run_command,
            sleep=lambda seconds: None,
            print_line=lambda message: messages.append(message),
        )

        facade.setup("tun7", "107")

        commands = [command for command, _ in calls]
        self.assertEqual(commands[0], ["ip", "rule", "del", "table", "107"])
        self.assertEqual(commands[1], ["ip", "route", "flush", "table", "107"])
        self.assertIn(["ip", "route", "add", "default", "dev", "tun7", "table", "107"], commands)
        self.assertIn(["ip", "rule", "add", "oif", "tun7", "table", "107"], commands)
        self.assertIn(["sysctl", "-w", "net.ipv4.conf.tun7.rp_filter=2"], commands)
        self.assertTrue(any("第 1 次尝试成功" in message for message in messages))

    def test_setup_retries_and_logs_final_failure(self) -> None:
        sleeps: list[float] = []
        messages: list[str] = []
        logs: list[tuple[str, str]] = []

        def run_command(command: list[str], **kwargs: object) -> object:
            if command[:3] == ["ip", "route", "add"]:
                raise PermissionError("operation not permitted")
            return object()

        facade = PolicyRoutingFacade(
            run_command=run_command,
            sleep=lambda seconds: sleeps.append(seconds),
            print_line=lambda message: messages.append(message),
            log_line=lambda level, message: logs.append((level, message)),
        )

        facade.setup("tun7", "107")

        self.assertEqual(sleeps, [1, 1, 1])
        self.assertEqual(len([message for message in messages if "第 " in message and "次启用失败" in message]), 3)
        self.assertEqual(logs[0][0], "ERROR")
        self.assertIn("ERR_ROUTE_TABLE_ADD_FAILED", logs[0][1])

    def test_cleanup_runs_cleanup_commands_and_swallows_errors(self) -> None:
        calls: list[list[str]] = []
        messages: list[str] = []

        def run_command(command: list[str], **kwargs: object) -> object:
            calls.append(command)
            if len(calls) == 1:
                raise RuntimeError("already gone")
            return object()

        facade = PolicyRoutingFacade(
            run_command=run_command,
            print_line=lambda message: messages.append(message),
        )

        facade.cleanup("107")

        self.assertEqual(calls, [["ip", "rule", "del", "table", "107"]])
        self.assertEqual(messages, [])


if __name__ == "__main__":
    unittest.main()
