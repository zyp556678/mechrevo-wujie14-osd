"""Two ways to get an OSD onto a Plasma screen.

LayerShellRenderer draws it ourselves on a ``zwlr_layer_shell_v1`` surface.
That is the default because it is the only way to control where the icon goes
and how big it is -- KWin honours the protocol, so an ordinary process can sit
above every window without patching the compositor. It is also why the KDE
frontend is a program rather than a Plasmoid: a Plasmoid is drawn inside
plasmashell's own window and cannot cover other applications.

PlasmaRenderer hands the job to plasmashell's existing OSD service instead.
Nothing is configurable that way -- position, size and duration all belong to
plasmashell -- but it needs no layer-shell support at all, which makes it a
useful fallback if the default ever stops drawing on some screen or driver.

Only the layer-shell backend needs the environment below, and it must be set
before QGuiApplication exists: Qt's Wayland platform plugin reads it while
initialising, and a window created with the default integration silently
ignores every anchor it is given.
"""
import logging
import os
from pathlib import Path

from PyQt6.QtCore import (QCoreApplication, QEvent, QObject, QUrl,
                          pyqtProperty, pyqtSignal)

from . import geometry, icons

log = logging.getLogger(__name__)

SHELL_INTEGRATION_VAR = 'QT_WAYLAND_SHELL_INTEGRATION'
SHELL_INTEGRATION = 'layer-shell'

QML_FILE = Path(__file__).with_name('osd.qml')

# plasmashell's OSD service, verified live with busctl.
PLASMA_SERVICE = 'org.kde.plasmashell'
PLASMA_PATH = '/org/kde/osdService'
PLASMA_IFACE = 'org.kde.osdService'


def prepare_environment(backend):
    """Make the platform plugin pick the right shell integration.

    Called before QGuiApplication is built. It is process-wide, which is the
    reason the settings window is a separate program: it needs ordinary
    windows, and a process cannot have both.
    """
    if backend != 'layer-shell':
        return

    # Mutter does not implement zwlr_layer_shell_v1, so the surface would fail
    # to materialise and Qt would report it as an opaque protocol error. The
    # autostart entry already skips GNOME; this catches a manual launch.
    if 'GNOME' in os.environ.get('XDG_CURRENT_DESKTOP', '').upper():
        raise RuntimeError(
            'the layer-shell backend needs a compositor with '
            'zwlr_layer_shell_v1, which GNOME Shell does not have; use the '
            'GNOME extension there, or run with --backend plasma')

    os.environ.setdefault('QT_QPA_PLATFORM', 'wayland')
    os.environ[SHELL_INTEGRATION_VAR] = SHELL_INTEGRATION


class OsdState(QObject):
    """Everything the QML surface binds to.

    Kept in one property rather than a dozen pyqtProperty declarations: QML
    re-evaluates every binding when `state` changes, and that is exactly the
    granularity needed -- an OSD updates a few times a second at most.

    `shown` is a second signal on purpose. Its handler restarts the fade
    animation, and it has to run *after* QML has picked up the new icon, or
    the OSD fades in whatever was on screen last time. Emitting `changed`
    first guarantees that, because binding updates are synchronous; relying on
    the two handlers being connected in the right order would not.
    """

    changed = pyqtSignal()
    shown = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.icon_source = ''
        self.size = 0
        self.anchor_left = True
        self.anchor_top = True
        self.margin_left = 0
        self.margin_right = 0
        self.margin_top = 0
        self.margin_bottom = 0

    @pyqtProperty('QVariantMap', notify=changed)
    def state(self):
        return {
            'iconSource': self.icon_source,
            'size': self.size,
            'anchorLeft': self.anchor_left,
            'anchorTop': self.anchor_top,
            'marginLeft': self.margin_left,
            'marginRight': self.margin_right,
            'marginTop': self.margin_top,
            'marginBottom': self.margin_bottom,
        }


class LayerShellRenderer:
    """Draw the OSD on a layer-shell surface."""

    def __init__(self, config):
        from PyQt6.QtGui import QGuiApplication
        from PyQt6.QtQml import QQmlApplicationEngine

        self._config = config
        self._state = OsdState()
        self._app = QGuiApplication.instance()

        # Geometry first, QML second. The layer surface is created while the
        # component loads, and layer-shell rejects a zero-sized surface unless
        # it is anchored to both edges -- so the window has to know its size
        # before it exists, not be corrected afterwards.
        self.apply(config)

        self._engine = QQmlApplicationEngine()
        self._engine.rootContext().setContextProperty('osd', self._state)
        self._engine.load(QUrl.fromLocalFile(str(QML_FILE)))
        if not self._engine.rootObjects():
            raise RuntimeError('could not load %s' % QML_FILE)

    def apply(self, config):
        """Re-resolve size and position against the current screen.

        Called on every draw as well as on a settings change, so a resolution
        change does not need a restart. Same policy as the GNOME frontend.
        """
        self._config = config
        screen = self._app.primaryScreen()
        area = screen.geometry()
        place = geometry.placement(config, area.width(), area.height())
        pin = geometry.anchors(place, area.width(), area.height())

        self._state.size = place.size
        self._state.anchor_left = pin.left
        self._state.anchor_top = pin.top
        self._state.margin_left = pin.margin_left
        self._state.margin_right = pin.margin_right
        self._state.margin_top = pin.margin_top
        self._state.margin_bottom = pin.margin_bottom
        self._state.changed.emit()

    def show(self, icon_name, label=''):
        # `label` is accepted and dropped: the artwork already says which mode
        # the machine is in, and the vendor's Windows OSD drew no text either.
        # The signature is shared so the caller stays backend-agnostic.
        path = icons.resolve(icon_name)
        if path is None:
            log.warning('icon not found: %s', icon_name)
            return
        self._state.icon_source = QUrl.fromLocalFile(path).toString()
        self._state.changed.emit()
        self._state.shown.emit()

    def close(self):
        """Tear the window down while the engine's context is still valid.

        Qt destroys a QML engine's context before the objects bound to it, so
        letting the interpreter drop everything at exit makes every binding
        re-evaluate against a dead context -- one TypeError per property, on
        the way out of a perfectly healthy process. Deleting the root object
        first, and forcing the deferred delete to run now rather than at some
        later event loop turn that will never come, keeps the shutdown quiet.
        """
        for root in self._engine.rootObjects():
            root.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


class PlasmaRenderer:
    """Hand the OSD to plasmashell, which owns position, size and timing."""

    def __init__(self, config):
        from PyQt6.QtDBus import QDBusConnection

        self._config = config
        self._bus = QDBusConnection.sessionBus()

    def apply(self, config):
        self._config = config

    def show(self, icon_name, label=''):
        from PyQt6.QtDBus import QDBus, QDBusMessage

        path = icons.resolve(icon_name)
        if path is None:
            log.warning('icon not found: %s', icon_name)
            return

        message = QDBusMessage.createMethodCall(
            PLASMA_SERVICE, PLASMA_PATH, PLASMA_IFACE, 'showText')
        message.setArguments([path, label])
        # NoBlock: send and move on. plasmashell does not validate its
        # arguments -- a bad path is dropped in silence and the call still
        # succeeds -- so there is nothing a reply could tell us. Whether an
        # icon appears is the only signal that matters.
        self._bus.call(message, QDBus.CallMode.NoBlock)

    def close(self):
        """Nothing to tear down: plasmashell owns the window, not us."""


def make_renderer(config):
    if config.backend == 'plasma':
        return PlasmaRenderer(config)
    return LayerShellRenderer(config)
