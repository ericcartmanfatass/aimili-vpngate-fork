from __future__ import annotations

import random
import socket
from typing import Any

from aimilivpn.system.proxy_config import bind_device_bytes, bind_device_name


def dns_server_address(dns_server: str) -> tuple[int, tuple[Any, ...]]:
    server = dns_server.strip()
    if server.startswith("[") and server.endswith("]"):
        server = server[1:-1]
    if ":" in server:
        return socket.AF_INET6, (server, 53, 0, 0)
    return socket.AF_INET, (server, 53)


def dns_query_over_tun0(host: str, qtype: int, dns_server: str, timeout: float) -> str | None:
    sock = None
    try:
        tx_id = random.getrandbits(16).to_bytes(2, "big")
        flags = b"\x01\x00"
        questions = b"\x00\x01"
        rrs = b"\x00\x00\x00\x00\x00\x00"

        qname = b""
        for part in host.split("."):
            if not part:
                continue
            part_bytes = part.encode("idna")
            if len(part_bytes) > 63:
                return None
            qname += len(part_bytes).to_bytes(1, "big") + part_bytes
        qname += b"\x00"

        qtype_qclass = qtype.to_bytes(2, "big") + b"\x00\x01"
        packet = tx_id + flags + questions + rrs + qname + qtype_qclass

        family, server_address = dns_server_address(dns_server)
        sock = socket.socket(family, socket.SOCK_DGRAM)
        sock.settimeout(timeout)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, bind_device_bytes())
        except OSError as e:
            if "operation not permitted" in str(e).lower() or e.errno == 1:
                print(
                    f"[DNS 绑定失败] [ERR_PROXY_BIND_TUN_PERM_DENIED] 无法绑定到 {bind_device_name()}：需要 root 或 CAP_NET_RAW 权限。",
                    flush=True,
                )
            elif "no such device" in str(e).lower() or e.errno == 19:
                print(
                    f"[DNS 绑定失败] [ERR_ROUTE_DEV_NOT_FOUND] DNS 无法绑定到 {bind_device_name()}：未找到网络设备。",
                    flush=True,
                )
            return None
        sock.sendto(packet, server_address)
        resp, _ = sock.recvfrom(4096)
    except Exception:
        return None
    finally:
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass

    try:
        if len(resp) < 12 or resp[:2] != tx_id:
            return None
        rcode = resp[3] & 0x0F
        if rcode != 0:
            return None

        offset = 12
        while offset < len(resp):
            length = resp[offset]
            if length == 0:
                offset += 1
                break
            if (length & 0xC0) == 0xC0:
                offset += 2
                break
            offset += 1 + length

        offset += 4
        answers_count = int.from_bytes(resp[6:8], "big")
        for _ in range(answers_count):
            if offset >= len(resp):
                break
            while offset < len(resp):
                length = resp[offset]
                if length == 0:
                    offset += 1
                    break
                if (length & 0xC0) == 0xC0:
                    offset += 2
                    break
                offset += 1 + length
            if offset + 10 > len(resp):
                break
            atype = int.from_bytes(resp[offset : offset + 2], "big")
            aclass = int.from_bytes(resp[offset + 2 : offset + 4], "big")
            rdlength = int.from_bytes(resp[offset + 8 : offset + 10], "big")
            offset += 10
            if offset + rdlength > len(resp):
                break
            record = resp[offset : offset + rdlength]
            if atype == qtype and aclass == 1:
                if qtype == 1 and rdlength == 4:
                    return socket.inet_ntoa(record)
                if qtype == 28 and rdlength == 16:
                    return socket.inet_ntop(socket.AF_INET6, record)
            offset += rdlength
    except Exception:
        return None
    return None


def resolve_dns_over_tun0(host: str, dns_server: str = "8.8.8.8", timeout: float = 3.0) -> str | None:
    try:
        socket.inet_aton(host)
        return host
    except OSError:
        pass
    try:
        socket.inet_pton(socket.AF_INET6, host)
        return host
    except OSError:
        pass
    return dns_query_over_tun0(host, 1, dns_server, timeout) or dns_query_over_tun0(host, 28, dns_server, timeout)


def create_connection(address: tuple[str, int], timeout: float = 20) -> socket.socket:
    host, port = address
    resolved_ip = resolve_dns_over_tun0(host)
    if resolved_ip:
        host = resolved_ip

    err = None
    for res in socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM):
        af, socktype, proto, canonname, sa = res
        sock = None
        try:
            sock = socket.socket(af, socktype, proto)
            sock.settimeout(timeout)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, bind_device_bytes())
            sock.connect(sa)
            return sock
        except OSError as e:
            err = e
            if "operation not permitted" in str(e).lower() or e.errno == 1:
                err = OSError(
                    f"[ERR_PROXY_BIND_TUN_PERM_DENIED] 无法绑定到虚拟接口 {bind_device_name()}：需要 root 或 CAP_NET_RAW 权限。"
                )
            elif "no such device" in str(e).lower() or e.errno == 19:
                err = OSError(
                    f"[ERR_ROUTE_DEV_NOT_FOUND] 无法绑定虚拟接口 {bind_device_name()}：未找到设备。"
                )
            if sock is not None:
                sock.close()
    if err is not None:
        raise err
    raise OSError("getaddrinfo returns empty list")
