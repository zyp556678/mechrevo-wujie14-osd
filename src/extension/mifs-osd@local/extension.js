// MIFS Fn-key OSD — shows an icon overlay when the daemon reports a change.
//
// The daemon (org.mechrevo.Mifs on the system bus) owns all the hardware
// knowledge; this extension only draws. Keeping it that way means a bug here
// cannot hang the shell for longer than one redraw.
//
// Layering: Main.uiGroup sits above every window, so the actor needs no
// window management at all. Non-reactive and unfocusable gives click-through
// and keeps keyboard focus where the user left it.
//
// Geometry is stored as fractions of the monitor rather than pixels, so the
// same settings look right on the built-in panel and on an external display
// of a different resolution.

import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

const BUS_NAME = 'org.mechrevo.Mifs';
const OBJECT_PATH = '/org/mechrevo/Mifs';
const IFACE = 'org.mechrevo.Mifs';

const HOLD_MS = 1500;   // matches the vendor tool
const FADE_IN_MS = 120;
const FADE_OUT_MS = 250;

export default class MifsOsdExtension extends Extension {
    enable() {
        this._timeoutId = 0;
        this._subId = 0;
        this._settingsId = 0;
        this._settings = this.getSettings();

        // Derive the icon directory from this module's own URL. Avoid
        // GLib.build_filenamev and Extension.path here: both have changed
        // behaviour across shell releases and reject each other's types.
        const moduleDir = Gio.File.new_for_uri(import.meta.url)
            .get_parent().get_path();
        this._iconsDir = `${moduleDir}/icons`;

        this._icon = new St.Icon();
        this._actor = new St.Bin({
            style_class: 'mifs-osd',
            reactive: false,
            can_focus: false,
            child: this._icon,
        });
        Main.uiGroup.add_child(this._actor);
        this._actor.hide();

        this._settingsId = this._settings.connect('changed', (settings, key) => {
            // The preferences window is a separate process, so a preview
            // request arrives as a bumped counter rather than a method call.
            if (key === 'preview-trigger') {
                this._show(settings.get_string('preview-icon'));
                return;
            }
            if (this._actor.visible)
                this._applyGeometry();
        });

        // sender must be null, not BUS_NAME. Signals from the daemon carry
        // its unique name (":1.x") as sender, and matching on the well-known
        // name fails to resolve in that direction. The interface, path and
        // member below are specific enough to filter on.
        this._subId = Gio.DBus.system.signal_subscribe(
            null, IFACE, 'OsdRequested', OBJECT_PATH, null,
            Gio.DBusSignalFlags.NONE,
            (_conn, _sender, _path, _iface, _signal, params) => {
                try {
                    // deepUnpack() gives the dict but leaves each a{sv} value
                    // as a Variant, so unpack them explicitly. Plain unpack()
                    // is worse: it does not recurse and yields undefined.
                    const [dict] = params.deepUnpack();
                    this._show(dict.icon.unpack());
                } catch (e) {
                    logError(e, 'mifs-osd: bad signal payload');
                }
            });
    }

    // -- geometry ---------------------------------------------------------

    // Resolve the configured size and position against the current monitor.
    // Called on every draw so a resolution or settings change is picked up
    // without a restart.
    _applyGeometry() {
        const monitor = Main.layoutManager.primaryMonitor;
        const size = Math.round(
            monitor.width * this._settings.get_double('size-percent'));
        const sizeClamped = Math.max(24, Math.min(size, monitor.width,
                                                  monitor.height));

        this._icon.icon_size = sizeClamped;
        this._actor.set_size(sizeClamped, sizeClamped);

        let x;
        let y;
        if (this._settings.get_string('position-mode') === 'margin') {
            // Horizontally centred, lifted off the bottom edge so it clears
            // the dock.
            x = monitor.x + Math.floor((monitor.width - sizeClamped) / 2);
            y = monitor.y + monitor.height - sizeClamped -
                this._settings.get_int('bottom-margin');
        } else {
            // Centre the icon on the configured fraction of the screen.
            const cx = monitor.x + monitor.width *
                this._settings.get_double('x-percent');
            const cy = monitor.y + monitor.height *
                this._settings.get_double('y-percent');
            x = Math.round(cx - sizeClamped / 2);
            y = Math.round(cy - sizeClamped / 2);
        }

        this._actor.set_position(x, y);
        return sizeClamped;
    }

    // -- drawing ----------------------------------------------------------

    _show(iconFile) {
        const file = Gio.File.new_for_path(`${this._iconsDir}/${iconFile}`);
        if (!file.query_exists(null)) {
            logError(new Error(`icon not found: ${file.get_path()}`),
                     'mifs-osd');
            return;
        }
        this._icon.gicon = new Gio.FileIcon({file});
        this._applyGeometry();

        this._actor.remove_all_transitions();
        if (!this._actor.visible) {
            this._actor.opacity = 0;
            this._actor.show();
        }
        this._actor.ease({
            opacity: 255,
            duration: FADE_IN_MS,
            mode: Clutter.AnimationMode.EASE_OUT_QUAD,
        });

        if (this._timeoutId)
            GLib.source_remove(this._timeoutId);
        this._timeoutId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, HOLD_MS, () => {
            this._timeoutId = 0;
            this._actor.ease({
                opacity: 0,
                duration: FADE_OUT_MS,
                mode: Clutter.AnimationMode.EASE_IN_QUAD,
                onComplete: () => this._actor.hide(),
            });
            return GLib.SOURCE_REMOVE;
        });
    }

    disable() {
        if (this._timeoutId) {
            GLib.source_remove(this._timeoutId);
            this._timeoutId = 0;
        }
        if (this._subId) {
            Gio.DBus.system.signal_unsubscribe(this._subId);
            this._subId = 0;
        }
        if (this._settingsId && this._settings) {
            this._settings.disconnect(this._settingsId);
            this._settingsId = 0;
        }
        this._settings = null;
        this._actor?.destroy();
        this._actor = null;
        this._icon = null;
    }
}
