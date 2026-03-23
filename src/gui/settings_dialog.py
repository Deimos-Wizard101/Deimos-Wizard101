import os
import glob

import shutil

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QCheckBox, QDoubleSpinBox, QSpinBox, QComboBox, QLineEdit,
    QGroupBox, QScrollArea, QWidget, QFormLayout, QFileDialog,
    QColorDialog, QApplication,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor

from src.gui.commands import GUICommand, GUICommandType
from src.settings_manager import DEFAULT_SETTINGS, DEFAULT_THEME, RESTART_REQUIRED_KEYS


class _NoScrollComboBox(QComboBox):
    """QComboBox that ignores scroll wheel events to prevent accidental changes."""
    def wheelEvent(self, event):
        event.ignore()


class _NoScrollSpinBox(QSpinBox):
    def wheelEvent(self, event):
        event.ignore()


class _NoScrollDoubleSpinBox(QDoubleSpinBox):
    def wheelEvent(self, event):
        event.ignore()


def _scan_locales():
    """Scan locale/ directory for available .lang files."""
    codes = []
    locale_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'locale')
    for path in glob.glob(os.path.join(locale_dir, '*.lang')):
        codes.append(os.path.splitext(os.path.basename(path))[0])
    return sorted(codes) if codes else ['en']


_CLIENT_OPTIONS = ['None', 'p1', 'p2', 'p3', 'p4']

_THEME_KEYS = [
    ('bg_color', 'setting_bg_color'),
    ('alt_bg', 'setting_alt_bg'),
    ('text_color', 'setting_text_color'),
    ('button_color', 'setting_button_color'),
    ('stroke_color', 'setting_stroke_color'),
    ('titlebar_bg', 'setting_titlebar_bg'),
]


def _color_swatch(color_hex):
    """Create a small colored QWidget swatch."""
    swatch = QWidget()
    swatch.setFixedSize(24, 24)
    swatch.setStyleSheet(
        f"background-color: {color_hex}; border: 1px solid rgba(255,255,255,60); border-radius: 3px;"
    )
    return swatch


def show_settings_dialog(ctx):
    tl = ctx.tl
    current = ctx.settings.get_settings()
    current_theme = ctx.settings.get_theme()
    original_theme = dict(current_theme)
    theme_edits = dict(current_theme)

    dialog = QDialog(ctx.window)
    dialog.setWindowTitle(tl('settings_title'))
    dialog.setModal(True)
    dialog.setMinimumWidth(380)
    dialog.setStyleSheet(
        f"QWidget {{ background-color: {ctx.bg_color}; color: {ctx.text_color}; }}"
        f"QGroupBox {{ border: 1px solid rgba(255,255,255,40); border-radius: 4px; margin-top: 14px; padding-top: 8px; }}"
        f"QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top left; padding: 0 6px; font-weight: bold; }}"
    )

    outer_layout = QVBoxLayout(dialog)

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setStyleSheet(
        "QScrollArea { border: none; }"
        "QScrollBar:vertical { width: 6px; background: transparent; }"
        "QScrollBar::handle:vertical { background: rgba(255,255,255,40); border-radius: 3px; min-height: 20px; }"
        "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }"
    )
    outer_layout.addWidget(scroll)

    scroll_widget = QWidget()
    layout = QVBoxLayout(scroll_widget)
    layout.setSpacing(8)
    scroll.setWidget(scroll_widget)

    widgets = {}  # key -> widget

    def _add_checkbox(form, key, label_key):
        cb = QCheckBox(tl(label_key))
        cb.setChecked(bool(current.get(key, DEFAULT_SETTINGS.get(key))))
        form.addRow(cb)
        widgets[key] = cb

    def _add_client_combo(form, key, label_key):
        combo = _NoScrollComboBox()
        combo.addItems(_CLIENT_OPTIONS)
        val = current.get(key)
        combo.setCurrentText(str(val) if val else 'None')
        form.addRow(tl(label_key), combo)
        widgets[key] = combo

    # ---- General ----
    general_group = QGroupBox(tl('settings_general'))
    general_form = QFormLayout(general_group)
    general_form.setSpacing(4)

    speed_spin = _NoScrollDoubleSpinBox()
    speed_spin.setRange(0.1, 20.0)
    speed_spin.setSingleStep(0.5)
    speed_spin.setDecimals(1)
    speed_spin.setValue(float(current.get('speed_multiplier', 5.0)))
    general_form.addRow(tl('setting_speed_multiplier'), speed_spin)
    widgets['speed_multiplier'] = speed_spin

    _add_checkbox(general_form, 'use_potions', 'setting_use_potions')
    _add_checkbox(general_form, 'buy_potions', 'setting_buy_potions')
    _add_checkbox(general_form, 'rich_presence', 'setting_rich_presence')
    _add_checkbox(general_form, 'drop_logging', 'setting_drop_logging')
    _add_checkbox(general_form, 'use_anti_afk', 'setting_use_anti_afk')

    layout.addWidget(general_group)

    # ---- Theme (color swatches) ----
    theme_group = QGroupBox(tl('settings_theme'))
    theme_form = QFormLayout(theme_group)
    theme_form.setSpacing(4)

    swatches = {}

    def _update_swatch(key):
        swatches[key].setStyleSheet(
            f"background-color: {theme_edits[key]}; border: 1px solid rgba(255,255,255,60); border-radius: 3px;"
        )

    def _make_color_row(key, label_key):
        hex_val = theme_edits[key]
        swatch = _color_swatch(hex_val)
        swatches[key] = swatch
        pick_btn = QPushButton("...")
        pick_btn.setFixedSize(28, 24)
        pick_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        def _pick(k=key, lk=label_key):
            color = QColorDialog.getColor(QColor(theme_edits[k]), dialog, tl(lk))
            if color.isValid():
                theme_edits[k] = color.name()
                _update_swatch(k)

        pick_btn.clicked.connect(lambda checked, k=key, lk=label_key: _pick(k, lk))

        reset_btn = QPushButton()
        reset_btn.setIcon(ctx.titlebar_svg_icon(ctx.svgs['reset'], 14))
        reset_btn.setFixedSize(22, 22)
        reset_btn.setStyleSheet(ctx.icon_btn_style)
        reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reset_btn.setToolTip(tl('reset_to_default').format(DEFAULT_THEME[key]))

        def _reset(k=key):
            theme_edits[k] = DEFAULT_THEME[k]
            _update_swatch(k)

        reset_btn.clicked.connect(lambda checked, k=key: _reset(k))

        row = QHBoxLayout()
        row.addWidget(swatch)
        row.addWidget(pick_btn)
        row.addWidget(reset_btn)
        row.addStretch()
        theme_form.addRow(tl(label_key), row)

    for key, label_key in _THEME_KEYS:
        _make_color_row(key, label_key)

    # Import/Export row
    ie_row = QHBoxLayout()

    import_theme_btn = QPushButton(tl('settings_import_theme'))
    import_theme_btn.setStyleSheet(ctx.btn_style)
    import_theme_btn.setCursor(Qt.CursorShape.PointingHandCursor)

    def _import_theme():
        path, _ = QFileDialog.getOpenFileName(dialog, tl('settings_import_theme'), "", "JSON files (*.json)")
        if path:
            new_theme = ctx.settings.import_theme(path)
            theme_edits.update(new_theme)
            for k in swatches:
                _update_swatch(k)
            from src.gui.theme import apply_theme
            apply_theme(ctx, new_theme)

    import_theme_btn.clicked.connect(_import_theme)
    ie_row.addWidget(import_theme_btn)

    export_theme_btn = QPushButton(tl('settings_export_theme'))
    export_theme_btn.setStyleSheet(ctx.btn_style)
    export_theme_btn.setCursor(Qt.CursorShape.PointingHandCursor)

    def _export_theme():
        path, _ = QFileDialog.getSaveFileName(dialog, tl('settings_export_theme'), "", "JSON files (*.json)")
        if path:
            ctx.settings.export_theme(path)

    export_theme_btn.clicked.connect(_export_theme)
    ie_row.addWidget(export_theme_btn)
    ie_row.addStretch()

    theme_form.addRow(ie_row)

    layout.addWidget(theme_group)

    # ---- Appearance (font + locale) ----
    appearance_group = QGroupBox(tl('settings_appearance'))
    appearance_form = QFormLayout(appearance_group)
    appearance_form.setSpacing(4)

    locale_combo = _NoScrollComboBox()
    locale_combo.addItems(_scan_locales())
    locale_combo.setCurrentText(str(current.get('locale', 'en')))
    widgets['locale'] = locale_combo

    locale_row = QHBoxLayout()
    locale_row.addWidget(locale_combo, 1)
    import_lang_btn = QPushButton()
    import_lang_btn.setIcon(ctx.titlebar_svg_icon(ctx.svgs['import'], 16))
    import_lang_btn.setFixedSize(24, 24)
    import_lang_btn.setStyleSheet(ctx.icon_btn_style)
    import_lang_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    import_lang_btn.setToolTip(tl('import_lang_file'))

    def _import_lang():
        path, _ = QFileDialog.getOpenFileName(dialog, tl('import_lang_title'), "", "Language files (*.lang)")
        if path:
            locale_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'locale')
            dest = os.path.join(locale_dir, os.path.basename(path))
            if not os.path.abspath(dest).startswith(os.path.abspath(locale_dir)):
                return
            shutil.copy2(path, dest)
            code = os.path.splitext(os.path.basename(path))[0]
            codes = _scan_locales()
            locale_combo.clear()
            locale_combo.addItems(codes)
            locale_combo.setCurrentText(code)

    import_lang_btn.clicked.connect(_import_lang)
    locale_row.addWidget(import_lang_btn)
    appearance_form.addRow(tl('setting_locale') + ' *', locale_row)

    font_edit = QLineEdit(str(current.get('font', 'Segoe UI')))
    widgets['font'] = font_edit

    font_reset_btn = QPushButton()
    font_reset_btn.setIcon(ctx.titlebar_svg_icon(ctx.svgs['reset'], 14))
    font_reset_btn.setFixedSize(22, 22)
    font_reset_btn.setStyleSheet(ctx.icon_btn_style)
    font_reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    font_reset_btn.setToolTip(tl('reset_to_default').format(DEFAULT_SETTINGS['font']))
    font_reset_btn.clicked.connect(lambda checked: font_edit.setText(DEFAULT_SETTINGS['font']))

    font_row = QHBoxLayout()
    font_row.addWidget(font_edit, 1)
    font_row.addWidget(font_reset_btn)
    appearance_form.addRow(tl('setting_font'), font_row)

    font_size_spin = _NoScrollSpinBox()
    font_size_spin.setRange(6, 24)
    font_size_spin.setValue(int(current.get('font_size', 9)))
    widgets['font_size'] = font_size_spin

    font_size_reset_btn = QPushButton()
    font_size_reset_btn.setIcon(ctx.titlebar_svg_icon(ctx.svgs['reset'], 14))
    font_size_reset_btn.setFixedSize(22, 22)
    font_size_reset_btn.setStyleSheet(ctx.icon_btn_style)
    font_size_reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    font_size_reset_btn.setToolTip(tl('reset_to_default').format(DEFAULT_SETTINGS['font_size']))
    font_size_reset_btn.clicked.connect(lambda checked: font_size_spin.setValue(DEFAULT_SETTINGS['font_size']))

    font_size_row = QHBoxLayout()
    font_size_row.addWidget(font_size_spin, 1)
    font_size_row.addWidget(font_size_reset_btn)
    appearance_form.addRow(tl('setting_font_size'), font_size_row)

    layout.addWidget(appearance_group)

    # ---- Sigil ----
    sigil_group = QGroupBox(tl('settings_sigil'))
    sigil_form = QFormLayout(sigil_group)
    sigil_form.setSpacing(4)

    _add_checkbox(sigil_form, 'use_team_up', 'setting_use_team_up')
    _add_client_combo(sigil_form, 'client_to_follow', 'setting_client_to_follow')

    layout.addWidget(sigil_group)

    # ---- Questing ----
    questing_group = QGroupBox(tl('settings_questing'))
    questing_form = QFormLayout(questing_group)
    questing_form.setSpacing(4)

    _add_client_combo(questing_form, 'client_to_boost', 'setting_client_to_boost')
    _add_checkbox(questing_form, 'friend_teleport', 'setting_friend_teleport')
    _add_checkbox(questing_form, 'gear_switching_in_solo_zones', 'setting_gear_switching')
    _add_client_combo(questing_form, 'hitter_client', 'setting_hitter_client')

    layout.addWidget(questing_group)

    # ---- Auto Pet ----
    pet_group = QGroupBox(tl('settings_auto_pet'))
    pet_form = QFormLayout(pet_group)
    pet_form.setSpacing(4)

    _add_checkbox(pet_form, 'ignore_pet_level_up', 'setting_ignore_pet_level_up')
    _add_checkbox(pet_form, 'only_play_dance_game', 'setting_only_dance_game')

    layout.addWidget(pet_group)

    # ---- Combat ----
    combat_group = QGroupBox(tl('settings_combat'))
    combat_form = QFormLayout(combat_group)
    combat_form.setSpacing(4)

    _add_checkbox(combat_form, 'kill_minions_first', 'setting_kill_minions_first')
    _add_checkbox(combat_form, 'automatic_team_based_combat', 'setting_auto_team_combat')
    _add_checkbox(combat_form, 'discard_duplicate_cards', 'setting_discard_duplicates')

    layout.addWidget(combat_group)

    layout.addStretch()

    # ---- Bottom buttons ----
    restart_label = QLabel("* " + tl('settings_restart_note'))
    restart_label.setStyleSheet("color: orange; font-style: italic;")
    restart_label.setVisible(False)
    outer_layout.addWidget(restart_label)

    btn_row = QHBoxLayout()
    btn_row.addStretch()

    save_btn = QPushButton(tl('settings_save'))
    save_btn.setStyleSheet(ctx.btn_style)
    save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn_row.addWidget(save_btn)

    cancel_btn = QPushButton(tl('settings_cancel'))
    cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn_row.addWidget(cancel_btn)

    outer_layout.addLayout(btn_row)

    def _collect_values():
        values = {}
        for key, w in widgets.items():
            if isinstance(w, QCheckBox):
                values[key] = w.isChecked()
            elif isinstance(w, QDoubleSpinBox):
                values[key] = w.value()
            elif isinstance(w, QSpinBox):
                values[key] = w.value()
            elif isinstance(w, QComboBox):
                text = w.currentText()
                if key in ('client_to_follow', 'client_to_boost', 'hitter_client'):
                    values[key] = None if text == 'None' else text
                else:
                    values[key] = text
            elif isinstance(w, QLineEdit):
                values[key] = w.text()
        return values

    saved = [False]

    def _on_save():
        from src.gui.theme import apply_theme

        # Handle theme changes
        if theme_edits != original_theme:
            ctx.settings.set_theme(theme_edits)
            apply_theme(ctx, theme_edits)

        # Handle font changes
        new_font = font_edit.text()
        new_font_size = font_size_spin.value()
        old_font = current.get('font', 'Segoe UI')
        old_font_size = current.get('font_size', 9)
        if new_font != old_font or new_font_size != old_font_size:
            ctx.gui_font = new_font
            ctx.gui_font_size = new_font_size
            from src.gui.theme import compute_styles
            styles = compute_styles(theme_edits, new_font, new_font_size)
            app = QApplication.instance()
            if app:
                app.setStyleSheet(styles['app_style'])

        # Handle non-theme settings
        new_values = _collect_values()
        changed = {}
        for key, new_val in new_values.items():
            old_val = current.get(key, DEFAULT_SETTINGS.get(key))
            if new_val != old_val:
                changed[key] = new_val

        if changed:
            ctx.settings.set_settings(changed)
            ctx.send_queue.put(GUICommand(GUICommandType.UpdateSettings, changed))

        saved[0] = True

        if changed.keys() & RESTART_REQUIRED_KEYS:
            restart_label.setVisible(True)
            save_btn.setEnabled(False)
            return

        dialog.accept()

    def _on_cancel():
        if not saved[0] and theme_edits != original_theme:
            from src.gui.theme import apply_theme
            apply_theme(ctx, original_theme)
            ctx.settings.set_theme(original_theme)
        dialog.reject()

    save_btn.clicked.connect(_on_save)
    cancel_btn.clicked.connect(_on_cancel)

    dialog.exec()
