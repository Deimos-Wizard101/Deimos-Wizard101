import { useMemo, useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog';
import { Input } from './ui/input';

interface Props {
  open: boolean;
  title: string;
  description: string;
  data: string;
  onClose: () => void;
  /** If true, parse UI tree paths and copy path instead of raw line */
  isUITree?: boolean;
}

function parseUITreePaths(content: string): Map<string, string[]> {
  const lines = content.split('\n').filter(Boolean);
  const pathDict = new Map<string, string[]>();
  const pathStack: string[] = [];

  for (const line of lines) {
    const indent = line.length - line.replace(/^-+/, '').length;
    const cleanLine = line.replace(/^-+\s*/, '');
    const nameMatch = cleanLine.match(/\[(.*?)\]/);
    const name = nameMatch ? nameMatch[1] : cleanLine.split(/\s+/)[0];

    while (pathStack.length > indent) pathStack.pop();
    const currentPath = [...pathStack, name];
    pathDict.set(line, currentPath.length > 1 ? currentPath.slice(1) : currentPath);
    pathStack.push(name);
  }

  return pathDict;
}

export function EntityListDialog({ open, title, description, data, onClose, isUITree }: Props) {
  const [search, setSearch] = useState('');

  const lines = useMemo(() => data.split('\n').filter(Boolean), [data]);
  const pathDict = useMemo(() => isUITree ? parseUITreePaths(data) : null, [data, isUITree]);

  const filtered = useMemo(() => {
    if (!search) return lines;
    const lower = search.toLowerCase();
    return lines.filter(l => l.toLowerCase().includes(lower));
  }, [lines, search]);

  const handleSelect = (line: string) => {
    if (isUITree && pathDict) {
      const path = pathDict.get(line);
      if (path) {
        navigator.clipboard.writeText(String(path));
      }
    } else {
      navigator.clipboard.writeText(line);
    }
    onClose();
  };

  return (
    <Dialog open={open} onOpenChange={v => !v && onClose()}>
      <DialogContent className="max-w-2xl max-h-[80vh]">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>
        <p className="text-xs text-muted-foreground">{description}</p>
        <Input
          placeholder="Search..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="mb-2"
        />
        <div className="h-80 overflow-y-auto border border-border rounded-lg">
          {filtered.map((line, i) => (
            <button
              key={i}
              className="w-full text-left px-2 py-1 text-xs hover:bg-accent hover:text-accent-foreground font-mono truncate"
              onClick={() => handleSelect(line)}
            >
              {line}
            </button>
          ))}
          {filtered.length === 0 && (
            <p className="text-xs text-muted-foreground p-2">No results found.</p>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
