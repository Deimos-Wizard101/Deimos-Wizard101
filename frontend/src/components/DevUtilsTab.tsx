import { useState } from 'react';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { GUICommandType, GUIKeys, WORLDS } from '../types';
import type { DeimosState } from '../hooks/useDeimosSocket';

interface Props {
  state: DeimosState;
  send: (type: string, data?: unknown) => void;
}

export function DevUtilsTab({ state, send }: Props) {
  const [xInput, setXInput] = useState('');
  const [yInput, setYInput] = useState('');
  const [zInput, setZInput] = useState('');
  const [yawInput, setYawInput] = useState('');
  const [entityInput, setEntityInput] = useState('');
  const [zoneInput, setZoneInput] = useState('');
  const [worldInput, setWorldInput] = useState('WizardCity');

  const handleCustomTP = () => {
    if (xInput || yInput || zInput || yawInput) {
      send(GUICommandType.CustomTeleport, {
        X: xInput,
        Y: yInput,
        Z: zInput,
        Yaw: yawInput,
      });
    }
  };

  const handleEntityTP = () => {
    if (entityInput) {
      send(GUICommandType.EntityTeleport, entityInput);
    }
  };

  return (
    <div className="space-y-4">
      {/* Custom TP */}
      <div className="border border-border rounded-lg p-3 space-y-3">
        <h3 className="text-sm font-semibold text-muted-foreground">TP Utils</h3>
        <p className="text-xs text-muted-foreground">The utils below are for advanced users and no support will be given on them.</p>
        <div className="flex items-center gap-2 flex-wrap">
          <label className="text-xs">X:</label>
          <Input className="w-20" value={xInput} onChange={e => setXInput(e.target.value)} />
          <label className="text-xs">Y:</label>
          <Input className="w-20" value={yInput} onChange={e => setYInput(e.target.value)} />
          <label className="text-xs">Z:</label>
          <Input className="w-20" value={zInput} onChange={e => setZInput(e.target.value)} />
          <label className="text-xs">Yaw:</label>
          <Input className="w-20" value={yawInput} onChange={e => setYawInput(e.target.value)} />
          <Button size="sm" onClick={handleCustomTP}>Custom TP</Button>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-xs">Entity Name:</label>
          <Input className="flex-1" value={entityInput} onChange={e => setEntityInput(e.target.value)} />
          <Button size="sm" onClick={handleEntityTP}>Entity TP</Button>
        </div>
      </div>

      {/* Dev Utils */}
      <div className="border border-border rounded-lg p-3 space-y-3">
        <h3 className="text-sm font-semibold text-muted-foreground">Dev Utils</h3>
        <div className="flex gap-2">
          <Button size="sm" variant="secondary" onClick={() => send(GUICommandType.Copy, GUIKeys.copy_entity_list)}>
            Available Entities
          </Button>
          <Button size="sm" variant="secondary" onClick={() => send(GUICommandType.Copy, GUIKeys.copy_ui_tree)}>
            Available Paths
          </Button>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-xs">Zone Name:</label>
          <Input className="w-40" value={zoneInput} onChange={e => setZoneInput(e.target.value)} />
          <Button size="sm" onClick={() => zoneInput && send(GUICommandType.GoToZone, [false, zoneInput])}>
            Go To Zone
          </Button>
          <Button size="sm" variant="secondary" onClick={() => zoneInput && send(GUICommandType.GoToZone, [true, zoneInput])}>
            Mass Go To Zone
          </Button>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-xs">World Name:</label>
          <Select value={worldInput} onValueChange={setWorldInput}>
            <SelectTrigger className="w-40">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {WORLDS.map(w => (
                <SelectItem key={w} value={w}>{w}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button size="sm" onClick={() => send(GUICommandType.GoToWorld, [false, worldInput])}>
            Go To World
          </Button>
          <Button size="sm" variant="secondary" onClick={() => send(GUICommandType.GoToWorld, [true, worldInput])}>
            Mass Go To World
          </Button>
        </div>
        <div className="flex gap-2 flex-wrap">
          <Button size="sm" variant="secondary" onClick={() => send(GUICommandType.GoToBazaar, false)}>Go To Bazaar</Button>
          <Button size="sm" variant="secondary" onClick={() => send(GUICommandType.GoToBazaar, true)}>Mass Go To Bazaar</Button>
          <Button size="sm" variant="secondary" onClick={() => send(GUICommandType.RefillPotions, false)}>Refill Potions</Button>
          <Button size="sm" variant="secondary" onClick={() => send(GUICommandType.RefillPotions, true)}>Mass Refill Potions</Button>
        </div>
      </div>
    </div>
  );
}
