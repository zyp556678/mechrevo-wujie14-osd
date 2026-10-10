#!/usr/bin/env python3
"""End-to-end test: poller -> mapper -> D-Bus signal -> subscriber.

Exercises the whole chain except the shell extension, on the session bus so
no root-owned policy file is needed.

    MIFS_OSD_SESSION_BUS=1 sudo -E python3 tools/e2etest.py [seconds]

Press Fn+F1 / Fn+F4 / Fn+F7 while it runs.
"""
import os
import sys
import threading

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                '..', 'src', 'daemon'))

os.environ.setdefault('MIFS_OSD_SESSION_BUS', '1')

from gi.repository import Gio, GLib  # noqa: E402

from mifs_osd import acpi, dbus_service, poller  # noqa: E402


def main(argv):
    secs = float(argv[1]) if len(argv) > 1 else 60.0

    if not acpi.module_loaded():
        print('acpi_call not loaded; run: modprobe acpi_call')
        return 1

    svc = dbus_service.Service()
    stop = threading.Event()
    seen = []

    def on_change(feature, value, icon):
        print('  change  %-22s = 0x%02x -> %s' % (feature, value, icon),
              flush=True)
        GLib.idle_add(svc.emit_osd, feature, value, icon)

    def on_signal(_c, _s, _p, _i, _sig, params):
        d = params.unpack()[0]
        seen.append(d)
        print('  SIGNAL  %-22s value=%d  icon=%s'
              % (d['feature'], d['value'], d['icon']), flush=True)

    def worker():
        p = poller.Poller(on_change)
        p.prime()
        p.run(stop.is_set)

    def finish():
        stop.set()
        GLib.idle_add(svc._loop.quit)

    # Subscribe once the name is owned. Service stores the connection in
    # _on_bus_acquired; wrap the bound method so it still runs.
    original_acquired = svc._on_bus_acquired

    def acquired(conn, name):
        original_acquired(conn, name)
        bus = Gio.bus_get_sync(dbus_service._bus_type(), None)
        bus.signal_subscribe(dbus_service.BUS_NAME, dbus_service.IFACE,
                             'OsdRequested', dbus_service.OBJECT_PATH, None,
                             Gio.DBusSignalFlags.NONE, on_signal)

    svc._on_bus_acquired = acquired

    threading.Thread(target=worker, daemon=True).start()
    GLib.timeout_add(int(secs * 1000), finish)
    print('running %.0fs — press Fn+F1 / Fn+F4 / Fn+F7 ...' % secs, flush=True)
    svc.run()
    print('done; %d signal(s) received' % len(seen))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
