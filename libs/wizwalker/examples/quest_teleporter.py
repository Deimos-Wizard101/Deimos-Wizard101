import asyncio

import wizwalker
from wizwalker.hotkey import Hotkey, Listener, ModifierKeys


class Quester(wizwalker.ClientHandler):
    def __init__(self):
        super().__init__()
        self.get_new_clients()

    async def activate_hooks(self):
        for client in self.clients:
            await client.hook_handler.activate_quest_hook()
            await client.hook_handler.activate_player_hook()
            await client.hook_handler.activate_movement_teleport_hook()

    async def handle_e_pressed(self):
        for client in self.clients:
            await client.teleport(await client.quest_position.position())

    async def run(self):
        await self.activate_hooks()

        quest_hotkey = Hotkey(
            wizwalker.Keycode.Q,
            self.handle_e_pressed,
            modifiers=ModifierKeys.SHIFT | ModifierKeys.NOREPEAT,
        )
        quest_listener = Listener(quest_hotkey)

        while True:
            await quest_listener.listen()


if __name__ == "__main__":
    quester = Quester()
    try:
        asyncio.run(quester.run())
    finally:
        print("Exiting")
        asyncio.run(quester.close())
