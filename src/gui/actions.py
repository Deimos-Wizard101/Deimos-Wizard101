import re

from PyQt6.QtWidgets import QPushButton, QMenu
from PyQt6.QtCore import Qt

from src.gui.commands import GUICommand, GUICommandType, _format_binding


class ActionRegistry:
    """Centralizes the hotkey action system: registration, binding, styled buttons."""

    def __init__(self, settings, tl, send_queue, btn_style, icon_btn_style, titlebar_svg_icon_fn):
        self.settings = settings
        self.tl = tl
        self.send_queue = send_queue
        self.btn_style = btn_style
        self.icon_btn_style = icon_btn_style
        self._titlebar_svg_icon = titlebar_svg_icon_fn

        self.callbacks = {}   # action_id -> callback function
        self.meta = {}        # action_id -> {'name': str, 'category': str}
        self.key_labels = {}  # action_id -> QLabel (in manager tab, for live sync)
        self.clear_btns = {}  # action_id -> QPushButton (the X button)
        self.row_widgets = {} # action_id -> QWidget (row container, for show/hide)
        self._auto_counter = 0
        self.add_dynamic_hk_row = None  # Set by hotkeys tab after construction
        self._styled_buttons = []       # tracked QPushButtons with btn_style
        self._icon_buttons = []         # tracked (QPushButton, svg_str) for icon buttons

    def register(self, action_id, name, category, callback):
        self.callbacks[action_id] = callback
        self.meta[action_id] = {'name': name, 'category': category}

    def get_binding_display(self, action_id):
        if self.settings is None:
            return self.tl('unbound')
        hotkeys = self.settings.get_hotkeys()
        binding = hotkeys.get(action_id)
        if binding is None:
            return self.tl('unbound')
        return _format_binding(binding.get("key"), binding.get("modifiers"))

    def do_rebind(self, action_id, key, mods):
        """Send rebind command to backend and update all UI labels."""
        if self.settings:
            if key:
                self.settings.set_hotkey(action_id, key, mods or [])
            else:
                self.settings.clear_hotkey(action_id)
        if key:
            self.send_queue.put(GUICommand(GUICommandType.RebindHotkey, (action_id, key, mods)))
        else:
            self.send_queue.put(GUICommand(GUICommandType.RebindHotkey, (action_id, None, None)))
        display = _format_binding(key, mods) if key else self.tl('unbound')
        if action_id not in self.key_labels and key:
            if self.add_dynamic_hk_row:
                self.add_dynamic_hk_row(action_id)
        if action_id in self.key_labels:
            self.key_labels[action_id].setText(display)
        if key and action_id in self.row_widgets:
            self.row_widgets[action_id].setVisible(True)

    def make_bindable(self, btn, action_id):
        """Attach right-click context menu for hotkey binding to a button."""
        btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        tl = self.tl
        def _on_context(pos):
            menu = QMenu(btn)
            bind_action = menu.addAction(tl('bind_hotkey') + "...")
            unbind_action = None
            current_display = self.get_binding_display(action_id)
            if current_display != tl('unbound'):
                unbind_action = menu.addAction(tl('unbind_hotkey') + f" ({current_display})")
            action = menu.exec(btn.mapToGlobal(pos))
            if action == bind_action:
                from src.gui.widgets import HotkeyCapture
                meta = self.meta.get(action_id, {})
                all_bindings = self.settings.get_hotkeys() if self.settings else {}
                dlg = HotkeyCapture(meta.get('name', action_id), all_bindings, action_id, tl=tl, parent=btn.window())
                def _on_captured(key, mods):
                    if key == "":
                        self.do_rebind(action_id, None, None)
                    else:
                        self.do_rebind(action_id, key, mods)
                dlg.captured.connect(_on_captured)
                dlg.exec()
            elif unbind_action and action == unbind_action:
                self.do_rebind(action_id, None, None)
        btn.customContextMenuRequested.connect(_on_context)

    def styled_btn(self, label, callback=None, action_id=None):
        btn = QPushButton(label)
        btn.setStyleSheet(self.btn_style)
        self._styled_buttons.append(btn)
        if callback:
            btn.clicked.connect(callback)
            aid = action_id
            if aid is None:
                aid = re.sub(r'[^a-z0-9]+', '_', label.lower()).strip('_')
                if aid in self.meta:
                    self._auto_counter += 1
                    aid = f"{aid}_{self._auto_counter}"
            if aid not in self.meta:
                self.register(aid, label, '', callback)
            self.make_bindable(btn, aid)
        return btn

    def action_icon_btn(self, svg_str, tooltip, callback):
        btn = QPushButton()
        btn.setIcon(self._titlebar_svg_icon(svg_str, 32))
        btn.setFixedSize(40, 40)
        btn.setStyleSheet(self.icon_btn_style)
        btn.setToolTip(tooltip)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(callback)
        self._icon_buttons.append((btn, svg_str))
        aid = re.sub(r'[^a-z0-9]+', '_', tooltip.lower()).strip('_')
        if aid in self.meta:
            self._auto_counter += 1
            aid = f"{aid}_{self._auto_counter}"
        self.register(aid, tooltip, '', callback)
        self.make_bindable(btn, aid)
        return btn

    def restyle_all(self, btn_style, icon_btn_style, svg_icon_fn, old_stroke, new_stroke):
        """Re-apply styles to all tracked buttons after a theme change."""
        self.btn_style = btn_style
        self.icon_btn_style = icon_btn_style
        live_styled = []
        for btn in self._styled_buttons:
            try:
                btn.setStyleSheet(btn_style)
                live_styled.append(btn)
            except RuntimeError:
                pass
        self._styled_buttons = live_styled
        new_icon_buttons = []
        for btn, svg_str in self._icon_buttons:
            try:
                new_svg = svg_str.replace(old_stroke, new_stroke)
                btn.setIcon(svg_icon_fn(new_svg, 32))
                btn.setStyleSheet(icon_btn_style)
                new_icon_buttons.append((btn, new_svg))
            except RuntimeError:
                pass
        self._icon_buttons = new_icon_buttons
