import { useState } from 'react';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { GUICommandType, GUIKeys } from '../types';
import type { DeimosState } from '../hooks/useDeimosSocket';

interface Props {
  state: DeimosState;
  send: (type: string, data?: unknown) => void;
}

export function CameraTab({ state, send }: Props) {
  const [camX, setCamX] = useState('');
  const [camY, setCamY] = useState('');
  const [camZ, setCamZ] = useState('');
  const [camYaw, setCamYaw] = useState('');
  const [camRoll, setCamRoll] = useState('');
  const [camPitch, setCamPitch] = useState('');
  const [camEntity, setCamEntity] = useState('');
  const [camDistance, setCamDistance] = useState('');
  const [camMin, setCamMin] = useState('');
  const [camMax, setCamMax] = useState('');

  const handleSetPosition = () => {
    if (camX || camY || camZ || camYaw || camRoll || camPitch) {
      send(GUICommandType.SetCamPosition, {
        X: camX, Y: camY, Z: camZ,
        Yaw: camYaw, Roll: camRoll, Pitch: camPitch,
      });
    }
  };

  const handleSetDistance = () => {
    if (camDistance || camMin || camMax) {
      send(GUICommandType.SetCamDistance, {
        Distance: camDistance, Min: camMin, Max: camMax,
      });
    }
  };

  return (
    <div className="border border-border rounded-lg p-3 space-y-3">
      <h3 className="text-sm font-semibold text-muted-foreground">Camera Controls</h3>
      <p className="text-xs text-muted-foreground">The utils below are for advanced users and no support will be given on them.</p>

      {/* Position */}
      <div className="flex items-center gap-2 flex-wrap">
        <label className="text-xs">X:</label>
        <Input className="w-24" value={camX} onChange={e => setCamX(e.target.value)} />
        <label className="text-xs">Y:</label>
        <Input className="w-24" value={camY} onChange={e => setCamY(e.target.value)} />
        <label className="text-xs">Z:</label>
        <Input className="w-24" value={camZ} onChange={e => setCamZ(e.target.value)} />
        <Button size="sm" onClick={handleSetPosition}>Set Camera Position</Button>
      </div>

      {/* Rotation */}
      <div className="flex items-center gap-2 flex-wrap">
        <label className="text-xs">Yaw:</label>
        <Input className="w-24" value={camYaw} onChange={e => setCamYaw(e.target.value)} />
        <label className="text-xs">Roll:</label>
        <Input className="w-24" value={camRoll} onChange={e => setCamRoll(e.target.value)} />
        <label className="text-xs">Pitch:</label>
        <Input className="w-24" value={camPitch} onChange={e => setCamPitch(e.target.value)} />
      </div>

      {/* Anchor */}
      <div className="flex items-center gap-2">
        <label className="text-xs">Entity:</label>
        <Input className="w-48" value={camEntity} onChange={e => setCamEntity(e.target.value)} />
        <Button size="sm" onClick={() => send(GUICommandType.AnchorCam, camEntity)}>Anchor</Button>
        <Button size="sm" variant="secondary" onClick={() => send(GUICommandType.ToggleOption, GUIKeys.toggle_camera_collision)}>
          Toggle Camera Collision
        </Button>
      </div>

      {/* Distance */}
      <div className="flex items-center gap-2 flex-wrap">
        <label className="text-xs">Distance:</label>
        <Input className="w-24" value={camDistance} onChange={e => setCamDistance(e.target.value)} />
        <label className="text-xs">Min:</label>
        <Input className="w-24" value={camMin} onChange={e => setCamMin(e.target.value)} />
        <label className="text-xs">Max:</label>
        <Input className="w-24" value={camMax} onChange={e => setCamMax(e.target.value)} />
        <Button size="sm" onClick={handleSetDistance}>Set Distance</Button>
      </div>

      {/* Copy buttons */}
      <div className="flex gap-2">
        <Button size="sm" variant="secondary" onClick={() => send(GUICommandType.Copy, GUIKeys.copy_camera_position)}>
          Copy Camera Position
        </Button>
        <Button size="sm" variant="secondary" onClick={() => send(GUICommandType.Copy, GUIKeys.copy_camera_rotation)}>
          Copy Camera Rotation
        </Button>
      </div>
    </div>
  );
}
