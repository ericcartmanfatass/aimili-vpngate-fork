from __future__ import annotations

import ipaddress
from collections.abc import Iterable
from typing import Any


DEFAULT_TRUSTED_PROXY_ADDRESSES = ("127.0.0.1", "::1")


def _normalized_ip(value: Any) -> str:
    text = str(value or "").strip().strip("[]")
    if not text:
        return ""
    try:
        address = ipaddress.ip_address(text)
    except ValueError:
        return ""
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return str(address.ipv4_mapped)
    return str(address)


def is_loopback_host(value: Any) -> bool:
    text = str(value or "").strip().lower().strip("[]")
    if text == "localhost":
        return True
    normalized = _normalized_ip(text)
    if not normalized:
        return False
    return ipaddress.ip_address(normalized).is_loopback


def parse_trusted_proxy_addresses(value: str | Iterable[Any] | None) -> tuple[str, ...]:
    if value is None:
        items: Iterable[Any] = DEFAULT_TRUSTED_PROXY_ADDRESSES
    elif isinstance(value, str):
        items = value.split(",")
    else:
        items = value

    addresses: list[str] = []
    for item in items:
        normalized = _normalized_ip(item)
        if not normalized or not ipaddress.ip_address(normalized).is_loopback:
            continue
        if normalized not in addresses:
            addresses.append(normalized)
    return tuple(addresses)


def request_uses_trusted_https(
    handler: Any,
    *,
    trust_proxy_headers: bool,
    trusted_proxy_addresses: Iterable[str],
) -> bool:
    if not trust_proxy_headers:
        return False

    client_address = getattr(handler, "client_address", ())
    peer = _normalized_ip(client_address[0] if client_address else "")
    trusted = {_normalized_ip(item) for item in trusted_proxy_addresses}
    trusted.discard("")
    if not peer or peer not in trusted or not is_loopback_host(peer):
        return False

    forwarded_proto = str(getattr(handler, "headers", {}).get("X-Forwarded-Proto", ""))
    return forwarded_proto.split(",", 1)[0].strip().lower() == "https"


def request_client_ip(
    handler: Any,
    *,
    trust_proxy_headers: bool,
    trusted_proxy_addresses: Iterable[str],
) -> str:
    client_address = getattr(handler, "client_address", ())
    peer = _normalized_ip(client_address[0] if client_address else "")
    if not trust_proxy_headers:
        return peer or "unknown"

    trusted = {_normalized_ip(item) for item in trusted_proxy_addresses}
    trusted.discard("")
    if not peer or peer not in trusted or not is_loopback_host(peer):
        return peer or "unknown"

    forwarded_for = str(getattr(handler, "headers", {}).get("X-Forwarded-For", ""))
    forwarded = _normalized_ip(forwarded_for.split(",", 1)[0])
    return forwarded or peer


def secure_cookie_suffix(handler: Any) -> str:
    checker = getattr(handler, "is_secure_request", None)
    return "; Secure" if callable(checker) and checker() else ""


def management_http_notice(label: str, host: str, port: int, *, trust_proxy_headers: bool) -> str:
    if not is_loopback_host(host):
        return (
            f"[安全警告] {label} 正以明文 HTTP 监听非 loopback 地址 {host}:{port}；"
            "请立即改为 127.0.0.1，并仅通过 TLS 反向代理访问。"
        )
    if trust_proxy_headers:
        return (
            f"[安全] {label} 仅在 {host}:{port} 提供本机 HTTP upstream；"
            "仅显式信任的本机 TLS 反向代理可声明 HTTPS。"
        )
    return (
        f"[安全提示] {label} 仅在 {host}:{port} 提供本机明文 HTTP；"
        "如需远程访问，请配置 TLS 反向代理，勿开放该端口。"
    )
