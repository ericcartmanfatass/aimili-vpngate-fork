from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from aimilivpn.core.auth import generate_password
from aimilivpn.system.ui_config import UiConfigStore, generate_username


@dataclass
class ManagerUiRuntime:
    data_dir: Callable[[], Path]
    lock: Any
    ui_host: Callable[[], str]
    ui_port: Callable[[], int]
    proxy_port: Callable[[], int]
    bounded_int: Callable[[Any, int, int, int], int]
    password_factory: Callable[[], str] = generate_password
    username_factory: Callable[[], str] = generate_username

    def generate_random_password(self) -> str:
        return self.password_factory()

    def generate_random_username(self) -> str:
        return self.username_factory()

    def store(self) -> UiConfigStore:
        return UiConfigStore(
            data_dir=self.data_dir(),
            lock=self.lock,
            ui_host=self.ui_host(),
            ui_port=self.ui_port(),
            proxy_port=self.proxy_port(),
            bounded_int=self.bounded_int,
            password_factory=self.generate_random_password,
            username_factory=self.generate_random_username,
        )

    def load(self) -> dict[str, Any]:
        return self.store().load()

    def save(self, config: dict[str, Any]) -> None:
        self.store().save(config)
