import { Tabs, TabsContent, TabsList, TabsTrigger } from './components/ui/tabs';
import { useDeimosSocket } from './hooks/useDeimosSocket';
import { ClientInfo } from './components/ClientInfo';
import { HotkeysTab } from './components/HotkeysTab';
import { CameraTab } from './components/CameraTab';
import { DevUtilsTab } from './components/DevUtilsTab';
import { StatViewerTab } from './components/StatViewerTab';
import { FlythroughTab } from './components/FlythroughTab';
import { BotTab } from './components/BotTab';
import { CombatTab } from './components/CombatTab';
import { MiscTab } from './components/MiscTab';
import { ConsoleTab } from './components/ConsoleTab';
import { EntityListDialog } from './components/EntityListDialog';

export default function App() {
  const { state, send, dismissEntityList, dismissUITree } = useDeimosSocket();

  return (
    <div className="max-w-4xl mx-auto p-4 space-y-4">
      <p className="text-xs text-muted-foreground">
        Deimos will always be a free tool. If you paid for this, you got scammed!
      </p>

      <Tabs defaultValue="hotkeys">
        <TabsList className="flex-wrap h-auto gap-1">
          <TabsTrigger value="hotkeys">Hotkeys</TabsTrigger>
          <TabsTrigger value="camera">Camera</TabsTrigger>
          <TabsTrigger value="devutils">Dev Utils</TabsTrigger>
          <TabsTrigger value="statviewer">Stat Viewer</TabsTrigger>
          <TabsTrigger value="flythrough">Flythrough</TabsTrigger>
          <TabsTrigger value="bot">Bot</TabsTrigger>
          <TabsTrigger value="combat">Combat</TabsTrigger>
          <TabsTrigger value="misc">Misc</TabsTrigger>
          <TabsTrigger value="console">Console</TabsTrigger>
        </TabsList>

        <TabsContent value="hotkeys"><HotkeysTab state={state} send={send} /></TabsContent>
        <TabsContent value="camera"><CameraTab state={state} send={send} /></TabsContent>
        <TabsContent value="devutils"><DevUtilsTab state={state} send={send} /></TabsContent>
        <TabsContent value="statviewer"><StatViewerTab state={state} send={send} /></TabsContent>
        <TabsContent value="flythrough"><FlythroughTab send={send} /></TabsContent>
        <TabsContent value="bot"><BotTab send={send} /></TabsContent>
        <TabsContent value="combat"><CombatTab send={send} /></TabsContent>
        <TabsContent value="misc"><MiscTab send={send} /></TabsContent>
        <TabsContent value="console"><ConsoleTab state={state} send={send} /></TabsContent>
      </Tabs>

      <ClientInfo state={state} />

      {/* Entity list popup */}
      <EntityListDialog
        open={!!state.entityListData}
        title="Entity List"
        description="Click the entity needed to copy the name and location to clipboard."
        data={state.entityListData || ''}
        onClose={dismissEntityList}
      />

      {/* UI tree popup */}
      <EntityListDialog
        open={!!state.uiTreeData}
        title="UI Tree"
        description="Click the path needed to copy it to clipboard."
        data={state.uiTreeData || ''}
        onClose={dismissUITree}
        isUITree
      />
    </div>
  );
}
