#!/bin/bash
# Build the .deb for Debian and Ubuntu.
#
# The package carries the daemon and the KDE Plasma frontend. The GNOME Shell
# extension is deliberately not in it: extensions.gnome.org distributes that
# one, and bundling it here would leave two copies of the same Javascript on
# disk with no way to tell which one is running. GNOME users install the
# extension from the project's releases instead.
#
# The autostart entry goes to /etc/xdg/autostart rather than into anyone's
# home directory, which is what a package can do and what makes it apply to
# every user of the machine.
set -euo pipefail

REPO="$(dirname "$(dirname "$(readlink -f "$0")")")"
NAME=mechrevo-wujie14-osd

# The nearest tag, without its leading v. Pass a version to override.
VERSION="${1:-$(git -C "$REPO" describe --tags --abbrev=0 2>/dev/null || echo 0.0.0)}"
VERSION="${VERSION#v}"

if ! git -C "$REPO" describe --tags --exact-match >/dev/null 2>&1; then
    echo "warning: HEAD is not exactly $VERSION; the package will be built" >&2
    echo "         from a working tree that is ahead of the version." >&2
fi

OUT="$REPO/dist/${NAME}_${VERSION}_all.deb"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

mkdir -p "$REPO/dist"
rm -f "$OUT"

# --- file tree ------------------------------------------------------------
PKG="$STAGE/pkg"
DOC="$PKG/usr/share/doc/$NAME"

# Python and QML sources only. Copying the directory wholesale would drag
# __pycache__ along, and a .pyc built by the developer's interpreter has no
# business in a package.
stage_sources() {   # stage_sources <source-dir> <destination-dir>
    install -d -m 0755 "$2"
    find "$1" -maxdepth 1 -type f \( -name '*.py' -o -name '*.qml' \) \
        -exec install -m 0644 {} "$2/" \;
}

LIBEXEC="$PKG/usr/libexec/mifs-osd"
install -d -m 0755 "$LIBEXEC"
stage_sources "$REPO/src/daemon/mifs_osd" "$LIBEXEC/mifs_osd"
stage_sources "$REPO/src/kde/mifs_osd_kde" "$LIBEXEC/mifs_osd_kde"
stage_sources "$REPO/src/kde/mifs_osd_settings" "$LIBEXEC/mifs_osd_settings"

# Same layout as install.sh, so the two ways of installing are not two
# different systems to support.
write_launcher() {   # write_launcher <path>   (body on stdin)
    install -m 0755 /dev/stdin "$1"
}
write_launcher "$LIBEXEC/mifs-osdd" <<'EOF'
#!/usr/bin/python3 -I
import sys
sys.path.insert(0, '/usr/libexec/mifs-osd')
from mifs_osd.__main__ import main
sys.exit(main())
EOF
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

install -d -m 0755 "$PKG/usr/bin"
ln -s "../libexec/mifs-osd/mifs-osd-kde" "$PKG/usr/bin/mifs-osd-kde"
ln -s "../libexec/mifs-osd/mifs-osd-settings" "$PKG/usr/bin/mifs-osd-settings"

install -d -m 0755 "$PKG/usr/share/mifs-osd/icons"
install -m 0644 "$REPO/src/extension/mifs-osd@local/icons/"*.png \
    "$PKG/usr/share/mifs-osd/icons/"

install -d -m 0755 "$PKG/usr/share/applications"
install -m 0644 "$REPO/desktop/mifs-osd-settings.desktop" \
    "$PKG/usr/share/applications/"

install -d -m 0755 "$PKG/etc/xdg/autostart"
install -m 0644 "$REPO/desktop/mifs-osd-kde.desktop" \
    "$PKG/etc/xdg/autostart/"

install -d -m 0755 "$PKG/usr/share/dbus-1/system.d"
install -m 0644 "$REPO/dbus/org.mechrevo.Mifs.conf" \
    "$PKG/usr/share/dbus-1/system.d/"

install -d -m 0755 "$PKG/etc/systemd/system"
install -m 0644 "$REPO/systemd/mifs-osdd.service" \
    "$PKG/etc/systemd/system/"

install -d -m 0755 "$PKG/etc/modules-load.d"
# modprobe reads only lines that look like a module name, but a stray comment
# in this particular file would end up in the kernel's module list handling,
# so keep it to the bare name the way install.sh does.
echo acpi_call > "$PKG/etc/modules-load.d/mifs-osd.conf"

# --- documentation --------------------------------------------------------
install -d -m 0755 "$DOC"
install -m 0644 "$REPO/README.md" "$DOC/README.md"
install -m 0644 "$REPO/LICENSE" "$DOC/LICENSE"

cat > "$DOC/copyright" <<'EOF'
Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/
Upstream-Name: mechrevo-wujie14-osd
Source: https://github.com/zyp556678/mechrevo-wujie14-osd

Files: *
Copyright: 2026 zyp556678 <taitanyunluo2@126.com>
License: MIT

Files: usr/share/mifs-osd/icons/*
Copyright: MECHREVO
Comment: Carved out of the vendor's Windows binary T140_OSD_V06, which is
 where the artwork still belongs. Shipped here only so this machine can show
 the same icons the vendor's own tool did; the MIT licence above does not
 cover them.
EOF

{
    printf '%s (%s) unstable; urgency=medium\n\n' "$NAME" "$VERSION"
    printf '  * Package build.\n\n'
    printf ' -- zyp556678 <taitanyunluo2@126.com>  %s\n' "$(date -R)"
} | gzip -9n > "$DOC/changelog.Debian.gz"
chmod 0644 "$DOC/changelog.Debian.gz"

# --- control --------------------------------------------------------------
SIZE="$(du -sk "$PKG" | cut -f1)"
CTRL="$STAGE/pkg/DEBIAN"
install -d -m 0755 "$CTRL"

cat > "$CTRL/control" <<EOF
Package: $NAME
Version: $VERSION
Section: utils
Priority: optional
Architecture: all
Depends: python3, python3-gi, python3-pyqt6, python3-pyqt6.qtqml,
 qml6-module-qtquick, qml6-module-org-kde-layershell, layer-shell-qt
Recommends: acpi-call-dkms
Installed-Size: $SIZE
Maintainer: zyp556678 <taitanyunluo2@126.com>
Homepage: https://github.com/zyp556678/mechrevo-wujie14-osd
Description: Fn-key OSD for the MECHREVO WUJIE14 Pro on KDE Plasma
 Replaces the vendor's Windows tool T140_OSD_V06 on Linux: shows an on-screen
 display when Fn+F1 (performance mode), Fn+F4 (touchpad) or Fn+F7 (keyboard
 backlight) is pressed, and fades it out again 1.5 seconds later.
 .
 A small root daemon reads the hardware state through acpi_call and publishes
 it on the system bus; the KDE Plasma frontend draws the icon on a layer-shell
 surface, above every window and out of the way of clicks. Position and size
 are configurable, and the settings window shows the result on the real screen
 before it is saved.
 .
 GNOME is not covered by this package. GNOME Shell has no layer-shell and
 needs a Shell extension instead, which is distributed separately through
 extensions.gnome.org and the project's releases. The daemon in this package
 is what that extension talks to, so the two can be installed side by side.
 .
 acpi-call-dkms is only a recommendation because on a Secure Boot machine its
 module needs a MOK enrolment and a reboot before it will load. The daemon
 starts regardless and says so in the journal.
EOF

# --- maintainer scripts ---------------------------------------------------
cat > "$CTRL/postinst" <<'EOF'
#!/bin/sh
set -e

if [ "$1" = configure ]; then
    # Not fatal, and deliberately not a dependency: see the package
    # description. A machine that has not enrolled the MOK key yet still gets
    # a working service that reports the problem, rather than a package that
    # refuses to finish configuring.
    if ! modprobe acpi_call 2>/dev/null; then
        echo "mifs-osd: acpi_call is not loaded yet." >&2
        echo "  Install acpi-call-dkms, enrol the MOK key, then reboot." >&2
    fi

    systemctl daemon-reload || true
    systemctl enable --now mifs-osdd.service || true
    # Pick up the new D-Bus policy without a reboot.
    systemctl reload dbus.service 2>/dev/null || true
fi

exit 0
EOF

cat > "$CTRL/prerm" <<'EOF'
#!/bin/sh
set -e

# Stop before the files go, so the daemon is never left with its own code
# removed from under it.
if [ "$1" = remove ] || [ "$1" = deconfigure ]; then
    systemctl disable --now mifs-osdd.service || true
fi

exit 0
EOF

cat > "$CTRL/postrm" <<'EOF'
#!/bin/sh
set -e

if [ "$1" = remove ] || [ "$1" = purge ]; then
    systemctl daemon-reload || true
    # Drop the policy this package added. Harmless if dbus is already gone,
    # which is why the failure is ignored.
    systemctl reload dbus.service 2>/dev/null || true
fi

exit 0
EOF

chmod 0755 "$CTRL/postinst" "$CTRL/prerm" "$CTRL/postrm"

# Everything under /etc is a conffile, so an edit survives an upgrade.
cat > "$CTRL/conffiles" <<'EOF'
/etc/modules-load.d/mifs-osd.conf
/etc/systemd/system/mifs-osdd.service
/etc/xdg/autostart/mifs-osd-kde.desktop
EOF

# --- build ----------------------------------------------------------------
# --root-owner-group does the chown that fakeroot would otherwise be needed
# for, and does it without pretending to be root.
dpkg-deb --root-owner-group --build "$PKG" "$OUT" >/dev/null

echo "built $OUT"
echo
dpkg-deb --info "$OUT" | sed -n '1,12p'
echo "--- 文件数 ---"
dpkg-deb --contents "$OUT" | wc -l
