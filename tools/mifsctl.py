#!/usr/bin/env python3
"""Development CLI for the MIFS interface.

    mifsctl list                 show polled features and their current values
    mifsctl get <Feature>        read one feature
    mifsctl set <Feature> <int>  write one feature
    mifsctl raw <32 hex bytes>   send an arbitrary buffer (debugging only)

Needs root, because /proc/acpi/call is root-only.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                '..', 'src', 'daemon'))

from mifs_osd import acpi, features  # noqa: E402


def cmd_list():
    if not acpi.module_loaded():
        print('acpi_call not loaded; run: modprobe acpi_call')
        return 1
    print('%-24s %-8s %s' % ('feature', 'value', 'name'))
    print('-' * 52)
    for name in features.POLLED:
        val = acpi.get(name)
        if val is None:
            print('%-24s %-8s %s' % (name, '-', 'unsupported'))
        else:
            print('%-24s 0x%02x     %s'
                  % (name, val, features.VALUE_NAMES[name].get(val, '?')))
    return 0


def cmd_get(name):
    if name not in features.POLLED:
        print('unknown feature: %s' % name)
        print('known: %s' % ', '.join(features.POLLED))
        return 2
    val = acpi.get(name)
    if val is None:
        print('%s: unsupported on this machine' % name)
        return 1
    print('%s = 0x%02x (%s)'
          % (name, val, features.VALUE_NAMES[name].get(val, '?')))
    return 0


def cmd_set(name, raw_value):
    if name not in features.POLLED:
        print('unknown feature: %s' % name)
        return 2
    try:
        value = int(raw_value, 0)
    except ValueError:
        print('value must be an integer: %r' % raw_value)
        return 2
    ok = acpi.set_value(name, value)
    print('%s <- 0x%02x: %s' % (name, value, 'ok' if ok else 'FAILED'))
    if ok:
        print('read back: 0x%02x' % (acpi.get(name) or 0))
    return 0 if ok else 1


def cmd_raw(hex_bytes):
    if len(hex_bytes) != acpi.BUF_LEN:
        print('need exactly %d bytes, got %d' % (acpi.BUF_LEN, len(hex_bytes)))
        return 2
    reply = acpi.call(bytes(hex_bytes))
    print('reply: {%s}' % ', '.join('0x%02x' % b for b in reply))
    return 0


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    cmd = argv[1]
    if cmd == 'list':
        return cmd_list()
    if cmd == 'get' and len(argv) == 3:
        return cmd_get(argv[2])
    if cmd == 'set' and len(argv) == 4:
        return cmd_set(argv[2], argv[3])
    if cmd == 'raw' and len(argv) == 3:
        try:
            data = bytes(int(b, 16) for b in argv[2].split())
        except ValueError:
            print('raw needs space-separated hex bytes')
            return 2
        return cmd_raw(data)
    print(__doc__)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv))
