#!/usr/bin/env python3
"""Compatibility wrapper for the packaged backend runtime."""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("AIMILIVPN_INSTALL_DIR", str(Path(__file__).resolve().parent))

from aimilivpn.system import vpngate_manager as _runtime


if __name__ == "__main__":
    _runtime.main()
else:
    sys.modules[__name__] = _runtime
