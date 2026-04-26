from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QLabel, QComboBox,
    QPushButton, QScrollArea, QFrame, QGraphicsOpacityEffect,
)
from PyQt6.QtCore import Qt

from src.gui.commands import GUICommand, GUICommandType
from src.gui.helpers import centered_label, repo_icon_btn
from src.gui.widgets import AnimatedStackedWidget
from src.paths import wizard_city_dance_game_path
from src.utils import assign_pet_level


def build_dev_utils_tab(ctx):
    tab = QWidget()
    outer = QVBoxLayout(tab)
    outer.setContentsMargins(4, 2, 4, 2)
    outer.setSpacing(2)

    # --- Header (full width, above panels) ---
    dev_header = QHBoxLayout()
    dev_header.addWidget(centered_label(ctx.tl('advanced_warning')), 1)
    dev_header.addWidget(repo_icon_btn(ctx, ctx.svgs['readme'], ctx.tl('tooltip_wiki_utilities'), f"{ctx.wiki_base}/Utilities"))
    outer.addLayout(dev_header)

    tab_layout = QHBoxLayout()
    tab_layout.setSpacing(4)
    outer.addLayout(tab_layout, 1)

    dev_inputs = {}
    sc = ctx.stroke_color

    worlds = ['WizardCity', 'Krokotopia', 'Marleybone', 'MooShu', 'DragonSpire', 'Grizzleheim', 'Celestia', 'Wysteria', 'Zafaria', 'Avalon', 'Azteca', 'Khrysalis', 'Polaris', 'Mirage', 'Empyrea', 'Karamelle', 'Lemuria']
    pet_worlds = ['WizardCity', 'Krokotopia', 'Marleybone', 'Mooshu', 'Dragonspyre']

    _dev_icons = {
        'axis':   f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M13.5 10.5 15 9"/><path d="M4 4v15a1 1 0 0 0 1 1h15"/><path d="M4.293 19.707 6 18"/><path d="m9 15 1.5-1.5"/></svg>',
        'rotate': f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16.466 7.5C15.643 4.237 13.952 2 12 2 9.239 2 7 6.477 7 12s2.239 10 5 10c.342 0 .677-.069 1-.2"/><path d="m15.194 13.707 3.814 1.86-1.86 3.814"/><path d="M19 15.57c-1.804.885-4.274 1.43-7 1.43-5.523 0-10-2.239-10-5s4.477-5 10-5c4.838 0 8.873 1.718 9.8 4"/></svg>',
        'person': f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="5" r="1"/><path d="m9 20 3-6 3 6"/><path d="m6 8 6 2 6-2"/><path d="M12 10v4"/></svg>',
        'gid':    f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 10a2 2 0 0 0-2 2c0 1.02-.1 2.51-.26 4"/><path d="M14 13.12c0 2.38 0 6.38-1 8.88"/><path d="M17.29 21.02c.12-.6.43-2.3.5-3.02"/><path d="M2 12a10 10 0 0 1 18-6"/><path d="M2 16h.01"/><path d="M21.8 16c.2-2 .131-5.354 0-6"/><path d="M5 19.5C5.5 18 6 15 6 12a6 6 0 0 1 .34-2"/><path d="M8.65 22c.21-.66.45-1.32.57-2"/><path d="M9 6.8a6 6 0 0 1 9 5.2v2"/></svg>',
        'map':    f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.106 5.553a2 2 0 0 0 1.788 0l3.659-1.83A1 1 0 0 1 21 4.619v12.764a1 1 0 0 1-.553.894l-4.553 2.277a2 2 0 0 1-1.788 0l-4.212-2.106a2 2 0 0 0-1.788 0l-3.659 1.83A1 1 0 0 1 3 19.381V6.618a1 1 0 0 1 .553-.894l4.553-2.277a2 2 0 0 1 1.788 0z"/><path d="M15 5.764v15"/><path d="M9 3.236v15"/></svg>',
        'earth':  f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21.54 15H17a2 2 0 0 0-2 2v4.54"/><path d="M7 3.34V5a3 3 0 0 0 3 3a2 2 0 0 1 2 2c0 1.1.9 2 2 2a2 2 0 0 0 2-2c0-1.1.9-2 2-2h3.17"/><path d="M11 21.95V18a2 2 0 0 0-2-2a2 2 0 0 1-2-2v-1a2 2 0 0 0-2-2H2.05"/><circle cx="12" cy="12" r="10"/></svg>',
        'scale':  f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 7v11a1 1 0 0 0 1 1h11"/><path d="M5.293 18.707 11 13"/><circle cx="19" cy="19" r="2"/><circle cx="5" cy="5" r="2"/></svg>',
        'paw':    f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="4" r="2"/><circle cx="18" cy="8" r="2"/><circle cx="20" cy="16" r="2"/><path d="M9 10a5 5 0 0 1 5 5v3.5a3.5 3.5 0 0 1-6.84 1.045Q6.52 17.48 4.46 16.84A3.5 3.5 0 0 1 5.5 10Z"/></svg>',
    }

    _dev_fields = [
        (ctx.tl('tp_utils'), None, None, 'header', None),
        ('X',                    'XInput',             _dev_icons['axis'],   'line', None),
        ('Y',                    'YInput',             _dev_icons['axis'],   'line', None),
        ('Z',                    'ZInput',             _dev_icons['axis'],   'line', None),
        (ctx.tl('yaw'),          'YawInput',           _dev_icons['rotate'], 'line', None),
        (ctx.tl('entity_name'),  'EntityTPInput',      _dev_icons['person'], 'line', None),
        ('GID',                  'EntityTPGIDInput',   _dev_icons['gid'],    'line', None),
        (ctx.tl('navigation'), None, None, 'header', None),
        (ctx.tl('zone_name'),    'ZoneInput',          _dev_icons['map'],    'line', None),
        (ctx.tl('world_name'),   'WorldInput',         _dev_icons['earth'],  'combo', {'items': worlds, 'default': 'WizardCity'}),
        (ctx.tl('misc'), None, None, 'header', None),
        (ctx.tl('scale'),        'scale',              _dev_icons['scale'],  'line', None),
        (ctx.tl('select_pet_world'), 'PetWorldInput',  _dev_icons['paw'],    'combo', {'items': pet_worlds, 'default': 'WizardCity'}),
    ]

    # --- Left panel: scrollable field list ---
    left_panel = QWidget()
    left_panel.setFixedWidth(310)
    left_layout = QVBoxLayout(left_panel)
    left_layout.setContentsMargins(0, 0, 0, 0)
    left_layout.setSpacing(4)

    dev_scroll = QScrollArea()
    dev_scroll.setWidgetResizable(True)
    dev_scroll.setFrameShape(QFrame.Shape.NoFrame)
    dev_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    dev_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    dev_scroll_widget = QWidget()
    dev_scroll_layout = QVBoxLayout(dev_scroll_widget)
    dev_scroll_layout.setContentsMargins(0, 2, 0, 2)
    dev_scroll_layout.setSpacing(2)

    for label, tag, icon_svg, wtype, extra in _dev_fields:
        if wtype == 'header':
            hdr = QLabel(f"<b>{label}</b>")
            dev_scroll_layout.addWidget(hdr)
            continue

        row = QHBoxLayout()
        row.setSpacing(2)
        row.setContentsMargins(0, 0, 0, 0)

        icon_label = QLabel()
        icon_label.setFixedSize(20, 20)
        icon_label.setPixmap(ctx.titlebar_svg_icon(icon_svg, 16).pixmap(16, 16))
        ctx.tracked_svg_labels.append([icon_label, icon_svg, 16, 'pixmap'])
        row.addWidget(icon_label)

        if wtype == 'combo':
            widget = QComboBox()
            widget.addItems(extra['items'])
            widget.setCurrentText(extra['default'])
        else:
            widget = QLineEdit()
            widget.setPlaceholderText(label)

        dev_inputs[tag] = widget
        ctx.widget_tags[tag] = widget
        row.addWidget(widget, 1)

        dev_scroll_layout.addLayout(row)

    dev_scroll_layout.addStretch()
    dev_scroll.setWidget(dev_scroll_widget)
    left_layout.addWidget(dev_scroll, 1)
    tab_layout.addWidget(left_panel)

    # --- Pet world auto-apply ---
    pet_combo = dev_inputs['PetWorldInput']

    def pet_world_callback(text):
        if text != wizard_city_dance_game_path[-1]:
            assign_pet_level(text)

    pet_combo.currentTextChanged.connect(pet_world_callback)

    # --- Right panel: action buttons (centered) ---
    right_panel = QWidget()
    right_layout = QVBoxLayout(right_panel)
    right_layout.setContentsMargins(4, 4, 4, 4)

    # --- Individual / Mass toggle buttons (fixed at top) ---
    _inactive_toggle_style = (
        "QPushButton { border: 2px solid transparent; border-radius: 4px; padding: 4px; }"
        "QPushButton:hover { background: rgba(255,255,255,30); }"
    )

    toggle_row = QHBoxLayout()
    toggle_row.setSpacing(4)
    toggle_row.addStretch()

    _indiv_svg = ctx.svgs['individual']
    indiv_toggle_btn = QPushButton()
    indiv_toggle_btn.setIcon(ctx.titlebar_svg_icon(_indiv_svg, 20))
    indiv_toggle_btn.setFixedSize(32, 32)
    indiv_toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    indiv_toggle_btn.setToolTip(ctx.tl('individual'))
    ctx.tracked_svg_labels.append([indiv_toggle_btn, _indiv_svg, 20, 'icon'])
    toggle_row.addWidget(indiv_toggle_btn)

    _mass_svg = ctx.svgs['mass']
    mass_toggle_btn = QPushButton()
    mass_toggle_btn.setIcon(ctx.titlebar_svg_icon(_mass_svg, 20))
    mass_toggle_btn.setFixedSize(32, 32)
    mass_toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    mass_toggle_btn.setToolTip(ctx.tl('all_clients'))
    ctx.tracked_svg_labels.append([mass_toggle_btn, _mass_svg, 20, 'icon'])
    toggle_row.addWidget(mass_toggle_btn)

    toggle_row.addStretch()
    right_layout.addLayout(toggle_row)

    right_layout.addStretch()

    # --- Individual action callbacks ---
    def custom_tp_callback():
        gid_val = dev_inputs['EntityTPGIDInput'].text()
        name_val = dev_inputs['EntityTPInput'].text()
        tp_vals = [dev_inputs['XInput'].text(), dev_inputs['YInput'].text(), dev_inputs['ZInput'].text(), dev_inputs['YawInput'].text()]
        if gid_val:
            ctx.send_queue.put(GUICommand(GUICommandType.EntityTeleport, {'name': '', 'gid': gid_val}))
        elif name_val:
            ctx.send_queue.put(GUICommand(GUICommandType.EntityTeleport, {'name': name_val, 'gid': ''}))
        elif any(tp_vals):
            ctx.send_queue.put(GUICommand(GUICommandType.CustomTeleport, {
                'X': tp_vals[0], 'Y': tp_vals[1], 'Z': tp_vals[2], 'Yaw': tp_vals[3],
            }))

    def go_to_zone_callback():
        val = dev_inputs['ZoneInput'].text()
        if val:
            ctx.send_queue.put(GUICommand(GUICommandType.GoToZone, (False, str(val))))

    def go_to_world_callback():
        val = dev_inputs['WorldInput'].currentText()
        if val:
            ctx.send_queue.put(GUICommand(GUICommandType.GoToWorld, (False, val)))

    def go_to_bazaar_callback():
        ctx.send_queue.put(GUICommand(GUICommandType.GoToBazaar, False))

    def refill_potions_callback():
        ctx.send_queue.put(GUICommand(GUICommandType.RefillPotions, False))

    def set_scale_callback():
        ctx.send_queue.put(GUICommand(GUICommandType.SetScale, dev_inputs['scale'].text()))

    # --- Animated stack for individual / mass pages ---
    btn_stack = AnimatedStackedWidget(duration=200)

    # Page 0: Individual buttons
    indiv_page = QWidget()
    indiv_col = QVBoxLayout(indiv_page)
    indiv_col.setContentsMargins(0, 0, 0, 0)
    indiv_col.setSpacing(4)
    indiv_col.setAlignment(Qt.AlignmentFlag.AlignHCenter)
    indiv_col.addWidget(ctx.registry.styled_btn(ctx.tl('custom_tp'), custom_tp_callback))
    indiv_col.addWidget(ctx.registry.styled_btn(ctx.tl('go_to_zone'), go_to_zone_callback))
    indiv_col.addWidget(ctx.registry.styled_btn(ctx.tl('go_to_world'), go_to_world_callback))
    indiv_col.addWidget(ctx.registry.styled_btn(ctx.tl('go_to_bazaar'), go_to_bazaar_callback))
    indiv_col.addWidget(ctx.registry.styled_btn(ctx.tl('refill_potions'), refill_potions_callback))
    indiv_col.addWidget(ctx.registry.styled_btn(ctx.tl('set_scale'), set_scale_callback))
    btn_stack.addWidget(indiv_page)

    # Page 1: Mass buttons
    _mass_widgets = []

    def mass_go_to_zone_callback():
        val = dev_inputs['ZoneInput'].text()
        if val:
            ctx.send_queue.put(GUICommand(GUICommandType.GoToZone, (True, str(val))))

    def mass_go_to_world_callback():
        val = dev_inputs['WorldInput'].currentText()
        if val:
            ctx.send_queue.put(GUICommand(GUICommandType.GoToWorld, (True, val)))

    def mass_go_to_bazaar_callback():
        ctx.send_queue.put(GUICommand(GUICommandType.GoToBazaar, True))

    def mass_refill_potions_callback():
        ctx.send_queue.put(GUICommand(GUICommandType.RefillPotions, True))

    mass_page = QWidget()
    mass_col = QVBoxLayout(mass_page)
    mass_col.setContentsMargins(0, 0, 0, 0)
    mass_col.setSpacing(4)
    mass_col.setAlignment(Qt.AlignmentFlag.AlignHCenter)

    for label, cb in [
        (ctx.tl('mass_go_to_zone'), mass_go_to_zone_callback),
        (ctx.tl('mass_go_to_world'), mass_go_to_world_callback),
        (ctx.tl('mass_go_to_bazaar'), mass_go_to_bazaar_callback),
        (ctx.tl('mass_refill_potions'), mass_refill_potions_callback),
    ]:
        btn = ctx.registry.styled_btn(label, cb)
        _mass_widgets.append(btn)
        mass_col.addWidget(btn)

    btn_stack.addWidget(mass_page)
    right_layout.addWidget(btn_stack)

    # --- Toggle logic: animate between pages ---
    _mass_active = [False]

    def _update_toggle_style(mass_active):
        _mass_active[0] = mass_active
        active = f"QPushButton {{ border: 2px solid {ctx.stroke_color}; border-radius: 4px; padding: 4px; }}"
        indiv_toggle_btn.setStyleSheet(active if not mass_active else _inactive_toggle_style)
        mass_toggle_btn.setStyleSheet(active if mass_active else _inactive_toggle_style)

    def _show_individual():
        btn_stack.slide_to(0)
        _update_toggle_style(False)

    def _show_mass():
        btn_stack.slide_to(1)
        _update_toggle_style(True)

    indiv_toggle_btn.clicked.connect(_show_individual)
    mass_toggle_btn.clicked.connect(_show_mass)
    _update_toggle_style(False)

    right_layout.addStretch()
    tab_layout.addWidget(right_panel)

    # --- Mass state management ---
    def _update_mass_state(client_count):
        enabled = client_count > 1
        for w in _mass_widgets:
            w.setEnabled(enabled)
            if enabled:
                w.setGraphicsEffect(None)
            else:
                effect = QGraphicsOpacityEffect(w)
                effect.setOpacity(0.35)
                w.setGraphicsEffect(effect)

    _update_mass_state(0)

    def _retheme():
        _update_toggle_style(_mass_active[0])

    ctx.exports['dev_utils'] = {
        'update_mass_state': _update_mass_state,
        'retheme': _retheme,
    }

    return tab
