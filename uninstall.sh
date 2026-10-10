#!/bin/bash
# Remove everything install.sh added. Run as root.
set -uo pipefail

REPO="$(dirname "$(readlink -f "$0")")"

if [ "$(id -u)" -ne 0 ]; then
    echo "must run as root (pkexec $0)" >&2
    exit 1
fi

TARGET_USER="${SUDO_USER:-${PKEXEC_UID:+$(id -un "$PKEXEC_UID")}}"
TARGET_HOME=""
if [ -n "${TARGET_USER:-}" ] && [ "$TARGET_USER" != root ]; then
    TARGET_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
fi

systemctl disable --now mifs-osdd.service 2>/dev/null || true
rm -f /etc/systemd/system/mifs-osdd.service
systemctl daemon-reload

rm -rf /usr/libexec/mifs-osd
rm -f /usr/share/dbus-1/system.d/org.mechrevo.Mifs.conf
systemctl reload dbus.service 2>/dev/null || systemctl restart dbus.service
rm -f /etc/modules-load.d/mifs-osd.conf

if [ -n "$TARGET_HOME" ]; then
    rm -rf "$TARGET_HOME/.local/share/gnome-shell/extensions/mifs-osd@local"
fi

echo "Removed. acpi_call itself was left installed; remove it with:"
echo "  apt remove acpi-call-dkms"
