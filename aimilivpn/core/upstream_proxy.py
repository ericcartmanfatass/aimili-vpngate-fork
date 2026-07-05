from __future__ import annotations

import base64
import socket
import ssl
import urllib.parse
from typing import Callable

ProxyAuthProvider = Callable[[], tuple[str | None, str | None]]


def proxy_basic_auth_header(username: str, password: str) -> str:
    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    return f"Proxy-Authorization: Basic {token}\r\n"


def recv_exact(sock: socket.socket, size: int) -> bytes:
    data = b""
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise RuntimeError("Unexpected EOF while reading proxy response")
        data += chunk
    return data


def read_http_response_head(sock: socket.socket, limit: int = 65536) -> bytes:
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = sock.recv(4096)
        if not chunk:
            break
        data += chunk
        if len(data) > limit:
            raise RuntimeError("Proxy response header too large")
    if b"\r\n\r\n" not in data:
        raise RuntimeError("Incomplete HTTP proxy response header")
    return data


def socks5_address_bytes(host: str) -> tuple[int, bytes]:
    try:
        return 1, socket.inet_aton(host)
    except OSError:
        pass
    try:
        return 4, socket.inet_pton(socket.AF_INET6, host)
    except OSError:
        pass
    host_bytes = host.encode("idna")
    if len(host_bytes) > 255:
        raise RuntimeError("SOCKS5 target host name is too long")
    return 3, bytes([len(host_bytes)]) + host_bytes


def read_socks5_connect_reply(sock: socket.socket) -> None:
    header = recv_exact(sock, 4)
    if header[0] != 5:
        raise RuntimeError("Invalid SOCKS5 reply version")
    address_type = header[3]
    if address_type == 1:
        recv_exact(sock, 4)
    elif address_type == 3:
        domain_len = recv_exact(sock, 1)[0]
        recv_exact(sock, domain_len)
    elif address_type == 4:
        recv_exact(sock, 16)
    else:
        raise RuntimeError(f"Invalid SOCKS5 reply address type: {address_type}")
    recv_exact(sock, 2)
    if header[1] != 0:
        raise RuntimeError(f"SOCKS5 connection request rejected, code={header[1]}")


def format_host_port(host: str, port: int) -> str:
    return f"[{host}]:{port}" if ":" in host and not host.startswith("[") else f"{host}:{port}"


def decode_http_body(response_data: bytes) -> str:
    header_end = response_data.find(b"\r\n\r\n")
    if header_end == -1:
        raise RuntimeError("Invalid HTTP response format")

    headers_part = response_data[:header_end].decode("utf-8", errors="replace")
    body_part = response_data[header_end + 4:]

    lines = headers_part.splitlines()
    if not lines:
        raise RuntimeError("Empty response headers")
    status_line = lines[0]
    status_parts = status_line.split()
    if len(status_parts) >= 2:
        try:
            status_code = int(status_parts[1])
            if status_code != 200:
                raise RuntimeError(f"HTTP Server returned status {status_code}: {status_line}")
        except ValueError:
            pass

    is_chunked = any(
        key.strip().lower() == "transfer-encoding" and "chunked" in value.lower()
        for line in lines[1:]
        if ":" in line
        for key, value in [line.split(":", 1)]
    )
    if is_chunked:
        body_part = decode_chunked_body(body_part)

    return body_part.decode("utf-8", errors="replace")


def decode_chunked_body(body: bytes) -> bytes:
    decoded = b""
    idx = 0
    while idx < len(body):
        chunk_header_end = body.find(b"\r\n", idx)
        if chunk_header_end == -1:
            break
        chunk_size_text = body[idx:chunk_header_end].split(b";")[0].strip()
        try:
            chunk_size = int(chunk_size_text, 16)
        except ValueError:
            break
        if chunk_size == 0:
            break
        idx = chunk_header_end + 2
        decoded += body[idx : idx + chunk_size]
        idx += chunk_size + 2
    return decoded


def fetch_text_via_proxy(
    url: str,
    proxy_type: str,
    proxy_host: str,
    proxy_port: int,
    *,
    proxy_auth: ProxyAuthProvider,
    use_ssl_verify: bool = True,
    socket_factory: Callable[[int, int], socket.socket] = socket.socket,
) -> str:
    parsed = urllib.parse.urlsplit(url)
    domain = parsed.hostname or "www.vpngate.net"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    is_https = parsed.scheme == "https"
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query

    sock: socket.socket | None = None
    try:
        family = socket.AF_INET6 if ":" in proxy_host else socket.AF_INET
        sock = socket_factory(family, socket.SOCK_STREAM)
        sock.settimeout(12)
        sock.connect((proxy_host, proxy_port))
        proxy_user, proxy_pass = proxy_auth()

        if proxy_type == "socks":
            _establish_socks5_tunnel(sock, domain, port, proxy_user, proxy_pass)
            if is_https:
                ctx = ssl.create_default_context() if use_ssl_verify else ssl._create_unverified_context()
                sock = ctx.wrap_socket(sock, server_hostname=domain)
        else:
            if is_https:
                _establish_http_connect_tunnel(sock, domain, port, proxy_user, proxy_pass)
                ctx = ssl.create_default_context() if use_ssl_verify else ssl._create_unverified_context()
                sock = ctx.wrap_socket(sock, server_hostname=domain)

        request_uri = url if proxy_type == "http" and not is_https else path
        auth_header = (
            proxy_basic_auth_header(proxy_user, proxy_pass or "")
            if proxy_type == "http" and not is_https and proxy_user is not None
            else ""
        )
        request = (
            f"GET {request_uri} HTTP/1.1\r\n"
            f"Host: {domain}\r\n"
            f"User-Agent: Mozilla/5.0 vpngate-openvpn-manager/2.0\r\n"
            f"Accept: text/plain,*/*\r\n"
            f"{auth_header}"
            f"Connection: close\r\n\r\n"
        )
        sock.sendall(request.encode("utf-8"))
        return decode_http_body(_read_response(sock))
    finally:
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass


def _establish_socks5_tunnel(
    sock: socket.socket,
    domain: str,
    port: int,
    proxy_user: str | None,
    proxy_pass: str | None,
) -> None:
    sock.sendall(b"\x05\x02\x00\x02" if proxy_user is not None else b"\x05\x01\x00")
    response = recv_exact(sock, 2)
    if len(response) < 2 or response[0] != 5:
        raise RuntimeError("SOCKS5 authentication failed or unsupported")
    if response[1] == 2:
        if proxy_user is None:
            raise RuntimeError("SOCKS5 proxy requires username/password authentication")
        user_bytes = proxy_user.encode("utf-8")
        pass_bytes = (proxy_pass or "").encode("utf-8")
        if len(user_bytes) > 255 or len(pass_bytes) > 255:
            raise RuntimeError("SOCKS5 proxy credentials are too long")
        sock.sendall(b"\x01" + bytes([len(user_bytes)]) + user_bytes + bytes([len(pass_bytes)]) + pass_bytes)
        auth_response = recv_exact(sock, 2)
        if len(auth_response) < 2 or auth_response[1] != 0:
            raise RuntimeError("SOCKS5 username/password authentication failed")
    elif response[1] != 0:
        raise RuntimeError("SOCKS5 authentication method unsupported")

    address_type, address_bytes = socks5_address_bytes(domain)
    sock.sendall(b"\x05\x01\x00" + bytes([address_type]) + address_bytes + port.to_bytes(2, "big"))
    read_socks5_connect_reply(sock)


def _establish_http_connect_tunnel(
    sock: socket.socket,
    domain: str,
    port: int,
    proxy_user: str | None,
    proxy_pass: str | None,
) -> None:
    authority = format_host_port(domain, port)
    auth_header = proxy_basic_auth_header(proxy_user, proxy_pass or "") if proxy_user is not None else ""
    request = (
        f"CONNECT {authority} HTTP/1.1\r\n"
        f"Host: {authority}\r\n"
        f"User-Agent: Mozilla/5.0 vpngate-openvpn-manager/2.0\r\n"
        f"{auth_header}"
        f"Proxy-Connection: Keep-Alive\r\n\r\n"
    )
    sock.sendall(request.encode("ascii"))
    response = read_http_response_head(sock)
    status_line = response.split(b"\r\n", 1)[0].decode("utf-8", errors="replace")
    status_parts = status_line.split()
    status_code = int(status_parts[1]) if len(status_parts) >= 2 and status_parts[1].isdigit() else 0
    if status_code != 200:
        raise RuntimeError(f"HTTP CONNECT tunnel failed: {status_line}")


def _read_response(sock: socket.socket, limit: int = 10 * 1024 * 1024) -> bytes:
    response_data = b""
    while True:
        chunk = sock.recv(4096)
        if not chunk:
            break
        response_data += chunk
        if len(response_data) > limit:
            break
    return response_data
