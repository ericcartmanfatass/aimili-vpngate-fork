from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from aimilivpn.core.blacklist import blacklist_entry, clean_blacklist
from aimilivpn.system.state_store import read_json_file, write_json_file


@dataclass(frozen=True)
class BlacklistStore:
    path: Path
    lock: Any
    backoff_seconds: int
    now: Callable[[], float] = time.time

    def load(self) -> dict[str, dict[str, Any]]:
        current_time = self.now()
        raw = read_json_file(self.path, {}, self.lock)
        cleaned, changed = clean_blacklist(raw, now=current_time)
        if changed:
            write_json_file(self.path, cleaned, self.lock)
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
        write_json_file(self.path, blacklist, self.lock)
