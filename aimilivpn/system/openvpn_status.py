from __future__ import annotations

from typing import Callable


HANDSHAKE_STATUS_MAP: tuple[tuple[str, str, str], ...] = (
    ("resolving", "解析域名", "正在解析服务器域名与 IP 地址..."),
    ("udp link local", "物理连接", "已创建本地套接字，开始尝试发送数据包..."),
    ("tcp link local", "物理连接", "已创建本地套接字，开始尝试发送数据包..."),
    ("tls: initial packet", "证书握手", "已成功发送首包，正在与远程服务器建立 TLS 安全通道..."),
    ("verify ok", "证书校验", "服务器证书校验成功，正在进行身份验证..."),
    ("peer connection initiated", "协商加密", "控制通道已建立，已初始化与服务器的加密对等连接..."),
    ("push_request", "请求配置", "正在向服务器发送 PUSH_REQUEST 请求配置参数与 IP 分配..."),
    ("push_reply", "应用配置", "已接收服务器 PUSH_REPLY，获取到 IP 分配，正在准备配置网卡..."),
    ("tun/tap device", "创建网卡", "正在创建虚拟通道并打开 TUN 虚拟网卡设备..."),
    ("do_ifconfig", "网卡配置", "正在为虚拟网卡配置 IP 地址及相关网络属性..."),
)


def handshake_status_update(line_lower: str) -> dict[str, str] | None:
    normalized_line = line_lower.lower()
    for key, short_status, detailed_desc in HANDSHAKE_STATUS_MAP:
        if key in normalized_line:
            return {
                "active_node_latency": short_status,
                "last_check_message": detailed_desc,
            }
    return None


def update_handshake_status(line_lower: str, set_state: Callable[..., None]) -> None:
    update = handshake_status_update(line_lower)
    if update is not None:
        set_state(**update)
