#!/usr/bin/env bash
set -euo pipefail

VERSION="${1:-}"
OUTPUT_DIR="${2:-dist-release}"
if [[ ! "$VERSION" =~ ^v[0-9]+\.[0-9]+\.[0-9]+([.-][A-Za-z0-9._-]+)?$ ]]; then
    echo "usage: $0 vX.Y.Z [output-dir]" >&2
    exit 2
fi

COMMIT=$(git rev-list -n 1 "$VERSION")
if [ -z "$COMMIT" ]; then
    echo "release tag not found: $VERSION" >&2
    exit 1
fi
mkdir -p "$OUTPUT_DIR"
ARCHIVE="aimilivpn-${VERSION}.tar.gz"
git archive --format=tar --prefix="aimilivpn-${VERSION}/" "$COMMIT" | gzip -n > "$OUTPUT_DIR/$ARCHIVE"
(
    cd "$OUTPUT_DIR"
    sha256sum "$ARCHIVE" > SHA256SUMS
)
echo "created $OUTPUT_DIR/$ARCHIVE and $OUTPUT_DIR/SHA256SUMS"
