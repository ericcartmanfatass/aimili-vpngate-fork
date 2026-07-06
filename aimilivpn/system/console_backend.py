from __future__ import annotations

import http.client
import json
import os
import subprocess
from typing import Any


def systemctl(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["systemctl"] + args, capture_output=True, text=True, timeout=10)


def service_active(service: str) -> bool:
    try:
        return systemctl(["is-active", "--quiet", service]).returncode == 0
    except Exception:
        return False


def service_action(service: str, action: str) -> dict[str, Any]:
    if action not in {"start", "stop", "restart"}:
        return {"ok": False, "error": "unsupported service action"}
    try:
        res = systemctl([action, service])
        return {
            "ok": res.returncode == 0,
            "stdout": res.stdout,
            "stderr": res.stderr,
            "returncode": res.returncode,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


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
        return {
            "ok": False,
            "status": 502,
            "error": f"backend {inst['id']} unavailable on 127.0.0.1:{inst['ui_port']}: {exc}",
        }
    finally:
        conn.close()
    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        data = {"raw": raw.decode("utf-8", errors="replace")}
    if resp.status >= 400:
        return {"ok": False, "status": resp.status, "error": data}
    return data if isinstance(data, dict) else {"ok": True, "data": data}
