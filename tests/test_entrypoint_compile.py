from __future__ import annotations

import py_compile
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class EntrypointCompileTests(unittest.TestCase):
    def test_runtime_entrypoints_compile(self) -> None:
        entrypoints = (
            ROOT / "vpngate_manager.py",
            ROOT / "proxy_server.py",
            ROOT / "console_server.py",
            ROOT / "vpn_utils.py",
            ROOT / "aimilivpn" / "system" / "vpngate_manager.py",
            ROOT / "aimilivpn" / "system" / "proxy_server.py",
            ROOT / "aimilivpn" / "system" / "console_server.py",
        )

        with tempfile.TemporaryDirectory() as tmp:
            for index, path in enumerate(entrypoints):
                with self.subTest(path=path.name):
                    py_compile.compile(
                        str(path),
                        cfile=str(Path(tmp) / f"{index}.pyc"),
                        doraise=True,
                    )


if __name__ == "__main__":
    unittest.main()
