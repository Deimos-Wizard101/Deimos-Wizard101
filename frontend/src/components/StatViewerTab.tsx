import { useState } from 'react';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { Checkbox } from './ui/checkbox';
import { GUICommandType, GUIKeys, SCHOOLS, SCHOOL_ID_MAP } from '../types';
import type { DeimosState } from '../hooks/useDeimosSocket';

interface Props {
  state: DeimosState;
  send: (type: string, data?: unknown) => void;
}

export function StatViewerTab({ state, send }: Props) {
  const [enemyIndex, setEnemyIndex] = useState('1');
  const [allyIndex, setAllyIndex] = useState('1');
  const [damage, setDamage] = useState('');
  const [school, setSchool] = useState('Fire');
  const [critChecked, setCritChecked] = useState(true);
  const [forceSchool, setForceSchool] = useState(false);

  // Use values from backend if available
  const enemyOptions = state.windowValues['EnemyInput'] || Array.from({ length: 12 }, (_, i) => String(i + 1));
  const allyOptions = state.windowValues['AllyInput'] || Array.from({ length: 12 }, (_, i) => String(i + 1));
  const statText = state.windowState['stat_viewer'] || 'No client has been selected.';

  // Sync selected values from backend
  const displayEnemy = state.windowState['EnemyInput'] || enemyIndex;
  const displayAlly = state.windowState['AllyInput'] || allyIndex;
  const displaySchool = state.windowState['SchoolInput'] || school;

  const handleViewStats = () => {
    const eIdx = parseInt(displayEnemy) || parseInt(enemyIndex);
    const aIdx = parseInt(displayAlly) || parseInt(allyIndex);
    const baseDmg = damage.replace(/[^0-9]/g, '');
    const schoolId = SCHOOL_ID_MAP[displaySchool] || SCHOOL_ID_MAP[school];
    send(GUICommandType.SelectEnemy, [eIdx, aIdx, baseDmg, schoolId, critChecked, forceSchool]);
  };

  const handleSwapMembers = () => {
    setEnemyIndex(allyIndex);
    setAllyIndex(enemyIndex);
  };

  return (
    <div className="border border-border rounded-lg p-3 space-y-3">
      <h3 className="text-sm font-semibold text-muted-foreground">Stat Viewer</h3>
      <p className="text-xs text-muted-foreground">The utils below are for advanced users and no support will be given on them.</p>

      {/* Index selectors */}
      <div className="flex items-center gap-2">
        <label className="text-xs">Caster/Target Indices:</label>
        <Select value={displayEnemy} onValueChange={v => setEnemyIndex(v)}>
          <SelectTrigger className="w-32">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {enemyOptions.map((v) => (
              <SelectItem key={`e-${v}`} value={String(v)}>{v}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={displayAlly} onValueChange={v => setAllyIndex(v)}>
          <SelectTrigger className="w-32">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {allyOptions.map((v) => (
              <SelectItem key={`a-${v}`} value={String(v)}>{v}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Damage / School / Crit */}
      <div className="flex items-center gap-2 flex-wrap">
        <label className="text-xs">Dmg:</label>
        <Input className="w-20" value={damage} onChange={e => setDamage(e.target.value)} />
        <label className="text-xs">School:</label>
        <Select value={displaySchool} onValueChange={v => setSchool(v)}>
          <SelectTrigger className="w-28">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {SCHOOLS.map(s => (
              <SelectItem key={s} value={s}>{s}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <label className="text-xs">Crit:</label>
        <Checkbox checked={critChecked} onCheckedChange={v => setCritChecked(!!v)} />
        <Button size="sm" onClick={handleViewStats}>View Stats</Button>
        <Button size="sm" variant="secondary" onClick={() => send(GUICommandType.Copy, GUIKeys.copy_stats)}>Copy Stats</Button>
      </div>

      {/* Stat display */}
      <pre className="border border-border rounded-lg p-2 h-48 overflow-y-auto overflow-x-auto font-mono text-xs bg-zinc-950 whitespace-pre-wrap">
        {statText}
      </pre>

      {/* Swap / Force school */}
      <div className="flex items-center gap-2">
        <Button size="sm" variant="secondary" onClick={handleSwapMembers}>Swap Members</Button>
        <label className="text-xs">Force School Damage:</label>
        <Checkbox checked={forceSchool} onCheckedChange={v => setForceSchool(!!v)} />
      </div>
    </div>
  );
}
