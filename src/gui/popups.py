import html
import re
import webbrowser

import pyperclip

from PyQt6.QtWidgets import (
    QFrame,
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QListWidget, QListWidgetItem, QWidget, QMenu, QProgressBar,
    QComboBox, QPlainTextEdit, QTextEdit, QFormLayout,
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QFont, QTextFormat, QTextCursor, QKeySequence, QShortcut, QColor, QPainter

from src import bot_registry
from src.gui.commands import GUICommand, GUICommandType
from src.gui.helpers import launcher_small_icon_btn, spinning_loader_widget, show_recent_menu


def show_update_dialog(parent, send_queue, version, notes_url, tool_name='Deimos', tl=None):
    """Non-modal 'update available' prompt.

    Returns the dialog, which exposes ``set_progress``/``set_status``/``set_error``
    so the backend's progress messages can drive it. On accept it sends
    ``ApplyUpdate`` and switches into a download-progress view.
    """
    _ = tl or (lambda k: k)

    dialog = QDialog(parent)
    dialog.setWindowTitle(f"{tool_name} Update")
    layout = QVBoxLayout(dialog)

    headline = QLabel(f"<b>{tool_name} v{version}</b> is available.")
    headline.setTextFormat(Qt.TextFormat.RichText)
    layout.addWidget(headline)

    if notes_url:
        link = QLabel(f'<a href="{notes_url}">View changelog</a>')
        link.setTextFormat(Qt.TextFormat.RichText)
        link.setOpenExternalLinks(True)
        layout.addWidget(link)

    status_label = QLabel("")
    status_label.setWordWrap(True)
    status_label.hide()
    layout.addWidget(status_label)

    progress = QProgressBar()
    progress.setRange(0, 100)
    progress.hide()
    layout.addWidget(progress)

    btn_row = QHBoxLayout()
    later_btn = QPushButton("Later")
    update_btn = QPushButton("Update now")
    update_btn.setDefault(True)
    btn_row.addWidget(later_btn)
    btn_row.addWidget(update_btn)
    layout.addLayout(btn_row)

    def on_update():
        update_btn.setEnabled(False)
        later_btn.setEnabled(False)
        status_label.setText("Downloading update...")
        status_label.show()
        progress.setValue(0)
        progress.show()
        dialog.adjustSize()
        send_queue.put(GUICommand(GUICommandType.ApplyUpdate))

    update_btn.clicked.connect(on_update)
    later_btn.clicked.connect(dialog.close)

    def set_progress(pct):
        progress.show()
        progress.setValue(int(pct))

    def set_status(msg):
        status_label.setText(str(msg))
        status_label.show()

    def set_error(msg):
        progress.hide()
        status_label.setText(str(msg))
        status_label.show()
        update_btn.setEnabled(True)
        later_btn.setEnabled(True)
        update_btn.setText("Retry")

    dialog.set_progress = set_progress
    dialog.set_status = set_status
    dialog.set_error = set_error

    dialog.adjustSize()
    for btn in dialog.findChildren(QPushButton):
        btn.setAutoDefault(False)
        btn.setDefault(False)

    dialog.show()
    if big_editor.viewport().width() > 0:
        big_editor.document().setTextWidth(big_editor.viewport().width())
    big_editor.update_line_number_area_width(0)
    return dialog


def show_bot_search_popup(ctx, bot_tab):
    """Popup listing registry bots compatible with the current zone and client count.

    Opens in a 'searching' state; the backend's ``BotSearchResults`` message drives
    it via the exposed ``set_results``. Each row can load the bot into the Bot tab
    editor or import and run it through the existing bot machinery.
    """
    tl = ctx.tl
    dialog = QDialog(ctx.window)
    dialog.setWindowTitle(tl('bot_search_title'))
    dialog.resize(520, 400)
    layout = QVBoxLayout(dialog)

    status_row = QHBoxLayout()
    loader = spinning_loader_widget(ctx)
    status_row.addWidget(loader)
    status_label = QLabel(tl('bot_search_searching'))
    status_label.setWordWrap(True)
    status_row.addWidget(status_label, 1)
    layout.addLayout(status_row)

    listbox = QListWidget()
    listbox.hide()
    layout.addWidget(listbox, 1)

    def _import_bot(path, run):
        ctx.send_queue.put(GUICommand(GUICommandType.ImportSearchedBot, (path, run)))
        ctx.tabs.setCurrentWidget(bot_tab)
        dialog.close()

    def _add_bot_row(bot, index):
        item = QListWidgetItem()
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(4, 2, 4, 2)
        row_layout.setSpacing(4)

        text_col = QVBoxLayout()
        text_col.setSpacing(0)
        meta_parts = [f"<b>{html.escape(str(bot.get('name', '?')))}</b>"]
        if bot.get('author'):
            meta_parts.append(html.escape(str(bot['author'])))
        if bot.get('format'):
            meta_parts.append(html.escape(str(bot['format'])))
        if bot.get('clients'):
            meta_parts.append(html.escape(f"@clients {bot['clients']}"))
        if bot.get('is_general'):
            meta_parts.append(tl('bot_search_general'))
        title_label = QLabel(' &nbsp;·&nbsp; '.join(meta_parts))
        title_label.setTextFormat(Qt.TextFormat.RichText)
        text_col.addWidget(title_label)

        description = str(bot.get('description') or '').strip()
        if description:
            short = description if len(description) <= 150 else description[:150] + '…'
            desc_label = QLabel(short)
            desc_label.setWordWrap(True)
            desc_label.setToolTip(description)
            text_col.addWidget(desc_label)
        row_layout.addLayout(text_col, 1)

        path = bot.get('path')
        row_layout.addWidget(launcher_small_icon_btn(
            ctx, ctx.svgs['import'], tl('bot_search_import'), lambda _=False, p=path: _import_bot(p, False)))
        row_layout.addWidget(launcher_small_icon_btn(
            ctx, ctx.svgs['play'], tl('bot_search_run'), lambda _=False, p=path: _import_bot(p, True)))

        item.setSizeHint(row_widget.sizeHint())
        listbox.addItem(item)
        listbox.setItemWidget(item, row_widget)

    def set_results(data):
        loader.hide()
        error = data.get('error')
        if error:
            error_keys = {'no_clients': 'bot_search_no_clients', 'no_zone': 'bot_search_no_zone'}
            status_label.setText(tl(error_keys.get(error, 'bot_search_error')))
            return
        zone = data.get('zone', '')
        count = data.get('client_count', 0)
        bots = data.get('bots') or []
        if not bots:
            status_label.setText(tl('bot_search_no_results').format(zone, count))
            return
        status_label.setText(tl('bot_search_results_header').format(zone, count))
        listbox.setUpdatesEnabled(False)
        listbox.clear()
        for index, bot in enumerate(bots):
            _add_bot_row(bot, index)
        listbox.setUpdatesEnabled(True)
        listbox.show()

    dialog.set_results = set_results

    close_btn = QPushButton(tl('close'))
    close_btn.clicked.connect(dialog.close)
    layout.addWidget(close_btn)

    for btn in dialog.findChildren(QPushButton):
        btn.setAutoDefault(False)
        btn.setDefault(False)

    dialog.show()
    if big_editor.viewport().width() > 0:
        big_editor.document().setTextWidth(big_editor.viewport().width())
    big_editor.update_line_number_area_width(0)
    return dialog


def show_bot_publish_popup(ctx, bot_text):
    """Dialog to fill in/verify a bot's metadata, then publish it to the registry repo.

    Prefills from any metadata header already in the bot text, the inferred format,
    and the last-used author. The current zone and the logged-in Discord username
    arrive asynchronously from the backend via ``set_context``, each filling its
    field only if still empty (header/remembered values take precedence).
    Publishing opens GitHub's 'new file' flow so the user can propose it as a PR.
    """
    tl = ctx.tl
    metadata, body = bot_registry.split_bot_metadata(bot_text)
    metadata.setdefault('format', bot_registry.infer_bot_format(bot_text))
    if not (metadata.get('author') or '').strip() and ctx.settings:
        metadata['author'] = ctx.settings.get_setting('bot_publish_author') or ''

    dialog = QDialog(ctx.window)
    dialog.setWindowTitle(tl('bot_publish_title'))
    dialog.resize(460, 0)
    layout = QVBoxLayout(dialog)

    intro = QLabel(tl('bot_publish_intro'))
    intro.setWordWrap(True)
    layout.addWidget(intro)

    form = QFormLayout()
    name_input = QLineEdit((metadata.get('name') or '').strip())
    name_input.setPlaceholderText(tl('bot_publish_name_hint'))

    zone_row_widget = QWidget()
    zone_row_layout = QHBoxLayout(zone_row_widget)
    zone_row_layout.setContentsMargins(0, 0, 0, 0)
    zone_row_layout.setSpacing(6)
    zone_input = QLineEdit((metadata.get('zone') or '').strip())
    zone_input.setPlaceholderText(tl('bot_publish_zone_hint'))
    zone_row_layout.addWidget(zone_input, stretch=1)
    if 'readme' in getattr(ctx, 'svgs', {}):
        _readme_svg = ctx.svgs['readme']
        zone_info_btn = QPushButton()
        zone_info_btn.setIcon(ctx.titlebar_svg_icon(_readme_svg, 14))
        zone_info_btn.setFixedSize(20, 20)
        zone_info_btn.setStyleSheet(ctx.icon_btn_style)
        zone_info_btn.setToolTip(tl('bot_publish_zone_tip'))
        zone_info_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if hasattr(ctx, 'tracked_icon_buttons'):
            ctx.tracked_icon_buttons.append((zone_info_btn, _readme_svg, 14))
        zone_row_layout.addWidget(zone_info_btn, alignment=Qt.AlignmentFlag.AlignVCenter)

    author_input = QLineEdit((metadata.get('author') or '').strip())
    format_input = QComboBox()
    format_input.addItems(['bot', 'expertmode'])
    fmt = (metadata.get('format') or 'bot').strip()
    if format_input.findText(fmt) >= 0:
        format_input.setCurrentText(fmt)
    clients_input = QLineEdit((metadata.get('clients') or '').strip())
    clients_input.setPlaceholderText(tl('bot_publish_clients_hint'))
    description_input = QPlainTextEdit((metadata.get('description') or '').strip())
    description_input.setPlaceholderText(tl('bot_publish_description_hint'))
    description_input.setFixedHeight(72)

    form.addRow(tl('bot_publish_name') + ' *', name_input)
    form.addRow(tl('bot_publish_zone') + ' *', zone_row_widget)
    form.addRow(tl('bot_publish_author') + ' *', author_input)
    form.addRow(tl('bot_publish_format'), format_input)
    form.addRow(tl('bot_publish_clients'), clients_input)
    form.addRow(tl('bot_publish_description'), description_input)
    layout.addLayout(form)

    message_label = QLabel('')
    message_label.setWordWrap(True)
    message_label.hide()
    layout.addWidget(message_label)

    btn_row = QHBoxLayout()
    btn_row.addStretch()
    cancel_btn = QPushButton(tl('cancel'))
    cancel_btn.clicked.connect(dialog.close)
    publish_btn = QPushButton(tl('bot_publish_action'))
    publish_btn.setStyleSheet(ctx.btn_style)
    btn_row.addWidget(cancel_btn)
    btn_row.addWidget(publish_btn)
    layout.addLayout(btn_row)

    def _show_message(text, error=False):
        color = '#e06c75' if error else ctx.text_color
        message_label.setStyleSheet(f"color: {color};")
        message_label.setText(text)
        message_label.show()
        dialog.adjustSize()

    def _validate():
        has_zones = any(z.strip() for z in zone_input.text().split(','))
        required = bool(name_input.text().strip() and has_zones and author_input.text().strip())
        clients_ok = bot_registry.is_valid_clients_constraint(clients_input.text())
        publish_btn.setEnabled(required and clients_ok)
        if not clients_ok:
            _show_message(tl('bot_publish_bad_clients'), error=True)
        elif message_label.isVisible():
            message_label.hide()

    for w in (name_input, zone_input, author_input, clients_input):
        w.textChanged.connect(_validate)
    _validate()

    def set_context(data):
        # Only fill values we couldn't already derive from the bot's own header or
        # the remembered author — these arrive async and must not clobber user input.
        data = data or {}
        zone = data.get('zone') or ''
        if zone and not zone_input.text().strip():
            zone_input.setText(zone)
        author = data.get('discord_username') or ''
        if author and not author_input.text().strip():
            author_input.setText(author)

    dialog.set_context = set_context

    def _on_publish():
        clean_zones = [z.strip() for z in zone_input.text().split(',') if z.strip()]
        meta = {
            'name': name_input.text().strip(),
            'zone': ', '.join(clean_zones),
            'author': author_input.text().strip(),
            'format': format_input.currentText(),
            'clients': clients_input.text().strip(),
            'description': description_input.toPlainText().strip(),
        }
        if ctx.settings:
            ctx.settings.set_setting('bot_publish_author', meta['author'])
        content = bot_registry.build_bot_text(meta, body)
        url = bot_registry.build_publish_url(meta['zone'], meta['name'], content)
        if len(url) <= bot_registry.publish_url_max_length:
            webbrowser.open(url)
            _show_message(tl('bot_publish_opened'))
        else:
            # Too large to prefill via URL — copy the text and open the blank editor.
            pyperclip.copy(content)
            webbrowser.open(bot_registry.build_publish_fallback_url(meta['zone'], meta['name']))
            _show_message(tl('bot_publish_opened_clipboard'))
        publish_btn.setEnabled(False)
        publish_btn.setText(tl('bot_publish_done'))

    publish_btn.clicked.connect(_on_publish)

    for btn in dialog.findChildren(QPushButton):
        btn.setAutoDefault(False)
        btn.setDefault(False)

    dialog.show()
    if big_editor.viewport().width() > 0:
        big_editor.document().setTextWidth(big_editor.viewport().width())
    big_editor.update_line_number_area_width(0)
    return dialog


def show_ui_tree_popup(parent, send_queue, ui_tree_content, text_dict, copy_btn_factory, tl=None):
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
    dialog.setWindowTitle(tl('ui_tree') if tl else "UI Tree")
    dialog.resize(700, 500)
    layout = QVBoxLayout(dialog)

    layout.addWidget(QLabel(tl('ui_tree_hint') if tl else "Click the path needed to copy it to clipboard."))

    search_input = QLineEdit()
    search_input.setPlaceholderText(tl('search') if tl else "Search")
    layout.addWidget(search_input)

    listbox = QListWidget()
    listbox.setMouseTracking(True)
    layout.addWidget(listbox)

    line_items = []

    listbox.setUpdatesEnabled(False)
    for line in ui_tree_list:
        item = QListWidgetItem()
        path = path_dict.get(line)
        item.setData(Qt.ItemDataRole.UserRole, {'path': path, 'text': text_dict.get(line)})

        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(4, 0, 4, 0)

        label = QLabel(line)
        row_layout.addWidget(label, stretch=1)

        if line in text_dict:
            text_to_copy = text_dict[line]
            btn = copy_btn_factory(lambda _=False, t=text_to_copy: pyperclip.copy(t))
            _prefix = tl('copy_text').format(text_to_copy[:50] + ('...' if len(text_to_copy) > 50 else '')) if tl else f"Copy text: {text_to_copy[:50]}{'...' if len(text_to_copy) > 50 else ''}"
            btn.setToolTip(_prefix)
            row_layout.addWidget(btn)

        item.setSizeHint(row_widget.sizeHint())
        listbox.addItem(item)
        listbox.setItemWidget(item, row_widget)
        line_items.append((line.lower(), item))
    listbox.setUpdatesEnabled(True)

    def on_search(text):
        needle = text.lower()
        listbox.setUpdatesEnabled(False)
        for lowered, item in line_items:
            item.setHidden(bool(needle) and needle not in lowered)
        listbox.setUpdatesEnabled(True)

    def on_hover(item):
        if item:
            data = item.data(Qt.ItemDataRole.UserRole)
            if data and data.get('path'):
                send_queue.put(GUICommand(GUICommandType.HighlightUIWindow, data['path']))

    def _clear_highlight():
        send_queue.put(GUICommand(GUICommandType.ClearHighlight))

    def on_select(item):
        if item:
            data = item.data(Qt.ItemDataRole.UserRole)
            if data and data.get('path'):
                pyperclip.copy(str(data['path']))
            else:
                widget = listbox.itemWidget(item)
                if widget:
                    label = widget.findChild(QLabel)
                    if label:
                        pyperclip.copy(label.text())
            _clear_highlight()
            dialog.close()

    search_input.textChanged.connect(on_search)
    listbox.itemEntered.connect(on_hover)
    listbox.itemClicked.connect(on_select)

    orig_leave = listbox.leaveEvent
    def _leave_event(event):
        _clear_highlight()
        orig_leave(event)
    listbox.leaveEvent = _leave_event

    orig_close = dialog.closeEvent
    def _close_event(event):
        _clear_highlight()
        orig_close(event)
    dialog.closeEvent = _close_event

    close_btn = QPushButton(tl('close') if tl else "Close")
    close_btn.clicked.connect(dialog.close)
    layout.addWidget(close_btn)

    dialog.show()


def show_entity_list_popup(parent, send_queue, widget_tags, tabs, dev_tab, camera_tab, tl=None):
    dialog = QDialog(parent)
    dialog.setWindowTitle(tl('entity_list') if tl else "Entity List")
    dialog.resize(450, 400)
    layout = QVBoxLayout(dialog)

    layout.addWidget(QLabel(tl('entity_list_hint') if tl else "Click to copy. Right-click for TP / Camera options."))

    search_input = QLineEdit()
    search_input.setPlaceholderText(tl('search') if tl else "Search")
    layout.addWidget(search_input)

    listbox = QListWidget()
    listbox.setMouseTracking(True)
    layout.addWidget(listbox)

    all_entities = []

    def _populate(entries):
        listbox.clear()
        for entry in entries:
            item = QListWidgetItem(entry['display'])
            item.setData(Qt.ItemDataRole.UserRole, {
                'x': entry['x'], 'y': entry['y'], 'z': entry['z'],
                'height': entry.get('height', 170.0),
                'gid': entry.get('gid', 0),
                'distance': entry.get('distance', 0.0),
            })
            listbox.addItem(item)

    def update_entities(entity_data):
        nonlocal all_entities
        all_entities = entity_data
        search_text = search_input.text()
        if search_text:
            filtered = [e for e in all_entities if search_text.lower() in e['display'].lower()]
            _populate(filtered)
        else:
            _populate(all_entities)

    dialog.update_entities = update_entities

    def on_search(text):
        if text:
            filtered = [e for e in all_entities if text.lower() in e['display'].lower()]
            _populate(filtered)
        else:
            _populate(all_entities)

    def on_hover(item):
        if item:
            data = item.data(Qt.ItemDataRole.UserRole)
            if data:
                send_queue.put(GUICommand(GUICommandType.HighlightEntity, (data['x'], data['y'], data['z'], data['height'])))

    def on_select(item):
        if item:
            pyperclip.copy(item.text())
            send_queue.put(GUICommand(GUICommandType.ClearHighlight))
            dialog.close()

    def _clear_highlight():
        send_queue.put(GUICommand(GUICommandType.ClearHighlight))

    listbox.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    def on_context_menu(pos):
        item = listbox.itemAt(pos)
        if not item:
            return
        data = item.data(Qt.ItemDataRole.UserRole)
        if not data:
            return
        gid_str = str(data.get('gid', ''))

        menu = QMenu(listbox)
        tp_action = menu.addAction(tl('tp_to_entity') if tl else "Teleport to Entity")
        anchor_action = menu.addAction(tl('anchor_cam_to_entity') if tl else "Anchor Camera to Entity")

        action = menu.exec(listbox.mapToGlobal(pos))
        if action == tp_action:
            gid_widget = widget_tags.get('EntityTPGIDInput')
            if gid_widget:
                gid_widget.setText(gid_str)
            tabs.setCurrentWidget(dev_tab)
            send_queue.put(GUICommand(GUICommandType.ClearHighlight))
            dialog.close()
        elif action == anchor_action:
            gid_widget = widget_tags.get('CamEntityGIDInput')
            if gid_widget:
                gid_widget.setText(gid_str)
            tabs.setCurrentWidget(camera_tab)
            send_queue.put(GUICommand(GUICommandType.ClearHighlight))
            dialog.close()

    listbox.customContextMenuRequested.connect(on_context_menu)

    search_input.textChanged.connect(on_search)
    listbox.itemEntered.connect(on_hover)
    listbox.itemClicked.connect(on_select)

    orig_leave = listbox.leaveEvent
    def _leave_event(event):
        _clear_highlight()
        orig_leave(event)
    listbox.leaveEvent = _leave_event

    orig_close = dialog.closeEvent
    def _close_event(event):
        _clear_highlight()
        send_queue.put(GUICommand(GUICommandType.StopEntityStream))
        orig_close(event)
    dialog.closeEvent = _close_event

    close_btn = QPushButton(tl('close') if tl else "Close")
    close_btn.clicked.connect(dialog.close)
    layout.addWidget(close_btn)

    send_queue.put(GUICommand(GUICommandType.StartEntityStream))

    for btn in dialog.findChildren(QPushButton):
        btn.setAutoDefault(False)
        btn.setDefault(False)

    dialog.show()
    if big_editor.viewport().width() > 0:
        big_editor.document().setTextWidth(big_editor.viewport().width())
    big_editor.update_line_number_area_width(0)
    return dialog

class _LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.code_editor = editor

    def sizeHint(self):
        return QSize(self.code_editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self.code_editor.line_number_area_paint_event(event)


class CodeEditor(QTextEdit):
    # Zero outer frame margin for maximal text area
    def __init__(self, parent=None, stroke_color="#888888", show_line_numbers=False):
        super().__init__(parent)
        self.stroke_color = stroke_color
        self.line_number_area = _LineNumberArea(self)
        self.show_line_numbers = show_line_numbers
        self.on_find_requested = None
        self.on_replace_requested = None

        # Clean monospace coding font (10pt default)
        font = QFont("Cascadia Code", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)
        self.document().setDefaultFont(font)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(' ') * 4)

        # Standard clean document margin, zero frame border and disabled horizontal scrollbar
        self.document().setDocumentMargin(0)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setFrameShadow(QFrame.Shadow.Plain)
        self.setLineWidth(0)
        self.setStyleSheet(
            "QTextEdit { border: none; outline: none; }"
            "QTextEdit:focus { border: none; outline: none; }"
            "QScrollBar:vertical { width: 12px; background: rgba(0, 0, 0, 0.15); border-radius: 6px; margin: 0px; }"
            "QScrollBar::handle:vertical { background: rgba(255, 255, 255, 0.25); border-radius: 5px; min-height: 28px; margin: 1px; }"
            "QScrollBar::handle:vertical:hover { background: rgba(255, 255, 255, 0.45); }"
            "QScrollBar::handle:vertical:pressed { background: rgba(255, 255, 255, 0.65); }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; background: transparent; }"
            "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }"
        )

        self._connect_doc_signals()
        self.verticalScrollBar().valueChanged.connect(lambda _: self.line_number_area.update())
        self.cursorPositionChanged.connect(self.highlight_current_line)

        self.set_line_numbers_visible(show_line_numbers)

    def _connect_doc_signals(self):
        try:
            self.document().blockCountChanged.disconnect(self.update_line_number_area_width)
        except Exception:
            pass
        try:
            self.document().contentsChanged.disconnect(self._on_doc_contents_changed)
        except Exception:
            pass
        self.document().blockCountChanged.connect(self.update_line_number_area_width)
        self.document().contentsChanged.connect(self._on_doc_contents_changed)

    def _on_doc_contents_changed(self):
        if self.viewport().width() > 0:
            self.document().setTextWidth(self.viewport().width())
        self.update_line_number_area_width(0)
        self.line_number_area.update()

    def setDocument(self, document):
        super().setDocument(document)
        font = QFont("Cascadia Code", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)
        self.document().setDefaultFont(font)
        self.document().setDocumentMargin(0)
        if self.viewport().width() > 0:
            self.document().setTextWidth(self.viewport().width())
        self.document().markContentsDirty(0, self.document().characterCount())
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(' ') * 4)
        self._connect_doc_signals()
        self.update_line_number_area_width(0)
        self.line_number_area.update()
        self.viewport().update()

    def blockCount(self):
        return self.document().blockCount()

    def line_number_area_width(self):
        if not self.show_line_numbers:
            return 0
        digits = max(1, len(str(max(1, self.blockCount()))))
        from PyQt6.QtGui import QFont, QFontMetrics
        line_font = QFont(self.font().family(), max(7, self.font().pointSize() - 2))
        fm = QFontMetrics(line_font)
        # Balanced 4px left margin + max digits width + 4px right margin to hairline
        return 4 + fm.horizontalAdvance('9' * digits) + 4

    def set_line_numbers_visible(self, visible):
        self.show_line_numbers = visible
        self.line_number_area.setVisible(visible)
        w = self.line_number_area_width()
        self.setViewportMargins(w, 0, 0, 0)
        cr = self.contentsRect()
        if visible:
            self.line_number_area.setGeometry(cr.left(), cr.top(), w, cr.height())
            self.line_number_area.update()
        else:
            self.line_number_area.setGeometry(0, 0, 0, 0)
        self.viewport().update()

    def toggle_line_numbers(self):
        self.set_line_numbers_visible(not self.show_line_numbers)
        return self.show_line_numbers

    def update_line_number_area_width(self, _=0):
        w = self.line_number_area_width()
        self.setViewportMargins(w, 0, 0, 0)
        if self.show_line_numbers:
            cr = self.contentsRect()
            self.line_number_area.setGeometry(cr.left(), cr.top(), w, cr.height())
            self.line_number_area.update()

    def showEvent(self, event):
        super().showEvent(event)
        if self.viewport().width() > 0:
            self.document().setTextWidth(self.viewport().width())
        self.update_line_number_area_width(0)
        self.line_number_area.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        w = self.line_number_area_width()
        if self.show_line_numbers:
            self.setViewportMargins(w, 0, 0, 0)
            self.line_number_area.setGeometry(cr.left(), cr.top(), w, cr.height())
            self.line_number_area.update()
        else:
            self.setViewportMargins(0, 0, 0, 0)
            self.line_number_area.setGeometry(0, 0, 0, 0)
        if self.viewport().width() > 0:
            self.document().setTextWidth(self.viewport().width())

    def highlight_current_line(self):
        extra_selections = []
        if not self.isReadOnly():
            selection = QTextEdit.ExtraSelection()
            # Very gentle, calm ambient highlight (soft translucent tint, completely glare-free)
            line_color = QColor(255, 255, 255, 14)
            selection.format.setBackground(line_color)
            selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            extra_selections.append(selection)
        self.setExtraSelections(extra_selections)

    def contextMenuEvent(self, event):
        menu = self.createStandardContextMenu()
        if menu:
            menu.addSeparator()
            if self.on_find_requested:
                find_act = menu.addAction("Find")
                find_act.setShortcut(QKeySequence("Ctrl+F"))
                find_act.triggered.connect(self.on_find_requested)
            if self.on_replace_requested and not self.isReadOnly():
                replace_act = menu.addAction("Replace")
                replace_act.setShortcut(QKeySequence("Ctrl+H"))
                replace_act.triggered.connect(self.on_replace_requested)
            menu.exec(event.globalPos())
        else:
            super().contextMenuEvent(event)

    def line_number_area_paint_event(self, event):
        if not self.show_line_numbers:
            return
        from PyQt6.QtGui import QPainter, QColor, QFont, QFontMetrics
        painter = QPainter(self.line_number_area)
        painter.fillRect(event.rect(), self.palette().base().color())

        doc = self.document()
        block = doc.begin()
        block_number = 0

        line_font = QFont(self.font().family(), max(7, self.font().pointSize() - 2))
        line_fm = QFontMetrics(line_font)
        editor_fm = self.fontMetrics()
        painter.setFont(line_font)
        painter.setPen(QColor(128, 128, 128, 140))

        vbar = self.verticalScrollBar().value()
        viewport_top = 0
        viewport_bottom = self.viewport().height()
        gutter_w = self.line_number_area.width()

        while block.isValid():
            layout = block.layout()
            if layout:
                pos = layout.position()
                y = int(pos.y()) - vbar
                h = int(layout.boundingRect().height())
                if y + h >= viewport_top and y <= viewport_bottom:
                    number = str(block_number + 1)
                    num_w = line_fm.horizontalAdvance(number)
                    # Perfectly centered horizontally in the gutter
                    x_center = max(0, int((gutter_w - 1 - num_w) / 2))
                    # Line height of the first line in this block for exact vertical middle alignment
                    first_line_h = int(layout.lineAt(0).rect().height()) if layout.lineCount() > 0 else (h if h > 0 else editor_fm.height())
                    # Centered vertically in the middle of the text line space
                    painter.drawText(x_center, y, num_w + 2, first_line_h,
                                     Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, number)
            block = block.next()
            block_number += 1

        # Crisp, subtle separator border line between gutter and code text
        painter.setPen(QColor(128, 128, 128, 40))
        painter.drawLine(gutter_w - 1, event.rect().top(), gutter_w - 1, event.rect().bottom())


def show_bot_editor_popup(ctx, parent_editor, run_cb=None, kill_cb=None, set_running_cb=None, import_cb=None, export_cb=None, tl=None, mode='bot'):
    """Opens a fully resizable, standalone Editor or Console Logs window with line numbers and shortcuts."""
    is_console = (mode == 'console')
    is_combat = (mode == 'combat')

    if is_console:
        default_title = "Console Logs"
        title_key = 'console_editor_title'
    elif is_combat:
        default_title = "Combat Editor"
        title_key = 'combat_editor_title'
    else:
        default_title = "Bot Editor"
        title_key = 'bot_editor_title'

    win_title = ctx.tl(title_key) if ctx.tl(title_key) != title_key else default_title

    dialog = QDialog(ctx.window)
    dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
    dialog.setWindowTitle(win_title)
    dialog.resize(850, 650)
    dialog.setMinimumSize(500, 380)
    dialog.setWindowFlags(Qt.WindowType.Window)

    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(0, 1, 0, 0)
    layout.setSpacing(1)

    # Top Toolbar
    top_bar = QHBoxLayout()
    top_bar.setContentsMargins(4, 0, 4, 0)
    top_bar.setSpacing(3)

    def make_popup_icon_btn(svg_key, tooltip, callback, action_id):
        btn = QPushButton()
        btn.setAutoDefault(False)
        btn.setDefault(False)
        svg_content = ctx.svgs.get(svg_key, '')
        if not svg_content and svg_key == 'check':
            sc = getattr(ctx, 'stroke_color', '#61afef')
            svg_content = f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>'
        btn.setIcon(ctx.titlebar_svg_icon(svg_content, 22))
        btn.setFixedSize(30, 30)
        btn.setStyleSheet(ctx.icon_btn_style)
        btn.setToolTip(tooltip)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if callback:
            btn.clicked.connect(callback)
        if hasattr(ctx, 'registry') and ctx.registry and action_id:
            ctx.registry.make_bindable(btn, action_id)
        if hasattr(ctx, 'tracked_icon_buttons') and svg_content:
            ctx.tracked_icon_buttons.append((btn, svg_content, 26))
        return btn

    if is_console:
        # CONSOLE TAB: Only copy button on the left, line numbers toggle (#) on the right.
        def _copy_logs():
            import pyperclip
            pyperclip.copy(parent_editor.toPlainText())

        copy_btn = make_popup_icon_btn('copy_logs', ctx.tl('copy_logs'), _copy_logs, 'copy_logs')
        top_bar.addWidget(copy_btn)
        top_bar.addStretch()

        numbers_btn = QPushButton("#")
        numbers_btn.setFixedSize(26, 26)
        numbers_btn.setToolTip("Toggle Line Numbers")
        numbers_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        numbers_btn.setStyleSheet(
            f"{ctx.icon_btn_style}; font-weight: bold; font-size: 13px; color: rgba(200, 200, 200, 0.85);"
        )
        top_bar.addWidget(numbers_btn)
    else:
        # BOT & COMBAT TABS: Full action toolbar
        import_tooltip = ctx.tl('import_playstyle') if is_combat else ctx.tl('import_bot')
        export_tooltip = ctx.tl('export_playstyle') if is_combat else ctx.tl('export_bot')
        import_aid = 'import_playstyle' if is_combat else 'import_bot'
        export_aid = 'export_playstyle' if is_combat else 'export_bot'

        recent_aid = 'recent_imports'
        recent_btn = QPushButton()
        recent_btn.setAutoDefault(False)
        recent_btn.setDefault(False)
        recent_btn.setIcon(ctx.titlebar_svg_icon(ctx.svgs['recent'], 26))
        recent_btn.setFixedSize(30, 30)
        recent_btn.setStyleSheet(ctx.icon_btn_style)
        recent_btn.setToolTip(ctx.tl('recent_imports'))
        recent_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        recent_btn.clicked.connect(lambda: show_recent_menu(ctx, 'combat' if is_combat else 'bot', parent_editor, recent_btn))
        if hasattr(ctx, 'registry') and ctx.registry:
            ctx.registry.make_bindable(recent_btn, recent_aid)
        if hasattr(ctx, 'tracked_icon_buttons'):
            ctx.tracked_icon_buttons.append((recent_btn, ctx.svgs['recent'], 26))

        import_btn = make_popup_icon_btn('import', import_tooltip, import_cb, import_aid)
        export_btn = make_popup_icon_btn('export', export_tooltip, export_cb, export_aid)

        top_bar.addWidget(recent_btn)
        top_bar.addWidget(import_btn)
        top_bar.addWidget(export_btn)

        action_btn = None
        if not is_combat:
            action_btn = QPushButton()
            action_btn.setFixedSize(30, 30)
            action_btn.setStyleSheet(ctx.icon_btn_style)
            action_btn.setCursor(Qt.CursorShape.PointingHandCursor)

            _running = [False]

            if hasattr(ctx, 'tracked_toggle_btns'):
                for b, r, sz in ctx.tracked_toggle_btns:
                    if getattr(b, 'toolTip', lambda: '')() in (ctx.tl('run_bot'), ctx.tl('kill_bot')):
                        _running[0] = bool(r[0])
                        break

            def update_action_icon(running):
                _running[0] = running
                svg = ctx.svgs['kill'] if running else ctx.svgs['play']
                action_btn.setIcon(ctx.titlebar_svg_icon(svg, 22))
                action_btn.setToolTip(ctx.tl('kill_bot') if running else ctx.tl('run_bot'))

            update_action_icon(_running[0])

            def on_action_toggle():
                if _running[0]:
                    kill_cb()
                else:
                    run_cb()

            action_btn.clicked.connect(on_action_toggle)

            orig_bot_export_set = None
            if hasattr(ctx, 'exports') and 'bot' in ctx.exports:
                orig_bot_export_set = ctx.exports['bot'].get('set_running')

            def synced_set_running(running):
                update_action_icon(running)
                if orig_bot_export_set:
                    try:
                        orig_bot_export_set(running)
                    except Exception:
                        pass

            ctx.exports['bot']['set_running'] = synced_set_running

            if hasattr(ctx, 'registry') and ctx.registry:
                ctx.registry.make_bindable(action_btn, 'toggle_bot')

            if hasattr(ctx, 'tracked_toggle_btns'):
                ctx.tracked_toggle_btns.append((action_btn, _running, 26))

            top_bar.addWidget(action_btn)
        else:
            action_btn = make_popup_icon_btn('refresh', ctx.tl('set_playstyles'), run_cb, 'set_playstyles')
            top_bar.addWidget(action_btn)

        top_bar.addStretch()

        numbers_btn = QPushButton("#")
        numbers_btn.setFixedSize(26, 26)
        numbers_btn.setToolTip("Toggle Line Numbers")
        numbers_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        numbers_btn.setStyleSheet(
            f"{ctx.icon_btn_style}; font-weight: bold; font-size: 13px; color: rgba(200, 200, 200, 0.85);"
        )
        top_bar.addWidget(numbers_btn)

        check_btn = None
        if not is_combat:
            check_aid = 'validate_bot_script'
            check_btn = make_popup_icon_btn('check', "Validate Syntax", lambda: None, check_aid)
            if hasattr(ctx, 'registry') and ctx.registry:
                if check_aid not in ctx.registry.meta:
                    ctx.registry.register(check_aid, "Validate Syntax", "Bot", lambda: None)
                ctx.registry.make_bindable(check_btn, check_aid)
            top_bar.addWidget(check_btn)

    layout.addLayout(top_bar)

    # Load saved user preference for line numbers (default: False / toggled off)
    initial_show_lines = False
    if hasattr(ctx, 'settings') and ctx.settings:
        saved_pref = ctx.settings.get_setting('editor_show_line_numbers')
        if saved_pref is not None:
            initial_show_lines = bool(saved_pref)

    numbers_btn.setStyleSheet(
        f"{ctx.icon_btn_style}; font-weight: bold; font-size: 13px; color: " +
        ("rgba(200, 200, 200, 0.85);" if initial_show_lines else "rgba(100, 100, 100, 0.5);")
    )

    # Find & Replace Bar (Collapsible with Ctrl+F / Ctrl+H)
    find_replace_widget = QWidget()
    find_replace_layout = QVBoxLayout(find_replace_widget)
    find_replace_layout.setContentsMargins(6, 4, 6, 4)
    find_replace_layout.setSpacing(4)
    find_replace_widget.setStyleSheet("background: rgba(30, 30, 30, 0.95); border: 1px solid rgba(255, 255, 255, 0.15); border-radius: 6px;")

    # Row 1: Find Row
    find_row = QHBoxLayout()
    find_row.setContentsMargins(0, 0, 0, 0)
    find_row.setSpacing(6)

    find_input = QLineEdit()
    find_input.setPlaceholderText("Find text...")
    find_input.setStyleSheet("padding: 3px 6px; border-radius: 4px;")

    match_count_label = QLabel("0 of 0")
    match_count_label.setStyleSheet("color: rgba(180, 180, 180, 0.85); font-size: 11px; min-width: 55px; background: transparent; border: none;")

    find_prev_btn = QPushButton()
    find_prev_svg = ctx.svgs.get('arrow_up', f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{getattr(ctx, "stroke_color", "#61afef")}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="18 15 12 9 6 15"/></svg>')
    find_prev_btn.setIcon(ctx.titlebar_svg_icon(find_prev_svg, 14))
    find_prev_btn.setFixedSize(26, 24)
    find_prev_btn.setToolTip("Previous Match (Shift+Enter)")
    find_prev_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    find_prev_btn.setStyleSheet(ctx.icon_btn_style)

    find_next_btn = QPushButton()
    find_next_svg = ctx.svgs.get('arrow_down', f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{getattr(ctx, "stroke_color", "#61afef")}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>')
    find_next_btn.setIcon(ctx.titlebar_svg_icon(find_next_svg, 14))
    find_next_btn.setFixedSize(26, 24)
    find_next_btn.setToolTip("Next Match (Enter)")
    find_next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    find_next_btn.setStyleSheet(ctx.icon_btn_style)

    find_close_btn = QPushButton()
    find_close_btn.setAutoDefault(False)
    find_close_btn.setDefault(False)
    find_close_btn.setIcon(ctx.titlebar_svg_icon(ctx.svgs['x'], 14))
    find_close_btn.setFixedSize(26, 24)
    find_close_btn.setToolTip("Close Find (Esc)")
    find_close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    find_close_btn.setStyleSheet(ctx.icon_btn_style)

    find_row.addWidget(find_input, 1)
    find_row.addWidget(match_count_label)
    find_row.addWidget(find_prev_btn)
    find_row.addWidget(find_next_btn)
    find_row.addWidget(find_close_btn)
    find_replace_layout.addLayout(find_row)

    # Row 2: Replace Row (for editable modes: Bot & Combat)
    replace_row_widget = QWidget()
    replace_row = QHBoxLayout(replace_row_widget)
    replace_row.setContentsMargins(0, 0, 0, 0)
    replace_row.setSpacing(6)

    replace_input = QLineEdit()
    replace_input.setPlaceholderText("Replace with...")
    replace_input.setStyleSheet("padding: 3px 6px; border-radius: 4px;")

    replace_one_btn = QPushButton("Replace")
    replace_one_btn.setStyleSheet(f"{ctx.icon_btn_style}; padding: 0 8px; font-size: 11px; height: 24px;")

    replace_all_btn = QPushButton("Replace All")
    replace_all_btn.setStyleSheet(f"{ctx.icon_btn_style}; padding: 0 8px; font-size: 11px; height: 24px;")

    replace_row.addWidget(replace_input, 1)
    replace_row.addWidget(replace_one_btn)
    replace_row.addWidget(replace_all_btn)
    find_replace_layout.addWidget(replace_row_widget)

    if is_console:
        replace_row_widget.hide()

    find_replace_widget.hide()
    layout.addWidget(find_replace_widget)

    # Code Editor with Line Numbers (default toggled off per user request)
    big_editor = CodeEditor(dialog, stroke_color=getattr(ctx, 'stroke_color', '#888888'), show_line_numbers=initial_show_lines)
    if is_console:
        big_editor.setReadOnly(True)
        big_editor.setPlainText(parent_editor.toPlainText())
    else:
        # Share native QTextDocument for flawless, seamless Undo/Redo (Ctrl+Z / Ctrl+Y)
        big_editor.setDocument(parent_editor.document())
        big_editor.document().setDocumentMargin(0)
        # Re-apply styling/font on big_editor
        font = QFont("Cascadia Code", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        big_editor.setFont(font)
        big_editor.setTabStopDistance(big_editor.fontMetrics().horizontalAdvance(' ') * 4)

    layout.addWidget(big_editor, 1)

    # Connect toggle line numbers button & save user preference
    def _on_toggle_numbers():
        is_visible = big_editor.toggle_line_numbers()
        numbers_btn.setStyleSheet(
            f"{ctx.icon_btn_style}; font-weight: bold; font-size: 13px; color: " +
            ("rgba(200, 200, 200, 0.85);" if is_visible else "rgba(100, 100, 100, 0.5);")
        )
        if hasattr(ctx, 'settings') and ctx.settings:
            try:
                ctx.settings.set_setting('editor_show_line_numbers', is_visible)
            except Exception:
                pass

    numbers_btn.clicked.connect(_on_toggle_numbers)

    # Find & Replace Match Counting and Cycling Logic
    def get_match_positions():
        query = find_input.text()
        if not query:
            return []
        text_content = big_editor.toPlainText()
        pos = 0
        positions = []
        q_len = len(query)
        while True:
            idx = text_content.find(query, pos)
            if idx == -1:
                break
            positions.append(idx)
            pos = idx + max(1, q_len)
        return positions

    def update_match_label():
        query = find_input.text()
        if not query:
            match_count_label.setText("0 of 0")
            return
        positions = get_match_positions()
        total = len(positions)
        if total == 0:
            match_count_label.setText("0 of 0")
            return
        cursor_pos = big_editor.textCursor().selectionStart()
        current_idx = 0
        for i, p in enumerate(positions):
            if cursor_pos >= p:
                current_idx = i + 1
            else:
                break
        if current_idx == 0 and total > 0:
            current_idx = 1
        match_count_label.setText(f"{current_idx} of {total}")

    def find_next():
        query = find_input.text()
        if not query:
            return
        if not big_editor.find(query):
            # Wrap around to document beginning
            big_editor.moveCursor(QTextCursor.MoveOperation.Start)
            big_editor.find(query)
        update_match_label()

    def find_prev():
        query = find_input.text()
        if not query:
            return
        from PyQt6.QtGui import QTextDocument
        if not big_editor.find(query, QTextDocument.FindFlag.FindBackward):
            # Wrap around to document end
            big_editor.moveCursor(QTextCursor.MoveOperation.End)
            big_editor.find(query, QTextDocument.FindFlag.FindBackward)
        update_match_label()

    def replace_one():
        if is_console or big_editor.isReadOnly():
            return
        query = find_input.text()
        replacement = replace_input.text()
        if not query:
            return
        cursor = big_editor.textCursor()
        if cursor.hasSelection() and cursor.selectedText() == query:
            cursor.insertText(replacement)
            big_editor.setTextCursor(cursor)
            find_next()
        else:
            find_next()
            cursor = big_editor.textCursor()
            if cursor.hasSelection() and cursor.selectedText() == query:
                cursor.insertText(replacement)
                big_editor.setTextCursor(cursor)
                find_next()
        big_editor.viewport().update()
        if hasattr(parent_editor, 'viewport'):
            parent_editor.viewport().update()
        update_match_label()

    def replace_all():
        if is_console or big_editor.isReadOnly():
            return
        query = find_input.text()
        replacement = replace_input.text()
        if not query:
            return
        doc = big_editor.document()
        cursor = QTextCursor(doc)
        cursor.beginEditBlock()
        replaced = False
        while True:
            cursor = doc.find(query, cursor)
            if cursor.isNull():
                break
            cursor.insertText(replacement)
            replaced = True
        cursor.endEditBlock()
        if replaced:
            # Force immediate viewport repaint and layout refresh on both editors
            big_editor.setTextCursor(cursor)
            big_editor.viewport().update()
            if hasattr(parent_editor, 'viewport'):
                parent_editor.viewport().update()
        update_match_label()

    def on_find_input_key(event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                find_prev()
            else:
                find_next()
            event.accept()
            return
        QLineEdit.keyPressEvent(find_input, event)

    def on_replace_input_key(event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            replace_one()
            event.accept()
            return
        QLineEdit.keyPressEvent(replace_input, event)

    find_input.keyPressEvent = on_find_input_key
    replace_input.keyPressEvent = on_replace_input_key
    find_input.textChanged.connect(lambda _: update_match_label())
    find_next_btn.clicked.connect(find_next)
    find_prev_btn.clicked.connect(find_prev)
    replace_one_btn.clicked.connect(replace_one)
    replace_all_btn.clicked.connect(replace_all)

    def close_find_replace():
        find_replace_widget.hide()
        big_editor.setFocus()

    find_close_btn.clicked.connect(close_find_replace)

    def toggle_find_bar(show_replace=False):
        curr_h = dialog.height()
        curr_w = dialog.width()
        # If already visible in the requested mode, pressing shortcut again closes it
        if find_replace_widget.isVisible():
            if is_console:
                close_find_replace()
                dialog.resize(curr_w, curr_h)
                return
            replace_is_shown = replace_row_widget.isVisible()
            if show_replace == replace_is_shown:
                close_find_replace()
                dialog.resize(curr_w, curr_h)
                return
            # Switch between Find-only and Replace modes
            replace_row_widget.setVisible(show_replace)
            dialog.resize(curr_w, curr_h)
            if show_replace:
                replace_input.setFocus()
                replace_input.selectAll()
            else:
                find_input.setFocus()
                find_input.selectAll()
            return

        # Not visible -> show it
        if not is_console:
            replace_row_widget.setVisible(show_replace)
        find_replace_widget.show()
        dialog.resize(curr_w, curr_h)
        cursor = big_editor.textCursor()
        if cursor.hasSelection():
            sel = cursor.selectedText().strip()
            if sel and ('\n' not in sel):
                find_input.setText(sel)
        find_input.setFocus()
        find_input.selectAll()
        update_match_label()

    big_editor.on_find_requested = lambda: toggle_find_bar(show_replace=False)
    if not is_console:
        big_editor.on_replace_requested = lambda: toggle_find_bar(show_replace=True)

    QShortcut(QKeySequence("Ctrl+F"), dialog, lambda: toggle_find_bar(show_replace=False))
    if not is_console:
        QShortcut(QKeySequence("Ctrl+H"), dialog, lambda: toggle_find_bar(show_replace=True))
    QShortcut(QKeySequence("Escape"), find_replace_widget, close_find_replace)
    QShortcut(QKeySequence("Shift+Return"), find_input, find_prev)

    # Seamless dialog-wide Undo and Redo (guarded and crash-proof)
    def do_dialog_undo():
        try:
            focused = QApplication.focusWidget()
            if isinstance(focused, QLineEdit):
                if hasattr(focused, 'isUndoAvailable') and focused.isUndoAvailable():
                    focused.undo()
                    return
            if not is_console and hasattr(big_editor, 'undo'):
                big_editor.undo()
                update_match_label()
                big_editor.viewport().update()
                if hasattr(parent_editor, 'viewport'):
                    parent_editor.viewport().update()
        except Exception:
            pass

    def do_dialog_redo():
        try:
            focused = QApplication.focusWidget()
            if isinstance(focused, QLineEdit):
                if hasattr(focused, 'isRedoAvailable') and focused.isRedoAvailable():
                    focused.redo()
                    return
            if not is_console and hasattr(big_editor, 'redo'):
                big_editor.redo()
                update_match_label()
                big_editor.viewport().update()
                if hasattr(parent_editor, 'viewport'):
                    parent_editor.viewport().update()
        except Exception:
            pass

    if not is_console:
        QShortcut(QKeySequence("Ctrl+Z"), dialog, do_dialog_undo)
        QShortcut(QKeySequence("Ctrl+Y"), dialog, do_dialog_redo)
        QShortcut(QKeySequence("Ctrl+Shift+Z"), dialog, do_dialog_redo)


    # Attach in-window hotkey shortcuts so binded keys execute inside the editor!
    active_shortcuts = []
    if hasattr(ctx, 'settings') and ctx.settings:
        hotkeys = ctx.settings.get_hotkeys()

        actions_map = {
            'copy_logs': (_copy_logs if is_console else None),
            'toggle_bot': (on_action_toggle if (not is_combat and not is_console) else None),
            'import_bot': (import_cb if (not is_combat and not is_console) else None),
            'export_bot': (export_cb if (not is_combat and not is_console) else None),
            'recent_imports': ((lambda: show_recent_menu(ctx, 'combat' if is_combat else 'bot', parent_editor, recent_btn)) if not is_console else None),
            'import_playstyle': (import_cb if is_combat else None),
            'export_playstyle': (export_cb if is_combat else None),
            'set_playstyles': (run_cb if is_combat else None),
            'validate_bot_script': None # linked after validate fn
        }

        def build_key_seq(binding):
            if not binding or not binding.get('key'):
                return None
            parts = []
            for m in binding.get('modifiers', []):
                if m.upper() in ('CTRL', 'CONTROL'): parts.append('Ctrl')
                elif m.upper() == 'SHIFT': parts.append('Shift')
                elif m.upper() == 'ALT': parts.append('Alt')
            parts.append(binding['key'])
            return '+'.join(parts)

        for aid, cb in actions_map.items():
            if cb and aid in hotkeys:
                seq_str = build_key_seq(hotkeys.get(aid))
                if seq_str:
                    try:
                        sc = QShortcut(QKeySequence(seq_str), dialog, cb)
                        active_shortcuts.append(sc)
                    except Exception:
                        pass


    # Syntax status notification banner (placed at the TOP above editor, never at the bottom!)
    status_card = None
    syntax_label = None
    if not is_combat and not is_console:
        status_card = QWidget()
        status_card_layout = QHBoxLayout(status_card)
        status_card_layout.setContentsMargins(8, 4, 8, 4)
        status_card_layout.setSpacing(6)

        syntax_label = QLabel("")
        syntax_label.setWordWrap(True)
        syntax_label.setStyleSheet("font-weight: 600; background: transparent; border: none;")

        status_dismiss_btn = QPushButton()
        status_dismiss_btn.setAutoDefault(False)
        status_dismiss_btn.setDefault(False)
        status_dismiss_btn.setIcon(ctx.titlebar_svg_icon(ctx.svgs['x'], 14))
        status_dismiss_btn.setFixedSize(26, 24)
        status_dismiss_btn.setToolTip("Dismiss")
        status_dismiss_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        status_dismiss_btn.setStyleSheet(ctx.icon_btn_style)
        status_dismiss_btn.clicked.connect(status_card.hide)

        status_card_layout.addWidget(syntax_label, 1)
        status_card_layout.addWidget(status_dismiss_btn)
        status_card.hide()
        # Insert right below top_bar at index 1 so the bottom is ALWAYS 100% clean editor space!
        layout.insertWidget(1, status_card)

        big_editor.textChanged.connect(lambda: status_card.hide() if status_card.isVisible() else None)
        big_editor.cursorPositionChanged.connect(lambda: status_card.hide() if status_card.isVisible() else None)

    # 2-Way Sync (for read-only console streaming)
    def on_console_parent_changed():
        if is_console:
            cursor_at_end = (big_editor.textCursor().position() >= len(big_editor.toPlainText()) - 5)
            big_editor.setPlainText(parent_editor.toPlainText())
            if cursor_at_end:
                big_editor.moveCursor(QTextCursor.MoveOperation.End)

    if is_console:
        parent_editor.textChanged.connect(on_console_parent_changed)

    # Syntax Validation logic (Bot Editor only)
    if not is_combat and not is_console and check_btn is not None:
        def on_validate():
            if status_card.isVisible():
                status_card.hide()
                return

            text = big_editor.toPlainText().strip()
            if not text:
                status_card.setStyleSheet(
                    "background-color: rgba(229, 192, 123, 0.15); color: #e5c07b; "
                    "border: 1px solid #e5c07b; border-radius: 6px;"
                )
                syntax_label.setText("Script is empty.")
                status_card.show()
                return

            try:
                from src.deimoslang.vm import VM
                v = VM({})
                v.load_from_text(text)
                status_card.setStyleSheet(
                    "background-color: rgba(152, 195, 121, 0.15); color: #98c379; "
                    "border: 1px solid #98c379; border-radius: 6px;"
                )
                syntax_label.setText("Valid syntax. No errors found.")
                status_card.show()
            except Exception as e:
                err_msg = str(e).strip()
                err_msg = err_msg.replace('?', '').strip()
                status_card.setStyleSheet(
                    "background-color: rgba(224, 108, 117, 0.15); color: #e06c75; "
                    "border: 1px solid #e06c75; border-radius: 6px;"
                )
                syntax_label.setText(f"Syntax Error: {err_msg}")
                status_card.show()

        check_btn.clicked.connect(on_validate)
        if hasattr(ctx, 'registry') and ctx.registry and check_aid in ctx.registry.callbacks:
            ctx.registry.callbacks[check_aid] = on_validate

        if hasattr(ctx, 'settings') and ctx.settings:
            hotkeys = ctx.settings.get_hotkeys()
            if check_aid in hotkeys:
                seq_str = build_key_seq(hotkeys.get(check_aid))
                if seq_str:
                    try:
                        active_shortcuts.append(QShortcut(QKeySequence(seq_str), dialog, on_validate))
                    except Exception:
                        pass



    def on_close(event):
        if is_console:
            try:
                parent_editor.textChanged.disconnect(on_console_parent_changed)
            except Exception:
                pass
        if not is_combat and not is_console and hasattr(ctx, 'exports') and 'bot' in ctx.exports and orig_bot_export_set:
            ctx.exports['bot']['set_running'] = orig_bot_export_set
        if is_console:
            attr_name = 'console_editor_dialog'
        elif is_combat:
            attr_name = 'combat_editor_dialog'
        else:
            attr_name = 'bot_editor_dialog'
        if getattr(ctx, attr_name, None) is dialog:
            setattr(ctx, attr_name, None)
        event.accept()

    dialog.closeEvent = on_close

    for btn in dialog.findChildren(QPushButton):
        btn.setAutoDefault(False)
        btn.setDefault(False)

    dialog.show()
    if big_editor.viewport().width() > 0:
        big_editor.document().setTextWidth(big_editor.viewport().width())
    big_editor.update_line_number_area_width(0)
    return dialog
