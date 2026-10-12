"""Find the icon file the daemon asked for.

The daemon sends a bare filename: it is desktop-agnostic and has no business
knowing where a frontend keeps its artwork. Resolving on this side also lets a
user override one icon without touching the system copy.
"""
import os
from pathlib import Path

USER_ICONS = os.path.expanduser('~/.local/share/mifs-osd/icons')
SYSTEM_ICONS = '/usr/share/mifs-osd/icons'

# Running from a checkout: the icons live inside the GNOME extension, because
# that is the only place extensions.gnome.org lets it keep them. The KDE
# frontend borrows the same files rather than duplicating 17 PNGs in git.
_DEV_ICONS = (Path(__file__).resolve().parents[2]
              / 'extension' / 'mifs-osd@local' / 'icons')

SEARCH_PATH = (USER_ICONS, SYSTEM_ICONS, str(_DEV_ICONS))


def resolve(filename):
    """Return an absolute path for an icon, or None if it is missing.

    An unknown name is not an error worth a dialog: the daemon may know about
    a feature this frontend's artwork predates, and a missing icon should cost
    one OSD, not the process.
    """
    if not filename:
        return None
    if os.path.isabs(filename):
        return filename if os.path.exists(filename) else None
    for directory in SEARCH_PATH:
        candidate = os.path.join(directory, filename)
        if os.path.exists(candidate):
            return candidate
    return None


def available():
    """Every icon filename on offer, for the settings window's picker."""
    seen = []
    for directory in SEARCH_PATH:
        try:
            names = sorted(os.listdir(directory))
        except OSError:
            continue
        for name in names:
            if name.endswith('.png') and name not in seen:
                seen.append(name)
    return seen
