import os
import queue
import re
import sys
import time

from loguru import logger
import ctypes

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QCheckBox, QLineEdit, QTextEdit,
    QPlainTextEdit, QComboBox, QFrame, QDialog,
)
from PyQt6.QtCore import QTimer, Qt, QSize
from PyQt6.QtGui import QPixmap, QIcon, QFont, QPainter
from PyQt6.QtSvg import QSvgRenderer

from src.lang import load_lang
from src.gui.commands import GUICommand, GUICommandType, GUIKeys, _format_binding
from src.gui.widgets import AnimatedTabWidget, ConsoleTextEdit, PyQtSink, HighlightOverlay
from src.gui.helpers import (
    resource_path, centered_label, copy_icon_btn, copy_callback, build_shared_svgs,
    init_recent_imports,
)
from src.gui.actions import ActionRegistry
from src.gui.theme import compute_styles
from src.gui.popups import show_ui_tree_popup, show_entity_list_popup

from src.gui.tab_launcher import build_launcher_tab
from src.gui.tab_hotkeys import build_hotkeys_tab
from src.gui.tab_camera import build_camera_tab
from src.gui.tab_dev_utils import build_dev_utils_tab
from src.gui.tab_stats import build_stats_tab
from src.gui.tab_actions import build_flythrough_tab, build_bot_tab, build_combat_tab


class GUIContext:
    """Shared state passed to tab builders."""
    pass


def manage_gui(send_queue: queue.Queue, recv_queue: queue.Queue, theme_dict, tool_name, tool_version, gui_on_top, langcode, gui_font='Segoe UI', gui_font_size=9, tool_author='Deimos-Wizard101', settings=None):
    tl = load_lang(langcode)

    # Set AppUserModelID so Windows uses our icon in taskbar/process list
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(f"deimos.{tool_name}")
    except Exception:
        pass

    app = QApplication(sys.argv)
    app.setFont(QFont(gui_font if gui_font else "Segoe UI", gui_font_size if gui_font_size else 9))

    _vp_height = 450

    # Compute styles from theme dict (includes font in stylesheet)
    styles = compute_styles(theme_dict, gui_font, gui_font_size)
    _bg_color = theme_dict['bg_color']
    _text_color = theme_dict['text_color']
    _stroke_color = theme_dict['stroke_color']

    _hex_bg = _bg_color.lstrip('#')
    _r, _g, _b = int(_hex_bg[0:2], 16), int(_hex_bg[2:4], 16), int(_hex_bg[4:6], 16)
    _theme = "dark" if (_r + _g + _b) < 384 else "light"

    btn_style = styles['btn_style']
    icon_btn_style = styles['icon_btn_style']

    app.setStyleSheet(styles['app_style'])

    window = QMainWindow()
    _window_flags = Qt.WindowType.FramelessWindowHint
    if gui_on_top:
        _window_flags |= Qt.WindowType.WindowStaysOnTopHint
    window.setWindowFlags(_window_flags)
    window.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)

    # Enable Windows 11 rounded corners on frameless window
    try:
        import ctypes, ctypes.wintypes
        _hwnd = ctypes.wintypes.HWND(int(window.winId()))
        DWMWA_WINDOW_CORNER_PREFERENCE = 33
        DWMWCP_ROUND = ctypes.c_int(2)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            _hwnd, DWMWA_WINDOW_CORNER_PREFERENCE,
            ctypes.byref(DWMWCP_ROUND), ctypes.sizeof(DWMWCP_ROUND)
        )
    except Exception:
        pass
    window.setStyleSheet(styles['groupbox_style'])
    window.setFixedHeight(_vp_height)

    _ico_path = resource_path("Deimos-logo.ico")
    if os.path.exists(_ico_path):
        window.setWindowIcon(QIcon(_ico_path))

    central = QWidget()
    window.setCentralWidget(central)
    main_layout = QVBoxLayout(central)
    main_layout.setContentsMargins(0, 0, 0, 0)
    main_layout.setSpacing(0)

    # ==================== Custom Titlebar ====================
    _tc = _text_color
    _sc = _stroke_color
    _close_svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{_sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>'
    _minimize_svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{_sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14"/></svg>'
    _pin_svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{_sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 17v5"/><path d="M9 10.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24V16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V7a1 1 0 0 1 1-1 2 2 0 0 0 0-4H8a2 2 0 0 0 0 4 1 1 0 0 1 1 1z"/></svg>'
    _unpin_svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{_sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 17v5"/><path d="M15 9.34V7a1 1 0 0 1 1-1 2 2 0 0 0 0-4H7.89"/><path d="m2 2 20 20"/><path d="M9 9v1.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24V16a1 1 0 0 0 1 1h11"/></svg>'

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
    titlebar.setStyleSheet(styles['titlebar_style'])
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
    pin_btn.setToolTip(tl('always_on_top') if _is_pinned[0] else tl('not_on_top'))
    pin_btn.setFixedSize(32, 24)
    pin_btn.setStyleSheet(_titlebar_btn_style)
    pin_btn.setCursor(Qt.CursorShape.PointingHandCursor)

    def _toggle_pin():
        _is_pinned[0] = not _is_pinned[0]
        if settings:
            settings.set_setting('on_top', _is_pinned[0])
        # Use ctx.pin_svgs for theme-aware icons (updated by apply_theme)
        if hasattr(ctx, 'pin_svgs'):
            _cur_pin, _cur_unpin = ctx.pin_svgs
            pin_btn.setIcon(_titlebar_svg_icon(_cur_pin if _is_pinned[0] else _cur_unpin))
        else:
            pin_btn.setIcon(_pin_icon if _is_pinned[0] else _unpin_icon)
        pin_btn.setToolTip(tl('always_on_top') if _is_pinned[0] else tl('not_on_top'))
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

    # Gear button (settings) — callback uses late-binding since ctx doesn't exist yet
    _gear_svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{_sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/></svg>'
    gear_btn = QPushButton()
    gear_btn.setIcon(_titlebar_svg_icon(_gear_svg))
    gear_btn.setFixedSize(32, 24)
    gear_btn.setStyleSheet(_titlebar_btn_style)
    gear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    gear_btn.setToolTip(tl('settings') if tl('settings') != 'settings' else 'Settings')
    titlebar_layout.addWidget(gear_btn)

    # Center: title
    titlebar_layout.addStretch()

    title_label = QLabel(f'{tool_name} v{tool_version}')
    title_label.setStyleSheet(f"QLabel {{ color: {_tc}; font-weight: bold; background: transparent; }}")
    titlebar_layout.addWidget(title_label)

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
    tabs.setStyleSheet("QTabWidget::tab-bar { alignment: center; }")
    content_layout.addWidget(tabs)

    # Widget tag registry for backend updates
    widget_tags = {}

    # Build shared SVGs and registry
    svgs = build_shared_svgs(_stroke_color)

    registry = ActionRegistry(settings, tl, send_queue, btn_style, icon_btn_style, _titlebar_svg_icon)

    # ==================== GUIContext ====================
    ctx = GUIContext()
    ctx.send_queue = send_queue
    ctx.widget_tags = widget_tags
    ctx.tl = tl
    ctx.settings = settings
    ctx.window = window
    ctx.app = app
    ctx.titlebar = titlebar
    ctx.stroke_color = _stroke_color
    ctx.text_color = _text_color
    ctx.bg_color = _bg_color
    ctx.theme = _theme
    ctx.btn_style = btn_style
    ctx.btn_color_hex = theme_dict['button_color']
    ctx.gui_font = gui_font
    ctx.gui_font_size = gui_font_size
    ctx.icon_btn_style = icon_btn_style
    ctx.tool_name = tool_name
    ctx.tool_version = tool_version
    ctx.tool_author = tool_author
    ctx.registry = registry
    ctx.exports = {}
    ctx.svgs = svgs
    ctx.titlebar_svg_icon = _titlebar_svg_icon
    ctx.repo_base = f"https://github.com/{tool_author}/{tool_name}-Wizard101"
    ctx.wiki_base = f"{ctx.repo_base}/wiki"
    ctx.tabs = tabs
    ctx.tracked_icon_buttons = []
    ctx.tracked_svg_labels = []
    ctx.tracked_toggle_btns = []
    ctx.toggle_switches = []
    ctx.titlebar_buttons = [
        (pin_btn, _pin_svg),
        (gear_btn, _gear_svg),
        (minimize_btn, _minimize_svg),
        (close_btn, _close_svg),
    ]
    ctx.pin_svgs = (_pin_svg, _unpin_svg)
    ctx.is_pinned = _is_pinned
    ctx.title_label = title_label

    init_recent_imports(settings)

    # Late-bind gear button now that ctx exists
    def _open_settings():
        from src.gui.settings_dialog import show_settings_dialog
        show_settings_dialog(ctx)
    gear_btn.clicked.connect(lambda: _open_settings())

    # ==================== Build Tabs ====================
    registry._ctx = ctx
    ctx.current_tab_name = ''

    ctx.current_tab_name = tl('launcher')
    launcher_tab = build_launcher_tab(ctx)
    tabs.addTab(launcher_tab, tl('launcher'))

    ctx.current_tab_name = tl('hotkeys')
    hotkeys_tab = build_hotkeys_tab(ctx)
    tabs.addTab(hotkeys_tab, tl('hotkeys'))

    ctx.current_tab_name = tl('camera')
    camera_tab = build_camera_tab(ctx)
    tabs.addTab(camera_tab, tl('camera'))

    ctx.current_tab_name = tl('dev_utils')
    dev_tab = build_dev_utils_tab(ctx)
    tabs.addTab(dev_tab, tl('dev_utils'))

    ctx.current_tab_name = tl('stats')
    stats_tab = build_stats_tab(ctx)
    tabs.addTab(stats_tab, tl('stats'))

    ctx.current_tab_name = tl('flythrough')
    flythrough_tab = build_flythrough_tab(ctx)
    tabs.addTab(flythrough_tab, tl('flythrough'))

    ctx.current_tab_name = tl('bot')
    bot_tab = build_bot_tab(ctx)
    tabs.addTab(bot_tab, tl('bot'))

    ctx.current_tab_name = tl('combat')
    combat_tab = build_combat_tab(ctx)
    tabs.addTab(combat_tab, tl('combat'))

    ctx.current_tab_name = ''

    # ==================== Console Tab ====================
    console_tab = QWidget()
    console_layout = QVBoxLayout(console_tab)
    console_layout.setContentsMargins(4, 4, 4, 4)
    console_layout.addWidget(centered_label(tl('console_support')))

    console_text = ConsoleTextEdit()
    console_text.setReadOnly(True)
    console_text.setStyleSheet(
        "QScrollBar:vertical { width: 6px; background: transparent; }"
        "QScrollBar::handle:vertical { background: rgba(255,255,255,40); border-radius: 3px; min-height: 20px; }"
        "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }"
    )
    widget_tags['-CONSOLE-'] = console_text
    console_layout.addWidget(console_text, 1)

    _logs_expanded = [False]

    toggle_expand_btn = QPushButton()
    toggle_expand_btn.setIcon(_titlebar_svg_icon(svgs['expand'], 32))
    toggle_expand_btn.setFixedSize(40, 40)
    toggle_expand_btn.setStyleSheet(icon_btn_style)
    toggle_expand_btn.setToolTip(tl('collapse_expand_logs'))
    toggle_expand_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    # Track with current SVG for restyle (expand is default state)
    ctx.tracked_icon_buttons.append((toggle_expand_btn, svgs['expand'], 32))

    console_psg = PyQtSink(console_text)

    def _toggle_expand_logs():
        _logs_expanded[0] = not _logs_expanded[0]
        _svg = ctx.svgs['collapse'] if _logs_expanded[0] else ctx.svgs['expand']
        toggle_expand_btn.setIcon(_titlebar_svg_icon(_svg, 32))
        console_psg.toggle_show_expanded_logs()

    toggle_expand_btn.clicked.connect(_toggle_expand_logs)

    console_btn_row = QHBoxLayout()
    console_btn_row.addStretch()
    console_btn_row.addWidget(toggle_expand_btn)
    console_btn_row.addWidget(registry.action_icon_btn(svgs['copy_logs'], tl('copy_logs'), copy_callback(send_queue, GUIKeys.copy_logs)))
    console_btn_row.addStretch()
    console_layout.addLayout(console_btn_row)
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

    client_label = QLabel(tl('client') + ': ')
    widget_tags['Title'] = client_label

    _entity_svg = svgs['entity']
    entities_btn = QPushButton()
    entities_btn.setIcon(_titlebar_svg_icon(_entity_svg, 16))
    entities_btn.setFixedSize(20, 20)
    entities_btn.setStyleSheet(icon_btn_style)
    entities_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    entities_btn.setToolTip(tl('available_entities'))
    entities_btn.clicked.connect(copy_callback(send_queue, GUIKeys.copy_entity_list))
    ctx.tracked_icon_buttons.append((entities_btn, _entity_svg, 16))

    _window_svg = svgs['window']
    paths_btn = QPushButton()
    paths_btn.setIcon(_titlebar_svg_icon(_window_svg, 16))
    paths_btn.setFixedSize(20, 20)
    paths_btn.setStyleSheet(icon_btn_style)
    paths_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    paths_btn.setToolTip(tl('available_paths'))
    paths_btn.clicked.connect(copy_callback(send_queue, GUIKeys.copy_ui_tree))
    ctx.tracked_icon_buttons.append((paths_btn, _window_svg, 16))

    footer_vbox.addLayout(_footer_row(client_label, entities_btn, paths_btn))

    zone_label = QLabel(tl('zone') + ': ')
    widget_tags['Zone'] = zone_label
    footer_vbox.addLayout(_footer_row(zone_label, copy_icon_btn(ctx, copy_callback(send_queue, GUIKeys.copy_zone))))

    xyz_label = QLabel(tl('position_xyz') + ' ')
    widget_tags['xyz'] = xyz_label
    footer_vbox.addLayout(_footer_row(xyz_label, copy_icon_btn(ctx, copy_callback(send_queue, GUIKeys.copy_position))))

    pry_label = QLabel(tl('orientation_pry') + ' ')
    widget_tags['pry'] = pry_label
    footer_vbox.addLayout(_footer_row(pry_label, copy_icon_btn(ctx, copy_callback(send_queue, GUIKeys.copy_rotation))))

    content_layout.addLayout(footer_vbox)

    # ==================== Console Sink ====================
    global console_sink
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
    ok_btn = QPushButton(tl('ok'))
    ok_btn.clicked.connect(license_dialog.close)
    ld_layout.addWidget(ok_btn, alignment=Qt.AlignmentFlag.AlignCenter)
    license_dialog.adjustSize()
    hint = license_dialog.sizeHint()
    license_dialog.setFixedSize(max(int(hint.width() * 1.5), 350), hint.height())
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
    entity_popup_ref = [None]
    stats = ctx.exports.get('stats', {})
    launcher = ctx.exports.get('launcher', {})
    hotkeys_exports = ctx.exports.get('hotkeys', {})
    dev_utils_exports = ctx.exports.get('dev_utils', {})
    flythrough_exports = ctx.exports.get('flythrough', {})
    bot_exports = ctx.exports.get('bot', {})

    # Load dynamic hotkey rows now that all buttons/actions have been registered
    static_ids = hotkeys_exports.get('static_ids', set())
    add_dynamic_hk_row = hotkeys_exports.get('add_dynamic_hk_row')
    if settings and add_dynamic_hk_row:
        for aid, binding in settings.get_hotkeys().items():
            if aid not in static_ids and binding is not None and aid in registry.meta:
                add_dynamic_hk_row(aid)

    highlight_overlay = [None]  # Lazy: created on first UpdateHighlightBox

    # Cache stats references
    duel_circle = stats.get('duel_circle')
    ctx.duel_circle = duel_circle
    _swapped = stats.get('swapped', [False])
    _last_stat_response = stats.get('last_stat_response', [{}])
    _update_damage_readout = stats.get('update_damage_readout', lambda: None)
    _pending_view_side = stats.get('pending_view_side', [None])
    _update_stat_popup_rows = stats.get('update_stat_popup_rows', lambda v: None)
    _last_calc_school = stats.get('last_calc_school', [''])

    # Cache launcher references
    _populate_account_list = launcher.get('populate_account_list', lambda v: None)
    _rebuild_hooked_clients_list = launcher.get('rebuild_hooked_clients_list', lambda: None)
    _refresh_account_eligibility = launcher.get('refresh_account_eligibility', lambda v: None)
    _hooking_handles = launcher.get('hooking_handles', set())
    _last_hooked_data = launcher.get('last_hooked_data', {})
    account_list = launcher.get('account_list')

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
                            if _swapped[0]:
                                duel_circle.set_ally_name(str(value))
                            else:
                                duel_circle.set_enemy_name(str(value))
                        elif tag == 'AllyInput':
                            if _swapped[0]:
                                duel_circle.set_enemy_name(str(value))
                            else:
                                duel_circle.set_ally_name(str(value))
                        elif tag == 'calc_school':
                            _last_calc_school[0] = str(value)
                            _update_damage_readout()
                        elif tag == 'stat_viewer':
                            if _pending_view_side[0] is not None:
                                _update_stat_popup_rows(value)
                                _pending_view_side[0] = None
                            _last_stat_response[0] = value
                            _update_damage_readout()
                        elif tag == 'slot_info':
                            if _swapped[0]:
                                swapped_info = {}
                                for (side, idx), info in value.items():
                                    new_side = 'ally' if side == 'enemy' else 'enemy'
                                    new_info = dict(info)
                                    if 'is_friendly' in new_info:
                                        new_info['is_friendly'] = not new_info['is_friendly']
                                    swapped_info[(new_side, idx)] = new_info
                                duel_circle.set_slot_info(swapped_info)
                            else:
                                duel_circle.set_slot_info(value)
                        elif tag == 'FlythroughStatus':
                            flythrough_exports.get('set_running', lambda v: None)(value == 'Enabled')
                        elif tag == 'BotStatus':
                            bot_exports.get('set_running', lambda v: None)(value == 'Enabled')
                        else:
                            widget = widget_tags.get(tag)
                            if widget is not None:
                                if isinstance(widget, QCheckBox):
                                    widget.setChecked(value == 'Enabled')
                                elif isinstance(widget, QLabel) and hasattr(widget, 'setChecked'):
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
                        if tag == 'EnemyInput':
                            if _swapped[0]:
                                duel_circle.set_ally_count(len(values))
                            else:
                                duel_circle.set_enemy_count(len(values))
                            if duel_circle._enemy_count == 0 and duel_circle._ally_count == 0:
                                _last_stat_response[0] = {}
                                _update_damage_readout()
                        elif tag == 'AllyInput':
                            if _swapped[0]:
                                duel_circle.set_enemy_count(len(values))
                            else:
                                duel_circle.set_ally_count(len(values))
                            if duel_circle._enemy_count == 0 and duel_circle._ally_count == 0:
                                _last_stat_response[0] = {}
                                _update_damage_readout()
                        else:
                            widget = widget_tags.get(tag)
                            if widget is not None and isinstance(widget, QComboBox):
                                widget.clear()
                                widget.addItems(values)

                    case GUICommandType.UpdateConsole:
                        console_psg.toggle_show_expanded_logs()

                    case GUICommandType.ShowUITreePopup:
                        tree_str, tree_texts = com.data
                        show_ui_tree_popup(window, send_queue, tree_str, tree_texts, lambda cb: copy_icon_btn(ctx, cb), tl=tl)

                    case GUICommandType.ShowEntityListPopup:
                        if entity_popup_ref[0] is not None:
                            try:
                                entity_popup_ref[0].close()
                            except Exception:
                                pass
                        entity_popup_ref[0] = show_entity_list_popup(window, send_queue, widget_tags, tabs, dev_tab, camera_tab, tl=tl)

                    case GUICommandType.UpdateEntityListData:
                        popup = entity_popup_ref[0]
                        if popup is not None and popup.isVisible():
                            popup.update_entities(com.data)
                        else:
                            entity_popup_ref[0] = None

                    case GUICommandType.UpdateHighlightBox:
                        if com.data is not None:
                            if highlight_overlay[0] is None:
                                highlight_overlay[0] = HighlightOverlay()
                            game_hwnd, x1, y1, x2, y2 = com.data
                            highlight_overlay[0].update_box(game_hwnd, x1, y1, x2, y2)
                        else:
                            if highlight_overlay[0] is not None:
                                highlight_overlay[0].clear_box()

                    case GUICommandType.CopyConsole:
                        console_psg.copy()

                    case GUICommandType.InvokeAction:
                        action_cb = registry.callbacks.get(com.data)
                        if action_cb:
                            action_cb()

                    case GUICommandType.UpdateAccountList:
                        if com.data is not None:
                            _populate_account_list(com.data)

                    case GUICommandType.UpdateHookedClients:
                        if com.data:
                            managed_accounts = com.data.get('managed_accounts', [])
                            widget_tags['managed_accounts'] = set(managed_accounts)
                            _refresh_account_eligibility(managed_accounts)
                            _hooking_handles.intersection_update(set(com.data.get('unmanaged', [])))
                            _last_hooked_data.clear()
                            _last_hooked_data.update(com.data)
                        else:
                            _last_hooked_data.clear()
                            _hooking_handles.clear()
                        _rebuild_hooked_clients_list()
                        _update_mc = hotkeys_exports.get('update_multi_client_state')
                        hooked_count = len(_last_hooked_data.get('hooked', []))
                        if _update_mc:
                            _update_mc(hooked_count)
                        _update_dev_mass = dev_utils_exports.get('update_mass_state')
                        if _update_dev_mass:
                            _update_dev_mass(hooked_count)

                    case GUICommandType.ClearLaunchCheckboxes:
                        if account_list and not (settings and settings.get_setting('remember_chosen_clients')):
                            for i in range(account_list.count()):
                                item = account_list.item(i)
                                w = account_list.itemWidget(item)
                                if w:
                                    cb = w.findChild(QCheckBox)
                                    if cb:
                                        cb.setChecked(False)

        except queue.Empty:
            pass

    timer = QTimer()
    timer.timeout.connect(poll_queue)
    timer.start(16)

    window.show()
    # Lock width to the tab bar width + content margins
    tab_bar_width = tabs.tabBar().sizeHint().width()
    margins = content_layout.contentsMargins()
    window.setFixedWidth(tab_bar_width + margins.left() + margins.right() + 8)
    app.exec()

    # After app exits, signal backend
    if not close_accepted[0]:
        send_queue.put(GUICommand(GUICommandType.AttemptedClose))
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


console_sink = None
