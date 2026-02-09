from enum import Enum, auto
import asyncio
import json
import queue
import re
import os

from loguru import logger
from aiohttp import web


class ToolClosedException(Exception):
    pass


class GUICommandType(Enum):
    # deimos <-> window
    Close = auto()
    AttemptedClose = auto()
    CloseFromBackend = auto()

    # window -> deimos
    ToggleOption = auto()
    Copy = auto()
    SelectEnemy = auto()

    Teleport = auto()
    CustomTeleport = auto()
    EntityTeleport = auto()

    XYZSync = auto()
    XPress = auto()

    GoToZone = auto()
    GoToWorld = auto()
    GoToBazaar = auto()

    RefillPotions = auto()

    AnchorCam = auto()
    SetCamPosition = auto()
    SetCamDistance = auto()

    ExecuteFlythrough = auto()
    KillFlythrough = auto()

    ExecuteBot = auto()
    KillBot = auto()

    SetPlaystyles = auto()

    # SetPetWorld = auto()

    SetScale = auto()

    SetPetWorld = auto()

    # deimos -> window
    UpdateWindow = auto()
    UpdateWindowValues = auto()
    UpdateConsole = auto()
    CopyConsole = auto()

    ShowUITreePopup = auto()
    ShowEntityListPopup = auto()

    LogMessage = auto()


# TODO:
# - inherit from StrEnum in 3.11 to make this nicer
# - fix naming convention, it's inconsistent
class GUIKeys:
    toggle_speedhack = "togglespeedhack"
    toggle_combat = "togglecombat"
    toggle_dialogue = "toggledialogue"
    toggle_sigil = "togglesigil"
    toggle_questing = "toggle_questing"
    toggle_auto_pet = "toggleautopet"
    toggle_auto_potion = "toggleautopotion"
    toggle_freecam = "togglefreecam"
    toggle_camera_collision = "togglecameracollision"
    toggle_show_expanded_logs = "toggleshowexpandedlogs"

    hotkey_quest_tp = "hotkeyquesttp"
    hotkey_freecam_tp = "hotkeyfreecamtp"

    mass_hotkey_mass_tp = "masshotkeymasstp"
    mass_hotkey_xyz_sync = "masshotkeyxyzsync"
    mass_hotkey_x_press = "masshotkeyxpress"

    copy_position = "copyposition"
    copy_zone = "copyzone"
    copy_rotation = "copyrotation"
    copy_entity_list = "copyentitylist"
    copy_ui_tree = "copyuitree"
    copy_camera_position = "copycameraposition"
    copy_stats = "copystats"
    copy_camera_rotation = "copycamerarotation"
    copy_logs = "copylogs"

    button_custom_tp = "buttoncustomtp"
    button_entity_tp = "buttonentitytp"
    button_go_to_zone = "buttongotozone"
    button_mass_go_to_zone = "buttonmassgotozone"
    button_go_to_world = "buttongotoworld"
    button_mass_go_to_world = "buttonmassgotoworld"
    button_go_to_bazaar = "buttongotobazaar"
    button_mass_go_to_bazaar = "buttonmassgotobazaar"
    button_refill_potions = "buttonrefillpotions"
    button_mass_refill_potions = "buttonmassrefillpotions"
    button_set_camera_position = "buttonsetcameraposition"
    button_anchor = "buttonanchor"
    button_set_distance = "buttonsetdistance"
    button_view_stats = "buttonviewstats"
    button_swap_members = "buttonswapmembers"

    button_execute_flythrough = "buttonexecuteflythrough"
    button_kill_flythrough = "buttonkillflythrough"
    button_run_bot = "buttonrunbot"
    button_kill_bot = "buttonkillbot"
    button_set_playstyles = "buttonsetplaystyles"
    button_set_scale = "buttonsetscale"


class GUICommand:
    def __init__(self, com_type: GUICommandType, data=None):
        self.com_type = com_type
        self.data = data

    def to_dict(self):
        data = self.data
        # Convert tuples to lists for JSON serialization
        if isinstance(data, tuple):
            data = list(data)
        return {"type": self.com_type.name, "data": data}

    @staticmethod
    def from_dict(d: dict) -> 'GUICommand':
        com_type = GUICommandType[d["type"]]
        data = d.get("data")
        # Reconstruct tuple data for commands that expect tuples
        if com_type == GUICommandType.GoToZone and isinstance(data, list):
            data = (data[0], data[1])
        elif com_type == GUICommandType.GoToWorld and isinstance(data, list):
            data = (data[0], data[1])
        elif com_type == GUICommandType.SelectEnemy and isinstance(data, list):
            data = tuple(data)
        return GUICommand(com_type, data)


class WebSocketLogSink:
    """Loguru sink that buffers log messages and sends them via WebSocket."""
    def __init__(self):
        self.buffer = []
        self.max_lines = 1000
        self.bridge = None  # Set after bridge is created

        self.level_colors = {
            "DEBUG": "grey",
            "INFO": "white",
            "SUCCESS": "white",
            "WARNING": "yellow",
            "ERROR": "red",
            "CRITICAL": "white"
        }

        self.level_bg = {
            "SUCCESS": "green",
            "CRITICAL": "red"
        }

    def write(self, message):
        # Strip ANSI color codes
        ansi_pattern = r'\033\[\d+m'
        clean_message = re.sub(ansi_pattern, '', message)

        split_msg = clean_message.split("|")
        if len(split_msg) < 3:
            for l in self.level_colors:
                if l in clean_message:
                    level = l
                    break
            else:
                level = "DEBUG"
        else:
            level = split_msg[1].strip()

        def collapse_log(input_str: str) -> str:
            if "-" not in input_str:
                return input_str
            split_input = input_str.split("-")
            if len(split_input) < 4:
                return input_str
            return split_input[3].lstrip()

        truncated_message = level + " - " + collapse_log(clean_message)

        entry = {
            "message": clean_message,
            "truncated": truncated_message,
            "level": level
        }

        self.buffer.append(entry)
        if len(self.buffer) > self.max_lines:
            self.buffer.pop(0)

        # Send to connected WebSocket clients via the bridge
        if self.bridge:
            cmd = GUICommand(GUICommandType.LogMessage, entry)
            self.bridge._enqueue_to_clients(cmd)

    def get_buffer(self):
        return self.buffer

    def copy(self):
        import pyperclip
        log_str = "```\n"
        for entry in self.buffer:
            log_str += entry["message"]
        pyperclip.copy(log_str + "```")
        logger.debug("Copied current logs.")


class WebSocketBridge:
    """Bridges the existing queue.Queue system to WebSocket clients."""

    def __init__(self, send_queue: queue.Queue, recv_queue: queue.Queue, host="127.0.0.1", port=38762):
        self.send_queue = send_queue  # GUI -> Deimos (recv_queue from manage_gui perspective)
        self.recv_queue = recv_queue  # Deimos -> GUI (gui_send_queue)
        self.host = host
        self.port = port
        self._clients: set[web.WebSocketResponse] = set()
        self._app = None
        self._runner = None
        self.log_sink = WebSocketLogSink()
        self.log_sink.bridge = self

    def _enqueue_to_clients(self, cmd: GUICommand):
        """Queue a command to be sent to all connected WS clients (non-blocking)."""
        msg = json.dumps(cmd.to_dict())
        for ws in list(self._clients):
            if not ws.closed:
                asyncio.ensure_future(ws.send_str(msg))

    async def _ws_handler(self, request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self._clients.add(ws)
        logger.info("WebSocket client connected")

        # Send current log buffer to new client
        for entry in self.log_sink.buffer:
            cmd = GUICommand(GUICommandType.LogMessage, entry)
            await ws.send_str(json.dumps(cmd.to_dict()))

        try:
            async for msg in ws:
                if msg.type == web.WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                        cmd = GUICommand.from_dict(data)
                        self.send_queue.put(cmd)
                    except (json.JSONDecodeError, KeyError) as e:
                        logger.warning(f"Invalid WS message: {e}")
                elif msg.type == web.WSMsgType.ERROR:
                    logger.warning(f"WS error: {ws.exception()}")
        finally:
            self._clients.discard(ws)
            logger.info("WebSocket client disconnected")

        return ws

    async def _drain_queue(self):
        """Continuously drain recv_queue (Deimos -> GUI) and send to WS clients."""
        while True:
            try:
                while True:
                    cmd = self.recv_queue.get_nowait()
                    self._enqueue_to_clients(cmd)
            except queue.Empty:
                pass
            await asyncio.sleep(0.05)

    async def start(self):
        """Start the aiohttp server with WebSocket and static file serving."""
        self._app = web.Application()

        # WebSocket route
        self._app.router.add_get('/ws', self._ws_handler)

        # Serve React build files
        src_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(src_dir)
        frontend_dist = os.path.join(project_root, 'frontend', 'dist')
        index_html = os.path.join(frontend_dist, 'index.html')
        assets_dir = os.path.join(frontend_dist, 'assets')

        if os.path.isfile(index_html):
            # Serve static assets first (JS, CSS bundles)
            if os.path.isdir(assets_dir):
                self._app.router.add_static('/assets/', assets_dir)

            # Catch-all: serve matching files or fall back to index.html for SPA routing
            async def spa_handler(request):
                # Serve index.html for root
                if request.path == '/':
                    return web.FileResponse(index_html)
                # Try to serve the file directly from dist
                rel_path = request.path.lstrip('/')
                file_path = os.path.join(frontend_dist, rel_path)
                if os.path.isfile(file_path):
                    return web.FileResponse(file_path)
                # SPA fallback
                return web.FileResponse(index_html)

            self._app.router.add_get('/{path:.*}', spa_handler)
        else:
            logger.warning(f"Frontend build not found at {frontend_dist}. Run 'cd frontend && bun run build' to build the GUI.")

            async def no_frontend_handler(request):
                if request.path == '/ws':
                    return  # handled by ws_handler
                return web.Response(
                    text="Deimos GUI not built. Run 'cd frontend && bun run build' first, then restart.",
                    content_type='text/plain',
                    status=503,
                )

            self._app.router.add_get('/', no_frontend_handler)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self.host, self.port)
        await site.start()
        logger.info(f"Deimos GUI server started at http://{self.host}:{self.port}")

        # Start queue drain loop
        await self._drain_queue()

    async def shutdown(self):
        """Gracefully shut down the server."""
        for ws in list(self._clients):
            await ws.close()
        if self._runner:
            await self._runner.cleanup()
