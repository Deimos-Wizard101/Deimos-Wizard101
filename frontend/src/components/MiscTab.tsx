import { useState } from 'react';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { GUICommandType, PET_WORLDS } from '../types';

interface Props {
  send: (type: string, data?: unknown) => void;
}

export function MiscTab({ send }: Props) {
  const [scale, setScale] = useState('');
  const [petWorld, setPetWorld] = useState('WizardCity');

  return (
    <div className="border border-border rounded-lg p-3 space-y-3">
      <h3 className="text-sm font-semibold text-muted-foreground">Misc Utils</h3>
      <p className="text-xs text-muted-foreground">The utils below are for advanced users and no support will be given on them.</p>
      <div className="flex items-center gap-2">
        <label className="text-xs">Scale:</label>
        <Input className="w-24" value={scale} onChange={e => setScale(e.target.value)} />
        <Button size="sm" onClick={() => send(GUICommandType.SetScale, scale)}>Set Scale</Button>
      </div>
      <div className="flex items-center gap-2">
        <label className="text-xs">Select a pet world:</label>
        <Select value={petWorld} onValueChange={v => {
          setPetWorld(v);
          send(GUICommandType.SetPetWorld, v);
        }}>
          <SelectTrigger className="w-40">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {PET_WORLDS.map(w => (
              <SelectItem key={w} value={w}>{w}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    </div>
  );
}
