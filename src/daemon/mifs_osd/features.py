"""MIFS feature identifiers, from the reverse-engineered Windows binary.

Each name maps to the byte written at InData[3]. Only the features the
daemon actually polls are listed; the full enum has more entries that this
machine does not implement.
"""

# InData[1]: method class
GET = 0xFA
SET = 0xFB

# InData[3]: WMIMethodName
SYSTEM_PER_MODE = 0x08
FN_LOCK = 0x0B
TP_LOCK = 0x0C
RGB_KEYBOARD_BRIGHTNESS = 0x12

# Features the daemon polls, in a stable order.
POLLED = {
    'SystemPerMode': SYSTEM_PER_MODE,
    'FnLock': FN_LOCK,
    'TPLock': TP_LOCK,
    'RGBKeyboardBrightness': RGB_KEYBOARD_BRIGHTNESS,
}

# Byte value ranges accepted for Set, per feature.
VALUE_RANGE = {
    'SystemPerMode': (0, 2),           # 0=performance 1=balanced 2=quiet
    'FnLock': (0, 1),
    'TPLock': (0, 1),
    'RGBKeyboardBrightness': (0, 10),  # level_0..level_10; 0x80 is auto
}

# Human-readable value names, used for the OSD label.
VALUE_NAMES = {
    'SystemPerMode': {0: 'Performance', 1: 'Balanced', 2: 'Quiet'},
    'FnLock': {0: 'Off', 1: 'On'},
    'TPLock': {0: 'On', 1: 'Off'},     # TPLock=1 means the touchpad is locked
    'RGBKeyboardBrightness': {i: 'Level %d' % i for i in range(11)},
}
