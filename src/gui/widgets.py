import math
import re
import time
import ctypes
import ctypes.wintypes

import pyperclip
from PyQt6.QtWidgets import (
    QWidget, QTabWidget, QTabBar, QCheckBox, QStackedWidget, QDialog,
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QPlainTextEdit,
    QToolTip,
)
from PyQt6.QtCore import (
    QTimer, Qt, QMetaObject, Q_ARG, pyqtSlot, pyqtSignal,
    QPropertyAnimation, QEasingCurve, QPoint, QParallelAnimationGroup,
    QRectF,
)
from PyQt6.QtGui import QPixmap, QIcon, QPainter, QColor, QPen, QBrush, QFont, QFontMetrics
from PyQt6.QtSvg import QSvgRenderer

from src.gui.commands import _QT_KEY_TO_KEYCODE, _MODIFIER_KEYS, _format_binding


class ToggleNameLabel(QLabel):
    """A QLabel that toggles bold font weight as a status indicator."""

    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self._checked = False

    def setChecked(self, checked):
        self._checked = checked
        f = self.font()
        f.setBold(checked)
        self.setFont(f)

    def isChecked(self):
        return self._checked


class BoldSelectedTabBar(QTabBar):
    """QTabBar that bolds the selected tab without shifting sizes.
    All tabs are pre-sized using bold font metrics so switching never changes widths."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("QTabBar::tab:selected { font-weight: bold; }")

    def tabSizeHint(self, index):
        size = super().tabSizeHint(index)
        f = QFont(self.font())
        f.setBold(True)
        bold_width = QFontMetrics(f).horizontalAdvance(self.tabText(index))
        normal_width = QFontMetrics(self.font()).horizontalAdvance(self.tabText(index))
        size.setWidth(size.width() + bold_width - normal_width)
        return size


class AnimatedTabWidget(QTabWidget):
    """QTabWidget with horizontal slide animation between tabs."""
    def __init__(self, duration=200, parent=None):
        super().__init__(parent)
        self.setTabBar(BoldSelectedTabBar())
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

    def __init__(self, left_svg="", right_svg="", left_tooltip="", right_tooltip="", vertical=False, button_color=None, parent=None):
        super().__init__(parent)
        self._left_tooltip = left_tooltip
        self._right_tooltip = right_tooltip
        self._vertical = vertical
        self._button_color = button_color if button_color is not None else QColor(74, 1, 158)
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

    def set_button_color(self, color):
        self._button_color = color
        self.update()

    def paintEvent(self, event):
        from PyQt6.QtGui import QBrush
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        pad = self._PAD
        cell = self._icon_cell
        gap = self._GAP

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self._button_color))

        if self._vertical:
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

        direction = 1 if index > self.currentIndex() else -1

        next_widget.setGeometry(0, 0, width, self.height())
        next_widget.move(direction * width, 0)
        next_widget.show()
        next_widget.raise_()

        group = QParallelAnimationGroup(self)

        anim_out = QPropertyAnimation(current_widget, b"pos", self)
        anim_out.setDuration(self._duration)
        anim_out.setStartValue(current_widget.pos())
        anim_out.setEndValue(QPoint(-direction * width, 0))
        anim_out.setEasingCurve(QEasingCurve.Type.InOutCubic)
        group.addAnimation(anim_out)

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
    viewEnemy = pyqtSignal()
    viewAlly = pyqtSignal()
    swapClicked = pyqtSignal()

    _SLOT_RADIUS = 14

    def __init__(self, stroke_color='#e0e0e0', text_color='#ffffff', bg_color='#1e1e1e', button_color='#4a019e', tl=None, parent=None):
        super().__init__(parent)
        self._tl = tl or (lambda k: k)
        self._stroke_color = QColor(stroke_color)
        self._text_color = QColor(text_color)
        self._bg_color = QColor(bg_color)
        self._SELECTED_COLOR = QColor(button_color)
        self._enemy_count = 4
        self._ally_count = 4
        self._selected_caster = 1
        self._selected_target = 1
        self._enemy_name = ""
        self._ally_name = ""
        self._slot_centers = {}
        self._slot_icons = {}
        self._status_message = ""
        self._slot_info = {}
        self.setFixedSize(220, 224)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        _friendly_svg = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#ffffff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M8 14s1.5 2 4 2 4-2 4-2"/><line x1="9" x2="9.01" y1="9" y2="9"/><line x1="15" x2="15.01" y1="9" y2="9"/></svg>'
        _hostile_svg = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#ffffff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M16 16s-1.5-2-4-2-4 2-4 2"/><path d="M7.5 8 10 9"/><path d="m14 9 2.5-1"/><path d="M9 10h.01"/><path d="M15 10h.01"/></svg>'
        _stunned_svg = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#ffffff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11.017 2.814a1 1 0 0 1 1.966 0l1.051 5.558a2 2 0 0 0 1.594 1.594l5.558 1.051a1 1 0 0 1 0 1.966l-5.558 1.051a2 2 0 0 0-1.594 1.594l-1.051 5.558a1 1 0 0 1-1.966 0l-1.051-5.558a2 2 0 0 0-1.594-1.594l-5.558-1.051a1 1 0 0 1 0-1.966l5.558-1.051a2 2 0 0 0 1.594-1.594z"/><path d="M20 2v4"/><path d="M22 4h-4"/><circle cx="4" cy="20" r="2"/></svg>'
        _dead_svg = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#ffffff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>'
        self._friendly_icon = self._render_svg(_friendly_svg, 10)
        self._hostile_icon = self._render_svg(_hostile_svg, 10)
        self._stunned_icon = self._render_svg(_stunned_svg, 10)
        self._dead_icon = self._render_svg(_dead_svg, 10)
        self._slot_allegiance = {}
        self._slot_dead = {}
        self._slot_stunned = {}
        self._flipped = False

        self._eye_rects = {}
        self._swap_rect = QRectF()

        self._build_slot_icons(stroke_color)

        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(16)
        self._anim_timer.timeout.connect(self._anim_tick)
        self._anim_progress = 1.0
        self._anim_start_time = 0.0
        self._anim_duration = 0.6
        self._anim_start_angles = {}
        self._anim_end_angles = {}
        self._name_swap_pending = False
        self._pending_enemy_name = ""
        self._pending_ally_name = ""

    def _build_slot_icons(self, sc):
        """Build slot icon pixmaps for the given stroke color."""
        self._slot_icons.clear()
        enemy_svgs = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m11 19-6-6"/><path d="m5 21-2-2"/><path d="m8 16-4 4"/><path d="M9.5 17.5 21 6V3h-3L6.5 14.5"/></svg>',
            f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2.586 17.414A2 2 0 0 0 2 18.828V21a1 1 0 0 0 1 1h3a1 1 0 0 0 1-1v-1a1 1 0 0 1 1-1h1a1 1 0 0 0 1-1v-1a1 1 0 0 1 1-1h.172a2 2 0 0 0 1.414-.586l.814-.814a6.5 6.5 0 1 0-4-4z"/><circle cx="16.5" cy="7.5" r=".5" fill="{sc}"/></svg>',
            f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.5 3 8 9l4 13 4-13-2.5-6"/><path d="M17 3a2 2 0 0 1 1.6.8l3 4a2 2 0 0 1 .013 2.382l-7.99 10.986a2 2 0 0 1-3.247 0l-7.99-10.986A2 2 0 0 1 2.4 7.8l2.998-3.997A2 2 0 0 1 7 3z"/><path d="M2 9h20"/></svg>',
            f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 11a2 2 0 1 1-4 0 4 4 0 0 1 8 0 6 6 0 0 1-12 0 8 8 0 0 1 16 0 10 10 0 1 1-20 0 11.93 11.93 0 0 1 2.42-7.22 2 2 0 1 1 3.16 2.44"/></svg>',
            f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m20 13.7-2.1-2.1a2 2 0 0 0-2.8 0L9.7 17"/><path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H19a1 1 0 0 1 1 1v18a1 1 0 0 1-1 1H6.5a1 1 0 0 1 0-5H20"/><circle cx="10" cy="8" r="2"/></svg>',
            f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 22h8"/><path d="M7 10h10"/><path d="M12 15v7"/><path d="M12 15a5 5 0 0 0 5-5c0-2-.5-4-2-8H9c-1.5 4-2 6-2 8a5 5 0 0 0 5 5Z"/></svg>',
            f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 4V2"/><path d="M15 16v-2"/><path d="M8 9h2"/><path d="M20 9h2"/><path d="M17.8 11.8 19 13"/><path d="M15 9h.01"/><path d="M17.8 6.2 19 5"/><path d="m3 21 9-9"/><path d="M12.2 6.2 11 5"/></svg>',
            f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 2v6.292a7 7 0 1 0 4 0V2"/><path d="M5 15h14"/><path d="M8.5 2h7"/></svg>',
        ]
        ally_svgs = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/></svg>',
            f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2.062 12.348a1 1 0 0 1 0-.696 10.75 10.75 0 0 1 19.876 0 1 1 0 0 1 0 .696 10.75 10.75 0 0 1-19.876 0"/><circle cx="12" cy="12" r="3"/></svg>',
            f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11.525 2.295a.53.53 0 0 1 .95 0l2.31 4.679a2.123 2.123 0 0 0 1.595 1.16l5.166.756a.53.53 0 0 1 .294.904l-3.736 3.638a2.123 2.123 0 0 0-.611 1.878l.882 5.14a.53.53 0 0 1-.771.56l-4.618-2.428a2.122 2.122 0 0 0-1.973 0L6.396 21.01a.53.53 0 0 1-.77-.56l.881-5.139a2.122 2.122 0 0 0-.611-1.879L2.16 9.795a.53.53 0 0 1 .294-.906l5.165-.755a2.122 2.122 0 0 0 1.597-1.16z"/></svg>',
            f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20.985 12.486a9 9 0 1 1-9.473-9.472c.405-.022.617.46.402.803a6 6 0 0 0 8.268 8.268c.344-.215.825-.004.803.401"/></svg>',
            f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m20 13.7-2.1-2.1a2 2 0 0 0-2.8 0L9.7 17"/><path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H19a1 1 0 0 1 1 1v18a1 1 0 0 1-1 1H6.5a1 1 0 0 1 0-5H20"/><circle cx="10" cy="8" r="2"/></svg>',
            f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 22h8"/><path d="M7 10h10"/><path d="M12 15v7"/><path d="M12 15a5 5 0 0 0 5-5c0-2-.5-4-2-8H9c-1.5 4-2 6-2 8a5 5 0 0 0 5 5Z"/></svg>',
            f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 4V2"/><path d="M15 16v-2"/><path d="M8 9h2"/><path d="M20 9h2"/><path d="M17.8 11.8 19 13"/><path d="M15 9h.01"/><path d="M17.8 6.2 19 5"/><path d="m3 21 9-9"/><path d="M12.2 6.2 11 5"/></svg>',
            f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 2v6.292a7 7 0 1 0 4 0V2"/><path d="M5 15h14"/><path d="M8.5 2h7"/></svg>',
        ]
        icon_size = 16
        for i, svg in enumerate(enemy_svgs):
            self._slot_icons[('enemy', i + 1)] = self._render_svg(svg, icon_size)
        for i, svg in enumerate(ally_svgs):
            self._slot_icons[('ally', i + 1)] = self._render_svg(svg, icon_size)

        # Rebuild eye/swap icons with the stroke color
        _eye_svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2.062 12.348a1 1 0 0 1 0-.696 10.75 10.75 0 0 1 19.876 0 1 1 0 0 1 0 .696 10.75 10.75 0 0 1-19.876 0"/><circle cx="12" cy="12" r="3"/></svg>'
        self._eye_icon = self._render_svg(_eye_svg, 14)

        _swap_svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"/><path d="M16 16h5v5"/><circle cx="12" cy="12" r="1"/></svg>'
        self._swap_icon = self._render_svg(_swap_svg, 14)

    def set_theme_colors(self, stroke, text, bg, button):
        """Update theme colors at runtime."""
        self._stroke_color = QColor(stroke)
        self._text_color = QColor(text)
        self._bg_color = QColor(bg)
        self._SELECTED_COLOR = QColor(button)
        self._build_slot_icons(stroke)
        self.update()

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
        self._slot_centers.clear()
        w = self.width()
        h = self.height()
        cx = w / 2
        cy = h / 2
        r = min(w, h) * 0.38
        rx = r
        ry = r

        enemy_angles = self._distribute_angles(self._enemy_count, center_deg=270)
        if self._flipped:
            enemy_angles = [2 * 270 - a for a in enemy_angles]

        ally_angles = self._distribute_angles(self._ally_count, center_deg=90)
        if self._flipped:
            ally_angles = [2 * 90 - a for a in ally_angles]

        if self._anim_progress < 1.0:
            t = self._anim_progress
            for (side, idx), start_deg in self._anim_start_angles.items():
                end_deg = self._anim_end_angles.get((side, idx), start_deg)
                diff = (end_deg - start_deg + 180) % 360 - 180
                deg = start_deg + diff * t
                rad = math.radians(deg)
                x = cx + rx * math.cos(rad)
                y = cy + ry * math.sin(rad)
                self._slot_centers[(side, idx)] = (x, y)
        else:
            for i, deg in enumerate(enemy_angles):
                rad = math.radians(deg)
                x = cx + rx * math.cos(rad)
                y = cy + ry * math.sin(rad)
                self._slot_centers[('enemy', i + 1)] = (x, y)

            for i, deg in enumerate(ally_angles):
                rad = math.radians(deg)
                x = cx + rx * math.cos(rad)
                y = cy + ry * math.sin(rad)
                self._slot_centers[('ally', i + 1)] = (x, y)

    @staticmethod
    def _distribute_angles(count, center_deg):
        spacing = 36
        if count > 4:
            spacing = min(spacing, 170 / (count - 1))
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
        r = min(w, h) * 0.38
        rx = r
        ry = r

        pen = QPen(self._stroke_color, 1.5)
        pen.setStyle(Qt.PenStyle.DotLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QRectF(cx - rx, cy - ry, rx * 2, ry * 2))

        if self._enemy_count == 0 and self._ally_count == 0 and self._status_message:
            label_font = painter.font()
            label_font.setPixelSize(11)
            painter.setFont(label_font)
            painter.setPen(QPen(self._stroke_color))
            text_rect = QRectF(cx - rx, cy - ry, rx * 2, ry * 2)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, self._status_message)
            painter.end()
            return

        siw = self._swap_icon.width() / self._swap_icon.devicePixelRatio()
        sih = self._swap_icon.height() / self._swap_icon.devicePixelRatio()
        self._swap_rect = QRectF(cx - siw / 2, cy - sih / 2, siw, sih)
        painter.drawPixmap(self._swap_rect, self._swap_icon, QRectF(self._swap_icon.rect()))

        line_color = QColor(self._stroke_color)
        line_color.setAlpha(180)
        painter.setPen(QPen(line_color, 0.5))
        gap_half = siw / 2 + 3
        line_extent = rx * 0.7
        painter.drawLine(int(cx - line_extent), int(cy), int(cx - gap_half), int(cy))
        painter.drawLine(int(cx + gap_half), int(cy), int(cx + line_extent), int(cy))

        r = self._SLOT_RADIUS

        for (side, idx), (sx, sy) in self._slot_centers.items():
            rect = QRectF(sx - r, sy - r, r * 2, r * 2)
            is_dead = self._slot_dead.get((side, idx), False)
            is_selected = not is_dead and (
                (side == 'enemy' and idx == self._selected_target) or
                (side == 'ally' and idx == self._selected_caster))

            if is_dead:
                dead_color = QColor(self._stroke_color)
                dead_color.setAlpha(50)
                painter.setBrush(QBrush(dead_color))
                painter.setPen(QPen(dead_color, 1.5))
            elif is_selected:
                painter.setBrush(QBrush(self._SELECTED_COLOR))
                painter.setPen(QPen(self._SELECTED_COLOR.lighter(140), 2))
            else:
                painter.setBrush(QBrush(self._bg_color))
                painter.setPen(QPen(self._stroke_color, 1.5))

            painter.drawEllipse(rect)

            pix = self._slot_icons.get((side, idx))
            if pix:
                iw = pix.width() / pix.devicePixelRatio()
                ih = pix.height() / pix.devicePixelRatio()
                if is_dead:
                    painter.setOpacity(0.25)
                painter.drawPixmap(QRectF(sx - iw / 2, sy - ih / 2, iw, ih), pix, QRectF(pix.rect()))
                if is_dead:
                    painter.setOpacity(1.0)

            is_stunned = self._slot_stunned.get((side, idx), False)
            allegiance = self._slot_allegiance.get((side, idx))
            if is_dead:
                ind_pix = self._dead_icon
            elif is_stunned:
                ind_pix = self._stunned_icon
            elif allegiance is not None:
                ind_pix = self._friendly_icon if allegiance else self._hostile_icon
            else:
                ind_pix = None
            if ind_pix is not None:
                dx = sx - cx
                dy = sy - cy
                dist = math.sqrt(dx * dx + dy * dy) or 1
                nx, ny = dx / dist, dy / dist
                ind_w = ind_pix.width() / ind_pix.devicePixelRatio()
                ind_h = ind_pix.height() / ind_pix.devicePixelRatio()
                ix = sx + nx * (r + 8) - ind_w / 2
                iy = sy + ny * (r + 8) - ind_h / 2
                painter.drawPixmap(QRectF(ix, iy, ind_w, ind_h), ind_pix, QRectF(ind_pix.rect()))

        label_font = painter.font()
        label_font.setPixelSize(10)
        label_font.setBold(False)
        painter.setFont(label_font)
        painter.setPen(QPen(self._stroke_color))
        if self._anim_progress < 1.0:
            t = self._anim_progress
            name_opacity = abs(2.0 * t - 1.0)
            painter.setOpacity(name_opacity)
        if self._enemy_name:
            painter.drawText(QRectF(0, cy - 22, w, 14), Qt.AlignmentFlag.AlignCenter, self._enemy_name)
        if self._ally_name:
            painter.drawText(QRectF(0, cy + 8, w, 14), Qt.AlignmentFlag.AlignCenter, self._ally_name)
        painter.setOpacity(1.0)

        eiw = self._eye_icon.width() / self._eye_icon.devicePixelRatio()
        eih = self._eye_icon.height() / self._eye_icon.devicePixelRatio()
        eye_offset = ry / 2
        enemy_eye_rect = QRectF(cx - eiw / 2, cy - eye_offset - eih / 2, eiw, eih)
        ally_eye_rect = QRectF(cx - eiw / 2, cy + eye_offset - eih / 2, eiw, eih)
        self._eye_rects['enemy'] = enemy_eye_rect
        self._eye_rects['ally'] = ally_eye_rect

        if self._enemy_count == 0:
            painter.setOpacity(0.25)
        painter.drawPixmap(enemy_eye_rect, self._eye_icon, QRectF(self._eye_icon.rect()))
        painter.setOpacity(1.0)

        if self._ally_count == 0:
            painter.setOpacity(0.25)
        painter.drawPixmap(ally_eye_rect, self._eye_icon, QRectF(self._eye_icon.rect()))
        painter.setOpacity(1.0)

        painter.end()

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self._calc_slot_positions()
        px, py = event.position().x(), event.position().y()

        if not self._swap_rect.isNull():
            padded = self._swap_rect.adjusted(-4, -4, 4, 4)
            if padded.contains(px, py):
                self.swapClicked.emit()
                return

        for side, rect in self._eye_rects.items():
            padded = rect.adjusted(-6, -6, 6, 6)
            if padded.contains(px, py):
                count = self._enemy_count if side == 'enemy' else self._ally_count
                if count > 0:
                    if side == 'enemy':
                        self.viewEnemy.emit()
                    else:
                        self.viewAlly.emit()
                return

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
            if self._slot_dead.get((side, idx), False):
                return
            if side == 'enemy':
                self._selected_target = idx
                self.targetSelected.emit(idx)
            else:
                self._selected_caster = idx
                self.casterSelected.emit(idx)
            self.update()

    def mouseMoveEvent(self, event):
        px, py = event.position().x(), event.position().y()
        hit_r = self._SLOT_RADIUS + 6
        for (side, idx), (sx, sy) in self._slot_centers.items():
            if (px - sx) ** 2 + (py - sy) ** 2 <= hit_r ** 2:
                info = self._slot_info.get((side, idx))
                if info:
                    name = info.get('name', '???')
                    max_dmg = info.get('max_dmg', 0)
                    sim_dmg = info.get('sim_dmg', 0)
                    allegiance = self._slot_allegiance.get((side, idx))
                    is_dead = self._slot_dead.get((side, idx), False)
                    is_stunned = self._slot_stunned.get((side, idx), False)
                    if is_dead:
                        status_str = self._tl('status_dead')
                    elif is_stunned:
                        status_str = self._tl('status_stunned')
                    elif allegiance:
                        status_str = self._tl('status_friendly')
                    elif allegiance is not None:
                        status_str = self._tl('status_hostile')
                    else:
                        status_str = self._tl('status_unknown')
                    text = f"{name}\nMax Dmg: {max_dmg}\nSim Dmg: {sim_dmg}\nStatus: {status_str}"
                    QToolTip.showText(event.globalPosition().toPoint(), text, self)
                    return
        QToolTip.hideText()

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

    def set_enemy_count(self, count):
        self._enemy_count = count
        if self._selected_target > count:
            self._selected_target = max(1, count)
        self.update()

    def set_ally_count(self, count):
        self._ally_count = count
        if self._selected_caster > count:
            self._selected_caster = max(1, count)
        self.update()

    def set_status_message(self, msg):
        self._status_message = msg

    def set_slot_info(self, info):
        self._slot_info = info
        self._slot_allegiance = {k: v.get('is_friendly', k[0] == 'ally') for k, v in info.items()}
        self._slot_dead = {k: v.get('is_dead', False) for k, v in info.items()}
        self._slot_stunned = {k: v.get('is_stunned', False) for k, v in info.items()}
        self.update()

    def swap_sides(self):
        if self._anim_timer.isActive():
            self._anim_timer.stop()
            self._anim_progress = 1.0
            if self._name_swap_pending:
                self._enemy_name = self._pending_enemy_name
                self._ally_name = self._pending_ally_name
                self._name_swap_pending = False

        old_enemy_angles = self._distribute_angles(self._enemy_count, center_deg=270)
        if self._flipped:
            old_enemy_angles = [2 * 270 - a for a in old_enemy_angles]
        old_ally_angles = self._distribute_angles(self._ally_count, center_deg=90)
        if self._flipped:
            old_ally_angles = [2 * 90 - a for a in old_ally_angles]

        self._selected_caster, self._selected_target = self._selected_target, self._selected_caster
        self._pending_enemy_name = self._ally_name
        self._pending_ally_name = self._enemy_name
        self._name_swap_pending = True
        self._enemy_count, self._ally_count = self._ally_count, self._enemy_count
        swapped = {}
        for (side, idx), pix in self._slot_icons.items():
            new_side = 'ally' if side == 'enemy' else 'enemy'
            swapped[(new_side, idx)] = pix
        self._slot_icons = swapped
        swapped_alleg = {}
        for (side, idx), friendly in self._slot_allegiance.items():
            swapped_alleg[('ally' if side == 'enemy' else 'enemy', idx)] = not friendly
        self._slot_allegiance = swapped_alleg
        self._slot_dead = {('ally' if s == 'enemy' else 'enemy', i): v for (s, i), v in self._slot_dead.items()}
        self._slot_stunned = {('ally' if s == 'enemy' else 'enemy', i): v for (s, i), v in self._slot_stunned.items()}

        self._flipped = not self._flipped

        new_enemy_angles = self._distribute_angles(self._enemy_count, center_deg=270)
        if self._flipped:
            new_enemy_angles = [2 * 270 - a for a in new_enemy_angles]
        new_ally_angles = self._distribute_angles(self._ally_count, center_deg=90)
        if self._flipped:
            new_ally_angles = [2 * 90 - a for a in new_ally_angles]

        self._anim_start_angles = {}
        self._anim_end_angles = {}
        for i, old_deg in enumerate(old_enemy_angles):
            key = ('ally', i + 1)
            if i < len(new_ally_angles):
                self._anim_start_angles[key] = old_deg
                self._anim_end_angles[key] = new_ally_angles[i]
        for i, old_deg in enumerate(old_ally_angles):
            key = ('enemy', i + 1)
            if i < len(new_enemy_angles):
                self._anim_start_angles[key] = old_deg
                self._anim_end_angles[key] = new_enemy_angles[i]

        self._anim_progress = 0.0
        self._anim_start_time = time.monotonic()
        self._anim_timer.start()

    def _anim_tick(self):
        elapsed = time.monotonic() - self._anim_start_time
        t = min(elapsed / self._anim_duration, 1.0)
        self._anim_progress = 1.0 - (1.0 - t) ** 3
        if self._name_swap_pending and t >= 0.5:
            self._enemy_name = self._pending_enemy_name
            self._ally_name = self._pending_ally_name
            self._name_swap_pending = False
        self.update()
        if t >= 1.0:
            self._anim_timer.stop()
            self._anim_progress = 1.0


class HotkeyCapture(QDialog):
    """Modal dialog that captures a single key press + modifiers."""
    captured = pyqtSignal(str, list)

    def __init__(self, action_name: str, existing_bindings: dict, current_action_id: str, tl=None, parent=None):
        super().__init__(parent)
        self._tl = tl or (lambda k: k)
        self._existing = existing_bindings
        self._current_action_id = current_action_id
        self._action_name = action_name
        self._key = None
        self._mods = []
        self.setWindowTitle(self._tl('bind_hotkey'))
        self.setFixedSize(280, 120)
        self.setModal(True)

        layout = QVBoxLayout(self)
        self._label = QLabel(f"{action_name}\n{self._tl('press_a_key')}")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._label)

        btn_row = QHBoxLayout()
        self._ok_btn = QPushButton(self._tl('ok'))
        self._ok_btn.setEnabled(False)
        self._ok_btn.clicked.connect(self._accept)
        self._clear_btn = QPushButton(self._tl('unbind_hotkey'))
        self._clear_btn.clicked.connect(self._clear)
        self._cancel_btn = QPushButton(self._tl('cancel'))
        self._cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self._ok_btn)
        btn_row.addWidget(self._clear_btn)
        btn_row.addWidget(self._cancel_btn)
        layout.addLayout(btn_row)

    def _modifier_prefix(self, qt_mods):
        parts = []
        if qt_mods & Qt.KeyboardModifier.ControlModifier:
            parts.append("Ctrl")
        if qt_mods & Qt.KeyboardModifier.ShiftModifier:
            parts.append("Shift")
        if qt_mods & Qt.KeyboardModifier.AltModifier:
            parts.append("Alt")
        return "+".join(parts)

    def keyPressEvent(self, event):
        key = event.key()
        if key in _MODIFIER_KEYS:
            prefix = self._modifier_prefix(event.modifiers())
            if prefix:
                self._label.setText(f"{prefix}+...")
            return

        keycode_name = _QT_KEY_TO_KEYCODE.get(key)
        if keycode_name is None:
            return

        mods = []
        qt_mods = event.modifiers()
        if qt_mods & Qt.KeyboardModifier.ShiftModifier:
            mods.append("SHIFT")
        if qt_mods & Qt.KeyboardModifier.ControlModifier:
            mods.append("CTRL")
        if qt_mods & Qt.KeyboardModifier.AltModifier:
            mods.append("ALT")

        self._key = keycode_name
        self._mods = mods
        display = _format_binding(keycode_name, mods)
        self._label.setText(display)
        self._ok_btn.setEnabled(True)
        self._accept()

    def keyReleaseEvent(self, event):
        if event.key() in _MODIFIER_KEYS and self._key is None:
            prefix = self._modifier_prefix(event.modifiers())
            if prefix:
                self._label.setText(f"{prefix}+...")
            else:
                self._label.setText(f"{self._action_name}\n{self._tl('press_a_key')}")

    def _check_conflict(self) -> str | None:
        for aid, binding in self._existing.items():
            if aid == self._current_action_id or binding is None:
                continue
            if binding["key"] == self._key and sorted(binding.get("modifiers", [])) == sorted(self._mods):
                return aid
        return None

    def _accept(self):
        if self._key is None:
            return
        conflict = self._check_conflict()
        if conflict:
            from PyQt6.QtWidgets import QMessageBox
            result = QMessageBox.warning(
                self, self._tl('key_conflict'),
                self._tl('overwrite_binding').format(_format_binding(self._key, self._mods), conflict),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if result != QMessageBox.StandardButton.Yes:
                return
        self.captured.emit(self._key, self._mods)
        self.accept()

    def _clear(self):
        self._key = None
        self._mods = []
        self.captured.emit("", [])
        self.accept()


class HighlightOverlay(QWidget):
    """Transparent, click-through overlay that covers the game window."""
    THICKNESS = 3

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self._box_rect = (0, 0, 0, 0)
        self._has_box = False
        self._click_through_set = False

    def _ensure_click_through(self):
        if not self._click_through_set:
            self._click_through_set = True
            hwnd = int(self.winId())
            ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
            ctypes.windll.user32.SetWindowLongW(hwnd, -20, ex_style | 0x20 | 0x80000)

    def update_box(self, game_hwnd, x1, y1, x2, y2):
        self._ensure_click_through()
        origin = ctypes.wintypes.POINT(0, 0)
        ctypes.windll.user32.ClientToScreen(game_hwnd, ctypes.byref(origin))
        client_rect = ctypes.wintypes.RECT()
        ctypes.windll.user32.GetClientRect(game_hwnd, ctypes.byref(client_rect))

        dpr = self.devicePixelRatioF()
        self.setGeometry(
            round(origin.x / dpr), round(origin.y / dpr),
            round(client_rect.right / dpr), round(client_rect.bottom / dpr)
        )

        overlay_hwnd = int(self.winId())
        GW_HWNDPREV = 3
        above_game = ctypes.windll.user32.GetWindow(game_hwnd, GW_HWNDPREV)
        if above_game != overlay_hwnd:
            SWP_NOSIZE = 0x0001
            SWP_NOMOVE = 0x0002
            SWP_NOACTIVATE = 0x0010
            insert_after = above_game if above_game else 0
            ctypes.windll.user32.SetWindowPos(
                overlay_hwnd, insert_after,
                0, 0, 0, 0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE
            )

        self._box_rect = (round(x1 / dpr), round(y1 / dpr), round(x2 / dpr), round(y2 / dpr))
        self._has_box = True
        if not self.isVisible():
            self.show()
        self.update()

    def clear_box(self):
        self._has_box = False
        self.hide()

    def paintEvent(self, event):
        if not self._has_box:
            return
        painter = QPainter(self)
        pen = QPen(QColor(0, 255, 0), self.THICKNESS)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        bx1, by1, bx2, by2 = self._box_rect
        painter.drawRect(bx1, by1, bx2 - bx1, by2 - by1)
        painter.end()


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
        from loguru import logger
        logger.debug("Copied current logs.")

    def toggle_show_expanded_logs(self, override: bool | None = None):
        match override:
            case True | False:
                self.show_expanded_logs = override
            case _:
                self.show_expanded_logs = not self.show_expanded_logs

        from loguru import logger
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
