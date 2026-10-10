"""D-Bus service that turns poller events into OSD signals.

Runs on the system bus: the daemon needs root for /proc/acpi/call, and a
system service is the natural home for that. The GNOME Shell extension runs
in the user session and subscribes to the OsdRequested signal.
"""
import logging
import os

import gi

gi.require_version('Gio', '2.0')
from gi.repository import Gio, GLib  # noqa: E402

from . import acpi, features

log = logging.getLogger(__name__)

BUS_NAME = 'org.mechrevo.Mifs'
OBJECT_PATH = '/org/mechrevo/Mifs'
IFACE = 'org.mechrevo.Mifs'

# Testing hook: set MIFS_OSD_SESSION_BUS=1 to use the session bus, so the
# daemon can be exercised without installing the root-owned system policy.
_USE_SESSION_BUS = os.environ.get('MIFS_OSD_SESSION_BUS') == '1'


def _bus_type():
    return Gio.BusType.SESSION if _USE_SESSION_BUS else Gio.BusType.SYSTEM

IFACE_XML = """
<node>
  <interface name="org.mechrevo.Mifs">
    <method name="GetState">
      <arg type="s" name="name" direction="in"/>
      <arg type="a{sv}" name="state" direction="out"/>
    </method>
    <method name="ListFeatures">
      <arg type="as" name="names" direction="out"/>
    </method>
    <signal name="OsdRequested">
      <arg type="a{sv}" name="params"/>
    </signal>
  </interface>
</node>
"""


class Service:
    def __init__(self):
        self._conn = None
        self._node_info = Gio.DBusNodeInfo.new_for_xml(IFACE_XML)
        self._loop = GLib.MainLoop()

    # -- bus plumbing ----------------------------------------------------
    def _on_bus_acquired(self, conn, _name):
        self._conn = conn
        conn.register_object(OBJECT_PATH, self._node_info.interfaces[0],
                             self._handle_method, None, None)
        log.info('acquired %s on the system bus', BUS_NAME)

    def _handle_method(self, _conn, _sender, _path, _iface, method, params,
                       invocation):
        if method == 'GetState':
            name = params.unpack()[0]
            value = acpi.get(name) if name in features.POLLED else None
            result = {}
            if value is not None:
                result['name'] = GLib.Variant('s', name)
                result['value'] = GLib.Variant('y', value)
                result['label'] = GLib.Variant(
                    's', features.VALUE_NAMES[name].get(value, '?'))
            invocation.return_value(
                GLib.Variant('(a{sv})', (result,)))
        elif method == 'ListFeatures':
            invocation.return_value(
                GLib.Variant('(as)', (list(features.POLLED),)))
        else:
            invocation.return_error_literal(
                Gio.DBusError, Gio.DBusError.UNKNOWN_METHOD, method)

    # -- outbound --------------------------------------------------------
    def emit_osd(self, feature, value, icon):
        """Ask the shell to show an OSD for this feature value."""
        if self._conn is None:
            log.warning('no bus connection; dropping OSD for %s', feature)
            return
        params = {
            'feature': GLib.Variant('s', feature),
            'value': GLib.Variant('y', value),
            'icon': GLib.Variant('s', icon),
            'label': GLib.Variant(
                's', features.VALUE_NAMES.get(feature, {}).get(value, '')),
        }
        try:
            self._conn.emit_signal(None, OBJECT_PATH, IFACE, 'OsdRequested',
                                   GLib.Variant('(a{sv})', (params,)))
        except GLib.Error as exc:
            log.warning('failed to emit OSD signal: %s', exc)

    # -- lifecycle -------------------------------------------------------
    def run(self):
        Gio.bus_own_name(_bus_type(), BUS_NAME,
                         Gio.BusNameOwnerFlags.NONE,
                         self._on_bus_acquired, None, None)
        self._loop.run()
