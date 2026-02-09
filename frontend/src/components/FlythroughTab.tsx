import { useRef, useState } from 'react';
import { Button } from './ui/button';
import { Textarea } from './ui/textarea';
import { GUICommandType } from '../types';

interface Props {
  send: (type: string, data?: unknown) => void;
}

export function FlythroughTab({ send }: Props) {
  const [script, setScript] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleImport = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => setScript(reader.result as string);
    reader.readAsText(file);
    e.target.value = '';
  };

  const handleExport = () => {
    const blob = new Blob([script], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'flythrough.txt';
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="border border-border rounded-lg p-3 space-y-3">
      <h3 className="text-sm font-semibold text-muted-foreground">Flythrough Creator</h3>
      <p className="text-xs text-muted-foreground">The utils below are for advanced users and no support will be given on them.</p>
      <Textarea
        className="h-64 font-mono text-xs"
        value={script}
        onChange={e => setScript(e.target.value)}
        placeholder="Enter flythrough commands..."
      />
      <div className="flex gap-2 flex-wrap">
        <input ref={fileInputRef} type="file" accept=".txt" className="hidden" onChange={handleImport} />
        <Button size="sm" variant="secondary" onClick={() => fileInputRef.current?.click()}>Import Flythrough</Button>
        <Button size="sm" variant="secondary" onClick={handleExport}>Export Flythrough</Button>
        <Button size="sm" onClick={() => send(GUICommandType.ExecuteFlythrough, script)}>Execute Flythrough</Button>
        <Button size="sm" variant="destructive" onClick={() => send(GUICommandType.KillFlythrough)}>Kill Flythrough</Button>
      </div>
    </div>
  );
}
