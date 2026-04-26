import os
import sys
import webbrowser
import ctypes
from threading import Thread

from PyQt6.QtWidgets import (
    QWidget, QPushButton, QLabel, QGroupBox, QVBoxLayout, QHBoxLayout,
    QSizePolicy, QMenu, QFileDialog,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap, QIcon, QPainter, QTransform
from PyQt6.QtSvg import QSvgRenderer

from src.gui.commands import GUICommand, GUICommandType


def resource_path(filename: str) -> str:
    """Resolve path for bundled resources (PyInstaller) or source directory."""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, filename)
    return filename


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


def titlebar_svg_icon(window, svg_str, size=24):
    """DPI-aware SVG to QIcon factory."""
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


def svg_icon(svg_str):
    """Create a 24px QIcon from an SVG string."""
    renderer = QSvgRenderer(svg_str.encode())
    pixmap = QPixmap(24, 24)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return QIcon(pixmap)


def centered_label(text):
    lbl = QLabel(text)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return lbl


def repo_icon_btn(ctx, svg_str, tooltip, url):
    btn = QPushButton()
    btn.setToolTip(tooltip)
    btn.setStyleSheet(ctx.icon_btn_style)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setFixedSize(24, 24)
    btn.setIcon(svg_icon(svg_str))
    btn.clicked.connect(lambda: webbrowser.open(url))
    if hasattr(ctx, 'tracked_icon_buttons'):
        ctx.tracked_icon_buttons.append((btn, svg_str, 24))
    return btn


def section_group(ctx, title, tooltip_text=None):
    group = QGroupBox()
    group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
    layout = QVBoxLayout(group)
    layout.setContentsMargins(6, 2, 6, 2)
    layout.setSpacing(1)
    header = QHBoxLayout()
    header.addWidget(QLabel(f"<b>{title}</b>"))
    header.addStretch()
    if tooltip_text:
        _svg = ctx.svgs['info']
        info_btn = QPushButton()
        info_btn.setIcon(ctx.titlebar_svg_icon(_svg, 16))
        info_btn.setFixedSize(20, 20)
        info_btn.setStyleSheet(ctx.icon_btn_style)
        info_btn.setToolTip(tooltip_text)
        info_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if hasattr(ctx, 'tracked_icon_buttons'):
            ctx.tracked_icon_buttons.append((info_btn, _svg, 16))
        header.addWidget(info_btn)
    layout.addLayout(header)
    return group, layout


def copy_icon_btn(ctx, callback):
    _svg = ctx.svgs['clipboard']
    btn = QPushButton()
    btn.setIcon(ctx.titlebar_svg_icon(_svg, 16))
    btn.setFixedSize(20, 20)
    btn.setStyleSheet(ctx.icon_btn_style)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setToolTip(ctx.tl('copy'))
    btn.clicked.connect(callback)
    if hasattr(ctx, 'tracked_icon_buttons'):
        ctx.tracked_icon_buttons.append((btn, _svg, 16))
    return btn


def launcher_icon_btn(ctx, svg_str, tooltip, callback, size=32):
    btn = QPushButton()
    btn.setIcon(ctx.titlebar_svg_icon(svg_str, 24))
    btn.setFixedSize(size, size)
    btn.setStyleSheet(ctx.icon_btn_style)
    btn.setToolTip(tooltip)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.clicked.connect(callback)
    if hasattr(ctx, 'tracked_icon_buttons'):
        ctx.tracked_icon_buttons.append((btn, svg_str, 24))
    return btn


def launcher_small_icon_btn(ctx, svg_str, tooltip, callback):
    btn = QPushButton()
    btn.setIcon(ctx.titlebar_svg_icon(svg_str, 16))
    btn.setFixedSize(22, 22)
    btn.setStyleSheet(ctx.icon_btn_style)
    btn.setToolTip(tooltip)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.clicked.connect(callback)
    if hasattr(ctx, 'tracked_icon_buttons'):
        ctx.tracked_icon_buttons.append((btn, svg_str, 16))
    return btn


def spinning_loader_widget(ctx, size=22):
    lbl = QLabel()
    lbl.setFixedSize(size, size)
    dpr = ctx.window.devicePixelRatioF()
    real = int(size * dpr)
    renderer = QSvgRenderer(ctx.svgs['loader'].encode())
    angle = [0]
    def _tick():
        angle[0] = (angle[0] + 45) % 360
        pm = QPixmap(real, real)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.translate(real / 2, real / 2)
        p.rotate(angle[0])
        p.translate(-real / 2, -real / 2)
        renderer.render(p)
        p.end()
        pm.setDevicePixelRatio(dpr)
        lbl.setPixmap(pm)
    _tick()
    timer = QTimer(lbl)
    timer.timeout.connect(_tick)
    timer.start(120)
    return lbl


def toggle_callback(send_queue, event_key):
    def cb():
        send_queue.put(GUICommand(GUICommandType.ToggleOption, event_key))
    return cb


def copy_callback(send_queue, event_key):
    def cb():
        send_queue.put(GUICommand(GUICommandType.Copy, event_key))
    return cb


def teleport_callback(send_queue, event_key):
    def cb():
        send_queue.put(GUICommand(GUICommandType.Teleport, event_key))
    return cb


# --- Recent imports system ---

_recent_imports = {'flythrough': [], 'bot': [], 'combat': []}
_max_recent = 10
_settings_ref = None  # set by init_recent_imports


def init_recent_imports(settings):
    """Load persisted recent imports from settings.json on startup."""
    global _settings_ref
    _settings_ref = settings
    if settings:
        for cat in _recent_imports:
            _recent_imports[cat] = settings.get_recent_imports(cat)


def add_recent(category, filepath):
    recent = _recent_imports[category]
    if filepath in recent:
        recent.remove(filepath)
    recent.insert(0, filepath)
    del recent[_max_recent:]
    if _settings_ref:
        _settings_ref.add_recent_import(category, filepath, _max_recent)


def show_recent_menu(ctx, category, editor, btn):
    recent = _recent_imports[category]
    menu = QMenu(ctx.window)
    if not recent:
        action = menu.addAction(ctx.tl('no_recent_imports'))
        action.setEnabled(False)
    else:
        for path in recent:
            display = os.path.basename(path)
            action = menu.addAction(display)
            action.setToolTip(path)
            action.triggered.connect(lambda checked, p=path: _load_recent(p, editor, category))
    menu.exec(btn.mapToGlobal(btn.rect().bottomLeft()))


def _load_recent(filepath, editor, category):
    try:
        with open(filepath) as f:
            editor.setPlainText(f.read())
        add_recent(category, filepath)
    except Exception:
        pass


def restyle_tracked_buttons(ctx, icon_btn_style, svg_icon_fn, old_stroke, new_stroke):
    """Re-render all helper-created icon buttons after a theme change."""
    new_tracked = []
    for btn, svg_str, size in ctx.tracked_icon_buttons:
        try:
            new_svg = svg_str.replace(old_stroke, new_stroke)
            btn.setIcon(svg_icon_fn(new_svg, size))
            btn.setStyleSheet(icon_btn_style)
            new_tracked.append((btn, new_svg, size))
        except RuntimeError:
            pass  # Button's parent widget was destroyed (e.g. closed popup)
    ctx.tracked_icon_buttons = new_tracked


def build_shared_svgs(stroke_color):
    """Build the dict of shared SVG strings for a given stroke color."""
    sc = stroke_color
    return {
        'license': f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v18"/><path d="m19 8 3 8a5 5 0 0 1-6 0zV7"/><path d="M3 7h1a17 17 0 0 0 8-2 17 17 0 0 0 8 2h1"/><path d="m5 8 3 8a5 5 0 0 1-6 0zV7"/><path d="M7 21h10"/></svg>',
        'readme': f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>',
        'source': f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 6a9 9 0 0 0-9 9V3"/><circle cx="18" cy="6" r="3"/><circle cx="6" cy="18" r="3"/></svg>',
        'discord': f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3H4a2 2 0 0 0-2 2v16.286a.71.71 0 0 0 1.212.502l2.202-2.202A2 2 0 0 1 6.828 19H20a2 2 0 0 0 2-2v-4"/><path d="M16 3h6v6"/><path d="m16 9 6-6"/></svg>',
        'clipboard': f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="8" height="4" x="8" y="2" rx="1" ry="1"/><path d="M8 4H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"/><path d="M16 4h2a2 2 0 0 1 2 2v4"/><path d="M21 14H11"/><path d="m15 10-4 4 4 4"/></svg>',
        'pencil': f'<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21.174 6.812a1 1 0 0 0-3.986-3.987L3.842 16.174a2 2 0 0 0-.5.83l-1.321 4.352a.5.5 0 0 0 .623.622l4.353-1.32a2 2 0 0 0 .83-.497z"/></svg>',
        'x': f'<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>',
        'individual': f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12.034 12.681a.498.498 0 0 1 .647-.647l9 3.5a.5.5 0 0 1-.033.943l-3.444 1.068a1 1 0 0 0-.66.66l-1.067 3.443a.5.5 0 0 1-.943.033z"/><path d="M21 11V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h6"/></svg>',
        'mass': f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v18"/><path d="M3 12h18"/><rect x="3" y="3" width="18" height="18" rx="2"/></svg>',
        'info': f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2.992 16.342a2 2 0 0 1 .094 1.167l-1.065 3.29a1 1 0 0 0 1.236 1.168l3.413-.998a2 2 0 0 1 1.099.092 10 10 0 1 0-4.777-4.719"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><path d="M12 17h.01"/></svg>',
        'import': f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 22a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h8a2.4 2.4 0 0 1 1.704.706l3.588 3.588A2.4 2.4 0 0 1 20 8v12a2 2 0 0 1-2 2z"/><path d="M14 2v5a1 1 0 0 0 1 1h5"/><path d="M12 12v6"/><path d="m15 15-3-3-3 3"/></svg>',
        'export': f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 22a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h8a2.4 2.4 0 0 1 1.704.706l3.588 3.588A2.4 2.4 0 0 1 20 8v12a2 2 0 0 1-2 2z"/><path d="M14 2v5a1 1 0 0 0 1 1h5"/><path d="M12 18v-6"/><path d="m9 15 3 3 3-3"/></svg>',
        'play': f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 5a2 2 0 0 1 3.008-1.728l11.997 6.998a2 2 0 0 1 .003 3.458l-12 7A2 2 0 0 1 5 19z"/></svg>',
        'kill': f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.513 4.856 13.12 2.17a.5.5 0 0 1 .86.46l-1.377 4.317"/><path d="M15.656 10H20a1 1 0 0 1 .78 1.63l-1.72 1.773"/><path d="M16.273 16.273 10.88 21.83a.5.5 0 0 1-.86-.46l1.92-6.02A1 1 0 0 0 11 14H4a1 1 0 0 1-.78-1.63l4.507-4.643"/><path d="m2 2 20 20"/></svg>',
        'refresh': f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/></svg>',
        'recent': f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 22a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h8a2.4 2.4 0 0 1 1.704.706l3.588 3.588A2.4 2.4 0 0 1 20 8v12a2 2 0 0 1-2 2z"/><path d="M14 2v5a1 1 0 0 0 1 1h5"/><circle cx="11.5" cy="14.5" r="2.5"/><path d="M13.3 16.3 15 18"/></svg>',
        'add': f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14"/><path d="M12 5v14"/></svg>',
        'trash': f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/></svg>',
        'rocket': f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09z"/><path d="m12 15-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z"/><path d="M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0"/><path d="M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5"/></svg>',
        'folder': f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2z"/></svg>',
        'eject': f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>',
        'hook': f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m17.586 11.414-5.93 5.93a1 1 0 0 1-8-8l3.137-3.137a.707.707 0 0 1 1.207.5V10"/><path d="M20.414 8.586 22 7"/><circle cx="19" cy="10" r="2"/></svg>',
        'kill_client': f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>',
        'relaunch': f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/></svg>',
        'gear': f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/></svg>',
        'loader': f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2v4"/><path d="m16.2 7.8 2.9-2.9"/><path d="M18 12h4"/><path d="m16.2 16.2 2.9 2.9"/><path d="M12 18v4"/><path d="m4.9 19.1 2.9-2.9"/><path d="M2 12h4"/><path d="m4.9 4.9 2.9 2.9"/></svg>',
        'entity': f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="5" r="1"/><path d="m9 20 3-6 3 6"/><path d="m6 8 6 2 6-2"/><path d="M12 10v4"/></svg>',
        'window': f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="18" x="3" y="3" rx="2"/><path d="M3 9h18"/><path d="M9 21V9"/></svg>',
        'expand': f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 12h6"/><path d="M8 12H2"/><path d="M12 2v2"/><path d="M12 8v2"/><path d="M12 14v2"/><path d="M12 20v2"/><path d="m19 15 3-3-3-3"/><path d="m5 9-3 3 3 3"/></svg>',
        'collapse': f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12h6"/><path d="M22 12h-6"/><path d="M12 2v2"/><path d="M12 8v2"/><path d="M12 14v2"/><path d="M12 20v2"/><path d="m19 9-3 3 3 3"/><path d="m5 15 3-3-3-3"/></svg>',
        'copy_logs': f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="8" height="4" x="8" y="2" rx="1" ry="1"/><path d="M8 4H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"/><path d="M16 4h2a2 2 0 0 1 2 2v4"/><path d="M21 14H11"/><path d="m15 10-4 4 4 4"/></svg>',
        'reset': f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/></svg>',
    }
