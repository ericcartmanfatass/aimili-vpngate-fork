from __future__ import annotations

import mimetypes
from pathlib import Path


DEFAULT_STATIC_DIR = Path(__file__).resolve().parent / "static"


def is_safe_static_path(path: str) -> bool:
    if not path or path.startswith(("/", "\\")):
        return False
    candidate = Path(path)
    if candidate.is_absolute():
        return False
    return all(part not in {"", ".", ".."} for part in candidate.parts)


def guess_content_type(path: str) -> str:
    suffix = Path(path).suffix.lower()
    explicit = {
        ".css": "text/css; charset=utf-8",
        ".js": "application/javascript; charset=utf-8",
        ".json": "application/json; charset=utf-8",
        ".svg": "image/svg+xml",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".ico": "image/x-icon",
    }
    if suffix in explicit:
        return explicit[suffix]
    guessed, _ = mimetypes.guess_type(path)
    return guessed or "application/octet-stream"


def get_static_asset(path: str, fallback: bytes | None = None, static_dir: Path | None = None) -> bytes | None:
    if not is_safe_static_path(path):
        raise ValueError(f"invalid static asset path: {path!r}")

    root = static_dir or DEFAULT_STATIC_DIR
    candidate = (root / path).resolve()
    root_resolved = root.resolve()
    if root_resolved != candidate and root_resolved not in candidate.parents:
        raise ValueError(f"static asset path escapes root: {path!r}")

    try:
        if candidate.is_file():
            return candidate.read_bytes()
    except OSError:
        pass
    return fallback

