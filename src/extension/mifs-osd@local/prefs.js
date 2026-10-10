// Preferences for the MIFS OSD extension.
//
// Two kinds of preview, because they answer different questions:
//   - the thumbnail at the top shows where the icon lands relative to the
//     screen, and the icon can be dragged around it;
//   - the button fires the real OSD so you can judge size and contrast
//     against whatever is actually on screen.
//
// The thumbnail is drawn to the monitor's aspect ratio, and edits are stored
// as fractions, so nothing here depends on the current resolution.

import Adw from 'gi://Adw';
import Gdk from 'gi://Gdk';
import Gio from 'gi://Gio';
import Gtk from 'gi://Gtk';

import {ExtensionPreferences} from 'resource:///org/gnome/Shell/Extensions/js/extensions/prefs.js';

// Icons the daemon can ask for, as (file, label) pairs for the picker.
const PREVIEW_ICONS = [
    ['SystemPerfMode_2.png', 'Performance mode'],
    ['SystemPerfMode_1.png', 'Balanced mode'],
    ['SystemPerfMode_0.png', 'Quiet mode'],
    ['TouchPad_ON.png', 'Touchpad on'],
    ['TouchPad_OFF.png', 'Touchpad off'],
    ['Fn_ON.png', 'Fn lock on'],
    ['Fn_OFF.png', 'Fn lock off'],
    ['RGBKeyboardBrightnessLevel_0.png', 'Backlight level 0'],
    ['RGBKeyboardBrightnessLevel_1.png', 'Backlight level 1'],
    ['RGBKeyboardBrightnessLevel_2.png', 'Backlight level 2'],
    ['RGBKeyboardBrightnessLevel_3.png', 'Backlight level 3'],
];

// The thumbnail is a stand-in for the screen; keep it a sensible size and
// let it keep the monitor's shape.
const THUMB_WIDTH = 320;

export default class MifsOsdPreferences extends ExtensionPreferences {
    fillPreferencesWindow(window) {
        this._settings = this.getSettings();
        this._iconDir = `${this.path}/icons`;

        window.add(this._buildPositionPage());
        window.add(this._buildIconPage());

        window.search_enabled = true;
    }

    // -- page: position ---------------------------------------------------

    _buildPositionPage() {
        const page = new Adw.PreferencesPage({
            title: 'Position',
            icon_name: 'mark-location-symbolic',
        });

        const group = new Adw.PreferencesGroup({
            title: 'Placement',
            description: 'Where the icon appears, as a fraction of the ' +
                'screen. Fractions keep the layout correct on any display.',
        });
        page.add(group);

        group.add(this._buildPreviewThumbnail());

        // Position mode
        const modeRow = new Adw.ComboRow({
            title: 'Position mode',
            subtitle: 'Fraction places the icon anywhere; margin keeps it ' +
                'centred just above the bottom edge',
            model: Gtk.StringList.new(['Fraction of screen', 'Margin from bottom']),
        });
        modeRow.selected =
            this._settings.get_string('position-mode') === 'margin' ? 1 : 0;
        modeRow.connect('notify::selected', () => {
            this._settings.set_string('position-mode',
                modeRow.selected === 1 ? 'margin' : 'percent');
            this._syncRows();
        });
        group.add(modeRow);
        this._modeRow = modeRow;

        // X / Y as percentages. The stored value is a 0..1 fraction, so
        // asPercent makes the slider read 0..100 while storing the fraction.
        this._xRow = this._buildScaleRow(
            'Horizontal', 'x-percent', 0, 100, '%', true);
        this._yRow = this._buildScaleRow(
            'Vertical', 'y-percent', 0, 100, '%', true);
        group.add(this._xRow);
        group.add(this._yRow);

        // Margin from bottom
        this._marginRow = this._buildSpinRow(
            'Gap above bottom edge', 'bottom-margin', 0, 2000, 'px',
            'Distance between the icon and the bottom of the screen');
        group.add(this._marginRow);

        this._syncRows();
        return page;
    }

    // A miniature of the screen with a draggable icon on it.
    _buildPreviewThumbnail() {
        const monitor = Gdk.Display.get_default()?.get_monitors().get_item(0);
        const ratio = monitor ? monitor.get_geometry().height /
            monitor.get_geometry().width : 9 / 16;
        const thumbHeight = Math.round(THUMB_WIDTH * ratio);

        this._thumb = new Gtk.DrawingArea({
            width_request: THUMB_WIDTH,
            height_request: thumbHeight,
            hexpand: false,
        });
        this._thumb.set_draw_func((area, cr, w, h) =>
            this._drawThumbnail(cr, w, h));

        // Dragging inside the thumbnail moves the icon. The grab offset is
        // captured on drag-begin and applied to the stored position on each
        // update, so the icon follows the pointer instead of jumping.
        const drag = new Gtk.GestureDrag();
        drag.connect('drag-begin', (_g, startX, startY) => {
            this._grabDx = startX - this._settings.get_double('x-percent') *
                this._thumb.get_width();
            this._grabDy = startY - this._settings.get_double('y-percent') *
                this._thumb.get_height();
        });
        drag.connect('drag-update', (_g, offX, offY) => {
            const w = this._thumb.get_width();
            const h = this._thumb.get_height();
            if (w <= 0 || h <= 0)
                return;
            const x = Math.min(Math.max(this._grabDx + offX, 0), w);
            const y = Math.min(Math.max(this._grabDy + offY, 0), h);
            this._settings.set_double('x-percent', x / w);
            this._settings.set_double('y-percent', y / h);
        });
        this._thumb.add_controller(drag);

        // Repaint whenever anything relevant changes.
        this._settings.connect('changed', () => this._thumb.queue_draw());

        const box = new Adw.PreferencesRow({
            activatable: false,
            selectable: false,
        });
        const inner = new Gtk.Box({
            orientation: Gtk.Orientation.VERTICAL,
            spacing: 8,
            margin_top: 12,
            margin_bottom: 12,
        });
        inner.append(new Gtk.Label({
            label: 'Drag the icon to set its position',
            xalign: 0,
        }));
        inner.append(this._thumb);
        box.set_child(inner);
        return box;
    }

    _drawThumbnail(cr, w, h) {
        // Screen background
        cr.setSourceRGB(0.15, 0.15, 0.18);
        cr.rectangle(0, 0, w, h);
        cr.fill();

        // Where the icon will land, using the same maths as the extension.
        const mode = this._settings.get_string('position-mode');
        const sizePct = this._settings.get_double('size-percent');
        const side = Math.max(6, Math.round(w * sizePct));

        let cx;
        let cy;
        if (mode === 'margin') {
            const marginFrac = this._settings.get_int('bottom-margin') / 1080;
            cx = w / 2;
            cy = h - side / 2 - marginFrac * h;
        } else {
            cx = w * this._settings.get_double('x-percent');
            cy = h * this._settings.get_double('y-percent');
        }

        // Icon placeholder
        cr.setSourceRGB(0.95, 0.95, 0.95);
        cr.rectangle(Math.round(cx - side / 2), Math.round(cy - side / 2),
                     side, side);
        cr.fill();

        // Crosshair through the centre
        cr.setSourceRGBA(1, 1, 1, 0.35);
        cr.setLineWidth(1);
        cr.moveTo(cx, 0); cr.lineTo(cx, h);
        cr.moveTo(0, cy); cr.lineTo(w, cy);
        cr.stroke();
    }

    // -- page: icon -------------------------------------------------------

    _buildIconPage() {
        const page = new Adw.PreferencesPage({
            title: 'Icon',
            icon_name: 'image-x-generic-symbolic',
        });

        const group = new Adw.PreferencesGroup({
            title: 'Size',
            description: 'Icon width as a fraction of the screen width, so ' +
                'it looks the same on any display.',
        });
        page.add(group);

        this._sizeRow = this._buildScaleRow(
            'Size', 'size-percent', 3, 40, '%', /* asPercent */ true);
        group.add(this._sizeRow);

        const previewGroup = new Adw.PreferencesGroup({title: 'Preview'});
        page.add(previewGroup);

        // Which icon the previews use
        const names = PREVIEW_ICONS.map(([, label]) => label);
        const iconRow = new Adw.ComboRow({
            title: 'Icon to preview',
            model: Gtk.StringList.new(names),
        });
        const current = this._settings.get_string('preview-icon');
        iconRow.selected = Math.max(
            0, PREVIEW_ICONS.findIndex(([file]) => file === current));
        iconRow.connect('notify::selected', () => {
            this._settings.set_string('preview-icon',
                PREVIEW_ICONS[iconRow.selected][0]);
        });
        previewGroup.add(iconRow);

        // Fire the real OSD so size and contrast can be judged in situ.
        const showRow = new Adw.ActionRow({
            title: 'Show on screen',
            subtitle: 'Draws the icon on the real screen for 1.5 seconds',
        });
        const button = new Gtk.Button({
            label: 'Show',
            valign: Gtk.Align.CENTER,
        });
        button.add_css_class('suggested-action');
        button.connect('clicked', () => {
            // Bump a counter; the extension watches it and draws once.
            this._settings.set_int('preview-trigger',
                this._settings.get_int('preview-trigger') + 1);
        });
        showRow.add_suffix(button);
        showRow.activatable_widget = button;
        previewGroup.add(showRow);

        return page;
    }

    // -- row builders -----------------------------------------------------

    // A slider shown as a percentage. `asPercent` scales the stored double
    // by 100 (size-percent is stored as 0.13, shown as 13%).
    _buildScaleRow(title, key, min, max, suffix, asPercent = false) {
        const scale = asPercent ? 100 : 1;
        const row = new Adw.ActionRow({title});
        const slider = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, min, max, 1);
        slider.set_size_request(220, -1);
        slider.set_draw_value(true);
        slider.set_value_pos(Gtk.PositionType.RIGHT);
        slider.set_value(this._settings.get_double(key) * scale);
        slider.set_format_value_func((_s, v) => `${Math.round(v)}${suffix}`);
        slider.connect('value-changed', () => {
            this._settings.set_double(key, slider.get_value() / scale);
        });
        // Keep the slider in step when the value is changed from elsewhere
        // (dragging the thumbnail writes the same keys).
        this._settings.connect(`changed::${key}`, () => {
            const v = this._settings.get_double(key) * scale;
            if (Math.abs(slider.get_value() - v) > 0.01)
                slider.set_value(v);
        });
        row.add_suffix(slider);
        row.set_activatable_widget(slider);
        row._slider = slider;
        row._scale = scale;
        return row;
    }

    _buildSpinRow(title, key, min, max, suffix, subtitle) {
        const row = new Adw.SpinRow({
            title,
            subtitle,
            adjustment: new Gtk.Adjustment({
                lower: min,
                upper: max,
                step_increment: 10,
                page_increment: 50,
            }),
        });
        row.set_value(this._settings.get_int(key));
        row.connect('notify::value', () => {
            this._settings.set_int(key, row.get_value());
        });
        return row;
    }

    // Show only the rows that apply to the selected position mode.
    _syncRows() {
        const margin = this._settings.get_string('position-mode') === 'margin';
        this._xRow.visible = !margin;
        this._yRow.visible = !margin;
        this._marginRow.visible = margin;
        this._thumb?.queue_draw();
    }
}
