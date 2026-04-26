import re
import pyperclip

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLineEdit, QLabel,
    QComboBox, QCheckBox, QPushButton, QDialog, QScrollArea, QFrame,
    QSizePolicy, QToolTip,
)
from PyQt6.QtCore import Qt, QTimer, QPoint

from loguru import logger

from src.gui.commands import GUICommand, GUICommandType
from src.gui.helpers import centered_label, repo_icon_btn
from src.gui.widgets import DuelCircleWidget
from src.combat_objects import school_id_to_names


def _build_stat_svgs(stroke_color):
    sc = stroke_color
    return {
        'est_dmg':     f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/></svg>',
        'name':        f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>',
        'template_id': f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 3h5v5"/><path d="M8 3H3v5"/><path d="M12 22v-8.3a4 4 0 0 0-1.172-2.872L3 3"/><path d="m15 9 6-6"/></svg>',
        'template_name':f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M10 12a1 1 0 0 0-1 1v1a1 1 0 0 1-1 1 1 1 0 0 1 1 1v1a1 1 0 0 0 1 1"/><path d="M14 18a1 1 0 0 0 1-1v-1a1 1 0 0 1 1-1 1 1 0 0 1-1-1v-1a1 1 0 0 0-1-1"/></svg>',
        'power_pips':  f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 14a1 1 0 0 1-.78-1.63l9.9-10.2a.5.5 0 0 1 .86.46l-1.92 6.02A1 1 0 0 0 13 10h7a1 1 0 0 1 .78 1.63l-9.9 10.2a.5.5 0 0 1-.86-.46l1.92-6.02A1 1 0 0 0 11 14z"/></svg>',
        'pips':        f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="1"/></svg>',
        'shadow_pips': f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 2a7 7 0 1 0 10 10"/></svg>',
        'health':      f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z"/><path d="M3.22 12H9.5l.5-1 2 4.5 2-7 1.5 3.5h5.27"/></svg>',
        'boosts':      f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/></svg>',
        'resists':     f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/></svg>',
        'damages':     f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.5 17.5 3 6V3h3l11.5 11.5"/><path d="M13 19l6-6"/><path d="M16 16l4 4"/><path d="M19 21l2-2"/><path d="m14.5 6.5 1-1a2.12 2.12 0 0 1 3 3l-1 1"/><path d="m18.5 10.5 1-1a2.12 2.12 0 0 1 3 3l-1 1"/></svg>',
        'pierces':     f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="22" y1="12" x2="18" y2="12"/><line x1="6" y1="12" x2="2" y2="12"/><line x1="12" y1="6" x2="12" y2="2"/><line x1="12" y1="22" x2="12" y2="18"/></svg>',
        'crits':       f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z"/></svg>',
        'blocks':      f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m14.5 9.5-5 5"/></svg>',
        'masteries':   f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21.42 10.922a1 1 0 0 0-.019-1.838L12.83 5.18a2 2 0 0 0-1.66 0L2.6 9.08a1 1 0 0 0 0 1.832l8.57 3.908a2 2 0 0 0 1.66 0z"/><path d="M22 10v6"/><path d="M6 12.5V16a6 3 0 0 0 12 0v-3.5"/></svg>',
        'pvp':         f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>',
    }


def build_stats_tab(ctx):
    tab = QWidget()
    stats_layout = QVBoxLayout(tab)
    stats_layout.setContentsMargins(4, 4, 4, 4)
    stats_layout.setSpacing(4)

    tl = ctx.tl
    send_queue = ctx.send_queue

    # Header row
    stats_header = QHBoxLayout()
    stats_header.addWidget(centered_label(tl('advanced_warning')), 1)
    stats_header.addWidget(repo_icon_btn(ctx, ctx.svgs['readme'], tl('tooltip_wiki_stats'), f"{ctx.wiki_base}/Stats"))
    stats_layout.addLayout(stats_header)

    # Radial duel circle widget
    duel_circle = DuelCircleWidget(stroke_color=ctx.stroke_color, text_color=ctx.text_color, bg_color=ctx.bg_color, button_color=ctx.btn_color_hex, tl=tl)
    duel_circle.set_status_message(tl('not_in_combat'))
    duel_circle.set_enemy_count(0)
    duel_circle.set_ally_count(0)

    # Damage calculation config
    stats_inputs = {}

    damage_input = QLineEdit()
    damage_input.setFixedWidth(50)
    damage_input.setPlaceholderText(tl('dmg'))
    stats_inputs['DamageInput'] = damage_input
    ctx.widget_tags['DamageInput'] = damage_input

    schools = ['Caster', 'Target', 'Fire', 'Ice', 'Storm', 'Myth', 'Life', 'Death', 'Balance', 'Star', 'Sun', 'Moon', 'Shadow']
    school_combo = QComboBox()
    school_combo.addItems(schools)
    school_combo.setCurrentText('Caster')
    school_combo.setFixedWidth(80)
    stats_inputs['SchoolInput'] = school_combo
    ctx.widget_tags['SchoolInput'] = school_combo

    crit_check = QCheckBox(tl('crit'))
    crit_check.setChecked(True)
    stats_inputs['CritStatus'] = crit_check
    ctx.widget_tags['CritStatus'] = crit_check

    # Stat SVGs for popup rows
    _stat_svgs = _build_stat_svgs(ctx.stroke_color)

    # Stat popup dialog (non-modal, reusable)
    _stat_popup = [None]
    _stat_popup_rows = []
    _stat_popup_grid = [None]
    _stat_popup_scroll_widget = [None]
    _stat_popup_data = [[]]

    # Damage readout state and label
    _last_stat_response = [{}]
    _last_calc_school = ['']
    damage_readout = QLabel()
    damage_readout.setTextFormat(Qt.TextFormat.RichText)
    damage_readout.setWordWrap(True)
    damage_readout.setAlignment(Qt.AlignmentFlag.AlignCenter)
    damage_readout.setStyleSheet("font-size: 10px; padding: 2px;")
    damage_readout.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding)

    def _update_damage_readout():
        stat_dicts = _last_stat_response[0]
        if not stat_dicts:
            damage_readout.setText('')
            return
        est_dmg_str = ''
        name_str = ''
        for entry in stat_dicts:
            if entry.get('key') == 'est_dmg':
                est_dmg_str = entry.get('value', '')
            elif entry.get('key') == 'name':
                name_str = entry.get('value', '')
            elif entry.get('key') == 'pvp':
                damage_readout.setText('')
                return
        if not est_dmg_str or not name_str:
            damage_readout.setText('')
            return
        parts = est_dmg_str.split(' vs ', 1)
        if len(parts) != 2:
            damage_readout.setText('')
            return
        dmg_value = parts[0].strip()
        target_name = parts[1].strip()
        name_parts = name_str.split(' - ')
        caster_name = name_parts[0].strip() if name_parts else '???'
        school_name = _last_calc_school[0] or ''
        base_text = re.sub(r'[^0-9]', '', str(damage_input.text()))
        if base_text:
            dmg_phrase = f'a {base_text} damage'
        else:
            dmg_phrase = 'an estimated'
        crit_str = ' critical' if crit_check.isChecked() else ''
        damage_readout.setText(
            f'<b>{caster_name}</b> would deal <b><u>{dmg_value}</u></b> {school_name} damage against {target_name}, assuming {dmg_phrase}{crit_str} hit.'
        )

    def _update_stat_popup_rows(stat_dicts):
        _stat_popup_data[0] = stat_dicts
        grid = _stat_popup_grid[0]
        container = _stat_popup_scroll_widget[0]
        if grid is None or container is None:
            return

        while grid.count():
            item = grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        _stat_popup_rows.clear()

        for row_i, entry in enumerate(stat_dicts):
            key = entry.get('key', '')
            label = entry.get('label', '')
            value = entry.get('value', '')

            svg_str = _stat_svgs.get(key, '')
            if svg_str:
                icon_pixmap = ctx.titlebar_svg_icon(svg_str, 16).pixmap(16, 16)
                icon_label = QLabel()
                icon_label.setPixmap(icon_pixmap)
                icon_label.setFixedSize(20, 20)
                icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            else:
                icon_label = QLabel()
                icon_label.setFixedSize(20, 20)
            grid.addWidget(icon_label, row_i, 0)

            lbl = QLabel(f'<b>{label}</b>')
            lbl.setFixedWidth(100)
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            grid.addWidget(lbl, row_i, 1)

            val_label = QLabel(value)
            val_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            val_label.setCursor(Qt.CursorShape.PointingHandCursor)
            val_label.setWordWrap(True)
            val_label.setStyleSheet("padding: 2px 4px;")
            captured_value = value
            val_label.mousePressEvent = lambda _ev, v=captured_value, vl=val_label: _copy_stat_value(v, vl)
            grid.addWidget(val_label, row_i, 2)

            _stat_popup_rows.append((icon_label, lbl, val_label))

    def _copy_stat_value(value, label_widget):
        pyperclip.copy(value)
        QToolTip.showText(label_widget.mapToGlobal(QPoint(0, 0)), ctx.tl('copied'), label_widget, msecShowTime=1000)

    def _copy_all_stats():
        lines = [f"{e['label']}: {e['value']}" for e in _stat_popup_data[0]]
        pyperclip.copy('\n'.join(lines))

    def _get_or_create_stat_popup():
        if _stat_popup[0] is not None and _stat_popup[0].isVisible():
            return _stat_popup[0]

        dialog = QDialog(ctx.window)
        dialog.setWindowTitle(ctx.tl('combat_stats'))
        dialog.setWindowFlags(dialog.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        dialog.resize(450, 350)
        dlg_layout = QVBoxLayout(dialog)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll_widget = QWidget()
        grid = QGridLayout(scroll_widget)
        grid.setContentsMargins(6, 6, 6, 6)
        grid.setSpacing(4)
        grid.setColumnStretch(2, 1)
        scroll.setWidget(scroll_widget)
        dlg_layout.addWidget(scroll)

        _stat_popup_grid[0] = grid
        _stat_popup_scroll_widget[0] = scroll_widget

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        copy_stat_btn = QPushButton()
        copy_stat_btn.setIcon(ctx.titlebar_svg_icon(ctx.svgs['clipboard'], 16))
        copy_stat_btn.setFixedSize(28, 28)
        copy_stat_btn.setStyleSheet(ctx.icon_btn_style)
        copy_stat_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        copy_stat_btn.setToolTip(tl('copy_stats'))
        copy_stat_btn.clicked.connect(_copy_all_stats)
        btn_row.addWidget(copy_stat_btn)

        close_btn = ctx.registry.styled_btn(ctx.tl('close'), dialog.close)
        btn_row.addWidget(close_btn)
        btn_row.addStretch()
        dlg_layout.addLayout(btn_row)

        _stat_popup[0] = dialog
        return dialog

    # Stat request logic
    _swapped = [False]
    _pending_view_side = [None]

    def _send_stat_request(view_side=None):
        _pending_view_side[0] = view_side
        try:
            base_damage = re.sub(r'[^0-9]', '', str(damage_input.text()))
            school_text = school_combo.currentText()
            if school_text == 'Caster':
                school_id = None
                force_school = False
            elif school_text == 'Target':
                school_id = 'target'
                force_school = True
            else:
                school_id = school_id_to_names[school_text]
                force_school = True
            if not _swapped[0]:
                ally_idx = duel_circle.selected_caster()
                enemy_idx = duel_circle.selected_target()
            else:
                enemy_idx = duel_circle.selected_caster()
                ally_idx = duel_circle.selected_target()
            send_queue.put(GUICommand(GUICommandType.SelectEnemy, (
                ally_idx, enemy_idx,
                base_damage, school_id,
                crit_check.isChecked(),
                force_school,
                _swapped[0],
                view_side
            )))
        except Exception:
            logger.error("Failed to send stat request", exc_info=True)

    def _is_selection_valid():
        if not _swapped[0]:
            return (duel_circle.selected_caster() <= duel_circle._ally_count and
                    duel_circle.selected_target() <= duel_circle._enemy_count and
                    duel_circle._ally_count > 0 and duel_circle._enemy_count > 0)
        else:
            return (duel_circle.selected_caster() <= duel_circle._enemy_count and
                    duel_circle.selected_target() <= duel_circle._ally_count and
                    duel_circle._ally_count > 0 and duel_circle._enemy_count > 0)

    def _view_side_stats(side):
        if not _is_selection_valid():
            return
        _send_stat_request(view_side=side)
        popup = _get_or_create_stat_popup()
        popup.show()
        popup.raise_()

    def _on_slot_changed(_idx):
        if _is_selection_valid():
            _send_stat_request()

    duel_circle.casterSelected.connect(_on_slot_changed)
    duel_circle.targetSelected.connect(_on_slot_changed)
    duel_circle.viewEnemy.connect(lambda: _view_side_stats('enemy'))
    duel_circle.viewAlly.connect(lambda: _view_side_stats('ally'))

    def _swap_sides_callback():
        _swapped[0] = not _swapped[0]
        duel_circle.swap_sides()
        if _is_selection_valid():
            _send_stat_request()

    duel_circle.swapClicked.connect(_swap_sides_callback)

    # Content row — duel circle | calc settings
    stats_content = QHBoxLayout()

    calc_widget = QWidget()
    calc_widget.setFixedSize(130, 224)
    calc_col = QVBoxLayout(calc_widget)
    calc_col.setContentsMargins(0, 0, 0, 0)
    calc_col.setSpacing(4)
    calc_col.addStretch()
    damage_input.setPlaceholderText(tl('base_dmg'))
    damage_input.setFixedWidth(70)
    calc_col.addWidget(damage_input, alignment=Qt.AlignmentFlag.AlignHCenter)
    school_combo.setFixedWidth(70)
    calc_col.addWidget(school_combo, alignment=Qt.AlignmentFlag.AlignHCenter)
    calc_col.addWidget(crit_check, alignment=Qt.AlignmentFlag.AlignHCenter)
    calc_col.addWidget(damage_readout)
    calc_col.addStretch()

    stats_content.addStretch(1)
    stats_content.addWidget(duel_circle)
    stats_content.addStretch(1)
    stats_content.addWidget(calc_widget)
    stats_content.addStretch(1)
    stats_layout.addLayout(stats_content)

    # Auto-refresh: poll combat state every 3 seconds when stats tab is active
    stats_timer = QTimer(tab)
    stats_timer.setInterval(3000)
    def _auto_refresh_stats():
        if ctx.tabs.currentWidget() == tab:
            _send_stat_request()
    stats_timer.timeout.connect(_auto_refresh_stats)
    stats_timer.start()

    # Update readout when crit/damage inputs change
    crit_check.stateChanged.connect(lambda: _update_damage_readout())
    damage_input.textChanged.connect(lambda: _update_damage_readout())

    stats_layout.addStretch()

    # Export state for event loop
    ctx.exports['stats'] = {
        'duel_circle': duel_circle,
        'swapped': _swapped,
        'last_stat_response': _last_stat_response,
        'update_damage_readout': _update_damage_readout,
        'pending_view_side': _pending_view_side,
        'update_stat_popup_rows': _update_stat_popup_rows,
        'last_calc_school': _last_calc_school,
    }

    return tab
