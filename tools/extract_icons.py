#!/usr/bin/env python3
"""Carve the OSD PNGs out of the vendor's Windows binary.

The vendor tool embeds its artwork as System.Drawing.Bitmap objects inside a
managed resource called BLDFnHotkeyUtility.ResourceOSD. That resource is a
serialized blob whose index holds, for each name, the byte offset of the
image in the blob's data section. We read the index to pair names with
images, then cut each PNG out by its own chunk structure.

    python3 tools/extract_icons.py <BLDFnHotkeyUtility.exe> [outdir]

Defaults to extracted_osd_png/ next to the repo root. Run scripts/scale_icons.py
afterwards to produce the 600px icons the extension actually ships.
"""
import os
import re
import struct
import sys

NAMES = [
    'Ambientlight_OFF', 'Ambientlight_ON', 'CapsLK_OFF', 'CapsLK_ON',
    'Fn_OFF', 'Fn_ON', 'NumLK_OFF', 'NumLK_ON',
    'RGBKeyboardBrightnessLevel_0', 'RGBKeyboardBrightnessLevel_1',
    'RGBKeyboardBrightnessLevel_2', 'RGBKeyboardBrightnessLevel_3',
    'SystemPerfMode_0', 'SystemPerfMode_1', 'SystemPerfMode_2',
    'TouchPad_OFF', 'TouchPad_ON',
]

# A .NET BinaryFormatter object header: serialization header, then a
# System.Drawing.Bitmap record. The PNG payload follows shortly after.
BF_HEADER = b'\x00\x01\x00\x00\x00\xff\xff\xff\xff\x01\x00\x00\x00\x00\x00\x00\x00'
PNG_SIG = b'\x89PNG\r\n\x1a\n'


def png_end(data, start):
    """Return the offset just past the IEND chunk of the PNG at `start`."""
    p = start + len(PNG_SIG)
    while p < len(data):
        length = int.from_bytes(data[p:p + 4], 'big')
        ctype = data[p + 4:p + 8]
        p += 12 + length
        if ctype == b'IEND':
            return p
    raise ValueError('unterminated PNG at %#x' % start)


def build_index(data):
    """Map resource name -> byte offset within the resource blob."""
    index = {}
    for name in NAMES:
        enc = name.encode('utf-16-le')
        for m in re.finditer(re.escape(enc), data):
            pos = m.start()
            # The name is preceded by its length as a single-byte 7F int and
            # followed by the data offset as a little-endian int32.
            if pos < 1 or data[pos - 1] != len(enc):
                continue
            offset, = struct.unpack_from('<i', data, pos + len(enc))
            index[name] = offset
            break
        else:
            raise SystemExit('resource name not found: %s' % name)
    return index


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    exe = argv[1]
    outdir = argv[2] if len(argv) > 2 else os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'extracted_osd_png')

    data = open(exe, 'rb').read()
    index = build_index(data)

    # Every embedded image, located by its BinaryFormatter header.
    images = []
    for m in re.finditer(re.escape(BF_HEADER), data):
        start = m.start()
        png = data.find(PNG_SIG, start, start + 400)
        if png < 0:
            continue
        images.append((start, png, png_end(data, png)))
    if not images:
        raise SystemExit('no embedded images found')

    # The blob base is whatever makes the index offsets line up with the
    # image positions. Derive it from the first entry, then verify the rest.
    base = images[0][0] - min(index.values())
    by_start = {img[0]: img for img in images}
    for name, offset in index.items():
        if offset + base not in by_start:
            raise SystemExit('index/offset mismatch for %s' % name)

    os.makedirs(outdir, exist_ok=True)
    for name, offset in index.items():
        _, png, end = by_start[offset + base]
        blob = data[png:end]
        w, h = struct.unpack('>II', data[png + 16:png + 24])
        with open(os.path.join(outdir, name + '.png'), 'wb') as f:
            f.write(blob)
        print('%-34s %7d bytes  %dx%d' % (name + '.png', len(blob), w, h))
    print('\n%d images -> %s' % (len(index), outdir))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
