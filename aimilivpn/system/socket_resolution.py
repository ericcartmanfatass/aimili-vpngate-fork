from __future__ import annotations

import socket
from typing import Any, Callable


def install_ipv4_preferred_getaddrinfo(socket_module: Any = socket) -> Callable[..., Any]:
    original_getaddrinfo = socket_module.getaddrinfo

    def ipv4_preferred_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        if family == 0:
            if isinstance(host, str) and ":" in host:
                return original_getaddrinfo(host, port, socket_module.AF_INET6, type, proto, flags)
            try:
                results = original_getaddrinfo(host, port, socket_module.AF_INET, type, proto, flags)
                if results:
                    return results
            except socket_module.gaierror:
                pass
            return original_getaddrinfo(host, port, 0, type, proto, flags)
        return original_getaddrinfo(host, port, family, type, proto, flags)

    socket_module.getaddrinfo = ipv4_preferred_getaddrinfo
    return original_getaddrinfo
