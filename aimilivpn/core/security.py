from __future__ import annotations

import re


class UnsafeOpenVPNConfig(ValueError):
    """Raised when a remote OpenVPN profile contains unsafe directives."""


FORBIDDEN_DIRECTIVES = {
    "script-security",
    "up",
    "down",
    "route-up",
    "route-pre-down",
    "down-pre",
    "plugin",
    "learn-address",
    "client-connect",
    "client-disconnect",
    "auth-user-pass-verify",
    "tls-verify",
    "iproute",
    "setenv",
}

ALLOWED_DIRECTIVES = {
    "auth",
    "auth-user-pass",
    "ca",
    "cert",
    "cipher",
    "client",
    "comp-lzo",
    "compress",
    "data-ciphers",
    "dev",
    "dhcp-option",
    "explicit-exit-notify",
    "float",
    "ifconfig-nowarn",
    "key",
    "key-direction",
    "link-mtu",
    "mute",
    "nobind",
    "persist-key",
    "persist-tun",
    "proto",
    "pull",
    "redirect-gateway",
    "remote",
    "remote-cert-tls",
    "reneg-sec",
    "resolv-retry",
    "route",
    "tls-auth",
    "tls-client",
    "tls-crypt",
    "tls-version-min",
    "tun-mtu",
    "verb",
    "verify-x509-name",
}

ALLOWED_INLINE_BLOCKS = {"ca", "cert", "key", "tls-auth", "tls-crypt"}
_PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
    re.DOTALL,
)


def _directive_name(line: str) -> str:
    return line.split(None, 1)[0].lower()


def sanitize_ovpn_config(config_text: str, *, strict: bool = True) -> str:
    if not isinstance(config_text, str) or not config_text.strip():
        raise UnsafeOpenVPNConfig("OpenVPN config is empty")

    sanitized: list[str] = []
    block_name: str | None = None

    for line_no, raw_line in enumerate(config_text.splitlines(), start=1):
        line = raw_line.strip()

        if block_name is not None:
            if line.lower() == f"</{block_name}>":
                block_name = None
            sanitized.append(raw_line.rstrip())
            continue

        if not line or line.startswith(("#", ";")):
            sanitized.append(raw_line.rstrip())
            continue

        if line.startswith("<") and line.endswith(">"):
            tag = line.strip("<>/").lower()
            if tag not in ALLOWED_INLINE_BLOCKS or line.startswith("</"):
                raise UnsafeOpenVPNConfig(f"disallowed inline block at line {line_no}: {line}")
            block_name = tag
            sanitized.append(raw_line.rstrip())
            continue

        name = _directive_name(line)
        if name in FORBIDDEN_DIRECTIVES:
            raise UnsafeOpenVPNConfig(f"unsafe OpenVPN directive at line {line_no}: {name}")
        if strict and name not in ALLOWED_DIRECTIVES:
            raise UnsafeOpenVPNConfig(f"unknown OpenVPN directive at line {line_no}: {name}")
        sanitized.append(raw_line.rstrip())

    if block_name is not None:
        raise UnsafeOpenVPNConfig(f"unterminated OpenVPN inline block: {block_name}")

    return "\n".join(sanitized).strip() + "\n"


def redact_sensitive_text(text: str) -> str:
    if not text:
        return text
    redacted = _PRIVATE_KEY_RE.sub("[REDACTED PRIVATE KEY]", text)
    redacted = re.sub(
        r"(?im)^(\s*(?:password|password_hash|api[_-]?key|token|proxy-authorization)\s*[:=]\s*).*$",
        r"\1[REDACTED]",
        redacted,
    )
    redacted = re.sub(r"(?is)<key>.*?</key>", "<key>\n[REDACTED]\n</key>", redacted)
    return redacted

