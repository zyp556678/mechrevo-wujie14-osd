#!/usr/bin/env python3
"""Exercise the poller without D-Bus: print OSD requests as they happen.

    sudo python3 tools/polltest.py [seconds]

Press Fn+F1 / Fn+F4 / Fn+F7 while it runs.
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                '..', 'src', 'daemon'))

from mifs_osd import acpi, poller  # noqa: E402


def main(argv):
    secs = float(argv[1]) if len(argv) > 1 else 60.0

    if not acpi.module_loaded():
        print('acpi_call not loaded; run: modprobe acpi_call')
        return 1

    def on_change(feature, value, icon):
        print('%7.2fs  %-24s = 0x%02x  ->  %s'
              % (time.monotonic() - t0, feature, value, icon), flush=True)

    p = poller.Poller(on_change)
    p.prime()
    print('primed; polling %.0fs. Press Fn+F1 / Fn+F4 / Fn+F7 ...' % secs,
          flush=True)
    t0 = time.monotonic()
    p.run(lambda: time.monotonic() - t0 >= secs)
    print('done')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
