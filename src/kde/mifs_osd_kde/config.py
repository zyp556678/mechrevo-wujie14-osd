"""The KDE frontend's settings, stored as an INI file.

The GNOME frontend keeps these values in GSettings, which has no equivalent
on Plasma, so the KDE side owns its own file. Every value means the same
thing it does in the extension's schema -- positions are fractions of the
monitor and the size is a fraction of its width -- so the icon lands in the
same place on either desktop and switching back does not need a re-tune.

Parsing is deliberately forgiving. The file is meant to be hand-editable, and
a typo in it should cost the user their exact placement, not the OSD itself.
"""
import configparser
import os

CONFIG_DIR = os.path.expanduser('~/.config/mifs-osd')
CONFIG_PATH = os.path.join(CONFIG_DIR, 'osd.conf')

BACKENDS = ('layer-shell', 'plasma')
POSITION_MODES = ('percent', 'margin')

# Ranges the settings window offers. Values outside them are clamped rather
# than rejected: a slightly odd number still draws, and silently resetting a
# hand-edited file to defaults would be worse than honouring it.
MIN_SIZE_PERCENT = 0.02
MAX_SIZE_PERCENT = 0.60

DEFAULTS = """\
[backend]
mode = layer-shell

[position]
mode = percent
x-percent = 0.5
y-percent = 0.77
bottom-margin = 120

[icon]
size-percent = 0.13

[preview]
icon = SystemPerfMode_2.png
trigger = 0
"""


def _choice(parser, section, key, allowed, default):
    value = parser.get(section, key, fallback=default).strip()
    return value if value in allowed else default


def _number(parser, section, key, default, lo, hi):
    try:
        value = parser.getfloat(section, key, fallback=default)
    except (configparser.Error, ValueError):
        return default
    return min(max(value, lo), hi)


def _integer(parser, section, key, default, lo, hi):
    try:
        value = parser.getint(section, key, fallback=default)
    except (configparser.Error, ValueError):
        return default
    return min(max(value, lo), hi)


class Config:
    """A snapshot of the settings.

    Reloading replaces the values in place; nothing else caches them, so an
    edit always takes effect on the next draw.
    """

    def __init__(self, path=CONFIG_PATH):
        self.path = path
        self.backend = 'layer-shell'
        self.position_mode = 'percent'
        self.x_percent = 0.5
        self.y_percent = 0.77
        self.bottom_margin = 120
        self.size_percent = 0.13
        self.preview_icon = 'SystemPerfMode_2.png'
        self.preview_trigger = 0

    def reload(self):
        """Re-read the file, filling in defaults for anything unusable."""
        parser = configparser.ConfigParser(interpolation=None)
        parser.read_string(DEFAULTS)
        try:
            parser.read(self.path, encoding='utf-8')
        except OSError:
            pass  # missing file: the defaults above are the whole story
        except configparser.Error:
            pass  # malformed file: same, rather than refusing to run

        self.backend = _choice(parser, 'backend', 'mode', BACKENDS,
                               'layer-shell')
        self.position_mode = _choice(parser, 'position', 'mode',
                                     POSITION_MODES, 'percent')
        self.x_percent = _number(parser, 'position', 'x-percent', 0.5, 0.0, 1.0)
        self.y_percent = _number(parser, 'position', 'y-percent', 0.77, 0.0, 1.0)
        self.bottom_margin = _integer(parser, 'position', 'bottom-margin',
                                      120, 0, 4000)
        self.size_percent = _number(parser, 'icon', 'size-percent', 0.13,
                                    MIN_SIZE_PERCENT, MAX_SIZE_PERCENT)
        self.preview_icon = parser.get('preview', 'icon', fallback='').strip()
        self.preview_trigger = _integer(parser, 'preview', 'trigger', 0,
                                        -2 ** 31, 2 ** 31 - 1)
        return self

    def save(self):
        """Write the current values back, creating the directory if needed.

        Only the settings window calls this. The renderer never writes, so a
        running OSD cannot fight a preference edit for ownership of the file.
        """
        parser = configparser.ConfigParser(interpolation=None)
        parser.read_string(DEFAULTS)
        parser['backend']['mode'] = self.backend
        parser['position']['mode'] = self.position_mode
        parser['position']['x-percent'] = '%.4f' % self.x_percent
        parser['position']['y-percent'] = '%.4f' % self.y_percent
        parser['position']['bottom-margin'] = str(self.bottom_margin)
        parser['icon']['size-percent'] = '%.4f' % self.size_percent
        parser['preview']['icon'] = self.preview_icon
        parser['preview']['trigger'] = str(self.preview_trigger)

        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        # Write through a temporary file: the renderer watches this path, and
        # watching a half-written file would reload garbage.
        tmp = self.path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as handle:
            parser.write(handle)
        os.replace(tmp, self.path)
