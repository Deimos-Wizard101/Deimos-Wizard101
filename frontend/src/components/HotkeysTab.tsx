import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { GUICommandType, GUIKeys } from '../types';
import type { DeimosState } from '../hooks/useDeimosSocket';

interface Props {
  state: DeimosState;
  send: (type: string, data?: unknown) => void;
}

const toggles = [
  { label: 'Speedhack', key: GUIKeys.toggle_speedhack, statusKey: 'SpeedhackStatus' },
  { label: 'Combat', key: GUIKeys.toggle_combat, statusKey: 'CombatStatus' },
  { label: 'Dialogue', key: GUIKeys.toggle_dialogue, statusKey: 'DialogueStatus' },
  { label: 'Sigil', key: GUIKeys.toggle_sigil, statusKey: 'SigilStatus' },
  { label: 'Questing', key: GUIKeys.toggle_questing, statusKey: 'QuestingStatus' },
  { label: 'Auto Pet', key: GUIKeys.toggle_auto_pet, statusKey: 'Auto PetStatus' },
  { label: 'Auto Potion', key: GUIKeys.toggle_auto_potion, statusKey: 'Auto PotionStatus' },
];

const hotkeys = [
  { label: 'Quest TP', key: GUIKeys.hotkey_quest_tp, type: GUICommandType.Teleport },
  { label: 'Freecam', key: GUIKeys.toggle_freecam, type: GUICommandType.ToggleOption },
  { label: 'Freecam TP', key: GUIKeys.hotkey_freecam_tp, type: GUICommandType.Teleport },
];

const massHotkeys = [
  { label: 'Mass TP', key: GUIKeys.mass_hotkey_mass_tp, type: GUICommandType.Teleport },
  { label: 'XYZ Sync', key: GUIKeys.mass_hotkey_xyz_sync, type: GUICommandType.XYZSync },
  { label: 'X Press', key: GUIKeys.mass_hotkey_x_press, type: GUICommandType.XPress },
];

const copyActions = [
  { label: 'Copy Zone', key: GUIKeys.copy_zone },
  { label: 'Copy Position', key: GUIKeys.copy_position },
  { label: 'Copy Rotation', key: GUIKeys.copy_rotation },
];

export function HotkeysTab({ state, send }: Props) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
      {/* Toggles */}
      <div className="border border-border rounded-lg p-3 space-y-2">
        <h3 className="text-sm font-semibold text-muted-foreground">Toggles</h3>
        {toggles.map(t => {
          const status = state.windowState[t.statusKey] || 'Disabled';
          const isEnabled = status === 'Enabled';
          return (
            <div key={t.key} className="flex items-center justify-between gap-2">
              <Button
                size="sm"
                variant="secondary"
                className="flex-1"
                onClick={() => send(GUICommandType.ToggleOption, t.key)}
              >
                {t.label}
              </Button>
              <Badge variant={isEnabled ? 'success' : 'secondary'} className="w-16 justify-center">
                {status}
              </Badge>
            </div>
          );
        })}
      </div>

      {/* Hotkeys */}
      <div className="border border-border rounded-lg p-3 space-y-2">
        <h3 className="text-sm font-semibold text-muted-foreground">Hotkeys</h3>
        {hotkeys.map(h => (
          <Button
            key={h.key}
            size="sm"
            variant="secondary"
            className="w-full"
            onClick={() => send(h.type, h.key)}
          >
            {h.label}
          </Button>
        ))}
      </div>

      {/* Mass Hotkeys */}
      <div className="border border-border rounded-lg p-3 space-y-2">
        <h3 className="text-sm font-semibold text-muted-foreground">Mass Hotkeys</h3>
        {massHotkeys.map(m => (
          <Button
            key={m.key}
            size="sm"
            variant="secondary"
            className="w-full"
            onClick={() => {
              if (m.type === GUICommandType.Teleport) {
                send(m.type, m.key);
              } else {
                send(m.type);
              }
            }}
          >
            {m.label}
          </Button>
        ))}
      </div>

      {/* Utils */}
      <div className="border border-border rounded-lg p-3 space-y-2">
        <h3 className="text-sm font-semibold text-muted-foreground">Utils</h3>
        {copyActions.map(c => (
          <Button
            key={c.key}
            size="sm"
            variant="secondary"
            className="w-full"
            onClick={() => send(GUICommandType.Copy, c.key)}
          >
            {c.label}
          </Button>
        ))}
      </div>
    </div>
  );
}
