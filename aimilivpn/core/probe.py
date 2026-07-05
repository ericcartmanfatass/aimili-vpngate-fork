from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any, Callable
import concurrent.futures
import uuid


class TestIndexPool:
    def __init__(self, start: int = 2, stop: int = 100) -> None:
        if start >= stop:
            raise ValueError("start must be less than stop")
        self.start = start
        self.stop = stop
        self._active: set[int] = set()
        self._lock = Lock()

    def acquire(self) -> int:
        with self._lock:
            for idx in range(self.start, self.stop):
                if idx not in self._active:
                    self._active.add(idx)
                    return idx
        raise RuntimeError("no free OpenVPN test interface index; please retry later")

    def release(self, idx: int) -> None:
        with self._lock:
            self._active.discard(idx)


def build_test_config_path(
    config_dir: Path,
    node_id: str,
    *,
    safe_name: Callable[[str], str],
    token_factory: Callable[[], str] | None = None,
) -> Path:
    token_factory = token_factory or (lambda: uuid.uuid4().hex)
    return config_dir / f".test_{safe_name(node_id)}_{token_factory()}.ovpn"


@dataclass(frozen=True)
class OpenVPNProbeResult:
    node_id: str
    remote_host: str
    remote_port: int
    latency_ms: int
    ok: bool
    message: str


def select_probe_nodes(
    nodes: list[dict[str, Any]],
    node_ids: list[str],
    *,
    node_matches_allowed: Callable[[dict[str, Any]], bool],
) -> list[dict[str, Any]]:
    wanted = set(node_ids)
    return [node for node in nodes if node.get("id") in wanted and node_matches_allowed(node)]


def probe_result_to_node_patch(
    probe: OpenVPNProbeResult,
    source_node: dict[str, Any],
    *,
    probed_at: float,
) -> dict[str, Any]:
    if not probe.ok and probe.message.startswith("Failed to write configuration:"):
        return unavailable_probe_result(probe.node_id, probe.message, probed_at=probed_at)

    return {
        "id": probe.node_id,
        "ip": source_node.get("ip") or probe.remote_host,
        "remote_host": probe.remote_host,
        "remote_port": probe.remote_port,
        "latency_ms": probe.latency_ms,
        "probe_status": "available" if probe.ok else "unavailable",
        "probe_message": probe.message,
        "probed_at": probed_at,
        "owner": "",
        "asn": "",
        "as_name": "",
        "location": "",
        "ip_type": "",
        "quality": "",
    }


def unavailable_probe_result(node_id: str, message: str, *, probed_at: float | None = None) -> dict[str, Any]:
    result = {
        "id": node_id,
        "probe_status": "unavailable",
        "probe_message": message,
        "latency_ms": 0,
    }
    if probed_at is not None:
        result.update({
            "probed_at": probed_at,
            "owner": "",
            "asn": "",
            "as_name": "",
            "location": "",
            "ip_type": "",
            "quality": "",
        })
    return result


def run_probe_batch(
    nodes: list[dict[str, Any]],
    *,
    probe_node: Callable[[tuple[int, dict[str, Any]]], dict[str, Any]],
    max_workers: int,
) -> dict[str, dict[str, Any]]:
    if not nodes:
        return {}

    updated_nodes: dict[str, dict[str, Any]] = {}
    worker_count = min(max_workers, max(1, len(nodes)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {executor.submit(probe_node, (idx, node)): str(node["id"]) for idx, node in enumerate(nodes)}
        for future in concurrent.futures.as_completed(futures):
            node_id = futures[future]
            try:
                updated_nodes[node_id] = future.result()
            except Exception as exc:
                updated_nodes[node_id] = unavailable_probe_result(node_id, f"Test exception: {exc}")
    return updated_nodes


def execute_openvpn_probe(
    *,
    node_id: str,
    config_text: str,
    remote_host: str,
    remote_port: int,
    fallback_ping: int,
    config_dir: Path,
    safe_name: Callable[[str], str],
    write_config: Callable[[Path, str], None],
    ping_latency: Callable[[str, int, int], int],
    run_openvpn: Callable[..., tuple[bool, str, object]],
    index_pool: TestIndexPool,
    timeout: int,
    raise_write_error: bool = False,
) -> OpenVPNProbeResult:
    temp_path = build_test_config_path(config_dir, node_id, safe_name=safe_name)
    try:
        write_config(temp_path, config_text)
    except Exception as exc:
        if raise_write_error:
            raise RuntimeError(f"Failed to write temp config file: {exc}") from exc
        return OpenVPNProbeResult(
            node_id=node_id,
            remote_host=remote_host,
            remote_port=remote_port,
            latency_ms=0,
            ok=False,
            message=f"Failed to write configuration: {exc}",
        )

    latency = ping_latency(remote_host, remote_port, fallback_ping)
    idx = None
    try:
        idx = index_pool.acquire()
        ok, message, _ = run_openvpn(
            str(temp_path),
            keep_alive=False,
            route_nopull=True,
            timeout=timeout,
            dev=f"tun{idx}",
        )
    finally:
        if idx is not None:
            index_pool.release(idx)
        try:
            if temp_path.exists():
                temp_path.unlink()
        except Exception:
            pass

    return OpenVPNProbeResult(
        node_id=node_id,
        remote_host=remote_host,
        remote_port=remote_port,
        latency_ms=latency,
        ok=ok,
        message=message,
    )


def enrich_available_probe_nodes(
    probe_results: list[dict[str, Any]],
    enrich_ip_info: Callable[[list[dict[str, Any]]], None],
    on_error: Callable[[Exception], None] | None = None,
) -> None:
    available_nodes = [node for node in probe_results if node.get("probe_status") == "available"]
    if not available_nodes:
        return
    try:
        enrich_ip_info(available_nodes)
    except Exception as exc:
        if on_error:
            on_error(exc)


def apply_quality_patches_to_probe_results(
    probe_results: list[dict[str, Any]],
    *,
    record_quality: Callable[[dict[str, Any], bool, int, str], Any],
    quality_to_patch: Callable[[Any], dict[str, Any]],
    parse_int: Callable[[Any], int],
    on_error: Callable[[dict[str, Any], Exception], None] | None = None,
) -> None:
    for result in probe_results:
        try:
            quality = record_quality(
                result,
                result.get("probe_status") == "available",
                parse_int(result.get("latency_ms")),
                str(result.get("probe_message") or ""),
            )
            result.update(quality_to_patch(quality))
        except Exception as exc:
            if on_error:
                on_error(result, exc)


def merge_probe_results_into_nodes(
    nodes: list[dict[str, Any]],
    updated_nodes: dict[str, dict[str, Any]],
    *,
    sort_nodes: Callable[[list[dict[str, Any]]], list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    for node in nodes:
        node_id = node.get("id")
        if node_id in updated_nodes:
            node.update(updated_nodes[node_id])
    return sort_nodes(nodes)
