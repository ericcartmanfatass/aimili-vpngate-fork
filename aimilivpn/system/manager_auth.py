from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from aimilivpn.core.auth import generate_session_token, verify_password, verify_username


@dataclass
class ManagerAuthRuntime:
    token_factory: Callable[[], str] = generate_session_token
    password_verifier: Callable[[str, str], bool] = verify_password
    username_verifier: Callable[[str, str], bool] = verify_username

    def generate_session_token(self) -> str:
        return self.token_factory()

    def get_session_token(self, password: str, username: str = "admin") -> str:
        return self.generate_session_token()

    def verify_password(self, password: str, stored_hash: str) -> bool:
        return self.password_verifier(password, stored_hash)

    def verify_username(self, username: str, expected_username: str) -> bool:
        return self.username_verifier(username, expected_username)
