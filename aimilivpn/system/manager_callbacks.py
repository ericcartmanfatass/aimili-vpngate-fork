from __future__ import annotations

import os
import sys
from typing import Any, Callable


def print_line(message: str) -> None:
    print(message, flush=True)


def module_log_writer(
    log_to_json: Callable[[str, str, str], None],
    module: str,
) -> Callable[[str, str], None]:
    def write(level: str, message: str) -> None:
        log_to_json(level, module, message)

    return write


def diagnose_with_host_keyword(
    diagnose: Callable[..., tuple[bool, str] | None],
) -> Callable[[int, str], tuple[bool, str] | None]:
    def run(port: int, host: str) -> tuple[bool, str] | None:
        return diagnose(port, host=host)

    return run


def is_linux() -> bool:
    return sys.platform.startswith("linux")


def console_token() -> str:
    return os.environ.get("INSTANCE_API_TOKEN", "")


def set_stdout(stream: Any) -> None:
    setattr(sys, "stdout", stream)


def set_stderr(stream: Any) -> None:
    setattr(sys, "stderr", stream)


def exit_process(code: int) -> None:
    os._exit(code)
