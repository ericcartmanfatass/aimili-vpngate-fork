from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class RuntimePaths:
    root_dir: Path
    data_dir: Path
    config_dir: Path
    nodes_file: Path
    state_file: Path
    auth_file: Path
    upstream_proxy_auth_file: Path
    blacklist_file: Path
    regions_file: Path
    quality_results_file: Path
    settings_file: Path


def build_runtime_paths(root_dir: Path, data_dir: str | None = None) -> RuntimePaths:
    resolved_root = root_dir.resolve()
    normalized_data_dir = data_dir.strip() if data_dir else ""
    resolved_data_dir = Path(normalized_data_dir).resolve() if normalized_data_dir else resolved_root / "vpngate_data"
    return RuntimePaths(
        root_dir=resolved_root,
        data_dir=resolved_data_dir,
        config_dir=resolved_data_dir / "configs",
        nodes_file=resolved_data_dir / "nodes.json",
        state_file=resolved_data_dir / "state.json",
        auth_file=resolved_data_dir / "vpngate_auth.txt",
        upstream_proxy_auth_file=resolved_data_dir / "upstream_proxy_auth.txt",
        blacklist_file=resolved_data_dir / "blacklist.json",
        regions_file=resolved_data_dir / "regions.json",
        quality_results_file=resolved_data_dir / "quality_results.json",
        settings_file=resolved_data_dir / "settings.json",
    )


def ensure_runtime_dirs(paths: RuntimePaths, auth_user: str, auth_pass: str) -> None:
    paths.data_dir.mkdir(exist_ok=True, parents=True)
    paths.config_dir.mkdir(exist_ok=True, parents=True)
    if not paths.auth_file.exists():
        paths.auth_file.write_text(f"{auth_user}\n{auth_pass}\n", encoding="utf-8")
        _chmod_private(paths.auth_file)


def write_upstream_proxy_auth_file(
    paths: RuntimePaths,
    get_upstream_proxy_auth: Callable[[], tuple[str | None, str | None]],
    print_line: Callable[[str], None],
) -> str | None:
    username, password = get_upstream_proxy_auth()
    if username is None:
        return None
    try:
        paths.data_dir.mkdir(exist_ok=True, parents=True)
        paths.upstream_proxy_auth_file.write_text(f"{username}\n{password or ''}\n", encoding="utf-8")
        _chmod_private(paths.upstream_proxy_auth_file)
        return str(paths.upstream_proxy_auth_file)
    except Exception as exc:
        print_line(f"[上游代理认证] 写入认证文件失败: {exc}")
        return None


def _chmod_private(path: Path) -> None:
    try:
        path.chmod(0o600)
    except OSError:
        pass
