#!/bin/bash
# Install the D-Bus policy file and reload the bus. Needs root.
set -eu

SRC="$(dirname "$(readlink -f "$0")")/dbus/org.mechrevo.Mifs.conf"
DST=/usr/share/dbus-1/system.d/org.mechrevo.Mifs.conf

install -m 0644 "$SRC" "$DST"
echo "installed $DST"

# Reload the system bus so the policy takes effect without a reboot.
if command -v systemctl >/dev/null 2>&1; then
    systemctl reload dbus.service 2>/dev/null || systemctl restart dbus.service
    echo "dbus.service reloaded"
fi
