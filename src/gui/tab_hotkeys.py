import os

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from src.gui.commands import GUICommand, GUICommandType, GUIKeys
from src.gui.helpers import (
    centered_label,
    repo_icon_btn,
    resource_path,
    teleport_callback,
    toggle_callback,
)
from src.gui.widgets import HotkeyCapture, ToggleNameLabel


def build_hotkeys_tab(ctx):
    tab = QWidget()
    hotkeys_layout = QHBoxLayout(tab)
    hotkeys_layout.setContentsMargins(4, 4, 4, 4)
    hotkeys_layout.setSpacing(4)

    registry = ctx.registry
    tl = ctx.tl
    send_queue = ctx.send_queue
    settings = ctx.settings

    # Callbacks used by bindable actions
    def xyz_sync_callback():
        send_queue.put(GUICommand(GUICommandType.XYZSync))

    def x_press_callback():
        send_queue.put(GUICommand(GUICommandType.XPress))

    def friend_tp_callback():
        send_queue.put(GUICommand(GUICommandType.FriendTeleport))

    # def dialogue_side_quests_callback():
    #     send_queue.put(GUICommand(GUICommandType.ToggleDialogueSideQuests))

    # --- Left panel: Hotkey Manager ---
    hk_manager = QWidget()
    hk_manager.setFixedWidth(310)
    hk_manager_layout = QVBoxLayout(hk_manager)
    hk_manager_layout.setContentsMargins(0, 0, 0, 0)
    hk_manager_layout.setSpacing(4)

    sc = ctx.stroke_color
    _toggle_icons = {
        "gauge": f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m12 14 4-4"/><path d="M3.34 19a10 10 0 1 1 17.32 0"/></svg>',
        "combat": f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12.035 17.012a3 3 0 0 0-3-3l-.311-.002a.72.72 0 0 1-.505-1.229l1.195-1.195A2 2 0 0 1 10.828 11H12a2 2 0 0 0 0-4H9.243a3 3 0 0 0-2.122.879l-2.707 2.707A4.83 4.83 0 0 0 3 14a8 8 0 0 0 8 8h2a8 8 0 0 0 8-8V7a2 2 0 1 0-4 0v2a2 2 0 1 0 4 0"/><path d="M13.888 9.662A2 2 0 0 0 17 8V5A2 2 0 1 0 13 5"/><path d="M9 5A2 2 0 1 0 5 5V10"/><path d="M9 7V4A2 2 0 1 1 13 4V7.268"/></svg>',
        "speech": f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8.8 20v-4.1l1.9.2a2.3 2.3 0 0 0 2.164-2.1V8.3A5.37 5.37 0 0 0 2 8.25c0 2.8.656 3.054 1 4.55a5.77 5.77 0 0 1 .029 2.758L2 20"/><path d="M19.8 17.8a7.5 7.5 0 0 0 .003-10.603"/><path d="M17 15a3.5 3.5 0 0 0-.025-4.975"/></svg>',
        "bot": f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 8V4H8"/><rect width="16" height="12" x="4" y="8" rx="2"/><path d="M2 14h2"/><path d="M20 14h2"/><path d="M15 13v2"/><path d="M9 13v2"/></svg>',
        "brain": f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5a3 3 0 1 0-5.997.125 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .556 6.588A4 4 0 1 0 12 18Z"/><path d="M9 13a4.5 4.5 0 0 0 3-4"/><path d="M6.003 5.125A3 3 0 0 0 6.401 6.5"/><path d="M3.477 10.896a4 4 0 0 1 .585-.396"/><path d="M6 18a4 4 0 0 1-1.967-.516"/><path d="M12 13h4"/><path d="M12 18h6a2 2 0 0 1 2 2v1"/><path d="M12 8h8"/><path d="M16 8V5a2 2 0 0 1 2-2"/><circle cx="16" cy="13" r=".5"/><circle cx="18" cy="3" r=".5"/><circle cx="20" cy="21" r=".5"/><circle cx="20" cy="8" r=".5"/></svg>',
        "paw": f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="4" r="2"/><circle cx="18" cy="8" r="2"/><circle cx="20" cy="16" r="2"/><path d="M9 10a5 5 0 0 1 5 5v3.5a3.5 3.5 0 0 1-6.84 1.045Q6.52 17.48 4.46 16.84A3.5 3.5 0 0 1 5.5 10Z"/></svg>',
        "flask": f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 2v6.292a7 7 0 1 0 4 0V2"/><path d="M5 15h14"/><path d="M8.5 2h7"/></svg>',
        "cctv": f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 19H4a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h5"/><path d="M13 5h7a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2h-5"/><circle cx="12" cy="12" r="3"/><path d="m18 22-3-3 3-3"/><path d="m6 2 3 3-3 3"/></svg>',
        "goal": f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 13V2l8 4-8 4"/><path d="M20.561 10.222a9 9 0 1 1-12.55-5.29"/><path d="M8.002 9.997a5 5 0 1 0 8.9 2.02"/></svg>',
        "view": f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 17v2a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-2"/><path d="M21 7V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v2"/><circle cx="12" cy="12" r="1"/><path d="M18.944 12.33a1 1 0 0 0 0-.66 7.5 7.5 0 0 0-13.888 0 1 1 0 0 0 0 .66 7.5 7.5 0 0 0 13.888 0"/></svg>',
        "contact": f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 2v2"/><path d="M7 22v-2a2 2 0 0 1 2-2h6a2 2 0 0 1 2 2v2"/><path d="M8 2v2"/><circle cx="12" cy="11" r="3"/><rect x="3" y="4" width="18" height="18" rx="2"/></svg>',
        "users": f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><path d="M16 3.128a4 4 0 0 1 0 7.744"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><circle cx="9" cy="7" r="4"/></svg>',
        "locate": f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="2" x2="5" y1="12" y2="12"/><line x1="19" x2="22" y1="12" y2="12"/><line x1="12" x2="12" y1="2" y2="5"/><line x1="12" x2="12" y1="19" y2="22"/><circle cx="12" cy="12" r="7"/><circle cx="12" cy="12" r="3"/></svg>',
        "keyboard": f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 8h.01"/><path d="M12 12h.01"/><path d="M14 8h.01"/><path d="M16 12h.01"/><path d="M18 8h.01"/><path d="M6 8h.01"/><path d="M7 16h10"/><path d="M8 12h.01"/><rect width="20" height="16" x="2" y="4" rx="2"/></svg>',
        "custom": f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.5 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v5.5"/><path d="m14.3 19.6 1-.4"/><path d="M15 3v7.5"/><path d="m15.2 16.9-.9-.3"/><path d="m16.6 21.7.3-.9"/><path d="m16.8 15.3-.4-1"/><path d="m19.1 15.2.3-.9"/><path d="m19.6 21.7-.4-1"/><path d="m20.7 16.8 1-.4"/><path d="m21.7 19.4-.9-.3"/><path d="M9 3v18"/><circle cx="18" cy="18" r="3"/></svg>',
        "chevron": f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m6 17 5-5-5-5"/><path d="m13 17 5-5-5-5"/></svg>',
        "exit": f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 12h11"/><path d="m17 16 4-4-4-4"/><path d="M21 6.344V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-1.344"/></svg>',
    }

    _hk_categories = [
        (
            tl("cat_toggles"),
            [
                (
                    "toggle_speed",
                    tl("speedhack"),
                    toggle_callback(send_queue, GUIKeys.toggle_speedhack),
                    True,
                    tl("speedhack"),
                    _toggle_icons["gauge"],
                ),
                (
                    "toggle_combat",
                    tl("combat_toggle"),
                    toggle_callback(send_queue, GUIKeys.toggle_combat),
                    True,
                    tl("combat_toggle"),
                    _toggle_icons["combat"],
                ),
                (
                    "toggle_dialogue",
                    tl("dialogue"),
                    toggle_callback(send_queue, GUIKeys.toggle_dialogue),
                    True,
                    tl("dialogue"),
                    _toggle_icons["speech"],
                ),
                # ("toggle_dialogue_side_quests", tl('dialogue_side_quests'), dialogue_side_quests_callback, False, None, _toggle_icons['speech']),
                (
                    "toggle_sigil",
                    tl("sigil"),
                    toggle_callback(send_queue, GUIKeys.toggle_sigil),
                    True,
                    tl("sigil"),
                    _toggle_icons["bot"],
                ),
                (
                    "toggle_questing",
                    tl("questing"),
                    toggle_callback(send_queue, GUIKeys.toggle_questing),
                    True,
                    tl("questing"),
                    _toggle_icons["brain"],
                ),
                (
                    "toggle_auto_pet",
                    tl("auto_pet"),
                    toggle_callback(send_queue, GUIKeys.toggle_auto_pet),
                    True,
                    tl("auto_pet"),
                    _toggle_icons["paw"],
                ),
                (
                    "toggle_auto_potion",
                    tl("auto_potion"),
                    toggle_callback(send_queue, GUIKeys.toggle_auto_potion),
                    True,
                    tl("auto_potion"),
                    _toggle_icons["flask"],
                ),
                (
                    "toggle_freecam",
                    tl("freecam"),
                    toggle_callback(send_queue, GUIKeys.toggle_freecam),
                    True,
                    tl("freecam"),
                    _toggle_icons["cctv"],
                ),
            ],
        ),
        (
            tl("cat_teleports"),
            [
                (
                    "quest_tp",
                    tl("quest_tp"),
                    teleport_callback(send_queue, GUIKeys.hotkey_quest_tp),
                    False,
                    None,
                    _toggle_icons["goal"],
                ),
                (
                    "freecam_tp",
                    tl("freecam_tp"),
                    teleport_callback(send_queue, GUIKeys.hotkey_freecam_tp),
                    False,
                    None,
                    _toggle_icons["view"],
                ),
                ("friend_tp", tl("friend_tp"), friend_tp_callback, False, None, _toggle_icons["contact"]),
            ],
        ),
        (
            tl("cat_multi_client"),
            [
                (
                    "mass_tp",
                    tl("mass_tp"),
                    teleport_callback(send_queue, GUIKeys.mass_hotkey_mass_tp),
                    False,
                    None,
                    _toggle_icons["users"],
                ),
                ("xyz_sync", tl("xyz_sync"), xyz_sync_callback, False, None, _toggle_icons["locate"]),
                ("x_press", tl("x_press"), x_press_callback, False, None, _toggle_icons["keyboard"]),
            ],
        ),
        (
            tl("cat_system"),
            [
                ("kill_tool", tl("kill_tool"), None, False, None, _toggle_icons["exit"]),
            ],
        ),
    ]

    hk_scroll = QScrollArea()
    hk_scroll.setWidgetResizable(True)
    hk_scroll.setFrameShape(QFrame.Shape.NoFrame)
    hk_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    hk_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    hk_scroll_widget = QWidget()
    hk_scroll_layout = QVBoxLayout(hk_scroll_widget)
    hk_scroll_layout.setContentsMargins(0, 2, 0, 2)
    hk_scroll_layout.setSpacing(2)

    _dynamic_header_added = [False]
    _dynamic_header_label = [None]
    _hk_stretch_index = [None]
    _dynamic_row_widgets = {}

    def _make_edit_handler(aid):
        def handler():
            meta = registry.meta.get(aid, {})
            all_bindings = settings.get_hotkeys() if settings else {}
            dlg = HotkeyCapture(meta.get("name", aid), all_bindings, aid, tl=tl, parent=tab.window())

            def _on_captured(key, mods):
                if key == "":
                    registry.do_rebind(aid, None, None)
                else:
                    registry.do_rebind(aid, key, mods)

            dlg.captured.connect(_on_captured)
            dlg.exec()

        return handler

    def _make_clear_handler(aid):
        def handler():
            registry.do_rebind(aid, None, None)
            if aid in registry.row_widgets:
                registry.row_widgets[aid].setVisible(False)

            # Hide "Other" header if all dynamic rows are now hidden
            if _dynamic_header_label[0] is not None and all(not w.isVisible() for w in _dynamic_row_widgets.values()):
                _dynamic_header_label[0].setVisible(False)

        return handler

    def _build_hk_row(
        action_id, display_name, callback, is_toggle=False, tag_name=None, icon_svg=None, removable=False, category=None
    ):
        # Parent widgets to hk_scroll_widget to prevent them from briefly
        # appearing as top-level windows (parentless QPushButtons flash on Windows).
        _p = hk_scroll_widget
        row = QHBoxLayout()
        row.setSpacing(2)
        row.setContentsMargins(0, 0, 0, 0)

        if icon_svg:
            icon_label = QLabel(_p)
            icon_label.setFixedSize(20, 20)
            icon_label.setPixmap(ctx.titlebar_svg_icon(icon_svg, 16).pixmap(16, 16))
            ctx.tracked_svg_labels.append([icon_label, icon_svg, 16, "pixmap"])
            row.addWidget(icon_label)

        if is_toggle and tag_name:
            name_label = ToggleNameLabel(display_name, _p)
            ctx.widget_tags[f"{tag_name}Status"] = name_label

        else:
            name_label = QLabel(display_name, _p)

        # icon(20) + key(70) + edit(20) + clear/spacer(20) + spacing ≈ 140px
        _name_max = 165

        if category:
            _chevron_svg = _toggle_icons["chevron"]
            chevron_label = QLabel(_p)
            chevron_label.setFixedSize(16, 16)
            chevron_label.setPixmap(ctx.titlebar_svg_icon(_chevron_svg, 16).pixmap(16, 16))
            ctx.tracked_svg_labels.append([chevron_label, _chevron_svg, 16, "pixmap"])

            cat_label = QLabel(category, _p)

            name_group = QWidget(_p)
            name_group.setMaximumWidth(_name_max)
            name_row = QHBoxLayout(name_group)
            name_row.setContentsMargins(0, 0, 0, 0)
            name_row.setSpacing(2)
            name_row.addStretch()
            name_row.addWidget(cat_label)
            name_row.addWidget(chevron_label)
            name_row.addWidget(name_label)
            name_row.addStretch()
            name_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

            if callback:
                name_group.setCursor(Qt.CursorShape.PointingHandCursor)
                name_group.mousePressEvent = (lambda cb_ref: lambda e: cb_ref())(callback)

            row.addWidget(name_group)

        else:
            name_label.setMaximumWidth(_name_max)
            name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            name_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

            if callback:
                name_label.setCursor(Qt.CursorShape.PointingHandCursor)
                name_label.mousePressEvent = (lambda cb_ref: lambda e: cb_ref())(callback)

            row.addWidget(name_label)

        key_label = QLabel(registry.get_binding_display(action_id), _p)
        key_label.setFixedWidth(70)
        key_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        key_label.setStyleSheet(f"color: {ctx.text_color}; font-style: italic;")
        registry.key_labels[action_id] = key_label
        row.addWidget(key_label)

        _pencil_svg = ctx.svgs["pencil"]
        edit_btn = QPushButton(_p)
        edit_btn.setIcon(ctx.titlebar_svg_icon(_pencil_svg, 14))
        edit_btn.setFixedSize(20, 20)
        edit_btn.setStyleSheet(ctx.icon_btn_style)
        edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        edit_btn.setToolTip(tl("bind_hotkey"))
        edit_btn.clicked.connect(_make_edit_handler(action_id))
        ctx.tracked_svg_labels.append([edit_btn, _pencil_svg, 14, "icon"])
        row.addWidget(edit_btn)

        if removable:
            _x_svg = ctx.svgs["x"]
            clear_btn = QPushButton(_p)
            clear_btn.setIcon(ctx.titlebar_svg_icon(_x_svg, 14))
            clear_btn.setFixedSize(20, 20)
            clear_btn.setStyleSheet(ctx.icon_btn_style)
            clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            clear_btn.setToolTip(tl("unbind_hotkey"))
            clear_btn.clicked.connect(_make_clear_handler(action_id))
            ctx.tracked_svg_labels.append([clear_btn, _x_svg, 14, "icon"])
            registry.clear_btns[action_id] = clear_btn
            row.addWidget(clear_btn)

        else:
            tail_spacer = QLabel(_p)
            tail_spacer.setFixedSize(20, 20)
            row.addWidget(tail_spacer)

        return row

    def _add_dynamic_hk_row(action_id):
        if action_id in _dynamic_row_widgets:
            _dynamic_row_widgets[action_id].setVisible(True)
            registry.row_widgets[action_id] = _dynamic_row_widgets[action_id]

            if _dynamic_header_label[0] is not None:
                _dynamic_header_label[0].setVisible(True)

            return

        meta = registry.meta.get(action_id, {})
        display_name = meta.get("name", action_id)
        cat = meta.get("category", "") or None
        callback = registry.callbacks.get(action_id)

        insert_idx = _hk_stretch_index[0] if _hk_stretch_index[0] is not None else hk_scroll_layout.count()

        if not _dynamic_header_added[0]:
            _dynamic_header_added[0] = True
            hdr = QLabel(f"<b>{tl('cat_other')}</b>")
            _dynamic_header_label[0] = hdr
            hk_scroll_layout.insertWidget(insert_idx, hdr)
            insert_idx += 1

            if _hk_stretch_index[0] is not None:
                _hk_stretch_index[0] += 1

        elif _dynamic_header_label[0] is not None:
            _dynamic_header_label[0].setVisible(True)

        row_widget = QWidget()
        row_layout = _build_hk_row(
            action_id, display_name, callback, icon_svg=_toggle_icons["custom"], removable=True, category=cat
        )
        row_widget.setLayout(row_layout)
        row_widget.setContentsMargins(0, 0, 0, 0)
        hk_scroll_layout.insertWidget(insert_idx, row_widget)
        _dynamic_row_widgets[action_id] = row_widget
        registry.row_widgets[action_id] = row_widget

        if _hk_stretch_index[0] is not None:
            _hk_stretch_index[0] += 1

    _multi_client_widgets = []
    _multi_client_cat_name = tl("cat_multi_client")

    for cat_name, actions in _hk_categories:
        cat_label = QLabel(f"<b>{cat_name}</b>")
        hk_scroll_layout.addWidget(cat_label)

        if cat_name == _multi_client_cat_name:
            _multi_client_widgets.append(cat_label)

        for action_id, display_name, callback, is_toggle, tag_name, icon_svg in actions:
            registry.register(action_id, display_name, cat_name, callback)
            row = _build_hk_row(action_id, display_name, callback, is_toggle, tag_name, icon_svg)
            row_widget = QWidget()
            row_widget.setContentsMargins(0, 0, 0, 0)
            row_widget.setLayout(row)
            registry.row_widgets[action_id] = row_widget
            hk_scroll_layout.addWidget(row_widget)

            if cat_name == _multi_client_cat_name:
                _multi_client_widgets.append(row_widget)

    def _update_multi_client_state(client_count):
        enabled = client_count > 1
        for w in _multi_client_widgets:
            w.setEnabled(enabled)

            if enabled:
                w.setGraphicsEffect(None)

            else:
                effect = QGraphicsOpacityEffect(w)
                effect.setOpacity(0.35)
                w.setGraphicsEffect(effect)

    hk_scroll_layout.addStretch()
    _hk_stretch_index[0] = hk_scroll_layout.count() - 1
    hk_scroll.setWidget(hk_scroll_widget)
    hk_manager_layout.addWidget(hk_scroll)

    # Reset button
    def _reset_hotkeys():
        if settings:
            settings.reset_hotkeys()
            hotkeys = settings.get_hotkeys()

            for aid, lbl in registry.key_labels.items():
                binding = hotkeys.get(aid)

                if binding:
                    from src.gui.commands import _format_binding

                    lbl.setText(_format_binding(binding.get("key"), binding.get("modifiers")))

                else:
                    lbl.setText(tl("unbound"))

                if aid in registry.row_widgets:
                    registry.row_widgets[aid].setVisible(True)

                if aid not in hotkeys:
                    send_queue.put(GUICommand(GUICommandType.RebindHotkey, (aid, None, None)))

            for aid, binding in hotkeys.items():
                if binding:
                    send_queue.put(
                        GUICommand(GUICommandType.RebindHotkey, (aid, binding["key"], binding.get("modifiers", [])))
                    )
                else:
                    send_queue.put(GUICommand(GUICommandType.RebindHotkey, (aid, None, None)))

    hk_manager_layout.addWidget(registry.styled_btn(tl("reset_defaults"), _reset_hotkeys))
    hotkeys_layout.addWidget(hk_manager)

    # --- Right panel: Tool info ---
    info_widget = QWidget()
    info_layout = QVBoxLayout(info_widget)
    info_layout.setContentsMargins(4, 4, 4, 4)

    info_layout.addStretch()

    _logo_path = resource_path("Deimos-logo.png")
    if os.path.exists(_logo_path):
        logo_label = QLabel()
        pixmap = QPixmap(_logo_path)

        if not pixmap.isNull():
            scaled = pixmap.scaledToHeight(80, Qt.TransformationMode.SmoothTransformation)
            logo_label.setPixmap(scaled)
            logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            info_layout.addWidget(logo_label)

    _changelog_url = f"https://github.com/{ctx.tool_author}/{ctx.tool_name}-Wizard101/releases/tag/{ctx.tool_version}"
    version_label = QLabel(
        f'<b>{ctx.tool_name}</b> <a href="{_changelog_url}" style="color: {ctx.text_color}; text-decoration: none;">v{ctx.tool_version}</a>'
    )
    version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    version_label.setOpenExternalLinks(True)
    info_layout.addWidget(version_label)

    repo_links_row = QHBoxLayout()
    repo_links_row.setSpacing(4)
    repo_links_row.addStretch()
    repo_links_row.addWidget(
        repo_icon_btn(ctx, ctx.svgs["license"], tl("tooltip_license"), f"{ctx.repo_base}/blob/main/LICENSE")
    )
    repo_links_row.addWidget(
        repo_icon_btn(ctx, ctx.svgs["readme"], tl("tooltip_wiki_hotkeys"), f"{ctx.wiki_base}/Hotkeys")
    )
    repo_links_row.addWidget(repo_icon_btn(ctx, ctx.svgs["source"], tl("tooltip_source_code"), ctx.repo_base))
    repo_links_row.addWidget(
        repo_icon_btn(ctx, ctx.svgs["discord"], tl("tooltip_discord"), "https://discord.gg/59UrPJwYDm")
    )
    repo_links_row.addStretch()
    info_layout.addLayout(repo_links_row)

    info_layout.addStretch()
    hotkeys_layout.addWidget(info_widget)

    # Store static IDs and the dynamic row adder for main.py to use
    static_ids = {aid for _, actions in _hk_categories for aid, *_ in actions}

    _update_multi_client_state(0)

    def _retheme():
        # Update key binding label colors
        for lbl in registry.key_labels.values():
            lbl.setStyleSheet(f"color: {ctx.text_color}; font-style: italic;")

        # Update version link color
        _cl_url = f"https://github.com/{ctx.tool_author}/{ctx.tool_name}-Wizard101/releases/tag/{ctx.tool_version}"
        version_label.setText(
            f'<b>{ctx.tool_name}</b> <a href="{_cl_url}" style="color: {ctx.text_color}; text-decoration: none;">v{ctx.tool_version}</a>'
        )

    ctx.exports["hotkeys"] = {
        "add_dynamic_hk_row": _add_dynamic_hk_row,
        "static_ids": static_ids,
        "update_multi_client_state": _update_multi_client_state,
        "retheme": _retheme,
    }

    # Wire up the dynamic row adder to the registry
    registry.add_dynamic_hk_row = _add_dynamic_hk_row

    return tab
