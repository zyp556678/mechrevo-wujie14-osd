#!/bin/bash
# Build the distributable zip for a GitHub release.
#
# The archive unpacks to a single top-level directory named after the
# project, so a user can extract it, cd in, and run install.sh. The
# extension subdirectory keeps the layout GNOME expects, so install.sh
# copies it verbatim.
set -euo pipefail

REPO="$(dirname "$(dirname "$(readlink -f "$0")")")"
VERSION="${1:-$(git -C "$REPO" describe --tags --always --dirty 2>/dev/null || echo dev)}"
NAME="mechrevo-wujie14-osd-$VERSION"
OUT="$REPO/dist/$NAME.zip"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

command -v zip >/dev/null || { echo "zip not installed" >&2; exit 1; }

mkdir -p "$REPO/dist"
rm -f "$OUT"

# Stage under the release name so the extracted directory is self-describing
# rather than inheriting whatever the working copy happens to be called.
mkdir -p "$STAGE/$NAME"
cp -r "$REPO/install.sh" "$REPO/uninstall.sh" "$REPO/README.md" \
      "$REPO/LICENSE" "$REPO/src" "$REPO/systemd" "$REPO/dbus" \
      "$STAGE/$NAME/"
find "$STAGE" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
find "$STAGE" -name '*.pyc' -delete 2>/dev/null || true

(cd "$STAGE" && zip -r "$OUT" "$NAME" >/dev/null)

echo "built $OUT"
unzip -l "$OUT" | tail -3
