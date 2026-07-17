from __future__ import annotations

import socket
import threading

import vpn_utils
from aimilivpn.system.proxy_config import (
    MAX_PROXY_CONNECTIONS,
    bind_device_name,
    proxy_connection_sem,
    set_bind_device,
)
from aimilivpn.system.proxy_protocol import proxy_client


def start_proxy_server(
    host: str,
    port: int,
    bind_dev: str = "tun0",
    *,
    stop_event: threading.Event | None = None,
) -> None:
    shutdown = stop_event or threading.Event()
    set_bind_device(bind_dev)
    is_ipv6 = ":" in host or host == ""
    af = socket.AF_INET6 if is_ipv6 else socket.AF_INET
    server = None
    try:
        server = socket.socket(af, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if is_ipv6:
            try:
                server.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
            except OSError:
                pass
        server.bind((host, port))
        server.listen(256)
        server.settimeout(1.0)
        print(f"HTTP/SOCKS5 代理已监听 {host}:{port}（绑定设备: {bind_device_name()}）", flush=True)
    except Exception as e:
        if server is not None:
            try:
                server.close()
            except Exception:
                pass
        if is_ipv6 and host in ("::", ""):
            print(f"[警告] IPv6 绑定 {host}:{port} 失败（{e}），正在回退到 IPv4 0.0.0.0 ...", flush=True)
            try:
                server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                server.bind(("0.0.0.0", port))
                server.listen(256)
                server.settimeout(1.0)
                print(f"HTTP/SOCKS5 代理已监听 0.0.0.0:{port}（IPv4 回退）", flush=True)
            except Exception as ex:
                diag = vpn_utils.diagnose_local_obstructions(port, host="0.0.0.0")
                diag_msg = diag[1] if diag else str(ex)
                print(f"[错误] 无法在 0.0.0.0:{port} 启动 HTTP/SOCKS5 代理: {diag_msg}", flush=True)
                return
        elif is_ipv6 and host == "::1":
            print(f"[警告] IPv6 绑定 {host}:{port} 失败（{e}），正在回退到 IPv4 127.0.0.1 ...", flush=True)
            try:
                server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                server.bind(("127.0.0.1", port))
                server.listen(256)
                server.settimeout(1.0)
                print(f"HTTP/SOCKS5 代理已监听 127.0.0.1:{port}（IPv4 回退）", flush=True)
            except Exception as ex:
                diag = vpn_utils.diagnose_local_obstructions(port, host="127.0.0.1")
                diag_msg = diag[1] if diag else str(ex)
                print(f"[错误] 无法在 127.0.0.1:{port} 启动 HTTP/SOCKS5 代理: {diag_msg}", flush=True)
                return
        else:
            diag = vpn_utils.diagnose_local_obstructions(port, host=host)
            diag_msg = diag[1] if diag else str(e)
            print(f"[错误] 无法在 {host}:{port} 启动 HTTP/SOCKS5 代理: {diag_msg}", flush=True)
            return

    try:
        while not shutdown.is_set():
            try:
                client, address = server.accept()
            except socket.timeout:
                continue
            except OSError as exc:
                if shutdown.is_set():
                    break
                print(f"[错误] 代理接收连接失败: {exc}", flush=True)
                if shutdown.wait(0.5):
                    break
                continue
            if not proxy_connection_sem.acquire(blocking=False):
                print(
                    f"[代理限流] 当前连接数已达到 {MAX_PROXY_CONNECTIONS}，拒绝客户端 {address}",
                    flush=True,
                )
                try:
                    client.close()
                except OSError:
                    pass
                continue

            def run_client() -> None:
                try:
                    proxy_client(client, address)
                finally:
                    proxy_connection_sem.release()

            threading.Thread(target=run_client, daemon=True).start()
    finally:
        try:
            server.close()
        except OSError:
            pass
