import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from aimilivpn.core.probe import (
    OpenVPNProbeResult,
    TestIndexPool,
    apply_quality_patches_to_probe_results,
    build_test_config_path,
    enrich_available_probe_nodes,
    execute_openvpn_probe,
    merge_probe_results_into_nodes,
    probe_result_to_node_patch,
    run_probe_batch,
    select_probe_nodes,
    unavailable_probe_result,
)


class TestProbeHelpers(unittest.TestCase):
    def test_index_pool_acquires_until_exhausted(self) -> None:
        pool = TestIndexPool(start=2, stop=4)

        self.assertEqual(pool.acquire(), 2)
        self.assertEqual(pool.acquire(), 3)
        with self.assertRaises(RuntimeError):
            pool.acquire()

    def test_index_pool_reuses_released_index(self) -> None:
        pool = TestIndexPool(start=2, stop=4)

        first = pool.acquire()
        pool.acquire()
        pool.release(first)

        self.assertEqual(pool.acquire(), first)

    def test_index_pool_rejects_invalid_range(self) -> None:
        with self.assertRaises(ValueError):
            TestIndexPool(start=4, stop=4)

    def test_build_test_config_path_uses_safe_name_and_token(self) -> None:
        path = build_test_config_path(
            Path("/tmp/configs"),
            "JP 1/2",
            safe_name=lambda value: value.replace(" ", "_").replace("/", "_"),
            token_factory=lambda: "abc123",
        )

        self.assertEqual(path, Path("/tmp/configs/.test_JP_1_2_abc123.ovpn"))

    def test_execute_openvpn_probe_runs_and_cleans_up(self) -> None:
        pool = TestIndexPool(start=7, stop=8)
        calls: dict[str, object] = {}

        with TemporaryDirectory() as tmp:
            config_dir = Path(tmp)

            def write_config(path: Path, config_text: str) -> None:
                calls["config_path"] = path
                path.write_text(config_text, encoding="utf-8")

            def ping_latency(host: str, port: int, fallback: int) -> int:
                calls["ping"] = (host, port, fallback)
                return 42

            def run_openvpn(config_file: str, **kwargs: object) -> tuple[bool, str, object]:
                calls["run"] = (config_file, kwargs)
                self.assertTrue(Path(config_file).exists())
                return True, "ready", object()

            result = execute_openvpn_probe(
                node_id="JP 1",
                config_text="client\n",
                remote_host="198.51.100.1",
                remote_port=1194,
                fallback_ping=88,
                config_dir=config_dir,
                safe_name=lambda value: value.replace(" ", "_"),
                write_config=write_config,
                ping_latency=ping_latency,
                run_openvpn=run_openvpn,
                index_pool=pool,
                timeout=5,
            )

            self.assertTrue(result.ok)
            self.assertEqual(result.latency_ms, 42)
            self.assertEqual(result.message, "ready")
            self.assertEqual(calls["ping"], ("198.51.100.1", 1194, 88))
            config_file, kwargs = calls["run"]
            self.assertEqual(kwargs["dev"], "tun7")
            self.assertEqual(kwargs["timeout"], 5)
            self.assertFalse(Path(str(config_file)).exists())
            self.assertEqual(pool.acquire(), 7)

    def test_execute_openvpn_probe_returns_unavailable_on_write_error(self) -> None:
        def write_config(path: Path, config_text: str) -> None:
            raise OSError("disk full")

        def ping_latency(host: str, port: int, fallback: int) -> int:
            raise AssertionError("ping should not run")

        def run_openvpn(config_file: str, **kwargs: object) -> tuple[bool, str, object]:
            raise AssertionError("openvpn should not run")

        result = execute_openvpn_probe(
            node_id="jp",
            config_text="client\n",
            remote_host="198.51.100.1",
            remote_port=1194,
            fallback_ping=0,
            config_dir=Path("/tmp/configs"),
            safe_name=lambda value: value,
            write_config=write_config,
            ping_latency=ping_latency,
            run_openvpn=run_openvpn,
            index_pool=TestIndexPool(start=2, stop=3),
            timeout=5,
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.latency_ms, 0)
        self.assertIn("Failed to write configuration: disk full", result.message)

    def test_select_probe_nodes_filters_ids_and_allowed_countries(self) -> None:
        nodes = [
            {"id": "jp", "country_short": "JP"},
            {"id": "us", "country_short": "US"},
            {"id": "de", "country_short": "DE"},
        ]

        selected = select_probe_nodes(
            nodes,
            ["jp", "us"],
            node_matches_allowed=lambda node: node.get("country_short") == "JP",
        )

        self.assertEqual(selected, [{"id": "jp", "country_short": "JP"}])

    def test_probe_result_to_node_patch_builds_available_patch(self) -> None:
        patch = probe_result_to_node_patch(
            OpenVPNProbeResult(
                node_id="jp",
                remote_host="vpn.example",
                remote_port=443,
                latency_ms=35,
                ok=True,
                message="ready",
            ),
            {"id": "jp", "ip": "198.51.100.10"},
            probed_at=123.0,
        )

        self.assertEqual(patch["id"], "jp")
        self.assertEqual(patch["ip"], "198.51.100.10")
        self.assertEqual(patch["remote_host"], "vpn.example")
        self.assertEqual(patch["remote_port"], 443)
        self.assertEqual(patch["probe_status"], "available")
        self.assertEqual(patch["latency_ms"], 35)
        self.assertEqual(patch["probed_at"], 123.0)

    def test_probe_result_to_node_patch_handles_write_failure(self) -> None:
        patch = probe_result_to_node_patch(
            OpenVPNProbeResult(
                node_id="jp",
                remote_host="vpn.example",
                remote_port=443,
                latency_ms=0,
                ok=False,
                message="Failed to write configuration: readonly",
            ),
            {"id": "jp"},
            probed_at=123.0,
        )

        self.assertEqual(patch["probe_status"], "unavailable")
        self.assertEqual(patch["probe_message"], "Failed to write configuration: readonly")
        self.assertEqual(patch["owner"], "")

    def test_unavailable_probe_result_can_include_probe_metadata(self) -> None:
        result = unavailable_probe_result("jp", "failed", probed_at=123.0)

        self.assertEqual(result["id"], "jp")
        self.assertEqual(result["probe_status"], "unavailable")
        self.assertEqual(result["probed_at"], 123.0)
        self.assertEqual(result["quality"], "")

    def test_run_probe_batch_collects_results_and_exceptions(self) -> None:
        nodes = [{"id": "ok"}, {"id": "bad"}]

        def probe_node(args: tuple[int, dict[str, object]]) -> dict[str, object]:
            _, node = args
            if node["id"] == "bad":
                raise RuntimeError("boom")
            return {"id": node["id"], "probe_status": "available"}

        results = run_probe_batch(nodes, probe_node=probe_node, max_workers=2)

        self.assertEqual(results["ok"], {"id": "ok", "probe_status": "available"})
        self.assertEqual(results["bad"]["probe_status"], "unavailable")
        self.assertEqual(results["bad"]["probe_message"], "Test exception: boom")

    def test_execute_openvpn_probe_can_raise_write_error(self) -> None:
        def write_config(path: Path, config_text: str) -> None:
            raise OSError("readonly")

        with self.assertRaisesRegex(RuntimeError, "Failed to write temp config file: readonly"):
            execute_openvpn_probe(
                node_id="jp",
                config_text="client\n",
                remote_host="198.51.100.1",
                remote_port=1194,
                fallback_ping=0,
                config_dir=Path("/tmp/configs"),
                safe_name=lambda value: value,
                write_config=write_config,
                ping_latency=lambda host, port, fallback: 0,
                run_openvpn=lambda config_file, **kwargs: (False, "", object()),
                index_pool=TestIndexPool(start=2, stop=3),
                timeout=5,
                raise_write_error=True,
            )

    def test_enrich_available_probe_nodes_only_sends_available_nodes(self) -> None:
        results = [
            {"id": "jp", "probe_status": "available"},
            {"id": "us", "probe_status": "unavailable"},
        ]
        enriched_ids: list[str] = []

        def enrich(nodes: list[dict[str, object]]) -> None:
            enriched_ids.extend(str(node["id"]) for node in nodes)
            nodes[0]["owner"] = "isp"

        enrich_available_probe_nodes(results, enrich)

        self.assertEqual(enriched_ids, ["jp"])
        self.assertEqual(results[0]["owner"], "isp")
        self.assertNotIn("owner", results[1])

    def test_enrich_available_probe_nodes_reports_errors(self) -> None:
        errors: list[str] = []

        def enrich(nodes: list[dict[str, object]]) -> None:
            raise RuntimeError("rate limited")

        enrich_available_probe_nodes(
            [{"id": "jp", "probe_status": "available"}],
            enrich,
            on_error=lambda exc: errors.append(str(exc)),
        )

        self.assertEqual(errors, ["rate limited"])

    def test_apply_quality_patches_to_probe_results_updates_each_result(self) -> None:
        results = [
            {"id": "jp", "probe_status": "available", "latency_ms": "23", "probe_message": "ok"},
            {"id": "us", "probe_status": "unavailable", "latency_ms": "", "probe_message": ""},
        ]
        recorded: list[tuple[str, bool, int, str]] = []

        def record_quality(node: dict[str, object], ok: bool, latency: int, message: str) -> str:
            recorded.append((str(node["id"]), ok, latency, message))
            return str(node["id"])

        apply_quality_patches_to_probe_results(
            results,
            record_quality=record_quality,
            quality_to_patch=lambda quality: {"quality_id": quality},
            parse_int=lambda value: int(value or 0),
        )

        self.assertEqual(recorded, [("jp", True, 23, "ok"), ("us", False, 0, "")])
        self.assertEqual(results[0]["quality_id"], "jp")
        self.assertEqual(results[1]["quality_id"], "us")

    def test_apply_quality_patches_to_probe_results_reports_errors(self) -> None:
        errors: list[tuple[str, str]] = []

        def record_quality(node: dict[str, object], ok: bool, latency: int, message: str) -> str:
            raise RuntimeError("quality down")

        apply_quality_patches_to_probe_results(
            [{"id": "jp", "probe_status": "available", "latency_ms": 1}],
            record_quality=record_quality,
            quality_to_patch=lambda quality: {},
            parse_int=lambda value: int(value or 0),
            on_error=lambda node, exc: errors.append((str(node["id"]), str(exc))),
        )

        self.assertEqual(errors, [("jp", "quality down")])

    def test_merge_probe_results_into_nodes_updates_and_sorts(self) -> None:
        nodes = [
            {"id": "us", "latency_ms": 80},
            {"id": "jp", "latency_ms": 90},
            {"id": "de", "latency_ms": 70},
        ]
        updated = {
            "jp": {"id": "jp", "latency_ms": 20, "probe_status": "available"},
            "missing": {"id": "missing", "latency_ms": 1},
        }

        merged = merge_probe_results_into_nodes(
            nodes,
            updated,
            sort_nodes=lambda items: sorted(items, key=lambda item: int(item["latency_ms"])),
        )

        self.assertEqual([node["id"] for node in merged], ["jp", "de", "us"])
        self.assertEqual(merged[0]["probe_status"], "available")
        self.assertNotIn("missing", [node["id"] for node in merged])


if __name__ == "__main__":
    unittest.main()
