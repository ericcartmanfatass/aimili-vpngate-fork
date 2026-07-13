#!/usr/bin/env python3
from __future__ import annotations

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
    instance_state,
    sessions,
    stripped_nodes,
)
from aimilivpn.web.proxy_trust import management_http_notice


def main() -> None:
    auth = load_console_auth()
    host = str(auth.get("host") or CONSOLE_HOST)
    port = int(auth.get("port") or CONSOLE_PORT)
    print(f"AimiliVPN console listening on {host}:{port}; secret path hidden", flush=True)
    print(
        management_http_notice(
            "Console",
            host,
            port,
            trust_proxy_headers=TRUST_PROXY_HEADERS,
        ),
        flush=True,
    )
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
