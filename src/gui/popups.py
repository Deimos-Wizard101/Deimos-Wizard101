import re

import pyperclip
from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.gui.commands import GUICommand, GUICommandType


def show_ui_tree_popup(parent, send_queue, ui_tree_content, text_dict, copy_btn_factory, tl=None):
    ui_tree_list = ui_tree_content.splitlines()

    path_dict = {}
    path_stack = []

    for line in ui_tree_list:
        indent = len(line) - len(line.lstrip("-"))
        clean_line = line.lstrip("- ")

        name_match = re.search(r"\[(.*?)\]", clean_line)
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
    dialog.setWindowTitle(tl("ui_tree") if tl else "UI Tree")
    dialog.resize(700, 500)
    layout = QVBoxLayout(dialog)

    layout.addWidget(QLabel(tl("ui_tree_hint") if tl else "Click the path needed to copy it to clipboard."))

    search_input = QLineEdit()
    search_input.setPlaceholderText(tl("search") if tl else "Search")
    layout.addWidget(search_input)

    listbox = QListWidget()
    listbox.setMouseTracking(True)
    layout.addWidget(listbox)

    def _populate(lines):
        listbox.clear()

        for line in lines:
            item = QListWidgetItem()
            path = path_dict.get(line)
            item.setData(Qt.ItemDataRole.UserRole, {"path": path, "text": text_dict.get(line)})

            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(4, 0, 4, 0)

            label = QLabel(line)
            row_layout.addWidget(label, stretch=1)

            if line in text_dict:
                text_to_copy = text_dict[line]
                btn = copy_btn_factory(lambda _=False, t=text_to_copy: pyperclip.copy(t))
                _prefix = (
                    tl("copy_text").format(text_to_copy[:50] + ("..." if len(text_to_copy) > 50 else ""))
                    if tl
                    else f"Copy text: {text_to_copy[:50]}{'...' if len(text_to_copy) > 50 else ''}"
                )
                btn.setToolTip(_prefix)
                row_layout.addWidget(btn)

            item.setSizeHint(row_widget.sizeHint())
            listbox.addItem(item)
            listbox.setItemWidget(item, row_widget)

    _populate(ui_tree_list)

    def on_search(text):
        filtered = [line for line in ui_tree_list if text.lower() in line.lower()]
        _populate(filtered)

    def on_hover(item):
        if item:
            data = item.data(Qt.ItemDataRole.UserRole)

            if data and data.get("path"):
                send_queue.put(GUICommand(GUICommandType.HighlightUIWindow, data["path"]))

    def _clear_highlight():
        send_queue.put(GUICommand(GUICommandType.ClearHighlight))

    def on_select(item):
        if item:
            data = item.data(Qt.ItemDataRole.UserRole)

            if data and data.get("path"):
                pyperclip.copy(str(data["path"]))

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

    close_btn = QPushButton(tl("close") if tl else "Close")
    close_btn.clicked.connect(dialog.close)
    layout.addWidget(close_btn)

    dialog.show()


def show_entity_list_popup(parent, send_queue, widget_tags, tabs, dev_tab, camera_tab, tl=None):
    dialog = QDialog(parent)
    dialog.setWindowTitle(tl("entity_list") if tl else "Entity List")
    dialog.resize(450, 400)
    layout = QVBoxLayout(dialog)

    layout.addWidget(QLabel(tl("entity_list_hint") if tl else "Click to copy. Right-click for TP / Camera options."))

    search_input = QLineEdit()
    search_input.setPlaceholderText(tl("search") if tl else "Search")
    layout.addWidget(search_input)

    listbox = QListWidget()
    listbox.setMouseTracking(True)
    layout.addWidget(listbox)

    all_entities = []

    def _populate(entries):
        listbox.clear()

        for entry in entries:
            item = QListWidgetItem(entry["display"])
            item.setData(
                Qt.ItemDataRole.UserRole,
                {
                    "x": entry["x"],
                    "y": entry["y"],
                    "z": entry["z"],
                    "height": entry.get("height", 170.0),
                    "gid": entry.get("gid", 0),
                    "distance": entry.get("distance", 0.0),
                },
            )
            listbox.addItem(item)

    def update_entities(entity_data):
        nonlocal all_entities
        all_entities = entity_data
        search_text = search_input.text()

        if search_text:
            filtered = [e for e in all_entities if search_text.lower() in e["display"].lower()]
            _populate(filtered)

        else:
            _populate(all_entities)

    dialog.update_entities = update_entities

    def on_search(text):
        if text:
            filtered = [e for e in all_entities if text.lower() in e["display"].lower()]
            _populate(filtered)

        else:
            _populate(all_entities)

    def on_hover(item):
        if item:
            data = item.data(Qt.ItemDataRole.UserRole)

            if data:
                send_queue.put(
                    GUICommand(GUICommandType.HighlightEntity, (data["x"], data["y"], data["z"], data["height"]))
                )

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

        gid_str = str(data.get("gid", ""))

        menu = QMenu(listbox)
        tp_action = menu.addAction(tl("tp_to_entity") if tl else "Teleport to Entity")
        anchor_action = menu.addAction(tl("anchor_cam_to_entity") if tl else "Anchor Camera to Entity")

        action = menu.exec(listbox.mapToGlobal(pos))

        if action == tp_action:
            gid_widget = widget_tags.get("EntityTPGIDInput")

            if gid_widget:
                gid_widget.setText(gid_str)

            tabs.setCurrentWidget(dev_tab)
            send_queue.put(GUICommand(GUICommandType.ClearHighlight))
            dialog.close()

        elif action == anchor_action:
            gid_widget = widget_tags.get("CamEntityGIDInput")

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

    close_btn = QPushButton(tl("close") if tl else "Close")
    close_btn.clicked.connect(dialog.close)
    layout.addWidget(close_btn)

    send_queue.put(GUICommand(GUICommandType.StartEntityStream))

    dialog.show()
    return dialog
