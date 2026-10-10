"""Map (feature, value) pairs to OSD icon filenames.

Icon numbering does NOT always match the MIFS value. The vendor shipped the
SystemPerfMode artwork in visual order (0=leaf/quiet, 2=rocket/performance)
while the firmware numbers the modes the other way round (0=performance,
2=quiet). Verified by opening the PNGs. Do not "simplify" this table.
"""

# feature -> {value: icon filename}
ICONS = {
    'SystemPerMode': {
        0: 'SystemPerfMode_2.png',   # rocket  = performance
        1: 'SystemPerfMode_1.png',   # needle  = balanced
        2: 'SystemPerfMode_0.png',   # leaf    = quiet
    },
    'TPLock': {
        0: 'TouchPad_ON.png',
        1: 'TouchPad_OFF.png',
    },
    'FnLock': {
        0: 'Fn_OFF.png',
        1: 'Fn_ON.png',
    },
    'RGBKeyboardBrightness': {
        i: 'RGBKeyboardBrightnessLevel_%d.png' % i for i in range(4)
    },
}


def icon_for(feature, value):
    """Return the icon filename for a feature value, or None if unmapped."""
    table = ICONS.get(feature)
    if table is None:
        return None
    return table.get(value)
