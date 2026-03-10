from enum import Enum, auto
import gettext
import queue
import re
import os
import webbrowser
import tkinter as tk
import customtkinter as ctk
from tkinter import filedialog
import pyperclip
from src.combat_objects import school_id_to_names
from src.paths import wizard_city_dance_game_path
from src.utils import assign_pet_level
from threading import Thread
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


class TkSink:
    def __init__(self, console_textbox: ctk.CTkTextbox):
        self.console = console_textbox
        self.buffer = []
        self.max_lines = 1000
        self.show_expanded_logs = False

        self.level_colors = {
            "DEBUG": "grey",
            "INFO": "white",
            "SUCCESS": "green",
            "WARNING": "yellow",
            "ERROR": "red",
            "CRITICAL": "#ff3333",
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
            for l in self.level_colors:
                if l in clean_message:
                    level = l
                    break
            else:
                level = "DEBUG"
        else:
            level = split_msg[1].strip()

        def collapse_log(input_str: str) -> str:
            if "-" not in input_str:
                return input_str
            split_input = input_str.split("-")
            if len(split_input) < 4:
                return input_str
            return split_input[3].lstrip()

        truncated_message = level + " - " + collapse_log(clean_message)

        self.buffer.append((clean_message, truncated_message, level))
        if len(self.buffer) > self.max_lines:
            self.buffer.pop(0)

        try:
            message_to_write = clean_message if self.show_expanded_logs else truncated_message
            color = self.level_colors.get(level, "white")
            tag_name = f"level_{level}"
            self.console.configure(state="normal")
            self.console.insert("end", message_to_write, tag_name)
            self.console.tag_config(tag_name, foreground=color)
            self.console.configure(state="disabled")
            self.console.see("end")
        except Exception:
            pass

    def refresh(self):
        try:
            self.console.configure(state="normal")
            self.console.delete("1.0", "end")
            for clean, trunc, level in self.buffer:
                message_to_write = clean if self.show_expanded_logs else trunc
                color = self.level_colors.get(level, "white")
                tag_name = f"level_{level}"
                self.console.insert("end", message_to_write, tag_name)
                self.console.tag_config(tag_name, foreground=color)
            self.console.configure(state="disabled")
            self.console.see("end")
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


def _make_btn(parent, text, command, btn_color="#4a019e", text_color="white", **kwargs):
    """Helper to create a styled button."""
    height = kwargs.pop('height', 28)
    return ctk.CTkButton(parent, text=text, command=command,
                         fg_color=btn_color, text_color=text_color,
                         hover_color=_lighten(btn_color), height=height, **kwargs)


def _lighten(hex_color, amount=30):
    hex_color = hex_color.lstrip('#')
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    r, g, b = min(r + amount, 255), min(g + amount, 255), min(b + amount, 255)
    return f"#{r:02x}{g:02x}{b:02x}"


def show_ui_tree_popup(root, ui_tree_content):
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
            name = clean_line.split()[0] if clean_line.split() else clean_line

        while len(path_stack) > indent:
            path_stack.pop()

        current_path = path_stack.copy()
        current_path.append(name)

        path_dict[line] = current_path[1:] if len(current_path) > 1 else current_path
        path_stack.append(name)

    popup = ctk.CTkToplevel(root)
    popup.title("UI Tree")
    popup.geometry("700x500")
    popup.attributes("-topmost", True)

    ctk.CTkLabel(popup, text="Click the path needed to copy it to clipboard.").pack(padx=10, pady=(10, 5))

    search_var = ctk.StringVar()
    search_entry = ctk.CTkEntry(popup, textvariable=search_var, placeholder_text="Search...")
    search_entry.pack(fill="x", padx=10, pady=5)

    listbox_frame = ctk.CTkFrame(popup)
    listbox_frame.pack(fill="both", expand=True, padx=10, pady=5)

    listbox = tk.Listbox(listbox_frame, bg="#2b2b2b", fg="white", selectbackground="#4a019e",
                         font=("Consolas", 10), borderwidth=0, highlightthickness=0)
    scrollbar = ctk.CTkScrollbar(listbox_frame, command=listbox.yview)
    listbox.configure(yscrollcommand=scrollbar.set)
    listbox.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    for item in ui_tree_list:
        listbox.insert("end", item)

    def on_search(*args):
        search_term = search_var.get().lower()
        listbox.delete(0, "end")
        for item in ui_tree_list:
            if search_term in item.lower():
                listbox.insert("end", item)

    search_var.trace_add("write", on_search)

    def on_select(event):
        selection = listbox.curselection()
        if selection:
            selected = listbox.get(selection[0])
            if selected in path_dict:
                pyperclip.copy(str(path_dict[selected]))
            else:
                pyperclip.copy(selected)
            popup.destroy()

    listbox.bind("<<ListboxSelect>>", on_select)

    ctk.CTkButton(popup, text="Close", command=popup.destroy).pack(padx=10, pady=10)


def show_entity_list_popup(root, entity_list_content):
    entity_list = entity_list_content.splitlines()

    popup = ctk.CTkToplevel(root)
    popup.title("Entity List")
    popup.geometry("700x500")
    popup.attributes("-topmost", True)

    ctk.CTkLabel(popup, text="Click the entity needed to copy the name and location to clipboard.").pack(padx=10, pady=(10, 5))

    search_var = ctk.StringVar()
    search_entry = ctk.CTkEntry(popup, textvariable=search_var, placeholder_text="Search...")
    search_entry.pack(fill="x", padx=10, pady=5)

    listbox_frame = ctk.CTkFrame(popup)
    listbox_frame.pack(fill="both", expand=True, padx=10, pady=5)

    listbox = tk.Listbox(listbox_frame, bg="#2b2b2b", fg="white", selectbackground="#4a019e",
                         font=("Consolas", 10), borderwidth=0, highlightthickness=0)
    scrollbar = ctk.CTkScrollbar(listbox_frame, command=listbox.yview)
    listbox.configure(yscrollcommand=scrollbar.set)
    listbox.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    for item in entity_list:
        listbox.insert("end", item)

    def on_search(*args):
        search_term = search_var.get().lower()
        listbox.delete(0, "end")
        for item in entity_list:
            if search_term in item.lower():
                listbox.insert("end", item)

    search_var.trace_add("write", on_search)

    def on_select(event):
        selection = listbox.curselection()
        if selection:
            pyperclip.copy(listbox.get(selection[0]))
            popup.destroy()

    listbox.bind("<<ListboxSelect>>", on_select)

    ctk.CTkButton(popup, text="Close", command=popup.destroy).pack(padx=10, pady=10)


def manage_gui(send_queue: queue.Queue, recv_queue: queue.Queue, gui_theme, gui_text_color, gui_button_color, tool_name, tool_version, gui_on_top, langcode):
    if langcode != 'en':
        translate = gettext.translation("messages", "locale", languages=[langcode])
        tl = translate.gettext
    else:
        gettext.bindtextdomain('messages', 'locale')
        gettext.textdomain('messages')
        tl = gettext.gettext

    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")

    btn_color = gui_button_color if gui_button_color.startswith('#') else f"#{gui_button_color}"

    root = ctk.CTk()
    root.title(f"{tool_name} GUI v{tool_version}")
    root.resizable(False, False)
    root.attributes("-topmost", gui_on_top)

    # Set icon
    icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "Deimos-logo.ico")
    if os.path.exists(icon_path):
        try:
            root.iconbitmap(icon_path)
        except Exception:
            pass

    # Widget references for updates
    widgets = {}
    toggle_vars = {}

    def btn(parent, text, command, **kwargs):
        return _make_btn(parent, text, command, btn_color=btn_color, text_color=gui_text_color, **kwargs)

    # ===================== Custom Title Bar =====================
    root.overrideredirect(True)

    titlebar = ctk.CTkFrame(root, height=32, corner_radius=0, fg_color="#1e1e1e")
    titlebar.pack(fill="x", side="top")
    titlebar.pack_propagate(False)

    # Icon in title bar
    icon_png_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "Deimos-logo.png")
    if os.path.exists(icon_png_path):
        try:
            from PIL import Image
            title_icon_image = ctk.CTkImage(Image.open(icon_png_path), size=(20, 20))
            ctk.CTkLabel(titlebar, image=title_icon_image, text="").pack(side="left", padx=(8, 4))
        except Exception:
            pass

    ctk.CTkLabel(titlebar, text=f"{tool_name} v{tool_version}", font=("Segoe UI", 12),
                 text_color="white").pack(side="left", padx=4)

    close_btn = ctk.CTkButton(titlebar, text="✕", width=40, height=32, corner_radius=0,
                               fg_color="transparent", hover_color="#c42b1c", text_color="white",
                               command=lambda: send_queue.put(GUICommand(GUICommandType.AttemptedClose)))
    close_btn.pack(side="right")

    # Title bar dragging
    _drag = {"x": 0, "y": 0}
    def start_drag(e):
        _drag["x"] = e.x
        _drag["y"] = e.y
    def do_drag(e):
        x = root.winfo_x() + e.x - _drag["x"]
        y = root.winfo_y() + e.y - _drag["y"]
        root.geometry(f"+{x}+{y}")
    titlebar.bind("<Button-1>", start_drag)
    titlebar.bind("<B1-Motion>", do_drag)

    # ===================== Disclaimer =====================
    disclaimer_frame = ctk.CTkFrame(root, fg_color="transparent")
    disclaimer_frame.pack(fill="x", padx=10, pady=(4, 0))
    ctk.CTkLabel(disclaimer_frame,
                 text=tl('Deimos will always be a free tool. If you paid for this, you got scammed!'),
                 font=("Segoe UI", 11)).pack(anchor="w")

    # ===================== Tab View =====================
    tabview = ctk.CTkTabview(root, height=260)
    tabview.pack(fill="both", expand=True, padx=10, pady=(0, 5))

    tab_hotkeys = tabview.add(tl('Hotkeys'))
    tab_camera = tabview.add(tl('Camera'))
    tab_dev = tabview.add(tl('Dev Utils'))
    tab_stats = tabview.add(tl('Stats'))
    tab_flythrough = tabview.add(tl('Flythrough'))
    tab_bot = tabview.add(tl('Bot'))
    tab_combat = tabview.add(tl('Combat'))
    tab_misc = tabview.add(tl('Misc'))
    tab_console = tabview.add(tl('Console'))

    # ==================== Hotkeys Tab ====================
    hotkeys_left = ctk.CTkFrame(tab_hotkeys)
    hotkeys_left.pack(side="left", fill="y", padx=(0, 5))

    # Toggles
    toggles_frame = ctk.CTkFrame(hotkeys_left)
    toggles_frame.pack(fill="x", pady=(0, 5))
    ctk.CTkLabel(toggles_frame, text=tl('Toggles'), font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=5)

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
        row = ctk.CTkFrame(toggles_frame, fg_color="transparent")
        row.pack(fill="x", padx=5, pady=1)
        var = tk.BooleanVar(value=False)
        toggle_vars[f'{name}Status'] = var
        cb = ctk.CTkCheckBox(row, text="", variable=var, width=20, state="disabled",
                             checkbox_width=18, checkbox_height=18)
        cb.pack(side="left")
        btn(row, name, lambda k=key: send_queue.put(GUICommand(GUICommandType.ToggleOption, k)),
            width=90).pack(side="left", padx=(4, 0))

    # Hotkeys + Mass Hotkeys
    hotkeys_mid = ctk.CTkFrame(tab_hotkeys)
    hotkeys_mid.pack(side="left", fill="y", padx=(0, 5))

    hk_frame = ctk.CTkFrame(hotkeys_mid)
    hk_frame.pack(fill="x", pady=(0, 5))
    ctk.CTkLabel(hk_frame, text=tl('Hotkeys'), font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=5)
    btn(hk_frame, tl('Quest TP'), lambda: send_queue.put(GUICommand(GUICommandType.Teleport, GUIKeys.hotkey_quest_tp)),
        width=110).pack(padx=5, pady=1)
    btn(hk_frame, tl('Freecam'), lambda: send_queue.put(GUICommand(GUICommandType.ToggleOption, GUIKeys.toggle_freecam)),
        width=110).pack(padx=5, pady=1)
    btn(hk_frame, tl('Freecam TP'), lambda: send_queue.put(GUICommand(GUICommandType.Teleport, GUIKeys.hotkey_freecam_tp)),
        width=110).pack(padx=5, pady=1)

    mhk_frame = ctk.CTkFrame(hotkeys_mid)
    mhk_frame.pack(fill="x", pady=(5, 0))
    ctk.CTkLabel(mhk_frame, text=tl('Mass Hotkeys'), font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=5)
    btn(mhk_frame, tl('Mass TP'), lambda: send_queue.put(GUICommand(GUICommandType.Teleport, GUIKeys.mass_hotkey_mass_tp)),
        width=110).pack(padx=5, pady=1)
    btn(mhk_frame, tl('XYZ Sync'), lambda: send_queue.put(GUICommand(GUICommandType.XYZSync)),
        width=110).pack(padx=5, pady=1)
    btn(mhk_frame, tl('X Press'), lambda: send_queue.put(GUICommand(GUICommandType.XPress)),
        width=110).pack(padx=5, pady=1)

    # Tool Info Panel
    info_frame = ctk.CTkFrame(tab_hotkeys)
    info_frame.pack(side="left", fill="both", expand=True, padx=(0, 0))

    # Logo
    logo_png = os.path.join(os.path.dirname(os.path.dirname(__file__)), "Deimos-logo.png")
    if os.path.exists(logo_png):
        try:
            from PIL import Image
            logo_image = ctk.CTkImage(Image.open(logo_png), size=(64, 64))
            ctk.CTkLabel(info_frame, image=logo_image, text="").pack(pady=(20, 5))
        except Exception:
            pass

    ctk.CTkLabel(info_frame, text=f"{tool_name} v{tool_version}",
                 font=("Segoe UI", 14, "bold")).pack(pady=(5, 2))

    discord_btn = ctk.CTkButton(info_frame, text="Discord: discord.gg/JHrdCNK",
                                 fg_color="transparent", hover_color="#333355",
                                 text_color="#6495ED", font=("Segoe UI", 12, "underline"),
                                 command=lambda: webbrowser.open("https://discord.gg/JHrdCNK"))
    discord_btn.pack(pady=2)

    # ==================== Camera Tab ====================
    dev_notice = tl('The utils below are for advanced users and no support will be given on them.')
    ctk.CTkLabel(tab_camera, text=dev_notice, wraplength=550).pack(anchor="w", padx=5, pady=(5, 2))

    cam_row1 = ctk.CTkFrame(tab_camera, fg_color="transparent")
    cam_row1.pack(fill="x", padx=5, pady=2)
    ctk.CTkLabel(cam_row1, text="X:").pack(side="left")
    widgets['CamXInput'] = ctk.CTkEntry(cam_row1, width=70)
    widgets['CamXInput'].pack(side="left", padx=2)
    ctk.CTkLabel(cam_row1, text="Y:").pack(side="left")
    widgets['CamYInput'] = ctk.CTkEntry(cam_row1, width=70)
    widgets['CamYInput'].pack(side="left", padx=2)
    ctk.CTkLabel(cam_row1, text="Z:").pack(side="left")
    widgets['CamZInput'] = ctk.CTkEntry(cam_row1, width=70)
    widgets['CamZInput'].pack(side="left", padx=2)
    btn(cam_row1, tl('Set Camera Position'),
        lambda: send_queue.put(GUICommand(GUICommandType.SetCamPosition, {
            'X': widgets['CamXInput'].get(), 'Y': widgets['CamYInput'].get(), 'Z': widgets['CamZInput'].get(),
            'Yaw': widgets['CamYawInput'].get(), 'Roll': widgets['CamRollInput'].get(), 'Pitch': widgets['CamPitchInput'].get(),
        }))).pack(side="left", padx=2)

    cam_row2 = ctk.CTkFrame(tab_camera, fg_color="transparent")
    cam_row2.pack(fill="x", padx=5, pady=2)
    ctk.CTkLabel(cam_row2, text=tl('Yaw') + ':').pack(side="left")
    widgets['CamYawInput'] = ctk.CTkEntry(cam_row2, width=70)
    widgets['CamYawInput'].pack(side="left", padx=2)
    ctk.CTkLabel(cam_row2, text=tl('Roll') + ':').pack(side="left")
    widgets['CamRollInput'] = ctk.CTkEntry(cam_row2, width=70)
    widgets['CamRollInput'].pack(side="left", padx=2)
    ctk.CTkLabel(cam_row2, text=tl('Pitch') + ':').pack(side="left")
    widgets['CamPitchInput'] = ctk.CTkEntry(cam_row2, width=70)
    widgets['CamPitchInput'].pack(side="left", padx=2)

    cam_row3 = ctk.CTkFrame(tab_camera, fg_color="transparent")
    cam_row3.pack(fill="x", padx=5, pady=2)
    ctk.CTkLabel(cam_row3, text=tl('Entity') + ':').pack(side="left")
    widgets['CamEntityInput'] = ctk.CTkEntry(cam_row3, width=140)
    widgets['CamEntityInput'].pack(side="left", padx=2)
    btn(cam_row3, tl('Anchor'),
        lambda: send_queue.put(GUICommand(GUICommandType.AnchorCam, widgets['CamEntityInput'].get()))).pack(side="left", padx=2)
    btn(cam_row3, tl('Toggle Cam Collision'),
        lambda: send_queue.put(GUICommand(GUICommandType.ToggleOption, GUIKeys.toggle_camera_collision))).pack(side="left", padx=2)

    cam_row4 = ctk.CTkFrame(tab_camera, fg_color="transparent")
    cam_row4.pack(fill="x", padx=5, pady=2)
    ctk.CTkLabel(cam_row4, text=tl('Distance') + ':').pack(side="left")
    widgets['CamDistanceInput'] = ctk.CTkEntry(cam_row4, width=70)
    widgets['CamDistanceInput'].pack(side="left", padx=2)
    ctk.CTkLabel(cam_row4, text=tl('Min') + ':').pack(side="left")
    widgets['CamMinInput'] = ctk.CTkEntry(cam_row4, width=70)
    widgets['CamMinInput'].pack(side="left", padx=2)
    ctk.CTkLabel(cam_row4, text=tl('Max') + ':').pack(side="left")
    widgets['CamMaxInput'] = ctk.CTkEntry(cam_row4, width=70)
    widgets['CamMaxInput'].pack(side="left", padx=2)
    btn(cam_row4, tl('Set Distance'),
        lambda: send_queue.put(GUICommand(GUICommandType.SetCamDistance, {
            "Distance": widgets['CamDistanceInput'].get(), "Min": widgets['CamMinInput'].get(), "Max": widgets['CamMaxInput'].get(),
        }))).pack(side="left", padx=2)

    cam_row5 = ctk.CTkFrame(tab_camera, fg_color="transparent")
    cam_row5.pack(fill="x", padx=5, pady=2)
    btn(cam_row5, tl('Copy Camera Position'),
        lambda: send_queue.put(GUICommand(GUICommandType.Copy, GUIKeys.copy_camera_position))).pack(side="left", padx=2)
    btn(cam_row5, tl('Copy Camera Rotation'),
        lambda: send_queue.put(GUICommand(GUICommandType.Copy, GUIKeys.copy_camera_rotation))).pack(side="left", padx=2)

    # ==================== Dev Utils Tab ====================
    ctk.CTkLabel(tab_dev, text=dev_notice, wraplength=550).pack(anchor="w", padx=5, pady=(5, 2))

    # TP Utils
    ctk.CTkLabel(tab_dev, text=tl('TP Utils'), font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=5)
    tp_row1 = ctk.CTkFrame(tab_dev, fg_color="transparent")
    tp_row1.pack(fill="x", padx=5, pady=2)
    ctk.CTkLabel(tp_row1, text="X:").pack(side="left")
    widgets['XInput'] = ctk.CTkEntry(tp_row1, width=55)
    widgets['XInput'].pack(side="left", padx=2)
    ctk.CTkLabel(tp_row1, text="Y:").pack(side="left")
    widgets['YInput'] = ctk.CTkEntry(tp_row1, width=55)
    widgets['YInput'].pack(side="left", padx=2)
    ctk.CTkLabel(tp_row1, text="Z:").pack(side="left")
    widgets['ZInput'] = ctk.CTkEntry(tp_row1, width=55)
    widgets['ZInput'].pack(side="left", padx=2)
    ctk.CTkLabel(tp_row1, text=tl('Yaw') + ':').pack(side="left")
    widgets['YawInput'] = ctk.CTkEntry(tp_row1, width=55)
    widgets['YawInput'].pack(side="left", padx=2)
    btn(tp_row1, tl('Custom TP'), lambda: send_queue.put(GUICommand(GUICommandType.CustomTeleport, {
        'X': widgets['XInput'].get(), 'Y': widgets['YInput'].get(),
        'Z': widgets['ZInput'].get(), 'Yaw': widgets['YawInput'].get(),
    }))).pack(side="left", padx=2)

    tp_row2 = ctk.CTkFrame(tab_dev, fg_color="transparent")
    tp_row2.pack(fill="x", padx=5, pady=2)
    ctk.CTkLabel(tp_row2, text=tl('Entity Name') + ':').pack(side="left")
    widgets['EntityTPInput'] = ctk.CTkEntry(tp_row2, width=220)
    widgets['EntityTPInput'].pack(side="left", padx=2)
    btn(tp_row2, tl('Entity TP'), lambda: send_queue.put(GUICommand(GUICommandType.EntityTeleport, widgets['EntityTPInput'].get())) if widgets['EntityTPInput'].get() else None).pack(side="left", padx=2)

    # Dev Utils section
    ctk.CTkLabel(tab_dev, text=tl('Dev Utils'), font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=5, pady=(5, 0))
    dev_row1 = ctk.CTkFrame(tab_dev, fg_color="transparent")
    dev_row1.pack(fill="x", padx=5, pady=2)
    btn(dev_row1, tl('Available Entities'), lambda: send_queue.put(GUICommand(GUICommandType.Copy, GUIKeys.copy_entity_list))).pack(side="left", padx=2)
    btn(dev_row1, tl('Available Paths'), lambda: send_queue.put(GUICommand(GUICommandType.Copy, GUIKeys.copy_ui_tree))).pack(side="left", padx=2)

    dev_row2 = ctk.CTkFrame(tab_dev, fg_color="transparent")
    dev_row2.pack(fill="x", padx=5, pady=2)
    ctk.CTkLabel(dev_row2, text=tl('Zone Name') + ':').pack(side="left")
    widgets['ZoneInput'] = ctk.CTkEntry(dev_row2, width=120)
    widgets['ZoneInput'].pack(side="left", padx=2)
    btn(dev_row2, tl('Go To Zone'), lambda: send_queue.put(GUICommand(GUICommandType.GoToZone, (False, widgets['ZoneInput'].get()))) if widgets['ZoneInput'].get() else None).pack(side="left", padx=2)
    btn(dev_row2, tl('Mass Go To Zone'), lambda: send_queue.put(GUICommand(GUICommandType.GoToZone, (True, widgets['ZoneInput'].get()))) if widgets['ZoneInput'].get() else None).pack(side="left", padx=2)

    worlds = ['WizardCity', 'Krokotopia', 'Marleybone', 'MooShu', 'DragonSpire', 'Grizzleheim', 'Celestia', 'Wysteria', 'Zafaria', 'Avalon', 'Azteca', 'Khrysalis', 'Polaris', 'Mirage', 'Empyrea', 'Karamelle', 'Lemuria']
    dev_row3 = ctk.CTkFrame(tab_dev, fg_color="transparent")
    dev_row3.pack(fill="x", padx=5, pady=2)
    ctk.CTkLabel(dev_row3, text=tl('World Name') + ':').pack(side="left")
    widgets['WorldInput'] = ctk.CTkComboBox(dev_row3, values=worlds, width=120, state="readonly")
    widgets['WorldInput'].set('WizardCity')
    widgets['WorldInput'].pack(side="left", padx=2)
    btn(dev_row3, tl('Go To World'), lambda: send_queue.put(GUICommand(GUICommandType.GoToWorld, (False, widgets['WorldInput'].get())))).pack(side="left", padx=2)
    btn(dev_row3, tl('Mass Go To World'), lambda: send_queue.put(GUICommand(GUICommandType.GoToWorld, (True, widgets['WorldInput'].get())))).pack(side="left", padx=2)

    dev_row4 = ctk.CTkFrame(tab_dev, fg_color="transparent")
    dev_row4.pack(fill="x", padx=5, pady=2)
    btn(dev_row4, tl('Go To Bazaar'), lambda: send_queue.put(GUICommand(GUICommandType.GoToBazaar, False))).pack(side="left", padx=2)
    btn(dev_row4, tl('Mass Go To Bazaar'), lambda: send_queue.put(GUICommand(GUICommandType.GoToBazaar, True))).pack(side="left", padx=2)
    btn(dev_row4, tl('Refill Potions'), lambda: send_queue.put(GUICommand(GUICommandType.RefillPotions, False))).pack(side="left", padx=2)
    btn(dev_row4, tl('Mass Refill Potions'), lambda: send_queue.put(GUICommand(GUICommandType.RefillPotions, True))).pack(side="left", padx=2)

    # ==================== Stats Tab ====================
    ctk.CTkLabel(tab_stats, text=dev_notice, wraplength=550).pack(anchor="w", padx=5, pady=(5, 2))

    indices = [str(i + 1) for i in range(12)]
    stat_row1 = ctk.CTkFrame(tab_stats, fg_color="transparent")
    stat_row1.pack(fill="x", padx=5, pady=2)
    ctk.CTkLabel(stat_row1, text=tl('Caster/Target') + ':').pack(side="left")
    widgets['EnemyInput'] = ctk.CTkComboBox(stat_row1, values=indices, width=80, state="readonly")
    widgets['EnemyInput'].set('1')
    widgets['EnemyInput'].pack(side="left", padx=2)
    widgets['AllyInput'] = ctk.CTkComboBox(stat_row1, values=indices, width=80, state="readonly")
    widgets['AllyInput'].set('1')
    widgets['AllyInput'].pack(side="left", padx=2)

    schools = ['Fire', 'Ice', 'Storm', 'Myth', 'Life', 'Death', 'Balance', 'Star', 'Sun', 'Moon', 'Shadow']
    stat_row2 = ctk.CTkFrame(tab_stats, fg_color="transparent")
    stat_row2.pack(fill="x", padx=5, pady=2)
    ctk.CTkLabel(stat_row2, text=tl('Dmg') + ':').pack(side="left")
    widgets['DamageInput'] = ctk.CTkEntry(stat_row2, width=55)
    widgets['DamageInput'].pack(side="left", padx=2)
    ctk.CTkLabel(stat_row2, text=tl('School') + ':').pack(side="left")
    widgets['SchoolInput'] = ctk.CTkComboBox(stat_row2, values=schools, width=80, state="readonly")
    widgets['SchoolInput'].set('Fire')
    widgets['SchoolInput'].pack(side="left", padx=2)
    ctk.CTkLabel(stat_row2, text=tl('Crit') + ':').pack(side="left")
    widgets['CritStatus'] = ctk.CTkCheckBox(stat_row2, text="", width=20, checkbox_width=18, checkbox_height=18)
    widgets['CritStatus'].select()
    widgets['CritStatus'].pack(side="left", padx=2)

    def view_stats_cmd():
        enemy_index = re.sub(r'[^0-9]', '', str(widgets['EnemyInput'].get()))
        ally_index = re.sub(r'[^0-9]', '', str(widgets['AllyInput'].get()))
        base_damage = re.sub(r'[^0-9]', '', str(widgets['DamageInput'].get()))
        school_id = school_id_to_names[widgets['SchoolInput'].get()]
        send_queue.put(GUICommand(GUICommandType.SelectEnemy, (
            int(enemy_index) if enemy_index else 1,
            int(ally_index) if ally_index else 1,
            base_damage, school_id,
            bool(widgets['CritStatus'].get()),
            bool(widgets['ForceSchoolStatus'].get())
        )))

    btn(stat_row2, tl('View Stats'), view_stats_cmd).pack(side="left", padx=2)
    btn(stat_row2, tl('Copy Stats'), lambda: send_queue.put(GUICommand(GUICommandType.Copy, GUIKeys.copy_stats))).pack(side="left", padx=2)

    widgets['stat_viewer'] = ctk.CTkTextbox(tab_stats, height=100, state="disabled")
    widgets['stat_viewer'].pack(fill="both", expand=True, padx=5, pady=2)
    widgets['stat_viewer'].configure(state="normal")
    widgets['stat_viewer'].insert("1.0", tl('No client has been selected.'))
    widgets['stat_viewer'].configure(state="disabled")

    stat_row3 = ctk.CTkFrame(tab_stats, fg_color="transparent")
    stat_row3.pack(fill="x", padx=5, pady=2)
    def swap_members():
        e = widgets['EnemyInput'].get()
        a = widgets['AllyInput'].get()
        widgets['EnemyInput'].set(a)
        widgets['AllyInput'].set(e)
    btn(stat_row3, tl('Swap Members'), swap_members).pack(side="left", padx=2)
    ctk.CTkLabel(stat_row3, text=tl('Force School Damage') + ':').pack(side="left", padx=(10, 0))
    widgets['ForceSchoolStatus'] = ctk.CTkCheckBox(stat_row3, text="", width=20, checkbox_width=18, checkbox_height=18)
    widgets['ForceSchoolStatus'].pack(side="left", padx=2)

    # ==================== Flythrough Tab ====================
    ctk.CTkLabel(tab_flythrough, text=dev_notice, wraplength=550).pack(anchor="w", padx=5, pady=(5, 2))
    widgets['flythrough_creator'] = ctk.CTkTextbox(tab_flythrough, height=120)
    widgets['flythrough_creator'].pack(fill="both", expand=True, padx=5, pady=2)

    fly_btns = ctk.CTkFrame(tab_flythrough, fg_color="transparent")
    fly_btns.pack(fill="x", padx=5, pady=2)

    def import_flythrough():
        path = filedialog.askopenfilename(filetypes=[("Text Files", "*.txt")])
        if path:
            with open(path) as f:
                widgets['flythrough_creator'].delete("1.0", "end")
                widgets['flythrough_creator'].insert("1.0", f.read())

    def export_flythrough():
        path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text Files", "*.txt")])
        if path:
            with open(path, 'w') as f:
                f.write(widgets['flythrough_creator'].get("1.0", "end-1c"))

    btn(fly_btns, tl('Import Flythrough'), import_flythrough).pack(side="left", padx=2)
    btn(fly_btns, tl('Export Flythrough'), export_flythrough).pack(side="left", padx=2)
    btn(fly_btns, tl('Execute Flythrough'),
        lambda: send_queue.put(GUICommand(GUICommandType.ExecuteFlythrough, widgets['flythrough_creator'].get("1.0", "end-1c")))).pack(side="left", padx=2)
    btn(fly_btns, tl('Kill Flythrough'),
        lambda: send_queue.put(GUICommand(GUICommandType.KillFlythrough))).pack(side="left", padx=2)

    # ==================== Bot Tab ====================
    ctk.CTkLabel(tab_bot, text=dev_notice, wraplength=550).pack(anchor="w", padx=5, pady=(5, 2))
    widgets['bot_creator'] = ctk.CTkTextbox(tab_bot, height=120)
    widgets['bot_creator'].pack(fill="both", expand=True, padx=5, pady=2)

    bot_btns = ctk.CTkFrame(tab_bot, fg_color="transparent")
    bot_btns.pack(fill="x", padx=5, pady=2)

    def import_bot():
        path = filedialog.askopenfilename(filetypes=[("Text Files", "*.txt")])
        if path:
            with open(path) as f:
                widgets['bot_creator'].delete("1.0", "end")
                widgets['bot_creator'].insert("1.0", f.read())

    def export_bot():
        path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text Files", "*.txt")])
        if path:
            with open(path, 'w') as f:
                f.write(widgets['bot_creator'].get("1.0", "end-1c"))

    btn(bot_btns, 'Import Bot', import_bot).pack(side="left", padx=2)
    btn(bot_btns, 'Export Bot', export_bot).pack(side="left", padx=2)
    btn(bot_btns, tl('Run Bot'),
        lambda: send_queue.put(GUICommand(GUICommandType.ExecuteBot, widgets['bot_creator'].get("1.0", "end-1c")))).pack(side="left", padx=2)
    btn(bot_btns, tl('Kill Bot'),
        lambda: send_queue.put(GUICommand(GUICommandType.KillBot))).pack(side="left", padx=2)

    # ==================== Combat Tab ====================
    ctk.CTkLabel(tab_combat, text=dev_notice, wraplength=550).pack(anchor="w", padx=5, pady=(5, 2))
    widgets['combat_config'] = ctk.CTkTextbox(tab_combat, height=120)
    widgets['combat_config'].pack(fill="both", expand=True, padx=5, pady=2)

    combat_btns = ctk.CTkFrame(tab_combat, fg_color="transparent")
    combat_btns.pack(fill="x", padx=5, pady=2)

    def import_combat():
        path = filedialog.askopenfilename(filetypes=[("Text Files", "*.txt")])
        if path:
            with open(path) as f:
                widgets['combat_config'].delete("1.0", "end")
                widgets['combat_config'].insert("1.0", f.read())

    def export_combat():
        path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text Files", "*.txt")])
        if path:
            with open(path, 'w') as f:
                f.write(widgets['combat_config'].get("1.0", "end-1c"))

    btn(combat_btns, 'Import Playstyle', import_combat).pack(side="left", padx=2)
    btn(combat_btns, 'Export Playstyle', export_combat).pack(side="left", padx=2)
    btn(combat_btns, tl('Set Playstyles'),
        lambda: send_queue.put(GUICommand(GUICommandType.SetPlaystyles, widgets['combat_config'].get("1.0", "end-1c")))).pack(side="left", padx=2)

    # ==================== Misc Tab ====================
    ctk.CTkLabel(tab_misc, text=dev_notice, wraplength=550).pack(anchor="w", padx=5, pady=(5, 2))
    misc_row1 = ctk.CTkFrame(tab_misc, fg_color="transparent")
    misc_row1.pack(fill="x", padx=5, pady=2)
    ctk.CTkLabel(misc_row1, text=tl('Scale') + ':').pack(side="left")
    widgets['scale'] = ctk.CTkEntry(misc_row1, width=70)
    widgets['scale'].pack(side="left", padx=2)
    btn(misc_row1, tl('Set Scale'),
        lambda: send_queue.put(GUICommand(GUICommandType.SetScale, widgets['scale'].get()))).pack(side="left", padx=2)

    pet_worlds = ['WizardCity', 'Krokotopia', 'Marleybone', 'Mooshu', 'Dragonspyre']
    misc_row2 = ctk.CTkFrame(tab_misc, fg_color="transparent")
    misc_row2.pack(fill="x", padx=5, pady=2)
    ctk.CTkLabel(misc_row2, text='Select a pet world:').pack(side="left")

    def on_pet_world_change(choice):
        if choice != wizard_city_dance_game_path[-1]:
            assign_pet_level(choice)

    widgets['PetWorldInput'] = ctk.CTkComboBox(misc_row2, values=pet_worlds, width=120, state="readonly",
                                                command=on_pet_world_change)
    widgets['PetWorldInput'].set('WizardCity')
    widgets['PetWorldInput'].pack(side="left", padx=2)

    # ==================== Console Tab ====================
    ctk.CTkLabel(tab_console, text=tl('Be sure to include your logs when asking for support.')).pack(anchor="w", padx=5, pady=(5, 2))
    widgets['-CONSOLE-'] = ctk.CTkTextbox(tab_console, height=120, state="disabled")
    widgets['-CONSOLE-'].pack(fill="both", expand=True, padx=5, pady=2)

    console_btns = ctk.CTkFrame(tab_console, fg_color="transparent")
    console_btns.pack(fill="x", padx=5, pady=2)
    btn(console_btns, tl('Collapse / Expand Logs'),
        lambda: send_queue.put(GUICommand(GUICommandType.ToggleOption, GUIKeys.toggle_show_expanded_logs))).pack(side="left", padx=2)
    btn(console_btns, tl('Copy Logs'),
        lambda: send_queue.put(GUICommand(GUICommandType.Copy, GUIKeys.copy_logs))).pack(side="left", padx=2)

    # ==================== Client Info Bar ====================
    info_bar = ctk.CTkFrame(root, fg_color="transparent")
    info_bar.pack(fill="x", padx=10, pady=(0, 8))

    # Use grid for right-aligned copy buttons
    info_bar.columnconfigure(0, weight=1)
    info_bar.columnconfigure(1, weight=0)

    widgets['Title'] = ctk.CTkLabel(info_bar, text=tl('Client') + ': ', anchor="w")
    widgets['Title'].grid(row=0, column=0, sticky="w", columnspan=2)

    widgets['Zone'] = ctk.CTkLabel(info_bar, text=tl('Zone') + ': ', anchor="w")
    widgets['Zone'].grid(row=1, column=0, sticky="w")
    btn(info_bar, "Copy", lambda: send_queue.put(GUICommand(GUICommandType.Copy, GUIKeys.copy_zone)),
        width=50, height=22).grid(row=1, column=1, sticky="e", padx=(5, 0))

    widgets['xyz'] = ctk.CTkLabel(info_bar, text="Position (XYZ): ", anchor="w")
    widgets['xyz'].grid(row=2, column=0, sticky="w")
    btn(info_bar, "Copy", lambda: send_queue.put(GUICommand(GUICommandType.Copy, GUIKeys.copy_position)),
        width=50, height=22).grid(row=2, column=1, sticky="e", padx=(5, 0))

    widgets['pry'] = ctk.CTkLabel(info_bar, text="Orientation (PRY): ", anchor="w")
    widgets['pry'].grid(row=3, column=0, sticky="w")
    btn(info_bar, "Copy", lambda: send_queue.put(GUICommand(GUICommandType.Copy, GUIKeys.copy_rotation)),
        width=50, height=22).grid(row=3, column=1, sticky="e", padx=(5, 0))

    # ===================== Console Sink Setup =====================
    global console_sink
    global console_psg
    console_psg = TkSink(widgets['-CONSOLE-'])
    console_sink = logger.add(console_psg, colorize=True)

    # ===================== License Popup =====================
    license_popup = ctk.CTkToplevel(root)
    license_popup.title(tl('License Agreement'))
    license_popup.geometry("500x130")
    license_popup.attributes("-topmost", True)
    license_popup.resizable(False, False)
    ctk.CTkLabel(license_popup,
                 text=tl('Deimos will always be free and open-source.\nBy using Deimos, you agree to the GPL v3 license agreement.\nIf you bought this, you got scammed!'),
                 wraplength=470).pack(padx=15, pady=(15, 5))
    ctk.CTkButton(license_popup, text="OK", command=license_popup.destroy).pack(pady=5)
    root.after(5000, lambda: license_popup.destroy() if license_popup.winfo_exists() else None)

    # ===================== Queue Polling Loop =====================
    def poll_queue():
        try:
            while True:
                com = recv_queue.get_nowait()
                match com.com_type:
                    case GUICommandType.Close:
                        root.destroy()
                        return

                    case GUICommandType.CloseFromBackend:
                        send_queue.put(GUICommand(GUICommandType.AttemptedClose))

                    case GUICommandType.UpdateWindow:
                        tag = com.data[0]
                        value = com.data[1]
                        # Check toggle status checkboxes
                        if tag in toggle_vars:
                            toggle_vars[tag].set(value == 'Enabled')
                        elif tag in widgets:
                            widget = widgets[tag]
                            if isinstance(widget, ctk.CTkLabel):
                                widget.configure(text=value)
                            elif isinstance(widget, ctk.CTkEntry):
                                widget.delete(0, "end")
                                widget.insert(0, value)
                            elif isinstance(widget, ctk.CTkComboBox):
                                widget.set(value)
                            elif isinstance(widget, ctk.CTkTextbox):
                                widget.configure(state="normal")
                                widget.delete("1.0", "end")
                                widget.insert("1.0", value)
                                widget.configure(state="disabled")

                    case GUICommandType.UpdateWindowValues:
                        tag = com.data[0]
                        values = com.data[1]
                        if tag in widgets:
                            widget = widgets[tag]
                            if isinstance(widget, ctk.CTkComboBox):
                                widget.configure(values=[str(v) for v in values])

                    case GUICommandType.UpdateConsole:
                        console_psg.toggle_show_expanded_logs()

                    case GUICommandType.ShowUITreePopup:
                        show_ui_tree_popup(root, com.data)

                    case GUICommandType.ShowEntityListPopup:
                        show_entity_list_popup(root, com.data)

                    case GUICommandType.CopyConsole:
                        console_psg.copy()

        except queue.Empty:
            pass

        root.after(10, poll_queue)

    root.after(10, poll_queue)

    # Handle window close
    def on_closing():
        send_queue.put(GUICommand(GUICommandType.AttemptedClose))

    root.protocol("WM_DELETE_WINDOW", on_closing)

    # Size the window after all widgets are placed
    root.update_idletasks()
    root.mainloop()
