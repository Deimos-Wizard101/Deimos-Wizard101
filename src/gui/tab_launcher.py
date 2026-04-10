import os

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from src.gui.commands import GUICommand, GUICommandType
from src.gui.helpers import (
    centered_label,
    launcher_icon_btn,
    launcher_small_icon_btn,
    spinning_loader_widget,
)


def build_launcher_tab(ctx):
    tab = QWidget()
    launcher_layout = QVBoxLayout(tab)
    launcher_layout.setContentsMargins(4, 4, 4, 4)
    launcher_layout.setSpacing(4)

    tl = ctx.tl
    send_queue = ctx.send_queue
    svgs = ctx.svgs

    _hover_rgba = "rgba(255,255,255,15)" if ctx.theme in ("black", "dark") else "rgba(0,0,0,15)"
    _launcher_list_style = (
        "QListWidget::item {"
        "  background: transparent;"
        "  border-radius: 4px;"
        "  padding: 2px;"
        "  margin: 1px 2px;"
        "}"
        "QListWidget::item:hover {"
        f"  background-color: {_hover_rgba};"
        "}"
        "QListWidget::item:disabled {"
        "  background: transparent;"
        "}"
        "QScrollBar:vertical { width: 6px; background: transparent; }"
        "QScrollBar::handle:vertical { background: rgba(255,255,255,40); border-radius: 3px; min-height: 20px; }"
        "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }"
    )

    # --- Two-column layout ---
    columns_layout = QHBoxLayout()

    # ===== Left column: Saved Accounts =====
    left_col = QVBoxLayout()
    left_col.setSpacing(2)

    acct_header = QHBoxLayout()
    acct_header.addWidget(centered_label(tl("saved_accounts")), 1)
    left_col.addLayout(acct_header)

    account_list = QListWidget()
    account_list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
    account_list.setDefaultDropAction(Qt.DropAction.MoveAction)
    account_list.setStyleSheet(_launcher_list_style)
    ctx.widget_tags["AccountList"] = account_list

    def _on_account_rows_moved(*_args):
        nicknames = []

        for i in range(account_list.count()):
            item = account_list.item(i)
            w = account_list.itemWidget(item)

            if w:
                label = w.findChild(QLabel)

                if label:
                    nicknames.append(label.text())

        if nicknames:
            send_queue.put(GUICommand(GUICommandType.ReorderAccounts, nicknames))

    account_list.model().rowsMoved.connect(_on_account_rows_moved)
    left_col.addWidget(account_list, 1)

    columns_layout.addLayout(left_col, 1)

    # ===== Right column: Hooked Clients =====
    right_col = QVBoxLayout()
    right_col.setSpacing(2)

    hooked_header = QHBoxLayout()
    hooked_header.addWidget(centered_label(tl("hooked_clients")), 1)
    right_col.addLayout(hooked_header)

    hooked_clients_list = QListWidget()
    hooked_clients_list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
    hooked_clients_list.setDefaultDropAction(Qt.DropAction.MoveAction)
    hooked_clients_list.setStyleSheet(_launcher_list_style)
    ctx.widget_tags["HookedClientsList"] = hooked_clients_list
    right_col.addWidget(hooked_clients_list, 1)

    _hooking_handles = set()
    _last_hooked_data = {}

    columns_layout.addLayout(right_col, 1)
    launcher_layout.addLayout(columns_layout, 1)

    # --- Account dialog and helpers ---
    def _show_add_account_dialog():
        dlg = QDialog(ctx.window)
        dlg.setWindowTitle(tl("add_account"))
        dlg.setModal(True)
        dlg_layout = QVBoxLayout(dlg)

        nick_input = QLineEdit()
        nick_input.setPlaceholderText(tl("nickname"))
        dlg_layout.addWidget(QLabel(tl("nickname")))
        dlg_layout.addWidget(nick_input)

        save_btn = QPushButton(tl("save_account"))
        save_btn.setStyleSheet(ctx.btn_style)

        def _on_save():
            nick = nick_input.text().strip()

            if nick:
                send_queue.put(GUICommand(GUICommandType.SaveAccount, nick))
                dlg.accept()

        save_btn.clicked.connect(_on_save)
        dlg_layout.addWidget(save_btn)

        dlg.adjustSize()
        dlg.exec()

    def _build_account_item_widget(nickname: str, disabled: bool = False):
        row = QWidget(account_list)
        row.setStyleSheet("background: transparent;")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(2, 0, 2, 0)
        row_layout.setSpacing(4)

        cb = QCheckBox()
        row_layout.addWidget(cb)

        lbl = QLabel(nickname)
        lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        row_layout.addWidget(lbl, 1)

        if disabled:
            cb.setEnabled(False)
            cb.setChecked(False)
            lbl.setStyleSheet(
                "color: rgba(255,255,255,80);" if ctx.theme in ("black", "dark") else "color: rgba(0,0,0,80);"
            )
            lbl.setToolTip(tl("already_active"))

        def _delete_this():
            send_queue.put(GUICommand(GUICommandType.DeleteAccount, nickname))

        trash_btn = launcher_small_icon_btn(ctx, svgs["trash"], tl("remove_account"), _delete_this)
        row_layout.addWidget(trash_btn)

        return row

    def _populate_account_list(nicknames: list[str]):
        remember = ctx.settings and ctx.settings.get_setting("remember_chosen_clients")
        managed = ctx.widget_tags.get("managed_accounts", set())
        account_list.setUpdatesEnabled(False)
        account_list.clear()

        for nick in nicknames:
            item = QListWidgetItem()
            item.setSizeHint(QSize(0, 28))
            row_widget = _build_account_item_widget(nick, disabled=(nick in managed and not remember))
            account_list.addItem(item)
            account_list.setItemWidget(item, row_widget)

        account_list.setUpdatesEnabled(True)

    def _refresh_account_eligibility(managed_accounts):
        remember = ctx.settings and ctx.settings.get_setting("remember_chosen_clients")
        managed = set(managed_accounts)

        for i in range(account_list.count()):
            item = account_list.item(i)
            w = account_list.itemWidget(item)

            if not w:
                continue

            cb = w.findChild(QCheckBox)
            lbl = w.findChild(QLabel)

            if not cb or not lbl:
                continue

            nick = lbl.text()

            if nick in managed and not remember:
                cb.setEnabled(False)
                cb.setChecked(False)
                lbl.setStyleSheet(
                    "color: rgba(255,255,255,80);" if ctx.theme in ("black", "dark") else "color: rgba(0,0,0,80);"
                )
                lbl.setToolTip(tl("already_active"))

            else:
                cb.setEnabled(True)
                lbl.setStyleSheet("")
                lbl.setToolTip("")

    def _build_hooked_client_widget(info: dict):
        row = QWidget(hooked_clients_list)
        row.setStyleSheet("background: transparent;")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(2, 0, 2, 0)
        row_layout.setSpacing(4)

        title = info["title"]
        nick = info.get("account_nick")
        display = f"{title} ({nick})" if nick else title
        lbl = QLabel(display)
        lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        row_layout.addWidget(lbl, 1)

        handle = info["handle"]

        def _kill_this():
            send_queue.put(GUICommand(GUICommandType.KillClient, handle))

        kill_btn = launcher_small_icon_btn(ctx, svgs["kill_client"], tl("kill_client"), _kill_this)
        row_layout.addWidget(kill_btn)

        if nick:
            def _relaunch_this():
                send_queue.put(GUICommand(GUICommandType.RelaunchClient, (handle, nick)))

            relaunch_btn = launcher_small_icon_btn(ctx, svgs["relaunch"], tl("relaunch_client"), _relaunch_this)
            row_layout.addWidget(relaunch_btn)

        def _eject_this():
            send_queue.put(GUICommand(GUICommandType.UnhookClient, handle))

        eject_btn = launcher_small_icon_btn(ctx, svgs["eject"], tl("unhook_client"), _eject_this)
        row_layout.addWidget(eject_btn)

        return row

    def _build_unmanaged_client_widget(handle: int):
        row = QWidget(hooked_clients_list)
        row.setStyleSheet("background: transparent;")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(2, 0, 2, 0)
        row_layout.setSpacing(4)

        lbl = QLabel(f"Wizard101 ({handle})")
        lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        lbl.setStyleSheet(
            "color: rgba(255,255,255,120);" if ctx.theme in ("black", "dark") else "color: rgba(0,0,0,120);"
        )
        row_layout.addWidget(lbl, 1)

        def _kill_this():
            send_queue.put(GUICommand(GUICommandType.KillClient, handle))

        kill_btn = launcher_small_icon_btn(ctx, svgs["kill_client"], tl("kill_client"), _kill_this)
        row_layout.addWidget(kill_btn)

        def _hook_this():
            _hooking_handles.add(handle)
            _rebuild_hooked_clients_list()
            send_queue.put(GUICommand(GUICommandType.HookClient, handle))

        hook_btn = launcher_small_icon_btn(ctx, svgs["hook"], tl("hook_client"), _hook_this)
        row_layout.addWidget(hook_btn)

        return row

    def _build_hooking_client_widget(handle: int, nick: str = None):
        row = QWidget(hooked_clients_list)
        row.setStyleSheet("background: transparent;")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(2, 0, 2, 0)
        row_layout.setSpacing(4)

        display = nick if nick else f"Wizard101 ({handle})"
        lbl = QLabel(display)
        lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        lbl.setStyleSheet(
            "color: rgba(255,255,255,120);" if ctx.theme in ("black", "dark") else "color: rgba(0,0,0,120);"
        )
        row_layout.addWidget(lbl, 1)

        row_layout.addWidget(spinning_loader_widget(ctx))

        return row

    def _rebuild_hooked_clients_list():
        hooked_clients_list.setUpdatesEnabled(False)
        hooked_clients_list.clear()
        hooked = _last_hooked_data.get("hooked", [])
        unmanaged = _last_hooked_data.get("unmanaged", [])
        hooking_backend = set(_last_hooked_data.get("hooking", []))
        hooked_handle_set = {info["handle"] for info in hooked}

        for info in hooked:
            item = QListWidgetItem()
            item.setSizeHint(QSize(0, 28))
            h = info["handle"]

            if h in hooking_backend:
                item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                row_widget = _build_hooking_client_widget(h, info.get("account_nick"))

            else:
                item.setData(Qt.ItemDataRole.UserRole, h)
                row_widget = _build_hooked_client_widget(info)

            hooked_clients_list.addItem(item)
            hooked_clients_list.setItemWidget(item, row_widget)

        for h in list(_hooking_handles):
            if h not in hooked_handle_set:
                item = QListWidgetItem()
                item.setSizeHint(QSize(0, 28))
                item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                row_widget = _build_hooking_client_widget(h)
                hooked_clients_list.addItem(item)
                hooked_clients_list.setItemWidget(item, row_widget)

        remaining = [h for h in unmanaged if h not in _hooking_handles]

        if remaining:
            sep_item = QListWidgetItem()
            sep_item.setSizeHint(QSize(0, 20))
            sep_item.setFlags(Qt.ItemFlag.NoItemFlags)
            sep_widget = QWidget(hooked_clients_list)
            sep_widget.setStyleSheet("background: transparent;")
            sep_layout = QHBoxLayout(sep_widget)
            sep_layout.setContentsMargins(4, 2, 4, 2)
            sep_lbl = QLabel(tl("unmanaged_clients"))
            sep_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            sep_lbl.setStyleSheet(
                "color: rgba(255,255,255,80); font-size: 10px;"
                if ctx.theme in ("black", "dark")
                else "color: rgba(0,0,0,80); font-size: 10px;"
            )
            sep_layout.addWidget(sep_lbl, 1)
            hooked_clients_list.addItem(sep_item)
            hooked_clients_list.setItemWidget(sep_item, sep_widget)
            for handle in remaining:
                u_item = QListWidgetItem()
                u_item.setSizeHint(QSize(0, 28))
                u_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                u_widget = _build_unmanaged_client_widget(handle)
                hooked_clients_list.addItem(u_item)
                hooked_clients_list.setItemWidget(u_item, u_widget)

        hooked_clients_list.setUpdatesEnabled(True)

    def _on_hooked_rows_moved(*_args):
        handles = []

        for i in range(hooked_clients_list.count()):
            item = hooked_clients_list.item(i)
            handle = item.data(Qt.ItemDataRole.UserRole)

            if handle is not None:
                handles.append(handle)

        if handles:
            send_queue.put(GUICommand(GUICommandType.ReorderClients, handles))
            old_hooked = _last_hooked_data.get("hooked", [])
            handle_to_info = {info["handle"]: info for info in old_hooked}
            _last_hooked_data["hooked"] = [handle_to_info[h] for h in handles if h in handle_to_info]
            _rebuild_hooked_clients_list()

    hooked_clients_list.model().rowsMoved.connect(_on_hooked_rows_moved)

    # Launch & Login button
    def _launch_and_login():
        selected = []

        for i in range(account_list.count()):
            item = account_list.item(i)
            w = account_list.itemWidget(item)

            if w:
                cb = w.findChild(QCheckBox)
                lbl = w.findChild(QLabel)

                if cb and lbl and cb.isChecked():
                    selected.append(lbl.text())

        if selected:
            game_path = game_path_input.text().strip()
            send_queue.put(GUICommand(GUICommandType.LaunchInstance, (selected, game_path)))

    # Auto-detect game path
    _steam_path = r"C:\Program Files (x86)\Steam\steamapps\common\Wizard101"
    _default_path = r"C:\ProgramData\KingsIsle Entertainment\Wizard101"
    _detected_path = ""

    if os.path.isdir(_steam_path):
        _detected_path = _steam_path

    elif os.path.isdir(_default_path):
        _detected_path = _default_path

    game_path_input = QLineEdit(_detected_path)
    game_path_input.setReadOnly(True)
    game_path_input.setVisible(False)
    ctx.widget_tags["GamePath"] = game_path_input

    def _show_settings_dialog():
        dlg = QDialog(ctx.window)
        dlg.setWindowTitle(tl("settings"))
        dlg.setModal(True)
        dlg_layout = QVBoxLayout(dlg)
        dlg_layout.addWidget(QLabel(tl("game_path")))
        path_row = QHBoxLayout()
        path_input = QLineEdit(game_path_input.text())
        path_input.setReadOnly(True)
        path_row.addWidget(path_input)

        def _pick():
            path = QFileDialog.getExistingDirectory(ctx.window, tl("game_path"))

            if path:
                path_input.setText(path)
                game_path_input.setText(path)

        path_row.addWidget(launcher_icon_btn(ctx, svgs["folder"], tl("game_path"), _pick))
        dlg_layout.addLayout(path_row)
        dlg.adjustSize()
        dlg.exec()

    launcher_action_row = QHBoxLayout()
    launcher_action_row.addStretch()
    launcher_action_row.addWidget(
        ctx.registry.action_icon_btn(svgs["add"], tl("add_account"), lambda: _show_add_account_dialog())
    )
    launcher_action_row.addWidget(ctx.registry.action_icon_btn(svgs["play"], tl("launch_login"), _launch_and_login))
    launcher_action_row.addWidget(ctx.registry.action_icon_btn(svgs["gear"], tl("settings"), _show_settings_dialog))
    launcher_action_row.addStretch()
    launcher_layout.addLayout(launcher_action_row)

    # Request account list from backend on startup
    send_queue.put(GUICommand(GUICommandType.LoadAccounts))

    # Export state for the event loop
    ctx.exports["launcher"] = {
        "populate_account_list": _populate_account_list,
        "rebuild_hooked_clients_list": _rebuild_hooked_clients_list,
        "refresh_account_eligibility": _refresh_account_eligibility,
        "hooking_handles": _hooking_handles,
        "last_hooked_data": _last_hooked_data,
        "account_list": account_list,
    }

    return tab
