import { useCallback, useEffect, useRef, useState } from 'react';
import { GUICommandType, type GUIMessage, type LogEntry } from '../types';

export interface DeimosState {
  /** Key-value map from UpdateWindow messages, e.g. SpeedhackStatus -> "Enabled" */
  windowState: Record<string, string>;
  /** Key-values list map from UpdateWindowValues messages */
  windowValues: Record<string, string[]>;
  /** Log entries from LogMessage commands */
  logs: LogEntry[];
  /** Whether the WS is connected */
  connected: boolean;
  /** Data for entity list popup */
  entityListData: string | null;
  /** Data for UI tree popup */
  uiTreeData: string | null;
  /** Whether console expand is toggled */
  consoleExpanded: boolean;
}

export function useDeimosSocket() {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const [state, setState] = useState<DeimosState>({
    windowState: {},
    windowValues: {},
    logs: [],
    connected: false,
    entityListData: null,
    uiTreeData: null,
    consoleExpanded: false,
  });

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      setState(s => ({ ...s, connected: true }));
    };

    ws.onclose = () => {
      setState(s => ({ ...s, connected: false }));
      reconnectTimer.current = setTimeout(connect, 2000);
    };

    ws.onerror = () => {
      ws.close();
    };

    ws.onmessage = (event) => {
      try {
        const msg: GUIMessage = JSON.parse(event.data);
        handleMessage(msg);
      } catch {
        // ignore malformed messages
      }
    };

    wsRef.current = ws;
  }, []);

  const handleMessage = useCallback((msg: GUIMessage) => {
    switch (msg.type) {
      case GUICommandType.UpdateWindow: {
        const [key, value] = msg.data as [string, string];
        setState(s => ({
          ...s,
          windowState: { ...s.windowState, [key]: String(value) },
        }));
        break;
      }
      case GUICommandType.UpdateWindowValues: {
        const [key, values] = msg.data as [string, string[]];
        setState(s => ({
          ...s,
          windowValues: { ...s.windowValues, [key]: values },
        }));
        break;
      }
      case GUICommandType.LogMessage: {
        const entry = msg.data as LogEntry;
        setState(s => ({
          ...s,
          logs: [...s.logs.slice(-999), entry],
        }));
        break;
      }
      case GUICommandType.ShowEntityListPopup: {
        setState(s => ({ ...s, entityListData: msg.data as string }));
        break;
      }
      case GUICommandType.ShowUITreePopup: {
        setState(s => ({ ...s, uiTreeData: msg.data as string }));
        break;
      }
      case GUICommandType.UpdateConsole: {
        setState(s => ({ ...s, consoleExpanded: !s.consoleExpanded }));
        break;
      }
      case GUICommandType.CopyConsole: {
        // Copy logs to clipboard
        setState(s => {
          const logStr = "```\n" + s.logs.map(l => l.message).join('') + "```";
          navigator.clipboard.writeText(logStr);
          return s;
        });
        break;
      }
    }
  }, []);

  const send = useCallback((type: string, data?: unknown) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type, data: data ?? null }));
    }
  }, []);

  const dismissEntityList = useCallback(() => {
    setState(s => ({ ...s, entityListData: null }));
  }, []);

  const dismissUITree = useCallback(() => {
    setState(s => ({ ...s, uiTreeData: null }));
  }, []);

  useEffect(() => {
    connect();
    return () => {
      clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);

  return { state, send, dismissEntityList, dismissUITree };
}
