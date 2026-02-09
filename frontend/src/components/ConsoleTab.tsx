import { useEffect, useRef, useState } from 'react';
import { Button } from './ui/button';
import { GUICommandType, GUIKeys } from '../types';
import type { DeimosState } from '../hooks/useDeimosSocket';

interface Props {
  state: DeimosState;
  send: (type: string, data?: unknown) => void;
}

const levelColorMap: Record<string, string> = {
  DEBUG: 'text-gray-400',
  INFO: 'text-zinc-100',
  SUCCESS: 'text-green-400',
  WARNING: 'text-yellow-400',
  ERROR: 'text-red-400',
  CRITICAL: 'text-red-300 bg-red-900/40',
};

export function ConsoleTab({ state, send }: Props) {
  const [expanded, setExpanded] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [state.logs.length]);

  const handleCopyLogs = () => {
    const logStr = "```\n" + state.logs.map(l => l.message).join('') + "```";
    navigator.clipboard.writeText(logStr);
  };

  return (
    <div className="space-y-2">
      <p className="text-xs text-muted-foreground">Be sure to include your logs when asking for support.</p>
      <div
        ref={scrollRef}
        className="border border-border rounded-lg p-2 h-80 overflow-y-auto overflow-x-auto font-mono text-xs bg-zinc-950"
      >
        {state.logs.map((entry, i) => (
          <div key={i} className={levelColorMap[entry.level] || 'text-zinc-100'}>
            {expanded ? entry.message : entry.truncated}
          </div>
        ))}
        {state.logs.length === 0 && (
          <span className="text-muted-foreground">No log messages yet.</span>
        )}
      </div>
      <div className="flex gap-2">
        <Button size="sm" variant="secondary" onClick={() => setExpanded(e => !e)}>
          {expanded ? 'Collapse Logs' : 'Expand Logs'}
        </Button>
        <Button size="sm" variant="secondary" onClick={handleCopyLogs}>
          Copy Logs
        </Button>
      </div>
    </div>
  );
}
