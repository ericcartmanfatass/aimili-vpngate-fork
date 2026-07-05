from __future__ import annotations

import hashlib
import hmac
import secrets
import string
from datetime import datetime, timezone
from typing import Any, Callable


HASH_SCHEME = "pbkdf2_sha256"
DEFAULT_ITERATIONS = 260_000


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def generate_password(length: int = 24) -> str:
    if length < 12:
        raise ValueError("password length must be at least 12")
    alphabet = string.ascii_letters + string.digits
    while True:
        password = "".join(secrets.choice(alphabet) for _ in range(length))
        if (
            any(ch.islower() for ch in password)
            and any(ch.isupper() for ch in password)
            and any(ch.isdigit() for ch in password)
        ):
            return password


def generate_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_password(password: str, iterations: int = DEFAULT_ITERATIONS) -> str:
    if not password:
        raise ValueError("password must not be empty")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"{HASH_SCHEME}${iterations}${salt.hex()}${digest.hex()}"


def _parse_hash(stored_hash: str) -> tuple[int, bytes, bytes] | None:
    parts = stored_hash.split("$")
    if len(parts) != 4 or parts[0] != HASH_SCHEME:
        return None
    try:
        iterations = int(parts[1])
        salt = bytes.fromhex(parts[2])
        expected = bytes.fromhex(parts[3])
    except (TypeError, ValueError):
        return None
    if iterations <= 0 or not salt or not expected:
        return None
    return iterations, salt, expected


def is_password_hash(value: str | None) -> bool:
    return bool(value and _parse_hash(value) is not None)


def verify_password(password: str, stored_hash: str) -> bool:
    parsed = _parse_hash(stored_hash)
    if parsed is None:
        return hmac.compare_digest(password or "", stored_hash or "")
    iterations, salt, expected = parsed
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(digest, expected)


def migrate_auth_config(
    config: dict[str, Any],
    *,
    password_factory: Callable[[], str] | None = None,
) -> tuple[dict[str, Any], bool, str | None]:
    """Convert legacy auth config with a plaintext password to password_hash."""
    migrated = dict(config)
    changed = False
    generated_password: str | None = None

    plaintext = str(migrated.get("password") or "")
    password_hash = str(migrated.get("password_hash") or "")

    if plaintext and not is_password_hash(password_hash):
        migrated["password_hash"] = hash_password(plaintext)
        migrated.pop("password", None)
        changed = True
    elif not plaintext and not is_password_hash(password_hash):
        password_factory = password_factory or generate_password
        generated_password = password_factory()
        migrated["password_hash"] = hash_password(generated_password)
        migrated.pop("password", None)
        changed = True
    elif "password" in migrated:
        migrated.pop("password", None)
        changed = True

    now = utc_now_iso()
    if changed and not migrated.get("created_at"):
        migrated["created_at"] = now
    if changed:
        migrated["updated_at"] = now

    return migrated, changed, generated_password


def verify_username(username: str, expected_username: str) -> bool:
    return hmac.compare_digest(username or "", expected_username or "")

