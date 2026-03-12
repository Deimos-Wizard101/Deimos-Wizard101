from enum import Enum, auto
import os
import queue
import re
import sys
import webbrowser
import pyperclip
from src.combat_objects import school_id_to_names
from src.paths import wizard_city_dance_game_path
from src.lang import load_lang
from src.utils import assign_pet_level
from threading import Thread

from loguru import logger
import ctypes

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTabWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QPushButton, QCheckBox, QLineEdit, QTextEdit,
    QPlainTextEdit, QComboBox, QGroupBox, QFrame, QDialog, QListWidget,
    QFileDialog, QSizePolicy, QSpacerItem,
)
from PyQt6.QtCore import QTimer, Qt, QSize, QMetaObject, Q_ARG, pyqtSlot
from PyQt6.QtGui import QPixmap, QIcon, QFont


def _resource_path(filename: str) -> str:
    """Resolve path for bundled resources (PyInstaller) or source directory."""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, filename)
    return filename


global console_sink


def terminate_thread(thread: Thread):
    if not thread.is_alive():
        return

    exc = ctypes.py_object(SystemExit)
    res = ctypes.pythonapi.PyThreadState_SetAsyncExc(
        ctypes.c_long(thread.ident), exc)
    if res == 0:
        raise ValueError("Invalid thread ID")
    elif res != 1:
        ctypes.pythonapi.PyThreadState_SetAsyncExc(thread.ident, None)
        raise SystemError("PyThreadState_SetAsyncExc failed")

class ToolClosedException(Exception):
    pass


class GUICommandType(Enum):
    # deimos <-> window
    Close = auto()
    AttemptedClose = auto()
    CloseFromBackend = auto()

    # window -> deimos
    ToggleOption = auto()
    Copy = auto()
    SelectEnemy = auto()

    Teleport = auto()
    CustomTeleport = auto()
    EntityTeleport = auto()

    XYZSync = auto()
    XPress = auto()

    GoToZone = auto()
    GoToWorld = auto()
    GoToBazaar = auto()

    RefillPotions = auto()

    AnchorCam = auto()
    SetCamPosition = auto()
    SetCamDistance = auto()

    ExecuteFlythrough = auto()
    KillFlythrough = auto()

    ExecuteBot = auto()
    KillBot = auto()

    SetPlaystyles = auto()

    SetScale = auto()

    # deimos -> window
    UpdateWindow = auto()
    UpdateWindowValues = auto()
    UpdateConsole = auto()
    CopyConsole = auto()

    ShowUITreePopup = auto()
    ShowEntityListPopup = auto()


class GUIKeys:
    toggle_speedhack = "togglespeedhack"
    toggle_combat = "togglecombat"
    toggle_dialogue = "toggledialogue"
    toggle_sigil = "togglesigil"
    toggle_questing = "toggle_questing"
    toggle_auto_pet = "toggleautopet"
    toggle_auto_potion = "toggleautopotion"
    toggle_freecam = "togglefreecam"
    toggle_camera_collision = "togglecameracollision"
    toggle_show_expanded_logs = "toggleshowexpandedlogs"

    hotkey_quest_tp = "hotkeyquesttp"
    hotkey_freecam_tp = "hotkeyfreecamtp"

    mass_hotkey_mass_tp = "masshotkeymasstp"
    mass_hotkey_xyz_sync = "masshotkeyxyzsync"
    mass_hotkey_x_press = "masshotkeyxpress"

    copy_position = "copyposition"
    copy_zone = "copyzone"
    copy_rotation = "copyrotation"
    copy_entity_list = "copyentitylist"
    copy_ui_tree = "copyuitree"
    copy_camera_position = "copycameraposition"
    copy_stats = "copystats"
    copy_camera_rotation = "copycamerarotation"
    copy_logs = "copylogs"

    button_custom_tp = "buttoncustomtp"
    button_entity_tp = "buttonentitytp"
    button_go_to_zone = "buttongotozone"
    button_mass_go_to_zone = "buttonmassgotozone"
    button_go_to_world = "buttongotoworld"
    button_mass_go_to_world = "buttonmassgotoworld"
    button_go_to_bazaar = "buttongotobazaar"
    button_mass_go_to_bazaar = "buttonmassgotobazaar"
    button_refill_potions = "buttonrefillpotions"
    button_mass_refill_potions = "buttonmassrefillpotions"
    button_set_camera_position = "buttonsetcameraposition"
    button_anchor = "buttonanchor"
    button_set_distance = "buttonsetdistance"
    button_view_stats = "buttonviewstats"
    button_swap_members = "buttonswapmembers"

    button_execute_flythrough = "buttonexecuteflythrough"
    button_kill_flythrough = "buttonkillflythrough"
    button_run_bot = "buttonrunbot"
    button_kill_bot = "buttonkillbot"
    button_set_playstyles = "buttonsetplaystyles"
    button_set_scale = "buttonsetscale"


class GUICommand:
    def __init__(self, com_type: GUICommandType, data=None):
        self.com_type = com_type
        self.data = data


class ConsoleTextEdit(QPlainTextEdit):
    """QPlainTextEdit subclass with thread-safe slots for log appending."""

    @pyqtSlot(str)
    def _append_log(self, text):
        current = self.toPlainText()
        if current:
            self.setPlainText(current + text)
        else:
            self.setPlainText(text)
        scrollbar = self.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    @pyqtSlot(str)
    def _set_log(self, text):
        self.setPlainText(text)
        scrollbar = self.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())


class PyQtSink:
    def __init__(self, console_widget: QPlainTextEdit):
        self.console_widget = console_widget
        self.buffer = []
        self.max_lines = 1000
        self.show_expanded_logs = False

    def copy(self):
        log_str = "```\n"
        for (line, _, _) in self.buffer:
            log_str += line
        pyperclip.copy(log_str + "```")
        logger.debug("Copied current logs.")

    def toggle_show_expanded_logs(self, override: bool | None = None):
        match override:
            case True | False:
                self.show_expanded_logs = override
            case _:
                self.show_expanded_logs = not self.show_expanded_logs

        match self.show_expanded_logs:
            case True:
                logger.debug("Console is now showing full log messages.")
            case _:
                logger.debug("Console is now truncating log messages.")

        self.refresh()

    def write(self, message):
        ansi_pattern = r'\033\[\d+m'
        clean_message = re.sub(ansi_pattern, '', message)

        split_msg = clean_message.split("|")
        if len(split_msg) < 3:
            for l in ["DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"]:
                if l in clean_message:
                    level = l
                    break
            else:
                level = "DEBUG"
        else:
            level = split_msg[1].lstrip().rstrip()

        def collapse_log(input: str) -> str:
            if "-" not in input:
                return input
            split_input = input.split("-")
            if len(split_input) < 4:
                return input
            return split_input[3].lstrip()

        truncated_message = level + " - " + collapse_log(clean_message)

        self.buffer.append((clean_message, truncated_message, level))
        if len(self.buffer) > self.max_lines:
            self.buffer.pop(0)

        try:
            message_to_write = clean_message if self.show_expanded_logs else truncated_message
            # Thread-safe: marshal to GUI thread via QMetaObject.invokeMethod
            QMetaObject.invokeMethod(self.console_widget, "_append_log",
                Qt.ConnectionType.QueuedConnection, Q_ARG(str, message_to_write))
        except Exception:
            pass

    def refresh(self):
        try:
            text = ""
            for clean, trunc, level in self.buffer:
                message_to_write = clean if self.show_expanded_logs else trunc
                text += message_to_write
            QMetaObject.invokeMethod(self.console_widget, "_set_log",
                Qt.ConnectionType.QueuedConnection, Q_ARG(str, text))
        except Exception:
            pass

    def get_buffer(self):
        return self.buffer


def _show_ui_tree_popup(parent, ui_tree_content):
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
    dialog.setWindowTitle("UI Tree")
    dialog.resize(700, 500)
    layout = QVBoxLayout(dialog)

    layout.addWidget(QLabel("Click the path needed to copy it to clipboard."))

    search_input = QLineEdit()
    search_input.setPlaceholderText("Search")
    layout.addWidget(search_input)

    listbox = QListWidget()
    listbox.addItems(ui_tree_list)
    layout.addWidget(listbox)

    def on_search(text):
        listbox.clear()
        filtered = [line for line in ui_tree_list if text.lower() in line.lower()]
        listbox.addItems(filtered)

    def on_select(item):
        if item:
            selected_line = item.text()
            if selected_line in path_dict:
                path = path_dict[selected_line]
                pyperclip.copy(str(path))
            else:
                pyperclip.copy(selected_line)
            dialog.close()

    search_input.textChanged.connect(on_search)
    listbox.itemClicked.connect(on_select)

    close_btn = QPushButton("Close")
    close_btn.clicked.connect(dialog.close)
    layout.addWidget(close_btn)

    dialog.show()


def _show_entity_list_popup(parent, entity_list_content):
    entity_list = entity_list_content.splitlines()

    dialog = QDialog(parent)
    dialog.setWindowTitle("Entity List")
    dialog.resize(700, 500)
    layout = QVBoxLayout(dialog)

    layout.addWidget(QLabel("Click the entity needed to copy the name and location to clipboard."))

    search_input = QLineEdit()
    search_input.setPlaceholderText("Search")
    layout.addWidget(search_input)

    listbox = QListWidget()
    listbox.addItems(entity_list)
    layout.addWidget(listbox)

    def on_search(text):
        listbox.clear()
        filtered = [line for line in entity_list if text.lower() in line.lower()]
        listbox.addItems(filtered)

    def on_select(item):
        if item:
            pyperclip.copy(item.text())
            dialog.close()

    search_input.textChanged.connect(on_search)
    listbox.itemClicked.connect(on_select)

    close_btn = QPushButton("Close")
    close_btn.clicked.connect(dialog.close)
    layout.addWidget(close_btn)

    dialog.show()


def manage_gui(send_queue: queue.Queue, recv_queue: queue.Queue, gui_theme, gui_text_color, gui_button_color, tool_name, tool_version, gui_on_top, langcode, gui_scale=1.0):
    tl = load_lang(langcode)

    # Set AppUserModelID so Windows uses our icon in taskbar/process list
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(f"deimos.{tool_name}")
    except Exception:
        pass

    # Qt6 handles DPI awareness natively — no need to call SetProcessDpiAwareness
    app = QApplication(sys.argv)

    _scale = float(gui_scale) if gui_scale else 1.0
    _vp_width = int(550 * _scale)
    _vp_height = int(450 * _scale)

    # Button color
    _hex = gui_button_color.lstrip('#') if isinstance(gui_button_color, str) else "4a019e"
    btn_r, btn_g, btn_b = int(_hex[0:2], 16), int(_hex[2:4], 16), int(_hex[4:6], 16)

    btn_style = (
        f"QPushButton {{"
        f"  background-color: rgb({btn_r},{btn_g},{btn_b});"
        f"  color: white;"
        f"  border: none;"
        f"  padding: 4px 8px;"
        f"  border-radius: 4px;"
        f"}}"
        f"QPushButton:hover {{"
        f"  background-color: rgb({min(btn_r+30,255)},{min(btn_g+30,255)},{min(btn_b+30,255)});"
        f"}}"
        f"QPushButton:pressed {{"
        f"  background-color: rgb({max(btn_r-20,0)},{max(btn_g-20,0)},{max(btn_b-20,0)});"
        f"}}"
    )

    link_style = (
        "QPushButton {"
        "  background-color: transparent;"
        "  color: rgb(100,149,237);"
        "  border: none;"
        "  padding: 2px;"
        "}"
        "QPushButton:hover {"
        "  background-color: rgb(50,50,80);"
        "}"
    )

    frame_style = (
        "QFrame {"
        "  border: 1px solid palette(mid);"
        "  border-radius: 4px;"
        "}"
    )

    window = QMainWindow()
    window.setWindowTitle(f'{tool_name} GUI v{tool_version}')
    window.setFixedSize(_vp_width, _vp_height)

    if gui_on_top:
        window.setWindowFlags(window.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)

    _ico_path = _resource_path("Deimos-logo.ico")
    if os.path.exists(_ico_path):
        window.setWindowIcon(QIcon(_ico_path))

    central = QWidget()
    window.setCentralWidget(central)
    main_layout = QVBoxLayout(central)
    main_layout.setContentsMargins(8, 8, 8, 8)
    main_layout.setSpacing(4)

    main_layout.addWidget(QLabel(tl('free_tool')))

    tabs = QTabWidget()
    main_layout.addWidget(tabs)

    # Widget tag registry for backend updates
    widget_tags = {}

    def styled_btn(label, callback=None):
        btn = QPushButton(label)
        btn.setStyleSheet(btn_style)
        if callback:
            btn.clicked.connect(callback)
        return btn

    # ==================== Callbacks ====================
    def toggle_callback(event_key):
        def cb():
            send_queue.put(GUICommand(GUICommandType.ToggleOption, event_key))
        return cb

    def copy_callback(event_key):
        def cb():
            send_queue.put(GUICommand(GUICommandType.Copy, event_key))
        return cb

    def teleport_callback(event_key):
        def cb():
            send_queue.put(GUICommand(GUICommandType.Teleport, event_key))
        return cb

    # ==================== Hotkeys Tab ====================
    hotkeys_tab = QWidget()
    hotkeys_layout = QHBoxLayout(hotkeys_tab)
    hotkeys_layout.setContentsMargins(4, 4, 4, 4)

    _hotkey_h = int(230 * _scale)

    # Toggles column
    toggles_frame = QFrame()
    toggles_frame.setStyleSheet(frame_style)
    toggles_frame.setFixedWidth(int(140 * _scale))
    toggles_frame.setFixedHeight(_hotkey_h)
    toggles_vbox = QVBoxLayout(toggles_frame)
    toggles_vbox.setContentsMargins(4, 4, 4, 4)
    toggles_vbox.setSpacing(2)
    toggles_vbox.addWidget(QLabel(tl('toggles')))

    toggles_data = [
        (tl('speedhack'), GUIKeys.toggle_speedhack),
        (tl('combat_toggle'), GUIKeys.toggle_combat),
        (tl('dialogue'), GUIKeys.toggle_dialogue),
        (tl('sigil'), GUIKeys.toggle_sigil),
        (tl('questing'), GUIKeys.toggle_questing),
        (tl('auto_pet'), GUIKeys.toggle_auto_pet),
        (tl('auto_potion'), GUIKeys.toggle_auto_potion),
    ]
    for name, key in toggles_data:
        row = QHBoxLayout()
        cb = QCheckBox()
        cb.setEnabled(False)
        widget_tags[f'{name}Status'] = cb
        row.addWidget(cb)
        btn = styled_btn(name, toggle_callback(key))
        btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        row.addWidget(btn)
        toggles_vbox.addLayout(row)

    toggles_vbox.addStretch()
    hotkeys_layout.addWidget(toggles_frame)

    # Hotkeys + Mass Hotkeys column
    hotkeys_frame = QFrame()
    hotkeys_frame.setStyleSheet(frame_style)
    hotkeys_frame.setFixedWidth(int(130 * _scale))
    hotkeys_frame.setFixedHeight(_hotkey_h)
    hk_vbox = QVBoxLayout(hotkeys_frame)
    hk_vbox.setContentsMargins(4, 4, 4, 4)
    hk_vbox.setSpacing(2)
    hk_vbox.addWidget(QLabel(tl('hotkeys_label')))

    hk_vbox.addWidget(styled_btn(tl('quest_tp'), teleport_callback(GUIKeys.hotkey_quest_tp)))
    hk_vbox.addWidget(styled_btn(tl('freecam'), toggle_callback(GUIKeys.toggle_freecam)))
    hk_vbox.addWidget(styled_btn(tl('freecam_tp'), teleport_callback(GUIKeys.hotkey_freecam_tp)))

    hk_vbox.addSpacing(4)
    hk_vbox.addWidget(QLabel(tl('mass_hotkeys')))

    hk_vbox.addWidget(styled_btn(tl('mass_tp'), teleport_callback(GUIKeys.mass_hotkey_mass_tp)))

    def xyz_sync_callback():
        send_queue.put(GUICommand(GUICommandType.XYZSync))
    hk_vbox.addWidget(styled_btn(tl('xyz_sync'), xyz_sync_callback))

    def x_press_callback():
        send_queue.put(GUICommand(GUICommandType.XPress))
    hk_vbox.addWidget(styled_btn(tl('x_press'), x_press_callback))

    hk_vbox.addStretch()
    hotkeys_layout.addWidget(hotkeys_frame)

    # Tool info panel
    info_widget = QWidget()
    info_layout = QVBoxLayout(info_widget)
    info_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
    info_layout.addSpacing(15)

    _logo_path = _resource_path("Deimos-logo.png")
    if os.path.exists(_logo_path):
        logo_label = QLabel()
        pixmap = QPixmap(_logo_path)
        if not pixmap.isNull():
            scaled = pixmap.scaledToHeight(int(80 * _scale), Qt.TransformationMode.SmoothTransformation)
            logo_label.setPixmap(scaled)
            logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            info_layout.addWidget(logo_label)

    version_label = QLabel(f"{tool_name} v{tool_version}")
    version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    info_layout.addWidget(version_label)

    discord_btn = QPushButton("discord.gg/59UrPJwYDm")
    discord_btn.setStyleSheet(link_style)
    discord_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    discord_btn.clicked.connect(lambda: webbrowser.open("https://discord.gg/59UrPJwYDm"))
    info_layout.addWidget(discord_btn, alignment=Qt.AlignmentFlag.AlignCenter)

    info_layout.addStretch()
    hotkeys_layout.addWidget(info_widget)

    tabs.addTab(hotkeys_tab, tl('hotkeys'))

    # ==================== Camera Tab ====================
    camera_tab = QWidget()
    cam_layout = QVBoxLayout(camera_tab)
    cam_layout.setContentsMargins(4, 4, 4, 4)
    cam_layout.setSpacing(4)
    cam_layout.addWidget(QLabel(tl('advanced_warning')))

    cam_inputs = {}

    # --- Position group: XYZ + Yaw/Roll/Pitch in a compact grid ---
    pos_group = QGroupBox(tl('set_camera_position'))
    pos_grid = QGridLayout(pos_group)
    pos_grid.setContentsMargins(6, 4, 6, 4)
    pos_grid.setHorizontalSpacing(4)
    pos_grid.setVerticalSpacing(2)

    for col, (placeholder, tag) in enumerate([('X', 'CamXInput'), ('Y', 'CamYInput'), ('Z', 'CamZInput'),
                                               (tl('yaw'), 'CamYawInput'), (tl('roll'), 'CamRollInput'), (tl('pitch'), 'CamPitchInput')]):
        inp = QLineEdit()
        inp.setPlaceholderText(placeholder)
        inp.setFixedWidth(70)
        cam_inputs[tag] = inp
        widget_tags[tag] = inp
        pos_grid.addWidget(inp, 0, col)

    def set_cam_pos_callback():
        inputs = [cam_inputs['CamXInput'].text(), cam_inputs['CamYInput'].text(), cam_inputs['CamZInput'].text(),
                  cam_inputs['CamYawInput'].text(), cam_inputs['CamRollInput'].text(), cam_inputs['CamPitchInput'].text()]
        if any(inputs):
            send_queue.put(GUICommand(GUICommandType.SetCamPosition, {
                'X': inputs[0], 'Y': inputs[1], 'Z': inputs[2],
                'Yaw': inputs[3], 'Roll': inputs[4], 'Pitch': inputs[5],
            }))

    pos_grid.addWidget(styled_btn(tl('set_camera_position'), set_cam_pos_callback), 0, 6)
    cam_layout.addWidget(pos_group)

    # --- Anchor + Distance in one row using two side-by-side groups ---
    mid_row = QHBoxLayout()
    mid_row.setSpacing(4)

    anchor_group = QGroupBox(tl('anchor'))
    anchor_lay = QHBoxLayout(anchor_group)
    anchor_lay.setContentsMargins(6, 4, 6, 4)
    cam_entity_input = QLineEdit()
    cam_entity_input.setPlaceholderText(tl('entity'))
    cam_entity_input.setMinimumWidth(80)
    cam_inputs['CamEntityInput'] = cam_entity_input
    widget_tags['CamEntityInput'] = cam_entity_input
    anchor_lay.addWidget(cam_entity_input, 1)

    def anchor_callback():
        send_queue.put(GUICommand(GUICommandType.AnchorCam, cam_entity_input.text()))
    anchor_lay.addWidget(styled_btn(tl('anchor'), anchor_callback))
    anchor_lay.addWidget(styled_btn(tl('toggle_camera_collision'), toggle_callback(GUIKeys.toggle_camera_collision)))
    mid_row.addWidget(anchor_group)

    dist_group = QGroupBox(tl('set_distance'))
    dist_lay = QHBoxLayout(dist_group)
    dist_lay.setContentsMargins(6, 4, 6, 4)
    for placeholder, tag in [(tl('distance'), 'CamDistanceInput'), (tl('min'), 'CamMinInput'), (tl('max'), 'CamMaxInput')]:
        inp = QLineEdit()
        inp.setPlaceholderText(placeholder)
        inp.setFixedWidth(65)
        cam_inputs[tag] = inp
        widget_tags[tag] = inp
        dist_lay.addWidget(inp)

    def set_distance_callback():
        inputs = [cam_inputs['CamDistanceInput'].text(), cam_inputs['CamMinInput'].text(), cam_inputs['CamMaxInput'].text()]
        if any(inputs):
            send_queue.put(GUICommand(GUICommandType.SetCamDistance, {
                "Distance": inputs[0], "Min": inputs[1], "Max": inputs[2],
            }))
    dist_lay.addWidget(styled_btn(tl('set_distance'), set_distance_callback))
    mid_row.addWidget(dist_group)

    cam_layout.addLayout(mid_row)

    # --- Copy buttons ---
    copy_row = QHBoxLayout()
    copy_row.addWidget(styled_btn(tl('copy_camera_position'), copy_callback(GUIKeys.copy_camera_position)))
    copy_row.addWidget(styled_btn(tl('copy_camera_rotation'), copy_callback(GUIKeys.copy_camera_rotation)))
    copy_row.addStretch()
    cam_layout.addLayout(copy_row)

    cam_layout.addStretch()
    tabs.addTab(camera_tab, tl('camera'))

    # ==================== Dev Utils Tab ====================
    dev_tab = QWidget()
    dev_layout = QVBoxLayout(dev_tab)
    dev_layout.setContentsMargins(4, 4, 4, 4)
    dev_layout.setSpacing(4)
    dev_layout.addWidget(QLabel(tl('advanced_warning')))

    dev_inputs = {}

    # --- Teleport group ---
    tp_group = QGroupBox(tl('tp_utils'))
    tp_lay = QVBoxLayout(tp_group)
    tp_lay.setContentsMargins(6, 4, 6, 4)
    tp_lay.setSpacing(2)

    # Coordinate TP: compact row with placeholder text instead of labels
    coord_row = QHBoxLayout()
    coord_row.setSpacing(3)
    for placeholder, tag, w in [('X', 'XInput', 50), ('Y', 'YInput', 50), ('Z', 'ZInput', 50), (tl('yaw'), 'YawInput', 50)]:
        inp = QLineEdit()
        inp.setPlaceholderText(placeholder)
        inp.setFixedWidth(w)
        dev_inputs[tag] = inp
        widget_tags[tag] = inp
        coord_row.addWidget(inp)

    def custom_tp_callback():
        tp_vals = [dev_inputs['XInput'].text(), dev_inputs['YInput'].text(), dev_inputs['ZInput'].text(), dev_inputs['YawInput'].text()]
        if any(tp_vals):
            send_queue.put(GUICommand(GUICommandType.CustomTeleport, {
                'X': tp_vals[0], 'Y': tp_vals[1], 'Z': tp_vals[2], 'Yaw': tp_vals[3],
            }))

    coord_row.addWidget(styled_btn(tl('custom_tp'), custom_tp_callback))
    coord_row.addStretch()
    tp_lay.addLayout(coord_row)

    # Entity TP
    ent_row = QHBoxLayout()
    ent_row.setSpacing(3)
    entity_tp_input = QLineEdit()
    entity_tp_input.setPlaceholderText(tl('entity_name'))
    dev_inputs['EntityTPInput'] = entity_tp_input
    widget_tags['EntityTPInput'] = entity_tp_input
    ent_row.addWidget(entity_tp_input, 1)

    def entity_tp_callback():
        val = entity_tp_input.text()
        if val:
            send_queue.put(GUICommand(GUICommandType.EntityTeleport, val))

    ent_row.addWidget(styled_btn(tl('entity_tp'), entity_tp_callback))
    tp_lay.addLayout(ent_row)

    dev_layout.addWidget(tp_group)

    # --- Navigation group ---
    nav_group = QGroupBox(tl('dev_utils_label'))
    nav_lay = QVBoxLayout(nav_group)
    nav_lay.setContentsMargins(6, 4, 6, 4)
    nav_lay.setSpacing(2)

    # Zone + World on the same row
    zw_row = QHBoxLayout()
    zw_row.setSpacing(3)

    zone_input = QLineEdit()
    zone_input.setPlaceholderText(tl('zone_name'))
    zone_input.setFixedWidth(100)
    dev_inputs['ZoneInput'] = zone_input
    widget_tags['ZoneInput'] = zone_input
    zw_row.addWidget(zone_input)

    def go_to_zone_callback():
        val = zone_input.text()
        if val:
            send_queue.put(GUICommand(GUICommandType.GoToZone, (False, str(val))))

    def mass_go_to_zone_callback():
        val = zone_input.text()
        if val:
            send_queue.put(GUICommand(GUICommandType.GoToZone, (True, str(val))))

    zw_row.addWidget(styled_btn(tl('go_to_zone'), go_to_zone_callback))
    zw_row.addWidget(styled_btn(tl('mass_go_to_zone'), mass_go_to_zone_callback))

    zw_row.addSpacing(8)

    worlds = ['WizardCity', 'Krokotopia', 'Marleybone', 'MooShu', 'DragonSpire', 'Grizzleheim', 'Celestia', 'Wysteria', 'Zafaria', 'Avalon', 'Azteca', 'Khrysalis', 'Polaris', 'Mirage', 'Empyrea', 'Karamelle', 'Lemuria']
    world_combo = QComboBox()
    world_combo.addItems(worlds)
    world_combo.setCurrentText('WizardCity')
    world_combo.setFixedWidth(110)
    dev_inputs['WorldInput'] = world_combo
    widget_tags['WorldInput'] = world_combo
    zw_row.addWidget(world_combo)

    def go_to_world_callback():
        val = world_combo.currentText()
        if val:
            send_queue.put(GUICommand(GUICommandType.GoToWorld, (False, val)))

    def mass_go_to_world_callback():
        val = world_combo.currentText()
        if val:
            send_queue.put(GUICommand(GUICommandType.GoToWorld, (True, val)))

    zw_row.addWidget(styled_btn(tl('go_to_world'), go_to_world_callback))
    zw_row.addWidget(styled_btn(tl('mass_go_to_world'), mass_go_to_world_callback))
    zw_row.addStretch()
    nav_lay.addLayout(zw_row)

    # Quick actions: Bazaar + Potions + Entity/UI buttons
    actions_row = QHBoxLayout()
    actions_row.setSpacing(3)

    def go_to_bazaar_callback():
        send_queue.put(GUICommand(GUICommandType.GoToBazaar, False))

    def mass_go_to_bazaar_callback():
        send_queue.put(GUICommand(GUICommandType.GoToBazaar, True))

    def refill_potions_callback():
        send_queue.put(GUICommand(GUICommandType.RefillPotions, False))

    def mass_refill_potions_callback():
        send_queue.put(GUICommand(GUICommandType.RefillPotions, True))

    actions_row.addWidget(styled_btn(tl('go_to_bazaar'), go_to_bazaar_callback))
    actions_row.addWidget(styled_btn(tl('mass_go_to_bazaar'), mass_go_to_bazaar_callback))
    actions_row.addWidget(styled_btn(tl('refill_potions'), refill_potions_callback))
    actions_row.addWidget(styled_btn(tl('mass_refill_potions'), mass_refill_potions_callback))
    actions_row.addStretch()
    nav_lay.addLayout(actions_row)

    # Entity list + UI tree buttons
    inspect_row = QHBoxLayout()
    inspect_row.setSpacing(3)
    inspect_row.addWidget(styled_btn(tl('available_entities'), copy_callback(GUIKeys.copy_entity_list)))
    inspect_row.addWidget(styled_btn(tl('available_paths'), copy_callback(GUIKeys.copy_ui_tree)))
    inspect_row.addStretch()
    nav_lay.addLayout(inspect_row)

    dev_layout.addWidget(nav_group)

    dev_layout.addStretch()
    tabs.addTab(dev_tab, tl('dev_utils'))

    # ==================== Stats Tab ====================
    stats_tab = QWidget()
    stats_layout = QVBoxLayout(stats_tab)
    stats_layout.setContentsMargins(4, 4, 4, 4)
    stats_layout.addWidget(QLabel(tl('advanced_warning')))

    stats_inputs = {}
    indices = [str(i + 1) for i in range(12)]

    idx_row = QHBoxLayout()
    idx_row.addWidget(QLabel(tl('caster_target_indices') + ':'))
    enemy_combo = QComboBox()
    enemy_combo.addItems(indices)
    enemy_combo.setCurrentText('1')
    enemy_combo.setFixedWidth(100)
    stats_inputs['EnemyInput'] = enemy_combo
    widget_tags['EnemyInput'] = enemy_combo
    idx_row.addWidget(enemy_combo)

    ally_combo = QComboBox()
    ally_combo.addItems(indices)
    ally_combo.setCurrentText('1')
    ally_combo.setFixedWidth(100)
    stats_inputs['AllyInput'] = ally_combo
    widget_tags['AllyInput'] = ally_combo
    idx_row.addWidget(ally_combo)
    idx_row.addStretch()
    stats_layout.addLayout(idx_row)

    schools = ['Fire', 'Ice', 'Storm', 'Myth', 'Life', 'Death', 'Balance', 'Star', 'Sun', 'Moon', 'Shadow']
    dmg_row = QHBoxLayout()
    dmg_row.addWidget(QLabel(tl('dmg') + ':'))
    damage_input = QLineEdit()
    damage_input.setFixedWidth(60)
    stats_inputs['DamageInput'] = damage_input
    widget_tags['DamageInput'] = damage_input
    dmg_row.addWidget(damage_input)

    dmg_row.addWidget(QLabel(tl('school') + ':'))
    school_combo = QComboBox()
    school_combo.addItems(schools)
    school_combo.setCurrentText('Fire')
    school_combo.setFixedWidth(80)
    stats_inputs['SchoolInput'] = school_combo
    widget_tags['SchoolInput'] = school_combo
    dmg_row.addWidget(school_combo)

    dmg_row.addWidget(QLabel(tl('crit') + ':'))
    crit_check = QCheckBox()
    crit_check.setChecked(True)
    stats_inputs['CritStatus'] = crit_check
    widget_tags['CritStatus'] = crit_check
    dmg_row.addWidget(crit_check)

    def view_stats_callback():
        enemy_index = re.sub(r'[^0-9]', '', str(enemy_combo.currentText()))
        ally_index = re.sub(r'[^0-9]', '', str(ally_combo.currentText()))
        base_damage = re.sub(r'[^0-9]', '', str(damage_input.text()))
        school_id: int = school_id_to_names[school_combo.currentText()]
        send_queue.put(GUICommand(GUICommandType.SelectEnemy, (
            int(enemy_index) if enemy_index else 1,
            int(ally_index) if ally_index else 1,
            base_damage, school_id,
            crit_check.isChecked(),
            force_school_check.isChecked()
        )))

    dmg_row.addWidget(styled_btn(tl('view_stats'), view_stats_callback))
    dmg_row.addWidget(styled_btn(tl('copy_stats'), copy_callback(GUIKeys.copy_stats)))
    dmg_row.addStretch()
    stats_layout.addLayout(dmg_row)

    stat_viewer = QTextEdit()
    stat_viewer.setPlainText(tl('no_client_selected'))
    stat_viewer.setReadOnly(True)
    stat_viewer.setFixedHeight(120)
    widget_tags['stat_viewer'] = stat_viewer
    stats_layout.addWidget(stat_viewer)

    swap_row = QHBoxLayout()

    def swap_members_callback():
        enemy_val = enemy_combo.currentText()
        ally_val = ally_combo.currentText()
        enemy_combo.setCurrentText(ally_val)
        ally_combo.setCurrentText(enemy_val)

    swap_row.addWidget(styled_btn(tl('swap_members'), swap_members_callback))
    swap_row.addWidget(QLabel(tl('force_school_damage') + ':'))
    force_school_check = QCheckBox()
    stats_inputs['ForceSchoolStatus'] = force_school_check
    widget_tags['ForceSchoolStatus'] = force_school_check
    swap_row.addWidget(force_school_check)
    swap_row.addStretch()
    stats_layout.addLayout(swap_row)

    stats_layout.addStretch()
    tabs.addTab(stats_tab, tl('stats'))

    # ==================== Flythrough Tab ====================
    flythrough_tab = QWidget()
    fly_layout = QVBoxLayout(flythrough_tab)
    fly_layout.setContentsMargins(4, 4, 4, 4)
    fly_layout.addWidget(QLabel(tl('advanced_warning')))

    flythrough_editor = QTextEdit()
    flythrough_editor.setFixedHeight(150)
    widget_tags['flythrough_creator'] = flythrough_editor
    fly_layout.addWidget(flythrough_editor)

    fly_btn_row = QHBoxLayout()

    def flythrough_import():
        filepath, _ = QFileDialog.getOpenFileName(window, "Import Flythrough", "", "Text Files (*.txt)")
        if filepath:
            try:
                with open(filepath) as f:
                    flythrough_editor.setPlainText(f.read())
            except Exception:
                pass

    def flythrough_export():
        filepath, _ = QFileDialog.getSaveFileName(window, "Export Flythrough", "flythrough.txt", "Text Files (*.txt)")
        if filepath:
            try:
                with open(filepath, 'w') as f:
                    f.write(flythrough_editor.toPlainText())
            except Exception:
                pass

    def execute_flythrough_callback():
        send_queue.put(GUICommand(GUICommandType.ExecuteFlythrough, flythrough_editor.toPlainText()))

    def kill_flythrough_callback():
        send_queue.put(GUICommand(GUICommandType.KillFlythrough))

    fly_btn_row.addWidget(styled_btn(tl('import_flythrough'), flythrough_import))
    fly_btn_row.addWidget(styled_btn(tl('export_flythrough'), flythrough_export))
    fly_btn_row.addWidget(styled_btn(tl('execute_flythrough'), execute_flythrough_callback))
    fly_btn_row.addWidget(styled_btn(tl('kill_flythrough'), kill_flythrough_callback))
    fly_btn_row.addStretch()
    fly_layout.addLayout(fly_btn_row)

    fly_layout.addStretch()
    tabs.addTab(flythrough_tab, tl('flythrough'))

    # ==================== Bot Tab ====================
    bot_tab = QWidget()
    bot_layout = QVBoxLayout(bot_tab)
    bot_layout.setContentsMargins(4, 4, 4, 4)
    bot_layout.addWidget(QLabel(tl('advanced_warning')))

    bot_editor = QTextEdit()
    bot_editor.setFixedHeight(150)
    widget_tags['bot_creator'] = bot_editor
    bot_layout.addWidget(bot_editor)

    bot_btn_row = QHBoxLayout()

    def bot_import():
        filepath, _ = QFileDialog.getOpenFileName(window, "Import Bot", "", "Text Files (*.txt)")
        if filepath:
            try:
                with open(filepath) as f:
                    bot_editor.setPlainText(f.read())
            except Exception:
                pass

    def bot_export():
        filepath, _ = QFileDialog.getSaveFileName(window, "Export Bot", "bot.txt", "Text Files (*.txt)")
        if filepath:
            try:
                with open(filepath, 'w') as f:
                    f.write(bot_editor.toPlainText())
            except Exception:
                pass

    def run_bot_callback():
        send_queue.put(GUICommand(GUICommandType.ExecuteBot, bot_editor.toPlainText()))

    def kill_bot_callback():
        send_queue.put(GUICommand(GUICommandType.KillBot))

    bot_btn_row.addWidget(styled_btn(tl('import_bot'), bot_import))
    bot_btn_row.addWidget(styled_btn(tl('export_bot'), bot_export))
    bot_btn_row.addWidget(styled_btn(tl('run_bot'), run_bot_callback))
    bot_btn_row.addWidget(styled_btn(tl('kill_bot'), kill_bot_callback))
    bot_btn_row.addStretch()
    bot_layout.addLayout(bot_btn_row)

    bot_layout.addStretch()
    tabs.addTab(bot_tab, tl('bot'))

    # ==================== Combat Tab ====================
    combat_tab = QWidget()
    combat_layout = QVBoxLayout(combat_tab)
    combat_layout.setContentsMargins(4, 4, 4, 4)
    combat_layout.addWidget(QLabel(tl('advanced_warning')))

    combat_editor = QTextEdit()
    combat_editor.setFixedHeight(150)
    widget_tags['combat_config'] = combat_editor
    combat_layout.addWidget(combat_editor)

    combat_btn_row = QHBoxLayout()

    def combat_import():
        filepath, _ = QFileDialog.getOpenFileName(window, "Import Playstyle", "", "Text Files (*.txt)")
        if filepath:
            try:
                with open(filepath) as f:
                    combat_editor.setPlainText(f.read())
            except Exception:
                pass

    def combat_export():
        filepath, _ = QFileDialog.getSaveFileName(window, "Export Playstyle", "playstyle.txt", "Text Files (*.txt)")
        if filepath:
            try:
                with open(filepath, 'w') as f:
                    f.write(combat_editor.toPlainText())
            except Exception:
                pass

    def set_playstyles_callback():
        send_queue.put(GUICommand(GUICommandType.SetPlaystyles, combat_editor.toPlainText()))

    combat_btn_row.addWidget(styled_btn(tl('import_playstyle'), combat_import))
    combat_btn_row.addWidget(styled_btn(tl('export_playstyle'), combat_export))
    combat_btn_row.addWidget(styled_btn(tl('set_playstyles'), set_playstyles_callback))
    combat_btn_row.addStretch()
    combat_layout.addLayout(combat_btn_row)

    combat_layout.addStretch()
    tabs.addTab(combat_tab, tl('combat'))

    # ==================== Misc Tab ====================
    misc_tab = QWidget()
    misc_layout = QVBoxLayout(misc_tab)
    misc_layout.setContentsMargins(4, 4, 4, 4)
    misc_layout.addWidget(QLabel(tl('advanced_warning')))

    scale_row = QHBoxLayout()
    scale_row.addWidget(QLabel(tl('scale') + ':'))
    scale_input = QLineEdit()
    scale_input.setFixedWidth(80)
    widget_tags['scale'] = scale_input
    scale_row.addWidget(scale_input)

    def set_scale_callback():
        send_queue.put(GUICommand(GUICommandType.SetScale, scale_input.text()))

    scale_row.addWidget(styled_btn(tl('set_scale'), set_scale_callback))
    scale_row.addStretch()
    misc_layout.addLayout(scale_row)

    pet_worlds = ['WizardCity', 'Krokotopia', 'Marleybone', 'Mooshu', 'Dragonspyre']
    pet_row = QHBoxLayout()
    pet_row.addWidget(QLabel(tl('select_pet_world')))
    pet_combo = QComboBox()
    pet_combo.addItems(pet_worlds)
    pet_combo.setCurrentText('WizardCity')
    pet_combo.setFixedWidth(120)
    widget_tags['PetWorldInput'] = pet_combo

    def pet_world_callback(text):
        if text != wizard_city_dance_game_path[-1]:
            assign_pet_level(text)

    pet_combo.currentTextChanged.connect(pet_world_callback)
    pet_row.addWidget(pet_combo)
    pet_row.addStretch()
    misc_layout.addLayout(pet_row)

    misc_layout.addStretch()
    tabs.addTab(misc_tab, tl('misc'))

    # ==================== Console Tab ====================
    console_tab = QWidget()
    console_layout = QVBoxLayout(console_tab)
    console_layout.setContentsMargins(4, 4, 4, 4)
    console_layout.addWidget(QLabel(tl('console_support')))

    console_text = ConsoleTextEdit()
    console_text.setReadOnly(True)
    console_text.setFixedHeight(150)
    widget_tags['-CONSOLE-'] = console_text
    console_layout.addWidget(console_text)

    console_btn_row = QHBoxLayout()
    console_btn_row.addWidget(styled_btn(tl('collapse_expand_logs'), toggle_callback(GUIKeys.toggle_show_expanded_logs)))
    console_btn_row.addWidget(styled_btn(tl('copy_logs'), copy_callback(GUIKeys.copy_logs)))
    console_btn_row.addStretch()
    console_layout.addLayout(console_btn_row)

    console_layout.addStretch()
    tabs.addTab(console_tab, tl('console'))

    # ==================== Client Info Footer ====================
    main_layout.addWidget(QFrame(frameShape=QFrame.Shape.HLine))

    footer_grid = QGridLayout()
    footer_grid.setContentsMargins(0, 0, 0, 0)

    title_label = QLabel(tl('client') + ': ')
    widget_tags['Title'] = title_label
    footer_grid.addWidget(title_label, 0, 0)

    zone_label = QLabel(tl('zone') + ': ')
    widget_tags['Zone'] = zone_label
    footer_grid.addWidget(zone_label, 1, 0)
    zone_copy = styled_btn("Copy", copy_callback(GUIKeys.copy_zone))
    zone_copy.setFixedSize(50, 20)
    footer_grid.addWidget(zone_copy, 1, 1)

    xyz_label = QLabel("Position (XYZ): ")
    widget_tags['xyz'] = xyz_label
    footer_grid.addWidget(xyz_label, 2, 0)
    pos_copy = styled_btn("Copy", copy_callback(GUIKeys.copy_position))
    pos_copy.setFixedSize(50, 20)
    footer_grid.addWidget(pos_copy, 2, 1)

    pry_label = QLabel("Orientation (PRY): ")
    widget_tags['pry'] = pry_label
    footer_grid.addWidget(pry_label, 3, 0)
    rot_copy = styled_btn("Copy", copy_callback(GUIKeys.copy_rotation))
    rot_copy.setFixedSize(50, 20)
    footer_grid.addWidget(rot_copy, 3, 1)

    main_layout.addLayout(footer_grid)

    # ==================== Console Sink ====================
    global console_sink
    console_psg = PyQtSink(console_text)
    console_sink = logger.add(console_psg, colorize=True)

    # ==================== License Popup ====================
    license_dialog = QDialog(window)
    license_dialog.setWindowTitle(tl('license_title'))
    license_dialog.setFixedSize(500, 120)
    license_dialog.setModal(True)
    ld_layout = QVBoxLayout(license_dialog)
    ld_layout.addWidget(QLabel(tl('license_text')))
    ok_btn = QPushButton("OK")
    ok_btn.clicked.connect(license_dialog.close)
    ld_layout.addWidget(ok_btn)
    license_dialog.show()
    QTimer.singleShot(5000, license_dialog.close)

    # ==================== Font Scale ====================
    if _scale != 1.0:
        font = app.font()
        font.setPointSizeF(font.pointSizeF() * _scale)
        app.setFont(font)

    # ==================== Close Handling ====================
    close_accepted = [False]
    original_close = window.closeEvent

    def close_event(event):
        if close_accepted[0]:
            event.accept()
            return
        event.ignore()
        send_queue.put(GUICommand(GUICommandType.AttemptedClose))

    window.closeEvent = close_event

    # ==================== Event Loop Timer ====================
    def poll_queue():
        try:
            while True:
                com = recv_queue.get_nowait()
                match com.com_type:
                    case GUICommandType.Close:
                        close_accepted[0] = True
                        window.close()
                        app.quit()
                        return

                    case GUICommandType.CloseFromBackend:
                        send_queue.put(GUICommand(GUICommandType.AttemptedClose))

                    case GUICommandType.UpdateWindow:
                        tag = com.data[0]
                        value = com.data[1]
                        widget = widget_tags.get(tag)
                        if widget is not None:
                            if isinstance(widget, QCheckBox):
                                widget.setChecked(value == 'Enabled')
                            elif isinstance(widget, QLabel):
                                widget.setText(str(value))
                            elif isinstance(widget, QLineEdit):
                                widget.setText(str(value))
                            elif isinstance(widget, QComboBox):
                                widget.setCurrentText(str(value))
                            elif isinstance(widget, (QTextEdit, QPlainTextEdit)):
                                if isinstance(widget, QPlainTextEdit):
                                    widget.setPlainText(str(value))
                                else:
                                    widget.setPlainText(str(value))

                    case GUICommandType.UpdateWindowValues:
                        tag = com.data[0]
                        values = com.data[1]
                        widget = widget_tags.get(tag)
                        if widget is not None and isinstance(widget, QComboBox):
                            widget.clear()
                            widget.addItems(values)

                    case GUICommandType.UpdateConsole:
                        console_psg.toggle_show_expanded_logs()

                    case GUICommandType.ShowUITreePopup:
                        _show_ui_tree_popup(window, com.data)

                    case GUICommandType.ShowEntityListPopup:
                        _show_entity_list_popup(window, com.data)

                    case GUICommandType.CopyConsole:
                        console_psg.copy()

        except queue.Empty:
            pass

    timer = QTimer()
    timer.timeout.connect(poll_queue)
    timer.start(16)

    window.show()
    app.exec()

    # After app exits, signal backend
    if not close_accepted[0]:
        send_queue.put(GUICommand(GUICommandType.AttemptedClose))
        import time
        timeout = 30
        start = time.time()
        while time.time() - start < timeout:
            try:
                com = recv_queue.get_nowait()
                if com.com_type == GUICommandType.Close:
                    break
            except queue.Empty:
                pass
            time.sleep(0.1)
