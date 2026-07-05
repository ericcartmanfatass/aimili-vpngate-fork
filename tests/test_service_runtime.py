from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path
from typing import Any, Iterable

from aimilivpn.system.service_runtime import Tee, VpnGateServiceRuntime
from aimilivpn.system.startup import DaemonTask


class ServiceRuntimeTests(unittest.TestCase):
    def build_runtime(self, tmp: Path, calls: dict[str, Any], *, gateway_ready: bool = True) -> VpnGateServiceRuntime:
        def start_daemon_threads(tasks: Iterable[DaemonTask]) -> None:
            calls.setdefault("daemon_tasks", []).extend(list(tasks))

        return VpnGateServiceRuntime(
            ensure_dirs=lambda: calls.__setitem__("ensured", True),
            kill_existing_openvpn_processes=lambda: calls.__setitem__("killed", True),
            data_dir=lambda: tmp,
            state_file=lambda: tmp / "state.json",
            write_json=lambda path, data: calls.__setitem__("state", (path, data)),
            api_url=lambda: "https://example.test/api",
            instance_id=lambda: "default",
            tun_dev=lambda: "tun0",
            policy_table=lambda: "100",
            allowed_countries=lambda: {"JP", "KR"},
            target_valid_nodes=lambda: 3,
            fetch_interval_seconds=lambda: 60,
            check_interval_seconds=lambda: 30,
            local_proxy_host=lambda: "127.0.0.1",
            local_proxy_port=lambda: 7928,
            ui_host=lambda: "::",
            ui_port=lambda: 8787,
            start_proxy_server=lambda host, port, tun: None,
            collector_loop=lambda: None,
            background_proxy_checker=lambda: None,
            active_node_pinger=lambda: None,
            start_daemon_threads=start_daemon_threads,
            wait_for_gateway=lambda host, port: gateway_ready,
            load_ui_config=lambda: {"host": "127.0.0.1", "port": "9000"},
            bounded_int=lambda value, default, min_value, max_value: int(value or default),
            web_server_runtime=lambda: "runtime",
            serve_web_forever=lambda host, port, runtime: calls.__setitem__("served", (host, port, runtime)),
            print_line=lambda message: calls.setdefault("messages", []).append(message),
            set_stdout=lambda stream: calls.__setitem__("stdout", stream),
            set_stderr=lambda stream: calls.__setitem__("stderr", stream),
            tee_factory=lambda path: calls.setdefault("tee_paths", []).append(path) or object(),
        )

    def test_main_initializes_state_threads_and_web_server(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = Path(raw_tmp)
            calls: dict[str, Any] = {}
            runtime = self.build_runtime(tmp, calls)

            runtime.main()

        self.assertTrue(calls["ensured"])
        self.assertTrue(calls["killed"])
        self.assertEqual(calls["tee_paths"], [str(tmp / "vpngate.log")])
        self.assertIs(calls["stdout"], calls["stderr"])
        state_path, state = calls["state"]
        self.assertEqual(state_path, tmp / "state.json")
        self.assertEqual(state["allowed_countries"], ["JP", "KR"])
        self.assertEqual(calls["served"], ("127.0.0.1", 9000, "runtime"))
        self.assertEqual(len(calls["daemon_tasks"]), 4)
        self.assertIn("代理网关已成功启动监听", "\n".join(calls["messages"]))

    def test_main_reports_gateway_timeout_but_continues(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            calls: dict[str, Any] = {}
            runtime = self.build_runtime(Path(raw_tmp), calls, gateway_ready=False)

            runtime.main()

        self.assertIn("代理网关启动超时", "\n".join(calls["messages"]))
        self.assertIn("served", calls)

    def test_tee_writes_to_stdout_and_file(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            output = io.StringIO()
            log_path = Path(raw_tmp) / "nested" / "vpngate.log"
            tee = Tee(str(log_path), stdout=output)

            tee.write("hello")
            tee.flush()
            tee.file.close()
            log_text = log_path.read_text(encoding="utf-8")

        self.assertEqual(output.getvalue(), "hello")
        self.assertEqual(log_text, "hello")


if __name__ == "__main__":
    unittest.main()