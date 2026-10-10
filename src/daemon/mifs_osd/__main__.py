"""Entry point: poll MIFS in a worker thread, serve OSD signals on the bus.

The poller blocks on /proc/acpi/call I/O, so it runs in its own thread; the
GLib main loop owns the D-Bus connection and must stay in the main thread.
Signals are emitted from the poller thread, which GDBus tolerates, but we
marshal through the main loop anyway so emission order matches observation
order and a slow bus never stalls the sampler.
"""
import logging
import signal
import sys
import threading

from gi.repository import GLib

from . import acpi, dbus_service, poller

log = logging.getLogger('mifs-osd')


def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(name)s: %(message)s')

    if not acpi.module_loaded() and not acpi.load_module():
        log.error('acpi_call unavailable; cannot read MIFS state')
        return 1

    service = dbus_service.Service()
    stop = threading.Event()

    def on_change(feature, value, icon):
        log.info('%s = 0x%02x -> %s', feature, value, icon)
        GLib.idle_add(service.emit_osd, feature, value, icon)

    def worker():
        p = poller.Poller(on_change)
        p.prime()
        log.info('polling MIFS every %.2fs', poller.POLL_INTERVAL)
        p.run(stop.is_set)

    def on_term(_signum, _frame):
        stop.set()
        GLib.idle_add(service._loop.quit)

    signal.signal(signal.SIGTERM, on_term)
    signal.signal(signal.SIGINT, on_term)

    threading.Thread(target=worker, name='poller', daemon=True).start()
    try:
        service.run()
    finally:
        stop.set()
    log.info('stopped')
    return 0


if __name__ == '__main__':
    sys.exit(main())
