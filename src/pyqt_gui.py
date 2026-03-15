from enum import Enum, auto
import math
import os
import queue
import re
import sys
import webbrowser
import pyperclip
from src.combat_objects import school_id_to_names
from src.paths import wizard_city_dance_game_path
from src.lang import load_lang
from src.utils import assign_pet_level
from threading import Thread

from loguru import logger
import ctypes

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTabWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QPushButton, QCheckBox, QLineEdit, QTextEdit,
    QPlainTextEdit, QComboBox, QGroupBox, QFrame, QDialog, QListWidget,
    QFileDialog, QSizePolicy, QStackedWidget,
)
from PyQt6.QtCore import QTimer, Qt, QMetaObject, Q_ARG, pyqtSlot, pyqtSignal, QPropertyAnimation, QEasingCurve, QPoint, QParallelAnimationGroup, QRectF
from PyQt6.QtGui import QPixmap, QIcon, QFont, QPainter, QColor, QPen, QBrush
from PyQt6.QtSvg import QSvgRenderer


class AnimatedTabWidget(QTabWidget):
    """QTabWidget with horizontal slide animation between tabs."""
    def __init__(self, duration=200, parent=None):
        super().__init__(parent)
        self._duration = duration
        self._animating = False
        self._prev_index = 0
        self.currentChanged.connect(self._on_tab_changed)

    def _on_tab_changed(self, index):
        if self._animating:
            return

        prev = self._prev_index
        self._prev_index = index
        if prev == index:
            return

        self._animating = True
        stack = self.findChild(QStackedWidget)
        if not stack:
            self._animating = False
            return

        current_widget = stack.widget(index)
        prev_widget = stack.widget(prev)
        if not current_widget or not prev_widget:
            self._animating = False
            return

        width = stack.width()
        direction = 1 if index > prev else -1

        # Position current (new) widget off-screen
        current_widget.setGeometry(0, 0, width, stack.height())
        current_widget.move(direction * width, 0)
        current_widget.show()
        current_widget.raise_()

        # Also keep prev visible during animation
        prev_widget.show()
        prev_widget.raise_()
        current_widget.raise_()

        group = QParallelAnimationGroup(self)

        anim_out = QPropertyAnimation(prev_widget, b"pos", self)
        anim_out.setDuration(self._duration)
        anim_out.setStartValue(prev_widget.pos())
        anim_out.setEndValue(QPoint(-direction * width, 0))
        anim_out.setEasingCurve(QEasingCurve.Type.InOutCubic)
        group.addAnimation(anim_out)

        anim_in = QPropertyAnimation(current_widget, b"pos", self)
        anim_in.setDuration(self._duration)
        anim_in.setStartValue(QPoint(direction * width, 0))
        anim_in.setEndValue(QPoint(0, 0))
        anim_in.setEasingCurve(QEasingCurve.Type.InOutCubic)
        group.addAnimation(anim_in)

        def on_finished():
            prev_widget.hide()
            prev_widget.move(0, 0)
            self._animating = False

        group.finished.connect(on_finished)
        group.start()


class ToggleSwitch(QCheckBox):
    """A styled toggle switch widget with two SVG icons. Supports horizontal or vertical orientation."""
    _ICON_SIZE = 16
    _GAP = 2
    _PAD = 4

    def __init__(self, left_svg="", right_svg="", left_tooltip="", right_tooltip="", vertical=False, parent=None):
        super().__init__(parent)
        self._left_tooltip = left_tooltip
        self._right_tooltip = right_tooltip
        self._vertical = vertical
        self._icon_cell = self._ICON_SIZE + self._PAD * 2
        if vertical:
            self.setFixedSize(self._icon_cell, self._icon_cell * 2 + self._GAP)
        else:
            self.setFixedSize(self._icon_cell * 2 + self._GAP, self._icon_cell)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("QCheckBox { spacing: 0px; } QCheckBox::indicator { width: 0px; height: 0px; }")
        self._left_pix = self._render_svg(left_svg, self._ICON_SIZE)
        self._right_pix = self._render_svg(right_svg, self._ICON_SIZE)

    def _render_svg(self, svg_str, size):
        dpr = self.devicePixelRatioF()
        real_size = int(size * dpr)
        renderer = QSvgRenderer(svg_str.encode())
        pixmap = QPixmap(real_size, real_size)
        pixmap.fill(Qt.GlobalColor.transparent)
        p = QPainter(pixmap)
        renderer.render(p)
        p.end()
        pixmap.setDevicePixelRatio(dpr)
        return pixmap

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setChecked(not self.isChecked())

    def paintEvent(self, event):
        from PyQt6.QtGui import QColor, QBrush
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        pad = self._PAD
        cell = self._icon_cell
        gap = self._GAP

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(74, 1, 158)))

        if self._vertical:
            # Top = first icon, bottom = second icon
            if self.isChecked():
                painter.drawRoundedRect(0, cell + gap, cell, cell, 4, 4)
            else:
                painter.drawRoundedRect(0, 0, cell, cell, 4, 4)
            painter.drawPixmap(pad, pad, self._left_pix)
            painter.drawPixmap(pad, cell + gap + pad, self._right_pix)
        else:
            if self.isChecked():
                painter.drawRoundedRect(cell + gap, 0, cell, cell, 4, 4)
            else:
                painter.drawRoundedRect(0, 0, cell, cell, 4, 4)
            painter.drawPixmap(pad, pad, self._left_pix)
            painter.drawPixmap(cell + gap + pad, pad, self._right_pix)

        painter.end()

    def event(self, event):
        if event.type() == event.Type.ToolTip:
            if self._vertical:
                y = event.pos().y()
                if y < self._icon_cell:
                    self.setToolTip(self._left_tooltip)
                else:
                    self.setToolTip(self._right_tooltip)
            else:
                x = event.pos().x()
                if x < self._icon_cell:
                    self.setToolTip(self._left_tooltip)
                else:
                    self.setToolTip(self._right_tooltip)
        return super().event(event)


class AnimatedStackedWidget(QStackedWidget):
    """QStackedWidget with a horizontal slide animation between pages."""
    def __init__(self, duration=250, parent=None):
        super().__init__(parent)
        self._duration = duration
        self._animating = False

    def slide_to(self, index):
        if self._animating or index == self.currentIndex():
            return

        self._animating = True
        current_widget = self.currentWidget()
        next_widget = self.widget(index)
        width = self.width()

        # Determine slide direction
        direction = 1 if index > self.currentIndex() else -1

        # Position the next widget off-screen
        next_widget.setGeometry(0, 0, width, self.height())
        next_widget.move(direction * width, 0)
        next_widget.show()
        next_widget.raise_()

        group = QParallelAnimationGroup(self)

        # Slide current widget out
        anim_out = QPropertyAnimation(current_widget, b"pos", self)
        anim_out.setDuration(self._duration)
        anim_out.setStartValue(current_widget.pos())
        anim_out.setEndValue(QPoint(-direction * width, 0))
        anim_out.setEasingCurve(QEasingCurve.Type.InOutCubic)
        group.addAnimation(anim_out)

        # Slide next widget in
        anim_in = QPropertyAnimation(next_widget, b"pos", self)
        anim_in.setDuration(self._duration)
        anim_in.setStartValue(QPoint(direction * width, 0))
        anim_in.setEndValue(QPoint(0, 0))
        anim_in.setEasingCurve(QEasingCurve.Type.InOutCubic)
        group.addAnimation(anim_in)

        def on_finished():
            self.setCurrentIndex(index)
            self._animating = False

        group.finished.connect(on_finished)
        group.start()


class DuelCircleWidget(QWidget):
    """Custom widget that renders a radial duel circle with enemy/ally slots."""
    casterSelected = pyqtSignal(int)
    targetSelected = pyqtSignal(int)

    _SLOT_RADIUS = 14
    _SELECTED_COLOR = QColor(74, 1, 158)

    def __init__(self, stroke_color='#e0e0e0', text_color='#ffffff', bg_color='#1e1e1e', parent=None):
        super().__init__(parent)
        self._stroke_color = QColor(stroke_color)
        self._text_color = QColor(text_color)
        self._bg_color = QColor(bg_color)
        self._enemy_count = 4
        self._ally_count = 4
        self._selected_caster = 1
        self._selected_target = 1
        self._enemy_name = ""
        self._ally_name = ""
        self._slot_centers = {}  # (side, index) -> (x, y)
        self._slot_icons = {}   # (side, index) -> QPixmap
        self.setFixedSize(300, 200)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        sc = stroke_color
        enemy_svgs = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m11 19-6-6"/><path d="m5 21-2-2"/><path d="m8 16-4 4"/><path d="M9.5 17.5 21 6V3h-3L6.5 14.5"/></svg>',
            f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2.586 17.414A2 2 0 0 0 2 18.828V21a1 1 0 0 0 1 1h3a1 1 0 0 0 1-1v-1a1 1 0 0 1 1-1h1a1 1 0 0 0 1-1v-1a1 1 0 0 1 1-1h.172a2 2 0 0 0 1.414-.586l.814-.814a6.5 6.5 0 1 0-4-4z"/><circle cx="16.5" cy="7.5" r=".5" fill="{sc}"/></svg>',
            f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.5 3 8 9l4 13 4-13-2.5-6"/><path d="M17 3a2 2 0 0 1 1.6.8l3 4a2 2 0 0 1 .013 2.382l-7.99 10.986a2 2 0 0 1-3.247 0l-7.99-10.986A2 2 0 0 1 2.4 7.8l2.998-3.997A2 2 0 0 1 7 3z"/><path d="M2 9h20"/></svg>',
            f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 11a2 2 0 1 1-4 0 4 4 0 0 1 8 0 6 6 0 0 1-12 0 8 8 0 0 1 16 0 10 10 0 1 1-20 0 11.93 11.93 0 0 1 2.42-7.22 2 2 0 1 1 3.16 2.44"/></svg>',
        ]
        ally_svgs = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/></svg>',
            f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2.062 12.348a1 1 0 0 1 0-.696 10.75 10.75 0 0 1 19.876 0 1 1 0 0 1 0 .696 10.75 10.75 0 0 1-19.876 0"/><circle cx="12" cy="12" r="3"/></svg>',
            f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11.525 2.295a.53.53 0 0 1 .95 0l2.31 4.679a2.123 2.123 0 0 0 1.595 1.16l5.166.756a.53.53 0 0 1 .294.904l-3.736 3.638a2.123 2.123 0 0 0-.611 1.878l.882 5.14a.53.53 0 0 1-.771.56l-4.618-2.428a2.122 2.122 0 0 0-1.973 0L6.396 21.01a.53.53 0 0 1-.77-.56l.881-5.139a2.122 2.122 0 0 0-.611-1.879L2.16 9.795a.53.53 0 0 1 .294-.906l5.165-.755a2.122 2.122 0 0 0 1.597-1.16z"/></svg>',
            f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20.985 12.486a9 9 0 1 1-9.473-9.472c.405-.022.617.46.402.803a6 6 0 0 0 8.268 8.268c.344-.215.825-.004.803.401"/></svg>',
        ]
        icon_size = 16
        for i, svg in enumerate(enemy_svgs):
            self._slot_icons[('enemy', i + 1)] = self._render_svg(svg, icon_size)
        for i, svg in enumerate(ally_svgs):
            self._slot_icons[('ally', i + 1)] = self._render_svg(svg, icon_size)

    def _render_svg(self, svg_str, size):
        dpr = self.devicePixelRatioF()
        real = int(size * dpr)
        renderer = QSvgRenderer(svg_str.encode())
        pix = QPixmap(real, real)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        renderer.render(p)
        p.end()
        pix.setDevicePixelRatio(dpr)
        return pix

    def _calc_slot_positions(self):
        """Calculate slot center positions on an elliptical arc."""
        self._slot_centers.clear()
        w = self.width()
        h = self.height()
        cx = w / 2
        cy = h / 2
        rx = w * 0.38
        ry = h * 0.38

        # Enemy slots on top arc (270° = top)
        enemy_angles = self._distribute_angles(self._enemy_count, center_deg=270)
        for i, deg in enumerate(enemy_angles):
            rad = math.radians(deg)
            x = cx + rx * math.cos(rad)
            y = cy + ry * math.sin(rad)
            self._slot_centers[('enemy', i + 1)] = (x, y)

        # Ally slots on bottom arc (90° = bottom)
        ally_angles = self._distribute_angles(self._ally_count, center_deg=90)
        for i, deg in enumerate(ally_angles):
            rad = math.radians(deg)
            x = cx + rx * math.cos(rad)
            y = cy + ry * math.sin(rad)
            self._slot_centers[('ally', i + 1)] = (x, y)

    @staticmethod
    def _distribute_angles(count, center_deg):
        """Evenly distribute `count` slots around `center_deg` with 36° spacing."""
        spacing = 36
        total_span = spacing * (count - 1)
        start = center_deg - total_span / 2
        return [start + i * spacing for i in range(count)]

    def paintEvent(self, event):
        self._calc_slot_positions()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        cx = w / 2
        cy = h / 2
        rx = w * 0.38
        ry = h * 0.38

        # Draw oval outline
        pen = QPen(self._stroke_color, 1.5)
        pen.setStyle(Qt.PenStyle.DotLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QRectF(cx - rx, cy - ry, rx * 2, ry * 2))

        # Draw divider line
        painter.setPen(QPen(self._stroke_color, 0.5, Qt.PenStyle.DashLine))
        painter.drawLine(int(cx - rx * 0.7), int(cy), int(cx + rx * 0.7), int(cy))

        r = self._SLOT_RADIUS

        for (side, idx), (sx, sy) in self._slot_centers.items():
            rect = QRectF(sx - r, sy - r, r * 2, r * 2)
            is_selected = (side == 'enemy' and idx == self._selected_target) or \
                          (side == 'ally' and idx == self._selected_caster)

            if is_selected:
                painter.setBrush(QBrush(self._SELECTED_COLOR))
                painter.setPen(QPen(self._SELECTED_COLOR.lighter(140), 2))
            else:
                painter.setBrush(QBrush(self._bg_color))
                painter.setPen(QPen(self._stroke_color, 1.5))

            painter.drawEllipse(rect)

            # Draw slot icon centered via QPointF for sub-pixel accuracy
            pix = self._slot_icons.get((side, idx))
            if pix:
                iw = pix.width() / pix.devicePixelRatio()
                ih = pix.height() / pix.devicePixelRatio()
                painter.drawPixmap(QRectF(sx - iw / 2, sy - ih / 2, iw, ih), pix, QRectF(pix.rect()))

        # Draw selected names near the divider line
        label_font = painter.font()
        label_font.setPixelSize(10)
        label_font.setBold(False)
        painter.setFont(label_font)
        painter.setPen(QPen(self._stroke_color))
        if self._enemy_name:
            painter.drawText(QRectF(0, cy - 16, w, 14), Qt.AlignmentFlag.AlignCenter, self._enemy_name)
        if self._ally_name:
            painter.drawText(QRectF(0, cy + 2, w, 14), Qt.AlignmentFlag.AlignCenter, self._ally_name)

        painter.end()

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self._calc_slot_positions()
        px, py = event.position().x(), event.position().y()
        hit_r = self._SLOT_RADIUS + 6
        best_key = None
        best_dist = float('inf')
        for key, (sx, sy) in self._slot_centers.items():
            dist = (px - sx) ** 2 + (py - sy) ** 2
            if dist < best_dist and dist <= hit_r ** 2:
                best_dist = dist
                best_key = key
        if best_key:
            side, idx = best_key
            if side == 'enemy':
                self._selected_target = idx
                self.targetSelected.emit(idx)
            else:
                self._selected_caster = idx
                self.casterSelected.emit(idx)
            self.update()

    def selected_caster(self):
        return self._selected_caster

    def selected_target(self):
        return self._selected_target

    def set_enemy_name(self, name):
        self._enemy_name = name
        self.update()

    def set_ally_name(self, name):
        self._ally_name = name
        self.update()


def _resource_path(filename: str) -> str:
    """Resolve path for bundled resources (PyInstaller) or source directory."""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, filename)
    return filename


global console_sink


def terminate_thread(thread: Thread):
    if not thread.is_alive():
        return

    exc = ctypes.py_object(SystemExit)
    res = ctypes.pythonapi.PyThreadState_SetAsyncExc(
        ctypes.c_long(thread.ident), exc)
    if res == 0:
        raise ValueError("Invalid thread ID")
    elif res != 1:
        ctypes.pythonapi.PyThreadState_SetAsyncExc(thread.ident, None)
        raise SystemError("PyThreadState_SetAsyncExc failed")

class ToolClosedException(Exception):
    pass


class GUICommandType(Enum):
    # deimos <-> window
    Close = auto()
    AttemptedClose = auto()
    CloseFromBackend = auto()

    # window -> deimos
    ToggleOption = auto()
    Copy = auto()
    SelectEnemy = auto()

    Teleport = auto()
    CustomTeleport = auto()
    EntityTeleport = auto()

    XYZSync = auto()
    XPress = auto()

    GoToZone = auto()
    GoToWorld = auto()
    GoToBazaar = auto()

    RefillPotions = auto()

    AnchorCam = auto()
    SetCamPosition = auto()
    SetCamDistance = auto()

    ExecuteFlythrough = auto()
    KillFlythrough = auto()

    ExecuteBot = auto()
    KillBot = auto()

    SetPlaystyles = auto()

    SetScale = auto()

    PopulateCamera = auto()

    # deimos -> window
    UpdateWindow = auto()
    UpdateWindowValues = auto()
    UpdateConsole = auto()
    CopyConsole = auto()

    ShowUITreePopup = auto()
    ShowEntityListPopup = auto()

    # Launcher
    LaunchInstance = auto()
    SaveAccount = auto()
    DeleteAccount = auto()
    LoadAccounts = auto()
    UpdateAccountList = auto()


class GUIKeys:
    toggle_speedhack = "togglespeedhack"
    toggle_combat = "togglecombat"
    toggle_dialogue = "toggledialogue"
    toggle_sigil = "togglesigil"
    toggle_questing = "toggle_questing"
    toggle_auto_pet = "toggleautopet"
    toggle_auto_potion = "toggleautopotion"
    toggle_freecam = "togglefreecam"
    toggle_camera_collision = "togglecameracollision"
    toggle_show_expanded_logs = "toggleshowexpandedlogs"

    hotkey_quest_tp = "hotkeyquesttp"
    hotkey_freecam_tp = "hotkeyfreecamtp"

    mass_hotkey_mass_tp = "masshotkeymasstp"
    mass_hotkey_xyz_sync = "masshotkeyxyzsync"
    mass_hotkey_x_press = "masshotkeyxpress"

    copy_position = "copyposition"
    copy_zone = "copyzone"
    copy_rotation = "copyrotation"
    copy_entity_list = "copyentitylist"
    copy_ui_tree = "copyuitree"
    copy_camera_position = "copycameraposition"
    copy_stats = "copystats"
    copy_logs = "copylogs"

    button_custom_tp = "buttoncustomtp"
    button_entity_tp = "buttonentitytp"
    button_go_to_zone = "buttongotozone"
    button_mass_go_to_zone = "buttonmassgotozone"
    button_go_to_world = "buttongotoworld"
    button_mass_go_to_world = "buttonmassgotoworld"
    button_go_to_bazaar = "buttongotobazaar"
    button_mass_go_to_bazaar = "buttonmassgotobazaar"
    button_refill_potions = "buttonrefillpotions"
    button_mass_refill_potions = "buttonmassrefillpotions"
    button_set_camera_position = "buttonsetcameraposition"
    button_anchor = "buttonanchor"
    button_set_distance = "buttonsetdistance"
    button_view_stats = "buttonviewstats"
    button_swap_members = "buttonswapmembers"

    button_execute_flythrough = "buttonexecuteflythrough"
    button_kill_flythrough = "buttonkillflythrough"
    button_run_bot = "buttonrunbot"
    button_kill_bot = "buttonkillbot"
    button_set_playstyles = "buttonsetplaystyles"
    button_set_scale = "buttonsetscale"


class GUICommand:
    def __init__(self, com_type: GUICommandType, data=None):
        self.com_type = com_type
        self.data = data


class ConsoleTextEdit(QPlainTextEdit):
    """QPlainTextEdit subclass with thread-safe slots for log appending."""

    @pyqtSlot(str)
    def _append_log(self, text):
        current = self.toPlainText()
        if current:
            self.setPlainText(current + text)
        else:
            self.setPlainText(text)
        scrollbar = self.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    @pyqtSlot(str)
    def _set_log(self, text):
        self.setPlainText(text)
        scrollbar = self.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())


class PyQtSink:
    def __init__(self, console_widget: QPlainTextEdit):
        self.console_widget = console_widget
        self.buffer = []
        self.max_lines = 1000
        self.show_expanded_logs = False

    def copy(self):
        log_str = "```\n"
        for (line, _, _) in self.buffer:
            log_str += line
        pyperclip.copy(log_str + "```")
        logger.debug("Copied current logs.")

    def toggle_show_expanded_logs(self, override: bool | None = None):
        match override:
            case True | False:
                self.show_expanded_logs = override
            case _:
                self.show_expanded_logs = not self.show_expanded_logs

        match self.show_expanded_logs:
            case True:
                logger.debug("Console is now showing full log messages.")
            case _:
                logger.debug("Console is now truncating log messages.")

        self.refresh()

    def write(self, message):
        ansi_pattern = r'\033\[\d+m'
        clean_message = re.sub(ansi_pattern, '', message)

        split_msg = clean_message.split("|")
        if len(split_msg) < 3:
            for l in ["DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"]:
                if l in clean_message:
                    level = l
                    break
            else:
                level = "DEBUG"
        else:
            level = split_msg[1].lstrip().rstrip()

        def collapse_log(input: str) -> str:
            if "-" not in input:
                return input
            split_input = input.split("-")
            if len(split_input) < 4:
                return input
            return split_input[3].lstrip()

        truncated_message = level + " - " + collapse_log(clean_message)

        self.buffer.append((clean_message, truncated_message, level))
        if len(self.buffer) > self.max_lines:
            self.buffer.pop(0)

        try:
            message_to_write = clean_message if self.show_expanded_logs else truncated_message
            # Thread-safe: marshal to GUI thread via QMetaObject.invokeMethod
            QMetaObject.invokeMethod(self.console_widget, "_append_log",
                Qt.ConnectionType.QueuedConnection, Q_ARG(str, message_to_write))
        except Exception:
            pass

    def refresh(self):
        try:
            text = ""
            for clean, trunc, level in self.buffer:
                message_to_write = clean if self.show_expanded_logs else trunc
                text += message_to_write
            QMetaObject.invokeMethod(self.console_widget, "_set_log",
                Qt.ConnectionType.QueuedConnection, Q_ARG(str, text))
        except Exception:
            pass

    def get_buffer(self):
        return self.buffer


def _show_ui_tree_popup(parent, ui_tree_content):
    ui_tree_list = ui_tree_content.splitlines()

    path_dict = {}
    path_stack = []

    for line in ui_tree_list:
        indent = len(line) - len(line.lstrip('-'))
        clean_line = line.lstrip('- ')

        name_match = re.search(r'\[(.*?)\]', clean_line)
        if name_match:
            name = name_match.group(1)
        else:
            name = clean_line.split()[0]

        while len(path_stack) > indent:
            path_stack.pop()

        current_path = path_stack.copy()
        current_path.append(name)

        path_dict[line] = current_path[1:] if len(current_path) > 1 else current_path
        path_stack.append(name)

    dialog = QDialog(parent)
    dialog.setWindowTitle("UI Tree")
    dialog.resize(700, 500)
    layout = QVBoxLayout(dialog)

    layout.addWidget(QLabel("Click the path needed to copy it to clipboard."))

    search_input = QLineEdit()
    search_input.setPlaceholderText("Search")
    layout.addWidget(search_input)

    listbox = QListWidget()
    listbox.addItems(ui_tree_list)
    layout.addWidget(listbox)

    def on_search(text):
        listbox.clear()
        filtered = [line for line in ui_tree_list if text.lower() in line.lower()]
        listbox.addItems(filtered)

    def on_select(item):
        if item:
            selected_line = item.text()
            if selected_line in path_dict:
                path = path_dict[selected_line]
                pyperclip.copy(str(path))
            else:
                pyperclip.copy(selected_line)
            dialog.close()

    search_input.textChanged.connect(on_search)
    listbox.itemClicked.connect(on_select)

    close_btn = QPushButton("Close")
    close_btn.clicked.connect(dialog.close)
    layout.addWidget(close_btn)

    dialog.show()


def _show_entity_list_popup(parent, entity_list_content):
    entity_list = [line for line in entity_list_content.splitlines() if line.strip()]

    dialog = QDialog(parent)
    dialog.setWindowTitle("Entity List")
    dialog.resize(450, 400)
    layout = QVBoxLayout(dialog)

    layout.addWidget(QLabel("Click the entity needed to copy the name and location to clipboard."))

    search_input = QLineEdit()
    search_input.setPlaceholderText("Search")
    layout.addWidget(search_input)

    listbox = QListWidget()
    listbox.addItems(entity_list)
    layout.addWidget(listbox)

    def on_search(text):
        listbox.clear()
        filtered = [line for line in entity_list if text.lower() in line.lower()]
        listbox.addItems(filtered)

    def on_select(item):
        if item:
            pyperclip.copy(item.text())
            dialog.close()

    search_input.textChanged.connect(on_search)
    listbox.itemClicked.connect(on_select)

    close_btn = QPushButton("Close")
    close_btn.clicked.connect(dialog.close)
    layout.addWidget(close_btn)

    dialog.show()


def manage_gui(send_queue: queue.Queue, recv_queue: queue.Queue, gui_theme, gui_text_color, gui_button_color, tool_name, tool_version, gui_on_top, langcode, gui_font='Segoe UI', gui_font_size=9, tool_author='Deimos-Wizard101'):
    tl = load_lang(langcode)

    # Set AppUserModelID so Windows uses our icon in taskbar/process list
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(f"deimos.{tool_name}")
    except Exception:
        pass

    # Qt6 handles DPI awareness natively — no need to call SetProcessDpiAwareness
    app = QApplication(sys.argv)

    _vp_height = 450

    # Apply font
    font = QFont(gui_font, gui_font_size)
    app.setFont(font)

    # Apply theme (dark/light) and text color
    _text_color = gui_text_color if isinstance(gui_text_color, str) else 'white'
    _theme = gui_theme.lower() if isinstance(gui_theme, str) else 'black'
    if _theme in ('black', 'dark'):
        _bg_color = '#1e1e1e'
        _alt_bg = '#2d2d2d'
    else:
        _bg_color = '#f0f0f0'
        _alt_bg = '#ffffff'

    _stroke_color = gui_text_color if gui_text_color else ('#e0e0e0' if _theme in ('black', 'dark') else '#333333')

    app.setStyleSheet(
        f"QWidget {{ background-color: {_bg_color}; color: {_text_color}; }}"
        f"QComboBox {{ background-color: {_alt_bg}; color: {_text_color}; padding-left: 4px; }}"
        f"QLineEdit {{ background-color: {_alt_bg}; color: {_text_color}; }}"
        f"QTextEdit {{ background-color: {_alt_bg}; color: {_text_color}; }}"
        f"QPlainTextEdit {{ background-color: {_alt_bg}; color: {_text_color}; }}"
        f"QListWidget {{ background-color: {_alt_bg}; color: {_text_color}; }}"
    )

    # Button color
    _hex = gui_button_color.lstrip('#') if isinstance(gui_button_color, str) else "4a019e"
    btn_r, btn_g, btn_b = int(_hex[0:2], 16), int(_hex[2:4], 16), int(_hex[4:6], 16)

    btn_style = (
        f"QPushButton {{"
        f"  background-color: rgb({btn_r},{btn_g},{btn_b});"
        f"  color: white;"
        f"  border: none;"
        f"  padding: 4px 8px;"
        f"  border-radius: 4px;"
        f"}}"
        f"QPushButton:hover {{"
        f"  background-color: rgb({min(btn_r+30,255)},{min(btn_g+30,255)},{min(btn_b+30,255)});"
        f"}}"
        f"QPushButton:pressed {{"
        f"  background-color: rgb({max(btn_r-20,0)},{max(btn_g-20,0)},{max(btn_b-20,0)});"
        f"}}"
    )

    link_style = (
        "QPushButton {"
        "  background-color: transparent;"
        "  color: rgb(100,149,237);"
        "  border: none;"
        "  padding: 2px;"
        "}"
        "QPushButton:hover {"
        "  background-color: rgb(50,50,80);"
        "}"
    )

    frame_style = (
        "QFrame {"
        "  border: 1px solid palette(mid);"
        "  border-radius: 4px;"
        "}"
    )

    groupbox_style = (
        "QGroupBox {"
        "  border: none;"
        "  margin-top: 12px;"
        "  padding-top: 4px;"
        "}"
        "QGroupBox::title {"
        "  subcontrol-origin: margin;"
        "  subcontrol-position: top left;"
        "  padding: 0 4px;"
        "  font-weight: bold;"
        "}"
    )

    window = QMainWindow()
    _window_flags = Qt.WindowType.FramelessWindowHint
    if gui_on_top:
        _window_flags |= Qt.WindowType.WindowStaysOnTopHint
    window.setWindowFlags(_window_flags)
    window.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
    window.setStyleSheet(groupbox_style)
    window.setFixedHeight(_vp_height)

    _ico_path = _resource_path("Deimos-logo.ico")
    if os.path.exists(_ico_path):
        window.setWindowIcon(QIcon(_ico_path))

    central = QWidget()
    window.setCentralWidget(central)
    main_layout = QVBoxLayout(central)
    main_layout.setContentsMargins(0, 0, 0, 0)
    main_layout.setSpacing(0)

    # ==================== Custom Titlebar ====================
    _tc = gui_text_color if gui_text_color else "#e0e0e0"
    _close_svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{_tc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>'
    _minimize_svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{_tc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14"/></svg>'
    _pin_svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{_tc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 17v5"/><path d="M9 10.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24V16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V7a1 1 0 0 1 1-1 2 2 0 0 0 0-4H8a2 2 0 0 0 0 4 1 1 0 0 1 1 1z"/></svg>'
    _unpin_svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{_tc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 17v5"/><path d="M15 9.34V7a1 1 0 0 1 1-1 2 2 0 0 0 0-4H7.89"/><path d="m2 2 20 20"/><path d="M9 9v1.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24V16a1 1 0 0 0 1 1h11"/></svg>'

    def _titlebar_svg_icon(svg_str, size=24):
        dpr = window.devicePixelRatioF()
        real_size = int(size * dpr)
        renderer = QSvgRenderer(svg_str.encode())
        pixmap = QPixmap(real_size, real_size)
        pixmap.fill(Qt.GlobalColor.transparent)
        p = QPainter(pixmap)
        renderer.render(p)
        p.end()
        pixmap.setDevicePixelRatio(dpr)
        return QIcon(pixmap)

    titlebar = QWidget()
    titlebar.setFixedHeight(32)
    titlebar.setStyleSheet(
        "QWidget { background-color: rgba(30, 30, 30, 255); }"
    )
    titlebar_layout = QHBoxLayout(titlebar)
    titlebar_layout.setContentsMargins(4, 0, 4, 0)
    titlebar_layout.setSpacing(0)
    titlebar_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

    _titlebar_btn_style = (
        "QPushButton {"
        "  background-color: transparent;"
        "  border: none;"
        "  padding: 4px;"
        "}"
        "QPushButton:hover {"
        "  background-color: rgba(255,255,255,30);"
        "  border-radius: 4px;"
        "}"
    )
    _close_btn_style = (
        "QPushButton {"
        "  background-color: transparent;"
        "  border: none;"
        "  padding: 4px;"
        "}"
        "QPushButton:hover {"
        "  background-color: rgba(232,17,35,200);"
        "  border-radius: 4px;"
        "}"
    )

    # Left side: pin button
    _is_pinned = [gui_on_top]
    _pin_icon = _titlebar_svg_icon(_pin_svg)
    _unpin_icon = _titlebar_svg_icon(_unpin_svg)

    pin_btn = QPushButton()
    pin_btn.setIcon(_pin_icon if _is_pinned[0] else _unpin_icon)
    pin_btn.setToolTip("Always on top" if _is_pinned[0] else "Not on top")
    pin_btn.setFixedSize(32, 24)
    pin_btn.setStyleSheet(_titlebar_btn_style)
    pin_btn.setCursor(Qt.CursorShape.PointingHandCursor)

    def _toggle_pin():
        _is_pinned[0] = not _is_pinned[0]
        pin_btn.setIcon(_pin_icon if _is_pinned[0] else _unpin_icon)
        pin_btn.setToolTip("Always on top" if _is_pinned[0] else "Not on top")
        # Use Win32 SetWindowPos to toggle topmost without recreating the window
        import ctypes.wintypes
        _SetWindowPos = ctypes.windll.user32.SetWindowPos
        _SetWindowPos.argtypes = [ctypes.wintypes.HWND, ctypes.wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
        _SetWindowPos.restype = ctypes.wintypes.BOOL
        hwnd = ctypes.wintypes.HWND(int(window.winId()))
        HWND_TOPMOST = ctypes.wintypes.HWND(-1)
        HWND_NOTOPMOST = ctypes.wintypes.HWND(-2)
        SWP_NOMOVE = 0x0002
        SWP_NOSIZE = 0x0001
        SWP_NOACTIVATE = 0x0010
        insert_after = HWND_TOPMOST if _is_pinned[0] else HWND_NOTOPMOST
        _SetWindowPos(hwnd, insert_after, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)

    pin_btn.clicked.connect(_toggle_pin)
    titlebar_layout.addWidget(pin_btn)

    # Center: icon + title (use stretch on both sides)
    titlebar_layout.addStretch()

    _center_row = QHBoxLayout()
    _center_row.setSpacing(4)
    if os.path.exists(_ico_path):
        title_icon_label = QLabel()
        title_icon_pix = QPixmap(_ico_path).scaled(16, 16, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        title_icon_label.setPixmap(title_icon_pix)
        title_icon_label.setFixedSize(20, 16)
        title_icon_label.setStyleSheet("background: transparent;")
        _center_row.addWidget(title_icon_label)

    title_label = QLabel(f'{tool_name} v{tool_version}')
    title_label.setStyleSheet(f"QLabel {{ color: {_tc}; font-weight: bold; background: transparent; }}")
    _center_row.addWidget(title_label)
    titlebar_layout.addLayout(_center_row)

    titlebar_layout.addStretch()

    # Right side: minimize + close
    minimize_btn = QPushButton()
    minimize_btn.setIcon(_titlebar_svg_icon(_minimize_svg))
    minimize_btn.setFixedSize(32, 24)
    minimize_btn.setStyleSheet(_titlebar_btn_style)
    minimize_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    minimize_btn.clicked.connect(window.showMinimized)
    titlebar_layout.addWidget(minimize_btn)

    close_btn = QPushButton()
    close_btn.setIcon(_titlebar_svg_icon(_close_svg))
    close_btn.setFixedSize(32, 24)
    close_btn.setStyleSheet(_close_btn_style)
    close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    close_btn.clicked.connect(window.close)
    titlebar_layout.addWidget(close_btn)

    # Drag support
    _drag_pos = [None]
    def _titlebar_mouse_press(event):
        if event.button() == Qt.MouseButton.LeftButton:
            _drag_pos[0] = event.globalPosition().toPoint() - window.frameGeometry().topLeft()
    def _titlebar_mouse_move(event):
        if _drag_pos[0] is not None and event.buttons() & Qt.MouseButton.LeftButton:
            window.move(event.globalPosition().toPoint() - _drag_pos[0])
    def _titlebar_mouse_release(event):
        _drag_pos[0] = None

    titlebar.mousePressEvent = _titlebar_mouse_press
    titlebar.mouseMoveEvent = _titlebar_mouse_move
    titlebar.mouseReleaseEvent = _titlebar_mouse_release

    main_layout.addWidget(titlebar)

    # ==================== Content Area ====================
    content_widget = QWidget()
    content_layout = QVBoxLayout(content_widget)
    content_layout.setContentsMargins(8, 8, 8, 8)
    content_layout.setSpacing(4)
    main_layout.addWidget(content_widget)

    free_tool_label = QLabel(tl('free_tool'))
    free_tool_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    content_layout.addWidget(free_tool_label)

    tabs = AnimatedTabWidget(duration=200)
    content_layout.addWidget(tabs)

    # Widget tag registry for backend updates
    widget_tags = {}

    def styled_btn(label, callback=None):
        btn = QPushButton(label)
        btn.setStyleSheet(btn_style)
        if callback:
            btn.clicked.connect(callback)
        return btn

    def centered_label(text):
        lbl = QLabel(text)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return lbl


    # ==================== Callbacks ====================
    def toggle_callback(event_key):
        def cb():
            send_queue.put(GUICommand(GUICommandType.ToggleOption, event_key))
        return cb

    def copy_callback(event_key):
        def cb():
            send_queue.put(GUICommand(GUICommandType.Copy, event_key))
        return cb

    def teleport_callback(event_key):
        def cb():
            send_queue.put(GUICommand(GUICommandType.Teleport, event_key))
        return cb

    icon_btn_style = (
        "QPushButton {"
        "  background-color: transparent;"
        "  border: none;"
        "  padding: 2px;"
        "}"
        "QPushButton:hover {"
        "  background-color: rgba(255,255,255,30);"
        "  border-radius: 4px;"
        "}"
    )

    # ==================== Launcher Tab ====================
    launcher_tab = QWidget()
    launcher_layout = QVBoxLayout(launcher_tab)
    launcher_layout.setContentsMargins(4, 4, 4, 4)
    launcher_layout.setSpacing(4)

    launcher_header = QHBoxLayout()
    launcher_header.addWidget(centered_label(tl('launcher')), 1)
    launcher_layout.addLayout(launcher_header)

    # Account list (multi-select)
    account_list = QListWidget()
    account_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
    account_list.setFixedHeight(120)
    widget_tags['AccountList'] = account_list
    launcher_layout.addWidget(account_list)

    # Account action buttons row
    _add_svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{_stroke_color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14"/><path d="M12 5v14"/></svg>'
    _trash_svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{_stroke_color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/></svg>'
    _rocket_svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{_stroke_color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09z"/><path d="m12 15-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z"/><path d="M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0"/><path d="M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5"/></svg>'
    _folder_svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{_stroke_color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2z"/></svg>'

    def _launcher_icon_btn(svg_str, tooltip, callback):
        btn = QPushButton()
        btn.setIcon(_titlebar_svg_icon(svg_str, 24))
        btn.setFixedSize(32, 32)
        btn.setStyleSheet(icon_btn_style)
        btn.setToolTip(tooltip)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(callback)
        return btn

    def _show_add_account_dialog():
        dlg = QDialog(window)
        dlg.setWindowTitle(tl('add_account'))
        dlg.setModal(True)
        dlg_layout = QVBoxLayout(dlg)

        nick_input = QLineEdit()
        nick_input.setPlaceholderText(tl('nickname'))
        dlg_layout.addWidget(QLabel(tl('nickname')))
        dlg_layout.addWidget(nick_input)

        user_input = QLineEdit()
        user_input.setPlaceholderText(tl('username'))
        dlg_layout.addWidget(QLabel(tl('username')))
        dlg_layout.addWidget(user_input)

        pass_input = QLineEdit()
        pass_input.setPlaceholderText(tl('password'))
        pass_input.setEchoMode(QLineEdit.EchoMode.Password)
        dlg_layout.addWidget(QLabel(tl('password')))
        dlg_layout.addWidget(pass_input)

        save_btn = QPushButton(tl('save_account'))
        save_btn.setStyleSheet(btn_style)
        def _on_save():
            nick = nick_input.text().strip()
            user = user_input.text().strip()
            pw = pass_input.text()
            if nick and user and pw:
                send_queue.put(GUICommand(GUICommandType.SaveAccount, (nick, user, pw)))
                dlg.accept()
        save_btn.clicked.connect(_on_save)
        dlg_layout.addWidget(save_btn)

        dlg.adjustSize()
        dlg.exec()

    def _remove_selected_accounts():
        for item in account_list.selectedItems():
            send_queue.put(GUICommand(GUICommandType.DeleteAccount, item.text()))

    acct_btn_row = QHBoxLayout()
    acct_btn_row.addStretch()
    acct_btn_row.addWidget(_launcher_icon_btn(_add_svg, tl('add_account'), _show_add_account_dialog))
    acct_btn_row.addWidget(_launcher_icon_btn(_trash_svg, tl('remove_account'), _remove_selected_accounts))
    acct_btn_row.addStretch()
    launcher_layout.addLayout(acct_btn_row)

    # Launch & Login button (prominent, centered)
    def _launch_and_login():
        selected = [item.text() for item in account_list.selectedItems()]
        if selected:
            game_path = game_path_input.text().strip()
            send_queue.put(GUICommand(GUICommandType.LaunchInstance, (selected, game_path)))

    launch_btn = QPushButton(tl('launch_login'))
    launch_btn.setStyleSheet(btn_style)
    launch_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    launch_btn.setFixedHeight(36)
    launch_btn.clicked.connect(_launch_and_login)
    launcher_layout.addWidget(launch_btn)

    # Game path row
    launcher_layout.addWidget(QLabel(tl('game_path')))
    game_path_row = QHBoxLayout()

    # Auto-detect game path
    _steam_path = r"C:\Program Files (x86)\Steam\steamapps\common\Wizard101"
    _default_path = r"C:\ProgramData\KingsIsle Entertainment\Wizard101"
    _detected_path = ""
    if os.path.isdir(_steam_path):
        _detected_path = _steam_path
    elif os.path.isdir(_default_path):
        _detected_path = _default_path

    game_path_input = QLineEdit(_detected_path)
    game_path_input.setReadOnly(True)
    widget_tags['GamePath'] = game_path_input
    game_path_row.addWidget(game_path_input)

    def _pick_game_path():
        path = QFileDialog.getExistingDirectory(window, tl('game_path'))
        if path:
            game_path_input.setText(path)
    game_path_row.addWidget(_launcher_icon_btn(_folder_svg, tl('game_path'), _pick_game_path))
    launcher_layout.addLayout(game_path_row)

    launcher_layout.addStretch()

    # Request account list from backend on startup
    send_queue.put(GUICommand(GUICommandType.LoadAccounts))

    # ==================== Hotkeys Tab ====================
    hotkeys_tab = QWidget()
    hotkeys_layout = QHBoxLayout(hotkeys_tab)
    hotkeys_layout.setContentsMargins(4, 4, 4, 4)

    _hotkey_h = 230

    # Toggles + Hotkeys combined panel
    combined_frame = QFrame()
    combined_frame.setStyleSheet(frame_style)
    combined_frame.setFixedWidth(280)
    combined_frame.setFixedHeight(_hotkey_h)
    combined_vbox = QVBoxLayout(combined_frame)
    combined_vbox.setContentsMargins(4, 4, 4, 4)
    combined_vbox.setSpacing(2)
    combined_vbox.addWidget(QLabel(tl('toggles')))

    toggles_data = [
        (tl('speedhack'), GUIKeys.toggle_speedhack),
        (tl('combat_toggle'), GUIKeys.toggle_combat),
        (tl('dialogue'), GUIKeys.toggle_dialogue),
        (tl('sigil'), GUIKeys.toggle_sigil),
        (tl('questing'), GUIKeys.toggle_questing),
        (tl('auto_pet'), GUIKeys.toggle_auto_pet),
        (tl('auto_potion'), GUIKeys.toggle_auto_potion),
    ]
    for i in range(0, len(toggles_data), 2):
        row = QHBoxLayout()
        # Left toggle
        name, key = toggles_data[i]
        cb = QCheckBox()
        cb.setEnabled(False)
        widget_tags[f'{name}Status'] = cb
        row.addWidget(cb)
        btn = styled_btn(name, toggle_callback(key))
        btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        row.addWidget(btn)
        # Right toggle (if exists)
        if i + 1 < len(toggles_data):
            name2, key2 = toggles_data[i + 1]
            cb2 = QCheckBox()
            cb2.setEnabled(False)
            widget_tags[f'{name2}Status'] = cb2
            row.addWidget(cb2)
            btn2 = styled_btn(name2, toggle_callback(key2))
            btn2.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            row.addWidget(btn2)
        combined_vbox.addLayout(row)

    # Toggle switch: Individual / All Clients
    combined_vbox.addSpacing(2)
    toggle_row = QHBoxLayout()
    _individual_svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{_stroke_color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12.034 12.681a.498.498 0 0 1 .647-.647l9 3.5a.5.5 0 0 1-.033.943l-3.444 1.068a1 1 0 0 0-.66.66l-1.067 3.443a.5.5 0 0 1-.943.033z"/><path d="M21 11V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h6"/></svg>'
    _mass_svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{_stroke_color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v18"/><path d="M3 12h18"/><rect x="3" y="3" width="18" height="18" rx="2"/></svg>'
    hotkey_toggle = ToggleSwitch(_individual_svg, _mass_svg, tl('hotkeys_label'), tl('mass_hotkeys'))
    toggle_row.addStretch()
    toggle_row.addWidget(hotkey_toggle)
    toggle_row.addStretch()
    combined_vbox.addLayout(toggle_row)

    hotkey_stack = AnimatedStackedWidget(duration=200)

    # Page 0: Individual hotkeys
    individual_page = QWidget()
    individual_vbox = QVBoxLayout(individual_page)
    individual_vbox.setContentsMargins(0, 0, 0, 0)
    individual_vbox.setSpacing(2)
    individual_hotkeys = [
        (tl('quest_tp'), teleport_callback(GUIKeys.hotkey_quest_tp)),
        (tl('freecam'), toggle_callback(GUIKeys.toggle_freecam)),
        (tl('freecam_tp'), teleport_callback(GUIKeys.hotkey_freecam_tp)),
    ]
    for i in range(0, len(individual_hotkeys), 2):
        row = QHBoxLayout()
        name, cb_fn = individual_hotkeys[i]
        btn = styled_btn(name, cb_fn)
        btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        row.addWidget(btn)
        if i + 1 < len(individual_hotkeys):
            name2, cb_fn2 = individual_hotkeys[i + 1]
            btn2 = styled_btn(name2, cb_fn2)
            btn2.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            row.addWidget(btn2)
        individual_vbox.addLayout(row)
    individual_vbox.addStretch()
    hotkey_stack.addWidget(individual_page)

    # Page 1: Mass hotkeys
    def xyz_sync_callback():
        send_queue.put(GUICommand(GUICommandType.XYZSync))
    def x_press_callback():
        send_queue.put(GUICommand(GUICommandType.XPress))

    mass_page = QWidget()
    mass_vbox = QVBoxLayout(mass_page)
    mass_vbox.setContentsMargins(0, 0, 0, 0)
    mass_vbox.setSpacing(2)
    mass_hotkeys = [
        (tl('mass_tp'), teleport_callback(GUIKeys.mass_hotkey_mass_tp)),
        (tl('xyz_sync'), xyz_sync_callback),
        (tl('x_press'), x_press_callback),
    ]
    for i in range(0, len(mass_hotkeys), 2):
        row = QHBoxLayout()
        name, cb_fn = mass_hotkeys[i]
        btn = styled_btn(name, cb_fn)
        btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        row.addWidget(btn)
        if i + 1 < len(mass_hotkeys):
            name2, cb_fn2 = mass_hotkeys[i + 1]
            btn2 = styled_btn(name2, cb_fn2)
            btn2.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            row.addWidget(btn2)
        mass_vbox.addLayout(row)
    mass_vbox.addStretch()
    hotkey_stack.addWidget(mass_page)

    hotkey_toggle.toggled.connect(lambda checked: hotkey_stack.slide_to(1 if checked else 0))
    combined_vbox.addWidget(hotkey_stack)

    combined_vbox.addStretch()
    hotkeys_layout.addWidget(combined_frame)

    # Tool info panel — vertically centered to match adjacent frames
    info_widget = QWidget()
    info_widget.setFixedHeight(_hotkey_h)
    info_layout = QVBoxLayout(info_widget)
    info_layout.setContentsMargins(4, 4, 4, 4)

    info_layout.addStretch()

    _logo_path = _resource_path("Deimos-logo.png")
    if os.path.exists(_logo_path):
        logo_label = QLabel()
        pixmap = QPixmap(_logo_path)
        if not pixmap.isNull():
            scaled = pixmap.scaledToHeight(80, Qt.TransformationMode.SmoothTransformation)
            logo_label.setPixmap(scaled)
            logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            info_layout.addWidget(logo_label)

    _changelog_url = f"https://github.com/{tool_author}/{tool_name}-Wizard101/releases/tag/{tool_version}"
    version_label = QLabel(f'<b>{tool_name}</b> <a href="{_changelog_url}" style="color: {_stroke_color}; text-decoration: none;">v{tool_version}</a>')
    version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    version_label.setOpenExternalLinks(True)
    info_layout.addWidget(version_label)

    # Repo links row
    _repo_base = f"https://github.com/{tool_author}/{tool_name}-Wizard101"
    _wiki_base = f"{_repo_base}/wiki"
    repo_links_row = QHBoxLayout()
    repo_links_row.setSpacing(4)



    _license_svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{_stroke_color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v18"/><path d="m19 8 3 8a5 5 0 0 1-6 0zV7"/><path d="M3 7h1a17 17 0 0 0 8-2 17 17 0 0 0 8 2h1"/><path d="m5 8 3 8a5 5 0 0 1-6 0zV7"/><path d="M7 21h10"/></svg>'
    _readme_svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{_stroke_color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>'
    _source_svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{_stroke_color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 6a9 9 0 0 0-9 9V3"/><circle cx="18" cy="6" r="3"/><circle cx="6" cy="18" r="3"/></svg>'
    _discord_svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{_stroke_color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3H4a2 2 0 0 0-2 2v16.286a.71.71 0 0 0 1.212.502l2.202-2.202A2 2 0 0 1 6.828 19H20a2 2 0 0 0 2-2v-4"/><path d="M16 3h6v6"/><path d="m16 9 6-6"/></svg>'
    _clipboard_svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{_stroke_color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="8" height="4" x="8" y="2" rx="1" ry="1"/><path d="M8 4H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"/><path d="M16 4h2a2 2 0 0 1 2 2v4"/><path d="M21 14H11"/><path d="m15 10-4 4 4 4"/></svg>'

    def _svg_icon(svg_str):
        renderer = QSvgRenderer(svg_str.encode())
        pixmap = QPixmap(24, 24)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        return QIcon(pixmap)

    def _repo_icon_btn(svg_str, tooltip, url):
        btn = QPushButton()
        btn.setToolTip(tooltip)
        btn.setStyleSheet(icon_btn_style)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedSize(24, 24)
        btn.setIcon(_svg_icon(svg_str))
        btn.clicked.connect(lambda: webbrowser.open(url))
        return btn

    _info_svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{_stroke_color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2.992 16.342a2 2 0 0 1 .094 1.167l-1.065 3.29a1 1 0 0 0 1.236 1.168l3.413-.998a2 2 0 0 1 1.099.092 10 10 0 1 0-4.777-4.719"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><path d="M12 17h.01"/></svg>'

    def _section_group(title, tooltip_text):
        group = QGroupBox()
        group.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        layout = QVBoxLayout(group)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(2)
        header = QHBoxLayout()
        header.addWidget(QLabel(f"<b>{title}</b>"))
        header.addStretch()
        info_btn = QPushButton()
        info_btn.setIcon(_titlebar_svg_icon(_info_svg, 16))
        info_btn.setFixedSize(20, 20)
        info_btn.setStyleSheet(icon_btn_style)
        info_btn.setToolTip(tooltip_text)
        info_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        header.addWidget(info_btn)
        layout.addLayout(header)
        return group, layout

    repo_links_row.addStretch()
    repo_links_row.addWidget(_repo_icon_btn(_license_svg, tl('tooltip_license'), f"{_repo_base}/blob/main/LICENSE"))
    repo_links_row.addWidget(_repo_icon_btn(_readme_svg, tl('tooltip_wiki_hotkeys'), f"{_wiki_base}/Hotkeys"))
    repo_links_row.addWidget(_repo_icon_btn(_source_svg, tl('tooltip_source_code'), _repo_base))
    repo_links_row.addWidget(_repo_icon_btn(_discord_svg, tl('tooltip_discord'), "https://discord.gg/59UrPJwYDm"))
    repo_links_row.addStretch()
    info_layout.addLayout(repo_links_row)

    info_layout.addStretch()
    hotkeys_layout.addWidget(info_widget)

    tabs.addTab(launcher_tab, tl('launcher'))
    tabs.addTab(hotkeys_tab, tl('hotkeys'))

    # ==================== Camera Tab ====================
    camera_tab = QWidget()
    cam_layout = QVBoxLayout(camera_tab)
    cam_layout.setContentsMargins(4, 4, 4, 4)
    cam_layout.setSpacing(4)
    cam_header = QHBoxLayout()
    cam_header.addWidget(centered_label(tl('advanced_warning')), 1)
    cam_header.addWidget(_repo_icon_btn(_readme_svg, tl('tooltip_wiki_camera'), f"{_wiki_base}/Camera"))
    cam_layout.addLayout(cam_header)

    cam_inputs = {}

    # --- Position group: XYZ + Yaw/Roll/Pitch in a compact grid ---
    pos_group, pos_vbox = _section_group(tl('set_camera_position'), tl('tooltip_section_camera_position'))
    pos_grid = QGridLayout()
    pos_grid.setHorizontalSpacing(4)
    pos_grid.setVerticalSpacing(2)

    for col, (placeholder, tag) in enumerate([('X', 'CamXInput'), ('Y', 'CamYInput'), ('Z', 'CamZInput'),
                                               (tl('yaw'), 'CamYawInput'), (tl('roll'), 'CamRollInput'), (tl('pitch'), 'CamPitchInput')]):
        inp = QLineEdit()
        inp.setPlaceholderText(placeholder)
        inp.setFixedWidth(70)
        cam_inputs[tag] = inp
        widget_tags[tag] = inp
        pos_grid.addWidget(inp, 0, col)

    def set_cam_pos_callback():
        inputs = [cam_inputs['CamXInput'].text(), cam_inputs['CamYInput'].text(), cam_inputs['CamZInput'].text(),
                  cam_inputs['CamYawInput'].text(), cam_inputs['CamRollInput'].text(), cam_inputs['CamPitchInput'].text()]
        if any(inputs):
            send_queue.put(GUICommand(GUICommandType.SetCamPosition, {
                'X': inputs[0], 'Y': inputs[1], 'Z': inputs[2],
                'Yaw': inputs[3], 'Roll': inputs[4], 'Pitch': inputs[5],
            }))

    pos_grid.addWidget(styled_btn(tl('set_camera_position'), set_cam_pos_callback), 0, 6)
    pos_vbox.addLayout(pos_grid)
    cam_layout.addWidget(pos_group)

    # --- Anchor + Distance in one row using two side-by-side groups ---
    mid_row = QHBoxLayout()
    mid_row.setSpacing(4)

    anchor_group, anchor_vbox = _section_group(tl('anchor'), tl('tooltip_section_anchor'))
    anchor_lay = QHBoxLayout()
    cam_entity_input = QLineEdit()
    cam_entity_input.setPlaceholderText(tl('entity'))
    cam_entity_input.setMinimumWidth(80)
    cam_inputs['CamEntityInput'] = cam_entity_input
    widget_tags['CamEntityInput'] = cam_entity_input
    anchor_lay.addWidget(cam_entity_input, 1)

    def anchor_callback():
        send_queue.put(GUICommand(GUICommandType.AnchorCam, cam_entity_input.text()))
    anchor_lay.addWidget(styled_btn(tl('anchor'), anchor_callback))
    anchor_lay.addWidget(styled_btn(tl('toggle_camera_collision'), toggle_callback(GUIKeys.toggle_camera_collision)))
    anchor_vbox.addLayout(anchor_lay)
    mid_row.addWidget(anchor_group)

    dist_group, dist_vbox = _section_group(tl('set_distance'), tl('tooltip_section_distance'))
    dist_lay = QHBoxLayout()
    for placeholder, tag in [(tl('distance'), 'CamDistanceInput'), (tl('min'), 'CamMinInput'), (tl('max'), 'CamMaxInput')]:
        inp = QLineEdit()
        inp.setPlaceholderText(placeholder)
        inp.setFixedWidth(65)
        cam_inputs[tag] = inp
        widget_tags[tag] = inp
        dist_lay.addWidget(inp)

    def set_distance_callback():
        inputs = [cam_inputs['CamDistanceInput'].text(), cam_inputs['CamMinInput'].text(), cam_inputs['CamMaxInput'].text()]
        if any(inputs):
            send_queue.put(GUICommand(GUICommandType.SetCamDistance, {
                "Distance": inputs[0], "Min": inputs[1], "Max": inputs[2],
            }))
    dist_lay.addWidget(styled_btn(tl('set_distance'), set_distance_callback))
    dist_vbox.addLayout(dist_lay)
    mid_row.addWidget(dist_group)

    cam_layout.addLayout(mid_row)

    # --- Utils group ---
    cam_utils_group, cam_utils_vbox = _section_group("Utils", tl('tooltip_section_utils'))
    cam_utils_lay = QHBoxLayout()
    cam_utils_lay.setSpacing(3)

    def populate_camera_callback():
        send_queue.put(GUICommand(GUICommandType.PopulateCamera))

    cam_utils_lay.addWidget(styled_btn("Populate", populate_camera_callback))
    cam_utils_lay.addWidget(styled_btn(tl('copy_camera_position'), copy_callback(GUIKeys.copy_camera_position)))
    cam_utils_lay.addStretch()
    cam_utils_vbox.addLayout(cam_utils_lay)
    cam_layout.addWidget(cam_utils_group)

    cam_layout.addStretch()
    tabs.addTab(camera_tab, tl('camera'))

    # ==================== Dev Utils Tab ====================
    dev_tab = QWidget()
    dev_layout = QVBoxLayout(dev_tab)
    dev_layout.setContentsMargins(4, 4, 4, 4)
    dev_layout.setSpacing(4)
    dev_header = QHBoxLayout()
    dev_header.addWidget(centered_label(tl('advanced_warning')), 1)
    dev_header.addWidget(_repo_icon_btn(_readme_svg, tl('tooltip_wiki_utilities'), f"{_wiki_base}/Utilities"))
    dev_layout.addLayout(dev_header)

    dev_inputs = {}

    # --- Teleport group ---
    tp_group, tp_lay = _section_group(tl('tp_utils'), tl('tooltip_section_tp_utils'))

    # Coordinate TP: compact row with placeholder text instead of labels
    coord_row = QHBoxLayout()
    coord_row.setSpacing(3)
    for placeholder, tag, w in [('X', 'XInput', 50), ('Y', 'YInput', 50), ('Z', 'ZInput', 50), (tl('yaw'), 'YawInput', 50)]:
        inp = QLineEdit()
        inp.setPlaceholderText(placeholder)
        inp.setFixedWidth(w)
        dev_inputs[tag] = inp
        widget_tags[tag] = inp
        coord_row.addWidget(inp)

    def custom_tp_callback():
        tp_vals = [dev_inputs['XInput'].text(), dev_inputs['YInput'].text(), dev_inputs['ZInput'].text(), dev_inputs['YawInput'].text()]
        if any(tp_vals):
            send_queue.put(GUICommand(GUICommandType.CustomTeleport, {
                'X': tp_vals[0], 'Y': tp_vals[1], 'Z': tp_vals[2], 'Yaw': tp_vals[3],
            }))

    coord_row.addWidget(styled_btn(tl('custom_tp'), custom_tp_callback))
    coord_row.addStretch()
    tp_lay.addLayout(coord_row)

    # Entity TP
    ent_row = QHBoxLayout()
    ent_row.setSpacing(3)
    entity_tp_input = QLineEdit()
    entity_tp_input.setPlaceholderText(tl('entity_name'))
    dev_inputs['EntityTPInput'] = entity_tp_input
    widget_tags['EntityTPInput'] = entity_tp_input
    ent_row.addWidget(entity_tp_input, 1)

    def entity_tp_callback():
        val = entity_tp_input.text()
        if val:
            send_queue.put(GUICommand(GUICommandType.EntityTeleport, val))

    ent_row.addWidget(styled_btn(tl('entity_tp'), entity_tp_callback))
    tp_lay.addLayout(ent_row)

    dev_layout.addWidget(tp_group)

    # --- Navigation group ---
    nav_group, nav_vbox = _section_group("Navigation", tl('tooltip_section_navigation'))
    nav_outer = QHBoxLayout()
    nav_outer.setSpacing(6)

    # Vertical toggle on the left
    nav_toggle = ToggleSwitch(_individual_svg, _mass_svg, "Individual", "All Clients", vertical=True)
    nav_outer.addWidget(nav_toggle, 0, Qt.AlignmentFlag.AlignVCenter)

    # Content on the right (wrapped in a widget for vertical centering)
    nav_content_widget = QWidget()
    nav_content = QVBoxLayout(nav_content_widget)
    nav_content.setContentsMargins(0, 0, 0, 0)
    nav_content.setSpacing(2)

    # Inputs row (always visible above the animated stack)
    nav_inputs_row = QHBoxLayout()
    nav_inputs_row.setSpacing(3)

    zone_input = QLineEdit()
    zone_input.setPlaceholderText(tl('zone_name'))
    dev_inputs['ZoneInput'] = zone_input
    widget_tags['ZoneInput'] = zone_input
    nav_inputs_row.addWidget(zone_input, 1)

    worlds = ['WizardCity', 'Krokotopia', 'Marleybone', 'MooShu', 'DragonSpire', 'Grizzleheim', 'Celestia', 'Wysteria', 'Zafaria', 'Avalon', 'Azteca', 'Khrysalis', 'Polaris', 'Mirage', 'Empyrea', 'Karamelle', 'Lemuria']
    world_combo = QComboBox()
    world_combo.addItems(worlds)
    world_combo.setCurrentText('WizardCity')
    world_combo.setFixedWidth(100)
    dev_inputs['WorldInput'] = world_combo
    widget_tags['WorldInput'] = world_combo
    nav_inputs_row.addWidget(world_combo)
    nav_inputs_row.addStretch()
    nav_content.addLayout(nav_inputs_row)

    # Animated stack for individual/mass buttons
    nav_stack = AnimatedStackedWidget(duration=200)

    # Page 0: Individual buttons
    nav_indiv_page = QWidget()
    nav_indiv_lay = QVBoxLayout(nav_indiv_page)
    nav_indiv_lay.setContentsMargins(0, 0, 0, 0)
    nav_indiv_lay.setSpacing(2)

    def go_to_zone_callback():
        val = zone_input.text()
        if val:
            send_queue.put(GUICommand(GUICommandType.GoToZone, (False, str(val))))

    def go_to_world_callback():
        val = world_combo.currentText()
        if val:
            send_queue.put(GUICommand(GUICommandType.GoToWorld, (False, val)))

    def go_to_bazaar_callback():
        send_queue.put(GUICommand(GUICommandType.GoToBazaar, False))

    def refill_potions_callback():
        send_queue.put(GUICommand(GUICommandType.RefillPotions, False))

    indiv_btn_row = QHBoxLayout()
    indiv_btn_row.setSpacing(3)
    indiv_btn_row.addWidget(styled_btn(tl('go_to_zone'), go_to_zone_callback))
    indiv_btn_row.addWidget(styled_btn(tl('go_to_world'), go_to_world_callback))
    indiv_btn_row.addWidget(styled_btn(tl('go_to_bazaar'), go_to_bazaar_callback))
    indiv_btn_row.addWidget(styled_btn(tl('refill_potions'), refill_potions_callback))
    indiv_btn_row.addStretch()
    nav_indiv_lay.addLayout(indiv_btn_row)
    nav_indiv_lay.addStretch()
    nav_stack.addWidget(nav_indiv_page)

    # Page 1: Mass buttons
    nav_mass_page = QWidget()
    nav_mass_lay = QVBoxLayout(nav_mass_page)
    nav_mass_lay.setContentsMargins(0, 0, 0, 0)
    nav_mass_lay.setSpacing(2)

    def mass_go_to_zone_callback():
        val = zone_input.text()
        if val:
            send_queue.put(GUICommand(GUICommandType.GoToZone, (True, str(val))))

    def mass_go_to_world_callback():
        val = world_combo.currentText()
        if val:
            send_queue.put(GUICommand(GUICommandType.GoToWorld, (True, val)))

    def mass_go_to_bazaar_callback():
        send_queue.put(GUICommand(GUICommandType.GoToBazaar, True))

    def mass_refill_potions_callback():
        send_queue.put(GUICommand(GUICommandType.RefillPotions, True))

    mass_btn_row = QHBoxLayout()
    mass_btn_row.setSpacing(3)
    mass_btn_row.addWidget(styled_btn(tl('mass_go_to_zone'), mass_go_to_zone_callback))
    mass_btn_row.addWidget(styled_btn(tl('mass_go_to_world'), mass_go_to_world_callback))
    mass_btn_row.addWidget(styled_btn(tl('mass_go_to_bazaar'), mass_go_to_bazaar_callback))
    mass_btn_row.addWidget(styled_btn(tl('mass_refill_potions'), mass_refill_potions_callback))
    mass_btn_row.addStretch()
    nav_mass_lay.addLayout(mass_btn_row)
    nav_mass_lay.addStretch()
    nav_stack.addWidget(nav_mass_page)

    nav_toggle.toggled.connect(lambda checked: nav_stack.slide_to(1 if checked else 0))
    nav_content.addWidget(nav_stack)

    nav_outer.addWidget(nav_content_widget, 1, Qt.AlignmentFlag.AlignVCenter)
    nav_vbox.addLayout(nav_outer)

    dev_layout.addWidget(nav_group)

    # --- Misc. group (moved from Misc tab) ---
    misc_group, misc_vbox = _section_group(tl('misc'), tl('tooltip_section_misc'))
    misc_lay = QHBoxLayout()
    misc_lay.setSpacing(3)

    misc_lay.addWidget(QLabel(tl('scale') + ':'))
    scale_input = QLineEdit()
    scale_input.setFixedWidth(50)
    widget_tags['scale'] = scale_input
    misc_lay.addWidget(scale_input)

    def set_scale_callback():
        send_queue.put(GUICommand(GUICommandType.SetScale, scale_input.text()))

    misc_lay.addWidget(styled_btn(tl('set_scale'), set_scale_callback))

    misc_lay.addSpacing(8)

    misc_lay.addWidget(QLabel(tl('select_pet_world')))
    pet_worlds = ['WizardCity', 'Krokotopia', 'Marleybone', 'Mooshu', 'Dragonspyre']
    pet_combo = QComboBox()
    pet_combo.addItems(pet_worlds)
    pet_combo.setCurrentText('WizardCity')
    pet_combo.setFixedWidth(100)
    widget_tags['PetWorldInput'] = pet_combo

    def pet_world_callback(text):
        if text != wizard_city_dance_game_path[-1]:
            assign_pet_level(text)

    pet_combo.currentTextChanged.connect(pet_world_callback)
    misc_lay.addWidget(pet_combo)
    misc_lay.addStretch()
    misc_vbox.addLayout(misc_lay)

    dev_layout.addWidget(misc_group)

    dev_layout.addStretch()
    tabs.addTab(dev_tab, tl('utilities'))

    # Shared action icons for stats/flythrough/bot/combat tabs
    _import_svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{_stroke_color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 22a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h8a2.4 2.4 0 0 1 1.704.706l3.588 3.588A2.4 2.4 0 0 1 20 8v12a2 2 0 0 1-2 2z"/><path d="M14 2v5a1 1 0 0 0 1 1h5"/><path d="M12 12v6"/><path d="m15 15-3-3-3 3"/></svg>'
    _export_svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{_stroke_color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 22a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h8a2.4 2.4 0 0 1 1.704.706l3.588 3.588A2.4 2.4 0 0 1 20 8v12a2 2 0 0 1-2 2z"/><path d="M14 2v5a1 1 0 0 0 1 1h5"/><path d="M12 18v-6"/><path d="m9 15 3 3 3-3"/></svg>'
    _play_svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{_stroke_color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 5a2 2 0 0 1 3.008-1.728l11.997 6.998a2 2 0 0 1 .003 3.458l-12 7A2 2 0 0 1 5 19z"/></svg>'
    _kill_svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{_stroke_color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.513 4.856 13.12 2.17a.5.5 0 0 1 .86.46l-1.377 4.317"/><path d="M15.656 10H20a1 1 0 0 1 .78 1.63l-1.72 1.773"/><path d="M16.273 16.273 10.88 21.83a.5.5 0 0 1-.86-.46l1.92-6.02A1 1 0 0 0 11 14H4a1 1 0 0 1-.78-1.63l4.507-4.643"/><path d="m2 2 20 20"/></svg>'
    _refresh_svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{_stroke_color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/></svg>'

    def _action_icon_btn(svg_str, tooltip, callback):
        btn = QPushButton()
        btn.setIcon(_titlebar_svg_icon(svg_str, 32))
        btn.setFixedSize(40, 40)
        btn.setStyleSheet(icon_btn_style)
        btn.setToolTip(tooltip)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(callback)
        return btn

    # ==================== Stats Tab ====================
    stats_tab = QWidget()
    stats_layout = QVBoxLayout(stats_tab)
    stats_layout.setContentsMargins(4, 4, 4, 4)
    stats_layout.setSpacing(4)

    # Header row — warning + wiki icon
    stats_header = QHBoxLayout()
    stats_header.addWidget(centered_label(tl('advanced_warning')), 1)
    stats_header.addWidget(_repo_icon_btn(_readme_svg, tl('tooltip_wiki_stats'), f"{_wiki_base}/Stats"))
    stats_layout.addLayout(stats_header)

    # Radial duel circle widget
    duel_circle = DuelCircleWidget(stroke_color=_stroke_color, text_color=_text_color, bg_color=_bg_color)
    stats_layout.addWidget(duel_circle, alignment=Qt.AlignmentFlag.AlignCenter)

    # Damage calculation config (lives inside a popup dialog)
    stats_inputs = {}

    damage_input = QLineEdit()
    damage_input.setFixedWidth(50)
    damage_input.setPlaceholderText(tl('dmg'))
    stats_inputs['DamageInput'] = damage_input
    widget_tags['DamageInput'] = damage_input

    schools = ['Fire', 'Ice', 'Storm', 'Myth', 'Life', 'Death', 'Balance', 'Star', 'Sun', 'Moon', 'Shadow']
    school_combo = QComboBox()
    school_combo.addItems(schools)
    school_combo.setCurrentText('Fire')
    school_combo.setFixedWidth(80)
    stats_inputs['SchoolInput'] = school_combo
    widget_tags['SchoolInput'] = school_combo

    crit_check = QCheckBox(tl('crit'))
    crit_check.setChecked(True)
    stats_inputs['CritStatus'] = crit_check
    widget_tags['CritStatus'] = crit_check

    force_school_check = QCheckBox(tl('force_school_damage'))
    stats_inputs['ForceSchoolStatus'] = force_school_check
    widget_tags['ForceSchoolStatus'] = force_school_check

    _dmg_calc_popup = [None]

    def _show_dmg_calc_popup():
        if _dmg_calc_popup[0] is not None and _dmg_calc_popup[0].isVisible():
            _dmg_calc_popup[0].raise_()
            return

        dialog = QDialog(window)
        dialog.setWindowTitle(tl('dmg'))
        dialog.setWindowFlags(dialog.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        dlg_layout = QVBoxLayout(dialog)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel(tl('dmg') + ':'))
        row1.addWidget(damage_input)
        row1.addWidget(QLabel(tl('school') + ':'))
        row1.addWidget(school_combo)
        dlg_layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(crit_check)
        row2.addWidget(force_school_check)
        row2.addStretch()
        dlg_layout.addLayout(row2)

        close_btn = styled_btn("Close", dialog.close)
        dlg_layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        dialog.adjustSize()
        dialog.setFixedSize(dialog.sizeHint())
        _dmg_calc_popup[0] = dialog
        dialog.show()

    # Stat popup dialog (non-modal, reusable)
    _stat_popup = [None]

    def _get_or_create_stat_popup():
        if _stat_popup[0] is not None and _stat_popup[0].isVisible():
            return _stat_popup[0]

        dialog = QDialog(window)
        dialog.setWindowTitle("Combat Stats")
        dialog.setWindowFlags(dialog.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        dialog.resize(400, 300)
        dlg_layout = QVBoxLayout(dialog)

        stat_text = QTextEdit()
        stat_text.setPlainText(tl('no_client_selected'))
        stat_text.setReadOnly(True)
        widget_tags['stat_viewer'] = stat_text
        dlg_layout.addWidget(stat_text)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        copy_stat_btn = QPushButton()
        copy_stat_btn.setIcon(_titlebar_svg_icon(_clipboard_svg, 16))
        copy_stat_btn.setFixedSize(28, 28)
        copy_stat_btn.setStyleSheet(icon_btn_style)
        copy_stat_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        copy_stat_btn.setToolTip(tl('copy_stats'))
        copy_stat_btn.clicked.connect(lambda: pyperclip.copy(stat_text.toPlainText()))
        btn_row.addWidget(copy_stat_btn)

        close_btn = styled_btn("Close", dialog.close)
        btn_row.addWidget(close_btn)
        btn_row.addStretch()
        dlg_layout.addLayout(btn_row)

        _stat_popup[0] = dialog
        return dialog

    # View stats callback — sends command and opens popup
    def view_stats_callback():
        base_damage = re.sub(r'[^0-9]', '', str(damage_input.text()))
        school_id: int = school_id_to_names[school_combo.currentText()]
        send_queue.put(GUICommand(GUICommandType.SelectEnemy, (
            duel_circle.selected_target(),
            duel_circle.selected_caster(),
            base_damage, school_id,
            crit_check.isChecked(),
            force_school_check.isChecked()
        )))
        popup = _get_or_create_stat_popup()
        popup.show()
        popup.raise_()

    # Action icon SVGs
    _eye_svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{_stroke_color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2.062 12.348a1 1 0 0 1 0-.696 10.75 10.75 0 0 1 19.876 0 1 1 0 0 1 0 .696 10.75 10.75 0 0 1-19.876 0"/><circle cx="12" cy="12" r="3"/></svg>'
    _calc_svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{_stroke_color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="16" height="20" x="4" y="2" rx="2"/><line x1="8" x2="16" y1="6" y2="6"/><line x1="16" x2="16" y1="14" y2="18"/><path d="M16 10h.01"/><path d="M12 10h.01"/><path d="M8 10h.01"/><path d="M12 14h.01"/><path d="M8 14h.01"/><path d="M12 18h.01"/><path d="M8 18h.01"/></svg>'

    # Centered action icons — Damage Config + View Stats
    stats_btn_row = QHBoxLayout()
    stats_btn_row.addStretch()
    stats_btn_row.addWidget(_action_icon_btn(_calc_svg, tl('dmg'), _show_dmg_calc_popup))
    stats_btn_row.addWidget(_action_icon_btn(_eye_svg, tl('view_stats'), view_stats_callback))
    stats_btn_row.addStretch()
    stats_layout.addLayout(stats_btn_row)

    stats_layout.addStretch()
    tabs.addTab(stats_tab, tl('stats'))

    # ==================== Flythrough Tab ====================
    flythrough_tab = QWidget()
    fly_layout = QVBoxLayout(flythrough_tab)
    fly_layout.setContentsMargins(4, 4, 4, 4)
    fly_header = QHBoxLayout()
    fly_header.addWidget(centered_label(tl('advanced_warning')), 1)
    fly_header.addWidget(_repo_icon_btn(_readme_svg, tl('tooltip_wiki_flythroughs'), f"{_wiki_base}/Flythroughs"))
    fly_layout.addLayout(fly_header)

    flythrough_editor = QTextEdit()
    flythrough_editor.setFixedHeight(150)
    widget_tags['flythrough_creator'] = flythrough_editor
    fly_layout.addWidget(flythrough_editor)

    fly_btn_row = QHBoxLayout()

    def flythrough_import():
        filepath, _ = QFileDialog.getOpenFileName(window, "Import Flythrough", "", "Text Files (*.txt)")
        if filepath:
            try:
                with open(filepath) as f:
                    flythrough_editor.setPlainText(f.read())
            except Exception:
                pass

    def flythrough_export():
        filepath, _ = QFileDialog.getSaveFileName(window, "Export Flythrough", "flythrough.txt", "Text Files (*.txt)")
        if filepath:
            try:
                with open(filepath, 'w') as f:
                    f.write(flythrough_editor.toPlainText())
            except Exception:
                pass

    def execute_flythrough_callback():
        send_queue.put(GUICommand(GUICommandType.ExecuteFlythrough, flythrough_editor.toPlainText()))

    def kill_flythrough_callback():
        send_queue.put(GUICommand(GUICommandType.KillFlythrough))

    fly_btn_row.addStretch()
    fly_btn_row.addWidget(_action_icon_btn(_import_svg, tl('import_flythrough'), flythrough_import))
    fly_btn_row.addWidget(_action_icon_btn(_export_svg, tl('export_flythrough'), flythrough_export))
    fly_btn_row.addWidget(_action_icon_btn(_play_svg, tl('execute_flythrough'), execute_flythrough_callback))
    fly_btn_row.addWidget(_action_icon_btn(_kill_svg, tl('kill_flythrough'), kill_flythrough_callback))
    fly_btn_row.addStretch()
    fly_layout.addLayout(fly_btn_row)

    fly_layout.addStretch()
    tabs.addTab(flythrough_tab, tl('flythrough'))

    # ==================== Bot Tab ====================
    bot_tab = QWidget()
    bot_layout = QVBoxLayout(bot_tab)
    bot_layout.setContentsMargins(4, 4, 4, 4)
    bot_header = QHBoxLayout()
    bot_header.addWidget(centered_label(tl('advanced_warning')), 1)
    bot_header.addWidget(_repo_icon_btn(_readme_svg, tl('tooltip_wiki_bots'), f"{_wiki_base}/Bots"))
    bot_layout.addLayout(bot_header)

    bot_editor = QTextEdit()
    bot_editor.setFixedHeight(150)
    widget_tags['bot_creator'] = bot_editor
    bot_layout.addWidget(bot_editor)

    bot_btn_row = QHBoxLayout()

    def bot_import():
        filepath, _ = QFileDialog.getOpenFileName(window, "Import Bot", "", "Text Files (*.txt)")
        if filepath:
            try:
                with open(filepath) as f:
                    bot_editor.setPlainText(f.read())
            except Exception:
                pass

    def bot_export():
        filepath, _ = QFileDialog.getSaveFileName(window, "Export Bot", "bot.txt", "Text Files (*.txt)")
        if filepath:
            try:
                with open(filepath, 'w') as f:
                    f.write(bot_editor.toPlainText())
            except Exception:
                pass

    def run_bot_callback():
        send_queue.put(GUICommand(GUICommandType.ExecuteBot, bot_editor.toPlainText()))

    def kill_bot_callback():
        send_queue.put(GUICommand(GUICommandType.KillBot))

    bot_btn_row.addStretch()
    bot_btn_row.addWidget(_action_icon_btn(_import_svg, tl('import_bot'), bot_import))
    bot_btn_row.addWidget(_action_icon_btn(_export_svg, tl('export_bot'), bot_export))
    bot_btn_row.addWidget(_action_icon_btn(_play_svg, tl('run_bot'), run_bot_callback))
    bot_btn_row.addWidget(_action_icon_btn(_kill_svg, tl('kill_bot'), kill_bot_callback))
    bot_btn_row.addStretch()
    bot_layout.addLayout(bot_btn_row)

    bot_layout.addStretch()
    tabs.addTab(bot_tab, tl('bot'))

    # ==================== Combat Tab ====================
    combat_tab = QWidget()
    combat_layout = QVBoxLayout(combat_tab)
    combat_layout.setContentsMargins(4, 4, 4, 4)
    combat_header = QHBoxLayout()
    combat_header.addWidget(centered_label(tl('advanced_warning')), 1)
    combat_header.addWidget(_repo_icon_btn(_readme_svg, tl('tooltip_wiki_playstyles'), f"{_wiki_base}/Playstyles"))
    combat_layout.addLayout(combat_header)

    combat_editor = QTextEdit()
    combat_editor.setFixedHeight(150)
    widget_tags['combat_config'] = combat_editor
    combat_layout.addWidget(combat_editor)

    combat_btn_row = QHBoxLayout()

    def combat_import():
        filepath, _ = QFileDialog.getOpenFileName(window, "Import Playstyle", "", "Text Files (*.txt)")
        if filepath:
            try:
                with open(filepath) as f:
                    combat_editor.setPlainText(f.read())
            except Exception:
                pass

    def combat_export():
        filepath, _ = QFileDialog.getSaveFileName(window, "Export Playstyle", "playstyle.txt", "Text Files (*.txt)")
        if filepath:
            try:
                with open(filepath, 'w') as f:
                    f.write(combat_editor.toPlainText())
            except Exception:
                pass

    def set_playstyles_callback():
        send_queue.put(GUICommand(GUICommandType.SetPlaystyles, combat_editor.toPlainText()))

    combat_btn_row.addStretch()
    combat_btn_row.addWidget(_action_icon_btn(_import_svg, tl('import_playstyle'), combat_import))
    combat_btn_row.addWidget(_action_icon_btn(_export_svg, tl('export_playstyle'), combat_export))
    combat_btn_row.addWidget(_action_icon_btn(_refresh_svg, tl('set_playstyles'), set_playstyles_callback))
    combat_btn_row.addStretch()
    combat_layout.addLayout(combat_btn_row)

    combat_layout.addStretch()
    tabs.addTab(combat_tab, tl('combat'))

    # ==================== Console Tab ====================
    console_tab = QWidget()
    console_layout = QVBoxLayout(console_tab)
    console_layout.setContentsMargins(4, 4, 4, 4)
    console_layout.addWidget(centered_label(tl('console_support')))

    console_text = ConsoleTextEdit()
    console_text.setReadOnly(True)
    console_text.setFixedHeight(150)
    widget_tags['-CONSOLE-'] = console_text
    console_layout.addWidget(console_text)

    _expand_svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{_stroke_color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 12h6"/><path d="M8 12H2"/><path d="M12 2v2"/><path d="M12 8v2"/><path d="M12 14v2"/><path d="M12 20v2"/><path d="m19 15 3-3-3-3"/><path d="m5 9-3 3 3 3"/></svg>'
    _collapse_svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{_stroke_color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12h6"/><path d="M22 12h-6"/><path d="M12 2v2"/><path d="M12 8v2"/><path d="M12 14v2"/><path d="M12 20v2"/><path d="m19 9-3 3 3 3"/><path d="m5 15 3-3-3-3"/></svg>'
    _copy_logs_svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{_stroke_color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="8" height="4" x="8" y="2" rx="1" ry="1"/><path d="M8 4H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"/><path d="M16 4h2a2 2 0 0 1 2 2v4"/><path d="M21 14H11"/><path d="m15 10-4 4 4 4"/></svg>'

    _expand_icon = _titlebar_svg_icon(_expand_svg, 32)
    _collapse_icon = _titlebar_svg_icon(_collapse_svg, 32)
    _logs_expanded = [False]

    toggle_expand_btn = QPushButton()
    toggle_expand_btn.setIcon(_expand_icon)
    toggle_expand_btn.setFixedSize(40, 40)
    toggle_expand_btn.setStyleSheet(icon_btn_style)
    toggle_expand_btn.setToolTip(tl('collapse_expand_logs'))
    toggle_expand_btn.setCursor(Qt.CursorShape.PointingHandCursor)

    def _toggle_expand_logs():
        _logs_expanded[0] = not _logs_expanded[0]
        toggle_expand_btn.setIcon(_collapse_icon if _logs_expanded[0] else _expand_icon)
        console_psg.toggle_show_expanded_logs()

    toggle_expand_btn.clicked.connect(_toggle_expand_logs)

    console_btn_row = QHBoxLayout()
    console_btn_row.addStretch()
    console_btn_row.addWidget(toggle_expand_btn)
    console_btn_row.addWidget(_action_icon_btn(_copy_logs_svg, tl('copy_logs'), copy_callback(GUIKeys.copy_logs)))
    console_btn_row.addStretch()
    console_layout.addLayout(console_btn_row)

    console_layout.addStretch()
    tabs.addTab(console_tab, tl('console'))

    # ==================== Client Info Footer ====================
    content_layout.addWidget(QFrame(frameShape=QFrame.Shape.HLine))

    footer_vbox = QVBoxLayout()
    footer_vbox.setContentsMargins(0, 0, 0, 0)
    footer_vbox.setSpacing(1)

    def _footer_row(label_widget, *buttons):
        row = QHBoxLayout()
        row.addWidget(label_widget)
        row.addStretch()
        for btn in buttons:
            row.addWidget(btn)
        return row

    _entity_svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{_stroke_color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="5" r="1"/><path d="m9 20 3-6 3 6"/><path d="m6 8 6 2 6-2"/><path d="M12 10v4"/></svg>'
    _window_svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{_stroke_color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="18" x="3" y="3" rx="2"/><path d="M3 9h18"/><path d="M9 21V9"/></svg>'

    client_label = QLabel(tl('client') + ': ')
    widget_tags['Title'] = client_label

    entities_btn = QPushButton()
    entities_btn.setIcon(_titlebar_svg_icon(_entity_svg, 16))
    entities_btn.setFixedSize(20, 20)
    entities_btn.setStyleSheet(icon_btn_style)
    entities_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    entities_btn.setToolTip(tl('available_entities'))
    entities_btn.clicked.connect(copy_callback(GUIKeys.copy_entity_list))

    paths_btn = QPushButton()
    paths_btn.setIcon(_titlebar_svg_icon(_window_svg, 16))
    paths_btn.setFixedSize(20, 20)
    paths_btn.setStyleSheet(icon_btn_style)
    paths_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    paths_btn.setToolTip(tl('available_paths'))
    paths_btn.clicked.connect(copy_callback(GUIKeys.copy_ui_tree))

    footer_vbox.addLayout(_footer_row(client_label, entities_btn, paths_btn))

    def _copy_icon_btn(callback):
        btn = QPushButton()
        btn.setIcon(_titlebar_svg_icon(_clipboard_svg, 16))
        btn.setFixedSize(20, 20)
        btn.setStyleSheet(icon_btn_style)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolTip("Copy")
        btn.clicked.connect(callback)
        return btn

    zone_label = QLabel(tl('zone') + ': ')
    widget_tags['Zone'] = zone_label
    footer_vbox.addLayout(_footer_row(zone_label, _copy_icon_btn(copy_callback(GUIKeys.copy_zone))))

    xyz_label = QLabel("Position (XYZ): ")
    widget_tags['xyz'] = xyz_label
    footer_vbox.addLayout(_footer_row(xyz_label, _copy_icon_btn(copy_callback(GUIKeys.copy_position))))

    pry_label = QLabel("Orientation (PRY): ")
    widget_tags['pry'] = pry_label
    footer_vbox.addLayout(_footer_row(pry_label, _copy_icon_btn(copy_callback(GUIKeys.copy_rotation))))

    content_layout.addLayout(footer_vbox)

    # ==================== Console Sink ====================
    global console_sink
    console_psg = PyQtSink(console_text)
    console_sink = logger.add(console_psg, colorize=True)

    # ==================== License Popup ====================
    license_dialog = QDialog(window)
    license_dialog.setWindowTitle(tl('license_title'))
    license_dialog.setModal(True)
    ld_layout = QVBoxLayout(license_dialog)
    ld_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
    license_label = QLabel(f"<b>{tl('license_text')}</b>")
    license_label.setTextFormat(Qt.TextFormat.RichText)
    license_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    license_label.setWordWrap(True)
    ld_layout.addWidget(license_label)
    ok_btn = QPushButton("OK")
    ok_btn.clicked.connect(license_dialog.close)
    ld_layout.addWidget(ok_btn, alignment=Qt.AlignmentFlag.AlignCenter)
    license_dialog.adjustSize()
    hint = license_dialog.sizeHint()
    license_dialog.setFixedSize(int(hint.width() * 1.5), hint.height())
    license_dialog.show()
    QTimer.singleShot(5000, license_dialog.close)

    # ==================== Close Handling ====================
    close_accepted = [False]

    def close_event(event):
        if close_accepted[0]:
            event.accept()
            return
        event.ignore()
        send_queue.put(GUICommand(GUICommandType.AttemptedClose))

    window.closeEvent = close_event

    # ==================== Event Loop Timer ====================
    def poll_queue():
        try:
            while True:
                com = recv_queue.get_nowait()
                match com.com_type:
                    case GUICommandType.Close:
                        close_accepted[0] = True
                        window.close()
                        app.quit()
                        return

                    case GUICommandType.CloseFromBackend:
                        send_queue.put(GUICommand(GUICommandType.AttemptedClose))

                    case GUICommandType.UpdateWindow:
                        tag = com.data[0]
                        value = com.data[1]
                        if tag == 'EnemyInput':
                            duel_circle.set_enemy_name(str(value))
                        elif tag == 'AllyInput':
                            duel_circle.set_ally_name(str(value))
                        else:
                            widget = widget_tags.get(tag)
                            if widget is not None:
                                if isinstance(widget, QCheckBox):
                                    widget.setChecked(value == 'Enabled')
                                elif isinstance(widget, QLabel):
                                    widget.setText(str(value))
                                elif isinstance(widget, QLineEdit):
                                    widget.setText(str(value))
                                elif isinstance(widget, QComboBox):
                                    widget.setCurrentText(str(value))
                                elif isinstance(widget, (QTextEdit, QPlainTextEdit)):
                                    if isinstance(widget, QPlainTextEdit):
                                        widget.setPlainText(str(value))
                                    else:
                                        widget.setPlainText(str(value))

                    case GUICommandType.UpdateWindowValues:
                        tag = com.data[0]
                        values = com.data[1]
                        widget = widget_tags.get(tag)
                        if widget is not None and isinstance(widget, QComboBox):
                            widget.clear()
                            widget.addItems(values)

                    case GUICommandType.UpdateConsole:
                        console_psg.toggle_show_expanded_logs()

                    case GUICommandType.ShowUITreePopup:
                        _show_ui_tree_popup(window, com.data)

                    case GUICommandType.ShowEntityListPopup:
                        _show_entity_list_popup(window, com.data)

                    case GUICommandType.CopyConsole:
                        console_psg.copy()

                    case GUICommandType.UpdateAccountList:
                        account_list.clear()
                        if com.data:
                            account_list.addItems(com.data)

        except queue.Empty:
            pass

    timer = QTimer()
    timer.timeout.connect(poll_queue)
    timer.start(16)

    window.show()
    # Lock width to the tab bar width + content margins
    tab_bar_width = tabs.tabBar().sizeHint().width()
    margins = content_layout.contentsMargins()
    window.setFixedWidth(tab_bar_width + margins.left() + margins.right())
    app.exec()

    # After app exits, signal backend
    if not close_accepted[0]:
        send_queue.put(GUICommand(GUICommandType.AttemptedClose))
        import time
        timeout = 30
        start = time.time()
        while time.time() - start < timeout:
            try:
                com = recv_queue.get_nowait()
                if com.com_type == GUICommandType.Close:
                    break
            except queue.Empty:
                pass
            time.sleep(0.1)
