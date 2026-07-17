from __future__ import annotations

import http.client
import json
import os
import re
import subprocess
from typing import Any


MANAGED_SERVICE_PATTERN = re.compile(r"^aimilivpn@([a-z0-9][a-z0-9_-]{0,31})\.service$")


def is_managed_service(service: str, instance_id: str | None = None) -> bool:
    match = MANAGED_SERVICE_PATTERN.fullmatch(str(service or ""))
    return bool(match and (instance_id is None or match.group(1) == instance_id.lower()))


def systemctl(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["systemctl"] + args, capture_output=True, text=True, timeout=10)


def service_active(service: str) -> bool:
    if not is_managed_service(service):
        return False
    try:
        return systemctl(["is-active", "--quiet", service]).returncode == 0
    except Exception:
        return False


def service_action(service: str, action: str, *, instance_id: str | None = None) -> dict[str, Any]:
    if action not in {"start", "stop", "restart"}:
        return {"ok": False, "error": "unsupported service action"}
    if not is_managed_service(service, instance_id):
        print("[console audit] rejected unmanaged service operation", flush=True)
        return {"ok": False, "error": "service operation rejected"}
    try:
        res = systemctl([action, service])
        if res.returncode == 0:
            return {"ok": True, "returncode": 0}
        print(f"[console audit] 服务操作失败，返回码 {res.returncode}", flush=True)
        return {"ok": False, "error": "服务操作失败", "returncode": res.returncode}
    except Exception as exc:
        print(f"[console audit] service operation raised {type(exc).__name__}", flush=True)
        return {"ok": False, "error": "服务操作失败"}


def backend_request(
    inst: dict[str, Any],
    api_path: str,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    token = os.environ.get("INSTANCE_API_TOKEN", "")
    body = None
    headers = {"X-Aimili-Console-Token": token}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    conn = http.client.HTTPConnection("127.0.0.1", int(inst["ui_port"]), timeout=12)
    try:
        conn.request(method, api_path, body=body, headers=headers)
        resp = conn.getresponse()
        raw = resp.read()
    except Exception as exc:
        print(
            f"[console audit] backend request failed for managed instance: {type(exc).__name__}",
            flush=True,
        )
        return {"ok": False, "status": 502, "error": "backend unavailable"}
    finally:
        conn.close()
    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        data = {"raw": raw.decode("utf-8", errors="replace")}
    if resp.status >= 400:
        return {"ok": False, "status": resp.status, "error": data}
    return data if isinstance(data, dict) else {"ok": True, "data": data}
