"""Entry point for the KDE frontend.

Wiring only: read the settings, then keep three things in step -- the OSD
signal from the root daemon, the settings file, and the renderer. All the
hardware knowledge stays in the daemon, so a bug here can only cost a window,
never a hung desktop.
"""
import argparse
import logging
import os
import signal
import sys

from PyQt6.QtCore import QFileSystemWatcher, QObject, QTimer, pyqtSlot

from . import icons, instance, renderer as renderers
from .config import BACKENDS, CONFIG_PATH, Config

log = logging.getLogger('mifs-osd')

SERVICE = 'org.mechrevo.Mifs'
OBJECT_PATH = '/org/mechrevo/Mifs'
IFACE = 'org.mechrevo.Mifs'

# How long a one-shot --show stays on screen before the process exits.
ONESHOT_MS = 2500


class SettingsWatcher:
    """Watch the settings file, and the directory holding it.

    Both paths are needed. A rewrite in place updates the file but not the
    directory; a replace -- which is how the settings window saves, so that a
    half-written file is never read -- updates the directory but drops the
    watch on the file. Together they cover both ways of saving.
    """

    def __init__(self, path, on_change):
        self.path = path
        self._on_change = on_change
        self._watcher = QFileSystemWatcher()
        self._watcher.fileChanged.connect(on_change)
        self._watcher.directoryChanged.connect(self._on_directory)
        self.refresh()

    def _on_directory(self, _path):
        # The file may have just been replaced; re-attach before the next edit.
        self.refresh()

    def refresh(self):
        wanted = [self.path, os.path.dirname(self.path) or '.']
        watched = self._watcher.files() + self._watcher.directories()
        for path in watched:
            if path not in wanted:
                self._watcher.removePath(path)
        for path in wanted:
            if path not in watched and os.path.exists(path):
                self._watcher.addPath(path)


class OsdReceiver(QObject):
    """Turn the daemon's system-bus signal into a draw.

    QtDBus will only connect a slot that belongs to a QObject and is declared
    as a pyqtSlot, so the handler cannot be a plain nested function.
    """

    def __init__(self, config, osd):
        super().__init__()
        self._config = config
        self._osd = osd

    @pyqtSlot('QVariantMap')
    def on_requested(self, params):
        icon = params.get('icon') or ''
        # Re-resolve geometry on every draw: a resolution or settings change is
        # then picked up without a restart, as in the GNOME frontend.
        self._osd.apply(self._config)
        self._osd.show(icon, params.get('label') or '')
        log.info('%s -> %s', params.get('feature'), icon)


def parse_args(argv):
    parser = argparse.ArgumentParser(
        prog='mifs-osd-kde',
        description='Show an OSD for MECHREVO WUJIE14 Pro Fn-key actions.')
    parser.add_argument('--config', default=CONFIG_PATH,
                        help='settings file (default: %(default)s)')
    parser.add_argument('--backend', choices=BACKENDS,
                        help='override the configured renderer')
    parser.add_argument('--show', metavar='ICON',
                        help='show one icon and exit; for testing')
    parser.add_argument('--list-icons', action='store_true',
                        help='list the icon filenames available')
    return parser.parse_args(argv)


def main(argv=None):
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(name)s: %(message)s')

    args = parse_args(sys.argv[1:] if argv is None else argv)

    if args.list_icons:
        for name in icons.available():
            print(name)
        return 0

    # Settings are plain Python, so they can be read before Qt exists -- which
    # they have to be, because the backend decides how Qt's Wayland platform
    # plugin must be set up. See renderers.prepare_environment.
    config = Config(args.config).reload()
    if args.backend:
        config.backend = args.backend
    try:
        renderers.prepare_environment(config.backend)
    except RuntimeError as exc:
        log.error('%s', exc)
        return 1

    from PyQt6.QtGui import QGuiApplication

    app = QGuiApplication(sys.argv[:1])

    # First run: leave a documented file behind, so the settings are findable
    # rather than living only in this module's defaults.
    if not os.path.exists(config.path):
        config.save()
        log.info('wrote default settings to %s', config.path)

    try:
        osd = renderers.make_renderer(config)
    except RuntimeError as exc:
        log.error('%s', exc)
        return 1

    if args.show:
        osd.apply(config)
        osd.show(args.show)
        QTimer.singleShot(ONESHOT_MS, app.quit)
        try:
            return app.exec()
        finally:
            osd.close()

    # Qt's loop is C++ and does not return to the interpreter on its own, so a
    # Python signal handler would not run until the next Python-level
    # callback. This empty tick gives one the chance to, which is what makes
    # SIGTERM from a logout or a systemd stop take effect promptly.
    signal.signal(signal.SIGTERM, lambda *_: app.quit())
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    tick = QTimer()
    tick.timeout.connect(lambda: None)
    tick.start(200)

    lock = instance.acquire()
    if lock is None:
        log.info('another renderer is already running; exiting')
        return 0

    seen_trigger = config.preview_trigger

    def on_settings_changed(_path):
        nonlocal seen_trigger
        config.reload()
        osd.apply(config)
        # The settings window has no way to talk to this process, so a preview
        # request arrives as a bumped counter in the file -- the same trick the
        # GNOME frontend uses with its preview-trigger key.
        if config.preview_trigger != seen_trigger:
            seen_trigger = config.preview_trigger
            log.info('preview: %s', config.preview_icon)
            osd.show(config.preview_icon)
        else:
            # Dragging the icon in the settings window writes the file on
            # every step, so this is debug level: it is expected traffic, not
            # news.
            log.debug('settings reloaded')

    watcher = SettingsWatcher(config.path, on_settings_changed)

    from PyQt6.QtDBus import QDBusConnection

    receiver = OsdReceiver(config, osd)
    bus = QDBusConnection.systemBus()
    if not bus.connect(SERVICE, OBJECT_PATH, IFACE, 'OsdRequested',
                       receiver.on_requested):
        log.error('cannot subscribe to %s on the system bus', IFACE)
        return 1

    log.info('watching for OSD requests (backend=%s)', config.backend)
    try:
        return app.exec()
    finally:
        # Orderly, while the QML engine's context is still alive. See
        # LayerShellRenderer.close for what goes wrong otherwise.
        osd.close()


if __name__ == '__main__':
    sys.exit(main())
