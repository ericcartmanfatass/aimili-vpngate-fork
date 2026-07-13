from __future__ import annotations

import unittest
from pathlib import Path

from aimilivpn.system.connection_runtime import ActiveConnectionRuntimeFacade


class FakeProcess:
    def __init__(self, poll_result: int | None = None) -> None:
        self.poll_result = poll_result

    def poll(self) -> int | None:
        return self.poll_result


def build_facade(**overrides: object) -> ActiveConnectionRuntimeFacade:
    kwargs = {
        "cleanup_policy_routing": lambda: None,
        "read_nodes": lambda: [],
        "write_nodes": lambda nodes: None,
        "load_ui_config": lambda: {},
        "save_ui_config": lambda config: None,
        "find_active_config_file": lambda nodes, node_id: None,
        "clear_active_flags": lambda nodes: None,
        "stop_process": lambda proc: None,
        "kill_existing_processes": lambda: None,
        "delete_file_if_exists": lambda path: False,
        "set_state": lambda **kwargs: None,
        "run_exclusive": lambda callback: callback(),
        "log_line": None,
        "print_line": lambda message: None,
    }
    kwargs.update(overrides)
    return ActiveConnectionRuntimeFacade(**kwargs)  # type: ignore[arg-type]


class ActiveConnectionRuntimeFacadeTests(unittest.TestCase):
    def test_begin_connect_sets_connecting_state(self) -> None:
        states: list[dict[str, object]] = []
        facade = build_facade(set_state=lambda **kwargs: states.append(kwargs))

        is_connecting = facade.begin_connect(
            node_id="node-1",
            is_connecting=False,
            busy_log_message="busy",
            busy_error_message="already busy",
            active_node_latency="connecting",
            last_check_message="initializing {node_id}",
        )

        self.assertTrue(is_connecting)
        self.assertEqual(
            states,
            [
                {
                    "is_connecting": True,
                    "active_node_latency": "connecting",
                    "last_check_message": "initializing node-1",
                }
            ],
        )

    def test_begin_connect_rejects_when_already_connecting(self) -> None:
        messages: list[str] = []
        states: list[dict[str, object]] = []
        facade = build_facade(
            print_line=lambda message: messages.append(message),
            set_state=lambda **kwargs: states.append(kwargs),
        )

        with self.assertRaisesRegex(RuntimeError, "already busy"):
            facade.begin_connect(
                node_id="node-1",
                is_connecting=True,
                busy_log_message="busy",
                busy_error_message="already busy",
                active_node_latency="connecting",
                last_check_message="initializing {node_id}",
            )

        self.assertEqual(messages, ["busy"])
        self.assertEqual(states, [])

    def test_finish_connecting_returns_released_flag(self) -> None:
        facade = build_facade()

        self.assertFalse(facade.finish_connecting())

    def test_prepare_target_reads_nodes_updates_and_saves_ui_config(self) -> None:
        nodes = [{"id": "node-1", "country_short": "JP"}]
        saved_configs: list[dict[str, object]] = []
        events: list[str] = []

        def run_exclusive(callback) -> None:
            events.append("lock-enter")
            callback()
            events.append("lock-exit")

        facade = build_facade(
            read_nodes=lambda: nodes,
            load_ui_config=lambda: {"routing_mode": "fixed_ip"},
            save_ui_config=lambda config: saved_configs.append(dict(config)),
            run_exclusive=run_exclusive,
        )

        returned_nodes, node = facade.prepare_target(
            "node-1",
            node_matches_allowed=lambda item: True,
            allowed_countries={"JP"},
        )

        self.assertIs(returned_nodes, nodes)
        self.assertIs(node, nodes[0])
        self.assertEqual(saved_configs, [{"routing_mode": "fixed_ip", "connection_enabled": True, "fixed_node_id": "node-1"}])
        self.assertEqual(events, ["lock-enter", "lock-exit"])

    def test_prepare_target_rejects_disallowed_node(self) -> None:
        facade = build_facade(
            read_nodes=lambda: [{"id": "node-1", "country_short": "US"}],
            load_ui_config=lambda: {},
        )

        with self.assertRaisesRegex(ValueError, "outside this instance allowed countries"):
            facade.prepare_target(
                "node-1",
                node_matches_allowed=lambda item: False,
                allowed_countries={"JP"},
            )

    def test_handle_start_failure_marks_node_failed_and_returns_empty_active_id(self) -> None:
        nodes = [{"id": "node-1", "active": True}, {"id": "node-2", "active": True}]
        deleted: list[str | Path | None] = []
        written_nodes: list[list[dict[str, object]]] = []
        logs: list[tuple[str, str]] = []
        messages: list[str] = []
        states: list[dict[str, object]] = []
        facade = build_facade(
            delete_file_if_exists=lambda path: deleted.append(path) or True,
            write_nodes=lambda updated: written_nodes.append([dict(node) for node in updated]),
            log_line=lambda level, message: logs.append((level, message)),
            print_line=lambda message: messages.append(message),
            set_state=lambda **kwargs: states.append(kwargs),
        )

        active_node_id = facade.handle_start_failure(
            nodes=nodes,
            node_id="node-1",
            config_path="/tmp/node-1.ovpn",
            message="AUTH_FAILED",
            log_message_template="connect {node_id} failed: {message}",
            print_message_template="failed {node_id}: {message}",
        )

        self.assertEqual(active_node_id, "")
        self.assertEqual(deleted, ["/tmp/node-1.ovpn"])
        self.assertEqual(written_nodes[0][0]["active"], False)
        self.assertEqual(written_nodes[0][0]["probe_status"], "unavailable")
        self.assertEqual(written_nodes[0][0]["probe_message"], "AUTH_FAILED")
        self.assertEqual(written_nodes[0][1]["active"], False)
        self.assertEqual(logs, [("ERROR", "connect node-1 failed: AUTH_FAILED")])
        self.assertEqual(messages, ["failed node-1: AUTH_FAILED"])
        self.assertEqual(states[0]["active_openvpn_node_id"], "")
        self.assertEqual(states[0]["is_connecting"], False)
        self.assertEqual(states[0]["last_check_message"], "连接失败: connection could not be established")

    def test_register_active_process_returns_process_and_node_id(self) -> None:
        process = FakeProcess()
        facade = build_facade()

        active_process, active_node_id = facade.register_active_process(process, "node-1")  # type: ignore[arg-type]

        self.assertIs(active_process, process)
        self.assertEqual(active_node_id, "node-1")

    def test_stop_active_cleans_routing_processes_and_config(self) -> None:
        events: list[str] = []
        deleted: list[str | Path | None] = []
        process = FakeProcess()

        facade = build_facade(
            cleanup_policy_routing=lambda: events.append("cleanup-routing"),
            read_nodes=lambda: [{"id": "node-1", "config_file": "/tmp/node-1.ovpn"}],
            find_active_config_file=lambda nodes, node_id: str(nodes[0]["config_file"]),
            stop_process=lambda proc: events.append(f"stop-process:{proc is process}"),
            kill_existing_processes=lambda: events.append("kill-existing"),
            delete_file_if_exists=lambda path: deleted.append(path) or True,
        )

        new_process, new_node_id = facade.stop_active(process, "node-1")  # type: ignore[arg-type]

        self.assertIsNone(new_process)
        self.assertEqual(new_node_id, "")
        self.assertEqual(events, ["cleanup-routing", "stop-process:True", "kill-existing"])
        self.assertEqual(deleted, ["/tmp/node-1.ovpn"])

    def test_stop_active_without_node_skips_node_lookup(self) -> None:
        read_calls = 0
        deleted: list[str | Path | None] = []

        def read_nodes() -> list[dict[str, object]]:
            nonlocal read_calls
            read_calls += 1
            return []

        facade = build_facade(
            cleanup_policy_routing=lambda: None,
            read_nodes=read_nodes,
            find_active_config_file=lambda nodes, node_id: "unexpected",
            stop_process=lambda proc: None,
            kill_existing_processes=lambda: None,
            delete_file_if_exists=lambda path: deleted.append(path) or False,
        )

        facade.stop_active(None, "")

        self.assertEqual(read_calls, 0)
        self.assertEqual(deleted, [None])

    def test_is_running_checks_process_poll(self) -> None:
        facade = build_facade()

        self.assertTrue(facade.is_running(FakeProcess(None)))  # type: ignore[arg-type]
        self.assertFalse(facade.is_running(FakeProcess(0)))  # type: ignore[arg-type]
        self.assertFalse(facade.is_running(None))

    def test_clear_active_state_stops_process_clears_nodes_and_updates_state(self) -> None:
        process = FakeProcess()
        nodes = [{"id": "node-1", "active": True}, {"id": "node-2", "active": True}]
        written_nodes: list[list[dict[str, object]]] = []
        states: list[dict[str, object]] = []
        events: list[str] = []

        def run_exclusive(callback) -> None:
            events.append("lock-enter")
            callback()
            events.append("lock-exit")

        facade = build_facade(
            read_nodes=lambda: nodes,
            write_nodes=lambda updated: written_nodes.append([dict(node) for node in updated]),
            clear_active_flags=lambda updated: [node.update({"active": False}) for node in updated],
            stop_process=lambda proc: events.append(f"stop:{proc is process}"),
            set_state=lambda **kwargs: states.append(kwargs),
            run_exclusive=run_exclusive,
        )

        new_process, new_node_id = facade.clear_active_state(process, "failed")  # type: ignore[arg-type]

        self.assertIsNone(new_process)
        self.assertEqual(new_node_id, "")
        self.assertEqual(events, ["stop:True", "lock-enter", "lock-exit"])
        self.assertEqual(written_nodes[0], [{"id": "node-1", "active": False}, {"id": "node-2", "active": False}])
        self.assertEqual(
            states[0],
            {
                "active_openvpn_node_id": "",
                "is_connecting": False,
                "active_node_latency": "无活动连接",
                "last_check_message": "failed",
            },
        )


if __name__ == "__main__":
    unittest.main()
