"""Work out where the icon goes on a screen.

This is a port of the GNOME extension's ``_applyGeometry`` and the maths is
kept identical on purpose: positions are fractions of the monitor and the
size is a fraction of its width, so the same settings put the icon in the
same place on either desktop. Do not "fix" a rounding difference here without
changing extension.js too -- the two are meant to agree.
"""
from dataclasses import dataclass

# Below this the icon is a smudge; above it, the clamp keeps a silly
# size-percent from covering the whole screen.
MIN_SIZE_PX = 24


@dataclass(frozen=True)
class Placement:
    """Icon position and size in monitor pixels."""

    x: int
    y: int
    size: int


@dataclass(frozen=True)
class Anchors:
    """Which screen edges to pin to and the offsets that follow.

    layer-shell has no free-floating position: a surface is anchored to one or
    more edges and then offset by margins. Only two of the four margins are
    ever in use; the rest stay zero so the unused edges stay unpinned.
    """

    left: bool
    top: bool
    margin_left: int
    margin_right: int
    margin_top: int
    margin_bottom: int


def placement(config, width, height):
    """Resolve the configured size and position against a monitor."""
    size = round(width * config.size_percent)
    size = max(MIN_SIZE_PX, min(size, width, height))

    if config.position_mode == 'margin':
        # Horizontally centred, lifted clear of the bottom edge.
        x = (width - size) // 2
        y = height - size - config.bottom_margin
    else:
        # The icon is centred on the configured fraction of the screen.
        x = round(width * config.x_percent - size / 2)
        y = round(height * config.y_percent - size / 2)
    return Placement(x, y, size)


def anchors(place, width, height):
    """Pick the anchor edges for a placement.

    Margins are unsigned in the protocol, so a position that hangs off the
    left or top edge -- which a percentage near 0 produces, since the icon is
    centred on the point -- cannot be expressed as a negative offset. Deciding
    the edge per axis instead measures from the opposite side, which keeps the
    offset non-negative for any placement.
    """
    if place.x + place.size / 2 <= width / 2:
        left, margin_left, margin_right = True, max(0, place.x), 0
    else:
        left, margin_left = False, 0
        margin_right = max(0, width - place.x - place.size)

    if place.y + place.size / 2 <= height / 2:
        top, margin_top, margin_bottom = True, max(0, place.y), 0
    else:
        top, margin_top = False, 0
        margin_bottom = max(0, height - place.y - place.size)

    return Anchors(left, top, margin_left, margin_right, margin_top,
                   margin_bottom)
