#!/usr/bin/env python3
from __future__ import annotations

import threading
from http.server import ThreadingHTTPServer

from aimilivpn.system.console_backend import (
    backend_request,
    service_action,
    service_active,
    systemctl,
)
from aimilivpn.system.console_config import (
    AUTH_FILE,
    CONFIG_DIR,
    CONSOLE_HOST,
    CONSOLE_PORT,
    INSTALL_DIR,
    INSTANCES_FILE,
    MAX_REQUEST_THREADS,
    load_console_auth,
    random_token,
    read_json,
    write_json,
    TRUST_PROXY_HEADERS,
)
from aimilivpn.system.console_instances import (
    instance_by_id,
    load_instances,
    normalize_instance,
    parse_env_file,
    read_logs,
)
from aimilivpn.system.console_routes import (
    INDEX_HTML,
    LOGIN_HTML,
    Handler,
    global_console_runtime,
    instance_state,
    sessions,
    stripped_nodes,
)
from aimilivpn.web.proxy_trust import management_http_notice


class BoundedThreadingHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False

    def __init__(
        self,
        server_address: tuple[str, int],
        request_handler_class: type[Handler],
        *,
        max_request_threads: int = MAX_REQUEST_THREADS,
    ) -> None:
        self._request_slots = threading.BoundedSemaphore(max_request_threads)
        super().__init__(server_address, request_handler_class)

    def process_request(self, request: object, client_address: tuple[str, int]) -> None:
        if not self._request_slots.acquire(blocking=False):
            try:
                request.sendall(  # type: ignore[attr-defined]
                    b"HTTP/1.1 503 Service Unavailable\r\n"
                    b"Connection: close\r\nContent-Length: 0\r\n\r\n"
                )
            except OSError:
                pass
            self.shutdown_request(request)  # type: ignore[arg-type]
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self._request_slots.release()
            raise

    def process_request_thread(self, request: object, client_address: tuple[str, int]) -> None:
        try:
            super().process_request_thread(request, client_address)  # type: ignore[arg-type]
        finally:
            self._request_slots.release()


def main() -> None:
    auth = load_console_auth()
    host = str(auth.get("host") or CONSOLE_HOST)
    port = int(auth.get("port") or CONSOLE_PORT)
    print(f"AimiliVPN Console 已监听 {host}:{port}；安全路径已隐藏", flush=True)
    print(
        management_http_notice(
            "Console",
            host,
            port,
            trust_proxy_headers=TRUST_PROXY_HEADERS,
        ),
        flush=True,
    )
    global_runtime = global_console_runtime()
    global_runtime.start()
    try:
        BoundedThreadingHTTPServer((host, port), Handler).serve_forever()
    finally:
        global_runtime.stop()


if __name__ == "__main__":
    main()
