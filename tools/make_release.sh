#!/bin/bash
# Build the artifacts attached to a GitHub release.
#
# Three of them, because there are three ways to install this and they do not
# overlap:
#
#   - the source zip, for install.sh on a machine where nothing is packaged;
#   - the .deb, which carries the shared daemon and the KDE Plasma frontend;
#   - the GNOME Shell extension, which is what extensions.gnome.org
#     distributes and what GNOME users are pointed at.
#
# The frontends are kept apart on purpose. Bundling both into one archive
# would ship every user a desktop's worth of code they cannot run, and would
# leave two copies of the same Javascript on disk for anyone who installs the
# extension from extensions.gnome.org as well.
set -euo pipefail

REPO="$(dirname "$(dirname "$(readlink -f "$0")")")"
VERSION="${1:-$(git -C "$REPO" describe --tags --abbrev=0 2>/dev/null || echo dev)}"
VERSION="${VERSION#v}"

SRC_NAME="mechrevo-wujie14-osd-$VERSION"
EXT_UUID="mifs-osd@local"
EXT_NAME="mifs-osd-gnome-extension-$VERSION"
OUT="$REPO/dist"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

command -v zip >/dev/null || { echo "zip not installed" >&2; exit 1; }

mkdir -p "$OUT"
rm -f "$OUT/$SRC_NAME.zip" "$OUT/$EXT_NAME.zip"

# --- source zip, for install.sh -------------------------------------------
# Unpacks to a single top-level directory named after the project, so an
# extracted copy is self-describing rather than inheriting whatever the
# working copy happens to be called.
mkdir -p "$STAGE/$SRC_NAME"
cp -r "$REPO/install.sh" "$REPO/uninstall.sh" "$REPO/README.md" \
      "$REPO/LICENSE" "$REPO/src" "$REPO/systemd" "$REPO/dbus" \
      "$REPO/desktop" "$STAGE/$SRC_NAME/"
find "$STAGE/$SRC_NAME" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
find "$STAGE/$SRC_NAME" -name '*.pyc' -delete 2>/dev/null || true

(cd "$STAGE" && zip -r "$OUT/$SRC_NAME.zip" "$SRC_NAME" >/dev/null)
echo "built $OUT/$SRC_NAME.zip"

# --- GNOME Shell extension ------------------------------------------------
# The extension files go at the top level of the archive, not inside a
# directory: that is the layout both extensions.gnome.org and
# `gnome-extensions install` expect.
EXT_SRC="$REPO/src/extension/$EXT_UUID"
EXT_DIR="$STAGE/$EXT_NAME"
mkdir -p "$EXT_DIR"
cp "$EXT_SRC/metadata.json" "$EXT_SRC/extension.js" "$EXT_SRC/prefs.js" "$EXT_DIR/"
cp -r "$EXT_SRC/icons" "$EXT_SRC/schemas" "$EXT_DIR/"
find "$EXT_DIR" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
find "$EXT_DIR" -name 'gschemas.compiled' -delete 2>/dev/null || true

(cd "$EXT_DIR" && zip -r "$OUT/$EXT_NAME.zip" . >/dev/null)
echo "built $OUT/$EXT_NAME.zip"
echo "  upload this one to extensions.gnome.org"

# --- Debian package -------------------------------------------------------
# Built by its own script, which is also usable on its own.
"$REPO/tools/build_deb.sh" "$VERSION"
