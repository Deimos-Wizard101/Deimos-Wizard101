// Mirrors Python GUICommandType enum
export enum GUICommandType {
  Close = "Close",
  AttemptedClose = "AttemptedClose",
  CloseFromBackend = "CloseFromBackend",

  ToggleOption = "ToggleOption",
  Copy = "Copy",
  SelectEnemy = "SelectEnemy",

  Teleport = "Teleport",
  CustomTeleport = "CustomTeleport",
  EntityTeleport = "EntityTeleport",

  XYZSync = "XYZSync",
  XPress = "XPress",

  GoToZone = "GoToZone",
  GoToWorld = "GoToWorld",
  GoToBazaar = "GoToBazaar",

  RefillPotions = "RefillPotions",

  AnchorCam = "AnchorCam",
  SetCamPosition = "SetCamPosition",
  SetCamDistance = "SetCamDistance",

  ExecuteFlythrough = "ExecuteFlythrough",
  KillFlythrough = "KillFlythrough",

  ExecuteBot = "ExecuteBot",
  KillBot = "KillBot",

  SetPlaystyles = "SetPlaystyles",

  SetScale = "SetScale",
  SetPetWorld = "SetPetWorld",

  UpdateWindow = "UpdateWindow",
  UpdateWindowValues = "UpdateWindowValues",
  UpdateConsole = "UpdateConsole",
  CopyConsole = "CopyConsole",

  ShowUITreePopup = "ShowUITreePopup",
  ShowEntityListPopup = "ShowEntityListPopup",

  LogMessage = "LogMessage",
}

// Mirrors Python GUIKeys class
export const GUIKeys = {
  toggle_speedhack: "togglespeedhack",
  toggle_combat: "togglecombat",
  toggle_dialogue: "toggledialogue",
  toggle_sigil: "togglesigil",
  toggle_questing: "toggle_questing",
  toggle_auto_pet: "toggleautopet",
  toggle_auto_potion: "toggleautopotion",
  toggle_freecam: "togglefreecam",
  toggle_camera_collision: "togglecameracollision",
  toggle_show_expanded_logs: "toggleshowexpandedlogs",

  hotkey_quest_tp: "hotkeyquesttp",
  hotkey_freecam_tp: "hotkeyfreecamtp",

  mass_hotkey_mass_tp: "masshotkeymasstp",
  mass_hotkey_xyz_sync: "masshotkeyxyzsync",
  mass_hotkey_x_press: "masshotkeyxpress",

  copy_position: "copyposition",
  copy_zone: "copyzone",
  copy_rotation: "copyrotation",
  copy_entity_list: "copyentitylist",
  copy_ui_tree: "copyuitree",
  copy_camera_position: "copycameraposition",
  copy_stats: "copystats",
  copy_camera_rotation: "copycamerarotation",
  copy_logs: "copylogs",

  button_custom_tp: "buttoncustomtp",
  button_entity_tp: "buttonentitytp",
  button_go_to_zone: "buttongotozone",
  button_mass_go_to_zone: "buttonmassgotozone",
  button_go_to_world: "buttongotoworld",
  button_mass_go_to_world: "buttonmassgotoworld",
  button_go_to_bazaar: "buttongotobazaar",
  button_mass_go_to_bazaar: "buttonmassgotobazaar",
  button_refill_potions: "buttonrefillpotions",
  button_mass_refill_potions: "buttonmassrefillpotions",
  button_set_camera_position: "buttonsetcameraposition",
  button_anchor: "buttonanchor",
  button_set_distance: "buttonsetdistance",
  button_view_stats: "buttonviewstats",
  button_swap_members: "buttonswapmembers",

  button_execute_flythrough: "buttonexecuteflythrough",
  button_kill_flythrough: "buttonkillflythrough",
  button_run_bot: "buttonrunbot",
  button_kill_bot: "buttonkillbot",
  button_set_playstyles: "buttonsetplaystyles",
  button_set_scale: "buttonsetscale",
} as const;

export interface GUIMessage {
  type: string;
  data: unknown;
}

export interface LogEntry {
  message: string;
  truncated: string;
  level: string;
}

export const SCHOOL_ID_MAP: Record<string, number> = {
  Fire: 2343174,
  Ice: 72777,
  Storm: 83375795,
  Myth: 2448141,
  Life: 2330892,
  Death: 78318724,
  Balance: 2625203,
  Star: 2625634,
  Sun: 78483842,
  Moon: 2504141,
  Shadow: 393098038,
};

export const WORLDS = [
  'WizardCity', 'Krokotopia', 'Marleybone', 'MooShu', 'DragonSpire',
  'Grizzleheim', 'Celestia', 'Wysteria', 'Zafaria', 'Avalon',
  'Azteca', 'Khrysalis', 'Polaris', 'Mirage', 'Empyrea',
  'Karamelle', 'Lemuria',
];

export const PET_WORLDS = [
  'WizardCity', 'Krokotopia', 'Marleybone', 'Mooshu', 'Dragonspyre',
];

export const SCHOOLS = [
  'Fire', 'Ice', 'Storm', 'Myth', 'Life', 'Death', 'Balance',
  'Star', 'Sun', 'Moon', 'Shadow',
];
