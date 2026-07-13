from __future__ import annotations

import json
import os
import stat
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory

from aimilivpn.system.instance_lifecycle import InstanceLifecycle, LifecycleError


class FakeSystemctl:
    def __init__(self, fail_on: tuple[str, ...] | None = None) -> None:
        self.calls: list[list[str]] = []
        self.fail_on = fail_on

    def __call__(self, args: list[str]) -> SimpleNamespace:
        self.calls.append(list(args))
        failed = self.fail_on is not None and tuple(args) == self.fail_on
        return SimpleNamespace(returncode=1 if failed else 0)


def build_lifecycle(
    root: Path,
    runner: FakeSystemctl,
    countries: list[dict[str, object]] | None = None,
) -> InstanceLifecycle:
    config_dir = root / "etc" / "aimilivpn"
    install_dir = root / "opt" / "aimilivpn"
    config_dir.mkdir(parents=True)
    install_dir.mkdir(parents=True)
    (config_dir / "instance_api_token").write_text("token-1\n", encoding="utf-8")
    return InstanceLifecycle(
        config_dir=config_dir,
        install_dir=install_dir,
        instances_file=config_dir / "instances.json",
        token_file=config_dir / "instance_api_token",
        systemctl=runner,
        lock=threading.RLock(),
        country_catalog=(lambda: list(countries)) if countries is not None else None,
    )


class InstanceLifecycleTests(unittest.TestCase):
    def test_legacy_catalog_fallback_preserves_preferred_countries(self) -> None:
        with TemporaryDirectory() as tmp:
            lifecycle = build_lifecycle(Path(tmp), FakeSystemctl())

            catalog = lifecycle.catalog()

        self.assertEqual({item["country"] for item in catalog}, {"JP", "KR", "US"})
        self.assertEqual(next(item for item in catalog if item["country"] == "JP")["tun_dev"], "tun10")

    def test_create_atomically_writes_private_env_catalog_and_starts_service(self) -> None:
        with TemporaryDirectory() as tmp:
            runner = FakeSystemctl()
            lifecycle = build_lifecycle(Path(tmp), runner)

            created = lifecycle.create("US")

            env_file = Path(created["env_file"])
            env_text = env_file.read_text(encoding="utf-8")
            catalog = json.loads(lifecycle.instances_file.read_text(encoding="utf-8"))
            self.assertIn("INSTANCE_API_TOKEN=token-1", env_text)
            self.assertIn("ALLOWED_COUNTRIES=US", env_text)
            self.assertEqual(catalog["instances"], [created])
            if os.name != "nt":
                self.assertEqual(stat.S_IMODE(env_file.stat().st_mode), 0o600)
                self.assertEqual(stat.S_IMODE(lifecycle.instances_file.stat().st_mode), 0o600)
            self.assertIn(["daemon-reload"], runner.calls)
            self.assertIn(["enable", "--now", "aimilivpn@us.service"], runner.calls)

    def test_duplicate_is_rejected_and_catalog_conflict_uses_next_slot(self) -> None:
        with TemporaryDirectory() as tmp:
            lifecycle = build_lifecycle(Path(tmp), FakeSystemctl())
            lifecycle.create("JP")

            with self.assertRaisesRegex(LifecycleError, "already exists"):
                lifecycle.create("JP")

            payload = json.loads(lifecycle.instances_file.read_text(encoding="utf-8"))
            payload["instances"][0]["proxy_port"] = 7929
            lifecycle.instances_file.write_text(json.dumps(payload), encoding="utf-8")
            selected = lifecycle.validate_create("US")

            self.assertEqual(selected["tun_dev"], "tun13")
            self.assertEqual(selected["proxy_port"], 7931)

    def test_host_resource_probe_blocks_creation(self) -> None:
        with TemporaryDirectory() as tmp:
            lifecycle = build_lifecycle(Path(tmp), FakeSystemctl())
            object.__setattr__(lifecycle, "resource_probe", lambda selected: ["ui_port"])

            with self.assertRaisesRegex(LifecycleError, "host resource conflict: ui_port"):
                lifecycle.create("US")

    def test_dynamic_catalog_uses_vpngate_countries_and_reserves_legacy_slots(self) -> None:
        countries = [
            {"country": "JP", "name": "Japan", "node_count": 5},
            {"country": "DE", "name": "Germany", "node_count": 3},
            {"country": "FR", "name": "France", "node_count": 2},
        ]
        with TemporaryDirectory() as tmp:
            lifecycle = build_lifecycle(Path(tmp), FakeSystemctl(), countries)

            catalog = lifecycle.catalog()

        self.assertEqual({item["country"] for item in catalog}, {"JP", "DE", "FR"})
        germany = next(item for item in catalog if item["country"] == "DE")
        self.assertEqual(germany["id"], "de")
        self.assertEqual(germany["node_count"], 3)
        self.assertEqual(germany["tun_dev"], "tun13")
        self.assertEqual(germany["policy_table"], 113)

    def test_dynamic_allocations_persist_and_do_not_renumber_existing_instances(self) -> None:
        countries = [
            {"country": "JP", "name": "Japan", "node_count": 5},
            {"country": "DE", "name": "Germany", "node_count": 3},
            {"country": "FR", "name": "France", "node_count": 2},
        ]
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            lifecycle = build_lifecycle(root, FakeSystemctl(), countries)
            jp = lifecycle.create("JP")
            germany = lifecycle.create("DE")

            restarted = InstanceLifecycle(
                config_dir=lifecycle.config_dir,
                install_dir=lifecycle.install_dir,
                instances_file=lifecycle.instances_file,
                token_file=lifecycle.token_file,
                systemctl=FakeSystemctl(),
                lock=threading.RLock(),
                country_catalog=lambda: list(countries),
            )
            france = restarted.create("FR")

        self.assertEqual(jp["tun_dev"], "tun10")
        self.assertEqual(germany["tun_dev"], "tun13")
        self.assertEqual(france["tun_dev"], "tun14")

    def test_country_missing_from_current_vpngate_catalog_is_rejected(self) -> None:
        with TemporaryDirectory() as tmp:
            lifecycle = build_lifecycle(
                Path(tmp),
                FakeSystemctl(),
                [{"country": "DE", "name": "Germany", "node_count": 1}],
            )

            with self.assertRaisesRegex(LifecycleError, "not available"):
                lifecycle.create("FR")

    def test_create_failure_rolls_back_catalog_env_and_empty_data(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runner = FakeSystemctl(("enable", "--now", "aimilivpn@kr.service"))
            lifecycle = build_lifecycle(root, runner)

            with self.assertRaisesRegex(LifecycleError, "managed service operation failed"):
                lifecycle.create("KR")

            self.assertFalse((lifecycle.config_dir / "kr.env").exists())
            self.assertFalse(lifecycle.instances_file.exists())
            self.assertFalse((lifecycle.install_dir / "data" / "kr").exists())
            self.assertIn(["disable", "--now", "aimilivpn@kr.service"], runner.calls)

    def test_delete_retains_data_by_default(self) -> None:
        with TemporaryDirectory() as tmp:
            lifecycle = build_lifecycle(Path(tmp), FakeSystemctl())
            created = lifecycle.create("US")
            data_dir = Path(created["data_dir"])
            (data_dir / "nodes.json").write_text("[]", encoding="utf-8")

            result = lifecycle.delete("us", confirmation="us")

            self.assertTrue(result["data_retained"])
            self.assertTrue(data_dir.exists())
            self.assertFalse(Path(created["env_file"]).exists())
            catalog = json.loads(lifecycle.instances_file.read_text(encoding="utf-8"))
            self.assertEqual(catalog["instances"], [])

    def test_data_purge_requires_separate_confirmation(self) -> None:
        with TemporaryDirectory() as tmp:
            lifecycle = build_lifecycle(Path(tmp), FakeSystemctl())
            created = lifecycle.create("KR")
            data_dir = Path(created["data_dir"])

            with self.assertRaisesRegex(LifecycleError, "separate confirmation"):
                lifecycle.delete("kr", confirmation="kr", retain_data=False)

            lifecycle.delete(
                "kr",
                confirmation="kr",
                retain_data=False,
                purge_data_confirmation="purge:kr",
            )
            self.assertFalse(data_dir.exists())

    def test_delete_rejects_catalog_data_path_outside_managed_root(self) -> None:
        with TemporaryDirectory() as tmp:
            lifecycle = build_lifecycle(Path(tmp), FakeSystemctl())
            created = lifecycle.create("KR")
            payload = json.loads(lifecycle.instances_file.read_text(encoding="utf-8"))
            payload["instances"][0]["data_dir"] = str(Path(tmp) / "outside")
            lifecycle.instances_file.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaisesRegex(LifecycleError, "data path is not managed"):
                lifecycle.delete("kr", confirmation="kr")

            self.assertTrue(Path(created["env_file"]).exists())

    def test_delete_failure_restores_catalog_env_and_staged_data(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runner = FakeSystemctl()
            lifecycle = build_lifecycle(root, runner)
            created = lifecycle.create("US")
            data_dir = Path(created["data_dir"])
            (data_dir / "nodes.json").write_text("[]", encoding="utf-8")
            runner.fail_on = ("daemon-reload",)

            with self.assertRaisesRegex(LifecycleError, "managed service operation failed"):
                lifecycle.delete(
                    "us",
                    confirmation="us",
                    retain_data=False,
                    purge_data_confirmation="purge:us",
                )

            self.assertTrue(Path(created["env_file"]).exists())
            self.assertTrue(data_dir.exists())
            catalog = json.loads(lifecycle.instances_file.read_text(encoding="utf-8"))
            self.assertEqual(catalog["instances"][0]["id"], "us")
            self.assertIn(["enable", "--now", "aimilivpn@us.service"], runner.calls)


if __name__ == "__main__":
    unittest.main()
