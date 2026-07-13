from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from aimilivpn.core.blacklist import blacklist_entry, clean_blacklist
from aimilivpn.core.storage import BlacklistRepository


@dataclass(frozen=True)
class BlacklistStore:
    path: Path
    lock: Any
    backoff_seconds: int
    now: Callable[[], float] = time.time
    repository: BlacklistRepository | None = None

    def _repository(self) -> BlacklistRepository:
        return self.repository or BlacklistRepository(self.path)

    def _read(self) -> dict[str, Any]:
        return self._repository().read_raw_entries()

    def _write(self, entries: dict[str, dict[str, Any]]) -> None:
        self._repository().write_entries(entries)

    def load(self) -> dict[str, dict[str, Any]]:
        current_time = self.now()
        raw = self._read()
        cleaned, changed = clean_blacklist(raw, now=current_time)
        if changed:
            self._write(cleaned)
        return cleaned

    def mark(self, node: dict[str, Any], message: str) -> None:
        node_id = str(node.get("id") or "").strip()
        if not node_id:
            return
        current_time = self.now()
        blacklist = self.load()
        blacklist[node_id] = blacklist_entry(
            node,
            message=message,
            now=current_time,
            backoff_seconds=self.backoff_seconds,
        )
        self._write(blacklist)
