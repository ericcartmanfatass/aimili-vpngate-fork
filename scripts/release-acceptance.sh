#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"

if [ "$(uname -s)" != "Linux" ]; then
    echo "release acceptance must run on Linux; Windows source checks are not a release signal" >&2
    exit 2
fi

PYTHON="${PYTHON:-python3}"
command -v "$PYTHON" >/dev/null
command -v node >/dev/null

"$PYTHON" -m compileall -q \
    aimilivpn console_server.py proxy_server.py vpngate_manager.py vpn_utils.py tests
bash -n install.sh scripts/build-release.sh scripts/release-acceptance.sh
"$PYTHON" -m unittest discover -s tests -p 'test*.py'
node --test tests/frontend_dom.test.js
"$PYTHON" scripts/release_migration_drill.py

if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git diff --check
fi

echo "source release acceptance passed"
