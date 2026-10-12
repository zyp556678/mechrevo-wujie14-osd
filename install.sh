#!/bin/bash
# Install the MIFS Fn-key OSD daemon and its desktop frontend.
#
# Run as root (pkexec or sudo). Per-user files go into the invoking user's
# home, not root's, so $SUDO_USER or $PKEXEC_UID is used to find it.
#
# Both frontends are installed no matter which desktop is running. The GNOME
# extension is inert unless GNOME Shell loads it, and the KDE autostart entry
# is skipped under GNOME (NotShowIn). Switching desktops therefore needs no
# reinstall -- only a re-login.
set -euo pipefail

REPO="$(dirname "$(readlink -f "$0")")"

LIBEXEC=/usr/libexec/mifs-osd
ICONS=/usr/share/mifs-osd/icons
DBUS_CONF=/usr/share/dbus-1/system.d/org.mechrevo.Mifs.conf
UNIT=/etc/systemd/system/mifs-osdd.service
MODULES_CONF=/etc/modules-load.d/mifs-osd.conf
SETTINGS_DESKTOP=/usr/share/applications/mifs-osd-settings.desktop

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

# Write one of the launcher scripts.
#
# Deliberately not `install -m 0755 /dev/stdin <dest>`, which is the obvious
# spelling and the one this script used to use. When the destination already
# exists, GNU install canonicalises the source to check that it is not the
# same file as the destination; /dev/stdin resolves through procfs to a
# pseudo-path like "pipe:[123]" or a deleted temporary file with no directory
# entry, the canonicalisation fails with ENOENT, and install aborts with a
# bare "No such file or directory". The first install works and every
# reinstall fails. A real temporary file has a path, so install can compare
# it, and the destination is replaced rather than truncated in place -- which
# matters for the daemon launcher, since the daemon may be running from it.
write_launcher() {
    local dest="$1" tmp="$1.new"
    cat > "$tmp"
    install -m 0755 "$tmp" "$dest"
    rm -f "$tmp"
}

# --- daemon ---------------------------------------------------------------
install -d -m 0755 "$LIBEXEC"
cp -r "$REPO/src/daemon/mifs_osd" "$LIBEXEC/"
write_launcher "$LIBEXEC/mifs-osdd" <<'EOF'
#!/usr/bin/python3 -I
import sys
sys.path.insert(0, '/usr/libexec/mifs-osd')
from mifs_osd.__main__ import main
sys.exit(main())
EOF

# --- KDE frontend ---------------------------------------------------------
# The renderer is what draws; the settings window writes the file the
# renderer watches. They are separate programs because the renderer sets
# QT_WAYLAND_SHELL_INTEGRATION, which turns every window in the process into
# a layer-shell surface -- fine for an OSD, wrong for a dialog.
cp -r "$REPO/src/kde/mifs_osd_kde" "$LIBEXEC/"
cp -r "$REPO/src/kde/mifs_osd_settings" "$LIBEXEC/"
write_launcher "$LIBEXEC/mifs-osd-kde" <<'EOF'
#!/usr/bin/python3 -I
import sys
sys.path.insert(0, '/usr/libexec/mifs-osd')
from mifs_osd_kde.__main__ import main
sys.exit(main())
EOF
write_launcher "$LIBEXEC/mifs-osd-settings" <<'EOF'
#!/usr/bin/python3 -I
import sys
sys.path.insert(0, '/usr/libexec/mifs-osd')
from mifs_osd_settings.main import main
sys.exit(main())
EOF

# Stable entry points, so the desktop files never need to know how the
# backing packages happen to be laid out.
ln -sf "$LIBEXEC/mifs-osd-kde" /usr/bin/mifs-osd-kde
ln -sf "$LIBEXEC/mifs-osd-settings" /usr/bin/mifs-osd-settings

# Leftovers from a checkout only get in the way of the installed copy.
find "$LIBEXEC" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true

echo "installed daemon + KDE frontend -> $LIBEXEC"

# --- icons ----------------------------------------------------------------
# Shared location. The GNOME extension has to carry its own copy because
# extensions.gnome.org ships it as one zip, and the KDE frontend falls back to
# that copy when running from a checkout.
install -d -m 0755 "$ICONS"
install -m 0644 "$REPO/src/extension/mifs-osd@local/icons/"*.png "$ICONS/"
echo "installed icons -> $ICONS"

# --- GNOME extension ------------------------------------------------------
EXT_DST="$TARGET_HOME/.local/share/gnome-shell/extensions/mifs-osd@local"
install -d -m 0755 "$EXT_DST/icons"
install -d -m 0755 "$EXT_DST/schemas"
install -m 0644 "$REPO/src/extension/mifs-osd@local/metadata.json" "$EXT_DST/"
install -m 0644 "$REPO/src/extension/mifs-osd@local/extension.js" "$EXT_DST/"
install -m 0644 "$REPO/src/extension/mifs-osd@local/prefs.js" "$EXT_DST/"
install -m 0644 "$REPO/src/extension/mifs-osd@local/icons/"*.png "$EXT_DST/icons/"
install -m 0644 "$REPO/src/extension/mifs-osd@local/schemas/"*.xml "$EXT_DST/schemas/"
glib-compile-schemas "$EXT_DST/schemas"
chown -R "$TARGET_USER":"$TARGET_USER" "$EXT_DST"
echo "installed GNOME extension -> $EXT_DST"

# --- desktop entries ------------------------------------------------------
install -m 0644 "$REPO/desktop/mifs-osd-settings.desktop" "$SETTINGS_DESKTOP"
AUTOSTART_DIR="$TARGET_HOME/.config/autostart"
install -d -m 0755 -o "$TARGET_USER" -g "$TARGET_USER" "$AUTOSTART_DIR"
install -m 0644 -o "$TARGET_USER" -g "$TARGET_USER" \
    "$REPO/desktop/mifs-osd-kde.desktop" "$AUTOSTART_DIR/"
echo "installed settings entry + KDE autostart"

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

# --- frontend dependencies ------------------------------------------------
# Checked rather than installed: this script is not a package manager, and a
# silent apt run during an install is a surprise nobody wants.
missing=""
python3 -c 'import PyQt6.QtQml' 2>/dev/null || missing="$missing python3-pyqt6.qtqml"
[ -e /usr/lib/x86_64-linux-gnu/qt6/plugins/wayland-shell-integration/liblayer-shell.so ] \
    || ls /usr/lib/*/qt6/plugins/wayland-shell-integration/liblayer-shell.so \
       >/dev/null 2>&1 \
    || missing="$missing layer-shell-qt"
if [ -n "$missing" ]; then
    echo
    echo "WARNING: the KDE frontend is missing dependencies:$missing"
    echo "  install them with:  apt install$missing"
fi

# --- start the frontend that matches the running session ------------------
if pgrep -u "$TARGET_USER" -x plasmashell >/dev/null 2>&1; then
    echo "Plasma session detected; the OSD starts automatically at next login."
    echo "To try it now, run this in your own terminal (not as root):"
    echo "    mifs-osd-kde &"
elif pgrep -u "$TARGET_USER" -x gnome-shell >/dev/null 2>&1; then
    if sudo -u "$TARGET_USER" gnome-extensions enable mifs-osd@local 2>/dev/null; then
        echo "extension enabled"
    else
        echo "NOTE: enable it manually: gnome-extensions enable mifs-osd@local"
    fi
fi

echo
echo "Done. Press Fn+F1 / Fn+F4 / Fn+F7 to test."
