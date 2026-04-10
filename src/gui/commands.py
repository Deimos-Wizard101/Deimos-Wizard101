from enum import Enum, auto

from PyQt6.QtCore import Qt


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

    PopulateCamera = auto()
    PopulatePlayerGID = auto()  # GUI -> Backend: fetch player GID into CamEntityGIDInput

    RebindHotkey = auto()  # GUI -> Backend: (action_id, key, modifiers) or (action_id, None, None)
    FriendTeleport = auto()  # GUI -> Backend
    ToggleDialogueSideQuests = auto()  # GUI -> Backend

    InvokeAction = auto()  # Backend -> GUI: action_id (triggers button callback)

    # deimos -> window
    UpdateWindow = auto()
    UpdateWindowValues = auto()
    UpdateConsole = auto()
    CopyConsole = auto()

    ShowUITreePopup = auto()
    ShowEntityListPopup = auto()

    HighlightEntity = auto()  # GUI -> Backend, data = (x, y, z, height)
    HighlightUIWindow = auto()  # GUI -> Backend, data = list[str] (name path)
    ClearHighlight = auto()  # GUI -> Backend, data = None
    UpdateHighlightBox = auto()  # Backend -> GUI, data = (window_handle, x1, y1, x2, y2) or None

    StartEntityStream = auto()  # GUI -> Backend, data = None
    StopEntityStream = auto()  # GUI -> Backend, data = None
    UpdateEntityListData = auto()  # Backend -> GUI, data = list of entity dicts

    # Launcher
    LaunchInstance = auto()
    SaveAccount = auto()
    DeleteAccount = auto()
    LoadAccounts = auto()
    UpdateAccountList = auto()
    ReorderAccounts = auto()
    UnhookClient = auto()
    HookClient = auto()
    KillClient = auto()
    RelaunchClient = auto()
    UpdateHookedClients = auto()
    ClearLaunchCheckboxes = auto()
    ReorderClients = auto()

    UpdateSettings = auto()  # GUI -> Backend: dict of {key: value} pairs


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

    toggle_dialogue_side_quests = "toggledialoguesidequests"
    friend_tp = "friendtp"

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
    copy_camera_rotation = "copycamerarotation"
    copy_stats = "copystats"
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


# Maps Qt key codes to wizwalker Keycode member names
_QT_KEY_TO_KEYCODE = {
    Qt.Key.Key_Backspace: "BACK",
    Qt.Key.Key_Tab: "TAB",
    Qt.Key.Key_Return: "RETURN",
    Qt.Key.Key_Enter: "RETURN",
    Qt.Key.Key_Pause: "PAUSE",
    Qt.Key.Key_CapsLock: "CAPITAL",
    Qt.Key.Key_Escape: "ESCAPE",
    Qt.Key.Key_Space: "SPACE",
    Qt.Key.Key_PageUp: "PRIOR",
    Qt.Key.Key_PageDown: "NEXT",
    Qt.Key.Key_End: "END",
    Qt.Key.Key_Home: "HOME",
    Qt.Key.Key_Left: "LEFT",
    Qt.Key.Key_Up: "UP",
    Qt.Key.Key_Right: "RIGHT",
    Qt.Key.Key_Down: "DOWN",
    Qt.Key.Key_Insert: "INSERT",
    Qt.Key.Key_Delete: "DELETE",
    Qt.Key.Key_0: "ZERO",
    Qt.Key.Key_1: "ONE",
    Qt.Key.Key_2: "TWO",
    Qt.Key.Key_3: "THREE",
    Qt.Key.Key_4: "FOUR",
    Qt.Key.Key_5: "FIVE",
    Qt.Key.Key_6: "SIX",
    Qt.Key.Key_7: "SEVEN",
    Qt.Key.Key_8: "EIGHT",
    Qt.Key.Key_9: "NINE",
    Qt.Key.Key_A: "A",
    Qt.Key.Key_B: "B",
    Qt.Key.Key_C: "C",
    Qt.Key.Key_D: "D",
    Qt.Key.Key_E: "E",
    Qt.Key.Key_F: "F",
    Qt.Key.Key_G: "G",
    Qt.Key.Key_H: "H",
    Qt.Key.Key_I: "I",
    Qt.Key.Key_J: "J",
    Qt.Key.Key_K: "K",
    Qt.Key.Key_L: "L",
    Qt.Key.Key_M: "M",
    Qt.Key.Key_N: "N",
    Qt.Key.Key_O: "O",
    Qt.Key.Key_P: "P",
    Qt.Key.Key_Q: "Q",
    Qt.Key.Key_R: "R",
    Qt.Key.Key_S: "S",
    Qt.Key.Key_T: "T",
    Qt.Key.Key_U: "U",
    Qt.Key.Key_V: "V",
    Qt.Key.Key_W: "W",
    Qt.Key.Key_X: "X",
    Qt.Key.Key_Y: "Y",
    Qt.Key.Key_Z: "Z",
    Qt.Key.Key_F1: "F1",
    Qt.Key.Key_F2: "F2",
    Qt.Key.Key_F3: "F3",
    Qt.Key.Key_F4: "F4",
    Qt.Key.Key_F5: "F5",
    Qt.Key.Key_F6: "F6",
    Qt.Key.Key_F7: "F7",
    Qt.Key.Key_F8: "F8",
    Qt.Key.Key_F9: "F9",
    Qt.Key.Key_F10: "F10",
    Qt.Key.Key_F11: "F11",
    Qt.Key.Key_F12: "F12",
    Qt.Key.Key_NumLock: "NUMLOCK",
    Qt.Key.Key_ScrollLock: "SCROLL",
    Qt.Key.Key_Semicolon: "OEM_1",
    Qt.Key.Key_Equal: "OEM_PLUS",
    Qt.Key.Key_Comma: "OEM_COMMA",
    Qt.Key.Key_Minus: "OEM_MINUS",
    Qt.Key.Key_Period: "OEM_PERIOD",
    Qt.Key.Key_Slash: "OEM_2",
    Qt.Key.Key_QuoteLeft: "OEM_3",
    Qt.Key.Key_BracketLeft: "OEM_4",
    Qt.Key.Key_Backslash: "OEM_5",
    Qt.Key.Key_BracketRight: "OEM_6",
    Qt.Key.Key_Apostrophe: "OEM_7",
}

# Bare modifier keys to ignore (only fire when combined with a real key)
_MODIFIER_KEYS = {
    Qt.Key.Key_Shift,
    Qt.Key.Key_Control,
    Qt.Key.Key_Alt,
    Qt.Key.Key_Meta,
}


def _format_binding(key: str | None, modifiers: list[str] | None) -> str:
    """Format a key binding for display, e.g. 'Shift+F4' or 'Unbound'."""
    if key is None:
        return "Unbound"

    parts = []

    if modifiers:
        for m in modifiers:
            parts.append(m.capitalize())

    # Make key name more readable
    display = key

    for prefix in ("OEM_",):
        if display.startswith(prefix):
            display = display[len(prefix) :]

    parts.append(display)
    return "+".join(parts)
