#!/usr/bin/env python3
"""Downscale the extracted 2000x2000 OSD PNGs to 600x600 for the Shell extension.

Source images live in extracted_osd_png/. The Shell extension draws them at
icon_size=300 logical pixels, so 600px covers HiDPI (2x) without upscaling.
SystemPerfMode_* sources are 2001x2001 and get centre-cropped to an even size.
"""
import os
import sys

import gi

gi.require_version('GdkPixbuf', '2.0')
from gi.repository import GdkPixbuf  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, 'extracted_osd_png')
DST = os.path.join(ROOT, 'src', 'extension', 'mifs-osd@local', 'icons')
TARGET = 600


def main():
    if not os.path.isdir(SRC):
        sys.exit('source directory missing: %s' % SRC)
    os.makedirs(DST, exist_ok=True)

    names = sorted(f for f in os.listdir(SRC) if f.lower().endswith('.png'))
    if not names:
        sys.exit('no PNGs found in %s' % SRC)

    for name in names:
        src_path = os.path.join(SRC, name)
        pb = GdkPixbuf.Pixbuf.new_from_file(src_path)

        # Centre-crop to an even square so the downscale stays clean.
        side = min(pb.get_width(), pb.get_height())
        if side % 2:
            side -= 1
        if (pb.get_width(), pb.get_height()) != (side, side):
            x = (pb.get_width() - side) // 2
            y = (pb.get_height() - side) // 2
            pb = pb.new_subpixbuf(x, y, side, side)

        scaled = pb.scale_simple(TARGET, TARGET, GdkPixbuf.InterpType.BILINEAR)
        out_path = os.path.join(DST, name)
        scaled.savev(out_path, 'png', [], [])
        print('%-36s %dx%d -> %dx%d' % (name, pb.get_width(), pb.get_height(),
                                        TARGET, TARGET))

    print('\n%d icons written to %s' % (len(names), DST))


if __name__ == '__main__':
    main()
