from enum import Enum, auto
import gettext
import queue
import re
import dearpygui.dearpygui as dpg
import pyperclip
from src.combat_objects import school_id_to_names
from src.paths import wizard_city_dance_game_path
from src.utils import assign_pet_level
from threading import Thread

import re
from loguru import logger
import ctypes

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


class DpgSink:
    def __init__(self, console_tag):
        self.console_tag = console_tag
        self.buffer = []
        self.max_lines = 1000
        self.show_expanded_logs = False

        self.level_colors = {
            "DEBUG": (150, 150, 150, 255),
            "INFO": (255, 255, 255, 255),
            "SUCCESS": (255, 255, 255, 255),
            "WARNING": (255, 255, 0, 255),
            "ERROR": (255, 0, 0, 255),
            "CRITICAL": (255, 255, 255, 255),
        }

        # For SUCCESS/CRITICAL we'll just use text color (bg not directly supported in dpg input_text)
        self.level_special_colors = {
            "SUCCESS": (0, 255, 0, 255),
            "CRITICAL": (255, 50, 50, 255),
        }

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
            for l, c in self.level_colors.items():
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
            current = dpg.get_value(self.console_tag)
            if current:
                dpg.set_value(self.console_tag, current + message_to_write)
            else:
                dpg.set_value(self.console_tag, message_to_write)
        except Exception:
            pass

    def refresh(self):
        try:
            text = ""
            for clean, trunc, level in self.buffer:
                message_to_write = clean if self.show_expanded_logs else trunc
                text += message_to_write
            dpg.set_value(self.console_tag, text)
        except Exception:
            pass

    def get_buffer(self):
        return self.buffer


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


# TODO:
# - inherit from StrEnum in 3.11 to make this nicer
# - fix naming convention, it's inconsistent
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



def show_ui_tree_popup(ui_tree_content):
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

    popup_tag = "ui_tree_popup"
    listbox_tag = "ui_tree_listbox"
    search_tag = "ui_tree_search"

    if dpg.does_item_exist(popup_tag):
        dpg.delete_item(popup_tag)

    def on_search(sender, app_data):
        search_term = app_data.lower()
        filtered = [line for line in ui_tree_list if search_term in line.lower()]
        dpg.configure_item(listbox_tag, items=filtered)

    def on_select(sender, app_data):
        if app_data:
            selected_line = app_data
            if selected_line in path_dict:
                path = path_dict[selected_line]
                pyperclip.copy(str(path))
            else:
                pyperclip.copy(selected_line)
            dpg.delete_item(popup_tag)

    def on_close(sender, app_data):
        dpg.delete_item(popup_tag)

    with dpg.window(label="UI Tree", tag=popup_tag, width=700, height=500, on_close=on_close):
        dpg.add_text("Click the path needed to copy it to clipboard.")
        dpg.add_input_text(label="Search", tag=search_tag, callback=on_search, on_enter=False)
        dpg.add_listbox(items=ui_tree_list, tag=listbox_tag, num_items=20, callback=on_select, width=-1)
        dpg.add_button(label="Close", callback=on_close)


def show_entity_list_popup(entity_list_content):
    entity_list = entity_list_content.splitlines()

    popup_tag = "entity_list_popup"
    listbox_tag = "entity_list_listbox"
    search_tag = "entity_list_search"

    if dpg.does_item_exist(popup_tag):
        dpg.delete_item(popup_tag)

    def on_search(sender, app_data):
        search_term = app_data.lower()
        filtered = [line for line in entity_list if search_term in line.lower()]
        dpg.configure_item(listbox_tag, items=filtered)

    def on_select(sender, app_data):
        if app_data:
            pyperclip.copy(app_data)
            dpg.delete_item(popup_tag)

    def on_close(sender, app_data):
        dpg.delete_item(popup_tag)

    with dpg.window(label="Entity List", tag=popup_tag, width=700, height=500, on_close=on_close):
        dpg.add_text("Click the entity needed to copy the name and location to clipboard.")
        dpg.add_input_text(label="Search", tag=search_tag, callback=on_search, on_enter=False)
        dpg.add_listbox(items=entity_list, tag=listbox_tag, num_items=20, callback=on_select, width=-1)
        dpg.add_button(label="Close", callback=on_close)


def manage_gui(send_queue: queue.Queue, recv_queue: queue.Queue, gui_theme, gui_text_color, gui_button_color, tool_name, tool_version, gui_on_top, langcode, gui_scale=1.0):
    if langcode != 'en':
        translate = gettext.translation("messages", "locale", languages=[langcode])
        tl = translate.gettext
    else:
        gettext.bindtextdomain('messages', 'locale')
        gettext.textdomain('messages')
        tl = gettext.gettext

    dpg.create_context()

    # Apply GUI scale from config (default 1.0, set in Deimos-config.ini under [gui] scale=)
    _scale = float(gui_scale) if gui_scale else 1.0
    _vp_width = int(550 * _scale)
    _vp_height = int(450 * _scale)

    dpg.create_viewport(title=f'{tool_name} GUI v{tool_version}', width=_vp_width, height=_vp_height, always_on_top=gui_on_top, resizable=False)

    # Theme setup
    with dpg.theme() as global_theme:
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 4)
            dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 8, 8)
            dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 8, 4)

    # Button theme
    _hex = gui_button_color.lstrip('#') if isinstance(gui_button_color, str) else "4a019e"
    btn_r, btn_g, btn_b = int(_hex[0:2], 16), int(_hex[2:4], 16), int(_hex[4:6], 16)
    with dpg.theme() as button_theme:
        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Button, (btn_r, btn_g, btn_b, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (min(btn_r+30, 255), min(btn_g+30, 255), min(btn_b+30, 255), 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, (max(btn_r-20, 0), max(btn_g-20, 0), max(btn_b-20, 0), 255))

    dpg.bind_theme(global_theme)

    global console_sink
    global console_psg

    # License popup (auto-close after 5 seconds)
    license_popup_tag = "license_popup"
    license_start_frame = [0]

    def close_license(sender=None, app_data=None):
        if dpg.does_item_exist(license_popup_tag):
            dpg.delete_item(license_popup_tag)

    with dpg.window(label=tl('License Agreement'), tag=license_popup_tag, modal=True, no_close=False, on_close=close_license, width=500, height=120):
        dpg.add_text(tl('Deimos will always be free and open-source.\nBy using Deimos, you agree to the GPL v3 license agreement.\nIf you bought this, you got scammed!'))
        dpg.add_button(label="OK", callback=close_license)

    # Callbacks
    def toggle_callback(event_key):
        def cb(sender, app_data):
            send_queue.put(GUICommand(GUICommandType.ToggleOption, event_key))
        return cb

    def copy_callback(event_key):
        def cb(sender, app_data):
            send_queue.put(GUICommand(GUICommandType.Copy, event_key))
        return cb

    def teleport_callback(event_key):
        def cb(sender, app_data):
            send_queue.put(GUICommand(GUICommandType.Teleport, event_key))
        return cb

    def custom_tp_callback(sender, app_data):
        tp_inputs = [dpg.get_value('XInput'), dpg.get_value('YInput'), dpg.get_value('ZInput'), dpg.get_value('YawInput')]
        if any(tp_inputs):
            send_queue.put(GUICommand(GUICommandType.CustomTeleport, {
                'X': tp_inputs[0], 'Y': tp_inputs[1], 'Z': tp_inputs[2], 'Yaw': tp_inputs[3],
            }))

    def entity_tp_callback(sender, app_data):
        val = dpg.get_value('EntityTPInput')
        if val:
            send_queue.put(GUICommand(GUICommandType.EntityTeleport, val))

    def xyz_sync_callback(sender, app_data):
        send_queue.put(GUICommand(GUICommandType.XYZSync))

    def x_press_callback(sender, app_data):
        send_queue.put(GUICommand(GUICommandType.XPress))

    def anchor_callback(sender, app_data):
        send_queue.put(GUICommand(GUICommandType.AnchorCam, dpg.get_value('CamEntityInput')))

    def set_cam_pos_callback(sender, app_data):
        inputs = [dpg.get_value('CamXInput'), dpg.get_value('CamYInput'), dpg.get_value('CamZInput'),
                  dpg.get_value('CamYawInput'), dpg.get_value('CamRollInput'), dpg.get_value('CamPitchInput')]
        if any(inputs):
            send_queue.put(GUICommand(GUICommandType.SetCamPosition, {
                'X': inputs[0], 'Y': inputs[1], 'Z': inputs[2],
                'Yaw': inputs[3], 'Roll': inputs[4], 'Pitch': inputs[5],
            }))

    def set_distance_callback(sender, app_data):
        inputs = [dpg.get_value('CamDistanceInput'), dpg.get_value('CamMinInput'), dpg.get_value('CamMaxInput')]
        if any(inputs):
            send_queue.put(GUICommand(GUICommandType.SetCamDistance, {
                "Distance": inputs[0], "Min": inputs[1], "Max": inputs[2],
            }))

    def go_to_zone_callback(sender, app_data):
        val = dpg.get_value('ZoneInput')
        if val:
            send_queue.put(GUICommand(GUICommandType.GoToZone, (False, str(val))))

    def mass_go_to_zone_callback(sender, app_data):
        val = dpg.get_value('ZoneInput')
        if val:
            send_queue.put(GUICommand(GUICommandType.GoToZone, (True, str(val))))

    def go_to_world_callback(sender, app_data):
        val = dpg.get_value('WorldInput')
        if val:
            send_queue.put(GUICommand(GUICommandType.GoToWorld, (False, val)))

    def mass_go_to_world_callback(sender, app_data):
        val = dpg.get_value('WorldInput')
        if val:
            send_queue.put(GUICommand(GUICommandType.GoToWorld, (True, val)))

    def go_to_bazaar_callback(sender, app_data):
        send_queue.put(GUICommand(GUICommandType.GoToBazaar, False))

    def mass_go_to_bazaar_callback(sender, app_data):
        send_queue.put(GUICommand(GUICommandType.GoToBazaar, True))

    def refill_potions_callback(sender, app_data):
        send_queue.put(GUICommand(GUICommandType.RefillPotions, False))

    def mass_refill_potions_callback(sender, app_data):
        send_queue.put(GUICommand(GUICommandType.RefillPotions, True))

    def execute_flythrough_callback(sender, app_data):
        send_queue.put(GUICommand(GUICommandType.ExecuteFlythrough, dpg.get_value('flythrough_creator')))

    def kill_flythrough_callback(sender, app_data):
        send_queue.put(GUICommand(GUICommandType.KillFlythrough))

    def run_bot_callback(sender, app_data):
        send_queue.put(GUICommand(GUICommandType.ExecuteBot, dpg.get_value('bot_creator')))

    def kill_bot_callback(sender, app_data):
        send_queue.put(GUICommand(GUICommandType.KillBot))

    def set_playstyles_callback(sender, app_data):
        send_queue.put(GUICommand(GUICommandType.SetPlaystyles, dpg.get_value('combat_config')))

    def set_scale_callback(sender, app_data):
        send_queue.put(GUICommand(GUICommandType.SetScale, dpg.get_value('scale')))

    def view_stats_callback(sender, app_data):
        enemy_index = re.sub(r'[^0-9]', '', str(dpg.get_value('EnemyInput')))
        ally_index = re.sub(r'[^0-9]', '', str(dpg.get_value('AllyInput')))
        base_damage = re.sub(r'[^0-9]', '', str(dpg.get_value('DamageInput')))
        school_id: int = school_id_to_names[dpg.get_value('SchoolInput')]
        send_queue.put(GUICommand(GUICommandType.SelectEnemy, (
            int(enemy_index) if enemy_index else 1,
            int(ally_index) if ally_index else 1,
            base_damage, school_id,
            dpg.get_value('CritStatus'),
            dpg.get_value('ForceSchoolStatus')
        )))

    def swap_members_callback(sender, app_data):
        enemy_val = dpg.get_value('EnemyInput')
        ally_val = dpg.get_value('AllyInput')
        dpg.set_value('EnemyInput', ally_val)
        dpg.set_value('AllyInput', enemy_val)

    def pet_world_callback(sender, app_data):
        if app_data != wizard_city_dance_game_path[-1]:
            assign_pet_level(app_data)

    # File dialog callbacks
    def _import_file(content_tag):
        def callback(sender, app_data):
            if app_data and 'file_path_name' in app_data:
                filepath = app_data['file_path_name']
                try:
                    with open(filepath) as f:
                        dpg.set_value(content_tag, f.read())
                except Exception:
                    pass
        return callback

    def _export_file(content_tag):
        def callback(sender, app_data):
            if app_data and 'file_path_name' in app_data:
                filepath = app_data['file_path_name']
                try:
                    with open(filepath, 'w') as f:
                        f.write(dpg.get_value(content_tag))
                except Exception:
                    pass
        return callback

    # File dialogs
    with dpg.file_dialog(directory_selector=False, show=False, callback=_import_file('flythrough_creator'), tag="flythrough_import_dialog", width=350, height=280):
        dpg.add_file_extension(".txt", color=(255, 255, 255, 255))
    with dpg.file_dialog(directory_selector=False, show=False, callback=_export_file('flythrough_creator'), tag="flythrough_export_dialog", width=350, height=280, default_filename="flythrough.txt"):
        dpg.add_file_extension(".txt", color=(255, 255, 255, 255))
    with dpg.file_dialog(directory_selector=False, show=False, callback=_import_file('bot_creator'), tag="bot_import_dialog", width=350, height=280):
        dpg.add_file_extension(".txt", color=(255, 255, 255, 255))
    with dpg.file_dialog(directory_selector=False, show=False, callback=_export_file('bot_creator'), tag="bot_export_dialog", width=350, height=280, default_filename="bot.txt"):
        dpg.add_file_extension(".txt", color=(255, 255, 255, 255))
    with dpg.file_dialog(directory_selector=False, show=False, callback=_import_file('combat_config'), tag="combat_import_dialog", width=350, height=280):
        dpg.add_file_extension(".txt", color=(255, 255, 255, 255))
    with dpg.file_dialog(directory_selector=False, show=False, callback=_export_file('combat_config'), tag="combat_export_dialog", width=350, height=280, default_filename="playstyle.txt"):
        dpg.add_file_extension(".txt", color=(255, 255, 255, 255))

    # Main window
    with dpg.window(tag="primary_window"):
        dpg.add_text(tl('Deimos will always be a free tool. If you paid for this, you got scammed!'))

        with dpg.tab_bar():
            # ==================== Hotkeys Tab ====================
            with dpg.tab(label=tl('Hotkeys')):
                with dpg.group(horizontal=True):
                    # Toggles frame
                    _hotkey_h = int(230 * _scale)
                    with dpg.child_window(width=140, height=_hotkey_h, border=True):
                        dpg.add_text(tl('Toggles'))
                        dpg.add_separator()
                        toggles = [
                            (tl('Speedhack'), GUIKeys.toggle_speedhack),
                            (tl('Combat'), GUIKeys.toggle_combat),
                            (tl('Dialogue'), GUIKeys.toggle_dialogue),
                            (tl('Sigil'), GUIKeys.toggle_sigil),
                            (tl('Questing'), GUIKeys.toggle_questing),
                            (tl('Auto Pet'), GUIKeys.toggle_auto_pet),
                            (tl('Auto Potion'), GUIKeys.toggle_auto_potion),
                        ]
                        for name, key in toggles:
                            with dpg.group(horizontal=True):
                                dpg.add_checkbox(tag=f'{name}Status', default_value=False, enabled=False)
                                dpg.add_button(label=name, callback=toggle_callback(key), width=-1)
                                dpg.bind_item_theme(dpg.last_item(), button_theme)

                    # Hotkeys + Mass Hotkeys stacked
                    with dpg.child_window(width=130, height=_hotkey_h, border=True):
                        dpg.add_text(tl('Hotkeys'))
                        dpg.add_separator()
                        dpg.add_button(label=tl('Quest TP'), callback=teleport_callback(GUIKeys.hotkey_quest_tp), width=-1)
                        dpg.bind_item_theme(dpg.last_item(), button_theme)
                        dpg.add_button(label=tl('Freecam'), callback=toggle_callback(GUIKeys.toggle_freecam), width=-1)
                        dpg.bind_item_theme(dpg.last_item(), button_theme)
                        dpg.add_button(label=tl('Freecam TP'), callback=teleport_callback(GUIKeys.hotkey_freecam_tp), width=-1)
                        dpg.bind_item_theme(dpg.last_item(), button_theme)
                        dpg.add_spacer(height=4)
                        dpg.add_text(tl('Mass Hotkeys'))
                        dpg.add_separator()
                        dpg.add_button(label=tl('Mass TP'), callback=teleport_callback(GUIKeys.mass_hotkey_mass_tp), width=-1)
                        dpg.bind_item_theme(dpg.last_item(), button_theme)
                        dpg.add_button(label=tl('XYZ Sync'), callback=xyz_sync_callback, width=-1)
                        dpg.bind_item_theme(dpg.last_item(), button_theme)
                        dpg.add_button(label=tl('X Press'), callback=x_press_callback, width=-1)
                        dpg.bind_item_theme(dpg.last_item(), button_theme)

                    # Tool info panel — fixed width, content centered via indent
                    import webbrowser
                    with dpg.child_window(width=-1, height=_hotkey_h, border=False, tag="tool_info_panel"):
                        dpg.add_spacer(height=15)

                        _info_center_items = []  # (item_tag, approx_width) — centered in render loop
                        try:
                            _logo_w, _logo_h, _, _logo_data = dpg.load_image("Deimos-logo.png")
                            with dpg.texture_registry():
                                dpg.add_static_texture(width=_logo_w, height=_logo_h, default_value=_logo_data, tag="logo_texture")
                            dpg.add_image("logo_texture", tag="logo_image")
                            _info_center_items.append(("logo_image", _logo_w))
                        except Exception:
                            dpg.add_text("(logo)")

                        dpg.add_spacer(height=6)

                        _version_text = f"{tool_name} v{tool_version}"
                        _version_tag = dpg.add_text(_version_text)
                        _info_center_items.append((_version_tag, len(_version_text) * 7))

                        dpg.add_spacer(height=2)

                        _discord_label = "discord.gg/59UrPJwYDm"
                        def _open_discord(_s, _a):
                            webbrowser.open("https://discord.gg/59UrPJwYDm")
                        dpg.add_button(label=_discord_label, callback=_open_discord, tag="discord_link")
                        _info_center_items.append(("discord_link", len(_discord_label) * 7 + 16))
                        with dpg.theme() as link_theme:
                            with dpg.theme_component(dpg.mvButton):
                                dpg.add_theme_color(dpg.mvThemeCol_Button, (0, 0, 0, 0))
                                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (50, 50, 80, 255))
                                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, (0, 0, 0, 0))
                                dpg.add_theme_color(dpg.mvThemeCol_Text, (100, 149, 237, 255))
                        dpg.bind_item_theme("discord_link", link_theme)

            # ==================== Camera Tab ====================
            with dpg.tab(label=tl('Camera')):
                dpg.add_text(tl('The utils below are for advanced users and no support will be given on them.'))
                dpg.add_separator()
                with dpg.group(horizontal=True):
                    dpg.add_text('X:'); dpg.add_input_text(tag='CamXInput', width=80)
                    dpg.add_text('Y:'); dpg.add_input_text(tag='CamYInput', width=80)
                    dpg.add_text('Z:'); dpg.add_input_text(tag='CamZInput', width=80)
                    dpg.add_button(label=tl('Set Camera Position'), callback=set_cam_pos_callback)
                    dpg.bind_item_theme(dpg.last_item(), button_theme)
                with dpg.group(horizontal=True):
                    dpg.add_text(tl('Yaw') + ':'); dpg.add_input_text(tag='CamYawInput', width=80)
                    dpg.add_text(tl('Roll') + ':'); dpg.add_input_text(tag='CamRollInput', width=80)
                    dpg.add_text(tl('Pitch') + ':'); dpg.add_input_text(tag='CamPitchInput', width=80)
                with dpg.group(horizontal=True):
                    dpg.add_text(tl('Entity') + ':'); dpg.add_input_text(tag='CamEntityInput', width=150)
                    dpg.add_button(label=tl('Anchor'), callback=anchor_callback)
                    dpg.bind_item_theme(dpg.last_item(), button_theme)
                    dpg.add_button(label=tl('Toggle Camera Collision'), callback=toggle_callback(GUIKeys.toggle_camera_collision))
                    dpg.bind_item_theme(dpg.last_item(), button_theme)
                with dpg.group(horizontal=True):
                    dpg.add_text(tl('Distance') + ':'); dpg.add_input_text(tag='CamDistanceInput', width=80)
                    dpg.add_text(tl('Min') + ':'); dpg.add_input_text(tag='CamMinInput', width=80)
                    dpg.add_text(tl('Max') + ':'); dpg.add_input_text(tag='CamMaxInput', width=80)
                    dpg.add_button(label=tl('Set Distance'), callback=set_distance_callback)
                    dpg.bind_item_theme(dpg.last_item(), button_theme)
                with dpg.group(horizontal=True):
                    dpg.add_button(label=tl('Copy Camera Position'), callback=copy_callback(GUIKeys.copy_camera_position))
                    dpg.bind_item_theme(dpg.last_item(), button_theme)
                    dpg.add_button(label=tl('Copy Camera Rotation'), callback=copy_callback(GUIKeys.copy_camera_rotation))
                    dpg.bind_item_theme(dpg.last_item(), button_theme)

            # ==================== Dev Utils Tab ====================
            with dpg.tab(label=tl('Dev Utils')):
                dpg.add_text(tl('The utils below are for advanced users and no support will be given on them.'))
                dpg.add_separator()
                # TP Utils
                dpg.add_text(tl('TP Utils'))
                with dpg.group(horizontal=True):
                    dpg.add_text('X:'); dpg.add_input_text(tag='XInput', width=55)
                    dpg.add_text('Y:'); dpg.add_input_text(tag='YInput', width=55)
                    dpg.add_text('Z:'); dpg.add_input_text(tag='ZInput', width=60)
                    dpg.add_text(tl('Yaw') + ':'); dpg.add_input_text(tag='YawInput', width=55)
                    dpg.add_button(label=tl('Custom TP'), callback=custom_tp_callback)
                    dpg.bind_item_theme(dpg.last_item(), button_theme)
                with dpg.group(horizontal=True):
                    dpg.add_text(tl('Entity Name') + ':'); dpg.add_input_text(tag='EntityTPInput', width=250)
                    dpg.add_button(label=tl('Entity TP'), callback=entity_tp_callback)
                    dpg.bind_item_theme(dpg.last_item(), button_theme)
                dpg.add_separator()

                # Dev Utils
                dpg.add_text(tl('Dev Utils'))
                with dpg.group(horizontal=True):
                    dpg.add_button(label=tl('Available Entities'), callback=copy_callback(GUIKeys.copy_entity_list))
                    dpg.bind_item_theme(dpg.last_item(), button_theme)
                    dpg.add_button(label=tl('Available Paths'), callback=copy_callback(GUIKeys.copy_ui_tree))
                    dpg.bind_item_theme(dpg.last_item(), button_theme)
                with dpg.group(horizontal=True):
                    dpg.add_text(tl('Zone Name') + ':'); dpg.add_input_text(tag='ZoneInput', width=120)
                    dpg.add_button(label=tl('Go To Zone'), callback=go_to_zone_callback)
                    dpg.bind_item_theme(dpg.last_item(), button_theme)
                    dpg.add_button(label=tl('Mass Go To Zone'), callback=mass_go_to_zone_callback)
                    dpg.bind_item_theme(dpg.last_item(), button_theme)
                worlds = ['WizardCity', 'Krokotopia', 'Marleybone', 'MooShu', 'DragonSpire', 'Grizzleheim', 'Celestia', 'Wysteria', 'Zafaria', 'Avalon', 'Azteca', 'Khrysalis', 'Polaris', 'Mirage', 'Empyrea', 'Karamelle', 'Lemuria']
                with dpg.group(horizontal=True):
                    dpg.add_text(tl('World Name') + ':')
                    dpg.add_combo(items=worlds, default_value='WizardCity', tag='WorldInput', width=120)
                    dpg.add_button(label=tl('Go To World'), callback=go_to_world_callback)
                    dpg.bind_item_theme(dpg.last_item(), button_theme)
                    dpg.add_button(label=tl('Mass Go To World'), callback=mass_go_to_world_callback)
                    dpg.bind_item_theme(dpg.last_item(), button_theme)
                with dpg.group(horizontal=True):
                    dpg.add_button(label=tl('Go To Bazaar'), callback=go_to_bazaar_callback)
                    dpg.bind_item_theme(dpg.last_item(), button_theme)
                    dpg.add_button(label=tl('Mass Go To Bazaar'), callback=mass_go_to_bazaar_callback)
                    dpg.bind_item_theme(dpg.last_item(), button_theme)
                    dpg.add_button(label=tl('Refill Potions'), callback=refill_potions_callback)
                    dpg.bind_item_theme(dpg.last_item(), button_theme)
                    dpg.add_button(label=tl('Mass Refill Potions'), callback=mass_refill_potions_callback)
                    dpg.bind_item_theme(dpg.last_item(), button_theme)

            # ==================== Stat Viewer Tab ====================
            with dpg.tab(label=tl('Stats')):
                dpg.add_text(tl('The utils below are for advanced users and no support will be given on them.'))
                dpg.add_separator()
                indices = [str(i + 1) for i in range(12)]
                with dpg.group(horizontal=True):
                    dpg.add_text(tl('Caster/Target Indices') + ':')
                    dpg.add_combo(items=indices, default_value='1', tag='EnemyInput', width=100)
                    dpg.add_combo(items=indices, default_value='1', tag='AllyInput', width=100)
                schools = ['Fire', 'Ice', 'Storm', 'Myth', 'Life', 'Death', 'Balance', 'Star', 'Sun', 'Moon', 'Shadow']
                with dpg.group(horizontal=True):
                    dpg.add_text(tl('Dmg') + ':'); dpg.add_input_text(tag='DamageInput', width=60, default_value='')
                    dpg.add_text(tl('School') + ':'); dpg.add_combo(items=schools, default_value='Fire', tag='SchoolInput', width=80)
                    dpg.add_text(tl('Crit') + ':'); dpg.add_checkbox(tag='CritStatus', default_value=True)
                    dpg.add_button(label=tl('View Stats'), callback=view_stats_callback)
                    dpg.bind_item_theme(dpg.last_item(), button_theme)
                    dpg.add_button(label=tl('Copy Stats'), callback=copy_callback(GUIKeys.copy_stats))
                    dpg.bind_item_theme(dpg.last_item(), button_theme)
                dpg.add_input_text(tag='stat_viewer', default_value=tl('No client has been selected.'), multiline=True, width=-1, height=120, readonly=True)
                with dpg.group(horizontal=True):
                    dpg.add_button(label=tl('Swap Members'), callback=swap_members_callback)
                    dpg.bind_item_theme(dpg.last_item(), button_theme)
                    dpg.add_text(tl('Force School Damage') + ':')
                    dpg.add_checkbox(tag='ForceSchoolStatus')

            # ==================== Flythrough Tab ====================
            with dpg.tab(label=tl('Flythrough')):
                dpg.add_text(tl('The utils below are for advanced users and no support will be given on them.'))
                dpg.add_separator()
                dpg.add_input_text(tag='flythrough_creator', multiline=True, width=-1, height=150)
                with dpg.group(horizontal=True):
                    dpg.add_button(label=tl('Import Flythrough'), callback=lambda: dpg.show_item("flythrough_import_dialog"))
                    dpg.bind_item_theme(dpg.last_item(), button_theme)
                    dpg.add_button(label=tl('Export Flythrough'), callback=lambda: dpg.show_item("flythrough_export_dialog"))
                    dpg.bind_item_theme(dpg.last_item(), button_theme)
                    dpg.add_button(label=tl('Execute Flythrough'), callback=execute_flythrough_callback)
                    dpg.bind_item_theme(dpg.last_item(), button_theme)
                    dpg.add_button(label=tl('Kill Flythrough'), callback=kill_flythrough_callback)
                    dpg.bind_item_theme(dpg.last_item(), button_theme)

            # ==================== Bot Tab ====================
            with dpg.tab(label=tl('Bot')):
                dpg.add_text(tl('The utils below are for advanced users and no support will be given on them.'))
                dpg.add_separator()
                dpg.add_input_text(tag='bot_creator', multiline=True, width=-1, height=150)
                with dpg.group(horizontal=True):
                    dpg.add_button(label='Import Bot', callback=lambda: dpg.show_item("bot_import_dialog"))
                    dpg.bind_item_theme(dpg.last_item(), button_theme)
                    dpg.add_button(label='Export Bot', callback=lambda: dpg.show_item("bot_export_dialog"))
                    dpg.bind_item_theme(dpg.last_item(), button_theme)
                    dpg.add_button(label=tl('Run Bot'), callback=run_bot_callback)
                    dpg.bind_item_theme(dpg.last_item(), button_theme)
                    dpg.add_button(label=tl('Kill Bot'), callback=kill_bot_callback)
                    dpg.bind_item_theme(dpg.last_item(), button_theme)

            # ==================== Combat Tab ====================
            with dpg.tab(label=tl('Combat')):
                dpg.add_text(tl('The utils below are for advanced users and no support will be given on them.'))
                dpg.add_separator()
                dpg.add_input_text(tag='combat_config', multiline=True, width=-1, height=150)
                with dpg.group(horizontal=True):
                    dpg.add_button(label='Import Playstyle', callback=lambda: dpg.show_item("combat_import_dialog"))
                    dpg.bind_item_theme(dpg.last_item(), button_theme)
                    dpg.add_button(label='Export Playstyle', callback=lambda: dpg.show_item("combat_export_dialog"))
                    dpg.bind_item_theme(dpg.last_item(), button_theme)
                    dpg.add_button(label=tl('Set Playstyles'), callback=set_playstyles_callback)
                    dpg.bind_item_theme(dpg.last_item(), button_theme)

            # ==================== Misc Tab ====================
            with dpg.tab(label=tl('Misc')):
                dpg.add_text(tl('The utils below are for advanced users and no support will be given on them.'))
                dpg.add_separator()
                with dpg.group(horizontal=True):
                    dpg.add_text(tl('Scale') + ':'); dpg.add_input_text(tag='scale', width=80)
                    dpg.add_button(label=tl('Set Scale'), callback=set_scale_callback)
                    dpg.bind_item_theme(dpg.last_item(), button_theme)
                pet_worlds = ['WizardCity', 'Krokotopia', 'Marleybone', 'Mooshu', 'Dragonspyre']
                with dpg.group(horizontal=True):
                    dpg.add_text('Select a pet world:')
                    dpg.add_combo(items=pet_worlds, default_value='WizardCity', tag='PetWorldInput', width=120, callback=pet_world_callback)

            # ==================== Console Tab ====================
            with dpg.tab(label=tl('Console')):
                dpg.add_text(tl('Be sure to include your logs when asking for support.'))
                dpg.add_separator()
                dpg.add_input_text(tag='-CONSOLE-', multiline=True, width=-1, height=150, readonly=True)
                with dpg.group(horizontal=True):
                    dpg.add_button(label=tl('Collapse / Expand Logs'), callback=toggle_callback(GUIKeys.toggle_show_expanded_logs))
                    dpg.bind_item_theme(dpg.last_item(), button_theme)
                    dpg.add_button(label=tl('Copy Logs'), callback=copy_callback(GUIKeys.copy_logs))
                    dpg.bind_item_theme(dpg.last_item(), button_theme)

        # Client info at bottom
        dpg.add_separator()
        with dpg.table(header_row=False, borders_innerH=False, borders_outerH=False, borders_innerV=False, borders_outerV=False):
            dpg.add_table_column(init_width_or_weight=0, width_stretch=True)
            dpg.add_table_column(init_width_or_weight=0, width_fixed=True)
            with dpg.table_row():
                dpg.add_text(tl('Client') + ': ', tag='Title')
                dpg.add_spacer()
            with dpg.table_row():
                dpg.add_text(tl('Zone') + ': ', tag='Zone')
                dpg.add_button(label="Copy##zone", callback=copy_callback(GUIKeys.copy_zone), small=True)
                dpg.bind_item_theme(dpg.last_item(), button_theme)
            with dpg.table_row():
                dpg.add_text("Position (XYZ): ", tag='xyz')
                dpg.add_button(label="Copy##pos", callback=copy_callback(GUIKeys.copy_position), small=True)
                dpg.bind_item_theme(dpg.last_item(), button_theme)
            with dpg.table_row():
                dpg.add_text("Orientation (PRY): ", tag='pry')
                dpg.add_button(label="Copy##rot", callback=copy_callback(GUIKeys.copy_rotation), small=True)
                dpg.bind_item_theme(dpg.last_item(), button_theme)

    console_psg = DpgSink('-CONSOLE-')
    console_sink = logger.add(console_psg, colorize=True)

    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.set_primary_window("primary_window", True)

    if _scale != 1.0:
        dpg.set_global_font_scale(_scale)

    running = True
    _info_centered = False

    while dpg.is_dearpygui_running() and running:
        # Center tool info items once layout has settled
        if not _info_centered and dpg.get_frame_count() > 10:
            _info_centered = True
            try:
                panel_w = dpg.get_item_rect_size("tool_info_panel")[0]
                if panel_w > 0:
                    for item, item_w in _info_center_items:
                        indent = max(0, int((panel_w - item_w) / 2) - 8)
                        dpg.set_item_indent(item, indent)
            except Exception:
                pass

        # Auto-close license popup after ~5 seconds (300 frames at 60fps)
        if license_start_frame[0] == 0:
            license_start_frame[0] = dpg.get_frame_count()
        if dpg.does_item_exist(license_popup_tag) and dpg.get_frame_count() - license_start_frame[0] > 300:
            close_license()

        # Process commands from backend
        try:
            while True:
                com = recv_queue.get_nowait()
                match com.com_type:
                    case GUICommandType.Close:
                        running = False

                    case GUICommandType.CloseFromBackend:
                        send_queue.put(GUICommand(GUICommandType.AttemptedClose))

                    case GUICommandType.UpdateWindow:
                        tag = com.data[0]
                        value = com.data[1]
                        if dpg.does_item_exist(tag):
                            item_type = dpg.get_item_type(tag)
                            if "Checkbox" in item_type or "mvCheckbox" in item_type:
                                dpg.set_value(tag, value == 'Enabled')
                            else:
                                dpg.set_value(tag, value)

                    case GUICommandType.UpdateWindowValues:
                        tag = com.data[0]
                        values = com.data[1]
                        if dpg.does_item_exist(tag):
                            dpg.configure_item(tag, items=values)

                    case GUICommandType.UpdateConsole:
                        console_psg.toggle_show_expanded_logs()

                    case GUICommandType.ShowUITreePopup:
                        show_ui_tree_popup(com.data)

                    case GUICommandType.ShowEntityListPopup:
                        show_entity_list_popup(com.data)

                    case GUICommandType.CopyConsole:
                        console_psg.copy()

        except queue.Empty:
            pass

        dpg.render_dearpygui_frame()

    # Signal backend about the close
    if not running:
        # Backend told us to close via GUICommandType.Close
        send_queue.put(GUICommand(GUICommandType.Close))
    else:
        # User closed the window themselves — signal backend to unhook gracefully
        send_queue.put(GUICommand(GUICommandType.AttemptedClose))
        # Wait for backend to finish unhooking before destroying context
        import time
        timeout = 30  # max seconds to wait
        start = time.time()
        while time.time() - start < timeout:
            try:
                com = recv_queue.get_nowait()
                if com.com_type == GUICommandType.Close:
                    break
            except queue.Empty:
                pass
            time.sleep(0.1)

    dpg.destroy_context()
