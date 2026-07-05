from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from aimilivpn.core.models import QualityResult, VpnNode


class QualityProvider(ABC):
    name: str

    @abstractmethod
    def check_node(self, node: VpnNode | dict[str, Any]) -> QualityResult:
        raise NotImplementedError

    def check_ip(self, ip: str) -> QualityResult:
        raise NotImplementedError(f"{self.name} does not support raw IP checks")
