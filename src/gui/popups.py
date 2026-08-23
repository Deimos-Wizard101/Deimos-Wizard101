import html
import re
import webbrowser

import pyperclip

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QListWidget, QListWidgetItem, QWidget, QMenu, QProgressBar,
    QComboBox, QPlainTextEdit, QFormLayout,
)
from PyQt6.QtCore import Qt, QSize

from src import bot_registry
from src.gui.commands import GUICommand, GUICommandType
from src.gui.helpers import launcher_small_icon_btn, spinning_loader_widget


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
    dialog.show()
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

    dialog.show()
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
    zone_input = QLineEdit((metadata.get('zone') or '').strip())
    zone_input.setPlaceholderText(tl('bot_publish_zone_hint'))
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
    form.addRow(tl('bot_publish_zone') + ' *', zone_input)
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
        required = all(w.text().strip() for w in (name_input, zone_input, author_input))
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
        meta = {
            'name': name_input.text().strip(),
            'zone': zone_input.text().strip(),
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

    dialog.show()
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

    dialog.show()
    return dialog
