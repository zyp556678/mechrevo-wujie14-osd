#!/bin/bash
# Install the MIFS Fn-key OSD daemon and GNOME Shell extension.
#
# Run as root (pkexec or sudo). The extension is installed into the invoking
# user's home, not root's, so $SUDO_USER is used to find the right home.
set -euo pipefail

REPO="$(dirname "$(readlink -f "$0")")"

LIBEXEC=/usr/libexec/mifs-osd
DBUS_CONF=/usr/share/dbus-1/system.d/org.mechrevo.Mifs.conf
UNIT=/etc/systemd/system/mifs-osdd.service
MODULES_CONF=/etc/modules-load.d/mifs-osd.conf

if [ "$(id -u)" -ne 0 ]; then
    echo "must run as root (pkexec $0)" >&2
    exit 1
fi

TARGET_USER="${SUDO_USER:-${PKEXEC_UID:+$(id -un "$PKEXEC_UID")}}"
if [ -z "${TARGET_USER:-}" ] || [ "$TARGET_USER" = root ]; then
    echo "cannot determine the desktop user; set SUDO_USER explicitly" >&2
    exit 1
fi
TARGET_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
echo "installing for user: $TARGET_USER ($TARGET_HOME)"

# --- daemon ---------------------------------------------------------------
install -d -m 0755 "$LIBEXEC"
cp -r "$REPO/src/daemon/mifs_osd" "$LIBEXEC/"
install -m 0755 /dev/stdin "$LIBEXEC/mifs-osdd" <<'EOF'
#!/usr/bin/python3 -I
import sys
sys.path.insert(0, '/usr/libexec/mifs-osd')
from mifs_osd.__main__ import main
sys.exit(main())
EOF
echo "installed daemon -> $LIBEXEC"

# --- icons + extension ----------------------------------------------------
EXT_DST="$TARGET_HOME/.local/share/gnome-shell/extensions/mifs-osd@local"
install -d -m 0755 "$EXT_DST/icons"
install -m 0644 "$REPO/src/extension/mifs-osd@local/metadata.json" "$EXT_DST/"
install -m 0644 "$REPO/src/extension/mifs-osd@local/extension.js" "$EXT_DST/"
install -m 0644 "$REPO/src/extension/mifs-osd@local/icons/"*.png "$EXT_DST/icons/"
chown -R "$TARGET_USER":"$TARGET_USER" "$TARGET_HOME/.local/share/gnome-shell/extensions/mifs-osd@local"
echo "installed extension -> $EXT_DST"

# --- dbus policy ----------------------------------------------------------
install -m 0644 "$REPO/dbus/org.mechrevo.Mifs.conf" "$DBUS_CONF"
systemctl reload dbus.service 2>/dev/null || systemctl restart dbus.service
echo "installed dbus policy -> $DBUS_CONF"

# --- autoload acpi_call ---------------------------------------------------
echo acpi_call > "$MODULES_CONF"
modprobe acpi_call 2>/dev/null || true
echo "acpi_call will autoload at boot"

# --- systemd --------------------------------------------------------------
install -m 0644 "$REPO/systemd/mifs-osdd.service" "$UNIT"
systemctl daemon-reload
systemctl enable --now mifs-osdd.service
echo "daemon enabled and started"

# --- enable the extension -------------------------------------------------
if command -v gnome-extensions >/dev/null 2>&1; then
    sudo -u "$TARGET_USER" gnome-extensions enable mifs-osd@local 2>/dev/null \
        && echo "extension enabled" \
        || echo "NOTE: enable it manually: gnome-extensions enable mifs-osd@local"
fi

echo
echo "Done. Press Fn+F1 / Fn+F4 / Fn+F7 to test."
