import { Badge } from './ui/badge';
import type { DeimosState } from '../hooks/useDeimosSocket';

interface Props {
  state: DeimosState;
}

export function ClientInfo({ state }: Props) {
  const title = state.windowState['Title'] || 'Client: ';
  const zone = state.windowState['Zone'] || 'Zone: ';
  const xyz = state.windowState['xyz'] || 'Position (XYZ): ';
  const pry = state.windowState['pry'] || 'Orientation (PRY): ';

  return (
    <div className="border border-border rounded-lg p-3 space-y-1 bg-zinc-900/50">
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium">{title}</span>
        <Badge variant={state.connected ? 'success' : 'destructive'} className="text-[10px]">
          {state.connected ? 'Connected' : 'Disconnected'}
        </Badge>
      </div>
      <p className="text-xs text-muted-foreground">{zone}</p>
      <p className="text-xs text-muted-foreground">{xyz}</p>
      <p className="text-xs text-muted-foreground">{pry}</p>
    </div>
  );
}
