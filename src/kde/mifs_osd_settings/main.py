"""Settings window for the KDE frontend.

A separate program from the renderer rather than a mode of it: the renderer
sets QT_WAYLAND_SHELL_INTEGRATION so that every window it creates becomes a
layer-shell surface, and a settings window must be an ordinary window. The two
never talk directly -- writing the settings file is enough, because the
renderer watches it.

Two kinds of preview, matching the GNOME frontend, because they answer
different questions: the thumbnail shows where the icon lands relative to the
screen, and the button draws the real OSD so size and contrast can be judged
against whatever is actually behind it.
"""
import copy
import shutil
import sys
from pathlib import Path

from PyQt6.QtCore import QProcess, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QGuiApplication, QIcon, QPainter, QPen
from PyQt6.QtWidgets import (
    QApplication, QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
    QMessageBox, QPushButton, QSlider, QSpinBox, QVBoxLayout, QWidget)

from mifs_osd_kde import geometry, icons, instance
from mifs_osd_kde.config import MAX_SIZE_PERCENT, MIN_SIZE_PERCENT, Config

# (file, label) for the picker. Only the icons a user can actually trigger are
# worth offering; the ambient-light and CapsLock artwork is unused on Linux.
PREVIEW_ICONS = [
    ('SystemPerfMode_2.png', '性能模式'),
    ('SystemPerfMode_1.png', '均衡模式'),
    ('SystemPerfMode_0.png', '静音模式'),
    ('TouchPad_ON.png', '触控板开'),
    ('TouchPad_OFF.png', '触控板关'),
    ('Fn_ON.png', 'Fn 锁开'),
    ('Fn_OFF.png', 'Fn 锁关'),
    ('RGBKeyboardBrightnessLevel_0.png', '键盘背光 0'),
    ('RGBKeyboardBrightnessLevel_1.png', '键盘背光 1'),
    ('RGBKeyboardBrightnessLevel_2.png', '键盘背光 2'),
    ('RGBKeyboardBrightnessLevel_3.png', '键盘背光 3'),
]

BACKEND_LABELS = [
    ('layer-shell', '自绘（可调位置与大小）'),
    ('plasma', '系统 OSD（位置大小不可调）'),
]

THUMB_WIDTH = 320

# How often the renderer's status is re-checked. Cheap enough to poll: it is
# one open, one flock and one close.
STATUS_POLL_MS = 2000


def launch_command():
    """How to start a renderer, preferring the installed entry point.

    Falls back to this interpreter with the package path injected, so a
    checkout works too -- the renderer package sits next to this one.
    """
    installed = shutil.which('mifs-osd-kde')
    if installed:
        return installed, []
    parent = str(Path(__file__).resolve().parents[1])
    code = ('import sys; sys.path.insert(0, %r); '
            'from mifs_osd_kde.__main__ import main; sys.exit(main())'
            % parent)
    return sys.executable, ['-c', code]


class ScreenThumb(QWidget):
    """A miniature of the screen with a draggable icon on it."""

    moved = pyqtSignal(float, float)

    def __init__(self, config):
        super().__init__()
        self._config = config
        screen = QGuiApplication.primaryScreen().geometry()
        self._screen_w = max(1, screen.width())
        self._screen_h = max(1, screen.height())
        self._height_px = round(THUMB_WIDTH * self._screen_h / self._screen_w)
        self._dragging = False
        self._grab_dx = 0.0
        self._grab_dy = 0.0
        self.setFixedSize(THUMB_WIDTH, self._height_px)

    def set_config(self, config):
        self._config = config
        self.update()

    def _place(self):
        """Placement for the thumbnail, using the renderer's own maths.

        The bottom margin is in real pixels, so it is scaled to the thumbnail;
        everything else is already a fraction and needs no adjusting. Sharing
        geometry.placement means the preview cannot drift from the real thing.
        """
        scaled = copy.copy(self._config)
        scaled.bottom_margin = round(
            self._config.bottom_margin * self.height() / self._screen_h)
        return geometry.placement(scaled, self.width(), self.height())

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(38, 38, 46))

        place = self._place()
        painter.fillRect(place.x, place.y, place.size, place.size,
                         QColor(242, 242, 242))

        pen = QPen(QColor(255, 255, 255, 90))
        pen.setWidth(1)
        painter.setPen(pen)
        centre_x = place.x + place.size // 2
        centre_y = place.y + place.size // 2
        painter.drawLine(centre_x, 0, centre_x, self.height())
        painter.drawLine(0, centre_y, self.width(), centre_y)
        painter.end()

    def mousePressEvent(self, event):
        place = self._place()
        self._grab_dx = event.position().x() - (place.x + place.size / 2)
        self._grab_dy = event.position().y() - (place.y + place.size / 2)
        self._dragging = True

    def mouseMoveEvent(self, event):
        if not self._dragging:
            return
        # The grab offset is captured on press so the icon keeps its position
        # under the pointer instead of jumping to it.
        x = event.position().x() - self._grab_dx
        y = event.position().y() - self._grab_dy
        self.moved.emit(
            min(max(x / self.width(), 0.0), 1.0),
            min(max(y / self.height(), 0.0), 1.0))

    def mouseReleaseEvent(self, _event):
        self._dragging = False


class SettingsWindow(QWidget):
    def __init__(self, config):
        super().__init__()
        self._config = config
        self.setWindowTitle('MIFS OSD 设置')

        layout = QVBoxLayout(self)
        layout.addWidget(self._build_position_group())
        layout.addWidget(self._build_icon_group())
        layout.addWidget(self._build_backend_group())

        self._sync_mode()

        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._refresh_status)
        self._status_timer.start(STATUS_POLL_MS)
        self._refresh_status()

    # -- position ----------------------------------------------------------

    def _build_position_group(self):
        group = QGroupBox('位置')
        outer = QVBoxLayout(group)

        outer.addWidget(QLabel('拖动方块设置图标位置'))
        self._thumb = ScreenThumb(self._config)
        self._thumb.moved.connect(self._on_thumb_moved)
        outer.addWidget(self._thumb, alignment=Qt.AlignmentFlag.AlignLeft)

        form = QFormLayout()

        self._mode = QComboBox()
        self._mode.addItem('屏幕比例', 'percent')
        self._mode.addItem('距底边边距', 'margin')
        self._mode.setCurrentIndex(
            1 if self._config.position_mode == 'margin' else 0)
        self._mode.currentIndexChanged.connect(self._on_mode_changed)
        form.addRow('定位方式', self._mode)

        self._x = self._percent_slider(self._config.x_percent)
        self._x.valueChanged.connect(
            lambda v: self._set('x_percent', v / 100.0))
        form.addRow('水平位置', self._x)

        self._y = self._percent_slider(self._config.y_percent)
        self._y.valueChanged.connect(
            lambda v: self._set('y_percent', v / 100.0))
        form.addRow('垂直位置', self._y)

        self._margin = QSpinBox()
        self._margin.setRange(0, 2000)
        self._margin.setSingleStep(10)
        self._margin.setSuffix(' px')
        self._margin.setValue(self._config.bottom_margin)
        self._margin.valueChanged.connect(
            lambda v: self._set('bottom_margin', v))
        form.addRow('距底边距离', self._margin)

        outer.addLayout(form)
        return group

    def _percent_slider(self, value):
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(0, 100)
        # Round-trip through the stored fraction so the handle matches what
        # the renderer will actually use, not the other way round.
        slider.setValue(round(value * 100))
        return slider

    def _on_thumb_moved(self, x_percent, y_percent):
        self._config.x_percent = x_percent
        self._config.y_percent = y_percent
        for slider, value in ((self._x, x_percent), (self._y, y_percent)):
            slider.blockSignals(True)
            slider.setValue(round(value * 100))
            slider.blockSignals(False)
        self._thumb.update()
        self._save()

    def _on_mode_changed(self, _index):
        self._config.position_mode = self._mode.currentData()
        self._sync_mode()
        self._save()

    def _sync_mode(self):
        margin = self._config.position_mode == 'margin'
        for widget in (self._x, self._y):
            widget.setEnabled(not margin)
        self._margin.setEnabled(margin)
        self._thumb.update()

    # -- icon --------------------------------------------------------------

    def _build_icon_group(self):
        group = QGroupBox('图标')
        form = QFormLayout(group)

        self._size = QSlider(Qt.Orientation.Horizontal)
        self._size.setRange(round(MIN_SIZE_PERCENT * 100),
                            round(MAX_SIZE_PERCENT * 100))
        self._size.setValue(round(self._config.size_percent * 100))
        self._size_readout = QLabel('%d %%' % self._size.value())
        self._size.valueChanged.connect(self._on_size_changed)

        size_row = QHBoxLayout()
        size_row.addWidget(self._size)
        size_row.addWidget(self._size_readout)
        form.addRow('大小（屏宽百分比）', size_row)

        self._icon = QComboBox()
        for filename, label in PREVIEW_ICONS:
            path = icons.resolve(filename)
            self._icon.addItem(QIcon(path) if path else QIcon(), label,
                               filename)
        current = self._config.preview_icon
        index = next((i for i, (f, _l) in enumerate(PREVIEW_ICONS)
                      if f == current), 0)
        self._icon.setCurrentIndex(index)
        self._config.preview_icon = PREVIEW_ICONS[index][0]
        self._icon.currentIndexChanged.connect(
            lambda i: self._set('preview_icon', PREVIEW_ICONS[i][0]))
        form.addRow('预览图标', self._icon)

        row = QHBoxLayout()
        show = QPushButton('在屏幕上显示')
        show.clicked.connect(self._show_on_screen)
        row.addWidget(show)

        self._status = QLabel()
        row.addWidget(self._status)

        self._start_button = QPushButton('启动渲染器')
        self._start_button.clicked.connect(self._start_renderer)
        row.addWidget(self._start_button)
        form.addRow('预览', row)
        return group

    def _refresh_status(self):
        """Say whether anything is listening, instead of leaving it implied.

        A preview request is just a counter in the settings file. With no
        renderer watching it the click does exactly what a working one does
        up to the point of drawing -- which, from the outside, is nothing at
        all. Saying so is the difference between a broken button and a
        switched-off program.
        """
        running = instance.is_running()
        self._status.setText('渲染器运行中' if running else '渲染器未运行')
        self._status.setStyleSheet(
            'color: palette(mid);' if running else 'color: #c0392b;')
        self._start_button.setVisible(not running)

    def _start_renderer(self):
        program, arguments = launch_command()
        started, _pid = QProcess.startDetached(program, arguments)
        if not started:
            QMessageBox.warning(
                self, '启动失败',
                '没能启动渲染器。\n\n请在终端手动运行：mifs-osd-kde')
            return
        # Give it time to load the QML and take the lock before reporting.
        QTimer.singleShot(1500, self._refresh_status)

    def _on_size_changed(self, value):
        self._size_readout.setText('%d %%' % value)
        self._set('size_percent', value / 100.0)

    def _show_on_screen(self):
        if not instance.is_running():
            answer = QMessageBox.question(
                self, '渲染器未运行',
                '没有渲染器在监听，预览不会出现在屏幕上。\n\n'
                '现在启动它吗？')
            if answer == QMessageBox.StandardButton.Yes:
                self._start_renderer()
            return
        # The renderer watches this counter; bumping it draws one OSD. Same
        # mechanism as the GNOME frontend's preview-trigger key.
        self._config.preview_trigger += 1
        self._save()

    # -- backend -----------------------------------------------------------

    def _build_backend_group(self):
        group = QGroupBox('渲染方式')
        form = QFormLayout(group)

        self._backend = QComboBox()
        for mode, label in BACKEND_LABELS:
            self._backend.addItem(label, mode)
        index = next((i for i, (m, _l) in enumerate(BACKEND_LABELS)
                      if m == self._config.backend), 0)
        self._backend.setCurrentIndex(index)
        self._backend.currentIndexChanged.connect(
            lambda i: self._set('backend', BACKEND_LABELS[i][0]))
        form.addRow('后端', self._backend)

        note = QLabel('自绘走 KWin 的 layer-shell，位置和大小由上面控制；\n'
                      '系统 OSD 由 plasmashell 绘制，位置大小超时都不可调，\n'
                      '仅作自绘不生效时的退路。切换后需要重启渲染器。')
        note.setStyleSheet('color: palette(mid);')
        form.addRow('', note)
        return group

    # -- plumbing ----------------------------------------------------------

    def _set(self, name, value):
        setattr(self._config, name, value)
        self._thumb.update()
        self._save()

    def _save(self):
        self._config.save()


def main():
    app = QApplication(sys.argv[:1])
    window = SettingsWindow(Config().reload())
    window.show()
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
