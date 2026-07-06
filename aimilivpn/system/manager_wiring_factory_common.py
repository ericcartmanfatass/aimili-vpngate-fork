from __future__ import annotations

from typing import Callable, TypeVar

RuntimeT = TypeVar("RuntimeT")


def build_runtime(runtime_cls: Callable[..., RuntimeT], wiring: object) -> RuntimeT:
    return runtime_cls(**vars(wiring))
