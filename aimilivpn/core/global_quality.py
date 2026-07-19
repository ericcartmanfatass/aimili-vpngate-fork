from __future__ import annotations

"""IP-deduplicated Scamalytics batch processing for the global node catalog."""

import json
import os
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from aimilivpn.core.global_storage import GlobalRepository


@dataclass(frozen=True)
class QualityBatchSummary:
    unique_ips: int
    cache_hits: int
    requested: int
    failed: int
    deferred: int

    def to_dict(self) -> dict[str, int]:
        return {
            "unique_ips": self.unique_ips,
            "cache_hits": self.cache_hits,
            "requested": self.requested,
            "failed": self.failed,
            "deferred": self.deferred,
        }


class QualityBatchProcessor:
    """Process each published VPNGate IP once and retain only safe fields.

    ``query`` is injected so the scheduler can use the existing provider while
    tests can exercise cache, deduplication and quota behaviour offline.
    """

    def __init__(
        self,
        cache_path: Path,
        *,
        cache_ttl_seconds: int = 7 * 86400,
        rate_limit_per_minute: int = 30,
        now: Callable[[], float] = time.time,
        repository: GlobalRepository | None = None,
        retry_backoff_seconds: tuple[int, ...] = (300, 900, 1800, 3600),
        daily_quota: int | None = None,
    ) -> None:
        self.cache_path = cache_path
        self.cache_ttl_seconds = max(60, int(cache_ttl_seconds))
        self.rate_limit_per_minute = max(1, int(rate_limit_per_minute))
        self.now = now
        self.repository = repository
        self.retry_backoff_seconds = tuple(max(1, int(value)) for value in retry_backoff_seconds) or (300,)
        self.daily_quota = max(0, int(daily_quota or 0))
        self.metrics_path = self.cache_path.with_name("quality_metrics.json")

    def run(self, nodes: Iterable[dict[str, Any]], query: Callable[[str], MappingLike]) -> QualityBatchSummary:
        unique_ips = []
        seen: set[str] = set()
        for node in nodes:
            ip = str(node.get("server_ip") or node.get("ip") or node.get("remote_host") or "").strip()
            if ip and ip not in seen:
                seen.add(ip)
                unique_ips.append(ip)

        now = self.now()
        if self.repository is not None:
            self.repository.enqueue_quality_ips(unique_ips, now=now)
            cache = self.repository.read_quality()
            queue = {str(item.get("ip")): item for item in self.repository.read_quality_queue() if item.get("ip")}
        else:
            cache = self._read_cache()
            queue = {}
        metrics = self._load_metrics(now)
        cache_hits = requested = failed = deferred = 0
        for ip in unique_ips:
            cached = cache.get(ip)
            if (
                isinstance(cached, dict)
                and str(cached.get("status") or "ok") == "ok"
                and float(cached.get("cache_expires_at") or 0) > now
            ):
                cache_hits += 1
                metrics["cache_hits"] = int(metrics.get("cache_hits") or 0) + 1
                if self.repository is not None:
                    self.repository.remove_quality_queue(ip)
                continue
            queued = queue.get(ip)
            if queued and float(queued.get("next_attempt_at") or 0) > now:
                deferred += 1
                continue
            if requested >= self.rate_limit_per_minute:
                deferred += 1
                metrics["deferred"] = int(metrics.get("deferred") or 0) + 1
                if self.repository is not None:
                    attempts = int(queued.get("attempts") or 0) if queued else 0
                    self.repository.mark_quality_queue(
                        ip,
                        status="pending",
                        attempts=attempts,
                        next_attempt_at=now,
                        now=now,
                    )
                continue
            if self.daily_quota and int(metrics.get("requests") or 0) >= self.daily_quota:
                deferred += 1
                metrics["deferred"] = int(metrics.get("deferred") or 0) + 1
                if self.repository is not None:
                    attempts = int(queued.get("attempts") or 0) if queued else 0
                    self.repository.mark_quality_queue(
                        ip,
                        status="pending",
                        attempts=attempts,
                        next_attempt_at=now + 86400,
                        now=now,
                    )
                continue
            requested += 1
            metrics["requests"] = int(metrics.get("requests") or 0) + 1
            try:
                result = query(ip)
                safe_result = self._safe_result(ip, result, now + self.cache_ttl_seconds)
                metrics["successes"] = int(metrics.get("successes") or 0) + 1
                if self.repository is not None:
                    self.repository.upsert_quality(ip, safe_result)
                    self.repository.remove_quality_queue(ip)
                else:
                    cache[ip] = safe_result
            except Exception as exc:
                failed += 1
                metrics["failures"] = int(metrics.get("failures") or 0) + 1
                failure = {
                    "ip": ip,
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "checked_at": now,
                    "cache_expires_at": now + min(300, self.cache_ttl_seconds),
                }
                if self.repository is not None:
                    attempts = (int(queued.get("attempts") or 0) if queued else 0) + 1
                    retry_index = min(attempts - 1, len(self.retry_backoff_seconds) - 1)
                    self.repository.upsert_quality(ip, failure)
                    self.repository.mark_quality_queue(
                        ip,
                        status="failed",
                        attempts=attempts,
                        next_attempt_at=now + self.retry_backoff_seconds[retry_index],
                        last_error=type(exc).__name__,
                        now=now,
                    )
                else:
                    cache[ip] = failure
        if self.repository is None:
            self._write_cache(cache)
        metrics["remaining"] = max(0, self.daily_quota - int(metrics.get("requests") or 0)) if self.daily_quota else None
        metrics["last_run_at"] = now
        self._write_metrics(metrics)
        return QualityBatchSummary(len(unique_ips), cache_hits, requested, failed, deferred)

    def _load_metrics(self, now: float) -> dict[str, Any]:
        payload = self.repository.read_quality_metrics() if self.repository is not None else self._read_metrics_file()
        today = datetime.fromtimestamp(now, tz=timezone.utc).date().isoformat()
        if payload.get("date") != today or int(payload.get("quota") or 0) != self.daily_quota:
            return {
                "date": today,
                "quota": self.daily_quota,
                "cache_hits": 0,
                "requests": 0,
                "successes": 0,
                "failures": 0,
                "deferred": 0,
                "remaining": self.daily_quota if self.daily_quota else None,
            }
        return dict(payload)

    def _write_metrics(self, metrics: dict[str, Any]) -> None:
        if self.repository is not None:
            self.repository.write_quality_metrics(metrics)
        else:
            self._write_metrics_file(metrics)

    def _read_metrics_file(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.metrics_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _write_metrics_file(self, payload: dict[str, Any]) -> None:
        self.metrics_path.parent.mkdir(parents=True, exist_ok=True)
        fd, raw_tmp = tempfile.mkstemp(prefix=f".{self.metrics_path.name}.", suffix=".tmp", dir=self.metrics_path.parent)
        tmp = Path(raw_tmp)
        try:
            os.close(fd)
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            try:
                tmp.chmod(0o600)
            except OSError:
                pass
            os.replace(tmp, self.metrics_path)
        finally:
            tmp.unlink(missing_ok=True)

    def _safe_result(self, ip: str, result: MappingLike, expires_at: float) -> dict[str, Any]:
        payload = dict(result) if isinstance(result, dict) else {}
        allowed = {
            "risk_score",
            "risk_level",
            "proxy_detected",
            "datacenter_detected",
            "provider",
            "source",
            "country",
            "asn",
        }
        clean = {key: payload[key] for key in allowed if key in payload}
        clean.update({"ip": ip, "status": "ok", "checked_at": self.now(), "cache_expires_at": expires_at})
        return clean

    def _read_cache(self) -> dict[str, dict[str, Any]]:
        try:
            payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _write_cache(self, payload: dict[str, dict[str, Any]]) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        fd, raw_tmp = tempfile.mkstemp(prefix=f".{self.cache_path.name}.", suffix=".tmp", dir=self.cache_path.parent)
        tmp = Path(raw_tmp)
        try:
            os.close(fd)
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            try:
                tmp.chmod(0o600)
            except OSError:
                pass
            os.replace(tmp, self.cache_path)
            try:
                self.cache_path.chmod(0o600)
            except OSError:
                pass
        finally:
            tmp.unlink(missing_ok=True)


MappingLike = dict[str, Any]
