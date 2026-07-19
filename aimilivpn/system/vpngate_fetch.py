from __future__ import annotations

import json
import os
import ssl
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from aimilivpn.core import upstream_proxy as upstream_proxy_core
from aimilivpn.providers import vpngate as vpngate_provider


@dataclass(frozen=True)
class VpnGateFetchFacade:
    api_url: str
    config_dir: Path
    max_scan_rows: int
    allowed_countries: set[str]
    allow_insecure_fetch: bool
    load_blacklist: Callable[[], dict[str, dict[str, Any]]]
    cached_nodes: Callable[[], list[dict[str, Any]]]
    set_state: Callable[..., None]
    log_line: Callable[[str, str], None]
    diagnose_api_failure: Callable[[str], tuple[str, str]]
    get_upstream_proxy: Callable[[], tuple[str, str, int]]
    get_upstream_proxy_auth: Callable[[], tuple[str | None, str | None]]
    country_translations: dict[str, str]
    safe_name: Callable[[str], str]
    country_catalog_file: Path | None = None
    sleep: Callable[[float], None] = time.sleep
    now: Callable[[], float] = time.time
    urlopen: Callable[..., Any] = urllib.request.urlopen

    def fetch_api_text_via_proxy(
        self,
        url: str,
        proxy_type: str,
        proxy_host: str,
        proxy_port: int,
        use_ssl_verify: bool = True,
    ) -> str:
        return upstream_proxy_core.fetch_text_via_proxy(
            url,
            proxy_type,
            proxy_host,
            proxy_port,
            proxy_auth=self.get_upstream_proxy_auth,
            use_ssl_verify=use_ssl_verify,
        )

    def fetch_api_text(self, url: str | None = None, use_ssl_verify: bool = True) -> str:
        url = url or self.api_url
        proxy_type, proxy_host, proxy_port = self.get_upstream_proxy()
        if proxy_type and proxy_host and proxy_port:
            try:
                print(
                    f"[VPNGate 抓取] 检测到上游 {proxy_type} 代理，尝试通过代理获取 API…",
                    flush=True,
                )
                return self.fetch_api_text_via_proxy(
                    url,
                    proxy_type,
                    proxy_host,
                    proxy_port,
                    use_ssl_verify,
                )
            except Exception as exc:
                print(
                    f"[VPNGate 抓取] 通过代理获取 API 失败，尝试使用直连；异常类型: {type(exc).__name__}",
                    flush=True,
                )
                self.log_line("WARNING", f"使用上游 {proxy_type} 代理获取 API 失败；异常类型: {type(exc).__name__}")

        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 vpngate-openvpn-manager/2.0",
                "Accept": "text/plain,*/*",
            },
        )
        if url.startswith("https://") and not use_ssl_verify:
            context = ssl._create_unverified_context()
            with self.urlopen(request, timeout=12, context=context) as response:
                return response.read().decode("utf-8", errors="replace")
        with self.urlopen(request, timeout=12) as response:
            return response.read().decode("utf-8", errors="replace")

    def fetch_candidates(self) -> list[dict[str, Any]]:
        blacklist = self.load_blacklist()
        candidates: list[dict[str, Any]] = []
        seen_ips: set[str] = set()
        has_cache = len(self.cached_nodes()) > 0
        max_attempts = 1 if has_cache else 2

        attempts_targets = [(self.api_url, True)]
        if self.allow_insecure_fetch:
            print(
                "[候选节点抓取] 已启用 ALLOW_INSECURE_FETCH，可能使用不安全的 VPNGate 回退连接。",
                flush=True,
            )
            self.log_line("WARNING", "已启用 ALLOW_INSECURE_FETCH，可能使用不安全的 VPNGate 回退连接。")
            attempts_targets.append((self.api_url, False))
        if self.allow_insecure_fetch and self.api_url.startswith("https://"):
            attempts_targets.append((self.api_url.replace("https://", "http://"), True))

        self.log_line("INFO", "开始拉取官方 API 节点列表...")

        last_error: Exception | None = None
        for url, verify_ssl in attempts_targets:
            for attempt in range(max_attempts):
                if attempt > 0:
                    self.sleep(1.5)
                try:
                    message = f"尝试拉取 VPNGate API（TLS 验证: {verify_ssl}，第 {attempt + 1} 次尝试）…"
                    print(f"[候选节点抓取] {message}", flush=True)
                    self.log_line("INFO", message)
                    api_text = self.fetch_api_text(url, verify_ssl)
                    self._write_country_catalog(api_text)
                    parsed_nodes, seen_ips, warnings = vpngate_provider.parse_legacy_candidates_filtered(
                        api_text,
                        self.config_dir,
                        max_scan_rows=self.max_scan_rows,
                        allowed_countries=self.allowed_countries,
                        blacklist=blacklist,
                        seen_ips=seen_ips,
                        now=self.now(),
                        country_translations=self.country_translations,
                        safe_name_func=self.safe_name,
                    )
                    for warning in warnings:
                        print(f"[候选节点抓取] 已跳过无效的 VPNGate 数据行；技术详情: {warning}", flush=True)
                        self.log_line("WARNING", f"已跳过无效的 VPNGate 数据行；技术详情: {warning}")
                    candidates.extend(parsed_nodes)
                    if candidates:
                        break
                except Exception as exc:
                    last_error = exc
                    print(
                        f"[候选节点抓取] 拉取失败；TLS 验证: {verify_ssl}；异常类型: {type(exc).__name__}",
                        flush=True,
                    )
                    self.log_line("WARNING", f"拉取失败 (URL: {url}, 验证: {verify_ssl}): {exc}")
            if candidates:
                break

        if not candidates:
            error_code, diagnostic = self.diagnose_api_failure(self.api_url)
            full_message = f"获取官方 API 节点最终失败: {last_error} | 诊断结果: {diagnostic}"
            print(f"[错误代码 {error_code}] {full_message}", flush=True)
            self.log_line("ERROR", f"[错误代码 {error_code}] {full_message}")
            self.set_state(
                last_fetch_status="error",
                last_fetch_error_code=error_code,
                last_fetch_message=diagnostic,
            )
            if last_error:
                raise RuntimeError(diagnostic) from last_error
            raise RuntimeError(diagnostic)

        self.set_state(
            last_fetch_at=self.now(),
            last_fetch_status="ok",
            last_fetch_message=f"Fetched {len(candidates)} unique candidates across multiple attempts.",
            blacklisted_nodes=len(blacklist),
        )
        self.log_line("INFO", f"成功获取官方 API 节点，共 {len(candidates)} 个候选节点")
        return candidates

    def _write_country_catalog(self, api_text: str) -> None:
        countries = vpngate_provider.country_catalog_from_text(api_text)
        if not countries:
            return
        path = self.country_catalog_file or (self.config_dir.parent / "country_catalog.json")
        payload = json.dumps(
            {"version": 1, "updated_at": self.now(), "countries": countries},
            ensure_ascii=False,
            indent=2,
        ).encode("utf-8")
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.tmp")
        try:
            temporary.write_bytes(payload)
            os.chmod(temporary, 0o600)
            os.replace(temporary, path)
            os.chmod(path, 0o600)
        finally:
            temporary.unlink(missing_ok=True)
