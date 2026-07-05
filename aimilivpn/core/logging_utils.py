from __future__ import annotations

import re

from .security import redact_sensitive_text


def redact_secret(value: str) -> str:
    if not value:
        return value
    if len(value) <= 8:
        return "[REDACTED]"
    return f"{value[:3]}...[REDACTED]...{value[-3:]}"


def redact_log_message(message: str) -> str:
    redacted = redact_sensitive_text(message or "")
    redacted = re.sub(
        r"(?i)(api[_-]?key|session|token|password|password_hash)=([^\s&]+)",
        lambda match: f"{match.group(1)}={redact_secret(match.group(2))}",
        redacted,
    )
    return redacted

