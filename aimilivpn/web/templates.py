from __future__ import annotations

from pathlib import Path


DEFAULT_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


def get_template(name: str, fallback: str, template_dir: Path | None = None) -> str:
    if "/" in name or "\\" in name or name in {"", ".", ".."}:
        raise ValueError(f"invalid template name: {name!r}")

    directory = template_dir or DEFAULT_TEMPLATE_DIR
    path = directory / name
    try:
        if path.is_file():
            return path.read_text(encoding="utf-8")
    except OSError:
        pass
    return fallback


def get_login_html(fallback: str) -> str:
    return get_template("login.html", fallback)


def get_index_html(fallback: str) -> str:
    return get_template("index.html", fallback)


def get_console_login_html(fallback: str) -> str:
    return get_template("console_login.html", fallback)


def get_console_index_html(fallback: str) -> str:
    return get_template("console_index.html", fallback)
