"""Flythrough, Bot, and Combat tabs — all share the editor+import/export/execute/kill pattern."""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QFileDialog, QPushButton
from PyQt6.QtCore import Qt

from src.gui.commands import GUICommand, GUICommandType
from src.gui.helpers import centered_label, repo_icon_btn, add_recent, show_recent_menu


def _make_toggle_btn(ctx, play_tooltip, kill_tooltip, execute_cb, kill_cb, action_id):
    """Create a single play/kill toggle button."""
    _running = [False]

    btn = QPushButton()
    btn.setIcon(ctx.titlebar_svg_icon(ctx.svgs['play'], 32))
    btn.setFixedSize(40, 40)
    btn.setStyleSheet(ctx.icon_btn_style)
    btn.setToolTip(play_tooltip)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)

    def _toggle():
        if _running[0]:
            kill_cb()
        else:
            execute_cb()

    btn.clicked.connect(_toggle)
    ctx.registry.register(action_id, play_tooltip, '', _toggle)
    ctx.registry.make_bindable(btn, action_id)

    def set_running(running):
        _running[0] = running
        svg = ctx.svgs['kill'] if running else ctx.svgs['play']
        btn.setIcon(ctx.titlebar_svg_icon(svg, 32))
        btn.setToolTip(kill_tooltip if running else play_tooltip)

    ctx.tracked_toggle_btns.append((btn, _running, 32))

    return btn, set_running


def build_flythrough_tab(ctx):
    tab = QWidget()
    layout = QVBoxLayout(tab)
    layout.setContentsMargins(4, 4, 4, 4)
    header = QHBoxLayout()
    header.addWidget(centered_label(ctx.tl('advanced_warning')), 1)
    header.addWidget(repo_icon_btn(ctx, ctx.svgs['readme'], ctx.tl('tooltip_wiki_flythroughs'), f"{ctx.wiki_base}/Flythroughs"))
    layout.addLayout(header)

    editor = QTextEdit()
    ctx.widget_tags['flythrough_creator'] = editor
    layout.addWidget(editor, 1)

    btn_row = QHBoxLayout()

    def flythrough_import():
        filepath, _ = QFileDialog.getOpenFileName(ctx.window, ctx.tl('import_flythrough'), "", "Text Files (*.txt)")
        if filepath:
            try:
                with open(filepath) as f:
                    editor.setPlainText(f.read())
                add_recent('flythrough', filepath)
            except Exception:
                pass

    def flythrough_export():
        filepath, _ = QFileDialog.getSaveFileName(ctx.window, ctx.tl('export_flythrough'), "flythrough.txt", "Text Files (*.txt)")
        if filepath:
            try:
                with open(filepath, 'w') as f:
                    f.write(editor.toPlainText())
            except Exception:
                pass

    def execute_flythrough_callback():
        ctx.send_queue.put(GUICommand(GUICommandType.ExecuteFlythrough, editor.toPlainText()))

    def kill_flythrough_callback():
        ctx.send_queue.put(GUICommand(GUICommandType.KillFlythrough))

    toggle_btn, set_flythrough_running = _make_toggle_btn(
        ctx, ctx.tl('execute_flythrough'), ctx.tl('kill_flythrough'),
        execute_flythrough_callback, kill_flythrough_callback, 'toggle_flythrough')

    recent_btn = ctx.registry.action_icon_btn(ctx.svgs['recent'], ctx.tl('recent_imports'), lambda: None)
    recent_btn.clicked.disconnect()
    recent_btn.clicked.connect(lambda: show_recent_menu(ctx, 'flythrough', editor, recent_btn))
    btn_row.addStretch()
    btn_row.addWidget(recent_btn)
    btn_row.addWidget(ctx.registry.action_icon_btn(ctx.svgs['import'], ctx.tl('import_flythrough'), flythrough_import))
    btn_row.addWidget(ctx.registry.action_icon_btn(ctx.svgs['export'], ctx.tl('export_flythrough'), flythrough_export))
    btn_row.addWidget(toggle_btn)
    btn_row.addStretch()
    layout.addLayout(btn_row)

    ctx.exports['flythrough'] = {'set_running': set_flythrough_running}
    return tab


def build_bot_tab(ctx):
    tab = QWidget()
    layout = QVBoxLayout(tab)
    layout.setContentsMargins(4, 4, 4, 4)
    header = QHBoxLayout()
    header.addWidget(centered_label(ctx.tl('advanced_warning')), 1)
    header.addWidget(repo_icon_btn(ctx, ctx.svgs['readme'], ctx.tl('tooltip_wiki_bots'), f"{ctx.wiki_base}/Bots"))
    layout.addLayout(header)

    editor = QTextEdit()
    ctx.widget_tags['bot_creator'] = editor
    layout.addWidget(editor, 1)

    btn_row = QHBoxLayout()

    def bot_import():
        filepath, _ = QFileDialog.getOpenFileName(ctx.window, ctx.tl('import_bot'), "", "Text Files (*.txt)")
        if filepath:
            try:
                with open(filepath) as f:
                    editor.setPlainText(f.read())
                add_recent('bot', filepath)
            except Exception:
                pass

    def bot_export():
        filepath, _ = QFileDialog.getSaveFileName(ctx.window, ctx.tl('export_bot'), "bot.txt", "Text Files (*.txt)")
        if filepath:
            try:
                with open(filepath, 'w') as f:
                    f.write(editor.toPlainText())
            except Exception:
                pass

    def run_bot_callback():
        ctx.send_queue.put(GUICommand(GUICommandType.ExecuteBot, editor.toPlainText()))

    def kill_bot_callback():
        ctx.send_queue.put(GUICommand(GUICommandType.KillBot))

    toggle_btn, set_bot_running = _make_toggle_btn(
        ctx, ctx.tl('run_bot'), ctx.tl('kill_bot'),
        run_bot_callback, kill_bot_callback, 'toggle_bot')

    recent_btn = ctx.registry.action_icon_btn(ctx.svgs['recent'], ctx.tl('recent_imports'), lambda: None)
    recent_btn.clicked.disconnect()
    recent_btn.clicked.connect(lambda: show_recent_menu(ctx, 'bot', editor, recent_btn))
    btn_row.addStretch()
    btn_row.addWidget(recent_btn)
    btn_row.addWidget(ctx.registry.action_icon_btn(ctx.svgs['import'], ctx.tl('import_bot'), bot_import))
    btn_row.addWidget(ctx.registry.action_icon_btn(ctx.svgs['export'], ctx.tl('export_bot'), bot_export))
    btn_row.addWidget(toggle_btn)
    btn_row.addStretch()
    layout.addLayout(btn_row)

    ctx.exports['bot'] = {'set_running': set_bot_running}
    return tab


def build_combat_tab(ctx):
    tab = QWidget()
    layout = QVBoxLayout(tab)
    layout.setContentsMargins(4, 4, 4, 4)
    header = QHBoxLayout()
    header.addWidget(centered_label(ctx.tl('advanced_warning')), 1)
    header.addWidget(repo_icon_btn(ctx, ctx.svgs['readme'], ctx.tl('tooltip_wiki_playstyles'), f"{ctx.wiki_base}/Playstyles"))
    layout.addLayout(header)

    editor = QTextEdit()
    ctx.widget_tags['combat_config'] = editor
    layout.addWidget(editor, 1)

    btn_row = QHBoxLayout()

    def combat_import():
        filepath, _ = QFileDialog.getOpenFileName(ctx.window, ctx.tl('import_playstyle'), "", "Text Files (*.txt)")
        if filepath:
            try:
                with open(filepath) as f:
                    editor.setPlainText(f.read())
                add_recent('combat', filepath)
            except Exception:
                pass

    def combat_export():
        filepath, _ = QFileDialog.getSaveFileName(ctx.window, ctx.tl('export_playstyle'), "playstyle.txt", "Text Files (*.txt)")
        if filepath:
            try:
                with open(filepath, 'w') as f:
                    f.write(editor.toPlainText())
            except Exception:
                pass

    def set_playstyles_callback():
        ctx.send_queue.put(GUICommand(GUICommandType.SetPlaystyles, editor.toPlainText()))

    recent_btn = ctx.registry.action_icon_btn(ctx.svgs['recent'], ctx.tl('recent_imports'), lambda: None)
    recent_btn.clicked.disconnect()
    recent_btn.clicked.connect(lambda: show_recent_menu(ctx, 'combat', editor, recent_btn))
    btn_row.addStretch()
    btn_row.addWidget(recent_btn)
    btn_row.addWidget(ctx.registry.action_icon_btn(ctx.svgs['import'], ctx.tl('import_playstyle'), combat_import))
    btn_row.addWidget(ctx.registry.action_icon_btn(ctx.svgs['export'], ctx.tl('export_playstyle'), combat_export))
    btn_row.addWidget(ctx.registry.action_icon_btn(ctx.svgs['refresh'], ctx.tl('set_playstyles'), set_playstyles_callback))
    btn_row.addStretch()
    layout.addLayout(btn_row)
    return tab
