from __future__ import annotations

import unittest
from unittest.mock import MagicMock, Mock

from aimilivpn.system.manager_threads import ManagerThreadRuntime


class ManagerThreadRuntimeTests(unittest.TestCase):
    def make_runtime(self, thread_factory: Mock | None = None) -> ManagerThreadRuntime:
        return ManagerThreadRuntime(
            lock=MagicMock(name="lock"),
            maintenance_lock=Mock(name="maintenance_lock"),
            maintain_valid_nodes=Mock(name="maintain_valid_nodes"),
            thread_factory=thread_factory or Mock(name="thread_factory"),
        )

    def test_run_with_lock_returns_callback_result(self) -> None:
        runtime = self.make_runtime()
        callback = Mock(name="callback", return_value="ok")

        result = runtime.run_with_lock(callback)

        self.assertEqual(result, "ok")
        runtime.lock.__enter__.assert_called_once_with()
        callback.assert_called_once_with()
        runtime.lock.__exit__.assert_called_once()

    def test_maintenance_lock_helpers_delegate_to_lock(self) -> None:
        runtime = self.make_runtime()
        runtime.maintenance_lock.acquire.return_value = True

        self.assertTrue(runtime.try_acquire_maintenance_lock())
        runtime.release_maintenance_lock()

        runtime.maintenance_lock.acquire.assert_called_once_with(blocking=False)
        runtime.maintenance_lock.release.assert_called_once_with()

    def test_thread_starters_create_daemon_threads(self) -> None:
        threads: list[tuple[dict[str, object], Mock]] = []

        def thread_factory(**kwargs: object) -> Mock:
            thread = Mock()
            threads.append((kwargs, thread))
            return thread

        runtime = self.make_runtime(thread_factory=Mock(side_effect=thread_factory))
        background_target = Mock(name="background_target")
        daemon_target = Mock(name="daemon_target")

        runtime.start_background_thread(background_target)
        runtime.start_daemon_thread(daemon_target, ("node-1",))
        runtime.start_maintenance_thread()

        self.assertEqual(threads[0][0], {"target": background_target, "daemon": True})
        self.assertEqual(threads[1][0], {"target": daemon_target, "args": ("node-1",), "daemon": True})
        self.assertEqual(threads[2][0], {"target": runtime.maintain_valid_nodes, "args": (False,), "daemon": True})
        for _, thread in threads:
            thread.start.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
