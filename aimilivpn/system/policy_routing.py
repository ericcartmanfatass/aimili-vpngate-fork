from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

from aimilivpn.core import routing as routing_core


@dataclass
class PolicyRoutingFacade:
    run_command: Callable[..., object] = routing_core.run_command
    sleep: Callable[[float], None] = time.sleep
    print_line: Callable[[str], None] = print
    log_line: Callable[[str, str], None] | None = None

    def setup(self, interface: str, table: str) -> None:
        for command in routing_core.cleanup_route_commands(table):
            try:
                self.run_command(command, capture_output=True, timeout=2)
            except Exception:
                pass

        success = False
        last_error: BaseException | None = None
        for attempt in range(1, 4):
            try:
                for command in routing_core.policy_route_commands(interface, table):
                    self.run_command(command, check=True, timeout=2, capture_output=True)
                for command in routing_core.rp_filter_commands(interface):
                    try:
                        self.run_command(command, capture_output=True, timeout=2)
                    except Exception:
                        pass
                self.print_line(
                    f"[policy_routing] Enabled policy routing for interface {interface} "
                    f"table {table} (attempt {attempt} success)"
                )
                success = True
                break
            except Exception as exc:
                last_error = exc
                kind = routing_core.classify_route_error(exc)
                self.print_line(f"[policy_routing] Attempt {attempt} failed to enable policy routing ({kind}): {exc}")
                self.sleep(1)

        if not success:
            error = routing_core.format_route_error(last_error, table=table)
            self.print_line(f"[??????] [???? 3003] {error}")
            if self.log_line:
                self.log_line("ERROR", f"[???? 3003] {error}")

    def cleanup(self, table: str) -> None:
        try:
            for command in routing_core.cleanup_route_commands(table):
                self.run_command(command, capture_output=True, timeout=2)
            self.print_line(f"[policy_routing] Cleared policy routing table {table}")
        except Exception:
            pass
